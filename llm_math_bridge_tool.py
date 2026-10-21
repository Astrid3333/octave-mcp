"""
llm_math_bridge_tool.py
Puente entre el pipeline matematico de octave-mcp y un LLM real (Anthropic API,
llamada directa via HTTPS, sin SDK). Cuatro modos, mas un modo 'auto' que
decide entre los otros tres segun que tan dificil parece la consulta:

  - interpret    : dada una consulta en lenguaje natural, llama al LLM para
                    decidir que compute_X (de los que existen de verdad en
                    server.py, descubiertos via ast, no una lista inventada)
                    y con que parametros usar. NO ejecuta el tool, solo
                    interpreta. Devuelve {"tool", "params", "razonamiento",
                    "necesita_mas_pasos"}.

  - explain       : dado el resultado (dict) de un compute_X ya ejecutado,
                    llama al LLM para generar una explicacion en espanol,
                    lenguaje llano. No re-ejecuta nada.

  - orchestrate   : dada una consulta que puede requerir varios tools
                    encadenados, alterna interpret -> ejecutar -> evaluar si
                    hace falta otro paso, hasta max_steps o hasta que el LLM
                    diga que termino (necesita_mas_pasos=False). Al final
                    llama a explain sobre el resultado del ultimo paso.

  - auto          : heuristica barata primero, sin gastar LLM. Si la consulta
                    tiene marcadores de encadenamiento explicito ("y luego",
                    "despues", "primero...entonces", etc.) va directo a
                    orchestrate. Si no, hace un solo interpret + ejecuta +
                    explain (un tool, no una cadena). No hay heuristica que
                    evite el LLM del todo: elegir el tool correcto y sus
                    parametros reales requiere entender la consulta, eso no
                    se puede hacer con regex de forma confiable. La heuristica
                    solo decide CUANTO LLM hace falta (una llamada vs varias),
                    no si hace falta.

Requiere ANTHROPIC_API_KEY en el entorno. Si no esta seteada, cualquier modo
que necesite el LLM devuelve {"error": ...} con instrucciones, en vez de
fallar con una excepcion cruda a mitad de una cadena de pasos.

Modelo: configurable via el parametro 'model' o la variable de entorno
LLM_MATH_BRIDGE_MODEL. Default abajo en DEFAULT_MODEL -- confirmar que sea
un model id valido para tu cuenta/API key antes de usar en produccion, los
ids de modelo cambian con el tiempo y este archivo no se actualiza solo.
"""
import ast
import importlib
import json
import os
import re
import urllib.error
import urllib.request

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = os.environ.get("LLM_MATH_BRIDGE_MODEL", "claude-sonnet-5")

_VALID_MODES = ("interpret", "explain", "orchestrate", "auto")

_MULTISTEP_MARKERS = (
    "y luego", "despues", "después", "entonces", "paso 1", "primero",
    "encadena", "encadenando", "combinando", "seguido de", "una vez que",
)


# ---------------------------------------------------------------------------
# Descubrimiento de tools reales (mismo mecanismo que smoke_test.py: ast
# sobre server.py, sin lista hardcodeada que se desactualice).
# ---------------------------------------------------------------------------

def discover_tools(server_py_path="server.py"):
    """Devuelve lista de dicts {modulo, funcion, alias, doc} para cada
    'from X_tool import compute_Y [as alias]' en server.py. 'doc' es la
    primera linea no vacia del docstring de la funcion real (import + getattr
    perezoso, no se ejecuta nada)."""
    if not os.path.exists(server_py_path):
        return []
    tree = ast.parse(open(server_py_path, encoding="utf-8").read(), filename=server_py_path)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith("_tool"):
            for alias in node.names:
                if not alias.name.startswith("compute_"):
                    continue
                entry = {
                    "modulo": node.module,
                    "funcion": alias.name,
                    "alias": alias.asname or alias.name,
                    "doc": "",
                }
                try:
                    mod = importlib.import_module(node.module)
                    func = getattr(mod, alias.name, None)
                    if func and func.__doc__:
                        first_line = next(
                            (l.strip() for l in func.__doc__.splitlines() if l.strip()), ""
                        )
                        entry["doc"] = first_line
                except Exception as e:
                    entry["doc"] = f"(no se pudo importar: {type(e).__name__})"
                out.append(entry)
    return out


def _find_tool(tools, name):
    """Busca por alias o por funcion exacta (case-insensitive)."""
    name_lower = name.lower()
    for t in tools:
        if t["alias"].lower() == name_lower or t["funcion"].lower() == name_lower:
            return t
    return None


def execute_tool(tool_name, params, server_py_path="server.py"):
    """Importa el modulo real y ejecuta compute_X(**params). No inventa
    resultados si el tool no existe o si params no calza -- devuelve
    {"error": ...} describiendo exactamente que fallo."""
    tools = discover_tools(server_py_path)
    entry = _find_tool(tools, tool_name)
    if entry is None:
        nombres = [t["alias"] for t in tools]
        return {"error": f"tool '{tool_name}' no encontrado en {server_py_path}", "tools_disponibles": nombres}

    try:
        mod = importlib.import_module(entry["modulo"])
        func = getattr(mod, entry["funcion"])
    except Exception as e:
        return {"error": f"no se pudo importar {entry['modulo']}.{entry['funcion']}: {type(e).__name__}: {e}"}

    params = params or {}
    try:
        resultado = func(**params)
    except TypeError as e:
        return {"error": f"parametros invalidos para {tool_name}: {e}", "params_recibidos": params}
    except Exception as e:
        return {"error": f"{type(e).__name__} ejecutando {tool_name}: {e}", "params_recibidos": params}

    return {"tool": entry["alias"], "params": params, "resultado": resultado}


# ---------------------------------------------------------------------------
# Llamada real al LLM (Anthropic API, HTTPS directo via stdlib, sin SDK)
# ---------------------------------------------------------------------------

def _call_anthropic(system_prompt, user_prompt, model=None, max_tokens=1500):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None, (
            "ANTHROPIC_API_KEY no esta seteada en el entorno. "
            "Setearla con: export ANTHROPIC_API_KEY=sk-ant-..."
        )

    body = json.dumps({
        "model": model or DEFAULT_MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=body,
        method="POST",
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        return None, f"HTTPError {e.code} llamando a Anthropic API: {detail}"
    except urllib.error.URLError as e:
        return None, f"URLError llamando a Anthropic API: {e.reason}"

    text_parts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
    if not text_parts:
        return None, f"respuesta sin bloques de texto: {data}"
    return "\n".join(text_parts), None


def _extract_json(text):
    """El LLM a veces envuelve el JSON en ```json ... ``` pese a que se le
    pide que no lo haga. Lo limpiamos antes de parsear."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return json.loads(cleaned)


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------

def _mode_interpret(query, model, server_py_path, candidate_tools=None):
    if not query:
        return {"error": "mode='interpret' requiere 'query' (la consulta en lenguaje natural)"}

    tools = candidate_tools if candidate_tools is not None else discover_tools(server_py_path)
    if not tools:
        return {"error": f"no se encontraron tools en {server_py_path} (¿ruta correcta?)"}

    catalogo = "\n".join(f"- {t['alias']}: {t['doc']}" for t in tools)
    system_prompt = (
        "Sos un router que decide que funcion matematica usar dada una consulta "
        "en espanol. Respondes UNICAMENTE con un objeto JSON, sin texto antes ni "
        "despues, sin bloques de codigo markdown. El JSON debe tener exactamente "
        "estas claves: 'tool' (el nombre exacto de una de las funciones listadas "
        "abajo, o null si ninguna aplica), 'params' (dict con los parametros que "
        "le pasarias, best-effort a partir de la consulta), 'razonamiento' (1-2 "
        "frases en espanol de por que elegiste ese tool), 'necesita_mas_pasos' "
        "(true si la consulta requiere ademas otro tool despues de este, false "
        "si con este alcanza).\n\nTools disponibles:\n" + catalogo
    )
    raw, err = _call_anthropic(system_prompt, query, model=model)
    if err:
        return {"error": err}
    try:
        parsed = _extract_json(raw)
    except (ValueError, TypeError) as e:
        return {"error": f"el LLM no devolvio JSON valido: {e}", "respuesta_cruda": raw}

    for key in ("tool", "params", "razonamiento", "necesita_mas_pasos"):
        parsed.setdefault(key, None)
    return parsed


def _mode_explain(tool_name, result, query, model):
    if result is None:
        return {"error": "mode='explain' requiere 'result' (el dict devuelto por un compute_X ya ejecutado)"}

    system_prompt = (
        "Sos un asistente que explica resultados de calculos matematicos/"
        "cientificos en espanol llano, sin jerga innecesaria, para alguien que "
        "entiende el dominio pero quiere una lectura rapida del resultado, no "
        "un volcado de numeros. 3-5 frases. Respondes UNICAMENTE con un objeto "
        "JSON: {'explicacion': '...'}, sin texto extra ni markdown."
    )
    user_prompt = (
        f"Consulta original: {query or '(no especificada)'}\n"
        f"Tool ejecutado: {tool_name or '(no especificado)'}\n"
        f"Resultado (JSON): {json.dumps(result, ensure_ascii=False, default=str)}"
    )
    raw, err = _call_anthropic(system_prompt, user_prompt, model=model, max_tokens=500)
    if err:
        return {"error": err}
    try:
        parsed = _extract_json(raw)
    except (ValueError, TypeError):
        # Si no vino en JSON limpio, devolvemos el texto tal cual en vez de
        # fallar -- para 'explain' el texto crudo sigue siendo util.
        return {"explicacion": raw.strip()}
    return parsed


def _mode_orchestrate(query, model, max_steps, server_py_path):
    if not query:
        return {"error": "mode='orchestrate' requiere 'query'"}

    trace = []
    contexto = query
    ultimo_resultado = None
    ultimo_tool = None

    for step in range(1, max_steps + 1):
        decision = _mode_interpret(contexto, model, server_py_path)
        if "error" in decision:
            trace.append({"paso": step, "error_interpret": decision["error"]})
            break
        if not decision.get("tool"):
            trace.append({"paso": step, "nota": "el LLM no eligio ningun tool, deteniendo"})
            break

        ejecucion = execute_tool(decision["tool"], decision.get("params") or {}, server_py_path)
        trace.append({"paso": step, "decision": decision, "ejecucion": ejecucion})

        if "error" in ejecucion:
            # le devolvemos el error al LLM en el proximo paso para que
            # decida si reintentar con otros params o abandonar, en vez de
            # simplemente cortar la cadena.
            contexto = (
                f"{query}\n\n[Contexto: en el paso {step} se intento usar "
                f"'{decision['tool']}' con params {decision.get('params')} y fallo "
                f"con: {ejecucion['error']}. Elegi otro tool u otros params, o "
                f"respondé necesita_mas_pasos=false si no se puede continuar.]"
            )
            ultimo_resultado, ultimo_tool = None, None
            if not decision.get("necesita_mas_pasos", True):
                break
            continue

        ultimo_resultado = ejecucion["resultado"]
        ultimo_tool = ejecucion["tool"]

        if not decision.get("necesita_mas_pasos"):
            break

        contexto = (
            f"{query}\n\n[Contexto: en el paso {step} se ejecuto '{ultimo_tool}' "
            f"y dio este resultado: {json.dumps(ultimo_resultado, ensure_ascii=False, default=str)}. "
            "Decidí el proximo paso, o respondé necesita_mas_pasos=false si ya "
            "se completo lo pedido.]"
        )

    explicacion = None
    if ultimo_resultado is not None:
        explicacion = _mode_explain(ultimo_tool, ultimo_resultado, query, model)

    return {
        "query": query,
        "n_pasos": len(trace),
        "trace": trace,
        "resultado_final": ultimo_resultado,
        "tool_final": ultimo_tool,
        "explicacion": explicacion,
    }


def _estimate_difficulty(query):
    q = query.lower()
    if any(marker in q for marker in _MULTISTEP_MARKERS):
        return "compleja"
    return "simple"


def _mode_auto(query, model, max_steps, server_py_path):
    if not query:
        return {"error": "mode='auto' requiere 'query'"}

    dificultad = _estimate_difficulty(query)

    if dificultad == "compleja":
        resultado = _mode_orchestrate(query, model, max_steps, server_py_path)
        resultado["dificultad_estimada"] = dificultad
        resultado["ruta_tomada"] = "orchestrate"
        return resultado

    decision = _mode_interpret(query, model, server_py_path)
    if "error" in decision:
        decision["dificultad_estimada"] = dificultad
        decision["ruta_tomada"] = "interpret"
        return decision
    if not decision.get("tool"):
        return {
            "dificultad_estimada": dificultad, "ruta_tomada": "interpret",
            "nota": "el LLM no encontro un tool aplicable", "decision": decision,
        }

    ejecucion = execute_tool(decision["tool"], decision.get("params") or {}, server_py_path)
    explicacion = None
    if "error" not in ejecucion:
        explicacion = _mode_explain(ejecucion["tool"], ejecucion["resultado"], query, model)

    return {
        "dificultad_estimada": dificultad,
        "ruta_tomada": "interpret+execute+explain",
        "decision": decision,
        "ejecucion": ejecucion,
        "explicacion": explicacion,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def compute_llm_math_bridge(mode="auto", query=None, tool_name=None, params=None,
                             result=None, max_steps=3, model=None, server_py_path="server.py"):
    if mode not in _VALID_MODES:
        return {"error": f"mode desconocido: '{mode}'", "modos_validos": list(_VALID_MODES)}

    if mode == "interpret":
        return _mode_interpret(query, model, server_py_path)
    if mode == "explain":
        return _mode_explain(tool_name, result, query, model)
    if mode == "orchestrate":
        return _mode_orchestrate(query, model, max_steps, server_py_path)
    return _mode_auto(query, model, max_steps, server_py_path)


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY no seteada -- solo pruebo discover_tools() y execute_tool(), sin LLM.\n")
        tools = discover_tools()
        print(f"Tools descubiertos: {len(tools)}")
        for t in tools[:5]:
            print(f"  - {t['alias']}: {t['doc']}")
        if len(tools) > 5:
            print(f"  ... y {len(tools) - 5} mas")
    else:
        print(compute_llm_math_bridge(
            mode="auto",
            query="Calcula el numero de Lyapunov del mapa logistico",
        ))
