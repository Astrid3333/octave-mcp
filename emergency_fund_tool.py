"""
emergency_fund_tool.py
Fase D / Tanda 4 (1 de 3): fondo de emergencia.
Autocontenido: sin imports cruzados a otros modulos del repo.
Schema con name/description/inputSchema desde el inicio.

Modos:
  - coverage_target: monto objetivo del fondo dado gasto mensual esencial y
    meses de cobertura deseados.
  - current_coverage_months: cuantos meses de gasto cubre el ahorro actual.
  - funding_timeline: meses para alcanzar la meta dado aporte mensual y
    retorno esperado (formula cerrada via logaritmo, no iteracion).
  - risk_adjusted_target: ajusta los meses de cobertura recomendados segun
    factores de riesgo cualitativos (ingreso unico, dependientes, etc.).
  - validate: suite de checks contra casos cerrados.
"""

import json
import math


EMERGENCY_FUND_TOOL_SCHEMA = {
    "name": "emergency_fund_tool",
    "description": (
        "Fondo de emergencia: coverage_target (monto objetivo dado gasto mensual "
        "esencial y meses de cobertura deseados), current_coverage_months (meses "
        "de gasto que cubre el ahorro actual), funding_timeline (meses para "
        "alcanzar la meta dado aporte mensual y retorno esperado, formula cerrada "
        "via logaritmo), risk_adjusted_target (ajusta meses de cobertura "
        "recomendados segun factores de riesgo: ingreso unico, dependientes, "
        "empleo inestable, trabajo independiente). confidence_flag 'alta' para "
        "la mecanica de interes compuesto y el despeje algebraico de meses "
        "(deterministicos); los meses de cobertura recomendados en "
        "risk_adjusted_target son una heuristica de referencia, no una regla "
        "universal. No es asesoria financiera. validate corre 8 checks."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "coverage_target",
                    "current_coverage_months",
                    "funding_timeline",
                    "risk_adjusted_target",
                    "validate",
                ],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


# ----------------------------------------------------------------------
# Motores autocontenidos
# ----------------------------------------------------------------------

def _future_value(present_value: float, periodic_contribution: float,
                   annual_rate: float, years: float,
                   periods_per_year: int = 1) -> float:
    n = periods_per_year * years
    r = annual_rate / periods_per_year
    if r == 0:
        return present_value + periodic_contribution * n
    growth = (1 + r) ** n
    return present_value * growth + periodic_contribution * ((growth - 1) / r)


def _months_to_reach_target(target: float, current_savings: float,
                             monthly_contribution: float, annual_rate: float):
    """
    Despeje algebraico (cerrado, via logaritmo) de _future_value para el
    numero de periodos mensuales n, dado target, ahorro actual y aporte
    mensual constante. Devuelve None si la meta es inalcanzable con esos
    parametros (aporte y retorno insuficientes).
    """
    r = annual_rate / 12.0
    if r == 0:
        if monthly_contribution <= 0:
            return 0.0 if current_savings >= target else None
        months = (target - current_savings) / monthly_contribution
        return max(months, 0.0)

    denom = current_savings * r + monthly_contribution
    numer = target * r + monthly_contribution
    if denom <= 0 or numer <= 0:
        return None
    growth = numer / denom
    if growth <= 0:
        return None
    months = math.log(growth) / math.log(1 + r)
    return max(months, 0.0)


# ----------------------------------------------------------------------
# Modo 1: coverage_target
# ----------------------------------------------------------------------

def _mode_coverage_target(params: dict) -> dict:
    monthly_essential_expenses = float(params["monthly_essential_expenses"])
    months_of_coverage = float(params["months_of_coverage"])

    target = monthly_essential_expenses * months_of_coverage

    return {
        "monthly_essential_expenses": monthly_essential_expenses,
        "months_of_coverage": months_of_coverage,
        "target_fund": round(target, 2),
    }


# ----------------------------------------------------------------------
# Modo 2: current_coverage_months
# ----------------------------------------------------------------------

def _mode_current_coverage_months(params: dict) -> dict:
    current_savings = float(params["current_savings"])
    monthly_essential_expenses = float(params["monthly_essential_expenses"])

    months_covered = (
        current_savings / monthly_essential_expenses
        if monthly_essential_expenses > 0 else float("inf")
    )

    return {
        "current_savings": current_savings,
        "monthly_essential_expenses": monthly_essential_expenses,
        "months_covered": round(months_covered, 2) if months_covered != float("inf") else None,
    }


# ----------------------------------------------------------------------
# Modo 3: funding_timeline
# ----------------------------------------------------------------------

def _mode_funding_timeline(params: dict) -> dict:
    target = float(params["target"])
    current_savings = float(params.get("current_savings", 0.0))
    monthly_contribution = float(params["monthly_contribution"])
    annual_return = float(params.get("annual_return", 0.0))

    months = _months_to_reach_target(target, current_savings, monthly_contribution, annual_return)

    return {
        "target": target,
        "current_savings": current_savings,
        "monthly_contribution": monthly_contribution,
        "annual_return": annual_return,
        "months_to_reach_target": round(months, 2) if months is not None else None,
        "reachable": months is not None,
    }


# ----------------------------------------------------------------------
# Modo 4: risk_adjusted_target
# ----------------------------------------------------------------------

_RISK_WEIGHTS = {
    "single_income": 2.0,
    "has_dependents": 1.0,
    "unstable_job": 2.0,
    "self_employed": 2.0,
    "no_other_liquid_assets": 1.0,
}


def _mode_risk_adjusted_target(params: dict) -> dict:
    monthly_essential_expenses = float(params["monthly_essential_expenses"])
    base_months = float(params.get("base_months", 3.0))
    risk_factors = params.get("risk_factors", {})

    risk_score = 0.0
    active_factors = []
    for factor, weight in _RISK_WEIGHTS.items():
        if risk_factors.get(factor):
            risk_score += weight
            active_factors.append(factor)

    recommended_months = base_months + risk_score
    recommended_months = max(3.0, min(recommended_months, 12.0))

    target = monthly_essential_expenses * recommended_months

    return {
        "monthly_essential_expenses": monthly_essential_expenses,
        "base_months": base_months,
        "active_risk_factors": active_factors,
        "risk_score": risk_score,
        "recommended_months": recommended_months,
        "target_fund": round(target, 2),
    }


# ----------------------------------------------------------------------
# Validacion
# ----------------------------------------------------------------------

def _mode_validate() -> dict:
    checks = []

    # 1) coverage_target: aritmetica exacta
    ct = _mode_coverage_target({
        "monthly_essential_expenses": 2000.0, "months_of_coverage": 6,
    })
    checks.append({
        "name": "coverage_target_arithmetic_exact",
        "computed": ct["target_fund"],
        "expected": 12000.0,
        "passed": abs(ct["target_fund"] - 12000.0) < 0.01,
    })

    # 2) current_coverage_months: aritmetica exacta
    ccm = _mode_current_coverage_months({
        "current_savings": 9000.0, "monthly_essential_expenses": 1500.0,
    })
    checks.append({
        "name": "current_coverage_months_arithmetic_exact",
        "computed": ccm["months_covered"],
        "expected": 6.0,
        "passed": abs(ccm["months_covered"] - 6.0) < 0.01,
    })

    # 3) funding_timeline: round-trip contra _future_value (con el n calculado,
    #    la FV en meses debe llegar exactamente al target)
    ft = _mode_funding_timeline({
        "target": 15000.0, "current_savings": 2000.0,
        "monthly_contribution": 400.0, "annual_return": 0.04,
    })
    months = ft["months_to_reach_target"]
    fv_check = _future_value(2000.0, 400.0, 0.04, months / 12.0, periods_per_year=12)
    checks.append({
        "name": "funding_timeline_roundtrip_matches_target",
        "target": 15000.0,
        "achieved": round(fv_check, 2),
        "abs_diff": round(abs(fv_check - 15000.0), 2),
        "passed": abs(fv_check - 15000.0) < 5.0,
    })

    # 4) mayor aporte mensual -> menos meses para alcanzar la meta
    ft_low = _mode_funding_timeline({
        "target": 15000.0, "current_savings": 2000.0,
        "monthly_contribution": 200.0, "annual_return": 0.04,
    })["months_to_reach_target"]
    ft_high = _mode_funding_timeline({
        "target": 15000.0, "current_savings": 2000.0,
        "monthly_contribution": 800.0, "annual_return": 0.04,
    })["months_to_reach_target"]
    checks.append({
        "name": "higher_contribution_reduces_months_to_target",
        "months_low_contribution": ft_low,
        "months_high_contribution": ft_high,
        "passed": ft_high < ft_low,
    })

    # 5) funding_timeline: meta inalcanzable con aporte y retorno cero debe dar None
    ft_unreachable = _mode_funding_timeline({
        "target": 15000.0, "current_savings": 2000.0,
        "monthly_contribution": 0.0, "annual_return": 0.0,
    })
    checks.append({
        "name": "unreachable_target_returns_none",
        "reachable": ft_unreachable["reachable"],
        "months_to_reach_target": ft_unreachable["months_to_reach_target"],
        "passed": ft_unreachable["reachable"] is False and ft_unreachable["months_to_reach_target"] is None,
    })

    # 6) risk_adjusted_target: sin factores de riesgo, se queda en el base_months
    rat_low_risk = _mode_risk_adjusted_target({
        "monthly_essential_expenses": 2000.0, "base_months": 3.0, "risk_factors": {},
    })
    checks.append({
        "name": "no_risk_factors_stays_at_base_months",
        "recommended_months": rat_low_risk["recommended_months"],
        "expected": 3.0,
        "passed": abs(rat_low_risk["recommended_months"] - 3.0) < 0.01,
    })

    # 7) risk_adjusted_target: mas factores de riesgo -> mas meses recomendados
    rat_high_risk = _mode_risk_adjusted_target({
        "monthly_essential_expenses": 2000.0, "base_months": 3.0,
        "risk_factors": {
            "single_income": True, "has_dependents": True,
            "unstable_job": True, "self_employed": True,
            "no_other_liquid_assets": True,
        },
    })
    checks.append({
        "name": "more_risk_factors_gives_more_recommended_months",
        "months_low_risk": rat_low_risk["recommended_months"],
        "months_high_risk": rat_high_risk["recommended_months"],
        "passed": rat_high_risk["recommended_months"] > rat_low_risk["recommended_months"],
    })

    # 8) risk_adjusted_target: el tope de 12 meses se respeta aunque el score sea mayor
    checks.append({
        "name": "recommended_months_capped_at_12",
        "recommended_months": rat_high_risk["recommended_months"],
        "passed": rat_high_risk["recommended_months"] <= 12.0,
    })

    validation_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "validation_passed": validation_passed}


# ----------------------------------------------------------------------
# Dispatch principal
# ----------------------------------------------------------------------

def compute_emergency_fund(mode="validate", params=None):
    params = params or {}
    if mode == "coverage_target":
        return _mode_coverage_target(params)
    elif mode == "current_coverage_months":
        return _mode_current_coverage_months(params)
    elif mode == "funding_timeline":
        return _mode_funding_timeline(params)
    elif mode == "risk_adjusted_target":
        return _mode_risk_adjusted_target(params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(
            f"modo desconocido: {mode}. Use coverage_target | current_coverage_months | "
            f"funding_timeline | risk_adjusted_target | validate"
        )


try:
    from tool_registry import register_tool
    register_tool(
        name="emergency_fund_tool",
        schema=EMERGENCY_FUND_TOOL_SCHEMA,
        handler=lambda args: compute_emergency_fund(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    d = compute_emergency_fund("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de emergency_fund_tool.py pasaron OK.")
