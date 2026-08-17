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

NASA_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["apod", "mars_rover_photos", "neo_feed", "epic", "validate"],
        },
        "api_key": {"type": "string", "description": "API key de api.nasa.gov. Default: DEMO_KEY (rate limit bajo)."},
        "date": {"type": "string", "description": "Fecha YYYY-MM-DD. Usado por apod (un dia) y mars_rover_photos (earth_date)."},
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


def _url(path, params):
    return f"{BASE_URL}{path}?" + urllib.parse.urlencode(params)


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

    url = _url("/planetary/apod", {"api_key": "DEMO_KEY", "date": "2024-01-01"})
    checks.append({"case": "build url: query codificada correctamente", "ok": "date=2024-01-01" in url and url.startswith(BASE_URL)})

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
                "(imagenes de disco completo de la Tierra desde DSCOVR). "
                "Usa DEMO_KEY por default (rate limit bajo); se puede pasar "
                "una api_key propia."
            ),
            "inputSchema": NASA_SCHEMA,
        },
        handler=lambda args: compute_nasa(args.get("mode"), args),
    )


if __name__ == "__main__":
    print(json.dumps(compute_nasa("validate"), indent=2, ensure_ascii=False))
