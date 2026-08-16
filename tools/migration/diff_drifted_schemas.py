#!/usr/bin/env python3
"""
Para los tools marcados con DRIFT por verify_preexisting_schemas.py,
imprime lado a lado el inputSchema que hoy expone TOOLS[] en server.py
(lo que el cliente MCP realmente ve) contra el contenido de la constante
interna del modulo (que podria ser mas nueva, mas vieja, o simplemente
distinta por otra razon). No decide nada -- solo muestra el diff para que
elijas cual es la version correcta antes de la Fase 3.
"""
import re
import ast
import json
import difflib

with open("server.py") as f:
    server_content = f.read()

with open("schema_extraction_plan.json") as f:
    plan_data = json.load(f)
plan = plan_data["plan"]

name_anchor = re.compile(r'\{\s*\n?\s*"name":\s*"(\w+)"')
tools_dict = {}
for m in name_anchor.finditer(server_content):
    start = m.start()
    name = m.group(1)
    depth = 0
    i = start
    end = None
    in_string = False
    escape = False
    while i < len(server_content):
        c = server_content[i]
        if in_string:
            if escape:
                escape = False
            elif c == '\\':
                escape = True
            elif c == '"':
                in_string = False
        else:
            if c == '"':
                in_string = True
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        i += 1
    if end is None:
        continue
    try:
        tools_dict[name] = ast.literal_eval(server_content[start:end])
    except (ValueError, SyntaxError):
        pass


def extract_constant_from_module_source(module_path, const_name):
    with open(module_path) as f:
        src = f.read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == const_name:
                    try:
                        return ast.literal_eval(node.value)
                    except (ValueError, SyntaxError):
                        return None
    return None


for entry in plan:
    tool_name = entry["tool_name"]
    module = entry["module"]
    const_name = entry["schema_const_name"]
    module_path = f"{module}.py"

    existing_value = extract_constant_from_module_source(module_path, const_name)
    if existing_value is None:
        continue

    expected_schema = tools_dict.get(tool_name, {}).get("inputSchema")
    if existing_value == expected_schema:
        continue

    print(f"\n{'='*70}")
    print(f"DRIFT: {tool_name}  ({module_path} / {const_name})")
    print('='*70)

    tools_json = json.dumps(expected_schema, indent=2, ensure_ascii=False, sort_keys=True)
    const_json = json.dumps(existing_value, indent=2, ensure_ascii=False, sort_keys=True)

    diff = list(difflib.unified_diff(
        tools_json.splitlines(),
        const_json.splitlines(),
        fromfile="TOOLS[] (lo que el cliente MCP ve hoy)",
        tofile=f"{const_name} (constante interna del modulo)",
        lineterm=""
    ))
    if diff:
        print("\n".join(diff))
    else:
        print("(mismo contenido pero distinto orden de keys / tipos -- revisar a mano)")
