"""Utilidades compartidas para las herramientas de combinatoria avanzada."""

from __future__ import annotations

from fractions import Fraction
from typing import Any


def safe_number(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and abs(value) > 2**53:
        return str(value)
    if isinstance(value, Fraction):
        if value.denominator == 1:
            return safe_number(value.numerator)
        return f"{value.numerator}/{value.denominator}"
    if isinstance(value, dict):
        return {str(key): safe_number(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_number(item) for item in value]
    return value


def need_int(
    args: dict[str, Any],
    key: str,
    *,
    default: int | None = None,
    minimum: int = 0,
    maximum: int | None = None,
    required: bool = False,
) -> int:
    if key not in args or args[key] is None:
        if required:
            raise ValueError(f"falta el parametro '{key}'")
        if default is None:
            raise ValueError(f"falta el parametro '{key}'")
        return default
    value = args[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise ValueError(f"'{key}' debe ser entero")
    value = int(value)
    if value < minimum:
        raise ValueError(f"'{key}' debe ser >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"'{key}' debe ser <= {maximum}")
    return value


def need_list(args: dict[str, Any], key: str, *, required: bool = False) -> list[Any]:
    value = args.get(key)
    if value is None:
        if required:
            raise ValueError(f"falta el parametro '{key}'")
        return []
    if not isinstance(value, list):
        raise ValueError(f"'{key}' debe ser una lista")
    return value


def parse_graph(
    args: dict[str, Any],
    *,
    allow_loops: bool = False,
    allow_parallel: bool = False,
) -> tuple[list[Any], list[tuple[int, int]]]:
    raw_edges = need_list(args, "edges", required=True)
    raw_vertices = need_list(args, "vertices")
    labels: list[Any] = []
    seen: set[Any] = set()

    def add_label(label: Any) -> None:
        if isinstance(label, (list, dict)):
            raise ValueError("los vertices deben ser escalares JSON")
        try:
            if label in seen:
                return
            seen.add(label)
        except TypeError as exc:
            raise ValueError("los vertices deben ser escalares JSON") from exc
        labels.append(label)

    for label in raw_vertices:
        add_label(label)
    for edge in raw_edges:
        if not isinstance(edge, (list, tuple)) or len(edge) != 2:
            raise ValueError("cada edge debe ser una pareja [u, v]")
        add_label(edge[0])
        add_label(edge[1])
    if not labels:
        labels = []
    index = {label: position for position, label in enumerate(labels)}
    edges: list[tuple[int, int]] = []
    edge_set: set[tuple[int, int]] = set()
    for edge in raw_edges:
        left = index[edge[0]]
        right = index[edge[1]]
        if left == right and not allow_loops:
            raise ValueError("la graph no admite loops")
        canonical = (min(left, right), max(left, right))
        if canonical in edge_set and not allow_parallel:
            raise ValueError("la graph no admite edges paralelas")
        edge_set.add(canonical)
        edges.append(canonical)
    return labels, sorted(edges)


def adjacency_sets(vertex_count: int, edges: list[tuple[int, int]]) -> list[set[int]]:
    adjacency = [set() for _ in range(vertex_count)]
    for left, right in edges:
        if left == right:
            continue
        adjacency[left].add(right)
        adjacency[right].add(left)
    return adjacency


def connected_components(vertex_count: int, edges: list[tuple[int, int]]) -> list[list[int]]:
    adjacency = adjacency_sets(vertex_count, edges)
    components: list[list[int]] = []
    visited: set[int] = set()
    for start in range(vertex_count):
        if start in visited:
            continue
        stack = [start]
        visited.add(start)
        component = []
        while stack:
            vertex = stack.pop()
            component.append(vertex)
            for neighbor in adjacency[vertex]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))
    return components


def poly_add(left: dict[tuple[int, int], int], right: dict[tuple[int, int], int]) -> dict[tuple[int, int], int]:
    result = dict(left)
    for power, coefficient in right.items():
        result[power] = result.get(power, 0) + coefficient
    return {power: coefficient for power, coefficient in result.items() if coefficient}


def poly_sub(left: dict[tuple[int, int], int], right: dict[tuple[int, int], int]) -> dict[tuple[int, int], int]:
    result = dict(left)
    for power, coefficient in right.items():
        result[power] = result.get(power, 0) - coefficient
    return {power: coefficient for power, coefficient in result.items() if coefficient}


def poly_mul(left: dict[tuple[int, int], int], right: dict[tuple[int, int], int]) -> dict[tuple[int, int], int]:
    result: dict[tuple[int, int], int] = {}
    for (x_left, y_left), left_coefficient in left.items():
        for (x_right, y_right), right_coefficient in right.items():
            power = (x_left + x_right, y_left + y_right)
            result[power] = result.get(power, 0) + left_coefficient * right_coefficient
    return {power: coefficient for power, coefficient in result.items() if coefficient}


def poly_shift(
    polynomial: dict[tuple[int, int], int],
    x_shift: int = 0,
    y_shift: int = 0,
) -> dict[tuple[int, int], int]:
    return {
        (x_power + x_shift, y_power + y_shift): coefficient
        for (x_power, y_power), coefficient in polynomial.items()
        if coefficient
    }


def poly_to_string(polynomial: dict[tuple[int, int], int], *, variable: str = "x") -> str:
    terms: list[str] = []
    for (x_power, y_power), coefficient in sorted(
        polynomial.items(), key=lambda item: (-item[0][0], -item[0][1])
    ):
        if coefficient == 0:
            continue
        pieces: list[str] = []
        if x_power:
            pieces.append(variable if x_power == 1 else f"{variable}^{x_power}")
        if y_power:
            pieces.append("y" if y_power == 1 else f"y^{y_power}")
        body = "*".join(pieces) if pieces else "1"
        if body == "1":
            terms.append(str(coefficient) if not terms else f"+ {coefficient}")
        elif coefficient < 0:
            prefix = "-" if abs(coefficient) == 1 else f"- {abs(coefficient)}*"
            terms.append(f"{prefix}{body}")
        elif terms:
            prefix = "+ " if coefficient == 1 else f"+ {coefficient}*"
            terms.append(f"{prefix}{body}")
        else:
            prefix = "" if coefficient == 1 else f"{coefficient}*"
            terms.append(f"{prefix}{body}")
    return " ".join(terms) if terms else "0"


def poly_to_dict(polynomial: dict[tuple[int, int], int]) -> dict[str, int]:
    result: dict[str, int] = {}
    for (x_power, y_power), coefficient in sorted(polynomial.items()):
        key = poly_to_string({(x_power, y_power): coefficient}, variable="X")
        result[key] = coefficient
    return result
