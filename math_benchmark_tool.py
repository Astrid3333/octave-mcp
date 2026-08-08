"""
math_benchmark_tool.py
Tool: math_benchmark

Compara metodos numericos contra soluciones analiticas conocidas para
estimar orden de convergencia empirico y error real, en tres familias:

  - mode='ode_methods'   : Euler, RK2 (punto medio), RK4 vs solucion
                            analitica de un problema de prueba
                            (decaimiento exponencial, oscilador armonico,
                            crecimiento logistico).
  - mode='quadrature'    : Trapecio, Simpson, cuadratura de Gauss-Legendre
                            (Gauss-Legendre via numpy) vs integral analitica
                            una funcion arbitraria o preset.
  - mode='root_finding'  : Biseccion, Newton-Raphson, Secante vs raiz
                            conocida de un preset o expresion dada.
  - mode='validate'      : corre un caso canonico de cada familia con
                            verdad conocida y devuelve all_passed.

No depende de Octave ni de scipy: todo el calculo se hace en Python puro
(numpy, sympy), mismo patron que auto_differentiation_tool.py.
"""

import numpy as np
import sympy as sp
from numpy.polynomial.legendre import leggauss


# ---------------------------------------------------------------------------
# Presets de problemas ODE con solucion analitica conocida
# ---------------------------------------------------------------------------
_ODE_PRESETS = {
    "exponential_decay": {
        "rhs": lambda t, y, k=1.0: -k * y,
        "analytical": lambda t, y0=1.0, k=1.0: y0 * np.exp(-k * t),
        "y0": 1.0,
        "params": {"k": 1.0},
        "description": "y' = -k*y",
    },
    "harmonic_oscillator": {
        # sistema de 2 ecuaciones: y = [posicion, velocidad]
        "rhs": lambda t, y, w=1.0: np.array([y[1], -w**2 * y[0]]),
        "analytical": lambda t, y0=np.array([1.0, 0.0]), w=1.0: np.array(
            [y0[0] * np.cos(w * t), -y0[0] * w * np.sin(w * t)]
        ),
        "y0": np.array([1.0, 0.0]),
        "params": {"w": 1.0},
        "description": "y'' + w^2*y = 0 (sistema y=[pos,vel])",
    },
    "logistic_growth": {
        "rhs": lambda t, y, r=1.0, K=1.0: r * y * (1 - y / K),
        "analytical": lambda t, y0=0.1, r=1.0, K=1.0: (
            K / (1 + ((K - y0) / y0) * np.exp(-r * t))
        ),
        "y0": 0.1,
        "params": {"r": 1.0, "K": 1.0},
        "description": "y' = r*y*(1 - y/K)",
    },
}


def _euler_step(rhs, t, y, h, params):
    return y + h * rhs(t, y, **params)


def _rk2_step(rhs, t, y, h, params):
    k1 = rhs(t, y, **params)
    k2 = rhs(t + h / 2, y + h / 2 * k1, **params)
    return y + h * k2


def _rk4_step(rhs, t, y, h, params):
    k1 = rhs(t, y, **params)
    k2 = rhs(t + h / 2, y + h / 2 * k1, **params)
    k3 = rhs(t + h / 2, y + h / 2 * k2, **params)
    k4 = rhs(t + h, y + h * k3, **params)
    return y + (h / 6) * (k1 + 2 * k2 + 2 * k3 + k4)


_ODE_METHODS = {"euler": _euler_step, "rk2": _rk2_step, "rk4": _rk4_step}


def _run_ode_method(step_fn, rhs, y0, t0, t_end, h, params):
    n_steps = int(round((t_end - t0) / h))
    t, y = t0, np.array(y0, dtype=float)
    for _ in range(n_steps):
        y = step_fn(rhs, t, y, h, params)
        t += h
    return t, y


def _bench_ode_methods(problem="exponential_decay", h_list=None, t_end=2.0, methods=None):
    if problem not in _ODE_PRESETS:
        return {"error": f"problema desconocido: {problem}. Opciones: {list(_ODE_PRESETS)}"}
    preset = _ODE_PRESETS[problem]
    rhs = preset["rhs"]
    analytical = preset["analytical"]
    y0 = preset["y0"]
    params = preset["params"]

    h_list = h_list or [0.4, 0.2, 0.1, 0.05, 0.025]
    methods = methods or list(_ODE_METHODS)

    y_true = np.atleast_1d(analytical(t_end, y0, **params))

    results = {}
    for m in methods:
        step_fn = _ODE_METHODS[m]
        errors, hs = [], []
        for h in h_list:
            _, y_num = _run_ode_method(step_fn, rhs, y0, 0.0, t_end, h, params)
            y_num = np.atleast_1d(y_num)
            err = float(np.linalg.norm(y_num - y_true))
            errors.append(err)
            hs.append(h)

        # orden de convergencia empirico: pendiente de log(err) vs log(h)
        log_h = np.log(hs)
        log_err = np.log(np.maximum(errors, 1e-300))
        order = float(np.polyfit(log_h, log_err, 1)[0]) if len(hs) >= 2 else None

        results[m] = {
            "h_values": hs,
            "errors": errors,
            "empirical_order": order,
            "expected_order": {"euler": 1, "rk2": 2, "rk4": 4}[m],
        }

    return {
        "problem": problem,
        "description": preset["description"],
        "t_end": t_end,
        "y_true": y_true.tolist(),
        "methods": results,
    }


# ---------------------------------------------------------------------------
# Cuadratura
# ---------------------------------------------------------------------------
_QUADRATURE_PRESETS = {
    "polynomial": {"expr": "x**3 - 2*x + 1", "a": 0.0, "b": 2.0},
    "sine": {"expr": "sin(x)", "a": 0.0, "b": 3.141592653589793},
    "exponential": {"expr": "exp(-x**2)", "a": -2.0, "b": 2.0},
    "oscillatory": {"expr": "sin(20*x)", "a": 0.0, "b": 3.141592653589793},
}


_np_trapezoidal = getattr(np, "trapezoid", None) or np.trapz


def _trapezoidal(f, a, b, n):
    x = np.linspace(a, b, n + 1)
    y = f(x)
    return float(_np_trapezoidal(y, x))


def _simpson(f, a, b, n):
    if n % 2 == 1:
        n += 1
    x = np.linspace(a, b, n + 1)
    y = f(x)
    h = (b - a) / n
    return float(h / 3 * (y[0] + y[-1] + 4 * np.sum(y[1:-1:2]) + 2 * np.sum(y[2:-2:2])))


def _gauss_legendre(f, a, b, n):
    n = max(n, 2)
    nodes, weights = leggauss(n)  # nodos/pesos en [-1, 1]
    x_mapped = 0.5 * (b - a) * nodes + 0.5 * (b + a)
    y = f(x_mapped)
    return float(0.5 * (b - a) * np.sum(weights * y))


_QUADRATURE_METHODS = {"trapezoidal": _trapezoidal, "simpson": _simpson, "gauss_legendre": _gauss_legendre}


def _bench_quadrature(function_expr=None, a=None, b=None, preset="polynomial", n_list=None, methods=None):
    if function_expr is None:
        if preset not in _QUADRATURE_PRESETS:
            return {"error": f"preset desconocido: {preset}. Opciones: {list(_QUADRATURE_PRESETS)}"}
        p = _QUADRATURE_PRESETS[preset]
        function_expr, a, b = p["expr"], p["a"], p["b"]

    x = sp.symbols("x")
    expr = sp.sympify(function_expr)
    f_np = sp.lambdify(x, expr, "numpy")
    exact_raw = sp.N(sp.integrate(expr, (x, a, b)))
    exact_c = complex(exact_raw)
    exact = exact_c.real if abs(exact_c.imag) < 1e-9 else exact_c

    n_list = n_list or [4, 8, 16, 32, 64, 128]
    methods = methods or list(_QUADRATURE_METHODS)

    results = {}
    for m in methods:
        fn = _QUADRATURE_METHODS[m]
        errors, ns = [], []
        for n in n_list:
            val = fn(f_np, a, b, n)
            errors.append(abs(val - exact))
            ns.append(n)
        results[m] = {"n_values": ns, "errors": errors}

    return {
        "function_expr": function_expr,
        "bounds": [a, b],
        "exact_value": exact,
        "methods": results,
    }


# ---------------------------------------------------------------------------
# Busqueda de raices
# ---------------------------------------------------------------------------
_ROOT_PRESETS = {
    "cubic": {"expr": "x**3 - x - 2", "bracket": [1.0, 2.0], "x0": 1.5},
    "transcendental": {"expr": "cos(x) - x", "bracket": [0.0, 1.0], "x0": 0.5},
}


def _bisection(f, a, b, tol, max_iter):
    fa, fb = f(a), f(b)
    if fa * fb > 0:
        return None, max_iter
    for i in range(max_iter):
        m = (a + b) / 2
        fm = f(m)
        if abs(fm) < tol or (b - a) / 2 < tol:
            return m, i + 1
        if fa * fm < 0:
            b = m
        else:
            a, fa = m, fm
    return (a + b) / 2, max_iter


def _newton(f, fprime, x0, tol, max_iter):
    x = x0
    for i in range(max_iter):
        fx = f(x)
        if abs(fx) < tol:
            return x, i + 1
        dfx = fprime(x)
        if dfx == 0:
            return None, i + 1
        x = x - fx / dfx
    return x, max_iter


def _secant(f, x0, x1, tol, max_iter):
    for i in range(max_iter):
        f0, f1 = f(x0), f(x1)
        if abs(f1) < tol:
            return x1, i + 1
        if f1 == f0:
            return None, i + 1
        x2 = x1 - f1 * (x1 - x0) / (f1 - f0)
        x0, x1 = x1, x2
    return x1, max_iter


def _bench_root_finding(function_expr=None, bracket=None, x0=None, preset="cubic", tol=1e-10, max_iter=100):
    if function_expr is None:
        if preset not in _ROOT_PRESETS:
            return {"error": f"preset desconocido: {preset}. Opciones: {list(_ROOT_PRESETS)}"}
        p = _ROOT_PRESETS[preset]
        function_expr, bracket, x0 = p["expr"], p["bracket"], p["x0"]

    x = sp.symbols("x")
    expr = sp.sympify(function_expr)
    fprime_expr = sp.diff(expr, x)
    f = sp.lambdify(x, expr, "numpy")
    fprime = sp.lambdify(x, fprime_expr, "numpy")

    root_ref = None
    try:
        real_roots = [r for r in sp.solve(sp.Eq(expr, 0), x) if r.is_real]
        if real_roots:
            root_ref = float(min(real_roots, key=lambda r: abs(float(r) - x0)))
    except NotImplementedError:
        pass
    if root_ref is None:
        try:
            root_ref = float(sp.nsolve(expr, x, x0))
        except Exception:
            root_ref = None

    results = {}

    r, it = _bisection(f, bracket[0], bracket[1], tol, max_iter)
    results["bisection"] = {"root": r, "iterations": it}

    r, it = _newton(f, fprime, x0, tol, max_iter)
    results["newton"] = {"root": r, "iterations": it}

    r, it = _secant(f, bracket[0], bracket[1], tol, max_iter)
    results["secant"] = {"root": r, "iterations": it}

    if root_ref is not None:
        for m in results:
            if results[m]["root"] is not None:
                results[m]["error_vs_reference"] = abs(results[m]["root"] - root_ref)

    return {
        "function_expr": function_expr,
        "reference_root": root_ref,
        "methods": results,
    }


# ---------------------------------------------------------------------------
# Validacion
# ---------------------------------------------------------------------------
def _validate():
    checks = []

    ode = _bench_ode_methods("exponential_decay", h_list=[0.2, 0.1, 0.05], t_end=1.0)
    ok = abs(ode["methods"]["rk4"]["empirical_order"] - 4) < 0.5
    checks.append({
        "check": "rk4_order_exponential_decay",
        "passed": bool(ok),
        "empirical_order": ode["methods"]["rk4"]["empirical_order"],
    })

    quad = _bench_quadrature(preset="polynomial", n_list=[4, 8, 16])
    ok = quad["methods"]["simpson"]["errors"][-1] < 1e-8
    checks.append({
        "check": "simpson_polynomial_exact_ish",
        "passed": bool(ok),
        "final_error": quad["methods"]["simpson"]["errors"][-1],
    })

    roots = _bench_root_finding(preset="cubic")
    ok = roots["methods"]["newton"]["error_vs_reference"] < 1e-8
    checks.append({
        "check": "newton_cubic_root",
        "passed": bool(ok),
        "error": roots["methods"]["newton"]["error_vs_reference"],
    })

    return {"all_passed": all(c["passed"] for c in checks), "checks": checks}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def compute_math_benchmark(mode="validate", **kwargs):
    if mode == "ode_methods":
        return _bench_ode_methods(**kwargs)
    elif mode == "quadrature":
        return _bench_quadrature(**kwargs)
    elif mode == "root_finding":
        return _bench_root_finding(**kwargs)
    elif mode == "validate":
        return _validate()
    else:
        return {"error": f"mode desconocido: {mode}. Opciones: ode_methods, quadrature, root_finding, validate"}


MATH_BENCHMARK_TOOL_SCHEMA = {
    "name": "math_benchmark",
    "description": (
        "Compara metodos numericos contra soluciones analiticas conocidas y "
        "estima el orden de convergencia empirico. mode='ode_methods' "
        "(Euler/RK2/RK4 vs solucion analitica; kwargs: problem in "
        "['exponential_decay','harmonic_oscillator','logistic_growth'], "
        "h_list, t_end, methods); mode='quadrature' (Trapecio/Simpson/"
        "Gauss-Legendre vs integral analitica via sympy; kwargs: "
        "function_expr, a, b o preset in ['polynomial','sine','exponential',"
        "'oscillatory'], n_list, methods); mode='root_finding' (Biseccion/"
        "Newton-Raphson/Secante vs raiz de referencia; kwargs: function_expr, "
        "bracket, x0 o preset in ['cubic','transcendental'], tol, max_iter); "
        "mode='validate' corre un caso de cada familia con verdad conocida."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["ode_methods", "quadrature", "root_finding", "validate"],
                "default": "validate",
            },
            "problem": {"type": "string", "description": "Preset ODE. Solo mode=ode_methods."},
            "h_list": {"type": "array", "items": {"type": "number"}, "description": "Pasos a barrer. Solo mode=ode_methods."},
            "t_end": {"type": "number", "description": "Tiempo final de integracion. Solo mode=ode_methods."},
            "function_expr": {"type": "string", "description": "Expresion sympy en x. mode=quadrature o root_finding."},
            "a": {"type": "number", "description": "Limite inferior. Solo mode=quadrature."},
            "b": {"type": "number", "description": "Limite superior. Solo mode=quadrature."},
            "preset": {"type": "string", "description": "Nombre de preset (ver description). mode=quadrature o root_finding."},
            "n_list": {"type": "array", "items": {"type": "integer"}, "description": "Subdivisiones a barrer. Solo mode=quadrature."},
            "bracket": {"type": "array", "items": {"type": "number"}, "description": "[a,b] para biseccion/secante. Solo mode=root_finding."},
            "x0": {"type": "number", "description": "Punto inicial para Newton. Solo mode=root_finding."},
            "tol": {"type": "number", "description": "Tolerancia. Solo mode=root_finding."},
            "max_iter": {"type": "integer", "description": "Iteraciones maximas. Solo mode=root_finding."},
            "methods": {"type": "array", "items": {"type": "string"}, "description": "Subconjunto de metodos a correr. Opcional."},
        },
        "required": [],
    },
}
