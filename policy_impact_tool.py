"""
policy_impact_tool.py

Modelos agregados y simplificados (tipo "toy model" keynesiano) para explorar
el efecto de politicas macroeconomicas sobre variables agregadas como el PIB:
- shock_scenario: aplica un shock externo (ej. corte de suministro) a un PIB base
- intervention_analysis: modela el efecto de una intervencion (ej. ayuda humanitaria)
  sobre una variable de "bienestar" agregada
- austerity_vs_stimulus: compara un recorte de gasto publico vs. un estimulo,
  usando un multiplicador fiscal simple

Estos son modelos didacticos de dinamica de sistemas -- no son forecasts
economicos reales ni sustituyen un modelo DSGE calibrado; sirven para
explorar direccion y magnitud relativa de efectos bajo supuestos declarados.
"""


# ---------------------------------------------------------------------------
# 1) shock_scenario
# ---------------------------------------------------------------------------
def shock_scenario(params):
    """
    Aplica un shock (reduccion porcentual instantanea) a un PIB base, y luego
    una recuperacion gradual geometrica a lo largo de N periodos.
    """
    gdp0 = params.get("gdp0", 100.0)
    shock_pct = params.get("shock_pct", 0.10)  # 10% de caida
    recovery_rate = params.get("recovery_rate", 0.05)  # 5% de recuperacion del gap por periodo
    periods = int(params.get("periods", 10))

    gdp_after_shock = gdp0 * (1 - shock_pct)
    series = [{"t": 0, "gdp": gdp_after_shock}]

    gdp = gdp_after_shock
    for t in range(1, periods + 1):
        gap = gdp0 - gdp
        gdp = gdp + recovery_rate * gap
        series.append({"t": t, "gdp": gdp})

    return {
        "gdp0": gdp0,
        "gdp_after_shock": gdp_after_shock,
        "series": series,
        "gdp_final": gdp,
        "recovered_pct": (gdp - gdp_after_shock) / (gdp0 - gdp_after_shock) * 100.0
        if gdp0 != gdp_after_shock else 100.0,
    }


# ---------------------------------------------------------------------------
# 2) intervention_analysis
# ---------------------------------------------------------------------------
def intervention_analysis(params):
    """
    Modela el efecto de una intervencion (ej. ayuda humanitaria, transferencia
    directa) sobre una variable de bienestar agregada, con rendimientos
    marginales decrecientes (raiz cuadrada del monto de ayuda relativo a la
    necesidad).
    """
    baseline_wellbeing = params.get("baseline_wellbeing", 50.0)  # escala 0-100
    need_gap = params.get("need_gap", 40.0)  # cuanto falta para el maximo bienestar
    aid_amount = params.get("aid_amount", 20.0)
    aid_efficiency = params.get("aid_efficiency", 1.0)  # 0-1, perdida administrativa

    effective_aid = aid_amount * aid_efficiency
    # rendimiento marginal decreciente: mejora proporcional a sqrt(ayuda efectiva / gap)
    if need_gap <= 0:
        improvement = 0.0
    else:
        ratio = min(1.0, effective_aid / need_gap)
        improvement = need_gap * math_sqrt(ratio)

    new_wellbeing = min(100.0, baseline_wellbeing + improvement)

    return {
        "baseline_wellbeing": baseline_wellbeing,
        "effective_aid": effective_aid,
        "wellbeing_improvement": improvement,
        "new_wellbeing": new_wellbeing,
    }


def math_sqrt(x):
    import math
    return math.sqrt(max(0.0, x))


# ---------------------------------------------------------------------------
# 3) austerity_vs_stimulus
# ---------------------------------------------------------------------------
def austerity_vs_stimulus(params):
    """
    Compara el efecto de un recorte de gasto publico (austeridad) vs. un
    aumento de gasto (estimulo) sobre el PIB, usando un multiplicador
    fiscal simple: delta_gdp = multiplier * delta_spending.
    """
    gdp0 = params.get("gdp0", 100.0)
    spending_change_pct = params.get("spending_change_pct", 0.10)  # magnitud del cambio, positiva
    fiscal_multiplier = params.get("fiscal_multiplier", 1.5)

    spending_delta = gdp0 * spending_change_pct

    gdp_after_austerity = gdp0 - fiscal_multiplier * spending_delta
    gdp_after_stimulus = gdp0 + fiscal_multiplier * spending_delta

    return {
        "gdp0": gdp0,
        "spending_delta": spending_delta,
        "fiscal_multiplier": fiscal_multiplier,
        "gdp_after_austerity": gdp_after_austerity,
        "gdp_after_stimulus": gdp_after_stimulus,
        "gap_between_scenarios": gdp_after_stimulus - gdp_after_austerity,
    }


# ---------------------------------------------------------------------------
# Dispatch principal
# ---------------------------------------------------------------------------
def policy_impact_tool(params: dict) -> dict:
    mode = params.get("mode", "shock_scenario")

    if mode == "shock_scenario":
        return shock_scenario(params)
    elif mode == "intervention_analysis":
        return intervention_analysis(params)
    elif mode == "austerity_vs_stimulus":
        return austerity_vs_stimulus(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            "mode invalido. Opciones: shock_scenario, intervention_analysis, "
            "austerity_vs_stimulus, validate"
        )


# ---------------------------------------------------------------------------
# Modo validate
# ---------------------------------------------------------------------------
def _validate():
    checks = []

    # 1) shock_scenario: caida inicial correcta
    r1 = shock_scenario({"gdp0": 100.0, "shock_pct": 0.10, "recovery_rate": 0.05, "periods": 0})
    checks.append({
        "name": "shock_drop_correct",
        "passed": abs(r1["gdp_after_shock"] - 90.0) < 1e-9,
        "gdp_after_shock": r1["gdp_after_shock"],
    })

    # 2) shock_scenario: recuperacion gradual se acerca a gdp0 con muchos periodos
    r2 = shock_scenario({"gdp0": 100.0, "shock_pct": 0.10, "recovery_rate": 0.1, "periods": 200})
    checks.append({
        "name": "recovery_converges_to_baseline",
        "passed": abs(r2["gdp_final"] - 100.0) < 0.5,
        "gdp_final": r2["gdp_final"],
    })

    # 3) shock_scenario: sin recuperacion (recovery_rate=0), el PIB se queda en el nivel post-shock
    r3 = shock_scenario({"gdp0": 100.0, "shock_pct": 0.2, "recovery_rate": 0.0, "periods": 10})
    checks.append({
        "name": "no_recovery_stays_flat",
        "passed": abs(r3["gdp_final"] - 80.0) < 1e-9,
        "gdp_final": r3["gdp_final"],
    })

    # 4) intervention_analysis: ayuda que cubre exactamente el gap con eficiencia 100% -> mejora = gap
    r4 = intervention_analysis({
        "baseline_wellbeing": 50.0,
        "need_gap": 40.0,
        "aid_amount": 40.0,
        "aid_efficiency": 1.0,
    })
    checks.append({
        "name": "full_aid_covers_gap",
        "passed": abs(r4["wellbeing_improvement"] - 40.0) < 1e-6 and abs(r4["new_wellbeing"] - 90.0) < 1e-6,
        "result": r4,
    })

    # 5) intervention_analysis: sin ayuda -> sin mejora
    r5 = intervention_analysis({
        "baseline_wellbeing": 50.0,
        "need_gap": 40.0,
        "aid_amount": 0.0,
        "aid_efficiency": 1.0,
    })
    checks.append({
        "name": "no_aid_no_improvement",
        "passed": abs(r5["wellbeing_improvement"]) < 1e-9 and r5["new_wellbeing"] == 50.0,
        "result": r5,
    })

    # 6) intervention_analysis: bienestar nunca supera 100
    r6 = intervention_analysis({
        "baseline_wellbeing": 95.0,
        "need_gap": 40.0,
        "aid_amount": 100.0,
        "aid_efficiency": 1.0,
    })
    checks.append({
        "name": "wellbeing_capped_at_100",
        "passed": r6["new_wellbeing"] <= 100.0,
        "new_wellbeing": r6["new_wellbeing"],
    })

    # 7) austerity_vs_stimulus: calculo directo con multiplicador conocido
    r7 = austerity_vs_stimulus({"gdp0": 100.0, "spending_change_pct": 0.10, "fiscal_multiplier": 1.5})
    # spending_delta = 10, austeridad = 100 - 15 = 85, estimulo = 100 + 15 = 115
    checks.append({
        "name": "austerity_vs_stimulus_calculation",
        "passed": abs(r7["gdp_after_austerity"] - 85.0) < 1e-9 and abs(r7["gdp_after_stimulus"] - 115.0) < 1e-9,
        "result": r7,
    })

    # 8) austerity_vs_stimulus: el estimulo siempre da un PIB mayor que la austeridad
    #    (para multiplicador y cambio de gasto positivos)
    r8 = austerity_vs_stimulus({"gdp0": 200.0, "spending_change_pct": 0.05, "fiscal_multiplier": 0.8})
    checks.append({
        "name": "stimulus_always_exceeds_austerity",
        "passed": r8["gdp_after_stimulus"] > r8["gdp_after_austerity"],
        "gap": r8["gap_between_scenarios"],
    })

    all_passed = all(c["passed"] for c in checks)
    return {
        "mode": "validate",
        "tool": "policy_impact_tool",
        "all_passed": all_passed,
        "checks": checks,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(policy_impact_tool({"mode": "validate"}), indent=2))
