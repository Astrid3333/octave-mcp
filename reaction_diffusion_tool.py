#!/usr/bin/env python3
"""
reaction_diffusion_tool.py
Sistemas de reaccion-difusion: Fisher-KPP 1D (frente de avance con velocidad
analitica conocida - modelo directo de colonizacion fungica, avance del frente
de hifas sobre un sustrato), y Gray-Scott 2D (patrones de Turing - manchas,
rayas, laberintos - segun el regimen de parametros feed/kill). Ambos via
integracion explicita con diferencias finitas y condiciones de borde
periodicas/Neumann.
"""
import numpy as np


def compute_fisher_kpp(L=200, nx=400, r=1.0, D=1.0, T=50.0, dt=None,
                        initial_width=10, seed=None):
    """
    du/dt = D*d2u/dx2 + r*u*(1-u). Frente de onda viajera con velocidad
    analitica c = 2*sqrt(r*D) (resultado clasico de Fisher/Kolmogorov 1937) -
    sirve de benchmark de validacion directo contra la simulacion numerica.
    Condicion inicial: pulso localizado en el centro del dominio (colonia
    fungica puntual iniciando su avance).
    """
    dx = L / nx
    if dt is None:
        dt = 0.2 * dx ** 2 / D  # CFL conservador para estabilidad explicita
    n_steps = int(T / dt)
    x = np.linspace(0, L, nx)
    u = np.zeros(nx)
    center = nx // 2
    half_w = int(initial_width / dx)
    u[center - half_w:center + half_w] = 1.0

    front_positions = []
    track_every = max(1, n_steps // 100)
    for step in range(n_steps):
        lap = np.zeros_like(u)
        lap[1:-1] = (u[2:] - 2 * u[1:-1] + u[:-2]) / dx ** 2
        lap[0] = (u[1] - u[0]) / dx ** 2
        lap[-1] = (u[-2] - u[-1]) / dx ** 2
        u = u + dt * (D * lap + r * u * (1 - u))
        u = np.clip(u, 0, 1)
        if step % track_every == 0:
            above = np.where(u > 0.5)[0]
            if len(above) > 0:
                front_positions.append({"t": round(step * dt, 4), "front_x": round(float(x[above[-1]]), 4)})

    analytic_speed = 2 * np.sqrt(r * D)
    measured_speed = None
    if len(front_positions) > 5:
        ts = np.array([p["t"] for p in front_positions[-20:]])
        xs = np.array([p["front_x"] for p in front_positions[-20:]])
        if ts[-1] > ts[0]:
            measured_speed = float((xs[-1] - xs[0]) / (ts[-1] - ts[0]))

    return {
        "mode": "fisher_kpp", "L": L, "nx": nx, "r": r, "D": D, "T": T, "dt": round(dt, 6),
        "analytic_front_speed": round(float(analytic_speed), 6),
        "measured_front_speed": round(measured_speed, 6) if measured_speed is not None else None,
        "front_position_trajectory": front_positions,
        "final_profile_sample": [round(float(v), 6) for v in u[::max(1, nx // 40)]],
        "final_colonized_fraction": round(float((u > 0.5).mean()), 6),
    }


def compute_gray_scott(nx=100, ny=100, Du=0.16, Dv=0.08, feed=0.035, kill=0.065,
                        T=2000, dt=1.0, seed=None, n_snapshots=4):
    """
    Sistema Gray-Scott: du/dt = Du*lap(u) - u*v^2 + feed*(1-u);
    dv/dt = Dv*lap(v) + u*v^2 - (feed+kill)*v. Segun (feed, kill) aparecen
    patrones de Turing (manchas, laberintos, ondas) - regimenes conocidos:
    manchas ~ (0.035, 0.065), laberintos ~ (0.029, 0.057), ondas/caos ~
    (0.026, 0.051). Relevante como sustrato teorico para patrones de
    distribucion espacial en colonias (no solo el frente, sino la textura
    interna) y para el biosensor atmosferico de TritOS si se modela como
    sistema activador-inhibidor.
    """
    rng = np.random.default_rng(seed)
    u = np.ones((ny, nx))
    v = np.zeros((ny, nx))
    cx, cy = nx // 2, ny // 2
    r0 = max(3, nx // 20)
    yy, xx = np.ogrid[:ny, :nx]
    mask = (xx - cx) ** 2 + (yy - cy) ** 2 < r0 ** 2
    u[mask] = 0.50
    v[mask] = 0.25
    u += 0.02 * rng.standard_normal((ny, nx))
    v += 0.02 * rng.standard_normal((ny, nx))

    def laplacian(Z):
        return (
            -4 * Z
            + np.roll(Z, 1, axis=0) + np.roll(Z, -1, axis=0)
            + np.roll(Z, 1, axis=1) + np.roll(Z, -1, axis=1)
        )

    n_steps = int(T / dt)
    snapshot_every = max(1, n_steps // n_snapshots)
    snapshots = []
    for step in range(n_steps):
        Lu, Lv = laplacian(u), laplacian(v)
        uvv = u * v * v
        u += dt * (Du * Lu - uvv + feed * (1 - u))
        v += dt * (Dv * Lv + uvv - (feed + kill) * v)
        if step % snapshot_every == 0:
            snapshots.append({
                "t": round(step * dt, 2),
                "v_mean": round(float(v.mean()), 6),
                "v_std": round(float(v.std()), 6),
                "v_sample": [[round(float(x), 4) for x in row[::max(1, nx // 15)]] for row in v[::max(1, ny // 15)]],
            })

    return {
        "mode": "gray_scott", "nx": nx, "ny": ny, "Du": Du, "Dv": Dv,
        "feed": feed, "kill": kill, "T": T, "dt": dt,
        "n_snapshots": len(snapshots),
        "snapshots": snapshots,
        "final_v_mean": round(float(v.mean()), 6),
        "final_v_std": round(float(v.std()), 6),
        "final_pattern_variance": round(float(v.var()), 6),
    }


def compute_reaction_diffusion(mode, **kwargs):
    """Dispatcher unico para el tool MCP reaction_diffusion, segun 'mode'."""
    fns = {
        "fisher_kpp": compute_fisher_kpp,
        "gray_scott": compute_gray_scott,
    }
    if mode not in fns:
        raise ValueError(f"mode desconocido: {mode}")
    return fns[mode](**kwargs)


REACTION_DIFFUSION_TOOL_SCHEMA = {
    "name": "reaction_diffusion",
    "description": "Sistemas de reaccion-difusion: Fisher-KPP 1D (frente de onda viajera, velocidad analitica c=2*sqrt(r*D) - modelo de colonizacion fungica) y Gray-Scott 2D (patrones de Turing: manchas, laberintos, ondas segun regimen feed/kill).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["fisher_kpp", "gray_scott"]},
            "L": {"type": "number"}, "nx": {"type": "integer"}, "ny": {"type": "integer"},
            "r": {"type": "number"}, "D": {"type": "number"},
            "Du": {"type": "number"}, "Dv": {"type": "number"},
            "feed": {"type": "number"}, "kill": {"type": "number"},
            "T": {"type": "number"}, "dt": {"type": "number"},
            "initial_width": {"type": "number"}, "seed": {"type": "integer"},
            "n_snapshots": {"type": "integer"},
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    r1 = compute_reaction_diffusion(mode="fisher_kpp", L=200, nx=400, r=1.0, D=1.0, T=40.0)
    print({k: v for k, v in r1.items() if k not in ("front_position_trajectory", "final_profile_sample")})
    r2 = compute_reaction_diffusion(mode="gray_scott", nx=60, ny=60, feed=0.035, kill=0.065, T=3000, dt=1.0, seed=42, n_snapshots=3)
    print({k: v for k, v in r2.items() if k != "snapshots"})
    print("v_std por snapshot:", [s["v_std"] for s in r2["snapshots"]])

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("reaction_diffusion", REACTION_DIFFUSION_TOOL_SCHEMA, lambda args, _f=compute_reaction_diffusion: _f(**args))
