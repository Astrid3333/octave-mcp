"""
debt_snowball_tool.py

Simulador de estrategias de pago de multiples deudas: snowball (menor
balance primero) y avalanche (mayor tasa primero), mas comparacion
numerica de ahorro entre ambas.

Motor propio de simulacion mes-a-mes (no reutiliza _amortization_schedule
directamente para el caso multi-deuda, porque el pago extra se
redistribuye dinamicamente entre deudas a medida que se van cerrando --
el "efecto bola de nieve" -- algo que _amortization_schedule, pensada
para una sola deuda, no modela). Si se usa como caso limite con una sola
deuda, el motor propio se valida cruzado contra
credit_simulation_tool._amortization_schedule para confirmar consistencia
matematica.

Estructura de una deuda (dict):
    {"name": str, "balance": float, "apr": float (tasa anual en %,
     ej 19.99), "min_payment": float}
"""

import json

from credit_simulation_tool import _amortization_schedule, _standard_payment

DEBT_SNOWBALL_TOOL_SCHEMA = {
    "name": "debt_snowball_tool",
    "description": (
        "Estrategias de pago de multiples deudas con motor de simulacion mes-a-mes. "
        "Modos: snowball (prioriza pagar primero la deuda de menor balance, aunque "
        "no sea la de mayor tasa -- beneficio psicologico de cerrar deudas rapido), "
        "avalanche (prioriza la deuda de mayor tasa de interes -- matematicamente "
        "optimo para minimizar interes total pagado), compare (corre ambas "
        "estrategias sobre el mismo set de deudas y devuelve el ahorro en interes "
        "y en tiempo de avalanche sobre snowball), validate (autochequeos internos)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["snowball", "avalanche", "compare", "validate"],
            },
            "params": {
                "type": "object",
                "description": (
                    "Para snowball/avalanche/compare: {debts: [{name, balance, apr, "
                    "min_payment}, ...], extra_monthly: float, hard_cap_months?: int "
                    "(default 600)}. No requerido para validate."
                ),
            },
        },
        "required": ["mode"],
    },
}


def _simulate_payoff(debts, extra_monthly, strategy, hard_cap_months=600):
    if strategy not in ("snowball", "avalanche"):
        raise ValueError(f"estrategia desconocida: {strategy}")

    active = []
    for d in debts:
        active.append({
            "name": d["name"],
            "remaining": float(d["balance"]),
            "apr": float(d["apr"]),
            "min_payment": float(d["min_payment"]),
            "total_interest": 0.0,
            "payoff_month": None,
        })

    extra_pool = float(extra_monthly)
    month = 0
    total_interest_all = 0.0
    total_paid_all = 0.0
    payoff_order = []
    hit_hard_cap = False

    while any(d["remaining"] > 1e-2 for d in active):
        month += 1
        if month > hard_cap_months:
            hit_hard_cap = True
            month -= 1
            break

        for d in active:
            if d["remaining"] > 1e-2:
                interest = d["remaining"] * (d["apr"] / 100.0 / 12.0)
                d["remaining"] += interest
                d["total_interest"] += interest
                total_interest_all += interest

        for d in active:
            if d["remaining"] <= 1e-2:
                continue
            pay = min(d["min_payment"], d["remaining"])
            d["remaining"] -= pay
            total_paid_all += pay

        ordering = sorted(
            (d for d in active if d["remaining"] > 1e-2),
            key=(lambda d: d["remaining"]) if strategy == "snowball" else (lambda d: -d["apr"]),
        )
        pool = extra_pool
        for d in ordering:
            if pool <= 1e-9:
                break
            pay = min(pool, d["remaining"])
            d["remaining"] -= pay
            pool -= pay
            total_paid_all += pay

        for d in active:
            if d["remaining"] <= 1e-2 and d["payoff_month"] is None:
                d["remaining"] = 0.0
                d["payoff_month"] = month
                payoff_order.append(d["name"])
                extra_pool += d["min_payment"]

    return {
        "strategy": strategy,
        "months_to_debt_free": month,
        "hit_hard_cap": hit_hard_cap,
        "total_interest_paid": round(total_interest_all, 2),
        "total_paid": round(total_paid_all, 2),
        "payoff_order": payoff_order,
        "debts_detail": [
            {
                "name": d["name"],
                "payoff_month": d["payoff_month"],
                "total_interest": round(d["total_interest"], 2),
            }
            for d in active
        ],
    }


def _mode_snowball(params):
    debts = params["debts"]
    extra_monthly = params.get("extra_monthly", 0.0)
    hard_cap = params.get("hard_cap_months", 600)
    return {"mode": "snowball", **_simulate_payoff(debts, extra_monthly, "snowball", hard_cap)}


def _mode_avalanche(params):
    debts = params["debts"]
    extra_monthly = params.get("extra_monthly", 0.0)
    hard_cap = params.get("hard_cap_months", 600)
    return {"mode": "avalanche", **_simulate_payoff(debts, extra_monthly, "avalanche", hard_cap)}


def _mode_compare(params):
    debts = params["debts"]
    extra_monthly = params.get("extra_monthly", 0.0)
    hard_cap = params.get("hard_cap_months", 600)

    snow = _simulate_payoff(debts, extra_monthly, "snowball", hard_cap)
    aval = _simulate_payoff(debts, extra_monthly, "avalanche", hard_cap)

    interest_saved_by_avalanche = round(
        snow["total_interest_paid"] - aval["total_interest_paid"], 2
    )
    months_saved_by_avalanche = snow["months_to_debt_free"] - aval["months_to_debt_free"]

    if interest_saved_by_avalanche > 0.01:
        recommendation = "avalanche"
        note = (
            "avalanche minimiza el interes total pagado. snowball puede ser "
            "preferible igual si el beneficio psicologico de cerrar deudas "
            "rapido ayuda a mantener la disciplina de pago."
        )
    elif interest_saved_by_avalanche < -0.01:
        recommendation = "snowball"
        note = "caso atipico: snowball resulto con menor interes total que avalanche."
    else:
        recommendation = "equivalente"
        note = "ambas estrategias dan resultados practicamente identicos para este set de deudas."

    return {
        "mode": "compare",
        "snowball": snow,
        "avalanche": aval,
        "interest_saved_by_avalanche": interest_saved_by_avalanche,
        "months_saved_by_avalanche": months_saved_by_avalanche,
        "recommendation": recommendation,
        "note": note,
    }


def _mode_validate():
    checks = []

    principal = 10000.0
    apr = 12.0
    monthly_rate = apr / 100.0 / 12.0
    n_periods = 24
    standard_payment = round(_standard_payment(principal, monthly_rate, n_periods), 2)
    extra = 200.0

    single_debt = [{"name": "solo", "balance": principal, "apr": apr, "min_payment": standard_payment}]
    sim_result = _simulate_payoff(single_debt, extra, "snowball", hard_cap_months=120)

    amort_ref = _amortization_schedule(principal, monthly_rate, n_periods, extra_payment=extra)

    diff = abs(sim_result["total_interest_paid"] - amort_ref["total_interest"])
    checks.append({
        "name": "single_debt_matches_amortization_schedule",
        "sim_interest": sim_result["total_interest_paid"],
        "amort_interest": round(amort_ref["total_interest"], 2),
        "abs_diff": round(diff, 2),
        "passed": diff < 1.0,
    })

    debts_2 = [
        {"name": "A_low_rate", "balance": 1000.0, "apr": 5.0, "min_payment": 25.0},
        {"name": "B_high_rate", "balance": 1000.0, "apr": 25.0, "min_payment": 25.0},
    ]
    snow_2 = _simulate_payoff(debts_2, 200.0, "snowball", hard_cap_months=120)
    aval_2 = _simulate_payoff(debts_2, 200.0, "avalanche", hard_cap_months=120)
    checks.append({
        "name": "avalanche_interest_leq_snowball",
        "snowball_interest": snow_2["total_interest_paid"],
        "avalanche_interest": aval_2["total_interest_paid"],
        "passed": aval_2["total_interest_paid"] <= snow_2["total_interest_paid"] + 1e-6,
    })

    all_zero = (not snow_2["hit_hard_cap"]) and (not aval_2["hit_hard_cap"])
    checks.append({
        "name": "all_debts_reach_zero_no_hard_cap",
        "passed": all_zero,
    })

    debts_3 = [
        {"name": "small", "balance": 500.0, "apr": 10.0, "min_payment": 25.0},
        {"name": "medium", "balance": 1000.0, "apr": 10.0, "min_payment": 25.0},
        {"name": "large", "balance": 1500.0, "apr": 10.0, "min_payment": 25.0},
    ]
    snow_3 = _simulate_payoff(debts_3, 100.0, "snowball", hard_cap_months=120)
    checks.append({
        "name": "snowball_pays_smallest_balance_first",
        "payoff_order": snow_3["payoff_order"],
        "passed": snow_3["payoff_order"][0] == "small",
    })

    debts_4 = [
        {"name": "low_rate", "balance": 1000.0, "apr": 8.0, "min_payment": 25.0},
        {"name": "high_rate", "balance": 1000.0, "apr": 22.0, "min_payment": 25.0},
    ]
    aval_4 = _simulate_payoff(debts_4, 100.0, "avalanche", hard_cap_months=120)
    checks.append({
        "name": "avalanche_pays_highest_rate_first",
        "payoff_order": aval_4["payoff_order"],
        "passed": aval_4["payoff_order"][0] == "high_rate",
    })

    debts_5 = [{"name": "trampa", "balance": 100000.0, "apr": 30.0, "min_payment": 50.0}]
    trapped = _simulate_payoff(debts_5, 0.0, "snowball", hard_cap_months=12)
    checks.append({
        "name": "hard_cap_detected_when_payment_insufficient",
        "hit_hard_cap": trapped["hit_hard_cap"],
        "passed": trapped["hit_hard_cap"] is True,
    })

    validation_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "validation_passed": validation_passed}


def compute_debt_snowball_tool(mode, params=None):
    params = params or {}
    if mode == "snowball":
        return _mode_snowball(params)
    elif mode == "avalanche":
        return _mode_avalanche(params)
    elif mode == "compare":
        return _mode_compare(params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(
            f"modo desconocido: {mode}. Use snowball | avalanche | compare | validate"
        )


try:
    from tool_registry import register_tool
    register_tool(
        name="debt_snowball_tool",
        schema=DEBT_SNOWBALL_TOOL_SCHEMA,
        handler=lambda args: compute_debt_snowball_tool(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    d = compute_debt_snowball_tool("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de debt_snowball_tool.py pasaron OK.")
