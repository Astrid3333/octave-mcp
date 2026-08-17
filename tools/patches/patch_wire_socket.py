"""
patch_wire_socket.py

Wirea socket_topology_tool.py en server.py agregando una sola linea de
import (el modulo se auto-registra via tool_registry.register_tool(),
mismo patron que gait_analysis_tool.py / debt_snowball_tool.py).

Uso: colocar socket_topology_tool.py en la raiz del repo (junto a
server.py) y correr:  python3 patch_wire_socket.py
"""
import ast
import shutil
from datetime import datetime

PATH = "server.py"
IMPORT_LINE = "import socket_topology_tool  # auto-registra via tool_registry, no requiere mas ediciones\n"

with open(PATH) as f:
    content = f.read()

if "import socket_topology_tool" in content:
    print("socket_topology_tool ya esta wireado en server.py -- nada que hacer.")
else:
    backup = f"{PATH}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(PATH, backup)
    print(f"Backup: {backup}")

    lines = content.splitlines(keepends=True)
    insert_at = None
    for i, line in enumerate(lines):
        if "# auto-registra via tool_registry" in line:
            insert_at = i + 1

    if insert_at is None:
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

    ast.parse(new_content)
    with open(PATH, "w") as f:
        f.write(new_content)

    print(f"socket_topology_tool wireado en server.py (linea insertada en la posicion {insert_at + 1}).")
    print("server.py: sintaxis OK")
