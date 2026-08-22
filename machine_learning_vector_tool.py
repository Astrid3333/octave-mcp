"""
machine_learning_vector_tool.py

MCP tool: PCA (via SVD, sin sklearn) y extraccion de features basicas
sobre datasets de vectores (norma, media/varianza por componente, angulos).

mode="pca": reduccion de dimensionalidad via SVD sobre datos centrados
            (opcionalmente estandarizados).
mode="features": estadisticas descriptivas y angulos entre vectores.
mode="self_test": bateria de verificaciones internas.
"""

import numpy as np
import json
import sys


def _to_array(data, name="data"):
    arr = np.array(data, dtype=float)
    if arr.ndim != 2:
        raise ValueError(
            f"{name} debe ser una matriz 2D (n_samples x n_features), se recibio ndim={arr.ndim}"
        )
    if arr.shape[0] < 2:
        raise ValueError(f"{name} debe tener al menos 2 muestras (filas)")
    if arr.shape[1] < 1:
        raise ValueError(f"{name} debe tener al menos 1 componente (columna)")
    return arr


def compute_pca(params):
    data = params.get("data")
    if data is None:
        raise ValueError("Falta 'data' (matriz n_samples x n_features)")
    X = _to_array(data)
    n_samples, n_features = X.shape

    standardize = bool(params.get("standardize", False))
    n_components = params.get("n_components")
    max_components = min(n_samples, n_features)
    if n_components is None:
        n_components = max_components
    else:
        n_components = int(n_components)
        if n_components < 1 or n_components > max_components:
            raise ValueError(
                f"n_components debe estar entre 1 y {max_components}, se recibio {n_components}"
            )

    mean = X.mean(axis=0)
    Xc = X - mean

    if standardize:
        std = Xc.std(axis=0, ddof=1)
        std_safe = np.where(std == 0, 1.0, std)
        Xc = Xc / std_safe
    else:
        std_safe = np.ones(n_features)

    # SVD: Xc = U S Vt
    U, S, Vt = np.linalg.svd(Xc, full_matrices=False)

    components = Vt[:n_components]
    singular_values = S[:n_components]

    # varianza explicada: (S^2)/(n_samples-1)
    variances_all = (S ** 2) / max(n_samples - 1, 1)
    total_variance = variances_all.sum()
    explained_variance = variances_all[:n_components]
    explained_variance_ratio = (
        explained_variance / total_variance if total_variance > 0 else np.zeros(n_components)
    )

    projected = Xc @ components.T

    return {
        "n_samples": n_samples,
        "n_features": n_features,
        "n_components": n_components,
        "mean": mean.tolist(),
        "std_used": std_safe.tolist() if standardize else None,
        "components": components.tolist(),
        "singular_values": singular_values.tolist(),
        "explained_variance": explained_variance.tolist(),
        "explained_variance_ratio": explained_variance_ratio.tolist(),
        "cumulative_explained_variance_ratio": np.cumsum(explained_variance_ratio).tolist(),
        "projected": projected.tolist(),
    }


def compute_features(params):
    data = params.get("data")
    if data is None:
        raise ValueError("Falta 'data' (matriz n_samples x n_features)")
    X = _to_array(data)
    n_samples, n_features = X.shape

    norms = np.linalg.norm(X, axis=1)
    component_means = X.mean(axis=0)
    component_variances = X.var(axis=0, ddof=1) if n_samples > 1 else np.zeros(n_features)
    component_stds = np.sqrt(component_variances)

    centroid = component_means
    centroid_norm = np.linalg.norm(centroid)

    def angle_deg(u, v):
        nu = np.linalg.norm(u)
        nv = np.linalg.norm(v)
        if nu == 0 or nv == 0:
            return None
        cos_theta = np.clip(np.dot(u, v) / (nu * nv), -1.0, 1.0)
        return float(np.degrees(np.arccos(cos_theta)))

    angles_to_centroid = (
        [angle_deg(x, centroid) for x in X] if centroid_norm > 0 else [None] * n_samples
    )

    include_pairwise = bool(params.get("include_pairwise_angles", n_samples <= 20))
    pairwise_angles = None
    if include_pairwise:
        pairwise_angles = [
            [angle_deg(X[i], X[j]) for j in range(n_samples)] for i in range(n_samples)
        ]

    return {
        "n_samples": n_samples,
        "n_features": n_features,
        "norms": norms.tolist(),
        "mean_norm": float(norms.mean()),
        "component_means": component_means.tolist(),
        "component_variances": component_variances.tolist(),
        "component_stds": component_stds.tolist(),
        "centroid": centroid.tolist(),
        "angles_to_centroid_deg": angles_to_centroid,
        "pairwise_angles_deg": pairwise_angles,
    }


def run(mode, params=None):
    params = params or {}
    if mode == "validate":
        r = self_test()
        return {"checks": r["checks"], "validation_passed": r["all_passed"], "n_checks": r["total"]}
    if mode == "pca":
        return compute_pca(params)
    elif mode == "features":
        return compute_features(params)
    elif mode == "self_test":
        return self_test()
    else:
        raise ValueError(f"Modo desconocido: {mode}")


def self_test():
    checks = []

    def check(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    # 1. PCA sobre datos perfectamente colineales (y = 2x): toda la varianza en un eje
    xs = np.linspace(-5, 5, 30)
    data_line = np.column_stack([xs, 2 * xs])
    res = compute_pca({"data": data_line.tolist(), "n_components": 2})
    check(
        "pca: primer componente explica ~100% de la varianza en datos colineales",
        abs(res["explained_variance_ratio"][0] - 1.0) < 1e-6,
        f"ratio[0]={res['explained_variance_ratio'][0]:.6f}",
    )
    check(
        "pca: segundo componente explica ~0% de la varianza",
        res["explained_variance_ratio"][1] < 1e-6,
        f"ratio[1]={res['explained_variance_ratio'][1]:.2e}",
    )

    # 2. PCA: reconstruccion completa (n_components=n_features) recupera los datos originales
    reconstructed = np.array(res["projected"]) @ np.array(res["components"]) + np.array(res["mean"])
    err_recon = np.max(np.abs(reconstructed - data_line))
    check(
        "pca: reconstruccion completa recupera los datos originales",
        err_recon < 1e-8,
        f"max err={err_recon:.2e}",
    )

    # 3. PCA: n_components menor al maximo reduce la forma correctamente
    res2 = compute_pca({"data": data_line.tolist(), "n_components": 1})
    check(
        "pca: n_components=1 produce projected de forma (n,1)",
        np.array(res2["projected"]).shape == (30, 1),
        f"shape={np.array(res2['projected']).shape}",
    )

    # 4. PCA: media calculada correctamente
    mean_esperada = data_line.mean(axis=0)
    err_mean = np.max(np.abs(np.array(res["mean"]) - mean_esperada))
    check(
        "pca: mean coincide con la media real de los datos",
        err_mean < 1e-10,
        f"max err={err_mean:.2e}",
    )

    # 5. features: norma de vectores conocidos
    data_feat = [[3.0, 4.0], [6.0, 8.0], [0.0, 5.0]]
    resf = compute_features({"data": data_feat})
    normas_esperadas = [5.0, 10.0, 5.0]
    err_norm = max(abs(a - b) for a, b in zip(resf["norms"], normas_esperadas))
    check(
        "features: normas coinciden con calculo manual (3,4->5 / 6,8->10 / 0,5->5)",
        err_norm < 1e-9,
        f"obtenido={resf['norms']}",
    )

    # 6. features: angulo entre vectores paralelos (3,4) y (6,8) es 0 grados
    ang = resf["pairwise_angles_deg"][0][1]
    check(
        "features: angulo entre (3,4) y (6,8) (paralelos) es ~0 grados",
        ang is not None and abs(ang) < 1e-6,
        f"angulo={ang}",
    )

    # 7. features: angulo entre (3,4) y (0,5) coincide con el calculo analitico
    ang2 = resf["pairwise_angles_deg"][0][2]
    esperado = float(np.degrees(np.arccos(np.dot([3, 4], [0, 5]) / (5 * 5))))
    check(
        "features: angulo entre (3,4) y (0,5) coincide con calculo analitico",
        abs(ang2 - esperado) < 1e-6,
        f"esperado={esperado:.4f}, obtenido={ang2:.4f}",
    )

    # 8. features: media por componente
    data_stat = [[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]]
    res_stat = compute_features({"data": data_stat})
    check(
        "features: component_means coincide con medias manuales (2.0, 20.0)",
        abs(res_stat["component_means"][0] - 2.0) < 1e-9
        and abs(res_stat["component_means"][1] - 20.0) < 1e-9,
        f"obtenido={res_stat['component_means']}",
    )

    # 9. ValueError con menos de 2 muestras en pca
    try:
        compute_pca({"data": [[1.0, 2.0]]})
        check("ValueError con menos de 2 muestras en pca", False, "no lanzo excepcion")
    except ValueError:
        check("ValueError con menos de 2 muestras en pca", True)

    # 10. ValueError con data 1D en features
    try:
        compute_features({"data": [1.0, 2.0, 3.0]})
        check("ValueError con data 1D en features", False, "no lanzo excepcion")
    except ValueError:
        check("ValueError con data 1D en features", True)

    # 11. ValueError con n_components fuera de rango
    try:
        compute_pca({"data": data_feat, "n_components": 10})
        check("ValueError con n_components fuera de rango", False, "no lanzo excepcion")
    except ValueError:
        check("ValueError con n_components fuera de rango", True)

    # 12. ValueError con modo desconocido en run()
    try:
        run("modo_invalido", {})
        check("ValueError con modo desconocido en run()", False, "no lanzo excepcion")
    except ValueError:
        check("ValueError con modo desconocido en run()", True)

    total = len(checks)
    passed = sum(1 for c in checks if c["passed"])
    return {
        "total": total,
        "passed": passed,
        "all_passed": passed == total,
        "checks": checks,
    }


TOOL_SCHEMA = {
    "name": "machine_learning_vector_tool",
    "description": (
        "PCA (via SVD, sin dependencias externas) y extraccion de features basicas "
        "(normas, media/varianza por componente, angulos entre vectores) sobre datasets "
        "de vectores. modes: pca, features, self_test."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["pca", "features", "self_test", "validate"],
                "description": "Modo de operacion",
            },
            "params": {
                "type": "object",
                "description": (
                    "Parametros del modo. pca: {data, n_components?, standardize?}. "
                    "features: {data, include_pairwise_angles?}. self_test: {}."
                ),
            },
        },
        "required": ["mode"],
    },
}


def _handler(arguments):
    arguments = arguments or {}
    mode = arguments.get("mode")
    params = arguments.get("params", {})
    return run(mode, params)


try:
    from tool_registry import register_tool

    register_tool("machine_learning_vector_tool", TOOL_SCHEMA, _handler)
except ImportError:
    pass


def _main():
    if len(sys.argv) > 1 and sys.argv[1] == "self_test":
        print(json.dumps(self_test(), indent=2, ensure_ascii=False))
        return
    raw = sys.stdin.read() if not sys.stdin.isatty() else None
    if raw:
        req = json.loads(raw)
        mode = req.get("mode")
        params = req.get("params", {})
        print(json.dumps(run(mode, params), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _main()
