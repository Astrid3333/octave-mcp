"""
health_check_tool.py

Formaliza run_all_validations.py como un tool MCP invocable -- "dogfooding":
el propio servidor puede reportar su salud sin salir a una terminal ni
depender del hook de pre-push. Reusa exactamente la misma logica y el
mismo approach que run_all_validations.py (habla JSON-RPC con un
subprocess FRESCO de server.py), asi prueba lo mismo que veria un cliente
MCP real -- no importa si la tool destino esta en tool_registry.REGISTRY
o todavia en la cadena elif legacy, ambas se prueban por igual.

Se auto-registra via tool_registry (ver tool_registry.py) -- no requiere
tocar la cadena elif de server.py, solo UNA linea de import.

Modos:
  - run     : suite completa, con el detalle de checks de cada tool
              (PASSED/FAILED/ERROR/SKIPPED), igual que
              run_all_validations.py --verbose.
  - summary : mismos conteos, pero solo los NOMBRES de las tools
              FAILED/ERROR (sin el detalle de checks) -- pensado para
              lectura rapida.

Subconjunto (subset): parametro opcional con lista de nombres de tool.
Si viene no vacio, SOLO se validan esas (mismo motor, mismo reporte) y
los conteos son sobre el subconjunto -- pensado para barrer lotes de
tools sin correr la suite completa ni inundar la conversacion con
detalle (cada tool reportada solo como nombre + conteo). Los nombres
inexistentes se devuelven en 'unknown_tools'; si ninguno coincide,
overall_health='no_tools' (nunca 'healthy' con 0 tools validadas).

Nota de diseno: el enum de mode incluye "validate", pero ese modo NO
corre la suite -- llama a _validate(), un autochequeo trivial (schema
del subset, filtro puro y guard de tipo; ningun subprocess). Asi
run_all_validations.py puede incluirla en el
barrido (373/373) sin recursion: validarla a si misma no spawnea otro
health-check. La suite completa solo corre en mode="run"/"summary",
que se invocan siempre a proposito.

Nota de costo: cada llamada spawnea un subprocess de server.py para
tools/list_full + tools/list_deprecated, y despues corre los tools/call
de validate repartidos en PARALLEL_WORKERS subprocessos de server.py en
paralelo (mismo motor que run_all_validations.py: 148s con 4 workers con
la maquina despejada, 235s con load 15; ~5.5 min en serie -- medido
2026-10-25). Con la suite en serie el cliente MCP tipico cancelaba a los
4 min (y 6 workers empeora: 291s por oversubscription).
PARALLEL_WORKERS=1 recupera el camino secuencial (para comparar). No
pensada para llamarse en un loop ni con alta frecuencia.
"""
import json
import os
import subprocess
import sys
import time

import run_all_validations  # constructor canonico de requests (single source of truth)

SERVER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")
# 900s por subprocess (bootstrap o chunk de validate): las tools que antes
# fallaban al instante (dft, cfd, bem, fem) ahora computan de verdad y
# 300s no alcanzaba (medido 2026-10-22, suite 347 verde).
TIMEOUT_SECONDS = 900

# run_all_validations.SERVER_PATH es relativo ("server.py", pensado para
# correr desde el repo); health_check puede arrancar con cualquier CWD
# (cliente MCP), asi que se fija la ruta absoluta antes de reusar
# run_validations_parallel() (usa SERVER_PATH dentro de _run_chunk).
run_all_validations.SERVER_PATH = SERVER_PATH

HEALTH_CHECK_TOOL_SCHEMA = {
    "name": "health_check_tool",
    "description": (
        "Corre la suite de autovalidacion de las tools de octave-mcp "
        "que declaran mode='validate' en su schema (mismo motor que "
        "run_all_validations.py), spawneando un subprocess fresco del "
        "servidor y hablando JSON-RPC real -- prueba exactamente lo que un "
        "cliente MCP veria. Devuelve un reporte estructurado con conteos "
        "PASSED/FAILED/ERROR/SKIPPED. mode='run' incluye el detalle "
        "completo de checks por tool; mode='summary' (default) solo los "
        "conteos y los nombres de las tools FAILED/ERROR. Con el "
        "parametro 'subset' valida SOLO las tools nombradas (conteos "
        "compactos de un lote, sin correr la suite completa). Corre los "
        "tools/call en paralelo (PARALLEL_WORKERS subprocessos, default 4): "
        "suite completa ~2-3 minutos; un subset, segundos -- no pensada "
        "para llamarse con alta frecuencia."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["run", "summary", "validate"],
                "default": "summary",
                "description": "'run' = detalle completo de checks. 'summary' = solo conteos + nombres de tools con problemas.",
            },
            "subset": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Lista OPCIONAL de nombres de tool: si viene no vacia, "
                    "SOLO se validan esas y los conteos son sobre el "
                    "subconjunto (reporte compacto de un lote). Nombres "
                    "inexistentes van en 'unknown_tools'; si ninguno "
                    "coincide, overall_health='no_tools'. Sin este campo "
                    "(o vacio) = suite completa."
                ),
            },
        },
    },
}


def _build_requests(tools):
    """Delega en run_all_validations.build_requests: ese es el constructor
    canonico (ALTERNATE_VALIDATE_MODE, ALTERNATE_VALIDATE_PARAM_NAME,
    FLAT_SIGNATURE_TOOLS, KNOWN_NON_STANDARD_VALIDATE). Una copia local de
    ahi mismo hacia este check enviar payloads distintos a los de la suite
    oficial y reportaba tools en ERROR que la suite oficial aprueba.

    build_requests ya incluye initialize + tools/list_full; se recortan para
    que _run_suite pueda prepender su propio bootstrap."""
    all_requests, tool_id_map, skipped = run_all_validations.build_requests(tools)
    bootstrap = all_requests[:2]
    requests = all_requests[2:]
    skipped = [{"tool": name, "reason": reason} for name, reason in skipped]
    return bootstrap, requests, tool_id_map, skipped


def _apply_subset(tools, wanted):
    """Filtra 'tools' por los nombres de 'wanted' preservando el orden
    pedido y sin duplicados. Devuelve (seleccionadas, desconocidas).

    Pura (sin subprocess): _validate() la autochequea con datos falsos."""
    by_name = {t.get("name"): t for t in tools}
    seen = set()
    selected, unknown = [], []
    for name in wanted:
        if name in seen:
            continue
        seen.add(name)
        if name in by_name:
            selected.append(by_name[name])
        else:
            unknown.append(name)
    return selected, unknown


def _run_suite(tools_filter=None):
    # tools/list solo devuelve las 3 meta-tools (list_tools/get_tool_schema/
    # call_tool); el catalogo completo esta en tools/list_full. Usar
    # tools/list hacia el check reportar "healthy" validando 0 tools.
    bootstrap = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list_full", "params": {}},
        # id fuera del rango de tools/call (arrancan en 3): sin esto la
        # respuesta de list_deprecated pisaria en responses[] a la primera tool.
        {"jsonrpc": "2.0", "id": 900001, "method": "tools/list_deprecated", "params": {}},
    ]

    input_data = "\n".join(json.dumps(r) for r in bootstrap) + "\n"
    try:
        proc = subprocess.run(
            [sys.executable, SERVER_PATH], input=input_data,
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {"status": "fatal_error", "detail": f"timeout ({TIMEOUT_SECONDS}s) obteniendo tools/list_full"}

    tools = None
    deprecated = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("id") == 2:
            tools = d.get("result", {}).get("tools")
        elif d.get("id") == 900001:
            # alias de merges de catalogo: siguen siendo invocables, el harness
            # de run_all_validations.py las valida igual (365 = 362 + 3).
            deprecated = d.get("result", {}).get("tools", []) or []

    if tools is None:
        return {
            "status": "fatal_error",
            "detail": "no se pudo obtener tools/list_full del subprocess",
            "stderr_tail": proc.stderr[-2000:],
        }
    if deprecated:
        seen = {t.get("name") for t in tools}
        tools = list(tools) + [t for t in deprecated if t.get("name") not in seen]
    registered_total = len(tools)

    # subset: filtrar ANTES de construir requests (los conteos y el
    # tool_id_map son solo de las tools pedidas). Sin subset o vacio =
    # suite completa, igual que siempre.
    unknown_tools = []
    subset_used = bool(tools_filter)
    if subset_used:
        tools, unknown_tools = _apply_subset(tools, tools_filter)
        if not tools:
            # ningun nombre coincide: NO correr nada y NO reportar
            # 'healthy' validando 0 tools.
            return {
                "status": "ok",
                "filter": "subset",
                "requested_count": len(unknown_tools),
                "unknown_tools": unknown_tools,
                "elapsed_seconds": 0.0,
                "parallel_workers": 0,
                "stderr_chunk_count": 0,
                "total_tools_registered": registered_total,
                "with_validate_mode": 0,
                "overall_health": "no_tools",
                "passed_count": 0,
                "failed_count": 0,
                "error_count": 0,
                "skipped_count": 0,
                "passed": [],
                "failed": [],
                "errored": [],
                "skipped": [],
            }

    builder_bootstrap, call_requests, tool_id_map, skipped = _build_requests(tools)
    if [r["method"] for r in builder_bootstrap] != [r["method"] for r in bootstrap[:2]]:
        return {
            "status": "fatal_error",
            "detail": "el bootstrap de run_all_validations.build_requests difiere del "
                      "este archivo: " + str([r["method"] for r in builder_bootstrap]),
        }

    workers = run_all_validations.PARALLEL_WORKERS
    stderr_chunk_count = 0
    stderr_tails = []
    t0 = time.time()
    if workers <= 1:
        # camino secuencial de siempre: UN subprocess con todos los tools/call
        full_requests = bootstrap + call_requests
        input_data = "\n".join(json.dumps(r) for r in full_requests) + "\n"
        try:
            proc = subprocess.run(
                [sys.executable, SERVER_PATH], input=input_data,
                capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return {"status": "fatal_error", "detail": f"timeout ({TIMEOUT_SECONDS}s) corriendo las validaciones"}
        elapsed = time.time() - t0
        if proc.stderr.strip():
            stderr_chunk_count = 1
            stderr_tails = [proc.stderr[-400:]]

        responses = {}
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = d.get("id")
            if rid in tool_id_map:
                responses[rid] = d
    else:
        # paralelo: n chunks con ids offseteados, cada uno su subprocess de
        # server.py (mismo motor que run_all_validations.py). Reemplaza el
        # tool_id_map/skipped del camino secuencial (los ids difieren).
        tool_id_map, skipped_pairs, responses, elapsed, stderrs = (
            run_all_validations.run_validations_parallel(tools, workers)
        )
        skipped = [{"tool": name, "reason": reason} for name, reason in skipped_pairs]
        stderr_chunk_count = len(stderrs)
        stderr_tails = [e[:400] for e in stderrs]

    passed, failed, errored = [], [], []
    for rid, name in tool_id_map.items():
        resp = responses.get(rid)
        if resp is None:
            errored.append({"tool": name, "reason": "sin respuesta del servidor (timeout o crash)"})
            continue
        if "error" in resp:
            errored.append({"tool": name, "reason": f"JSON-RPC error: {resp['error']}"})
            continue
        try:
            text = resp["result"]["content"][0]["text"]
            parsed = json.loads(text)
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            errored.append({"tool": name, "reason": f"formato de respuesta inesperado: {e}"})
            continue

        # mismo criterio que run_all_validations.main(): varios nombres de
        # campo cuentan como veredicto (VALIDATION_FIELD_ALIASES). Mirar solo
        # validation_passed/all_passed marcaba en ERROR tools que la suite
        # oficial aprueba (all_pass, ok, todos_correctos, ...).
        if not isinstance(parsed, dict):
            errored.append({"tool": name, "reason": f"validate no estructurado (devolvio {type(parsed).__name__}, no dict)"})
            continue

        vp = None
        for _field in run_all_validations.VALIDATION_FIELD_ALIASES:
            if _field in parsed:
                vp = parsed.get(_field)
                break
        if vp is True:
            passed.append({"tool": name, "checks": parsed.get("checks")})
        elif vp is False:
            failing_checks = [
                c for c in parsed.get("checks", [])
                if isinstance(c, dict) and c.get("passed") is False
            ]
            failed.append({"tool": name, "failing_checks": failing_checks, "all_checks": parsed.get("checks")})
        else:
            errored.append({"tool": name, "reason": f"respuesta valida pero sin campo de veredicto (probado: {', '.join(run_all_validations.VALIDATION_FIELD_ALIASES)})"})

    # 'healthy' exige al menos UN tool con validate_mode evaluado:
    # reportar salud con 0 validadas es el mismo engano que el caso
    # tools/list documentado arriba.
    if not tool_id_map:
        overall = "no_tools"
    else:
        overall = "healthy" if not failed and not errored else "degraded"

    result = {
        "status": "ok",
        "elapsed_seconds": round(elapsed, 1),
        "parallel_workers": workers,
        "stderr_chunk_count": stderr_chunk_count,
        # solo visible en mode="run": el summary usa una lista blanca de campos
        "stderr_chunks_tail": stderr_tails,
        "total_tools_registered": registered_total,
        "with_validate_mode": len(tool_id_map),
        "overall_health": overall,
        "passed_count": len(passed),
        "failed_count": len(failed),
        "error_count": len(errored),
        "skipped_count": len(skipped),
        "passed": passed,
        "failed": failed,
        "errored": errored,
        "skipped": skipped,
    }
    if subset_used:
        result["filter"] = "subset"
        result["requested_count"] = len(tools) + len(unknown_tools)
        result["unknown_tools"] = unknown_tools
    return result


def compute_health_check(mode="summary", params=None, subset=None):
    if mode == "validate":
        return _validate()
    if mode not in ("summary", "run", "validate"):
        raise ValueError(f"mode desconocido: {mode!r}. Modos validos: summary, run, validate")
    if subset is not None and not isinstance(subset, list):
        raise ValueError(f"subset debe ser una lista de nombres de tool, no {type(subset).__name__}")
    result = _run_suite(tools_filter=subset)
    if result.get("status") != "ok" or mode == "run":
        return result
    # mode == "summary": mismo resultado sin el detalle de checks por tool
    out = {
        "status": result["status"],
        "elapsed_seconds": result["elapsed_seconds"],
        "parallel_workers": result.get("parallel_workers"),
        "stderr_chunk_count": result.get("stderr_chunk_count"),
        "total_tools_registered": result["total_tools_registered"],
        "with_validate_mode": result["with_validate_mode"],
        "overall_health": result["overall_health"],
        "passed_count": result["passed_count"],
        "failed_count": result["failed_count"],
        "error_count": result["error_count"],
        "skipped_count": result["skipped_count"],
        "failed_tools": [f["tool"] for f in result["failed"]],
        "errored_tools": [e["tool"] for e in result["errored"]],
    }
    if "filter" in result:
        out["filter"] = result["filter"]
        out["requested_count"] = result["requested_count"]
        out["unknown_tools"] = result["unknown_tools"]
    return out


# --- auto-registro en tool_registry (ver tool_registry.py) ---
try:
    from tool_registry import register_tool
    register_tool(
        name="health_check_tool",
        schema=HEALTH_CHECK_TOOL_SCHEMA,
        handler=lambda args: compute_health_check(
            args.get("mode", "summary"), args.get("params"), args.get("subset")
        ),
    )
except ImportError:
    pass




def _validate() -> dict:
    checks = []

    # 1) el schema expone el param subset
    props = HEALTH_CHECK_TOOL_SCHEMA.get("inputSchema", {}).get("properties", {})
    ok = "subset" in props and props.get("subset", {}).get("type") == "array"
    checks.append({
        "name": "schema_has_subset_param",
        "passed": ok,
        "details": "properties=%s" % sorted(props) if ok else f"properties={sorted(props)} (falta subset)",
    })

    # 2) _apply_subset: orden pedido, dedupe y desconocidas (puro)
    fake = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
    sel, unk = _apply_subset(fake, ["b", "x", "b", "y"])
    ok = [t["name"] for t in sel] == ["b"] and unk == ["x", "y"]
    checks.append({
        "name": "apply_subset_filter",
        "passed": ok,
        "details": f"selected={[t['name'] for t in sel]} unknown={unk}",
    })

    # 3) subset no-lista se rechaza ANTES de spawneear nada
    try:
        compute_health_check(mode="summary", subset="not-a-list")
        ok, detail = False, "no lanzo ValueError"
    except ValueError as exc:
        ok, detail = True, f"ValueError: {exc}"
    checks.append({"name": "subset_type_guard", "passed": ok, "details": detail})

    passed = [c["name"] for c in checks if c["passed"]]
    return {
        "checks": checks,
        "total_passed": len(passed),
        "total_checks": len(checks),
        "validation_passed": len(passed) == len(checks),
        "status": "success" if len(passed) == len(checks) else "failed",
    }


if __name__ == "__main__":
    import sys
    mode = "run" if "--verbose" in sys.argv else "summary"
    subset = None
    for arg in sys.argv[1:]:
        if arg.startswith("--subset="):
            subset = [s for s in arg.split("=", 1)[1].split(",") if s]
    d = compute_health_check(mode, subset=subset)
    print(json.dumps(d, indent=2, ensure_ascii=False))
    if d.get("status") == "ok":
        sys.exit(0 if d["overall_health"] == "healthy" else 1)
    sys.exit(2)
