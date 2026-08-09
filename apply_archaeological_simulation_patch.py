"""
apply_archaeological_simulation_patch.py

1) Limpia la duplicacion de econometrics_tool (import, schema, dispatcher)
   causada por haber corrido apply_econometrics_patch.py dos veces.
2) Aplica el patch de archaeological_simulation_tool (import, schema,
   dispatcher), siguiendo el mismo esquema de las 3 inserciones.

Backup automatico en server.py.bak_archaeological_simulation antes de tocar nada.
"""
import shutil

path = "server.py"
shutil.copy(path, "server.py.bak_archaeological_simulation")

with open(path, "r") as f:
    content = f.read()

# --- 0) Limpieza de duplicados de econometrics_tool ---

dup_import = (
    'from econometrics_tool import compute_econometrics, ECONOMETRICS_TOOL_SCHEMA\n'
    'from econometrics_tool import compute_econometrics, ECONOMETRICS_TOOL_SCHEMA\n'
)
single_import = 'from econometrics_tool import compute_econometrics, ECONOMETRICS_TOOL_SCHEMA\n'
if content.count(dup_import) == 1:
    content = content.replace(dup_import, single_import, 1)
    print("Limpiado: import duplicado de econometrics_tool.")
else:
    print("Aviso: no se encontro el import duplicado tal cual (puede que ya este limpio).")

dup_schema = (
    '    ECONOMETRICS_TOOL_SCHEMA,\n'
    '    ECONOMETRICS_TOOL_SCHEMA,\n'
)
single_schema = '    ECONOMETRICS_TOOL_SCHEMA,\n'
if content.count(dup_schema) == 1:
    content = content.replace(dup_schema, single_schema, 1)
    print("Limpiado: schema duplicado de ECONOMETRICS_TOOL_SCHEMA.")
else:
    print("Aviso: no se encontro el schema duplicado tal cual (puede que ya este limpio).")

dup_branch = '''            elif tool_name == "econometrics_tool":
                result = compute_econometrics(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }
            elif tool_name == "econometrics_tool":
                result = compute_econometrics(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }
'''
single_branch = '''            elif tool_name == "econometrics_tool":
                result = compute_econometrics(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }
'''
if content.count(dup_branch) == 1:
    content = content.replace(dup_branch, single_branch, 1)
    print("Limpiado: branch duplicado del dispatcher para econometrics_tool.")
else:
    print("Aviso: no se encontro el branch duplicado tal cual (puede que ya este limpio).")

# --- 1) Insertar import, despues del import de econometrics_tool (ya limpio) ---
marker_import = 'from econometrics_tool import compute_econometrics, ECONOMETRICS_TOOL_SCHEMA\n'
new_import = marker_import + 'from archaeological_simulation_tool import compute_archaeological_simulation, ARCHAEOLOGICAL_SIMULATION_TOOL_SCHEMA\n'
assert content.count(marker_import) == 1, f"marker_import aparece {content.count(marker_import)} veces, esperado 1"
content = content.replace(marker_import, new_import, 1)

# --- 2) Insertar el schema en la lista, despues de ECONOMETRICS_TOOL_SCHEMA ---
marker_schema = '    ECONOMETRICS_TOOL_SCHEMA,\n'
new_schema = marker_schema + '    ARCHAEOLOGICAL_SIMULATION_TOOL_SCHEMA,\n'
assert content.count(marker_schema) == 1, f"marker_schema aparece {content.count(marker_schema)} veces, esperado 1"
content = content.replace(marker_schema, new_schema, 1)

# --- 3) Insertar el branch del dispatcher, despues del bloque de econometrics_tool ---
marker_branch = '''            elif tool_name == "econometrics_tool":
                result = compute_econometrics(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }
'''
new_branch = marker_branch + '''            elif tool_name == "archaeological_simulation":
                result = compute_archaeological_simulation(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }
'''
assert content.count(marker_branch) == 1, f"marker_branch aparece {content.count(marker_branch)} veces, esperado 1"
content = content.replace(marker_branch, new_branch, 1)

with open(path, "w") as f:
    f.write(content)

print("OK: limpieza de duplicados + 3 inserciones de archaeological_simulation aplicadas.")
print("Backup guardado en server.py.bak_archaeological_simulation")
print("Verificar con: python3 -c \"import ast; ast.parse(open('server.py').read()); print('sintaxis OK')\"")
