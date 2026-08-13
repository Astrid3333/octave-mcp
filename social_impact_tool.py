"""
social_impact_tool.py

Impacto social de desastres y de inversion publica. Grupo "Economia Publica"
de la fase C de octave-mcp (junto a disaster_economics_tool, insurance_risk_tool).

Motor generico, cuatro metodos estandar de la literatura de vulnerabilidad
social y evaluacion de impacto:

    - social_vulnerability_index: indice de vulnerabilidad social (SoVI,
      Cutter, Boruff & Shirley 2003) via suma de z-scores de indicadores
      socioeconomicos, con signo configurable por indicador (algunos
      aumentan vulnerabilidad, otros la reducen).
    - displacement_estimate: estimacion de poblacion desplazada y unidades
      de vivienda temporal requeridas, a partir de conteos de dano
      habitacional por severidad (menor/mayor/destruido) y ocupacion
      promedio por vivienda (metodo estandar en evaluacion de dano post-
      desastre, p.ej. HAZUS-MH housing damage module).
    - equity_weighted_impact: pondera una perdida o dano economico por un
      factor de vulnerabilidad social, para priorizar inversion publica
      hacia poblaciones mas vulnerables (metodo de "equity weighting" en
      evaluacion social de proyectos, ver p.ej. HM Treasury Green Book).
    - casualty_estimate: estimacion simplificada de victimas (fallecidos/
      heridos) a partir de fraccion de estructuras colapsadas, ocupacion y
      factor de hora del dia, siguiendo la logica del modulo de victimas de
      HAZUS-MH (simplificado, sin curvas de fragilidad especificas por tipo
      estructural).
    - validate: suite de 10 checks

confidence_flag: "alta" para la mecanica de cada metodo (formulas
estandar de la literatura citada). No hay catalogo de indicadores/pesos
por region: los indicadores, pesos y tasas los provee quien llama.
"""

import math


SOCIAL_IMPACT_TOOL_SCHEMA = {
    "name": "social_impact_tool",
    "description": (
        "Impacto social de desastres y de inversion publica: "
        "social_vulnerability_index (indice SoVI via suma de z-scores de "
        "indicadores socioeconomicos con signo configurable por indicador), "
        "displacement_estimate (poblacion desplazada y unidades de vivienda "
        "temporal requeridas a partir de dano habitacional por severidad y "
        "ocupacion promedio), equity_weighted_impact (pondera perdida/dano "
        "economico por un factor de vulnerabilidad social para priorizar "
        "inversion), casualty_estimate (estimacion simplificada de victimas a "
        "partir de fraccion de estructuras colapsadas, ocupacion y hora del "
        "dia, logica HAZUS-MH simplificada), validate (suite de 10 checks). "
        "Motor generico: no trae catalogo de indicadores/pesos por region "
        "(los provee quien llama), confidence_flag 'alta' para la mecanica."
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


def _zscore(value, mean, std):
    if std == 0:
        return 0.0
    return (value - mean) / std


def compute_social_impact(mode, params=None):
    params = params or {}

    if mode == "social_vulnerability_index":
        # indicators: lista de {"name","value","population_mean","population_std","direction"}
        # direction: "increases_vulnerability" (+z) o "decreases_vulnerability" (-z)
        indicators = params["indicators"]
        components = []
        total_z = 0.0
        for ind in indicators:
            z = _zscore(float(ind["value"]), float(ind["population_mean"]), float(ind["population_std"]))
            direction = ind.get("direction", "increases_vulnerability")
            signed_z = z if direction == "increases_vulnerability" else -z
            components.append({
                "name": ind["name"], "z_score": z, "direction": direction, "signed_z_score": signed_z,
            })
            total_z += signed_z

        n = len(indicators)
        avg_z = total_z / n if n > 0 else 0.0

        if avg_z >= 1.0:
            band = "muy_alta"
        elif avg_z >= 0.5:
            band = "alta"
        elif avg_z >= -0.5:
            band = "media"
        elif avg_z >= -1.0:
            band = "baja"
        else:
            band = "muy_baja"

        return {
            "mode": "social_vulnerability_index",
            "n_indicators": n,
            "components": components,
            "sovi_index_sum": total_z,
            "sovi_index_avg": avg_z,
            "vulnerability_band": band,
            "method": "suma de z-scores con signo (SoVI, Cutter Boruff & Shirley 2003)",
            "confidence_flag": "alta",
        }

    elif mode == "displacement_estimate":
        housing_damage = params["housing_damage_counts"]  # {"minor":n,"major":n,"destroyed":n}
        occupancy_per_unit = float(params.get("avg_occupancy_per_unit", 3.0))
        # fracciones estandar de inhabitabilidad temporal por severidad (HAZUS-MH simplificado)
        uninhabitable_fraction = params.get("uninhabitable_fraction", {
            "minor": 0.0, "major": 0.6, "destroyed": 1.0,
        })

        minor = int(housing_damage.get("minor", 0))
        major = int(housing_damage.get("major", 0))
        destroyed = int(housing_damage.get("destroyed", 0))

        units_uninhabitable = (
            minor * uninhabitable_fraction.get("minor", 0.0)
            + major * uninhabitable_fraction.get("major", 0.6)
            + destroyed * uninhabitable_fraction.get("destroyed", 1.0)
        )
        displaced_population = units_uninhabitable * occupancy_per_unit

        return {
            "mode": "displacement_estimate",
            "housing_damage_counts": {"minor": minor, "major": major, "destroyed": destroyed},
            "avg_occupancy_per_unit": occupancy_per_unit,
            "uninhabitable_fraction_used": uninhabitable_fraction,
            "housing_units_uninhabitable": units_uninhabitable,
            "estimated_displaced_population": displaced_population,
            "temporary_housing_units_needed": math.ceil(units_uninhabitable),
            "method": "fracciones de inhabitabilidad por severidad, logica HAZUS-MH housing damage module",
            "confidence_flag": "alta",
        }

    elif mode == "equity_weighted_impact":
        raw_impact = float(params["raw_impact_value"])
        vulnerability_index = float(params["vulnerability_index"])
        # peso de equidad: 1 + alpha * vulnerability_index (alpha configurable, default 0.5)
        # a mayor vulnerabilidad, mayor peso relativo del impacto (metodo HM Treasury Green Book)
        alpha = float(params.get("equity_weight_alpha", 0.5))
        equity_weight = 1.0 + alpha * vulnerability_index
        weighted_impact = raw_impact * equity_weight

        return {
            "mode": "equity_weighted_impact",
            "raw_impact_value": raw_impact,
            "vulnerability_index": vulnerability_index,
            "equity_weight_alpha": alpha,
            "equity_weight_applied": equity_weight,
            "equity_weighted_impact": weighted_impact,
            "method": "equity weighting lineal sobre indice de vulnerabilidad (HM Treasury Green Book)",
            "confidence_flag": "alta",
        }

    elif mode == "casualty_estimate":
        structures_collapsed = int(params["structures_collapsed"])
        avg_occupants_per_structure = float(params["avg_occupants_per_structure"])
        time_of_day_occupancy_factor = float(params.get("time_of_day_occupancy_factor", 1.0))
        # fracciones estandar simplificadas de resultado dado colapso estructural
        # (fatalidad, herida grave, herida leve, ilesa), suman 1.0
        outcome_fractions = params.get("outcome_fractions_given_collapse", {
            "fatality": 0.10, "severe_injury": 0.20, "minor_injury": 0.30, "uninjured": 0.40,
        })
        total_frac = sum(outcome_fractions.values())
        if abs(total_frac - 1.0) > 1e-6:
            raise ValueError(f"outcome_fractions_given_collapse debe sumar 1.0 (suma actual: {total_frac})")

        exposed_population = structures_collapsed * avg_occupants_per_structure * time_of_day_occupancy_factor

        results = {k: exposed_population * v for k, v in outcome_fractions.items()}

        return {
            "mode": "casualty_estimate",
            "structures_collapsed": structures_collapsed,
            "avg_occupants_per_structure": avg_occupants_per_structure,
            "time_of_day_occupancy_factor": time_of_day_occupancy_factor,
            "exposed_population_estimate": exposed_population,
            "outcome_fractions_used": outcome_fractions,
            "estimated_outcomes": results,
            "method": "logica simplificada de modulo de victimas HAZUS-MH (sin curvas de fragilidad especificas por tipo estructural)",
            "confidence_flag": "media",
            "note": "estimacion gruesa; para analisis serio usar fragility curves especificas del tipo estructural y ocupacion real medida.",
        }

    elif mode == "validate":
        checks = []

        # 1) SoVI: indicador en la media exacta da z=0
        r1 = compute_social_impact("social_vulnerability_index", {
            "indicators": [{"name": "poverty_rate", "value": 20, "population_mean": 20, "population_std": 5,
                             "direction": "increases_vulnerability"}]
        })
        checks.append({
            "name": "sovi_indicator_at_mean_gives_zero_zscore",
            "z": r1["components"][0]["z_score"],
            "passed": abs(r1["components"][0]["z_score"]) < 1e-9,
        })

        # 2) SoVI: direction "decreases_vulnerability" invierte el signo
        r2 = compute_social_impact("social_vulnerability_index", {
            "indicators": [{"name": "income", "value": 30, "population_mean": 20, "population_std": 5,
                             "direction": "decreases_vulnerability"}]
        })
        checks.append({
            "name": "sovi_decreases_vulnerability_direction_flips_sign",
            "signed_z": r2["components"][0]["signed_z_score"],
            "passed": r2["components"][0]["signed_z_score"] < 0,
        })

        # 3) SoVI: banda muy_alta cuando avg_z >= 1.0
        r3 = compute_social_impact("social_vulnerability_index", {
            "indicators": [
                {"name": "a", "value": 30, "population_mean": 20, "population_std": 5, "direction": "increases_vulnerability"},
                {"name": "b", "value": 30, "population_mean": 20, "population_std": 5, "direction": "increases_vulnerability"},
            ]
        })
        checks.append({
            "name": "sovi_high_zscores_give_muy_alta_band",
            "avg_z": r3["sovi_index_avg"],
            "band": r3["vulnerability_band"],
            "passed": r3["vulnerability_band"] == "muy_alta",
        })

        # 4) displacement: destroyed=100% inhabitable
        r4 = compute_social_impact("displacement_estimate", {
            "housing_damage_counts": {"minor": 0, "major": 0, "destroyed": 50},
            "avg_occupancy_per_unit": 4.0,
        })
        checks.append({
            "name": "displacement_destroyed_units_fully_uninhabitable",
            "units_uninhabitable": r4["housing_units_uninhabitable"],
            "passed": r4["housing_units_uninhabitable"] == 50.0,
        })

        # 5) displacement: poblacion desplazada = unidades * ocupacion
        checks.append({
            "name": "displaced_population_equals_units_times_occupancy",
            "computed": r4["estimated_displaced_population"],
            "expected": 200.0,
            "passed": abs(r4["estimated_displaced_population"] - 200.0) < 1e-9,
        })

        # 6) displacement: minor damage (fraccion 0 por defecto) no desplaza a nadie
        r6 = compute_social_impact("displacement_estimate", {
            "housing_damage_counts": {"minor": 100, "major": 0, "destroyed": 0},
            "avg_occupancy_per_unit": 4.0,
        })
        checks.append({
            "name": "minor_damage_default_zero_displacement",
            "displaced": r6["estimated_displaced_population"],
            "passed": r6["estimated_displaced_population"] == 0.0,
        })

        # 7) equity_weighted_impact: vulnerability_index=0 no cambia el impacto (weight=1)
        r7 = compute_social_impact("equity_weighted_impact", {
            "raw_impact_value": 1000.0, "vulnerability_index": 0.0,
        })
        checks.append({
            "name": "zero_vulnerability_gives_unweighted_impact",
            "weighted": r7["equity_weighted_impact"],
            "passed": abs(r7["equity_weighted_impact"] - 1000.0) < 1e-9,
        })

        # 8) equity_weighted_impact: mayor vulnerabilidad -> mayor peso
        r8a = compute_social_impact("equity_weighted_impact", {"raw_impact_value": 1000.0, "vulnerability_index": 1.0})
        r8b = compute_social_impact("equity_weighted_impact", {"raw_impact_value": 1000.0, "vulnerability_index": 2.0})
        checks.append({
            "name": "higher_vulnerability_gives_higher_weighted_impact",
            "weighted_v1": r8a["equity_weighted_impact"],
            "weighted_v2": r8b["equity_weighted_impact"],
            "passed": r8b["equity_weighted_impact"] > r8a["equity_weighted_impact"],
        })

        # 9) casualty_estimate: outcome_fractions que no suman 1.0 lanzan excepcion
        try:
            compute_social_impact("casualty_estimate", {
                "structures_collapsed": 10, "avg_occupants_per_structure": 3,
                "outcome_fractions_given_collapse": {"fatality": 0.5, "uninjured": 0.6},
            })
            raised9 = False
        except ValueError:
            raised9 = True
        checks.append({"name": "casualty_outcome_fractions_must_sum_to_one", "passed": raised9})

        # 9b) casualty_estimate: suma de outcomes = poblacion expuesta
        r9b = compute_social_impact("casualty_estimate", {
            "structures_collapsed": 10, "avg_occupants_per_structure": 5,
        })
        sum_outcomes = sum(r9b["estimated_outcomes"].values())
        checks.append({
            "name": "casualty_outcomes_sum_equals_exposed_population",
            "sum_outcomes": sum_outcomes,
            "exposed": r9b["exposed_population_estimate"],
            "passed": abs(sum_outcomes - r9b["exposed_population_estimate"]) < 1e-6,
        })

        # 10) modo invalido lanza excepcion
        try:
            compute_social_impact("modo_invalido", {})
            invalid_raised = False
        except (KeyError, ValueError):
            invalid_raised = True
        checks.append({"name": "invalid_mode_raises", "passed": invalid_raised})

        all_passed = all(c["passed"] for c in checks)
        return {"checks": checks, "validation_passed": all_passed}

    else:
        raise ValueError(f"Modo desconocido para social_impact_tool: {mode}")
