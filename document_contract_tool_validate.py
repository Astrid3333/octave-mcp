"""
Self-test genérico para document_contract_tool.py.

Esto NO es el arnés run_all_validations.py del repo real (no lo tengo a
la vista). Es un chequeo funcional propio: casos felices + casos de error
a propósito, para las tres funciones públicas.
"""

import sys
import traceback

from document_contract_tool import (
    contract_define,
    contract_validate,
    grammar_compile,
    ContractError,
    _validate_self,
)

PASS = []
FAIL = []


def check(label, fn):
    try:
        fn()
        PASS.append(label)
        print(f"  OK  {label}")
    except AssertionError as e:
        FAIL.append((label, str(e)))
        print(f"FAIL  {label}: {e}")
    except Exception as e:
        FAIL.append((label, f"{type(e).__name__}: {e}"))
        print(f"FAIL  {label}: {type(e).__name__}: {e}")
        traceback.print_exc()


# ---------------------------------------------------------------------------
# contract_define
# ---------------------------------------------------------------------------

def t_define_basic():
    schema = contract_define(
        "incident_report_v1",
        [
            {"name": "title", "type": "string", "required": True},
            {"name": "severity", "type": "integer", "min": 1, "max": 5},
            {"name": "resolved", "type": "boolean", "required": False},
            {"name": "tags", "type": "array_of_string", "min_items": 1, "max_items": 5},
            {"name": "status", "type": "string", "enum": ["open", "closed"]},
        ],
    )
    assert schema["name"] == "incident_report_v1"
    assert len(schema["fields"]) == 5
    assert schema["saved"] is False  # sin run_id


def t_define_duplicate_field():
    try:
        contract_define("x", [
            {"name": "a", "type": "string"},
            {"name": "a", "type": "integer"},
        ])
        assert False, "debía lanzar ContractError por campo duplicado"
    except ContractError:
        pass


def t_define_bad_type():
    try:
        contract_define("x", [{"name": "a", "type": "object"}])
        assert False, "debía lanzar ContractError por tipo no soportado"
    except ContractError:
        pass


def t_define_min_gt_max():
    try:
        contract_define("x", [{"name": "a", "type": "integer", "min": 10, "max": 1}])
        assert False, "debía lanzar ContractError por min > max"
    except ContractError:
        pass


def t_define_enum_on_bad_type():
    try:
        contract_define("x", [{"name": "a", "type": "boolean", "enum": [True]}])
        assert False, "debía lanzar ContractError por enum en boolean"
    except ContractError:
        pass


def t_define_empty_fields():
    try:
        contract_define("x", [])
        assert False, "debía lanzar ContractError por fields vacío"
    except ContractError:
        pass


def t_define_run_id_with_workspace():
    # Ahora sí existe workspace_tool.py (stub) en esta carpeta -> saved debe ser True.
    schema = contract_define("x", [{"name": "a", "type": "string"}], run_id="run-123")
    assert schema["saved"] is True
    assert schema["run_id"] == "run-123"


# ---------------------------------------------------------------------------
# contract_validate
# ---------------------------------------------------------------------------

SCHEMA = contract_define(
    "incident_report_v1",
    [
        {"name": "title", "type": "string", "required": True},
        {"name": "severity", "type": "integer", "min": 1, "max": 5},
        {"name": "resolved", "type": "boolean", "required": False},
        {"name": "tags", "type": "array_of_string", "min_items": 1, "max_items": 3},
        {"name": "status", "type": "string", "enum": ["open", "closed"]},
    ],
)


def t_validate_valid_doc():
    doc = {
        "title": "server down",
        "severity": 3,
        "resolved": False,
        "tags": ["prod", "urgent"],
        "status": "open",
    }
    result = contract_validate(doc, SCHEMA)
    assert result["valid"] is True, result["errors"]
    assert result["errors"] == []
    assert set(result["checked_fields"]) == {"title", "severity", "resolved", "tags", "status"}


def t_validate_missing_required():
    doc = {"severity": 3, "status": "open", "tags": ["a"]}
    result = contract_validate(doc, SCHEMA)
    assert result["valid"] is False
    assert any("title" in e for e in result["errors"])


def t_validate_missing_optional_ok():
    doc = {"title": "x", "severity": 1, "status": "open", "tags": ["a"]}
    result = contract_validate(doc, SCHEMA)
    assert result["valid"] is True, result["errors"]


def t_validate_wrong_type():
    doc = {"title": 123, "severity": 1, "status": "open", "tags": ["a"]}
    result = contract_validate(doc, SCHEMA)
    assert result["valid"] is False
    assert any("title" in e for e in result["errors"])


def t_validate_bool_not_integer():
    # bool es subclase de int en Python -> no debe colarse como integer
    doc = {"title": "x", "severity": True, "status": "open", "tags": ["a"]}
    result = contract_validate(doc, SCHEMA)
    assert result["valid"] is False
    assert any("severity" in e for e in result["errors"])


def t_validate_out_of_range():
    doc = {"title": "x", "severity": 99, "status": "open", "tags": ["a"]}
    result = contract_validate(doc, SCHEMA)
    assert result["valid"] is False
    assert any("severity" in e for e in result["errors"])


def t_validate_bad_enum():
    doc = {"title": "x", "severity": 1, "status": "PENDING", "tags": ["a"]}
    result = contract_validate(doc, SCHEMA)
    assert result["valid"] is False
    assert any("status" in e for e in result["errors"])


def t_validate_array_min_items():
    doc = {"title": "x", "severity": 1, "status": "open", "tags": []}
    result = contract_validate(doc, SCHEMA)
    assert result["valid"] is False
    assert any("tags" in e for e in result["errors"])


def t_validate_array_wrong_element_type():
    doc = {"title": "x", "severity": 1, "status": "open", "tags": ["a", 5]}
    result = contract_validate(doc, SCHEMA)
    assert result["valid"] is False
    assert any("tags" in e for e in result["errors"])


def t_validate_accepts_raw_field_list():
    # contract_validate debe aceptar también una lista de specs directamente
    # (no solo el dict devuelto por contract_define)
    result = contract_validate({"a": "hi"}, [{"name": "a", "type": "string"}])
    assert result["valid"] is True, result["errors"]


def t_validate_document_not_dict():
    result = contract_validate(["not", "a", "dict"], SCHEMA)
    assert result["valid"] is False
    assert result["checked_fields"] == []


def t_validate_via_run_id():
    contract_define("via_run", [{"name": "a", "type": "string"}], run_id="run-abc")
    result = contract_validate({"a": "hi"}, run_id="run-abc")
    assert result["valid"] is True, result["errors"]


def t_validate_missing_schema_and_run_id():
    result = contract_validate({"a": "hi"})
    assert result["valid"] is False
    assert "schema" in result["errors"][0] or "run_id" in result["errors"][0]


def t_validate_unknown_run_id():
    result = contract_validate({"a": "hi"}, run_id="does-not-exist")
    assert result["valid"] is False
    assert "does-not-exist" in result["errors"][0]


# ---------------------------------------------------------------------------
# grammar_compile
# ---------------------------------------------------------------------------

def t_grammar_compile_basic():
    gbnf = grammar_compile(SCHEMA)
    assert "root ::=" in gbnf
    assert "field-title" in gbnf
    assert "field-severity" in gbnf
    assert "field-resolved" in gbnf
    assert "field-tags" in gbnf
    assert "field-status" in gbnf
    assert "string-value" in gbnf
    assert "integer-value" in gbnf
    assert "boolean-value" in gbnf
    assert "array-of-string-value" in gbnf


def t_grammar_compile_enum_inlined():
    schema = contract_define("x", [{"name": "status", "type": "string", "enum": ["open", "closed"]}])
    gbnf = grammar_compile(schema)
    assert '"open"' in gbnf
    assert '"closed"' in gbnf


def t_grammar_compile_empty_schema():
    try:
        grammar_compile({"fields": []})
        assert False, "debía lanzar ContractError con fields vacío"
    except ContractError:
        pass


def t_grammar_compile_field_order_fixed():
    # Confirma explícitamente la limitación documentada: el orden de
    # field-* en object-body sigue el orden de declaración del esquema.
    schema = contract_define("x", [
        {"name": "z_field", "type": "string"},
        {"name": "a_field", "type": "string"},
    ])
    gbnf = grammar_compile(schema)
    body_line = [l for l in gbnf.splitlines() if l.startswith("object-body")][0]
    assert body_line.index("field-z_field") < body_line.index("field-a_field")


def t_grammar_compile_accepts_raw_list():
    gbnf = grammar_compile([{"name": "a", "type": "string"}])
    assert "field-a" in gbnf


def t_grammar_compile_via_run_id():
    contract_define("via_run_gbnf", [{"name": "b", "type": "integer"}], run_id="run-xyz")
    gbnf = grammar_compile(run_id="run-xyz")
    assert "field-b" in gbnf


def t_grammar_compile_missing_schema_and_run_id():
    try:
        grammar_compile()
        assert False, "debía lanzar ContractError sin schema ni run_id"
    except ContractError:
        pass


def t_validate_self_mode():
    result = _validate_self()
    assert result["valid"] is True, result["checks"]
    assert len(result["checks"]) == 3


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------

def main():
    tests = [obj for name, obj in list(globals().items()) if name.startswith("t_")]
    tests.sort(key=lambda f: f.__name__)
    print(f"Corriendo {len(tests)} tests...\n")
    for t in tests:
        check(t.__name__, t)

    print(f"\n{len(PASS)} OK, {len(FAIL)} FAIL")
    if FAIL:
        print("\nFallos:")
        for label, msg in FAIL:
            print(f"  - {label}: {msg}")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
