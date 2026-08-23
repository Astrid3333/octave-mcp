"""
mycelial_network_tool.py

Herramienta MCP para modelado micelial: crecimiento logistico y tres
patrones de dispersion de esporas. Sigue el patron de octave-mcp:
self-registro via tool_registry (adaptar el bloque de registro al
mecanismo real de tu server.py -- ver nota al final del archivo).

Modos:
  - growth_logistic            : dB/dt = r*B*(1-B/K), validado contra
                                  solucion cerrada.
  - spore_ballistic             : eyeccion tipo gota-de-Buller + balistica
                                  con drag de Stokes (lineal), validado
                                  contra solucion cerrada de proyectil
                                  con drag lineal.
  - spore_statistical           : proceso de puntos 2D (poisson /
                                  neg_binomial / levy), estadisticas
                                  espaciales (NN, Clark-Evans).
  - spore_advection_diffusion   : PDE explicita 1D (difusion + adveccion
                                  por viento), validado contra pluma
                                  gaussiana analitica con deriva.
  - validate                    : autochequeo de los 4 modos anteriores.
"""

import numpy as np
from scipy.integrate import solve_ivp
from scipy.stats import poisson as _poisson, nbinom as _nbinom, levy_stable

MODES = [
    "growth_logistic",
    "spore_ballistic",
    "spore_statistical",
    "spore_advection_diffusion",
    "validate",
]


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def compute_mycelial_network(mode="growth_logistic", **kwargs):
    if mode == "validate":
        return _validate_mycelial_network()
    if mode == "growth_logistic":
        return _growth_logistic(**kwargs)
    if mode == "spore_ballistic":
        return _spore_ballistic(**kwargs)
    if mode == "spore_statistical":
        return _spore_statistical(**kwargs)
    if mode == "spore_advection_diffusion":
        return _spore_advection_diffusion(**kwargs)
    raise ValueError(
        f"mode desconocido: {mode!r}. Modos validos: {MODES}"
    )


# --------------------------------------------------------------------------
# 1. Crecimiento logistico
# --------------------------------------------------------------------------

def _growth_logistic(r=0.5, K=10.0, B0=0.1, t_max=20.0, n_points=200):
    """
    dB/dt = r*B*(1 - B/K)

    Solucion cerrada:
      B(t) = K / (1 + ((K - B0)/B0) * exp(-r*t))
    """
    t_eval = np.linspace(0.0, t_max, n_points)

    def rhs(t, B):
        return [r * B[0] * (1.0 - B[0] / K)]

    sol = solve_ivp(rhs, (0.0, t_max), [B0], t_eval=t_eval, method="RK45",
                     rtol=1e-9, atol=1e-12)

    B_analytic = K / (1.0 + ((K - B0) / B0) * np.exp(-r * t_eval))

    return {
        "mode": "growth_logistic",
        "t": t_eval.tolist(),
        "biomass": sol.y[0].tolist(),
        "biomass_analytic": B_analytic.tolist(),
        "max_abs_error": float(np.max(np.abs(sol.y[0] - B_analytic))),
        "params": {"r": r, "K": K, "B0": B0, "t_max": t_max},
    }


def _growth_logistic_closed_form(r, K, B0, t):
    return K / (1.0 + ((K - B0) / B0) * np.exp(-r * t))


# --------------------------------------------------------------------------
# 2. Eyeccion balistica (gota de Buller + drag de Stokes)
# --------------------------------------------------------------------------

def _buller_ejection_velocity(drop_radius_um=1.0, spore_mass_kg=None,
                               surface_tension=0.0728):
    """
    Energia liberada por el colapso de la gota de Buller (coalescencia con
    el hilar apendix) se convierte en energia cinetica de la espora.

    E_superficial ~ surface_tension * 4*pi*r_drop^2  (orden de magnitud del
    area de la gota que colapsa)
    v0 = sqrt(2*E / m_espora)

    Esto es una aproximacion de orden de magnitud (el mecanismo real
    involucra la geometria exacta del apendix hilar), suficiente para
    fijar un v0 realista (~1-2 m/s, consistente con mediciones de
    alta velocidad de Pringle et al.).
    """
    r_drop = drop_radius_um * 1e-6
    if spore_mass_kg is None:
        # espora tipica ~ 5 um radio, densidad ~1100 kg/m3
        r_spore = 5e-6
        density = 1100.0
        spore_mass_kg = density * (4.0 / 3.0) * np.pi * r_spore ** 3
    E = surface_tension * 4.0 * np.pi * r_drop ** 2
    v0 = np.sqrt(2.0 * E / spore_mass_kg)
    return float(v0), float(spore_mass_kg)


def _spore_ballistic(drop_radius_um=1.0, launch_angle_deg=30.0,
                      spore_mass_kg=None, stokes_b=None, t_max=0.01,
                      n_points=200, g=9.81):
    """
    Balistica 2D con drag lineal (Stokes, bajo numero de Reynolds):
      dvx/dt = -(b/m)*vx
      dvy/dt = -g - (b/m)*vy

    Solucion cerrada (drag lineal):
      vx(t) = vx0 * exp(-k t)
      x(t)  = (vx0/k) * (1 - exp(-k t))
      vy(t) = (vy0 + g/k)*exp(-k t) - g/k
      y(t)  = (vy0 + g/k)/k * (1 - exp(-k t)) - (g/k) t

    donde k = b/m.
    """
    v0, m = _buller_ejection_velocity(drop_radius_um, spore_mass_kg)
    theta = np.radians(launch_angle_deg)
    vx0 = v0 * np.cos(theta)
    vy0 = v0 * np.sin(theta)

    if stokes_b is None:
        # coeficiente de Stokes b = 6*pi*mu*r, mu_aire ~ 1.81e-5 Pa.s
        r_spore = 5e-6
        mu_air = 1.81e-5
        stokes_b = 6.0 * np.pi * mu_air * r_spore
    k = stokes_b / m

    t_eval = np.linspace(0.0, t_max, n_points)

    def rhs(t, state):
        vx, vy = state[2], state[3]
        return [vx, vy, -k * vx, -g - k * vy]

    sol = solve_ivp(rhs, (0.0, t_max), [0.0, 0.0, vx0, vy0],
                     t_eval=t_eval, method="RK45", rtol=1e-10, atol=1e-14)

    x_analytic = (vx0 / k) * (1.0 - np.exp(-k * t_eval))
    y_analytic = ((vy0 + g / k) / k) * (1.0 - np.exp(-k * t_eval)) - (g / k) * t_eval

    # alcance = primer cruce y=0 hacia abajo (despues del despegue)
    y_num = sol.y[1]
    landing_idx = None
    for i in range(1, len(y_num)):
        if y_num[i] <= 0.0 and y_num[i - 1] > 0.0:
            landing_idx = i
            break

    return {
        "mode": "spore_ballistic",
        "t": t_eval.tolist(),
        "x": sol.y[0].tolist(),
        "y": sol.y[1].tolist(),
        "x_analytic": x_analytic.tolist(),
        "y_analytic": y_analytic.tolist(),
        "max_abs_error_x": float(np.max(np.abs(sol.y[0] - x_analytic))),
        "max_abs_error_y": float(np.max(np.abs(sol.y[1] - y_analytic))),
        "v0_ms": v0,
        "spore_mass_kg": m,
        "stokes_b": stokes_b,
        "range_estimate_m": float(sol.y[0][landing_idx]) if landing_idx else None,
        "params": {"drop_radius_um": drop_radius_um,
                    "launch_angle_deg": launch_angle_deg, "t_max": t_max},
    }


# --------------------------------------------------------------------------
# 3. Distribucion espacial estadistica
# --------------------------------------------------------------------------

def _spore_statistical(distribution="poisson", n_spores=500,
                        area_size_m=10.0, cluster_r=None, levy_alpha=1.5,
                        seed=42):
    """
    Genera posiciones 2D de esporas segun el proceso elegido y calcula
    estadisticas de dispersion espacial:
      - distancia media al vecino mas cercano (NN)
      - indice de Clark-Evans R = NN_observado / NN_esperado_CSR
        (R ~ 1 => aleatorio, R < 1 => agregado/cluster, R > 1 => disperso)
    """
    rng = np.random.default_rng(seed)

    if distribution == "poisson":
        x = rng.uniform(0, area_size_m, n_spores)
        y = rng.uniform(0, area_size_m, n_spores)

    elif distribution == "neg_binomial":
        # clustering: primero centros "padre" via Poisson disperso,
        # luego hijos alrededor de cada centro (proceso tipo Neyman-Scott,
        # aproximado con neg_binomial para el conteo por cluster)
        r = cluster_r or (area_size_m * 0.05)
        n_parents = max(1, n_spores // 10)
        parents_x = rng.uniform(0, area_size_m, n_parents)
        parents_y = rng.uniform(0, area_size_m, n_parents)
        counts = _nbinom.rvs(5, 0.5, size=n_parents, random_state=rng)
        counts = np.maximum(counts, 1)
        counts = (counts / counts.sum() * n_spores).astype(int)
        x_list, y_list = [], []
        for px, py, c in zip(parents_x, parents_y, counts):
            ang = rng.uniform(0, 2 * np.pi, c)
            rad = rng.rayleigh(r, c)
            x_list.append(px + rad * np.cos(ang))
            y_list.append(py + rad * np.sin(ang))
        x = np.clip(np.concatenate(x_list), 0, area_size_m)
        y = np.clip(np.concatenate(y_list), 0, area_size_m)

    elif distribution == "levy":
        # Levy flight 2D desde un origen central: pasos con cola pesada
        # (dispersion a larga distancia por viento), angulo uniforme
        x0, y0 = area_size_m / 2.0, area_size_m / 2.0
        steps_raw = np.abs(levy_stable.rvs(levy_alpha, 0, size=n_spores,
                                            random_state=rng))
        steps = np.clip(steps_raw, 0, area_size_m * 3)  # cota fisica razonable
        ang = rng.uniform(0, 2 * np.pi, n_spores)
        x = x0 + steps * np.cos(ang)
        y = y0 + steps * np.sin(ang)

    else:
        raise ValueError(
            f"distribution desconocida: {distribution!r}. "
            "Usar 'poisson', 'neg_binomial' o 'levy'."
        )

    pts = np.column_stack([x, y])
    # NN observado (fuerza bruta, n_spores <= ~2000 esto es suficiente)
    nn_dists = []
    for i in range(len(pts)):
        d = np.linalg.norm(pts - pts[i], axis=1)
        d[i] = np.inf
        nn_dists.append(d.min())
    nn_mean = float(np.mean(nn_dists))

    density = n_spores / (area_size_m ** 2)
    nn_expected_csr = 1.0 / (2.0 * np.sqrt(density))
    clark_evans_R = nn_mean / nn_expected_csr

    result = {
        "mode": "spore_statistical",
        "distribution": distribution,
        "x": x.tolist(),
        "y": y.tolist(),
        "nn_mean_distance_m": nn_mean,
        "nn_expected_csr_m": nn_expected_csr,
        "clark_evans_R": clark_evans_R,
        "interpretation": (
            "agregado/cluster" if clark_evans_R < 0.9 else
            "disperso/regular" if clark_evans_R > 1.1 else
            "aleatorio (CSR)"
        ),
        "params": {"n_spores": n_spores, "area_size_m": area_size_m,
                    "seed": seed},
    }

    if distribution == "levy":
        tail_index_est = _hill_tail_index(steps_raw)
        result["step_lengths"] = steps_raw.tolist()
        result["levy_alpha_input"] = float(levy_alpha)
        result["estimated_tail_index"] = tail_index_est

    return result


def _hill_tail_index(data, frac=0.15):
    """
    Estimador de Hill para el indice de cola de una distribucion de cola
    pesada: dado un array de valores positivos, usa la fraccion superior
    (order statistics mas grandes) para estimar el exponente de la cola.

    Para una variable estable de Levy con parametro alpha, la cola de
    |X| decae como x^-(alpha+1), y el estimador de Hill sobre |X|
    recupera ese alpha (no exactamente el parametro de estabilidad
    completo de la distribucion simetrica, pero captura el mismo orden
    de magnitud del exponente de cola -- suficiente para un chequeo de
    consistencia, no una prueba estadistica formal).
    """
    data_sorted = np.sort(np.asarray(data))
    n = len(data_sorted)
    k = max(10, int(frac * n))
    top = data_sorted[-k:]
    x_k = data_sorted[-k - 1] if n > k else data_sorted[0]
    if x_k <= 0:
        x_k = np.min(top[top > 0]) * 0.5 if np.any(top > 0) else 1e-12
    logs = np.log(top / x_k)
    logs = logs[np.isfinite(logs) & (logs > 0)]
    if len(logs) == 0:
        return None
    xi_hat = np.mean(logs)
    if xi_hat <= 0:
        return None
    return float(1.0 / xi_hat)


# --------------------------------------------------------------------------
# 4. Pluma de adveccion-difusion
# --------------------------------------------------------------------------

def _spore_advection_diffusion(D=0.05, v_wind=0.3, source_mass=1.0,
                                x_max=20.0, nx=400, t_snapshot=10.0,
                                dt=None):
    """
    dC/dt = D * d2C/dx2 - v_wind * dC/dx

    Diferencias finitas explicitas 1D (mismo esqueleto que
    reaction_diffusion_tool con termino de adveccion), condicion inicial
    pulso delta aproximado en x=0.

    Solucion analitica (pluma gaussiana con deriva, fuente puntual
    instantanea en x=0, t=0):
      C(x,t) = M / sqrt(4*pi*D*t) * exp( -(x - v*t)^2 / (4*D*t) )
    """
    dx = x_max / nx
    x = np.linspace(-x_max / 2.0, x_max / 2.0, nx)

    if dt is None:
        # condicion de estabilidad CFL para difusion+adveccion explicita
        dt_diff = 0.4 * dx ** 2 / D
        dt_adv = 0.8 * dx / abs(v_wind) if v_wind != 0 else np.inf
        dt = min(dt_diff, dt_adv)

    n_steps = int(t_snapshot / dt)

    # pulso inicial: gaussiana angosta centrada en x=0 aproximando delta,
    # arrancamos la integracion en t0 pequeno para evitar la singularidad
    # t=0 de la solucion analitica
    t0 = 5.0 * dt
    C = (source_mass / np.sqrt(4.0 * np.pi * D * t0)) * \
        np.exp(-(x - v_wind * t0) ** 2 / (4.0 * D * t0))

    t = t0
    for _ in range(n_steps):
        C_pad = np.pad(C, 1, mode="constant", constant_values=0.0)
        d2C = (C_pad[2:] - 2 * C_pad[1:-1] + C_pad[:-2]) / dx ** 2
        dCdx = (C_pad[2:] - C_pad[:-2]) / (2.0 * dx)  # centrada
        C = C + dt * (D * d2C - v_wind * dCdx)
        t += dt

    C_analytic = (source_mass / np.sqrt(4.0 * np.pi * D * t)) * \
        np.exp(-(x - v_wind * t) ** 2 / (4.0 * D * t))

    return {
        "mode": "spore_advection_diffusion",
        "x": x.tolist(),
        "concentration": C.tolist(),
        "concentration_analytic": C_analytic.tolist(),
        "t_final": float(t),
        "max_abs_error": float(np.max(np.abs(C - C_analytic))),
        "peak_location_m": float(x[np.argmax(C)]),
        "params": {"D": D, "v_wind": v_wind, "source_mass": source_mass,
                    "x_max": x_max, "nx": nx, "t_snapshot": t_snapshot},
    }


# --------------------------------------------------------------------------
# 5. Validate
# --------------------------------------------------------------------------

def _validate_mycelial_network():
    checks = []
    all_passed = True

    # -- growth_logistic --
    r, K, B0, t_max = 0.5, 10.0, 0.1, 20.0
    out = _growth_logistic(r=r, K=K, B0=B0, t_max=t_max, n_points=200)
    tol = 1e-6
    passed = out["max_abs_error"] < tol
    all_passed &= passed
    checks.append({
        "name": "growth_logistic_vs_closed_form",
        "passed": bool(passed),
        "max_abs_error": out["max_abs_error"],
        "tolerance": tol,
    })

    # -- spore_ballistic --
    out = _spore_ballistic(drop_radius_um=1.0, launch_angle_deg=30.0,
                            t_max=0.01, n_points=200)
    tol_x = 1e-9
    tol_y = 1e-9
    passed = (out["max_abs_error_x"] < tol_x and
              out["max_abs_error_y"] < tol_y)
    all_passed &= passed
    checks.append({
        "name": "spore_ballistic_vs_linear_drag_closed_form",
        "passed": bool(passed),
        "max_abs_error_x": out["max_abs_error_x"],
        "max_abs_error_y": out["max_abs_error_y"],
    })

    # -- spore_statistical: CSR debe dar R cerca de 1, cluster debe dar R<1 --
    out_csr = _spore_statistical(distribution="poisson", n_spores=800,
                                  area_size_m=10.0, seed=1)
    out_cluster = _spore_statistical(distribution="neg_binomial",
                                      n_spores=800, area_size_m=10.0, seed=1)
    csr_ok = 0.85 < out_csr["clark_evans_R"] < 1.15
    cluster_ok = out_cluster["clark_evans_R"] < out_csr["clark_evans_R"]
    passed = csr_ok and cluster_ok
    all_passed &= passed
    checks.append({
        "name": "spore_statistical_csr_vs_cluster_ordering",
        "passed": bool(passed),
        "clark_evans_R_poisson": out_csr["clark_evans_R"],
        "clark_evans_R_cluster": out_cluster["clark_evans_R"],
    })

    # -- spore_statistical: Levy tail index (Hill estimator) vs input alpha --
    # n_spores grande para reducir varianza de muestreo del estimador
    levy_alpha_input = 1.5
    out_levy = _spore_statistical(distribution="levy", n_spores=5000,
                                   area_size_m=10.0, levy_alpha=levy_alpha_input,
                                   seed=7)
    tail_est = out_levy["estimated_tail_index"]
    rel_tol = 0.4  # estimador de Hill tiene varianza alta a n finito
    passed = (tail_est is not None and
              abs(tail_est - levy_alpha_input) / levy_alpha_input < rel_tol)
    all_passed &= passed
    checks.append({
        "name": "spore_statistical_levy_tail_index_vs_input_alpha",
        "passed": bool(passed),
        "levy_alpha_input": levy_alpha_input,
        "estimated_tail_index": tail_est,
        "relative_tolerance": rel_tol,
    })

    # -- spore_advection_diffusion --
    out = _spore_advection_diffusion(D=0.05, v_wind=0.3, source_mass=1.0,
                                      x_max=20.0, nx=400, t_snapshot=10.0)
    tol = 5e-3  # diferencias finitas explicitas, tolerancia mas laxa
    passed = out["max_abs_error"] < tol
    all_passed &= passed
    checks.append({
        "name": "spore_advection_diffusion_vs_gaussian_plume",
        "passed": bool(passed),
        "max_abs_error": out["max_abs_error"],
        "tolerance": tol,
    })

    return {
        "mode": "validate",
        "validation_passed": bool(all_passed),
        "checks": checks,
    }


# --------------------------------------------------------------------------
# NOTA DE INTEGRACION (adaptar a tu server.py real):
#
# 1. Registro de schema: agregar "mycelial_network" con
#    mode enum = MODES (incluyendo "validate") -- esto es lo que
#    run_all_validations.py detecta automaticamente via
#    mode_to_call="validate" por default, sin necesitar tocar
#    ALTERNATE_VALIDATE_MODE / ALTERNATE_VALIDATE_PARAM_NAME /
#    FLAT_SIGNATURE_TOOLS.
#
# 2. Dispatch: sumar el elif tool_name=="mycelial_network" en el
#    bloque de despacho de server.py, siguiendo el mismo patron
#    (result=compute_mycelial_network(**args), resp={...}).
#
# 3. Si mycelial_network termina viviendo junto a un submotor Rust
#    (candidato: spore_statistical con muchos agentes, o el paso de
#    NN fuerza-bruta si area/n_spores crece -- ahi mismo patron que
#    fem_poisson2d: subprocess + JSON), dejar el wrapper Python tal
#    cual y solo reemplazar el cuerpo de _spore_statistical con la
#    llamada al binario.
# --------------------------------------------------------------------------
