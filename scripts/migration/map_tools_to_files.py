#!/usr/bin/env python3
import re
from collections import defaultdict

with open("server.py") as f:
    content = f.read()

# Mapear cada import legacy a su modulo origen
import_pattern = re.compile(r'^from (\w+) import (.+)$', re.MULTILINE)
module_to_symbols = {}
for m in import_pattern.finditer(content):
    module, symbols = m.group(1), m.group(2)
    module_to_symbols[module] = [s.strip() for s in symbols.split(',')]

# Agrupar: cuantos schemas por modulo
multi_schema_modules = {
    mod: syms for mod, syms in module_to_symbols.items()
    if sum('SCHEMA' in s for s in syms) > 1
}

single_schema_modules = {
    mod: syms for mod, syms in module_to_symbols.items()
    if sum('SCHEMA' in s for s in syms) == 1
}

print(f"=== {len(single_schema_modules)} modulos con UN SOLO tool (migracion directa) ===\n")
print(f"=== {len(multi_schema_modules)} modulos con MULTIPLES tools (requieren mapeo manual) ===")
for mod, syms in multi_schema_modules.items():
    print(f"  {mod}: {syms}")

# Tambien: imports tipo "import X_tool" (sin from/import de simbolos) que
# ya podrian usar server_invoke_tool o un patron distinto (ver el modulo
# octave-mcp:server_invoke_tool con decenas de sub-tools por nombre)
bare_import_pattern = re.compile(r'^import (\w+)$', re.MULTILINE)
bare_imports = bare_import_pattern.findall(content)
print(f"\n=== {len(bare_imports)} imports 'bare' (sin desglose de simbolos) ===")
for name in bare_imports:
    print(f"  {name}")

with open("module_mapping_report.txt", "w") as f:
    f.write("SINGLE-SCHEMA (migracion directa, un register_tool por modulo):\n")
    for mod, syms in single_schema_modules.items():
        f.write(f"{mod}: {syms}\n")
    f.write(f"\nMULTI-SCHEMA (requieren un register_tool POR simbolo dentro del mismo archivo):\n")
    for mod, syms in multi_schema_modules.items():
        f.write(f"{mod}: {syms}\n")
    f.write(f"\nBARE IMPORTS (investigar patron de registro):\n")
    for name in bare_imports:
        f.write(f"{name}\n")

print("\nReporte guardado en module_mapping_report.txt")
