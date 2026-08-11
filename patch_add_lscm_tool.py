#!/usr/bin/env python3
"""
Patch: agrega lscm_tool a octave-mcp/server.py
Usa el mismo anchor de import (distmesh_tool) y el mismo patron de dispatch/schema
ya confirmados en el patch de sdf_tool.

Uso (dentro de ~/octave-mcp/):
    python3 patch_add_lscm_tool.py
"""

import ast
import shutil
import time

SERVER_PATH = "server.py"

with open(SERVER_PATH, "r") as f:
    content = f.read()

ast.parse(content)

timestamp = time.strftime("%Y%m%d_%H%M%S")
backup_path = f"{SERVER_PATH}.bak_{timestamp}"
shutil.copy(SERVER_PATH, backup_path)
print(f"Backup: {backup_path}")

# ---------------------------------------------------------------------------
# 1. Import — mismo anchor que uso sdf_tool. Si sdf_tool.py ya se aplico,
#    el import de sdf_tool aparece justo despues del de distmesh_tool, asi
#    que anclamos sobre la linea de sdf_tool si existe, o distmesh si no.
# ---------------------------------------------------------------------------

if "from sdf_tool import compute_sdf_tool, SDF_TOOL_SCHEMA" in content:
    import_marker = "from sdf_tool import compute_sdf_tool, SDF_TOOL_SCHEMA"
else:
    import_marker = "from distmesh_tool import compute_distmesh, DISTMESH_TOOL_SCHEMA"

assert content.count(import_marker) == 1, "import_marker no encontrado exactamente 1 vez"

lscm_import = "\nfrom lscm_tool import compute_lscm_tool, LSCM_TOOL_SCHEMA"
if "from lscm_tool import" not in content:
    content = content.replace(import_marker, import_marker + lscm_import, 1)
    print("Import de lscm_tool insertado.")
else:
    print("Import de lscm_tool ya presente, no se duplica.")

# ---------------------------------------------------------------------------
# 2. Dispatch elif — se inserta ANTES del bloque de distmesh_tool
# ---------------------------------------------------------------------------

dispatch_marker = (
    '            elif tool_name == "distmesh_tool":\n'
    '                result = compute_distmesh(**args)\n'
)
assert content.count(dispatch_marker) == 1, "dispatch_marker no encontrado exactamente 1 vez"

lscm_dispatch_block = (
    '            elif tool_name == "lscm_tool":\n'
    '                result = compute_lscm_tool(args.get("mode"), args.get("params"))\n'
    '                resp = {\n'
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                }\n'
)
content = content.replace(dispatch_marker, lscm_dispatch_block + dispatch_marker, 1)
print("Dispatch elif de lscm_tool insertado antes de distmesh_tool.")

# ---------------------------------------------------------------------------
# 3. Lista de schemas
# ---------------------------------------------------------------------------

schema_marker = "    DISTMESH_TOOL_SCHEMA,\n"
assert content.count(schema_marker) == 1, "schema_marker no encontrado exactamente 1 vez"
content = content.replace(schema_marker, schema_marker + "    LSCM_TOOL_SCHEMA,\n", 1)
print("LSCM_TOOL_SCHEMA agregado a la lista de schemas.")

# ---------------------------------------------------------------------------
# 4. Validar y escribir
# ---------------------------------------------------------------------------

ast.parse(content)
with open(SERVER_PATH, "w") as f:
    f.write(content)

print("server.py actualizado y validado sintacticamente.")
print("Smoke test (triangulo unico, deberia dar distorsion ~0):")
print(
    '  echo \'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":'
    '{"name":"lscm_tool","arguments":{"mode":"flatten_and_distortion","params":'
    '{"vertices":[[0,0,0],[1,0,0],[0,1,0]],"faces":[[0,1,2]]}}}}\' '
    "| timeout 30 python3 server.py"
)
