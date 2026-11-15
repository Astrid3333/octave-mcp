"""Posets, reticulos, funcion de Möbius y numeros de Whitney."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from advanced_combinatorics_common import need_list, safe_number
from tool_registry import register_tool


def _poset_data(args: dict[str, Any]) -> tuple[list[Any], list[list[bool]], list[list[int]]]:
    raw_elements = need_list(args, "elements")
    raw_relations = need_list(args, "relations")
    if not raw_relations:
        raw_relations = need_list(args, "covers")
    labels = list(raw_elements)
    index: dict[Any, int] = {}
    for position, label in enumerate(labels):
        if isinstance(label, (list, dict)):
            raise ValueError("los elementos del poset deben ser escalares JSON")
        try:
            if label in index:
                raise ValueError("'elements' contiene elementos repetidos")
            index[label] = position
        except TypeError as exc:
            raise ValueError("los elementos del poset deben ser escalares JSON") from exc

    def add(label: Any) -> None:
        if isinstance(label, (list, dict)):
            raise ValueError("los elementos del poset deben ser escalares JSON")
        try:
            if label not in index:
                index[label] = len(labels)
                labels.append(label)
        except TypeError as exc:
            raise ValueError("los elementos del poset deben ser escalares JSON") from exc
    for relation in raw_relations:
        if not isinstance(relation, (list, tuple)) or len(relation) != 2:
            raise ValueError("cada relacion debe ser una pareja [x,y] con x<=y")
        add(relation[0])
        add(relation[1])
    if not labels:
        raise ValueError("el poset necesita elementos o relaciones")
    count = len(labels)
    reach = [[False] * count for _ in range(count)]
    for position in range(count):
        reach[position][position] = True
    for relation in raw_relations:
        left = index[relation[0]]
        right = index[relation[1]]
        reach[left][right] = True
    for middle in range(count):
        for left in range(count):
            if not reach[left][middle]:
                continue
            for right in range(count):
                if reach[middle][right]:
                    reach[left][right] = True
    for left in range(count):
        for right in range(left + 1, count):
            if reach[left][right] and reach[right][left]:
                raise ValueError("las relaciones no son antisimetricas")
    predecessors = [
        [right for right in range(count) if reach[right][left] and right != left]
        for left in range(count)
    ]
    return labels, reach, predecessors


def _mobius_values(labels: list[Any], reach: list[list[bool]]) -> dict[tuple[int, int], int]:
    count = len(labels)

    @lru_cache(maxsize=None)
    def mobius(left: int, right: int) -> int:
        if left == right:
            return 1
        if not reach[left][right]:
            raise ValueError("los elementos no forman el intervalo solicitado")
        total = 0
        for middle in range(count):
            if middle != right and reach[left][middle] and reach[middle][right]:
                total += mobius(left, middle)
        return -total

    values: dict[tuple[int, int], int] = {}
    for left in range(count):
        for right in range(count):
            if reach[left][right]:
                values[(left, right)] = mobius(left, right)
    return values


def _mobius_result(args: dict[str, Any]) -> dict[str, Any]:
    labels, reach, _ = _poset_data(args)
    values = _mobius_values(labels, reach)
    interval = args.get("interval")
    selected = values
    if interval is not None:
        if not isinstance(interval, list) or len(interval) != 2:
            raise ValueError("'interval' debe ser [bottom, top]")
        index = {label: position for position, label in enumerate(labels)}
        if interval[0] not in index or interval[1] not in index:
            raise ValueError("el intervalo contiene elementos desconocidos")
        bottom = index[interval[0]]
        top = index[interval[1]]
        if not reach[bottom][top]:
            raise ValueError("bottom no es menor o igual que top")
        selected = {pair: value for pair, value in values.items() if pair[0] == bottom and pair[1] == top}
    matrix = []
    for left in range(len(labels)):
        row = []
        for right in range(len(labels)):
            row.append(values.get((left, right)))
        matrix.append(row)
    return {
        "elements": labels,
        "mobius": [
            {"x": labels[left], "y": labels[right], "mu": value}
            for (left, right), value in sorted(selected.items())
        ],
        "mobius_matrix": matrix,
    }


def _inversion_result(args: dict[str, Any]) -> dict[str, Any]:
    labels, reach, _ = _poset_data(args)
    values = need_list(args, "values", required=True)
    if len(values) != len(labels):
        raise ValueError("'values' debe tener tantos elementos como el poset")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ValueError("'values' debe contener enteros")
    mobius = _mobius_values(labels, reach)
    inverse = []
    inverse_dual = []
    for right in range(len(labels)):
        inverse.append(
            sum(mobius.get((left, right), 0) * values[left] for left in range(len(labels)) if reach[left][right])
        )
    for left in range(len(labels)):
        inverse_dual.append(
            sum(mobius.get((left, right), 0) * values[right] for right in range(len(labels)) if reach[left][right])
        )
    return {
        "elements": labels,
        "values": values,
        "inverse": safe_number(inverse),
        "inverse_dual": safe_number(inverse_dual),
    }


def _whitney_result(args: dict[str, Any]) -> dict[str, Any]:
    labels, reach, predecessors = _poset_data(args)
    ranks = [0] * len(labels)
    order = sorted(range(len(labels)), key=lambda position: (len(predecessors[position]), position))
    for position in order:
        if predecessors[position]:
            ranks[position] = max(ranks[predecessor] + 1 for predecessor in predecessors[position])
    maximum = max(ranks) if ranks else 0
    counts = [0] * (maximum + 1)
    for rank in ranks:
        counts[rank] += 1
    return {
        "elements": labels,
        "ranks": [
            {"element": labels[position], "rank": ranks[position]}
            for position in range(len(labels))
        ],
        "whitney_numbers": counts,
        "rank_generating_polynomial": " + ".join(
            f"{count}x^{rank}" if rank else str(count)
            for rank, count in enumerate(counts)
            if count
        ),
    }


def _lattice_result(args: dict[str, Any]) -> dict[str, Any]:
    labels, reach, _ = _poset_data(args)
    count = len(labels)
    meets: list[list[Any]] = []
    joins: list[list[Any]] = []
    for left in range(count):
        meet_row = []
        join_row = []
        for right in range(count):
            lower = [
                candidate
                for candidate in range(count)
                if reach[candidate][left] and reach[candidate][right]
            ]
            upper = [
                candidate
                for candidate in range(count)
                if reach[left][candidate] and reach[right][candidate]
            ]

            def greatest(candidates: list[int]) -> int | None:
                for candidate in candidates:
                    if all(reach[other][candidate] for other in candidates):
                        return candidate
                return None

            meet = greatest(lower)
            join = greatest(upper)
            if meet is None or join is None:
                raise ValueError(f"los elementos {labels[left]} y {labels[right]} no tienen meet/join")
            meet_row.append(labels[meet])
            join_row.append(labels[join])
        meets.append(meet_row)
        joins.append(join_row)
    return {
        "elements": labels,
        "is_lattice": True,
        "meets": meets,
        "joins": joins,
    }


def _validate() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    chain = _mobius_result({"elements": [0, 1, 2], "relations": [[0, 1], [1, 2]]})
    chain_values = {(item["x"], item["y"]): item["mu"] for item in chain["mobius"]}
    check("chain Möbius values are 1,-1,0", chain_values[(0, 1)] == -1 and chain_values[(1, 2)] == -1 and chain_values[(0, 2)] == 0)
    diamond = _mobius_result({"elements": [0, 1, 2, 3], "relations": [[0, 1], [0, 2], [1, 3], [2, 3]]})
    diamond_values = {(item["x"], item["y"]): item["mu"] for item in diamond["mobius"]}
    check("diamond Möbius(bottom,top)=1", diamond_values[(0, 3)] == 1, str(diamond_values[(0, 3)]))
    whitney = _whitney_result({"elements": [0, 1, 2, 3], "relations": [[0, 1], [0, 2], [1, 3], [2, 3]]})
    check("diamond Whitney numbers are [1,2,1]", whitney["whitney_numbers"] == [1, 2, 1], str(whitney["whitney_numbers"]))
    inversion = _inversion_result({"elements": [0, 1, 2], "relations": [[0, 1], [1, 2]], "values": [0, 0, 1]})
    check("Möbius inversion maps top delta to delta", inversion["inverse"] == [0, 0, 1], str(inversion["inverse"]))
    lattice = _lattice_result({"elements": [0, 1, 2, 3], "relations": [[0, 1], [0, 2], [1, 3], [2, 3]]})
    check("diamond has meet and join", lattice["is_lattice"] and lattice["meets"][1][2] == 0 and lattice["joins"][1][2] == 3)
    return {"validation_passed": all(item["passed"] for item in checks), "checks": checks}


def compute_poset_lattice(args: dict[str, Any]) -> dict[str, Any]:
    try:
        mode = args.get("mode", "validate")
        if mode == "validate":
            return _validate()
        if mode == "mobius":
            return _mobius_result(args)
        if mode == "inversion":
            return _inversion_result(args)
        if mode == "whitney":
            return _whitney_result(args)
        if mode == "lattice":
            return _lattice_result(args)
        raise ValueError("mode invalido")
    except (ValueError, TypeError, OverflowError, MemoryError) as exc:
        return {"error": str(exc)}


POSET_LATTICE_SCHEMA = {
    "name": "poset_lattice_tool",
    "description": (
        "Posets y reticulos: funcion de Möbius sobre intervalos, inversion "
        "de Möbius, numeros de Whitney por rango y verificacion de meet/join "
        "para reticulos finitos. Acepta relaciones o covers x<=y y devuelve "
        "matrices exactas."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["mobius", "inversion", "whitney", "lattice", "validate"],
                "default": "validate",
            },
            "elements": {"type": "array", "items": {}},
            "relations": {"type": "array", "items": {"type": "array", "items": {}}},
            "covers": {"type": "array", "items": {"type": "array", "items": {}}},
            "interval": {"type": "array", "items": {}},
            "values": {"type": "array", "items": {"type": "integer"}},
        },
        "required": ["mode"],
    },
}


register_tool(
    name="poset_lattice_tool",
    schema=POSET_LATTICE_SCHEMA,
    handler=compute_poset_lattice,
)
