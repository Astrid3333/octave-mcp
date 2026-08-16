#!/usr/bin/env python3
import re
import json

with open("server.py") as f:
    content = f.read()

# 1) mapa symbol -> modulo, a partir de todos los "from X import a, b, c"
import_pattern = re.compile(r'^from (\w+) import (.+)$', re.MULTILINE)
symbol_to_module = {}
module_symbols = {}
for m in import_pattern.finditer(content):
    module, symbols_str = m.group(1), m.group(2)
    symbols = [s.strip() for s in symbols_str.split(',')]
    module_symbols[module] = symbols
    for s in symbols:
        symbol_to_module.setdefault(s, []).append(module)

# 2) modulos ya migrados (import mudo) -- excluir del plan
migrated_pattern = re.compile(r'^import (\w+)  # auto-registra', re.MULTILINE)
already_migrated_modules = set(migrated_pattern.findall(content))

# 3) bloques elif completos, capturados atomicamente
elif_pattern = re.compile(
    r'( {16}elif tool_name == "(\w+)":\n(?:(?! {16}elif| {16}else).*\n)*)'
)
elif_blocks = elif_pattern.findall(content)

plan = []
conflicts = []
seen_tool_names = set()

for full_block, tool_name in elif_blocks:
    if tool_name in seen_tool_names:
        conflicts.append({"tool_name": tool_name, "reason": "elif duplicado en el dispatcher"})
        continue
    seen_tool_names.add(tool_name)

    result_match = re.search(r'result = (\w+)\((.*?)\)\n', full_block)
    if not result_match:
        conflicts.append({"tool_name": tool_name, "reason": "no se encontro 'result = FUNC(...)' -- forma atipica (ej. output=..., handle_X(args))"})
        continue

    func_name, call_args = result_match.group(1), result_match.group(2)

    if 'args.get("mode"' in call_args and 'args.get("params")' in call_args:
        handler_style = "mode_params"
    elif call_args.strip() == "**args":
        handler_style = "kwargs"
    else:
        conflicts.append({"tool_name": tool_name, "reason": f"firma atipica: {func_name}({call_args})"})
        continue

    candidate_modules = symbol_to_module.get(func_name, [])
    candidate_modules = [m for m in candidate_modules if m not in already_migrated_modules]

    if len(candidate_modules) == 0:
        conflicts.append({"tool_name": tool_name, "reason": f"funcion '{func_name}' no encontrada en ningun import (ya migrada o inexistente)"})
        continue
    if len(candidate_modules) > 1:
        conflicts.append({"tool_name": tool_name, "reason": f"funcion '{func_name}' ambigua, aparece en modulos: {candidate_modules}"})
        continue

    module = candidate_modules[0]
    schema_candidates = [s for s in module_symbols[module] if 'SCHEMA' in s]

    if len(schema_candidates) == 0:
        conflicts.append({"tool_name": tool_name, "reason": f"modulo '{module}' no tiene ninguna constante SCHEMA en su import"})
        continue
    if len(schema_candidates) > 1:
        conflicts.append({"tool_name": tool_name, "reason": f"modulo '{module}' tiene MULTIPLES schemas: {schema_candidates} -- requiere revision manual (multi-tool module)"})
        continue

    schema_const = schema_candidates[0]

    plan.append({
        "tool_name": tool_name,
        "module": module,
        "func_name": func_name,
        "schema_const": schema_const,
        "handler_style": handler_style,
    })

print(f"=== {len(plan)} tools con plan de migracion LIMPIO ===")
print(f"=== {len(conflicts)} tools con CONFLICTO (requieren revision manual) ===\n")

for c in conflicts:
    print(f"  CONFLICTO: {c['tool_name']}: {c['reason']}")

with open("migration_plan.json", "w") as f:
    json.dump({"plan": plan, "conflicts": conflicts}, f, indent=2, ensure_ascii=False)

print(f"\nPlan guardado en migration_plan.json ({len(plan)} listos, {len(conflicts)} conflictos)")
