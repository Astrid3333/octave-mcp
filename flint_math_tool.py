"""
flint_math_tool.py

python-flint (FLINT/Arb): aritmetica exacta de enteros, racionales, polinomios
(fmpz_poly/fmpq_poly), matrices (fmpz_mat/fmpq_mat), factorizacion y reales/
complejos de precision arbitraria con cotas de error (arb/acb).
"""

from pycas_runner import register_py_engine

_PREAMBLE = "from flint import *\nx = fmpz_poly([0, 1])\nX = fmpq_poly([0, 1])"

_SPECS = [
    ("factor_2_64_menos_1", "[(int(p), int(e)) for p, e in (fmpz(2)**64 - 1).factor()]",
     "[(3, 1), (5, 1), (17, 1), (257, 1), (641, 1), (65537, 1), (6700417, 1)]", "eq"),
    ("is_prime_mersenne_61", "bool((fmpz(2)**61 - 1).is_prime())", "True", "eq"),
    ("factor_poly_x4_menos_1", "len((x**4 - 1).factor()[1])", "3", "eq"),
    ("gcd_poly", "[int(c) for c in (x**2 - 1).gcd(x - 1).coeffs()]", "[-1, 1]", "eq"),
    ("fmpq_suma", "fmpq(1, 3) + fmpq(1, 6)", "1/2", "eq"),
    ("det_matriz_2x2", "fmpz_mat([[1, 2], [3, 4]]).det()", "-2", "eq"),
    ("arb_pi_15_digitos", "arb.pi().str(15, radius=False)", "3.14159265358979", "prefix"),
    ("error_div_cero", "fmpz(1) // fmpz(0)", "-", "error"),
]

register_py_engine(
    "flint_math_tool", "python-flint (FLINT/Arb)", _PREAMBLE,
    "python-flint: aritmetica exacta (fmpz/fmpq), polinomios fmpz_poly/fmpq_poly "
    "(x y X predefinidos), matrices fmpz_mat/fmpq_mat, factorizacion y reales "
    "arb/acb con cotas. Modos: compute (expr Python con flint importado) y validate.",
    _SPECS,
)

