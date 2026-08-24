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
        "required": ["source_tool"],
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


def _explain_disaster_simulation(result, level):
    mode = result.get("mode", "?")
    lines = []

    if mode == "monte_carlo_losses":
        n = result.get("n_years_simulated")
        lines.append(f"Simulacion Monte Carlo de perdidas anuales (modelo Poisson-LogNormal, {n} anos simulados).")
        lines.append(f"  - Perdida anual promedio: {_fmt(result.get('mean_annual_loss'))} (desvio: {_fmt(result.get('std_annual_loss'))}, mediana: {_fmt(result.get('median_annual_loss'))}).")
        lines.append(f"  - Perdida maxima simulada: {_fmt(result.get('max_simulated_loss'))}.")
        lines.append(f"  - Probabilidad de un ano sin perdidas: {_fmt(result.get('probability_zero_loss_year'))}.")
        var_cvar = result.get("var_cvar_by_percentile", {})
        for pct, vc in var_cvar.items():
            lines.append(f"  - {pct}: VaR={_fmt(vc.get('VaR'))}, CVaR={_fmt(vc.get('CVaR'))}.")
        if level == "basico":
            lines.append("VaR es la perdida que no se supera con esa probabilidad; CVaR es el promedio de las perdidas cuando SI se supera el VaR (la cola mala).")

    elif mode == "return_period_loss":
        n = result.get("n_years_sample")
        lines.append(f"Curva de perdida por periodo de retorno, estimada sobre {n} anos de muestra (estimador Weibull empirico).")
        for pt in result.get("return_period_curve", []):
            lines.append(f"  - Periodo de retorno {pt.get('return_period_years')} anos: perdida estimada {_fmt(pt.get('loss'))}.")
        if level == "basico":
            lines.append("Un 'periodo de retorno de N anos' significa que, en promedio, una perdida de esa magnitud o mayor ocurre una vez cada N anos -- no que vaya a pasar exactamente cada N anos.")

    elif mode == "exceedance_curve":
        n = result.get("n_years_sample")
        lines.append(f"Curva de excedencia de perdidas, estimada sobre {n} anos de muestra.")
        for pt in result.get("exceedance_curve", []):
            rp = pt.get("implied_return_period_years")
            rp_txt = f"{_fmt(rp)} anos" if rp is not None else "no estimable (probabilidad 0 en la muestra)"
            lines.append(f"  - Umbral {_fmt(pt.get('loss_threshold'))}: probabilidad anual de excedencia {_fmt(pt.get('annual_exceedance_probability'))} (periodo de retorno implicito: {rp_txt}).")

    else:
        lines.append(f"Resultado de disaster_simulation_tool en modo '{mode}' (sin template narrativo especifico para este modo todavia).")
        keys = [k for k in result.keys() if k not in ("mode", "confidence_flag", "note", "seed")][:8]
        lines.append(f"Campos principales: {', '.join(keys)}.")

    return "\n".join(lines)


def _explain_critical_infrastructure(result, level):
    lines = []

    if "redundancy_score" in result and "critical_edges" in result:
        lines.append(f"Analisis de redundancia N-1 sobre la red: {result.get('total_edges')} enlaces totales.")
        lines.append(f"  - Red base conectada: {'si' if result.get('base_graph_connected') else 'no'}.")
        lines.append(f"  - Redundancy score: {_fmt(result.get('redundancy_score'))} (1.0 = ningun enlace es punto unico de falla, 0.0 = todos lo son).")
        n_crit = result.get("n_critical_edges", 0)
        if n_crit:
            edges_txt = ", ".join(f"{e.get('from')}-{e.get('to')}" for e in result.get("critical_edges", [])[:6])
            lines.append(f"  - {n_crit} enlace(s) critico(s) (single point of failure): {edges_txt}.")
        else:
            lines.append("  - Ningun enlace critico: la red tolera la perdida de cualquier enlace individual sin desconectarse.")

    elif "final_failed_count" in result and "history" in result:
        lines.append(f"Simulacion de falla en cascada: {result.get('iterations_run')} iteracion(es), {'convergio' if result.get('converged') else 'NO convergio dentro del limite de iteraciones'}.")
        lines.append(f"  - Carga total inicial: {_fmt(result.get('initial_total_load'))}.")
        lines.append(f"  - Nodos fallados al final: {result.get('final_failed_count')} ({', '.join(result.get('final_failed_nodes', [])[:8])}).")
        if level == "basico":
            lines.append("Un nodo falla cuando su carga supera su capacidad; el excedente se redistribuye a los vecinos activos proporcional al headroom disponible de cada uno, y eso puede encadenar mas fallas.")

    elif "redistribution" in result and "failed_node" in result:
        lines.append(f"Redistribucion de carga tras la falla del nodo '{result.get('failed_node')}': {_fmt(result.get('excess_redistributed'))} de excedente repartido.")
        overloaded = result.get("newly_overloaded", [])
        for nid, info in result.get("redistribution", {}).items():
            flag = " (SUPERA CAPACIDAD)" if info.get("exceeds_capacity") else ""
            lines.append(f"  - {nid}: recibio {_fmt(info.get('share_received'))}, carga nueva {_fmt(info.get('new_load'))}/{_fmt(info.get('capacity'))}{flag}.")
        if overloaded:
            lines.append(f"  - Atencion: {len(overloaded)} vecino(s) quedaron sobrecargados por esta redistribucion, riesgo de cascada secundaria.")

    elif "betweenness" in result and "ranked_critical_nodes" in result:
        lines.append(f"Identificacion de nodos criticos via betweenness centrality (algoritmo de Brandes).")
        top = result.get("ranked_critical_nodes", [])[:5]
        for entry in top:
            lines.append(f"  - {entry.get('node')}: score={_fmt(entry.get('score'))}")
        mc = result.get("most_critical_node")
        if mc is not None:
            lines.append(f"  - Nodo mas critico estructuralmente: {mc}.")
        if level == "basico":
            lines.append("Betweenness alto = el nodo aparece en muchos de los caminos mas cortos entre otros pares de nodos; si falla, desconecta o alarga esas rutas.")

    else:
        lines.append("Resultado de critical_infrastructure_tool (sin template narrativo especifico para este modo todavia).")
        keys = list(result.keys())[:8]
        lines.append(f"Campos principales: {', '.join(keys)}.")

    return "\n".join(lines)


def _explain_urban_planning(result, level):
    lines = []

    if "shannon_entropy_normalized" in result:
        lines.append(f"Indice de mezcla de uso de suelo sobre {result.get('n_categories')} categoria(s): entropia normalizada = {_fmt(result.get('shannon_entropy_normalized'))}.")
        for cat, prop in result.get("proportions", {}).items():
            lines.append(f"  - {cat}: {_fmt(prop)} del area total.")
        if level == "basico":
            lines.append("1.0 = mezcla perfectamente equilibrada entre categorias, 0.0 = monocultivo (una sola categoria domina).")

    elif "accessibility_index" in result:
        lines.append(f"Indice de accesibilidad a servicio (umbral {_fmt(result.get('threshold_km'))} km): {_fmt(result.get('accessibility_index'))}.")
        lines.append(f"  - Poblacion cubierta: {result.get('covered_population')} de {result.get('total_population')} total.")
        n_under = result.get("n_underserved_zones", 0)
        if n_under:
            lines.append(f"  - {n_under} zona(s) sin cobertura, con {result.get('underserved_population')} habitantes fuera del umbral.")

    elif "density_per_km2" in result:
        lines.append(f"Densidad poblacional: {_fmt(result.get('density_per_km2'))} hab/km2 ({_fmt(result.get('population'))} hab en {_fmt(result.get('area_km2'))} km2).")
        if "capacity_per_km2" in result:
            flag = " -- SUPERA la capacidad de diseno" if result.get("over_capacity") else " -- dentro de la capacidad de diseno"
            lines.append(f"  - Ratio de utilizacion vs capacidad ({_fmt(result.get('capacity_per_km2'))} hab/km2): {_fmt(result.get('utilization_ratio'))}{flag}.")

    elif "projection" in result:
        lines.append(f"Proyeccion de demanda de infraestructura: poblacion final {_fmt(result.get('final_population'))}, demanda final {_fmt(result.get('final_demand'))}.")
        if "year_capacity_exceeded" in result:
            ey = result.get("year_capacity_exceeded")
            if ey is not None:
                lines.append(f"  - La capacidad instalada ({_fmt(result.get('current_capacity'))}) se supera en el ano {ey} de la proyeccion.")
            else:
                lines.append(f"  - La capacidad instalada ({_fmt(result.get('current_capacity'))}) no se supera dentro del horizonte proyectado.")
        if level == "basico":
            lines.append("El crecimiento poblacional usado es geometrico simple; tratar la proyeccion como escenario, no como pronostico.")

    else:
        lines.append("Resultado de urban_planning_tool (sin template narrativo especifico para este modo todavia).")
        keys = list(result.keys())[:8]
        lines.append(f"Campos principales: {', '.join(keys)}.")

    return "\n".join(lines)


def _explain_enzyme_kinetics(result, level):
    mode = result.get("mode", "?")
    lines = []

    if mode == "full_kinetics":
        p = result.get("params", {})
        lines.append(f"Cinetica enzimatica completa E+S<->ES->E+P (integracion ODE, no aproximacion): k1={p.get('k1')}, km1={p.get('km1')}, k2={p.get('k2')}, E0={p.get('E0')}, S0={p.get('S0')}.")
        lines.append(f"  - Km derivado: {_fmt(result.get('Km_derivado'))}, Vmax derivado: {_fmt(result.get('Vmax_derivado'))}.")
        lines.append(f"  - Al final de la simulacion: S={_fmt(result.get('S_final'))}, P={_fmt(result.get('P_final'))}.")
        if level == "basico":
            lines.append("Esta es la trayectoria 'real' del sistema completo (sin aproximaciones), util como referencia para validar la aproximacion de Michaelis-Menten.")

    elif mode == "michaelis_menten":
        lines.append(f"Aproximacion de Michaelis-Menten: Km={_fmt(result.get('Km'))}, Vmax={_fmt(result.get('Vmax'))}.")
        lines.append(f"  - Formula: {result.get('formula')}.")
        sample = result.get("velocidad_sample", [])
        if sample:
            lines.append(f"  - Velocidad de reaccion a lo largo del muestreo: de {_fmt(sample[0])} a {_fmt(sample[-1])}.")

    elif mode == "compare":
        lines.append(f"Comparacion cinetica completa vs aproximacion Michaelis-Menten: Km={_fmt(result.get('Km'))}, Vmax={_fmt(result.get('Vmax'))}.")
        valida = result.get("aproximacion_valida")
        err = result.get("error_relativo_promedio_MM_vs_completo")
        lines.append(f"  - QSSA (E0<<S0): {'se cumple' if result.get('condicion_QSSA_E0_menor_que_S0') else 'NO se cumple'} (ratio E0/S0={_fmt(result.get('ratio_E0_S0'))}).")
        lines.append(f"  - Error relativo promedio MM vs cinetica completa: {_fmt(err)} -> aproximacion {'VALIDA' if valida else 'NO valida'} (umbral 0.05).")
        if level == "basico":
            lines.append("La aproximacion de Michaelis-Menten asume que el complejo ES llega rapido a un estado cuasi-estacionario; eso solo es razonable cuando hay mucho menos enzima que sustrato (E0<<S0).")

    else:
        lines.append(f"Resultado de enzyme_kinetics_tool en modo '{mode}' (sin template narrativo especifico para este modo todavia).")
        keys = list(result.keys())[:8]
        lines.append(f"Campos principales: {', '.join(keys)}.")

    return "\n".join(lines)


def _explain_bacterial_growth(result, level):
    mode = result.get("mode", "?")
    lines = []

    if mode == "baranyi_roberts":
        p = result.get("params", {})
        lines.append(f"Curva de crecimiento bacteriano, modelo Baranyi-Roberts: mu_max={p.get('mu_max')}, y_max={p.get('y_max')}, h0={p.get('h0')}, t_max={p.get('t_max')}.")
        lines.append(f"  - Valor final (ln N/N0): {_fmt(result.get('final_y'))}.")
        lag = result.get("estimated_lag_time")
        if lag is not None:
            lines.append(f"  - Tiempo de lag estimado: {_fmt(lag)}.")
        if level == "basico":
            lines.append("h0 controla el estado fisiologico inicial de la poblacion: h0 alto = poblacion ya 'adaptada', lag corto; h0 bajo = lag largo antes de crecer.")

    elif mode == "gompertz":
        p = result.get("params", {})
        lines.append(f"Curva de crecimiento bacteriano, modelo Gompertz modificado (Zwietering 1990): mu_max={p.get('mu_max')}, asintota A={p.get('A')}, lag={p.get('lambda_lag')}, t_max={p.get('t_max')}.")
        lines.append(f"  - Valor final (ln N/N0): {_fmt(result.get('final_y'))}.")

    elif mode == "fit_growth_curve":
        if not result.get("converged"):
            lines.append(f"El ajuste de la curva Gompertz a los datos experimentales NO convergio: {result.get('error', 'sin detalle')}.")
        else:
            lines.append(f"Ajuste no lineal de curva Gompertz a datos experimentales: A={_fmt(result.get('A_fit'))}, mu_max={_fmt(result.get('mu_max_fit'))}, lag={_fmt(result.get('lambda_lag_fit'))}.")
            r2 = result.get("r_squared")
            lines.append(f"  - Bondad de ajuste (R2): {_fmt(r2)}.")
            if level == "basico" and r2 is not None:
                calidad = "muy bueno" if r2 > 0.9 else ("aceptable" if r2 > 0.7 else "pobre")
                lines.append(f"  - R2={_fmt(r2)} es un ajuste {calidad} (1.0 = perfecto).")

    else:
        lines.append(f"Resultado de bacterial_growth_tool en modo '{mode}' (sin template narrativo especifico para este modo todavia).")
        keys = [k for k in result.keys() if k not in ("t", "y_ln_N_N0", "fitted_values")][:8]
        lines.append(f"Campos principales: {', '.join(keys)}.")

    return "\n".join(lines)


def _explain_enzyme_stochastic(result, level):
    mode = result.get("mode", "?")
    lines = []

    if mode == "gillespie_michaelis_menten":
        p = result.get("params", {})
        lines.append(f"Simulacion estocastica exacta (Gillespie SSA) de una trayectoria: E0={p.get('E0')}, S0={p.get('S0')} moleculas, t_max={p.get('t_max')}.")
        lines.append(f"  - Eventos de reaccion simulados: {result.get('n_reaction_events')}.")
        lines.append(f"  - Estado final: S={_fmt(result.get('final_S'))}, P={_fmt(result.get('final_P'))} moleculas.")
        if level == "basico":
            lines.append("A diferencia del modelo ODE (numero continuo de moleculas), esto simula cada reaccion individual -- relevante cuando hay pocas moleculas y el ruido molecular importa.")

    elif mode == "gillespie_ensemble":
        p = result.get("params", {})
        n_runs = p.get("n_runs")
        p_mean = result.get("P_mean", [])
        p_std = result.get("P_std", [])
        lines.append(f"Ensamble de {n_runs} trayectorias estocasticas (Gillespie SSA): E0={p.get('E0')}, S0={p.get('S0')}, t_max={p.get('t_max')}.")
        if p_mean:
            lines.append(f"  - P(t) promedio al final: {_fmt(p_mean[-1])} +/- {_fmt(p_std[-1]) if p_std else '?'} (media +/- desvio sobre las {n_runs} corridas).")
        if level == "basico":
            lines.append("El desvio estandar entre corridas mide cuanto varia el resultado por el azar de las reacciones individuales -- desvio chico relativo a la media sugiere que el sistema se comporta casi deterministicamente.")

    else:
        lines.append(f"Resultado de enzyme_stochastic_tool en modo '{mode}' (sin template narrativo especifico para este modo todavia).")
        keys = [k for k in result.keys() if k not in ("trajectory", "query_times", "P_mean", "P_std", "S_mean", "S_std")][:8]
        lines.append(f"Campos principales: {', '.join(keys)}.")

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
    "compute_disaster_simulation": _explain_disaster_simulation,
    "compute_critical_infrastructure": _explain_critical_infrastructure,
    "compute_urban_planning": _explain_urban_planning,
    "compute_enzyme_kinetics": _explain_enzyme_kinetics,
    "compute_bacterial_growth_tool": _explain_bacterial_growth,
    "compute_enzyme_stochastic": _explain_enzyme_stochastic,
}


def _explain_generic(result, level):
    keys = list(result.keys())[:8]
    return (
        "No hay un template especifico para este tool todavia, asi que va una "
        f"descripcion generica del resultado. Campos principales: {', '.join(keys)}."
    )


def _run_self_test():
    """Autochequeo: corre interpret_and_explain sobre resultados sinteticos
    representativos de cada uno de los 17 tools reconocidos en _EXPLAINERS
    (mas el fallback generico), en ambos niveles ('basico' y 'tecnico'),
    y verifica que cada explicacion sea un string no vacio, que known_tool
    sea correcto, y que nada lance excepcion."""
    synthetic_cases = [
        ("compute_gradient_hessian", {
            "gradient": {"x": {"sympy": "2*x"}, "y": {"sympy": "2*y"}},
            "hessian": [[2, 0], [0, 2]],
        }),
        ("compute_jacobian", {"determinant": 3.5}),
        ("compute_lyapunov_exponent", {"lyapunov_exponent": 0.9}),
        ("integrate_stiff_ode", {"solver": "Radau", "t": [0.0, 0.1, 0.2]}),
        ("compute_bifurcation_diagram", {"stability": True}),
        ("compute_hilbert_transform", {}),
        ("math_error_analyzer", {"mode": "condition_number", "condition_number": 120.5}),
        ("math_benchmark", {"mode": "richardson"}),
        ("math_interpolation", {"runge_phenomenon_detected": True}),
        ("run_math_pipeline", {
            "n_steps": 2,
            "trace": [
                {"step": 0, "tool": "compute_gradient_hessian", "save_as": "grad"},
                {"step": 1, "tool": "math_error_analyzer", "save_as": "err"},
            ],
        }),
        ("math_visualization", {"mode": "function_plot", "y_min": -1.0, "y_max": 1.0}),
        ("compute_disaster_simulation", {
            "mode": "monte_carlo_losses", "n_years_simulated": 1000,
            "mean_annual_loss": 500.0, "std_annual_loss": 50.0,
            "median_annual_loss": 480.0, "max_simulated_loss": 2000.0,
            "probability_zero_loss_year": 0.1,
            "var_cvar_by_percentile": {"95%": {"VaR": 900.0, "CVaR": 1200.0}},
        }),
        ("compute_critical_infrastructure", {
            "redundancy_score": 0.8, "total_edges": 10,
            "base_graph_connected": True, "n_critical_edges": 1,
            "critical_edges": [{"from": "A", "to": "B"}],
        }),
        ("compute_urban_planning", {
            "shannon_entropy_normalized": 0.7, "n_categories": 3,
            "proportions": {"residencial": 0.5, "comercial": 0.3, "industrial": 0.2},
        }),
        ("compute_enzyme_kinetics", {
            "mode": "michaelis_menten", "Km": 5.0, "Vmax": 10.0,
            "formula": "v=Vmax*S/(Km+S)", "velocidad_sample": [1.0, 2.0, 3.0],
        }),
        ("compute_bacterial_growth_tool", {
            "mode": "gompertz",
            "params": {"mu_max": 0.5, "A": 3.0, "lambda_lag": 1.0, "t_max": 10.0},
            "final_y": 2.9,
        }),
        ("compute_enzyme_stochastic", {
            "mode": "gillespie_ensemble",
            "params": {"n_runs": 10, "E0": 5, "S0": 100, "t_max": 50.0},
            "P_mean": [0.0, 50.0, 95.0], "P_std": [0.0, 5.0, 3.0],
        }),
    ]

    checks = []

    for source_tool, synth_result in synthetic_cases:
        for level in ("basico", "tecnico"):
            try:
                out = interpret_and_explain(source_tool, synth_result, level=level)
                ok = (
                    isinstance(out.get("explanation"), str)
                    and len(out["explanation"]) > 0
                    and out.get("known_tool") is True
                )
                checks.append({
                    "name": f"{source_tool} ({level}): explicacion no vacia, known_tool=True",
                    "passed": ok,
                    "got_len": len(out.get("explanation", "")),
                })
            except Exception as e:
                checks.append({
                    "name": f"{source_tool} ({level}): no debe lanzar excepcion",
                    "passed": False,
                    "error": str(e),
                })

    # Caso fallback: tool desconocido -> explicacion generica, known_tool=False.
    try:
        out = interpret_and_explain("un_tool_que_no_existe_todavia", {"foo": 1, "bar": 2}, level="tecnico")
        ok = (
            isinstance(out.get("explanation"), str)
            and len(out["explanation"]) > 0
            and out.get("known_tool") is False
        )
        checks.append({
            "name": "tool desconocido: fallback generico, known_tool=False",
            "passed": ok,
        })
    except Exception as e:
        checks.append({
            "name": "tool desconocido: no debe lanzar excepcion",
            "passed": False,
            "error": str(e),
        })

    # Cobertura: todos los tools de _EXPLAINERS tienen un caso sintetico.
    covered = {c[0] for c in synthetic_cases}
    missing = set(_EXPLAINERS.keys()) - covered
    checks.append({
        "name": "cobertura: todos los _EXPLAINERS tienen caso sintetico",
        "passed": len(missing) == 0,
        "missing": sorted(missing),
    })

    all_passed = all(c["passed"] for c in checks)
    return {
        "checks": checks,
        "all_passed": all_passed,
        "total": len(checks),
        "validation_passed": all_passed,
    }


def interpret_and_explain(source_tool, result=None, level="tecnico"):
    if source_tool == "validate":
        return _run_self_test()
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

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("math_explainer", MATH_EXPLAINER_TOOL_SCHEMA, lambda args, _f=interpret_and_explain: _f(**args))
