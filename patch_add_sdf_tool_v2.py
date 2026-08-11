#!/usr/bin/env python3
"""
Patch v2: agrega sdf_tool a octave-mcp/server.py
Anchors confirmados contra el server.py real (grep/sed previos).

Uso (dentro de ~/octave-mcp/):
    python3 patch_add_sdf_tool_v2.py
"""

import ast
import shutil
import time

SERVER_PATH = "server.py"

with open(SERVER_PATH, "r") as f:
    content = f.read()

ast.parse(content)  # server.py debe estar sano antes de tocarlo

timestamp = time.strftime("%Y%m%d_%H%M%S")
backup_path = f"{SERVER_PATH}.bak_{timestamp}"
shutil.copy(SERVER_PATH, backup_path)
print(f"Backup: {backup_path}")

# ---------------------------------------------------------------------------
# 1. Import
# ---------------------------------------------------------------------------

import_marker = "from distmesh_tool import compute_distmesh, DISTMESH_TOOL_SCHEMA"
assert content.count(import_marker) == 1, "import_marker no encontrado exactamente 1 vez"

sdf_import = "\nfrom sdf_tool import compute_sdf_tool, SDF_TOOL_SCHEMA"
if "from sdf_tool import" not in content:
    content = content.replace(import_marker, import_marker + sdf_import, 1)
    print("Import de sdf_tool insertado.")
else:
    print("Import de sdf_tool ya presente, no se duplica.")

# ---------------------------------------------------------------------------
# 2. Dispatch elif — se inserta ANTES del bloque de distmesh_tool,
#    mismo formato de resp que ese bloque.
# ---------------------------------------------------------------------------

dispatch_marker = (
    '            elif tool_name == "distmesh_tool":\n'
    '                result = compute_distmesh(**args)\n'
)
assert content.count(dispatch_marker) == 1, "dispatch_marker no encontrado exactamente 1 vez"

sdf_dispatch_block = (
    '            elif tool_name == "sdf_tool":\n'
    '                result = compute_sdf_tool(args.get("mode"), args.get("params"))\n'
    '                resp = {\n'
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                }\n'
)
content = content.replace(dispatch_marker, sdf_dispatch_block + dispatch_marker, 1)
print("Dispatch elif de sdf_tool insertado antes de distmesh_tool.")

# ---------------------------------------------------------------------------
# 3. Lista de schemas
# ---------------------------------------------------------------------------

schema_marker = "    DISTMESH_TOOL_SCHEMA,\n"
assert content.count(schema_marker) == 1, "schema_marker no encontrado exactamente 1 vez"
content = content.replace(schema_marker, schema_marker + "    SDF_TOOL_SCHEMA,\n", 1)
print("SDF_TOOL_SCHEMA agregado a la lista de schemas.")

# ---------------------------------------------------------------------------
# 4. Validar y escribir
# ---------------------------------------------------------------------------

ast.parse(content)
with open(SERVER_PATH, "w") as f:
    f.write(content)

print("server.py actualizado y validado sintacticamente.")
print("Smoke test:")
print(
    '  echo \'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":'
    '{"name":"sdf_tool","arguments":{"mode":"evaluate","params":'
    '{"tree":{"op":"sphere","center":[0,0,0],"radius":1.0},"points":[[0,0,0],[1,0,0]]}}}}\' '
    "| timeout 30 python3 server.py"
)
