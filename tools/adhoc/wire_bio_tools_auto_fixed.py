#!/usr/bin/env python3
"""
wire_bio_tools_auto_fixed.py

Version corregida: usa el patron REAL de server.py (confirmado por grep):

    elif tool_name == "X":
        result = compute_X(**args)
        resp = {
            "jsonrpc": "2.0", "id": req_id,
            "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
        }

(12 espacios para 'elif', 16 para 'result ='/'resp ='/cierre '}', 20 para
las lineas internas de resp), en vez del patron generico viejo
(elif name == ...: return compute_X(**arguments)).

USO:
    cd ~/octave-mcp
    python3 wire_bio_tools_auto_fixed.py --dry-run
    python3 wire_bio_tools_auto_fixed.py
"""

import sys
import re
import shutil
import datetime
import argparse

TOOLS = [
    ("genome_signal_analysis_tool", "compute_genome_signal_analysis", "GENOME_SIGNAL_ANALYSIS_SCHEMA", "genome_signal_analysis"),
    ("polarization_mapping_tool", "compute_polarization_mapping", "POLARIZATION_MAPPING_SCHEMA", "polarization_mapping"),
    ("geometric_algebra_protein_tool", "compute_geometric_algebra_protein", "GEOMETRIC_ALGEBRA_PROTEIN_SCHEMA", "geometric_algebra_protein"),
    ("optical_sequence_id_tool", "compute_optical_sequence_id", "OPTICAL_SEQUENCE_ID_SCHEMA", "optical_sequence_id"),
    ("infrasound_tool", "compute_infrasound_tool", "INFRASOUND_TOOL_SCHEMA", "infrasound_tool"),
    ("bacterial_growth_tool", "compute_bacterial_growth_tool", "BACTERIAL_GROWTH_TOOL_SCHEMA", "bacterial_growth_tool"),
    ("viral_lattice_tool", "compute_viral_lattice_tool", "VIRAL_LATTICE_TOOL_SCHEMA", "viral_lattice_tool"),
    ("enzyme_stochastic_tool", "compute_enzyme_stochastic", "ENZYME_STOCHASTIC_SCHEMA", "enzyme_stochastic"),
    ("evo_lgca_tool", "compute_evo_lgca_tool", "EVO_LGCA_TOOL_SCHEMA", "evo_LGCA_tool"),
]

DEFAULT_IMPORTS_PATTERN = r"^from \w+ import compute_\w+, \w+_SCHEMA\s*$"
DEFAULT_SCHEMAS_PATTERN = r"^\s*\w+_SCHEMA,\s*$"
# Patron REAL confirmado por grep en server.py (12 espacios de indent para 'elif')
DEFAULT_DISPATCH_PATTERN = (
    r'^            elif tool_name == "\w+":\n'
    r'                result = compute_\w+\(\*\*args\)\n'
    r'                resp = \{\n'
    r'                    "jsonrpc": "2\.0", "id": req_id,\n'
    r'                    "result": \{"content": \[\{"type": "text", "text": json\.dumps\(result, ensure_ascii=False, indent=2\)\}\]\},\n'
    r'                \}'
)


def build_blocks():
    import_lines = [f"from {m} import {f}, {s}" for m, f, s, n in TOOLS]
    schema_lines = [f"    {s}," for m, f, s, n in TOOLS]
    dispatch_blocks = []
    for m, f, s, n in TOOLS:
        block = (
            f'            elif tool_name == "{n}":\n'
            f'                result = {f}(**args)\n'
            f'                resp = {{\n'
            f'                    "jsonrpc": "2.0", "id": req_id,\n'
            f'                    "result": {{"content": [{{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}}]}},\n'
            f'                }}'
        )
        dispatch_blocks.append(block)
    return "\n".join(import_lines), "\n".join(schema_lines), "\n".join(dispatch_blocks)


def find_last_match(content, pattern, flags=re.MULTILINE):
    matches = list(re.finditer(pattern, content, flags))
    if not matches:
        return None
    return matches[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--imports-pattern", default=DEFAULT_IMPORTS_PATTERN)
    ap.add_argument("--schemas-pattern", default=DEFAULT_SCHEMAS_PATTERN)
    ap.add_argument("--dispatch-pattern", default=DEFAULT_DISPATCH_PATTERN)
    ap.add_argument("--server", default="server.py")
    args = ap.parse_args()

    try:
        with open(args.server, "r") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"ERROR: no se encontro {args.server} en el directorio actual.")
        sys.exit(1)

    import_block, schema_block, dispatch_block = build_blocks()

    m_imports = find_last_match(content, args.imports_pattern)
    m_schemas = find_last_match(content, args.schemas_pattern)
    m_dispatch = find_last_match(content, args.dispatch_pattern, flags=re.MULTILINE)

    missing = []
    if m_imports is None:
        missing.append("imports")
    if m_schemas is None:
        missing.append("schemas")
    if m_dispatch is None:
        missing.append("dispatch")

    if missing:
        print(f"No se pudo auto-detectar el patron para: {', '.join(missing)}")
        print("\nLineas 'elif tool_name ==' encontradas (primeras 10):")
        for l in re.findall(r'elif tool_name == "\w+":', content)[:10]:
            print(f"  {l}")
        sys.exit(1)

    # sanity check: aseguremos que ninguno de los 9 tool_name nuevos ya existe
    # (evita doble-wiring si el script se corre dos veces)
    existing_names = set(re.findall(r'elif tool_name == "(\w+)":', content))
    dupes = [n for _, _, _, n in TOOLS if n in existing_names]
    if dupes:
        print(f"ADVERTENCIA: estos tool_name YA EXISTEN en server.py: {dupes}")
        print("Probablemente el wiring ya se aplico antes. Abortando para evitar duplicados.")
        sys.exit(1)

    print("=== PLAN DE INSERCION ===")
    print(f"imports: insertar despues de -> {m_imports.group(0)!r}")
    print(f"schemas: insertar despues de -> {m_schemas.group(0)!r}")
    print(f"dispatch: insertar despues del bloque que termina en -> {m_dispatch.group(0)[-60:]!r}")
    print(f"\nSe van a agregar {len(TOOLS)} tools: {[t[3] for t in TOOLS]}")

    if args.dry_run:
        print("\n--dry-run: no se modifico ningun archivo.")
        print("\n--- Preview del bloque de dispatch a insertar ---")
        print(dispatch_block[:600])
        return

    def insert_after(text, match_end, block):
        return text[:match_end] + "\n" + block + text[match_end:]

    new_content = content
    m = find_last_match(new_content, args.imports_pattern)
    new_content = insert_after(new_content, m.end(), import_block)

    m = find_last_match(new_content, args.schemas_pattern)
    new_content = insert_after(new_content, m.end(), schema_block)

    m = find_last_match(new_content, args.dispatch_pattern, flags=re.MULTILINE)
    new_content = insert_after(new_content, m.end(), "\n" + dispatch_block)

    backup_path = f"{args.server}.bak.{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(args.server, backup_path)
    print(f"\nBackup creado: {backup_path}")

    with open(args.server, "w") as f:
        f.write(new_content)

    print(f"{args.server} parcheado con {len(TOOLS)} tools nuevos.")

    # Validacion de sintaxis
    import py_compile
    try:
        py_compile.compile(args.server, doraise=True)
        print("py_compile OK: sintaxis valida.")
    except py_compile.PyCompileError as e:
        print(f"ERROR DE SINTAXIS despues del patch: {e}")
        print(f"Restaurando backup desde {backup_path} ...")
        shutil.copy(backup_path, args.server)
        print("server.py restaurado. Revisa el patron de dispatch.")
        sys.exit(1)

    print("Corre tu test_harness_timeout.py para validar antes de reiniciar Claude Desktop.")


if __name__ == "__main__":
    main()
