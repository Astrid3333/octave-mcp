#!/usr/bin/env python3
"""
patch_wire_stochastic_multivariate.py

Wirea advanced_stochastic_tool.py y multivariate_bayes_tool.py en server.py,
siguiendo el patron de 3 puntos usado en los patches anteriores del repo
(import, entrada en TOOLS[], rama de dispatch):

  1. Import: agrega
       from advanced_stochastic_tool import compute_advanced_stochastic
       from multivariate_bayes_tool import compute_multivariate_bayes
     DESPUES del cierre del ultimo bloque de import existente (nunca en
     medio de un `from X import (...)` multilinea -- ese fue uno de los
     dos bugs reales que rompio el patch de climate_tool).

  2. Schema: agrega las entradas de TOOLS[] (con inputSchema completo)
     justo antes del cierre `]` de la lista TOOLS.

  3. Dispatch: agrega las ramas
       elif tool_name == "advanced_stochastic_tool": ...
       elif tool_name == "multivariate_bayes_tool": ...
     al MISMO nivel de indentacion que las demas comparaciones de
     tool_name dentro del bloque interno de tools/call (no al nivel de
     comparacion de `method`, que fue el segundo bug real del patch de
     climate_tool -- ahi el regex habia enganchado un `else:` del nivel
     equivocado).

Uso:
    python3 patch_wire_stochastic_multivariate.py [ruta_a_server.py]

Por defecto busca ./server.py. Hace backup timestampeado antes de tocar
nada, y valida con ast.parse antes y despues de escribir.

Es idempotente: si detecta que ya esta wireado (busca el nombre del tool
en el archivo), no vuelve a insertar nada.
"""

import ast
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


TOOLS_TO_WIRE = [
    {
        "module": "advanced_stochastic_tool",
        "func": "compute_advanced_stochastic",
        "tool_name": "advanced_stochastic_tool",
        "description": ("Procesos estocasticos avanzados: HMM (forward-backward + Viterbi), "
                         "filtro de Kalman, particle filter (bootstrap), y GARCH(1,1) por MLE."),
        "modes": ["hmm", "kalman", "particle_filter", "garch"],
    },
    {
        "module": "multivariate_bayes_tool",
        "func": "compute_multivariate_bayes",
        "tool_name": "multivariate_bayes_tool",
        "description": ("Estadistica bayesiana multivariada: normal/t multivariada, Wishart, "
                         "modelo jerarquico (Gibbs), regresion via HMC, PCA con biplot y CV, "
                         "y Factor Analysis via EM."),
        "modes": ["mvn_sample", "mvt_sample", "wishart_sample", "hierarchical",
                  "hmc_regression", "pca_biplot", "pca_cv", "factor_analysis"],
    },
]


def _fail(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _validate_syntax(text, label):
    try:
        ast.parse(text)
    except SyntaxError as e:
        _fail(f"sintaxis invalida en {label}: {e}")


def _already_wired(text, tool_name):
    return f'"{tool_name}"' in text and f"compute_{TOOLS_TO_WIRE[0]['module'].split('_')[0]}" in text \
        or f'tool_name == "{tool_name}"' in text


def _find_import_insertion_point(text):
    """Devuelve el indice de caracter donde insertar los nuevos imports:
    justo despues del ULTIMO bloque de import de nivel superior, cerrado
    (nunca dentro de parentesis abiertos de un `from X import (...)`)."""
    lines = text.split("\n")
    last_import_end = None
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            # si abre parentesis sin cerrar, avanzar hasta el cierre real
            if "(" in line and ")" not in line:
                j = i
                while j < n and ")" not in lines[j]:
                    j += 1
                last_import_end = j + 1
                i = j + 1
                continue
            last_import_end = i + 1
            i += 1
            continue
        i += 1

    if last_import_end is None:
        _fail("no se encontro ningun bloque de import de nivel superior en server.py")

    char_idx = sum(len(l) + 1 for l in lines[:last_import_end])
    return char_idx


def _build_import_block():
    lines = []
    for t in TOOLS_TO_WIRE:
        lines.append(f"from {t['module']} import {t['func']}")
    return "\n".join(lines) + "\n"


def _build_tools_schema_entries():
    entries = []
    for t in TOOLS_TO_WIRE:
        modes_json = ", ".join(f'"{m}"' for m in t["modes"])
        entry = f'''    {{
        "name": "{t['tool_name']}",
        "description": "{t['description']}",
        "inputSchema": {{
            "type": "object",
            "properties": {{
                "mode": {{"type": "string", "enum": [{modes_json}]}},
                "params": {{"type": "object"}}
            }},
            "required": ["mode", "params"]
        }}
    }},'''
        entries.append(entry)
    return "\n".join(entries) + "\n"


def _find_tools_list_close(text):
    """Encuentra el `]` que cierra la lista TOOLS = [ ... ] de nivel
    superior, contando balance de corchetes desde la asignacion."""
    m = re.search(r"^TOOLS\s*=\s*\[", text, re.MULTILINE)
    if not m:
        _fail('no se encontro "TOOLS = [" en server.py')

    depth = 0
    i = m.end() - 1  # posicion del '[' inicial
    n = len(text)
    while i < n:
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    _fail('no se encontro el cierre balanceado de "TOOLS = [" en server.py')


def _find_dispatch_insertion(text):
    """Encuentra una rama existente `elif tool_name == "...":` dentro del
    bloque interno de tools/call, y devuelve (indice_de_insercion,
    indentacion) usando esa rama como referencia de nivel -- para no
    repetir el bug de engancharse a un `else:` del nivel de `method` en
    vez del nivel de `tool_name`."""
    pattern = re.compile(r'^([ \t]+)elif tool_name == "([a-zA-Z0-9_]+)":\s*$', re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        _fail('no se encontro ninguna rama "elif tool_name == ...": de referencia en server.py; '
              "revisar manualmente el patron de dispatch de este repo")

    last = matches[-1]
    indent = last.group(1)

    # avanzar hasta el final del bloque de esa rama (siguiente linea con
    # indentacion <= a la de la rama, que no este vacia)
    lines = text[last.end():].split("\n")
    offset = last.end() + 1  # +1 por el salto de linea tras el ':'
    consumed = 0
    for line in lines[1:]:  # la primera linea de lines es resto tras el ':' (vacio normalmente)
        if line.strip() == "":
            consumed += len(line) + 1
            continue
        cur_indent = len(line) - len(line.lstrip(" \t"))
        if line.strip() and cur_indent <= len(indent):
            break
        consumed += len(line) + 1

    insertion_point = last.end() + 1 + consumed
    return insertion_point, indent


def _build_dispatch_branches(indent):
    body_indent = indent + "    "
    branches = []
    for t in TOOLS_TO_WIRE:
        branch = (
            f'{indent}elif tool_name == "{t["tool_name"]}":\n'
            f'{body_indent}resp = {t["func"]}(tool_args.get("mode"), tool_args.get("params", {{}}))\n'
        )
        branches.append(branch)
    return "".join(branches)


def main():
    server_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("server.py")
    if not server_path.exists():
        _fail(f"no existe {server_path}")

    text = server_path.read_text()
    _validate_syntax(text, str(server_path) + " (antes del patch)")

    already = [t["tool_name"] for t in TOOLS_TO_WIRE if f'"{t["tool_name"]}"' in text]
    if len(already) == len(TOOLS_TO_WIRE):
        print(f"Ya wireados en {server_path}, no se toca nada: {already}")
        return
    if already:
        print(f"AVISO: {already} ya aparecen en el archivo; revisar manualmente antes de continuar "
              "para evitar duplicados. Abortando por seguridad.")
        return

    backup_path = server_path.with_name(
        f"{server_path.stem}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}{server_path.suffix}"
    )
    shutil.copy2(server_path, backup_path)
    print(f"Backup creado: {backup_path}")

    # --- Punto 1: import ---
    import_idx = _find_import_insertion_point(text)
    import_block = _build_import_block()
    text = text[:import_idx] + import_block + text[import_idx:]

    # --- Punto 2: entradas en TOOLS[] ---
    close_idx = _find_tools_list_close(text)
    schema_block = _build_tools_schema_entries()
    # si la ultima entrada existente no termina en coma, agregarla para
    # no dejar una lista con sintaxis invalida (`{...}\n    {...}`)
    before = text[:close_idx]
    stripped_before = before.rstrip()
    if stripped_before and not stripped_before.endswith(","):
        before = stripped_before + ",\n"
    text = before + schema_block + text[close_idx:]

    # --- Punto 3: dispatch ---
    insertion_point, indent = _find_dispatch_insertion(text)
    dispatch_block = _build_dispatch_branches(indent)
    text = text[:insertion_point] + dispatch_block + text[insertion_point:]

    _validate_syntax(text, str(server_path) + " (despues del patch, antes de escribir)")

    server_path.write_text(text)
    print(f"Patch aplicado con exito en {server_path}")
    print(f"Tools wireados: {[t['tool_name'] for t in TOOLS_TO_WIRE]}")
    print("Verifica con: python3 -c \"import ast; ast.parse(open('server.py').read())\"")
    print("y despues con un smoke test real (echo '...' | python3 server.py) por cada modo nuevo.")


if __name__ == "__main__":
    main()
