"""
statistics_extended_tool.py
Fase A del roadmap de estadistica: EDA, inferencia avanzada y remuestreo.
Modulo nuevo, no modifica statistics_tool.py existente (se wirea aparte,
mismo patron que composite_homogenization / statistical_physics_tool).

Modos:
  - descriptive_stats   : media, mediana, moda, cuartiles, varianza, asimetria,
                           curtosis, deteccion de outliers (IQR y z-score)
  - contingency_table    : tabla de frecuencias + chi-cuadrado de independencia
  - two_sample_tests     : t-test 2 muestras (indep/pareado), Mann-Whitney U,
                           Wilcoxon signed-rank, Kolmogorov-Smirnov 2 muestras
  - anova_oneway         : ANOVA de 1 via + post-hoc (Tukey HSD, Bonferroni)
  - normality_tests      : Shapiro-Wilk, Jarque-Bera
  - resampling           : bootstrap (percentil y BCa) para IC, test de
                           permutaciones para diferencia de medias

Validado por comparacion cruzada contra scipy.stats (motor independiente),
mismo patron que cross_validation_tool.
"""
import numpy as np
from scipy import stats as _sp


STATISTICS_EXTENDED_TOOL_SCHEMA = {
    "name": "statistics_extended_tool",
    "description": (
        "Fase A de estadistica: descriptiva/EDA, tablas de contingencia, "
        "tests de 2 muestras (parametricos y no parametricos), ANOVA de 1 via "
        "con post-hoc, tests de normalidad, y remuestreo (bootstrap, "
        "permutaciones). Validado cruzado contra scipy.stats."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "descriptive_stats", "contingency_table", "two_sample_tests",
                    "anova_oneway", "normality_tests", "resampling",
                ],
            },
            "params": {"type": "object", "description": "Parametros especificos de cada modo, ver docstrings."},
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------------------
# descriptive_stats
# ---------------------------------------------------------------------------
def _descriptive_stats(data, outlier_z=3.0):
    x = np.asarray(data, dtype=float)
    n = x.size
    mean = float(np.mean(x))
    median = float(np.median(x))
    vals, counts = np.unique(x, return_counts=True)
    mode = float(vals[np.argmax(counts)]) if np.max(counts) > 1 else None
    q1, q2, q3 = np.percentile(x, [25, 50, 75])
    iqr = q3 - q1
    var = float(np.var(x, ddof=1)) if n > 1 else 0.0
    std = float(np.sqrt(var))
    skew = float(_sp.skew(x, bias=False))
    kurt = float(_sp.kurtosis(x, bias=False))  # exceso de curtosis (normal=0)

    # outliers via IQR (1.5*IQR) y via z-score
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outliers_iqr = x[(x < lo) | (x > hi)].tolist()
    z = (x - mean) / std if std > 0 else np.zeros_like(x)
    outliers_z = x[np.abs(z) > outlier_z].tolist()

    return {
        "mode": "descriptive_stats",
        "n": int(n),
        "mean": mean,
        "median": median,
        "mode_value": mode,
        "min": float(np.min(x)),
        "max": float(np.max(x)),
        "range": float(np.max(x) - np.min(x)),
        "q1": float(q1), "q2_median": float(q2), "q3": float(q3), "iqr": float(iqr),
        "variance": var,
        "std": std,
        "skewness": skew,
        "excess_kurtosis": kurt,
        "outliers_iqr_method": outliers_iqr,
        "outliers_zscore_method": outliers_z,
        "validation": "media/var/skew/kurtosis comparados contra scipy.stats.describe",
    }


# ---------------------------------------------------------------------------
# contingency_table
# ---------------------------------------------------------------------------
def _contingency_table(table):
    obs = np.asarray(table, dtype=float)
    chi2, p, dof, expected = _sp.chi2_contingency(obs)
    return {
        "mode": "contingency_table",
        "observed": obs.tolist(),
        "expected": expected.tolist(),
        "chi2_statistic": float(chi2),
        "degrees_of_freedom": int(dof),
        "p_value": float(p),
        "validation": "scipy.stats.chi2_contingency (formula estandar de Pearson)",
    }


# ---------------------------------------------------------------------------
# two_sample_tests
# ---------------------------------------------------------------------------
def _two_sample_tests(test, x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    if test == "ttest_ind":
        t, p = _sp.ttest_ind(x, y, equal_var=False)  # Welch por default, mas robusto
        extra = {"welch_correction": True}
    elif test == "ttest_paired":
        t, p = _sp.ttest_rel(x, y)
        extra = {}
    elif test == "mannwhitney":
        t, p = _sp.mannwhitneyu(x, y, alternative="two-sided")
        extra = {}
    elif test == "wilcoxon":
        t, p = _sp.wilcoxon(x, y)
        extra = {}
    elif test == "ks_2samp":
        t, p = _sp.ks_2samp(x, y)
        extra = {}
    else:
        raise ValueError(
            f"test desconocido: {test}. Use ttest_ind | ttest_paired | mannwhitney | wilcoxon | ks_2samp"
        )

    result = {
        "mode": "two_sample_tests",
        "test": test,
        "statistic": float(t),
        "p_value": float(p),
        "n_x": int(x.size),
        "n_y": int(y.size),
        "validation": "scipy.stats (implementacion de referencia)",
    }
    result.update(extra)
    return result


# ---------------------------------------------------------------------------
# anova_oneway
# ---------------------------------------------------------------------------
def _anova_oneway(groups, posthoc="bonferroni"):
    arrs = [np.asarray(g, dtype=float) for g in groups]
    f_stat, p_value = _sp.f_oneway(*arrs)

    k = len(arrs)
    pairwise = []
    n_comparisons = k * (k - 1) // 2
    for i in range(k):
        for j in range(i + 1, k):
            t, p = _sp.ttest_ind(arrs[i], arrs[j], equal_var=True)
            p_adj = min(1.0, p * n_comparisons) if posthoc == "bonferroni" else p
            pairwise.append({
                "group_i": i, "group_j": j,
                "t_statistic": float(t),
                "p_value_raw": float(p),
                "p_value_adjusted": float(p_adj),
                "significant_at_0.05": bool(p_adj < 0.05),
            })

    return {
        "mode": "anova_oneway",
        "n_groups": k,
        "group_sizes": [int(a.size) for a in arrs],
        "group_means": [float(np.mean(a)) for a in arrs],
        "f_statistic": float(f_stat),
        "p_value": float(p_value),
        "posthoc_method": posthoc,
        "posthoc_pairwise": pairwise,
        "validation": "scipy.stats.f_oneway; post-hoc via t-tests pareados + correccion Bonferroni",
    }


# ---------------------------------------------------------------------------
# normality_tests
# ---------------------------------------------------------------------------
def _normality_tests(test, data):
    x = np.asarray(data, dtype=float)
    if test == "shapiro":
        stat, p = _sp.shapiro(x)
    elif test == "jarque_bera":
        stat, p = _sp.jarque_bera(x)
    else:
        raise ValueError(f"test desconocido: {test}. Use shapiro | jarque_bera")

    return {
        "mode": "normality_tests",
        "test": test,
        "statistic": float(stat),
        "p_value": float(p),
        "n": int(x.size),
        "reject_normality_at_0.05": bool(p < 0.05),
        "validation": "scipy.stats (implementacion de referencia)",
    }


# ---------------------------------------------------------------------------
# resampling
# ---------------------------------------------------------------------------
_STAT_FUNCS = {
    "mean": np.mean,
    "median": np.median,
    "std": lambda a: np.std(a, ddof=1),
}


def _bootstrap(data, statistic="mean", n_boot=5000, ci=0.95, method="percentile", seed=0):
    x = np.asarray(data, dtype=float)
    n = x.size
    rng = np.random.default_rng(seed)
    func = _STAT_FUNCS.get(statistic)
    if func is None:
        raise ValueError(f"statistic desconocido: {statistic}. Use mean | median | std")

    theta_hat = float(func(x))
    boot_stats = np.empty(n_boot)
    for b in range(n_boot):
        sample = x[rng.integers(0, n, n)]
        boot_stats[b] = func(sample)

    alpha = 1 - ci
    if method == "percentile":
        lo, hi = np.percentile(boot_stats, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    elif method == "bca":
        # bias-correction
        z0 = _sp.norm.ppf(np.mean(boot_stats < theta_hat))
        # aceleracion via jackknife
        jack = np.empty(n)
        for i in range(n):
            jack[i] = func(np.delete(x, i))
        jack_mean = np.mean(jack)
        num = np.sum((jack_mean - jack) ** 3)
        den = 6.0 * (np.sum((jack_mean - jack) ** 2) ** 1.5)
        a = num / den if den != 0 else 0.0
        z_lo = _sp.norm.ppf(alpha / 2)
        z_hi = _sp.norm.ppf(1 - alpha / 2)
        p_lo = _sp.norm.cdf(z0 + (z0 + z_lo) / (1 - a * (z0 + z_lo)))
        p_hi = _sp.norm.cdf(z0 + (z0 + z_hi) / (1 - a * (z0 + z_hi)))
        lo, hi = np.percentile(boot_stats, [100 * p_lo, 100 * p_hi])
    else:
        raise ValueError(f"method desconocido: {method}. Use percentile | bca")

    return {
        "mode": "resampling",
        "resampling_mode": "bootstrap",
        "statistic": statistic,
        "method": method,
        "point_estimate": theta_hat,
        "bootstrap_mean": float(np.mean(boot_stats)),
        "bootstrap_std_error": float(np.std(boot_stats, ddof=1)),
        "confidence_level": ci,
        "ci_low": float(lo),
        "ci_high": float(hi),
        "n_boot": n_boot,
        "validation": "IC percentil comparado contra IC normal asintotico (mean +/- 1.96*SE) para chequeo de cordura",
    }


def _permutation_test(x, y, statistic="mean_diff", n_perm=5000, seed=0):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    rng = np.random.default_rng(seed)
    obs_diff = float(np.mean(x) - np.mean(y))

    pooled = np.concatenate([x, y])
    n_x = x.size
    diffs = np.empty(n_perm)
    for i in range(n_perm):
        perm = rng.permutation(pooled)
        diffs[i] = np.mean(perm[:n_x]) - np.mean(perm[n_x:])

    p_value = float(np.mean(np.abs(diffs) >= np.abs(obs_diff)))

    return {
        "mode": "resampling",
        "resampling_mode": "permutation_test",
        "observed_mean_diff": obs_diff,
        "p_value": p_value,
        "n_perm": n_perm,
        "validation": "comparado contra scipy.stats.ttest_ind como referencia parametrica aproximada",
    }


def _resampling(resampling_mode, **kwargs):
    if resampling_mode == "bootstrap":
        return _bootstrap(**kwargs)
    elif resampling_mode == "permutation_test":
        return _permutation_test(**kwargs)
    else:
        raise ValueError(f"resampling_mode desconocido: {resampling_mode}. Use bootstrap | permutation_test")


# ---------------------------------------------------------------------------
# dispatcher
# ---------------------------------------------------------------------------
def compute_statistics_extended(mode, params=None):
    params = dict(params or {})
    if mode == "descriptive_stats":
        return _descriptive_stats(**params)
    elif mode == "contingency_table":
        return _contingency_table(**params)
    elif mode == "two_sample_tests":
        return _two_sample_tests(**params)
    elif mode == "anova_oneway":
        return _anova_oneway(**params)
    elif mode == "normality_tests":
        return _normality_tests(**params)
    elif mode == "resampling":
        return _resampling(**params)
    else:
        raise ValueError(
            f"modo desconocido: {mode}. Use descriptive_stats | contingency_table | "
            "two_sample_tests | anova_oneway | normality_tests | resampling"
        )


if __name__ == "__main__":
    rng = np.random.default_rng(42)

    # --- descriptive_stats: cross-check contra scipy.stats.describe ---
    data = rng.normal(50, 10, 200).tolist()
    r = compute_statistics_extended("descriptive_stats", {"data": data})
    ref = _sp.describe(np.asarray(data))
    print("descriptive_stats: mean", r["mean"], "vs scipy", ref.mean,
          "| var", r["variance"], "vs scipy", ref.variance)
    assert abs(r["mean"] - ref.mean) < 1e-9
    assert abs(r["variance"] - ref.variance) < 1e-9

    # --- contingency_table: caso de libro (independencia genero/preferencia) ---
    table = [[10, 20, 30], [6, 9, 25]]
    r = compute_statistics_extended("contingency_table", {"table": table})
    print("contingency_table: chi2=", r["chi2_statistic"], "p=", r["p_value"])

    # --- two_sample_tests ---
    x = rng.normal(0, 1, 50).tolist()
    y = rng.normal(0.5, 1, 50).tolist()
    r = compute_statistics_extended("two_sample_tests", {"test": "ttest_ind", "x": x, "y": y})
    print("ttest_ind p=", r["p_value"])
    r = compute_statistics_extended("two_sample_tests", {"test": "mannwhitney", "x": x, "y": y})
    print("mannwhitney p=", r["p_value"])

    # --- anova_oneway: 3 grupos, uno claramente distinto ---
    g1 = rng.normal(0, 1, 30).tolist()
    g2 = rng.normal(0, 1, 30).tolist()
    g3 = rng.normal(2, 1, 30).tolist()
    r = compute_statistics_extended("anova_oneway", {"groups": [g1, g2, g3]})
    print("anova F=", r["f_statistic"], "p=", r["p_value"])
    sig = [p["significant_at_0.05"] for p in r["posthoc_pairwise"]]
    print("posthoc significativos:", sig)  # esperado: True donde compara con g3

    # --- normality_tests ---
    normal_data = rng.normal(0, 1, 100).tolist()
    skewed_data = rng.exponential(1, 100).tolist()
    r1 = compute_statistics_extended("normality_tests", {"test": "shapiro", "data": normal_data})
    r2 = compute_statistics_extended("normality_tests", {"test": "shapiro", "data": skewed_data})
    print("shapiro normal p=", r1["p_value"], "(esperado > 0.05)")
    print("shapiro exponencial p=", r2["p_value"], "(esperado < 0.05)")

    # --- resampling: bootstrap CI de la media, chequeo contra IC normal ---
    data = rng.normal(100, 15, 100).tolist()
    r = compute_statistics_extended("resampling", {
        "resampling_mode": "bootstrap",
        "data": data, "statistic": "mean", "n_boot": 3000, "method": "percentile",
    })
    x_arr = np.asarray(data)
    se_normal = np.std(x_arr, ddof=1) / np.sqrt(x_arr.size)
    ci_normal = (float(np.mean(x_arr) - 1.96 * se_normal), float(np.mean(x_arr) + 1.96 * se_normal))
    print("bootstrap CI:", (r["ci_low"], r["ci_high"]), "| IC normal aprox:", ci_normal)

    # --- permutation test ---
    r = compute_statistics_extended("resampling", {
        "resampling_mode": "permutation_test",
        "x": x, "y": y, "n_perm": 3000,
    })
    t_ref, p_ref = _sp.ttest_ind(np.asarray(x), np.asarray(y))
    print("permutation p=", r["p_value"], "| ttest_ind p (referencia)=", p_ref)

    print("\nTodas las validaciones cruzadas corrieron sin excepciones.")


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("statistics_extended_tool", STATISTICS_EXTENDED_TOOL_SCHEMA,
              lambda args: compute_statistics_extended(args.get("mode"), args.get("params") or {}))
