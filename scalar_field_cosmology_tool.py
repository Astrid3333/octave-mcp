"""
scalar_field_cosmology_tool.py

Herramienta para octave-mcp: dinamica de un campo escalar de quintaesencia
phi(t) en un universo FLRW plano, con la ecuacion de Klein-Gordon acoplada
a Friedmann.

ENFOQUE (explicito y honesto):
Unidades naturales con kappa = 8*pi*G = 1. Ecuaciones resueltas:

    Klein-Gordon:  phi_ddot + 3*H*phi_dot + dV/dphi = 0
    Friedmann:     H^2 = (1/3) * [ phi_dot^2/2 + V(phi) + rho_r + rho_m ]

donde rho_r = rho_r0*(a0/a)^4 y rho_m = rho_m0*(a0/a)^3 son fluidos de
fondo opcionales (radiacion / materia) que NO estan acoplados al campo
(sin transferencia de energia -- eso es responsabilidad de otra tool,
p.ej. un futuro modelo de sector oscuro unificado con Gamma(z)).

Se integra en el tiempo fisico t con variables [phi, phi_dot, ln_a],
usando LSODA (adaptativo, apto para la rigidez que aparece cuando el
campo oscila rapido comparado con H).

Potenciales soportados:
  - "quadratic":    V(phi) = 0.5 * m^2 * phi^2        (dV/dphi = m^2*phi)
  - "exponential":  V(phi) = V0 * exp(-lambda*phi)     (dV/dphi = -lambda*V)

De cada potencial se extrae w_phi(t) = (phi_dot^2/2 - V)/(phi_dot^2/2 + V)
y Omega_phi(t) = rho_phi / (3*H^2).

mode: "self_test"
  Dos regression tests contra resultados analiticos conocidos de la
  literatura de quintaesencia (no inventados aqui):
  1. Atractor de potencial exponencial dominado por el campo: para V0*exp
     (-lambda*phi) sin fluidos de fondo, la solucion de escalamiento exacta
     es a(t) ~ t^p con p = 2/lambda^2, y w_phi -> lambda^2/3 - 1 en el
     atractor, independiente de las condiciones iniciales (Copeland,
     Liddle & Wands 1998). Se verifica que la integracion numerica, desde
     condiciones iniciales genericas, converge a ese w y ese exponente p.
  2. Oscilacion rapida de potencial cuadratico (m >> H): el promedio
     temporal sobre un periodo de w_phi -> 0 (comportamiento tipo materia,
     Turner 1983), y rho_phi decae como a^-3. Se verifica ambos frente a
     los valores analiticos.
  Ademas ambos tests chequean la ecuacion de continuidad
  drho_phi/dt = -3*H*(rho_phi + p_phi) como validacion interna independiente
  del integrador.

mode: "evolve"
  Corrida general: dado un potencial y condiciones iniciales (mas fluidos
  de fondo opcionales), devuelve las series temporales de a, H, phi,
  phi_dot, w_phi, Omega_phi, rho_phi.

NOTA DE ALCANCE: FLRW plano, homogeneo e isotropo, sin perturbaciones.
No incluye acoplamiento campo-fluido ni k != 0.
"""

import numpy as np
from scipy.integrate import solve_ivp
from tool_registry import register_tool


# ---------------------------------------------------------------------------
# Potenciales
# ---------------------------------------------------------------------------

def _V(phi, kind, params):
    if kind == "quadratic":
        m = params["m"]
        return 0.5 * m ** 2 * phi ** 2
    if kind == "exponential":
        V0, lam = params["V0"], params["lam"]
        return V0 * np.exp(-lam * phi)
    raise ValueError(f"potencial desconocido: {kind}")


def _dV_dphi(phi, kind, params):
    if kind == "quadratic":
        m = params["m"]
        return m ** 2 * phi
    if kind == "exponential":
        V0, lam = params["V0"], params["lam"]
        return -lam * V0 * np.exp(-lam * phi)
    raise ValueError(f"potencial desconocido: {kind}")


# ---------------------------------------------------------------------------
# Sistema dinamico: y = [phi, phi_dot, ln_a]
# ---------------------------------------------------------------------------

def _rho_background(ln_a, ln_a0, rho_r0, rho_m0):
    a_ratio = np.exp(ln_a0 - ln_a)  # a0/a
    return rho_r0 * a_ratio ** 4 + rho_m0 * a_ratio ** 3


def _H(phi, phi_dot, ln_a, kind, params, ln_a0, rho_r0, rho_m0):
    V = _V(phi, kind, params)
    rho_phi = 0.5 * phi_dot ** 2 + V
    rho_bg = _rho_background(ln_a, ln_a0, rho_r0, rho_m0)
    H2 = (rho_phi + rho_bg) / 3.0
    return np.sqrt(max(H2, 0.0)), rho_phi, rho_bg


def _rhs(t, y, kind, params, ln_a0, rho_r0, rho_m0):
    phi, phi_dot, ln_a = y
    H, rho_phi, rho_bg = _H(phi, phi_dot, ln_a, kind, params, ln_a0, rho_r0, rho_m0)
    dphi = phi_dot
    dphi_dot = -3.0 * H * phi_dot - _dV_dphi(phi, kind, params)
    dln_a = H
    return [dphi, dphi_dot, dln_a]


def _integrate(kind, params, phi0, phidot0, t_max, n_t, rho_r0=0.0, rho_m0=0.0, ln_a0=0.0):
    y0 = [phi0, phidot0, ln_a0]
    t_eval = np.linspace(0.0, t_max, n_t)
    sol = solve_ivp(
        _rhs, [0.0, t_max], y0, t_eval=t_eval, args=(kind, params, ln_a0, rho_r0, rho_m0),
        method="LSODA", rtol=1e-9, atol=1e-12, max_step=t_max / 200.0,
    )
    if not sol.success:
        raise RuntimeError(f"Integracion fallo: {sol.message}")

    phi, phi_dot, ln_a = sol.y
    a = np.exp(ln_a)
    H = np.zeros_like(a)
    rho_phi = np.zeros_like(a)
    rho_bg = np.zeros_like(a)
    for i in range(len(a)):
        H[i], rho_phi[i], rho_bg[i] = _H(phi[i], phi_dot[i], ln_a[i], kind, params, ln_a0, rho_r0, rho_m0)

    V = _V(phi, kind, params)
    p_phi = 0.5 * phi_dot ** 2 - V
    with np.errstate(divide="ignore", invalid="ignore"):
        w_phi = np.where(rho_phi > 1e-300, p_phi / rho_phi, np.nan)
    Omega_phi = rho_phi / (3.0 * H ** 2)

    return {
        "t": t_eval, "a": a, "H": H, "phi": phi, "phi_dot": phi_dot,
        "rho_phi": rho_phi, "p_phi": p_phi, "w_phi": w_phi, "Omega_phi": Omega_phi,
        "rho_bg": rho_bg,
    }


def _continuity_residual(series):
    """Chequeo independiente: drho_phi/dt debe igualar -3H(rho_phi+p_phi)."""
    t, rho_phi, H, p_phi = series["t"], series["rho_phi"], series["H"], series["p_phi"]
    drho_dt_numeric = np.gradient(rho_phi, t)
    drho_dt_analytic = -3.0 * H * (rho_phi + p_phi)
    denom = np.maximum(np.abs(drho_dt_analytic), 1e-12)
    rel_err = np.abs(drho_dt_numeric - drho_dt_analytic) / denom
    # ignorar extremos (diferencias finitas menos precisas en los bordes)
    interior = rel_err[2:-2]
    return float(np.median(interior))


# ---------------------------------------------------------------------------
# self_test
# ---------------------------------------------------------------------------

def _self_test():
    results = {}

    # --- Test 1: atractor exponencial (campo dominante) -----------------
    lam = 1.0
    p_analytic = 2.0 / lam ** 2
    w_analytic = lam ** 2 / 3.0 - 1.0

    params = {"V0": 1.0, "lam": lam}
    # condiciones iniciales genericas, lejos del atractor
    series = _integrate("exponential", params, phi0=-2.0, phidot0=3.0, t_max=200.0, n_t=4000)

    tail = slice(int(0.85 * len(series["t"])), None)
    t_tail = series["t"][tail]
    a_tail = series["a"][tail]
    w_tail = series["w_phi"][tail]

    # ajustar a(t) ~ t^p en la cola: log a = p*log t + const
    log_fit = np.polyfit(np.log(t_tail), np.log(a_tail), 1)
    p_numeric = float(log_fit[0])
    w_numeric = float(np.mean(w_tail))

    rel_err_p = abs(p_numeric - p_analytic) / p_analytic
    err_w = abs(w_numeric - w_analytic)
    continuity_res = _continuity_residual(series)

    results["exponential_attractor"] = {
        "lambda": lam,
        "p_analytic": p_analytic, "p_numeric": p_numeric, "rel_error_p": rel_err_p,
        "w_analytic": w_analytic, "w_numeric": w_numeric, "abs_error_w": err_w,
        "continuity_residual_median": continuity_res,
        "pass": bool(rel_err_p < 0.05 and err_w < 0.05 and continuity_res < 1e-3),
    }

    # --- Test 2: oscilacion rapida cuadratica (m >> H) -------------------
    m = 50.0
    params2 = {"m": m}
    phi0, phidot0 = 0.1, 0.0
    H0 = np.sqrt((0.5 * m ** 2 * phi0 ** 2) / 3.0)
    T_osc = 2.0 * np.pi / m
    t_max2 = 60.0 * T_osc  # muchas oscilaciones, pocos e-folds
    series2 = _integrate("quadratic", params2, phi0=phi0, phidot0=phidot0, t_max=t_max2, n_t=6000)

    tail2 = slice(int(0.6 * len(series2["t"])), None)
    w_avg = float(np.mean(series2["w_phi"][tail2]))

    # exponente de decaimiento de rho_phi vs a (esperado -3)
    a_tail2 = series2["a"][tail2]
    rho_tail2 = series2["rho_phi"][tail2]
    decay_fit = np.polyfit(np.log(a_tail2), np.log(rho_tail2), 1)
    n_decay = float(decay_fit[0])

    continuity_res2 = _continuity_residual(series2)

    results["quadratic_oscillation_average"] = {
        "m": m, "H0": float(H0), "m_over_H0": float(m / H0),
        "w_avg_numeric": w_avg, "w_avg_analytic": 0.0,
        "rho_decay_exponent_numeric": n_decay, "rho_decay_exponent_analytic": -3.0,
        "continuity_residual_median": continuity_res2,
        "pass": bool(abs(w_avg) < 0.15 and abs(n_decay + 3.0) < 0.3 and continuity_res2 < 1e-2),
    }

    all_pass = results["exponential_attractor"]["pass"] and results["quadratic_oscillation_average"]["pass"]
    return {"mode": "self_test", "all_pass": bool(all_pass), "tests": results}


# ---------------------------------------------------------------------------
# evolve
# ---------------------------------------------------------------------------

def _evolve(params_in):
    kind = params_in.get("potential", "exponential")
    if kind not in ("quadratic", "exponential"):
        raise ValueError("potential debe ser 'quadratic' o 'exponential'")

    if kind == "quadratic":
        params = {"m": float(params_in.get("m", 1.0))}
    else:
        params = {"V0": float(params_in.get("V0", 1.0)), "lam": float(params_in.get("lam", 1.0))}

    phi0 = float(params_in.get("phi0", 1.0))
    phidot0 = float(params_in.get("phidot0", 0.0))
    rho_r0 = float(params_in.get("rho_r0", 0.0))
    rho_m0 = float(params_in.get("rho_m0", 0.0))
    t_max = float(params_in.get("t_max", 20.0))
    n_t = int(params_in.get("n_t", 1000))

    series = _integrate(kind, params, phi0, phidot0, t_max, n_t, rho_r0=rho_r0, rho_m0=rho_m0)
    continuity_res = _continuity_residual(series)

    return {
        "mode": "evolve",
        "potential": kind,
        "params_used": {
            **params, "phi0": phi0, "phidot0": phidot0,
            "rho_r0": rho_r0, "rho_m0": rho_m0, "t_max": t_max, "n_t": n_t,
        },
        "diagnostics": {
            "w_phi_final": float(series["w_phi"][-1]),
            "Omega_phi_final": float(series["Omega_phi"][-1]),
            "e_folds_total": float(np.log(series["a"][-1] / series["a"][0])),
            "continuity_residual_median": continuity_res,
        },
        "series": {
            "t": series["t"].tolist(),
            "a": series["a"].tolist(),
            "H": series["H"].tolist(),
            "phi": series["phi"].tolist(),
            "phi_dot": series["phi_dot"].tolist(),
            "w_phi": [None if np.isnan(x) else float(x) for x in series["w_phi"]],
            "Omega_phi": series["Omega_phi"].tolist(),
            "rho_phi": series["rho_phi"].tolist(),
        },
        "note": (
            "FLRW plano, kappa=8*pi*G=1. Fluidos de fondo (rho_r0, rho_m0) no "
            "acoplados al campo -- sin transferencia de energia."
        ),
    }


# ---------------------------------------------------------------------------
# Entry point (firma compatible con octave-mcp)
# ---------------------------------------------------------------------------

def compute_scalar_field_cosmology_tool(mode, params=None):
    params = params or {}
    if mode == "self_test":
        return _self_test()
    elif mode == "evolve":
        return _evolve(params)
    else:
        return {"error": f"Modo desconocido: {mode}. Modos validos: self_test, evolve."}


SCALAR_FIELD_COSMOLOGY_TOOL_SCHEMA = {
    "name": "scalar_field_cosmology_tool",
    "description": (
        "Simulador de campo escalar de quintaesencia phi(t) en FLRW plano "
        "(kappa=8*pi*G=1): Klein-Gordon phi_ddot+3H*phi_dot+dV/dphi=0 acoplada "
        "a Friedmann H^2=(1/3)(phi_dot^2/2+V(phi)+rho_r+rho_m). Potenciales: "
        "quadratic (V=m^2*phi^2/2) y exponential (V=V0*exp(-lambda*phi)). "
        "mode=self_test: regression contra 2 resultados analiticos conocidos "
        "de la literatura de quintaesencia -- atractor de escalamiento del "
        "potencial exponencial (p=2/lambda^2, w->lambda^2/3-1) y promedio "
        "tipo-materia de la oscilacion rapida del potencial cuadratico (w->0, "
        "rho~a^-3) -- mas chequeo de la ecuacion de continuidad. "
        "mode=evolve: corrida general, devuelve series de a(t), H(t), phi(t), "
        "w_phi(t), Omega_phi(t), rho_phi(t) para un potencial y condiciones "
        "iniciales dadas, con fluidos de fondo (radiacion/materia) opcionales "
        "no acoplados al campo."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["self_test", "evolve"]},
            "params": {
                "type": "object",
                "properties": {
                    "potential": {"type": "string", "enum": ["quadratic", "exponential"], "description": "Tipo de potencial (default 'exponential')"},
                    "m": {"type": "number", "description": "Masa del campo, solo potencial quadratic (default 1.0)"},
                    "V0": {"type": "number", "description": "Escala del potencial, solo exponential (default 1.0)"},
                    "lam": {"type": "number", "description": "Pendiente lambda, solo exponential (default 1.0)"},
                    "phi0": {"type": "number", "description": "Valor inicial del campo (default 1.0)"},
                    "phidot0": {"type": "number", "description": "Velocidad inicial del campo (default 0.0)"},
                    "rho_r0": {"type": "number", "description": "Densidad de radiacion de fondo en a=1, no acoplada (default 0.0)"},
                    "rho_m0": {"type": "number", "description": "Densidad de materia de fondo en a=1, no acoplada (default 0.0)"},
                    "t_max": {"type": "number", "description": "Tiempo total de integracion (default 20.0)"},
                    "n_t": {"type": "integer", "description": "Numero de puntos de salida (default 1000)"},
                },
            },
        },
        "required": ["mode"],
    },
}


register_tool(
    name="scalar_field_cosmology_tool",
    schema=SCALAR_FIELD_COSMOLOGY_TOOL_SCHEMA,
    handler=lambda args: compute_scalar_field_cosmology_tool(
        args.get("mode"), args.get("params")
    ),
)


if __name__ == "__main__":
    import json
    print(json.dumps(compute_scalar_field_cosmology_tool("self_test"), indent=2))
