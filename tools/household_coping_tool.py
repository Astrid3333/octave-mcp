"""
household_coping_tool.py

Simula estrategias agregadas de un hogar (o unidad generica de consumo) ante
perdida de ingresos, inflacion, o shocks de gasto:
- budget_optimizer: reasigna un presupuesto fijo entre necesidades basicas
  y gasto no esencial, dada una restriccion de ingreso
- asset_liquidation: modela cuanto tiempo de "runway" da vender activos
  para cubrir un deficit mensual
- social_network_support: estima cuanto de un deficit puede cubrirse con
  apoyo de una red social/comunitaria, dada su capacidad agregada

Modelos agregados y genericos de economia domestica; no identifican personas
ni hogares reales, y no producen recomendaciones individualizadas.
"""


# ---------------------------------------------------------------------------
# 1) budget_optimizer
# ---------------------------------------------------------------------------
def budget_optimizer(params):
    """
    Dado un ingreso disponible y un piso minimo de gasto en necesidades
    basicas, calcula cuanto queda disponible para gasto no esencial y
    el "gap" si el ingreso no alcanza ni para lo basico.
    """
    income = params.get("income", 1000.0)
    essential_needs = params.get("essential_needs", 700.0)
    discretionary_target = params.get("discretionary_target", 300.0)

    if income >= essential_needs:
        essential_covered = essential_needs
        remaining = income - essential_needs
        discretionary_allocated = min(remaining, discretionary_target)
        gap = 0.0
    else:
        essential_covered = income
        remaining = 0.0
        discretionary_allocated = 0.0
        gap = essential_needs - income

    return {
        "essential_covered": essential_covered,
        "discretionary_allocated": discretionary_allocated,
        "remaining_after_essentials": remaining,
        "essential_needs_gap": gap,
        "budget_balanced": gap == 0.0,
    }


# ---------------------------------------------------------------------------
# 2) asset_liquidation
# ---------------------------------------------------------------------------
def asset_liquidation(params):
    """
    Dado un deficit mensual (gasto - ingreso) y un valor total de activos
    liquidables (con un "haircut" o perdida de valor al venderlos rapido),
    calcula cuantos meses de runway se obtienen.
    """
    monthly_deficit = params.get("monthly_deficit", 200.0)
    liquid_assets_value = params.get("liquid_assets_value", 2000.0)
    liquidation_haircut_pct = params.get("liquidation_haircut_pct", 0.15)

    if monthly_deficit <= 0:
        return {
            "runway_months": float("inf"),
            "effective_liquid_value": liquid_assets_value * (1 - liquidation_haircut_pct),
            "note": "No hay deficit mensual; no se requiere liquidar activos.",
        }

    effective_value = liquid_assets_value * (1 - liquidation_haircut_pct)
    runway_months = effective_value / monthly_deficit

    return {
        "runway_months": runway_months,
        "effective_liquid_value": effective_value,
        "monthly_deficit": monthly_deficit,
    }


# ---------------------------------------------------------------------------
# 3) social_network_support
# ---------------------------------------------------------------------------
def social_network_support(params):
    """
    Estima que fraccion de un deficit puede cubrirse con apoyo comunitario,
    dada una capacidad agregada de la red (suma de lo que N contactos pueden
    aportar antes de comprometer su propia subsistencia) y una tasa de
    "fatiga de solidaridad" que reduce el aporte disponible con el tiempo.
    """
    monthly_deficit = params.get("monthly_deficit", 200.0)
    network_capacity = params.get("network_capacity", 150.0)
    solidarity_fatigue_pct = params.get("solidarity_fatigue_pct", 0.0)  # 0=sin fatiga, 1=total

    effective_capacity = network_capacity * (1 - solidarity_fatigue_pct)
    covered = min(effective_capacity, monthly_deficit)
    coverage_pct = (covered / monthly_deficit * 100.0) if monthly_deficit > 0 else 100.0
    residual_deficit = max(0.0, monthly_deficit - covered)

    return {
        "effective_network_capacity": effective_capacity,
        "deficit_covered": covered,
        "coverage_pct": coverage_pct,
        "residual_deficit": residual_deficit,
    }


# ---------------------------------------------------------------------------
# Dispatch principal
# ---------------------------------------------------------------------------
def household_coping_tool(params: dict) -> dict:
    mode = params.get("mode", "budget_optimizer")

    if mode == "budget_optimizer":
        return budget_optimizer(params)
    elif mode == "asset_liquidation":
        return asset_liquidation(params)
    elif mode == "social_network_support":
        return social_network_support(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            "mode invalido. Opciones: budget_optimizer, asset_liquidation, "
            "social_network_support, validate"
        )


# ---------------------------------------------------------------------------
# Modo validate
# ---------------------------------------------------------------------------
def _validate():
    checks = []

    # 1) budget_optimizer: ingreso suficiente -> sin gap, discrecional asignado correctamente
    r1 = budget_optimizer({"income": 1000.0, "essential_needs": 700.0, "discretionary_target": 300.0})
    checks.append({
        "name": "sufficient_income_no_gap",
        "passed": r1["essential_needs_gap"] == 0.0 and r1["discretionary_allocated"] == 300.0,
        "result": r1,
    })

    # 2) budget_optimizer: ingreso insuficiente -> gap correcto, discrecional en 0
    r2 = budget_optimizer({"income": 500.0, "essential_needs": 700.0, "discretionary_target": 300.0})
    checks.append({
        "name": "insufficient_income_has_gap",
        "passed": abs(r2["essential_needs_gap"] - 200.0) < 1e-9 and r2["discretionary_allocated"] == 0.0,
        "result": r2,
    })

    # 3) budget_optimizer: ingreso justo cubre necesidades, sin sobra para discrecional
    r3 = budget_optimizer({"income": 700.0, "essential_needs": 700.0, "discretionary_target": 300.0})
    checks.append({
        "name": "exact_income_zero_discretionary",
        "passed": r3["essential_needs_gap"] == 0.0 and r3["discretionary_allocated"] == 0.0,
        "result": r3,
    })

    # 4) asset_liquidation: calculo directo de runway
    r4 = asset_liquidation({
        "monthly_deficit": 200.0,
        "liquid_assets_value": 2000.0,
        "liquidation_haircut_pct": 0.15,
    })
    expected_effective = 2000.0 * 0.85  # 1700
    expected_runway = expected_effective / 200.0  # 8.5
    checks.append({
        "name": "runway_calculation",
        "passed": abs(r4["effective_liquid_value"] - expected_effective) < 1e-6
        and abs(r4["runway_months"] - expected_runway) < 1e-6,
        "result": r4,
        "expected_runway_months": expected_runway,
    })

    # 5) asset_liquidation: sin deficit -> runway infinito
    r5 = asset_liquidation({"monthly_deficit": 0.0, "liquid_assets_value": 1000.0})
    checks.append({
        "name": "no_deficit_infinite_runway",
        "passed": r5["runway_months"] == float("inf"),
        "result": {"runway_months": r5["runway_months"]},
    })

    # 6) social_network_support: capacidad cubre todo el deficit
    r6 = social_network_support({
        "monthly_deficit": 100.0,
        "network_capacity": 150.0,
        "solidarity_fatigue_pct": 0.0,
    })
    checks.append({
        "name": "full_coverage",
        "passed": abs(r6["coverage_pct"] - 100.0) < 1e-6 and r6["residual_deficit"] == 0.0,
        "result": r6,
    })

    # 7) social_network_support: capacidad parcial, con fatiga de solidaridad
    r7 = social_network_support({
        "monthly_deficit": 200.0,
        "network_capacity": 150.0,
        "solidarity_fatigue_pct": 0.5,  # capacidad efectiva = 75
    })
    checks.append({
        "name": "partial_coverage_with_fatigue",
        "passed": abs(r7["effective_network_capacity"] - 75.0) < 1e-6
        and abs(r7["residual_deficit"] - 125.0) < 1e-6,
        "result": r7,
    })

    all_passed = all(c["passed"] for c in checks)
    return {
        "mode": "validate",
        "tool": "household_coping_tool",
        "all_passed": all_passed,
        "checks": checks,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(household_coping_tool({"mode": "validate"}), indent=2))
