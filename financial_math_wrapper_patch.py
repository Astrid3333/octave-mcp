
# ---------------------------------------------------------------------------
# Dispatcher unificado por 'mode' (agregado para wiring con server.py)
# ---------------------------------------------------------------------------

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
                    "annuity_valuation", "bond_pricing",
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
