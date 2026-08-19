"""
flood_risk_narrator_tool.py

Traductor de la salida numerica de un modelo de inundacion (puntos
evaluados, puntos inundados, profundidades) a un reporte en lenguaje
natural: nivel de riesgo, resumen del escenario y recomendaciones
concretas -- pensado para que una comunidad sin conocimientos
tecnicos pueda leer el resultado de flood_modeling_tool sin tener
que interpretar JSON.

OJO -- contrato de entrada explicito, NO adivina el shape real de
flood_modeling_tool: no hay acceso al codigo fuente de esa tool
desde este sandbox, asi que en vez de asumir nombres de campos (y
arriesgar el mismo tipo de bug silencioso que ya paso en este repo
con run_octave_fn/resp -- ver notas de paleography_tool y
archaeoastronomy), esta tool define su propio contrato documentado
abajo. Para conectarla de verdad a la salida real de
flood_modeling_tool hace falta un adaptador chico (mapear los campos
reales a este shape) -- pendiente hasta ver el output real de esa
tool.

Contrato de entrada esperado (params) para mode="narrate":
{
  "location_name": str,              # opcional, ej. "Rio X, sector Y"
  "n_points_total": int,             # puntos/nodos evaluados en la grilla
  "n_points_flooded": int,           # cuantos de esos quedaron inundados
  "depth_min_m": float,
  "depth_mean_m": float,
  "depth_max_m": float,
  "scenario_label": str,             # opcional, ej. "lluvia 24h percentil 95"
  "precipitation_total_mm": float,   # opcional, tipicamente de hydrometeo_data
  "language": str,                   # opcional, default "es" -- unico idioma
                                      # implementado por ahora, ver nota abajo
}

Nota sobre idioma: la vision original habla de "el idioma de la
comunidad". Esta primera version solo genera texto en espanol
(language="es") -- cualquier otro valor devuelve error explicito en
vez de fallar en silencio o devolver espanol disfrazado de otro
idioma. Agregar mas idiomas es extender _RECOMMENDATIONS_* y
_format_report_* con un caso nuevo, sin tocar la logica de
clasificacion de riesgo.
"""

import json
from tool_registry import register_tool

# Umbrales de riesgo -- deliberadamente simples y editables, NO
# vienen de una norma tecnica especifica (ej. no son los umbrales
# oficiales de alguna guia de defensa civil). Punto de partida
# razonable, no un valor autoritativo -- ajustar si Astrid tiene
# umbrales locales mejores.
CRITICO_DEPTH_M = 2.0
CRITICO_FRACTION = 0.5
ALTO_DEPTH_M = 1.0
ALTO_FRACTION = 0.3
MEDIO_DEPTH_M = 0.3
MEDIO_FRACTION = 0.1

_RECOMMENDATIONS_ES = {
    "critico": [
        "Evaluar evacuacion preventiva de las zonas mas bajas antes de que suba el nivel.",
        "Cortar o asegurar el suministro electrico en las areas con riesgo antes de que llegue el agua.",
        "Tener confirmada de antemano una via de escape hacia terreno alto.",
    ],
    "alto": [
        "Mover bienes de valor y documentos a un nivel elevado.",
        "Monitorear el nivel del rio o el caudal con la frecuencia que permitan los datos disponibles.",
        "Identificar de antemano a las personas mayores o con movilidad reducida que necesitarian ayuda para evacuar.",
    ],
    "medio": [
        "Revisar canaletas y drenajes para que no haya obstrucciones antes de una lluvia fuerte.",
        "Tener un plan simple de a quien avisar y adonde ir si el nivel sigue subiendo.",
    ],
    "bajo": [
        "Sin accion urgente segun este escenario -- igual conviene revisar el pronostico de lluvia si se espera un evento fuerte.",
    ],
}


def _classify_risk(fraction_flooded, depth_mean_m, depth_max_m):
    if depth_max_m >= CRITICO_DEPTH_M or fraction_flooded >= CRITICO_FRACTION:
        return "critico"
    if depth_max_m >= ALTO_DEPTH_M or fraction_flooded >= ALTO_FRACTION:
        return "alto"
    if depth_max_m >= MEDIO_DEPTH_M or fraction_flooded >= MEDIO_FRACTION:
        return "medio"
    return "bajo"


def _format_report_es(p, risk_level, fraction_flooded):
    loc = p.get("location_name") or "la zona evaluada"
    scenario = p.get("scenario_label")
    lines = [f"Riesgo de inundacion para {loc}: {risk_level.upper()}."]
    if scenario:
        lines.append(f"Escenario: {scenario}.")
    lines.append(
        f"De {p['n_points_total']} puntos evaluados, {p['n_points_flooded']} "
        f"quedarian inundados ({fraction_flooded * 100:.0f}%)."
    )
    lines.append(
        f"Profundidad estimada: promedio {p['depth_mean_m']:.2f} m, "
        f"maxima {p['depth_max_m']:.2f} m."
    )
    precip = p.get("precipitation_total_mm")
    if precip is not None:
        lines.append(f"Lluvia acumulada considerada: {precip:.1f} mm.")
    lines.append("")
    lines.append("Recomendaciones:")
    lines.extend(f"- {rec}" for rec in _RECOMMENDATIONS_ES[risk_level])
    return "\n".join(lines)


def compute_flood_risk_narrator(mode, params=None):
    params = params or {}

    if mode == "validate":
        return _validate()

    if mode != "narrate":
        return {"error": f"modo desconocido: {mode}. Modos validos: narrate, validate"}

    required = ["n_points_total", "n_points_flooded", "depth_min_m", "depth_mean_m", "depth_max_m"]
    missing = [k for k in required if k not in params]
    if missing:
        return {"error": f"faltan params requeridos: {missing}"}

    language = params.get("language", "es")
    if language != "es":
        return {"error": f"idioma '{language}' no implementado todavia -- solo 'es' por ahora"}

    n_total = params["n_points_total"]
    n_flooded = params["n_points_flooded"]
    fraction_flooded = (n_flooded / n_total) if n_total else 0.0

    risk_level = _classify_risk(fraction_flooded, params["depth_mean_m"], params["depth_max_m"])
    report_text = _format_report_es(params, risk_level, fraction_flooded)

    return {
        "risk_level": risk_level,
        "fraction_flooded": round(fraction_flooded, 4),
        "report_text": report_text,
    }


def _validate():
    checks = []

    critico_profundidad = compute_flood_risk_narrator("narrate", {
        "n_points_total": 100, "n_points_flooded": 60,
        "depth_min_m": 0.1, "depth_mean_m": 1.5, "depth_max_m": 2.5,
    })
    checks.append({"check": "critico_por_profundidad_maxima", "passed": critico_profundidad["risk_level"] == "critico"})

    critico_fraccion = compute_flood_risk_narrator("narrate", {
        "n_points_total": 100, "n_points_flooded": 55,
        "depth_min_m": 0.05, "depth_mean_m": 0.4, "depth_max_m": 0.6,
    })
    checks.append({"check": "critico_por_fraccion_inundada", "passed": critico_fraccion["risk_level"] == "critico"})

    alto = compute_flood_risk_narrator("narrate", {
        "n_points_total": 100, "n_points_flooded": 35,
        "depth_min_m": 0.1, "depth_mean_m": 0.6, "depth_max_m": 1.1,
    })
    checks.append({"check": "alto_por_profundidad_maxima", "passed": alto["risk_level"] == "alto"})

    bajo = compute_flood_risk_narrator("narrate", {
        "n_points_total": 100, "n_points_flooded": 2,
        "depth_min_m": 0.0, "depth_mean_m": 0.05, "depth_max_m": 0.1,
    })
    checks.append({"check": "bajo_riesgo_minimo", "passed": bajo["risk_level"] == "bajo"})

    faltan = compute_flood_risk_narrator("narrate", {"n_points_total": 10})
    checks.append({"check": "params_incompletos_da_error_no_crash", "passed": "error" in faltan})

    idioma_no_soportado = compute_flood_risk_narrator("narrate", {
        "n_points_total": 10, "n_points_flooded": 1,
        "depth_min_m": 0.0, "depth_mean_m": 0.1, "depth_max_m": 0.1,
        "language": "en",
    })
    checks.append({"check": "idioma_no_implementado_da_error_explicito", "passed": "error" in idioma_no_soportado})

    checks.append({
        "check": "reporte_incluye_recomendaciones",
        "passed": "Recomendaciones" in critico_profundidad["report_text"],
    })

    cero_puntos = compute_flood_risk_narrator("narrate", {
        "n_points_total": 0, "n_points_flooded": 0,
        "depth_min_m": 0.0, "depth_mean_m": 0.0, "depth_max_m": 0.0,
    })
    checks.append({
        "check": "cero_puntos_totales_no_divide_por_cero",
        "passed": cero_puntos.get("risk_level") == "bajo" and "error" not in cero_puntos,
    })

    all_passed = all(c["passed"] for c in checks)
    return {"validation_passed": all_passed, "checks": checks}


FLOOD_RISK_NARRATOR_TOOL_SCHEMA = {
    "name": "flood_risk_narrator",
    "description": (
        "Convierte la salida numerica de un modelo de inundacion (puntos evaluados, "
        "puntos inundados, profundidades) en un reporte de riesgo en lenguaje natural "
        "con recomendaciones, pensado para comunidades sin conocimientos tecnicos. "
        "Contrato de entrada documentado en el docstring del modulo -- requiere un "
        "adaptador para conectarse a la salida real de flood_modeling_tool."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["narrate", "validate"]},
            "params": {
                "type": "object",
                "properties": {
                    "location_name": {"type": "string"},
                    "n_points_total": {"type": "integer"},
                    "n_points_flooded": {"type": "integer"},
                    "depth_min_m": {"type": "number"},
                    "depth_mean_m": {"type": "number"},
                    "depth_max_m": {"type": "number"},
                    "scenario_label": {"type": "string"},
                    "precipitation_total_mm": {"type": "number"},
                    "language": {"type": "string", "description": "solo 'es' implementado por ahora"},
                },
            },
        },
        "required": ["mode"],
    },
}

register_tool(
    name="flood_risk_narrator",
    schema=FLOOD_RISK_NARRATOR_TOOL_SCHEMA,
    handler=lambda args: compute_flood_risk_narrator(args.get("mode"), args.get("params")),
)


if __name__ == "__main__":
    print(json.dumps(compute_flood_risk_narrator("validate"), ensure_ascii=False, indent=2))
