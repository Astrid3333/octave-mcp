"""
knowledge_graph_tool.py
Guia de exploracion sobre el propio catalogo de tools de octave-mcp, derivada
en vivo de los TOOLS schemas (nombre + descripcion) ya registrados en server.py.
No mantiene un grafo aparte a mano: si se agrega/saca una tool en server.py,
este tool queda actualizado automaticamente (recibe TOOLS por parametro).

Integrar en server.py:
  - import: from knowledge_graph_tool import compute_knowledge_graph, KNOWLEDGE_GRAPH_TOOL_SCHEMA
  - dispatcher: elif tool_name == "knowledge_graph_tool":
                    result = compute_knowledge_graph(args.get("mode"), args.get("params"), tools=TOOLS)
  - schema list: agregar KNOWLEDGE_GRAPH_TOOL_SCHEMA
  (requiere que TOOLS ya este definido en el momento del dispatch, lo cual es
   cierto porque TOOLS se arma a nivel de modulo antes del loop de requests)
"""

import re
import unicodedata

_STOPWORDS_ES = {
    "el", "la", "los", "las", "de", "del", "un", "una", "y", "o", "en", "con",
    "para", "por", "que", "se", "su", "sus", "es", "al", "como", "sobre",
    "entre", "esta", "este", "estos", "estas", "sin", "mas", "tool", "herramienta",
    "via", "contra", "corre", "corriendo", "usa", "usar", "dado", "dada",
    "calcula", "calculo", "devuelve", "retorna",
    # boilerplate de docstrings/suites de validacion, sin valor de dominio
    "checks", "quien", "llama", "suite", "confidence_flag", "validado",
}
_STOPWORDS_EN = {
    "the", "a", "an", "of", "and", "or", "in", "with", "for", "that", "is",
    "to", "on", "as", "tool", "mode", "validate", "custom", "presets", "preset",
    "octave",
}
_STOPWORDS = _STOPWORDS_ES | _STOPWORDS_EN

# Pares de sufijos adjetivales masc/fem frecuentes en las descripciones
# (ej. "bacteriano"/"bacteriana", "estocastico"/"estocastica"). Recortar
# la vocal final colapsa ambas formas al mismo stem para el scoring.
_GENDER_SUFFIXES = (
    "ano", "ana", "ico", "ica", "ivo", "iva", "oso", "osa",
    "ado", "ada", "ido", "ida", "ario", "aria", "orio", "oria",
)


def _strip_accents(s):
    """Normaliza tildes (ej. 'bacteriologico' == 'bacteriologico') via NFD unicode."""
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _stem_es(word):
    """
    Stemming liviano y conservador (sin libreria externa, consistente con
    el resto del proyecto): colapsa plural simple y variacion de genero
    en sufijos adjetivales comunes, para que 'bacteriano' y 'bacteriana'
    (o 'simulaciones' y 'simulacion') puntuen como el mismo termino en el
    scoring lexico. No es un stemmer linguisticamente completo -- solo
    cubre los patrones mas frecuentes en las descripciones de tools de
    este repo. Guardado conservador via longitudes minimas para evitar
    comerse palabras cortas por error.
    """
    w = word
    if len(w) > 6 and w.endswith("ciones"):
        w = w[:-3]  # "simulaciones" -> "simulacion"
    elif len(w) > 5 and re.search(r"[aeiou]s$", w):
        w = w[:-1]  # "bacterianas" -> "bacteriana", "modelos" -> "modelo"
    elif len(w) > 6 and w.endswith("es"):
        w = w[:-2]  # "arboles" -> "arbol"

    for suf in _GENDER_SUFFIXES:
        if len(w) > 7 and w.endswith(suf):
            w = w[:-1]  # "bacteriano"/"bacteriana" -> "bacterian"
            break

    return w


def _tokenize(text):
    text = _strip_accents(text.lower())
    words = re.findall(r"[a-z0-9_]+", text)
    return [_stem_es(w) for w in words if w not in _STOPWORDS and len(w) > 2]


def _tokenize_with_originals(text):
    """
    Igual que _tokenize, pero devuelve pares (stem, palabra_original) en vez
    de solo el stem. Usado por _mode_stats para poder mostrar una forma
    legible (ej. 'analitico') en vez del stem pelado (ej. 'analitic').
    """
    text = _strip_accents(text.lower())
    words = re.findall(r"[a-z0-9_]+", text)
    return [
        (_stem_es(w), w) for w in words if w not in _STOPWORDS and len(w) > 2
    ]


def _tool_text(schema):
    name = schema.get("name", "")
    desc = schema.get("description", "")
    return f"{name} {desc}"


def _score(query_tokens, tool_tokens):
    """Score simple: overlap ponderado, con bonus si el termino aparece en el nombre."""
    tool_set = set(tool_tokens)
    overlap = sum(1 for t in query_tokens if t in tool_set)
    return overlap


def _mode_search(p, tools):
    query = p.get("query", "")
    top_k = p.get("top_k", 8)
    q_tokens = _tokenize(query)
    if not q_tokens:
        raise ValueError("query vacia o sin terminos utiles")

    scored = []
    for schema in tools:
        t_tokens = _tokenize(_tool_text(schema))
        s = _score(q_tokens, t_tokens)
        if s > 0:
            scored.append((s, schema))

    scored.sort(key=lambda x: -x[0])
    resultados = [
        {
            "tool": s["name"],
            "score": sc,
            "descripcion": s.get("description", "")[:220],
        }
        for sc, s in scored[:top_k]
    ]

    return {
        "query": query,
        "n_candidatas": len(scored),
        "resultados": resultados,
        "sugerencia": (
            "Sin coincidencias directas; probar terminos mas generales o en ingles."
            if not resultados
            else "Revisa las tools de mayor score primero; usa mode='related' con el nombre "
            "de la mejor candidata para explorar tools conectadas por vocabulario compartido."
        ),
    }


def _mode_related(p, tools):
    tool_name = p.get("tool_name")
    top_k = p.get("top_k", 6)
    target = next((s for s in tools if s.get("name") == tool_name), None)
    if target is None:
        raise ValueError(f"tool_name '{tool_name}' no encontrado en TOOLS")

    target_tokens = set(_tokenize(_tool_text(target)))

    scored = []
    for schema in tools:
        if schema.get("name") == tool_name:
            continue
        t_tokens = set(_tokenize(_tool_text(schema)))
        shared = target_tokens & t_tokens
        if shared:
            scored.append((len(shared), schema, shared))

    scored.sort(key=lambda x: -x[0])
    resultados = [
        {
            "tool": s["name"],
            "terminos_compartidos": sorted(shared),
            "n_compartidos": n,
        }
        for n, s, shared in scored[:top_k]
    ]

    return {"tool_base": tool_name, "relacionadas": resultados}


def _mode_stats(p, tools):
    """Panorama rapido: cuantas tools hay, cuales son las palabras mas frecuentes
    en las descripciones (proxy de 'areas' del catalogo, sin categorias a mano).
    Cuenta por stem (para agrupar variantes de genero/numero) pero muestra la
    forma original mas frecuente de cada stem, para que el output sea legible
    (ej. 'analitico' en vez de 'analitic')."""
    from collections import Counter
    stem_tool_counter = Counter()      # stem -> en cuantas tools aparece
    stem_original_counter = Counter()  # (stem, palabra_original) -> frecuencia global

    for schema in tools:
        pairs = _tokenize_with_originals(_tool_text(schema))
        stems_in_tool = set(stem for stem, _ in pairs)
        stem_tool_counter.update(stems_in_tool)
        for stem, original in pairs:
            stem_original_counter[(stem, original)] += 1

    top_stems = stem_tool_counter.most_common(p.get("top_k", 25))

    display_form = {}
    for (stem, original), _ in stem_original_counter.most_common():
        if stem not in display_form:
            display_form[stem] = original

    return {
        "n_tools_totales": len(tools),
        "terminos_mas_frecuentes": [
            {"termino": display_form.get(stem, stem), "n_tools": n}
            for stem, n in top_stems
        ],
    }


def compute_knowledge_graph(mode, params=None, tools=None):
    if tools is None:
        raise ValueError("Se requiere la lista TOOLS del servidor (pasada por el dispatcher)")
    params = params or {}
    if mode == "search":
        return _mode_search(params, tools)
    elif mode == "related":
        return _mode_related(params, tools)
    elif mode == "stats":
        return _mode_stats(params, tools)
    else:
        raise ValueError(f"Modo desconocido: {mode}. Usar: search | related | stats")


KNOWLEDGE_GRAPH_TOOL_SCHEMA = {
    "name": "knowledge_graph_tool",
    "description": (
        "Guia de exploracion sobre el catalogo de tools de octave-mcp. mode='search': "
        "busca tools relevantes para una consulta en lenguaje natural (scoring lexico "
        "sobre nombre+descripcion de cada tool, sin categorias hardcodeadas). "
        "mode='related': dado el nombre de una tool, encuentra otras que comparten "
        "vocabulario en su descripcion. mode='stats': panorama del catalogo completo "
        "(terminos mas frecuentes, proxy de areas cubiertas). Se deriva en vivo de "
        "TOOLS, no requiere mantenimiento manual cuando se agregan tools nuevas."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["search", "related", "stats"]},
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}
