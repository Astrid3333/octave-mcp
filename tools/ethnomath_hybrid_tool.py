#!/usr/bin/env python3
"""
Tool: ethnomath_hybrid_tool
Hybrid cyclic-stochastic model: H(n) + PRNG
"""

import json
import numpy as np
from scipy import signal
import sys

def catalan(n):
    if n <= 1:
        return 1
    catalan_arr = [0] * (n + 1)
    catalan_arr[0], catalan_arr[1] = 1, 1
    for i in range(2, n + 1):
        for j in range(i):
            catalan_arr[i] += catalan_arr[j] * catalan_arr[i - 1 - j]
    return catalan_arr[n]

def prime_sum(n):
    if n <= 1:
        return 1
    factor_sum = 0
    d = 2
    temp_n = n
    while d * d <= temp_n:
        while temp_n % d == 0:
            factor_sum += d
            temp_n //= d
        d += 1
    if temp_n > 1:
        factor_sum += temp_n
    return factor_sum

GEMATRIA = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 200, 300, 400]

def H(n):
    c_n = catalan(n)
    g_n = GEMATRIA[min(n-1, len(GEMATRIA)-1)]
    factor_sum = prime_sum(g_n)
    metonium = pow(n, n % 19, 19)
    return c_n + factor_sum * metonium

def to_dna(h_val):
    map_dna = 'ATGC'
    dna = ''
    if h_val == 0:
        return 'A'
    while h_val > 0:
        digit = h_val % 4
        dna = map_dna[digit] + dna
        h_val //= 4
    return dna

def handle_validate():
    try:
        test_h = H(4)
        assert test_h == 50, f"H(4) should be 50, got {test_h}"
        test_c = catalan(5)
        assert test_c == 42, f"Catalan(5) should be 42, got {test_c}"
        np.random.seed(42)
        prng_sample = np.random.uniform(0, 1)
        assert 0 <= prng_sample <= 1, "PRNG out of range"
        dna = to_dna(10)
        assert all(c in 'ATGC' for c in dna), f"Invalid DNA: {dna}"
        return {
            "status": "PASSED",
            "mode": "validate",
            "tests": [
                "H(4) == 50: PASS",
                "Catalan(5) == 42: PASS",
                "PRNG [0,1]: PASS",
                "DNA ATGC: PASS"
            ]
        }
    except Exception as e:
        return {"status": "FAILED", "mode": "validate", "error": str(e)}

def handle_h_compute(args):
    n = int(args.get('n', 1))
    h_val = H(n)
    c_val = catalan(n)
    g_val = GEMATRIA[min(n-1, len(GEMATRIA)-1)]
    metonium = pow(n, n % 19, 19)
    return {
        "n": n,
        "H(n)": h_val,
        "Catalan(n)": c_val,
        "ratio_H_C": h_val / c_val if c_val > 0 else 0,
        "gematria": g_val,
        "metonium": metonium,
        "dna_sequence": to_dna(h_val)
    }

def handle_gracilaria(args):
    years = int(args.get('years', 30))
    base_prod = float(args.get('base_prod', 1000))
    seed = int(args.get('seed', 42))
    np.random.seed(seed)
    production = []
    for year in range(1, years + 1):
        n_metonium = (year - 1) % 19 + 1
        h_comp = H(n_metonium)
        h_factor = h_comp / 1000
        noise = (np.random.random() - 0.5) * 0.2
        prod = base_prod * h_factor * (1 + noise)
        production.append(prod)
    production = np.array(production)
    ac_19 = float(np.corrcoef(production[:-19], production[19:])[0, 1]) if len(production) >= 20 else None
    return {
        "application": "Gracilaria Chiloé",
        "years": years,
        "mean_production": float(np.mean(production)),
        "std_deviation": float(np.std(production)),
        "autocorrelation_lag_19": ac_19,
        "cycle_detectable": ac_19 > 0.3 if ac_19 else False,
        "production": production.tolist()[:15]
    }

def handle_medical(args):
    disease = args.get('disease', 'diabetes_type2')
    age_range = args.get('age_range', [20, 80])
    base_cases = float(args.get('base_cases', 100))
    seed = int(args.get('seed', 42))
    np.random.seed(seed)
    ages = np.arange(age_range[0], age_range[1] + 1)
    cases = []
    for age in ages:
        n_metonium = (age % 19) + 1
        h_comp = H(n_metonium)
        h_factor = h_comp / 1000
        noise = (np.random.random() - 0.5) * 0.2
        case_count = base_cases * h_factor * (1 + noise)
        cases.append(max(0, case_count))
    cases = np.array(cases)
    return {
        "disease": disease,
        "age_range": age_range,
        "mean_cases": float(np.mean(cases)),
        "total_cases": float(np.sum(cases)),
        "cases": cases.tolist()
    }

def analyze_series(n_years, base=1000, cycle=19, noise_pct=0.10, seed=42):
    rng = np.random.default_rng(seed)
    years_arr = np.arange(1, n_years + 1)
    h_raw = np.array([H(int((y - 1) % 19 + 1)) for y in years_arr])
    h_vals = base * (h_raw / 1000)
    noise = rng.uniform(-noise_pct, noise_pct, size=n_years)
    hybrid = h_vals * (1 + noise)
    prng_only = base * (1 + noise)

    def spectral_analysis(series):
        freqs = np.fft.rfftfreq(len(series))
        mags = np.abs(np.fft.rfft(series - series.mean()))
        top_idx = np.argsort(mags[1:])[::-1][:3] + 1
        periods = [round(1 / freqs[i], 1) if freqs[i] > 0 else None for i in top_idx]
        return {"top_periods": periods, "magnitudes": mags[top_idx].tolist()}

    def autocorr_at_lag(series, lag):
        s = (series - series.mean()) / series.std()
        return float(np.corrcoef(s[:-lag], s[lag:])[0, 1]) if lag < len(series) else None

    return {
        "mode": "analyze",
        "n_years": n_years,
        "stats": {
            "hybrid": {"mean": float(hybrid.mean()), "std": float(hybrid.std()),
                       "cv_pct": float(100 * hybrid.std() / hybrid.mean())},
            "h_only": {"mean": float(h_vals.mean()), "std": float(h_vals.std())},
            "prng_only": {"mean": float(prng_only.mean()), "std": float(prng_only.std())},
        },
        "fourier": {
            "hybrid": spectral_analysis(hybrid),
            "prng_only": spectral_analysis(prng_only),
        },
        "autocorr_lag19": {
            "hybrid": autocorr_at_lag(hybrid, cycle),
            "h_only": autocorr_at_lag(h_vals, cycle),
            "prng_only": autocorr_at_lag(prng_only, cycle),
        },
        "caveat": (
            "Top periods via raw FFT with few cycles (~{:.1f}) can show spurious "
            "peaks even in pure noise -- see prng_only's fourier magnitudes for "
            "comparison before treating hybrid's peak as evidence of a real cycle."
        ).format(n_years / cycle),
    }

def handle_analyze(args):
    n_years = int(args.get('n_years', 30))
    return analyze_series(n_years)

def main():
    try:
        input_data = json.loads(sys.stdin.read())
        mode = input_data.get('mode', 'h_compute')
        args = input_data.get('arguments', {})
        
        if mode == 'validate':
            result = handle_validate()
        elif mode == 'h_compute':
            result = handle_h_compute(args)
        elif mode == 'gracilaria':
            result = handle_gracilaria(args)
        elif mode == 'medical':
            result = handle_medical(args)
        elif mode == 'analyze':
            result = handle_analyze(args)
        else:
            result = {"error": f"Unknown mode: {mode}"}
        
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2))

if __name__ == '__main__':
    main()
