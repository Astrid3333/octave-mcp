"""
hydrometeo_data_tool.py

Capa de datos publicos de lluvia y caudal de rios, via Open-Meteo
(APIs publicas, sin API key, cobertura global) -- mismo espiritu que
terrain_elevation_tool.py usando OpenTopoData para elevacion real.

Dos fuentes:
  - archive-api.open-meteo.com: historico de precipitacion diaria
    (reanalisis ERA5, cobertura global, desde 1940)
  - flood-api.open-meteo.com: caudal de rios historico y pronosticado
    (basado en el modelo GloFAS de Copernicus, resolucion ~5km;
    rios muy chicos pueden no tener celda de grilla cerca -- por eso
    el summary de discharge devuelve un "warning" explicito en vez
    de fallar en silencio cuando la respuesta viene vacia)

IMPORTANTE -- sin probar en vivo: el sandbox donde se escribio este
archivo no tiene salida de red a estos dominios (allowlist
restringido a paquetes/GitHub), asi que se valido con la logica de
parseo/agregacion aislada de la llamada HTTP real (mode=validate usa
una respuesta mockeada con la forma documentada de la API, sin tocar
la red). Antes de dar esto por confirmado end-to-end hace falta un
smoke test real con mode=precipitation_history / mode=river_discharge
contra coordenadas conocidas, para confirmar que el schema de
respuesta de Open-Meteo no cambio.
"""

import json
import urllib.request
import urllib.error
from datetime import date, timedelta

from tool_registry import register_tool

ARCHIVE_API_URL = "https://archive-api.open-meteo.com/v1/archive"
FLOOD_API_URL = "https://flood-api.open-meteo.com/v1/flood"
FORECAST_API_URL = "https://api.open-meteo.com/v1/forecast"


def _http_get_json(url, params, timeout=20):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    full_url = f"{url}?{query}"
    req = urllib.request.Request(full_url, headers={"User-Agent": "octave-mcp/hydrometeo_data_tool"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _summarize_precipitation(data):
    daily = data.get("daily", {})
    dates = daily.get("time", [])
    raw_values = daily.get("precipitation_sum", [])
    values = [v if v is not None else 0.0 for v in raw_values]
    n = len(values)
    total = sum(values)
    return {
        "source": "open-meteo archive api (ERA5 reanalysis)",
        "n_days": n,
        "total_mm": round(total, 2),
        "mean_daily_mm": round(total / n, 2) if n else 0.0,
        "max_daily_mm": round(max(values), 2) if values else 0.0,
        "max_daily_date": dates[values.index(max(values))] if values else None,
        "daily": [{"date": d, "precipitation_mm": v} for d, v in zip(dates, values)],
    }


def _summarize_discharge(data):
    daily = data.get("daily", {})
    dates = daily.get("time", [])
    raw_values = daily.get("river_discharge", [])
    paired = [(d, v) for d, v in zip(dates, raw_values) if v is not None]
    if not paired:
        return {
            "source": "open-meteo flood api (GloFAS)",
            "n_days": 0,
            "warning": (
                "sin datos de caudal para esta ubicacion -- probablemente no hay "
                "celda de grilla GloFAS cerca (rio muy chico o coordenada fuera "
                "de la red hidrografica modelada), no un error de la llamada"
            ),
        }
    dates_clean, values = zip(*paired)
    n = len(values)
    return {
        "source": "open-meteo flood api (GloFAS)",
        "n_days": n,
        "mean_discharge_m3s": round(sum(values) / n, 3),
        "max_discharge_m3s": round(max(values), 3),
        "min_discharge_m3s": round(min(values), 3),
        "daily": [{"date": d, "discharge_m3s": v} for d, v in zip(dates_clean, values)],
    }


def _summarize_current_weather(data):
    current = data.get("current", {})
    units = data.get("current_units", {})
    wind_kmh = current.get("wind_speed_10m")
    return {
        "source": "open-meteo forecast api (current conditions)",
        "time": current.get("time"),
        "wind_speed_10m_kmh": wind_kmh,
        "wind_speed_10m_mph": round(wind_kmh * 0.621371, 2) if wind_kmh is not None else None,
        "wind_direction_10m_deg": current.get("wind_direction_10m"),
        "relative_humidity_2m_pct": current.get("relative_humidity_2m"),
        "temperature_2m_c": current.get("temperature_2m"),
        "units_raw": units,
    }


def _fetch_precipitation_history(lat, lon, start_date, end_date):
    data = _http_get_json(ARCHIVE_API_URL, {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": "precipitation_sum",
        "timezone": "auto",
    })
    return _summarize_precipitation(data)


def _fetch_river_discharge(lat, lon, start_date, end_date):
    data = _http_get_json(FLOOD_API_URL, {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": "river_discharge",
    })
    return _summarize_discharge(data)


def _fetch_current_weather(lat, lon):
    data = _http_get_json(FORECAST_API_URL, {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m",
        "timezone": "auto",
    })
    return _summarize_current_weather(data)


def _mock_precipitation_response():
    # Forma documentada de archive-api.open-meteo.com (daily.precipitation_sum)
    return {
        "daily": {
            "time": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "precipitation_sum": [0.0, 12.4, 3.1],
        }
    }


def _mock_discharge_response():
    return {
        "daily": {
            "time": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "river_discharge": [45.2, 47.8, 44.9],
        }
    }


def _mock_current_weather_response():
    # Forma documentada de api.open-meteo.com/v1/forecast con "current="
    return {
        "current": {
            "time": "2026-08-19T15:00",
            "temperature_2m": 22.5,
            "relative_humidity_2m": 38,
            "wind_speed_10m": 18.0,
            "wind_direction_10m": 270,
        },
        "current_units": {"wind_speed_10m": "km/h", "relative_humidity_2m": "%"},
    }


def _validate():
    checks = []

    precip = _summarize_precipitation(_mock_precipitation_response())
    expected_total = round(0.0 + 12.4 + 3.1, 2)
    checks.append({
        "check": "precipitation_total_mm_suma_correcta",
        "expected": expected_total,
        "actual": precip["total_mm"],
        "passed": abs(precip["total_mm"] - expected_total) < 1e-6,
    })
    checks.append({
        "check": "precipitation_max_day_es_el_dia_correcto",
        "expected": "2026-01-02",
        "actual": precip["max_daily_date"],
        "passed": precip["max_daily_date"] == "2026-01-02",
    })

    discharge = _summarize_discharge(_mock_discharge_response())
    expected_mean = round((45.2 + 47.8 + 44.9) / 3, 3)
    checks.append({
        "check": "discharge_mean_correcto",
        "expected": expected_mean,
        "actual": discharge["mean_discharge_m3s"],
        "passed": abs(discharge["mean_discharge_m3s"] - expected_mean) < 1e-6,
    })

    empty = _summarize_discharge({"daily": {"time": [], "river_discharge": []}})
    checks.append({
        "check": "discharge_vacio_da_warning_no_crash",
        "expected": "n_days=0 con warning presente",
        "actual": f"n_days={empty['n_days']}, warning_presente={'warning' in empty}",
        "passed": empty["n_days"] == 0 and "warning" in empty,
    })

    con_nulos = _summarize_precipitation({
        "daily": {"time": ["a", "b", "c"], "precipitation_sum": [1.0, None, 3.0]}
    })
    checks.append({
        "check": "precipitation_tolera_valores_null_de_la_api",
        "expected": 4.0,
        "actual": con_nulos["total_mm"],
        "passed": abs(con_nulos["total_mm"] - 4.0) < 1e-6,
    })

    weather = _summarize_current_weather(_mock_current_weather_response())
    checks.append({
        "check": "current_weather_wind_kmh_a_mph_correcto",
        "expected": round(18.0 * 0.621371, 2),
        "actual": weather["wind_speed_10m_mph"],
        "passed": abs(weather["wind_speed_10m_mph"] - round(18.0 * 0.621371, 2)) < 1e-6,
    })
    checks.append({
        "check": "current_weather_humidity_pasa_directo",
        "expected": 38,
        "actual": weather["relative_humidity_2m_pct"],
        "passed": weather["relative_humidity_2m_pct"] == 38,
    })

    all_passed = all(c["passed"] for c in checks)
    return {
        "validation_passed": all_passed,
        "checks": checks,
        "note": (
            "Validacion offline con respuestas mockeadas -- confirma la logica de "
            "parseo/agregacion, NO confirma que las APIs reales de Open-Meteo "
            "respondan hoy con este mismo schema (sin salida de red a open-meteo.com "
            "desde este sandbox). Correr mode=precipitation_history / "
            "mode=river_discharge con coordenadas reales antes de confiar en esto "
            "end-to-end."
        ),
    }


def compute_hydrometeo_data(mode, params=None):
    params = params or {}

    if mode == "validate":
        return _validate()

    if mode in ("precipitation_history", "river_discharge"):
        lat = params.get("lat")
        lon = params.get("lon")
        if lat is None or lon is None:
            return {"error": "faltan params requeridos: lat, lon"}
        end = params.get("end_date") or date.today().isoformat()
        start = params.get("start_date") or (date.today() - timedelta(days=30)).isoformat()
        try:
            if mode == "precipitation_history":
                return _fetch_precipitation_history(lat, lon, start, end)
            return _fetch_river_discharge(lat, lon, start, end)
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            return {"error": f"fallo la llamada a Open-Meteo ({mode}): {e}"}

    if mode == "current_weather":
        lat = params.get("lat")
        lon = params.get("lon")
        if lat is None or lon is None:
            return {"error": "faltan params requeridos: lat, lon"}
        try:
            return _fetch_current_weather(lat, lon)
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            return {"error": f"fallo la llamada a Open-Meteo (current_weather): {e}"}

    return {
        "error": f"modo desconocido: {mode}. Modos validos: precipitation_history, river_discharge, current_weather, validate"
    }


HYDROMETEO_DATA_TOOL_SCHEMA = {
    "name": "hydrometeo_data",
    "description": (
        "Datos publicos de lluvia (historico diario, ERA5 reanalysis via Open-Meteo), "
        "caudal de rios (historico via modelo GloFAS, Open-Meteo Flood API), y clima "
        "actual (viento/humedad/temperatura via Open-Meteo Forecast API), sin API key. "
        "Pensada para alimentar flood_modeling_tool / water_resource_tool / "
        "wildfire_risk_tool con datos reales en vez de valores puestos a mano."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["precipitation_history", "river_discharge", "current_weather", "validate"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "latitud decimal"},
                    "lon": {"type": "number", "description": "longitud decimal"},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD, default hoy-30dias"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD, default hoy"},
                },
            },
        },
        "required": ["mode"],
    },
}

register_tool(
    name="hydrometeo_data",
    schema=HYDROMETEO_DATA_TOOL_SCHEMA,
    handler=lambda args: compute_hydrometeo_data(args.get("mode"), args.get("params")),
)


if __name__ == "__main__":
    print(json.dumps(compute_hydrometeo_data("validate"), ensure_ascii=False, indent=2))
