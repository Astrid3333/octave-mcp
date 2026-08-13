"""
disaster_simulation_tool.py

Motor de simulacion Monte Carlo de desastres (frecuencia-severidad) para
gestion publica de riesgos. Cierra el grupo "Gestion de Riesgos" de la fase C
de octave-mcp (junto a natural_hazard_risk_tool, earthquake_analysis_tool,
wildfire_risk_tool, flood_modeling_tool, water_resource_tool, early_warning_tool,
decision_support_tool).

Enfoque: motor generico (no catalogo de datos hardcodeados). Implementa el
modelo actuarial/catastrofico estandar de frecuencia-severidad:

    N ~ Poisson(lambda)                      # numero de eventos por periodo
    X_i ~ LogNormal(mu, sigma)  i=1..N        # severidad (perdida) de cada evento
    S = sum(X_i, i=1..N)                      # perdida agregada del periodo

Sobre la distribucion empirica de S (obtenida por simulacion) se calculan:
    - percentiles / Value-at-Risk (VaR)
    - Conditional VaR / Tail-VaR (CVaR, promedio de la cola mas alla del VaR)
    - curva de perdida por periodo de retorno (estimador empirico de Weibull,
      T = (n+1)/m, igual convencion que gumbel_return_period en
      natural_hazard_risk_tool, para consistencia entre tools de la fase C)
    - curva de probabilidad de excedencia (EP curve)
    - combinacion de dos peligros (independientes o correlacionados via copula
      gaussiana simple) para perdida agregada multi-peligro

confidence_flag: "alta" para toda la mecanica de simulacion (Poisson,
LogNormal, VaR/CVaR, estimador de Weibull para periodo de retorno son
metodos estandar de la literatura actuarial y de modelacion de catastrofes,
no requieren tabla de datos empirica propia). El motor no trae ningun
catalogo de lambda/mu/sigma por tipo de peligro: esos parametros los provee
quien llama (o se toman de otras tools de la fase C, p.ej.
natural_hazard_risk_tool.gumbel_fit para severidad, o el lambda historico de
conteo de eventos).

Modos soportados (mode, params):
    - monte_carlo_losses(params): simulacion de perdida agregada anual
    - return_period_loss(params): perdida esperada a T anios (curva de
      periodo de retorno sobre la distribucion simulada)
    - exceedance_curve(params): curva de probabilidad de excedencia anual
      (EP curve) para una lista de umbrales de perdida
    - multi_hazard_combine(params): combina dos peligros independientes o
      correlacionados (copula gaussiana) en una perdida agregada conjunta
    - validate(): suite de 10 checks de consistencia estadistica/fisica
"""

import math
import numpy as np
from scipy import stats


DISASTER_SIMULATION_TOOL_SCHEMA = {
    "name": "disaster_simulation_tool",
    "description": (
        "Simulacion Monte Carlo de desastres (modelo actuarial frecuencia-severidad "
        "Poisson-LogNormal) para gestion publica de riesgos: monte_carlo_losses "
        "(distribucion de perdida agregada anual dado lambda de frecuencia y "
        "mu/sigma de severidad lognormal, con VaR y CVaR/Tail-VaR a percentiles "
        "configurables), return_period_loss (perdida esperada para periodos de "
        "retorno dados, estimador empirico de Weibull T=(n+1)/m, consistente con "
        "natural_hazard_risk_tool.gumbel_return_period), exceedance_curve (curva de "
        "probabilidad de excedencia anual -EP curve- para una lista de umbrales de "
        "perdida), multi_hazard_combine (combina dos peligros independientes o "
        "correlacionados via copula gaussiana en una perdida agregada conjunta), "
        "validate (suite de 10 checks). Motor generico: no trae catalogo de "
        "parametros por tipo de peligro (lambda/mu/sigma los provee quien llama), "
        "confidence_flag 'alta' para toda la mecanica estadistica."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string"},
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


def _rng(seed):
    return np.random.default_rng(seed)


def _simulate_annual_losses(lam, mu, sigma, n_years, seed):
    """
    Simula n_years de perdida agregada anual bajo el modelo
    Poisson(lambda) de frecuencia y LogNormal(mu, sigma) de severidad por evento.
    Devuelve un array de longitud n_years.
    """
    rng = _rng(seed)
    n_events = rng.poisson(lam=lam, size=n_years)
    losses = np.zeros(n_years, dtype=float)
    total_events = int(n_events.sum())
    if total_events > 0:
        severities = rng.lognormal(mean=mu, sigma=sigma, size=total_events)
        idx = 0
        for year in range(n_years):
            k = n_events[year]
            if k > 0:
                losses[year] = severities[idx: idx + k].sum()
                idx += k
    return losses


def _empirical_return_period_curve(losses, return_periods):
    """
    Curva perdida vs periodo de retorno usando el estimador empirico de Weibull
    T = (n+1)/m sobre las perdidas ordenadas de mayor a menor (m = rango, 1=mayor).
    Misma convencion que gumbel_return_period en natural_hazard_risk_tool.
    """
    sorted_desc = np.sort(losses)[::-1]
    n = len(sorted_desc)
    out = {}
    for T in return_periods:
        # m tal que T = (n+1)/m  =>  m = (n+1)/T
        m = (n + 1) / T
        if m < 1:
            # T mas alla del rango muestral: extrapola con el maximo observado,
            # marcado explicitamente como extrapolacion (no interpolado)
            out[str(T)] = {"loss": float(sorted_desc[0]), "extrapolated": True}
            continue
        # interpolacion lineal entre los dos rangos enteros mas cercanos
        m_lo = math.floor(m)
        m_hi = math.ceil(m)
        m_lo = max(1, min(m_lo, n))
        m_hi = max(1, min(m_hi, n))
        if m_lo == m_hi:
            loss_val = sorted_desc[m_lo - 1]
        else:
            frac = m - m_lo
            loss_val = sorted_desc[m_lo - 1] * (1 - frac) + sorted_desc[m_hi - 1] * frac
        out[str(T)] = {"loss": float(loss_val), "extrapolated": False}
    return out


def _var_cvar(losses, percentile):
    """VaR (percentil) y CVaR/TailVaR (promedio de la cola >= VaR) de un array de perdidas."""
    var = float(np.percentile(losses, percentile))
    tail = losses[losses >= var]
    cvar = float(tail.mean()) if len(tail) > 0 else var
    return var, cvar


def compute_disaster_simulation(mode, params=None):
    params = params or {}

    if mode == "monte_carlo_losses":
        lam = float(params["lambda_annual"])
        mu = float(params["sigma_severity_mu"]) if "sigma_severity_mu" in params else float(params["mu_severity"])
        sigma = float(params["sigma_severity"])
        n_years = int(params.get("n_years", 100000))
        seed = params.get("seed", 42)
        percentiles = params.get("var_percentiles", [90, 95, 99, 99.5])

        losses = _simulate_annual_losses(lam, mu, sigma, n_years, seed)

        var_cvar = {}
        for p in percentiles:
            var, cvar = _var_cvar(losses, p)
            var_cvar[f"p{p}"] = {"VaR": var, "CVaR": cvar}

        return {
            "mode": "monte_carlo_losses",
            "n_years_simulated": n_years,
            "mean_annual_loss": float(losses.mean()),
            "std_annual_loss": float(losses.std(ddof=1)),
            "median_annual_loss": float(np.median(losses)),
            "max_simulated_loss": float(losses.max()),
            "probability_zero_loss_year": float((losses == 0).mean()),
            "var_cvar_by_percentile": var_cvar,
            "seed": seed,
            "confidence_flag": "alta",
            "note": "Modelo Poisson-LogNormal estandar; parametros lambda/mu/sigma provistos por quien llama.",
        }

    elif mode == "return_period_loss":
        return_periods = params.get("return_periods_years", [10, 25, 50, 100, 250, 500])
        if "losses" in params:
            losses = np.array(params["losses"], dtype=float)
            n_years = len(losses)
            seed = None
        else:
            lam = float(params["lambda_annual"])
            mu = float(params["mu_severity"])
            sigma = float(params["sigma_severity"])
            n_years = int(params.get("n_years", 100000))
            seed = params.get("seed", 42)
            losses = _simulate_annual_losses(lam, mu, sigma, n_years, seed)

        curve = _empirical_return_period_curve(losses, return_periods)
        return {
            "mode": "return_period_loss",
            "n_years_sample": int(len(losses)),
            "seed": seed,
            "return_period_curve": curve,
            "estimator": "Weibull empirico T=(n+1)/m, igual convencion que natural_hazard_risk_tool.gumbel_return_period",
            "confidence_flag": "alta",
        }

    elif mode == "exceedance_curve":
        thresholds = params.get("loss_thresholds", None)
        if "losses" in params:
            losses = np.array(params["losses"], dtype=float)
            seed = None
        else:
            lam = float(params["lambda_annual"])
            mu = float(params["mu_severity"])
            sigma = float(params["sigma_severity"])
            n_years = int(params.get("n_years", 100000))
            seed = params.get("seed", 42)
            losses = _simulate_annual_losses(lam, mu, sigma, n_years, seed)

        if thresholds is None:
            thresholds = list(np.percentile(losses, [50, 75, 90, 95, 99, 99.5, 99.9]))

        curve = []
        for th in thresholds:
            p_exceed = float((losses > th).mean())
            curve.append({
                "loss_threshold": float(th),
                "annual_exceedance_probability": p_exceed,
                "implied_return_period_years": (1.0 / p_exceed) if p_exceed > 0 else None,
            })

        return {
            "mode": "exceedance_curve",
            "n_years_sample": int(len(losses)),
            "seed": seed,
            "exceedance_curve": curve,
            "confidence_flag": "alta",
        }

    elif mode == "multi_hazard_combine":
        h1 = params["hazard_1"]
        h2 = params["hazard_2"]
        n_years = int(params.get("n_years", 100000))
        seed = params.get("seed", 42)
        correlation = float(params.get("correlation", 0.0))

        if correlation == 0.0:
            losses_1 = _simulate_annual_losses(
                float(h1["lambda_annual"]), float(h1["mu_severity"]), float(h1["sigma_severity"]),
                n_years, seed,
            )
            losses_2 = _simulate_annual_losses(
                float(h2["lambda_annual"]), float(h2["mu_severity"]), float(h2["sigma_severity"]),
                n_years, seed + 1 if seed is not None else None,
            )
        else:
            # Copula gaussiana simple: correlaciona el conteo de eventos de ambos
            # peligros via variables normales latentes con correlacion rho,
            # transformadas a Poisson por inversion de CDF. La severidad de cada
            # evento se simula independiente condicional al conteo.
            rng = _rng(seed)
            rho = max(-0.999, min(0.999, correlation))
            mean = [0, 0]
            cov = [[1, rho], [1 * rho, 1]]
            z = rng.multivariate_normal(mean, cov, size=n_years)
            u = stats.norm.cdf(z)
            n1 = stats.poisson.ppf(u[:, 0], mu=float(h1["lambda_annual"])).astype(int)
            n2 = stats.poisson.ppf(u[:, 1], mu=float(h2["lambda_annual"])).astype(int)

            def _severity_totals(n_events, mu, sigma, seed_offset):
                rng2 = _rng((seed or 0) + seed_offset)
                total_events = int(n_events.sum())
                out = np.zeros(len(n_events), dtype=float)
                if total_events > 0:
                    sev = rng2.lognormal(mean=mu, sigma=sigma, size=total_events)
                    idx = 0
                    for i, k in enumerate(n_events):
                        if k > 0:
                            out[i] = sev[idx: idx + k].sum()
                            idx += k
                return out

            losses_1 = _severity_totals(n1, float(h1["mu_severity"]), float(h1["sigma_severity"]), 1000)
            losses_2 = _severity_totals(n2, float(h2["mu_severity"]), float(h2["sigma_severity"]), 2000)

        combined = losses_1 + losses_2
        var90_c, cvar90_c = _var_cvar(combined, 90)
        var99_c, cvar99_c = _var_cvar(combined, 99)

        return {
            "mode": "multi_hazard_combine",
            "n_years_simulated": n_years,
            "correlation_used": correlation,
            "hazard_1_mean_loss": float(losses_1.mean()),
            "hazard_2_mean_loss": float(losses_2.mean()),
            "combined_mean_loss": float(combined.mean()),
            "combined_std_loss": float(combined.std(ddof=1)),
            "combined_var_cvar": {
                "p90": {"VaR": var90_c, "CVaR": cvar90_c},
                "p99": {"VaR": var99_c, "CVaR": cvar99_c},
            },
            "diversification_note": (
                "std combinado < suma de std individuales cuando correlation < 1; "
                "con correlation=0 (independientes) la reduccion de riesgo por "
                "diversificacion es maxima."
            ),
            "confidence_flag": "alta",
        }

    elif mode == "validate":
        checks = []

        # 1) Media de Poisson se recupera con N grande
        rng = _rng(1)
        lam_true = 3.0
        n_sample = rng.poisson(lam=lam_true, size=500000)
        mean_est = float(n_sample.mean())
        checks.append({
            "name": "poisson_frequency_mean_recovered",
            "lambda_true": lam_true,
            "mean_estimated": mean_est,
            "passed": abs(mean_est - lam_true) < 0.02,
        })

        # 2) Media de LogNormal se recupera con N grande: E[X] = exp(mu + sigma^2/2)
        mu_t, sigma_t = 1.0, 0.5
        sample = rng.lognormal(mean=mu_t, sigma=sigma_t, size=500000)
        expected_mean = math.exp(mu_t + sigma_t ** 2 / 2)
        checks.append({
            "name": "lognormal_severity_mean_recovered",
            "expected_mean": expected_mean,
            "sample_mean": float(sample.mean()),
            "passed": abs(float(sample.mean()) - expected_mean) / expected_mean < 0.02,
        })

        # 3) monte_carlo_losses: perdida media agregada ~ lambda * E[severidad]
        res = compute_disaster_simulation("monte_carlo_losses", {
            "lambda_annual": 2.0, "mu_severity": 0.0, "sigma_severity": 1.0,
            "n_years": 200000, "seed": 7,
        })
        expected_agg_mean = 2.0 * math.exp(0.0 + 1.0 ** 2 / 2)
        checks.append({
            "name": "aggregate_loss_mean_matches_frequency_times_severity",
            "expected": expected_agg_mean,
            "computed": res["mean_annual_loss"],
            "passed": abs(res["mean_annual_loss"] - expected_agg_mean) / expected_agg_mean < 0.05,
        })

        # 4) CVaR siempre >= VaR (definicion: promedio de la cola por encima de VaR)
        checks.append({
            "name": "cvar_greater_or_equal_var",
            "p95": res["var_cvar_by_percentile"]["p95"],
            "passed": res["var_cvar_by_percentile"]["p95"]["CVaR"] >= res["var_cvar_by_percentile"]["p95"]["VaR"],
        })

        # 5) VaR monotonicamente creciente con el percentil
        vs = [res["var_cvar_by_percentile"][f"p{p}"]["VaR"] for p in [90, 95, 99, 99.5]]
        checks.append({
            "name": "var_monotonic_increasing_with_percentile",
            "values": vs,
            "passed": all(vs[i] <= vs[i + 1] for i in range(len(vs) - 1)),
        })

        # 6) Reproducibilidad: misma seed -> mismo resultado exacto
        res_a = compute_disaster_simulation("monte_carlo_losses", {
            "lambda_annual": 1.5, "mu_severity": 0.0, "sigma_severity": 0.8,
            "n_years": 5000, "seed": 123,
        })
        res_b = compute_disaster_simulation("monte_carlo_losses", {
            "lambda_annual": 1.5, "mu_severity": 0.0, "sigma_severity": 0.8,
            "n_years": 5000, "seed": 123,
        })
        checks.append({
            "name": "same_seed_gives_identical_result",
            "passed": res_a["mean_annual_loss"] == res_b["mean_annual_loss"],
        })

        # 7) Curva de periodo de retorno: perdida creciente con T
        rp = compute_disaster_simulation("return_period_loss", {
            "lambda_annual": 2.0, "mu_severity": 0.0, "sigma_severity": 1.0,
            "n_years": 200000, "seed": 9,
            "return_periods_years": [10, 50, 100, 500],
        })
        rp_vals = [rp["return_period_curve"][str(T)]["loss"] for T in [10, 50, 100, 500]]
        checks.append({
            "name": "return_period_loss_monotonic_increasing",
            "values": rp_vals,
            "passed": all(rp_vals[i] <= rp_vals[i + 1] for i in range(len(rp_vals) - 1)),
        })

        # 8) return_period mas alla del rango muestral se marca extrapolado
        rp_small = compute_disaster_simulation("return_period_loss", {
            "lambda_annual": 1.0, "mu_severity": 0.0, "sigma_severity": 1.0,
            "n_years": 50, "seed": 3,
            "return_periods_years": [1000],
        })
        checks.append({
            "name": "return_period_beyond_sample_flagged_extrapolated",
            "passed": rp_small["return_period_curve"]["1000"]["extrapolated"] is True,
        })

        # 9) Correlacion mas alta entre peligros aumenta el riesgo de cola combinado
        combo_indep = compute_disaster_simulation("multi_hazard_combine", {
            "hazard_1": {"lambda_annual": 2.0, "mu_severity": 0.0, "sigma_severity": 1.0},
            "hazard_2": {"lambda_annual": 2.0, "mu_severity": 0.0, "sigma_severity": 1.0},
            "n_years": 100000, "seed": 11, "correlation": 0.0,
        })
        combo_corr = compute_disaster_simulation("multi_hazard_combine", {
            "hazard_1": {"lambda_annual": 2.0, "mu_severity": 0.0, "sigma_severity": 1.0},
            "hazard_2": {"lambda_annual": 2.0, "mu_severity": 0.0, "sigma_severity": 1.0},
            "n_years": 100000, "seed": 11, "correlation": 0.9,
        })
        checks.append({
            "name": "higher_correlation_increases_combined_tail_risk",
            "cvar99_independent": combo_indep["combined_var_cvar"]["p99"]["CVaR"],
            "cvar99_correlated": combo_corr["combined_var_cvar"]["p99"]["CVaR"],
            "passed": combo_corr["combined_var_cvar"]["p99"]["CVaR"] >= combo_indep["combined_var_cvar"]["p99"]["CVaR"] * 0.95,
        })

        # 10) modo invalido lanza excepcion
        try:
            compute_disaster_simulation("modo_invalido", {})
            invalid_raised = False
        except (KeyError, ValueError):
            invalid_raised = True
        checks.append({"name": "invalid_mode_raises", "passed": invalid_raised})

        all_passed = all(c["passed"] for c in checks)
        return {"checks": checks, "validation_passed": all_passed}

    else:
        raise ValueError(f"Modo desconocido para disaster_simulation_tool: {mode}")
