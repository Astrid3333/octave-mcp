"""
document_contract_tool
=======================

Meta-tooling para que un LLM cliente sepa, ANTES de generar output, qué forma
tiene que tener ese output. Tres modos:

    - contract_define    : define y valida un esquema de campos (opcionalmente
                            lo guarda con un run_id).
    - contract_validate  : valida un documento (dict) contra un esquema,
                            recibido inline o cargado por run_id.
    - grammar_compile     : compila un esquema (inline o por run_id) a una
                            gramática GBNF (formato llama.cpp) para forzar
                            generación estructurada en modelos que soportan
                            grammar-constrained decoding.

NOTA DE INTEGRACIÓN (leer antes de mergear al repo real)
----------------------------------------------------------
Este archivo se integra contra `tool_registry.py` y `workspace_tool.py`
locales a esta carpeta — *** ambos son STUBS construidos por Claude, NO
son los archivos reales de octave-mcp ***. No tuve acceso al repo
(privado, sin red saliente en este entorno). Son implementaciones
plausibles para poder cablear y correr algo de punta a punta, no una
copia de tus convenciones reales.

Cuando tengas el repo real a mano, lo que hay que revisar:

  1. La firma de `register_tool(name, description, modes)` — puede
     diferir (kwargs, decorador en vez de llamada directa, campos
     adicionales requeridos).
  2. La firma de `save_run(run_id, tool_name, payload)` en
     `workspace_tool` — asumida por analogía con `temperature_sweep`,
     no confirmada.
  3. El modo `validate` que agrego abajo (`_validate_self`) corre un
     puñado de chequeos internos y devuelve `{"valid": bool, "checks": [...]}`
     — imité la forma más simple posible para que
     `run_all_validations.py` tenga algo que ejecutar, pero el shape
     real que usan las otras 86 tools con validate puede ser distinto.
  4. `contract_validate(run_id=...)` y `grammar_compile(run_id=...)`
     ahora soportan cargar el contrato guardado por `contract_define`
     en vez de recibirlo inline (vía `workspace_tool.load_run`, buscando
     la entrada más reciente con tool_name == "document_contract_tool").
     Asume que `load_run` devuelve una lista en orden de guardado — si
     el `load_run` real devuelve otra forma (ordenado distinto, paginado,
     etc), hay que ajustar `_load_contract_from_run`.

El módulo `validate.py` (self-test, ahora 27 casos) es independiente de
todo esto y no cambia.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple, Union


# ---------------------------------------------------------------------------
# Tipos de campo soportados (primer corte, sin objetos anidados)
# ---------------------------------------------------------------------------

SUPPORTED_TYPES = {"string", "number", "integer", "boolean", "array_of_string"}


class ContractError(Exception):
    """Error al definir o compilar un contrato (esquema inválido en sí mismo)."""


# ---------------------------------------------------------------------------
# contract_define
# ---------------------------------------------------------------------------

def contract_define(
    name: str,
    fields: List[Dict[str, Any]],
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Define y normaliza un esquema de contrato de documento.

    Args:
        name: nombre del contrato (ej. "incident_report_v1").
        fields: lista de specs de campo. Cada spec:
            {
                "name": str,                # requerido
                "type": str,                # requerido, uno de SUPPORTED_TYPES
                "required": bool,           # default True
                "enum": [valores],          # opcional, solo string/integer/number
                "min": number,              # opcional, solo number/integer
                "max": number,              # opcional, solo number/integer
                "min_items": int,           # opcional, solo array_of_string
                "max_items": int,           # opcional, solo array_of_string
            }
        run_id: si se provee, intenta guardar el contrato en el workspace
                (best-effort, ver _maybe_save_run).

    Returns:
        {
            "name": str,
            "fields": [...campos normalizados...],
            "run_id": str | None,
            "saved": bool,
        }

    Raises:
        ContractError si el esquema es inválido (tipo desconocido, nombre
        duplicado, rango incoherente, etc).
    """
    if not name or not isinstance(name, str):
        raise ContractError("'name' debe ser un string no vacío")

    if not fields or not isinstance(fields, list):
        raise ContractError("'fields' debe ser una lista no vacía")

    seen_names = set()
    normalized: List[Dict[str, Any]] = []

    for i, raw in enumerate(fields):
        if not isinstance(raw, dict):
            raise ContractError(f"fields[{i}] debe ser un dict, recibí {type(raw).__name__}")

        fname = raw.get("name")
        ftype = raw.get("type")

        if not fname or not isinstance(fname, str):
            raise ContractError(f"fields[{i}]: 'name' debe ser un string no vacío")
        if fname in seen_names:
            raise ContractError(f"campo duplicado: '{fname}'")
        seen_names.add(fname)

        if ftype not in SUPPORTED_TYPES:
            raise ContractError(
                f"fields[{i}] ('{fname}'): tipo '{ftype}' no soportado. "
                f"Válidos: {sorted(SUPPORTED_TYPES)}"
            )

        field: Dict[str, Any] = {
            "name": fname,
            "type": ftype,
            "required": bool(raw.get("required", True)),
        }

        # --- enum: solo tiene sentido en string / integer / number ---
        if "enum" in raw and raw["enum"] is not None:
            if ftype not in ("string", "integer", "number"):
                raise ContractError(
                    f"fields[{i}] ('{fname}'): 'enum' no es válido para tipo '{ftype}'"
                )
            enum_vals = raw["enum"]
            if not isinstance(enum_vals, list) or len(enum_vals) == 0:
                raise ContractError(f"fields[{i}] ('{fname}'): 'enum' debe ser una lista no vacía")
            field["enum"] = list(enum_vals)

        # --- min/max: solo number / integer ---
        has_min = "min" in raw and raw["min"] is not None
        has_max = "max" in raw and raw["max"] is not None
        if (has_min or has_max) and ftype not in ("number", "integer"):
            raise ContractError(
                f"fields[{i}] ('{fname}'): 'min'/'max' no son válidos para tipo '{ftype}'"
            )
        if has_min:
            field["min"] = raw["min"]
        if has_max:
            field["max"] = raw["max"]
        if has_min and has_max and raw["min"] > raw["max"]:
            raise ContractError(
                f"fields[{i}] ('{fname}'): 'min' ({raw['min']}) > 'max' ({raw['max']})"
            )

        # --- min_items/max_items: solo array_of_string ---
        has_min_items = "min_items" in raw and raw["min_items"] is not None
        has_max_items = "max_items" in raw and raw["max_items"] is not None
        if (has_min_items or has_max_items) and ftype != "array_of_string":
            raise ContractError(
                f"fields[{i}] ('{fname}'): 'min_items'/'max_items' solo válidos para array_of_string"
            )
        if has_min_items:
            if not isinstance(raw["min_items"], int) or raw["min_items"] < 0:
                raise ContractError(f"fields[{i}] ('{fname}'): 'min_items' debe ser int >= 0")
            field["min_items"] = raw["min_items"]
        if has_max_items:
            if not isinstance(raw["max_items"], int) or raw["max_items"] < 0:
                raise ContractError(f"fields[{i}] ('{fname}'): 'max_items' debe ser int >= 0")
            field["max_items"] = raw["max_items"]
        if has_min_items and has_max_items and raw["min_items"] > raw["max_items"]:
            raise ContractError(
                f"fields[{i}] ('{fname}'): 'min_items' > 'max_items'"
            )

        normalized.append(field)

    result = {
        "name": name,
        "fields": normalized,
        "run_id": run_id,
        "saved": False,
    }

    if run_id:
        result["saved"] = _maybe_save_run(run_id, {"name": name, "fields": normalized})

    return result


# ---------------------------------------------------------------------------
# contract_validate
# ---------------------------------------------------------------------------

def contract_validate(
    document: Dict[str, Any],
    schema: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Valida un documento (dict) contra un esquema de campos.

    Args:
        document: el documento a validar (ej. un JSON ya parseado).
        schema: ya sea el output de contract_define (dict con clave "fields"),
                o directamente la lista de specs de campo normalizadas.
                Opcional si se provee `run_id` (ver abajo).
        run_id: si se provee y `schema` es None, intenta cargar el contrato
                guardado bajo ese run_id (vía workspace_tool.load_run) en
                lugar de recibirlo inline. Si se pasan ambos, `schema` gana
                y `run_id` se ignora.

    Returns:
        {
            "valid": bool,
            "errors": [str, ...],       # vacío si valid=True
            "checked_fields": [str, ...],  # nombres de campos evaluados
        }
    """
    if schema is None:
        if run_id is None:
            return {
                "valid": False,
                "errors": ["hay que proveer 'schema' o 'run_id'"],
                "checked_fields": [],
            }
        loaded, err = _load_contract_from_run(run_id)
        if err:
            return {"valid": False, "errors": [err], "checked_fields": []}
        schema = loaded

    if isinstance(schema, dict) and "fields" in schema:
        fields = schema["fields"]
    elif isinstance(schema, list):
        fields = schema
    else:
        return {
            "valid": False,
            "errors": ["'schema' debe ser un dict con clave 'fields' o una lista de specs de campo"],
            "checked_fields": [],
        }

    if not isinstance(document, dict):
        return {
            "valid": False,
            "errors": [f"'document' debe ser un dict, recibí {type(document).__name__}"],
            "checked_fields": [],
        }

    errors: List[str] = []
    checked: List[str] = []

    for field in fields:
        fname = field["name"]
        ftype = field["type"]
        required = field.get("required", True)
        checked.append(fname)

        present = fname in document
        if not present:
            if required:
                errors.append(f"'{fname}': falta campo requerido")
            continue

        value = document[fname]
        type_ok, type_err = _check_type(value, ftype)
        if not type_ok:
            errors.append(f"'{fname}': {type_err}")
            continue

        # enum
        if "enum" in field and value not in field["enum"]:
            errors.append(f"'{fname}': valor {value!r} no está en enum {field['enum']}")

        # min/max (number/integer)
        if ftype in ("number", "integer"):
            if "min" in field and value < field["min"]:
                errors.append(f"'{fname}': {value} < min ({field['min']})")
            if "max" in field and value > field["max"]:
                errors.append(f"'{fname}': {value} > max ({field['max']})")

        # min_items/max_items (array_of_string)
        if ftype == "array_of_string":
            n = len(value)
            if "min_items" in field and n < field["min_items"]:
                errors.append(f"'{fname}': tiene {n} items, mínimo {field['min_items']}")
            if "max_items" in field and n > field["max_items"]:
                errors.append(f"'{fname}': tiene {n} items, máximo {field['max_items']}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "checked_fields": checked,
    }


def _check_type(value: Any, ftype: str) -> Tuple[bool, str]:
    """Chequea el tipo de `value` contra `ftype`. bool antes que int/number
    porque en Python bool es subclase de int (True/False no deben pasar
    como integer/number)."""
    if ftype == "string":
        return (isinstance(value, str), f"esperaba string, recibí {type(value).__name__}")
    if ftype == "boolean":
        return (isinstance(value, bool), f"esperaba boolean, recibí {type(value).__name__}")
    if ftype == "integer":
        ok = isinstance(value, int) and not isinstance(value, bool)
        return (ok, f"esperaba integer, recibí {type(value).__name__}")
    if ftype == "number":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        return (ok, f"esperaba number, recibí {type(value).__name__}")
    if ftype == "array_of_string":
        ok = isinstance(value, list) and all(isinstance(x, str) for x in value)
        return (ok, "esperaba lista de strings")
    return (False, f"tipo desconocido: {ftype}")


# ---------------------------------------------------------------------------
# grammar_compile -> GBNF (formato llama.cpp)
# ---------------------------------------------------------------------------
#
# LIMITACIÓN REAL (no es un detalle menor): GBNF genera una gramática de
# PRODUCCIÓN, no una gramática de VALIDACIÓN. Para un objeto JSON, eso
# implica que el orden de los campos en el output queda FIJO en el orden
# en que aparecen en el esquema — GBNF no puede expresar "estos N campos
# en cualquier orden" sin una explosión combinatoria de reglas (N!
# alternativas). Esto es aceptable para forzar generación (el modelo
# simplemente los emite en ese orden), pero significa que grammar_compile
# NO es un traductor fiel de JSON Schema: es una gramática de generación
# derivada de él, con esa restricción de orden fijo.
#
# Tampoco soporta (en este primer corte): objetos anidados, additionalProperties,
# oneOf/anyOf, ni arrays de tipos mixtos.

def grammar_compile(schema: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None, run_id: Optional[str] = None) -> str:
    """
    Compila un esquema (mismo shape que contract_define) a una gramática
    GBNF (formato llama.cpp) que fuerza al modelo a generar un objeto JSON
    con esa forma.

    Args:
        schema: dict con clave "fields", o lista de specs de campo.
                Opcional si se provee `run_id`.
        run_id: si se provee y `schema` es None, carga el contrato guardado
                bajo ese run_id (vía workspace_tool.load_run).

    Returns:
        str: la gramática GBNF completa, lista para pasar a
             --grammar-file en llama.cpp (o al parámetro equivalente).

    Raises:
        ContractError si el esquema tiene un tipo no soportado por GBNF
        en este primer corte, o si no se pudo resolver un esquema a partir
        de run_id.
    """
    if schema is None:
        if run_id is None:
            raise ContractError("hay que proveer 'schema' o 'run_id'")
        loaded, err = _load_contract_from_run(run_id)
        if err:
            raise ContractError(err)
        schema = loaded

    if isinstance(schema, dict) and "fields" in schema:
        fields = schema["fields"]
    elif isinstance(schema, list):
        fields = schema
    else:
        raise ContractError("'schema' debe ser un dict con clave 'fields' o una lista de specs de campo")

    if not fields:
        raise ContractError("el esquema no tiene campos, no se puede compilar una gramática")

    lines: List[str] = []
    lines.append("# Gramática generada por document_contract_tool.grammar_compile")
    lines.append("# NOTA: el orden de los campos abajo es FIJO (limitación de GBNF, ver docstring).")
    lines.append("")
    lines.append('root ::= "{" ws object-body "}" ws')
    lines.append("")

    # cuerpo del objeto: campo1 "," campo2 "," ... campoN  (orden fijo)
    field_rule_names = [f"field-{f['name']}" for f in fields]
    body = ' "," ws '.join(field_rule_names)
    lines.append(f"object-body ::= {field_rule_names[0]}" + (
        (" ws \",\" ws " + " ws \",\" ws ".join(field_rule_names[1:])) if len(field_rule_names) > 1 else ""
    ))
    lines.append("")

    for field in fields:
        fname = field["name"]
        ftype = field["type"]
        rule_name = f"field-{fname}"
        key = json.dumps(fname)  # string JSON-escapado

        value_rule = _gbnf_value_rule(field)
        lines.append(f'{rule_name} ::= {key} ws ":" ws {value_rule}')

    lines.append("")
    lines.extend(_GBNF_PRIMITIVES)

    return "\n".join(lines)


def _gbnf_value_rule(field: Dict[str, Any]) -> str:
    ftype = field["type"]
    fname = field["name"]

    if ftype == "string":
        if "enum" in field:
            alts = " | ".join(json.dumps(v) for v in field["enum"])
            return f"({alts})"
        return "string-value"

    if ftype == "boolean":
        return "boolean-value"

    if ftype == "integer":
        if "enum" in field:
            alts = " | ".join(json.dumps(v) for v in field["enum"])
            return f"({alts})"
        return "integer-value"

    if ftype == "number":
        if "enum" in field:
            alts = " | ".join(json.dumps(v) for v in field["enum"])
            return f"({alts})"
        return "number-value"

    if ftype == "array_of_string":
        return "array-of-string-value"

    raise ContractError(f"campo '{fname}': tipo '{ftype}' no soportado por grammar_compile")


# Reglas primitivas GBNF reutilizables (número, string, boolean, array de
# strings, whitespace). Basadas en la gramática JSON de referencia de
# llama.cpp (grammars/json.gbnf), acotadas a lo que este módulo necesita.
_GBNF_PRIMITIVES = [
    'ws ::= [ \\t\\n]*',
    "",
    'string-value ::= \"\\\"\" string-char* \"\\\"\"',
    'string-char ::= [^\"\\\\] | \"\\\\\" ([\"\\\\/bfnrt] | \"u\" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F])',
    "",
    'integer-value ::= \"-\"? ([0-9] | [1-9] [0-9]*)',
    "",
    'number-value ::= integer-value (\".\" [0-9]+)? ([eE] [-+]? [0-9]+)?',
    "",
    'boolean-value ::= \"true\" | \"false\"',
    "",
    'array-of-string-value ::= \"[\" ws (string-value (\",\" ws string-value)*)? ws \"]\"',
]


# ---------------------------------------------------------------------------
# Integración con workspace_tool.save_run (best-effort, ver nota al tope)
# ---------------------------------------------------------------------------

def _maybe_save_run(run_id: str, contract_payload: Dict[str, Any]) -> bool:
    """
    Guarda el contrato (name + fields) bajo run_id, serializado a JSON
    string dentro de 'data' -- necesario porque el save_run real del repo
    convierte cada valor de 'data' a np.ndarray, y 'fields' es una lista
    de dicts anidados (no soportado sin allow_pickle). Un string JSON se
    guarda limpio como array 0-d de texto.
    """
    try:
        from workspace_tool import save_run  # type: ignore
    except ImportError:
        return False
    try:
        save_run(
            run_id,
            data={"contract_json": json.dumps(contract_payload)},
            meta={"tool": "document_contract_tool", "contract_name": contract_payload.get("name")},
        )
        return True
    except Exception:
        return False


def _load_contract_from_run(run_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Carga el contrato guardado por contract_define bajo run_id, vía
    workspace_tool.load_run(run_id). load_run real devuelve
    {"data": {...}, "meta": {...}} o {"error": "..."} si no existe.
    Devuelve (contrato, None) o (None, mensaje_de_error).
    """
    try:
        from workspace_tool import load_run  # type: ignore
    except ImportError:
        return None, "workspace_tool.load_run no está disponible en este entorno"

    try:
        result = load_run(run_id)
    except Exception as e:
        return None, f"error cargando run_id '{run_id}': {type(e).__name__}: {e}"

    if isinstance(result, dict) and "error" in result:
        return None, result["error"]

    data = result.get("data", {}) if isinstance(result, dict) else {}
    contract_json = data.get("contract_json")
    if contract_json is None:
        return None, f"run_id '{run_id}' no tiene un contrato guardado por document_contract_tool (falta 'contract_json')"

    try:
        return json.loads(contract_json), None
    except Exception as e:
        return None, f"error parseando contrato guardado en run_id '{run_id}': {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# modo "validate" — para que run_all_validations.py tenga algo que correr
# (imitando el patrón de las otras 86 tools reales que exponen este modo)
# ---------------------------------------------------------------------------

def _validate_self() -> Dict[str, Any]:
    """
    Self-check liviano de las tres funciones públicas, pensado para correr
    rápido dentro de un hook pre-push (no reemplaza el self-test completo
    de validate.py, que tiene 23 casos). Devuelve {"valid": bool, "checks": [...]}.
    """
    checks = []

    def record(label, fn):
        try:
            fn()
            checks.append({"check": label, "ok": True})
        except Exception as e:
            checks.append({"check": label, "ok": False, "error": f"{type(e).__name__}: {e}"})

    def c1():
        schema = contract_define("smoke_test", [{"name": "a", "type": "string"}])
        assert schema["fields"][0]["name"] == "a"

    def c2():
        schema = contract_define("smoke_test", [{"name": "a", "type": "string"}])
        result = contract_validate({"a": "x"}, schema)
        assert result["valid"] is True

    def c3():
        schema = contract_define("smoke_test", [{"name": "a", "type": "string"}])
        gbnf = grammar_compile(schema)
        assert "field-a" in gbnf

    record("contract_define produces expected shape", c1)
    record("contract_validate accepts a valid document", c2)
    record("grammar_compile produces GBNF referencing declared fields", c3)

    return {"valid": all(c["ok"] for c in checks), "checks": checks}


# ---------------------------------------------------------------------------
# dispatcher + inputSchema + registro, siguiendo el patrón real del repo
# (grepeado de statmech_partition_tool.py: schema plano con inputSchema,
# handler único que despacha por args.get("mode"), todo el register_tool
# envuelto en try/except ImportError). NO MÁS STUBS de tool_registry acá —
# esto apunta al tool_registry.py real del repo.
# ---------------------------------------------------------------------------

DOCUMENT_CONTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["contract_define", "contract_validate", "grammar_compile", "validate"],
            "description": "Qué operación ejecutar.",
        },
        # --- contract_define ---
        "name": {
            "type": "string",
            "description": "[contract_define] nombre del contrato, ej. 'incident_report_v1'.",
        },
        "fields": {
            "type": "array",
            "description": (
                "[contract_define] lista de specs de campo: "
                "{name, type (string|number|integer|boolean|array_of_string), "
                "required, enum?, min?, max?, min_items?, max_items?}."
            ),
            "items": {"type": "object"},
        },
        # --- contract_validate ---
        "document": {
            "type": "object",
            "description": "[contract_validate] documento a validar contra el esquema.",
        },
        "schema": {
            "description": (
                "[contract_validate, grammar_compile] esquema inline: dict con "
                "clave 'fields' (output de contract_define) o lista de specs de "
                "campo. Alternativa a 'run_id'."
            ),
        },
        # --- común a contract_define / contract_validate / grammar_compile ---
        "run_id": {
            "type": "string",
            "description": (
                "[contract_define] guarda el contrato bajo este run_id. "
                "[contract_validate, grammar_compile] carga el contrato guardado "
                "bajo este run_id en vez de recibir 'schema' inline."
            ),
        },
    },
    "required": ["mode"],
}


def compute_document_contract(mode: Optional[str], args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dispatcher único para las cuatro operaciones del contrato de documento.
    Mismo patrón que compute_statmech_partition: recibe el modo y el dict
    completo de args, despacha, y devuelve un dict serializable a JSON.
    """
    args = args or {}

    if mode == "contract_define":
        try:
            return contract_define(
                name=args.get("name"),
                fields=args.get("fields"),
                run_id=args.get("run_id"),
            )
        except ContractError as e:
            return {"error": str(e)}

    if mode == "contract_validate":
        return contract_validate(
            document=args.get("document"),
            schema=args.get("schema"),
            run_id=args.get("run_id"),
        )

    if mode == "grammar_compile":
        try:
            gbnf = grammar_compile(schema=args.get("schema"), run_id=args.get("run_id"))
            return {"gbnf": gbnf}
        except ContractError as e:
            return {"error": str(e)}

    if mode == "validate":
        return _validate_self()

    return {"error": f"modo desconocido: '{mode}'. Válidos: contract_define, contract_validate, grammar_compile, validate"}


try:
    from tool_registry import register_tool  # type: ignore

    register_tool(
        name="document_contract_tool",
        schema={
            "name": "document_contract_tool",
            "description": (
                "Meta-tooling: define contratos de documento (contract_define), "
                "valida documentos contra un contrato (contract_validate), y "
                "compila un contrato a gramatica GBNF para generacion forzada "
                "(grammar_compile). Los contratos se pueden guardar/cargar por "
                "run_id via workspace_tool."
            ),
            "inputSchema": DOCUMENT_CONTRACT_SCHEMA,
        },
        handler=lambda args: compute_document_contract(args.get("mode"), args),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(compute_document_contract("validate", {}), indent=2, ensure_ascii=False))
