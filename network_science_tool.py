#!/usr/bin/env python3
"""
network_science_tool.py
Ciencia de redes: centralidades (grado, betweenness, closeness, eigenvector,
PageRank), deteccion de comunidades (Louvain, greedy modularity, label
propagation), modelos de crecimiento (Barabasi-Albert, Erdos-Renyi,
Watts-Strogatz), y metricas generales de grafo (densidad, clustering,
componentes, diametro, camino promedio).
"""
import networkx as nx
import numpy as np


def _build_graph(edges, directed=False, weighted=False, nodes=None):
    G = nx.DiGraph() if directed else nx.Graph()
    if nodes:
        G.add_nodes_from(nodes)
    for e in edges:
        if weighted and len(e) == 3:
            G.add_edge(e[0], e[1], weight=e[2])
        else:
            G.add_edge(e[0], e[1])
    return G


def _top_n(d, n=5):
    return [{"node": k, "value": round(v, 6)} for k, v in
             sorted(d.items(), key=lambda x: x[1], reverse=True)[:n]]


def compute_centrality(edges, directed=False, weighted=False, measures=None, nodes=None, top_n=5):
    G = _build_graph(edges, directed, weighted, nodes)
    if measures is None:
        measures = ["degree", "betweenness", "closeness", "eigenvector", "pagerank"]
    w = "weight" if weighted else None
    out = {}
    if "degree" in measures:
        out["degree"] = dict(G.degree())
    if "betweenness" in measures:
        out["betweenness"] = nx.betweenness_centrality(G, weight=w)
    if "closeness" in measures:
        out["closeness"] = nx.closeness_centrality(G, distance=w)
    if "eigenvector" in measures:
        try:
            out["eigenvector"] = nx.eigenvector_centrality(G, weight=w, max_iter=1000)
        except nx.PowerIterationFailedConvergence:
            out["eigenvector"] = {n: None for n in G.nodes()}
    if "pagerank" in measures:
        out["pagerank"] = nx.pagerank(G, weight=w)
    top = {m: _top_n(v, top_n) for m, v in out.items() if all(isinstance(x, (int, float)) for x in v.values())}
    return {
        "mode": "centrality",
        "n_nodes": G.number_of_nodes(), "n_edges": G.number_of_edges(),
        "measures": {m: {k: (round(v, 6) if isinstance(v, float) else v) for k, v in d.items()} for m, d in out.items()},
        "top_ranked": top,
    }


def compute_community_detection(edges, method="louvain", directed=False, weighted=False,
                                 resolution=1.0, seed=None, nodes=None):
    G = _build_graph(edges, directed, weighted, nodes)
    w = "weight" if weighted else None
    if method == "louvain":
        comms = nx.community.louvain_communities(G, weight=w, resolution=resolution, seed=seed)
    elif method == "greedy_modularity":
        comms = list(nx.community.greedy_modularity_communities(G, weight=w, resolution=resolution))
    elif method == "label_propagation":
        comms = list(nx.community.label_propagation_communities(G))
    else:
        raise ValueError(f"method desconocido: {method}")
    modularity = nx.community.modularity(G, comms, weight=w)
    comms_sorted = sorted([sorted(list(c)) for c in comms], key=len, reverse=True)
    return {
        "mode": "community_detection", "method": method,
        "n_nodes": G.number_of_nodes(), "n_edges": G.number_of_edges(),
        "n_communities": len(comms_sorted),
        "modularity": round(modularity, 6),
        "communities": comms_sorted,
        "community_sizes": [len(c) for c in comms_sorted],
    }


def compute_growth_model(model, n, m=None, p=None, k=None, seed=None):
    """
    Modelos generativos de red. Barabasi-Albert produce conectividad
    preferencial (scale-free, exponente de ley de potencia ~ -3 para la
    distribucion de grados) - el modelo relevante para redes comerciales
    historicas donde nodos "hub" (ciudades/oasis en la Ruta de la Seda)
    acumulan conexiones desproporcionadamente. Erdos-Renyi y Watts-Strogatz
    sirven como null models de comparacion (aleatorio puro vs. small-world).
    """
    if model == "barabasi_albert":
        if m is None:
            raise ValueError("barabasi_albert requiere m (aristas nuevas por nodo)")
        G = nx.barabasi_albert_graph(n, m, seed=seed)
    elif model == "erdos_renyi":
        if p is None:
            raise ValueError("erdos_renyi requiere p (probabilidad de arista)")
        G = nx.erdos_renyi_graph(n, p, seed=seed)
    elif model == "watts_strogatz":
        if k is None or p is None:
            raise ValueError("watts_strogatz requiere k (vecinos) y p (rewiring)")
        G = nx.watts_strogatz_graph(n, k, p, seed=seed)
    else:
        raise ValueError(f"model desconocido: {model}")

    degrees = np.array([d for _, d in G.degree()])
    result = {
        "mode": "growth_model", "model": model,
        "n_nodes": G.number_of_nodes(), "n_edges": G.number_of_edges(),
        "mean_degree": round(float(degrees.mean()), 6),
        "degree_std": round(float(degrees.std()), 6),
        "max_degree": int(degrees.max()),
        "avg_clustering": round(nx.average_clustering(G), 6),
    }
    if model == "barabasi_albert":
        # ajuste log-log crudo del exponente de la ley de potencia P(k) ~ k^-gamma
        vals, counts = np.unique(degrees, return_counts=True)
        mask = vals > 0
        if mask.sum() > 2:
            slope, _ = np.polyfit(np.log(vals[mask]), np.log(counts[mask] / counts[mask].sum()), 1)
            result["estimated_power_law_exponent"] = round(-float(slope), 4)
    if nx.is_connected(G):
        result["diameter"] = nx.diameter(G)
        result["avg_shortest_path_length"] = round(nx.average_shortest_path_length(G), 6)
    else:
        result["n_connected_components"] = nx.number_connected_components(G)
    return result


def compute_graph_metrics(edges, directed=False, weighted=False, nodes=None):
    G = _build_graph(edges, directed, weighted, nodes)
    degrees = np.array([d for _, d in G.degree()])
    result = {
        "mode": "graph_metrics",
        "n_nodes": G.number_of_nodes(), "n_edges": G.number_of_edges(),
        "density": round(nx.density(G), 6),
        "degree_mean": round(float(degrees.mean()), 6),
        "degree_std": round(float(degrees.std()), 6),
        "degree_min": int(degrees.min()), "degree_max": int(degrees.max()),
    }
    if not directed:
        result["avg_clustering"] = round(nx.average_clustering(G), 6)
        result["transitivity"] = round(nx.transitivity(G), 6)
        result["n_connected_components"] = nx.number_connected_components(G)
        largest = max(nx.connected_components(G), key=len)
        result["largest_component_size"] = len(largest)
        if nx.number_connected_components(G) == 1:
            result["diameter"] = nx.diameter(G)
            result["avg_shortest_path_length"] = round(nx.average_shortest_path_length(G), 6)
    else:
        result["n_strongly_connected_components"] = nx.number_strongly_connected_components(G)
        result["n_weakly_connected_components"] = nx.number_weakly_connected_components(G)
    return result


def compute_network_science(mode, **kwargs):
    """Dispatcher unico para el tool MCP network_science, segun 'mode'."""
    fns = {
        "centrality": compute_centrality,
        "community_detection": compute_community_detection,
        "growth_model": compute_growth_model,
        "graph_metrics": compute_graph_metrics,
    }
    if mode not in fns:
        raise ValueError(f"mode desconocido: {mode}")
    return fns[mode](**kwargs)


NETWORK_SCIENCE_TOOL_SCHEMA = {
    "name": "network_science",
    "description": "Ciencia de redes: centralidades (grado, betweenness, closeness, eigenvector, PageRank), deteccion de comunidades (Louvain, greedy modularity, label propagation), modelos de crecimiento (Barabasi-Albert, Erdos-Renyi, Watts-Strogatz), y metricas generales de grafo (densidad, clustering, componentes, diametro).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["centrality", "community_detection", "growth_model", "graph_metrics"]},
            "edges": {"type": "array"},
            "nodes": {"type": "array"},
            "directed": {"type": "boolean"}, "weighted": {"type": "boolean"},
            "measures": {"type": "array"}, "top_n": {"type": "integer"},
            "method": {"type": "string", "enum": ["louvain", "greedy_modularity", "label_propagation"]},
            "resolution": {"type": "number"}, "seed": {"type": "integer"},
            "model": {"type": "string", "enum": ["barabasi_albert", "erdos_renyi", "watts_strogatz"]},
            "n": {"type": "integer"}, "m": {"type": "integer"}, "p": {"type": "number"}, "k": {"type": "integer"},
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    # red de juguete estilo Ruta de la Seda: hubs (Samarcanda, Kashgar) vs nodos perifericos
    edges_toy = [
        ["Samarcanda", "Kashgar"], ["Samarcanda", "Bujara"], ["Samarcanda", "Merv"],
        ["Kashgar", "Dunhuang"], ["Kashgar", "Kokand"], ["Bujara", "Merv"],
        ["Merv", "Nishapur"], ["Dunhuang", "Chang'an"], ["Nishapur", "Bagdad"],
        ["Bagdad", "Damasco"], ["Damasco", "Antioquia"], ["Antioquia", "Constantinopla"],
    ]
    print(compute_network_science(mode="centrality", edges=edges_toy, top_n=3))
    print(compute_network_science(mode="community_detection", edges=edges_toy, method="louvain", seed=42))
    print(compute_network_science(mode="graph_metrics", edges=edges_toy))
    print(compute_network_science(mode="growth_model", model="barabasi_albert", n=200, m=2, seed=42))
    print(compute_network_science(mode="growth_model", model="erdos_renyi", n=200, p=0.02, seed=42))
