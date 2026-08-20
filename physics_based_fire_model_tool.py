import numpy as np


def compute_fire_spread_2d(Lx=200, Ly=200, nx=200, ny=200, D=1.0, r=1.0,
                            wind_speed=0.0, wind_dir_deg=0.0, T=30.0, dt=None,
                            initial_radius=5, seed=None, n_snapshots=30):
    """
    du/dt = D*(u_xx+u_yy) - wind_speed*(cos(theta)*u_x + sin(theta)*u_y) + r*u*(1-u)
    Extension 2D de fisher_kpp con viento vectorial (wind_dir_deg: 0=+x,
    sentido antihorario). Adveccion discretizada con upwind por dimension
    (splitting direccional en x e y por separado), misma logica que
    compute_fisher_kpp 1D. Ignicion: disco circular en el centro del dominio
    (foco puntual de incendio).
    """
    dx = Lx / nx
    dy = Ly / ny
    theta = np.radians(wind_dir_deg)
    vx = wind_speed * np.cos(theta)
    vy = wind_speed * np.sin(theta)

    if dt is None:
        dt_diff = 0.2 * min(dx, dy) ** 2 / D
        dt_adv_x = 0.8 * dx / abs(vx) if vx != 0 else np.inf
        dt_adv_y = 0.8 * dy / abs(vy) if vy != 0 else np.inf
        dt = min(dt_diff, dt_adv_x, dt_adv_y)
    n_steps = int(T / dt)

    x = np.linspace(0, Lx, nx)
    y = np.linspace(0, Ly, ny)
    X, Y = np.meshgrid(x, y, indexing="ij")
    cx, cy = Lx / 2, Ly / 2
    u = ((X - cx) ** 2 + (Y - cy) ** 2 <= initial_radius ** 2).astype(float)

    sample_dirs = [(0, "downwind_axis"), (180, "upwind_axis"),
                   (90, "crosswind_pos"), (270, "crosswind_neg")]
    front_traj = {name: [] for _, name in sample_dirs}
    track_every = max(1, n_steps // n_snapshots)

    def sample_front(u, ang_deg):
        ang = np.radians(ang_deg)
        max_r = min(Lx, Ly) / 2 - max(dx, dy)
        rs = np.arange(0, max_r, min(dx, dy))
        xs = cx + rs * np.cos(ang)
        ys = cy + rs * np.sin(ang)
        ix = np.clip((xs / dx).astype(int), 0, nx - 1)
        iy = np.clip((ys / dy).astype(int), 0, ny - 1)
        vals = u[ix, iy]
        above = np.where(vals > 0.5)[0]
        return float(rs[above[-1]]) if len(above) > 0 else 0.0

    for step in range(n_steps):
        lap = np.zeros_like(u)
        lap[1:-1, :] += (u[2:, :] - 2 * u[1:-1, :] + u[:-2, :]) / dx ** 2
        lap[0, :] += (u[1, :] - u[0, :]) / dx ** 2
        lap[-1, :] += (u[-2, :] - u[-1, :]) / dx ** 2
        lap[:, 1:-1] += (u[:, 2:] - 2 * u[:, 1:-1] + u[:, :-2]) / dy ** 2
        lap[:, 0] += (u[:, 1] - u[:, 0]) / dy ** 2
        lap[:, -1] += (u[:, -2] - u[:, -1]) / dy ** 2

        adv_x = np.zeros_like(u)
        if vx >= 0:
            adv_x[1:, :] = (u[1:, :] - u[:-1, :]) / dx
            adv_x[0, :] = (u[1, :] - u[0, :]) / dx
        else:
            adv_x[:-1, :] = (u[1:, :] - u[:-1, :]) / dx
            adv_x[-1, :] = (u[-1, :] - u[-2, :]) / dx

        adv_y = np.zeros_like(u)
        if vy >= 0:
            adv_y[:, 1:] = (u[:, 1:] - u[:, :-1]) / dy
            adv_y[:, 0] = (u[:, 1] - u[:, 0]) / dy
        else:
            adv_y[:, :-1] = (u[:, 1:] - u[:, :-1]) / dy
            adv_y[:, -1] = (u[:, -1] - u[:, -2]) / dy

        u = u + dt * (D * lap - vx * adv_x - vy * adv_y + r * u * (1 - u))
        u = np.clip(u, 0, 1)

        if step % track_every == 0:
            t = round(step * dt, 4)
            for ang, name in sample_dirs:
                front_traj[name].append({"t": t, "front_r": sample_front(u, ang)})

    def fit_speed(traj):
        if len(traj) < 6:
            return None
        ts = np.array([p["t"] for p in traj[-15:]])
        rs = np.array([p["front_r"] for p in traj[-15:]])
        if ts[-1] <= ts[0]:
            return None
        return float((rs[-1] - rs[0]) / (ts[-1] - ts[0]))

    measured = {name: fit_speed(front_traj[name]) for _, name in sample_dirs}

    return {
        "mode": "spread_2d", "Lx": Lx, "Ly": Ly, "nx": nx, "ny": ny,
        "D": D, "r": r, "wind_speed": wind_speed, "wind_dir_deg": wind_dir_deg,
        "T": T, "dt": round(dt, 6),
        "measured_front_speed": {k: (round(v, 6) if v is not None else None) for k, v in measured.items()},
        "final_burned_fraction": round(float((u > 0.5).mean()), 6),
    }


def _validate():
    # T mas largo que el intento anterior: un frente circular en 2D no viaja
    # a la velocidad asintotica plana desde el arranque -- hay correccion de
    # curvatura dR/dt ~ c_inf - D/R (Fisher-KPP radial), solo despreciable
    # cuando R >> ancho de frente sqrt(D/r)=1. Con T=15 el frente upwind/
    # crosswind (mas lentos) solo llegaban a R~20-27, insuficiente; con
    # T=40 todos superan R~50-100, la correccion D/R cae por debajo de 2%.
    Lx, Ly, nx, ny, T = 260, 260, 520, 520, 40.0
    dx = Lx / nx
    D, r, wind_speed = 1.0, 1.0, 1.0

    res = compute_fire_spread_2d(Lx=Lx, Ly=Ly, nx=nx, ny=ny, D=D, r=r,
                                  wind_speed=wind_speed, wind_dir_deg=0.0, T=T)
    m = res["measured_front_speed"]

    D_eff = D + 0.5 * dx * wind_speed
    # Derivacion: en coordenadas comoviles xi=x-v*t el termino de adveccion
    # se cancela exactamente y el frente es un circulo isotropo puro de
    # radio R(t)=2*sqrt(rD)*t centrado en el punto de ignicion. Al volver a
    # coordenadas fijas ese circulo se traslada rigidamente en x. El eje
    # crosswind mide la interseccion de ese circulo con el eje y, que por
    # Pitagoras da velocidad sqrt(4rD - v^2), NO 2*sqrt(rD) (formula previa
    # incorrecta -- 2*sqrt(rD) es la velocidad radial en el propio circulo,
    # no la velocidad de avance medida sobre el eje y fijo).
    crosswind_speed = (4 * r * D - wind_speed ** 2) ** 0.5
    analytic = {
        "downwind_axis": wind_speed + 2 * (r * D_eff) ** 0.5,
        "upwind_axis": -wind_speed + 2 * (r * D_eff) ** 0.5,
        "crosswind_pos": crosswind_speed,
        "crosswind_neg": crosswind_speed,
    }

    checks = []
    for name, a in analytic.items():
        meas = m[name]
        err = abs(meas - a) / abs(a) if meas is not None else 1.0
        checks.append({
            "name": name, "measured": meas, "analytic": round(a, 6),
            "rel_error": round(err, 6), "passed": bool(err < 0.12),
        })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def physics_based_fire_model(mode="spread_2d", **kwargs):
    if mode == "validate":
        return _validate()
    if mode == "spread_2d":
        return compute_fire_spread_2d(**kwargs)
    raise ValueError(f"mode desconocido: {mode}")


PHYSICS_BASED_FIRE_MODEL_TOOL_SCHEMA = {
    "name": "physics_based_fire_model",
    "description": "Extension 2D del modelo Fisher-KPP con adveccion vectorial de viento (magnitud+angulo): frente de incendio circular con reaccion logistica, difusion isotropa y viento direccional. Complementa forest_fire_simulator_tool (automata celular, sesgo direccional por vecindad 4-conectada) con un campo continuo sin ese sesgo.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["spread_2d", "validate"]},
            "Lx": {"type": "number"}, "Ly": {"type": "number"},
            "nx": {"type": "integer"}, "ny": {"type": "integer"},
            "D": {"type": "number"}, "r": {"type": "number"},
            "wind_speed": {"type": "number"}, "wind_dir_deg": {"type": "number"},
            "T": {"type": "number"}, "dt": {"type": "number"},
            "initial_radius": {"type": "number"}, "seed": {"type": "integer"},
            "n_snapshots": {"type": "integer"},
        },
        "required": [],
    },
}


from tool_registry import register_tool
register_tool("physics_based_fire_model", PHYSICS_BASED_FIRE_MODEL_TOOL_SCHEMA, physics_based_fire_model)
