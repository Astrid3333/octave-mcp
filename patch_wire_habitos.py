#!/usr/bin/env python3
"""
Agrega los imports de los 4 tools nuevos del grupo "habitos financieros"
(cierre de Fase D) en server.py, junto al bloque de tools que se
auto-registran via tool_registry (mismo patron que insurance_risk_tool).

Requiere que los 4 archivos .py ya esten copiados en ~/octave-mcp/ antes
de correr este patch: spending_pattern_tool.py, savings_rate_tool.py,
habit_streak_tool.py, financial_literacy_score_tool.py.

Detecta si el import ya existe para no duplicar si se corre 2 veces.
"""
import ast
import shutil
import sys
from datetime import datetime

TARGET = "server.py"

ANCHOR = '''import insurance_risk_tool  # auto-registra via tool_registry, no requiere mas ediciones'''

NEW_IMPORTS = [
    "spending_pattern_tool",
    "savings_rate_tool",
    "habit_streak_tool",
    "financial_literacy_score_tool",
]


def main():
    with open(TARGET, encoding="utf-8") as f:
        src = f.read()

    count = src.count(ANCHOR)
    assert count == 1, (
        f"[imports habitos financieros] se esperaba 1 ocurrencia del ancla "
        f"(import insurance_risk_tool), se encontraron {count} -- revisar a mano."
    )

    already_present = [name for name in NEW_IMPORTS if f"import {name}" in src]
    if already_present:
        print(f"Ya presentes, no se duplican: {already_present}")

    to_add = [name for name in NEW_IMPORTS if name not in already_present]
    if not to_add:
        print("Los 4 imports ya estaban presentes. Nada que hacer.")
        return

    new_lines = "\n".join(
        f"import {name}  # auto-registra via tool_registry, no requiere mas ediciones"
        for name in to_add
    )
    new_block = ANCHOR + "\n" + new_lines

    backup = f"{TARGET}.bak.{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy(TARGET, backup)

    new_src = src.replace(ANCHOR, new_block, 1)

    try:
        ast.parse(new_src)
    except SyntaxError as e:
        print(f"ERROR: el resultado no parsea como Python valido: {e}", file=sys.stderr)
        sys.exit(1)

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(new_src)

    print(f"Patch aplicado OK. Backup: {backup}")
    print(f"Imports agregados: {to_add}")
    print("Confirmar con: grep -n 'spending_pattern_tool\\|savings_rate_tool\\|habit_streak_tool\\|financial_literacy_score_tool' server.py")


if __name__ == "__main__":
    main()
