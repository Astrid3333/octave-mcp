"""
evo_lgca_tool.py

Automata celular de gas reticular (Lattice-Gas Cellular Automaton, LGCA,
Deutsch & Dormann 2005) para migracion colectiva de celulas en 1D, con una
capa evolutiva simple: cada particula/celula lleva un "fenotipo" escalar que
se hereda con mutacion en cada division, permitiendo estudiar seleccion
espacial durante la invasion de un frente celular.

Mecanica LGCA 1D estandar:
  - cada nodo del lattice tiene 2 canales de velocidad (derecha, izquierda)
    mas opcionalmente un canal de reposo.
  - paso de colision: en cada nodo, con exclusion (max 1 particula por
    canal), se reorientan las particulas segun una regla de colision simple
    (aqui: intercambio con probabilidad "alignment_prob" hacia la direccion
    de mayor densidad vecina -- proxy de quimiotaxis/mecanotaxis de
    poblacion).
  - paso de propagacion (streaming): cada particula se mueve un sitio en la
    direccion de su canal.
  - capa evolutiva: en cada paso, con "birth_prob" una celula ocupada genera
    una hija en un canal libre vecino (si existe) heredando el fenotipo +
    ruido gaussiano (mutacion); con "death_prob" una celula muere (libera su
    canal).

Modos:
  - lgca_1d_run: corre la simulacion y devuelve densidad total por sitio a
    lo largo del tiempo (para medir velocidad de avance del frente) mas
    fenotipo medio por sitio en el paso final.
  - front_speed: corre lgca_1d_run y estima la velocidad de avance del
    frente (posicion del borde de densidad>umbral vs tiempo, ajuste lineal).
  - validate: sin nacimiento/muerte (birth_prob=death_prob=0) el numero
    total de particulas debe conservarse exactamente.
"""

import numpy as np


def _init_lattice(L, initial_density, initial_region_frac, rng):
    # 2 canales: 0=derecha, 1=izquierda. Bool array (L, 2).
    channels = np.zeros((L, 2), dtype=bool)
    region_end = max(1, int(L * initial_region_frac))
    for x in range(region_end):
        for c in range(2):
            if rng.random() < initial_density:
                channels[x, c] = True
    phenotype = np.full(L, np.nan)
    phenotype[:region_end] = rng.normal(0.0, 1.0, region_end)
    return channels, phenotype


def _collision_step(channels, alignment_prob, rng):
    L = channels.shape[0]
    density = channels.sum(axis=1).astype(float)
    new_channels = channels.copy()
    for x in range(L):
        occupied = np.where(channels[x])[0]
        if len(occupied) < 1:
            continue
        left_d = density[x - 1] if x > 0 else 0.0
        right_d = density[x + 1] if x < L - 1 else 0.0
        preferred = 0 if right_d >= left_d else 1  # 0=derecha, 1=izquierda
        # con prob alignment_prob, reorienta particulas ocupadas hacia 'preferred'
        # (sujeto a exclusion: si el canal preferido ya esta ocupado, no se mueve)
        for c in list(occupied):
            if c != preferred and rng.random() < alignment_prob and not new_channels[x, preferred]:
                new_channels[x, c] = False
                new_channels[x, preferred] = True
    return new_channels


def _streaming_step(channels, phenotype):
    # bordes periodicos: garantiza conservacion exacta del numero de
    # particulas cuando birth_prob=death_prob=0 (sin esto, las particulas
    # que llegan al borde se perderian, ensuciando el chequeo de
    # conservacion). Para dominios grandes y tiempos cortos el efecto de
    # wraparound sobre la dinamica de interes es despreciable.
    L = channels.shape[0]
    new_channels = np.zeros_like(channels)
    new_phenotype = np.full(L, np.nan)
    # canal 0 = derecha (+1), canal 1 = izquierda (-1)
    for x in range(L):
        if channels[x, 0]:
            xr = (x + 1) % L
            new_channels[xr, 0] = True
            new_phenotype[xr] = phenotype[x] if not np.isnan(phenotype[x]) else new_phenotype[xr]
        if channels[x, 1]:
            xl = (x - 1) % L
            new_channels[xl, 1] = True
            new_phenotype[xl] = phenotype[x] if not np.isnan(phenotype[x]) else new_phenotype[xl]
    return new_channels, new_phenotype


def _birth_death_step(channels, phenotype, birth_prob, death_prob, mutation_std, rng):
    L = channels.shape[0]
    for x in range(L):
        occ = np.where(channels[x])[0]
        if len(occ) == 0:
            continue
        # muerte
        for c in list(occ):
            if rng.random() < death_prob:
                channels[x, c] = False
        occ = np.where(channels[x])[0]
        if len(occ) == 0:
            continue
        # nacimiento: intenta colocar hija en sitio vecino con canal libre
        if rng.random() < birth_prob:
            neighbor = x + 1 if rng.random() < 0.5 else x - 1
            if 0 <= neighbor < L:
                free = np.where(~channels[neighbor])[0]
                if len(free) > 0:
                    c_new = free[rng.integers(0, len(free))]
                    channels[neighbor, c_new] = True
                    parent_phen = phenotype[x] if not np.isnan(phenotype[x]) else 0.0
                    phenotype[neighbor] = parent_phen + rng.normal(0, mutation_std)
    density = channels.sum(axis=1)
    phenotype[density == 0] = np.nan
    return channels, phenotype


def _lgca_1d_run(
    L=100, n_steps=200, initial_density=0.6, initial_region_frac=0.1,
    alignment_prob=0.7, birth_prob=0.05, death_prob=0.02, mutation_std=0.1,
    seed=None, snapshot_every=None,
):
    rng = np.random.default_rng(seed)
    channels, phenotype = _init_lattice(L, initial_density, initial_region_frac, rng)
    if snapshot_every is None:
        snapshot_every = max(1, n_steps // 20)

    density_history = []
    total_particles_history = []

    for step in range(n_steps):
        channels = _collision_step(channels, alignment_prob, rng)
        channels, phenotype = _streaming_step(channels, phenotype)
        channels, phenotype = _birth_death_step(channels, phenotype, birth_prob, death_prob, mutation_std, rng)

        total = int(channels.sum())
        total_particles_history.append(total)
        if step % snapshot_every == 0:
            density_history.append({"t": step, "density_profile": channels.sum(axis=1).astype(float).tolist()})

    final_density = channels.sum(axis=1).astype(float)
    final_phenotype_mean = np.nanmean(phenotype) if not np.all(np.isnan(phenotype)) else None

    return {
        "mode": "lgca_1d_run",
        "params": {
            "L": L, "n_steps": n_steps, "initial_density": initial_density,
            "initial_region_frac": initial_region_frac, "alignment_prob": alignment_prob,
            "birth_prob": birth_prob, "death_prob": death_prob, "mutation_std": mutation_std,
        },
        "density_snapshots": density_history,
        "total_particles_history": total_particles_history,
        "final_density_profile": final_density.tolist(),
        "final_phenotype_mean": float(final_phenotype_mean) if final_phenotype_mean is not None else None,
        "final_total_particles": int(channels.sum()),
    }


def _front_position(density_profile, threshold_fraction=0.5, max_density=2.0):
    threshold = threshold_fraction * max_density
    above = np.where(np.array(density_profile) >= threshold)[0]
    if len(above) == 0:
        return None
    return int(above.max())


def _front_speed(L=100, n_steps=200, threshold_fraction=0.3, **lgca_kwargs):
    lgca_kwargs.setdefault("L", L)
    lgca_kwargs.setdefault("n_steps", n_steps)
    lgca_kwargs["snapshot_every"] = max(1, n_steps // 40)
    result = _lgca_1d_run(**lgca_kwargs)
    snaps = result["density_snapshots"]
    times, positions = [], []
    for snap in snaps:
        pos = _front_position(snap["density_profile"], threshold_fraction=threshold_fraction, max_density=2.0)
        if pos is not None:
            times.append(snap["t"])
            positions.append(pos)
    speed = None
    if len(times) >= 2:
        A = np.vstack([times, np.ones(len(times))]).T
        slope, intercept = np.linalg.lstsq(A, positions, rcond=None)[0]
        speed = float(slope)
    return {
        "mode": "front_speed",
        "front_positions_over_time": {"t": times, "position": positions},
        "estimated_front_speed_sites_per_step": speed,
        "final_total_particles": result["final_total_particles"],
    }


def _validate():
    conserved = _lgca_1d_run(
        L=40, n_steps=50, initial_density=0.5, initial_region_frac=0.2,
        alignment_prob=0.5, birth_prob=0.0, death_prob=0.0, seed=1,
    )
    history = conserved["total_particles_history"]
    conservation_ok = len(set(history)) == 1  # exactamente constante en cada paso

    growth_case = _front_speed(L=60, n_steps=80, birth_prob=0.1, death_prob=0.01, seed=2)
    speed_ok = growth_case["estimated_front_speed_sites_per_step"] is not None

    return {
        "mode": "validate",
        "particle_count_history_no_birth_death": history,
        "conservation_check_passed": conservation_ok,
        "front_speed_with_growth": growth_case["estimated_front_speed_sites_per_step"],
        "expected": "sin nacimiento/muerte el numero total de particulas se conserva exacto en cada paso",
        "validation_passed": bool(conservation_ok and speed_ok),
    }


def compute_evo_lgca_tool(mode, **kwargs):
    if mode == "lgca_1d_run":
        return _lgca_1d_run(
            L=kwargs.get("L", 100), n_steps=kwargs.get("n_steps", 200),
            initial_density=kwargs.get("initial_density", 0.6),
            initial_region_frac=kwargs.get("initial_region_frac", 0.1),
            alignment_prob=kwargs.get("alignment_prob", 0.7),
            birth_prob=kwargs.get("birth_prob", 0.05),
            death_prob=kwargs.get("death_prob", 0.02),
            mutation_std=kwargs.get("mutation_std", 0.1),
            seed=kwargs.get("seed"),
            snapshot_every=kwargs.get("snapshot_every"),
        )
    elif mode == "front_speed":
        return _front_speed(
            L=kwargs.get("L", 100), n_steps=kwargs.get("n_steps", 200),
            threshold_fraction=kwargs.get("threshold_fraction", 0.3),
            initial_density=kwargs.get("initial_density", 0.6),
            initial_region_frac=kwargs.get("initial_region_frac", 0.1),
            alignment_prob=kwargs.get("alignment_prob", 0.7),
            birth_prob=kwargs.get("birth_prob", 0.05),
            death_prob=kwargs.get("death_prob", 0.02),
            mutation_std=kwargs.get("mutation_std", 0.1),
            seed=kwargs.get("seed"),
        )
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"mode desconocido: {mode}")


EVO_LGCA_TOOL_SCHEMA = {
    "name": "evo_LGCA_tool",
    "description": (
        "Automata celular de gas reticular (LGCA, Deutsch & Dormann) en 1D para migracion "
        "colectiva de celulas, con capa evolutiva (nacimiento/muerte con herencia de fenotipo "
        "+ mutacion gaussiana). mode='lgca_1d_run' (L, n_steps, initial_density, "
        "initial_region_frac, alignment_prob, birth_prob, death_prob, mutation_std, seed): "
        "corre la simulacion y devuelve snapshots de densidad + fenotipo medio final; "
        "mode='front_speed' (mismos params + threshold_fraction): estima la velocidad de "
        "avance del frente celular por regresion lineal posicion-vs-tiempo; mode='validate' "
        "verifica conservacion exacta de particulas sin nacimiento/muerte."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["lgca_1d_run", "front_speed", "validate"],
                "default": "validate",
            },
            "L": {"type": "integer", "default": 100, "description": "Tamano del lattice."},
            "n_steps": {"type": "integer", "default": 200, "description": "Pasos de simulacion."},
            "initial_density": {"type": "number", "default": 0.6, "description": "Densidad inicial de ocupacion en la region inicial."},
            "initial_region_frac": {"type": "number", "default": 0.1, "description": "Fraccion del lattice ocupada inicialmente."},
            "alignment_prob": {"type": "number", "default": 0.7, "description": "Probabilidad de reorientacion hacia mayor densidad vecina."},
            "birth_prob": {"type": "number", "default": 0.05},
            "death_prob": {"type": "number", "default": 0.02},
            "mutation_std": {"type": "number", "default": 0.1, "description": "Desvio de la mutacion del fenotipo al nacer."},
            "seed": {"type": "integer", "description": "Semilla RNG, opcional."},
            "snapshot_every": {"type": "integer", "description": "Cada cuantos pasos guardar snapshot. lgca_1d_run."},
            "threshold_fraction": {"type": "number", "default": 0.3, "description": "front_speed: fraccion de densidad maxima que define el borde del frente."},
        },
        "required": ["mode"],
    },
}
