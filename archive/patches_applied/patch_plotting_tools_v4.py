#!/usr/bin/env python3
"""
Patch v4 para plotting_tools.py

Bug: PillowWriter (matplotlib.animation) no acepta un buffer BytesIO como
destino de anim.save() -- a diferencia de fig.savefig(), necesita un path
real (str u os.PathLike) porque abre el archivo el mismo para ir escribiendo
los frames del GIF.

Error observado:
  argument should be a str or an os.PathLike object where __fspath__
  returns a str, not 'BytesIO'

Fix: escribir a un archivo temporal en disco con tempfile.mkstemp(),
pasarle el path (str) a anim.save(), leer los bytes del archivo para
armar el base64, y borrar el temporal en un finally.
"""
import ast
import datetime
import shutil
import sys
from pathlib import Path

TARGET = Path("plotting_tools.py")

OLD = '''    buf = io.BytesIO()
    anim.save(buf, writer="pillow", fps=fps)
    plt.close(fig)
    buf.seek(0)
    gif_b64 = base64.b64encode(buf.read()).decode("ascii")'''

NEW = '''    import os
    import tempfile
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".gif")
    os.close(tmp_fd)
    try:
        anim.save(tmp_path, writer="pillow", fps=fps)
        plt.close(fig)
        with open(tmp_path, "rb") as _gif_f:
            gif_b64 = base64.b64encode(_gif_f.read()).decode("ascii")
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass'''


def main():
    if not TARGET.exists():
        print(f"ERROR: no se encontro {TARGET.resolve()}", file=sys.stderr)
        sys.exit(1)

    src = TARGET.read_text(encoding="utf-8")

    count = src.count(OLD)
    if count != 1:
        print(
            f"ERROR: se esperaba encontrar exactamente 1 ocurrencia del bloque objetivo, "
            f"se encontraron {count}. No se aplico ningun cambio.",
            file=sys.stderr,
        )
        print("Bloque buscado:", file=sys.stderr)
        print(OLD, file=sys.stderr)
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

    print("plotting_tools.py parcheado OK (patch v4).")
    print("py_compile OK.")
    print(r"""\nListo. Ahora corre:
  python3 plotting_tools.py self_test
  python3 plotting_tools.py validate""")


if __name__ == "__main__":
    main()
