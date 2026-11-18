"""Matroides representables sobre GF(2) y poliedros de matroides."""

from __future__ import annotations

import itertools
from functools import lru_cache
from typing import Any

from advanced_combinatorics_common import need_int, need_list
from tool_registry import register_tool


MAX_MATROID_ELEMENTS = 16
MAX_POLYTOPE_ELEMENTS = 12


def _matrix(args: dict[str, Any]) -> tuple[list[list[int]], int, int]:
    raw = need_list(args, "matrix", required=True)
    if not raw:
        raise ValueError("'matrix' no puede estar vacia")
    rows: list[list[int]] = []
    width = None
    for row in raw:
        if not isinstance(row, list):
            raise ValueError("cada fila de 'matrix' debe ser una lista")
        if width is None:
            width = len(row)
        if len(row) != width:
            raise ValueError("'matrix' debe ser rectangular")
        if any(value not in {0, 1} for value in row):
            raise ValueError("'matrix' solo admite entradas 0 y 1")
        rows.append(list(row))
    if width is None or width == 0:
        raise ValueError("'matrix' debe tener al menos una columna")
    if width > MAX_MATROID_ELEMENTS:
        raise ValueError(f"la matroide admite como maximo {MAX_MATROID_ELEMENTS} elementos")
    return rows, len(rows), width


def _column_masks(rows: list[list[int]], row_count: int, column_count: int) -> list[int]:
    return [
        sum((rows[row][column] & 1) << row for row in range(row_count))
        for column in range(column_count)
    ]


def _rank_of_vectors(vectors: list[int]) -> int:
    basis: dict[int, int] = {}
    for vector in vectors:
        value = vector
        while value:
            pivot = value.bit_length() - 1
            if pivot in basis:
                value ^= basis[pivot]
            else:
                basis[pivot] = value
                break
    return len(basis)


def _mask_indices(mask: int) -> list[int]:
    indices = []
    while mask:
        lowest = mask & -mask
        indices.append(lowest.bit_length() - 1)
        mask ^= lowest
    return indices


class _MatroidData:
    def __init__(self, columns: list[int], element_count: int):
        self.columns = columns
        self.element_count = element_count

    @lru_cache(maxsize=None)
    def rank(self, mask: int) -> int:
        vectors = [self.columns[index] for index in _mask_indices(mask)]
        return _rank_of_vectors(vectors)

    def independent(self, mask: int) -> bool:
        return self.rank(mask) == mask.bit_count()

    def bases(self) -> list[int]:
        rank = self.rank((1 << self.element_count) - 1)
        return [
            mask
            for mask in range(1 << self.element_count)
            if mask.bit_count() == rank and self.independent(mask)
        ]

    def circuits(self) -> list[int]:
        circuits = []
        for mask in range(1, 1 << self.element_count):
            if self.independent(mask):
                continue
            minimal = True
            for index in _mask_indices(mask):
                if not self.independent(mask ^ (1 << index)):
                    minimal = False
                    break
            if minimal:
                circuits.append(mask)
        return circuits

    def flats(self) -> list[int]:
        flats = []
        for mask in range(1 << self.element_count):
            rank = self.rank(mask)
            closure = 0
            for element in range(self.element_count):
                if self.rank(mask | (1 << element)) == rank:
                    closure |= 1 << element
            if closure == mask:
                flats.append(mask)
        return flats

    def loops(self) -> list[int]:
        return [element for element in range(self.element_count) if self.rank(1 << element) == 0]

    def coloops(self) -> list[int]:
        full = (1 << self.element_count) - 1
        rank = self.rank(full)
        if rank == 0:
            return list(range(self.element_count))
        return [
            element
            for element in range(self.element_count)
            if self.rank(full ^ (1 << element)) == rank - 1
        ]


def _data_from_matrix(args: dict[str, Any]) -> _MatroidData:
    rows, row_count, column_count = _matrix(args)
    return _MatroidData(_column_masks(rows, row_count, column_count), column_count)


def _representable_result(args: dict[str, Any]) -> dict[str, Any]:
    data = _data_from_matrix(args)
    full = (1 << data.element_count) - 1
    bases = data.bases()
    independent_sets = [
        mask for mask in range(1 << data.element_count) if data.independent(mask)
    ]
    circuits = data.circuits()
    flats = data.flats() if data.element_count <= 14 else []
    return {
        "field": "GF(2)",
        "n": data.element_count,
        "rank": data.rank(full),
        "independent_sets": [_mask_indices(mask) for mask in independent_sets],
        "bases": [_mask_indices(mask) for mask in bases],
        "circuits": [_mask_indices(mask) for mask in circuits],
        "flats": [_mask_indices(mask) for mask in flats],
        "loops": data.loops(),
        "coloops": data.coloops(),
    }


def _uniform_data(rank: int, element_count: int) -> dict[str, Any]:
    bases = [
        list(combination)
        for combination in itertools.combinations(range(element_count), rank)
    ]
    circuits = [
        list(combination)
        for combination in itertools.combinations(range(element_count), rank + 1)
    ]
    return {
        "matroid": f"U_{{{rank},{element_count}}}",
        "n": element_count,
        "rank": rank,
        "bases": bases,
        "circuits": circuits,
        "loops": list(range(element_count)) if rank == 0 else [],
        "coloops": list(range(element_count)) if rank == element_count else [],
        "rank_function": "r(S)=min(|S|,r)",
    }


def _uniform_result(args: dict[str, Any]) -> dict[str, Any]:
    rank = need_int(args, "r", minimum=0, required=True)
    element_count = need_int(args, "n", minimum=0, maximum=MAX_MATROID_ELEMENTS, required=True)
    if rank > element_count:
        raise ValueError("'r' no puede superar 'n'")
    return _uniform_data(rank, element_count)


def _polytope_result(args: dict[str, Any]) -> dict[str, Any]:
    if args.get("uniform") is True or args.get("matrix") is None:
        rank = need_int(args, "r", minimum=0, required=True)
        element_count = need_int(args, "n", minimum=0, maximum=MAX_POLYTOPE_ELEMENTS, required=True)
        if rank > element_count:
            raise ValueError("'r' no puede superar 'n'")
        bases = _uniform_data(rank, element_count)["bases"]

        def rank_function(subset: list[int]) -> int:
            return min(len(subset), rank)

        inequalities = []
        for size in range(1, element_count + 1):
            for subset in itertools.combinations(range(element_count), size):
                inequalities.append(
                    {
                        "subset": list(subset),
                        "right_hand_side": rank_function(subset),
                        "expression": " + ".join(f"x[{element}]" for element in subset),
                    }
                )
        return {
            "matroid": f"U_{{{rank},{element_count}}}",
            "n": element_count,
            "rank": rank,
            "dimension": rank,
            "vertices": [
                {"base": base, "incidence_vector": [1 if element in base else 0 for element in range(element_count)]}
                for base in bases
            ],
            "inequalities": inequalities,
            "nonnegativity": "x[e] >= 0",
            "equality": "sum_e x[e] = %d" % rank,
            "is_hypersimplex": True,
        }
    data = _data_from_matrix(args)
    if data.element_count > MAX_POLYTOPE_ELEMENTS:
        raise ValueError(f"el poliedro admite como maximo {MAX_POLYTOPE_ELEMENTS} elementos")
    full = (1 << data.element_count) - 1
    bases = data.bases()
    inequalities = []
    for mask in range(1 << data.element_count):
        subset = _mask_indices(mask)
        inequalities.append(
            {
                "subset": subset,
                "right_hand_side": data.rank(mask),
                "expression": " + ".join(f"x[{element}]" for element in subset),
            }
        )
    return {
        "matroid": "representable over GF(2)",
        "n": data.element_count,
        "rank": data.rank(full),
        "dimension": data.rank(full),
        "vertices": [
            {
                "base": _mask_indices(mask),
                "incidence_vector": [1 if mask & (1 << element) else 0 for element in range(data.element_count)],
            }
            for mask in bases
        ],
        "inequalities": inequalities,
        "nonnegativity": "x[e] >= 0",
        "equality": f"sum_e x[e] = {data.rank(full)}",
        "is_hypersimplex": False,
    }


def _validate() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    fano_matrix = [
        [1, 0, 0, 1, 1, 0, 1],
        [0, 1, 0, 1, 0, 1, 1],
        [0, 0, 1, 0, 1, 1, 1],
    ]
    fano = _representable_result({"matrix": fano_matrix})
    check("Fano matroid has rank 3", fano["rank"] == 3, str(fano["rank"]))
    check("Fano matroid has 28 bases", len(fano["bases"]) == 28, str(len(fano["bases"])))
    uniform = _uniform_result({"r": 2, "n": 4})
    check("U_2,4 has 6 bases", len(uniform["bases"]) == 6, str(len(uniform["bases"])))
    polytope = _polytope_result({"uniform": True, "r": 2, "n": 4})
    check("U_2,4 polytope has 6 vertices", len(polytope["vertices"]) == 6)
    special = _representable_result({"matrix": [[1, 0, 0], [0, 1, 0]]})
    check("loop and coloops are detected", special["loops"] == [2] and special["coloops"] == [0, 1], str(special))
    return {"validation_passed": all(item["passed"] for item in checks), "checks": checks}


def compute_matroid(args: dict[str, Any]) -> dict[str, Any]:
    try:
        mode = args.get("mode", "validate")
        if mode == "validate":
            return _validate()
        if mode == "representable":
            return _representable_result(args)
        if mode == "uniform":
            return _uniform_result(args)
        if mode == "polytope":
            return _polytope_result(args)
        raise ValueError("mode invalido")
    except (ValueError, TypeError, OverflowError, MemoryError) as exc:
        return {"error": str(exc)}


MATROID_SCHEMA = {
    "name": "matroid_tool",
    "description": (
        "Matroides representables sobre GF(2) y matroides uniformes U(r,n): "
        "rango, conjuntos independientes, bases, circuitos, flats, loops, "
        "coloops y poliedro de bases. El poliedro devuelve vertices exactas "
        "y su descripcion matricial x(S)<=r(S), x>=0, sum x=r."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["representable", "uniform", "polytope", "validate"],
                "default": "validate",
            },
            "matrix": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
            "uniform": {"type": "boolean"},
            "r": {"type": "integer", "minimum": 0},
            "n": {"type": "integer", "minimum": 0, "maximum": 16},
        },
        "required": ["mode"],
    },
}


register_tool(
    name="matroid_tool",
    schema=MATROID_SCHEMA,
    handler=compute_matroid,
)
