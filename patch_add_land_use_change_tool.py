#!/usr/bin/env python3
"""
patch_add_land_use_change_tool.py

Wirea land_use_change_tool.py en server.py. A diferencia de
cosmological_mcmc_tool.py (que quedo con wiring duplicado: dispatcher
legacy + registro directo), este tool sigue el patron limpio de
auto-registro via tool_registry (mismo patron que wildfire_intensity_model_tool,
geospatial_risk_analysis_tool, scalar_field_cosmology_tool, color_math_tool,
etc.): una sola linea de import en server.py, sin entrada en TOOLS[] ni
rama elif -- el propio archivo se registra al importarse.

Ancla en el import de color_math_tool (el ultimo tool de este patron
confirmado en server.py), con backup automatico, --dry-run y validacion
de sintaxis via py_compile.

Uso:
    cd ~/octave-mcp
    cp /ruta/a/land_use_change_tool.py .
    python3 patch_add_land_use_change_tool.py --dry-run
    python3 patch_add_land_use_change_tool.py
"""

import argparse
import datetime
import py_compile
import sys
from pathlib import Path

SERVER_PATH = Path("server.py")
TOOL_FILE = Path("land_use_change_tool.py")

IMPORT_MARKER = "import color_math_tool  # auto-registra via tool_registry"
NEW_IMPORT = "import land_use_change_tool  # auto-registra via tool_registry"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not SERVER_PATH.exists():
        print(f"ERROR: no se encontro {SERVER_PATH.resolve()}", file=sys.stderr)
        sys.exit(1)
    if not TOOL_FILE.exists():
        print(
            f"ERROR: no se encontro {TOOL_FILE.resolve()} -- copialo a este "
            "directorio antes de correr el patch.",
            file=sys.stderr,
        )
        sys.exit(1)

    content = SERVER_PATH.read_text(encoding="utf-8")

    assert content.count(IMPORT_MARKER) == 1, (
        f"No encontre (o encontre mas de una vez) '{IMPORT_MARKER}' en "
        "server.py -- ajustar IMPORT_MARKER manualmente."
    )
    assert "land_use_change_tool" not in content, (
        "land_use_change_tool ya parece estar wireado en server.py -- nada que hacer."
    )

    print("=== PLAN DE INSERCION ===")
    print(f"import: insertar despues de -> '{IMPORT_MARKER}'")
    print(f"  '{NEW_IMPORT}'")
    print()

    if args.dry_run:
        print("--dry-run: no se modifico ningun archivo.")
        return

    backup_name = f"server.py.bak_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    Path(backup_name).write_text(content, encoding="utf-8")
    print(f"Backup: {backup_name}")

    content = content.replace(IMPORT_MARKER, IMPORT_MARKER + "\n" + NEW_IMPORT, 1)
    SERVER_PATH.write_text(content, encoding="utf-8")

    try:
        py_compile.compile(str(SERVER_PATH), doraise=True)
        print("server.py actualizado y validado sintacticamente.")
    except py_compile.PyCompileError as e:
        print("ERROR de sintaxis tras el patch:", e, file=sys.stderr)
        print(f"Restaurando desde backup {backup_name}...", file=sys.stderr)
        Path(backup_name).replace(SERVER_PATH)
        sys.exit(1)

    print()
    print("Smoke test (modo validate, deberia dar passed=true y errors=[]):")
    print(
        '  python3 -c "from land_use_change_tool import '
        "compute_land_use_change_tool as f; import json; "
        "print(json.dumps(f('validate'), indent=2, default=str))\""
    )
    print()
    print("O via el protocolo MCP completo:")
    print(
        '  echo \'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":'
        '{"name":"land_use_change_tool","arguments":{"mode":"validate",'
        '"params":{}}}}\' | timeout 30 python3 server.py'
    )


if __name__ == "__main__":
    main()
