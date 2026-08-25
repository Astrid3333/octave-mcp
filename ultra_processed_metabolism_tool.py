"""
ultra_processed_metabolism_tool.py

Herramienta MCP que calcula indicadores cuantitativos (escala 0-10, 10=mejor,
salvo donde se indique lo contrario) relacionados con el grado de procesamiento
industrial de un alimento y su impacto metabolico esperado:

    - nova_classification_score : marcadores de ultraprocesamiento -> grupo NOVA estimado
    - glycemic_load_score       : carga glicemica (formula estandar) + heuristica de
                                   aceleracion por procesamiento (matriz alimentaria alterada)
    - energy_density_score      : kcal/100g vs umbrales de perfil nutricional tipo OMS
    - additive_load_score       : cantidad de aditivos/marcadores cosmeticos en la lista de ingredientes
    - composite_score           : combinacion ponderada de las 4 (renormaliza si se omite alguna)
    - validate                  : 10 chequeos de consistencia

IMPORTANTE - alcance y nivel de confianza:
Esta herramienta es un modelo cuantitativo educativo/comparativo de ciencia de
los alimentos, NO una herramienta de diagnostico ni de asesoria nutricional
personalizada. La clasificacion NOVA aqui es una APROXIMACION propia basada en
marcadores de ingredientes (no el protocolo completo de Monteiro et al. 2019,
que requiere evaluar la lista de ingredientes completa con criterio experto).
La heuristica de aceleracion glicemica por procesamiento (mayor velocidad de
digestion por disrupcion de la matriz alimentaria/reduccion de tamano de
particula) refleja un mecanismo bien documentado en literatura de nutricion,
pero el factor numerico usado (+15%) es una aproximacion de orden de magnitud,
no una calibracion contra un alimento especifico. Cada resultado trae
"confidence_note".
"""

# ---------------------------------------------------------------------------
# CATALOGO DE MARCADORES DE INGREDIENTES (peso hacia ultraprocesamiento)
# Los marcadores "cosmeticos" (que alteran color/sabor/textura sin razon
# nutricional/culinaria) fuerzan clasificacion NOVA 4 sin importar el resto.
# ---------------------------------------------------------------------------
_INGREDIENT_MARKERS = {
    "isolated_sugar": {"weight": 1, "cosmetic": False},
    "isolated_fat_oil": {"weight": 1, "cosmetic": False},
    "modified_starch": {"weight": 1, "cosmetic": False},
    "preservative": {"weight": 1, "cosmetic": False},
    "anti_caking_agent": {"weight": 1, "cosmetic": False},
    "stabilizer": {"weight": 1, "cosmetic": False},
    "acidity_regulator": {"weight": 1, "cosmetic": False},
    "hydrolyzed_protein": {"weight": 2, "cosmetic": True},
    "emulsifier": {"weight": 2, "cosmetic": True},
    "artificial_flavoring": {"weight": 2, "cosmetic": True},
    "artificial_colorant": {"weight": 2, "cosmetic": True},
    "flavor_enhancer": {"weight": 2, "cosmetic": True},
    "sweetener_artificial": {"weight": 2, "cosmetic": True},
}


def _clip(x, lo=0.0, hi=10.0):
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# 1) CLASIFICACION NOVA (aproximada)
# ---------------------------------------------------------------------------
def _nova_classification_score(ingredient_markers):
    """
    Regla de decision (aproximacion propia, no el protocolo NOVA completo):
      - 0 marcadores               -> grupo 1 (sin procesar / minimamente procesado)
      - solo marcadores no cosmeticos (isolated_sugar/fat, preservative, etc.),
        peso total <= 2            -> grupo 2/3 (ingrediente culinario procesado / alimento procesado)
      - cualquier marcador cosmetico presente, o peso total >= 3
                                    -> grupo 4 (ultraprocesado)
    """
    unknown = [m for m in ingredient_markers if m not in _INGREDIENT_MARKERS]
    if unknown:
        raise ValueError(f"marcadores desconocidos: {unknown}. Catalogo: {sorted(_INGREDIENT_MARKERS.keys())}")

    unique_markers = sorted(set(ingredient_markers))
    total_weight = sum(_INGREDIENT_MARKERS[m]["weight"] for m in unique_markers)
    has_cosmetic = any(_INGREDIENT_MARKERS[m]["cosmetic"] for m in unique_markers)

    if not unique_markers:
        nova_group = 1
    elif has_cosmetic or total_weight >= 3:
        nova_group = 4
    else:
        nova_group = 2

    # score inverso al grupo NOVA: grupo1->10, grupo2->6.5, grupo4->0 (mapeo fijo, no lineal
    # porque el salto conceptual grupo1->grupo4 es cualitativo, no una escala continua real)
    score_by_group = {1: 10.0, 2: 6.5, 3: 6.5, 4: 0.0}

    return {
        "dimension": "nova_classification",
        "ingredient_markers": unique_markers,
        "marker_weight_total": total_weight,
        "has_cosmetic_marker": has_cosmetic,
        "estimated_nova_group": nova_group,
        "score": score_by_group[nova_group],
        "confidence_note": (
            "Aproximacion propia de la clasificacion NOVA (Monteiro et al.) basada en presencia de "
            "marcadores de ingredientes tipicos, NO el protocolo NOVA completo (que requiere leer la "
            "lista de ingredientes real completa con criterio experto, incluyendo excepciones caso a "
            "caso). Usar como orientacion, no como clasificacion oficial de un producto real."
        ),
    }


# ---------------------------------------------------------------------------
# 2) CARGA GLICEMICA
# ---------------------------------------------------------------------------
def _glycemic_load_score(carbohydrates_g_per_serving, glycemic_index, fiber_g_per_serving=0.0,
                          is_ultra_processed=False, processing_gi_boost_fraction=0.15):
    """
    GL = GI_efectivo * carbohidratos_netos_g / 100
    carbohidratos_netos = max(0, carbs_g - fiber_g)  [simplificacion: la fibra no
    contribuye igual a la respuesta glicemica que el carbohidrato disponible]

    GI_efectivo = GI * (1 + processing_gi_boost_fraction) si is_ultra_processed,
    acotado a 110 (limite fisiologico razonable de referencia; GI de glucosa pura=100).
    Heuristica basada en el mecanismo de disrupcion de la matriz alimentaria
    (reduccion de tamano de particula acelera la digestion/absorcion), NO una
    calibracion exacta para un alimento especifico.

    Score (10=mejor): GL<=10 -> 10 (carga baja segun umbrales estandar de
    literatura de indice/carga glicemica), GL>=30 -> 0 (carga alta), lineal entremedio.
    """
    if carbohydrates_g_per_serving < 0:
        raise ValueError("carbohydrates_g_per_serving debe ser >= 0")
    if not (0 <= glycemic_index <= 110):
        raise ValueError("glycemic_index debe estar entre 0 y 110")
    if fiber_g_per_serving < 0:
        raise ValueError("fiber_g_per_serving debe ser >= 0")

    net_carbs = max(0.0, carbohydrates_g_per_serving - fiber_g_per_serving)
    effective_gi = glycemic_index
    if is_ultra_processed:
        effective_gi = min(110.0, glycemic_index * (1.0 + processing_gi_boost_fraction))

    glycemic_load = effective_gi * net_carbs / 100.0
    score = _clip(10.0 * (1.0 - (glycemic_load - 10.0) / (30.0 - 10.0))) if glycemic_load > 10.0 else 10.0
    score = _clip(score)

    return {
        "dimension": "glycemic_load",
        "carbohydrates_g_per_serving": carbohydrates_g_per_serving,
        "fiber_g_per_serving": fiber_g_per_serving,
        "net_carbs_g": net_carbs,
        "glycemic_index_input": glycemic_index,
        "is_ultra_processed": is_ultra_processed,
        "effective_glycemic_index": effective_gi,
        "glycemic_load": glycemic_load,
        "score": score,
        "confidence_note": (
            "Formula de carga glicemica estandar (GI*carbs_netos/100) con umbrales de score "
            "alineados a las categorias 'baja/media/alta carga glicemica' de literatura de "
            "indice glicemico. El boost del 15% por ultraprocesamiento es una aproximacion de "
            "orden de magnitud del efecto de disrupcion de matriz alimentaria, no calibrado por "
            "alimento especifico."
        ),
    }


# ---------------------------------------------------------------------------
# 3) DENSIDAD ENERGETICA
# ---------------------------------------------------------------------------
def _energy_density_score(kcal_per_100g):
    """
    Umbrales tipo perfil nutricional (orden de magnitud de literatura de
    densidad energetica): <=60 kcal/100g (frutas/verduras acuosas) -> score 10,
    >=400 kcal/100g (snacks/ultraprocesados calorico-densos) -> score 0, lineal entremedio.
    """
    if kcal_per_100g < 0:
        raise ValueError("kcal_per_100g debe ser >= 0")

    low, high = 60.0, 400.0
    if kcal_per_100g <= low:
        score = 10.0
    elif kcal_per_100g >= high:
        score = 0.0
    else:
        score = 10.0 * (high - kcal_per_100g) / (high - low)

    return {
        "dimension": "energy_density",
        "kcal_per_100g": kcal_per_100g,
        "score": _clip(score),
        "confidence_note": (
            "Umbrales de orden de magnitud inspirados en clasificaciones de densidad energetica "
            "de perfiles nutricionales (baja/media/alta densidad), no un estandar regulatorio "
            "especifico de un pais."
        ),
    }


# ---------------------------------------------------------------------------
# 4) CARGA DE ADITIVOS
# ---------------------------------------------------------------------------
def _additive_load_score(additive_count):
    """
    Penalizacion lineal simple: 0 aditivos -> score 10, cada aditivo adicional
    resta 1.5 puntos, acotado a 0 desde 7 aditivos en adelante.
    """
    if additive_count < 0:
        raise ValueError("additive_count debe ser >= 0")
    score = _clip(10.0 - 1.5 * additive_count)
    return {
        "dimension": "additive_load",
        "additive_count": additive_count,
        "score": score,
        "confidence_note": (
            "Penalizacion lineal propia por cantidad de aditivos declarados (no distingue tipo/dosis "
            "ni evalua seguridad regulatoria individual de cada aditivo -- para eso hay que revisar "
            "la evaluacion especifica de cada uno, ej. fichas de JECFA/EFSA)."
        ),
    }


# ---------------------------------------------------------------------------
# 5) COMPUESTO
# ---------------------------------------------------------------------------
def _composite_score(nova_score=None, glycemic_load_score=None,
                      energy_density_score=None, additive_load_score=None,
                      weight_nova=1.0, weight_glycemic=1.0,
                      weight_energy_density=1.0, weight_additive=1.0):
    components = []
    if nova_score is not None:
        components.append((nova_score, weight_nova, "nova"))
    if glycemic_load_score is not None:
        components.append((glycemic_load_score, weight_glycemic, "glycemic_load"))
    if energy_density_score is not None:
        components.append((energy_density_score, weight_energy_density, "energy_density"))
    if additive_load_score is not None:
        components.append((additive_load_score, weight_additive, "additive_load"))

    if not components:
        raise ValueError(
            "Hay que pasar al menos uno de: nova_score, glycemic_load_score, "
            "energy_density_score, additive_load_score"
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
        "confidence_note": (
            "Puntaje comparativo educativo, NO una recomendacion nutricional personalizada ni una "
            "herramienta de diagnostico. No reemplaza la evaluacion de un profesional de la salud."
        ),
    }


# ---------------------------------------------------------------------------
# VALIDATE
# ---------------------------------------------------------------------------
def _validate():
    checks = []

    # 1) NOVA: sin marcadores -> grupo 1, score maximo exacto
    n_none = _nova_classification_score([])
    checks.append({
        "name": "nova_no_markers_is_group1",
        "passed": n_none["estimated_nova_group"] == 1 and abs(n_none["score"] - 10.0) < 1e-9,
        "detail": f"grupo={n_none['estimated_nova_group']}, score={n_none['score']}",
    })

    # 2) NOVA: cualquier marcador cosmetico solo ya fuerza grupo 4
    n_cosmetic = _nova_classification_score(["emulsifier"])
    checks.append({
        "name": "nova_single_cosmetic_marker_forces_group4",
        "passed": n_cosmetic["estimated_nova_group"] == 4 and abs(n_cosmetic["score"] - 0.0) < 1e-9,
        "detail": f"grupo={n_cosmetic['estimated_nova_group']}, score={n_cosmetic['score']}",
    })

    # 3) NOVA: 2 marcadores no cosmeticos (peso total 2) se queda en grupo 2/3, no grupo 4
    n_mild = _nova_classification_score(["isolated_sugar", "preservative"])
    checks.append({
        "name": "nova_low_weight_noncosmetic_stays_group2",
        "passed": n_mild["estimated_nova_group"] == 2 and n_mild["marker_weight_total"] == 2,
        "detail": f"grupo={n_mild['estimated_nova_group']}, peso_total={n_mild['marker_weight_total']}",
    })

    # 4) Carga glicemica: formula exacta GL = GI*carbs_netos/100
    gl = _glycemic_load_score(carbohydrates_g_per_serving=50.0, glycemic_index=70.0, fiber_g_per_serving=5.0)
    expected_gl = 70.0 * (50.0 - 5.0) / 100.0
    checks.append({
        "name": "glycemic_load_exact_formula",
        "passed": abs(gl["glycemic_load"] - expected_gl) < 1e-9,
        "detail": f"GL calculada={gl['glycemic_load']:.6f}, esperada={expected_gl:.6f}",
    })

    # 5) Carga glicemica: monotonico decreciente en score a medida que sube la carga
    gl_low = _glycemic_load_score(20.0, 40.0)
    gl_high = _glycemic_load_score(80.0, 90.0)
    checks.append({
        "name": "glycemic_load_score_monotonic",
        "passed": gl_low["score"] > gl_high["score"],
        "detail": f"score(GL bajo)={gl_low['score']:.3f}, score(GL alto)={gl_high['score']:.3f}",
    })

    # 6) Carga glicemica: el mismo alimento ultraprocesado da GI efectivo mayor -> score menor o igual
    gl_normal = _glycemic_load_score(50.0, 60.0, is_ultra_processed=False)
    gl_processed = _glycemic_load_score(50.0, 60.0, is_ultra_processed=True)
    checks.append({
        "name": "glycemic_load_processing_boost_direction",
        "passed": gl_processed["effective_glycemic_index"] > gl_normal["effective_glycemic_index"]
        and gl_processed["score"] <= gl_normal["score"],
        "detail": f"GI_efectivo normal={gl_normal['effective_glycemic_index']:.2f}, "
                  f"GI_efectivo procesado={gl_processed['effective_glycemic_index']:.2f}",
    })

    # 7) Densidad energetica: monotonico decreciente y acotado en [0,10]
    e_low = _energy_density_score(40.0)
    e_mid = _energy_density_score(200.0)
    e_high = _energy_density_score(500.0)
    checks.append({
        "name": "energy_density_monotonic_and_bounded",
        "passed": e_low["score"] > e_mid["score"] > e_high["score"]
        and abs(e_low["score"] - 10.0) < 1e-9 and abs(e_high["score"] - 0.0) < 1e-9,
        "detail": f"score(40)={e_low['score']}, score(200)={e_mid['score']:.3f}, score(500)={e_high['score']}",
    })

    # 8) Carga de aditivos: monotonico decreciente, exacto en 0 y 7+ aditivos
    a_zero = _additive_load_score(0)
    a_three = _additive_load_score(3)
    a_many = _additive_load_score(10)
    checks.append({
        "name": "additive_load_monotonic_and_saturates",
        "passed": abs(a_zero["score"] - 10.0) < 1e-9
        and a_three["score"] < a_zero["score"]
        and abs(a_many["score"] - 0.0) < 1e-9,
        "detail": f"score(0)={a_zero['score']}, score(3)={a_three['score']:.3f}, score(10)={a_many['score']}",
    })

    # 9) Compuesto: con las 4 dimensiones y pesos iguales, exactamente el promedio simple
    comp_equal = _composite_score(
        nova_score=10.0, glycemic_load_score=6.0, energy_density_score=4.0, additive_load_score=8.0,
    )
    expected_avg = (10.0 + 6.0 + 4.0 + 8.0) / 4.0
    checks.append({
        "name": "composite_score_exact_simple_average",
        "passed": abs(comp_equal["score"] - expected_avg) < 1e-9,
        "detail": f"compuesto={comp_equal['score']:.9f}, esperado={expected_avg:.9f}",
    })

    # 10) Compuesto: renormalizacion de pesos al omitir dimensiones
    comp_partial = _composite_score(
        nova_score=2.0, glycemic_load_score=None, energy_density_score=8.0, additive_load_score=None,
        weight_nova=1.0, weight_energy_density=3.0,
    )
    expected_partial = (2.0 * 0.25) + (8.0 * 0.75)  # pesos 1:3 -> 0.25/0.75
    weights_sum_to_one = abs(sum(comp_partial["normalized_weights"].values()) - 1.0) < 1e-9
    checks.append({
        "name": "composite_score_weight_renormalization",
        "passed": set(comp_partial["included_dimensions"]) == {"nova", "energy_density"}
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
def ultra_processed_metabolism_tool(mode, **kwargs):
    if mode == "nova_classification_score":
        return _nova_classification_score(ingredient_markers=kwargs.get("ingredient_markers", []))
    elif mode == "glycemic_load_score":
        return _glycemic_load_score(
            carbohydrates_g_per_serving=kwargs["carbohydrates_g_per_serving"],
            glycemic_index=kwargs["glycemic_index"],
            fiber_g_per_serving=kwargs.get("fiber_g_per_serving", 0.0),
            is_ultra_processed=kwargs.get("is_ultra_processed", False),
            processing_gi_boost_fraction=kwargs.get("processing_gi_boost_fraction", 0.15),
        )
    elif mode == "energy_density_score":
        return _energy_density_score(kcal_per_100g=kwargs["kcal_per_100g"])
    elif mode == "additive_load_score":
        return _additive_load_score(additive_count=kwargs["additive_count"])
    elif mode == "composite_score":
        return _composite_score(
            nova_score=kwargs.get("nova_score"),
            glycemic_load_score=kwargs.get("glycemic_load_score"),
            energy_density_score=kwargs.get("energy_density_score"),
            additive_load_score=kwargs.get("additive_load_score"),
            weight_nova=kwargs.get("weight_nova", 1.0),
            weight_glycemic=kwargs.get("weight_glycemic", 1.0),
            weight_energy_density=kwargs.get("weight_energy_density", 1.0),
            weight_additive=kwargs.get("weight_additive", 1.0),
        )
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            f"mode desconocido: {mode!r}. Debe ser uno de "
            "['nova_classification_score', 'glycemic_load_score', 'energy_density_score', "
            "'additive_load_score', 'composite_score', 'validate']"
        )


# ---------------------------------------------------------------------------
# SCHEMA
# ---------------------------------------------------------------------------
ULTRA_PROCESSED_METABOLISM_TOOL_SCHEMA = {
    "name": "ultra_processed_metabolism_tool",
    "description": (
        "Calcula puntajes 0-10 (10=mejor) relacionados con grado de procesamiento industrial e "
        "impacto metabolico esperado de un alimento: clasificacion NOVA aproximada, carga glicemica "
        "(con heuristica de aceleracion por procesamiento), densidad energetica, y carga de "
        "aditivos. Mas un puntaje compuesto ponderado (renormaliza si se omite alguna dimension). "
        "Herramienta educativa/comparativa, no reemplaza asesoria nutricional profesional. "
        "mode='validate' corre 10 chequeos."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["nova_classification_score", "glycemic_load_score", "energy_density_score",
                         "additive_load_score", "composite_score", "validate"],
                "description": "Que dimension calcular, o 'validate' para autochequeo",
            },
            "ingredient_markers": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(_INGREDIENT_MARKERS.keys())},
                "description": "Marcadores de ingredientes presentes (nova_classification_score)",
            },
            "carbohydrates_g_per_serving": {"type": "number", "description": "Carbohidratos totales por porcion, g (glycemic_load_score)"},
            "glycemic_index": {"type": "number", "description": "Indice glicemico del alimento, 0-110 (glycemic_load_score)"},
            "fiber_g_per_serving": {"type": "number", "description": "Fibra por porcion, g (default 0.0)"},
            "is_ultra_processed": {"type": "boolean", "description": "Aplica el boost heuristico de GI por procesamiento (default false)"},
            "processing_gi_boost_fraction": {"type": "number", "description": "Fraccion de aumento del GI por procesamiento (default 0.15)"},
            "kcal_per_100g": {"type": "number", "description": "Densidad energetica, kcal/100g (energy_density_score)"},
            "additive_count": {"type": "integer", "description": "Cantidad de aditivos declarados en la lista de ingredientes (additive_load_score)"},
            "nova_score": {"type": "number", "description": "Score NOVA ya calculado (composite_score)"},
            "glycemic_load_score": {"type": "number", "description": "Score de carga glicemica ya calculado (composite_score)"},
            "energy_density_score": {"type": "number", "description": "Score de densidad energetica ya calculado (composite_score)"},
            "additive_load_score": {"type": "number", "description": "Score de carga de aditivos ya calculado (composite_score)"},
            "weight_nova": {"type": "number", "description": "Peso de NOVA en el compuesto (default 1.0)"},
            "weight_glycemic": {"type": "number", "description": "Peso de carga glicemica en el compuesto (default 1.0)"},
            "weight_energy_density": {"type": "number", "description": "Peso de densidad energetica en el compuesto (default 1.0)"},
            "weight_additive": {"type": "number", "description": "Peso de carga de aditivos en el compuesto (default 1.0)"},
        },
        "required": ["mode"],
    },
}


def _handler(kwargs):
    mode = kwargs.pop("mode")
    return ultra_processed_metabolism_tool(mode, **kwargs)


try:
    from tool_registry import register_tool
    register_tool("ultra_processed_metabolism_tool", ULTRA_PROCESSED_METABOLISM_TOOL_SCHEMA, _handler)
except ImportError:
    pass


if __name__ == "__main__":
    import json
    result = _validate()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print()
    print(f"validation_passed: {result['validation_passed']} "
          f"({result['n_passed']}/{result['n_checks']} checks)")
