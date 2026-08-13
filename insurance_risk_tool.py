"""
insurance_risk_tool.py

Seguros y reaseguro de catastrofes para gestion publica de riesgos. Cierra
el grupo "Economia Publica" de la fase C de octave-mcp (junto a
disaster_economics_tool, social_impact_tool). Complementa a
disaster_simulation_tool: donde ese motor genera la distribucion de
perdida agregada, este tool aplica sobre esa distribucion (o sobre
parametros equivalentes) la mecanica actuarial estandar de pricing.

Motor generico, cuatro metodos estandar de la practica actuarial y de
reaseguro de catastrofes:

    - pure_premium: prima pura (perdida anual esperada) mas cargas de gasto
      y margen de utilidad, sobre una muestra de perdidas simulada (mismo
      modelo Poisson-LogNormal que disaster_simulation_tool) o provista
      directamente. Formula estandar: prima_comercial = prima_pura / (1 -
      expense_ratio - profit_margin).
    - excess_of_loss_layer: pricing de una capa de reaseguro XoL (exceso de
      perdida) [attachment, attachment+limit]: perdida esperada de la capa =
      E[min(max(L-attachment,0), limit)], via Monte Carlo sobre la misma
      distribucion de perdida agregada (metodo estandar de pricing de
      reaseguro no proporcional).
    - cat_bond_pricing: pricing simplificado de un bono catastrofico:
      spread de riesgo proporcional a la perdida esperada de la capa
      cubierta mas un multiplicador de mercado (metodo estandar simplificado,
      cupon = perdida_esperada_capa/principal + spread_mercado).
    - loss_ratio_analysis: analisis de rentabilidad de una cartera dado
      primas cobradas y siniestros incurridos historicos: loss ratio,
      expense ratio, combined ratio (metodo estandar de analisis actuarial
      de cartera).
    - validate: suite de 10 checks

confidence_flag: "alta" para toda la mecanica (formulas y metodo de
simulacion estandar). El motor no trae catalogo de tasas de mercado,
expense ratios o spreads: esos parametros los provee quien llama.
"""

import math
import numpy as np


INSURANCE_RISK_TOOL_SCHEMA = {
    "name": "insurance_risk_tool",
    "description": (
        "Seguros y reaseguro de catastrofes: pure_premium (prima pura mas "
        "cargas de gasto y margen de utilidad, sobre una distribucion de "
        "perdida Poisson-LogNormal simulada o provista, prima_comercial = "
        "prima_pura/(1-expense_ratio-profit_margin)), excess_of_loss_layer "
        "(pricing de una capa de reaseguro XoL via Monte Carlo, perdida "
        "esperada de capa = E[min(max(L-attachment,0),limit)]), "
        "cat_bond_pricing (pricing simplificado de bono catastrofico: cupon = "
        "perdida esperada de la capa cubierta/principal + spread de mercado), "
        "loss_ratio_analysis (loss ratio, expense ratio y combined ratio de "
        "una cartera dado primas y siniestros historicos), validate (suite de "
        "10 checks). Motor generico: no trae catalogo de tasas de mercado ni "
        "expense ratios (los provee quien llama), confidence_flag 'alta'."
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


def _rng(seed):
    return np.random.default_rng(seed)


def _simulate_losses(lam, mu, sigma, n_years, seed):
    rng = _rng(seed)
    n_events = rng.poisson(lam=lam, size=n_years)
    losses = np.zeros(n_years, dtype=float)
    total_events = int(n_events.sum())
    if total_events > 0:
        severities = rng.lognormal(mean=mu, sigma=sigma, size=total_events)
        idx = 0
        for year in range(n_years):
            k = n_events[year]
            if k > 0:
                losses[year] = severities[idx: idx + k].sum()
                idx += k
    return losses


def _get_loss_sample(params):
    """Toma 'losses' directo si viene, si no simula con lambda/mu/sigma."""
    if "losses" in params:
        return np.array(params["losses"], dtype=float), None
    lam = float(params["lambda_annual"])
    mu = float(params["mu_severity"])
    sigma = float(params["sigma_severity"])
    n_years = int(params.get("n_years", 100000))
    seed = params.get("seed", 42)
    return _simulate_losses(lam, mu, sigma, n_years, seed), seed


def compute_insurance_risk(mode, params=None):
    params = params or {}

    if mode == "pure_premium":
        losses, seed = _get_loss_sample(params)
        expense_ratio = float(params.get("expense_ratio", 0.20))
        profit_margin = float(params.get("profit_margin", 0.10))
        if expense_ratio + profit_margin >= 1.0:
            raise ValueError("expense_ratio + profit_margin debe ser < 1.0")

        pure_premium = float(losses.mean())
        commercial_premium = pure_premium / (1.0 - expense_ratio - profit_margin)
        loading = commercial_premium - pure_premium

        return {
            "mode": "pure_premium",
            "n_years_sample": int(len(losses)),
            "seed": seed,
            "pure_premium": pure_premium,
            "expense_ratio": expense_ratio,
            "profit_margin": profit_margin,
            "loading": loading,
            "commercial_premium": commercial_premium,
            "method": "prima pura + carga estandar (expense + profit loading)",
            "confidence_flag": "alta",
        }

    elif mode == "excess_of_loss_layer":
        losses, seed = _get_loss_sample(params)
        attachment = float(params["attachment_point"])
        limit = float(params["layer_limit"])
        if limit <= 0:
            raise ValueError("layer_limit debe ser > 0")

        layer_losses = np.clip(losses - attachment, 0, limit)
        expected_layer_loss = float(layer_losses.mean())
        prob_attachment = float((losses > attachment).mean())
        prob_exhaustion = float((losses >= attachment + limit).mean())
        rate_on_line = expected_layer_loss / limit  # metrica estandar de reaseguro XoL

        return {
            "mode": "excess_of_loss_layer",
            "n_years_sample": int(len(losses)),
            "seed": seed,
            "attachment_point": attachment,
            "layer_limit": limit,
            "layer_top": attachment + limit,
            "expected_layer_loss": expected_layer_loss,
            "probability_layer_attaches": prob_attachment,
            "probability_layer_exhausted": prob_exhaustion,
            "rate_on_line": rate_on_line,
            "method": "E[min(max(L-attachment,0),limit)] via Monte Carlo sobre distribucion de perdida agregada",
            "confidence_flag": "alta",
        }

    elif mode == "cat_bond_pricing":
        losses, seed = _get_loss_sample(params)
        attachment = float(params["attachment_point"])
        limit = float(params["layer_limit"])
        principal = float(params["bond_principal"])
        market_spread = float(params.get("market_spread", 0.03))

        layer_losses = np.clip(losses - attachment, 0, limit)
        expected_layer_loss = float(layer_losses.mean())
        expected_loss_rate = expected_layer_loss / principal if principal > 0 else float("inf")
        prob_attachment = float((losses > attachment).mean())

        coupon_rate = expected_loss_rate + market_spread

        return {
            "mode": "cat_bond_pricing",
            "n_years_sample": int(len(losses)),
            "seed": seed,
            "attachment_point": attachment,
            "layer_limit": limit,
            "bond_principal": principal,
            "expected_layer_loss": expected_layer_loss,
            "expected_loss_rate": expected_loss_rate,
            "probability_of_attachment": prob_attachment,
            "market_spread": market_spread,
            "coupon_rate": coupon_rate,
            "method": "pricing simplificado: cupon = tasa de perdida esperada de la capa + spread de mercado",
            "confidence_flag": "alta",
            "note": "modelo simplificado; pricing de mercado real incorpora ademas costo de capital del inversor, liquidez y correlacion con otros riesgos de su portafolio.",
        }

    elif mode == "loss_ratio_analysis":
        premiums_earned = float(params["premiums_earned"])
        losses_incurred = float(params["losses_incurred"])
        expenses_incurred = float(params.get("expenses_incurred", 0.0))

        if premiums_earned <= 0:
            raise ValueError("premiums_earned debe ser > 0")

        loss_ratio = losses_incurred / premiums_earned
        expense_ratio = expenses_incurred / premiums_earned
        combined_ratio = loss_ratio + expense_ratio
        underwriting_result = premiums_earned - losses_incurred - expenses_incurred

        return {
            "mode": "loss_ratio_analysis",
            "premiums_earned": premiums_earned,
            "losses_incurred": losses_incurred,
            "expenses_incurred": expenses_incurred,
            "loss_ratio": loss_ratio,
            "expense_ratio": expense_ratio,
            "combined_ratio": combined_ratio,
            "underwriting_result": underwriting_result,
            "profitable": combined_ratio < 1.0,
            "method": "loss ratio / expense ratio / combined ratio estandar de analisis actuarial de cartera",
            "confidence_flag": "alta",
        }

    elif mode == "validate":
        checks = []

        # 1) pure_premium ~ media de la muestra de perdidas provista directamente
        losses_fixed = [10.0, 20.0, 30.0, 40.0]
        r1 = compute_insurance_risk("pure_premium", {"losses": losses_fixed, "expense_ratio": 0.0, "profit_margin": 0.0})
        checks.append({
            "name": "pure_premium_equals_mean_when_no_loading",
            "computed": r1["pure_premium"],
            "expected": 25.0,
            "passed": abs(r1["pure_premium"] - 25.0) < 1e-9,
        })

        # 2) commercial_premium > pure_premium cuando hay cargas
        r2 = compute_insurance_risk("pure_premium", {"losses": losses_fixed, "expense_ratio": 0.2, "profit_margin": 0.1})
        checks.append({
            "name": "commercial_premium_exceeds_pure_premium_with_loading",
            "pure": r2["pure_premium"], "commercial": r2["commercial_premium"],
            "passed": r2["commercial_premium"] > r2["pure_premium"],
        })

        # 3) expense_ratio + profit_margin >= 1.0 lanza excepcion
        try:
            compute_insurance_risk("pure_premium", {"losses": losses_fixed, "expense_ratio": 0.6, "profit_margin": 0.5})
            raised3 = False
        except ValueError:
            raised3 = True
        checks.append({"name": "excessive_loading_raises", "passed": raised3})

        # 4) excess_of_loss_layer: capa que nunca se toca da perdida esperada 0
        losses_low = [10.0, 15.0, 20.0, 12.0, 18.0]
        r4 = compute_insurance_risk("excess_of_loss_layer", {
            "losses": losses_low, "attachment_point": 1000.0, "layer_limit": 500.0,
        })
        checks.append({
            "name": "layer_far_above_losses_has_zero_expected_loss",
            "expected_layer_loss": r4["expected_layer_loss"],
            "passed": r4["expected_layer_loss"] == 0.0,
        })

        # 5) excess_of_loss_layer: capa que siempre se agota da perdida esperada = limit
        losses_high = [1000.0, 1000.0, 1000.0]
        r5 = compute_insurance_risk("excess_of_loss_layer", {
            "losses": losses_high, "attachment_point": 0.0, "layer_limit": 200.0,
        })
        checks.append({
            "name": "layer_always_exhausted_gives_expected_loss_equal_limit",
            "expected_layer_loss": r5["expected_layer_loss"],
            "passed": abs(r5["expected_layer_loss"] - 200.0) < 1e-9,
        })

        # 6) rate_on_line entre 0 y 1 (definicion: expected_layer_loss/limit, y layer_loss <= limit siempre)
        checks.append({
            "name": "rate_on_line_bounded_between_zero_and_one",
            "rate_on_line": r5["rate_on_line"],
            "passed": 0.0 <= r5["rate_on_line"] <= 1.0,
        })

        # 7) cat_bond coupon_rate >= market_spread (expected_loss_rate siempre >= 0)
        r7 = compute_insurance_risk("cat_bond_pricing", {
            "losses": losses_high, "attachment_point": 0.0, "layer_limit": 200.0,
            "bond_principal": 1000.0, "market_spread": 0.03,
        })
        checks.append({
            "name": "cat_bond_coupon_at_least_market_spread",
            "coupon_rate": r7["coupon_rate"], "market_spread": 0.03,
            "passed": r7["coupon_rate"] >= 0.03 - 1e-9,
        })

        # 8) loss_ratio_analysis: combined_ratio < 1.0 marca profitable=True
        r8 = compute_insurance_risk("loss_ratio_analysis", {
            "premiums_earned": 1000.0, "losses_incurred": 400.0, "expenses_incurred": 200.0,
        })
        checks.append({
            "name": "combined_ratio_below_one_marks_profitable",
            "combined_ratio": r8["combined_ratio"], "profitable": r8["profitable"],
            "passed": r8["combined_ratio"] < 1.0 and r8["profitable"] is True,
        })

        # 9) loss_ratio_analysis: premiums_earned <= 0 lanza excepcion
        try:
            compute_insurance_risk("loss_ratio_analysis", {
                "premiums_earned": 0.0, "losses_incurred": 100.0,
            })
            raised9 = False
        except ValueError:
            raised9 = True
        checks.append({"name": "zero_premiums_earned_raises", "passed": raised9})

        # 10) modo invalido lanza excepcion
        try:
            compute_insurance_risk("modo_invalido", {})
            invalid_raised = False
        except (KeyError, ValueError):
            invalid_raised = True
        checks.append({"name": "invalid_mode_raises", "passed": invalid_raised})

        all_passed = all(c["passed"] for c in checks)
        return {"checks": checks, "validation_passed": all_passed}

    else:
        raise ValueError(f"Modo desconocido para insurance_risk_tool: {mode}")
