"""Combinatoria de palabras, tableaux de Young, RSK y numeros de Kostka."""

from __future__ import annotations

import itertools
import math
from collections import Counter
from functools import lru_cache
from typing import Any

from advanced_combinatorics_common import need_list, safe_number
from tool_registry import register_tool


MAX_SHAPE_SIZE = 60


def _shape(args: dict[str, Any]) -> list[int]:
    raw = need_list(args, "shape", required=True)
    shape = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("'shape' debe contener enteros no negativos")
        shape.append(value)
    while shape and shape[-1] == 0:
        shape.pop()
    if any(left < right for left, right in zip(shape, shape[1:])):
        raise ValueError("'shape' debe ser no creciente")
    if sum(shape) > MAX_SHAPE_SIZE:
        raise ValueError(f"el tamano del shape supera {MAX_SHAPE_SIZE}")
    return shape


def _hook_matrix(shape: list[int]) -> list[list[int]]:
    matrix = []
    for row, length in enumerate(shape):
        row_hooks = []
        for column in range(length):
            arm = length - column - 1
            leg = sum(1 for lower_length in shape[row + 1 :] if lower_length > column)
            row_hooks.append(arm + leg + 1)
        matrix.append(row_hooks)
    return matrix


def _standard_count(shape: list[int], hooks: list[list[int]]) -> int:
    size = sum(shape)
    hook_product = math.prod(hook for row in hooks for hook in row)
    return math.factorial(size) // hook_product


def _conjugate(shape: list[int]) -> list[int]:
    if not shape:
        return []
    return [sum(1 for length in shape if length > column) for column in range(shape[0])]


def _content(args: dict[str, Any]) -> tuple[int, ...]:
    raw = need_list(args, "content", required=True)
    if not raw:
        raise ValueError("'content' no puede estar vacia")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in raw):
        raise ValueError("'content' debe contener multiplicidades no negativas")
    return tuple(raw)


def _count_sstyt(shape: list[int], content: tuple[int, ...]) -> int:
    size = sum(shape)
    if sum(content) != size:
        raise ValueError("la suma de 'content' debe coincidir con el tamano del shape")
    symbols = len(content)

    @lru_cache(maxsize=None)
    def count_rows(row_index: int, previous: tuple[int, ...], remaining: tuple[int, ...]) -> int:
        if row_index == len(shape):
            return 1 if not any(remaining) else 0
        length = shape[row_index]
        total = 0
        for row in itertools.combinations_with_replacement(range(1, symbols + 1), length):
            if any(row[index] <= previous[index] for index in range(min(length, len(previous)))):
                continue
            updated = list(remaining)
            feasible = True
            for value in row:
                if updated[value - 1] == 0:
                    feasible = False
                    break
                updated[value - 1] -= 1
            if feasible:
                total += count_rows(row_index + 1, row, tuple(updated))
        return total

    return count_rows(0, (), content)


def _partitions_of(total: int) -> list[list[int]]:
    if total == 0:
        return [[]]
    partitions: list[list[int]] = []

    def generate(remaining: int, maximum: int, current: list[int]) -> None:
        if remaining == 0:
            partitions.append(current[:])
            return
        for value in range(min(remaining, maximum), 0, -1):
            current.append(value)
            generate(remaining - value, value, current)
            current.pop()

    generate(total, total, [])
    return partitions


def _kostka_result(args: dict[str, Any]) -> dict[str, Any]:
    shape = _shape(args)
    if args.get("content") is not None:
        content = _content(args)
        return {
            "shape": shape,
            "content": list(content),
            "kostka": safe_number(_count_sstyt(shape, content)),
        }
    size = sum(shape)
    row = []
    for partition in _partitions_of(size):
        row.append(
            {
                "mu": partition,
                "kostka": safe_number(_count_sstyt(shape, tuple(partition))),
            }
        )
    return {
        "shape": shape,
        "size": size,
        "kostka_row": row,
    }


def _rsk_reverse(
    insertion: list[list[Any]],
    recording: list[list[int]],
) -> list[Any]:
    """Reconstruye la palabra desde (P, Q) deshaciendo la insercion fila a fila.

    El tableau de registro lleva el indice del paso en el cuadrado donde la
    forma crece, asi que deshacer el paso i consiste en mover hacia arriba la
    letra de ese cuadrado hasta liberar la letra que fue insertada.
    """
    tableau = [row[:] for row in insertion]
    positions: dict[int, tuple[int, int]] = {}
    for row_index, row in enumerate(recording):
        for column, value in enumerate(row):
            positions[value] = (row_index, column)
    word: list[Any] = [None] * len(positions)
    for time in sorted(positions, reverse=True):
        growth_row, growth_column = positions[time]
        moving = tableau[growth_row][growth_column]
        row_index = growth_row
        while row_index > 0:
            upper = tableau[row_index - 1]
            target = None
            for column, existing in enumerate(upper):
                if existing < moving:
                    target = column
            if target is None:
                raise ValueError("no se pudo reconstruir la palabra desde P y Q")
            displaced = upper[target]
            upper[target] = moving
            moving = displaced
            row_index -= 1
        word[time - 1] = moving
        del tableau[growth_row][growth_column]
    return word


def _is_standard_tableau(tableau: list[list[int]]) -> bool:
    for row in tableau:
        for column in range(1, len(row)):
            if row[column] <= row[column - 1]:
                return False
    for row_index in range(1, len(tableau)):
        upper = tableau[row_index - 1]
        lower = tableau[row_index]
        for column in range(min(len(upper), len(lower))):
            if lower[column] <= upper[column]:
                return False
    return True


def _rsk(args: dict[str, Any]) -> dict[str, Any]:
    raw_word = need_list(args, "word", required=True)
    if not raw_word:
        raise ValueError("'word' no puede estar vacia")
    try:
        ordered = sorted(set(raw_word))
    except TypeError as exc:
        raise ValueError("las letras de 'word' deben ser comparables") from exc
    insertion: list[list[Any]] = []
    recording: list[list[int]] = []
    for time, value in enumerate(raw_word, start=1):
        current = value
        row_index = 0
        while True:
            while len(insertion) <= row_index:
                insertion.append([])
                recording.append([])
            row = insertion[row_index]
            replace_at = None
            for column, existing in enumerate(row):
                if existing > current:
                    replace_at = column
                    break
            if replace_at is None:
                row.append(current)
                recording[row_index].append(time)
                break
            bumped = row[replace_at]
            row[replace_at] = current
            current = bumped
            row_index += 1
    reconstructed = _rsk_reverse(insertion, recording)
    return {
        "word": raw_word,
        "alphabet": ordered,
        "insertion_tableau": insertion,
        "recording_tableau": recording,
        "shape": [len(row) for row in insertion],
        "recording_is_standard": _is_standard_tableau(recording),
        "reconstructed_word": reconstructed,
        "roundtrip": reconstructed == raw_word,
    }


def _word_count(args: dict[str, Any]) -> dict[str, Any]:
    word = need_list(args, "word", required=True)
    if not word:
        raise ValueError("'word' no puede estar vacia")
    try:
        counts = Counter(word)
    except TypeError as exc:
        raise ValueError("las letras de 'word' deben ser escalares hashables") from exc
    denominator = math.prod(math.factorial(count) for count in counts.values())
    return {
        "word": word,
        "length": len(word),
        "letter_counts": dict(counts),
        "distinct_permutations": safe_number(math.factorial(len(word)) // denominator),
    }


def _standard_result(args: dict[str, Any]) -> dict[str, Any]:
    shape = _shape(args)
    hooks = _hook_matrix(shape)
    return {
        "shape": shape,
        "size": sum(shape),
        "conjugate_shape": _conjugate(shape),
        "number_of_standard_young_tableaux": safe_number(_standard_count(shape, hooks)),
    }


def _hook_result(args: dict[str, Any]) -> dict[str, Any]:
    shape = _shape(args)
    hooks = _hook_matrix(shape)
    hook_product = math.prod(hook for row in hooks for hook in row)
    return {
        "shape": shape,
        "hook_matrix": hooks,
        "hook_product": safe_number(hook_product),
        "number_of_standard_young_tableaux": safe_number(_standard_count(shape, hooks)),
    }


def _validate() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    hook = _hook_result({"shape": [3, 2]})
    check("shape (3,2) has hook product 24", hook["hook_product"] == 24, str(hook["hook_product"]))
    check("shape (3,2) has 5 SYT", hook["number_of_standard_young_tableaux"] == 5)
    standard = _standard_result({"shape": [2, 1]})
    check("shape (2,1) has 2 SYT", standard["number_of_standard_young_tableaux"] == 2)
    rsk = _rsk({"word": ["a", "b", "c"]})
    check("RSK of abc has shape (3)", rsk["shape"] == [3], str(rsk["shape"]))
    check("RSK of abc has P=[[1,2,3]]", rsk["insertion_tableau"] == [["a", "b", "c"]], str(rsk["insertion_tableau"]))
    check("RSK of abc has Q=[[1,2,3]]", rsk["recording_tableau"] == [[1, 2, 3]], str(rsk["recording_tableau"]))
    check("RSK roundtrip reconstructs word", rsk["roundtrip"] is True)
    mississippi = _rsk({"word": list("mississippi")})
    check(
        "RSK of mississippi has shape (5,5,1)",
        mississippi["shape"] == [5, 5, 1],
        str(mississippi["shape"]),
    )
    check(
        "RSK of mississippi has P=[[i,i,i,i,p],[m,p,s,s,s],[s]]",
        mississippi["insertion_tableau"]
        == [["i", "i", "i", "i", "p"], ["m", "p", "s", "s", "s"], ["s"]],
        str(mississippi["insertion_tableau"]),
    )
    check(
        "RSK of mississippi has Q=[[1,3,4,6,7],[2,5,8,9,10],[11]]",
        mississippi["recording_tableau"]
        == [[1, 3, 4, 6, 7], [2, 5, 8, 9, 10], [11]],
        str(mississippi["recording_tableau"]),
    )
    check(
        "RSK recording tableau is standard",
        mississippi["recording_is_standard"] is True,
    )
    check(
        "RSK roundtrip reconstructs mississippi",
        mississippi["roundtrip"] is True,
        str(mississippi["reconstructed_word"]),
    )
    banana_rsk = _rsk({"word": list("banana")})
    check(
        "RSK roundtrip reconstructs banana",
        banana_rsk["roundtrip"] is True,
        str(banana_rsk["reconstructed_word"]),
    )
    banana = _word_count({"word": list("banana")})
    check("banana has 60 distinct anagrams", banana["distinct_permutations"] == 60, str(banana["distinct_permutations"]))
    kostka = _kostka_result({"shape": [2, 1], "content": [2, 1]})
    check("K_(2,1),(2,1)=1", kostka["kostka"] == 1, str(kostka["kostka"]))
    return {"validation_passed": all(item["passed"] for item in checks), "checks": checks}


def compute_young_tableaux(args: dict[str, Any]) -> dict[str, Any]:
    try:
        mode = args.get("mode", "validate")
        if mode == "validate":
            return _validate()
        if mode == "hook_length":
            return _hook_result(args)
        if mode == "standard_tableaux":
            return _standard_result(args)
        if mode == "kostka":
            return _kostka_result(args)
        if mode == "rsk":
            return _rsk(args)
        if mode == "word_count":
            return _word_count(args)
        raise ValueError("mode invalido")
    except (ValueError, TypeError, OverflowError, MemoryError) as exc:
        return {"error": str(exc)}


YOUNG_TABLEAUX_SCHEMA = {
    "name": "young_tableaux_tool",
    "description": (
        "Palabras y tableaux de Young: formula de hook-length, numero de "
        "tableaux estándar, insercion Robinson-Schensted con tableau P "
        "semiestandar y tableau Q estandar, numeros de Kostka por DP y "
        "conteo de anagramas distintos. Todos los conteos son enteros exactos."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["hook_length", "standard_tableaux", "kostka", "rsk", "word_count", "validate"],
                "default": "validate",
            },
            "shape": {"type": "array", "items": {"type": "integer", "minimum": 0}},
            "content": {"type": "array", "items": {"type": "integer", "minimum": 0}},
            "word": {"type": "array", "items": {}},
        },
        "required": ["mode"],
    },
}


register_tool(
    name="young_tableaux_tool",
    schema=YOUNG_TABLEAUX_SCHEMA,
    handler=compute_young_tableaux,
)
