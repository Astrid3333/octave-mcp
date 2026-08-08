

def compute_financial_math(mode, **kwargs):
    """Dispatcher unico para el tool MCP financial_math, segun 'mode'."""
    fns = {
        "black_scholes": compute_black_scholes,
        "option_greeks": compute_option_greeks,
        "value_at_risk": compute_value_at_risk,
        "annuity_valuation": compute_annuity_valuation,
        "bond_pricing": compute_bond_pricing,
    }
    if mode not in fns:
        raise ValueError(f"mode desconocido: {mode}")
    return fns[mode](**kwargs)


FINANCIAL_MATH_TOOL_SCHEMA = {
    "name": "financial_math",
    "description": "Matematica financiera: Black-Scholes, griegas de opciones, Value at Risk (parametrico/historico/Monte Carlo), anualidades/perpetuidades, y bonos (precio/YTM/duracion/convexidad).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["black_scholes", "option_greeks", "value_at_risk", "annuity_valuation", "bond_pricing"]},
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
        },
        "required": ["mode"],
    },
}
