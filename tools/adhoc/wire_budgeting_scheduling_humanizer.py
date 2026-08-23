#!/usr/bin/env python3
"""
Wirea budgeting_tool, construction_scheduling_tool y math_humanizer_tool en server.py:
import, entrada en TOOLS, y dispatch elif para cada uno. Hace UN solo backup timestamped
antes de tocar nada. Usa asserts de anchor único por cada tool para no aplicar cambios
parciales si algo no calza exactamente.
"""
import shutil
import datetime

path = "server.py"
backup = f"{path}.bak.{datetime.datetime.now():%Y%m%d%H%M%S}"
shutil.copy(path, backup)
print(f"Backup creado: {backup}")

with open(path) as f:
    content = f.read()

TOOLS_TO_WIRE = [
    {
        "import_line": "from earthworks_tool import compute_earthworks, EARTHWORKS_TOOL_SCHEMA",
        "new_import": "from budgeting_tool import compute_budgeting, BUDGETING_TOOL_SCHEMA",
        "tools_anchor": "    EARTHWORKS_TOOL_SCHEMA,",
        "new_tools_entry": "    BUDGETING_TOOL_SCHEMA,",
        "elif_anchor": (
            '            elif tool_name == "earthworks":\n'
            "                result = compute_earthworks(**args)\n"
            "                resp = {\n"
            '                    "jsonrpc": "2.0", "id": req_id,\n'
            '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
            "                }"
        ),
        "new_elif": (
            "\n"
            '            elif tool_name == "budgeting_tool":\n'
            "                result = compute_budgeting(**args)\n"
            "                resp = {\n"
            '                    "jsonrpc": "2.0", "id": req_id,\n'
            '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
            "                }"
        ),
    },
    {
        "import_line": "from budgeting_tool import compute_budgeting, BUDGETING_TOOL_SCHEMA",
        "new_import": "from construction_scheduling_tool import compute_construction_scheduling, CONSTRUCTION_SCHEDULING_TOOL_SCHEMA",
        "tools_anchor": "    BUDGETING_TOOL_SCHEMA,",
        "new_tools_entry": "    CONSTRUCTION_SCHEDULING_TOOL_SCHEMA,",
        "elif_anchor": (
            '            elif tool_name == "budgeting_tool":\n'
            "                result = compute_budgeting(**args)\n"
            "                resp = {\n"
            '                    "jsonrpc": "2.0", "id": req_id,\n'
            '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
            "                }"
        ),
        "new_elif": (
            "\n"
            '            elif tool_name == "construction_scheduling_tool":\n'
            "                result = compute_construction_scheduling(**args)\n"
            "                resp = {\n"
            '                    "jsonrpc": "2.0", "id": req_id,\n'
            '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
            "                }"
        ),
    },
    {
        "import_line": "from construction_scheduling_tool import compute_construction_scheduling, CONSTRUCTION_SCHEDULING_TOOL_SCHEMA",
        "new_import": "from math_humanizer_tool import compute_math_humanizer, MATH_HUMANIZER_TOOL_SCHEMA",
        "tools_anchor": "    CONSTRUCTION_SCHEDULING_TOOL_SCHEMA,",
        "new_tools_entry": "    MATH_HUMANIZER_TOOL_SCHEMA,",
        "elif_anchor": (
            '            elif tool_name == "construction_scheduling_tool":\n'
            "                result = compute_construction_scheduling(**args)\n"
            "                resp = {\n"
            '                    "jsonrpc": "2.0", "id": req_id,\n'
            '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
            "                }"
        ),
        "new_elif": (
            "\n"
            '            elif tool_name == "math_humanizer_tool":\n'
            "                result = compute_math_humanizer(**args)\n"
            "                resp = {\n"
            '                    "jsonrpc": "2.0", "id": req_id,\n'
            '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
            "                }"
        ),
    },
]

for spec in TOOLS_TO_WIRE:
    assert content.count(spec["import_line"]) == 1, f"anchor de import no encontrado o duplicado: {spec['new_import']}"
    content = content.replace(spec["import_line"], spec["import_line"] + "\n" + spec["new_import"])

    assert content.count(spec["tools_anchor"]) == 1, f"anchor de TOOLS no encontrado o duplicado: {spec['new_tools_entry']}"
    content = content.replace(spec["tools_anchor"], spec["tools_anchor"] + "\n" + spec["new_tools_entry"])

    assert content.count(spec["elif_anchor"]) == 1, f"anchor de dispatch no encontrado o duplicado: {spec['new_elif']}"
    content = content.replace(spec["elif_anchor"], spec["elif_anchor"] + spec["new_elif"])

with open(path, "w") as f:
    f.write(content)

print("OK: budgeting_tool, construction_scheduling_tool y math_humanizer_tool wireados (import, TOOLS, dispatch cada uno).")
