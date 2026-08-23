#!/usr/bin/env python3
"""
patch_server_v2.py
Wirea multibody_dynamics_tool, particle_simulation_tool, finite_element_tool
en server.py usando anclas LITERALES tomadas directamente de tu archivo real
(no markers inventados). Hace backup con timestamp antes de escribir y valida
sintaxis con ast.parse al final.

Uso:
  cd ~/octave-mcp
  python3 patch_server_v2.py server.py
"""
import sys
import shutil
import time
import ast

IMPORT_ANCHOR = 'from text_analysis_math_tool import compute_text_analysis_math, TEXT_ANALYSIS_MATH_TOOL_SCHEMA\n'
NEW_IMPORTS = (
    'from multibody_dynamics_tool import compute_multibody_dynamics, MULTIBODY_DYNAMICS_TOOL_SCHEMA\n'
    'from particle_simulation_tool import compute_particle_simulation, PARTICLE_SIMULATION_TOOL_SCHEMA\n'
    'from finite_element_tool import compute_finite_element, FINITE_ELEMENT_TOOL_SCHEMA\n'
)

SCHEMA_ANCHOR = '    TEXT_ANALYSIS_MATH_TOOL_SCHEMA,\n'
NEW_SCHEMAS = (
    '    MULTIBODY_DYNAMICS_TOOL_SCHEMA,\n'
    '    PARTICLE_SIMULATION_TOOL_SCHEMA,\n'
    '    FINITE_ELEMENT_TOOL_SCHEMA,\n'
)

DISPATCH_ANCHOR = (
    '            elif tool_name == "numeral_systems_embedding":\n'
    '                result = compute_numeral_systems_embedding(**args)\n'
    '                resp = {\n'
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                }\n'
    '            else:\n'
)
NEW_DISPATCH = (
    '            elif tool_name == "multibody_dynamics_tool":\n'
    '                result = compute_multibody_dynamics(**args)\n'
    '                resp = {\n'
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                }\n'
    '            elif tool_name == "particle_simulation_tool":\n'
    '                result = compute_particle_simulation(**args)\n'
    '                resp = {\n'
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                }\n'
    '            elif tool_name == "finite_element_tool":\n'
    '                result = compute_finite_element(**args)\n'
    '                resp = {\n'
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                }\n'
    '            else:\n'
)


def main():
    if len(sys.argv) != 2:
        print("uso: python3 patch_server_v2.py server.py")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    backup_path = f"{path}.bak.{int(time.time())}"
    shutil.copy2(path, backup_path)
    print(f"backup creado: {backup_path}")

    already_wired = "multibody_dynamics_tool" in content and "compute_multibody_dynamics" in content
    if already_wired:
        print("[abort] parece que ya esta wireado (encontre 'compute_multibody_dynamics' en el archivo). No toco nada.")
        sys.exit(0)

    assert content.count(IMPORT_ANCHOR) == 1, "ancla de imports no encontrada o duplicada"
    content = content.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORTS, 1)

    assert content.count(SCHEMA_ANCHOR) == 1, "ancla de schema no encontrada o duplicada"
    content = content.replace(SCHEMA_ANCHOR, SCHEMA_ANCHOR + NEW_SCHEMAS, 1)

    assert content.count(DISPATCH_ANCHOR) == 1, "ancla de dispatch no encontrada o duplicada"
    content = content.replace(DISPATCH_ANCHOR, NEW_DISPATCH, 1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    ast.parse(content)
    print("server.py parcheado OK, sintaxis validada.")
    print("3 tools nuevos: multibody_dynamics_tool, particle_simulation_tool, finite_element_tool")
    print("Reiniciar el server MCP para que tomen efecto.")


if __name__ == "__main__":
    main()
