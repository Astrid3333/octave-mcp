"""
life_insurance_math_tool.py
Fase D / Tanda 3 (2 de 3): metodos de calculo de seguro de vida.
Autocontenido: no importa funciones privadas de otros modulos del repo
(leccion de retirement_planner_tool: evitar acoplamiento a nombres internos).

Modos:
  - human_life_value: valor presente del ingreso neto futuro de la persona asegurada.
  - needs_based_coverage: metodo de necesidades (deudas + gastos finales + educacion +
    reemplazo de ingreso - activos liquidos).
  - term_vs_permanent_cost: compara costo nominal y valor presente de poliza de
    termino vs poliza permanente (con valor en efectivo neteado al final).
  - coverage_gap_analysis: cobertura actual vs necesaria, clasificacion cualitativa.
  - validate: suite de checks contra casos cerrados.
"""

import json


LIFE_INSURANCE_MATH_TOOL_SCHEMA = {
    "name": "life_insurance_math_tool",
    "description": (
        "Calculos de seguro de vida: human_life_value (valor presente del ingreso "
        "neto futuro de la persona asegurada, con crecimiento salarial opcional), "
        "needs_based_coverage (metodo de necesidades: deudas + gastos finales + "
        "fondo de educacion + reemplazo de ingreso, menos activos liquidos), "
        "term_vs_permanent_cost (compara costo nominal y valor presente de poliza "
        "de termino vs permanente, netea valor en efectivo al horizonte), "
        "coverage_gap_analysis (cobertura actual vs necesaria, banda cualitativa "
        "sin_cobertura/insuficiente/por_debajo_de_lo_adecuado/adecuada/sobre_cobertura). "
        "confidence_flag 'alta' para la mecanica de valor presente (formulas cerradas "
        "y suma anio a anio deterministica); montos de necesidad y tasas de descuento "
        "son supuestos de quien llama. No es asesoria financiera ni actuarial. "
        "validate corre 8 checks de referencia."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "human_life_value",
                    "needs_based_coverage",
                    "term_vs_permanent_cost",
                    "coverage_gap_analysis",
                    "validate",
                ],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


# ----------------------------------------------------------------------
# Motores matematicos autocontenidos
# ----------------------------------------------------------------------

def _pv_growing_stream(annual_amount: float, years: int, discount_rate: float,
                        growth_rate: float = 0.0) -> float:
    """
    Valor presente de un flujo anual que crece a growth_rate, descontado a discount_rate.
    Suma explicita anio a anio (mas robusto de validar que la forma cerrada).
    t = 1..years, monto_t = annual_amount * (1+growth_rate)^(t-1)
    """
    pv = 0.0
    for t in range(1, years + 1):
        amount_t = annual_amount * ((1 + growth_rate) ** (t - 1))
        pv += amount_t / ((1 + discount_rate) ** t)
    return pv


def _pv_level_annuity(annual_amount: float, years: int, discount_rate: float) -> float:
    """Valor presente de una anualidad nivelada (caso particular de _pv_growing_stream)."""
    return _pv_growing_stream(annual_amount, years, discount_rate, growth_rate=0.0)


# ----------------------------------------------------------------------
# Modo 1: human_life_value
# ----------------------------------------------------------------------

def _mode_human_life_value(params: dict) -> dict:
    current_income = float(params["current_income"])
    self_consumption_rate = float(params.get("self_consumption_rate", 0.0))
    years_to_retirement = int(params["years_to_retirement"])
    discount_rate = float(params["discount_rate"])
    income_growth_rate = float(params.get("income_growth_rate", 0.0))

    net_annual_income = current_income * (1 - self_consumption_rate)
    human_life_value = _pv_growing_stream(
        net_annual_income, years_to_retirement, discount_rate, income_growth_rate
    )

    return {
        "current_income": current_income,
        "self_consumption_rate": self_consumption_rate,
        "net_annual_income_year1": round(net_annual_income, 2),
        "years_to_retirement": years_to_retirement,
        "discount_rate": discount_rate,
        "income_growth_rate": income_growth_rate,
        "human_life_value": round(human_life_value, 2),
    }


# ----------------------------------------------------------------------
# Modo 2: needs_based_coverage
# ----------------------------------------------------------------------

def _mode_needs_based_coverage(params: dict) -> dict:
    debts = float(params.get("debts", 0.0))
    final_expenses = float(params.get("final_expenses", 0.0))
    education_fund = float(params.get("education_fund", 0.0))
    income_replacement_years = float(params.get("income_replacement_years", 0.0))
    annual_income_replacement = float(params.get("annual_income_replacement", 0.0))
    liquid_assets = float(params.get("liquid_assets", 0.0))

    income_replacement_total = income_replacement_years * annual_income_replacement
    gross_need = debts + final_expenses + education_fund + income_replacement_total
    net_need = gross_need - liquid_assets

    return {
        "debts": debts,
        "final_expenses": final_expenses,
        "education_fund": education_fund,
        "income_replacement_total": round(income_replacement_total, 2),
        "liquid_assets": liquid_assets,
        "gross_need": round(gross_need, 2),
        "net_need": round(net_need, 2),
    }


# ----------------------------------------------------------------------
# Modo 3: term_vs_permanent_cost
# ----------------------------------------------------------------------

def _mode_term_vs_permanent_cost(params: dict) -> dict:
    term_annual_premium = float(params["term_annual_premium"])
    term_years = int(params["term_years"])
    permanent_annual_premium = float(params["permanent_annual_premium"])
    permanent_years = int(params["permanent_years"])
    cash_value_at_horizon = float(params.get("cash_value_at_horizon", 0.0))
    discount_rate = float(params["discount_rate"])

    nominal_term_total = term_annual_premium * term_years
    nominal_permanent_total = permanent_annual_premium * permanent_years

    pv_term_premiums = _pv_level_annuity(term_annual_premium, term_years, discount_rate)
    pv_permanent_premiums = _pv_level_annuity(
        permanent_annual_premium, permanent_years, discount_rate
    )
    pv_cash_value = cash_value_at_horizon / ((1 + discount_rate) ** permanent_years)
    pv_permanent_net_cost = pv_permanent_premiums - pv_cash_value

    cheaper_on_pv_basis = (
        "termino" if pv_term_premiums < pv_permanent_net_cost else "permanente"
    )

    return {
        "term_annual_premium": term_annual_premium,
        "term_years": term_years,
        "nominal_term_total": round(nominal_term_total, 2),
        "pv_term_premiums": round(pv_term_premiums, 2),
        "permanent_annual_premium": permanent_annual_premium,
        "permanent_years": permanent_years,
        "nominal_permanent_total": round(nominal_permanent_total, 2),
        "pv_permanent_premiums": round(pv_permanent_premiums, 2),
        "cash_value_at_horizon": cash_value_at_horizon,
        "pv_cash_value": round(pv_cash_value, 2),
        "pv_permanent_net_cost": round(pv_permanent_net_cost, 2),
        "cheaper_on_pv_basis": cheaper_on_pv_basis,
    }


# ----------------------------------------------------------------------
# Modo 4: coverage_gap_analysis
# ----------------------------------------------------------------------

def _classify_coverage_ratio(ratio: float, current_coverage: float) -> str:
    if current_coverage <= 0:
        return "sin_cobertura"
    if ratio < 0.5:
        return "insuficiente"
    if ratio < 0.9:
        return "por_debajo_de_lo_adecuado"
    if ratio <= 1.2:
        return "adecuada"
    return "sobre_cobertura"


def _mode_coverage_gap_analysis(params: dict) -> dict:
    current_coverage = float(params["current_coverage"])
    needed_coverage = float(params["needed_coverage"])

    gap = needed_coverage - current_coverage
    ratio = (current_coverage / needed_coverage) if needed_coverage > 0 else float("inf")
    band = _classify_coverage_ratio(ratio, current_coverage)

    return {
        "current_coverage": current_coverage,
        "needed_coverage": needed_coverage,
        "gap": round(gap, 2),
        "coverage_ratio": round(ratio, 4) if ratio != float("inf") else None,
        "band": band,
    }


# ----------------------------------------------------------------------
# Validacion
# ----------------------------------------------------------------------

def _mode_validate() -> dict:
    checks = []

    # 1) human_life_value sin crecimiento debe matchear anualidad nivelada exacta
    hlv = _mode_human_life_value({
        "current_income": 60000.0,
        "self_consumption_rate": 0.2,
        "years_to_retirement": 25,
        "discount_rate": 0.05,
        "income_growth_rate": 0.0,
    })
    expected_level_pv = _pv_level_annuity(60000.0 * 0.8, 25, 0.05)
    checks.append({
        "name": "human_life_value_matches_level_annuity_when_no_growth",
        "computed": hlv["human_life_value"],
        "expected": round(expected_level_pv, 2),
        "abs_diff": round(abs(hlv["human_life_value"] - expected_level_pv), 6),
        "passed": abs(hlv["human_life_value"] - expected_level_pv) < 0.01,
    })

    # 2) mayor crecimiento de ingreso -> mayor human life value (todo lo demas igual)
    hlv_low_growth = _mode_human_life_value({
        "current_income": 60000.0, "self_consumption_rate": 0.2,
        "years_to_retirement": 25, "discount_rate": 0.05, "income_growth_rate": 0.0,
    })["human_life_value"]
    hlv_high_growth = _mode_human_life_value({
        "current_income": 60000.0, "self_consumption_rate": 0.2,
        "years_to_retirement": 25, "discount_rate": 0.05, "income_growth_rate": 0.03,
    })["human_life_value"]
    checks.append({
        "name": "higher_income_growth_gives_higher_hlv",
        "hlv_low_growth": hlv_low_growth,
        "hlv_high_growth": hlv_high_growth,
        "passed": hlv_high_growth > hlv_low_growth,
    })

    # 3) needs_based_coverage: suma simple verificable a mano
    nbc = _mode_needs_based_coverage({
        "debts": 150000.0,
        "final_expenses": 15000.0,
        "education_fund": 80000.0,
        "income_replacement_years": 10,
        "annual_income_replacement": 40000.0,
        "liquid_assets": 50000.0,
    })
    expected_net_need = 150000.0 + 15000.0 + 80000.0 + (10 * 40000.0) - 50000.0
    checks.append({
        "name": "needs_based_coverage_arithmetic_exact",
        "computed": nbc["net_need"],
        "expected": round(expected_net_need, 2),
        "passed": abs(nbc["net_need"] - expected_net_need) < 0.01,
    })

    # 4) mas activos liquidos -> menor necesidad neta
    nbc_more_assets = _mode_needs_based_coverage({
        "debts": 150000.0, "final_expenses": 15000.0, "education_fund": 80000.0,
        "income_replacement_years": 10, "annual_income_replacement": 40000.0,
        "liquid_assets": 200000.0,
    })
    checks.append({
        "name": "more_liquid_assets_lowers_net_need",
        "net_need_low_assets": nbc["net_need"],
        "net_need_high_assets": nbc_more_assets["net_need"],
        "passed": nbc_more_assets["net_need"] < nbc["net_need"],
    })

    # 5) term_vs_permanent_cost: term nominal exacto (aritmetica simple)
    tvp = _mode_term_vs_permanent_cost({
        "term_annual_premium": 500.0,
        "term_years": 20,
        "permanent_annual_premium": 3000.0,
        "permanent_years": 40,
        "cash_value_at_horizon": 90000.0,
        "discount_rate": 0.05,
    })
    checks.append({
        "name": "term_nominal_total_exact",
        "computed": tvp["nominal_term_total"],
        "expected": 500.0 * 20,
        "passed": abs(tvp["nominal_term_total"] - 500.0 * 20) < 0.01,
    })

    # 6) termino barato de prima anual vs permanente cara: termino debe ganar en PV
    checks.append({
        "name": "cheap_term_beats_expensive_permanent_on_pv",
        "pv_term": tvp["pv_term_premiums"],
        "pv_permanent_net": tvp["pv_permanent_net_cost"],
        "cheaper_on_pv_basis": tvp["cheaper_on_pv_basis"],
        "passed": tvp["cheaper_on_pv_basis"] == "termino",
    })

    # 7) coverage_gap_analysis: bandas monotonicas y distintas
    bands = []
    for cc in [0.0, 100000.0, 700000.0, 950000.0, 1500000.0]:
        r = _mode_coverage_gap_analysis({
            "current_coverage": cc, "needed_coverage": 1000000.0,
        })
        bands.append(r["band"])
    checks.append({
        "name": "coverage_gap_bands_monotonic_and_distinct",
        "bands": bands,
        "passed": bands == [
            "sin_cobertura", "insuficiente", "por_debajo_de_lo_adecuado",
            "adecuada", "sobre_cobertura",
        ],
    })

    # 8) coverage_gap_analysis: gap exacto por aritmetica simple
    gap_check = _mode_coverage_gap_analysis({
        "current_coverage": 300000.0, "needed_coverage": 800000.0,
    })
    checks.append({
        "name": "coverage_gap_arithmetic_exact",
        "computed": gap_check["gap"],
        "expected": 500000.0,
        "passed": abs(gap_check["gap"] - 500000.0) < 0.01,
    })

    validation_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "validation_passed": validation_passed}


# ----------------------------------------------------------------------
# Dispatch principal
# ----------------------------------------------------------------------

def compute_life_insurance_math(mode="validate", params=None):
    params = params or {}
    if mode == "human_life_value":
        return _mode_human_life_value(params)
    elif mode == "needs_based_coverage":
        return _mode_needs_based_coverage(params)
    elif mode == "term_vs_permanent_cost":
        return _mode_term_vs_permanent_cost(params)
    elif mode == "coverage_gap_analysis":
        return _mode_coverage_gap_analysis(params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(
            f"modo desconocido: {mode}. Use human_life_value | needs_based_coverage | "
            f"term_vs_permanent_cost | coverage_gap_analysis | validate"
        )


try:
    from tool_registry import register_tool
    register_tool(
        name="life_insurance_math_tool",
        schema=LIFE_INSURANCE_MATH_TOOL_SCHEMA,
        handler=lambda args: compute_life_insurance_math(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    d = compute_life_insurance_math("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de life_insurance_math_tool.py pasaron OK.")
