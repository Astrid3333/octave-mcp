"""
math_interpreter_tool.py

Interprete de consultas en lenguaje natural (español, frases canonicas) para
el ecosistema octave-mcp: traduce texto a steps de run_math_pipeline.

IMPORTANTE: esto es un parser basado en reglas/regex, no NLU real. Sirve
para invocar el pipeline desde un contexto SIN un LLM en el medio (scripts,
cron jobs, otra app). Cuando hay un LLM en el loop (ej. Claude en el chat),
ese LLM ya hace esta traduccion mejor que cualquier regex.

Reutiliza execute_pipeline de math_pipeline_builder_tool para el modo
auto_run=True.
"""

import re

from math_pipeline_builder_tool import execute_pipeline, REGISTRY, TOOL_NAME_ALIASES


def _split_clauses(text: str) -> list:
    """Separa multiples pedidos en un mismo texto. Prioriza conectores
    explicitos; como fallback, separa por ' y ' solo si le sigue un verbo
    de accion conocido (para no romper 'x,y' o 'x y z' como variables)."""
    explicit = re.split(r"\s*(?:;|\by luego\b|\by despu[eé]s\b|\bluego\b|\bdespu[eé]s\b)\s*", text, flags=re.IGNORECASE)
    clauses = []
    verb_split = re.compile(
        r"\s+y\s+(?=(?:deriv|calcul|analiz|compar|verific|interpol|integr|obten|encontr|halla)\w*)",
        re.IGNORECASE,
    )
    for chunk in explicit:
        clauses.extend(verb_split.split(chunk))
    return [c.strip() for c in clauses if c.strip()]


def _clean_vars(raw: str) -> str:
    return re.sub(r"\s+", "", raw.strip().rstrip("."))


def _p_gradient_hessian(m):
    order = 2 if re.search(r"hessian", m.group(0), re.IGNORECASE) else 1
    return "compute_gradient_hessian", {
        "expression": m.group("expr").strip(),
        "variables": _clean_vars(m.group("vars")),
        "order": order,
    }


def _p_jacobian(m):
    return "compute_jacobian", {
        "expressions": m.group("exprs").strip(),
        "variables": _clean_vars(m.group("vars")),
    }


def _p_error_truncation(m):
    return "math_error_analyzer", {
        "mode": "truncation_roundoff",
        "function_expr": m.group("expr").strip(),
        "x0": float(m.group("x0")),
        "method": "central",
        "h_min_exp": 1,
        "h_max_exp": 8,
    }


def _p_benchmark_quadrature(m):
    return "math_benchmark", {
        "mode": "quadrature",
        "function_expr": m.group("expr").strip(),
        "a": float(m.group("a")),
        "b": float(m.group("b")),
    }


def _p_benchmark_root_finding(m):
    return "math_benchmark", {
        "mode": "root_finding",
        "function_expr": m.group("expr").strip(),
        "bracket": [float(m.group("a")), float(m.group("b"))],
    }


def _p_benchmark_ode(m):
    return "math_benchmark", {
        "mode": "ode_methods",
        "problem": m.group("problem").strip(),
    }


def _p_interpolation(m):
    return "math_interpolation", {
        "mode": "lagrange",
        "preset": m.group("preset").strip(),
    }


def _p_lyapunov(m):
    return "compute_lyapunov_exponent", {"system": m.group("system").strip()}


def _p_bifurcation(m):
    return "compute_bifurcation_diagram", {"map_name": m.group("map_name").strip()}


def _p_stiff_ode(m):
    return "integrate_stiff_ode", {"system": m.group("system").strip()}


def _p_hilbert(m):
    return "compute_hilbert_transform", {}


# Orden importa: mas especifico primero. Cada entrada: (regex, builder)
PATTERNS = [
    (
        re.compile(
            r"(?:gradiente(?:\s+y\s+hessiano)?|hessiano)\s+de\s+(?P<expr>.+?)\s+respecto\s+a\s+(?P<vars>[\w,\s]+?)$",
            re.IGNORECASE,
        ),
        _p_gradient_hessian,
    ),
    (
        re.compile(
            r"jacobiano\s+de\s+(?P<exprs>.+?)\s+respecto\s+a\s+(?P<vars>[\w,\s]+?)$",
            re.IGNORECASE,
        ),
        _p_jacobian,
    ),
    (
        re.compile(
            r"error\s+(?:de\s+)?truncamiento\s+de\s+(?P<expr>.+?)\s+en\s+x0\s*=?\s*(?P<x0>-?\d+(?:\.\d+)?)",
            re.IGNORECASE,
        ),
        _p_error_truncation,
    ),
    (
        re.compile(
            r"compar[ae]r?\s+m[eé]todos\s+de\s+(?:cuadratura|integraci[oó]n)\s+(?:para|de)\s+(?P<expr>.+?)\s+entre\s+(?P<a>-?\d+(?:\.\d+)?)\s+y\s+(?P<b>-?\d+(?:\.\d+)?)",
            re.IGNORECASE,
        ),
        _p_benchmark_quadrature,
    ),
    (
        re.compile(
            r"compar[ae]r?\s+m[eé]todos\s+de\s+(?:b[uú]squeda\s+de\s+)?ra[ií]ces\s+(?:para|de)\s+(?P<expr>.+?)\s+en\s*\[\s*(?P<a>-?\d+(?:\.\d+)?)\s*,\s*(?P<b>-?\d+(?:\.\d+)?)\s*\]",
            re.IGNORECASE,
        ),
        _p_benchmark_root_finding,
    ),
    (
        re.compile(
            r"compar[ae]r?\s+m[eé]todos\s+(?:num[eé]ricos\s+)?(?:para|de)\s+(?:edo|ode)\s+(?P<problem>\w+)",
            re.IGNORECASE,
        ),
        _p_benchmark_ode,
    ),
    (
        re.compile(
            r"interpolaci[oó]n\s+(?:lagrange\s+)?(?:del\s+preset\s+)?(?P<preset>runge|smooth_sine|exponential|abs_kink)",
            re.IGNORECASE,
        ),
        _p_interpolation,
    ),
    (
        re.compile(
            r"lyapunov\s+(?:de|para)\s+(?:el\s+sistema\s+)?(?P<system>\w+)",
            re.IGNORECASE,
        ),
        _p_lyapunov,
    ),
    (
        re.compile(
            r"bifurcaci[oó]n\s+(?:de|para)\s+(?:el\s+mapa\s+)?(?P<map_name>\w+)",
            re.IGNORECASE,
        ),
        _p_bifurcation,
    ),
    (
        re.compile(
            r"(?:sistema\s+)?(?:r[ií]gido|stiff)\s+(?P<system>\w+)",
            re.IGNORECASE,
        ),
        _p_stiff_ode,
    ),
    (
        re.compile(r"transformada\s+de\s+hilbert", re.IGNORECASE),
        _p_hilbert,
    ),
]


def _parse_clause(clause: str):
    for regex, builder in PATTERNS:
        m = regex.search(clause)
        if m:
            tool, args = builder(m)
            return {"clause": clause, "tool": tool, "args": args}
    return None


def interpret_math_query(query: str, auto_run: bool = False) -> dict:
    """
    Traduce una consulta en español (frases canonicas) a steps de
    run_math_pipeline. NO es NLU general: matchea contra un set fijo
    de patrones regex. Pensado para invocar el ecosistema sin un LLM
    en el medio.

    Args:
        query: texto con uno o mas pedidos, ej:
               "gradiente y hessiano de x**2*sin(y) + exp(x*y) respecto a x,y
                y luego error de truncamiento de sin(x) en x0=1"
        auto_run: si True, ademas de armar los steps los ejecuta
                  (via execute_pipeline) y devuelve resultados.

    Returns:
        dict con: query, clauses (texto separado), steps (matcheados,
        listos para run_math_pipeline(mode='run', steps=steps)),
        unmatched (clausulas que no matchearon ningun patron), y si
        auto_run=True: results/trace de la ejecucion.
    """
    clauses = _split_clauses(query)
    if not clauses:
        raise ValueError("La consulta esta vacia o no se pudo separar en clausulas.")

    steps = []
    unmatched = []

    for i, clause in enumerate(clauses):
        parsed = _parse_clause(clause)
        if parsed is None:
            unmatched.append(clause)
            continue
        steps.append({
            "tool": parsed["tool"],
            "args": parsed["args"],
            "save_as": f"step{len(steps)}",
        })

    result = {
        "query": query,
        "clauses": clauses,
        "steps": steps,
        "unmatched": unmatched,
    }

    if unmatched:
        result["warning"] = (
            f"{len(unmatched)} clausula(s) no matchearon ningun patron conocido "
            f"y fueron omitidas. Revisa 'unmatched' y arma esos steps a mano "
            f"para run_math_pipeline si los necesitas."
        )

    if auto_run:
        if not steps:
            raise ValueError("Ninguna clausula matcheo un patron; no hay nada que ejecutar.")
        context, trace = execute_pipeline(steps)
        result["results"] = context
        result["trace"] = trace

    return result


def validate(params=None):
    """Checks anclados a frases canonicas fijas -> tool/args exactos
    esperados del parser regex (no solo 'no crashea')."""
    checks = []

    # --- gradiente: tool correcto, variables limpias, order=1 (sin 'hessiano') ---
    r1 = interpret_math_query("gradiente de x**2+y respecto a x,y")
    step1 = r1["steps"][0] if r1["steps"] else {}
    checks.append({
        "name": "gradiente_parsea_tool_variables_order1",
        "tool": step1.get("tool"),
        "args": step1.get("args"),
        "passed": bool(step1.get("tool") == "compute_gradient_hessian"
                        and step1.get("args", {}).get("variables") == "x,y"
                        and step1.get("args", {}).get("order") == 1),
    })

    # --- hessiano: mismo patron, pero debe detectar 'hessiano' -> order=2 ---
    r2 = interpret_math_query("hessiano de x**2+y respecto a x,y")
    step2 = r2["steps"][0] if r2["steps"] else {}
    checks.append({
        "name": "hessiano_detecta_palabra_clave_order2",
        "tool": step2.get("tool"),
        "order": step2.get("args", {}).get("order"),
        "passed": bool(step2.get("tool") == "compute_gradient_hessian"
                        and step2.get("args", {}).get("order") == 2),
    })

    # --- jacobiano: expressions y variables extraidos correctamente ---
    r3 = interpret_math_query("jacobiano de x+y,x-y respecto a x,y")
    step3 = r3["steps"][0] if r3["steps"] else {}
    checks.append({
        "name": "jacobiano_parsea_expressions_y_variables",
        "tool": step3.get("tool"),
        "args": step3.get("args"),
        "passed": bool(step3.get("tool") == "compute_jacobian"
                        and step3.get("args", {}).get("expressions") == "x+y,x-y"
                        and step3.get("args", {}).get("variables") == "x,y"),
    })

    # --- error de truncamiento: x0 como float, mode correcto ---
    r4 = interpret_math_query("error de truncamiento de sin(x) en x0=1.5")
    step4 = r4["steps"][0] if r4["steps"] else {}
    x0_val = step4.get("args", {}).get("x0")
    checks.append({
        "name": "error_truncamiento_x0_parseado_como_float",
        "tool": step4.get("tool"),
        "x0": x0_val,
        "passed": bool(step4.get("tool") == "math_error_analyzer"
                        and step4.get("args", {}).get("mode") == "truncation_roundoff"
                        and isinstance(x0_val, float)
                        and abs(x0_val - 1.5) < 1e-9),
    })

    # --- separacion de clausulas: '; y luego' debe partir en 2 ---
    r5 = interpret_math_query(
        "gradiente de x**2 respecto a x; y luego "
        "error de truncamiento de cos(x) en x0=0"
    )
    checks.append({
        "name": "separacion_clausulas_conector_y_luego",
        "n_clauses": len(r5["clauses"]),
        "n_steps": len(r5["steps"]),
        "passed": bool(len(r5["clauses"]) == 2 and len(r5["steps"]) == 2),
    })

    # --- clausula sin match cae en 'unmatched', no crashea ni inventa tool ---
    r6 = interpret_math_query("esto no es una consulta matematica reconocible")
    checks.append({
        "name": "clausula_sin_match_cae_en_unmatched",
        "unmatched": r6.get("unmatched"),
        "n_steps": len(r6.get("steps", [])),
        "passed": bool(len(r6.get("unmatched", [])) == 1 and len(r6.get("steps", [])) == 0),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


MATH_INTERPRETER_TOOL_SCHEMA = {
    "name": "math_interpreter",
    "description": (
        "Traduce consultas en espanol con frases canonicas (ej: 'gradiente y "
        "hessiano de x**2*sin(y) respecto a x,y', 'error de truncamiento de "
        "sin(x) en x0=1') a steps de run_math_pipeline, via matching de "
        "patrones regex (NO es NLU general). Util para invocar el ecosistema "
        "octave-mcp sin un LLM en el medio. auto_run=True ademas ejecuta el "
        "pipeline resultante."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["validate"],
                "description": "Opcional. 'validate' corre la bateria de autochequeo en vez de interpretar una query.",
            },
            "query": {
                "type": "string",
                "description": "Consulta en espanol, una o mas peticiones separadas por ';', 'y luego', o 'y' + verbo.",
            },
            "auto_run": {
                "type": "boolean",
                "default": False,
                "description": "Si True, ademas de armar los steps los ejecuta y devuelve resultados.",
            },
        },
        "required": ["query"],
    },
}


if __name__ == "__main__":
    import json

    print("=== Consulta multi-clausula (solo parseo) ===")
    q = (
        "gradiente y hessiano de x**2*sin(y) + exp(x*y) respecto a x,y "
        "y luego error de truncamiento de sin(x) en x0=1"
    )
    r1 = interpret_math_query(q, auto_run=False)
    print(json.dumps({"steps": r1["steps"], "unmatched": r1["unmatched"]}, indent=2, ensure_ascii=False))

    print("\n=== Misma consulta con auto_run=True ===")
    r2 = interpret_math_query(q, auto_run=True)
    print("n_steps:", len(r2["steps"]), "| trace tools:", [s["tool"] for s in r2["trace"]])

    print("\n=== Clausula no reconocida (debe caer en unmatched) ===")
    r3 = interpret_math_query("hace algo raro que no matchea ningun patron")
    print(json.dumps(r3["unmatched"], indent=2, ensure_ascii=False))

    print("\n=== Benchmark de cuadratura via lenguaje natural ===")
    r4 = interpret_math_query("comparar metodos de cuadratura para sin(x) entre 0 y 3.1416")
    print(json.dumps(r4["steps"], indent=2, ensure_ascii=False))

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

def _math_interpreter_handler(args):
    if args.get("mode") == "validate":
        return validate(args)
    args = {k: v for k, v in args.items() if k != "mode"}
    return interpret_math_query(**args)


register_tool("math_interpreter", MATH_INTERPRETER_TOOL_SCHEMA, _math_interpreter_handler)
