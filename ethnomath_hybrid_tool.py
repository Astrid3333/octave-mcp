#!/usr/bin/env python3
"""
ethnomath_hybrid_tool: Matemáticas ancestrales Persa (base-60) + Hebrea (gematría),
con una fórmula híbrida H(n) que combina Catalan, factores primos de gematría y
el ciclo de Metón (19 años). Adaptado de un script de exploración
(ethnomath_hybrid_analysis.py) a formato tool MCP: sin prints a nivel de módulo,
todo devuelto como dict serializable.
"""
import math
from typing import Dict, List, Any

TOOL_NAME = "ethnomath_hybrid_tool"

HEBREW_GEMATRIA = {
    'aleph': 1, 'bet': 2, 'gimel': 3, 'dalet': 4, 'heh': 5,
    'vav': 6, 'zayin': 7, 'het': 8, 'tet': 9, 'yod': 10,
    'kaph': 20, 'lamed': 30, 'mem': 40, 'nun': 50, 'samekh': 60,
    'ayin': 70, 'pe': 80, 'tsade': 90, 'qoph': 100, 'resh': 200,
    'shin': 300, 'tav': 400
}
GEMATRIA_VALS = list(HEBREW_GEMATRIA.values())

TOOL_SCHEMA = {
    "name": "ethnomath_hybrid_tool",
    "description": (
        "Matemáticas ancestrales híbridas Persa (base-60) + Hebrea (gematría): "
        "Catalan en base-60, primalidad de valores gematría, fórmula híbrida H(n) "
        "(Catalan + factores primos de gematría + ciclo de Metón), secuencia "
        "recursiva hebrea, matriz de transformación Persa-Hebrea, zeta de Riemann "
        "sobre gematría, simetría Galois base60↔factorización."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "catalan_base60", "gematria_primality", "hybrid_formula",
                    "recursive_sequence", "transformation_matrix",
                    "riemann_zeta_gematria", "galois_symmetry", "all", "validate"
                ]
            },
            "params": {"type": "object"}
        },
        "required": ["mode"]
    }
}


def to_base60(n: int) -> List[int]:
    if not isinstance(n, int) or n < 0:
        raise ValueError(f"to_base60: esperado int >= 0, recibido {n}")
    if n == 0:
        return [0]
    digits = []
    while n > 0:
        digits.insert(0, n % 60)
        n //= 60
    return digits


def from_base60(digits: List[int]) -> int:
    if not isinstance(digits, (list, tuple)):
        raise ValueError(f"from_base60: esperado list, recibido {type(digits)}")
    result = 0
    for d in digits:
        if not isinstance(d, int) or d < 0 or d >= 60:
            raise ValueError(f"from_base60: dígito inválido {d}")
        result = result * 60 + d
    return result


def is_prime(n: int) -> bool:
    if not isinstance(n, int) or n < 0:
        raise ValueError(f"is_prime: esperado int >= 0, recibido {n}")
    if n < 2:
        return False
    for i in range(2, int(math.sqrt(n)) + 1):
        if n % i == 0:
            return False
    return True


def prime_factors(n: int) -> List[int]:
    if not isinstance(n, int) or n < 2:
        raise ValueError(f"prime_factors: esperado int > 1, recibido {n}")
    factors = []
    d = 2
    while d * d <= n:
        while n % d == 0:
            factors.append(d)
            n //= d
        d += 1
    if n > 1:
        factors.append(n)
    return factors


def catalan(n: int) -> int:
    if not isinstance(n, int) or n < 0:
        raise ValueError(f"catalan: esperado int >= 0, recibido {n}")
    if n <= 1:
        return 1
    catalan_vals = [0] * (n + 1)
    catalan_vals[0], catalan_vals[1] = 1, 1
    for i in range(2, n + 1):
        for j in range(i):
            catalan_vals[i] += catalan_vals[j] * catalan_vals[i - 1 - j]
    return catalan_vals[n]


def matrix_det(matrix: List[List[int]]) -> int:
    """Determinante vía Laplace (mod 19). NOTA (bug heredado del script original,
    conservado a propósito, ver 'known_issue_matrix_det' en modo validate):
    la rama n==2 no aplica %19, solo la rama recursiva de Laplace lo hace en el
    nivel superior -- valores intermedios sin modular pueden filtrarse en la
    recursión. No se corrigió para no alterar el resultado ya revisado a mano
    en la sesión original."""
    n = len(matrix)
    if n == 0:
        raise ValueError("matrix_det: matrix vacía")
    if n == 1:
        return matrix[0][0]
    if n == 2:
        return matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]
    det = 0
    for j in range(n):
        submatrix = [row[:j] + row[j + 1:] for row in matrix[1:]]
        minor = matrix_det(submatrix)
        det += ((-1) ** j) * matrix[0][j] * minor
    return det % 19


def _exp_catalan_base60(n_max: int = 8) -> Dict[str, Any]:
    rows = []
    for n in range(n_max):
        c_n = catalan(n)
        b60 = to_base60(c_n)
        rows.append({"n": n, "catalan": c_n, "base60": b60})
    return {"mode": "catalan_base60", "rows": rows}


def _exp_gematria_primality() -> Dict[str, Any]:
    primes = [g for g in GEMATRIA_VALS if is_prime(g)]
    composites = [g for g in GEMATRIA_VALS if not is_prime(g) and g > 1]
    return {
        "mode": "gematria_primality",
        "prime_gematriae": primes,
        "composite_gematriae": composites,
        "ratio_primes": len(primes) / len(GEMATRIA_VALS),
    }


def _exp_hybrid_formula(n_max: int = 12) -> Dict[str, Any]:
    rows = []
    for n in range(1, n_max + 1):
        c_n = catalan(n)
        g_n = GEMATRIA_VALS[min(n - 1, len(GEMATRIA_VALS) - 1)]
        factors = prime_factors(g_n) if g_n > 1 else [1]
        factor_sum = sum(factors)
        metonium = pow(n, n % 19, 19)
        h_n = c_n + factor_sum * metonium
        rows.append({
            "n": n, "catalan": c_n, "gematria": g_n,
            "factor_sum": factor_sum, "metonium": metonium, "H_n": h_n,
        })
    return {"mode": "hybrid_formula", "rows": rows}


def _exp_recursive_sequence(n_max: int = 19) -> Dict[str, Any]:
    a_seq = [1]
    for n in range(1, n_max + 1):
        gematria_mod = GEMATRIA_VALS[(n - 1) % len(GEMATRIA_VALS)]
        base60_digit = n % 60
        a_n = a_seq[-1] + gematria_mod * base60_digit
        a_seq.append(a_n)
    ratios = [a_seq[i + 1] / a_seq[i] for i in range(len(a_seq) - 1)]
    tol = 0.01
    last_5 = ratios[-5:]
    converges = len(last_5) >= 3 and (max(last_5) - min(last_5) < tol)
    return {
        "mode": "recursive_sequence",
        "sequence_preview": a_seq[:10],
        "sequence_length": len(a_seq),
        "ratios_preview": ratios[:10],
        "converges": converges,
        "final_ratio": ratios[-1] if ratios else None,
    }


def _exp_transformation_matrix() -> Dict[str, Any]:
    M = []
    for i in range(1, 8):
        row = [(i * j * 60) % 19 for j in range(1, 8)]
        M.append(row)
    det_val = matrix_det(M)
    return {
        "mode": "transformation_matrix",
        "matrix": M,
        "determinant_mod19": det_val,
        "known_issue_matrix_det": (
            "matrix_det no aplica %19 en la rama n==2, solo en la recursion "
            "de Laplace del nivel superior; se conserva sin corregir del "
            "script original -- ver docstring de matrix_det."
        ),
    }


def _exp_riemann_zeta_gematria(s_values: List[float] = None) -> Dict[str, Any]:
    if s_values is None:
        s_values = [1.5, 2, 2.5, 3]
    results = {}
    for s in s_values:
        results[str(s)] = sum(1.0 / (g ** s) for g in GEMATRIA_VALS if g > 0)
    return {"mode": "riemann_zeta_gematria", "zeta_values": results}


def _exp_galois_symmetry(n_max: int = 7) -> Dict[str, Any]:
    rows = []
    for n in range(1, n_max + 1):
        b60 = to_base60(n)
        gematria_n = GEMATRIA_VALS[(n - 1) % len(GEMATRIA_VALS)]
        factors = prime_factors(gematria_n) if gematria_n > 1 else [1]
        rows.append({"n": n, "base60": b60, "gematria": gematria_n, "factors": factors})
    return {"mode": "galois_symmetry", "rows": rows}


def _validate() -> Dict[str, Any]:
    checks = []

    def check(name, cond):
        checks.append({"name": name, "passed": bool(cond)})

    check("to_base60(0)==[0]", to_base60(0) == [0])
    check("from_base60(to_base60(3723))==3723", from_base60(to_base60(3723)) == 3723)
    check("catalan(0)==1 and catalan(1)==1", catalan(0) == 1 and catalan(1) == 1)
    check("catalan(4)==14", catalan(4) == 14)
    check("is_prime(2) and not is_prime(1)", is_prime(2) and not is_prime(1))
    check("prime_factors(60)==[2,2,3,5]", prime_factors(60) == [2, 2, 3, 5])
    check("len(GEMATRIA_VALS)==22", len(GEMATRIA_VALS) == 22)
    check("hybrid_formula produces 12 rows", len(_exp_hybrid_formula(12)["rows"]) == 12)
    check("recursive_sequence length matches n_max+1", _exp_recursive_sequence(19)["sequence_length"] == 20)
    check("transformation_matrix is 7x7", len(_exp_transformation_matrix()["matrix"]) == 7)

    passed = sum(1 for c in checks if c["passed"])
    return {
        "mode": "validate",
        "checks": checks,
        "n_checks": len(checks),
        "n_passed": passed,
        "validation_passed": passed == len(checks),
    }


def ethnomath_hybrid_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    mode = args.get("mode", "validate")
    params = args.get("params", {}) or {}
    try:
        if mode == "catalan_base60":
            return _exp_catalan_base60(params.get("n_max", 8))
        elif mode == "gematria_primality":
            return _exp_gematria_primality()
        elif mode == "hybrid_formula":
            return _exp_hybrid_formula(params.get("n_max", 12))
        elif mode == "recursive_sequence":
            return _exp_recursive_sequence(params.get("n_max", 19))
        elif mode == "transformation_matrix":
            return _exp_transformation_matrix()
        elif mode == "riemann_zeta_gematria":
            return _exp_riemann_zeta_gematria(params.get("s_values"))
        elif mode == "galois_symmetry":
            return _exp_galois_symmetry(params.get("n_max", 7))
        elif mode == "all":
            return {
                "mode": "all",
                "catalan_base60": _exp_catalan_base60(params.get("n_max", 8)),
                "gematria_primality": _exp_gematria_primality(),
                "hybrid_formula": _exp_hybrid_formula(params.get("n_max", 12)),
                "recursive_sequence": _exp_recursive_sequence(params.get("n_max", 19)),
                "transformation_matrix": _exp_transformation_matrix(),
                "riemann_zeta_gematria": _exp_riemann_zeta_gematria(params.get("s_values")),
                "galois_symmetry": _exp_galois_symmetry(params.get("n_max", 7)),
            }
        elif mode == "validate":
            return _validate()
        else:
            raise ValueError(f"modo desconocido: {mode}")
    except Exception as e:
        return {"mode": mode, "error": str(e), "validation_passed": False}


try:
    from tool_registry import register_tool
    register_tool(
        name=TOOL_SCHEMA["name"],
        schema=TOOL_SCHEMA,
        handler=ethnomath_hybrid_tool,
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    d = ethnomath_hybrid_tool({"mode": "validate"})
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de ethnomath_hybrid_tool.py pasaron OK.")
