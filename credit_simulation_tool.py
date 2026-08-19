"""
credit_simulation_tool.py

Fase D - Contabilidad y Finanzas Personales. Motor de amortizacion de
creditos: calculo de cuota estandar, tabla de amortizacion (frances,
cuota fija), impacto de pagos extra sobre plazo/interes, pago minimo de
tarjeta de credito (deteccion de "trampa del pago minimo"), y chequeo de
capacidad de pago (DTI).

Este es el motor fundacional de amortizacion de la Fase D -- debt_snowball_tool
y refinance_analysis_tool importan directamente _standard_payment y
_amortization_schedule en vez de reimplementar la formula.

Convencion: tasas se piden en TEA (tasa efectiva anual) y se convierten a
tasa por periodo dividiendo por periods_per_year (tasa nominal periodica,
no efectiva compuesta sub-anual -- consistente con savings_goal_tool).

Modos:
  - payment_calculator   : cuota fija (sistema frances) para un credito,
    total pagado, total interes.
  - amortization_schedule : tabla de amortizacion. detail='summary' (default)
    agrega por anio; detail='full' devuelve cuota a cuota (limitado a 120
    periodos para no inundar la respuesta -- si el plazo es mayor, se fuerza
    resumen anual con una nota).
  - extra_payment_impact  : compara el credito base contra el mismo credito
    con un pago extra fijo por periodo y/o un abono unico (lump sum) en un
    mes dado -- meses ahorrados, interes ahorrado.
  - credit_card_payoff    : saldo revolvente con pago minimo (% del saldo,
    tipico 2-4%) o pago fijo -- meses hasta saldar, interes total, y
    deteccion de "trampa del pago minimo" (no converge en un plazo razonable
    o el interes total excede el capital).
  - affordability_check   : DTI (debt-to-income) front-end/back-end dado
    ingreso bruto, deuda existente y la cuota propuesta -- clasificacion
    descriptiva por banda (heuristica 28/36), no una aprobacion de credito.
  - validate               : corre 5 checks de referencia.

confidence_flag: "alta" para toda la mecanica de amortizacion (sistema
frances es formula cerrada estandar). credit_card_payoff usa iteracion
numerica simple (no hay forma cerrada trivial con pago-minimo-como-%-del-
saldo-decreciente), confidence_flag 'alta' igual porque es aritmetica
determinista, no estimacion estadistica. Resultado entregado como "modelo
bajo los supuestos dados", no asesoria financiera ni oferta de credito.

Dependencias: ninguna externa (aritmetica pura).
"""


def _round(x, nd=2):
    return round(float(x), nd)


def _standard_payment(principal, rate_per_period, n_periods):
    """Cuota fija sistema frances. rate_per_period=0 -> amortizacion lineal simple."""
    if n_periods <= 0:
        raise ValueError("n_periods debe ser > 0")
    if principal < 0:
        raise ValueError("principal no puede ser negativo")
    if rate_per_period == 0:
        return principal / n_periods
    return principal * rate_per_period / (1.0 - (1.0 + rate_per_period) ** (-n_periods))


def _amortization_schedule(principal, rate_per_period, n_periods, extra_payment=0.0,
                            extra_lump_sum=0.0, extra_lump_month=None, hard_cap_periods=1200):
    """
    Genera la tabla completa de amortizacion. Si extra_payment>0, cada cuota aplica ese
    monto adicional a capital (acorta el plazo). extra_lump_sum se aplica una unica vez
    en extra_lump_month (si se especifica). hard_cap_periods evita loops infinitos si
    los parametros no convergen.
    """
    base_payment = _standard_payment(principal, rate_per_period, n_periods)
    balance = principal
    schedule = []
    period = 0
    total_interest = 0.0

    close_threshold = 1e-4  # residuo de punto flotante, muy por debajo de la unidad monetaria minima
    while balance > close_threshold and period < hard_cap_periods:
        period += 1
        interest = balance * rate_per_period
        principal_payment = base_payment - interest + extra_payment
        lump_this_period = extra_lump_sum if (extra_lump_month is not None and period == extra_lump_month) else 0.0
        principal_payment += lump_this_period
        if principal_payment > balance:
            principal_payment = balance
        balance -= principal_payment
        total_interest += interest
        schedule.append({
            "period": period,
            "payment": _round(interest + principal_payment),
            "interest": _round(interest),
            "principal_payment": _round(principal_payment),
            "balance": _round(max(balance, 0.0)),
        })
        if balance <= close_threshold:
            break

    return {
        "scheduled_payment": _round(base_payment),
        "n_periods_actual": period,
        "total_interest": _round(total_interest),
        "total_paid": _round(principal + total_interest),
        "schedule": schedule,
        "hit_hard_cap": period >= hard_cap_periods,
    }


def _annual_summary_from_schedule(schedule, periods_per_year=12):
    summary = []
    year = 1
    interest_acc = 0.0
    principal_acc = 0.0
    for i, row in enumerate(schedule, start=1):
        interest_acc += row["interest"]
        principal_acc += row["principal_payment"]
        if i % periods_per_year == 0 or i == len(schedule):
            summary.append({
                "year": year,
                "interest_paid": _round(interest_acc),
                "principal_paid": _round(principal_acc),
                "ending_balance": row["balance"],
            })
            year += 1
            interest_acc = 0.0
            principal_acc = 0.0
    return summary


def _payment_calculator_mode(principal, annual_rate, term_months):
    r = annual_rate / 12.0
    payment = _standard_payment(principal, r, term_months)
    total_paid = payment * term_months
    return {
        "mode": "payment_calculator",
        "principal": _round(principal),
        "annual_rate": annual_rate,
        "term_months": term_months,
        "monthly_payment": _round(payment),
        "total_paid": _round(total_paid),
        "total_interest": _round(total_paid - principal),
        "confidence_flag": "alta",
    }


def _amortization_schedule_mode(principal, annual_rate, term_months, extra_payment=0.0, detail="summary"):
    r = annual_rate / 12.0
    result = _amortization_schedule(principal, r, term_months, extra_payment=extra_payment)
    out = {
        "mode": "amortization_schedule",
        "principal": _round(principal),
        "annual_rate": annual_rate,
        "term_months": term_months,
        "extra_payment": _round(extra_payment),
        "monthly_payment": result["scheduled_payment"],
        "n_periods_actual": result["n_periods_actual"],
        "total_interest": result["total_interest"],
        "total_paid": result["total_paid"],
        "confidence_flag": "alta",
    }
    if detail == "full" and result["n_periods_actual"] <= 120:
        out["schedule"] = result["schedule"]
    else:
        out["annual_summary"] = _annual_summary_from_schedule(result["schedule"])
        if detail == "full":
            out["nota"] = f"plazo de {result['n_periods_actual']} periodos excede el limite de detalle completo (120); se devuelve resumen anual."
    return out


def _extra_payment_impact_mode(principal, annual_rate, term_months, extra_payment=0.0,
                                lump_sum=0.0, lump_month=None):
    r = annual_rate / 12.0
    baseline = _amortization_schedule(principal, r, term_months)
    with_extra = _amortization_schedule(
        principal, r, term_months, extra_payment=extra_payment,
        extra_lump_sum=lump_sum, extra_lump_month=lump_month,
    )
    return {
        "mode": "extra_payment_impact",
        "principal": _round(principal),
        "annual_rate": annual_rate,
        "term_months": term_months,
        "extra_payment_per_month": _round(extra_payment),
        "lump_sum": _round(lump_sum),
        "lump_sum_month": lump_month,
        "baseline": {
            "monthly_payment": baseline["scheduled_payment"],
            "n_periods": baseline["n_periods_actual"],
            "total_interest": baseline["total_interest"],
        },
        "with_extra_payment": {
            "n_periods": with_extra["n_periods_actual"],
            "total_interest": with_extra["total_interest"],
        },
        "months_saved": baseline["n_periods_actual"] - with_extra["n_periods_actual"],
        "interest_saved": _round(baseline["total_interest"] - with_extra["total_interest"]),
        "confidence_flag": "alta",
    }


def _credit_card_payoff_mode(balance, apr, min_payment_pct=None, fixed_payment=None,
                              min_payment_floor=25.0, max_months=600):
    if (min_payment_pct is None) == (fixed_payment is None):
        raise ValueError("especificar exactamente uno de min_payment_pct o fixed_payment")
    r = apr / 12.0
    bal = balance
    month = 0
    total_interest = 0.0
    total_paid = 0.0
    schedule_sample = []

    while bal > 1e-6 and month < max_months:
        month += 1
        interest = bal * r
        if min_payment_pct is not None:
            payment = max(bal * min_payment_pct, min_payment_floor)
        else:
            payment = fixed_payment
        payment = min(payment, bal + interest)
        principal_payment = payment - interest
        if principal_payment <= 0:
            # el pago no alcanza a cubrir ni el interes -> trampa, no converge
            month = max_months
            break
        bal -= principal_payment
        total_interest += interest
        total_paid += payment
        if month <= 6 or month % 12 == 0:
            schedule_sample.append({"month": month, "payment": _round(payment), "interest": _round(interest), "balance": _round(max(bal, 0.0))})

    trapped = month >= max_months and bal > 1e-6
    return {
        "mode": "credit_card_payoff",
        "starting_balance": _round(balance),
        "apr": apr,
        "min_payment_pct": min_payment_pct,
        "fixed_payment": fixed_payment,
        "months_to_payoff": None if trapped else month,
        "years_to_payoff": None if trapped else _round(month / 12, 2),
        "total_interest_paid": None if trapped else _round(total_interest),
        "total_paid": None if trapped else _round(total_paid),
        "interest_exceeds_principal": (not trapped) and total_interest > balance,
        "minimum_payment_trap": trapped,
        "schedule_sample": schedule_sample,
        "confidence_flag": "alta",
        "nota": (
            "pago minimo como % de saldo decreciente puede tardar decadas y pagar varias veces "
            "el capital en interes -- revisar minimum_payment_trap e interest_exceeds_principal."
        ),
    }


def _affordability_check_mode(gross_monthly_income, existing_monthly_debt, proposed_payment):
    if gross_monthly_income <= 0:
        raise ValueError("gross_monthly_income debe ser > 0")
    front_end = proposed_payment / gross_monthly_income
    back_end = (existing_monthly_debt + proposed_payment) / gross_monthly_income

    if back_end <= 0.28:
        band = "conservador (<=28%)"
    elif back_end <= 0.36:
        band = "dentro de rango convencional (28-36%)"
    elif back_end <= 0.43:
        band = "elevado (36-43%), aceptado por algunos prestamistas segun otros factores"
    else:
        band = "alto (>43%), fuera del rango convencional tipico"

    return {
        "mode": "affordability_check",
        "gross_monthly_income": _round(gross_monthly_income),
        "existing_monthly_debt": _round(existing_monthly_debt),
        "proposed_payment": _round(proposed_payment),
        "front_end_dti_pct": _round(front_end * 100, 2),
        "back_end_dti_pct": _round(back_end * 100, 2),
        "classification": band,
        "confidence_flag": "alta",
        "nota": "heuristica de mercado (regla 28/36), no un criterio de aprobacion real de ningun prestamista.",
    }


def _validate():
    checks = []

    # 1) payment_calculator: caso de referencia conocido, credito hipotecario tipico
    #    P=100000, i=6%/12=0.5%, n=360 -> cuota ~= 599.55
    r1 = _payment_calculator_mode(100000.0, 0.06, 360)
    checks.append({"name": "payment_calculator_known_case", "passed": bool(abs(r1["monthly_payment"] - 599.55) < 0.5)})

    # 2) amortization_schedule: el saldo final del schedule completo debe llegar a ~0
    r2 = _amortization_schedule_mode(10000.0, 0.08, 24, detail="full")
    last_balance = r2["schedule"][-1]["balance"]
    checks.append({"name": "amortization_ends_at_zero_balance", "passed": bool(abs(last_balance) < 1.0)})

    # 3) extra_payment_impact: pago extra siempre debe reducir plazo e interes
    r3 = _extra_payment_impact_mode(20000.0, 0.10, 60, extra_payment=100.0)
    checks.append({"name": "extra_payment_reduces_term_and_interest", "passed": bool(r3["months_saved"] > 0 and r3["interest_saved"] > 0)})

    # 4) credit_card_payoff: pago minimo bajo (2%) en saldo alto/APR alto debe tardar mucho mas
    #    que un pago fijo generoso -- comparacion relativa, no valor absoluto fijo
    r4a = _credit_card_payoff_mode(5000.0, 0.24, min_payment_pct=0.02)
    r4b = _credit_card_payoff_mode(5000.0, 0.24, fixed_payment=300.0)
    months_a = r4a["months_to_payoff"] or 10 ** 6
    months_b = r4b["months_to_payoff"] or 10 ** 6
    checks.append({"name": "credit_card_min_payment_slower_than_fixed", "passed": bool(months_a > months_b)})

    # 5) affordability_check: aritmetica DTI directa (30% back-end esperado)
    r5 = _affordability_check_mode(5000.0, 500.0, 1000.0)
    checks.append({"name": "affordability_dti_arithmetic", "passed": bool(abs(r5["back_end_dti_pct"] - 30.0) < 1e-6)})

    passed_all = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "validation_passed": bool(passed_all)}


def compute_credit_simulation_tool(mode="validate", params=None):
    params = params or {}
    if mode == "payment_calculator":
        return _payment_calculator_mode(params["principal"], params["annual_rate"], params["term_months"])
    elif mode == "amortization_schedule":
        return _amortization_schedule_mode(
            params["principal"], params["annual_rate"], params["term_months"],
            params.get("extra_payment", 0.0), params.get("detail", "summary"),
        )
    elif mode == "extra_payment_impact":
        return _extra_payment_impact_mode(
            params["principal"], params["annual_rate"], params["term_months"],
            params.get("extra_payment", 0.0), params.get("lump_sum", 0.0), params.get("lump_month"),
        )
    elif mode == "credit_card_payoff":
        return _credit_card_payoff_mode(
            params["balance"], params["apr"], params.get("min_payment_pct"),
            params.get("fixed_payment"), params.get("min_payment_floor", 25.0), params.get("max_months", 600),
        )
    elif mode == "affordability_check":
        return _affordability_check_mode(
            params["gross_monthly_income"], params["existing_monthly_debt"], params["proposed_payment"],
        )
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"mode desconocido: {mode}")


CREDIT_SIMULATION_TOOL_SCHEMA = {
    "name": "credit_simulation_tool",
    "description": (
        "Motor de amortizacion de creditos (sistema frances, cuota fija): payment_calculator "
        "(cuota mensual, total pagado, total interes), amortization_schedule (tabla de "
        "amortizacion, detail='summary' agrega por anio o 'full' cuota a cuota hasta 120 "
        "periodos), extra_payment_impact (compara credito base vs con pago extra mensual y/o "
        "abono unico -- meses e interes ahorrados), credit_card_payoff (saldo revolvente con "
        "pago minimo %-del-saldo o pago fijo, detecta 'trampa del pago minimo' e interes que "
        "excede el capital), affordability_check (DTI front-end/back-end vs heuristica 28/36, "
        "clasificacion descriptiva). Motor fundacional de la Fase D: debt_snowball_tool y "
        "refinance_analysis_tool importan directamente _standard_payment y "
        "_amortization_schedule de este modulo. confidence_flag 'alta' (formulas cerradas "
        "estandar o iteracion aritmetica determinista). No es asesoria financiera ni oferta de "
        "credito real. validate corre 5 checks de referencia."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["payment_calculator", "amortization_schedule", "extra_payment_impact", "credit_card_payoff", "affordability_check", "validate"],
                "default": "validate",
            },
            "params": {
                "type": "object",
                "description": (
                    "payment_calculator: {principal, annual_rate, term_months}. "
                    "amortization_schedule: {principal, annual_rate, term_months, extra_payment=0, detail='summary'|'full'}. "
                    "extra_payment_impact: {principal, annual_rate, term_months, extra_payment=0, lump_sum=0, lump_month}. "
                    "credit_card_payoff: {balance, apr, min_payment_pct XOR fixed_payment, min_payment_floor=25, max_months=600}. "
                    "affordability_check: {gross_monthly_income, existing_monthly_debt, proposed_payment}."
                ),
            },
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_credit_simulation_tool("validate"), indent=2, ensure_ascii=False))

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("credit_simulation_tool", CREDIT_SIMULATION_TOOL_SCHEMA, lambda args, _f=compute_credit_simulation_tool: _f(**args))
