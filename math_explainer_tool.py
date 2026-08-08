#!/usr/bin/env python3
"""
math_explainer_tool.py
Traduce el resultado JSON de cualquier tool del ecosistema octave-mcp a una
explicacion en espanol, paso a paso, en lenguaje natural. Pensado para cerrar
un run_math_pipeline con un paso final "explicame esto" en vez de dejar JSON
crudo, o para usarse solo sobre el resultado de un tool_call individual.

No llama a ninguna API externa: usa templates deterministicos por tool,
mas un fallback generico para tools no reconocidos.

Corre standalone: python3 math_explainer_tool.py
"""
import json


MATH_EXPLAINER_TOOL_SCHEMA = {
    "name": "math_explainer",
    "description": (
        "Genera una explicacion en espanol, paso a paso, del resultado JSON "
        "de otro tool matematico (compute_gradient_hessian, math_error_analyzer, "
        "compute_lyapunov_exponent, run_math_pipeline, etc.)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "source_tool": {
                "type": "string",
                "description": "Nombre del tool que genero 'result' (ej. 'compute_gradient_hessian').",
            },
            "result": {
                "type": "object",
                "description": "El JSON de resultado devuelto por ese tool.",
            },
            "level": {
                "type": "string",
                "enum": ["basico", "tecnico"],
                "default": "tecnico",
                "description": "'basico' = explicacion accesible paso a paso; 'tecnico' = con terminologia formal.",
            },
        },
        "required": ["source_tool", "result"],
    },
}


def _fmt(v, nd=4):
    if isinstance(v, float):
        return f"{v:.{nd}g}"
    return str(v)


def _explain_gradient_hessian(result, level):
    lines = []
    grad = result.get("gradient", {})
    lines.append(f"Se calculo el gradiente respecto a las variables: {', '.join(grad.keys())}.")
    for var, info in grad.items():
        expr = info.get("sympy", info) if isinstance(info, dict) else info
        lines.append(f"  - d/d{var} = {expr}")
    hess = result.get("hessian")
    if hess:
        lines.append("Tambien se calculo la matriz Hessiana (segundas derivadas parciales),")
        lines.append("que describe la curvatura de la funcion en cada direccion.")
        if level == "basico":
            lines.append("Un Hessiano permite saber si un punto critico es minimo, maximo o silla.")
    return "\n".join(lines)


def _explain_jacobian(result, level):
    lines = ["Se calculo la matriz Jacobiana del sistema de funciones dado."]
    if "determinant" in result and result["determinant"] is not None:
        lines.append(f"El determinante del Jacobiano es: {result['determinant']}.")
        if level == "basico":
            lines.append(
                "Si el determinante es distinto de cero en un punto, el sistema es "
                "localmente invertible ahi (teorema de la funcion inversa)."
            )
    return "\n".join(lines)


def _explain_lyapunov(result, level):
    lam = result.get("lyapunov_exponent") or result.get("lambda1")
    lines = [f"Se estimo el exponente de Lyapunov maximo: λ1 = {_fmt(lam)}."]
    if lam is not None:
        if lam > 0:
            lines.append("Como λ1 > 0, el sistema exhibe sensibilidad a condiciones iniciales: es caotico.")
        else:
            lines.append("Como λ1 <= 0, las trayectorias cercanas no divergen exponencialmente: no hay caos.")
    if level == "basico":
        lines.append(
            "En terminos simples: dos puntos de partida casi identicos terminan separandose "
            "cada vez mas rapido cuanto mayor es λ1, lo que hace impredecible el sistema a largo plazo."
        )
    return "\n".join(lines)


def _explain_stiff_ode(result, level):
    lines = [f"Se integro el sistema de ecuaciones diferenciales con el solver '{result.get('solver', '?')}'."]
    if "t" in result:
        lines.append(f"Se generaron {len(result['t'])} puntos de solucion en el intervalo temporal dado.")
    if level == "basico":
        lines.append(
            "Un sistema 'stiff' (rigido) es uno donde algunas variables cambian mucho mas rapido "
            "que otras; los solvers explicitos comunes (como RK4) fallarian o serian extremadamente lentos ahi."
        )
    return "\n".join(lines)


def _explain_bifurcation(result, level):
    lines = ["Se genero un diagrama de bifurcacion barriendo el parametro r del mapa iterativo."]
    if "stability" in result:
        lines.append("Se incluyo ademas un analisis de estabilidad puntual via la derivada del mapa.")
    if level == "basico":
        lines.append(
            "Cada valor de r produce uno o mas puntos de 'atractor' (adonde termina yendo la orbita "
            "tras el transitorio). Cuando esos puntos se duplican al variar r, es una bifurcacion; "
            "muchas duplicaciones seguidas suelen llevar al caos."
        )
    return "\n".join(lines)


def _explain_hilbert(result, level):
    lines = ["Se calculo la transformada de Hilbert de la senal, obteniendo la senal analitica."]
    lines.append("De ahi se extrajeron: envolvente (amplitud instantanea), fase instantanea y frecuencia instantanea.")
    if level == "basico":
        lines.append(
            "Esto sirve para senales no estacionarias, donde la amplitud o la frecuencia cambian con "
            "el tiempo (ej. una senal modulada): la transformada de Hilbert separa 'que tan fuerte' "
            "de 'que tan rapido oscila' en cada instante."
        )
    return "\n".join(lines)


def _explain_error_analyzer(result, level):
    mode = result.get("mode", "?")
    lines = [f"Analisis de error, modo '{mode}'."]
    if mode == "truncation_roundoff":
        lines.append(
            "Se comparo el error de truncamiento (por aproximar la derivada con un paso finito h) "
            "contra el error de redondeo (por la precision limitada de punto flotante), barriendo h."
        )
        if level == "basico":
            lines.append(
                "Hay un h optimo: si h es muy grande, el metodo es impreciso (error de truncamiento); "
                "si h es muy chico, la resta de numeros casi iguales amplifica errores de redondeo."
            )
    elif mode == "condition_number":
        cond = result.get("condition_number")
        lines.append(f"Numero de condicion de la matriz: {_fmt(cond)}.")
        if level == "basico":
            lines.append(
                "Un numero de condicion alto significa que pequenos errores en los datos de entrada "
                "(o en el redondeo) pueden amplificarse mucho en la solucion del sistema lineal."
            )
    return "\n".join(lines)


def _explain_benchmark(result, level):
    mode = result.get("mode", "?")
    lines = [f"Benchmark de metodos numericos, modo '{mode}'."]
    if level == "basico":
        lines.append(
            "Se compararon distintos metodos contra una solucion analitica conocida, para medir "
            "que tan rapido converge cada uno al reducir el paso (h) o aumentar las subdivisiones (n)."
        )
    return "\n".join(lines)


def _explain_interpolation(result, level):
    lines = ["Se comparo interpolacion contra la funcion exacta."]
    if result.get("runge_phenomenon_detected"):
        lines.append(
            "Se detecto el fenomeno de Runge: con nodos equiespaciados, el error crece cerca de los "
            "bordes del intervalo al aumentar el grado del polinomio."
        )
        if level == "basico":
            lines.append(
                "La solucion tipica es usar nodos de Chebyshev (mas concentrados en los bordes) "
                "en vez de nodos equiespaciados."
            )
    return "\n".join(lines)


def _explain_pipeline(result, level):
    trace = result.get("trace", [])
    lines = [f"Se ejecuto un pipeline de {result.get('n_steps', len(trace))} pasos encadenados:"]
    for step in trace:
        lines.append(f"  {step.get('step')}. {step.get('tool')} -> guardado como '{step.get('save_as')}'")
    if level == "basico":
        lines.append("Cada paso pudo usar resultados de pasos anteriores via referencias '$nombre.campo'.")
    return "\n".join(lines)


def _explain_visualization(result, level):
    mode = result.get("mode", "?")
    lines = [f"Se genero una visualizacion (PNG), modo '{mode}'."]
    if mode == "function_plot":
        lines.append(f"Rango de valores de la funcion en el dominio: [{_fmt(result.get('y_min'))}, {_fmt(result.get('y_max'))}].")
    elif mode == "phase_portrait":
        lines.append(f"Sistema: {result.get('system')}, con {result.get('n_points')} puntos de trayectoria.")
    elif mode == "bifurcation_render":
        lines.append(f"Se graficaron {result.get('n_points_total')} puntos sobre {result.get('n_r_values')} valores de r.")
    elif mode == "vector_field":
        lines.append(f"Magnitud maxima del campo: {_fmt(result.get('max_magnitude'))}.")
    return "\n".join(lines)


_EXPLAINERS = {
    "compute_gradient_hessian": _explain_gradient_hessian,
    "compute_jacobian": _explain_jacobian,
    "compute_lyapunov_exponent": _explain_lyapunov,
    "integrate_stiff_ode": _explain_stiff_ode,
    "compute_bifurcation_diagram": _explain_bifurcation,
    "compute_hilbert_transform": _explain_hilbert,
    "math_error_analyzer": _explain_error_analyzer,
    "math_benchmark": _explain_benchmark,
    "math_interpolation": _explain_interpolation,
    "run_math_pipeline": _explain_pipeline,
    "math_visualization": _explain_visualization,
}


def _explain_generic(result, level):
    keys = list(result.keys())[:8]
    return (
        "No hay un template especifico para este tool todavia, asi que va una "
        f"descripcion generica del resultado. Campos principales: {', '.join(keys)}."
    )


def interpret_and_explain(source_tool, result, level="tecnico"):
    if isinstance(result, str):
        result = json.loads(result)

    fn = _EXPLAINERS.get(source_tool, _explain_generic)
    explanation = fn(result, level)

    return {
        "source_tool": source_tool,
        "level": level,
        "explanation": explanation,
        "known_tool": source_tool in _EXPLAINERS,
    }


if __name__ == "__main__":
    print("=== gradient_hessian (tecnico) ===")
    r1 = interpret_and_explain(
        "compute_gradient_hessian",
        {"gradient": {"x": {"sympy": "2*x*sin(y)"}, "y": {"sympy": "x**2*cos(y)"}}, "hessian": [[1, 0], [0, 1]]},
        level="tecnico",
    )
    print(r1["explanation"])

    print("\n=== lyapunov (basico) ===")
    r2 = interpret_and_explain("compute_lyapunov_exponent", {"lyapunov_exponent": 0.9}, level="basico")
    print(r2["explanation"])

    print("\n=== run_math_pipeline (basico) ===")
    r3 = interpret_and_explain(
        "run_math_pipeline",
        {"n_steps": 2, "trace": [{"step": 0, "tool": "compute_gradient_hessian", "save_as": "grad"},
                                  {"step": 1, "tool": "math_error_analyzer", "save_as": "err"}]},
        level="basico",
    )
    print(r3["explanation"])

    print("\n=== tool desconocido (fallback generico) ===")
    r4 = interpret_and_explain("un_tool_que_no_existe_todavia", {"foo": 1, "bar": 2})
    print(r4["explanation"], "| known_tool:", r4["known_tool"])

    print("\nOK - todos los casos corrieron sin excepciones.")
