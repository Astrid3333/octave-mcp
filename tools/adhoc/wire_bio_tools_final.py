#!/usr/bin/env python3
"""
wire_bio_tools_final.py

Wirea los 9 bio tools (genome_signal_analysis, polarization_mapping,
geometric_algebra_protein, optical_sequence_id, infrasound_tool,
bacterial_growth_tool, viral_lattice_tool, enzyme_stochastic, evo_lgca_tool)
en server.py, en los 3 puntos correctos confirmados manualmente:

  1. imports: justo antes de la linea 'TOOLS = ['
  2. registro de schema: justo antes del ']' de cierre de TOOLS (linea unica)
  3. dispatch: justo antes del bloque 'else: ... Tool desconocido' (linea unica)

Corre con --dry-run primero para ver que hace, sin escribir nada.
Backup automatico antes de escribir.
"""
import argparse
import sys
import ast

SERVER_PATH = "server.py"

TOOLS = [
    # (import_name, compute_fn, schema_const, dispatch_tool_name)
    ("genome_signal_analysis_tool", "compute_genome_signal_analysis",
     "GENOME_SIGNAL_ANALYSIS_SCHEMA", "genome_signal_analysis"),
    ("polarization_mapping_tool", "compute_polarization_mapping",
     "POLARIZATION_MAPPING_SCHEMA", "polarization_mapping"),
    ("geometric_algebra_protein_tool", "compute_geometric_algebra_protein",
     "GEOMETRIC_ALGEBRA_PROTEIN_SCHEMA", "geometric_algebra_protein"),
    ("optical_sequence_id_tool", "compute_optical_sequence_id",
     "OPTICAL_SEQUENCE_ID_SCHEMA", "optical_sequence_id"),
    ("infrasound_tool", "compute_infrasound_tool",
     "INFRASOUND_TOOL_SCHEMA", "infrasound_tool"),
    ("bacterial_growth_tool", "compute_bacterial_growth_tool",
     "BACTERIAL_GROWTH_TOOL_SCHEMA", "bacterial_growth_tool"),
    ("viral_lattice_tool", "compute_viral_lattice_tool",
     "VIRAL_LATTICE_TOOL_SCHEMA", "viral_lattice_tool"),
    ("enzyme_stochastic_tool", "compute_enzyme_stochastic",
     "ENZYME_STOCHASTIC_SCHEMA", "enzyme_stochastic"),
    ("evo_lgca_tool", "compute_evo_lgca_tool",
     "EVO_LGCA_TOOL_SCHEMA", "evo_lgca_tool"),
]

IMPORT_MARKER = "TOOLS = [\n"

DISPATCH_MARKER = (
    '            else:\n'
    '                resp = {\n'
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "error": {"code": -32601, "message": f"Tool desconocido: {tool_name}"},\n'
    '                }\n'
)


def build_imports_block():
    lines = []
    for import_name, compute_fn, schema_const, _ in TOOLS:
        lines.append(f"from {import_name} import {compute_fn}, {schema_const}\n")
    return "".join(lines)


def build_schema_block():
    lines = []
    for _, _, schema_const, _ in TOOLS:
        lines.append(f"    {schema_const},\n")
    return "".join(lines)


def build_dispatch_block():
    lines = []
    for _, compute_fn, _, tool_name in TOOLS:
        lines.append(
            f'            elif tool_name == "{tool_name}":\n'
            f'                result = {compute_fn}(**args)\n'
            f'                resp = {{\n'
            f'                    "jsonrpc": "2.0", "id": req_id,\n'
            f'                    "result": {{"content": [{{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}}]}},\n'
            f'                }}\n'
        )
    return "".join(lines)


def find_schema_close_bracket(content):
    """Encuentra la unica linea que es exactamente ']' sola (cierre de TOOLS)."""
    lines = content.split("\n")
    matches = [i for i, l in enumerate(lines) if l == "]"]
    return matches


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with open(SERVER_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # --- 1. Validar anclas unicas ---
    n_import_marker = content.count(IMPORT_MARKER)
    if n_import_marker != 1:
        print(f"ERROR: IMPORT_MARKER aparece {n_import_marker} veces (se esperaba 1). Abortando.")
        sys.exit(1)

    n_dispatch_marker = content.count(DISPATCH_MARKER)
    if n_dispatch_marker != 1:
        print(f"ERROR: DISPATCH_MARKER aparece {n_dispatch_marker} veces (se esperaba 1). Abortando.")
        print("Pegue el bloque exacto de 'else: ... Tool desconocido' si cambio de formato.")
        sys.exit(1)

    close_matches = find_schema_close_bracket(content)
    if len(close_matches) != 1:
        print(f"ERROR: se encontraron {len(close_matches)} lineas que son ']' sola (se esperaba 1). Abortando.")
        sys.exit(1)

    print("Anclas encontradas OK (imports, dispatch, cierre de TOOLS).")

    imports_block = build_imports_block()
    schema_block = build_schema_block()
    dispatch_block = build_dispatch_block()

    if args.dry_run:
        print("\n=== IMPORTS A INSERTAR (antes de 'TOOLS = [') ===\n")
        print(imports_block)
        print("=== SCHEMAS A INSERTAR (antes del ']' de cierre de TOOLS) ===\n")
        print(schema_block)
        print("=== DISPATCH A INSERTAR (antes del 'else: Tool desconocido') ===\n")
        print(dispatch_block)
        print("--dry-run: no se escribio nada.")
        return

    # --- 2. Insertar imports (antes de 'TOOLS = [') ---
    content = content.replace(IMPORT_MARKER, imports_block + IMPORT_MARKER, 1)

    # --- 3. Insertar schemas (antes del ']' de cierre, re-detectado tras el insert anterior) ---
    lines = content.split("\n")
    close_matches = [i for i, l in enumerate(lines) if l == "]"]
    assert len(close_matches) == 1, "el cierre de TOOLS dejo de ser unico tras insertar imports"
    idx = close_matches[0]
    schema_lines = schema_block.rstrip("\n").split("\n")
    lines = lines[:idx] + schema_lines + lines[idx:]
    content = "\n".join(lines)

    # --- 4. Insertar dispatch (antes del else final) ---
    content = content.replace(DISPATCH_MARKER, dispatch_block + DISPATCH_MARKER, 1)

    # --- 5. Backup + validacion sintactica antes de escribir definitivo ---
    import time
    backup_path = f"{SERVER_PATH}.bak.{int(time.time())}"
    with open(SERVER_PATH, "r", encoding="utf-8") as f:
        original = f.read()
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(original)
    print(f"Backup guardado en {backup_path}")

    try:
        ast.parse(content)
    except SyntaxError as e:
        print(f"ERROR: el resultado parcheado NO es Python valido: {e}")
        print("No se escribio nada (el backup ya esta a salvo, el original no se toco).")
        sys.exit(1)

    with open(SERVER_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print("server.py parcheado y validado (ast.parse OK).")
    print("Corre: python3 -m py_compile server.py && python3 server.py  (Ctrl+C si arranca limpio)")


if __name__ == "__main__":
    main()
