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
  a bit; el wrapper normaliza a entero exacto la ventana de bug
  n en {18,19,20} (lispium 0.16.0 devuelve float: 18!
  -> 6.402373705728e15); (fact n) NO existe (se devuelve sin evaluar)
- "binomiales exactos" -> con argumentos literales SI: si lispium
  devuelve float (binomial 100 50) el wrapper lo normaliza a
  math.comb exacto en `outputs`; con argumentos no literales queda el
  float del motor
- "Ferrari para cuárticas" -> CIERTO en casos exactos verificados
- NO factoriza enteros (eso es sagebrush/maxima), NO tiene Laplace/ilt
  (eso es maxima_eval_tool), NO da certificados DerivedResult (alkahest)
- funciones desconocidas se devuelven SIN evaluar y con exit 0
  (ruido silencioso, cubierto por un check de validate)
- prime? en lispium solo fiable hasta ~2^53: literales mayores dan
  Eval error y expresiones mayores devuelven 0 aunque el número sea
  primo (bug 0.16.0: M61 salia 0). El WRAPPER reescribe
  (prime? X) cuando |X| > 2^53 se evalúa a entero exacto y decide con
  Miller-Rabin propio (bases fijas; determinista hasta ~3.3e24,
  más allá es empírico), emitiendo ((lambda (v) 0|1) X) y restaurando
  el form original en `result`. Operandos no evaluables quedan al
  motor tal cual.

Integración one-shot: cada llamada escribe un archivo .lspm temporal y
ejecuta `lispium run <archivo>` con timeout — no hay sesión entre
llamadas (define + usa en la misma llamada). Salida por bloque
`; <expr>` + valor, parseada a `outputs`.

Modos:
- compute: eval / diff / integrate / solve / factor / modular / guia.
- validate: autochequeos contra referencias conocidas (factorial 100
  exacto vs math.factorial, ventana 18 exacta tras normalización,
  función desconocida silenciosa, binomial 100 50 exacta vs
  math.comb, diff/integrate/solve/factor, modpow vs pow(), prime?
  97/100 + M61/M67/M127 vía wrapper, det/eigenvalues/linsolve,
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
_PRIMEQ_HEAD = "(prime?"
_FACTORIAL_LIT_RE = re.compile(r"^\(factorial\s+(-?\d+)\s*\)$")
_BINOMIAL_LIT_RE = re.compile(r"^\(binomial\s+(\d+)\s+(\d+)\s*\)$")
_BIGF = 1 << 53


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


def _extract_sexpr(src, start):
    """Índice justo después del s-expression balanceado en src[start]=='('."""
    depth = 0
    i = start
    while i < len(src):
        c = src[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def _apply_int_op(op, args):
    if op == "+" and args:
        return sum(args)
    if op == "*" and args:
        r = 1
        for a in args:
            r *= a
        return r
    if op == "-" and args:
        v = args[0]
        if len(args) == 1:
            return -v
        for a in args[1:]:
            v -= a
        return v
    if op == "/" and len(args) == 2 and args[1] != 0 and args[0] % args[1] == 0:
        return args[0] // args[1]
    if op == "^" and len(args) == 2 and 0 <= args[1] <= 4096:
        a, e = args
        if abs(a) > 1 and e * abs(a).bit_length() > 4_000_000:
            return None
        return a ** e
    return None


def _eval_int_sexpr(s):
    """Evalúa una s-expression aritmética de enteros; None si no es exacta."""
    n = len(s)
    pos = [0]

    def skip():
        while pos[0] < n and s[pos[0]].isspace():
            pos[0] += 1

    def parse():
        skip()
        if pos[0] >= n:
            return None
        c = s[pos[0]]
        if c == "(":
            pos[0] += 1
            skip()
            if pos[0] >= n or s[pos[0]] != "(":
                # operador atómico obligatorio: (+ 1 2), no ((f x) y)
                if pos[0] >= n or s[pos[0]] in ")":
                    return None
                op = ""
                while pos[0] < n and not s[pos[0]].isspace() and s[pos[0]] != ")":
                    op += s[pos[0]]
                    pos[0] += 1
            else:
                return None
            args = []
            while True:
                skip()
                if pos[0] >= n:
                    return None
                if s[pos[0]] == ")":
                    pos[0] += 1
                    break
                v = parse()
                if v is None:
                    return None
                args.append(v)
            return _apply_int_op(op, args)
        if c == ")":
            return None
        atom = ""
        while pos[0] < n and not s[pos[0]].isspace() and s[pos[0]] not in "()":
            atom += s[pos[0]]
            pos[0] += 1
        if not _INT_RE.match(atom):
            return None
        return int(atom)

    v = parse()
    skip()
    if v is None or pos[0] != n:
        return None
    return v


def _isprime(n):
    """Miller-Rabin con bases fijas; determinista hasta ~3.3e24."""
    if n < 2:
        return False
    small = (
        2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37,
        41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97,
    )
    for p in small:
        if n % p == 0:
            return n == p
    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for a in small:
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _patch_primeq(src):
    """Reescribe `(prime? X)` con |X| > 2^53 evaluable a entero exacto.

    lispium 0.16.0 falla con operandos grandes (literal -> Eval error,
    expresión -> 0 aunque el valor sea primo). El wrapper calcula X y
    decide con `_isprime`, emitiendo `((lambda (v) 0|1) X)` — misma
    forma, valor correcto. Devuelve (src_nuevo, lista de
    (form_parcheado, form_original)) para restaurar el eco en `result`.
    """
    patches = []
    out = []
    i = 0
    while True:
        j = src.find(_PRIMEQ_HEAD, i)
        if j < 0:
            out.append(src[i:])
            break
        end = _extract_sexpr(src, j)
        if end < 0:
            out.append(src[i:])
            break
        prev = src[j - 1] if j > 0 else " "
        after = src[j + len(_PRIMEQ_HEAD)] if j + len(_PRIMEQ_HEAD) < len(src) else ""
        if (prev.isalnum() or prev == "_") or after not in " \t\n(":
            out.append(src[i:j + len(_PRIMEQ_HEAD)])
            i = j + len(_PRIMEQ_HEAD)
            continue
        operand = src[j + len(_PRIMEQ_HEAD):end - 1]
        val = _eval_int_sexpr(operand.strip())
        if val is None or -_BIGF <= val <= _BIGF or val.bit_length() > 100000:
            out.append(src[i:end])
            i = end
            continue
        flag = "1" if (val > 0 and _isprime(val)) else "0"
        new_form = "((lambda (v) %s) %s)" % (flag, operand)
        out.append(src[i:j])
        out.append(new_form)
        patches.append((new_form, src[j:end]))
        i = end
    return "".join(out), patches


def _restore_primeq(body, patches):
    """Restaura `(prime? X)` originales en el eco de lispium.

    El motor normaliza espacios en su eco (`; <expr>`), asi que el
    parche se busca con un patron flexible a espacios.
    """
    for new_form, old_form in patches:
        esc = re.escape(new_form)
        pat = re.sub(r"(?:\\ )+", r"\\s+", esc)
        pat = pat.replace("\\\n", r"\s+").replace("\n", r"\s+")
        body = re.sub(pat, lambda _m, o=old_form: o, body)
    return body


def _blocks_pairs(stdout):
    """Bloques `; <expr>` + valor, conservando la expr."""
    pairs = []
    for chunk in (stdout or "").split("\n\n"):
        lines = [ln for ln in chunk.split("\n") if ln.strip()]
        if not lines:
            continue
        expr = None
        if lines[0].startswith("; "):
            expr = lines[0][2:].strip()
            lines = lines[1:]
        if lines:
            pairs.append((expr, "\n".join(lines).strip()))
    return pairs


def _normalize_exact(expr, val):
    """Literales (factorial n)/(binomial n k) float -> entero exacto."""
    if not expr or not val or not any(c in val for c in ".eE"):
        return val
    m = _FACTORIAL_LIT_RE.match(expr)
    if m and 0 <= int(m.group(1)) <= 100000:
        return str(math.factorial(int(m.group(1))))
    m = _BINOMIAL_LIT_RE.match(expr)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if 0 <= b <= a <= 100000:
            return str(math.comb(a, b))
    return val


def _run_lisp(code, timeout):
    """Ejecuta `lispium run` sobre un .lspm temporal one-shot."""
    if not isinstance(code, str) or not code.strip():
        raise ValueError("code/expression vacío")
    if not code.endswith("\n"):
        code += "\n"
    code, prime_patches = _patch_primeq(code)
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
            if prime_patches:
                body = _restore_primeq(body, prime_patches)
            out["result"] = body
            parsed = [
                _normalize_exact(expr, val) for expr, val in _blocks_pairs(stdout)
            ]
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
            "(prime? n) -> 1/0; el WRAPPER reescribe (prime? X) con "
            "|X| > 2^53 evaluable a entero exacto y decide con "
            "Miller-Rabin propio (determinista hasta ~3.3e24), "
            "restaurando el form original en `result`; operandos no "
            "evaluables quedan al motor (mayores: literal -> Eval "
            "error; expresión -> 0, bug 0.16.0). "
            "(factorial n) EXACTO: la ventana de bug n en "
            "{18,19,20} (float) se normaliza en `outputs`; "
            "(binomial n k) normalizado a entero con literales\n"
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

    def check_factorial_exact_window():
        # lispium 0.16.0 devuelve float en n=18..20; el wrapper
        # normaliza a entero exacto (math.factorial) en outputs.
        got = one("(factorial 18)")[0]
        expected = str(math.factorial(18))
        return (
            got == expected,
            got,
            "%s (exacto tras normalizar el float 6.402373705728e15)" % expected,
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

    def check_binomial_literal_exact():
        # lispium 0.16.0 devolvia 1.0089134454556418e29 (float);
        # el wrapper normaliza a math.comb con argumentos literales.
        got = one("(binomial 100 50)")[0]
        expected = str(math.comb(100, 50))
        return (
            got == expected,
            got[-40:],
            "%s (exacto; antes: 1.0089134454556418e29)" % expected[-40:],
        )

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

    def check_prime_mersenne61():
        # lispium 0.16.0 devolvia 0 con valor grande por expresión
        # aunque M61 es primo; el wrapper lo reescribe con MR.
        got = one("(prime? (- (^ 2 61) 1))")[0]
        return (
            got == "1",
            got,
            "1 (M61=2^61-1 primo; antes del wrapper: 0)",
        )

    def check_prime_mersenne127_literal():
        # literal grande: lispium daba Eval error; wrapper lo decide.
        got = one("(prime? 170141183460469231731687303715884105727)")[0]
        return got == "1", got, "1 (M127 literal; antes: Eval error)"

    def check_prime_composite_big():
        # ruta False del wrapper: M67 = 2^67-1 es compuesto.
        outs = one("(prime? 147573952589676412927)\n(prime? (- (^ 2 67) 1))")
        ok = outs[0] == "0" and outs[1] == "0"
        return ok, outs, ["0 (literal compuesto)", "0 (expresión compuesta)"]

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
    chk("lispium_factorial_exact_window", check_factorial_exact_window)
    chk("lispium_unknown_function_silent", check_unknown_function_silent)
    chk("lispium_binomial_small", check_binomial_small)
    chk("lispium_binomial_literal_exact", check_binomial_literal_exact)
    chk("lispium_diff_cubic", check_diff_cubic)
    chk("lispium_integrate_parts", check_integrate_parts)
    chk("lispium_solve_quadratic", check_solve_quadratic)
    chk("lispium_solve_quartic_exact", check_solve_quartic_exact)
    chk("lispium_factor_quadratic", check_factor_quadratic)
    chk("lispium_modpow_crosscheck", check_modpow_crosscheck)
    chk("lispium_prime_flags", check_prime_flags)
    chk("lispium_prime_mersenne61", check_prime_mersenne61)
    chk("lispium_prime_mersenne127_literal", check_prime_mersenne127_literal)
    chk("lispium_prime_composite_big", check_prime_composite_big)
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
