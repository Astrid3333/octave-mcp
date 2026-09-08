#!/usr/bin/env python3
"""
ethnomath_comparative_tool: Comparación de 3 sistemas ancestrales
- Persa (base 60, Metón 19 años)
- Ternaria Rusa (base 3 balanceada, TritOS)
- Cananeo (ciclos lunares 13 + Fibonacci)

Tool para octave-mcp registry
"""

import math
from typing import Dict, List, Any

TOOL_SCHEMA = {
    "name": "ethnomath_comparative_tool",
    "description": "Comparación de matemáticas ancestrales: Persa (base 60) vs Ternaria Rusa (base 3 bal) vs Cananeo (ciclos lunares). "
                   "Catalan en 3 bases, análisis de primalidad, secuencias híbridas H(n) según cada sistema.",
    "input_schema": {
        "type": "object",
        "properties": {
            "experiment": {
                "type": "string",
                "enum": [
                    "catalan_bases",
                    "primes_systems",
                    "hybrid_sequences",
                    "full_comparative"
                ],
                "description": "Experimento comparativo"
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

# ============================================================
# TERNARIA RUSA (Base 3 Balanceada)
# ============================================================

def to_balanced_ternary(n: int) -> List[int]:
    """Base 3 balanceada: dígitos en {-1, 0, 1} (notación: T, 0, 1)"""
    if n == 0:
        return [0]
    
    digits_3 = []
    temp = abs(n)
    while temp > 0:
        digits_3.insert(0, temp % 3)
        temp //= 3
    
    balanced = []
    carry = 0
    for d in reversed(digits_3):
        d += carry
        if d >= 2:
            balanced.insert(0, d - 3)
            carry = 1
        else:
            balanced.insert(0, d)
            carry = 0
    
    if carry:
        balanced.insert(0, carry)
    
    if n < 0:
        balanced = [-d for d in balanced]
    
    return balanced

def balanced_ternary_to_str(digits: List[int]) -> str:
    """Notación legible: T=-1, 0, 1"""
    return "".join(["T" if d == -1 else str(d) for d in digits])

# ============================================================
# CANANEO (Ciclos Lunares + Fibonacci)
# ============================================================

CANAANITE_CYCLES = {
    'shana': 13,      # año lunar
    'hodesh': 29,     # mes lunar
    'chaos': 8,       # Fibonacci (complejidad)
    'harmony': 5,     # Fibonacci (armonía)
    'balance': 3,     # Fibonacci (balance)
    'duality': 2,     # Fibonacci
    'unity': 1
}

CANAANITE_VALS = list(CANAANITE_CYCLES.values())
FIBONACCI_SEQ = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144]

# ============================================================
# UTILIDADES
# ============================================================

def is_prime(n: int) -> bool:
    if n < 2:
        return False
    for i in range(2, int(math.sqrt(n)) + 1):
        if n % i == 0:
            return False
    return True

def prime_factors(n: int) -> List[int]:
    if n < 2:
        return [1]
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

def to_base60(n: int) -> str:
    if n == 0:
        return "0"
    digits = []
    while n > 0:
        digits.insert(0, n % 60)
        n //= 60
    return " : ".join(str(d) for d in digits)

# ============================================================
# EXPERIMENTOS COMPARATIVOS
# ============================================================

def exp_catalan_bases(n_max: int = 12) -> Dict[str, Any]:
    """Catalan(n) en Persa (base60) vs Ternaria vs Cananeo"""
    results = []
    
    for n in range(n_max):
        c_n = catalan(n)
        b60 = to_base60(c_n)
        b3 = to_balanced_ternary(c_n)
        b3_str = balanced_ternary_to_str(b3)
        factors = prime_factors(c_n) if c_n > 1 else [1]
        lunar_factors = sum(1 for f in factors if f in CANAANITE_VALS)
        
        results.append({
            "n": n,
            "catalan": c_n,
            "persan_base60": b60,
            "russian_ternary": b3_str,
            "canaanite_lunar_factors": lunar_factors,
            "prime_factors": factors
        })
    
    return {
        "experiment": "catalan_bases",
        "results": results,
        "analysis": f"Catalan(0-{n_max-1}): Persa (60) vs Ternaria Rusa (3-bal) vs Cananeo (ciclos lunares)",
        "n_checks": n_max,
        "validation_passed": len(results) == n_max
    }

def exp_primes_systems() -> Dict[str, Any]:
    """Primalidad comparada en los 3 sistemas"""
    
    # Persa (gematría)
    persan_vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30]
    persan_primes = [v for v in persan_vals if is_prime(v)]
    
    # Ternaria (potencias de 3: 1, 3, 9, 27, 81, 243)
    ternary_vals = [3**i for i in range(6)]
    ternary_primes = [v for v in ternary_vals if is_prime(v)]
    
    # Cananeo (ciclos lunares: 1, 2, 3, 5, 8, 13, 29)
    canaanite_primes = [v for v in CANAANITE_VALS if is_prime(v)]
    
    return {
        "experiment": "primes_systems",
        "results": {
            "persan": {
                "values": persan_vals,
                "primes": persan_primes,
                "n_primes": len(persan_primes),
                "ratio": round(len(persan_primes) / len(persan_vals), 3)
            },
            "russian_ternary": {
                "values": ternary_vals,
                "primes": ternary_primes,
                "n_primes": len(ternary_primes),
                "ratio": round(len(ternary_primes) / len(ternary_vals), 3)
            },
            "canaanite": {
                "values": sorted(CANAANITE_VALS),
                "primes": sorted(canaanite_primes),
                "n_primes": len(canaanite_primes),
                "ratio": round(len(canaanite_primes) / len(CANAANITE_VALS), 3)
            }
        },
        "analysis": f"Densidad prima: Persa={len(persan_primes)}/{len(persan_vals)} vs Ternaria={len(ternary_primes)}/{len(ternary_vals)} vs Cananeo={len(canaanite_primes)}/{len(CANAANITE_VALS)}",
        "n_checks": len(persan_vals) + len(ternary_vals) + len(CANAANITE_VALS),
        "validation_passed": True
    }

def exp_hybrid_sequences(n_max: int = 12) -> Dict[str, Any]:
    """Secuencia H(n) personalizada para cada sistema"""
    results = []
    
    for n in range(1, n_max + 1):
        c_n = catalan(n)
        
        # PERSA: H_p(n) = C_n + Σfactores(gematría) * n^(n mod 19) [Metón 19 años]
        persan_gematria = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30]
        g_n = persan_gematria[min(n-1, len(persan_gematria)-1)]
        factors_p = prime_factors(g_n) if g_n > 1 else [1]
        metonium = pow(n, n % 19, 19)
        h_persan = c_n + sum(factors_p) * metonium
        
        # TERNARIA: H_t(n) = C_n + popcount(ternaria(n)) * 3^(n mod 5)
        # popcount = cantidad de dígitos no-cero
        b3 = to_balanced_ternary(n)
        popcount = sum(1 for d in b3 if d != 0)
        power_3 = pow(3, n % 5)
        h_ternary = c_n + popcount * power_3
        
        # CANANEO: H_c(n) = C_n + (n mod 13) * Fib(n mod 8)
        # n mod 13 = ciclos lunares año
        # Fib = armonía cíclica
        lunar_mod = n % 13
        fib_idx = n % 8
        fib_val = FIBONACCI_SEQ[fib_idx]
        h_canaanite = c_n + lunar_mod * fib_val
        
        results.append({
            "n": n,
            "catalan": c_n,
            "h_persan": h_persan,
            "h_ternary": h_ternary,
            "h_canaanite": h_canaanite,
            "persan_metonium": metonium,
            "ternary_popcount": popcount,
            "canaanite_lunar": lunar_mod,
            "canaanite_fib": fib_val
        })
    
    return {
        "experiment": "hybrid_sequences",
        "results": results,
        "analysis": f"H(n) híbrida: Persa (Metón 19) vs Ternaria (base3) vs Cananeo (ciclos lunares × Fib)",
        "n_checks": n_max,
        "validation_passed": all(
            r["h_persan"] > 0 and r["h_ternary"] > 0 and r["h_canaanite"] > 0
            for r in results
        )
    }

# ============================================================
# DISPATCHER
# ============================================================

def ethnomath_comparative_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """MCP tool entrypoint"""
    try:
        experiment = args.get("experiment", "full_comparative")
        n_max = args.get("n_max", 12)
        verbose = args.get("verbose", True)
        
        experiments = {
            "catalan_bases": lambda: exp_catalan_bases(n_max),
            "primes_systems": lambda: exp_primes_systems(),
            "hybrid_sequences": lambda: exp_hybrid_sequences(n_max),
        }
        
        if experiment == "full_comparative":
            all_results = []
            for exp_name in experiments.keys():
                all_results.append(experiments[exp_name]())
            return {
                "experiment": "full_comparative",
                "results": all_results,
                "analysis": "Comparación 3 sistemas: Persa (base60, Metón19) vs Ternaria Rusa (base3-bal, TritOS) vs Cananeo (ciclos lunares, Fibonacci)",
                "n_checks": sum(r.get("n_checks", 0) for r in all_results),
                "validation_passed": all(r.get("validation_passed", False) for r in all_results),
                "verbose": verbose
            }
        elif experiment in experiments:
            result = experiments[experiment]()
            result["verbose"] = verbose
            return result
        else:
            raise ValueError(f"Experimento desconocido: {experiment}")
    
    except Exception as e:
        return {
            "experiment": "error",
            "error": str(e),
            "n_checks": 0,
            "validation_passed": False
        }
