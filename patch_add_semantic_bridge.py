#!/usr/bin/env python3
"""
Integra semantic_bridge en server.py en 3 puntos, clonando exactamente
el patron ya usado para knowledge_graph_tool (que tampoco pasa por
tool_registry.register_tool porque necesita 'tools=TOOLS' inyectado):

  1. Import: agrega la linea de import justo despues de la de
     knowledge_graph_tool (linea ~167).
  2. TOOLS: agrega SEMANTIC_BRIDGE_TOOL_SCHEMA justo despues de
     KNOWLEDGE_GRAPH_TOOL_SCHEMA dentro del array TOOLS (linea ~346).
  3. Dispatch: agrega un elif tool_name == "semantic_bridge" justo
     despues del de knowledge_graph_tool (linea ~1405), con la misma
     forma de invocacion (result = compute_semantic_bridge(mode, params,
     tools=TOOLS)).

Cada bloque se busca por match unico. Si CUALQUIERA de los 3 no da
match exacto (0 o 2+ veces), aborta sin escribir nada -- no hay
assert mudo, se imprime el reporte completo para revisar a mano.
"""
import shutil
import sys
from datetime import datetime

TARGET = "server.py"

PATCHES = [
    {
        "label": "import",
        "old": (
            "from knowledge_graph_tool import compute_knowledge_graph, "
            "KNOWLEDGE_GRAPH_TOOL_SCHEMA\n"
        ),
        "new": (
            "from knowledge_graph_tool import compute_knowledge_graph, "
            "KNOWLEDGE_GRAPH_TOOL_SCHEMA\n"
            "from semantic_bridge_tool import compute_semantic_bridge, "
            "SEMANTIC_BRIDGE_TOOL_SCHEMA\n"
        ),
    },
    {
        "label": "TOOLS_entry",
        "old": "    KNOWLEDGE_GRAPH_TOOL_SCHEMA,\n",
        "new": "    KNOWLEDGE_GRAPH_TOOL_SCHEMA,\n    SEMANTIC_BRIDGE_TOOL_SCHEMA,\n",
    },
    {
        "label": "dispatch_elif",
        "old": (
            '                elif tool_name == "knowledge_graph_tool":\n'
            '                    result = compute_knowledge_graph(args.get("mode"), '
            'args.get("params"), tools=TOOLS)\n'
            '                    resp = {\n'
            '                        "jsonrpc": "2.0", "id": req_id,\n'
            '                        "result": {"content": [{"type": "text", '
            '"text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
            '                    }\n'
        ),
        "new": (
            '                elif tool_name == "knowledge_graph_tool":\n'
            '                    result = compute_knowledge_graph(args.get("mode"), '
            'args.get("params"), tools=TOOLS)\n'
            '                    resp = {\n'
            '                        "jsonrpc": "2.0", "id": req_id,\n'
            '                        "result": {"content": [{"type": "text", '
            '"text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
            '                    }\n'
            '                elif tool_name == "semantic_bridge":\n'
            '                    result = compute_semantic_bridge(args.get("mode"), '
            'args.get("params"), tools=TOOLS)\n'
            '                    resp = {\n'
            '                        "jsonrpc": "2.0", "id": req_id,\n'
            '                        "result": {"content": [{"type": "text", '
            '"text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
            '                    }\n'
        ),
    },
]


def main():
    dry_run = "--dry-run" in sys.argv

    with open(TARGET, encoding="utf-8") as f:
        content = f.read()

    report = []
    working = content
    all_ok = True

    for p in PATCHES:
        matches = working.count(p["old"])
        ok = matches == 1
        all_ok = all_ok and ok
        report.append({"label": p["label"], "matches": matches, "ok": ok})
        if ok:
            working = working.replace(p["old"], p["new"])

    print(f"Lineas originales: {len(content.splitlines())}")
    print(f"Lineas resultantes (si se aplica): {len(working.splitlines())}")
    print()
    for r in report:
        status = "OK" if r["ok"] else "REVISAR"
        print(f"[{status}] {r['label']}: matches={r['matches']}")

    if not all_ok:
        print(
            "\nAl menos un bloque no dio match unico (matches != 1). "
            "NO SE ESCRIBIO NADA. Revisar a mano antes de reintentar."
        )
        sys.exit(1)

    if dry_run:
        print("\n(--dry-run: no se escribio nada)")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{TARGET}.bak.{ts}"
    shutil.copy(TARGET, backup_path)

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(working)

    print(f"\nPatch aplicado OK. Backup: {backup_path}")
    print("Ahora: git diff server.py (revisar a mano) y despues correr "
          "python3 server.py con un tools/list para confirmar semantic_bridge "
          "antes de commitear.")


if __name__ == "__main__":
    main()
