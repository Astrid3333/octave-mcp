#!/usr/bin/env python3
"""
population_genetics_tool.py
Genetica de poblaciones: equilibrio de Hardy-Weinberg (con test chi-cuadrado),
deriva genica (simulacion de Wright-Fisher), seleccion natural (dinamica
deterministica de frecuencias alelicas), coalescencia (tiempo esperado al
MRCA), y distancias geneticas (Fst de Wright, distancia de Nei).
"""
import math
import numpy as np
from scipy.stats import chi2


def compute_hardy_weinberg(p, observed_counts=None):
    q = 1 - p
    expected_freq = {"AA": p ** 2, "Aa": 2 * p * q, "aa": q ** 2}
    result = {
        "mode": "hardy_weinberg",
        "p": p, "q": round(q, 6),
        "expected_frequencies": {k: round(v, 6) for k, v in expected_freq.items()},
    }
    if observed_counts is not None:
        n = sum(observed_counts.values())
        expected_counts = {k: v * n for k, v in expected_freq.items()}
        chi2_stat = sum(
            (observed_counts[k] - expected_counts[k]) ** 2 / expected_counts[k]
            for k in expected_counts
        )
        p_value = float(chi2.sf(chi2_stat, df=1))
        result["observed_counts"] = observed_counts
        result["expected_counts"] = {k: round(v, 4) for k, v in expected_counts.items()}
        result["chi2_statistic"] = round(chi2_stat, 6)
        result["p_value"] = round(p_value, 6)
        result["in_hwe"] = p_value > 0.05
    return result


def compute_genetic_drift(N, p0, generations, n_simulations=1000, seed=None, track_every=None):
    """
    Simulacion de Wright-Fisher: en cada generacion se muestrean 2N alelos
    (poblacion diploide) de una binomial con probabilidad p de la generacion
    anterior. Sin seleccion ni mutacion, es un martingala puro - por eso la
    probabilidad de fijacion (p->1) debe converger a p0 con generaciones
    suficientes, y es el mecanismo por el cual poblaciones pequenas pueden
    perder variabilidad genetica (o alelos raros) puramente por azar, sin que
    medie ninguna ventaja selectiva - relevante para anticipar perdida de
    diversidad genetica tras un cuello de botella poblacional.
    """
    rng = np.random.default_rng(seed)
    p = np.full(n_simulations, p0, dtype=float)
    if track_every is None:
        track_every = max(1, generations // 20)
    trajectory = [{"generation": 0, "mean_frequency": round(float(p.mean()), 6),
                   "std_frequency": round(float(p.std()), 6)}]
    for gen in range(1, generations + 1):
        counts = rng.binomial(2 * N, p)
        p = counts / (2 * N)
        if gen % track_every == 0 or gen == generations:
            trajectory.append({"generation": gen, "mean_frequency": round(float(p.mean()), 6),
                                "std_frequency": round(float(p.std()), 6)})
    fixation_prob = float((p == 1.0).mean())
    loss_prob = float((p == 0.0).mean())
    still_segregating = float(((p > 0) & (p < 1)).mean())
    expected_het_final = float((2 * p * (1 - p)).mean())
    return {
        "mode": "genetic_drift",
        "N": N, "p0": p0, "generations": generations, "n_simulations": n_simulations,
        "fixation_probability": round(fixation_prob, 6),
        "loss_probability": round(loss_prob, 6),
        "still_segregating_probability": round(still_segregating, 6),
        "expected_heterozygosity_final": round(expected_het_final, 6),
        "trajectory_mean_frequency": trajectory,
    }


def compute_natural_selection(p0, generations, w_AA=1.0, w_Aa=1.0, w_aa=1.0, track_every=None):
    p = p0
    if track_every is None:
        track_every = max(1, generations // 20)
    trajectory = [{"generation": 0, "frequency": round(p0, 6)}]
    for gen in range(1, generations + 1):
        q = 1 - p
        wbar = p ** 2 * w_AA + 2 * p * q * w_Aa + q ** 2 * w_aa
        p = (p ** 2 * w_AA + p * q * w_Aa) / wbar
        if gen % track_every == 0 or gen == generations:
            trajectory.append({"generation": gen, "frequency": round(p, 6)})
    return {
        "mode": "natural_selection",
        "p0": p0, "generations": generations,
        "fitness": {"w_AA": w_AA, "w_Aa": w_Aa, "w_aa": w_aa},
        "final_frequency": round(p, 6),
        "mean_fitness_final": round(p ** 2 * w_AA + 2 * p * (1 - p) * w_Aa + (1 - p) ** 2 * w_aa, 6),
        "trajectory": trajectory,
    }


def compute_coalescence(sample_size, effective_population_size, ploidy=2):
    Ne = effective_population_size
    per_k = []
    total_tmrca = 0.0
    total_tree_length = 0.0
    for k in range(sample_size, 1, -1):
        Tk = 2 * (ploidy * Ne) / (k * (k - 1))
        per_k.append({"k_lineages": k, "expected_time_generations": round(Tk, 4)})
        total_tmrca += Tk
        total_tree_length += k * Tk
    return {
        "mode": "coalescence",
        "sample_size": sample_size,
        "effective_population_size": Ne,
        "ploidy": ploidy,
        "per_k_lineages": per_k,
        "expected_tmrca_generations": round(total_tmrca, 4),
        "expected_total_tree_length_generations": round(total_tree_length, 4),
    }


def compute_genetic_distance(method="fst", freq_pop1=None, freq_pop2=None):
    if method == "fst":
        if freq_pop1 is None or freq_pop2 is None:
            raise ValueError("freq_pop1 y freq_pop2 (frecuencias alelicas por locus) son requeridos")
        p1 = np.asarray(freq_pop1, dtype=float)
        p2 = np.asarray(freq_pop2, dtype=float)
        pbar = (p1 + p2) / 2
        Ht = 2 * pbar * (1 - pbar)
        H1 = 2 * p1 * (1 - p1)
        H2 = 2 * p2 * (1 - p2)
        Hs = (H1 + H2) / 2
        with np.errstate(divide="ignore", invalid="ignore"):
            fst_per_locus = np.where(Ht > 0, (Ht - Hs) / Ht, 0.0)
        return {
            "mode": "genetic_distance", "method": "fst",
            "n_loci": len(p1),
            "fst_per_locus": [round(float(x), 6) for x in fst_per_locus],
            "fst_mean": round(float(np.mean(fst_per_locus)), 6),
        }
    elif method == "nei":
        if freq_pop1 is None or freq_pop2 is None:
            raise ValueError("freq_pop1 y freq_pop2 (listas de listas: loci x alelos) son requeridos")
        n_loci = len(freq_pop1)
        Jxy_sum = Jx_sum = Jy_sum = 0.0
        for locus1, locus2 in zip(freq_pop1, freq_pop2):
            a1 = np.asarray(locus1, dtype=float)
            a2 = np.asarray(locus2, dtype=float)
            Jxy_sum += float(np.sum(a1 * a2))
            Jx_sum += float(np.sum(a1 ** 2))
            Jy_sum += float(np.sum(a2 ** 2))
        Jxy, Jx, Jy = Jxy_sum / n_loci, Jx_sum / n_loci, Jy_sum / n_loci
        I = Jxy / math.sqrt(Jx * Jy)
        D = -math.log(I) if I > 0 else float("inf")
        return {
            "mode": "genetic_distance", "method": "nei",
            "n_loci": n_loci,
            "genetic_identity_I": round(I, 6),
            "genetic_distance_D": round(D, 6),
        }
    else:
        raise ValueError(f"method desconocido: {method}")


def compute_population_genetics(mode, **kwargs):
    """Dispatcher unico para el tool MCP population_genetics, segun 'mode'."""
    fns = {
        "hardy_weinberg": compute_hardy_weinberg,
        "genetic_drift": compute_genetic_drift,
        "natural_selection": compute_natural_selection,
        "coalescence": compute_coalescence,
        "genetic_distance": compute_genetic_distance,
    }
    if mode not in fns:
        raise ValueError(f"mode desconocido: {mode}")
    return fns[mode](**kwargs)


POPULATION_GENETICS_TOOL_SCHEMA = {
    "name": "population_genetics",
    "description": "Genetica de poblaciones: equilibrio de Hardy-Weinberg (con test chi-cuadrado), deriva genica (simulacion de Wright-Fisher), seleccion natural (dinamica de frecuencias alelicas), coalescencia (tiempo esperado al MRCA), y distancias geneticas (Fst de Wright, distancia de Nei).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["hardy_weinberg", "genetic_drift", "natural_selection", "coalescence", "genetic_distance"]},
            "p": {"type": "number"},
            "observed_counts": {"type": "object"},
            "N": {"type": "integer"}, "p0": {"type": "number"}, "generations": {"type": "integer"},
            "n_simulations": {"type": "integer"}, "seed": {"type": "integer"}, "track_every": {"type": "integer"},
            "w_AA": {"type": "number"}, "w_Aa": {"type": "number"}, "w_aa": {"type": "number"},
            "sample_size": {"type": "integer"}, "effective_population_size": {"type": "number"}, "ploidy": {"type": "integer"},
            "method": {"type": "string", "enum": ["fst", "nei"]},
            "freq_pop1": {"type": "array"}, "freq_pop2": {"type": "array"},
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    print(compute_population_genetics(mode="hardy_weinberg", p=0.6))
    print(compute_population_genetics(mode="hardy_weinberg", p=0.6, observed_counts={"AA": 40, "Aa": 40, "aa": 20}))
    print(compute_population_genetics(mode="genetic_drift", N=20, p0=0.5, generations=200, n_simulations=2000, seed=42))
    print(compute_population_genetics(mode="natural_selection", p0=0.1, generations=50, w_AA=1.0, w_Aa=0.9, w_aa=0.5))
    print(compute_population_genetics(mode="coalescence", sample_size=5, effective_population_size=1000))
    print(compute_population_genetics(mode="genetic_distance", method="fst", freq_pop1=[0.3, 0.5, 0.7], freq_pop2=[0.6, 0.5, 0.2]))
    print(compute_population_genetics(mode="genetic_distance", method="nei", freq_pop1=[[0.3, 0.7], [0.5, 0.5]], freq_pop2=[[0.6, 0.4], [0.5, 0.5]]))
