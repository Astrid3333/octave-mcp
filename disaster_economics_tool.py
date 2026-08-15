"""
disaster_economics_tool.py

Impacto economico de desastres. No re-simula la fisica del peligro (eso
lo hacen earthquake_analysis_tool, wildfire_risk_tool,
natural_hazard_risk_tool, etc.) -- recibe intensidad/perdida ya
estimadas y se enfoca en la capa economica. Cuatro modos + validate:

- direct_loss: perdida economica directa = valor_expuesto *
  damage_ratio, donde damage_ratio viene de una curva de fragilidad
  parametrica generica (forma estandar en la literatura de riesgo de
  desastres, ver p.ej. HAZUS o curvas de vulnerabilidad tipo
  intensidad-dano): damage_ratio = min(1, (intensity/intensity_50)^k),
  con intensity_50 = intensidad a la cual el dano esperado es 50% y k
  la pendiente de la curva. Motor generico: intensity_50 y k los provee
  quien llama (no trae catalogo real de curvas de fragilidad por tipo
  de estructura).

- indirect_loss: perdida indirecta por interrupcion de actividad
  economica = perdida_diaria_de_produccion * dias_de_inactividad,
  con un multiplicador opcional de efectos de encadenamiento
  (input-output simplificado).

- recovery_time: tiempo de recuperacion via un modelo de recuperacion
  exponencial de la funcionalidad: functionality(t) = 1 -
  (1-functionality_0)*exp(-t/tau), resuelve el tiempo t para alcanzar
  un umbral de funcionalidad objetivo.

- cost_benefit_mitigation: analisis costo-beneficio de una medida de
  mitigacion, via valor presente neto (NPV) de perdidas evitadas menos
  el costo de la medida, y razon beneficio-costo (BCR), sobre un
  horizonte con una probabilidad anual de evento y una tasa de
  descuento.

- validate: suite de checks contra casos con solucion cerrada conocida.

Convencion identica al resto del repo: compute_disaster_economics(mode,
params=None) -> dict, registrado via tool_registry.register_tool().
"""
import numpy as np


DISASTER_ECONOMICS_TOOL_SCHEMA = {
    "name": "disaster_economics_tool",
    "description": (
        "Impacto economico de desastres (capa economica, no re-simula la "
        "fisica del peligro): direct_loss (perdida directa = "
        "valor_expuesto*damage_ratio, con damage_ratio de una curva de "
        "fragilidad generica damage_ratio=min(1,(intensity/intensity_50)^k), "
        "forma estandar tipo HAZUS), indirect_loss (perdida por "
        "interrupcion de actividad = perdida_diaria*dias_inactividad, con "
        "multiplicador de encadenamiento opcional), recovery_time (tiempo "
        "para alcanzar un umbral de funcionalidad via recuperacion "
        "exponencial functionality(t)=1-(1-functionality_0)*exp(-t/tau)), "
        "cost_benefit_mitigation (NPV de perdidas evitadas menos costo de "
        "mitigacion, y razon beneficio-costo, dado horizonte/probabilidad "
        "anual/tasa de descuento), validate (suite de checks). Motor "
        "generico: no trae catalogo real de curvas de fragilidad ni "
        "tablas input-output, los provee quien llama."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "direct_loss",
                    "indirect_loss",
                    "recovery_time",
                    "cost_benefit_mitigation",
                    "validate",
                ],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


def _mode_direct_loss(params):
    exposed_value = float(params["exposed_value"])
    if exposed_value < 0:
        raise ValueError("exposed_value debe ser >= 0")

    intensity = float(params["intensity"])
    intensity_50 = float(params["intensity_50"])
    k = float(params.get("k", 1.5))

    if intensity < 0:
        raise ValueError("intensity debe ser >= 0")
    if intensity_50 <= 0:
        raise ValueError("intensity_50 debe ser > 0")
    if k <= 0:
        raise ValueError("k debe ser > 0")

    damage_ratio = min(1.0, (intensity / intensity_50) ** k)
    direct_loss = exposed_value * damage_ratio

    return {
        "mode": "direct_loss",
        "exposed_value": exposed_value,
        "intensity": intensity,
        "intensity_50": intensity_50,
        "k": k,
        "damage_ratio": float(damage_ratio),
        "direct_loss": float(direct_loss),
        "method": "curva de fragilidad parametrica generica tipo HAZUS: damage_ratio=min(1,(I/I50)^k)",
    }


def _mode_indirect_loss(params):
    daily_output_loss = float(params["daily_output_loss"])
    if daily_output_loss < 0:
        raise ValueError("daily_output_loss debe ser >= 0")

    downtime_days = float(params["downtime_days"])
    if downtime_days < 0:
        raise ValueError("downtime_days debe ser >= 0")

    chain_multiplier = float(params.get("chain_multiplier", 1.0))
    if chain_multiplier < 1.0:
        raise ValueError("chain_multiplier debe ser >= 1.0 (1.0 = sin efectos de encadenamiento)")

    indirect_loss = daily_output_loss * downtime_days * chain_multiplier

    return {
        "mode": "indirect_loss",
        "daily_output_loss": daily_output_loss,
        "downtime_days": downtime_days,
        "chain_multiplier": chain_multiplier,
        "indirect_loss": float(indirect_loss),
    }


def _mode_recovery_time(params):
    functionality_0 = float(params["functionality_0"])
    if not (0.0 <= functionality_0 < 1.0):
        raise ValueError("functionality_0 debe estar en [0, 1)")

    tau_days = float(params["tau_days"])
    if tau_days <= 0:
        raise ValueError("tau_days debe ser > 0")

    target_functionality = float(params.get("target_functionality", 0.95))
    if not (functionality_0 < target_functionality <= 1.0):
        raise ValueError("target_functionality debe estar en (functionality_0, 1]")

    # functionality(t) = 1 - (1-f0)*exp(-t/tau)  =>  resolver t
    ratio = (1.0 - target_functionality) / (1.0 - functionality_0)
    if ratio <= 0:
        recovery_days = None
    else:
        recovery_days = float(-tau_days * np.log(ratio))

    horizon_days = params.get("curve_horizon_days")
    curve = None
    if horizon_days is not None:
        horizon_days = float(horizon_days)
        t_grid = np.linspace(0, horizon_days, min(50, max(2, int(horizon_days) + 1)))
        curve = [
            {"t_days": float(t), "functionality": float(1.0 - (1.0 - functionality_0) * np.exp(-t / tau_days))}
            for t in t_grid
        ]

    return {
        "mode": "recovery_time",
        "functionality_0": functionality_0,
        "tau_days": tau_days,
        "target_functionality": target_functionality,
        "recovery_time_days": recovery_days,
        "curve": curve,
        "method": "recuperacion exponencial: functionality(t) = 1 - (1-f0)*exp(-t/tau)",
    }


def _mode_cost_benefit_mitigation(params):
    mitigation_cost = float(params["mitigation_cost"])
    if mitigation_cost < 0:
        raise ValueError("mitigation_cost debe ser >= 0")

    expected_annual_loss_without = float(params["expected_annual_loss_without_mitigation"])
    expected_annual_loss_with = float(params["expected_annual_loss_with_mitigation"])
    if expected_annual_loss_without < 0 or expected_annual_loss_with < 0:
        raise ValueError("las perdidas anuales esperadas deben ser >= 0")
    if expected_annual_loss_with > expected_annual_loss_without:
        raise ValueError("la perdida esperada CON mitigacion no puede ser mayor que SIN mitigacion")

    horizon_years = int(params.get("horizon_years", 20))
    if horizon_years < 1:
        raise ValueError("horizon_years debe ser >= 1")

    discount_rate = float(params.get("discount_rate", 0.05))
    if not (0.0 <= discount_rate < 1.0):
        raise ValueError("discount_rate debe estar en [0, 1)")

    annual_avoided_loss = expected_annual_loss_without - expected_annual_loss_with

    years = np.arange(1, horizon_years + 1)
    discount_factors = 1.0 / (1.0 + discount_rate) ** years
    pv_avoided_losses = float(annual_avoided_loss * discount_factors.sum())

    npv = pv_avoided_losses - mitigation_cost
    bcr = pv_avoided_losses / mitigation_cost if mitigation_cost > 0 else float("inf")

    return {
        "mode": "cost_benefit_mitigation",
        "mitigation_cost": mitigation_cost,
        "annual_avoided_loss": float(annual_avoided_loss),
        "horizon_years": horizon_years,
        "discount_rate": discount_rate,
        "pv_avoided_losses": pv_avoided_losses,
        "npv": float(npv),
        "benefit_cost_ratio": float(bcr) if np.isfinite(bcr) else None,
        "recommended": bool(npv > 0),
    }


def _mode_validate():
    checks = []

    # 1) direct_loss: intensity == intensity_50 da damage_ratio exactamente 0.5^... no, da 1.0^k=1.0 -> revisar
    #    en realidad (I50/I50)^k = 1.0 -> damage_ratio=1.0 (dano total al llegar al umbral de referencia)
    r1 = _mode_direct_loss({"exposed_value": 1000.0, "intensity": 10.0, "intensity_50": 10.0, "k": 2.0})
    checks.append({
        "name": "direct_loss_at_intensity_50_gives_full_damage",
        "damage_ratio": r1["damage_ratio"], "loss": r1["direct_loss"],
        "passed": abs(r1["damage_ratio"] - 1.0) < 1e-9 and abs(r1["direct_loss"] - 1000.0) < 1e-9,
    })

    # 2) direct_loss: intensidad menor al umbral da damage_ratio < 1 y perdida proporcional
    r2 = _mode_direct_loss({"exposed_value": 1000.0, "intensity": 5.0, "intensity_50": 10.0, "k": 2.0})
    expected_ratio = (5.0 / 10.0) ** 2.0
    checks.append({
        "name": "direct_loss_partial_damage_matches_formula",
        "damage_ratio": r2["damage_ratio"], "expected": expected_ratio,
        "passed": abs(r2["damage_ratio"] - expected_ratio) < 1e-9,
    })

    # 3) direct_loss: intensidad mucho mayor al umbral se clippea a damage_ratio=1 (perdida total)
    r3 = _mode_direct_loss({"exposed_value": 500.0, "intensity": 100.0, "intensity_50": 10.0, "k": 2.0})
    checks.append({
        "name": "direct_loss_clips_at_full_damage",
        "damage_ratio": r3["damage_ratio"], "loss": r3["direct_loss"],
        "passed": abs(r3["damage_ratio"] - 1.0) < 1e-9 and abs(r3["direct_loss"] - 500.0) < 1e-9,
    })

    # 4) direct_loss: intensity_50 <= 0 lanza excepcion
    try:
        _mode_direct_loss({"exposed_value": 100.0, "intensity": 5.0, "intensity_50": 0.0})
        raised4 = False
    except ValueError:
        raised4 = True
    checks.append({"name": "zero_intensity_50_raises", "passed": raised4})

    # 5) indirect_loss: caso exacto (100/dia * 10 dias * multiplicador 1.5 = 1500)
    r5 = _mode_indirect_loss({"daily_output_loss": 100.0, "downtime_days": 10.0, "chain_multiplier": 1.5})
    checks.append({
        "name": "indirect_loss_exact",
        "loss": r5["indirect_loss"],
        "passed": abs(r5["indirect_loss"] - 1500.0) < 1e-9,
    })

    # 6) indirect_loss: chain_multiplier < 1 lanza excepcion
    try:
        _mode_indirect_loss({"daily_output_loss": 100.0, "downtime_days": 10.0, "chain_multiplier": 0.5})
        raised6 = False
    except ValueError:
        raised6 = True
    checks.append({"name": "chain_multiplier_below_one_raises", "passed": raised6})

    # 7) recovery_time: caso analitico simple, f0=0, target=1-1/e (~0.632) da recovery_time=tau exacto
    target = 1.0 - 1.0 / np.e
    r7 = _mode_recovery_time({"functionality_0": 0.0, "tau_days": 30.0, "target_functionality": float(target)})
    checks.append({
        "name": "recovery_time_at_one_tau",
        "recovery_days": r7["recovery_time_days"],
        "passed": abs(r7["recovery_time_days"] - 30.0) < 1e-6,
    })

    # 8) recovery_time: functionality_0 fuera de [0,1) lanza excepcion
    try:
        _mode_recovery_time({"functionality_0": 1.0, "tau_days": 30.0})
        raised8 = False
    except ValueError:
        raised8 = True
    checks.append({"name": "functionality_0_out_of_range_raises", "passed": raised8})

    # 9) cost_benefit_mitigation: mitigacion perfecta (annual_loss_with=0) con costo bajo da NPV>0 y recommended=True
    r9 = _mode_cost_benefit_mitigation({
        "mitigation_cost": 1000.0,
        "expected_annual_loss_without_mitigation": 500.0,
        "expected_annual_loss_with_mitigation": 0.0,
        "horizon_years": 10,
        "discount_rate": 0.05,
    })
    checks.append({
        "name": "effective_cheap_mitigation_has_positive_npv",
        "npv": r9["npv"], "recommended": r9["recommended"],
        "passed": r9["npv"] > 0 and r9["recommended"] is True,
    })

    # 10) cost_benefit_mitigation: perdida con mitigacion mayor que sin mitigacion lanza excepcion
    try:
        _mode_cost_benefit_mitigation({
            "mitigation_cost": 100.0,
            "expected_annual_loss_without_mitigation": 100.0,
            "expected_annual_loss_with_mitigation": 200.0,
        })
        raised10 = False
    except ValueError:
        raised10 = True
    checks.append({"name": "worse_mitigation_loss_raises", "passed": raised10})

    # 11) modo invalido lanza excepcion
    try:
        compute_disaster_economics("modo_invalido", {})
        invalid_raised = False
    except (KeyError, ValueError):
        invalid_raised = True
    checks.append({"name": "invalid_mode_raises", "passed": invalid_raised})

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_disaster_economics(mode, params=None):
    params = params or {}

    if mode == "direct_loss":
        return _mode_direct_loss(params)
    elif mode == "indirect_loss":
        return _mode_indirect_loss(params)
    elif mode == "recovery_time":
        return _mode_recovery_time(params)
    elif mode == "cost_benefit_mitigation":
        return _mode_cost_benefit_mitigation(params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(
            f"modo desconocido: {mode}. Use direct_loss | indirect_loss | "
            f"recovery_time | cost_benefit_mitigation | validate"
        )


try:
    from tool_registry import register_tool
    register_tool(
        name="disaster_economics_tool",
        schema=DISASTER_ECONOMICS_TOOL_SCHEMA,
        handler=lambda args: compute_disaster_economics(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    d = compute_disaster_economics("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de disaster_economics_tool.py pasaron OK.")
