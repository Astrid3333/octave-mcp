#!/usr/bin/env python3
"""
patch_add_quantum_astro_tool.py

Inserta quantum_astro_tool (Fase 1: operator_algebra) en server.py.
Sigue tu convencion: --dry-run, backup timestamped, asserts de unicidad
antes de tocar nada, py_compile al final.

A diferencia de tus patches anteriores con marker fijo, este busca los
anchors por regex sobre el propio server.py para no romper si el ultimo
import/schema/dispatch no es exactamente el que yo supongo desde afuera.
Igual que te paso con sdf_tool: si algun assert falla, correlo con
--dry-run primero y ajusta ANCHOR_* manualmente aca abajo.
"""

import re
import sys
import py_compile
import shutil
from datetime import datetime

SERVER_PATH = "server.py"
DRY_RUN = "--dry-run" in sys.argv

NEW_IMPORT = "from quantum_astro_tool import compute_quantum_astro_tool, QUANTUM_ASTRO_TOOL_SCHEMA\n"
NEW_SCHEMA_ENTRY = "    QUANTUM_ASTRO_TOOL_SCHEMA,\n"


def _build_dispatch_block(indent):
    """indent = el whitespace exacto que precede a 'elif tool_name == ...'
    en tu server.py real. El cuerpo va indentado un nivel mas (4 espacios)."""
    body_indent = indent + "    "
    return (
        f'{indent}elif tool_name == "quantum_astro_tool":\n'
        f"{body_indent}result = compute_quantum_astro_tool(**args)\n"
        f"{body_indent}resp = {{\n"
        f'{body_indent}    "jsonrpc": "2.0", "id": req_id,\n'
        f'{body_indent}    "result": {{"content": [{{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}}]}},\n'
        f"{body_indent}}}\n"
    )

# Patrones de anchor (regex), del mas especifico al mas generico.
IMPORT_ANCHOR_PATTERNS = [
    r"^from mesh_pde_tool import [^\n]*MESH_PDE_TOOL_SCHEMA\n",   # tu ultimo tool agregado
    r"^from lscm_tool import [^\n]*LSCM_TOOL_SCHEMA\n",
    r"^from sdf_tool import [^\n]*SDF_TOOL_SCHEMA\n",
    r"^from distmesh_tool import [^\n]*DISTMESH_TOOL_SCHEMA\n",
]
SCHEMA_ANCHOR_PATTERNS = [
    r"^ {4}MESH_PDE_TOOL_SCHEMA,\n",
    r"^ {4}LSCM_TOOL_SCHEMA,\n",
    r"^ {4}SDF_TOOL_SCHEMA,\n",
    r"^ {4}DISTMESH_TOOL_SCHEMA,\n",
]
# Dispatch: se inserta antes del bloque 'elif tool_name == "distmesh_tool":'
# (mismo punto de anclaje que usaste para sdf_tool, lscm_tool y mesh_pde_tool).
# La indentacion se captura del propio archivo en vez de asumir un numero
# fijo de espacios, para no depender de a que nivel de anidamiento este
# el dispatcher real.
DISPATCH_ANCHOR_PATTERN = r'^([ \t]*)elif tool_name == "distmesh_tool":\n'


def find_last_match(content, patterns):
    """Devuelve (match_text, end_index) del primer patron de la lista que
    aparezca en content, o (None, None) si ninguno matchea."""
    for pat in patterns:
        m = re.search(pat, content, re.MULTILINE)
        if m:
            return m.group(0), m.end()
    return None, None


def main():
    with open(SERVER_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # --- Import ---
    import_anchor_text, import_end = find_last_match(content, IMPORT_ANCHOR_PATTERNS)
    if import_anchor_text is None:
        print("No encontre ningun anchor de import conocido en server.py.")
        print("Ajusta IMPORT_ANCHOR_PATTERNS manualmente en este script.")
        sys.exit(1)

    assert content.count(NEW_IMPORT) == 0, "El import de quantum_astro_tool ya esta presente."

    # --- Schema ---
    schema_anchor_text, schema_end = find_last_match(content, SCHEMA_ANCHOR_PATTERNS)
    if schema_anchor_text is None:
        print("No encontre ningun anchor de schema conocido en server.py.")
        print("Ajusta SCHEMA_ANCHOR_PATTERNS manualmente en este script.")
        sys.exit(1)

    assert content.count(NEW_SCHEMA_ENTRY) == 0, "QUANTUM_ASTRO_TOOL_SCHEMA ya esta en la lista de schemas."

    # --- Dispatch ---
    dispatch_matches = list(re.finditer(DISPATCH_ANCHOR_PATTERN, content, re.MULTILINE))
    assert len(dispatch_matches) == 1, (
        f"Esperaba exactamente 1 ocurrencia de 'elif tool_name == \"distmesh_tool\":' "
        f"pero encontre {len(dispatch_matches)}. Revisa DISPATCH_ANCHOR_PATTERN manualmente."
    )
    dispatch_start = dispatch_matches[0].start()
    dispatch_indent = dispatch_matches[0].group(1)
    NEW_DISPATCH_BLOCK = _build_dispatch_block(dispatch_indent)

    assert content.count('elif tool_name == "quantum_astro_tool":') == 0, (
        "El dispatch de quantum_astro_tool ya esta presente."
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

    # Insertar en orden: dispatch primero (indice mas alto en el archivo,
    # asi los indices de import/schema mas arriba no se corren), luego
    # schema, luego import.
    new_content = (
        content[:dispatch_start] + NEW_DISPATCH_BLOCK + content[dispatch_start:]
    )

    # Recalcular offsets de schema/import sobre new_content porque el
    # dispatch se inserto mas abajo en el archivo (no afecta posiciones
    # anteriores, pero por prolijidad volvemos a matchear).
    schema_anchor_text2, schema_end2 = find_last_match(new_content, SCHEMA_ANCHOR_PATTERNS)
    new_content = (
        new_content[:schema_end2] + NEW_SCHEMA_ENTRY + new_content[schema_end2:]
    )

    import_anchor_text2, import_end2 = find_last_match(new_content, IMPORT_ANCHOR_PATTERNS)
    new_content = (
        new_content[:import_end2] + NEW_IMPORT + new_content[import_end2:]
    )

    with open(SERVER_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    print("Import de quantum_astro_tool insertado.")
    print("Dispatch elif de quantum_astro_tool insertado antes de distmesh_tool.")
    print("QUANTUM_ASTRO_TOOL_SCHEMA agregado a la lista de schemas.")

    try:
        py_compile.compile(SERVER_PATH, doraise=True)
        print("server.py actualizado y validado sintacticamente.")
    except py_compile.PyCompileError as e:
        print("ERROR de sintaxis tras el parche. Restaurando backup.")
        shutil.copy2(backup_name, SERVER_PATH)
        print(e)
        sys.exit(1)

    print()
    print("Smoke test (deberia dar [sx,sy] = 2i*sz y H_oscilador con eigenvalues 0.5,1.5,2.5,...):")
    print(
        '  echo \'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":'
        '{"name":"quantum_astro_tool","arguments":{"mode":"operator_algebra",'
        '"params":{"operation":"hamiltonian","hamiltonian_type":"harmonic_oscillator",'
        '"params":{"n_levels":5,"omega":1.0,"hbar":1.0}}}}}\' | timeout 30 python3 server.py'
    )


if __name__ == "__main__":
    main()
