"""
math_pipeline_builder_tool.py

Orquestador de pipelines para el ecosistema octave-mcp: encadena llamadas
a los tools matematicos ya existentes, permitiendo que el output de un
paso alimente el input de otro via referencias "$save_as.ruta.a.campo".

No reimplementa matematica: es infraestructura pura sobre los tools ya
construidos (auto_differentiation_tool, math_error_analyzer_tool,
math_benchmark_tool, math_interpolation_tool, lyapunov_tool, stiff_ode_tool,
bifurcation_tool, hilbert_tool).
"""

import time

from auto_differentiation_tool import compute_gradient_hessian, compute_jacobian
from lyapunov_tool import compute_lyapunov_exponent
from stiff_ode_tool import integrate_stiff_ode
from bifurcation_tool import compute_bifurcation_diagram
from hilbert_tool import compute_hilbert_transform
from math_error_analyzer_tool import compute_math_error_analysis
from math_benchmark_tool import compute_math_benchmark
from math_interpolation_tool import compute_math_interpolation


REGISTRY = {
    "compute_gradient_hessian": compute_gradient_hessian,
    "compute_jacobian": compute_jacobian,
    "compute_lyapunov_exponent": compute_lyapunov_exponent,
    "integrate_stiff_ode": integrate_stiff_ode,
    "compute_bifurcation_diagram": compute_bifurcation_diagram,
    "compute_hilbert_transform": compute_hilbert_transform,
    "compute_math_error_analysis": compute_math_error_analysis,
    "compute_math_benchmark": compute_math_benchmark,
    "compute_math_interpolation": compute_math_interpolation,
}

# Nombres de tool MCP que difieren del nombre de la funcion Python subyacente
TOOL_NAME_ALIASES = {
    "math_error_analyzer": "compute_math_error_analysis",
    "math_benchmark": "compute_math_benchmark",
    "math_interpolation": "compute_math_interpolation",
}


def _lookup_tool(name: str):
    if name in REGISTRY:
        return REGISTRY[name]
    if name in TOOL_NAME_ALIASES:
        return REGISTRY[TOOL_NAME_ALIASES[name]]
    disponibles = sorted(set(REGISTRY) | set(TOOL_NAME_ALIASES))
    raise ValueError(f"Tool desconocido en el pipeline: '{name}'. Disponibles: {disponibles}")


def _resolve_value(v, context):
    """Resuelve strings '$step_id.campo.subcampo' contra resultados previos.
    Soporta navegacion en dicts (por clave) y listas (por indice numerico)."""
    if isinstance(v, str) and v.startswith("$"):
        path = v[1:].split(".")
        if path[0] not in context:
            raise ValueError(
                f"Referencia '{v}' invalida: el paso '{path[0]}' no existe "
                f"(¿lo definiste con save_as? ¿va despues en la lista?)"
            )
        cur = context[path[0]]
        for key in path[1:]:
            if isinstance(cur, dict):
                if key not in cur:
                    raise ValueError(f"Clave '{key}' no encontrada al resolver '{v}'")
                cur = cur[key]
            elif isinstance(cur, list):
                try:
                    cur = cur[int(key)]
                except (ValueError, IndexError) as e:
                    raise ValueError(f"Indice '{key}' invalido al resolver '{v}': {e}")
            else:
                raise ValueError(f"No se puede navegar '{key}' en '{v}': valor no es dict ni list")
        return cur
    if isinstance(v, dict):
        return {k: _resolve_value(x, context) for k, x in v.items()}
    if isinstance(v, list):
        return [_resolve_value(x, context) for x in v]
    return v


def execute_pipeline(steps: list) -> tuple:
    """Ejecuta los pasos en orden. Cada step: {"tool": str, "args": dict, "save_as": str opcional}.
    Devuelve (context, trace): context mapea save_as -> resultado; trace es la bitacora ordenada."""
    if not steps:
        raise ValueError("El pipeline necesita al menos un paso ('steps' vacio)")

    context = {}
    trace = []

    for i, step in enumerate(steps):
        tool_name = step.get("tool")
        if not tool_name:
            raise ValueError(f"Paso {i}: falta la clave 'tool'")

        raw_args = step.get("args", {})
        save_as = step.get("save_as") or f"step{i}"
        fn = _lookup_tool(tool_name)

        try:
            resolved_args = _resolve_value(raw_args, context)
        except ValueError as e:
            raise ValueError(f"Paso {i} ('{tool_name}'): error resolviendo referencias -> {e}")

        t0 = time.perf_counter()
        try:
            output = fn(**resolved_args)
        except TypeError as e:
            raise ValueError(f"Paso {i} ('{tool_name}'): argumentos invalidos para la funcion -> {e}")
        elapsed = time.perf_counter() - t0

        context[save_as] = output
        trace.append({
            "step": i,
            "tool": tool_name,
            "save_as": save_as,
            "args_resolved": resolved_args,
            "elapsed_seconds": round(elapsed, 6),
        })

    return context, trace


def run_math_pipeline(steps: list = None, mode: str = "validate") -> dict:
    """
    Orquesta una cadena de llamadas a tools de octave-mcp, resolviendo
    referencias entre pasos.

    Args:
        steps: lista de {"tool": str, "args": dict, "save_as": str opcional}.
               En 'args', cualquier string que empiece con '$' se resuelve
               contra resultados de pasos previos, ej:
               "$grad.gradient.x.sympy" toma el campo anidado del paso
               guardado como save_as="grad".
        mode: "run" ejecuta los steps dados.
              "validate" (default) corre un pipeline de demo fijo:
              deriva simbolicamente y despues analiza su error numerico,
              para confirmar que el encadenado funciona sin pedir input.

    Returns:
        dict con mode, n_steps, trace (bitacora con tiempos) y results
        (mapa save_as -> resultado de cada paso).
    """
    if mode not in ("run", "validate"):
        raise ValueError("mode debe ser 'run' o 'validate'")

    if mode == "validate":
        steps = [
            {
                "tool": "compute_gradient_hessian",
                "args": {"expression": "x**2*sin(y) + exp(x*y)", "variables": "x,y", "order": 1},
                "save_as": "grad",
            },
            {
                "tool": "compute_math_error_analysis",
                "args": {
                    "mode": "truncation_roundoff",
                    "function_expr": "sin(x)",
                    "x0": 1.0,
                    "method": "central",
                    "h_min_exp": 1,
                    "h_max_exp": 8,
                },
                "save_as": "err",
            },
        ]
    elif not steps:
        raise ValueError("Debes indicar 'steps' (lista no vacia) cuando mode='run'")

    context, trace = execute_pipeline(steps)

    return {
        "mode": mode,
        "n_steps": len(steps),
        "trace": trace,
        "results": context,
    }


PIPELINE_BUILDER_TOOL_SCHEMA = {
    "name": "run_math_pipeline",
    "description": (
        "Encadena llamadas a los tools matematicos de octave-mcp (diferenciacion "
        "simbolica, Jacobiano, Lyapunov, ODEs stiff, bifurcacion, Hilbert, analisis "
        "de error, benchmark de metodos, interpolacion), pasando el output de un "
        "paso como input del siguiente via referencias '$save_as.campo.subcampo'. "
        "mode='validate' corre una demo fija (derivada -> analisis de error) sin "
        "pedir argumentos; mode='run' ejecuta los 'steps' dados."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["run", "validate"],
                "default": "validate",
                "description": "'validate' corre una demo fija; 'run' ejecuta 'steps'.",
            },
            "steps": {
                "type": "array",
                "description": (
                    "Lista ordenada de pasos. Cada uno: {tool, args, save_as opcional}. "
                    "Requerido si mode='run'."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "tool": {
                            "type": "string",
                            "description": (
                                "Nombre del tool a invocar. Uno de: compute_gradient_hessian, "
                                "compute_jacobian, compute_lyapunov_exponent, integrate_stiff_ode, "
                                "compute_bifurcation_diagram, compute_hilbert_transform, "
                                "math_error_analyzer, math_benchmark, math_interpolation."
                            ),
                        },
                        "args": {
                            "type": "object",
                            "description": (
                                "Argumentos para el tool. Cualquier string que empiece con '$' "
                                "se resuelve contra un resultado previo, ej '$grad.gradient.x.sympy'."
                            ),
                        },
                        "save_as": {
                            "type": "string",
                            "description": "Nombre para referenciar este resultado en pasos siguientes.",
                        },
                    },
                    "required": ["tool", "args"],
                },
            },
        },
        "required": [],
    },
}


if __name__ == "__main__":
    import json

    print("=== mode=validate (demo fija) ===")
    r1 = run_math_pipeline(mode="validate")
    print(json.dumps(r1["trace"], indent=2, ensure_ascii=False))

    print("\n=== mode=run con referencia entre pasos ===")
    steps = [
        {
            "tool": "compute_gradient_hessian",
            "args": {"expression": "r*x*(1 - x/K)", "variables": "x", "order": 1},
            "save_as": "logistic_grad",
        },
        {
            "tool": "compute_math_error_analysis",
            "args": {
                "mode": "truncation_roundoff",
                "function_expr": "x**3 - 2*x",
                "x0": 1.5,
                "method": "both",
                "h_min_exp": 1,
                "h_max_exp": 10,
            },
            "save_as": "err2",
        },
    ]
    r2 = run_math_pipeline(steps=steps, mode="run")
    print(json.dumps(r2["trace"], indent=2, ensure_ascii=False))
    print("\nCampo referenciable de ejemplo (logistic_grad.gradient.x.sympy):")
    print(r2["results"]["logistic_grad"]["gradient"]["x"]["sympy"])
