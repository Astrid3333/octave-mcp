#!/usr/bin/env python3
"""
Fix directo del bug confirmado en octave-mcp/server.py.

electromagnetic_tool.py define `def handle_electromagnetic_tool(arguments):`
(linea 253) -- el parametro de esa funcion se llama "arguments" por
casualidad. Al escribir el patch de wireo asumi (mal) que la variable
disponible en el scope del dispatch de server.py tambien se llamaba asi.

La rama de acoustics_tool (que si funciona) confirma que la variable real
en ese scope es `args` (via `args.get("mode", "validate")`, `args.get("params")`).

Este script reemplaza UNICAMENTE:
    result = handle_electromagnetic_tool(arguments)
por:
    result = handle_electromagnetic_tool(args)

dentro de la rama `elif tool_name == "electromagnetic_tool":`. No toca
ninguna otra linea.

Uso (dentro de ~/octave-mcp/):
    python3 fix_electromagnetic_tool_arguments_v2.py
"""

import ast
import re
import shutil
import time

SERVER_PATH = "server.py"

with open(SERVER_PATH, "r") as f:
    content = f.read()

ast.parse(content)

pattern = (
    r'(elif\s+tool_name\s*==\s*["\']electromagnetic_tool["\']\s*:\s*\n'
    r'[ \t]*result\s*=\s*handle_electromagnetic_tool\()arguments(\))'
)
matches = list(re.finditer(pattern, content))

if len(matches) == 0:
    print("ABORTADO: no encontre 'elif tool_name == \"electromagnetic_tool\": ... "
          "result = handle_electromagnetic_tool(arguments)' con esa forma exacta.")
    print("No se toco nada. Pegame `grep -n -A2 'elif tool_name == \"electromagnetic_tool\"' server.py`.")
    raise SystemExit(1)

if len(matches) > 1:
    print(f"ABORTADO: {len(matches)} ocurrencias, no es seguro reemplazar en automatico. No se toco nada.")
    raise SystemExit(1)

m = matches[0]

timestamp = time.strftime("%Y%m%d_%H%M%S")
backup_path = f"{SERVER_PATH}.bak_{timestamp}"
shutil.copy(SERVER_PATH, backup_path)
print(f"Backup: {backup_path}")

new_content = content[:m.start()] + m.group(1) + "args" + m.group(2) + content[m.end():]
ast.parse(new_content)

with open(SERVER_PATH, "w") as f:
    f.write(new_content)

print("Corregido: handle_electromagnetic_tool(arguments) -> handle_electromagnetic_tool(args)")
print("server.py actualizado y validado sintacticamente.")
