#!/usr/bin/env python3
"""
patch_add_dict_guard_validation_report.py

Guard defensivo en el reporte final de run_all_validations.py: si
"parsed" no es un dict (por ej. una tool que devuelve validate como
string plano, o un futuro caso de doble-encoding como el que tuvo
math_philosophy_history), se clasifica en errored() con motivo
explicito en vez de crashear con AttributeError.

Uso:
  python3 patch_add_dict_guard_validation_report.py --dry-run
  python3 patch_add_dict_guard_validation_report.py
"""
import shutil
import sys
from pathlib import Path

DRY = "--dry-run" in sys.argv
TARGET = Path("run_all_validations.py")

src = TARGET.read_text(encoding="utf-8")

old = '''        vp = None
        for _field in VALIDATION_FIELD_ALIASES:
            if _field in parsed:
                vp = parsed.get(_field)
                break
        if vp is True:
            passed.append((name, parsed.get("checks")))'''

new = '''        if not isinstance(parsed, dict):
            errored.append((name, f"validate no estructurado (devolvio {type(parsed).__name__}, no dict)"))
            continue

        vp = None
        for _field in VALIDATION_FIELD_ALIASES:
            if _field in parsed:
                vp = parsed.get(_field)
                break
        if vp is True:
            passed.append((name, parsed.get("checks")))'''

n = src.count(old)
if n != 1:
    print(f"ABORTADO -- anchor matcheo {n} veces, se esperaba 1")
    sys.exit(1)

print("OK -- anchor encontrado 1 vez")

if DRY:
    print("\n--dry-run: no escribi nada. Corre sin esa flag para aplicar.")
    sys.exit(0)

shutil.copy(TARGET, str(TARGET) + ".bak")
TARGET.write_text(src.replace(old, new, 1), encoding="utf-8")
print(f"Aplicado. Backup en {TARGET}.bak")
