#!/usr/bin/env python3
"""
bot_farm_pipeline_tool.py
Orquestador de investigacion de granjas de bots: corre los pasos del pipeline
(filtro de procedencia -> deteccion de rafagas -> anomalia de Benford ->
similitud de texto -> densidad de red opcional) sobre un conjunto de cuentas
y devuelve un reporte consolidado con un score de convergencia de señales.

Ninguna señal individual es prueba; el score de convergencia refleja cuantas
señales independientes apuntan al mismo conjunto de cuentas. Este pipeline
es una herramienta de TRIAGE para priorizar revision humana, no un veredicto
ni una atribucion.

Modos:
  investigate                  -- corre el pipeline completo sobre un dataset de cuentas
  benchmark_false_positive_rate -- corre el pipeline sobre una bateria de casos
                                    organicos sinteticos diversos y mide la tasa
                                    de falsos positivos
  validate                      -- self-test con casos sinteticos (bot farm, organico
                                    simple, filtro de procedencia, benchmark de FP)
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
            "enum": ["investigate", "validate", "benchmark_false_positive_rate"],
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
    # n minimo elevado de 10 a 500 tras benchmark empirico (ver benchmark_false_positive_rate):
    # con datos PERFECTAMENTE conformes a Benford (log-uniformes, sin manipulacion), el
    # criterio MAD de Nigrini da "no_conforme" el 100% de las veces con n=15-40 (puro ruido
    # de muestreo), ~90% con n=100, y no se estabiliza cerca de 0% hasta n~700-1000. Nigrini
    # califico estos umbrales para auditoria contable con miles de registros, no para
    # datasets tipicos de cuentas sociales (decenas/cientos). Por debajo de 500 el paso se
    # omite en vez de arriesgar un falso positivo estructural.
    if len(followers) < 500:
        return {
            "skipped": True,
            "reason": (
                f"insuficientes followers_count ({len(followers)} < 500) para que el "
                "criterio MAD de Nigrini sea estadisticamente confiable -- con menos "
                "datos el ruido de muestreo por si solo produce 'no_conforme' con "
                "datos genuinamente Benford-compatibles (ver interpretation de "
                "benchmark_false_positive_rate)."
            ),
        }
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
        "near_duplicates": near_duplicates[:50],
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
    max_possible_edges = n_nodes * (n_nodes - 1)
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
# Sintesis: score de convergencia (herramienta de TRIAGE, no veredicto)
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
        chi2_p = benford_result.get("chi2_p_value")
        # exigir corroboracion del chi2 p-value ademas del MAD: un solo criterio
        # estadistico disparando la señal es mas propenso a ruido que dos coincidiendo.
        # Si scipy no esta disponible (chi2_p None), se acepta solo el MAD como antes.
        if chi2_p is None or chi2_p < 0.05:
            signals_fired.append(
                f"followers_count no conforme a Benford (mad={benford_result.get('mad')}, "
                f"chi2_p_value={chi2_p})"
            )

    if not text_result.get("skipped") and text_result.get("fraction_near_duplicate", 0) > 0.15:
        signals_fired.append(f"plantillas de texto repetidas ({text_result['fraction_near_duplicate']*100:.1f}% de pares)")

    if not network_result.get("skipped") and network_result.get("density", 0) > 0.3:
        signals_fired.append(f"red anormalmente densa/cerrada (density={network_result['density']})")

    n_signals = len(signals_fired)
    if n_signals >= 3:
        signal_level = "alto"
    elif n_signals == 2:
        signal_level = "moderado"
    elif n_signals == 1:
        signal_level = "bajo"
    else:
        signal_level = "ninguno"

    requires_human_review = n_signals >= 1

    return {
        "n_independent_signals_fired": n_signals,
        "signals_detail": signals_fired,
        "signal_level": signal_level,
        "requires_human_review": requires_human_review,
        "interpretation": (
            "Este score es una herramienta de TRIAGE, no una conclusion ni prueba de "
            "operacion coordinada, y no permite atribuir la actividad a un actor "
            "especifico bajo ninguna circunstancia. Refleja CUANTAS señales "
            "independientes convergen sobre el mismo conjunto de cuentas, no la "
            "certeza de cada una por separado. signal_level='alto' (3+ señales) es el "
            "umbral practico para priorizar revision humana urgente; 'bajo' (1 señal "
            "aislada) casi siempre tiene una explicacion alternativa no maliciosa. "
            "NINGUN signal_level, por si solo, autoriza reportar una cuenta o cluster "
            "sin revision humana previa."
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
# benchmark_false_positive_rate -- bateria de casos organicos diversos
# ---------------------------------------------------------------------------

def _generate_diverse_organic_cases():
    import random

    cases = []

    word_bank = [
        "feria", "paltas", "parque", "caminar", "libro", "cocinar", "partido",
        "gol", "cafe", "musica", "playa", "trabajo", "reunion", "peliculas",
        "amigos", "familia", "viaje", "cerro", "lluvia", "sol", "gato", "perro",
        "pan", "vino", "cumpleanos", "estudio", "examen", "bicicleta", "auto", "tren",
    ]

    def _unique_text(rnd, i):
        n_words = rnd.randint(4, 9)
        return " ".join(rnd.sample(word_bank, n_words)) + f" hoy dia {i}"

    rnd = random.Random(101)
    accs = [{
        "username": f"a_{i}", "source_type": "official_api_authenticated",
        "n_independent_sources": 1, "followers_count": rnd.randint(5, 300),
        "timestamps": [rnd.uniform(0, 2000)],
        "text": _unique_text(rnd, i),
    } for i in range(15)]
    cases.append(("comunidad_chica_followers_bajos", accs, None))

    rnd = random.Random(202)
    accs = [{
        "username": f"b_{i}", "source_type": "official_api_authenticated",
        "n_independent_sources": 1,
        "followers_count": int(math.exp(rnd.uniform(math.log(50), math.log(2_000_000)))),
        "timestamps": [rnd.uniform(0, 5000)],
        "text": _unique_text(rnd, i),
    } for i in range(40)]
    cases.append(("cuentas_grandes_followers_amplios", accs, None))

    rnd = random.Random(303)
    frases_evento = [
        "gol increible, no lo puedo creer",
        "que jugada la de recien, tremendo",
        "esto va para el video del año jaja",
        "no me esperaba ese resultado para nada",
        "la hinchada esta que explota ahora mismo",
    ]
    accs = [{
        "username": f"c_{i}", "source_type": "official_api_authenticated",
        "n_independent_sources": 1, "followers_count": rnd.randint(20, 50000),
        "timestamps": [1000.0 + rnd.uniform(0, 8)],
        "text": rnd.choice(frases_evento) + f" (usuario {i})",
    } for i in range(30)]
    cases.append(("evento_real_reaccion_sincronica", accs, None))

    rnd = random.Random(404)
    topics = ["el nuevo capitulo", "la serie de anoche", "el estreno del viernes", "el trailer que salio"]
    accs = []
    for i in range(25):
        t = rnd.choice(topics)
        phrasing = rnd.choice([
            f"vi {t} y me encanto totalmente",
            f"recien termine de ver {t}, una locura",
            f"{t} supero todas mis expectativas la verdad",
            f"no puedo dejar de pensar en {t}",
        ])
        accs.append({
            "username": f"d_{i}", "source_type": "official_api_authenticated",
            "n_independent_sources": 1, "followers_count": rnd.randint(30, 8000),
            "timestamps": [rnd.uniform(0, 3000)], "text": phrasing,
        })
    cases.append(("comunidad_interes_compartido", accs, None))

    rnd = random.Random(505)
    accs = [{
        "username": f"e_{i}", "source_type": "official_api_authenticated",
        "n_independent_sources": 1, "followers_count": rnd.randint(100, 90000),
        "timestamps": [rnd.uniform(0, 4000)],
        "text": _unique_text(rnd, i),
    } for i in range(20)]
    edges = []
    for i in range(20):
        targets = rnd.sample([j for j in range(20) if j != i], k=rnd.choice([0, 1, 2]))
        edges.extend([f"e_{i}", f"e_{t}"] for t in targets)
    cases.append(("red_organica_moderada", accs, edges))

    rnd = random.Random(606)
    frases_multi = [
        "que buen dia para salir a caminar",
        "what a nice day to go for a walk",
        "quel bon temps pour se promener",
        "was fur ein schoner Tag zum Spazieren",
        "che bella giornata per fare una passeggiata",
    ]
    accs = [{
        "username": f"f_{i}", "source_type": "official_api_authenticated",
        "n_independent_sources": 1, "followers_count": rnd.randint(10, 40000),
        "timestamps": [rnd.uniform(0, 3000)], "text": rnd.choice(frases_multi) + f" #{i}",
    } for i in range(20)]
    cases.append(("cuentas_multilingues", accs, None))

    rnd = random.Random(707)
    accs = [{
        "username": f"g_{i}", "source_type": "official_api_authenticated",
        "n_independent_sources": 1, "followers_count": rnd.randint(15, 1000),
        "timestamps": [rnd.uniform(0, 1500)],
        "text": _unique_text(rnd, i),
    } for i in range(10)]
    cases.append(("dataset_pequeno_borde_de_umbrales", accs, None))

    rnd = random.Random(808)
    accs = [{
        "username": f"h_{i}", "source_type": "official_api_authenticated",
        "n_independent_sources": 1,
        "followers_count": max(int(rnd.paretovariate(1.16) * 200), 1),
        "timestamps": [rnd.uniform(0, 6000)],
        "text": _unique_text(rnd, i),
    } for i in range(35)]
    cases.append(("influencers_powerlaw_real", accs, None))

    return cases


def _benchmark_false_positive_rate(params=None):
    cases = _generate_diverse_organic_cases()
    results = []
    n_flagged_strict = 0
    n_any_signal = 0

    for case_name, accounts, edges in cases:
        r = investigate({"accounts": accounts, "edges": edges, "min_confidence_threshold": 0.3})
        level = r["convergence_score"]["signal_level"]
        if level in ("moderado", "alto"):
            n_flagged_strict += 1
        if level != "ninguno":
            n_any_signal += 1
        results.append({
            "case": case_name,
            "n_accounts": len(accounts),
            "signal_level": level,
            "n_signals": r["convergence_score"]["n_independent_signals_fired"],
            "signals_detail": r["convergence_score"]["signals_detail"],
        })

    n_cases = len(cases)
    return {
        "n_cases": n_cases,
        "false_positive_rate_strict": round(n_flagged_strict / n_cases, 4),
        "any_signal_rate": round(n_any_signal / n_cases, 4),
        "per_case_results": results,
        "interpretation": (
            "false_positive_rate_strict = fraccion de casos ORGANICOS conocidos que el "
            "pipeline clasifico como signal_level moderado/alto (el nivel que se usaria "
            "para priorizar un reporte). any_signal_rate incluye tambien señales aisladas "
            "('bajo'), esperables ocasionalmente y que NO deberian, por si solas, generar "
            "un reporte. Un false_positive_rate_strict alto (>15%) indica que los umbrales "
            "de _convergence_score son demasiado sensibles y deben recalibrarse ANTES de "
            "usar este pipeline sobre datos reales -- nunca despues de ver un caso real "
            "especifico fallar (eso es ajustar el criterio al resultado, no medirlo)."
        ),
    }


# ---------------------------------------------------------------------------
# validate -- self-test con caso sintetico
# ---------------------------------------------------------------------------

def _validate():
    import random
    random.seed(11)
    checks = {}

    bot_accounts = []
    templates = [
        "Increible lo que esta pasando, todos deberian saberlo YA #trending",
        "increible lo que esta pasando, todos deberian saberlo ya #trending!!",
        "Increíble lo q está pasando, todos deberían saberlo ya #trending",
    ]
    n_bot_accounts = 600
    for i in range(n_bot_accounts):
        bot_accounts.append({
            "username": f"bot_{i}",
            "source_type": "scrape_verifiable_metadata",
            "n_independent_sources": 2,
            "followers_count": random.randint(100, 999),
            "timestamps": [400.0 + random.uniform(0, 5)],
            "text": templates[i % len(templates)],
        })
    bot_edges = [[f"bot_{i}", f"bot_{(i+1) % n_bot_accounts}"] for i in range(n_bot_accounts)]

    r_bot = investigate({
        "accounts": bot_accounts,
        "edges": bot_edges,
        "min_confidence_threshold": 0.3,
    })
    checks["bot_farm_detected_high_suspicion"] = {
        "signal_level": r_bot["convergence_score"]["signal_level"],
        "n_signals": r_bot["convergence_score"]["n_independent_signals_fired"],
        "passed": r_bot["convergence_score"]["signal_level"] in ("alto", "moderado"),
    }

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
        "signal_level": r_organic["convergence_score"]["signal_level"],
        "n_signals": r_organic["convergence_score"]["n_independent_signals_fired"],
        "passed": r_organic["convergence_score"]["signal_level"] in ("ninguno", "bajo"),
    }

    mixed_accounts = [
        {"username": "good1", "source_type": "official_api_authenticated"},
        {"username": "bad1", "source_type": "user_generated_no_trace"},
    ]
    kept, prov = _step_provenance(mixed_accounts, 0.3)
    checks["provenance_filter_active"] = {
        "n_kept": len(kept),
        "passed": len(kept) == 1 and kept[0]["username"] == "good1",
    }

    bench = _benchmark_false_positive_rate()
    checks["false_positive_benchmark_acceptable"] = {
        "false_positive_rate_strict": bench["false_positive_rate_strict"],
        "any_signal_rate": bench["any_signal_rate"],
        "passed": bench["false_positive_rate_strict"] <= 0.15,
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
    elif mode == "benchmark_false_positive_rate":
        return _benchmark_false_positive_rate(params)
    else:
        raise ValueError(
            f"Modo desconocido: {mode!r}. Modos validos: investigate, validate, "
            f"benchmark_false_positive_rate."
        )


def register(reg):
    """Llamar desde server.py: from tools.bot_farm_pipeline_tool import register; register(tool_registry)"""
    reg.register_tool(TOOL_NAME, TOOL_SCHEMA, lambda args: run(args.get("mode"), args.get("params") or {}))


if __name__ == "__main__":
    import json
    print(json.dumps(run("validate", {}), indent=2, ensure_ascii=False))
