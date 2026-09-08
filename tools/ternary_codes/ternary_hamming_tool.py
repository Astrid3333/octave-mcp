#!/usr/bin/env python3
"""ternary_hamming_tool: Código Hamming sobre GF(3) (ternario balanceado-compatible)
para corrección de errores de un trit, con comparación de eficiencia energética
(Landauer) frente al Hamming binario clásico. Pensado para sustratos de bajo
consumo donde el trit es el símbolo nativo (p.ej. computación caótica/TritOS).
"""
import itertools
import math
from typing import Dict, List, Any

TOOL_SCHEMA = {
    "name": "ternary_hamming_tool",
    "description": "Código Hamming ternario (GF(3)) de corrección de 1 error de trit, con análisis de tasa y eficiencia energética (Landauer) vs. Hamming binario",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["encode", "decode", "correct_error", "energy_comparison", "validate"],
                "description": "Operación a ejecutar"
            },
            "r": {
                "type": "integer",
                "minimum": 2,
                "maximum": 5,
                "default": 3,
                "description": "Número de trits de paridad. n=(3^r-1)/2, k=n-r"
            },
            "data": {
                "type": "array",
                "items": {"type": "integer", "minimum": 0, "maximum": 2},
                "description": "Trits de datos a codificar (longitud k, requerido en mode=encode)"
            },
            "codeword": {
                "type": "array",
                "items": {"type": "integer", "minimum": 0, "maximum": 2},
                "description": "Palabra código recibida (longitud n, requerido en mode=decode/correct_error)"
            }
        },
        "required": ["mode"]
    }
}


def _gf3_representatives(r: int) -> List[tuple]:
    """Todos los vectores no nulos de GF(3)^r, hasta escalar (representante
    normalizado con primera componente no nula = 1). Estos son las columnas
    de la matriz de paridad H del código Hamming ternario."""
    if r < 2 or r > 5:
        raise ValueError("r debe estar entre 2 y 5")
    seen = []
    inv = {1: 1, 2: 2}  # inverso multiplicativo mod 3
    for v in itertools.product([0, 1, 2], repeat=r):
        if all(x == 0 for x in v):
            continue
        first_nonzero = next(x for x in v if x != 0)
        norm = tuple((x * inv[first_nonzero]) % 3 for x in v)
        if norm not in seen:
            seen.append(norm)
    return seen


def _build_H(r: int):
    cols = _gf3_representatives(r)
    H = [[cols[j][i] for j in range(len(cols))] for i in range(r)]
    parity_positions = []
    for i in range(r):
        e = tuple(1 if j == i else 0 for j in range(r))
        parity_positions.append(cols.index(e))
    return H, cols, parity_positions


def _syndrome(c: List[int], H: List[List[int]], r: int, n: int) -> tuple:
    return tuple(sum(H[i][j] * c[j] for j in range(n)) % 3 for i in range(r))


def _encode(data: List[int], r: int) -> Dict[str, Any]:
    H, cols, parity_positions = _build_H(r)
    n = len(cols)
    k = n - r
    if len(data) != k:
        raise ValueError(f"data debe tener longitud k={k} para r={r} (recibido {len(data)})")
    if any(d < 0 or d > 2 for d in data):
        raise ValueError("data debe contener solo trits 0, 1, 2")
    data_positions = [i for i in range(n) if i not in parity_positions]
    c = [0] * n
    for idx, d in zip(data_positions, data):
        c[idx] = d
    for row in range(r):
        s = sum(H[row][j] * c[j] for j in range(n) if j not in parity_positions) % 3
        c[parity_positions[row]] = (-s) % 3
    return {"codeword": c, "n": n, "k": k, "r": r}


def _decode(codeword: List[int], r: int) -> Dict[str, Any]:
    H, cols, _ = _build_H(r)
    n = len(cols)
    if len(codeword) != n:
        raise ValueError(f"codeword debe tener longitud n={n} para r={r} (recibido {len(codeword)})")
    if any(x < 0 or x > 2 for x in codeword):
        raise ValueError("codeword debe contener solo trits 0, 1, 2")
    s = _syndrome(codeword, H, r, n)
    if all(x == 0 for x in s):
        return {"corrected": codeword, "error_detected": False, "error_position": None}
    for j, col in enumerate(cols):
        for scalar in (1, 2):
            if all((scalar * col[i]) % 3 == s[i] for i in range(r)):
                corrected = codeword.copy()
                corrected[j] = (corrected[j] - scalar) % 3
                return {
                    "corrected": corrected,
                    "error_detected": True,
                    "error_position": j,
                    "error_magnitude": scalar
                }
    return {"corrected": codeword, "error_detected": True, "error_position": None,
            "note": "sindrome no corresponde a error de 1 trit (2+ errores)"}


def _energy_comparison(r: int) -> Dict[str, Any]:
    _, cols, _ = _gf3_representatives(r), None, None
    cols = _gf3_representatives(r)
    n = len(cols)
    k = n - r
    k_B = 1.380649e-23
    T = 300.0
    E_min_trit = k_B * T * math.log(3)
    E_min_bit = k_B * T * math.log(2)
    info_bits_ternary = k * math.log2(3)
    E_total_ternary = n * E_min_trit

    # Hamming binario clasico de tasa comparable: n_bin = 2^m - 1, k_bin = n_bin - m
    m = 4
    n_bin = 2 ** m - 1
    k_bin = n_bin - m
    E_total_binary = n_bin * E_min_bit

    return {
        "r": r,
        "ternary_code": {"n": n, "k": k, "rate": k / n,
                          "info_bits": info_bits_ternary,
                          "E_min_total_J": E_total_ternary,
                          "E_min_per_useful_bit_J": E_total_ternary / info_bits_ternary},
        "binary_hamming_reference": {"n": n_bin, "k": k_bin, "rate": k_bin / n_bin,
                                      "info_bits": float(k_bin),
                                      "E_min_total_J": E_total_binary,
                                      "E_min_per_useful_bit_J": E_total_binary / k_bin},
        "ternary_energy_advantage_pct":
            (1 - (E_total_ternary / info_bits_ternary) / (E_total_binary / k_bin)) * 100
    }


def _validate() -> Dict[str, Any]:
    checks = []

    # Check 1-2: construccion de H para r=2 y r=3 tiene dimensiones correctas
    for r in (2, 3):
        H, cols, pp = _build_H(r)
        n = len(cols)
        checks.append((f"r={r}: n=(3^{r}-1)/2={ (3**r-1)//2 }", n == (3**r - 1) // 2))
        checks.append((f"r={r}: {len(pp)} posiciones de paridad unicas", len(set(pp)) == r))

    # Check 3: codeword generado tiene sindrome cero
    r = 3
    enc = _encode([1, 2, 0, 1, 1, 2, 0, 2, 1, 0], r)
    H, cols, _ = _build_H(r)
    s = _syndrome(enc["codeword"], H, r, enc["n"])
    checks.append(("codeword valido tiene sindrome cero", all(x == 0 for x in s)))

    # Check 4: deteccion y correccion de 1 error en cada posicion
    import random
    random.seed(7)
    all_ok = True
    for _ in range(50):
        data = [random.randint(0, 2) for _ in range(enc["k"])]
        c = _encode(data, r)["codeword"]
        pos = random.randrange(len(c))
        err = random.choice([1, 2])
        corrupted = c.copy()
        corrupted[pos] = (corrupted[pos] + err) % 3
        dec = _decode(corrupted, r)
        if dec["corrected"] != c:
            all_ok = False
            break
    checks.append(("correccion de 1 error de trit en 50 pruebas aleatorias", all_ok))

    # Check 5: sin error, decode no modifica
    dec_clean = _decode(enc["codeword"], r)
    checks.append(("codeword sin error: error_detected=False", dec_clean["error_detected"] is False))

    # Check 6: energy_comparison retorna ternario mas eficiente que binario para r=3
    ec = _energy_comparison(3)
    checks.append(("codigo ternario mas eficiente en energia/bit util que Hamming binario",
                    ec["ternary_energy_advantage_pct"] > 0))

    passed = sum(1 for _, ok in checks if ok)
    return {
        "checks": [{"name": name, "passed": ok} for name, ok in checks],
        "passed": passed,
        "total": len(checks),
        "all_passed": passed == len(checks)
    }


def ternary_hamming_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    mode = args.get("mode")
    r = args.get("r", 3)

    if mode == "encode":
        data = args.get("data")
        if data is None:
            raise ValueError("mode=encode requiere 'data'")
        return _encode(data, r)

    elif mode == "decode" or mode == "correct_error":
        codeword = args.get("codeword")
        if codeword is None:
            raise ValueError(f"mode={mode} requiere 'codeword'")
        return _decode(codeword, r)

    elif mode == "energy_comparison":
        return _energy_comparison(r)

    elif mode == "validate":
        return _validate()

    else:
        raise ValueError(f"mode desconocido: {mode}")


if __name__ == "__main__":
    result = _validate()
    print(f"Validacion: {result['passed']}/{result['total']} checks pasados")
    for c in result["checks"]:
        status = "OK" if c["passed"] else "FALLO"
        print(f"  [{status}] {c['name']}")
