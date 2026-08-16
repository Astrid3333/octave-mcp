#!/usr/bin/env python3
"""
Fase 3 -- SOLO PLAN, no escribe nada.

register_tool() exige schema = entrada completa {"name","description",
"inputSchema"} con schema["name"] == name (si no, tira ValueError). Nuestras
46 constantes son inputSchema pelado (las 24 nuevas de Fase 2, y las 18 con
"drift real" que resultaron ser la version mas rica/correcta). Las 4 que ya
tenian forma de entrada completa (workspace_link, workspace_describe,
workspace_delete, disaster_simulation_tool) se usan tal cual.

Para cada uno de los 46:
  1. Re-deriva handler_style leyendo el elif real en server.py (mode_params
     vs kwargs), reusando literalmente la expresion de la llamada (asi no
     hay que adivinar el orden de argumentos).
  2. Lee la constante actual del modulo y detecta su forma (bare vs full-entry).
  3. Arma el bloque de codigo register_tool() a agregar al modulo:
     - si es full-entry con name correcto: schema=CONST_NAME directo
     - si es full-entry con name desalineado: schema={**CONST_NAME, "name": "..."}
     - si es bare: schema={"name": "...", "description": "...", "inputSchema": CONST_NAME}
  4. Calcula el span exacto a borrar de TOOLS[] (brace-matching) y del elif
     (mismo patron ya usado en toda la migracion) -- pero NO los borra, solo
     los guarda en el plan para inspeccion.
  5. Chequea si, tras migrar todos los tools de un modulo, el import en
     server.py puede pasar a "import modulo  # auto-registra..." (silencioso)
     -- es decir, si ningun otro simbolo de ese modulo (fuera de los que se
     migran) se sigue usando en server.py.

Guarda todo en phase3_plan.json e imprime un resumen. Revisar antes de pedir
el script que aplica.
"""
import re
import ast
import json

with open("server.py") as f:
    server_content = f.read()

with open("schema_extraction_plan.json") as f:
    plan_data = json.load(f)
plan_entries = plan_data["plan"]

name_anchor = re.compile(r'\{\s*\n?\s*"name":\s*"(\w+)"')
tools_dict = {}
tools_spans = {}
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
        tools_spans[name] = (start, end)
    except (ValueError, SyntaxError):
        pass

elif_pattern = re.compile(
    r'( {16}elif tool_name == "(\w+)":\n(?:(?! {16}elif| {16}else).*\n)*)'
)
elif_spans = {}
for m in elif_pattern.finditer(server_content):
    block, tool_name = m.group(1), m.group(2)
    elif_spans[tool_name] = (m.start(), m.end(), block)

result_call_pattern = re.compile(r'result = (.+?)\n')


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
                        return "<dinamico>"
    return None


FULL_ENTRY_KEYS = {"name", "description", "inputSchema"}

phase3_plan = []
problems = []

for entry in plan_entries:
    tool_name = entry["tool_name"]
    module = entry["module"]
    func_name = entry["func_name"]
    const_name = entry["schema_const_name"]
    module_path = f"{module}.py"
    description = entry["description"]

    if tool_name not in elif_spans:
        problems.append((tool_name, "no se encontro elif en server.py (raro, revisar a mano)"))
        continue
    _, _, block = elif_spans[tool_name]
    m = result_call_pattern.search(block)
    if not m:
        problems.append((tool_name, "no se encontro 'result = ...' en su elif"))
        continue
    call_expr = m.group(1).strip()

    current_value = extract_constant_from_module_source(module_path, const_name)
    if current_value is None:
        problems.append((tool_name, f"no se encontro la constante {const_name} en {module_path} (raro, deberia existir tras Fase 2)"))
        continue
    if current_value == "<dinamico>":
        problems.append((tool_name, f"{const_name} no es un literal simple, revisar a mano"))
        continue

    is_full_entry = isinstance(current_value, dict) and FULL_ENTRY_KEYS.issubset(current_value.keys())

    if is_full_entry:
        if current_value.get("name") != tool_name:
            schema_arg_code = f'{{**{const_name}, "name": "{tool_name}"}}'
        else:
            schema_arg_code = const_name
    else:
        schema_arg_code = (
            "{\n"
            f'        "name": "{tool_name}",\n'
            f'        "description": {description!r},\n'
            f"        \"inputSchema\": {const_name},\n"
            "    }"
        )

    register_block = (
        f'\ntry:\n'
        f'    from tool_registry import register_tool\n'
        f'    register_tool(\n'
        f'        name="{tool_name}",\n'
        f'        schema={schema_arg_code},\n'
        f'        handler=lambda args: {call_expr},\n'
        f'    )\n'
        f'except ImportError:\n'
        f'    pass\n'
    )

    tools_start, tools_end = tools_spans.get(tool_name, (None, None))
    elif_start, elif_end, _ = elif_spans[tool_name]

    phase3_plan.append({
        "tool_name": tool_name,
        "module": module,
        "func_name": func_name,
        "const_name": const_name,
        "is_full_entry": is_full_entry,
        "call_expr": call_expr,
        "register_block": register_block,
        "tools_span": [tools_start, tools_end],
        "elif_span": [elif_start, elif_end],
    })

print(f"=== {len(phase3_plan)} tools con plan de Fase 3 listo ===")
print(f"=== {len(problems)} con problemas (revisar antes de aplicar) ===\n")
for tool_name, reason in problems:
    print(f"  PROBLEMA: {tool_name}: {reason}")

with open("phase3_plan.json", "w") as f:
    json.dump({"plan": phase3_plan, "problems": problems}, f, indent=2, ensure_ascii=False)

print(f"\nPlan guardado en phase3_plan.json")

example_full = next((p for p in phase3_plan if p["is_full_entry"]), None)
example_bare = next((p for p in phase3_plan if not p["is_full_entry"]), None)

for label, ex in (("EJEMPLO full-entry (constante ya lista)", example_full), ("EJEMPLO bare inputSchema (se envuelve inline)", example_bare)):
    if ex:
        print(f"\n--- {label}: {ex['tool_name']} ({ex['module']}.py) ---")
        print(ex["register_block"])
