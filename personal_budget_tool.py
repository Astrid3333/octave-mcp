"""
personal_budget_tool.py

Fase D - Contabilidad y Finanzas Personales. Presupuesto personal/domestico:
balance ingreso-gasto, categorizacion vs benchmark tipo 50/30/20 (o uno
custom), split gasto fijo/variable, y asignacion de presupuesto base-cero
por categorias.

Modos:
  - income_expense_balance : ingreso total vs gastos por categoria -> balance,
    tasa de ahorro, breakdown porcentual por categoria (ordenado desc).
  - category_benchmark      : compara el gasto real por tipo (necesidad/deseo/
    ahorro) contra un benchmark de referencia (50/30/20 por defecto, o uno
    custom que sume 1.0), marca desvios en puntos porcentuales.
  - fixed_variable_split    : separa gastos fijos vs variables, calcula
    ratio de compromiso fijo sobre el ingreso (si se provee income).
  - zero_based_allocation   : presupuesto base-cero: dado ingreso total y
    categorias con % objetivo, asigna montos y verifica que la suma cierre
    en 100% (tolerancia configurable en puntos porcentuales).
  - validate                : corre 6 checks de referencia.

confidence_flag: "alta" para toda la mecanica (sumas y porcentajes cerrados,
sin estimacion estadistica de por medio). Los benchmarks (ej. 50/30/20) son
heuristicas de referencia, no normas universales -- el resultado se entrega
como "modelo bajo los supuestos dados", no como asesoria financiera
personalizada.

Dependencias: ninguna externa (aritmetica pura).
"""


def _round(x, nd=2):
    return round(float(x), nd)


def _income_expense_balance(income, expenses):
    """
    income: numero (ingreso total del periodo) o lista de {"source", "amount"}.
    expenses: lista de {"category", "amount"}.
    """
    if isinstance(income, (list, tuple)):
        income_breakdown = [{"source": s.get("source", ""), "amount": _round(s["amount"])} for s in income]
        total_income = sum(s["amount"] for s in income)
    else:
        income_breakdown = None
        total_income = float(income)

    if not expenses:
        raise ValueError("expenses no puede estar vacio")

    total_expenses = sum(e["amount"] for e in expenses)
    balance = total_income - total_expenses
    savings_rate = balance / total_income if total_income > 0 else None

    breakdown = []
    for e in expenses:
        pct = e["amount"] / total_expenses if total_expenses > 0 else 0.0
        breakdown.append({
            "category": e.get("category", ""),
            "amount": _round(e["amount"]),
            "pct_of_expenses": _round(pct * 100, 2),
        })
    breakdown.sort(key=lambda b: -b["amount"])

    return {
        "mode": "income_expense_balance",
        "total_income": _round(total_income),
        "income_breakdown": income_breakdown,
        "total_expenses": _round(total_expenses),
        "balance": _round(balance),
        "savings_rate_pct": _round(savings_rate * 100, 2) if savings_rate is not None else None,
        "status": "superavit" if balance > 0 else ("deficit" if balance < 0 else "equilibrio"),
        "expense_breakdown": breakdown,
        "confidence_flag": "alta",
    }


def _category_benchmark(expenses, total_income, benchmark=None):
    """
    expenses: lista de {"category", "amount", "type": "necesidad"|"deseo"|"ahorro" (o claves del benchmark)}.
    benchmark: dict opcional {tipo: fraccion 0-1}; default regla 50/30/20.
    """
    benchmark = benchmark or {"necesidad": 0.50, "deseo": 0.30, "ahorro": 0.20}
    if abs(sum(benchmark.values()) - 1.0) > 1e-6:
        raise ValueError(f"benchmark debe sumar 1.0, suma actual = {sum(benchmark.values())}")

    totals = {}
    for e in expenses:
        t = e.get("type")
        if t not in benchmark:
            raise ValueError(f"type desconocido en expense: {t!r}. Debe estar en benchmark: {list(benchmark)}")
        totals[t] = totals.get(t, 0.0) + e["amount"]

    total_categorized = sum(totals.values())
    rows = []
    for t, target_pct in benchmark.items():
        actual = totals.get(t, 0.0)
        actual_pct = actual / total_income if total_income > 0 else 0.0
        rows.append({
            "type": t,
            "actual_amount": _round(actual),
            "actual_pct_of_income": _round(actual_pct * 100, 2),
            "target_pct_of_income": _round(target_pct * 100, 2),
            "deviation_pp": _round((actual_pct - target_pct) * 100, 2),
            "over_target": actual_pct > target_pct + 1e-9,
        })

    return {
        "mode": "category_benchmark",
        "total_income": _round(total_income),
        "total_categorized": _round(total_categorized),
        "uncategorized_income_pct": _round((1 - total_categorized / total_income) * 100, 2) if total_income > 0 else None,
        "benchmark_used": benchmark,
        "rows": rows,
        "confidence_flag": "alta",
        "nota": "benchmark es una heuristica de referencia (ej. regla 50/30/20), no una norma universal.",
    }


def _fixed_variable_split(expenses, income=None):
    fixed = sum(e["amount"] for e in expenses if e.get("type") == "fixed")
    variable = sum(e["amount"] for e in expenses if e.get("type") == "variable")
    other = sum(e["amount"] for e in expenses if e.get("type") not in ("fixed", "variable"))
    total = fixed + variable + other

    result = {
        "mode": "fixed_variable_split",
        "fixed_total": _round(fixed),
        "variable_total": _round(variable),
        "other_untyped_total": _round(other),
        "total_expenses": _round(total),
        "fixed_ratio_of_expenses_pct": _round(fixed / total * 100, 2) if total > 0 else None,
        "variable_ratio_of_expenses_pct": _round(variable / total * 100, 2) if total > 0 else None,
        "confidence_flag": "alta",
    }
    if income is not None and income > 0:
        fixed_to_income = fixed / income
        result["fixed_to_income_ratio_pct"] = _round(fixed_to_income * 100, 2)
        result["nota_compromiso_fijo"] = (
            "gasto fijo > 50% del ingreso suele considerarse compromiso alto (heuristica, no regla estricta)"
            if fixed_to_income > 0.5 else None
        )
    return result


def _zero_based_allocation(total_income, categories, tolerance_pct=0.5):
    """categories: lista de {"name", "target_pct"} (fraccion 0-1)."""
    if not categories:
        raise ValueError("categories no puede estar vacio")
    total_pct = sum(c["target_pct"] for c in categories)
    diff_pct = (total_pct - 1.0) * 100

    rows = []
    for c in categories:
        amount = total_income * c["target_pct"]
        rows.append({
            "name": c["name"],
            "target_pct": _round(c["target_pct"] * 100, 2),
            "allocated_amount": _round(amount),
        })
    allocated_total = sum(r["allocated_amount"] for r in rows)

    return {
        "mode": "zero_based_allocation",
        "total_income": _round(total_income),
        "categories": rows,
        "allocated_total": _round(allocated_total),
        "unallocated_amount": _round(total_income - allocated_total),
        "sum_target_pct": _round(total_pct * 100, 2),
        "closes_at_100pct": abs(diff_pct) <= tolerance_pct,
        "deviation_pp": _round(diff_pct, 2),
        "confidence_flag": "alta",
    }


def _validate():
    checks = []

    # 1) income_expense_balance: superavit claro
    r1 = _income_expense_balance(1000.0, [{"category": "arriendo", "amount": 400}, {"category": "comida", "amount": 300}])
    checks.append({"name": "balance_superavit", "passed": bool(abs(r1["balance"] - 300.0) < 1e-6 and r1["status"] == "superavit")})

    # 2) income_expense_balance: deficit
    r2 = _income_expense_balance(500.0, [{"category": "arriendo", "amount": 400}, {"category": "comida", "amount": 300}])
    checks.append({"name": "balance_deficit", "passed": bool(r2["status"] == "deficit" and r2["balance"] < 0)})

    # 3) category_benchmark: gasto exactamente 50/30/20 -> desviacion cero en las 3 filas
    exp = [
        {"category": "a", "amount": 500, "type": "necesidad"},
        {"category": "b", "amount": 300, "type": "deseo"},
        {"category": "c", "amount": 200, "type": "ahorro"},
    ]
    r3 = _category_benchmark(exp, 1000.0)
    checks.append({"name": "benchmark_50_30_20_exact", "passed": bool(all(row["deviation_pp"] == 0.0 for row in r3["rows"]))})

    # 4) fixed_variable_split: ratio conocido (400 fijo / 500 total = 80%)
    exp2 = [{"category": "arriendo", "amount": 400, "type": "fixed"}, {"category": "salidas", "amount": 100, "type": "variable"}]
    r4 = _fixed_variable_split(exp2, income=1000.0)
    checks.append({"name": "fixed_variable_split_ratio", "passed": bool(abs(r4["fixed_ratio_of_expenses_pct"] - 80.0) < 1e-6)})

    # 5) zero_based_allocation: cierra en 100%
    cats = [{"name": "necesidad", "target_pct": 0.5}, {"name": "deseo", "target_pct": 0.3}, {"name": "ahorro", "target_pct": 0.2}]
    r5 = _zero_based_allocation(2000.0, cats)
    checks.append({"name": "zero_based_closes", "passed": bool(r5["closes_at_100pct"] and abs(r5["unallocated_amount"]) < 1e-6)})

    # 6) zero_based_allocation: gap detectado (categorias que no suman 100%)
    cats_bad = [{"name": "a", "target_pct": 0.5}, {"name": "b", "target_pct": 0.3}]
    r6 = _zero_based_allocation(2000.0, cats_bad)
    checks.append({"name": "zero_based_detects_gap", "passed": bool((not r6["closes_at_100pct"]) and r6["unallocated_amount"] > 0)})

    passed_all = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "validation_passed": bool(passed_all)}


def compute_personal_budget_tool(mode="validate", params=None):
    params = params or {}
    if mode == "income_expense_balance":
        return _income_expense_balance(params["income"], params["expenses"])
    elif mode == "category_benchmark":
        return _category_benchmark(params["expenses"], params["total_income"], params.get("benchmark"))
    elif mode == "fixed_variable_split":
        return _fixed_variable_split(params["expenses"], params.get("income"))
    elif mode == "zero_based_allocation":
        return _zero_based_allocation(params["total_income"], params["categories"], params.get("tolerance_pct", 0.5))
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"mode desconocido: {mode}")


PERSONAL_BUDGET_TOOL_SCHEMA = {
    "name": "personal_budget_tool",
    "description": (
        "Presupuesto personal/domestico: income_expense_balance (balance ingreso-gasto, tasa de "
        "ahorro, breakdown porcentual por categoria), category_benchmark (compara gasto real por "
        "tipo necesidad/deseo/ahorro contra un benchmark, regla 50/30/20 por defecto o uno custom "
        "que sume 1.0), fixed_variable_split (separa gasto fijo vs variable, ratio de compromiso "
        "fijo sobre ingreso), zero_based_allocation (presupuesto base-cero: asigna montos por "
        "categoria segun % objetivo y verifica que cierre en 100%). Aritmetica de presupuesto, "
        "confidence_flag 'alta' para toda la mecanica (sumas y porcentajes cerrados). No es "
        "asesoria financiera personalizada: los benchmarks son heuristicas de referencia, no "
        "normas. validate corre 6 checks de referencia."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["income_expense_balance", "category_benchmark", "fixed_variable_split", "zero_based_allocation", "validate"],
                "default": "validate",
            },
            "params": {
                "type": "object",
                "description": (
                    "income_expense_balance: {income (numero o lista de {source,amount}), expenses:[{category,amount}]}. "
                    "category_benchmark: {expenses:[{category,amount,type}], total_income, benchmark opcional {tipo:fraccion}}. "
                    "fixed_variable_split: {expenses:[{category,amount,type:'fixed'|'variable'}], income opcional}. "
                    "zero_based_allocation: {total_income, categories:[{name,target_pct}], tolerance_pct opcional}."
                ),
            },
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_personal_budget_tool("validate"), indent=2, ensure_ascii=False))
