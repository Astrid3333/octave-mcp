"""
point_cloud_filter.py -- Filtrado de nubes de puntos: downsampling por
voxel grid y remocion de outliers estadistica (k vecinos mas cercanos).

Modos:
  voxel_downsample            -- agrupa puntos en un grid de voxeles y
                                  devuelve el centroide de cada voxel ocupado
  statistical_outlier_removal -- remueve puntos cuya distancia media a sus
                                  k vecinos mas cercanos excede
                                  mean + std_ratio * std
  validate                    -- casos con respuesta exacta conocida
                                  (agrupacion de voxeles a mano) mas
                                  verificacion cruzada de la busqueda de
                                  vecinos contra fuerza bruta O(N^2)
"""

from collections import defaultdict

import numpy as np
from scipy.spatial import cKDTree


# ---------------------------------------------------------------------------
# Voxel downsampling
# ---------------------------------------------------------------------------

def _voxel_downsample(points, voxel_size):
    points = np.asarray(points, dtype=float)
    if voxel_size <= 0:
        raise ValueError("voxel_size debe ser > 0")
    voxel_idx = np.floor(points / voxel_size).astype(np.int64)
    groups = defaultdict(list)
    for i, key in enumerate(map(tuple, voxel_idx)):
        groups[key].append(i)
    out_points = []
    for key in sorted(groups.keys()):
        idxs = groups[key]
        out_points.append(points[idxs].mean(axis=0))
    out_points = np.array(out_points, dtype=float)
    return {
        "points": out_points.tolist(),
        "num_input": int(points.shape[0]),
        "num_output": int(out_points.shape[0]),
        "voxel_size": float(voxel_size),
    }


# ---------------------------------------------------------------------------
# Statistical outlier removal
# ---------------------------------------------------------------------------

def _knn_mean_distances(points, k):
    """Distancia media a los k vecinos mas cercanos (sin contarse a si
    mismo), usando cKDTree."""
    tree = cKDTree(points)
    # k+1 porque el propio punto es su vecino mas cercano (distancia 0)
    dists, _ = tree.query(points, k=k + 1)
    dists = dists[:, 1:]  # descartar columna 0 (distancia a si mismo)
    return dists.mean(axis=1)


def _knn_mean_distances_bruteforce(points, k):
    """Misma cantidad que _knn_mean_distances pero por fuerza bruta
    O(N^2), usada solo para verificar la version con cKDTree en validate."""
    n = points.shape[0]
    out = np.zeros(n)
    for i in range(n):
        d = np.linalg.norm(points - points[i], axis=1)
        d_sorted = np.sort(d)
        out[i] = d_sorted[1:k + 1].mean()
    return out


def _statistical_outlier_removal(points, k=8, std_ratio=2.0):
    points = np.asarray(points, dtype=float)
    n = points.shape[0]
    k_eff = min(k, n - 1)
    if k_eff < 1:
        raise ValueError("se necesitan al menos 2 puntos para statistical_outlier_removal")
    mean_dists = _knn_mean_distances(points, k_eff)
    mu = float(mean_dists.mean())
    sigma = float(mean_dists.std(ddof=0))
    threshold = mu + std_ratio * sigma
    keep_mask = mean_dists <= threshold
    removed_indices = np.where(~keep_mask)[0].tolist()
    return {
        "points": points[keep_mask].tolist(),
        "removed_indices": removed_indices,
        "num_input": int(n),
        "num_output": int(keep_mask.sum()),
        "mean_distance_mean": mu,
        "mean_distance_std": sigma,
        "threshold": threshold,
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def compute_point_cloud_filter(mode, **params):
    if mode == "validate":
        return _validate_point_cloud_filter()
    elif mode == "voxel_downsample":
        points = np.array(params["points"], dtype=float)
        voxel_size = params["voxel_size"]
        return _voxel_downsample(points, voxel_size)
    elif mode == "statistical_outlier_removal":
        points = np.array(params["points"], dtype=float)
        k = params.get("k", 8)
        std_ratio = params.get("std_ratio", 2.0)
        return _statistical_outlier_removal(points, k=k, std_ratio=std_ratio)
    else:
        raise ValueError(f"modo desconocido: {mode}. Use voxel_downsample | statistical_outlier_removal")


# ---------------------------------------------------------------------------
# Validacion
# ---------------------------------------------------------------------------

def _validate_point_cloud_filter():
    checks = []

    # --- voxel_downsample: caso con respuesta exacta calculada a mano ---
    # 3 puntos muy cerca (mismo voxel de tamano 1.0) + 1 punto lejos (otro voxel)
    pts = np.array([
        [0.1, 0.1, 0.1],
        [0.2, 0.2, 0.2],
        [0.3, 0.3, 0.3],
        [5.5, 5.5, 5.5],
    ])
    res = _voxel_downsample(pts, voxel_size=1.0)
    expected_centroid_group1 = pts[:3].mean(axis=0)
    out_pts = np.array(res["points"])
    checks.append({
        "name": "voxel_downsample_num_output",
        "expected": 2,
        "got": res["num_output"],
        "passed": bool(res["num_output"] == 2),
    })
    # el grupo de 3 puntos cae en el voxel (0,0,0); su centroide debe estar
    # entre los puntos de salida
    match = any(float(np.max(np.abs(op - expected_centroid_group1))) < 1e-9 for op in out_pts)
    checks.append({
        "name": "voxel_downsample_centroid_exacto",
        "expected": expected_centroid_group1.tolist(),
        "got": res["points"],
        "passed": bool(match),
    })

    # --- statistical_outlier_removal: cKDTree vs fuerza bruta O(N^2) ---
    rng = np.random.default_rng(7)
    cluster = rng.normal(loc=0.0, scale=0.2, size=(30, 3))
    mine_fast = _knn_mean_distances(cluster, k=5)
    mine_slow = _knn_mean_distances_bruteforce(cluster, k=5)
    diff = float(np.max(np.abs(mine_fast - mine_slow)))
    checks.append({
        "name": "knn_mean_distance_cKDTree_vs_bruteforce",
        "expected": "max abs diff < 1e-9",
        "got": round(diff, 12),
        "passed": bool(diff < 1e-9),
    })

    # --- statistical_outlier_removal: outliers plantados se remueven ---
    bulk = rng.normal(loc=0.0, scale=0.1, size=(40, 3))
    outliers = np.array([[10.0, 10.0, 10.0], [-12.0, 8.0, -9.0]])
    pts2 = np.vstack([bulk, outliers])
    res2 = _statistical_outlier_removal(pts2, k=8, std_ratio=2.0)
    removed = set(res2["removed_indices"])
    outlier_indices = {len(bulk), len(bulk) + 1}
    outliers_caught = outlier_indices.issubset(removed)
    checks.append({
        "name": "outlier_removal_detecta_outliers_plantados",
        "expected": f"indices {sorted(outlier_indices)} removidos",
        "got": sorted(removed),
        "passed": bool(outliers_caught),
    })
    # no debe removerse una fraccion enorme del cluster bulk (falsos positivos)
    false_positive_rate = len(removed - outlier_indices) / len(bulk)
    checks.append({
        "name": "outlier_removal_pocos_falsos_positivos",
        "expected": "< 15% del cluster bulk removido de mas",
        "got": round(false_positive_rate, 4),
        "passed": bool(false_positive_rate < 0.15),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}


if __name__ == "__main__":
    result = _validate_point_cloud_filter()
    for c in result["checks"]:
        status = "OK" if c["passed"] else "FALLO"
        print(f"[{status}] {c['name']}: esperado={c['expected']}  obtenido={c['got']}")
    print("\nTodas las validaciones pasaron." if result["all_passed"] else "\nHAY VALIDACIONES QUE FALLARON.")


POINT_CLOUD_FILTER_TOOL_SCHEMA = {
    "name": "point_cloud_filter",
    "description": (
        "Filtrado de nubes de puntos: voxel_downsample (reduccion por grid "
        "de voxeles, centroide por celda) y statistical_outlier_removal "
        "(remocion de outliers via distancia media a k vecinos mas "
        "cercanos, umbral mean + std_ratio*std)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["voxel_downsample", "statistical_outlier_removal", "validate"]},
            "params": {"type": "object", "description": "Parametros especificos de cada modo, ver docstrings."},
        },
        "required": ["mode"],
    },
}


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass


def _handle(args):
    _params = args.get("params") or {}
    return compute_point_cloud_filter(mode=args["mode"], **_params)


register_tool("point_cloud_filter", POINT_CLOUD_FILTER_TOOL_SCHEMA, _handle)
