"""
auto_differentiation_tool.py

Diferenciación simbólica exacta para el ecosistema mcp_octave.
Pensado para pegarse como @mcp.tool() dentro de /home/astrid/mcp_octave/server.py

No depende de Octave: usa sympy puro, así que corre en el mismo proceso
FastMCP sin invocar subprocess. Devuelve tanto las expresiones simbólicas
(para leer) como código Octave/Python listo para copiar (para ejecutar).
"""

import sympy as sp


def _parse_vars(variables: str):
    """'x,y,z' -> (x, y, z) símbolos de sympy, preservando el orden."""
    names = [v.strip() for v in variables.split(",") if v.strip()]
    if not names:
        raise ValueError("Debes indicar al menos una variable, ej: 'x,y'")
    # Se crea cada símbolo por separado (en vez de sp.symbols(names)) para
    # garantizar siempre una tupla de Symbol, sin casos especiales según
    # cuántas variables haya.
    syms = tuple(sp.Symbol(n) for n in names)
    return names, syms


def _expr_to_octave(expr) -> str:
    """Convierte una expresión sympy a sintaxis Octave (^, operadores elemento a elemento)."""
    code = sp.octave_code(expr)
    return code


def _expr_to_python(expr) -> str:
    return str(expr)


def auto_differentiate(expression: str, variables: str, order: int = 1) -> dict:
    """
    Calcula derivadas simbólicas exactas de una función escalar f(x1, x2, ...).

    Args:
        expression: expresión matemática en sintaxis tipo Python/sympy,
                    ej "x**2*sin(y) + exp(x*y)"
        variables: variables respecto a las que derivar, separadas por coma,
                   ej "x,y" (el orden define el orden del gradiente/hessiano)
        order: 1 -> solo gradiente (derivadas parciales de primer orden)
               2 -> gradiente + hessiano (matriz de segundas derivadas)

    Returns:
        dict con:
          - expression_original: la expresión tal cual, simplificada
          - variables: lista de variables detectadas
          - gradient: {var: {"sympy": str, "octave": str, "python": str}}
          - hessian: matriz NxN (solo si order >= 2), misma estructura
          - warnings: lista de avisos (ej. singularidades detectadas)
    """
    if order not in (1, 2):
        raise ValueError("order debe ser 1 (gradiente) o 2 (gradiente + hessiano)")

    names, syms = _parse_vars(variables)

    try:
        expr = sp.sympify(expression)
    except (sp.SympifyError, TypeError) as e:
        raise ValueError(f"No se pudo interpretar la expresión '{expression}': {e}")

    warnings = []

    # Verifica que las variables declaradas efectivamente aparecen en la expresión
    free_syms = {str(s) for s in expr.free_symbols}
    declared = set(names)
    unused = declared - free_syms
    if unused:
        warnings.append(
            f"Las variables {sorted(unused)} no aparecen en la expresión "
            f"(sus derivadas serán 0)."
        )

    expr_simpl = sp.simplify(expr)

    result = {
        "expression_original": str(expr_simpl),
        "variables": names,
        "gradient": {},
        "warnings": warnings,
    }

    # --- Gradiente (orden 1) ---
    grad_exprs = []
    for name, s in zip(names, syms):
        d = sp.diff(expr, s)
        d_simpl = sp.simplify(d)
        grad_exprs.append(d_simpl)
        result["gradient"][name] = {
            "sympy": str(d_simpl),
            "octave": _expr_to_octave(d_simpl),
            "python": _expr_to_python(d_simpl),
        }

    # --- Hessiano (orden 2) ---
    if order == 2:
        n = len(syms)
        hessian_matrix = []
        for i in range(n):
            row = []
            for j in range(n):
                d2 = sp.diff(expr, syms[i], syms[j])
                d2_simpl = sp.simplify(d2)
                row.append({
                    "sympy": str(d2_simpl),
                    "octave": _expr_to_octave(d2_simpl),
                    "python": _expr_to_python(d2_simpl),
                })
            hessian_matrix.append(row)
        result["hessian"] = hessian_matrix
        result["hessian_vars_order"] = names

    return result


def auto_jacobian(expressions: str, variables: str) -> dict:
    """
    Calcula el Jacobiano de un sistema de funciones vectorial F(x1,...,xn) -> R^m.
    Útil para stiff_ode_tool (Jacobiano del sistema de EDOs) y optimización.

    Args:
        expressions: funciones separadas por ';', ej "x**2 - y; x*y - 1"
        variables: variables separadas por coma, ej "x,y"

    Returns:
        dict con la matriz Jacobiana (m x n), cada entrada con sympy/octave/python,
        y el determinante si la matriz es cuadrada.
    """
    names, syms = _parse_vars(variables)

    raw_exprs = [e.strip() for e in expressions.split(";") if e.strip()]
    if not raw_exprs:
        raise ValueError("Debes indicar al menos una expresión, separadas por ';'")

    try:
        exprs = [sp.sympify(e) for e in raw_exprs]
    except (sp.SympifyError, TypeError) as e:
        raise ValueError(f"No se pudo interpretar alguna expresión: {e}")

    jac_matrix = []
    for f in exprs:
        row = []
        for s in syms:
            d = sp.simplify(sp.diff(f, s))
            row.append({
                "sympy": str(d),
                "octave": _expr_to_octave(d),
                "python": _expr_to_python(d),
            })
        jac_matrix.append(row)

    result = {
        "functions": [str(e) for e in exprs],
        "variables": names,
        "jacobian": jac_matrix,
        "shape": [len(exprs), len(names)],
    }

    if len(exprs) == len(names):
        sp_matrix = sp.Matrix([[sp.diff(f, s) for s in syms] for f in exprs])
        det = sp.simplify(sp_matrix.det())
        result["determinant"] = {
            "sympy": str(det),
            "octave": _expr_to_octave(det),
        }
        if det == 0:
            result["warnings"] = ["El determinante del Jacobiano es 0: el sistema es singular en general."]

    return result


# ---------------------------------------------------------------------------
# Envoltorio para FastMCP — pegar dentro de mcp_octave/server.py junto a los
# demás @mcp.tool(). Requiere que este archivo esté en el mismo directorio
# (o copiar las funciones de arriba directo en server.py).
# ---------------------------------------------------------------------------
#
# from auto_differentiation_tool import auto_differentiate, auto_jacobian
#
# @mcp.tool()
# def compute_gradient_hessian(expression: str, variables: str, order: int = 1) -> dict:
#     """Calcula gradiente (order=1) o gradiente+hessiano (order=2) de una función escalar."""
#     return auto_differentiate(expression, variables, order)
#
# @mcp.tool()
# def compute_jacobian(expressions: str, variables: str) -> dict:
#     """Calcula el Jacobiano de un sistema de funciones (separadas por ';')."""
#     return auto_jacobian(expressions, variables)


# ---------------------------------------------------------------------------
# Schemas MCP + wrappers (patron server.py: nombre de funcion == nombre tool)
# ---------------------------------------------------------------------------

GRADIENT_HESSIAN_TOOL_SCHEMA = {
    "name": "compute_gradient_hessian",
    "description": "Calcula el gradiente (order=1) o gradiente + hessiano (order=2) de una funcion escalar f(x1,...,xn) por diferenciacion simbolica exacta (sympy).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Expresion matematica en sintaxis Python/sympy, ej: 'x**2*sin(y) + exp(x*y)'",
            },
            "variables": {
                "type": "string",
                "description": "Variables respecto a las que derivar, separadas por coma, ej: 'x,y'",
            },
            "order": {
                "type": "integer",
                "description": "1 = solo gradiente, 2 = gradiente + hessiano",
                "enum": [1, 2],
                "default": 1,
            },
        },
        "required": ["expression", "variables"],
    },
}

JACOBIAN_TOOL_SCHEMA = {
    "name": "compute_jacobian",
    "description": "Calcula el Jacobiano de un sistema de funciones vectorial F(x1,...,xn) -> R^m, con determinante si la matriz es cuadrada.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "expressions": {
                "type": "string",
                "description": "Funciones separadas por ';', ej: 'x**2 - y; x*y - 1'",
            },
            "variables": {
                "type": "string",
                "description": "Variables separadas por coma, ej: 'x,y'",
            },
        },
        "required": ["expressions", "variables"],
    },
}


def compute_gradient_hessian(expression: str, variables: str, order: int = 1) -> dict:
    return auto_differentiate(expression, variables, order)


def compute_jacobian(expressions: str, variables: str) -> dict:
    return auto_jacobian(expressions, variables)


if __name__ == "__main__":
    # Pruebas rápidas
    import json

    print("=== Gradiente + Hessiano ===")
    r1 = auto_differentiate("x**2*sin(y) + exp(x*y)", "x,y", order=2)
    print(json.dumps(r1, indent=2, ensure_ascii=False))

    print("\n=== Jacobiano de sistema no lineal ===")
    r2 = auto_jacobian("x**2 - y; x*y - 1", "x,y")
    print(json.dumps(r2, indent=2, ensure_ascii=False))

    print("\n=== Caso logístico (para stiff_ode_tool) ===")
    r3 = auto_differentiate("r*x*(1 - x/K)", "x", order=1)
    print(json.dumps(r3, indent=2, ensure_ascii=False))
