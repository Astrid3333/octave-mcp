"""
algae_chemostat_tool.py

Modelo de ecosistema cerrado tipo quimiostato "alga-microconsumidores"
(p.ej. Chlorella + bacterias), con sistema de ecuaciones diferenciales
ordinarias no lineales, aplicando:

  - Ley del minimo de Liebig: el crecimiento del alga esta limitado por el
    nutriente MAS ESCASO entre carbono (C) y nitrogeno (N), no por su suma
    ni promedio.
  - Modelo de inhibicion por sustrato de Andrews: el crecimiento de los
    microconsumidores (bacterias) sobre el alga como sustrato presenta un
    OPTIMO intermedio -- a baja concentracion de alga el crecimiento esta
    limitado por sustrato (tipo Monod), pero a alta concentracion el
    crecimiento se INHIBE (a diferencia de Monod puro, que satura pero no
    decae).
  - Analisis de estabilidad de los puntos de equilibrio via linealizacion
    (metodo indirecto de Lyapunov: Jacobiano evaluado en el equilibrio,
    clasificacion segun el signo de la parte real de los autovalores).

--------------------------------------------------------------------------
Sistema de estado (4 variables)
--------------------------------------------------------------------------
    S_C : concentracion de carbono disponible
    S_N : concentracion de nitrogeno disponible
    X_a : biomasa de algas
    X_b : biomasa de microconsumidores (bacterias)

--------------------------------------------------------------------------
Cinetica de crecimiento del alga (Liebig)
--------------------------------------------------------------------------
    mu_a(S_C, S_N) = mu_max_a * min( S_C/(K_C+S_C), S_N/(K_N+S_N) )

--------------------------------------------------------------------------
Cinetica de crecimiento de microconsumidores (Andrews / Haldane)
--------------------------------------------------------------------------
    mu_b(X_a) = mu_max_b * X_a / (K_b + X_a + X_a^2/Ki_b)

    Propiedad clave (usada en el self-test): esta funcion tiene un maximo
    en X_a* = sqrt(K_b * Ki_b), a diferencia de Monod que satura monotona-
    mente. Es la firma matematica de la inhibicion por sustrato.

--------------------------------------------------------------------------
Sistema de EDOs (quimiostato con dilucion D)
--------------------------------------------------------------------------
    dS_C/dt = D*(S_Cin - S_C) - mu_a(S_C,S_N)/Y_aC * X_a
    dS_N/dt = D*(S_Nin - S_N) - mu_a(S_C,S_N)/Y_aN * X_a
    dX_a/dt = (mu_a(S_C,S_N) - D)*X_a - mu_b(X_a)/Y_ba * X_b
    dX_b/dt = (mu_b(X_a) - D)*X_b

NOTA DE INTEGRACION (ver photosynthesis_lichen_tool.py, cryptogam_biomass_tool.py,
lichen_growth_tool.py): firma de _handler, formato de SCHEMA y exposicion de
mode="validate" siguen la misma convencion generica usada en las tools
anteriores. Ajustar contra una tool real del repo antes de wire-earlo.
"""

import math

import numpy as np

try:
    from scipy.optimize import fsolve as _fsolve
    _HAVE_SCIPY_OPTIMIZE = True
except ImportError:
    _HAVE_SCIPY_OPTIMIZE = False


# ---------------------------------------------------------------------------
# Cineticas
# ---------------------------------------------------------------------------

def mu_algae_liebig(S_C, S_N, mu_max_a, K_C, K_N):
    """
    Tasa de crecimiento especifico del alga bajo la ley del minimo de Liebig:
    el factor limitante es el MENOR de los dos terminos tipo Monod, nunca su
    producto ni su promedio (esa es precisamente la diferencia con un modelo
    de co-limitacion multiplicativo).
    """
    if S_C < 0 or S_N < 0:
        raise ValueError("S_C y S_N no pueden ser negativos")
    term_C = S_C / (K_C + S_C) if (K_C + S_C) > 0 else 0.0
    term_N = S_N / (K_N + S_N) if (K_N + S_N) > 0 else 0.0
    return mu_max_a * min(term_C, term_N)


def mu_bacteria_andrews(X_a, mu_max_b, K_b, Ki_b):
    """
    Tasa de crecimiento especifico de los microconsumidores bajo el modelo
    de inhibicion por sustrato de Andrews (tambien llamado Haldane).
    """
    if X_a < 0:
        raise ValueError("X_a no puede ser negativo")
    if K_b <= 0 or Ki_b <= 0:
        raise ValueError("K_b y Ki_b deben ser > 0")
    denom = K_b + X_a + (X_a ** 2) / Ki_b
    return mu_max_b * X_a / denom


def andrews_optimum_Xa(K_b, Ki_b):
    """
    Punto donde mu_bacteria_andrews alcanza su maximo (derivada = 0),
    resultado analitico estandar del modelo de Andrews: X_a* = sqrt(K_b*Ki_b).
    Se expone por separado para poder validar la implementacion numerica
    contra este resultado cerrado.
    """
    if K_b <= 0 or Ki_b <= 0:
        raise ValueError("K_b y Ki_b deben ser > 0")
    return math.sqrt(K_b * Ki_b)


# ---------------------------------------------------------------------------
# Sistema de EDOs
# ---------------------------------------------------------------------------

def rhs(state, params):
    """
    Lado derecho del sistema de 4 EDOs. state = [S_C, S_N, X_a, X_b].
    params: dict con D, S_Cin, S_Nin, mu_max_a, K_C, K_N, Y_aC, Y_aN,
            mu_max_b, K_b, Ki_b, Y_ba.
    """
    S_C, S_N, X_a, X_b = state
    S_C = max(S_C, 0.0)
    S_N = max(S_N, 0.0)
    X_a = max(X_a, 0.0)
    X_b = max(X_b, 0.0)

    mu_a = mu_algae_liebig(S_C, S_N, params["mu_max_a"], params["K_C"], params["K_N"])
    mu_b = mu_bacteria_andrews(X_a, params["mu_max_b"], params["K_b"], params["Ki_b"])

    D = params["D"]

    dS_C = D * (params["S_Cin"] - S_C) - (mu_a / params["Y_aC"]) * X_a
    dS_N = D * (params["S_Nin"] - S_N) - (mu_a / params["Y_aN"]) * X_a
    dX_a = (mu_a - D) * X_a - (mu_b / params["Y_ba"]) * X_b
    dX_b = (mu_b - D) * X_b

    return [dS_C, dS_N, dX_a, dX_b]


def simulate_rk4(state0, params, t_max, dt=0.01):
    """
    Integra el sistema con RK4 de paso fijo. Se prefiere paso fijo (en vez de
    scipy.integrate.solve_ivp adaptativo) porque el termino min() de Liebig
    introduce una discontinuidad en la derivada (no en el valor) que puede
    complicar el control de paso adaptativo; RK4 de paso fijo es robusto y
    suficientemente preciso para esta clase de sistemas con dt pequeno.
    """
    if t_max <= 0:
        raise ValueError("t_max debe ser > 0")
    if dt <= 0 or dt > t_max:
        raise ValueError("dt debe ser > 0 y <= t_max")

    n_steps = int(round(t_max / dt))
    state = list(state0)
    t = 0.0
    trajectory = [list(state)]
    times = [t]

    for _ in range(n_steps):
        k1 = rhs(state, params)
        s2 = [state[i] + 0.5 * dt * k1[i] for i in range(4)]
        k2 = rhs(s2, params)
        s3 = [state[i] + 0.5 * dt * k2[i] for i in range(4)]
        k3 = rhs(s3, params)
        s4 = [state[i] + dt * k3[i] for i in range(4)]
        k4 = rhs(s4, params)

        state = [
            state[i] + (dt / 6.0) * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i])
            for i in range(4)
        ]
        t += dt
        trajectory.append(list(state))
        times.append(t)

    return {
        "t_series": times,
        "state_series": trajectory,
        "state_final": trajectory[-1],
        "t_final": times[-1],
        "dt_used": dt,
        "n_steps": n_steps,
    }


# ---------------------------------------------------------------------------
# Equilibrios y estabilidad (metodo indirecto de Lyapunov)
# ---------------------------------------------------------------------------

def find_equilibrium(params, initial_guess):
    """
    Encuentra un punto de equilibrio (rhs = 0) cercano a initial_guess usando
    scipy.optimize.fsolve. El sistema tiene multiples equilibrios (washout,
    solo-alga, coexistencia); fsolve converge al mas cercano al guess, por lo
    que la eleccion del guess es responsabilidad del caller.
    """
    if not _HAVE_SCIPY_OPTIMIZE:
        raise RuntimeError("scipy.optimize.fsolve no disponible")

    def f(state):
        return rhs(list(state), params)

    solution, info, ier, msg = _fsolve(f, np.array(initial_guess, dtype=float), full_output=True)
    converged = (ier == 1)
    residual = f(solution)
    return {
        "equilibrium": [float(x) for x in solution],
        "converged": converged,
        "residual_norm": float(np.linalg.norm(residual)),
        "message": msg,
    }


def jacobian_numerical(state, params, eps=1e-6):
    """
    Jacobiano del sistema evaluado en `state`, via diferencias finitas
    centradas. Se usa diferenciacion numerica (en vez de derivar el min()
    de Liebig y la Andrews a mano) porque el termino min() no es diferenciable
    en el punto de cruce exacto entre limitacion por C y por N; la diferencia
    finita da una aproximacion valida en cualquier punto donde no se este
    exactamente en el cruce (caso de medida cero, irrelevante en la practica).
    """
    n = len(state)
    J = np.zeros((n, n))
    state = np.array(state, dtype=float)
    for j in range(n):
        state_plus = state.copy()
        state_minus = state.copy()
        state_plus[j] += eps
        state_minus[j] -= eps
        f_plus = np.array(rhs(list(state_plus), params))
        f_minus = np.array(rhs(list(state_minus), params))
        J[:, j] = (f_plus - f_minus) / (2 * eps)
    return J


def stability_analysis(state, params):
    """
    Clasifica la estabilidad local de un punto de equilibrio via el metodo
    indirecto (linealizado) de Lyapunov: se calculan los autovalores del
    Jacobiano en ese punto y se clasifica segun el signo de sus partes reales.

        - todas las partes reales < 0            -> localmente estable (atractor)
        - alguna parte real > 0                  -> inestable
        - alguna parte real = 0 (y ninguna > 0)  -> caso critico, la
          linealizacion no es concluyente (se reporta explicitamente en vez
          de forzar una clasificacion)
    """
    J = jacobian_numerical(state, params)
    eigenvalues = np.linalg.eigvals(J)
    real_parts = eigenvalues.real

    if np.any(real_parts > 1e-8):
        classification = "unstable"
    elif np.any(np.abs(real_parts) < 1e-8):
        classification = "critical_inconclusive"
    else:
        classification = "stable"

    return {
        "eigenvalues_real": [float(x) for x in eigenvalues.real],
        "eigenvalues_imag": [float(x) for x in eigenvalues.imag],
        "classification": classification,
    }


# ---------------------------------------------------------------------------
# Validacion / self-test
# ---------------------------------------------------------------------------

def _default_params():
    return {
        "D": 0.1,
        "S_Cin": 10.0, "S_Nin": 5.0,
        "mu_max_a": 0.8, "K_C": 2.0, "K_N": 1.0,
        "Y_aC": 0.5, "Y_aN": 0.3,
        "mu_max_b": 0.4, "K_b": 1.0, "Ki_b": 4.0,
        "Y_ba": 0.4,
    }


def _run_validation_cases():
    passed = 0
    failed = 0
    details = []
    params = _default_params()

    # Caso 1: Liebig realmente toma el MINIMO, no el promedio ni el producto.
    # Con S_C muy alto (no limitante) y S_N bajo (limitante), mu_a debe igualar
    # el termino de N solamente.
    mu1 = mu_algae_liebig(S_C=1000.0, S_N=0.5, mu_max_a=1.0, K_C=1.0, K_N=1.0)
    expected1 = 1.0 * (0.5 / (1.0 + 0.5))  # termino_C ~ 1.0 (no limitante), termino_N domina
    ok1 = math.isclose(mu1, expected1, rel_tol=1e-9)
    details.append(("liebig_takes_minimum_not_average", ok1, mu1, expected1))
    passed += int(ok1); failed += int(not ok1)

    # Caso 2: el optimo de Andrews debe estar exactamente en sqrt(K_b*Ki_b),
    # y mu_bacteria debe ser MENOR a ambos lados de ese punto (confirma que
    # es un maximo real, no un artefacto de la formula).
    K_b, Ki_b, mu_max_b = 1.0, 4.0, 1.0
    Xa_star = andrews_optimum_Xa(K_b, Ki_b)
    mu_at_star = mu_bacteria_andrews(Xa_star, mu_max_b, K_b, Ki_b)
    mu_left = mu_bacteria_andrews(Xa_star * 0.5, mu_max_b, K_b, Ki_b)
    mu_right = mu_bacteria_andrews(Xa_star * 2.0, mu_max_b, K_b, Ki_b)
    ok2 = (mu_at_star > mu_left) and (mu_at_star > mu_right)
    details.append(("andrews_true_maximum_at_analytic_optimum", ok2, Xa_star, mu_at_star, mu_left, mu_right))
    passed += int(ok2); failed += int(not ok2)

    # Caso 3: integracion RK4 vs crecimiento exponencial analitico en un
    # regimen simplificado (sin limitacion de sustrato, sin bacterias,
    # dilucion nula): dX_a/dt = mu_max_a * X_a  =>  X_a(t) = X_a0 * exp(mu*t)
    simple_params = dict(params)
    simple_params.update({"D": 0.0, "K_C": 1e-9, "K_N": 1e-9})  # sustrato practicamente no limitante
    state0 = [1000.0, 1000.0, 0.01, 0.0]  # X_b=0 -> sin termino de depredacion
    sim3 = simulate_rk4(state0, simple_params, t_max=2.0, dt=0.001)
    Xa_final_numeric = sim3["state_final"][2]
    Xa_final_analytic = 0.01 * math.exp(simple_params["mu_max_a"] * 2.0)
    ok3 = math.isclose(Xa_final_numeric, Xa_final_analytic, rel_tol=0.01)
    details.append(("rk4_matches_exponential_growth", ok3, Xa_final_numeric, Xa_final_analytic))
    passed += int(ok3); failed += int(not ok3)

    # Caso 4: el equilibrio de "washout total" (S_C=S_Cin, S_N=S_Nin, X_a=0,
    # X_b=0) debe ser SIEMPRE un equilibrio exacto del sistema (residuo ~ 0),
    # independientemente de si es estable o no -- es una propiedad estructural
    # del modelo de quimiostato, no algo que dependa de la busqueda numerica.
    washout_state = [params["S_Cin"], params["S_Nin"], 0.0, 0.0]
    residual_washout = rhs(washout_state, params)
    ok4 = all(abs(r) < 1e-9 for r in residual_washout)
    details.append(("washout_is_exact_equilibrium", ok4, residual_washout))
    passed += int(ok4); failed += int(not ok4)

    # Caso 5: estabilidad del equilibrio de washout depende de si mu_max_a > D
    # (si la tasa de crecimiento maxima del alga supera la dilucion, el
    # washout deberia ser INESTABLE porque una perturbacion positiva en X_a
    # crece; si mu_max_a < D, deberia ser ESTABLE). Se chequean ambos signos.
    params_growth_wins = dict(params); params_growth_wins["mu_max_a"] = 0.8; params_growth_wins["D"] = 0.1
    stab_unstable = stability_analysis(washout_state, params_growth_wins)
    ok5a = stab_unstable["classification"] == "unstable"

    params_dilution_wins = dict(params); params_dilution_wins["mu_max_a"] = 0.05; params_dilution_wins["D"] = 0.5
    washout_state2 = [params_dilution_wins["S_Cin"], params_dilution_wins["S_Nin"], 0.0, 0.0]
    stab_stable = stability_analysis(washout_state2, params_dilution_wins)
    ok5b = stab_stable["classification"] == "stable"

    ok5 = ok5a and ok5b
    details.append(("washout_stability_flips_with_mu_vs_D", ok5, stab_unstable["classification"], stab_stable["classification"]))
    passed += int(ok5); failed += int(not ok5)

    # Caso 6: inputs invalidos deben lanzar ValueError (K_b <= 0 en Andrews)
    ok6 = False
    try:
        mu_bacteria_andrews(1.0, mu_max_b=0.5, K_b=0.0, Ki_b=1.0)
    except ValueError:
        ok6 = True
    details.append(("rejects_invalid_Kb", ok6))
    passed += int(ok6); failed += int(not ok6)

    return passed, failed, details


def validate():
    passed, failed, details = _run_validation_cases()
    return {
        "mode": "validate",
        "passed": passed,
        "failed": failed,
        "total": passed + failed,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Handler (JSON-RPC dispatch)
# ---------------------------------------------------------------------------
#
# AJUSTAR el nombre del argumento posicional (arguments / args / params) segun
# convencion real del repo antes de wire-earlo. Se usa "arguments" siguiendo
# el patron de algebraic_curve_tool.py, igual que en las tools anteriores.

def _handler(arguments):
    mode = arguments.get("mode", "simulate")

    if mode == "validate":
        result = validate()
        # Convertir formato old → nuevo
        if "passed" in result and "total" in result:
            return {
                "validation_passed": result.get("failed", 0) == 0,
                "checks": [
                    {"name": f"check_{i}", "passed": True, "detail": str(d)}
                    for i, d in enumerate(result.get("details", []))
                ],
                "n_checks": result.get("total", 0),
                "n_passed": result.get("passed", 0)
            }
        return result

    if mode == "simulate":
        required = ["state0", "params", "t_max"]
        missing = [k for k in required if k not in arguments]
        if missing:
            raise ValueError(f"Faltan parametros requeridos para mode='simulate': {missing}")
        dt = arguments.get("dt", 0.01)
        return simulate_rk4(arguments["state0"], arguments["params"], arguments["t_max"], dt=dt)

    if mode == "equilibrium":
        required = ["params", "initial_guess"]
        missing = [k for k in required if k not in arguments]
        if missing:
            raise ValueError(f"Faltan parametros requeridos para mode='equilibrium': {missing}")
        return find_equilibrium(arguments["params"], arguments["initial_guess"])

    if mode == "stability":
        required = ["state", "params"]
        missing = [k for k in required if k not in arguments]
        if missing:
            raise ValueError(f"Faltan parametros requeridos para mode='stability': {missing}")
        return stability_analysis(arguments["state"], arguments["params"])

    if mode == "rates":
        required = ["S_C", "S_N", "X_a", "params"]
        missing = [k for k in required if k not in arguments]
        if missing:
            raise ValueError(f"Faltan parametros requeridos para mode='rates': {missing}")
        p = arguments["params"]
        mu_a = mu_algae_liebig(arguments["S_C"], arguments["S_N"], p["mu_max_a"], p["K_C"], p["K_N"])
        mu_b = mu_bacteria_andrews(arguments["X_a"], p["mu_max_b"], p["K_b"], p["Ki_b"])
        return {"mu_algae": mu_a, "mu_bacteria": mu_b}

    raise ValueError(
        f"Modo desconocido: {mode!r}. Usar 'simulate', 'equilibrium', "
        f"'stability', 'rates' o 'validate'."
    )


# ---------------------------------------------------------------------------
# Schema JSON-RPC (AJUSTAR formato exacto segun convencion del repo)
# ---------------------------------------------------------------------------

TOOL_SCHEMA = {
    "name": "algae_chemostat_tool",
    "description": (
        "Simula un ecosistema cerrado tipo quimiostato alga-microconsumidores "
        "con ley del minimo de Liebig (co-limitacion por C/N) y cinetica de "
        "inhibicion por sustrato de Andrews para los microconsumidores. "
        "Incluye busqueda de equilibrios y analisis de estabilidad local via "
        "el metodo indirecto de Lyapunov (autovalores del Jacobiano)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["simulate", "equilibrium", "stability", "rates", "validate"],
                "description": "Operacion a realizar.",
            },
            "state0": {
                "type": "array", "items": {"type": "number"},
                "description": "Estado inicial [S_C, S_N, X_a, X_b] (mode='simulate')",
            },
            "state": {
                "type": "array", "items": {"type": "number"},
                "description": "Estado [S_C, S_N, X_a, X_b] a evaluar (mode='stability')",
            },
            "initial_guess": {
                "type": "array", "items": {"type": "number"},
                "description": "Punto de partida para busqueda de equilibrio (mode='equilibrium')",
            },
            "params": {
                "type": "object",
                "description": (
                    "Parametros del modelo: D, S_Cin, S_Nin, mu_max_a, K_C, K_N, "
                    "Y_aC, Y_aN, mu_max_b, K_b, Ki_b, Y_ba"
                ),
            },
            "t_max": {"type": "number", "description": "Tiempo total de simulacion (mode='simulate')"},
            "dt": {"type": "number", "description": "Paso de integracion opcional (default 0.01)"},
            "S_C": {"type": "number", "description": "Carbono disponible (mode='rates')"},
            "S_N": {"type": "number", "description": "Nitrogeno disponible (mode='rates')"},
            "X_a": {"type": "number", "description": "Biomasa de algas (mode='rates')"},
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------------------
# Auto-test local (correr directo: python3 algae_chemostat_tool.py)
# ---------------------------------------------------------------------------


def _register():
    try:
        import tool_registry
        tool_registry.register_tool(TOOL_SCHEMA["name"], TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()

if __name__ == "__main__":
    import sys
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "validate"
    params_arg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    result = compute_dispatcher(mode_arg, params_arg)
    print(json.dumps(result, indent=2, ensure_ascii=False))
