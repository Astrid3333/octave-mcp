"""
forest_fire_simulator_tool.py

Automata celular para propagacion de incendios forestales en una grilla 2D.
Modelo base: cada celda tiene estado 0 (vacio/quemado), 1 (en llamas) o 2
(bosque). En cada paso de tiempo:
  - bosque (2) con vecino en llamas (1) -> se enciende (pasa a 1), con
    probabilidad que depende de la direccion del vecino y (opcionalmente)
    la pendiente entre celdas.
  - bosque (2) puede encenderse solo por ignicion espontanea (rayo) con
    probabilidad p_lightning.
  - en llamas (1) -> se consume, pasa a vacio (0) (combustion de un paso,
    igual que el modelo clasico de automata celular de incendios).
  - vacio (0) puede regenerarse a bosque (2) con probabilidad p_growth.

Vecindad: 4-conectada (arriba/abajo/izquierda/derecha), con bordes
periodicos (toroidal) -- igual que el pseudocodigo Octave de referencia
(indexado circular via [n 1:n-1] / [2:n 1]). Un dominio finito real (sin
wraparound) requeriria recorte de bordes; no implementado aqui.

Extension de pendiente (opcional, mas alla del modelo clasico):
si se provee elevation_grid (misma forma que la grilla de vegetacion),
la probabilidad de que el fuego se propague de una celda en llamas a un
vecino de bosque se ajusta segun la pendiente entre ambas celdas: subir
una ladera aumenta la probabilidad de ignicion, bajarla la reduce. Esto
sigue la misma logica cualitativa que el factor de pendiente de Rothermel
(ya usado en wildfire_risk_tool.py para tasa de propagacion puntual), pero
aqui es una aproximacion lineal simple sobre la probabilidad de ignicion
por celda, no el modelo completo de Rothermel. Sin elevation_grid, el
modelo se reduce exactamente al automata clasico (ignicion determinista:
todo bosque con vecino en llamas se quema al paso siguiente).

Modos:
  - run: corre la simulacion n_steps pasos y devuelve el historial de
    conteos por estado (vacio/en_llamas/bosque) y la grilla final.
  - validate: suite de auto-chequeo.
"""

import numpy as np


def _neighbor_burning(veg):
    """Devuelve (arriba, abajo, izquierda, derecha): para cada celda,
    valor del vecino en esa direccion (bordes toroidal, via np.roll).
    up[i,j] = veg[i-1,j] (el vecino de arriba)."""
    up = np.roll(veg, 1, axis=0)
    down = np.roll(veg, -1, axis=0)
    left = np.roll(veg, 1, axis=1)
    right = np.roll(veg, -1, axis=1)
    return up, down, left, right


def _slope_ignition_prob(elevation_grid, base_prob, slope_multiplier, cell_size_m):
    """Para cada una de las 4 direcciones, probabilidad de ignicion desde
    ese vecino ajustada por pendiente. dz = elevacion(celda) -
    elevacion(vecino): positivo si la celda esta mas alta que el vecino
    en llamas (fuego subiendo la ladera hacia la celda) -> aumenta
    probabilidad; negativo (fuego bajando) -> la reduce. Aproximacion
    lineal simple sobre tan(pendiente) ~ dz/cell_size_m, recortada a
    [0, 1] -- no es el modelo completo de Rothermel, ver docstring de
    modulo. Devuelve (p_up, p_down, p_left, p_right)."""
    e_up, e_down, e_left, e_right = _neighbor_burning(elevation_grid)
    probs = []
    for e_neighbor in (e_up, e_down, e_left, e_right):
        dz = elevation_grid - e_neighbor
        slope_factor = dz / cell_size_m
        p = base_prob * np.clip(1.0 + slope_multiplier * slope_factor, 0.0, 1.0)
        probs.append(p)
    return tuple(probs)


def _step(veg, p_lightning, p_growth, rng, elevation_grid=None,
          base_spread_prob=1.0, slope_multiplier=4.0, cell_size_m=30.0):
    """Un paso del automata. Devuelve la grilla siguiente."""
    up, down, left, right = _neighbor_burning(veg)
    burning_up = (up == 1)
    burning_down = (down == 1)
    burning_left = (left == 1)
    burning_right = (right == 1)

    if elevation_grid is None:
        # Modelo clasico: ignicion determinista (prob=1) desde cualquier
        # vecino en llamas.
        p_up = p_down = p_left = p_right = base_spread_prob
    else:
        p_up, p_down, p_left, p_right = _slope_ignition_prob(
            elevation_grid, base_spread_prob, slope_multiplier, cell_size_m
        )

    # Probabilidad de NO encenderse desde ninguna direccion = producto de
    # "no encenderse desde esa direccion" sobre las direcciones con vecino
    # en llamas (si el vecino no esta en llamas, esa direccion no aporta
    # riesgo, equivalente a probabilidad 0 de esa direccion).
    no_ignite = np.ones_like(veg, dtype=float)
    no_ignite *= np.where(burning_up, 1.0 - p_up, 1.0)
    no_ignite *= np.where(burning_down, 1.0 - p_down, 1.0)
    no_ignite *= np.where(burning_left, 1.0 - p_left, 1.0)
    no_ignite *= np.where(burning_right, 1.0 - p_right, 1.0)
    ignite_prob = 1.0 - no_ignite

    forest = (veg == 2)
    roll_spread = rng.random(veg.shape)
    roll_lightning = rng.random(veg.shape)
    catches_fire = forest & ((roll_spread < ignite_prob) | (roll_lightning < p_lightning))

    empty = (veg == 0)
    roll_growth = rng.random(veg.shape)
    regrows = empty & (roll_growth < p_growth)

    was_burning = (veg == 1)

    new_veg = np.where(catches_fire, 1, veg)
    new_veg = np.where(was_burning, 0, new_veg)
    new_veg = np.where(regrows, 2, new_veg)
    return new_veg


def _counts(veg):
    return {
        "vacio": int(np.sum(veg == 0)),
        "en_llamas": int(np.sum(veg == 1)),
        "bosque": int(np.sum(veg == 2)),
    }


def _mode_run(params):
    initial_veg = params.get("initial_veg")
    n = params.get("n", 50)
    n_steps = params.get("n_steps", 20)
    p_lightning = params.get("p_lightning", 0.000005)
    p_growth = params.get("p_growth", 0.01)
    ignition_points = params.get("ignition_points")
    elevation_grid_raw = params.get("elevation_grid")
    base_spread_prob = params.get("base_spread_prob", 1.0)
    slope_multiplier = params.get("slope_multiplier", 4.0)
    cell_size_m = params.get("cell_size_m", 30.0)
    seed = params.get("seed")

    if initial_veg is not None:
        veg = np.array(initial_veg, dtype=int)
        if veg.ndim != 2:
            raise ValueError("initial_veg debe ser una grilla 2D")
    else:
        veg = np.full((n, n), 2, dtype=int)

    if ignition_points:
        for (i, j) in ignition_points:
            if not (0 <= i < veg.shape[0] and 0 <= j < veg.shape[1]):
                raise ValueError(f"ignition_point {(i, j)} fuera de la grilla {veg.shape}")
            veg[i, j] = 1

    elevation_grid = None
    if elevation_grid_raw is not None:
        elevation_grid = np.array(elevation_grid_raw, dtype=float)
        if elevation_grid.shape != veg.shape:
            raise ValueError(
                f"elevation_grid {elevation_grid.shape} debe tener la misma forma "
                f"que la grilla de vegetacion {veg.shape}"
            )

    rng = np.random.default_rng(seed)

    history = [_counts(veg)]
    for _ in range(n_steps):
        veg = _step(
            veg, p_lightning, p_growth, rng,
            elevation_grid=elevation_grid, base_spread_prob=base_spread_prob,
            slope_multiplier=slope_multiplier, cell_size_m=cell_size_m,
        )
        history.append(_counts(veg))

    return {
        "n_steps": n_steps,
        "grid_shape": list(veg.shape),
        "history": history,
        "final_grid": veg.tolist(),
        "used_elevation": elevation_grid is not None,
        "note": (
            "Vecindad 4-conectada, bordes periodicos (toroidal). Sin "
            "elevation_grid, ignicion determinista desde cualquier vecino "
            "en llamas (modelo clasico). Con elevation_grid, la "
            "probabilidad de ignicion por direccion se ajusta por pendiente "
            "(aproximacion lineal, no Rothermel completo)."
        ),
    }


def _validate():
    checks = []

    # Check 1: sin elevacion, ignicion determinista -- un foco unico en el
    # centro de una grilla grande de puro bosque debe encender EXACTAMENTE
    # sus 4 vecinos en el paso 1 (bordes toroidal no interfieren en grilla
    # grande y foco central).
    n = 21
    veg = np.full((n, n), 2, dtype=int)
    c = n // 2
    veg[c, c] = 1
    rng = np.random.default_rng(0)
    veg1 = _step(veg, p_lightning=0.0, p_growth=0.0, rng=rng)
    expected_burning = {(c - 1, c), (c + 1, c), (c, c - 1), (c, c + 1)}
    actual_burning = {(i, j) for i in range(n) for j in range(n) if veg1[i, j] == 1}
    checks.append({
        "name": "deterministic_spread_exact_4_neighbors",
        "expected": sorted(expected_burning), "actual": sorted(actual_burning),
        "passed": bool(actual_burning == expected_burning),
    })

    # Check 2: la celda que estaba en llamas se consume (pasa a vacio) en
    # el mismo paso.
    checks.append({
        "name": "burning_cell_becomes_empty",
        "value": int(veg1[c, c]),
        "passed": bool(veg1[c, c] == 0),
    })

    # Check 3: sin crecimiento (p_growth=0) y sin rayo (p_lightning=0), el
    # numero total de celdas vacias nunca decrece (nada regenera) a lo
    # largo de varios pasos.
    r = _mode_run({
        "n": 15, "n_steps": 8, "p_lightning": 0.0, "p_growth": 0.0,
        "ignition_points": [[7, 7]], "seed": 1,
    })
    vacios = [h["vacio"] for h in r["history"]]
    checks.append({
        "name": "no_growth_no_lightning_vacio_never_decreases",
        "vacios_por_paso": vacios,
        "passed": bool(all(vacios[i] <= vacios[i + 1] for i in range(len(vacios) - 1))),
    })

    # Check 4: con p_growth=1.0 (siempre regenera) toda celda vacia
    # regenera EN EL PASO SIGUIENTE al que quedo vacia -- no en el mismo
    # paso. Por eso la invariante correcta es: vacio(t) == en_llamas(t-1)
    # para todo t>=1 (lo unico que sigue vacio en t es lo que se acaba de
    # quemar en t; todo lo que ya estaba vacio antes de t se regenero
    # instantaneamente al llegar a t).
    r4 = _mode_run({
        "n": 11, "n_steps": 4, "p_lightning": 0.0, "p_growth": 1.0,
        "ignition_points": [[5, 5]], "seed": 2,
    })
    h4 = r4["history"]
    invariant_holds = all(h4[t]["vacio"] == h4[t - 1]["en_llamas"] for t in range(1, len(h4)))
    checks.append({
        "name": "full_growth_prob_empty_equals_prev_burning",
        "vacios_por_paso": [h["vacio"] for h in h4],
        "en_llamas_por_paso": [h["en_llamas"] for h in h4],
        "passed": bool(invariant_holds),
    })

    # Check 5: con elevation_grid en rampa (mas alta hacia un lado), el
    # fuego debe avanzar MAS celdas en la direccion cuesta arriba que en
    # la direccion opuesta (cuesta abajo), en el mismo numero de pasos.
    n5 = 41
    c5 = n5 // 2
    veg5 = np.full((n5, n5), 2, dtype=int)
    veg5[c5, c5] = 1
    # rampa: elevacion crece con la columna (j) -> "derecha" es cuesta arriba
    elev5 = np.tile(np.arange(n5, dtype=float), (n5, 1))
    r5 = _mode_run({
        "initial_veg": veg5.tolist(), "n_steps": 10,
        "p_lightning": 0.0, "p_growth": 0.0,
        "elevation_grid": elev5.tolist(),
        "base_spread_prob": 0.6, "slope_multiplier": 4.0, "cell_size_m": 1.0,
        "seed": 3,
    })
    final5 = np.array(r5["final_grid"])
    burned_or_burning5 = (final5 != 2)
    row_c = burned_or_burning5[c5, :]
    idx_burned = np.where(row_c)[0]
    dist_right = max((j - c5) for j in idx_burned if j >= c5) if any(j >= c5 for j in idx_burned) else 0
    dist_left = max((c5 - j) for j in idx_burned if j <= c5) if any(j <= c5 for j in idx_burned) else 0
    checks.append({
        "name": "fire_spreads_farther_uphill_than_downhill",
        "dist_uphill_right": int(dist_right), "dist_downhill_left": int(dist_left),
        "passed": bool(dist_right > dist_left),
    })

    # Check 6: elevation_grid con forma distinta a la grilla de vegetacion
    # da error explicito, no crash silencioso.
    try:
        _mode_run({
            "n": 10, "n_steps": 1, "elevation_grid": np.zeros((5, 5)).tolist(),
        })
        check6_passed = False
    except ValueError:
        check6_passed = True
    checks.append({
        "name": "mismatched_elevation_shape_gives_error_no_crash",
        "passed": bool(check6_passed),
    })

    # Check 7: ignition_point fuera de rango da error explicito.
    try:
        _mode_run({"n": 5, "n_steps": 1, "ignition_points": [[99, 99]]})
        check7_passed = False
    except ValueError:
        check7_passed = True
    checks.append({
        "name": "out_of_range_ignition_point_gives_error_no_crash",
        "passed": bool(check7_passed),
    })

    # Check 8: mismo seed -> misma trayectoria (reproducibilidad), corrida
    # con probabilidades intermedias (no deterministas) para que la
    # semilla realmente importe.
    params8 = {
        "n": 20, "n_steps": 10, "p_lightning": 0.02, "p_growth": 0.05,
        "ignition_points": [[10, 10]], "seed": 42,
    }
    ra = _mode_run(params8)
    rb = _mode_run(params8)
    checks.append({
        "name": "same_seed_reproducible",
        "passed": bool(ra["history"] == rb["history"]),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_forest_fire_simulator(mode, params=None):
    params = params or {}
    if mode == "run":
        return _mode_run(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"modo desconocido: {mode!r}")


FOREST_FIRE_SIMULATOR_TOOL_SCHEMA = {
    "name": "forest_fire_simulator",
    "description": (
        "Automata celular para propagacion de incendios forestales en grilla 2D "
        "(estados: 0=vacio/quemado, 1=en llamas, 2=bosque). Vecindad 4-conectada, "
        "bordes periodicos. Sin elevation_grid: ignicion determinista clasica "
        "(todo bosque con vecino en llamas se quema al paso siguiente), mas "
        "ignicion espontanea por rayo (p_lightning) y regeneracion (p_growth). "
        "Con elevation_grid (opcional, misma forma que la grilla, DEBE ser "
        "provista externamente -- no hay integracion con SRTM/OpenTopoData/etc., "
        "mismo patron que flood_connectivity_tool): ajusta la probabilidad de "
        "ignicion por pendiente entre celdas (subir ladera aumenta probabilidad, "
        "bajar la reduce) via aproximacion lineal simple -- no es el modelo "
        "completo de Rothermel de wildfire_risk_tool.py, que da tasa de "
        "propagacion puntual; este tool da evolucion espacial completa en el "
        "tiempo, son complementarios."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["run", "validate"]},
            "params": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "default": 50, "description": "Tamano de grilla NxN si no se provee initial_veg."},
                    "initial_veg": {"type": "array", "description": "Grilla 2D inicial (0/1/2), override de n. Lista de listas."},
                    "n_steps": {"type": "integer", "default": 20},
                    "p_lightning": {"type": "number", "default": 0.000005, "description": "Probabilidad de ignicion espontanea por celda de bosque por paso."},
                    "p_growth": {"type": "number", "default": 0.01, "description": "Probabilidad de regeneracion de bosque por celda vacia por paso."},
                    "ignition_points": {"type": "array", "description": "Lista de [fila,col] forzados a estado 'en llamas' al inicio."},
                    "elevation_grid": {"type": "array", "description": "Grilla 2D de elevacion (misma forma que la grilla de vegetacion), opcional. Debe ser provista externamente."},
                    "base_spread_prob": {"type": "number", "default": 1.0, "description": "Probabilidad base de ignicion desde un vecino en llamas antes del ajuste por pendiente. 1.0 = modelo clasico determinista si ademas no hay elevation_grid."},
                    "slope_multiplier": {"type": "number", "default": 4.0, "description": "Solo con elevation_grid. Sensibilidad de la probabilidad de ignicion a la pendiente (aproximacion lineal sobre dz/cell_size_m)."},
                    "cell_size_m": {"type": "number", "default": 30.0, "description": "Solo con elevation_grid. Tamano fisico de celda en metros, para convertir dz a pendiente."},
                    "seed": {"type": "integer", "description": "Semilla del generador aleatorio, para reproducibilidad."},
                },
            },
        },
        "required": ["mode"],
    },
}


try:
    from tool_registry import register_tool
    register_tool(
        name="forest_fire_simulator",
        schema=FOREST_FIRE_SIMULATOR_TOOL_SCHEMA,
        handler=lambda args: compute_forest_fire_simulator(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass
