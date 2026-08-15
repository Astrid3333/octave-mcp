"""
Agrega mode="validate" a compute_gradient_hessian y compute_jacobian
(auto_differentiation_tool.py). Ambas son sympy puro, sin Octave, sin
subprocess -- los checks son exactos (comparacion de string tras simplify,
mismo patron que symbolic_tool.py).

No toca la firma existente salvo agregar mode=None con default, para que
mode="validate" funcione sin necesidad de pasar expression/variables.

Uso:
    python3 patch_add_validate_group_c_sympy.py
"""
import ast
import shutil
from datetime import datetime

PATH = "auto_differentiation_tool.py"

VALIDATE_FUNCS = '''

def _validate_gradient_hessian():
    checks = []

    r1 = auto_differentiate("x**2*y + y**3", "x,y", order=2)
    checks.append({"name": "gradient x**2*y+y**3: grad_x == '2*x*y' exacto",
                    "passed": r1["gradient"]["x"]["sympy"] == "2*x*y",
                    "got": r1["gradient"]["x"]["sympy"]})
    checks.append({"name": "gradient x**2*y+y**3: grad_y == 'x**2 + 3*y**2' exacto",
                    "passed": r1["gradient"]["y"]["sympy"] == "x**2 + 3*y**2",
                    "got": r1["gradient"]["y"]["sympy"]})
    checks.append({"name": "hessian x**2*y+y**3: h[0][0]=='2*y', h[0][1]=='2*x', h[1][1]=='6*y' exacto",
                    "passed": (r1["hessian"][0][0]["sympy"] == "2*y"
                               and r1["hessian"][0][1]["sympy"] == "2*x"
                               and r1["hessian"][1][1]["sympy"] == "6*y"),
                    "got": {"h00": r1["hessian"][0][0]["sympy"], "h01": r1["hessian"][0][1]["sympy"],
                            "h11": r1["hessian"][1][1]["sympy"]}})

    r2 = auto_differentiate("sin(x) + x*y", "x,y", order=1)
    checks.append({"name": "gradient sin(x)+x*y: grad_x == 'y + cos(x)' exacto",
                    "passed": r2["gradient"]["x"]["sympy"] == "y + cos(x)",
                    "got": r2["gradient"]["x"]["sympy"]})
    checks.append({"name": "gradient sin(x)+x*y: grad_y == 'x' exacto",
                    "passed": r2["gradient"]["y"]["sympy"] == "x",
                    "got": r2["gradient"]["y"]["sympy"]})

    return {"mode": "validate", "validation_passed": all(c["passed"] for c in checks), "checks": checks}


def _validate_jacobian():
    checks = []

    r1 = auto_jacobian("x**2 - y; x*y - 1", "x,y")
    checks.append({"name": "jacobian [x**2-y, x*y-1]: fila0 == [2*x, -1] exacto",
                    "passed": (r1["jacobian"][0][0]["sympy"] == "2*x"
                               and r1["jacobian"][0][1]["sympy"] == "-1"),
                    "got": {"j00": r1["jacobian"][0][0]["sympy"], "j01": r1["jacobian"][0][1]["sympy"]}})
    checks.append({"name": "jacobian [x**2-y, x*y-1]: fila1 == [y, x] exacto",
                    "passed": (r1["jacobian"][1][0]["sympy"] == "y"
                               and r1["jacobian"][1][1]["sympy"] == "x"),
                    "got": {"j10": r1["jacobian"][1][0]["sympy"], "j11": r1["jacobian"][1][1]["sympy"]}})
    checks.append({"name": "jacobian [x**2-y, x*y-1]: determinante == '2*x**2 + y' exacto",
                    "passed": r1["determinant"]["sympy"] == "2*x**2 + y",
                    "got": r1["determinant"]["sympy"]})

    return {"mode": "validate", "validation_passed": all(c["passed"] for c in checks), "checks": checks}
'''

OLD_SIGS_AND_BODY = '''def compute_gradient_hessian(expression: str, variables: str, order: int = 1) -> dict:
    return auto_differentiate(expression, variables, order)


def compute_jacobian(expressions: str, variables: str) -> dict:
    return auto_jacobian(expressions, variables)'''

NEW_SIGS_AND_BODY = '''def compute_gradient_hessian(expression: str = None, variables: str = None, order: int = 1, mode: str = None) -> dict:
    if mode == "validate":
        return _validate_gradient_hessian()
    return auto_differentiate(expression, variables, order)


def compute_jacobian(expressions: str = None, variables: str = None, mode: str = None) -> dict:
    if mode == "validate":
        return _validate_jacobian()
    return auto_jacobian(expressions, variables)'''

OLD_SCHEMA_GH_TAIL = '''            "order": {
                "type": "integer",
                "description": "1 = solo gradiente, 2 = gradiente + hessiano",
                "enum": [1, 2],
                "default": 1,
            },
        },
        "required": ["expression", "variables"],
    },
}'''

NEW_SCHEMA_GH_TAIL = '''            "order": {
                "type": "integer",
                "description": "1 = solo gradiente, 2 = gradiente + hessiano",
                "enum": [1, 2],
                "default": 1,
            },
            "mode": {
                "type": "string",
                "enum": ["validate"],
                "description": "Si es 'validate', ejecuta el autochequeo interno (ignora expression/variables/order).",
            },
        },
    },
}'''

OLD_SCHEMA_JAC_TAIL = '''            "variables": {
                "type": "string",
                "description": "Variables separadas por coma, ej: 'x,y'",
            },
        },
        "required": ["expressions", "variables"],
    },
}'''

NEW_SCHEMA_JAC_TAIL = '''            "variables": {
                "type": "string",
                "description": "Variables separadas por coma, ej: 'x,y'",
            },
            "mode": {
                "type": "string",
                "enum": ["validate"],
                "description": "Si es 'validate', ejecuta el autochequeo interno (ignora expressions/variables).",
            },
        },
    },
}'''


def apply(src, old, new, label):
    count = src.count(old)
    assert count == 1, f"[{label}] se esperaba 1 ocurrencia, se encontraron {count} -- revisar a mano."
    return src.replace(old, new, 1)


def main():
    with open(PATH, "r", encoding="utf-8") as f:
        src = f.read()

    backup = f"{PATH}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(PATH, backup)

    src = apply(src, OLD_SCHEMA_GH_TAIL, NEW_SCHEMA_GH_TAIL, "schema gradient_hessian")
    src = apply(src, OLD_SCHEMA_JAC_TAIL, NEW_SCHEMA_JAC_TAIL, "schema jacobian")
    src = apply(src, OLD_SIGS_AND_BODY, NEW_SIGS_AND_BODY, "firmas compute_*")

    # Inserta las funciones _validate_* justo antes de las firmas nuevas
    marker = "def compute_gradient_hessian(expression: str = None"
    assert src.count(marker) == 1
    src = src.replace(marker, VALIDATE_FUNCS.strip("\n") + "\n\n\n" + marker, 1)

    with open(PATH, "w", encoding="utf-8") as f:
        f.write(src)

    ast.parse(src)
    print(f"Patch aplicado OK. Backup: {backup}")


if __name__ == "__main__":
    main()
