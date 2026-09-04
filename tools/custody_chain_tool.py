#!/usr/bin/env python3
"""
custody_chain_tool.py
Cadena de custodia / trazabilidad forense para pipelines de analisis (ej.
bot_farm_pipeline_tool + data_provenance_tool). No almacena los datos crudos:
solo sus hashes, encadenados, para que cualquier alteracion posterior de un
paso del analisis (o del reporte final) sea detectable matematicamente.

Modelo: cada paso de analisis se registra como un "step" con hash de su
input y de su output. Los steps se encadenan (chain_hash = hash del
chain_hash anterior + todos los step_hash en orden), igual que un ledger
simple. Verificar el reporte = recalcular el chain_hash y compararlo.
Verificar un step contra los datos originales = recalcular sus hashes.

Modos:
  hash_data                -- utilidad: hash SHA-256 de un dato JSON-serializable
  record_analysis_step     -- registra un paso (tool/mode/commit/input/output) -> step dict
  build_chain_report       -- encadena N steps + metadata de caso -> reporte final
  verify_chain_report      -- recalcula chain_hash del reporte y detecta manipulacion
  verify_step_against_data -- recalcula hashes de un step contra datos crudos actuales
  validate                  -- self-test (incluye caso de manipulacion detectada)
"""

import hashlib
import json
import uuid
import datetime
import subprocess
import os

TOOL_NAME = "custody_chain_tool"

TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Cadena de custodia forense para pipelines de analisis: registra pasos "
        "con hashes encadenados (input/output/step/chain), permite verificar "
        "integridad de un reporte completo o de un paso individual contra los "
        "datos originales. No almacena datos crudos, solo sus hashes."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "hash_data",
                    "record_analysis_step",
                    "build_chain_report",
                    "verify_chain_report",
                    "verify_step_against_data",
                    "validate",
                ],
            },
            "data": {"description": "Dato arbitrario JSON-serializable a hashear (hash_data)."},
            "tool_name": {"type": "string"},
            "tool_mode": {"type": "string"},
            "git_commit": {"type": "string", "description": "Commit hash del tool usado (opcional, se autodetecta si se omite)."},
            "input_data": {"description": "Input crudo del paso de analisis (record_analysis_step / verify_step_against_data)."},
            "output_data": {"description": "Output crudo del paso de analisis (record_analysis_step / verify_step_against_data)."},
            "analyst": {"type": "string"},
            "case_id": {"type": "string"},
            "description": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "object"}, "description": "Lista de steps producidos por record_analysis_step."},
            "previous_chain_hash": {"type": "string", "description": "chain_hash de un reporte anterior, para encadenar sesiones (default GENESIS)."},
            "report": {"type": "object", "description": "Reporte completo a verificar (verify_chain_report)."},
            "step": {"type": "object", "description": "Un step individual a verificar (verify_step_against_data)."},
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------------------
# utilidades de hashing
# ---------------------------------------------------------------------------

def _canonical_json(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _sha256_of(obj):
    return hashlib.sha256(_canonical_json(obj).encode("utf-8")).hexdigest()


def _sha256_of_strings(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _autodetect_git_commit():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True, text=True, timeout=3,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# modos
# ---------------------------------------------------------------------------

def hash_data(params):
    data = params.get("data")
    return {"sha256": _sha256_of(data)}


def record_analysis_step(params):
    tool_name = params.get("tool_name")
    tool_mode = params.get("tool_mode")
    if not tool_name or not tool_mode:
        raise ValueError("record_analysis_step requiere 'tool_name' y 'tool_mode'")

    git_commit = params.get("git_commit") or _autodetect_git_commit()
    timestamp = params.get("_timestamp_override") or _now_iso()  # override solo para tests deterministicos
    input_hash = _sha256_of(params.get("input_data"))
    output_hash = _sha256_of(params.get("output_data"))
    analyst = params.get("analyst", "unspecified")

    step_hash = _sha256_of_strings(tool_name, tool_mode, git_commit, timestamp, input_hash, output_hash, analyst)

    return {
        "tool_name": tool_name,
        "tool_mode": tool_mode,
        "git_commit": git_commit,
        "analyst": analyst,
        "timestamp_utc": timestamp,
        "input_hash": input_hash,
        "output_hash": output_hash,
        "step_hash": step_hash,
    }


def _compute_chain_hash(previous_chain_hash, steps):
    parts = [previous_chain_hash] + [s["step_hash"] for s in steps]
    return _sha256_of_strings(*parts)


def build_chain_report(params):
    steps = params.get("steps") or []
    if not steps:
        raise ValueError("build_chain_report requiere al menos un step en 'steps'")
    for i, s in enumerate(steps):
        if "step_hash" not in s:
            raise ValueError(f"step {i} no tiene 'step_hash' -- usar record_analysis_step para generarlo")

    previous_chain_hash = params.get("previous_chain_hash", "GENESIS")
    chain_hash = _compute_chain_hash(previous_chain_hash, steps)

    report = {
        "report_id": str(uuid.uuid4()),
        "case_id": params.get("case_id", "unspecified"),
        "analyst": params.get("analyst", "unspecified"),
        "description": params.get("description", ""),
        "created_utc": _now_iso(),
        "n_steps": len(steps),
        "steps": steps,
        "previous_chain_hash": previous_chain_hash,
        "chain_hash": chain_hash,
        "verification_note": (
            "Para verificar integridad: llamar verify_chain_report con este reporte completo. "
            "Cualquier alteracion de un step o del orden invalida chain_hash. "
            "Para verificar un step especifico contra los datos crudos originales, "
            "usar verify_step_against_data con ese step + input_data/output_data reales."
        ),
    }
    return report


def verify_chain_report(params):
    report = params.get("report")
    if not report:
        raise ValueError("verify_chain_report requiere 'report'")

    steps = report.get("steps", [])
    previous_chain_hash = report.get("previous_chain_hash", "GENESIS")
    declared_chain_hash = report.get("chain_hash")

    expected_chain_hash = _compute_chain_hash(previous_chain_hash, steps)
    valid = (expected_chain_hash == declared_chain_hash)

    step_integrity = []
    for i, s in enumerate(steps):
        recomputed = _sha256_of_strings(
            s.get("tool_name"), s.get("tool_mode"), s.get("git_commit"),
            s.get("timestamp_utc"), s.get("input_hash"), s.get("output_hash"),
            s.get("analyst"),
        )
        step_integrity.append({
            "step_index": i,
            "declared_step_hash": s.get("step_hash"),
            "recomputed_step_hash": recomputed,
            "intact": recomputed == s.get("step_hash"),
        })

    all_steps_intact = all(x["intact"] for x in step_integrity)

    return {
        "valid": valid and all_steps_intact,
        "chain_hash_matches": valid,
        "all_steps_intact": all_steps_intact,
        "expected_chain_hash": expected_chain_hash,
        "declared_chain_hash": declared_chain_hash,
        "step_integrity": step_integrity,
        "interpretation": (
            "Reporte integro: nadie edito los steps ni el chain_hash despues de generado."
            if (valid and all_steps_intact) else
            "MANIPULACION DETECTADA: el chain_hash o algun step_hash no coincide con lo "
            "recalculado. El reporte fue editado despues de ser generado, o los steps "
            "fueron reordenados/alterados."
        ),
    }


def verify_step_against_data(params):
    step = params.get("step")
    if not step:
        raise ValueError("verify_step_against_data requiere 'step'")

    recomputed_input_hash = _sha256_of(params.get("input_data"))
    recomputed_output_hash = _sha256_of(params.get("output_data"))

    input_matches = recomputed_input_hash == step.get("input_hash")
    output_matches = recomputed_output_hash == step.get("output_hash")

    return {
        "input_hash_matches": input_matches,
        "output_hash_matches": output_matches,
        "data_unchanged": input_matches and output_matches,
        "declared_input_hash": step.get("input_hash"),
        "recomputed_input_hash": recomputed_input_hash,
        "declared_output_hash": step.get("output_hash"),
        "recomputed_output_hash": recomputed_output_hash,
        "interpretation": (
            "Los datos crudos proporcionados ahora producen los mismos hashes que se "
            "registraron en el momento del analisis: no fueron alterados desde entonces."
            if (input_matches and output_matches) else
            "Los datos proporcionados NO coinciden con los hashes registrados en el step: "
            "o no son los datos originales, o fueron modificados despues del analisis."
        ),
    }


# ---------------------------------------------------------------------------
# validate — self-test (incluye caso positivo, caso de manipulacion, y
# verificacion de datos contra step)
# ---------------------------------------------------------------------------

def validate(params=None):
    checks = {}

    step1 = record_analysis_step({
        "tool_name": "data_provenance_tool", "tool_mode": "score_source",
        "input_data": {"source": "official_api", "n": 40},
        "output_data": {"score": 0.9, "tier": "alta"},
        "analyst": "test_suite",
    })
    step2 = record_analysis_step({
        "tool_name": "kleinberg_burst_tool", "tool_mode": "detect_bursts",
        "input_data": {"n_events": 200},
        "output_data": {"n_bursts_detected": 1, "max_level": 7},
        "analyst": "test_suite",
    })

    report = build_chain_report({
        "case_id": "TEST-CASE-001",
        "analyst": "test_suite",
        "description": "pipeline sintetico de prueba",
        "steps": [step1, step2],
    })

    v_ok = verify_chain_report({"report": report})
    checks["intact_report_verifies_valid"] = {
        "valid": v_ok["valid"],
        "passed": v_ok["valid"] is True,
    }

    import copy
    tampered_report = copy.deepcopy(report)
    tampered_report["steps"][1]["output_hash"] = "0" * 64
    v_tampered = verify_chain_report({"report": tampered_report})
    checks["tampering_detected"] = {
        "valid": v_tampered["valid"],
        "passed": v_tampered["valid"] is False,
    }

    reordered_report = copy.deepcopy(report)
    reordered_report["steps"] = list(reversed(reordered_report["steps"]))
    v_reordered = verify_chain_report({"report": reordered_report})
    checks["reorder_detected"] = {
        "chain_hash_matches": v_reordered["chain_hash_matches"],
        "passed": v_reordered["chain_hash_matches"] is False,
    }

    v_data_ok = verify_step_against_data({
        "step": step1,
        "input_data": {"source": "official_api", "n": 40},
        "output_data": {"score": 0.9, "tier": "alta"},
    })
    checks["step_data_verification_matches"] = {
        "data_unchanged": v_data_ok["data_unchanged"],
        "passed": v_data_ok["data_unchanged"] is True,
    }

    v_data_bad = verify_step_against_data({
        "step": step1,
        "input_data": {"source": "official_api", "n": 999},
        "output_data": {"score": 0.9, "tier": "alta"},
    })
    checks["step_data_tamper_detected"] = {
        "data_unchanged": v_data_bad["data_unchanged"],
        "passed": v_data_bad["data_unchanged"] is False,
    }

    all_passed = all(c["passed"] for c in checks.values())
    return {"validation_passed": all_passed, "checks": checks}


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

_DISPATCH = {
    "hash_data": hash_data,
    "record_analysis_step": record_analysis_step,
    "build_chain_report": build_chain_report,
    "verify_chain_report": verify_chain_report,
    "verify_step_against_data": verify_step_against_data,
    "validate": validate,
}


def run(params):
    mode = params.get("mode")
    if mode not in _DISPATCH:
        raise ValueError(f"mode desconocido: {mode!r}. Modos validos: {list(_DISPATCH.keys())}")
    return _DISPATCH[mode](params)


try:
    import tool_registry as _treg
    _treg.register_tool(TOOL_NAME, TOOL_SCHEMA, run)
except ImportError:
    pass


if __name__ == "__main__":
    print(json.dumps(run({"mode": "validate"}), indent=2, ensure_ascii=False))
