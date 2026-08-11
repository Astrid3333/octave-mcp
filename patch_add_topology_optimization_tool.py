#!/usr/bin/env python3
"""
Wirea topology_optimization_tool en octave-mcp/server.py en los 3 puntos
de siempre (import, dispatch, schema list), anclado por texto exacto
-- no por numero de linea -- para no repetir el problema de desfasaje
que rompio el wireo de circuit_tool.

Uso (dentro de ~/octave-mcp/):
    python3 patch_add_topology_optimization_tool.py
"""

import ast
import shutil
import time

SERVER_PATH = "server.py"

with open(SERVER_PATH, "r") as f:
    content = f.read()

ast.parse(content)  # confirma que partimos de un archivo valido

changes_made = []

# 1. Import: insertado justo despues del import de circuit_tool.
old_import = "from circuit_tool import compute_circuit_tool, CIRCUIT_TOOL_SCHEMA\n"
new_import = (
    old_import
    + "from topology_optimization_tool import compute_topology_optimization_tool, TOPOLOGY_OPTIMIZATION_TOOL_SCHEMA\n"
)
count = content.count(old_import)
if count != 1:
    print(f"ABORTADO en paso 1 (import): encontre {count} ocurrencias de la linea de import de circuit_tool (esperaba 1). No se toco nada.")
    raise SystemExit(1)
content = content.replace(old_import, new_import, 1)
changes_made.append("Import de topology_optimization_tool insertado.")

# 2. Dispatch: se inserta la rama nueva ENTRE el bloque completo de
#    circuit_tool y el inicio de geometric_algebra_protein.
old_dispatch = '''            elif tool_name == "circuit_tool":
                result = compute_circuit_tool(args.get("mode", "validate"), args.get("params"))
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }
            elif tool_name == "geometric_algebra_protein":'''

new_dispatch = '''            elif tool_name == "circuit_tool":
                result = compute_circuit_tool(args.get("mode", "validate"), args.get("params"))
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }
            elif tool_name == "topology_optimization_tool":
                result = compute_topology_optimization_tool(args.get("mode", "validate"), args.get("params"))
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }
            elif tool_name == "geometric_algebra_protein":'''

count = content.count(old_dispatch)
if count != 1:
    print(f"ABORTADO en paso 2 (dispatch): encontre {count} ocurrencias del bloque circuit_tool->geometric_algebra_protein (esperaba 1). No se toco nada (el import del paso 1 tampoco se escribio a disco).")
    raise SystemExit(1)
content = content.replace(old_dispatch, new_dispatch, 1)
changes_made.append("Dispatch elif de topology_optimization_tool insertado antes de geometric_algebra_protein.")

# 3. Schema list: agregado justo despues de CIRCUIT_TOOL_SCHEMA,
old_schema_line = "    CIRCUIT_TOOL_SCHEMA,\n"
new_schema_line = old_schema_line + "    TOPOLOGY_OPTIMIZATION_TOOL_SCHEMA,\n"
count = content.count(old_schema_line)
if count != 1:
    print(f"ABORTADO en paso 3 (schema): encontre {count} ocurrencias de 'CIRCUIT_TOOL_SCHEMA,' (esperaba 1). No se escribio nada a disco.")
    raise SystemExit(1)
content = content.replace(old_schema_line, new_schema_line, 1)
changes_made.append("TOPOLOGY_OPTIMIZATION_TOOL_SCHEMA agregado a la lista de schemas.")

# Validar sintaxis ANTES de escribir a disco.
ast.parse(content)

timestamp = time.strftime("%Y%m%d_%H%M%S")
backup_path = f"{SERVER_PATH}.bak_{timestamp}"
shutil.copy(SERVER_PATH, backup_path)
print(f"Backup: {backup_path}")

with open(SERVER_PATH, "w") as f:
    f.write(content)

for msg in changes_made:
    print(msg)
print("server.py actualizado y validado sintacticamente.")
