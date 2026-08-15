#!/usr/bin/env python3
"""
Agrega el registro faltante de insurance_risk_tool en tool_registry.

De los 8 archivos de Fase D encontrados en disco, 7 ya estaban
registrados y activos (import en server.py + register_tool() al final
del modulo): debt_snowball_tool, education_funding_tool,
emergency_fund_tool, investment_portfolio_tool, life_insurance_math_tool,
retirement_planner_tool, tax_estimation_tool.

insurance_risk_tool.py es el unico que quedo a medio terminar: tiene
INSURANCE_RISK_TOOL_SCHEMA y compute_insurance_risk(mode, params=None)
completos, con su propio modo "validate" (10 checks) ya implementado,
pero le falta el bloque register_tool() al final del archivo -- por eso
no aparecia ni en tool_registry.REGISTRY ni en el import de server.py.

Este patch solo toca insurance_risk_tool.py (agrega el bloque de
registro + main de autocheque, calcado de debt_snowball_tool.py). El
import correspondiente en server.py se agrega en un segundo patch aparte.
"""
import ast
import shutil
import sys
from datetime import datetime

TARGET = "insurance_risk_tool.py"

OLD = '''    else:
        raise ValueError(f"Modo desconocido para insurance_risk_tool: {mode}")'''

NEW = '''    else:
        raise ValueError(f"Modo desconocido para insurance_risk_tool: {mode}")


try:
    from tool_registry import register_tool
    register_tool(
        name="insurance_risk_tool",
        schema=INSURANCE_RISK_TOOL_SCHEMA,
        handler=lambda args: compute_insurance_risk(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    d = compute_insurance_risk("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\\nTodos los chequeos de insurance_risk_tool.py pasaron OK.")'''


def main():
    with open(TARGET, encoding="utf-8") as f:
        src = f.read()

    count = src.count(OLD)
    assert count == 1, f"[registro insurance_risk_tool] se esperaba 1 ocurrencia, se encontraron {count} -- revisar a mano."

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
    print("Confirmar con:")
    print('  python3 insurance_risk_tool.py   # corre el bloque __main__, valida y hace assert')
    print('  python3 -c "import tool_registry, insurance_risk_tool; print(\'insurance_risk_tool\' in tool_registry.REGISTRY)"')


if __name__ == "__main__":
    main()
