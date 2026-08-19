"""
flood_risk_narrator_tool.py

Narra en lenguaje natural el riesgo de inundación a partir de la salida
REAL de flood_modeling_tool en modo manning_normal_depth:

    {
        "normal_depth_m": float,
        "top_width_m": float,
        "velocity_m_s": float,
        ...
    }

(No de flood_connectivity_tool, que trabaja con puntos/nodos inundados
sobre un DEM -- esa es una forma de salida completamente distinta.)

Clasifica el peligro con la fórmula de "Hazard Rating" (HR) usada por la
guía de evaluación de riesgo de inundación del Defra/Environment Agency
del Reino Unido (2005/2006), estándar bien documentado en literatura de
riesgo hidráulico:

    HR = d * (v + 0.5) + DF

donde:
    d  = profundidad de agua (m)
    v  = velocidad del flujo (m/s)
    DF = factor de escombros/detritos (0 = agua limpia, 0.5 = típico con
         escombros/objetos flotantes, 1.0 = alto contenido de escombros
         o estructuras vulnerables cerca)

Bandas de clasificación (mismas fuentes):
    HR < 0.75          -> bajo
    0.75 <= HR < 1.25   -> medio
    1.25 <= HR < 2.0    -> alto
    HR >= 2.0           -> crítico

Se registra vía tool_registry (patrón self-registrante, no requiere
tocar TOOLS[]/dispatch manual en server.py -- solo el import en
server.py, igual que hydrometeo_data_tool).
"""

import math

RISK_LEVELS = ["bajo", "medio", "alto", "crítico"]

RECOMMENDATIONS = {
    "bajo": [
        "Monitorear la evolución de las lluvias y el nivel del cauce.",
        "Verificar que desagües y alcantarillas cercanas estén despejados.",
    ],
    "medio": [
        "Mover bienes de valor y documentos a un nivel elevado.",
        "Monitorear el nivel del río o el caudal con la frecuencia que permitan los datos disponibles.",
        "Evitar cruzar el cauce o zonas bajas a pie o en vehículo.",
    ],
    "alto": [
        "Mover bienes de valor y documentos a un nivel elevado.",
        "Identificar de antemano a las personas mayores o con movilidad reducida que necesitarían ayuda para evacuar.",
        "Evitar por completo el contacto con el flujo: a esta profundidad y velocidad puede arrastrar a una persona de pie.",
        "Tener lista una vía de evacuación alternativa a la zona baja.",
    ],
    "crítico": [
        "Evacuar la zona antes de que el nivel siga subiendo.",
        "No intentar cruzar el flujo a pie ni en vehículo bajo ninguna circunstancia.",
        "Contactar a los organismos de emergencia locales (ONEMI/SENAPRED) si hay personas en la zona de riesgo.",
        "Asumir riesgo estructural para construcciones livianas cercanas al cauce.",
    ],
}


def _classify(hazard_rating):
    if hazard_rating < 0.75:
        return "bajo"
    elif hazard_rating < 1.25:
        return "medio"
    elif hazard_rating < 2.0:
        return "alto"
    else:
        return "crítico"


def _narrate(location_name, depth_m, velocity_m_s, hazard_rating, risk_level, top_width_m=None):
    lines = []
    lines.append(f"Riesgo de inundación para {location_name}: {risk_level.upper()}.")
    lines.append(
        f"Profundidad normal estimada: {depth_m:.2f} m. Velocidad de flujo: {velocity_m_s:.2f} m/s."
    )
    if top_width_m is not None:
        lines.append(f"Ancho superficial estimado del flujo: {top_width_m:.2f} m.")
    lines.append(f"Índice de peligrosidad (Hazard Rating, Defra/EA): {hazard_rating:.2f}.")
    lines.append("")
    lines.append("Recomendaciones:")
    for rec in RECOMMENDATIONS[risk_level]:
        lines.append(f"- {rec}")
    return "\n".join(lines)


def _adapt_from_flood_modeling(fm_output):
    """
    Traduce el dict real devuelto por compute_flood_modeling(mode=
    'manning_normal_depth', ...) al shape que espera este tool.

    Contrato real confirmado en vivo (flood_modeling_tool.py):
        {
            "Q_design_m3_s": ..., "bottom_width_m": ..., "side_slope": ...,
            "manning_n": ..., "slope": ...,
            "normal_depth_m": ..., "top_width_m": ..., "wetted_area_m2": ...,
            "wetted_perimeter_m": ..., "hydraulic_radius_m": ...,
            "velocity_m_s": ...,
            "Q_check_m3_s": ..., "Q_error_pct": ...
        }
    """
    required = ["normal_depth_m", "velocity_m_s"]
    missing = [k for k in required if k not in fm_output]
    if missing:
        return None, f"la salida de flood_modeling_tool no tiene los campos requeridos: {missing}"

    return {
        "depth_m": fm_output["normal_depth_m"],
        "velocity_m_s": fm_output["velocity_m_s"],
        "top_width_m": fm_output.get("top_width_m"),
    }, None


def compute_flood_risk_narrator(mode, params=None):
    # El handler registrado via tool_registry llama con un único dict
    # posicional (ej: handler({'mode': 'validate', 'params': {...}})),
    # mientras que las llamadas directas (import + compute_fn(...)) y los
    # checks internos de validate() usan la firma clásica de dos
    # argumentos (mode, params). Se normalizan ambas formas acá mismo,
    # mismo patrón que compute_hydrometeo_data.
    if isinstance(mode, dict):
        args = mode
        params = args.get("params", {})
        mode = args.get("mode")

    params = params or {}

    if mode == "classify_from_manning":
        required = ["depth_m", "velocity_m_s", "location_name"]
        missing = [k for k in required if k not in params]
        if missing:
            return {"error": f"faltan parámetros requeridos: {missing}"}

        depth_m = float(params["depth_m"])
        velocity_m_s = float(params["velocity_m_s"])
        location_name = params["location_name"]
        debris_factor = float(params.get("debris_factor", 0.0))
        top_width_m = params.get("top_width_m")

        if depth_m < 0 or velocity_m_s < 0:
            return {"error": "depth_m y velocity_m_s deben ser >= 0"}

        hazard_rating = depth_m * (velocity_m_s + 0.5) + debris_factor
        risk_level = _classify(hazard_rating)
        report = _narrate(
            location_name, depth_m, velocity_m_s, hazard_rating, risk_level, top_width_m
        )

        return {
            "location_name": location_name,
            "depth_m": depth_m,
            "velocity_m_s": velocity_m_s,
            "top_width_m": top_width_m,
            "debris_factor": debris_factor,
            "hazard_rating": round(hazard_rating, 4),
            "risk_level": risk_level,
            "report": report,
        }

    elif mode == "classify_from_flood_modeling":
        required = ["flood_modeling_output", "location_name"]
        missing = [k for k in required if k not in params]
        if missing:
            return {"error": f"faltan parámetros requeridos: {missing}"}

        adapted, err = _adapt_from_flood_modeling(params["flood_modeling_output"])
        if err:
            return {"error": err}

        adapted["location_name"] = params["location_name"]
        if "debris_factor" in params:
            adapted["debris_factor"] = params["debris_factor"]

        return compute_flood_risk_narrator("classify_from_manning", adapted)

    elif mode == "validate":
        checks = []

        # Caso 1: agua baja y lenta -> bajo. HR = 0.3*(0.5+0.5)+0 = 0.3
        r = compute_flood_risk_narrator(
            "classify_from_manning",
            {"depth_m": 0.3, "velocity_m_s": 0.5, "location_name": "test"},
        )
        checks.append({
            "check": "bajo_riesgo_agua_baja_lenta",
            "expected_level": "bajo",
            "actual_level": r["risk_level"],
            "expected_hr": 0.3,
            "actual_hr": r["hazard_rating"],
            "passed": r["risk_level"] == "bajo" and math.isclose(r["hazard_rating"], 0.3, abs_tol=1e-6),
        })

        # Caso 2: HR = 1.0*(1.0+0.5)+0 = 1.5 -> alto
        r = compute_flood_risk_narrator(
            "classify_from_manning",
            {"depth_m": 1.0, "velocity_m_s": 1.0, "location_name": "test"},
        )
        checks.append({
            "check": "alto_riesgo_profundo_moderado",
            "expected_level": "alto",
            "actual_level": r["risk_level"],
            "expected_hr": 1.5,
            "actual_hr": r["hazard_rating"],
            "passed": r["risk_level"] == "alto" and math.isclose(r["hazard_rating"], 1.5, abs_tol=1e-6),
        })

        # Caso 3: HR = 2.0*(2.0+0.5)+0 = 5.0 -> crítico
        r = compute_flood_risk_narrator(
            "classify_from_manning",
            {"depth_m": 2.0, "velocity_m_s": 2.0, "location_name": "test"},
        )
        checks.append({
            "check": "critico_riesgo_extremo",
            "expected_level": "crítico",
            "actual_level": r["risk_level"],
            "expected_hr": 5.0,
            "actual_hr": r["hazard_rating"],
            "passed": r["risk_level"] == "crítico" and math.isclose(r["hazard_rating"], 5.0, abs_tol=1e-6),
        })

        # Caso 4: debris_factor eleva la clasificación. HR = 0.5*2.0+0.5 = 1.5 -> alto
        r = compute_flood_risk_narrator(
            "classify_from_manning",
            {"depth_m": 0.5, "velocity_m_s": 1.5, "location_name": "test", "debris_factor": 0.5},
        )
        checks.append({
            "check": "debris_factor_eleva_clasificacion",
            "expected_level": "alto",
            "actual_level": r["risk_level"],
            "expected_hr": 1.5,
            "actual_hr": r["hazard_rating"],
            "passed": r["risk_level"] == "alto" and math.isclose(r["hazard_rating"], 1.5, abs_tol=1e-6),
        })

        # Caso 5: agua estancada (d=0, v=0) no revienta, HR=0, bajo
        r = compute_flood_risk_narrator(
            "classify_from_manning",
            {"depth_m": 0.0, "velocity_m_s": 0.0, "location_name": "test"},
        )
        checks.append({
            "check": "cero_no_revienta",
            "expected_level": "bajo",
            "actual_level": r.get("risk_level"),
            "passed": r.get("risk_level") == "bajo" and r.get("hazard_rating") == 0.0,
        })

        # Caso 6: adaptador contra fixture real de flood_modeling_tool
        # (Q=45 m3/s, sección trapezoidal, salida real confirmada en vivo)
        fm_output = {
            "Q_design_m3_s": 45.0, "bottom_width_m": 8.0, "side_slope": 1.5,
            "manning_n": 0.035, "slope": 0.001,
            "normal_depth_m": 2.73106, "top_width_m": 16.1932,
            "wetted_area_m2": 33.0365, "wetted_perimeter_m": 17.847,
            "hydraulic_radius_m": 1.8511, "velocity_m_s": 1.3621,
            "Q_check_m3_s": 45.0, "Q_error_pct": 0.0,
        }
        r = compute_flood_risk_narrator(
            "classify_from_flood_modeling",
            {"flood_modeling_output": fm_output, "location_name": "test"},
        )
        # HR = 2.73106*(1.3621+0.5) = 2.73106*1.8621 ~ 5.0865 -> critico
        expected_hr = 2.73106 * (1.3621 + 0.5)
        checks.append({
            "check": "adaptador_flood_modeling_fixture_real",
            "expected_level": "crítico",
            "actual_level": r.get("risk_level"),
            "expected_hr": round(expected_hr, 4),
            "actual_hr": r.get("hazard_rating"),
            "passed": r.get("risk_level") == "crítico"
                      and math.isclose(r.get("hazard_rating", -1), expected_hr, abs_tol=1e-3),
        })

        # Caso 6b: adaptador con campos faltantes da error, no crash
        r = compute_flood_risk_narrator(
            "classify_from_flood_modeling",
            {"flood_modeling_output": {"normal_depth_m": 1.0}, "location_name": "test"},
        )
        checks.append({
            "check": "adaptador_campos_faltantes_da_error_no_crash",
            "passed": "error" in r,
        })

        # Caso 7: params incompletos da error explícito, no crash
        r = compute_flood_risk_narrator("classify_from_manning", {"depth_m": 1.0})
        checks.append({
            "check": "params_incompletos_da_error_no_crash",
            "passed": "error" in r,
        })

        all_passed = all(c["passed"] for c in checks)
        return {"validation_passed": all_passed, "checks": checks}

    else:
        return {"error": f"modo no soportado: {mode}. Usar 'classify_from_manning' o 'validate'."}


FLOOD_RISK_NARRATOR_SCHEMA = {
    "name": "flood_risk_narrator",
    "description": (
        "Clasifica el riesgo de inundación (bajo/medio/alto/crítico) y genera un reporte en "
        "lenguaje natural a partir de profundidad y velocidad de flujo -- p.ej. la salida real "
        "de flood_modeling_tool en modo manning_normal_depth (normal_depth_m, velocity_m_s)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["classify_from_manning", "classify_from_flood_modeling", "validate"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "depth_m": {"type": "number", "description": "Profundidad de agua en metros (normal_depth_m de flood_modeling_tool) -- modo classify_from_manning"},
                    "velocity_m_s": {"type": "number", "description": "Velocidad del flujo en m/s -- modo classify_from_manning"},
                    "top_width_m": {"type": "number", "description": "Ancho superficial del flujo en metros (opcional)"},
                    "flood_modeling_output": {"type": "object", "description": "Dict de salida completo de compute_flood_modeling(mode='manning_normal_depth', ...) -- modo classify_from_flood_modeling"},
                    "location_name": {"type": "string", "description": "Nombre del lugar/cauce a narrar"},
                    "debris_factor": {"type": "number", "description": "0 = agua limpia, 0.5 = escombros típicos, 1.0 = alto contenido de escombros (default 0.0)"},
                },
            },
        },
        "required": ["mode"],
    },
}


try:
    from tool_registry import register_tool
    register_tool(
        "flood_risk_narrator",
        FLOOD_RISK_NARRATOR_SCHEMA,
        compute_flood_risk_narrator,
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    print(json.dumps(compute_flood_risk_narrator("validate"), indent=2, ensure_ascii=False))
