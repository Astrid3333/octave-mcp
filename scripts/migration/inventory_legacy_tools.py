#!/usr/bin/env python3
import re

with open("server.py") as f:
    content = f.read()
lines = content.splitlines(keepends=True)

# 1) imports legacy: from X_tool import compute_Y[, compute_Z...], Y_SCHEMA[, Z_SCHEMA...]
import_pattern = re.compile(r'^from (\w+) import (.+)$', re.MULTILINE)
legacy_imports = []
for m in import_pattern.finditer(content):
    module, symbols = m.group(1), m.group(2)
    if 'SCHEMA' in symbols:
        legacy_imports.append((module, [s.strip() for s in symbols.split(',')]))

print(f"=== {len(legacy_imports)} imports legacy encontrados ===\n")

# 2) bloques elif del dispatcher: capturar CADA bloque completo (elif...hasta el
#    siguiente elif/else al mismo nivel de indentacion), no solo las primeras 2 lineas
elif_pattern = re.compile(
    r'( {16}elif tool_name == "(\w+)":\n(?:(?! {16}elif| {16}else).*\n)*)',
)
elif_blocks = elif_pattern.findall(content)
print(f"=== {len(elif_blocks)} bloques elif encontrados en el dispatcher ===\n")

tool_names_in_dispatcher = {name for _, name in elif_blocks}
tool_names_in_registry_imports = set()

# nombres de tool que YA estan en el patron nuevo (import mudo con comentario)
new_pattern = re.compile(r'^import (\w+)  # auto-registra', re.MULTILINE)
already_migrated = set(new_pattern.findall(content))

print(f"=== {len(already_migrated)} tools ya migrados (import mudo) ===\n")

# tools legacy pendientes = los que aparecen en el dispatcher pero no en already_migrated
pending = sorted(tool_names_in_dispatcher - already_migrated)
print(f"=== {len(pending)} tools LEGACY PENDIENTES de migrar ===")
for name in pending:
    print(f"  - {name}")

# flag: modulos con mas de un schema/compute (requieren cuidado extra)
multi = [(mod, syms) for mod, syms in legacy_imports if sum('SCHEMA' in s for s in syms) > 1]
print(f"\n=== {len(multi)} MODULOS CON MULTIPLES TOOLS (requieren revision manual) ===")
for mod, syms in multi:
    print(f"  - {mod}: {syms}")

with open("legacy_inventory_report.txt", "w") as f:
    f.write(f"Pendientes ({len(pending)}):\n")
    for name in pending:
        f.write(f"{name}\n")
    f.write(f"\nMultiples ({len(multi)}):\n")
    for mod, syms in multi:
        f.write(f"{mod}: {syms}\n")

print("\nReporte guardado en legacy_inventory_report.txt")
