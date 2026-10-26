"""
alkahest_cas_tool.py

CAS simbólico Alkahest (núcleo Rust + FLINT + egglog, PyPI `alkahest`)
enchufado al MCP con el contrato estándar de la casa: DerivedResult con
value + steps (log de rewrite rules JSON-safe) + verification + certificado
Lean 4 cuando existe.

Diseño:
- Un ExprPool nuevo por llamada: el pool es write-only y crece sin límite,
  así que nunca se reutiliza entre peticiones (lección del propio autor de
  Alkahest).
- Los símbolos se resuelven por nombre dentro del pool (hash-consing: el
  mismo nombre = el mismo nodo), así que parse() con mapa vacío y luego
  pool.symbol(var) dan el mismo símbolo.
- validate usa referencias analíticas trazadas a mano (derivada de
  sin(x^2)*exp(x), series de exp, Σk^2, raíces ±2, factorización de
  2^32-1, ...) — no depende de otro CAS como oráculo.
- La serie con order=N trunca ANTES de x^N (término O(x^N)); para
  verificar hasta x^5 se pide order=6.

Nota de robustez (bug 2026-10-22, causa raíz 2026-10-26): las operaciones
de teoría de números de alkahest (factorint/totient/nextprime con entradas
grandes o difíciles) abortaban el proceso con SIGILL — un panic con abort
que NO se puede capturar con try/except. Causa raíz: el libflint
empaquetado del wheel viene compilado con ADX (adcx/adox, Broadwell+;
2626 patrones en segmentos ejecutables) y esta CPU (Haswell i7-4785T) no
tiene ADX. Fix aplicado 2026-10-26: FLINT 3.6.0 reconstruido con
`-O2 -march=x86-64 -mtune=generic` y reemplazado en
`site-packages/alkahest.libs/libflint-*.so` (0 patrones ADX). El validate
comprueba que esa lib siga sin ADX (`nt_libflint_no_adx`): si alguien
reinstala el wheel roto, el check falla en vez de esconder el fallback.
Las cuatro NT ops siguen corriendo en un subprocess aislado (defensa en
profundidad para ruedas/CPUs sin el fix): si el hijo alkahest muere
(señal/timeout), el padre reintenta con sympy y reporta el motor en el
campo `engine` con `fallback_reason`, nunca en silencio.
"""

import json
import math
import mmap
import signal
import struct
import subprocess
import sys
from pathlib import Path

from tool_registry import register_tool

try:
    import alkahest as ak
    import alkahest.number_theory as _ant
except ImportError:
    ak = None
    _ant = None

ALKAHEST_CAS_TOOL_SCHEMA = {
    "name": "alkahest_cas_tool",
    "description": (
        "CAS simbólico Alkahest (núcleo Rust+FLINT): diff, integrate, "
        "simplify, limit, series, solve (Gröbner), sum_definite/"
        "sum_indefinite (telescoping creativo), factorint/isprime/"
        "totient/nextprime (teoría de números), matrix (eigenvals/"
        "eigenvects/inverse/det/rank/trace/rref/jordan_form), jacobian, "
        "diophantine (lineal + Pell), real_roots (aislamiento CAD de "
        "raíces reales). Cada operación simbólica "
        "devuelve DerivedResult: value, steps (log de reglas de reescritura "
        "JSON-safe), verification (certificate_available/exactly_verified/"
        "...) y certificate (Lean 4, truncado a 4 KB). Modos: compute (una "
        "operación con expr/var/point/order/bounds/equations/n) y validate "
        "(autochequeos contra soluciones analíticas conocidas). Las NT ops "
        "corren aisladas en subprocess con fallback a sympy si el núcleo "
        "Rust aborta (campo engine = alkahest | sympy_fallback)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["compute", "validate"],
            },
            "operation": {
                "type": "string",
                "enum": [
                    "diff",
                    "integrate",
                    "simplify",
                    "limit",
                    "series",
                    "solve",
                    "sum_definite",
                    "sum_indefinite",
                    "factorint",
                    "isprime",
                    "totient",
                    "nextprime",
                    "matrix",
                    "jacobian",
                    "diophantine",
                    "real_roots",
                ],
                "description": (
                    "Operación a ejecutar en mode=compute. factorint/"
                    "isprime/totient/nextprime usan n; solve usa equations; "
                    "matrix usa matrix+action; jacobian usa exprs+vars; "
                    "diophantine/real_roots usan expr (+vars/var)."
                ),
            },
            "expr": {
                "type": "string",
                "description": (
                    "Expresión infija, ej: \"sin(x^2)*exp(x)\", "
                    "\"(x^2-1)/(x-1)\". Los símbolos se autodetectan. "
                    "Requerida salvo para solve (equations) y teoría de "
                    "números (n)."
                ),
            },
            "var": {
                "type": "string",
                "description": (
                    "Símbolo variable: derivada/integración/límite/"
                    "serie/índice de sumas. Default \"x\"."
                ),
                "default": "x",
            },
            "point": {
                "anyOf": [{"type": "number"}, {"type": "string"}],
                "description": (
                    "Punto para limit (ej 0, \"n\") o centro de la serie "
                    "(default 0)."
                ),
            },
            "order": {
                "type": "integer",
                "description": (
                    "series: orden N de truncamiento (términos hasta "
                    "x^(N-1), error O(x^N)). Debe ser >= 1."
                ),
            },
            "bounds": {
                "type": "array",
                "description": (
                    "[lo, hi] numéricos o simbólicos (ej [0, 2] o "
                    "[1, \"n\"]) para integrate definida y sum_definite."
                ),
            },
            "equations": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Ecuaciones para solve, expresadas como expresiones "
                    "igualadas a cero (ej [\"x^2 - 4\"])."
                ),
            },
            "vars": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Incógnitas de solve/jacobian/diophantine "
                    "(default [var])."
                ),
            },
            "n": {
                "type": "integer",
                "description": "Entero para factorint/isprime/totient/nextprime.",
            },
            "dir": {
                "type": "string",
                "enum": ["+", "-"],
                "description": "limit: dirección de aproximación (opcional).",
            },
            "matrix": {
                "type": "array",
                "items": {"type": "array"},
                "description": (
                    "operation=matrix: matriz rectangular "
                    "[[fila1],[fila2],...] con números o expresiones como "
                    "cadenas (ej [[2,1],[1,2]] o [[\"x\",1],[0,\"x\"]])."
                ),
            },
            "action": {
                "type": "string",
                "enum": [
                    "eigenvals",
                    "eigenvects",
                    "inverse",
                    "det",
                    "rank",
                    "trace",
                    "rref",
                    "jordan_form",
                ],
                "description": (
                    "operation=matrix: qué computar (default eigenvals)."
                ),
            },
            "exprs": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "operation=jacobian: componentes del vector f, "
                    "ej [\"x*y\", \"y^2 - x\"], con vars=[x,y]."
                ),
            },
        },
        "required": ["mode"],
    },
}


def _require_ak():
    if ak is None:
        raise ValueError(
            "alkahest no está instalado en .venv "
            "(.venv/bin/pip install alkahest)"
        )


# Hijo aislado para NT: el kernel Rust de alkahest aborta con SIGILL en
# ciertas entradas (factorint/totient/nextprime grandes o difíciles) y una
# señal así mata al MCP entero si corre in-process. RLIMIT_CORE=0 evita
# core dumps; el padre detecta rc<0 y reintenta con sympy. Con el libflint
# sin ADX el hijo alkahest ya no muere en esta CPU, pero el fence queda
# como defensa en profundidad (p. ej. ruedas reinstaladas con el bug).
_NT_CHILD_SRC = """
import json, resource, sys
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
op, engine, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
if engine == "alkahest":
    import alkahest.number_theory as mod
    fn = getattr(mod, op)
else:
    import sympy
    fn = {"factorint": sympy.factorint, "totient": sympy.totient,
          "isprime": sympy.isprime, "nextprime": sympy.nextprime}[op]
r = fn(n)
if isinstance(r, dict):
    out = {str(k): int(v) for k, v in r.items()}
elif isinstance(r, bool):
    out = bool(r)
else:
    out = int(r)
sys.stdout.write(json.dumps(out))
"""

_NT_TIMEOUT_SECONDS = 45


def _nt_isolated(op, n):
    """Corre NT op en hijo aislado: alkahest primero, sympy si muere."""
    last = None
    for engine, label in (("alkahest", "alkahest"), ("sympy", "sympy_fallback")):
        try:
            proc = subprocess.run(
                [sys.executable, "-c", _NT_CHILD_SRC, op, engine, str(n)],
                capture_output=True,
                text=True,
                timeout=_NT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            last = f"{engine}: timeout {_NT_TIMEOUT_SECONDS}s"
            continue
        if proc.returncode == 0 and proc.stdout.strip():
            payload = json.loads(proc.stdout)
            result = {"operation": op, "ok": True, "n": n, "engine": label}
            if engine != "alkahest":
                result["fallback_reason"] = last
            if isinstance(payload, dict):
                result["factors"] = payload
            elif op == "isprime":
                result["isprime"] = payload
            elif op == "totient":
                result["totient"] = payload
            else:
                result["nextprime"] = payload
            return result
        if proc.returncode < 0:
            sig = -proc.returncode
            try:
                name = signal.Signals(sig).name
            except ValueError:
                name = str(sig)
            last = f"{engine}: crash signal {sig} ({name})"
        else:
            err = (proc.stderr or "").strip()[-200:]
            last = f"{engine}: rc={proc.returncode} {err}"
    raise ValueError(f"NT operation={op} fallo en ambos motores: {last}")


def _fresh_pool():
    """Pool nuevo por llamada: ExprPool es write-only y no se libera."""
    return ak.ExprPool()


_INF_ALIASES = frozenset({"oo", "OO", "inf", "Inf", "infinity", "∞", "+∞"})


def _to_expr(pool, value):
    if isinstance(value, bool):
        raise ValueError(f"valor no esperado: {value!r}")
    if isinstance(value, int):
        return pool.integer(value)
    if isinstance(value, float):
        return ak.parse(repr(float(value)), pool)
    text = str(value)
    if text in _INF_ALIASES:
        return pool.pos_infinity()
    return ak.parse(text, pool)


def _ser_derived(result):
    """DerivedResult -> dict JSON-safe (to_dict ya es serializable)."""
    out = result.to_dict()
    cert = result.certificate or ""
    out["certificate"] = cert[:4096]
    out["certificate_chars"] = len(cert)
    return out


def _eval_at(expr, pairs):
    """Evalúa expr (nativa alkahest) con pares [(símbolo, float), ...]."""
    fn = ak.compile_expr(expr, [s for s, _ in pairs])
    return float(fn([v for _, v in pairs]))


def _cells(matrix_like):
    """Matriz/lista anidada -> filas de strings JSON-safe.

    Las columnas de eigenvects vienen como Matrix embebidas: se
    desempaqueta cualquier fila que tenga to_list().
    """
    rows = matrix_like.to_list() if hasattr(matrix_like, "to_list") else matrix_like
    out = []
    for row in rows:
        if hasattr(row, "to_list"):
            row = row.to_list()
        out.append([str(c) for c in row])
    return out


def _bound(value):
    """Cota de RootInterval: float si es numérico, string si es simbólica."""
    if isinstance(value, (int, float)):
        return float(value)
    return str(value)


def _column(vec):
    """Autovector (lista de Matrix-columna o lista de filas) -> [str, ...]."""
    rows = vec.to_list() if hasattr(vec, "to_list") else vec
    return [str(row[0] if isinstance(row, (list, tuple)) else row) for row in rows]


def _compute(args):
    _require_ak()
    op = args.get("operation")
    if not isinstance(op, str) or not op:
        raise ValueError("mode=compute requiere operation")

    pool = _fresh_pool()
    var = args.get("var") or "x"

    if op in ("factorint", "isprime", "totient", "nextprime"):
        n = args.get("n")
        if not isinstance(n, int) or isinstance(n, bool):
            raise ValueError(f"operation={op} requiere n entero")
        return _nt_isolated(op, n)

    if op == "solve":
        equations = args.get("equations")
        if not equations:
            expr_str = args.get("expr")
            equations = [expr_str] if expr_str else []
        if not equations:
            raise ValueError("operation=solve requiere equations o expr")
        names = args.get("vars") or [var]
        eq_objs = [ak.parse(str(eq), pool, {}) for eq in equations]
        sym_objs = [pool.symbol(str(name)) for name in names]
        solutions = ak.solve(eq_objs, sym_objs)
        serialized = [
            {str(k): str(v) for k, v in dict(sol).items()} for sol in solutions
        ]
        return {
            "operation": op,
            "ok": True,
            "count": len(serialized),
            "solutions": serialized,
            "vars": [str(name) for name in names],
            "method": "groebner",
        }

    if op == "matrix":
        rows = args.get("matrix")
        if not isinstance(rows, list) or not rows:
            raise ValueError("operation=matrix requiere matrix=[[...],[...]]")
        if not all(isinstance(r, list) and r for r in rows):
            raise ValueError("matrix debe ser una lista de filas no vacías")
        width = len(rows[0])
        if any(len(r) != width for r in rows):
            raise ValueError("matrix debe ser rectangular")
        mat = ak.Matrix.from_rows(
            [[_to_expr(pool, c) for c in row] for row in rows]
        )
        action = args.get("action") or "eigenvals"
        out = {
            "operation": op,
            "action": action,
            "ok": True,
            "shape": [int(d) for d in mat.shape()],
        }
        if action == "eigenvals":
            out["eigenvals"] = {
                str(k): int(v) for k, v in mat.eigenvals().items()
            }
        elif action == "eigenvects":
            out["eigenvects"] = [
                {
                    "value": str(val),
                    "mult": int(mult),
                    "basis": [_column(vec) for vec in basis],
                }
                for val, mult, basis in mat.eigenvects()
            ]
        elif action == "inverse":
            out["inverse"] = _cells(mat.inverse())
        elif action == "det":
            out["det"] = str(mat.det())
        elif action == "rank":
            out["rank"] = str(mat.rank())
        elif action == "trace":
            out["trace"] = str(mat.trace())
        elif action == "rref":
            out["rref"] = _cells(mat.rref())
        elif action == "jordan_form":
            p_mat, j_mat = mat.jordan_form()
            out["jordan"] = {"P": _cells(p_mat), "J": _cells(j_mat)}
        else:
            raise ValueError(f"action desconocida: {action}")
        return out

    if op == "jacobian":
        exprs = args.get("exprs")
        if not isinstance(exprs, list) or not exprs:
            raise ValueError("operation=jacobian requiere exprs=[...]")
        names = args.get("vars")
        if not isinstance(names, list) or not names:
            raise ValueError("operation=jacobian requiere vars=[...]")
        f_objs = [ak.parse(str(s), pool, {}) for s in exprs]
        var_objs = [pool.symbol(str(n)) for n in names]
        jac = ak.jacobian(f_objs, var_objs)
        return {
            "operation": op,
            "ok": True,
            "vars": [str(n) for n in names],
            "shape": [int(d) for d in jac.shape()],
            "jacobian": _cells(jac),
        }

    expr_str = args.get("expr")
    if not isinstance(expr_str, str) or not expr_str.strip():
        raise ValueError(f"operation={op} requiere expr")

    expr = ak.parse(expr_str, pool, {})
    sym = pool.symbol(var)

    if op == "diophantine":
        names = args.get("vars") or [var]
        sol = ak.diophantine(expr, [pool.symbol(str(n)) for n in names])
        out = {
            "operation": op,
            "ok": True,
            "vars": [str(n) for n in names],
            "kind": str(sol.kind),
            "solution": str(sol),
        }
        if sol.parameter is not None:
            out["parameter"] = str(sol.parameter)
        if sol.parametric is not None:
            out["parametric"] = [str(e) for e in sol.parametric]
        if sol.fundamental is not None:
            out["fundamental"] = [str(c) for c in sol.fundamental]
        if sol.pell_d is not None:
            out["pell_d"] = str(sol.pell_d)
        if sol.points is not None:
            out["points"] = [[str(c) for c in pt] for pt in sol.points]
        return out

    if op == "real_roots":
        roots = ak.real_roots(expr, sym)

        def _exact_rational(pair):
            if isinstance(pair, tuple) and len(pair) == 2:
                return f"{pair[0]}/{pair[1]}"
            return str(pair)

        intervals = [
            {
                "lo": _bound(iv.lo),
                "hi": _bound(iv.hi),
                "lo_exact": _exact_rational(iv.lo_exact()),
                "hi_exact": _exact_rational(iv.hi_exact()),
            }
            for iv in roots
        ]
        return {
            "operation": op,
            "ok": True,
            "var": var,
            "count": len(intervals),
            "intervals": intervals,
        }

    if op == "diff":
        result = ak.diff(expr, sym)
        return {"operation": op, "ok": True, "var": var, **_ser_derived(result)}

    if op == "integrate":
        bounds = args.get("bounds")
        if bounds is not None:
            if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
                raise ValueError("bounds debe ser [lo, hi]")
            lo, hi = (_to_expr(pool, b) for b in bounds)
            result = ak.integrate(expr, sym, lo, hi)
        else:
            result = ak.integrate(expr, sym)
        return {"operation": op, "ok": True, "var": var, **_ser_derived(result)}

    if op == "simplify":
        result = ak.simplify(expr)
        return {"operation": op, "ok": True, **_ser_derived(result)}

    if op == "limit":
        if "point" not in args:
            raise ValueError("operation=limit requiere point")
        point = _to_expr(pool, args["point"])
        direction = args.get("dir")
        result = ak.limit(expr, sym, point, direction)
        return {
            "operation": op,
            "ok": True,
            "var": var,
            "point": str(args["point"]),
            **_ser_derived(result),
        }

    if op == "series":
        order = args.get("order")
        if not isinstance(order, int) or isinstance(order, bool) or order < 1:
            raise ValueError("operation=series requiere order entero >= 1")
        point = _to_expr(pool, args.get("point", 0))
        series = ak.series(expr, sym, point, order)
        truncated = series.truncated()
        return {
            "operation": op,
            "ok": True,
            "var": var,
            "order": order,
            "truncated": str(truncated),
            "with_big_o": str(series.expr),
            "value": str(series.expr),
        }

    if op in ("sum_definite", "sum_indefinite"):
        bounds = args.get("bounds")
        if op == "sum_definite":
            if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
                raise ValueError(
                    "operation=sum_definite requiere bounds=[lo, hi]"
                )
            lo, hi = (_to_expr(pool, b) for b in bounds)
            result = ak.sum_definite(expr, sym, lo, hi)
        else:
            result = ak.sum_indefinite(expr, sym)
        return {
            "operation": op,
            "ok": True,
            "var": var,
            **_ser_derived(result),
        }

    raise ValueError(f"operation desconocida: {op}")


# Patrones de máquina ADX (adcx/adox = F3/F2 0F 38 F6, con/sin REX):
# presentes solo si el binario fue compilado para CPUs con ADX
# (Broadwell+). Haswell y anteriores los abortan con SIGILL.
_ADX_PATTERNS = (
    b"\xf3\x0f\x38\xf6",
    b"\xf2\x0f\x38\xf6",
    b"\xf3\x48\x0f\x38\xf6",
    b"\xf3\x49\x0f\x38\xf6",
    b"\xf3\x4c\x0f\x38\xf6",
    b"\xf3\x41\x0f\x38\xf6",
    b"\xf2\x48\x0f\x38\xf6",
    b"\xf2\x4c\x0f\x38\xf6",
)


def _count_adx_exec(path):
    """Cuenta patrones adcx/adox en segmentos ejecutables de un ELF."""
    with open(path, "rb") as fh, mmap.mmap(
        fh.fileno(), 0, access=mmap.ACCESS_READ
    ) as mm:
        if mm[:4] != b"\x7fELF" or len(mm) < 64:
            return -1
        e_phoff = struct.unpack_from("<Q", mm, 32)[0]
        e_phentsize, e_phnum = struct.unpack_from("<HH", mm, 54)
        if e_phoff == 0 or e_phentsize == 0:
            return -1
        total = 0
        for i in range(e_phnum):
            off = e_phoff + i * e_phentsize
            p_type, p_flags = struct.unpack_from("<II", mm, off)
            if p_type != 1 or not (p_flags & 1):  # PT_LOAD + PF_X
                continue
            p_offset, _, _, p_filesz = struct.unpack_from("<QQQQ", mm, off + 8)
            seg = bytes(mm[p_offset : p_offset + p_filesz])
            for pat in _ADX_PATTERNS:
                j = seg.find(pat)
                while j >= 0:
                    total += 1
                    j = seg.find(pat, j + 1)
        return total


def _validate():
    if ak is None:
        msg = "alkahest no instalado (.venv/bin/pip install alkahest)"
        return {
            "mode": "validate",
            "validation_passed": False,
            "checks": [{"name": "import_alkahest", "passed": False, "error": msg}],
        }

    checks = []

    def chk(name, fn):
        try:
            passed, got, expected = fn()
            checks.append(
                {
                    "name": name,
                    "passed": bool(passed),
                    "got": got,
                    "expected": expected,
                }
            )
        except Exception as exc:  # noqa: BLE001 - el contrato exige informar
            checks.append(
                {"name": name, "passed": False, "error": str(exc)[:300]}
            )

    def check_diff():
        pool = _fresh_pool()
        expr = ak.parse("sin(x^2)*exp(x)", pool, {})
        x = pool.symbol("x")
        value = ak.diff(expr, x).value
        # g(x) = e^x (2x cos(x^2) + sin(x^2)) a cada punto
        ref = [
            math.exp(p) * (2.0 * p * math.cos(p * p) + math.sin(p * p))
            for p in (-1.3, 0.7, 2.1)
        ]
        # compile multi-punto: evaluar uno a uno
        got_pts = [
            _eval_at(value, [(x, p)])
            for p in (-1.3, 0.7, 2.1)
        ]
        err = max(abs(g - r) for g, r in zip(got_pts, ref))
        return err < 1e-9, f"max_err={err:.3e}", "< 1e-9 vs derivada analítica"

    def check_integrate_definite():
        pool = _fresh_pool()
        expr = ak.parse("x^2", pool, {})
        x = pool.symbol("x")
        result = ak.integrate(expr, x, pool.integer(0), pool.integer(2))
        got = _eval_at(result.value, [])
        return (
            abs(got - 8.0 / 3.0) < 1e-12 and str(result.value) == "8/3",
            f"value={result.value!s}, eval={got!r}",
            "8/3 (=2.6666...)",
        )

    def check_integrate_cos():
        pool = _fresh_pool()
        expr = ak.parse("cos(t)", pool, {})
        t = pool.symbol("t")
        result = ak.integrate(
            expr, t, _to_expr(pool, -1.5), _to_expr(pool, 2.3)
        )
        got = _eval_at(result.value, [])
        ref = math.sin(2.3) - math.sin(-1.5)
        return abs(got - ref) < 1e-9, f"eval={got!r}", f"sin(2.3)-sin(-1.5)={ref!r}"

    def check_simplify_rational():
        pool = _fresh_pool()
        expr = ak.parse("(x^2-1)/(x-1)", pool, {})
        x = pool.symbol("x")
        value = ak.simplify(expr).value
        pts = (3.5, -0.2, 10.0)
        errs = [abs(_eval_at(value, [(x, p)]) - (p + 1.0)) for p in pts]
        return max(errs) < 1e-12, f"max_err={max(errs):.3e}", "== x+1, < 1e-12"

    def check_limit():
        pool = _fresh_pool()
        expr = ak.parse("sin(x)/x", pool, {})
        x = pool.symbol("x")
        value = ak.limit(expr, x, pool.integer(0)).value
        return str(value) == "1", str(value), "1"

    def check_limit_bernoulli_inf():
        # Regresión de _to_expr: "oo" debe resolverse a pos_infinity();
        # con un símbolo normal el límite quedaba sin evaluar.
        pool = _fresh_pool()
        expr = ak.parse("(1+1/n)^n", pool, {})
        n = pool.symbol("n")
        value = ak.limit(expr, n, _to_expr(pool, "oo")).value
        return str(value) == "exp(1)", str(value), "exp(1)"

    def check_sum_definite_basel_inf():
        # Basel exige la forma k^(-2): "1/k^2" parsea como 1/(k^2) y cae
        # en PySumError E-SUM-002 (comportamiento upstream de alkahest).
        pool = _fresh_pool()
        k = pool.symbol("k")
        value = ak.sum_definite(
            _to_expr(pool, "k^(-2)"), k, _to_expr(pool, 1), _to_expr(pool, "oo")
        ).value
        got = _eval_at(value, [])
        return abs(got - math.pi**2 / 6) < 1e-12, f"eval={got!r}", "pi^2/6"

    def check_series_exp():
        pool = _fresh_pool()
        expr = ak.parse("exp(x)", pool, {})
        x = pool.symbol("x")
        series = ak.series(expr, x, pool.integer(0), 6)
        poly = series.truncated()
        errs = []
        for p in (0.3, -0.5):
            ref = sum(p**k / math.factorial(k) for k in range(6))
            errs.append(abs(_eval_at(poly, [(x, p)]) - ref))
        has_o = "O(x^6)" in str(series.expr)
        return (
            max(errs) < 1e-9 and has_o,
            f"max_err={max(errs):.3e}, O(x^6)={'O(x^6)' in str(series.expr)}",
            "Taylor exp(x) a x^5, < 1e-9, truncamiento O(x^6)",
        )

    def check_solve_quadratic():
        pool = _fresh_pool()
        x = pool.symbol("x")
        solutions = ak.solve([ak.parse("x^2 - 4", pool, {})], [x])
        roots = sorted(
            _eval_at(list(dict(sol).values())[0], []) for sol in solutions
        )
        ok = len(roots) == 2 and abs(roots[0] + 2.0) < 1e-9 and abs(roots[1] - 2.0) < 1e-9
        return ok, f"roots={roots}", "[-2, 2]"

    def check_solve_system():
        pool = _fresh_pool()
        x = pool.symbol("x")
        y = pool.symbol("y")
        eq1 = ak.parse("x + y - 2", pool, {})
        eq2 = ak.parse("x^2 + y^2 - 5", pool, {})
        solutions = ak.solve([eq1, eq2], [x, y])
        worst = 0.0
        for sol in solutions:
            assignment = dict(sol)
            xv = _eval_at(assignment[x], [])
            yv = _eval_at(assignment[y], [])
            worst = max(worst, abs(xv + yv - 2.0), abs(xv * xv + yv * yv - 5.0))
        return (
            len(solutions) == 2 and worst < 1e-9,
            f"solutions={len(solutions)}, max_residual={worst:.3e}",
            "2 soluciones con residuo < 1e-9",
        )

    def check_sum_definite_k2():
        pool = _fresh_pool()
        k = pool.symbol("k")
        n = pool.symbol("n")
        value = ak.sum_definite(
            ak.parse("k^2", pool, {}), k, pool.integer(1), n
        ).value
        errs = []
        for nv in (1, 2, 5, 10):
            ref = nv * (nv + 1) * (2 * nv + 1) / 6
            errs.append(abs(_eval_at(value, [(n, float(nv))]) - ref))
        return max(errs) < 1e-9, f"max_err={max(errs):.3e}", "n(n+1)(2n+1)/6 en n=1,2,5,10"

    def check_sum_indefinite_k():
        pool = _fresh_pool()
        k = pool.symbol("k")
        value = ak.sum_indefinite(ak.parse("k", pool, {}), k).value
        # Convención antidiferencia (Gosper): F con ΔF(k)=F(k+1)-F(k)=k,
        # o sea F(k)=k(k-1)/2. Verificamos ΔF(k)==k, independiente de la
        # constante de sumación.
        errs = []
        for kv in (1.0, 7.0, 40.0):
            fk = _eval_at(value, [(k, kv)])
            fkp1 = _eval_at(value, [(k, kv + 1.0)])
            errs.append(abs((fkp1 - fk) - kv))
        return (
            max(errs) < 1e-9,
            f"max|dF-k|={max(errs):.3e}, F(7)={_eval_at(value, [(k, 7.0)])!r}",
            "antidiferencia ΔF(k)=k, < 1e-9 (F=k(k-1)/2, F(7)=21)",
        )

    def check_nt_isprime():
        got = {
            "2**61-1": bool(_ant.isprime(2**61 - 1)),
            "2**32-1": bool(_ant.isprime(2**32 - 1)),
            "15485863": bool(_ant.isprime(15485863)),
        }
        expected = {"2**61-1": True, "2**32-1": False, "15485863": True}
        return got == expected, got, expected

    def check_nt_factorint():
        got = {str(p): int(e) for p, e in _ant.factorint(2**32 - 1).items()}
        expected = {"3": 1, "5": 1, "17": 1, "257": 1, "65537": 1}
        return got == expected, got, expected

    def check_nt_totient_nextprime():
        got = {"totient(97)": int(_ant.totient(97)), "nextprime(100)": int(_ant.nextprime(100))}
        expected = {"totient(97)": 96, "nextprime(100)": 101}
        return got == expected, got, expected

    def check_nt_isolated_fence():
        # Repro del crash: factorint(2^64+1) abortaba alkahest con SIGILL
        # in-process; el fence lo contiene y sympy lo resuelve. Con el
        # libflint sin ADX debe responder alkahest nativo.
        result = _nt_isolated("factorint", 2**64 + 1)
        expected = {"274177": 1, "67280421310721": 1}
        ok = (
            result.get("factors") == expected
            and result.get("engine") in ("alkahest", "sympy_fallback")
        )
        return (
            ok,
            f"engine={result.get('engine')}, factors={result.get('factors')}, "
            f"reason={result.get('fallback_reason', '-')}",
            "F6 = 274177 x 67280421310721 con motor declarado, sin crash",
        )

    def check_nt_libflint_no_adx():
        # El wheel original trae libflint con ADX (2626 patrones adcx/adox
        # en segmentos ejecutables): SIGILL en CPUs sin ADX (Haswell).
        # Tras el fix baseline debe quedar 0; cualquier reinstalación del
        # wheel roto vuelve a pasar este umbral y el check falla de forma
        # visible en vez de esconder el fallback de sympy.
        libs = Path(ak.__file__).resolve().parent.parent / "alkahest.libs"
        targets = sorted(libs.glob("libflint-*.so*"))
        counts = {p.name: _count_adx_exec(p) for p in targets}
        total = sum(c for c in counts.values() if c >= 0)
        ok = bool(targets) and total < 100
        return (
            ok,
            f"libflint={counts}, total_adx={total}",
            ">=1 libflint empaquetado y <100 patrones ADX "
            "(wheel original: 2626, fix baseline: 0)",
        )

    def check_derived_contract():
        pool = _fresh_pool()
        expr = ak.parse("sin(x^2)*exp(x)", pool, {})
        x = pool.symbol("x")
        result = ak.diff(expr, x)
        data = result.to_dict()  # debe ser JSON-safe sin excepciones
        dumped = json.dumps(data)
        steps = data.get("steps") or []
        ok = (
            0 < len(steps) <= 64
            and all("rule" in s and "before" in s and "after" in s for s in steps)
            and data.get("verification", {}).get("status")
            in {
                "certificate_available",
                "exactly_verified",
                "externally_asserted",
                "numerically_checked",
                "unverified",
            }
            and len(dumped) > 100,
        )
        return ok, f"steps={len(steps)}, bytes={len(dumped)}", "to_dict JSON-safe, steps con rule/before/after, verification status documentado"

    def check_certificate_lean():
        pool = _fresh_pool()
        expr = ak.parse("x^2", pool, {})
        x = pool.symbol("x")
        result = ak.integrate(expr, x, pool.integer(0), pool.integer(2))
        cert = result.certificate or ""
        status = (result.verification or {}).get("status")
        ok = (
            bool(result.certificate)
            and status == "certificate_available"
            and cert.lstrip().startswith("import Mathlib")
        )
        return (
            ok,
            f"has_certificate={bool(result.certificate)}, status={status}, "
            f"len={len(cert)}, head={cert[:20]!r}",
            "certificado Lean 4 con verificación certificate_available",
        )

    def check_matrix_eigenvals_2x2():
        pool = _fresh_pool()
        mat = ak.Matrix.from_rows(
            [
                [pool.integer(2), pool.integer(1)],
                [pool.integer(1), pool.integer(2)],
            ]
        )
        ev = {str(k): int(v) for k, v in mat.eigenvals().items()}
        ok = ev == {"1": 1, "3": 1}
        return (
            ok,
            f"eigenvals={ev}",
            "eigenvals exactos de [[2,1],[1,2]] = {1:1, 3:1} (A=I+2J)",
        )

    def check_matrix_inverse_residual():
        pool = _fresh_pool()
        a = ak.Matrix.from_rows(
            [
                [pool.integer(2), pool.integer(1)],
                [pool.integer(1), pool.integer(2)],
            ]
        )
        det = str(a.det())
        inv = _cells(a.inverse())
        prod = [
            [str(ak.simplify(c).value) for c in row]
            for row in a.multiply(a.inverse()).to_list()
        ]
        expected_inv = [["2/3", "-1/3"], ["-1/3", "2/3"]]
        expected_id = [["1", "0"], ["0", "1"]]
        ok = det == "3" and inv == expected_inv and prod == expected_id
        return (
            ok,
            f"det={det}, inv={inv}, A*A^-1={prod}",
            "det=3, A·A⁻¹=I y A⁻¹=[[2/3,-1/3],[-1/3,2/3]]",
        )

    def check_jacobian_analytic():
        pool = _fresh_pool()
        x, y = pool.symbol("x"), pool.symbol("y")
        jac = ak.jacobian(
            [ak.parse("x*y", pool, {}), ak.parse("y^2 - x", pool, {})], [x, y]
        )
        cells = jac.to_list()
        at_34 = [[_eval_at(c, [(x, 3.0), (y, 4.0)]) for c in row] for row in cells]
        expected = [[4.0, 3.0], [-1.0, 8.0]]
        ok = len(at_34) == 2 and all(
            abs(a - b) < 1e-9 for ra, rb in zip(at_34, expected) for a, b in zip(ra, rb)
        )
        return (
            ok,
            f"J(3,4)={at_34}",
            "jacobian de (x·y, y²−x) en (3,4) = [[4,3],[-1,8]]",
        )

    def check_diophantine_linear():
        pool = _fresh_pool()
        x, y = pool.symbol("x"), pool.symbol("y")
        sol = ak.diophantine(ak.parse("3*x + 5*y - 1", pool, {}), [x, y])
        residuals = []
        for t in (0.0, 1.0, -2.0):
            xt = _eval_at(sol.parametric[0], [(sol.parameter, t)])
            yt = _eval_at(sol.parametric[1], [(sol.parameter, t)])
            residuals.append(3 * xt + 5 * yt - 1.0)
        ok = sol.kind == "parametric_linear" and all(
            abs(r) < 1e-9 for r in residuals
        )
        return (
            ok,
            f"kind={sol.kind}, parametric=[{sol.parametric}], residuals={residuals}",
            "3x+5y=1 con solución paramétrica que satisface la ecuación",
        )

    def check_diophantine_pell():
        pool = _fresh_pool()
        x, y = pool.symbol("x"), pool.symbol("y")
        sol = ak.diophantine(
            ak.parse("x^2 - 2*y^2 - 1", pool, {}), [x, y]
        )
        fund = [str(c) for c in sol.fundamental]
        residual = (
            _eval_at(sol.fundamental[0], []) ** 2
            - 2 * _eval_at(sol.fundamental[1], []) ** 2
            - 1
        )
        ok = (
            sol.kind == "pell_fundamental"
            and fund == ["3", "2"]
            and abs(residual) < 1e-9
            and str(sol.pell_d) == "2"
        )
        return (
            ok,
            f"kind={sol.kind}, fundamental={fund}, residual={residual}, "
            f"pell_d={sol.pell_d}",
            "x²−2y²=1: fundamental (3,2) (16−2·4=1) y D=2",
        )

    def check_real_roots_intervals():
        pool = _fresh_pool()
        x = pool.symbol("x")
        poly = ak.parse("x^2 - 2", pool, {})
        roots = ak.real_roots(poly, x)
        sign_ok = all(
            _eval_at(poly, [(x, iv.lo)]) * _eval_at(poly, [(x, iv.hi)]) < 0
            for iv in roots
        )
        pos = [iv for iv in roots if iv.lo > 0][0]
        exact_lo = pos.lo_exact()
        none_roots = ak.real_roots(ak.parse("x^2 + 1", pool, {}), x)
        ok = (
            len(roots) == 2
            and sign_ok
            and pos.lo <= 1.0 <= 2.0 <= pos.hi
            and len(none_roots) == 0
        )
        return (
            ok,
            f"n_intervals={len(roots)}, sign_change={sign_ok}, "
            f"positive_iv=({pos.lo}, {pos.hi}), lo_exact={exact_lo}, "
            f"x^2+1-> {len(none_roots)} raíces",
            "x²−2: 2 intervalos aislados con cambio de signo que contienen ±√2; "
            "x²+1: sin raíces reales",
        )

    chk("diff_analytic_vs_numeric", check_diff)
    chk("integrate_definite_x2", check_integrate_definite)
    chk("integrate_definite_cos", check_integrate_cos)
    chk("simplify_rational", check_simplify_rational)
    chk("limit_sin_over_x", check_limit)
    chk("limit_bernoulli_inf", check_limit_bernoulli_inf)
    chk("sum_definite_basel_inf", check_sum_definite_basel_inf)
    chk("series_exp_truncation", check_series_exp)
    chk("solve_quadratic_roots", check_solve_quadratic)
    chk("solve_system_residuals", check_solve_system)
    chk("sum_definite_k2", check_sum_definite_k2)
    chk("sum_indefinite_k", check_sum_indefinite_k)
    chk("nt_isprime", check_nt_isprime)
    chk("nt_factorint", check_nt_factorint)
    chk("nt_totient_nextprime", check_nt_totient_nextprime)
    chk("nt_isolated_fence", check_nt_isolated_fence)
    chk("nt_libflint_no_adx", check_nt_libflint_no_adx)
    chk("derived_result_contract", check_derived_contract)
    chk("certificate_lean_export", check_certificate_lean)
    chk("matrix_eigenvals_2x2", check_matrix_eigenvals_2x2)
    chk("matrix_inverse_residual", check_matrix_inverse_residual)
    chk("jacobian_analytic", check_jacobian_analytic)
    chk("diophantine_linear", check_diophantine_linear)
    chk("diophantine_pell", check_diophantine_pell)
    chk("real_roots_intervals", check_real_roots_intervals)

    return {
        "mode": "validate",
        "validation_passed": all(c["passed"] for c in checks),
        "checks": checks,
        "engine": f"alkahest {ak.version()}",
    }


def _alkahest_cas_handler(args):
    mode = args.get("mode", "compute")
    if mode == "validate":
        return _validate()
    if mode != "compute":
        raise ValueError(f"mode desconocido: {mode}")
    return _compute(args)


register_tool(
    name="alkahest_cas_tool",
    schema=ALKAHEST_CAS_TOOL_SCHEMA,
    handler=lambda args: _alkahest_cas_handler(args),
)
