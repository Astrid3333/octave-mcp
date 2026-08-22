#!/usr/bin/env python3
"""
patch_add_symbolic_check_statmech.py

Agrega un check symbolic (Octave pkg symbolic) a _validate() de
statmech_partition_tool.py: cruza el U de _qho (formula cerrada en
Python) contra -d(ln Z)/d(beta) calculado simbolicamente, en
beta=hbar=omega=1.

Si pkg symbolic no esta instalado (o octave_infra_tool no se puede
importar), el check se marca skipped=True y NO cuenta contra
all_passed -- decision de diseno: esta tool es pura Python/math, no
se le acopla una dependencia dura de Octave por un check extra.

Uso:
  python3 patch_add_symbolic_check_statmech.py --dry-run
  python3 patch_add_symbolic_check_statmech.py
"""
import shutil
import sys
from pathlib import Path

DRY = "--dry-run" in sys.argv
F = Path("statmech_partition_tool.py")
src = F.read_text()


def report(ok, msg):
    print(("OK -- " if ok else "FALLO -- ") + msg)
    return ok


anchor_def = "def _validate():\n    checks = []"
new_func = '''def _symbolic_check_qho_energy():
    """
    Cruza el U de _qho (formula cerrada en Python) contra la derivada
    simbolica de -d(ln Z)/d(beta) calculada por Octave (pkg symbolic),
    para beta=hbar=omega=1 (T=1, unidades naturales). Si el paquete
    symbolic no esta instalado, el check se marca skipped=True y no
    cuenta contra all_passed -- esta tool es pura Python/math y no se
    le acopla una dependencia dura de Octave por este check extra.
    """
    try:
        from octave_infra_tool import _run_octave
    except ImportError:
        return {"case": "qho U simbolico vs -d(lnZ)/dbeta (Octave symbolic)",
                "skipped": True, "ok": True,
                "detail": "no se pudo importar octave_infra_tool"}

    octave_code = (
        "pkg load symbolic\\n"
        "syms b h w\\n"
        "Z = exp(-b*h*w/2) / (1 - exp(-b*h*w));\\n"
        "U_expr = -diff(log(Z), b);\\n"
        "U_val = double(subs(U_expr, [b, h, w], [1.0, 1.0, 1.0]));\\n"
        "printf('%.15g\\\\n', U_val);\\n"
    )
    r = _run_octave(octave_code, timeout=30)
    if r["returncode"] != 0 or not r["stdout"]:
        return {"case": "qho U simbolico vs -d(lnZ)/dbeta (Octave symbolic)",
                "skipped": True, "ok": True,
                "detail": f"symbolic no disponible o fallo: {r['stderr'][:200]}"}
    try:
        symbolic_U = float(r["stdout"].strip().splitlines()[-1])
    except ValueError:
        return {"case": "qho U simbolico vs -d(lnZ)/dbeta (Octave symbolic)",
                "skipped": True, "ok": True,
                "detail": f"salida no parseable: {r['stdout'][:200]}"}

    python_U = _qho({"T": 1.0, "hbar": 1.0, "omega": 1.0, "kB": 1.0})["U"]
    ok = abs(symbolic_U - python_U) < 1e-6
    return {"case": "qho U simbolico vs -d(lnZ)/dbeta (Octave symbolic)",
            "expected": symbolic_U, "got": python_U, "ok": ok,
            "detail": f"symbolic={symbolic_U}, python={python_U}"}


def _validate():
    checks = []'''

ok1 = report(anchor_def in src, "anchor 'def _validate' encontrado")

old_return = 'return {"validate": True, "all_passed": all(c["ok"] for c in checks), "checks": checks}'
new_return = ('checks.append(_symbolic_check_qho_energy())\n'
              '    return {"validate": True, '
              '"all_passed": all(c["ok"] for c in checks if not c.get("skipped")), '
              '"checks": checks}')

ok2 = report(old_return in src, "anchor del return final encontrado")

if ok1 and ok2 and not DRY:
    src = src.replace(anchor_def, new_func)
    src = src.replace(old_return, new_return)
    shutil.copy(F, F.with_suffix(".py.bak"))
    print(f"  (backup en {F.with_suffix('.py.bak')})")
    F.write_text(src)

print()
if DRY:
    print("--dry-run: no escribi nada. Corre sin esa flag para aplicar.")
else:
    print("Aplicado (si los 2 anchors dieron OK).")
