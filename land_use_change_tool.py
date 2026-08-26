"""
land_use_change_tool.py

Modelo de cambio de uso de suelo (LULC - Land Use/Land Cover Change) via
cadena de Markov de transicion entre categorias de cobertura, mas un
modelo de fragmentacion de habitat (percolacion en grilla + deteccion de
componentes conexas) para distinguir perdida de habitat de fragmentacion
propiamente dicha (la misma area perdida puede repartirse en fragmentos
muy distintos segun el patron espacial).

Modelo de transicion (mode=transition_model):
    estado(t+1) = estado(t) . P
donde P es la matriz de transicion (fila=estado actual, columna=estado
siguiente, cada fila suma 1) entre 4 categorias: bosque, agricultura,
urbano, agua. La matriz default es ilustrativa (no calibrada contra un
dataset regional real, ver nota en DEFAULT_TRANSITION_MATRIX) pero
internamente consistente: urbano y agua se modelan como absorbentes
(en la escala de tiempo de este modelo no vuelven a bosque/agricultura),
bosque y agricultura son transitorios. Con esa estructura la cadena es
una cadena de Markov absorbente clasica: se resuelve en forma cerrada
via la matriz fundamental N=(I-Q)^-1 (Q=submatriz transitorio-a-transitorio)
para obtener la matriz de probabilidad de absorcion B=N.R, y se compara
contra la proyeccion numerica iterando P muchos pasos -- mismo patron de
verificacion cerrado-vs-numerico que unified_dark_sector_tool.

Modelo de fragmentacion (mode=fragmentation):
    genera una grilla NxN de habitat/no-habitat con perdida de habitat
    aleatoria (probabilidad habitat_loss_prob por celda, patron tipo
    percolacion de sitio), detecta componentes conexas (4-conectividad,
    flood-fill iterativo con pila, sin dependencia de scipy) y calcula
    metricas de fragmentacion: numero de parches, largest patch index
    (LPI, fraccion del paisaje total), fraccion del parche mas grande
    respecto al habitat remanente (la metrica que realmente distingue
    fragmentacion de mera perdida de area), densidad de borde y densidad
    de parches.

Modos:
  - transition_model: proyecta las proporciones de uso de suelo a
    n_steps (anios) usando la cadena de Markov, y devuelve ademas la
    prediccion analitica de la distribucion de largo plazo (cadena
    absorbente).
  - fragmentation: genera una grilla sintetica y calcula metricas de
    fragmentacion del habitat.
  - validate: autochequeo interno matematico (8 chequeos).
"""

import numpy as np

STATES = ["forest", "agriculture", "urban", "water"]

# Matriz de transicion anual default (ilustrativa -- NO calibrada contra
# datos reales de una region especifica, pensada solo para demostrar el
# modelo; fila=estado actual, cada fila suma 1). Urbano y agua se
# modelan como absorbentes en la escala de tiempo de este modelo.
DEFAULT_TRANSITION_MATRIX = [
    [0.985, 0.010, 0.004, 0.001],  # forest
    [0.005, 0.960, 0.030, 0.005],  # agriculture
    [0.000, 0.000, 1.000, 0.000],  # urban (absorbente)
    [0.000, 0.000, 0.000, 1.000],  # water (absorbente)
]

DEFAULT_INITIAL_PROPORTIONS = {
    "forest": 0.50, "agriculture": 0.30, "urban": 0.15, "water": 0.05
}

# Por default, urbano (idx 2) y agua (idx 3) son los estados absorbentes
# para el analisis cerrado de cadena absorbente.
DEFAULT_ABSORBING_IDX = [2, 3]


def _normalize_initial(initial_dict):
    vec = np.array([initial_dict.get(s, 0.0) for s in STATES], dtype=float)
    total = vec.sum()
    if total <= 0:
        raise ValueError("Las proporciones iniciales no pueden sumar 0.")
    return vec / total


def _iterate_transition(P, initial_vec, n_steps):
    """Proyecta la distribucion de estados n_steps veces. Devuelve la
    trayectoria completa (incluyendo el paso 0) como lista de vectores."""
    trajectory = [initial_vec.copy()]
    state = initial_vec.copy()
    for _ in range(n_steps):
        state = state @ P
        trajectory.append(state.copy())
    return trajectory


def _absorption_matrix(P, transient_idx, absorbing_idx):
    """Matriz fundamental N=(I-Q)^-1 y matriz de probabilidad de
    absorcion B=N.R de una cadena de Markov absorbente."""
    Q = P[np.ix_(transient_idx, transient_idx)]
    R = P[np.ix_(transient_idx, absorbing_idx)]
    I = np.eye(len(transient_idx))
    N = np.linalg.inv(I - Q)
    B = N @ R
    return N, B


def _predicted_longrun_distribution(P, initial_vec, transient_idx, absorbing_idx):
    """Distribucion de largo plazo predicha en forma cerrada (cadena
    absorbente): toda la masa transitoria termina absorbida, repartida
    segun B; los estados absorbentes retienen su masa inicial mas lo que
    absorben."""
    _, B = _absorption_matrix(P, transient_idx, absorbing_idx)
    initial_transient = initial_vec[transient_idx]
    absorbed_mass = initial_transient @ B  # una entrada por estado absorbente

    predicted = np.zeros(len(STATES))
    for k, idx in enumerate(absorbing_idx):
        predicted[idx] = initial_vec[idx] + absorbed_mass[k]
    for idx in transient_idx:
        predicted[idx] = 0.0
    return predicted


def _mode_transition_model(params):
    P = np.array(params.get("transition_matrix", DEFAULT_TRANSITION_MATRIX), dtype=float)
    initial_dict = params.get("initial_proportions", DEFAULT_INITIAL_PROPORTIONS)
    initial_vec = _normalize_initial(initial_dict)
    n_steps = int(params.get("n_steps", 50))
    absorbing_idx = list(params.get("absorbing_states_idx", DEFAULT_ABSORBING_IDX))
    transient_idx = [i for i in range(len(STATES)) if i not in absorbing_idx]

    trajectory = _iterate_transition(P, initial_vec, n_steps)
    final_state = trajectory[-1]

    predicted_longrun = _predicted_longrun_distribution(
        P, initial_vec, transient_idx, absorbing_idx
    )

    return {
        "mode": "transition_model",
        "states": STATES,
        "n_steps": n_steps,
        "initial_proportions": dict(zip(STATES, initial_vec.tolist())),
        "final_proportions": dict(zip(STATES, final_state.tolist())),
        "trajectory": [dict(zip(STATES, s.tolist())) for s in trajectory],
        "predicted_longrun_distribution": dict(zip(STATES, predicted_longrun.tolist())),
        "absorbing_states": [STATES[i] for i in absorbing_idx],
        "transient_states": [STATES[i] for i in transient_idx],
        "note": (
            "predicted_longrun_distribution es la solucion cerrada de cadena "
            "de Markov absorbente (matriz fundamental), independiente de "
            "n_steps; final_proportions es la proyeccion numerica a n_steps "
            "anios. Si n_steps es grande, ambas deberian converger."
        ),
    }


def _label_connected_components(grid):
    """Etiquetado de componentes conexas (4-conectividad) via flood-fill
    iterativo con pila (sin dependencia de scipy). Devuelve (labels,
    n_components); solo se etiquetan celdas de habitat (valor 1)."""
    n, m = grid.shape
    labels = np.zeros_like(grid, dtype=int)
    current_label = 0
    for i in range(n):
        for j in range(m):
            if grid[i, j] == 1 and labels[i, j] == 0:
                current_label += 1
                stack = [(i, j)]
                labels[i, j] = current_label
                while stack:
                    ci, cj = stack.pop()
                    for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ni, nj = ci + di, cj + dj
                        if (0 <= ni < n and 0 <= nj < m
                                and grid[ni, nj] == 1 and labels[ni, nj] == 0):
                            labels[ni, nj] = current_label
                            stack.append((ni, nj))
    return labels, current_label


def _edge_density(grid):
    """Fraccion de pares de celdas adyacentes (4-conectividad) que cruzan
    el borde habitat/no-habitat, sobre el total de pares adyacentes."""
    horiz_diff = grid[:, :-1] != grid[:, 1:]
    vert_diff = grid[:-1, :] != grid[1:, :]
    total_edges = horiz_diff.size + vert_diff.size
    if total_edges == 0:
        return 0.0
    boundary_edges = int(horiz_diff.sum() + vert_diff.sum())
    return boundary_edges / total_edges


def _run_fragmentation(grid_size, habitat_loss_prob, seed):
    rng = np.random.default_rng(seed)
    grid = (rng.random((grid_size, grid_size)) >= habitat_loss_prob).astype(int)

    labels, n_patches = _label_connected_components(grid)
    total_cells = grid_size * grid_size
    total_habitat_cells = int(grid.sum())

    if n_patches > 0:
        patch_sizes = np.bincount(labels.ravel())[1:]  # excluye label 0 (no-habitat)
        largest_patch_size = int(patch_sizes.max())
        mean_patch_size = float(patch_sizes.mean())
    else:
        largest_patch_size = 0
        mean_patch_size = 0.0

    lpi_of_landscape = largest_patch_size / total_cells
    lpi_of_remaining_habitat = (
        largest_patch_size / total_habitat_cells if total_habitat_cells > 0 else 0.0
    )
    patch_density = n_patches / total_cells
    edge_density = _edge_density(grid)

    return {
        "grid_size": grid_size,
        "habitat_loss_prob": habitat_loss_prob,
        "seed": seed,
        "total_habitat_fraction": total_habitat_cells / total_cells,
        "n_patches": n_patches,
        "largest_patch_size_cells": largest_patch_size,
        "mean_patch_size_cells": mean_patch_size,
        "largest_patch_index_of_landscape": lpi_of_landscape,
        "largest_patch_fraction_of_remaining_habitat": lpi_of_remaining_habitat,
        "patch_density": patch_density,
        "edge_density": edge_density,
    }


def _mode_fragmentation(params):
    grid_size = int(params.get("grid_size", 60))
    habitat_loss_prob = float(params.get("habitat_loss_prob", 0.3))
    seed = int(params.get("seed", 42))

    result = _run_fragmentation(grid_size, habitat_loss_prob, seed)
    result["mode"] = "fragmentation"
    result["note"] = (
        "largest_patch_fraction_of_remaining_habitat es la metrica que "
        "distingue fragmentacion de mera perdida de habitat: dos escenarios "
        "con la misma habitat_loss_prob pueden repartir la perdida en un "
        "solo parche compacto o en muchos parches chicos segun el patron "
        "espacial; aca el patron es percolacion de sitio (perdida aleatoria "
        "independiente por celda), asi que a mayor habitat_loss_prob, mas "
        "fragmentado (no solo mas chico)."
    )
    return result


def _validate():
    """Autochequeo interno matematico (no placeholder). Devuelve
    {"mode": "validate", "passed": bool, "checks": {...}, "errors": [...]}."""
    checks = {}
    errors = []

    P = np.array(DEFAULT_TRANSITION_MATRIX, dtype=float)
    absorbing_idx = DEFAULT_ABSORBING_IDX
    transient_idx = [i for i in range(len(STATES)) if i not in absorbing_idx]
    initial_vec = _normalize_initial(DEFAULT_INITIAL_PROPORTIONS)

    # 1) cada fila de la matriz de transicion default suma 1 (matriz
    #    estocastica valida)
    row_sums = P.sum(axis=1)
    checks["transition_matrix_rows_sum_to_1"] = bool(np.allclose(row_sums, 1.0))
    if not checks["transition_matrix_rows_sum_to_1"]:
        errors.append(f"Filas de la matriz de transicion no suman 1: {row_sums}")

    # 2) la proyeccion conserva probabilidad total en cada paso
    trajectory = _iterate_transition(P, initial_vec, n_steps=50)
    sums = [float(np.sum(s)) for s in trajectory]
    checks["trajectory_conserves_probability"] = bool(
        all(abs(s - 1.0) < 1e-9 for s in sums)
    )
    if not checks["trajectory_conserves_probability"]:
        errors.append(f"La suma de proporciones no se mantuvo en 1 en algun paso: {sums}")

    # 3) en el largo plazo (muchos pasos), la masa en estados transitorios
    #    (bosque, agricultura) tiende a 0
    longrun_trajectory = _iterate_transition(P, initial_vec, n_steps=3000)
    longrun_state = longrun_trajectory[-1]
    transient_mass_longrun = float(sum(longrun_state[i] for i in transient_idx))
    checks["transient_mass_vanishes_longrun"] = bool(transient_mass_longrun < 1e-9)
    checks["transient_mass_longrun_value"] = transient_mass_longrun
    if not checks["transient_mass_vanishes_longrun"]:
        errors.append(
            f"Masa transitoria no convergio a ~0 tras 3000 pasos: {transient_mass_longrun}"
        )

    # 4) verificacion cerrado-vs-numerico: la distribucion de largo plazo
    #    analitica (matriz fundamental) debe coincidir con la proyeccion
    #    numerica de 3000 pasos
    predicted_longrun = _predicted_longrun_distribution(
        P, initial_vec, transient_idx, absorbing_idx
    )
    max_diff = float(np.max(np.abs(predicted_longrun - longrun_state)))
    checks["closed_form_matches_numeric_longrun"] = bool(max_diff < 1e-6)
    checks["closed_form_vs_numeric_max_diff"] = max_diff
    if not checks["closed_form_matches_numeric_longrun"]:
        errors.append(
            f"La prediccion cerrada (matriz fundamental) no coincide con la "
            f"proyeccion numerica de largo plazo (diff max={max_diff})"
        )

    # 5) fragmentacion: a mayor habitat_loss_prob, el parche mas grande
    #    ocupa una fraccion MENOR del habitat remanente (no solo del
    #    paisaje total) -- esa es la firma real de fragmentacion, no solo
    #    de perdida de area
    frag_low = _run_fragmentation(grid_size=60, habitat_loss_prob=0.10, seed=7)
    frag_high = _run_fragmentation(grid_size=60, habitat_loss_prob=0.70, seed=7)
    checks["fragmentation_increases_with_habitat_loss"] = bool(
        frag_high["largest_patch_fraction_of_remaining_habitat"]
        < frag_low["largest_patch_fraction_of_remaining_habitat"]
    )
    if not checks["fragmentation_increases_with_habitat_loss"]:
        errors.append(
            "El parche mas grande no se fragmenta mas (relativo al habitat "
            "remanente) al aumentar habitat_loss_prob"
        )

    # 6) reproducibilidad con la misma semilla
    frag_a = _run_fragmentation(grid_size=40, habitat_loss_prob=0.3, seed=123)
    frag_b = _run_fragmentation(grid_size=40, habitat_loss_prob=0.3, seed=123)
    checks["fragmentation_reproducible_with_same_seed"] = bool(
        frag_a["n_patches"] == frag_b["n_patches"]
        and frag_a["largest_patch_size_cells"] == frag_b["largest_patch_size_cells"]
    )
    if not checks["fragmentation_reproducible_with_same_seed"]:
        errors.append("Dos corridas de fragmentacion con la misma semilla difieren")

    # 7) caso limite: sin perdida de habitat, toda la grilla es un unico
    #    parche y no hay borde interno
    frag_zero_loss = _run_fragmentation(grid_size=20, habitat_loss_prob=0.0, seed=1)
    checks["zero_loss_gives_single_patch"] = bool(frag_zero_loss["n_patches"] == 1)
    checks["zero_loss_gives_zero_edge_density"] = bool(
        frag_zero_loss["edge_density"] == 0.0
    )
    if not checks["zero_loss_gives_single_patch"]:
        errors.append(
            f"habitat_loss_prob=0 no dio un unico parche: "
            f"{frag_zero_loss['n_patches']} parches"
        )
    if not checks["zero_loss_gives_zero_edge_density"]:
        errors.append("habitat_loss_prob=0 no dio edge_density=0")

    # 8) modo desconocido devuelve {"error": ...} sin lanzar excepcion
    try:
        unknown_result = compute_land_use_change_tool(mode="no_existe", params={})
        checks["unknown_mode_returns_error_dict"] = bool(
            isinstance(unknown_result, dict) and "error" in unknown_result
        )
        if not checks["unknown_mode_returns_error_dict"]:
            errors.append(
                f"Modo desconocido no devolvio un dict con 'error': {unknown_result}"
            )
    except Exception as e:
        checks["unknown_mode_returns_error_dict"] = False
        errors.append(f"Modo desconocido lanzo excepcion en vez de devolver error: {e}")

    return {
        "mode": "validate",
        "validation_passed": len(errors) == 0,
        "checks": checks,
        "errors": errors,
    }


def compute_land_use_change_tool(mode, params=None):
    params = params or {}
    if mode == "transition_model":
        return _mode_transition_model(params)
    elif mode == "fragmentation":
        return _mode_fragmentation(params)
    elif mode == "validate":
        return _validate()
    else:
        return {
            "error": (
                f"Modo desconocido: {mode}. Modos validos: transition_model, "
                "fragmentation, validate."
            )
        }


LAND_USE_CHANGE_TOOL_SCHEMA = {
    "name": "land_use_change_tool",
    "description": (
        "Modelo de cambio de uso de suelo: mode=transition_model proyecta "
        "proporciones de cobertura (bosque/agricultura/urbano/agua) via "
        "cadena de Markov, con verificacion cerrado-vs-numerico contra la "
        "solucion analitica de cadena absorbente (matriz fundamental). "
        "mode=fragmentation genera una grilla sintetica de perdida de "
        "habitat (percolacion de sitio) y calcula metricas de "
        "fragmentacion (numero de parches, largest patch index, densidad "
        "de borde) via deteccion de componentes conexas, distinguiendo "
        "fragmentacion de mera perdida de area."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["transition_model", "fragmentation", "validate"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "transition_matrix": {
                        "type": "array",
                        "description": "Matriz 4x4 de transicion (filas suman 1), orden [forest, agriculture, urban, water]. Default: matriz ilustrativa interna.",
                    },
                    "initial_proportions": {
                        "type": "object",
                        "description": "Proporciones iniciales por categoria (se normalizan a 1). Default: forest 0.50, agriculture 0.30, urban 0.15, water 0.05.",
                    },
                    "n_steps": {"type": "integer", "description": "Anios a proyectar en transition_model (default 50)"},
                    "absorbing_states_idx": {
                        "type": "array",
                        "description": "Indices de estados absorbentes para el analisis cerrado (default [2, 3] = urban, water)",
                    },
                    "grid_size": {"type": "integer", "description": "Lado de la grilla NxN en fragmentation (default 60)"},
                    "habitat_loss_prob": {"type": "number", "description": "Probabilidad de perdida de habitat por celda en fragmentation (default 0.3)"},
                    "seed": {"type": "integer", "description": "Semilla RNG (default 42)"},
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
    "land_use_change_tool",
    LAND_USE_CHANGE_TOOL_SCHEMA,
    lambda args, _f=compute_land_use_change_tool: _f(**args),
)
