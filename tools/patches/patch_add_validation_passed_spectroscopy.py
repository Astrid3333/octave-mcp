#!/usr/bin/env python3
"""
Patch: agrega el campo 'validation_passed' al dict que devuelve
run_self_test() en tools/spectroscopy_tool.py.

run_all_validations.py acepta varios nombres de campo alternativos
(VALIDATION_FIELD_ALIASES: validation_passed, all_passed, ok, all_pass,
todos_correctos, all_params_within_2sigma) para saber si el autochequeo
paso. run_self_test() solo devolvia 'status': 'PASSED'/'FAILED', que no
esta en esa lista -> el harness marcaba [ERROR] "respuesta valida pero
sin campo 'validation_passed'" pese a que los 11 tests internos pasaban.

Fix: agregar 'validation_passed': tests_passed == tests_total al mismo
dict de retorno, sin tocar ninguno de los 11 tests existentes ni la
logica de conteo.

Uso:
    python3 patch_add_validation_passed_spectroscopy.py --file /path/a/tools/spectroscopy_tool.py
"""
import argparse
import ast
import shutil
import sys
import time

OLD_BLOCK = """    return {
        'tool': TOOL_NAME,
        'tests_passed': tests_passed,
        'tests_total': tests_total,
        'errors': errors,
        'status': 'PASSED' if tests_passed == tests_total else 'FAILED',
    }"""

NEW_BLOCK = """    return {
        'tool': TOOL_NAME,
        'tests_passed': tests_passed,
        'tests_total': tests_total,
        'errors': errors,
        'status': 'PASSED' if tests_passed == tests_total else 'FAILED',
        'validation_passed': tests_passed == tests_total,
    }"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="Ruta a tools/spectroscopy_tool.py")
    args = parser.parse_args()

    path = args.file
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    checks = []

    count_old = content.count(OLD_BLOCK)
    checks.append(("bloque_viejo_encontrado_una_vez", count_old == 1))
    if count_old != 1:
        print(f"[ABORTA] OLD_BLOCK aparece {count_old} veces (se esperaba 1). "
              f"No se modifica nada.")
        for name, ok in checks:
            print(f"  [{'OK' if ok else 'FAIL'}] {name}")
        sys.exit(1)

    ts = time.strftime("%Y%m%d-%H%M%S")
    backup_path = f"{path}.bak-{ts}"
    shutil.copy2(path, backup_path)
    checks.append(("backup_creado", True))
    print(f"Backup: {backup_path}")

    new_content = content.replace(OLD_BLOCK, NEW_BLOCK)
    checks.append(("contenido_cambio", new_content != content))

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)

    try:
        ast.parse(new_content)
        checks.append(("compile_ok", True))
    except SyntaxError as e:
        checks.append(("compile_ok", False))
        print(f"[ERROR] SyntaxError tras el patch: {e}")
        print("Restaurando desde backup...")
        shutil.copy2(backup_path, path)

    checks.append(("campo_validation_passed_presente",
                    "'validation_passed': tests_passed == tests_total" in new_content))
    # Confirmar que los 11 tests originales siguen intactos (conteo de tests_total += 1)
    checks.append(("los_11_tests_originales_intactos",
                    new_content.count("tests_total += 1") == content.count("tests_total += 1")))

    print("\n--- REPORTE ---")
    all_ok = True
    for name, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")
        all_ok = all_ok and ok

    print(f"\nRESULTADO: {'TODOS LOS CHECKS OK' if all_ok else 'HAY CHECKS FALLIDOS -- revisar'}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
