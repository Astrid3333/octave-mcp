"""
semantic_bridge_tool.py

Wrapper de recomendacion (Fase 2 acotada, "la primera opcion"): dado una
tarea en lenguaje natural, devuelve tools candidatas usando el motor
lexico ya existente en knowledge_graph_tool.py. NO ejecuta nada, NO arma
ni corre pipelines -- eso queda en manos del usuario, que arma el
run_pipeline a mano con los nombres recomendados.

Por que no usa el patron generico de tool_registry (register_tool +
lambda de una linea): al igual que knowledge_graph_tool.py, este modulo
necesita la lista completa de schemas (TOOLS) para poder buscar/recomendar,
y esa lista se arma en server.py. Se registra via un 'elif tool_name ==
"semantic_bridge"' dedicado en el dispatch de server.py, mismo patron ya
usado para knowledge_graph_tool -- no via tool_registry.register_tool().
"""
import json

from knowledge_graph_tool import compute_knowledge_graph


def _mode_recommend(params, tools):
    """
    mode='recommend': busca tools relevantes para una tarea en lenguaje
    natural, reusando compute_knowledge_graph(mode='search', ...) y
    adicionalmente arma sugerencias de 'related' para el top resultado
    (para exponer vecinos tematicos, no solo el hit directo).

    Traduce los nombres de parametro "amigables" de semantic_bridge
    (task_description, max_results) a los que espera realmente
    compute_knowledge_graph (query, top_k).
    """
    task_description = params.get("task_description", "")
    max_results = params.get("max_results", 8)

    try:
        search_result = compute_knowledge_graph(
            "search",
            {"query": task_description, "top_k": max_results},
            tools=tools,
        )
    except ValueError as e:
        # _mode_search lanza ValueError si la query queda sin tokens
        # utiles (ej: vacia, o solo stopwords). Lo convertimos en una
        # respuesta normal en vez de dejar que reviente sin control.
        return {
            "task_description": task_description,
            "candidatos": [],
            "relacionadas_con_top_candidato": None,
            "nota": f"No se pudo buscar: {e}",
        }

    candidates = search_result.get("resultados", [])
    top_name = candidates[0]["tool"] if candidates else None

    related = None
    if top_name:
        related = compute_knowledge_graph(
            "related",
            {"tool_name": top_name},
            tools=tools,
        )

    return {
        "task_description": task_description,
        "candidatos": candidates,
        "relacionadas_con_top_candidato": related,
        "nota": (
            "Esto es solo una recomendacion -- no se ejecuto ninguna tool. "
            "Para correrlas encadenadas, armar un pipeline con run_pipeline "
            "usando los nombres sugeridos arriba (clave 'tool' de cada candidato)."
        ),
    }


def compute_semantic_bridge(mode, params=None, tools=None):
    """
    Handler de la tool 'semantic_bridge'. mode='recommend' es el unico
    modo real (mas mode='validate' para autochequeo). Requiere 'tools'
    (lista de schemas), inyectada por el dispatcher -- igual que
    knowledge_graph_tool.
    """
    if tools is None:
        raise ValueError(
            "Se requiere la lista TOOLS del servidor (pasada por el dispatcher), "
            "igual que knowledge_graph_tool."
        )
    params = params or {}

    if mode == "recommend":
        return _mode_recommend(params, tools)

    elif mode == "validate":
        checks = []

        r1 = _mode_recommend({"task_description": "sismo terremoto magnitud"}, tools)
        found_earthquake = any(
            "earthquake" in (c.get("tool") or "") for c in r1.get("candidatos", [])
        )
        checks.append({
            "name": "recommend_encuentra_tool_relevante_para_sismo",
            "passed": found_earthquake,
        })

        r2 = _mode_recommend({"task_description": "xyzxyz_termino_sin_sentido_123"}, tools)
        checks.append({
            "name": "recommend_no_rompe_con_query_sin_matches",
            "passed": "candidatos" in r2,
        })

        all_passed = all(c["passed"] for c in checks)
        return {"checks": checks, "validation_passed": all_passed}

    else:
        raise ValueError(f"Modo desconocido para semantic_bridge: {mode}. Usar: recommend | validate")


SEMANTIC_BRIDGE_TOOL_SCHEMA = {
    "name": "semantic_bridge",
    "description": (
        "Recomendador de tools para una tarea descrita en lenguaje natural. "
        "mode='recommend': busca candidatas relevantes (reusa el motor lexico "
        "de knowledge_graph_tool sobre nombre+descripcion de cada tool) y "
        "ademas sugiere tools relacionadas con la mejor candidata. NO ejecuta "
        "nada -- solo recomienda; para correr las tools encontradas, armar un "
        "pipeline explicito con run_pipeline usando los nombres sugeridos. "
        "mode='validate' (suite de 2 checks)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"mode": {"type": "string"}, "params": {"type": "object"}},
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    # Self-test standalone: necesita TOOLS, que normalmente arma server.py.
    # Para probarlo aislado, construimos una lista minima de schemas de
    # ejemplo -- NO representa el catalogo real, solo valida que la logica
    # de _mode_recommend funcione sobre datos de juguete.
    fake_tools = [
        {"name": "earthquake_analysis_tool", "description": "Peligrosidad sismica, atenuacion PGA, magnitud, terremoto"},
        {"name": "wildfire_risk_tool", "description": "Riesgo de incendios forestales, propagacion, viento"},
        {"name": "savings_rate_tool", "description": "Ahorro personal, tasa de ahorro, finanzas"},
    ]
    d = compute_semantic_bridge("validate", tools=fake_tools)
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de semantic_bridge (semantic_bridge_tool.py) pasaron OK sobre datos de prueba.")
    print("NOTA: este self-test usa una lista de tools de juguete, no el catalogo real (eso requiere server.py).")
