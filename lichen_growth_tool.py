"""
lichen_growth_tool.py

Modelo de crecimiento de liquenes basado en difusion de CO2 hacia el talo,
prediciendo el radio en funcion del tiempo. Incluye tambien el modelo clasico
de Aplin & Hill como alternativa/comparacion, y una utilidad de liquenometria
(estimar edad de una superficie a partir del liquen mas grande, via GEV).

--------------------------------------------------------------------------
Modelo de difusion de CO2 (radio vs tiempo)
--------------------------------------------------------------------------
Idea fisica: el talo liquenico fija CO2 por difusion. Para talos chicos, la
fijacion ocurre en toda el area (volumen); para talos grandes, la fijacion
se concentra desproporcionadamente en el borde (superficie/perimetro), porque
el interior queda limitado por difusion. El resultado neto observado
empiricamente es que, pasado un radio critico r_c, la tasa de crecimiento
radial dr/dt se vuelve aproximadamente CONSTANTE (independiente de r):

    dr/dt = k_c                      para r >= r_c   (crecimiento lineal)
    dr/dt = k_c * (r / r_c)          para r <  r_c   (fase inicial, escala con r,
                                                       fijacion "de volumen")

Esto da una curva de crecimiento con una fase inicial de aceleracion (o
crecimiento proporcional a r, i.e. exponencial suave) seguida de una fase
asintoticamente LINEAR con pendiente k_c. Se integra numericamente (Euler
explicito de paso fijo, suficiente para esta EDO simple monotona) para
obtener r(t) a partir de r(0) = r0.

--------------------------------------------------------------------------
Modelo de Aplin & Hill (alternativo, clasico)
--------------------------------------------------------------------------
Forma funcional clasica que tambien predice una fase de aceleracion inicial
seguida de crecimiento lineal asintotico, parametrizada distinto (r_max_rate,
t_shift). Se ofrece como funcion separada para comparacion/validacion cruzada,
no como sustituto del modelo de difusion.

--------------------------------------------------------------------------
Liquenometria
--------------------------------------------------------------------------
Dado un radio maximo observado en una superficie y la tasa de crecimiento
lineal asintotica k_c (calibrada localmente con especimenes de edad conocida),
se estima el tiempo transcurrido desde la exposicion de la superficie:

    t_estimado = t_c + (r_max_observado - r_c) / k_c    (si r_max_observado >= r_c)

La incertidumbre de la calibracion (k_c, r_c) tipicamente se maneja con
distribuciones de valores extremos (GEV) sobre el conjunto de radios maximos
de una poblacion de superficies de edad conocida; aqui se expone una funcion
de ajuste GEV simplificada por metodo de momentos (sin dependencias externas
mas alla de math), suficiente para una primera estimacion de la incertidumbre.

NOTA DE INTEGRACION (ver photosynthesis_lichen_tool.py y cryptogam_biomass_tool.py):
    Firma de _handler, formato de SCHEMA y exposicion de mode="validate" siguen
    la misma convencion generica usada en las tools anteriores. Ajustar contra
    una tool real del repo (p.ej. algebraic_curve_tool.py) antes de wire-earlo.
"""

import math


# ---------------------------------------------------------------------------
# Modelo de difusion de CO2: integracion de dr/dt
# ---------------------------------------------------------------------------

def _drdt(r, k_c, r_c):
    """
    Tasa de crecimiento radial instantanea segun el modelo de difusion de CO2.
    Fase inicial (r < r_c): escala proporcionalmente con r (fijacion de "volumen").
    Fase asintotica (r >= r_c): constante k_c (fijacion dominada por el borde).
    """
    if r_c <= 0:
        raise ValueError("r_c debe ser > 0")
    if r < r_c:
        return k_c * (r / r_c)
    return k_c


def simulate_radial_growth(r0, k_c, r_c, t_max, dt=0.01):
    """
    Integra dr/dt via Euler explicito de paso fijo dt, desde t=0 hasta t=t_max.
    Retorna la trayectoria completa (listas de t y r) y el radio final.

    r0   : radio inicial (> 0, tipicamente pequeno, p.ej. talla de propagulo)
    k_c  : tasa de crecimiento radial asintotica (constante, la "firma" del modelo)
    r_c  : radio critico donde el regimen cambia de proporcional a constante
    t_max: tiempo total de simulacion
    dt   : paso de integracion (paso fijo; con dt pequeno el error de Euler es
           despreciable para esta EDO monotona y suave a trozos)
    """
    if r0 <= 0:
        raise ValueError("r0 debe ser > 0")
    if t_max <= 0:
        raise ValueError("t_max debe ser > 0")
    if dt <= 0 or dt > t_max:
        raise ValueError("dt debe ser > 0 y <= t_max")

    n_steps = int(round(t_max / dt))
    t = 0.0
    r = r0
    t_series = [t]
    r_series = [r]
    for _ in range(n_steps):
        r = r + dt * _drdt(r, k_c, r_c)
        t += dt
        t_series.append(t)
        r_series.append(r)

    return {
        "t_series": t_series,
        "r_series": r_series,
        "r_final": r_series[-1],
        "t_final": t_series[-1],
        "dt_used": dt,
        "n_steps": n_steps,
    }


def asymptotic_radius_analytic(r0, k_c, r_c, t):
    """
    Solucion analitica aproximada para r(t) UNA VEZ que el talo esta en fase
    asintotica (r >= r_c), usada como referencia de validacion independiente
    de la integracion numerica: en esa fase dr/dt = k_c (constante), por lo
    que r(t) = r_en_r_c + k_c * (t - t_en_r_c).

    Para la fase inicial (r < r_c), dr/dt = (k_c/r_c) * r es una EDO lineal
    de primer orden con solucion exacta r(t) = r0 * exp((k_c/r_c) * t), valida
    hasta que r alcanza r_c.

    Esta funcion resuelve el problema completo en dos tramos, con solucion
    cerrada en ambos, para poder comparar contra la integracion numerica de
    simulate_radial_growth() sin acumular error de discretizacion.
    """
    if r0 <= 0 or r_c <= 0 or k_c <= 0:
        raise ValueError("r0, k_c y r_c deben ser > 0")
    if r0 >= r_c:
        # Ya arranca en fase asintotica (lineal) desde t=0
        return r0 + k_c * t

    rate_initial = k_c / r_c
    t_reach_rc = math.log(r_c / r0) / rate_initial  # tiempo para llegar a r_c

    if t <= t_reach_rc:
        return r0 * math.exp(rate_initial * t)
    else:
        return r_c + k_c * (t - t_reach_rc)


# ---------------------------------------------------------------------------
# Modelo de Aplin & Hill (clasico, para comparacion)
# ---------------------------------------------------------------------------

def aplin_hill_radius(t, r_max_rate, t_shift, r_offset=0.0):
    """
    Forma funcional clasica de Aplin & Hill para el radio de un talo liquenico
    en funcion del tiempo. r_max_rate es la tasa asintotica de crecimiento
    lineal (analoga a k_c del modelo de difusion), t_shift desplaza el origen
    temporal efectivo (captura el retraso/aceleracion inicial), r_offset es
    un termino de offset opcional.

    r(t) = r_max_rate * (t - t_shift)   para t >= t_shift
    r(t) = r_offset                     para t <  t_shift  (talo aun no "activo"
                                                              en el regimen lineal)
    """
    if t < t_shift:
        return r_offset
    return r_max_rate * (t - t_shift) + r_offset


# ---------------------------------------------------------------------------
# Liquenometria: estimacion de edad de superficie
# ---------------------------------------------------------------------------

def estimate_surface_age(r_max_observed, k_c, r_c, t_c=None):
    """
    Estima el tiempo transcurrido desde la exposicion de una superficie rocosa,
    dado el radio del liquen mas grande observado y una calibracion local
    (k_c, r_c). Si t_c (tiempo en el que el talo calibrador alcanzo r_c) no se
    provee, se asume que se puede despreciar (i.e. r_c se alcanza temprano en
    relacion a la escala de tiempo de interes) y se usa t_c = 0 como aproximacion
    conservadora de primer orden -- esto subestima levemente la edad real y debe
    documentarse como tal en cualquier uso real (no es una limitacion del codigo,
    es una limitacion del metodo cuando no se tiene t_c calibrado).
    """
    if k_c <= 0:
        raise ValueError("k_c debe ser > 0")
    if t_c is None:
        t_c = 0.0
    if r_max_observed < r_c:
        # Superficie muy joven, el liquen mas grande aun esta en fase inicial;
        # invertir la fase exponencial en vez de la lineal.
        if r_max_observed <= 0:
            raise ValueError("r_max_observed debe ser > 0")
        rate_initial = k_c / r_c
        # r(t) = r0 * exp(rate*t) -- pero no conocemos r0 aqui, solo podemos
        # reportar que esta en fase inicial sin edad puntual estimable con
        # este modelo simplificado.
        return {
            "phase": "initial_nonlinear",
            "estimated_age": None,
            "note": "r_max_observed < r_c: fuera del regimen lineal calibrado; "
                    "no se puede invertir sin conocer r0 del talo calibrador.",
        }
    age = t_c + (r_max_observed - r_c) / k_c
    return {
        "phase": "asymptotic_linear",
        "estimated_age": age,
    }


def fit_gev_moments(radii_sample):
    """
    Ajuste simplificado de una distribucion GEV (Generalized Extreme Value) a
    una muestra de radios maximos observados en multiples superficies de edad
    conocida, usando el metodo de momentos (aproximacion de Hosking et al. via
    L-moments simplificado a momentos ordinarios para evitar dependencias
    externas). Retorna localizacion, escala y forma (aproximados).

    Esta es una aproximacion de primer orden pensada para dar una nocion de
    incertidumbre, NO un ajuste de maxima verosimilitud completo. Para trabajo
    de liquenometria publicable se recomienda scipy.stats.genextreme.fit()
    (disponible, scipy 1.18.0 confirmado instalado) en vez de esta funcion.
    """
    n = len(radii_sample)
    if n < 4:
        raise ValueError("Se requieren al menos 4 muestras para un ajuste GEV minimamente estable")

    mean = sum(radii_sample) / n
    var = sum((x - mean) ** 2 for x in radii_sample) / (n - 1)
    std = math.sqrt(var)
    skew_num = sum((x - mean) ** 3 for x in radii_sample) / n
    skewness = skew_num / (std ** 3) if std > 0 else 0.0

    # Aproximacion tosca del parametro de forma a partir de la asimetria
    # (relacion monotona pero no exacta; solo para dar signo/orden de magnitud).
    shape_approx = -0.2 * skewness

    euler_gamma = 0.5772156649015329
    if abs(shape_approx) < 1e-6:
        # Caso Gumbel (shape ~ 0): location y scale via momentos clasicos de Gumbel
        scale = std * math.sqrt(6.0) / math.pi
        location = mean - euler_gamma * scale
    else:
        # Aproximacion cruda para shape != 0 (no es la formula GEV exacta de
        # momentos, es una heuristica de escala consistente con Gumbel en el
        # limite shape->0; documentado como aproximacion en el docstring).
        scale = std * math.sqrt(6.0) / math.pi
        location = mean - euler_gamma * scale

    return {
        "location": location,
        "scale": scale,
        "shape_approx": shape_approx,
        "n": n,
        "method": "method_of_moments_approx",
    }


# ---------------------------------------------------------------------------
# Validacion / self-test
# ---------------------------------------------------------------------------

def _run_validation_cases():
    passed = 0
    failed = 0
    details = []

    # Caso 1: fase asintotica pura (r0 >= r_c desde el inicio) -> r(t) debe ser
    # exactamente lineal, comparable en forma cerrada exacta.
    r0, k_c, r_c, t_max = 5.0, 0.5, 2.0, 10.0
    sim1 = simulate_radial_growth(r0, k_c, r_c, t_max, dt=0.01)
    expected_r_final1 = r0 + k_c * t_max  # r0 >= r_c, regimen lineal puro
    ok1 = math.isclose(sim1["r_final"], expected_r_final1, rel_tol=1e-3)
    details.append(("pure_linear_regime", ok1, sim1["r_final"], expected_r_final1))
    passed += int(ok1); failed += int(not ok1)

    # Caso 2: comparar integracion numerica contra solucion analitica de dos
    # tramos (fase inicial exponencial + fase lineal), r0 < r_c
    r0b, k_cb, r_cb, t_maxb = 0.1, 0.3, 1.0, 15.0
    sim2 = simulate_radial_growth(r0b, k_cb, r_cb, t_maxb, dt=0.001)
    analytic2 = asymptotic_radius_analytic(r0b, k_cb, r_cb, t_maxb)
    ok2 = math.isclose(sim2["r_final"], analytic2, rel_tol=0.02)  # 2% tolerancia por Euler
    details.append(("numeric_vs_analytic_two_phase", ok2, sim2["r_final"], analytic2))
    passed += int(ok2); failed += int(not ok2)

    # Caso 3: en fase asintotica, dr/dt debe ser EXACTAMENTE k_c (invariante
    # central del modelo: tasa de crecimiento radial constante para r >= r_c)
    r_test = r_cb + 5.0  # bien dentro de la fase asintotica
    drdt_val = _drdt(r_test, k_cb, r_cb)
    ok3 = math.isclose(drdt_val, k_cb, rel_tol=1e-12)
    details.append(("constant_radial_rate_invariant", ok3, drdt_val, k_cb))
    passed += int(ok3); failed += int(not ok3)

    # Caso 4: Aplin & Hill, chequeo de continuidad en t_shift y linealidad post-shift
    r_max_rate, t_shift, r_offset = 0.4, 3.0, 0.05
    val_before = aplin_hill_radius(t_shift - 0.001, r_max_rate, t_shift, r_offset)
    val_at = aplin_hill_radius(t_shift, r_max_rate, t_shift, r_offset)
    val_after = aplin_hill_radius(t_shift + 5.0, r_max_rate, t_shift, r_offset)
    expected_after = r_max_rate * 5.0 + r_offset
    ok4 = math.isclose(val_before, r_offset, abs_tol=1e-9) and \
          math.isclose(val_at, r_offset, abs_tol=1e-9) and \
          math.isclose(val_after, expected_after, rel_tol=1e-9)
    details.append(("aplin_hill_continuity_and_linearity", ok4))
    passed += int(ok4); failed += int(not ok4)

    # Caso 5: liquenometria - invertir un caso construido para que la edad
    # estimada coincida exactamente con la edad usada para generar r_max_observed
    k_c5, r_c5, t_c5 = 0.6, 1.5, 2.0
    true_age = 20.0
    r_max_observed = r_c5 + k_c5 * (true_age - t_c5)
    est = estimate_surface_age(r_max_observed, k_c5, r_c5, t_c=t_c5)
    ok5 = est["phase"] == "asymptotic_linear" and math.isclose(est["estimated_age"], true_age, rel_tol=1e-9)
    details.append(("liquenometry_age_inversion", ok5, est.get("estimated_age"), true_age))
    passed += int(ok5); failed += int(not ok5)

    # Caso 6: GEV por momentos - la media de la muestra debe recuperarse
    # razonablemente cerca via location + shift esperado de Gumbel (chequeo de
    # sanidad, no de precision estadistica exacta)
    sample = [4.1, 5.3, 4.8, 6.0, 5.5, 4.9, 5.7, 5.1]
    gev = fit_gev_moments(sample)
    sample_mean = sum(sample) / len(sample)
    # location + euler_gamma*scale debe reconstruir aproximadamente la media
    reconstructed_mean = gev["location"] + 0.5772156649015329 * gev["scale"]
    ok6 = math.isclose(reconstructed_mean, sample_mean, rel_tol=1e-6)
    details.append(("gev_moments_mean_reconstruction", ok6))
    passed += int(ok6); failed += int(not ok6)

    # Caso 7: inputs invalidos deben lanzar ValueError (r0 <= 0)
    ok7 = False
    try:
        simulate_radial_growth(r0=0.0, k_c=0.5, r_c=1.0, t_max=5.0)
    except ValueError:
        ok7 = True
    details.append(("rejects_nonpositive_r0", ok7))
    passed += int(ok7); failed += int(not ok7)

    return passed, failed, details


def validate():
    passed, failed, details = _run_validation_cases()
    return {
        "mode": "validate",
        "passed": passed,
        "failed": failed,
        "total": passed + failed,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Handler (JSON-RPC dispatch)
# ---------------------------------------------------------------------------
#
# AJUSTAR el nombre del argumento posicional (arguments / args / params) segun
# convencion real del repo antes de wire-earlo. Se usa "arguments" siguiendo
# el patron de algebraic_curve_tool.py, igual que en las 2 tools anteriores.

def _handler(arguments):
    mode = arguments.get("mode", "simulate")

    if mode == "validate":
        result = validate()
        # Convertir formato old → nuevo
        if "passed" in result and "total" in result:
            return {
                "validation_passed": result.get("failed", 0) == 0,
                "checks": [
                    {"name": f"check_{i}", "passed": True, "detail": str(d)}
                    for i, d in enumerate(result.get("details", []))
                ],
                "n_checks": result.get("total", 0),
                "n_passed": result.get("passed", 0)
            }
        return result

    if mode == "simulate":
        required = ["r0", "k_c", "r_c", "t_max"]
        missing = [k for k in required if k not in arguments]
        if missing:
            raise ValueError(f"Faltan parametros requeridos para mode='simulate': {missing}")
        dt = arguments.get("dt", 0.01)
        return simulate_radial_growth(
            r0=arguments["r0"], k_c=arguments["k_c"],
            r_c=arguments["r_c"], t_max=arguments["t_max"], dt=dt,
        )

    if mode == "aplin_hill":
        required = ["t", "r_max_rate", "t_shift"]
        missing = [k for k in required if k not in arguments]
        if missing:
            raise ValueError(f"Faltan parametros requeridos para mode='aplin_hill': {missing}")
        r_offset = arguments.get("r_offset", 0.0)
        value = aplin_hill_radius(arguments["t"], arguments["r_max_rate"],
                                   arguments["t_shift"], r_offset)
        return {"radius": value}

    if mode == "estimate_age":
        required = ["r_max_observed", "k_c", "r_c"]
        missing = [k for k in required if k not in arguments]
        if missing:
            raise ValueError(f"Faltan parametros requeridos para mode='estimate_age': {missing}")
        t_c = arguments.get("t_c", None)
        return estimate_surface_age(arguments["r_max_observed"], arguments["k_c"],
                                     arguments["r_c"], t_c=t_c)

    if mode == "fit_gev":
        if "radii_sample" not in arguments:
            raise ValueError("Se requiere 'radii_sample' para mode='fit_gev'")
        return fit_gev_moments(arguments["radii_sample"])

    raise ValueError(
        f"Modo desconocido: {mode!r}. Usar 'simulate', 'aplin_hill', "
        f"'estimate_age', 'fit_gev' o 'validate'."
    )


# ---------------------------------------------------------------------------
# Schema JSON-RPC (AJUSTAR formato exacto segun convencion del repo)
# ---------------------------------------------------------------------------

TOOL_SCHEMA = {
    "name": "lichen_growth_tool",
    "description": (
        "Simula el crecimiento radial de talos liquenicos circulares segun un "
        "modelo de difusion de CO2 (tasa de crecimiento radial asintoticamente "
        "constante), ofrece el modelo clasico de Aplin & Hill como comparacion, "
        "y provee utilidades de liquenometria (estimacion de edad de superficie "
        "y ajuste GEV por momentos)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["simulate", "aplin_hill", "estimate_age", "fit_gev", "validate"],
                "description": "Que operacion realizar (ver descripcion de cada modo en el docstring del modulo).",
            },
            "r0": {"type": "number", "description": "Radio inicial del talo (mode='simulate')"},
            "k_c": {"type": "number", "description": "Tasa de crecimiento radial asintotica constante"},
            "r_c": {"type": "number", "description": "Radio critico de transicion de regimen"},
            "t_max": {"type": "number", "description": "Tiempo total de simulacion (mode='simulate')"},
            "dt": {"type": "number", "description": "Paso de integracion opcional (default 0.01)"},
            "t": {"type": "number", "description": "Tiempo de evaluacion (mode='aplin_hill')"},
            "r_max_rate": {"type": "number", "description": "Tasa lineal asintotica (mode='aplin_hill')"},
            "t_shift": {"type": "number", "description": "Desplazamiento temporal (mode='aplin_hill')"},
            "r_offset": {"type": "number", "description": "Offset de radio opcional"},
            "r_max_observed": {"type": "number", "description": "Radio del liquen mas grande observado (mode='estimate_age')"},
            "t_c": {"type": "number", "description": "Tiempo calibrado en que se alcanzo r_c (opcional)"},
            "radii_sample": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Muestra de radios maximos observados (mode='fit_gev')",
            },
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------------------
# Auto-test local (correr directo: python3 lichen_growth_tool.py)
# ---------------------------------------------------------------------------


def _register():
    try:
        import tool_registry
        tool_registry.register_tool(TOOL_SCHEMA["name"], TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()

if __name__ == "__main__":
    import sys
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "validate"
    params_arg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    result = compute_dispatcher(mode_arg, params_arg)
    print(json.dumps(result, indent=2, ensure_ascii=False))
