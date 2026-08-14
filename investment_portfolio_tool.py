"""
investment_portfolio_tool.py
Fase D / Tanda 4 (2 de 3): analisis de portafolio de inversion.
Autocontenido: sin imports cruzados a otros modulos del repo.
Schema con name/description/inputSchema desde el inicio.

Modos:
  - expected_return_variance: retorno esperado y volatilidad del portafolio,
    dado pesos, retornos/volatilidades por activo y matriz de correlacion
    (identidad -es decir, sin correlacion- si no se provee).
  - rebalancing_drift: pesos actuales vs objetivo, desvio (drift) por activo
    y montos de compra/venta para rebalancear.
  - risk_return_score: clasificacion cualitativa del portafolio segun su
    volatilidad esperada (conservador/moderado/agresivo).
  - diversification_score: indice de concentracion (Herfindahl-Hirschman)
    sobre los pesos, con banda cualitativa.
  - validate: suite de checks contra casos cerrados.
"""

import json
import math


INVESTMENT_PORTFOLIO_TOOL_SCHEMA = {
    "name": "investment_portfolio_tool",
    "description": (
        "Analisis de portafolio de inversion: expected_return_variance (retorno "
        "esperado y volatilidad del portafolio dado pesos, retornos/volatilidades "
        "por activo y matriz de correlacion opcional -identidad, sin correlacion, "
        "si se omite-), rebalancing_drift (pesos actuales vs objetivo, desvio por "
        "activo y montos de compra/venta para rebalancear), risk_return_score "
        "(clasificacion cualitativa conservador/moderado/agresivo segun "
        "volatilidad esperada), diversification_score (indice de concentracion "
        "Herfindahl-Hirschman sobre los pesos, banda concentrado/moderado/"
        "diversificado). confidence_flag 'alta' para la mecanica de varianza de "
        "portafolio (algebra lineal determinista); los retornos/volatilidades "
        "esperados por activo son un supuesto de quien llama, no una prediccion. "
        "No es asesoria financiera ni de inversion. validate corre 8 checks."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "expected_return_variance",
                    "rebalancing_drift",
                    "risk_return_score",
                    "diversification_score",
                    "validate",
                ],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


# ----------------------------------------------------------------------
# Modo 1: expected_return_variance
# ----------------------------------------------------------------------

def _mode_expected_return_variance(params: dict) -> dict:
    assets = params["assets"]  # lista de {name, weight, expected_return, volatility}
    correlation_matrix = params.get("correlation_matrix")  # lista de listas, opcional

    n = len(assets)
    weights = [float(a["weight"]) for a in assets]
    returns = [float(a["expected_return"]) for a in assets]
    vols = [float(a["volatility"]) for a in assets]

    if correlation_matrix is None:
        # sin matriz de correlacion: se asume identidad (activos no correlacionados)
        correlation_matrix = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]

    portfolio_return = sum(w * r for w, r in zip(weights, returns))

    portfolio_variance = 0.0
    for i in range(n):
        for j in range(n):
            cov_ij = correlation_matrix[i][j] * vols[i] * vols[j]
            portfolio_variance += weights[i] * weights[j] * cov_ij

    portfolio_stdev = math.sqrt(max(portfolio_variance, 0.0))

    return {
        "assets": [a["name"] for a in assets],
        "weights": weights,
        "portfolio_expected_return": round(portfolio_return, 6),
        "portfolio_variance": round(portfolio_variance, 8),
        "portfolio_stdev": round(portfolio_stdev, 6),
    }


# ----------------------------------------------------------------------
# Modo 2: rebalancing_drift
# ----------------------------------------------------------------------

def _mode_rebalancing_drift(params: dict) -> dict:
    holdings = params["holdings"]  # lista de {name, current_value, target_weight}

    total_value = sum(float(h["current_value"]) for h in holdings)

    results = []
    for h in holdings:
        name = h["name"]
        current_value = float(h["current_value"])
        target_weight = float(h["target_weight"])

        current_weight = current_value / total_value if total_value > 0 else 0.0
        target_value = total_value * target_weight
        drift = current_weight - target_weight
        trade_amount = target_value - current_value  # positivo = comprar, negativo = vender

        results.append({
            "name": name,
            "current_value": current_value,
            "current_weight": round(current_weight, 4),
            "target_weight": target_weight,
            "drift": round(drift, 4),
            "trade_amount": round(trade_amount, 2),
            "action": "comprar" if trade_amount > 0.01 else ("vender" if trade_amount < -0.01 else "mantener"),
        })

    return {
        "total_value": round(total_value, 2),
        "holdings": results,
    }


# ----------------------------------------------------------------------
# Modo 3: risk_return_score
# ----------------------------------------------------------------------

def _classify_risk_band(portfolio_stdev: float) -> str:
    if portfolio_stdev < 0.08:
        return "conservador"
    if portfolio_stdev < 0.15:
        return "moderado"
    if portfolio_stdev < 0.25:
        return "agresivo"
    return "muy_agresivo"


def _mode_risk_return_score(params: dict) -> dict:
    portfolio_stdev = float(params["portfolio_stdev"])
    portfolio_expected_return = float(params.get("portfolio_expected_return", 0.0))

    band = _classify_risk_band(portfolio_stdev)
    sharpe_proxy = None
    risk_free_rate = params.get("risk_free_rate")
    if risk_free_rate is not None and portfolio_stdev > 0:
        sharpe_proxy = round((portfolio_expected_return - float(risk_free_rate)) / portfolio_stdev, 4)

    return {
        "portfolio_stdev": portfolio_stdev,
        "portfolio_expected_return": portfolio_expected_return,
        "risk_band": band,
        "sharpe_proxy": sharpe_proxy,
    }


# ----------------------------------------------------------------------
# Modo 4: diversification_score
# ----------------------------------------------------------------------

def _classify_hhi_band(hhi: float) -> str:
    if hhi > 0.5:
        return "concentrado"
    if hhi > 0.25:
        return "moderado"
    return "diversificado"


def _mode_diversification_score(params: dict) -> dict:
    weights = [float(w) for w in params["weights"]]

    hhi = sum(w ** 2 for w in weights)
    n_effective = (1.0 / hhi) if hhi > 0 else 0.0
    band = _classify_hhi_band(hhi)

    return {
        "weights": weights,
        "herfindahl_hirschman_index": round(hhi, 4),
        "effective_number_of_positions": round(n_effective, 2),
        "band": band,
    }


# ----------------------------------------------------------------------
# Validacion
# ----------------------------------------------------------------------

def _mode_validate() -> dict:
    checks = []

    # 1) expected_return_variance: retorno esperado por promedio ponderado, exacto
    erv = _mode_expected_return_variance({
        "assets": [
            {"name": "Acciones", "weight": 0.6, "expected_return": 0.08, "volatility": 0.18},
            {"name": "Bonos", "weight": 0.4, "expected_return": 0.03, "volatility": 0.05},
        ],
    })
    expected_return = 0.6 * 0.08 + 0.4 * 0.03
    checks.append({
        "name": "expected_return_weighted_average_exact",
        "computed": erv["portfolio_expected_return"],
        "expected": round(expected_return, 6),
        "passed": abs(erv["portfolio_expected_return"] - expected_return) < 1e-6,
    })

    # 2) sin matriz de correlacion (identidad), la varianza debe matchear la
    #    formula manual sum(w_i^2 * vol_i^2) para activos no correlacionados
    expected_variance = (0.6 ** 2) * (0.18 ** 2) + (0.4 ** 2) * (0.05 ** 2)
    checks.append({
        "name": "variance_matches_manual_formula_when_uncorrelated",
        "computed": erv["portfolio_variance"],
        "expected": round(expected_variance, 8),
        "passed": abs(erv["portfolio_variance"] - expected_variance) < 1e-8,
    })

    # 3) con correlacion perfecta (+1) entre dos activos, la stdev del portafolio
    #    debe ser exactamente el promedio ponderado de las stdev individuales
    #    (caso limite conocido: no hay beneficio de diversificacion)
    erv_corr1 = _mode_expected_return_variance({
        "assets": [
            {"name": "A", "weight": 0.5, "expected_return": 0.05, "volatility": 0.10},
            {"name": "B", "weight": 0.5, "expected_return": 0.05, "volatility": 0.20},
        ],
        "correlation_matrix": [[1.0, 1.0], [1.0, 1.0]],
    })
    expected_stdev_corr1 = 0.5 * 0.10 + 0.5 * 0.20
    checks.append({
        "name": "perfect_correlation_gives_weighted_average_stdev",
        "computed": erv_corr1["portfolio_stdev"],
        "expected": round(expected_stdev_corr1, 6),
        "passed": abs(erv_corr1["portfolio_stdev"] - expected_stdev_corr1) < 1e-6,
    })

    # 4) rebalancing_drift: conservacion del valor total (nadie gana ni pierde plata al rebalancear)
    rd = _mode_rebalancing_drift({
        "holdings": [
            {"name": "Acciones", "current_value": 7000.0, "target_weight": 0.6},
            {"name": "Bonos", "current_value": 3000.0, "target_weight": 0.4},
        ],
    })
    sum_trades = sum(h["trade_amount"] for h in rd["holdings"])
    checks.append({
        "name": "rebalancing_trades_net_to_zero",
        "sum_trades": round(sum_trades, 2),
        "passed": abs(sum_trades) < 0.05,
    })

    # 5) rebalancing_drift: el activo sobreponderado debe marcarse para vender
    acciones = next(h for h in rd["holdings"] if h["name"] == "Acciones")
    checks.append({
        "name": "overweight_asset_flagged_to_sell",
        "current_weight": acciones["current_weight"],
        "target_weight": acciones["target_weight"],
        "action": acciones["action"],
        "passed": acciones["current_weight"] > acciones["target_weight"] and acciones["action"] == "vender",
    })

    # 6) risk_return_score: bandas monotonicas y distintas segun volatilidad
    bands = [_mode_risk_return_score({"portfolio_stdev": s})["risk_band"]
             for s in [0.03, 0.10, 0.20, 0.30]]
    checks.append({
        "name": "risk_bands_monotonic_and_distinct",
        "bands": bands,
        "passed": bands == ["conservador", "moderado", "agresivo", "muy_agresivo"],
    })

    # 7) diversification_score: portafolio 100% concentrado en un activo -> HHI=1.0
    ds_concentrated = _mode_diversification_score({"weights": [1.0]})
    checks.append({
        "name": "fully_concentrated_portfolio_has_hhi_one",
        "computed": ds_concentrated["herfindahl_hirschman_index"],
        "expected": 1.0,
        "band": ds_concentrated["band"],
        "passed": abs(ds_concentrated["herfindahl_hirschman_index"] - 1.0) < 1e-9 and ds_concentrated["band"] == "concentrado",
    })

    # 8) diversification_score: N activos con igual peso -> HHI = 1/N exacto
    ds_equal = _mode_diversification_score({"weights": [0.25, 0.25, 0.25, 0.25]})
    checks.append({
        "name": "equal_weight_n_assets_hhi_is_one_over_n",
        "computed": ds_equal["herfindahl_hirschman_index"],
        "expected": 0.25,
        "effective_positions": ds_equal["effective_number_of_positions"],
        "passed": abs(ds_equal["herfindahl_hirschman_index"] - 0.25) < 1e-9 and abs(ds_equal["effective_number_of_positions"] - 4.0) < 0.01,
    })

    validation_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "validation_passed": validation_passed}


# ----------------------------------------------------------------------
# Dispatch principal
# ----------------------------------------------------------------------

def compute_investment_portfolio(mode="validate", params=None):
    params = params or {}
    if mode == "expected_return_variance":
        return _mode_expected_return_variance(params)
    elif mode == "rebalancing_drift":
        return _mode_rebalancing_drift(params)
    elif mode == "risk_return_score":
        return _mode_risk_return_score(params)
    elif mode == "diversification_score":
        return _mode_diversification_score(params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(
            f"modo desconocido: {mode}. Use expected_return_variance | rebalancing_drift | "
            f"risk_return_score | diversification_score | validate"
        )


try:
    from tool_registry import register_tool
    register_tool(
        name="investment_portfolio_tool",
        schema=INVESTMENT_PORTFOLIO_TOOL_SCHEMA,
        handler=lambda args: compute_investment_portfolio(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    d = compute_investment_portfolio("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de investment_portfolio_tool.py pasaron OK.")
