"""
renewable_potential_tool
=========================
Potencial de energia solar (irradiacion diaria + estimacion de energia PV) y
potencial de energia eolica (distribucion de Weibull + limite de Betz).

Convenciones seguidas (inferidas de otras tools del repo):
  - dispatch por 'mode', params en un dict 'params'
  - mode='validate' corre una bateria de self-tests (formula cerrada vs
    integracion numerica independiente, no solo "valores esperados" de memoria)
  - sin dependencias externas mas alla de numpy/scipy (ya usadas en otras tools)

Modes:
  solar_daily_irradiation : H0 extraterrestre + H terrestre (Kt) + tilt (Liu-Jordan isotropico)
  pv_energy_estimate      : irradiacion en el plano del panel -> energia PV diaria/anual
  wind_weibull_energy     : AEP (energia anual esperada) via integracion Weibull x curva de potencia
  wind_betz_limit         : potencia teorica maxima (limite de Betz, Cp=16/27)
  validate                : self-tests

NOTA DE ALCANCE: modelos estandar de ingenieria (Duffie & Beckman para solar;
Weibull/Betz para eolica), pensados para estimaciones de primer orden a nivel
comunitario, no para diseno de ingenieria de detalle ni para bancabilidad de
proyecto. No reemplaza un estudio de recurso eolico/solar in-situ.
"""

import math
import numpy as np
from scipy import integrate
from scipy.special import gamma as gamma_fn

GSC = 1367.0  # constante solar, W/m^2


# ---------------------------------------------------------------------------
# SOLAR
# ---------------------------------------------------------------------------

def _declination_deg(n):
    """Declinacion solar (Cooper, 1969), grados. n = dia del anio (1-365)."""
    return 23.45 * math.sin(math.radians(360.0 * (284 + n) / 365.0))


def _sunset_hour_angle_deg(lat_deg, decl_deg):
    lat = math.radians(lat_deg)
    decl = math.radians(decl_deg)
    cos_ws = -math.tan(lat) * math.tan(decl)
    cos_ws = max(-1.0, min(1.0, cos_ws))  # clamp (sol de medianoche / polar)
    return math.degrees(math.acos(cos_ws))


def _h0_closed_form_MJ(lat_deg, n):
    """Irradiacion extraterrestre diaria sobre horizontal, MJ/m^2/dia (Duffie & Beckman eq. 1.10.3)."""
    decl = _declination_deg(n)
    ws = _sunset_hour_angle_deg(lat_deg, decl)
    lat = math.radians(lat_deg)
    decl_r = math.radians(decl)
    ws_r = math.radians(ws)
    ecc = 1.0 + 0.033 * math.cos(math.radians(360.0 * n / 365.0))
    val_Wh = (24.0 * 3600.0 * GSC / math.pi) * ecc * (
        math.cos(lat) * math.cos(decl_r) * math.sin(ws_r) + ws_r * math.sin(lat) * math.sin(decl_r)
    )
    return val_Wh / 1e6  # J/m^2/dia -> MJ/m^2/dia


def _h0_numeric_MJ(lat_deg, n):
    """Mismo H0 pero por integracion numerica directa de Gsc*ecc*cos(theta_z) sobre el angulo horario.
    Sirve como chequeo independiente de la formula cerrada (no reusa la misma derivacion)."""
    decl = math.radians(_declination_deg(n))
    lat = math.radians(lat_deg)
    ws = math.radians(_sunset_hour_angle_deg(lat_deg, math.degrees(decl)))
    ecc = 1.0 + 0.033 * math.cos(math.radians(360.0 * n / 365.0))

    def integrand(omega):
        cos_tz = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(omega)
        return max(0.0, GSC * ecc * cos_tz)

    # integral en angulo horario (rad) -> convertir a tiempo: dt = (24h/2pi) d(omega)
    val_W_per_m2_rad, _ = integrate.quad(integrand, -ws, ws)
    seconds_per_rad = (24.0 * 3600.0) / (2.0 * math.pi)
    return (val_W_per_m2_rad * seconds_per_rad) / 1e6


def _erbs_diffuse_fraction(kt):
    """Correlacion de Erbs (1982) para fraccion difusa diaria Hd/H a partir del indice de claridad Kt."""
    if kt <= 0.22:
        return 1.0 - 0.09 * kt
    elif kt <= 0.8:
        return 0.9511 - 0.1604 * kt + 4.388 * kt**2 - 16.638 * kt**3 + 12.336 * kt**4
    else:
        return 0.165


def solar_daily_irradiation(params):
    lat = params["latitude"]
    n = params.get("day_of_year", 172)  # default: solsticio de junio
    kt = params.get("clearness_index", 0.5)
    tilt_deg = params.get("tilt_deg", abs(lat))  # default: tilt = |latitud| (regla practica)
    rho_ground = params.get("ground_reflectance", 0.2)

    h0 = _h0_closed_form_MJ(lat, n)
    h_horizontal = kt * h0
    hd_fraction = _erbs_diffuse_fraction(kt)
    hd = hd_fraction * h_horizontal
    hb = h_horizontal - hd

    decl = _declination_deg(n)
    ws = _sunset_hour_angle_deg(lat, decl)
    lat_r, tilt_r, decl_r = math.radians(lat), math.radians(tilt_deg), math.radians(decl)
    ws_r = math.radians(ws)

    # Rb: razon de radiacion directa sobre superficie inclinada vs horizontal,
    # promedio diario (Liu-Jordan, superficie orientada al ecuador -> hemisferio
    # correspondiente segun signo de la latitud)
    lat_eff = lat_r - tilt_r if lat >= 0 else lat_r + tilt_r
    cos_ws_tilt = -math.tan(lat_eff) * math.tan(decl_r)
    cos_ws_tilt = max(-1.0, min(1.0, cos_ws_tilt))
    ws_tilt = math.acos(cos_ws_tilt)
    ws_tilt = min(ws_tilt, ws_r)  # el sol no puede estar sobre el horizonte fuera de [-ws,ws]

    num = (math.cos(lat_eff) * math.cos(decl_r) * math.sin(ws_tilt) + ws_tilt * math.sin(lat_eff) * math.sin(decl_r))
    den = (math.cos(lat_r) * math.cos(decl_r) * math.sin(ws_r) + ws_r * math.sin(lat_r) * math.sin(decl_r))
    rb = num / den if den > 0 else 0.0

    h_tilt = hb * rb + hd * (1 + math.cos(tilt_r)) / 2.0 + h_horizontal * rho_ground * (1 - math.cos(tilt_r)) / 2.0

    return {
        "H0_extraterrestrial_MJ_m2_day": round(h0, 4),
        "H_horizontal_MJ_m2_day": round(h_horizontal, 4),
        "H_diffuse_MJ_m2_day": round(hd, 4),
        "H_beam_MJ_m2_day": round(hb, 4),
        "H_tilted_MJ_m2_day": round(h_tilt, 4),
        "H_tilted_kWh_m2_day": round(h_tilt / 3.6, 4),
        "declination_deg": round(decl, 3),
        "sunset_hour_angle_deg": round(ws, 3),
        "beam_tilt_factor_Rb": round(rb, 4),
        "tilt_deg_used": tilt_deg,
    }


def pv_energy_estimate(params):
    area_m2 = params["panel_area_m2"]
    panel_efficiency = params.get("panel_efficiency", 0.18)
    performance_ratio = params.get("performance_ratio", 0.75)  # perdidas por temperatura, cableado, inversor, suciedad

    solar = solar_daily_irradiation(params)
    h_tilt_kWh = solar["H_tilted_kWh_m2_day"]

    daily_kWh = h_tilt_kWh * area_m2 * panel_efficiency * performance_ratio
    annual_kWh = daily_kWh * 365.0

    return {
        "solar_resource": solar,
        "panel_area_m2": area_m2,
        "panel_efficiency": panel_efficiency,
        "performance_ratio": performance_ratio,
        "daily_energy_kWh": round(daily_kWh, 3),
        "annual_energy_kWh": round(annual_kWh, 1),
    }


# ---------------------------------------------------------------------------
# EOLICA
# ---------------------------------------------------------------------------

def _weibull_pdf(v, c, k):
    v = np.asarray(v, dtype=float)
    out = np.zeros_like(v)
    mask = v > 0
    out[mask] = (k / c) * (v[mask] / c) ** (k - 1) * np.exp(-((v[mask] / c) ** k))
    return out


def _power_curve(v, rho, rotor_diameter_m, cp, cut_in, rated_speed, cut_out, rated_power_kw):
    area = math.pi * (rotor_diameter_m / 2.0) ** 2
    v = np.atleast_1d(np.asarray(v, dtype=float))
    p_kw = np.zeros_like(v)
    ramp = (v >= cut_in) & (v < rated_speed)
    p_kw[ramp] = 0.5 * rho * area * cp * v[ramp] ** 3 / 1000.0
    p_kw = np.minimum(p_kw, rated_power_kw)
    flat = (v >= rated_speed) & (v <= cut_out)
    p_kw[flat] = rated_power_kw
    return p_kw


def wind_weibull_energy(params):
    mean_v = params["mean_wind_speed_ms"]
    k = params.get("weibull_shape_k", 2.0)  # k=2 -> distribucion de Rayleigh, default razonable sin datos
    rho = params.get("air_density_kg_m3", 1.225)
    rotor_d = params["rotor_diameter_m"]
    cp = params.get("power_coefficient", 0.40)  # tipico turbinas reales 0.35-0.45 (limite de Betz 0.593)
    cut_in = params.get("cut_in_speed_ms", 3.0)
    rated_speed = params.get("rated_speed_ms", 12.0)
    cut_out = params.get("cut_out_speed_ms", 25.0)
    rated_power_kw = params.get("rated_power_kw", None)

    c_scale = mean_v / gamma_fn(1.0 + 1.0 / k)

    if rated_power_kw is None:
        area = math.pi * (rotor_d / 2.0) ** 2
        rated_power_kw = 0.5 * rho * area * cp * rated_speed**3 / 1000.0

    def integrand(v):
        p = _power_curve(v, rho, rotor_d, cp, cut_in, rated_speed, cut_out, rated_power_kw)[0]
        f = _weibull_pdf(np.array([v]), c_scale, k)[0]
        return p * f

    avg_power_kw, _ = integrate.quad(integrand, cut_in, cut_out, limit=200)
    aep_kwh = avg_power_kw * 8760.0
    capacity_factor = avg_power_kw / rated_power_kw if rated_power_kw > 0 else 0.0

    return {
        "mean_wind_speed_ms": mean_v,
        "weibull_shape_k": k,
        "weibull_scale_c": round(c_scale, 4),
        "rated_power_kw": round(rated_power_kw, 2),
        "average_power_kw": round(avg_power_kw, 3),
        "annual_energy_production_kWh": round(aep_kwh, 1),
        "capacity_factor": round(capacity_factor, 4),
    }


def wind_betz_limit(params):
    v = params["wind_speed_ms"]
    rho = params.get("air_density_kg_m3", 1.225)
    rotor_d = params["rotor_diameter_m"]
    cp_actual = params.get("power_coefficient", None)

    area = math.pi * (rotor_d / 2.0) ** 2
    cp_betz = 16.0 / 27.0
    p_wind_kw = 0.5 * rho * area * v**3 / 1000.0
    p_betz_kw = p_wind_kw * cp_betz

    result = {
        "wind_speed_ms": v,
        "rotor_area_m2": round(area, 3),
        "power_in_wind_kw": round(p_wind_kw, 3),
        "betz_limit_cp": round(cp_betz, 6),
        "max_theoretical_power_kw": round(p_betz_kw, 3),
    }
    if cp_actual is not None:
        result["actual_cp"] = cp_actual
        result["actual_power_kw"] = round(p_wind_kw * cp_actual, 3)
        result["fraction_of_betz_limit"] = round(cp_actual / cp_betz, 4)
    return result


# ---------------------------------------------------------------------------
# VALIDATE
# ---------------------------------------------------------------------------

def validate():
    checks = []

    # 1. H0: formula cerrada vs integracion numerica independiente, varios casos
    for lat, n in [(0.0, 80), (23.45, 172), (-33.45, 355), (50.0, 1)]:
        closed = _h0_closed_form_MJ(lat, n)
        numeric = _h0_numeric_MJ(lat, n)
        rel_err = abs(closed - numeric) / max(abs(closed), 1e-9)
        checks.append({
            "check": f"H0 closed-form vs numeric quad (lat={lat}, n={n})",
            "closed_form_MJ": round(closed, 4),
            "numeric_MJ": round(numeric, 4),
            "rel_error": rel_err,
            "pass": rel_err < 1e-3,
        })

    # 2. H0 en el ecuador en equinoccio debe ser cercano al maximo teorico simple
    #    (Gsc*ecc*24*3600/pi aprox, ya que ws=90deg=pi/2 y decl=0 simplifica el termino)
    h0_eq = _h0_closed_form_MJ(0.0, 80)
    expected_approx = (24 * 3600 * GSC / math.pi) / 1e6
    checks.append({
        "check": "H0 ecuador/equinoccio ~ orden de magnitud esperado (30-40 MJ/m2/dia)",
        "value_MJ": round(h0_eq, 3),
        "pass": 30.0 < h0_eq < 42.0,
    })

    # 3. Weibull pdf integra a 1
    c_test, k_test = 6.0, 2.0
    area_pdf, _ = integrate.quad(lambda v: _weibull_pdf(np.array([v]), c_test, k_test)[0], 0, 100)
    checks.append({
        "check": "Weibull PDF integra a 1 (c=6, k=2)",
        "integral": round(area_pdf, 6),
        "pass": abs(area_pdf - 1.0) < 1e-4,
    })

    # 4. Media de la Weibull recuperada via c = mean/Gamma(1+1/k) coincide con la media numerica
    mean_target = 7.5
    c_recovered = mean_target / gamma_fn(1.0 + 1.0 / k_test)
    mean_numeric, _ = integrate.quad(lambda v: v * _weibull_pdf(np.array([v]), c_recovered, k_test)[0], 0, 100)
    checks.append({
        "check": "Media Weibull recuperada (mean_target=7.5, k=2)",
        "mean_target": mean_target,
        "mean_numeric": round(mean_numeric, 4),
        "pass": abs(mean_numeric - mean_target) < 1e-3,
    })

    # 5. Limite de Betz: Cp maximo teorico = 16/27
    betz = wind_betz_limit({"wind_speed_ms": 8.0, "rotor_diameter_m": 80.0, "power_coefficient": 0.4})
    checks.append({
        "check": "Cp de Betz = 16/27 = 0.5926",
        "value": betz["betz_limit_cp"],
        "pass": abs(betz["betz_limit_cp"] - 16.0 / 27.0) < 1e-5,  # tolerancia por el redondeo a 6 decimales del resultado
    })

    # 6. Cp actual (0.4) debe dar potencia menor que el limite de Betz
    checks.append({
        "check": "Potencia con Cp real (0.4) < potencia limite de Betz",
        "actual_power_kw": betz["actual_power_kw"],
        "max_theoretical_power_kw": betz["max_theoretical_power_kw"],
        "pass": betz["actual_power_kw"] < betz["max_theoretical_power_kw"],
    })

    # 7. AEP monotona creciente en la velocidad media del viento
    aep_low = wind_weibull_energy({"mean_wind_speed_ms": 5.0, "rotor_diameter_m": 80.0})
    aep_high = wind_weibull_energy({"mean_wind_speed_ms": 9.0, "rotor_diameter_m": 80.0})
    checks.append({
        "check": "AEP monotona creciente con la velocidad media del viento",
        "aep_5ms_kWh": aep_low["annual_energy_production_kWh"],
        "aep_9ms_kWh": aep_high["annual_energy_production_kWh"],
        "pass": aep_high["annual_energy_production_kWh"] > aep_low["annual_energy_production_kWh"],
    })

    # 8. Factor de capacidad en rango fisico [0,1]
    checks.append({
        "check": "Factor de capacidad en [0,1]",
        "value": aep_high["capacity_factor"],
        "pass": 0.0 <= aep_high["capacity_factor"] <= 1.0,
    })

    n_pass = sum(1 for c in checks if c["pass"])
    return {
        "n_checks": len(checks),
        "n_pass": n_pass,
        "all_pass": n_pass == len(checks),
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# DISPATCH (para integrar con register_tool del repo real)
# ---------------------------------------------------------------------------

def renewable_potential_tool(mode, params=None):
    params = params or {}
    if mode == "solar_daily_irradiation":
        return solar_daily_irradiation(params)
    elif mode == "pv_energy_estimate":
        return pv_energy_estimate(params)
    elif mode == "wind_weibull_energy":
        return wind_weibull_energy(params)
    elif mode == "wind_betz_limit":
        return wind_betz_limit(params)
    elif mode == "validate":
        return validate()
    else:
        raise ValueError(f"mode desconocido: {mode}")


TOOL_SCHEMA = {
    "name": "renewable_potential_tool",
    "description": (
        "Potencial de energia renovable a nivel comunitario/primer-orden. Solar: irradiacion diaria "
        "extraterrestre y terrestre (Kt), correccion por inclinacion del panel (Liu-Jordan isotropico), "
        "y estimacion de energia PV diaria/anual dado area y eficiencia de panel. Eolica: energia anual "
        "esperada (AEP) integrando una curva de potencia tipica contra una distribucion de Weibull del "
        "viento, y limite teorico de Betz (Cp_max=16/27) para comparar contra el Cp real de una turbina. "
        "Modelos estandar de ingenieria (Duffie & Beckman; Weibull/Betz) para estimaciones de primer orden, "
        "no reemplazan un estudio de recurso solar/eolico in-situ ni diseno de ingenieria de detalle."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["solar_daily_irradiation", "pv_energy_estimate", "wind_weibull_energy", "wind_betz_limit", "validate"],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    import json
    result = validate()
    print(json.dumps(result, indent=2, ensure_ascii=False))


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

def _handle(args):
    return renewable_potential_tool(args.get("mode"), args.get("params"))

register_tool("renewable_potential_tool", TOOL_SCHEMA, _handle)
