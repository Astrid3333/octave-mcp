"""
Dinamica molecular clasica: potencial de Lennard-Jones, integrador
velocity Verlet. Python puro + numpy, sin dependencias externas
(la matematica es simple, no justifica un submotor Rust ni subprocess).
"""
import numpy as np
import tool_registry


def _lj_forces_energy(positions, sigma, epsilon):
    n = positions.shape[0]
    forces = np.zeros_like(positions)
    pe = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            rij = positions[i] - positions[j]
            r = np.linalg.norm(rij)
            sr6 = (sigma / r) ** 6
            sr12 = sr6 ** 2
            pe += 4.0 * epsilon * (sr12 - sr6)
            fmag_over_r = 24.0 * epsilon / (r ** 2) * (2.0 * sr12 - sr6)
            f = fmag_over_r * rij
            forces[i] += f
            forces[j] -= f
    return forces, pe


def _run_verlet(positions, velocities, sigma, epsilon, mass, dt, n_steps):
    positions = np.array(positions, dtype=float)
    velocities = np.array(velocities, dtype=float)
    forces, pe = _lj_forces_energy(positions, sigma, epsilon)
    accel = forces / mass

    trajectory = [positions.copy().tolist()]
    ke0 = 0.5 * mass * float(np.sum(velocities ** 2))
    energies = [{"ke": ke0, "pe": pe, "total": ke0 + pe}]

    for _ in range(n_steps):
        v_half = velocities + 0.5 * accel * dt
        positions = positions + v_half * dt
        forces, pe = _lj_forces_energy(positions, sigma, epsilon)
        accel = forces / mass
        velocities = v_half + 0.5 * accel * dt
        ke = 0.5 * mass * float(np.sum(velocities ** 2))
        trajectory.append(positions.copy().tolist())
        energies.append({"ke": ke, "pe": pe, "total": ke + pe})

    return trajectory, energies


def compute_simulate(params):
    positions = params["positions"]
    n = len(positions)
    velocities = params.get("velocities", [[0.0, 0.0, 0.0]] * n)
    sigma = params.get("sigma", 1.0)
    epsilon = params.get("epsilon", 1.0)
    mass = params.get("mass", 1.0)
    dt = params.get("dt", 0.001)
    n_steps = params.get("n_steps", 1000)

    trajectory, energies = _run_verlet(positions, velocities, sigma, epsilon, mass, dt, n_steps)
    total0 = energies[0]["total"]
    totals = [e["total"] for e in energies]
    drift_max = max(abs(t - total0) for t in totals)
    drift_relative = drift_max / abs(total0) if total0 != 0 else drift_max

    return {
        "mode": "simulate",
        "n_particles": n,
        "n_steps": n_steps,
        "dt": dt,
        "sigma": sigma,
        "epsilon": epsilon,
        "mass": mass,
        "trajectory": trajectory,
        "energy_initial": energies[0],
        "energy_final": energies[-1],
        "energy_drift_max": drift_max,
        "energy_drift_relative": drift_relative,
    }


def compute_validate(params=None):
    checks = []

    # Check 1: equilibrio de 2 particulas -- fuerza neta exactamente cero en r_eq
    r_eq = 2.0 ** (1.0 / 6.0)  # sigma=1
    traj1, en1 = _run_verlet(
        positions=[[0.0, 0.0, 0.0], [r_eq, 0.0, 0.0]],
        velocities=[[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
        sigma=1.0, epsilon=1.0, mass=1.0, dt=0.001, n_steps=100)
    p0 = np.array(traj1[0])
    max_displacement = max(
        float(np.linalg.norm(np.array(p) - p0)) for p in traj1)
    checks.append({
        "name": "equilibrio 2 particulas en r_eq=2^(1/6)*sigma, fuerza neta cero, sin movimiento",
        "max_displacement": max_displacement,
        "passed": bool(max_displacement < 1e-9),
    })

    # Check 2: conservacion de energia NVE, grilla 4 particulas, momento neto cero
    traj2, en2 = _run_verlet(
        positions=[[0.0, 0.0, 0.0], [1.5, 0.0, 0.0], [0.0, 1.5, 0.0], [1.5, 1.5, 0.0]],
        velocities=[[0.1, 0.0, 0.0], [-0.1, 0.0, 0.0], [0.0, 0.1, 0.0], [0.0, -0.1, 0.0]],
        sigma=1.0, epsilon=1.0, mass=1.0, dt=0.001, n_steps=2000)
    total0 = en2[0]["total"]
    totals = [e["total"] for e in en2]
    drift_relative = max(abs(t - total0) for t in totals) / abs(total0)
    checks.append({
        "name": "conservacion de energia NVE, 4 particulas, 2000 pasos velocity Verlet",
        "energy_initial": total0,
        "energy_drift_relative": drift_relative,
        "passed": bool(drift_relative < 1e-3),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": bool(all_passed)}


MOLECULAR_DYNAMICS_TOOL_SCHEMA = {
    "name": "molecular_dynamics_tool",
    "description": (
        "Dinamica molecular clasica: potencial de Lennard-Jones, "
        "integrador velocity Verlet (simplectico, conserva energia en "
        "NVE). mode='validate' chequea equilibrio de 2 particulas "
        "(fuerza cero en r_eq) y conservacion de energia en un sistema "
        "de 4 particulas."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["simulate", "validate"]},
            "params": {
                "type": "object",
                "properties": {
                    "positions": {"type": "array", "description": "lista de [x,y,z] iniciales, requerido en simulate"},
                    "velocities": {"type": "array", "description": "lista de [vx,vy,vz] iniciales, default cero"},
                    "sigma": {"type": "number", "default": 1.0},
                    "epsilon": {"type": "number", "default": 1.0},
                    "mass": {"type": "number", "default": 1.0},
                    "dt": {"type": "number", "default": 0.001},
                    "n_steps": {"type": "integer", "default": 1000},
                },
            },
        },
        "required": ["mode"],
    },
}


def _handler(args):
    mode = args.get("mode")
    params = args.get("params", {}) or {}
    if mode == "simulate":
        return compute_simulate(params)
    elif mode == "validate":
        return compute_validate(params)
    else:
        raise ValueError(f"modo desconocido: {mode}")


tool_registry.register_tool("molecular_dynamics_tool", MOLECULAR_DYNAMICS_TOOL_SCHEMA, _handler)
