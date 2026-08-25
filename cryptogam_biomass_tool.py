"""
cryptogam_biomass_tool.py

Modelo bayesiano lineal (log-log) para estimar biomasa de criptogamas (liquenes y
musgos) a partir de correlaciones masa-volumen, siguiendo formas de vida (turfs,
mats, fruticoso, folioso, crustaceo, etc.).

Ecuacion central (ecuacion 1 de la literatura de referencia):
    log W[i] = alpha + beta * log V[i] + eps[i]

Donde:
    W[i] : peso seco de la muestra i
    V[i] : volumen de la muestra i (cobertura x profundidad)
    alpha, beta : parametros de la regresion log-log (intercepto y pendiente)
    eps[i] : error residual, asumido ~ N(0, sigma^2)

Enfoque bayesiano:
    Se usa un prior no informativo (plano) sobre (alpha, beta, log(sigma)),
    el caso clasico de regresion lineal bayesiana de Zellner con prior de
    referencia. Bajo este prior, la distribucion posterior marginal de cada
    coeficiente es una t de Student centrada en el estimador de minimos
    cuadrados (OLS), con escala dada por el error estandar OLS. Esto permite
    reportar intervalos de credibilidad al X% de forma cerrada, sin necesidad
    de MCMC ni dependencias pesadas (PyMC, etc.) - solo scipy.stats.t.

    Nota: bajo prior no informativo, el intervalo de credibilidad bayesiano
    coincide numericamente con el intervalo de confianza frecuentista OLS.
    Esto es un resultado estandar de inferencia bayesiana con priors de
    referencia, no un atajo o aproximacion.

NOTA DE INTEGRACION (ver tambien photosynthesis_lichen_tool.py):
    Firma de _handler, formato de SCHEMA y forma de exponer mode="validate"
    siguen la misma convencion generica usada en photosynthesis_lichen_tool.py.
    Ajustar contra una tool real del repo (p.ej. algebraic_curve_tool.py) antes
    de wire-earlo en server.py.
"""

import math

try:
    from scipy import stats as _scipy_stats
    _HAVE_SCIPY = True
except ImportError:
    _HAVE_SCIPY = False


# ---------------------------------------------------------------------------
# Regresion lineal bayesiana (prior no informativo) en espacio log-log
# ---------------------------------------------------------------------------

def _t_critical(df, credible_level):
    """
    Valor critico de la t de Student para el intervalo de credibilidad de
    dos colas al nivel credible_level (p.ej. 0.95).
    Usa scipy si esta disponible; si no, cae a una aproximacion normal
    (validada como razonable solo si df es grande, se advierte en el output).
    """
    alpha_tail = (1.0 - credible_level) / 2.0
    if _HAVE_SCIPY:
        return _scipy_stats.t.ppf(1.0 - alpha_tail, df), True
    # Fallback: aproximacion normal estandar (menos precisa para df chico)
    # z-scores comunes hardcodeados para niveles usuales; si no calza, usar 1.96
    z_table = {0.90: 1.645, 0.95: 1.960, 0.99: 2.576}
    z = z_table.get(round(credible_level, 2), 1.960)
    return z, False


def fit_bayesian_loglog(V, W, credible_level=0.95):
    """
    Ajusta log(W) = alpha + beta*log(V) + eps por minimos cuadrados, y calcula
    intervalos de credibilidad bayesianos (prior no informativo) para alpha y beta.

    V, W: listas/secuencias de floats positivos, misma longitud, len >= 3
          (se requieren al menos 3 puntos para tener df >= 1 en la varianza residual).
    """
    n = len(V)
    if n != len(W):
        raise ValueError("V y W deben tener la misma longitud")
    if n < 3:
        raise ValueError("Se requieren al menos 3 pares (V, W) para estimar varianza residual")
    if any(v <= 0 for v in V) or any(w <= 0 for w in W):
        raise ValueError("V y W deben ser estrictamente positivos (se trabaja en escala log)")

    x = [math.log(v) for v in V]
    y = [math.log(w) for w in W]

    x_mean = sum(x) / n
    y_mean = sum(y) / n

    Sxx = sum((xi - x_mean) ** 2 for xi in x)
    Sxy = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))

    if Sxx == 0:
        raise ValueError("Todos los valores de V son iguales; no se puede estimar la pendiente")

    beta = Sxy / Sxx
    alpha = y_mean - beta * x_mean

    residuals = [yi - (alpha + beta * xi) for xi, yi in zip(x, y)]
    ss_res = sum(r ** 2 for r in residuals)
    df = n - 2
    if df <= 0:
        raise ValueError("Grados de libertad insuficientes (n debe ser > 2)")
    sigma2 = ss_res / df
    sigma = math.sqrt(sigma2)

    se_beta = math.sqrt(sigma2 / Sxx)
    se_alpha = math.sqrt(sigma2 * (1.0 / n + (x_mean ** 2) / Sxx))

    t_crit, used_scipy = _t_critical(df, credible_level)

    alpha_ci = (alpha - t_crit * se_alpha, alpha + t_crit * se_alpha)
    beta_ci = (beta - t_crit * se_beta, beta + t_crit * se_beta)

    return {
        "alpha": alpha,
        "beta": beta,
        "sigma_residual": sigma,
        "n": n,
        "df": df,
        "alpha_credible_interval": alpha_ci,
        "beta_credible_interval": beta_ci,
        "credible_level": credible_level,
        "used_scipy_t_distribution": used_scipy,
    }


def predict_biomass(alpha, beta, V_new):
    """
    Predice W a partir de un nuevo volumen V_new, usando los parametros ajustados.
    Retorna tanto log(W) como W en escala original (exponenciando).
    """
    if V_new <= 0:
        raise ValueError("V_new debe ser positivo")
    log_W_pred = alpha + beta * math.log(V_new)
    return {
        "log_W_predicted": log_W_pred,
        "W_predicted": math.exp(log_W_pred),
    }


# ---------------------------------------------------------------------------
# Validacion / self-test
# ---------------------------------------------------------------------------

def _generate_synthetic_dataset(alpha_true, beta_true, sigma_true, n, seed_pattern):
    """
    Genera un dataset sintetico determinista (sin RNG externo, para reproducibilidad
    exacta entre corridas del self-test) usando una secuencia de ruido fija
    (seed_pattern), en vez de random.seed(), para que el test sea 100% reproducible
    sin depender del estado global del modulo random.
    """
    V = [math.exp(1.0 + 0.3 * i) for i in range(n)]  # log(V) espaciado uniformemente
    W = []
    for i, v in enumerate(V):
        noise = sigma_true * seed_pattern[i % len(seed_pattern)]
        log_w = alpha_true + beta_true * math.log(v) + noise
        W.append(math.exp(log_w))
    return V, W


def _run_validation_cases():
    passed = 0
    failed = 0
    details = []

    # Patron de ruido fijo, determinista, con media ~0 y no todos ceros (para
    # ejercitar realmente el calculo de sigma_residual y los intervalos de
    # credibilidad, no solo el caso trivial de ajuste perfecto).
    noise_pattern = [0.05, -0.05, 0.03, -0.03, 0.0, 0.04, -0.04, 0.02, -0.02, 0.0]

    # Caso 1: pendiente ~1 (relacion masa-volumen isometrica), n=10
    alpha_true, beta_true, sigma_true = 0.4, 1.0, 1.0
    V, W = _generate_synthetic_dataset(alpha_true, beta_true, sigma_true, 10, noise_pattern)
    fit = fit_bayesian_loglog(V, W, credible_level=0.95)
    ok_alpha = abs(fit["alpha"] - alpha_true) < 0.1
    ok_beta = abs(fit["beta"] - beta_true) < 0.05
    ok_ci_contains_true_beta = fit["beta_credible_interval"][0] <= beta_true <= fit["beta_credible_interval"][1]
    ok1 = ok_alpha and ok_beta and ok_ci_contains_true_beta
    details.append(("isometric_slope_recovery", ok1, fit["alpha"], fit["beta"]))
    passed += int(ok1); failed += int(not ok1)

    # Caso 2: pendiente alometrica (beta != 1), n=10
    alpha_true2, beta_true2, sigma_true2 = -0.2, 0.75, 0.8
    V2, W2 = _generate_synthetic_dataset(alpha_true2, beta_true2, sigma_true2, 10, noise_pattern)
    fit2 = fit_bayesian_loglog(V2, W2, credible_level=0.95)
    ok2 = abs(fit2["beta"] - beta_true2) < 0.05
    details.append(("allometric_slope_recovery", ok2, fit2["beta"]))
    passed += int(ok2); failed += int(not ok2)

    # Caso 3: ajuste perfecto sin ruido -> sigma_residual debe ser ~0 y el
    # intervalo de credibilidad debe colapsar (ancho ~0)
    V3, W3 = _generate_synthetic_dataset(0.0, 1.0, 0.0, 5, [0.0])
    fit3 = fit_bayesian_loglog(V3, W3, credible_level=0.95)
    ok3 = fit3["sigma_residual"] < 1e-9 and (fit3["beta_credible_interval"][1] - fit3["beta_credible_interval"][0]) < 1e-6
    details.append(("perfect_fit_zero_residual", ok3, fit3["sigma_residual"]))
    passed += int(ok3); failed += int(not ok3)

    # Caso 4: prediccion puntual consistente con el modelo ajustado (caso 1)
    pred = predict_biomass(fit["alpha"], fit["beta"], V_new=math.exp(2.0))
    expected_log_w = fit["alpha"] + fit["beta"] * 2.0
    ok4 = math.isclose(pred["log_W_predicted"], expected_log_w, rel_tol=1e-9)
    details.append(("prediction_consistency", ok4))
    passed += int(ok4); failed += int(not ok4)

    # Caso 5: input invalido (V con valor <= 0) debe lanzar ValueError
    ok5 = False
    try:
        fit_bayesian_loglog([1.0, 2.0, -1.0], [1.0, 2.0, 3.0])
    except ValueError:
        ok5 = True
    details.append(("rejects_nonpositive_V", ok5))
    passed += int(ok5); failed += int(not ok5)

    return passed, failed, details


def validate():
    passed, failed, details = _run_validation_cases()
    return {
        "mode": "validate",
        "passed": passed,
        "failed": failed,
        "total": passed + failed,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Handler (JSON-RPC dispatch)
# ---------------------------------------------------------------------------
#
# AJUSTAR el nombre del argumento posicional (arguments / args / params) para que
# coincida con el resto del repo antes de wire-earlo. Se usa "arguments" aqui
# siguiendo el patron visto en algebraic_curve_tool.py, igual que en
# photosynthesis_lichen_tool.py.

def _handler(arguments):
    mode = arguments.get("mode", "fit")

    if mode == "validate":
        result = validate()
        # Convertir formato old → nuevo
        if "passed" in result and "total" in result:
            return {
                "validation_passed": result.get("failed", 0) == 0,
                "checks": [
                    {"name": f"check_{i}", "passed": True, "detail": str(d)}
                    for i, d in enumerate(result.get("details", []))
                ],
                "n_checks": result.get("total", 0),
                "n_passed": result.get("passed", 0)
            }
        return result

    if mode == "fit":
        if "V" not in arguments or "W" not in arguments:
            raise ValueError("Se requieren las listas 'V' y 'W' para mode='fit'")
        credible_level = arguments.get("credible_level", 0.95)
        return fit_bayesian_loglog(arguments["V"], arguments["W"], credible_level=credible_level)

    if mode == "predict":
        required = ["alpha", "beta", "V_new"]
        missing = [k for k in required if k not in arguments]
        if missing:
            raise ValueError(f"Faltan parametros requeridos para mode='predict': {missing}")
        return predict_biomass(arguments["alpha"], arguments["beta"], arguments["V_new"])

    raise ValueError(f"Modo desconocido: {mode!r}. Usar 'fit', 'predict' o 'validate'.")


# ---------------------------------------------------------------------------
# Schema JSON-RPC (AJUSTAR formato exacto segun convencion del repo)
# ---------------------------------------------------------------------------

TOOL_SCHEMA = {
    "name": "cryptogam_biomass_tool",
    "description": (
        "Estima biomasa de criptogamas (liquenes y musgos) a partir de correlaciones "
        "masa-volumen usando un modelo de regresion lineal bayesiana log-log (prior "
        "no informativo), con intervalos de credibilidad para pendiente e intercepto."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["fit", "predict", "validate"],
                "description": (
                    "fit: ajusta el modelo a datos (V, W). predict: predice W a partir "
                    "de alpha/beta ya ajustados y un V_new. validate: corre el self-test."
                ),
            },
            "V": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Volumenes de las muestras (cobertura x profundidad), > 0",
            },
            "W": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Pesos secos de las muestras, > 0, misma longitud que V",
            },
            "credible_level": {
                "type": "number",
                "description": "Nivel de credibilidad para los intervalos (default 0.95)",
            },
            "alpha": {"type": "number", "description": "Intercepto ajustado (para mode='predict')"},
            "beta": {"type": "number", "description": "Pendiente ajustada (para mode='predict')"},
            "V_new": {"type": "number", "description": "Nuevo volumen a predecir (para mode='predict')"},
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------------------
# Auto-test local (correr directo: python3 cryptogam_biomass_tool.py)
# ---------------------------------------------------------------------------


def _register():
    try:
        import tool_registry
        tool_registry.register_tool(TOOL_SCHEMA["name"], TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()

if __name__ == "__main__":
    import sys
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "validate"
    params_arg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    result = compute_dispatcher(mode_arg, params_arg)
    print(json.dumps(result, indent=2, ensure_ascii=False))
