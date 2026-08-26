"""
cascading_failure_tool.py

Fallos en cascada en redes de infraestructura (redes electricas, de
transporte, de comunicaciones): distinto de percolation_theory_tool
(conectividad estatica a p fijo) porque ademas modela la REDISTRIBUCION
de carga tras cada fallo, que es lo que dispara el efecto domino real en
sistemas de este tipo (Motter & Lai 2002, "Cascade-based attacks on
complex networks").

Modelo de red: se genera con Barabasi-Albert (preferential attachment,
sin depender de networkx -- implementacion propia) porque las redes de
infraestructura reales suelen ser libres de escala (pocos hubs de alto
grado, muchos nodos de bajo grado), o alternativamente Erdos-Renyi
(aleatoria uniforme) para comparar.

Modos:
  - local_redistribution_cascade: cada nodo tiene una carga inicial
    (proxy: su grado, estandar en la literatura de cascadas quando no
    se calcula betweenness centrality completo) y una capacidad
    capacity=(1+alpha)*load (alpha = margen de tolerancia). Al fallar
    un nodo (disparador), su carga se reparte en partes iguales entre
    sus vecinos activos; si un vecino supera su capacidad, tambien
    falla y su carga se redistribuye en la siguiente ronda -- efecto
    domino. Se itera hasta que no hay fallos nuevos.
  - network_robustness: mide la fraccion del componente conexo mas
    grande a medida que se remueven nodos, comparando remocion
    aleatoria vs. dirigida (los de mayor grado primero) -- el resultado
    clasico "robusta pero fragil" de las redes libres de escala
    (Albert, Jeong & Barabasi 2000, Nature): resistentes a fallos
    aleatorios, muy vulnerables a ataques dirigidos a los hubs.
  - validate: chequeos contra el comportamiento conocido de ambos
    modelos.
"""

import numpy as np


def _generate_ba_graph(n, m, seed):
    """Barabasi-Albert: arranca con una camarilla de m+1 nodos, cada
    nodo nuevo se conecta a m nodos existentes elegidos con
    probabilidad proporcional a su grado actual (preferential
    attachment), via el truco estandar de 'lista de nodos repetidos'.
    """
    rng = np.random.default_rng(seed)
    adj = {i: set() for i in range(n)}
    init_nodes = list(range(min(m + 1, n)))
    for i in init_nodes:
        for j in init_nodes:
            if i != j:
                adj[i].add(j)

    repeated_nodes = []
    for i in init_nodes:
        for j in adj[i]:
            if j > i:
                repeated_nodes.extend([i, j])

    for new_node in range(m + 1, n):
        targets = set()
        attempts = 0
        while len(targets) < m and attempts < 10000:
            candidate = repeated_nodes[rng.integers(0, len(repeated_nodes))]
            targets.add(candidate)
            attempts += 1
        for t in targets:
            adj[new_node].add(t)
            adj[t].add(new_node)
            repeated_nodes.extend([new_node, t])
    return adj


def _generate_er_graph(n, p, seed):
    """Erdos-Renyi: cada par de nodos conectado independiente con
    probabilidad p."""
    rng = np.random.default_rng(seed)
    adj = {i: set() for i in range(n)}
    rand_matrix = rng.random((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            if rand_matrix[i, j] < p:
                adj[i].add(j)
                adj[j].add(i)
    return adj


def _connected_components(adj, active):
    active = set(active)
    visited = set()
    components = []
    for node in active:
        if node in visited:
            continue
        stack = [node]
        comp = set()
        visited.add(node)
        while stack:
            u = stack.pop()
            comp.add(u)
            for v in adj[u]:
                if v in active and v not in visited:
                    visited.add(v)
                    stack.append(v)
        components.append(comp)
    return components


def _largest_component_fraction(adj, active, n_total):
    if not active:
        return 0.0
    comps = _connected_components(adj, active)
    if not comps:
        return 0.0
    return max(len(c) for c in comps) / n_total


def _mode_local_redistribution_cascade(params):
    n = int(params.get("n_nodes", 150))
    m = int(params.get("m_edges", 3))
    seed = int(params.get("seed", 42))
    alpha = float(params.get("alpha", 0.2))
    graph_type = params.get("graph_type", "ba")
    er_p = float(params.get("er_p", 0.04))
    trigger_node = params.get("trigger_node", None)

    if graph_type == "er":
        adj = _generate_er_graph(n, er_p, seed)
    else:
        adj = _generate_ba_graph(n, m, seed)

    degree = {i: len(adj[i]) for i in range(n)}
    load = {i: float(max(degree[i], 1)) for i in range(n)}
    capacity = {i: (1.0 + alpha) * load[i] for i in range(n)}

    if trigger_node is None:
        trigger_node = max(range(n), key=lambda x: degree[x])
    trigger_node = int(trigger_node)

    active = set(range(n))
    failed = {trigger_node}
    active.discard(trigger_node)

    cascade_history = [len(failed)]
    newly_failed = {trigger_node}
    steps = 0

    while newly_failed:
        steps += 1
        redistribute = {}
        for node in newly_failed:
            neighbors_active = [nb for nb in adj[node] if nb in active]
            if not neighbors_active:
                continue
            share = load[node] / len(neighbors_active)
            for nb in neighbors_active:
                redistribute[nb] = redistribute.get(nb, 0.0) + share

        for node, extra in redistribute.items():
            load[node] += extra

        newly_failed = {node for node in active if load[node] > capacity[node]}
        for node in newly_failed:
            active.discard(node)
            failed.add(node)
        cascade_history.append(len(failed))

        if steps > n + 5:
            break

    return {
        "mode": "local_redistribution_cascade",
        "n_nodes": n,
        "graph_type": graph_type,
        "alpha": alpha,
        "trigger_node": trigger_node,
        "trigger_node_degree": degree[trigger_node],
        "n_failed": len(failed),
        "fraction_failed": len(failed) / n,
        "steps": steps,
        "cascade_history": cascade_history,
        "note": (
            "load inicial usa el grado del nodo como proxy simplificado de "
            "carga (estandar cuando no se calcula betweenness centrality "
            "completo, que es O(n*m) y mas caro); alpha mayor = mas margen "
            "de capacidad = cascada mas chica."
        ),
    }


def _mode_network_robustness(params):
    n = int(params.get("n_nodes", 200))
    m = int(params.get("m_edges", 3))
    seed = int(params.get("seed", 42))
    n_steps = int(params.get("n_steps", 15))
    graph_type = params.get("graph_type", "ba")
    er_p = float(params.get("er_p", 0.03))

    if graph_type == "er":
        adj = _generate_er_graph(n, er_p, seed)
    else:
        adj = _generate_ba_graph(n, m, seed)

    degree = {i: len(adj[i]) for i in range(n)}
    rng = np.random.default_rng(seed)

    order_random = list(range(n))
    rng.shuffle(order_random)
    order_targeted = sorted(range(n), key=lambda x: -degree[x])

    removal_fractions = np.linspace(0.0, 0.9, n_steps).tolist()

    random_curve = []
    targeted_curve = []
    for f in removal_fractions:
        n_remove = int(round(f * n))
        removed_random = set(order_random[:n_remove])
        removed_targeted = set(order_targeted[:n_remove])
        active_random = set(range(n)) - removed_random
        active_targeted = set(range(n)) - removed_targeted
        random_curve.append(_largest_component_fraction(adj, active_random, n))
        targeted_curve.append(_largest_component_fraction(adj, active_targeted, n))

    # area bajo la curva (aprox trapezoidal) como resumen escalar de
    # robustez global -- metrica estandar (Schneider et al. 2011, "R")
    _trapz = getattr(np, "trapezoid", None) or np.trapz
    robustness_random = float(_trapz(random_curve, removal_fractions))
    robustness_targeted = float(_trapz(targeted_curve, removal_fractions))

    return {
        "mode": "network_robustness",
        "n_nodes": n,
        "graph_type": graph_type,
        "removal_fractions": removal_fractions,
        "largest_component_fraction_random": random_curve,
        "largest_component_fraction_targeted": targeted_curve,
        "robustness_metric_random": robustness_random,
        "robustness_metric_targeted": robustness_targeted,
        "note": (
            "robustness_metric = area bajo la curva de fraccion del "
            "componente gigante vs. fraccion removida (Schneider et al. "
            "2011); para redes libres de escala se espera "
            "robustness_metric_random > robustness_metric_targeted "
            "('robusta pero fragil', Albert, Jeong & Barabasi 2000)."
        ),
    }


def _validate():
    checks = {}
    errors = []

    # 1) Nodo aislado (grado 0) disparado como trigger: falla solo, sin
    #    cascada (no tiene vecinos a quien contagiar).
    n_iso = 20
    adj_iso = {i: set() for i in range(n_iso)}
    # conectar todos menos el nodo 0, que queda aislado a proposito
    for i in range(1, n_iso - 1):
        adj_iso[i].add(i + 1)
        adj_iso[i + 1].add(i)
    load = {i: float(max(len(adj_iso[i]), 1)) for i in range(n_iso)}
    capacity = {i: 1.2 * load[i] for i in range(n_iso)}
    active = set(range(n_iso)) - {0}
    failed = {0}
    newly_failed = {0}
    while newly_failed:
        redistribute = {}
        for node in newly_failed:
            neighbors_active = [nb for nb in adj_iso[node] if nb in active]
            if not neighbors_active:
                continue
            share = load[node] / len(neighbors_active)
            for nb in neighbors_active:
                redistribute[nb] = redistribute.get(nb, 0.0) + share
        for node, extra in redistribute.items():
            load[node] += extra
        newly_failed = {node for node in active if load[node] > capacity[node]}
        active -= newly_failed
        failed |= newly_failed
    isolated_no_cascade = (len(failed) == 1)
    checks["isolated_node_no_cascade"] = bool(isolated_no_cascade)
    if not isolated_no_cascade:
        errors.append(f"nodo aislado disparo cascada de {len(failed)} nodos (deberia fallar solo)")

    # 2) Transicion de fase en alpha: el modelo de cascada por
    #    redistribucion muestra una transicion nitida tipo todo-o-nada
    #    (no gradual) entre "cascada total" y "cascada contenida en el
    #    disparador" -- consistente con el comportamiento reportado
    #    para modelos de cascada por redistribucion de carga (Motter &
    #    Lai 2002). Se localiza el alpha critico por biseccion y se
    #    confirma que separa correctamente los dos regimenes.
    r_low_alpha = _mode_local_redistribution_cascade({"n_nodes": 150, "seed": 5, "alpha": 0.02, "trigger_node": None})
    trig = r_low_alpha["trigger_node"]
    lo, hi = 0.02, 5.0
    frac_lo = r_low_alpha["fraction_failed"]
    frac_hi = _mode_local_redistribution_cascade({"n_nodes": 150, "seed": 5, "alpha": hi, "trigger_node": trig})["fraction_failed"]
    for _ in range(12):
        mid = 0.5 * (lo + hi)
        frac_mid = _mode_local_redistribution_cascade({"n_nodes": 150, "seed": 5, "alpha": mid, "trigger_node": trig})["fraction_failed"]
        if frac_mid > 0.5 * (frac_lo + 0.007):
            lo = mid
        else:
            hi = mid
    alpha_critical = 0.5 * (lo + hi)

    below_critical = _mode_local_redistribution_cascade({"n_nodes": 150, "seed": 5, "alpha": max(alpha_critical - 0.02, 0.001), "trigger_node": trig})
    above_critical = _mode_local_redistribution_cascade({"n_nodes": 150, "seed": 5, "alpha": alpha_critical + 0.02, "trigger_node": trig})
    transition_confirmed = (below_critical["fraction_failed"] > 0.5) and (above_critical["fraction_failed"] < 0.1)
    checks["sharp_critical_alpha_transition_confirmed"] = bool(transition_confirmed)
    checks["alpha_critical_value"] = float(alpha_critical)
    checks["fraction_failed_below_critical"] = below_critical["fraction_failed"]
    checks["fraction_failed_above_critical"] = above_critical["fraction_failed"]
    checks["fraction_failed_at_alpha_0.02"] = frac_lo
    checks["fraction_failed_at_alpha_5.0"] = frac_hi
    if not transition_confirmed:
        errors.append("no se confirmo una transicion nitida en torno al alpha critico localizado")

    # 3) Alpha extremo (capacidad enorme): cascada no se propaga mas
    #    alla del nodo disparador.
    r_extreme = _mode_local_redistribution_cascade({"n_nodes": 150, "seed": 5, "alpha": 1000.0, "trigger_node": r_low_alpha["trigger_node"]})
    no_propagation = (r_extreme["n_failed"] == 1)
    checks["extreme_alpha_no_propagation"] = bool(no_propagation)
    if not no_propagation:
        errors.append(f"con alpha=1000 la cascada igual se propago a {r_extreme['n_failed']} nodos")

    # 4) Robustez: al remover 0% de nodos, el componente gigante es 1.0
    #    (toda la red conectada, o al menos el maximo posible si el
    #    grafo generado no quedo totalmente conexo).
    r_robust = _mode_network_robustness({"n_nodes": 200, "seed": 11, "n_steps": 12})
    checks["largest_component_at_zero_removal"] = r_robust["largest_component_fraction_random"][0]
    zero_removal_ok = r_robust["largest_component_fraction_random"][0] > 0.9
    checks["zero_removal_gives_near_full_component"] = bool(zero_removal_ok)
    if not zero_removal_ok:
        errors.append(f"componente gigante en remocion 0% es solo {r_robust['largest_component_fraction_random'][0]:.3f}, deberia ser casi 1.0")

    # 5) "Robusta pero fragil": para una red libre de escala, el ataque
    #    dirigido a los hubs fragmenta la red mucho mas rapido que la
    #    remocion aleatoria (Albert, Jeong & Barabasi 2000) -- se mide
    #    via el area bajo la curva (metrica de robustez global).
    robust_yet_fragile = (r_robust["robustness_metric_random"] > r_robust["robustness_metric_targeted"])
    checks["scale_free_robust_to_random_fragile_to_targeted"] = bool(robust_yet_fragile)
    checks["robustness_metric_random_value"] = r_robust["robustness_metric_random"]
    checks["robustness_metric_targeted_value"] = r_robust["robustness_metric_targeted"]
    if not robust_yet_fragile:
        errors.append(
            f"no se observo el patron robusta-pero-fragil: robustez aleatoria "
            f"{r_robust['robustness_metric_random']:.3f} <= robustez dirigida "
            f"{r_robust['robustness_metric_targeted']:.3f}"
        )

    # 6) Reproducibilidad: misma seed, mismo resultado exacto en ambos modos.
    ra = _mode_local_redistribution_cascade({"n_nodes": 100, "seed": 77, "alpha": 0.2})
    rb = _mode_local_redistribution_cascade({"n_nodes": 100, "seed": 77, "alpha": 0.2})
    reproducible_cascade = (ra["cascade_history"] == rb["cascade_history"])
    checks["reproducible_cascade_with_same_seed"] = bool(reproducible_cascade)
    if not reproducible_cascade:
        errors.append("cascada no reproducible con la misma seed")

    return {
        "mode": "validate",
        "validation_passed": len(errors) == 0,
        "checks": checks,
        "errors": errors,
    }


def compute_cascading_failure_tool(mode, params=None):
    params = params or {}
    if mode == "local_redistribution_cascade":
        return _mode_local_redistribution_cascade(params)
    elif mode == "network_robustness":
        return _mode_network_robustness(params)
    elif mode == "validate":
        return _validate()
    else:
        return {
            "error": (
                f"Modo desconocido: {mode}. Modos validos: "
                "local_redistribution_cascade, network_robustness, validate."
            )
        }


CASCADING_FAILURE_TOOL_SCHEMA = {
    "name": "cascading_failure_tool",
    "description": (
        "Fallos en cascada en redes de infraestructura, con redistribucion "
        "de carga real (distinto de percolation_theory_tool, que es "
        "conectividad estatica sin dinamica de carga). Red generada via "
        "Barabasi-Albert (libre de escala, tipica de infraestructura real) "
        "o Erdos-Renyi. mode=local_redistribution_cascade: cada nodo tiene "
        "carga=grado y capacidad=(1+alpha)*carga; al fallar un nodo "
        "disparador su carga se reparte entre vecinos activos, "
        "propagandose si algun vecino supera su capacidad. "
        "mode=network_robustness: mide la fraccion del componente conexo "
        "mas grande al remover nodos al azar vs. dirigido a los de mayor "
        "grado (resultado 'robusta pero fragil' de redes libres de "
        "escala, Albert-Jeong-Barabasi 2000)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["local_redistribution_cascade", "network_robustness", "validate"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "n_nodes": {"type": "integer", "description": "Numero de nodos de la red (default 150/200 segun modo)"},
                    "m_edges": {"type": "integer", "description": "Aristas nuevas por nodo en Barabasi-Albert (default 3)"},
                    "graph_type": {"type": "string", "enum": ["ba", "er"], "description": "Tipo de red: ba=Barabasi-Albert (libre de escala), er=Erdos-Renyi (default ba)"},
                    "er_p": {"type": "number", "description": "Probabilidad de conexion si graph_type=er (default 0.03-0.04)"},
                    "alpha": {"type": "number", "description": "Margen de tolerancia de capacidad, solo local_redistribution_cascade (default 0.2)"},
                    "trigger_node": {"type": "integer", "description": "Nodo que dispara la cascada; default null = nodo de mayor grado"},
                    "n_steps": {"type": "integer", "description": "Puntos de la curva de remocion en network_robustness (default 15)"},
                    "seed": {"type": "integer", "description": "Semilla RNG (default 42)"},
                },
            },
        },
        "required": ["mode"],
    },
}

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool(
    "cascading_failure_tool",
    CASCADING_FAILURE_TOOL_SCHEMA,
    lambda args, _f=compute_cascading_failure_tool: _f(**args),
)
