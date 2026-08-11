#!/usr/bin/env python3
"""
Repara el bloque de dispatch de circuit_tool que quedo insertado en medio
de la rama de polarization_mapping (cortandola a la mitad), y lo vuelve a
poner como una rama elif propia, completa, antes de geometric_algebra_protein.

Uso (dentro de ~/octave-mcp/):
    python3 fix_circuit_tool_dispatch.py
"""

import ast
import shutil
import time

SERVER_PATH = "server.py"

with open(SERVER_PATH, "r") as f:
    content = f.read()

broken = '''            elif tool_name == "polarization_mapping":
            elif tool_name == "circuit_tool":
                result = compute_circuit_tool(args.get("mode", "validate"), args.get("params"))
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }
                result = compute_polarization_mapping(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }
            elif tool_name == "geometric_algebra_protein":'''

fixed = '''            elif tool_name == "polarization_mapping":
                result = compute_polarization_mapping(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }
            elif tool_name == "circuit_tool":
                result = compute_circuit_tool(args.get("mode", "validate"), args.get("params"))
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }
            elif tool_name == "geometric_algebra_protein":'''

count = content.count(broken)
if count == 0:
    print("ABORTADO: no encontre el bloque roto exacto. No se toco nada.")
    print("Pegame 'sed -n \"1000,1020p\" server.py' actualizado y ajusto el patron.")
    raise SystemExit(1)
if count > 1:
    print(f"ABORTADO: el patron roto aparece {count} veces (deberia ser 1). No se toco nada.")
    raise SystemExit(1)

timestamp = time.strftime("%Y%m%d_%H%M%S")
backup_path = f"{SERVER_PATH}.bak_{timestamp}"
shutil.copy(SERVER_PATH, backup_path)
print(f"Backup: {backup_path}")

new_content = content.replace(broken, fixed)

ast.parse(new_content)  # valida sintaxis ANTES de escribir

with open(SERVER_PATH, "w") as f:
    f.write(new_content)

print("Bloque de circuit_tool separado de polarization_mapping y reordenado.")
print("server.py actualizado y validado sintacticamente.")
