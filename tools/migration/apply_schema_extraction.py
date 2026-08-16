#!/usr/bin/env python3
"""
Aplica la Fase 2: agrega las constantes _SCHEMA a cada modulo y actualiza
el import correspondiente en server.py.

Lee schema_extraction_plan.json (generado por build_schema_extraction_plan.py).
Agrupa las entradas por modulo, porque varios tools comparten un mismo
archivo (ej. los 6 workspace_* vienen todos de workspace_tool.py) -- si no
agrupamos, el segundo intento de tocar la misma linea de import fallaria
por no encontrar el texto original (ya modificado por el primero).

Para cada modulo:
  1. Backup timestampeado del .py del modulo y de server.py (una sola vez
     por corrida, no por entrada).
  2. Agrega al final del archivo del modulo tantas constantes _SCHEMA como
     tools tenga ese modulo en el plan, con pprint.pformat (True/False/None
     nativos de Python, no true/false/null de JSON).
  3. En server.py, busca la linea "from {modulo} import {simbolos...}" y le
     agrega, al final, todas las constantes _SCHEMA nuevas de ese modulo
     que todavia no esten ahi.
  4. Valida con ast.parse tanto el modulo como server.py despues de escribir.

No toca TOOLS[] ni las ramas elif del dispatcher -- eso se deja para
cuando estos 46 tools se re-evaluen con build_migration_plan.py y entren
al flujo normal de migracion a register_tool.
"""
import re
import ast
import json
import shutil
import pprint
import datetime
from collections import defaultdict

TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

with open("schema_extraction_plan.json") as f:
    data = json.load(f)
plan = data["plan"]

if not plan:
    print("Plan vacio, nada que hacer.")
    raise SystemExit(0)

# --- agrupar por modulo ---
by_module = defaultdict(list)
for entry in plan:
    by_module[entry["module"]].append(entry)

print(f"=== {len(plan)} tools en el plan, agrupados en {len(by_module)} modulos ===\n")

with open("server.py") as f:
    server_content = f.read()

# backup de server.py una sola vez
server_bak = f"server.py.bak_{TS}"
shutil.copy("server.py", server_bak)
print(f"backup server.py -> {server_bak}")

modules_touched = []
modules_failed = []

for module, entries in sorted(by_module.items()):
    module_path = f"{module}.py"

    # --- 1) backup del modulo ---
    mod_bak = f"{module_path}.bak_{TS}"
    shutil.copy(module_path, mod_bak)

    with open(module_path) as f:
        module_content = f.read()

    # --- 2) agregar constantes _SCHEMA al final del modulo ---
    new_constants = []
    for e in entries:
        const_name = e["schema_const_name"]
        if re.search(rf'^{const_name}\s*=', module_content, re.MULTILINE):
            # ya existe (corrida repetida) -- no duplicar
            continue
        schema_repr = pprint.pformat(e["schema"], indent=4, width=100, sort_dicts=False)
        new_constants.append(f"\n{const_name} = {schema_repr}\n")

    if new_constants:
        module_content_new = module_content.rstrip("\n") + "\n" + "".join(new_constants)
    else:
        module_content_new = module_content

    # --- 3) actualizar el import en server.py ---
    import_line_pattern = re.compile(rf'^from {re.escape(module)} import (.+)$', re.MULTILINE)
    m = import_line_pattern.search(server_content)
    if not m:
        modules_failed.append((module, "no se encontro la linea de import en server.py"))
        continue

    existing_symbols = [s.strip() for s in m.group(1).split(',')]
    const_names_needed = [e["schema_const_name"] for e in entries]
    to_add = [c for c in const_names_needed if c not in existing_symbols]

    if to_add:
        new_symbols_str = ", ".join(existing_symbols + to_add)
        new_import_line = f"from {module} import {new_symbols_str}"
        server_content = import_line_pattern.sub(new_import_line, server_content, count=1)

    # --- 4) validar y escribir ---
    try:
        ast.parse(module_content_new)
    except SyntaxError as e:
        modules_failed.append((module, f"ast.parse fallo en {module_path}: {e}"))
        continue

    with open(module_path, "w") as f:
        f.write(module_content_new)

    modules_touched.append(module)
    print(f"  OK: {module_path} (+{len(new_constants)} constantes) / import en server.py actualizado (+{len(to_add)} simbolos)")

# validar server.py completo al final
try:
    ast.parse(server_content)
except SyntaxError as e:
    print(f"\nERROR CRITICO: server.py no parsea despues de los cambios: {e}")
    print(f"Restaurando desde backup {server_bak}...")
    shutil.copy(server_bak, "server.py")
    raise SystemExit(1)

with open("server.py", "w") as f:
    f.write(server_content)

print(f"\n=== {len(modules_touched)} modulos actualizados OK ===")
if modules_failed:
    print(f"=== {len(modules_failed)} modulos con error ===")
    for mod, reason in modules_failed:
        print(f"  - {mod}: {reason}")

print("\nAhora corre: python3 -c \"import server\" && echo 'server.py importa OK'")
print("y despues volve a correr build_migration_plan.py -- estos tools deberian pasar a la categoria LIMPIA.")
