#!/usr/bin/env python3
"""
v2: antes de comparar, detecta la FORMA de la constante preexistente.

Descubrimos con workspace_link que algunas constantes _SCHEMA no guardan
un inputSchema pelado (type/properties/required) sino la ENTRADA COMPLETA
al estilo TOOLS[] (name/description/inputSchema). Compararlas directo contra
el inputSchema de TOOLS[] da un falso "drift" que en realidad es solo una
diferencia de forma, no de contenido.

Este script clasifica cada uno de los 22 drift en 3 categorias:
  A) MISMA FORMA, CONTENIDO DISTINTO -- drift real, hay que decidir cual usar
  B) CONSTANTE ES ENTRADA COMPLETA -- extrae su ["inputSchema"] interno y
     compara ESO contra TOOLS[]; si coincide, no es drift real, solo forma
  C) FORMA IRRECONOCIBLE -- no tiene ni pinta de inputSchema ni de entrada
     completa, hay que mirarla a mano
"""
import re
import ast
import json

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


INPUTSCHEMA_KEYS = {"type", "properties", "required"}
FULL_ENTRY_KEYS = {"name", "description", "inputSchema"}

real_drift = []
shape_only = []
unrecognized = []
checked = 0

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

    checked += 1

    if not isinstance(existing_value, dict):
        unrecognized.append((tool_name, module, const_name, "la constante no es un dict"))
        continue

    keys = set(existing_value.keys())

    if keys and keys.issubset(INPUTSCHEMA_KEYS) or "properties" in keys:
        real_drift.append((tool_name, module, const_name, existing_value, expected_schema))
    elif FULL_ENTRY_KEYS.issubset(keys):
        inner_schema = existing_value.get("inputSchema")
        if inner_schema == expected_schema:
            shape_only.append((tool_name, module, const_name))
        else:
            real_drift.append((tool_name, module, const_name, inner_schema, expected_schema))
    else:
        unrecognized.append((tool_name, module, const_name, f"keys no reconocidas: {sorted(keys)}"))

print(f"=== {checked} tools con drift original re-clasificados ===\n")
print(f"=== {len(shape_only)} eran solo diferencia de FORMA (entrada completa vs inputSchema pelado) -- sin drift real de contenido ===")
for tool_name, module, const_name in shape_only:
    print(f"  OK (solo forma): {tool_name} ({module}.py / {const_name})")

print(f"\n=== {len(real_drift)} tienen DRIFT REAL de contenido (revisar) ===")
for tool_name, module, const_name, existing, expected in real_drift:
    print(f"\n  --- {tool_name} ({module}.py / {const_name}) ---")
    print(f"  TOOLS[] hoy expone:   {json.dumps(expected, ensure_ascii=False)}")
    print(f"  constante interna:    {json.dumps(existing, ensure_ascii=False)}")

if unrecognized:
    print(f"\n=== {len(unrecognized)} con forma IRRECONOCIBLE (mirar a mano) ===")
    for tool_name, module, const_name, reason in unrecognized:
        print(f"  {tool_name} ({module}.py / {const_name}): {reason}")
