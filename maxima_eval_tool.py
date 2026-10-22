"""
maxima_eval_tool.py

CAS Maxima 5.46 (descendiente de MACSYMA) vía CLI batch, pensado como
CAS alternativo para validación cruzada cuando Octave/SymPy/alkahest
no dan el resultado esperado (recomendación de pasted-5.txt: usar el
binario `maxima`, NO la GUI Xmaxima, que no acepta opciones).

Ejecución por llamada (sin estado):
    maxima --very-quiet --batch-string='<código>'
con display2d:false para salida de una línea y marcadores <<R>>/<<E>>
alrededor del resultado para poder parsearlo aunque el valor ocupe
varias líneas (p.ej. solve con varias soluciones).

Modos:
- compute / eval:  expr -> r: errcatch(expr); print(<<R>>); disp(r);
  print(<<E>>). errcatch convierte errores de Maxima en [] (el mensaje
  de error queda en stdout y se extrae); errores de sintaxis abortan el
  batch y se detectan por ausencia de marcadores.
- compute / batch: code -> sentencias Maxima crudas (sin errcatch),
  devuelve el stdout tal cual.
- validate: autochequeos contra referencias analíticas conocidas
  (∫x²=8/3, ∫cos=2, factorización de 2^64-1 = (2^32-1)(2^32+1),
  raíces de x²-5x+6, límite sin(x)/x, etc.) ejecutadas en el Maxima
  real del sistema.
"""

import re
import subprocess

from tool_registry import register_tool

_MAXIMA_BIN = "maxima"
_VERSION_CACHE = None

MAXIMA_EVAL_TOOL_SCHEMA = {
    "name": "maxima_eval_tool",
    "description": (
        "CAS Maxima 5.46 por CLI batch (maxima --batch-string, modo no "
        "interactivo; NO usa la GUI Xmaxima). Sirve como CAS alternativo "
        "para validación cruzada simbólica cuando Octave/SymPy/alkahest "
        "no dan el resultado esperado. Modos: compute (operation=eval "
        "evalúa expr con errcatch y devuelve el resultado de una línea; "
        "operation=batch ejecuta code con sentencias Maxima crudas) y "
        "validate (autochequeos contra referencias analíticas conocidas)."
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
                "enum": ["eval", "batch"],
                "description": (
                    "compute: eval = evaluar expr (seguro, con errcatch); "
                    "batch = sentencias crudas en code (por defecto eval)."
                ),
            },
            "expr": {
                "type": "string",
                "description": (
                    "Expresión Maxima para operation=eval, ej: "
                    "\"integrate(x^2, x, 0, 2)\" o "
                    "\"diff(sin(x^2)*exp(x), x)\"."
                ),
            },
            "code": {
                "type": "string",
                "description": (
                    "operation=batch: sentencias Maxima completas, ej: "
                    "\"load(facint)$ factor(2^64-1)$\". Finalizar con $ "
                    "si no se quiere ver el resultado."
                ),
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout en segundos (default 30).",
            },
        },
        "required": ["mode"],
    },
}


def _maxima_version():
    global _VERSION_CACHE
    if _VERSION_CACHE is None:
        try:
            proc = subprocess.run(
                [_MAXIMA_BIN, "--version"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            _VERSION_CACHE = proc.stdout.strip().splitlines()[0] if proc.stdout else "maxima"
        except (OSError, subprocess.TimeoutExpired, IndexError):
            _VERSION_CACHE = "maxima (sin versión)"
    return _VERSION_CACHE


def _run_batch(inner, timeout):
    """Ejecuta `display2d:false; <inner>` y devuelve (stdout, rc)."""
    batch = f"display2d:false; {inner}"
    try:
        proc = subprocess.run(
            [_MAXIMA_BIN, "--very-quiet", f"--batch-string={batch}"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise ValueError(f"Maxima no respondió en {timeout}s")
    except FileNotFoundError:
        raise ValueError(
            "maxima no está instalado (sudo apt-get install -y maxima)"
        )
    return (proc.stdout or "") + (proc.stderr or ""), proc.returncode


def _parse_markers(stdout):
    """Extrae el resultado entre <<R>> y <<E>>; None si faltan marcadores."""
    lines = stdout.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.strip() == '"<<R>>"':
            start = i
            break
    if start is None:
        return None
    end = None
    for i, ln in enumerate(lines):
        if i > start and 'print("<<E>>")' in ln:
            end = i
            break
    if end is None:
        return None
    zone = lines[start + 1:end]
    # La primera línea de la zona es SIEMPRE el eco de nuestro disp(...)
    # construido; se descarta sin mirar su texto.
    if zone:
        zone = zone[1:]
    while zone and zone[-1].strip() in ("", "done"):
        zone.pop()
    return "\n".join(zone).strip()


def _extract_error(stdout, result):
    """Mensaje de error de Maxima (errcatch -> [] o sintaxis)."""
    lines = stdout.splitlines()
    if result == "[]":
        r_echo = next(
            (i for i, ln in enumerate(lines) if ln.startswith("r:errcatch")),
            None,
        )
        mark = next(
            (i for i, ln in enumerate(lines) if ln.strip() == '"<<R>>"'),
            None,
        )
        if r_echo is not None and mark is not None:
            msg = []
            for ln in lines[r_echo + 1:mark]:
                s = ln.strip()
                if not s or s == "[]":
                    continue
                if s.startswith("print(") or s.startswith("<<R>>"):
                    break
                msg.append(s)
            if msg:
                return " ".join(msg)
        return "Maxima reportó un error (errcatch devolvió [])"
    if "incorrect syntax" in stdout:
        for ln in lines:
            if "incorrect syntax" in ln:
                return ln.strip()
    if "Lisp error" in stdout or "Maxima encountered" in stdout:
        for ln in lines:
            if "Lisp error" in ln or "Maxima encountered" in ln:
                return ln.strip()
    return "Maxima terminó sin marcadores de resultado (error de sintaxis?)"


def _eval_expr(expr, timeout):
    # errcatch devuelve [valor] o [] (error): first(r) desempaca el valor
    # real y is(equal(r,[])) protege el caso de error (first([]) fallaría).
    inner = (
        f"r: errcatch({expr}); "
        'print("<<R>>"); '
        "disp(if is(equal(r, [])) then [] else first(r)); "
        'print("<<E>>");'
    )
    stdout, rc = _run_batch(inner, timeout)
    result = _parse_markers(stdout)
    if result is None:
        return {
            "ok": False,
            "engine": _maxima_version(),
            "input": expr,
            "error": _extract_error(stdout, None),
            "raw": stdout.strip(),
        }
    if result == "[]":
        return {
            "ok": False,
            "engine": _maxima_version(),
            "input": expr,
            "error": _extract_error(stdout, result),
            "raw": stdout.strip(),
        }
    return {
        "ok": True,
        "engine": _maxima_version(),
        "input": expr,
        "result": result,
    }


def _compute(args):
    op = args.get("operation") or "eval"
    timeout = int(args.get("timeout") or 30)
    if op == "batch":
        code = args.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("operation=batch requiere code")
        stdout, rc = _run_batch(code, timeout)
        bad = (
            ("incorrect syntax" in stdout)
            or ("Lisp error" in stdout)
            or ("Maxima encountered" in stdout)
            or (rc != 0)
        )
        out = {
            "operation": op,
            "ok": not bad,
            "engine": _maxima_version(),
            "returncode": rc,
            "stdout": stdout.strip(),
        }
        if bad:
            out["error"] = _extract_error(stdout, None)
        return out

    expr = args.get("expr")
    if not isinstance(expr, str) or not expr.strip():
        raise ValueError("operation=eval requiere expr")
    r = _eval_expr(expr, timeout)
    return {"operation": op, **r}


def _validate():
    checks = []

    def chk(name, fn):
        try:
            passed, got, expected = fn()
        except Exception as exc:  # noqa: BLE001
            passed, got, expected = False, f"{type(exc).__name__}: {exc}", "-"
        checks.append(
            {"name": name, "passed": bool(passed), "got": str(got),
             "expected": str(expected)}
        )

    def ev(expr):
        r = _eval_expr(expr, 30)
        if not r.get("ok"):
            raise RuntimeError(f"eval falló: {r.get('error')}")
        return r["result"]

    def check_integrate_x2():
        got = ev("integrate(x^2, x, 0, 2)")
        return (
            got == "8/3",
            got,
            "8/3 (∫₀²x²dx = 8/3, integración directa de la potencia)",
        )

    def check_integrate_cos():
        got = ev("integrate(cos(x), x, 0, %pi)")
        return (
            got == "0",
            got,
            "0 (primitiva sen(x): sen(π)−sen(0) = 0−0)",
        )

    def check_diff_numeric():
        import math

        got = ev("float(subst(x = 1, diff(sin(x^2)*exp(x), x)))")
        ref = math.e * (2 * math.cos(1.0) + math.sin(1.0))
        val = float(got)
        return (
            abs(val - ref) < 1e-9,
            f"f'(1)={got} vs ref={ref:.12f}",
            "f'(1) = e·(2cos1 + sin1) (regla del producto + cadena)",
        )

    def check_solve_quadratic():
        got = ev("solve(x^2 - 5*x + 6, x)")
        ok = "x = 3" in got and "x = 2" in got
        return (
            ok,
            got,
            "soluciones exactas x=3 y x=2 (raíces de x²−5x+6 = "
            "(x−2)(x−3))",
        )

    def check_factor_2_64():
        got = ev("factor(2^64 - 1)")
        ref_factors = [3, 5, 17, 257, 641, 65537, 6700417]
        product_ok = 1
        for f in ref_factors:
            product_ok *= f
        product_ok = product_ok == 2**64 - 1
        parsed = [
            int(t) for t in re.findall(r"\d+", got.replace("*", " * "))
        ]
        ok = (
            product_ok
            and sorted(parsed) == sorted(ref_factors)
            and got.replace(" ", "") == "*".join(
                str(f) for f in ref_factors
            )
        )
        return (
            ok,
            got,
            "3·5·17·257·641·65537·6700417 = (2^32−1)(2^32+1) = 2^64−1",
        )

    def check_limit_sin_over_x():
        got = ev("limit(sin(x)/x, x, 0)")
        return (got == "1", got, "lim_{x→0} sin(x)/x = 1 (límite notable)")

    def check_taylor_exp():
        got = ev("ev(taylor(exp(x), x, 0, 5))")
        ok = (
            got.startswith("1+x+x^2/2+x^3/6+x^4/24")
            and "x^5/120" in got
            and "x^6" not in got
        )
        return (
            ok,
            got,
            "serie de e^x de Maxima hasta x^5 (taylor(...,0,5) incluye "
            "x^5; sin término x^6)",
        )

    def check_error_fence():
        r = _eval_expr("1/0", 30)
        ok = (r.get("ok") is False) and bool(r.get("error"))
        return (
            ok,
            f"ok={r.get('ok')}, error={str(r.get('error'))[:80]}",
            "división por cero -> ok=false con mensaje de error "
            "(errcatch no revienta el proceso)",
        )

    chk("maxima_integrate_x2", check_integrate_x2)
    chk("maxima_integrate_cos", check_integrate_cos)
    chk("maxima_diff_numeric", check_diff_numeric)
    chk("maxima_solve_quadratic", check_solve_quadratic)
    chk("maxima_factor_2_64_minus_1", check_factor_2_64)
    chk("maxima_limit_sin_over_x", check_limit_sin_over_x)
    chk("maxima_taylor_exp", check_taylor_exp)
    chk("maxima_error_fence", check_error_fence)

    return {
        "mode": "validate",
        "validation_passed": all(c["passed"] for c in checks),
        "checks": checks,
        "engine": _maxima_version(),
    }


def _maxima_eval_handler(args):
    mode = args.get("mode")
    if mode == "validate":
        return _validate()
    if mode == "compute":
        return _compute(args)
    raise ValueError("mode debe ser 'compute' o 'validate'")


register_tool(
    name="maxima_eval_tool",
    schema=MAXIMA_EVAL_TOOL_SCHEMA,
    handler=lambda args: _maxima_eval_handler(args),
)
