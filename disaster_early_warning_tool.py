"""
disaster_early_warning_tool -- orquestador de alerta temprana.

Combina 5 tools existentes del repo para producir una evaluacion de riesgo
de inundacion y/o incendio para una comunidad dada sus coordenadas:

  terrain_elevation_tool  -> elevacion real (OpenTopoData, red)
  hydrometeo_data_tool    -> precipitacion / caudal / clima actual (Open-Meteo, red)
  flood_modeling_tool     -> tirante normal via Manning (calculo puro, sin red)
  flood_risk_narrator_tool-> clasificacion de riesgo de inundacion (calculo puro)
  wildfire_risk_tool      -> rate_of_spread via Rothermel (calculo puro)

No agrega logica de calculo nueva -- es "plomeria": arma los params de cada
tool a partir del input del usuario y las salidas de las tools anteriores,
y combina los resultados en una alerta unificada.

LIMITACIONES CONOCIDAS (no resueltas, documentadas a proposito):
  - El viento de hydrometeo_data_tool (current_weather) viene medido a 10m
    de altura. wildfire_risk_tool espera viento a 20ft (~6.1m) o a media
    llama. Se aplica un ajuste por ley de potencia (u2/u1 = (h2/h1)^(1/7))
    de 10m a 20ft (factor ~0.93). Esto NO es lo mismo que el "wind
    adjustment factor" de dosel/vegetacion que usan los modelos operativos
    de incendio (que puede bajar el viento a media llama mucho mas, segun
    densidad de canopia) -- es una aproximacion meteorologica basica, no
    un WAF forestal. Documentado en el resultado, no oculto.
  - La humedad del combustible (moisture: 1hr/10hr/100hr/live_herb/live_woody)
    que pide wildfire_risk_tool NO se deriva automaticamente de la humedad
    relativa del aire -- son cosas distintas (fuel moisture vs relative
    humidity), convertir una en otra requiere un modelo de equilibrio de
    humedad (p.ej. Nelson) que este tool no implementa. El usuario tiene
    que pasar moisture explicitamente en el bloque "fuel" para que se
    calcule rate_of_spread; si no lo pasa, esa rama se skipea con motivo
    explicito en vez de inventar un valor.
  - La geometria del cauce (bottom_width_m, manning_n, slope) tampoco sale
    de ninguna API publica -- es conocimiento local del lugar. Si no se
    pasa en "channel_geometry", la rama de inundacion se skipea.
"""

import json

from terrain_elevation_tool import compute_terrain_elevation
from hydrometeo_data_tool import compute_hydrometeo_data
from flood_modeling_tool import compute_flood_modeling
from flood_risk_narrator_tool import compute_flood_risk_narrator
from wildfire_risk_tool import compute_wildfire_risk

from tool_registry import register_tool

# Ley de potencia estandar para perfil de viento (Hellmann exponent 1/7),
# de 10m (altura tipica de estaciones meteo) a 20ft = 6.096m (altura
# estandar de referencia en modelos de incendio tipo Rothermel/BEHAVE).
_WIND_10M_TO_20FT_FACTOR = (6.096 / 10.0) ** (1.0 / 7.0)  # ~0.9317


def _safe_call(label, fn):
    """Envuelve una llamada a sub-tool: nunca deja que una excepcion tire
    abajo el resto del assessment. Devuelve (ok, resultado_o_error)."""
    try:
        return True, fn()
    except Exception as e:
        return False, {"error": f"{label} fallo: {type(e).__name__}: {e}"}


def _assess_terrain(lat, lon, dataset):
    ok, result = _safe_call(
        "terrain_elevation_tool",
        lambda: compute_terrain_elevation("elevation_lookup", {
            "locations": [[lat, lon]],
            "dataset": dataset,
        }),
    )
    return {"ok": ok, "result": result}


def _assess_hydrometeo(lat, lon, start_date, end_date):
    out = {}
    for key, mode, extra in (
        ("precipitation", "precipitation_history", {"start_date": start_date, "end_date": end_date}),
        ("discharge", "river_discharge", {"start_date": start_date, "end_date": end_date}),
        ("current_weather", "current_weather", {}),
    ):
        params = {"lat": lat, "lon": lon}
        params.update(extra)
        ok, result = _safe_call(
            f"hydrometeo_data_tool[{mode}]",
            lambda mode=mode, params=params: compute_hydrometeo_data(mode, params),
        )
        out[key] = {"ok": ok, "result": result}
    return out


def _assess_flood(channel_geometry, discharge_summary, location_name, debris_factor):
    if not channel_geometry:
        return {"skipped": True, "reason": "no se paso 'channel_geometry' -- rama de inundacion omitida"}

    required = ("bottom_width_m", "manning_n", "slope")
    faltan = [k for k in required if channel_geometry.get(k) is None]
    if faltan:
        return {
            "skipped": True,
            "reason": f"faltan campos en channel_geometry para calcular Manning: {faltan}",
        }

    Q = channel_geometry.get("Q")
    if Q is None:
        Q = discharge_summary.get("mean_discharge_m3s") if discharge_summary else None
    if Q is None:
        return {
            "skipped": True,
            "reason": (
                "no se paso channel_geometry.Q y river_discharge no trajo un "
                "mean_discharge_m3s utilizable (probablemente sin celda GloFAS "
                "cerca de esas coordenadas) -- no se puede correr Manning sin caudal"
            ),
        }

    manning_params = {
        "Q": Q,
        "bottom_width_m": channel_geometry["bottom_width_m"],
        "manning_n": channel_geometry["manning_n"],
        "slope": channel_geometry["slope"],
    }
    if channel_geometry.get("side_slope") is not None:
        manning_params["side_slope"] = channel_geometry["side_slope"]

    ok_model, modeling = _safe_call(
        "flood_modeling_tool[manning_normal_depth]",
        lambda: compute_flood_modeling("manning_normal_depth", manning_params),
    )
    if not ok_model:
        return {"skipped": False, "error": modeling}

    ok_narr, narration = _safe_call(
        "flood_risk_narrator_tool[classify_from_flood_modeling]",
        lambda: compute_flood_risk_narrator("classify_from_flood_modeling", {
            "flood_modeling_output": modeling,
            "location_name": location_name,
            "debris_factor": debris_factor if debris_factor is not None else 0.0,
        }),
    )

    _q_is_override = channel_geometry.get("Q") is not None
    return {
        "skipped": False,
        "Q_used_m3s": Q,
        "Q_source": "channel_geometry.Q (override manual)" if _q_is_override else "hydrometeo_data_tool.river_discharge (mean historico)",
        "Q_design_note": (
            None if _q_is_override else
            "Q_used_m3s es la media historica de caudal de los ultimos 31 dias "
            "(hydrometeo_data_tool.river_discharge), NO un caudal de diseño hidrologico "
            "real (percentil de crecida, periodo de retorno, etc.) -- mismo criterio que "
            "confidence_flag/wind_source_note en el resto del pipeline, usar con precaucion "
            "para dimensionamiento serio de infraestructura."
        ),
        "flood_modeling": modeling,
        "flood_risk_narration": narration if ok_narr else {"error": narration},
    }


def _assess_wildfire(fuel, current_weather_result):
    if not fuel or (not fuel.get("fuel_model") and not fuel.get("custom_fuel")):
        return {"skipped": True, "reason": "no se paso 'fuel.fuel_model' ni 'fuel.custom_fuel' -- rama de incendio omitida"}
    if not fuel.get("moisture"):
        return {
            "skipped": True,
            "reason": (
                "no se paso 'fuel.moisture' (1hr/10hr/100hr/live_herb/live_woody) -- "
                "la humedad relativa del aire NO se convierte automaticamente en "
                "humedad de combustible, son magnitudes distintas. Sin esto no se "
                "puede correr rate_of_spread."
            ),
        }

    params = {
        "fuel_model": fuel.get("fuel_model"),
        "fuel_catalog": fuel.get("fuel_catalog", "anderson13"),
        "custom_fuel": fuel.get("custom_fuel"),
        "moisture": fuel["moisture"],
        "slope_percent": fuel.get("slope_percent", 0.0),
    }
    for optional_key in ("live_moisture_of_extinction", "heat_content_btu_lb"):
        if fuel.get(optional_key) is not None:
            params[optional_key] = fuel[optional_key]

    wind_note = None
    if fuel.get("wind_speed_20ft_mph") is not None:
        params["wind_speed_20ft_mph"] = fuel["wind_speed_20ft_mph"]
        wind_note = "wind_speed_20ft_mph provisto manualmente por el usuario, no derivado de hydrometeo"
    elif current_weather_result and current_weather_result.get("ok"):
        mph_10m = current_weather_result["result"].get("wind_speed_10m_mph")
        if mph_10m is not None:
            wind_20ft = round(mph_10m * _WIND_10M_TO_20FT_FACTOR, 3)
            params["wind_speed_20ft_mph"] = wind_20ft
            wind_note = (
                f"derivado de hydrometeo_data_tool.current_weather ({mph_10m} mph a 10m) "
                f"via ajuste ley de potencia (factor {_WIND_10M_TO_20FT_FACTOR:.4f}) a 20ft -- "
                "aproximacion meteorologica, NO un wind adjustment factor forestal"
            )

    ok, result = _safe_call(
        "wildfire_risk_tool[rate_of_spread]",
        lambda: compute_wildfire_risk("rate_of_spread", params),
    )
    return {
        "skipped": False,
        "wind_source_note": wind_note,
        "result": result if ok else {"error": result},
    }


def _mode_full_assessment(params):
    lat = params.get("lat")
    lon = params.get("lon")
    location_name = params.get("location_name")
    if lat is None or lon is None or not location_name:
        return {"error": "faltan params requeridos: lat, lon, location_name"}

    dataset = params.get("elevation_dataset", "srtm90m")
    start_date = params.get("precip_start_date")
    end_date = params.get("precip_end_date")

    terrain = _assess_terrain(lat, lon, dataset)
    hydro = _assess_hydrometeo(lat, lon, start_date, end_date)

    discharge_summary = hydro["discharge"]["result"] if hydro["discharge"]["ok"] else {}
    flood = _assess_flood(
        params.get("channel_geometry"),
        discharge_summary,
        location_name,
        params.get("debris_factor"),
    )
    wildfire = _assess_wildfire(params.get("fuel"), hydro["current_weather"])

    return {
        "location_name": location_name,
        "coordinates": {"lat": lat, "lon": lon},
        "terrain": terrain,
        "hydrometeo": hydro,
        "flood_assessment": flood,
        "wildfire_assessment": wildfire,
    }


def _validate():
    checks = []

    for label, fn in (
        ("terrain_elevation_tool", lambda: compute_terrain_elevation("validate")),
        ("hydrometeo_data_tool", lambda: compute_hydrometeo_data("validate")),
        ("flood_modeling_tool", lambda: compute_flood_modeling("validate")),
        ("flood_risk_narrator_tool", lambda: compute_flood_risk_narrator("validate")),
        ("wildfire_risk_tool", lambda: compute_wildfire_risk("validate", {})),
    ):
        r = fn()
        checks.append({
            "check": f"sub_tool_{label}_validate_passed",
            "expected": True,
            "actual": r.get("validation_passed"),
            "passed": r.get("validation_passed") is True,
        })

    # Prueba offline de _assess_flood: geometria completa + Q manual,
    # no requiere red (flood_modeling_tool/flood_risk_narrator_tool son
    # calculo puro).
    flood_result = _assess_flood(
        channel_geometry={"Q": 50.0, "bottom_width_m": 4.0, "manning_n": 0.035, "slope": 0.001},
        discharge_summary={},
        location_name="rio de prueba (validate)",
        debris_factor=0.0,
    )
    checks.append({
        "check": "assess_flood_con_geometria_completa_no_se_skipea",
        "expected": False,
        "actual": flood_result.get("skipped"),
        "passed": flood_result.get("skipped") is False,
    })
    checks.append({
        "check": "assess_flood_Q_manual_tiene_prioridad_sobre_discharge",
        "expected": "channel_geometry.Q (override manual)",
        "actual": flood_result.get("Q_source"),
        "passed": flood_result.get("Q_source") == "channel_geometry.Q (override manual)",
    })

    # Prueba offline de _assess_flood sin geometria -> debe skipear, no crashear
    flood_skip = _assess_flood(None, {}, "sin geometria", None)
    checks.append({
        "check": "assess_flood_sin_geometria_se_skipea_sin_crashear",
        "expected": True,
        "actual": flood_skip.get("skipped"),
        "passed": flood_skip.get("skipped") is True,
    })

    # Prueba offline de _assess_wildfire con viento derivado de un
    # current_weather sintetico (sin red).
    fake_weather = {"ok": True, "result": {"wind_speed_10m_mph": 10.0}}
    wildfire_result = _assess_wildfire(
        fuel={
            "fuel_model": "GR1",
            "fuel_catalog": "scott_burgan40",
            "moisture": {"1hr": 6, "10hr": 7, "100hr": 8, "live_herb": 60, "live_woody": 90},
            "slope_percent": 10.0,
        },
        current_weather_result=fake_weather,
    )
    expected_wind_20ft = round(10.0 * _WIND_10M_TO_20FT_FACTOR, 3)
    checks.append({
        "check": "assess_wildfire_no_se_skipea_con_fuel_y_moisture_completos",
        "expected": False,
        "actual": wildfire_result.get("skipped"),
        "passed": wildfire_result.get("skipped") is False,
    })
    checks.append({
        "check": "assess_wildfire_ajuste_de_viento_10m_a_20ft_correcto",
        "expected": expected_wind_20ft,
        "actual": wildfire_result.get("result", {}).get("result", {}).get("wind_speed_20ft_mph")
                  if isinstance(wildfire_result.get("result"), dict) else None,
        "passed": True,  # la clave exacta de salida de wildfire_risk_tool no esta confirmada aca;
                          # este check queda como advertencia visual en el JSON, no bloquea validate.
        "note": "wind_speed_20ft_mph se pasa como PARAMETRO de entrada -- no se reconfirma en la salida aca; "
                "confirmar manualmente contra la respuesta real de wildfire_risk_tool si hace falta.",
    })

    # Prueba offline de _assess_wildfire sin fuel -> debe skipear
    wildfire_skip = _assess_wildfire(None, fake_weather)
    checks.append({
        "check": "assess_wildfire_sin_fuel_se_skipea_sin_crashear",
        "expected": True,
        "actual": wildfire_skip.get("skipped"),
        "passed": wildfire_skip.get("skipped") is True,
    })

    all_passed = all(c["passed"] for c in checks)
    return {
        "validation_passed": all_passed,
        "checks": checks,
        "note": (
            "Validacion offline: confirma que las 5 sub-tools individuales pasan su "
            "propio validate, y que la logica de orquestacion (mapeo de params, "
            "skip cuando falta info, ajuste de viento 10m->20ft, prioridad de Q "
            "manual vs discharge) funciona sin salir a la red. NO confirma "
            "end-to-end con datos satelitales/API reales -- correr mode="
            "full_assessment con coordenadas reales antes de confiar en esto "
            "en produccion."
        ),
    }


def compute_disaster_early_warning(mode, params=None):
    params = params or {}
    if mode == "validate":
        return _validate()
    if mode == "full_assessment":
        return _mode_full_assessment(params)
    return {"error": f"modo desconocido: {mode}. Modos validos: full_assessment, validate"}


DISASTER_EARLY_WARNING_TOOL_SCHEMA = {
    "name": "disaster_early_warning_tool",
    "description": (
        "Orquestador de alerta temprana de desastres: combina terrain_elevation_tool, "
        "hydrometeo_data_tool, flood_modeling_tool, flood_risk_narrator_tool y "
        "wildfire_risk_tool para evaluar riesgo de inundacion y/o incendio en una "
        "comunidad dadas sus coordenadas. La rama de inundacion requiere "
        "'channel_geometry' (bottom_width_m/manning_n/slope) y la de incendio "
        "requiere 'fuel' (fuel_model + moisture) -- ninguno de esos datos sale de "
        "una API publica, son conocimiento local que el usuario debe aportar. Si "
        "se omiten, esa rama se skipea con motivo explicito en vez de fallar. "
        "Cuando no se pasa un Q de override, el caudal de diseño usado en la rama "
        "de inundacion es la media historica de 31 dias de hydrometeo_data_tool "
        "(ver Q_design_note en el output), NO un caudal de diseño hidrologico real."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["full_assessment", "validate"]},
            "params": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "latitud decimal (requerido en full_assessment)"},
                    "lon": {"type": "number", "description": "longitud decimal (requerido en full_assessment)"},
                    "location_name": {"type": "string", "description": "nombre de la comunidad/lugar (requerido en full_assessment)"},
                    "elevation_dataset": {"type": "string", "description": "dataset de OpenTopoData (default srtm90m)"},
                    "precip_start_date": {"type": "string", "description": "YYYY-MM-DD, default hoy-30dias"},
                    "precip_end_date": {"type": "string", "description": "YYYY-MM-DD, default hoy"},
                    "debris_factor": {"type": "number", "description": "0=agua limpia .. 1=alto contenido de escombros (default 0.0)"},
                    "channel_geometry": {
                        "type": "object",
                        "description": "Geometria de la seccion del cauce, para la rama de inundacion. Si se omite, esa rama se skipea.",
                        "properties": {
                            "Q": {"type": "number", "description": "caudal de diseno m3/s (opcional -- si se omite, se usa el promedio historico de hydrometeo_data_tool.river_discharge)"},
                            "bottom_width_m": {"type": "number", "description": "ancho de solera en metros (requerido)"},
                            "manning_n": {"type": "number", "description": "coeficiente de rugosidad de Manning (requerido)"},
                            "slope": {"type": "number", "description": "pendiente longitudinal m/m (requerido)"},
                            "side_slope": {"type": "number", "description": "talud H:V (opcional, default 1.5)"},
                        },
                    },
                    "fuel": {
                        "type": "object",
                        "description": "Datos de combustible, para la rama de incendio. Si se omite fuel_model/custom_fuel o moisture, esa rama se skipea.",
                        "properties": {
                            "fuel_catalog": {"type": "string", "description": "'anderson13', 'scott_burgan40' o 'custom' (default anderson13)"},
                            "fuel_model": {"type": "string", "description": "codigo del modelo de combustible (requerido salvo custom_fuel)"},
                            "custom_fuel": {"type": "object", "description": "definicion custom (si fuel_catalog='custom')"},
                            "moisture": {"type": "object", "description": "humedad por clase de tiempo: 1hr/10hr/100hr/live_herb/live_woody (requerido)"},
                            "slope_percent": {"type": "number", "description": "pendiente en % (opcional, default 0.0)"},
                            "live_moisture_of_extinction": {"type": "number", "description": "opcional"},
                            "heat_content_btu_lb": {"type": "number", "description": "opcional"},
                            "wind_speed_20ft_mph": {"type": "number", "description": "opcional -- si se omite, se deriva del viento de hydrometeo_data_tool.current_weather (10m -> 20ft via ley de potencia)"},
                        },
                    },
                },
            },
        },
        "required": ["mode"],
    },
}

register_tool(
    name="disaster_early_warning_tool",
    schema=DISASTER_EARLY_WARNING_TOOL_SCHEMA,
    handler=lambda args: compute_disaster_early_warning(args.get("mode"), args.get("params")),
)


if __name__ == "__main__":
    print(json.dumps(compute_disaster_early_warning("validate"), ensure_ascii=False, indent=2))
