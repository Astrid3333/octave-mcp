#!/usr/bin/env python3
"""
financial_math_tool.py
Matematica financiera: Black-Scholes, griegas de opciones, Value at Risk
(parametrico/historico/Monte Carlo), valuacion de anualidades/perpetuidades,
bonos (precio/YTM/duracion/convexidad), y riesgo de catastrofe (VaR ajustado
por riesgo climatico/ambiental via proceso de Poisson compuesto).
"""
import math
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq


def _bs_d1_d2(S, K, T, r, sigma, q=0.0):
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def compute_black_scholes(S, K, T, r, sigma, q=0.0, option_type="call"):
    d1, d2 = _bs_d1_d2(S, K, T, r, sigma, q)
    if option_type == "call":
        price = S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    elif option_type == "put":
        price = K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)
    else:
        raise ValueError(f"option_type desconocido: {option_type}")
    return {
        "mode": "black_scholes",
        "option_type": option_type,
        "price": round(price, 6),
        "d1": round(d1, 6),
        "d2": round(d2, 6),
    }


def compute_option_greeks(S, K, T, r, sigma, q=0.0, option_type="call"):
    d1, d2 = _bs_d1_d2(S, K, T, r, sigma, q)
    pdf_d1 = norm.pdf(d1)
    if option_type == "call":
        delta = math.exp(-q * T) * norm.cdf(d1)
        rho = K * T * math.exp(-r * T) * norm.cdf(d2) / 100
        theta = (
            -S * pdf_d1 * sigma * math.exp(-q * T) / (2 * math.sqrt(T))
            - r * K * math.exp(-r * T) * norm.cdf(d2)
            + q * S * math.exp(-q * T) * norm.cdf(d1)
        ) / 365
    elif option_type == "put":
        delta = -math.exp(-q * T) * norm.cdf(-d1)
        rho = -K * T * math.exp(-r * T) * norm.cdf(-d2) / 100
        theta = (
            -S * pdf_d1 * sigma * math.exp(-q * T) / (2 * math.sqrt(T))
            + r * K * math.exp(-r * T) * norm.cdf(-d2)
            - q * S * math.exp(-q * T) * norm.cdf(-d1)
        ) / 365
    else:
        raise ValueError(f"option_type desconocido: {option_type}")
    gamma = math.exp(-q * T) * pdf_d1 / (S * sigma * math.sqrt(T))
    vega = S * math.exp(-q * T) * pdf_d1 * math.sqrt(T) / 100
    return {
        "mode": "option_greeks",
        "option_type": option_type,
        "delta": round(delta, 6),
        "gamma": round(gamma, 6),
        "vega": round(vega, 6),
        "theta": round(theta, 6),
        "rho": round(rho, 6),
    }


def compute_value_at_risk(method="parametric", confidence=0.95, portfolio_value=1.0,
                           mu=0.0, sigma=None, returns=None, horizon_days=1,
                           n_simulations=100000, seed=None):
    z = norm.ppf(1 - confidence)
    if method == "parametric":
        if sigma is None:
            raise ValueError("sigma es requerido para method='parametric'")
        h = horizon_days
        var_pct = -(mu * h + z * sigma * math.sqrt(h))
        var_value = var_pct * portfolio_value
        return {
            "mode": "value_at_risk", "method": method, "confidence": confidence,
            "var_pct": round(var_pct, 6), "var_value": round(var_value, 2),
        }
    elif method == "historical":
        if not returns:
            raise ValueError("returns es requerido para method='historical'")
        arr = np.asarray(returns, dtype=float)
        var_pct = -np.percentile(arr, (1 - confidence) * 100)
        var_value = var_pct * portfolio_value
        return {
            "mode": "value_at_risk", "method": method, "confidence": confidence,
            "var_pct": round(float(var_pct), 6), "var_value": round(float(var_value), 2),
            "n_observations": len(arr),
        }
    elif method == "monte_carlo":
        if sigma is None:
            raise ValueError("sigma es requerido para method='monte_carlo'")
        rng = np.random.default_rng(seed)
        h = horizon_days
        sims = rng.normal(mu * h, sigma * math.sqrt(h), size=n_simulations)
        var_pct = -np.percentile(sims, (1 - confidence) * 100)
        var_value = var_pct * portfolio_value
        return {
            "mode": "value_at_risk", "method": method, "confidence": confidence,
            "var_pct": round(float(var_pct), 6), "var_value": round(float(var_value), 2),
            "n_simulations": n_simulations,
        }
    else:
        raise ValueError(f"method desconocido: {method}")


def compute_annuity_valuation(kind, payment=None, rate=None, n_periods=None,
                               growth_rate=0.0, due=False):
    if kind == "present_value":
        pv = payment * (1 - (1 + rate) ** -n_periods) / rate
        if due:
            pv *= (1 + rate)
        return {"mode": "annuity_valuation", "kind": kind, "present_value": round(pv, 6)}
    elif kind == "future_value":
        fv = payment * (((1 + rate) ** n_periods - 1) / rate)
        if due:
            fv *= (1 + rate)
        return {"mode": "annuity_valuation", "kind": kind, "future_value": round(fv, 6)}
    elif kind == "perpetuity":
        pv = payment / rate
        return {"mode": "annuity_valuation", "kind": kind, "present_value": round(pv, 6)}
    elif kind == "growing_perpetuity":
        if rate <= growth_rate:
            raise ValueError("rate debe ser mayor que growth_rate para que la perpetuidad converja")
        pv = payment / (rate - growth_rate)
        return {"mode": "annuity_valuation", "kind": kind, "present_value": round(pv, 6)}
    else:
        raise ValueError(f"kind desconocido: {kind}")


def compute_bond_pricing(face_value=1000.0, coupon_rate=None, periods_per_year=2,
                          n_periods=None, ytm=None, market_price=None):
    coupon = face_value * coupon_rate / periods_per_year if coupon_rate is not None else 0.0

    def price_from_ytm(y):
        per_rate = y / periods_per_year
        cfs = [coupon] * n_periods
        cfs[-1] += face_value
        return sum(cf / (1 + per_rate) ** t for t, cf in enumerate(cfs, start=1))

    result = {"mode": "bond_pricing"}

    if ytm is not None and market_price is None:
        price = price_from_ytm(ytm)
        result["price"] = round(price, 6)
        result["ytm"] = ytm
    elif market_price is not None:
        f = lambda y: price_from_ytm(y) - market_price
        try:
            solved_ytm = brentq(f, -0.99, 5.0)
        except ValueError:
            raise ValueError("no se pudo resolver YTM en el rango de busqueda (-99%, 500%)")
        result["price"] = round(market_price, 6)
        result["ytm"] = round(solved_ytm, 6)
        ytm = solved_ytm
    else:
        raise ValueError("se requiere ytm o market_price")

    per_rate = ytm / periods_per_year
    cfs = [coupon] * n_periods
    cfs[-1] += face_value
    price = sum(cf / (1 + per_rate) ** t for t, cf in enumerate(cfs, start=1))
    mac_duration_periods = sum(
        t * cf / (1 + per_rate) ** t for t, cf in enumerate(cfs, start=1)
    ) / price
    mac_duration_years = mac_duration_periods / periods_per_year
    mod_duration = mac_duration_years / (1 + per_rate)
    convexity = sum(
        t * (t + 1) * cf / (1 + per_rate) ** (t + 2) for t, cf in enumerate(cfs, start=1)
    ) / (price * periods_per_year ** 2)

    result["macaulay_duration_years"] = round(mac_duration_years, 6)
    result["modified_duration"] = round(mod_duration, 6)
    result["convexity"] = round(convexity, 6)
    return result


def compute_catastrophe_risk(confidence=0.95, portfolio_value=1.0, horizon_years=1,
                              catastrophe_frequency=0.1, severity_mean=0.15, severity_std=0.10,
                              climate_stress_factor=1.0, base_sigma=None, base_mu=0.0,
                              n_simulations=100000, seed=None):
    """
    VaR ajustado por riesgo de catastrofe climatica/ambiental via proceso de
    Poisson compuesto. Simula perdidas anuales combinando:
      - perdidas catastroficas: N ~ Poisson(catastrophe_frequency * climate_stress_factor
        * horizon_years) eventos, cada uno con severidad ~ Lognormal(severity_mean,
        severity_std) como fraccion del portfolio.
      - opcionalmente, perdida de mercado 'base' ~ Normal(base_mu, base_sigma) si se pasa
        base_sigma (para combinar riesgo financiero tradicional + riesgo de catastrofe).
    climate_stress_factor > 1 simula escenarios de intensificacion climatica futura
    (mayor frecuencia de eventos extremos que la base historica).
    Reporta VaR y TVaR (Expected Shortfall, promedio de perdidas mas alla del VaR) -
    el TVaR es la metrica relevante para colas gordas de catastrofe, donde el VaR
    parametrico normal subestima sistematicamente la magnitud de perdidas extremas.
    """
    rng = np.random.default_rng(seed)
    lam = catastrophe_frequency * climate_stress_factor * horizon_years

    sev_var = severity_std ** 2
    sigma_ln = math.sqrt(math.log(1 + sev_var / severity_mean ** 2))
    mu_ln = math.log(severity_mean) - 0.5 * sigma_ln ** 2

    n_events = rng.poisson(lam, size=n_simulations)
    total_cat_loss_pct = np.zeros(n_simulations)
    max_events = int(n_events.max()) if n_simulations > 0 else 0
    if max_events > 0:
        severities = rng.lognormal(mu_ln, sigma_ln, size=(n_simulations, max_events))
        mask = np.arange(max_events)[None, :] < n_events[:, None]
        total_cat_loss_pct = (severities * mask).sum(axis=1)

    if base_sigma is not None:
        base_loss_pct = -rng.normal(base_mu * horizon_years, base_sigma * math.sqrt(horizon_years), size=n_simulations)
    else:
        base_loss_pct = np.zeros(n_simulations)

    total_loss_pct = total_cat_loss_pct + base_loss_pct
    total_loss_value = total_loss_pct * portfolio_value

    var_pct = np.percentile(total_loss_pct, confidence * 100)
    var_value = var_pct * portfolio_value

    tail = total_loss_value[total_loss_value >= var_value]
    tvar_value = float(tail.mean()) if tail.size > 0 else float(var_value)
    tvar_pct = tvar_value / portfolio_value if portfolio_value else 0.0

    expected_annual_loss_value = float(total_loss_value.mean())
    prob_any_catastrophe = float((n_events > 0).mean())

    return {
        "mode": "catastrophe_risk",
        "confidence": confidence,
        "horizon_years": horizon_years,
        "catastrophe_frequency_input": catastrophe_frequency,
        "climate_stress_factor": climate_stress_factor,
        "effective_annual_event_rate": catastrophe_frequency * climate_stress_factor,
        "expected_annual_loss_pct": round(float(total_cat_loss_pct.mean()), 6),
        "expected_annual_loss_value": round(expected_annual_loss_value, 2),
        "var_pct": round(float(var_pct), 6),
        "var_value": round(float(var_value), 2),
        "tvar_pct": round(float(tvar_pct), 6),
        "tvar_value": round(tvar_value, 2),
        "probability_at_least_one_catastrophe": round(prob_any_catastrophe, 6),
        "n_simulations": n_simulations,
    }


def compute_financial_math(mode, **kwargs):
    """Dispatcher unico para el tool MCP financial_math, segun 'mode'."""
    fns = {
        "black_scholes": compute_black_scholes,
        "option_greeks": compute_option_greeks,
        "value_at_risk": compute_value_at_risk,
        "annuity_valuation": compute_annuity_valuation,
        "bond_pricing": compute_bond_pricing,
        "catastrophe_risk": compute_catastrophe_risk,
    }
    if mode not in fns:
        raise ValueError(f"mode desconocido: {mode}")
    return fns[mode](**kwargs)


FINANCIAL_MATH_TOOL_SCHEMA = {
    "name": "financial_math",
    "description": "Matematica financiera: Black-Scholes, griegas de opciones, Value at Risk (parametrico/historico/Monte Carlo), anualidades/perpetuidades, bonos (precio/YTM/duracion/convexidad), y riesgo de catastrofe climatica/ambiental (VaR y TVaR via Poisson compuesto).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["black_scholes", "option_greeks", "value_at_risk", "annuity_valuation", "bond_pricing", "catastrophe_risk"]},
            "S": {"type": "number"}, "K": {"type": "number"}, "T": {"type": "number"},
            "r": {"type": "number"}, "sigma": {"type": "number"}, "q": {"type": "number"},
            "option_type": {"type": "string", "enum": ["call", "put"]},
            "method": {"type": "string", "enum": ["parametric", "historical", "monte_carlo"]},
            "confidence": {"type": "number"}, "portfolio_value": {"type": "number"},
            "mu": {"type": "number"}, "returns": {"type": "array", "items": {"type": "number"}},
            "horizon_days": {"type": "integer"}, "n_simulations": {"type": "integer"}, "seed": {"type": "integer"},
            "kind": {"type": "string", "enum": ["present_value", "future_value", "perpetuity", "growing_perpetuity"]},
            "payment": {"type": "number"}, "rate": {"type": "number"}, "n_periods": {"type": "integer"},
            "growth_rate": {"type": "number"}, "due": {"type": "boolean"},
            "face_value": {"type": "number"}, "coupon_rate": {"type": "number"},
            "periods_per_year": {"type": "integer"}, "ytm": {"type": "number"}, "market_price": {"type": "number"},
            "horizon_years": {"type": "number"}, "catastrophe_frequency": {"type": "number"},
            "severity_mean": {"type": "number"}, "severity_std": {"type": "number"},
            "climate_stress_factor": {"type": "number"}, "base_sigma": {"type": "number"}, "base_mu": {"type": "number"},
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    print(compute_financial_math(mode="black_scholes", S=100, K=100, T=1, r=0.05, sigma=0.2, option_type="call"))
    print(compute_financial_math(mode="option_greeks", S=100, K=100, T=1, r=0.05, sigma=0.2, option_type="call"))
    print(compute_financial_math(mode="value_at_risk", method="parametric", confidence=0.95, portfolio_value=1000000, mu=0.0005, sigma=0.02, horizon_days=1))
    print(compute_financial_math(mode="annuity_valuation", kind="present_value", payment=1000, rate=0.05, n_periods=10))
    print(compute_financial_math(mode="bond_pricing", face_value=1000, coupon_rate=0.06, periods_per_year=2, n_periods=20, market_price=980))
    print(compute_financial_math(mode="catastrophe_risk", portfolio_value=1000000, confidence=0.95, catastrophe_frequency=0.2, severity_mean=0.15, severity_std=0.10, climate_stress_factor=1.5, base_sigma=0.15, seed=42))
