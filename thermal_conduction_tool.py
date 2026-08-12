"""
thermal_conduction_tool.py
Conduccion de calor FEM: 1D estacionario (con generacion volumetrica opcional)
y 1D transitorio (Crank-Nicolson).

Modos:
  - steady_1d    : barra/pared 1D, FEM lineal, Dirichlet en ambos extremos,
                    generacion volumetrica uniforme opcional
  - transient_1d : misma barra, condicion inicial uniforme, extremos fijados
                    a T=0 en t=0+, integracion Crank-Nicolson en el tiempo

Validado contra:
  - steady_1d (q_gen=0):  T(x) = T0 + (TL-T0)*x/L                          (perfil lineal)
  - steady_1d (q_gen!=0): T(x) = T0 + [(TL-T0)/L + q*L/(2k)]*x - q/(2k)*x^2 (parabola exacta,
                           de k*T''=-q con T(0)=T0, T(L)=TL)
  - transient_1d:         theta(x,t) = sum_{n=1,3,5,...} (4/(n*pi))*Ti*sin(n*pi*x/L)
                                        * exp(-n^2*pi^2*alpha*t/L^2)
                           (serie de Fourier, losa con ambos extremos a T=0 para t>0,
                           condicion inicial uniforme Ti -- caso estandar de libro de
                           texto, ej. Incropera / Carslaw & Jaeger)
"""
import numpy as np

THERMAL_CONDUCTION_TOOL_SCHEMA = {
    "name": "thermal_conduction_tool",
    "description": (
        "Conduccion de calor FEM: steady_1d (barra 1D estacionaria, Dirichlet en "
        "ambos extremos, generacion volumetrica uniforme opcional) y transient_1d "
        "(misma barra, Crank-Nicolson en el tiempo, extremos fijados a T=0 en "
        "t=0+). Validado contra soluciones analiticas de libro de texto (perfil "
        "lineal/parabolico en steady, serie de Fourier en transient)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["steady_1d", "transient_1d", "validate"]},
            "params": {"type": "object", "description": "Parametros especificos de cada modo, ver docstring."},
        },
        "required": ["mode"],
    },
}


def _steady_1d(k=200.0, A=0.001, L=1.0, T0=100.0, TL=20.0, q_gen=0.0, n_el=20):
    """
    k [W/m/K], A [m^2], L [m], T0/TL: Dirichlet en x=0 / x=L,
    q_gen [W/m^3]: generacion volumetrica uniforme (default 0).
    """
    n_nodes = n_el + 1
    le = L / n_el
    x = np.linspace(0.0, L, n_nodes)

    ke = (k * A / le) * np.array([[1, -1], [-1, 1]])
    K = np.zeros((n_nodes, n_nodes))
    for e in range(n_el):
        K[e:e + 2, e:e + 2] += ke

    fe = q_gen * A * le / 2.0 * np.array([1.0, 1.0])
    F = np.zeros(n_nodes)
    for e in range(n_el):
        F[e:e + 2] += fe

    free = list(range(1, n_nodes - 1))
    T_full = np.zeros(n_nodes)
    T_full[0] = T0
    T_full[-1] = TL
    if free:
        F_mod = (F[free]
                  - K[np.ix_(free, [0])].flatten() * T0
                  - K[np.ix_(free, [n_nodes - 1])].flatten() * TL)
        Kff = K[np.ix_(free, free)]
        T_full[free] = np.linalg.solve(Kff, F_mod)

    if q_gen == 0.0:
        T_analytic = T0 + (TL - T0) * x / L
    else:
        C1 = (TL - T0) / L + q_gen * L / (2.0 * k)
        T_analytic = T0 + C1 * x - q_gen / (2.0 * k) * x**2

    err = np.abs(T_full - T_analytic)
    denom = np.maximum(np.abs(T_analytic), 1e-9)
    rel_err_pct = float(np.max(100.0 * err / denom))

    return {
        "mode": "steady_1d",
        "x": x.tolist(),
        "temperature_fem": T_full.tolist(),
        "temperature_analytic": T_analytic.tolist(),
        "max_relative_error_pct": rel_err_pct,
    }


def _transient_1d(k=200.0, rho=8000.0, cp=500.0, A=0.001, L=1.0, T_i=100.0,
                   n_el=20, t_final=50.0, n_steps=500, n_fourier_terms=99,
                   eval_fraction=0.5):
    """
    Condicion inicial T(x,0)=T_i uniforme; T(0,t)=T(L,t)=0 para t>0.
    k [W/m/K], rho [kg/m^3], cp [J/kg/K] -> alpha = k/(rho*cp).
    eval_fraction: fraccion de t_final en la que se compara max_relative_error_pct
    (t_final en si puede tener theta~0 en los extremos y errores relativos ruidosos
    solo ahi; se reporta tambien el estado final completo igualmente).
    """
    alpha = k / (rho * cp)
    n_nodes = n_el + 1
    le = L / n_el
    x = np.linspace(0.0, L, n_nodes)
    dt = t_final / n_steps

    ke = (k * A / le) * np.array([[1, -1], [-1, 1]])
    me = (rho * cp * A * le / 6.0) * np.array([[2, 1], [1, 2]])
    K = np.zeros((n_nodes, n_nodes))
    M = np.zeros((n_nodes, n_nodes))
    for e in range(n_el):
        K[e:e + 2, e:e + 2] += ke
        M[e:e + 2, e:e + 2] += me

    T = np.full(n_nodes, float(T_i))
    T[0] = 0.0
    T[-1] = 0.0

    free = list(range(1, n_nodes - 1))
    Mff = M[np.ix_(free, free)]
    Kff = K[np.ix_(free, free)]
    A_lhs = Mff / dt + Kff / 2.0
    A_rhs = Mff / dt - Kff / 2.0

    eval_time = eval_fraction * t_final
    n_eval_steps = int(round(eval_time / dt))
    T_at_eval = None

    for step in range(n_steps):
        rhs = A_rhs @ T[free]
        T[free] = np.linalg.solve(A_lhs, rhs)
        T[0] = 0.0
        T[-1] = 0.0
        if step + 1 == n_eval_steps:
            T_at_eval = T.copy()

    if T_at_eval is None:
        T_at_eval = T.copy()

    def fourier_solution(t):
        n_range = np.arange(1, 2 * n_fourier_terms, 2)
        T_an = np.zeros(n_nodes)
        for n in n_range:
            coeff = (4.0 / (n * np.pi)) * T_i
            T_an += coeff * np.sin(n * np.pi * x / L) * np.exp(-(n**2) * (np.pi**2) * alpha * t / L**2)
        return T_an

    T_analytic_eval = fourier_solution(eval_time)
    T_analytic_final = fourier_solution(t_final)

    denom = np.maximum(np.abs(T_analytic_eval), 1e-3 * T_i)
    mask = np.abs(T_analytic_eval) > 1e-3 * T_i
    err = np.abs(T_at_eval - T_analytic_eval)
    rel_err_pct = float(np.max(100.0 * err[mask] / denom[mask])) if mask.any() else 0.0

    return {
        "mode": "transient_1d",
        "t_eval": eval_time,
        "t_final": t_final,
        "x": x.tolist(),
        "temperature_fem_at_t_eval": T_at_eval.tolist(),
        "temperature_analytic_at_t_eval": T_analytic_eval.tolist(),
        "temperature_fem_at_t_final": T.tolist(),
        "temperature_analytic_at_t_final": T_analytic_final.tolist(),
        "max_relative_error_pct": rel_err_pct,
    }


def _mode_validate():
    r_lin = _steady_1d(k=15.0, A=0.01, L=1.0, T0=100.0, TL=20.0, q_gen=0.0, n_el=20)
    r_gen = _steady_1d(k=15.0, A=0.01, L=1.0, T0=100.0, TL=20.0, q_gen=5e4, n_el=20)
    r_trans = _transient_1d(k=15.0, rho=7800.0, cp=460.0, A=0.01, L=0.1, T_i=100.0,
                             n_el=40, t_final=358.8, n_steps=1600, eval_fraction=0.5)

    checks = {
        "steady_linear_matches_analytic": r_lin["max_relative_error_pct"] < 1e-6,
        "steady_generation_matches_analytic": r_gen["max_relative_error_pct"] < 1.0,
        "transient_matches_fourier_series": r_trans["max_relative_error_pct"] < 1.0,
    }
    return {
        "mode": "validate",
        "steady_1d_linear": r_lin,
        "steady_1d_with_generation": r_gen,
        "transient_1d": r_trans,
        "checks": checks,
        "expected": (
            "steady_1d sin generacion: perfil exactamente lineal (FEM lineal es "
            "exacto para conduccion pura sin generacion, error debe ser ~0). Con "
            "generacion uniforme: parabola exacta de k*T''=-q, error <1%%. "
            "transient_1d: coincide con la serie de Fourier de la losa con "
            "extremos a T=0 y condicion inicial uniforme (Incropera / Carslaw & "
            "Jaeger), error <1%% lejos de los extremos."
        ),
        "validation_passed": all(checks.values()),
    }


def compute_thermal_conduction(mode, params=None):
    params = params or {}
    if mode == "steady_1d":
        return _steady_1d(**params)
    elif mode == "transient_1d":
        return _transient_1d(**params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(f"modo desconocido: {mode}. Use steady_1d | transient_1d | validate")


if __name__ == "__main__":
    import json
    print(json.dumps(compute_thermal_conduction("validate"), indent=2))
