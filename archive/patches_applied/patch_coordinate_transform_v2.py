#!/usr/bin/env python3
"""
Patch para coordinate_transform_tool.py

Bug: el schema usaba la clave 'input_schema' (snake_case), pero
run_all_validations.py -- y el resto del ecosistema (ver JACOBIAN_TOOL_SCHEMA
en auto_differentiation_tool.py) -- espera 'inputSchema' (camelCase, tal
como lo define el protocolo MCP). Como el harness detecta mode=validate
inspeccionando el enum dentro de 'inputSchema', con la clave incorrecta
nunca encontraba la propiedad 'mode' y marcaba la tool como SKIPPED
("sin modo validate en el schema"), aunque el enum ["...", "validate"]
estaba perfectamente definido adentro.

Fix: renombrar unicamente la clave 'input_schema' -> 'inputSchema' en
COORDINATE_TRANSFORM_SCHEMA. No cambia nada del comportamiento de la
tool en si (run(), self_test(), _validate() siguen igual) -- solo hace
que el harness la reconozca.
"""
import ast
import datetime
import shutil
import sys
from pathlib import Path

TARGET = Path("coordinate_transform_tool.py")

OLD = '    "input_schema": {'
NEW = '    "inputSchema": {'


def main():
    if not TARGET.exists():
        print(f"ERROR: no se encontro {TARGET.resolve()}", file=sys.stderr)
        sys.exit(1)

    src = TARGET.read_text(encoding="utf-8")

    count = src.count(OLD)
    if count != 1:
        print(
            f"ERROR: se esperaba encontrar exactamente 1 ocurrencia de la linea objetivo, "
            f"se encontraron {count}. No se aplico ningun cambio.",
            file=sys.stderr,
        )
        print(f"Linea buscada: {OLD!r}", file=sys.stderr)
        sys.exit(1)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = TARGET.with_name(f"{TARGET.name}.bak_{ts}")
    shutil.copy2(TARGET, backup_path)
    print(f"Backup creado: {backup_path}")

    new_src = src.replace(OLD, NEW)
    TARGET.write_text(new_src, encoding="utf-8")

    try:
        ast.parse(new_src)
    except SyntaxError as e:
        shutil.copy2(backup_path, TARGET)
        print(f"ERROR: el archivo parcheado no es sintacticamente valido: {e}", file=sys.stderr)
        print("Se revirtio el archivo al estado original desde el backup.", file=sys.stderr)
        sys.exit(1)

    print("coordinate_transform_tool.py parcheado OK.")
    print("py_compile OK.")
    print(r"""\nListo. Ahora corre:
  python3 coordinate_transform_tool.py self_test
  python3 coordinate_transform_tool.py validate
  python3 run_all_validations.py   # deberia bajar SKIPPED de 15 a 14 y subir PASSED a 231""")


if __name__ == "__main__":
    main()
