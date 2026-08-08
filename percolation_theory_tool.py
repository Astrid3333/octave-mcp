#!/usr/bin/env python3
"""
percolation_theory_tool.py
Teoria de percolacion: percolacion en grilla 2D (sitio y enlace) con barrido
de probabilidad para localizar el umbral critico, percolacion en grafos
arbitrarios (relevante para redes ya construidas, ej. con network_science_tool),
y analisis de tamano de cluster (distribucion, cluster gigante, exponentes
criticos aproximados). Aplicable a conectividad de crecimiento micelial
(colonizacion como percolacion de sitios en una grilla de sustrato) y al
umbral de conductividad electrica en composites micelio-grafeno (fraccion de
carga conductora necesaria para que aparezca un camino percolante).
"""
import numpy as np
from scipy import ndimage


def _label_clusters(grid, connectivity=1):
    structure = ndimage.generate_binary_structure(2, connectivity)
    labeled, n_clusters = ndimage.label(grid, structure=structure)
    return labeled, n_clusters


def _has_spanning_cluster(labeled, n_clusters, axis="both"):
    if n_clusters == 0:
        return False, None
    top_labels = set(labeled[0, :]) - {0}
    bottom_labels = set(labeled[-1, :]) - {0}
    left_labels = set(labeled[:, 0]) - {0}
    right_labels = set(labeled[:, -1]) - {0}
    vertical = top_labels & bottom_labels
    horizontal = left_labels & right_labels
    if axis == "vertical":
        spanning = vertical
    elif axis == "horizontal":
        spanning = horizontal
    else:
        spanning = vertical | horizontal
    return len(spanning) > 0, sorted(spanning)[0] if spanning else None


def compute_site_percolation(L, p, seed=None, connectivity=1):
    rng = np.random.default_rng(seed)
    grid = rng.random((L, L)) < p
    labeled, n_clusters = _label_clusters(grid, connectivity)
    spans, spanning_label = _has_spanning_cluster(labeled, n_clusters)
    sizes = ndimage.sum(grid, labeled, range(1, n_clusters + 1)) if n_clusters > 0 else np.array([])
    giant_size = int(sizes.max()) if len(sizes) > 0 else 0
    return {
        "mode": "site_percolation", "L": L, "p": p,
        "n_occupied_sites": int(grid.sum()),
        "n_clusters": int(n_clusters),
        "cluster_sizes_sorted": sorted([int(s) for s in sizes], reverse=True)[:20],
        "giant_cluster_size": giant_size,
        "giant_cluster_fraction": round(giant_size / (L * L), 6),
        "percolates": bool(spans),
    }


def compute_bond_percolation(L, p, seed=None):
    rng = np.random.default_rng(seed)
    # une celdas vecinas segun enlaces activos independientes (horiz/vert)
    parent = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    for i in range(L):
        for j in range(L):
            parent[(i, j)] = (i, j)

    h_bonds = rng.random((L, L - 1)) < p
    v_bonds = rng.random((L - 1, L)) < p
    for i in range(L):
        for j in range(L - 1):
            if h_bonds[i, j]:
                union((i, j), (i, j + 1))
    for i in range(L - 1):
        for j in range(L):
            if v_bonds[i, j]:
                union((i, j), (i + 1, j))

    top_roots = {find((0, j)) for j in range(L)}
    bottom_roots = {find((L - 1, j)) for j in range(L)}
    left_roots = {find((i, 0)) for i in range(L)}
    right_roots = {find((i, L - 1)) for i in range(L)}
    spans = bool((top_roots & bottom_roots) or (left_roots & right_roots))

    from collections import Counter
    cluster_sizes = Counter(find((i, j)) for i in range(L) for j in range(L))
    sizes_sorted = sorted(cluster_sizes.values(), reverse=True)
    return {
        "mode": "bond_percolation", "L": L, "p": p,
        "n_clusters": len(cluster_sizes),
        "cluster_sizes_sorted": sizes_sorted[:20],
        "giant_cluster_size": sizes_sorted[0] if sizes_sorted else 0,
        "giant_cluster_fraction": round(sizes_sorted[0] / (L * L), 6) if sizes_sorted else 0.0,
        "percolates": spans,
    }


def compute_critical_threshold(L, p_min=0.3, p_max=0.8, n_p=25, n_trials=30, percolation_type="site", seed=None):
    """
    Barrido de p para estimar el umbral critico p_c: la probabilidad donde la
    fraccion de trials que percolan pasa abruptamente de 0 a 1. Para
    percolacion de sitios en grilla cuadrada 2D el valor teorico conocido es
    p_c ~ 0.5927 (Feynman/Ziff); para enlaces, p_c = 0.5 exacto. Sirve como
    benchmark de validacion del propio estimador.
    """
    rng = np.random.default_rng(seed)
    p_values = np.linspace(p_min, p_max, n_p)
    fractions = []
    for p in p_values:
        successes = 0
        for _ in range(n_trials):
            trial_seed = int(rng.integers(0, 2**31))
            if percolation_type == "site":
                r = compute_site_percolation(L, float(p), seed=trial_seed)
            else:
                r = compute_bond_percolation(L, float(p), seed=trial_seed)
            successes += r["percolates"]
        fractions.append(successes / n_trials)
    fractions = np.array(fractions)
    # p_c aproximado: interpolacion donde la fraccion cruza 0.5
    if fractions.max() < 0.5 or fractions.min() > 0.5:
        p_c_estimate = None
    else:
        idx = np.searchsorted(fractions, 0.5)
        idx = min(max(idx, 1), len(p_values) - 1)
        p0, p1 = p_values[idx - 1], p_values[idx]
        f0, f1 = fractions[idx - 1], fractions[idx]
        p_c_estimate = float(p0 + (0.5 - f0) * (p1 - p0) / (f1 - f0)) if f1 != f0 else float(p_values[idx])
    known_reference = {"site": 0.592746, "bond": 0.5}.get(percolation_type)
    return {
        "mode": "critical_threshold", "L": L, "percolation_type": percolation_type,
        "n_trials_per_p": n_trials,
        "p_values": [round(float(p), 4) for p in p_values],
        "percolation_fraction": [round(float(f), 4) for f in fractions],
        "estimated_p_c": round(p_c_estimate, 4) if p_c_estimate is not None else None,
        "known_reference_p_c": known_reference,
    }


def compute_graph_percolation(edges, p, seed=None, nodes=None):
    """
    Percolacion sobre un grafo arbitrario (no necesariamente grilla): cada
    arista se activa independientemente con probabilidad p, y se mide el
    tamano del componente gigante resultante. Compatible con redes ya
    construidas via network_science_tool.
    """
    import networkx as nx
    rng = np.random.default_rng(seed)
    G_full = nx.Graph()
    if nodes:
        G_full.add_nodes_from(nodes)
    G_full.add_edges_from(edges)
    G_perc = nx.Graph()
    G_perc.add_nodes_from(G_full.nodes())
    active_edges = [e for e in edges if rng.random() < p]
    G_perc.add_edges_from(active_edges)
    components = list(nx.connected_components(G_perc))
    sizes_sorted = sorted([len(c) for c in components], reverse=True)
    giant = sizes_sorted[0] if sizes_sorted else 0
    return {
        "mode": "graph_percolation", "p": p,
        "n_nodes": G_full.number_of_nodes(), "n_edges_total": G_full.number_of_edges(),
        "n_edges_active": len(active_edges),
        "n_components": len(components),
        "component_sizes_sorted": sizes_sorted[:20],
        "giant_component_size": giant,
        "giant_component_fraction": round(giant / G_full.number_of_nodes(), 6) if G_full.number_of_nodes() else 0.0,
    }


def compute_percolation_theory(mode, **kwargs):
    """Dispatcher unico para el tool MCP percolation_theory, segun 'mode'."""
    fns = {
        "site_percolation": compute_site_percolation,
        "bond_percolation": compute_bond_percolation,
        "critical_threshold": compute_critical_threshold,
        "graph_percolation": compute_graph_percolation,
    }
    if mode not in fns:
        raise ValueError(f"mode desconocido: {mode}")
    return fns[mode](**kwargs)


PERCOLATION_THEORY_TOOL_SCHEMA = {
    "name": "percolation_theory",
    "description": "Teoria de percolacion: percolacion de sitio y de enlace en grilla 2D, estimacion del umbral critico p_c via barrido de probabilidad, y percolacion sobre grafos arbitrarios (componente gigante). Aplicable a conectividad de crecimiento micelial y umbral de conductividad en composites micelio-grafeno.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["site_percolation", "bond_percolation", "critical_threshold", "graph_percolation"]},
            "L": {"type": "integer"}, "p": {"type": "number"}, "seed": {"type": "integer"},
            "connectivity": {"type": "integer"},
            "p_min": {"type": "number"}, "p_max": {"type": "number"}, "n_p": {"type": "integer"},
            "n_trials": {"type": "integer"}, "percolation_type": {"type": "string", "enum": ["site", "bond"]},
            "edges": {"type": "array"}, "nodes": {"type": "array"},
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    print(compute_percolation_theory(mode="site_percolation", L=50, p=0.55, seed=42))
    print(compute_percolation_theory(mode="site_percolation", L=50, p=0.65, seed=42))
    print(compute_percolation_theory(mode="bond_percolation", L=50, p=0.45, seed=42))
    print(compute_percolation_theory(mode="bond_percolation", L=50, p=0.55, seed=42))
    r = compute_percolation_theory(mode="critical_threshold", L=30, p_min=0.4, p_max=0.75, n_p=15, n_trials=20, percolation_type="site", seed=42)
    print(r)
    print(compute_percolation_theory(
        mode="graph_percolation",
        edges=[["a","b"],["b","c"],["c","d"],["d","a"],["a","c"]],
        p=0.6, seed=42,
    ))
