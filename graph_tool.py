#!/usr/bin/env python3
"""
graph_tool.py — Algoritmia pura sobre grafos: Dijkstra, MST (Kruskal), detección de ciclos.
"""
import heapq

GRAPH_TOOL_SCHEMA = {
    "name": "compute_graph_algorithms",
    "description": (
        "Corre algoritmos clásicos de grafos: camino más corto (Dijkstra), árbol de "
        "expansión mínima (Kruskal), y detección de ciclos. Incluye presets de "
        "validación (small_weighted, disconnected, with_cycle) o acepta un grafo "
        "custom vía lista de aristas."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "preset": {
                "type": "string",
                "enum": ["small_weighted", "disconnected", "with_cycle", "custom"],
                "default": "small_weighted",
            },
            "mode": {"type": "string", "enum": ["validate"]},
            "edges": {"type": "array", "items": {"type": "array"}},
            "directed": {"type": "boolean", "default": False},
            "operation": {
                "type": "string",
                "enum": ["dijkstra", "mst", "cycle_detection", "all"],
                "default": "all",
            },
            "source": {},
        },
        "required": [],
    },
}

_PRESETS = {
    "small_weighted": {
        "edges": [
            ("A", "B", 4), ("A", "C", 2), ("B", "C", 1),
            ("B", "D", 5), ("C", "D", 8), ("C", "E", 10),
            ("D", "E", 2), ("D", "F", 6), ("E", "F", 3),
        ],
        "directed": False,
    },
    "disconnected": {
        "edges": [("A", "B", 1), ("B", "C", 2), ("X", "Y", 5)],
        "directed": False,
    },
    "with_cycle": {
        "edges": [("A", "B", 1), ("B", "C", 1), ("C", "A", 1), ("C", "D", 2)],
        "directed": False,
    },
}


class _UnionFind:
    def __init__(self, nodes):
        self.parent = {n: n for n in nodes}
        self.rank = {n: 0 for n in nodes}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        return True


def _build_adj(edges, directed):
    nodes = set()
    adj = {}
    for u, v, w in edges:
        nodes.add(u); nodes.add(v)
        adj.setdefault(u, []).append((v, w))
        if not directed:
            adj.setdefault(v, []).append((u, w))
        else:
            adj.setdefault(v, [])
    return sorted(nodes, key=str), adj


def _dijkstra(nodes, adj, source):
    dist = {n: float("inf") for n in nodes}
    prev = {n: None for n in nodes}
    dist[source] = 0
    pq = [(0, source)]
    visited = set()
    while pq:
        d, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)
        for v, w in adj.get(u, []):
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))

    paths = {}
    for n in nodes:
        if dist[n] == float("inf"):
            paths[n] = None
            continue
        path = []
        cur = n
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        paths[n] = list(reversed(path))

    return {
        "source": source,
        "distances": {n: (dist[n] if dist[n] != float("inf") else None) for n in nodes},
        "paths": paths,
    }


def _mst_kruskal(nodes, edges):
    uf = _UnionFind(nodes)
    mst_edges = []
    total_weight = 0
    for u, v, w in sorted(edges, key=lambda e: e[2]):
        if uf.union(u, v):
            mst_edges.append([u, v, w])
            total_weight += w
    n_components = len({uf.find(n) for n in nodes})
    return {
        "mst_edges": mst_edges,
        "total_weight": total_weight,
        "is_spanning_forest_only": n_components > 1,
        "n_components": n_components,
    }


def _detect_cycle(nodes, edges, directed):
    if not directed:
        uf = _UnionFind(nodes)
        for u, v, w in edges:
            if not uf.union(u, v):
                return {"has_cycle": True, "note": f"Ciclo detectado al agregar arista ({u},{v})."}
        return {"has_cycle": False, "note": "Sin ciclos (es un bosque)."}
    else:
        adj = {}
        for u, v, w in edges:
            adj.setdefault(u, []).append(v)
            adj.setdefault(v, [])
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in nodes}

        def dfs(u):
            color[u] = GRAY
            for v in adj.get(u, []):
                if color[v] == GRAY:
                    return True
                if color[v] == WHITE and dfs(v):
                    return True
            color[u] = BLACK
            return False

        for n in nodes:
            if color[n] == WHITE and dfs(n):
                return {"has_cycle": True, "note": "Ciclo dirigido detectado (DFS con back-edge)."}
        return {"has_cycle": False, "note": "Sin ciclos dirigidos (DAG)."}


def _validate_graph_algorithms() -> dict:
    """Checks contra valores calculados a mano para los 3 presets:
    small_weighted: Dijkstra desde A da distancias exactas {A:0,B:3,C:2,D:8,
    E:10,F:13} (via A-C-B=3 mas corto que A-B=4); MST (Kruskal) total_weight
    exacto=13 con 1 componente; tiene ciclo (9 aristas > 5 = n-1).
    with_cycle: triangulo A-B-C-A, has_cycle=True.
    disconnected: 2 componentes (A-B-C y X-Y), es bosque (has_cycle=False),
    MST marca is_spanning_forest_only=True."""
    checks = []

    r = compute_graph_algorithms(preset="small_weighted", operation="all")
    expected_dist = {"A": 0, "B": 3, "C": 2, "D": 8, "E": 10, "F": 13}
    got_dist = r["dijkstra"]["distances"]
    checks.append({"name": "small_weighted: Dijkstra desde A distancias exactas",
                    "passed": got_dist == expected_dist, "got": got_dist})
    checks.append({"name": "small_weighted: MST total_weight==13, 1 componente",
                    "passed": r["mst"]["total_weight"] == 13 and r["mst"]["n_components"] == 1,
                    "got": r["mst"]})
    checks.append({"name": "small_weighted: tiene ciclo (9 aristas > n-1=5)",
                    "passed": r["cycle_detection"]["has_cycle"] is True,
                    "got": r["cycle_detection"]})

    r2 = compute_graph_algorithms(preset="with_cycle", operation="cycle_detection")
    checks.append({"name": "with_cycle: triangulo A-B-C-A detectado",
                    "passed": r2["cycle_detection"]["has_cycle"] is True,
                    "got": r2["cycle_detection"]})

    r3 = compute_graph_algorithms(preset="disconnected", operation="all")
    checks.append({"name": "disconnected: 2 componentes, es bosque (sin ciclo)",
                    "passed": r3["mst"]["n_components"] == 2
                              and r3["mst"]["is_spanning_forest_only"] is True
                              and r3["cycle_detection"]["has_cycle"] is False,
                    "got": {"mst": r3["mst"], "cycle_detection": r3["cycle_detection"]}})

    return {
        "mode": "validate",
        "validation_passed": all(c["passed"] for c in checks),
        "checks": checks,
    }


def compute_graph_algorithms(
    preset="small_weighted",
    edges=None,
    directed=False,
    operation="all",
    source=None,
    mode=None,
    **kwargs,
):
    if mode == "validate":
        return _validate_graph_algorithms()
    if preset == "custom":
        if not edges:
            raise ValueError("preset='custom' requiere 'edges' (lista de [u, v, peso]).")
        edge_list = [tuple(e) for e in edges]
    else:
        if preset not in _PRESETS:
            raise ValueError(f"preset desconocido: {preset}")
        edge_list = _PRESETS[preset]["edges"]
        directed = _PRESETS[preset]["directed"]

    nodes, adj = _build_adj(edge_list, directed)
    if not nodes:
        raise ValueError("El grafo no tiene nodos.")

    src = source if source is not None else nodes[0]
    if src not in nodes:
        raise ValueError(f"source='{src}' no está en el grafo. Nodos: {nodes}")

    out = {"preset": preset, "directed": directed, "nodes": nodes, "n_edges": len(edge_list)}

    if operation in ("dijkstra", "all"):
        out["dijkstra"] = _dijkstra(nodes, adj, src)
    if operation in ("mst", "all"):
        if directed:
            out["mst"] = {"error": "MST (Kruskal) solo aplica a grafos no dirigidos."}
        else:
            out["mst"] = _mst_kruskal(nodes, edge_list)
    if operation in ("cycle_detection", "all"):
        out["cycle_detection"] = _detect_cycle(nodes, edge_list, directed)

    return out

GRAPH_ALGORITHMS_SCHEMA = {   'type': 'object',
    'properties': {   'preset': {'type': 'string'},
                      'edges': {'type': 'array'},
                      'directed': {'type': 'boolean'},
                      'operation': {'type': 'string'},
                      'source': {'type': 'string'},
                      'mode': {'type': 'string', 'enum': ['validate']}}}

try:
    from tool_registry import register_tool
    register_tool(
        name="graph_algorithms",
        schema={
        "name": "graph_algorithms",
        "description": "Corre algoritmos clasicos de grafos: Dijkstra, MST (Kruskal), deteccion de ciclos. Presets: small_weighted, disconnected, with_cycle, o custom via 'edges' [[u,v,peso],...]. mode='validate' corre un check rapido contra valores exactos calculados a mano.",
        "inputSchema": GRAPH_ALGORITHMS_SCHEMA,
    },
        handler=lambda args: compute_graph_algorithms(**args),
    )
except ImportError:
    pass

