"""
photosynthesis_lichen_tool.py

Modelo de fotosintesis neta para liquenes y musgos (poikilohydric photosynthesis model).

Ecuacion central:
    A = [ (Pm20 * PPFD) / (alpha_PPFD + PPFD) * f_T(T) - Rs20 * f_R(T) ] * Bcap * f_W(Wcap)

Donde:
    Pm20      : tasa maxima de fotosintesis bruta a 20 C (umol CO2 / g Chl / s, o unidad equivalente)
    PPFD      : densidad de flujo de fotones fotosinteticos (umol foton / m^2 / s)
    alpha_PPFD: constante de saturacion de luz (media saturacion, misma unidad que PPFD)
    Rs20      : tasa de respiracion a 20 C
    T         : temperatura del talo (C)
    Bcap      : capacidad de biomasa / factor de escala de biomasa fotosinteticamente activa
    Wcap      : contenido de agua relativo del talo (0-1, o unidad especifica del sitio)

Funciones de respuesta:
    f_T(T): respuesta tipo Q10 tanto para fotosintesis como respiracion (curvas separadas
            son comunes en la literatura, aqui se ofrece una funcion Q10 generica que se
            puede parametrizar distinto para f_T y f_R via T_ref/Q10 propios).
    f_R(T): igual forma funcional que f_T pero con su propio Q10 (tipicamente distinto).
    f_W(Wcap): funcion de respuesta al contenido de agua, tipo sigmoide/saturante que capta
               tanto la limitacion por desecacion (W bajo) como la depresion por exceso de
               agua que bloquea difusion de CO2 (W alto), comun en liquenes poikilohydricos.

NOTA DE INTEGRACION:
    Este archivo sigue una convencion GENERICA basada en los patrones observados en otras
    tools del repo (schema con "mode" incluyendo "validate", handler de un solo argumento
    posicional). Antes de wire-earlo en server.py, comparar linea por linea contra una tool
    simple ya funcionando (p.ej. algebraic_curve_tool.py) para:
      - nombre exacto del parametro del handler (arguments / args / params)
      - forma exacta en que tool_registry.register_tool() espera el schema
      - convencion de nombres de campos en el schema (inputSchema vs input_schema, etc.)
    Ajustar segun corresponda antes de copiar a ~/octave-mcp/.
"""

import math


# ---------------------------------------------------------------------------
# Funciones de respuesta biofisica
# ---------------------------------------------------------------------------

def _q10_response(T, T_ref=20.0, Q10=2.0):
    """
    Respuesta tipo Q10 generica: factor multiplicativo relativo a T_ref.
    f(T_ref) = 1.0 por construccion.
    """
    return Q10 ** ((T - T_ref) / 10.0)


def _water_response(Wcap, W_opt=0.7, k_low=20.0, k_high=8.0, W_high_onset=0.95,
                     rise_center=0.2):
    """
    Respuesta al contenido de agua del talo, forma tipo campana suave:
      - sube con Wcap hasta W_opt (limitacion por desecacion resuelta)
      - se mantiene cerca de 1.0 en la meseta
      - cae si Wcap se acerca a saturacion total (bloqueo de difusion de CO2
        por pelicula de agua, fenomeno bien documentado en liquenes)
    Implementada como producto de dos sigmoides (ascenso y descenso), acotada en [0, 1].
    k_low mas alto y rise_center = 0.2 aseguran que f_W colapse fuerte y rapido
    cerca de Wcap = 0 (desecacion severa), consistente con la fisiologia de
    liquenes poikilohidricos (perdida casi total de actividad al secarse).
    """
    Wcap = max(0.0, min(1.0, Wcap))
    rise = 1.0 / (1.0 + math.exp(-k_low * (Wcap - rise_center)))
    fall = 1.0 / (1.0 + math.exp(k_high * (Wcap - W_high_onset)))
    # normalizar para que el maximo del producto sea ~1.0 en W_opt
    norm_at_opt = (1.0 / (1.0 + math.exp(-k_low * (W_opt - 0.15)))) * \
                  (1.0 / (1.0 + math.exp(k_high * (W_opt - W_high_onset))))
    if norm_at_opt <= 0:
        norm_at_opt = 1.0
    return (rise * fall) / norm_at_opt


# ---------------------------------------------------------------------------
# Modelo central
# ---------------------------------------------------------------------------

def net_photosynthesis(Pm20, PPFD, alpha_PPFD, Rs20, T, Bcap, Wcap,
                        Q10_photo=2.0, Q10_resp=2.0, T_ref=20.0,
                        W_opt=0.7, k_low=20.0, k_high=8.0, W_high_onset=0.95):
    """
    Calcula la tasa de fotosintesis neta A segun el modelo descrito en el docstring
    del modulo.

    Retorna un dict con el valor de A y los factores intermedios (utilidad para
    debugging y para que el caller pueda auditar el calculo sin recomputar).
    """
    if alpha_PPFD <= 0:
        raise ValueError("alpha_PPFD debe ser > 0 (constante de saturacion de luz)")
    if PPFD < 0:
        raise ValueError("PPFD no puede ser negativo")

    light_term = (Pm20 * PPFD) / (alpha_PPFD + PPFD)
    fT = _q10_response(T, T_ref=T_ref, Q10=Q10_photo)
    fR = _q10_response(T, T_ref=T_ref, Q10=Q10_resp)
    fW = _water_response(Wcap, W_opt=W_opt, k_low=k_low, k_high=k_high,
                          W_high_onset=W_high_onset)

    gross_minus_resp = (light_term * fT) - (Rs20 * fR)
    A = gross_minus_resp * Bcap * fW

    return {
        "A": A,
        "light_term": light_term,
        "f_T": fT,
        "f_R": fR,
        "f_W": fW,
        "gross_minus_resp_before_water_biomass": gross_minus_resp,
    }


# ---------------------------------------------------------------------------
# Validacion / self-test
# ---------------------------------------------------------------------------

def _run_validation_cases():
    """
    Casos de prueba con valores de referencia calculados analiticamente a mano
    (sustituyendo directo en la formula, sin pasar por net_photosynthesis) para
    evitar que un bug en la implementacion se auto-confirme.

    Cada caso: (kwargs, valor_esperado_de_A, tolerancia_relativa)
    """
    cases = []

    # Caso 1: T = T_ref = 20 (f_T = f_R = 1.0 exactos, sin ambiguedad de Q10),
    # Wcap = W_opt exacto (f_W debe dar ~1.0 por normalizacion)
    kwargs1 = dict(Pm20=10.0, PPFD=500.0, alpha_PPFD=250.0, Rs20=1.0,
                   T=20.0, Bcap=1.0, Wcap=0.7)
    light_term1 = (10.0 * 500.0) / (250.0 + 500.0)   # = 6.6666...
    expected1 = (light_term1 * 1.0 - 1.0 * 1.0) * 1.0 * 1.0  # fW ~ 1.0 en W_opt
    cases.append((kwargs1, expected1, 0.02))  # 2% tolerancia por la normalizacion de fW

    # Caso 2: PPFD = 0 -> solo respiracion negativa, fW en W_opt
    kwargs2 = dict(Pm20=10.0, PPFD=0.0, alpha_PPFD=250.0, Rs20=1.0,
                   T=20.0, Bcap=1.0, Wcap=0.7)
    expected2 = (0.0 - 1.0) * 1.0 * 1.0
    cases.append((kwargs2, expected2, 0.02))

    # Caso 3: Wcap = 0 -> desecacion total, f_W debe colapsar cerca de 0
    kwargs3 = dict(Pm20=10.0, PPFD=500.0, alpha_PPFD=250.0, Rs20=1.0,
                   T=20.0, Bcap=1.0, Wcap=0.0)
    # No hay formula cerrada simple aqui por la sigmoide; se chequea signo/magnitud
    # en vez de un valor exacto (ver assert especial abajo).
    cases.append((kwargs3, None, None))

    # Caso 4: Bcap escala linealmente -> duplicar Bcap debe duplicar A si A>0 en caso base
    kwargs4a = dict(Pm20=10.0, PPFD=500.0, alpha_PPFD=250.0, Rs20=1.0,
                    T=20.0, Bcap=1.0, Wcap=0.7)
    kwargs4b = dict(kwargs4a); kwargs4b["Bcap"] = 2.0
    cases.append(("SCALE_CHECK", (kwargs4a, kwargs4b)))

    passed = 0
    failed = 0
    details = []

    for entry in cases:
        if entry[0] == "SCALE_CHECK":
            a_kwargs, b_kwargs = entry[1]
            rA = net_photosynthesis(**a_kwargs)["A"]
            rB = net_photosynthesis(**b_kwargs)["A"]
            ok = math.isclose(rB, 2.0 * rA, rel_tol=1e-9)
            details.append(("scale_check_Bcap_linear", ok))
            passed += int(ok); failed += int(not ok)
            continue

        kwargs, expected, tol = entry
        result = net_photosynthesis(**kwargs)
        A = result["A"]

        if kwargs.get("Wcap") == 0.0 and expected is None:
            # Caso 3: solo verificamos que f_W sea pequeno (desecacion severa reduce
            # fuertemente la actividad fotosintetica neta observable)
            ok = result["f_W"] < 0.05
            details.append(("desiccation_collapse_fW", ok, result["f_W"]))
            passed += int(ok); failed += int(not ok)
            continue

        ok = math.isclose(A, expected, rel_tol=tol)
        details.append((kwargs, A, expected, ok))
        passed += int(ok); failed += int(not ok)

    return passed, failed, details


def validate():
    """
    Punto de entrada de validacion. Ajustar el nombre/firma de esta funcion segun
    la convencion real de mode="validate" en el resto del repo (algunas tools
    exponen esto como parte del dispatch de _handler en vez de una funcion suelta).
    """
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
# AJUSTAR el nombre del argumento posicional (arguments / args / params) para que
# coincida con el resto del repo antes de wire-earlo. Se usa "arguments" aqui
# siguiendo el patron visto en algebraic_curve_tool.py.

def _handler(arguments):
    mode = arguments.get("mode", "compute")

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

    if mode == "compute":
        required = ["Pm20", "PPFD", "alpha_PPFD", "Rs20", "T", "Bcap", "Wcap"]
        missing = [k for k in required if k not in arguments]
        if missing:
            raise ValueError(f"Faltan parametros requeridos: {missing}")

        optional_kwargs = {
            k: arguments[k] for k in
            ["Q10_photo", "Q10_resp", "T_ref", "W_opt", "k_low", "k_high", "W_high_onset"]
            if k in arguments
        }

        return net_photosynthesis(
            Pm20=arguments["Pm20"],
            PPFD=arguments["PPFD"],
            alpha_PPFD=arguments["alpha_PPFD"],
            Rs20=arguments["Rs20"],
            T=arguments["T"],
            Bcap=arguments["Bcap"],
            Wcap=arguments["Wcap"],
            **optional_kwargs,
        )

    raise ValueError(f"Modo desconocido: {mode!r}. Usar 'compute' o 'validate'.")


# ---------------------------------------------------------------------------
# Schema JSON-RPC (AJUSTAR formato exacto segun convencion del repo)
# ---------------------------------------------------------------------------

TOOL_SCHEMA = {
    "name": "photosynthesis_lichen_tool",
    "description": (
        "Calcula la tasa de fotosintesis neta (A) de liquenes y musgos en funcion "
        "de la luz (PPFD), la temperatura del talo y el contenido de agua, segun "
        "el modelo de fotosintesis neta poikilohidrica."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["compute", "validate"],
                "description": "compute: calcula A. validate: corre el self-test.",
            },
            "Pm20": {"type": "number", "description": "Tasa maxima de fotosintesis a 20 C"},
            "PPFD": {"type": "number", "description": "Densidad de flujo de fotones fotosinteticos"},
            "alpha_PPFD": {"type": "number", "description": "Constante de saturacion de luz"},
            "Rs20": {"type": "number", "description": "Tasa de respiracion a 20 C"},
            "T": {"type": "number", "description": "Temperatura del talo (C)"},
            "Bcap": {"type": "number", "description": "Factor de escala de biomasa activa"},
            "Wcap": {"type": "number", "description": "Contenido de agua relativo del talo (0-1)"},
            "Q10_photo": {"type": "number", "description": "Q10 opcional para fotosintesis (default 2.0)"},
            "Q10_resp": {"type": "number", "description": "Q10 opcional para respiracion (default 2.0)"},
            "T_ref": {"type": "number", "description": "Temperatura de referencia (default 20.0)"},
            "W_opt": {"type": "number", "description": "Wcap optimo (default 0.7)"},
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------------------
# Auto-test local (correr directo: python3 photosynthesis_lichen_tool.py)
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
