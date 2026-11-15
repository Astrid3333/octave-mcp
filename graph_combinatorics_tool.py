"""Polinomios cromatico y de Tutte, matchings y emparejamientos perfectos."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from advanced_combinatorics_common import (
    adjacency_sets,
    connected_components,
    parse_graph,
    poly_add,
    poly_shift,
    poly_sub,
    poly_to_string,
    safe_number,
)
from tool_registry import register_tool


MAX_GRAPH_VERTICES = 12
MAX_GRAPH_EDGES = 14


def _graph(
    args: dict[str, Any],
    *,
    multigraph: bool = False,
) -> tuple[list[Any], list[tuple[int, int]]]:
    labels, edges = parse_graph(
        args,
        allow_loops=multigraph,
        allow_parallel=multigraph,
    )
    if len(labels) > MAX_GRAPH_VERTICES:
        raise ValueError(f"la graph admite como maximo {MAX_GRAPH_VERTICES} vertices")
    if len(edges) > MAX_GRAPH_EDGES:
        raise ValueError(f"la graph admite como maximo {MAX_GRAPH_EDGES} edges")
    return labels, edges


def _chromatic_polynomial(vertex_count: int, edges: tuple[tuple[int, int], ...]) -> dict[int, int]:
    @lru_cache(maxsize=None)
    def polynomial(count: int, edge_set: tuple[tuple[int, int], ...]) -> dict[int, int]:
        if not edge_set:
            return {count: 1}
        edge = edge_set[0]
        remaining = edge_set[1:]
        deletion = polynomial(count, remaining)
        left, right = edge
        contracted_edges = []
        for edge_left, edge_right in remaining:
            new_left = left if edge_left == right else edge_left
            new_right = left if edge_right == right else edge_right
            if new_left == new_right:
                continue
            contracted_edges.append((min(new_left, new_right), max(new_left, new_right)))
        contraction = polynomial(count - 1, tuple(sorted(set(contracted_edges))))
        return poly_sub(deletion, contraction)

    return polynomial(vertex_count, edges)


def _chromatic_expression(coefficients: dict[int, int]) -> str:
    terms = []
    for degree in sorted(coefficients, reverse=True):
        coefficient = coefficients[degree]
        if not coefficient:
            continue
        if degree == 0:
            body = "1"
        else:
            body = "x" if degree == 1 else f"x**{degree}"
        if body == "1":
            terms.append(str(coefficient) if not terms else f"+ {coefficient}")
        elif coefficient < 0:
            prefix = "-" if abs(coefficient) == 1 else f"- {abs(coefficient)}*"
            terms.append(f"{prefix}{body}")
        elif terms:
            prefix = "+" if coefficient == 1 else f"+ {coefficient}*"
            terms.append(f"{prefix}{body}")
        else:
            prefix = "" if coefficient == 1 else f"{coefficient}*"
            terms.append(f"{prefix}{body}")
    return " ".join(terms) if terms else "0"


def _chromatic_result(args: dict[str, Any]) -> dict[str, Any]:
    labels, edges = _graph(args)
    coefficients = _chromatic_polynomial(len(labels), tuple(edges))
    chromatic_number = None
    for colors in range(1, len(labels) + 1):
        value = sum(coefficient * colors**degree for degree, coefficient in coefficients.items())
        if value != 0:
            chromatic_number = colors
            break
    return {
        "vertices": labels,
        "edges": [[labels[left], labels[right]] for left, right in edges],
        "chromatic_polynomial": _chromatic_expression(coefficients),
        "coefficients": {str(degree): coefficient for degree, coefficient in sorted(coefficients.items())},
        "chromatic_number": chromatic_number,
    }


def _contract_multigraph(vertex_count: int, edges: tuple[tuple[int, int], ...], edge: tuple[int, int]) -> tuple[int, tuple[tuple[int, int], ...]]:
    left, right = edge
    keep_vertex = min(left, right)
    remove_vertex = max(left, right)
    retained = [vertex for vertex in range(vertex_count) if vertex != remove_vertex]
    relabel = {vertex: index for index, vertex in enumerate(retained)}
    contracted = []
    skipped = False
    for edge_left, edge_right in edges:
        if not skipped and edge_left == edge[0] and edge_right == edge[1]:
            skipped = True
            continue
        new_left = keep_vertex if edge_left == remove_vertex else edge_left
        new_right = keep_vertex if edge_right == remove_vertex else edge_right
        contracted.append((relabel[new_left], relabel[new_right]))
    return len(retained), tuple(sorted(contracted))


def _tutte_polynomial(vertex_count: int, edges: tuple[tuple[int, int], ...]) -> dict[tuple[int, int], int]:
    @lru_cache(maxsize=None)
    def polynomial(count: int, edge_set: tuple[tuple[int, int], ...]) -> dict[tuple[int, int], int]:
        if not edge_set:
            return {(0, 0): 1}
        loops = [edge for edge in edge_set if edge[0] == edge[1]]
        regular = tuple(edge for edge in edge_set if edge[0] != edge[1])
        if loops:
            base = polynomial(count, regular)
            return poly_shift(base, 0, len(loops))
        edge = regular[0]
        remaining = regular[1:]
        deleted_edges = tuple(sorted(remaining))
        before = len(connected_components(count, list(deleted_edges)))
        after = len(connected_components(count, list(edge_set)))
        if before > after:
            contracted_count, contracted_edges = _contract_multigraph(count, edge_set, edge)
            return poly_shift(polynomial(contracted_count, contracted_edges), 1, 0)
        deletion = polynomial(count, deleted_edges)
        contracted_count, contracted_edges = _contract_multigraph(count, edge_set, edge)
        contraction = polynomial(contracted_count, contracted_edges)
        return poly_add(deletion, contraction)

    return polynomial(vertex_count, edges)


def _tutte_result(args: dict[str, Any]) -> dict[str, Any]:
    labels, edges = _graph(args, multigraph=True)
    polynomial = _tutte_polynomial(len(labels), tuple(edges))
    return {
        "vertices": labels,
        "edges": [[labels[left], labels[right]] for left, right in edges],
        "tutte_polynomial": poly_to_string(polynomial),
        "coefficients": [
            {"x": x_power, "y": y_power, "coefficient": coefficient}
            for (x_power, y_power), coefficient in sorted(polynomial.items())
        ],
    }


def _matching_polynomial(vertex_count: int, edges: list[tuple[int, int]]) -> dict[int, int]:
    adjacency = adjacency_sets(vertex_count, edges)

    @lru_cache(maxsize=None)
    def count(mask: int) -> dict[int, int]:
        if not mask:
            return {0: 1}
        lowest = mask & -mask
        vertex = lowest.bit_length() - 1
        rest = mask ^ lowest
        result = dict(count(rest))
        for neighbor in adjacency[vertex]:
            if rest & (1 << neighbor):
                smaller = count(rest ^ (1 << neighbor))
                for size, amount in smaller.items():
                    result[size + 1] = result.get(size + 1, 0) + amount
        return {size: amount for size, amount in result.items() if amount}

    return count((1 << vertex_count) - 1)


def _matchings_result(args: dict[str, Any]) -> dict[str, Any]:
    labels, edges = _graph(args)
    coefficients = _matching_polynomial(len(labels), edges)
    perfect = coefficients.get(len(labels) // 2, 0) if len(labels) % 2 == 0 else 0
    return {
        "vertices": labels,
        "edges": [[labels[left], labels[right]] for left, right in edges],
        "matching_polynomial": " + ".join(
            f"{coefficients[size]}x**{size}" if size else str(coefficients[size])
            for size in sorted(coefficients)
        ),
        "coefficients": {str(size): coefficients[size] for size in sorted(coefficients)},
        "number_of_matchings": safe_number(sum(coefficients.values())),
        "perfect_matchings": safe_number(perfect),
    }


def _validate() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    triangle = _chromatic_result({"vertices": [0, 1, 2], "edges": [[0, 1], [1, 2], [0, 2]]})
    check("C3 chromatic polynomial", triangle["chromatic_polynomial"] == "x**3 - 3*x**2 + 2*x", triangle["chromatic_polynomial"])
    check("C3 chromatic number is 3", triangle["chromatic_number"] == 3)
    cycle4 = _chromatic_result({"vertices": [0, 1, 2, 3], "edges": [[0, 1], [1, 2], [2, 3], [0, 3]]})
    check("C4 chromatic polynomial", cycle4["chromatic_polynomial"] == "x**4 - 4*x**3 + 6*x**2 - 3*x", cycle4["chromatic_polynomial"])
    clique4 = _chromatic_result({"vertices": [0, 1, 2, 3], "edges": [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]]})
    check("K4 chromatic polynomial", clique4["chromatic_polynomial"] == "x**4 - 6*x**3 + 11*x**2 - 6*x", clique4["chromatic_polynomial"])
    check("K4 chromatic number is 4", clique4["chromatic_number"] == 4)
    tutte_triangle = _tutte_result({"vertices": [0, 1, 2], "edges": [[0, 1], [1, 2], [0, 2]]})
    check("C3 Tutte polynomial is x^2+x+y", tutte_triangle["tutte_polynomial"] == "x^2 + x + y", tutte_triangle["tutte_polynomial"])
    tree = _tutte_result({"vertices": [0, 1, 2, 3], "edges": [[0, 1], [1, 2], [2, 3]]})
    check("tree on 4 vertices has Tutte x^3", tree["tutte_polynomial"] == "x^3", tree["tutte_polynomial"])
    parallel = _tutte_result({"vertices": [0, 1], "edges": [[0, 1], [0, 1]]})
    check("two parallel edges have Tutte x+y", parallel["tutte_polynomial"] == "x + y", parallel["tutte_polynomial"])
    loop_graph = _tutte_result({"vertices": [0, 1], "edges": [[0, 0], [0, 1]]})
    check("a loop contributes y", loop_graph["tutte_polynomial"] == "x*y", loop_graph["tutte_polynomial"])
    path4 = _matchings_result({"vertices": [0, 1, 2, 3], "edges": [[0, 1], [1, 2], [2, 3]]})
    check("P4 matching polynomial", path4["coefficients"] == {"0": 1, "1": 3, "2": 1}, str(path4["coefficients"]))
    check("P4 has one perfect matching", path4["perfect_matchings"] == 1)
    cycle4_matchings = _matchings_result({"vertices": [0, 1, 2, 3], "edges": [[0, 1], [1, 2], [2, 3], [0, 3]]})
    check("C4 matching polynomial", cycle4_matchings["coefficients"] == {"0": 1, "1": 4, "2": 2}, str(cycle4_matchings["coefficients"]))
    return {"validation_passed": all(item["passed"] for item in checks), "checks": checks}


def compute_graph_combinatorics(args: dict[str, Any]) -> dict[str, Any]:
    try:
        mode = args.get("mode", "validate")
        if mode == "validate":
            return _validate()
        if mode == "chromatic_polynomial":
            return _chromatic_result(args)
        if mode == "tutte_polynomial":
            return _tutte_result(args)
        if mode == "matchings":
            return _matchings_result(args)
        raise ValueError("mode invalido")
    except (ValueError, TypeError, OverflowError, MemoryError) as exc:
        return {"error": str(exc)}


GRAPH_COMBINATORICS_SCHEMA = {
    "name": "graph_combinatorics_tool",
    "description": (
        "Combinatoria de grafos avanzada: polinomio cromatico exacto por "
        "deletion-contraction, polinomio de Tutte con bridges y loops, y "
        "conteo por DP de todos los matchings y emparejamientos perfectos. "
        "Entrada por vertices y edges [u,v]; Tutte admite loops y edges "
        "paralelas."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["chromatic_polynomial", "tutte_polynomial", "matchings", "validate"],
                "default": "validate",
            },
            "vertices": {"type": "array", "items": {}},
            "edges": {"type": "array", "items": {"type": "array", "items": {}}},
        },
        "required": ["mode"],
    },
}


register_tool(
    name="graph_combinatorics_tool",
    schema=GRAPH_COMBINATORICS_SCHEMA,
    handler=compute_graph_combinatorics,
)
