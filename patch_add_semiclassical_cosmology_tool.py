#!/usr/bin/env python3
"""
patch_add_semiclassical_cosmology_tool.py

Inserta semiclassical_cosmology_tool (Fase 2: friedmann_lqg_correction,
bounce_dynamics, power_spectrum) en server.py. Mismo patron que
patch_add_quantum_astro_tool.py: --dry-run, backup timestamped, anchors
por regex (no hardcodeados), indentacion del dispatch capturada del propio
archivo, py_compile al final.

El anchor de import ahora incluye quantum_astro_tool (tu ultimo tool
agregado) como primer candidato.
"""

import re
import sys
import py_compile
import shutil
from datetime import datetime

SERVER_PATH = "server.py"
DRY_RUN = "--dry-run" in sys.argv

NEW_IMPORT = "from semiclassical_cosmology_tool import compute_semiclassical_cosmology_tool, SEMICLASSICAL_COSMOLOGY_TOOL_SCHEMA\n"
NEW_SCHEMA_ENTRY = "    SEMICLASSICAL_COSMOLOGY_TOOL_SCHEMA,\n"


def _build_dispatch_block(indent):
    body_indent = indent + "    "
    return (
        f'{indent}elif tool_name == "semiclassical_cosmology_tool":\n'
        f"{body_indent}result = compute_semiclassical_cosmology_tool(**args)\n"
        f"{body_indent}resp = {{\n"
        f'{body_indent}    "jsonrpc": "2.0", "id": req_id,\n'
        f'{body_indent}    "result": {{"content": [{{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}}]}},\n'
        f"{body_indent}}}\n"
    )


# Anchors, del mas especifico al mas generico. quantum_astro_tool primero
# porque es el ultimo insertado; si tu server.py todavia no lo tiene (por
# ejemplo si corres esto antes de aplicar ese parche, o en otro orden),
# cae a mesh_pde_tool, etc.
IMPORT_ANCHOR_PATTERNS = [
    r"^from quantum_astro_tool import [^\n]*QUANTUM_ASTRO_TOOL_SCHEMA\n",
    r"^from mesh_pde_tool import [^\n]*MESH_PDE_TOOL_SCHEMA\n",
    r"^from lscm_tool import [^\n]*LSCM_TOOL_SCHEMA\n",
    r"^from sdf_tool import [^\n]*SDF_TOOL_SCHEMA\n",
    r"^from distmesh_tool import [^\n]*DISTMESH_TOOL_SCHEMA\n",
]
SCHEMA_ANCHOR_PATTERNS = [
    r"^ {4}QUANTUM_ASTRO_TOOL_SCHEMA,\n",
    r"^ {4}MESH_PDE_TOOL_SCHEMA,\n",
    r"^ {4}LSCM_TOOL_SCHEMA,\n",
    r"^ {4}SDF_TOOL_SCHEMA,\n",
    r"^ {4}DISTMESH_TOOL_SCHEMA,\n",
]
DISPATCH_ANCHOR_PATTERN = r'^([ \t]*)elif tool_name == "distmesh_tool":\n'


def find_last_match(content, patterns):
    for pat in patterns:
        m = re.search(pat, content, re.MULTILINE)
        if m:
            return m.group(0), m.end()
    return None, None


def main():
    with open(SERVER_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    import_anchor_text, import_end = find_last_match(content, IMPORT_ANCHOR_PATTERNS)
    if import_anchor_text is None:
        print("No encontre ningun anchor de import conocido en server.py.")
        print("Ajusta IMPORT_ANCHOR_PATTERNS manualmente en este script.")
        sys.exit(1)
    assert content.count(NEW_IMPORT) == 0, "El import de semiclassical_cosmology_tool ya esta presente."

    schema_anchor_text, schema_end = find_last_match(content, SCHEMA_ANCHOR_PATTERNS)
    if schema_anchor_text is None:
        print("No encontre ningun anchor de schema conocido en server.py.")
        print("Ajusta SCHEMA_ANCHOR_PATTERNS manualmente en este script.")
        sys.exit(1)
    assert content.count(NEW_SCHEMA_ENTRY) == 0, "SEMICLASSICAL_COSMOLOGY_TOOL_SCHEMA ya esta en la lista de schemas."

    dispatch_matches = list(re.finditer(DISPATCH_ANCHOR_PATTERN, content, re.MULTILINE))
    assert len(dispatch_matches) == 1, (
        f"Esperaba exactamente 1 ocurrencia de 'elif tool_name == \"distmesh_tool\":' "
        f"pero encontre {len(dispatch_matches)}. Revisa DISPATCH_ANCHOR_PATTERN manualmente."
    )
    dispatch_start = dispatch_matches[0].start()
    dispatch_indent = dispatch_matches[0].group(1)
    NEW_DISPATCH_BLOCK = _build_dispatch_block(dispatch_indent)

    assert content.count('elif tool_name == "semiclassical_cosmology_tool":') == 0, (
        "El dispatch de semiclassical_cosmology_tool ya esta presente."
    )

    print("=== PLAN DE INSERCION ===")
    print(f"imports: insertar despues de -> {import_anchor_text.strip()!r}")
    print(f"schemas: insertar despues de -> {schema_anchor_text.strip()!r}")
    print("dispatch: insertar antes de -> 'elif tool_name == \"distmesh_tool\":'")
    print()
    print("Nuevo bloque de import:")
    print(f"  {NEW_IMPORT.strip()}")
    print()
    print("Nuevo bloque de schema:")
    print(f"  {NEW_SCHEMA_ENTRY.strip()}")
    print()
    print("Nuevo bloque de dispatch:")
    print(NEW_DISPATCH_BLOCK)

    if DRY_RUN:
        print("--dry-run: no se modifico ningun archivo.")
        return

    backup_name = f"{SERVER_PATH}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(SERVER_PATH, backup_name)
    print(f"Backup: {backup_name}")

    new_content = content[:dispatch_start] + NEW_DISPATCH_BLOCK + content[dispatch_start:]

    schema_anchor_text2, schema_end2 = find_last_match(new_content, SCHEMA_ANCHOR_PATTERNS)
    new_content = new_content[:schema_end2] + NEW_SCHEMA_ENTRY + new_content[schema_end2:]

    import_anchor_text2, import_end2 = find_last_match(new_content, IMPORT_ANCHOR_PATTERNS)
    new_content = new_content[:import_end2] + NEW_IMPORT + new_content[import_end2:]

    with open(SERVER_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    print("Import de semiclassical_cosmology_tool insertado.")
    print("Dispatch elif de semiclassical_cosmology_tool insertado antes de distmesh_tool.")
    print("SEMICLASSICAL_COSMOLOGY_TOOL_SCHEMA agregado a la lista de schemas.")

    try:
        py_compile.compile(SERVER_PATH, doraise=True)
        print("server.py actualizado y validado sintacticamente.")
    except py_compile.PyCompileError as e:
        print("ERROR de sintaxis tras el parche. Restaurando backup.")
        shutil.copy2(backup_name, SERVER_PATH)
        print(e)
        sys.exit(1)

    print()
    print("Smoke test 1 (bounce_dynamics, dust w=0: a_min~0.2154435, addot/a=150.0, is_true_bounce=true):")
    print(
        '  echo \'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":'
        '{"name":"semiclassical_cosmology_tool","arguments":{"mode":"bounce_dynamics",'
        '"params":{"rho0":1.0,"a0":1.0,"w":0.0,"rho_c":100.0,"kappa":1.0}}}}\' | timeout 30 python3 server.py'
    )
    print()
    print("Smoke test 2 (friedmann_lqg_correction, dust w=0):")
    print(
        '  echo \'{"jsonrpc":"2.0","id":2,"method":"tools/call","params":'
        '{"name":"semiclassical_cosmology_tool","arguments":{"mode":"friedmann_lqg_correction",'
        '"params":{"rho0":1.0,"a0":1.0,"w":0.0,"rho_c":100.0,"kappa":1.0,"t_max":3.0,"n_points":50}}}}\' | timeout 30 python3 server.py'
    )


if __name__ == "__main__":
    main()
