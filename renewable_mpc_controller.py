"""
renewable_mpc_controller.py

Control predictivo (MPC) de despacho economico para microrred aislada o
conectada a red: PV + eolica + bateria + red, horizonte rodante.

Fisica/optimizacion (formulacion estandar de MPC economico para
microrredes, formulas de dominio publico re-derivadas aca):

  Variables de decision por paso t=0..N-1:
    pc[t]  potencia de carga de bateria (kW, >=0)
    pd[t]  potencia de descarga de bateria (kW, >=0)
    gi[t]  potencia importada de red (kW, >=0)
    ge[t]  potencia exportada a red (kW, >=0)
  y estado soc[t] (kWh) para t=0..N.

  Balance de energia en cada paso (igualdad):
    pv[t] + wind[t] + pd[t] + gi[t] = load[t] + pc[t] + ge[t]

  Dinamica de SoC (igualdad, con perdidas de carga/descarga separadas):
    soc[t+1] = soc[t] + dt*(eta_charge*pc[t] - pd[t]/eta_discharge)

  Costo (a minimizar), horizonte N pasos de duracion dt cada uno:
    J = sum_t dt * (price_buy[t]*gi[t] - price_sell[t]*ge[t])
        [+ lambda_smooth * sum_t (pc[t]^2 + pd[t]^2)   solo modo QP]

  El problema con costo puramente lineal (sin termino de suavizado) es un
  LP (variables y restricciones todas lineales) -- se resuelve exacto con
  scipy.optimize.linprog, method="highs". Si se agrega penalizacion
  cuadratica de la potencia de bateria (para desalentar ciclado agresivo
  / degradacion), el problema pasa a QP y se resuelve con
  scipy.optimize.minimize, method="SLSQP", usando la solucion LP como
  punto inicial (warm start).

  No se usa cvxpy/osqp: scipy ya es dependencia del repo (game_theory_tool,
  climate_tool, econometrics_tool) y alcanza para los tamanos de horizonte
  tipicos de MPC economico horario (N=24 a N=96), sin agregar dependencia
  nueva.

CUIDADO DE CONFIANZA DE DATOS:
  - formulacion LP/QP y solver: alta -- linprog HiGHS es exacto para LP;
    SLSQP converge a optimo local pero el problema QP aca es convexo
    (Hessiano diagonal >=0), por lo que el optimo local es global.
  - los forecasts de entrada (pv, wind, load, precios) son responsabilidad
    del usuario -- esta tool NO pronostica, solo optimiza el despacho dado
    el forecast. Precision del resultado = precision del forecast (tipico
    de MPC: se resuelve cada paso con el forecast actualizado, horizonte
    rodante, solo se ejecuta el primer paso de la solucion).
  - eficiencias de carga/descarga: valores tipicos de literatura si no se
    especifican (0.95/0.95, round-trip ~0.90), NO reemplazan curva real
    del inversor/BMS elegido.
"""
import math

try:
    import numpy as np
except ImportError:
    np = None

try:
    from scipy.optimize import linprog, minimize
except ImportError:
    linprog = None
    minimize = None


def _broadcast(x, n, name):
    if x is None:
        raise ValueError(f"falta {name}")
    if isinstance(x, (int, float)):
        return [float(x)] * n
    x = list(x)
    if len(x) != n:
        raise ValueError(f"{name} debe tener longitud {n} (horizonte), tiene {len(x)}")
    return [float(v) for v in x]


def _build_problem(params):
    if np is None or linprog is None:
        raise RuntimeError("requiere numpy y scipy instalados")

    n = int(params.get("horizon_steps", 24))
    dt = float(params.get("dt_h", 1.0))

    pv = _broadcast(params.get("pv_forecast_kW"), n, "pv_forecast_kW")
    wind = _broadcast(params.get("wind_forecast_kW"), n, "wind_forecast_kW")
    load = _broadcast(params.get("load_forecast_kW"), n, "load_forecast_kW")
    price_buy = _broadcast(params.get("price_buy"), n, "price_buy")
    price_sell = _broadcast(params.get("price_sell"), n, "price_sell")

    soc_init = params.get("soc_init_kWh")
    soc_min = params.get("soc_min_kWh")
    soc_max = params.get("soc_max_kWh")
    if soc_init is None or soc_min is None or soc_max is None:
        raise ValueError("faltan soc_init_kWh, soc_min_kWh, soc_max_kWh")
    if not (soc_min <= soc_init <= soc_max):
        raise ValueError("soc_init_kWh debe estar entre soc_min_kWh y soc_max_kWh")

    soc_target = params.get("soc_target_kWh")  # None = libre dentro de [min,max]

    batt_charge_max = float(params.get("batt_charge_max_kW", params.get("batt_power_max_kW", 0.0)))
    batt_discharge_max = float(params.get("batt_discharge_max_kW", params.get("batt_power_max_kW", 0.0)))
    eta_charge = float(params.get("eta_charge", 0.95))
    eta_discharge = float(params.get("eta_discharge", 0.95))

    grid_import_max = params.get("grid_import_max_kW")
    grid_export_max = params.get("grid_export_max_kW")
    grid_import_max = float(grid_import_max) if grid_import_max is not None else 1e6
    grid_export_max = float(grid_export_max) if grid_export_max is not None else 1e6

    if eta_charge <= 0 or eta_discharge <= 0:
        raise ValueError("eta_charge y eta_discharge deben ser > 0")

    # layout de variables: [pc(n), pd(n), gi(n), ge(n), soc(n+1)]
    nv = 4 * n + (n + 1)

    def idx_pc(t):
        return t

    def idx_pd(t):
        return n + t

    def idx_gi(t):
        return 2 * n + t

    def idx_ge(t):
        return 3 * n + t

    def idx_soc(t):
        return 4 * n + t

    c = [0.0] * nv
    for t in range(n):
        c[idx_gi(t)] = dt * price_buy[t]
        c[idx_ge(t)] = -dt * price_sell[t]

    A_eq = []
    b_eq = []

    # balance de energia
    for t in range(n):
        row = [0.0] * nv
        row[idx_pd(t)] = 1.0
        row[idx_gi(t)] = 1.0
        row[idx_pc(t)] = -1.0
        row[idx_ge(t)] = -1.0
        A_eq.append(row)
        b_eq.append(load[t] - pv[t] - wind[t])

    # dinamica de soc
    for t in range(n):
        row = [0.0] * nv
        row[idx_soc(t + 1)] = 1.0
        row[idx_soc(t)] = -1.0
        row[idx_pc(t)] = -dt * eta_charge
        row[idx_pd(t)] = dt / eta_discharge
        A_eq.append(row)
        b_eq.append(0.0)

    bounds = [(0.0, batt_charge_max)] * n
    bounds += [(0.0, batt_discharge_max)] * n
    bounds += [(0.0, grid_import_max)] * n
    bounds += [(0.0, grid_export_max)] * n
    soc_bounds = [(soc_min, soc_max)] * (n + 1)
    soc_bounds[0] = (soc_init, soc_init)
    if soc_target is not None:
        soc_bounds[n] = (soc_target, soc_target)
    bounds += soc_bounds

    return dict(
        n=n, dt=dt, pv=pv, wind=wind, load=load, price_buy=price_buy, price_sell=price_sell,
        soc_init=soc_init, soc_min=soc_min, soc_max=soc_max, soc_target=soc_target,
        batt_charge_max=batt_charge_max, batt_discharge_max=batt_discharge_max,
        eta_charge=eta_charge, eta_discharge=eta_discharge,
        grid_import_max=grid_import_max, grid_export_max=grid_export_max,
        nv=nv, c=c, A_eq=A_eq, b_eq=b_eq, bounds=bounds,
        idx_pc=idx_pc, idx_pd=idx_pd, idx_gi=idx_gi, idx_ge=idx_ge, idx_soc=idx_soc,
    )


def _extract_schedule(x, prob):
    n = prob["n"]
    pc = [round(float(x[prob["idx_pc"](t)]), 6) for t in range(n)]
    pd = [round(float(x[prob["idx_pd"](t)]), 6) for t in range(n)]
    gi = [round(float(x[prob["idx_gi"](t)]), 6) for t in range(n)]
    ge = [round(float(x[prob["idx_ge"](t)]), 6) for t in range(n)]
    soc = [round(float(x[prob["idx_soc"](t)]), 6) for t in range(n + 1)]
    net_cost = sum(prob["dt"] * (prob["price_buy"][t] * gi[t] - prob["price_sell"][t] * ge[t]) for t in range(n))
    return dict(
        batt_charge_kW=pc, batt_discharge_kW=pd,
        grid_import_kW=gi, grid_export_kW=ge, soc_kWh=soc,
        net_cost=round(net_cost, 6),
        soc_final_kWh=soc[n],
    )


def _dispatch_lp(params):
    prob = _build_problem(params)
    res = linprog(prob["c"], A_eq=prob["A_eq"], b_eq=prob["b_eq"], bounds=prob["bounds"], method="highs")
    if not res.success:
        raise RuntimeError(f"LP no convergio: {res.message}")
    out = _extract_schedule(res.x, prob)
    out["solver"] = "linprog-highs"
    out["horizon_steps"] = prob["n"]
    out["dt_h"] = prob["dt"]
    out["objective"] = "costo_neto_grid"
    return out


def _dispatch_qp(params):
    if minimize is None:
        raise RuntimeError("requiere scipy.optimize.minimize (SLSQP)")
    prob = _build_problem(params)
    n = prob["n"]
    lam = float(params.get("smoothing_lambda", 0.0))

    c_arr = np.array(prob["c"])
    A_eq = np.array(prob["A_eq"])
    b_eq = np.array(prob["b_eq"])

    def objective(x):
        lin = float(c_arr @ x)
        quad = lam * float(np.sum(x[:n] ** 2) + np.sum(x[n:2 * n] ** 2))
        return lin + quad

    def jac(x):
        g = c_arr.copy()
        g[:n] += 2 * lam * x[:n]
        g[n:2 * n] += 2 * lam * x[n:2 * n]
        return g

    # warm start: solucion LP (lambda=0 es exactamente el caso LP)
    lp_res = linprog(prob["c"], A_eq=prob["A_eq"], b_eq=prob["b_eq"], bounds=prob["bounds"], method="highs")
    if not lp_res.success:
        raise RuntimeError(f"warm-start LP no convergio: {lp_res.message}")
    x0 = lp_res.x

    constraints = [{"type": "eq", "fun": (lambda x, row=A_eq[i], rhs=b_eq[i]: float(row @ x - rhs))}
                   for i in range(A_eq.shape[0])]

    res = minimize(objective, x0, jac=jac, method="SLSQP", bounds=prob["bounds"],
                    constraints=constraints, options={"maxiter": 300, "ftol": 1e-9})
    if not res.success:
        raise RuntimeError(f"QP (SLSQP) no convergio: {res.message}")

    out = _extract_schedule(res.x, prob)
    out["solver"] = "SLSQP-warmstart-LP"
    out["horizon_steps"] = n
    out["dt_h"] = prob["dt"]
    out["smoothing_lambda"] = lam
    out["objective"] = "costo_neto_grid + lambda*potencia_bateria^2"
    return out


def _validate():
    checks = []

    # 1) sin bateria: despacho debe coincidir con balance instantaneo (miope)
    n = 4
    p1 = dict(
        horizon_steps=n, dt_h=1.0,
        pv_forecast_kW=[0.0, 2.0, 5.0, 1.0],
        wind_forecast_kW=[1.0, 1.0, 1.0, 1.0],
        load_forecast_kW=[3.0, 3.0, 3.0, 3.0],
        price_buy=0.20, price_sell=0.05,
        soc_init_kWh=5.0, soc_min_kWh=5.0, soc_max_kWh=5.0,
        batt_power_max_kW=0.0,
    )
    r1 = _dispatch_lp(p1)
    expected_gi = [max(0.0, p1["load_forecast_kW"][t] - p1["pv_forecast_kW"][t] - p1["wind_forecast_kW"][t]) for t in range(n)]
    expected_ge = [max(0.0, -(p1["load_forecast_kW"][t] - p1["pv_forecast_kW"][t] - p1["wind_forecast_kW"][t])) for t in range(n)]
    ok1 = all(abs(r1["grid_import_kW"][t] - expected_gi[t]) < 1e-6 and abs(r1["grid_export_kW"][t] - expected_ge[t]) < 1e-6 for t in range(n))
    checks.append({"case": "sin_bateria: dispatch = balance instantaneo (miope)",
                    "got": {"gi": r1["grid_import_kW"], "ge": r1["grid_export_kW"]},
                    "expected": {"gi": expected_gi, "ge": expected_ge}, "ok": ok1})

    # 2) precio plano + eta=1 + soc cerrado (soc_final=soc_init): costo optimo
    #    NO depende de como se despache la bateria (no hay arbitraje posible),
    #    debe igualar el costo del balance sin bateria.
    n2 = 6
    price_flat = 0.15
    pv2 = [0.0, 0.0, 3.0, 6.0, 4.0, 0.0]
    wind2 = [1.0] * n2
    load2 = [2.0] * n2
    p2 = dict(
        horizon_steps=n2, dt_h=1.0,
        pv_forecast_kW=pv2, wind_forecast_kW=wind2, load_forecast_kW=load2,
        price_buy=price_flat, price_sell=price_flat,
        soc_init_kWh=10.0, soc_min_kWh=0.0, soc_max_kWh=20.0, soc_target_kWh=10.0,
        batt_charge_max_kW=5.0, batt_discharge_max_kW=5.0,
        eta_charge=1.0, eta_discharge=1.0,
    )
    r2 = _dispatch_lp(p2)
    net_no_batt = [load2[t] - pv2[t] - wind2[t] for t in range(n2)]
    expected_cost2 = sum(price_flat * max(0.0, v) - price_flat * max(0.0, -v) for v in net_no_batt)
    ok2 = abs(r2["net_cost"] - expected_cost2) < 1e-6
    checks.append({"case": "precio_plano+eta1+soc_cerrado: costo optimo = costo sin bateria (no hay arbitraje gratis)",
                    "got": r2["net_cost"], "expected": round(expected_cost2, 6), "ok": ok2})

    # 3) arbitraje puro (sin generacion): bateria debe cargar en la hora mas
    #    barata y descargar en la mas cara.
    n3 = 4
    price3 = [0.10, 0.50, 0.10, 0.50]
    p3 = dict(
        horizon_steps=n3, dt_h=1.0,
        pv_forecast_kW=[0.0] * n3, wind_forecast_kW=[0.0] * n3, load_forecast_kW=[2.0] * n3,
        price_buy=price3, price_sell=price3,
        soc_init_kWh=5.0, soc_min_kWh=0.0, soc_max_kWh=10.0,
        batt_charge_max_kW=3.0, batt_discharge_max_kW=3.0,
        eta_charge=0.95, eta_discharge=0.95,
    )
    r3 = _dispatch_lp(p3)
    cheap_idx = [t for t, pr in enumerate(price3) if pr == min(price3)]
    exp_idx = [t for t, pr in enumerate(price3) if pr == max(price3)]
    charges_at_cheap = any(r3["batt_charge_kW"][t] > 1e-3 for t in cheap_idx)
    discharges_at_expensive = any(r3["batt_discharge_kW"][t] > 1e-3 for t in exp_idx)
    checks.append({"case": "arbitraje: bateria carga en hora barata y descarga en hora cara",
                    "got": {"charge": r3["batt_charge_kW"], "discharge": r3["batt_discharge_kW"], "price": price3},
                    "expected": "carga>0 en argmin(price), descarga>0 en argmax(price)",
                    "ok": charges_at_cheap and discharges_at_expensive})

    # 4) factibilidad: soc siempre dentro de [min,max] en todos los casos anteriores
    all_soc = r1["soc_kWh"] + r2["soc_kWh"] + r3["soc_kWh"]
    bounds_ok = (all(5.0 - 1e-6 <= v <= 5.0 + 1e-6 for v in r1["soc_kWh"]) and
                 all(0.0 - 1e-6 <= v <= 20.0 + 1e-6 for v in r2["soc_kWh"]) and
                 all(0.0 - 1e-6 <= v <= 10.0 + 1e-6 for v in r3["soc_kWh"]))
    checks.append({"case": "factibilidad: soc dentro de [soc_min, soc_max] en todos los pasos",
                    "got": "dentro de rango" if bounds_ok else "fuera de rango", "expected": "dentro de rango", "ok": bounds_ok})

    # 5) QP con suavizado: perfil de potencia de bateria debe ser mas suave
    #    (menor suma de diferencias al cuadrado) que el LP para el mismo caso.
    p5 = dict(p3)
    p5["smoothing_lambda"] = 0.5
    r5 = _dispatch_qp(p5)

    def _roughness(pc, pd):
        net = [pc[t] - pd[t] for t in range(len(pc))]
        return sum((net[t + 1] - net[t]) ** 2 for t in range(len(net) - 1))

    rough_lp = _roughness(r3["batt_charge_kW"], r3["batt_discharge_kW"])
    rough_qp = _roughness(r5["batt_charge_kW"], r5["batt_discharge_kW"])
    ok5 = rough_qp <= rough_lp + 1e-6
    checks.append({"case": "QP con lambda>0: perfil de potencia de bateria mas (o igual) suave que LP",
                    "got": {"roughness_lp": round(rough_lp, 6), "roughness_qp": round(rough_qp, 6)},
                    "expected": "roughness_qp <= roughness_lp", "ok": ok5})

    # 6) QP con lambda=0 debe coincidir con LP (mismo optimo)
    p6 = dict(p3)
    p6["smoothing_lambda"] = 0.0
    r6 = _dispatch_qp(p6)
    ok6 = abs(r6["net_cost"] - r3["net_cost"]) < 1e-4
    checks.append({"case": "QP lambda=0 coincide con LP (mismo costo optimo)",
                    "got": r6["net_cost"], "expected": r3["net_cost"], "ok": ok6})

    return {"validate": True, "all_passed": all(c["ok"] for c in checks), "checks": checks}


def compute_renewable_mpc_controller(mode, params=None):
    params = params or {}
    if mode == "dispatch_lp":
        return _dispatch_lp(params)
    elif mode == "dispatch_qp":
        return _dispatch_qp(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            f"mode desconocido: {mode!r}. Valores validos: dispatch_lp, dispatch_qp, validate."
        )


RENEWABLE_MPC_CONTROLLER_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["dispatch_lp", "dispatch_qp", "validate"],
            "default": "dispatch_lp",
        },
        "horizon_steps": {"type": "integer", "default": 24, "description": "N pasos del horizonte MPC (ej. 24 = 24h con dt=1h)."},
        "dt_h": {"type": "number", "default": 1.0, "description": "Duracion de cada paso en horas."},
        "pv_forecast_kW": {"type": "array", "items": {"type": "number"}, "description": "Forecast PV, longitud horizon_steps."},
        "wind_forecast_kW": {"type": "array", "items": {"type": "number"}, "description": "Forecast eolico, longitud horizon_steps."},
        "load_forecast_kW": {"type": "array", "items": {"type": "number"}, "description": "Forecast de carga, longitud horizon_steps."},
        "price_buy": {"description": "Precio compra ($/kWh), escalar o arreglo por paso."},
        "price_sell": {"description": "Precio venta ($/kWh), escalar o arreglo por paso."},
        "soc_init_kWh": {"type": "number"},
        "soc_min_kWh": {"type": "number"},
        "soc_max_kWh": {"type": "number"},
        "soc_target_kWh": {"type": "number", "description": "Opcional, fija soc final del horizonte (ej. igual a soc_init para horizonte rodante cerrado)."},
        "batt_power_max_kW": {"type": "number", "description": "Atajo: usa el mismo limite para carga y descarga."},
        "batt_charge_max_kW": {"type": "number"},
        "batt_discharge_max_kW": {"type": "number"},
        "eta_charge": {"type": "number", "default": 0.95},
        "eta_discharge": {"type": "number", "default": 0.95},
        "grid_import_max_kW": {"type": "number", "description": "Opcional, limite de importacion de red."},
        "grid_export_max_kW": {"type": "number", "description": "Opcional, limite de exportacion de red."},
        "smoothing_lambda": {"type": "number", "default": 0.0, "description": "Solo dispatch_qp: peso de penalizacion cuadratica de potencia de bateria (suaviza ciclado)."},
    },
    "required": ["mode"],
}


try:
    from tool_registry import register_tool
    register_tool(
        name="renewable_mpc_controller",
        schema={
            "name": "renewable_mpc_controller",
            "description": (
                "MPC de despacho economico para microrred PV+eolica+bateria+red, "
                "horizonte rodante. dispatch_lp resuelve el problema lineal exacto "
                "(scipy linprog HiGHS): minimiza costo neto de red (compra-venta) "
                "sujeto a balance de energia y dinamica de SoC. dispatch_qp agrega "
                "penalizacion cuadratica de potencia de bateria (smoothing_lambda) "
                "para desalentar ciclado agresivo, resuelto con SLSQP con warm-start "
                "desde la solucion LP."
            ),
            "inputSchema": RENEWABLE_MPC_CONTROLLER_TOOL_SCHEMA,
        },
        handler=lambda args: compute_renewable_mpc_controller(args.get("mode"), args),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    print(json.dumps(compute_renewable_mpc_controller("validate"), indent=2, ensure_ascii=False))
