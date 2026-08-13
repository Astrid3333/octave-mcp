"""
refinance_analysis_tool.py

Fase D / Tanda 2 — Deudas y Créditos
Compara un crédito actual vs una alternativa refinanciada (nueva tasa y/o
nuevo plazo, con costos de cierre), calcula el breakeven point (en meses),
el ahorro total bajo un horizonte de tenencia dado, y una recomendación
bajo los supuestos dados. Esto es un modelo de decisión financiera, NO
asesoría financiera personalizada real — cada resultado se devuelve con
confidence_flag="model_under_stated_assumptions".

Reutiliza el motor de amortización francesa de credit_simulation_tool.py:
_standard_payment(principal, rate_per_period, n_periods)
_amortization_schedule(principal, rate_per_period, n_periods, extra_payment=0.0)
"""

from __future__ import annotations
import json
import sys
from typing import Optional

try:
    # En el repo real (octave-mcp), este import trae las funciones ya
    # validadas y wireadas de credit_simulation_tool.py.
    from credit_simulation_tool import _standard_payment, _amortization_schedule
except ImportError:
    # Fallback local SOLO para poder correr/validar este archivo de forma
    # aislada (sandbox) cuando credit_simulation_tool.py no está presente
    # en el mismo directorio. En el repo real de Astrid el import de
    # arriba es el que se usa — este bloque nunca debería ejecutarse ahí.
    def _standard_payment(principal, rate_per_period, n_periods):
        if rate_per_period == 0:
            return principal / n_periods
        r = rate_per_period
        return principal * (r * (1 + r) ** n_periods) / ((1 + r) ** n_periods - 1)

    def _amortization_schedule(principal, rate_per_period, n_periods, extra_payment=0.0):
        schedule = []
        balance = principal
        payment = _standard_payment(principal, rate_per_period, n_periods)
        period = 0
        max_periods = int(n_periods) * 4 + 12
        while balance > 1e-4 and period < max_periods:
            period += 1
            interest = balance * rate_per_period
            principal_paid = payment - interest + extra_payment
            if principal_paid > balance:
                principal_paid = balance
            balance -= principal_paid
            schedule.append({
                "period": period,
                "payment": round(payment + extra_payment, 2),
                "interest": round(interest, 2),
                "principal": round(principal_paid, 2),
                "balance": round(max(balance, 0.0), 2),
            })
            if balance <= 1e-4:
                break
        return schedule


MODEL_DISCLAIMER = "model_under_stated_assumptions"


def _total_interest(schedule):
    return sum(p["interest"] for p in schedule)


def _total_paid_over_horizon(schedule, horizon_months):
    """Suma pagos (cuota) de un schedule limitado a horizon_months períodos.
    Si el schedule termina antes del horizonte, no se agregan pagos extra
    (el crédito ya está saldado)."""
    return sum(p["payment"] for p in schedule[:horizon_months])


def _payment_comparison(params):
    principal = float(params["principal"])
    annual_rate_current = float(params["annual_rate_current"])
    remaining_term_months = int(params["remaining_term_months"])
    annual_rate_new = float(params["annual_rate_new"])
    new_term_months = int(params["new_term_months"])
    closing_costs = float(params.get("closing_costs", 0.0))
    roll_closing_costs_into_loan = bool(params.get("roll_closing_costs_into_loan", False))

    r_current = annual_rate_current / 12.0
    r_new = annual_rate_new / 12.0

    current_payment = _standard_payment(principal, r_current, remaining_term_months)
    current_schedule = _amortization_schedule(principal, r_current, remaining_term_months)

    new_principal = principal + closing_costs if roll_closing_costs_into_loan else principal
    new_payment = _standard_payment(new_principal, r_new, new_term_months)
    new_schedule = _amortization_schedule(new_principal, r_new, new_term_months)

    monthly_savings = current_payment - new_payment

    return {
        "current_monthly_payment": round(current_payment, 2),
        "current_total_interest_remaining_term": round(_total_interest(current_schedule), 2),
        "new_monthly_payment": round(new_payment, 2),
        "new_total_interest_full_term": round(_total_interest(new_schedule), 2),
        "new_principal_financed": round(new_principal, 2),
        "monthly_savings": round(monthly_savings, 2),
        "closing_costs": round(closing_costs, 2),
        "closing_costs_rolled_into_loan": roll_closing_costs_into_loan,
        "confidence_flag": MODEL_DISCLAIMER,
    }


def _breakeven_analysis(params):
    if "monthly_savings" in params:
        monthly_savings = float(params["monthly_savings"])
        closing_costs = float(params["closing_costs"])
        payment_detail = None
    else:
        payment_detail = _payment_comparison(params)
        monthly_savings = payment_detail["monthly_savings"]
        closing_costs = float(params.get("closing_costs", 0.0))

    if monthly_savings <= 0:
        result = {
            "breakeven_months": None,
            "breakeven_years": None,
            "reaches_breakeven": False,
            "note": "la cuota nueva no es menor que la actual bajo estos supuestos; no hay breakeven",
        }
    else:
        breakeven_months = closing_costs / monthly_savings
        result = {
            "breakeven_months": round(breakeven_months, 2),
            "breakeven_years": round(breakeven_months / 12.0, 2),
            "reaches_breakeven": True,
            "note": None,
        }

    result["monthly_savings"] = round(monthly_savings, 2)
    result["closing_costs"] = round(closing_costs, 2)
    if payment_detail is not None:
        result["payment_detail"] = payment_detail
    result["confidence_flag"] = MODEL_DISCLAIMER
    return result


def _total_cost_comparison(params):
    principal = float(params["principal"])
    annual_rate_current = float(params["annual_rate_current"])
    remaining_term_months = int(params["remaining_term_months"])
    annual_rate_new = float(params["annual_rate_new"])
    new_term_months = int(params["new_term_months"])
    closing_costs = float(params.get("closing_costs", 0.0))
    roll_closing_costs_into_loan = bool(params.get("roll_closing_costs_into_loan", False))
    horizon_months = int(params.get("horizon_months", max(remaining_term_months, new_term_months)))

    r_current = annual_rate_current / 12.0
    r_new = annual_rate_new / 12.0

    current_schedule = _amortization_schedule(principal, r_current, remaining_term_months)
    new_principal = principal + closing_costs if roll_closing_costs_into_loan else principal
    new_schedule = _amortization_schedule(new_principal, r_new, new_term_months)

    total_cost_current = _total_paid_over_horizon(current_schedule, horizon_months)
    total_cost_new = _total_paid_over_horizon(new_schedule, horizon_months)
    if not roll_closing_costs_into_loan:
        total_cost_new += closing_costs

    return {
        "horizon_months": horizon_months,
        "total_cost_current": round(total_cost_current, 2),
        "total_cost_new": round(total_cost_new, 2),
        "total_savings": round(total_cost_current - total_cost_new, 2),
        "closing_costs_rolled_into_loan": roll_closing_costs_into_loan,
        "confidence_flag": MODEL_DISCLAIMER,
    }


def _refinance_decision(params):
    planned_stay_months = int(params["planned_stay_months"])
    breakeven = _breakeven_analysis(params)
    total_cost = _total_cost_comparison({**params, "horizon_months": planned_stay_months})

    if not breakeven["reaches_breakeven"]:
        recommendation = "no_conviene"
        reason = "la cuota nueva no reduce el pago mensual bajo estos supuestos"
    elif planned_stay_months >= breakeven["breakeven_months"]:
        recommendation = "conviene_refinanciar"
        reason = (
            f"el horizonte de permanencia ({planned_stay_months} meses) supera "
            f"el breakeven ({breakeven['breakeven_months']} meses)"
        )
    else:
        recommendation = "no_conviene"
        reason = (
            f"el horizonte de permanencia ({planned_stay_months} meses) es menor "
            f"al breakeven ({breakeven['breakeven_months']} meses)"
        )

    return {
        "recommendation": recommendation,
        "reason": reason,
        "planned_stay_months": planned_stay_months,
        "breakeven": breakeven,
        "total_cost_comparison": total_cost,
        "confidence_flag": MODEL_DISCLAIMER,
    }


def _validate():
    checks = []

    # Check 1: tasa 0% -> cuota = principal / n_periods (caso analítico exacto)
    p1 = _standard_payment(12000, 0.0, 12)
    checks.append({"name": "zero_rate_payment_exact", "passed": abs(p1 - 1000.0) < 1e-6})

    # Check 2: breakeven analítico simple: closing_costs=3000, monthly_savings=100 -> 30 meses
    b2 = _breakeven_analysis({"monthly_savings": 100.0, "closing_costs": 3000.0})
    checks.append({
        "name": "breakeven_simple_analytic",
        "passed": b2["reaches_breakeven"] and abs(b2["breakeven_months"] - 30.0) < 1e-6,
    })

    # Check 3: monthly_savings <= 0 -> no reaches breakeven, sin division por cero
    b3 = _breakeven_analysis({"monthly_savings": -50.0, "closing_costs": 2000.0})
    checks.append({"name": "breakeven_no_savings_safe", "passed": b3["reaches_breakeven"] is False})

    # Check 4: schedule nuevo amortiza a ~0 exactamente al final del plazo nuevo
    sched4 = _amortization_schedule(200000, 0.05 / 12, 180)
    checks.append({
        "name": "new_loan_fully_amortizes",
        "passed": len(sched4) > 0 and sched4[-1]["balance"] < 1e-2 and len(sched4) == 180,
    })

    # Check 4b: a IGUAL plazo, tasa nueva menor -> cuota nueva estrictamente menor
    # (aislado del efecto de acortar/alargar plazo, que puede compensar o revertir
    # el efecto de la tasa)
    pc4b = _payment_comparison({
        "principal": 200000, "annual_rate_current": 0.07, "remaining_term_months": 180,
        "annual_rate_new": 0.05, "new_term_months": 180, "closing_costs": 4000,
    })
    checks.append({
        "name": "new_rate_lower_gives_lower_payment_same_term",
        "passed": pc4b["new_monthly_payment"] < pc4b["current_monthly_payment"],
    })

    # Check 5: mismos tasa/plazo (sin beneficio real), solo costos de cierre no roleados
    #   -> total_cost_new - total_cost_current debe ser exactamente closing_costs
    tc5 = _total_cost_comparison({
        "principal": 100000, "annual_rate_current": 0.06, "remaining_term_months": 120,
        "annual_rate_new": 0.06, "new_term_months": 120, "closing_costs": 2500,
        "roll_closing_costs_into_loan": False,
    })
    diff5 = tc5["total_cost_new"] - tc5["total_cost_current"]
    checks.append({"name": "identical_terms_cost_diff_equals_closing_costs", "passed": abs(diff5 - 2500.0) < 1.0})

    # Check 6: decision — horizonte largo con breakeven corto debe recomendar refinanciar
    d6 = _refinance_decision({
        "principal": 150000, "annual_rate_current": 0.08, "remaining_term_months": 200,
        "annual_rate_new": 0.045, "new_term_months": 180, "closing_costs": 3000,
        "planned_stay_months": 120,
    })
    checks.append({"name": "long_stay_recommends_refinance", "passed": d6["recommendation"] == "conviene_refinanciar"})

    # Check 7: decision — horizonte muy corto (menor al breakeven) no debe recomendar refinanciar
    d7 = _refinance_decision({
        "principal": 150000, "annual_rate_current": 0.08, "remaining_term_months": 200,
        "annual_rate_new": 0.079, "new_term_months": 200, "closing_costs": 8000,
        "planned_stay_months": 6,
    })
    checks.append({"name": "short_stay_recommends_against", "passed": d7["recommendation"] == "no_conviene"})

    return {
        "mode": "validate",
        "checks": checks,
        "validation_passed": all(c["passed"] for c in checks),
    }


def compute_refinance_analysis_tool(mode: str, params: Optional[dict] = None):
    params = params or {}
    if mode == "validate":
        return _validate()
    elif mode == "payment_comparison":
        return _payment_comparison(params)
    elif mode == "breakeven_analysis":
        return _breakeven_analysis(params)
    elif mode == "total_cost_comparison":
        return _total_cost_comparison(params)
    elif mode == "refinance_decision":
        return _refinance_decision(params)
    else:
        return {
            "error": f"modo desconocido: {mode}",
            "modes_disponibles": [
                "validate", "payment_comparison", "breakeven_analysis",
                "total_cost_comparison", "refinance_decision",
            ],
        }


REFINANCE_ANALYSIS_TOOL_SCHEMA = {
    "name": "refinance_analysis_tool",
    "description": (
        "Compara un credito actual vs una alternativa refinanciada (nueva tasa/plazo, "
        "costos de cierre). Modos: "
        "payment_comparison (cuota actual vs nueva), "
        "breakeven_analysis (meses para recuperar los costos de cierre via el ahorro mensual), "
        "total_cost_comparison (costo total actual vs nuevo bajo un horizonte de meses dado), "
        "refinance_decision (recomendacion conviene/no conviene combinando breakeven y horizonte "
        "de permanencia planeado). Modelo bajo los supuestos dados, no asesoria financiera real."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "validate",
                    "payment_comparison",
                    "breakeven_analysis",
                    "total_cost_comparison",
                    "refinance_decision",
                ],
            },
            "params": {
                "type": "object",
                "description": "Parametros especificos del modo (opcional para validate).",
            },
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    result = compute_refinance_analysis_tool("validate")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["validation_passed"] else 1)
