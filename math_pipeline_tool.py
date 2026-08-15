"""
math_pipeline_tool.py

Meta-tool: encadena llamadas a otros compute_* tools del servidor sin volver
a levantar Octave por fuera -- cada tool sigue usando su propio motor
interno, este modulo solo orquesta el orden y pasa datos entre pasos.

Un paso puede referenciar el resultado de un paso anterior via un string
"$stepN.clave.subclave" en cualquier valor de 'params' (resuelto
recursivamente sobre dicts/listas), donde N es el indice 0-based del paso
ya ejecutado. Ejemplo:

    steps = [
        {"tool": "statistics", "params": {"mode": "linear_regression", "preset": "known_linear"}},
        {"tool": "population_dynamics", "params": {"mode": "logistic_growth", "r": "$step0.slope"}},
    ]

Filosofia igual al resto del repo (mismo criterio que socket_qa_engine e
historian_tool): si un paso falla -- tool desconocido, parametro faltante,
referencia invalida, o el tool de destino devuelve su propio {"error":...}
-- el pipeline se DETIENE ahi y reporta el motivo especifico. No adivina
defaults ni sigue corriendo pasos siguientes con datos incompletos.

TOOL_REGISTRY es un subconjunto deliberado: los tools "puros" que reciben
solo tipos JSON-serializables (numeros, listas, dicts, strings) y no
dependen del helper _run_octave definido inline en server.py. Los 4 tools
base (octave_run, octave_eval_expr, octave_run_script, octave_version)
quedan fuera de esta primera version porque estan atados a ese helper --
extension futura si hace falta encadenar codigo Octave crudo como un paso
mas del pipeline.

Validacion (mode='validate'): pipeline real de 2 pasos, no simulado. Paso 0
corre una regresion lineal con verdad conocida (pendiente esperada ~2.0,
preset determinista con ruido gaussiano chico). Paso 1 usa esa pendiente
ESTIMADA (no la esperada) como tasa de crecimiento 'r' de un crecimiento
logistico. La validacion chequea tres cosas independientes: (a) que el
valor referenciado llego EXACTO al paso siguiente -- no una copia
redondeada ni un default silencioso, (b) que la pendiente estimada cae
cerca del valor esperado (confirma que step0 corrio bien), y (c) que el
propio population_dynamics_tool valida su salida contra la solucion
analitica cerrada del crecimiento logistico con ese r encadenado
(confirma que el valor no solo "llego", sino que es matematicamente
utilizable rio abajo).
"""
import re

from lyapunov_tool import compute_lyapunov_exponent
from stiff_ode_tool import integrate_stiff_ode
from bifurcation_tool import compute_bifurcation_diagram
from hilbert_tool import compute_hilbert_transform
from graph_tool import compute_graph_algorithms
from qm_tool import compute_qm_potential_well
from nuclear_decay_tool import compute_nuclear_decay_chain
from fractal_dimension_tool import compute_fractal_dimension
from linear_algebra_tool import compute_linear_algebra
from persistent_homology_tool import compute_persistent_homology
from statistics_tool import compute_statistics
from number_theory_tool import compute_number_theory
from symbolic_tool import compute_symbolic
from optimization_tool import compute_optimization
from pde_tool import compute_pde
from population_dynamics_tool import compute_population_dynamics
from reaction_diffusion_tool import compute_reaction_diffusion
from enzyme_kinetics_tool import compute_enzyme_kinetics
from historian_tool import compute_historian
from braid_group_tool import compute_braid_group
from tritbraid_tool import compute_tritbraid

MATH_PIPELINE_SCHEMA = {
    "name": "compute_math_pipeline",
    "description": (
        "Encadena llamadas a otros compute_* tools del servidor: cada paso "
        "puede referenciar el resultado de un paso anterior via strings "
        "'$stepN.clave.subclave' dentro de sus params. mode='run' ejecuta "
        "'steps' (lista de {tool, params}); mode='validate' corre un "
        "pipeline sintetico de 2 pasos con verdad conocida; "
        "mode='list_tools' devuelve los nombres de tool disponibles para "
        "encadenar (subconjunto de 'tools puros', ver docstring del modulo)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["run", "validate", "list_tools"], "default": "validate"},
            "steps": {
                "type": "array",
                "description": (
                    "Solo si mode='run'. Cada elemento: {'tool': <nombre del "
                    "registro, ver list_tools>, 'params': {...}}. Los "
                    "valores de 'params' aceptan strings '$stepN.clave' "
                    "para referenciar el resultado del paso N (0-based) ya "
                    "ejecutado en este mismo pipeline."
                ),
            },
        },
    },
}

TOOL_REGISTRY = {
    "lyapunov": compute_lyapunov_exponent,
    "stiff_ode": integrate_stiff_ode,
    "bifurcation": compute_bifurcation_diagram,
    "hilbert": compute_hilbert_transform,
    "graph": compute_graph_algorithms,
    "qm_well": compute_qm_potential_well,
    "nuclear_decay": compute_nuclear_decay_chain,
    "fractal_dimension": compute_fractal_dimension,
    "linear_algebra": compute_linear_algebra,
    "persistent_homology": compute_persistent_homology,
    "statistics": compute_statistics,
    "number_theory": compute_number_theory,
    "symbolic": compute_symbolic,
    "optimization": compute_optimization,
    "pde": compute_pde,
    "population_dynamics": compute_population_dynamics,
    "reaction_diffusion": compute_reaction_diffusion,
    "enzyme_kinetics": compute_enzyme_kinetics,
    "historian": compute_historian,
    "braid_group": compute_braid_group,
    "tritbraid": compute_tritbraid,
}

_REF_RE = re.compile(r"^\$step(\d+)\.(.+)$")


def _get_path(obj, path):
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                raise KeyError(
                    f"clave '{part}' no encontrada en el resultado referenciado "
                    f"(claves disponibles: {list(cur.keys())})"
                )
            cur = cur[part]
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                raise KeyError(f"indice '{part}' invalido para lista de largo {len(cur)}")
        else:
            raise KeyError(f"no se puede navegar '{part}' sobre un valor de tipo {type(cur).__name__}")
    return cur


def _resolve(value, results):
    if isinstance(value, str):
        m = _REF_RE.match(value)
        if not m:
            return value
        idx, path = int(m.group(1)), m.group(2)
        if idx >= len(results) or results[idx] is None:
            raise KeyError(f"step{idx} no disponible (no ejecutado todavia o fallo)")
        return _get_path(results[idx], path)
    if isinstance(value, dict):
        return {k: _resolve(v, results) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, results) for v in value]
    return value


def _run_step(step, results):
    tool_name = step.get("tool")
    if tool_name not in TOOL_REGISTRY:
        return {"status": "error", "error": f"tool desconocido: '{tool_name}'. Disponibles: {sorted(TOOL_REGISTRY)}"}
    raw_params = step.get("params") or {}
    try:
        resolved = _resolve(raw_params, results)
    except KeyError as e:
        return {"status": "error", "error": f"referencia invalida en params: {e}"}
    fn = TOOL_REGISTRY[tool_name]
    try:
        out = fn(**resolved)
    except TypeError as e:
        return {"status": "error", "error": f"parametros invalidos para '{tool_name}': {e}"}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    if isinstance(out, dict) and "error" in out:
        return {"status": "error", "error": f"{tool_name} devolvio error interno: {out['error']}"}
    return {"status": "ok", "result": out}


def _run_pipeline(steps):
    results = []
    step_reports = []
    for i, step in enumerate(steps):
        report = _run_step(step, results)
        report["step"] = i
        report["tool"] = step.get("tool")
        step_reports.append(report)
        if report["status"] == "ok":
            results.append(report["result"])
        else:
            results.append(None)
            break  # escalar, no seguir con datos incompletos
    completed = sum(1 for r in step_reports if r["status"] == "ok")
    return {
        "n_steps_requested": len(steps),
        "n_steps_completed": completed,
        "all_completed": completed == len(steps),
        "steps": step_reports,
    }


def _validate():
    steps = [
        {"tool": "statistics", "params": {"mode": "linear_regression", "preset": "known_linear"}},
        {"tool": "population_dynamics", "params": {
            "mode": "logistic_growth", "r": "$step0.slope",
            "K": 100.0, "x0": 10.0, "t_max": 10.0, "n_points": 20,
        }},
    ]
    run = _run_pipeline(steps)
    checks = {"pipeline_completo": run["all_completed"]}
    if run["all_completed"]:
        slope = run["steps"][0]["result"]["slope"]
        r_used = run["steps"][1]["result"]["params"]["r"]
        max_err = run["steps"][1]["result"]["max_error_vs_analytic"]
        checks["referencia_llego_exacta"] = (r_used == slope)
        checks["slope_estimada_cerca_de_2.0"] = abs(slope - 2.0) < 0.05
        # population_dynamics_tool llama a ode45 con tolerancias default de
        # Octave (RelTol~1e-3), no las tolerancias custom que usa stiff_ode_tool;
        # sobre una transicion logistica rapida (r~2, K=100) eso deja un error
        # absoluto tipico ~0.05 en la zona de mayor pendiente. 0.1 es un margen
        # atado a esa tolerancia conocida, no un numero elegido para que pase.
        checks["logistic_growth_valida_contra_analitica"] = max_err < 0.1
    return {
        "mode": "validate",
        "todos_correctos": all(checks.values()),
        "checks": checks,
        "pipeline_detail": run,
    }


def compute_math_pipeline(mode="validate", steps=None):
    if mode == "list_tools":
        return {"tools_disponibles": sorted(TOOL_REGISTRY.keys())}
    if mode == "validate":
        return _validate()
    if mode == "run":
        if not steps:
            return {"error": "mode='run' requiere 'steps' (lista de {tool, params})"}
        return _run_pipeline(steps)
    return {"error": f"mode desconocido: {mode}"}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_math_pipeline("validate"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_math_pipeline("list_tools"), indent=2, ensure_ascii=False))


try:
    from tool_registry import register_tool
    register_tool(
        name="compute_math_pipeline",
        schema=MATH_PIPELINE_SCHEMA,
        handler=lambda args: compute_math_pipeline(**args),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    d = compute_math_pipeline(mode="validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d.get("todos_correctos", False), "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de math_pipeline_tool.py pasaron OK.")
