#!/usr/bin/env python3
"""
Fase 3 -- APLICADOR. Lee phase3_plan.json (ya revisado: 46/46 sin problemas)
y aplica los cambios:

  1. Inserta el bloque register_tool() al final de cada modulo tocado.
  2. Borra la entrada correspondiente de TOOLS[] en server.py.
  3. Borra el bloque elif correspondiente en server.py.
  4. Si tras borrar todo lo anterior no queda NINGUN otro uso de
     "modulo.algo" en server.py, cambia su import a la forma silenciosa
     "import modulo  # auto-registra via tool_registry, no requiere mas
     ediciones" (el mismo patron que ya tienen personal_budget_tool y
     savings_goal_tool).
  5. Valida con ast.parse() que server.py y cada modulo tocado siguen
     siendo Python sintacticamente valido. Si algo no parsea, restaura
     TODOS los backups y aborta -- no deja el repo a medio aplicar.

Uso:
    python3 apply_phase3.py --dry-run   # no toca nada, solo reporta
    python3 apply_phase3.py             # aplica de verdad

Requisito minimo antes de correr esto de verdad: repo limpio (git status
sin cambios pendientes) para poder revisar el diff completo y hacer
`git checkout .` si hace falta, ademas de los .bak que deja este script.
"""
import ast
import json
import re
import shutil
import sys

DRY_RUN = "--dry-run" in sys.argv

with open("phase3_plan.json") as f:
    plan_data = json.load(f)
plan = plan_data["plan"]
if plan_data["problems"]:
    print("ABORTO: phase3_plan.json todavia tiene problemas sin resolver.")
    sys.exit(1)

with open("server.py") as f:
    server_content = f.read()

by_module = {}
for entry in plan:
    by_module.setdefault(entry["module"], []).append(entry)

backups_made = []


def backup(path):
    bak = path + ".bak"
    shutil.copy(path, bak)
    backups_made.append((path, bak))


def restore_all():
    for path, bak in backups_made:
        shutil.copy(bak, path)
    print(f"Restaurados {len(backups_made)} archivo(s) desde .bak. Nada quedo aplicado.")


# --- 1. Preparar el nuevo contenido de cada modulo (insertar register_tool) ---
module_new_src = {}
for module, entries in by_module.items():
    module_path = f"{module}.py"
    with open(module_path) as f:
        src = f.read()
    addition = "\n".join(e["register_block"] for e in entries)
    module_new_src[module_path] = src.rstrip("\n") + "\n" + addition + "\n"

# --- 2. Borrar de server.py: todos los tools_span + elif_span ---
spans_to_delete = []
for entry in plan:
    spans_to_delete.append(("tools", tuple(entry["tools_span"]), entry["tool_name"]))
    spans_to_delete.append(("elif", tuple(entry["elif_span"]), entry["tool_name"]))
spans_to_delete.sort(key=lambda x: x[1][0], reverse=True)

new_server = server_content
comma_pattern = re.compile(r'\s*,')

for kind, (start, end), tool_name in spans_to_delete:
    if start is None:
        print(f"AVISO: sin span de tipo {kind} para {tool_name}, se salta -- revisar a mano")
        continue
    seg_start, seg_end = start, end
    if kind == "tools":
        m = comma_pattern.match(new_server[end:end + 50])
        if m:
            seg_end = end + m.end()
        else:
            before = new_server[max(0, start - 50):start]
            m2 = re.search(r',\s*$', before)
            if m2:
                seg_start = start - (len(before) - m2.start())
    new_server = new_server[:seg_start] + new_server[seg_end:]

# --- 3. Imports silenciosos, evaluado sobre new_server YA con los elif borrados ---
silent_candidates = []
for module in by_module:
    pattern = re.compile(rf'\b{re.escape(module)}\.\w+')
    if not pattern.search(new_server):
        silent_candidates.append(module)

import_pattern = re.compile(r'^import (\w+)\s*(?:#.*)?$', re.MULTILINE)


def make_silent(m):
    mod = m.group(1)
    if mod in silent_candidates:
        return f"import {mod}  # auto-registra via tool_registry, no requiere mas ediciones"
    return m.group(0)


new_server = import_pattern.sub(make_silent, new_server)

if DRY_RUN:
    print(f"[DRY] modulos a modificar: {sorted(by_module)}")
    print(f"[DRY] spans a borrar en server.py: {len(spans_to_delete)} "
          f"({len(plan)} tools x 2)")
    print(f"[DRY] imports que pasarian a forma silenciosa: {silent_candidates}")
    print(f"[DRY] server.py: {len(server_content)} -> {len(new_server)} caracteres")
    for module, new_src in module_new_src.items():
        print(f"[DRY] {module}: +{len(new_src) - len(open(module).read())} caracteres")
    sys.exit(0)

# --- 4. Aplicar de verdad, con backup de TODO antes de escribir nada ---
backup("server.py")
for module_path in module_new_src:
    backup(module_path)

with open("server.py", "w") as f:
    f.write(new_server)
for module_path, new_src in module_new_src.items():
    with open(module_path, "w") as f:
        f.write(new_src)

# --- 5. Validar sintaxis de TODO lo tocado; si algo falla, rollback total ---
broken = []
for path in ["server.py"] + list(module_new_src.keys()):
    try:
        ast.parse(open(path).read())
    except SyntaxError as e:
        broken.append((path, str(e)))

if broken:
    print("ABORTO: los siguientes archivos quedaron con sintaxis invalida tras aplicar:")
    for path, err in broken:
        print(f"  {path}: {err}")
    restore_all()
    sys.exit(1)

print(f"Aplicado OK. {len(plan)} tools migradas a register_tool().")
print(f"Backups: {', '.join(bak for _, bak in backups_made)}")
print(f"Imports pasados a forma silenciosa: {silent_candidates}")
print("\nSiguiente paso recomendado: correr el servidor, pedir tools/list y")
print("confirmar que los 46 aparecen con su schema rico, despues correr tu")
print("suite de validacion pre-push antes de git add / commit.")
