#!/usr/bin/env python3
"""
run_all_validations.py

Suite de pruebas automatica para octave-mcp. Recorre TODAS las tools
expuestas por server.py via tools/list, detecta cuales soportan modo
"validate" (inspeccionando el enum de "mode" en su inputSchema) y les
manda tools/call real con mode=validate a un unico subprocess de
server.py, igual que lo haria un cliente MCP.

No requiere que las tools sigan un patron de firma uniforme -- no se
importa ningun modulo directamente, todo pasa por el dispatch real de
server.py, asi el test cubre exactamente lo que un cliente MCP veria.

Categorias de resultado por tool:
  PASSED  - respondio con validation_passed: true
  FAILED  - respondio con validation_passed: false (o algun check individual
            en false) -- ver detalle de checks que fallaron
  ERROR   - la llamada tiro una excepcion en el servidor, o la respuesta
            no tiene el formato esperado (json invalido, sin content, etc.)
  SKIPPED - la tool no declara "validate" en el enum de su parametro mode
            (o no tiene parametro mode) -- no se la puede autovalidar asi

Uso:
    python3 run_all_validations.py
    python3 run_all_validations.py --verbose   # muestra el detalle de
                                                 # checks de cada tool, no
                                                 # solo las que fallan
Exit code: 0 si no hubo FAILED ni ERROR, 1 en caso contrario.
"""

import json
import subprocess
import sys
import time

SERVER_PATH = "server.py"
TIMEOUT_SECONDS = 180

# Tools que declaran "validate" en su enum de mode pero mode=validate
# significa otra cosa para ellas (no "correr autochequeos internos") --
# se excluyen a mano de la evaluacion automatica en vez de reportarlas
# como ERROR. Ver justificacion de cada una en el comentario.
KNOWN_NON_STANDARD_VALIDATE = {
    # mode=validate ejecuta un pipeline default de pasos (compute_gradient_hessian
    # + compute_math_error_analysis encadenados) y devuelve su trace/resultados,
    # no un reporte de autochequeo con validation_passed/all_passed.
    "run_math_pipeline": "mode=validate ejecuta un pipeline default, no un autochequeo",
}


def build_requests(tools):
    """Devuelve (requests, tool_id_map) donde requests es la lista completa
    a mandarle al subprocess (initialize + tools/list + un tools/call por
    cada tool candidata), y tool_id_map mapea id -> nombre de tool para
    las llamadas de validate."""
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    tool_id_map = {}
    next_id = 3
    skipped = []

    for t in tools:
        name = t["name"]
        mode_prop = t.get("inputSchema", {}).get("properties", {}).get("mode", {})
        enum = mode_prop.get("enum")
        if enum is None or "validate" not in enum:
            skipped.append((name, "sin modo validate en el schema"))
            continue
        if name in KNOWN_NON_STANDARD_VALIDATE:
            skipped.append((name, KNOWN_NON_STANDARD_VALIDATE[name]))
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


def main():
    verbose = "--verbose" in sys.argv

    print("Consultando tools/list en server.py ...")
    bootstrap = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    input_data = "\n".join(json.dumps(r) for r in bootstrap) + "\n"
    proc = subprocess.run(
        ["python3", SERVER_PATH], input=input_data,
        capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
    )
    tools = None
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("id") == 2:
            tools = d["result"]["tools"]
            break

    if tools is None:
        print("ERROR FATAL: no se pudo obtener tools/list.")
        print("STDERR:", proc.stderr[-3000:])
        sys.exit(1)

    print(f"Total de tools registradas: {len(tools)}\n")

    requests, tool_id_map, skipped = build_requests(tools)
    print(f"Tools con modo 'validate' detectado: {len(tool_id_map)}")
    print(f"Tools sin modo 'validate' (SKIPPED): {len(skipped)}\n")

    print("Ejecutando validaciones (un solo subprocess, puede tardar)...")
    t0 = time.time()
    input_data = "\n".join(json.dumps(r) for r in requests) + "\n"
    proc = subprocess.run(
        ["python3", SERVER_PATH], input=input_data,
        capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
    )
    elapsed = time.time() - t0
    print(f"Listo en {elapsed:.1f}s.\n")

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
            errored.append((name, "sin respuesta del servidor (timeout o crash)"))
            continue
        if "error" in resp:
            errored.append((name, f"JSON-RPC error: {resp['error']}"))
            continue
        try:
            text = resp["result"]["content"][0]["text"]
            parsed = json.loads(text)
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            errored.append((name, f"formato de respuesta inesperado: {e}"))
            continue

        # algunas tools usan "validation_passed", otras usan "all_passed"
        # para el mismo concepto -- se aceptan ambos nombres de campo.
        vp = parsed.get("validation_passed")
        if vp is None:
            vp = parsed.get("all_passed")
        if vp is True:
            passed.append((name, parsed.get("checks")))
        elif vp is False:
            failing_checks = [
                c for c in parsed.get("checks", [])
                if isinstance(c, dict) and c.get("passed") is False
            ]
            failed.append((name, failing_checks, parsed.get("checks")))
        else:
            errored.append((name, "respuesta valida pero sin campo 'validation_passed'"))

    total = len(tool_id_map)
    print("=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(f"  Total tools registradas:        {len(tools)}")
    print(f"  Con modo validate (evaluadas):  {total}")
    print(f"  PASSED:                         {len(passed)}")
    print(f"  FAILED:                         {len(failed)}")
    print(f"  ERROR:                          {len(errored)}")
    print(f"  SKIPPED (sin modo validate):    {len(skipped)}")
    print("=" * 70)

    if failed:
        print("\n--- TOOLS CON VALIDACION FALLIDA ---")
        for name, failing_checks, all_checks in failed:
            print(f"\n  [FAILED] {name}")
            for c in failing_checks:
                print(f"      - check fallido: {json.dumps(c, ensure_ascii=False)}")

    if errored:
        print("\n--- TOOLS CON ERROR ---")
        for name, msg in errored:
            print(f"\n  [ERROR] {name}")
            print(f"      {msg}")

    if verbose:
        print("\n--- DETALLE COMPLETO DE TOOLS PASSED ---")
        for name, checks in passed:
            n_checks = len(checks) if checks else 0
            print(f"  [PASSED] {name}  ({n_checks} checks)")

    if skipped:
        print(f"\n--- TOOLS SKIPPED ({len(skipped)}) ---")
        if verbose:
            for name, reason in sorted(skipped):
                print(f"  [SKIPPED] {name}  -- {reason}")
        else:
            print("  (usar --verbose para ver la lista completa con motivos)")

    print()
    if failed or errored:
        print(f"RESULTADO FINAL: {len(failed)} fallidas, {len(errored)} con error. Revisar arriba.")
        sys.exit(1)
    else:
        print("RESULTADO FINAL: todas las tools con modo validate pasaron OK.")
        sys.exit(0)


if __name__ == "__main__":
    main()
