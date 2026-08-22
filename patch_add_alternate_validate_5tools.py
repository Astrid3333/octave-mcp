#!/usr/bin/env python3
"""
patch_add_alternate_validate_5tools.py

Wirea 5 tools (levant, ancient_calculator, originarios,
persistent_homology: preset=validate; math_philosophy_history:
topic=validate) al harness run_all_validations.py. Las 5 usan un
parametro distinto de "mode", asi que no alcanza con
ALTERNATE_VALIDATE_MODE solo -- se agrega un dict nuevo
ALTERNATE_VALIDATE_PARAM_NAME que dice que parametro usar en vez de
"mode", y se modifican las 2 construcciones de `arguments` (una por
chunk paralelo) para usarlo. Tambien se agregan las 5 a
FLAT_SIGNATURE_TOOLS porque sus handlers son lambda args:
compute_x(**args), firma plana sin envoltorio "params".

No se toca ningun archivo de las 5 tools, solo run_all_validations.py.

Uso:
  python3 patch_add_alternate_validate_5tools.py --dry-run
  python3 patch_add_alternate_validate_5tools.py
"""
import shutil
import sys
from pathlib import Path

DRY = "--dry-run" in sys.argv
F = Path("run_all_validations.py")
src = F.read_text()


def report(ok, msg):
    print(("OK -- " if ok else "FALLO -- ") + msg)
    return ok


all_ok = True

# 1) ALTERNATE_VALIDATE_MODE: agregar las 5 entradas
anchor_mode = '    "workspace_validate": "validate",\n'
all_ok &= report(anchor_mode in src, "anchor 'workspace_validate' en ALTERNATE_VALIDATE_MODE encontrado")

new_mode_lines = (
    anchor_mode
    + '    "levant": "validate",\n'
    + '    "ancient_calculator": "validate",\n'
    + '    "originarios": "validate",\n'
    + '    "persistent_homology": "validate",\n'
    + '    "math_philosophy_history": "validate",\n'
)

# 2) FLAT_SIGNATURE_TOOLS: agregar las 5 + insertar el dict nuevo justo despues
old_flat = '    "plot_workspace_run", "octave_run", "octave_eval_expr", "octave_run_script", "octave_version",}'
all_ok &= report(old_flat in src, "anchor de FLAT_SIGNATURE_TOOLS (con las 4 de octave) encontrado")

new_flat = (
    '    "plot_workspace_run", "octave_run", "octave_eval_expr", "octave_run_script", "octave_version",\n'
    '    "levant", "ancient_calculator", "originarios", "persistent_homology", "math_philosophy_history",}\n\n'
    '# Tools cuyo parametro real de invocacion no es "mode" (preset, topic, etc.)\n'
    '# -- ver ALTERNATE_VALIDATE_MODE para el valor a pasar en ese parametro.\n'
    'ALTERNATE_VALIDATE_PARAM_NAME = {\n'
    '    "levant": "preset",\n'
    '    "ancient_calculator": "preset",\n'
    '    "originarios": "preset",\n'
    '    "persistent_homology": "preset",\n'
    '    "math_philosophy_history": "topic",\n'
    '}'
)

# 3) arguments = {"mode": mode_to_call} -- aparece 2 veces (build_requests + chunk), mismo fix en ambas
old_args = '        arguments = {"mode": mode_to_call}'
count_args = src.count(old_args)
all_ok &= report(count_args == 2, f"anchor de 'arguments = {{...}}' encontrado 2 veces (encontrado {count_args})")

new_args = (
    '        param_name = ALTERNATE_VALIDATE_PARAM_NAME.get(name, "mode")\n'
    '        arguments = {param_name: mode_to_call}'
)

if all_ok and not DRY:
    src = src.replace(anchor_mode, new_mode_lines)
    src = src.replace(old_flat, new_flat)
    src = src.replace(old_args, new_args)
    shutil.copy(F, F.with_suffix(".py.bak"))
    print(f"  (backup en {F.with_suffix('.py.bak')})")
    F.write_text(src)

print()
if DRY:
    print("--dry-run: no escribi nada. Corre sin esa flag para aplicar.")
else:
    print("Aplicado (si los 3 anchors dieron OK).")
