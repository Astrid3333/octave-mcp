#!/usr/bin/env python3
"""
circuit_tool.py

Analisis Nodal Modificado (MNA - Modified Nodal Analysis) de circuitos
resistivos con fuentes de voltaje y corriente independientes.

Sistema resuelto:

    [ G   B ] [V]   [i]
    [ B^T 0 ] [J] = [e]

- G (n x n): stamp de conductancias (n = nodos no-tierra, nodo 0 = tierra).
- B (n x m): acoplamiento fuente de voltaje <-> nodo. Convencion (verificada
  a mano contra un divisor de voltaje simple):
      B[nodo_positivo][k] = -1
      B[nodo_negativo][k] = +1
  Con esta convencion, la corriente resuelta J_k es positiva cuando la
  fuente ENTREGA potencia (corriente sale por el terminal +). La convencion
  opuesta (+1/-1) da J_k con el signo invertido y rompe la conservacion de
  energia en el chequeo de validacion.
- i (n): corriente inyectada en cada nodo por fuentes de corriente.
- e (m): valor de cada fuente de voltaje.

Fuentes de corriente: (nodo_desde, nodo_hacia, I) significa que una
corriente I fluye DESDE nodo_desde HACIA nodo_hacia a traves de la fuente
(el circuito externo recibe +I en nodo_hacia y -I en nodo_desde).

Topologias degeneradas (fuentes de voltaje en conflicto, lazos de solo
fuentes de voltaje, nodos que dejan la matriz singular) se detectan via
rango de matriz ANTES de resolver, y levantan ValueError con un mensaje
especifico en vez de dejar que numpy tire una excepcion generica o, peor,
devuelva una solucion basura via lstsq.
"""

import random

import numpy as np


class CircuitError(ValueError):
    """Error de topologia de circuito (degenerada) o de parametros invalidos."""


def _idx(node):
    # nodo 0 = tierra, no entra en la matriz; nodos 1..n -> indices 0..n-1
    return node - 1


def _build_mna(num_nodes, resistors, voltage_sources, current_sources):
    n = num_nodes
    m = len(voltage_sources)

    if n <= 0:
        raise CircuitError("num_nodes debe ser >= 1 (nodos no-tierra, sin contar el nodo 0)")

    G = np.zeros((n, n))
    i_vec = np.zeros(n)
    B = np.zeros((n, m))
    e_vec = np.zeros(m)

    for (a, b, R) in resistors:
        if a == b:
            raise CircuitError(f"Resistor con ambos terminales en el mismo nodo ({a}) -> cortocircuito trivial, no aporta ecuacion util")
        if R <= 0:
            raise CircuitError(f"Resistencia invalida (<=0): R={R} entre nodos {a}-{b}")
        g = 1.0 / R
        if a != 0:
            G[_idx(a), _idx(a)] += g
        if b != 0:
            G[_idx(b), _idx(b)] += g
        if a != 0 and b != 0:
            G[_idx(a), _idx(b)] -= g
            G[_idx(b), _idx(a)] -= g

    for (a, b, I) in current_sources:
        if b != 0:
            i_vec[_idx(b)] += I
        if a != 0:
            i_vec[_idx(a)] -= I

    C = np.zeros((m, n))

    for k, (p, neg, Vs) in enumerate(voltage_sources):
        if p == neg:
            raise CircuitError(f"Fuente de voltaje {k} conecta el nodo {p} consigo mismo")
        # B: coeficiente de J_k en las filas de KCL (nodo positivo/negativo).
        # Convencion verificada a mano: B[pos]=-1, B[neg]=+1 da J_k > 0 cuando
        # la fuente entrega potencia (ver docstring del modulo).
        if p != 0:
            B[_idx(p), k] = -1.0
        if neg != 0:
            B[_idx(neg), k] = 1.0
        # C: fila de la propia fuente, V_p - V_neg = Vs. Esta ecuacion es fija
        # (no es B^T) - independiente del signo elegido arriba para B.
        if p != 0:
            C[k, _idx(p)] = 1.0
        if neg != 0:
            C[k, _idx(neg)] = -1.0
        e_vec[k] = Vs

    if m > 0:
        D = np.zeros((m, m))
        A = np.block([[G, B], [C, D]])
        z = np.concatenate([i_vec, e_vec])
    else:
        A = G
        z = i_vec

    return A, z, n, m, i_vec


def solve_nodal_analysis(num_nodes, resistors, voltage_sources, current_sources,
                          rank_tol=1e-10):
    """
    Resuelve el circuito. Lanza CircuitError si la topologia es degenerada
    (matriz MNA singular: fuentes de voltaje en conflicto, lazo cerrado de
    solo fuentes de voltaje, nodo flotante sin ningun camino resistivo/fuente
    a tierra, etc.) en vez de devolver una solucion invalida.
    """
    A, z, n, m, i_vec = _build_mna(num_nodes, resistors, voltage_sources, current_sources)

    rank = np.linalg.matrix_rank(A, tol=rank_tol)
    if rank < A.shape[0]:
        raise CircuitError(
            f"Topologia degenerada: matriz MNA singular (rank {rank} de {A.shape[0]}). "
            "Causas tipicas: fuentes de voltaje en conflicto o en lazo cerrado, "
            "nodo sin ningun camino (resistor o fuente) hacia el resto del circuito."
        )

    x = np.linalg.solve(A, z)
    V = x[:n]
    J = x[n:] if m > 0 else np.array([])

    V_full = np.concatenate([[0.0], V])  # V_full[0] = tierra = 0

    p_dissipated = 0.0
    for (a, b, R) in resistors:
        p_dissipated += (V_full[a] - V_full[b]) ** 2 / R

    p_voltage_sources = float(sum(Vs * Jk for (_, _, Vs), Jk in zip(voltage_sources, J)))
    p_current_sources = float(np.dot(V, i_vec))
    p_delivered = p_voltage_sources + p_current_sources

    denom = max(abs(p_dissipated), abs(p_delivered), 1e-12)
    error_pct = abs(p_delivered - p_dissipated) / denom * 100.0

    return {
        "node_voltages": {str(k + 1): float(v) for k, v in enumerate(V)},
        "voltage_source_currents": [float(j) for j in J],
        "power_dissipated_resistors": p_dissipated,
        "power_delivered_voltage_sources": p_voltage_sources,
        "power_delivered_current_sources": p_current_sources,
        "power_delivered_total": p_delivered,
        "energy_conservation_error_pct": float(error_pct),
        "energy_conserved": bool(error_pct < 1e-6),
    }


# ---------------------------------------------------------------------------
# Validacion
# ---------------------------------------------------------------------------

def _validate_voltage_divider():
    """V1 --R1-- node1 --R2-- tierra, fuente Vs entre node1... probamos el
    caso mas simple primero: fuente directamente sobre un resistor a tierra."""
    Vs, R = 9.0, 470.0
    res = solve_nodal_analysis(
        num_nodes=1,
        resistors=[(1, 0, R)],
        voltage_sources=[(1, 0, Vs)],
        current_sources=[],
    )
    V1 = res["node_voltages"]["1"]
    J0 = res["voltage_source_currents"][0]
    expected_I = Vs / R
    return {
        "V1": V1, "V1_expected": Vs,
        "J": J0, "J_expected": expected_I,
        "error_pct_V": float(abs(V1 - Vs) / Vs * 100.0),
        "error_pct_J": float(abs(J0 - expected_I) / expected_I * 100.0),
        "energy_conserved": res["energy_conserved"],
        "passed": bool(abs(V1 - Vs) / Vs < 1e-9
                        and abs(J0 - expected_I) / expected_I < 1e-9
                        and res["energy_conserved"]),
    }


def _validate_two_resistor_divider():
    """Divisor de voltaje clasico: Vs -- R1 -- node1 -- R2 -- tierra."""
    Vs, R1, R2 = 12.0, 1000.0, 2000.0
    # node1 = nodo intermedio, node2 = terminal + de la fuente
    res = solve_nodal_analysis(
        num_nodes=2,
        resistors=[(2, 1, R1), (1, 0, R2)],
        voltage_sources=[(2, 0, Vs)],
        current_sources=[],
    )
    V1 = res["node_voltages"]["1"]
    expected_V1 = Vs * R2 / (R1 + R2)
    return {
        "V1": V1, "V1_expected": expected_V1,
        "error_pct": float(abs(V1 - expected_V1) / expected_V1 * 100.0),
        "energy_conserved": res["energy_conserved"],
        "passed": bool(abs(V1 - expected_V1) / expected_V1 < 1e-9
                        and res["energy_conserved"]),
    }


def _validate_current_source():
    """Fuente de corriente I inyectada en un nodo con un solo resistor a tierra:
    V = I*R por Ley de Ohm."""
    I, R = 0.05, 330.0
    res = solve_nodal_analysis(
        num_nodes=1,
        resistors=[(1, 0, R)],
        voltage_sources=[],
        current_sources=[(0, 1, I)],
    )
    V1 = res["node_voltages"]["1"]
    expected_V1 = I * R
    return {
        "V1": V1, "V1_expected": expected_V1,
        "error_pct": float(abs(V1 - expected_V1) / expected_V1 * 100.0),
        "energy_conserved": res["energy_conserved"],
        "passed": bool(abs(V1 - expected_V1) / expected_V1 < 1e-9
                        and res["energy_conserved"]),
    }


def _validate_degenerate_detection():
    """Dos fuentes de voltaje distintas forzando el mismo nodo -> debe
    levantar CircuitError, no devolver un resultado numerico."""
    try:
        solve_nodal_analysis(
            num_nodes=1,
            resistors=[(1, 0, 100.0)],
            voltage_sources=[(1, 0, 5.0), (1, 0, 9.0)],
            current_sources=[],
        )
        return {"passed": False, "detail": "No se detecto la topologia degenerada (deberia haber lanzado CircuitError)"}
    except CircuitError as e:
        return {"passed": True, "detail": str(e)}


def _random_circuit(rng, n_nodes, n_resistors, n_vsources, n_isources):
    resistors = [(rng.randint(0, n_nodes), rng.randint(0, n_nodes), rng.uniform(10, 1000))
                 for _ in range(n_resistors)]
    resistors = [(a, b, R) for (a, b, R) in resistors if a != b]
    voltage_sources = [(rng.randint(1, n_nodes), rng.randint(0, n_nodes), rng.uniform(-15, 15))
                        for _ in range(n_vsources)]
    voltage_sources = [(p, neg, Vs) for (p, neg, Vs) in voltage_sources if p != neg]
    current_sources = [(rng.randint(0, n_nodes), rng.randint(0, n_nodes), rng.uniform(-2, 2))
                        for _ in range(n_isources)]
    return resistors, voltage_sources, current_sources


def _stress_test(n_trials=200, seed=42):
    rng = random.Random(seed)
    n_passed = 0
    n_skipped_degenerate = 0
    worst = {"error_pct": 0.0}
    failures = []

    for trial in range(n_trials):
        n_nodes = rng.randint(2, 6)
        resistors, voltage_sources, current_sources = _random_circuit(
            rng, n_nodes,
            n_resistors=rng.randint(2, 6),
            n_vsources=rng.randint(0, 2),
            n_isources=rng.randint(0, 2),
        )
        if not resistors:
            n_skipped_degenerate += 1
            continue
        try:
            res = solve_nodal_analysis(n_nodes, resistors, voltage_sources, current_sources)
        except CircuitError:
            n_skipped_degenerate += 1
            continue

        err = res["energy_conservation_error_pct"]
        if err > worst["error_pct"]:
            worst = {
                "trial": trial, "error_pct": err, "n_nodes": n_nodes,
                "resistors": resistors, "voltage_sources": voltage_sources,
                "current_sources": current_sources,
            }
        if res["energy_conserved"]:
            n_passed += 1
        else:
            failures.append({"trial": trial, "error_pct": err})

    return {
        "n_trials": n_trials,
        "n_passed": n_passed,
        "n_skipped_degenerate": n_skipped_degenerate,
        "n_failed": len(failures),
        "worst_case_error_pct": worst["error_pct"],
        "failures": failures[:5],
        "passed": len(failures) == 0,
    }


def validate(params=None):
    params = params or {}
    n_trials = int(params.get("stress_test_trials", 200))

    checks = {
        "single_source_direct": _validate_voltage_divider(),
        "two_resistor_voltage_divider": _validate_two_resistor_divider(),
        "current_source_ohms_law": _validate_current_source(),
        "degenerate_topology_detection": _validate_degenerate_detection(),
        "energy_conservation_stress_test": _stress_test(n_trials=n_trials),
    }
    validation_passed = all(c["passed"] for c in checks.values())
    return {"mode": "validate", **checks, "validation_passed": validation_passed}


# ---------------------------------------------------------------------------
# Dispatch (mismo patron que el resto de octave-mcp)
# ---------------------------------------------------------------------------

def handle_circuit_tool(arguments):
    mode = arguments.get("mode", "validate")
    params = arguments.get("params") or {}

    if mode == "validate":
        return validate(params)

    if mode == "nodal_analysis":
        try:
            num_nodes = int(params["num_nodes"])
            resistors = [tuple(r) for r in params.get("resistors", [])]
            voltage_sources = [tuple(v) for v in params.get("voltage_sources", [])]
            current_sources = [tuple(c) for c in params.get("current_sources", [])]
        except KeyError as e:
            raise CircuitError(f"Falta parametro requerido: {e}")
        result = solve_nodal_analysis(num_nodes, resistors, voltage_sources, current_sources)
        return {"mode": "nodal_analysis", **result}

    if mode == "stress_test":
        n_trials = int(params.get("n_trials", 500))
        seed = int(params.get("seed", 42))
        return {"mode": "stress_test", **_stress_test(n_trials=n_trials, seed=seed)}

    raise CircuitError(f"Modo desconocido para circuit_tool: {mode}")


def compute_circuit_tool(mode="validate", params=None):
    """Wrapper con la misma firma que compute_acoustics_tool(mode, params),
    para wirear circuit_tool en server.py con el mismo patron de dispatch."""
    return handle_circuit_tool({"mode": mode, "params": params or {}})


CIRCUIT_TOOL_SCHEMA = {
    "name": "circuit_tool",
    "description": (
        "Analisis nodal modificado (MNA) de circuitos resistivos con fuentes de "
        "voltaje y corriente independientes. mode='validate' corre casos analiticos "
        "conocidos (divisor de voltaje, Ley de Ohm con fuente de corriente, deteccion "
        "de topologia degenerada) y un stress test de conservacion de energia sobre "
        "circuitos aleatorios. mode='nodal_analysis' resuelve un circuito dado: "
        "num_nodes (nodos no-tierra, nodo 0 = tierra), resistors=[[a,b,R],...], "
        "voltage_sources=[[nodo_pos,nodo_neg,V],...], current_sources=[[nodo_desde,nodo_hacia,I],...]. "
        "mode='stress_test' corre n_trials circuitos aleatorios y reporta estadisticas "
        "de conservacion de energia."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["validate", "nodal_analysis", "stress_test"],
                "default": "validate",
            },
            "params": {
                "type": "object",
                "description": "Parametros especificos del modo (ver descripcion de la tool).",
            },
        },
    },
}


if __name__ == "__main__":
    import json
    print(json.dumps(validate(), ensure_ascii=False, indent=2))
