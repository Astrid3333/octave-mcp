"""
flood_modeling_tool.py

Modelado de inundaciones para gestion publica: generacion de hidrogramas de
crecida, transito de crecidas (routing) y extension de la mancha de
inundacion en un tramo de canal via ecuacion de Manning.

Nota de diseno: en vez de un solver 2D completo (que requeriria reimplementar
gran parte de cfd_tool/finite_element_tool), este modulo se enfoca en las 3
piezas hidrologicas/hidraulicas standalone que resuelven el caso de uso de
gestion publica (generar la crecida, transitarla por el cauce/embalse, y
estimar hasta donde llega el agua en una seccion), cada una validable de
forma cerrada.

Modos:
  - scs_triangular_hydrograph: hidrograma unitario triangular SCS a partir de
                lluvia efectiva y caracteristicas de cuenca
  - muskingum_routing: transito de un hidrograma de entrada por un tramo de
                cauce (metodo de Muskingum, K y X)
  - manning_normal_depth: profundidad normal y ancho de inundacion en una
                seccion trapezoidal para un caudal dado (ecuacion de Manning,
                resuelta por biseccion)
"""

import numpy as np


def _mode_scs_triangular_hydrograph(p):
    """
    Hidrograma unitario triangular SCS.
    qp = 2.08 * A / Tp   (qp en m3/s por mm de lluvia efectiva, A en km2, Tp en h)
    Tp = D/2 + tlag       (tiempo al pico, h)
    tlag = 0.6 * tc        (tiempo de retardo, h; convencion SCS estandar)
    Tb = 2.67 * Tp          (tiempo base del hidrograma triangular, h)
    El hidrograma final se escala por la lluvia efectiva (mm) y se discretiza
    en pasos de tiempo dt (h).
    """
    A_km2 = float(p["area_km2"])
    tc_h = float(p["time_of_concentration_h"])
    D_h = float(p.get("rainfall_duration_h", 0.133 * tc_h))  # convencion SCS: D ~ 0.133*tc
    excess_mm = float(p["rainfall_excess_mm"])
    dt_h = float(p.get("dt_h", D_h / 2.0 if D_h > 0 else 0.1))

    tlag_h = 0.6 * tc_h
    Tp_h = D_h / 2.0 + tlag_h
    Tb_h = 2.67 * Tp_h
    qp_per_cm = 2.08 * A_km2 / Tp_h  # m3/s por CENTIMETRO de lluvia efectiva (convencion SCS)

    qp = qp_per_cm * (excess_mm / 10.0)

    n_steps = int(np.ceil(Tb_h / dt_h)) + 1
    t = np.arange(n_steps) * dt_h
    q = np.where(
        t <= Tp_h,
        qp * (t / Tp_h),
        qp * np.maximum(0.0, (Tb_h - t) / (Tb_h - Tp_h)),
    )

    # volumen bajo el hidrograma (integracion trapezoidal), en m3
    volume_m3 = float(np.trapezoid(q, t * 3600.0))
    volume_expected_m3 = excess_mm / 1000.0 * A_km2 * 1e6

    return {
        "area_km2": A_km2, "time_of_concentration_h": tc_h,
        "rainfall_duration_h": round(D_h, 4), "rainfall_excess_mm": excess_mm,
        "lag_time_h": round(tlag_h, 4),
        "time_to_peak_h": round(Tp_h, 4),
        "time_base_h": round(Tb_h, 4),
        "peak_flow_m3_s": round(float(qp), 4),
        "time_h": np.round(t, 4).tolist(),
        "flow_m3_s": np.round(q, 4).tolist(),
        "volume_m3": round(volume_m3, 2),
        "volume_expected_m3": round(volume_expected_m3, 2),
        "volume_error_pct": round(abs(volume_m3 - volume_expected_m3) / volume_expected_m3 * 100, 4),
    }


def _mode_muskingum_routing(p):
    """
    Transito de Muskingum:
        O(t+1) = C0*I(t+1) + C1*I(t) + C2*O(t)
    con:
        C0 = (-K*X + 0.5*dt) / (K - K*X + 0.5*dt)
        C1 = (K*X + 0.5*dt)  / (K - K*X + 0.5*dt)
        C2 = (K - K*X - 0.5*dt) / (K - K*X + 0.5*dt)
    (C0 + C1 + C2 = 1 siempre, por construccion)
    """
    inflow = np.asarray(p["inflow"], dtype=float)
    K = float(p["K"])          # constante de almacenamiento, horas
    X = float(p["X"])          # factor de ponderacion, [0, 0.5]
    dt = float(p.get("dt_h", 1.0))
    O0 = float(p.get("initial_outflow", inflow[0]))

    if not (0.0 <= X <= 0.5):
        raise ValueError("X debe estar en [0, 0.5]")

    denom = K - K * X + 0.5 * dt
    C0 = (-K * X + 0.5 * dt) / denom
    C1 = (K * X + 0.5 * dt) / denom
    C2 = (K - K * X - 0.5 * dt) / denom

    n = len(inflow)
    outflow = np.empty(n)
    outflow[0] = O0
    for t in range(1, n):
        outflow[t] = C0 * inflow[t] + C1 * inflow[t - 1] + C2 * outflow[t - 1]

    peak_inflow = float(np.max(inflow))
    peak_outflow = float(np.max(outflow))
    peak_inflow_idx = int(np.argmax(inflow))
    peak_outflow_idx = int(np.argmax(outflow))

    return {
        "K_h": K, "X": X, "dt_h": dt,
        "C0": round(float(C0), 6), "C1": round(float(C1), 6), "C2": round(float(C2), 6),
        "C_sum_check": round(float(C0 + C1 + C2), 9),
        "outflow": np.round(outflow, 4).tolist(),
        "peak_inflow_m3_s": round(peak_inflow, 4),
        "peak_outflow_m3_s": round(peak_outflow, 4),
        "attenuation_pct": round((1.0 - peak_outflow / peak_inflow) * 100, 4) if peak_inflow > 0 else 0.0,
        "peak_lag_steps": peak_outflow_idx - peak_inflow_idx,
        "inflow_volume_m3": round(float(np.trapezoid(inflow, dx=dt * 3600.0)), 2),
        "outflow_volume_m3": round(float(np.trapezoid(outflow, dx=dt * 3600.0)), 2),
    }


def _manning_Q(h, b, z, n, S0):
    """Caudal de Manning para seccion trapezoidal, dado tirante h."""
    A = (b + z * h) * h                      # area mojada
    P = b + 2.0 * h * np.sqrt(1.0 + z ** 2)   # perimetro mojado
    R = A / P if P > 0 else 0.0               # radio hidraulico
    Q = (1.0 / n) * A * (R ** (2.0 / 3.0)) * np.sqrt(S0)
    return Q, A, P, R


def _mode_manning_normal_depth(p):
    """
    Resuelve la ecuacion de Manning para seccion trapezoidal por biseccion:
        Q = (1/n) * A * R^(2/3) * sqrt(S0)
    Devuelve el tirante normal h y el ancho superficial (extension de la
    mancha de inundacion en esa seccion) T = b + 2*z*h.
    """
    Q_target = float(p["Q"])       # caudal de diseno, m3/s
    b = float(p["bottom_width_m"])  # ancho de solera, m
    z = float(p.get("side_slope", 1.5))  # talud H:V
    n_manning = float(p["manning_n"])
    S0 = float(p["slope"])          # pendiente longitudinal, m/m

    if Q_target <= 0:
        raise ValueError("Q debe ser > 0")

    lo, hi = 1e-6, 1.0
    Q_hi, _, _, _ = _manning_Q(hi, b, z, n_manning, S0)
    iters = 0
    while Q_hi < Q_target and iters < 200:
        hi *= 2.0
        Q_hi, _, _, _ = _manning_Q(hi, b, z, n_manning, S0)
        iters += 1

    for _ in range(200):
        mid = 0.5 * (lo + hi)
        Q_mid, _, _, _ = _manning_Q(mid, b, z, n_manning, S0)
        if Q_mid < Q_target:
            lo = mid
        else:
            hi = mid

    h = 0.5 * (lo + hi)
    Q_check, A, P, R = _manning_Q(h, b, z, n_manning, S0)
    top_width = b + 2.0 * z * h
    velocity = Q_check / A if A > 0 else 0.0

    return {
        "Q_design_m3_s": Q_target,
        "bottom_width_m": b, "side_slope": z, "manning_n": n_manning, "slope": S0,
        "normal_depth_m": round(float(h), 6),
        "top_width_m": round(float(top_width), 4),
        "wetted_area_m2": round(float(A), 4),
        "wetted_perimeter_m": round(float(P), 4),
        "hydraulic_radius_m": round(float(R), 4),
        "velocity_m_s": round(float(velocity), 4),
        "Q_check_m3_s": round(float(Q_check), 6),
        "Q_error_pct": round(abs(Q_check - Q_target) / Q_target * 100, 6),
    }


def _validate():
    checks = []

    # --- Check 1: SCS triangular hydrograph -- conservacion de volumen. El area
    # bajo el triangulo debe reproducir el volumen de escorrentia (excess*A)
    # dentro de tolerancia de discretizacion (trapecio vs triangulo exacto).
    h1 = _mode_scs_triangular_hydrograph({
        "area_km2": 25.0, "time_of_concentration_h": 3.0,
        "rainfall_excess_mm": 40.0, "dt_h": 0.05,
    })
    checks.append({
        "name": "scs_hydrograph_volume_conservation",
        "volume_computed": h1["volume_m3"], "volume_expected": h1["volume_expected_m3"],
        "error_pct": h1["volume_error_pct"],
        "passed": bool(h1["volume_error_pct"] < 1.0),
    })

    # --- Check 2: SCS triangular hydrograph -- caudal pico via sustitucion
    # directa de la formula qp = 2.08*A/Tp * excess_mm
    tlag = 0.6 * 3.0
    D = 0.133 * 3.0
    Tp = D / 2.0 + tlag
    qp_expected = 2.08 * 25.0 / Tp * (40.0 / 10.0)
    err_qp = abs(h1["peak_flow_m3_s"] - qp_expected) / qp_expected * 100
    checks.append({
        "name": "scs_hydrograph_peak_direct",
        "computed": h1["peak_flow_m3_s"], "expected": round(qp_expected, 4),
        "error_pct": round(err_qp, 6), "passed": bool(err_qp < 1e-3),
    })

    # --- Check 3: Muskingum, C0+C1+C2 = 1 siempre (identidad algebraica)
    r2 = _mode_muskingum_routing({
        "inflow": [10, 10, 30, 60, 90, 70, 40, 20, 10, 10],
        "K": 2.0, "X": 0.2, "dt_h": 1.0,
    })
    checks.append({
        "name": "muskingum_coefficients_sum_to_1",
        "C_sum": r2["C_sum_check"], "passed": bool(abs(r2["C_sum_check"] - 1.0) < 1e-9),
    })

    # --- Check 4: Muskingum, atenuacion del pico -- para una crecida transitada
    # por un tramo con almacenamiento (K>0), el pico de salida debe ser menor o
    # igual al pico de entrada, y debe ocurrir despues (retardo >= 0)
    checks.append({
        "name": "muskingum_peak_attenuation_and_lag",
        "peak_inflow": r2["peak_inflow_m3_s"], "peak_outflow": r2["peak_outflow_m3_s"],
        "peak_lag_steps": r2["peak_lag_steps"],
        "passed": bool(r2["peak_outflow_m3_s"] <= r2["peak_inflow_m3_s"] + 1e-9
                  and r2["peak_lag_steps"] >= 0),
    })

    # --- Check 5: Muskingum, caso trivial K=0 -> outflow debe igualar inflow
    # exactamente en todos los pasos (sin almacenamiento, sin atenuacion)
    r3 = _mode_muskingum_routing({
        "inflow": [5, 15, 25, 15, 5], "K": 1e-9, "X": 0.0, "dt_h": 1.0,
        "initial_outflow": 5,
    })
    max_diff = max(abs(a - b) for a, b in zip(r3["outflow"], [5, 15, 25, 15, 5]))
    checks.append({
        "name": "muskingum_zero_storage_limit",
        "outflow": r3["outflow"], "max_abs_diff_vs_inflow": round(max_diff, 4),
        "passed": bool(max_diff < 1e-2),
    })

    # --- Check 6: Manning, Q_check debe reproducir Q_target (consistencia de
    # la biseccion contra la propia ecuacion que resuelve)
    m1 = _mode_manning_normal_depth({
        "Q": 45.0, "bottom_width_m": 8.0, "side_slope": 1.5,
        "manning_n": 0.035, "slope": 0.001,
    })
    checks.append({
        "name": "manning_bisection_self_consistency",
        "Q_error_pct": m1["Q_error_pct"], "passed": bool(m1["Q_error_pct"] < 1e-4),
    })

    # --- Check 7: Manning, monotonia -- mayor caudal de diseno debe dar mayor
    # tirante normal y mayor ancho de inundacion, con la misma seccion
    m_low = _mode_manning_normal_depth({
        "Q": 10.0, "bottom_width_m": 8.0, "side_slope": 1.5,
        "manning_n": 0.035, "slope": 0.001,
    })
    m_high = _mode_manning_normal_depth({
        "Q": 100.0, "bottom_width_m": 8.0, "side_slope": 1.5,
        "manning_n": 0.035, "slope": 0.001,
    })
    checks.append({
        "name": "manning_monotonicity_depth_width",
        "depth_low_Q": m_low["normal_depth_m"], "depth_high_Q": m_high["normal_depth_m"],
        "width_low_Q": m_low["top_width_m"], "width_high_Q": m_high["top_width_m"],
        "passed": bool(m_high["normal_depth_m"] > m_low["normal_depth_m"]
                  and m_high["top_width_m"] > m_low["top_width_m"]),
    })

    # --- Check 8: Manning, caso rectangular (side_slope=0) contra formula
    # cerrada evaluada a mano: con z=0, A=b*h, P=b+2h, sin biseccion necesaria
    # para validar la funcion _manning_Q en si misma
    b, n_m, S0 = 5.0, 0.03, 0.002
    h_test = 1.2
    Q_manual, A_manual, P_manual, R_manual = _manning_Q(h_test, b, 0.0, n_m, S0)
    A_expected = b * h_test
    P_expected = b + 2 * h_test
    R_expected = A_expected / P_expected
    Q_expected = (1.0 / n_m) * A_expected * R_expected ** (2.0 / 3.0) * np.sqrt(S0)
    err_manual = abs(Q_manual - Q_expected) / Q_expected * 100
    checks.append({
        "name": "manning_rectangular_closed_form",
        "Q_computed": round(float(Q_manual), 6), "Q_expected": round(float(Q_expected), 6),
        "error_pct": round(err_manual, 9), "passed": bool(err_manual < 1e-9),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_flood_modeling(mode, params=None):
    params = params or {}

    if mode == "scs_triangular_hydrograph":
        return _mode_scs_triangular_hydrograph(params)
    elif mode == "muskingum_routing":
        return _mode_muskingum_routing(params)
    elif mode == "manning_normal_depth":
        return _mode_manning_normal_depth(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"Modo desconocido: {mode}")


if __name__ == "__main__":
    import json
    print(json.dumps(compute_flood_modeling("validate"), indent=2, ensure_ascii=False))

FLOOD_MODELING_TOOL_SCHEMA = {   'type': 'object',
    'properties': {'mode': {'type': 'string'}, 'params': {'type': 'object'}},
    'required': ['mode']}

try:
    from tool_registry import register_tool
    register_tool(
        name="flood_modeling_tool",
        schema={
        "name": "flood_modeling_tool",
        "description": 'Modelado de crecidas para planificacion de drenajes: scs_triangular_hydrograph (hidrograma unitario triangular SCS), muskingum_routing (transito de crecidas por un tramo de cauce), manning_normal_depth (tirante normal y ancho de inundacion en seccion trapezoidal via ecuacion de Manning).',
        "inputSchema": FLOOD_MODELING_TOOL_SCHEMA,
    },
        handler=lambda args: compute_flood_modeling(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass

