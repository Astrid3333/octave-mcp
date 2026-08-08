#!/usr/bin/env python3
"""
spatial_statistics_tool.py
Estadistica espacial: autocorrelacion espacial global (Moran's I, Geary's C)
con z-score bajo hipotesis nula de aleatoriedad, semivariograma empirico
binneado por distancia, y kriging ordinario (interpolacion optima con modelo
de variograma esferico/exponencial/gaussiano). Aplicable a analisis de
riesgo hidrologico multi-cuenca (autocorrelacion de variables ambientales
entre sitios de monitoreo, interpolacion de variables no muestreadas).
"""
import numpy as np
from scipy.spatial.distance import cdist
from scipy.stats import norm


def _weight_matrix(coordinates, weight_type="inverse_distance", k=None, threshold=None):
    coords = np.asarray(coordinates, dtype=float)
    D = cdist(coords, coords)
    n = len(coords)
    W = np.zeros((n, n))
    if weight_type == "inverse_distance":
        with np.errstate(divide="ignore"):
            W = np.where(D > 0, 1.0 / D, 0.0)
    elif weight_type == "knn":
        k = k or min(4, n - 1)
        for i in range(n):
            nearest = np.argsort(D[i])[1:k + 1]
            W[i, nearest] = 1.0
    elif weight_type == "threshold":
        threshold = threshold or np.median(D[D > 0])
        W = ((D > 0) & (D <= threshold)).astype(float)
    else:
        raise ValueError(f"weight_type desconocido: {weight_type}")
    return W, D


def compute_morans_i(values, coordinates, weight_type="inverse_distance", k=None, threshold=None):
    z = np.asarray(values, dtype=float)
    n = len(z)
    W, _ = _weight_matrix(coordinates, weight_type, k, threshold)
    z_dev = z - z.mean()
    S0 = W.sum()
    num = n * np.sum(W * np.outer(z_dev, z_dev))
    den = S0 * np.sum(z_dev ** 2)
    I = float(num / den) if den != 0 else 0.0

    E_I = -1.0 / (n - 1)
    S1 = 0.5 * np.sum((W + W.T) ** 2)
    S2 = np.sum((W.sum(axis=1) + W.sum(axis=0)) ** 2)
    b2 = (np.sum(z_dev ** 4) / n) / (np.sum(z_dev ** 2) / n) ** 2
    Var_I = ((n * ((n ** 2 - 3 * n + 3) * S1 - n * S2 + 3 * S0 ** 2)
              - b2 * ((n ** 2 - n) * S1 - 2 * n * S2 + 6 * S0 ** 2))
             / ((n - 1) * (n - 2) * (n - 3) * S0 ** 2)) - E_I ** 2
    z_score = float((I - E_I) / np.sqrt(Var_I)) if Var_I > 0 else None
    p_value = float(2 * (1 - norm.cdf(abs(z_score)))) if z_score is not None else None
    return {
        "mode": "morans_i", "n_points": n, "weight_type": weight_type,
        "morans_i": round(I, 6), "expected_i_under_null": round(float(E_I), 6),
        "z_score": round(z_score, 6) if z_score is not None else None,
        "p_value": round(p_value, 6) if p_value is not None else None,
        "interpretation": "clustered_positive" if I > E_I and (p_value or 1) < 0.05 else
                           "dispersed_negative" if I < E_I and (p_value or 1) < 0.05 else "random_no_significant_pattern",
    }


def compute_gearys_c(values, coordinates, weight_type="inverse_distance", k=None, threshold=None):
    z = np.asarray(values, dtype=float)
    n = len(z)
    W, _ = _weight_matrix(coordinates, weight_type, k, threshold)
    S0 = W.sum()
    z_dev = z - z.mean()
    num = (n - 1) * np.sum(W * (z[:, None] - z[None, :]) ** 2)
    den = 2 * S0 * np.sum(z_dev ** 2)
    C = float(num / den) if den != 0 else 1.0
    return {
        "mode": "gearys_c", "n_points": n, "weight_type": weight_type,
        "gearys_c": round(C, 6),
        "expected_c_under_null": 1.0,
        "interpretation": "positive_autocorrelation" if C < 1 else "negative_autocorrelation" if C > 1 else "no_autocorrelation",
    }


def compute_semivariogram(values, coordinates, n_bins=10, max_distance=None):
    z = np.asarray(values, dtype=float)
    coords = np.asarray(coordinates, dtype=float)
    D = cdist(coords, coords)
    n = len(z)
    iu = np.triu_indices(n, k=1)
    dists = D[iu]
    sq_diffs = (z[iu[0]] - z[iu[1]]) ** 2
    if max_distance is None:
        max_distance = dists.max()
    bins = np.linspace(0, max_distance, n_bins + 1)
    bin_idx = np.digitize(dists, bins) - 1
    lags, semivariances, n_pairs = [], [], []
    for b in range(n_bins):
        mask = bin_idx == b
        if mask.sum() > 0:
            lags.append(float((bins[b] + bins[b + 1]) / 2))
            semivariances.append(float(0.5 * sq_diffs[mask].mean()))
            n_pairs.append(int(mask.sum()))
    sill_estimate = float(np.var(z))
    return {
        "mode": "semivariogram", "n_points": n, "n_bins": n_bins, "max_distance": round(float(max_distance), 4),
        "lags": [round(l, 4) for l in lags],
        "semivariances": [round(s, 6) for s in semivariances],
        "n_pairs_per_bin": n_pairs,
        "sample_variance_sill_estimate": round(sill_estimate, 6),
    }


def _variogram_model(h, model, nugget, sill, range_):
    h = np.asarray(h, dtype=float)
    if model == "spherical":
        gamma = np.where(h <= range_, nugget + (sill - nugget) * (1.5 * h / range_ - 0.5 * (h / range_) ** 3), sill)
        gamma = np.where(h == 0, 0, gamma)
    elif model == "exponential":
        gamma = nugget + (sill - nugget) * (1 - np.exp(-h / range_))
        gamma = np.where(h == 0, 0, gamma)
    elif model == "gaussian":
        gamma = nugget + (sill - nugget) * (1 - np.exp(-(h / range_) ** 2))
        gamma = np.where(h == 0, 0, gamma)
    else:
        raise ValueError(f"model desconocido: {model}")
    return gamma


def compute_kriging(sample_coordinates, sample_values, target_coordinates,
                     model="spherical", nugget=0.0, sill=None, range_=None):
    coords = np.asarray(sample_coordinates, dtype=float)
    z = np.asarray(sample_values, dtype=float)
    targets = np.asarray(target_coordinates, dtype=float)
    n = len(z)
    if sill is None:
        sill = float(np.var(z))
    if range_ is None:
        D_sample = cdist(coords, coords)
        range_ = float(D_sample.max() / 2)

    D = cdist(coords, coords)
    Gamma = _variogram_model(D, model, nugget, sill, range_)
    A = np.ones((n + 1, n + 1))
    A[:n, :n] = Gamma
    A[-1, -1] = 0
    A_inv = np.linalg.pinv(A)

    predictions, variances = [], []
    for t in targets:
        d_t = cdist(coords, [t]).flatten()
        gamma_t = _variogram_model(d_t, model, nugget, sill, range_)
        b = np.append(gamma_t, 1.0)
        weights_lagrange = A_inv @ b
        weights = weights_lagrange[:n]
        mu = weights_lagrange[-1]
        pred = float(np.sum(weights * z))
        var = float(np.sum(weights * gamma_t) + mu)
        predictions.append(pred)
        variances.append(max(var, 0.0))

    return {
        "mode": "kriging", "model": model, "nugget": nugget, "sill": round(sill, 6), "range": round(range_, 6),
        "n_sample_points": n, "n_target_points": len(targets),
        "predictions": [round(p, 6) for p in predictions],
        "kriging_variance": [round(v, 6) for v in variances],
        "kriging_std": [round(float(np.sqrt(v)), 6) for v in variances],
    }


def compute_spatial_statistics(mode, **kwargs):
    """Dispatcher unico para el tool MCP spatial_statistics, segun 'mode'."""
    fns = {
        "morans_i": compute_morans_i,
        "gearys_c": compute_gearys_c,
        "semivariogram": compute_semivariogram,
        "kriging": compute_kriging,
    }
    if mode not in fns:
        raise ValueError(f"mode desconocido: {mode}")
    return fns[mode](**kwargs)


SPATIAL_STATISTICS_TOOL_SCHEMA = {
    "name": "spatial_statistics",
    "description": "Estadistica espacial: autocorrelacion global (Moran's I y Geary's C con z-score/p-value bajo hipotesis nula de aleatoriedad), semivariograma empirico binneado por distancia, y kriging ordinario (interpolacion optima con modelo esferico/exponencial/gaussiano). Util para analisis de riesgo hidrologico multi-cuenca y variables ambientales georreferenciadas.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["morans_i", "gearys_c", "semivariogram", "kriging"]},
            "values": {"type": "array"}, "coordinates": {"type": "array"},
            "weight_type": {"type": "string", "enum": ["inverse_distance", "knn", "threshold"]},
            "k": {"type": "integer"}, "threshold": {"type": "number"},
            "n_bins": {"type": "integer"}, "max_distance": {"type": "number"},
            "sample_coordinates": {"type": "array"}, "sample_values": {"type": "array"}, "target_coordinates": {"type": "array"},
            "model": {"type": "string", "enum": ["spherical", "exponential", "gaussian"]},
            "nugget": {"type": "number"}, "sill": {"type": "number"}, "range_": {"type": "number"},
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    rng = np.random.default_rng(42)
    # grilla 5x5 con patron espacialmente autocorrelacionado (gradiente + ruido leve)
    coords_grid = [[i, j] for i in range(5) for j in range(5)]
    values_clustered = [float(i + j) + rng.normal(0, 0.3) for i, j in coords_grid]
    values_random = list(rng.normal(0, 1, 25))

    print(compute_spatial_statistics(mode="morans_i", values=values_clustered, coordinates=coords_grid, weight_type="knn", k=4))
    print(compute_spatial_statistics(mode="morans_i", values=values_random, coordinates=coords_grid, weight_type="knn", k=4))
    print(compute_spatial_statistics(mode="gearys_c", values=values_clustered, coordinates=coords_grid, weight_type="knn", k=4))

    r = compute_spatial_statistics(mode="semivariogram", values=values_clustered, coordinates=coords_grid, n_bins=8)
    print({k: v for k, v in r.items()})

    sample_coords = [[0, 0], [4, 0], [0, 4], [4, 4], [2, 2]]
    sample_vals = [1.0, 5.0, 5.0, 9.0, 5.0]
    targets = [[1, 1], [3, 3], [2, 0]]
    print(compute_spatial_statistics(mode="kriging", sample_coordinates=sample_coords, sample_values=sample_vals, target_coordinates=targets, model="spherical"))
