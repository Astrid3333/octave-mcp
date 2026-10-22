"""
sagebrush_math_tool.py

Sagebrush 0.7.2 (paquete PyPI `sagebrush`, entry-point `sagebrush-mcp`)
— CAS de teoría de números de investigación con motores Rust clean-room
(MIT/Apache-2.0) e interfaz Sage-compatible, sin necesitar Sage, PARI ni
FLINT instalados. Recomendación de pasted-7.txt, verificada en PyPI el
2026-10-22 (wstein@sagemath.com, 0.7.0 publicado 2026-10-10).

Qué aporta que ningún otro tool del servidor da hoy:
- factorización ECM de enteros grandes (factor(2^128+1) se resuelve)
- cuerpos numéricos: discriminante, base integral, grupos de clase
  (bajo GRH, como Sage/PARI), unidades, regulador
- formas modulares: newform_orbits con etiquetas LMFDB y polos
  característicos de Hecke demostrados
- curvas elípticas: conductor, rango, a_p
- álgebra lineal exacta sobre ZZ/QQ (Hermite, Smith, LLL)
- cálculo simbólico con verificación (toda antiderivada se chequea por
  diferenciación) y ODEs (desolve)

Integración por la API directa `sagebrush.session.Session` (el mismo
servidor upstream la usa internamente): una sesión persistente por
proceso MCP, con candado — las variables de operation=sage/python
persisten entre llamadas, operation=reinicia la sesión. Los atajos
factor/number_field/newforms corren aislados (isolated=True), igual que
el upstream, para no ensuciar la sesión. Cada run tiene su timeout y el
motor interrumpe (Ctrl-C) al superarlo; una sesión que no para se
reinicia sola (la respuesta trae restarted=True).

Modos:
- compute: operaciones sage / python / factor / number_field /
  newforms / reiniciar / guia (ver schema).
- validate: autochequeos contra referencias conocidas (factorización de
  2^64-1, primalidad de 2^127-1, clase 3 de Q(sqrt(-23)), forma
  nueva 11.2.a.a, conductor 37 de [0,0,1,-1,0], det de matriz ZZ,
  persistencia de sesión y valla de error 1/0).
"""

import json
import re
import threading

from tool_registry import register_tool

_VERSION_CACHE = None
_SESSION = None
_SESSION_LOCK = threading.Lock()

SAGEBRUSH_MATH_TOOL_SCHEMA = {
    "name": "sagebrush_math_tool",
    "description": (
        "Sagebrush 0.7.2 (motores Rust clean-room, sintaxis Sage, sin "
        "Sage/PARI/FLINT): teoría de números de investigación. ECM "
        "factor(2^128+1), cuerpos numéricos con grupos de clase (GRH), "
        "formas modulares newform_orbits con etiquetas LMFDB, curvas "
        "elípticas, álgebra lineal exacta ZZ/QQ (Hermite/Smith/LLL), "
        "cálculo simbólico verificado y desolve. Sesión sage persistente "
        "entre llamadas (reset reinicia); los atajos factor/"
        "number_field/newforms corren aislados."
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
                    "sage",
                    "python",
                    "factor",
                    "number_field",
                    "newforms",
                    "reiniciar",
                    "guia",
                ],
                "description": (
                    "compute: sage = código Sage en sesión persistente "
                    "(2^10, 1/3 exacto, R.<x>=QQ[]); python = Python plano "
                    "en la misma sesión; factor = factorización ECM "
                    "aislada; number_field = invariantes de Q[x]/(f) "
                    "aislado; newform_orbits de nivel/peso aislado; "
                    "reiniciar = borra la sesión; guia = lista de lo "
                    "implementado. Por defecto sage."
                ),
            },
            "code": {
                "type": "string",
                "description": (
                    "operation=sage|python: código a ejecutar, ej "
                    "\"K.<a> = NumberField(x^3 - 11); print(K.class_number())\"."
                ),
            },
            "n": {
                "type": "string",
                "description": (
                    "operation=factor: entero o expresión entera, ej "
                    "\"2^128 + 1\"."
                ),
            },
            "polynomial": {
                "type": "string",
                "description": (
                    "operation=number_field: polinomio irreducible en x, "
                    "ej \"x^3 - 11\"."
                ),
            },
            "level": {
                "type": "integer",
                "description": "operation=newforms: nivel N (>= 1).",
            },
            "weight": {
                "type": "integer",
                "description": "operation=newforms: peso k (>= 2, default 2).",
            },
            "include_plots": {
                "type": "boolean",
                "description": (
                    "Incluir el SVG completo de los plots (por defecto "
                    "solo resumen mime/bytes)."
                ),
            },
            "timeout": {
                "type": "number",
                "description": (
                    "Segundos antes de interrumpir (default: 60 sage/"
                    "python, 120 factor, 300 number_field/newforms; "
                    "máx 3600)."
                ),
            },
        },
        "required": ["mode"],
    },
}

_FACTOR_INT_RE = re.compile(r"[0-9\s\+\-\*/\(\)^]+")


def _version():
    global _VERSION_CACHE
    if _VERSION_CACHE is None:
        try:
            from importlib.metadata import version

            _VERSION_CACHE = "sagebrush %s" % version("sagebrush")
        except Exception:  # noqa: BLE001
            _VERSION_CACHE = "sagebrush (sin versión)"
    return _VERSION_CACHE


def _session():
    """Sesión persistente por proceso MCP (una sola, con candado)."""
    global _SESSION
    if _SESSION is None:
        try:
            from sagebrush.session import Session
        except ImportError as exc:  # noqa: TRY002
            raise ValueError(
                "sagebrush no está instalado "
                "(pip install sagebrush-mcp en el venv): %s" % exc
            )
        _SESSION = Session()
    return _SESSION


def _timeout(args, default):
    try:
        t = float(args.get("timeout") or default)
    except (TypeError, ValueError):
        t = float(default)
    return max(1.0, min(t, 3600.0))


def _run(code, mode, timeout, isolated=False, include_plots=False):
    with _SESSION_LOCK:
        r = _session().run(
            code, mode=mode, timeout=timeout, isolated=isolated
        )
    out = {
        "ok": not r.get("error"),
        "engine": _version(),
        "mode": mode,
    }
    if r.get("seconds") is not None:
        out["seconds"] = r["seconds"]
    if r.get("restarted"):
        out["restarted"] = True
    stdout = (r.get("stdout") or "").strip()
    if stdout:
        out["stdout"] = stdout
    if r.get("result") is not None:
        out["result"] = str(r["result"])
    displays = r.get("displays") or []
    if displays:
        plots = []
        for mime, data in displays:
            entry = {"mime": mime, "bytes": len(data)}
            if include_plots and len(data) <= 200_000:
                entry["data"] = data
            elif include_plots:
                entry["note"] = "SVG >200KB, omitido (include_plots)"
            plots.append(entry)
        out["plots"] = plots
    if r.get("error"):
        out["error"] = str(r["error"]).strip()
    return out


def _guide():
    try:
        from sagebrush.mcp_server import GUIDE

        return {
            "ok": True,
            "engine": _version(),
            "operation": "guia",
            "guide": GUIDE,
        }
    except ImportError as exc:  # noqa: TRY002
        raise ValueError("sagebrush no está instalado: %s" % exc)


def _compute(args):
    op = args.get("operation") or "sage"

    if op in ("sage", "python"):
        code = args.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("operation=%s requiere code" % op)
        return _run(
            code,
            mode=op,
            timeout=_timeout(args, 60),
            include_plots=bool(args.get("include_plots")),
        )

    if op == "reiniciar":
        with _SESSION_LOCK:
            _session().restart()
        return {
            "ok": True,
            "engine": _version(),
            "operation": op,
            "result": "Sesión reiniciada (variables borradas).",
        }

    if op == "guia":
        return _guide()

    if op == "factor":
        n = args.get("n")
        if not isinstance(n, str) or not n.strip():
            raise ValueError("operation=factor requiere n")
        n = n.strip()
        if not _FACTOR_INT_RE.fullmatch(n):
            raise ValueError(
                "n debe ser una expresión entera "
                "(dígitos y + - * / ^ paréntesis)"
            )
        code = "__n = Integer(%s)\nprint(factor(__n))" % n
        return {
            "operation": op,
            **_run(code, mode="sage", timeout=_timeout(args, 120), isolated=True),
        }

    if op == "number_field":
        poly = args.get("polynomial")
        if not isinstance(poly, str) or not poly.strip():
            raise ValueError("operation=number_field requiere polynomial")
        code = (
            "R.<x> = QQ[]\nK.<a> = NumberField(R(%s))\n" % json.dumps(poly.strip())
            + "print('field:', K)\nprint('degree:', K.degree())\n"
            "print('signature:', K.signature())\n"
            "print('discriminant:', K.discriminant(), '=', factor(K.discriminant()))\n"
            "print('integral basis:', K.integral_basis())\n"
            "G = K.class_group()\nprint('class group:', G, '(GRH)')\n"
            "print('class number:', K.class_number())\n"
            "U = K.unit_group()\nprint('unit group:', U)\n"
            "print('regulator:', K.regulator())\n"
        )
        return {
            "operation": op,
            **_run(code, mode="sage", timeout=_timeout(args, 300), isolated=True),
        }

    if op == "newforms":
        level = args.get("level")
        weight = args.get("weight", 2) or 2
        try:
            level = int(level)
            weight = int(weight)
        except (TypeError, ValueError):
            raise ValueError("operation=newforms requiere level entero")
        if level < 1:
            raise ValueError("level debe ser >= 1")
        if weight < 2:
            raise ValueError("weight debe ser >= 2")
        code = "for o in newform_orbits(%d, %d):\n    print(o)\n    print()" % (
            level,
            weight,
        )
        return {
            "operation": op,
            **_run(code, mode="sage", timeout=_timeout(args, 300), isolated=True),
        }

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

    def _sage_isolated(code, timeout=60):
        r = _run(code, mode="sage", timeout=timeout, isolated=True)
        if r.get("ok") is False:
            raise RuntimeError(r.get("error") or "run falló")
        return (r.get("stdout") or "").strip()

    def check_factor_2_64():
        got = _sage_isolated(
            "__n = Integer(2^64 - 1)\nprint(factor(__n))"
        )
        expected = "3 * 5 * 17 * 257 * 641 * 65537 * 6700417"
        return got == expected, got, expected

    def check_prime_mersenne():
        got = _sage_isolated("print(is_prime(2^127 - 1))")
        return got == "True", got, "True (2^127-1 es primo de Mersenne)"

    def check_rational_exact():
        got = _sage_isolated("print(Integer(1)/3 + Integer(1)/6)")
        return got == "1/2", got, "1/2 (aritmética exacta, no flotante)"

    def check_class_number_sqrt_minus_23():
        got = _sage_isolated(
            "R.<x> = QQ[]\nK.<a> = NumberField(x^2 + 23)\n"
            "print(K.class_number())"
        )
        return got == "3", got, "3 (Q(sqrt(-23)) clase 3, clásico)"

    def check_poly_factor():
        got = _sage_isolated(
            "R.<x> = QQ[]\nf = x^2 - 5*x + 6\nprint(f.factor())"
        )
        return got == "(x - 3) * (x - 2)", got, "(x - 3) * (x - 2)"

    def check_elliptic_conductor():
        got = _sage_isolated(
            "print(EllipticCurve([0,0,1,-1,0]).conductor())"
        )
        return got == "37", got, "37 (curva 37a1 de Cremona)"

    def check_symbolic_diff():
        got = _sage_isolated("print(diff(sin(x^2)*exp(x), x))")
        ok = ("cos(x^2)" in got) and ("e^x" in got)
        return ok, got, "contiene cos(x^2) y e^x (impresión Sage)"

    def check_linalg_det_zz():
        got = _sage_isolated("print(matrix(ZZ, [[1,2],[3,4]]).det())")
        return got == "-2", got, "-2 (det exacto sobre ZZ)"

    def check_newform_11_2():
        got = _sage_isolated(
            "for o in newform_orbits(11, 2):\n    print(o)", timeout=120
        )
        ok = got.startswith("11.2.a.a") and "q - 2*q^2" in got
        return ok, got, "etiqueta 11.2.a.a con q-expansión"

    def check_session_persistence():
        r1 = _run("_sbp = 21", mode="sage", timeout=30)
        if r1.get("ok") is False:
            return False, r1.get("error"), "asignación en sesión viva"
        r2 = _run("print(_sbp * 2)", mode="sage", timeout=30)
        got = (r2.get("stdout") or "").strip()
        return got == "42", got, "42 (la variable sobrevive entre llamadas)"

    def check_error_fence():
        r = _run("1/0", mode="sage", timeout=30)
        ok = (r.get("ok") is False) and bool(r.get("error"))
        return ok, f"ok={r.get('ok')}, error={str(r.get('error'))[:80]}", (
            "1/0 -> ok=false con mensaje (ZeroDivisionError capturado)"
        )

    chk("sagebrush_factor_2_64", check_factor_2_64)
    chk("sagebrush_prime_mersenne", check_prime_mersenne)
    chk("sagebrush_rational_exact", check_rational_exact)
    chk("sagebrush_class_number_sqrt_minus_23", check_class_number_sqrt_minus_23)
    chk("sagebrush_poly_factor", check_poly_factor)
    chk("sagebrush_elliptic_conductor_37", check_elliptic_conductor)
    chk("sagebrush_symbolic_diff", check_symbolic_diff)
    chk("sagebrush_linalg_det_zz", check_linalg_det_zz)
    chk("sagebrush_newform_11_2", check_newform_11_2)
    chk("sagebrush_session_persistence", check_session_persistence)
    chk("sagebrush_error_fence", check_error_fence)

    return {
        "mode": "validate",
        "validation_passed": all(c["passed"] for c in checks),
        "checks": checks,
        "engine": _version(),
    }


def _sagebrush_math_handler(args):
    mode = args.get("mode")
    if mode == "validate":
        return _validate()
    if mode == "compute":
        return _compute(args)
    raise ValueError("mode debe ser 'compute' o 'validate'")


register_tool(
    name="sagebrush_math_tool",
    schema=SAGEBRUSH_MATH_TOOL_SCHEMA,
    handler=lambda args: _sagebrush_math_handler(args),
)
