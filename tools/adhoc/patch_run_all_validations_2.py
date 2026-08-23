#!/usr/bin/env python3
"""
patch_run_all_validations_2.py

Segundo patch sobre run_all_validations.py (requiere que
patch_run_all_validations.py ya haya corrido antes -- este parte de un
ALTERNATE_VALIDATE_MODE ya existente).

Agrega 4 tools que SI aceptan mode="validate" y responden con un
autochequeo real (confirmado a mano: plague_sir devuelve {'ok': True,
...}), pero cuyo inputSchema no declara "validate" en el enum de mode,
por lo que el chequeo de elegibilidad las descartaba antes de siquiera
intentar la llamada. Se mapean a si mismas ("validate" -> "validate")
solo para saltar ese chequeo de enum.

Uso:
    python3 patch_run_all_validations_2.py
"""

import shutil
import subprocess
import sys
import time

TARGET = "run_all_validations.py"


def main():
    backup_name = f"{TARGET}.bak.{int(time.time())}"
    shutil.copy2(TARGET, backup_name)
    print(f"OK: backup creado en {backup_name}")

    with open(TARGET, "r", encoding="utf-8") as f:
        text = f.read()

    old = '''ALTERNATE_VALIDATE_MODE = {
    "tritbraid": "validate_physics",
    "scalar_field_cosmology_tool": "self_test",
    "vacuum_energy_density_tool": "self_test",
    "quantum_cosmology_tool": "self_test",
    "cosmological_mcmc_tool": "mock_recovery",
}'''

    new = '''ALTERNATE_VALIDATE_MODE = {
    "tritbraid": "validate_physics",
    "scalar_field_cosmology_tool": "self_test",
    "vacuum_energy_density_tool": "self_test",
    "quantum_cosmology_tool": "self_test",
    "cosmological_mcmc_tool": "mock_recovery",
    # Estas 4 SI aceptan mode="validate" y responden con un autochequeo
    # real (via el campo "ok", ver VALIDATION_FIELD_ALIASES) -- pero su
    # inputSchema no declara "validate" en el enum de mode, asi que el
    # chequeo automatico normal las descartaba antes de intentar nada.
    # Se mapean a si mismas para saltar solo el chequeo de enum.
    "plague_sir": "validate",
    "settlement_clusters": "validate",
    "historical_extractor": "validate",
    "abstract_algebra": "validate",
}'''

    count = text.count(old)
    if count != 1:
        print(f"ERROR: no se encontro el bloque OLD exacto "
              f"(encontrado {count} veces, se esperaba 1). Abortando sin tocar nada.")
        sys.exit(1)

    text = text.replace(old, new, 1)

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(text)

    result = subprocess.run(
        [sys.executable, "-m", "py_compile", TARGET],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("ERROR: el archivo parcheado no compila. Restaurando backup.")
        print(result.stderr)
        shutil.copy2(backup_name, TARGET)
        sys.exit(1)

    print("OK: patch aplicado y sintaxis valida.")


if __name__ == "__main__":
    main()
