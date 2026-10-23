"""cadabra2_math_tool.py — Cadabra2 2.6.0 (Kasper Peeters) para octave-mcp.

CAS de algebra tensorial, fermiones y teoria de campos. Motor: modulo
python `cadabra2` (C++ .so) corriendo en un subprocess fresh por llamada
(las propiedades Indices/Metric/... son estado global del proceso, asi
que el aislamiento evita sangrado entre llamadas). Sin CLI `cdb` en la
wheel; version via importlib.metadata.

Patron identico a lispium_math_tool: mode=compute (ops estructuradas +
eval de codigo python cadabra libre) / mode=validate (checks con pins de
los quirks descubiertos en smoke). Todos los quirks y limites estan en
la guia.
"""

import importlib.metadata
import json
import os
import subprocess
import sys
import time

from tool_registry import register_tool

_VERSION_CACHE = None

_CADABRA2_MATH_TOOL_SCHEMA = {
    "name": "cadabra2_math_tool",
    "description": (
        "Cadabra2 2.6.0 (Kasper Peeters, modulo puro python+C++): CAS de "
        "algebra tensorial — canonicalise de indices, metricas, fermiones "
        "(sort_product+AntiCommuting), substitute, evaluate, simplify, "
        "puente a sympy. Cada llamada corre en un subprocess fresco (sin "
        "estado entre llamadas; declarar propiedades en el mismo codigo). "
        "Ver guia para quirks y limites conocidos."
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
                    "canonicalise",
                    "collect_terms",
                    "substitute",
                    "eliminate_metric",
                    "sort_product",
                    "distribute",
                    "evaluate",
                    "simplify",
                    "to_sympy",
                    "guia",
                ],
                "description": (
                    "compute: eval = codigo python cadabra arbitrario "
                    "(con prelude 'from cadabra2 import *'); las demas = "
                    "atajos sobre `ex` (y `rule` para substitute); guia = "
                    "API + quirks + limites. Por defecto eval."
                ),
            },
            "code": {
                "type": "string",
                "description": (
                    "operation=eval: codigo python con la API cadabra2, "
                    "ej \"print(str(canonicalise(Ex('A_{n m}'))))\". Las "
                    "propiedades declaradas valen solo dentro de la misma "
                    "llamada."
                ),
            },
            "ex": {
                "type": "string",
                "description": (
                    "operation estructurada: expresion en sintaxis "
                    "cadabra (latex), ej \"A_{m n} A^{n k}\" o "
                    "\"(x + 1)**2 - x**2 - 2*x - 1\"."
                ),
            },
            "rule": {
                "type": "string",
                "description": (
                    "operation=substitute: regla 'pat = val', ej "
                    "\"x = a + b\" o \"x^2 = a\"."
                ),
            },
            "timeout": {
                "type": "number",
                "description": "Segundos antes de cortar (default 30, max 3600).",
            },
        },
        "required": ["mode"],
    },
}

_PRELUDE = "from cadabra2 import *\n"

_INPLACE_OPS = (
    "canonicalise",
    "collect_terms",
    "sort_product",
    "distribute",
    "evaluate",
    "simplify",
    "eliminate_metric",
)


def _version():
    global _VERSION_CACHE
    if _VERSION_CACHE is None:
        try:
            _VERSION_CACHE = importlib.metadata.version("cadabra2")
        except importlib.metadata.PackageNotFoundError:
            _VERSION_CACHE = "not-installed"
    return _VERSION_CACHE


def _py():
    cand = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
    return cand if os.path.exists(cand) else sys.executable


def _timeout(args, default=30.0, cap=3600.0):
    raw = args.get("timeout") if isinstance(args, dict) else None
    try:
        val = float(raw) if raw is not None else default
    except (TypeError, ValueError):
        raise ValueError("timeout debe ser numerico")
    if val <= 0:
        raise ValueError("timeout debe ser > 0")
    return min(val, cap)


def _run_cadabra(code, timeout):
    payload = _PRELUDE + code
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            [_py(), "-c", payload],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "engine": _version(),
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "error": "timeout tras %gs" % timeout,
            "seconds": round(time.monotonic() - t0, 3),
        }
    out = {
        "ok": proc.returncode == 0,
        "engine": _version(),
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "seconds": round(time.monotonic() - t0, 3),
        "error": None,
    }
    if proc.returncode != 0:
        tail = (proc.stderr.strip().splitlines() or ["exit %d" % proc.returncode])
        out["error"] = tail[-1]
    return out


def _structured_code(op, ex, rule=None):
    ex_lit = json.dumps(ex)
    if op == "substitute":
        if not isinstance(rule, str) or not rule.strip():
            raise ValueError('operation=substitute requiere rule, ej "x = a"')
        return "_r = substitute(Ex(%s), Ex(%s))\nprint(str(_r))" % (
            ex_lit,
            json.dumps(rule),
        )
    if op == "to_sympy":
        return (
            "import sympy as _sp\n"
            "_r = SympyBridge(Ex(%s)).to_sympy()\n"
            "print(_sp.sstr(_r))" % ex_lit
        )
    if op in _INPLACE_OPS:
        return (
            "_ex = Ex(%s)\n"
            "_r = %s(_ex)\n"
            "print(str(_ex if _r is None else _r))" % (ex_lit, op)
        )
    raise ValueError("operation desconocida: %r" % op)


def _compute(args):
    op = args.get("operation") or "eval"

    if op == "guia":
        return _guide()

    if op == "eval":
        code = args.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("operation=eval requiere code")
        return {"operation": op, **_run_cadabra(code, _timeout(args))}

    ex = args.get("ex")
    if not isinstance(ex, str) or not ex.strip():
        raise ValueError("operation=%s requiere ex" % op)
    code = _structured_code(op, ex.strip(), args.get("rule"))
    res = _run_cadabra(code, _timeout(args))
    if res["ok"]:
        res["result"] = res["stdout"].rstrip("\n")
    return {"operation": op, **res}


def _guide():
    return {
        "ok": True,
        "engine": _version(),
        "operation": "guia",
        "guide": (
            "Cadabra2 2.6.0 (Kasper Peeters): algebra tensorial y teoria "
            "de campos. Sintaxis latex: A_{m n}, A^{m}, x^2 o x**2, "
            "\\partial_x{f}, \\delta_{m n}.\n"
            "Aislamiento: cada llamada es un subprocess fresco — las "
            "propiedades NO persisten; declarar TODO (propiedades + "
            "algoritmos) en el mismo operation=eval o en la misma llamada "
            "estructurada.\n"
            "Ops estructuradas (operation + ex): canonicalise (indices, "
            "muta in place, NO cancela terminos identicos), collect_terms "
            "(SI cancela identicos — correr DESPUES de canonicalise), "
            "sort_product (reordena factores no conmutativos), substitute "
            "(rule='pat = val'), evaluate (aritmetica: Ex('1 + 1') crudo "
            "queda '1 + 1'; evaluate -> 2), simplify (expande y cancela "
            "polinomios), distribute (distribuye productos: x*(y+z) -> "
            "x y + x z; NO expande potencias), eliminate_metric (g_{m n} "
            "g^{n k} -> g_{m}^{k}), to_sympy (SympyBridge.to_sympy).\n"
            "Propiedades (en operation=eval, ANTES del algoritmo): "
            "AntiSymmetric(Ex('A_{m n}')), Indices(Ex('m, n, k'), "
            "Ex('position = fixed')), Metric(Ex('g_{m n}')), "
            "SortOrder(Ex('a, b')), AntiCommuting(Ex('psi_1, psi_2')). "
            "Las list-properties SOLO aceptan Ex con comas (Ex('m') -> "
            "RuntimeError 'A list property cannot be assigned to a "
            "single object').\n"
            "Fermiones: SortOrder + AntiCommuting -> sort_product -> "
            "collect_terms da 0 sobre psi_1 psi_2 + psi_2 psi_1 "
            "(canonicalise NO reordena factores).\n"
            "Quirks/limites (pins en validate): expand((x+y)**2) no "
            "expande (usar simplify); substitute NO desciende a la base "
            "de una potencia (x^2 + y con x = a+b queda igual; usar "
            "patron completo x^2 = a); Ex() NUNCA lanza ante input "
            "malformado — trunca en silencio (')' -> '', 'x +' -> 'x'), "
            "el unico error real es de python (sintaxis del code); "
            "delta de Kronecker NO contrae (\\delta_{m n} A^m -> "
            "\\delta^{m}_{n} A_{m} tras canonicalise+reduce_delta; "
            "eliminate_metric si funciona); puente sympy con '^' roto "
            "(x^2 -> simbolo 'x(UP2)') — escribir x**2 para potencias "
            "escalares; map_sympy devuelve artefacto ('\\sum(x^{2})()') "
            "— no usar; help() de funciones falla (manual .cnb no "
            "incluido en la wheel); sin binario cdb ni __version__ "
            "(version: importlib.metadata.version('cadabra2') = 2.6.0)."
        ),
    }


def _validate():
    checks = []

    def chk(name, code, expect, timeout=60.0):
        r = _run_cadabra(code, timeout)
        if r["ok"]:
            got = r["stdout"].splitlines()
            passed = got == expect
        else:
            got = ["<error: %s>" % (r["error"] or "fail")]
            passed = False
        checks.append(
            {
                "name": name,
                "passed": passed,
                "expected": expect,
                "got": got,
            }
        )

    chk(
        "cadabra2_basic_eval",
        "print(str(Ex(r'A_x B^x')))",
        ["A_{x} B^{x}"],
    )
    chk(
        "cadabra2_antisym_canonicalise",
        "AntiSymmetric(Ex(r'A_{m n}'))\n"
        "print(str(canonicalise(Ex(r'A_{n m}'))))",
        ["-A_{m n}"],
    )
    chk(
        "cadabra2_derivative_commutator_pipeline",
        "ex = Ex(r'\\partial_x{f} \\partial_y{f} - "
        "\\partial_y{f} \\partial_x{f}')\n"
        "canonicalise(ex)\n"
        "collect_terms(ex)\n"
        "print(str(ex))",
        ["0"],
    )
    chk(
        "cadabra2_metric_elimination",
        "Indices(Ex(r'm, n, k'), Ex(r'position = fixed'))\n"
        "Metric(Ex(r'g_{m n}'))\n"
        "print(str(eliminate_metric(Ex(r'g_{m n} g^{n k}'))))",
        ["g_{m}^{k}"],
    )
    chk(
        "cadabra2_substitute_scalar",
        "print(str(substitute(Ex(r'x + y'), Ex(r'x = a'))))",
        ["a + y"],
    )
    chk(
        "cadabra2_substitute_power_full_pattern",
        "print(str(substitute(Ex(r'x^2 + y'), Ex(r'x^2 = a'))))",
        ["a + y"],
    )
    chk(
        "cadabra2_substitute_power_base_pin",
        "print(str(substitute(Ex(r'x^2 + y'), Ex(r'x = a + b'))))",
        ["x^{2} + y"],
    )
    chk(
        "cadabra2_grassmann_sort",
        "SortOrder(Ex(r'\\psi_1, \\psi_2'))\n"
        "AntiCommuting(Ex(r'\\psi_1, \\psi_2'))\n"
        "ex = Ex(r'\\psi_1 \\psi_2 + \\psi_2 \\psi_1')\n"
        "sort_product(ex)\n"
        "collect_terms(ex)\n"
        "print(str(ex))",
        ["0"],
    )
    chk(
        "cadabra2_evaluate_vs_raw",
        "print(str(Ex(r'1 + 1')))\n"
        "print(str(evaluate(Ex(r'1 + 1'))))",
        ["1 + 1", "2"],
    )
    chk(
        "cadabra2_simplify_polynomial",
        "print(str(simplify(Ex(r'(x + 1)**2 - x**2 - 2*x - 1'))))",
        ["0"],
    )
    chk(
        "cadabra2_distribute_product",
        "print(str(distribute(Ex(r'x*(y + z)'))))",
        ["x y + x z"],
    )
    chk(
        "cadabra2_expand_power_pin",
        "print(str(expand(Ex(r'(x + y)**2'))))",
        ["(x + y)**2"],
    )
    chk(
        "cadabra2_sympy_bridge_clean",
        "import sympy as _sp\n"
        "_s = SympyBridge(Ex(r'x + y')).to_sympy()\n"
        "print(_sp.sstr(_s))\n"
        "print(','.join(sorted(str(t) for t in _s.free_symbols)))",
        ["x + y", "x,y"],
    )
    chk(
        "cadabra2_sympy_bridge_power_bug_pin",
        "import sympy as _sp\n"
        "print(_sp.sstr(SympyBridge(Ex(r'x^2')).to_sympy()))\n"
        "print(_sp.sstr(SympyBridge(Ex(r'x**2')).to_sympy()))",
        ["x(UP2)", "x**2"],
    )
    chk(
        "cadabra2_ex_silent_truncation_pin",
        "print(repr(str(Ex(r'x +'))))\n"
        "print(repr(str(Ex(r')'))))",
        ["'x'", "''"],
    )
    chk(
        "cadabra2_list_property_requires_comma",
        "try:\n"
        "    Indices(Ex(r'm'))\n"
        "    print('NO-ERROR')\n"
        "except RuntimeError:\n"
        "    print('RuntimeError')\n"
        "Indices(Ex(r'm, n'), Ex(r'position = fixed'))\n"
        "print('comma-ok')",
        ["RuntimeError", "comma-ok"],
    )
    chk(
        "cadabra2_delta_no_contraction_pin",
        "Indices(Ex(r'm, n, k'), Ex(r'position = fixed'))\n"
        "ex = Ex(r'\\delta_{m n} A^m')\n"
        "canonicalise(ex)\n"
        "reduce_delta(ex)\n"
        "print(str(ex))",
        ["δ^{m}_{n} A_{m}"],
    )

    fence = _run_cadabra("raise ValueError('boom')", 30.0)
    fence_ok = (not fence["ok"]) and ("ValueError" in (fence["stderr"] or ""))
    checks.append(
        {
            "name": "cadabra2_error_fence_python",
            "passed": fence_ok,
            "expected": ["ok=False", "stderr contiene ValueError"],
            "got": [
                "ok=%s" % fence["ok"],
                (fence["stderr"] or "").strip().splitlines()[-1]
                if (fence["stderr"] or "").strip()
                else "<stderr vacio>",
            ],
        }
    )

    return {
        "mode": "validate",
        "validation_passed": all(c["passed"] for c in checks),
        "checks": checks,
        "engine": _version(),
    }


def _cadabra2_math_handler(args):
    mode = args.get("mode")
    if mode == "validate":
        return _validate()
    if mode == "compute":
        return _compute(args)
    raise ValueError("mode debe ser 'compute' o 'validate'")


register_tool(
    name="cadabra2_math_tool",
    schema=_CADABRA2_MATH_TOOL_SCHEMA,
    handler=lambda args: _cadabra2_math_handler(args),
)
