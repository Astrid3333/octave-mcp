#!/usr/bin/env python3
"""
particle_simulation_tool
-------------------------
Simulación de dos cuerpos:
  - modo físico "kepler": órbita gravitacional de dos cuerpos, integrada con RK4.
  - modo físico "collision": colisión elástica de dos partículas (esferas duras, 2D).

mode="run"      -> devuelve la trayectoria simulada.
mode="validate" -> corre ambos escenarios físicos con parámetros por defecto
                    (o los que se pasen) y verifica conservación de:
                      * energía mecánica total (KE + PE)
                      * momento lineal total (px, py)
                      * momento angular total (solo para "kepler")
"""

import numpy as np

G_DEFAULT = 1.0


# ----------------------------------------------------------------------
# Utilidades físicas
# ----------------------------------------------------------------------

def kinetic_energy(m, v):
    return 0.5 * m * float(np.dot(v, v))


def grav_potential_energy(m1, m2, r1, r2, G):
    d = np.linalg.norm(r1 - r2)
    d = max(d, 1e-9)
    return -G * m1 * m2 / d


def total_momentum(m1, v1, m2, v2):
    return m1 * v1 + m2 * v2


def angular_momentum(m, r, v):
    # L_z en 2D: m * (x*vy - y*vx)
    return m * (r[0] * v[1] - r[1] * v[0])


# ----------------------------------------------------------------------
# Escenario 1: órbita de Kepler (RK4)
# ----------------------------------------------------------------------

def _kepler_derivatives(state, m1, m2, G):
    r1 = state[0:2]
    r2 = state[2:4]
    v1 = state[4:6]
    v2 = state[6:8]

    d = r2 - r1
    dist = np.linalg.norm(d)
    dist = max(dist, 1e-6)
    f = G * m1 * m2 / dist**3 * d  # fuerza sobre 1, dirigida hacia 2

    a1 = f / m1
    a2 = -f / m2

    return np.concatenate([v1, v2, a1, a2])


def simulate_kepler(params):
    m1 = params.get("m1", 1.0)
    m2 = params.get("m2", 1000.0)
    G = params.get("G", G_DEFAULT)
    dt = params.get("dt", 0.001)
    steps = int(params.get("steps", 4000))

    r1 = np.array(params.get("r1", [0.0, 0.0]), dtype=float)
    r2 = np.array(params.get("r2", [1.0, 0.0]), dtype=float)

    d_vec = r2 - r1
    dist = max(np.linalg.norm(d_vec), 1e-6)
    # velocidad circular relativa correcta (marco del centro de masa),
    # perpendicular a la línea que une los cuerpos
    tangent = np.array([-d_vec[1], d_vec[0]]) / dist
    v_rel_mag = float(np.sqrt(G * (m1 + m2) / dist))
    v_rel = v_rel_mag * tangent

    default_v1 = (-m2 / (m1 + m2)) * v_rel
    default_v2 = (m1 / (m1 + m2)) * v_rel

    v1 = np.array(params.get("v1", default_v1.tolist()), dtype=float)
    v2 = np.array(params.get("v2", default_v2.tolist()), dtype=float)

    state = np.concatenate([r1, r2, v1, v2])

    traj = [state.copy()]
    energies = []
    momenta = []
    ang_momenta = []

    def record(s):
        r1_, r2_, v1_, v2_ = s[0:2], s[2:4], s[4:6], s[6:8]
        ke = kinetic_energy(m1, v1_) + kinetic_energy(m2, v2_)
        pe = grav_potential_energy(m1, m2, r1_, r2_, G)
        energies.append(ke + pe)
        p = total_momentum(m1, v1_, m2, v2_)
        momenta.append(p.copy())
        L = angular_momentum(m1, r1_, v1_) + angular_momentum(m2, r2_, v2_)
        ang_momenta.append(L)

    record(state)

    for _ in range(steps):
        k1 = _kepler_derivatives(state, m1, m2, G)
        k2 = _kepler_derivatives(state + 0.5 * dt * k1, m1, m2, G)
        k3 = _kepler_derivatives(state + 0.5 * dt * k2, m1, m2, G)
        k4 = _kepler_derivatives(state + dt * k3, m1, m2, G)
        state = state + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        traj.append(state.copy())
        record(state)

    return {
        "trajectory": [s.tolist() for s in traj],
        "energies": energies,
        "momenta": [p.tolist() for p in momenta],
        "angular_momenta": ang_momenta,
    }


# ----------------------------------------------------------------------
# Escenario 2: colisión elástica de esferas duras (2D)
# ----------------------------------------------------------------------

def elastic_collision_2d(m1, v1, m2, v2, r1, r2):
    """
    Colisión elástica 2D entre esferas duras, a lo largo de la línea
    que une los centros en el instante del choque (r1, r2).
    Devuelve (v1_after, v2_after).
    """
    n = (r2 - r1)
    dist = np.linalg.norm(n)
    n = n / max(dist, 1e-9)

    v1n = np.dot(v1, n)
    v2n = np.dot(v2, n)
    v1t = v1 - v1n * n
    v2t = v2 - v2n * n

    # componentes normales tras choque elástico 1D
    v1n_after = ((m1 - m2) * v1n + 2 * m2 * v2n) / (m1 + m2)
    v2n_after = ((m2 - m1) * v2n + 2 * m1 * v1n) / (m1 + m2)

    v1_after = v1t + v1n_after * n
    v2_after = v2t + v2n_after * n
    return v1_after, v2_after


def simulate_collision(params):
    m1 = params.get("m1", 2.0)
    m2 = params.get("m2", 3.0)
    r1 = np.array(params.get("r1", [-1.0, 0.0]), dtype=float)
    r2 = np.array(params.get("r2", [1.0, 0.0]), dtype=float)
    v1_before = np.array(params.get("v1", [1.5, 0.2]), dtype=float)
    v2_before = np.array(params.get("v2", [-0.7, -0.1]), dtype=float)

    ke_before = kinetic_energy(m1, v1_before) + kinetic_energy(m2, v2_before)
    p_before = total_momentum(m1, v1_before, m2, v2_before)

    v1_after, v2_after = elastic_collision_2d(m1, v1_before, m2, v2_before, r1, r2)

    ke_after = kinetic_energy(m1, v1_after) + kinetic_energy(m2, v2_after)
    p_after = total_momentum(m1, v1_after, m2, v2_after)

    return {
        "v1_before": v1_before.tolist(),
        "v2_before": v2_before.tolist(),
        "v1_after": v1_after.tolist(),
        "v2_after": v2_after.tolist(),
        "ke_before": ke_before,
        "ke_after": ke_after,
        "p_before": p_before.tolist(),
        "p_after": p_after.tolist(),
    }


# ----------------------------------------------------------------------
# Modes
# ----------------------------------------------------------------------

def _mode_simulate_kepler_orbit(params):
    return {"scenario": "kepler", "result": simulate_kepler(params)}


def _mode_simulate_elastic_collision(params):
    return {"scenario": "collision", "result": simulate_collision(params)}


def _mode_validate(params):
    tol_energy = params.get("tol_energy", 1e-2)   # tolerancia relativa
    tol_momentum = params.get("tol_momentum", 1e-6)  # tolerancia absoluta

    checks = []

    # --- Kepler orbit ---
    kep_params = dict(params.get("kepler_params", {}))
    kep = simulate_kepler(kep_params)

    e0 = kep["energies"][0]
    e_drift = max(abs(e - e0) for e in kep["energies"])
    rel_e_drift = e_drift / max(abs(e0), 1e-9)
    checks.append({
        "name": "kepler_energy_conservation",
        "passed": bool(rel_e_drift < tol_energy),
        "detail": {"relative_drift": rel_e_drift, "tolerance": tol_energy},
    })

    p0 = np.array(kep["momenta"][0])
    p_drift = max(float(np.linalg.norm(np.array(p) - p0)) for p in kep["momenta"])
    checks.append({
        "name": "kepler_momentum_conservation",
        "passed": bool(p_drift < max(tol_momentum, 1e-6 * (np.linalg.norm(p0) + 1))),
        "detail": {"drift": p_drift},
    })

    L0 = kep["angular_momenta"][0]
    L_drift = max(abs(L - L0) for L in kep["angular_momenta"])
    rel_L_drift = L_drift / max(abs(L0), 1e-9)
    checks.append({
        "name": "kepler_angular_momentum_conservation",
        "passed": bool(rel_L_drift < tol_energy),
        "detail": {"relative_drift": rel_L_drift, "tolerance": tol_energy},
    })

    # --- Elastic collision ---
    coll_params = dict(params.get("collision_params", {}))
    coll = simulate_collision(coll_params)

    ke_rel_diff = abs(coll["ke_after"] - coll["ke_before"]) / max(abs(coll["ke_before"]), 1e-9)
    checks.append({
        "name": "collision_energy_conservation",
        "passed": bool(ke_rel_diff < 1e-9),
        "detail": {"relative_diff": ke_rel_diff},
    })

    p_before = np.array(coll["p_before"])
    p_after = np.array(coll["p_after"])
    p_diff = float(np.linalg.norm(p_after - p_before))
    checks.append({
        "name": "collision_momentum_conservation",
        "passed": bool(p_diff < 1e-9),
        "detail": {"diff": p_diff},
    })

    validation_passed = all(c["passed"] for c in checks)

    return {
        "validation_passed": validation_passed,
        "checks": checks,
        "kepler_summary": {
            "energy_relative_drift": rel_e_drift,
            "momentum_drift": p_drift,
            "angular_momentum_relative_drift": rel_L_drift,
        },
        "collision_summary": {
            "ke_relative_diff": ke_rel_diff,
            "momentum_diff": p_diff,
        },
    }


def run(mode, params=None):
    params = params or {}
    if mode == "validate":
        return _mode_validate(params)
    if mode == "simulate_kepler_orbit":
        return _mode_simulate_kepler_orbit(params)
    if mode == "simulate_elastic_collision":
        return _mode_simulate_elastic_collision(params)
    return {"error": f"unknown mode '{mode}'"}


if __name__ == "__main__":
    import json
    print(json.dumps(run("validate", {}), indent=2))


# ============================================================================
# TOOL REGISTRATION (auto-agregado)
# ============================================================================

TOOL_SCHEMA = {
    "name": "particle_simulation_tool",
    "description": (
        "Simula colisiones elasticas y orbitas gravitacionales de Kepler entre "
        "dos cuerpos (RK4). simulate_kepler_orbit devuelve la trayectoria "
        "orbital; simulate_elastic_collision devuelve el resultado de una "
        "colision elastica 2D; validate verifica conservacion de energia, "
        "momento lineal y momento angular."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "description": "Modo de operacion",
                "enum": [
                    "simulate_kepler_orbit",
                    "simulate_elastic_collision",
                    "validate",
                ],
                "type": "string",
            },
            "m1": {"description": "Masa del cuerpo 1", "type": "number"},
            "m2": {"description": "Masa del cuerpo 2", "type": "number"},
            "r1": {"description": "Posicion inicial [x, y] del cuerpo 1", "type": "array", "items": {"type": "number"}},
            "r2": {"description": "Posicion inicial [x, y] del cuerpo 2", "type": "array", "items": {"type": "number"}},
            "v1": {"description": "Velocidad inicial [vx, vy] del cuerpo 1 (opcional; por defecto orbita circular)", "type": "array", "items": {"type": "number"}},
            "v2": {"description": "Velocidad inicial [vx, vy] del cuerpo 2 (opcional; por defecto orbita circular)", "type": "array", "items": {"type": "number"}},
            "G": {"description": "Constante gravitacional, default 1.0", "type": "number"},
            "dt": {"description": "Paso de integracion RK4, default 0.001", "type": "number"},
            "steps": {"description": "Numero de pasos de integracion, default 4000", "type": "integer"},
            "tol_energy": {"description": "Tolerancia relativa de drift de energia/momento angular para validate, default 0.01", "type": "number"},
            "tol_momentum": {"description": "Tolerancia absoluta de drift de momento lineal para validate, default 1e-6", "type": "number"},
            "kepler_params": {"description": "Overrides de parametros (m1, m2, r1, r2, v1, v2, G, dt, steps) para el sub-chequeo de orbita en modo validate", "type": "object"},
            "collision_params": {"description": "Overrides de parametros (m1, m2, r1, r2, v1, v2) para el sub-chequeo de colision en modo validate", "type": "object"},
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
