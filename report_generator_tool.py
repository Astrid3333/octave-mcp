"""
report_generator_tool.py

Exporta resultados (dict JSON-serializable, típicamente la salida de
cualquier otra tool de octave-mcp) a un reporte legible: Markdown,
LaTeX (texto plano, sin invocar un motor LaTeX) o JSON pretty-printed.

No agrega dependencias nuevas (solo stdlib). Sigue el mismo patrón
de auto-registro vía tool_registry usado en el resto del repo
(units_constants_tool, heating_value_tool, etc.): un solo import en
server.py y listo.

Dos formas de traer los datos:
  - "data": el dict a reportar, pasado directo (para uso ad-hoc).
  - "run_id": carga el resultado guardado por otra tool vía
    workspace_tool.load_run / load_run_safe (para reportar algo ya
    corrido y guardado, sin tener que repetir el cálculo).

Modos:
  - to_markdown: reporte .md (título, metadata opcional, secciones
    por clave de primer nivel; listas de dicts -> tabla; escalares
    sueltos -> tabla key/value).
  - to_latex: mismo contenido, como .tex standalone (article) con
    tabular para lo que to_markdown pone en tabla. Texto plano, no
    requiere pdflatex ni ningun motor instalado -- el usuario lo
    compila donde quiera.
  - to_json: json.dumps con indent=2, ensure_ascii=False (conveniencia,
    ya que casi todo el resto del repo ya devuelve JSON pero sin
    normalizar orden de claves ni indentación consistente).
  - validate: self-test con datos sintéticos (no depende de ninguna
    otra tool ni de Octave).
"""

import json
import re
from datetime import datetime, timezone

try:
    from tool_registry import register_tool
except ImportError:
    register_tool = None

try:
    import workspace_tool
except ImportError:
    workspace_tool = None


REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["to_markdown", "to_latex", "to_json", "validate"],
        },
        "data": {
            "description": "Dict a reportar. Alternativa a run_id.",
        },
        "run_id": {
            "type": "string",
            "description": (
                "Si se pasa en vez de 'data', carga el resultado desde "
                "workspace_tool.load_run / load_run_safe."
            ),
        },
        "title": {"type": "string", "description": "Titulo del reporte."},
        "meta": {
            "type": "object",
            "description": (
                "Metadata opcional a mostrar arriba del reporte "
                "(ej: {'tool': 'heating_value_tool', 'fuel': 'CH4'})."
            ),
        },
    },
    "required": ["mode"],
}


# ---------------------------------------------------------------- helpers --

def _is_scalar(v):
    return isinstance(v, (int, float, str, bool)) or v is None


def _is_list_of_dicts(v):
    return isinstance(v, list) and len(v) > 0 and all(isinstance(x, dict) for x in v)


def _escape_latex(s):
    s = str(s)
    repl = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    pattern = re.compile("|".join(re.escape(k) for k in repl))
    return pattern.sub(lambda m: repl[m.group()], s)


def _fmt_scalar_md(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:.6g}"
    if v is None:
        return "—"
    return str(v)


def _resolve_data(args):
    """Devuelve (data, source_note)."""
    if args.get("data") is not None:
        return args["data"], None
    run_id = args.get("run_id")
    if run_id:
        if workspace_tool is None:
            return {"error": "workspace_tool no disponible en este entorno"}, None
        loader = getattr(workspace_tool, "load_run_safe", None) or workspace_tool.load_run
        result = loader(run_id)
        if "error" in result:
            return result, None
        note = f"run_id: {run_id}"
        meta = result.get("meta")
        if meta:
            note += f" (meta: {json.dumps(meta, ensure_ascii=False)})"
        return result.get("data", result), note
    return {"error": "se requiere 'data' o 'run_id'"}, None


# --------------------------------------------------------------- markdown --

def _md_table_from_list_of_dicts(rows):
    cols = []
    for r in rows:
        for k in r.keys():
            if k not in cols:
                cols.append(k)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(_fmt_scalar_md(r.get(c, "")) for c in cols) + " |")
    return "\n".join(lines)


def _md_table_from_dict(d):
    lines = ["| campo | valor |", "| --- | --- |"]
    for k, v in d.items():
        if _is_scalar(v):
            lines.append(f"| {k} | {_fmt_scalar_md(v)} |")
        else:
            lines.append(f"| {k} | `{json.dumps(v, ensure_ascii=False)}` |")
    return "\n".join(lines)


def _render_markdown(data, title, meta):
    lines = [f"# {title}", ""]
    lines.append(f"_Generado: {datetime.now(timezone.utc).isoformat(timespec='seconds')}Z_")
    lines.append("")
    if meta:
        lines.append("## Metadata")
        lines.append("")
        lines.append(_md_table_from_dict(meta))
        lines.append("")

    if _is_scalar(data):
        lines.append(_fmt_scalar_md(data))
        return "\n".join(lines)

    if _is_list_of_dicts(data):
        lines.append("## Resultados")
        lines.append("")
        lines.append(_md_table_from_list_of_dicts(data))
        return "\n".join(lines)

    if isinstance(data, dict):
        scalar_items = {k: v for k, v in data.items() if _is_scalar(v)}
        complex_items = {k: v for k, v in data.items() if not _is_scalar(v)}

        if scalar_items:
            lines.append("## Resumen")
            lines.append("")
            lines.append(_md_table_from_dict(scalar_items))
            lines.append("")

        for k, v in complex_items.items():
            lines.append(f"## {k}")
            lines.append("")
            if _is_list_of_dicts(v):
                lines.append(_md_table_from_list_of_dicts(v))
            elif isinstance(v, dict):
                lines.append(_md_table_from_dict(v))
            elif isinstance(v, list):
                lines.append("\n".join(f"- {_fmt_scalar_md(x)}" for x in v))
            else:
                lines.append(f"`{json.dumps(v, ensure_ascii=False)}`")
            lines.append("")
        return "\n".join(lines)

    lines.append(f"```json\n{json.dumps(data, indent=2, ensure_ascii=False)}\n```")
    return "\n".join(lines)


# ------------------------------------------------------------------ latex --

def _latex_table_from_list_of_dicts(rows):
    cols = []
    for r in rows:
        for k in r.keys():
            if k not in cols:
                cols.append(k)
    spec = "l" * len(cols)
    lines = [r"\begin{tabular}{" + spec + "}", r"\toprule"]
    lines.append(" & ".join(_escape_latex(c) for c in cols) + r" \\")
    lines.append(r"\midrule")
    for r in rows:
        lines.append(" & ".join(_escape_latex(_fmt_scalar_md(r.get(c, ""))) for c in cols) + r" \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    return "\n".join(lines)


def _latex_table_from_dict(d):
    lines = [r"\begin{tabular}{ll}", r"\toprule", r"Campo & Valor \\", r"\midrule"]
    for k, v in d.items():
        val = _fmt_scalar_md(v) if _is_scalar(v) else json.dumps(v, ensure_ascii=False)
        lines.append(f"{_escape_latex(k)} & {_escape_latex(val)} " + r"\\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    return "\n".join(lines)


def _render_latex(data, title, meta):
    body = []
    body.append(r"\documentclass{article}")
    body.append(r"\usepackage[utf8]{inputenc}")
    body.append(r"\usepackage{booktabs}")
    body.append(r"\usepackage{geometry}")
    body.append(r"\geometry{margin=2.5cm}")
    body.append(f"\\title{{{_escape_latex(title)}}}")
    body.append(r"\date{" + datetime.now(timezone.utc).strftime("%Y-%m-%d") + "}")
    body.append(r"\begin{document}")
    body.append(r"\maketitle")

    if meta:
        body.append(r"\section*{Metadata}")
        body.append(_latex_table_from_dict(meta))

    if _is_scalar(data):
        body.append(_escape_latex(_fmt_scalar_md(data)))
    elif _is_list_of_dicts(data):
        body.append(r"\section*{Resultados}")
        body.append(_latex_table_from_list_of_dicts(data))
    elif isinstance(data, dict):
        scalar_items = {k: v for k, v in data.items() if _is_scalar(v)}
        complex_items = {k: v for k, v in data.items() if not _is_scalar(v)}
        if scalar_items:
            body.append(r"\section*{Resumen}")
            body.append(_latex_table_from_dict(scalar_items))
        for k, v in complex_items.items():
            body.append(f"\\section*{{{_escape_latex(k)}}}")
            if _is_list_of_dicts(v):
                body.append(_latex_table_from_list_of_dicts(v))
            elif isinstance(v, dict):
                body.append(_latex_table_from_dict(v))
            elif isinstance(v, list):
                body.append(r"\begin{itemize}")
                for x in v:
                    body.append(f"\\item {_escape_latex(_fmt_scalar_md(x))}")
                body.append(r"\end{itemize}")
            else:
                body.append(r"\begin{verbatim}")
                body.append(json.dumps(v, indent=2, ensure_ascii=False))
                body.append(r"\end{verbatim}")
    else:
        body.append(r"\begin{verbatim}")
        body.append(json.dumps(data, indent=2, ensure_ascii=False))
        body.append(r"\end{verbatim}")

    body.append(r"\end{document}")
    return "\n".join(body)


# --------------------------------------------------------------- dispatch --

def compute_report(mode, args=None):
    args = args or {}

    if mode == "validate":
        return _validate()

    title = args.get("title", "Reporte")
    meta = args.get("meta")
    data, note = _resolve_data(args)

    if isinstance(data, dict) and "error" in data and len(data) == 1:
        return {"error": data["error"]}

    if note and not meta:
        meta = {"fuente": note}
    elif note and meta:
        meta = dict(meta, fuente=note)

    if mode == "to_markdown":
        return {"format": "markdown", "content": _render_markdown(data, title, meta)}
    if mode == "to_latex":
        return {"format": "latex", "content": _render_latex(data, title, meta)}
    if mode == "to_json":
        return {"format": "json", "content": json.dumps(data, indent=2, ensure_ascii=False)}

    return {"error": f"modo desconocido: {mode}"}


def _validate():
    checks = []

    scalar_case = {"lhv": 50.025, "hhv": 55.511, "fuel": "CH4"}
    md = _render_markdown(scalar_case, "Heating value CH4", None)
    checks.append({
        "case": "markdown: dict de escalares genera tabla resumen",
        "ok": "| lhv | 50.025 |" in md and "## Resumen" in md,
    })

    list_case = [
        {"case": "CH4 LHV", "got": 50.025, "expected": 50.0, "ok": True},
        {"case": "H2 LHV", "got": 119.953, "expected": 120.0, "ok": True},
    ]
    md_list = _render_markdown({"checks": list_case, "all_passed": True}, "Validate", None)
    checks.append({
        "case": "markdown: lista de dicts anidada genera tabla con columnas correctas",
        "ok": "| case | got | expected | ok |" in md_list and "CH4 LHV" in md_list,
    })

    tex = _render_latex(scalar_case, "Heating value CH4", {"tool": "heating_value_tool"})
    checks.append({
        "case": "latex: documento bien formado (begin/end document, tabular presente)",
        "ok": r"\begin{document}" in tex and r"\end{document}" in tex and r"\begin{tabular}" in tex,
    })

    esc = _escape_latex("100% & $x_1$ #tag")
    checks.append({
        "case": "latex: escape de caracteres especiales (%, &, $, #, _)",
        "ok": esc == r"100\% \& \$x\_1\$ \#tag",
    })

    js = compute_report("to_json", {"data": {"a": 1, "b": [1, 2, 3]}})
    parsed_back = json.loads(js["content"])
    checks.append({
        "case": "to_json: round-trip preserva estructura",
        "ok": parsed_back == {"a": 1, "b": [1, 2, 3]},
    })

    missing = compute_report("to_markdown", {})
    checks.append({
        "case": "sin 'data' ni 'run_id' devuelve error explicito",
        "ok": "error" in missing,
    })

    all_passed = all(c["ok"] for c in checks)
    return {"validate": True, "all_passed": all_passed, "checks": checks}


if register_tool is not None:
    register_tool(
        name="report_generator_tool",
        schema={
            "name": "report_generator_tool",
            "description": (
                "Exporta un dict de resultados (pasado directo via 'data' o "
                "cargado via 'run_id' desde workspace_tool) a un reporte: "
                "to_markdown (.md con tablas), to_latex (.tex standalone con "
                "booktabs, sin requerir motor LaTeX instalado), to_json "
                "(pretty-print). Util para convertir la salida JSON de "
                "cualquier otra tool del repo en algo presentable."
            ),
            "inputSchema": REPORT_SCHEMA,
        },
        handler=lambda args: compute_report(args.get("mode"), args),
    )


if __name__ == "__main__":
    print(json.dumps(compute_report("validate"), indent=2, ensure_ascii=False))
