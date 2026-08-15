"""
pipeline_orchestrator_tool.py

Orquestador de pipelines con dependencias explicitas entre tools ya
registradas en tool_registry. Sin NLP, sin inferencia automatica de
dependencias: el usuario declara el JSON de pasos y de donde sale/entra
cada dato.

Paso de datos ENTRE pasos del mismo pipeline: dict en memoria (no usa
workspace_tool.save_run/load_run, que estan pensados para arrays
numericos via npz y no para resultados JSON arbitrarios con estructura
mixta). Persistencia opcional al workspace real solo si el paso lo pide
explicitamente via 'persist_to_workspace' (ver mas abajo).

Se registra a si mismo como una tool mas: 'run_pipeline', con
mode='execute' y mode='validate' (mismo patron que el resto del repo).
"""
import json

import tool_registry  # se usa para REGISTRY (lookup de handlers dentro del pipeline)
from workspace_tool import save_run, load_run_safe, workspace_link  # solo para persistencia opcional final


def _extract_field(result, field_path):
    """Navega result (dict anidado) segun field_path tipo 'a.b.c'."""
    if field_path is None:
        return result
    cur = result
    for part in field_path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(
                f"extract_field {field_path!r} no encontrado (fallo en {part!r})"
            )
        cur = cur[part]
    return cur


def dry_check_pipeline(steps):
    """
    Valida el pipeline SIN ejecutar nada. Devuelve (ok: bool, report: list[dict]).
    Chequea: tool existe en tool_registry.REGISTRY, step_id unico y presente,
    input_from_step con las claves requeridas.
    """
    report = []
    ok = True
    seen_ids = set()

    for step in steps:
        step_id = step.get("step_id")
        tool = step.get("tool")
        issues = []

        if not step_id:
            issues.append("falta step_id")
        elif step_id in seen_ids:
            issues.append(f"step_id duplicado: {step_id!r}")
        seen_ids.add(step_id)

        if tool not in tool_registry.REGISTRY:
            issues.append(f"tool no encontrada en tool_registry.REGISTRY: {tool!r}")

        ifs = step.get("input_from_step")
        if ifs is not None:
            if not ifs.get("source_step_id"):
                issues.append("input_from_step sin 'source_step_id'")
            elif ifs["source_step_id"] not in seen_ids:
                issues.append(
                    f"input_from_step referencia source_step_id="
                    f"{ifs['source_step_id']!r} que no aparecio antes en el pipeline"
                )
            if not ifs.get("maps_to_param"):
                issues.append("input_from_step sin 'maps_to_param'")

        ifw = step.get("input_from_workspace")
        if ifw is not None:
            if not ifw.get("ref"):
                issues.append("input_from_workspace sin 'ref' (run_id o alias)")
            if not ifw.get("maps_to_param"):
                issues.append("input_from_workspace sin 'maps_to_param'")

        if issues:
            ok = False
        report.append({"step_id": step_id, "tool": tool, "issues": issues})

    return ok, report


def run_pipeline(steps, verbose=True):
    """
    Ejecuta un pipeline ya validado. steps: lista de dicts, cada uno:
      {
        "step_id": str,
        "tool": str (debe existir en tool_registry.REGISTRY),
        "arguments": {"mode": ..., "params": {...}},   # como cualquier tools/call
        "input_from_step": {                            # opcional
            "source_step_id": str,
            "extract_field": "a.b.c" | None,             # None = resultado completo
            "maps_to_param": str                         # nombre del param destino
        },
        "persist_to_workspace": "run_id_opcional" | None  # opcional, ver docstring del modulo
      }

    Devuelve dict con status y resultados por paso. Aborta el resto del
    pipeline (no sigue en cascada) si un paso falla.
    """
    ok, dry_report = dry_check_pipeline(steps)
    if not ok:
        if verbose:
            print("ABORTADO: el pipeline no paso el dry-check.")
            for entry in dry_report:
                if entry["issues"]:
                    print(f"  [FAIL] {entry['step_id']}: {'; '.join(entry['issues'])}")
        return {"status": "aborted", "dry_check_report": dry_report, "results": []}

    in_memory_results = {}  # step_id -> resultado completo de esa tool
    results = []

    for step in steps:
        step_id = step["step_id"]
        tool_name = step["tool"]
        args = dict(step.get("arguments", {}))  # copia, no mutar el config original

        ifs = step.get("input_from_step")
        if ifs is not None:
            try:
                source_result = in_memory_results[ifs["source_step_id"]]
                extracted = _extract_field(source_result, ifs.get("extract_field"))
            except KeyError as e:
                msg = f"no se pudo resolver input_from_step -- {e}"
                if verbose:
                    print(f"[FAIL] {step_id}: {msg}")
                results.append({"step_id": step_id, "status": "failed", "error": msg})
                break
            params = args.setdefault("params", {})
            params[ifs["maps_to_param"]] = extracted

        ifw = step.get("input_from_workspace")
        if ifw is not None:
            try:
                ref = ifw["ref"]
                resolved = workspace_link("resolve", alias=ref)
                run_id = resolved["run_id"] if "run_id" in resolved and not resolved.get("dangling") else ref
                loaded = load_run_safe(run_id)
                if "error" in loaded:
                    raise KeyError(loaded["error"])
                extracted_ws = _extract_field(loaded["data"], ifw.get("extract_field"))
            except KeyError as e:
                msg = f"no se pudo resolver input_from_workspace -- {e}"
                if verbose:
                    print(f"[FAIL] {step_id}: {msg}")
                results.append({"step_id": step_id, "status": "failed", "error": msg})
                break
            params = args.setdefault("params", {})
            params[ifw["maps_to_param"]] = extracted_ws

        handler = tool_registry.REGISTRY[tool_name]["handler"]
        try:
            result = handler(args)
        except Exception as e:
            msg = f"excepcion al ejecutar {tool_name} -- {e}"
            if verbose:
                print(f"[FAIL] {step_id}: {msg}")
            results.append({"step_id": step_id, "status": "failed", "error": msg})
            break

        in_memory_results[step_id] = result

        persisted = None
        run_id = step.get("persist_to_workspace")
        if run_id is not None:
            # Persistencia opcional al workspace real (npz). Solo tiene
            # sentido si 'result' es mayormente numerico -- si falla,
            # se reporta pero NO aborta el pipeline (es un extra, no el
            # paso de datos principal entre steps).
            try:
                save_info = save_run(run_id, result, meta={"tool": tool_name, "step_id": step_id})
                persisted = save_info["run_id"]
            except Exception as e:
                if verbose:
                    print(f"  (aviso: no se pudo persistir '{step_id}' al workspace: {e})")

        if verbose:
            extra = f", persistido en workspace como {persisted!r}" if persisted else ""
            print(f"[OK] {step_id}: tool={tool_name}{extra}")
        results.append({"step_id": step_id, "status": "ok", "persisted_as": persisted})

    all_ok = len(results) == len(steps) and all(r["status"] == "ok" for r in results)
    return {
        "status": "completed" if all_ok else "partial_failure",
        "results": results,
    }


def compute_run_pipeline(mode, params=None):
    """
    Handler de la tool 'run_pipeline'. mode='execute' corre el pipeline
    declarado en params['steps']. mode='validate' corre una suite minima
    de autochequeo con tools ya conocidas del repo (mismo patron que el
    resto de las tools del proyecto).
    """
    params = params or {}

    if mode == "execute":
        steps = params.get("steps", [])
        return run_pipeline(steps, verbose=False)

    elif mode == "validate":
        # Suite minima: pipeline de 1 paso con una tool cualquiera ya
        # confirmada en tool_registry.REGISTRY (earthquake_analysis_tool),
        # mas un caso de dry-check que debe fallar a proposito.
        checks = []

        ok_steps = [{
            "step_id": "s1",
            "tool": "earthquake_analysis_tool",
            "arguments": {
                "mode": "deterministic",
                "params": {"magnitude": 6.5, "distance_km": 20, "soil_class": "C"},
            },
        }]
        r1 = run_pipeline(ok_steps, verbose=False)
        checks.append({
            "name": "pipeline_de_un_paso_ejecuta_ok",
            "passed": r1["status"] == "completed",
        })

        bad_steps = [{
            "step_id": "s1",
            "tool": "tool_que_no_existe_xyz",
            "arguments": {},
        }]
        r2 = run_pipeline(bad_steps, verbose=False)
        checks.append({
            "name": "dry_check_aborta_con_tool_inexistente",
            "passed": r2["status"] == "aborted",
        })

        all_passed = all(c["passed"] for c in checks)
        return {"checks": checks, "validation_passed": all_passed}

    else:
        raise ValueError(f"Modo desconocido para run_pipeline: {mode}")


_RUN_PIPELINE_SCHEMA = {
    "name": "run_pipeline",
    "description": (
        "Orquestador de pipelines con dependencias EXPLICITAS entre tools "
        "ya registradas (sin NLP, sin inferencia automatica). mode=execute "
        "corre steps=[{step_id, tool, arguments, input_from_step?, "
        "persist_to_workspace?}], pasando resultados entre pasos por dict "
        "en memoria (input_from_step.extract_field navega el resultado del "
        "step anterior, maps_to_param define el parametro destino). Valida "
        "el pipeline completo (tools existen, referencias validas) ANTES "
        "de ejecutar nada, y aborta sin ejecutar si algo no calza. "
        "mode=validate (suite de 2 checks)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"mode": {"type": "string", "enum": ["execute", "validate"]}, "params": {"type": "object"}},
        "required": ["mode"],
    },
}

try:
    from tool_registry import register_tool
    register_tool(
        name="run_pipeline",
        schema=_RUN_PIPELINE_SCHEMA,
        handler=lambda args: compute_run_pipeline(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    # Al correr este archivo standalone (no via server.py), tool_registry.REGISTRY
    # esta vacio salvo lo que este propio modulo registra -- las demas tools se
    # registran como efecto secundario de su import (mismo patron que
    # insurance_risk_tool.py). En produccion server.py ya las importa todas
    # antes de despachar nada; para el autochequeo standalone forzamos aca el
    # import de la tool que usa la suite de validate.
    import earthquake_analysis_tool  # noqa: F401 -- fuerza su auto-registro

    d = compute_run_pipeline("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de run_pipeline (pipeline_orchestrator_tool.py) pasaron OK.")
