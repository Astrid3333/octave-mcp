"""
patch_wire_gait.py

Wirea gait_analysis_tool.py en server.py agregando una sola linea de
import (el modulo se auto-registra via tool_registry.register_tool(),
mismo patron que debt_snowball_tool.py / molecular_dynamics_tool.py).

Uso: colocar gait_analysis_tool.py en la raiz del repo (junto a server.py)
y correr:  python3 patch_wire_gait.py
"""
import ast
import shutil
from datetime import datetime

PATH = "server.py"
IMPORT_LINE = "import gait_analysis_tool  # auto-registra via tool_registry, no requiere mas ediciones\n"

with open(PATH) as f:
    content = f.read()

if "import gait_analysis_tool" in content:
    print("gait_analysis_tool ya esta wireado en server.py -- nada que hacer.")
else:
    backup = f"{PATH}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(PATH, backup)
    print(f"Backup: {backup}")

    # anclar despues de la ultima linea "import X_tool  # auto-registra..."
    # existente, para mantener el bloque de auto-registros junto
    lines = content.splitlines(keepends=True)
    insert_at = None
    for i, line in enumerate(lines):
        if "# auto-registra via tool_registry" in line:
            insert_at = i + 1

    if insert_at is None:
        # fallback: insertar despues de la primera linea "import tool_registry"
        for i, line in enumerate(lines):
            if line.startswith("import tool_registry"):
                insert_at = i + 1
                break

    if insert_at is None:
        raise SystemExit(
            "No encontre un lugar de anclaje (ni '# auto-registra via tool_registry' "
            "ni 'import tool_registry') en server.py -- revisar manualmente."
        )

    lines.insert(insert_at, IMPORT_LINE)
    new_content = "".join(lines)

    ast.parse(new_content)  # valida sintaxis antes de escribir
    with open(PATH, "w") as f:
        f.write(new_content)

    print(f"gait_analysis_tool wireado en server.py (linea insertada en la posicion {insert_at + 1}).")
    print("server.py: sintaxis OK")
