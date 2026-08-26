"""
isa_atmosphere_tool.py

Modelo de la Atmosfera Estandar Internacional (ISA / ICAO 1993) por capas,
0 a 84852 m de altitud geopotencial. Devuelve presion, temperatura, densidad
y velocidad del sonido para una altitud dada.

Util para cualquier tool que dependa de altitud: wildfire_risk_tool, drones,
correccion barometrica, radiacion solar a altura, etc.
"""

import math

# ---------------------------------------------------------------------------
# Constantes ISA
# ---------------------------------------------------------------------------
G0 = 9.80665        # gravedad estandar [m/s^2]
R = 287.05287       # constante especifica del aire seco [J/(kg*K)]
GAMMA = 1.4         # indice adiabatico del aire

T0 = 288.15         # temperatura a nivel del mar [K]
P0 = 101325.0       # presion a nivel del mar [Pa]
RHO0 = 1.225        # densidad a nivel del mar [kg/m^3]

# Capas ISA: (altitud base [m], temperatura base [K], lapse rate [K/m])
# lapse rate > 0 significa que la temperatura DISMINUYE con la altura
LAYERS = [
    (0.0, 288.15, 0.0065),
    (11000.0, 216.65, 0.0),
    (20000.0, 216.65, -0.0010),
    (32000.0, 228.65, -0.0028),
    (47000.0, 270.65, 0.0),
    (51000.0, 270.65, 0.0028),
    (71000.0, 214.65, 0.0020),
    (84852.0, 186.946, None),  # techo del modelo
]


def _layer_for_altitude(h):
    for i in range(len(LAYERS) - 1):
        base_h, base_t, lapse = LAYERS[i]
        next_h = LAYERS[i + 1][0]
        if base_h <= h <= next_h or (i == len(LAYERS) - 2 and h > next_h):
            return i, base_h, base_t, lapse
    # por debajo de 0: extrapola con la primera capa
    return 0, LAYERS[0][0], LAYERS[0][1], LAYERS[0][2]


def _pressure_at_base(layer_index):
    """Presion acumulada en la base de cada capa, integrando capa por capa."""
    p = P0
    for i in range(layer_index):
        base_h, base_t, lapse = LAYERS[i]
        next_h = LAYERS[i + 1][0]
        dh = next_h - base_h
        if lapse != 0:
            t_next = base_t - lapse * dh
            p = p * (t_next / base_t) ** (G0 / (R * lapse))
        else:
            p = p * math.exp(-G0 * dh / (R * base_t))
    return p


def isa_properties(h):
    """
    h: altitud geopotencial en metros (0 <= h <= 84852 recomendado；
       se extrapola fuera de rango con advertencia implicita).
    Devuelve dict con temperature_k, pressure_pa, density_kg_m3, speed_of_sound_ms.
    """
    idx, base_h, base_t, lapse = _layer_for_altitude(h)
    base_p = _pressure_at_base(idx)
    dh = h - base_h

    if lapse != 0 and lapse is not None:
        t = base_t - lapse * dh
        p = base_p * (t / base_t) ** (G0 / (R * lapse))
    else:
        t = base_t
        p = base_p * math.exp(-G0 * dh / (R * base_t))

    rho = p / (R * t)
    a = math.sqrt(GAMMA * R * t)

    return {
        "altitude_m": h,
        "temperature_k": t,
        "temperature_c": t - 273.15,
        "pressure_pa": p,
        "pressure_hpa": p / 100.0,
        "density_kg_m3": rho,
        "speed_of_sound_ms": a,
    }


def pressure_altitude(p_target, h_guess=0.0, tol=1e-6, max_iter=100):
    """Inversion numerica simple: dada una presion, encontrar la altitud (bisection)."""
    lo, hi = -5000.0, 84852.0
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        p_mid = isa_properties(mid)["pressure_pa"]
        if abs(p_mid - p_target) < tol * p_target:
            return mid
        # presion decrece monotonicamente con la altura
        if p_mid > p_target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# ---------------------------------------------------------------------------
# Dispatch principal
# ---------------------------------------------------------------------------
def isa_atmosphere_tool(params: dict) -> dict:
    """
    params esperado:
      mode: "properties" (default) | "pressure_to_altitude" | "validate"
      altitude_m: requerido si mode == "properties"
      pressure_pa: requerido si mode == "pressure_to_altitude"
    """
    mode = params.get("mode", "properties")

    if mode == "validate":
        return _validate()

    elif mode == "pressure_to_altitude":
        h = pressure_altitude(params["pressure_pa"])
        return {"altitude_m": h, "pressure_pa": params["pressure_pa"]}

    elif mode == "properties":
        if "altitude_m" not in params:
            raise ValueError("Falta 'altitude_m' para mode='properties'")
        return isa_properties(params["altitude_m"])

    else:
        raise ValueError(
            "mode invalido. Opciones: properties, pressure_to_altitude, validate"
        )


# ---------------------------------------------------------------------------
# Modo validate — valores de referencia tabulados de la ISA estandar
# ---------------------------------------------------------------------------
def _validate():
    checks = []

    # 1) Nivel del mar
    r0 = isa_properties(0.0)
    checks.append({
        "name": "sea_level",
        "passed": abs(r0["pressure_pa"] - P0) < 1e-3 and abs(r0["temperature_k"] - T0) < 1e-6,
        "pressure_pa": r0["pressure_pa"],
        "temperature_k": r0["temperature_k"],
    })

    # 2) 11000 m (tope de la troposfera) — valores de referencia ICAO estandar
    r11 = isa_properties(11000.0)
    checks.append({
        "name": "tropopause_11000m",
        "passed": abs(r11["pressure_pa"] - 22632.0) < 5.0 and abs(r11["temperature_k"] - 216.65) < 0.01,
        "pressure_pa": r11["pressure_pa"],
        "temperature_k": r11["temperature_k"],
        "expected_pressure_pa": 22632.0,
    })

    # 3) 20000 m — referencia ICAO estandar ~5474.9 Pa
    r20 = isa_properties(20000.0)
    checks.append({
        "name": "20000m",
        "passed": abs(r20["pressure_pa"] - 5474.9) < 5.0,
        "pressure_pa": r20["pressure_pa"],
        "expected_pressure_pa": 5474.9,
    })

    # 4) 32000 m — referencia ICAO estandar ~868.02 Pa
    r32 = isa_properties(32000.0)
    checks.append({
        "name": "32000m",
        "passed": abs(r32["pressure_pa"] - 868.02) < 2.0,
        "pressure_pa": r32["pressure_pa"],
        "expected_pressure_pa": 868.02,
    })

    # 5) Densidad a nivel del mar
    checks.append({
        "name": "sea_level_density",
        "passed": abs(r0["density_kg_m3"] - RHO0) < 1e-3,
        "density_kg_m3": r0["density_kg_m3"],
        "expected_density_kg_m3": RHO0,
    })

    # 6) Velocidad del sonido a nivel del mar (~340.29 m/s)
    checks.append({
        "name": "sea_level_speed_of_sound",
        "passed": abs(r0["speed_of_sound_ms"] - 340.29) < 0.1,
        "speed_of_sound_ms": r0["speed_of_sound_ms"],
    })

    # 7) Monotonicidad: la presion decrece con la altura
    altitudes = [0, 1000, 5000, 11000, 20000, 32000, 47000, 71000, 84000]
    pressures = [isa_properties(h)["pressure_pa"] for h in altitudes]
    monotonic = all(pressures[i] > pressures[i + 1] for i in range(len(pressures) - 1))
    checks.append({
        "name": "pressure_monotonic_decrease",
        "passed": monotonic,
        "pressures_pa": pressures,
    })

    # 8) Inversion: pressure_to_altitude recupera la altitud original
    h_test = 5500.0
    p_test = isa_properties(h_test)["pressure_pa"]
    h_recovered = pressure_altitude(p_test)
    checks.append({
        "name": "pressure_altitude_inversion",
        "passed": abs(h_recovered - h_test) < 1.0,
        "h_original": h_test,
        "h_recovered": h_recovered,
    })

    all_passed = all(c["passed"] for c in checks)
    return {
        "mode": "validate",
        "tool": "isa_atmosphere_tool",
        "all_passed": all_passed,
        "checks": checks,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(isa_atmosphere_tool({"mode": "validate"}), indent=2))
