#!/usr/bin/env python3
"""
patch_add_quantum_cosmology_tool.py

Inserta quantum_cosmology_tool en server.py (import, schema en TOOLS,
dispatch elif), siguiendo el mismo patron usado para quantum_astro_tool,
semiclassical_cosmology_tool y cosmological_mcmc_tool.

Uso:
    python3 patch_add_quantum_cosmology_tool.py --dry-run
    python3 patch_add_quantum_cosmology_tool.py
"""

import sys
import shutil
import datetime
import ast

SERVER_FILE = "server.py"

IMPORT_ANCHOR = 'from cosmological_mcmc_tool import compute_cosmological_mcmc_tool, COSMOLOGICAL_MCMC_TOOL_SCHEMA'
IMPORT_BLOCK = 'from quantum_cosmology_tool import compute_quantum_cosmology_tool, QUANTUM_COSMOLOGY_TOOL_SCHEMA'

SCHEMA_ANCHOR = 'COSMOLOGICAL_MCMC_TOOL_SCHEMA,'
SCHEMA_BLOCK = '    QUANTUM_COSMOLOGY_TOOL_SCHEMA,'

DISPATCH_ANCHOR = 'elif tool_name == "distmesh_tool":'
DISPATCH_BLOCK = '''            elif tool_name == "quantum_cosmology_tool":
                result = compute_quantum_cosmology_tool(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }
'''


def main():
    dry_run = "--dry-run" in sys.argv

    with open(SERVER_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    if "quantum_cosmology_tool" in content:
        print("quantum_cosmology_tool ya esta presente en server.py, no se hace nada.")
        return

    print("=== PLAN DE INSERCION ===")
    print(f"imports: insertar despues de -> '{IMPORT_ANCHOR}'")
    print(f"schemas: insertar despues de -> '{SCHEMA_ANCHOR}'")
    print(f"dispatch: insertar antes de -> '{DISPATCH_ANCHOR}'")
    print()
    print("Nuevo bloque de import:")
    print(f"  {IMPORT_BLOCK}")
    print()
    print("Nuevo bloque de schema:")
    print(SCHEMA_BLOCK.strip())
    print()
    print("Nuevo bloque de dispatch:")
    print(DISPATCH_BLOCK)

    if dry_run:
        print("--dry-run: no se modifico ningun archivo.")
        return

    # 1) import
    if IMPORT_ANCHOR not in content:
        print(f"ERROR: no se encontro el anchor de import: {IMPORT_ANCHOR}")
        sys.exit(1)
    content = content.replace(
        IMPORT_ANCHOR, IMPORT_ANCHOR + "\n" + IMPORT_BLOCK, 1
    )

    # 2) schema (dentro de la lista TOOLS)
    if SCHEMA_ANCHOR not in content:
        print(f"ERROR: no se encontro el anchor de schema: {SCHEMA_ANCHOR}")
        sys.exit(1)
    content = content.replace(
        "    " + SCHEMA_ANCHOR,
        "    " + SCHEMA_ANCHOR + "\n" + SCHEMA_BLOCK,
        1,
    )

    # 3) dispatch elif (antes de distmesh_tool, indentacion 12 espacios)
    dispatch_anchor_full = "            " + DISPATCH_ANCHOR
    if dispatch_anchor_full not in content:
        print(f"ERROR: no se encontro el anchor de dispatch: {dispatch_anchor_full}")
        sys.exit(1)
    content = content.replace(
        dispatch_anchor_full,
        DISPATCH_BLOCK + dispatch_anchor_full,
        1,
    )

    # backup
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{SERVER_FILE}.bak_{timestamp}"
    shutil.copy(SERVER_FILE, backup_name)
    print(f"Backup: {backup_name}")

    # validar sintaxis antes de escribir
    try:
        ast.parse(content)
    except SyntaxError as e:
        print(f"ERROR de sintaxis en el resultado, no se escribio nada: {e}")
        sys.exit(1)

    with open(SERVER_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    print("Import de quantum_cosmology_tool insertado.")
    print("QUANTUM_COSMOLOGY_TOOL_SCHEMA agregado a la lista de schemas.")
    print("Dispatch elif de quantum_cosmology_tool insertado antes de distmesh_tool.")
    print("server.py actualizado y validado sintacticamente.")
    print()
    print('Smoke test (deberia dar all_pass=true):')
    print('  echo \'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"quantum_cosmology_tool","arguments":{"mode":"self_test","params":{}}}}\' | timeout 30 python3 server.py')


if __name__ == "__main__":
    main()
