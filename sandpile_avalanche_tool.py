"""
sandpile_avalanche_tool.py

Modelo de Bak-Tang-Wiesenfeld (BTW, 1987) -- el "monton de arena" clasico
de criticalidad autoorganizada (SOC). Grilla NxN de alturas enteras;
frontera abierta (los granos que caen del borde se pierden del sistema,
no hay reflejo). Regla de colapso ("toppling"): si h[i,j] >= 4 (umbral
= numero de vecinos en 2D), la celda pierde 4 granos y reparte 1 a cada
vecino ortogonal (los vecinos fuera de la grilla se pierden). Se agrega
un grano de a uno en un sitio (por default el centro, patron clasico) y
se deja que el sistema colapse hasta estabilizar antes de agregar el
siguiente; el numero de colapsos disparados por un solo grano agregado
es el "tamano de la avalancha" de ese evento.

Resultado central de SOC: sin ajustar ningun parametro externo, el
sistema evoluciona solo hacia un estado critico donde el tamano de las
avalanchas sigue una ley de potencia P(s) ~ s^-tau (sin escala
caracteristica), y la altura promedio converge a un valor fijo conocido
(~2.125 para la grilla infinita, Dhar 1990, resultado exacto via
algebra de grupo abeliano).

Modos:
  - run_avalanches: corre n_grains adiciones de granos, devuelve la
    serie de tamanos/duraciones/areas de avalancha y la altura promedio
    final.
  - power_law_fit: corre avalanchas y ajusta P(s) ~ s^-tau via regresion
    lineal en log-log sobre bins logaritmicos (sin depender de
    scipy.stats.powerlaw), reporta tau, R^2 del ajuste, y rango de s
    usado.
  - validate: chequeos contra el comportamiento fisico conocido del
    modelo (ver _validate para el detalle de cada uno).
"""

import numpy as np


def _run_btw(grid_size=20, n_grains=4000, seed=42, drop_site="center",
             warmup_grains=0):
    """Corre el modelo BTW y devuelve la serie de avalanchas + grilla final.

    drop_site: "center" (patron clasico, drenaje simetrico hacia los 4
    bordes) o "random" (grano cae en sitio uniforme al azar cada vez).
    warmup_grains: adiciones descartadas de la serie de resultados (para
    dejar que el sistema alcance el estado critico antes de medir), pero
    SI se aplican a la grilla.
    """
    rng = np.random.default_rng(seed)
    grid = np.zeros((grid_size, grid_size), dtype=np.int64)
    center = (grid_size // 2, grid_size // 2)

    avalanche_sizes = []
    avalanche_durations = []
    avalanche_areas = []

    total_grains_added = warmup_grains + n_grains

    for step in range(total_grains_added):
        if drop_site == "center":
            i, j = center
        else:
            i = rng.integers(0, grid_size)
            j = rng.integers(0, grid_size)
        grid[i, j] += 1

        # Relajacion: colapso simultaneo de todos los sitios criticos por
        # "oleada" (mas fiel al proceso fisico -- y mas rapido -- que
        # colapsar de a un sitio con una pila).
        n_topples = 0
        toppled_sites = set()
        duration = 0
        while True:
            critical = grid >= 4
            if not critical.any():
                break
            duration += 1
            n_topple_this_wave = int(critical.sum())
            n_topples += n_topple_this_wave

            # cuantas veces colapsa cada sitio critico en esta oleada
            # (siempre 1, porque justo despues de colapsar baja de 4;
            # pero un sitio puede volver a ser critico en la oleada
            # siguiente si recibe granos de vecinos)
            overflow = np.where(critical, 4, 0)
            grid -= overflow

            # repartir 1 grano a cada vecino ortogonal de cada sitio que
            # colapso esta oleada; vecinos fuera de la grilla se pierden
            idx_i, idx_j = np.where(critical)
            toppled_sites.update(zip(idx_i.tolist(), idx_j.tolist()))
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ni = idx_i + di
                nj = idx_j + dj
                valid = (ni >= 0) & (ni < grid_size) & (nj >= 0) & (nj < grid_size)
                np.add.at(grid, (ni[valid], nj[valid]), 1)

        if step >= warmup_grains:
            avalanche_sizes.append(n_topples)
            avalanche_durations.append(duration)
            avalanche_areas.append(len(toppled_sites))

    return {
        "grid": grid,
        "avalanche_sizes": avalanche_sizes,
        "avalanche_durations": avalanche_durations,
        "avalanche_areas": avalanche_areas,
    }


def _mode_run_avalanches(params):
    grid_size = int(params.get("grid_size", 20))
    n_grains = int(params.get("n_grains", 4000))
    seed = int(params.get("seed", 42))
    drop_site = params.get("drop_site", "center")
    warmup_grains = int(params.get("warmup_grains", 2000))

    result = _run_btw(grid_size=grid_size, n_grains=n_grains, seed=seed,
                       drop_site=drop_site, warmup_grains=warmup_grains)

    sizes = np.array(result["avalanche_sizes"])
    grid = result["grid"]

    return {
        "mode": "run_avalanches",
        "grid_size": grid_size,
        "n_grains_measured": n_grains,
        "warmup_grains": warmup_grains,
        "avalanche_sizes": result["avalanche_sizes"],
        "avalanche_durations": result["avalanche_durations"],
        "avalanche_areas": result["avalanche_areas"],
        "mean_avalanche_size": float(np.mean(sizes)) if len(sizes) else 0.0,
        "max_avalanche_size": int(np.max(sizes)) if len(sizes) else 0,
        "mean_height_final": float(np.mean(grid)),
        "fraction_zero_avalanches": float(np.mean(sizes == 0)) if len(sizes) else None,
        "note": (
            "mean_height_final deberia acercarse a ~2.125 (resultado exacto "
            "de Dhar 1990 para la grilla infinita) a medida que grid_size y "
            "n_grains crecen; con grillas chicas y pocos granos hay sesgo "
            "de tamano finito hacia abajo."
        ),
    }


def _power_law_fit(sizes, min_size=1):
    """Ajuste log-log simple por bins logaritmicos (evita el sesgo de
    contar linealmente colas donde hay pocos eventos grandes). Devuelve
    pendiente (tau), intercepto, y R^2 del ajuste lineal en log-log.
    """
    sizes = np.asarray(sizes)
    sizes = sizes[sizes >= min_size]
    if len(sizes) < 10:
        return {"tau": None, "r_squared": None, "n_events": len(sizes),
                "error": "muy pocos eventos para ajustar"}

    s_min, s_max = sizes.min(), sizes.max()
    if s_max <= s_min:
        return {"tau": None, "r_squared": None, "n_events": len(sizes),
                "error": "rango de tamanos degenerado"}

    n_bins = max(8, min(25, int(np.log2(s_max / max(s_min, 1)) * 3)))
    bin_edges = np.unique(np.geomspace(s_min, s_max + 1, n_bins))
    if len(bin_edges) < 4:
        return {"tau": None, "r_squared": None, "n_events": len(sizes),
                "error": "muy pocos bins distintos"}

    counts, edges = np.histogram(sizes, bins=bin_edges)
    bin_widths = np.diff(edges)
    bin_centers = np.sqrt(edges[:-1] * edges[1:])  # centro geometrico

    # densidad de probabilidad normalizada por ancho de bin (estandar
    # para histogramas log-binned de leyes de potencia)
    density = counts / bin_widths / len(sizes)

    valid = density > 0
    if valid.sum() < 4:
        return {"tau": None, "r_squared": None, "n_events": len(sizes),
                "error": "muy pocos bins con densidad > 0"}

    x = np.log10(bin_centers[valid])
    y = np.log10(density[valid])

    # regresion lineal simple
    A = np.vstack([x, np.ones_like(x)]).T
    slope, intercept = np.linalg.lstsq(A, y, rcond=None)[0]
    y_pred = A @ np.array([slope, intercept])
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return {
        "tau": float(-slope),  # P(s) ~ s^-tau, pendiente log-log es -tau
        "intercept": float(intercept),
        "r_squared": float(r_squared),
        "n_events": int(len(sizes)),
        "n_bins_used": int(valid.sum()),
        "size_range": [float(s_min), float(s_max)],
    }


def _mode_power_law_fit(params):
    grid_size = int(params.get("grid_size", 24))
    n_grains = int(params.get("n_grains", 6000))
    seed = int(params.get("seed", 42))
    drop_site = params.get("drop_site", "center")
    warmup_grains = int(params.get("warmup_grains", 3000))
    min_size = int(params.get("min_size", 1))

    result = _run_btw(grid_size=grid_size, n_grains=n_grains, seed=seed,
                       drop_site=drop_site, warmup_grains=warmup_grains)

    fit = _power_law_fit(result["avalanche_sizes"], min_size=min_size)

    return {
        "mode": "power_law_fit",
        "grid_size": grid_size,
        "n_grains_measured": n_grains,
        "fit": fit,
        "note": (
            "tau tipico reportado en la literatura para el modelo BTW 2D "
            "esta en el rango ~0.9-1.2 para el exponente de tamano (Bak, "
            "Tang & Wiesenfeld 1987; valores exactos dependen fuertemente "
            "de la definicion de 'tamano' -- topples vs area vs duracion "
            "-- y de efectos de tamano finito de la grilla). Este ajuste "
            "usa topples totales."
        ),
    }


def _validate():
    checks = {}
    errors = []

    # 1) Sin granos agregados, ninguna avalancha posible (grilla vacia).
    r0 = _run_btw(grid_size=10, n_grains=1, seed=1, warmup_grains=0)
    checks["empty_grid_first_grain_no_avalanche"] = (r0["avalanche_sizes"][0] == 0)
    if r0["avalanche_sizes"][0] != 0:
        errors.append("primer grano en grilla vacia disparo una avalancha (no deberia)")

    # 2) Conservacion de masa: granos que quedan en la grilla + granos
    #    perdidos por el borde == granos agregados. Medimos perdida por
    #    borde contando la diferencia entre lo agregado y lo que quedo.
    grid_size = 12
    n_grains = 500
    r1 = _run_btw(grid_size=grid_size, n_grains=n_grains, seed=7, warmup_grains=0)
    grains_remaining = int(r1["grid"].sum())
    grains_added = n_grains
    # los granos perdidos son necesariamente >= 0 y grains_remaining <= grains_added
    mass_conserved_or_lost_at_boundary = (0 <= grains_remaining <= grains_added)
    checks["mass_conserved_or_lost_at_boundary"] = bool(mass_conserved_or_lost_at_boundary)
    checks["grains_remaining_value"] = grains_remaining
    checks["grains_added_value"] = grains_added
    if not mass_conserved_or_lost_at_boundary:
        errors.append(
            f"conservacion de masa violada: quedaron {grains_remaining} "
            f"granos habiendo agregado solo {grains_added}"
        )

    # 3) Todas las celdas quedan por debajo del umbral tras estabilizar
    #    (ninguna corrida deberia terminar con un sitio critico sin
    #    colapsar -- bug de logica de relajacion).
    all_below_threshold = bool((r1["grid"] < 4).all())
    checks["all_cells_below_threshold_after_relaxation"] = all_below_threshold
    if not all_below_threshold:
        errors.append("quedaron celdas con h>=4 tras la relajacion (bug de toppling)")

    # 4) Un solo grano sobre una grilla ya cerca del umbral SI puede
    #    disparar una avalancha grande (sensibilidad -- lo opuesto del
    #    check 1: el mismo tipo de evento microscopico, resultado
    #    macroscopico distinto segun el estado del sistema).
    grid_size2 = 16
    r2 = _run_btw(grid_size=grid_size2, n_grains=3000, seed=3, warmup_grains=1500)
    sizes2 = np.array(r2["avalanche_sizes"])
    has_large_avalanche = bool((sizes2 > 10).any())
    checks["large_avalanches_occur_after_warmup"] = has_large_avalanche
    checks["max_avalanche_size_value"] = int(sizes2.max()) if len(sizes2) else 0
    if not has_large_avalanche:
        errors.append("no aparecio ninguna avalancha grande (>10 topples) tras warmup -- sistema no llego a criticalidad")

    # 5) La distribucion de tamanos de avalancha tiene cola pesada: la
    #    mayoria de eventos son chicos (tamano 0 o 1) pero hay una cola
    #    de eventos grandes -- el sello de SOC, a diferencia de una
    #    distribucion con escala caracteristica (ej. Poisson/exponencial)
    #    donde los eventos grandes serian extremadamente raros.
    frac_small = float(np.mean(sizes2 <= 1))
    frac_large = float(np.mean(sizes2 > 20))
    heavy_tail_present = (frac_small > 0.3) and (frac_large > 0.0)
    checks["heavy_tail_distribution"] = bool(heavy_tail_present)
    checks["fraction_trivial_avalanches"] = frac_small
    checks["fraction_large_avalanches"] = frac_large
    if not heavy_tail_present:
        errors.append("la distribucion no muestra el patron esperado de cola pesada (muchos eventos triviales + algunos grandes)")

    # 6) Ajuste de ley de potencia: pendiente negativa razonable (tau
    #    positivo, no un valor absurdo como tau=20 o tau negativo) y
    #    R^2 del ajuste log-log no trivialmente malo.
    fit = _power_law_fit(r2["avalanche_sizes"], min_size=1)
    tau = fit.get("tau")
    r2_fit = fit.get("r_squared")
    tau_reasonable = (tau is not None) and (0.3 <= tau <= 3.0)
    fit_not_terrible = (r2_fit is not None) and (r2_fit > 0.5)
    checks["power_law_tau_in_plausible_range"] = bool(tau_reasonable)
    checks["power_law_tau_value"] = tau
    checks["power_law_fit_r_squared"] = r2_fit
    checks["power_law_fit_not_terrible"] = bool(fit_not_terrible)
    if not tau_reasonable:
        errors.append(f"tau del ajuste de ley de potencia fuera de rango plausible: {tau}")
    if not fit_not_terrible:
        errors.append(f"ajuste log-log de mala calidad: R^2={r2_fit}")

    # 7) Altura promedio converge hacia el rango fisico conocido
    #    (Dhar 1990: ~2.125 para grilla infinita; con grilla finita y
    #    n_grains moderado se espera un valor cercano pero no exacto --
    #    toleramos un rango amplio [1.5, 3.0] para no sobreajustar a
    #    efectos de tamano finito).
    mean_height = float(np.mean(r2["grid"]))
    height_in_range = 1.5 <= mean_height <= 3.0
    checks["mean_height_near_theoretical_soc_value"] = bool(height_in_range)
    checks["mean_height_value"] = mean_height
    if not height_in_range:
        errors.append(f"altura promedio {mean_height:.3f} fuera del rango esperado [1.5, 3.0] cerca de SOC")

    # 8) Determinismo: misma seed -> mismo resultado exacto.
    r3a = _run_btw(grid_size=10, n_grains=200, seed=99, warmup_grains=0)
    r3b = _run_btw(grid_size=10, n_grains=200, seed=99, warmup_grains=0)
    reproducible = (r3a["avalanche_sizes"] == r3b["avalanche_sizes"])
    checks["reproducible_with_same_seed"] = bool(reproducible)
    if not reproducible:
        errors.append("misma seed dio resultados distintos (deberia ser determinista)")

    return {
        "mode": "validate",
        "validation_passed": len(errors) == 0,
        "checks": checks,
        "errors": errors,
    }


def compute_sandpile_avalanche_tool(mode, params=None):
    params = params or {}
    if mode == "run_avalanches":
        return _mode_run_avalanches(params)
    elif mode == "power_law_fit":
        return _mode_power_law_fit(params)
    elif mode == "validate":
        return _validate()
    else:
        return {
            "error": (
                f"Modo desconocido: {mode}. Modos validos: run_avalanches, "
                "power_law_fit, validate."
            )
        }


SANDPILE_AVALANCHE_TOOL_SCHEMA = {
    "name": "sandpile_avalanche_tool",
    "description": (
        "Modelo de Bak-Tang-Wiesenfeld (monton de arena, 1987): grilla NxN "
        "con frontera abierta, colapso ('toppling') cuando una celda "
        "alcanza el umbral de 4 granos, reparto a los 4 vecinos "
        "ortogonales. Ejemplo clasico de criticalidad autoorganizada (SOC) "
        "-- el sistema evoluciona solo, sin ajustar ningun parametro "
        "externo, hacia un estado donde el tamano de las avalanchas sigue "
        "una ley de potencia (sin escala caracteristica) en vez de una "
        "distribucion con escala tipica. mode=run_avalanches corre "
        "n_grains adiciones y devuelve la serie de tamanos/duraciones de "
        "avalancha. mode=power_law_fit corre la simulacion y ajusta "
        "P(s)~s^-tau por regresion log-log sobre bins logaritmicos."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["run_avalanches", "power_law_fit", "validate"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "grid_size": {"type": "integer", "description": "Lado de la grilla NxN (default 20 en run_avalanches, 24 en power_law_fit)"},
                    "n_grains": {"type": "integer", "description": "Granos agregados y medidos (default 4000/6000 segun modo)"},
                    "warmup_grains": {"type": "integer", "description": "Granos agregados antes de empezar a medir, para alcanzar el estado critico (default 2000/3000 segun modo)"},
                    "drop_site": {"type": "string", "enum": ["center", "random"], "description": "Donde cae cada grano (default center, patron clasico)"},
                    "seed": {"type": "integer", "description": "Semilla RNG, solo usada si drop_site=random (default 42)"},
                    "min_size": {"type": "integer", "description": "Tamano minimo de avalancha incluido en el ajuste de ley de potencia (default 1)"},
                },
            },
        },
        "required": ["mode"],
    },
}

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool(
    "sandpile_avalanche_tool",
    SANDPILE_AVALANCHE_TOOL_SCHEMA,
    lambda args, _f=compute_sandpile_avalanche_tool: _f(**args),
)
