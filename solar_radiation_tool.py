"""
solar_radiation_tool.py

Geometria solar y radiacion en cielo despejado -- formula cerrada, sin
datos meteorologicos externos, sin solver. Todo lo que necesita es
lat/lon, dia del anio y hora; el modelo de cielo despejado (Hottel 1976)
solo necesita altitud y un tipo de clima tabulado.

Referencias (textbook estandar de ingenieria solar, formulas de dominio
publico re-derivadas aca, no texto copiado):
  - Duffie & Beckman, "Solar Engineering of Thermal Processes" -- geometria
    solar (declinacion/EoT de Spencer 1971), incidencia sobre superficie
    inclinada, modelo isotropico de cielo difuso (Liu & Jordan 1963).
  - Hottel (1976) "A simple model for estimating the transmittance of
    direct solar radiation through clear atmospheres" -- tau_b(altitud,
    clima), tau_d de Liu-Jordan (1960).

Convenciones (Duffie & Beckman):
  - latitud: + norte, - sur.
  - beta (tilt): 0=horizontal, 90=vertical.
  - gamma (azimut de superficie): 0 = mirando al ecuador (sur en
    hemisferio norte, norte en hemisferio sur), + hacia el oeste.
  - hora angular H: 0 al mediodia solar, +/-15 grados por hora
    (matutino negativo).
  - "hora solar" (solar_time_hr) = tiempo solar aparente local, NO hora
    de reloj. El modo solar_time convierte hora de reloj -> hora solar
    usando la ecuacion del tiempo + correccion de longitud.

CUIDADO DE CONFIANZA DE DATOS:
  - geometria solar (declinacion, EoT, posicion del sol): alta -- formulas
    de Spencer, error tipico < 0.01 grado en declinacion, < 1 min en EoT,
    validadas aca contra los casos limite de equinoccio/solsticio.
  - clear-sky Hottel: media -- el propio modelo tiene +/-15% de incertidumbre
    documentada en la literatura contra medicion real, aun en cielo
    perfectamente despejado (variabilidad atmosferica no capturada por
    4 climas tabulados). Sirve para diseno preliminar, no para prediccion
    de produccion energetica de precision.
"""
import math

SOLAR_CONSTANT = 1367.0  # W/m^2 (Gsc, valor clasico de ingenieria, Duffie&Beckman)

# Dias representativos "promedio del mes" de Klein (1977), usados en
# ingenieria solar para aproximar el comportamiento anual con 12 puntos
# en vez de integrar los 365 dias.
KLEIN_REPRESENTATIVE_DAYS = [17, 47, 75, 105, 135, 162, 198, 228, 258, 288, 318, 344]

# Hottel (1976), tabla de correccion por clima (r0, r1, rk) sobre los
# coeficientes de atmosfera estandar a0*, a1*, k*. Altitud de referencia
# 0 = nivel del mar.
HOTTEL_CLIMATES = {
    "tropical": dict(r0=0.95, r1=0.98, rk=1.02),
    "midlatitude_summer": dict(r0=0.97, r1=0.99, rk=1.02),
    "subarctic_summer": dict(r0=0.99, r1=0.99, rk=1.01),
    "midlatitude_winter": dict(r0=1.03, r1=1.01, rk=1.00),
}

D2R = math.pi / 180.0
R2D = 180.0 / math.pi


def _B(n):
    """Angulo del dia (radianes), Spencer 1971. n = dia del anio (1-365)."""
    return 2 * math.pi * (n - 1) / 365.0


def _declination_deg(n):
    """Declinacion solar (grados), serie de Spencer 1971 -- error < 0.0006 rad
    (~0.03 grados), mucho mas precisa que la formula simple de Cooper
    (23.45*sin(360(284+n)/365)) que se usa a veces como aproximacion rapida."""
    B = _B(n)
    delta = (0.006918 - 0.399912 * math.cos(B) + 0.070257 * math.sin(B)
              - 0.006758 * math.cos(2 * B) + 0.000907 * math.sin(2 * B)
              - 0.002697 * math.cos(3 * B) + 0.00148 * math.sin(3 * B))
    return delta * R2D


def _equation_of_time_min(n):
    """Ecuacion del tiempo (minutos), Spencer 1971."""
    B = _B(n)
    return 229.18 * (0.000075 + 0.001868 * math.cos(B) - 0.032077 * math.sin(B)
                      - 0.014615 * math.cos(2 * B) - 0.04089 * math.sin(2 * B))


def _eccentricity_factor(n):
    """E0 = (Gon/Gsc), correccion de excentricidad orbital, Spencer 1971."""
    B = _B(n)
    return (1.00011 + 0.034221 * math.cos(B) + 0.00128 * math.sin(B)
            + 0.000719 * math.cos(2 * B) + 0.000077 * math.sin(2 * B))


def _solar_time_hr(clock_time_hr, longitude_deg, std_meridian_deg, n):
    eot = _equation_of_time_min(n)
    correction_min = 4 * (std_meridian_deg - longitude_deg) + eot
    return clock_time_hr + correction_min / 60.0


def _hour_angle_deg(solar_time_hr):
    return 15.0 * (solar_time_hr - 12.0)


def _sun_position(lat_deg, n, solar_time_hr):
    """Devuelve (altitud, azimut, zenit) en grados. Azimut medido desde el
    sur (convencion Duffie&Beckman), + hacia el oeste."""
    lat = lat_deg * D2R
    dec = _declination_deg(n) * D2R
    H = _hour_angle_deg(solar_time_hr) * D2R

    cos_theta_z = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(H)
    cos_theta_z = max(-1.0, min(1.0, cos_theta_z))
    theta_z = math.acos(cos_theta_z)
    altitude = math.pi / 2 - theta_z

    if math.cos(altitude) < 1e-9:
        azimuth = 0.0
    else:
        cos_gamma_s = (cos_theta_z * math.sin(lat) - math.sin(dec)) / (math.cos(altitude) * math.cos(lat))
        cos_gamma_s = max(-1.0, min(1.0, cos_gamma_s))
        gamma_s = math.acos(cos_gamma_s)
        # signo: manana (H<0) azimut negativo (este), tarde (H>0) positivo (oeste)
        if H < 0:
            gamma_s = -gamma_s
        azimuth = gamma_s

    return altitude * R2D, azimuth * R2D, theta_z * R2D


def _incidence_angle_deg(lat_deg, n, solar_time_hr, beta_deg, gamma_deg):
    """Angulo de incidencia sobre superficie con tilt beta y azimut gamma
    (0=mirando al ecuador). Formula general de Duffie&Beckman Eq. 1.6.2."""
    lat = lat_deg * D2R
    dec = _declination_deg(n) * D2R
    H = _hour_angle_deg(solar_time_hr) * D2R
    beta = beta_deg * D2R
    gamma = gamma_deg * D2R

    cos_theta = (math.sin(dec) * math.sin(lat) * math.cos(beta)
                 - math.sin(dec) * math.cos(lat) * math.sin(beta) * math.cos(gamma)
                 + math.cos(dec) * math.cos(lat) * math.cos(beta) * math.cos(H)
                 + math.cos(dec) * math.sin(lat) * math.sin(beta) * math.cos(gamma) * math.cos(H)
                 + math.cos(dec) * math.sin(beta) * math.sin(gamma) * math.sin(H))
    cos_theta = max(-1.0, min(1.0, cos_theta))
    return math.acos(cos_theta) * R2D


def _sunset_hour_angle_deg(lat_deg, n):
    lat = lat_deg * D2R
    dec = _declination_deg(n) * D2R
    cos_ws = -math.tan(lat) * math.tan(dec)
    if cos_ws <= -1.0:
        return 180.0  # sol de medianoche
    if cos_ws >= 1.0:
        return 0.0    # noche polar
    return math.acos(cos_ws) * R2D


def _sun_times(params):
    lat = params.get("latitude_deg")
    n = params.get("day_of_year")
    if lat is None or n is None:
        raise ValueError("sun_times requiere latitude_deg y day_of_year")
    ws = _sunset_hour_angle_deg(lat, n)
    day_length_hr = 2 * ws / 15.0
    sunrise = 12.0 - ws / 15.0
    sunset = 12.0 + ws / 15.0
    return {
        "latitude_deg": lat, "day_of_year": n,
        "declination_deg": round(_declination_deg(n), 4),
        "equation_of_time_min": round(_equation_of_time_min(n), 3),
        "sunset_hour_angle_deg": round(ws, 4),
        "sunrise_solar_time_hr": round(sunrise, 4),
        "sunset_solar_time_hr": round(sunset, 4),
        "day_length_hr": round(day_length_hr, 4),
    }


def _solar_time_mode(params):
    required = ["clock_time_hr", "longitude_deg", "std_meridian_deg", "day_of_year"]
    missing = [k for k in required if params.get(k) is None]
    if missing:
        raise ValueError(f"solar_time requiere: {', '.join(missing)}")
    st = _solar_time_hr(params["clock_time_hr"], params["longitude_deg"],
                         params["std_meridian_deg"], params["day_of_year"])
    return {
        "clock_time_hr": params["clock_time_hr"],
        "equation_of_time_min": round(_equation_of_time_min(params["day_of_year"]), 3),
        "longitude_correction_min": round(4 * (params["std_meridian_deg"] - params["longitude_deg"]), 3),
        "solar_time_hr": round(st, 4),
        "note": "std_meridian_deg = 15 * offset_UTC_horas (ej. Chile continental "
                "UTC-4 -> -60; positivo al este de Greenwich).",
    }


def _solar_position_mode(params):
    lat = params.get("latitude_deg")
    n = params.get("day_of_year")
    st = params.get("solar_time_hr")
    if lat is None or n is None or st is None:
        raise ValueError("solar_position requiere latitude_deg, day_of_year, solar_time_hr")
    alt, az, zen = _sun_position(lat, n, st)
    result = {
        "latitude_deg": lat, "day_of_year": n, "solar_time_hr": st,
        "declination_deg": round(_declination_deg(n), 4),
        "hour_angle_deg": round(_hour_angle_deg(st), 4),
        "solar_altitude_deg": round(alt, 4),
        "solar_zenith_deg": round(zen, 4),
        "solar_azimuth_deg": round(az, 4),
        "sun_is_up": alt > 0,
    }
    beta = params.get("beta_deg")
    gamma = params.get("gamma_deg", 0.0)
    if beta is not None:
        result["surface_tilt_deg"] = beta
        result["surface_azimuth_deg"] = gamma
        result["incidence_angle_deg"] = round(_incidence_angle_deg(lat, n, st, beta, gamma), 4)
    return result


def _clearsky_beam_diffuse(lat_deg, n, solar_time_hr, altitude_km=0.0, climate="midlatitude_summer"):
    """Nucleo Hottel (1976) + Liu-Jordan (1960). Devuelve (I_bn, I_b_horiz,
    I_d_horiz, I_global_horiz) en W/m^2. Si el sol esta bajo el horizonte,
    todo es 0."""
    if climate not in HOTTEL_CLIMATES:
        raise ValueError(f"clima desconocido: {climate!r}. Disponibles: {sorted(HOTTEL_CLIMATES)}")
    alt, _, _ = _sun_position(lat_deg, n, solar_time_hr)
    if alt <= 0:
        return 0.0, 0.0, 0.0, 0.0

    A = altitude_km
    a0s = 0.4237 - 0.00821 * (6 - A) ** 2
    a1s = 0.5055 + 0.00595 * (6.5 - A) ** 2
    ks = 0.2711 + 0.01858 * (2.5 - A) ** 2
    c = HOTTEL_CLIMATES[climate]
    a0, a1, k = c["r0"] * a0s, c["r1"] * a1s, c["rk"] * ks

    sin_alt = math.sin(alt * D2R)
    tau_b = a0 + a1 * math.exp(-k / sin_alt)
    tau_d = 0.2710 - 0.2939 * tau_b  # Liu-Jordan, diffuse transmittance en cielo despejado

    G0n = SOLAR_CONSTANT * _eccentricity_factor(n)
    I_bn = G0n * tau_b
    I_b_h = I_bn * sin_alt
    I_d_h = G0n * tau_d * sin_alt
    return I_bn, I_b_h, I_d_h, I_b_h + I_d_h


def _clearsky_mode(params):
    lat = params.get("latitude_deg")
    n = params.get("day_of_year")
    st = params.get("solar_time_hr")
    if lat is None or n is None or st is None:
        raise ValueError("clearsky_irradiance requiere latitude_deg, day_of_year, solar_time_hr")
    alt_km = params.get("altitude_km", 0.0)
    climate = params.get("climate", "midlatitude_summer")
    I_bn, I_bh, I_dh, I_gh = _clearsky_beam_diffuse(lat, n, st, alt_km, climate)
    return {
        "latitude_deg": lat, "day_of_year": n, "solar_time_hr": st,
        "climate": climate, "altitude_km": alt_km,
        "solar_altitude_deg": round(_sun_position(lat, n, st)[0], 4),
        "beam_normal_Wm2": round(I_bn, 2),
        "beam_horizontal_Wm2": round(I_bh, 2),
        "diffuse_horizontal_Wm2": round(I_dh, 2),
        "global_horizontal_Wm2": round(I_gh, 2),
        "data_confidence": "media",
        "note": "Modelo Hottel de cielo despejado: +/-15% de incertidumbre tipica "
                "documentada en literatura incluso en dia realmente despejado. Para "
                "diseno preliminar, no reemplaza datos TMY/satelitales.",
    }


def _poa_irradiance(lat_deg, n, solar_time_hr, beta_deg, gamma_deg, altitude_km=0.0,
                      climate="midlatitude_summer", albedo=0.2):
    """Irradiancia total sobre plano inclinado (POA), modelo isotropico de
    cielo difuso (Liu & Jordan 1963): I_poa = beam + diffuse_isotropic + reflejo_suelo."""
    I_bn, I_bh, I_dh, I_gh = _clearsky_beam_diffuse(lat_deg, n, solar_time_hr, altitude_km, climate)
    if I_bn == 0.0 and I_gh == 0.0:
        return 0.0, 0.0, 0.0, 0.0
    theta = _incidence_angle_deg(lat_deg, n, solar_time_hr, beta_deg, gamma_deg)
    cos_theta = max(0.0, math.cos(theta * D2R))  # sin luz directa si el sol queda detras del plano

    beta = beta_deg * D2R
    I_beam_t = I_bn * cos_theta
    I_diff_t = I_dh * (1 + math.cos(beta)) / 2.0
    I_refl_t = I_gh * albedo * (1 - math.cos(beta)) / 2.0
    return I_beam_t, I_diff_t, I_refl_t, I_beam_t + I_diff_t + I_refl_t


def _poa_mode(params):
    lat = params.get("latitude_deg")
    n = params.get("day_of_year")
    st = params.get("solar_time_hr")
    beta = params.get("beta_deg")
    if lat is None or n is None or st is None or beta is None:
        raise ValueError("poa_irradiance requiere latitude_deg, day_of_year, solar_time_hr, beta_deg")
    gamma = params.get("gamma_deg", 0.0 if lat >= 0 else 180.0)
    alt_km = params.get("altitude_km", 0.0)
    climate = params.get("climate", "midlatitude_summer")
    albedo = params.get("albedo", 0.2)
    beam, diff, refl, total = _poa_irradiance(lat, n, st, beta, gamma, alt_km, climate, albedo)
    return {
        "latitude_deg": lat, "day_of_year": n, "solar_time_hr": st,
        "beta_deg": beta, "gamma_deg": gamma, "albedo": albedo,
        "poa_beam_Wm2": round(beam, 2),
        "poa_diffuse_Wm2": round(diff, 2),
        "poa_ground_reflected_Wm2": round(refl, 2),
        "poa_total_Wm2": round(total, 2),
        "data_confidence": "media",
        "note": "Cielo difuso isotropico (Liu-Jordan); no incluye componente "
                "circumsolar/horizonte (modelos anisotropicos tipo Hay-Davies "
                "darian un pequenio ajuste extra, tipicamente <5% en cielo despejado).",
    }


def _daily_energy_kwh_m2(lat_deg, n, beta_deg, gamma_deg, altitude_km=0.0,
                           climate="midlatitude_summer", albedo=0.2, n_samples=97):
    """Integra la POA total a lo largo del dia (regla del trapecio, muestreo
    uniforme en hora solar 0-24h) y devuelve energia diaria en kWh/m^2."""
    times = [24.0 * i / (n_samples - 1) for i in range(n_samples)]
    values = []
    for t in times:
        _, _, _, total = _poa_irradiance(lat_deg, n, t, beta_deg, gamma_deg, altitude_km, climate, albedo)
        values.append(total)
    # trapecio
    dt_hr = times[1] - times[0]
    energy_Wh_m2 = 0.0
    for i in range(len(values) - 1):
        energy_Wh_m2 += (values[i] + values[i + 1]) / 2.0 * dt_hr
    return energy_Wh_m2 / 1000.0


def _daily_energy_mode(params):
    lat = params.get("latitude_deg")
    n = params.get("day_of_year")
    beta = params.get("beta_deg")
    if lat is None or n is None or beta is None:
        raise ValueError("daily_energy requiere latitude_deg, day_of_year, beta_deg")
    gamma = params.get("gamma_deg", 0.0 if lat >= 0 else 180.0)
    alt_km = params.get("altitude_km", 0.0)
    climate = params.get("climate", "midlatitude_summer")
    albedo = params.get("albedo", 0.2)
    e = _daily_energy_kwh_m2(lat, n, beta, gamma, alt_km, climate, albedo)
    return {
        "latitude_deg": lat, "day_of_year": n, "beta_deg": beta, "gamma_deg": gamma,
        "daily_energy_kWh_m2": round(e, 4),
        "data_confidence": "media",
    }


def _optimize_tilt_mode(params):
    lat = params.get("latitude_deg")
    if lat is None:
        raise ValueError("optimize_tilt requiere latitude_deg")
    gamma = params.get("gamma_deg", 0.0 if lat >= 0 else 180.0)
    alt_km = params.get("altitude_km", 0.0)
    climate = params.get("climate", "midlatitude_summer")
    albedo = params.get("albedo", 0.2)
    period = params.get("period", "annual")  # "annual" o day_of_year especifico
    beta_step = params.get("beta_step_deg", 1.0)

    if period == "annual":
        days = KLEIN_REPRESENTATIVE_DAYS
    else:
        days = [int(period)]

    betas = [i * beta_step for i in range(int(90 / beta_step) + 1)]
    best_beta, best_energy = None, -1.0
    curve = []
    for beta in betas:
        total = sum(_daily_energy_kwh_m2(lat, n, beta, gamma, alt_km, climate, albedo) for n in days)
        avg_daily = total / len(days)
        curve.append({"beta_deg": beta, "avg_daily_energy_kWh_m2": round(avg_daily, 4)})
        if avg_daily > best_energy:
            best_energy = avg_daily
            best_beta = beta

    return {
        "latitude_deg": lat, "gamma_deg": gamma, "period": period,
        "optimal_beta_deg": best_beta,
        "optimal_avg_daily_energy_kWh_m2": round(best_energy, 4),
        "rule_of_thumb_beta_deg": round(abs(lat), 2),
        "note": "rule_of_thumb_beta_deg = |latitud| es la heuristica clasica de "
                "ingenieria para tilt fijo optimo anual; el optimo calculado deberia "
                "quedar cerca (tipicamente dentro de +/-10-15 grados, la diferencia "
                "viene de la asimetria estacional del clima Hottel elegido).",
        "sweep_beta_step_deg": beta_step,
        "curve": curve,
    }


def _validate():
    checks = []

    # 1) Declinacion ~0 en equinoccio (20 marzo aprox, n=79) y ~+23.45 en
    # solsticio de junio (n=172), ~-23.45 en solsticio de diciembre (n=355)
    d_eq = _declination_deg(79)
    checks.append({"case": "declinacion en equinoccio marzo (n=79) ~ 0",
                    "got": round(d_eq, 3), "expected": 0.0, "ok": abs(d_eq) < 1.0})
    d_jun = _declination_deg(172)
    checks.append({"case": "declinacion en solsticio junio (n=172) ~ +23.45",
                    "got": round(d_jun, 3), "expected": 23.45, "ok": abs(d_jun - 23.45) < 0.5})
    d_dec = _declination_deg(355)
    checks.append({"case": "declinacion en solsticio diciembre (n=355) ~ -23.45",
                    "got": round(d_dec, 3), "expected": -23.45, "ok": abs(d_dec + 23.45) < 0.5})

    # 2) En el ecuador, equinoccio, mediodia solar: sol en el cenit (altitud=90)
    alt, az, zen = _sun_position(0.0, 79, 12.0)
    checks.append({"case": "ecuador+equinoccio+mediodia: altitud solar ~ 90",
                    "got": round(alt, 2), "expected": 90.0, "ok": abs(alt - 90) < 1.0})

    # 3) Tropico de Cancer, solsticio de junio, mediodia: sol en el cenit
    alt2, _, _ = _sun_position(23.45, 172, 12.0)
    checks.append({"case": "Tropico de Cancer+solsticio junio+mediodia: altitud ~ 90",
                    "got": round(alt2, 2), "expected": 90.0, "ok": abs(alt2 - 90) < 1.0})

    # 4) Excentricidad orbital: G0n maximo cerca de perihelio (principios de enero,
    # n~3) y minimo cerca de afelio (principios de julio, n~186)
    E0_jan = _eccentricity_factor(3)
    E0_jul = _eccentricity_factor(186)
    checks.append({"case": "irradiancia extraterrestre mayor en enero (perihelio) que en julio (afelio)",
                    "got": round(E0_jan, 5), "expected_greater_than": round(E0_jul, 5),
                    "ok": E0_jan > E0_jul})
    checks.append({"case": "Gon en rango fisico esperado (1322-1414 W/m2 aprox)",
                    "got": round(SOLAR_CONSTANT * E0_jan, 1),
                    "ok": 1322 <= SOLAR_CONSTANT * E0_jan <= 1420})

    # 5) Consistencia interna: incidencia sobre superficie horizontal (beta=0)
    # debe coincidir con el zenit solar, para cualquier gamma (irrelevante si beta=0)
    lat_t, n_t, st_t = -41.87, 172, 10.5  # Castro, Chiloe aprox, invierno-verano cualquiera
    theta_h = _incidence_angle_deg(lat_t, n_t, st_t, 0.0, 0.0)
    _, _, zen_t = _sun_position(lat_t, n_t, st_t)
    checks.append({"case": "incidencia sobre horizontal == zenit solar (consistencia interna)",
                    "got": round(theta_h, 4), "expected": round(zen_t, 4),
                    "ok": abs(theta_h - zen_t) < 1e-6})

    # 6) Superficie inclinada a beta=latitud, mirando al ecuador, en equinoccio
    # y mediodia solar: incidencia = 0 (el plano apunta exactamente al sol)
    lat_test = 35.0
    gamma_test = 0.0  # hemisferio norte, mirando al sur (ecuador)
    theta_opt = _incidence_angle_deg(lat_test, 79, 12.0, lat_test, gamma_test)
    checks.append({"case": "beta=lat, gamma=ecuador, equinoccio, mediodia: incidencia ~ 0",
                    "got": round(theta_opt, 3), "expected": 0.0, "ok": abs(theta_opt) < 0.5})
    # mismo caso en hemisferio sur (gamma=180=mirando al norte)
    lat_test_s = -35.0
    theta_opt_s = _incidence_angle_deg(lat_test_s, 79, 12.0, abs(lat_test_s), 180.0)
    checks.append({"case": "hemisferio sur: beta=|lat|, gamma=180(norte), equinoccio, mediodia: incidencia ~ 0",
                    "got": round(theta_opt_s, 3), "expected": 0.0, "ok": abs(theta_opt_s) < 0.5})

    # 7) Duracion del dia = 12h exactas en el ecuador para cualquier dia del anio
    st = _sun_times({"latitude_deg": 0.0, "day_of_year": 172})
    checks.append({"case": "duracion del dia en el ecuador ~ 12h (todo el anio)",
                    "got": st["day_length_hr"], "expected": 12.0, "ok": abs(st["day_length_hr"] - 12.0) < 0.05})

    # 8) Clear-sky Hottel: I_bn debe estar en rango fisico razonable a nivel del
    # mar con sol alto (0 < I_bn < Gon), y crecer con la altitud (menos atmosfera
    # que atravesar)
    I_bn_sl, _, _, _ = _clearsky_beam_diffuse(-33.0, 355, 12.0, altitude_km=0.0, climate="midlatitude_summer")
    I_bn_hi, _, _, _ = _clearsky_beam_diffuse(-33.0, 355, 12.0, altitude_km=3.0, climate="midlatitude_summer")
    Gon = SOLAR_CONSTANT * _eccentricity_factor(355)
    checks.append({"case": "clear-sky I_bn en rango fisico (0, Gon) a nivel del mar",
                    "got": round(I_bn_sl, 1), "ok": 0 < I_bn_sl < Gon})
    checks.append({"case": "clear-sky I_bn crece con altitud (menos atmosfera)",
                    "got": round(I_bn_hi, 1), "expected_greater_than": round(I_bn_sl, 1),
                    "ok": I_bn_hi > I_bn_sl})

    # 9) POA con beta=0 debe coincidir con la irradiancia global horizontal
    # (el termino de reflejo de suelo se anula con beta=0 y el diffuso isotropico
    # coincide con el horizontal cuando el plano ES el horizonte)
    _, _, _, I_gh = _clearsky_beam_diffuse(-33.0, 355, 12.0, 0.0, "midlatitude_summer")
    _, _, _, poa_h = _poa_irradiance(-33.0, 355, 12.0, 0.0, 0.0, 0.0, "midlatitude_summer", 0.2)
    checks.append({"case": "POA con beta=0 == irradiancia global horizontal",
                    "got": round(poa_h, 2), "expected": round(I_gh, 2), "ok": abs(poa_h - I_gh) < 0.5})

    # 10) Optimizador: para latitudes medias, el tilt optimo anual deberia
    # quedar razonablemente cerca de |latitud| (heuristica clasica)
    opt = _optimize_tilt_mode({"latitude_deg": -33.45, "beta_step_deg": 5.0})
    diff_rule = abs(opt["optimal_beta_deg"] - opt["rule_of_thumb_beta_deg"])
    checks.append({"case": "tilt optimo anual cerca de |latitud| (heuristica clasica, tol 15 grados)",
                    "got": opt["optimal_beta_deg"], "expected_near": opt["rule_of_thumb_beta_deg"],
                    "ok": diff_rule <= 15.0})

    return {"validate": True, "all_passed": all(c["ok"] for c in checks), "checks": checks}


def compute_solar_radiation(mode, params=None):
    params = params or {}
    if mode == "solar_time":
        return _solar_time_mode(params)
    elif mode == "sun_times":
        return _sun_times(params)
    elif mode == "solar_position":
        return _solar_position_mode(params)
    elif mode == "clearsky_irradiance":
        return _clearsky_mode(params)
    elif mode == "poa_irradiance":
        return _poa_mode(params)
    elif mode == "daily_energy":
        return _daily_energy_mode(params)
    elif mode == "optimize_tilt":
        return _optimize_tilt_mode(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            f"mode desconocido: {mode!r}. Valores validos: solar_time, sun_times, "
            f"solar_position, clearsky_irradiance, poa_irradiance, daily_energy, "
            f"optimize_tilt, validate."
        )


SOLAR_RADIATION_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["solar_time", "sun_times", "solar_position", "clearsky_irradiance",
                     "poa_irradiance", "daily_energy", "optimize_tilt", "validate"],
            "default": "poa_irradiance",
        },
        "latitude_deg": {"type": "number", "description": "+ norte, - sur."},
        "longitude_deg": {"type": "number", "description": "+ este de Greenwich. Solo solar_time."},
        "std_meridian_deg": {"type": "number",
            "description": "Solo solar_time. 15 * offset_UTC_horas (ej. Chile continental UTC-4 -> -60)."},
        "clock_time_hr": {"type": "number", "description": "Hora de reloj decimal (0-24). Solo solar_time."},
        "day_of_year": {"type": "integer", "description": "1-365."},
        "solar_time_hr": {"type": "number", "description": "Hora solar aparente decimal, mediodia solar=12."},
        "beta_deg": {"type": "number", "description": "Inclinacion del plano: 0=horizontal, 90=vertical."},
        "gamma_deg": {"type": "number",
            "description": "Azimut del plano, 0=mirando al ecuador (default segun hemisferio de latitude_deg)."},
        "altitude_km": {"type": "number", "default": 0.0, "description": "Altitud del sitio sobre el nivel del mar."},
        "climate": {"type": "string", "enum": sorted(HOTTEL_CLIMATES), "default": "midlatitude_summer",
            "description": (
                "Perfil de turbidez atmosferica de Hottel (1976) para el modelo de "
                "cielo despejado -- NO es un clima geografico/bioma, es una clasificacion "
                "de que tan clara esta la atmosfera tipicamente, segun banda de latitud y "
                "estacion. Elegir por banda de latitud + estacion del sitio, no por nombre "
                "descriptivo local: 'tropical' (0-23 lat aprox, cualquier estacion), "
                "'midlatitude_summer' (23-66 lat aprox, verano de ese hemisferio -- mas "
                "turbidez/humedad, default de este tool), 'midlatitude_winter' (23-66 lat "
                "aprox, invierno de ese hemisferio -- atmosfera mas clara/seca, mayor "
                "irradiancia directa relativa), 'subarctic_summer' (>66 lat aprox, unico "
                "perfil de esa banda, valido solo en meses de luz solar). Ojo con el "
                "hemisferio: para sitios en el hemisferio sur, el 'verano' u 'invierno' "
                "del perfil corresponde a la estacion real del sitio, no al nombre en si "
                "-- ej. julio en Chiloe (lat ~-42) es invierno austral, entonces "
                "corresponde 'midlatitude_winter' aunque el string no diga 'sur'."
            )},
        "albedo": {"type": "number", "default": 0.2, "description": "Reflectancia del suelo (0-1)."},
        "period": {"type": "string", "default": "annual",
            "description": "optimize_tilt: 'annual' (12 dias representativos de Klein) o un day_of_year especifico como string."},
        "beta_step_deg": {"type": "number", "default": 1.0, "description": "optimize_tilt: paso del barrido de tilt."},
    },
    "required": ["mode"],
}


try:
    from tool_registry import register_tool
    register_tool(
        name="solar_radiation_tool",
        schema={
            "name": "solar_radiation_tool",
            "description": (
                "Geometria solar (declinacion, ecuacion del tiempo, posicion del sol, "
                "amanecer/atardecer) e irradiancia de cielo despejado (modelo Hottel + "
                "Liu-Jordan) sobre superficie horizontal o inclinada (POA), incluyendo "
                "un optimizador de inclinacion fija (optimize_tilt) que barre beta para "
                "maximizar la energia diaria promedio anual o de un dia especifico. "
                "Formula cerrada, sin datos meteorologicos externos, asume cielo despejado."
            ),
            "inputSchema": SOLAR_RADIATION_TOOL_SCHEMA,
        },
        handler=lambda args: compute_solar_radiation(args.get("mode"), args),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    print(json.dumps(compute_solar_radiation("validate"), indent=2, ensure_ascii=False))
