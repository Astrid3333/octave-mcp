"""
tax_estimation_tool.py
Fase D / Tanda 4 (3 de 3): estimacion de impuesto sobre la renta, progresivo.
Autocontenido: sin imports cruzados a otros modulos del repo.
Schema con name/description/inputSchema desde el inicio.

Deliberadamente generico: NO trae una tabla de tramos hardcodeada de ningun
pais (los sistemas tributarios varian por jurisdiccion y cambian ano a ano).
Quien llama provee sus propios tramos como parametro:
  brackets = [
    {"upper_bound": 10000, "rate": 0.10},
    {"upper_bound": 40000, "rate": 0.20},
    {"upper_bound": null,  "rate": 0.30}   # null = sin techo, ultimo tramo
  ]
Los tramos deben venir ordenados ascendentemente por upper_bound, con el
ultimo tramo en null (sin techo).

Modos:
  - marginal_tax: impuesto total sobre un ingreso gravable, dado los tramos.
    Devuelve tambien tasa efectiva y tasa marginal.
  - after_tax_income: ingreso neto dado ingreso bruto, deducciones y tramos.
  - bracket_breakdown: detalle de cuanto se tributa en cada tramo (transparencia).
  - what_if_income_change: impuesto marginal sobre un monto adicional de
    ingreso (aumento, bono), y cuanto de ese monto queda neto.
  - validate: suite de checks contra casos cerrados.
"""

import json


TAX_ESTIMATION_TOOL_SCHEMA = {
    "name": "tax_estimation_tool",
    "description": (
        "Estimacion de impuesto sobre la renta con tramos progresivos "
        "provistos por quien llama (generico, sin tabla hardcodeada de ningun "
        "pais -los sistemas tributarios varian por jurisdiccion y cambian ano "
        "a ano-). Modos: marginal_tax (impuesto total sobre ingreso gravable, "
        "mas tasa efectiva y tasa marginal), after_tax_income (ingreso neto "
        "dado ingreso bruto, deducciones y tramos), bracket_breakdown (detalle "
        "de cuanto se tributa en cada tramo), what_if_income_change (impuesto "
        "marginal sobre un monto adicional de ingreso, ej. aumento o bono, y "
        "cuanto de ese monto queda neto). confidence_flag 'alta' para la "
        "mecanica de calculo progresivo (aritmetica determinista dados los "
        "tramos); los tramos, tasas y deducciones son un input de quien llama, "
        "no una tabla oficial ni actualizada por esta tool. No es asesoria "
        "fiscal ni legal; consultar la normativa vigente de la jurisdiccion "
        "correspondiente. validate corre 8 checks."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "marginal_tax",
                    "after_tax_income",
                    "bracket_breakdown",
                    "what_if_income_change",
                    "validate",
                ],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


# ----------------------------------------------------------------------
# Motor autocontenido: calculo de impuesto progresivo por tramos
# ----------------------------------------------------------------------

def _compute_progressive_tax(taxable_income: float, brackets: list):
    """
    Calcula el impuesto total sobre taxable_income dado una lista de tramos
    ordenados ascendentemente por upper_bound (el ultimo tramo debe tener
    upper_bound=None, sin techo). Devuelve (tax_total, breakdown, marginal_rate).
    """
    if taxable_income <= 0:
        return 0.0, [], (brackets[0]["rate"] if brackets else 0.0)

    tax_total = 0.0
    lower = 0.0
    breakdown = []
    marginal_rate = 0.0

    for b in brackets:
        upper = b["upper_bound"]
        rate = float(b["rate"])

        if upper is None:
            portion = max(0.0, taxable_income - lower)
        else:
            portion = max(0.0, min(taxable_income, upper) - lower)

        tax_in_bracket = portion * rate
        tax_total += tax_in_bracket

        if portion > 0:
            breakdown.append({
                "lower_bound": lower,
                "upper_bound": upper,
                "rate": rate,
                "taxable_amount_in_bracket": round(portion, 2),
                "tax_in_bracket": round(tax_in_bracket, 2),
            })
            marginal_rate = rate

        if upper is not None:
            lower = upper
            if taxable_income <= upper:
                break
        else:
            break

    return tax_total, breakdown, marginal_rate


# ----------------------------------------------------------------------
# Modo 1: marginal_tax
# ----------------------------------------------------------------------

def _mode_marginal_tax(params: dict) -> dict:
    taxable_income = float(params["taxable_income"])
    brackets = params["brackets"]

    tax_total, breakdown, marginal_rate = _compute_progressive_tax(taxable_income, brackets)
    effective_rate = (tax_total / taxable_income) if taxable_income > 0 else 0.0

    return {
        "taxable_income": taxable_income,
        "tax_total": round(tax_total, 2),
        "effective_rate": round(effective_rate, 4),
        "marginal_rate": marginal_rate,
    }


# ----------------------------------------------------------------------
# Modo 2: after_tax_income
# ----------------------------------------------------------------------

def _mode_after_tax_income(params: dict) -> dict:
    gross_income = float(params["gross_income"])
    deductions = float(params.get("deductions", 0.0))
    brackets = params["brackets"]

    taxable_income = max(0.0, gross_income - deductions)
    tax_total, _, marginal_rate = _compute_progressive_tax(taxable_income, brackets)
    net_income = gross_income - tax_total
    effective_rate = (tax_total / gross_income) if gross_income > 0 else 0.0

    return {
        "gross_income": gross_income,
        "deductions": deductions,
        "taxable_income": round(taxable_income, 2),
        "tax_total": round(tax_total, 2),
        "net_income": round(net_income, 2),
        "effective_rate": round(effective_rate, 4),
        "marginal_rate": marginal_rate,
    }


# ----------------------------------------------------------------------
# Modo 3: bracket_breakdown
# ----------------------------------------------------------------------

def _mode_bracket_breakdown(params: dict) -> dict:
    taxable_income = float(params["taxable_income"])
    brackets = params["brackets"]

    tax_total, breakdown, marginal_rate = _compute_progressive_tax(taxable_income, brackets)

    return {
        "taxable_income": taxable_income,
        "breakdown": breakdown,
        "tax_total": round(tax_total, 2),
        "marginal_rate": marginal_rate,
    }


# ----------------------------------------------------------------------
# Modo 4: what_if_income_change
# ----------------------------------------------------------------------

def _mode_what_if_income_change(params: dict) -> dict:
    current_taxable_income = float(params["current_taxable_income"])
    additional_income = float(params["additional_income"])
    brackets = params["brackets"]

    tax_before, _, _ = _compute_progressive_tax(current_taxable_income, brackets)
    tax_after, _, marginal_rate_after = _compute_progressive_tax(
        current_taxable_income + additional_income, brackets
    )

    extra_tax = tax_after - tax_before
    net_additional_income = additional_income - extra_tax
    effective_marginal_rate_on_increment = (
        (extra_tax / additional_income) if additional_income > 0 else 0.0
    )

    return {
        "current_taxable_income": current_taxable_income,
        "additional_income": additional_income,
        "tax_before": round(tax_before, 2),
        "tax_after": round(tax_after, 2),
        "extra_tax": round(extra_tax, 2),
        "net_additional_income": round(net_additional_income, 2),
        "effective_marginal_rate_on_increment": round(effective_marginal_rate_on_increment, 4),
        "marginal_rate_at_new_income": marginal_rate_after,
    }


# ----------------------------------------------------------------------
# Validacion
# ----------------------------------------------------------------------

_TEST_BRACKETS = [
    {"upper_bound": 10000.0, "rate": 0.10},
    {"upper_bound": 40000.0, "rate": 0.20},
    {"upper_bound": None, "rate": 0.30},
]


def _mode_validate() -> dict:
    checks = []

    # 1) marginal_tax: aritmetica exacta para ingreso dentro del segundo tramo
    #    (10000 al 10% + 15000 al 20%, para taxable_income=25000)
    mt = _mode_marginal_tax({"taxable_income": 25000.0, "brackets": _TEST_BRACKETS})
    expected_tax = 10000.0 * 0.10 + 15000.0 * 0.20
    checks.append({
        "name": "marginal_tax_arithmetic_exact_second_bracket",
        "computed": mt["tax_total"],
        "expected": round(expected_tax, 2),
        "passed": abs(mt["tax_total"] - expected_tax) < 0.01,
    })

    # 2) marginal_tax: tasa marginal correcta (25000 cae en el tramo del 20%)
    checks.append({
        "name": "marginal_rate_matches_bracket_containing_income",
        "computed": mt["marginal_rate"],
        "expected": 0.20,
        "passed": abs(mt["marginal_rate"] - 0.20) < 1e-9,
    })

    # 3) marginal_tax: ingreso en el ultimo tramo (sin techo), aritmetica exacta
    mt_high = _mode_marginal_tax({"taxable_income": 60000.0, "brackets": _TEST_BRACKETS})
    expected_tax_high = 10000.0 * 0.10 + 30000.0 * 0.20 + 20000.0 * 0.30
    checks.append({
        "name": "marginal_tax_arithmetic_exact_top_bracket",
        "computed": mt_high["tax_total"],
        "expected": round(expected_tax_high, 2),
        "passed": abs(mt_high["tax_total"] - expected_tax_high) < 0.01,
    })

    # 4) after_tax_income: net_income + tax_total debe reconstruir el gross_income exacto
    ati = _mode_after_tax_income({
        "gross_income": 55000.0, "deductions": 5000.0, "brackets": _TEST_BRACKETS,
    })
    checks.append({
        "name": "after_tax_income_reconciles_to_gross",
        "net_plus_tax": round(ati["net_income"] + ati["tax_total"], 2),
        "gross_income": ati["gross_income"],
        "passed": abs((ati["net_income"] + ati["tax_total"]) - ati["gross_income"]) < 0.01,
    })

    # 5) after_tax_income: mas deducciones -> menos impuesto (income gravable menor)
    ati_more_deductions = _mode_after_tax_income({
        "gross_income": 55000.0, "deductions": 20000.0, "brackets": _TEST_BRACKETS,
    })
    checks.append({
        "name": "more_deductions_lowers_tax",
        "tax_low_deductions": ati["tax_total"],
        "tax_high_deductions": ati_more_deductions["tax_total"],
        "passed": ati_more_deductions["tax_total"] < ati["tax_total"],
    })

    # 6) bracket_breakdown: la suma de los tramos individuales debe matchear el total
    bb = _mode_bracket_breakdown({"taxable_income": 60000.0, "brackets": _TEST_BRACKETS})
    sum_breakdown = sum(item["tax_in_bracket"] for item in bb["breakdown"])
    checks.append({
        "name": "bracket_breakdown_sums_to_total",
        "sum_breakdown": round(sum_breakdown, 2),
        "tax_total": bb["tax_total"],
        "passed": abs(sum_breakdown - bb["tax_total"]) < 0.01,
    })

    # 7) what_if_income_change: extra_tax + net_additional_income = additional_income (exacto)
    wi = _mode_what_if_income_change({
        "current_taxable_income": 38000.0, "additional_income": 5000.0,
        "brackets": _TEST_BRACKETS,
    })
    checks.append({
        "name": "what_if_reconciles_extra_tax_and_net",
        "sum_check": round(wi["extra_tax"] + wi["net_additional_income"], 2),
        "additional_income": wi["additional_income"],
        "passed": abs((wi["extra_tax"] + wi["net_additional_income"]) - wi["additional_income"]) < 0.01,
    })

    # 8) what_if_income_change: un aumento que cruza de tramo (10% -> 20%) debe
    #    dar una tasa marginal efectiva sobre el incremento estrictamente entre
    #    ambas tasas (ni 10% plano ni 20% plano)
    wi_cross = _mode_what_if_income_change({
        "current_taxable_income": 9000.0, "additional_income": 2000.0,
        "brackets": _TEST_BRACKETS,
    })
    checks.append({
        "name": "bracket_crossing_gives_blended_marginal_rate",
        "effective_marginal_rate_on_increment": wi_cross["effective_marginal_rate_on_increment"],
        "passed": 0.10 < wi_cross["effective_marginal_rate_on_increment"] < 0.20,
    })

    validation_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "validation_passed": validation_passed}


# ----------------------------------------------------------------------
# Dispatch principal
# ----------------------------------------------------------------------

def compute_tax_estimation(mode="validate", params=None):
    params = params or {}
    if mode == "marginal_tax":
        return _mode_marginal_tax(params)
    elif mode == "after_tax_income":
        return _mode_after_tax_income(params)
    elif mode == "bracket_breakdown":
        return _mode_bracket_breakdown(params)
    elif mode == "what_if_income_change":
        return _mode_what_if_income_change(params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(
            f"modo desconocido: {mode}. Use marginal_tax | after_tax_income | "
            f"bracket_breakdown | what_if_income_change | validate"
        )


try:
    from tool_registry import register_tool
    register_tool(
        name="tax_estimation_tool",
        schema=TAX_ESTIMATION_TOOL_SCHEMA,
        handler=lambda args: compute_tax_estimation(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    d = compute_tax_estimation("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de tax_estimation_tool.py pasaron OK.")
