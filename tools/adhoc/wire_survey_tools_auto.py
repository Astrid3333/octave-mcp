#!/usr/bin/env python3
"""
wire_survey_tools_auto.py
Cablea los 6 survey_*_tool en octave-mcp/server.py: import, entradas TOOLS, dispatch elif.
Corre desde ~/octave-mcp/  (mismo directorio que server.py y donde vas a copiar survey_tools.py).
"""

import shutil
import subprocess
import sys
import time

FILE = "server.py"
TS = time.strftime("%Y%m%d_%H%M%S")
BACKUP = f"server.py.bak_{TS}"

with open(FILE, "r", encoding="utf-8") as f:
    content = f.read()

# ---------------------------------------------------------------------------
# 1) IMPORT
# ---------------------------------------------------------------------------
import_anchor = "from mesh_spectral_tool import compute_mesh_spectral_tool, MESH_SPECTRAL_TOOL_SCHEMA\n"
import_block = (
    "from survey_tools import (\n"
    "    compute_survey_angles, SURVEY_ANGLES_TOOL_SCHEMA,\n"
    "    compute_survey_distance, SURVEY_DISTANCE_TOOL_SCHEMA,\n"
    "    compute_survey_curvature, SURVEY_CURVATURE_TOOL_SCHEMA,\n"
    "    compute_traverse_adjustment, TRAVERSE_ADJUSTMENT_TOOL_SCHEMA,\n"
    "    compute_survey_curves, SURVEY_CURVES_TOOL_SCHEMA,\n"
    "    compute_survey_area_volume, SURVEY_AREA_VOLUME_TOOL_SCHEMA,\n"
    ")\n"
)

assert content.count(import_anchor) == 1, f"import_anchor aparece {content.count(import_anchor)} veces (esperado 1)"
content = content.replace(import_anchor, import_anchor + import_block)

# ---------------------------------------------------------------------------
# 2) TOOLS list
# ---------------------------------------------------------------------------
tools_anchor = "    MESH_SPECTRAL_TOOL_SCHEMA,\n]"
tools_block = (
    "    MESH_SPECTRAL_TOOL_SCHEMA,\n"
    "    SURVEY_ANGLES_TOOL_SCHEMA,\n"
    "    SURVEY_DISTANCE_TOOL_SCHEMA,\n"
    "    SURVEY_CURVATURE_TOOL_SCHEMA,\n"
    "    TRAVERSE_ADJUSTMENT_TOOL_SCHEMA,\n"
    "    SURVEY_CURVES_TOOL_SCHEMA,\n"
    "    SURVEY_AREA_VOLUME_TOOL_SCHEMA,\n"
    "]"
)

assert content.count(tools_anchor) == 1, f"tools_anchor aparece {content.count(tools_anchor)} veces (esperado 1)"
content = content.replace(tools_anchor, tools_block)

# ---------------------------------------------------------------------------
# 3) DISPATCH elif
# ---------------------------------------------------------------------------
dispatch_anchor = (
    "            else:\n"
    "                resp = {\n"
    "                    \"jsonrpc\": \"2.0\", \"id\": req_id,\n"
    "                    \"error\": {\"code\": -32601, \"message\": f\"Tool desconocido: {tool_name}\"},\n"
    "                }\n"
)

def elif_block(tool_name, compute_fn):
    return (
        f"            elif tool_name == \"{tool_name}\":\n"
        f"                result = {compute_fn}(**args)\n"
        f"                resp = {{\n"
        f"                    \"jsonrpc\": \"2.0\", \"id\": req_id,\n"
        f"                    \"result\": {{\"content\": [{{\"type\": \"text\", \"text\": json.dumps(result, ensure_ascii=False, indent=2)}}]}},\n"
        f"                }}\n"
    )

new_elifs = (
    elif_block("survey_angles_tool", "compute_survey_angles")
    + elif_block("survey_distance_tool", "compute_survey_distance")
    + elif_block("survey_curvature_tool", "compute_survey_curvature")
    + elif_block("traverse_adjustment_tool", "compute_traverse_adjustment")
    + elif_block("survey_curves_tool", "compute_survey_curves")
    + elif_block("survey_area_volume_tool", "compute_survey_area_volume")
)

assert content.count(dispatch_anchor) == 1, f"dispatch_anchor aparece {content.count(dispatch_anchor)} veces (esperado 1)"
content = content.replace(dispatch_anchor, new_elifs + dispatch_anchor)

# ---------------------------------------------------------------------------
# Backup + escritura + validación
# ---------------------------------------------------------------------------
shutil.copy(FILE, BACKUP)
print(f"Backup creado: {BACKUP}")

with open(FILE, "w", encoding="utf-8") as f:
    f.write(content)

result = subprocess.run([sys.executable, "-m", "py_compile", FILE], capture_output=True, text=True)
if result.returncode != 0:
    print("ERROR de compilacion, restaurando backup:")
    print(result.stderr)
    shutil.copy(BACKUP, FILE)
    sys.exit(1)

print("OK: server.py actualizado y compila correctamente.")
print("Recordá copiar survey_tools.py a este mismo directorio antes de reiniciar el server.")
print(f"Backup por si algo falla: {BACKUP}")
