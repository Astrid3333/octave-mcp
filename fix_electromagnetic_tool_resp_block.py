#!/usr/bin/env python3
"""
Fix #2 para octave-mcp/server.py: la rama `elif tool_name ==
"electromagnetic_tool":` quedo con `result = handle_electromagnetic_tool(args)`
pero SIN su propio bloque `resp = {...}` -- por eso el nombre `args` ya
esta bien (fix anterior) pero ahora tira `name 'resp' is not defined`.

Es el mismo patron de bug que ya paso una vez con archaeoastronomy /
quantum_information: el patch de wireo original inserto la rama nueva
justo antes de acoustics_tool pero corto el bloque resp mal, dejandolo
"pegado" solo a acoustics_tool en vez de duplicarlo para la rama nueva.

Este script:
  1. Toma el bloque `resp = {...}` de la rama de acoustics_tool (que si
     funciona) como plantilla, preservando indentacion exacta.
  2. Confirma que la rama de electromagnetic_tool termina en
     `result = handle_electromagnetic_tool(args)` sin resp propio.
  3. Inserta una copia de ese bloque resp inmediatamente despues de esa
     linea, dentro de la rama de electromagnetic_tool. No toca nada mas.

Uso (dentro de ~/octave-mcp/):
    python3 fix_electromagnetic_tool_resp_block.py
"""

import ast
import re
import shutil
import time

SERVER_PATH = "server.py"

with open(SERVER_PATH, "r") as f:
    content = f.read()

ast.parse(content)

# 1. Extraer el bloque resp={...} de la rama de acoustics_tool (plantilla conocida-buena).
acoustics_resp_match = re.search(
    r'elif\s+tool_name\s*==\s*["\']acoustics_tool["\']\s*:\s*\n'
    r'(?:[ \t]*[^\n]*\n)*?'                      # linea(s) de result = ... antes del resp
    r'([ \t]+)resp\s*=\s*\{\s*\n'
    r'(?:[ \t]*[^\n]*\n)*?'
    r'[ \t]*\}\s*\n',
    content
)

if not acoustics_resp_match:
    print("ABORTADO: no encontre un bloque 'resp = {...}' dentro de la rama de acoustics_tool.")
    print("No se toco nada. Pegame `grep -n -A6 'elif tool_name == \"acoustics_tool\"' server.py`.")
    raise SystemExit(1)

indent = acoustics_resp_match.group(1)
resp_template = acoustics_resp_match.group(0).split("resp = {", 1)[1]
resp_template = "resp = {" + resp_template  # bloque completo tal cual, con su indentacion original

# 2. Confirmar que electromagnetic_tool termina en result=... sin resp propio,
#    y que el siguiente elif es justamente el de acoustics_tool (para no
#    insertar en el lugar equivocado si el orden cambio).
em_pattern = re.compile(
    r'(elif\s+tool_name\s*==\s*["\']electromagnetic_tool["\']\s*:\s*\n'
    r'([ \t]+)result\s*=\s*handle_electromagnetic_tool\(args\)\s*\n)'
    r'(\s*elif\s+tool_name\s*==\s*["\']acoustics_tool["\'])'
)
em_match = em_pattern.search(content)

if not em_match:
    print("ABORTADO: no encontre la rama de electromagnetic_tool en la forma esperada")
    print("('result = handle_electromagnetic_tool(args)' seguida directo del elif de acoustics_tool, sin resp propio).")
    print("No se toco nada. Pegame `grep -n -A3 'elif tool_name == \"electromagnetic_tool\"' server.py`.")
    raise SystemExit(1)

if "resp" in em_match.group(1):
    print("La rama de electromagnetic_tool ya tiene un 'resp' propio -- no hay nada que corregir aca.")
    raise SystemExit(1)

em_indent = em_match.group(2)
# Reindentar la plantilla del resp a la indentacion de la rama de
# electromagnetic_tool, preservando la indentacion RELATIVA interna del
# bloque (las lineas dentro del dict van 4 espacios mas adentro que
# "resp = {" y el cierre "}" vuelve al nivel base).
base_len = len(indent)
template_lines = resp_template.rstrip("\n").split("\n")
reindented = []
for i, line in enumerate(template_lines):
    stripped = line.lstrip(" \t")
    if i == 0:
        reindented.append(em_indent + stripped)  # "resp = {"
        continue
    orig_leading = len(line) - len(stripped)
    delta = max(orig_leading - base_len, 0)
    reindented.append(em_indent + (" " * delta) + stripped)
reindented_block = "\n".join(reindented) + "\n"

insertion_point = em_match.end(1)  # justo despues de la linea "result = handle_electromagnetic_tool(args)\n"

# 3. Backup y escritura.
timestamp = time.strftime("%Y%m%d_%H%M%S")
backup_path = f"{SERVER_PATH}.bak_{timestamp}"
shutil.copy(SERVER_PATH, backup_path)
print(f"Backup: {backup_path}")

new_content = content[:insertion_point] + reindented_block + content[insertion_point:]
ast.parse(new_content)

with open(SERVER_PATH, "w") as f:
    f.write(new_content)

print("Bloque 'resp = {...}' agregado a la rama de electromagnetic_tool (copiado del patron de acoustics_tool).")
print("server.py actualizado y validado sintacticamente.")
