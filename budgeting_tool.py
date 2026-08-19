"""
budgeting_tool.py

Tool MCP: budgeting_tool
Generación de presupuestos de construcción: costo directo, análisis de precios
unitarios (APU), gastos generales/utilidad/contingencia/impuestos, escalamiento
por inflación, y presupuesto agregado por capítulos.

Operaciones soportadas (parámetro `mode`):
  - direct_cost           : costo directo de una lista de partidas (qty * unit_cost)
  - apply_markups         : aplica gastos generales, utilidad, contingencia e impuesto sobre un costo directo
  - unit_price_analysis    : análisis de precio unitario (APU) clásico: materiales + mano de obra + equipo -> precio de venta
  - escalation             : escalamiento compuesto de un monto por inflación/reajuste anual
  - budget_summary         : agrega varios capítulos de partidas en un presupuesto total, con markups al final
  - validate                : corre 5 autochequeos (uno por modo) contra valores calculados a mano

Dependencias: ninguna externa (aritmética pura).
"""

BUDGETING_TOOL_SCHEMA = {
    "name": "budgeting_tool",
    "description": (
        "Generación de presupuestos de construcción: costo directo de partidas, análisis "
        "de precio unitario (APU: materiales + mano de obra + equipo), aplicación de gastos "
        "generales/utilidad/contingencia/impuesto sobre un costo directo, escalamiento "
        "compuesto por inflación, y presupuesto agregado por capítulos."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["direct_cost", "apply_markups", "unit_price_analysis", "escalation", "budget_summary", "validate"],
                "description": "Si es 'validate', ejecuta el autocheque interno (5 casos, uno por modo) contra valores calculados a mano, e ignora el resto de los parámetros.",
            },
            "items": {"type": "array", "description": "Lista de {description, quantity, unit_cost}. direct_cost."},
            "direct_cost": {"type": "number", "description": "Costo directo base. apply_markups."},
            "overhead_pct": {"type": "number", "description": "Gastos generales, fracción (ej 0.15). apply_markups, unit_price_analysis, budget_summary."},
            "profit_pct": {"type": "number", "description": "Utilidad, fracción. apply_markups, unit_price_analysis, budget_summary."},
            "contingency_pct": {"type": "number", "description": "Contingencia, fracción. apply_markups, budget_summary."},
            "tax_pct": {"type": "number", "description": "Impuesto (ej IVA=0.19), fracción. apply_markups, budget_summary."},
            "materials": {"type": "array", "description": "Lista de {qty, unit_cost}. unit_price_analysis."},
            "labor": {"type": "array", "description": "Lista de {qty, unit_cost} (horas-hombre x costo/hora). unit_price_analysis."},
            "equipment": {"type": "array", "description": "Lista de {qty, unit_cost}. unit_price_analysis."},
            "base_amount": {"type": "number", "description": "Monto base a escalar. escalation."},
            "annual_rate": {"type": "number", "description": "Tasa anual de reajuste, fracción. escalation."},
            "years": {"type": "number", "description": "Años (puede ser fraccionario). escalation."},
            "chapters": {"type": "array", "description": "Lista de {name, items:[{description,quantity,unit_cost}]}. budget_summary."},
        },
        "required": ["mode"],
    },
}


def _direct_cost(items):
    lines = []
    total = 0.0
    for it in items:
        subtotal = it["quantity"] * it["unit_cost"]
        total += subtotal
        lines.append({
            "description": it.get("description", ""),
            "quantity": it["quantity"], "unit_cost": it["unit_cost"],
            "subtotal": round(subtotal, 2),
        })
    return {"mode": "direct_cost", "lines": lines, "total_direct_cost": round(total, 2)}


def _apply_markups(direct_cost, overhead_pct=0.0, profit_pct=0.0, contingency_pct=0.0, tax_pct=0.0):
    """
    Aplicación SECUENCIAL (cada % se aplica sobre el subtotal acumulado hasta ese punto,
    no todos sobre el costo directo original). Es la convención más común en presupuestos
    de construcción chilenos (GG, luego Utilidad, luego IVA sobre el total con utilidad).
    """
    running = direct_cost
    breakdown = {"direct_cost": round(direct_cost, 2)}
    for name, pct in [("overhead", overhead_pct), ("profit", profit_pct),
                       ("contingency", contingency_pct), ("tax", tax_pct)]:
        amount = running * pct
        running += amount
        breakdown[f"{name}_pct"] = pct
        breakdown[f"{name}_amount"] = round(amount, 2)
        breakdown[f"subtotal_after_{name}"] = round(running, 2)
    breakdown["total"] = round(running, 2)
    return {"mode": "apply_markups", **breakdown}


def _unit_price_analysis(materials=None, labor=None, equipment=None, overhead_pct=0.0, profit_pct=0.0):
    materials = materials or []
    labor = labor or []
    equipment = equipment or []
    material_cost = sum(m["qty"] * m["unit_cost"] for m in materials)
    labor_cost = sum(l["qty"] * l["unit_cost"] for l in labor)
    equipment_cost = sum(e["qty"] * e["unit_cost"] for e in equipment)
    direct_unit_cost = material_cost + labor_cost + equipment_cost
    overhead = direct_unit_cost * overhead_pct
    subtotal_with_overhead = direct_unit_cost + overhead
    profit = subtotal_with_overhead * profit_pct
    unit_price = subtotal_with_overhead + profit
    return {
        "mode": "unit_price_analysis",
        "material_cost": round(material_cost, 2),
        "labor_cost": round(labor_cost, 2),
        "equipment_cost": round(equipment_cost, 2),
        "direct_unit_cost": round(direct_unit_cost, 2),
        "overhead_amount": round(overhead, 2),
        "profit_amount": round(profit, 2),
        "unit_price": round(unit_price, 2),
    }


def _escalation(base_amount, annual_rate, years):
    escalated = base_amount * (1 + annual_rate) ** years
    return {
        "mode": "escalation",
        "base_amount": round(base_amount, 2),
        "annual_rate": annual_rate,
        "years": years,
        "escalated_amount": round(escalated, 2),
        "increase": round(escalated - base_amount, 2),
    }


def _budget_summary(chapters, overhead_pct=0.0, profit_pct=0.0, contingency_pct=0.0, tax_pct=0.0):
    chapter_results = []
    total_direct = 0.0
    for ch in chapters:
        dc = _direct_cost(ch["items"])
        chapter_results.append({"name": ch["name"], "direct_cost": dc["total_direct_cost"], "lines": dc["lines"]})
        total_direct += dc["total_direct_cost"]

    markups = _apply_markups(total_direct, overhead_pct, profit_pct, contingency_pct, tax_pct)
    return {
        "mode": "budget_summary",
        "chapters": chapter_results,
        "total_direct_cost": round(total_direct, 2),
        "markups": markups,
        "grand_total": markups["total"],
    }


def _run_validate():
    """Autochequeos contra valores calculados a mano, uno por modo."""
    checks = []

    # 1. direct_cost: 2x100 + 3x50 = 350
    dc = _direct_cost([{"quantity": 2, "unit_cost": 100}, {"quantity": 3, "unit_cost": 50}])
    checks.append({
        "case": "direct_cost 2x100 + 3x50",
        "got": dc["total_direct_cost"], "expected": 350.0,
        "ok": abs(dc["total_direct_cost"] - 350.0) < 1e-6,
    })

    # 2. apply_markups: 1000 con GG 15%, utilidad 10%, contingencia 5%, IVA 19% secuencial -> 1580.62
    markups = _apply_markups(1000, overhead_pct=0.15, profit_pct=0.10, contingency_pct=0.05, tax_pct=0.19)
    checks.append({
        "case": "apply_markups 1000 con GG15/Util10/Cont5/IVA19 secuencial",
        "got": markups["total"], "expected": 1580.62,
        "ok": abs(markups["total"] - 1580.62) < 1e-6,
    })

    # 3. unit_price_analysis: materiales 2x10, mano de obra 1x20, equipo 1x5, GG 10%, utilidad 5% -> 51.98
    upa = _unit_price_analysis(
        materials=[{"qty": 2, "unit_cost": 10}], labor=[{"qty": 1, "unit_cost": 20}],
        equipment=[{"qty": 1, "unit_cost": 5}], overhead_pct=0.1, profit_pct=0.05,
    )
    checks.append({
        "case": "unit_price_analysis mat=20 mo=20 eq=5 GG10/Util5",
        "got": upa["unit_price"], "expected": 51.98,
        "ok": abs(upa["unit_price"] - 51.98) < 1e-6,
    })

    # 4. escalation: 1000 al 5% anual por 2 años -> 1102.5
    esc = _escalation(1000, 0.05, 2)
    checks.append({
        "case": "escalation 1000 a 5% anual x 2 anios",
        "got": esc["escalated_amount"], "expected": 1102.5,
        "ok": abs(esc["escalated_amount"] - 1102.5) < 1e-6,
    })

    # 5. budget_summary: 2 capitulos (100 + 100 = 200 directo), GG 10% -> grand_total 220
    bs = _budget_summary(
        [{"name": "A", "items": [{"quantity": 1, "unit_cost": 100}]},
         {"name": "B", "items": [{"quantity": 2, "unit_cost": 50}]}],
        overhead_pct=0.1,
    )
    checks.append({
        "case": "budget_summary 2 capitulos direct=200 GG10",
        "got": {"total_direct_cost": bs["total_direct_cost"], "grand_total": bs["grand_total"]},
        "expected": {"total_direct_cost": 200.0, "grand_total": 220.0},
        "ok": abs(bs["total_direct_cost"] - 200.0) < 1e-6 and abs(bs["grand_total"] - 220.0) < 1e-6,
    })

    all_passed = all(c["ok"] for c in checks)
    return {"validate": True, "all_passed": all_passed, "checks": checks}


def compute_budgeting(mode, **params):
    """Entry point del tool. Despacha según `mode`. Retorna un dict serializable a JSON."""
    if mode == "validate":
        return _run_validate()
    if mode == "direct_cost":
        return _direct_cost(params["items"])
    if mode == "apply_markups":
        return _apply_markups(
            params["direct_cost"], params.get("overhead_pct", 0.0), params.get("profit_pct", 0.0),
            params.get("contingency_pct", 0.0), params.get("tax_pct", 0.0),
        )
    if mode == "unit_price_analysis":
        return _unit_price_analysis(
            params.get("materials"), params.get("labor"), params.get("equipment"),
            params.get("overhead_pct", 0.0), params.get("profit_pct", 0.0),
        )
    if mode == "escalation":
        return _escalation(params["base_amount"], params["annual_rate"], params["years"])
    if mode == "budget_summary":
        return _budget_summary(
            params["chapters"], params.get("overhead_pct", 0.0), params.get("profit_pct", 0.0),
            params.get("contingency_pct", 0.0), params.get("tax_pct", 0.0),
        )

    raise ValueError(
        f"mode no soportado: {mode}. Usar: direct_cost | apply_markups | "
        "unit_price_analysis | escalation | budget_summary | validate"
    )


if __name__ == "__main__":
    import json
    print(json.dumps(compute_budgeting(mode="validate"), ensure_ascii=False, indent=2))

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("budgeting_tool", BUDGETING_TOOL_SCHEMA, lambda args, _f=compute_budgeting: _f(**args))
