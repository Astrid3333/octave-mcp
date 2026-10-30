"""
symengine_math_tool.py

SymEngine (nucleo C++): algebra simbolica rapida (expand, diff, subs, series
basicas, evaluacion numerica de precision arbitraria). Oraculo veloz para
validacion cruzada contra maxima/sympy.
"""

from pycas_runner import register_py_engine

_PREAMBLE = "from symengine import *\nx, y = symbols('x y')"

_SPECS = [
    ("expand_binomio_cubo", "expand((x + 1)**3 - (x**3 + 3*x**2 + 3*x + 1))", "0", "eq"),
    ("derivada_sin2", "expand(diff(sin(x)**2, x) - 2*sin(x)*cos(x))", "0", "eq"),
    ("racional_suma", "Rational(1, 3) + Rational(1, 6)", "1/2", "eq"),
    ("sqrt2_al_cuadrado", "sqrt(2)**2", "2", "eq"),
    ("subs_numerico", "(x**2 + y).subs({x: 3, y: 1})", "10", "eq"),
    ("pi_100_bits", "pi.n(100)", "3.14159265358979323846264338", "prefix"),
    ("error_sintaxis", "sympify('1+')", "-", "error"),
]

register_py_engine(
    "symengine_math_tool", "SymEngine", _PREAMBLE,
    "SymEngine: algebra simbolica rapida (x y predefinidos como simbolos): "
    "expand, diff, subs, sqrt, Rational, expr.n(bits). Modos: compute "
    "(expr Python con symengine importado) y validate.",
    _SPECS,
)

