#!/usr/bin/env python3
"""
Patch: agrega acoustics_tool a octave-mcp/server.py
Mismo patron de 3 puntos (import, dispatch, schema list) que
genome_signal_analysis_tool / polarization_mapping_tool.

Uso (dentro de ~/octave-mcp/):
    python3 patch_add_acoustics_tool.py
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
# 1. Import
# ---------------------------------------------------------------------------

import_marker = "from polarization_mapping_tool import compute_polarization_mapping, POLARIZATION_MAPPING_SCHEMA"
assert content.count(import_marker) == 1, "import_marker no encontrado exactamente 1 vez"

acoustics_import = "\nfrom acoustics_tool import compute_acoustics_tool, ACOUSTICS_TOOL_SCHEMA"
if "from acoustics_tool import" not in content:
    content = content.replace(import_marker, import_marker + acoustics_import, 1)
    print("Import de acoustics_tool insertado.")
else:
    print("Import de acoustics_tool ya presente, no se duplica.")

# ---------------------------------------------------------------------------
# 2. Dispatch elif
# ---------------------------------------------------------------------------

dispatch_marker = (
    '            elif tool_name == "polarization_mapping":\n'
    '                result = compute_polarization_mapping(**args)\n'
)
assert content.count(dispatch_marker) == 1, "dispatch_marker no encontrado exactamente 1 vez"

acoustics_dispatch_block = (
    '            elif tool_name == "acoustics_tool":\n'
    '                result = compute_acoustics_tool(args.get("mode", "validate"), args.get("params"))\n'
    '                resp = {\n'
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                }\n'
)
content = content.replace(dispatch_marker, acoustics_dispatch_block + dispatch_marker, 1)
print("Dispatch elif de acoustics_tool insertado antes de polarization_mapping.")

# ---------------------------------------------------------------------------
# 3. Lista de schemas
# ---------------------------------------------------------------------------

schema_marker = "    POLARIZATION_MAPPING_SCHEMA,\n"
assert content.count(schema_marker) == 1, "schema_marker no encontrado exactamente 1 vez"
content = content.replace(schema_marker, schema_marker + "    ACOUSTICS_TOOL_SCHEMA,\n", 1)
print("ACOUSTICS_TOOL_SCHEMA agregado a la lista de schemas.")

# ---------------------------------------------------------------------------
# 4. Validar y escribir
# ---------------------------------------------------------------------------

ast.parse(content)
with open(SERVER_PATH, "w") as f:
    f.write(content)

print("server.py actualizado y validado sintacticamente.")
