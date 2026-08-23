#!/usr/bin/env python3
"""
patch_run_all_validations_3.py

Tercer patch sobre run_all_validations.py (requiere que los dos patches
anteriores ya hayan corrido).

plague_sir, settlement_clusters, historical_extractor y abstract_algebra
se registran via `lambda args: compute_X(**args)` con firma plana
(mode, text_data=None, preset=None, ...) -- no aceptan un kwarg "params"
ni tienen **kwargs. build_requests siempre mandaba {"mode": ..., "params": {}}
para toda tool evaluada, lo que rompia estas 4 con
"got an unexpected keyword argument 'params'".

Se agrega un set explicito de tools con firma plana, y se omite la
clave "params" del payload solo para esas.

Uso:
    python3 patch_run_all_validations_3.py
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

    # --- Bloque 1: declarar el set de tools con firma plana ---
    old1 = '''    "plague_sir": "validate",
    "settlement_clusters": "validate",
    "historical_extractor": "validate",
    "abstract_algebra": "validate",
}'''

    new1 = '''    "plague_sir": "validate",
    "settlement_clusters": "validate",
    "historical_extractor": "validate",
    "abstract_algebra": "validate",
}

# Tools registradas via `lambda args: compute_X(**args)` con firma plana
# (mode, text_data=None, preset=None, ...) -- no aceptan un kwarg "params"
# ni tienen **kwargs, asi que el payload estandar {"mode": ..., "params": {}}
# les tira TypeError. Se omite "params" del payload solo para estas.
FLAT_SIGNATURE_TOOLS = {
    "plague_sir",
    "settlement_clusters",
    "historical_extractor",
    "abstract_algebra",
}'''

    count1 = text.count(old1)
    if count1 != 1:
        print(f"ERROR bloque 1: encontrado {count1} veces, se esperaba 1. Abortando sin tocar nada.")
        sys.exit(1)
    text = text.replace(old1, new1, 1)

    # --- Bloque 2: usar FLAT_SIGNATURE_TOOLS al armar el payload ---
    old2 = '''        requests.append({
            "jsonrpc": "2.0",
            "id": next_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": {"mode": mode_to_call, "params": {}}},
        })'''

    new2 = '''        arguments = {"mode": mode_to_call}
        if name not in FLAT_SIGNATURE_TOOLS:
            arguments["params"] = {}
        requests.append({
            "jsonrpc": "2.0",
            "id": next_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })'''

    count2 = text.count(old2)
    if count2 != 1:
        print(f"ERROR bloque 2: encontrado {count2} veces, se esperaba 1. Abortando sin tocar nada.")
        sys.exit(1)
    text = text.replace(old2, new2, 1)

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
