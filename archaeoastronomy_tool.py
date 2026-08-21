#!/usr/bin/env python3
"""
archaeoastronomy_tool.py
Calculos astronomicos para datacion y analisis de alineamientos historicos:
posicion solar y lunar (algoritmos de baja precision de Jean Meeus,
"Astronomical Algorithms", validos aprox. 1000 a.C. - 3000 d.C. sin
necesidad de descargar efemerides externas), fecha de equinoccios y
solsticios para un ano dado, y verificacion de alineamientos arqueologicos
(dado un azimut de horizonte medido en un sitio, calcula la declinacion
correspondiente y la compara con las declinaciones extremas del sol/luna
para ese periodo historico).
Precision tipica: sol ~0.01 grados en longitud, luna ~0.2 grados - mas que
suficiente para verificar alineamientos arqueoastronomicos (escala de
grados, no de arcosegundos).
"""
import math


def julian_day(year, month, day, hour=12.0):
    """JD para calendario gregoriano/juliano proleptico (Meeus cap. 7)."""
    if month <= 2:
        year -= 1
        month += 12
    A = math.floor(year / 100)
    if (year, month, day) >= (1582, 10, 15):
        B = 2 - A + math.floor(A / 4)
    else:
        B = 0
    jd = (math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1))
          + day + hour / 24.0 + B - 1524.5)
    return jd


def _T(jd):
    return (jd - 2451545.0) / 36525.0


def solar_position(jd):
    """Longitud eclíptica aparente, oblicuidad y declinacion del sol
    (Meeus cap. 25, baja precision, error < 0.01 grados)."""
    T = _T(jd)
    L0 = (280.46646 + 36000.76983 * T + 0.0003032 * T ** 2) % 360.0
    M = (357.52911 + 35999.05029 * T - 0.0001537 * T ** 2) % 360.0
    Mr = math.radians(M)
    C = ((1.914602 - 0.004817 * T - 0.000014 * T ** 2) * math.sin(Mr)
         + (0.019993 - 0.000101 * T) * math.sin(2 * Mr)
         + 0.000289 * math.sin(3 * Mr))
    true_long = L0 + C
    omega = 125.04 - 1934.136 * T
    apparent_long = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))

    eps0 = (23 + 26 / 60 + 21.448 / 3600
            - (46.8150 * T + 0.00059 * T ** 2 - 0.001813 * T ** 3) / 3600)
    eps = eps0 + 0.00256 * math.cos(math.radians(omega))

    lam = math.radians(apparent_long)
    eps_r = math.radians(eps)
    ra = math.degrees(math.atan2(math.cos(eps_r) * math.sin(lam), math.cos(lam))) % 360.0
    dec = math.degrees(math.asin(math.sin(eps_r) * math.sin(lam)))

    return {
        "geometric_mean_longitude": round(L0, 6),
        "mean_anomaly": round(M, 6),
        "apparent_longitude": round(apparent_long, 6),
        "obliquity_ecliptic": round(eps, 6),
        "right_ascension": round(ra, 6),
        "declination": round(dec, 6),
    }


def lunar_position(jd):
    """Longitud, latitud eclipticas y declinacion de la luna (Meeus cap. 47,
    terminos periodicos principales, error tipico < 0.3 grados)."""
    T = _T(jd)
    Lp = (218.3164477 + 481267.88123421 * T - 0.0015786 * T ** 2) % 360.0
    D = (297.8501921 + 445267.1114034 * T - 0.0018819 * T ** 2) % 360.0
    M = (357.5291092 + 35999.0502909 * T - 0.0001536 * T ** 2) % 360.0
    Mp = (134.9633964 + 477198.8675055 * T + 0.0089970 * T ** 2) % 360.0
    F = (93.2720950 + 483202.0175233 * T - 0.0036539 * T ** 2) % 360.0

    Dr, Mr, Mpr, Fr = (math.radians(x) for x in (D, M, Mp, F))

    dL = (6.288774 * math.sin(Mpr)
          + 1.274027 * math.sin(2 * Dr - Mpr)
          + 0.658314 * math.sin(2 * Dr)
          + 0.213618 * math.sin(2 * Mpr)
          - 0.185116 * math.sin(Mr)
          - 0.114332 * math.sin(2 * Fr))
    dB = (5.128122 * math.sin(Fr)
          + 0.280602 * math.sin(Mpr + Fr)
          + 0.277693 * math.sin(Mpr - Fr)
          + 0.173237 * math.sin(2 * Dr - Fr))

    lon = (Lp + dL) % 360.0
    lat = dB

    eps = 23.4392911 - 0.0130042 * T
    eps_r = math.radians(eps)
    lon_r, lat_r = math.radians(lon), math.radians(lat)

    ra = math.degrees(math.atan2(
        math.sin(lon_r) * math.cos(eps_r) - math.tan(lat_r) * math.sin(eps_r),
        math.cos(lon_r))) % 360.0
    dec = math.degrees(math.asin(
        math.sin(lat_r) * math.cos(eps_r) + math.cos(lat_r) * math.sin(eps_r) * math.sin(lon_r)))

    return {
        "mean_longitude": round(Lp, 6),
        "ecliptic_longitude": round(lon, 6),
        "ecliptic_latitude": round(lat, 6),
        "right_ascension": round(ra, 6),
        "declination": round(dec, 6),
        "note": "terminos periodicos principales (subconjunto de ELP2000); precision tipica < 0.3 grados",
    }


def _solar_longitude_at(jd):
    return solar_position(jd)["apparent_longitude"] % 360.0


def _find_longitude_crossing(year, target_long, jd_guess, max_iter=30):
    jd = jd_guess
    for _ in range(max_iter):
        lam = _solar_longitude_at(jd)
        diff = ((target_long - lam + 180) % 360) - 180
        if abs(diff) < 1e-6:
            break
        jd += diff / 0.9856002
    return jd


def _jd_to_calendar(jd):
    jd = jd + 0.5
    Z = math.floor(jd)
    F = jd - Z
    if Z < 2299161:
        A = Z
    else:
        alpha = math.floor((Z - 1867216.25) / 36524.25)
        A = Z + 1 + alpha - math.floor(alpha / 4)
    B = A + 1524
    C = math.floor((B - 122.1) / 365.25)
    D = math.floor(365.25 * C)
    E = math.floor((B - D) / 30.6001)
    day = B - D - math.floor(30.6001 * E) + F
    month = E - 1 if E < 14 else E - 13
    year = C - 4716 if month > 2 else C - 4715
    day_int = int(math.floor(day))
    hour = (day - day_int) * 24.0
    return int(year), int(month), day_int, round(hour, 4)


def compute_equinox_solstice(year, event="all"):
    events = {
        "march_equinox": 0.0,
        "june_solstice": 90.0,
        "september_equinox": 180.0,
        "december_solstice": 270.0,
    }
    approx_month_day = {
        "march_equinox": (3, 20),
        "june_solstice": (6, 21),
        "september_equinox": (9, 22),
        "december_solstice": (12, 21),
    }
    to_compute = events.keys() if event == "all" else [event]
    if event != "all" and event not in events:
        raise ValueError(f"event debe ser uno de {list(events.keys())} o 'all'")

    results = {}
    for name in to_compute:
        m, d = approx_month_day[name]
        jd_guess = julian_day(year, m, d)
        jd = _find_longitude_crossing(year, events[name], jd_guess)
        y, mo, day, hour = _jd_to_calendar(jd)
        results[name] = {
            "julian_day": round(jd, 5),
            "calendar_date_utc": f"{y:05d}-{mo:02d}-{day:02d}",
            "hour_utc": hour,
        }
    return {
        "mode": "equinox_solstice",
        "year": year,
        "calendar_note": (
            "calendario juliano proleptico para year < 1582-10-15, "
            "gregoriano en caso contrario; year negativo = a.C. astronomico (0 = 1 a.C.)"
        ),
        "events": results,
    }


def _rise_set_azimuth(latitude_deg, declination_deg):
    phi = math.radians(latitude_deg)
    delta = math.radians(declination_deg)
    h0 = math.radians(-0.8333)
    cos_H0 = (math.sin(h0) - math.sin(phi) * math.sin(delta)) / (math.cos(phi) * math.cos(delta))
    if cos_H0 > 1 or cos_H0 < -1:
        return None
    H0 = math.acos(cos_H0)
    alt_at_H0 = math.asin(math.sin(phi) * math.sin(delta) + math.cos(phi) * math.cos(delta) * math.cos(H0))
    cos_az = (math.sin(delta) - math.sin(phi) * math.sin(alt_at_H0)) / (math.cos(phi) * math.cos(alt_at_H0))
    cos_az = max(-1.0, min(1.0, cos_az))
    az_rise = math.degrees(math.acos(cos_az))
    az_set = 360.0 - az_rise
    return az_rise, az_set


def compute_alignment_check(latitude, azimuth, year, body="sun", tolerance_deg=1.0):
    phi = math.radians(latitude)
    az = math.radians(azimuth)
    h0 = math.radians(-0.8333)

    sin_delta = math.sin(phi) * math.sin(h0) + math.cos(phi) * math.cos(h0) * math.cos(az)
    implied_declination = math.degrees(math.asin(max(-1.0, min(1.0, sin_delta))))

    candidates = {}
    if body in ("sun", "both"):
        candidates["june_solstice_sun_declination"] = 23.436 - 0.0000004 * (year - 2000)
        candidates["december_solstice_sun_declination"] = -candidates["june_solstice_sun_declination"]
        candidates["equinox_sun_declination"] = 0.0
    if body in ("moon", "both"):
        eps = 23.4392911
        i_moon = 5.145
        candidates["major_lunar_standstill_declination"] = eps + i_moon
        candidates["minor_lunar_standstill_declination"] = eps - i_moon
        candidates["neg_major_lunar_standstill_declination"] = -(eps + i_moon)
        candidates["neg_minor_lunar_standstill_declination"] = -(eps - i_moon)

    matches = []
    for name, dec in candidates.items():
        diff = abs(implied_declination - dec)
        if diff <= tolerance_deg:
            matches.append({"event": name, "declination": round(dec, 4), "difference_deg": round(diff, 4)})

    return {
        "mode": "alignment_check",
        "latitude": latitude,
        "azimuth": azimuth,
        "year": year,
        "implied_declination": round(implied_declination, 4),
        "tolerance_deg": tolerance_deg,
        "candidate_declinations": {k: round(v, 4) for k, v in candidates.items()},
        "matches_within_tolerance": matches,
        "interpretation": (
            "alineamiento_astronomico_consistente" if matches else
            "sin_correspondencia_clara_con_eventos_solares_lunares_estandar"
        ),
    }


def validate():
    """Checks anclados a valores astronomicos reales conocidos, verificados
    de antemano contra el algoritmo de Meeus antes de escribir este patch."""
    checks = []

    # --- JD de J2000.0, epoca de referencia estandar ---
    jd_j2000 = julian_day(2000, 1, 1, 12.0)
    checks.append({
        "name": "julian_day_epoca_j2000_exacta",
        "expected": 2451545.0, "actual": jd_j2000,
        "passed": bool(abs(jd_j2000 - 2451545.0) < 1e-9),
    })

    # --- oblicuidad eclíptica en J2000.0 cerca del valor IAU conocido ---
    sp = solar_position(2451545.0)
    eps = sp["obliquity_ecliptic"]
    checks.append({
        "name": "obliquidad_eclíptica_j2000_cerca_de_valor_iau",
        "expected_approx": 23.4392911, "actual": eps, "diff": abs(eps - 23.4392911),
        "passed": bool(abs(eps - 23.4392911) < 0.02),
    })

    # --- equinoccios/solsticios 2000 coinciden con fechas reales conocidas ---
    eq2000 = compute_equinox_solstice(2000, "all")
    known_real = {
        "march_equinox": ("02000-03-20", 7.35),
        "june_solstice": ("02000-06-21", 1.80),
        "september_equinox": ("02000-09-22", 17.47),
        "december_solstice": ("02000-12-21", 13.62),
    }
    eq_checks = []
    all_eq_ok = True
    for name, (expected_date, expected_hour) in known_real.items():
        got = eq2000["events"][name]
        date_ok = got["calendar_date_utc"] == expected_date
        hour_diff = abs(got["hour_utc"] - expected_hour)
        hour_ok = hour_diff < 1.5
        ok = date_ok and hour_ok
        all_eq_ok = all_eq_ok and ok
        eq_checks.append({"event": name, "expected_date": expected_date, "got_date": got["calendar_date_utc"],
                           "expected_hour": expected_hour, "got_hour": got["hour_utc"], "passed": ok})
    checks.append({
        "name": "equinoccios_solsticios_2000_coinciden_con_fechas_reales",
        "detail": eq_checks,
        "passed": bool(all_eq_ok),
    })

    # --- alignment_check autoconsistente con _rise_set_azimuth ---
    lat_test, dec_test = 45.0, 23.436
    rs = _rise_set_azimuth(lat_test, dec_test)
    az_rise = rs[0] if rs else None
    round_trip_diff = None
    round_trip_ok = False
    if az_rise is not None:
        back = compute_alignment_check(lat_test, az_rise, 2000, body="sun", tolerance_deg=0.01)
        round_trip_diff = abs(back["implied_declination"] - dec_test)
        round_trip_ok = round_trip_diff < 1e-6
    checks.append({
        "name": "alignment_check_autoconsistente_con_rise_set_azimuth",
        "latitude": lat_test, "declination_original": dec_test, "azimuth_calculado": az_rise,
        "declination_recuperada_diff": round_trip_diff,
        "passed": bool(round_trip_ok),
    })

    # --- declinacion lunar dentro del limite fisico conocido (~28.6 grados) ---
    decs = []
    for y in range(1990, 2010):
        for m in range(1, 13, 3):
            jd = julian_day(y, m, 15)
            decs.append(lunar_position(jd)["declination"])
    max_abs_dec = max(abs(d) for d in decs)
    checks.append({
        "name": "declinacion_lunar_dentro_de_limite_fisico_conocido",
        "max_abs_declination_observada": round(max_abs_dec, 4), "limite_fisico_esperado": 28.7,
        "passed": bool(max_abs_dec < 28.7),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_archaeoastronomy(mode, **kwargs):
    if mode == "solar_position":
        jd = kwargs.get("julian_day")
        if jd is None:
            jd = julian_day(kwargs["year"], kwargs["month"], kwargs["day"], kwargs.get("hour", 12.0))
        result = solar_position(jd)
        result["mode"] = "solar_position"
        result["julian_day"] = round(jd, 5)
        return result
    elif mode == "lunar_position":
        jd = kwargs.get("julian_day")
        if jd is None:
            jd = julian_day(kwargs["year"], kwargs["month"], kwargs["day"], kwargs.get("hour", 12.0))
        result = lunar_position(jd)
        result["mode"] = "lunar_position"
        result["julian_day"] = round(jd, 5)
        return result
    elif mode == "equinox_solstice":
        return compute_equinox_solstice(kwargs["year"], kwargs.get("event", "all"))
    elif mode == "alignment_check":
        return compute_alignment_check(
            kwargs["latitude"], kwargs["azimuth"], kwargs["year"],
            body=kwargs.get("body", "sun"), tolerance_deg=kwargs.get("tolerance_deg", 1.0),
        )
    elif mode == "julian_day":
        jd = julian_day(kwargs["year"], kwargs["month"], kwargs["day"], kwargs.get("hour", 12.0))
        return {"mode": "julian_day", "year": kwargs["year"], "month": kwargs["month"],
                "day": kwargs["day"], "hour": kwargs.get("hour", 12.0), "julian_day": round(jd, 5)}
    elif mode == "validate":
        return validate()
    else:
        raise ValueError(f"modo desconocido: {mode}")


ARCHAEOASTRONOMY_TOOL_SCHEMA = {
    "name": "archaeoastronomy",
    "description": (
        "Calculos astronomicos para datacion y arqueoastronomia via "
        "algoritmos de Meeus (baja precision, sin efemerides externas): "
        "posicion solar y lunar (longitud eclíptica, ascension recta, "
        "declinacion) para cualquier fecha desde ~1000 a.C., fecha de "
        "equinoccios/solsticios de un ano dado, conversion a dia juliano, "
        "y verificacion de alineamientos arqueologicos (dado azimut y "
        "latitud de un sitio, calcula la declinacion implicada y la "
        "compara contra solsticios/lunisticios)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["solar_position", "lunar_position", "equinox_solstice", "alignment_check", "julian_day", "validate"],
            },
            "year": {"type": "integer", "description": "todos los modos excepto julian_day directo; negativo = a.C. astronomico"},
            "month": {"type": "integer"},
            "day": {"type": "integer"},
            "hour": {"type": "number", "description": "hora UTC decimal, default 12.0"},
            "julian_day": {"type": "number", "description": "alternativa directa a year/month/day para solar_position, lunar_position"},
            "event": {"type": "string", "enum": ["march_equinox", "june_solstice", "september_equinox", "december_solstice", "all"], "description": "equinox_solstice, default 'all'"},
            "latitude": {"type": "number", "description": "alignment_check, grados, positivo=N"},
            "azimuth": {"type": "number", "description": "alignment_check, grados desde el norte, medido en el sitio"},
            "body": {"type": "string", "enum": ["sun", "moon", "both"], "description": "alignment_check, default 'sun'"},
            "tolerance_deg": {"type": "number", "description": "alignment_check, default 1.0"},
        },
        "required": ["mode"],
    },
}

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("archaeoastronomy", ARCHAEOASTRONOMY_TOOL_SCHEMA, lambda args, _f=compute_archaeoastronomy: _f(**args))
