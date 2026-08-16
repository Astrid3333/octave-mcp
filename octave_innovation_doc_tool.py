"""
octave_innovation_doc_tool.py

Sistema de "documentos de innovacion" para codigo Octave (.m): un schema
de campos obligatorios embebido como bloque de comentario Octave valido al
inicio del archivo, mas validacion (schema + sintaxis real del codigo) y
proyeccion a distintas vistas segun audiencia (octave_eject).

Diseño desde cero -- se confirmo por busqueda exhaustiva (grep local del
server.py real y github:search_code) que octave_eject, el concepto de
"documento OCTAVE con schema propio" y el "recibo de validacion" no
existian bajo ningun nombre en el repo antes de este modulo.

Convencion de la persona: el "documento OCTAVE" es codigo GNU Octave (.m)
real -- el mismo lenguaje que ya usan las 191 tools del repo -- no un
formato de texto nuevo. Por eso el schema se embebe en un bloque de
comentario `%{ ... %}` de Octave, que es sintaxis 100% valida: el archivo
sigue siendo un .m corriente, parseable por octave-cli sin modificaciones,
y el bloque de header no interfiere con el codigo real que le sigue.

FORMATO DEL DOCUMENTO
======================
El header, si existe, debe ser el primer contenido no-blanco del archivo:

    %{
    OCTAVE_DOC: v1
    TITULO: nombre corto del documento (opcional)
    PROBLEMA: el desafio identificado
    SOLUCION_INNOVADORA: la propuesta matematica o tecnica
    IMPACTO_ESPERADO: beneficios cuantitativos o cualitativos
    TOOLS_UTILIZADAS: tool_a, tool_b, tool_c
    AUTOR: opcional
    FECHA: opcional
    %}

    <codigo Octave real a continuacion>

Reglas de parseo: una linea que matchea `^[A-Z][A-Z0-9_]*:` abre un campo
nuevo; lineas siguientes que no matchean ese patron son continuacion del
campo anterior (se unen con un espacio, estilo parrafo). Campos
obligatorios (schema v1): PROBLEMA, SOLUCION_INNOVADORA, IMPACTO_ESPERADO,
TOOLS_UTILIZADAS. Campos opcionales: TITULO, AUTOR, FECHA. Un documento
sin `%{ OCTAVE_DOC: ... %}` como primer bloque simplemente no tiene header
reconocido (found_header=False) -- no es un error, es un .m corriente.

RECIBO DE VALIDACION
=====================
validate_doc (o write_doc cuando pasa) produce un "recibo": un segundo
bloque de comentario Octave, tambien valido, que se puede insertar
inmediatamente despues del header:

    %{
    OCTAVE_RECEIPT: v1
    validated_at: 2026-08-16T12:00:00Z
    validation_status: PASSED
    schema_version: v1
    code_syntax_status: VALID
    %}

Este recibo "viaja con" el documento: write_doc lo escribe al archivo
cuando la validacion pasa, y parse_doc lo detecta y reporta si ya existe
(reemplazandolo en vez de duplicarlo si se vuelve a escribir).

CROSS-CHECK DE TOOLS_UTILIZADAS
=================================
Solo un subconjunto de las tools del repo esta migrado al patron nuevo de
auto-registro via tool_registry (tool_registry.get_names()); la mayoria
sigue wireada a mano en server.py (patron legacy, ver tool_registry.py:
"Estrategia de migracion (strangler fig)"). Por eso el cross-check NUNCA
marca como invalido un nombre de tool que no aparece en
tool_registry.get_names() -- lo reporta como "unverified" (no verificable
por este mecanismo, puede perfectamente ser una tool legacy real), y solo
"confirmed" para las que si aparecen ahi. Esto evita falsos negativos
masivos dado que ~176 de 191 tools son legacy.

octave_eject: PROYECCION A VISTAS
===================================
Dado un documento con header reconocido, proyecta la informacion segun
audiencia:
  - executive: TITULO + PROBLEMA + SOLUCION_INNOVADORA + IMPACTO_ESPERADO
    en prosa llana, sin codigo ni lista de tools -- para quien toma
    decisiones.
  - developer: TITULO + PROBLEMA + SOLUCION_INNOVADORA + TOOLS_UTILIZADAS
    (como lista) + el codigo Octave completo -- para el equipo tecnico.
  - raw: el documento original sin modificar.
"""

import re
from datetime import datetime, timezone

import tool_registry

try:
    from octave_grammar_tool import validate_code as _grammar_validate_code
except ImportError:
    _grammar_validate_code = None


SCHEMA_VERSION = "v1"
REQUIRED_FIELDS = ["PROBLEMA", "SOLUCION_INNOVADORA", "IMPACTO_ESPERADO", "TOOLS_UTILIZADAS"]
OPTIONAL_FIELDS = ["TITULO", "AUTOR", "FECHA"]
KNOWN_FIELDS = set(REQUIRED_FIELDS) | set(OPTIONAL_FIELDS) | {"OCTAVE_DOC"}

_BLOCK_RE = re.compile(r"\A\s*%\{\s*\n(.*?)\n\s*%\}\s*\n?", re.S)
_FIELD_LINE_RE = re.compile(r"^([A-Z][A-Z0-9_]*):\s?(.*)$")
_RECEIPT_BLOCK_RE = re.compile(r"%\{\s*\nOCTAVE_RECEIPT:.*?\n\s*%\}\s*\n?", re.S)


def _parse_block(block_text):
    """Parsea el contenido interno de un bloque %{ ... %} en un dict de
    campo -> valor, uniendo lineas de continuacion con espacio."""
    fields = {}
    current_key = None
    for line in block_text.splitlines():
        m = _FIELD_LINE_RE.match(line.strip())
        if m:
            current_key = m.group(1)
            fields[current_key] = m.group(2).strip()
        elif current_key is not None and line.strip():
            fields[current_key] = (fields[current_key] + " " + line.strip()).strip()
    return fields


def parse_doc(text):
    """Extrae el header de innovacion (si existe) y el cuerpo de codigo
    restante. No lanza excepcion si no hay header: found_header=False y
    body=texto completo."""
    m = _BLOCK_RE.match(text)
    if not m:
        return {
            "found_header": False,
            "schema_version": None,
            "fields": {},
            "unknown_fields": [],
            "has_receipt": "OCTAVE_RECEIPT:" in text[:2000],
            "body": text,
        }

    header_fields = _parse_block(m.group(1))
    body = text[m.end():]

    if "OCTAVE_DOC" not in header_fields:
        # es un bloque de comentario Octave valido, pero no declara ser
        # un documento de innovacion (no tiene la marca de schema) -- se
        # trata como .m corriente sin header reconocido.
        return {
            "found_header": False,
            "schema_version": None,
            "fields": {},
            "unknown_fields": [],
            "has_receipt": "OCTAVE_RECEIPT:" in text[:2000],
            "body": text,
        }

    schema_version = header_fields.pop("OCTAVE_DOC", None)
    unknown = sorted(k for k in header_fields if k not in KNOWN_FIELDS)

    # si justo despues del header hay un bloque de recibo, lo salteamos
    # del body para que la vista "developer"/"raw" no lo duplique como
    # si fuera codigo -- pero lo dejamos reportado via has_receipt.
    receipt_m = _RECEIPT_BLOCK_RE.match(body.lstrip("\n"))
    has_receipt = receipt_m is not None
    if has_receipt:
        stripped = body.lstrip("\n")
        body = stripped[receipt_m.end():]

    return {
        "found_header": True,
        "schema_version": schema_version,
        "fields": header_fields,
        "unknown_fields": unknown,
        "has_receipt": has_receipt,
        "body": body,
    }


def _check_tools_utilizadas(tools_field_value):
    names = [t.strip() for t in tools_field_value.split(",") if t.strip()]
    try:
        registered = tool_registry.get_names()
    except Exception:
        registered = set()
    confirmed = [n for n in names if n in registered]
    unverified = [n for n in names if n not in registered]
    return {"declared": names, "confirmed": confirmed, "unverified": unverified}


def _code_syntax_check(code):
    if _grammar_validate_code is None:
        return {"available": False, "reason": "octave_grammar_tool no importable"}
    try:
        result = _grammar_validate_code(code, use_real_check=True)
        return {"available": True, "result": result}
    except Exception as e:
        return {"available": False, "reason": f"error: {e}"}


def validate_doc(text, check_syntax=True):
    parsed = parse_doc(text)
    schema_errors = []

    if not parsed["found_header"]:
        schema_errors.append({
            "type": "missing_header",
            "message": (
                "no se encontro un bloque %{ OCTAVE_DOC: v1 ... %} como "
                "primer contenido del archivo"
            ),
        })
    else:
        if parsed["schema_version"] != SCHEMA_VERSION:
            schema_errors.append({
                "type": "unsupported_schema_version",
                "message": f"OCTAVE_DOC declara '{parsed['schema_version']}', soportado: '{SCHEMA_VERSION}'",
            })
        for field in REQUIRED_FIELDS:
            value = parsed["fields"].get(field)
            if value is None:
                schema_errors.append({"type": "missing_field", "field": field})
            elif not value.strip():
                schema_errors.append({"type": "empty_field", "field": field})

    tools_check = None
    if parsed["found_header"] and parsed["fields"].get("TOOLS_UTILIZADAS"):
        tools_check = _check_tools_utilizadas(parsed["fields"]["TOOLS_UTILIZADAS"])

    code_check = _code_syntax_check(parsed["body"]) if check_syntax else {"available": False, "reason": "check_syntax=False"}
    code_syntax_ok = True
    if code_check.get("available") and code_check["result"]["validation_status"] == "INVALID":
        code_syntax_ok = False

    schema_valid = not schema_errors
    overall_status = "PASSED" if (schema_valid and code_syntax_ok) else "FAILED"

    result = {
        "mode": "validate_doc",
        "schema_valid": schema_valid,
        "schema_errors": schema_errors,
        "unknown_fields": parsed["unknown_fields"],
        "tools_utilizadas_check": tools_check,
        "code_validation": code_check,
        "validation_status": overall_status,
    }
    if overall_status == "PASSED":
        result["receipt"] = {
            "OCTAVE_RECEIPT": SCHEMA_VERSION,
            "validated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "validation_status": "PASSED",
            "schema_version": parsed["schema_version"],
            "code_syntax_status": "VALID" if code_check.get("available") else "no_verificado",
        }
    return result


def _format_receipt_block(receipt):
    lines = ["%{"]
    lines.append(f"OCTAVE_RECEIPT: {receipt['OCTAVE_RECEIPT']}")
    for key in ("validated_at", "validation_status", "schema_version", "code_syntax_status"):
        lines.append(f"{key}: {receipt[key]}")
    lines.append("%}")
    return "\n".join(lines) + "\n"


def write_doc(text, path, check_syntax=True):
    validation = validate_doc(text, check_syntax=check_syntax)
    if validation["validation_status"] != "PASSED":
        return {**validation, "mode": "write_doc", "written": False, "path": path}

    # separar header original (sin recibo previo) del resto, y re-armar
    # con el recibo nuevo insertado justo despues del header.
    m = _BLOCK_RE.match(text)
    header_text = text[:m.end()]
    rest = text[m.end():]
    rest_no_old_receipt = _RECEIPT_BLOCK_RE.sub("", rest.lstrip("\n"), count=1)
    receipt_block = _format_receipt_block(validation["receipt"])
    new_text = header_text + receipt_block + "\n" + rest_no_old_receipt

    with open(path, "w") as f:
        f.write(new_text)

    return {
        **validation,
        "mode": "write_doc",
        "written": True,
        "path": path,
    }


def eject(text, view="executive"):
    parsed = parse_doc(text)
    if not parsed["found_header"]:
        return {
            "mode": "eject", "view": view,
            "error": "el documento no tiene un header %{ OCTAVE_DOC: v1 ... %} reconocido",
        }

    f = parsed["fields"]
    titulo = f.get("TITULO", "(sin titulo)")

    if view == "raw":
        return {"mode": "eject", "view": "raw", "text": text}

    if view == "executive":
        parts = [f"# {titulo}", ""]
        parts.append(f"**Problema:** {f.get('PROBLEMA', '')}")
        parts.append("")
        parts.append(f"**Solucion:** {f.get('SOLUCION_INNOVADORA', '')}")
        parts.append("")
        parts.append(f"**Impacto esperado:** {f.get('IMPACTO_ESPERADO', '')}")
        return {"mode": "eject", "view": "executive", "text": "\n".join(parts)}

    if view == "developer":
        tools = [t.strip() for t in f.get("TOOLS_UTILIZADAS", "").split(",") if t.strip()]
        parts = [f"# {titulo} (vista tecnica)", ""]
        parts.append(f"**Problema:** {f.get('PROBLEMA', '')}")
        parts.append("")
        parts.append(f"**Solucion tecnica:** {f.get('SOLUCION_INNOVADORA', '')}")
        parts.append("")
        parts.append(f"**Tools utilizadas:** {', '.join(tools) if tools else '(ninguna declarada)'}")
        parts.append("")
        parts.append("**Codigo:**")
        parts.append("```octave")
        parts.append(parsed["body"].strip())
        parts.append("```")
        return {"mode": "eject", "view": "developer", "text": "\n".join(parts)}

    return {"mode": "eject", "view": view, "error": f"vista desconocida: {view!r}, opciones: executive, developer, raw"}


# ----------------------------------------------------------------------
# Validacion (autochequeo del tool, convencion del repo)
# ----------------------------------------------------------------------

_EXAMPLE_VALID_DOC = """%{
OCTAVE_DOC: v1
TITULO: Ejemplo de contrato de innovacion
PROBLEMA: Los agentes no reciben la gramatica al fallar la validacion.
SOLUCION_INNOVADORA: octave_grammar_tool adjunta grammar_hint en la misma respuesta.
IMPACTO_ESPERADO: Menos llamadas por intento de generacion, ciclo cerrado.
TOOLS_UTILIZADAS: octave_grammar_tool, octave_syntax_tool
%}

x = 1;
for i = 1:10
  x = x + i;
endfor
printf("%d\\n", x);
"""

_EXAMPLE_MISSING_FIELD_DOC = """%{
OCTAVE_DOC: v1
TITULO: Ejemplo incompleto
PROBLEMA: falta un campo obligatorio.
SOLUCION_INNOVADORA: ninguna todavia.
%}

x = 1;
"""


def _parse_full_header_check():
    r = parse_doc(_EXAMPLE_VALID_DOC)
    ok = (
        r["found_header"] is True
        and r["schema_version"] == SCHEMA_VERSION
        and all(field in r["fields"] for field in REQUIRED_FIELDS)
        and r["fields"]["TITULO"] == "Ejemplo de contrato de innovacion"
    )
    return {
        "name": "parse_doc_extracts_all_required_fields",
        "found_header": r["found_header"],
        "fields_present": sorted(r["fields"].keys()),
        "passed": bool(ok),
    }


def _parse_no_header_check():
    plain_code = "x = 1;\ny = 2;\nprintf(\"%d\\n\", x + y);\n"
    r = parse_doc(plain_code)
    ok = r["found_header"] is False and r["body"] == plain_code
    return {
        "name": "parse_doc_handles_missing_header_gracefully",
        "found_header": r["found_header"],
        "passed": bool(ok),
    }


def _validate_complete_doc_passes():
    r = validate_doc(_EXAMPLE_VALID_DOC, check_syntax=True)
    ok = r["schema_valid"] is True and r["validation_status"] == "PASSED" and "receipt" in r
    return {
        "name": "validate_doc_complete_document_passes",
        "validation_status": r["validation_status"],
        "schema_valid": r["schema_valid"],
        "code_check_available": r["code_validation"].get("available"),
        "passed": bool(ok),
    }


def _validate_missing_field_fails():
    r = validate_doc(_EXAMPLE_MISSING_FIELD_DOC, check_syntax=False)
    missing_types = [e["field"] for e in r["schema_errors"] if e["type"] == "missing_field"]
    ok = (
        r["schema_valid"] is False
        and r["validation_status"] == "FAILED"
        and "IMPACTO_ESPERADO" in missing_types
        and "TOOLS_UTILIZADAS" in missing_types
    )
    return {
        "name": "validate_doc_missing_field_fails",
        "validation_status": r["validation_status"],
        "missing_fields_detected": missing_types,
        "passed": bool(ok),
    }


def _eject_views_differ_check():
    exec_view = eject(_EXAMPLE_VALID_DOC, view="executive")
    dev_view = eject(_EXAMPLE_VALID_DOC, view="developer")
    ok = (
        "error" not in exec_view
        and "error" not in dev_view
        and "```octave" not in exec_view["text"]
        and "```octave" in dev_view["text"]
        and "TOOLS_UTILIZADAS" not in exec_view["text"]
        and "octave_grammar_tool" in dev_view["text"]
    )
    return {
        "name": "eject_executive_excludes_code_developer_includes_it",
        "executive_has_code_block": "```octave" in exec_view.get("text", ""),
        "developer_has_code_block": "```octave" in dev_view.get("text", ""),
        "passed": bool(ok),
    }


def _write_doc_roundtrip_check():
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".m", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        fail_result = write_doc(_EXAMPLE_MISSING_FIELD_DOC, tmp_path, check_syntax=False)
        fail_ok = fail_result["written"] is False

        pass_result = write_doc(_EXAMPLE_VALID_DOC, tmp_path, check_syntax=True)
        pass_ok = pass_result["written"] is True

        with open(tmp_path) as f:
            written_text = f.read()
        reparsed = parse_doc(written_text)
        receipt_ok = reparsed["has_receipt"] is True and "OCTAVE_DOC: v1" in written_text
    finally:
        import os as _os
        _os.unlink(tmp_path)

    ok = fail_ok and pass_ok and receipt_ok
    return {
        "name": "write_doc_only_writes_when_passed_and_stamps_receipt",
        "fail_case_written": not fail_ok,
        "pass_case_written": pass_ok,
        "receipt_detected_after_write": receipt_ok,
        "passed": bool(ok),
    }


def validate():
    checks = [
        _parse_full_header_check(),
        _parse_no_header_check(),
        _validate_complete_doc_passes(),
        _validate_missing_field_fails(),
        _eject_views_differ_check(),
        _write_doc_roundtrip_check(),
    ]
    return {
        "mode": "validate",
        "checks": checks,
        "validation_passed": all(c["passed"] for c in checks),
    }


def compute_octave_innovation_doc(mode="validate", **kwargs):
    if mode == "parse_doc":
        return parse_doc(kwargs["text"])
    elif mode == "validate_doc":
        return validate_doc(kwargs["text"], check_syntax=kwargs.get("check_syntax", True))
    elif mode == "write_doc":
        return write_doc(kwargs["text"], kwargs["path"], check_syntax=kwargs.get("check_syntax", True))
    elif mode == "eject":
        return eject(kwargs["text"], view=kwargs.get("view", "executive"))
    elif mode == "validate":
        return validate()
    else:
        raise ValueError(f"mode desconocido: {mode}")


OCTAVE_INNOVATION_DOC_TOOL_SCHEMA = {
    "name": "octave_innovation_doc_tool",
    "description": (
        "Sistema de 'contrato de innovacion' para documentos Octave (.m): "
        "un schema de campos obligatorios (PROBLEMA, SOLUCION_INNOVADORA, "
        "IMPACTO_ESPERADO, TOOLS_UTILIZADAS) embebido como bloque de "
        "comentario Octave valido (%{ OCTAVE_DOC: v1 ... %}) al inicio del "
        "archivo -- el archivo sigue siendo .m corriente y parseable. "
        "Modos: parse_doc extrae los campos del header; validate_doc "
        "chequea completitud del schema + sintaxis real del codigo (via "
        "octave_grammar_tool/octave-cli) y devuelve un recibo de "
        "validacion cuando pasa; write_doc valida y solo escribe a disco "
        "si PASSED, estampando el recibo en el archivo; eject proyecta el "
        "documento a una vista segun audiencia (view=executive: resumen "
        "sin codigo para quien decide; view=developer: vista tecnica con "
        "tools usadas y codigo completo; view=raw: documento original). "
        "mode=validate corre el autochequeo del tool."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["parse_doc", "validate_doc", "write_doc", "eject", "validate"],
            },
            "text": {"type": "string", "description": "contenido del documento .m (parse_doc, validate_doc, write_doc, eject)"},
            "path": {"type": "string", "description": "ruta de destino (write_doc)"},
            "check_syntax": {"type": "boolean", "description": "si valida tambien la sintaxis del codigo via octave_grammar_tool (default true)"},
            "view": {"type": "string", "enum": ["executive", "developer", "raw"], "description": "vista de proyeccion (eject, default executive)"},
        },
        "required": ["mode"],
    },
}


def _handler(args):
    args = dict(args or {})
    mode = args.pop("mode", "validate")
    params = args.pop("params", None) or {}
    merged = {**params, **args}
    return compute_octave_innovation_doc(mode=mode, **merged)


tool_registry.register_tool(
    "octave_innovation_doc_tool", OCTAVE_INNOVATION_DOC_TOOL_SCHEMA, _handler
)


if __name__ == "__main__":
    import json
    print(json.dumps(validate(), indent=2, ensure_ascii=False))
