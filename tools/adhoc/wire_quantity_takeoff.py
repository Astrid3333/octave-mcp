#!/usr/bin/env python3
"""
Wirea quantity_takeoff en server.py: import, entrada en TOOLS, y dispatch elif.
Hace backup timestamped antes de tocar nada. Usa asserts de anchor único
para no aplicar cambios si algo no calza exactamente.
"""
import shutil
import datetime

path = "server.py"
backup = f"{path}.bak.{datetime.datetime.now():%Y%m%d%H%M%S}"
shutil.copy(path, backup)
print(f"Backup creado: {backup}")

with open(path) as f:
    content = f.read()

# --- 1. import ---
anchor_import = "from financial_math_tool import compute_financial_math, FINANCIAL_MATH_TOOL_SCHEMA"
assert content.count(anchor_import) == 1, "anchor de import no encontrado o duplicado"
content = content.replace(
    anchor_import,
    anchor_import
    + "\nfrom quantity_takeoff_tool import compute_quantity_takeoff, QUANTITY_TAKEOFF_TOOL_SCHEMA",
)

# --- 2. entrada en TOOLS ---
anchor_tools = "    FINANCIAL_MATH_TOOL_SCHEMA,"
assert content.count(anchor_tools) == 1, "anchor de TOOLS no encontrado o duplicado"
content = content.replace(
    anchor_tools,
    anchor_tools + "\n    QUANTITY_TAKEOFF_TOOL_SCHEMA,",
)

# --- 3. dispatch elif ---
anchor_elif = (
    '            elif tool_name == "financial_math":\n'
    "                result = compute_financial_math(**args)\n"
    "                resp = {\n"
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    "                }"
)
assert content.count(anchor_elif) == 1, "anchor de dispatch no encontrado o duplicado"
new_elif = (
    "\n"
    '            elif tool_name == "quantity_takeoff":\n'
    "                result = compute_quantity_takeoff(**args)\n"
    "                resp = {\n"
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    "                }"
)
content = content.replace(anchor_elif, anchor_elif + new_elif)

with open(path, "w") as f:
    f.write(content)

print("OK: quantity_takeoff wireado en las 3 partes (import, TOOLS, dispatch).")
