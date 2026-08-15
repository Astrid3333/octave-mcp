"""
savings_goal_tool.py

Fase D - Contabilidad y Finanzas Personales. Motor de interes compuesto
aplicado a metas de ahorro: valor futuro con aportes periodicos, aporte
requerido para alcanzar una meta, tiempo necesario para alcanzarla, progreso
de una meta en curso, y ajuste de una meta nominal por inflacion.

Este es uno de los motores fundacionales de la Fase D (interes compuesto /
anualidad ordinaria) -- otras tools de la fase (retirement_planner_tool,
education_funding_tool, financial_independence_tool) reutilizan las mismas
formulas cerradas via import directo de las funciones _future_value /
_periods_to_reach / _contribution_for_goal.

Convencion: todas las tasas se piden en TEA (tasa efectiva anual, ej. 0.06 =
6%/anio) y se convierten internamente a tasa por periodo dividiendo por
periods_per_year (aproximacion de tasa nominal periodica, no efectiva
compuesta sub-anual -- suficiente para modelado de planificacion personal).
Los aportes se asumen al final de cada periodo (anualidad ordinaria).

Modos:
  - future_value            : valor futuro de un capital inicial + aportes
    periodicos a una tasa dada, sobre n anios.
  - required_contribution   : aporte periodico necesario para alcanzar una
    meta en un plazo dado.
  - time_to_goal             : cantidad de periodos/anios necesarios para
    alcanzar una meta dado un aporte periodico fijo (forma cerrada via
    logaritmo; si rate=0, formula lineal).
  - goal_progress            : dado el ahorro acumulado actual y un aporte
    mensual fijo, calcula meses restantes y fecha proyectada (delega en
    time_to_goal con principal=ahorro actual).
  - inflation_adjusted_target: ajusta una meta nominal de hoy a su
    equivalente futuro dado un horizonte y una tasa de inflacion esperada.
  - validate                 : corre 6 checks de referencia.

confidence_flag: "alta" para toda la mecanica (formulas cerradas de interes
compuesto, estandar de finanzas personales). Resultado entregado como
"modelo bajo los supuestos dados" -- la tasa de interes/inflacion real futura
es incierta y la provee quien llama, no es una prediccion.

Dependencias: ninguna externa (math estandar).
"""

import math


def _round(x, nd=2):
    return round(float(x), nd)


def _future_value(principal, contribution, rate_per_period, n_periods):
    """FV de anualidad ordinaria (aportes al final del periodo) + capital inicial compuesto."""
    if n_periods < 0:
        raise ValueError("n_periods no puede ser negativo")
    fv_principal = principal * (1.0 + rate_per_period) ** n_periods
    if rate_per_period == 0:
        fv_contrib = contribution * n_periods
    else:
        fv_contrib = contribution * (((1.0 + rate_per_period) ** n_periods - 1.0) / rate_per_period)
    return fv_principal, fv_contrib


def _periods_to_reach(goal, principal, contribution, rate_per_period):
    """Resuelve n tal que future_value(principal, contribution, rate, n) == goal. Forma cerrada."""
    if goal <= principal:
        return 0.0
    if rate_per_period == 0:
        if contribution <= 0:
            raise ValueError("con rate=0 y goal>principal, contribution debe ser > 0")
        return (goal - principal) / contribution
    denom = principal * rate_per_period + contribution
    if denom <= 0:
        raise ValueError("combinacion principal/contribution/rate no converge a la meta (denominador <= 0)")
    x = (goal * rate_per_period + contribution) / denom
    if x <= 0:
        raise ValueError("no hay solucion real para n_periods con estos parametros")
    return math.log(x) / math.log(1.0 + rate_per_period)


def _contribution_for_goal(goal, principal, rate_per_period, n_periods):
    """Resuelve el aporte periodico constante que hace future_value == goal en n_periods dados."""
    if n_periods <= 0:
        raise ValueError("n_periods debe ser > 0")
    fv_principal = principal * (1.0 + rate_per_period) ** n_periods
    remaining = goal - fv_principal
    if rate_per_period == 0:
        return remaining / n_periods
    annuity_factor = ((1.0 + rate_per_period) ** n_periods - 1.0) / rate_per_period
    if annuity_factor <= 0:
        raise ValueError("annuity_factor <= 0, no se puede resolver el aporte")
    return remaining / annuity_factor


def _to_period_rate(annual_rate, periods_per_year):
    return annual_rate / periods_per_year


def _future_value_mode(principal, contribution, annual_rate, n_years, periods_per_year=12):
    r = _to_period_rate(annual_rate, periods_per_year)
    n = n_years * periods_per_year
    fv_principal, fv_contrib = _future_value(principal, contribution, r, n)
    total = fv_principal + fv_contrib
    return {
        "mode": "future_value",
        "principal": _round(principal),
        "contribution_per_period": _round(contribution),
        "annual_rate": annual_rate,
        "periods_per_year": periods_per_year,
        "n_years": n_years,
        "n_periods": n,
        "fv_from_principal": _round(fv_principal),
        "fv_from_contributions": _round(fv_contrib),
        "future_value_total": _round(total),
        "total_contributed": _round(contribution * n),
        "total_interest_earned": _round(total - principal - contribution * n),
        "confidence_flag": "alta",
        "nota": "modelo bajo tasa de interes constante asumida; no es una prediccion de retorno real.",
    }


def _required_contribution_mode(goal_amount, principal, annual_rate, n_years, periods_per_year=12):
    r = _to_period_rate(annual_rate, periods_per_year)
    n = n_years * periods_per_year
    contribution = _contribution_for_goal(goal_amount, principal, r, n)
    return {
        "mode": "required_contribution",
        "goal_amount": _round(goal_amount),
        "principal": _round(principal),
        "annual_rate": annual_rate,
        "periods_per_year": periods_per_year,
        "n_years": n_years,
        "n_periods": n,
        "required_contribution_per_period": _round(contribution),
        "feasible": contribution >= 0,
        "confidence_flag": "alta",
    }


def _time_to_goal_mode(goal_amount, principal, contribution, annual_rate, periods_per_year=12):
    r = _to_period_rate(annual_rate, periods_per_year)
    n_periods = _periods_to_reach(goal_amount, principal, contribution, r)
    return {
        "mode": "time_to_goal",
        "goal_amount": _round(goal_amount),
        "principal": _round(principal),
        "contribution_per_period": _round(contribution),
        "annual_rate": annual_rate,
        "periods_per_year": periods_per_year,
        "n_periods_needed": _round(n_periods, 3),
        "n_years_needed": _round(n_periods / periods_per_year, 3),
        "confidence_flag": "alta",
    }


def _goal_progress_mode(current_savings, monthly_contribution, annual_rate, goal_amount):
    r = _to_period_rate(annual_rate, 12)
    n_months = _periods_to_reach(goal_amount, current_savings, monthly_contribution, r)
    pct_of_goal = current_savings / goal_amount if goal_amount > 0 else None
    return {
        "mode": "goal_progress",
        "current_savings": _round(current_savings),
        "goal_amount": _round(goal_amount),
        "pct_of_goal_reached": _round(pct_of_goal * 100, 2) if pct_of_goal is not None else None,
        "monthly_contribution": _round(monthly_contribution),
        "annual_rate": annual_rate,
        "months_remaining": _round(n_months, 2),
        "years_remaining": _round(n_months / 12, 2),
        "confidence_flag": "alta",
    }


def _inflation_adjusted_target_mode(nominal_goal_today, years, expected_inflation_rate):
    future_nominal = nominal_goal_today * (1.0 + expected_inflation_rate) ** years
    return {
        "mode": "inflation_adjusted_target",
        "nominal_goal_today": _round(nominal_goal_today),
        "years": years,
        "expected_inflation_rate": expected_inflation_rate,
        "future_nominal_target": _round(future_nominal),
        "purchasing_power_erosion_pct": _round((1 - nominal_goal_today / future_nominal) * 100, 2),
        "confidence_flag": "alta",
        "nota": "inflacion futura es un supuesto de quien llama, no una proyeccion; usar un rango de escenarios si hay incertidumbre.",
    }


def _validate():
    checks = []

    # 1) future_value: solo capital, sin aportes -> compuesto simple vs analitica
    r1 = _future_value_mode(1000.0, 0.0, 0.10, 1, periods_per_year=1)
    expected_1 = 1000.0 * 1.10
    checks.append({"name": "fv_principal_only_compound", "passed": bool(abs(r1["future_value_total"] - expected_1) < 1e-6)})

    # 2) future_value: rate=0, solo aportes -> lineal
    r2 = _future_value_mode(0.0, 100.0, 0.0, 1, periods_per_year=12)
    expected_2 = 100.0 * 12
    checks.append({"name": "fv_rate_zero_linear", "passed": bool(abs(r2["future_value_total"] - expected_2) < 1e-6)})

    # 3) required_contribution: inversa de future_value (el aporte calculado debe reproducir la meta)
    goal = 50000.0
    rc = _required_contribution_mode(goal, 5000.0, 0.06, 10, periods_per_year=12)
    check_fv = _future_value_mode(5000.0, rc["required_contribution_per_period"], 0.06, 10, periods_per_year=12)
    checks.append({"name": "required_contribution_inverse_consistent", "passed": bool(abs(check_fv["future_value_total"] - goal) < 1.0)})

    # 4) time_to_goal: inversa de future_value (n calculado debe reproducir la meta aprox)
    tt = _time_to_goal_mode(20000.0, 1000.0, 200.0, 0.05, periods_per_year=12)
    n_check = round(tt["n_periods_needed"])
    fv_check = _future_value_mode(1000.0, 200.0, 0.05, n_check / 12, periods_per_year=12)
    checks.append({"name": "time_to_goal_inverse_consistent", "passed": bool(abs(fv_check["future_value_total"] - 20000.0) < 200.0)})

    # 5) goal_progress: consistente con time_to_goal (mismo problema, mismo resultado)
    gp = _goal_progress_mode(1000.0, 200.0, 0.05, 20000.0)
    checks.append({"name": "goal_progress_matches_time_to_goal", "passed": bool(abs(gp["months_remaining"] - tt["n_periods_needed"]) < 0.01)})

    # 6) inflation_adjusted_target: caso conocido, 2% anual x 10 anios sobre 1000 -> 1000*1.02^10
    ia = _inflation_adjusted_target_mode(1000.0, 10, 0.02)
    expected_6 = 1000.0 * (1.02 ** 10)
    checks.append({"name": "inflation_adjusted_known_case", "passed": bool(abs(ia["future_nominal_target"] - expected_6) < 0.5)})

    passed_all = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "validation_passed": bool(passed_all)}


def compute_savings_goal_tool(mode="validate", params=None):
    params = params or {}
    if mode == "future_value":
        return _future_value_mode(
            params.get("principal", 0.0), params.get("contribution", 0.0),
            params["annual_rate"], params["n_years"], params.get("periods_per_year", 12),
        )
    elif mode == "required_contribution":
        return _required_contribution_mode(
            params["goal_amount"], params.get("principal", 0.0),
            params["annual_rate"], params["n_years"], params.get("periods_per_year", 12),
        )
    elif mode == "time_to_goal":
        return _time_to_goal_mode(
            params["goal_amount"], params.get("principal", 0.0), params["contribution"],
            params["annual_rate"], params.get("periods_per_year", 12),
        )
    elif mode == "goal_progress":
        return _goal_progress_mode(
            params["current_savings"], params["monthly_contribution"],
            params["annual_rate"], params["goal_amount"],
        )
    elif mode == "inflation_adjusted_target":
        return _inflation_adjusted_target_mode(
            params["nominal_goal_today"], params["years"], params["expected_inflation_rate"],
        )
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"mode desconocido: {mode}")


SAVINGS_GOAL_TOOL_SCHEMA = {
    "name": "savings_goal_tool",
    "description": (
        "Motor de interes compuesto para metas de ahorro (anualidad ordinaria, aportes a fin de "
        "periodo): future_value (valor futuro de capital inicial + aportes periodicos), "
        "required_contribution (aporte periodico necesario para alcanzar una meta en un plazo "
        "dado), time_to_goal (periodos necesarios para alcanzar una meta con aporte fijo, forma "
        "cerrada via logaritmo), goal_progress (meses restantes dado el ahorro acumulado actual y "
        "un aporte mensual fijo), inflation_adjusted_target (ajusta una meta nominal de hoy a su "
        "equivalente futuro bajo una tasa de inflacion esperada). Motor fundacional de la Fase D: "
        "retirement_planner_tool/education_funding_tool/financial_independence_tool reutilizan las "
        "mismas formulas cerradas. confidence_flag 'alta' para la mecanica (formulas estandar de "
        "interes compuesto); la tasa de interes/inflacion futura es un supuesto de quien llama, no "
        "una prediccion. validate corre 6 checks de referencia."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["future_value", "required_contribution", "time_to_goal", "goal_progress", "inflation_adjusted_target", "validate"],
                "default": "validate",
            },
            "params": {
                "type": "object",
                "description": (
                    "future_value: {principal, contribution, annual_rate, n_years, periods_per_year=12}. "
                    "required_contribution: {goal_amount, principal, annual_rate, n_years, periods_per_year=12}. "
                    "time_to_goal: {goal_amount, principal, contribution, annual_rate, periods_per_year=12}. "
                    "goal_progress: {current_savings, monthly_contribution, annual_rate, goal_amount}. "
                    "inflation_adjusted_target: {nominal_goal_today, years, expected_inflation_rate}."
                ),
            },
        },
        "required": ["mode"],
    },
}


try:
    from tool_registry import register_tool
    register_tool(
        name="savings_goal_tool",
        schema=SAVINGS_GOAL_TOOL_SCHEMA,
        handler=lambda args: compute_savings_goal_tool(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    print(json.dumps(compute_savings_goal_tool("validate"), indent=2, ensure_ascii=False))
