#!/usr/bin/env python3
"""
Patch: agrega sdf_tool a octave-mcp/server.py

Uso (en tu maquina, dentro de ~/octave-mcp/):
    python3 patch_add_sdf_tool.py

Requiere que sdf_tool.py este en el mismo directorio que server.py
(o ajustar SDF_MODULE_PATH abajo).

Sigue el patron:
  - backup con timestamp antes de escribir
  - anchors literales con assert content.count(marker) == 1
  - ast.parse() para validar sintaxis antes y despues
"""

import ast
import shutil
import time

SERVER_PATH = "server.py"
SDF_MODULE_PATH = "sdf_tool.py"

# ---------------------------------------------------------------------------
# 1. Validar que el archivo actual es sintacticamente valido
# ---------------------------------------------------------------------------

with open(SERVER_PATH, "r") as f:
    content = f.read()

ast.parse(content)  # falla ruidosamente si server.py ya esta roto

# ---------------------------------------------------------------------------
# 2. Backup
# ---------------------------------------------------------------------------

timestamp = time.strftime("%Y%m%d_%H%M%S")
backup_path = f"{SERVER_PATH}.bak_{timestamp}"
shutil.copy(SERVER_PATH, backup_path)
print(f"Backup: {backup_path}")

# ---------------------------------------------------------------------------
# 3. Insertar el import del modulo sdf_tool
#    Anchor: la primera linea "import numpy" (ajustar si tu import real difiere)
# ---------------------------------------------------------------------------

import_marker = "import numpy as np"
assert content.count(import_marker) >= 1, (
    "No encontre 'import numpy as np' en server.py — "
    "ajustar import_marker manualmente en este script."
)
# insertamos el import de sdf_tool justo despues de la PRIMERA ocurrencia
idx = content.index(import_marker) + len(import_marker)
sdf_import = "\nfrom sdf_tool import compute_sdf_tool, SDF_TOOL_SCHEMA"
if sdf_import.strip() not in content:
    content = content[:idx] + sdf_import + content[idx:]
    print("Import de sdf_tool insertado.")
else:
    print("Import de sdf_tool ya presente, no se duplica.")

# ---------------------------------------------------------------------------
# 4. Insertar el dispatch elif — anchor: dispatch existente de distmesh_tool
#    AJUSTAR este marker si el nombre real de tu bloque difiere.
# ---------------------------------------------------------------------------

dispatch_marker = 'elif tool_name == "distmesh_tool":'
assert content.count(dispatch_marker) == 1, (
    f"Marker de dispatch no encontrado exactamente una vez: '{dispatch_marker}'. "
    "Editar dispatch_marker en este script para que apunte a un elif real "
    "de tu server.py (copiar y pegar la linea exacta, con la indentacion que uses)."
)

sdf_dispatch_block = (
    'elif tool_name == "sdf_tool":\n'
    '            result = compute_sdf_tool(\n'
    '                arguments.get("mode"), arguments.get("params")\n'
    '            )\n'
    '        '
)
content = content.replace(dispatch_marker, sdf_dispatch_block + dispatch_marker, 1)
print("Dispatch elif insertado antes de distmesh_tool.")

# ---------------------------------------------------------------------------
# 5. Insertar en la lista de schemas — anchor: DISTMESH_TOOL_SCHEMA
#    AJUSTAR si el nombre de la variable de schema de distmesh difiere.
# ---------------------------------------------------------------------------

schema_marker = "DISTMESH_TOOL_SCHEMA,"
assert content.count(schema_marker) == 1, (
    f"Marker de schema no encontrado exactamente una vez: '{schema_marker}'. "
    "Editar schema_marker para que apunte al item real de tu lista de schemas."
)
content = content.replace(schema_marker, schema_marker + "\n    SDF_TOOL_SCHEMA,", 1)
print("SDF_TOOL_SCHEMA agregado a la lista de schemas.")

# ---------------------------------------------------------------------------
# 6. Validar sintaxis final y escribir
# ---------------------------------------------------------------------------

ast.parse(content)
with open(SERVER_PATH, "w") as f:
    f.write(content)

print("server.py actualizado y validado.")
print("Verificar sdf_tool.py esta copiado junto a server.py, luego correr el smoke test:")
print(
    '  echo \'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\' | '
    "timeout 30 python3 server.py"
)
