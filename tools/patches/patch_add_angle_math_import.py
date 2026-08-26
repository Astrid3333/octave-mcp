#!/usr/bin/env python3
"""
Patch: agrega 'import angle_math_tool' a server.py.

angle_math_tool.py ya tenia su bug de registro corregido (register_tool
con firma correcta, ejecutado a nivel de modulo) pero nunca tuvo su
import agregado en server.py -> el modulo nunca se cargaba, por lo tanto
nunca se registraba, pese a que el propio archivo ya estaba bien.

Ancla: se inserta la linea justo despues de la linea existente
'import sustainable_sourcing_tool', que es un import simple del mismo
patron (import <nombre_archivo>) en el mismo bloque.

Uso:
    python3 patch_add_angle_math_import.py --file /path/a/server.py
"""
import argparse
import ast
import shutil
import sys
import time

ANCHOR = "import sustainable_sourcing_tool\n"
NEW_LINE = "import angle_math_tool\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="Ruta a server.py")
    args = parser.parse_args()
    path = args.file

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    checks = []

    checks.append(("ya_no_esta_importada", "import angle_math_tool" not in content))
    n_anchor = content.count(ANCHOR)
    checks.append(("ancla_encontrada_una_vez", n_anchor == 1))

    if n_anchor != 1 or "import angle_math_tool" in content:
        print(f"[ABORTA] ancla matches={n_anchor}, ya_importada={'import angle_math_tool' in content}. "
              f"No se modifica nada.")
        for name, ok in checks:
            print(f"  [{'OK' if ok else 'FAIL'}] {name}")
        sys.exit(1)

    ts = time.strftime("%Y%m%d-%H%M%S")
    backup_path = f"{path}.bak-{ts}"
    shutil.copy2(path, backup_path)
    checks.append(("backup_creado", True))
    print(f"Backup: {backup_path}")

    new_content = content.replace(ANCHOR, ANCHOR + NEW_LINE, 1)
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

    checks.append(("nueva_linea_presente", NEW_LINE.strip() in new_content))
    checks.append(("solo_una_linea_nueva", new_content.count("import angle_math_tool") == 1))

    print("\n--- REPORTE ---")
    all_ok = True
    for name, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")
        all_ok = all_ok and ok

    print(f"\nRESULTADO: {'TODOS LOS CHECKS OK' if all_ok else 'HAY CHECKS FALLIDOS -- revisar'}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
