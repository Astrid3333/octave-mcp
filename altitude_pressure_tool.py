import math

# ---------------------------------------------------------------------
# constantes ISA (Atmosfera Estandar Internacional)
# ---------------------------------------------------------------------

P0 = 101325.0        # Pa, presion a nivel del mar
T0 = 288.15           # K, temperatura a nivel del mar
L = 0.0065            # K/m, gradiente termico (troposfera, 0-11 km)
R = 8.31446           # J/(mol K)
G = 9.80665           # m/s^2
M = 0.0289644         # kg/mol
ALT_TROPOPAUSA = 11000.0  # m, limite superior de la troposfera en el modelo ISA
ALT_ESTRATOPAUSA = 20000.0  # m, limite superior de la 2da capa estratosferica modelada

WGS84_A = 6378137.0            # semieje mayor, m
WGS84_F = 1 / 298.257223563    # achatamiento
WGS84_E2 = WGS84_F * (2 - WGS84_F)  # excentricidad al cuadrado


# ---------------------------------------------------------------------
# presion atmosferica (modelo ISA)
# ---------------------------------------------------------------------

def _presion_isa(alt_m):
    if alt_m <= ALT_TROPOPAUSA:
        presion_pa = P0 * (1 - (L * alt_m) / T0) ** (G * M / (R * L))
        temp_k = T0 - L * alt_m
    elif alt_m <= ALT_ESTRATOPAUSA:
        t11 = T0 - L * ALT_TROPOPAUSA
        p11 = P0 * (1 - (L * ALT_TROPOPAUSA) / T0) ** (G * M / (R * L))
        presion_pa = p11 * math.exp(-G * M * (alt_m - ALT_TROPOPAUSA) / (R * t11))
        temp_k = t11
    else:
        raise ValueError(
            f"altitud_m={alt_m} fuera de rango soportado por este modelo "
            f"(valido hasta {ALT_ESTRATOPAUSA} m)"
        )
    return presion_pa, temp_k


def _calc_presion(params):
    alt_m = params.get("altitud_m")
    if alt_m is None:
        raise ValueError("params.altitud_m es requerido")
    presion_pa, temp_k = _presion_isa(alt_m)
    return {
        "altitud_m": alt_m,
        "presion_pa": presion_pa,
        "presion_hpa": presion_pa / 100.0,
        "temperatura_k": temp_k,
        "temperatura_c": temp_k - 273.15,
    }


# ---------------------------------------------------------------------
# conversion de coordenadas geodesicas <-> ECEF (WGS84)
# ---------------------------------------------------------------------

def _geodetic_to_ecef(lat_deg, lon_deg, alt_m):
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    n = WGS84_A / math.sqrt(1 - WGS84_E2 * sin_lat ** 2)
    x = (n + alt_m) * cos_lat * math.cos(lon)
    y = (n + alt_m) * cos_lat * math.sin(lon)
    z = (n * (1 - WGS84_E2) + alt_m) * sin_lat
    return x, y, z


def _ecef_to_geodetic(x, y, z):
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - WGS84_E2))
    for _ in range(6):
        sin_lat = math.sin(lat)
        n = WGS84_A / math.sqrt(1 - WGS84_E2 * sin_lat ** 2)
        alt = p / math.cos(lat) - n
        lat = math.atan2(z, p * (1 - WGS84_E2 * n / (n + alt)))
    sin_lat = math.sin(lat)
    n = WGS84_A / math.sqrt(1 - WGS84_E2 * sin_lat ** 2)
    alt = p / math.cos(lat) - n
    return math.degrees(lat), math.degrees(lon), alt


def _calc_geodetic2ecef(params):
    lat = params.get("latitud")
    lon = params.get("longitud")
    alt_m = params.get("altitud_m")
    if lat is None or lon is None or alt_m is None:
        raise ValueError("params requiere latitud, longitud y altitud_m")
    x, y, z = _geodetic_to_ecef(lat, lon, alt_m)
    return {"x": x, "y": y, "z": z}


def _calc_ecef2geodetic(params):
    x = params.get("x")
    y = params.get("y")
    z = params.get("z")
    if x is None or y is None or z is None:
        raise ValueError("params requiere x, y, z")
    lat, lon, alt_m = _ecef_to_geodetic(x, y, z)
    return {"latitud": lat, "longitud": lon, "altitud_m": alt_m}


# ---------------------------------------------------------------------
# combinado: coordenadas + presion en un solo llamado
# ---------------------------------------------------------------------

def _calc_altitud_presion(params):
    lat = params.get("latitud")
    lon = params.get("longitud")
    alt_m = params.get("altitud_m")
    if lat is None or lon is None or alt_m is None:
        raise ValueError("params requiere latitud, longitud y altitud_m")

    presion = _calc_presion({"altitud_m": alt_m})
    x, y, z = _geodetic_to_ecef(lat, lon, alt_m)

    return {
        "latitud": lat,
        "longitud": lon,
        "altitud_m": alt_m,
        "presion_pa": presion["presion_pa"],
        "presion_hpa": presion["presion_hpa"],
        "temperatura_c": presion["temperatura_c"],
        "ecef": {"x": x, "y": y, "z": z},
    }


# ---------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------

def _validate():
    checks = {}

    # (a) presion a nivel del mar debe dar exactamente P0
    r0 = _calc_presion({"altitud_m": 0})
    checks["presion_nivel_mar_101325pa"] = {
        "cumple": abs(r0["presion_pa"] - P0) < 1e-6,
        "valor": round(r0["presion_pa"], 6),
    }

    # (b) presion a 2500m debe estar cerca del valor tabulado real (~747 hPa)
    r2500 = _calc_presion({"altitud_m": 2500})
    checks["presion_2500m_cerca_747hpa"] = {
        "cumple": abs(r2500["presion_hpa"] - 747.0) < 2.0,
        "valor": round(r2500["presion_hpa"], 3),
    }

    # (c) presion en la tropopausa (11000m) debe estar cerca de 226.3 hPa (valor tabulado ISA)
    r11000 = _calc_presion({"altitud_m": 11000})
    checks["presion_11000m_cerca_226hpa"] = {
        "cumple": abs(r11000["presion_hpa"] - 226.3) < 1.0,
        "valor": round(r11000["presion_hpa"], 3),
    }

    # (d) monotonia: la presion debe decrecer estrictamente con la altitud
    presiones = [_calc_presion({"altitud_m": a})["presion_pa"] for a in (0, 1000, 5000, 11000, 15000, 20000)]
    monotona = all(presiones[i] > presiones[i + 1] for i in range(len(presiones) - 1))
    checks["presion_monotona_decreciente"] = {"cumple": monotona, "valor": [round(p, 2) for p in presiones]}

    # (e) roundtrip geodetic -> ecef -> geodetic debe ser identidad (Nueva York, 2500m)
    lat0, lon0, alt0 = 40.7, -74.0, 2500.0
    x, y, z = _geodetic_to_ecef(lat0, lon0, alt0)
    lat1, lon1, alt1 = _ecef_to_geodetic(x, y, z)
    checks["roundtrip_geodetic_ecef_lat"] = {"cumple": abs(lat1 - lat0) < 1e-6, "valor": round(lat1, 8)}
    checks["roundtrip_geodetic_ecef_lon"] = {"cumple": abs(lon1 - lon0) < 1e-6, "valor": round(lon1, 8)}
    checks["roundtrip_geodetic_ecef_alt"] = {"cumple": abs(alt1 - alt0) < 1e-3, "valor": round(alt1, 6)}

    # (f) nivel del mar en el ecuador, longitud 0 -> ECEF debe caer sobre el eje x, con |x| ~= WGS84_A
    x_eq, y_eq, z_eq = _geodetic_to_ecef(0.0, 0.0, 0.0)
    checks["ecuador_lon0_x_igual_semieje_mayor"] = {
        "cumple": abs(x_eq - WGS84_A) < 1e-3,
        "valor": round(x_eq, 6),
    }
    checks["ecuador_lon0_y_z_cero"] = {
        "cumple": abs(y_eq) < 1e-6 and abs(z_eq) < 1e-6,
        "valor": [round(y_eq, 8), round(z_eq, 8)],
    }

    # (g) altitud fuera de rango debe levantar error controlado
    try:
        _calc_presion({"altitud_m": 25000})
        fuera_de_rango_ok = False
    except ValueError:
        fuera_de_rango_ok = True
    checks["altitud_fuera_de_rango_levanta_error"] = {"cumple": fuera_de_rango_ok, "valor": fuera_de_rango_ok}

    all_pass = all(c["cumple"] for c in checks.values())
    return {"mode": "validate", "checks": checks, "validation_passed": all_pass}


# ---------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------

def compute_altitude_pressure(mode="altitud_presion", params=None):
    params = params or {}
    if mode == "presion":
        return _calc_presion(params)
    elif mode == "geodetic2ecef":
        return _calc_geodetic2ecef(params)
    elif mode == "ecef2geodetic":
        return _calc_ecef2geodetic(params)
    elif mode == "altitud_presion":
        return _calc_altitud_presion(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            f"mode desconocido: {mode!r}. Usar: presion | geodetic2ecef | ecef2geodetic | altitud_presion | validate"
        )


ALTITUDE_PRESSURE_TOOL_SCHEMA = {
    "name": "altitude_pressure_tool",
    "description": (
        "Calculos de presion atmosferica por altitud (modelo ISA, valido hasta 20000m) "
        "y conversion de coordenadas geodesicas WGS84 <-> ECEF. "
        "mode='presion': params={altitud_m}. "
        "mode='geodetic2ecef': params={latitud,longitud,altitud_m}. "
        "mode='ecef2geodetic': params={x,y,z}. "
        "mode='altitud_presion': params={latitud,longitud,altitud_m} devuelve presion + ECEF juntos."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["presion", "geodetic2ecef", "ecef2geodetic", "altitud_presion", "validate"],
                "default": "altitud_presion",
            },
            "params": {"type": "object"},
        },
    },
}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_altitude_pressure("validate"), indent=2, ensure_ascii=False))


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool(
    "altitude_pressure_tool",
    ALTITUDE_PRESSURE_TOOL_SCHEMA,
    lambda args: compute_altitude_pressure(args.get("mode", "altitud_presion"), args.get("params")),
)
