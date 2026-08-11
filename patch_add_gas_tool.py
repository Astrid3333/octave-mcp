"""
Wirea gas_tool.py en server.py: import, dispatch elif, schema en TOOLS.
Backup timestamped + asserts de unicidad antes de escribir.
"""
import shutil
from datetime import datetime

SERVER = "server.py"

with open(SERVER, "r") as f:
    content = f.read()

backup_name = f"{SERVER}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
shutil.copy(SERVER, backup_name)
print(f"Backup: {backup_name}")

# 1. Import
import_marker = "from mesh_spectral_tool import compute_mesh_spectral_tool, MESH_SPECTRAL_TOOL_SCHEMA\n"
assert content.count(import_marker) == 1, "import_marker no encontrado o no unico"
content = content.replace(
    import_marker,
    import_marker + "from gas_tool import compute_gas, GAS_TOOL_SCHEMA\n",
)
print("Import de gas_tool insertado.")

# 2. Dispatch elif (insertado despues del bloque de survey_area_volume_tool, antes del else final)
dispatch_marker = (
    '            elif tool_name == "survey_area_volume_tool":\n'
    "                result = compute_survey_area_volume(**args)\n"
    "                resp = {\n"
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    "                }\n"
)
assert content.count(dispatch_marker) == 1, "dispatch_marker no encontrado o no unico"
new_elif = (
    '            elif tool_name == "gas_tool":\n'
    '                result = compute_gas(args.get("mode"), args.get("params"))\n'
    "                resp = {\n"
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    "                }\n"
)
content = content.replace(dispatch_marker, dispatch_marker + new_elif)
print("Dispatch elif de gas_tool insertado despues de survey_area_volume_tool.")

# 3. Schema en TOOLS list
schema_marker = "    SURVEY_AREA_VOLUME_TOOL_SCHEMA,\n]"
assert content.count(schema_marker) == 1, "schema_marker no encontrado o no unico"
content = content.replace(
    schema_marker,
    "    SURVEY_AREA_VOLUME_TOOL_SCHEMA,\n    GAS_TOOL_SCHEMA,\n]",
)
print("GAS_TOOL_SCHEMA agregado a la lista de schemas.")

with open(SERVER, "w") as f:
    f.write(content)

import ast
ast.parse(content)
print("server.py actualizado y validado sintacticamente.")
