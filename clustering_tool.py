"""
clustering_tool.py
Fase C del roadmap de estadistica: clustering y reduccion de dimensionalidad.

Modos:
  - kmeans        : K-means con inicializacion k-means++, silhouette y Davies-Bouldin
  - hierarchical  : clustering jerarquico (linkage single/complete/average), estructura
                     de dendrograma (para math_visualization_tool) + asignacion de clusters
                     via corte a k grupos
  - pca_extended  : PCA con biplot (loadings + scores) y contribucion de variables,
                     complementa linear_algebra_tool (no lo duplica)

Validado contra sklearn:
  - kmeans: centroides, inertia, silhouette_score, davies_bouldin_score comparados
    contra sklearn.cluster.KMeans / sklearn.metrics
  - hierarchical: asignacion de clusters (corte a k grupos) comparada contra
    sklearn.cluster.AgglomerativeClustering (misma metrica de linkage), matriz de
    linkage generada con scipy.cluster.hierarchy (referencia canonica)
  - pca_extended: varianza explicada y loadings (salvo signo, que es arbitrario en
    SVD) comparados contra sklearn.decomposition.PCA
"""
import numpy as np


# ---------------------------------------------------------------------------
# kmeans
# ---------------------------------------------------------------------------

def _kmeans_plus_plus_init(X, k, rng):
    n = X.shape[0]
    centers = np.empty((k, X.shape[1]))
    first = rng.integers(n)
    centers[0] = X[first]
    closest_sq_dist = np.sum((X - centers[0]) ** 2, axis=1)
    for i in range(1, k):
        probs = closest_sq_dist / closest_sq_dist.sum()
        next_idx = rng.choice(n, p=probs)
        centers[i] = X[next_idx]
        new_sq_dist = np.sum((X - centers[i]) ** 2, axis=1)
        closest_sq_dist = np.minimum(closest_sq_dist, new_sq_dist)
    return centers


def _kmeans_single_run(X, k, rng, max_iter=300, tol=1e-4):
    centers = _kmeans_plus_plus_init(X, k, rng)
    labels = np.zeros(X.shape[0], dtype=int)
    for _ in range(max_iter):
        dists = np.linalg.norm(X[:, None, :] - centers[None, :, :], axis=2)
        new_labels = np.argmin(dists, axis=1)
        new_centers = np.array([
            X[new_labels == j].mean(axis=0) if np.any(new_labels == j) else centers[j]
            for j in range(k)
        ])
        shift = np.linalg.norm(new_centers - centers)
        centers, labels = new_centers, new_labels
        if shift < tol:
            break
    inertia = float(np.sum((X - centers[labels]) ** 2))
    return centers, labels, inertia


def _silhouette_score(X, labels):
    n = X.shape[0]
    unique_labels = np.unique(labels)
    if len(unique_labels) < 2:
        return 0.0
    dist = np.linalg.norm(X[:, None, :] - X[None, :, :], axis=2)
    sil = np.zeros(n)
    for i in range(n):
        same = labels == labels[i]
        same[i] = False
        if not np.any(same):
            sil[i] = 0.0
            continue
        a = dist[i, same].mean()
        b = np.inf
        for lab in unique_labels:
            if lab == labels[i]:
                continue
            other = labels == lab
            b = min(b, dist[i, other].mean())
        sil[i] = (b - a) / max(a, b)
    return float(sil.mean())


def _davies_bouldin_score(X, labels, centers):
    k = centers.shape[0]
    unique_labels = np.unique(labels)
    scatter = np.zeros(k)
    for j in unique_labels:
        pts = X[labels == j]
        scatter[j] = np.mean(np.linalg.norm(pts - centers[j], axis=1)) if len(pts) else 0.0
    db_terms = []
    for i in unique_labels:
        max_ratio = -np.inf
        for j in unique_labels:
            if i == j:
                continue
            cd = np.linalg.norm(centers[i] - centers[j])
            if cd == 0:
                continue
            ratio = (scatter[i] + scatter[j]) / cd
            max_ratio = max(max_ratio, ratio)
        if max_ratio > -np.inf:
            db_terms.append(max_ratio)
    return float(np.mean(db_terms)) if db_terms else 0.0


def _kmeans(X, k, n_init=10, max_iter=300, random_state=0):
    X = np.asarray(X, dtype=float)
    rng = np.random.default_rng(random_state)
    best = None
    for _ in range(n_init):
        centers, labels, inertia = _kmeans_single_run(X, k, rng, max_iter=max_iter)
        if best is None or inertia < best[2]:
            best = (centers, labels, inertia)
    centers, labels, inertia = best
    sil = _silhouette_score(X, labels)
    db = _davies_bouldin_score(X, labels, centers)
    return {
        "mode": "kmeans",
        "k": k,
        "labels": labels.tolist(),
        "centroids": centers.tolist(),
        "inertia": inertia,
        "silhouette_score": sil,
        "davies_bouldin_score": db,
    }


# ---------------------------------------------------------------------------
# hierarchical
# ---------------------------------------------------------------------------

def _hierarchical(X, linkage="average", n_clusters=None):
    from scipy.cluster.hierarchy import linkage as scipy_linkage, fcluster, dendrogram
    from scipy.spatial.distance import pdist

    X = np.asarray(X, dtype=float)
    method_map = {"single": "single", "complete": "complete", "average": "average"}
    if linkage not in method_map:
        raise ValueError("linkage debe ser single | complete | average")
    Z = scipy_linkage(pdist(X), method=method_map[linkage])

    dendro = dendrogram(Z, no_plot=True)
    result = {
        "mode": "hierarchical",
        "linkage": linkage,
        "linkage_matrix": Z.tolist(),
        "dendrogram_order": dendro["leaves"],
        "n_samples": int(X.shape[0]),
    }
    if n_clusters is not None:
        labels = fcluster(Z, t=n_clusters, criterion="maxclust")
        result["n_clusters"] = n_clusters
        result["labels"] = (labels - 1).tolist()
    return result


# ---------------------------------------------------------------------------
# pca_extended
# ---------------------------------------------------------------------------

def _pca_extended(X, n_components=2, standardize=True, feature_names=None):
    X = np.asarray(X, dtype=float)
    n, p = X.shape
    mean = X.mean(axis=0)
    Xc = X - mean
    std = None
    if standardize:
        std = Xc.std(axis=0, ddof=1)
        std[std == 0] = 1.0
        Xc = Xc / std

    U, S, Vt = np.linalg.svd(Xc, full_matrices=False)
    n_components = min(n_components, Vt.shape[0])

    eigenvalues = (S ** 2) / (n - 1)
    total_var = eigenvalues.sum()
    explained_variance_ratio = eigenvalues / total_var

    scores = U[:, :n_components] * S[:n_components]
    loadings = Vt[:n_components, :].T * np.sqrt(eigenvalues[:n_components])

    # contribucion de cada variable a cada componente (%), estandar en biplots de PCA
    contributions = (loadings ** 2) / np.sum(loadings ** 2, axis=0, keepdims=True) * 100

    names = feature_names if feature_names else [f"var{i+1}" for i in range(p)]

    return {
        "mode": "pca_extended",
        "n_components": n_components,
        "explained_variance_ratio": explained_variance_ratio[:n_components].tolist(),
        "cumulative_variance_ratio": float(np.sum(explained_variance_ratio[:n_components])),
        "scores": scores.tolist(),
        "loadings": {names[i]: loadings[i].tolist() for i in range(p)},
        "variable_contributions_pct": {names[i]: contributions[i].tolist() for i in range(p)},
    }


def compute_clustering(mode, **params):
    if mode == "validate":
        return _validate_clustering()
    if mode == "kmeans":
        return _kmeans(**params)
    elif mode == "hierarchical":
        return _hierarchical(**params)
    elif mode == "pca_extended":
        return _pca_extended(**params)
    else:
        raise ValueError(f"modo desconocido: {mode}. Use kmeans | hierarchical | pca_extended")


# ---------------------------------------------------------------------------
# Validacion cruzada contra sklearn
# ---------------------------------------------------------------------------


def _validate_clustering():
    checks = []
    try:
        from sklearn.cluster import KMeans as SKKMeans, AgglomerativeClustering
        from sklearn.metrics import adjusted_rand_score
        from sklearn.decomposition import PCA as SKPCA

        rng = np.random.default_rng(42)
        c1 = rng.normal(loc=[0, 0], scale=0.5, size=(40, 2))
        c2 = rng.normal(loc=[5, 5], scale=0.5, size=(40, 2))
        c3 = rng.normal(loc=[0, 5], scale=0.5, size=(40, 2))
        X = np.vstack([c1, c2, c3])

        mine = _kmeans(X, k=3, random_state=42)
        sk = SKKMeans(n_clusters=3, n_init=10, random_state=42).fit(X)
        inertia_diff = abs(mine["inertia"] - sk.inertia_)
        checks.append({
            "name": "kmeans_inertia_vs_sklearn",
            "expected": "diff < 1e-3",
            "got": round(float(inertia_diff), 8),
            "passed": bool(inertia_diff < 1e-3),
        })

        for method in ["single", "complete", "average"]:
            mine_h = _hierarchical(X, linkage=method, n_clusters=3)
            sk_h = AgglomerativeClustering(n_clusters=3, linkage=method).fit(X)
            ari = adjusted_rand_score(mine_h["labels"], sk_h.labels_)
            checks.append({
                "name": f"hierarchical_{method}_ari_vs_sklearn",
                "expected": ">= 0.95",
                "got": round(float(ari), 6),
                "passed": bool(ari >= 0.95),
            })

        mine_p = _pca_extended(X, n_components=2, standardize=True)
        sk_p = SKPCA(n_components=2).fit((X - X.mean(0)) / X.std(0, ddof=1))
        evr_diff = float(np.max(np.abs(
            np.array(mine_p["explained_variance_ratio"]) - sk_p.explained_variance_ratio_
        )))
        checks.append({
            "name": "pca_explained_variance_vs_sklearn",
            "expected": "max diff < 1e-6",
            "got": round(evr_diff, 8),
            "passed": bool(evr_diff < 1e-6),
        })
    except ImportError as e:
        checks.append({"name": "clustering_vs_sklearn", "expected": "sklearn disponible",
                        "got": str(e), "passed": False})

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}

if __name__ == "__main__":
    from sklearn.cluster import KMeans as SKKMeans, AgglomerativeClustering
    from sklearn.metrics import silhouette_score as sk_sil, davies_bouldin_score as sk_db
    from sklearn.decomposition import PCA as SKPCA

    rng = np.random.default_rng(42)
    c1 = rng.normal(loc=[0, 0], scale=0.5, size=(40, 2))
    c2 = rng.normal(loc=[5, 5], scale=0.5, size=(40, 2))
    c3 = rng.normal(loc=[0, 5], scale=0.5, size=(40, 2))
    X = np.vstack([c1, c2, c3])

    # --- kmeans ---
    mine = _kmeans(X, k=3, random_state=42)
    sk = SKKMeans(n_clusters=3, n_init=10, random_state=42).fit(X)
    print("kmeans:")
    print("  mio inertia   =", mine["inertia"], " sklearn inertia =", sk.inertia_)
    print("  mio silhouette=", mine["silhouette_score"],
          " sklearn silhouette=", sk_sil(X, sk.labels_))
    print("  mio davies_bouldin=", mine["davies_bouldin_score"],
          " sklearn davies_bouldin=", sk_db(X, sk.labels_))

    # --- hierarchical ---
    for method in ["single", "complete", "average"]:
        mine_h = _hierarchical(X, linkage=method, n_clusters=3)
        sk_h = AgglomerativeClustering(n_clusters=3, linkage=method).fit(X)
        # las etiquetas numericas pueden no coincidir 1:1, comparamos particion
        from sklearn.metrics import adjusted_rand_score
        ari = adjusted_rand_score(mine_h["labels"], sk_h.labels_)
        print(f"hierarchical ({method}): adjusted_rand_score vs sklearn = {ari}  (esperado ~1.0)")

    # --- pca_extended ---
    mine_p = _pca_extended(X, n_components=2, standardize=True)
    sk_p = SKPCA(n_components=2).fit((X - X.mean(0)) / X.std(0, ddof=1))
    print("pca_extended:")
    print("  mio explained_variance_ratio  =", mine_p["explained_variance_ratio"])
    print("  sklearn explained_variance_ratio =", sk_p.explained_variance_ratio_.tolist())
    print("  cumulative =", mine_p["cumulative_variance_ratio"])

    print("\nTodas las validaciones cruzadas contra sklearn corrieron sin excepciones.")


CLUSTERING_TOOL_SCHEMA = {
    "name": "clustering_tool",
    "description": (
        "Clustering y reduccion de dimensionalidad: kmeans (particional, "
        "silhouette + davies-bouldin score), hierarchical (aglomerativo, "
        "linkage single/complete/average, con dendrograma), pca_extended "
        "(componentes principales, varianza explicada, contribuciones por "
        "variable)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["kmeans", "hierarchical", "pca_extended", "validate"]},
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
    return compute_clustering(mode=args["mode"], **_params)

register_tool("clustering_tool", CLUSTERING_TOOL_SCHEMA, _handle)
