"""
sustainable_sourcing_tool.py

Herramienta MCP que calcula puntajes cuantitativos (escala 0-10, 10=mejor) para
4 dimensiones de sostenibilidad en el ABASTECIMIENTO de un alimento (distinto de
ethical_food_advisor_tool, que cubre produccion/GEI-tierra-agua/bienestar animal/
laboral): transporte, estacionalidad, certificaciones y packaging. Mas un
puntaje compuesto ponderado.

    - transport_score    : huella de GEI del transporte segun modo + distancia (independiente de la masa)
    - seasonality_score  : si esta en temporada localmente, invernadero calefaccionado, meses en frio
    - certification_score: catalogo de certificaciones (organico, fair trade, MSC/ASC, etc.)
    - packaging_score    : catalogo de materiales de packaging + razon packaging/producto
    - composite_score    : combinacion ponderada de las 4 (renormaliza si se omite alguna)
    - validate            : 10 chequeos de consistencia

IMPORTANTE - nivel de confianza:
Los factores de emision de transporte son ORDENES DE MAGNITUD tipicos citados
en literatura de ciclo de vida (ej. estilo DEFRA/ecoinvent: aereo >> camion >
tren > barco). Los catalogos de certificacion y packaging son escalas
CUALITATIVAS PROPIAS que reflejan un orden razonable segun rigurosidad de
verificacion / reciclabilidad tipica -- no una equivalencia oficial entre
esquemas de certificacion ni un LCA (analisis de ciclo de vida) de un producto
especifico. Cada resultado trae "confidence_note".
"""

# ---------------------------------------------------------------------------
# CATALOGO DE TRANSPORTE (g CO2eq por tonelada-km, ordenes de magnitud tipicos)
# ---------------------------------------------------------------------------
_TRANSPORT_CATALOG = {
    "sea_freight": 12.0,
    "rail": 25.0,
    "road_truck": 100.0,
    "air_freight": 600.0,
}

# ---------------------------------------------------------------------------
# CATALOGO DE CERTIFICACIONES (escala propia 0-10, "none" como piso)
# ---------------------------------------------------------------------------
_CERTIFICATION_CATALOG = {
    "none": 2.0,
    "non_gmo": 3.5,
    "rainforest_alliance": 6.0,
    "asc_certified": 7.0,
    "fair_trade": 7.0,
    "organic": 7.5,
    "msc_certified": 7.5,
    "regenerative_organic_certified": 9.0,
}

# ---------------------------------------------------------------------------
# CATALOGO DE PACKAGING (escala propia 0-10, segun reciclabilidad/reutilizacion tipica)
# ---------------------------------------------------------------------------
_PACKAGING_CATALOG = {
    "bulk_no_packaging": 10.0,
    "reusable_container": 9.0,
    "paper_cardboard": 7.5,
    "glass": 6.5,
    "aluminum": 6.0,
    "plastic_recyclable": 5.0,
    "plastic_non_recyclable": 2.0,
    "multilayer_composite": 1.0,
}


def _clip(x, lo=0.0, hi=10.0):
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# 1) TRANSPORTE
# ---------------------------------------------------------------------------
def _transport_score(transport_mode, distance_km, threshold_kg_co2eq_per_kg=1.0):
    """
    co2_per_kg_food (kg CO2eq / kg de alimento transportado) = distance_km * factor_g_per_tkm / 1e6
    (se cancela la masa: es el mismo resultado independiente de cuantos kg se transporten).
    Score lineal: 10 en emisiones=0, 0 en emisiones>=threshold (default 1.0 kg CO2eq/kg,
    referencia razonable para "transporte muy intensivo", configurable).
    """
    if transport_mode not in _TRANSPORT_CATALOG:
        raise ValueError(f"transport_mode debe ser uno de {sorted(_TRANSPORT_CATALOG.keys())}")
    if distance_km < 0:
        raise ValueError("distance_km debe ser >= 0")
    if threshold_kg_co2eq_per_kg <= 0:
        raise ValueError("threshold_kg_co2eq_per_kg debe ser > 0")

    factor = _TRANSPORT_CATALOG[transport_mode]
    co2_per_kg_food = distance_km * factor / 1_000_000.0
    score = _clip(10.0 * (1.0 - co2_per_kg_food / threshold_kg_co2eq_per_kg))

    return {
        "dimension": "transport",
        "transport_mode": transport_mode,
        "distance_km": distance_km,
        "emission_factor_g_co2eq_per_tonne_km": factor,
        "co2eq_kg_per_kg_food": co2_per_kg_food,
        "score": score,
        "confidence_note": (
            "Factores de emision por modo de transporte son ordenes de magnitud tipicos de "
            "literatura de ciclo de vida ampliamente citada (aereo >> camion > tren > barco), "
            "no una medicion de una ruta/flota especifica."
        ),
    }


# ---------------------------------------------------------------------------
# 2) ESTACIONALIDAD
# ---------------------------------------------------------------------------
def _seasonality_score(in_season, requires_heated_greenhouse=False, months_in_cold_storage=0.0):
    """
    Base 10 si esta en temporada localmente, 4 si no (fuera de temporada pero sin
    necesariamente invernadero calefaccionado, ej. importado de otro hemisferio en
    su propia temporada). Penalizaciones: -3 fijo si requiere invernadero
    calefaccionado, -0.5 por mes en frigorifico (acotado a -3 maximo).
    """
    if months_in_cold_storage < 0:
        raise ValueError("months_in_cold_storage debe ser >= 0")

    base = 10.0 if in_season else 4.0
    greenhouse_penalty = 3.0 if requires_heated_greenhouse else 0.0
    cold_storage_penalty = min(3.0, 0.5 * months_in_cold_storage)

    score = _clip(base - greenhouse_penalty - cold_storage_penalty)

    return {
        "dimension": "seasonality",
        "in_season": in_season,
        "requires_heated_greenhouse": requires_heated_greenhouse,
        "months_in_cold_storage": months_in_cold_storage,
        "score": score,
        "confidence_note": (
            "Formula propia (base 10/4 segun temporada, -3 por invernadero calefaccionado, "
            "-0.5/mes de frigorifico hasta -3). No modela el mix energetico especifico del "
            "invernadero ni el tipo de refrigerante usado."
        ),
    }


# ---------------------------------------------------------------------------
# 3) CERTIFICACIONES
# ---------------------------------------------------------------------------
def _certification_score(certifications):
    """
    certifications: lista de strings del catalogo (puede venir vacia -> 'none').
    Toma el maximo del catalogo entre las certificaciones presentes (la mas
    rigurosa domina) y suma un bono chico por certificaciones adicionales
    (0.25 por cada una extra, tope +1.0 total), acotado a 10.
    """
    if not certifications:
        certifications = ["none"]
    unknown = [c for c in certifications if c not in _CERTIFICATION_CATALOG]
    if unknown:
        raise ValueError(f"certificaciones desconocidas: {unknown}. Catalogo: {sorted(_CERTIFICATION_CATALOG.keys())}")

    unique_certs = sorted(set(certifications))
    base = max(_CERTIFICATION_CATALOG[c] for c in unique_certs)
    bonus = min(1.0, 0.25 * (len(unique_certs) - 1))
    score = _clip(base + bonus)

    return {
        "dimension": "certification",
        "certifications": unique_certs,
        "base_score": base,
        "multi_certification_bonus": bonus,
        "score": score,
        "confidence_note": (
            "Escala propia 0-10 que ordena certificaciones por rigurosidad de verificacion tipica "
            "(no es una equivalencia oficial entre esquemas -- cada certificacion audita cosas "
            "distintas y no son directamente comparables en la practica)."
        ),
    }


# ---------------------------------------------------------------------------
# 4) PACKAGING
# ---------------------------------------------------------------------------
def _packaging_score(packaging_material, packaging_to_product_mass_ratio=0.0):
    """
    Score base del catalogo, penalizado linealmente por la razon de masa
    packaging/producto (ej. 0.3 = el packaging pesa 30% de lo que pesa el
    producto), acotada a un maximo de penalizacion del 50% del score base
    (razon >= 0.5 ya aplica el maximo).
    """
    if packaging_material not in _PACKAGING_CATALOG:
        raise ValueError(f"packaging_material debe ser uno de {sorted(_PACKAGING_CATALOG.keys())}")
    if packaging_to_product_mass_ratio < 0:
        raise ValueError("packaging_to_product_mass_ratio debe ser >= 0")

    base = _PACKAGING_CATALOG[packaging_material]
    penalty_fraction = min(0.5, packaging_to_product_mass_ratio)
    score = _clip(base * (1.0 - penalty_fraction))

    return {
        "dimension": "packaging",
        "packaging_material": packaging_material,
        "packaging_to_product_mass_ratio": packaging_to_product_mass_ratio,
        "base_score": base,
        "score": score,
        "confidence_note": (
            "Escala propia 0-10 segun reciclabilidad/reutilizacion tipica del material (no un LCA "
            "de packaging especifico, que dependeria del sistema real de reciclaje disponible "
            "localmente)."
        ),
    }


# ---------------------------------------------------------------------------
# 5) COMPUESTO
# ---------------------------------------------------------------------------
def _composite_score(transport_score=None, seasonality_score=None,
                      certification_score=None, packaging_score=None,
                      weight_transport=1.0, weight_seasonality=1.0,
                      weight_certification=1.0, weight_packaging=1.0):
    """
    Combina las 4 dimensiones ya calculadas (0-10 cada una). Si una dimension
    es None, se excluye y los pesos restantes se renormalizan para sumar 1.
    """
    components = []
    if transport_score is not None:
        components.append((transport_score, weight_transport, "transport"))
    if seasonality_score is not None:
        components.append((seasonality_score, weight_seasonality, "seasonality"))
    if certification_score is not None:
        components.append((certification_score, weight_certification, "certification"))
    if packaging_score is not None:
        components.append((packaging_score, weight_packaging, "packaging"))

    if not components:
        raise ValueError(
            "Hay que pasar al menos uno de: transport_score, seasonality_score, "
            "certification_score, packaging_score"
        )

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

    # 1) Transporte: mismo distancia, aereo debe dar score menor que barco
    t_air = _transport_score("air_freight", 5000)
    t_sea = _transport_score("sea_freight", 5000)
    checks.append({
        "name": "transport_score_air_worse_than_sea",
        "passed": t_air["score"] < t_sea["score"],
        "detail": f"score(air,5000km)={t_air['score']:.3f}, score(sea,5000km)={t_sea['score']:.3f}",
    })

    # 2) Transporte: a distancia 0, score exacto 10 sin importar el modo
    t_zero = _transport_score("air_freight", 0)
    checks.append({
        "name": "transport_score_zero_distance_is_max",
        "passed": abs(t_zero["score"] - 10.0) < 1e-9 and abs(t_zero["co2eq_kg_per_kg_food"] - 0.0) < 1e-12,
        "detail": f"score(0km)={t_zero['score']:.9f}",
    })

    # 3) Transporte: monotonico decreciente en distancia (mismo modo)
    t_short = _transport_score("road_truck", 100)
    t_long = _transport_score("road_truck", 3000)
    checks.append({
        "name": "transport_score_monotonic_in_distance",
        "passed": t_short["score"] > t_long["score"],
        "detail": f"score(100km)={t_short['score']:.3f}, score(3000km)={t_long['score']:.3f}",
    })

    # 4) Estacionalidad: en temporada > fuera de temporada (resto igual)
    s_in = _seasonality_score(True)
    s_out = _seasonality_score(False)
    checks.append({
        "name": "seasonality_in_season_better",
        "passed": s_in["score"] > s_out["score"],
        "detail": f"score(in_season)={s_in['score']:.3f}, score(out_of_season)={s_out['score']:.3f}",
    })

    # 5) Estacionalidad: invernadero calefaccionado y frigorifico bajan el score, acotado en [0,10]
    s_worst = _seasonality_score(False, requires_heated_greenhouse=True, months_in_cold_storage=12.0)
    checks.append({
        "name": "seasonality_penalties_bounded",
        "passed": 0.0 <= s_worst["score"] <= 10.0 and s_worst["score"] < s_out["score"],
        "detail": f"score(peor caso)={s_worst['score']:.3f}",
    })

    # 6) Certificaciones: organic > none, y regenerative_organic_certified es el maximo del catalogo
    c_none = _certification_score([])
    c_organic = _certification_score(["organic"])
    c_max = _certification_score(["regenerative_organic_certified"])
    checks.append({
        "name": "certification_catalog_order",
        "passed": c_organic["score"] > c_none["score"]
        and c_max["score"] >= c_organic["score"]
        and c_max["score"] <= 10.0,
        "detail": f"none={c_none['score']:.3f}, organic={c_organic['score']:.3f}, "
                  f"regenerative_organic_certified={c_max['score']:.3f}",
    })

    # 7) Certificaciones: multiples certificaciones dan score >= que la mejor individual sola
    c_single = _certification_score(["fair_trade"])
    c_multi = _certification_score(["fair_trade", "organic"])
    checks.append({
        "name": "certification_multi_bonus_is_nonnegative",
        "passed": c_multi["score"] >= c_single["score"],
        "detail": f"single(fair_trade)={c_single['score']:.3f}, multi(fair_trade+organic)={c_multi['score']:.3f}",
    })

    # 8) Packaging: bulk (sin envase) > plastico no reciclable, y razon de masa alta penaliza
    p_bulk = _packaging_score("bulk_no_packaging")
    p_plastic = _packaging_score("plastic_non_recyclable")
    p_heavy = _packaging_score("glass", packaging_to_product_mass_ratio=0.6)
    p_light = _packaging_score("glass", packaging_to_product_mass_ratio=0.0)
    checks.append({
        "name": "packaging_catalog_order_and_mass_penalty",
        "passed": p_bulk["score"] > p_plastic["score"] and p_heavy["score"] < p_light["score"],
        "detail": f"bulk={p_bulk['score']:.3f}, plastic_non_recyclable={p_plastic['score']:.3f}, "
                  f"glass(ratio=0.6)={p_heavy['score']:.3f}, glass(ratio=0)={p_light['score']:.3f}",
    })

    # 9) Compuesto: con las 4 dimensiones y pesos iguales, exactamente el promedio simple
    comp_equal = _composite_score(
        transport_score=8.0, seasonality_score=6.0, certification_score=4.0, packaging_score=10.0,
    )
    expected_avg = (8.0 + 6.0 + 4.0 + 10.0) / 4.0
    checks.append({
        "name": "composite_score_exact_simple_average",
        "passed": abs(comp_equal["score"] - expected_avg) < 1e-9,
        "detail": f"compuesto={comp_equal['score']:.9f}, esperado={expected_avg:.9f}",
    })

    # 10) Compuesto: renormalizacion de pesos al omitir una dimension
    comp_partial = _composite_score(
        transport_score=9.0, seasonality_score=None, certification_score=3.0, packaging_score=None,
        weight_transport=3.0, weight_certification=1.0,
    )
    expected_partial = (9.0 * 0.75) + (3.0 * 0.25)  # pesos 3:1 -> 0.75/0.25
    weights_sum_to_one = abs(sum(comp_partial["normalized_weights"].values()) - 1.0) < 1e-9
    checks.append({
        "name": "composite_score_weight_renormalization",
        "passed": set(comp_partial["included_dimensions"]) == {"transport", "certification"}
        and weights_sum_to_one
        and abs(comp_partial["score"] - expected_partial) < 1e-9,
        "detail": f"pesos_normalizados={comp_partial['normalized_weights']}, "
                  f"score={comp_partial['score']:.6f}, esperado={expected_partial:.6f}",
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
def sustainable_sourcing_tool(mode, **kwargs):
    if mode == "transport_score":
        return _transport_score(
            transport_mode=kwargs["transport_mode"],
            distance_km=kwargs["distance_km"],
            threshold_kg_co2eq_per_kg=kwargs.get("threshold_kg_co2eq_per_kg", 1.0),
        )
    elif mode == "seasonality_score":
        return _seasonality_score(
            in_season=kwargs["in_season"],
            requires_heated_greenhouse=kwargs.get("requires_heated_greenhouse", False),
            months_in_cold_storage=kwargs.get("months_in_cold_storage", 0.0),
        )
    elif mode == "certification_score":
        return _certification_score(certifications=kwargs.get("certifications", []))
    elif mode == "packaging_score":
        return _packaging_score(
            packaging_material=kwargs["packaging_material"],
            packaging_to_product_mass_ratio=kwargs.get("packaging_to_product_mass_ratio", 0.0),
        )
    elif mode == "composite_score":
        return _composite_score(
            transport_score=kwargs.get("transport_score"),
            seasonality_score=kwargs.get("seasonality_score"),
            certification_score=kwargs.get("certification_score"),
            packaging_score=kwargs.get("packaging_score"),
            weight_transport=kwargs.get("weight_transport", 1.0),
            weight_seasonality=kwargs.get("weight_seasonality", 1.0),
            weight_certification=kwargs.get("weight_certification", 1.0),
            weight_packaging=kwargs.get("weight_packaging", 1.0),
        )
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            f"mode desconocido: {mode!r}. Debe ser uno de "
            "['transport_score', 'seasonality_score', 'certification_score', "
            "'packaging_score', 'composite_score', 'validate']"
        )


# ---------------------------------------------------------------------------
# SCHEMA
# ---------------------------------------------------------------------------
SUSTAINABLE_SOURCING_TOOL_SCHEMA = {
    "name": "sustainable_sourcing_tool",
    "description": (
        "Calcula puntajes 0-10 (10=mejor) para transporte (modo+distancia), estacionalidad, "
        "certificaciones, y packaging de un alimento, mas un puntaje compuesto ponderado (pesos "
        "se renormalizan si se omite alguna dimension). mode='validate' corre 10 chequeos."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["transport_score", "seasonality_score", "certification_score",
                         "packaging_score", "composite_score", "validate"],
                "description": "Que dimension calcular, o 'validate' para autochequeo",
            },
            "transport_mode": {
                "type": "string",
                "enum": sorted(_TRANSPORT_CATALOG.keys()),
                "description": "Modo de transporte (transport_score)",
            },
            "distance_km": {"type": "number", "description": "Distancia recorrida en km (transport_score)"},
            "threshold_kg_co2eq_per_kg": {"type": "number", "description": "Umbral de referencia para score=0, kg CO2eq/kg (default 1.0)"},
            "in_season": {"type": "boolean", "description": "Esta en temporada local (seasonality_score)"},
            "requires_heated_greenhouse": {"type": "boolean", "description": "Requiere invernadero calefaccionado (default false)"},
            "months_in_cold_storage": {"type": "number", "description": "Meses en frigorifico (default 0.0)"},
            "certifications": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(_CERTIFICATION_CATALOG.keys())},
                "description": "Lista de certificaciones del catalogo (certification_score, vacio = 'none')",
            },
            "packaging_material": {
                "type": "string",
                "enum": sorted(_PACKAGING_CATALOG.keys()),
                "description": "Material de packaging (packaging_score)",
            },
            "packaging_to_product_mass_ratio": {"type": "number", "description": "Masa de packaging / masa de producto (default 0.0)"},
            "transport_score": {"type": "number", "description": "Score de transporte ya calculado (composite_score)"},
            "seasonality_score": {"type": "number", "description": "Score de estacionalidad ya calculado (composite_score)"},
            "certification_score": {"type": "number", "description": "Score de certificacion ya calculado (composite_score)"},
            "packaging_score": {"type": "number", "description": "Score de packaging ya calculado (composite_score)"},
            "weight_transport": {"type": "number", "description": "Peso de transporte en el compuesto (default 1.0)"},
            "weight_seasonality": {"type": "number", "description": "Peso de estacionalidad en el compuesto (default 1.0)"},
            "weight_certification": {"type": "number", "description": "Peso de certificacion en el compuesto (default 1.0)"},
            "weight_packaging": {"type": "number", "description": "Peso de packaging en el compuesto (default 1.0)"},
        },
        "required": ["mode"],
    },
}


def _handler(**kwargs):
    mode = kwargs.pop("mode")
    return sustainable_sourcing_tool(mode, **kwargs)


try:
    from tool_registry import register_tool
    register_tool("sustainable_sourcing_tool", SUSTAINABLE_SOURCING_TOOL_SCHEMA, _handler)
except ImportError:
    pass


if __name__ == "__main__":
    import json
    result = _validate()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print()
    print(f"validation_passed: {result['validation_passed']} "
          f"({result['n_passed']}/{result['n_checks']} checks)")
