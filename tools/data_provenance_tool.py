#!/usr/bin/env python3
"""
data_provenance_tool.py
Scoring de procedencia/confiabilidad de fuentes de datos para pipelines de
deteccion de desinformacion/bots. No reemplaza verificacion humana ni fact-
checking real -- da un puntaje estructurado basado en como se obtuvo el dato,
no en si el contenido es verdadero.

Modos:
  score_source          -- puntaja una sola fuente segun su metodo de obtencion
  cross_reference_check -- corrobora una afirmacion contra multiples fuentes
                            independientes y ajusta el score por consenso
  flag_unverifiable     -- procesa un batch de registros, filtra/pondera segun
                            umbral de confianza minimo
  validate               -- self-test
"""

TOOL_NAME = "data_provenance_tool"

TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["score_source", "cross_reference_check", "flag_unverifiable", "validate"],
        },
        "params": {
            "type": "object",
            "properties": {
                "source_type": {
                    "type": "string",
                    "enum": [
                        "official_api_authenticated",
                        "scrape_verifiable_metadata",
                        "scrape_no_metadata",
                        "screenshot_no_metadata",
                        "third_party_unverified",
                        "user_generated_no_trace",
                    ],
                    "description": "score_source: metodo de obtencion del dato.",
                },
                "n_independent_sources": {
                    "type": "integer",
                    "description": "score_source (opcional) / cross_reference_check: cuantas fuentes independientes reportan lo mismo.",
                },
                "has_timestamp_verifiable": {
                    "type": "boolean",
                    "description": "score_source: si el timestamp puede verificarse contra un tercero (ej. Wayback Machine, API del propio dato).",
                },
                "claims": {
                    "type": "array",
                    "description": "cross_reference_check: lista de afirmaciones/observaciones, cada una con su source_type.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source_type": {"type": "string"},
                            "value": {},
                        },
                    },
                },
                "records": {
                    "type": "array",
                    "description": "flag_unverifiable: lista de registros, cada uno con source_type y datos asociados.",
                    "items": {"type": "object"},
                },
                "min_confidence_threshold": {
                    "type": "number",
                    "description": "flag_unverifiable: umbral minimo (0-1) de confianza para no descartar el registro. Default 0.3.",
                },
            },
        },
    },
    "required": ["mode"],
    "name": TOOL_NAME,
}


# ---------------------------------------------------------------------------
# Tabla base de confianza por tipo de fuente
# ---------------------------------------------------------------------------

_BASE_CONFIDENCE = {
    "official_api_authenticated": 0.90,
    "scrape_verifiable_metadata": 0.60,
    "scrape_no_metadata": 0.35,
    "screenshot_no_metadata": 0.20,
    "third_party_unverified": 0.25,
    "user_generated_no_trace": 0.05,
}

_TIER_LABELS = [
    (0.75, "alta"),
    (0.45, "media"),
    (0.15, "baja"),
    (0.0, "descartar"),
]


def _tier_label(score):
    for threshold, label in _TIER_LABELS:
        if score >= threshold:
            return label
    return "descartar"


def _clip01(x):
    return max(0.0, min(1.0, x))


# ---------------------------------------------------------------------------
# score_source
# ---------------------------------------------------------------------------

def score_source(params):
    source_type = params.get("source_type")
    if source_type not in _BASE_CONFIDENCE:
        raise ValueError(
            f"source_type invalido: {source_type!r}. "
            f"Validos: {sorted(_BASE_CONFIDENCE.keys())}"
        )

    base = _BASE_CONFIDENCE[source_type]
    score = base

    n_sources = params.get("n_independent_sources")
    if n_sources is not None:
        n_sources = int(n_sources)
        if n_sources >= 2:
            # bonus logaritmico por corroboracion, capado
            bonus = min(0.20, 0.06 * (n_sources - 1))
            score = _clip01(score + bonus)

    has_ts = params.get("has_timestamp_verifiable")
    if has_ts is True:
        score = _clip01(score + 0.08)
    elif has_ts is False:
        score = _clip01(score - 0.05)

    return {
        "source_type": source_type,
        "base_confidence": base,
        "adjusted_confidence": round(score, 4),
        "confidence_tier": _tier_label(score),
        "n_independent_sources": n_sources,
        "interpretation": (
            "Este score refleja confiabilidad del METODO de obtencion, no si el "
            "contenido es verdadero. Un score alto significa 'trazable y verificable', "
            "no 'exacto'. Usar como peso de entrada a otros analisis (ej. "
            "power_law_benford_tool, kleinberg_burst_tool), no como veredicto final."
        ),
    }


# ---------------------------------------------------------------------------
# cross_reference_check
# ---------------------------------------------------------------------------

def cross_reference_check(params):
    claims = params.get("claims")
    if not claims:
        raise ValueError("params.claims es requerido (lista de {source_type, value}).")

    scored = []
    for c in claims:
        st = c.get("source_type")
        if st not in _BASE_CONFIDENCE:
            raise ValueError(f"source_type invalido en claims: {st!r}")
        scored.append({"source_type": st, "value": c.get("value"), "base": _BASE_CONFIDENCE[st]})

    values = [c["value"] for c in scored]
    unique_values = list({repr(v) for v in values})
    n_agree = len(values) - (len(unique_values) - 1) if len(unique_values) > 0 else 0
    # forma simple de "consenso": fraccion de claims que coinciden con el valor mas comun
    if values:
        from collections import Counter
        counts = Counter(repr(v) for v in values)
        most_common_repr, most_common_count = counts.most_common(1)[0]
        consensus_fraction = most_common_count / len(values)
    else:
        consensus_fraction = 0.0
        most_common_count = 0

    weighted_avg_base = sum(c["base"] for c in scored) / len(scored)

    # penaliza fuerte si hay poca coincidencia entre fuentes independientes
    if len(scored) >= 2:
        disagreement_penalty = (1.0 - consensus_fraction) * 0.35
    else:
        disagreement_penalty = 0.0

    final_score = _clip01(weighted_avg_base + 0.10 * min(len(scored) - 1, 3) - disagreement_penalty)

    return {
        "n_claims": len(scored),
        "n_agreeing_on_majority_value": most_common_count,
        "consensus_fraction": round(consensus_fraction, 4),
        "weighted_avg_base_confidence": round(weighted_avg_base, 4),
        "disagreement_penalty": round(disagreement_penalty, 4),
        "final_confidence": round(final_score, 4),
        "confidence_tier": _tier_label(final_score),
        "interpretation": (
            "consensus_fraction bajo con multiples fuentes independientes es señal de "
            "informacion contradictoria o no corroborada -- tratar con precaucion incluso "
            "si alguna fuente individual tenia buena confianza base."
        ),
    }


# ---------------------------------------------------------------------------
# flag_unverifiable
# ---------------------------------------------------------------------------

def flag_unverifiable(params):
    records = params.get("records")
    if records is None:
        raise ValueError("params.records es requerido (lista de registros con source_type).")
    threshold = float(params.get("min_confidence_threshold", 0.3))

    kept, discarded = [], []
    for i, rec in enumerate(records):
        st = rec.get("source_type")
        if st not in _BASE_CONFIDENCE:
            discarded.append({"index": i, "reason": f"source_type invalido: {st!r}", "record": rec})
            continue
        s = score_source({
            "source_type": st,
            "n_independent_sources": rec.get("n_independent_sources"),
            "has_timestamp_verifiable": rec.get("has_timestamp_verifiable"),
        })
        entry = {"index": i, "confidence": s["adjusted_confidence"], "tier": s["confidence_tier"], "record": rec}
        if s["adjusted_confidence"] >= threshold:
            kept.append(entry)
        else:
            discarded.append({**entry, "reason": f"confidence {s['adjusted_confidence']} < threshold {threshold}"})

    return {
        "threshold": threshold,
        "n_total": len(records),
        "n_kept": len(kept),
        "n_discarded": len(discarded),
        "kept": kept,
        "discarded": discarded,
        "interpretation": (
            "Los registros 'discarded' no deben alimentar analisis cuantitativos "
            "(ej. power_law_benford_tool, kleinberg_burst_tool) como si fueran hechos "
            "confirmados; pueden usarse solo como hipotesis a investigar aparte."
        ),
    }


# ---------------------------------------------------------------------------
# validate -- self-test
# ---------------------------------------------------------------------------

def _validate():
    checks = {}

    # 1) API oficial autenticada debe dar score alto
    r1 = score_source({"source_type": "official_api_authenticated"})
    checks["official_api_high_confidence"] = {
        "score": r1["adjusted_confidence"],
        "tier": r1["confidence_tier"],
        "passed": r1["adjusted_confidence"] >= 0.75 and r1["confidence_tier"] == "alta",
    }

    # 2) screenshot sin metadata y sin corroboracion debe dar score bajo
    r2 = score_source({"source_type": "screenshot_no_metadata"})
    checks["screenshot_low_confidence"] = {
        "score": r2["adjusted_confidence"],
        "tier": r2["confidence_tier"],
        "passed": r2["adjusted_confidence"] < 0.45,
    }

    # 3) corroboracion con multiples fuentes independientes debe subir el score
    r3a = score_source({"source_type": "scrape_no_metadata", "n_independent_sources": 1})
    r3b = score_source({"source_type": "scrape_no_metadata", "n_independent_sources": 5})
    checks["corroboration_increases_score"] = {
        "score_1_source": r3a["adjusted_confidence"],
        "score_5_sources": r3b["adjusted_confidence"],
        "passed": r3b["adjusted_confidence"] > r3a["adjusted_confidence"],
    }

    # 4) cross_reference_check: fuentes que coinciden deben dar score mayor que fuentes que discrepan
    agree = cross_reference_check({"claims": [
        {"source_type": "scrape_verifiable_metadata", "value": "X"},
        {"source_type": "scrape_verifiable_metadata", "value": "X"},
        {"source_type": "third_party_unverified", "value": "X"},
    ]})
    disagree = cross_reference_check({"claims": [
        {"source_type": "scrape_verifiable_metadata", "value": "X"},
        {"source_type": "scrape_verifiable_metadata", "value": "Y"},
        {"source_type": "third_party_unverified", "value": "Z"},
    ]})
    checks["consensus_beats_disagreement"] = {
        "agree_score": agree["final_confidence"],
        "disagree_score": disagree["final_confidence"],
        "passed": agree["final_confidence"] > disagree["final_confidence"],
    }

    # 5) flag_unverifiable: umbral debe descartar lo debil y mantener lo fuerte
    batch = flag_unverifiable({
        "records": [
            {"source_type": "official_api_authenticated", "id": "a"},
            {"source_type": "user_generated_no_trace", "id": "b"},
        ],
        "min_confidence_threshold": 0.3,
    })
    checks["threshold_filters_correctly"] = {
        "n_kept": batch["n_kept"],
        "n_discarded": batch["n_discarded"],
        "passed": batch["n_kept"] == 1 and batch["n_discarded"] == 1,
    }

    passed = sum(c["passed"] for c in checks.values())
    return {
        "validation_passed": passed == len(checks),
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# dispatcher / registro
# ---------------------------------------------------------------------------

def run(mode, params):
    params = params or {}
    if mode == "score_source":
        return score_source(params)
    elif mode == "cross_reference_check":
        return cross_reference_check(params)
    elif mode == "flag_unverifiable":
        return flag_unverifiable(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            f"Modo desconocido: {mode!r}. "
            f"Modos validos: score_source, cross_reference_check, flag_unverifiable, validate."
        )


def register(reg):
    """Llamar desde server.py: from tools.data_provenance_tool import register; register(tool_registry)"""
    reg.register_tool(TOOL_NAME, TOOL_SCHEMA, lambda args: run(args.get("mode"), args.get("params") or {}))


if __name__ == "__main__":
    import json
    print(json.dumps(run("validate", {}), indent=2, ensure_ascii=False))
