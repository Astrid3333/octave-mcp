#!/usr/bin/env python3
"""
wire_mesh_spectral_tool.py

Wireo automatico de mesh_spectral_tool en server.py de octave-mcp.
Mismo patron validado que wire_bio_tools_auto_fixed.py (confirmado por
grep sobre el server.py real: elif tool_name == ... / result = ... /
resp = {...}).

USO:
    cd ~/octave-mcp
    # 1. copiar mesh_spectral_tool.py a este directorio primero
    python3 wire_mesh_spectral_tool.py --dry-run
    python3 wire_mesh_spectral_tool.py
"""

import sys
import re
import shutil
import datetime
import argparse

MODULE = "mesh_spectral_tool"
FUNC = "compute_mesh_spectral_tool"
SCHEMA = "MESH_SPECTRAL_TOOL_SCHEMA"
TOOL_NAME = "mesh_spectral_tool"

DEFAULT_IMPORTS_PATTERN = r"^from \w+ import compute_\w+, \w+_SCHEMA\s*$"
DEFAULT_SCHEMAS_PATTERN = r"^\s*\w+_SCHEMA,\s*$"
DEFAULT_DISPATCH_PATTERN = (
    r'^            elif tool_name == "\w+":\n'
    r'                result = compute_\w+\(\*\*args\)\n'
    r'                resp = \{\n'
    r'                    "jsonrpc": "2\.0", "id": req_id,\n'
    r'                    "result": \{"content": \[\{"type": "text", "text": json\.dumps\(result, ensure_ascii=False, indent=2\)\}\]\},\n'
    r'                \}'
)


def find_last_match(content, pattern, flags=re.MULTILINE):
    matches = list(re.finditer(pattern, content, flags))
    return matches[-1] if matches else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--server", default="server.py")
    args = ap.parse_args()

    try:
        with open(args.server, "r") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"ERROR: no se encontro {args.server} en el directorio actual.")
        sys.exit(1)

    # sanity: mesh_spectral_tool.py debe existir en el mismo directorio
    import os
    if not os.path.exists(f"{MODULE}.py"):
        print(f"ERROR: no se encontro {MODULE}.py en el directorio actual.")
        print(f"Copia mesh_spectral_tool.py a este directorio ({os.getcwd()}) antes de correr este script.")
        sys.exit(1)

    # anti-duplicado
    if f'elif tool_name == "{TOOL_NAME}"' in content:
        print(f"ADVERTENCIA: '{TOOL_NAME}' ya existe en el dispatch de {args.server}.")
        print("Probablemente ya fue wireado antes. Abortando para evitar duplicados.")
        sys.exit(1)

    import_block = f"from {MODULE} import {FUNC}, {SCHEMA}"
    schema_block = f"    {SCHEMA},"
    dispatch_block = (
        f'            elif tool_name == "{TOOL_NAME}":\n'
        f'                result = {FUNC}(**args)\n'
        f'                resp = {{\n'
        f'                    "jsonrpc": "2.0", "id": req_id,\n'
        f'                    "result": {{"content": [{{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}}]}},\n'
        f'                }}'
    )

    m_imports = find_last_match(content, DEFAULT_IMPORTS_PATTERN)
    m_schemas = find_last_match(content, DEFAULT_SCHEMAS_PATTERN)
    m_dispatch = find_last_match(content, DEFAULT_DISPATCH_PATTERN, flags=re.MULTILINE)

    missing = []
    if m_imports is None:
        missing.append("imports")
    if m_schemas is None:
        missing.append("schemas")
    if m_dispatch is None:
        missing.append("dispatch")
    if missing:
        print(f"No se pudo auto-detectar el patron para: {', '.join(missing)}")
        sys.exit(1)

    print("=== PLAN DE INSERCION ===")
    print(f"imports: insertar despues de -> {m_imports.group(0)!r}")
    print(f"schemas: insertar despues de -> {m_schemas.group(0)!r}")
    print(f"dispatch: insertar despues del bloque que termina en -> {m_dispatch.group(0)[-60:]!r}")
    print(f"\nNuevo bloque de import:\n  {import_block}")
    print(f"\nNuevo bloque de schema:\n  {schema_block}")
    print(f"\nNuevo bloque de dispatch:\n{dispatch_block}")

    if args.dry_run:
        print("\n--dry-run: no se modifico ningun archivo.")
        return

    def insert_after(text, match_end, block):
        return text[:match_end] + "\n" + block + text[match_end:]

    new_content = content
    m = find_last_match(new_content, DEFAULT_IMPORTS_PATTERN)
    new_content = insert_after(new_content, m.end(), import_block)

    m = find_last_match(new_content, DEFAULT_SCHEMAS_PATTERN)
    new_content = insert_after(new_content, m.end(), schema_block)

    m = find_last_match(new_content, DEFAULT_DISPATCH_PATTERN, flags=re.MULTILINE)
    new_content = insert_after(new_content, m.end(), "\n" + dispatch_block)

    backup_path = f"{args.server}.bak.{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(args.server, backup_path)
    print(f"\nBackup creado: {backup_path}")

    with open(args.server, "w") as f:
        f.write(new_content)

    print(f"{args.server} parcheado con mesh_spectral_tool.")

    import py_compile
    try:
        py_compile.compile(args.server, doraise=True)
        print("py_compile OK: sintaxis valida.")
    except py_compile.PyCompileError as e:
        print(f"ERROR DE SINTAXIS despues del patch: {e}")
        print(f"Restaurando backup desde {backup_path} ...")
        shutil.copy(backup_path, args.server)
        print("server.py restaurado.")
        sys.exit(1)

    print("Listo. Corre un smoke test antes de reiniciar Claude Desktop.")


if __name__ == "__main__":
    main()
