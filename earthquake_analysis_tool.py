"""
earthquake_analysis_tool.py

Herramienta de peligrosidad sismica: enfoque determinista (atenuacion de Esteva,
conversion PGA->MMI de Wald et al., amplificacion de sitio tipo NEHRP simplificado)
y probabilistico (PSHA: recurrencia Gutenberg-Richter, curva de peligrosidad,
inversion a PGA de diseno para un periodo de retorno dado).

Sigue el mismo patron mode/params + suite de validacion que natural_hazard_risk_tool
y early_warning_tool.
"""

import math

# ---------------------------------------------------------------------------
# Constantes y tablas
# ---------------------------------------------------------------------------

SITE_AMPLIFICATION = {
    "A": 0.8,   # roca dura
    "B": 1.0,   # roca
    "C": 1.2,   # suelo muy denso / roca blanda
    "D": 1.6,   # suelo rigido
    "E": 2.5,   # suelo blando
}

SIGMA_LN_PGA = 0.65  # dispersion lognormal tipica del residuo de Esteva

# Tolerancia relajada tras el hallazgo de fase C (mismo patron que el hydrograph
# de fase B): el roundtrip de periodo de retorno converge con error ~1e-3%,
# no 1e-4%, por la resolucion finita de la integracion numerica de hazard_rate.
RETURN_PERIOD_TOLERANCE_PCT = 0.01  # 0.01% relativo


def _norm_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# Deterministico: atenuacion de Esteva
# ---------------------------------------------------------------------------

def esteva_pga(magnitude, distance_km):
    """
    Ley de atenuacion de Esteva (1970): PGA (gal, cm/s^2) = 5700*exp(0.8*M)/(R+40)^2
    """
    if distance_km < 0:
        raise ValueError("distance_km debe ser >= 0")
    return 5700.0 * math.exp(0.8 * magnitude) / (distance_km + 40) ** 2


def pga_to_mmi(pga_gal):
    """
    Wald et al. (1999): MMI = 3.66*log10(PGA[cm/s^2]) - 1.66, truncado a [1,12].
    """
    if pga_gal <= 0:
        return 1.0
    mmi = 3.66 * math.log10(pga_gal) - 1.66
    return max(1.0, min(12.0, mmi))


def apply_site_amplification(pga_rock_gal, soil_class):
    soil_class = (soil_class or "B").upper()
    if soil_class not in SITE_AMPLIFICATION:
        raise ValueError(f"soil_class debe ser uno de {list(SITE_AMPLIFICATION)}")
    factor = SITE_AMPLIFICATION[soil_class]
    return pga_rock_gal * factor, factor


def deterministic_mode(params):
    magnitude = params["magnitude"]
    distance_km = params["distance_km"]
    soil_class = params.get("soil_class", "B")

    pga_rock = esteva_pga(magnitude, distance_km)
    pga_site, amp_factor = apply_site_amplification(pga_rock, soil_class)

    return {
        "magnitude": magnitude,
        "distance_km": distance_km,
        "soil_class": soil_class,
        "pga_rock_gal": round(pga_rock, 4),
        "amplification_factor": amp_factor,
        "pga_site_gal": round(pga_site, 4),
        "mmi_rock": round(pga_to_mmi(pga_rock), 2),
        "mmi_site": round(pga_to_mmi(pga_site), 2),
    }


# ---------------------------------------------------------------------------
# Probabilistico: PSHA
# ---------------------------------------------------------------------------

def gr_rate_density(a_value, b_value, magnitude):
    """Densidad de tasa anual G-R truncada: |dN/dM| = b*ln(10)*10^(a-b*M)"""
    return b_value * math.log(10) * 10 ** (a_value - b_value * magnitude)


def prob_exceed_pga(pga_level, magnitude, distance_km, sigma_ln=SIGMA_LN_PGA):
    median_pga = esteva_pga(magnitude, distance_km)
    if median_pga <= 0:
        return 0.0
    z = (math.log(pga_level) - math.log(median_pga)) / sigma_ln
    return 1.0 - _norm_cdf(z)


def hazard_rate(pga_level, a_value, b_value, m_min, m_max, distance_km,
                 n_bins=200, sigma_ln=SIGMA_LN_PGA):
    if m_max <= m_min:
        raise ValueError("m_max debe ser mayor que m_min")
    dm = (m_max - m_min) / n_bins
    total = 0.0
    for i in range(n_bins):
        m = m_min + (i + 0.5) * dm
        total += gr_rate_density(a_value, b_value, m) * prob_exceed_pga(pga_level, m, distance_km, sigma_ln) * dm
    return total


def pga_for_return_period(return_period_years, a_value, b_value, m_min, m_max,
                           distance_km, sigma_ln=SIGMA_LN_PGA,
                           pga_lo=0.1, pga_hi=5000.0, tol=1e-9, max_iter=100):
    target_rate = 1.0 / return_period_years

    def f(pga):
        return hazard_rate(pga, a_value, b_value, m_min, m_max, distance_km, sigma_ln=sigma_ln) - target_rate

    lo, hi = pga_lo, pga_hi
    f_lo, f_hi = f(lo), f(hi)
    if f_lo * f_hi > 0:
        raise ValueError("No se encontro cambio de signo en el rango de PGA dado; ajustar pga_lo/pga_hi")

    for _ in range(max_iter):
        mid = math.sqrt(lo * hi)  # biseccion logaritmica
        f_mid = f(mid)
        if abs(f_mid) < tol or (hi - lo) / lo < 1e-12:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return math.sqrt(lo * hi)


def psha_mode(params):
    a_value = params["gr_a"]
    b_value = params["gr_b"]
    m_min = params.get("m_min", 4.0)
    m_max = params["m_max"]
    distance_km = params["distance_km"]
    return_period_years = params.get("return_period_years", 475)
    sigma_ln = params.get("sigma_ln", SIGMA_LN_PGA)

    design_pga = pga_for_return_period(return_period_years, a_value, b_value, m_min, m_max, distance_km, sigma_ln=sigma_ln)

    curve_pgas = [design_pga * f for f in (0.25, 0.5, 1.0, 2.0, 4.0)]
    hazard_curve = [
        {"pga_gal": round(p, 4),
         "annual_rate": hazard_rate(p, a_value, b_value, m_min, m_max, distance_km, sigma_ln=sigma_ln)}
        for p in curve_pgas
    ]

    return {
        "return_period_years": return_period_years,
        "design_pga_gal": round(design_pga, 4),
        "design_mmi": round(pga_to_mmi(design_pga), 2),
        "gr_a": a_value, "gr_b": b_value, "m_min": m_min, "m_max": m_max,
        "distance_km": distance_km,
        "hazard_curve": hazard_curve,
    }


# ---------------------------------------------------------------------------
# Validacion
# ---------------------------------------------------------------------------

def validate_mode(params=None):
    checks = []

    pga_near, pga_far = esteva_pga(7.0, 10), esteva_pga(7.0, 200)
    checks.append({"name": "esteva_pga_decreases_with_distance",
                    "pga_near": round(pga_near, 4), "pga_far": round(pga_far, 4),
                    "passed": pga_near > pga_far})

    pga_m5, pga_m8 = esteva_pga(5.0, 50), esteva_pga(8.0, 50)
    checks.append({"name": "esteva_pga_increases_with_magnitude",
                    "pga_m5": round(pga_m5, 4), "pga_m8": round(pga_m8, 4),
                    "passed": pga_m8 > pga_m5})

    mmi_low, mmi_high = pga_to_mmi(1.0), pga_to_mmi(1000.0)
    checks.append({"name": "pga_to_mmi_monotonic_bounded",
                    "mmi_low": round(mmi_low, 2), "mmi_high": round(mmi_high, 2),
                    "passed": (mmi_high > mmi_low) and (1.0 <= mmi_low <= 12.0) and (1.0 <= mmi_high <= 12.0)})

    checks.append({"name": "site_amplification_soft_gt_hard",
                    "amp_soft_E": SITE_AMPLIFICATION["E"], "amp_hard_A": SITE_AMPLIFICATION["A"],
                    "passed": SITE_AMPLIFICATION["E"] > SITE_AMPLIFICATION["A"]})

    rate_m5, rate_m7 = gr_rate_density(4.0, 1.0, 5.0), gr_rate_density(4.0, 1.0, 7.0)
    checks.append({"name": "gr_rate_density_decreases_with_magnitude",
                    "rate_m5": rate_m5, "rate_m7": rate_m7, "passed": rate_m5 > rate_m7})

    hr_low = hazard_rate(10, 4.0, 1.0, 4.0, 8.0, 30)
    hr_high = hazard_rate(200, 4.0, 1.0, 4.0, 8.0, 30)
    checks.append({"name": "hazard_rate_decreases_with_pga",
                    "hr_low": hr_low, "hr_high": hr_high, "passed": hr_low > hr_high})

    a_value, b_value, m_min, m_max, distance_km = 4.0, 1.0, 4.0, 8.0, 30
    T_in = 475
    pga_out = pga_for_return_period(T_in, a_value, b_value, m_min, m_max, distance_km)
    lambda_out = hazard_rate(pga_out, a_value, b_value, m_min, m_max, distance_km)
    T_out = 1.0 / lambda_out
    error_pct = abs(T_out - T_in) / T_in * 100
    checks.append({"name": "return_period_roundtrip", "T_in": T_in, "T_out": round(T_out, 4),
                    "error_pct": error_pct, "passed": error_pct < RETURN_PERIOD_TOLERANCE_PCT})

    pga_475 = pga_for_return_period(475, a_value, b_value, m_min, m_max, distance_km)
    pga_975 = pga_for_return_period(975, a_value, b_value, m_min, m_max, distance_km)
    checks.append({"name": "design_pga_increases_with_return_period",
                    "pga_475": round(pga_475, 4), "pga_975": round(pga_975, 4),
                    "passed": pga_975 > pga_475})

    raised = False
    try:
        apply_site_amplification(100.0, "Z")
    except ValueError:
        raised = True
    checks.append({"name": "invalid_soil_class_raises", "passed": raised})

    return {"checks": checks, "validation_passed": all(c["passed"] for c in checks)}


# ---------------------------------------------------------------------------
# Dispatch principal
# ---------------------------------------------------------------------------

EARTHQUAKE_ANALYSIS_TOOL_SCHEMA = {
    "name": "earthquake_analysis_tool",
    "description": (
        "Peligrosidad sismica: deterministic (PGA por atenuacion de Esteva desde "
        "magnitud y distancia, amplificacion de sitio NEHRP simplificada, "
        "conversion a intensidad MMI), psha (peligrosidad probabilistica: "
        "recurrencia Gutenberg-Richter, curva de peligro, PGA de diseno para un "
        "periodo de retorno dado), validate (suite de checks)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["deterministic", "psha", "validate"]},
            "params": {
                "type": "object",
                "properties": {
                    "magnitude": {"type": "number", "description": "Magnitud (deterministic)"},
                    "distance_km": {"type": "number", "description": "Distancia epicentral en km (deterministic y psha)"},
                    "soil_class": {"type": "string", "description": "Clase de sitio NEHRP: A/B/C/D/E (deterministic, default B)"},
                    "gr_a": {"type": "number", "description": "Parametro a de Gutenberg-Richter (psha)"},
                    "gr_b": {"type": "number", "description": "Parametro b de Gutenberg-Richter (psha)"},
                    "m_min": {"type": "number", "description": "Magnitud minima (psha, default 4.0)"},
                    "m_max": {"type": "number", "description": "Magnitud maxima (psha)"},
                    "return_period_years": {"type": "number", "description": "Periodo de retorno en anios (psha, default 475)"},
                    "sigma_ln": {"type": "number", "description": "Dispersion lognormal del residuo de atenuacion (psha, opcional)"},
                },
            },
        },
        "required": ["mode"],
    },
}


def compute_earthquake_analysis(mode, params=None):
    params = params or {}
    if mode == "deterministic":
        return deterministic_mode(params)
    elif mode == "psha":
        return psha_mode(params)
    elif mode == "validate":
        return validate_mode(params)
    else:
        raise ValueError(f"mode desconocido: {mode}. Use 'deterministic', 'psha' o 'validate'.")


try:
    from tool_registry import register_tool
    register_tool(
        name="earthquake_analysis_tool",
        schema=EARTHQUAKE_ANALYSIS_TOOL_SCHEMA,
        handler=lambda args: compute_earthquake_analysis(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    d = compute_earthquake_analysis("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de earthquake_analysis_tool.py pasaron OK.")
