"""
statistics_tool.py

Estadistica e inferencia via Octave nativo: regresion lineal (minimos
cuadrados), correlacion de Pearson, t-test de una muestra (con p-value via
la funcion beta incompleta 'betainc', nativa de Octave -- no requiere el
paquete 'statistics'), e inferencia bayesiana conjugada beta-binomial.

Pensado para que el trabajo de analisis de riesgo (inundaciones en Chile e
Iran, QGIS) tenga un camino directo a traves del ecosistema MCP en vez de
resolverse solo dentro de QGIS.

Mismo patron de validacion: presets con resultado analitico/conocido antes
de aplicar el mismo codigo a datos reales via 'custom'.
"""
import subprocess
import tempfile
import os
import math
import random

STATISTICS_SCHEMA = {
    "name": "compute_statistics",
    "description": (
        "Estadistica e inferencia via Octave: linear_regression (minimos "
        "cuadrados, pendiente/intercepto/R2), correlation (Pearson r), "
        "t_test (una muestra, t-stat + p-value via betainc), "
        "bayesian_beta_binomial (actualizacion conjugada de una tasa de "
        "exito, prior Beta(a,b) + datos binomiales -> posterior). Presets "
        "sinteticos validados o 'custom' via 'x'/'y'/'sample'."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["linear_regression", "correlation", "t_test", "bayesian_beta_binomial"],
                "default": "linear_regression",
            },
            "preset": {
                "type": "string",
                "enum": ["known_linear", "known_correlation", "known_ttest", "known_bayesian", "custom"],
                "default": "known_linear",
            },
            "x": {"type": "array", "description": "Solo si preset='custom', mode in [linear_regression, correlation]"},
            "y": {"type": "array", "description": "Solo si preset='custom', mode in [linear_regression, correlation]"},
            "sample": {"type": "array", "description": "Solo si preset='custom', mode='t_test'"},
            "mu0": {"type": "number", "default": 5.0, "description": "Media hipotetica H0, para t_test"},
            "prior_a": {"type": "number", "default": 1.0, "description": "Para bayesian_beta_binomial"},
            "prior_b": {"type": "number", "default": 1.0, "description": "Para bayesian_beta_binomial"},
            "successes": {"type": "integer", "default": 7, "description": "Para bayesian_beta_binomial"},
            "trials": {"type": "integer", "default": 10, "description": "Para bayesian_beta_binomial"},
        },
    },
}


def _run_octave(code, timeout=30):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".m", delete=False) as fh:
        fh.write(code)
        script_path = fh.name
    try:
        r = subprocess.run(["octave", "--no-gui", "--no-init-file", script_path],
                            capture_output=True, text=True, timeout=timeout)
    finally:
        os.unlink(script_path)
    if r.returncode != 0:
        return None, r.stderr.strip()
    return r.stdout.strip(), None


def _vec_to_octave(v):
    return "[" + ",".join(str(x) for x in v) + "]"


def _gen_known_linear():
    rng = random.Random(0)
    x = [i * 10 / 49 for i in range(50)]
    y = [2 * xi + 3 + rng.gauss(0, 0.1) for xi in x]
    return x, y, {"slope_esperado": 2.0, "intercept_esperado": 3.0, "nota": "ruido gaussiano chico agregado; R2 deberia ser muy cercano a 1"}


def _gen_known_correlation():
    rng = random.Random(0)
    x = [rng.gauss(0, 1) for _ in range(100)]
    y = [-3 * xi + rng.gauss(0, 0.05) for xi in x]
    return x, y, {"r_esperado": "cercano a -1.0 (relacion lineal negativa casi perfecta)"}


def _gen_known_ttest():
    rng = random.Random(1)
    sample = [rng.gauss(5, 1) for _ in range(30)]
    return sample, {"nota": "muestra generada con media poblacional real=5; test contra mu0=5 no deberia rechazar, contra mu0=6 si"}


def compute_statistics(mode="linear_regression", preset="known_linear", x=None, y=None,
                        sample=None, mu0=5.0, prior_a=1.0, prior_b=1.0, successes=7, trials=10):
    known = None

    if mode == "linear_regression":
        if preset == "custom":
            if not x or not y or len(x) != len(y):
                return {"error": "preset='custom' requiere 'x' e 'y' de igual longitud"}
        elif preset == "known_linear":
            x, y, known = _gen_known_linear()
        else:
            return {"error": f"preset '{preset}' no aplica para mode='linear_regression'"}

        x_str, y_str = _vec_to_octave(x), _vec_to_octave(y)
        code = f"""
x = {x_str}';
y = {y_str}';
n = length(x);
X = [ones(n,1), x];
coefs = X \\ y;
intercept = coefs(1);
slope = coefs(2);
y_pred = X * coefs;
ss_res = sum((y - y_pred).^2);
ss_tot = sum((y - mean(y)).^2);
r2 = 1 - ss_res/ss_tot;
printf("%.8f %.8f %.8f", slope, intercept, r2);
"""
        out, err = _run_octave(code)
        if out is None:
            return {"error": "octave fallo", "stderr": err}
        slope, intercept, r2 = [float(v) for v in out.split()]
        result = {"n_points": len(x), "slope": round(slope, 6), "intercept": round(intercept, 6), "r_squared": round(r2, 6)}

    elif mode == "correlation":
        if preset == "custom":
            if not x or not y or len(x) != len(y):
                return {"error": "preset='custom' requiere 'x' e 'y' de igual longitud"}
        elif preset == "known_correlation":
            x, y, known = _gen_known_correlation()
        else:
            return {"error": f"preset '{preset}' no aplica para mode='correlation'"}

        x_str, y_str = _vec_to_octave(x), _vec_to_octave(y)
        code = f"""
x = {x_str}';
y = {y_str}';
r = corr(x, y);
printf("%.8f", r);
"""
        out, err = _run_octave(code)
        if out is None:
            return {"error": "octave fallo", "stderr": err}
        result = {"n_points": len(x), "pearson_r": round(float(out), 6)}

    elif mode == "t_test":
        if preset == "custom":
            if not sample:
                return {"error": "preset='custom' requiere 'sample'"}
        elif preset == "known_ttest":
            sample, known = _gen_known_ttest()
        else:
            return {"error": f"preset '{preset}' no aplica para mode='t_test'"}

        s_str = _vec_to_octave(sample)
        code = f"""
s = {s_str}';
n = length(s);
xbar = mean(s);
sd = std(s);
se = sd / sqrt(n);
t = (xbar - {mu0}) / se;
df = n - 1;
xb = df / (df + t^2);
p_one_side = 0.5 * betainc(xb, df/2, 0.5);
p_two_sided = 2 * p_one_side;
printf("%.8f %.8f %.8f %.8f %d", xbar, sd, t, p_two_sided, df);
"""
        out, err = _run_octave(code)
        if out is None:
            return {"error": "octave fallo", "stderr": err}
        xbar, sd, t_stat, p_value, df = out.split()
        result = {
            "n": len(sample), "mean": round(float(xbar), 6), "std": round(float(sd), 6),
            "mu0_tested": mu0, "t_statistic": round(float(t_stat), 6),
            "p_value_two_sided": round(float(p_value), 6), "df": int(df),
            "reject_at_alpha_0.05": float(p_value) < 0.05,
        }

    elif mode == "bayesian_beta_binomial":
        if preset not in ("known_bayesian", "custom"):
            return {"error": f"preset '{preset}' no aplica para mode='bayesian_beta_binomial'"}
        code = f"""
prior_a = {prior_a}; prior_b = {prior_b};
successes = {successes}; trials = {trials};
post_a = prior_a + successes;
post_b = prior_b + (trials - successes);
post_mean = post_a / (post_a + post_b);
post_var = (post_a*post_b) / ((post_a+post_b)^2 * (post_a+post_b+1));
printf("%.8f %.8f %.8f %.8f", post_a, post_b, post_mean, post_var);
"""
        out, err = _run_octave(code)
        if out is None:
            return {"error": "octave fallo", "stderr": err}
        post_a_v, post_b_v, post_mean, post_var = [float(v) for v in out.split()]
        result = {
            "prior": {"a": prior_a, "b": prior_b},
            "data": {"successes": successes, "trials": trials},
            "posterior": {"a": round(post_a_v, 6), "b": round(post_b_v, 6)},
            "posterior_mean": round(post_mean, 6),
            "posterior_std": round(math.sqrt(post_var), 6),
        }
        if preset == "known_bayesian":
            known = {"posterior_mean_esperado": round((prior_a + successes) / (prior_a + prior_b + trials), 6)}

    else:
        return {"error": f"mode desconocido: {mode}"}

    if known:
        result["known_reference"] = known
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(compute_statistics("linear_regression", "known_linear"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_statistics("t_test", "known_ttest", mu0=5.0), indent=2, ensure_ascii=False))
    print(json.dumps(compute_statistics("t_test", "known_ttest", mu0=6.0), indent=2, ensure_ascii=False))
    print(json.dumps(compute_statistics("bayesian_beta_binomial", "known_bayesian"), indent=2, ensure_ascii=False))
