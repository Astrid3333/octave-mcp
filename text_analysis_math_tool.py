#!/usr/bin/env python3
"""
text_analysis_math_tool.py
Herramientas matematicas para linguistica computacional y analisis
de textos historicos: distancias de edicion (Levenshtein, Jaro-Winkler),
modelos de lenguaje n-grama (cadenas de Markov con suavizado add-k),
leyes de frecuencia (Zipf, Heaps) y estilometria (distancia
Kullback-Leibler / Jensen-Shannon entre distribuciones lexicas de dos
textos, para atribucion de autoria o comparacion de corpus).
Sin dependencias externas mas alla de numpy - portable al mismo stack
que el resto de octave-mcp.
"""
import re
import math
from collections import Counter
import numpy as np


def _levenshtein(a, b):
    n, m = len(a), len(b)
    if n == 0:
        return m
    if m == 0:
        return n
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        curr = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[m]


def _jaro(a, b):
    if a == b:
        return 1.0
    len_a, len_b = len(a), len(b)
    if len_a == 0 or len_b == 0:
        return 0.0
    match_distance = max(len_a, len_b) // 2 - 1
    match_distance = max(match_distance, 0)
    a_matches = [False] * len_a
    b_matches = [False] * len_b
    matches = 0
    transpositions = 0

    for i in range(len_a):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len_b)
        for j in range(start, end):
            if b_matches[j] or a[i] != b[j]:
                continue
            a_matches[i] = True
            b_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len_a):
        if not a_matches[i]:
            continue
        while not b_matches[k]:
            k += 1
        if a[i] != b[k]:
            transpositions += 1
        k += 1
    transpositions //= 2

    return (matches / len_a + matches / len_b +
            (matches - transpositions) / matches) / 3.0


def _jaro_winkler(a, b, prefix_scale=0.1, max_prefix=4):
    jaro_sim = _jaro(a, b)
    prefix_len = 0
    for ca, cb in zip(a, b):
        if ca == cb:
            prefix_len += 1
            if prefix_len == max_prefix:
                break
        else:
            break
    return jaro_sim + prefix_len * prefix_scale * (1 - jaro_sim)


def compute_edit_distance(text_a, text_b, method="levenshtein"):
    if method == "levenshtein":
        dist = _levenshtein(text_a, text_b)
        max_len = max(len(text_a), len(text_b), 1)
        return {
            "mode": "edit_distance",
            "method": "levenshtein",
            "distance": dist,
            "normalized_distance": round(dist / max_len, 6),
            "similarity": round(1 - dist / max_len, 6),
        }
    elif method == "jaro_winkler":
        sim = _jaro_winkler(text_a, text_b)
        return {
            "mode": "edit_distance",
            "method": "jaro_winkler",
            "similarity": round(sim, 6),
            "distance": round(1 - sim, 6),
        }
    else:
        raise ValueError("method debe ser 'levenshtein' o 'jaro_winkler'")


def _tokenize(text):
    return re.findall(r"[a-zA-ZáéíóúñÁÉÍÓÚÑüÜ']+", text.lower())


def compute_ngram_model(text, n=2, k_smoothing=1.0, query_next=None):
    tokens = _tokenize(text)
    if len(tokens) < n:
        raise ValueError(f"texto demasiado corto para n={n}")

    vocab = sorted(set(tokens))
    V = len(vocab)

    contexts = Counter()
    ngrams = Counter()
    for i in range(len(tokens) - n + 1):
        context = tuple(tokens[i:i + n - 1])
        full = tuple(tokens[i:i + n])
        contexts[context] += 1
        ngrams[full] += 1

    result = {
        "mode": "ngram_model",
        "n": n,
        "k_smoothing": k_smoothing,
        "vocab_size": V,
        "n_tokens": len(tokens),
        "n_distinct_contexts": len(contexts),
        "n_distinct_ngrams": len(ngrams),
    }

    if query_next is not None:
        context = tuple(_tokenize(query_next)[-(n - 1):]) if n > 1 else tuple()
        context_count = contexts.get(context, 0)
        probs = {}
        for w in vocab:
            full = context + (w,)
            probs[w] = (ngrams.get(full, 0) + k_smoothing) / (context_count + k_smoothing * V)
        top = sorted(probs.items(), key=lambda kv: -kv[1])[:10]
        result["query_context"] = list(context)
        result["top_predictions"] = [{"token": w, "prob": round(p, 6)} for w, p in top]

    log_prob_sum = 0.0
    count_eval = 0
    for i in range(len(tokens) - n + 1):
        context = tuple(tokens[i:i + n - 1])
        full = tuple(tokens[i:i + n])
        context_count = contexts[context]
        p = (ngrams[full] + k_smoothing) / (context_count + k_smoothing * V)
        log_prob_sum += math.log(p)
        count_eval += 1
    if count_eval > 0:
        perplexity = math.exp(-log_prob_sum / count_eval)
        result["perplexity_self"] = round(perplexity, 6)

    return result


def compute_frequency_laws(text):
    tokens = _tokenize(text)
    n_tokens = len(tokens)
    if n_tokens < 5:
        raise ValueError("texto demasiado corto para ajustar Zipf/Heaps")

    freqs = Counter(tokens)
    ranked = sorted(freqs.values(), reverse=True)
    ranks = np.arange(1, len(ranked) + 1)
    log_r = np.log(ranks)
    log_f = np.log(ranked)

    A = np.vstack([log_r, np.ones_like(log_r)]).T
    slope, intercept = np.linalg.lstsq(A, log_f, rcond=None)[0]
    zipf_s = -slope
    residuals = log_f - (slope * log_r + intercept)
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((log_f - np.mean(log_f)) ** 2))
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else None

    n_samples = min(30, n_tokens)
    step = max(1, n_tokens // n_samples)
    n_points, v_points = [], []
    seen = set()
    for i, tok in enumerate(tokens, 1):
        seen.add(tok)
        if i % step == 0 or i == n_tokens:
            n_points.append(i)
            v_points.append(len(seen))
    log_n = np.log(n_points)
    log_v = np.log(v_points)
    A2 = np.vstack([log_n, np.ones_like(log_n)]).T
    beta, log_k = np.linalg.lstsq(A2, log_v, rcond=None)[0]

    return {
        "mode": "frequency_laws",
        "n_tokens": n_tokens,
        "vocab_size": len(freqs),
        "zipf_exponent_s": round(float(zipf_s), 6),
        "zipf_r_squared": round(r_squared, 6) if r_squared is not None else None,
        "zipf_typical_range_note": "s tipicamente cercano a 1.0 para lenguaje natural",
        "heaps_beta": round(float(beta), 6),
        "heaps_k": round(float(math.exp(log_k)), 6),
        "heaps_typical_range_note": "beta tipicamente entre 0.4 y 0.6",
    }


def compute_stylometry(text_a, text_b, top_n=200):
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        raise ValueError("ambos textos deben tener tokens")

    freqs_a = Counter(tokens_a)
    freqs_b = Counter(tokens_b)
    combined_vocab = set(w for w, _ in freqs_a.most_common(top_n)) | \
                      set(w for w, _ in freqs_b.most_common(top_n))
    vocab = sorted(combined_vocab)

    eps = 1e-10
    p = np.array([freqs_a.get(w, 0) for w in vocab], dtype=float)
    q = np.array([freqs_b.get(w, 0) for w in vocab], dtype=float)
    p = p / p.sum() + eps
    q = q / q.sum() + eps
    p = p / p.sum()
    q = q / q.sum()

    kl_pq = float(np.sum(p * np.log(p / q)))
    kl_qp = float(np.sum(q * np.log(q / p)))
    m = 0.5 * (p + q)
    js_div = 0.5 * float(np.sum(p * np.log(p / m))) + 0.5 * float(np.sum(q * np.log(q / m)))
    js_dist = math.sqrt(max(js_div, 0.0))

    ttr_a = len(freqs_a) / len(tokens_a)
    ttr_b = len(freqs_b) / len(tokens_b)

    return {
        "mode": "stylometry",
        "vocab_compared": len(vocab),
        "n_tokens_a": len(tokens_a),
        "n_tokens_b": len(tokens_b),
        "kl_divergence_a_to_b": round(kl_pq, 6),
        "kl_divergence_b_to_a": round(kl_qp, 6),
        "jensen_shannon_divergence": round(js_div, 6),
        "jensen_shannon_distance": round(js_dist, 6),
        "type_token_ratio_a": round(ttr_a, 6),
        "type_token_ratio_b": round(ttr_b, 6),
        "interpretation": (
            "misma_mano_probable" if js_dist < 0.15 else
            "posible_diferencia_estilistica" if js_dist < 0.35 else
            "estilos_lexicos_claramente_distintos"
        ),
    }


def compute_text_analysis_math(mode, **kwargs):
    if mode == "edit_distance":
        return compute_edit_distance(
            kwargs["text_a"], kwargs["text_b"],
            method=kwargs.get("method", "levenshtein"),
        )
    elif mode == "ngram_model":
        return compute_ngram_model(
            kwargs["text"], n=kwargs.get("n", 2),
            k_smoothing=kwargs.get("k_smoothing", 1.0),
            query_next=kwargs.get("query_next"),
        )
    elif mode == "frequency_laws":
        return compute_frequency_laws(kwargs["text"])
    elif mode == "stylometry":
        return compute_stylometry(
            kwargs["text_a"], kwargs["text_b"],
            top_n=kwargs.get("top_n", 200),
        )
    else:
        raise ValueError(f"modo desconocido: {mode}")


TEXT_ANALYSIS_MATH_TOOL_SCHEMA = {
    "name": "text_analysis_math",
    "description": (
        "Matematica para linguistica computacional: distancias de edicion "
        "(Levenshtein, Jaro-Winkler), modelo de lenguaje n-grama con "
        "suavizado y perplejidad, leyes de frecuencia (Zipf, Heaps), y "
        "estilometria (KL / Jensen-Shannon entre distribuciones lexicas de "
        "dos textos) para atribucion de autoria o comparacion de corpus, "
        "incluyendo textos historicos."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["edit_distance", "ngram_model", "frequency_laws", "stylometry"],
            },
            "text_a": {"type": "string", "description": "edit_distance, stylometry"},
            "text_b": {"type": "string", "description": "edit_distance, stylometry"},
            "method": {"type": "string", "enum": ["levenshtein", "jaro_winkler"], "description": "edit_distance"},
            "text": {"type": "string", "description": "ngram_model, frequency_laws"},
            "n": {"type": "integer", "description": "ngram_model, orden del n-grama (default 2)"},
            "k_smoothing": {"type": "number", "description": "ngram_model, suavizado add-k (default 1.0)"},
            "query_next": {"type": "string", "description": "ngram_model, contexto para predecir siguiente token"},
            "top_n": {"type": "integer", "description": "stylometry, tamano de vocabulario comparado (default 200)"},
        },
        "required": ["mode"],
    },
}
