#!/usr/bin/env python3
"""
insert_pointcloud_tools.py -- Agrega los imports de las 4 tools nuevas de
nube de puntos a server.py, anclado por texto sobre un import ya existente
conocido. Aborta sin tocar nada si no encuentra ningun ancla.

Uso:
    cd ~/octave-mcp
    python3 insert_pointcloud_tools.py
"""

import ast
import shutil
import sys
from datetime import datetime

SERVER_PATH = "server.py"
NEW_IMPORTS = [
    "import point_cloud_loader",
    "import point_cloud_filter",
    "import point_cloud_registration",
    "import point_cloud_surface_reconstruction",
]

# candidatos de ancla, en orden de preferencia (el mas probable de estar
# cerca del final del bloque de imports de tools primero)
ANCHOR_CANDIDATES = [
    "import kinematics_simulator",
    "import molecular_dynamics_tool",
    "import particle_simulation_tool",
    "import clustering_tool",
]


def main():
    try:
        with open(SERVER_PATH, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"ERROR: no se encontro '{SERVER_PATH}' en el directorio actual. "
              f"Corré este script desde ~/octave-mcp.")
        sys.exit(1)

    if any(imp in "".join(lines) for imp in NEW_IMPORTS):
        print("AVISO: al menos uno de los imports nuevos ya esta presente en "
              "server.py. Revisá manualmente antes de continuar (no se tocó nada).")
        sys.exit(1)

    anchor_line_idx = None
    anchor_used = None
    for candidate in ANCHOR_CANDIDATES:
        for i, line in enumerate(lines):
            code_part = line.split("#", 1)[0].strip()  # pelar comentario tipo "# auto-registra via tool_registry"
            if code_part == candidate:
                anchor_line_idx = i
                anchor_used = candidate
                break
        if anchor_line_idx is not None:
            break

    if anchor_line_idx is None:
        print("ERROR: no se encontro ningun ancla conocida "
              f"({ANCHOR_CANDIDATES}) en server.py. No se modifico nada. "
              "Pasame `grep -n '^import ' server.py` para elegir un ancla valida.")
        sys.exit(1)

    print(f"Ancla encontrada: '{anchor_used}' en la linea {anchor_line_idx + 1}")

    backup_path = f"{SERVER_PATH}.backup-pointcloud-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(SERVER_PATH, backup_path)
    print(f"Backup creado: {backup_path}")

    insertion = [imp + "\n" for imp in NEW_IMPORTS]
    new_lines = lines[:anchor_line_idx + 1] + insertion + lines[anchor_line_idx + 1:]
    new_content = "".join(new_lines)

    try:
        ast.parse(new_content)
    except SyntaxError as e:
        print(f"ERROR: el server.py resultante no parsea (SyntaxError: {e}). "
              f"No se escribio nada, el backup queda en {backup_path} sin usar.")
        sys.exit(1)

    with open(SERVER_PATH, "w") as f:
        f.write(new_content)

    print("server.py actualizado y valida sintacticamente (ast.parse OK).")
    print("\nSiguiente paso -- smoke test real:")
    print("  echo '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}' | python3 server.py \\")
    print("    | python3 -c \"import sys,json; names=[t['name'] for t in json.load(sys.stdin)['result']['tools']]; "
          "print('point_cloud tools encontrados:', [n for n in names if n.startswith('point_cloud')])\"")


if __name__ == "__main__":
    main()
