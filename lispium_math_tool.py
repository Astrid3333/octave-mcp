"""
lispium_math_tool.py

Lispium 0.16.0 (paquete PyPI `lispium`, binario Zig empaquetado por la
rueda `lispium` con su propio CLI) — CAS ligero de sintaxis Lisp.
Recomendación de pasted-7.txt, verificada en PyPI el 2026-10-22
(Tetraslam/lispium, MIT, sin dependencias de Python).

Qué aporta respecto al resto del servidor:
- segunda opinión independiente: motor nativo aislado (ni SymPy, ni
  Maxima, ni Sagebrush), útil para cross-check en ejemplos
- enteros exactos gigantes con (factorial n) (100! devuelto bit a bit)
- solve exacto de cuárticas (Ferrari): x^4-10x^2+9 -> {3, -3, 1, -1}
- álgebra lineal exacta y compacta: det/inv/eigenvalues/linsolve
- modpow/prime? modulares (cross-check con pow() de Python)

Honestidad de alcance (contraste con pasted-7.txt):
- "factoriales gigantes" -> CIERTO con (factorial n): 100! exacto bit
  a bit; VENTANA BUG n en {18, 19, 20} sale como float (18!
  -> 6.402373705728e15); (fact n) NO existe (se devuelve sin evaluar)
- "binomiales exactos" -> SOLO pequeños: binomial 10 3 = 120, pero
  binomial 100 50 -> 1.0089134454556418e29 (float, no el entero)
- "Ferrari para cuárticas" -> CIERTO en casos exactos verificados
- NO factoriza enteros (eso es sagebrush/maxima), NO tiene Laplace/ilt
  (eso es maxima_eval_tool), NO da certificados DerivedResult (alkahest)
- funciones desconocidas se devuelven SIN evaluar y con exit 0
  (ruido silencioso, cubierto por un check de validate)
- prime? SOLO fiable hasta ~2^53: literales mayores dan Eval error y
  valores construidos por expresión mayores devuelven 0 (bug 0.16.0:
  (prime? (- (^ 2 61) 1)) -> 0, pero M61 es primo; para primos
  grandes usar sagebrush_math_tool)

Integración one-shot: cada llamada escribe un archivo .lspm temporal y
ejecuta `lispium run <archivo>` con timeout — no hay sesión entre
llamadas (define + usa en la misma llamada). Salida por bloque
`; <expr>` + valor, parseada a `outputs`.

Modos:
- compute: eval / diff / integrate / solve / factor / modular / guia.
- validate: autochequeos contra referencias conocidas (factorial 100
  exacto vs math.factorial, ventana float 18, función desconocida
  silenciosa, binomial pequeño, diff/integrate/solve/factor, modpow vs
  pow(), prime? 97/100 + bug de prime? en M61, det/eigenvalues/linsolve,
  define+lambda y vallas de error Parse/Eval).
"""

import math
import os
import re
import subprocess
import tempfile
import time

from tool_registry import register_tool

_VERSION_CACHE = None

_LISPIUM_MATH_TOOL_SCHEMA = {
    "name": "lispium_math_tool",
    "description": (
        "Lispium 0.16.0 (binario Zig, sintaxis Lisp, sin deps Python): "
        "CAS ligero de cross-check. (factorial n) exacto gigante (con "
        "ventana float n=18..20), solve exacto de cuárticas, "
        "diff/integrate/factor de polinomios, det/eigenvalues/linsolve, "
        "modpow/prime?. Cada llamada corre en un archivo .lspm aparte "
        "(sin sesión entre llamadas). Ver guia para sintaxis y límites "
        "conocidos."
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
                    "eval",
                    "diff",
                    "integrate",
                    "solve",
                    "factor",
                    "modular",
                    "guia",
                ],
                "description": (
                    "compute: eval = código Lisp arbitrario; diff/"
                    "integrate/solve/factor = atajos sobre `expression` "
                    "y `variable`; modular = modpow(base, exponent, "
                    "modulus); guia = sintaxis + límites conocidos. "
                    "Por defecto eval."
                ),
            },
            "code": {
                "type": "string",
                "description": (
                    "operation=eval: código Lisp, una expresión por "
                    "línea, ej \"(diff (sin (* x x)) x)\". Las "
                    "definiciones (define ...) valen dentro de la misma "
                    "llamada."
                ),
            },
            "expression": {
                "type": "string",
                "description": (
                    "operation=diff|integrate|solve|factor: expresión "
                    "Lisp, ej \"(^ x 3)\" o \"(+ (^ x 2) (* -5 x) 6)\"."
                ),
            },
            "variable": {
                "type": "string",
                "description": (
                    "operation=diff|integrate|solve|factor: variable, "
                    "ej \"x\"."
                ),
            },
            "order": {
                "type": "integer",
                "description": "operation=diff: orden de la derivada (default 1).",
            },
            "base": {
                "type": "string",
                "description": "operation=modular: base entera, ej \"2\".",
            },
            "exponent": {
                "type": "string",
                "description": "operation=modular: exponente entero >= 0.",
            },
            "modulus": {
                "type": "string",
                "description": "operation=modular: módulo entero >= 1.",
            },
            "timeout": {
                "type": "number",
                "description": "Segundos antes de cortar (default 30, máx 3600).",
            },
        },
        "required": ["mode"],
    },
}

_INT_RE = re.compile(r"-?\d+$")
_ERROR_LINE_RE = re.compile(r"^[^\s:]+:\d+(:\d+)?: (Parse|Eval) error")


def _version():
    global _VERSION_CACHE
    if _VERSION_CACHE is None:
        try:
            from importlib.metadata import version

            _VERSION_CACHE = "lispium %s" % version("lispium")
        except Exception:  # noqa: BLE001
            _VERSION_CACHE = "lispium (sin versión)"
    return _VERSION_CACHE


def _binary():
    try:
        from lispium.cli import get_binary_path
    except ImportError as exc:  # noqa: TRY002
        raise ValueError(
            "lispium no está instalado (pip install lispium en el venv): %s"
            % exc
        )
    try:
        path = get_binary_path()
    except FileNotFoundError as exc:  # noqa: TRY002
        raise ValueError(str(exc))
    if os.name != "nt":
        try:
            mode = os.stat(path).st_mode
            if mode & 0o111 != 0o111:
                os.chmod(path, mode | 0o755)
        except OSError:
            pass
    return str(path)


def _timeout(args, default=30):
    try:
        t = float(args.get("timeout") or default)
    except (TypeError, ValueError):
        t = float(default)
    return max(1.0, min(t, 3600.0))


def _outputs(stdout):
    """Bloques separados por línea en blanco: `; <expr>` + valor."""
    blocks = []
    for chunk in (stdout or "").split("\n\n"):
        lines = [ln for ln in chunk.split("\n") if ln.strip()]
        if not lines:
            continue
        if lines[0].startswith("; "):
            lines = lines[1:]
        if lines:
            blocks.append("\n".join(lines).strip())
    return blocks


def _run_lisp(code, timeout):
    """Ejecuta `lispium run` sobre un .lspm temporal one-shot."""
    if not isinstance(code, str) or not code.strip():
        raise ValueError("code/expression vacío")
    if not code.endswith("\n"):
        code += "\n"
    bin_path = _binary()
    fd, path = tempfile.mkstemp(suffix=".lspm", prefix="lispium_", text=True)
    started = time.monotonic()
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(code)
        try:
            proc = subprocess.run(
                [bin_path, "run", path],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "engine": _version(),
                "error": "lispium no respondió en %gs" % timeout,
            }
        except FileNotFoundError:
            raise ValueError("binario de lispium no encontrado: %s" % bin_path)
        stdout = proc.stdout or ""
        stderr = (proc.stderr or "").strip()
        elapsed = round(time.monotonic() - started, 3)
        error_lines = [ln for ln in stdout.split("\n") if _ERROR_LINE_RE.match(ln)]
        if stderr:
            error_lines.append(stderr)
        out = {
            "ok": proc.returncode == 0,
            "engine": _version(),
            "exit_code": proc.returncode,
            "seconds": elapsed,
        }
        body = stdout.strip()
        if body:
            out["result"] = body
            parsed = _outputs(stdout)
            if parsed:
                out["outputs"] = parsed
        if proc.returncode != 0 or error_lines:
            out["error"] = "\n".join(error_lines).strip() or (
                "exit=%d sin mensaje" % proc.returncode
            )
        return out
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _guide():
    return {
        "ok": True,
        "engine": _version(),
        "operation": "guia",
        "guide": (
            "Lispium: CAS de sintaxis Lisp, una expresión por línea.\n"
            "Aritmética: (+ a b) (- a b c) (= a - b - c, RESTA TODO) "
            "(* a b) (^ a b) (/ a b)\n"
            "Cálculo: (diff e v) (diff e v n) (integrate e v) "
            "(taylor e v pt n) (simplify e) (expand e)\n"
            "Álgebra: (solve e v) incl. cuárticas exactas, "
            "(factor e v) polinomios, (substitute e v val) (collect e v)\n"
            "Lineal: (matrix (a b) (c d)) (det M) (inv M) (matmul A B) "
            "(eigenvalues M) (linsolve A b)\n"
            "Modular/enteros: (mod a b) (gcd a b) (modpow b e m) "
            "(prime? n) -> 1/0 SOLO fiable hasta ~2^53 (mayores: "
            "literal -> Eval error; por expresión -> devuelve 0, bug "
            "0.16.0: M61 sale 0), (factorial n) EXACTO excepto n en "
            "{18,19,20} (sale float, bug 0.16.0), (binomial n k) "
            "exacto solo pequeño\n"
            "Programación: (define f (lambda (x) ...)) (f 7) — solo "
            "dentro de la MISMA llamada (no hay sesión entre llamadas).\n"
            "Errores: función desconocida se devuelve SIN evaluar y con "
            "exit 0 ((fact 100) -> (fact 100), ruido silencioso); "
            "(/ 1 0) -> Eval error y exit 1; paréntesis sin "
            "cerrar -> Parse error, aborta el archivo (exit 1).\n"
            "Límites verificados (2026-10-22): taylor usa coeficientes "
            "float (no 1/6 exacto); simplify no cancela "
            "(x^2-4)/(x-2); NO factoriza enteros (sagebrush/ "
            "maxima); polygcd falla con argumentos polinomiales "
            "(bug 0.16.0)."
        ),
    }


def _compute(args):
    op = args.get("operation") or "eval"

    if op == "eval":
        code = args.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("operation=eval requiere code")
        return {"operation": op, **_run_lisp(code, _timeout(args))}

    if op == "guia":
        return _guide()

    if op in ("diff", "integrate", "solve", "factor"):
        expr = args.get("expression")
        var = args.get("variable") or "x"
        if not isinstance(expr, str) or not expr.strip():
            raise ValueError("operation=%s requiere expression" % op)
        if not isinstance(var, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", var):
            raise ValueError("variable debe ser un identificador, ej \"x\"")
        expr = expr.strip()
        if op == "diff":
            order = args.get("order", 1) or 1
            try:
                order = int(order)
            except (TypeError, ValueError):
                raise ValueError("order debe ser entero")
            if order < 1 or order > 50:
                raise ValueError("order debe estar en [1, 50]")
            code = "(diff %s %s %d)" % (expr, var, order) if order > 1 else "(diff %s %s)" % (expr, var)
        else:
            code = "(%s %s %s)" % (op, expr, var)
        return {"operation": op, **_run_lisp(code, _timeout(args))}

    if op == "modular":
        vals = {}
        for key, lo in (("base", None), ("exponent", 0), ("modulus", 1)):
            raw = args.get(key)
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError("operation=modular requiere %s" % key)
            raw = raw.strip()
            if not _INT_RE.match(raw):
                raise ValueError("%s debe ser entero" % key)
            val = int(raw)
            if lo is not None and val < lo:
                raise ValueError("%s debe ser >= %d" % (key, lo))
            vals[key] = val
        code = "(modpow %d %d %d)" % (vals["base"], vals["exponent"], vals["modulus"])
        return {"operation": op, **_run_lisp(code, _timeout(args))}

    raise ValueError("operation desconocida: %s" % op)


def _validate():
    checks = []

    def chk(name, fn):
        try:
            passed, got, expected = fn()
        except Exception as exc:  # noqa: BLE001
            passed, got, expected = False, f"{type(exc).__name__}: {exc}", "-"
        checks.append(
            {
                "name": name,
                "passed": passed,
                "got": str(got)[:300],
                "expected": str(expected)[:300],
            }
        )

    def one(code, timeout=30):
        r = _run_lisp(code, timeout)
        if r.get("ok") is False:
            raise RuntimeError(r.get("error") or "run falló")
        outs = r.get("outputs") or []
        if not outs:
            raise RuntimeError("sin outputs en: %s" % str(r.get("result"))[:80])
        return outs

    def check_arithmetic():
        got = one("(+ 1 2)")[0]
        return got == "3", got, "3"

    def check_factorial_100_exact():
        got = one("(factorial 100)")[0]
        expected = str(math.factorial(100))
        return got == expected, got[-40:], "100! exacto vs math.factorial (final)" + expected[-10:]

    def check_factorial_float_window():
        got = one("(factorial 18)")[0]
        return got == "6.402373705728e15", got, (
            "6.402373705728e15 (BUG documentado: n=18..20 sale float)"
        )

    def check_unknown_function_silent():
        r = _run_lisp("(fact 100)", 30)
        outs = r.get("outputs") or []
        ok = (r.get("ok") is True) and outs and outs[0] == "(fact 100)"
        return ok, outs, (
            "[(fact 100)] con exit 0 (función inexistente silenciosa)"
        )

    def check_binomial_small():
        got = one("(binomial 10 3)")[0]
        return got == "120", got, "120 (pequeños son exactos; ver guia para floats)"

    def check_diff_cubic():
        got = one("(diff (^ x 3) x)")[0]
        return got == "(* 3 (^ x 2))", got, "(* 3 (^ x 2))"

    def check_integrate_parts():
        got = one("(integrate (* x (exp x)) x)")[0]
        return got == "(* (- x 1) (exp x))", got, "(* (- x 1) (exp x)) = (x-1)e^x"

    def check_solve_quadratic():
        got = one("(solve (- (^ x 2) 4) x)")[0]
        return got == "(solutions 2 -2)", got, "(solutions 2 -2)"

    def check_solve_quartic_exact():
        got = one("(solve (+ (^ x 4) (* -10 (^ x 2)) 9) x)")[0]
        return got == "(solutions 3 -3 1 -1)", got, (
            "(solutions 3 -3 1 -1) (Ferrari exacto)"
        )

    def check_factor_quadratic():
        got = one("(factor (+ (^ x 2) (* -5 x) 6) x)")[0]
        return got == "(* (- x 3) (- x 2))", got, "(* (- x 3) (- x 2))"

    def check_modpow_crosscheck():
        got = one("(modpow 2 100 1000003)")[0]
        expected = str(pow(2, 100, 1000003))
        return got == expected, got, "%s (vs pow() de Python)" % expected

    def check_prime_flags():
        outs = one("(prime? 97)\n(prime? 100)")
        ok = outs[0] == "1" and outs[1] == "0"
        return ok, outs, ["1 (97 primo)", "0 (100 compuesto)"]

    def check_prime_mersenne61_bug():
        # Pin de bug 0.16.0: M61 = 2^61-1 ES primo de Mersenne, pero
        # prime? con valor grande por expresión devuelve 0. El check
        # pasa mientras el bug exista; si una versión futura lo arregla
        # hay que actualizar este pin y la guía.
        got = one("(prime? (- (^ 2 61) 1))")[0]
        return (
            got == "0",
            got,
            "0 (BUG: M61=2^61-1 es primo; sagebrush/sympy dicen True)",
        )

    def check_linear_algebra():
        outs = one(
            "(det (matrix (1 2) (3 4)))\n"
            "(eigenvalues (matrix (2 1) (1 2)))\n"
            "(linsolve (matrix (1 1) (1 -1)) (vector 3 1))"
        )
        ok = (
            outs[0] == "-2"
            and outs[1] == "(eigenvalues 3 1)"
            and outs[2] == "(vector 2 1)"
        )
        return ok, outs, ["-2", "(eigenvalues 3 1)", "(vector 2 1)"]

    def check_define_lambda():
        outs = one("(define f (lambda (x) (* x x)))\n(f 7)")
        ok = outs[0] == "<lambda>" and outs[1] == "49"
        return ok, outs, ["<lambda>", "49 (define+apply en una llamada)"]

    def check_error_fence_eval():
        r = _run_lisp("(/ 1 0)", 30)
        ok = (r.get("ok") is False) and ("Eval error" in (r.get("error") or ""))
        return (
            ok,
            f"ok={r.get('ok')}, error={str(r.get('error'))[:80]}",
            "ok=false con Eval error (exit != 0)",
        )

    def check_error_fence_parse():
        r = _run_lisp("(+ 1 2", 30)
        ok = (r.get("ok") is False) and ("Parse error" in (r.get("error") or ""))
        return (
            ok,
            f"ok={r.get('ok')}, error={str(r.get('error'))[:80]}",
            "ok=false con Parse error (archivo abortado)",
        )

    chk("lispium_arithmetic", check_arithmetic)
    chk("lispium_factorial_100_exact", check_factorial_100_exact)
    chk("lispium_factorial_float_window", check_factorial_float_window)
    chk("lispium_unknown_function_silent", check_unknown_function_silent)
    chk("lispium_binomial_small", check_binomial_small)
    chk("lispium_diff_cubic", check_diff_cubic)
    chk("lispium_integrate_parts", check_integrate_parts)
    chk("lispium_solve_quadratic", check_solve_quadratic)
    chk("lispium_solve_quartic_exact", check_solve_quartic_exact)
    chk("lispium_factor_quadratic", check_factor_quadratic)
    chk("lispium_modpow_crosscheck", check_modpow_crosscheck)
    chk("lispium_prime_flags", check_prime_flags)
    chk("lispium_prime_mersenne61_bug", check_prime_mersenne61_bug)
    chk("lispium_linear_algebra", check_linear_algebra)
    chk("lispium_define_lambda", check_define_lambda)
    chk("lispium_error_fence_eval", check_error_fence_eval)
    chk("lispium_error_fence_parse", check_error_fence_parse)

    return {
        "mode": "validate",
        "validation_passed": all(c["passed"] for c in checks),
        "checks": checks,
        "engine": _version(),
    }


def _lispium_math_handler(args):
    mode = args.get("mode")
    if mode == "validate":
        return _validate()
    if mode == "compute":
        return _compute(args)
    raise ValueError("mode debe ser 'compute' o 'validate'")


register_tool(
    name="lispium_math_tool",
    schema=_LISPIUM_MATH_TOOL_SCHEMA,
    handler=lambda args: _lispium_math_handler(args),
)
