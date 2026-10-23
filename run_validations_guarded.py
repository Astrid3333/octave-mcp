#!/usr/bin/env python3
"""
run_validations_guarded.py

Wrapper NO invasivo sobre run_all_validations.py: no lo modifica ni
necesita conocer su codigo interno. Lo corre como subprocess, muestra
su output tal cual (streaming), y al final parsea el bloque RESUMEN
para decidir el exit code:

    exit 0  -> "PASSED" == total evaluadas Y no hay FAILED/ERROR
               Y ademas la bateria cross-check pasa (N/N PASS)
    exit 1  -> hay al menos un FAILED o ERROR, no se pudo parsear
               el resumen, o la bateria falla (fail-safe: ante la
               duda, se considera fallo)

Despues de un guard OK corre examples/multi_cas_crosscheck.py
(bateria multi-motor vs sympy) como segundo gate; su output tambien
se muestra tal cual.

Pensado para engancharse despues en un pre-push hook o en CI sin tener
que tocar run_all_validations.py, que puede seguir cambiando de forma
independiente.

Uso:
    .venv/bin/python run_validations_guarded.py
    echo "EXIT: $?"
"""
import os
import re
import subprocess
import sys

RESUMEN_FAILED_RE = re.compile(r"FAILED:\s+(\d+)")
RESUMEN_ERROR_RE = re.compile(r"ERROR:\s+(\d+)")
RESUMEN_PASSED_RE = re.compile(r"PASSED:\s+(\d+)")
RESUMEN_TOTAL_EVAL_RE = re.compile(r"Con modo validate \(evaluadas\):\s+(\d+)")
BATTERY_PASS_RE = re.compile(r"(\d+)/(\d+) PASS")

_HERE = os.path.dirname(os.path.abspath(__file__))
_VENV_PY = os.path.join(_HERE, ".venv", "bin", "python")


def _run_battery():
    py = _VENV_PY if os.path.exists(_VENV_PY) else sys.executable
    proc = subprocess.run(
        [py, os.path.join(_HERE, "examples", "multi_cas_crosscheck.py")],
        capture_output=True,
        text=True,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    m = BATTERY_PASS_RE.search(proc.stdout)
    if proc.returncode != 0 or not m or m.group(1) != m.group(2):
        got = m.group(0) if m else "sin resumen PASS"
        print(
            f"\nGUARD: FALLO en la bateria cross-check -- {got} "
            f"(exit {proc.returncode}).",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"\nGUARD: OK bateria cross-check {m.group(0)}.")


def main():
    proc = subprocess.run(
        [sys.executable, "run_all_validations.py"],
        capture_output=True,
        text=True,
    )
    # Mostramos el output tal cual lo hubiera visto corriendo el script solo.
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)

    combined = proc.stdout + "\n" + proc.stderr

    m_failed = RESUMEN_FAILED_RE.search(combined)
    m_error = RESUMEN_ERROR_RE.search(combined)
    m_passed = RESUMEN_PASSED_RE.search(combined)
    m_total = RESUMEN_TOTAL_EVAL_RE.search(combined)

    if not (m_failed and m_error and m_passed and m_total):
        print(
            "\nGUARD: no pude parsear el bloque RESUMEN de run_all_validations.py "
            "-- tratando como FALLO por seguridad (fail-safe).",
            file=sys.stderr,
        )
        sys.exit(1)

    n_failed = int(m_failed.group(1))
    n_error = int(m_error.group(1))
    n_passed = int(m_passed.group(1))
    n_total = int(m_total.group(1))

    ok = (n_failed == 0 and n_error == 0 and n_passed == n_total)

    if ok:
        print(f"\nGUARD: OK -- {n_passed}/{n_total} PASSED, 0 FAILED, 0 ERROR.")
        _run_battery()
        sys.exit(0)
    else:
        print(
            f"\nGUARD: FALLO -- {n_passed}/{n_total} PASSED, "
            f"{n_failed} FAILED, {n_error} ERROR.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
