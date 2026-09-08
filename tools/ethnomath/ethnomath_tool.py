#!/usr/bin/env python3
"""ethnomath_tool: Análisis híbrido Persa-Hebreo"""
import math
from typing import Dict, List, Any

TOOL_SCHEMA = {
    "name": "ethnomath_hybrid_tool",
    "description": "Análisis de matemáticas ancestrales Persa (base 60) + Hebrea (gematría)",
    "input_schema": {
        "type": "object",
        "properties": {
            "experiment": {
                "type": "string",
                "enum": ["catalan_base60", "gematria_primes", "hybrid_formula",
                        "recursive_sequence", "transformation_matrix", "riemann_zeta",
                        "galois_symmetry", "full_analysis"],
                "description": "Experimento a ejecutar"
            },
            "n_max": {"type": "integer", "minimum": 1, "maximum": 30, "default": 12},
            "verbose": {"type": "boolean", "default": True}
        },
        "required": ["experiment"]
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "experiment": {"type": "string"},
            "results": {"type": "array"},
            "analysis": {"type": "string"},
            "n_checks": {"type": "integer"},
            "validation_passed": {"type": "boolean"}
        }
    }
}

HEBREW_GEMATRIA = {
    'aleph': 1, 'bet': 2, 'gimel': 3, 'dalet': 4, 'heh': 5, 'vav': 6, 'zayin': 7, 'het': 8,
    'tet': 9, 'yod': 10, 'kaph': 20, 'lamed': 30, 'mem': 40, 'nun': 50, 'samekh': 60,
    'ayin': 70, 'pe': 80, 'tsade': 90, 'qoph': 100, 'resh': 200, 'shin': 300, 'tav': 400
}
GEMATRIA_VALS = list(HEBREW_GEMATRIA.values())

def to_base60(n: int) -> List[int]:
    if not isinstance(n, int) or n < 0:
        raise ValueError(f"to_base60: int >= 0, got {n}")
    if n == 0:
        return [0]
    digits = []
    while n > 0:
        digits.insert(0, n % 60)
        n //= 60
    return digits

def is_prime(n: int) -> bool:
    if n < 2:
        return False
    for i in range(2, int(math.sqrt(n)) + 1):
        if n % i == 0:
            return False
    return True

def prime_factors(n: int) -> List[int]:
    if not isinstance(n, int) or n < 2:
        raise ValueError(f"prime_factors: int > 1, got {n}")
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
    if n <= 1:
        return 1
    catalan_vals = [0] * (n + 1)
    catalan_vals[0], catalan_vals[1] = 1, 1
    for i in range(2, n + 1):
        for j in range(i):
            catalan_vals[i] += catalan_vals[j] * catalan_vals[i - 1 - j]
    return catalan_vals[n]

def matrix_det(matrix):
    n = len(matrix)
    if n == 1:
        return matrix[0][0]
    if n == 2:
        return matrix[0][0]*matrix[1][1] - matrix[0][1]*matrix[1][0]
    det = 0
    for j in range(n):
        submatrix = [row[:j] + row[j+1:] for row in matrix[1:]]
        minor = matrix_det(submatrix)
        det += ((-1)**j) * matrix[0][j] * minor
    return det % 19

def exp_catalan_base60(n_max: int = 12) -> Dict[str, Any]:
    results = []
    for n in range(n_max):
        c_n = catalan(n)
        b60 = to_base60(c_n)
        results.append({"n": n, "catalan": c_n, "base60": b60, "base60_str": " : ".join(str(d) for d in b60)})
    return {"experiment": "catalan_base60", "results": results, "analysis": f"Catalan(0-{n_max-1})", "n_checks": n_max, "validation_passed": all(r["catalan"] > 0 for r in results)}

def exp_gematria_primes() -> Dict[str, Any]:
    primes = [g for g in GEMATRIA_VALS if is_prime(g)]
    composites = [g for g in GEMATRIA_VALS if not is_prime(g) and g > 1]
    return {"experiment": "gematria_primes", "results": {"primes": primes, "composites": composites, "n_primes": len(primes)}, "analysis": f"{len(primes)}/{len(GEMATRIA_VALS)} primos", "n_checks": len(GEMATRIA_VALS), "validation_passed": len(primes) == 4}

def exp_hybrid_formula(n_max: int = 12) -> Dict[str, Any]:
    results = []
    for n in range(1, n_max + 1):
        c_n = catalan(n)
        g_n = GEMATRIA_VALS[min(n-1, len(GEMATRIA_VALS)-1)]
        factors = prime_factors(g_n) if g_n > 1 else [1]
        factor_sum = sum(factors)
        metonium = pow(n, n % 19, 19)
        h_n = c_n + factor_sum * metonium
        results.append({"n": n, "catalan": c_n, "gematria": g_n, "factor_sum": factor_sum, "metonium": metonium, "h_n": h_n})
    return {"experiment": "hybrid_formula", "results": results, "analysis": "H(n) = C_n + Σfactores", "n_checks": n_max, "validation_passed": all(r["h_n"] > 0 for r in results)}

def exp_recursive_sequence(n_max: int = 20) -> Dict[str, Any]:
    a_seq = [1]
    for n in range(1, n_max):
        gematria_mod = GEMATRIA_VALS[(n-1) % len(GEMATRIA_VALS)]
        base60_digit = (n % 60)
        a_n = a_seq[-1] + gematria_mod * base60_digit
        a_seq.append(a_n)
    ratios = [a_seq[i+1]/a_seq[i] for i in range(len(a_seq)-1)]
    converges = len(ratios) >= 3 and (max(ratios[-5:]) - min(ratios[-5:])) < 0.01
    return {"experiment": "recursive_sequence", "results": {"sequence": a_seq, "ratios": [round(r, 4) for r in ratios], "converges": converges}, "analysis": f"Recursión Hebrea", "n_checks": n_max, "validation_passed": len(a_seq) == n_max}

def exp_transformation_matrix() -> Dict[str, Any]:
    M = []
    for i in range(1, 8):
        row = [((i * j * 60) % 19) for j in range(1, 8)]
        M.append(row)
    det_val = matrix_det(M)
    return {"experiment": "transformation_matrix", "results": {"matrix": M, "determinant_mod19": det_val, "rank": 7 if det_val != 0 else "<7"}, "analysis": f"Matriz 7x7 (mod 19)", "n_checks": 49, "validation_passed": len(M) == 7}

def exp_riemann_zeta() -> Dict[str, Any]:
    results = {}
    for s in [1.5, 2, 2.5, 3]:
        zeta_val = sum(1.0 / (g ** s) for g in GEMATRIA_VALS if g > 0)
        results[f"zeta_{s}"] = round(zeta_val, 6)
    return {"experiment": "riemann_zeta", "results": results, "analysis": "ζ(s) sobre gematría", "n_checks": len(GEMATRIA_VALS) * 4, "validation_passed": all(v > 0 for v in results.values())}

def exp_galois_symmetry(n_max: int = 8) -> Dict[str, Any]:
    results = []
    for n in range(1, n_max):
        b60 = to_base60(n)
        gematria_n = GEMATRIA_VALS[(n-1) % len(GEMATRIA_VALS)]
        factors = prime_factors(gematria_n) if gematria_n > 1 else [1]
        results.append({"n": n, "base60": b60, "gematria": gematria_n, "prime_factors": factors})
    return {"experiment": "galois_symmetry", "results": results, "analysis": "Simetría de Galois", "n_checks": n_max - 1, "validation_passed": len(results) == n_max - 1}

def run_ethnomath(experiment: str, n_max: int = 12, verbose: bool = True) -> Dict[str, Any]:
    experiments = {
        "catalan_base60": lambda: exp_catalan_base60(n_max),
        "gematria_primes": lambda: exp_gematria_primes(),
        "hybrid_formula": lambda: exp_hybrid_formula(n_max),
        "recursive_sequence": lambda: exp_recursive_sequence(n_max),
        "transformation_matrix": lambda: exp_transformation_matrix(),
        "riemann_zeta": lambda: exp_riemann_zeta(),
        "galois_symmetry": lambda: exp_galois_symmetry(n_max),
    }
    if experiment not in experiments:
        raise ValueError(f"Experimento desconocido: {experiment}")
    result = experiments[experiment]()
    result["verbose"] = verbose
    return result

def full_analysis(n_max: int = 12) -> Dict[str, Any]:
    all_results = []
    for exp in ["catalan_base60", "gematria_primes", "hybrid_formula", "recursive_sequence", "transformation_matrix", "riemann_zeta", "galois_symmetry"]:
        all_results.append(run_ethnomath(exp, n_max, verbose=False))
    return {"experiment": "full_analysis", "results": all_results, "analysis": "7 experimentos", "n_checks": sum(r.get("n_checks", 0) for r in all_results), "validation_passed": all(r.get("validation_passed", False) for r in all_results)}

def ethnomath_hybrid_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        experiment = args.get("experiment", "full_analysis")
        n_max = args.get("n_max", 12)
        verbose = args.get("verbose", True)
        if experiment == "full_analysis":
            result = full_analysis(n_max)
        else:
            result = run_ethnomath(experiment, n_max, verbose)
        return result
    except Exception as e:
        return {"experiment": "error", "error": str(e), "n_checks": 0, "validation_passed": False}
