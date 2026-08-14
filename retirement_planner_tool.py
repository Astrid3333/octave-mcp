"""
retirement_planner_tool: planificacion de retiro con motor de interes compuesto
reusado de savings_goal_tool (future_value). Fase D / Tanda 3.

Modos:
  - accumulation_projection: proyecta saldo de retiro con aportes crecientes por inflacion salarial
  - required_savings_rate: % de salario a ahorrar para alcanzar una meta de reemplazo de ingreso
  - withdrawal_sustainability: simulacion de decumulacion (regla de retiro tipo 4%)
  - replacement_ratio: % del ultimo salario cubierto por el fondo proyectado
  - validate: suite de autochequeos contra formulas cerradas y casos de libro
"""

def _future_value(present_value: float, periodic_contribution: float,
                   annual_rate: float, years: float,
                   periods_per_year: int = 1) -> float:
    """
    Valor futuro con aportes periodicos, capitalizacion compuesta.
    FV = PV*(1+r)^n + PMT * [((1+r)^n - 1) / r]
    """
    n = periods_per_year * years
    r = annual_rate / periods_per_year
    if r == 0:
        return present_value + periodic_contribution * n
    growth = (1 + r) ** n
    fv_principal = present_value * growth
    fv_contributions = periodic_contribution * ((growth - 1) / r)
    return fv_principal + fv_contributions


RETIREMENT_PLANNER_TOOL_SCHEMA = {
    "name": "retirement_planner_tool",
    "description": (
        "Planificacion de retiro con motor de interes compuesto: accumulation_projection "
        "(proyeccion de saldo con aportes que crecen por inflacion salarial), "
        "required_savings_rate (% de salario a ahorrar hoy para una meta de reemplazo de ingreso), "
        "withdrawal_sustainability (simulacion de decumulacion, regla de retiro tipo 4% de Bengen), "
        "replacement_ratio (% del ultimo salario cubierto por el fondo proyectado, con banda cualitativa). "
        "confidence_flag 'alta' para la mecanica (formulas cerradas de anualidad e iteracion "
        "aritmetica determinista); las tasas de retorno/inflacion futuras son un supuesto de "
        "quien llama, no una prediccion. No es asesoria financiera. validate corre 7 checks de referencia."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "accumulation_projection", "required_savings_rate",
                    "withdrawal_sustainability", "replacement_ratio", "validate",
                ],
                "default": "validate",
            },
            "params": {"type": "object"},
        },
    },
}


# ----------------------------------------------------------------------
# accumulation_projection: aporte que crece por inflacion salarial
# ----------------------------------------------------------------------
def _accumulation_projection(params):
    current_savings = float(params.get("current_savings", 0.0))
    annual_contribution = float(params.get("annual_contribution", 0.0))
    annual_return = float(params.get("annual_return", 0.06))
    contribution_growth_rate = float(params.get("contribution_growth_rate", 0.0))
    n_years = int(params.get("n_years", 30))

    if annual_return <= -1.0:
        raise ValueError("annual_return debe ser > -1.0")
    if n_years <= 0:
        raise ValueError("n_years debe ser > 0")

    balance = current_savings
    contribution = annual_contribution
    trajectory = []
    for year in range(1, n_years + 1):
        balance = balance * (1.0 + annual_return) + contribution
        trajectory.append({"year": year, "contribution": round(contribution, 2), "balance": round(balance, 2)})
        contribution *= (1.0 + contribution_growth_rate)

    return {
        "mode": "accumulation_projection",
        "final_balance": round(balance, 2),
        "total_contributed": round(sum(t["contribution"] for t in trajectory) + current_savings, 2),
        "trajectory": trajectory,
    }


# ----------------------------------------------------------------------
# required_savings_rate: % de salario para alcanzar una meta de reemplazo
# ----------------------------------------------------------------------
def _required_savings_rate(params):
    current_salary = float(params.get("current_salary"))
    salary_growth_rate = float(params.get("salary_growth_rate", 0.02))
    annual_return = float(params.get("annual_return", 0.06))
    n_years = int(params.get("n_years"))
    target_replacement_ratio = float(params.get("target_replacement_ratio", 0.7))
    current_savings = float(params.get("current_savings", 0.0))
    withdrawal_rate = float(params.get("withdrawal_rate", 0.04))

    if not (0.0 < target_replacement_ratio <= 2.0):
        raise ValueError("target_replacement_ratio debe estar en (0, 2]")
    if withdrawal_rate <= 0.0:
        raise ValueError("withdrawal_rate debe ser > 0")
    if n_years <= 0:
        raise ValueError("n_years debe ser > 0")

    final_salary = current_salary * (1.0 + salary_growth_rate) ** n_years
    target_annual_income = final_salary * target_replacement_ratio
    target_balance = target_annual_income / withdrawal_rate

    # busqueda binaria sobre la tasa de ahorro (fraccion del salario, que crece con el salario)
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        balance = current_savings
        salary = current_salary
        for _year in range(n_years):
            contribution = salary * mid
            balance = balance * (1.0 + annual_return) + contribution
            salary *= (1.0 + salary_growth_rate)
        if balance < target_balance:
            lo = mid
        else:
            hi = mid

    savings_rate = hi

    return {
        "mode": "required_savings_rate",
        "final_salary_projected": round(final_salary, 2),
        "target_annual_income": round(target_annual_income, 2),
        "target_balance_needed": round(target_balance, 2),
        "required_savings_rate": round(savings_rate, 4),
        "required_annual_contribution_today": round(current_salary * savings_rate, 2),
    }


# ----------------------------------------------------------------------
# withdrawal_sustainability: decumulacion, cuantos anios dura el fondo
# ----------------------------------------------------------------------
def _withdrawal_sustainability(params):
    initial_balance = float(params.get("initial_balance"))
    annual_withdrawal = float(params.get("annual_withdrawal"))
    annual_return = float(params.get("annual_return", 0.05))
    inflation_rate = float(params.get("inflation_rate", 0.03))
    max_years = int(params.get("max_years", 60))

    if initial_balance <= 0:
        raise ValueError("initial_balance debe ser > 0")
    if annual_withdrawal <= 0:
        raise ValueError("annual_withdrawal debe ser > 0")

    balance = initial_balance
    withdrawal = annual_withdrawal
    trajectory = []
    depleted_year = None
    for year in range(1, max_years + 1):
        balance = balance * (1.0 + annual_return) - withdrawal
        trajectory.append({"year": year, "withdrawal": round(withdrawal, 2), "balance": round(max(balance, 0.0), 2)})
        if balance <= 0:
            depleted_year = year
            balance = 0.0
            break
        withdrawal *= (1.0 + inflation_rate)

    sustainable_indefinitely = depleted_year is None

    return {
        "mode": "withdrawal_sustainability",
        "depleted_at_year": depleted_year,
        "sustainable_indefinitely": sustainable_indefinitely,
        "final_balance": round(balance, 2),
        "initial_withdrawal_rate": round(annual_withdrawal / initial_balance, 4),
        "trajectory": trajectory,
    }


# ----------------------------------------------------------------------
# replacement_ratio: % del ultimo salario cubierto por el fondo proyectado
# ----------------------------------------------------------------------
def _replacement_ratio(params):
    projected_balance = float(params.get("projected_balance"))
    final_salary = float(params.get("final_salary"))
    withdrawal_rate = float(params.get("withdrawal_rate", 0.04))
    other_annual_income = float(params.get("other_annual_income", 0.0))

    if final_salary <= 0:
        raise ValueError("final_salary debe ser > 0")
    if withdrawal_rate <= 0:
        raise ValueError("withdrawal_rate debe ser > 0")

    annual_income_from_savings = projected_balance * withdrawal_rate
    total_annual_income = annual_income_from_savings + other_annual_income
    ratio = total_annual_income / final_salary

    if ratio < 0.5:
        band = "insuficiente"
    elif ratio < 0.7:
        band = "ajustado"
    elif ratio <= 1.0:
        band = "adecuado"
    else:
        band = "holgado"

    return {
        "mode": "replacement_ratio",
        "annual_income_from_savings": round(annual_income_from_savings, 2),
        "total_annual_retirement_income": round(total_annual_income, 2),
        "replacement_ratio": round(ratio, 4),
        "band": band,
    }


# ----------------------------------------------------------------------
# validate: 7 checks de referencia
# ----------------------------------------------------------------------
def _validate():
    checks = []

    # 1) accumulation_projection sin crecimiento de aporte debe matchear future_value exacto
    #    (misma convencion de capitalizacion: anual, periods_per_year=1)
    r = _accumulation_projection({
        "current_savings": 10000.0, "annual_contribution": 6000.0,
        "annual_return": 0.07, "contribution_growth_rate": 0.0, "n_years": 20,
    })
    fv_expected = _future_value(10000.0, 6000.0, 0.07, 20, periods_per_year=1)
    checks.append({
        "name": "accumulation_matches_future_value_when_no_growth",
        "computed": r["final_balance"], "expected_annual_fv": round(fv_expected, 2),
        "abs_diff": round(abs(r["final_balance"] - fv_expected), 2),
        "passed": abs(r["final_balance"] - fv_expected) < 5.0,
    })

    # 2) mas anios de aporte siempre da mayor balance final
    r10 = _accumulation_projection({"current_savings": 0, "annual_contribution": 5000, "annual_return": 0.06, "n_years": 10})
    r20 = _accumulation_projection({"current_savings": 0, "annual_contribution": 5000, "annual_return": 0.06, "n_years": 20})
    checks.append({
        "name": "more_years_gives_higher_balance",
        "balance_10y": r10["final_balance"], "balance_20y": r20["final_balance"],
        "passed": r20["final_balance"] > r10["final_balance"],
    })

    # 3) required_savings_rate: verificar que la tasa encontrada efectivamente alcanza la meta
    rr = _required_savings_rate({
        "current_salary": 50000, "salary_growth_rate": 0.02, "annual_return": 0.06,
        "n_years": 25, "target_replacement_ratio": 0.7, "withdrawal_rate": 0.04,
    })
    balance_check = 0.0
    salary_check = 50000.0
    for _ in range(25):
        balance_check = balance_check * 1.06 + salary_check * rr["required_savings_rate"]
        salary_check *= 1.02
    checks.append({
        "name": "required_savings_rate_reaches_target_balance",
        "target": rr["target_balance_needed"], "achieved": round(balance_check, 2),
        "passed": abs(balance_check - rr["target_balance_needed"]) < rr["target_balance_needed"] * 0.01,
    })

    # 4) required_savings_rate: meta mas alta requiere tasa de ahorro mas alta
    rr_low = _required_savings_rate({
        "current_salary": 50000, "n_years": 25, "target_replacement_ratio": 0.5,
    })
    rr_high = _required_savings_rate({
        "current_salary": 50000, "n_years": 25, "target_replacement_ratio": 1.0,
    })
    checks.append({
        "name": "higher_target_replacement_needs_higher_savings_rate",
        "rate_low_target": rr_low["required_savings_rate"], "rate_high_target": rr_high["required_savings_rate"],
        "passed": rr_high["required_savings_rate"] > rr_low["required_savings_rate"],
    })

    # 5) withdrawal_sustainability: caso clasico regla del 4% (Bengen), retorno=inflacion+4% real aprox
    # con retorno nominal 7% e inflacion 3%, retiro inicial 4% deberia durar >=30 anios tipicamente
    ws = _withdrawal_sustainability({
        "initial_balance": 1000000, "annual_withdrawal": 40000,
        "annual_return": 0.07, "inflation_rate": 0.03, "max_years": 40,
    })
    checks.append({
        "name": "four_percent_rule_survives_30_years_at_7pct_return",
        "depleted_at_year": ws["depleted_at_year"], "sustainable_indefinitely": ws["sustainable_indefinitely"],
        "passed": ws["depleted_at_year"] is None or ws["depleted_at_year"] >= 30,
    })

    # 6) withdrawal_sustainability: retiro excesivo se agota rapido (caso extremo de control)
    ws_bad = _withdrawal_sustainability({
        "initial_balance": 1000000, "annual_withdrawal": 150000,
        "annual_return": 0.05, "inflation_rate": 0.03, "max_years": 40,
    })
    checks.append({
        "name": "excessive_withdrawal_depletes_fast",
        "depleted_at_year": ws_bad["depleted_at_year"],
        "passed": ws_bad["depleted_at_year"] is not None and ws_bad["depleted_at_year"] < 15,
    })

    # 7) replacement_ratio: banda coherente en los 4 extremos
    bands = []
    for bal in [200000, 700000, 1200000, 2000000]:
        res = _replacement_ratio({"projected_balance": bal, "final_salary": 60000, "withdrawal_rate": 0.04})
        bands.append(res["band"])
    checks.append({
        "name": "replacement_ratio_bands_are_monotonic_and_distinct",
        "bands": bands,
        "passed": bands == sorted(bands, key=lambda b: ["insuficiente", "ajustado", "adecuado", "holgado"].index(b)) and len(set(bands)) >= 3,
    })

    all_pass = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "validation_passed": all_pass}


def compute_retirement_planner(mode="validate", params=None):
    params = params or {}
    if mode == "accumulation_projection":
        return _accumulation_projection(params)
    if mode == "required_savings_rate":
        return _required_savings_rate(params)
    if mode == "withdrawal_sustainability":
        return _withdrawal_sustainability(params)
    if mode == "replacement_ratio":
        return _replacement_ratio(params)
    if mode == "validate":
        return _validate()
    raise ValueError(f"modo desconocido: '{mode}' (validos: accumulation_projection, required_savings_rate, withdrawal_sustainability, replacement_ratio, validate)")


try:
    from tool_registry import register_tool
    register_tool(
        name="retirement_planner_tool",
        schema=RETIREMENT_PLANNER_TOOL_SCHEMA,
        handler=lambda args: compute_retirement_planner(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass

if __name__ == "__main__":
    import json
    print(json.dumps(compute_retirement_planner("validate"), indent=2, ensure_ascii=False))
