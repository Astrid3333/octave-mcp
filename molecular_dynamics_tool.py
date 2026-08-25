#!/usr/bin/env python3
"""
molecular_dynamics_tool
------------------------
N partículas en 2D interactuando por un potencial de Lennard-Jones,
integradas con velocity Verlet (simpléctico -> buena conservación de
energía a largo plazo).

mode="run"      -> devuelve trayectorias, velocidades y energías por paso.
mode="validate" -> corre una simulación con N partículas y verifica:
                      * conservación de energía total (drift relativo)
                      * conservación de momento lineal total (px, py)
                        (exacta si no hay fuerzas externas, solo pares)
"""

import numpy as np

EPSILON_DEFAULT = 1.0
SIGMA_DEFAULT = 1.0


def lj_potential(r, epsilon, sigma):
    sr6 = (sigma / r) ** 6
    sr12 = sr6 ** 2
    return 4.0 * epsilon * (sr12 - sr6)


def lj_force_magnitude(r, epsilon, sigma):
    # F(r) = -dU/dr ; positivo = repulsivo (se aleja)
    sr6 = (sigma / r) ** 6
    sr12 = sr6 ** 2
    return 24.0 * epsilon * (2 * sr12 - sr6) / r


def compute_forces_and_energy(positions, epsilon, sigma, r_cut):
    n = positions.shape[0]
    forces = np.zeros_like(positions)
    pe = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            d = positions[i] - positions[j]
            r = np.linalg.norm(d)
            r = max(r, 1e-3)
            if r > r_cut:
                continue
            fmag = lj_force_magnitude(r, epsilon, sigma)
            fvec = fmag * (d / r)
            forces[i] += fvec
            forces[j] -= fvec
            pe += lj_potential(r, epsilon, sigma)
    return forces, pe


def simulate_md(params):
    n = int(params.get("n_particles", 4))
    epsilon = params.get("epsilon", EPSILON_DEFAULT)
    sigma = params.get("sigma", SIGMA_DEFAULT)
    mass = params.get("mass", 1.0)
    dt = params.get("dt", 0.005)
    steps = int(params.get("steps", 2000))
    r_cut = params.get("r_cut", 3.0 * sigma)

    rng = np.random.default_rng(params.get("seed", 42))

    if "positions" in params:
        positions = np.array(params["positions"], dtype=float)
        n = positions.shape[0]
    else:
        # rejilla espaciada a distancia de equilibrio (~2^(1/6) sigma) + jitter leve
        side = int(np.ceil(np.sqrt(n)))
        spacing = 1.3 * sigma
        positions = []
        for idx in range(n):
            gx, gy = idx % side, idx // side
            jitter = rng.uniform(-0.05, 0.05, size=2)
            positions.append([gx * spacing, gy * spacing] + jitter)
        positions = np.array(positions[:n], dtype=float)

    if "velocities" in params:
        velocities = np.array(params["velocities"], dtype=float)
    else:
        velocities = rng.uniform(-0.3, 0.3, size=(n, 2))
        # anular momento total inicial (marco del centro de masa)
        velocities -= velocities.mean(axis=0)

    masses = np.full(n, mass, dtype=float)

    forces, pe = compute_forces_and_energy(positions, epsilon, sigma, r_cut)

    traj = [positions.copy()]
    vels = [velocities.copy()]
    energies = []
    momenta = []

    def record(pos, vel, pe_val):
        ke = 0.5 * np.sum(masses[:, None] * vel**2)
        energies.append(ke + pe_val)
        p = (masses[:, None] * vel).sum(axis=0)
        momenta.append(p.copy())

    record(positions, velocities, pe)

    for _ in range(steps):
        # velocity Verlet
        accel = forces / masses[:, None]
        positions = positions + velocities * dt + 0.5 * accel * dt**2
        new_forces, pe = compute_forces_and_energy(positions, epsilon, sigma, r_cut)
        new_accel = new_forces / masses[:, None]
        velocities = velocities + 0.5 * (accel + new_accel) * dt
        forces = new_forces

        traj.append(positions.copy())
        vels.append(velocities.copy())
        record(positions, velocities, pe)

    return {
        "trajectory": [p.tolist() for p in traj],
        "velocities": [v.tolist() for v in vels],
        "energies": energies,
        "momenta": [p.tolist() for p in momenta],
        "n_particles": n,
    }


def _mode_run(params):
    return simulate_md(params)


def _mode_validate(params):
    tol_energy = params.get("tol_energy", 0.02)      # 2% drift relativo permitido
    tol_momentum = params.get("tol_momentum", 1e-6)  # debería ser ~exacto

    result = simulate_md(params)

    energies = result["energies"]
    e0 = energies[0]
    e_drift = max(abs(e - e0) for e in energies)
    rel_e_drift = e_drift / max(abs(e0), 1e-9)

    momenta = np.array(result["momenta"])
    p0 = momenta[0]
    p_drift = float(np.max(np.linalg.norm(momenta - p0, axis=1)))

    checks = [
        {
            "name": "md_energy_conservation",
            "passed": bool(rel_e_drift < tol_energy),
            "detail": {"relative_drift": rel_e_drift, "tolerance": tol_energy},
        },
        {
            "name": "md_momentum_conservation",
            "passed": bool(p_drift < max(tol_momentum, 1e-6 * (np.linalg.norm(p0) + 1))),
            "detail": {"drift": p_drift},
        },
    ]

    validation_passed = all(c["passed"] for c in checks)

    return {
        "validation_passed": validation_passed,
        "checks": checks,
        "summary": {
            "n_particles": result["n_particles"],
            "energy_relative_drift": rel_e_drift,
            "momentum_drift": p_drift,
            "n_steps": len(energies) - 1,
        },
    }


def run(mode, params=None):
    params = params or {}
    if mode == "validate":
        return _mode_validate(params)
    if mode == "simulate":
        return _mode_run(params)
    return {"error": f"unknown mode '{mode}'"}


if __name__ == "__main__":
    import json
    print(json.dumps(run("validate", {}), indent=2))


# ============================================================================
# TOOL REGISTRATION (auto-agregado)
# ============================================================================

TOOL_SCHEMA = {
    "name": "molecular_dynamics_tool",
    "description": (
        "Simula N particulas 2D interactuando por un potencial de "
        "Lennard-Jones, integradas con velocity Verlet (simplectico). "
        "simulate devuelve trayectorias/velocidades/energias por paso; "
        "validate verifica conservacion de energia total y momento lineal."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "description": "Modo de operacion",
                "enum": ["simulate", "validate"],
                "type": "string",
            },
            "n_particles": {"description": "Numero de particulas si no se pasan 'positions', default 4", "type": "integer"},
            "epsilon": {"description": "Profundidad del pozo de potencial Lennard-Jones, default 1.0", "type": "number"},
            "sigma": {"description": "Distancia de equilibrio Lennard-Jones, default 1.0", "type": "number"},
            "mass": {"description": "Masa de cada particula, default 1.0", "type": "number"},
            "dt": {"description": "Paso de integracion velocity Verlet, default 0.005", "type": "number"},
            "steps": {"description": "Numero de pasos de integracion, default 2000", "type": "integer"},
            "r_cut": {"description": "Radio de corte del potencial, default 3*sigma", "type": "number"},
            "seed": {"description": "Semilla aleatoria para posiciones/velocidades iniciales, default 42", "type": "integer"},
            "positions": {"description": "Posiciones iniciales [[x,y], ...] (opcional, si no se da se genera una rejilla)", "type": "array"},
            "velocities": {"description": "Velocidades iniciales [[vx,vy], ...] (opcional, si no se da se generan aleatorias con momento total nulo)", "type": "array"},
            "tol_energy": {"description": "Tolerancia relativa de drift de energia para validate, default 0.02", "type": "number"},
            "tol_momentum": {"description": "Tolerancia absoluta de drift de momento para validate, default 1e-6", "type": "number"},
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
