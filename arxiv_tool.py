"""
arxiv_tool.py

Cliente de la API publica de arXiv (export.arxiv.org/api/query, Atom XML,
sin API key). Primera de las 3 APIs externas priorizadas (arXiv / CERN
Open Data / NASA) -- se arranca por esta porque ya hay uso real en el
repo (cita a arXiv:1712.09676 en cosmological_mcmc_tool.py).

Sin dependencias nuevas: urllib.request + xml.etree.ElementTree (stdlib).
No requiere red para 'validate' -- el parser se prueba contra un fixture
Atom fijo embebido en el archivo, no contra la red real (mismo criterio
que "sin Octave" en otras tools: el self-test no debe depender de una
condicion externa que puede fallar por motivos ajenos al codigo).

Modos:
  - search: busca por query string (sintaxis de arXiv: "au:", "ti:",
    "abs:", "cat:", booleanos AND/OR/ANDNOT), con sort_by/sort_order y
    paginacion (start/max_results).
  - get_by_id: trae uno o mas papers por arXiv id (ej "1712.09676" o
    "1712.09676v2").
  - validate: prueba el parser Atom->dict contra un fixture fijo (sin
    red) + prueba de construccion de URL de query (sin red).
"""

import json
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

try:
    from tool_registry import register_tool
except ImportError:
    register_tool = None


BASE_URL = "http://export.arxiv.org/api/query"
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}

ARXIV_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": ["search", "get_by_id", "validate"]},
        "query": {
            "type": "string",
            "description": (
                "Query en sintaxis de arXiv (ej: 'au:Hawking AND cat:gr-qc', "
                "'ti:\"black hole\"'). Requerido en mode=search."
            ),
        },
        "id_list": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Lista de arXiv ids. Requerido en mode=get_by_id.",
        },
        "start": {"type": "integer", "description": "Offset de paginacion (default 0)."},
        "max_results": {"type": "integer", "description": "Maximo de resultados (default 10, cap 100)."},
        "sort_by": {
            "type": "string",
            "enum": ["relevance", "lastUpdatedDate", "submittedDate"],
            "description": "Solo aplica a mode=search (default relevance).",
        },
        "sort_order": {"type": "string", "enum": ["ascending", "descending"]},
        "timeout": {"type": "number", "description": "Timeout de red en segundos (default 15)."},
    },
    "required": ["mode"],
}


# ------------------------------------------------------------------ parse --

def _text(el, path):
    node = el.find(path, NS)
    return node.text.strip() if node is not None and node.text else None


def _parse_entry(entry):
    entry_id_raw = _text(entry, "atom:id") or ""
    m = re.search(r"arxiv\.org/abs/(.+)$", entry_id_raw)
    short_id = m.group(1) if m else entry_id_raw

    authors = [
        _text(a, "atom:name")
        for a in entry.findall("atom:author", NS)
        if _text(a, "atom:name")
    ]
    categories = [
        c.get("term")
        for c in entry.findall("atom:category", NS)
        if c.get("term")
    ]
    pdf_link = None
    for link in entry.findall("atom:link", NS):
        if link.get("title") == "pdf" or link.get("type") == "application/pdf":
            pdf_link = link.get("href")

    summary = _text(entry, "atom:summary")

    return {
        "id": short_id,
        "title": (_text(entry, "atom:title") or "").replace("\n", " ").strip(),
        "summary": summary.replace("\n", " ").strip() if summary else None,
        "authors": authors,
        "published": _text(entry, "atom:published"),
        "updated": _text(entry, "atom:updated"),
        "categories": categories,
        "primary_category": (
            entry.find("arxiv:primary_category", NS).get("term")
            if entry.find("arxiv:primary_category", NS) is not None
            else None
        ),
        "pdf_url": pdf_link,
        "abs_url": entry_id_raw or None,
        "doi": _text(entry, "arxiv:doi"),
        "comment": _text(entry, "arxiv:comment"),
    }


def _parse_feed(xml_bytes):
    root = ET.fromstring(xml_bytes)
    total_results = _text(root, "opensearch:totalResults")
    entries = [_parse_entry(e) for e in root.findall("atom:entry", NS)]
    return {
        "total_results": int(total_results) if total_results else None,
        "returned": len(entries),
        "papers": entries,
    }


# --------------------------------------------------------------------- io --

def _fetch(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "octave-mcp/arxiv_tool"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _build_search_url(args):
    params = {
        "search_query": args["query"],
        "start": args.get("start", 0),
        "max_results": min(args.get("max_results", 10), 100),
    }
    sort_by = args.get("sort_by")
    if sort_by:
        params["sortBy"] = sort_by
        params["sortOrder"] = args.get("sort_order", "descending")
    return BASE_URL + "?" + urllib.parse.urlencode(params)


def _build_id_url(args):
    ids = args.get("id_list") or []
    params = {"id_list": ",".join(ids)}
    return BASE_URL + "?" + urllib.parse.urlencode(params)


# --------------------------------------------------------------- dispatch --

def compute_arxiv(mode, args=None):
    args = args or {}

    if mode == "validate":
        return _validate()

    timeout = args.get("timeout", 15)

    try:
        if mode == "search":
            if not args.get("query"):
                return {"error": "mode=search requiere 'query'"}
            url = _build_search_url(args)
            raw = _fetch(url, timeout)
            result = _parse_feed(raw)
            result["query"] = args["query"]
            return result

        if mode == "get_by_id":
            if not args.get("id_list"):
                return {"error": "mode=get_by_id requiere 'id_list'"}
            url = _build_id_url(args)
            raw = _fetch(url, timeout)
            return _parse_feed(raw)

        return {"error": f"modo desconocido: {mode}"}

    except urllib.error.URLError as e:
        return {"error": f"fallo de red consultando arXiv: {e}"}
    except ET.ParseError as e:
        return {"error": f"respuesta de arXiv no parseable como XML: {e}"}


# ------------------------------------------------------------- self-test --

_FIXTURE_ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>1</opensearch:totalResults>
  <opensearch:startIndex>0</opensearch:startIndex>
  <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
  <entry>
    <id>http://arxiv.org/abs/1712.09676v2</id>
    <published>2017-12-27T18:59:59Z</published>
    <updated>2018-03-15T10:00:00Z</updated>
    <title>
   A Fake Test Paper Title
    </title>
    <summary>
   This is a fake summary used only for offline validate mode.
    </summary>
    <author><name>Jane Doe</name></author>
    <author><name>John Roe</name></author>
    <arxiv:doi>10.1000/fake.doi</arxiv:doi>
    <arxiv:comment>12 pages, 3 figures</arxiv:comment>
    <link href="http://arxiv.org/abs/1712.09676v2" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/1712.09676v2" rel="related" type="application/pdf"/>
    <arxiv:primary_category term="astro-ph.CO" scheme="http://arxiv.org/schemas/atom"/>
    <category term="astro-ph.CO" scheme="http://arxiv.org/schemas/atom"/>
    <category term="gr-qc" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
</feed>
"""


def _validate():
    checks = []

    parsed = _parse_feed(_FIXTURE_ATOM)
    checks.append({"case": "parseo de feed: total_results correcto", "ok": parsed["total_results"] == 1})
    checks.append({"case": "parseo de feed: returned == len(papers)", "ok": parsed["returned"] == 1 == len(parsed["papers"])})

    p = parsed["papers"][0]
    checks.append({"case": "id extraido correctamente (sin prefijo de URL)", "ok": p["id"] == "1712.09676v2"})
    checks.append({"case": "titulo con whitespace normalizado", "ok": p["title"] == "A Fake Test Paper Title"})
    checks.append({"case": "summary con whitespace normalizado", "ok": p["summary"] == "This is a fake summary used only for offline validate mode."})
    checks.append({"case": "autores en orden", "ok": p["authors"] == ["Jane Doe", "John Roe"]})
    checks.append({"case": "categorias como lista de terms", "ok": set(p["categories"]) == {"astro-ph.CO", "gr-qc"}})
    checks.append({"case": "primary_category extraida", "ok": p["primary_category"] == "astro-ph.CO"})
    checks.append({"case": "pdf_url apunta al link con title=pdf", "ok": p["pdf_url"] == "http://arxiv.org/pdf/1712.09676v2"})
    checks.append({"case": "doi y comment extraidos", "ok": p["doi"] == "10.1000/fake.doi" and p["comment"] == "12 pages, 3 figures"})

    url = _build_search_url({"query": 'au:Hawking AND cat:gr-qc', "start": 5, "max_results": 500, "sort_by": "submittedDate"})
    checks.append({"case": "build_search_url: query codificada, max_results limitado a 100", "ok": "max_results=100" in url and "start=5" in url and "sortBy=submittedDate" in url})

    id_url = _build_id_url({"id_list": ["1712.09676", "2101.00001"]})
    checks.append({"case": "build_id_url: ids unidos por coma", "ok": "id_list=1712.09676%2C2101.00001" in id_url})

    missing_query = compute_arxiv("search", {})
    checks.append({"case": "search sin query devuelve error explicito (sin llegar a hacer red)", "ok": "error" in missing_query})

    missing_ids = compute_arxiv("get_by_id", {})
    checks.append({"case": "get_by_id sin id_list devuelve error explicito (sin llegar a hacer red)", "ok": "error" in missing_ids})

    all_passed = all(c["ok"] for c in checks)
    return {"validate": True, "all_passed": all_passed, "checks": checks}


if register_tool is not None:
    register_tool(
        name="arxiv_tool",
        schema={
            "name": "arxiv_tool",
            "description": (
                "Cliente de la API publica de arXiv (export.arxiv.org, sin "
                "API key). search: busqueda por query con sintaxis de arXiv "
                "(au:/ti:/abs:/cat:, sortBy, paginacion). get_by_id: trae "
                "papers puntuales por arXiv id. Devuelve titulo, autores, "
                "resumen, categorias, DOI, link a PDF."
            ),
            "inputSchema": ARXIV_SCHEMA,
        },
        handler=lambda args: compute_arxiv(args.get("mode"), args),
    )


if __name__ == "__main__":
    print(json.dumps(compute_arxiv("validate"), indent=2, ensure_ascii=False))
