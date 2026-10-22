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
"""

import json
import math

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
        "totient/nextprime (teoría de números). Cada operación simbólica "
        "devuelve DerivedResult: value, steps (log de reglas de reescritura "
        "JSON-safe), verification (certificate_available/exactly_verified/"
        "...) y certificate (Lean 4, truncado a 4 KB). Modos: compute (una "
        "operación con expr/var/point/order/bounds/equations/n) y validate "
        "(autochequeos contra soluciones analíticas conocidas)."
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
                ],
                "description": (
                    "Operación a ejecutar en mode=compute. factorint/"
                    "isprime/totient/nextprime usan n; solve usa equations."
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
                "description": "Incógnitas de solve (default [var]).",
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


def _fresh_pool():
    """Pool nuevo por llamada: ExprPool es write-only y no se libera."""
    return ak.ExprPool()


def _to_expr(pool, value):
    if isinstance(value, bool):
        raise ValueError(f"valor no esperado: {value!r}")
    if isinstance(value, int):
        return pool.integer(value)
    if isinstance(value, float):
        return ak.parse(repr(float(value)), pool)
    return ak.parse(str(value), pool)


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


def _compute(args):
    _require_ak()
    op = args.get("operation")
    if not isinstance(op, str) or not op:
        raise ValueError("mode=compute requiere operation")

    pool = _fresh_pool()
    var = args.get("var") or "x"

    if op in ("factorint", "isprime", "totient", "nextprime"):
        if _ant is None:
            raise ValueError("alkahest.number_theory no disponible")
        n = args.get("n")
        if not isinstance(n, int) or isinstance(n, bool):
            raise ValueError(f"operation={op} requiere n entero")
        if op == "factorint":
            payload = {str(p): int(e) for p, e in _ant.factorint(n).items()}
        elif op == "isprime":
            payload = {"n": n, "isprime": bool(_ant.isprime(n))}
        elif op == "totient":
            payload = {"n": n, "totient": int(_ant.totient(n))}
        else:
            payload = {"n": n, "nextprime": int(_ant.nextprime(n))}
        return {"operation": op, "ok": True, **payload}

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

    expr_str = args.get("expr")
    if not isinstance(expr_str, str) or not expr_str.strip():
        raise ValueError(f"operation={op} requiere expr")

    expr = ak.parse(expr_str, pool, {})
    sym = pool.symbol(var)

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

    chk("diff_analytic_vs_numeric", check_diff)
    chk("integrate_definite_x2", check_integrate_definite)
    chk("integrate_definite_cos", check_integrate_cos)
    chk("simplify_rational", check_simplify_rational)
    chk("limit_sin_over_x", check_limit)
    chk("series_exp_truncation", check_series_exp)
    chk("solve_quadratic_roots", check_solve_quadratic)
    chk("solve_system_residuals", check_solve_system)
    chk("sum_definite_k2", check_sum_definite_k2)
    chk("sum_indefinite_k", check_sum_indefinite_k)
    chk("nt_isprime", check_nt_isprime)
    chk("nt_factorint", check_nt_factorint)
    chk("nt_totient_nextprime", check_nt_totient_nextprime)
    chk("derived_result_contract", check_derived_contract)
    chk("certificate_lean_export", check_certificate_lean)

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
