"""
geodetic_coord_tool.py

Conversion de coordenadas geodesicas: LLA (lat/lon/altura) <-> ECEF <-> AER
(Azimuth-Elevation-Range) respecto de un punto de referencia local (ENU).

Elipsoide por defecto: WGS84. Tambien soporta GRS80 (SIRGAS, usado en Chile)
pasando ellipsoid="GRS80".

Sigue el patron de dispatch usado en octave-mcp: una funcion de entrada que
recibe un dict de parametros con "mode" (o via source_tool/params en el
harness de validacion), y devuelve un dict con resultados o con el reporte
de mode="validate".
"""

import math

# ---------------------------------------------------------------------------
# Definiciones de elipsoides (semieje mayor a [m], achatamiento f)
# ---------------------------------------------------------------------------
ELLIPSOIDS = {
    "WGS84": {"a": 6378137.0, "f": 1.0 / 298.257223563},
    "GRS80": {"a": 6378137.0, "f": 1.0 / 298.257222101},
}


def _ellipsoid_params(name):
    name = (name or "WGS84").upper()
    if name not in ELLIPSOIDS:
        raise ValueError(
            f"Elipsoide desconocido: {name}. Opciones: {list(ELLIPSOIDS.keys())}"
        )
    a = ELLIPSOIDS[name]["a"]
    f = ELLIPSOIDS[name]["f"]
    b = a * (1 - f)
    e2 = f * (2 - f)  # excentricidad al cuadrado
    return a, b, e2


# ---------------------------------------------------------------------------
# LLA -> ECEF
# ---------------------------------------------------------------------------
def lla_to_ecef(lat_deg, lon_deg, h, ellipsoid="WGS84"):
    a, b, e2 = _ellipsoid_params(ellipsoid)
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)

    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)

    N = a / math.sqrt(1 - e2 * sin_lat * sin_lat)  # radio de curvatura primer vertical

    x = (N + h) * cos_lat * math.cos(lon)
    y = (N + h) * cos_lat * math.sin(lon)
    z = (N * (1 - e2) + h) * sin_lat

    return x, y, z


# ---------------------------------------------------------------------------
# ECEF -> LLA (formula cerrada de Heikkinen, sin iteracion)
# ---------------------------------------------------------------------------
def ecef_to_lla(x, y, z, ellipsoid="WGS84"):
    a, b, e2 = _ellipsoid_params(ellipsoid)
    ep2 = (a * a - b * b) / (b * b)  # segunda excentricidad al cuadrado

    p = math.sqrt(x * x + y * y)

    # Casos degenerados (polo)
    if p < 1e-12:
        lat = math.copysign(math.pi / 2, z) if z != 0 else 0.0
        lon = 0.0
        h = abs(z) - b
        return math.degrees(lat), math.degrees(lon), h

    theta = math.atan2(z * a, p * b)
    sin_theta = math.sin(theta)
    cos_theta = math.cos(theta)

    lat = math.atan2(
        z + ep2 * b * sin_theta ** 3,
        p - e2 * a * cos_theta ** 3,
    )
    lon = math.atan2(y, x)

    sin_lat = math.sin(lat)
    N = a / math.sqrt(1 - e2 * sin_lat * sin_lat)
    h = p / math.cos(lat) - N

    return math.degrees(lat), math.degrees(lon), h


# ---------------------------------------------------------------------------
# ECEF (o LLA) -> ENU / AER relativo a un punto de referencia
# ---------------------------------------------------------------------------
def ecef_to_enu(x, y, z, ref_lat_deg, ref_lon_deg, ref_h, ellipsoid="WGS84"):
    ref_x, ref_y, ref_z = lla_to_ecef(ref_lat_deg, ref_lon_deg, ref_h, ellipsoid)

    dx = x - ref_x
    dy = y - ref_y
    dz = z - ref_z

    lat = math.radians(ref_lat_deg)
    lon = math.radians(ref_lon_deg)

    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)

    # Matriz de rotacion ECEF -> ENU
    e = -sin_lon * dx + cos_lon * dy
    n = -sin_lat * cos_lon * dx - sin_lat * sin_lon * dy + cos_lat * dz
    u = cos_lat * cos_lon * dx + cos_lat * sin_lon * dy + sin_lat * dz

    return e, n, u


def enu_to_aer(e, n, u):
    r = math.sqrt(e * e + n * n + u * u)
    az = math.degrees(math.atan2(e, n)) % 360.0
    el = math.degrees(math.asin(u / r)) if r > 1e-12 else 0.0
    return az, el, r


def lla_to_aer(lat_deg, lon_deg, h, ref_lat_deg, ref_lon_deg, ref_h, ellipsoid="WGS84"):
    x, y, z = lla_to_ecef(lat_deg, lon_deg, h, ellipsoid)
    e, n, u = ecef_to_enu(x, y, z, ref_lat_deg, ref_lon_deg, ref_h, ellipsoid)
    return enu_to_aer(e, n, u)


# ---------------------------------------------------------------------------
# Dispatch principal
# ---------------------------------------------------------------------------
def geodetic_coord_tool(params: dict) -> dict:
    """
    params esperado:
      conversion: "lla_to_ecef" | "ecef_to_lla" | "lla_to_aer" | "ecef_to_enu" | "enu_to_aer"
      ellipsoid: "WGS84" (default) | "GRS80"
      + los campos numericos segun la conversion elegida
    """
    conversion = params.get("conversion")
    ellipsoid = params.get("ellipsoid", "WGS84")

    if conversion == "lla_to_ecef":
        x, y, z = lla_to_ecef(
            params["lat_deg"], params["lon_deg"], params["h"], ellipsoid
        )
        return {"x": x, "y": y, "z": z, "ellipsoid": ellipsoid}

    elif conversion == "ecef_to_lla":
        lat, lon, h = ecef_to_lla(params["x"], params["y"], params["z"], ellipsoid)
        return {"lat_deg": lat, "lon_deg": lon, "h": h, "ellipsoid": ellipsoid}

    elif conversion == "ecef_to_enu":
        e, n, u = ecef_to_enu(
            params["x"], params["y"], params["z"],
            params["ref_lat_deg"], params["ref_lon_deg"], params["ref_h"],
            ellipsoid,
        )
        return {"e": e, "n": n, "u": u, "ellipsoid": ellipsoid}

    elif conversion == "enu_to_aer":
        az, el, r = enu_to_aer(params["e"], params["n"], params["u"])
        return {"azimuth_deg": az, "elevation_deg": el, "range_m": r}

    elif conversion == "lla_to_aer":
        az, el, r = lla_to_aer(
            params["lat_deg"], params["lon_deg"], params["h"],
            params["ref_lat_deg"], params["ref_lon_deg"], params["ref_h"],
            ellipsoid,
        )
        return {"azimuth_deg": az, "elevation_deg": el, "range_m": r, "ellipsoid": ellipsoid}

    elif params.get("mode") == "validate" or conversion == "validate":
        return _validate()

    else:
        raise ValueError(
            "conversion invalida. Opciones: lla_to_ecef, ecef_to_lla, "
            "ecef_to_enu, enu_to_aer, lla_to_aer, validate"
        )


# ---------------------------------------------------------------------------
# Modo validate
# ---------------------------------------------------------------------------
def _validate():
    checks = []

    # 1) Round-trip LLA -> ECEF -> LLA en un punto cercano a Castro, Chiloe
    lat0, lon0, h0 = -42.4827, -73.7649, 30.0
    x, y, z = lla_to_ecef(lat0, lon0, h0)
    lat1, lon1, h1 = ecef_to_lla(x, y, z)

    err_lat = abs(lat1 - lat0)
    err_lon = abs(lon1 - lon0)
    err_h = abs(h1 - h0)

    checks.append({
        "name": "roundtrip_lla_ecef_lla_castro",
        "passed": err_lat < 1e-8 and err_lon < 1e-8 and err_h < 1e-6,
        "err_lat_deg": err_lat,
        "err_lon_deg": err_lon,
        "err_h_m": err_h,
    })

    # 2) Punto conocido en el ecuador, altura 0 -> ECEF esperado (a, 0, 0)
    a, _, _ = _ellipsoid_params("WGS84")
    x2, y2, z2 = lla_to_ecef(0.0, 0.0, 0.0)
    checks.append({
        "name": "equator_prime_meridian",
        "passed": abs(x2 - a) < 1e-3 and abs(y2) < 1e-6 and abs(z2) < 1e-6,
        "x": x2, "y": y2, "z": z2, "expected_x": a,
    })

    # 3) Polo norte, altura 0 -> ECEF esperado (0, 0, b)
    _, b, _ = _ellipsoid_params("WGS84")
    x3, y3, z3 = lla_to_ecef(90.0, 0.0, 0.0)
    checks.append({
        "name": "north_pole",
        "passed": abs(x3) < 1e-6 and abs(y3) < 1e-6 and abs(z3 - b) < 1e-3,
        "x": x3, "y": y3, "z": z3, "expected_z": b,
    })

    # 4) AER: un punto directamente "arriba" del origen (mismo lat/lon, mas altura)
    #    debe dar elevacion ~90 grados
    az, el, r = lla_to_aer(
        lat0, lon0, h0 + 1000.0,
        lat0, lon0, h0,
    )
    checks.append({
        "name": "straight_up_elevation_90",
        "passed": abs(el - 90.0) < 1e-3 and abs(r - 1000.0) < 1e-1,
        "elevation_deg": el,
        "range_m": r,
    })

    # 5) AER: punto al norte del origen -> azimuth ~0 grados
    az2, el2, r2 = lla_to_aer(
        lat0 + 0.01, lon0, h0,
        lat0, lon0, h0,
    )
    checks.append({
        "name": "north_point_azimuth_0",
        "passed": abs(az2 - 0.0) < 1.0 or abs(az2 - 360.0) < 1.0,
        "azimuth_deg": az2,
    })

    # 6) GRS80 funciona sin explotar (usado en SIRGAS / Chile)
    xg, yg, zg = lla_to_ecef(lat0, lon0, h0, ellipsoid="GRS80")
    latg, long_, hg = ecef_to_lla(xg, yg, zg, ellipsoid="GRS80")
    checks.append({
        "name": "grs80_roundtrip",
        "passed": abs(latg - lat0) < 1e-8 and abs(long_ - lon0) < 1e-8 and abs(hg - h0) < 1e-6,
    })

    all_passed = all(c["passed"] for c in checks)
    return {
        "mode": "validate",
        "tool": "geodetic_coord_tool",
        "all_passed": all_passed,
        "checks": checks,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(geodetic_coord_tool({"mode": "validate"}), indent=2))
