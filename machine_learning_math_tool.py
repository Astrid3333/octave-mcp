#!/usr/bin/env python3
"""
machine_learning_math_tool.py
Fundamentos matematicos de machine learning: descenso de gradiente (simbolico,
via sympy), regresion lineal y logistica, funciones de costo, comparacion de
regularizacion L1/L2 (Lasso/Ridge), y PCA (analisis de componentes principales).

No es un framework de ML -- es la matematica de base que un curso universitario
necesita ver explicita (gradientes paso a paso, ecuaciones normales, autovalores),
no una caja negra tipo sklearn.

Corre standalone: python3 machine_learning_math_tool.py
"""
import json
import numpy as np
import sympy as sp


MACHINE_LEARNING_TOOL_SCHEMA = {
    "name": "machine_learning_math",
    "description": (
        "Fundamentos matematicos de machine learning: descenso de gradiente "
        "simbolico, regresion lineal/logistica, funciones de costo (MSE, MAE, "
        "cross-entropy, hinge), comparacion de regularizacion L1/L2, y PCA."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "gradient_descent",
                    "linear_regression",
                    "logistic_regression",
                    "cost_functions",
                    "regularization_compare",
                    "pca",
                    "validate",
                ],
                "description": "Que submodulo ejecutar.",
            },
            "expression": {
                "type": "string",
                "description": "Expresion simbolica de la funcion de costo (solo mode=gradient_descent).",
            },
            "variables": {
                "type": "string",
                "description": "Variables de la expresion, separadas por coma (solo gradient_descent).",
            },
            "x0": {
                "type": "array",
                "description": "Punto inicial, mismo orden que 'variables' (solo gradient_descent).",
            },
            "learning_rate": {"type": "number", "default": 0.01},
            "n_iterations": {"type": "integer", "default": 100},
            "X": {
                "type": "array",
                "description": "Matriz de features, lista de listas (linear/logistic_regression, regularization_compare, pca).",
            },
            "y": {
                "type": "array",
                "description": "Vector objetivo/etiquetas (linear/logistic_regression, cost_functions).",
            },
            "y_pred": {
                "type": "array",
                "description": "Predicciones (solo mode=cost_functions).",
            },
            "cost_function": {
                "type": "string",
                "enum": ["mse", "mae", "cross_entropy", "hinge"],
                "default": "mse",
                "description": "Solo mode=cost_functions.",
            },
            "alpha": {
                "type": "number",
                "default": 1.0,
                "description": "Fuerza de regularizacion (solo regularization_compare).",
            },
            "n_components": {
                "type": "integer",
                "description": "Numero de componentes a retener (solo mode=pca). Si se omite, usa todas.",
            },
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------------------
# gradient_descent (simbolico, via sympy)
# ---------------------------------------------------------------------------
def _gradient_descent(expression, variables, x0, learning_rate=0.01, n_iterations=100):
    var_names = [v.strip() for v in variables.split(",")]
    syms = sp.symbols(var_names)
    if not isinstance(syms, (list, tuple)):
        syms = [syms]
    expr = sp.sympify(expression)

    grad_exprs = [sp.diff(expr, s) for s in syms]
    f_num = sp.lambdify(syms, expr, "numpy")
    grad_num = sp.lambdify(syms, grad_exprs, "numpy")

    x = np.array(x0, dtype=float)
    trajectory = [x.tolist()]
    losses = [float(f_num(*x))]

    for _ in range(n_iterations):
        g = np.array(grad_num(*x), dtype=float)
        x = x - learning_rate * g
        trajectory.append(x.tolist())
        losses.append(float(f_num(*x)))

    return {
        "mode": "gradient_descent",
        "variables": var_names,
        "gradient_symbolic": [str(g) for g in grad_exprs],
        "x_final": x.tolist(),
        "loss_final": losses[-1],
        "loss_initial": losses[0],
        "converged": abs(losses[-1] - losses[-2]) < 1e-10 if len(losses) > 1 else False,
        "n_iterations": n_iterations,
        "trajectory_sample": trajectory[:: max(1, n_iterations // 10)],
        "loss_curve_sample": losses[:: max(1, n_iterations // 10)],
    }


# ---------------------------------------------------------------------------
# linear_regression (ecuaciones normales)
# ---------------------------------------------------------------------------
def _linear_regression(X, y):
    X = np.array(X, dtype=float)
    y = np.array(y, dtype=float)
    X_design = np.column_stack([np.ones(len(X)), X])

    coeffs, _, _, _ = np.linalg.lstsq(X_design, y, rcond=None)
    y_hat = X_design @ coeffs

    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else None

    return {
        "mode": "linear_regression",
        "intercept": float(coeffs[0]),
        "coefficients": coeffs[1:].tolist(),
        "r_squared": r_squared,
        "residuals_sample": (y - y_hat).tolist()[:10],
        "y_pred_sample": y_hat.tolist()[:10],
    }


# ---------------------------------------------------------------------------
# logistic_regression (descenso de gradiente sobre log-loss)
# ---------------------------------------------------------------------------
def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))


def _logistic_regression(X, y, learning_rate=0.1, n_iterations=500):
    X = np.array(X, dtype=float)
    y = np.array(y, dtype=float)
    X_design = np.column_stack([np.ones(len(X)), X])
    n, d = X_design.shape

    w = np.zeros(d)
    losses = []
    for _ in range(n_iterations):
        z = X_design @ w
        p = _sigmoid(z)
        eps = 1e-12
        loss = -np.mean(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))
        losses.append(float(loss))
        grad = X_design.T @ (p - y) / n
        w = w - learning_rate * grad

    p_final = _sigmoid(X_design @ w)
    y_pred = (p_final >= 0.5).astype(int)
    y_int = y.astype(int)

    tp = int(np.sum((y_pred == 1) & (y_int == 1)))
    tn = int(np.sum((y_pred == 0) & (y_int == 0)))
    fp = int(np.sum((y_pred == 1) & (y_int == 0)))
    fn = int(np.sum((y_pred == 0) & (y_int == 1)))
    accuracy = (tp + tn) / n if n > 0 else None

    return {
        "mode": "logistic_regression",
        "intercept": float(w[0]),
        "coefficients": w[1:].tolist(),
        "log_loss_final": losses[-1],
        "log_loss_initial": losses[0],
        "confusion_matrix": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "accuracy": accuracy,
    }


# ---------------------------------------------------------------------------
# cost_functions
# ---------------------------------------------------------------------------
def _cost_functions(y, y_pred, cost_function="mse"):
    y = np.array(y, dtype=float)
    y_pred = np.array(y_pred, dtype=float)

    if cost_function == "mse":
        value = float(np.mean((y - y_pred) ** 2))
    elif cost_function == "mae":
        value = float(np.mean(np.abs(y - y_pred)))
    elif cost_function == "cross_entropy":
        eps = 1e-12
        p = np.clip(y_pred, eps, 1 - eps)
        value = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    elif cost_function == "hinge":
        y_signed = np.where(y <= 0, -1, 1)
        value = float(np.mean(np.maximum(0, 1 - y_signed * y_pred)))
    else:
        raise ValueError(f"cost_function desconocida: {cost_function}")

    return {
        "mode": "cost_functions",
        "cost_function": cost_function,
        "value": value,
        "n_samples": len(y),
    }


# ---------------------------------------------------------------------------
# regularization_compare (Ridge cerrado vs Lasso via coordinate descent)
# ---------------------------------------------------------------------------
def _ridge(X, y, alpha):
    n, d = X.shape
    I = np.eye(d)
    I[0, 0] = 0  # no regularizar el intercept
    return np.linalg.solve(X.T @ X + alpha * I, X.T @ y)


def _lasso_coordinate_descent(X, y, alpha, n_iterations=200):
    n, d = X.shape
    w = np.zeros(d)
    for _ in range(n_iterations):
        for j in range(d):
            if j == 0:
                w[j] = np.mean(y - X[:, 1:] @ w[1:]) if d > 1 else np.mean(y)
                continue
            X_j = X[:, j]
            residual = y - X @ w + w[j] * X_j
            rho = X_j @ residual
            z = X_j @ X_j
            if rho < -alpha / 2:
                w[j] = (rho + alpha / 2) / z
            elif rho > alpha / 2:
                w[j] = (rho - alpha / 2) / z
            else:
                w[j] = 0.0
    return w


def _regularization_compare(X, y, alpha=1.0):
    X = np.array(X, dtype=float)
    y = np.array(y, dtype=float)
    X_design = np.column_stack([np.ones(len(X)), X])

    w_ridge = _ridge(X_design, y, alpha)
    w_lasso = _lasso_coordinate_descent(X_design, y, alpha)

    n_zero_lasso = int(np.sum(np.abs(w_lasso[1:]) < 1e-8))

    return {
        "mode": "regularization_compare",
        "alpha": alpha,
        "ridge": {"intercept": float(w_ridge[0]), "coefficients": w_ridge[1:].tolist()},
        "lasso": {"intercept": float(w_lasso[0]), "coefficients": w_lasso[1:].tolist()},
        "lasso_coeficientes_en_cero": n_zero_lasso,
        "nota": "Lasso empuja coeficientes exactamente a cero (seleccion de variables); Ridge los encoge pero no los anula.",
    }


# ---------------------------------------------------------------------------
# pca
# ---------------------------------------------------------------------------
def _pca(X, n_components=None):
    X = np.array(X, dtype=float)
    X_centered = X - X.mean(axis=0)
    cov = np.cov(X_centered, rowvar=False)
    if cov.ndim == 0:
        cov = cov.reshape(1, 1)

    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]

    total_var = float(np.sum(eigvals))
    explained_ratio = (eigvals / total_var).tolist() if total_var > 0 else eigvals.tolist()

    k = n_components or len(eigvals)
    projection = (X_centered @ eigvecs[:, :k]).tolist()

    return {
        "mode": "pca",
        "eigenvalues": eigvals.tolist(),
        "explained_variance_ratio": explained_ratio,
        "n_components_used": k,
        "projected_data_sample": projection[:10],
    }


# ---------------------------------------------------------------------------
# dispatcher
# ---------------------------------------------------------------------------
def compute_machine_learning_math(mode, **kwargs):
    if mode == "validate":
        return validate()
    if mode == "gradient_descent":
        return _gradient_descent(
            kwargs["expression"], kwargs["variables"], kwargs["x0"],
            kwargs.get("learning_rate", 0.01), kwargs.get("n_iterations", 100),
        )
    elif mode == "linear_regression":
        return _linear_regression(kwargs["X"], kwargs["y"])
    elif mode == "logistic_regression":
        return _logistic_regression(
            kwargs["X"], kwargs["y"],
            kwargs.get("learning_rate", 0.1), kwargs.get("n_iterations", 500),
        )
    elif mode == "cost_functions":
        return _cost_functions(kwargs["y"], kwargs["y_pred"], kwargs.get("cost_function", "mse"))
    elif mode == "regularization_compare":
        return _regularization_compare(kwargs["X"], kwargs["y"], kwargs.get("alpha", 1.0))
    elif mode == "pca":
        return _pca(kwargs["X"], kwargs.get("n_components"))
    else:
        raise ValueError(f"mode desconocido: {mode}")


if __name__ == "__main__":
    print("=== gradient_descent (f = x^2 + y^2, minimo en 0,0) ===")
    r1 = compute_machine_learning_math(
        "gradient_descent", expression="x**2 + y**2", variables="x,y",
        x0=[5.0, 5.0], learning_rate=0.1, n_iterations=50,
    )
    print(json.dumps({k: v for k, v in r1.items() if k not in ("trajectory_sample",)}, indent=2))

    print("\n=== linear_regression (y = 2x + 1 + ruido) ===")
    rng = np.random.default_rng(0)
    X_lin = rng.uniform(0, 10, size=(30, 1))
    y_lin = 2 * X_lin[:, 0] + 1 + rng.normal(0, 0.5, size=30)
    r2 = compute_machine_learning_math("linear_regression", X=X_lin.tolist(), y=y_lin.tolist())
    print("intercept:", r2["intercept"], "| coef:", r2["coefficients"], "| R2:", r2["r_squared"])

    print("\n=== logistic_regression (clasificacion binaria simple) ===")
    X_log = rng.uniform(-3, 3, size=(60, 1))
    y_log = (X_log[:, 0] > 0).astype(int)
    r3 = compute_machine_learning_math("logistic_regression", X=X_log.tolist(), y=y_log.tolist())
    print("accuracy:", r3["accuracy"], "| confusion_matrix:", r3["confusion_matrix"])

    print("\n=== cost_functions (mse, mae, cross_entropy) ===")
    y_true = [1, 0, 1, 1]
    y_hat = [0.9, 0.2, 0.6, 0.4]
    for cf in ["mse", "mae", "cross_entropy"]:
        r4 = compute_machine_learning_math("cost_functions", y=y_true, y_pred=y_hat, cost_function=cf)
        print(f"  {cf}: {r4['value']:.4f}")

    print("\n=== regularization_compare (Ridge vs Lasso) ===")
    r5 = compute_machine_learning_math("regularization_compare", X=X_lin.tolist(), y=y_lin.tolist(), alpha=2.0)
    print("ridge coef:", r5["ridge"]["coefficients"], "| lasso coef:", r5["lasso"]["coefficients"])
    print("lasso coeficientes en cero:", r5["lasso_coeficientes_en_cero"])

    print("\n=== pca (2D correlacionado) ===")
    X_pca = rng.multivariate_normal([0, 0], [[3, 2], [2, 2]], size=100)
    r6 = compute_machine_learning_math("pca", X=X_pca.tolist())
    print("eigenvalues:", [round(v, 3) for v in r6["eigenvalues"]])
    print("explained_variance_ratio:", [round(v, 3) for v in r6["explained_variance_ratio"]])

    print("\nOK - todos los modos corrieron sin excepciones.")

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("machine_learning_math", MACHINE_LEARNING_TOOL_SCHEMA, lambda args, _f=compute_machine_learning_math: _f(**args))


# ---------------------------------------------------------------------------
# Validacion propia (mode="validate") -- llama directo a las funciones
# internas con casos de solucion analitica conocida.
# ---------------------------------------------------------------------------

def validate():
    checks = []

    # 1) gradient_descent: f=x^2+y^2, minimo global en el origen
    r1 = _gradient_descent("x**2 + y**2", "x,y", [5.0, 5.0], learning_rate=0.1, n_iterations=200)
    err1 = max(abs(v) for v in r1["x_final"])
    checks.append({
        "name": "gradient_descent_converge_al_origen_en_x2_mas_y2",
        "passed": err1 < 1e-3,
        "detail": f"x_final={r1['x_final']} loss_final={r1['loss_final']:.2e}",
    })

    # 2) linear_regression: y = 2x + 1 exacto (sin ruido) -> recupera coeficientes exactos
    X = [[0.0], [1.0], [2.0], [3.0], [4.0]]
    y = [1.0, 3.0, 5.0, 7.0, 9.0]
    r2 = _linear_regression(X, y)
    err2 = abs(r2["intercept"] - 1.0) + abs(r2["coefficients"][0] - 2.0)
    checks.append({
        "name": "linear_regression_recupera_pendiente_e_intercepto_exactos",
        "passed": err2 < 1e-8 and abs(r2["r_squared"] - 1.0) < 1e-8,
        "detail": f"intercept={r2['intercept']:.6f} coef={r2['coefficients'][0]:.6f} r2={r2['r_squared']:.6f}",
    })

    # 3) logistic_regression: datos perfectamente separables en 1D -> accuracy 1.0
    X_log = [[-3.0], [-2.0], [-1.0], [1.0], [2.0], [3.0]]
    y_log = [0, 0, 0, 1, 1, 1]
    r3 = _logistic_regression(X_log, y_log, learning_rate=0.5, n_iterations=2000)
    checks.append({
        "name": "logistic_regression_separa_perfectamente_datos_lineales",
        "passed": r3["accuracy"] == 1.0,
        "detail": f"accuracy={r3['accuracy']} confusion_matrix={r3['confusion_matrix']}",
    })

    # 4) cost_functions: mse/mae con y==y_pred deben dar 0 exacto
    y_eq = [1.0, 2.0, 3.0]
    r4a = _cost_functions(y_eq, y_eq, "mse")
    r4b = _cost_functions(y_eq, y_eq, "mae")
    checks.append({
        "name": "cost_functions_mse_mae_cero_con_prediccion_perfecta",
        "passed": r4a["value"] == 0.0 and r4b["value"] == 0.0,
        "detail": f"mse={r4a['value']} mae={r4b['value']}",
    })

    # 5) cost_functions: mse con error conocido (y=[0,0], y_pred=[1,1] -> mse=1.0)
    r5 = _cost_functions([0.0, 0.0], [1.0, 1.0], "mse")
    checks.append({
        "name": "cost_functions_mse_error_conocido",
        "passed": abs(r5["value"] - 1.0) < 1e-12,
        "detail": f"mse={r5['value']}",
    })

    # 6) pca: datos perfectamente colineales -> primer componente explica ~100% de la varianza
    xs = np.linspace(-5, 5, 30)
    data_line = np.column_stack([xs, 2 * xs]).tolist()
    r6 = _pca(data_line, None)
    checks.append({
        "name": "pca_primer_componente_explica_toda_la_varianza_en_datos_colineales",
        "passed": abs(r6["explained_variance_ratio"][0] - 1.0) < 1e-6,
        "detail": f"explained_variance_ratio={r6['explained_variance_ratio']}",
    })

    all_pass = all(c["passed"] for c in checks)
    return {
        "validation_passed": all_pass,
        "n_checks": len(checks),
        "checks": checks,
    }
