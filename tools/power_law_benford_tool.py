"""
power_law_benford_tool.py

octave-mcp tool: ajuste de leyes de potencia (metodo Clauset-Shalizi-Newman,
CSN 2009) y test de conformidad con la ley de Benford (primer digito, Nigrini MAD
+ chi-cuadrado).

Modos:
  - power_law_fit : estima xmin y alpha via MLE (barrido de xmin minimizando el
                     estadistico KS), reporta bondad de ajuste (KS) y, opcionalmente,
                     un p-value bootstrap (metodo semiparametrico de Clauset et al.).
  - benford_test   : distribucion del primer digito vs. ley de Benford, chi-cuadrado
                      + MAD (Mean Absolute Deviation, escala de conformidad de Nigrini).
  - validate       : self-test interno (sin parametros de entrada), corre ambos modos
                      sobre datos sinteticos con verdad conocida y devuelve
                      validation_passed=True/False.

Convencion de registro (ver octave-mcp/tools/*): el handler SIEMPRE recibe el dict
completo de tools/call. Este modulo expone `run(mode, params)` y una funcion
`register(reg)` que hace:
    reg.register_tool(TOOL_NAME, TOOL_SCHEMA, lambda args: run(args.get("mode"), args.get("params") or {}))
"""

import math
import numpy as np

TOOL_NAME = "power_law_benford_tool"

TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": "Detección de leyes de potencia y distribuciones de Benford",
    "inputSchema": {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["power_law_fit", "benford_test", "validate"],
        },
        "params": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Muestra de valores positivos (power_law_fit) o conteos/magnitudes (benford_test).",
                },
                "discrete": {
                    "type": "boolean",
                    "description": "power_law_fit: True si los datos son enteros/discretos (usa MLE discreta aproximada). Default False (continua).",
                },
                "xmin_candidates": {
                    "type": "integer",
                    "description": "power_law_fit: numero de valores candidatos de xmin a barrer (default 50, tomados de los valores unicos ordenados de la muestra).",
                },
                "bootstrap_samples": {
                    "type": "integer",
                    "description": "power_law_fit: numero de replicas bootstrap semiparametricas para el p-value de bondad de ajuste (default 0 = omitir, es costoso). Recomendado 200+ para uso real.",
                },
                "digits": {
                    "type": "integer",
                    "description": "benford_test: cuantos digitos iniciales testear (1 = primer digito clasico, 2 = primeros dos digitos). Default 1.",
                },
            },
            "required": ["data"],
        },
    },
    "required": ["mode"],
    }
}


# ---------------------------------------------------------------------------
# power_law_fit — metodo Clauset-Shalizi-Newman (CSN)
# ---------------------------------------------------------------------------

def _mle_alpha_continuous(x, xmin):
    x = x[x >= xmin]
    n = len(x)
    if n < 2:
        return None, n
    alpha = 1.0 + n / np.sum(np.log(x / xmin))
    return alpha, n


def _mle_alpha_discrete(x, xmin):
    # Aproximacion de Newton (Clauset et al. 2009, eq. 3.7) via bisection sobre
    # zeta(alpha, xmin) sin depender de mpmath: usamos la aproximacion continua
    # con correccion de media entero (xmin - 0.5), suficientemente buena para
    # datos discretos de cola larga (no es la MLE exacta con funcion zeta de Hurwitz).
    x = x[x >= xmin]
    n = len(x)
    if n < 2:
        return None, n
    alpha = 1.0 + n / np.sum(np.log(x / (xmin - 0.5)))
    return alpha, n


def _ks_statistic(x, xmin, alpha, discrete):
    x = np.sort(x[x >= xmin])
    n = len(x)
    if n == 0:
        return np.inf
    empirical_cdf = np.arange(1, n + 1) / n
    if discrete:
        # CDF de la ley de potencia discreta aproximada por la continua (suficiente
        # para el barrido de xmin; el objetivo es comparar formas relativas).
        theoretical_cdf = 1.0 - (x / xmin) ** (-(alpha - 1.0))
    else:
        theoretical_cdf = 1.0 - (x / xmin) ** (-(alpha - 1.0))
    return np.max(np.abs(empirical_cdf - theoretical_cdf))


def _fit_power_law(data, discrete=False, xmin_candidates=50):
    x = np.asarray(data, dtype=float)
    x = x[x > 0]
    x = np.sort(x)
    if len(x) < 10:
        raise ValueError("Se necesitan al menos 10 puntos positivos para un ajuste confiable.")

    unique_vals = np.unique(x)
    if len(unique_vals) > xmin_candidates:
        idx = np.linspace(0, len(unique_vals) - 1, xmin_candidates).astype(int)
        candidates = unique_vals[idx]
    else:
        candidates = unique_vals[:-1] if len(unique_vals) > 1 else unique_vals

    best = None
    mle_fn = _mle_alpha_discrete if discrete else _mle_alpha_continuous
    for xmin in candidates:
        alpha, n_tail = mle_fn(x, xmin)
        if alpha is None or n_tail < 5:
            continue
        ks = _ks_statistic(x, xmin, alpha, discrete)
        if best is None or ks < best["ks"]:
            best = {"xmin": float(xmin), "alpha": float(alpha), "ks": float(ks), "n_tail": int(n_tail)}

    if best is None:
        raise ValueError("No se pudo ajustar: muy pocos puntos por encima de cualquier xmin candidato.")
    return best, x


def _bootstrap_pvalue(x, best, discrete, n_bootstrap, rng):
    """P-value semiparametrico (Clauset, Shalizi & Newman 2009, seccion 4).
    Genera muestras sinteticas: por debajo de xmin, remuestrea de los datos
    originales; por encima de xmin, muestrea de la ley de potencia ajustada.
    Refitea cada replica y compara el KS observado contra la distribucion nula.
    """
    xmin, alpha, ks_obs = best["xmin"], best["alpha"], best["ks"]
    below = x[x < xmin]
    n = len(x)
    n_tail = best["n_tail"]
    p_tail = n_tail / n
    count_ge = 0
    mle_fn = _mle_alpha_discrete if discrete else _mle_alpha_continuous

    for _ in range(n_bootstrap):
        n_tail_sim = rng.binomial(n, p_tail)
        n_below_sim = n - n_tail_sim
        below_sample = rng.choice(below, size=n_below_sim, replace=True) if len(below) > 0 and n_below_sim > 0 else np.array([])
        # muestreo de ley de potencia continua por inversion: x = xmin * (1-u)^(-1/(alpha-1))
        u = rng.random(n_tail_sim)
        tail_sample = xmin * (1.0 - u) ** (-1.0 / (alpha - 1.0)) if n_tail_sim > 0 else np.array([])
        synth = np.concatenate([below_sample, tail_sample])
        synth = np.sort(synth[synth > 0])
        if len(synth) < 10:
            continue
        try:
            sim_best, _ = _fit_power_law(synth, discrete=discrete, xmin_candidates=30)
        except ValueError:
            continue
        if sim_best["ks"] >= ks_obs:
            count_ge += 1

    return count_ge / n_bootstrap if n_bootstrap > 0 else None


def power_law_fit(params):
    data = params.get("data")
    if not data:
        raise ValueError("params.data es requerido (lista de valores positivos).")
    discrete = bool(params.get("discrete", False))
    xmin_candidates = int(params.get("xmin_candidates", 50))
    n_bootstrap = int(params.get("bootstrap_samples", 0))

    best, x = _fit_power_law(data, discrete=discrete, xmin_candidates=xmin_candidates)

    result = {
        "xmin": best["xmin"],
        "alpha": best["alpha"],
        "ks_statistic": best["ks"],
        "n_total": int(len(x)),
        "n_tail": best["n_tail"],
        "tail_fraction": best["n_tail"] / len(x),
        "discrete": discrete,
        "interpretation": (
            "alpha tipico de fenomenos de cola pesada esta en 2-3; alpha<2 o KS alto "
            "sugiere que la ley de potencia no es un buen modelo o que los datos "
            "estan truncados/manipulados en la cola."
        ),
    }

    if n_bootstrap > 0:
        rng = np.random.default_rng(12345)
        p = _bootstrap_pvalue(x, best, discrete, n_bootstrap, rng)
        result["goodness_of_fit_pvalue"] = p
        result["goodness_of_fit_note"] = (
            "p > 0.1 (regla de Clauset et al.): la ley de potencia es un modelo "
            "plausible para la cola. p <= 0.1: se puede rechazar la hipotesis de "
            "ley de potencia."
        )

    return result


# ---------------------------------------------------------------------------
# benford_test — primer digito (o primeros N digitos) vs ley de Benford
# ---------------------------------------------------------------------------

def _benford_expected_probs(digits):
    if digits == 1:
        d = np.arange(1, 10)
        p = np.log10(1.0 + 1.0 / d)
        return d.astype(str).tolist(), p
    elif digits == 2:
        d = np.arange(10, 100)
        p = np.log10(1.0 + 1.0 / d)
        return d.astype(str).tolist(), p
    else:
        raise ValueError("digits debe ser 1 o 2.")


def _leading_digits(x, digits):
    x = np.abs(x)
    x = x[x > 0]
    exponents = np.floor(np.log10(x)).astype(int)
    normalized = x / (10.0 ** exponents)  # en [1, 10)
    if digits == 1:
        lead = np.floor(normalized).astype(int)
        lead = np.clip(lead, 1, 9)
    else:
        lead = np.floor(normalized * 10).astype(int)
        lead = np.clip(lead, 10, 99)
    return lead


def benford_test(params):
    data = params.get("data")
    if not data:
        raise ValueError("params.data es requerido (lista de valores/conteos positivos).")
    digits = int(params.get("digits", 1))
    x = np.asarray(data, dtype=float)
    x = x[x > 0]
    n = len(x)
    if n < 30:
        raise ValueError("Se recomiendan al menos 30 observaciones positivas para un test de Benford confiable.")

    labels, expected_p = _benford_expected_probs(digits)
    lead = _leading_digits(x, digits)

    start = 1 if digits == 1 else 10
    observed_counts = np.array([np.sum(lead == (start + i)) for i in range(len(labels))], dtype=float)
    observed_p = observed_counts / n
    expected_counts = expected_p * n

    # Chi-cuadrado de bondad de ajuste
    with np.errstate(divide="ignore", invalid="ignore"):
        chi2 = np.sum(np.where(expected_counts > 0, (observed_counts - expected_counts) ** 2 / expected_counts, 0.0))
    dof = len(labels) - 1

    # p-value via scipy si esta disponible; si no, deja el chi2 crudo
    try:
        from scipy import stats as _stats
        p_value = float(1.0 - _stats.chi2.cdf(chi2, dof))
    except ImportError:
        p_value = None

    # MAD (Mean Absolute Deviation) — escala de conformidad de Nigrini (2012)
    mad = float(np.mean(np.abs(observed_p - expected_p)))
    if digits == 1:
        if mad < 0.006:
            conformity = "conformidad_cercana"
        elif mad < 0.012:
            conformity = "conformidad_aceptable"
        elif mad < 0.015:
            conformity = "conformidad_marginal"
        else:
            conformity = "no_conforme"
    else:
        conformity = "usar_umbrales_MAD_especificos_para_2_digitos"

    return {
        "digits": digits,
        "n": int(n),
        "observed_proportions": dict(zip(labels, observed_p.tolist())),
        "expected_proportions_benford": dict(zip(labels, expected_p.tolist())),
        "chi2_statistic": float(chi2),
        "degrees_of_freedom": dof,
        "chi2_p_value": p_value,
        "mad": mad,
        "conformity_nigrini": conformity,
        "interpretation": (
            "MAD bajo + p-value alto => los datos son consistentes con Benford "
            "(naturales, no manipulados/generados en lote). Desviacion fuerte "
            "(no_conforme, p-value bajo) es señal de datos artificiales, redondeados, "
            "truncados, o generados con un rango acotado (tipico de cuentas creadas en lote)."
        ),
    }


# ---------------------------------------------------------------------------
# validate — self-test
# ---------------------------------------------------------------------------

def _validate():
    rng = np.random.default_rng(42)
    checks = {}

    # 1) power_law_fit sobre una muestra sintetica Pareto(alpha=2.5, xmin=1)
    true_alpha = 2.5
    n = 5000
    u = rng.random(n)
    synth_pl = (1.0 - u) ** (-1.0 / (true_alpha - 1.0))  # xmin=1
    fit = power_law_fit({"data": synth_pl.tolist(), "xmin_candidates": 30})
    alpha_err = abs(fit["alpha"] - true_alpha)
    checks["power_law_alpha_recovery"] = {
        "true_alpha": true_alpha,
        "estimated_alpha": fit["alpha"],
        "abs_error": alpha_err,
        "passed": alpha_err < 0.25,
    }

    # 2) benford_test sobre datos que SI siguen Benford (10^Uniform(0,4): magnitudes
    #    fisicas/economicas naturales siguen aproximadamente esta ley)
    benford_like = 10 ** rng.uniform(0, 4, size=4000)
    bt_pass = benford_test({"data": benford_like.tolist()})
    checks["benford_positive_case"] = {
        "mad": bt_pass["mad"],
        "conformity": bt_pass["conformity_nigrini"],
        "passed": bt_pass["conformity_nigrini"] in ("conformidad_cercana", "conformidad_aceptable"),
    }

    # 3) benford_test sobre datos que NO deberian seguir Benford (uniforme estrecho,
    #    tipico de conteos manipulados/lote, ej. seguidores entre 900 y 1100)
    non_benford = rng.uniform(900, 1100, size=4000)
    bt_fail = benford_test({"data": non_benford.tolist()})
    checks["benford_negative_case"] = {
        "mad": bt_fail["mad"],
        "conformity": bt_fail["conformity_nigrini"],
        "passed": bt_fail["conformity_nigrini"] == "no_conforme",
    }

    all_passed = all(c["passed"] for c in checks.values())
    return {
        "validation_passed": bool(all_passed),
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

def run(mode, params):
    params = params or {}
    if mode == "power_law_fit":
        return power_law_fit(params)
    elif mode == "benford_test":
        return benford_test(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"Modo desconocido: {mode!r}. Modos validos: power_law_fit, benford_test, validate.")


def register(reg):
    """Llamar desde server.py: from tools.power_law_benford_tool import register; register(tool_registry)"""
    reg.register_tool(TOOL_NAME, TOOL_SCHEMA, lambda args: run(args.get("mode"), args.get("params") or {}))


if __name__ == "__main__":
    import json
    print(json.dumps(run("validate", {}), indent=2, ensure_ascii=False))
