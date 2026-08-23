#!/usr/bin/env python3
"""
wire_bio_tools.py

Wireo de los 9 tools nuevos (genomas/proteinas/luz/infrasonido/bacterias/
virus/enzimas/celulas) dentro de server.py de octave-mcp.

USO:
    1. Copia los 9 archivos *_tool.py a ~/octave-mcp/ (junto a server.py).
    2. Corre este script UNA VEZ desde ~/octave-mcp/:
           python3 wire_bio_tools.py
    3. Si algun anchor no matchea exactamente (server.py tiene una estructura
       distinta a la esperada), el script va a fallar con un AssertionError
       claro indicando que patch fallo -- no va a dejar server.py a medio
       parchear (hace un backup antes de escribir).
    4. Reiniciar Claude Desktop despues de correr esto (o correr tu harness
       de test_harness_timeout.py contra el server.py resultante para
       validar antes de reiniciar).

Este script asume la convencion ya establecida en octave-mcp:
    - imports de la forma: from nombre_tool import compute_nombre_tool, NOMBRE_TOOL_SCHEMA
    - una lista de tool schemas (buscamos el patron mas comun: una lista
      python donde se van agregando los *_SCHEMA)
    - un dispatcher tipo if/elif por nombre de tool que llama a compute_X

Como no tengo el server.py real en este entorno, dejo el patch en DOS
ESTRATEGIAS para que elijas la que aplique a tu archivo real:

  ESTRATEGIA A (recomendada si tu server.py ya usa un dict TOOL_REGISTRY
  o una lista de tuplas (schema, compute_fn) -- confirma el patron real
  antes de correr):
      Edita las variables ANCHOR_IMPORTS, ANCHOR_SCHEMAS, ANCHOR_DISPATCH
      mas abajo para que coincidan EXACTAMENTE (string) con una linea
      unica existente en tu server.py, y corre el script.

  ESTRATEGIA B (manual, mas segura si no estas 100% segura del patron):
      Ignora este script y agrega las 3 lineas de cada tool a mano en
      server.py, usando de guia el bloque IMPORTS_BLOCK / SCHEMAS_BLOCK /
      DISPATCH_BLOCK impresos por --print-blocks (ver abajo).

Corre con --print-blocks para solo imprimir los bloques a pegar a mano,
sin tocar ningun archivo:
    python3 wire_bio_tools.py --print-blocks
"""

import sys
import shutil
import datetime

TOOLS = [
    ("genome_signal_analysis_tool", "compute_genome_signal_analysis", "GENOME_SIGNAL_ANALYSIS_SCHEMA"),
    ("polarization_mapping_tool", "compute_polarization_mapping", "POLARIZATION_MAPPING_SCHEMA"),
    ("geometric_algebra_protein_tool", "compute_geometric_algebra_protein", "GEOMETRIC_ALGEBRA_PROTEIN_SCHEMA"),
    ("optical_sequence_id_tool", "compute_optical_sequence_id", "OPTICAL_SEQUENCE_ID_SCHEMA"),
    ("infrasound_tool", "compute_infrasound_tool", "INFRASOUND_TOOL_SCHEMA"),
    ("bacterial_growth_tool", "compute_bacterial_growth_tool", "BACTERIAL_GROWTH_TOOL_SCHEMA"),
    ("viral_lattice_tool", "compute_viral_lattice_tool", "VIRAL_LATTICE_TOOL_SCHEMA"),
    ("enzyme_stochastic_tool", "compute_enzyme_stochastic", "ENZYME_STOCHASTIC_SCHEMA"),
    ("evo_lgca_tool", "compute_evo_lgca_tool", "EVO_LGCA_TOOL_SCHEMA"),
]

# ---- AJUSTA ESTOS 3 ANCHORS ANTES DE CORRER EN MODO PATCH (no --print-blocks) ----
# Deben ser strings que existan EXACTAMENTE UNA VEZ en tu server.py real.
# Ejemplos tipicos (reemplaza por lo que encuentres en tu archivo):
ANCHOR_IMPORTS = "from chemometrics_tool import compute_chemometrics_tool, CHEMOMETRICS_TOOL_SCHEMA"
ANCHOR_SCHEMAS = "CHEMOMETRICS_TOOL_SCHEMA,"
ANCHOR_DISPATCH = 'elif name == "chemometrics_tool":\n        return compute_chemometrics_tool(**arguments)'
# ------------------------------------------------------------------------------


def build_blocks():
    import_lines = []
    schema_lines = []
    dispatch_lines = []
    for module_name, func_name, schema_name in TOOLS:
        import_lines.append(f"from {module_name} import {func_name}, {schema_name}")
        schema_lines.append(f"    {schema_name},")
        tool_display_name = schema_name.replace("_SCHEMA", "").lower()
        dispatch_lines.append(
            f'    elif name == "{tool_display_name}":\n        return {func_name}(**arguments)'
        )
    return "\n".join(import_lines), "\n".join(schema_lines), "\n".join(dispatch_lines)


def main():
    import_block, schema_block, dispatch_block = build_blocks()

    if "--print-blocks" in sys.argv:
        print("=== IMPORTS_BLOCK (agregar junto a los demas imports de tools) ===\n")
        print(import_block)
        print("\n=== SCHEMAS_BLOCK (agregar a la lista/registro de schemas) ===\n")
        print(schema_block)
        print("\n=== DISPATCH_BLOCK (agregar al if/elif de despacho por nombre) ===\n")
        print(dispatch_block)
        print(
            "\nNOTA: los nombres de tool usados en el dispatch son en minuscula segun "
            "el schema (X_SCHEMA -> 'x'). Si tu convencion de 'name' en el schema real "
            "difiere (ej: 'evo_LGCA_tool' con mayusculas en LGCA), ajusta el string "
            "despues de 'elif name ==' para que coincida EXACTO con el campo 'name' "
            "dentro de cada *_SCHEMA (ver los archivos *_tool.py)."
        )
        return

    server_path = "server.py"
    try:
        with open(server_path, "r") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"ERROR: no se encontro {server_path} en el directorio actual. Corre este script desde ~/octave-mcp/.")
        sys.exit(1)

    for anchor, label in [
        (ANCHOR_IMPORTS, "ANCHOR_IMPORTS"),
        (ANCHOR_SCHEMAS, "ANCHOR_SCHEMAS"),
        (ANCHOR_DISPATCH, "ANCHOR_DISPATCH"),
    ]:
        count = content.count(anchor)
        assert count == 1, (
            f"{label} no matchea exactamente 1 vez en server.py (matcheo {count} veces). "
            f"Edita la variable {label} en este script para que coincida con una linea "
            f"REAL y UNICA de tu server.py, o corre con --print-blocks y pega a mano."
        )

    backup_path = f"server.py.bak.{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(server_path, backup_path)
    print(f"Backup creado: {backup_path}")

    content = content.replace(ANCHOR_IMPORTS, ANCHOR_IMPORTS + "\n" + import_block, 1)
    content = content.replace(ANCHOR_SCHEMAS, ANCHOR_SCHEMAS + "\n" + schema_block, 1)
    content = content.replace(ANCHOR_DISPATCH, ANCHOR_DISPATCH + "\n" + dispatch_block, 1)

    with open(server_path, "w") as f:
        f.write(content)

    print(f"server.py parcheado con {len(TOOLS)} tools nuevos.")
    print("Copia los 9 archivos *_tool.py a este mismo directorio si aun no lo hiciste.")
    print("Corre tu test_harness_timeout.py para validar antes de reiniciar Claude Desktop.")


if __name__ == "__main__":
    main()
