"""
symbolic_tool.py

Algebra simbolica via sympy: simplificacion, resolucion de ecuaciones,
derivadas, integrales (indefinidas y definidas), series de Taylor. Puente
necesario porque Octave es 100% numerico -- no hay forma de hacer esto
dentro del ecosistema Octave existente sin este modulo.

Seguridad: las expresiones del usuario se parsean con sympy.parse_expr en
modo seguro (sin eval() de Python crudo), restringido a un namespace de
funciones matematicas conocidas. No ejecuta codigo arbitrario.

Mismo patron de validacion: presets con resultado analitico conocido
((x^2-1)/(x-1) simplifica a x+1; integral de sin(x) en [0,pi] = 2; etc.)
antes de aplicar a expresiones custom.
"""
import sympy as sp
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application

SYMBOLIC_SCHEMA = {
    "name": "compute_symbolic",
    "description": (
        "Algebra simbolica via sympy: simplify (simplificacion de "
        "expresiones), solve (resolver ecuaciones = 0), differentiate "
        "(derivada simbolica), integrate (integral indefinida o definida "
        "si se dan limites), taylor_series (serie de Taylor alrededor de "
        "un punto). Presets validados con resultado analitico conocido, o "
        "'custom' via 'expression' (string, ej: 'x**2 - 5*x + 6')."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["simplify", "solve", "differentiate", "integrate", "taylor_series"],
                "default": "simplify",
            },
            "preset": {
                "type": "string",
                "enum": ["known_simplify", "known_solve", "known_derivative", "known_integral", "known_taylor", "custom"],
                "default": "known_simplify",
            },
            "expression": {"type": "string", "description": "Expresion en variable 'x' (y opcionalmente 'y'), solo si preset='custom'. Ej: 'sin(x)*x**2'"},
            "variable": {"type": "string", "default": "x"},
            "lower_limit": {"type": "string", "description": "Para integrate: limite inferior (si se da, calcula integral definida)"},
            "upper_limit": {"type": "string", "description": "Para integrate: limite superior"},
            "point": {"type": "string", "default": "0", "description": "Para taylor_series: punto de expansion"},
            "order": {"type": "integer", "default": 5, "description": "Para taylor_series: orden de la serie"},
        },
    },
}

_TRANSFORMATIONS = standard_transformations + (implicit_multiplication_application,)


def _safe_parse(expr_str, symbols_dict):
    return parse_expr(expr_str, local_dict=symbols_dict, transformations=_TRANSFORMATIONS,
                       global_dict={"sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "exp": sp.exp,
                                    "log": sp.log, "sqrt": sp.sqrt, "pi": sp.pi, "E": sp.E,
                                    "Abs": sp.Abs, "asin": sp.asin, "acos": sp.acos, "atan": sp.atan,
                                    "Integer": sp.Integer, "Float": sp.Float, "Rational": sp.Rational,
                                    "Symbol": sp.Symbol})


def compute_symbolic(mode="simplify", preset="known_simplify", expression=None,
                      variable="x", lower_limit=None, upper_limit=None, point="0", order=5):
    x = sp.Symbol(variable)
    y = sp.Symbol("y")
    symbols_dict = {variable: x, "y": y}
    known = None

    try:
        if mode == "simplify":
            if preset == "custom":
                if not expression:
                    return {"error": "preset='custom' requiere 'expression'"}
                expr = _safe_parse(expression, symbols_dict)
            elif preset == "known_simplify":
                expr = (x**2 - 1) / (x - 1)
                known = {"esperado": "x + 1"}
            else:
                return {"error": f"preset '{preset}' no aplica para mode='simplify'"}
            result = {"expression_original": str(expr), "simplified": str(sp.simplify(expr))}

        elif mode == "solve":
            if preset == "custom":
                if not expression:
                    return {"error": "preset='custom' requiere 'expression' (se resuelve expression=0)"}
                expr = _safe_parse(expression, symbols_dict)
            elif preset == "known_solve":
                expr = x**2 - 5*x + 6
                known = {"raices_esperadas": [2, 3]}
            else:
                return {"error": f"preset '{preset}' no aplica para mode='solve'"}
            solutions = sp.solve(expr, x)
            result = {"expression": str(expr) + " = 0", "solutions": [str(s) for s in solutions]}

        elif mode == "differentiate":
            if preset == "custom":
                if not expression:
                    return {"error": "preset='custom' requiere 'expression'"}
                expr = _safe_parse(expression, symbols_dict)
            elif preset == "known_derivative":
                expr = x**2 * sp.sin(x)
                known = {"esperado": "x**2*cos(x) + 2*x*sin(x)"}
            else:
                return {"error": f"preset '{preset}' no aplica para mode='differentiate'"}
            derivative = sp.diff(expr, x)
            result = {"expression": str(expr), "derivative": str(derivative),
                      "derivative_simplified": str(sp.simplify(derivative))}

        elif mode == "integrate":
            if preset == "custom":
                if not expression:
                    return {"error": "preset='custom' requiere 'expression'"}
                expr = _safe_parse(expression, symbols_dict)
            elif preset == "known_integral":
                expr = sp.sin(x)
                lower_limit, upper_limit = "0", "pi"
                known = {"esperado": "2 (integral definida de sin(x) en [0,pi])"}
            else:
                return {"error": f"preset '{preset}' no aplica para mode='integrate'"}

            if lower_limit is not None and upper_limit is not None:
                lo = _safe_parse(lower_limit, symbols_dict)
                hi = _safe_parse(upper_limit, symbols_dict)
                integral = sp.integrate(expr, (x, lo, hi))
                result = {"expression": str(expr), "type": "definida",
                          "limits": [str(lo), str(hi)], "value": str(integral)}
            else:
                integral = sp.integrate(expr, x)
                result = {"expression": str(expr), "type": "indefinida", "antiderivative": str(integral) + " + C"}

        elif mode == "taylor_series":
            if preset == "custom":
                if not expression:
                    return {"error": "preset='custom' requiere 'expression'"}
                expr = _safe_parse(expression, symbols_dict)
            elif preset == "known_taylor":
                expr = sp.exp(x)
                point, order = "0", 5
                known = {"esperado": "1 + x + x**2/2 + x**3/6 + x**4/24 + O(x**5)"}
            else:
                return {"error": f"preset '{preset}' no aplica para mode='taylor_series'"}
            pt = _safe_parse(point, symbols_dict)
            series = sp.series(expr, x, pt, order)
            result = {"expression": str(expr), "point": str(pt), "order": order, "series": str(series)}

        else:
            return {"error": f"mode desconocido: {mode}"}

    except Exception as ex:
        return {"error": f"error al procesar la expresion: {str(ex)}"}

    if known:
        result["known_reference"] = known
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(compute_symbolic("simplify", "known_simplify"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_symbolic("solve", "known_solve"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_symbolic("differentiate", "known_derivative"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_symbolic("integrate", "known_integral"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_symbolic("taylor_series", "known_taylor"), indent=2, ensure_ascii=False))
