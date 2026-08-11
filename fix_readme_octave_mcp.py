#!/usr/bin/env python3
"""
Fix: corrige README.md de octave-mcp despues del error de conteo (118 -> 120)
y saca la mencion de electromagnetic_tool, que nunca se wireo realmente
en server.py (confirmado con grep -c "electromagnetic_tool" server.py -> 0).

Uso (dentro de ~/octave-mcp/):
    python3 fix_readme_octave_mcp.py
"""

import shutil
import time

README_PATH = "README.md"

with open(README_PATH, "r") as f:
    readme = f.read()

timestamp = time.strftime("%Y%m%d_%H%M%S")
backup_path = f"{README_PATH}.bak_{timestamp}"
shutil.copy(README_PATH, backup_path)
print(f"Backup: {backup_path}")

# 1. Corregir 118 -> 120 en las dos lineas reales (no la nota historica de 39)
fixes = [
    ("que expone 118 herramientas", "que expone 120 herramientas"),
    ("*Total: 118 herramientas registradas", "*Total: 120 herramientas registradas"),
    ("octave-mcp: 88 -> 118 tools.", "octave-mcp: 88 -> 120 tools."),
]

for old, new in fixes:
    if old in readme:
        readme = readme.replace(old, new)
        print(f"OK: '{old}' -> '{new}'")
    else:
        print(f"ADVERTENCIA: no se encontro '{old}' — revisar a mano.")

# 2. Sacar el bullet de electromagnetic_tool (no wireado realmente en server.py)
em_bullet_start = "- **electromagnetic_tool**:"
if em_bullet_start in readme:
    start = readme.index(em_bullet_start)
    # el bullet termina en el proximo doble salto de linea
    end = readme.index("\n\n", start)
    removed = readme[start:end]
    readme = readme[:start] + readme[end+2:]
    print("Bullet de electromagnetic_tool removido:")
    print(removed)
else:
    print("No se encontro el bullet de electromagnetic_tool (¿ya se saco?).")

with open(README_PATH, "w") as f:
    f.write(readme)

print("README.md corregido. Revisa el diff antes de commitear:")
print("  git diff README.md | cat")
