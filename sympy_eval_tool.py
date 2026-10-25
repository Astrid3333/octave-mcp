"""
sympy_eval_tool.py

SymPy (librería Python ya presente en el venv — es el oráculo que usa
examples/multi_cas_crosscheck.py) expuesto como tool CAS del servidor:
quinto motor del router cas_router_math_tool y motor de referencia en
proceso (sin subprocess).

Qué aporta respecto al resto del servidor:
- oráculo simbólico: el MISMO sympy que usa la batería de cross-check
  multi-CAS, ahora consultable desde el servidor
- dialecto Python: `x**2`, `diff(f, x)`, `integrate(f, x)`,
  `solve(e, x)`, `factorial(100)`, `laplace_transform(...)` vía
  sympify (verifica qué acepta el check de laplace en validate)
- comparación entre dialectos: cas_router_math_tool normaliza con
  sympy para calcular agreement en operation=crosscheck

Honestidad de alcance:
- evaluación EN PROCESO del servidor: `timeout` no corta nada (existe
  solo por compatibilidad con el router); una expr patológica puede
  tardar lo que tarde sympy
- sympify evalúa con eval de Python: entrada no confiable → riesgo
  (igual que sagebrush, que corre python arbitrario; el servidor es
  local y de confianza)
- NO factoriza enteros gigantes como motor dedicado ni tiene la
  profundidad de maxima/sagebrush en teoría de números; aporta
  portabilidad y cross-check, no especialización
- sin sesión entre llamadas: cada expr se sympify aislada

Modos:
- compute: eval (sympify + str, con simplify opcional) / guia.
- validate: autochequeos (aritmética, diff, integrate, solve,
  factorial 100 exacto vs math.factorial, laplace_transform, sqrt
  auto-simplificado, simplify de (x^2-4)/(x-2), valla de error).
"""

import math
import time

from tool_registry import register_tool

_VERSION = None


def _version():
    global _VERSION
    if _VERSION is None:
        try:
            import sympy
            _VERSION = "sympy %s" % sympy.__version__
        except Exception:  # noqa: BLE001
            _VERSION = "sympy (sin versión)"
    return _VERSION


SYMPY_EVAL_TOOL_SCHEMA = {
    "name": "sympy_eval_tool",
    "description": (
        "SymPy en proceso como CAS de cross-check: operation=eval "
        "sympifica una expresión en dialecto Python (x**2, diff, "
        "integrate, solve, factorial, laplace_transform...) con "
        "simplify opcional; guia documenta dialecto y límites. "
        "Quinto motor del cas_router_math_tool. mode=compute|validate."
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
                "enum": ["eval", "guia"],
                "description": "eval (default) | guia",
            },
            "expr": {
                "type": "string",
                "description": (
                    "operation=eval: expresión en dialecto Python/"
                    "sympy, ej \"diff(x**3, x)\" o \"2+2\"."
                ),
            },
            "simplify": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Si true, aplica sympy.simplify al resultado antes "
                    "de devolverlo (por defecto se devuelve tal cual)."
                ),
            },
            "timeout": {
                "type": "number",
                "default": 30,
                "description": (
                    "NO aplica (evaluación en proceso, sin corte); "
                    "existe por compatibilidad con el router."
                ),
            },
        },
        "required": ["mode"],
    },
}


def _eval_expr(expr, do_simplify=False):
    """sympify en proceso; nunca lanza, devuelve dict con ok/result."""
    if not isinstance(expr, str) or not expr.strip():
        return {"ok": False, "error": "expr vacío"}
    t0 = time.time()
    try:
        import sympy
        val = sympy.sympify(expr.strip())
        if do_simplify:
            val = sympy.simplify(val)
        return {
            "ok": True,
            "result": str(val),
            "seconds": round(time.time() - t0, 3),
        }
    except Exception as exc:  # noqa: BLE001 — el tool captura todo
        return {
            "ok": False,
            "error": "%s: %s" % (type(exc).__name__, str(exc)[:300]),
            "seconds": round(time.time() - t0, 3),
        }


def _guide():
    return {
        "ok": True,
        "operation": "guia",
        "engine": _version(),
        "guide": (
            "sympy_eval_tool: expresión en dialecto Python, sympify.\n"
            "Aritmética: 2+2, sqrt(8) -> 2*sqrt(2) (auto), "
            "factorial(100) exacto, binomial(n, k).\n"
            "Cálculo: diff(f, x) [diff(f, x, 2)], integrate(f, x), "
            "integrate(f, (x, a, b)), limit, series(f, x, 0, 5).\n"
            "Álgebra: solve(e, x), factor(p), expand(e), "
            "simplify(e) (pedir simplify=true para cancelar "
            "(x**2-4)/(x-2)).\n"
            "Transformadas: laplace_transform(f, t, s) devuelve tupla "
            "(F(s), convergence, cond) — str la muestra tal cual.\n"
            "Límites verificados: la eval es en PROCESO del servidor "
            "(timeout no corta); sin sesión entre llamadas; sympify "
            "usa eval de Python (entrada no confiable = riesgo, igual "
            "que sagebrush); para factores primos grandes usar "
            "sagebrush, para Laplace profundo maxima."
        ),
    }


def _compute(args):
    op = (args.get("operation") or "eval").strip().lower()
    if op == "guia":
        return _guide()
    if op == "eval":
        expr = args.get("expr")
        do_simplify = bool(args.get("simplify", False))
        out = _eval_expr(expr, do_simplify)
        return {"operation": op, "engine": _version(), **out}
    raise ValueError("operation debe ser eval|guia, no %r" % op)


def _validate():
    checks = []

    def chk(name, fn):
        try:
            passed, got, expected = fn()
        except Exception as exc:  # noqa: BLE001
            passed, got, expected = False, "%s: %s" % (
                type(exc).__name__, exc), "-"
        checks.append({
            "name": name,
            "passed": bool(passed),
            "got": str(got)[:300],
            "expected": str(expected)[:300],
        })

    def one(expr, simplify=False):
        r = _eval_expr(expr, simplify)
        if not r.get("ok"):
            raise RuntimeError(r.get("error") or "eval falló")
        return r["result"]

    def check_arithmetic():
        got = one("2+2")
        return got == "4", got, "4"

    def check_diff_cubic():
        got = one("diff(x**3, x)")
        return got == "3*x**2", got, "3*x**2"

    def check_integrate_square():
        got = one("integrate(x**2, x)")
        return got == "x**3/3", got, "x**3/3"

    def check_solve_quadratic():
        got = one("solve(x**2-4, x)")
        return got == "[-2, 2]", got, "[-2, 2]"

    def check_factorial_100_exact():
        got = one("factorial(100)")
        expected = str(math.factorial(100))
        return got == expected, got[-40:], (
            "100! exacto vs math.factorial (final)" + expected[-10:]
        )

    def check_laplace_sin():
        got = one("laplace_transform(sin(t), t, s)")
        return "1/(s**2 + 1)" in got, got, (
            "tupla con 1/(s**2 + 1) (convergence 0, True)"
        )

    def check_sqrt_auto():
        got = one("sqrt(8)")
        return got == "2*sqrt(2)", got, "2*sqrt(2) (auto-simplificación)"

    def check_simplify_flag():
        got = one("(x**2-4)/(x-2)", simplify=True)
        return got == "x + 2", got, "x + 2 (simplify=true cancela)"

    def check_error_fence():
        r = _eval_expr("diff(x**3, ")
        ok = (not r.get("ok") and bool(r.get("error")))
        return ok, "ok=%s error=%s" % (
            r.get("ok"), str(r.get("error"))[:80]), (
            "ok=false con error de sintaxis"
        )

    chk("sympy_arithmetic", check_arithmetic)
    chk("sympy_diff_cubic", check_diff_cubic)
    chk("sympy_integrate_square", check_integrate_square)
    chk("sympy_solve_quadratic", check_solve_quadratic)
    chk("sympy_factorial_100_exact", check_factorial_100_exact)
    chk("sympy_laplace_sin", check_laplace_sin)
    chk("sympy_sqrt_auto", check_sqrt_auto)
    chk("sympy_simplify_flag", check_simplify_flag)
    chk("sympy_error_fence", check_error_fence)

    return {
        "mode": "validate",
        "validation_passed": all(c["passed"] for c in checks),
        "checks": checks,
        "engine": _version(),
    }


def _sympy_eval_handler(args):
    mode = args.get("mode")
    if mode == "validate":
        return _validate()
    if mode == "compute":
        return _compute(args)
    raise ValueError("mode debe ser 'compute' o 'validate'")


register_tool(
    name="sympy_eval_tool",
    schema=SYMPY_EVAL_TOOL_SCHEMA,
    handler=_sympy_eval_handler,
)
