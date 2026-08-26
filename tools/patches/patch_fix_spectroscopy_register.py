#!/usr/bin/env python3
"""
Patch: corrige el bloque de registro de tools/spectroscopy_tool.py

Bugs corregidos:
1. La llamada a register_tool() vivía dentro de una función _register()
   que solo se invocaba bajo `if __name__ == '__main__':` -> nunca se
   ejecutaba al importar el modulo desde server.py, asi que la tool
   jamas quedaba en tool_registry.REGISTRY en uso normal.
2. La firma usada era register_tool(TOOL_NAME, run, modes=TOOL_MODES),
   que no coincide con la firma real:
       register_tool(name, schema, handler)
   Se corrige para pasar TOOL_SCHEMA como segundo argumento y run como
   handler (run ya tiene la firma correcta: recibe el dict `arguments`
   y devuelve un dict).

Uso:
    python3 patch_fix_spectroscopy_register.py --file /path/a/tools/spectroscopy_tool.py
"""
import argparse
import ast
import re
import shutil
import sys
import time

# Tolerante a lineas en blanco extra entre el register_tool y el if __main__
OLD_BLOCK_RE = re.compile(
    r"def _register\(\):\n"
    r'    """Registra la herramienta en tool_registry\."""\n'
    r"    from tool_registry import register_tool\n"
    r"    register_tool\(TOOL_NAME, run, modes=TOOL_MODES\)\n"
    r"\s*\n*"
    r"if __name__ == '__main__':\n"
    r"    _register\(\)\n?"
)

NEW_BLOCK = '''try:
    from tool_registry import register_tool
    register_tool(TOOL_NAME, TOOL_SCHEMA, run)
except ImportError:
    pass

if __name__ == '__main__':
    import json
    print(json.dumps(run_self_test(), indent=2, default=str))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="Ruta a tools/spectroscopy_tool.py")
    args = parser.parse_args()

    path = args.file
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    checks = []

    # Check 1: el bloque viejo existe exactamente una vez
    matches = OLD_BLOCK_RE.findall(content)
    count_old = len(matches)
    checks.append(("bloque_viejo_encontrado_una_vez", count_old == 1))
    if count_old != 1:
        print(f"[ABORTA] OLD_BLOCK_RE matchea {count_old} veces (se esperaba 1). "
              f"No se modifica nada.")
        for name, ok in checks:
            print(f"  [{'OK' if ok else 'FAIL'}] {name}")
        sys.exit(1)

    # Backup automatico
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup_path = f"{path}.bak-{ts}"
    shutil.copy2(path, backup_path)
    checks.append(("backup_creado", True))
    print(f"Backup: {backup_path}")

    # Aplicar patch
    new_content = OLD_BLOCK_RE.sub(NEW_BLOCK, content, count=1)
    checks.append(("contenido_cambio", new_content != content))

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)

    # Compile check
    try:
        ast.parse(new_content)
        checks.append(("compile_ok", True))
    except SyntaxError as e:
        checks.append(("compile_ok", False))
        print(f"[ERROR] SyntaxError tras el patch: {e}")
        print(f"Restaurando desde backup...")
        shutil.copy2(backup_path, path)

    # Verificaciones puntuales sobre el nuevo contenido
    checks.append(("ya_no_tiene_modes_kwarg", "modes=TOOL_MODES" not in new_content))
    checks.append(("nueva_llamada_presente",
                    "register_tool(TOOL_NAME, TOOL_SCHEMA, run)" in new_content))
    checks.append(("try_except_importerror_presente",
                    "except ImportError:" in new_content))
    checks.append(("main_usa_run_self_test",
                    "run_self_test()" in new_content.split("if __name__")[-1]))

    print("\n--- REPORTE ---")
    all_ok = True
    for name, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")
        all_ok = all_ok and ok

    print(f"\nRESULTADO: {'TODOS LOS CHECKS OK' if all_ok else 'HAY CHECKS FALLIDOS -- revisar'}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
