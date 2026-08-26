#!/usr/bin/env python3
r"""
Inserta aminoacid_tool.py en ~/octave-mcp: copia el archivo a la raíz del
repo y agrega la línea de import a server.py, ancla después del último
import de tool "^import \w+_tool$" que encuentre. Auto-registra vía
tool_registry (decorador @register_tool), no requiere más ediciones.
"""
import ast
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO = Path.home() / "octave-mcp"
SRC = Path(__file__).parent / "aminoacid_tool.py"
SERVER = REPO / "server.py"
IMPORT_LINE = "import aminoacid_tool  # auto-registra via tool_registry, no requiere mas ediciones\n"


def main():
    if not REPO.exists():
        print(f"ERROR: no existe {REPO}")
        sys.exit(1)
    if not SRC.exists():
        print(f"ERROR: no existe {SRC} (¿lo descargaste al lado de este script?)")
        sys.exit(1)
    if not SERVER.exists():
        print(f"ERROR: no existe {SERVER}")
        sys.exit(1)

    dest = REPO / "aminoacid_tool.py"
    if dest.exists():
        if SRC.resolve() == dest.resolve():
            print(f"{dest} ya está en su lugar (fue movido ahí directamente), no hace falta copiar.")
        else:
            print(f"ERROR: {dest} ya existe y es un archivo distinto al de origen. Borralo o revisalo a mano primero.")
            sys.exit(1)
    else:
        # 1. copiar archivo
        shutil.copy(SRC, dest)
        print(f"Copiado: {dest}")

    # 2. validar sintaxis del archivo copiado
    ast.parse(dest.read_text())
    print("aminoacid_tool.py: sintaxis OK (ast.parse)")

    # 3. backup de server.py
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = REPO / f"server.py.backup-aminoacid-{ts}"
    shutil.copy(SERVER, backup)
    print(f"Backup creado: {backup.name}")

    # 4. buscar ancla: último "import X_tool" de una sola linea
    lines = SERVER.read_text().splitlines(keepends=True)
    anchor_idx = None
    pattern = re.compile(r"^import \w+_tool\s*(#.*)?$")
    for i, line in enumerate(lines):
        if pattern.match(line.strip()):
            anchor_idx = i
    if anchor_idx is None:
        print("ERROR: no se encontró ninguna línea ancla 'import X_tool' en server.py")
        sys.exit(1)
    print(f"Ancla encontrada: {lines[anchor_idx].strip()!r} en la linea {anchor_idx + 1}")

    if "import aminoacid_tool" in SERVER.read_text():
        print("ERROR: server.py ya tiene una referencia a aminoacid_tool, abortando para no duplicar.")
        sys.exit(1)

    lines.insert(anchor_idx + 1, IMPORT_LINE)
    SERVER.write_text("".join(lines))

    # 5. validar sintaxis de server.py actualizado
    ast.parse(SERVER.read_text())
    print("server.py actualizado y valida sintacticamente (ast.parse OK).")

    print("\nSiguiente paso -- smoke test real:")
    print("  echo '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}' | python3 server.py \\")
    print("    | python3 -c \"import sys,json; names=[t['name'] for t in json.load(sys.stdin)['result']['tools']]; print('aminoacid tools encontrados:', [n for n in names if 'aminoacid' in n])\"")
    print("\nDespues corré el validate real:")
    print("  echo '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"aminoacid_tool\",\"arguments\":{\"mode\":\"validate\"}}}' | python3 server.py")


if __name__ == "__main__":
    main()
