#!/usr/bin/env python3
"""Wirea climate_scenario_tool en server.py, con el patron REAL confirmado
contra tu repo (schema inline en TOOLS[], compute_X(mode, params), resp
propio por rama). Hace backup automatico antes de tocar nada."""
import re
import shutil
import time

TARGET = "server.py"

with open(TARGET, encoding="utf-8") as f:
    content = f.read()

backup_name = f"{TARGET}.bak.{time.strftime('%Y%m%d%H%M%S')}"
shutil.copyfile(TARGET, backup_name)

changes = 0

# 1) Import (sin SCHEMA, patron de las tools mas recientes: early_warning_tool, etc.)
import_line = "from climate_scenario_tool import compute_climate_scenario\n"
if "from climate_scenario_tool import" not in content:
    import_matches = list(re.finditer(r"^from \w+_tool import .*$", content, re.MULTILINE))
    if not import_matches:
        raise RuntimeError("No encontre ningun 'from X_tool import ...' para anclar el nuevo import")
    last_import = import_matches[-1]
    insert_at = last_import.end()
    content = content[:insert_at] + "\n" + import_line.rstrip("\n") + content[insert_at:]
    changes += 1
else:
    print("Import ya presente, no se duplica.")

# 2) Entrada en TOOLS = [...] (schema inline, mismo formato que early_warning_tool)
if '"name": "climate_scenario_tool"' not in content:
    tools_match = re.search(r"TOOLS\s*=\s*\[", content)
    if not tools_match:
        raise RuntimeError("No encontre 'TOOLS = [' para insertar el schema")
    insert_at = tools_match.end()
    schema_entry = (
        '\n    {"name": "climate_scenario_tool", '
        '"description": "Analisis de escenarios climaticos: trend_analysis '
        '(regresion lineal, Mann-Kendall, changepoint CUSUM sobre series '
        'temporales), rcp_projection (proyeccion de temperatura/nivel del mar '
        'para un RCP y anio dado), list_rcp_scenarios (catalogo RCP2.6/4.5/6.0/8.5 '
        'con datos IPCC AR5), validate.", '
        '"inputSchema": {"type": "object", "properties": '
        '{"mode": {"type": "string"}, "params": {"type": "object"}}, '
        '"required": ["mode"]}},'
    )
    content = content[:insert_at] + schema_entry + content[insert_at:]
    changes += 1
else:
    print("Entrada en TOOLS ya presente, no se duplica.")

# 3) Bloque de dispatch: mismo patron de 4 lineas que las tools recientes
#    (elif ... : result = compute_X(args.get("mode"), args.get("params")); resp propio)
if 'tool_name == "climate_scenario_tool"' not in content:
    anchor = 'elif tool_name == "early_warning_tool":'
    anchor_idx = content.find(anchor)
    if anchor_idx == -1:
        m = re.search(
            r'elif tool_name == "[a-zA-Z_]+_tool":\n\s*result = compute_\w+\(args\.get\("mode"\), args\.get\("params"\)\)\n\s*resp = \{\n(?:.*\n)*?\s*\}\n',
            content,
        )
        if not m:
            raise RuntimeError("No encontre un bloque de dispatch existente para anclar el nuevo")
        insert_at = m.end()
    else:
        # Retrocedemos al inicio de la linea (antes de la indentacion existente),
        # para no duplicar/perder espacios al insertar.
        insert_at = content.rfind("\n", 0, anchor_idx) + 1

    indent = "                "  # 16 espacios, igual que el resto de las ramas elif
    new_block = (
        f'{indent}elif tool_name == "climate_scenario_tool":\n'
        f'{indent}    result = compute_climate_scenario(args.get("mode"), args.get("params"))\n'
        f'{indent}    resp = {{\n'
        f'{indent}        "jsonrpc": "2.0", "id": req_id,\n'
        f'{indent}        "result": {{"content": [{{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}}]}},\n'
        f'{indent}    }}\n'
    )
    content = content[:insert_at] + new_block + content[insert_at:]
    changes += 1
else:
    print("Bloque de dispatch ya presente, no se duplica.")

with open(TARGET, "w", encoding="utf-8") as f:
    f.write(content)

print(f"Backup: {backup_name}")
print(f"Patch aplicado: {changes} inserciones (import, TOOLS, dispatch).")
