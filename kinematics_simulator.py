#!/usr/bin/env python3
"""
kinematics_simulator
---------------------
Integra numéricamente (RK4) el movimiento de una partícula bajo
gravedad constante y, opcionalmente, arrastre (drag) proporcional a v^2.

mode="run"      -> devuelve posición y velocidad en cada paso.
mode="validate" -> dos chequeos:
      1) sin arrastre: compara la trayectoria RK4 contra la solución
         analítica del tiro parabólico (precisión del integrador).
      2) sin arrastre: verifica conservación de energía mecánica
         (KE + PE gravitatoria) a lo largo de la simulación.
   (con arrastre, la energía debe *disminuir* monótonamente; también
    se reporta como chequeo informativo si se pide explícitamente)
"""

import numpy as np


def _derivatives(state, g, drag_coeff, mass):
    # state = [x, y, vx, vy]
    vx, vy = state[2], state[3]
    v = np.array([vx, vy])
    speed = np.linalg.norm(v)

    ax, ay = 0.0, -g
    if drag_coeff > 0 and speed > 1e-9:
        drag_acc = -(drag_coeff / mass) * speed * v
        ax += drag_acc[0]
        ay += drag_acc[1]

    return np.array([vx, vy, ax, ay])


def simulate_kinematics(params):
    g = params.get("g", 9.81)
    mass = params.get("mass", 1.0)
    drag_coeff = params.get("drag_coeff", 0.0)
    dt = params.get("dt", 0.001)

    x0 = params.get("x0", 0.0)
    y0 = params.get("y0", 0.0)
    speed0 = params.get("speed0", 20.0)
    angle_deg = params.get("angle_deg", 45.0)
    angle = np.radians(angle_deg)
    vx0 = speed0 * np.cos(angle)
    vy0 = speed0 * np.sin(angle)

    state = np.array([x0, y0, vx0, vy0], dtype=float)

    positions = [state[0:2].copy()]
    velocities = [state[2:4].copy()]
    times = [0.0]
    t = 0.0

    max_steps = int(params.get("max_steps", 200000))
    steps = 0
    while state[1] >= 0.0 and steps < max_steps:
        k1 = _derivatives(state, g, drag_coeff, mass)
        k2 = _derivatives(state + 0.5 * dt * k1, g, drag_coeff, mass)
        k3 = _derivatives(state + 0.5 * dt * k2, g, drag_coeff, mass)
        k4 = _derivatives(state + dt * k3, g, drag_coeff, mass)
        state = state + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        t += dt
        steps += 1
        positions.append(state[0:2].copy())
        velocities.append(state[2:4].copy())
        times.append(t)

    return {
        "positions": [p.tolist() for p in positions],
        "velocities": [v.tolist() for v in velocities],
        "times": times,
        "params": {
            "g": g, "mass": mass, "drag_coeff": drag_coeff, "dt": dt,
            "x0": x0, "y0": y0, "speed0": speed0, "angle_deg": angle_deg,
        },
    }


def analytical_projectile(t, x0, y0, vx0, vy0, g):
    x = x0 + vx0 * t
    y = y0 + vy0 * t - 0.5 * g * t**2
    return x, y


def _mode_run(params):
    return simulate_kinematics(params)


def _mode_validate(params):
    tol_position = params.get("tol_position", 1e-3)   # error absoluto máx permitido
    tol_energy = params.get("tol_energy", 1e-4)        # drift relativo permitido

    # --- Caso sin arrastre: precisión del integrador vs solución analítica ---
    no_drag_params = dict(params.get("kinematics_params", {}))
    no_drag_params["drag_coeff"] = 0.0
    result = simulate_kinematics(no_drag_params)

    g = result["params"]["g"]
    x0, y0 = result["params"]["x0"], result["params"]["y0"]
    speed0 = result["params"]["speed0"]
    angle = np.radians(result["params"]["angle_deg"])
    vx0, vy0 = speed0 * np.cos(angle), speed0 * np.sin(angle)

    max_pos_error = 0.0
    for t, (x_num, y_num) in zip(result["times"], result["positions"]):
        x_an, y_an = analytical_projectile(t, x0, y0, vx0, vy0, g)
        err = np.hypot(x_num - x_an, y_num - y_an)
        max_pos_error = max(max_pos_error, err)

    checks = [
        {
            "name": "kinematics_analytical_agreement",
            "passed": bool(max_pos_error < tol_position),
            "detail": {"max_position_error": max_pos_error, "tolerance": tol_position},
        }
    ]

    # --- Conservación de energía mecánica (sin arrastre) ---
    mass = result["params"]["mass"]
    energies = []
    for (x, y), (vx, vy) in zip(result["positions"], result["velocities"]):
        ke = 0.5 * mass * (vx**2 + vy**2)
        pe = mass * g * y
        energies.append(ke + pe)

    e0 = energies[0]
    e_drift = max(abs(e - e0) for e in energies)
    rel_e_drift = e_drift / max(abs(e0), 1e-9)

    checks.append({
        "name": "kinematics_energy_conservation",
        "passed": bool(rel_e_drift < tol_energy),
        "detail": {"relative_drift": rel_e_drift, "tolerance": tol_energy},
    })

    # --- Chequeo informativo: con arrastre, la energía debe disminuir monótonamente ---
    drag_summary = None
    if params.get("check_drag_dissipation", True):
        drag_params = dict(params.get("kinematics_params", {}))
        drag_params["drag_coeff"] = params.get("drag_coeff_test", 0.05)
        drag_result = simulate_kinematics(drag_params)
        dmass = drag_result["params"]["mass"]
        dg = drag_result["params"]["g"]
        drag_energies = []
        for (x, y), (vx, vy) in zip(drag_result["positions"], drag_result["velocities"]):
            ke = 0.5 * dmass * (vx**2 + vy**2)
            pe = dmass * dg * y
            drag_energies.append(ke + pe)
        # con arrastre, la energía mecánica debe ser no creciente (dentro de tolerancia numérica)
        increases = [drag_energies[i+1] - drag_energies[i] for i in range(len(drag_energies)-1)]
        max_increase = max(increases) if increases else 0.0
        monotonic_ok = max_increase < 1e-6 * max(abs(drag_energies[0]), 1.0)
        checks.append({
            "name": "kinematics_drag_dissipates_energy",
            "passed": bool(monotonic_ok),
            "detail": {"max_energy_increase_step": max_increase},
        })
        drag_summary = {
            "energy_start": drag_energies[0],
            "energy_end": drag_energies[-1],
        }

    validation_passed = all(c["passed"] for c in checks)

    return {
        "validation_passed": validation_passed,
        "checks": checks,
        "summary": {
            "max_position_error_vs_analytical": max_pos_error,
            "energy_relative_drift": rel_e_drift,
            "n_steps": len(result["times"]) - 1,
            "drag_test": drag_summary,
        },
    }


def run(mode, params=None):
    params = params or {}
    if mode == "validate":
        return _mode_validate(params)
    if mode == "simulate_projectile":
        return _mode_run(params)
    return {"error": f"unknown mode '{mode}'"}


if __name__ == "__main__":
    import json
    print(json.dumps(run("validate", {}), indent=2))


# ============================================================================
# TOOL REGISTRATION (auto-agregado)
# ============================================================================

TOOL_SCHEMA = {
    "name": "kinematics_simulator",
    "description": (
        "Integra con RK4 la trayectoria de una particula bajo gravedad "
        "constante, con arrastre (drag) opcional proporcional a v^2. "
        "simulate_projectile devuelve posicion/velocidad por paso; "
        "validate compara contra la solucion analitica del tiro parabolico "
        "y verifica conservacion de energia mecanica (sin arrastre)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "description": "Modo de operacion",
                "enum": ["simulate_projectile", "validate"],
                "type": "string",
            },
            "g": {"description": "Aceleracion gravitatoria, default 9.81", "type": "number"},
            "mass": {"description": "Masa de la particula, default 1.0", "type": "number"},
            "drag_coeff": {"description": "Coeficiente de arrastre (0 = sin arrastre), default 0.0", "type": "number"},
            "dt": {"description": "Paso de integracion RK4, default 0.001", "type": "number"},
            "x0": {"description": "Posicion inicial x, default 0.0", "type": "number"},
            "y0": {"description": "Posicion inicial y (altura), default 0.0", "type": "number"},
            "speed0": {"description": "Rapidez inicial, default 20.0", "type": "number"},
            "angle_deg": {"description": "Angulo de lanzamiento en grados, default 45.0", "type": "number"},
            "max_steps": {"description": "Limite de pasos de integracion, default 200000", "type": "integer"},
            "tol_position": {"description": "Error absoluto maximo permitido vs solucion analitica para validate, default 1e-3", "type": "number"},
            "tol_energy": {"description": "Drift relativo de energia permitido para validate, default 1e-4", "type": "number"},
            "kinematics_params": {"description": "Overrides de parametros (g, mass, x0, y0, speed0, angle_deg, dt) para el sub-chequeo analitico en modo validate", "type": "object"},
            "check_drag_dissipation": {"description": "Si true (default), agrega un chequeo informativo de que la energia disminuye monotonamente con arrastre", "type": "boolean"},
            "drag_coeff_test": {"description": "Coeficiente de arrastre usado solo para el chequeo de disipacion, default 0.05", "type": "number"},
        },
        "required": ["mode"],
    },
}


def _handler(arguments):
    mode = arguments.get("mode", "validate")
    result = run(mode, arguments)
    if mode == "validate" and isinstance(result, dict) and "passed" in result and "total" in result:
        details = result.get("details", [])
        return {
            "validation_passed": result.get("passed", 0) == result.get("total", 0),
            "checks": [
                {"name": f"check_{i}", "passed": "\u2713" in str(d), "detail": str(d)}
                for i, d in enumerate(details)
            ],
            "n_checks": result.get("total", 0),
            "n_passed": result.get("passed", 0),
        }
    return result


def _register():
    try:
        import tool_registry
        tool_registry.register_tool(TOOL_SCHEMA["name"], TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()
