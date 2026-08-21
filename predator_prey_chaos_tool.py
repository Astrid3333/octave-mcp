"""
predator_prey_chaos_tool.py

Modelos depredador-presa con geometria de atractor. Punto 4 de la
extension de octave-mcp hacia sistemas caoticos aplicados (junto a
attractor_trajectory_tool y correlation_dimension_tool).

Dos modelos, con roles distintos:

- Hastings-Powell (1991): cadena trofica de 3 especies (recurso->
  consumidor->depredador) con dos respuestas funcionales tipo Holling II.
  Es EL modelo depredador-presa caotico clasico de la literatura (produce
  el llamado "atractor teacup"). Referencia: Hastings, A. & Powell, T.
  (1991), "Chaos in a Three-Species Food Chain", Ecology 72(3).

- Rosenzweig-MacArthur: el modelo base de 2 especies (presa con
  crecimiento logistico + Holling II) mencionado como punto de partida.
  Se incluye como referencia/contraste, NO como generador de caos: por
  Poincare-Bendixson, un sistema continuo de 2 especies (2D, autonomo) no
  puede tener trayectorias caoticas -- a lo sumo un ciclo limite. El
  validate explota justamente este contraste (HP: lambda1>0, RM: lambda1<=0).

NOTA: la busqueda que trajo Astrid mencionaba un "modelo con atractor en
forma de caracola" -- no se implementa aca por no tener una formulacion de
ecuaciones verificable en una referencia citable. Si aparece la cita
concreta (autor/paper/ecuaciones), se puede agregar como tercer modo.

Integracion: RK4 puro Python (mismo patron que _lorenz_series en
chaos_diagnosis_tool), sin Octave -- estos sistemas no son stiff y no
justifican el overhead de subprocess.

Diagnostico de caos en el validate: se reusa compute_chaos_diagnosis de
chaos_diagnosis_tool sobre la serie x(t) generada, en vez de reimplementar
Rosenstein aca -- mismo criterio de deteccion de caos en toda la suite.
"""

from chaos_diagnosis_tool import compute_chaos_diagnosis

PREDATOR_PREY_CHAOS_SCHEMA = {
    "name": "compute_predator_prey_chaos",
    "description": (
        "Modelos depredador-presa con geometria de atractor: hastings_powell "
        "(cadena trofica de 3 especies, caotico con parametros clasicos -- "
        "'atractor teacup') y rosenzweig_macarthur (2 especies, referencia NO "
        "caotica por Poincare-Bendixson -- a lo sumo ciclo limite). "
        "Complementa a attractor_trajectory_tool (atractores fisicos clasicos) "
        "con el caso ecologico."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["hastings_powell", "rosenzweig_macarthur", "validate"],
                "default": "hastings_powell",
            },
            "params": {
                "type": "object",
                "description": (
                    "Hastings-Powell: a1,b1,a2,b2,d1,d2 (default: valores clasicos "
                    "que producen el atractor caotico, Hastings & Powell 1991). "
                    "Rosenzweig-MacArthur: r,K,a,h,e,m (default: valores que dan "
                    "un ciclo limite estable, no caotico)."
                ),
            },
            "initial_condition": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Estado inicial. Default: HP=[0.5,0.5,10.0], RM=[0.5,0.5].",
            },
            "dt": {"type": "number", "default": 0.01},
            "n_steps": {"type": "integer", "default": 6000},
            "discard": {"type": "integer", "default": 2000, "description": "Pasos iniciales descartados (transiente)."},
            "downsample_for_plot": {"type": "integer", "default": 500},
        },
    },
}

_HP_DEFAULTS = {"a1": 5.0, "b1": 3.0, "a2": 0.1, "b2": 2.0, "d1": 0.4, "d2": 0.01}
_RM_DEFAULTS = {"r": 1.0, "K": 1.0, "a": 5.0, "h": 0.1, "e": 0.5, "m": 0.4}


def _rk4_step(f, y, dt):
    k1 = f(y)
    y2 = [y[j] + dt / 2 * k1[j] for j in range(len(y))]
    k2 = f(y2)
    y3 = [y[j] + dt / 2 * k2[j] for j in range(len(y))]
    k3 = f(y3)
    y4 = [y[j] + dt * k3[j] for j in range(len(y))]
    k4 = f(y4)
    return [y[j] + dt / 6 * (k1[j] + 2 * k2[j] + 2 * k3[j] + k4[j]) for j in range(len(y))]


def _integrate(f, y0, dt, n_steps, discard):
    y = list(y0)
    traj = []
    for i in range(n_steps + discard):
        y = _rk4_step(f, y, dt)
        if i >= discard:
            traj.append(list(y))
    return traj


def _hastings_powell_rhs(p):
    a1, b1, a2, b2, d1, d2 = p["a1"], p["b1"], p["a2"], p["b2"], p["d1"], p["d2"]

    def f(y):
        x, yv, z = y
        f1 = a1 * x / (1 + b1 * x)
        f2 = a2 * yv / (1 + b2 * yv)
        return (
            x * (1 - x) - f1 * yv,
            f1 * yv - f2 * z - d1 * yv,
            f2 * z - d2 * z,
        )
    return f


def _rosenzweig_macarthur_rhs(p):
    r, K, a, h, e, m = p["r"], p["K"], p["a"], p["h"], p["e"], p["m"]

    def f(y):
        x, yv = y
        pred_response = a * x / (1 + a * h * x) if x > 0 else 0.0
        return (
            r * x * (1 - x / K) - pred_response * yv,
            e * pred_response * yv - m * yv,
        )
    return f


def compute_predator_prey_chaos(
    mode="hastings_powell",
    params=None,
    initial_condition=None,
    dt=0.01,
    n_steps=6000,
    discard=2000,
    downsample_for_plot=500,
    **kwargs,
):
    if mode == "validate":
        return _validate_predator_prey_chaos()

    if mode == "hastings_powell":
        p = {**_HP_DEFAULTS, **(params or {})}
        ic = initial_condition or [0.5, 0.5, 10.0]
        f = _hastings_powell_rhs(p)
        species_names = ["x_recurso", "y_consumidor", "z_depredador"]
    elif mode == "rosenzweig_macarthur":
        p = {**_RM_DEFAULTS, **(params or {})}
        ic = initial_condition or [0.5, 0.5]
        f = _rosenzweig_macarthur_rhs(p)
        species_names = ["x_presa", "y_depredador"]
    else:
        return {"error": f"mode desconocido: {mode}"}

    traj = _integrate(f, ic, dt, n_steps, discard)
    if not traj:
        return {"error": "integracion no produjo puntos (n_steps/discard mal configurados)."}

    cols = list(zip(*traj))
    bounds = {species_names[i]: [round(min(cols[i]), 6), round(max(cols[i]), 6)] for i in range(len(species_names))}
    any_negative = any(min(c) < -1e-6 for c in cols)

    step = max(1, len(traj) // downsample_for_plot)
    idx = list(range(0, len(traj), step))
    sample = [
        {species_names[i]: round(traj[k][i], 6) for i in range(len(species_names))}
        for k in idx
    ]

    return {
        "mode": mode,
        "params_used": p,
        "initial_condition": ic,
        "n_points_integrated": len(traj),
        "species_bounds": bounds,
        "poblaciones_negativas_detectadas": bool(any_negative),
        "final_state": {species_names[i]: round(cols[i][-1], 6) for i in range(len(species_names))},
        "trajectory_sample": sample,
        "n_points_plot": len(idx),
        "nota": (
            "poblaciones_negativas_detectadas=True indicaria un problema numerico "
            "(dt muy grande para la rigidez del sistema) -- las poblaciones no "
            "deberian volverse negativas en ninguno de los dos modelos."
        ),
    }


def _validate_predator_prey_chaos() -> dict:
    """3 checks: 1) Hastings-Powell con params clasicos: la serie x(t) debe
    diagnosticarse como caotica (lambda1>0 via chaos_diagnosis_tool sobre la
    serie generada) -- es el resultado central citado en Hastings & Powell
    1991. 2) Rosenzweig-MacArthur con params default: NO debe diagnosticarse
    como claramente caotico (lambda1 <= 0.1, umbral generoso porque un ciclo
    limite puede dar lambda1 cercano a 0 con ruido numerico de estimacion) --
    contraste directo con HP, explota Poincare-Bendixson. 3) Ninguno de los
    dos modelos debe producir poblaciones negativas con los params/dt default
    (sanity check numerico basico, independiente de si el sistema es caotico)."""
    checks = []

    r_hp = compute_predator_prey_chaos(mode="hastings_powell", dt=0.01, n_steps=14000, discard=8000)
    if "error" in r_hp:
        checks.append({"name": "hastings_powell: sin error", "passed": False, "got": r_hp})
    else:
        checks.append({
            "name": "hastings_powell: sin poblaciones negativas (dt=0.01 estable)",
            "passed": not r_hp["poblaciones_negativas_detectadas"],
            "got": {"bounds": r_hp["species_bounds"]},
        })
        x_series = [p["x_recurso"] for p in r_hp["trajectory_sample"]]
        # serie de plot esta downsampled -- para el diagnostico de caos usamos
        # una corrida dedicada con mas puntos (downsample_for_plot alto = casi sin downsamplear)
        r_hp_full = compute_predator_prey_chaos(mode="hastings_powell", dt=0.01, n_steps=14000, discard=8000, downsample_for_plot=14000)
        x_full = [p["x_recurso"] for p in r_hp_full["trajectory_sample"]]
        diag_hp = compute_chaos_diagnosis(mode="series", series=x_full, dt=0.01)
        lambda1_hp = diag_hp.get("lambda1_comparacion_surrogates")
        checks.append({
            "name": "hastings_powell clasico: lambda1 > 0 (caos confirmado, Hastings & Powell 1991)",
            "passed": bool(lambda1_hp is not None and lambda1_hp > 0),
            "got": {"lambda1": lambda1_hp, "diagnostico": diag_hp.get("diagnostico")},
        })

    r_rm = compute_predator_prey_chaos(mode="rosenzweig_macarthur", dt=0.01, n_steps=14000, discard=8000, downsample_for_plot=14000)
    if "error" in r_rm:
        checks.append({"name": "rosenzweig_macarthur: sin error", "passed": False, "got": r_rm})
    else:
        checks.append({
            "name": "rosenzweig_macarthur: sin poblaciones negativas",
            "passed": not r_rm["poblaciones_negativas_detectadas"],
            "got": {"bounds": r_rm["species_bounds"]},
        })
        x_rm = [p["x_presa"] for p in r_rm["trajectory_sample"]]
        diag_rm = compute_chaos_diagnosis(mode="series", series=x_rm, dt=0.01)
        lambda1_rm = diag_rm.get("lambda1_comparacion_surrogates")
        checks.append({
            "name": "rosenzweig_macarthur: lambda1 <= 0.1 (NO caotico, contraste con HP via Poincare-Bendixson)",
            "passed": bool(lambda1_rm is not None and lambda1_rm <= 0.1),
            "got": {"lambda1": lambda1_rm, "diagnostico": diag_rm.get("diagnostico")},
        })

    return {"mode": "validate", "validation_passed": all(c["passed"] for c in checks), "checks": checks}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_predator_prey_chaos(mode="hastings_powell"), indent=2, ensure_ascii=False)[:2000])
    print("---VALIDATE---")
    print(json.dumps(_validate_predator_prey_chaos(), indent=2, ensure_ascii=False))


try:
    from tool_registry import register_tool
    register_tool(
        name="predator_prey_chaos",
        schema={**PREDATOR_PREY_CHAOS_SCHEMA, "name": "predator_prey_chaos"},
        handler=lambda args: compute_predator_prey_chaos(**args),
    )
except ImportError:
    pass
