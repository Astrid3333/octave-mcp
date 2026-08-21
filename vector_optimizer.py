"""
vector_optimizer: optimizacion de funciones escalares de un vector de
parametros, via gradient descent (con momentum opcional) o metodo de
Newton, usando gradiente y Hessiano calculados por diferencias finitas
centradas.

Por seguridad no se acepta codigo arbitrario del usuario como funcion
objetivo (nada de eval()). En su lugar se ofrece un set de funciones de
prueba estandar de optimizacion (sphere, rosenbrock, rastrigin, booth) mas
'quadratic', que cubre el caso general de programacion cuadratica:
f(x) = 0.5 * x^T A x - b^T x, param por el usuario via matriz A y vector b.
"""

import sys
import json

import numpy as np


# ---------------------------------------------------------------------------
# funciones objetivo predefinidas
# ---------------------------------------------------------------------------

def _f_sphere(x, extra=None):
    return float(np.sum(x**2))


def _f_rosenbrock(x, extra=None):
    if x.shape[0] < 2:
        raise ValueError("rosenbrock requiere al menos 2 dimensiones")
    return float(np.sum(100.0 * (x[1:] - x[:-1]**2)**2 + (1 - x[:-1])**2))


def _f_rastrigin(x, extra=None):
    n = x.shape[0]
    A = 10.0
    return float(A * n + np.sum(x**2 - A * np.cos(2 * np.pi * x)))


def _f_booth(x, extra=None):
    if x.shape[0] != 2:
        raise ValueError("booth esta definida solo para 2 dimensiones")
    x1, x2 = x[0], x[1]
    return float((x1 + 2 * x2 - 7) ** 2 + (2 * x1 + x2 - 5) ** 2)


def _f_quadratic(x, extra):
    A = np.array(extra["A"], dtype=float)
    b = np.array(extra["b"], dtype=float)
    if A.shape != (x.shape[0], x.shape[0]):
        raise ValueError(f"A debe ser {x.shape[0]}x{x.shape[0]}, tiene {A.shape}")
    if b.shape != x.shape:
        raise ValueError(f"b debe tener {x.shape[0]} componentes, tiene {b.shape[0]}")
    return float(0.5 * x @ A @ x - b @ x)


_OBJECTIVES = {
    "sphere": _f_sphere,
    "rosenbrock": _f_rosenbrock,
    "rastrigin": _f_rastrigin,
    "booth": _f_booth,
    "quadratic": _f_quadratic,
}


def _get_objective(name, extra_params):
    if name not in _OBJECTIVES:
        raise ValueError(f"objective desconocido: {name} (usar {'/'.join(_OBJECTIVES.keys())})")
    fn = _OBJECTIVES[name]

    if name == "quadratic":
        if extra_params is None or "A" not in extra_params or "b" not in extra_params:
            raise ValueError("objective='quadratic' requiere extra_params con 'A' (matriz) y 'b' (vector)")

    def wrapped(x):
        return fn(x, extra_params)

    return wrapped


# ---------------------------------------------------------------------------
# validacion
# ---------------------------------------------------------------------------

def _validate_x0(x0):
    if x0 is None:
        raise ValueError("falta 'x0' en params (punto inicial)")
    arr = np.array(x0, dtype=float)
    if arr.ndim != 1:
        raise ValueError("x0 debe ser un vector 1D")
    if arr.shape[0] < 1:
        raise ValueError("x0 no puede estar vacio")
    if not np.all(np.isfinite(arr)):
        raise ValueError("x0 contiene valores no finitos (NaN/inf)")
    return arr


# ---------------------------------------------------------------------------
# gradiente y hessiano por diferencias finitas
# ---------------------------------------------------------------------------

def _numeric_gradient(f, x, h=1e-5):
    n = x.shape[0]
    grad = np.zeros(n)
    for i in range(n):
        x_fwd = x.copy()
        x_bwd = x.copy()
        x_fwd[i] += h
        x_bwd[i] -= h
        grad[i] = (f(x_fwd) - f(x_bwd)) / (2 * h)
    return grad


def _numeric_hessian(f, x, h=1e-4):
    n = x.shape[0]
    hess = np.zeros((n, n))
    f0 = f(x)
    for i in range(n):
        for j in range(i, n):
            if i == j:
                x_fwd = x.copy()
                x_bwd = x.copy()
                x_fwd[i] += h
                x_bwd[i] -= h
                hess[i, i] = (f(x_fwd) - 2 * f0 + f(x_bwd)) / (h * h)
            else:
                x_pp, x_pm, x_mp, x_mm = x.copy(), x.copy(), x.copy(), x.copy()
                x_pp[i] += h; x_pp[j] += h
                x_pm[i] += h; x_pm[j] -= h
                x_mp[i] -= h; x_mp[j] += h
                x_mm[i] -= h; x_mm[j] -= h
                val = (f(x_pp) - f(x_pm) - f(x_mp) + f(x_mm)) / (4 * h * h)
                hess[i, j] = val
                hess[j, i] = val
    return hess


# ---------------------------------------------------------------------------
# metodos de optimizacion
# ---------------------------------------------------------------------------

def _optimize_gradient_descent(f, x0, learning_rate, momentum, max_iter, tol):
    x = x0.copy()
    velocity = np.zeros_like(x)
    history = [{"iter": 0, "x": x.tolist(), "f": f(x)}]

    for it in range(1, max_iter + 1):
        grad = _numeric_gradient(f, x)
        velocity = momentum * velocity - learning_rate * grad
        x = x + velocity
        f_val = f(x)
        history.append({"iter": it, "x": x.tolist(), "f": f_val})

        if np.linalg.norm(grad) < tol:
            break

    return x, history


def _optimize_newton(f, x0, max_iter, tol, hessian_reg):
    x = x0.copy()
    history = [{"iter": 0, "x": x.tolist(), "f": f(x)}]

    for it in range(1, max_iter + 1):
        grad = _numeric_gradient(f, x)
        if np.linalg.norm(grad) < tol:
            break

        hess = _numeric_hessian(f, x)
        hess_reg = hess + hessian_reg * np.eye(len(x))
        try:
            step = np.linalg.solve(hess_reg, grad)
        except np.linalg.LinAlgError:
            # hessiano singular incluso regularizado: caer a un paso de gradiente
            step = grad

        x = x - step
        f_val = f(x)
        history.append({"iter": it, "x": x.tolist(), "f": f_val})

    return x, history


# ---------------------------------------------------------------------------
# modo principal
# ---------------------------------------------------------------------------

def optimize(params):
    params = params or {}
    x0 = _validate_x0(params.get("x0"))
    objective_name = params.get("objective", "sphere")
    extra_params = params.get("extra_params")
    f = _get_objective(objective_name, extra_params)

    method = params.get("method", "gradient_descent")
    if method not in ("gradient_descent", "newton"):
        raise ValueError("method debe ser gradient_descent o newton")

    max_iter = int(params.get("max_iter", 500))
    if max_iter < 1:
        raise ValueError("max_iter debe ser >= 1")
    tol = float(params.get("tol", 1e-8))
    if tol <= 0:
        raise ValueError("tol debe ser > 0")

    if method == "gradient_descent":
        learning_rate = float(params.get("learning_rate", 0.01))
        if learning_rate <= 0:
            raise ValueError("learning_rate debe ser > 0")
        momentum = float(params.get("momentum", 0.0))
        if not (0.0 <= momentum < 1.0):
            raise ValueError("momentum debe estar en [0, 1)")
        x_final, history = _optimize_gradient_descent(f, x0, learning_rate, momentum, max_iter, tol)
    else:
        hessian_reg = float(params.get("hessian_reg", 1e-6))
        if hessian_reg < 0:
            raise ValueError("hessian_reg debe ser >= 0")
        x_final, history = _optimize_newton(f, x0, max_iter, tol, hessian_reg)

    final_grad = _numeric_gradient(f, x_final)

    return {
        "objective": objective_name,
        "method": method,
        "x0": x0.tolist(),
        "x_final": x_final.tolist(),
        "f_final": f(x_final),
        "n_iterations": len(history) - 1,
        "converged": bool(np.linalg.norm(final_grad) < tol),
        "final_gradient_norm": float(np.linalg.norm(final_grad)),
        "history": history,
    }


def gradient_at(params):
    """Modo auxiliar: solo evalua el gradiente numerico en un punto, sin optimizar."""
    params = params or {}
    x0 = _validate_x0(params.get("x0"))
    objective_name = params.get("objective", "sphere")
    extra_params = params.get("extra_params")
    f = _get_objective(objective_name, extra_params)

    grad = _numeric_gradient(f, x0)
    return {
        "objective": objective_name,
        "x": x0.tolist(),
        "f": f(x0),
        "gradient": grad.tolist(),
        "gradient_norm": float(np.linalg.norm(grad)),
    }


TOOL_SCHEMA = {
    "name": "vector_optimizer",
    "description": (
        "Optimizacion de funciones escalares vectoriales via gradient "
        "descent (con momentum opcional) o metodo de Newton, con "
        "gradiente/Hessiano calculados por diferencias finitas centradas. "
        "Funciones objetivo predefinidas: sphere, rosenbrock, rastrigin, "
        "booth (2D), quadratic (parametrizable via extra_params.A y "
        "extra_params.b). No ejecuta codigo arbitrario del usuario. "
        "Modos: optimize, gradient_at (solo evalua el gradiente en un "
        "punto), self_test."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["optimize", "gradient_at", "self_test"]},
            "params": {
                "type": "object",
                "properties": {
                    "x0": {"type": "array", "items": {"type": "number"}, "description": "punto inicial"},
                    "objective": {"type": "string", "enum": ["sphere", "rosenbrock", "rastrigin", "booth", "quadratic"]},
                    "extra_params": {
                        "type": "object",
                        "description": "para objective=quadratic: {A: matriz NxN, b: vector N}",
                    },
                    "method": {"type": "string", "enum": ["gradient_descent", "newton"], "description": "solo para mode=optimize (default gradient_descent)"},
                    "learning_rate": {"type": "number", "description": "para gradient_descent (default 0.01)"},
                    "momentum": {"type": "number", "description": "para gradient_descent, en [0,1) (default 0)"},
                    "hessian_reg": {"type": "number", "description": "para newton, regularizacion diagonal del Hessiano (default 1e-6)"},
                    "max_iter": {"type": "integer", "description": "iteraciones maximas (default 500)"},
                    "tol": {"type": "number", "description": "tolerancia de norma de gradiente para convergencia (default 1e-8)"},
                },
                "required": ["x0"],
            },
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------------------
# self_test
# ---------------------------------------------------------------------------

def run_self_test():
    checks = []

    def check(name, cond, detail=""):
        checks.append({"name": name, "passed": bool(cond), "detail": detail})

    # 1) sphere: minimo global en el origen, cualquier x0 deberia converger a ~0
    out_sphere = optimize({
        "x0": [3.0, -4.0, 2.0],
        "objective": "sphere",
        "method": "gradient_descent",
        "learning_rate": 0.1,
        "max_iter": 500,
    })
    err_sphere = np.linalg.norm(out_sphere["x_final"])
    check("sphere (gradient_descent): converge cerca del origen", err_sphere < 1e-3, f"|x_final|={err_sphere:.2e}")
    check("sphere: converged=True reportado", out_sphere["converged"], f"converged={out_sphere['converged']}")

    # 2) quadratic: minimo analitico en x* = A^-1 b
    A = [[4.0, 1.0], [1.0, 3.0]]
    b = [1.0, 2.0]
    x_star_analytic = np.linalg.solve(np.array(A), np.array(b))
    out_quad = optimize({
        "x0": [0.0, 0.0],
        "objective": "quadratic",
        "extra_params": {"A": A, "b": b},
        "method": "newton",
        "max_iter": 20,
    })
    err_quad = np.max(np.abs(np.array(out_quad["x_final"]) - x_star_analytic))
    check("quadratic (newton): converge al minimo analitico A^-1 b", err_quad < 1e-4, f"analitico={x_star_analytic.tolist()}, obtenido={out_quad['x_final']}, err={err_quad:.2e}")

    # 3) newton en cuadratica deberia converger en muy pocas iteraciones (funcion es exactamente cuadratica)
    check("quadratic (newton): converge en pocas iteraciones (<=5)", out_quad["n_iterations"] <= 5, f"n_iterations={out_quad['n_iterations']}")

    # 4) booth: minimo conocido en (1, 3), f=0
    out_booth = optimize({
        "x0": [0.0, 0.0],
        "objective": "booth",
        "method": "gradient_descent",
        "learning_rate": 0.05,
        "max_iter": 2000,
    })
    err_booth = np.max(np.abs(np.array(out_booth["x_final"]) - np.array([1.0, 3.0])))
    check("booth: converge cerca del minimo conocido (1,3)", err_booth < 1e-2, f"x_final={out_booth['x_final']}, err={err_booth:.4f}")

    # 5) rosenbrock: minimo conocido en (1,1,...,1), f=0 -- con momentum deberia converger mejor que sin
    out_rosen = optimize({
        "x0": [-1.0, 1.5],
        "objective": "rosenbrock",
        "method": "gradient_descent",
        "learning_rate": 0.001,
        "momentum": 0.9,
        "max_iter": 5000,
    })
    f_rosen_x0 = _f_rosenbrock(np.array([-1.0, 1.5]))
    check("rosenbrock: f_final decrece sustancialmente desde f(x0)", out_rosen["f_final"] < f_rosen_x0, f"f(x0)={f_rosen_x0:.4f}, f_final={out_rosen['f_final']:.4f}")

    # 6) gradient_at: gradiente de sphere en x=(1,2) debe ser (2,4)
    out_grad = gradient_at({"x0": [1.0, 2.0], "objective": "sphere"})
    expected_grad = [2.0, 4.0]
    err_grad = np.max(np.abs(np.array(out_grad["gradient"]) - np.array(expected_grad)))
    check("gradient_at: gradiente de sphere en (1,2) = (2,4)", err_grad < 1e-4, f"esperado={expected_grad}, obtenido={out_grad['gradient']}")

    # 7) validaciones de error
    try:
        optimize({"x0": [1.0, 2.0], "objective": "booth_invalido"})
        check("ValueError con objective desconocido", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con objective desconocido", True, "")

    try:
        optimize({"x0": [1.0, 2.0, 3.0], "objective": "booth"})  # booth requiere 2D
        check("ValueError con booth en dimension incorrecta", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con booth en dimension incorrecta", True, "")

    try:
        optimize({"x0": [1.0, 2.0], "objective": "quadratic"})  # falta extra_params
        check("ValueError con quadratic sin extra_params", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con quadratic sin extra_params", True, "")

    try:
        optimize({"x0": [1.0, 2.0], "method": "metodo_invalido"})
        check("ValueError con method desconocido", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con method desconocido", True, "")

    try:
        run("modo_inexistente", {})
        check("ValueError con modo desconocido en run()", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con modo desconocido en run()", True, "")

    total = len(checks)
    passed = sum(1 for c in checks if c["passed"])
    return {"total": total, "passed": passed, "all_passed": passed == total, "checks": checks}


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

def run(mode, params=None):
    if mode == "optimize":
        return optimize(params or {})
    elif mode == "gradient_at":
        return gradient_at(params or {})
    elif mode == "self_test":
        return run_self_test()
    else:
        raise ValueError(f"modo desconocido: {mode} (usar optimize/gradient_at/self_test)")


if __name__ == "__main__":
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "self_test"
    params_arg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    try:
        out = run(mode_arg, params_arg)
        print(json.dumps(out, indent=2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)


def _register():
    """
    Auto-registro estilo octave-mcp (patron self-registrante via
    tool_registry, register_tool(name, schema, handler)).
    """
    try:
        import tool_registry

        def _handler(args):
            return run(args.get("mode"), args.get("params"))

        tool_registry.register_tool("vector_optimizer", TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()
