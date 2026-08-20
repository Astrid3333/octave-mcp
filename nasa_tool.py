"""
nasa_tool.py

Cliente de las APIs publicas de NASA (api.nasa.gov). Segunda de las APIs
externas priorizadas (arXiv ya hecho / CERN / NASA) -- se eligio NASA
sobre CERN por volumen de datos: el archivo EOSDIS de NASA ronda las
70+ PB hoy (proyectado a 247+ PB para 2025) contra los ~5 PB del portal
de CERN Open Data.

Sin dependencias nuevas: urllib.request + json (stdlib). Mismo patron de
force_ipv4 que arxiv_tool.py, por si la ruta IPv6 rota en la red de
Astrid tambien afecta a api.nasa.gov (host distinto, red distinta,
mejor no asumir que el fix de un host aplica al otro sin poder probarlo).

Endpoints cubiertos (los mas utiles para uso ad-hoc, no la totalidad
de la API de NASA que es enorme):
  - apod: Astronomy Picture of the Day (por fecha o rango de fechas)
  - mars_rover_photos: fotos de Curiosity/Opportunity/Spirit/Perseverance
    por sol (dia marciano) o fecha terrestre, con filtro de camara
  - neo_feed: Near Earth Objects (asteroides) que pasan cerca de la
    Tierra en un rango de fechas (max 7 dias por limite de la API)
  - epic: imagenes de la Tierra completa desde el satelite DSCOVR

API key: usa 'DEMO_KEY' por default si no se pasa una (rate limit muy
bajo, ~30/hora -- suficiente para probar, Astrid puede pedir su propia
key gratis en api.nasa.gov/ para uso real).

Modo validate: offline, con fixtures JSON fijos (mismo criterio que
arxiv_tool -- el self-test no depende de la red real).
"""

import csv
import json
import socket
import urllib.error
import urllib.parse
import urllib.request

try:
    from tool_registry import register_tool
except ImportError:
    register_tool = None


BASE_URL = "https://api.nasa.gov"

# FIRMS vive en un host y un sistema de auth totalmente distintos de
# api.nasa.gov (MAP_KEY propia, se pide en firms.modaps.eosdis.nasa.gov/api/map_key/,
# no sirve el api_key de arriba). Y a diferencia de todo lo demas en este
# archivo, el endpoint de area devuelve CSV plano, no JSON -- por eso
# _fetch_text existe aparte de _fetch_json en vez de reusarlo.
FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

NASA_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["apod", "mars_rover_photos", "neo_feed", "epic", "active_fire_detections", "validate"],
        },
        "api_key": {"type": "string", "description": "API key de api.nasa.gov. Default: DEMO_KEY (rate limit bajo). NO sirve para active_fire_detections -- ver firms_map_key."},
        "firms_map_key": {"type": "string", "description": "MAP_KEY de FIRMS (firms.modaps.eosdis.nasa.gov/api/map_key/), separada del sistema de keys de api.nasa.gov. Requerida en mode=active_fire_detections."},
        "area": {"type": "string", "description": "Bounding box 'west,south,east,north' en grados decimales, o 'world'. Requerido en mode=active_fire_detections."},
        "source": {
            "type": "string",
            "enum": ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT"],
            "description": "Fuente satelital en mode=active_fire_detections. Default: VIIRS_SNPP_NRT.",
        },
        "day_range": {"type": "integer", "description": "Dias hacia atras desde 'date' (o desde hoy), 1-10. Usado por active_fire_detections. Default: 1."},
        "date": {"type": "string", "description": "Fecha YYYY-MM-DD. Usado por apod (un dia), mars_rover_photos (earth_date) y active_fire_detections (fin del rango, opcional, default hoy/ultimo dia disponible)."},
        "start_date": {"type": "string", "description": "YYYY-MM-DD. Usado por apod (rango) y neo_feed (requerido)."},
        "end_date": {"type": "string", "description": "YYYY-MM-DD. Usado por apod (rango) y neo_feed (max 7 dias desde start_date)."},
        "rover": {
            "type": "string",
            "enum": ["curiosity", "opportunity", "spirit", "perseverance"],
            "description": "Requerido en mode=mars_rover_photos.",
        },
        "sol": {"type": "integer", "description": "Dia marciano desde el aterrizaje. Alternativa a 'date' en mars_rover_photos."},
        "camera": {"type": "string", "description": "Filtro de camara opcional (ej: 'FHAZ', 'NAVCAM') en mars_rover_photos."},
        "epic_type": {"type": "string", "enum": ["natural", "enhanced"], "description": "Usado por epic (default natural)."},
        "timeout": {"type": "number", "description": "Timeout de red en segundos (default 15)."},
        "force_ipv4": {
            "type": "boolean",
            "description": "Si true, resuelve solo A records (IPv4). Ver nota en arxiv_tool.py sobre por que existe esta opcion.",
        },
    },
    "required": ["mode"],
}


# --------------------------------------------------------------------- io --

def _fetch_json(url, timeout, force_ipv4=False):
    req = urllib.request.Request(url, headers={"User-Agent": "octave-mcp/nasa_tool"})
    if force_ipv4:
        original_getaddrinfo = socket.getaddrinfo

        def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

        socket.getaddrinfo = _ipv4_only_getaddrinfo
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        finally:
            socket.getaddrinfo = original_getaddrinfo
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _fetch_text(url, timeout, force_ipv4=False):
    req = urllib.request.Request(url, headers={"User-Agent": "octave-mcp/nasa_tool"})
    if force_ipv4:
        original_getaddrinfo = socket.getaddrinfo

        def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

        socket.getaddrinfo = _ipv4_only_getaddrinfo
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8")
        finally:
            socket.getaddrinfo = original_getaddrinfo
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _url(path, params):
    return f"{BASE_URL}{path}?" + urllib.parse.urlencode(params)


def _firms_url(map_key, source, area, day_range, date=None):
    path = f"{FIRMS_BASE_URL}/{map_key}/{source}/{area}/{day_range}"
    if date:
        path += f"/{date}"
    return path


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------ per-endpoint --

def _apod(args):
    params = {"api_key": args.get("api_key", "DEMO_KEY")}
    if args.get("start_date"):
        params["start_date"] = args["start_date"]
        if args.get("end_date"):
            params["end_date"] = args["end_date"]
    elif args.get("date"):
        params["date"] = args["date"]
    url = _url("/planetary/apod", params)
    data = _fetch_json(url, args.get("timeout", 15), args.get("force_ipv4", False))
    items = data if isinstance(data, list) else [data]
    return {
        "count": len(items),
        "items": [
            {
                "date": it.get("date"),
                "title": it.get("title"),
                "explanation": it.get("explanation"),
                "media_type": it.get("media_type"),
                "url": it.get("url"),
                "hdurl": it.get("hdurl"),
                "copyright": it.get("copyright"),
            }
            for it in items
        ],
    }


def _mars_rover_photos(args):
    if not args.get("rover"):
        return {"error": "mode=mars_rover_photos requiere 'rover'"}
    params = {"api_key": args.get("api_key", "DEMO_KEY")}
    if args.get("sol") is not None:
        params["sol"] = args["sol"]
    elif args.get("date"):
        params["earth_date"] = args["date"]
    else:
        params["sol"] = 1000
    if args.get("camera"):
        params["camera"] = args["camera"]
    url = _url(f"/mars-photos/api/v1/rovers/{args['rover']}/photos", params)
    data = _fetch_json(url, args.get("timeout", 15), args.get("force_ipv4", False))
    photos = data.get("photos", [])
    return {
        "count": len(photos),
        "photos": [
            {
                "id": p.get("id"),
                "sol": p.get("sol"),
                "earth_date": p.get("earth_date"),
                "camera": (p.get("camera") or {}).get("full_name"),
                "img_src": p.get("img_src"),
                "rover": (p.get("rover") or {}).get("name"),
                "rover_status": (p.get("rover") or {}).get("status"),
            }
            for p in photos
        ],
    }


def _neo_feed(args):
    if not args.get("start_date"):
        return {"error": "mode=neo_feed requiere 'start_date'"}
    params = {"api_key": args.get("api_key", "DEMO_KEY"), "start_date": args["start_date"]}
    if args.get("end_date"):
        params["end_date"] = args["end_date"]
    url = _url("/neo/rest/v1/feed", params)
    data = _fetch_json(url, args.get("timeout", 15), args.get("force_ipv4", False))
    by_date = data.get("near_earth_objects", {})
    objects = []
    for date, neos in by_date.items():
        for neo in neos:
            approach = (neo.get("close_approach_data") or [{}])[0]
            diameter = (neo.get("estimated_diameter") or {}).get("meters", {})
            objects.append({
                "date": date,
                "name": neo.get("name"),
                "id": neo.get("id"),
                "is_potentially_hazardous": neo.get("is_potentially_hazardous_asteroid"),
                "estimated_diameter_m_min": diameter.get("estimated_diameter_min"),
                "estimated_diameter_m_max": diameter.get("estimated_diameter_max"),
                "miss_distance_km": (approach.get("miss_distance") or {}).get("kilometers"),
                "relative_velocity_kmh": (approach.get("relative_velocity") or {}).get("kilometers_per_hour"),
            })
    return {
        "element_count": data.get("element_count", len(objects)),
        "objects": objects,
    }


def _epic(args):
    epic_type = args.get("epic_type", "natural")
    params = {"api_key": args.get("api_key", "DEMO_KEY")}
    path = f"/EPIC/api/{epic_type}"
    if args.get("date"):
        path += f"/date/{args['date']}"
    url = _url(path, params)
    data = _fetch_json(url, args.get("timeout", 15), args.get("force_ipv4", False))
    items = data if isinstance(data, list) else []
    results = []
    for it in items:
        d = (it.get("date") or "")[:10].replace("-", "/")
        image_name = it.get("image")
        img_url = None
        if d and image_name:
            img_url = f"https://api.nasa.gov/EPIC/archive/{epic_type}/{d}/png/{image_name}.png?api_key={params['api_key']}"
        results.append({
            "identifier": it.get("identifier"),
            "caption": it.get("caption"),
            "date": it.get("date"),
            "image_url": img_url,
        })
    return {"count": len(results), "images": results}


def _firms_active_fires(args):
    map_key = args.get("firms_map_key")
    if not map_key:
        return {"error": "mode=active_fire_detections requiere 'firms_map_key' (se registra aparte en firms.modaps.eosdis.nasa.gov/api/map_key/, no es el api_key de api.nasa.gov)"}
    area = args.get("area")
    if not area:
        return {"error": "mode=active_fire_detections requiere 'area' ('west,south,east,north' o 'world')"}
    source = args.get("source", "VIIRS_SNPP_NRT")
    day_range = args.get("day_range", 1)
    url = _firms_url(map_key, source, area, day_range, args.get("date"))
    text = _fetch_text(url, args.get("timeout", 15), args.get("force_ipv4", False))
    lines = text.strip().splitlines()
    if not lines or "latitude" not in lines[0].lower():
        # FIRMS devuelve texto plano (no CSV) en casos de error -- MAP_KEY
        # invalida, cuota diaria de transacciones agotada, parametros mal
        # formados. Este chequeo y el layout de columnas de abajo estan
        # armados de memoria: firms.modaps.eosdis.nasa.gov no esta en la
        # allowlist de red del sandbox de Claude, asi que nada de esto se
        # probo contra la API real todavia -- confirmar la primera vez que
        # corra con una MAP_KEY de verdad.
        return {"error": f"respuesta inesperada de FIRMS (no parece CSV valido, ¿MAP_KEY invalida o cuota agotada?): {text[:200]}"}
    reader = csv.DictReader(lines)
    detections = []
    for row in reader:
        detections.append({
            "latitude": _to_float(row.get("latitude")),
            "longitude": _to_float(row.get("longitude")),
            "brightness": _to_float(row.get("bright_ti4") or row.get("brightness")),
            "confidence": row.get("confidence"),
            "frp": _to_float(row.get("frp")),
            "acq_date": row.get("acq_date"),
            "acq_time": row.get("acq_time"),
            "satellite": row.get("satellite"),
            "daynight": row.get("daynight"),
        })
    return {
        "count": len(detections),
        "source": source,
        "area": area,
        "day_range": day_range,
        "detections": detections,
    }


# --------------------------------------------------------------- dispatch --

def compute_nasa(mode, args=None):
    args = args or {}

    if mode == "validate":
        return _validate()

    try:
        if mode == "apod":
            return _apod(args)
        if mode == "mars_rover_photos":
            return _mars_rover_photos(args)
        if mode == "neo_feed":
            return _neo_feed(args)
        if mode == "epic":
            return _epic(args)
        if mode == "active_fire_detections":
            return _firms_active_fires(args)
        return {"error": f"modo desconocido: {mode}"}
    except urllib.error.URLError as e:
        return {"error": f"fallo de red consultando NASA: {e}"}
    except json.JSONDecodeError as e:
        return {"error": f"respuesta de NASA no parseable como JSON: {e}"}


# ------------------------------------------------------------- self-test --

_APOD_FIXTURE = {
    "date": "2024-01-01",
    "title": "A Fake Nebula",
    "explanation": "This is a fake APOD explanation used only for offline validate mode.",
    "media_type": "image",
    "url": "https://example.invalid/apod.jpg",
    "hdurl": "https://example.invalid/apod_hd.jpg",
    "copyright": "Fake Observatory",
}

_MARS_FIXTURE = {
    "photos": [
        {
            "id": 424905,
            "sol": 1000,
            "earth_date": "2015-05-30",
            "camera": {"full_name": "Front Hazard Avoidance Camera"},
            "img_src": "https://example.invalid/mars1.jpg",
            "rover": {"name": "Curiosity", "status": "active"},
        }
    ]
}

_NEO_FIXTURE = {
    "element_count": 1,
    "near_earth_objects": {
        "2024-01-01": [
            {
                "id": "1234",
                "name": "Fake Asteroid (2024 AB)",
                "is_potentially_hazardous_asteroid": False,
                "estimated_diameter": {"meters": {"estimated_diameter_min": 10.0, "estimated_diameter_max": 22.0}},
                "close_approach_data": [
                    {
                        "miss_distance": {"kilometers": "1234567.0"},
                        "relative_velocity": {"kilometers_per_hour": "45000.0"},
                    }
                ],
            }
        ]
    },
}

_EPIC_FIXTURE = [
    {"identifier": "20240101000000", "caption": "Fake Earth full disk", "date": "2024-01-01 00:00:00", "image": "epic_1b_20240101000000"}
]

# CSV ficticio (coordenadas y valores inventados, no corresponden a un
# incendio real) para probar el parseo offline de active_fire_detections.
_FIRMS_FIXTURE_CSV = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_ti5,frp,daynight\n"
    "-33.010,-71.550,335.2,0.39,0.36,2024-01-01,0512,N,VIIRS,n,2.0NRT,289.1,4.8,D\n"
    "-33.040,-71.600,301.7,0.40,0.37,2024-01-01,0512,N,VIIRS,l,2.0NRT,285.0,1.2,D\n"
)


def _validate():
    checks = []

    # Parseamos los fixtures directamente contra la logica de normalizacion
    # de cada _endpoint (sin pasar por _fetch_json / red), monkeypatcheando
    # _fetch_json solo durante el self-test.
    global _fetch_json
    original_fetch = _fetch_json

    def _fake_fetch(url, timeout, force_ipv4=False):
        if "/planetary/apod" in url:
            return _APOD_FIXTURE
        if "/mars-photos/" in url:
            return _MARS_FIXTURE
        if "/neo/rest/v1/feed" in url:
            return _NEO_FIXTURE
        if "/EPIC/api/" in url:
            return _EPIC_FIXTURE
        raise AssertionError(f"URL inesperada en fixture: {url}")

    _fetch_json = _fake_fetch
    try:
        apod = compute_nasa("apod", {"date": "2024-01-01"})
        checks.append({"case": "apod: parsea titulo/url/media_type", "ok": apod["items"][0]["title"] == "A Fake Nebula" and apod["items"][0]["media_type"] == "image"})

        mars = compute_nasa("mars_rover_photos", {"rover": "curiosity", "sol": 1000})
        checks.append({"case": "mars_rover_photos: extrae camara y rover anidados", "ok": mars["photos"][0]["camera"] == "Front Hazard Avoidance Camera" and mars["photos"][0]["rover"] == "Curiosity"})

        missing_rover = compute_nasa("mars_rover_photos", {"sol": 1000})
        checks.append({"case": "mars_rover_photos sin 'rover' devuelve error explicito (sin red)", "ok": "error" in missing_rover})

        neo = compute_nasa("neo_feed", {"start_date": "2024-01-01"})
        checks.append({"case": "neo_feed: aplana near_earth_objects por fecha en lista", "ok": neo["element_count"] == 1 and neo["objects"][0]["name"] == "Fake Asteroid (2024 AB)"})
        checks.append({"case": "neo_feed: extrae miss_distance y diametro anidados", "ok": neo["objects"][0]["miss_distance_km"] == "1234567.0" and neo["objects"][0]["estimated_diameter_m_max"] == 22.0})

        missing_start = compute_nasa("neo_feed", {})
        checks.append({"case": "neo_feed sin 'start_date' devuelve error explicito (sin red)", "ok": "error" in missing_start})

        epic = compute_nasa("epic", {"date": "2024-01-01"})
        checks.append({"case": "epic: construye image_url a partir de date+image", "ok": epic["images"][0]["image_url"].startswith("https://api.nasa.gov/EPIC/archive/natural/2024/01/01/png/epic_1b_20240101000000.png")})
    finally:
        _fetch_json = original_fetch

    global _fetch_text
    original_fetch_text = _fetch_text

    def _fake_fetch_text(url, timeout, force_ipv4=False):
        if "/api/area/csv/" in url:
            return _FIRMS_FIXTURE_CSV
        raise AssertionError(f"URL inesperada en fixture (text): {url}")

    _fetch_text = _fake_fetch_text
    try:
        firms = compute_nasa("active_fire_detections", {"firms_map_key": "FAKEKEY123", "area": "-72,-34,-71,-33", "day_range": 1})
        checks.append({"case": "active_fire_detections: parsea lat/lon/confidence/frp del CSV", "ok": firms["count"] == 2 and firms["detections"][0]["confidence"] == "n" and firms["detections"][0]["frp"] == 4.8 and firms["detections"][0]["latitude"] == -33.010})

        missing_key = compute_nasa("active_fire_detections", {"area": "-72,-34,-71,-33"})
        checks.append({"case": "active_fire_detections sin 'firms_map_key' devuelve error explicito (sin red)", "ok": "error" in missing_key})

        missing_area = compute_nasa("active_fire_detections", {"firms_map_key": "FAKEKEY123"})
        checks.append({"case": "active_fire_detections sin 'area' devuelve error explicito (sin red)", "ok": "error" in missing_area})
    finally:
        _fetch_text = original_fetch_text

    url = _url("/planetary/apod", {"api_key": "DEMO_KEY", "date": "2024-01-01"})
    checks.append({"case": "build url: query codificada correctamente", "ok": "date=2024-01-01" in url and url.startswith(BASE_URL)})

    firms_url = _firms_url("FAKEKEY123", "VIIRS_SNPP_NRT", "-72,-34,-71,-33", 1)
    checks.append({"case": "firms url: arma el path MAP_KEY/source/area/day_range en orden", "ok": firms_url == f"{FIRMS_BASE_URL}/FAKEKEY123/VIIRS_SNPP_NRT/-72,-34,-71,-33/1"})

    all_passed = all(c["ok"] for c in checks)
    return {"validate": True, "all_passed": all_passed, "checks": checks}


if register_tool is not None:
    register_tool(
        name="nasa_tool",
        schema={
            "name": "nasa_tool",
            "description": (
                "Cliente de APIs publicas de NASA (api.nasa.gov). Modos: "
                "apod (foto astronomica del dia, por fecha o rango), "
                "mars_rover_photos (fotos de rovers marcianos por sol o "
                "fecha terrestre, con filtro de camara), neo_feed "
                "(asteroides cercanos a la Tierra en un rango de hasta 7 "
                "dias, con distancia y velocidad de aproximacion), epic "
                "(imagenes de disco completo de la Tierra desde DSCOVR), "
                "active_fire_detections (detecciones de incendios activos "
                "via FIRMS/VIIRS-MODIS en un bounding box, requiere "
                "firms_map_key propia -- MAP_KEY separada del sistema de "
                "api_key de arriba). Usa DEMO_KEY por default (rate limit "
                "bajo) para los demas modos; se puede pasar una api_key "
                "propia."
            ),
            "inputSchema": NASA_SCHEMA,
        },
        handler=lambda args: compute_nasa(args.get("mode"), args),
    )


if __name__ == "__main__":
    print(json.dumps(compute_nasa("validate"), indent=2, ensure_ascii=False))
