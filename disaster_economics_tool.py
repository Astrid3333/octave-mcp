"""
disaster_economics_tool.py

Economia de desastres para gestion publica. Grupo "Economia Publica" de la
fase C de octave-mcp (junto a social_impact_tool, insurance_risk_tool).

Motor generico (sin catalogo de parametros macroeconomicos hardcodeados):
implementa cuatro metodos estandar de la literatura de economia de desastres
y evaluacion de inversion publica:

    - direct_indirect_loss: perdida indirecta via multiplicador economico
      regional (metodo estandar de "output multiplier", ver p.ej. Rose &
      Liao 2005, HAZUS-MH economic module). indirect = direct * (m - 1).
    - business_interruption_loss: perdida acumulada por interrupcion de
      actividad economica durante una recuperacion con forma exponencial
      hacia el nivel pre-desastre (integral cerrada, no requiere simulacion).
    - benefit_cost_ratio: BCR de una inversion de mitigacion, comparando el
      valor presente de la perdida anual esperada evitada (AAL, tipicamente
      salida de disaster_simulation_tool.monte_carlo_losses) contra el costo
      de la inversion, a una tasa de descuento y horizonte dados (metodo
      estandar de evaluacion social de proyectos, VAN/BCR).
    - gdp_impact_icor: impacto en el flujo de producto (GDP) de la
      destruccion de stock de capital, via el ratio incremental
      capital-producto (ICOR), metodo estandar en literatura de crecimiento
      y reconstruccion post-desastre (Hallegatte 2008, entre otros).
    - validate: suite de 10 checks

confidence_flag: "alta" para toda la mecanica (formulas cerradas, estandar
en la literatura). No hay catalogo de multiplicadores/ICOR por region o
sector: esos parametros los provee quien llama (surgen de datos regionales
reales, no de una tabla generica que el motor pudiera inventar).
"""

import math


DISASTER_ECONOMICS_TOOL_SCHEMA = {
    "name": "disaster_economics_tool",
    "description": (
        "Economia de desastres para evaluacion de politica publica: "
        "direct_indirect_loss (perdida indirecta via multiplicador economico "
        "regional, indirect=direct*(m-1)), business_interruption_loss (perdida "
        "acumulada por interrupcion de actividad economica durante una "
        "recuperacion exponencial hacia el nivel pre-desastre, integral cerrada), "
        "benefit_cost_ratio (BCR de una inversion de mitigacion: VAN de la "
        "perdida anual esperada evitada vs costo de inversion, a tasa de "
        "descuento y horizonte dados), gdp_impact_icor (impacto en el flujo de "
        "producto por destruccion de stock de capital via ratio incremental "
        "capital-producto ICOR), validate (suite de 10 checks). Motor generico: "
        "no trae catalogo de multiplicadores/ICOR por region o sector (los "
        "provee quien llama), confidence_flag 'alta' para toda la mecanica."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string"},
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


def _business_interruption_integral(direct_output_loss_rate, recovery_rate, horizon_years):
    """
    Modelo: la actividad economica cae a una fraccion (1 - direct_output_loss_rate)
    del nivel normal en t=0 y se recupera exponencialmente hacia el nivel normal
    con tasa recovery_rate: perdida(t) = direct_output_loss_rate * exp(-recovery_rate * t)
    (fraccion de output normal aun perdida en el tiempo t).

    Perdida acumulada (en unidades de "anios de output normal perdidos") en
    [0, horizon_years] = integral de perdida(t) dt
                        = direct_output_loss_rate / recovery_rate * (1 - exp(-recovery_rate*horizon_years))
    """
    if recovery_rate <= 0:
        raise ValueError("recovery_rate debe ser > 0")
    cumulative_loss_fraction_years = (direct_output_loss_rate / recovery_rate) * (
        1 - math.exp(-recovery_rate * horizon_years)
    )
    return cumulative_loss_fraction_years


def compute_disaster_economics(mode, params=None):
    params = params or {}

    if mode == "direct_indirect_loss":
        direct_loss = float(params["direct_loss"])
        multiplier = float(params["output_multiplier"])
        if multiplier < 1.0:
            raise ValueError("output_multiplier debe ser >= 1.0 (1.0 = sin efecto indirecto)")
        indirect_loss = direct_loss * (multiplier - 1.0)
        total_loss = direct_loss + indirect_loss
        return {
            "mode": "direct_indirect_loss",
            "direct_loss": direct_loss,
            "output_multiplier": multiplier,
            "indirect_loss": indirect_loss,
            "total_economic_loss": total_loss,
            "indirect_to_direct_ratio": indirect_loss / direct_loss if direct_loss > 0 else 0.0,
            "method": "output multiplier estandar (Rose & Liao 2005 / HAZUS-MH economic module)",
            "confidence_flag": "alta",
        }

    elif mode == "business_interruption_loss":
        direct_output_loss_rate = float(params["direct_output_loss_rate"])
        recovery_rate = float(params["recovery_rate_per_year"])
        horizon_years = float(params.get("horizon_years", 10))
        annual_output_normal = float(params.get("annual_output_normal", 1.0))

        cum_frac_years = _business_interruption_integral(direct_output_loss_rate, recovery_rate, horizon_years)
        total_loss = cum_frac_years * annual_output_normal
        half_life = math.log(2) / recovery_rate
        # fraccion de output aun perdida al final del horizonte
        residual_loss_fraction = direct_output_loss_rate * math.exp(-recovery_rate * horizon_years)

        return {
            "mode": "business_interruption_loss",
            "direct_output_loss_rate": direct_output_loss_rate,
            "recovery_rate_per_year": recovery_rate,
            "horizon_years": horizon_years,
            "recovery_half_life_years": half_life,
            "cumulative_loss_fraction_years": cum_frac_years,
            "total_business_interruption_loss": total_loss,
            "residual_loss_fraction_at_horizon": residual_loss_fraction,
            "method": "recuperacion exponencial hacia nivel pre-desastre, integral cerrada",
            "confidence_flag": "alta",
        }

    elif mode == "benefit_cost_ratio":
        aal_avoided = float(params["annual_expected_loss_avoided"])
        investment_cost = float(params["investment_cost"])
        discount_rate = float(params.get("discount_rate", 0.05))
        horizon_years = int(params.get("horizon_years", 30))
        maintenance_cost_annual = float(params.get("maintenance_cost_annual", 0.0))

        if discount_rate <= 0:
            pv_annuity_factor = float(horizon_years)
        else:
            pv_annuity_factor = (1 - (1 + discount_rate) ** (-horizon_years)) / discount_rate

        pv_avoided_losses = aal_avoided * pv_annuity_factor
        pv_maintenance = maintenance_cost_annual * pv_annuity_factor
        total_cost_pv = investment_cost + pv_maintenance
        bcr = pv_avoided_losses / total_cost_pv if total_cost_pv > 0 else float("inf")
        npv = pv_avoided_losses - total_cost_pv

        return {
            "mode": "benefit_cost_ratio",
            "annual_expected_loss_avoided": aal_avoided,
            "investment_cost": investment_cost,
            "discount_rate": discount_rate,
            "horizon_years": horizon_years,
            "pv_annuity_factor": pv_annuity_factor,
            "pv_avoided_losses": pv_avoided_losses,
            "pv_total_cost": total_cost_pv,
            "benefit_cost_ratio": bcr,
            "npv": npv,
            "recommendation": "inversion_justificada" if bcr > 1.0 else "inversion_no_justificada_por_bcr",
            "method": "VAN de perdida evitada vs costo, anualidad descontada estandar",
            "confidence_flag": "alta",
        }

    elif mode == "gdp_impact_icor":
        capital_destroyed = float(params["capital_stock_destroyed"])
        icor = float(params["icor"])
        if icor <= 0:
            raise ValueError("icor debe ser > 0")
        annual_gdp_flow_lost = capital_destroyed / icor
        recovery_years = float(params.get("reconstruction_years", 5))
        gdp_impact_cumulative = annual_gdp_flow_lost * recovery_years / 2.0
        # /2 asume reconstruccion lineal (perdida de flujo decrece linealmente a 0)

        baseline_gdp = params.get("baseline_annual_gdp")
        pct_of_gdp = None
        if baseline_gdp:
            pct_of_gdp = 100.0 * annual_gdp_flow_lost / float(baseline_gdp)

        return {
            "mode": "gdp_impact_icor",
            "capital_stock_destroyed": capital_destroyed,
            "icor": icor,
            "annual_gdp_flow_lost_year_1": annual_gdp_flow_lost,
            "reconstruction_years": recovery_years,
            "cumulative_gdp_impact_assuming_linear_reconstruction": gdp_impact_cumulative,
            "pct_of_baseline_gdp_year_1": pct_of_gdp,
            "method": "ratio incremental capital-producto (ICOR), estandar en literatura de reconstruccion post-desastre",
            "confidence_flag": "alta",
        }

    elif mode == "validate":
        checks = []

        # 1) indirect_loss = 0 cuando multiplier = 1.0
        r1 = compute_disaster_economics("direct_indirect_loss", {"direct_loss": 1000.0, "output_multiplier": 1.0})
        checks.append({
            "name": "zero_multiplier_effect_gives_zero_indirect_loss",
            "indirect_loss": r1["indirect_loss"],
            "passed": r1["indirect_loss"] == 0.0,
        })

        # 2) indirect_loss escala linealmente con direct_loss
        r2a = compute_disaster_economics("direct_indirect_loss", {"direct_loss": 1000.0, "output_multiplier": 1.5})
        r2b = compute_disaster_economics("direct_indirect_loss", {"direct_loss": 2000.0, "output_multiplier": 1.5})
        checks.append({
            "name": "indirect_loss_scales_linearly_with_direct_loss",
            "ratio": r2b["indirect_loss"] / r2a["indirect_loss"],
            "passed": abs(r2b["indirect_loss"] / r2a["indirect_loss"] - 2.0) < 1e-9,
        })

        # 3) multiplier < 1.0 lanza excepcion
        try:
            compute_disaster_economics("direct_indirect_loss", {"direct_loss": 100.0, "output_multiplier": 0.9})
            raised = False
        except ValueError:
            raised = True
        checks.append({"name": "multiplier_below_one_raises", "passed": raised})

        # 4) business_interruption: horizonte infinito converge a direct_output_loss_rate/recovery_rate
        r4 = compute_disaster_economics("business_interruption_loss", {
            "direct_output_loss_rate": 0.3, "recovery_rate_per_year": 1.0,
            "horizon_years": 50, "annual_output_normal": 1.0,
        })
        expected_limit = 0.3 / 1.0
        checks.append({
            "name": "business_interruption_converges_to_analytic_limit_at_long_horizon",
            "computed": r4["cumulative_loss_fraction_years"],
            "expected_limit": expected_limit,
            "passed": abs(r4["cumulative_loss_fraction_years"] - expected_limit) < 1e-6,
        })

        # 5) residual_loss_fraction decrece con horizon_years
        r5a = compute_disaster_economics("business_interruption_loss", {
            "direct_output_loss_rate": 0.3, "recovery_rate_per_year": 0.5, "horizon_years": 1,
        })
        r5b = compute_disaster_economics("business_interruption_loss", {
            "direct_output_loss_rate": 0.3, "recovery_rate_per_year": 0.5, "horizon_years": 5,
        })
        checks.append({
            "name": "residual_loss_fraction_decreases_over_time",
            "residual_1yr": r5a["residual_loss_fraction_at_horizon"],
            "residual_5yr": r5b["residual_loss_fraction_at_horizon"],
            "passed": r5b["residual_loss_fraction_at_horizon"] < r5a["residual_loss_fraction_at_horizon"],
        })

        # 6) recovery_rate <= 0 lanza excepcion
        try:
            compute_disaster_economics("business_interruption_loss", {
                "direct_output_loss_rate": 0.3, "recovery_rate_per_year": 0,
            })
            raised6 = False
        except ValueError:
            raised6 = True
        checks.append({"name": "zero_recovery_rate_raises", "passed": raised6})

        # 7) BCR > 1 cuando perdida evitada es grande relativo al costo; BCR < 1 en el caso opuesto
        r7a = compute_disaster_economics("benefit_cost_ratio", {
            "annual_expected_loss_avoided": 100000, "investment_cost": 500000,
            "discount_rate": 0.05, "horizon_years": 30,
        })
        r7b = compute_disaster_economics("benefit_cost_ratio", {
            "annual_expected_loss_avoided": 1000, "investment_cost": 500000,
            "discount_rate": 0.05, "horizon_years": 30,
        })
        checks.append({
            "name": "bcr_reflects_relative_magnitude_of_benefit_vs_cost",
            "bcr_favorable_case": r7a["benefit_cost_ratio"],
            "bcr_unfavorable_case": r7b["benefit_cost_ratio"],
            "passed": r7a["benefit_cost_ratio"] > 1.0 and r7b["benefit_cost_ratio"] < 1.0,
        })

        # 8) discount_rate = 0 usa anualidad simple (factor = horizon_years)
        r8 = compute_disaster_economics("benefit_cost_ratio", {
            "annual_expected_loss_avoided": 1000, "investment_cost": 1000,
            "discount_rate": 0.0, "horizon_years": 10,
        })
        checks.append({
            "name": "zero_discount_rate_uses_simple_annuity_factor",
            "pv_annuity_factor": r8["pv_annuity_factor"],
            "passed": r8["pv_annuity_factor"] == 10.0,
        })

        # 9) gdp_impact_icor: mayor ICOR (menos eficiente el capital) implica menor impacto en GDP flow
        r9a = compute_disaster_economics("gdp_impact_icor", {"capital_stock_destroyed": 1e6, "icor": 3.0})
        r9b = compute_disaster_economics("gdp_impact_icor", {"capital_stock_destroyed": 1e6, "icor": 6.0})
        checks.append({
            "name": "higher_icor_gives_lower_gdp_flow_impact",
            "gdp_impact_icor3": r9a["annual_gdp_flow_lost_year_1"],
            "gdp_impact_icor6": r9b["annual_gdp_flow_lost_year_1"],
            "passed": r9b["annual_gdp_flow_lost_year_1"] < r9a["annual_gdp_flow_lost_year_1"],
        })

        # 10) modo invalido lanza excepcion
        try:
            compute_disaster_economics("modo_invalido", {})
            invalid_raised = False
        except (KeyError, ValueError):
            invalid_raised = True
        checks.append({"name": "invalid_mode_raises", "passed": invalid_raised})

        all_passed = all(c["passed"] for c in checks)
        return {"checks": checks, "validation_passed": all_passed}

    else:
        raise ValueError(f"Modo desconocido para disaster_economics_tool: {mode}")
