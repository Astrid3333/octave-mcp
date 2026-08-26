#!/usr/bin/env python3
"""
Agrega mode="validate" a knowledge_graph_tool.py:
  1) Inserta _mode_validate(params, tools) antes de compute_knowledge_graph()
     -- usa un catalogo sintetico propio, autocontenido, NO depende del
     parametro `tools` recibido (igual que el bloque __main__ existente).
  2) Agrega la rama elif mode == "validate" en el dispatch, y actualiza
     el mensaje de error del modo desconocido.
  3) Actualiza el enum del inputSchema para incluir "validate".

Uso:
    cd ~/octave-mcp
    python3 patch_knowledge_graph_add_validate.py
"""
import ast
import datetime
import pathlib
import py_compile
import sys

TARGET = pathlib.Path("knowledge_graph_tool.py")

if not TARGET.exists():
    print(f"ERROR: no se encuentra {TARGET} en el directorio actual.", file=sys.stderr)
    sys.exit(1)

original = TARGET.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# 1) Insertar _mode_validate antes de compute_knowledge_graph
# ---------------------------------------------------------------------------
ANCHOR_1 = "def compute_knowledge_graph(mode, params=None, tools=None):"
count_1 = original.count(ANCHOR_1)
assert count_1 == 1, f"ancla (def compute_knowledge_graph) aparece {count_1} veces, se esperaba 1"

VALIDATE_FN = '''def _mode_validate(p, tools):
    """Self-test autocontenido: usa un catalogo sintetico propio (no el
    `tools` real del server) para que el resultado sea determinista y no
    dependa de que tools cambien con el tiempo. Ejercita search, related,
    stats y el manejo de errores de cada uno."""
    checks = []

    _VALIDATE_TOOLS = [
        {
            "name": "control_theory",
            "description": (
                "Teoria de control: respuesta a escalon de lazo PID cerrado, "
                "estabilidad de Routh-Hurwitz, lugar de raices, control OGY "
                "para estabilizar orbitas periodicas inestables."
            ),
        },
        {
            "name": "optimal_control",
            "description": "Control optimo: LQR, ley de control -Kx, simulacion de lazo cerrado.",
        },
        {
            "name": "bacterial_growth_tool",
            "description": (
                "Simulacion de crecimiento bacteriano: modelo logistico y "
                "exponencial, poblacion bacteriana en funcion del tiempo."
            ),
        },
        {
            "name": "enzyme_kinetics",
            "description": "Cinetica enzimatica: Michaelis-Menten, full kinetics E+S<->ES->E+P.",
        },
    ]

    def _check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})

    # --- search: coincidencia directa por nombre+descripcion ---
    try:
        r = _mode_search({"query": "estabilidad control PID lazo cerrado"}, _VALIDATE_TOOLS)
        ok = (
            bool(r["resultados"])
            and r["resultados"][0]["tool"] == "control_theory"
            and (len(r["resultados"]) < 2 or r["resultados"][0]["score"] > r["resultados"][1]["score"])
        )
        _check("search_encuentra_match_directo", ok)
    except Exception:
        _check("search_encuentra_match_directo", False)

    # --- search: stemming de genero (bacteriano/bacteriana) debe matchear ---
    try:
        r = _mode_search({"query": "poblacion bacteriana"}, _VALIDATE_TOOLS)
        tools_encontradas = [x["tool"] for x in r["resultados"]]
        _check("search_stemming_genero", "bacterial_growth_tool" in tools_encontradas)
    except Exception:
        _check("search_stemming_genero", False)

    # --- search: query vacia/solo stopwords debe lanzar ValueError ---
    try:
        _mode_search({"query": "el de la"}, _VALIDATE_TOOLS)
        _check("search_query_vacia_lanza_valueerror", False)
    except ValueError:
        _check("search_query_vacia_lanza_valueerror", True)
    except Exception:
        _check("search_query_vacia_lanza_valueerror", False)

    # --- related: control_theory y optimal_control comparten vocabulario ---
    try:
        r = _mode_related({"tool_name": "control_theory"}, _VALIDATE_TOOLS)
        ok = bool(r["relacionadas"]) and r["relacionadas"][0]["tool"] == "optimal_control"
        _check("related_encuentra_tool_conectada", ok)
    except Exception:
        _check("related_encuentra_tool_conectada", False)

    # --- related: tool_name inexistente debe lanzar ValueError ---
    try:
        _mode_related({"tool_name": "tool_que_no_existe"}, _VALIDATE_TOOLS)
        _check("related_tool_inexistente_lanza_valueerror", False)
    except ValueError:
        _check("related_tool_inexistente_lanza_valueerror", True)
    except Exception:
        _check("related_tool_inexistente_lanza_valueerror", False)

    # --- stats: cuenta tools correctamente ---
    try:
        r = _mode_stats({"top_k": 25}, _VALIDATE_TOOLS)
        _check("stats_cuenta_tools_correctamente", r["n_tools_totales"] == len(_VALIDATE_TOOLS))
    except Exception:
        _check("stats_cuenta_tools_correctamente", False)

    # --- modo desconocido debe lanzar ValueError ---
    try:
        compute_knowledge_graph("modo_inventado", {}, tools=_VALIDATE_TOOLS)
        _check("modo_desconocido_lanza_valueerror", False)
    except ValueError:
        _check("modo_desconocido_lanza_valueerror", True)
    except Exception:
        _check("modo_desconocido_lanza_valueerror", False)

    return {
        "checks": checks,
        "validation_passed": all(c["passed"] for c in checks),
    }


'''

patched = original.replace(ANCHOR_1, VALIDATE_FN + ANCHOR_1, 1)

# ---------------------------------------------------------------------------
# 2) Rama en el dispatch + mensaje de error actualizado
# ---------------------------------------------------------------------------
ANCHOR_2 = '''    elif mode == "stats":
        return _mode_stats(params, tools)
    else:
        raise ValueError(f"Modo desconocido: {mode}. Usar: search | related | stats")'''
count_2 = patched.count(ANCHOR_2)
assert count_2 == 1, f"ancla (dispatch stats/else) aparece {count_2} veces, se esperaba 1"

REPLACEMENT_2 = '''    elif mode == "stats":
        return _mode_stats(params, tools)
    elif mode == "validate":
        return _mode_validate(params, tools)
    else:
        raise ValueError(f"Modo desconocido: {mode}. Usar: search | related | stats | validate")'''

patched = patched.replace(ANCHOR_2, REPLACEMENT_2, 1)

# ---------------------------------------------------------------------------
# 3) Enum del schema
# ---------------------------------------------------------------------------
ANCHOR_3 = '"mode": {"type": "string", "enum": ["search", "related", "stats"]},'
count_3 = patched.count(ANCHOR_3)
assert count_3 == 1, f"ancla (enum schema) aparece {count_3} veces, se esperaba 1"

REPLACEMENT_3 = '"mode": {"type": "string", "enum": ["search", "related", "stats", "validate"]},'
patched = patched.replace(ANCHOR_3, REPLACEMENT_3, 1)

# ---------------------------------------------------------------------------
# Validar sintaxis antes de escribir
# ---------------------------------------------------------------------------
try:
    ast.parse(patched)
except SyntaxError as e:
    print(f"ERROR: el resultado parcheado no compila (ast.parse): {e}", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Backup + escritura
# ---------------------------------------------------------------------------
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = TARGET.with_name(f"{TARGET.name}.bak_{timestamp}")
backup_path.write_text(original, encoding="utf-8")
print(f"backup: {backup_path}")

TARGET.write_text(patched, encoding="utf-8")
print("aplicado OK")

py_compile.compile(str(TARGET), doraise=True)
print("py_compile OK")
