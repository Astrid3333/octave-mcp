"""
data_file_reader_tool.py

Lectura de archivos de datos con formato mixto (texto y numeros), como
CSV/TSV con cabeceras o columnas de texto mezcladas con columnas
numericas. Complementa plotting_tools.py para el caso de datos
experimentales o de simulacion que necesitan graficarse.

Modos:
  - read_delimited : lee un archivo (o contenido inline) delimitado por
                      comas/tabs/punto y coma, con deteccion automatica
                      de delimitador y de si la primera fila es cabecera,
                      e inferencia de tipo por columna (numerico vs texto).
  - inspect        : igual que read_delimited pero solo devuelve metadata
                      (columnas, tipos, n_filas) sin los datos completos --
                      util para previsualizar archivos grandes.
  - self_test / validate : autochequeo contra un CSV sintetico embebido
                      con cabecera y columnas mixtas.

No usa pandas para mantener esto como wrapper liviano (igual que el resto
de octave-mcp) -- csv.Sniffer para deteccion de dialecto, e inferencia de
tipo manual (intenta float, si falla intenta int, si falla deja str).
"""

import csv
import io
import json
import sys

TOOL_SCHEMA = {
    "name": "data_file_reader_tool",
    "description": (
        "Lectura de archivos de datos con formato mixto (texto y "
        "numeros): CSV/TSV con cabeceras o columnas de texto, deteccion "
        "automatica de delimitador y de cabecera, e inferencia de tipo "
        "por columna. Modos: read_delimited, inspect, self_test, validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["read_delimited", "inspect", "self_test", "validate"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "ruta al archivo en disco (usar esto o 'content', no ambos)"},
                    "content": {"type": "string", "description": "contenido del archivo inline como string (usar esto o 'path')"},
                    "delimiter": {"type": "string", "description": "delimitador explicito (si se omite, se auto-detecta con csv.Sniffer)"},
                    "has_header": {"type": "boolean", "description": "si se omite, se auto-detecta con csv.Sniffer.has_header"},
                    "encoding": {"type": "string", "description": "encoding del archivo (default utf-8, solo aplica con 'path')"},
                    "max_preview_rows": {"type": "integer", "description": "filas de muestra en 'inspect' (default 10)"},
                },
            },
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def _get_text(params):
    """Obtiene el texto a parsear desde 'content' o 'path' (mutuamente
    excluyentes). Levanta ValueError si faltan ambos o sobran los dos."""
    content = params.get("content")
    path = params.get("path")
    if content is not None and path is not None:
        raise ValueError("especificar 'content' o 'path', no ambos")
    if content is not None:
        return content
    if path is not None:
        encoding = params.get("encoding", "utf-8")
        with open(path, "r", encoding=encoding, newline="") as f:
            return f.read()
    raise ValueError("se requiere 'content' o 'path'")


def _detect_dialect(text, explicit_delimiter=None):
    """Detecta el dialecto (delimitador) via csv.Sniffer, con fallback a
    coma si el Sniffer no puede determinarlo (por ejemplo, muy pocas
    filas o un formato ambiguo)."""
    if explicit_delimiter is not None:
        class _ExplicitDialect(csv.Dialect):
            delimiter = explicit_delimiter
            quotechar = '"'
            doublequote = True
            skipinitialspace = False
            lineterminator = "\r\n"
            quoting = csv.QUOTE_MINIMAL
        return _ExplicitDialect()

    sample = text[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        class _FallbackDialect(csv.Dialect):
            delimiter = ","
            quotechar = '"'
            doublequote = True
            skipinitialspace = False
            lineterminator = "\r\n"
            quoting = csv.QUOTE_MINIMAL
        return _FallbackDialect()


def _detect_header(text, dialect):
    """Detecta si la primera fila es cabecera con una heuristica propia
    como metodo principal (csv.Sniffer.has_header resulto poco confiable
    en muestras chicas o con columnas de tipo mixto/valores faltantes):
    para cada columna que en las demas filas es mayormente numerica
    (>50% de los valores), se vota "es header" si el valor de esa
    columna en la primera fila NO es numerico. Si todas las columnas
    numericas votan a favor, la primera fila es cabecera. Si ninguna
    columna es mayormente numerica (no hay señal), se usa csv.Sniffer
    como ultimo recurso."""
    reader = csv.reader(io.StringIO(text), dialect=dialect)
    rows = list(reader)
    if len(rows) < 2:
        return False

    first, rest = rows[0], rows[1:]
    ncols = len(first)
    votes_checked = 0
    votes_header = 0
    for c in range(ncols):
        first_val = first[c] if c < len(first) else ""
        rest_values = [r[c] for r in rest if c < len(r)]
        if not rest_values:
            continue
        rest_numeric_frac = sum(
            1 for v in rest_values if _try_numeric(v) is not None
        ) / len(rest_values)
        if rest_numeric_frac > 0.5:
            votes_checked += 1
            if _try_numeric(first_val) is None:
                votes_header += 1

    if votes_checked > 0:
        return votes_header == votes_checked

    sample = text[:8192]
    try:
        return csv.Sniffer().has_header(sample)
    except csv.Error:
        return False


def _try_numeric(value):
    """Intenta convertir a int, luego a float. Devuelve None si no es
    numerico (string vacio tampoco cuenta como numerico)."""
    value = value.strip()
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return None


def _infer_column_types(columns):
    """Para cada columna (lista de strings), infiere el tipo dominante:
    'int' si todos los valores no vacios son enteros, 'float' si todos
    son numericos (con al menos un float), 'text' en otro caso. Tambien
    convierte los valores al tipo inferido (dejando None para vacios)."""
    result_types = []
    result_values = []
    for col in columns:
        parsed = [_try_numeric(v) if v.strip() != "" else None for v in col]
        non_null = [p for p in parsed if p is not None]
        if non_null and all(isinstance(p, int) for p in non_null):
            col_type = "int"
        elif non_null and all(isinstance(p, (int, float)) for p in non_null):
            col_type = "float"
            parsed = [float(p) if p is not None else None for p in parsed]
        else:
            col_type = "text"
            parsed = [v if v.strip() != "" else None for v in col]
        result_types.append(col_type)
        result_values.append(parsed)
    return result_types, result_values


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------

def _parse(params):
    text = _get_text(params)
    dialect = _detect_dialect(text, params.get("delimiter"))
    has_header = params.get("has_header")
    if has_header is None:
        has_header = _detect_header(text, dialect)

    reader = csv.reader(io.StringIO(text), dialect=dialect)
    rows = list(reader)
    if not rows:
        raise ValueError("el archivo/contenido esta vacio")

    if has_header:
        header = rows[0]
        data_rows = rows[1:]
    else:
        header = [f"col_{i}" for i in range(len(rows[0]))]
        data_rows = rows

    n_cols = len(header)
    # normalizar filas mas cortas/largas que el header (rellenar con "")
    norm_rows = []
    for r in data_rows:
        if len(r) < n_cols:
            r = r + [""] * (n_cols - len(r))
        elif len(r) > n_cols:
            r = r[:n_cols]
        norm_rows.append(r)

    columns = [[row[c] for row in norm_rows] for c in range(n_cols)]
    col_types, col_values = _infer_column_types(columns)

    return {
        "header": header,
        "has_header": bool(has_header),
        "delimiter": dialect.delimiter,
        "n_rows": len(norm_rows),
        "n_cols": n_cols,
        "column_types": col_types,
        "columns": {header[i]: col_values[i] for i in range(n_cols)},
    }


def read_delimited(params=None):
    params = params or {}
    out = _parse(params)
    return {
        "mode": "read_delimited",
        "header": out["header"],
        "has_header": out["has_header"],
        "delimiter": out["delimiter"],
        "n_rows": out["n_rows"],
        "n_cols": out["n_cols"],
        "column_types": out["column_types"],
        "columns": out["columns"],
    }


def inspect(params=None):
    params = params or {}
    out = _parse(params)
    max_preview = int(params.get("max_preview_rows", 10))
    preview = {
        name: values[:max_preview] for name, values in out["columns"].items()
    }
    return {
        "mode": "inspect",
        "header": out["header"],
        "has_header": out["has_header"],
        "delimiter": out["delimiter"],
        "n_rows": out["n_rows"],
        "n_cols": out["n_cols"],
        "column_types": out["column_types"],
        "preview": preview,
    }


# ---------------------------------------------------------------------------
# self_test / run / registro
# ---------------------------------------------------------------------------

_SYNTHETIC_CSV = (
    "nombre,edad,ciudad,peso_kg\n"
    "Ana,34,Castro,61.5\n"
    "Luis,28,Ancud,78.2\n"
    "Marta,45,Quellon,,\n"
    "Pedro,,Castro,80.0\n"
).replace(",,\n", ",\n")  # limpia doble coma accidental de edicion


def run_self_test():
    checks = []

    def check(name, cond, detail=""):
        checks.append({"name": name, "passed": bool(cond), "detail": detail})

    out = read_delimited({"content": _SYNTHETIC_CSV})
    check("read_delimited: header detectado correctamente",
          out["header"] == ["nombre", "edad", "ciudad", "peso_kg"],
          f"header={out['header']}")
    check("read_delimited: has_header=True", out["has_header"] is True,
          f"has_header={out['has_header']}")
    check("read_delimited: delimiter=','", out["delimiter"] == ",",
          f"delimiter={out['delimiter']!r}")
    check("read_delimited: n_rows=4", out["n_rows"] == 4,
          f"n_rows={out['n_rows']}")
    check("read_delimited: columna 'edad' inferida como numerica (int/float)",
          out["column_types"][1] in ("int", "float"),
          f"tipo={out['column_types'][1]}")
    check("read_delimited: columna 'nombre' inferida como texto",
          out["column_types"][0] == "text",
          f"tipo={out['column_types'][0]}")
    check("read_delimited: valor faltante en 'edad' (Pedro) es None",
          out["columns"]["edad"][3] is None,
          f"valor={out['columns']['edad'][3]!r}")
    check("read_delimited: valor faltante en 'peso_kg' (Marta) es None",
          out["columns"]["peso_kg"][2] is None,
          f"valor={out['columns']['peso_kg'][2]!r}")

    # sin cabecera (todo numerico, sin nombres de columna reconocibles)
    csv_sin_header = "1,2,3\n4,5,6\n7,8,9\n"
    out2 = read_delimited({"content": csv_sin_header, "has_header": False})
    check("read_delimited: has_header=False respeta override explicito",
          out2["has_header"] is False, f"has_header={out2['has_header']}")
    check("read_delimited: columnas generadas col_0..col_2 sin header",
          out2["header"] == ["col_0", "col_1", "col_2"],
          f"header={out2['header']}")

    # inspect: preview limitado
    out3 = inspect({"content": _SYNTHETIC_CSV, "max_preview_rows": 2})
    check("inspect: preview limitado a max_preview_rows",
          len(out3["preview"]["nombre"]) == 2,
          f"len(preview)={len(out3['preview']['nombre'])}")

    total = len(checks)
    passed = sum(1 for c in checks if c["passed"])
    return {"total": total, "passed": passed, "all_passed": passed == total, "checks": checks}


def run(mode, params=None):
    params = params or {}
    if mode == "validate":
        r = run_self_test()
        return {"checks": r["checks"], "validation_passed": r["all_passed"], "n_checks": r["total"]}
    elif mode == "self_test":
        return run_self_test()
    elif mode == "read_delimited":
        return read_delimited(params)
    elif mode == "inspect":
        return inspect(params)
    else:
        raise ValueError(
            f"modo desconocido: {mode} (usar read_delimited/inspect/self_test)"
        )


if __name__ == "__main__":
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "self_test"
    params_arg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    try:
        out = run(mode_arg, params_arg)
        print(json.dumps(out, indent=2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)


def _register():
    """
    Auto-registro estilo octave-mcp (patron self-registrante via
    tool_registry, register_tool(name, schema, handler)).
    """
    try:
        import tool_registry

        def _handler(args):
            return run(args.get("mode"), args.get("params"))

        tool_registry.register_tool("data_file_reader_tool", TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()
