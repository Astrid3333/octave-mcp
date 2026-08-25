"""
ethical_food_advisor_tool.py

Herramienta MCP que calcula puntajes cuantitativos (escala 0-10, 10=mejor) para
3 dimensiones eticas de un alimento, mas un puntaje compuesto ponderado:

    - environmental_footprint_score : huella de GEI/tierra/agua vs. catalogo de categorias
    - animal_welfare_score          : sistema de crianza vs. catalogo inspirado en las "Cinco Libertades"
    - labor_conditions_score        : salario relativo/horas/sindicalizacion/seguridad
    - composite_score               : combinacion ponderada de las 3 (pesos configurables, se renormalizan
                                       automaticamente si se omite una dimension, ej. alimentos vegetales
                                       sin bienestar animal aplicable)
    - validate                      : 10 chequeos de consistencia (monotonia, cotas, exactitud de la suma ponderada)

IMPORTANTE - nivel de confianza:
El catalogo ambiental usa valores APROXIMADOS y de ORDEN DE MAGNITUD tomados de
fuentes ampliamente citadas en literatura de ciclo de vida (Poore & Nemecek 2018
para GEI/uso de tierra; Mekonnen & Hoekstra 2012 para huella hidrica), como
promedios GLOBALES por categoria de alimento -- no mediciones de un producto o
region especifica. El catalogo de bienestar animal es una escala cualitativa
propia inspirada en las Cinco Libertades (Farm Animal Welfare Council), no un
estandar certificado. Cada resultado trae "confidence_note" aclarando esto.
"""

import math

# ---------------------------------------------------------------------------
# CATALOGO AMBIENTAL (valores aproximados, promedios globales de literatura)
# ghg_kg_co2eq_per_kg, land_m2_per_kg, water_l_per_kg
# ---------------------------------------------------------------------------
_ENV_CATALOG = {
    "beef": {"ghg": 60.0, "land": 326.0, "water": 15415.0},
    "lamb_mutton": {"ghg": 24.0, "land": 185.0, "water": 10412.0},
    "cheese": {"ghg": 21.0, "land": 41.0, "water": 5605.0},
    "pork": {"ghg": 7.0, "land": 11.0, "water": 5988.0},
    "poultry": {"ghg": 6.0, "land": 7.0, "water": 4325.0},
    "fish_farmed": {"ghg": 5.0, "land": 4.0, "water": 3691.0},
    "eggs": {"ghg": 4.5, "land": 6.0, "water": 3265.0},
    "rice": {"ghg": 4.0, "land": 2.0, "water": 2497.0},
    "milk": {"ghg": 3.0, "land": 9.0, "water": 1020.0},
    "tofu": {"ghg": 2.0, "land": 2.2, "water": 2515.0},
    "vegetables": {"ghg": 2.0, "land": 0.3, "water": 322.0},
    "legumes": {"ghg": 0.9, "land": 7.3, "water": 4055.0},
    "fruit": {"ghg": 1.1, "land": 0.7, "water": 962.0},
    "nuts": {"ghg": 0.3, "land": 7.9, "water": 9063.0},
}

# ---------------------------------------------------------------------------
# CATALOGO DE BIENESTAR ANIMAL (escala propia 0-10, inspirada en las Cinco
# Libertades: de hambre/sed, de incomodidad, de dolor/enfermedad, de expresar
# comportamiento natural, de miedo/angustia)
# ---------------------------------------------------------------------------
_ANIMAL_WELFARE_CATALOG = {
    "battery_cage": 1.5,
    "conventional_indoor_confinement": 2.5,
    "enriched_cage": 3.0,
    "cage_free_indoor": 4.5,
    "free_range": 6.5,
    "pasture_raised": 8.0,
    "certified_organic_pasture": 9.0,
}


def _clip(x, lo=0.0, hi=10.0):
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# 1) HUELLA AMBIENTAL
# ---------------------------------------------------------------------------
def _environmental_footprint_score(food_category=None, ghg_kg_co2eq_per_kg=None,
                                    land_m2_per_kg=None, water_l_per_kg=None,
                                    weight_ghg=0.5, weight_land=0.25, weight_water=0.25):
    """
    Normaliza cada metrica en escala logaritmica contra el rango [min, max] del
    catalogo (log porque las huellas de GEI/agua/tierra varian ordenes de
    magnitud entre categorias, ej. carne de vacuno vs. verduras), y combina
    las 3 con pesos configurables (se normalizan a sumar 1). 10 = menor impacto.
    """
    if food_category is not None:
        if food_category not in _ENV_CATALOG:
            raise ValueError(f"food_category debe ser uno de {sorted(_ENV_CATALOG.keys())}")
        entry = _ENV_CATALOG[food_category]
        ghg = entry["ghg"] if ghg_kg_co2eq_per_kg is None else ghg_kg_co2eq_per_kg
        land = entry["land"] if land_m2_per_kg is None else land_m2_per_kg
        water = entry["water"] if water_l_per_kg is None else water_l_per_kg
    else:
        if ghg_kg_co2eq_per_kg is None or land_m2_per_kg is None or water_l_per_kg is None:
            raise ValueError(
                "Sin food_category hay que pasar ghg_kg_co2eq_per_kg, land_m2_per_kg y water_l_per_kg"
            )
        ghg, land, water = ghg_kg_co2eq_per_kg, land_m2_per_kg, water_l_per_kg

    total_weight = weight_ghg + weight_land + weight_water
    if total_weight <= 0:
        raise ValueError("La suma de los pesos debe ser > 0")
    w_ghg, w_land, w_water = weight_ghg / total_weight, weight_land / total_weight, weight_water / total_weight

    def _log_normalize(value, catalog_key):
        values = [v[catalog_key] for v in _ENV_CATALOG.values()]
        lo, hi = min(values), max(values)
        v_clamped = max(min(value, hi), lo)
        if hi == lo:
            return 10.0
        return 10.0 * (math.log(hi) - math.log(v_clamped)) / (math.log(hi) - math.log(lo))

    ghg_score = _log_normalize(ghg, "ghg")
    land_score = _log_normalize(land, "land")
    water_score = _log_normalize(water, "water")

    composite = w_ghg * ghg_score + w_land * land_score + w_water * water_score

    return {
        "dimension": "environmental_footprint",
        "food_category": food_category,
        "ghg_kg_co2eq_per_kg": ghg,
        "land_m2_per_kg": land,
        "water_l_per_kg": water,
        "ghg_score": ghg_score,
        "land_score": land_score,
        "water_score": water_score,
        "score": _clip(composite),
        "confidence_note": (
            "Catalogo con promedios globales aproximados de literatura de ciclo de vida "
            "ampliamente citada (Poore & Nemecek 2018 para GEI/tierra, Mekonnen & Hoekstra 2012 "
            "para agua). No representa un producto, granja o region especifica -- usar como "
            "orden de magnitud comparativo entre categorias."
        ),
    }


# ---------------------------------------------------------------------------
# 2) BIENESTAR ANIMAL
# ---------------------------------------------------------------------------
def _animal_welfare_score(farming_system):
    if farming_system not in _ANIMAL_WELFARE_CATALOG:
        raise ValueError(f"farming_system debe ser uno de {sorted(_ANIMAL_WELFARE_CATALOG.keys())}")
    score = _ANIMAL_WELFARE_CATALOG[farming_system]
    return {
        "dimension": "animal_welfare",
        "farming_system": farming_system,
        "score": score,
        "confidence_note": (
            "Escala propia 0-10 inspirada en las Cinco Libertades del Farm Animal Welfare Council "
            "(hambre/sed, incomodidad, dolor/enfermedad, comportamiento natural, miedo/angustia). "
            "No es un puntaje de una certificacion oficial ni una auditoria de granja real; "
            "es una jerarquia cualitativa razonable entre sistemas de crianza tipicos."
        ),
    }


# ---------------------------------------------------------------------------
# 3) CONDICIONES LABORALES
# ---------------------------------------------------------------------------
def _labor_conditions_score(wage_as_fraction_of_living_wage, max_weekly_hours,
                             has_collective_bargaining=False, safety_certification=False):
    """
    Puntaje ponderado: 60% salario relativo al salario digno local, 20% horas
    semanales (10 si <=40h, 0 si >=70h, interpolacion lineal entremedio),
    10% sindicalizacion/negociacion colectiva, 10% certificacion de seguridad laboral.
    """
    if wage_as_fraction_of_living_wage < 0:
        raise ValueError("wage_as_fraction_of_living_wage debe ser >= 0")
    if max_weekly_hours < 0:
        raise ValueError("max_weekly_hours debe ser >= 0")

    wage_component = _clip(wage_as_fraction_of_living_wage * 10.0)

    if max_weekly_hours <= 40:
        hours_component = 10.0
    elif max_weekly_hours >= 70:
        hours_component = 0.0
    else:
        hours_component = 10.0 * (70.0 - max_weekly_hours) / (70.0 - 40.0)

    bargaining_component = 10.0 if has_collective_bargaining else 0.0
    safety_component = 10.0 if safety_certification else 0.0

    score = (
        0.6 * wage_component
        + 0.2 * hours_component
        + 0.1 * bargaining_component
        + 0.1 * safety_component
    )

    return {
        "dimension": "labor_conditions",
        "wage_as_fraction_of_living_wage": wage_as_fraction_of_living_wage,
        "max_weekly_hours": max_weekly_hours,
        "has_collective_bargaining": has_collective_bargaining,
        "safety_certification": safety_certification,
        "wage_component": wage_component,
        "hours_component": hours_component,
        "score": _clip(score),
        "confidence_note": (
            "Formula ponderada propia (60% salario relativo, 20% horas, 10% negociacion colectiva, "
            "10% certificacion de seguridad). No sigue un estandar de auditoria social especifico "
            "(ej. SA8000, Fair Trade) -- sirve como aproximacion comparativa, no como certificacion."
        ),
    }


# ---------------------------------------------------------------------------
# 4) COMPUESTO
# ---------------------------------------------------------------------------
def _composite_score(environmental_score=None, animal_welfare_score=None, labor_score=None,
                      weight_environmental=1.0, weight_animal_welfare=1.0, weight_labor=1.0):
    """
    Combina las 3 dimensiones ya calculadas (0-10 cada una). Si una dimension
    no aplica (ej. animal_welfare_score=None para un alimento vegetal), su peso
    se excluye y los pesos restantes se renormalizan para sumar 1.
    """
    components = []
    if environmental_score is not None:
        components.append((environmental_score, weight_environmental, "environmental"))
    if animal_welfare_score is not None:
        components.append((animal_welfare_score, weight_animal_welfare, "animal_welfare"))
    if labor_score is not None:
        components.append((labor_score, weight_labor, "labor"))

    if not components:
        raise ValueError("Hay que pasar al menos uno de: environmental_score, animal_welfare_score, labor_score")

    total_weight = sum(w for _, w, _ in components)
    if total_weight <= 0:
        raise ValueError("La suma de los pesos de las dimensiones incluidas debe ser > 0")

    normalized_weights = {name: w / total_weight for _, w, name in components}
    composite = sum(score * (w / total_weight) for score, w, _ in components)

    return {
        "dimension": "composite",
        "included_dimensions": [name for _, _, name in components],
        "normalized_weights": normalized_weights,
        "score": _clip(composite),
    }


# ---------------------------------------------------------------------------
# VALIDATE
# ---------------------------------------------------------------------------
def _validate():
    checks = []

    # 1) Ambiental: vacuno (mayor GEI) debe tener score menor que verduras (menor GEI)
    env_beef = _environmental_footprint_score(food_category="beef")
    env_veg = _environmental_footprint_score(food_category="vegetables")
    checks.append({
        "name": "environmental_score_monotonic_vs_ghg",
        "passed": env_beef["score"] < env_veg["score"],
        "detail": f"score(beef)={env_beef['score']:.3f}, score(vegetables)={env_veg['score']:.3f}",
    })

    # 2) Ambiental: todos los scores del catalogo quedan acotados en [0,10]
    all_env_scores = [_environmental_footprint_score(food_category=k)["score"] for k in _ENV_CATALOG]
    checks.append({
        "name": "environmental_score_bounded_for_full_catalog",
        "passed": all(0.0 <= s <= 10.0 for s in all_env_scores),
        "detail": f"min={min(all_env_scores):.3f}, max={max(all_env_scores):.3f}",
    })

    # 3) Ambiental: el elemento de peor huella (max GHG) da score minimo exacto (0), el mejor (min GHG) score maximo exacto (10)
    worst = max(_ENV_CATALOG, key=lambda k: _ENV_CATALOG[k]["ghg"])
    best = min(_ENV_CATALOG, key=lambda k: _ENV_CATALOG[k]["ghg"])
    worst_score = _environmental_footprint_score(food_category=worst, weight_ghg=1.0, weight_land=0.0, weight_water=0.0)["score"]
    best_score = _environmental_footprint_score(food_category=best, weight_ghg=1.0, weight_land=0.0, weight_water=0.0)["score"]
    checks.append({
        "name": "environmental_score_extremes_exact",
        "passed": abs(worst_score - 0.0) < 1e-9 and abs(best_score - 10.0) < 1e-9,
        "detail": f"{worst}(peor GHG)={worst_score:.9f}, {best}(mejor GHG)={best_score:.9f}",
    })

    # 4) Bienestar animal: orden esperado entre sistemas segun catalogo
    order = ["battery_cage", "cage_free_indoor", "free_range", "certified_organic_pasture"]
    scores_order = [_animal_welfare_score(s)["score"] for s in order]
    checks.append({
        "name": "animal_welfare_catalog_monotonic_order",
        "passed": all(scores_order[i] < scores_order[i + 1] for i in range(len(scores_order) - 1)),
        "detail": f"{dict(zip(order, scores_order))}",
    })

    # 5) Laboral: acotado en [0,10] en un barrido de casos
    labor_cases = [
        _labor_conditions_score(0.0, 80, False, False)["score"],
        _labor_conditions_score(0.5, 55, False, False)["score"],
        _labor_conditions_score(1.0, 40, True, True)["score"],
        _labor_conditions_score(3.0, 35, True, True)["score"],
    ]
    checks.append({
        "name": "labor_score_bounded",
        "passed": all(0.0 <= s <= 10.0 for s in labor_cases),
        "detail": f"scores={labor_cases}",
    })

    # 6) Laboral: monotonico creciente en el salario relativo (resto fijo)
    labor_low_wage = _labor_conditions_score(0.3, 40, False, False)["score"]
    labor_high_wage = _labor_conditions_score(0.9, 40, False, False)["score"]
    checks.append({
        "name": "labor_score_monotonic_in_wage",
        "passed": labor_high_wage > labor_low_wage,
        "detail": f"score(wage=0.3)={labor_low_wage:.3f}, score(wage=0.9)={labor_high_wage:.3f}",
    })

    # 7) Laboral: monotonico decreciente en horas semanales (resto fijo)
    labor_few_hours = _labor_conditions_score(0.8, 40, False, False)["score"]
    labor_many_hours = _labor_conditions_score(0.8, 65, False, False)["score"]
    checks.append({
        "name": "labor_score_monotonic_decreasing_in_hours",
        "passed": labor_few_hours > labor_many_hours,
        "detail": f"score(40h)={labor_few_hours:.3f}, score(65h)={labor_many_hours:.3f}",
    })

    # 8) Compuesto: con pesos iguales y las 3 dimensiones, exactamente el promedio simple
    comp_equal = _composite_score(
        environmental_score=6.0, animal_welfare_score=8.0, labor_score=4.0,
        weight_environmental=1.0, weight_animal_welfare=1.0, weight_labor=1.0,
    )
    expected_avg = (6.0 + 8.0 + 4.0) / 3.0
    checks.append({
        "name": "composite_score_exact_simple_average",
        "passed": abs(comp_equal["score"] - expected_avg) < 1e-9,
        "detail": f"compuesto={comp_equal['score']:.9f}, esperado={expected_avg:.9f}",
    })

    # 9) Compuesto: renormalizacion de pesos al omitir una dimension (ej. alimento vegetal sin bienestar animal)
    comp_no_welfare = _composite_score(
        environmental_score=9.0, animal_welfare_score=None, labor_score=5.0,
        weight_environmental=2.0, weight_animal_welfare=1.0, weight_labor=2.0,
    )
    # pesos originales sin animal_welfare: environmental=2, labor=2 -> renormalizados a 0.5/0.5
    expected_composite = 0.5 * 9.0 + 0.5 * 5.0
    weights_sum_to_one = abs(sum(comp_no_welfare["normalized_weights"].values()) - 1.0) < 1e-9
    checks.append({
        "name": "composite_score_weight_renormalization",
        "passed": "animal_welfare" not in comp_no_welfare["included_dimensions"]
        and weights_sum_to_one
        and abs(comp_no_welfare["score"] - expected_composite) < 1e-9,
        "detail": f"pesos_normalizados={comp_no_welfare['normalized_weights']}, "
                  f"score={comp_no_welfare['score']:.6f}, esperado={expected_composite:.6f}",
    })

    # 10) Compuesto: acotado en [0,10] en un barrido de combinaciones
    composite_bounds_ok = True
    for e in [0.0, 5.0, 10.0]:
        for a in [0.0, 5.0, 10.0]:
            for l in [0.0, 5.0, 10.0]:
                s = _composite_score(environmental_score=e, animal_welfare_score=a, labor_score=l)["score"]
                if not (0.0 <= s <= 10.0):
                    composite_bounds_ok = False
    checks.append({
        "name": "composite_score_bounded_full_sweep",
        "passed": composite_bounds_ok,
        "detail": "barrido de 27 combinaciones (e,a,l en {0,5,10}) todas dentro de [0,10]",
    })

    all_passed = all(c["passed"] for c in checks)
    return {
        "dimension": "validate",
        "validation_passed": all_passed,
        "checks": checks,
        "n_checks": len(checks),
        "n_passed": sum(1 for c in checks if c["passed"]),
    }


# ---------------------------------------------------------------------------
# DISPATCHER
# ---------------------------------------------------------------------------
def ethical_food_advisor_tool(mode, **kwargs):
    if mode == "environmental_footprint_score":
        return _environmental_footprint_score(
            food_category=kwargs.get("food_category"),
            ghg_kg_co2eq_per_kg=kwargs.get("ghg_kg_co2eq_per_kg"),
            land_m2_per_kg=kwargs.get("land_m2_per_kg"),
            water_l_per_kg=kwargs.get("water_l_per_kg"),
            weight_ghg=kwargs.get("weight_ghg", 0.5),
            weight_land=kwargs.get("weight_land", 0.25),
            weight_water=kwargs.get("weight_water", 0.25),
        )
    elif mode == "animal_welfare_score":
        return _animal_welfare_score(farming_system=kwargs["farming_system"])
    elif mode == "labor_conditions_score":
        return _labor_conditions_score(
            wage_as_fraction_of_living_wage=kwargs["wage_as_fraction_of_living_wage"],
            max_weekly_hours=kwargs["max_weekly_hours"],
            has_collective_bargaining=kwargs.get("has_collective_bargaining", False),
            safety_certification=kwargs.get("safety_certification", False),
        )
    elif mode == "composite_score":
        return _composite_score(
            environmental_score=kwargs.get("environmental_score"),
            animal_welfare_score=kwargs.get("animal_welfare_score"),
            labor_score=kwargs.get("labor_score"),
            weight_environmental=kwargs.get("weight_environmental", 1.0),
            weight_animal_welfare=kwargs.get("weight_animal_welfare", 1.0),
            weight_labor=kwargs.get("weight_labor", 1.0),
        )
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            f"mode desconocido: {mode!r}. Debe ser uno de "
            "['environmental_footprint_score', 'animal_welfare_score', 'labor_conditions_score', "
            "'composite_score', 'validate']"
        )


# ---------------------------------------------------------------------------
# SCHEMA
# ---------------------------------------------------------------------------
ETHICAL_FOOD_ADVISOR_TOOL_SCHEMA = {
    "name": "ethical_food_advisor_tool",
    "description": (
        "Calcula puntajes 0-10 (10=mejor) para huella ambiental, bienestar animal y condiciones "
        "laborales de un alimento, mas un puntaje compuesto ponderado (pesos se renormalizan si se "
        "omite alguna dimension). mode='validate' corre 10 chequeos de consistencia."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["environmental_footprint_score", "animal_welfare_score",
                         "labor_conditions_score", "composite_score", "validate"],
                "description": "Que dimension calcular, o 'validate' para autochequeo",
            },
            "food_category": {
                "type": "string",
                "enum": sorted(_ENV_CATALOG.keys()),
                "description": "Categoria de alimento del catalogo (environmental_footprint_score)",
            },
            "ghg_kg_co2eq_per_kg": {"type": "number", "description": "Override de GEI en kg CO2eq/kg (opcional)"},
            "land_m2_per_kg": {"type": "number", "description": "Override de uso de tierra en m2/kg (opcional)"},
            "water_l_per_kg": {"type": "number", "description": "Override de huella hidrica en L/kg (opcional)"},
            "weight_ghg": {"type": "number", "description": "Peso de GEI en el score ambiental (default 0.5)"},
            "weight_land": {"type": "number", "description": "Peso de tierra en el score ambiental (default 0.25)"},
            "weight_water": {"type": "number", "description": "Peso de agua en el score ambiental (default 0.25)"},
            "farming_system": {
                "type": "string",
                "enum": sorted(_ANIMAL_WELFARE_CATALOG.keys()),
                "description": "Sistema de crianza (animal_welfare_score)",
            },
            "wage_as_fraction_of_living_wage": {"type": "number", "description": "Salario / salario digno local (labor_conditions_score)"},
            "max_weekly_hours": {"type": "number", "description": "Horas semanales maximas (labor_conditions_score)"},
            "has_collective_bargaining": {"type": "boolean", "description": "Hay negociacion colectiva/sindicato (default false)"},
            "safety_certification": {"type": "boolean", "description": "Tiene certificacion de seguridad laboral (default false)"},
            "environmental_score": {"type": "number", "description": "Score ambiental ya calculado (composite_score)"},
            "animal_welfare_score": {"type": "number", "description": "Score de bienestar animal ya calculado (composite_score, omitir si no aplica)"},
            "labor_score": {"type": "number", "description": "Score laboral ya calculado (composite_score)"},
            "weight_environmental": {"type": "number", "description": "Peso de la dimension ambiental en el compuesto (default 1.0)"},
            "weight_animal_welfare": {"type": "number", "description": "Peso de la dimension de bienestar animal en el compuesto (default 1.0)"},
            "weight_labor": {"type": "number", "description": "Peso de la dimension laboral en el compuesto (default 1.0)"},
        },
        "required": ["mode"],
    },
}


def _handler(**kwargs):
    mode = kwargs.pop("mode")
    return ethical_food_advisor_tool(mode, **kwargs)


try:
    from tool_registry import register_tool
    register_tool("ethical_food_advisor_tool", ETHICAL_FOOD_ADVISOR_TOOL_SCHEMA, _handler)
except ImportError:
    pass


if __name__ == "__main__":
    import json
    result = _validate()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print()
    print(f"validation_passed: {result['validation_passed']} "
          f"({result['n_passed']}/{result['n_checks']} checks)")
