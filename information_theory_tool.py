#!/usr/bin/env python3
"""
information_theory_tool.py
Teoria de la informacion: entropia de Shannon (y entropia condicional/cruzada),
informacion mutua entre dos variables, divergencia KL y distancia Jensen-Shannon
entre distribuciones, y entropia de secuencias/codigos (util para comparar
sistemas numerales ancestrales por su eficiencia informacional, o para
caracterizar la aleatoriedad de senales de TritOS).
"""
import numpy as np
from scipy.stats import entropy as scipy_entropy


def _normalize(p):
    p = np.asarray(p, dtype=float)
    p = np.clip(p, 1e-15, None)
    return p / p.sum()


def compute_shannon_entropy(distribution, base=2):
    p = _normalize(distribution)
    H = -np.sum(p * np.log(p) / np.log(base))
    H_max = np.log(len(p)) / np.log(base)
    return {
        "mode": "shannon_entropy", "base": base, "n_outcomes": len(p),
        "entropy": round(float(H), 6),
        "max_possible_entropy": round(float(H_max), 6),
        "normalized_entropy": round(float(H / H_max), 6) if H_max > 0 else None,
        "redundancy": round(float(1 - H / H_max), 6) if H_max > 0 else None,
    }


def compute_kl_divergence(p, q, base=2):
    p_n, q_n = _normalize(p), _normalize(q)
    if len(p_n) != len(q_n):
        raise ValueError("p y q deben tener la misma longitud")
    kl_pq = float(np.sum(p_n * np.log(p_n / q_n) / np.log(base)))
    kl_qp = float(np.sum(q_n * np.log(q_n / p_n) / np.log(base)))
    m = 0.5 * (p_n + q_n)
    js = 0.5 * float(np.sum(p_n * np.log(p_n / m) / np.log(base))) + \
         0.5 * float(np.sum(q_n * np.log(q_n / m) / np.log(base)))
    return {
        "mode": "kl_divergence", "base": base, "n_outcomes": len(p_n),
        "kl_divergence_p_q": round(kl_pq, 6),
        "kl_divergence_q_p": round(kl_qp, 6),
        "jensen_shannon_divergence": round(js, 6),
        "jensen_shannon_distance": round(float(np.sqrt(max(js, 0))), 6),
        "distributions_identical": bool(np.allclose(p_n, q_n, atol=1e-6)),
    }


def compute_mutual_information(joint_distribution, base=2):
    P = np.asarray(joint_distribution, dtype=float)
    P = P / P.sum()
    Px = P.sum(axis=1)
    Py = P.sum(axis=0)
    Hx = compute_shannon_entropy(Px, base)["entropy"]
    Hy = compute_shannon_entropy(Py, base)["entropy"]
    P_safe = np.clip(P, 1e-15, None)
    outer = np.outer(Px, Py)
    outer_safe = np.clip(outer, 1e-15, None)
    mi = float(np.sum(P * np.log(P_safe / outer_safe) / np.log(base)))
    Hxy = compute_shannon_entropy(P.flatten(), base)["entropy"]
    return {
        "mode": "mutual_information", "base": base, "shape": list(P.shape),
        "H_X": round(Hx, 6), "H_Y": round(Hy, 6), "H_XY_joint": round(Hxy, 6),
        "mutual_information": round(mi, 6),
        "normalized_mutual_information": round(mi / min(Hx, Hy), 6) if min(Hx, Hy) > 0 else None,
        "independent_approx": bool(abs(mi) < 1e-4),
    }


def compute_cross_entropy(p, q, base=2):
    p_n, q_n = _normalize(p), _normalize(q)
    H_cross = float(-np.sum(p_n * np.log(q_n) / np.log(base)))
    H_p = compute_shannon_entropy(p_n, base)["entropy"]
    return {
        "mode": "cross_entropy", "base": base,
        "cross_entropy_p_q": round(H_cross, 6),
        "entropy_p": round(H_p, 6),
        "kl_divergence_p_q": round(H_cross - H_p, 6),
    }


def compute_sequence_entropy(sequence, order=1, base=2):
    seq = list(sequence)
    n = len(seq)
    if order == 1:
        symbols, counts = np.unique(seq, return_counts=True)
        result = compute_shannon_entropy(counts, base)
        result["mode"] = "sequence_entropy"
        result["order"] = 1
        result["symbols"] = symbols.tolist()
        result["counts"] = counts.tolist()
        return result
    else:
        from collections import Counter
        context_counts = Counter()
        joint_counts = Counter()
        for i in range(n - order + 1):
            context = tuple(seq[i:i + order - 1])
            symbol = seq[i + order - 1]
            context_counts[context] += 1
            joint_counts[(context, symbol)] += 1
        H_cond = 0.0
        total = sum(joint_counts.values())
        for (context, symbol), count in joint_counts.items():
            p_joint = count / total
            p_cond = count / context_counts[context]
            H_cond -= p_joint * np.log(p_cond) / np.log(base)
        symbols_order1, counts_order1 = np.unique(seq, return_counts=True)
        H1 = compute_shannon_entropy(counts_order1, base)["entropy"]
        return {
            "mode": "sequence_entropy", "order": order, "base": base,
            "n_symbols_unique": len(symbols_order1),
            "n_contexts_unique": len(context_counts),
            "entropy_order_1": round(H1, 6),
            "conditional_entropy_order_n": round(float(H_cond), 6),
            "structural_redundancy": round(float(H1 - H_cond), 6),
        }


def compute_information_theory(mode, **kwargs):
    """Dispatcher unico para el tool MCP information_theory, segun 'mode'."""
    fns = {
        "shannon_entropy": compute_shannon_entropy,
        "kl_divergence": compute_kl_divergence,
        "mutual_information": compute_mutual_information,
        "cross_entropy": compute_cross_entropy,
        "sequence_entropy": compute_sequence_entropy,
    }
    if mode not in fns:
        raise ValueError(f"mode desconocido: {mode}")
    return fns[mode](**kwargs)


INFORMATION_THEORY_TOOL_SCHEMA = {
    "name": "information_theory",
    "description": "Teoria de la informacion: entropia de Shannon, divergencia KL y distancia Jensen-Shannon entre distribuciones, informacion mutua entre variables conjuntas, entropia cruzada, y entropia condicional de secuencias (orden-n, para medir redundancia estructural en sistemas numerales o senales discretas).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["shannon_entropy", "kl_divergence", "mutual_information", "cross_entropy", "sequence_entropy"]},
            "distribution": {"type": "array"}, "base": {"type": "number"},
            "p": {"type": "array"}, "q": {"type": "array"},
            "joint_distribution": {"type": "array"},
            "sequence": {"type": "array"}, "order": {"type": "integer"},
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    print(compute_information_theory(mode="shannon_entropy", distribution=[0.5, 0.25, 0.25]))
    print(compute_information_theory(mode="shannon_entropy", distribution=[1, 1, 1, 1]))
    print(compute_information_theory(mode="kl_divergence", p=[0.5, 0.5], q=[0.9, 0.1]))
    print(compute_information_theory(mode="kl_divergence", p=[0.5, 0.5], q=[0.5, 0.5]))
    print(compute_information_theory(mode="mutual_information", joint_distribution=[[0.25, 0.25], [0.25, 0.25]]))
    print(compute_information_theory(mode="mutual_information", joint_distribution=[[0.4, 0.1], [0.1, 0.4]]))
    seq = list("ABABABABAB" * 5)
    print(compute_information_theory(mode="sequence_entropy", sequence=seq, order=1))
    print(compute_information_theory(mode="sequence_entropy", sequence=seq, order=2))
