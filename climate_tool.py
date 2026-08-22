"""
climate_tool.py

Capa de física climática específica, patrón consistente con biorefinery_tool / gas_tool:
cada modo resuelve un caso concreto y se valida contra una solución analítica conocida
en vez de wrappear sin más los solvers genéricos ya existentes (integrate_stiff_ode,
pde_tool, cfd_tool, compute_bifurcation_diagram, population_dynamics, reaction_diffusion,
finite_element_tool).

Modos:
    - energy_balance_ebm
    - newton_cooling_trend
    - carbon_cycle_box
    - bifurcation_snowball
"""

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq


# ---------------------------------------------------------------------------
# Modo 1: energy_balance_ebm
# ---------------------------------------------------------------------------
def energy_balance_ebm(params=None):
    """
    Integra C dT/dt = Q/4 (1 - alpha(T)) - eps*sigma*T^4

    alpha(T) lineal por tramos entre alpha_ice (T <= T_ice) y alpha_water (T >= T_water),
    interpolado linealmente en el medio (si son iguales, albedo constante -> EBM clásico).

    Valida contra el punto de equilibrio analítico:
        T_eq = [ Q(1-alpha)/(4 eps sigma) ]^(1/4)
    usando el albedo constante (alpha_ice == alpha_water) para tener forma cerrada exacta.
    """
    p = params or {}
    Q = p.get("Q", 1361.0)          # W/m^2, constante solar
    eps = p.get("epsilon", 0.61)    # emisividad efectiva
    sigma = 5.670374419e-8          # W/m^2/K^4
    C = p.get("C", 2.08e8)          # J/m^2/K, capacidad calorífica efectiva
    alpha_ice = p.get("alpha_ice", 0.3)
    alpha_water = p.get("alpha_water", 0.3)
    T_ice = p.get("T_ice", 260.0)
    T_water = p.get("T_water", 280.0)
    T0 = p.get("T0", 288.0)
    t_span = p.get("t_span", (0.0, 3.15e9))  # ~100 años en segundos

    def albedo(T):
        if alpha_ice == alpha_water:
            return alpha_ice
        if T <= T_ice:
            return alpha_ice
        if T >= T_water:
            return alpha_water
        frac = (T - T_ice) / (T_water - T_ice)
        return alpha_ice + frac * (alpha_water - alpha_ice)

    def rhs(t, y):
        T = y[0]
        a = albedo(T)
        dTdt = (Q / 4.0 * (1.0 - a) - eps * sigma * T ** 4) / C
        return [dTdt]

    sol = solve_ivp(rhs, t_span, [T0], method="Radau", rtol=1e-9, atol=1e-9, dense_output=True)
    T_final_numeric = sol.y[0, -1]

    result = {
        "mode": "energy_balance_ebm",
        "T_final_numeric_K": float(T_final_numeric),
        "t_final_s": float(sol.t[-1]),
        "converged": bool(sol.success),
    }

    # Validación analítica: solo tiene forma cerrada exacta si el albedo es constante
    if alpha_ice == alpha_water:
        T_eq_analytic = (Q * (1.0 - alpha_ice) / (4.0 * eps * sigma)) ** 0.25
        rel_err = abs(T_final_numeric - T_eq_analytic) / T_eq_analytic
        result["validation"] = {
            "T_eq_analytic_K": float(T_eq_analytic),
            "relative_error": float(rel_err),
            "passed": bool(rel_err < 1e-4),
        }
    else:
        # con albedo variable puede haber multiestabilidad (relevante para bifurcation_snowball);
        # acá solo reportamos el punto fijo numérico alcanzado desde T0
        result["validation"] = {
            "note": "albedo variable: no hay forma cerrada única, ver bifurcation_snowball para el diagrama completo"
        }

    return result


# ---------------------------------------------------------------------------
# Modo 2: newton_cooling_trend
# ---------------------------------------------------------------------------
def newton_cooling_trend(params=None):
    """
    dT/dt = -k (T - Ta), solución cerrada T(t) = Ta + (T0 - Ta) exp(-k t)

    Valida la integración numérica contra la solución analítica en una grilla de tiempos.
    Útil para proyecciones simples de series de tiempo cortas (ajuste exponencial a una
    anomalía de temperatura relajando hacia un nuevo equilibrio Ta).
    """
    p = params or {}
    k = p.get("k", 0.05)         # 1/año
    Ta = p.get("Ta", 15.0)       # °C, temperatura de equilibrio asintótica
    T0 = p.get("T0", 14.0)       # °C, condición inicial
    t_end = p.get("t_end", 100.0)
    n_points = p.get("n_points", 200)

    t_eval = np.linspace(0, t_end, n_points)

    def rhs(t, y):
        return [-k * (y[0] - Ta)]

    sol = solve_ivp(rhs, (0, t_end), [T0], t_eval=t_eval, method="RK45", rtol=1e-10, atol=1e-10)
    T_numeric = sol.y[0]
    T_analytic = Ta + (T0 - Ta) * np.exp(-k * t_eval)

    max_abs_err = float(np.max(np.abs(T_numeric - T_analytic)))
    max_rel_err = float(np.max(np.abs((T_numeric - T_analytic) / (T_analytic - Ta + 1e-12))))

    return {
        "mode": "newton_cooling_trend",
        "t": t_eval.tolist(),
        "T_numeric": T_numeric.tolist(),
        "T_analytic": T_analytic.tolist(),
        "half_life": float(np.log(2) / k),
        "validation": {
            "max_abs_error": max_abs_err,
            "passed": bool(max_abs_err < 1e-6),
        },
    }


# ---------------------------------------------------------------------------
# Modo 3: carbon_cycle_box
# ---------------------------------------------------------------------------
def carbon_cycle_box(params=None):
    """
    Modelo de cajas atmósfera-océano-tierra (tipo CAMBIO / Bern simplificado).

    Compartimentos: M_atm, M_ocean, M_land (GtC)
    Flujos lineales k_ij * M_i (relajación hacia equilibrio) + F_ant(t) inyectado a la atmósfera.

    Valida por conservación de masa total: sin F_ant, la suma de los 3 compartimentos
    debe permanecer constante (dentro de tolerancia numérica) a lo largo de toda la integración.
    """
    p = params or {}
    M_atm0 = p.get("M_atm0", 850.0)
    M_ocean0 = p.get("M_ocean0", 38000.0)
    M_land0 = p.get("M_land0", 2000.0)

    k_ao = p.get("k_ao", 0.2)   # atm -> ocean
    k_oa = p.get("k_oa", 0.02)  # ocean -> atm
    k_al = p.get("k_al", 0.1)   # atm -> land
    k_la = p.get("k_la", 0.08)  # land -> atm

    F_ant_rate = p.get("F_ant_GtC_per_yr", 0.0)  # 0 => test de conservación pura
    t_end = p.get("t_end", 500.0)
    n_points = p.get("n_points", 500)

    def rhs(t, y):
        M_atm, M_ocean, M_land = y
        flux_ao = k_ao * M_atm
        flux_oa = k_oa * M_ocean
        flux_al = k_al * M_atm
        flux_la = k_la * M_land
        dM_atm = -flux_ao + flux_oa - flux_al + flux_la + F_ant_rate
        dM_ocean = flux_ao - flux_oa
        dM_land = flux_al - flux_la
        return [dM_atm, dM_ocean, dM_land]

    t_eval = np.linspace(0, t_end, n_points)
    sol = solve_ivp(rhs, (0, t_end), [M_atm0, M_ocean0, M_land0],
                     t_eval=t_eval, method="Radau", rtol=1e-10, atol=1e-8)

    total = sol.y[0] + sol.y[1] + sol.y[2]
    total0 = M_atm0 + M_ocean0 + M_land0

    result = {
        "mode": "carbon_cycle_box",
        "t": t_eval.tolist(),
        "M_atm": sol.y[0].tolist(),
        "M_ocean": sol.y[1].tolist(),
        "M_land": sol.y[2].tolist(),
        "F_ant_GtC_per_yr": F_ant_rate,
    }

    if F_ant_rate == 0.0:
        max_dev = float(np.max(np.abs(total - total0)))
        rel_dev = max_dev / total0
        result["validation"] = {
            "total0": float(total0),
            "max_deviation_GtC": max_dev,
            "relative_deviation": rel_dev,
            "passed": bool(rel_dev < 1e-6),
        }
    else:
        # con F_ant activo, la masa total inyectada debe calzar con el aumento observado
        expected_added = F_ant_rate * t_end
        actual_added = float(total[-1] - total0)
        rel_err = abs(actual_added - expected_added) / expected_added if expected_added != 0 else 0.0
        result["validation"] = {
            "expected_added_GtC": float(expected_added),
            "actual_added_GtC": actual_added,
            "relative_error": float(rel_err),
            "passed": bool(rel_err < 1e-4),
        }

    return result


# ---------------------------------------------------------------------------
# Modo 4: bifurcation_snowball
# ---------------------------------------------------------------------------
def bifurcation_snowball(params=None):
    """
    Modelo de Budyko-Sellers 0-D con albedo dependiente de T (histéresis / Snowball Earth).

    dT/dt = [ Q/4 (1 - alpha(T)) - (A + B T) ] / C

    con OLR linealizado A + B*T (parametrización de Budyko, T en grados CELSIUS -- esa es
    la convención estándar de A=201.4, B=1.45; usarla en Kelvin da puntos críticos fuera de
    todo rango físico) y albedo tipo step suavizado entre alpha_ice y alpha_water alrededor
    de T_crit.

    Encuentra los puntos de equilibrio (raíces de dT/dt=0) barriendo Q como parámetro de
    bifurcación, y valida contra los puntos de bifurcación conocidos del modelo de Budyko
    clásico (Q_crit para la aparición/desaparición de la rama congelada), calculados
    resolviendo el sistema tangente f(T)=0, f'(T)=0 en el propio caso límite de albedo
    escalón (alpha_ice/alpha_water constantes a cada lado de T_crit).
    """
    p = params or {}
    A = p.get("A", 201.4)          # W/m^2 (Budyko), T en °C
    B = p.get("B", 1.45)           # W/m^2/°C (Budyko)
    C = p.get("C", 2.08e8)         # no se usa para equilibrios, solo si se integra transitorio
    alpha_ice = p.get("alpha_ice", 0.62)
    alpha_water = p.get("alpha_water", 0.32)
    T_crit = p.get("T_crit", -10.0)      # °C, umbral clásico de línea de hielo en Budyko
    width = p.get("smooth_width", 0.3)   # ancho de suavizado del escalón, en °C (angosto para
                                          # que el numérico converja bien al límite de escalón puro)
    Q_range = p.get("Q_range", (900.0, 2100.0))
    n_Q = p.get("n_Q", 2000)
    T_range = p.get("T_range", (-60.0, 60.0))   # °C

    def albedo(T):
        # tanh suavizado entre alpha_water (T alto) y alpha_ice (T bajo)
        return alpha_water + (alpha_ice - alpha_water) * 0.5 * (1 - np.tanh((T - T_crit) / width))

    def f(T, Q):
        return Q / 4.0 * (1.0 - albedo(T)) - (A + B * T)

    Qs = np.linspace(Q_range[0], Q_range[1], n_Q)
    equilibria_branches = []  # lista de (Q, T_eq) para cada raíz encontrada
    T_grid = np.linspace(T_range[0], T_range[1], 4000)

    for Q in Qs:
        vals = f(T_grid, Q)
        sign_changes = np.where(np.diff(np.sign(vals)) != 0)[0]
        roots = []
        for idx in sign_changes:
            try:
                root = brentq(f, T_grid[idx], T_grid[idx + 1], args=(Q,))
                roots.append(root)
            except ValueError:
                continue
        for r in roots:
            equilibria_branches.append((Q, r))

    # Estabilidad: df/dT < 0 => estable
    def dfdT(T, Q, h=1e-3):
        return (f(T + h, Q) - f(T - h, Q)) / (2 * h)

    stable = [(Q, T) for (Q, T) in equilibria_branches if dfdT(T, Q) < 0]
    unstable = [(Q, T) for (Q, T) in equilibria_branches if dfdT(T, Q) >= 0]

    # --- Validación: caso límite de albedo tipo escalón puro (width -> 0) ---
    # En ese límite, para T < T_crit: f(T,Q) = Q/4(1-alpha_ice) - (A+B T)  (rama fría, lineal)
    # para T > T_crit: f(T,Q) = Q/4(1-alpha_water) - (A+B T)              (rama cálida, lineal)
    # Cada rama es lineal en T => a Q fijo hay a lo sumo una raíz por rama (sin pliegue propio),
    # así que la multiestabilidad viene de tener las DOS raíces (una de cada rama) coexistiendo
    # simultáneamente cuando T_crit cae dentro del rango donde ambas ramas dan T consistente.
    # Los Q de aparición/desaparición de la rama fría (Q_crit_low) y de la rama cálida (Q_crit_high)
    # son los valores de Q para los que la raíz de cada rama lineal cae exactamente en T_crit:
    #   T_crit = Q/4 (1-alpha) - A) / B  =>  Q_crit = 4*(A + B*T_crit)/(1-alpha)
    Q_crit_cold_branch = 4.0 * (A + B * T_crit) / (1.0 - alpha_ice)
    Q_crit_warm_branch = 4.0 * (A + B * T_crit) / (1.0 - alpha_water)

    # Con width finito, buscamos los Q donde el número de raíces reales cambia (los "saltos"
    # del diagrama de bifurcación numérico) y los comparamos contra estos valores límite.
    root_counts = []
    for Q in Qs:
        vals = f(T_grid, Q)
        sign_changes = np.where(np.diff(np.sign(vals)) != 0)[0]
        root_counts.append(len(sign_changes))
    root_counts = np.array(root_counts)
    transition_idx = np.where(np.diff(root_counts) != 0)[0]
    Q_transitions_numeric = Qs[transition_idx].tolist()

    tol = 0.02 * (Q_range[1] - Q_range[0])  # tolerancia moderada porque width>0 desplaza la transición
    match_low = any(abs(qt - Q_crit_cold_branch) < tol for qt in Q_transitions_numeric) if Q_transitions_numeric else False
    match_high = any(abs(qt - Q_crit_warm_branch) < tol for qt in Q_transitions_numeric) if Q_transitions_numeric else False

    return {
        "mode": "bifurcation_snowball",
        "Q_stable_branch": [q for q, _ in stable],
        "T_stable_branch": [t for _, t in stable],
        "Q_unstable_branch": [q for q, _ in unstable],
        "T_unstable_branch": [t for _, t in unstable],
        "Q_transitions_numeric": Q_transitions_numeric,
        "validation": {
            "Q_crit_cold_branch_analytic": float(Q_crit_cold_branch),
            "Q_crit_warm_branch_analytic": float(Q_crit_warm_branch),
            "matched_low_transition": bool(match_low),
            "matched_high_transition": bool(match_high),
            "passed": bool(match_low and match_high),
            "note": "tolerancia amplia porque el suavizado tanh (width>0) desplaza la transición respecto del límite de escalón puro",
        },
    }


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
def validate(params=None):
    checks = []
    for m in ["energy_balance_ebm", "newton_cooling_trend", "carbon_cycle_box", "bifurcation_snowball"]:
        r = compute_climate(m)
        v = r.get("validation", {})
        passed = bool(v.get("passed", False))
        checks.append({
            "name": f"climate_{m}_validation_interna_passed",
            "passed": passed,
            "detail": {k: val for k, val in v.items() if k != "passed"},
        })
    all_pass = all(c["passed"] for c in checks)
    return {
        "validation_passed": all_pass,
        "n_checks": len(checks),
        "checks": checks,
    }


def compute_climate(mode, params=None):
    modes = {
        "validate": validate,
        "energy_balance_ebm": energy_balance_ebm,
        "newton_cooling_trend": newton_cooling_trend,
        "carbon_cycle_box": carbon_cycle_box,
        "bifurcation_snowball": bifurcation_snowball,
    }
    if mode not in modes:
        raise ValueError(f"modo desconocido: {mode}. Modos válidos: {list(modes.keys())}")
    return modes[mode](params)


if __name__ == "__main__":
    import json
    for m in ["energy_balance_ebm", "newton_cooling_trend", "carbon_cycle_box", "bifurcation_snowball"]:
        r = compute_climate(m)
        v = r.get("validation", {})
        print(f"--- {m} ---")
        print(json.dumps(v, indent=2, ensure_ascii=False))
        print()

CLIMATE_TOOL_SCHEMA = {   'type': 'object',
    'properties': {   'mode': {   'type': 'string',
                                  'enum': [   'energy_balance_ebm',
                                              'newton_cooling_trend',
                                              'carbon_cycle_box',
                                              'bifurcation_snowball',
                                              'validate']},
                      'params': {   'type': 'object',
                                    'description': 'Parametros especificos del modo (opcional, '
                                                   'cada modo trae defaults razonables).'}},
    'required': ['mode']}

try:
    from tool_registry import register_tool
    register_tool(
        name="climate_tool",
        schema={
        "name": "climate_tool",
        "description": 'Fisica climatica especifica con validacion analitica. Modos: energy_balance_ebm (balance de energia 0-D, punto de equilibrio T_eq), newton_cooling_trend (relajacion exponencial dT/dt=-k(T-Ta), proyeccion de series cortas), carbon_cycle_box (modelo de cajas atmosfera-oceano-tierra, conservacion de masa), bifurcation_snowball (histeresis albedo-temperatura tipo Budyko-Sellers, Snowball Earth).',
        "inputSchema": CLIMATE_TOOL_SCHEMA,
    },
        handler=lambda args: compute_climate(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass

