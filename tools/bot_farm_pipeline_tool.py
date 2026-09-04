#!/usr/bin/env python3
"""
bot_farm_pipeline_tool.py
Orquestador de investigacion de granjas de bots: corre los pasos del pipeline
(filtro de procedencia -> deteccion de rafagas -> anomalia de Benford ->
similitud de texto -> densidad de red opcional) sobre un conjunto de cuentas
y devuelve un reporte consolidado con un score de convergencia de señales.

Ninguna señal individual es prueba; el score de convergencia refleja cuantas
señales independientes apuntan al mismo conjunto de cuentas.

Modos:
  investigate -- corre el pipeline completo sobre un dataset de cuentas
  validate     -- self-test con un caso sintetico de bot farm y uno organico
"""

import sys
import os
import math
from difflib import SequenceMatcher

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_TOOLS_DIR)
sys.path.insert(0, _TOOLS_DIR)
sys.path.insert(0, _ROOT_DIR)

import kleinberg_burst_tool
import power_law_benford_tool
import data_provenance_tool

TOOL_NAME = "bot_farm_pipeline_tool"

TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["investigate", "validate"],
        },
        "params": {
            "type": "object",
            "properties": {
                "accounts": {
                    "type": "array",
                    "description": (
                        "Lista de cuentas. Cada una: {username, source_type, "
                        "followers_count (opcional), account_created_at_verifiable (opcional bool), "
                        "n_independent_sources (opcional), timestamps (lista de floats/epoch, opcional), "
                        "text (string, opcional)}."
                    ),
                    "items": {"type": "object"},
                },
                "min_confidence_threshold": {
                    "type": "number",
                    "description": "Umbral minimo de confianza de procedencia (0-1). Default 0.3.",
                },
                "text_similarity_threshold": {
                    "type": "number",
                    "description": "Umbral de similitud de texto (0-1, SequenceMatcher ratio) para marcar 'plantilla repetida'. Default 0.85.",
                },
                "edges": {
                    "type": "array",
                    "description": "Opcional: lista de [origen, destino] (menciones/retweets) entre usernames de 'accounts', para densidad de red.",
                    "items": {"type": "array"},
                },
            },
        },
    },
    "required": ["mode"],
    "name": TOOL_NAME,
}


# ---------------------------------------------------------------------------
# Paso 1: filtro de procedencia
# ---------------------------------------------------------------------------

def _step_provenance(accounts, threshold):
    records = [
        {
            "source_type": a.get("source_type", "third_party_unverified"),
            "n_independent_sources": a.get("n_independent_sources"),
            "has_timestamp_verifiable": a.get("account_created_at_verifiable"),
            "username": a.get("username"),
        }
        for a in accounts
    ]
    result = data_provenance_tool.run("flag_unverifiable", {
        "records": records,
        "min_confidence_threshold": threshold,
    })
    kept_usernames = {entry["record"]["username"] for entry in result["kept"]}
    kept_accounts = [a for a in accounts if a.get("username") in kept_usernames]
    return kept_accounts, result


# ---------------------------------------------------------------------------
# Paso 2: rafagas temporales
# ---------------------------------------------------------------------------

def _step_bursts(accounts):
    all_timestamps = []
    for a in accounts:
        ts = a.get("timestamps") or []
        all_timestamps.extend(float(t) for t in ts)
    if len(all_timestamps) < 3:
        return {"skipped": True, "reason": "insuficientes timestamps (<3) tras el filtro de procedencia."}
    all_timestamps.sort()
    result = kleinberg_burst_tool.run("detect_bursts", {"timestamps": all_timestamps})
    return result


# ---------------------------------------------------------------------------
# Paso 3: anomalia de Benford sobre followers_count
# ---------------------------------------------------------------------------

def _step_benford(accounts):
    followers = [a.get("followers_count") for a in accounts if a.get("followers_count") is not None]
    followers = [f for f in followers if f and f > 0]
    if len(followers) < 10:
        return {"skipped": True, "reason": "insuficientes followers_count (<10) tras el filtro de procedencia."}
    result = power_law_benford_tool.run("benford_test", {"data": followers, "digits": 1})
    return result


# ---------------------------------------------------------------------------
# Paso 4: similitud de texto (plantillas repetidas)
# ---------------------------------------------------------------------------

def _step_text_similarity(accounts, threshold):
    texts = [(a.get("username"), a.get("text")) for a in accounts if a.get("text")]
    if len(texts) < 2:
        return {"skipped": True, "reason": "insuficientes textos (<2) para comparar."}

    near_duplicates = []
    n_pairs = 0
    n_similar = 0
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            n_pairs += 1
            u1, t1 = texts[i]
            u2, t2 = texts[j]
            ratio = SequenceMatcher(None, t1, t2).ratio()
            if ratio >= threshold:
                n_similar += 1
                near_duplicates.append({"username_a": u1, "username_b": u2, "similarity": round(ratio, 4)})

    fraction_similar = n_similar / n_pairs if n_pairs else 0.0
    return {
        "n_texts": len(texts),
        "n_pairs_compared": n_pairs,
        "n_near_duplicate_pairs": n_similar,
        "fraction_near_duplicate": round(fraction_similar, 4),
        "near_duplicates": near_duplicates[:50],  # cap para no inflar el reporte
        "interpretation": (
            "fraction_near_duplicate alto indica plantillas de texto reusadas con "
            "variaciones minimas -- tipico de cuentas coordinadas que amplifican el "
            "mismo mensaje. Humanos independientes raramente producen texto casi identico."
        ),
    }


# ---------------------------------------------------------------------------
# Paso 5: densidad de red (opcional)
# ---------------------------------------------------------------------------

def _step_network_density(accounts, edges):
    if not edges:
        return {"skipped": True, "reason": "no se proveyeron edges."}
    usernames = {a.get("username") for a in accounts}
    valid_edges = [e for e in edges if len(e) == 2 and e[0] in usernames and e[1] in usernames]
    n_nodes = len(usernames)
    n_edges = len(valid_edges)
    max_possible_edges = n_nodes * (n_nodes - 1)  # dirigido
    density = n_edges / max_possible_edges if max_possible_edges > 0 else 0.0
    return {
        "n_nodes": n_nodes,
        "n_edges_valid": n_edges,
        "density": round(density, 4),
        "interpretation": (
            "Densidad alta sobre un conjunto chico y cerrado de cuentas (que ademas "
            "coincide en las otras señales) sugiere una comunidad artificialmente "
            "cerrada en vez de interaccion organica dispersa."
        ),
    }


# ---------------------------------------------------------------------------
# Sintesis: score de convergencia
# ---------------------------------------------------------------------------

def _convergence_score(provenance_result, burst_result, benford_result, text_result, network_result):
    signals_fired = []

    n_kept = provenance_result["n_kept"]
    n_total = provenance_result["n_total"]
    if n_total > 0 and (n_kept / n_total) < 0.5:
        signals_fired.append("mas de la mitad de los registros descartados por baja procedencia -- dataset debil")

    if not burst_result.get("skipped") and burst_result.get("n_bursts_detected", 0) > 0:
        max_level = max((b["max_level"] for b in burst_result.get("bursts", [])), default=0)
        if max_level >= 3:
            signals_fired.append(f"rafaga temporal detectada (max_level={max_level})")

    if not benford_result.get("skipped") and benford_result.get("conformity_nigrini") == "no_conforme":
        signals_fired.append(f"followers_count no conforme a Benford (mad={benford_result.get('mad')})")

    if not text_result.get("skipped") and text_result.get("fraction_near_duplicate", 0) > 0.15:
        signals_fired.append(f"plantillas de texto repetidas ({text_result['fraction_near_duplicate']*100:.1f}% de pares)")

    if not network_result.get("skipped") and network_result.get("density", 0) > 0.3:
        signals_fired.append(f"red anormalmente densa/cerrada (density={network_result['density']})")

    n_signals = len(signals_fired)
    if n_signals >= 3:
        verdict = "alta_sospecha_coordinacion"
    elif n_signals == 2:
        verdict = "sospecha_moderada"
    elif n_signals == 1:
        verdict = "señal_aislada_investigar_mas"
    else:
        verdict = "sin_evidencia_de_coordinacion"

    return {
        "n_independent_signals_fired": n_signals,
        "signals_detail": signals_fired,
        "verdict": verdict,
        "interpretation": (
            "El veredicto refleja CUANTAS señales independientes convergen, no la "
            "certeza de cada una por separado. 3+ señales sobre el mismo conjunto de "
            "cuentas es el umbral practico para tratarlo como caso a reportar; 1 señal "
            "aislada casi siempre tiene una explicacion alternativa no maliciosa."
        ),
    }


# ---------------------------------------------------------------------------
# investigate
# ---------------------------------------------------------------------------

def investigate(params):
    accounts = params.get("accounts")
    if not accounts:
        raise ValueError("params.accounts es requerido (lista de cuentas).")
    threshold = float(params.get("min_confidence_threshold", 0.3))
    text_threshold = float(params.get("text_similarity_threshold", 0.85))
    edges = params.get("edges")

    kept_accounts, provenance_result = _step_provenance(accounts, threshold)
    burst_result = _step_bursts(kept_accounts)
    benford_result = _step_benford(kept_accounts)
    text_result = _step_text_similarity(kept_accounts, text_threshold)
    network_result = _step_network_density(kept_accounts, edges)

    convergence = _convergence_score(provenance_result, burst_result, benford_result, text_result, network_result)

    return {
        "n_accounts_input": len(accounts),
        "n_accounts_after_provenance_filter": len(kept_accounts),
        "step1_provenance": provenance_result,
        "step2_burst_detection": burst_result,
        "step3_benford_test": benford_result,
        "step4_text_similarity": text_result,
        "step5_network_density": network_result,
        "convergence_score": convergence,
    }


# ---------------------------------------------------------------------------
# validate -- self-test con caso sintetico
# ---------------------------------------------------------------------------

def _validate():
    import random
    random.seed(11)
    checks = {}

    # --- Caso 1: bot farm sintetica (deberia dar alta sospecha) ---
    bot_accounts = []
    templates = [
        "Increible lo que esta pasando, todos deberian saberlo YA #trending",
        "increible lo que esta pasando, todos deberian saberlo ya #trending!!",
        "Increíble lo q está pasando, todos deberían saberlo ya #trending",
    ]
    for i in range(40):
        bot_accounts.append({
            "username": f"bot_{i}",
            "source_type": "scrape_verifiable_metadata",
            "n_independent_sources": 2,
            "followers_count": random.randint(100, 999),  # rango acotado tipico de compra en lote
            "timestamps": [400.0 + random.uniform(0, 5)],  # rafaga concentrada
            "text": templates[i % len(templates)],
        })
    bot_edges = [[f"bot_{i}", f"bot_{(i+1) % 40}"] for i in range(40)]

    r_bot = investigate({
        "accounts": bot_accounts,
        "edges": bot_edges,
        "min_confidence_threshold": 0.3,
    })
    checks["bot_farm_detected_high_suspicion"] = {
        "verdict": r_bot["convergence_score"]["verdict"],
        "n_signals": r_bot["convergence_score"]["n_independent_signals_fired"],
        "passed": r_bot["convergence_score"]["verdict"] in ("alta_sospecha_coordinacion", "sospecha_moderada"),
    }

    # --- Caso 2: cuentas organicas sinteticas (deberia dar sin evidencia) ---
    organic_word_bank = [
        "feria", "paltas", "parque", "caminar", "libro", "cocinar", "partido",
        "gol", "cafe", "musica", "playa", "trabajo", "reunion", "peliculas",
        "amigos", "familia", "viaje", "cerro", "lluvia", "sol", "gato", "perro",
        "pan", "vino", "cumpleanos", "estudio", "examen", "bicicleta", "auto", "tren",
    ]
    organic_accounts = []
    for i in range(40):
        n_words = random.randint(4, 9)
        text = " ".join(random.sample(organic_word_bank, n_words)) + f" hoy dia {i} jaja"
        followers = int(math.exp(random.uniform(math.log(5), math.log(500000))))
        organic_accounts.append({
            "username": f"user_{i}",
            "source_type": "official_api_authenticated",
            "n_independent_sources": 1,
            "followers_count": followers,
            "timestamps": [random.uniform(0, 1000)],
            "text": text,
        })

    r_organic = investigate({
        "accounts": organic_accounts,
        "min_confidence_threshold": 0.3,
    })
    checks["organic_not_flagged"] = {
        "verdict": r_organic["convergence_score"]["verdict"],
        "n_signals": r_organic["convergence_score"]["n_independent_signals_fired"],
        "passed": r_organic["convergence_score"]["verdict"] in ("sin_evidencia_de_coordinacion", "señal_aislada_investigar_mas"),
    }

    # --- Caso 3: provenance filter realmente descarta fuentes debiles ---
    mixed_accounts = [
        {"username": "good1", "source_type": "official_api_authenticated"},
        {"username": "bad1", "source_type": "user_generated_no_trace"},
    ]
    kept, prov = _step_provenance(mixed_accounts, 0.3)
    checks["provenance_filter_active"] = {
        "n_kept": len(kept),
        "passed": len(kept) == 1 and kept[0]["username"] == "good1",
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
    if mode == "investigate":
        return investigate(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"Modo desconocido: {mode!r}. Modos validos: investigate, validate.")


def register(reg):
    """Llamar desde server.py: from tools.bot_farm_pipeline_tool import register; register(tool_registry)"""
    reg.register_tool(TOOL_NAME, TOOL_SCHEMA, lambda args: run(args.get("mode"), args.get("params") or {}))


if __name__ == "__main__":
    import json
    print(json.dumps(run("validate", {}), indent=2, ensure_ascii=False))
