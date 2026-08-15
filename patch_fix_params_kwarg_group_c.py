"""
Fix: run_all_validations.py invoca las tools con un kwarg 'params' extra
(mismo patron JSON-RPC que usa con survey_tools.py, etc), pero
compute_gradient_hessian/compute_jacobian no lo aceptaban en su firma.
Se agrega **kwargs para absorberlo sin cambiar el comportamiento existente.

Uso:
    python3 patch_fix_params_kwarg_group_c.py
"""
import ast
import shutil
from datetime import datetime

PATH = "auto_differentiation_tool.py"

OLD = '''def compute_gradient_hessian(expression: str = None, variables: str = None, order: int = 1, mode: str = None) -> dict:
    if mode == "validate":
        return _validate_gradient_hessian()
    return auto_differentiate(expression, variables, order)


def compute_jacobian(expressions: str = None, variables: str = None, mode: str = None) -> dict:
    if mode == "validate":
        return _validate_jacobian()
    return auto_jacobian(expressions, variables)'''

NEW = '''def compute_gradient_hessian(expression: str = None, variables: str = None, order: int = 1, mode: str = None, **kwargs) -> dict:
    if mode == "validate":
        return _validate_gradient_hessian()
    return auto_differentiate(expression, variables, order)


def compute_jacobian(expressions: str = None, variables: str = None, mode: str = None, **kwargs) -> dict:
    if mode == "validate":
        return _validate_jacobian()
    return auto_jacobian(expressions, variables)'''


def main():
    with open(PATH, "r", encoding="utf-8") as f:
        src = f.read()

    backup = f"{PATH}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(PATH, backup)

    count = src.count(OLD)
    assert count == 1, f"se esperaba 1 ocurrencia, se encontraron {count} -- revisar a mano."
    src = src.replace(OLD, NEW, 1)

    with open(PATH, "w", encoding="utf-8") as f:
        f.write(src)

    ast.parse(src)
    print(f"Patch aplicado OK. Backup: {backup}")


if __name__ == "__main__":
    main()
