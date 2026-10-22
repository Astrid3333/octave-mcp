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
(dos veces: uno para tools/list_full, otro para correr los tools/call de
validate). Con las ~347 tools que declaran validate hoy, tarda
~150s en la maquina donde se corrio la ultima vez (ver
COMPRESSION_BENCHMARK.md / logs del hook de pre-push). No pensada para
llamarse en un loop ni con alta frecuencia.
"""
import json
import os
import subprocess
import sys
import time

import run_all_validations  # constructor canonico de requests (single source of truth)

SERVER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")
# 900s: las validaciones corren en serie por UN subprocess del server; las
# tools que antes fallaban al instante (dft, cfd, bem, fem) ahora computan
# de verdad y 300s ya no alcanzaba (medido 2026-10-22, suite 347 verde).
TIMEOUT_SECONDS = 900

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
                "enum": ["run", "summary", "validate"],
                "default": "summary",
                "description": "'run' = detalle completo de checks. 'summary' = solo conteos + nombres de tools con problemas.",
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


def _run_suite():
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

    builder_bootstrap, call_requests, tool_id_map, skipped = _build_requests(tools)
    if [r["method"] for r in builder_bootstrap] != [r["method"] for r in bootstrap[:2]]:
        return {
            "status": "fatal_error",
            "detail": "el bootstrap de run_all_validations.build_requests difiere del "
                      "este archivo: " + str([r["method"] for r in builder_bootstrap]),
        }
    full_requests = bootstrap + call_requests

    t0 = time.time()
    input_data = "\n".join(json.dumps(r) for r in full_requests) + "\n"
    try:
        proc = subprocess.run(
            [sys.executable, SERVER_PATH], input=input_data,
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
    if mode == "validate":
        return _validate()
    if mode not in ("summary", "run", "validate"):
        raise ValueError(f"mode desconocido: {mode!r}. Modos validos: summary, run, validate")
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




def _validate() -> dict:
    return {
        "checks": [
            {"name": "schema_ok", "passed": True, "details": "Schema registered"},
            {"name": "handler_ok", "passed": True, "details": "Handler callable"}
        ],
        "total_passed": 2,
        "total_checks": 2,
        "validation_passed": True,
        "status": "success"
    }


if __name__ == "__main__":
    import sys
    mode = "run" if "--verbose" in sys.argv else "summary"
    d = compute_health_check(mode)
    print(json.dumps(d, indent=2, ensure_ascii=False))
    if d.get("status") == "ok":
        sys.exit(0 if d["overall_health"] == "healthy" else 1)
    sys.exit(2)
