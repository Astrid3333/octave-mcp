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

Nota de diseno: esta tool deliberadamente NO declara mode="validate" en
su propio schema (el enum es solo ["run","summary"]). Si lo hiciera,
run_all_validations.py (o esta misma tool corriendose sobre si misma)
la detectaria como candidata a autovalidarse, y validarse a si misma
implicaria spawnear un health-check completo (que a su vez spawnea un
subprocess entero de server.py) DENTRO de otro health-check -- recursion
sin beneficio real. Por eso queda afuera del barrido automatico y se
invoca siempre a proposito.

Nota de costo: cada llamada spawnea un subprocess COMPLETO de server.py
(dos veces: uno para tools/list, otro para correr los tools/call de
validate). Con las ~60-65 tools que declaran validate hoy, tarda
~90-150s en la maquina donde se corrio la ultima vez (ver
COMPRESSION_BENCHMARK.md / logs del hook de pre-push). No pensada para
llamarse en un loop ni con alta frecuencia.
"""
import json
import os
import subprocess
import time

SERVER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")
TIMEOUT_SECONDS = 300

# Igual que en run_all_validations.py: tools que declaran "validate" en su
# enum de mode pero mode=validate significa otra cosa para ellas (no un
# autochequeo con validation_passed/all_passed). Mantener esta lista en
# sync manual con la de run_all_validations.py -- son la misma excepcion,
# vista desde dos lugares distintos (ver nota al final del archivo).
KNOWN_NON_STANDARD_VALIDATE = {
    "run_math_pipeline": "mode=validate ejecuta un pipeline default, no un autochequeo",
}

HEALTH_CHECK_TOOL_SCHEMA = {
    "name": "health_check_tool",
    "description": (
        "Corre la suite de autovalidacion de todas las tools de octave-mcp "
        "que declaran mode='validate' en su schema (mismo motor que "
        "run_all_validations.py), spawneando un subprocess fresco del "
        "servidor y hablando JSON-RPC real -- prueba exactamente lo que un "
        "cliente MCP veria. Devuelve un reporte estructurado con conteos "
        "PASSED/FAILED/ERROR/SKIPPED. mode='run' incluye el detalle "
        "completo de checks por tool; mode='summary' (default) solo los "
        "conteos y los nombres de las tools FAILED/ERROR. Tarda del orden "
        "de 1-3 minutos -- no pensada para llamarse con alta frecuencia."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["run", "summary"],
                "default": "summary",
                "description": "'run' = detalle completo de checks. 'summary' = solo conteos + nombres de tools con problemas.",
            },
        },
    },
}


def _build_requests(tools):
    requests = []
    tool_id_map = {}
    next_id = 3
    skipped = []
    for t in tools:
        name = t["name"]
        mode_prop = t.get("inputSchema", {}).get("properties", {}).get("mode", {})
        enum = mode_prop.get("enum")
        if enum is None or "validate" not in enum:
            skipped.append({"tool": name, "reason": "sin modo validate en el schema"})
            continue
        if name in KNOWN_NON_STANDARD_VALIDATE:
            skipped.append({"tool": name, "reason": KNOWN_NON_STANDARD_VALIDATE[name]})
            continue
        requests.append({
            "jsonrpc": "2.0",
            "id": next_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": {"mode": "validate", "params": {}}},
        })
        tool_id_map[next_id] = name
        next_id += 1
    return requests, tool_id_map, skipped


def _run_suite():
    bootstrap = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]

    input_data = "\n".join(json.dumps(r) for r in bootstrap) + "\n"
    try:
        proc = subprocess.run(
            ["python3", SERVER_PATH], input=input_data,
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {"status": "fatal_error", "detail": f"timeout ({TIMEOUT_SECONDS}s) obteniendo tools/list"}

    tools = None
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("id") == 2:
            tools = d.get("result", {}).get("tools")
            break

    if tools is None:
        return {
            "status": "fatal_error",
            "detail": "no se pudo obtener tools/list del subprocess",
            "stderr_tail": proc.stderr[-2000:],
        }

    call_requests, tool_id_map, skipped = _build_requests(tools)
    full_requests = bootstrap + call_requests

    t0 = time.time()
    input_data = "\n".join(json.dumps(r) for r in full_requests) + "\n"
    try:
        proc = subprocess.run(
            ["python3", SERVER_PATH], input=input_data,
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {"status": "fatal_error", "detail": f"timeout ({TIMEOUT_SECONDS}s) corriendo las validaciones"}
    elapsed = time.time() - t0

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

        # algunas tools usan "validation_passed", otras "all_passed" -- se aceptan ambos.
        vp = parsed.get("validation_passed")
        if vp is None:
            vp = parsed.get("all_passed")
        if vp is True:
            passed.append({"tool": name, "checks": parsed.get("checks")})
        elif vp is False:
            failing_checks = [
                c for c in parsed.get("checks", [])
                if isinstance(c, dict) and c.get("passed") is False
            ]
            failed.append({"tool": name, "failing_checks": failing_checks, "all_checks": parsed.get("checks")})
        else:
            errored.append({"tool": name, "reason": "respuesta valida pero sin campo 'validation_passed'"})

    return {
        "status": "ok",
        "elapsed_seconds": round(elapsed, 1),
        "total_tools_registered": len(tools),
        "with_validate_mode": len(tool_id_map),
        "overall_health": "healthy" if not failed and not errored else "degraded",
        "passed_count": len(passed),
        "failed_count": len(failed),
        "error_count": len(errored),
        "skipped_count": len(skipped),
        "passed": passed,
        "failed": failed,
        "errored": errored,
        "skipped": skipped,
    }


def compute_health_check(mode="summary", params=None):
    result = _run_suite()
    if result.get("status") != "ok" or mode == "run":
        return result
    # mode == "summary": mismo resultado sin el detalle de checks por tool
    return {
        "status": result["status"],
        "elapsed_seconds": result["elapsed_seconds"],
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


# --- auto-registro en tool_registry (ver tool_registry.py) ---
try:
    from tool_registry import register_tool
    register_tool(
        name="health_check_tool",
        schema=HEALTH_CHECK_TOOL_SCHEMA,
        handler=lambda args: compute_health_check(args.get("mode", "summary"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import sys
    mode = "run" if "--verbose" in sys.argv else "summary"
    d = compute_health_check(mode)
    print(json.dumps(d, indent=2, ensure_ascii=False))
    if d.get("status") == "ok":
        sys.exit(0 if d["overall_health"] == "healthy" else 1)
    sys.exit(2)
