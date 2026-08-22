"""
kinematics_simulator: simulacion de cinematica/dinamica de particulas via
integracion numerica RK4, con varios modelos de fuerza predefinidos
(gravedad uniforme, gravedad + arrastre, oscilador armonico/resorte).

Estado por particula: [x, y, (z), vx, vy, (vz)] -- 2D o 3D segun la
dimensionalidad de position/velocity inicial.

Convenciones:
- Todas las unidades son consistentes con el usuario (SI por default:
  metros, segundos, m/s, m/s^2).
- La integracion es RK4 de paso fijo (mismo patron que
  virtual_pharmacokinetics.py), no adaptativo.
"""

import sys
import json

import numpy as np


# ---------------------------------------------------------------------------
# validacion
# ---------------------------------------------------------------------------

def _validate_vec(v, name, ndim_expected=None):
    if v is None:
        raise ValueError(f"falta '{name}' en params")
    arr = np.array(v, dtype=float)
    if arr.ndim != 1:
        raise ValueError(f"{name} debe ser un vector 1D (lista de numeros)")
    if arr.shape[0] not in (2, 3):
        raise ValueError(f"{name} debe tener 2 o 3 componentes (2D o 3D), tiene {arr.shape[0]}")
    if ndim_expected is not None and arr.shape[0] != ndim_expected:
        raise ValueError(f"{name} tiene {arr.shape[0]} componentes, esperado {ndim_expected} (debe coincidir con position)")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contiene valores no finitos (NaN/inf)")
    return arr


def _validate_physical_params(params, ndim):
    mass = float(params.get("mass", 1.0))
    if mass <= 0:
        raise ValueError("mass debe ser > 0")

    force_model = params.get("force_model", "gravity")
    valid_models = ("gravity", "gravity_drag", "spring", "custom_constant")
    if force_model not in valid_models:
        raise ValueError(f"force_model desconocido: {force_model} (usar {'/'.join(valid_models)})")

    gravity_vec = params.get("gravity")
    if gravity_vec is None:
        # default: gravedad terrestre hacia -y (o -z en 3D, convencion: ultimo eje es "arriba")
        gravity_vec = [0.0] * ndim
        gravity_vec[-1] = -9.8
    gravity_vec = _validate_vec(gravity_vec, "gravity", ndim)

    drag_coeff = float(params.get("drag_coeff", 0.0))
    if drag_coeff < 0:
        raise ValueError("drag_coeff debe ser >= 0")

    spring_k = float(params.get("spring_k", 1.0))
    if force_model == "spring" and spring_k < 0:
        raise ValueError("spring_k debe ser >= 0")

    spring_anchor = params.get("spring_anchor")
    if spring_anchor is None:
        spring_anchor = [0.0] * ndim
    spring_anchor = _validate_vec(spring_anchor, "spring_anchor", ndim)

    custom_force = params.get("custom_force")
    if force_model == "custom_constant":
        if custom_force is None:
            raise ValueError("force_model='custom_constant' requiere 'custom_force' (vector de fuerza constante)")
        custom_force = _validate_vec(custom_force, "custom_force", ndim)

    return {
        "mass": mass,
        "force_model": force_model,
        "gravity": gravity_vec,
        "drag_coeff": drag_coeff,
        "spring_k": spring_k,
        "spring_anchor": spring_anchor,
        "custom_force": custom_force,
    }


# ---------------------------------------------------------------------------
# modelos de fuerza -> aceleracion
# ---------------------------------------------------------------------------

def _acceleration(pos, vel, phys):
    mass = phys["mass"]
    model = phys["force_model"]

    if model == "gravity":
        return phys["gravity"].copy()

    elif model == "gravity_drag":
        speed = np.linalg.norm(vel)
        drag_accel = -phys["drag_coeff"] * speed * vel / mass if speed > 1e-12 else np.zeros_like(vel)
        return phys["gravity"] + drag_accel

    elif model == "spring":
        # F = -k * (pos - anchor), sin gravedad (oscilador puro)
        displacement = pos - phys["spring_anchor"]
        return -phys["spring_k"] * displacement / mass

    elif model == "custom_constant":
        return phys["custom_force"] / mass

    else:
        raise ValueError(f"force_model desconocido: {model}")


def _derivative(state, ndim, phys):
    pos = state[:ndim]
    vel = state[ndim:]
    accel = _acceleration(pos, vel, phys)
    return np.concatenate([vel, accel])


def _rk4_step(state, dt, ndim, phys):
    k1 = _derivative(state, ndim, phys)
    k2 = _derivative(state + 0.5 * dt * k1, ndim, phys)
    k3 = _derivative(state + 0.5 * dt * k2, ndim, phys)
    k4 = _derivative(state + dt * k3, ndim, phys)
    return state + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)


# ---------------------------------------------------------------------------
# modo principal
# ---------------------------------------------------------------------------

def simulate(params):
    params = params or {}
    position = _validate_vec(params.get("position"), "position")
    ndim = position.shape[0]
    velocity = _validate_vec(params.get("velocity", [0.0] * ndim), "velocity", ndim)

    t_end = float(params.get("t_end", 10.0))
    if t_end <= 0:
        raise ValueError("t_end debe ser > 0")
    n_steps = int(params.get("n_steps", 1000))
    if n_steps < 1:
        raise ValueError("n_steps debe ser >= 1")

    phys = _validate_physical_params(params, ndim)

    dt = t_end / n_steps
    state = np.concatenate([position, velocity])

    stop_at_ground = bool(params.get("stop_at_ground", False))
    ground_axis = ndim - 1  # ultimo eje = "altura" por convencion

    times = [0.0]
    trajectory = [state.copy()]

    t = 0.0
    for _ in range(n_steps):
        new_state = _rk4_step(state, dt, ndim, phys)
        t += dt

        if stop_at_ground and new_state[ground_axis] < 0.0 and state[ground_axis] >= 0.0:
            # interpolacion lineal simple para encontrar el cruce con altura=0
            frac = state[ground_axis] / (state[ground_axis] - new_state[ground_axis])
            crossing_state = state + frac * (new_state - state)
            crossing_t = t - dt + frac * dt
            times.append(crossing_t)
            trajectory.append(crossing_state.copy())
            state = crossing_state
            break

        state = new_state
        times.append(t)
        trajectory.append(state.copy())

    trajectory = np.array(trajectory)
    positions = trajectory[:, :ndim]
    velocities = trajectory[:, ndim:]

    return {
        "ndim": ndim,
        "n_points": len(times),
        "dt": dt,
        "force_model": phys["force_model"],
        "times": times,
        "positions": positions.tolist(),
        "velocities": velocities.tolist(),
        "final_position": positions[-1].tolist(),
        "final_velocity": velocities[-1].tolist(),
        "stopped_at_ground": bool(stop_at_ground and times[-1] < t_end),
    }


TOOL_SCHEMA = {
    "name": "kinematics_simulator",
    "description": (
        "Simulacion de cinematica/dinamica de particulas via integracion "
        "numerica RK4 de paso fijo. Modelos de fuerza: gravity (gravedad "
        "uniforme), gravity_drag (gravedad + arrastre cuadratico en "
        "velocidad), spring (oscilador armonico hacia un punto ancla), "
        "custom_constant (fuerza constante arbitraria). Modos: simulate, "
        "self_test."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["simulate", "self_test", "validate"]},
            "params": {
                "type": "object",
                "properties": {
                    "position": {"type": "array", "items": {"type": "number"}, "description": "posicion inicial [x,y] o [x,y,z]"},
                    "velocity": {"type": "array", "items": {"type": "number"}, "description": "velocidad inicial, mismo ndim que position (default: cero)"},
                    "mass": {"type": "number", "description": "masa (default 1.0)"},
                    "force_model": {"type": "string", "enum": ["gravity", "gravity_drag", "spring", "custom_constant"]},
                    "gravity": {"type": "array", "items": {"type": "number"}, "description": "vector de gravedad (default: -9.8 en el ultimo eje)"},
                    "drag_coeff": {"type": "number", "description": "coeficiente de arrastre cuadratico, para force_model=gravity_drag (default 0)"},
                    "spring_k": {"type": "number", "description": "constante de resorte, para force_model=spring (default 1.0)"},
                    "spring_anchor": {"type": "array", "items": {"type": "number"}, "description": "punto de anclaje del resorte (default: origen)"},
                    "custom_force": {"type": "array", "items": {"type": "number"}, "description": "vector de fuerza constante, para force_model=custom_constant"},
                    "t_end": {"type": "number", "description": "tiempo total de simulacion (default 10.0)"},
                    "n_steps": {"type": "integer", "description": "numero de pasos RK4 (default 1000)"},
                    "stop_at_ground": {"type": "boolean", "description": "si true, detiene la simulacion cuando la ultima coordenada cruza 0 (default false)"},
                },
                "required": ["position"],
            },
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------------------
# self_test
# ---------------------------------------------------------------------------

def run_self_test():
    checks = []

    def check(name, cond, detail=""):
        checks.append({"name": name, "passed": bool(cond), "detail": detail})

    # 1) proyectil sin arrastre: comparar contra solucion analitica
    v0, angle_deg, g = 50.0, 45.0, 9.8
    theta = np.radians(angle_deg)
    vx0, vy0 = v0 * np.cos(theta), v0 * np.sin(theta)

    out = simulate({
        "position": [0.0, 0.0],
        "velocity": [vx0, vy0],
        "force_model": "gravity",
        "gravity": [0.0, -g],
        "t_end": 2.0,
        "n_steps": 2000,
    })
    t_check = 2.0
    x_analytic = vx0 * t_check
    y_analytic = vy0 * t_check - 0.5 * g * t_check**2
    x_numeric, y_numeric = out["final_position"]
    err_x = abs(x_numeric - x_analytic)
    err_y = abs(y_numeric - y_analytic)
    check("proyectil sin arrastre: x(t) coincide con solucion analitica", err_x < 1e-3, f"analitico={x_analytic:.4f}, numerico={x_numeric:.4f}, err={err_x:.2e}")
    check("proyectil sin arrastre: y(t) coincide con solucion analitica", err_y < 1e-3, f"analitico={y_analytic:.4f}, numerico={y_numeric:.4f}, err={err_y:.2e}")

    # 2) tiempo de vuelo teorico
    t_vuelo_analitico = 2 * vy0 / g
    out_ground = simulate({
        "position": [0.0, 0.0],
        "velocity": [vx0, vy0],
        "force_model": "gravity",
        "gravity": [0.0, -g],
        "t_end": 20.0,
        "n_steps": 20000,
        "stop_at_ground": True,
    })
    t_vuelo_numerico = out_ground["times"][-1]
    err_t = abs(t_vuelo_numerico - t_vuelo_analitico)
    check("proyectil: tiempo de vuelo coincide con 2*vy0/g", err_t < 1e-2, f"analitico={t_vuelo_analitico:.4f}, numerico={t_vuelo_numerico:.4f}")
    check("proyectil: stop_at_ground detiene con altura final ~0", abs(out_ground["final_position"][1]) < 1e-2, f"y_final={out_ground['final_position'][1]:.4e}")

    # 3) oscilador armonico: periodo T = 2*pi*sqrt(m/k)
    m, k = 2.0, 8.0
    T_analitico = 2 * np.pi * np.sqrt(m / k)
    x0_osc = 1.0
    out_osc = simulate({
        "position": [x0_osc, 0.0],
        "velocity": [0.0, 0.0],
        "force_model": "spring",
        "mass": m,
        "spring_k": k,
        "spring_anchor": [0.0, 0.0],
        "t_end": T_analitico,
        "n_steps": 5000,
    })
    x_final_osc = out_osc["final_position"][0]
    err_osc = abs(x_final_osc - x0_osc)
    check("oscilador armonico: retorna a x0 tras un periodo completo", err_osc < 1e-2, f"x0={x0_osc}, x_final={x_final_osc:.4f}, err={err_osc:.2e}")

    # 4) conservacion de energia en oscilador armonico
    positions_osc = np.array(out_osc["positions"])[:, 0]
    velocities_osc = np.array(out_osc["velocities"])[:, 0]
    energy = 0.5 * k * positions_osc**2 + 0.5 * m * velocities_osc**2
    energy_drift = (energy.max() - energy.min()) / energy[0]
    check("oscilador armonico: energia mecanica se conserva (drift < 1%)", energy_drift < 0.01, f"drift relativo={energy_drift:.4e}")

    # 5) 3D: caida libre en 3D con gravedad en eje z
    out_3d = simulate({
        "position": [0.0, 0.0, 100.0],
        "velocity": [1.0, 1.0, 0.0],
        "force_model": "gravity",
        "gravity": [0.0, 0.0, -9.8],
        "t_end": 1.0,
        "n_steps": 1000,
    })
    check("3D: ndim detectado correctamente", out_3d["ndim"] == 3, f"ndim={out_3d['ndim']}")
    z_analytic_3d = 100.0 - 0.5 * 9.8 * 1.0**2
    z_numeric_3d = out_3d["final_position"][2]
    err_z3d = abs(z_numeric_3d - z_analytic_3d)
    check("3D: caida libre en z coincide con solucion analitica", err_z3d < 1e-3, f"analitico={z_analytic_3d:.4f}, numerico={z_numeric_3d:.4f}")

    # 6) custom_constant: F constante => x(t) = 0.5*a*t^2 desde reposo
    F_custom = [4.0, 0.0]
    m_custom = 2.0
    a_expected = F_custom[0] / m_custom
    out_custom = simulate({
        "position": [0.0, 0.0],
        "velocity": [0.0, 0.0],
        "force_model": "custom_constant",
        "mass": m_custom,
        "custom_force": F_custom,
        "t_end": 3.0,
        "n_steps": 1000,
    })
    x_expected_custom = 0.5 * a_expected * 3.0**2
    err_custom = abs(out_custom["final_position"][0] - x_expected_custom)
    check("custom_constant: x(t)=0.5*a*t^2 desde reposo", err_custom < 1e-2, f"esperado={x_expected_custom:.4f}, obtenido={out_custom['final_position'][0]:.4f}")

    # 7) errores esperados
    try:
        simulate({"position": [0.0, 0.0], "velocity": [0.0, 0.0, 0.0]})
        check("ValueError con velocity de ndim distinto a position", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con velocity de ndim distinto a position", True, "")

    try:
        simulate({"position": [0.0]})
        check("ValueError con position de 1 componente", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con position de 1 componente", True, "")

    try:
        simulate({"position": [0.0, 0.0], "force_model": "modelo_inexistente"})
        check("ValueError con force_model desconocido", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con force_model desconocido", True, "")

    try:
        simulate({"position": [0.0, 0.0], "force_model": "custom_constant"})
        check("ValueError con custom_constant sin custom_force", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con custom_constant sin custom_force", True, "")

    try:
        run("modo_inexistente", {})
        check("ValueError con modo desconocido en run()", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con modo desconocido en run()", True, "")

    total = len(checks)
    passed = sum(1 for c in checks if c["passed"])
    return {"total": total, "passed": passed, "all_passed": passed == total, "checks": checks}


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

def run(mode, params=None):
    if mode == "validate":
        r = run_self_test()
        return {"checks": r["checks"], "validation_passed": r["all_passed"], "n_checks": r["total"]}
    if mode == "simulate":
        return simulate(params or {})
    elif mode == "self_test":
        return run_self_test()
    else:
        raise ValueError(f"modo desconocido: {mode} (usar simulate/self_test)")


if __name__ == "__main__":
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "self_test"
    params_arg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    try:
        out = run(mode_arg, params_arg)
        print(json.dumps(out, indent=2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)


def _register():
    """
    Auto-registro estilo octave-mcp (patron self-registrante via
    tool_registry, register_tool(name, schema, handler)).
    """
    try:
        import tool_registry

        def _handler(args):
            return run(args.get("mode"), args.get("params"))

        tool_registry.register_tool("kinematics_simulator", TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()
