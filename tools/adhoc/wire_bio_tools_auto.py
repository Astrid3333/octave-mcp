#!/usr/bin/env python3
"""
wire_bio_tools_auto.py

Wireo automatico de los 9 tools nuevos en server.py de octave-mcp, SIN
edicion manual de anchors. Detecta por regex el patron ya existente en tu
server.py real (imports de tools, lista de schemas, dispatch if/elif) y
inserta los 9 bloques nuevos a continuacion del ultimo match encontrado.

USO (todo por terminal, sin nano):

    cd ~/octave-mcp
    python3 wire_bio_tools_auto.py --dry-run      # solo muestra que va a hacer
    python3 wire_bio_tools_auto.py                # aplica el patch (con backup automatico)

Si el auto-detect no encuentra alguno de los 3 patrones (imports/schemas/
dispatch), el script lista lo que SI encontro y sale sin tocar nada, para
que ajustes el regex correspondiente via --imports-pattern / --schemas-pattern
/ --dispatch-pattern (todo pasado como argumento de linea de comandos, sin
editar el archivo).
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

# regex para detectar el ULTIMO match existente de cada patron en server.py
DEFAULT_IMPORTS_PATTERN = r"^from \w+ import compute_\w+, \w+_SCHEMA\s*$"
DEFAULT_SCHEMAS_PATTERN = r"^\s*\w+_SCHEMA,\s*$"
DEFAULT_DISPATCH_PATTERN = r'elif name == "\w+":\n\s+return compute_\w+\(\*\*arguments\)'


def build_blocks():
    import_lines = [f"from {m} import {f}, {s}" for m, f, s, n in TOOLS]
    schema_lines = [f"    {s}," for m, f, s, n in TOOLS]
    dispatch_lines = [f'    elif name == "{n}":\n        return {f}(**arguments)' for m, f, s, n in TOOLS]
    return "\n".join(import_lines), "\n".join(schema_lines), "\n".join(dispatch_lines)


def find_last_match(content, pattern, flags=re.MULTILINE):
    matches = list(re.finditer(pattern, content, flags))
    if not matches:
        return None
    return matches[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Solo mostrar el plan, no escribir nada.")
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
        print("Corre este script desde ~/octave-mcp/ (o usa --server /ruta/a/server.py).")
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
        print("\nLineas encontradas en tu server.py que parecen imports de tools (primeras 5):")
        for l in re.findall(r"^from \w+ import.*$", content, re.MULTILINE)[:5]:
            print(f"  {l}")
        print("\nLineas encontradas que parecen dispatch elif (primeras 5):")
        for l in re.findall(r'elif name == "\w+":', content)[:5]:
            print(f"  {l}")
        print(
            "\nAjusta el patron correspondiente con --imports-pattern / --schemas-pattern / "
            "--dispatch-pattern (regex, pasado como string por linea de comandos) y volve a correr."
        )
        sys.exit(1)

    print("=== PLAN DE INSERCION ===")
    print(f"imports: insertar despues de -> {m_imports.group(0)!r}")
    print(f"schemas: insertar despues de -> {m_schemas.group(0)!r}")
    print(f"dispatch: insertar despues de -> {m_dispatch.group(0)[:80]!r}...")
    print(f"\nSe van a agregar {len(TOOLS)} tools: {[t[3] for t in TOOLS]}")

    if args.dry_run:
        print("\n--dry-run: no se modifico ningun archivo.")
        return

    # insertar en orden: dispatch primero (indice mas alto no afecta a los otros
    # porque recalculamos posiciones sobre el contenido actualizado en cada paso)
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
    print("Corre tu test_harness_timeout.py para validar antes de reiniciar Claude Desktop.")


if __name__ == "__main__":
    main()
