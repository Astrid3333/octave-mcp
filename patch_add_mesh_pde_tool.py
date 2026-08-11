#!/usr/bin/env python3
"""
Patch: agrega mesh_pde_tool a octave-mcp/server.py
Mismos anchors confirmados que sdf_tool/lscm_tool.

Uso (dentro de ~/octave-mcp/):
    python3 patch_add_mesh_pde_tool.py
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
# 1. Import — anclamos sobre el import mas reciente ya insertado (lscm o sdf),
#    o distmesh como ultimo fallback.
# ---------------------------------------------------------------------------

if "from lscm_tool import compute_lscm_tool, LSCM_TOOL_SCHEMA" in content:
    import_marker = "from lscm_tool import compute_lscm_tool, LSCM_TOOL_SCHEMA"
elif "from sdf_tool import compute_sdf_tool, SDF_TOOL_SCHEMA" in content:
    import_marker = "from sdf_tool import compute_sdf_tool, SDF_TOOL_SCHEMA"
else:
    import_marker = "from distmesh_tool import compute_distmesh, DISTMESH_TOOL_SCHEMA"

assert content.count(import_marker) == 1, "import_marker no encontrado exactamente 1 vez"

pde_import = "\nfrom mesh_pde_tool import compute_mesh_pde_tool, MESH_PDE_TOOL_SCHEMA"
if "from mesh_pde_tool import" not in content:
    content = content.replace(import_marker, import_marker + pde_import, 1)
    print("Import de mesh_pde_tool insertado.")
else:
    print("Import de mesh_pde_tool ya presente, no se duplica.")

# ---------------------------------------------------------------------------
# 2. Dispatch elif — se inserta ANTES del bloque de distmesh_tool
# ---------------------------------------------------------------------------

dispatch_marker = (
    '            elif tool_name == "distmesh_tool":\n'
    '                result = compute_distmesh(**args)\n'
)
assert content.count(dispatch_marker) == 1, "dispatch_marker no encontrado exactamente 1 vez"

pde_dispatch_block = (
    '            elif tool_name == "mesh_pde_tool":\n'
    '                result = compute_mesh_pde_tool(args.get("mode"), args.get("params"))\n'
    '                resp = {\n'
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                }\n'
)
content = content.replace(dispatch_marker, pde_dispatch_block + dispatch_marker, 1)
print("Dispatch elif de mesh_pde_tool insertado antes de distmesh_tool.")

# ---------------------------------------------------------------------------
# 3. Lista de schemas
# ---------------------------------------------------------------------------

schema_marker = "    DISTMESH_TOOL_SCHEMA,\n"
assert content.count(schema_marker) == 1, "schema_marker no encontrado exactamente 1 vez"
content = content.replace(schema_marker, schema_marker + "    MESH_PDE_TOOL_SCHEMA,\n", 1)
print("MESH_PDE_TOOL_SCHEMA agregado a la lista de schemas.")

# ---------------------------------------------------------------------------
# 4. Validar y escribir
# ---------------------------------------------------------------------------

ast.parse(content)
with open(SERVER_PATH, "w") as f:
    f.write(content)

print("server.py actualizado y validado sintacticamente.")
print("Smoke test (fan de 3 triangulos, vertice 3 es el unico interior libre):")
print(
    '  echo \'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":'
    '{"name":"mesh_pde_tool","arguments":{"mode":"smooth","params":'
    '{"vertices":[[0,0,0],[2,0,0],[1,2,0],[1,0.5,0]],'
    '"faces":[[0,1,3],[1,2,3],[2,0,3]],"boundary_indices":[0,1,2]}}}}\' '
    "| timeout 30 python3 server.py"
)
