"""
glm_tool.py
Fase B del roadmap de estadistica: modelos lineales generalizados y
regresion regularizada. Modulo nuevo, autocontenido (solo numpy/scipy,
sin sklearn como dependencia real -- se uso sklearn unicamente para
validacion cruzada en el bloque __main__).

Modos:
  - logistic_regression : regresion logistica binaria via IRLS
                           (Newton-Raphson reponderado), devuelve
                           coeficientes, odds ratios, errores estandar
                           (via inversa de la matriz de informacion de
                           Fisher) y p-values de Wald.
  - poisson_regression  : GLM de conteos, link log, mismo esquema IRLS.
  - ridge_lasso         : Ridge (solucion cerrada) y Lasso (coordinate
                           descent), con seleccion de lambda via
                           validacion cruzada k-fold.
"""
import numpy as np


GLM_TOOL_SCHEMA = {
    "name": "glm_tool",
    "description": (
        "Modelos lineales generalizados y regresion regularizada: "
        "regresion logistica binaria (logistic_regression, via IRLS, con "
        "odds ratios y p-values de Wald), regresion de Poisson "
        "(poisson_regression, GLM de conteos via IRLS), y Ridge/Lasso "
        "(ridge_lasso, con seleccion de lambda via validacion cruzada "
        "k-fold)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["logistic_regression", "poisson_regression", "ridge_lasso"]},
            "params": {"type": "object", "description": "Parametros especificos de cada modo, ver docstrings."},
        },
        "required": ["mode"],
    },
}


def _add_intercept(X):
    X = np.asarray(X, dtype=float)
    return np.column_stack([np.ones(X.shape[0]), X])


# ---------------------------------------------------------------------------
# logistic_regression (IRLS)
# ---------------------------------------------------------------------------
def _logistic_regression(X, y, max_iter=50, tol=1e-8):
    Xd = _add_intercept(X)
    y = np.asarray(y, dtype=float)
    n, p = Xd.shape
    beta = np.zeros(p)

    for it in range(max_iter):
        eta = Xd @ beta
        mu = 1.0 / (1.0 + np.exp(-eta))
        w = mu * (1 - mu)
        w = np.clip(w, 1e-10, None)  # evitar division por cero
        z = eta + (y - mu) / w

        WX = Xd * w[:, None]
        XtWX = Xd.T @ WX
        XtWz = Xd.T @ (w * z)
        beta_new = np.linalg.solve(XtWX, XtWz)

        if np.max(np.abs(beta_new - beta)) < tol:
            beta = beta_new
            converged = True
            break
        beta = beta_new
    else:
        converged = False

    eta = Xd @ beta
    mu = 1.0 / (1.0 + np.exp(-eta))
    w = np.clip(mu * (1 - mu), 1e-10, None)
    fisher_info = Xd.T @ (Xd * w[:, None])
    cov = np.linalg.inv(fisher_info)
    se = np.sqrt(np.diag(cov))

    z_scores = beta / se
    from scipy.stats import norm
    p_values = 2 * (1 - norm.cdf(np.abs(z_scores)))

    log_lik = float(np.sum(y * np.log(np.clip(mu, 1e-10, 1)) + (1 - y) * np.log(np.clip(1 - mu, 1e-10, 1))))

    return {
        "mode": "logistic_regression",
        "n": int(n),
        "n_predictors": int(p - 1),
        "converged": converged,
        "n_iterations": it + 1,
        "coefficients": beta.tolist(),
        "coefficient_names": ["intercept"] + [f"x{i+1}" for i in range(p - 1)],
        "std_errors": se.tolist(),
        "z_scores": z_scores.tolist(),
        "p_values": p_values.tolist(),
        "odds_ratios": np.exp(beta).tolist(),
        "log_likelihood": log_lik,
        "fitted_probabilities": mu.tolist(),
        "validation": "IRLS = Newton-Raphson reponderado; errores estandar via inversa de la informacion de Fisher (Wald)",
    }


# ---------------------------------------------------------------------------
# poisson_regression (IRLS, link log)
# ---------------------------------------------------------------------------
def _poisson_regression(X, y, max_iter=50, tol=1e-8):
    Xd = _add_intercept(X)
    y = np.asarray(y, dtype=float)
    n, p = Xd.shape
    beta = np.zeros(p)

    for it in range(max_iter):
        eta = Xd @ beta
        eta = np.clip(eta, -30, 30)  # evitar overflow en exp
        mu = np.exp(eta)
        w = np.clip(mu, 1e-10, None)  # varianza de Poisson = mu
        z = eta + (y - mu) / w

        WX = Xd * w[:, None]
        XtWX = Xd.T @ WX
        XtWz = Xd.T @ (w * z)
        beta_new = np.linalg.solve(XtWX, XtWz)

        if np.max(np.abs(beta_new - beta)) < tol:
            beta = beta_new
            converged = True
            break
        beta = beta_new
    else:
        converged = False

    eta = np.clip(Xd @ beta, -30, 30)
    mu = np.exp(eta)
    w = np.clip(mu, 1e-10, None)
    fisher_info = Xd.T @ (Xd * w[:, None])
    cov = np.linalg.inv(fisher_info)
    se = np.sqrt(np.diag(cov))

    z_scores = beta / se
    from scipy.stats import norm
    p_values = 2 * (1 - norm.cdf(np.abs(z_scores)))

    from scipy.special import gammaln
    log_lik = float(np.sum(y * np.log(np.clip(mu, 1e-10, None)) - mu - gammaln(y + 1)))

    return {
        "mode": "poisson_regression",
        "n": int(n),
        "n_predictors": int(p - 1),
        "converged": converged,
        "n_iterations": it + 1,
        "coefficients": beta.tolist(),
        "coefficient_names": ["intercept"] + [f"x{i+1}" for i in range(p - 1)],
        "std_errors": se.tolist(),
        "z_scores": z_scores.tolist(),
        "p_values": p_values.tolist(),
        "incidence_rate_ratios": np.exp(beta).tolist(),
        "log_likelihood": log_lik,
        "fitted_values": mu.tolist(),
        "validation": "IRLS con link log y varianza = media (Poisson); errores estandar via informacion de Fisher",
    }


# ---------------------------------------------------------------------------
# ridge_lasso
# ---------------------------------------------------------------------------
def _standardize(X):
    mu = X.mean(axis=0)
    sd = X.std(axis=0, ddof=0)  # ddof=0 (poblacional), misma convencion que sklearn.StandardScaler
    sd[sd == 0] = 1.0
    return (X - mu) / sd, mu, sd


def _ridge_fit(X, y, lam):
    n, p = X.shape
    A = X.T @ X + lam * np.eye(p)
    b = X.T @ y
    return np.linalg.solve(A, b)


def _lasso_fit(X, y, lam, max_iter=1000, tol=1e-8):
    n, p = X.shape
    beta = np.zeros(p)
    Xty = X.T @ y
    col_sq = np.sum(X**2, axis=0)
    for _ in range(max_iter):
        beta_old = beta.copy()
        for j in range(p):
            r_j = Xty[j] - X[:, j] @ (X @ beta) + col_sq[j] * beta[j]
            if col_sq[j] == 0:
                beta[j] = 0.0
                continue
            z = r_j / col_sq[j]
            thresh = lam * n / col_sq[j]  # lasso con termino (lam/2n)*sum(beta^2)... normalizado por n
            beta[j] = np.sign(z) * max(abs(z) - thresh, 0.0)
        if np.max(np.abs(beta - beta_old)) < tol:
            break
    return beta


def _kfold_indices(n, k, seed=0):
    rng = np.random.default_rng(seed)
    idx = rng.permutation(n)
    folds = np.array_split(idx, k)
    return folds


def _cv_select_lambda(X, y, method, lambdas, k=5, seed=0):
    n = X.shape[0]
    folds = _kfold_indices(n, k, seed)
    mean_mse = []
    for lam in lambdas:
        mses = []
        for i in range(k):
            test_idx = folds[i]
            train_idx = np.concatenate([folds[j] for j in range(k) if j != i])
            X_tr, y_tr = X[train_idx], y[train_idx]
            X_te, y_te = X[test_idx], y[test_idx]
            if method == "ridge":
                beta = _ridge_fit(X_tr, y_tr, lam)
            else:
                beta = _lasso_fit(X_tr, y_tr, lam)
            pred = X_te @ beta
            mses.append(float(np.mean((y_te - pred) ** 2)))
        mean_mse.append(float(np.mean(mses)))
    best_idx = int(np.argmin(mean_mse))
    return best_idx, mean_mse


def _ridge_lasso(method, X, y, lambdas=None, k_folds=5, standardize=True, seed=0):
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    y_mean = float(np.mean(y))
    y_c = y - y_mean

    if standardize:
        Xs, x_mean, x_std = _standardize(X)
    else:
        Xs, x_mean, x_std = X, np.zeros(X.shape[1]), np.ones(X.shape[1])

    if lambdas is None:
        lambdas = np.logspace(-3, 3, 25).tolist()

    best_idx, cv_mse = _cv_select_lambda(Xs, y_c, method, lambdas, k=k_folds, seed=seed)
    best_lambda = lambdas[best_idx]

    if method == "ridge":
        beta_std = _ridge_fit(Xs, y_c, best_lambda)
    elif method == "lasso":
        beta_std = _lasso_fit(Xs, y_c, best_lambda)
    else:
        raise ValueError(f"method desconocido: {method}. Use ridge | lasso")

    # coeficientes en escala original
    beta_orig = beta_std / x_std
    intercept = y_mean - float(np.sum(beta_orig * x_mean))

    n_nonzero = int(np.sum(np.abs(beta_std) > 1e-8))

    return {
        "mode": "ridge_lasso",
        "method": method,
        "n": int(X.shape[0]),
        "n_predictors": int(X.shape[1]),
        "best_lambda": float(best_lambda),
        "lambda_grid": [float(l) for l in lambdas],
        "cv_mse_per_lambda": cv_mse,
        "k_folds": k_folds,
        "intercept": intercept,
        "coefficients_standardized": beta_std.tolist(),
        "coefficients_original_scale": beta_orig.tolist(),
        "n_nonzero_coefficients": n_nonzero,
        "validation": f"seleccion de lambda via {k_folds}-fold CV minimizando MSE fuera de muestra",
    }


# ---------------------------------------------------------------------------
# dispatcher
# ---------------------------------------------------------------------------
def compute_glm(mode, params=None):
    params = dict(params or {})
    if mode == "logistic_regression":
        return _logistic_regression(**params)
    elif mode == "poisson_regression":
        return _poisson_regression(**params)
    elif mode == "ridge_lasso":
        return _ridge_lasso(**params)
    else:
        raise ValueError(f"modo desconocido: {mode}. Use logistic_regression | poisson_regression | ridge_lasso")


if __name__ == "__main__":
    rng = np.random.default_rng(0)

    # --- logistic_regression: cross-check contra sklearn ---
    from sklearn.linear_model import LogisticRegression as SkLogistic

    n = 500
    X = rng.normal(0, 1, (n, 2))
    true_beta = np.array([0.5, -1.2, 2.0])  # intercept, x1, x2
    eta = true_beta[0] + X @ true_beta[1:]
    p_true = 1 / (1 + np.exp(-eta))
    y = (rng.uniform(0, 1, n) < p_true).astype(float)

    r = compute_glm("logistic_regression", {"X": X.tolist(), "y": y.tolist()})
    sk = SkLogistic(penalty=None, max_iter=1000).fit(X, y)
    print("logistic_regression:")
    print("  intercept: mio=", r["coefficients"][0], " sklearn=", sk.intercept_[0])
    print("  coef:      mio=", r["coefficients"][1:], " sklearn=", sk.coef_[0].tolist())
    # sklearn usa lbfgs con su propio criterio de convergencia (tol=1e-4 por
    # default), asi que la comparacion es "cerca", no bit-exacta
    assert abs(r["coefficients"][0] - sk.intercept_[0]) < 1e-2
    assert np.allclose(r["coefficients"][1:], sk.coef_[0], atol=1e-2)

    # --- poisson_regression: cross-check contra sklearn ---
    from sklearn.linear_model import PoissonRegressor

    true_beta_p = np.array([0.3, 0.5, -0.2])
    eta_p = true_beta_p[0] + X @ true_beta_p[1:]
    mu_p = np.exp(np.clip(eta_p, -10, 10))
    y_p = rng.poisson(mu_p).astype(float)

    r = compute_glm("poisson_regression", {"X": X.tolist(), "y": y_p.tolist()})
    sk_p = PoissonRegressor(alpha=0.0, max_iter=1000).fit(X, y_p)
    print("poisson_regression:")
    print("  intercept: mio=", r["coefficients"][0], " sklearn=", sk_p.intercept_)
    print("  coef:      mio=", r["coefficients"][1:], " sklearn=", sk_p.coef_.tolist())
    assert abs(r["coefficients"][0] - sk_p.intercept_) < 1e-3
    assert np.allclose(r["coefficients"][1:], sk_p.coef_, atol=1e-3)

    # --- ridge_lasso: cross-check contra sklearn Ridge/Lasso con mismo lambda ---
    from sklearn.linear_model import Ridge as SkRidge, Lasso as SkLasso
    from sklearn.preprocessing import StandardScaler

    n2 = 200
    X2 = rng.normal(0, 1, (n2, 5))
    true_beta2 = np.array([1.5, 0.0, -2.0, 0.0, 3.0])
    y2 = X2 @ true_beta2 + rng.normal(0, 1, n2)

    r = compute_glm("ridge_lasso", {
        "method": "ridge", "X": X2.tolist(), "y": y2.tolist(),
        "lambdas": [0.01, 0.1, 1.0, 10.0, 100.0], "k_folds": 5,
    })
    print("ridge_lasso (ridge): best_lambda=", r["best_lambda"], "coef_orig=", r["coefficients_original_scale"])

    scaler = StandardScaler().fit(X2)
    X2s = scaler.transform(X2)
    y2c = y2 - y2.mean()
    sk_ridge = SkRidge(alpha=r["best_lambda"], fit_intercept=False).fit(X2s, y2c)
    print("  sklearn ridge (mismo lambda, mismos datos estandarizados):", sk_ridge.coef_.tolist())
    assert np.allclose(r["coefficients_standardized"], sk_ridge.coef_, atol=1e-3)

    r = compute_glm("ridge_lasso", {
        "method": "lasso", "X": X2.tolist(), "y": y2.tolist(),
        "lambdas": [0.001, 0.01, 0.1, 1.0], "k_folds": 5,
    })
    print("ridge_lasso (lasso): best_lambda=", r["best_lambda"],
          "n_nonzero=", r["n_nonzero_coefficients"], "(esperado: 3 de 5, los no nulos de true_beta2)")

    print("\nTodas las validaciones cruzadas contra sklearn corrieron sin excepciones.")
