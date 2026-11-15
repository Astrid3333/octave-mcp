"""Teoria de Pólya y Burnside para coloraciones bajo grupos de permutaciones."""

from __future__ import annotations

import itertools
from collections import Counter
from fractions import Fraction
from typing import Any

from advanced_combinatorics_common import need_int, need_list, safe_number
from tool_registry import register_tool


MAX_EXPLICIT_GROUP = 720
MAX_SYMMETRIC_DEGREE = 8


def _normalize_permutation(raw: Any, degree: int) -> tuple[int, ...]:
    if not isinstance(raw, (list, tuple)) or len(raw) != degree:
        raise ValueError(f"cada permutacion debe tener {degree} elementos")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in raw):
        raise ValueError("las permutaciones deben contener enteros")
    values = list(raw)
    if set(values) == set(range(degree)):
        return tuple(values)
    if set(values) == set(range(1, degree + 1)):
        return tuple(value - 1 for value in values)
    raise ValueError(f"la permutacion {raw!r} no es una permutacion de {degree} elementos")


def _permutations_from_args(args: dict[str, Any]) -> tuple[int, list[tuple[int, ...]], str]:
    degree = need_int(args, "n", minimum=1, required=True)
    explicit = need_list(args, "permutations")
    if explicit:
        if len(explicit) > MAX_EXPLICIT_GROUP:
            raise ValueError(f"el grupo explicito supera {MAX_EXPLICIT_GROUP} elementos")
        permutations = [_normalize_permutation(item, degree) for item in explicit]
        unique = sorted(set(permutations))
        if len(unique) != len(permutations):
            raise ValueError("las permutaciones explicitas contienen duplicados")
        return degree, unique, "explicit"
    group = args.get("group", "symmetric")
    if group == "symmetric":
        if degree > MAX_SYMMETRIC_DEGREE:
            raise ValueError(f"el grupo simmetrico admite n <= {MAX_SYMMETRIC_DEGREE}")
        return degree, list(itertools.permutations(range(degree))), "symmetric"
    if group == "cyclic":
        permutations = [tuple((index + shift) % degree for index in range(degree)) for shift in range(degree)]
        return degree, permutations, "cyclic"
    if group == "dihedral":
        rotations = [tuple((index + shift) % degree for index in range(degree)) for shift in range(degree)]
        reflections = [tuple((-index + shift) % degree for index in range(degree)) for shift in range(degree)]
        return degree, sorted(set(rotations + reflections)), "dihedral"
    raise ValueError("'group' debe ser symmetric, cyclic, dihedral o debe usarse 'permutations'")


def _cycle_type(permutation: tuple[int, ...]) -> tuple[int, ...]:
    visited = [False] * len(permutation)
    lengths: list[int] = []
    for start in range(len(permutation)):
        if visited[start]:
            continue
        length = 0
        vertex = start
        while not visited[vertex]:
            visited[vertex] = True
            vertex = permutation[vertex]
            length += 1
        lengths.append(length)
    return tuple(sorted(lengths))


def _is_group(permutations: list[tuple[int, ...]], degree: int) -> tuple[bool, list[str]]:
    identity = tuple(range(degree))
    elements = set(permutations)
    problems: list[str] = []
    if identity not in elements:
        problems.append("falta la identidad")
    for left in elements:
        for right in elements:
            composed = tuple(left[right[index]] for index in range(degree))
            if composed not in elements:
                problems.append(f"falta el producto {left} o {right}")
                return False, problems
    return not problems, problems


def _cycle_index_data(permutations: list[tuple[int, ...]]) -> tuple[dict[tuple[int, ...], int], int]:
    counter = Counter(_cycle_type(permutation) for permutation in permutations)
    return dict(sorted(counter.items())), len(permutations)


def _cycle_index_expression(
    cycle_counts: dict[tuple[int, ...], int],
    group_order: int,
) -> str:
    from sympy import Add, Rational, Symbol, together

    terms = []
    for cycle_type, multiplicity in cycle_counts.items():
        monomial = 1
        for length in cycle_type:
            monomial *= Symbol(f"x{length}")
        terms.append(Rational(multiplicity, group_order) * monomial)
    return str(together(Add(*terms))) if terms else "0"


def _compute(args: dict[str, Any]) -> dict[str, Any]:
    degree, permutations, source = _permutations_from_args(args)
    if source == "explicit":
        is_group, problems = _is_group(permutations, degree)
        if not is_group:
            raise ValueError("las permutaciones no forman un grupo: " + "; ".join(problems))
    cycle_counts, group_order = _cycle_index_data(permutations)
    expression = _cycle_index_expression(cycle_counts, group_order)
    fixed_contributions: list[dict[str, Any]] = []
    for cycle_type in sorted(cycle_counts):
        cycle_count = len(cycle_type)
        fixed_contributions.append(
            {
                "cycle_type": list(cycle_type),
                "multiplicity": cycle_counts[cycle_type],
                "fixed_colorings": safe_number(cycle_count),
            }
        )
    result: dict[str, Any] = {
        "degree": degree,
        "group": source,
        "group_order": group_order,
        "cycle_types": [
            {"cycle_type": list(cycle_type), "multiplicity": multiplicity}
            for cycle_type, multiplicity in cycle_counts.items()
        ],
        "cycle_index": expression,
        "cycle_index_coefficients": [
            {
                "cycle_type": list(cycle_type),
                "coefficient": str(Fraction(multiplicity, group_order)),
                "multiplicity": multiplicity,
            }
            for cycle_type, multiplicity in cycle_counts.items()
        ],
        "fixed_coloring_base": fixed_contributions,
    }
    mode = args.get("mode", "cycle_index")
    if mode == "count_colorings":
        colors = need_int(args, "colors", minimum=1, required=True)
        fixed_by_type = {
            cycle_type: colors ** len(cycle_type) for cycle_type in cycle_counts
        }
        total_fixed = sum(multiplicity * fixed_by_type[cycle_type] for cycle_type, multiplicity in cycle_counts.items())
        if total_fixed % group_order:
            raise ValueError("Burnside produjo un promedio no entero; el conjunto de permutaciones no es un grupo")
        result["colors"] = colors
        result["orbits"] = safe_number(total_fixed // group_order)
        result["fixed_colorings_by_cycle_type"] = [
            {
                "cycle_type": list(cycle_type),
                "fixed_colorings": safe_number(fixed_by_type[cycle_type]),
                "multiplicity": multiplicity,
            }
            for cycle_type, multiplicity in cycle_counts.items()
        ]
    return result


def _validate() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    s3 = _compute({"mode": "count_colorings", "n": 3, "group": "symmetric", "colors": 2})
    check("S3 degree 3 over 2 colors has 4 orbits", s3.get("orbits") == 4, str(s3.get("orbits")))
    expected_index = "(x1**3 + 3*x1*x2 + 2*x3)/6"
    check("S3 cycle index", s3.get("cycle_index") == expected_index, str(s3.get("cycle_index")))
    cyclic = _compute({"mode": "count_colorings", "n": 4, "group": "cyclic", "colors": 3})
    check("cyclic n=4 over 3 colors has 24 orbits", cyclic.get("orbits") == 24, str(cyclic.get("orbits")))
    dihedral = _compute({"mode": "count_colorings", "n": 4, "group": "dihedral", "colors": 3})
    check("dihedral n=4 over 3 colors has 21 orbits", dihedral.get("orbits") == 21, str(dihedral.get("orbits")))
    explicit = _compute(
        {
            "mode": "count_colorings",
            "n": 3,
            "permutations": [[0, 1, 2], [1, 0, 2]],
            "colors": 2,
        }
    )
    check("explicit S2 on 3 positions over 2 colors has 6 orbits", explicit.get("orbits") == 6, str(explicit.get("orbits")))
    try:
        invalid = _compute(
            {
                "mode": "count_colorings",
                "n": 2,
                "permutations": [[0, 1], [1, 0], [0, 1]],
                "colors": 2,
            }
        )
        rejected = "error" in invalid
    except ValueError:
        rejected = True
    check("explicit non-group is rejected", rejected)
    return {"validation_passed": all(item["passed"] for item in checks), "checks": checks}


def compute_polya_burnside(args: dict[str, Any]) -> dict[str, Any]:
    try:
        mode = args.get("mode", "validate")
        if mode == "validate":
            return _validate()
        if mode not in {"cycle_index", "count_colorings"}:
            raise ValueError("mode invalido")
        return _compute(args)
    except (ValueError, TypeError, OverflowError, MemoryError) as exc:
        return {"error": str(exc)}


POLYA_BURNSIDE_SCHEMA = {
    "name": "polya_burnside_tool",
    "description": (
        "Pólya y Burnside: índice de ciclos y conteo exacto de coloraciones "
        "módulo permutaciones. Modos cycle_index y count_colorings; grupos "
        "simétrico, cíclico, diédrico o permutaciones explícitas verificadas "
        "como grupo. Devuelve índices de ciclos, contribuciones por tipo y "
        "número de órbitas con enteros exactos."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["cycle_index", "count_colorings", "validate"],
                "default": "validate",
            },
            "n": {"type": "integer", "minimum": 1, "description": "Número de posiciones"},
            "group": {
                "type": "string",
                "enum": ["symmetric", "cyclic", "dihedral"],
                "description": "Grupo por defecto si no se dan permutaciones explícitas",
            },
            "permutations": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "integer"}},
                "description": "Elementos explícitos del grupo; 0..n-1 o 1..n",
            },
            "colors": {"type": "integer", "minimum": 1, "description": "Número de colores"},
        },
        "required": ["mode"],
    },
}


register_tool(
    name="polya_burnside_tool",
    schema=POLYA_BURNSIDE_SCHEMA,
    handler=compute_polya_burnside,
)
