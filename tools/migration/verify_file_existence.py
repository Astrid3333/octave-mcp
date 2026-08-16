#!/usr/bin/env python3
import re
import os

with open("server.py") as f:
    content = f.read()

import_pattern = re.compile(r'^from (\w+) import (.+)$', re.MULTILINE)
modules = set()
for m in import_pattern.finditer(content):
    modules.add(m.group(1))

missing = []
found = []
for mod in sorted(modules):
    path = f"{mod}.py"
    if os.path.exists(path):
        found.append(mod)
    else:
        missing.append(mod)

print(f"=== {len(found)} modulos con archivo .py confirmado ===")
print(f"=== {len(missing)} modulos SIN archivo .py correspondiente (investigar) ===")
for mod in missing:
    print(f"  - {mod}.py NO EXISTE")

with open("file_existence_report.txt", "w") as f:
    f.write(f"CONFIRMADOS ({len(found)}):\n")
    for mod in found:
        f.write(f"{mod}.py\n")
    f.write(f"\nFALTANTES ({len(missing)}):\n")
    for mod in missing:
        f.write(f"{mod}.py\n")

print("\nReporte guardado en file_existence_report.txt")
