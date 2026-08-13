"""
patch_wire_refinance_analysis.py

Wirea refinance_analysis_tool en server.py de octave-mcp, siguiendo la
convencion REAL confirmada via grep en el repo de Astrid:
  - import: from credit_simulation_tool import compute_credit_simulation_tool, CREDIT_SIMULATION_TOOL_SCHEMA
  - TOOLS: la lista referencia la constante de schema por nombre (no un dict inline)
  - dispatch: resp = {"jsonrpc": "2.0", "id": req_id, "result": {"content": [...]}}

Ancla en credit_simulation_tool (ultimo tool de Fase D confirmado wireado,
commit 5fde2a5) en vez de debt_snowball_tool, que no esta confirmado como
wireado en el repo real.

Uso:
    cd ~/octave-mcp
    cp ~/Descargas/refinance_analysis_tool.py .
    cp ~/Descargas/patch_wire_refinance_analysis.py .
    python3 patch_wire_refinance_analysis.py

Hace backup timestampeado de server.py antes de tocar nada. Si algun anchor
no matchea, no escribe nada y avisa cual fallo.
"""

import re
import shutil
import ast
import sys
import datetime
from pathlib import Path

SERVER_PATH = Path("server.py")

IMPORT_LINE = (
    "from refinance_analysis_tool import "
    "compute_refinance_analysis_tool, REFINANCE_ANALYSIS_TOOL_SCHEMA\n"
)


def main():
    if not SERVER_PATH.exists():
        print("ERROR: no se encontro server.py en el directorio actual.")
        sys.exit(1)

    original = SERVER_PATH.read_text(encoding="utf-8")
    text = original

    if "refinance_analysis_tool" in text:
        print("refinance_analysis_tool ya parece estar wireado en server.py — no se toca nada.")
        sys.exit(0)

    # --- 1. Import ---
    import_anchor = re.search(
        r"^from credit_simulation_tool import compute_credit_simulation_tool, CREDIT_SIMULATION_TOOL_SCHEMA\n",
        text, re.MULTILINE,
    )
    if not import_anchor:
        print("ERROR: no se encontro la linea de import de credit_simulation_tool para anclar el nuevo import.")
        sys.exit(1)
    insert_at = import_anchor.end()
    text = text[:insert_at] + IMPORT_LINE + text[insert_at:]

    # --- 2. Entrada en TOOLS[] (referencia a la constante, no dict inline) ---
    tools_anchor = re.search(
        r"^( *)CREDIT_SIMULATION_TOOL_SCHEMA,\n",
        text, re.MULTILINE,
    )
    if not tools_anchor:
        print("ERROR: no se encontro 'CREDIT_SIMULATION_TOOL_SCHEMA,' en la lista TOOLS.")
        sys.exit(1)
    indent = tools_anchor.group(1)
    insert_at = tools_anchor.end()
    text = text[:insert_at] + f"{indent}REFINANCE_ANALYSIS_TOOL_SCHEMA,\n" + text[insert_at:]

    # --- 3. Rama de dispatch ---
    dispatch_pattern = re.compile(
        r'^( *)elif tool_name == "credit_simulation_tool":\n'
        r'( *)result = compute_credit_simulation_tool\(args\.get\("mode", "validate"\), args\.get\("params"\)\)\n'
        r'( *)resp = \{\n'
        r'( *)"jsonrpc": "2\.0", "id": req_id,\n'
        r'( *)"result": \{"content": \[\{"type": "text", "text": json\.dumps\(result, ensure_ascii=False, indent=2\)\}\]\},\n'
        r'( *)\}\n',
        re.MULTILINE,
    )
    m = dispatch_pattern.search(text)
    if not m:
        print("ERROR: no se encontro la rama de dispatch completa de credit_simulation_tool con el formato esperado.")
        print("Pegame 'sed -n \"1494,1502p\" server.py' si esto falla, para ajustar el patron exacto.")
        sys.exit(1)
    elif_indent, body_indent = m.group(1), m.group(2)
    new_branch = (
        f'{elif_indent}elif tool_name == "refinance_analysis_tool":\n'
        f'{body_indent}result = compute_refinance_analysis_tool(args.get("mode", "validate"), args.get("params"))\n'
        f'{body_indent}resp = {{\n'
        f'{body_indent}    "jsonrpc": "2.0", "id": req_id,\n'
        f'{body_indent}    "result": {{"content": [{{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}}]}},\n'
        f'{body_indent}}}\n'
    )
    insert_at = m.end()
    text = text[:insert_at] + new_branch + text[insert_at:]

    # --- Validar sintaxis antes de escribir ---
    try:
        ast.parse(text)
    except SyntaxError as e:
        print(f"ERROR: el server.py parcheado no es sintacticamente valido: {e}")
        print("No se escribio nada (el original quedo intacto).")
        sys.exit(1)

    # --- Backup y escritura ---
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = Path(f"server.py.bak_{ts}")
    shutil.copy(SERVER_PATH, backup_path)
    SERVER_PATH.write_text(text, encoding="utf-8")

    print(f"Backup: {backup_path}")
    print("Import de refinance_analysis_tool insertado.")
    print("REFINANCE_ANALYSIS_TOOL_SCHEMA agregado a la lista TOOLS.")
    print("Dispatch elif de refinance_analysis_tool insertado despues de credit_simulation_tool.")
    print("server.py actualizado y validado sintacticamente.")


if __name__ == "__main__":
    main()
