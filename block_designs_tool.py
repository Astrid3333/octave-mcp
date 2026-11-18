"""Disenos de bloques, planos proyectivos, MOLS y matrices de Hadamard."""

from __future__ import annotations

import itertools
from collections import Counter
from typing import Any

from advanced_combinatorics_common import need_int, need_list
from tool_registry import register_tool


MAX_FIELD_ORDER = 16


class _FiniteField:
    def __init__(self, prime: int, degree: int):
        self.prime = prime
        self.degree = degree
        self.order = prime**degree
        self.modulus = self._find_modulus() if degree > 1 else (0, 1)
        self.elements = [
            tuple((value // (prime**index)) % prime for index in range(degree))
            for value in range(self.order)
        ]

    def _find_modulus(self) -> tuple[int, ...]:
        from sympy import Poly, symbols

        variable = symbols("x")
        for lower in range(self.prime**self.degree):
            coefficients = []
            value = lower
            for _ in range(self.degree):
                coefficients.append(value % self.prime)
                value //= self.prime
            coefficients.append(1)
            polynomial = Poly.from_list(list(reversed(coefficients)), variable, modulus=self.prime)
            if polynomial.is_irreducible:
                return tuple(coefficients)
        raise ValueError(f"no se encontro un polinomio irreducible para GF({self.prime}^{self.degree})")

    def add(self, left: tuple[int, ...], right: tuple[int, ...]) -> tuple[int, ...]:
        return tuple((left[index] + right[index]) % self.prime for index in range(self.degree))

    def negate(self, value: tuple[int, ...]) -> tuple[int, ...]:
        return tuple((-coefficient) % self.prime for coefficient in value)

    def multiply(self, left: tuple[int, ...], right: tuple[int, ...]) -> tuple[int, ...]:
        product = [0] * (2 * self.degree - 1)
        for left_degree, left_coefficient in enumerate(left):
            for right_degree, right_coefficient in enumerate(right):
                product[left_degree + right_degree] = (
                    product[left_degree + right_degree] + left_coefficient * right_coefficient
                ) % self.prime
        for degree in range(2 * self.degree - 2, self.degree - 1, -1):
            coefficient = product[degree] % self.prime
            product[degree] = 0
            for lower_degree in range(self.degree):
                product[degree - self.degree + lower_degree] = (
                    product[degree - self.degree + lower_degree]
                    - coefficient * self.modulus[lower_degree]
                ) % self.prime
        return tuple(product[: self.degree])

    def power(self, value: tuple[int, ...], exponent: int) -> tuple[int, ...]:
        result = tuple(1 if index == 0 else 0 for index in range(self.degree))
        base = value
        while exponent:
            if exponent & 1:
                result = self.multiply(result, base)
            base = self.multiply(base, base)
            exponent >>= 1
        return result

    def inverse(self, value: tuple[int, ...]) -> tuple[int, ...]:
        if all(coefficient == 0 for coefficient in value):
            raise ValueError("el cero no tiene inverso")
        return self.power(value, self.order - 2)

    def encode(self, value: tuple[int, ...]) -> int:
        result = 0
        for index, coefficient in enumerate(value):
            result += coefficient * self.prime**index
        return result


def _prime_power(order: int) -> tuple[int, int]:
    for prime in range(2, order + 1):
        if order % prime:
            continue
        degree = 0
        value = order
        while value % prime == 0:
            value //= prime
            degree += 1
        if value == 1:
            return prime, degree
    raise ValueError(f"'{order}' no es una potencia prima")


def _normalize_vector(field: _FiniteField, vector: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, ...], ...]:
    for coefficient in vector:
        if any(entry != 0 for entry in coefficient):
            inverse = field.inverse(coefficient)
            return tuple(field.multiply(inverse, entry) for entry in vector)
    raise ValueError("vector cero")


def _construct_projective_plane(order: int) -> dict[str, Any]:
    if order < 2 or order > MAX_FIELD_ORDER:
        raise ValueError(f"el orden q debe estar entre 2 y {MAX_FIELD_ORDER}")
    prime, degree = _prime_power(order)
    field = _FiniteField(prime, degree)
    zero = tuple(0 for _ in range(degree))
    vectors = [
        (left, middle, right)
        for left in field.elements
        for middle in field.elements
        for right in field.elements
        if left != zero or middle != zero or right != zero
    ]
    normalized = {_normalize_vector(field, vector) for vector in vectors}
    points = sorted(normalized, key=lambda vector: tuple(field.encode(entry) for entry in vector))
    line_vectors = [
        (left, middle, right)
        for left in field.elements
        for middle in field.elements
        for right in field.elements
        if left != zero or middle != zero or right != zero
    ]
    normalized_lines = {_normalize_vector(field, vector) for vector in line_vectors}
    lines = []
    for line in sorted(normalized_lines, key=lambda vector: tuple(field.encode(entry) for entry in vector)):
        block = []
        for index, point in enumerate(points):
            value = zero
            for coefficient, coordinate in zip(line, point):
                value = field.add(value, field.multiply(coefficient, coordinate))
            if value == zero:
                block.append(index)
        lines.append(block)
    report = _verify_projective_plane(points, lines, order)
    report["points"] = [
        [field.encode(coordinate) for coordinate in point]
        for point in points
    ]
    report["blocks"] = lines
    report["field"] = {"prime": prime, "extension_degree": degree, "order": order}
    return report


def _verify_projective_plane(points: list[Any], lines: list[list[int]], order: int) -> dict[str, Any]:
    point_count = len(points)
    expected = order**2 + order + 1
    replication = Counter(index for block in lines for index in block)
    pair_counts: Counter[tuple[int, int]] = Counter()
    for block in lines:
        for left, right in itertools.combinations(sorted(set(block)), 2):
            pair_counts[(left, right)] += 1
    all_pairs = list(itertools.combinations(range(point_count), 2))
    return {
        "q": order,
        "v": point_count,
        "b": len(lines),
        "r": sorted(set(replication.values())),
        "k": sorted(set(len(block) for block in lines)),
        "lambda_values": sorted(set(pair_counts.values())),
        "parameter_equations_hold": point_count == expected
        and len(lines) == expected
        and set(replication.values()) == {order + 1}
        and set(len(block) for block in lines) == {order + 1}
        and set(pair_counts.values()) == {1}
        and len(pair_counts) == len(all_pairs),
        "is_projective_plane": point_count == expected
        and len(lines) == expected
        and set(replication.values()) == {order + 1}
        and set(len(block) for block in lines) == {order + 1}
        and set(pair_counts.values()) == {1}
        and len(pair_counts) == len(all_pairs),
    }


def _verify_bibd(args: dict[str, Any]) -> dict[str, Any]:
    v = need_int(args, "v", minimum=1, required=True)
    b = need_int(args, "b", minimum=0, required=True)
    r = need_int(args, "r", minimum=0, required=True)
    k = need_int(args, "k", minimum=1, required=True)
    lambda_value = need_int(args, "lambda", minimum=0, required=True)
    blocks = need_list(args, "blocks")
    result: dict[str, Any] = {
        "v": v,
        "b": b,
        "r": r,
        "k": k,
        "lambda": lambda_value,
        "parameter_equations": {
            "vr=bk": v * r == b * k,
            "r(k-1)=lambda(v-1)": r * (k - 1) == lambda_value * (v - 1),
        },
    }
    result["parameter_equations_hold"] = all(result["parameter_equations"].values())
    if blocks:
        normalized: list[tuple[int, ...]] = []
        for block in blocks:
            if not isinstance(block, list) or not block:
                raise ValueError("cada bloque debe ser una lista no vacia")
            if len(set(block)) != len(block):
                raise ValueError("un bloque contiene elementos repetidos")
            normalized.append(tuple(sorted(block)))
        replication = Counter(index for block in normalized for index in block)
        pair_counts: Counter[tuple[int, int]] = Counter()
        for block in normalized:
            for left, right in itertools.combinations(block, 2):
                pair_counts[(left, right)] += 1
        result["blocks_checked"] = len(normalized)
        result["block_sizes"] = sorted(set(len(block) for block in normalized))
        result["replications"] = sorted(set(replication.get(index, 0) for index in range(v)))
        result["pair_multiplicities"] = sorted(set(pair_counts.values()))
        result["is_bibd"] = (
            len(normalized) == b
            and set(len(block) for block in normalized) == {k}
            and set(replication.get(index, 0) for index in range(v)) == {r}
            and set(pair_counts.values()) == {lambda_value}
        )
    else:
        result["is_bibd"] = None
        result["note"] = "parameteres validos; faltan blocks para verificar la incidencia"
    return result


def _verify_steiner(args: dict[str, Any]) -> dict[str, Any]:
    v = need_int(args, "v", minimum=1, required=True)
    blocks = need_list(args, "blocks", required=True)
    lambda_value = need_int(args, "lambda", default=1, minimum=1)
    normalized: list[tuple[int, ...]] = []
    for block in blocks:
        if not isinstance(block, list) or len(block) != 3 or len(set(block)) != 3:
            raise ValueError("cada bloque de un sistema Steiner de grado 3 debe tener 3 elementos distintos")
        normalized.append(tuple(sorted(block)))
    pair_counts: Counter[tuple[int, int]] = Counter()
    for block in normalized:
        for left, right in itertools.combinations(block, 2):
            pair_counts[(left, right)] += 1
    replication = Counter(index for block in normalized for index in block)
    all_pairs = list(itertools.combinations(range(v), 2))
    return {
        "v": v,
        "lambda": lambda_value,
        "b": len(normalized),
        "divisibility_conditions_hold": v % 6 in {1, 3},
        "block_sizes": sorted(set(len(block) for block in normalized)),
        "replications": sorted(set(replication.get(index, 0) for index in range(v))),
        "pair_multiplicities": sorted(set(pair_counts.values())),
        "all_pairs_covered": set(pair_counts) == set(all_pairs),
        "is_steiner_system": v % 6 in {1, 3}
        and set(replication.get(index, 0) for index in range(v)) == {(v - 1) // 2}
        and set(pair_counts.values()) == {lambda_value}
        and set(pair_counts) == set(all_pairs),
    }


def _construct_mols(order: int) -> dict[str, Any]:
    prime, degree = _prime_power(order)
    field = _FiniteField(prime, degree)
    squares = []
    for slope in field.elements[:-1]:
        square = []
        for row in field.elements:
            for column in field.elements:
                square.append(field.encode(field.add(field.multiply(slope, row), column)))
        squares.append(square)
    square_count = len(squares)
    orthogonality = []
    for left_index in range(square_count):
        for right_index in range(left_index + 1, square_count):
            pairs = {
                (squares[left_index][position], squares[right_index][position])
                for position in range(order * order)
            }
            orthogonality.append(len(pairs) == order * order)
    return {
        "order": order,
        "count": square_count,
        "squares": squares,
        "mutually_orthogonal": all(orthogonality),
        "orthogonality_checks": orthogonality,
    }


def _construct_hadamard(order: int) -> dict[str, Any]:
    if order < 1 or order & (order - 1):
        raise ValueError("el orden de una matriz de Sylvester debe ser una potencia de 2")
    if order > 1024:
        raise ValueError("el orden de Hadamard esta limitado a 1024")
    matrix = [[1]]
    while len(matrix) < order:
        size = len(matrix)
        matrix = (
            [matrix[row][:] + matrix[row][:] for row in range(size)]
            + [matrix[row][:] + [-value for value in matrix[row]] for row in range(size)]
        )
    products = []
    for left in range(order):
        for right in range(order):
            products.append(sum(matrix[left][index] * matrix[right][index] for index in range(order)))
    expected_values = [order if left == right else 0 for left in range(order) for right in range(order)]
    orthogonal = products == expected_values
    return {
        "order": order,
        "matrix": matrix,
        "is_hadamard": orthogonal,
        "orthogonality": products,
    }


def _verify_hadamard(args: dict[str, Any]) -> dict[str, Any]:
    matrix = need_list(args, "matrix", required=True)
    if not matrix or any(not isinstance(row, list) for row in matrix):
        raise ValueError("'matrix' debe ser una matriz no vacia")
    order = len(matrix)
    if any(len(row) != order for row in matrix):
        raise ValueError("'matrix' debe ser cuadrada")
    if any(value not in {-1, 1} for row in matrix for value in row):
        raise ValueError("todos losentries de la matriz deben ser -1 o 1")
    products = []
    for left in range(order):
        for right in range(order):
            products.append(sum(matrix[left][index] * matrix[right][index] for index in range(order)))
    expected = [order if left == right else 0 for left in range(order) for right in range(order)]
    return {
        "order": order,
        "is_hadamard": products == expected,
        "orthogonality": products,
    }


def _validate() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    fano = _construct_projective_plane(2)
    check("Fano plane has 7 points and 7 lines", fano["v"] == 7 and fano["b"] == 7)
    check("Fano plane verifies as projective plane", fano["is_projective_plane"])
    order_four = _construct_projective_plane(4)
    check("projective plane order 4 verifies", order_four["is_projective_plane"] and order_four["v"] == 21)
    mols = _construct_mols(3)
    check("order 3 constructs 2 MOLS", mols["count"] == 2)
    check("order 3 MOLS are orthogonal", mols["mutually_orthogonal"])
    hadamard = _construct_hadamard(4)
    check("Sylvester Hadamard order 4 verifies", hadamard["is_hadamard"])
    return {"validation_passed": all(item["passed"] for item in checks), "checks": checks}


def compute_block_designs(args: dict[str, Any]) -> dict[str, Any]:
    try:
        mode = args.get("mode", "validate")
        if mode == "validate":
            return _validate()
        if mode == "verify_bibd":
            return _verify_bibd(args)
        if mode == "projective_plane":
            return _construct_projective_plane(need_int(args, "q", minimum=2, maximum=MAX_FIELD_ORDER, required=True))
        if mode == "steiner":
            if args.get("construct") == "fano":
                plane = _construct_projective_plane(2)
                blocks = plane["blocks"]
                return {
                    "v": 7,
                    "b": len(blocks),
                    "blocks": blocks,
                    "is_steiner_system": True,
                    "lambda": 1,
                }
            return _verify_steiner(args)
        if mode == "mols":
            return _construct_mols(need_int(args, "order", minimum=2, maximum=MAX_FIELD_ORDER, required=True))
        if mode == "hadamard":
            if args.get("matrix") is not None:
                return _verify_hadamard(args)
            return _construct_hadamard(need_int(args, "order", minimum=1, maximum=1024, required=True))
        raise ValueError("mode invalido")
    except (ValueError, TypeError, OverflowError, MemoryError) as exc:
        return {"error": str(exc)}


BLOCK_DESIGNS_SCHEMA = {
    "name": "block_designs_tool",
    "description": (
        "Disenos de bloques: verificacion BIBD, planos proyectivos de orden "
        "q primo-potencia, sistemas Steiner, conjuntos de cuadrados latinos "
        "mutuamente ortogonales y matrices de Hadamard. Incluye construccion "
        "exacta de planos/MOLS por campo finito y matrices de Sylvester."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["verify_bibd", "projective_plane", "steiner", "mols", "hadamard", "validate"],
                "default": "validate",
            },
            "v": {"type": "integer", "minimum": 1},
            "b": {"type": "integer", "minimum": 0},
            "r": {"type": "integer", "minimum": 0},
            "k": {"type": "integer", "minimum": 1},
            "lambda": {"type": "integer", "minimum": 0},
            "blocks": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
            "q": {"type": "integer", "minimum": 2, "maximum": 16},
            "order": {"type": "integer", "minimum": 1, "maximum": 1024},
            "construct": {"type": "string", "enum": ["fano"]},
            "matrix": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
        },
        "required": ["mode"],
    },
}


register_tool(
    name="block_designs_tool",
    schema=BLOCK_DESIGNS_SCHEMA,
    handler=compute_block_designs,
)
