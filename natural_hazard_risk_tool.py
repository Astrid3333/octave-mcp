"""
natural_hazard_risk_tool.py

Modelado de riesgo multifactorial para gestion publica de desastres naturales.

Modos:
  - risk_index: R = H*E*V*A (o variante geometrica ponderada) para un sitio,
                con clasificacion en bandas (bajo/medio/alto/muy alto)
  - risk_grid:  mismo calculo pero sobre arrays/grillas -> mapa de calor de riesgo
  - gumbel_return_period: T = (n+1)/m, periodo de retorno empirico (formula de
                Weibull/Gumbel de posicion de trazado) para una magnitud rankeada
  - gumbel_fit: ajusta una distribucion de Gumbel a una serie de magnitudes
                (metodo de momentos) y estima magnitud de diseno para un periodo
                de retorno dado, o el periodo de retorno de una magnitud dada

Convencion de riesgo:
  R = H * E * V / A   (A = capacidad de adaptacion, en el denominador: mayor
  capacidad de adaptacion reduce el riesgo neto). H, E, V, A normalizados en
  [0,1] cuando se usa la variante normalizada; A nunca puede ser 0 (se acota
  a un piso pequenio para evitar division por cero).
"""

import numpy as np


def _classify_risk(r, thresholds=(0.1, 0.3, 0.6)):
    """Clasifica un valor de riesgo normalizado en bandas."""
    low, med, high = thresholds
    if r < low:
        return "bajo"
    elif r < med:
        return "medio"
    elif r < high:
        return "alto"
    else:
        return "muy_alto"


def _risk_value(H, E, V, A, weighted=False, w=None):
    H = np.asarray(H, dtype=float)
    E = np.asarray(E, dtype=float)
    V = np.asarray(V, dtype=float)
    A = np.asarray(A, dtype=float)
    A = np.maximum(A, 1e-6)  # piso para evitar division por cero

    if not weighted:
        R = H * E * V / A
    else:
        if w is None:
            w = {"H": 1.0, "E": 1.0, "V": 1.0, "A": 1.0}
        R = (H ** w.get("H", 1.0)) * (E ** w.get("E", 1.0)) * (V ** w.get("V", 1.0)) \
            / (A ** w.get("A", 1.0))
    return R


def _mode_risk_index(p):
    H = p["H"]
    E = p["E"]
    V = p["V"]
    A = p.get("A", 1.0)
    weighted = p.get("weighted", False)
    w = p.get("weights")
    thresholds = tuple(p.get("thresholds", (0.1, 0.3, 0.6)))

    R = float(_risk_value(H, E, V, A, weighted=weighted, w=w))
    return {
        "H": H, "E": E, "V": V, "A": A,
        "risk_index": round(R, 6),
        "classification": _classify_risk(R, thresholds),
        "thresholds_used": list(thresholds),
    }


def _mode_risk_grid(p):
    H = np.asarray(p["H"], dtype=float)
    E = np.asarray(p["E"], dtype=float)
    V = np.asarray(p["V"], dtype=float)
    A = np.asarray(p.get("A", np.ones_like(H)), dtype=float)
    weighted = p.get("weighted", False)
    w = p.get("weights")
    thresholds = tuple(p.get("thresholds", (0.1, 0.3, 0.6)))

    if H.shape != E.shape or H.shape != V.shape or H.shape != A.shape:
        raise ValueError("H, E, V, A deben tener la misma forma para risk_grid")

    R = _risk_value(H, E, V, A, weighted=weighted, w=w)

    classify = np.vectorize(lambda x: _classify_risk(x, thresholds))
    classes = classify(R)

    counts = {}
    for band in ("bajo", "medio", "alto", "muy_alto"):
        counts[band] = int(np.sum(classes == band))

    return {
        "shape": list(R.shape),
        "risk_grid": np.round(R, 6).tolist(),
        "classification_grid": classes.tolist(),
        "band_counts": counts,
        "max_risk": round(float(np.max(R)), 6),
        "max_risk_location": [int(x) for x in np.unravel_index(np.argmax(R), R.shape)],
        "mean_risk": round(float(np.mean(R)), 6),
        "thresholds_used": list(thresholds),
    }


def _mode_gumbel_return_period(p):
    """
    Formula de posicion de trazado (plotting position), atribuida a Weibull
    y ampliamente usada en analisis de frecuencia hidrologica junto con Gumbel:
        T = (n + 1) / m
    donde n = numero total de eventos en el registro, m = rango del evento
    (1 = mayor magnitud, n = menor magnitud) tras ordenar de mayor a menor.
    """
    magnitudes = np.asarray(p["magnitudes"], dtype=float)
    n = len(magnitudes)
    order = np.argsort(-magnitudes)  # de mayor a menor
    ranked_mag = magnitudes[order]
    m = np.arange(1, n + 1)
    T = (n + 1) / m
    exceedance_prob = 1.0 / T

    return {
        "n_events": n,
        "ranked_magnitude_desc": np.round(ranked_mag, 6).tolist(),
        "rank_m": m.tolist(),
        "return_period_years": np.round(T, 4).tolist(),
        "annual_exceedance_probability": np.round(exceedance_prob, 6).tolist(),
    }


def _gumbel_params_moments(data):
    """Ajuste de Gumbel (max) por metodo de momentos."""
    data = np.asarray(data, dtype=float)
    mean = np.mean(data)
    std = np.std(data, ddof=1)
    euler_gamma = 0.5772156649015329
    # alpha = escala, u = ubicacion
    alpha = std * np.sqrt(6) / np.pi
    u = mean - euler_gamma * alpha
    return u, alpha


def _mode_gumbel_fit(p):
    data = np.asarray(p["data"], dtype=float)
    u, alpha = _gumbel_params_moments(data)

    result = {
        "n_obs": len(data),
        "location_u": round(float(u), 6),
        "scale_alpha": round(float(alpha), 6),
        "mean_input": round(float(np.mean(data)), 6),
        "std_input": round(float(np.std(data, ddof=1)), 6),
    }

    if "return_period" in p and p["return_period"] is not None:
        T = float(p["return_period"])
        # Magnitud de diseno para periodo de retorno T (CDF Gumbel invertida):
        # x_T = u - alpha * ln(-ln(1 - 1/T))
        yT = -np.log(-np.log(1.0 - 1.0 / T))
        xT = u + alpha * yT
        result["query_return_period_years"] = T
        result["design_magnitude"] = round(float(xT), 6)

    if "magnitude" in p and p["magnitude"] is not None:
        x = float(p["magnitude"])
        y = (x - u) / alpha
        F = np.exp(-np.exp(-y))  # P(X <= x)
        exceed_prob = 1.0 - F
        T_est = 1.0 / exceed_prob if exceed_prob > 0 else np.inf
        result["query_magnitude"] = x
        result["cdf_P_X_leq_x"] = round(float(F), 6)
        result["annual_exceedance_probability"] = round(float(exceed_prob), 6)
        result["estimated_return_period_years"] = round(float(T_est), 4) if np.isfinite(T_est) else None

    return result


def _validate():
    checks = []

    # --- Check 1: risk_index basico, R = H*E*V/A, con A=1 se reduce a H*E*V
    r = _mode_risk_index({"H": 0.8, "E": 0.6, "V": 0.5, "A": 1.0})
    expected = 0.8 * 0.6 * 0.5
    err = abs(r["risk_index"] - expected) / expected * 100
    checks.append({
        "name": "risk_index_basic",
        "computed": r["risk_index"], "expected": round(expected, 6),
        "error_pct": round(err, 6), "passed": err < 1e-6,
    })

    # --- Check 2: mayor capacidad de adaptacion (A) reduce el riesgo, monotonia
    r_lowA = _risk_value(0.8, 0.6, 0.5, 0.2)
    r_highA = _risk_value(0.8, 0.6, 0.5, 0.9)
    checks.append({
        "name": "adaptation_monotonicity",
        "r_low_adaptation": round(float(r_lowA), 6),
        "r_high_adaptation": round(float(r_highA), 6),
        "passed": bool(r_lowA > r_highA),
    })

    # --- Check 3: risk_grid consistente con risk_index elemento a elemento
    H = np.array([[0.9, 0.2], [0.5, 0.7]])
    E = np.array([[0.8, 0.3], [0.5, 0.6]])
    V = np.array([[0.7, 0.4], [0.5, 0.5]])
    A = np.array([[0.5, 0.5], [0.5, 0.5]])
    grid = _mode_risk_grid({"H": H, "E": E, "V": V, "A": A})
    manual = (H * E * V / A)
    max_abs_err = float(np.max(np.abs(np.array(grid["risk_grid"]) - manual)))
    checks.append({
        "name": "risk_grid_consistency",
        "max_abs_error": max_abs_err,
        "passed": max_abs_err < 1e-9,
    })

    # --- Check 4: Gumbel return period, caso de libro: n=1 evento -> T = (1+1)/1 = 2
    gr = _mode_gumbel_return_period({"magnitudes": [100.0]})
    checks.append({
        "name": "gumbel_return_period_n1",
        "computed_T": gr["return_period_years"][0], "expected_T": 2.0,
        "passed": abs(gr["return_period_years"][0] - 2.0) < 1e-9,
    })

    # --- Check 5: Gumbel return period, n=9 eventos, mayor magnitud (m=1) -> T=(9+1)/1=10
    mags9 = [50, 80, 30, 95, 60, 40, 20, 70, 55]
    gr9 = _mode_gumbel_return_period({"magnitudes": mags9})
    checks.append({
        "name": "gumbel_return_period_n9_m1",
        "computed_T": gr9["return_period_years"][0], "expected_T": 10.0,
        "passed": abs(gr9["return_period_years"][0] - 10.0) < 1e-9,
    })

    # --- Check 6: Gumbel fit, round-trip. Genero datos sinteticos EXACTOS de una
    # Gumbel con (u0, alpha0) conocidos via la inversa de la CDF sobre una malla
    # uniforme de probabilidades (sin ruido), ajusto por momentos, y verifico
    # que recupero u0, alpha0 dentro de tolerancia razonable, y que design
    # magnitude / return period son consistentes uno con el otro (round trip).
    rng = np.random.default_rng(42)
    u0, alpha0 = 20.0, 5.0
    probs = rng.uniform(0.001, 0.999, size=20000)
    synthetic = u0 - alpha0 * np.log(-np.log(probs))
    fit = _mode_gumbel_fit({"data": synthetic})
    err_u = abs(fit["location_u"] - u0) / u0 * 100
    err_alpha = abs(fit["scale_alpha"] - alpha0) / alpha0 * 100
    checks.append({
        "name": "gumbel_fit_moment_recovery",
        "u0": u0, "alpha0": alpha0,
        "fitted_u": fit["location_u"], "fitted_alpha": fit["scale_alpha"],
        "error_pct_u": round(err_u, 4), "error_pct_alpha": round(err_alpha, 4),
        "passed": err_u < 5.0 and err_alpha < 5.0,
    })

    # --- Check 7: round-trip design_magnitude <-> estimated_return_period_years
    fit_rt = _mode_gumbel_fit({"data": synthetic, "return_period": 100.0})
    xT = fit_rt["design_magnitude"]
    fit_back = _mode_gumbel_fit({"data": synthetic, "magnitude": xT})
    T_back = fit_back["estimated_return_period_years"]
    err_T = abs(T_back - 100.0) / 100.0 * 100
    checks.append({
        "name": "gumbel_fit_roundtrip_T_to_x_to_T",
        "T_query": 100.0, "x_design": xT, "T_recovered": T_back,
        "error_pct": round(err_T, 4), "passed": err_T < 1.0,
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_natural_hazard_risk(mode, params=None):
    params = params or {}

    if mode == "risk_index":
        return _mode_risk_index(params)
    elif mode == "risk_grid":
        return _mode_risk_grid(params)
    elif mode == "gumbel_return_period":
        return _mode_gumbel_return_period(params)
    elif mode == "gumbel_fit":
        return _mode_gumbel_fit(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"Modo desconocido: {mode}")


if __name__ == "__main__":
    import json
    print(json.dumps(compute_natural_hazard_risk("validate"), indent=2, ensure_ascii=False))

NATURAL_HAZARD_RISK_TOOL_SCHEMA = {   'type': 'object',
    'properties': {'mode': {'type': 'string', 'enum': ['risk_index', 'risk_grid', 'gumbel_return_period', 'gumbel_fit', 'validate'], 'default': 'validate'}, 'params': {'type': 'object'}},
    'required': ['mode']}

try:
    from tool_registry import register_tool
    register_tool(
        name="natural_hazard_risk_tool",
        schema={
        "name": "natural_hazard_risk_tool",
        "description": 'Modelado de riesgo multifactorial (R=H*E*V/A) para gestion publica de desastres naturales: risk_index (indice de riesgo puntual con clasificacion en bandas), risk_grid (mapa de calor de riesgo sobre grilla), gumbel_return_period (periodo de retorno empirico T=(n+1)/m), gumbel_fit (ajuste de distribucion de Gumbel por momentos y estimacion de magnitud de diseno o periodo de retorno).',
        "inputSchema": NATURAL_HAZARD_RISK_TOOL_SCHEMA,
    },
        handler=lambda args: compute_natural_hazard_risk(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass

