"""
critical_infrastructure_tool.py

Analisis de resiliencia de infraestructura critica (redes de agua, energia,
transporte) modeladas como grafos. Todos los algoritmos de grafo son
implementaciones manuales (BFS, Brandes) sin dependencias externas tipo
networkx.

Modos:
  - network_redundancy_n1: identifica aristas cuya remocion desconecta el
    grafo (single point of failure a nivel de enlace).
  - cascading_failure_simulation: simula fallas en cascada por sobrecarga:
    un nodo falla cuando load > capacity, redistribuye su carga a vecinos
    activos proporcional al headroom disponible, itera hasta estabilizar.
  - load_redistribution: un solo paso de redistribucion de carga desde un
    nodo dado hacia sus vecinos.
  - critical_node_identification: betweenness centrality (algoritmo de
    Brandes, O(V*E) para grafos no ponderados) para rankear nodos por
    criticidad estructural.
  - validate: suite de 10 checks.

confidence_flag: "media" para cascading_failure_simulation (el modelo de
redistribucion proporcional a headroom es una aproximacion razonable pero
no capta todos los modos de falla reales de una red fisica); "alta" para
el resto (BFS y Brandes son resultados exactos sobre el grafo dado).
"""

import json
import sys
from collections import deque


# ---------------------------------------------------------------------------
# Motor de grafos
# ---------------------------------------------------------------------------

def _build_adjacency(nodes, edges):
    adj = {n: [] for n in nodes}
    for e in edges:
        u, v = e["from"], e["to"]
        if u not in adj or v not in adj:
            raise ValueError(f"arista referencia nodo inexistente: {u}-{v}")
        adj[u].append(v)
        adj[v].append(u)
    return adj


def _bfs_reachable(adj, start, blocked_edges=None):
    blocked_edges = blocked_edges or set()
    visited = {start}
    queue = deque([start])
    while queue:
        u = queue.popleft()
        for v in adj.get(u, []):
            key = frozenset((u, v))
            if key in blocked_edges:
                continue
            if v not in visited:
                visited.add(v)
                queue.append(v)
    return visited


def _betweenness_centrality(nodes, adj):
    """Algoritmo de Brandes (2001) para betweenness centrality exacta en
    grafos no ponderados."""
    C = {n: 0.0 for n in nodes}
    for s in nodes:
        S = []
        P = {w: [] for w in nodes}
        sigma = {w: 0 for w in nodes}
        sigma[s] = 1
        d = {w: -1 for w in nodes}
        d[s] = 0
        Q = deque([s])
        while Q:
            v = Q.popleft()
            S.append(v)
            for w in adj[v]:
                if d[w] < 0:
                    Q.append(w)
                    d[w] = d[v] + 1
                if d[w] == d[v] + 1:
                    sigma[w] += sigma[v]
                    P[w].append(v)
        delta = {w: 0.0 for w in nodes}
        while S:
            w = S.pop()
            for v in P[w]:
                delta[v] += (sigma[v] / sigma[w]) * (1 + delta[w])
            if w != s:
                C[w] += delta[w]
    # grafo no dirigido: cada par contado dos veces
    for n in nodes:
        C[n] /= 2.0
    return C


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------

def _network_redundancy_n1(params):
    nodes = params["nodes"]
    edges = params["edges"]
    if not nodes or not edges:
        raise ValueError("nodes y edges no pueden estar vacios")
    adj = _build_adjacency(nodes, edges)
    all_nodes = set(nodes)
    base_reach = _bfs_reachable(adj, nodes[0])
    base_connected = base_reach == all_nodes

    critical_edges = []
    for e in edges:
        key = frozenset((e["from"], e["to"]))
        reach = _bfs_reachable(adj, nodes[0], blocked_edges={key})
        if reach != all_nodes:
            critical_edges.append({"from": e["from"], "to": e["to"]})

    redundancy_score = 1.0 - len(critical_edges) / len(edges)
    return {
        "base_graph_connected": base_connected,
        "total_edges": len(edges),
        "critical_edges": critical_edges,
        "n_critical_edges": len(critical_edges),
        "redundancy_score": round(redundancy_score, 6),
    }


def _cascading_failure_simulation(params):
    nodes_in = params["nodes"]  # [{"id","capacity","load"}]
    edges = params["edges"]
    max_iterations = int(params.get("max_iterations", 50))

    state = {
        n["id"]: {"capacity": float(n["capacity"]), "load": float(n["load"]), "failed": False}
        for n in nodes_in
    }
    adj = {n["id"]: [] for n in nodes_in}
    for e in edges:
        adj[e["from"]].append(e["to"])
        adj[e["to"]].append(e["from"])

    initial_total_load = sum(s["load"] for s in state.values())
    history = []
    for it in range(max_iterations):
        newly_failed = [nid for nid, s in state.items() if not s["failed"] and s["load"] > s["capacity"]]
        if not newly_failed:
            break
        for nid in newly_failed:
            excess = state[nid]["load"]
            state[nid]["failed"] = True
            neighbors = [m for m in adj.get(nid, []) if not state[m]["failed"]]
            if neighbors:
                headrooms = {m: max(state[m]["capacity"] - state[m]["load"], 0.0) for m in neighbors}
                total_headroom = sum(headrooms.values())
                for m in neighbors:
                    share = (
                        excess * (headrooms[m] / total_headroom)
                        if total_headroom > 0
                        else excess / len(neighbors)
                    )
                    state[m]["load"] += share
            # si no hay vecinos activos, la carga se pierde (nodo aislado tras cascada)
        history.append({
            "iteration": it + 1,
            "newly_failed": newly_failed,
            "total_failed_so_far": sum(1 for s in state.values() if s["failed"]),
        })

    return {
        "iterations_run": len(history),
        "converged": len(history) < max_iterations,
        "history": history,
        "initial_total_load": round(initial_total_load, 6),
        "final_failed_count": sum(1 for s in state.values() if s["failed"]),
        "final_failed_nodes": [nid for nid, s in state.items() if s["failed"]],
        "final_state": {
            nid: {"capacity": s["capacity"], "load": round(s["load"], 6), "failed": s["failed"]}
            for nid, s in state.items()
        },
    }


def _load_redistribution(params):
    nodes_in = params["nodes"]
    edges = params["edges"]
    failed_node = params["failed_node"]

    state = {n["id"]: {"capacity": float(n["capacity"]), "load": float(n["load"])} for n in nodes_in}
    if failed_node not in state:
        raise ValueError(f"failed_node '{failed_node}' no existe en nodes")

    adj = {n["id"]: [] for n in nodes_in}
    for e in edges:
        adj[e["from"]].append(e["to"])
        adj[e["to"]].append(e["from"])

    excess = state[failed_node]["load"]
    neighbors = [m for m in adj.get(failed_node, []) if m != failed_node]
    if not neighbors:
        raise ValueError(f"nodo '{failed_node}' no tiene vecinos activos para redistribuir carga")

    headrooms = {m: max(state[m]["capacity"] - state[m]["load"], 0.0) for m in neighbors}
    total_headroom = sum(headrooms.values())

    redistribution = {}
    newly_overloaded = []
    total_redistributed = 0.0
    for m in neighbors:
        share = excess * (headrooms[m] / total_headroom) if total_headroom > 0 else excess / len(neighbors)
        new_load = state[m]["load"] + share
        total_redistributed += share
        redistribution[m] = {
            "share_received": round(share, 6),
            "new_load": round(new_load, 6),
            "capacity": state[m]["capacity"],
            "exceeds_capacity": new_load > state[m]["capacity"],
        }
        if new_load > state[m]["capacity"]:
            newly_overloaded.append(m)

    return {
        "failed_node": failed_node,
        "excess_redistributed": round(excess, 6),
        "total_redistributed_check": round(total_redistributed, 6),
        "redistribution": redistribution,
        "newly_overloaded": newly_overloaded,
    }


def _critical_node_identification(params):
    nodes = params["nodes"]
    edges = params["edges"]
    if not nodes:
        raise ValueError("nodes no puede estar vacio")
    adj = _build_adjacency(nodes, edges)
    C = _betweenness_centrality(nodes, adj)
    ranked = sorted(C.items(), key=lambda kv: -kv[1])
    return {
        "betweenness": {n: round(c, 6) for n, c in C.items()},
        "ranked_critical_nodes": [{"node": n, "score": round(c, 6)} for n, c in ranked],
        "most_critical_node": ranked[0][0] if ranked else None,
    }


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

def _check(name, passed, **extra):
    return {"name": name, "passed": bool(passed), **extra}


def _validate():
    checks = []

    # Grafo estrella: centro + 4 hojas
    star_nodes = ["C", "L1", "L2", "L3", "L4"]
    star_edges = [{"from": "C", "to": f"L{i}"} for i in range(1, 5)]
    bc = _critical_node_identification({"nodes": star_nodes, "edges": star_edges})
    center_score = bc["betweenness"]["C"]
    leaf_scores = [bc["betweenness"][f"L{i}"] for i in range(1, 5)]
    checks.append(_check(
        "star_graph_center_has_max_betweenness",
        center_score > max(leaf_scores),
        center_score=center_score, max_leaf_score=max(leaf_scores),
    ))
    checks.append(_check(
        "star_graph_leaves_have_zero_betweenness",
        all(s == 0.0 for s in leaf_scores),
        leaf_scores=leaf_scores,
    ))

    # Grafo lineal (cadena): toda arista es puente => todas criticas
    chain_nodes = ["A", "B", "C", "D"]
    chain_edges = [{"from": "A", "to": "B"}, {"from": "B", "to": "C"}, {"from": "C", "to": "D"}]
    n1_chain = _network_redundancy_n1({"nodes": chain_nodes, "edges": chain_edges})
    checks.append(_check(
        "chain_graph_all_edges_critical",
        n1_chain["n_critical_edges"] == len(chain_edges),
        n_critical=n1_chain["n_critical_edges"], total=len(chain_edges),
    ))
    checks.append(_check(
        "chain_graph_zero_redundancy",
        n1_chain["redundancy_score"] == 0.0,
        redundancy_score=n1_chain["redundancy_score"],
    ))

    # Triangulo (ciclo de 3): ninguna arista es critica
    tri_nodes = ["A", "B", "C"]
    tri_edges = [{"from": "A", "to": "B"}, {"from": "B", "to": "C"}, {"from": "C", "to": "A"}]
    n1_tri = _network_redundancy_n1({"nodes": tri_nodes, "edges": tri_edges})
    checks.append(_check(
        "triangle_cycle_no_critical_edges",
        n1_tri["n_critical_edges"] == 0,
        n_critical=n1_tri["n_critical_edges"],
    ))
    checks.append(_check(
        "triangle_cycle_full_redundancy",
        n1_tri["redundancy_score"] == 1.0,
        redundancy_score=n1_tri["redundancy_score"],
    ))

    # Cascada de fallas, caso 1: vecinos con headroom amplio -> solo falla N1,
    # la carga completa del nodo fallado se conserva integramente en los sobrevivientes.
    casc_nodes_ok = [
        {"id": "N1", "capacity": 10.0, "load": 15.0},
        {"id": "N2", "capacity": 100.0, "load": 5.0},
        {"id": "N3", "capacity": 100.0, "load": 5.0},
    ]
    casc_edges = [{"from": "N1", "to": "N2"}, {"from": "N1", "to": "N3"}]
    casc_ok = _cascading_failure_simulation({"nodes": casc_nodes_ok, "edges": casc_edges})
    checks.append(_check(
        "cascading_failure_stops_when_neighbors_have_headroom",
        casc_ok["converged"] and casc_ok["final_failed_count"] == 1,
        converged=casc_ok["converged"], final_failed_count=casc_ok["final_failed_count"],
    ))
    # Cuando el nodo fallado tiene todos sus vecinos activos, su carga completa
    # se transfiere a los sobrevivientes (no se pierde carga en la red).
    initial_total = sum(n["load"] for n in casc_nodes_ok)
    survivors_total = sum(s["load"] for s in casc_ok["final_state"].values() if not s["failed"])
    checks.append(_check(
        "cascading_failure_conserves_total_load",
        abs(survivors_total - initial_total) < 1e-6,
        survivors_total=round(survivors_total, 6), initial_total=round(initial_total, 6),
    ))

    # Cascada de fallas, caso 2: vecinos sin headroom suficiente -> se propaga
    casc_nodes_cascade = [
        {"id": "N1", "capacity": 10.0, "load": 15.0},
        {"id": "N2", "capacity": 10.0, "load": 5.0},
        {"id": "N3", "capacity": 10.0, "load": 5.0},
    ]
    casc_cascade = _cascading_failure_simulation({"nodes": casc_nodes_cascade, "edges": casc_edges})
    checks.append(_check(
        "cascading_failure_propagates_when_neighbors_lack_headroom",
        casc_cascade["final_failed_count"] > 1,
        final_failed_count=casc_cascade["final_failed_count"],
    ))

    # Redistribucion de carga: la suma de shares recibidos == exceso redistribuido
    lr = _load_redistribution({
        "nodes": [
            {"id": "F", "capacity": 10.0, "load": 20.0},
            {"id": "M1", "capacity": 10.0, "load": 2.0},
            {"id": "M2", "capacity": 10.0, "load": 8.0},
        ],
        "edges": [{"from": "F", "to": "M1"}, {"from": "F", "to": "M2"}],
        "failed_node": "F",
    })
    sum_shares = sum(v["share_received"] for v in lr["redistribution"].values())
    checks.append(_check(
        "load_redistribution_shares_sum_to_excess",
        abs(sum_shares - lr["excess_redistributed"]) < 1e-6,
        sum_shares=round(sum_shares, 6), excess=lr["excess_redistributed"],
    ))

    # invalid_mode_raises
    try:
        compute_critical_infrastructure("modo_inexistente", {})
        invalid_ok = False
    except ValueError:
        invalid_ok = True
    checks.append(_check("invalid_mode_raises", invalid_ok))

    return {"checks": checks, "validation_passed": all(c["passed"] for c in checks)}


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def compute_critical_infrastructure(mode, params):
    params = params or {}
    if mode == "network_redundancy_n1":
        return _network_redundancy_n1(params)
    elif mode == "cascading_failure_simulation":
        return _cascading_failure_simulation(params)
    elif mode == "load_redistribution":
        return _load_redistribution(params)
    elif mode == "critical_node_identification":
        return _critical_node_identification(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"modo desconocido: {mode}")


CRITICAL_INFRASTRUCTURE_TOOL_SCHEMA = {
    "name": "critical_infrastructure_tool",
    "description": (
        "Resiliencia de infraestructura critica modelada como grafo: "
        "network_redundancy_n1 (identifica aristas cuya remocion desconecta la red, "
        "single point of failure a nivel de enlace, via BFS), "
        "cascading_failure_simulation (falla en cascada por sobrecarga: nodo falla si "
        "load>capacity, redistribuye excedente a vecinos activos proporcional al headroom "
        "disponible, itera hasta estabilizar), "
        "load_redistribution (un paso de redistribucion de carga desde un nodo dado), "
        "critical_node_identification (betweenness centrality exacta via algoritmo de "
        "Brandes, ranking de nodos por criticidad estructural), "
        "validate (suite de 10 checks). Algoritmos de grafo manuales (BFS, Brandes), sin "
        "dependencias externas. confidence_flag 'media' en cascading_failure_simulation "
        "(modelo de redistribucion proporcional es una aproximacion), 'alta' en el resto."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"mode": {"type": "string", "enum": ["network_redundancy_n1", "cascading_failure_simulation", "load_redistribution", "critical_node_identification", "validate"], "default": "validate"}, "params": {"type": "object"}},
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        result = compute_critical_infrastructure(
            req.get("mode", "validate"), req.get("params", {})
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

def _handle(args):
    return compute_critical_infrastructure(args.get("mode"), args.get("params"))

register_tool("critical_infrastructure_tool", CRITICAL_INFRASTRUCTURE_TOOL_SCHEMA, _handle)
