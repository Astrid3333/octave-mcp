"""
patch_wire_climate.py

Wirea climate_tool.py en server.py siguiendo el patrón ya usado (import + entrada en
TOOLS[] + rama de dispatch con **args), igual que acoustics_tool, quantum_astro_tool, etc.

Uso:
    1. Copiar climate_tool.py a la raíz del repo (junto a server.py).
    2. Correr:  python3 patch_wire_climate.py
    3. Verificar:  python3 -c "import server"
    4. git add climate_tool.py server.py && git commit -m "wire climate_tool" && git push

Es defensivo: si detecta que climate_tool ya está wireado (import o dispatch ya presentes),
no toca nada y avisa.
"""

import re
import shutil
import sys

SERVER_PATH = "server.py"
BACKUP_PATH = "server.py.bak_climate"

IMPORT_LINE = "from climate_tool import compute_climate\n"

TOOLS_ENTRY = '''    {
        "name": "climate_tool",
        "description": (
            "Fisica climatica especifica con validacion analitica. Modos: "
            "energy_balance_ebm (balance de energia 0-D, punto de equilibrio T_eq), "
            "newton_cooling_trend (relajacion exponencial dT/dt=-k(T-Ta), proyeccion de series cortas), "
            "carbon_cycle_box (modelo de cajas atmosfera-oceano-tierra, conservacion de masa), "
            "bifurcation_snowball (histeresis albedo-temperatura tipo Budyko-Sellers, Snowball Earth)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": [
                        "energy_balance_ebm",
                        "newton_cooling_trend",
                        "carbon_cycle_box",
                        "bifurcation_snowball",
                    ],
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

def already_wired(text):
    return "climate_tool" in text and "compute_climate" in text


def insert_import(text):
    if IMPORT_LINE.strip() in text:
        return text
    # Insertar despues del ultimo "from X_tool import Y" que encuentre, o al principio si no hay ninguno
    matches = list(re.finditer(r"^from \w+ import .+\n", text, flags=re.MULTILINE))
    if matches:
        last = matches[-1]
        idx = last.end()
        return text[:idx] + IMPORT_LINE + text[idx:]
    else:
        return IMPORT_LINE + text


def insert_tools_entry(text):
    # Busca el cierre de la lista TOOLS: "]" que sigue al ultimo "}," de nivel superior
    # Estrategia simple y robusta: insertar la entrada justo antes del primer
    # "]\n" que aparezca despues de la primera ocurrencia de "TOOLS = ["
    m = re.search(r"TOOLS\s*=\s*\[", text)
    if not m:
        raise RuntimeError("No encontre 'TOOLS = [' en server.py -- revisar manualmente")
    close_idx = text.find("\n]", m.end())
    if close_idx == -1:
        raise RuntimeError("No encontre el cierre de la lista TOOLS -- revisar manualmente")
    return text[:close_idx] + "\n" + TOOLS_ENTRY + text[close_idx:]


def insert_dispatch(text):
    # Inserta la rama elif justo antes del ultimo "else:" de nivel de dispatch,
    # tomando el indent real de ese "else:" para que la rama nueva quede alineada.
    else_matches = list(re.finditer(r"\n(?P<indent>[ \t]*)else:\n", text))
    if else_matches:
        last_else = else_matches[-1]
        indent = last_else.group("indent")
        block = f'{indent}elif tool_name == "climate_tool":\n{indent}    resp = compute_climate(**args)\n'
        insert_at = last_else.start() + 1  # justo despues del \n, al inicio de la linea "else:"
        return text[:insert_at] + block + text[insert_at:]
    else:
        raise RuntimeError(
            "No encontre un 'else:' final en el dispatch -- pegar la rama "
            "'elif tool_name == \"climate_tool\": resp = compute_climate(**args)' "
            "manualmente antes de la rama de error/tool desconocida, con el mismo indent"
        )


def main():
    with open(SERVER_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    if already_wired(text):
        print("climate_tool ya parece estar wireado en server.py -- no se modifica nada.")
        sys.exit(0)

    shutil.copyfile(SERVER_PATH, BACKUP_PATH)
    print(f"Backup guardado en {BACKUP_PATH}")

    text = insert_import(text)
    text = insert_tools_entry(text)
    text = insert_dispatch(text)

    with open(SERVER_PATH, "w", encoding="utf-8") as f:
        f.write(text)

    print("climate_tool wireado: import + entrada TOOLS + rama dispatch agregadas.")
    print("Verificar con:  python3 -c \"import server\"")


if __name__ == "__main__":
    main()
