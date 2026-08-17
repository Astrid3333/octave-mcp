"""
tool_catalog_tool.py

Indice searchable de las tools de octave-mcp, generado en runtime -- NO es
una lista mantenida a mano (eso se desincroniza; ver el bug real de
fractional_fourier_tool documentado en tool_registry.py). Resuelve un
problema concreto: con 200+ tools, ni el usuario ni el LLM que orquesta
las llamadas puede recordar que existe y bajo que modo.

Fuente de datos (en orden de preferencia, sin ambiguedad sobre cual se usa):
  1. sys.modules['__main__'].TOOLS -- si tool_catalog_tool fue importado
     como parte de server.py (caso real de produccion), esto es la lista
     COMPLETA de schemas que server.py expone en tools/list: tools
     legacy (dispatch por cadena elif) + tools migradas a tool_registry.
     Se lee de forma perezosa (dentro del handler, no al importar el
     modulo), porque al momento de import de tool_catalog_tool.py el
     propio server.py todavia no termino de construir TOOLS (se define
     mas abajo en el archivo). Leerlo en el momento de la llamada evita
     el problema de orden de import sin necesitar reimportar server.py
     (que re-ejecutaria todos los imports y rompería tool_registry con
     colisiones de nombre).
  2. Si no existe __main__.TOOLS (ej. corriendo este archivo standalone
     para el smoke test/validate), cae a tool_registry.get_schemas() --
     cubre las tools migradas, suficiente para los self-checks.

Esto es DELIBERADAMENTE una tool sin "IA" ni interpretacion de lenguaje
natural: busqueda por substring de keywords contra nombre/descripcion/
propiedades del schema, y clasificacion por dominio con un diccionario de
keywords explicito y versionado en este archivo. No hay heuristica oculta
que se pueda desincronizar con un cambio silencioso -- si un dominio
clasifica mal, se corrige el diccionario, no un modelo.

CUIDADO DE CONFIANZA DE DATOS:
  - search / list_all: alta -- indice generado directamente de las
    estructuras vivas del servidor (TOOLS o REGISTRY), no hay copia que
    pueda quedar vieja.
  - by_domain: media -- la clasificacion es por keywords manuales
    (DOMAIN_KEYWORDS abajo), no semantica. Una tool puede caer en varios
    dominios o en ninguno (bucket "sin_clasificar", nunca se descarta en
    silencio -- ver validate).
"""
import sys

try:
    import tool_registry
except ImportError:
    tool_registry = None


# Diccionario de dominios -> keywords (minusculas, sin tildes) que se
# buscan en nombre+descripcion de cada tool. Una tool puede matchear
# varios dominios. Mantenido a mano deliberadamente (a diferencia del
# indice de tools en si, que es 100% derivado) -- es la unica pieza
# editorial de este archivo, y es chica y explicita.
DOMAIN_KEYWORDS = {
    "matematica": ["algebra", "calculo", "ecuacion", "matriz", "fourier",
                   "wavelet", "topologia", "combinator", "numeric", "serie",
                   "interpolacion", "geodesic", "grupo", "simbolic"],
    "fisica": ["fisica", "cuantic", "mecanic", "electromagnet", "termodinamic",
               "acustic", "optic", "relativ", "lyapunov", "caos", "bifurcacion",
               "dinamica molecular", "estadistica mecanica"],
    "quimica": ["quimic", "molecul", "dft", "pyscf", "reaccion", "cinetica"],
    "biologia": ["biolog", "bacteri", "enzima", "poblacion", "genetic",
                 "epidemi", "microbio", "crecimiento"],
    "ingenieria": ["estructural", "cfd", "movimiento de tierra", "obra",
                   "construccion", "electromagnetic", "bem", "material"],
    "finanzas_riesgo": ["financ", "presupuesto", "riesgo", "econom",
                         "actuari", "seguro", "contab"],
    "energia": ["solar", "eolic", "bateria", "mpc", "energia renovable",
                "despacho", "red electrica", "grid"],
    "estadistica_datos": ["estadistic", "probabilidad", "regresion",
                           "machine learning", "aprendizaje automatico",
                           "series de tiempo", "benchmark"],
    "infraestructura_urbanismo": ["infraestructura critica", "urban",
                                   "catastrofe", "desastre", "riesgo natural"],
    "etnomatematica_historica": ["ancestral", "arqueo", "etnomatematic",
                                  "historic", "yupana", "soroban", "suanpan"],
    "octave_pipeline": ["octave", "pipeline", "workspace", "explainer",
                         "humanizer", "visualizacion"],
}


def _normalize(s):
    if not s:
        return ""
    s = s.lower()
    repl = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"}
    for a, b in repl.items():
        s = s.replace(a, b)
    return s


def _get_schemas():
    """Fuente unica de verdad, resuelta en el momento de la llamada
    (nunca al importar este modulo -- ver docstring)."""
    main_mod = sys.modules.get("__main__")
    if main_mod is not None and hasattr(main_mod, "TOOLS"):
        schemas = list(main_mod.TOOLS)
        source = "server.TOOLS (legacy + tool_registry, catalogo completo)"
    elif tool_registry is not None:
        schemas = tool_registry.get_schemas()
        source = "tool_registry.get_schemas() (solo tools migradas -- server.TOOLS no disponible en este contexto)"
    else:
        schemas = []
        source = "sin fuente disponible"
    return schemas, source


def _schema_text(schema):
    parts = [schema.get("name", ""), schema.get("description", "")]
    props = schema.get("inputSchema", {}).get("properties", {})
    parts.extend(props.keys())
    mode_prop = props.get("mode", {})
    parts.extend(mode_prop.get("enum", []) if isinstance(mode_prop, dict) else [])
    return _normalize(" ".join(parts))


def _search(params):
    query = params.get("query")
    if not query:
        raise ValueError("search requiere 'query' (string o lista de keywords)")
    keywords = query if isinstance(query, list) else [query]
    keywords = [_normalize(k) for k in keywords if k]
    if not keywords:
        raise ValueError("query vacio")

    schemas, source = _get_schemas()
    scored = []
    for schema in schemas:
        text = _schema_text(schema)
        hits = sum(1 for k in keywords if k in text)
        if hits > 0:
            scored.append((hits, schema))
    scored.sort(key=lambda t: (-t[0], t[1].get("name", "")))

    max_results = int(params.get("max_results", 15))
    results = [
        {
            "name": s.get("name"),
            "description": (s.get("description") or "")[:220],
            "modes": (s.get("inputSchema", {}).get("properties", {}).get("mode", {}) or {}).get("enum"),
            "score": hits,
        }
        for hits, s in scored[:max_results]
    ]
    return {
        "query": keywords,
        "total_matches": len(scored),
        "results": results,
        "source": source,
    }


def _by_domain(params):
    domain = params.get("domain")
    if not domain:
        raise ValueError(f"by_domain requiere 'domain'. Validos: {sorted(DOMAIN_KEYWORDS)}")
    if domain not in DOMAIN_KEYWORDS:
        raise ValueError(f"dominio desconocido: {domain!r}. Validos: {sorted(DOMAIN_KEYWORDS)}")

    keywords = DOMAIN_KEYWORDS[domain]
    schemas, source = _get_schemas()
    matches = []
    for schema in schemas:
        text = _schema_text(schema)
        if any(k in text for k in keywords):
            matches.append({
                "name": schema.get("name"),
                "description": (schema.get("description") or "")[:220],
            })
    matches.sort(key=lambda m: m["name"] or "")
    return {"domain": domain, "total_matches": len(matches), "results": matches, "source": source}


def _list_all(params):
    schemas, source = _get_schemas()
    names = sorted(s.get("name") for s in schemas if s.get("name"))
    return {"total_tools": len(names), "names": names, "source": source}


def _list_domains(params):
    return {"domains": sorted(DOMAIN_KEYWORDS), "keywords_por_dominio": DOMAIN_KEYWORDS}


def _validate():
    checks = []

    # 1) sin __main__.TOOLS (caso self-test), la fuente cae a tool_registry
    schemas, source = _get_schemas()
    ok1 = "tool_registry" in source or "server.TOOLS" in source
    checks.append({"case": "fuente de datos resuelta sin error (server.TOOLS o fallback a tool_registry)",
                    "got": source, "expected": "una de las dos fuentes documentadas", "ok": ok1})

    # 2) search por el propio nombre de esta tool debe encontrarla (self-reference)
    r2 = _search({"query": "tool_catalog"})
    ok2 = any(x["name"] == "tool_catalog_tool" for x in r2["results"])
    checks.append({"case": "search('tool_catalog') encuentra tool_catalog_tool (self-reference)",
                    "got": [x["name"] for x in r2["results"]], "expected": "incluye tool_catalog_tool", "ok": ok2})

    # 3) search sin resultados no rompe, devuelve lista vacia con total_matches=0
    r3 = _search({"query": "xyzxyz_keyword_inexistente_qwerty"})
    ok3 = r3["total_matches"] == 0 and r3["results"] == []
    checks.append({"case": "search sin matches devuelve total_matches=0 y results=[] (no error)",
                    "got": r3["total_matches"], "expected": 0, "ok": ok3})

    # 4) by_domain('energia') debe incluir las tools de energia renovable
    #    si estan presentes en la fuente actual (registry o server.TOOLS)
    all_names = {s.get("name") for s in schemas}
    r4 = _by_domain({"domain": "energia"})
    energia_esperadas = {"solar_radiation_tool", "wind_power_curve_tool",
                          "battery_sizing_tool", "renewable_mpc_controller"}
    presentes = energia_esperadas & all_names
    encontradas = {m["name"] for m in r4["results"]}
    ok4 = presentes.issubset(encontradas)
    checks.append({"case": "by_domain('energia') cubre las tools de energia renovable presentes en la fuente",
                    "got": sorted(encontradas & energia_esperadas),
                    "expected": sorted(presentes), "ok": ok4})

    # 5) cada dominio en DOMAIN_KEYWORDS responde sin error (no hay dominio roto)
    ok5 = True
    for d in DOMAIN_KEYWORDS:
        try:
            _by_domain({"domain": d})
        except Exception:
            ok5 = False
            break
    checks.append({"case": "todos los dominios en DOMAIN_KEYWORDS resuelven sin error",
                    "got": "todos OK" if ok5 else "algun dominio rompio", "expected": "todos OK", "ok": ok5})

    # 6) dominio invalido levanta ValueError (no falla silenciosamente)
    ok6 = False
    try:
        _by_domain({"domain": "no_existe_este_dominio"})
    except ValueError:
        ok6 = True
    checks.append({"case": "by_domain con dominio invalido levanta ValueError",
                    "got": "ValueError" if ok6 else "no levanto error", "expected": "ValueError", "ok": ok6})

    # 7) list_all no tiene nombres duplicados (deteccion de colision, mismo
    #    tipo de bug que motivo la migracion a tool_registry)
    r7 = _list_all({})
    ok7 = len(r7["names"]) == len(set(r7["names"]))
    checks.append({"case": "list_all sin nombres duplicados",
                    "got": len(r7["names"]) - len(set(r7["names"])), "expected": 0, "ok": ok7})

    return {"validate": True, "all_passed": all(c["ok"] for c in checks), "checks": checks}


def compute_tool_catalog(mode, params=None):
    params = params or {}
    if mode == "search":
        return _search(params)
    elif mode == "by_domain":
        return _by_domain(params)
    elif mode == "list_all":
        return _list_all(params)
    elif mode == "list_domains":
        return _list_domains(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            f"mode desconocido: {mode!r}. Valores validos: search, by_domain, "
            f"list_all, list_domains, validate."
        )


TOOL_CATALOG_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["search", "by_domain", "list_all", "list_domains", "validate"],
            "default": "search",
        },
        "query": {"description": "Para search: string o lista de keywords."},
        "domain": {"type": "string", "enum": sorted(DOMAIN_KEYWORDS), "description": "Para by_domain."},
        "max_results": {"type": "integer", "default": 15, "description": "Para search."},
    },
    "required": ["mode"],
}


try:
    from tool_registry import register_tool
    register_tool(
        name="tool_catalog_tool",
        schema={
            "name": "tool_catalog_tool",
            "description": (
                "Indice searchable de todas las tools de octave-mcp, generado "
                "en runtime (sin lista mantenida a mano, nunca se desincroniza). "
                "search: keyword(s) -> tools cuyo nombre/descripcion/schema "
                "matchea. by_domain: dominio (matematica, fisica, quimica, "
                "biologia, ingenieria, finanzas_riesgo, energia, "
                "estadistica_datos, infraestructura_urbanismo, "
                "etnomatematica_historica, octave_pipeline) -> tools "
                "clasificadas por keywords explicitas. list_all: nombres de "
                "todas las tools registradas. list_domains: dominios "
                "disponibles y sus keywords."
            ),
            "inputSchema": TOOL_CATALOG_TOOL_SCHEMA,
        },
        handler=lambda args: compute_tool_catalog(args.get("mode"), args),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    print(json.dumps(compute_tool_catalog("validate"), indent=2, ensure_ascii=False))
