#!/usr/bin/env python3
"""
Agrega los imports de los 5 tools nuevos de la Fase C del roadmap de
administracion publica (nucleo sismico + riesgo por amenaza + impacto
economico/social) en server.py, junto al bloque de tools que se
auto-registran via tool_registry (mismo patron que insurance_risk_tool
y los 4 de habitos financieros).

Requiere que los 5 archivos .py ya esten copiados en ~/octave-mcp/ antes
de correr este patch: earthquake_analysis_tool.py, wildfire_risk_tool.py,
landslide_risk_tool.py, disaster_economics_tool.py, social_impact_tool.py.

Detecta si el import ya existe para no duplicar si se corre 2 veces.
Ancla flexible: busca la ultima linea "import <nombre>_tool  # auto-
registra via tool_registry" del bloque de auto-registro (cualquiera de
las ya conocidas), para no depender de que financial_literacy_score_tool
sea necesariamente la ultima si el orden de imports cambio.
"""
import ast
import re
import shutil
import sys
from datetime import datetime

TARGET = "server.py"

# cualquiera de estas, en orden de preferencia, sirve de ancla (la primera
# que aparezca en el archivo se usa; todas pertenecen al bloque de
# auto-registro via tool_registry ya existente)
ANCHOR_CANDIDATES = [
    "financial_literacy_score_tool",
    "habit_streak_tool",
    "insurance_risk_tool",
]

NEW_IMPORTS = [
    "earthquake_analysis_tool",
    "wildfire_risk_tool",
    "landslide_risk_tool",
    "disaster_economics_tool",
    "social_impact_tool",
]


def main():
    with open(TARGET, encoding="utf-8") as f:
        src = f.read()

    anchor_line = None
    for candidate in ANCHOR_CANDIDATES:
        pattern = f"import {candidate}  # auto-registra via tool_registry, no requiere mas ediciones"
        if src.count(pattern) == 1:
            anchor_line = pattern
            break
        elif src.count(pattern) > 1:
            print(f"ERROR: '{pattern}' aparece mas de una vez -- revisar a mano.", file=sys.stderr)
            sys.exit(1)

    if anchor_line is None:
        print(f"ERROR: no se encontro ninguna ancla conocida ({ANCHOR_CANDIDATES}) en {TARGET}.", file=sys.stderr)
        sys.exit(1)

    already_present = [name for name in NEW_IMPORTS if f"import {name}" in src]
    if already_present:
        print(f"Ya presentes, no se duplican: {already_present}")

    to_add = [name for name in NEW_IMPORTS if name not in already_present]
    if not to_add:
        print("Los 5 imports ya estaban presentes. Nada que hacer.")
        return

    new_lines = "\n".join(
        f"import {name}  # auto-registra via tool_registry, no requiere mas ediciones"
        for name in to_add
    )
    new_block = anchor_line + "\n" + new_lines

    backup = f"{TARGET}.bak.{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy(TARGET, backup)

    new_src = src.replace(anchor_line, new_block, 1)

    try:
        ast.parse(new_src)
    except SyntaxError as e:
        print(f"ERROR: el resultado no parsea como Python valido: {e}", file=sys.stderr)
        sys.exit(1)

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(new_src)

    print(f"Patch aplicado OK. Backup: {backup}")
    print(f"Ancla usada: {anchor_line}")
    print(f"Imports agregados: {to_add}")
    print("Confirmar con: grep -n 'earthquake_analysis_tool\\|wildfire_risk_tool\\|landslide_risk_tool\\|disaster_economics_tool\\|social_impact_tool' server.py")


if __name__ == "__main__":
    main()
