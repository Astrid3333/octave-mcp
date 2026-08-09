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
                "enum": ["direct_cost", "apply_markups", "unit_price_analysis", "escalation", "budget_summary"],
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


def compute_budgeting(mode, **params):
    """Entry point del tool. Despacha según `mode`. Retorna un dict serializable a JSON."""
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
        "unit_price_analysis | escalation | budget_summary"
    )
