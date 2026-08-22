"""
genESOM_simulator: aumento de datos generativo estilo genESOM (generative
Emergent Self-Organizing Map) para datasets biologicos pequenos.

Entrena un SOM sobre un conjunto reducido de muestras reales (ej. resultados
de un experimento con pocos animales) y genera muestras sinteticas
estadisticamente similares, siguiendo el principio de las 3R (reduccion).

No es un ML framework generico: es deliberadamente simple y auditable,
consistente con el resto de octave-mcp.
"""

import sys
import json
from collections import defaultdict

import numpy as np


# ---------------------------------------------------------------------------
# validacion
# ---------------------------------------------------------------------------

def _validate_data(data):
    if data is None:
        raise ValueError("falta 'data' en params")
    arr = np.array(data, dtype=float)
    if arr.ndim != 2:
        raise ValueError("data debe ser una lista de listas (muestras x features), 2D")
    if arr.shape[0] < 5:
        raise ValueError(f"se requieren al menos 5 muestras reales, se recibieron {arr.shape[0]}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("data contiene valores no finitos (NaN/inf)")
    return arr


# ---------------------------------------------------------------------------
# entrenamiento SOM
# ---------------------------------------------------------------------------

def _train_som(data_arr, grid_size=(5, 5), n_epochs=200, random_state=42):
    n_samples, n_features = data_arr.shape
    rng = np.random.default_rng(random_state)

    data_min = data_arr.min(axis=0)
    data_max = data_arr.max(axis=0)
    scale = np.where(data_max - data_min < 1e-12, 1.0, data_max - data_min)
    norm_data = (data_arr - data_min) / scale

    gx, gy = grid_size
    if gx < 1 or gy < 1:
        raise ValueError("grid_size debe tener dimensiones >= 1")

    weights = rng.uniform(0, 1, size=(gx, gy, n_features))
    grid_coords = np.array([[i, j] for i in range(gx) for j in range(gy)],
                            dtype=float).reshape(gx, gy, 2)

    radius0 = max(gx, gy) / 2.0
    lr0 = 0.5

    for epoch in range(n_epochs):
        frac = epoch / max(n_epochs, 1)
        lr = lr0 * (1 - frac)
        radius = radius0 * (1 - frac) + 1e-3

        idx = rng.integers(0, n_samples)
        sample = norm_data[idx]

        dists = np.sum((weights - sample) ** 2, axis=2)
        bmu_idx = np.array(np.unravel_index(np.argmin(dists), dists.shape), dtype=float)

        grid_dists = np.sum((grid_coords - bmu_idx) ** 2, axis=2)
        neighborhood = np.exp(-grid_dists / (2 * radius ** 2))

        weights += lr * neighborhood[..., None] * (sample - weights)

    # asignar cada muestra real a su BMU final
    assignments = []
    for i in range(n_samples):
        dists = np.sum((weights - norm_data[i]) ** 2, axis=2)
        bmu_idx = np.unravel_index(np.argmin(dists), dists.shape)
        assignments.append(bmu_idx)

    return {
        "weights": weights,
        "data_min": data_min,
        "scale": scale,
        "assignments": assignments,
        "norm_data": norm_data,
    }


def _generate_synthetic(model, n_synthetic, noise_scale=0.05, random_state=43):
    rng = np.random.default_rng(random_state)
    weights = model["weights"]
    assignments = model["assignments"]
    norm_data = model["norm_data"]
    n_features = weights.shape[2]

    node_points = defaultdict(list)
    for i, a in enumerate(assignments):
        node_points[a].append(norm_data[i])

    occupied_nodes = list(node_points.keys())
    if not occupied_nodes:
        raise ValueError("entrenamiento del SOM no produjo nodos ocupados")

    synthetic_norm = []
    for _ in range(n_synthetic):
        node = occupied_nodes[rng.integers(0, len(occupied_nodes))]
        pts = np.array(node_points[node])
        center = weights[node]
        if len(pts) > 1:
            local_std = pts.std(axis=0)
        else:
            local_std = np.full(n_features, noise_scale)
        local_std = np.maximum(local_std, 1e-3)
        sample = center + rng.normal(0, 1, size=n_features) * local_std
        synthetic_norm.append(sample)

    synthetic_norm = np.clip(np.array(synthetic_norm), 0.0, 1.0)
    synthetic = synthetic_norm * model["scale"] + model["data_min"]
    return synthetic


def _compare_stats(real, synthetic):
    real_mean, real_std = real.mean(axis=0), real.std(axis=0)
    syn_mean, syn_std = synthetic.mean(axis=0), synthetic.std(axis=0)

    mean_rel = np.abs(syn_mean - real_mean) / np.where(np.abs(real_mean) < 1e-9, 1.0, np.abs(real_mean))
    std_rel = np.abs(syn_std - real_std) / np.where(real_std < 1e-9, 1.0, real_std)

    return {
        "real_mean": real_mean.tolist(),
        "synthetic_mean": syn_mean.tolist(),
        "real_std": real_std.tolist(),
        "synthetic_std": syn_std.tolist(),
        "mean_relative_diff_avg": float(np.mean(mean_rel)),
        "std_relative_diff_avg": float(np.mean(std_rel)),
    }


# ---------------------------------------------------------------------------
# modo principal
# ---------------------------------------------------------------------------

def augment(params):
    params = params or {}
    data_arr = _validate_data(params.get("data"))

    n_synthetic = int(params.get("n_synthetic", len(data_arr)))
    if n_synthetic < 1:
        raise ValueError("n_synthetic debe ser >= 1")

    grid_size = tuple(params.get("grid_size", [5, 5]))
    n_epochs = int(params.get("n_epochs", 200))
    noise_scale = float(params.get("noise_scale", 0.05))
    random_state = int(params.get("random_state", 42))

    model = _train_som(data_arr, grid_size=grid_size, n_epochs=n_epochs, random_state=random_state)
    synthetic = _generate_synthetic(model, n_synthetic, noise_scale=noise_scale, random_state=random_state + 1)
    stats = _compare_stats(data_arr, synthetic)

    return {
        "n_real": int(len(data_arr)),
        "n_synthetic": int(len(synthetic)),
        "grid_size": list(grid_size),
        "synthetic_data": synthetic.tolist(),
        "comparison": stats,
    }


TOOL_SCHEMA = {
    "name": "genESOM_simulator",
    "description": (
        "Aumento de datos generativo estilo genESOM (generative Emergent "
        "Self-Organizing Map) para datasets biologicos pequenos. Entrena un "
        "SOM sobre un conjunto reducido de muestras reales (ej. resultados "
        "de un experimento con pocos animales) y genera muestras sinteticas "
        "estadisticamente similares, siguiendo el principio de las 3R "
        "(reduccion). Modos: augment (entrena + genera + compara "
        "estadisticas), self_test."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["augment", "self_test", "validate"]},
            "params": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "number"}},
                        "description": "muestras reales, lista de listas (n_muestras x n_features), minimo 5",
                    },
                    "n_synthetic": {"type": "integer", "description": "muestras sinteticas a generar (default: n_real)"},
                    "grid_size": {"type": "array", "items": {"type": "integer"}, "description": "[filas, columnas] de la grilla SOM (default [5,5])"},
                    "n_epochs": {"type": "integer", "description": "epocas de entrenamiento (default 200)"},
                    "noise_scale": {"type": "number", "description": "ruido gaussiano en espacio normalizado para nodos con 1 sola muestra (default 0.05)"},
                    "random_state": {"type": "integer", "description": "semilla, default 42"},
                },
            },
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------------------
# self_test
# ---------------------------------------------------------------------------

def run_self_test():
    checks = []

    def check(name, cond, detail=""):
        checks.append({"name": name, "passed": bool(cond), "detail": detail})

    rng = np.random.default_rng(7)
    cluster_a = rng.normal(loc=[0, 0], scale=[1, 1], size=(15, 2))
    cluster_b = rng.normal(loc=[8, 8], scale=[1, 1], size=(15, 2))
    data = np.vstack([cluster_a, cluster_b]).tolist()

    # 1) forma de salida correcta
    out = augment({"data": data, "n_synthetic": 20, "random_state": 1})
    check("augment: n_synthetic respetado", out["n_synthetic"] == 20,
          f"pedido=20, obtenido={out['n_synthetic']}")
    check("augment: shape de synthetic_data correcta",
          len(out["synthetic_data"]) == 20 and len(out["synthetic_data"][0]) == 2,
          f"shape=({len(out['synthetic_data'])}, {len(out['synthetic_data'][0])})")

    # 2) medias sinteticas razonablemente cerca de las reales (SOM es aproximado, tolerancia generosa)
    mean_diff = out["comparison"]["mean_relative_diff_avg"]
    check("augment: media sintetica dentro de tolerancia (<0.5 relativo)",
          mean_diff < 0.5, f"mean_relative_diff_avg={mean_diff:.4f}")

    # 3) dispersion sintetica no colapsa a cero ni explota
    real_std = np.array(out["comparison"]["real_std"])
    syn_std = np.array(out["comparison"]["synthetic_std"])
    ratio = syn_std / np.where(real_std < 1e-9, 1.0, real_std)
    check("augment: std sintetica en rango razonable (0.05x - 10x de la real)",
          bool(np.all(ratio > 0.05) and np.all(ratio < 10)),
          f"ratios={ratio.tolist()}")

    # 4) reproducibilidad con misma semilla
    out2 = augment({"data": data, "n_synthetic": 20, "random_state": 1})
    check("augment: reproducible con mismo random_state",
          out["synthetic_data"] == out2["synthetic_data"], "")

    # 5) grid_size custom
    out3 = augment({"data": data, "n_synthetic": 5, "grid_size": [3, 3], "random_state": 2})
    check("augment: grid_size custom no rompe", out3["grid_size"] == [3, 3],
          f"grid_size={out3['grid_size']}")

    # 6) n_synthetic=1 (caso borde)
    out4 = augment({"data": data, "n_synthetic": 1, "random_state": 3})
    check("augment: n_synthetic=1 funciona", len(out4["synthetic_data"]) == 1, "")

    # 7) errores esperados
    try:
        augment({"data": [[1, 2], [3, 4]]})  # menos de 5 muestras
        check("ValueError con <5 muestras", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con <5 muestras", True, "")

    try:
        augment({"data": [[1, 2], [3, "x"], [5, 6], [7, 8], [9, 10]]})  # no numerico
        check("ValueError con datos no numericos", False, "no se levanto excepcion")
    except (ValueError, TypeError):
        check("ValueError con datos no numericos", True, "")

    try:
        augment({"data": [1, 2, 3, 4, 5]})  # 1D en vez de 2D
        check("ValueError con data 1D", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con data 1D", True, "")

    try:
        run("modo_inexistente", {})
        check("ValueError con modo desconocido en run()", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con modo desconocido en run()", True, "")

    total = len(checks)
    passed = sum(1 for c in checks if c["passed"])
    return {"total": total, "passed": passed, "all_passed": passed == total, "checks": checks}


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

def run(mode, params=None):
    if mode == "validate":
        r = run_self_test()
        return {"checks": r["checks"], "validation_passed": r["all_passed"], "n_checks": r["total"]}
    if mode == "augment":
        return augment(params or {})
    elif mode == "self_test":
        return run_self_test()
    else:
        raise ValueError(f"modo desconocido: {mode} (usar augment/self_test)")


if __name__ == "__main__":
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "self_test"
    params_arg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    try:
        out = run(mode_arg, params_arg)
        print(json.dumps(out, indent=2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)


def _register():
    """
    Auto-registro estilo octave-mcp (patron self-registrante via
    tool_registry, register_tool(name, schema, handler)).
    """
    try:
        import tool_registry

        def _handler(args):
            return run(args.get("mode"), args.get("params"))

        tool_registry.register_tool("genESOM_simulator", TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()
