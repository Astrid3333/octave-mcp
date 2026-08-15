"""
financial_literacy_score_tool.py

Score compuesto de salud financiera. A diferencia del resto de Fase D,
este modulo no re-simula liquidez/deuda/inversion desde cero: recibe como
input los INDICADORES ya calculados por las tools especializadas
(emergency_fund_tool para meses de cobertura, un ratio deuda/ingreso,
savings_rate_tool para la tasa de ahorro, investment_portfolio_tool para
un indice de diversificacion) y los combina en un score ponderado 0-100.
Esto evita duplicar logica de negocio ya validada en otros modulos y dejar
la responsabilidad de "traer los numeros" a quien orquesta la llamada
(igual que decision_support_tool no recalcula riesgo, solo combina
criterios ya dados).

Cuatro modos:

- health_score: dado los 4 componentes (liquidez, endeudamiento, ahorro,
  diversificacion) ya normalizados 0-100 (o normalizables via umbrales
  simples que trae el propio modulo), calcula el score compuesto
  ponderado y una clasificacion cualitativa.
- component_breakdown: igual que health_score pero devuelve el detalle
  de cada componente (valor crudo, valor normalizado, peso, contribucion
  al score total).
- score_sensitivity: recalcula el score subiendo cada componente en un
  delta fijo (uno por vez, ceteris paribus) para ver cual mueve mas el
  score total -- indica donde conviene poner el esfuerzo marginal.
- validate: suite de checks contra casos con solucion cerrada conocida.

Convencion identica al resto de Fase D: compute_financial_literacy_score
(mode, params=None) -> dict, registrado via tool_registry.register_tool().
"""


FINANCIAL_LITERACY_SCORE_TOOL_SCHEMA = {
    "name": "financial_literacy_score_tool",
    "description": (
        "Score compuesto de salud financiera, combinando 4 componentes ya "
        "calculados por otras tools de Fase D (no los recalcula): "
        "liquidez (meses de cobertura, de emergency_fund_tool), "
        "endeudamiento (ratio deuda/ingreso), ahorro (savings_rate, de "
        "savings_rate_tool) y diversificacion (indice de investment_"
        "portfolio_tool). health_score (normaliza cada componente 0-100 "
        "via umbrales simples y devuelve el score ponderado + "
        "clasificacion), component_breakdown (detalle de valor crudo/"
        "normalizado/peso/contribucion por componente), score_sensitivity "
        "(sube cada componente un delta fijo ceteris paribus para ver cual "
        "mueve mas el score total), validate (suite de checks). Pesos "
        "default: liquidez 25%, endeudamiento 25%, ahorro 25%, "
        "diversificacion 25% (configurables)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "health_score",
                    "component_breakdown",
                    "score_sensitivity",
                    "validate",
                ],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}

DEFAULT_WEIGHTS = {
    "liquidity": 0.25,
    "debt": 0.25,
    "savings": 0.25,
    "diversification": 0.25,
}


def _normalize_liquidity(months_covered):
    """meses de cobertura de emergencia -> 0-100. Umbral: 6 meses = 100."""
    target_months = 6.0
    return min(100.0, 100.0 * months_covered / target_months)


def _normalize_debt(debt_to_income_ratio):
    """ratio deuda/ingreso -> 0-100 (mas bajo el ratio, mejor el score).
    Umbral: ratio 0 = 100, ratio >= 0.5 = 0, lineal entre medio."""
    threshold = 0.5
    score = 100.0 * (1.0 - debt_to_income_ratio / threshold)
    return max(0.0, min(100.0, score))


def _normalize_savings(savings_rate):
    """tasa de ahorro (0-1) -> 0-100. Umbral: 20% de ahorro = 100."""
    target_rate = 0.20
    return min(100.0, 100.0 * savings_rate / target_rate)


def _normalize_diversification(diversification_index):
    """indice de diversificacion 0-1 (ej. 1 - HHI normalizado) -> 0-100
    directo (se asume que ya viene en escala 0-1)."""
    return max(0.0, min(100.0, 100.0 * diversification_index))


def _get_components(params):
    """Extrae los 4 componentes crudos y los normaliza. Acepta valores
    crudos (months_covered, debt_to_income_ratio, savings_rate,
    diversification_index) o, si vienen ya normalizados 0-100, un flag
    pre_normalized=True para saltear la normalizacion."""
    required = ["months_covered", "debt_to_income_ratio", "savings_rate", "diversification_index"]
    missing = [r for r in required if r not in params]
    if missing:
        raise ValueError(f"faltan parametros requeridos: {missing}")

    months_covered = float(params["months_covered"])
    debt_to_income_ratio = float(params["debt_to_income_ratio"])
    savings_rate = float(params["savings_rate"])
    diversification_index = float(params["diversification_index"])

    if months_covered < 0:
        raise ValueError("months_covered debe ser >= 0")
    if debt_to_income_ratio < 0:
        raise ValueError("debt_to_income_ratio debe ser >= 0")
    if not (0.0 <= savings_rate <= 1.0):
        raise ValueError("savings_rate debe estar en [0, 1]")
    if not (0.0 <= diversification_index <= 1.0):
        raise ValueError("diversification_index debe estar en [0, 1]")

    return {
        "liquidity": {"raw": months_covered, "normalized": _normalize_liquidity(months_covered)},
        "debt": {"raw": debt_to_income_ratio, "normalized": _normalize_debt(debt_to_income_ratio)},
        "savings": {"raw": savings_rate, "normalized": _normalize_savings(savings_rate)},
        "diversification": {"raw": diversification_index, "normalized": _normalize_diversification(diversification_index)},
    }


def _get_weights(params):
    weights = dict(DEFAULT_WEIGHTS)
    custom = params.get("weights", {})
    weights.update({k: float(v) for k, v in custom.items()})
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"los pesos deben sumar 1.0, suman {total}")
    return weights


def _classify(score):
    if score >= 80:
        return "excelente"
    elif score >= 60:
        return "buena"
    elif score >= 40:
        return "regular"
    else:
        return "debil"


def _compute_score(components, weights):
    score = sum(components[k]["normalized"] * weights[k] for k in weights)
    return score


def _mode_health_score(params):
    components = _get_components(params)
    weights = _get_weights(params)
    score = _compute_score(components, weights)

    return {
        "mode": "health_score",
        "score": score,
        "classification": _classify(score),
        "weights": weights,
    }


def _mode_component_breakdown(params):
    components = _get_components(params)
    weights = _get_weights(params)
    score = _compute_score(components, weights)

    detail = [
        {
            "component": k,
            "raw_value": components[k]["raw"],
            "normalized_0_100": components[k]["normalized"],
            "weight": weights[k],
            "contribution_to_score": components[k]["normalized"] * weights[k],
        }
        for k in weights
    ]

    return {
        "mode": "component_breakdown",
        "score": score,
        "classification": _classify(score),
        "components": detail,
    }


def _mode_score_sensitivity(params):
    base_components = _get_components(params)
    weights = _get_weights(params)
    base_score = _compute_score(base_components, weights)

    delta = float(params.get("delta_normalized_points", 10.0))

    results = []
    for k in weights:
        bumped = {
            key: dict(val) for key, val in base_components.items()
        }
        bumped[k]["normalized"] = min(100.0, bumped[k]["normalized"] + delta)
        new_score = _compute_score(bumped, weights)
        results.append({
            "component": k,
            "delta_normalized_points": delta,
            "new_score": new_score,
            "score_gain": new_score - base_score,
        })

    results.sort(key=lambda r: r["score_gain"], reverse=True)

    return {
        "mode": "score_sensitivity",
        "base_score": base_score,
        "delta_normalized_points": delta,
        "results": results,
        "highest_impact_component": results[0]["component"] if results else None,
    }


def _mode_validate():
    checks = []

    base_params = {
        "months_covered": 3.0,
        "debt_to_income_ratio": 0.25,
        "savings_rate": 0.10,
        "diversification_index": 0.5,
    }

    # 1) health_score: componentes en el maximo dan score 100
    r1 = _mode_health_score({
        "months_covered": 6.0, "debt_to_income_ratio": 0.0,
        "savings_rate": 0.20, "diversification_index": 1.0,
    })
    checks.append({
        "name": "all_max_components_give_score_100",
        "score": r1["score"], "classification": r1["classification"],
        "passed": abs(r1["score"] - 100.0) < 1e-9 and r1["classification"] == "excelente",
    })

    # 2) health_score: componentes en el minimo dan score 0
    r2 = _mode_health_score({
        "months_covered": 0.0, "debt_to_income_ratio": 0.5,
        "savings_rate": 0.0, "diversification_index": 0.0,
    })
    checks.append({
        "name": "all_min_components_give_score_0",
        "score": r2["score"], "classification": r2["classification"],
        "passed": abs(r2["score"]) < 1e-9 and r2["classification"] == "debil",
    })

    # 3) health_score: pesos que no suman 1 lanzan excepcion
    try:
        _mode_health_score({**base_params, "weights": {"liquidity": 0.5}})
        raised3 = False
    except ValueError:
        raised3 = True
    checks.append({"name": "invalid_weights_sum_raises", "passed": raised3})

    # 4) health_score: savings_rate fuera de [0,1] lanza excepcion
    try:
        _mode_health_score({**base_params, "savings_rate": 1.5})
        raised4 = False
    except ValueError:
        raised4 = True
    checks.append({"name": "savings_rate_out_of_range_raises", "passed": raised4})

    # 5) component_breakdown: contribuciones suman el score total
    r5 = _mode_component_breakdown(base_params)
    contrib_sum = sum(c["contribution_to_score"] for c in r5["components"])
    checks.append({
        "name": "contributions_sum_to_total_score",
        "contrib_sum": contrib_sum, "score": r5["score"],
        "passed": abs(contrib_sum - r5["score"]) < 1e-9,
    })

    # 6) component_breakdown: peso custom se refleja en la contribucion
    r6 = _mode_component_breakdown({
        **base_params,
        "weights": {"liquidity": 0.7, "debt": 0.1, "savings": 0.1, "diversification": 0.1},
    })
    liquidity_detail = next(c for c in r6["components"] if c["component"] == "liquidity")
    checks.append({
        "name": "custom_weight_reflected_in_contribution",
        "weight": liquidity_detail["weight"],
        "passed": abs(liquidity_detail["weight"] - 0.7) < 1e-9
        and abs(liquidity_detail["contribution_to_score"] - liquidity_detail["normalized_0_100"] * 0.7) < 1e-9,
    })

    # 7) score_sensitivity: subir un componente nunca baja el score
    r7 = _mode_score_sensitivity(base_params)
    checks.append({
        "name": "sensitivity_bump_never_decreases_score",
        "min_gain": min(res["score_gain"] for res in r7["results"]),
        "passed": all(res["score_gain"] >= -1e-9 for res in r7["results"]),
    })

    # 8) score_sensitivity: componente ya en el tope (delta lo satura) da gain 0
    r8 = _mode_score_sensitivity({
        "months_covered": 6.0, "debt_to_income_ratio": 0.25,
        "savings_rate": 0.10, "diversification_index": 0.5,
        "delta_normalized_points": 10.0,
    })
    liquidity_gain = next(r for r in r8["results"] if r["component"] == "liquidity")
    checks.append({
        "name": "saturated_component_gives_zero_gain",
        "gain": liquidity_gain["score_gain"],
        "passed": abs(liquidity_gain["score_gain"]) < 1e-9,
    })

    # 9) months_covered negativo lanza excepcion
    try:
        _mode_health_score({**base_params, "months_covered": -1.0})
        raised9 = False
    except ValueError:
        raised9 = True
    checks.append({"name": "negative_months_covered_raises", "passed": raised9})

    # 10) modo invalido lanza excepcion
    try:
        compute_financial_literacy_score("modo_invalido", {})
        invalid_raised = False
    except (KeyError, ValueError):
        invalid_raised = True
    checks.append({"name": "invalid_mode_raises", "passed": invalid_raised})

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_financial_literacy_score(mode, params=None):
    params = params or {}

    if mode == "health_score":
        return _mode_health_score(params)
    elif mode == "component_breakdown":
        return _mode_component_breakdown(params)
    elif mode == "score_sensitivity":
        return _mode_score_sensitivity(params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(
            f"modo desconocido: {mode}. Use health_score | component_breakdown | "
            f"score_sensitivity | validate"
        )


try:
    from tool_registry import register_tool
    register_tool(
        name="financial_literacy_score_tool",
        schema=FINANCIAL_LITERACY_SCORE_TOOL_SCHEMA,
        handler=lambda args: compute_financial_literacy_score(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    d = compute_financial_literacy_score("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de financial_literacy_score_tool.py pasaron OK.")
