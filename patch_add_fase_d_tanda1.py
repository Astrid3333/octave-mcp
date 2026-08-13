#!/usr/bin/env python3
"""
Patch: agrega los 3 tools de Fase D / Tanda 1 (motores fundacionales) a
octave-mcp/server.py:

  - personal_budget_tool   (presupuesto personal/domestico, sin dependencias)
  - savings_goal_tool      (motor de interes compuesto -- reutilizado despues
    por retirement_planner_tool, education_funding_tool, financial_independence_tool)
  - credit_simulation_tool (motor de amortizacion -- reutilizado despues por
    debt_snowball_tool y refinance_analysis_tool)

Mismo patron de 3 puntos (import, dispatch elif, lista de schemas) que
patch_add_acoustics_tool.py. Ancla en multivariate_bayes_tool, el ultimo
tool wireado en server.py al momento de escribir este patch.

Uso (dentro de ~/octave-mcp/):
    python3 patch_add_fase_d_tanda1.py
"""

import ast
import shutil
import time

SERVER_PATH = "server.py"

with open(SERVER_PATH, "r") as f:
    content = f.read()

ast.parse(content)

timestamp = time.strftime("%Y%m%d_%H%M%S")
backup_path = f"{SERVER_PATH}.bak_{timestamp}"
shutil.copy(SERVER_PATH, backup_path)
print(f"Backup: {backup_path}")

# ---------------------------------------------------------------------------
# 1. Imports
# ---------------------------------------------------------------------------

import_marker = "from multivariate_bayes_tool import compute_multivariate_bayes"
assert content.count(import_marker) == 1, "import_marker no encontrado exactamente 1 vez"

fase_d_imports = (
    "\nfrom personal_budget_tool import compute_personal_budget_tool, PERSONAL_BUDGET_TOOL_SCHEMA"
    "\nfrom savings_goal_tool import compute_savings_goal_tool, SAVINGS_GOAL_TOOL_SCHEMA"
    "\nfrom credit_simulation_tool import compute_credit_simulation_tool, CREDIT_SIMULATION_TOOL_SCHEMA"
)
if "from personal_budget_tool import" not in content:
    content = content.replace(import_marker, import_marker + fase_d_imports, 1)
    print("Imports de Fase D / Tanda 1 insertados.")
else:
    print("Imports de Fase D ya presentes, no se duplican.")

# ---------------------------------------------------------------------------
# 2. Lista de schemas (TOOLS)
# ---------------------------------------------------------------------------

schema_marker = "    KNOWLEDGE_GRAPH_TOOL_SCHEMA,\n"
assert content.count(schema_marker) == 1, "schema_marker no encontrado exactamente 1 vez"

fase_d_schemas = (
    "    PERSONAL_BUDGET_TOOL_SCHEMA,\n"
    "    SAVINGS_GOAL_TOOL_SCHEMA,\n"
    "    CREDIT_SIMULATION_TOOL_SCHEMA,\n"
)
if "PERSONAL_BUDGET_TOOL_SCHEMA," not in content.split("TOOLS = [", 1)[1].split("]", 1)[0]:
    content = content.replace(schema_marker, schema_marker + fase_d_schemas, 1)
    print("Schemas de Fase D / Tanda 1 agregados a la lista TOOLS.")
else:
    print("Schemas de Fase D ya presentes en TOOLS, no se duplican.")

# ---------------------------------------------------------------------------
# 3. Dispatch elif
# ---------------------------------------------------------------------------

dispatch_marker = (
    '                elif tool_name == "multivariate_bayes_tool":\n'
    '                    result = compute_multivariate_bayes(args.get("mode"), args.get("params"))\n'
    '                    resp = {\n'
    '                        "jsonrpc": "2.0", "id": req_id,\n'
    '                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                    }\n'
)
assert content.count(dispatch_marker) == 1, "dispatch_marker no encontrado exactamente 1 vez"

fase_d_dispatch_block = (
    '                elif tool_name == "personal_budget_tool":\n'
    '                    result = compute_personal_budget_tool(args.get("mode", "validate"), args.get("params"))\n'
    '                    resp = {\n'
    '                        "jsonrpc": "2.0", "id": req_id,\n'
    '                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                    }\n'
    '                elif tool_name == "savings_goal_tool":\n'
    '                    result = compute_savings_goal_tool(args.get("mode", "validate"), args.get("params"))\n'
    '                    resp = {\n'
    '                        "jsonrpc": "2.0", "id": req_id,\n'
    '                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                    }\n'
    '                elif tool_name == "credit_simulation_tool":\n'
    '                    result = compute_credit_simulation_tool(args.get("mode", "validate"), args.get("params"))\n'
    '                    resp = {\n'
    '                        "jsonrpc": "2.0", "id": req_id,\n'
    '                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                    }\n'
)
content = content.replace(dispatch_marker, dispatch_marker + fase_d_dispatch_block, 1)
print("Dispatch elif de Fase D / Tanda 1 insertado despues de multivariate_bayes_tool.")

# ---------------------------------------------------------------------------
# 4. Validar y escribir
# ---------------------------------------------------------------------------

ast.parse(content)
with open(SERVER_PATH, "w") as f:
    f.write(content)

print("server.py actualizado y validado sintacticamente.")
print("Tools agregados: personal_budget_tool, savings_goal_tool, credit_simulation_tool")
