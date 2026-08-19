#!/usr/bin/env python3
"""
financial_math_tool.py

Matematica financiera: valuacion de opciones (Black-Scholes + griegas),
Value at Risk (parametrico, historico, Monte Carlo), valuacion de
anualidades/perpetuidades, y bonos (precio, YTM, duracion, convexidad).

Pensado para economia/finanzas a nivel de curso universitario o analisis
aplicado real (no solo docencia).

Usa scipy.stats para la normal estandar en Black-Scholes/VaR parametrico,
numpy para VaR historico/Monte Carlo y flujos de bonos, y una
raiz de Newton simple (sin dependencias extra) para YTM.

Corre standalone: python3 financial_math_tool.py
"""
import json
import math

import numpy as np
from scipy.stats import norm

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _round(x, nd=6):
    if isinstance(x, (int, float, np.floating, np.integer)):
        return round(float(x), nd)
    return x


# ---------------------------------------------------------------------------
# Black-Scholes + griegas
# ---------------------------------------------------------------------------

def _bs_d1_d2(S, K, T, r, sigma, q=0.0):
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def compute_black_scholes(S, K, T, r, sigma, option_type="call", q=0.0):
    """Precio Black-Scholes-Merton (con dividend yield continuo q opcional)."""
    d1, d2 = _bs_d1_d2(S, K, T, r, sigma, q)
    if option_type == "call":
        price = S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    elif option_type == "put":
        price = K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)
    else:
        raise ValueError("option_type debe ser 'call' o 'put'")

    return {
        "mode": "black_scholes",
        "option_type": option_type,
        "inputs": {"S": S, "K": K, "T": T, "r": r, "sigma": sigma, "q": q},
        "d1": _round(d1),
        "d2": _round(d2),
        "price": _round(price),
    }


def compute_option_greeks(S, K, T, r, sigma, option_type="call", q=0.0):
    """Delta, gamma, vega, theta (por dia), rho."""
    d1, d2 = _bs_d1_d2(S, K, T, r, sigma, q)
    pdf_d1 = norm.pdf(d1)

    gamma = math.exp(-q * T) * pdf_d1 / (S * sigma * math.sqrt(T))
    vega = S * math.exp(-q * T) * pdf_d1 * math.sqrt(T) / 100.0  # por 1% de sigma

    if option_type == "call":
        delta = math.exp(-q * T) * norm.cdf(d1)
        theta_annual = (
            -S * math.exp(-q * T) * pdf_d1 * sigma / (2 * math.sqrt(T))
            - r * K * math.exp(-r * T) * norm.cdf(d2)
            + q * S * math.exp(-q * T) * norm.cdf(d1)
        )
        rho = K * T * math.exp(-r * T) * norm.cdf(d2) / 100.0  # por 1% de r
    elif option_type == "put":
        delta = -math.exp(-q * T) * norm.cdf(-d1)
        theta_annual = (
            -S * math.exp(-q * T) * pdf_d1 * sigma / (2 * math.sqrt(T))
            + r * K * math.exp(-r * T) * norm.cdf(-d2)
            - q * S * math.exp(-q * T) * norm.cdf(-d1)
        )
        rho = -K * T * math.exp(-r * T) * norm.cdf(-d2) / 100.0
    else:
        raise ValueError("option_type debe ser 'call' o 'put'")

    return {
        "mode": "option_greeks",
        "option_type": option_type,
        "inputs": {"S": S, "K": K, "T": T, "r": r, "sigma": sigma, "q": q},
        "delta": _round(delta),
        "gamma": _round(gamma),
        "vega_per_1pct_vol": _round(vega),
        "theta_per_day": _round(theta_annual / 365.0),
        "rho_per_1pct_rate": _round(rho),
    }


# ---------------------------------------------------------------------------
# Value at Risk
# ---------------------------------------------------------------------------

def compute_value_at_risk(method, confidence=0.95, portfolio_value=1_000_000.0,
                           mu=0.0, sigma=None, returns=None, horizon_days=1,
                           n_simulations=100_000, seed=42):
    """
    method: 'parametric' | 'historical' | 'monte_carlo'
    - parametric: usa mu/sigma (retornos diarios) y la normal estandar
    - historical: usa una serie 'returns' (lista de retornos historicos)
    - monte_carlo: simula retornos ~ N(mu, sigma) 'n_simulations' veces
    VaR se reporta como perdida positiva (monto en $ del portfolio).
    """
    z = norm.ppf(1 - confidence)  # z negativo, ej. -1.645 para 95%
    horizon_scale = math.sqrt(horizon_days)

    if method == "parametric":
        if sigma is None:
            raise ValueError("parametric requiere sigma (desviacion estandar diaria)")
        mu_h = mu * horizon_days
        sigma_h = sigma * horizon_scale
        var_pct = -(mu_h + z * sigma_h)
        var_amount = var_pct * portfolio_value
        result = {
            "mode": "value_at_risk",
            "method": "parametric",
            "confidence": confidence,
            "z_score": _round(z),
            "var_pct": _round(var_pct),
            "var_amount": _round(var_amount),
        }

    elif method == "historical":
        if not returns:
            raise ValueError("historical requiere la lista 'returns'")
        arr = np.array(returns, dtype=float)
        var_pct = -np.percentile(arr, (1 - confidence) * 100)
        var_amount = var_pct * portfolio_value
        result = {
            "mode": "value_at_risk",
            "method": "historical",
            "confidence": confidence,
            "n_observations": len(arr),
            "var_pct": _round(var_pct),
            "var_amount": _round(var_amount),
        }

    elif method == "monte_carlo":
        if sigma is None:
            raise ValueError("monte_carlo requiere sigma (desviacion estandar diaria)")
        rng = np.random.default_rng(seed)
        sim_returns = rng.normal(mu * horizon_days, sigma * horizon_scale, n_simulations)
        var_pct = -np.percentile(sim_returns, (1 - confidence) * 100)
        var_amount = var_pct * portfolio_value
        # Expected Shortfall (CVaR) de regalo, muy usado junto al VaR
        cutoff = np.percentile(sim_returns, (1 - confidence) * 100)
        es_pct = -sim_returns[sim_returns <= cutoff].mean()
        result = {
            "mode": "value_at_risk",
            "method": "monte_carlo",
            "confidence": confidence,
            "n_simulations": n_simulations,
            "var_pct": _round(var_pct),
            "var_amount": _round(var_amount),
            "expected_shortfall_pct": _round(es_pct),
            "expected_shortfall_amount": _round(es_pct * portfolio_value),
        }
    else:
        raise ValueError("method debe ser 'parametric', 'historical' o 'monte_carlo'")

    result["portfolio_value"] = portfolio_value
    result["horizon_days"] = horizon_days
    return result


# ---------------------------------------------------------------------------
# Anualidades / perpetuidades
# ---------------------------------------------------------------------------

def compute_annuity_valuation(kind, payment, rate, n_periods=None, growth_rate=0.0,
                               due=False):
    """
    kind: 'present_value' | 'future_value' | 'perpetuity' | 'growing_perpetuity'
    rate, growth_rate: tasa por periodo (no anualizada si los periodos no son anuales)
    due=True -> anualidad anticipada (pagos al inicio del periodo)
    """
    if kind == "present_value":
        if n_periods is None:
            raise ValueError("present_value requiere n_periods")
        if abs(rate - growth_rate) < 1e-12:
            pv = payment * n_periods / (1 + rate)
        else:
            g, r = growth_rate, rate
            pv = payment * (1 - ((1 + g) / (1 + r)) ** n_periods) / (r - g)
        if due:
            pv *= (1 + rate)
        result = {"mode": "annuity_valuation", "kind": "present_value",
                  "present_value": _round(pv)}

    elif kind == "future_value":
        if n_periods is None:
            raise ValueError("future_value requiere n_periods")
        if growth_rate != 0.0:
            raise ValueError("future_value con crecimiento no esta soportado; use present_value y capitalice aparte")
        if rate == 0:
            fv = payment * n_periods
        else:
            fv = payment * (((1 + rate) ** n_periods - 1) / rate)
        if due:
            fv *= (1 + rate)
        result = {"mode": "annuity_valuation", "kind": "future_value",
                  "future_value": _round(fv)}

    elif kind == "perpetuity":
        if rate <= 0:
            raise ValueError("perpetuity requiere rate > 0")
        pv = payment / rate
        if due:
            pv *= (1 + rate)
        result = {"mode": "annuity_valuation", "kind": "perpetuity",
                  "present_value": _round(pv)}

    elif kind == "growing_perpetuity":
        if rate <= growth_rate:
            raise ValueError("growing_perpetuity requiere rate > growth_rate")
        pv = payment / (rate - growth_rate)
        if due:
            pv *= (1 + rate)
        result = {"mode": "annuity_valuation", "kind": "growing_perpetuity",
                  "present_value": _round(pv)}
    else:
        raise ValueError("kind no reconocido")

    result["inputs"] = {"payment": payment, "rate": rate, "n_periods": n_periods,
                         "growth_rate": growth_rate, "due": due}
    return result


# ---------------------------------------------------------------------------
# Bonos: precio, YTM (Newton), duracion, convexidad
# ---------------------------------------------------------------------------

def _bond_price(face_value, coupon_rate, ytm, n_periods, periods_per_year=1):
    c = face_value * coupon_rate / periods_per_year
    y = ytm / periods_per_year
    price = 0.0
    for t in range(1, n_periods + 1):
        cf = c + (face_value if t == n_periods else 0.0)
        price += cf / (1 + y) ** t
    return price


def compute_bond_pricing(mode, face_value=1000.0, coupon_rate=0.05, n_periods=10,
                          periods_per_year=1, ytm=None, market_price=None):
    """
    mode: 'price' (dado ytm) | 'ytm' (dado market_price, via Newton-Raphson)
    Tambien devuelve duracion de Macaulay, duracion modificada y convexidad
    evaluadas en el ytm resultante/dado.
    """
    if mode == "price":
        if ytm is None:
            raise ValueError("mode='price' requiere ytm")
        price = _bond_price(face_value, coupon_rate, ytm, n_periods, periods_per_year)
    elif mode == "ytm":
        if market_price is None:
            raise ValueError("mode='ytm' requiere market_price")
        # Newton-Raphson simple partiendo de coupon_rate como semilla
        y = coupon_rate if coupon_rate > 0 else 0.05
        for _ in range(200):
            f = _bond_price(face_value, coupon_rate, y, n_periods, periods_per_year) - market_price
            eps = 1e-6
            f_prime = (
                _bond_price(face_value, coupon_rate, y + eps, n_periods, periods_per_year)
                - _bond_price(face_value, coupon_rate, y - eps, n_periods, periods_per_year)
            ) / (2 * eps)
            if abs(f_prime) < 1e-12:
                break
            y_new = y - f / f_prime
            if abs(y_new - y) < 1e-10:
                y = y_new
                break
            y = y_new
        ytm = y
        price = _bond_price(face_value, coupon_rate, ytm, n_periods, periods_per_year)
    else:
        raise ValueError("mode debe ser 'price' o 'ytm'")

    # Duracion de Macaulay y convexidad (numerica, en periodos -> se anualiza)
    c = face_value * coupon_rate / periods_per_year
    y = ytm / periods_per_year
    weighted_t = 0.0
    convexity_sum = 0.0
    for t in range(1, n_periods + 1):
        cf = c + (face_value if t == n_periods else 0.0)
        pv_cf = cf / (1 + y) ** t
        weighted_t += t * pv_cf
        convexity_sum += t * (t + 1) * pv_cf / (1 + y) ** 2

    macaulay_duration_periods = weighted_t / price
    macaulay_duration_years = macaulay_duration_periods / periods_per_year
    modified_duration = macaulay_duration_years / (1 + y)
    convexity = convexity_sum / price / (periods_per_year ** 2)

    return {
        "mode": "bond_pricing",
        "sub_mode": mode,
        "inputs": {"face_value": face_value, "coupon_rate": coupon_rate,
                   "n_periods": n_periods, "periods_per_year": periods_per_year},
        "ytm": _round(ytm),
        "price": _round(price),
        "macaulay_duration_years": _round(macaulay_duration_years),
        "modified_duration": _round(modified_duration),
        "convexity": _round(convexity),
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    print("=== black_scholes (call ATM-ish, ejemplo de texto clasico) ===")
    r1 = compute_black_scholes(S=100, K=100, T=1, r=0.05, sigma=0.2, option_type="call")
    print(json.dumps(r1, indent=2))
    print("Esperado: precio ~10.45 (Black-Scholes call clasico S=K=100, r=5%, sigma=20%, T=1)\n")

    print("=== option_greeks (mismo call) ===")
    r2 = compute_option_greeks(S=100, K=100, T=1, r=0.05, sigma=0.2, option_type="call")
    print(json.dumps(r2, indent=2))
    print("Esperado: delta ~0.6368, gamma ~0.0188, theta negativo (decaimiento temporal)\n")

    print("=== black_scholes put (put-call parity check) ===")
    r_put = compute_black_scholes(S=100, K=100, T=1, r=0.05, sigma=0.2, option_type="put")
    call_price = r1["price"]
    put_price = r_put["price"]
    parity_lhs = call_price - put_price
    parity_rhs = 100 - 100 * math.exp(-0.05 * 1)
    print(f"call - put = {parity_lhs:.6f} | S - K*e^(-rT) = {parity_rhs:.6f}")
    print(f"Paridad put-call {'OK' if abs(parity_lhs - parity_rhs) < 1e-6 else 'FALLA'}\n")

    print("=== value_at_risk parametric (portfolio $1M, mu=0, sigma=1.5% diario, 95%) ===")
    r3 = compute_value_at_risk("parametric", confidence=0.95, portfolio_value=1_000_000,
                                mu=0.0, sigma=0.015)
    print(json.dumps(r3, indent=2))
    print("Esperado: VaR ~ 1.645 * 1.5% * $1M ~= $24,675\n")

    print("=== value_at_risk historical (retornos sinteticos) ===")
    rng = np.random.default_rng(0)
    synthetic_returns = rng.normal(0.0005, 0.012, 500).tolist()
    r4 = compute_value_at_risk("historical", confidence=0.95, portfolio_value=1_000_000,
                                returns=synthetic_returns)
    print(json.dumps(r4, indent=2))
    print("Esperado: VaR cercano al parametrico dado que los retornos son normales\n")

    print("=== value_at_risk monte_carlo (con Expected Shortfall) ===")
    r5 = compute_value_at_risk("monte_carlo", confidence=0.99, portfolio_value=1_000_000,
                                mu=0.0, sigma=0.015, n_simulations=200_000)
    print(json.dumps(r5, indent=2))
    print("Esperado: VaR_99% ~ 2.326 * 1.5% * $1M ~= $34,900, ES algo mayor al VaR\n")

    print("=== annuity_valuation: present_value (anualidad ordinaria) ===")
    r6 = compute_annuity_valuation("present_value", payment=1000, rate=0.05, n_periods=10)
    print(json.dumps(r6, indent=2))
    print("Esperado: PV ~ $7,721.73 (anualidad ordinaria, 1000/periodo, 5%, 10 periodos)\n")

    print("=== annuity_valuation: present_value anticipada (due=True) ===")
    r7 = compute_annuity_valuation("present_value", payment=1000, rate=0.05, n_periods=10, due=True)
    print(json.dumps(r7, indent=2))
    print("Esperado: PV ~ $8,107.82 (= PV ordinaria * 1.05)\n")

    print("=== annuity_valuation: future_value ===")
    r8 = compute_annuity_valuation("future_value", payment=1000, rate=0.05, n_periods=10)
    print(json.dumps(r8, indent=2))
    print("Esperado: FV ~ $12,577.89\n")

    print("=== annuity_valuation: perpetuity ===")
    r9 = compute_annuity_valuation("perpetuity", payment=1000, rate=0.05, n_periods=None)
    print(json.dumps(r9, indent=2))
    print("Esperado: PV = 1000/0.05 = $20,000\n")

    print("=== annuity_valuation: growing_perpetuity (modelo de Gordon) ===")
    r10 = compute_annuity_valuation("growing_perpetuity", payment=100, rate=0.08,
                                     n_periods=None, growth_rate=0.03)
    print(json.dumps(r10, indent=2))
    print("Esperado: PV = 100/(0.08-0.03) = $2,000 (Gordon Growth Model)\n")

    print("=== bond_pricing: price (bono a la par -> precio = face_value) ===")
    r11 = compute_bond_pricing("price", face_value=1000, coupon_rate=0.06, n_periods=10,
                                periods_per_year=1, ytm=0.06)
    print(json.dumps(r11, indent=2))
    print("Esperado: price = 1000.0 exacto (cupon = ytm -> bono a la par)\n")

    print("=== bond_pricing: price (bono con descuento, ytm > cupon) ===")
    r12 = compute_bond_pricing("price", face_value=1000, coupon_rate=0.05, n_periods=10,
                                periods_per_year=1, ytm=0.07)
    print(json.dumps(r12, indent=2))
    print("Esperado: price < 1000 (bono con descuento, ~858.65)\n")

    print("=== bond_pricing: ytm (recuperar el 7% desde el precio calculado arriba) ===")
    r13 = compute_bond_pricing("ytm", face_value=1000, coupon_rate=0.05, n_periods=10,
                                periods_per_year=1, market_price=r12["price"])
    print(json.dumps(r13, indent=2))
    print(f"Esperado: ytm recuperado ~= 0.07 (Newton-Raphson debe converger de vuelta)\n")

    checks_ok = (
        abs(r1["price"] - 10.4506) < 1e-3
        and abs(parity_lhs - parity_rhs) < 1e-6
        and abs(r6["present_value"] - 7721.73) < 1
        and abs(r9["present_value"] - 20000.0) < 1e-6
        and abs(r10["present_value"] - 2000.0) < 1e-6
        and abs(r11["price"] - 1000.0) < 1e-6
        and abs(r13["ytm"] - 0.07) < 1e-4
    )
    print("OK - todos los modos corrieron y los checks numericos pasaron."
          if checks_ok else "ADVERTENCIA - algun check numerico no coincidio, revisar arriba.")

# ---------------------------------------------------------------------------
# Dispatcher unificado por 'mode' (agregado para wiring con server.py)
# ---------------------------------------------------------------------------

def _validate_financial_math() -> dict:
    """Reusa los checks numericos del __main__ (checks_ok), contra valores de
    referencia de libro de texto conocidos: Black-Scholes call ATM clasico
    (S=K=100,r=5%,sigma=20%,T=1) precio~=10.4506; paridad put-call exacta;
    anualidad ordinaria PV~=7721.73; perpetuidad PV=pago/tasa exacto (20000);
    perpetuidad creciente = Gordon Growth Model exacto (2000); bono a la par
    (cupon==ytm) precio==face_value exacto (1000); YTM recuperado por Newton-
    Raphson desde el precio de un bono con descuento debe converger de vuelta
    al 7% usado para generarlo."""
    checks = []

    r1 = compute_black_scholes(S=100, K=100, T=1, r=0.05, sigma=0.2, option_type="call")
    checks.append({"name": "black_scholes call ATM ~= 10.4506",
                    "passed": abs(r1["price"] - 10.4506) < 1e-3, "got": r1["price"]})

    r_put = compute_black_scholes(S=100, K=100, T=1, r=0.05, sigma=0.2, option_type="put")
    parity_lhs = r1["price"] - r_put["price"]
    parity_rhs = 100 - 100 * math.exp(-0.05 * 1)
    checks.append({"name": "paridad put-call: call-put == S-K*e^(-rT)",
                    "passed": abs(parity_lhs - parity_rhs) < 1e-6,
                    "got": {"lhs": parity_lhs, "rhs": parity_rhs}})

    r6 = compute_annuity_valuation("present_value", payment=1000, rate=0.05, n_periods=10)
    checks.append({"name": "anualidad ordinaria PV ~= 7721.73",
                    "passed": abs(r6["present_value"] - 7721.73) < 1, "got": r6["present_value"]})

    r9 = compute_annuity_valuation("perpetuity", payment=1000, rate=0.05)
    checks.append({"name": "perpetuidad PV == pago/tasa == 20000 exacto",
                    "passed": abs(r9["present_value"] - 20000.0) < 1e-6, "got": r9["present_value"]})

    r10 = compute_annuity_valuation("growing_perpetuity", payment=100, rate=0.08, growth_rate=0.03)
    checks.append({"name": "Gordon Growth Model PV == 100/(0.08-0.03) == 2000 exacto",
                    "passed": abs(r10["present_value"] - 2000.0) < 1e-6, "got": r10["present_value"]})

    r11 = compute_bond_pricing("price", face_value=1000, coupon_rate=0.06, n_periods=10,
                                periods_per_year=1, ytm=0.06)
    checks.append({"name": "bono a la par (cupon==ytm): precio == face_value == 1000 exacto",
                    "passed": abs(r11["price"] - 1000.0) < 1e-6, "got": r11["price"]})

    r12 = compute_bond_pricing("price", face_value=1000, coupon_rate=0.05, n_periods=10,
                                periods_per_year=1, ytm=0.07)
    r13 = compute_bond_pricing("ytm", face_value=1000, coupon_rate=0.05, n_periods=10,
                                periods_per_year=1, market_price=r12["price"])
    checks.append({"name": "Newton-Raphson YTM recupera el 7% usado para generar el precio",
                    "passed": abs(r13["ytm"] - 0.07) < 1e-4, "got": r13["ytm"]})

    return {
        "mode": "validate",
        "validation_passed": all(c["passed"] for c in checks),
        "checks": checks,
        "not_covered": [
            "value_at_risk (parametric/historical/monte_carlo): sin valor analitico exacto de referencia, es estadistico por naturaleza",
        ],
    }


def compute_financial_math(mode, params=None, **kwargs):
    """
    Dispatcher unico para financial_math_tool. mode:
      'black_scholes'      -> compute_black_scholes(S,K,T,r,sigma,option_type,q)
      'option_greeks'      -> compute_option_greeks(S,K,T,r,sigma,option_type,q)
      'value_at_risk'      -> compute_value_at_risk(method,confidence,portfolio_value,
                               mu,sigma,returns,horizon_days,n_simulations,seed)
      'annuity_valuation'  -> compute_annuity_valuation(kind,payment,rate,n_periods,
                               growth_rate,due)
      'bond_pricing'       -> compute_bond_pricing(mode,face_value,coupon_rate,
                               n_periods,periods_per_year,ytm,market_price)

    Acepta los parametros de cada sub-modo tanto en un dict 'params' anidado
    como en kwargs planos (para compatibilidad con distintas convenciones de
    llamada del dispatch en server.py).
    """
    p = dict(params) if params else {}
    p.update(kwargs)

    if mode == "validate":
        return _validate_financial_math()
    if mode == "black_scholes":
        return compute_black_scholes(**p)
    elif mode == "option_greeks":
        return compute_option_greeks(**p)
    elif mode == "value_at_risk":
        return compute_value_at_risk(**p)
    elif mode == "annuity_valuation":
        return compute_annuity_valuation(**p)
    elif mode == "bond_pricing":
        # bond_pricing usa su propio parametro interno 'mode' ('price'/'ytm').
        # Aca 'mode' externo ya vale 'bond_pricing', asi que el sub-modo debe
        # venir como 'sub_mode' en params/kwargs y se remapea a 'mode' interno.
        if "sub_mode" not in p:
            raise ValueError("bond_pricing requiere 'sub_mode' ('price' o 'ytm')")
        p["mode"] = p.pop("sub_mode")
        return compute_bond_pricing(**p)
    else:
        raise ValueError(
            "mode debe ser uno de: 'black_scholes', 'option_greeks', "
            "'value_at_risk', 'annuity_valuation', 'bond_pricing'"
        )


FINANCIAL_MATH_TOOL_SCHEMA = {
    "name": "financial_math",
    "description": (
        "Matematica financiera: valuacion de opciones Black-Scholes con griegas "
        "completas (black_scholes, option_greeks), Value at Risk parametrico/"
        "historico/Monte Carlo con Expected Shortfall (value_at_risk), valuacion "
        "de anualidades y perpetuidades con o sin crecimiento (annuity_valuation), "
        "y bonos: precio dado YTM o YTM dado precio de mercado via Newton-Raphson, "
        "mas duracion de Macaulay/modificada y convexidad (bond_pricing)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "black_scholes", "option_greeks", "value_at_risk",
                    "annuity_valuation", "bond_pricing", "validate",
                ],
            },
            "params": {
                "type": "object",
                "description": (
                    "Parametros especificos de cada modo:\n"
                    "black_scholes/option_greeks: S,K,T,r,sigma,option_type"
                    "('call'|'put'),q(opcional)\n"
                    "value_at_risk: method('parametric'|'historical'|'monte_carlo'),"
                    "confidence,portfolio_value,mu,sigma,returns(lista, solo "
                    "historical),horizon_days,n_simulations,seed\n"
                    "annuity_valuation: kind('present_value'|'future_value'|"
                    "'perpetuity'|'growing_perpetuity'),payment,rate,n_periods,"
                    "growth_rate,due(bool)\n"
                    "bond_pricing: sub_mode('price'|'ytm'),face_value,coupon_rate,"
                    "n_periods,periods_per_year,ytm(si sub_mode='price'),"
                    "market_price(si sub_mode='ytm')"
                ),
            },
        },
        "required": ["mode"],
    },
}

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("financial_math", FINANCIAL_MATH_TOOL_SCHEMA, lambda args, _f=compute_financial_math: _f(**args))
