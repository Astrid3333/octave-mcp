#!/usr/bin/env python3
"""
Patch combinado para tools que vinieron de documentos externos con dos
bugs identicos:

1. Registro roto: register_tool(TOOL_NAME, run, modes=TOOL_MODES) colgado
   bajo `if __name__ == '__main__':` -> nunca se ejecuta al importar el
   modulo desde server.py, la tool nunca queda en tool_registry.REGISTRY.
   Ademas la firma es incorrecta: la real es register_tool(name, schema,
   handler), no acepta kwarg modes=.

2. run_self_test() devuelve 'status': 'PASSED'/'FAILED' pero no el campo
   'validation_passed' que espera run_all_validations.py (via
   VALIDATION_FIELD_ALIASES) -> el harness marca [ERROR] pese a que los
   tests internos pasan.

Aplica ambos fixes sin tocar la logica de los tests existentes.

Uso:
    python3 patch_fix_registration_and_validation.py --file /path/a/tools/algun_tool.py
"""
import argparse
import ast
import re
import shutil
import sys
import time

# --- Fix 1: registro ---------------------------------------------------
OLD_REGISTER_RE = re.compile(
    r"def _register\(\):\n"
    r'    """Registra la herramienta en tool_registry\."""\n'
    r"    from tool_registry import register_tool\n"
    r"    register_tool\(TOOL_NAME, run, modes=TOOL_MODES\)\n"
    r"\s*\n*"
    r"if __name__ == '__main__':\n"
    r"    _register\(\)\n?"
)

NEW_REGISTER = '''try:
    from tool_registry import register_tool
    register_tool(TOOL_NAME, TOOL_SCHEMA, run)
except ImportError:
    pass

if __name__ == '__main__':
    import json
    print(json.dumps(run_self_test(), indent=2, default=str))
'''

# --- Fix 2: validation_passed -------------------------------------------
OLD_RETURN_RE = re.compile(
    r"return \{\n"
    r"        'tool': TOOL_NAME,\n"
    r"        'tests_passed': tests_passed,\n"
    r"        'tests_total': tests_total,\n"
    r"        'errors': errors,\n"
    r"        'status': 'PASSED' if tests_passed == tests_total else 'FAILED',\n"
    r"    \}"
)

NEW_RETURN = """return {
        'tool': TOOL_NAME,
        'tests_passed': tests_passed,
        'tests_total': tests_total,
        'errors': errors,
        'status': 'PASSED' if tests_passed == tests_total else 'FAILED',
        'validation_passed': tests_passed == tests_total,
    }"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    args = parser.parse_args()
    path = args.file

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    checks = []

    n_register = len(OLD_REGISTER_RE.findall(content))
    n_return = len(OLD_RETURN_RE.findall(content))
    checks.append(("bloque_registro_encontrado_una_vez", n_register == 1))
    checks.append(("bloque_return_encontrado_una_vez", n_return == 1))

    if n_register != 1 or n_return != 1:
        print(f"[ABORTA] registro matches={n_register}, return matches={n_return} "
              f"(se esperaba 1 y 1). No se modifica nada.")
        for name, ok in checks:
            print(f"  [{'OK' if ok else 'FAIL'}] {name}")
        sys.exit(1)

    ts = time.strftime("%Y%m%d-%H%M%S")
    backup_path = f"{path}.bak-{ts}"
    shutil.copy2(path, backup_path)
    checks.append(("backup_creado", True))
    print(f"Backup: {backup_path}")

    new_content = OLD_REGISTER_RE.sub(NEW_REGISTER, content, count=1)
    new_content = OLD_RETURN_RE.sub(NEW_RETURN, new_content, count=1)
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

    checks.append(("nueva_llamada_register_presente",
                    "register_tool(TOOL_NAME, TOOL_SCHEMA, run)" in new_content))
    checks.append(("try_except_importerror_presente",
                    "except ImportError:" in new_content))
    checks.append(("campo_validation_passed_presente",
                    "'validation_passed': tests_passed == tests_total" in new_content))
    checks.append(("num_tests_originales_intacto",
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
