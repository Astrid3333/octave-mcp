#!/usr/bin/env python3
"""
Patch para server.py: agrega los 4 imports pendientes de auto-registro
via tool_registry.

  import mycelial_network_tool    # sesion anterior
  import fungal_morphology_tool   # sesion anterior
  import plotting_tools           # esta sesion (parametric_curve, cycloid_family,
                                   #   curve_with_vectors, animate_trace)
  import data_file_reader_tool    # esta sesion (read_delimited, inspect)

Se insertan justo despues de la ultima linea de import con el comentario
'# auto-registra via tool_registry' (teaching_strategies_simulator_tool),
manteniendo el mismo estilo de comentario que el resto del bloque.
"""
import ast
import datetime
import shutil
import sys
from pathlib import Path

TARGET = Path("server.py")

ANCHOR = "import teaching_strategies_simulator_tool  # auto-registra via tool_registry"

NEW_IMPORTS = """import teaching_strategies_simulator_tool  # auto-registra via tool_registry
import mycelial_network_tool  # auto-registra via tool_registry
import fungal_morphology_tool  # auto-registra via tool_registry
import plotting_tools  # auto-registra via tool_registry
import data_file_reader_tool  # auto-registra via tool_registry"""


def main():
    if not TARGET.exists():
        print(f"ERROR: no se encontro {TARGET.resolve()}", file=sys.stderr)
        sys.exit(1)

    src = TARGET.read_text(encoding="utf-8")

    count = src.count(ANCHOR)
    if count != 1:
        print(
            f"ERROR: se esperaba encontrar exactamente 1 ocurrencia de la linea ancla, "
            f"se encontraron {count}. No se aplico ningun cambio.",
            file=sys.stderr,
        )
        print(f"Linea buscada: {ANCHOR!r}", file=sys.stderr)
        sys.exit(1)

    # Verificar que ninguno de los 4 imports nuevos ya este presente
    # (evita duplicados si se corre el patch dos veces)
    already_present = []
    for mod in ["mycelial_network_tool", "fungal_morphology_tool", "plotting_tools", "data_file_reader_tool"]:
        if f"import {mod}\n" in src or f"import {mod} " in src:
            already_present.append(mod)
    if already_present:
        print(
            f"ERROR: los siguientes imports ya estan presentes en server.py: {already_present}. "
            "No se aplico ningun cambio para evitar duplicados.",
            file=sys.stderr,
        )
        sys.exit(1)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = TARGET.with_name(f"{TARGET.name}.bak_{ts}")
    shutil.copy2(TARGET, backup_path)
    print(f"Backup creado: {backup_path}")

    new_src = src.replace(ANCHOR, NEW_IMPORTS)
    TARGET.write_text(new_src, encoding="utf-8")

    try:
        ast.parse(new_src)
    except SyntaxError as e:
        shutil.copy2(backup_path, TARGET)
        print(f"ERROR: el archivo parcheado no es sintacticamente valido: {e}", file=sys.stderr)
        print("Se revirtio el archivo al estado original desde el backup.", file=sys.stderr)
        sys.exit(1)

    print("server.py parcheado OK.")
    print("py_compile OK.")
    print("Se agregaron 4 imports:")
    print("  - mycelial_network_tool")
    print("  - fungal_morphology_tool")
    print("  - plotting_tools")
    print("  - data_file_reader_tool")
    print(r"""\nListo. Ahora corre:
  python3 -c "import ast; ast.parse(open('server.py').read())" && echo "ast OK"
  python3 server.py &
  # confirmar que arranca sin errores de registro (nombres duplicados, etc.)
  # despues detenerlo y correr run_all_validations.py para confirmar 245 tools totales""")


if __name__ == "__main__":
    main()
