"""
math_interpolation_tool.py
Tool: math_interpolation

Compara metodos de interpolacion contra la funcion exacta (sympy), con
foco en el fenomeno de Runge (interpolacion polinomica de alto grado con
nodos equiespaciados) y su mitigacion con nodos de Chebyshev o splines.

  - mode='lagrange'       : interpolacion de Lagrange (forma baricentrica,
                             numericamente estable) vs funcion exacta.
                             kwargs: preset o function_expr+domain, n_list,
                             node_type in ['equally_spaced','chebyshev'].
  - mode='spline'         : spline cubico natural (implementado sin scipy)
                             vs funcion exacta. kwargs: preset o
                             function_expr+domain, n_list.
  - mode='compare_nodes'  : corre 'lagrange' con ambos tipos de nodo para
                             el mismo n_list -- forma directa de ver el
                             fenomeno de Runge (equally_spaced diverge,
                             chebyshev converge).
  - mode='validate'       : casos canonicos con verdad conocida.

No depende de Octave ni de scipy: todo en Python puro (numpy, sympy),
mismo patron que math_error_analyzer_tool.py y math_benchmark_tool.py.
"""

import numpy as np
import sympy as sp


# ---------------------------------------------------------------------------
# Presets de funciones de prueba
# ---------------------------------------------------------------------------
_FUNCTION_PRESETS = {
    "runge": {"expr": "1/(1+25*x**2)", "domain": [-1.0, 1.0]},
    "smooth_sine": {"expr": "sin(pi*x)", "domain": [-1.0, 1.0]},
    "exponential": {"expr": "exp(x)", "domain": [-1.0, 1.0]},
    "abs_kink": {"expr": "Abs(x)", "domain": [-1.0, 1.0]},
}


def _resolve_function(function_expr, domain, preset):
    if function_expr is None:
        if preset not in _FUNCTION_PRESETS:
            return None, None, {"error": f"preset desconocido: {preset}. Opciones: {list(_FUNCTION_PRESETS)}"}
        p = _FUNCTION_PRESETS[preset]
        function_expr, domain = p["expr"], p["domain"]
    x = sp.symbols("x")
    expr = sp.sympify(function_expr)
    f_np = sp.lambdify(x, expr, "numpy")
    return f_np, domain, function_expr


# ---------------------------------------------------------------------------
# Nodos
# ---------------------------------------------------------------------------
def _nodes(n, domain, node_type):
    a, b = domain
    if node_type == "chebyshev":
        k = np.arange(n)
        # nodos de Chebyshev-Gauss-Lobatto, mapeados a [a,b]
        cheb = np.cos(np.pi * k / (n - 1)) if n > 1 else np.array([0.0])
        return 0.5 * (a + b) + 0.5 * (b - a) * cheb[::-1]
    return np.linspace(a, b, n)


# ---------------------------------------------------------------------------
# Interpolacion de Lagrange (forma baricentrica)
# ---------------------------------------------------------------------------
def _barycentric_weights(x_nodes):
    n = len(x_nodes)
    w = np.ones(n)
    for j in range(n):
        diffs = x_nodes[j] - np.delete(x_nodes, j)
        w[j] = 1.0 / np.prod(diffs)
    return w


def _barycentric_eval(x_nodes, y_nodes, w, x_eval):
    x_eval = np.atleast_1d(x_eval).astype(float)
    result = np.empty_like(x_eval)
    for i, xe in enumerate(x_eval):
        diff = xe - x_nodes
        exact_idx = np.where(np.abs(diff) < 1e-14)[0]
        if exact_idx.size > 0:
            result[i] = y_nodes[exact_idx[0]]
            continue
        terms = w / diff
        result[i] = np.sum(terms * y_nodes) / np.sum(terms)
    return result


def _bench_lagrange(preset="runge", function_expr=None, domain=None, n_list=None, node_type="equally_spaced", n_eval=400):
    f_np, domain, expr_or_err = _resolve_function(function_expr, domain, preset)
    if f_np is None:
        return expr_or_err
    function_expr = expr_or_err

    n_list = n_list or [5, 9, 13, 17, 21]
    x_dense = np.linspace(domain[0], domain[1], n_eval)
    y_true = f_np(x_dense)

    errors, ns = [], []
    for n in n_list:
        x_nodes = _nodes(n, domain, node_type)
        y_nodes = f_np(x_nodes)
        w = _barycentric_weights(x_nodes)
        y_interp = _barycentric_eval(x_nodes, y_nodes, w, x_dense)
        errors.append(float(np.max(np.abs(y_interp - y_true))))
        ns.append(n)

    return {
        "function_expr": function_expr,
        "domain": domain,
        "node_type": node_type,
        "n_values": ns,
        "max_errors": errors,
    }


# ---------------------------------------------------------------------------
# Spline cubico natural (implementado a mano, sin scipy)
# ---------------------------------------------------------------------------
def _natural_cubic_spline_coeffs(x, y):
    n = len(x) - 1
    h = np.diff(x)
    alpha = np.zeros(n + 1)
    for i in range(1, n):
        alpha[i] = (3.0 / h[i]) * (y[i + 1] - y[i]) - (3.0 / h[i - 1]) * (y[i] - y[i - 1])

    l = np.ones(n + 1)
    mu = np.zeros(n + 1)
    z = np.zeros(n + 1)
    for i in range(1, n):
        l[i] = 2.0 * (x[i + 1] - x[i - 1]) - h[i - 1] * mu[i - 1]
        mu[i] = h[i] / l[i]
        z[i] = (alpha[i] - h[i - 1] * z[i - 1]) / l[i]

    c = np.zeros(n + 1)
    b = np.zeros(n)
    d = np.zeros(n)
    for j in range(n - 1, -1, -1):
        c[j] = z[j] - mu[j] * c[j + 1]
        b[j] = (y[j + 1] - y[j]) / h[j] - h[j] * (c[j + 1] + 2.0 * c[j]) / 3.0
        d[j] = (c[j + 1] - c[j]) / (3.0 * h[j])

    a = y[:-1]
    return a, b, c[:-1], d


def _eval_spline(x_nodes, coeffs, x_eval):
    a, b, c, d = coeffs
    x_eval = np.atleast_1d(x_eval).astype(float)
    idx = np.clip(np.searchsorted(x_nodes, x_eval, side="right") - 1, 0, len(a) - 1)
    dx = x_eval - x_nodes[idx]
    return a[idx] + b[idx] * dx + c[idx] * dx**2 + d[idx] * dx**3


def _bench_spline(preset="runge", function_expr=None, domain=None, n_list=None, n_eval=400):
    f_np, domain, expr_or_err = _resolve_function(function_expr, domain, preset)
    if f_np is None:
        return expr_or_err
    function_expr = expr_or_err

    n_list = n_list or [5, 9, 13, 17, 21]
    x_dense = np.linspace(domain[0], domain[1], n_eval)
    y_true = f_np(x_dense)

    errors, ns = [], []
    for n in n_list:
        x_nodes = _nodes(n, domain, "equally_spaced")
        y_nodes = f_np(x_nodes)
        coeffs = _natural_cubic_spline_coeffs(x_nodes, y_nodes)
        y_interp = _eval_spline(x_nodes, coeffs, x_dense)
        errors.append(float(np.max(np.abs(y_interp - y_true))))
        ns.append(n)

    return {
        "function_expr": function_expr,
        "domain": domain,
        "n_values": ns,
        "max_errors": errors,
    }


# ---------------------------------------------------------------------------
# Comparacion de nodos (demo directa del fenomeno de Runge)
# ---------------------------------------------------------------------------
def _compare_nodes(preset="runge", function_expr=None, domain=None, n_list=None, n_eval=400):
    equally = _bench_lagrange(preset, function_expr, domain, n_list, "equally_spaced", n_eval)
    if "error" in equally:
        return equally
    chebyshev = _bench_lagrange(preset, function_expr, domain, n_list, "chebyshev", n_eval)

    return {
        "function_expr": equally["function_expr"],
        "domain": equally["domain"],
        "n_values": equally["n_values"],
        "equally_spaced_errors": equally["max_errors"],
        "chebyshev_errors": chebyshev["max_errors"],
        "runge_phenomenon_detected": bool(
            equally["max_errors"][-1] > equally["max_errors"][0]
            and chebyshev["max_errors"][-1] < equally["max_errors"][-1]
        ),
    }


# ---------------------------------------------------------------------------
# Validacion
# ---------------------------------------------------------------------------
def _validate():
    checks = []

    # Un polinomio de grado 2 debe interpolarse EXACTO con >=3 nodos, cualquier metodo
    exact = _bench_lagrange(function_expr="x**2 - x + 1", domain=[-1.0, 1.0], n_list=[5], node_type="equally_spaced")
    ok = exact["max_errors"][0] < 1e-10
    checks.append({"check": "lagrange_exact_on_polynomial", "passed": bool(ok), "max_error": exact["max_errors"][0]})

    # Fenomeno de Runge: equiespaciado debe empeorar, Chebyshev debe mejorar
    cmp = _compare_nodes(preset="runge", n_list=[5, 11, 17, 23])
    checks.append({
        "check": "runge_phenomenon_equally_vs_chebyshev",
        "passed": bool(cmp["runge_phenomenon_detected"]),
        "equally_spaced_errors": cmp["equally_spaced_errors"],
        "chebyshev_errors": cmp["chebyshev_errors"],
    })

    # Spline cubico natural debe converger (error decreciente) en funcion suave
    spl = _bench_spline(preset="smooth_sine", n_list=[5, 9, 13, 17])
    ok = spl["max_errors"][-1] < spl["max_errors"][0]
    checks.append({"check": "spline_converges_on_smooth_function", "passed": bool(ok), "errors": spl["max_errors"]})

    return {"all_passed": all(c["passed"] for c in checks), "checks": checks}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def compute_math_interpolation(mode="validate", **kwargs):
    if mode == "lagrange":
        return _bench_lagrange(**kwargs)
    elif mode == "spline":
        return _bench_spline(**kwargs)
    elif mode == "compare_nodes":
        return _compare_nodes(**kwargs)
    elif mode == "validate":
        return _validate()
    else:
        return {"error": f"mode desconocido: {mode}. Opciones: lagrange, spline, compare_nodes, validate"}


MATH_INTERPOLATION_TOOL_SCHEMA = {
    "name": "math_interpolation",
    "description": (
        "Compara metodos de interpolacion contra la funcion exacta, con foco "
        "en el fenomeno de Runge y su mitigacion. mode='lagrange' "
        "(interpolacion de Lagrange en forma baricentrica; kwargs: preset in "
        "['runge','smooth_sine','exponential','abs_kink'] o function_expr+"
        "domain, n_list, node_type in ['equally_spaced','chebyshev']); "
        "mode='spline' (spline cubico natural, sin scipy; mismos kwargs sin "
        "node_type); mode='compare_nodes' (corre lagrange con ambos tipos de "
        "nodo para el mismo n_list, marca runge_phenomenon_detected); "
        "mode='validate' corre casos con verdad conocida."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["lagrange", "spline", "compare_nodes", "validate"],
                "default": "validate",
            },
            "preset": {"type": "string", "description": "Nombre de preset (ver description). Opcional si se da function_expr."},
            "function_expr": {"type": "string", "description": "Expresion sympy en x. Opcional, reemplaza preset."},
            "domain": {"type": "array", "items": {"type": "number"}, "description": "[a,b]. Requerido si se usa function_expr."},
            "n_list": {"type": "array", "items": {"type": "integer"}, "description": "Cantidades de nodos a barrer."},
            "node_type": {"type": "string", "enum": ["equally_spaced", "chebyshev"], "description": "Solo mode=lagrange."},
            "n_eval": {"type": "integer", "description": "Puntos de la grilla densa para medir error maximo. Default 400."},
        },
        "required": [],
    },
}
