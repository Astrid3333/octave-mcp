"""
particle_simulation_tool.py
Simulacion de particulas: gravitacion, colisiones, difusion estocastica.

Modos:
  - kepler_orbit           : problema de dos cuerpos, orbita circular, RK4 adaptativo
  - elastic_collision_nbody: colisiones elasticas 1D en cadena de N particulas
  - random_walk_diffusion  : caminata aleatoria / MSD, recupera coeficiente de difusion D

Validado contra:
  - T = 2*pi*sqrt(a^3/(G*M))                       (tercera ley de Kepler)
  - conservacion exacta de momento y energia        (colision elastica 1D, formula libro de texto)
  - MSD(t) = 2*D*t  (difusion 1D)                   (regresion lineal recupera D)
"""
import numpy as np
from scipy.integrate import solve_ivp

PARTICLE_SIMULATION_TOOL_SCHEMA = {
    "name": "particle_simulation_tool",
    "description": (
        "Simulacion de particulas: orbita de Kepler de dos cuerpos (kepler_orbit), "
        "colisiones elasticas en cadena 1D (elastic_collision_nbody), caminata "
        "aleatoria y recuperacion de coeficiente de difusion (random_walk_diffusion)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["kepler_orbit", "elastic_collision_nbody", "random_walk_diffusion"]},
            "params": {"type": "object", "description": "Parametros especificos de cada modo, ver docstrings."},
        },
        "required": ["mode"],
    },
}


def _kepler_orbit(G=1.0, M=1.0, a=1.0, n_periods=2):
    T_analytic = 2*np.pi*np.sqrt(a**3/(G*M))
    v0 = np.sqrt(G*M/a)

    def ode(t, s):
        x, y, vx, vy = s
        r = np.hypot(x, y)
        return [vx, vy, -G*M*x/r**3, -G*M*y/r**3]

    sol = solve_ivp(ode, [0, n_periods*T_analytic], [a, 0, 0, v0], max_step=0.001)
    x, y = sol.y[0], sol.y[1]
    theta = np.unwrap(np.arctan2(y, x))
    T_numeric = float(2*np.pi / ((theta[-1]-theta[0])/(sol.t[-1]-sol.t[0])))
    return {
        "mode": "kepler_orbit",
        "period_analytic_s": T_analytic,
        "period_numeric_s": T_numeric,
        "relative_error_pct": 100*abs(T_numeric-T_analytic)/T_analytic,
        "time": sol.t.tolist()[::100],
        "x": x.tolist()[::100],
        "y": y.tolist()[::100],
    }


def _elastic_collision_nbody(masses, velocities):
    m = list(masses)
    v = list(velocities)
    n = len(m)
    p0 = sum(mi*vi for mi, vi in zip(m, v))
    e0 = sum(0.5*mi*vi**2 for mi, vi in zip(m, v))
    history = [list(v)]
    for i in range(n-1):
        m1, m2 = m[i], m[i+1]
        u1, u2 = v[i], v[i+1]
        v1 = ((m1-m2)*u1 + 2*m2*u2)/(m1+m2)
        v2 = ((m2-m1)*u2 + 2*m1*u1)/(m1+m2)
        v[i], v[i+1] = v1, v2
        history.append(list(v))
    p1 = sum(mi*vi for mi, vi in zip(m, v))
    e1 = sum(0.5*mi*vi**2 for mi, vi in zip(m, v))
    return {
        "mode": "elastic_collision_nbody",
        "final_velocities": v,
        "momentum_before": p0, "momentum_after": p1,
        "momentum_drift": p1-p0,
        "energy_before": e0, "energy_after": e1,
        "energy_drift": e1-e0,
        "history": history,
    }


def _random_walk_diffusion(n_particles=2000, n_steps=2000, dt=0.01, D_true=0.5, seed=0):
    rng = np.random.default_rng(seed)
    sigma = np.sqrt(2*D_true*dt)
    steps = rng.normal(0, sigma, size=(n_particles, n_steps))
    pos = np.cumsum(steps, axis=1)
    t = np.arange(1, n_steps+1)*dt
    msd = np.mean(pos**2, axis=0)
    D_fit = float(np.sum(t*msd) / np.sum(t*t) / 2)
    return {
        "mode": "random_walk_diffusion",
        "D_true": D_true,
        "D_fit": D_fit,
        "relative_error_pct": 100*abs(D_fit-D_true)/D_true,
        "time": t.tolist()[::50],
        "msd": msd.tolist()[::50],
    }


def compute_particle_simulation(mode, params=None):
    params = params or {}
    if mode == "kepler_orbit":
        return _kepler_orbit(**params)
    elif mode == "elastic_collision_nbody":
        return _elastic_collision_nbody(**params)
    elif mode == "random_walk_diffusion":
        return _random_walk_diffusion(**params)
    else:
        raise ValueError(f"modo desconocido: {mode}. Use kepler_orbit | elastic_collision_nbody | random_walk_diffusion")


if __name__ == "__main__":
    r1 = compute_particle_simulation("kepler_orbit", {})
    print("kepler_orbit err%% =", r1["relative_error_pct"])
    r2 = compute_particle_simulation("elastic_collision_nbody", {"masses": [2.0, 3.0], "velocities": [5.0, -2.0]})
    print("collision momentum drift =", r2["momentum_drift"], "energy drift =", r2["energy_drift"])
    r3 = compute_particle_simulation("random_walk_diffusion", {})
    print("diffusion err%% =", r3["relative_error_pct"])
