"""
universal_scale_tool.py

Herramienta general de matematica de escala: ajusta leyes de potencia
(y = a * x^b) a datos, interpreta el exponente segun el dominio conocido
(Zipf, Kleiber, Gutenberg-Richter, Pareto, etc.) y verifica invarianza
de escala.
"""

import math
import numpy as np
from scipy.optimize import curve_fit


KNOWN_EXPONENTS = {
    "zipf": -1.0,
    "kleiber": 0.75,
    "gutenberg_richter": -1.0,
    "pareto": -2.0,
}


def _power_law(x, a, b):
    return a * np.power(x, b)


def power_law_fit(params):
    x = np.array(params.get("x", []), dtype=float)
    y = np.array(params.get("y", []), dtype=float)
    domain = params.get("domain", "unknown")

    if len(x) < 3 or len(y) < 3:
        raise ValueError("Se requieren al menos 3 puntos (x, y) para el ajuste.")

    # Ajuste inicial razonable via log-log linear fit para dar buen p0 a curve_fit
    log_x = np.log(x)
    log_y = np.log(np.abs(y))
    b0, log_a0 = np.polyfit(log_x, log_y, 1)
    a0 = math.exp(log_a0)

    popt, _ = curve_fit(_power_law, x, y, p0=[a0, b0], maxfev=10000)
    a, b = popt

    residuals = y - _power_law(x, *popt)
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 1.0

    interpretation = _interpret_exponent(b, domain)

    return {
        "exponent": float(b),
        "coefficient": float(a),
        "r_squared": r_squared,
        "domain": domain,
        "interpretation": interpretation,
    }


def _interpret_exponent(exponent, domain):
    if domain in KNOWN_EXPONENTS:
        expected = KNOWN_EXPONENTS[domain]
        tol = 0.15 if domain != "pareto" else 0.3
        if abs(exponent - expected) < tol:
            return f"Exponente {exponent:.3f} consistente con {domain} (esperado {expected})"
        else:
            return f"Exponente {exponent:.3f}: no coincide con {domain} (esperado {expected})"
    return f"Exponente {exponent:.3f} en dominio '{domain}' (sin referencia conocida)"


def scale_invariance_test(params):
    """
    Verifica que, para una ley de potencia y = a * x^b, escalar x por un
    factor k produce un escalado multiplicativo de y por k^b (invarianza
    de forma bajo cambio de escala) — esto es la propiedad que distingue
    a las leyes de potencia de otras familias funcionales.
    """
    a = params.get("a", 2.0)
    b = params.get("b", 0.75)
    x = np.array(params.get("x", [1.0, 2.0, 5.0, 10.0]), dtype=float)
    k = params.get("scale_factor", 3.0)

    y_original = _power_law(x, a, b)
    y_scaled_input = _power_law(x * k, a, b)

    # y(k*x) / y(x) deberia ser constante e igual a k^b para TODOS los puntos
    ratios = y_scaled_input / y_original
    expected_ratio = k ** b

    max_error = float(np.max(np.abs(ratios - expected_ratio)))
    invariant = max_error < 1e-6

    return {
        "expected_ratio": expected_ratio,
        "observed_ratios": ratios.tolist(),
        "max_error": max_error,
        "is_scale_invariant": invariant,
    }


def universal_scale_tool(params: dict) -> dict:
    mode = params.get("mode", "power_law_fit")

    if mode == "power_law_fit":
        return power_law_fit(params)
    elif mode == "scale_invariance_test":
        return scale_invariance_test(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError("mode invalido. Opciones: power_law_fit, scale_invariance_test, validate")


def _validate():
    checks = []

    # 1) Zipf: tamanos de ciudad ~ rank^-1
    rank = np.arange(1, 11, dtype=float)
    city_sizes = 1_000_000.0 * rank ** (-1.0)
    r1 = power_law_fit({"x": rank.tolist(), "y": city_sizes.tolist(), "domain": "zipf"})
    checks.append({
        "name": "zipf_exponent_recovered",
        "passed": abs(r1["exponent"] - (-1.0)) < 0.05 and r1["r_squared"] > 0.99,
        "exponent": r1["exponent"],
        "r_squared": r1["r_squared"],
    })

    # 2) Kleiber: metabolismo ~ masa^0.75
    mass = np.array([1.0, 10.0, 100.0, 1000.0, 10000.0])
    metabolism = 70.0 * mass ** 0.75
    r2 = power_law_fit({"x": mass.tolist(), "y": metabolism.tolist(), "domain": "kleiber"})
    checks.append({
        "name": "kleiber_exponent_recovered",
        "passed": abs(r2["exponent"] - 0.75) < 0.02 and r2["r_squared"] > 0.99,
        "exponent": r2["exponent"],
        "r_squared": r2["r_squared"],
    })

    # 3) Gutenberg-Richter: N ~ M^-1 (aproximacion en escala potencia, no log-lineal en M)
    #    usamos la forma de ley de potencia directa para probar el mecanismo de ajuste
    x3 = np.array([1.0, 2.0, 4.0, 8.0, 16.0])
    y3 = 500.0 * x3 ** (-1.0)
    r3 = power_law_fit({"x": x3.tolist(), "y": y3.tolist(), "domain": "gutenberg_richter"})
    checks.append({
        "name": "gutenberg_richter_exponent_recovered",
        "passed": abs(r3["exponent"] - (-1.0)) < 0.05,
        "exponent": r3["exponent"],
    })

    # 4) Pareto: y ~ x^-2
    x4 = np.array([1.0, 2.0, 3.0, 5.0, 10.0])
    y4 = 100.0 * x4 ** (-2.0)
    r4 = power_law_fit({"x": x4.tolist(), "y": y4.tolist(), "domain": "pareto"})
    checks.append({
        "name": "pareto_exponent_recovered",
        "passed": abs(r4["exponent"] - (-2.0)) < 0.1,
        "exponent": r4["exponent"],
    })

    # 5) scale_invariance_test: debe confirmar invarianza para una ley de potencia exacta
    r5 = scale_invariance_test({"a": 2.0, "b": 0.75, "x": [1.0, 2.0, 5.0, 10.0], "scale_factor": 4.0})
    checks.append({
        "name": "scale_invariance_holds_for_power_law",
        "passed": r5["is_scale_invariant"],
        "max_error": r5["max_error"],
    })

    all_passed = all(c["passed"] for c in checks)
    return {
        "mode": "validate",
        "tool": "universal_scale_tool",
        "all_passed": all_passed,
        "checks": checks,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(universal_scale_tool({"mode": "validate"}), indent=2))
