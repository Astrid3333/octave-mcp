"""
ocas_symbolic_tool.py

Puente a oCAS (paquete Python "ocas", bindings de Rust, PyPI/crates.io),
un CAS mas nuevo y mas rapido que sympy para algunas operaciones
(el core esta en Rust). En desarrollo activo (v0.26.0 al momento de
escribir esto, jul-ago 2026) -- se valida cada modo contra un caso con
resultado analitico conocido antes de exponerlo a expresiones custom,
mismo criterio que symbolic_tool.py (sympy).

Nota de sintaxis: el parser de Expression("...") de ocas usa '^' para
potencia (NO es XOR de Python -- Python nunca ve ese caracter porque
va dentro de un string). '**' no esta soportado por el parser interno
y tira "parse error: unexpected token". Usar siempre '^' en los
strings de 'expression'.

Modes:
- symbolic: simplify / differentiate / integrate / substitute, via
  ocas.Expression (motor Rust).
- number_theory: isprime, factorint, nextprime, totient, divisor_sigma,
  mobius, liouville_lambda, jacobi_symbol, discrete_log, crt.
- diophantine: resuelve a*x + b*y = c (solucion particular + general).
"""
import ocas
from ocas import Expression

OCAS_SYMBOLIC_SCHEMA = {
    "name": "ocas_symbolic",
    "description": (
        "Algebra simbolica y teoria de numeros via oCAS (motor Rust, "
        "mas rapido que sympy pero mas nuevo/menos probado). "
        "mode='symbolic': simplify/differentiate/integrate/substitute "
        "sobre 'expression' (string, potencia con '^' NO '**', ej "
        "'x^2 + 2*x + 1'). mode='number_theory': operation=isprime|"
        "factorint|nextprime|totient|divisor_sigma|mobius|"
        "liouville_lambda|jacobi_symbol|discrete_log|crt sobre enteros. "
        "mode='diophantine': resuelve a*x+b*y=c. Presets con resultado "
        "conocido validado, o preset='custom' con los parametros propios."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["symbolic", "number_theory", "diophantine"], "default": "symbolic"},
            "preset": {"type": "string", "default": "known"},
            "sub_mode": {"type": "string", "description": "Para mode=symbolic: simplify|differentiate|integrate|substitute"},
            "expression": {"type": "string", "description": "Ej: 'x^2 + 2*x + 1'. Potencia SIEMPRE con '^'."},
            "variable": {"type": "string", "default": "x"},
            "sub_value": {"type": "string", "description": "Para substitute: valor a sustituir (string, se parsea como Expression)"},
            "operation": {"type": "string", "description": "Para mode=number_theory: isprime|factorint|nextprime|totient|divisor_sigma|mobius|liouville_lambda|jacobi_symbol|discrete_log|crt"},
            "n": {"type": "integer"},
            "a": {"type": "integer"},
            "b": {"type": "integer"},
            "c": {"type": "integer"},
            "moduli": {"type": "array", "items": {"type": "integer"}},
            "residues": {"type": "array", "items": {"type": "integer"}},
        },
    },
}


def compute_ocas_symbolic(mode="symbolic", preset="known", sub_mode=None, expression=None,
                           variable="x", sub_value=None, operation=None, n=None,
                           a=None, b=None, c=None, moduli=None, residues=None):
    known = None
    try:
        if mode == "symbolic":
            if preset == "custom":
                if not expression:
                    return {"error": "preset='custom' requiere 'expression' (usar '^' para potencia, no '**')"}
                expr = Expression(expression)
            else:
                expr = Expression("x^2 + 2*x + 1")
                expression = "x^2 + 2*x + 1"
                known = {"esperado_simplify": "1 + (2*x) + (x^2)", "esperado_diff": "2 + (2*x)"}

            if sub_mode == "differentiate":
                result = {"expression": str(expr), "derivative": str(expr.diff(variable))}
            elif sub_mode == "integrate":
                result = {"expression": str(expr), "antiderivative": str(expr.integrate(variable))}
            elif sub_mode == "substitute":
                if sub_value is None:
                    return {"error": "sub_mode='substitute' requiere 'sub_value'"}
                result = {"expression": str(expr), "substituted": str(expr.substitute(variable, Expression(sub_value)))}
            else:
                result = {"expression": str(expr), "simplified": str(expr.simplify())}

        elif mode == "number_theory":
            if preset != "custom":
                operation, n = "isprime", 97
                known = {"esperado": True, "nota": "97 es primo"}

            if operation == "isprime":
                result = {"n": n, "isprime": ocas.isprime(n)}
            elif operation == "factorint":
                result = {"n": n, "factors": ocas.factorint(n)}
            elif operation == "nextprime":
                result = {"n": n, "nextprime": ocas.nextprime(n)}
            elif operation == "totient":
                result = {"n": n, "totient": ocas.totient(n)}
            elif operation == "divisor_sigma":
                result = {"n": n, "divisor_sigma": ocas.divisor_sigma(n)}
            elif operation == "mobius":
                result = {"n": n, "mobius": ocas.mobius(n)}
            elif operation == "liouville_lambda":
                result = {"n": n, "liouville_lambda": ocas.liouville_lambda(n)}
            elif operation == "jacobi_symbol":
                if a is None or n is None:
                    return {"error": "jacobi_symbol requiere 'a' y 'n' (n impar positivo)"}
                result = {"a": a, "n": n, "jacobi_symbol": ocas.jacobi_symbol(a, n)}
            elif operation == "discrete_log":
                if n is None or a is None or b is None:
                    return {"error": "discrete_log requiere n=modulo primo, a=base, b=target (resuelve a^x=b mod n)"}
                result = {"p": n, "base": a, "target": b, "x": ocas.discrete_log(n, a, b)}
            elif operation == "crt":
                if not moduli or not residues:
                    return {"error": "crt requiere 'moduli' y 'residues' (mismo largo)"}
                r, m = ocas.crt(moduli, residues)
                result = {"moduli": moduli, "residues": residues, "r": r, "m": m}
            else:
                return {"error": f"operation desconocida: {operation}"}

        elif mode == "diophantine":
            if preset != "custom":
                a, b, c = 3, 5, 1
                known = {"esperado_particular": "(2, -1)  # 3*2+5*(-1)=1"}
            if a is None or b is None or c is None:
                return {"error": "diophantine requiere 'a', 'b', 'c' (resuelve a*x+b*y=c)"}
            sol = ocas.solve_diophantine(a, b, c)
            if sol is None:
                result = {"a": a, "b": b, "c": c, "solution": None, "nota": "no existe solucion entera"}
            else:
                result = {"a": a, "b": b, "c": c, "particular": sol.particular, "general_direction": sol.general}

        else:
            return {"error": f"mode desconocido: {mode}"}

    except Exception as ex:
        return {"error": f"error al procesar en oCAS: {str(ex)}"}

    if known:
        result["known_reference"] = known
    result["_ocas_version"] = ocas.ocas.__version__
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(compute_ocas_symbolic("symbolic", "known", sub_mode="differentiate"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_ocas_symbolic("number_theory", "known"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_ocas_symbolic("diophantine", "known"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_ocas_symbolic("symbolic", "custom", expression="x^2", sub_mode="integrate"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_ocas_symbolic("number_theory", "custom", operation="crt", moduli=[3, 5], residues=[2, 3]), indent=2, ensure_ascii=False))
