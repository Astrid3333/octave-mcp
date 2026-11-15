"""Numeros de Ramsey, cotas y grafos de Turan."""

from __future__ import annotations

import itertools
from typing import Any

from advanced_combinatorics_common import need_int, need_list, safe_number
from tool_registry import register_tool


KNOWN_RAMSEY = {
    (2, 2): 2,
    (2, 3): 3,
    (2, 4): 4,
    (2, 5): 5,
    (2, 6): 6,
    (2, 7): 7,
    (2, 8): 8,
    (2, 9): 9,
    (3, 3): 6,
    (3, 4): 9,
    (3, 5): 14,
    (3, 6): 18,
    (3, 7): 23,
    (3, 8): 28,
    (3, 9): 36,
    (4, 4): 18,
    (4, 5): 25,
}


def _pair(left: int, right: int) -> tuple[int, int]:
    return (left, right) if left <= right else (right, left)


def _known_value(left: int, right: int) -> int | None:
    return KNOWN_RAMSEY.get(_pair(left, right))


def _recursive_upper_bound(left: int, right: int) -> int:
    if left == 1 or right == 1:
        return 1
    known_left = _known_value(left - 1, right)
    known_right = _known_value(left, right - 1)
    first = known_left if known_left is not None else _recursive_upper_bound(left - 1, right)
    second = known_right if known_right is not None else _recursive_upper_bound(left, right - 1)
    return first + second


def _bounds(left: int, right: int) -> dict[str, Any]:
    lower = (left - 1) * (right - 1) + 1
    upper = _recursive_upper_bound(left, right)
    exact = _known_value(left, right)
    return {
        "s": left,
        "t": right,
        "exact": safe_number(exact),
        "exact_known": exact is not None,
        "lower_bound": safe_number(lower),
        "upper_bound": safe_number(upper),
        "lower_bound_construction": "coloracion explicita sobre (s-1)(t-1) vertices",
        "upper_bound_method": "R(s,t) <= R(s-1,t)+R(s,t-1)",
    }


def _verify_coloring(args: dict[str, Any]) -> dict[str, Any]:
    left = need_int(args, "s", minimum=1, required=True)
    right = need_int(args, "t", minimum=1, required=True)
    coloring = need_list(args, "coloring", required=True)
    if len(coloring) > 1000:
        raise ValueError("la coloracion admite como maximo 1000 edges")
    labels: list[Any] = []
    index: dict[Any, int] = {}

    def add(label: Any) -> None:
        if label not in index:
            index[label] = len(labels)
            labels.append(label)

    edge_colors: dict[tuple[int, int], str] = {}
    for item in coloring:
        if not isinstance(item, list) or len(item) != 3:
            raise ValueError("cada elemento de coloring debe ser [u, v, color]")
        left_label, right_label, color = item
        if color not in {"red", "blue"}:
            raise ValueError("cada color debe ser 'red' o 'blue'")
        add(left_label)
        add(right_label)
        left_index = index[left_label]
        right_index = index[right_label]
        if left_index == right_index:
            raise ValueError("una edge no puede ser un loop")
        key = _pair(left_index, right_index)
        if key in edge_colors:
            raise ValueError("hay una edge repetida")
        edge_colors[key] = color
    missing = [
        (labels[left], labels[right])
        for left, right in itertools.combinations(range(len(labels)), 2)
        if _pair(left, right) not in edge_colors
    ]
    if missing:
        raise ValueError(f"la coloracion debe definir K_{len(labels)}; faltan {len(missing)} edges")
    adjacency = {"red": [set() for _ in labels], "blue": [set() for _ in labels]}
    for (left_index, right_index), color in edge_colors.items():
        adjacency[color][left_index].add(right_index)
        adjacency[color][right_index].add(left_index)

    def find_clique(color: str, target: int) -> list[int] | None:
        vertices = sorted(range(len(labels)), key=lambda vertex: (-len(adjacency[color][vertex]), vertex))
        selected: list[int] = []

        def search(start: int) -> list[int] | None:
            if len(selected) == target:
                return list(selected)
            for position in range(start, len(vertices)):
                vertex = vertices[position]
                if all(vertex in adjacency[color][other] for other in selected):
                    selected.append(vertex)
                    found = search(position + 1)
                    if found is not None:
                        return found
                    selected.pop()
            return None

        return search(0)

    red_clique = find_clique("red", left)
    blue_clique = find_clique("blue", right)
    result = {
        "v": len(labels),
        "s": left,
        "t": right,
        "red_clique_found": red_clique is not None,
        "blue_clique_found": blue_clique is not None,
        "red_clique": [labels[index] for index in red_clique] if red_clique else None,
        "blue_clique": [labels[index] for index in blue_clique] if blue_clique else None,
    }
    result["has_monochromatic_clique"] = red_clique is not None or blue_clique is not None
    return result


def _turan_graph(args: dict[str, Any]) -> dict[str, Any]:
    n = need_int(args, "n", minimum=1, required=True)
    parts = need_int(args, "r", minimum=1, required=True)
    if parts > n:
        raise ValueError("'r' no puede superar 'n'")
    sizes = [n // parts + (1 if index < n % parts else 0) for index in range(parts)]
    groups = [list(range(sum(sizes[:index]), sum(sizes[: index + 1]))) for index in range(parts)]
    edge_count = sum(
        sizes[left] * sizes[right]
        for left in range(parts)
        for right in range(left + 1, parts)
    )
    edges = []
    if n <= 60:
        for left in range(parts):
            for right in range(left + 1, parts):
                for left_vertex in groups[left]:
                    for right_vertex in groups[right]:
                        edges.append([left_vertex, right_vertex])
    return {
        "n": n,
        "r": parts,
        "forbidden_clique": parts + 1,
        "part_sizes": sizes,
        "parts": groups,
        "edge_count": edge_count,
        "extremal_edge_count": edge_count,
        "turan_graph": "T_%d(%d)" % (parts, n),
        "contains_K_%d" % (parts + 1): False,
        "edges": edges,
    }


def _validate() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    ramsey = _bounds(3, 3)
    check("R(3,3)=6", ramsey["exact"] == 6, str(ramsey))
    check("R(3,3) upper recursion gives 6", ramsey["upper_bound"] == 6)
    unknown = _bounds(5, 5)
    check("R(5,5) is not asserted exact", unknown["exact_known"] is False and unknown["exact"] is None)
    check("R(5,5) bounds are ordered", unknown["lower_bound"] <= unknown["upper_bound"])
    turan3 = _turan_graph({"n": 5, "r": 2})
    check("ex(5,K3)=6", turan3["edge_count"] == 6, str(turan3["edge_count"]))
    turan4 = _turan_graph({"n": 7, "r": 3})
    check("ex(7,K4)=16", turan4["edge_count"] == 16, str(turan4["edge_count"]))
    check("T_3(7) is complete tripartite", turan4["part_sizes"] == [3, 2, 2])
    check("T_3(7) has no K4", turan4["contains_K_4"] is False)
    return {"validation_passed": all(item["passed"] for item in checks), "checks": checks}


def compute_ramsey_extremal(args: dict[str, Any]) -> dict[str, Any]:
    try:
        mode = args.get("mode", "validate")
        if mode == "validate":
            return _validate()
        if mode in {"ramsey_number", "ramsey_bound"}:
            left = need_int(args, "s", minimum=1, required=True)
            right = need_int(args, "t", minimum=1, required=True)
            return _bounds(left, right)
        if mode == "verify_ramsey_graph":
            return _verify_coloring(args)
        if mode == "turan":
            return _turan_graph(args)
        raise ValueError("mode invalido")
    except (ValueError, TypeError, OverflowError, MemoryError) as exc:
        return {"error": str(exc)}


RAMSEY_EXTREMAL_SCHEMA = {
    "name": "ramsey_extremal_tool",
    "description": (
        "Teoria de Ramsey y extremal: valores exactos pequenos establecidos, "
        "cotas inferiores explicitas y recursivas cuando el valor exacto no "
        "se conoce, verificacion de coloraciones 2-colores y grafos de Turan "
        "T_r(n) con el conteo exacto de edges extremal."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["ramsey_number", "ramsey_bound", "verify_ramsey_graph", "turan", "validate"],
                "default": "validate",
            },
            "s": {"type": "integer", "minimum": 1},
            "t": {"type": "integer", "minimum": 1},
            "n": {"type": "integer", "minimum": 1},
            "r": {"type": "integer", "minimum": 1},
            "coloring": {
                "type": "array",
                "items": {"type": "array"},
                "description": "Triples [u,v,'red'|'blue'] para las edges de K_n",
            },
        },
        "required": ["mode"],
    },
}


register_tool(
    name="ramsey_extremal_tool",
    schema=RAMSEY_EXTREMAL_SCHEMA,
    handler=compute_ramsey_extremal,
)
