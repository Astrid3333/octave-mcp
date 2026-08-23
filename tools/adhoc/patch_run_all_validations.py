#!/usr/bin/env python3
"""
patch_run_all_validations.py

Amplia run_all_validations.py en dos frentes, sin tocar ninguna tool
individual:

1) ALTERNATE_VALIDATE_MODE: tools cuyo autochequeo interno es real pero
   vive bajo otro nombre de modo ("self_test", "validate_physics",
   "mock_recovery") en vez de "validate". Auditado a mano el 2026-08-18
   contra el repo real -- cada una fue invocada y confirmada como
   autochequeo funcional, no un modo de computo cualquiera.

2) VALIDATION_FIELD_ALIASES: amplia el reconocimiento de campo de
   resultado mas alla de "validation_passed"/"all_passed" para incluir
   "ok", "all_pass", "todos_correctos" y "all_params_within_2sigma"
   (este ultimo especifico de cosmological_mcmc_tool, cuyo autochequeo
   es una recuperacion de parametros conocidos desde datos sinteticos,
   no una lista de checks booleanos).

Uso:
    python3 patch_run_all_validations.py
"""

import shutil
import subprocess
import sys
import time

TARGET = "run_all_validations.py"


def read():
    with open(TARGET, "r", encoding="utf-8") as f:
        return f.read()


def write(text):
    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(text)


def apply_patch(text, old, new, label):
    count = text.count(old)
    if count != 1:
        print(f"ERROR: no se encontro el bloque OLD exacto para '{label}' "
              f"(encontrado {count} veces, se esperaba 1). Abortando sin tocar nada.")
        sys.exit(1)
    return text.replace(old, new, 1)


def main():
    backup_name = f"{TARGET}.bak.{int(time.time())}"
    shutil.copy2(TARGET, backup_name)
    print(f"OK: backup creado en {backup_name}")

    text = read()

    # --- Bloque 1: agregar ALTERNATE_VALIDATE_MODE + VALIDATION_FIELD_ALIASES ---
    old1 = '''KNOWN_NON_STANDARD_VALIDATE = {
    # mode=validate ejecuta un pipeline default de pasos (compute_gradient_hessian
    # + compute_math_error_analysis encadenados) y devuelve su trace/resultados,
    # no un reporte de autochequeo con validation_passed/all_passed.
    "run_math_pipeline": "mode=validate ejecuta un pipeline default, no un autochequeo",
}'''

    new1 = '''KNOWN_NON_STANDARD_VALIDATE = {
    # mode=validate ejecuta un pipeline default de pasos (compute_gradient_hessian
    # + compute_math_error_analysis encadenados) y devuelve su trace/resultados,
    # no un reporte de autochequeo con validation_passed/all_passed.
    "run_math_pipeline": "mode=validate ejecuta un pipeline default, no un autochequeo",
}

# Tools cuyo autochequeo interno existe y es funcionalmente equivalente a
# mode=validate, pero vive bajo otro nombre de modo (nunca se estandarizo
# el nombre "validate" en estas). Auditadas a mano el 2026-08-18: cada una
# fue invocada y confirmada como autochequeo real, no un modo de computo.
ALTERNATE_VALIDATE_MODE = {
    "tritbraid": "validate_physics",
    "scalar_field_cosmology_tool": "self_test",
    "vacuum_energy_density_tool": "self_test",
    "quantum_cosmology_tool": "self_test",
    "cosmological_mcmc_tool": "mock_recovery",
}

# Nombres de campo alternativos para "el autochequeo paso" -- distintas
# tools nunca convergieron en una sola convencion. all_params_within_2sigma
# es especifico de cosmological_mcmc_tool (su autochequeo es una
# recuperacion de parametros conocidos desde datos sinteticos, no una
# lista de checks booleanos).
VALIDATION_FIELD_ALIASES = (
    "validation_passed", "all_passed", "ok", "all_pass",
    "todos_correctos", "all_params_within_2sigma",
)'''

    text = apply_patch(text, old1, new1, "agregar ALTERNATE_VALIDATE_MODE / VALIDATION_FIELD_ALIASES")

    # --- Bloque 2: usar ALTERNATE_VALIDATE_MODE en build_requests ---
    old2 = '''    for t in tools:
        name = t["name"]
        mode_prop = t.get("inputSchema", {}).get("properties", {}).get("mode", {})
        enum = mode_prop.get("enum")
        if enum is None or "validate" not in enum:
            skipped.append((name, "sin modo validate en el schema"))
            continue
        if name in KNOWN_NON_STANDARD_VALIDATE:
            skipped.append((name, KNOWN_NON_STANDARD_VALIDATE[name]))
            continue
        requests.append({
            "jsonrpc": "2.0",
            "id": next_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": {"mode": "validate", "params": {}}},
        })
        tool_id_map[next_id] = name
        next_id += 1

    return requests, tool_id_map, skipped'''

    new2 = '''    for t in tools:
        name = t["name"]
        mode_prop = t.get("inputSchema", {}).get("properties", {}).get("mode", {})
        enum = mode_prop.get("enum")
        mode_to_call = "validate"
        if enum is None or "validate" not in enum:
            if name in ALTERNATE_VALIDATE_MODE:
                mode_to_call = ALTERNATE_VALIDATE_MODE[name]
            else:
                skipped.append((name, "sin modo validate en el schema"))
                continue
        if name in KNOWN_NON_STANDARD_VALIDATE:
            skipped.append((name, KNOWN_NON_STANDARD_VALIDATE[name]))
            continue
        requests.append({
            "jsonrpc": "2.0",
            "id": next_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": {"mode": mode_to_call, "params": {}}},
        })
        tool_id_map[next_id] = name
        next_id += 1

    return requests, tool_id_map, skipped'''

    text = apply_patch(text, old2, new2, "usar ALTERNATE_VALIDATE_MODE en build_requests")

    # --- Bloque 3: ampliar reconocimiento de campo de resultado ---
    old3 = '''        # algunas tools usan "validation_passed", otras usan "all_passed"
        # para el mismo concepto -- se aceptan ambos nombres de campo.
        vp = parsed.get("validation_passed")
        if vp is None:
            vp = parsed.get("all_passed")
        if vp is True:'''

    new3 = '''        # algunas tools usan "validation_passed", otras usan "all_passed",
        # "ok", "all_pass", "todos_correctos", u otro campo especifico
        # (ver VALIDATION_FIELD_ALIASES) -- se aceptan todos como sinonimos.
        vp = None
        for _field in VALIDATION_FIELD_ALIASES:
            if _field in parsed:
                vp = parsed.get(_field)
                break
        if vp is True:'''

    text = apply_patch(text, old3, new3, "ampliar reconocimiento de campo de resultado")

    write(text)

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
