#!/usr/bin/env python3
"""
patch_add_cosmological_mcmc_tool.py

Wirea cosmological_mcmc_tool (Fase 3 de semiclassical_cosmology_tool:
MCMC de parametros cosmologicos) en server.py, siguiendo el mismo patron
robusto de los patches anteriores (import + entrada en la lista de
schemas + rama de dispatch), con backup automatico, --dry-run y
validacion de sintaxis via py_compile.

Ancla en el import/schema de semiclassical_cosmology_tool (el ultimo
tool wireado antes de este), y en el dispatch de distmesh_tool (mismo
punto de insercion que usaron todos los patches recientes: mesh_spectral,
sdf, lscm, mesh_pde, quantum_astro, semiclassical_cosmology).
"""

import argparse
import datetime
import py_compile
import re
import sys
from pathlib import Path

SERVER_PATH = Path("server.py")

IMPORT_MARKER = (
    "from semiclassical_cosmology_tool import compute_semiclassical_cosmology_tool, "
    "SEMICLASSICAL_COSMOLOGY_TOOL_SCHEMA"
)
NEW_IMPORT = (
    "from cosmological_mcmc_tool import compute_cosmological_mcmc_tool, "
    "COSMOLOGICAL_MCMC_TOOL_SCHEMA"
)

SCHEMA_MARKER = "SEMICLASSICAL_COSMOLOGY_TOOL_SCHEMA,"
NEW_SCHEMA_LINE = "COSMOLOGICAL_MCMC_TOOL_SCHEMA,"

# La indentacion real del bloque de dispatch varia segun el archivo (se
# vio 12 espacios en server.py), asi que se detecta con regex en vez de
# asumirla fija -- evita el bug de indentacion duplicada de una version
# anterior de este patcher.
DISPATCH_MARKER_RE = re.compile(
    r'^([ \t]*)elif tool_name == "distmesh_tool":', re.MULTILINE
)


def build_dispatch_block(indent):
    # OJO: no se agrega indentacion final suelta despues del bloque --
    # el marker que se re-inserta a continuacion (via regex, group(0))
    # ya trae su propio indent, así que agregar uno extra acá duplica
    # espacios y rompe la cadena elif (bug detectado y corregido en
    # pruebas antes de tocar el repo real).
    inner = indent + "    "
    return (
        f'{indent}elif tool_name == "cosmological_mcmc_tool":\n'
        f"{inner}result = compute_cosmological_mcmc_tool(**args)\n"
        f"{inner}resp = {{\n"
        f'{inner}    "jsonrpc": "2.0", "id": req_id,\n'
        f'{inner}    "result": {{"content": [{{"type": "text", '
        f'"text": json.dumps(result, ensure_ascii=False, indent=2)}}]}},\n'
        f"{inner}}}\n"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not SERVER_PATH.exists():
        print(f"ERROR: no se encontro {SERVER_PATH.resolve()}", file=sys.stderr)
        sys.exit(1)

    content = SERVER_PATH.read_text(encoding="utf-8")

    assert content.count(IMPORT_MARKER) >= 1, (
        f"No encontre '{IMPORT_MARKER}' en server.py — ajustar IMPORT_MARKER manualmente."
    )
    assert content.count(SCHEMA_MARKER) >= 1, (
        f"No encontre '{SCHEMA_MARKER}' en server.py — ajustar SCHEMA_MARKER manualmente."
    )
    dispatch_match = DISPATCH_MARKER_RE.search(content)
    assert dispatch_match is not None, (
        'No encontre \'elif tool_name == "distmesh_tool":\' en server.py — '
        "ajustar DISPATCH_MARKER_RE manualmente."
    )
    assert "cosmological_mcmc_tool" not in content.replace(NEW_IMPORT, ""), (
        "cosmological_mcmc_tool ya parece estar wireado en server.py — nada que hacer."
    )

    indent = dispatch_match.group(1)
    new_dispatch_block = build_dispatch_block(indent)

    print("=== PLAN DE INSERCION ===")
    print(f"imports: insertar despues de -> '{IMPORT_MARKER}'")
    print(f"schemas: insertar despues de -> '{SCHEMA_MARKER}'")
    print('dispatch: insertar antes de -> \'elif tool_name == "distmesh_tool":\'')
    print(f"  (indentacion detectada: {len(indent)} espacios)")
    print()
    print("Nuevo bloque de import:")
    print(f"  {NEW_IMPORT}")
    print()
    print("Nuevo bloque de schema:")
    print(f"  {NEW_SCHEMA_LINE}")
    print()
    print("Nuevo bloque de dispatch:")
    print(new_dispatch_block.rstrip())
    print()

    if args.dry_run:
        print("--dry-run: no se modifico ningun archivo.")
        return

    backup_name = f"server.py.bak_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    Path(backup_name).write_text(content, encoding="utf-8")
    print(f"Backup: {backup_name}")

    # 1) import
    content = content.replace(
        IMPORT_MARKER, IMPORT_MARKER + "\n" + NEW_IMPORT, 1
    )
    print("Import de cosmological_mcmc_tool insertado.")

    # 2) schema (respeta la indentacion de la propia linea marcador)
    schema_line_re = re.compile(
        r"^([ \t]*)" + re.escape(SCHEMA_MARKER) + r"[ \t]*$", re.MULTILINE
    )
    schema_match = schema_line_re.search(content)
    schema_indent = schema_match.group(1) if schema_match else "    "
    content = content.replace(
        SCHEMA_MARKER,
        SCHEMA_MARKER + "\n" + schema_indent + NEW_SCHEMA_LINE,
        1,
    )
    print("COSMOLOGICAL_MCMC_TOOL_SCHEMA agregado a la lista de schemas.")

    # 3) dispatch (insertar antes del marker, con la indentacion detectada)
    content = DISPATCH_MARKER_RE.sub(
        lambda m: new_dispatch_block + m.group(0), content, count=1
    )
    print("Dispatch elif de cosmological_mcmc_tool insertado antes de distmesh_tool.")

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
    print("Smoke test 1 (mock_recovery, deberia dar all_params_within_2sigma=true):")
    print(
        '  echo \'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":'
        '{"name":"cosmological_mcmc_tool","arguments":{"mode":"mock_recovery",'
        '"params":{}}}}\' | timeout 60 python3 server.py'
    )
    print()
    print("Smoke test 2 (fit_hz_chronometers sobre datos reales, H0~67-68, Om0~0.33-0.36):")
    print(
        '  echo \'{"jsonrpc":"2.0","id":2,"method":"tools/call","params":'
        '{"name":"cosmological_mcmc_tool","arguments":{"mode":"fit_hz_chronometers",'
        '"params":{}}}}\' | timeout 60 python3 server.py'
    )


if __name__ == "__main__":
    main()
