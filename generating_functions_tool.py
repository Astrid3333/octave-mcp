"""Funciones generatrices ordinarias, exponenciales y recurrencias lineales."""

from __future__ import annotations

import ast
from fractions import Fraction
from typing import Any

from advanced_combinatorics_common import need_int, need_list, safe_number
from tool_registry import register_tool


MAX_TERMS = 10000
MAX_EXPRESSION_LENGTH = 500
ALLOWED_FUNCTIONS = {
    "Abs",
    "E",
    "I",
    "Rational",
    "binomial",
    "cos",
    "exp",
    "factorial",
    "log",
    "pi",
    "sin",
    "sqrt",
    "tan",
}


def _integer_list(args: dict[str, Any], key: str, *, required: bool = False) -> list[int]:
    values = need_list(args, key, required=required)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ValueError(f"'{key}' debe contener enteros")
    return values


def _recurrence_data(args: dict[str, Any]) -> tuple[list[int], list[int]]:
    recurrence = _integer_list(args, "recurrence", required=True)
    initial = _integer_list(args, "initial", required=True)
    if not recurrence:
        raise ValueError("'recurrence' no puede estar vacia")
    if len(initial) != len(recurrence):
        raise ValueError("'initial' y 'recurrence' deben tener la misma longitud")
    return recurrence, initial


def _sequence_terms(initial: list[int], recurrence: list[int], count: int) -> list[int]:
    if count < 0 or count > MAX_TERMS:
        raise ValueError(f"el numero de terminos debe estar entre 0 y {MAX_TERMS}")
    order = len(recurrence)
    terms = list(initial[:count])
    while len(terms) < count:
        position = len(terms)
        terms.append(sum(recurrence[index] * terms[position - index - 1] for index in range(order)))
    return terms


def _ordinary_fraction(initial: list[int], recurrence: list[int]) -> tuple[list[int], list[int]]:
    order = len(recurrence)
    denominator = [0] * (order + 1)
    denominator[0] = 1
    for index, coefficient in enumerate(recurrence, start=1):
        denominator[index] = -coefficient
    numerator = [0] * order
    for degree in range(order):
        value = initial[degree]
        for index in range(1, degree + 1):
            value -= recurrence[index - 1] * initial[degree - index]
        numerator[degree] = value
    return numerator, denominator


def _sympy_polynomial(coefficients: list[int], variable: Any) -> Any:
    from sympy import Add

    return Add(*(coefficient * variable**degree for degree, coefficient in enumerate(coefficients)))


def _rsolve(initial: list[int], recurrence: list[int]) -> tuple[str, Any]:
    from sympy import Eq, Function, rsolve, symbols

    sequence = Function("a")
    index = symbols("n", integer=True)
    equation = Eq(
        sequence(index),
        sum(recurrence[position] * sequence(index - position - 1) for position in range(len(recurrence))),
    )
    solution = rsolve(equation, sequence(index), init={position: value for position, value in enumerate(initial)})
    return str(solution), solution


def _safe_expression(expression: str, variable_name: str = "x") -> Any:
    from sympy import E, I, Abs, Integer, Rational, Symbol, factorial
    from sympy import binomial as sympy_binomial
    from sympy import cos, exp, log, pi, sin, sqrt, tan
    from sympy.parsing.sympy_parser import parse_expr

    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("'expression' debe ser una cadena no vacia")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ValueError(f"'expression' supera {MAX_EXPRESSION_LENGTH} caracteres")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("'expression' no es una expresion valida") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            raise ValueError("no se permiten atributos en la expresion")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_FUNCTIONS:
                raise ValueError("la expresion usa una funcion no permitida")
        if isinstance(node, ast.Name) and node.id not in ALLOWED_FUNCTIONS and node.id != variable_name:
            raise ValueError(f"simbolo no permitido: {node.id}")
    variable = Symbol(variable_name)
    globals_ = {
        "__builtins__": {},
        "Abs": Abs,
        "E": E,
        "I": I,
        "Integer": Integer,
        "Rational": Rational,
        "Symbol": Symbol,
        "binomial": sympy_binomial,
        "cos": cos,
        "exp": exp,
        "factorial": factorial,
        "log": log,
        "pi": pi,
        "sin": sin,
        "sqrt": sqrt,
        "tan": tan,
    }
    return parse_expr(
        expression,
        local_dict={variable_name: variable},
        global_dict=globals_,
        evaluate=True,
    )


def _egf_coefficients(terms: list[int]) -> list[str]:
    from math import factorial

    return [safe_number(Fraction(term, factorial(index))) for index, term in enumerate(terms)]


def _ordinary_result(args: dict[str, Any]) -> dict[str, Any]:
    from sympy import cancel, symbols

    variable = symbols("x")
    recurrence = _integer_list(args, "recurrence")
    initial = _integer_list(args, "initial")
    coefficients = _integer_list(args, "coefficients")
    if recurrence or initial:
        if not recurrence or not initial:
            raise ValueError("'recurrence' e 'initial' deben enviarse juntos")
        if len(recurrence) != len(initial):
            raise ValueError("'recurrence' e 'initial' deben tener la misma longitud")
        numerator, denominator = _ordinary_fraction(initial, recurrence)
        count = need_int(args, "n", default=len(initial) + 6, minimum=0, maximum=MAX_TERMS)
        terms = _sequence_terms(initial, recurrence, count)
        ogf = cancel(_sympy_polynomial(numerator, variable) / _sympy_polynomial(denominator, variable))
        return {
            "kind": "ordinary",
            "numerator": numerator,
            "denominator": denominator,
            "ogf": str(ogf),
            "coefficients": safe_number(terms),
            "a_n": safe_number(terms[-1]) if terms else None,
        }
    if coefficients:
        count = need_int(args, "n", default=len(coefficients), minimum=0, maximum=MAX_TERMS)
        selected = coefficients[:count]
        return {
            "kind": "ordinary",
            "numerator": selected,
            "denominator": [1],
            "ogf": str(_sympy_polynomial(selected, variable)),
            "coefficients": safe_number(selected),
            "a_n": safe_number(selected[-1]) if selected else None,
        }
    raise ValueError("se requiere 'recurrence' con 'initial' o una lista 'coefficients'")


def _exponential_result(args: dict[str, Any]) -> dict[str, Any]:
    from sympy import Sum, factorial, oo, symbols

    variable = symbols("x")
    index = symbols("n", integer=True)
    recurrence = _integer_list(args, "recurrence")
    initial = _integer_list(args, "initial")
    coefficients = _integer_list(args, "coefficients")
    if recurrence or initial:
        if not recurrence or not initial:
            raise ValueError("'recurrence' e 'initial' deben enviarse juntos")
        if len(recurrence) != len(initial):
            raise ValueError("'recurrence' e 'initial' deben tener la misma longitud")
        count = need_int(args, "n", default=len(initial) + 6, minimum=0, maximum=MAX_TERMS)
        terms = _sequence_terms(initial, recurrence, count)
        closed_text, closed = _rsolve(initial, recurrence)
        egf = Sum(closed * variable**index / factorial(index), (index, 0, oo))
        return {
            "kind": "exponential",
            "closed_form": closed_text,
            "egf": str(egf),
            "sequence_coefficients": safe_number(terms),
            "egf_coefficients": _egf_coefficients(terms),
            "a_n": safe_number(terms[-1]) if terms else None,
        }
    if coefficients:
        count = need_int(args, "n", default=len(coefficients), minimum=0, maximum=MAX_TERMS)
        selected = coefficients[:count]
        finite = sum(selected[index] * variable**index / factorial(index) for index in range(len(selected)))
        return {
            "kind": "exponential",
            "closed_form": None,
            "egf": str(finite),
            "sequence_coefficients": safe_number(selected),
            "egf_coefficients": _egf_coefficients(selected),
            "a_n": safe_number(selected[-1]) if selected else None,
        }
    raise ValueError("se requiere 'recurrence' con 'initial' o una lista 'coefficients'")


def _recurrence_result(args: dict[str, Any]) -> dict[str, Any]:
    from sympy import Sum, factorial, oo, symbols

    variable = symbols("x")
    index = symbols("n", integer=True)
    recurrence, initial = _recurrence_data(args)
    count = need_int(args, "n", default=len(initial) + 6, minimum=0, maximum=MAX_TERMS)
    terms = _sequence_terms(initial, recurrence, count)
    numerator, denominator = _ordinary_fraction(initial, recurrence)
    closed_text, closed = _rsolve(initial, recurrence)
    ogf = _sympy_polynomial(numerator, variable) / _sympy_polynomial(denominator, variable)
    egf = Sum(closed * variable**index / factorial(index), (index, 0, oo))
    return {
        "kind": "recurrence",
        "recurrence": recurrence,
        "initial": initial,
        "closed_form": closed_text,
        "ogf": str(ogf),
        "egf": str(egf),
        "coefficients": safe_number(terms),
        "a_n": safe_number(terms[-1]) if terms else None,
    }


def _coefficient_result(args: dict[str, Any]) -> dict[str, Any]:
    from sympy import series

    variable_name = args.get("variable", "x")
    if not isinstance(variable_name, str) or not variable_name.isidentifier():
        raise ValueError("'variable' debe ser un identificador")
    expression = _safe_expression(args.get("expression"), variable_name)
    degree = need_int(args, "n", minimum=0, maximum=1000, required=True)
    variable = _safe_expression(variable_name, variable_name)
    expansion = series(expression, variable, 0, degree + 1).removeO().expand()
    coefficient = expansion.coeff(variable, degree)
    return {
        "kind": "coefficient",
        "expression": str(expression),
        "variable": variable_name,
        "n": degree,
        "coefficient": safe_number(coefficient),
    }


def _validate() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    fibonacci = _recurrence_result({"recurrence": [1, 1], "initial": [0, 1], "n": 11})
    check("Fibonacci a_10=55", fibonacci.get("a_n") == 55, str(fibonacci.get("a_n")))
    check("Fibonacci OGF numerator x", fibonacci.get("ogf", "").startswith("x/"), fibonacci.get("ogf", ""))
    check("Fibonacci closed form is symbolic", "sqrt(5)" in fibonacci.get("closed_form", ""), fibonacci.get("closed_form", ""))
    coefficient = _coefficient_result({"expression": "1/(1-x-x**2)", "n": 10})
    check("coefficient of x^10 in 1/(1-x-x^2) is 89", coefficient.get("coefficient") == 89, str(coefficient.get("coefficient")))
    ordinary = _ordinary_result({"coefficients": [1, 1, 2, 3, 5]})
    check("ordinary coefficients are preserved", ordinary.get("coefficients") == [1, 1, 2, 3, 5], str(ordinary.get("coefficients")))
    exponential = _exponential_result({"recurrence": [2], "initial": [1], "n": 5})
    check("EGF coefficient of 2^4/4! is 2/3", exponential.get("egf_coefficients", [])[4] == "2/3", str(exponential.get("egf_coefficients")))
    try:
        unsafe = _coefficient_result({"expression": "__import__('os').system('true')", "n": 0})
        rejected = "error" in unsafe
    except ValueError:
        rejected = True
    check("unsafe expression is rejected", rejected)
    return {"validation_passed": all(item["passed"] for item in checks), "checks": checks}


def compute_generating_functions(args: dict[str, Any]) -> dict[str, Any]:
    try:
        mode = args.get("mode", "validate")
        if mode == "validate":
            return _validate()
        if mode == "ordinary":
            return _ordinary_result(args)
        if mode == "exponential":
            return _exponential_result(args)
        if mode == "coefficient":
            return _coefficient_result(args)
        if mode == "recurrence":
            return _recurrence_result(args)
        raise ValueError("mode invalido")
    except (ValueError, TypeError, OverflowError, MemoryError, SyntaxError) as exc:
        return {"error": str(exc)}


GENERATING_FUNCTIONS_SCHEMA = {
    "name": "generating_functions_tool",
    "description": (
        "Funciones generatrices y recurrencias lineales exactas: OGF racional "
        "P(x)/Q(x), EGF con coeficientes a_n/n!, extraccion de coeficientes "
        "por series simbolicas y forma cerrada mediante rsolve de SymPy. "
        "Modos ordinary, exponential, coefficient, recurrence y validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["ordinary", "exponential", "coefficient", "recurrence", "validate"],
                "default": "validate",
            },
            "recurrence": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "a_n=c1*a_(n-1)+...+cr*a_(n-r)",
            },
            "initial": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Valores iniciales a_0..a_(r-1)",
            },
            "coefficients": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Coeficientes dados para una OGF/EGF truncada",
            },
            "expression": {"type": "string", "description": "Expresion simbolica en la variable"},
            "variable": {"type": "string", "default": "x", "description": "Variable de la expresion"},
            "n": {"type": "integer", "minimum": 0, "description": "Indice o numero de terminos"},
        },
        "required": ["mode"],
    },
}


register_tool(
    name="generating_functions_tool",
    schema=GENERATING_FUNCTIONS_SCHEMA,
    handler=compute_generating_functions,
)
