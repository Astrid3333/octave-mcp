"""
education_funding_tool.py
Fase D / Tanda 3 (3 de 3): planificacion de ahorro para educacion.
Autocontenido: no importa funciones de otros modulos del repo (leccion de
retirement_planner_tool: evitar acoplamiento a nombres internos/privados).
Schema con name/description/inputSchema desde el inicio (leccion de
life_insurance_math_tool: tool_registry.register_tool exige esa forma).

Modos:
  - cost_projection: proyecta el costo total de educacion al momento de inicio,
    dado costo actual e inflacion educativa (tipicamente distinta a inflacion general).
  - required_savings_plan: aporte periodico necesario para alcanzar el costo
    proyectado, dado ahorro ya acumulado y retorno esperado.
  - funding_gap_analysis: ahorro proyectado bajo el plan actual vs la meta,
    con banda cualitativa.
  - multi_child_allocation: reparte un presupuesto de ahorro total entre varios
    hijos, proporcional a su necesidad, y marca si cada uno individualmente
    alcanza su meta.
  - validate: suite de checks contra casos cerrados.
"""

import json


EDUCATION_FUNDING_TOOL_SCHEMA = {
    "name": "education_funding_tool",
    "description": (
        "Planificacion de ahorro para educacion: cost_projection (costo futuro "
        "proyectado con inflacion educativa propia, distinta de la inflacion "
        "general), required_savings_plan (aporte periodico necesario dado ahorro "
        "ya acumulado, retorno esperado y anios hasta el inicio), "
        "funding_gap_analysis (ahorro proyectado bajo el plan actual vs la meta, "
        "banda cualitativa sin_plan/insuficiente/por_debajo_de_la_meta/cubierto/"
        "sobre_financiado), multi_child_allocation (reparte un presupuesto de "
        "ahorro mensual entre varios hijos proporcional a su necesidad, marca si "
        "cada uno individualmente alcanza su meta). confidence_flag 'alta' para "
        "la mecanica de interes compuesto (formulas cerradas deterministicas); "
        "costos, inflacion educativa y retornos futuros son supuestos de quien "
        "llama, no una prediccion. No es asesoria financiera. validate corre "
        "8 checks de referencia."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "cost_projection",
                    "required_savings_plan",
                    "funding_gap_analysis",
                    "multi_child_allocation",
                    "validate",
                ],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


# ----------------------------------------------------------------------
# Motores matematicos autocontenidos
# ----------------------------------------------------------------------

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


def _required_periodic_contribution(target_future_value: float, years: float,
                                     current_savings: float, annual_rate: float,
                                     periods_per_year: int = 1) -> float:
    """
    Aporte periodico necesario para que el ahorro (con lo ya acumulado)
    alcance target_future_value en 'years' anios, a annual_rate de retorno.
    Despeje algebraico de _future_value para PMT.
    """
    n = periods_per_year * years
    r = annual_rate / periods_per_year
    growth = (1 + r) ** n
    fv_from_savings = current_savings * growth
    remaining = target_future_value - fv_from_savings
    if r == 0:
        return remaining / n if n != 0 else 0.0
    return remaining * r / (growth - 1)


# ----------------------------------------------------------------------
# Modo 1: cost_projection
# ----------------------------------------------------------------------

def _mode_cost_projection(params: dict) -> dict:
    current_cost = float(params["current_cost"])
    education_inflation = float(params["education_inflation"])
    years_to_start = float(params["years_to_start"])

    projected_cost = current_cost * ((1 + education_inflation) ** years_to_start)

    return {
        "current_cost": current_cost,
        "education_inflation": education_inflation,
        "years_to_start": years_to_start,
        "projected_cost": round(projected_cost, 2),
    }


# ----------------------------------------------------------------------
# Modo 2: required_savings_plan
# ----------------------------------------------------------------------

def _mode_required_savings_plan(params: dict) -> dict:
    current_cost = float(params["current_cost"])
    education_inflation = float(params.get("education_inflation", 0.0))
    years_to_start = float(params["years_to_start"])
    current_savings = float(params.get("current_savings", 0.0))
    annual_return = float(params["annual_return"])
    periods_per_year = int(params.get("periods_per_year", 12))

    projected_cost = current_cost * ((1 + education_inflation) ** years_to_start)
    required_contribution = _required_periodic_contribution(
        projected_cost, years_to_start, current_savings, annual_return, periods_per_year
    )

    return {
        "current_cost": current_cost,
        "education_inflation": education_inflation,
        "years_to_start": years_to_start,
        "current_savings": current_savings,
        "annual_return": annual_return,
        "periods_per_year": periods_per_year,
        "projected_cost": round(projected_cost, 2),
        "required_periodic_contribution": round(required_contribution, 2),
    }


# ----------------------------------------------------------------------
# Modo 3: funding_gap_analysis
# ----------------------------------------------------------------------

def _classify_funding_ratio(ratio: float, projected_savings: float) -> str:
    if projected_savings <= 0:
        return "sin_plan"
    if ratio < 0.5:
        return "insuficiente"
    if ratio < 0.9:
        return "por_debajo_de_la_meta"
    if ratio <= 1.1:
        return "cubierto"
    return "sobre_financiado"


def _mode_funding_gap_analysis(params: dict) -> dict:
    target = float(params["target"])
    current_savings = float(params.get("current_savings", 0.0))
    periodic_contribution = float(params.get("periodic_contribution", 0.0))
    annual_return = float(params["annual_return"])
    years_to_start = float(params["years_to_start"])
    periods_per_year = int(params.get("periods_per_year", 12))

    projected_savings = _future_value(
        current_savings, periodic_contribution, annual_return,
        years_to_start, periods_per_year,
    )
    gap = target - projected_savings
    ratio = (projected_savings / target) if target > 0 else float("inf")
    band = _classify_funding_ratio(ratio, projected_savings)

    return {
        "target": target,
        "current_savings": current_savings,
        "periodic_contribution": periodic_contribution,
        "annual_return": annual_return,
        "years_to_start": years_to_start,
        "periods_per_year": periods_per_year,
        "projected_savings": round(projected_savings, 2),
        "gap": round(gap, 2),
        "funding_ratio": round(ratio, 4) if ratio != float("inf") else None,
        "band": band,
    }


# ----------------------------------------------------------------------
# Modo 4: multi_child_allocation
# ----------------------------------------------------------------------

def _mode_multi_child_allocation(params: dict) -> dict:
    children = params["children"]
    total_monthly_budget = float(params["total_monthly_budget"])
    annual_return = float(params["annual_return"])

    per_child = []
    total_required = 0.0
    for child in children:
        name = child["name"]
        target_cost = float(child["target_cost"])
        years_to_start = float(child["years_to_start"])
        current_savings = float(child.get("current_savings", 0.0))

        required_monthly = _required_periodic_contribution(
            target_cost, years_to_start, current_savings, annual_return,
            periods_per_year=12,
        )
        required_monthly = max(required_monthly, 0.0)
        per_child.append({
            "name": name,
            "target_cost": target_cost,
            "years_to_start": years_to_start,
            "current_savings": current_savings,
            "required_monthly": required_monthly,
        })
        total_required += required_monthly

    results = []
    for c in per_child:
        weight = (c["required_monthly"] / total_required) if total_required > 0 else (
            1.0 / len(per_child) if per_child else 0.0
        )
        allocated_monthly = total_monthly_budget * weight
        shortfall = max(0.0, c["required_monthly"] - allocated_monthly)
        meets_goal = allocated_monthly >= c["required_monthly"] - 0.01

        results.append({
            "name": c["name"],
            "target_cost": c["target_cost"],
            "years_to_start": c["years_to_start"],
            "required_monthly": round(c["required_monthly"], 2),
            "allocated_monthly": round(allocated_monthly, 2),
            "shortfall": round(shortfall, 2),
            "meets_goal": meets_goal,
        })

    return {
        "total_monthly_budget": total_monthly_budget,
        "total_required_monthly": round(total_required, 2),
        "overall_coverage_ratio": (
            round(total_monthly_budget / total_required, 4) if total_required > 0 else None
        ),
        "children": results,
    }


# ----------------------------------------------------------------------
# Validacion
# ----------------------------------------------------------------------

def _mode_validate() -> dict:
    checks = []

    # 1) cost_projection: aritmetica exacta
    cp = _mode_cost_projection({
        "current_cost": 50000.0, "education_inflation": 0.05, "years_to_start": 10,
    })
    expected_cp = 50000.0 * (1.05 ** 10)
    checks.append({
        "name": "cost_projection_arithmetic_exact",
        "computed": cp["projected_cost"],
        "expected": round(expected_cp, 2),
        "passed": abs(cp["projected_cost"] - expected_cp) < 0.01,
    })

    # 2) mayor inflacion educativa -> mayor costo proyectado
    cp_low = _mode_cost_projection({
        "current_cost": 50000.0, "education_inflation": 0.03, "years_to_start": 10,
    })["projected_cost"]
    cp_high = _mode_cost_projection({
        "current_cost": 50000.0, "education_inflation": 0.07, "years_to_start": 10,
    })["projected_cost"]
    checks.append({
        "name": "higher_education_inflation_gives_higher_projected_cost",
        "cp_low": cp_low,
        "cp_high": cp_high,
        "passed": cp_high > cp_low,
    })

    # 3) required_savings_plan: round-trip contra _future_value debe matchear la meta (diff 0)
    rsp = _mode_required_savings_plan({
        "current_cost": 80000.0, "education_inflation": 0.04, "years_to_start": 15,
        "current_savings": 5000.0, "annual_return": 0.06, "periods_per_year": 12,
    })
    fv_check = _future_value(
        5000.0, rsp["required_periodic_contribution"], 0.06, 15, periods_per_year=12,
    )
    checks.append({
        "name": "required_savings_plan_roundtrip_matches_target",
        "target": rsp["projected_cost"],
        "achieved": round(fv_check, 2),
        "abs_diff": round(abs(fv_check - rsp["projected_cost"]), 2),
        "passed": abs(fv_check - rsp["projected_cost"]) < 1.0,
    })

    # 4) mas ahorro acumulado -> menor aporte requerido
    rsp_more_savings = _mode_required_savings_plan({
        "current_cost": 80000.0, "education_inflation": 0.04, "years_to_start": 15,
        "current_savings": 30000.0, "annual_return": 0.06, "periods_per_year": 12,
    })
    checks.append({
        "name": "more_current_savings_lowers_required_contribution",
        "required_low_savings": rsp["required_periodic_contribution"],
        "required_high_savings": rsp_more_savings["required_periodic_contribution"],
        "passed": rsp_more_savings["required_periodic_contribution"] < rsp["required_periodic_contribution"],
    })

    # 5) funding_gap_analysis: contribucion exacta al requerido -> gap ~0, banda "cubierto"
    fga_exact = _mode_funding_gap_analysis({
        "target": rsp["projected_cost"],
        "current_savings": 5000.0,
        "periodic_contribution": rsp["required_periodic_contribution"],
        "annual_return": 0.06,
        "years_to_start": 15,
        "periods_per_year": 12,
    })
    checks.append({
        "name": "funding_gap_zero_when_contribution_matches_requirement",
        "gap": fga_exact["gap"],
        "band": fga_exact["band"],
        "passed": abs(fga_exact["gap"]) < 1.0 and fga_exact["band"] == "cubierto",
    })

    # 6) funding_gap_analysis: bandas monotonicas y distintas segun aporte
    bands = []
    for contrib in [0.0, 50.0, 300.0, rsp["required_periodic_contribution"], 2000.0]:
        r = _mode_funding_gap_analysis({
            "target": rsp["projected_cost"], "current_savings": 5000.0,
            "periodic_contribution": contrib, "annual_return": 0.06,
            "years_to_start": 15, "periods_per_year": 12,
        })
        bands.append(r["band"])
    checks.append({
        "name": "funding_gap_bands_monotonic_and_distinct",
        "bands": bands,
        "passed": bands == [
            "insuficiente", "insuficiente", "por_debajo_de_la_meta",
            "cubierto", "sobre_financiado",
        ],
    })

    # 7) multi_child_allocation: conservacion de presupuesto (suma asignada = presupuesto total)
    mca = _mode_multi_child_allocation({
        "children": [
            {"name": "Hijo A", "target_cost": 100000.0, "years_to_start": 3, "current_savings": 5000.0},
            {"name": "Hijo B", "target_cost": 120000.0, "years_to_start": 12, "current_savings": 2000.0},
        ],
        "total_monthly_budget": 1000.0,
        "annual_return": 0.06,
    })
    sum_allocated = sum(c["allocated_monthly"] for c in mca["children"])
    checks.append({
        "name": "multi_child_allocation_conserves_total_budget",
        "sum_allocated": round(sum_allocated, 2),
        "total_budget": mca["total_monthly_budget"],
        "passed": abs(sum_allocated - mca["total_monthly_budget"]) < 0.05,
    })

    # 8) multi_child_allocation: el hijo mas urgente (menos anios) recibe mas asignacion
    hijo_a = next(c for c in mca["children"] if c["name"] == "Hijo A")
    hijo_b = next(c for c in mca["children"] if c["name"] == "Hijo B")
    checks.append({
        "name": "more_urgent_child_gets_higher_allocation",
        "allocated_hijo_a_3y": hijo_a["allocated_monthly"],
        "allocated_hijo_b_12y": hijo_b["allocated_monthly"],
        "passed": hijo_a["allocated_monthly"] > hijo_b["allocated_monthly"],
    })

    validation_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "validation_passed": validation_passed}


# ----------------------------------------------------------------------
# Dispatch principal
# ----------------------------------------------------------------------

def compute_education_funding(mode="validate", params=None):
    params = params or {}
    if mode == "cost_projection":
        return _mode_cost_projection(params)
    elif mode == "required_savings_plan":
        return _mode_required_savings_plan(params)
    elif mode == "funding_gap_analysis":
        return _mode_funding_gap_analysis(params)
    elif mode == "multi_child_allocation":
        return _mode_multi_child_allocation(params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(
            f"modo desconocido: {mode}. Use cost_projection | required_savings_plan | "
            f"funding_gap_analysis | multi_child_allocation | validate"
        )


try:
    from tool_registry import register_tool
    register_tool(
        name="education_funding_tool",
        schema=EDUCATION_FUNDING_TOOL_SCHEMA,
        handler=lambda args: compute_education_funding(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    d = compute_education_funding("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de education_funding_tool.py pasaron OK.")
