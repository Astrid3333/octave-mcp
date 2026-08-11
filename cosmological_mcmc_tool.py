"""
cosmological_mcmc_tool.py

Fase 3 de semiclassical_cosmology_tool: ajuste MCMC (Metropolis-Hastings
self-contained, sin dependencias externas de sampler) de un modelo LCDM
plano con techo holonomico tipo LQG, contra H(z).

Modelo:
    H(z)^2 = H0^2 * [ Om0*(1+z)^3 + (1-Om0) ] * (1 - rho_total(z)/rho_c)

donde rho_total(z) = H0^2 * [ Om0*(1+z)^3 + (1-Om0) ]  (kappa=1, mismas
unidades que en semiclassical_cosmology_tool: rho_c en unidades de H0^2).

A las densidades cubiertas por datos de bajo z (z < 2), rho_total/rho_c
es minusculo salvo que rho_c sea artificialmente bajo, asi que el ajuste
recupera bien (H0, Om0) y solo pone una cota inferior sobre rho_c -- eso
es un resultado fisico esperado, no un bug del sampler.

Modos:
  - mock_recovery: genera datos sinteticos con parametros verdaderos
    conocidos (mismo patron de ruido/z que el dataset real) y verifica
    que el MCMC los recupera dentro de ~2 sigma antes de confiar en el
    ajuste sobre datos reales.
  - fit_hz_chronometers: corre el MCMC sobre la compilacion real de 31
    mediciones de H(z) por cronometros cosmicos (Marra & Sapone 2018,
    arXiv:1712.09676, que a su vez compila Zhang et al. 2014, Simon et
    al. 2005, Stern et al. 2010, Moresco et al. 2012/2016, Ratsimbazafy
    et al. 2017).
"""

import numpy as np

# ---------------------------------------------------------------------------
# Dataset real: 31 mediciones de H(z) por cronometros cosmicos
# (z, H(z) en km/s/Mpc, sigma en km/s/Mpc)
# Marra & Sapone (2018), arXiv:1712.09676
# ---------------------------------------------------------------------------
HZ_CHRONOMETERS_DATA = [
    (0.07, 69.0, 19.6), (0.09, 69.0, 12.0), (0.12, 68.6, 26.2),
    (0.17, 83.0, 8.0), (0.179, 75.0, 4.0), (0.199, 75.0, 5.0),
    (0.2, 72.9, 29.6), (0.27, 77.0, 14.0), (0.28, 88.8, 36.6),
    (0.352, 83.0, 14.0), (0.3802, 83.0, 13.5), (0.4, 95.0, 17.0),
    (0.4004, 77.0, 10.2), (0.4247, 87.1, 11.2), (0.4497, 92.8, 12.9),
    (0.47, 89.0, 49.6), (0.4783, 80.9, 9.0), (0.48, 97.0, 62.0),
    (0.593, 104.0, 13.0), (0.68, 92.0, 8.0), (0.781, 105.0, 12.0),
    (0.875, 125.0, 17.0), (0.88, 90.0, 40.0), (0.9, 117.0, 23.0),
    (1.037, 154.0, 20.0), (1.3, 168.0, 17.0), (1.363, 160.0, 33.6),
    (1.43, 177.0, 18.0), (1.53, 140.0, 14.0), (1.75, 202.0, 40.0),
    (1.965, 186.5, 50.4),
]

PARAM_NAMES = ["H0", "Om0", "log10_rho_c"]

# Prior: uniforme en cada parametro. rho_c en escala log10 porque el
# ajuste solo puede acotarlo por abajo (regimen de bajo z no llega a
# rho~rho_c), y un prior log-uniforme amplio evita sesgar esa cota.
PRIOR_BOUNDS = {
    "H0": (40.0, 100.0),
    "Om0": (0.05, 0.6),
    "log10_rho_c": (3.0, 8.0),
}

TRUE_PARAMS_MOCK = {"H0": 70.0, "Om0": 0.30, "log10_rho_c": 6.0}


def _h_model(z, H0, Om0, rho_c):
    """H(z) para LCDM plano con techo holonomico LQG (kappa=1)."""
    z = np.asarray(z, dtype=float)
    e2 = Om0 * (1.0 + z) ** 3 + (1.0 - Om0)
    rho_total = H0 ** 2 * e2
    correction = 1.0 - rho_total / rho_c
    # cerca del bounce la correccion tocaria 0 (o negativo si rho_c es
    # demasiado bajo para el prior); se clampa para mantener el
    # likelihood bien definido durante el muestreo, is_true_bounce=false
    # efectivo en esa region del prior queda penalizado via chi2 alto
    # cuando el modelo ya no puede reproducir H(z) real.
    correction = np.clip(correction, 1e-8, None)
    return H0 * np.sqrt(np.clip(e2, 0.0, None)) * np.sqrt(correction)


def _log_prior(theta):
    for name, val in zip(PARAM_NAMES, theta):
        lo, hi = PRIOR_BOUNDS[name]
        if not (lo <= val <= hi):
            return -np.inf
    return 0.0


def _log_likelihood(theta, z, h_obs, sigma):
    H0, Om0, log10_rho_c = theta
    rho_c = 10.0 ** log10_rho_c
    h_pred = _h_model(z, H0, Om0, rho_c)
    resid = (h_obs - h_pred) / sigma
    return -0.5 * np.sum(resid ** 2)


def _log_posterior(theta, z, h_obs, sigma):
    lp = _log_prior(theta)
    if not np.isfinite(lp):
        return -np.inf
    return lp + _log_likelihood(theta, z, h_obs, sigma)


def _run_metropolis_hastings(z, h_obs, sigma, n_steps=20000, burn_in=5000,
                              thin=5, seed=42, step_scale=None):
    """Metropolis-Hastings simple con propuesta gaussiana diagonal y
    adaptacion de escala por fases (sin dependencias externas de MCMC)."""
    rng = np.random.default_rng(seed)
    ndim = len(PARAM_NAMES)

    if step_scale is None:
        step_scale = np.array([3.0, 0.05, 0.3])  # H0, Om0, log10_rho_c

    # punto inicial: centro del prior con jitter
    theta = np.array([
        0.5 * (PRIOR_BOUNDS[n][0] + PRIOR_BOUNDS[n][1]) for n in PARAM_NAMES
    ])
    theta = theta + rng.normal(scale=step_scale * 0.1, size=ndim)

    log_post = _log_posterior(theta, z, h_obs, sigma)
    chain = np.zeros((n_steps, ndim))
    log_posts = np.zeros(n_steps)
    n_accept = 0

    for i in range(n_steps):
        proposal = theta + rng.normal(scale=step_scale, size=ndim)
        log_post_prop = _log_posterior(proposal, z, h_obs, sigma)
        log_alpha = log_post_prop - log_post
        if np.log(rng.uniform()) < log_alpha:
            theta = proposal
            log_post = log_post_prop
            n_accept += 1
        chain[i] = theta
        log_posts[i] = log_post

        # adaptacion simple de la escala de propuesta durante el burn-in
        if i > 0 and i % 500 == 0 and i < burn_in:
            recent_rate = n_accept / (i + 1)
            if recent_rate < 0.15:
                step_scale *= 0.8
            elif recent_rate > 0.5:
                step_scale *= 1.2

    acceptance_rate = n_accept / n_steps
    post_burn = chain[burn_in::thin]
    post_burn_logp = log_posts[burn_in::thin]

    best_idx = int(np.argmax(post_burn_logp))
    best_theta = post_burn[best_idx]

    summary = {}
    for j, name in enumerate(PARAM_NAMES):
        samples_j = post_burn[:, j]
        summary[name] = {
            "mean": float(np.mean(samples_j)),
            "std": float(np.std(samples_j)),
            "median": float(np.median(samples_j)),
            "p05": float(np.percentile(samples_j, 5)),
            "p95": float(np.percentile(samples_j, 95)),
        }

    return {
        "samples": post_burn,
        "acceptance_rate": acceptance_rate,
        "summary": summary,
        "best_theta": best_theta,
        "n_samples_post_burn": post_burn.shape[0],
    }


def _chi2_at(theta, z, h_obs, sigma):
    H0, Om0, log10_rho_c = theta
    rho_c = 10.0 ** log10_rho_c
    h_pred = _h_model(z, H0, Om0, rho_c)
    return float(np.sum(((h_obs - h_pred) / sigma) ** 2))


def _mode_mock_recovery(params):
    n_steps = int(params.get("n_steps", 60000))
    burn_in = int(params.get("burn_in", 15000))
    thin = int(params.get("thin", 10))
    seed = int(params.get("seed", 42))

    z = np.array([row[0] for row in HZ_CHRONOMETERS_DATA])
    sigma = np.array([row[2] for row in HZ_CHRONOMETERS_DATA])

    rng = np.random.default_rng(seed)
    true_theta = np.array([TRUE_PARAMS_MOCK[n] for n in PARAM_NAMES])
    rho_c_true = 10.0 ** TRUE_PARAMS_MOCK["log10_rho_c"]
    h_true = _h_model(z, TRUE_PARAMS_MOCK["H0"], TRUE_PARAMS_MOCK["Om0"], rho_c_true)
    h_obs = h_true + rng.normal(scale=sigma)

    result = _run_metropolis_hastings(z, h_obs, sigma, n_steps=n_steps,
                                       burn_in=burn_in, thin=thin, seed=seed)

    chi2 = _chi2_at(result["best_theta"], z, h_obs, sigma)
    dof = len(z) - len(PARAM_NAMES)

    recovery_check = {}
    for name, true_val in TRUE_PARAMS_MOCK.items():
        s = result["summary"][name]
        n_sigma_off = abs(s["mean"] - true_val) / s["std"] if s["std"] > 0 else float("inf")
        recovery_check[name] = {
            "true_value": true_val,
            "recovered_mean": s["mean"],
            "recovered_std": s["std"],
            "n_sigma_off": n_sigma_off,
            "within_2sigma": bool(n_sigma_off <= 2.0),
        }

    all_within_2sigma = all(v["within_2sigma"] for v in recovery_check.values())

    return {
        "mode": "mock_recovery",
        "n_data_points": len(z),
        "true_params": TRUE_PARAMS_MOCK,
        "posterior_summary": result["summary"],
        "recovery_check": recovery_check,
        "all_params_within_2sigma": all_within_2sigma,
        "chi2": chi2,
        "dof": dof,
        "chi2_per_dof": chi2 / dof,
        "acceptance_rate": result["acceptance_rate"],
        "n_samples_post_burn": result["n_samples_post_burn"],
        "note": "Datos sinteticos generados con los mismos z y sigma que el dataset real de cronometros cosmicos, para no sesgar el test de recuperacion. Si all_params_within_2sigma=true, el pipeline MCMC recupera parametros conocidos antes de confiar en el ajuste sobre datos reales.",
    }


def _mode_fit_hz_chronometers(params):
    n_steps = int(params.get("n_steps", 60000))
    burn_in = int(params.get("burn_in", 15000))
    thin = int(params.get("thin", 10))
    seed = int(params.get("seed", 42))

    z = np.array([row[0] for row in HZ_CHRONOMETERS_DATA])
    h_obs = np.array([row[1] for row in HZ_CHRONOMETERS_DATA])
    sigma = np.array([row[2] for row in HZ_CHRONOMETERS_DATA])

    result = _run_metropolis_hastings(z, h_obs, sigma, n_steps=n_steps,
                                       burn_in=burn_in, thin=thin, seed=seed)

    chi2 = _chi2_at(result["best_theta"], z, h_obs, sigma)
    dof = len(z) - len(PARAM_NAMES)

    rho_c_summary = result["summary"]["log10_rho_c"]
    rho_c_lower_95 = 10.0 ** rho_c_summary["p05"]

    return {
        "mode": "fit_hz_chronometers",
        "dataset": "31 mediciones H(z) por cronometros cosmicos (Marra & Sapone 2018, arXiv:1712.09676)",
        "n_data_points": len(z),
        "posterior_summary": {
            "H0": result["summary"]["H0"],
            "Om0": result["summary"]["Om0"],
            "log10_rho_c": result["summary"]["log10_rho_c"],
        },
        "rho_c_lower_bound_95pct": rho_c_lower_95,
        "chi2": chi2,
        "dof": dof,
        "chi2_per_dof": chi2 / dof,
        "acceptance_rate": result["acceptance_rate"],
        "n_samples_post_burn": result["n_samples_post_burn"],
        "note": "A las densidades cubiertas por z<2 (regimen de bajo z), rho_total/rho_c es despreciable salvo rho_c artificialmente bajo: el fondo LCDM (H0, Om0) sale bien determinado, y rho_c solo recibe una cota inferior (empujada hacia el borde superior del prior en log10_rho_c) -- resultado fisico esperado, no un artefacto del sampler. Para constrenir rho_c con datos reales haria falta el universo muy temprano (rho~rho_c), fuera del alcance de H(z) de bajo z.",
    }


def compute_cosmological_mcmc_tool(mode, params=None):
    params = params or {}
    if mode == "mock_recovery":
        return _mode_mock_recovery(params)
    elif mode == "fit_hz_chronometers":
        return _mode_fit_hz_chronometers(params)
    else:
        return {"error": f"Modo desconocido: {mode}. Modos validos: mock_recovery, fit_hz_chronometers."}


COSMOLOGICAL_MCMC_TOOL_SCHEMA = {
    "name": "cosmological_mcmc_tool",
    "description": (
        "MCMC (Metropolis-Hastings self-contained) para ajustar un modelo LCDM plano "
        "con techo holonomico tipo LQG (fase 3 de semiclassical_cosmology_tool) contra "
        "H(z). mode=mock_recovery: genera datos sinteticos con parametros conocidos y "
        "verifica que el sampler los recupera dentro de 2 sigma. mode=fit_hz_chronometers: "
        "ajusta contra la compilacion real de 31 mediciones de H(z) por cronometros "
        "cosmicos (Marra & Sapone 2018), devolviendo posteriors de H0 y Om0 y una cota "
        "inferior sobre rho_c (no constrenido por datos de bajo z, resultado fisico "
        "esperado)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["mock_recovery", "fit_hz_chronometers"]},
            "params": {
                "type": "object",
                "properties": {
                    "n_steps": {"type": "integer", "description": "Pasos totales del MCMC (default 20000)"},
                    "burn_in": {"type": "integer", "description": "Pasos de burn-in descartados (default 5000)"},
                    "thin": {"type": "integer", "description": "Factor de thinning post burn-in (default 5)"},
                    "seed": {"type": "integer", "description": "Semilla RNG (default 42)"},
                },
            },
        },
        "required": ["mode"],
    },
}
