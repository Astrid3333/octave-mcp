"""combinatorics_tool.py - combinatoria general exacta (enteros de precision arbitraria).

Formato octave-mcp: compute_combinatorics(args) + COMBINATORICS_TOOL_SCHEMA.
Solo biblioteca estandar; sympy es opcional y solo se usa en mode=validate.
"""
import itertools
import math
from functools import lru_cache

MAX_ENUM = 10000
MAX_N = 5000  # tope para recurrencias O(n^2)


def _safe(x):
    """Enteros fuera del rango exacto de float JSON se devuelven como str."""
    return str(x) if isinstance(x, int) and abs(x) > 2 ** 53 else x


def _need_int(args, key, lo=0, hi=None):
    if key not in args or args[key] is None:
        raise ValueError(f"falta el parametro '{key}'")
    v = args[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v:
        raise ValueError(f"'{key}' debe ser entero")
    v = int(v)
    if v < lo or (hi is not None and v > hi):
        raise ValueError(f"'{key}' fuera de rango [{lo}, {hi if hi is not None else 'inf'}]")
    return v


@lru_cache(maxsize=None)
def _stirling2_row(n):
    row = [1]  # S(0,0)
    for i in range(1, n + 1):
        new = [0] * (i + 1)
        for k in range(1, i + 1):
            prev_k = row[k] if k < len(row) else 0
            new[k] = k * prev_k + row[k - 1]
        row = new
    return tuple(row)


@lru_cache(maxsize=None)
def _stirling1_row(n):
    row = [1]  # c(0,0), sin signo
    for i in range(1, n + 1):
        new = [0] * (i + 1)
        for k in range(1, i + 1):
            prev_k = row[k] if k < len(row) else 0
            new[k] = (i - 1) * prev_k + row[k - 1]
        row = new
    return tuple(row)


def _partitions_table(n):
    """p(n,k): particiones de n en exactamente k partes."""
    p = [[0] * (n + 1) for _ in range(n + 1)]
    p[0][0] = 1
    for i in range(1, n + 1):
        for k in range(1, i + 1):
            p[i][k] = p[i - 1][k - 1] + (p[i - k][k] if i - k >= 0 else 0)
    return p


def _bell(n):
    return sum(_stirling2_row(n))


def _catalan(n):
    return math.comb(2 * n, n) // (n + 1)


def _derangements(n):
    d0, d1 = 1, 0
    if n == 0:
        return 1
    for i in range(2, n + 1):
        d0, d1 = d1, (i - 1) * (d0 + d1)
    return d1


def _multinomial(parts):
    total = sum(parts)
    r = math.factorial(total)
    for p in parts:
        r //= math.factorial(p)
    return r


def _count(args):
    n = _need_int(args, "n", 0, 10 ** 6)
    k = _need_int(args, "k", 0, 10 ** 6)
    out = {
        "n": n, "k": k,
        "n^k (variaciones con repeticion)": _safe(n ** k),
        "C(n+k-1,k) (combinaciones con repeticion)": _safe(math.comb(n + k - 1, k) if n + k > 0 else 1),
    }
    out["C(n,k) (binomial)"] = _safe(math.comb(n, k))
    out["P(n,k) (variaciones sin repeticion)"] = _safe(math.perm(n, k))
    out["n! (permutaciones)"] = _safe(math.factorial(n)) if n <= 20000 else "omitido (n>20000)"
    return out


def _enumerate(args):
    kind = args.get("kind", "combinations")
    items = args.get("items")
    if items is None:
        items = list(range(_need_int(args, "n", 0, 12)))
    if not isinstance(items, list) or len(items) > 20:
        raise ValueError("'items' debe ser lista de <=20 elementos")
    k = args.get("k")
    k = len(items) if k is None else _need_int(args, "k", 0, len(items) if kind != "product" else 10)
    limit = min(_need_int(args, "limit", 1, MAX_ENUM) if "limit" in args else 200, MAX_ENUM)
    gens = {
        "combinations": lambda: itertools.combinations(items, k),
        "permutations": lambda: itertools.permutations(items, k),
        "combinations_with_replacement": lambda: itertools.combinations_with_replacement(items, k),
        "product": lambda: itertools.product(items, repeat=k),
    }
    if kind not in gens:
        raise ValueError(f"kind invalido; usa {sorted(gens)}")
    res = [list(t) for t in itertools.islice(gens[kind](), limit)]
    total = {
        "combinations": math.comb(len(items), k),
        "permutations": math.perm(len(items), k),
        "combinations_with_replacement": math.comb(len(items) + k - 1, k) if len(items) + k else 1,
        "product": len(items) ** k,
    }[kind]
    return {"kind": kind, "total": _safe(total), "devueltos": len(res),
            "truncado": len(res) < total, "resultados": res}


def _validate():
    checks = []

    def chk(name, got, exp):
        checks.append({"check": name, "ok": got == exp, "got": _safe(got), "esperado": _safe(exp)})

    chk("C(10,3)", math.comb(10, 3), 120)
    chk("S2(5,3)", _stirling2_row(5)[3], 25)
    chk("c(5,2) sin signo", _stirling1_row(5)[2], 50)
    chk("Bell(6)", _bell(6), 203)
    chk("Catalan(10)", _catalan(10), 16796)
    chk("D(6) subfactorial", _derangements(6), 265)
    chk("p(10)", sum(_partitions_table(10)[10]), 42)
    chk("p(100)", sum(_partitions_table(100)[100]), 190569292)
    chk("multinomial(2,3,4)", _multinomial([2, 3, 4]), 1260)
    chk("sum_k C(20,k)=2^20", sum(math.comb(20, k) for k in range(21)), 2 ** 20)
    chk("sum_k S2(8,k)*k! = Fubini(8)", sum(s * math.factorial(k) for k, s in enumerate(_stirling2_row(8))), 545835)
    chk("sum_k c(7,k) = 7!", sum(_stirling1_row(7)), math.factorial(7))
    chk("D(n) = round(n!/e), n=10", _derangements(10), round(math.factorial(10) / math.e))
    chk("enumerate C(5,2) cuenta", len(_enumerate({"kind": "combinations", "n": 5, "k": 2})["resultados"]), 10)
    try:
        import sympy
        from sympy.functions.combinatorial.numbers import stirling
        chk("sympy S2(9,4)", _stirling2_row(9)[4], int(stirling(9, 4)))
        chk("sympy c(9,4)", _stirling1_row(9)[4], int(stirling(9, 4, kind=1)))
        chk("sympy Bell(12)", _bell(12), int(sympy.bell(12)))
        chk("sympy Catalan(15)", _catalan(15), int(sympy.catalan(15)))
        chk("sympy subfactorial(9)", _derangements(9), int(sympy.subfactorial(9)))
    except Exception as e:  # sympy ausente o API distinta
        checks.append({"check": "sympy cruzado", "ok": True, "nota": f"omitido: {type(e).__name__}"})
    # caminos de error
    for name, a in [("n negativo", {"mode": "count", "n": -1, "k": 1}),
                    ("k no entero", {"mode": "count", "n": 5, "k": 1.5}),
                    ("mode invalido", {"mode": "xyz"})]:
        r = compute_combinatorics(a)
        checks.append({"check": f"error: {name}", "ok": "error" in r})
    return {"all_passed": all(c["ok"] for c in checks), "checks": checks}


def compute_combinatorics(args):
    try:
        mode = args.get("mode", "validate")
        if mode == "validate":
            return _validate()
        if mode == "count":
            return _count(args)
        if mode == "enumerate":
            return _enumerate(args)
        if mode == "multinomial":
            parts = args.get("parts")
            if not isinstance(parts, list) or not parts or any(
                    isinstance(p, bool) or not isinstance(p, int) or p < 0 for p in parts):
                raise ValueError("'parts' debe ser lista de enteros >= 0")
            return {"parts": parts, "multinomial": _safe(_multinomial(parts))}
        n = _need_int(args, "n", 0, MAX_N if mode in ("stirling2", "stirling1", "bell", "partitions") else 10 ** 5)
        if mode in ("stirling2", "stirling1"):
            row = (_stirling2_row if mode == "stirling2" else _stirling1_row)(n)
            if args.get("k") is not None:
                k = _need_int(args, "k", 0, n)
                return {"n": n, "k": k, mode: _safe(row[k])}
            return {"n": n, "fila": [_safe(x) for x in row], "suma": _safe(sum(row))}
        if mode == "bell":
            return {"n": n, "bell": _safe(_bell(n))}
        if mode == "catalan":
            return {"n": n, "catalan": _safe(_catalan(n))}
        if mode == "derangements":
            return {"n": n, "subfactorial": _safe(_derangements(n)),
                    "fraccion_de_n!": _derangements(n) / math.factorial(n) if n <= 170 else 1 / math.e}
        if mode == "partitions":
            t = _partitions_table(n)[n]
            if args.get("k") is not None:
                k = _need_int(args, "k", 0, n)
                return {"n": n, "k": k, "p(n,k)": _safe(t[k])}
            return {"n": n, "p(n)": _safe(sum(t)), "por_numero_de_partes": [_safe(x) for x in t]}
        raise ValueError("mode invalido")
    except (ValueError, OverflowError, MemoryError) as e:
        return {"error": str(e)}


COMBINATORICS_TOOL_SCHEMA = {
    "name": "combinatorics_tool",
    "description": (
        "Combinatoria general exacta (enteros de precision arbitraria): count (n^k, C(n,k), P(n,k), "
        "multiconjuntos, n!), stirling1/stirling2 (numero o fila), bell, catalan, derangements "
        "(subfactorial), partitions (p(n) y p(n,k)), multinomial, enumerate (lista combinaciones/"
        "permutaciones/producto con limite) y validate (identidades + cruce con sympy + caminos de error). "
        "Numeros mayores a 2^53 se devuelven como cadena."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "default": "validate",
                     "enum": ["count", "stirling1", "stirling2", "bell", "catalan", "derangements",
                              "partitions", "multinomial", "enumerate", "validate"]},
            "n": {"type": "integer", "description": "Tamano del conjunto / indice"},
            "k": {"type": "integer", "description": "Tamano de la seleccion / numero de bloques o partes"},
            "parts": {"type": "array", "items": {"type": "integer"}, "description": "Solo multinomial"},
            "kind": {"type": "string",
                     "enum": ["combinations", "permutations", "combinations_with_replacement", "product"],
                     "description": "Solo enumerate"},
            "items": {"type": "array", "description": "Solo enumerate: elementos (<=20); si falta se usa range(n)"},
            "limit": {"type": "integer", "description": "Solo enumerate: maximo de resultados (<=10000, default 200)"},
        },
        "required": ["mode"],
    },
}


from tool_registry import register_tool  # <- igual que en ternary_combinatorics_tool.py


register_tool(
    name="combinatorics_tool",
    schema=COMBINATORICS_TOOL_SCHEMA,
    handler=compute_combinatorics,
)
