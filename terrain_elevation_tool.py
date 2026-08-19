"""
terrain_elevation_tool.py

Consulta elevacion real del terreno via OpenTopoData (API publica, sin
API key, servidor default: https://api.opentopodata.org).

Modos:
  - elevation_lookup: llamada de red real. Devuelve elevacion (m) para
    una lista de puntos [lat, lon]. Batching automatico a <=100 puntos
    por request (limite del servidor publico), con pausa de 1s entre
    batches (limite de 1 req/seg del servidor publico). Requiere
    conectividad a api.opentopodata.org -- no disponible en el sandbox
    de red de Claude, correr desde la maquina del usuario.
  - validate: NO hace ninguna llamada de red. Verifica la logica de
    batching/parseo/reconstruccion de orden contra respuestas JSON de
    ejemplo (formato real documentado de OpenTopoData), hardcodeadas
    en este archivo. Mantiene el pre-push hook offline y determinista,
    igual que el resto del repo.

confidence_flag en elevation_lookup: "elevacion real de terreno, pero
no verificada independientemente contra una segunda fuente -- depende
de la exactitud del dataset de OpenTopoData (default srtm90m, ~90m de
resolucion horizontal) y de que el servicio publico este disponible en
el momento de la consulta."
"""

import json
import time
import urllib.request
import urllib.error


OPENTOPODATA_BASE_URL = "https://api.opentopodata.org/v1"
MAX_LOCATIONS_PER_REQUEST = 100
RATE_LIMIT_SLEEP_SECONDS = 1.0


# ---------------------------------------------------------------------------
# Logica pura (testeable offline, sin red) -- separada de la llamada HTTP
# ---------------------------------------------------------------------------

def _build_locations_param(batch):
    """batch: lista de (lat, lon) -> string 'lat,lon|lat,lon|...'"""
    return "|".join(f"{lat},{lon}" for lat, lon in batch)


def _chunk_locations(locations, size=MAX_LOCATIONS_PER_REQUEST):
    for i in range(0, len(locations), size):
        yield locations[i:i + size]


def _parse_opentopodata_response(response_json, expected_n):
    """Extrae elevaciones en orden desde un dict ya parseado de JSON
    con el formato real de OpenTopoData. Levanta ValueError si el
    status no es OK o si la cantidad de resultados no coincide."""
    status = response_json.get("status")
    if status != "OK":
        raise ValueError(f"OpenTopoData devolvio status={status!r}: {response_json.get('error', 'sin detalle')}")
    results = response_json.get("results", [])
    if len(results) != expected_n:
        raise ValueError(f"se esperaban {expected_n} resultados, llegaron {len(results)}")
    elevations = []
    for r in results:
        elev = r.get("elevation")
        elevations.append(elev)  # puede ser None si el dataset no cubre ese punto
    return elevations


def _elevations_for_locations(locations, dataset, fetch_fn):
    """locations: lista de (lat, lon). fetch_fn(url) -> dict ya parseado
    de JSON (permite inyectar un mock en validate() sin tocar la red)."""
    all_elevations = []
    batches = list(_chunk_locations(locations))
    for i, batch in enumerate(batches):
        locs_param = _build_locations_param(batch)
        url = f"{OPENTOPODATA_BASE_URL}/{dataset}?locations={locs_param}"
        response_json = fetch_fn(url)
        batch_elevations = _parse_opentopodata_response(response_json, len(batch))
        all_elevations.extend(batch_elevations)
        if i < len(batches) - 1:
            time.sleep(RATE_LIMIT_SLEEP_SECONDS)
    return all_elevations


# ---------------------------------------------------------------------------
# Llamada de red real (solo usada en elevation_lookup, nunca en validate)
# ---------------------------------------------------------------------------

def _http_fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "octave-mcp/terrain_elevation_tool"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            raise ValueError(f"HTTP {e.code} de OpenTopoData, respuesta no-JSON: {body[:200]}")
    except urllib.error.URLError as e:
        raise ValueError(f"no se pudo conectar a OpenTopoData: {e.reason}")
    return json.loads(body)


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------

def _elevation_lookup(params):
    locations_raw = params.get("locations")
    if not locations_raw:
        raise ValueError("params['locations'] es requerido: lista de [lat, lon]")
    locations = [(float(lat), float(lon)) for lat, lon in locations_raw]
    dataset = params.get("dataset", "srtm90m")

    elevations = _elevations_for_locations(locations, dataset, _http_fetch_json)

    return {
        "locations": [{"lat": lat, "lon": lon} for lat, lon in locations],
        "elevations_m": elevations,
        "dataset": dataset,
        "n_points": len(locations),
        "n_batches": len(list(_chunk_locations(locations))),
        "confidence_flag": (
            "elevacion real de terreno, pero no verificada independientemente "
            "contra una segunda fuente -- depende de la exactitud del dataset "
            f"'{dataset}' de OpenTopoData y de que el servicio publico este "
            "disponible en el momento de la consulta."
        ),
    }


# JSON de ejemplo con el formato real documentado de OpenTopoData
# (https://www.opentopodata.org/#example-request), usado SOLO para
# validate() -- nunca se llama a la red real desde aca.
_EXAMPLE_RESPONSE_OK = {
    "status": "OK",
    "results": [
        {"elevation": 1608.0, "location": {"lat": 40.7, "lng": -74.0}, "dataset": "srtm90m"},
        {"elevation": 4632.0, "location": {"lat": 46.8, "lng": 10.3}, "dataset": "srtm90m"},
    ],
}

_EXAMPLE_RESPONSE_OCEAN = {
    "status": "OK",
    "results": [
        {"elevation": None, "location": {"lat": 0.0, "lng": -160.0}, "dataset": "srtm90m"},
    ],
}

_EXAMPLE_RESPONSE_ERROR = {
    "status": "INVALID_REQUEST",
    "error": "lat must be in range -90 to 90",
}


def _validate():
    checks = []

    try:
        elevs = _parse_opentopodata_response(_EXAMPLE_RESPONSE_OK, expected_n=2)
        ok = elevs == [1608.0, 4632.0]
        checks.append({"nombre": "parseo_basico_orden_preservado", "paso": ok, "detalle": {"elevations": elevs}})
    except Exception as e:
        checks.append({"nombre": "parseo_basico_orden_preservado", "paso": False, "detalle": {"error": str(e)}})

    try:
        elevs = _parse_opentopodata_response(_EXAMPLE_RESPONSE_OCEAN, expected_n=1)
        ok = elevs == [None]
        checks.append({"nombre": "elevacion_none_no_rompe_parseo", "paso": ok, "detalle": {"elevations": elevs}})
    except Exception as e:
        checks.append({"nombre": "elevacion_none_no_rompe_parseo", "paso": False, "detalle": {"error": str(e)}})

    try:
        _parse_opentopodata_response(_EXAMPLE_RESPONSE_ERROR, expected_n=1)
        checks.append({"nombre": "status_error_levanta_valueerror", "paso": False, "detalle": {"error": "no levanto excepcion"}})
    except ValueError as e:
        checks.append({"nombre": "status_error_levanta_valueerror", "paso": True, "detalle": {"mensaje": str(e)}})

    try:
        _parse_opentopodata_response(_EXAMPLE_RESPONSE_OK, expected_n=5)
        checks.append({"nombre": "mismatch_cantidad_levanta_valueerror", "paso": False, "detalle": {"error": "no levanto excepcion"}})
    except ValueError as e:
        checks.append({"nombre": "mismatch_cantidad_levanta_valueerror", "paso": True, "detalle": {"mensaje": str(e)}})

    locations_250 = [(float(i % 90), float(i % 180)) for i in range(250)]
    batches = list(_chunk_locations(locations_250))
    ok = [len(b) for b in batches] == [100, 100, 50]
    checks.append({"nombre": "batching_250_puntos_100_100_50", "paso": ok, "detalle": {"tamanos": [len(b) for b in batches]}})

    calls = []

    def _mock_fetch(url):
        calls.append(url)
        n_locs_in_url = url.split("locations=")[1].count("|") + 1
        return {
            "status": "OK",
            "results": [{"elevation": float(idx), "location": {}} for idx in range(n_locs_in_url)],
        }

    locations_5 = [(float(i), float(i)) for i in range(5)]
    elevs = _elevations_for_locations(locations_5, "srtm90m", _mock_fetch)
    ok = elevs == [0.0, 1.0, 2.0, 3.0, 4.0] and len(calls) == 1
    checks.append({"nombre": "elevations_for_locations_batch_unico_orden_ok", "paso": ok, "detalle": {"elevations": elevs, "n_calls": len(calls)}})

    calls_multi = []

    def _mock_fetch_multi(url):
        calls_multi.append(url)
        n_locs_in_url = url.split("locations=")[1].count("|") + 1
        base = len(calls_multi) - 1
        return {
            "status": "OK",
            "results": [{"elevation": float(base * 1000 + idx), "location": {}} for idx in range(n_locs_in_url)],
        }

    locations_150 = [(float(i), float(i)) for i in range(150)]
    elevs = _elevations_for_locations(locations_150, "srtm90m", _mock_fetch_multi)
    ok = (
        len(elevs) == 150
        and elevs[:100] == [float(i) for i in range(100)]
        and elevs[100:] == [float(1000 + i) for i in range(50)]
        and len(calls_multi) == 2
    )
    checks.append({"nombre": "multi_batch_concatenacion_orden_correcto", "paso": ok, "detalle": {"n_elevations": len(elevs), "n_calls": len(calls_multi)}})

    todos_pasaron = all(c["paso"] for c in checks)
    return {"checks": checks, "todos_pasaron": todos_pasaron, "validation_passed": todos_pasaron}


def compute_terrain_elevation(mode, params=None):
    params = params or {}
    if mode == "elevation_lookup":
        return _elevation_lookup(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"modo desconocido: {mode!r}. Modos validos: elevation_lookup, validate")


TERRAIN_ELEVATION_TOOL_SCHEMA = {
    "name": "terrain_elevation_tool",
    "description": (
        "Consulta elevacion real del terreno via OpenTopoData (API publica "
        "gratuita, sin API key, dataset default srtm90m ~90m de resolucion). "
        "Modo 'elevation_lookup' hace una llamada de red real (requiere "
        "conectividad a api.opentopodata.org). Modo 'validate' NO llama a la "
        "red -- verifica la logica de batching/parseo offline contra "
        "respuestas de ejemplo, para mantener el pre-push hook determinista. "
        "Pensado para alimentar 'elevations' en flood_connectivity_tool con "
        "datos reales en vez de sinteticos."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["elevation_lookup", "validate"]},
            "params": {
                "type": "object",
                "properties": {
                    "locations": {
                        "type": "array",
                        "description": "Lista de [lat, lon] en grados decimales. Ej: [[40.7, -74.0], [46.8, 10.3]]",
                        "items": {"type": "array", "items": {"type": "number"}},
                    },
                    "dataset": {
                        "type": "string",
                        "default": "srtm90m",
                        "description": "Dataset de OpenTopoData (srtm90m, srtm30m, aster30m, etc. -- ver opentopodata.org/datasets)",
                    },
                },
            },
        },
        "required": ["mode"],
    },
}


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass


def _handle(args):
    return compute_terrain_elevation(args.get("mode"), args.get("params"))


register_tool("terrain_elevation_tool", TERRAIN_ELEVATION_TOOL_SCHEMA, _handle)


if __name__ == "__main__":
    print(json.dumps(compute_terrain_elevation("validate"), indent=2))
