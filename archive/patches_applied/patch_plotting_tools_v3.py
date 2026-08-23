#!/usr/bin/env python3
"""
Patch v3 para plotting_tools.py

Bug: Animation.save() no acepta el kwarg 'format' (a diferencia de fig.savefig()).
El writer='pillow' ya determina que la salida es GIF, asi que 'format="gif"' sobra
y provoca: TypeError: Animation.save() got an unexpected keyword argument 'format'

Fix: eliminar unicamente el kwarg format="gif" de la llamada a anim.save(),
sin tocar writer='pillow' ni fps.
"""
import ast
import datetime
import shutil
import sys
from pathlib import Path

TARGET = Path("plotting_tools.py")

OLD = '    anim.save(buf, format="gif", writer="pillow", fps=fps)'
NEW = '    anim.save(buf, writer="pillow", fps=fps)'


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

    # backup con timestamp, mismo patron que v2
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = TARGET.with_name(f"{TARGET.name}.bak_{ts}")
    shutil.copy2(TARGET, backup_path)
    print(f"Backup creado: {backup_path}")

    new_src = src.replace(OLD, NEW)
    TARGET.write_text(new_src, encoding="utf-8")

    # validacion de sintaxis
    try:
        ast.parse(new_src)
    except SyntaxError as e:
        # revertir si algo salio mal
        shutil.copy2(backup_path, TARGET)
        print(f"ERROR: el archivo parcheado no es sintacticamente valido: {e}", file=sys.stderr)
        print("Se revirtio el archivo al estado original desde el backup.", file=sys.stderr)
        sys.exit(1)

    print("plotting_tools.py parcheado OK (patch v3).")
    print("py_compile OK.")
    print(r"""\nListo. Ahora corre:
  python3 plotting_tools.py self_test
  python3 plotting_tools.py validate""")


if __name__ == "__main__":
    main()
