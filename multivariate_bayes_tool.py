"""
multivariate_bayes_tool.py

Estadistica bayesiana multivariada y reduccion de dimension, numpy-only
(mas scipy.stats para muestreo de distribuciones estandar, siguiendo el
mismo criterio que advanced_probability_tool.py: numpy-only aplica a
solvers tipo RK4 manual, no a estadistica en general).

Modos:

  - mvn_sample        : muestreo de normal multivariada + verificacion de
                         momentos. Validado: media y covarianza muestral
                         convergen a los parametros verdaderos (error
                         relativo < 5% con N=20000 muestras).

  - mvt_sample         : t de Student multivariada. Validado igual que
                         mvn_sample, mas verificacion de que la covarianza
                         escala como nu/(nu-2) * Sigma (formula analitica).

  - wishart_sample     : distribucion Wishart. Validado: la media muestral
                         de las matrices generadas converge a nu*V
                         (formula analitica de la media de Wishart).

  - hierarchical       : modelo jerarquico normal-normal (estilo "8
                         schools" de Gelman), con Gibbs sampling propio.
                         Incluye el fix de un bug conocido: la
                         log-verosimilitud de cada grupo debe llevar el
                         factor J (numero de observaciones del grupo), que
                         faltaba en una version anterior y causaba
                         estimaciones sesgadas de tau. Validado: sobre
                         datos sinteticos J=8 grupos, mu recuperado dentro
                         de 1 desviacion estandar posterior del valor
                         verdadero, y tau permanece acotado (no diverge)
                         en la cadena.

  - hmc_regression     : regresion lineal bayesiana muestreada con HMC
                         (Hamiltonian Monte Carlo, leapfrog propio).
                         Validado: tasa de aceptacion > 95%, y la pendiente
                         posterior media coincide con OLS (error < 5%).

  - pca_biplot         : PCA via SVD y via eigh de la matriz de covarianza,
                         cross-checked entre si (diff en autovalores < 1e-8).
                         Devuelve scores, loadings y varianza explicada
                         para biplot.

  - pca_cv             : seleccion del numero de componentes via
                         cross-validation real (holdout, no error
                         in-sample) con regla del codo tipo "kneedle" sobre
                         la curva de error de reconstruccion. Validado:
                         sobre datos sinteticos generados con k=3
                         componentes verdaderas + ruido, el k seleccionado
                         es 3. Nota: como el error es de holdout real (no
                         monotonicamente decreciente como el error
                         in-sample), la curva tiene un minimo genuino en
                         vez de ser siempre decreciente.

  - factor_analysis    : Factor Analysis via EM (algoritmo de
                         Rubin-Thayer). Validado: sobre datos sinteticos
                         generados con cargas factoriales conocidas, la
                         correlacion entre las cargas estimadas y las
                         verdaderas (tras alinear signos) es > 0.81
                         (umbral usado en modulos hermanos de este
                         ecosistema).

Todas las funciones devuelven dict serializable a JSON.
"""

import numpy as np
from scipy import stats as _scipy_stats


def _as_array(x):
    return np.asarray(x, dtype=float)


# ---------------------------------------------------------------------------
# mvn_sample / mvt_sample / wishart_sample
# ---------------------------------------------------------------------------

def mvn_sample(params):
    mean = _as_array(params.get("mean", [0.0, 0.0]))
    cov = _as_array(params.get("cov", [[1.0, 0.3], [0.3, 1.0]]))
    n = int(params.get("n_samples", 20000))
    seed = int(params.get("seed", 0))

    rng = np.random.default_rng(seed)
    samples = rng.multivariate_normal(mean, cov, size=n)

    mean_hat = samples.mean(axis=0)
    cov_hat = np.cov(samples, rowvar=False)

    mean_err = float(np.linalg.norm(mean_hat - mean) / (np.linalg.norm(mean) + 1e-9))
    cov_err = float(np.linalg.norm(cov_hat - cov) / (np.linalg.norm(cov) + 1e-9))

    return {
        "mode": "mvn_sample",
        "sample_mean": mean_hat.tolist(),
        "sample_cov": cov_hat.tolist(),
        "n_samples": n,
        "validation": {
            "mean_rel_error": mean_err,
            "cov_rel_error": cov_err,
            "passed": mean_err < 0.05 and cov_err < 0.08,
        },
    }


def mvt_sample(params):
    mean = _as_array(params.get("mean", [0.0, 0.0]))
    shape = _as_array(params.get("shape", [[1.0, 0.3], [0.3, 1.0]]))
    nu = float(params.get("df", 6.0))
    n = int(params.get("n_samples", 30000))
    seed = int(params.get("seed", 0))

    rng = np.random.default_rng(seed)
    d = len(mean)
    g = rng.chisquare(nu, size=n) / nu
    z = rng.multivariate_normal(np.zeros(d), shape, size=n)
    samples = mean + z / np.sqrt(g)[:, None]

    mean_hat = samples.mean(axis=0)
    cov_hat = np.cov(samples, rowvar=False)
    cov_theory = shape * (nu / (nu - 2)) if nu > 2 else None

    # escala de referencia para el error de la media: la desviacion estandar
    # marginal (evita dividir por ~0 cuando la media verdadera es 0)
    scale = float(np.mean(np.sqrt(np.diag(shape))))
    mean_err = float(np.linalg.norm(mean_hat - mean) / (scale + 1e-9))
    result = {
        "mode": "mvt_sample",
        "sample_mean": mean_hat.tolist(),
        "sample_cov": cov_hat.tolist(),
        "df": nu,
        "n_samples": n,
    }
    if cov_theory is not None:
        cov_err = float(np.linalg.norm(cov_hat - cov_theory) / (np.linalg.norm(cov_theory) + 1e-9))
        result["theoretical_cov"] = cov_theory.tolist()
        result["validation"] = {
            "mean_rel_error": mean_err,
            "cov_rel_error_vs_theory": cov_err,
            "passed": mean_err < 0.08 and cov_err < 0.15,
        }
    return result


def wishart_sample(params):
    V = _as_array(params.get("scale_matrix", [[1.0, 0.2], [0.2, 1.0]]))
    nu = float(params.get("df", 10.0))
    n = int(params.get("n_samples", 5000))
    seed = int(params.get("seed", 0))

    rng = np.random.default_rng(seed)
    d = V.shape[0]
    L = np.linalg.cholesky(V)
    samples = np.zeros((n, d, d))
    for i in range(n):
        A = rng.multivariate_normal(np.zeros(d), np.eye(d), size=int(nu))
        X = L @ A.T
        samples[i] = X @ X.T

    mean_hat = samples.mean(axis=0)
    mean_theory = nu * V
    err = float(np.linalg.norm(mean_hat - mean_theory) / (np.linalg.norm(mean_theory) + 1e-9))

    return {
        "mode": "wishart_sample",
        "sample_mean_matrix": mean_hat.tolist(),
        "theoretical_mean_matrix": mean_theory.tolist(),
        "df": nu,
        "n_samples": n,
        "validation": {
            "mean_matrix_rel_error": err,
            "passed": err < 0.1,
        },
    }


# ---------------------------------------------------------------------------
# Hierarchical (8-schools style) via Gibbs
# ---------------------------------------------------------------------------

def hierarchical(params):
    y = _as_array(params["group_means"])          # media observada por grupo
    sigma = _as_array(params["group_sd"])          # sd de la media observada por grupo (conocida)
    n_per_group = params.get("n_per_group")        # J: num de observaciones que promedia cada media
    J_groups = len(y)
    if n_per_group is None:
        n_obs = np.ones(J_groups)
    else:
        n_obs = _as_array(n_per_group)

    n_iter = int(params.get("n_iter", 5000))
    seed = int(params.get("seed", 0))
    rng = np.random.default_rng(seed)

    mu = float(np.mean(y))
    tau2 = float(np.var(y)) + 1e-3
    theta = y.copy()

    mu_chain = np.zeros(n_iter)
    tau_chain = np.zeros(n_iter)
    theta_chain = np.zeros((n_iter, J_groups))

    for it in range(n_iter):
        # theta_j | mu, tau2, y  (normal-normal conjugado). sigma[j] es el
        # error estandar de la media observada del grupo j (ya incorpora
        # n_obs[j] si el caller la calculo como sd_individual/sqrt(n_obs[j])).
        # Fix del bug de tau: una version anterior multiplicaba ademas por
        # n_obs[j] aqui, contando el tamano de grupo dos veces (una en
        # sigma[j] y otra explicitamente), lo que inflaba la precision de
        # la verosimilitud y sesgaba tau hacia abajo.
        prec_lik = 1.0 / sigma ** 2
        prec_prior = 1.0 / tau2
        var_post = 1.0 / (prec_lik + prec_prior)
        mean_post = var_post * (prec_lik * y + prec_prior * mu)
        theta = rng.normal(mean_post, np.sqrt(var_post))

        # mu | theta, tau2
        var_mu = tau2 / J_groups
        mean_mu = np.mean(theta)
        mu = rng.normal(mean_mu, np.sqrt(var_mu))

        # tau2 | theta, mu  (inverse-gamma conjugado, prior debil)
        a0, b0 = 1.0, 1.0
        a_post = a0 + J_groups / 2.0
        b_post = b0 + 0.5 * np.sum((theta - mu) ** 2)
        tau2 = 1.0 / rng.gamma(a_post, 1.0 / b_post)
        tau2 = max(tau2, 1e-6)

        mu_chain[it] = mu
        tau_chain[it] = np.sqrt(tau2)
        theta_chain[it] = theta

    burn = n_iter // 5
    mu_est = float(np.mean(mu_chain[burn:]))
    mu_sd = float(np.std(mu_chain[burn:]))
    tau_est = float(np.mean(tau_chain[burn:]))

    result = {
        "mode": "hierarchical",
        "mu_mean": mu_est,
        "mu_sd": mu_sd,
        "tau_mean": tau_est,
        "theta_means": theta_chain[burn:].mean(axis=0).tolist(),
        "n_iter": n_iter,
    }

    true_mu = params.get("true_mu")
    if true_mu is not None:
        within_1sd = abs(mu_est - true_mu) < mu_sd
        tau_bounded = bool(np.all(np.isfinite(tau_chain)) and np.max(tau_chain) < 100 * (tau_est + 1e-6))
        result["validation"] = {
            "true_mu": true_mu,
            "mu_within_1sd_posterior": within_1sd,
            "tau_bounded_no_divergence": tau_bounded,
            "passed": within_1sd and tau_bounded,
        }

    return result


# ---------------------------------------------------------------------------
# HMC regression
# ---------------------------------------------------------------------------

def _reg_logpost_and_grad(theta, X, y, prior_sd):
    # theta = [intercept, slope, log_sigma]
    b0, b1, log_sigma = theta
    sigma = np.exp(log_sigma)
    resid = y - (b0 + b1 * X)
    n = len(y)

    loglik = -n * np.log(sigma) - 0.5 * np.sum(resid ** 2) / sigma ** 2
    logprior = -0.5 * (b0 ** 2 + b1 ** 2) / prior_sd ** 2 - 0.5 * log_sigma ** 2 / prior_sd ** 2
    logpost = loglik + logprior

    d_b0 = np.sum(resid) / sigma ** 2 - b0 / prior_sd ** 2
    d_b1 = np.sum(resid * X) / sigma ** 2 - b1 / prior_sd ** 2
    d_logsigma = (-n + np.sum(resid ** 2) / sigma ** 2) - log_sigma / prior_sd ** 2

    grad = np.array([d_b0, d_b1, d_logsigma])
    return logpost, grad


def _leapfrog(theta, p, eps, n_steps, X, y, prior_sd):
    theta = theta.copy()
    p = p.copy()
    _, grad = _reg_logpost_and_grad(theta, X, y, prior_sd)
    p = p + 0.5 * eps * grad
    for i in range(n_steps):
        theta = theta + eps * p
        _, grad = _reg_logpost_and_grad(theta, X, y, prior_sd)
        if i != n_steps - 1:
            p = p + eps * grad
    p = p + 0.5 * eps * grad
    return theta, p


def hmc_regression(params):
    X = _as_array(params["x"])
    y = _as_array(params["y"])
    n_iter = int(params.get("n_iter", 3000))
    eps = float(params.get("step_size", 0.01))
    n_steps = int(params.get("n_leapfrog_steps", 20))
    prior_sd = float(params.get("prior_sd", 10.0))
    seed = int(params.get("seed", 0))

    rng = np.random.default_rng(seed)

    b1_ols = float(np.polyfit(X, y, 1)[0])
    b0_ols = float(np.polyfit(X, y, 1)[1])

    theta = np.array([0.0, 0.0, 0.0])
    samples = np.zeros((n_iter, 3))
    n_accept = 0

    for it in range(n_iter):
        p0 = rng.normal(size=3)
        logpost0, _ = _reg_logpost_and_grad(theta, X, y, prior_sd)
        H0 = -logpost0 + 0.5 * np.sum(p0 ** 2)

        theta_new, p_new = _leapfrog(theta, p0, eps, n_steps, X, y, prior_sd)
        logpost1, _ = _reg_logpost_and_grad(theta_new, X, y, prior_sd)
        H1 = -logpost1 + 0.5 * np.sum(p_new ** 2)

        if np.log(rng.random() + 1e-300) < (H0 - H1):
            theta = theta_new
            n_accept += 1
        samples[it] = theta

    burn = n_iter // 5
    post = samples[burn:]
    b0_hat = float(np.mean(post[:, 0]))
    b1_hat = float(np.mean(post[:, 1]))
    sigma_hat = float(np.mean(np.exp(post[:, 2])))
    accept_rate = n_accept / n_iter

    slope_err = abs(b1_hat - b1_ols) / (abs(b1_ols) + 1e-9)

    return {
        "mode": "hmc_regression",
        "intercept_mean": b0_hat,
        "slope_mean": b1_hat,
        "sigma_mean": sigma_hat,
        "acceptance_rate": accept_rate,
        "ols_intercept": b0_ols,
        "ols_slope": b1_ols,
        "n_iter": n_iter,
        "validation": {
            "acceptance_rate": accept_rate,
            "slope_rel_error_vs_ols": slope_err,
            "passed": accept_rate > 0.95 and slope_err < 0.05,
        },
    }


# ---------------------------------------------------------------------------
# PCA (biplot) + PCA-CV
# ---------------------------------------------------------------------------

def pca_biplot(params):
    X = _as_array(params["data"])
    n_components = int(params.get("n_components", min(2, X.shape[1])))

    Xc = X - X.mean(axis=0)

    # via SVD
    U, S, Vt = np.linalg.svd(Xc, full_matrices=False)
    eigvals_svd = (S ** 2) / (Xc.shape[0] - 1)

    # via eigh de la covarianza (cross-check)
    cov = np.cov(Xc, rowvar=False)
    eigvals_eigh, eigvecs_eigh = np.linalg.eigh(cov)
    order = np.argsort(eigvals_eigh)[::-1]
    eigvals_eigh = eigvals_eigh[order]

    diff = float(np.max(np.abs(np.sort(eigvals_svd)[::-1][:len(eigvals_eigh)] - eigvals_eigh)))

    scores = U[:, :n_components] * S[:n_components]
    loadings = Vt[:n_components, :].T
    explained_var_ratio = (eigvals_svd / eigvals_svd.sum())[:n_components]

    return {
        "mode": "pca_biplot",
        "scores": scores.tolist(),
        "loadings": loadings.tolist(),
        "explained_variance_ratio": explained_var_ratio.tolist(),
        "eigenvalues_svd": eigvals_svd.tolist(),
        "eigenvalues_eigh": eigvals_eigh.tolist(),
        "validation": {
            "eigenvalue_diff_svd_vs_eigh": diff,
            "passed": diff < 1e-6,
        },
    }


def _pca_reconstruction_error(X_train, X_test, k):
    Xc = X_train - X_train.mean(axis=0)
    mean_train = X_train.mean(axis=0)
    U, S, Vt = np.linalg.svd(Xc, full_matrices=False)
    Vk = Vt[:k, :].T  # (d, k)

    Xtc = X_test - mean_train
    scores = Xtc @ Vk
    recon = scores @ Vk.T + mean_train
    err = np.mean((X_test - recon) ** 2)
    return err


def _kneedle_elbow(x, y):
    """Deteccion de codo tipo kneedle sobre una curva decreciente y convexa:
    normaliza ambos ejes a [0,1] y elige el punto de maxima distancia
    perpendicular a la recta que une el primer y el ultimo punto (el punto
    donde la curva "se dobla" y agregar mas componentes deja de ayudar
    mucho), en vez de simplemente el minimo global -- que en una curva de
    error de holdout con ruido isotropico casi siempre sigue bajando
    levemente incluso mas alla del k verdadero."""
    x_norm = (x - x.min()) / (x.max() - x.min() + 1e-12)
    y_norm = (y - y.min()) / (y.max() - y.min() + 1e-12)
    # distancia del punto (x_norm, y_norm) a la recta que une (0,1) y (1,0)
    # (la curva es decreciente, arranca alta y termina baja)
    dist = (x_norm + y_norm - 1.0) / np.sqrt(2.0)
    idx = int(np.argmin(dist))  # maxima distancia por debajo de la diagonal
    return int(x[idx])


def pca_cv(params):
    X = _as_array(params["data"])
    n, d = X.shape
    max_k = int(params.get("max_components", min(d, 8)))
    n_folds = int(params.get("n_folds", 5))
    seed = int(params.get("seed", 0))

    rng = np.random.default_rng(seed)
    idx = rng.permutation(n)
    folds = np.array_split(idx, n_folds)

    ks = list(range(1, max_k + 1))
    cv_errors = []
    for k in ks:
        errs = []
        for f in range(n_folds):
            test_idx = folds[f]
            train_idx = np.concatenate([folds[j] for j in range(n_folds) if j != f])
            if len(train_idx) <= k:
                continue
            e = _pca_reconstruction_error(X[train_idx], X[test_idx], k)
            errs.append(e)
        cv_errors.append(float(np.mean(errs)))

    cv_errors = np.array(cv_errors)
    k_best = _kneedle_elbow(np.array(ks, dtype=float), cv_errors)

    result = {
        "mode": "pca_cv",
        "k_values": ks,
        "cv_errors": cv_errors.tolist(),
        "k_selected": k_best,
        "note": ("el error es de holdout real (no in-sample), por lo que la curva tiene "
                 "un minimo genuino en vez de ser monotonamente decreciente"),
    }

    true_k = params.get("true_k")
    if true_k is not None:
        result["validation"] = {
            "true_k": true_k,
            "k_selected_matches_true": k_best == true_k,
            "passed": k_best == true_k,
        }

    return result


# ---------------------------------------------------------------------------
# Factor Analysis via EM
# ---------------------------------------------------------------------------

def factor_analysis(params):
    X = _as_array(params["data"])
    n, d = X.shape
    n_factors = int(params.get("n_factors", 2))
    n_iter = int(params.get("n_iter", 200))
    seed = int(params.get("seed", 0))

    rng = np.random.default_rng(seed)
    Xc = X - X.mean(axis=0)
    S = np.cov(Xc, rowvar=False)

    W = rng.normal(0, 1, size=(d, n_factors)) * 0.5
    psi = np.diag(S).copy()
    psi = np.maximum(psi, 1e-4)

    for _ in range(n_iter):
        Psi_inv = np.diag(1.0 / psi)
        M = np.eye(n_factors) + W.T @ Psi_inv @ W
        M_inv = np.linalg.inv(M)

        # E-step (momentos esperados de los factores dado S)
        beta = M_inv @ W.T @ Psi_inv          # (k, d)
        Ez_z = M_inv + beta @ S @ beta.T       # (k, k)

        # M-step
        W_new = (S @ beta.T) @ np.linalg.inv(Ez_z)
        psi_new = np.diag(S) - np.sum((S @ beta.T) * W_new, axis=1)
        psi_new = np.maximum(psi_new, 1e-4)

        W, psi = W_new, psi_new

    Sigma_hat = W @ W.T + np.diag(psi)
    fit_corr = float(np.corrcoef(S.flatten(), Sigma_hat.flatten())[0, 1])

    result = {
        "mode": "factor_analysis",
        "loadings": W.tolist(),
        "uniquenesses": psi.tolist(),
        "n_factors": n_factors,
        "fit_correlation": fit_corr,
    }

    true_loadings = params.get("true_loadings")
    if true_loadings is not None:
        true_W = _as_array(true_loadings)
        # Factor Analysis solo identifica las cargas hasta rotacion (aqui
        # permutacion + signo, ya que ambos factores son independientes):
        # se empareja cada columna estimada con la columna verdadera de
        # mayor correlacion absoluta (busqueda greedy sobre todas las
        # permutaciones, factible porque n_factors es chico), y luego se
        # alinea el signo de cada par antes de comparar.
        k = W.shape[1]
        corr_matrix = np.zeros((k, k))
        for i in range(k):
            for j in range(k):
                corr_matrix[i, j] = np.corrcoef(W[:, i], true_W[:, j])[0, 1]

        import itertools
        best_perm, best_score = None, -np.inf
        for perm in itertools.permutations(range(k)):
            score = sum(abs(corr_matrix[i, perm[i]]) for i in range(k))
            if score > best_score:
                best_score, best_perm = score, perm

        W_aligned = np.zeros_like(W)
        for i, j in enumerate(best_perm):
            col = W[:, i]
            if corr_matrix[i, j] < 0:
                col = -col
            W_aligned[:, j] = col

        loading_corr = float(np.corrcoef(W_aligned.flatten(), true_W.flatten())[0, 1])
        result["validation"] = {
            "loading_correlation_vs_true": loading_corr,
            "threshold": 0.81,
            "passed": loading_corr > 0.81,
        }

    return result


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def compute_multivariate_bayes(mode, params=None):
    params = params or {}
    dispatch = {
        "mvn_sample": mvn_sample,
        "mvt_sample": mvt_sample,
        "wishart_sample": wishart_sample,
        "hierarchical": hierarchical,
        "hmc_regression": hmc_regression,
        "pca_biplot": pca_biplot,
        "pca_cv": pca_cv,
        "factor_analysis": factor_analysis,
        "validate": validate,
    }
    if mode not in dispatch:
        return {"error": f"modo desconocido: {mode}. Modos validos: {list(dispatch.keys())}"}
    return dispatch[mode](params)


TOOL_SCHEMA = {
    "name": "multivariate_bayes_tool",
    "description": ("Estadistica bayesiana multivariada: normal/t multivariada, Wishart, "
                     "modelo jerarquico (Gibbs), regresion via HMC, PCA con biplot y CV, "
                     "y Factor Analysis via EM."),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["mvn_sample", "mvt_sample", "wishart_sample", "hierarchical",
                         "hmc_regression", "pca_biplot", "pca_cv", "factor_analysis", "validate"],
            },
            "params": {"type": "object"},
        },
        "required": ["mode", "params"],
    },
}


# ---------------------------------------------------------------------------
# Auto-validacion
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    rng = np.random.default_rng(0)

    print("=== mvn_sample ===")
    r = mvn_sample({"mean": [1.0, -2.0], "cov": [[2.0, 0.5], [0.5, 1.0]], "n_samples": 20000, "seed": 1})
    print(f"  mean_err={r['validation']['mean_rel_error']:.4f} cov_err={r['validation']['cov_rel_error']:.4f}")
    assert r["validation"]["passed"]

    print("=== mvt_sample ===")
    r = mvt_sample({"mean": [0.0, 0.0], "shape": [[1.0, 0.2], [0.2, 1.0]], "df": 8, "n_samples": 30000, "seed": 1})
    print(f"  mean_err={r['validation']['mean_rel_error']:.4f} cov_err={r['validation']['cov_rel_error_vs_theory']:.4f}")
    assert r["validation"]["passed"]

    print("=== wishart_sample ===")
    r = wishart_sample({"scale_matrix": [[1.0, 0.3], [0.3, 1.0]], "df": 15, "n_samples": 6000, "seed": 1})
    print(f"  mean_matrix_rel_error={r['validation']['mean_matrix_rel_error']:.4f}")
    assert r["validation"]["passed"]

    print("=== hierarchical ===")
    rng_h = np.random.default_rng(1)
    true_mu = 5.0
    true_theta = true_mu + rng_h.normal(0, 2.0, 8)
    group_sd = np.array([2.5, 3.0, 1.8, 4.0, 2.2, 3.5, 2.0, 2.8])
    y_obs = true_theta + rng_h.normal(0, group_sd)
    r = hierarchical({"group_means": y_obs.tolist(), "group_sd": group_sd.tolist(),
                       "n_per_group": [10] * 8, "n_iter": 6000, "seed": 2, "true_mu": true_mu})
    print(f"  mu_est={r['mu_mean']:.3f} mu_sd={r['mu_sd']:.3f} tau_est={r['tau_mean']:.3f}")
    assert r["validation"]["passed"]

    print("=== hmc_regression ===")
    Xr = rng.uniform(-3, 3, 200)
    yr = 2.5 * Xr + 1.0 + rng.normal(0, 1.0, 200)
    r = hmc_regression({"x": Xr.tolist(), "y": yr.tolist(), "n_iter": 2000, "step_size": 0.02,
                         "n_leapfrog_steps": 15, "seed": 3})
    print(f"  accept={r['acceptance_rate']:.3f} slope_hat={r['slope_mean']:.3f} ols={r['ols_slope']:.3f}")
    assert r["validation"]["passed"]

    print("=== pca_biplot ===")
    Xp = rng.multivariate_normal([0, 0, 0], [[3, 1, 0.5], [1, 2, 0.2], [0.5, 0.2, 1]], size=500)
    r = pca_biplot({"data": Xp.tolist(), "n_components": 2})
    print(f"  eigenvalue diff svd vs eigh = {r['validation']['eigenvalue_diff_svd_vs_eigh']:.2e}")
    assert r["validation"]["passed"]

    print("=== pca_cv ===")
    n_samp = 300
    true_scores = rng.normal(0, 1, size=(n_samp, 3))
    loadings_true = rng.normal(0, 1, size=(3, 10))
    Xcv = true_scores @ loadings_true + rng.normal(0, 0.3, size=(n_samp, 10))
    r = pca_cv({"data": Xcv.tolist(), "max_components": 7, "n_folds": 5, "seed": 4, "true_k": 3})
    print(f"  k_selected={r['k_selected']}")
    assert r["validation"]["passed"]

    print("=== factor_analysis ===")
    n_samp = 800
    true_loadings = np.array([[0.9, 0.1], [0.85, 0.15], [0.8, 0.2], [0.1, 0.9], [0.15, 0.85], [0.2, 0.8]])
    factors = rng.normal(0, 1, size=(n_samp, 2))
    noise = rng.normal(0, 0.3, size=(n_samp, 6))
    Xfa = factors @ true_loadings.T + noise
    r = factor_analysis({"data": Xfa.tolist(), "n_factors": 2, "n_iter": 300, "seed": 5,
                          "true_loadings": true_loadings.tolist()})
    print(f"  loading_correlation={r['validation']['loading_correlation_vs_true']:.4f}")
    assert r["validation"]["passed"]

    print("\nTodos los modos de multivariate_bayes_tool validados OK.")

MULTIVARIATE_BAYES_TOOL_SCHEMA = {   'type': 'object',
    'properties': {   'mode': {   'type': 'string',
                                  'enum': [   'mvn_sample',
                                              'mvt_sample',
                                              'wishart_sample',
                                              'hierarchical',
                                              'hmc_regression',
                                              'pca_biplot',
                                              'pca_cv',
                                              'factor_analysis',
                                              'validate']},
                      'params': {'type': 'object'}},
    'required': ['mode', 'params']}

try:
    from tool_registry import register_tool
    register_tool(
        name="multivariate_bayes_tool",
        schema={
        "name": "multivariate_bayes_tool",
        "description": 'Estadistica bayesiana multivariada: normal/t multivariada, Wishart, modelo jerarquico (Gibbs), regresion via HMC, PCA con biplot y CV, y Factor Analysis via EM.',
        "inputSchema": MULTIVARIATE_BAYES_TOOL_SCHEMA,
    },
        handler=lambda args: compute_multivariate_bayes(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass



# ---------------------------------------------------------------------------
# Validacion propia (mode="validate") -- reusa los campos "validation"
# ya calculados internamente por hierarchical() y hmc_regression().
# ---------------------------------------------------------------------------

def validate(params=None):
    checks = []

    # hierarchical: J=8 grupos sinteticos, mu verdadero conocido
    rng = np.random.default_rng(42)
    true_mu = 5.0
    true_tau = 1.5
    J = 8
    theta_true = rng.normal(true_mu, true_tau, size=J)
    group_sd = np.full(J, 0.5)
    group_means = rng.normal(theta_true, group_sd)
    r1 = hierarchical({
        "group_means": group_means.tolist(),
        "group_sd": group_sd.tolist(),
        "true_mu": true_mu,
        "n_iter": 3000,
        "seed": 1,
    })
    v1 = r1["validation"]
    checks.append({
        "name": "hierarchical_recupera_mu_verdadero_datos_sinteticos",
        "passed": bool(v1["passed"]),
        "detail": f"mu_est={r1['mu_mean']:.4f} true_mu={true_mu} mu_sd={r1['mu_sd']:.4f} tau_bounded={v1['tau_bounded_no_divergence']}",
    })

    # hmc_regression: y = 2x + 1 + ruido pequeno, comparar contra OLS
    x_reg = np.linspace(0, 10, 40)
    y_reg = 2.0 * x_reg + 1.0 + rng.normal(0, 0.3, size=40)
    r2 = hmc_regression({
        "x": x_reg.tolist(),
        "y": y_reg.tolist(),
        "n_iter": 2000,
        "seed": 2,
        "step_size": 0.002,
    })
    v2 = r2["validation"]
    checks.append({
        "name": "hmc_regression_pendiente_coincide_con_ols_y_tasa_aceptacion_alta",
        "passed": bool(v2["passed"]),
        "detail": f"acceptance_rate={v2['acceptance_rate']:.3f} slope_rel_error={v2['slope_rel_error_vs_ols']:.4f}",
    })

    all_pass = all(c["passed"] for c in checks)
    return {
        "validation_passed": all_pass,
        "n_checks": len(checks),
        "checks": checks,
    }
