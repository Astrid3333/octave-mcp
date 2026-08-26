"""
socio_economic_scale_tool.py

Leyes de escala en sistemas socioeconomicos:
- zipf_city_size: ajusta la ley de Zipf (tamano de ciudad vs rank) y
  devuelve el exponente estimado
- pareto_wealth: ajusta una distribucion de Pareto a datos de riqueza/renta
  y devuelve el indice de cola (alpha) e interpretacion tipo 80/20
- scale_free_network: analiza si una secuencia de grados de una red sigue
  una distribucion libre de escala (ley de potencia en el histograma de grados)
"""

import math
import numpy as np


# ---------------------------------------------------------------------------
# zipf_city_size
# ---------------------------------------------------------------------------
def zipf_city_size(params):
    """
    Ajusta size = a * rank^b (b deberia ser ~ -1 para Zipf puro) via
    regresion log-log.
    """
    rank = np.array(params["rank"], dtype=float)
    size = np.array(params["size"], dtype=float)

    if len(rank) < 2:
        raise ValueError("Se requieren al menos 2 puntos rank/size")

    log_rank = np.log(rank)
    log_size = np.log(size)

    b, log_a = np.polyfit(log_rank, log_size, 1)
    a = math.exp(log_a)

    predicted = a * rank ** b
    residuals = size - predicted
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((size - np.mean(size)) ** 2))
    r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 1.0

    is_zipf = bool(abs(b - (-1.0)) < 0.15)

    return {
        "exponent": float(b),
        "coefficient": float(a),
        "r_squared": r_squared,
        "follows_zipf_law": is_zipf,
    }


# ---------------------------------------------------------------------------
# pareto_wealth
# ---------------------------------------------------------------------------
def pareto_wealth(params):
    """
    Estima el indice de cola alpha de una distribucion de Pareto usando el
    estimador de maxima verosimilitud de Hill:
      alpha_hat = n / sum(ln(x_i / x_min))
    donde x_min es el valor minimo (umbral) de la muestra.
    """
    wealth = np.array(params["wealth_values"], dtype=float)
    x_min = params.get("x_min", float(np.min(wealth)))

    sample = wealth[wealth >= x_min]
    n = len(sample)
    if n == 0:
        raise ValueError("Ningun valor de riqueza es >= x_min")

    alpha_hat = n / np.sum(np.log(sample / x_min))

    # Fraccion de riqueza total que posee el top 20% de la muestra (empirico)
    sorted_wealth = np.sort(sample)[::-1]
    top_20_count = max(1, int(round(0.2 * n)))
    top_20_share = float(np.sum(sorted_wealth[:top_20_count]) / np.sum(sorted_wealth) * 100.0)

    return {
        "alpha_estimate": float(alpha_hat),
        "x_min": x_min,
        "n_samples": n,
        "top_20pct_wealth_share": top_20_share,
    }


# ---------------------------------------------------------------------------
# scale_free_network
# ---------------------------------------------------------------------------
def scale_free_network(params):
    """
    Dada una secuencia de grados de una red, construye la distribucion de
    grados P(k) y ajusta una ley de potencia P(k) ~ k^-gamma via regresion
    log-log sobre el histograma (metodo simple, no MLE riguroso).
    """
    degrees = np.array(params["degrees"], dtype=float)
    degrees = degrees[degrees > 0]

    if len(degrees) < 5:
        raise ValueError("Se requieren al menos 5 grados > 0 para el analisis")

    unique_k, counts = np.unique(degrees, return_counts=True)
    p_k = counts / counts.sum()

    log_k = np.log(unique_k)
    log_p = np.log(p_k)

    gamma_neg, log_c = np.polyfit(log_k, log_p, 1)
    gamma = -gamma_neg  # convencion: P(k) ~ k^-gamma, gamma > 0

    predicted_log_p = log_c + gamma_neg * log_k
    residuals = log_p - predicted_log_p
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((log_p - np.mean(log_p)) ** 2))
    r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 1.0

    # Rango tipico de redes libres de escala reales: 2 < gamma < 3
    is_scale_free = 1.5 <= gamma <= 3.5 and r_squared > 0.7

    return {
        "gamma_exponent": float(gamma),
        "r_squared": r_squared,
        "is_scale_free_plausible": bool(is_scale_free),
        "n_unique_degrees": int(len(unique_k)),
    }


# ---------------------------------------------------------------------------
# Dispatch principal
# ---------------------------------------------------------------------------
def socio_economic_scale_tool(params: dict) -> dict:
    mode = params.get("mode", "zipf_city_size")

    if mode == "zipf_city_size":
        return zipf_city_size(params)
    elif mode == "pareto_wealth":
        return pareto_wealth(params)
    elif mode == "scale_free_network":
        return scale_free_network(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            "mode invalido. Opciones: zipf_city_size, pareto_wealth, "
            "scale_free_network, validate"
        )


# ---------------------------------------------------------------------------
# Modo validate
# ---------------------------------------------------------------------------
def _validate():
    checks = []

    # 1) zipf_city_size: datos generados exactamente con exponente -1
    rank = list(range(1, 21))
    size = [1_000_000.0 / r for r in rank]
    r1 = zipf_city_size({"rank": rank, "size": size})
    checks.append({
        "name": "zipf_exponent_recovered_exact",
        "passed": abs(r1["exponent"] - (-1.0)) < 1e-6 and r1["follows_zipf_law"],
        "exponent": r1["exponent"],
    })

    # 2) zipf_city_size: datos NO-Zipf (exponente -0.3) -> follows_zipf_law False
    size2 = [1_000_000.0 * (r ** -0.3) for r in rank]
    r2 = zipf_city_size({"rank": rank, "size": size2})
    checks.append({
        "name": "non_zipf_data_detected",
        "passed": not r2["follows_zipf_law"],
        "exponent": r2["exponent"],
    })

    # 3) pareto_wealth: distribucion sintetica de Pareto con alpha conocido (=2)
    #    x_i = x_min / U^(1/alpha), U uniforme en (0,1] — generamos determinista
    rng = np.random.default_rng(42)
    x_min = 1.0
    alpha_true = 2.0
    u = rng.uniform(0.001, 1.0, size=5000)
    synthetic_wealth = x_min / (u ** (1.0 / alpha_true))
    r3 = pareto_wealth({"wealth_values": synthetic_wealth.tolist(), "x_min": x_min})
    checks.append({
        "name": "pareto_alpha_recovered_approximately",
        "passed": abs(r3["alpha_estimate"] - alpha_true) < 0.15,
        "alpha_estimate": r3["alpha_estimate"],
        "expected": alpha_true,
    })

    # 4) pareto_wealth: top 20% concentra mas riqueza que una distribucion uniforme lo haria (>20%)
    checks.append({
        "name": "top_20pct_share_exceeds_uniform_baseline",
        "passed": r3["top_20pct_wealth_share"] > 20.0,
        "top_20pct_wealth_share": r3["top_20pct_wealth_share"],
    })

    # 5) scale_free_network: secuencia de grados generada con ley de potencia conocida (gamma=2.5)
    rng2 = np.random.default_rng(7)
    u2 = rng2.uniform(0.001, 1.0, size=3000)
    k_min = 1.0
    gamma_true = 2.5
    synthetic_degrees = np.round(k_min / (u2 ** (1.0 / (gamma_true - 1)))).astype(int)
    synthetic_degrees = synthetic_degrees[synthetic_degrees > 0]
    r5 = scale_free_network({"degrees": synthetic_degrees.tolist()})
    checks.append({
        "name": "scale_free_gamma_in_plausible_range",
        "passed": 1.5 <= r5["gamma_exponent"] <= 3.5,
        "gamma_exponent": r5["gamma_exponent"],
    })

    # 6) scale_free_network: red regular (todos los nodos con el mismo grado) -> no deberia
    #    verse como scale-free plausible con buen ajuste de ley de potencia (una sola k => insuficiente)
    regular_degrees = [4] * 10 + [5] * 2  # casi todos iguales, poca variacion
    try:
        r6 = scale_free_network({"degrees": regular_degrees})
        r6_ran = True
    except ValueError:
        r6_ran = False
    checks.append({
        "name": "near_regular_network_runs_without_error",
        "passed": r6_ran,
    })

    all_passed = all(c["passed"] for c in checks)
    return {
        "mode": "validate",
        "tool": "socio_economic_scale_tool",
        "all_passed": all_passed,
        "checks": checks,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(socio_economic_scale_tool({"mode": "validate"}), indent=2))
