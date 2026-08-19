#!/usr/bin/env python3
"""
run_validations_guarded.py

Wrapper NO invasivo sobre run_all_validations.py: no lo modifica ni
necesita conocer su codigo interno. Lo corre como subprocess, muestra
su output tal cual (streaming), y al final parsea el bloque RESUMEN
para decidir el exit code:

    exit 0  -> "PASSED" == total evaluadas Y no hay FAILED/ERROR
    exit 1  -> hay al menos un FAILED o ERROR, o no se pudo parsear
               el resumen (fail-safe: ante la duda, se considera fallo)

Pensado para engancharse despues en un pre-push hook o en CI sin tener
que tocar run_all_validations.py, que puede seguir cambiando de forma
independiente.

Uso:
    python3 run_validations_guarded.py
    echo "EXIT: $?"
"""
import re
import subprocess
import sys

RESUMEN_FAILED_RE = re.compile(r"FAILED:\s+(\d+)")
RESUMEN_ERROR_RE = re.compile(r"ERROR:\s+(\d+)")
RESUMEN_PASSED_RE = re.compile(r"PASSED:\s+(\d+)")
RESUMEN_TOTAL_EVAL_RE = re.compile(r"Con modo validate \(evaluadas\):\s+(\d+)")


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
