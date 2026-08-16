#!/usr/bin/env python3
"""
Compara, para los tools cuya constante _SCHEMA YA EXISTIA en el modulo
(no fue creada por apply_schema_extraction.py), el contenido de esa
constante preexistente contra el inputSchema que TOOLS[] expone hoy en
server.py. Si difieren, hay drift: la constante del modulo quedo
desactualizada respecto a lo que el cliente MCP realmente ve.

Usa el mismo brace-matching de build_schema_extraction_plan.py para leer
TOOLS[], y ast.literal_eval sobre el modulo para leer la constante real
(ejecutando el archivo del modulo de forma aislada via ast, sin importarlo
como modulo real, para no disparar sus side-effects/dependencias pesadas
como scipy/octave).
"""
import re
import ast
import json

with open("server.py") as f:
    server_content = f.read()

with open("schema_extraction_plan.json") as f:
    plan_data = json.load(f)
plan = plan_data["plan"]

# --- reconstruir tools_dict desde TOOLS[] (brace-matching, igual que antes) ---
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
                        return "<no literal, valor calculado dinamicamente>"
    return None


mismatches = []
matches = []
checked = 0

for entry in plan:
    tool_name = entry["tool_name"]
    module = entry["module"]
    const_name = entry["schema_const_name"]
    module_path = f"{module}.py"

    existing_value = extract_constant_from_module_source(module_path, const_name)
    if existing_value is None:
        continue

    checked += 1
    expected_schema = tools_dict.get(tool_name, {}).get("inputSchema")

    if existing_value == "<no literal, valor calculado dinamicamente>":
        mismatches.append((tool_name, module, const_name, "la constante preexistente no es un literal simple, no se pudo comparar automaticamente"))
        continue

    if existing_value == expected_schema:
        matches.append((tool_name, module, const_name))
    else:
        mismatches.append((tool_name, module, const_name, "CONTENIDO DISTINTO al inputSchema actual de TOOLS[]"))

print(f"=== {checked} constantes preexistentes revisadas ===")
print(f"=== {len(matches)} coinciden exactamente con TOOLS[] ===")
print(f"=== {len(mismatches)} tienen DRIFT (revisar antes de usarlas) ===\n")

for tool_name, module, const_name, reason in mismatches:
    print(f"  DRIFT: {tool_name} ({module}.py / {const_name}): {reason}")

if matches:
    print("\nOK (sin drift):")
    for tool_name, module, const_name in matches:
        print(f"  {tool_name} ({module}.py / {const_name})")
