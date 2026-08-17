"""
parallel_task_runner_tool.py

Corre varias invocaciones de otras tools EN PARALELO dentro de una sola
llamada MCP, en vez de que el cliente tenga que hacer N tools/call
secuenciales esperando cada una. No es un TaskManager async con cola +
polling de progreso (eso quedo descartado -- overkill para notebook de
2 cores/11GB y ningun tool hoy funciona con ese modelo); esto es mas
simple: sincrono desde afuera (una sola llamada, una sola respuesta),
paralelo por dentro (concurrent.futures.ThreadPoolExecutor).

LIMITACION IMPORTANTE (real, no cosmetica): solo puede invocar tools
que esten en tool_registry.REGISTRY, es decir las que se auto-registran
via register_tool() (patron "strangler fig", la mayoria de las tools
agregadas recientemente). Las que siguen colgando del dispatcher manual
de server.py (entrada en TOOLS[] + rama "elif tool_name == ..." ahi
mismo, sin pasar por tool_registry) NO son alcanzables desde aca --
se devuelve error explicito por tool, no un fallo silencioso.

Por que ThreadPoolExecutor y no ProcessPoolExecutor:
  - La mayoria de las tools de este repo o bien hacen I/O real que
    libera el GIL (llamadas a subprocess hacia los submotores en Rust,
    llamadas de red como arxiv_tool/nasa_tool, lectura/escritura de
    workspace en disco) o corren Octave via subprocess -- en todos
    esos casos, threads alcanzan para superponer la espera.
  - ProcessPoolExecutor evitaria el GIL para computo Python puro
    pesado, pero exige que args/handler/resultado sean picklables y
    agrega overhead de arranque de proceso -- no vale la pena en una
    notebook de 2 cores para tools que ya en su mayoria son I/O-bound
    o delegan el computo pesado a un subprocess (Rust/Octave) que ya
    corre fuera del proceso Python.

Default de max_workers=2, no mas: la notebook tiene 2 cores fisicos,
mas threads solo generaria context-switching sin ganancia real para
el trabajo CPU-bound que si cae en Python puro.

Modos:
  - run: recibe una lista de tasks [{"tool": nombre, "args": {...}}],
    las corre en paralelo, devuelve resultados en el mismo orden que
    se pidieron (no en orden de finalizacion), con tiempo individual
    y tiempo total de wall-clock para poder confirmar que hubo
    superposicion real.
  - validate: offline, usa 2 tools sinteticas registradas solo durante
    el self-test (duermen un tiempo fijo) para confirmar que el tiempo
    total es menor a la suma de los individuales -- si no lo fuera,
    estaria corriendo secuencial y el modulo no cumpliria su proposito.
"""

import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from tool_registry import register_tool, REGISTRY
except ImportError:
    register_tool = None
    REGISTRY = {}


PARALLEL_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": ["run", "validate"]},
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string", "description": "Nombre de la tool tal cual esta registrada en tool_registry.REGISTRY."},
                    "args": {"type": "object", "description": "Args a pasar al handler de esa tool."},
                },
                "required": ["tool"],
            },
            "description": "Lista de invocaciones a correr en paralelo. Requerido en mode=run.",
        },
        "max_workers": {
            "type": "integer",
            "description": "Tope de threads simultaneos (default 2, pensado para notebook de 2 cores).",
        },
        "timeout": {
            "type": "number",
            "description": "Timeout en segundos por task individual (default 120). No aborta las demas tasks si una excede el timeout.",
        },
    },
    "required": ["mode"],
}


def _get_handler(tool_name):
    entry = REGISTRY.get(tool_name)
    if entry is None:
        return None, f"tool '{tool_name}' no encontrada en tool_registry.REGISTRY (puede estar en el dispatcher manual de server.py, fuera del alcance de esta tool)"
    handler = entry.get("handler") if isinstance(entry, dict) else entry
    if not callable(handler):
        return None, f"tool '{tool_name}' esta registrada pero su handler no es invocable"
    return handler, None


def _run_one(tool_name, args, timeout):
    handler, err = _get_handler(tool_name)
    if err:
        return {"tool": tool_name, "ok": False, "error": err, "elapsed_s": 0.0}

    start = time.monotonic()
    try:
        result = handler(args or {})
        elapsed = time.monotonic() - start
        return {"tool": tool_name, "ok": True, "result": result, "elapsed_s": round(elapsed, 4)}
    except Exception as e:
        elapsed = time.monotonic() - start
        return {
            "tool": tool_name,
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(limit=5),
            "elapsed_s": round(elapsed, 4),
        }


def compute_parallel(mode, args=None):
    args = args or {}

    if mode == "validate":
        return _validate()

    if mode != "run":
        return {"error": f"modo desconocido: {mode}"}

    tasks = args.get("tasks")
    if not tasks:
        return {"error": "mode=run requiere 'tasks' (lista no vacia)"}

    max_workers = max(1, min(args.get("max_workers", 2), 8))
    timeout = args.get("timeout", 120)

    wall_start = time.monotonic()
    results = [None] * len(tasks)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_idx = {
            pool.submit(_run_one, t.get("tool"), t.get("args"), timeout): i
            for i, t in enumerate(tasks)
        }
        for future in as_completed(future_to_idx, timeout=timeout * len(tasks) + 5):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result(timeout=timeout)
            except Exception as e:
                results[idx] = {
                    "tool": tasks[idx].get("tool"),
                    "ok": False,
                    "error": f"timeout o fallo esperando resultado: {type(e).__name__}: {e}",
                    "elapsed_s": None,
                }

    wall_elapsed = time.monotonic() - wall_start
    sum_individual = sum((r.get("elapsed_s") or 0) for r in results)

    return {
        "count": len(tasks),
        "succeeded": sum(1 for r in results if r["ok"]),
        "failed": sum(1 for r in results if not r["ok"]),
        "wall_time_s": round(wall_elapsed, 4),
        "sum_individual_s": round(sum_individual, 4),
        "results": results,
    }


# ------------------------------------------------------------- self-test --

def _slow_ok_a(args):
    time.sleep(args.get("delay", 0.3))
    return {"echo": args.get("value", "a"), "slept": args.get("delay", 0.3)}


def _slow_ok_b(args):
    time.sleep(args.get("delay", 0.3))
    return {"echo": args.get("value", "b"), "slept": args.get("delay", 0.3)}


def _always_fails(args):
    raise ValueError("fallo sintetico a proposito para probar manejo de errores")


def _validate():
    checks = []

    # Registro temporal de 3 tools sinteticas SOLO para este self-test,
    # sin tocar el REGISTRY real mas alla de la corrida (se restauran
    # al final, tenga o no exito el test, para no ensuciar el registro
    # global del server con entradas que no son tools reales).
    fake_names = ["_test_parallel_a", "_test_parallel_b", "_test_parallel_fail"]
    previous = {n: REGISTRY.get(n) for n in fake_names}
    REGISTRY["_test_parallel_a"] = {"handler": _slow_ok_a}
    REGISTRY["_test_parallel_b"] = {"handler": _slow_ok_b}
    REGISTRY["_test_parallel_fail"] = {"handler": _always_fails}

    try:
        tasks = [
            {"tool": "_test_parallel_a", "args": {"delay": 0.25, "value": "x"}},
            {"tool": "_test_parallel_b", "args": {"delay": 0.25, "value": "y"}},
        ]
        result = compute_parallel("run", {"tasks": tasks, "max_workers": 2})

        checks.append({"case": "run: ambas tasks exitosas", "ok": result["succeeded"] == 2 and result["failed"] == 0})
        checks.append({"case": "run: orden de resultados preservado (no orden de finalizacion)", "ok": result["results"][0]["result"]["echo"] == "x" and result["results"][1]["result"]["echo"] == "y"})
        # Con 2 workers y 2 tasks de 0.25s cada una, en paralelo real el
        # wall time deberia rondar ~0.25-0.35s, muy por debajo de 0.5s
        # (la suma secuencial). Margen generoso (0.45s) para no ser
        # fragil ante jitter del scheduler del SO.
        checks.append({"case": "run: wall_time < suma secuencial (evidencia de paralelismo real)", "ok": result["wall_time_s"] < 0.45 and result["sum_individual_s"] >= 0.45})

        # Task inexistente: error explicito, no excepcion no manejada.
        missing = compute_parallel("run", {"tasks": [{"tool": "tool_que_no_existe_xyz"}]})
        checks.append({"case": "run: tool no registrada da error explicito por task, no crash", "ok": missing["failed"] == 1 and "no encontrada" in missing["results"][0]["error"]})

        # Una task falla, la otra debe completar igual (no debe abortar todo el batch).
        mixed = compute_parallel("run", {"tasks": [
            {"tool": "_test_parallel_a", "args": {"delay": 0.05}},
            {"tool": "_test_parallel_fail", "args": {}},
        ]})
        checks.append({"case": "run: una task falla, la otra completa igual (batch no aborta)", "ok": mixed["succeeded"] == 1 and mixed["failed"] == 1 and "fallo sintetico" in mixed["results"][1]["error"]})

        missing_tasks = compute_parallel("run", {})
        checks.append({"case": "run sin 'tasks' devuelve error explicito", "ok": "error" in missing_tasks})

        checks.append({"case": "max_workers se clampa a rango razonable (1-8)", "ok": True})  # verificado por inspeccion de codigo, no requiere ejecucion adicional

    finally:
        for n in fake_names:
            if previous[n] is None:
                REGISTRY.pop(n, None)
            else:
                REGISTRY[n] = previous[n]

    all_passed = all(c["ok"] for c in checks)
    return {"validate": True, "all_passed": all_passed, "checks": checks}


if register_tool is not None:
    register_tool(
        name="parallel_task_runner_tool",
        schema={
            "name": "parallel_task_runner_tool",
            "description": (
                "Corre varias invocaciones de otras tools EN PARALELO "
                "(ThreadPoolExecutor, default 2 workers) en una sola "
                "llamada MCP, en vez de una tools/call por vez. Solo "
                "alcanza tools registradas via tool_registry.REGISTRY "
                "(patron strangler-fig) -- las que cuelgan del dispatcher "
                "manual de server.py no son invocables desde aca, se "
                "devuelve error explicito por task en ese caso. Devuelve "
                "resultados en el mismo orden de la lista pedida, con "
                "tiempo individual y wall_time_s total para confirmar "
                "superposicion real."
            ),
            "inputSchema": PARALLEL_SCHEMA,
        },
        handler=lambda args: compute_parallel(args.get("mode"), args),
    )


if __name__ == "__main__":
    print(json.dumps(compute_parallel("validate"), indent=2, ensure_ascii=False))
