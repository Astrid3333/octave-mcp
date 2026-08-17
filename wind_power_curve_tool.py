"""
wind_power_curve_tool.py

Potencia eolica -- formula cerrada + una integracion numerica simple
(cuadratura de la distribucion de Weibull contra la curva de potencia
para el AEP). Sin dependencias nuevas, sin solver.

Fisica (referencias estandar de ingenieria eolica, Manwell/McGowan/Rogers
"Wind Energy Explained" y el limite de Betz 1919 -- formulas de dominio
publico re-derivadas aca):

  Potencia disponible en el viento a traves de un area A:
    P_wind = 0.5 * rho * A * v^3

  Limite de Betz: la maxima fraccion extraible de esa potencia por
  cualquier turbina de eje horizontal es Cp_max = 16/27 ~ 0.5926,
  resultado de maximizar Cp(a) = 4a(1-a)^2 sobre el factor de induccion
  axial a (a=1/3 en el optimo).

  Curva de potencia simplificada (modelo cubico estandar en cutin-rated):
    P(v) = 0                                            v < v_cutin
    P(v) = P_rated * (v^3-v_cutin^3)/(v_rated^3-v_cutin^3)   v_cutin<=v<=v_rated
    P(v) = P_rated                                      v_rated<=v<=v_cutout
    P(v) = 0                                            v > v_cutout

  Densidad del aire con altitud (atmosfera estandar internacional,
  formula barometrica simplificada, valida hasta ~11km):
    rho(h) = rho0 * (1 - L*h/T0)^(g*M/(R*L) - 1)
    rho0=1.225 kg/m3, T0=288.15K, L=0.0065 K/m, g=9.80665, M=0.0289644 kg/mol,
    R=8.31446 J/(mol K)

  Distribucion de Weibull para velocidad de viento:
    f(v) = (k/c)*(v/c)^(k-1)*exp(-(v/c)^k)
  Velocidad media: v_mean = c*Gamma(1+1/k)

  AEP (energia anual producida) = 8760h * integral_0^inf P(v)*f(v) dv
  (cuadratura numerica simple, regla del trapecio sobre v discretizado)

CUIDADO DE CONFIANZA DE DATOS: todo lo de esta tool es formula cerrada
fisica (alta confianza matematica). El termino "media" solo aplica a la
curva de potencia cubica simplificada en si misma -- es una aproximacion
estandar de ingenieria para turbinas reales (que usan tablas de
fabricante con perdidas aerodinamicas no cubicas cerca de v_rated);
error tipico reportado en literatura 5-15% contra curvas de datasheet
reales, aceptable para dimensionamiento preliminar.
"""
import math

BETZ_LIMIT = 16.0 / 27.0  # ~0.59259...
RHO0 = 1.225       # kg/m^3, densidad del aire a nivel del mar, 15C (ISA)
T0 = 288.15        # K
LAPSE = 0.0065     # K/m
G = 9.80665        # m/s^2
M_AIR = 0.0289644  # kg/mol
R_GAS = 8.31446261815324  # J/(mol K)


def _air_density(altitude_m=0.0, temperature_C=None):
    """Densidad del aire por atmosfera estandar (si no se da temperatura)
    o por gas ideal a temperatura dada (mas preciso si se conoce el sitio)."""
    if temperature_C is not None:
        # gas ideal con presion de la ISA a esa altitud, T real dada por el usuario
        T_isa = T0 - LAPSE * altitude_m
        p = 101325.0 * (T_isa / T0) ** (G * M_AIR / (R_GAS * LAPSE))
        T = temperature_C + 273.15
        return p * M_AIR / (R_GAS * T)
    T = T0 - LAPSE * altitude_m
    return RHO0 * (T / T0) ** (G * M_AIR / (R_GAS * LAPSE) - 1)


def _air_density_mode(params):
    h = params.get("altitude_m", 0.0)
    T = params.get("temperature_C")
    rho = _air_density(h, T)
    return {
        "altitude_m": h, "temperature_C": T,
        "air_density_kg_m3": round(rho, 5),
        "note": "Sin temperature_C usa atmosfera estandar (ISA); con temperature_C "
                "usa gas ideal con la presion ISA de esa altitud y la T real dada.",
    }


def _wind_power_density(rho, v):
    """Potencia disponible en el viento por unidad de area, W/m^2."""
    return 0.5 * rho * v ** 3


def _power_available_mode(params):
    v = params.get("wind_speed_ms")
    A = params.get("rotor_area_m2")
    if v is None or A is None:
        raise ValueError("power_available requiere wind_speed_ms y rotor_area_m2")
    rho = _air_density(params.get("altitude_m", 0.0), params.get("temperature_C"))
    P_wind = _wind_power_density(rho, v) * A
    Cp = params.get("Cp", BETZ_LIMIT)
    eta = params.get("eta_mech_gen", 1.0)
    P_extracted = P_wind * Cp * eta
    return {
        "wind_speed_ms": v, "rotor_area_m2": A, "air_density_kg_m3": round(rho, 4),
        "Cp": Cp, "eta_mech_gen": eta,
        "power_in_wind_W": round(P_wind, 2),
        "power_extracted_W": round(P_extracted, 2),
        "betz_limit_Cp": round(BETZ_LIMIT, 6),
        "fraction_of_betz": round(Cp / BETZ_LIMIT, 4) if Cp else None,
    }


def _power_curve(v, v_cutin, v_rated, v_cutout, P_rated):
    if v < v_cutin or v > v_cutout:
        return 0.0
    if v < v_rated:
        return P_rated * (v ** 3 - v_cutin ** 3) / (v_rated ** 3 - v_cutin ** 3)
    return P_rated


def _power_curve_mode(params):
    required = ["v_cutin_ms", "v_rated_ms", "v_cutout_ms", "P_rated_kW"]
    missing = [k for k in required if params.get(k) is None]
    if missing:
        raise ValueError(f"power_curve requiere: {', '.join(missing)}")
    v_cutin, v_rated, v_cutout, P_rated = (params["v_cutin_ms"], params["v_rated_ms"],
                                             params["v_cutout_ms"], params["P_rated_kW"])
    if not (v_cutin < v_rated < v_cutout):
        raise ValueError("se requiere v_cutin < v_rated < v_cutout")
    if "wind_speed_ms" in params and params["wind_speed_ms"] is not None:
        v = params["wind_speed_ms"]
        return {
            "wind_speed_ms": v,
            "power_kW": round(_power_curve(v, v_cutin, v_rated, v_cutout, P_rated), 4),
            "v_cutin_ms": v_cutin, "v_rated_ms": v_rated, "v_cutout_ms": v_cutout, "P_rated_kW": P_rated,
        }
    # sin wind_speed_ms: devuelve la curva completa muestreada
    v_max_plot = v_cutout + 2
    step = params.get("curve_step_ms", 0.5)
    n = int(v_max_plot / step) + 1
    curve = []
    v_ = 0.0
    for _ in range(n + 1):
        curve.append({"v_ms": round(v_, 3), "power_kW": round(_power_curve(v_, v_cutin, v_rated, v_cutout, P_rated), 4)})
        v_ += step
    return {
        "v_cutin_ms": v_cutin, "v_rated_ms": v_rated, "v_cutout_ms": v_cutout, "P_rated_kW": P_rated,
        "curve": curve,
    }


def _weibull_pdf(v, k, c):
    if v < 0:
        return 0.0
    return (k / c) * (v / c) ** (k - 1) * math.exp(-(v / c) ** k)


def _weibull_mean(k, c):
    return c * math.gamma(1 + 1 / k)


def _weibull_mode(params):
    k = params.get("k_shape")
    c = params.get("c_scale_ms")
    if k is None or c is None:
        raise ValueError("weibull_distribution requiere k_shape y c_scale_ms")
    v_mean = _weibull_mean(k, c)
    result = {"k_shape": k, "c_scale_ms": c, "mean_wind_speed_ms": round(v_mean, 4)}
    if "wind_speed_ms" in params and params["wind_speed_ms"] is not None:
        v = params["wind_speed_ms"]
        result["wind_speed_ms"] = v
        result["pdf_value"] = round(_weibull_pdf(v, k, c), 6)
    return result


def _aep(k, c, v_cutin, v_rated, v_cutout, P_rated_kW, v_max=40.0, n_steps=400):
    """AEP en kWh/anio, integrando P(v)*f(v) por trapecio."""
    dv = v_max / n_steps
    total = 0.0
    v_prev = 0.0
    f_prev = _weibull_pdf(v_prev, k, c) * _power_curve(v_prev, v_cutin, v_rated, v_cutout, P_rated_kW)
    for i in range(1, n_steps + 1):
        v = i * dv
        f = _weibull_pdf(v, k, c) * _power_curve(v, v_cutin, v_rated, v_cutout, P_rated_kW)
        total += (f_prev + f) / 2.0 * dv
        f_prev = f
    return total * 8760.0  # kW promedio -> kWh/anio


def _aep_mode(params):
    required = ["k_shape", "c_scale_ms", "v_cutin_ms", "v_rated_ms", "v_cutout_ms", "P_rated_kW"]
    missing = [k for k in required if params.get(k) is None]
    if missing:
        raise ValueError(f"annual_energy requiere: {', '.join(missing)}")
    k, c = params["k_shape"], params["c_scale_ms"]
    v_cutin, v_rated, v_cutout, P_rated = (params["v_cutin_ms"], params["v_rated_ms"],
                                             params["v_cutout_ms"], params["P_rated_kW"])
    v_max = params.get("v_max_integration_ms", max(40.0, v_cutout + 10))
    aep_kwh = _aep(k, c, v_cutin, v_rated, v_cutout, P_rated, v_max)
    cf = aep_kwh / (P_rated * 8760.0)
    return {
        "k_shape": k, "c_scale_ms": c, "mean_wind_speed_ms": round(_weibull_mean(k, c), 4),
        "v_cutin_ms": v_cutin, "v_rated_ms": v_rated, "v_cutout_ms": v_cutout, "P_rated_kW": P_rated,
        "AEP_kWh_year": round(aep_kwh, 1),
        "capacity_factor": round(cf, 4),
        "data_confidence": "media",
        "note": "capacity_factor tipico de turbinas reales en sitios buenos: 0.30-0.45 "
                "onshore, 0.40-0.55 offshore -- util como chequeo de sanidad del resultado.",
    }


def _validate():
    checks = []

    # 1) Limite de Betz exacto
    checks.append({"case": "limite de Betz == 16/27", "got": round(BETZ_LIMIT, 8),
                    "expected": round(16 / 27, 8), "ok": abs(BETZ_LIMIT - 16 / 27) < 1e-12})

    # 2) Cp(a)=4a(1-a)^2 maximizado en a=1/3 da exactamente 16/27
    def Cp_a(a):
        return 4 * a * (1 - a) ** 2
    checks.append({"case": "Cp(a=1/3) == Betz", "got": round(Cp_a(1 / 3), 6),
                    "expected": round(BETZ_LIMIT, 6), "ok": abs(Cp_a(1 / 3) - BETZ_LIMIT) < 1e-6})
    # y que sea maximo local (vecinos menores)
    checks.append({"case": "a=1/3 es maximo local de Cp(a)",
                    "got": [round(Cp_a(0.30), 5), round(Cp_a(1 / 3), 5), round(Cp_a(0.37), 5)],
                    "ok": Cp_a(1 / 3) > Cp_a(0.30) and Cp_a(1 / 3) > Cp_a(0.37)})

    # 3) Densidad del aire a nivel del mar, ISA (15C) == 1.225 kg/m3 exacto (por construccion)
    rho_sl = _air_density(0.0)
    checks.append({"case": "densidad del aire a nivel del mar (ISA) == 1.225",
                    "got": round(rho_sl, 4), "expected": 1.225, "ok": abs(rho_sl - 1.225) < 1e-6})
    # decrece con altitud
    rho_2000 = _air_density(2000.0)
    checks.append({"case": "densidad del aire decrece con altitud (2000m < nivel del mar)",
                    "got": round(rho_2000, 4), "expected_less_than": round(rho_sl, 4), "ok": rho_2000 < rho_sl})
    # valor de referencia conocido: densidad a 2000m ISA ~ 1.007 kg/m3 (tablas ISA estandar)
    checks.append({"case": "densidad a 2000m ISA ~ 1.007 kg/m3 (tabla ISA estandar, tol 1%)",
                    "got": round(rho_2000, 4), "expected": 1.007, "ok": abs(rho_2000 - 1.007) / 1.007 < 0.01})

    # 4) Curva de potencia: P(v_cutin)=0, P(v_rated)=P_rated exacto, P(v_cutout+eps)=0
    v_cutin, v_rated, v_cutout, P_rated = 3.0, 12.0, 25.0, 2000.0
    p_cutin = _power_curve(v_cutin, v_cutin, v_rated, v_cutout, P_rated)
    p_rated = _power_curve(v_rated, v_cutin, v_rated, v_cutout, P_rated)
    p_mid_rated = _power_curve(18.0, v_cutin, v_rated, v_cutout, P_rated)
    p_over = _power_curve(v_cutout + 0.1, v_cutin, v_rated, v_cutout, P_rated)
    p_under = _power_curve(v_cutin - 0.1, v_cutin, v_rated, v_cutout, P_rated)
    checks.append({"case": "P(v_cutin)==0", "got": p_cutin, "expected": 0.0, "ok": p_cutin == 0.0})
    checks.append({"case": "P(v_rated)==P_rated exacto", "got": p_rated, "expected": P_rated, "ok": abs(p_rated - P_rated) < 1e-9})
    checks.append({"case": "P constante == P_rated entre v_rated y v_cutout", "got": p_mid_rated, "expected": P_rated, "ok": abs(p_mid_rated - P_rated) < 1e-9})
    checks.append({"case": "P(v>v_cutout)==0", "got": p_over, "expected": 0.0, "ok": p_over == 0.0})
    checks.append({"case": "P(v<v_cutin)==0", "got": p_under, "expected": 0.0, "ok": p_under == 0.0})

    # 5) Weibull: k=2 (Rayleigh) con c dado, v_mean == c*Gamma(1.5) == c*sqrt(pi)/2
    k, c = 2.0, 8.0
    v_mean = _weibull_mean(k, c)
    expected_rayleigh = c * math.sqrt(math.pi) / 2
    checks.append({"case": "Weibull k=2 (Rayleigh): v_mean == c*sqrt(pi)/2",
                    "got": round(v_mean, 6), "expected": round(expected_rayleigh, 6),
                    "ok": abs(v_mean - expected_rayleigh) < 1e-9})

    # 6) Weibull pdf integra a 1 (numericamente, trapecio de alta resolucion)
    n_int, v_max_int = 4000, 60.0
    dv = v_max_int / n_int
    total = 0.0
    prev = _weibull_pdf(0.0, k, c)
    for i in range(1, n_int + 1):
        v = i * dv
        cur = _weibull_pdf(v, k, c)
        total += (prev + cur) / 2.0 * dv
        prev = cur
    checks.append({"case": "integral de la pdf de Weibull ~ 1", "got": round(total, 4), "expected": 1.0, "ok": abs(total - 1.0) < 1e-3})

    # 7) AEP: capacity factor debe estar en rango fisico (0,1) y AEP > 0 para
    # un caso tipico razonable
    aep = _aep(k, c, 3.0, 12.0, 25.0, 2000.0)
    cf = aep / (2000.0 * 8760.0)
    checks.append({"case": "capacity factor en rango fisico (0,1)", "got": round(cf, 4), "ok": 0 < cf < 1})

    # 8) AEP debe subir si sube la velocidad media del viento (c mayor), todo lo
    # demas igual -- chequeo de monotonicidad fisica basica
    aep_low_c = _aep(2.0, 5.0, 3.0, 12.0, 25.0, 2000.0)
    aep_high_c = _aep(2.0, 10.0, 3.0, 12.0, 25.0, 2000.0)
    checks.append({"case": "AEP crece con c_scale (mas viento) manteniendo todo lo demas igual",
                    "got": round(aep_high_c, 1), "expected_greater_than": round(aep_low_c, 1),
                    "ok": aep_high_c > aep_low_c})

    return {"validate": True, "all_passed": all(c["ok"] for c in checks), "checks": checks}


def compute_wind_power_curve(mode, params=None):
    params = params or {}
    if mode == "air_density":
        return _air_density_mode(params)
    elif mode == "power_available":
        return _power_available_mode(params)
    elif mode == "power_curve":
        return _power_curve_mode(params)
    elif mode == "weibull_distribution":
        return _weibull_mode(params)
    elif mode == "annual_energy":
        return _aep_mode(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            f"mode desconocido: {mode!r}. Valores validos: air_density, power_available, "
            f"power_curve, weibull_distribution, annual_energy, validate."
        )


WIND_POWER_CURVE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["air_density", "power_available", "power_curve", "weibull_distribution",
                     "annual_energy", "validate"],
            "default": "annual_energy",
        },
        "altitude_m": {"type": "number", "default": 0.0},
        "temperature_C": {"type": "number", "description": "Opcional; si se omite usa atmosfera estandar ISA."},
        "wind_speed_ms": {"type": "number"},
        "rotor_area_m2": {"type": "number", "description": "Solo power_available. pi*R^2 del rotor."},
        "Cp": {"type": "number", "description": "Solo power_available. Default: limite de Betz (16/27)."},
        "eta_mech_gen": {"type": "number", "default": 1.0, "description": "Eficiencia mecanica*generador combinada."},
        "v_cutin_ms": {"type": "number"},
        "v_rated_ms": {"type": "number"},
        "v_cutout_ms": {"type": "number"},
        "P_rated_kW": {"type": "number"},
        "curve_step_ms": {"type": "number", "default": 0.5, "description": "Solo power_curve sin wind_speed_ms."},
        "k_shape": {"type": "number", "description": "Parametro de forma de Weibull (tipico 1.5-3 para viento)."},
        "c_scale_ms": {"type": "number", "description": "Parametro de escala de Weibull, m/s."},
        "v_max_integration_ms": {"type": "number", "description": "Solo annual_energy: limite superior de la integral."},
    },
    "required": ["mode"],
}


try:
    from tool_registry import register_tool
    register_tool(
        name="wind_power_curve_tool",
        schema={
            "name": "wind_power_curve_tool",
            "description": (
                "Potencia eolica: densidad del aire por altitud (ISA), potencia "
                "disponible en el viento y limite de Betz, curva de potencia "
                "cubica simplificada cutin/rated/cutout, distribucion de Weibull "
                "de velocidad de viento y energia anual producida (AEP) con "
                "capacity factor via integracion Weibull x curva de potencia. "
                "Formula cerrada + cuadratura numerica simple, sin dependencias nuevas."
            ),
            "inputSchema": WIND_POWER_CURVE_TOOL_SCHEMA,
        },
        handler=lambda args: compute_wind_power_curve(args.get("mode"), args),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    print(json.dumps(compute_wind_power_curve("validate"), indent=2, ensure_ascii=False))
