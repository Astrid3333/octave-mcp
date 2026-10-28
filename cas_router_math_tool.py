"""cas_router_math_tool — router unificado de CAS.

Enruta una consulta al motor mas adecuado entre los cinco CAS ya
integrados en el servidor (maxima, sagebrush, lispium, cadabra2,
sympy) y, si
`fallback=true`, encadena los restantes hasta encontrar uno que
responda ok. NO traduce sintaxis: el usuario escribe la consulta en la
sintaxis del motor objetivo; la tool decide el motor (o respeta
`engine` explicito) y reporta el camino (`routed_by`, `attempts`).

Uso tipico (mode=compute, operation=eval):
  {"query": "diff(x^3, x)"}                        -> maxima (sniff)
  {"query": "eulerphi(100)"}                       -> sagebrush (sniff)
  {"query": "(expt 2 10)"}                         -> lispium (sniff)
  {"query": "A_{m n} A^{n k}"}                     -> cadabra2 (sniff)
  {"query": "...", "field": "tensor"}              -> cadabra2 (hint)
  {"query": "(expt 2 10)", "engine": "maxima",
   "fallback": true}                               -> fallback a lispium

Uso crosscheck (mode=compute, operation=crosscheck):
  {"queries": {"maxima": "2+2", "lispium": "(+ 2 2)"}}   -> por motor
  {"query": "2+2", "engines": ["maxima", "sagebrush"]}    -> misma query
Compara los resultados normalizados (sympy si parsea, si no string)
y reporta agreement: agree | disagree | uncomparable.

Cada llamada invoca el handler registrado de la tool destino via
tool_registry (en proceso, sin wire ni recursión). Las respuestas de
cada engine se anidan crudas en `engine_result` y se normalizan en
`result` (string legible) + `attempts` (log por motor).
"""

import json
import re
import time

import cadabra2_math_tool  # noqa: F401 — registra su handler
import lispium_math_tool  # noqa: F401
import maxima_eval_tool  # noqa: F401
import pari_gp_tool  # noqa: F401
import sagebrush_math_tool  # noqa: F401
import sympy_eval_tool  # noqa: F401
from tool_registry import get_handler, register_tool

# sympy al final: la cadena de fallback existente (maxima ->
# sagebrush -> lispium) conserva su orden de intentos.
_ENGINES = ["maxima", "sagebrush", "lispium", "cadabra2", "sympy"]
_TOOL_BY_ENGINE = {
    "maxima": "maxima_eval_tool",
    "sagebrush": "sagebrush_math_tool",
    "lispium": "lispium_math_tool",
    "cadabra2": "cadabra2_math_tool",
    "sympy": "sympy_eval_tool",
}
_FIELD_MAP = {
    "tensor": "cadabra2",
    "tensores": "cadabra2",
    "fermion": "cadabra2",
    "fermions": "cadabra2",
    "fisica": "cadabra2",
    "physics": "cadabra2",
    "numero": "sagebrush",
    "numeros": "sagebrush",
    "number": "sagebrush",
    "integers": "sagebrush",
    "prime": "sagebrush",
    "primes": "sagebrush",
    "factorizacion": "sagebrush",
    "laplace": "maxima",
    "ode": "maxima",
    "integral": "maxima",
    "calculo": "maxima",
    "calculus": "maxima",
    "lisp": "lispium",
}
_LATEX_RE = re.compile(r"\\partial|\\psi|\\sum|\\frac|_\{|\^\{")
_SAGE_RE = re.compile(
    r"euler_phi|is_prime|next_prime|class_group|newform|moebius"
    r"|EllipticCurve|NumberField|GF\(")
_MAXIMA_RE = re.compile(
    r"%e|%pi|diff\(|integrate\(|solve\(|matrix\(|block\(|ev\("
    r"|eulerphi\(")
_LISP_RE = re.compile(
    r"\((factor|diff|integrate|expt|modular|solve|simplify|gcd|lcm)\s"
    r"|^\(\s*[+\-*/^]")

CAS_ROUTER_TOOL_SCHEMA = {
    "name": "cas_router_math_tool",
    "description": (
        "Router unificado de CAS: enruta una consulta al motor adecuado "
        "entre maxima/sagebrush/lispium/cadabra2/sympy (sniffing + hint "
        "`field` + `engine` explicito) con cadena de fallback y log de "
        "intentos, o compara varios motores con operation=crosscheck. "
        "Sin traduccion de sintaxis. mode=compute (operation=eval, "
        "operation=crosscheck, operation=guia) o mode=validate "
        "(15 checks)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["compute", "validate"],
                "description": "compute | validate",
            },
            "operation": {
                "type": "string",
                "enum": ["eval", "crosscheck", "guia"],
                "description": "eval (default) | crosscheck | guia",
            },
            "query": {
                "type": "string",
                "description": (
                    "Consulta en la sintaxis del motor elegido/ruteado. "
                    "Requerida para operation=eval; en crosscheck se "
                    "reenvia tal cual a cada motor de `engines`."
                ),
            },
            "queries": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": (
                    "Por motor: {\"maxima\": \"2+2\", \"lispium\": \"(+ 2 "
                    "2)\"}. En crosscheck, alternativa a query+engines "
                    "(dialecto propio por motor)."
                ),
            },
            "engines": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["maxima", "sagebrush", "lispium",
                             "cadabra2", "sympy"],
                },
                "description": (
                    "Motores destino en operation=crosscheck cuando se "
                    "usa `query` unica (>=2). La query unica debe ser "
                    "valida en los dialectos elegidos (sin traduccion); "
                    "si un motor la acepta sin devolver valor, queda "
                    "fuera de la comparacion."
                ),
            },
            "engine": {
                "type": "string",
                "enum": ["auto", "maxima", "sagebrush", "lispium",
                         "cadabra2", "sympy"],
                "default": "auto",
                "description": "Motor explicito o auto (default).",
            },
            "field": {
                "type": "string",
                "description": (
                    "Hint de dominio: tensor/fisica, numero/prime, "
                    "laplace/ode/calculo, lisp."
                ),
            },
            "fallback": {
                "type": "boolean",
                "default": True,
                "description": (
                    "Si true y el primer motor falla, prueba los demas."
                ),
            },
            "timeout": {
                "type": "number",
                "default": 30,
                "description": "Timeout por intento (se pasa a cada engine.",
            },
        },
        "required": ["mode"],
    },
}


def _engine_args(engine, query, timeout):
    """Argumentos de tools/call para el handler del engine destino."""
    if engine == "maxima":
        return {"mode": "compute", "operation": "eval",
                "expr": query, "timeout": timeout}
    if engine == "sagebrush":
        return {"mode": "compute", "operation": "sage",
                "code": query, "timeout": timeout}
    if engine == "cadabra2":
        # El dialecto "expresion" de cadabra2 es la forma Ex (LaTeX-ish):
        # se envuelve en evaluate(Ex(...)) para que el eval-python la corra.
        code = "print(str(evaluate(Ex(%s))))" % json.dumps(query)
        return {"mode": "compute", "operation": "eval",
                "code": code, "timeout": timeout}
    if engine == "sympy":
        return {"mode": "compute", "operation": "eval",
                "expr": query, "timeout": timeout}
    # lispium: operation=eval + code (s-expr crudo)
    return {"mode": "compute", "operation": "eval",
            "code": query, "timeout": timeout}


def _call_engine(engine, query, timeout):
    """Invoca el handler registrado del engine; nunca lanza."""
    handler = get_handler(_TOOL_BY_ENGINE[engine])
    if handler is None:
        return {"ok": False, "error": "handler no registrado"}
    try:
        return handler(_engine_args(engine, query, timeout))
    except Exception as exc:  # noqa: BLE001 — el router captura todo
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}


def _result_str(engine, r):
    """String legible de la respuesta cruda de un engine."""
    if engine == "maxima":
        return r.get("result")
    if engine == "sagebrush":
        return r.get("stdout")
    if engine == "lispium":
        return r.get("result")
    if engine == "sympy":
        return r.get("result")
    return r.get("stdout")  # cadabra2


def _error_str(engine, r):
    err = r.get("error") or ""
    if not err and engine == "maxima":
        err = r.get("raw") or ""
    if not err and engine in ("sagebrush", "cadabra2", "lispium"):
        err = r.get("stderr") or ""
    if isinstance(err, str) and len(err) > 300:
        err = err[:300] + "..."
    return err


def _sniff(query, field):
    """Devuelve (engine, routed_by) sin ejecutar nada."""
    eng_field = _FIELD_MAP.get((field or "").strip().lower())
    if eng_field:
        return eng_field, "field-%s" % field.strip().lower()
    q = query or ""
    if _LATEX_RE.search(q):
        return "cadabra2", "auto-latex"
    if _SAGE_RE.search(q):
        return "sagebrush", "auto-number"
    if _LISP_RE.search(q):
        return "lispium", "auto-lisp"
    if _MAXIMA_RE.search(q):
        return "maxima", "auto-maxima"
    return "maxima", "default"


def _route_eval(args):
    query = args.get("query")
    if not query or not str(query).strip():
        raise ValueError("operation=eval requiere query")
    timeout = args.get("timeout", 30)
    fallback = args.get("fallback", True)
    engine = (args.get("engine") or "auto").strip().lower()

    if engine != "auto":
        if engine not in _ENGINES:
            raise ValueError(
                "engine desconocido %r; use uno de %s"
                % (engine, ", ".join(_ENGINES)))
        first, routed_by = engine, "explicit"
    else:
        first, routed_by = _sniff(query, args.get("field"))

    chain = [first] + [e for e in _ENGINES if e != first] if fallback \
        else [first]

    t0 = time.time()
    attempts = []
    winner = None
    for eng in chain:
        raw = _call_engine(eng, query, timeout)
        ok = bool(raw.get("ok"))
        attempts.append({
            "engine": eng,
            "ok": ok,
            "error": None if ok else _error_str(eng, raw),
        })
        if ok:
            winner = (eng, raw)
            break

    total = time.time() - t0
    if winner is None:
        return {
            "operation": "eval", "ok": False, "engine_used": None,
            "routed_by": routed_by, "fallback": fallback,
            "attempts": attempts, "result": None, "engine_result": None,
            "error": "ningun motor respondio ok", "seconds": total,
        }
    eng, raw = winner
    return {
        "operation": "eval", "ok": True, "engine_used": eng,
        "routed_by": routed_by, "fallback": fallback,
        "attempts": attempts, "result": _result_str(eng, raw),
        "engine_result": raw, "seconds": total,
    }


def _normalize(text):
    """Normaliza un resultado para comparar entre dialectos.

    Intenta sympy (con los ajustes de dialecto: ^ -> **, %e/%pi de
    maxima); si no parsea, devuelve el string tal cual (comparacion
    literal despues). Devuelve (valor, es_simbolico).
    """
    if text is None:
        return None, False
    s = str(text).strip()
    # lispium ecua el fuente en lineas '; ...': se descartan
    s = "\n".join(ln for ln in s.splitlines()
                  if not ln.lstrip().startswith(";")).strip()
    try:
        import sympy  # noqa: PLC0415 — import perezoso, dep opcional
        s2 = (s.replace("^", "**").replace("%e", "E")
              .replace("%pi", "pi").replace("%i", "I"))
        return sympy.sympify(s2), True
    except Exception:  # noqa: BLE001
        return s, False


def _agreement(results):
    """Compara los resultados ok: agree | disagree | uncomparable."""
    oks = [r for r in results if r["ok"] and r["result"] is not None]
    if len(oks) < 2:
        return "uncomparable"
    vals = [_normalize(r["result"]) for r in oks]
    if all(sym for _, sym in vals):
        first = vals[0][0]
        for other, _ in vals[1:]:
            try:
                import sympy  # noqa: PLC0415
                if sympy.simplify(first - other) != 0:
                    return "disagree"
            except Exception:  # noqa: BLE001
                return "uncomparable"
        return "agree"
    strs = [v for v, sym in vals if not sym]
    if len(strs) == len(vals):
        return "agree" if len(set(strs)) == 1 else "disagree"
    return "uncomparable"


def _route_crosscheck(args):
    """Corre la(s) query(s) en >=2 motores y compara resultados."""
    timeout = args.get("timeout", 30)
    queries = args.get("queries")
    if queries:
        if not isinstance(queries, dict):
            raise ValueError("queries debe ser un objeto {engine: query}")
        items = [(str(e).strip().lower(), str(q))
                 for e, q in queries.items()]
    else:
        query = args.get("query")
        if not query or not str(query).strip():
            raise ValueError(
                "operation=crosscheck requiere queries {engine: query} "
                "o query + engines")
        engines = args.get("engines") or _ENGINES
        if not isinstance(engines, list) or len(engines) < 2:
            raise ValueError(
                "engines debe listar >=2 motores (o use queries)")
        items = [(str(e).strip().lower(), str(query)) for e in engines]
    if len(items) < 2:
        raise ValueError("crosscheck necesita >=2 motores")
    for eng, _ in items:
        if eng not in _ENGINES:
            raise ValueError(
                "engine desconocido %r; use uno de %s"
                % (eng, ", ".join(_ENGINES)))

    t0 = time.time()
    results = []
    for eng, q in items:
        raw = _call_engine(eng, q, timeout)
        ok = bool(raw.get("ok"))
        results.append({
            "engine": eng,
            "ok": ok,
            "result": _result_str(eng, raw) if ok else None,
            "error": None if ok else _error_str(eng, raw),
        })
    agree = _agreement(results)
    return {
        "operation": "crosscheck", "ok": any(r["ok"] for r in results),
        "results": results, "agreement": agree,
        "seconds": time.time() - t0,
    }


def _guia():
    return {
        "tool": "cas_router_math_tool",
        "routing": (
            "1) engine explicito; 2) hint `field` (tensor/fisica -> "
            "cadabra2, numero/prime -> sagebrush, laplace/ode/calculo -> "
            "maxima, lisp -> lispium); 3) sniffing del query (latex "
            "\\partial/\\psi/_{{ -> cadabra2; eulerphi/classgroup/ -> "
            "sagebrush; (factor|expt|diff|... espaciado -> lispium; "
            "%e/%pi/diff( -> maxima); 4) default maxima."
        ),
        "fallback": (
            "Con fallback=true el intento 1 es el ruteado y luego se "
            "prueban maxima, sagebrush, lispium, cadabra2 en ese orden. "
            "El log completo queda en attempts[]."
        ),
        "syntax": (
            "El router NO traduce sintaxis: cada motor recibe el query "
            "crudo (maxima: expr sin ';'; sagebrush: codigo python; "
            "lispium: s-expr; cadabra2: codigo python-cadabra con Ex). "
            "Ver guia de cada tool para su dialecto."
        ),
        "engines": [
            {"engine": "maxima", "tool": "maxima_eval_tool",
             "forte": "calculo simbolico general, Laplace, ODE"},
            {"engine": "sagebrush", "tool": "sagebrush_math_tool",
             "forte": "teoria de numeros, factorizacion, newforms, python"},
            {"engine": "lispium", "tool": "lispium_math_tool",
             "forte": "Lisp numerico/simbolico, cross-check"},
            {"engine": "cadabra2", "tool": "cadabra2_math_tool",
             "forte": "tensores, fermiones, algebra fisica (LaTeX)"},
            {"engine": "sympy", "tool": "sympy_eval_tool",
             "forte": "oraculo en proceso, dialecto Python, "
                      "laplace_transform/solve/diff"},
        ],
        "crosscheck": (
            "operation=crosscheck corre una o mas queries en >=2 "
            "motores (queries {engine: query} con dialecto propio, o "
            "query unica + engines) y devuelve results[] por motor + "
            "agreement (agree/disagree/uncomparable) comparando con "
            "sympy cuando parsea y string cuando no."
        ),
    }


# ---------------------------------------------------------------- validate

def _check(name, fn):
    t0 = time.time()
    try:
        detail, passed = fn()
        err = None
    except Exception as exc:  # noqa: BLE001
        detail, passed, err = "", False, "%s: %s" % (type(exc).__name__, exc)
    return {
        "name": name, "passed": bool(passed),
        "detail": str(detail)[:300], "error": err,
        "seconds": round(time.time() - t0, 3),
    }


def _r(args):
    return _route_eval(args)


def _c_route_explicit():
    r = _r({"query": "(+ 1 2)", "engine": "lispium", "fallback": False})
    ok = r["ok"] and r["engine_used"] == "lispium" and r["routed_by"] == \
        "explicit" and "3" in (r["result"] or "")
    return "explicit lispium (+ 1 2) -> %r" % (r["result"] or r["error"]), ok


def _c_route_latex():
    r = _r({"query": "A_{m n} A^{n k}"})
    ok = r["ok"] and r["engine_used"] == "cadabra2" and \
        r["routed_by"] == "auto-latex"
    return "latex A_{m n} A^{n k} -> %s (%s)" % (
        r["engine_used"], r["routed_by"]), ok


def _c_route_maxima():
    r = _r({"query": "diff(x^3, x)"})
    ok = r["ok"] and r["engine_used"] == "maxima" and r["result"] == "3*x^2"
    return "diff(x^3,x) -> maxima %r" % r["result"], ok


def _c_route_number():
    r = _r({"query": "print(euler_phi(100))"})
    ok = r["ok"] and r["engine_used"] == "sagebrush" and \
        (r["result"] or "").strip() == "40"
    return "print(euler_phi(100)) -> sagebrush %r" % (
        r["result"] or "").strip(), ok


def _c_route_lisp():
    r = _r({"query": "(^ 2 10)"})
    ok = r["ok"] and r["engine_used"] == "lispium" and \
        "1024" in (r["result"] or "")
    return "(^ 2 10) -> lispium %r" % (r["result"] or ""), ok


def _c_field_hint():
    r = _r({"query": "A_{m n} g^{n k}", "field": "tensor", "engine": "auto"})
    ok = r["ok"] and r["engine_used"] == "cadabra2" and \
        r["routed_by"] == "field-tensor"
    return "field=tensor -> cadabra2 (%s)" % r["routed_by"], ok


def _c_field_laplace():
    r = _r({"query": "laplace(sin(t),t,s)", "field": "laplace"})
    ok = r["ok"] and r["engine_used"] == "maxima" and \
        r["routed_by"] == "field-laplace" and \
        (r["result"] or "").strip() == "1/(s^2+1)"
    return "field=laplace -> %s (%s) %r" % (
        r["engine_used"], r["routed_by"], r["result"]), ok


def _c_field_ode():
    r = _r({"query": "ode2('diff(y,x)+y=0,y,x)", "field": "ode"})
    ok = r["ok"] and r["engine_used"] == "maxima" and \
        r["routed_by"] == "field-ode" and "y =" in (r["result"] or "")
    return "field=ode -> %s (%s) %r" % (
        r["engine_used"], r["routed_by"], r["result"]), ok


def _c_fallback_chain():
    # Fuerza maxima (no entiende `^` prefix) con una query lisp que
    # lispium evalua: la cadena debe caer a sagebrush (falla) y luego
    # lispium (ok).
    r = _r({"query": "(^ 2 10)", "engine": "maxima", "fallback": True})
    ok = r["ok"] and r["engine_used"] == "lispium" and \
        len(r["attempts"]) == 3 and \
        [a["engine"] for a in r["attempts"]] == \
        ["maxima", "sagebrush", "lispium"]
    return "maxima falla, sagebrush falla, lispium ok -> %s (%d intentos)" % (
        r["engine_used"], len(r["attempts"])), ok


def _c_all_fail():
    r = _r({"query": "raise ValueError('boom')"})
    ok = (not r["ok"]) and r["engine_used"] is None and \
        len(r["attempts"]) == 5 and all(not a["ok"] for a in r["attempts"])
    return "raise en 5 motores -> ok=False, 5 intentos fallidos", ok


def _c_result_normalizado():
    r = _r({"query": "2 + 2", "engine": "maxima", "fallback": False})
    ok = r["ok"] and r["result"] == "4" and isinstance(r["engine_result"], dict)
    return "maxima 2+2 normalizado -> result=%r" % r["result"], ok


def _c_unknown_engine():
    try:
        _r({"query": "1", "engine": "wolfram", "fallback": False})
        return "no lanzo ValueError", False
    except ValueError as exc:
        return "ValueError: %s" % str(exc)[:80], "wolfram" in str(exc)


def _c_crosscheck_agree():
    r = _cas_router_math_handler({
        "mode": "compute", "operation": "crosscheck",
        "queries": {"maxima": "2+2", "sagebrush": "print(2+2)",
                    "lispium": "(+ 2 2)", "cadabra2": "2+2"}})
    ok = r["ok"] and r["agreement"] == "agree" and \
        all(x["ok"] for x in r["results"]) and len(r["results"]) == 4
    return "4 motores 2+2 -> agreement=%s (%s)" % (
        r["agreement"], ",".join(x["engine"] for x in r["results"])), ok


def _c_crosscheck_disagree():
    r = _cas_router_math_handler({
        "mode": "compute", "operation": "crosscheck",
        "queries": {"maxima": "2+2", "lispium": "(+ 2 3)"}})
    same = _cas_router_math_handler({
        "mode": "compute", "operation": "crosscheck",
        "query": "2+2", "engines": ["maxima", "cadabra2"]})
    ok = r["ok"] and r["agreement"] == "disagree" and \
        same["agreement"] == "agree" and len(same["results"]) == 2
    return "2+2 vs (+ 2 3) -> %s; query unica x2 -> %s" % (
        r["agreement"], same["agreement"]), ok


def _c_route_sympy():
    r = _r({"query": "diff(x**3, x)", "engine": "sympy",
            "fallback": False})
    ok = r["ok"] and r["engine_used"] == "sympy" and \
        r["result"] == "3*x**2"
    return "diff(x**3, x) -> sympy %r" % r["result"], ok


def _validate():
    checks = [
        _check("route_explicit", _c_route_explicit),
        _check("route_latex_tensor", _c_route_latex),
        _check("route_maxima_sniff", _c_route_maxima),
        _check("route_sagebrush_number", _c_route_number),
        _check("route_lisp_sniff", _c_route_lisp),
        _check("field_hint_tensor", _c_field_hint),
        _check("field_hint_laplace", _c_field_laplace),
        _check("field_hint_ode", _c_field_ode),
        _check("crosscheck_multi_dialect", _c_crosscheck_agree),
        _check("crosscheck_query_unica", _c_crosscheck_disagree),
        _check("fallback_chain", _c_fallback_chain),
        _check("all_fail_report", _c_all_fail),
        _check("result_normalizado", _c_result_normalizado),
        _check("route_sympy_explicit", _c_route_sympy),
        _check("unknown_engine_fence", _c_unknown_engine),
    ]
    passed = sum(1 for c in checks if c["passed"])
    return {
        "tool": "cas_router_math_tool",
        "engine": "cas-router 1.1 "
                  "(maxima+sagebrush+lispium+cadabra2+sympy)",
        "validation_passed": passed == len(checks),
        "checks_passed": passed,
        "checks_total": len(checks),
        "checks": checks,
    }


def _cas_router_math_handler(args):
    mode = (args.get("mode") or "").strip().lower()
    if mode == "validate":
        return _validate()
    if mode != "compute":
        raise ValueError("mode debe ser compute|validate, no %r" % mode)
    operation = (args.get("operation") or "eval").strip().lower()
    if operation == "guia":
        return {"operation": "guia", "ok": True, "guia": _guia()}
    if operation == "eval":
        return _route_eval(args)
    if operation == "crosscheck":
        return _route_crosscheck(args)
    raise ValueError(
        "operation debe ser eval|crosscheck|guia, no %r" % operation)


register_tool(
    name="cas_router_math_tool",
    schema=CAS_ROUTER_TOOL_SCHEMA,
    handler=_cas_router_math_handler,
)
