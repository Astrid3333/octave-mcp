#!/usr/bin/env python3
"""
Patch: actualiza README.md de octave-mcp con el conteo real de tools
y agrega una seccion documentando acoustics_tool y electromagnetic_tool.

Mismo patron que patch_update_readme.py (usado en mcp-octave-real).

Uso (dentro de ~/octave-mcp/):
    python3 patch_update_readme_octave_mcp.py
"""

import ast
import re
import shutil
import time

SERVER_PATH = "server.py"
README_PATH = "README.md"

# --- 1. Contar tools reales via AST (mismo criterio que el commit "conteo real de tools (119)") ---

with open(SERVER_PATH, "r") as f:
    server_src = f.read()

tree = ast.parse(server_src)

# Busca todas las listas/diccionarios que terminen en "_SCHEMA" agregados a la lista global de schemas,
# contando las apariciones de "elif tool_name ==" en el dispatcher como fuente de verdad,
# ya que ese es el conteo que se uso historicamente en este repo.
dispatch_count = len(re.findall(r"elif tool_name == ", server_src))
# Fallback / cruce: cuenta tambien nombres unicos de schema (*_SCHEMA)
schema_names = set(re.findall(r"(\w+_SCHEMA)\s*=", server_src))

print(f"Tools segun dispatch (elif tool_name ==): {dispatch_count}")
print(f"Schemas unicos (*_SCHEMA) encontrados: {len(schema_names)}")

if dispatch_count == 0:
    raise SystemExit("No se encontraron ramas de dispatch 'elif tool_name ==' — revisa el patron antes de continuar.")

new_count = dispatch_count

# --- 2. Backup y lectura del README ---

with open(README_PATH, "r") as f:
    readme = f.read()

timestamp = time.strftime("%Y%m%d_%H%M%S")
backup_path = f"{README_PATH}.bak_{timestamp}"
shutil.copy(README_PATH, backup_path)
print(f"Backup: {backup_path}")

# --- 3. Reemplazar el conteo viejo (ej. "119 tools", "119 herramientas") por el nuevo ---

old_count_pattern = re.compile(r"(\d+)\s+(tools|herramientas)")
matches = old_count_pattern.findall(readme)
if matches:
    old_counts_found = sorted(set(int(m[0]) for m in matches))
    print(f"Conteos viejos detectados en README: {old_counts_found}")
else:
    print("ADVERTENCIA: no se encontro ningun patron '<numero> tools/herramientas' en el README.")

def replace_count(match):
    return f"{new_count} {match.group(2)}"

readme_updated = old_count_pattern.sub(replace_count, readme)

# --- 4. Agregar seccion nueva de acustica/electromagnetismo si no existe ya ---

NEW_SECTION_HEADER = "## Acustica y Electromagnetismo"

if NEW_SECTION_HEADER not in readme_updated and "Acustica y Electromagnetismo" not in readme_updated:
    new_section = f"""

{NEW_SECTION_HEADER}

- **acoustics_tool**: ondas de presion 1D (`pressure_wave_1d`), modos propios de sala
  (`room_modes`), tiempo de reverberacion via formula de Sabine (`reverberation_sabine`).
  Validado contra solucion analitica y contra la relacion esperada RT60(reflectante) >
  RT60(absorbente).
- **electromagnetic_tool**: propagacion de campo E en 1D via FDTD leapfrog con bordes PEC
  (`wave_1d`); cristal fotonico 1D por matriz de transferencia, condicion de Bloch y deteccion
  de band gaps (`photonic_bandgap`). Validado end-to-end, incluyendo un apilado de cuarto de
  onda con el gap centrado exactamente en la frecuencia de diseno f0.
"""
    readme_updated = readme_updated.rstrip("\n") + new_section + "\n"
    print("Seccion 'Acustica y Electromagnetismo' agregada al README.")
else:
    print("La seccion de acustica/electromagnetismo ya existia — no se duplico.")

with open(README_PATH, "w") as f:
    f.write(readme_updated)

print(f"README.md actualizado: conteo -> {new_count} tools.")
print("Revisa el diff (git diff README.md) antes de commitear.")
