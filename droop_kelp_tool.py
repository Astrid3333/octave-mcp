"""
droop_kelp_tool
================

Modelo de Droop (cuota interna de nutriente) con limitacion adicional por
luz (funcion de Steele), aplicado a crecimiento de macroalgas (kelp).
Generaliza bacterial_growth_tool (que asume cinetica tipo Monod directa
sobre el nutriente externo) incorporando la cuota interna de nitrogeno,
que es el mecanismo dominante reportado en literatura para macroalgas
(Droop 1968; Ross & Geider aplicado a Laminaria/Macrocystis).

Variables de estado:
  Q : cuota interna de nutriente (nitrogeno) por unidad de biomasa
      [mg N / g biomasa seca]
  B : biomasa [g biomasa seca / m^2]
  S : concentracion de nutriente externo (disuelto) [mg N / L]

Ecuaciones:
  rho(S)      = rho_max * S / (Ks + S)              (captacion, Michaelis-Menten)
  mu(Q)       = mu_max * (1 - Qmin/Q)                (crecimiento limitado por cuota, Droop)
  L(I)        = (I / I_opt) * exp(1 - I / I_opt)     (limitacion por luz, Steele 1962)
  mu_eff(Q,I) = mu(Q) * L(I)

  dQ/dt = rho(S) - mu_eff(Q,I) * Q
  dB/dt = mu_eff(Q,I) * B - loss_rate * B
  dS/dt = -rho(S) * B / yield_coeff        (opcional, sistema cerrado)

Convencion de dispatch: el tool_registry invoca al handler pasando el
diccionario completo de argumentos como UN SOLO parametro posicional
(no expandido como **kwargs). Firma correcta: _handler(args).
"""

import math

import tool_registry


# ----------------------------------------------------------------------
# Parametros por defecto (ordenes de magnitud tipicos para Laminariales,
# ver Ross & Geider 2003; Broch & Slagstad 2012)
# ----------------------------------------------------------------------

DEFAULTS = {
    "mu_max": 0.20,       # tasa de crecimiento maxima [1/dia]
    "Qmin": 10.0,         # cuota interna minima [mg N / g DW]
    "Qmax": 40.0,         # cuota interna maxima (capacidad de almacenamiento)
    "rho_max": 5.0,       # captacion maxima de N [mg N / g DW / dia]
    "Ks": 3.0,            # cte de semisaturacion para captacion [mg N / L]
    "I_opt": 150.0,       # irradiancia optima [umol foton / m^2 / s]
    "loss_rate": 0.02,    # tasa de perdida/erosion de biomasa [1/dia]
    "yield_coeff": 1.0,   # g biomasa producida por mg N captado (conversion)
}


def uptake_rate(S, rho_max, Ks):
    """Captacion tipo Michaelis-Menten sobre nutriente externo S."""
    if S <= 0:
        return 0.0
    return rho_max * S / (Ks + S)


def growth_rate_droop(Q, Qmin, mu_max):
    """mu(Q) = mu_max * (1 - Qmin/Q), truncado en 0 (sin crecimiento
    negativo por debajo de la cuota minima)."""
    if Q <= 0:
        return 0.0
    val = mu_max * (1.0 - Qmin / Q)
    return max(val, 0.0)


def light_limitation_steele(I, I_opt):
    """Funcion de Steele (1962): fotoinhibicion suave, pico=1 en I=I_opt."""
    if I_opt <= 0:
        return 0.0
    x = I / I_opt
    return x * math.exp(1.0 - x)


def _derivatives(state, S_forcing, I_forcing, p):
    Q, B, S = state
    rho = uptake_rate(S, p["rho_max"], p["Ks"])
    mu = growth_rate_droop(Q, p["Qmin"], p["mu_max"])
    light = light_limitation_steele(I_forcing, p["I_opt"])
    mu_eff = mu * light

    dQ = rho - mu_eff * Q
    dB = mu_eff * B - p["loss_rate"] * B
    dS = -(rho * B) / p["yield_coeff"] if p.get("closed_system", True) else 0.0

    return (dQ, dB, dS)


def _rk4_step(state, dt, I_forcing, p):
    k1 = _derivatives(state, None, I_forcing, p)
    s2 = tuple(state[i] + dt / 2 * k1[i] for i in range(3))
    k2 = _derivatives(s2, None, I_forcing, p)
    s3 = tuple(state[i] + dt / 2 * k2[i] for i in range(3))
    k3 = _derivatives(s3, None, I_forcing, p)
    s4 = tuple(state[i] + dt * k3[i] for i in range(3))
    k4 = _derivatives(s4, None, I_forcing, p)

    new_state = tuple(
        state[i] + (dt / 6.0) * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i])
        for i in range(3)
    )
    # Cuota y biomasa no pueden ser negativas
    Q, B, S = new_state
    Q = max(Q, p["Qmin"] * 0.5)
    B = max(B, 0.0)
    S = max(S, 0.0)
    return (Q, B, S)


def simulate(days=30, dt=0.1, Q0=None, B0=1.0, S0=5.0, I=150.0, params=None):
    p = dict(DEFAULTS)
    if params:
        p.update(params)
    if Q0 is None:
        Q0 = p["Qmax"]

    n_steps = int(days / dt)
    state = (Q0, B0, S0)
    trajectory = [{"t": 0.0, "Q": state[0], "B": state[1], "S": state[2]}]
    t = 0.0
    for _ in range(n_steps):
        state = _rk4_step(state, dt, I, p)
        t += dt
        trajectory.append({"t": round(t, 6), "Q": state[0], "B": state[1], "S": state[2]})
    return trajectory


# ----------------------------------------------------------------------
# Validacion
# ----------------------------------------------------------------------

def _validate(params=None):
    p = dict(DEFAULTS)
    if params:
        p.update(params)
    checks = []

    # Check 1: en Q = Qmin, el crecimiento debe ser exactamente cero
    # (definicion de la cuota minima en el modelo de Droop).
    mu_at_qmin = growth_rate_droop(p["Qmin"], p["Qmin"], p["mu_max"])
    ok1 = abs(mu_at_qmin) < 1e-12
    checks.append({
        "name": "zero_growth_at_Qmin",
        "passed": bool(ok1),
        "detail": f"mu(Qmin)={mu_at_qmin:.3e} 1/dia (esperado 0)",
    })

    # Check 2: en Q = Qmax, mu(Qmax) debe coincidir con la formula cerrada
    # mu_max*(1 - Qmin/Qmax).
    mu_at_qmax = growth_rate_droop(p["Qmax"], p["Qmin"], p["mu_max"])
    expected = p["mu_max"] * (1.0 - p["Qmin"] / p["Qmax"])
    ok2 = abs(mu_at_qmax - expected) < 1e-9
    checks.append({
        "name": "closed_form_growth_at_Qmax",
        "passed": bool(ok2),
        "detail": f"mu(Qmax)={mu_at_qmax:.6f}, formula cerrada={expected:.6f} 1/dia",
    })

    # Check 3: la funcion de Steele debe alcanzar su maximo (=1.0) exactamente
    # en I = I_opt, y valer menos que 1 a ambos lados (fotoinhibicion +
    # limitacion por baja luz).
    l_at_opt = light_limitation_steele(p["I_opt"], p["I_opt"])
    l_below = light_limitation_steele(p["I_opt"] * 0.5, p["I_opt"])
    l_above = light_limitation_steele(p["I_opt"] * 2.0, p["I_opt"])
    ok3 = (
        abs(l_at_opt - 1.0) < 1e-9
        and l_below < l_at_opt
        and l_above < l_at_opt
    )
    checks.append({
        "name": "steele_light_peak_at_Iopt",
        "passed": bool(ok3),
        "detail": (
            f"L(I_opt)={l_at_opt:.6f}, L(0.5*I_opt)={l_below:.6f}, "
            f"L(2*I_opt)={l_above:.6f}"
        ),
    })

    # Check 4: conservacion de masa en sistema cerrado sin perdidas
    # (loss_rate=0): N total = S + B*Q debe mantenerse aprox constante
    # a lo largo de la simulacion (yield_coeff=1).
    p_closed = dict(p)
    p_closed["loss_rate"] = 0.0
    p_closed["yield_coeff"] = 1.0
    p_closed["closed_system"] = True
    traj = simulate(days=10, dt=0.05, Q0=p["Qmin"] * 1.5, B0=1.0, S0=20.0,
                     I=p["I_opt"], params=p_closed)
    n_total_start = traj[0]["S"] + traj[0]["B"] * traj[0]["Q"]
    n_total_end = traj[-1]["S"] + traj[-1]["B"] * traj[-1]["Q"]
    rel_err = abs(n_total_end - n_total_start) / max(abs(n_total_start), 1e-9)
    ok4 = rel_err < 1e-2  # 1% tolerancia por integracion numerica RK4
    checks.append({
        "name": "mass_balance_closed_system",
        "passed": bool(ok4),
        "detail": (
            f"N_total inicial={n_total_start:.4f}, N_total final={n_total_end:.4f}, "
            f"error relativo={rel_err:.4%}"
        ),
    })

    passed_count = sum(1 for c in checks if c["passed"])
    return {
        "all_passed": passed_count == len(checks),
        "passed": passed_count,
        "total": len(checks),
        "checks": checks,
    }


# ----------------------------------------------------------------------
# Dispatch
# ----------------------------------------------------------------------

def validate(model_params=None):
    return _validate(params=model_params)


def compute_droop_kelp(mode="validate", **kwargs):
    if mode == "validate":
        return validate(model_params=kwargs.get("model_params"))
    elif mode == "simulate":
        return {
            "trajectory": simulate(
                days=kwargs.get("days", 30),
                dt=kwargs.get("dt", 0.1),
                Q0=kwargs.get("Q0"),
                B0=kwargs.get("B0", 1.0),
                S0=kwargs.get("S0", 5.0),
                I=kwargs.get("I", 150.0),
                params=kwargs.get("model_params"),
            )
        }
    elif mode == "growth_rate":
        p = dict(DEFAULTS)
        if kwargs.get("model_params"):
            p.update(kwargs["model_params"])
        Q = kwargs.get("Q", p["Qmax"])
        I = kwargs.get("I", p["I_opt"])
        mu = growth_rate_droop(Q, p["Qmin"], p["mu_max"])
        light = light_limitation_steele(I, p["I_opt"])
        return {"Q": Q, "I": I, "mu": mu, "light_limitation": light, "mu_eff": mu * light}
    else:
        raise ValueError(f"mode desconocido: {mode}")


DROOP_KELP_TOOL_SCHEMA = {
    "name": "droop_kelp_tool",
    "description": (
        "Modelo de Droop (cuota interna de nutriente N) con limitacion "
        "adicional por luz (funcion de Steele) para crecimiento de "
        "macroalgas/kelp. Generaliza bacterial_growth_tool incorporando la "
        "cuota interna, mecanismo dominante en macroalgas (Droop 1968). "
        "Modos: validate (crecimiento nulo en Qmin, formula cerrada en Qmax, "
        "pico de Steele en I_opt, balance de masa en sistema cerrado), "
        "simulate (integracion RK4 de Q/B/S en el tiempo), growth_rate "
        "(tasa instantanea mu_eff para una cuota Q e irradiancia I dadas)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["validate", "simulate", "growth_rate"]},
            "days": {"type": "number", "description": "duracion de la simulacion en dias (simulate)"},
            "dt": {"type": "number", "description": "paso de integracion RK4 en dias (simulate)"},
            "Q0": {"type": "number", "description": "cuota interna inicial, mg N / g DW (simulate; default Qmax)"},
            "B0": {"type": "number", "description": "biomasa inicial, g DW/m^2 (simulate)"},
            "S0": {"type": "number", "description": "nutriente externo inicial, mg N/L (simulate)"},
            "I": {"type": "number", "description": "irradiancia, umol foton/m^2/s (simulate, growth_rate)"},
            "Q": {"type": "number", "description": "cuota interna, mg N / g DW (growth_rate)"},
            "model_params": {
                "type": "object",
                "description": "override de parametros del modelo (mu_max, Qmin, Qmax, rho_max, Ks, I_opt, loss_rate, yield_coeff)",
            },
        },
        "required": ["mode"],
    },
}


def _handler(args):
    args = dict(args or {})
    mode = args.pop("mode", "validate")
    params = args.pop("params", None) or {}
    merged = {**params, **args}
    return compute_droop_kelp(mode=mode, **merged)


tool_registry.register_tool("droop_kelp_tool", DROOP_KELP_TOOL_SCHEMA, _handler)


if __name__ == "__main__":
    import json
    print(json.dumps(validate(), indent=2, ensure_ascii=False))
