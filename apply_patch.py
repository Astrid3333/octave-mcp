#!/usr/bin/env python3
"""
apply_patch.py

Wirea statistical_physics_tool, cfd_tool, glm_tool, clustering_tool,
mcdm_tool, octave_syntax_tool en server.py de octave-mcp.

Uso: correr desde ~/octave-mcp (donde estan server.py y los 6 .py copiados)
    python3 apply_patch.py

Hace backup de server.py y clustering_tool.py antes de tocar nada.
"""
import re
import shutil
import sys

SERVER = "server.py"
CLUSTERING = "clustering_tool.py"

# ---------------------------------------------------------------------
# 0) Backups
# ---------------------------------------------------------------------
shutil.copy(SERVER, SERVER + ".bak_wireo11")
shutil.copy(CLUSTERING, CLUSTERING + ".bak_wireo11")
print(f"Backups: {SERVER}.bak_wireo11, {CLUSTERING}.bak_wireo11")

# ---------------------------------------------------------------------
# 1) clustering_tool.py no tenia schema -> se lo agregamos
# ---------------------------------------------------------------------
with open(CLUSTERING, "r") as f:
    clustering_src = f.read()

CLUSTERING_SCHEMA_BLOCK = '''

CLUSTERING_TOOL_SCHEMA = {
    "name": "clustering_tool",
    "description": (
        "Clustering y reduccion de dimensionalidad: kmeans (particional, "
        "silhouette + davies-bouldin score), hierarchical (aglomerativo, "
        "linkage single/complete/average, con dendrograma), pca_extended "
        "(componentes principales, varianza explicada, contribuciones por "
        "variable)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["kmeans", "hierarchical", "pca_extended"]},
            "params": {"type": "object", "description": "Parametros especificos de cada modo, ver docstrings."},
        },
        "required": ["mode"],
    },
}
'''

if "CLUSTERING_TOOL_SCHEMA" not in clustering_src:
    clustering_src += CLUSTERING_SCHEMA_BLOCK
    with open(CLUSTERING, "w") as f:
        f.write(clustering_src)
    print(f"[OK] Agregado CLUSTERING_TOOL_SCHEMA a {CLUSTERING}")
else:
    print(f"[SKIP] {CLUSTERING} ya tenia CLUSTERING_TOOL_SCHEMA")

# ---------------------------------------------------------------------
# 2) server.py: imports, TOOLS[], dispatch
# ---------------------------------------------------------------------
with open(SERVER, "r") as f:
    src = f.read()

# --- imports ---
IMPORT_ANCHOR = "from archaeological_simulation_tool import compute_archaeological_simulation, ARCHAEOLOGICAL_SIMULATION_TOOL_SCHEMA"
NEW_IMPORTS = IMPORT_ANCHOR + """
from statistical_physics_tool import compute_statistical_physics, STATISTICAL_PHYSICS_TOOL_SCHEMA
from cfd_tool import compute_cfd, CFD_TOOL_SCHEMA
from glm_tool import compute_glm, GLM_TOOL_SCHEMA
from clustering_tool import compute_clustering, CLUSTERING_TOOL_SCHEMA
from mcdm_tool import compute_mcdm, MCDM_TOOL_SCHEMA
from octave_syntax_tool import compute_octave_syntax, OCTAVE_SYNTAX_TOOL_SCHEMA"""

if "from statistical_physics_tool import" not in src:
    assert IMPORT_ANCHOR in src, "No encontre el anchor de import esperado en server.py"
    src = src.replace(IMPORT_ANCHOR, NEW_IMPORTS, 1)
    print("[OK] Imports agregados")
else:
    print("[SKIP] Imports ya estaban")

# --- entrada en TOOLS = [...] ---
TOOLS_ANCHOR = "    ARCHAEOLOGICAL_SIMULATION_TOOL_SCHEMA,"
NEW_TOOLS_ENTRIES = TOOLS_ANCHOR + """
    STATISTICAL_PHYSICS_TOOL_SCHEMA,
    CFD_TOOL_SCHEMA,
    GLM_TOOL_SCHEMA,
    CLUSTERING_TOOL_SCHEMA,
    MCDM_TOOL_SCHEMA,
    OCTAVE_SYNTAX_TOOL_SCHEMA,"""

if "STATISTICAL_PHYSICS_TOOL_SCHEMA,\n" not in src.split("TOOLS = [")[1].split("]")[0] if "TOOLS = [" in src else True:
    if TOOLS_ANCHOR in src and "STATISTICAL_PHYSICS_TOOL_SCHEMA," not in src[:src.find(TOOLS_ANCHOR) + 3000]:
        src = src.replace(TOOLS_ANCHOR, NEW_TOOLS_ENTRIES, 1)
        print("[OK] Entradas en TOOLS[] agregadas")
    else:
        print("[SKIP] Entradas en TOOLS[] ya estaban (o anchor no encontrado)")

# --- dispatch ---
DISPATCH_ANCHOR = '''            elif tool_name == "archaeological_simulation":
                result = compute_archaeological_simulation(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }'''

NEW_DISPATCH = DISPATCH_ANCHOR + '''
            elif tool_name == "statistical_physics_tool":
                # bug conocido: schema declara "params" anidado pero la funcion
                # usa **params flat -> desempaquetamos aca en vez de tocar el schema
                _params = args.get("params") or {}
                result = compute_statistical_physics(mode=args["mode"], **_params)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }
            elif tool_name == "cfd_tool":
                result = compute_cfd(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }
            elif tool_name == "glm_tool":
                result = compute_glm(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }
            elif tool_name == "clustering_tool":
                _params = args.get("params") or {}
                result = compute_clustering(mode=args["mode"], **_params)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }
            elif tool_name == "mcdm":
                result = compute_mcdm(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }
            elif tool_name == "octave_syntax":
                result = compute_octave_syntax(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }'''

if 'tool_name == "statistical_physics_tool"' not in src:
    assert DISPATCH_ANCHOR in src, "No encontre el anchor de dispatch esperado en server.py"
    src = src.replace(DISPATCH_ANCHOR, NEW_DISPATCH, 1)
    print("[OK] Bloques de dispatch agregados")
else:
    print("[SKIP] Dispatch ya estaba")

with open(SERVER, "w") as f:
    f.write(src)

# ---------------------------------------------------------------------
# 3) Validar sintaxis
# ---------------------------------------------------------------------
import ast
try:
    ast.parse(open(SERVER).read())
    ast.parse(open(CLUSTERING).read())
    print("\n=== SINTAXIS OK en server.py y clustering_tool.py ===")
except SyntaxError as e:
    print(f"\n=== ERROR DE SINTAXIS: {e} ===")
    print(f"Restaura con: cp {SERVER}.bak_wireo11 {SERVER}")
    sys.exit(1)

print("\nListo. Ahora corre:")
print("  python3 ~/Descargas/test_harness_timeout.py ~/octave-mcp/server.py")
