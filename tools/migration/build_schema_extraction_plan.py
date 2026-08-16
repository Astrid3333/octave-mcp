#!/usr/bin/env python3
"""
Fase 2 del plan de migracion a tool_registry -- v2.

Diferencia con v1: en vez de un regex de una sola linea para las entradas
de TOOLS[], usa brace-matching real. v1 fallaba en climate_tool,
advanced_stochastic_tool y multivariate_bayes_tool porque esas 3 entradas
estan escritas en varias lineas (confirmado con grep: '"name": "climate_tool",'
esta solo en la linea 356, el resto del dict sigue despues).
"""
import re
import ast
import json

with open("server.py") as f:
    content = f.read()

# --- 1) encontrar cada entrada de TOOLS[] por brace-matching ---
name_anchor = re.compile(r'\{\s*\n?\s*"name":\s*"(\w+)"')

tools_dict = {}
unparsed = []

for m in name_anchor.finditer(content):
    start = m.start()
    name = m.group(1)
    depth = 0
    i = start
    end = None
    in_string = False
    escape = False
    while i < len(content):
        c = content[i]
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
        unparsed.append((name, "no se encontro cierre balanceado"))
        continue
    literal = content[start:end]
    try:
        parsed = ast.literal_eval(literal)
        tools_dict[name] = parsed
    except (ValueError, SyntaxError) as e:
        unparsed.append((name, str(e)))

print(f"=== {len(tools_dict)} entradas de TOOLS[] parseadas OK (brace-matching) ===")
if unparsed:
    print(f"=== {len(unparsed)} entradas NO se pudieron parsear ===")
    for n, reason in unparsed:
        print(f"  - {n}: {reason}")

with open("migration_plan.json") as f:
    mp = json.load(f)

schema_conflicts = [
    c for c in mp["conflicts"]
    if "no tiene ninguna constante SCHEMA en su import" in c["reason"]
]

import_pattern = re.compile(r'^from (\w+) import (.+)$', re.MULTILINE)
symbol_to_module = {}
for m in import_pattern.finditer(content):
    module, symbols_str = m.group(1), m.group(2)
    for s in symbols_str.split(','):
        symbol_to_module.setdefault(s.strip(), []).append(module)

elif_pattern = re.compile(
    r' {16}elif tool_name == "(\w+)":\n {20}result = (\w+)\('
)
tool_to_func = dict(elif_pattern.findall(content))

plan = []
still_conflict = []

for c in schema_conflicts:
    tool_name = c["tool_name"]
    if tool_name not in tools_dict:
        still_conflict.append({"tool_name": tool_name, "reason": "no aparece como entrada de TOOLS[] tampoco (revisar a mano)"})
        continue

    func_name = tool_to_func.get(tool_name)
    if not func_name:
        still_conflict.append({"tool_name": tool_name, "reason": "no se encontro func_name en el dispatch"})
        continue

    candidate_modules = symbol_to_module.get(func_name, [])
    if len(candidate_modules) != 1:
        still_conflict.append({"tool_name": tool_name, "reason": f"funcion '{func_name}' no resuelve a exactamente 1 modulo: {candidate_modules}"})
        continue

    module = candidate_modules[0]
    tool_entry = tools_dict[tool_name]
    schema = tool_entry.get("inputSchema", {})
    description = tool_entry.get("description", "")
    schema_const_name = tool_name.upper() + "_SCHEMA"

    plan.append({
        "tool_name": tool_name,
        "module": module,
        "func_name": func_name,
        "schema_const_name": schema_const_name,
        "description": description,
        "schema": schema,
    })

print(f"\n=== {len(plan)} tools con plan de EXTRACCION DE SCHEMA listo ===")
print(f"=== {len(still_conflict)} siguen en conflicto ===\n")
for c in still_conflict:
    print(f"  CONFLICTO: {c['tool_name']}: {c['reason']}")

with open("schema_extraction_plan.json", "w") as f:
    json.dump({"plan": plan, "still_conflict": still_conflict}, f, indent=2, ensure_ascii=False)

print(f"\nPlan guardado en schema_extraction_plan.json ({len(plan)} listos, {len(still_conflict)} conflictos)")

for tn in ("climate_tool", "advanced_stochastic_tool", "multivariate_bayes_tool"):
    entry = next((p for p in plan if p["tool_name"] == tn), None)
    if entry:
        print(f"\n--- {tn}: RESUELTO -> {entry['schema_const_name']} en {entry['module']}.py ---")
    else:
        print(f"\n--- {tn}: SIGUE EN CONFLICTO ---")
