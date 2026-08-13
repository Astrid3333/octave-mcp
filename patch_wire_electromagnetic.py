"""
patch_wire_electromagnetic.py

Wirea electromagnetic_tool.py en server.py de octave-mcp.

A diferencia de patch_wire_climate.py (que buscaba anchors genericos como "el ultimo
import" o "el ultimo else:" y por eso se equivoco 2 veces contra el archivo real), este
patch ancla a los textos EXACTOS que ya confirmamos que existen en tu server.py real
(el bloque de climate_tool que quedo bien wireado tras el fix). Mucho mas seguro.

Uso:
    1. Copiar electromagnetic_tool.py a la raiz del repo (junto a server.py).
    2. Correr:  python3 patch_wire_electromagnetic.py
    3. Verificar:  python3 -c "import server" < /dev/null
    4. Probar:  echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"electromagnetic_tool","arguments":{"mode":"wave_1d"}}}' | python3 server.py
    5. git add electromagnetic_tool.py server.py && git commit -m "wire electromagnetic_tool" && git push
"""

import shutil
import sys

SERVER_PATH = "server.py"
BACKUP_PATH = "server.py.bak_electromagnetic"

IMPORT_ANCHOR = "from climate_tool import compute_climate\n"
IMPORT_NEW = "from electromagnetic_tool import compute_electromagnetic\n"

TOOLS_ENTRY = '''    {
        "name": "electromagnetic_tool",
        "description": (
            "Fisica electromagnetica (TMM, Born & Wolf) con validacion analitica. Modos: "
            "wave_1d (reflexion/transmision Fresnel en una interfaz simple), "
            "photonic_bandgap (gap fotonico de un stack cuarto-de-onda periodico, "
            "validado contra la formula de Yariv-Yeh)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["wave_1d", "photonic_bandgap"],
                },
                "params": {
                    "type": "object",
                    "description": "Parametros especificos del modo (opcional, cada modo trae defaults razonables).",
                },
            },
            "required": ["mode"],
        },
    },
'''

# Bloque exacto de climate_tool tal como quedo en tu server.py real tras el fix (commit 29344d5)
DISPATCH_ANCHOR = (
    '            elif tool_name == "climate_tool":\n'
    '                result = compute_climate(args.get("mode"), args.get("params"))\n'
    '                resp = {\n'
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                }\n'
)

DISPATCH_NEW = (
    '            elif tool_name == "electromagnetic_tool":\n'
    '                result = compute_electromagnetic(args.get("mode"), args.get("params"))\n'
    '                resp = {\n'
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                }\n'
)


def main():
    with open(SERVER_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    if "electromagnetic_tool" in text and "compute_electromagnetic" in text:
        print("electromagnetic_tool ya parece estar wireado en server.py -- no se modifica nada.")
        sys.exit(0)

    if IMPORT_ANCHOR not in text:
        print("ERROR: no encontre el anchor de import esperado (linea de climate_tool).")
        print("Puede que server.py haya cambiado desde el ultimo wireo. Pegame:")
        print("  grep -n 'from climate_tool import' server.py")
        sys.exit(1)

    if DISPATCH_ANCHOR not in text:
        print("ERROR: no encontre el anchor de dispatch esperado (bloque elif de climate_tool).")
        print("Puede que server.py haya cambiado desde el ultimo wireo. Pegame:")
        print("  grep -n 'elif tool_name == \"climate_tool\"' server.py")
        sys.exit(1)

    if "TOOLS = [" not in text or "\n]" not in text:
        print("ERROR: no encontre la lista TOOLS = [ ... ]. Revisar manualmente.")
        sys.exit(1)

    shutil.copyfile(SERVER_PATH, BACKUP_PATH)
    print(f"Backup guardado en {BACKUP_PATH}")

    # 1) import: justo despues del import de climate_tool
    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_NEW, 1)

    # 2) entrada en TOOLS: antes del cierre de la lista
    tools_start = text.find("TOOLS = [")
    close_idx = text.find("\n]", tools_start)
    text = text[:close_idx] + "\n" + TOOLS_ENTRY + text[close_idx:]

    # 3) dispatch: justo despues del bloque elif de climate_tool, mismo formato
    text = text.replace(DISPATCH_ANCHOR, DISPATCH_ANCHOR + DISPATCH_NEW, 1)

    with open(SERVER_PATH, "w", encoding="utf-8") as f:
        f.write(text)

    print("electromagnetic_tool wireado: import + entrada TOOLS + rama dispatch agregadas.")
    print('Verificar con:  python3 -c "import server" < /dev/null')


if __name__ == "__main__":
    main()
