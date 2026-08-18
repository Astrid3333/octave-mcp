"""
agricultural_dynamics_tool
============================
Dinamica de cultivos y plagas para planificacion agricola comunitaria.

Modes:
  crop_logistic_growth   : crecimiento de biomasa/rendimiento via modelo logistico (solucion analitica)
  yield_climate_response : rendimiento relativo dado estres hidrico (FAO Ky) y termico (funcion Yan & Hunt 1999)
  pest_predator_dynamics : dinamica presa-depredador (plaga vs enemigo natural), Lotka-Volterra clasico
                            o Rosenzweig-MacArthur (logistico + Holling tipo II), integracion RK45
  validate                : self-tests

Referencias de los modelos (estandar de agronomia/ecologia matematica, no
resultados propios): crecimiento logistico (Verhulst); FAO Ky water-stress
yield model (Doorenbos & Kassam 1979, FAO Irrigation and Drainage Paper 33);
funcion de respuesta termica de cultivos (Yan & Hunt, 1999, Annals of Botany);
Lotka-Volterra (1925/1926); Rosenzweig-MacArthur (1963).

NOTA DE ALCANCE: modelos de primer orden para planificacion y educacion.
No sustituyen un modelo agronomico calibrado localmente (suelo, variedad,
manejo) ni un programa de manejo integrado de plagas real.
"""

import math
import numpy as np
from scipy.integrate import solve_ivp


# ---------------------------------------------------------------------------
# CRECIMIENTO LOGISTICO
# ---------------------------------------------------------------------------

def _logistic_analytic(t, r, K, B0):
    """Solucion cerrada de dB/dt = r*B*(1-B/K)."""
    A = (K - B0) / B0
    return K / (1.0 + A * np.exp(-r * np.asarray(t)))


def crop_logistic_growth(params):
    r = params.get("growth_rate", 0.1)
    K = params["carrying_capacity"]
    B0 = params.get("initial_biomass", K * 0.01)
    t_max = params.get("t_max", 120.0)
    n_points = params.get("n_points", 50)

    t = np.linspace(0.0, t_max, n_points)
    B = _logistic_analytic(t, r, K, B0)

    # tiempo hasta alcanzar un porcentaje de K (default 90%)
    target_frac = params.get("target_fraction", 0.9)
    B_target = target_frac * K
    A = (K - B0) / B0
    if B_target < K:
        t_target = -math.log((K / B_target - 1.0) / A) / r
    else:
        t_target = None

    inflection_t = math.log(A) / r if A > 0 else 0.0
    max_growth_rate = r * K / 4.0  # dB/dt maximo, en B=K/2

    return {
        "t": t.tolist(),
        "biomass": B.tolist(),
        "growth_rate": r,
        "carrying_capacity": K,
        "initial_biomass": B0,
        "inflection_time": round(inflection_t, 4) if inflection_t > 0 else None,
        "max_growth_rate_per_time": round(max_growth_rate, 6),
        "time_to_target_fraction": round(t_target, 4) if t_target is not None else None,
        "target_fraction": target_frac,
        "final_biomass": round(float(B[-1]), 4),
    }


# ---------------------------------------------------------------------------
# RENDIMIENTO VS CLIMA
# ---------------------------------------------------------------------------

def _yan_hunt_temp_response(T, Tmin, Topt, Tmax):
    """Funcion de respuesta termica de cultivos (Yan & Hunt, 1999). f(Topt)=1, f(Tmin)=f(Tmax)=0."""
    if T <= Tmin or T >= Tmax:
        return 0.0
    exp1 = (Tmax - Topt) / (Topt - Tmin)
    term1 = ((Tmax - T) / (Tmax - Topt)) ** exp1
    term2 = (T - Tmin) / (Topt - Tmin)
    return term1 * term2


def yield_climate_response(params):
    Y_max = params["max_yield"]
    ETa = params["actual_evapotranspiration"]
    ETm = params["max_evapotranspiration"]
    Ky = params.get("yield_response_factor_Ky", 1.0)  # FAO-33, tipico 0.85-1.25 segun cultivo/etapa

    T = params.get("temperature_c", None)
    Tmin = params.get("t_cardinal_min_c", 8.0)
    Topt = params.get("t_cardinal_opt_c", 25.0)
    Tmax = params.get("t_cardinal_max_c", 40.0)

    water_deficit_frac = 1.0 - (ETa / ETm)
    rel_yield_water = 1.0 - Ky * water_deficit_frac
    rel_yield_water = max(0.0, min(1.0, rel_yield_water))

    if T is not None:
        f_temp = _yan_hunt_temp_response(T, Tmin, Topt, Tmax)
    else:
        f_temp = 1.0  # sin dato de temperatura, no se aplica penalizacion termica

    Y_actual = Y_max * rel_yield_water * f_temp

    return {
        "max_yield": Y_max,
        "water_deficit_fraction": round(water_deficit_frac, 4),
        "relative_yield_water_stress": round(rel_yield_water, 4),
        "temperature_response_factor": round(f_temp, 4),
        "estimated_yield": round(Y_actual, 4),
        "yield_response_factor_Ky": Ky,
        "cardinal_temperatures_c": {"min": Tmin, "opt": Topt, "max": Tmax},
    }


# ---------------------------------------------------------------------------
# DEPREDADOR-PRESA (PLAGAS)
# ---------------------------------------------------------------------------

def _lotka_volterra_rhs(t, state, a, b, c, d):
    x, y = state
    dxdt = a * x - b * x * y
    dydt = -c * y + d * x * y
    return [dxdt, dydt]


def _lv_invariant(x, y, a, b, c, d):
    """Cantidad conservada del LV clasico: V = d*x - c*ln(x) + b*y - a*ln(y). Constante a lo largo de la trayectoria."""
    return d * x - c * np.log(x) + b * y - a * np.log(y)


def _rosenzweig_macarthur_rhs(t, state, r, K, a, h, e, m):
    x, y = state
    x = max(x, 0.0)
    y = max(y, 0.0)
    predation = (a * x * y) / (1.0 + a * h * x) if x > 0 else 0.0
    dxdt = r * x * (1.0 - x / K) - predation
    dydt = e * predation - m * y
    return [dxdt, dydt]


def pest_predator_dynamics(params):
    model = params.get("model", "lotka_volterra")
    x0 = params.get("pest_initial", 10.0)
    y0 = params.get("predator_initial", 5.0)
    t_max = params.get("t_max", 50.0)
    n_points = params.get("n_points", 200)
    t_eval = np.linspace(0.0, t_max, n_points)

    if model == "lotka_volterra":
        a = params.get("pest_growth_rate", 1.0)       # crecimiento de la plaga sin depredador
        b = params.get("predation_rate", 0.1)          # tasa de depredacion
        c = params.get("predator_death_rate", 1.0)     # muerte del depredador sin presa
        d = params.get("predator_efficiency", 0.075)   # eficiencia de conversion presa->depredador

        sol = solve_ivp(_lotka_volterra_rhs, [0, t_max], [x0, y0], t_eval=t_eval,
                         args=(a, b, c, d), method="RK45", rtol=1e-9, atol=1e-9)
        x, y = sol.y[0], sol.y[1]
        invariant = _lv_invariant(x, y, a, b, c, d)

        return {
            "model": model,
            "t": t_eval.tolist(),
            "pest_population": x.tolist(),
            "predator_population": y.tolist(),
            "equilibrium": {"pest": round(c / d, 4), "predator": round(a / b, 4)},
            "invariant_mean": round(float(np.mean(invariant)), 6),
            "invariant_relative_std": round(float(np.std(invariant) / abs(np.mean(invariant))), 8),
            "params": {"a": a, "b": b, "c": c, "d": d},
        }

    elif model == "rosenzweig_macarthur":
        r = params.get("pest_growth_rate", 1.0)
        K = params.get("pest_carrying_capacity", 100.0)
        a = params.get("attack_rate", 0.05)
        h = params.get("handling_time", 0.1)
        e = params.get("conversion_efficiency", 0.3)
        m = params.get("predator_death_rate", 0.2)

        sol = solve_ivp(_rosenzweig_macarthur_rhs, [0, t_max], [x0, y0], t_eval=t_eval,
                         args=(r, K, a, h, e, m), method="RK45", rtol=1e-9, atol=1e-9)
        x, y = sol.y[0], sol.y[1]

        # equilibrio interior analitico (si e > m*h)
        equilibrium = None
        if e > m * h:
            x_star = m / (a * (e - m * h))
            y_star = (r * (1.0 - x_star / K) * (1.0 + a * h * x_star)) / a
            equilibrium = {"pest": round(x_star, 4), "predator": round(y_star, 4)}

        return {
            "model": model,
            "t": t_eval.tolist(),
            "pest_population": x.tolist(),
            "predator_population": y.tolist(),
            "interior_equilibrium": equilibrium,
            "params": {"r": r, "K": K, "a": a, "h": h, "e": e, "m": m},
        }
    else:
        raise ValueError(f"model desconocido: {model}")


# ---------------------------------------------------------------------------
# VALIDATE
# ---------------------------------------------------------------------------

def validate():
    checks = []

    # 1. Crecimiento logistico: solucion analitica vs integracion numerica RK45 independiente
    for r, K, B0 in [(0.15, 1000.0, 10.0), (0.3, 500.0, 250.0), (0.05, 2000.0, 5.0)]:
        t_eval = np.linspace(0, 100, 40)
        analytic = _logistic_analytic(t_eval, r, K, B0)
        sol = solve_ivp(lambda t, B: r * B * (1 - B / K), [0, 100], [B0], t_eval=t_eval,
                         method="RK45", rtol=1e-10, atol=1e-10)
        numeric = sol.y[0]
        rel_err = float(np.max(np.abs(analytic - numeric) / K))
        checks.append({
            "check": f"Crecimiento logistico: analitico vs RK45 (r={r}, K={K}, B0={B0})",
            "max_rel_error": rel_err,
            "pass": rel_err < 1e-6,
        })

    # 2. Maxima tasa de crecimiento ocurre en B=K/2 y vale r*K/4
    r, K, B0 = 0.2, 800.0, 5.0
    res = crop_logistic_growth({"growth_rate": r, "carrying_capacity": K, "initial_biomass": B0, "n_points": 2000, "t_max": 150})
    B_arr = np.array(res["biomass"])
    t_arr = np.array(res["t"])
    dBdt = np.gradient(B_arr, t_arr)
    idx_max = np.argmax(dBdt)
    checks.append({
        "check": "Tasa de crecimiento maxima ~ r*K/4, en B~K/2",
        "B_at_max_rate_over_K": round(float(B_arr[idx_max] / K), 3),
        "expected_B_over_K": 0.5,
        "max_rate_numeric": round(float(dBdt[idx_max]), 5),
        "max_rate_formula": round(r * K / 4.0, 5),
        "pass": bool(abs(B_arr[idx_max] / K - 0.5) < 0.02 and abs(dBdt[idx_max] - r * K / 4.0) / (r * K / 4.0) < 0.02),
    })

    # 3. FAO Ky: sin deficit hidrico (ETa=ETm) -> rendimiento relativo = 1 (sin perdida)
    res_fao1 = yield_climate_response({"max_yield": 10.0, "actual_evapotranspiration": 500.0,
                                        "max_evapotranspiration": 500.0, "yield_response_factor_Ky": 1.1})
    checks.append({
        "check": "FAO Ky: ETa=ETm -> rendimiento relativo hidrico = 1.0",
        "value": res_fao1["relative_yield_water_stress"],
        "pass": abs(res_fao1["relative_yield_water_stress"] - 1.0) < 1e-9,
    })

    # 4. FAO Ky: Ky=1, ETa=0.5*ETm -> perdida relativa = 0.5 exacto
    res_fao2 = yield_climate_response({"max_yield": 10.0, "actual_evapotranspiration": 250.0,
                                        "max_evapotranspiration": 500.0, "yield_response_factor_Ky": 1.0})
    checks.append({
        "check": "FAO Ky=1, ETa=0.5*ETm -> rendimiento relativo = 0.5",
        "value": res_fao2["relative_yield_water_stress"],
        "pass": abs(res_fao2["relative_yield_water_stress"] - 0.5) < 1e-9,
    })

    # 5. Yan-Hunt: f(Topt) = 1 exacto
    f_opt = _yan_hunt_temp_response(25.0, 8.0, 25.0, 40.0)
    checks.append({
        "check": "Yan-Hunt f(Topt) = 1.0",
        "value": round(f_opt, 9),
        "pass": abs(f_opt - 1.0) < 1e-9,
    })

    # 6. Yan-Hunt: f(Tmin) = f(Tmax) = 0
    f_min = _yan_hunt_temp_response(8.0, 8.0, 25.0, 40.0)
    f_max = _yan_hunt_temp_response(40.0, 8.0, 25.0, 40.0)
    checks.append({
        "check": "Yan-Hunt f(Tmin)=f(Tmax)=0",
        "f_min": f_min, "f_max": f_max,
        "pass": f_min == 0.0 and f_max == 0.0,
    })

    # 7. Lotka-Volterra clasico: cantidad conservada V(x,y) casi constante a lo largo de la trayectoria
    #    (chequeo independiente de que la integracion RK45 es correcta, no solo que "se ve periodico")
    lv = pest_predator_dynamics({"model": "lotka_volterra", "pest_initial": 15.0, "predator_initial": 8.0,
                                  "t_max": 60.0, "n_points": 300, "pest_growth_rate": 1.0,
                                  "predation_rate": 0.1, "predator_death_rate": 1.0, "predator_efficiency": 0.075})
    checks.append({
        "check": "Lotka-Volterra: invariante V(x,y) conservado (std relativo)",
        "invariant_relative_std": lv["invariant_relative_std"],
        "pass": lv["invariant_relative_std"] < 1e-4,
    })

    # 8. Lotka-Volterra: si arranca EXACTO en el equilibrio (c/d, a/b), se queda ahi (derivada ~0)
    a, b, c, d = 1.0, 0.1, 1.0, 0.075
    x_eq, y_eq = c / d, a / b
    dxdt, dydt = _lotka_volterra_rhs(0, [x_eq, y_eq], a, b, c, d)
    checks.append({
        "check": "Lotka-Volterra: en equilibrio (c/d, a/b) las derivadas son ~0",
        "dxdt": dxdt, "dydt": dydt,
        "pass": abs(dxdt) < 1e-9 and abs(dydt) < 1e-9,
    })

    # 9. Rosenzweig-MacArthur: arrancando en el equilibrio interior analitico, las derivadas son ~0
    r, K, a2, h, e, m = 1.0, 100.0, 0.05, 0.1, 0.3, 0.2
    x_star = m / (a2 * (e - m * h))
    y_star = (r * (1.0 - x_star / K) * (1.0 + a2 * h * x_star)) / a2
    dxdt2, dydt2 = _rosenzweig_macarthur_rhs(0, [x_star, y_star], r, K, a2, h, e, m)
    checks.append({
        "check": "Rosenzweig-MacArthur: en equilibrio interior analitico, derivadas ~0",
        "x_star": round(x_star, 4), "y_star": round(y_star, 4),
        "dxdt": round(dxdt2, 8), "dydt": round(dydt2, 8),
        "pass": abs(dxdt2) < 1e-6 and abs(dydt2) < 1e-6,
    })

    # 10. Rosenzweig-MacArthur: poblaciones no negativas a lo largo de la simulacion
    rm = pest_predator_dynamics({"model": "rosenzweig_macarthur", "pest_initial": 20.0, "predator_initial": 5.0,
                                  "t_max": 200.0, "n_points": 500})
    min_x = min(rm["pest_population"])
    min_y = min(rm["predator_population"])
    checks.append({
        "check": "Rosenzweig-MacArthur: poblaciones no negativas",
        "min_pest": round(min_x, 6), "min_predator": round(min_y, 6),
        "pass": min_x >= -1e-6 and min_y >= -1e-6,
    })

    n_pass = sum(1 for c in checks if c["pass"])
    return {
        "n_checks": len(checks),
        "n_pass": n_pass,
        "all_pass": n_pass == len(checks),
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# DISPATCH
# ---------------------------------------------------------------------------

def agricultural_dynamics_tool(mode, params=None):
    params = params or {}
    if mode == "crop_logistic_growth":
        return crop_logistic_growth(params)
    elif mode == "yield_climate_response":
        return yield_climate_response(params)
    elif mode == "pest_predator_dynamics":
        return pest_predator_dynamics(params)
    elif mode == "validate":
        return validate()
    else:
        raise ValueError(f"mode desconocido: {mode}")


TOOL_SCHEMA = {
    "name": "agricultural_dynamics_tool",
    "description": (
        "Dinamica de cultivos y plagas para planificacion agricola comunitaria. "
        "mode='crop_logistic_growth': crecimiento de biomasa/rendimiento via modelo logistico de Verhulst "
        "(solucion analitica cerrada), incluye tiempo a fraccion objetivo de capacidad de carga y tasa maxima "
        "de crecimiento. mode='yield_climate_response': rendimiento relativo combinando estres hidrico (FAO-33 "
        "Ky, Doorenbos & Kassam 1979) y respuesta termica via temperaturas cardinales (Yan & Hunt 1999). "
        "mode='pest_predator_dynamics': dinamica presa-depredador (plaga vs enemigo natural) via Lotka-Volterra "
        "clasico o Rosenzweig-MacArthur (logistico + funcion Holling tipo II), integracion RK45. "
        "Modelos estandar de agronomia/ecologia matematica de primer orden; no reemplazan un modelo agronomico "
        "calibrado localmente ni un programa de manejo integrado de plagas real."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["crop_logistic_growth", "yield_climate_response", "pest_predator_dynamics", "validate"],
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
