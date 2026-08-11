"""
Wirea biorefinery_tool.py en server.py: import, dispatch elif, schema en TOOLS.
Backup timestamped + asserts de unicidad.
"""
import shutil
from datetime import datetime

SERVER = "server.py"

with open(SERVER, "r") as f:
    content = f.read()

backup_name = f"{SERVER}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
shutil.copy(SERVER, backup_name)
print(f"Backup: {backup_name}")

# 1. Import (despues del import de knowledge_graph_tool, ya wireado)
import_marker = "from knowledge_graph_tool import compute_knowledge_graph, KNOWLEDGE_GRAPH_TOOL_SCHEMA\n"
assert content.count(import_marker) == 1, "import_marker (knowledge_graph_tool) no encontrado o no unico"
content = content.replace(
    import_marker,
    import_marker + "from biorefinery_tool import compute_biorefinery, BIOREFINERY_TOOL_SCHEMA\n",
)
print("Import de biorefinery_tool insertado.")

# 2. Dispatch elif (despues del bloque de knowledge_graph_tool)
dispatch_marker = (
    '            elif tool_name == "knowledge_graph_tool":\n'
    '                result = compute_knowledge_graph(args.get("mode"), args.get("params"), tools=TOOLS)\n'
    "                resp = {\n"
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    "                }\n"
)
assert content.count(dispatch_marker) == 1, "dispatch_marker (knowledge_graph_tool) no encontrado o no unico"
new_elif = (
    '            elif tool_name == "biorefinery_tool":\n'
    '                result = compute_biorefinery(args.get("mode"), args.get("params"))\n'
    "                resp = {\n"
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    "                }\n"
)
content = content.replace(dispatch_marker, dispatch_marker + new_elif)
print("Dispatch elif de biorefinery_tool insertado despues de knowledge_graph_tool.")

# 3. Schema en TOOLS list
schema_marker = "    KNOWLEDGE_GRAPH_TOOL_SCHEMA,\n]"
assert content.count(schema_marker) == 1, "schema_marker (KNOWLEDGE_GRAPH_TOOL_SCHEMA) no encontrado o no unico"
content = content.replace(
    schema_marker,
    "    KNOWLEDGE_GRAPH_TOOL_SCHEMA,\n    BIOREFINERY_TOOL_SCHEMA,\n]",
)
print("BIOREFINERY_TOOL_SCHEMA agregado a la lista de schemas.")

with open(SERVER, "w") as f:
    f.write(content)

import ast
ast.parse(content)
print("server.py actualizado y validado sintacticamente.")
