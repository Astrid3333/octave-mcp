"""
water_resource_tool.py

Modelado hidrologico basico para gestion publica de recursos hidricos:
cuencas, escorrentia y balance de agua en embalses/cuencas.

Modos:
  - rational_method: metodo racional, Qp = C*I*A/360 (caudal pico en m3/s,
                C adimensional, I en mm/h, A en hectareas)
  - scs_curve_number: escorrentia directa por el metodo de numero de curva
                (SCS-CN): Q = (P - 0.2S)^2 / (P + 0.8S) si P > 0.2S, si no Q=0;
                S = 25400/CN - 254 (mm)
  - time_of_concentration: formula de Kirpich, tc = 0.0195 * L^0.77 * S^-0.385
                (L en metros, S = pendiente m/m, tc en minutos)
  - water_balance: balance de masa de un embalse/cuenca sobre una serie
                temporal: V(t+1) = V(t) + Inflow(t) - Outflow(t) - Evap(t),
                con deteccion de deficit (volumen negativo) y desborde
                (volumen > capacidad, si se especifica)
"""

import numpy as np


def _mode_rational_method(p):
    C = float(p["C"])          # coeficiente de escorrentia, adimensional [0,1]
    I = float(p["I"])          # intensidad de lluvia, mm/h
    A = float(p["A"])          # area de la cuenca, hectareas

    if not (0.0 <= C <= 1.0):
        raise ValueError("C (coeficiente de escorrentia) debe estar en [0,1]")

    Qp = C * I * A / 360.0  # m3/s

    return {
        "C": C, "I_mm_h": I, "A_ha": A,
        "peak_flow_m3_s": round(Qp, 6),
    }


def _mode_scs_curve_number(p):
    P = float(p["P"])          # precipitacion total del evento, mm
    CN = float(p["CN"])        # numero de curva, (0,100]

    if not (0.0 < CN <= 100.0):
        raise ValueError("CN debe estar en (0, 100]")

    S = 25400.0 / CN - 254.0   # retencion potencial maxima, mm
    Ia = 0.2 * S                # abstraccion inicial (convencion estandar SCS)

    if P <= Ia:
        Q = 0.0
    else:
        Q = (P - Ia) ** 2 / (P - Ia + S)

    runoff_coefficient = Q / P if P > 0 else 0.0

    return {
        "P_mm": P, "CN": CN,
        "S_mm": round(S, 4),
        "Ia_mm": round(Ia, 4),
        "direct_runoff_Q_mm": round(Q, 6),
        "runoff_coefficient": round(runoff_coefficient, 6),
    }


def _mode_time_of_concentration(p):
    L = float(p["L"])          # longitud del cauce principal, metros
    S = float(p["S"])          # pendiente promedio, m/m (adimensional)

    if S <= 0:
        raise ValueError("S (pendiente) debe ser > 0")

    tc_min = 0.0195 * (L ** 0.77) * (S ** -0.385)

    return {
        "L_m": L, "S_m_per_m": S,
        "time_of_concentration_min": round(tc_min, 4),
        "time_of_concentration_h": round(tc_min / 60.0, 4),
    }


def _mode_water_balance(p):
    inflow = np.asarray(p["inflow"], dtype=float)
    outflow = np.asarray(p["outflow"], dtype=float)
    evap = np.asarray(p.get("evaporation", np.zeros_like(inflow)), dtype=float)
    V0 = float(p.get("initial_storage", 0.0))
    capacity = p.get("capacity")  # opcional

    n = len(inflow)
    if len(outflow) != n or len(evap) != n:
        raise ValueError("inflow, outflow y evaporation deben tener la misma longitud")

    net = inflow - outflow - evap
    storage = np.empty(n + 1)
    storage[0] = V0
    for t in range(n):
        storage[t + 1] = storage[t] + net[t]

    deficit_periods = [int(i) for i in range(1, n + 1) if storage[i] < 0]
    overflow_periods = []
    if capacity is not None:
        capacity = float(capacity)
        overflow_periods = [int(i) for i in range(1, n + 1) if storage[i] > capacity]

    return {
        "n_periods": n,
        "initial_storage": V0,
        "net_change_per_period": np.round(net, 6).tolist(),
        "storage_timeseries": np.round(storage, 6).tolist(),
        "final_storage": round(float(storage[-1]), 6),
        "min_storage": round(float(np.min(storage)), 6),
        "max_storage": round(float(np.max(storage)), 6),
        "deficit_periods": deficit_periods,
        "capacity": capacity,
        "overflow_periods": overflow_periods,
    }


def _validate():
    checks = []

    # --- Check 1: metodo racional, sustitucion directa
    r = _mode_rational_method({"C": 0.6, "I": 50.0, "A": 120.0})
    expected = 0.6 * 50.0 * 120.0 / 360.0
    err = abs(r["peak_flow_m3_s"] - expected) / expected * 100
    checks.append({
        "name": "rational_method_direct",
        "computed": r["peak_flow_m3_s"], "expected": round(expected, 6),
        "error_pct": round(err, 6), "passed": bool(err < 1e-9),
    })

    # --- Check 2: SCS-CN, caso limite CN=100 (superficie totalmente impermeable):
    # S=0, Ia=0 -> toda la lluvia escurre, Q = P exactamente
    r2 = _mode_scs_curve_number({"P": 80.0, "CN": 100.0})
    checks.append({
        "name": "scs_cn_impervious_limit",
        "S_mm": r2["S_mm"], "Q_mm": r2["direct_runoff_Q_mm"], "P_mm": 80.0,
        "passed": bool(abs(r2["S_mm"]) < 1e-9 and abs(r2["direct_runoff_Q_mm"] - 80.0) < 1e-6),
    })

    # --- Check 3: SCS-CN, P <= Ia -> Q debe ser exactamente 0 (sin escorrentia)
    r3 = _mode_scs_curve_number({"P": 5.0, "CN": 60.0})  # S~=169mm, Ia~=34mm > P=5
    checks.append({
        "name": "scs_cn_below_initial_abstraction",
        "P_mm": 5.0, "Ia_mm": r3["Ia_mm"], "Q_mm": r3["direct_runoff_Q_mm"],
        "passed": bool(r3["direct_runoff_Q_mm"] == 0.0 and 5.0 <= r3["Ia_mm"]),
    })

    # --- Check 4: SCS-CN monotonia -- mayor CN (superficie mas impermeable) debe
    # dar mayor escorrentia para la misma lluvia
    q_cn60 = _mode_scs_curve_number({"P": 80.0, "CN": 60.0})["direct_runoff_Q_mm"]
    q_cn90 = _mode_scs_curve_number({"P": 80.0, "CN": 90.0})["direct_runoff_Q_mm"]
    checks.append({
        "name": "scs_cn_monotonicity",
        "Q_CN60": q_cn60, "Q_CN90": q_cn90,
        "passed": bool(q_cn90 > q_cn60),
    })

    # --- Check 5: time_of_concentration, sustitucion directa (Kirpich)
    tc = _mode_time_of_concentration({"L": 1000.0, "S": 0.02})
    expected_tc = 0.0195 * (1000.0 ** 0.77) * (0.02 ** -0.385)
    err_tc = abs(tc["time_of_concentration_min"] - expected_tc) / expected_tc * 100
    checks.append({
        "name": "time_of_concentration_direct",
        "computed_min": tc["time_of_concentration_min"], "expected_min": round(expected_tc, 6),
        "error_pct": round(err_tc, 6), "passed": bool(err_tc < 1e-3),
    })

    # --- Check 6: water_balance, conservacion de masa exacta contra formula
    # cerrada: con inflow, outflow, evap CONSTANTES durante n periodos,
    # storage final = V0 + n*(inflow-outflow-evap), sin acumulacion de error
    n = 12
    inflow = [10.0] * n
    outflow = [7.0] * n
    evap = [1.0] * n
    V0 = 50.0
    wb = _mode_water_balance({"inflow": inflow, "outflow": outflow,
                               "evaporation": evap, "initial_storage": V0})
    expected_final = V0 + n * (10.0 - 7.0 - 1.0)
    err_wb = abs(wb["final_storage"] - expected_final)
    checks.append({
        "name": "water_balance_mass_conservation",
        "computed_final": wb["final_storage"], "expected_final": expected_final,
        "abs_error": round(err_wb, 9), "passed": bool(err_wb < 1e-9),
    })

    # --- Check 7: water_balance, deteccion de deficit -- outflow constante mayor
    # que inflow debe hacer que storage cruce a negativo en algun periodo, y ese
    # periodo debe estar identificado en deficit_periods
    wb2 = _mode_water_balance({
        "inflow": [1.0] * 10, "outflow": [5.0] * 10, "evaporation": [0.0] * 10,
        "initial_storage": 10.0,
    })
    # V(t) = 10 - 4t; cruza a negativo quiere decir 10-4t<0 -> t>2.5 -> primer t=3
    checks.append({
        "name": "water_balance_deficit_detection",
        "deficit_periods": wb2["deficit_periods"],
        "passed": bool(len(wb2["deficit_periods"]) > 0 and wb2["deficit_periods"][0] == 3),
    })

    # --- Check 8: water_balance, deteccion de desborde con capacity especificada
    wb3 = _mode_water_balance({
        "inflow": [20.0] * 5, "outflow": [0.0] * 5, "evaporation": [0.0] * 5,
        "initial_storage": 0.0, "capacity": 50.0,
    })
    # V(t) = 20t; supera 50 en t=3 (60>50)
    checks.append({
        "name": "water_balance_overflow_detection",
        "overflow_periods": wb3["overflow_periods"],
        "passed": bool(len(wb3["overflow_periods"]) > 0 and wb3["overflow_periods"][0] == 3),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_water_resource(mode, params=None):
    params = params or {}

    if mode == "rational_method":
        return _mode_rational_method(params)
    elif mode == "scs_curve_number":
        return _mode_scs_curve_number(params)
    elif mode == "time_of_concentration":
        return _mode_time_of_concentration(params)
    elif mode == "water_balance":
        return _mode_water_balance(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"Modo desconocido: {mode}")


if __name__ == "__main__":
    import json
    print(json.dumps(compute_water_resource("validate"), indent=2, ensure_ascii=False))
