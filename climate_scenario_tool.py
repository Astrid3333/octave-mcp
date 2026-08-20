"""
climate_scenario_tool.py
=========================
Herramienta MCP para analisis de escenarios climaticos, parte de la fase C
(matematica para administracion publica + fenomenos naturales) de octave-mcp.

Dos componentes independientes, segun lo pedido:

1) MOTOR GENERICO de deteccion de tendencias en series temporales climaticas
   (temperatura, precipitacion, nivel del mar, etc.) - no depende de ninguna
   tabla RCP especifica. Confianza ALTA: son metodos estadisticos estandar
   (regresion lineal por minimos cuadrados, test de Mann-Kendall, deteccion
   de punto de cambio por CUSUM), no valores tabulados que puedan estar mal
   recordados.

2) CATALOGO RCP (Representative Concentration Pathways) opcional, con datos
   REALES tomados de fuentes primarias/IPCC AR5 verificadas por busqueda web
   en esta sesion (no generados por patron):
   - Forzamiento radiativo 2100 (W/m2): valor definitorio de cada RCP, de
     Van Vuuren et al. 2011 "The representative concentration pathways: an
     overview", Climatic Change.
   - CO2 en 2100: RCP4.5 harmonizado = 538 ppmv (Thomson et al. 2011,
     "RCP4.5: A Pathway for Stabilization of Radiative Forcing by 2100").
     RCP2.6, RCP6.0, RCP8.5 solo tienen aca el equivalente CO2-eq total
     (490/850/1370 ppm CO2-eq) citado en DKRZ/IPCC, marcado explicitamente
     como CO2-eq y no como CO2 puro, porque ese es el dato que pude
     verificar con fuente primaria en esta sesion.
   - Proyecciones de temperatura y nivel del mar: IPCC AR5 (2013), tabla de
     sintesis con medias y rangos "likely" para 2046-2065 y 2081-2100,
     relativo a 1986-2005 (fuente: AR5 Synthesis Report / resumenes
     replicados en multiples paginas academicas, valores consistentes entre
     si en la busqueda).

CONFIANZA POR CAMPO (marcada explicitamente en cada respuesta que usa el
catalogo RCP, via "data_confidence"):
   - forcing_2100_w_m2: ALTA (valor definitorio de cada RCP, es su nombre)
   - co2_2100: MEDIA-ALTA para RCP4.5 (numero puntual con fuente primaria
     verificada), MEDIA para el resto (son CO2-eq de resumenes, no series
     completas de la publicacion original de Meinshausen et al. 2011, que
     no pude descargar completa en esta sesion)
   - temp_anomaly_C, sea_level_rise_m: ALTA (tabla de sintesis AR5, valores
     verificados y consistentes entre multiples fuentes en la busqueda)
   - trayectoria interpolada entre anclas temporales: MEDIA (interpolacion
     propia, forma funcional razonable pero NO es la serie real ano-a-ano
     de los modelos CMIP5, que tiene variabilidad y no es una curva suave)

Si en una sesion futura se descarga la serie completa de Meinshausen et al.
2011 (los archivos .dat originales de forzamiento por gas y por ano), este
catalogo deberia reemplazarse igual que se hizo con scott_burgan40 en
wildfire_risk_tool.py.
"""

from __future__ import annotations
import math

# ------------------------------------------------------------------
# Catalogo RCP - datos reales, ver docstring para fuentes y confianza
# ------------------------------------------------------------------

RCP_CATALOG = {
    "RCP2.6": {
        "forcing_2100_w_m2": 2.6,
        "forcing_peak_w_m2": 3.0,
        "forcing_peak_year_approx": 2050,
        "co2_2100": {"value_ppm": 490, "is_co2_eq": True, "confidence": "media"},
        "temp_anomaly_C": {
            "2046_2065": {"mean": 1.0, "low": 0.4, "high": 1.6},
            "2081_2100": {"mean": 1.0, "low": 0.3, "high": 1.7},
        },
        "sea_level_rise_m": {
            "2046_2065": {"mean": 0.24, "low": 0.17, "high": 0.32},
            "2081_2100": {"mean": 0.40, "low": 0.26, "high": 0.55},
        },
        "narrative": "Mitigacion fuerte; emisiones globales caen sustancialmente desde 2010-2020.",
    },
    "RCP4.5": {
        "forcing_2100_w_m2": 4.5,
        "forcing_peak_w_m2": 4.5,
        "forcing_peak_year_approx": 2100,
        "co2_2100": {"value_ppm": 538, "is_co2_eq": False, "confidence": "media-alta"},
        "temp_anomaly_C": {
            "2046_2065": {"mean": 1.4, "low": 0.9, "high": 2.0},
            "2081_2100": {"mean": 1.8, "low": 1.1, "high": 2.6},
        },
        "sea_level_rise_m": {
            "2046_2065": {"mean": 0.26, "low": 0.19, "high": 0.33},
            "2081_2100": {"mean": 0.47, "low": 0.32, "high": 0.63},
        },
        "narrative": "Estabilizacion del forzamiento; emisiones alcanzan pico cerca de 2040.",
    },
    "RCP6.0": {
        "forcing_2100_w_m2": 6.0,
        "forcing_peak_w_m2": 6.0,
        "forcing_peak_year_approx": 2100,
        "co2_2100": {"value_ppm": 850, "is_co2_eq": True, "confidence": "media"},
        "temp_anomaly_C": {
            "2046_2065": {"mean": 1.3, "low": 0.8, "high": 1.8},
            "2081_2100": {"mean": 2.2, "low": 1.4, "high": 3.1},
        },
        "sea_level_rise_m": {
            "2046_2065": {"mean": 0.25, "low": 0.18, "high": 0.32},
            "2081_2100": {"mean": 0.48, "low": 0.33, "high": 0.63},
        },
        "narrative": "Estabilizacion tardia; emisiones alcanzan pico cerca de 2080.",
    },
    "RCP8.5": {
        "forcing_2100_w_m2": 8.5,
        "forcing_peak_w_m2": 8.5,
        "forcing_peak_year_approx": 2100,
        "co2_2100": {"value_ppm": 1370, "is_co2_eq": True, "confidence": "media"},
        "temp_anomaly_C": {
            "2046_2065": {"mean": 2.0, "low": 1.4, "high": 2.6},
            "2081_2100": {"mean": 3.7, "low": 2.6, "high": 4.8},
        },
        "sea_level_rise_m": {
            "2046_2065": {"mean": 0.30, "low": 0.22, "high": 0.38},
            "2081_2100": {"mean": 0.63, "low": 0.45, "high": 0.82},
        },
        "narrative": "Sin mitigacion adicional; emisiones siguen creciendo durante todo el siglo XXI.",
    },
}

RCP_CATALOG_CONFIDENCE = {
    "overall": "media-alta",
    "note": (
        "Forzamiento radiativo 2100 y proyecciones de temperatura/nivel del mar: "
        "ALTA (IPCC AR5, valores definitorios y tabla de sintesis, verificados por "
        "busqueda web en esta sesion contra multiples fuentes consistentes entre si). "
        "CO2 en 2100: MEDIA-ALTA para RCP4.5 (numero puntual con fuente primaria "
        "verificada, Thomson et al. 2011), MEDIA para RCP2.6/6.0/8.5 (son CO2-eq de "
        "resumenes secundarios, no la serie completa de Meinshausen et al. 2011). "
        "Trayectorias interpoladas entre anclas temporales: MEDIA (forma funcional "
        "propia razonable, no la serie real ano-a-ano de los modelos CMIP5)."
    ),
}

_ANCHOR_YEARS = {"2046_2065": 2055.5, "2081_2100": 2090.5}
_BASELINE_YEAR = 1995.5  # centro de 1986-2005, referencia de anomalia AR5


def _interp_anchor_field(field_dict, year):
    """Interpola linealmente entre las dos anclas AR5 (y extrapola linealmente
    fuera de rango, con warning). field_dict tiene claves '2046_2065' y
    '2081_2100', cada una con mean/low/high."""
    y1, y2 = _ANCHOR_YEARS["2046_2065"], _ANCHOR_YEARS["2081_2100"]
    v1, v2 = field_dict["2046_2065"], field_dict["2081_2100"]
    extrapolated = not (y1 <= year <= y2)
    out = {}
    for key in ("mean", "low", "high"):
        # Recta que pasa por (baseline_year, 0) -> (y1, v1) es demasiado fuerte
        # asumir linealidad desde 1995; interpolamos/extrapolamos solo entre
        # las dos anclas dadas, que es la unica info real que tenemos.
        slope = (v2[key] - v1[key]) / (y2 - y1)
        out[key] = v1[key] + slope * (year - y1)
    return out, extrapolated


def _rcp_projection(rcp_name, year):
    if rcp_name not in RCP_CATALOG:
        raise ValueError(f"RCP desconocido: {rcp_name}. Use uno de {sorted(RCP_CATALOG)}")
    entry = RCP_CATALOG[rcp_name]
    temp, temp_extrap = _interp_anchor_field(entry["temp_anomaly_C"], year)
    sea, sea_extrap = _interp_anchor_field(entry["sea_level_rise_m"], year)
    return {
        "rcp": rcp_name,
        "year": year,
        "forcing_2100_w_m2": entry["forcing_2100_w_m2"],
        "co2_2100": entry["co2_2100"],
        "temp_anomaly_C_vs_1986_2005": temp,
        "temp_extrapolated_outside_AR5_anchors": temp_extrap,
        "sea_level_rise_m_vs_1986_2005": sea,
        "sea_extrapolated_outside_AR5_anchors": sea_extrap,
        "narrative": entry["narrative"],
        "data_confidence": RCP_CATALOG_CONFIDENCE,
    }


# ------------------------------------------------------------------
# Motor generico de tendencias - no depende de ninguna tabla RCP
# ------------------------------------------------------------------

def _linear_regression(years, values):
    n = len(years)
    mean_x = sum(years) / n
    mean_y = sum(values) / n
    sxx = sum((x - mean_x) ** 2 for x in years)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(years, values))
    if sxx == 0:
        raise ValueError("Todos los anios son iguales, no se puede ajustar una tendencia")
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    # R^2
    y_pred = [slope * x + intercept for x in years]
    ss_res = sum((y - yp) ** 2 for y, yp in zip(values, y_pred))
    ss_tot = sum((y - mean_y) ** 2 for y in values)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    # Error estandar de la pendiente (para IC aproximado)
    if n > 2 and ss_tot > 0:
        s_err = math.sqrt(ss_res / (n - 2))
        slope_se = s_err / math.sqrt(sxx)
    else:
        slope_se = 0.0
    return {
        "slope_per_year": slope,
        "intercept": intercept,
        "r_squared": r_squared,
        "slope_std_error": slope_se,
        "slope_ci95_approx": [slope - 1.96 * slope_se, slope + 1.96 * slope_se],
    }


def _mann_kendall(values):
    """Test de Mann-Kendall (no parametrico) para deteccion de tendencia
    monotona. Devuelve S, varianza, Z y una lectura cualitativa. Formulas
    estandar (Mann 1945, Kendall 1975), sin aproximaciones propias."""
    n = len(values)
    s = 0
    for k in range(n - 1):
        for j in range(k + 1, n):
            diff = values[j] - values[k]
            s += (diff > 0) - (diff < 0)
    # Varianza (sin ajuste por empates, caso general)
    var_s = n * (n - 1) * (2 * n + 5) / 18
    if s > 0:
        z = (s - 1) / math.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s)
    else:
        z = 0.0
    # p-valor de dos colas, aproximacion normal estandar
    p_value = 2 * (1 - _norm_cdf(abs(z)))
    if p_value < 0.05:
        trend = "creciente" if s > 0 else "decreciente"
    else:
        trend = "sin tendencia significativa (p>=0.05)"
    return {"S": s, "variance_S": var_s, "Z": z, "p_value_two_sided": p_value, "trend": trend}


def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _cusum_changepoint(values):
    """Deteccion simple de punto de cambio por CUSUM sobre la media.
    Devuelve el indice donde la suma acumulada de desvios respecto a la
    media es maxima en valor absoluto (heuristica estandar, no un test
    estadistico formal de significancia)."""
    n = len(values)
    mean_v = sum(values) / n
    cusum = [0.0]
    for v in values:
        cusum.append(cusum[-1] + (v - mean_v))
    abs_cusum = [abs(c) for c in cusum]
    idx = abs_cusum.index(max(abs_cusum))
    # idx en cusum (incluye el 0 inicial) -> mapear a indice de dato
    data_idx = max(0, min(idx - 1, n - 1))
    return {
        "changepoint_index": data_idx,
        "cusum_series": cusum,
        "max_abs_cusum": max(abs_cusum),
        "note": ("Heuristica CUSUM simple, no es un test de significancia formal "
                 "(tipo Pettitt); usar como indicador exploratorio."),
    }


def _trend_analysis(years, values):
    if len(years) != len(values):
        raise ValueError("years y values deben tener la misma longitud")
    if len(years) < 3:
        raise ValueError("Se necesitan al menos 3 puntos para un analisis de tendencia")
    reg = _linear_regression(years, values)
    mk = _mann_kendall(values)
    cp = _cusum_changepoint(values)
    return {
        "n_points": len(years),
        "linear_regression": reg,
        "mann_kendall": mk,
        "changepoint_cusum": cp,
    }


# ------------------------------------------------------------------
# Dispatcher principal
# ------------------------------------------------------------------

def compute_climate_scenario(mode, params):
    params = params or {}

    if mode == "trend_analysis":
        years = params["years"]
        values = params["values"]
        return _trend_analysis(years, values)

    elif mode == "rcp_projection":
        rcp = params["rcp"]
        year = params["year"]
        return _rcp_projection(rcp, year)

    elif mode == "list_rcp_scenarios":
        return {
            "scenarios": {k: {"forcing_2100_w_m2": v["forcing_2100_w_m2"],
                               "narrative": v["narrative"]}
                          for k, v in RCP_CATALOG.items()},
            "data_confidence": RCP_CATALOG_CONFIDENCE,
        }

    elif mode == "validate":
        return _run_validation()

    else:
        raise ValueError(
            f"Modo desconocido: {mode}. Use 'trend_analysis', 'rcp_projection', "
            f"'list_rcp_scenarios' o 'validate'"
        )


CLIMATE_SCENARIO_SCHEMA = {
    "name": "climate_scenario_tool",
    "description": (
        "Analisis de escenarios climaticos: (1) motor generico de deteccion de "
        "tendencias en series temporales (regresion lineal, Mann-Kendall, "
        "changepoint CUSUM), y (2) catalogo RCP2.6/4.5/6.0/8.5 con datos reales "
        "de IPCC AR5 (forzamiento radiativo, CO2, anomalia de temperatura, "
        "aumento del nivel del mar), con confianza marcada por campo."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["trend_analysis", "rcp_projection", "list_rcp_scenarios", "validate"],
            },
            "years": {"type": "array", "items": {"type": "number"},
                       "description": "Solo para trend_analysis"},
            "values": {"type": "array", "items": {"type": "number"},
                        "description": "Solo para trend_analysis"},
            "rcp": {"type": "string", "enum": list(RCP_CATALOG.keys()),
                     "description": "Solo para rcp_projection"},
            "year": {"type": "number", "description": "Solo para rcp_projection"},
        },
        "required": ["mode"],
    },
}


# ------------------------------------------------------------------
# Validacion interna
# ------------------------------------------------------------------

def _run_validation():
    checks = []

    # 1) Serie perfectamente lineal creciente -> pendiente exacta, R2=1, MK creciente
    years = list(range(2000, 2021))
    values = [0.02 * (y - 2000) + 14.0 for y in years]
    reg = _linear_regression(years, values)
    checks.append({"name": "linear_regression_recovers_exact_slope",
                   "slope": reg["slope_per_year"], "r_squared": reg["r_squared"],
                   "passed": abs(reg["slope_per_year"] - 0.02) < 1e-9 and reg["r_squared"] > 0.999})

    mk = _mann_kendall(values)
    checks.append({"name": "mann_kendall_detects_monotonic_increase",
                   "S": mk["S"], "p_value": mk["p_value_two_sided"], "trend": mk["trend"],
                   "passed": mk["S"] == len(values) * (len(values) - 1) // 2 and mk["trend"] == "creciente"})

    # 2) Serie constante -> pendiente 0, MK sin tendencia (S=0)
    flat = [15.0] * 20
    reg_flat = _linear_regression(list(range(2000, 2020)), flat)
    mk_flat = _mann_kendall(flat)
    checks.append({"name": "flat_series_gives_zero_slope_and_no_trend",
                   "slope": reg_flat["slope_per_year"], "mk_S": mk_flat["S"],
                   "passed": abs(reg_flat["slope_per_year"]) < 1e-12 and mk_flat["S"] == 0})

    # 3) Serie con salto abrupto a mitad de camino -> CUSUM detecta el changepoint cerca del salto real
    step_series = [10.0] * 15 + [20.0] * 15
    cp = _cusum_changepoint(step_series)
    checks.append({"name": "cusum_detects_step_changepoint_near_true_location",
                   "detected_index": cp["changepoint_index"], "true_index": 14,
                   "passed": abs(cp["changepoint_index"] - 14) <= 2})

    # 4) RCP_projection en las anclas exactas reproduce los valores tabulados sin interpolar
    proj_2055 = _rcp_projection("RCP8.5", _ANCHOR_YEARS["2046_2065"])
    expected_temp = RCP_CATALOG["RCP8.5"]["temp_anomaly_C"]["2046_2065"]["mean"]
    checks.append({"name": "rcp_projection_matches_ar5_anchor_exactly",
                   "computed": proj_2055["temp_anomaly_C_vs_1986_2005"]["mean"],
                   "expected": expected_temp,
                   "passed": abs(proj_2055["temp_anomaly_C_vs_1986_2005"]["mean"] - expected_temp) < 1e-9})

    # 5) Monotonia fisica entre escenarios: a igual anio, mas forzamiento -> mas temperatura proyectada
    t26 = _rcp_projection("RCP2.6", 2090.5)["temp_anomaly_C_vs_1986_2005"]["mean"]
    t45 = _rcp_projection("RCP4.5", 2090.5)["temp_anomaly_C_vs_1986_2005"]["mean"]
    t60 = _rcp_projection("RCP6.0", 2090.5)["temp_anomaly_C_vs_1986_2005"]["mean"]
    t85 = _rcp_projection("RCP8.5", 2090.5)["temp_anomaly_C_vs_1986_2005"]["mean"]
    checks.append({"name": "temp_projection_monotonic_across_rcp_severity",
                   "RCP2.6": t26, "RCP4.5": t45, "RCP6.0": t60, "RCP8.5": t85,
                   "passed": t26 <= t45 <= t60 <= t85})

    # 6) Mismo chequeo para nivel del mar
    s26 = _rcp_projection("RCP2.6", 2090.5)["sea_level_rise_m_vs_1986_2005"]["mean"]
    s85 = _rcp_projection("RCP8.5", 2090.5)["sea_level_rise_m_vs_1986_2005"]["mean"]
    checks.append({"name": "sea_level_projection_higher_for_more_severe_rcp",
                   "RCP2.6": s26, "RCP8.5": s85, "passed": s26 < s85})

    # 7) Extrapolacion fuera de rango se marca explicitamente
    proj_2200 = _rcp_projection("RCP4.5", 2200)
    checks.append({"name": "extrapolation_outside_anchors_flagged",
                   "temp_extrapolated": proj_2200["temp_extrapolated_outside_AR5_anchors"],
                   "passed": proj_2200["temp_extrapolated_outside_AR5_anchors"] is True})

    # 8) Catalogo completo (4 RCPs) y con confianza declarada
    list_info = compute_climate_scenario("list_rcp_scenarios", {})
    checks.append({"name": "rcp_catalog_complete_and_confidence_flagged",
                   "n_scenarios": len(list_info["scenarios"]),
                   "confidence_flag": list_info["data_confidence"]["overall"],
                   "passed": len(list_info["scenarios"]) == 4 and
                             list_info["data_confidence"]["overall"] == "media-alta"})

    # 9) Modo invalido levanta error
    try:
        compute_climate_scenario("no_existe", {})
        invalid_raised = False
    except ValueError:
        invalid_raised = True
    checks.append({"name": "invalid_mode_raises", "passed": invalid_raised})

    # 10) trend_analysis con menos de 3 puntos levanta error
    try:
        _trend_analysis([2000, 2001], [1.0, 2.0])
        short_raised = False
    except ValueError:
        short_raised = True
    checks.append({"name": "trend_analysis_requires_min_3_points", "passed": short_raised})

    return {"checks": checks, "validation_passed": all(c["passed"] for c in checks)}


if __name__ == "__main__":
    import json
    print(json.dumps(_run_validation(), indent=2, ensure_ascii=False))

CLIMATE_SCENARIO_TOOL_SCHEMA = {   'type': 'object',
    'properties': {'mode': {'type': 'string', 'enum': ['trend_analysis', 'rcp_projection', 'list_rcp_scenarios', 'validate'], 'default': 'validate'}, 'params': {'type': 'object'}},
    'required': ['mode']}

try:
    from tool_registry import register_tool
    register_tool(
        name="climate_scenario_tool",
        schema={
        "name": "climate_scenario_tool",
        "description": 'Analisis de escenarios climaticos: trend_analysis (regresion lineal, Mann-Kendall, changepoint CUSUM sobre series temporales), rcp_projection (proyeccion de temperatura/nivel del mar para un RCP y anio dado), list_rcp_scenarios (catalogo RCP2.6/4.5/6.0/8.5 con datos IPCC AR5), validate.',
        "inputSchema": CLIMATE_SCENARIO_TOOL_SCHEMA,
    },
        handler=lambda args: compute_climate_scenario(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass

