#!/usr/bin/env python3
"""
Agrega el import de insurance_risk_tool en server.py, junto al resto del
bloque de tools de Fase D que se auto-registran via tool_registry
(lineas 6-12 originales). Requiere haber corrido primero
patch_register_insurance_risk_tool.py.
"""
import ast
import shutil
import sys
from datetime import datetime

TARGET = "server.py"

OLD = '''import tax_estimation_tool  # auto-registra via tool_registry, no requiere mas ediciones'''

NEW = '''import tax_estimation_tool  # auto-registra via tool_registry, no requiere mas ediciones
import insurance_risk_tool  # auto-registra via tool_registry, no requiere mas ediciones'''


def main():
    with open(TARGET, encoding="utf-8") as f:
        src = f.read()

    count = src.count(OLD)
    assert count == 1, f"[import insurance_risk_tool en server.py] se esperaba 1 ocurrencia, se encontraron {count} -- revisar a mano."

    backup = f"{TARGET}.bak.{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy(TARGET, backup)

    new_src = src.replace(OLD, NEW, 1)

    try:
        ast.parse(new_src)
    except SyntaxError as e:
        print(f"ERROR: el resultado no parsea como Python valido: {e}", file=sys.stderr)
        sys.exit(1)

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(new_src)

    print(f"Patch aplicado OK. Backup: {backup}")
    print("Confirmar con: grep -n 'insurance_risk_tool' server.py")


if __name__ == "__main__":
    main()
