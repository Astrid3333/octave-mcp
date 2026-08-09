"""
econometrics_tool.py
======================
Modulo para octave-mcp / mcp-octave-real siguiendo el patron:
    compute_econometrics(mode, params) -> dict
    ECONOMETRICS_TOOL_SCHEMA (JSONRPC tool schema)

Cubre:
  - adf_test                : Augmented Dickey-Fuller (test de raiz unitaria)
  - arima_forecast          : ARIMA(p,d,q) via conditional least squares (MLE aprox)
  - garch_fit               : GARCH(1,1) via maxima verosimilitud (normal)
  - engle_granger_coint     : Cointegracion de Engle-Granger (2 pasos)
  - panel_fixed_effects     : Modelo de panel con efectos fijos (within estimator)
  - iv_2sls                 : Variables instrumentales / 2SLS
  - granger_causality       : Test de causalidad de Granger (F-test sobre VAR)

Complementa:
  - statistics_tool         : para tests de hipotesis generales, distribuciones
  - cross_validation_tool   : para particionado walk-forward de series
                               temporales (NO usar k-fold random en series
                               temporales -- rompe la estructura temporal).

Dependencias: numpy + scipy.optimize (scipy.stats para p-values).
Si falta scipy: `pip install scipy --break-system-packages`

Convenciones:
  - Todas las funciones reciben `params: dict` y devuelven `dict` JSON-able.
  - Series temporales se pasan como listas de floats, orden cronologico.
  - Los p-values de ADF/Engle-Granger usan aproximaciones de MacKinnon
    (tablas simplificadas), no son exactos pero sirven de guia -- para
    decisiones criticas contrastar con tablas completas.
"""

import numpy as np

try:
    from scipy import optimize as _sp_optimize
    from scipy import stats as _sp_stats
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


def _require_scipy():
    if not _HAS_SCIPY:
        raise RuntimeError(
            "Este modo requiere scipy. Instalar con: "
            "pip install scipy --break-system-packages"
        )


def _as_array(x, name):
    try:
        arr = np.asarray(x, dtype=float)
    except Exception as e:
        raise ValueError(f"'{name}' debe ser numerico: {e}")
    return arr


def _ols(X, y):
    """OLS via minimos cuadrados. X incluye columna de 1s si se quiere intercepto."""
    X = np.atleast_2d(X)
    coef, residuals, rank, sv = np.linalg.lstsq(X, y, rcond=None)
    y_hat = X @ coef
    resid = y - y_hat
    n, k = X.shape
    dof = max(n - k, 1)
    sigma2 = float(resid @ resid) / dof
    try:
        XtX_inv = np.linalg.pinv(X.T @ X)
        se = np.sqrt(np.clip(np.diag(sigma2 * XtX_inv), 0, None))
    except np.linalg.LinAlgError:
        se = np.full(k, np.nan)
    return {
        "coef": coef, "resid": resid, "y_hat": y_hat,
        "se": se, "sigma2": sigma2, "n": n, "k": k, "dof": dof,
    }


def _lag_matrix(x, n_lags):
    """Devuelve matriz de rezagos [x_{t-1}, ..., x_{t-n_lags}] alineada, y el
    vector x_t recortado para que coincidan las filas."""
    n = len(x)
    if n_lags >= n:
        raise ValueError("n_lags debe ser menor que el largo de la serie.")
    rows = n - n_lags
    lagged = np.zeros((rows, n_lags))
    for lag in range(1, n_lags + 1):
        lagged[:, lag - 1] = x[n_lags - lag: n - lag]
    current = x[n_lags:]
    return current, lagged


# ---------------------------------------------------------------------------
# ADF test (Augmented Dickey-Fuller)
# ---------------------------------------------------------------------------

_ADF_CRITICAL_VALUES = {"1%": -3.43, "5%": -2.86, "10%": -2.57}


def adf_test(params):
    """
    params:
      series: list[float]   -- REQUERIDO
      n_lags: int            -- default: auto (Schwert)
      regression: 'c'        -- solo 'c' (constante) implementado
    """
    series = params.get("series")
    if series is None:
        raise ValueError("Falta 'series'.")
    y = _as_array(series, "series")
    n = len(y)
    if n < 15:
        raise ValueError("Se requieren al menos 15 observaciones para ADF confiable.")

    n_lags = params.get("n_lags")
    if n_lags is None:
        n_lags = int(np.ceil(12 * (n / 100) ** 0.25))
    n_lags = max(0, min(int(n_lags), n // 3))

    dy = np.diff(y)
    y_lag1 = y[:-1]

    if n_lags > 0:
        dy_current, dy_lagged = _lag_matrix(dy, n_lags)
        y_lag1_aligned = y_lag1[n_lags:]
        X = np.column_stack([
            np.ones(len(dy_current)), y_lag1_aligned, dy_lagged
        ])
        y_reg = dy_current
    else:
        X = np.column_stack([np.ones(len(dy)), y_lag1])
        y_reg = dy

    fit = _ols(X, y_reg)
    rho_idx = 1
    rho = fit["coef"][rho_idx]
    se_rho = fit["se"][rho_idx]
    t_stat = float(rho / se_rho) if se_rho > 0 else float("nan")

    if t_stat < _ADF_CRITICAL_VALUES["1%"]:
        conclusion = "Rechaza H0 al 1%: serie estacionaria (no tiene raiz unitaria)."
    elif t_stat < _ADF_CRITICAL_VALUES["5%"]:
        conclusion = "Rechaza H0 al 5%: serie estacionaria (no tiene raiz unitaria)."
    elif t_stat < _ADF_CRITICAL_VALUES["10%"]:
        conclusion = "Rechaza H0 al 10%: evidencia debil de estacionariedad."
    else:
        conclusion = "No rechaza H0: serie probablemente tiene raiz unitaria (no estacionaria)."

    return {
        "test": "Augmented Dickey-Fuller",
        "n_lags_used": n_lags,
        "n_obs": n,
        "adf_statistic": t_stat,
        "critical_values": _ADF_CRITICAL_VALUES,
        "conclusion": conclusion,
        "note": ("Valores criticos aproximados de MacKinnon (1996), regresion "
                 "con constante sin tendencia. Para decisiones criticas, "
                 "contrastar con tablas completas o bootstrap."),
    }


# ---------------------------------------------------------------------------
# ARIMA(p,d,q) via conditional least squares
# ---------------------------------------------------------------------------

def _difference(y, d):
    for _ in range(d):
        y = np.diff(y)
    return y


def _undifference(diffed, original_tail, d):
    result = diffed.copy()
    seed = list(original_tail[-d:]) if d > 0 else []
    for _ in range(d):
        base = seed.pop()
        cum = np.concatenate([[base], result])
        result = np.cumsum(cum)[1:]
    return result


def _arma_neg_log_likelihood(theta, y, p, q):
    c = theta[0]
    phi = theta[1:1 + p]
    psi = theta[1 + p:1 + p + q]
    n = len(y)
    resid = np.zeros(n)
    for t in range(n):
        ar_part = sum(phi[i] * y[t - 1 - i] for i in range(p) if t - 1 - i >= 0)
        ma_part = sum(psi[j] * resid[t - 1 - j] for j in range(q) if t - 1 - j >= 0)
        pred = c + ar_part + ma_part
        resid[t] = y[t] - pred
    sigma2 = np.mean(resid ** 2)
    if sigma2 <= 0:
        return 1e10
    nll = 0.5 * n * np.log(2 * np.pi * sigma2) + 0.5 * np.sum(resid ** 2) / sigma2
    return float(nll)


def arima_forecast(params):
    """
    params:
      series: list[float]   -- REQUERIDO
      p: int                -- orden AR, default 1
      d: int                -- orden de diferenciacion, default 0
      q: int                -- orden MA, default 0
      n_forecast: int        -- pasos a pronosticar, default 5
    """
    _require_scipy()
    series = params.get("series")
    if series is None:
        raise ValueError("Falta 'series'.")
    y_original = _as_array(series, "series")
    p = int(params.get("p", 1))
    d = int(params.get("d", 0))
    q = int(params.get("q", 0))
    n_forecast = int(params.get("n_forecast", 5))

    y = _difference(y_original, d)
    if len(y) < (p + q + 5):
        raise ValueError("Serie muy corta para el orden ARIMA solicitado.")

    n_params = 1 + p + q
    theta0 = np.zeros(n_params)
    theta0[0] = np.mean(y)

    res = _sp_optimize.minimize(
        _arma_neg_log_likelihood, theta0, args=(y, p, q),
        method="Nelder-Mead",
        options={"maxiter": 2000, "xatol": 1e-6, "fatol": 1e-6},
    )
    theta = res.x
    c = theta[0]
    phi = theta[1:1 + p].tolist()
    psi = theta[1 + p:1 + p + q].tolist()

    n = len(y)
    resid = np.zeros(n)
    for t in range(n):
        ar_part = sum(theta[1 + i] * y[t - 1 - i] for i in range(p) if t - 1 - i >= 0)
        ma_part = sum(theta[1 + p + j] * resid[t - 1 - j] for j in range(q) if t - 1 - j >= 0)
        pred = c + ar_part + ma_part
        resid[t] = y[t] - pred
    sigma2 = float(np.mean(resid ** 2))

    y_ext = list(y)
    resid_ext = list(resid)
    for _ in range(n_forecast):
        t = len(y_ext)
        ar_part = sum(theta[1 + i] * y_ext[t - 1 - i] for i in range(p) if t - 1 - i >= 0)
        ma_part = sum(theta[1 + p + j] * resid_ext[t - 1 - j] for j in range(q) if t - 1 - j >= 0)
        pred = c + ar_part + ma_part
        y_ext.append(pred)
        resid_ext.append(0.0)

    forecast_diffed = np.array(y_ext[len(y):])

    if d > 0:
        forecast_levels = _undifference(forecast_diffed, y_original, d)
    else:
        forecast_levels = forecast_diffed

    return {
        "method": f"ARIMA({p},{d},{q}) via conditional least squares",
        "converged": bool(res.success),
        "const": float(c),
        "ar_coefficients": phi,
        "ma_coefficients": psi,
        "sigma2": sigma2,
        "aic_approx": float(2 * n_params + n * np.log(sigma2 + 1e-12)),
        "n_forecast": n_forecast,
        "forecast": forecast_levels.tolist(),
        "note": ("Forecast asume shocks futuros de MA en 0 (esperanza condicional). "
                 "AIC aproximado (no incluye correccion exacta de likelihood constante)."),
    }


# ---------------------------------------------------------------------------
# GARCH(1,1)
# ---------------------------------------------------------------------------

def _garch11_neg_log_likelihood(theta, r):
    omega, alpha, beta = theta
    if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 1:
        return 1e10
    n = len(r)
    sigma2 = np.zeros(n)
    sigma2[0] = np.var(r)
    for t in range(1, n):
        sigma2[t] = omega + alpha * r[t - 1] ** 2 + beta * sigma2[t - 1]
    sigma2 = np.clip(sigma2, 1e-12, None)
    nll = 0.5 * np.sum(np.log(2 * np.pi * sigma2) + (r ** 2) / sigma2)
    return float(nll)


def garch_fit(params):
    """
    params:
      returns: list[float]   -- REQUERIDO. serie de retornos (ya diferenciada
                                 / log-retornos, no precios en nivel)
      n_forecast: int         -- pasos de varianza a pronosticar, default 5
    """
    _require_scipy()
    returns = params.get("returns")
    if returns is None:
        raise ValueError("Falta 'returns' (serie de retornos, no precios en nivel).")
    r = _as_array(returns, "returns")
    r = r - np.mean(r)
    n = len(r)
    if n < 30:
        raise ValueError("Se recomiendan al menos 30 observaciones para GARCH(1,1).")

    n_forecast = int(params.get("n_forecast", 5))

    theta0 = np.array([np.var(r) * 0.1, 0.05, 0.90])
    bounds = [(1e-8, None), (0, 1), (0, 1)]
    res = _sp_optimize.minimize(
        _garch11_neg_log_likelihood, theta0, args=(r,),
        method="L-BFGS-B", bounds=bounds,
    )
    omega, alpha, beta = res.x

    sigma2 = np.zeros(n)
    sigma2[0] = np.var(r)
    for t in range(1, n):
        sigma2[t] = omega + alpha * r[t - 1] ** 2 + beta * sigma2[t - 1]

    forecast = []
    last_sigma2 = sigma2[-1]
    last_r2 = r[-1] ** 2
    for h in range(n_forecast):
        if h == 0:
            s2 = omega + alpha * last_r2 + beta * last_sigma2
        else:
            s2 = omega + (alpha + beta) * forecast[-1]
        forecast.append(float(s2))

    unconditional_var = omega / (1 - alpha - beta) if (alpha + beta) < 1 else float("nan")

    return {
        "method": "GARCH(1,1) via MLE (normal)",
        "converged": bool(res.success),
        "omega": float(omega),
        "alpha": float(alpha),
        "beta": float(beta),
        "persistence_alpha_plus_beta": float(alpha + beta),
        "unconditional_variance": float(unconditional_var),
        "conditional_variance_series": sigma2.tolist(),
        "n_forecast": n_forecast,
        "variance_forecast": forecast,
        "note": ("alpha+beta cercano a 1 indica alta persistencia de volatilidad "
                 "(clustering). Si alpha+beta >= 1 el proceso no es estacionario "
                 "en varianza (IGARCH)."),
    }


# ---------------------------------------------------------------------------
# Engle-Granger cointegration (2 pasos)
# ---------------------------------------------------------------------------

_EG_CRITICAL_VALUES = {"1%": -3.90, "5%": -3.34, "10%": -3.04}


def engle_granger_coint(params):
    """
    params:
      y: list[float]   -- REQUERIDO. serie dependiente
      x: list[float]   -- REQUERIDO. serie independiente (misma longitud)
      n_lags: int        -- lags para el ADF del residuo, default: auto
    """
    y_series = params.get("y")
    x_series = params.get("x")
    if y_series is None or x_series is None:
        raise ValueError("Faltan 'y' y/o 'x'.")
    y = _as_array(y_series, "y")
    x = _as_array(x_series, "x")
    if len(y) != len(x):
        raise ValueError("'y' y 'x' deben tener la misma longitud.")

    X = np.column_stack([np.ones(len(x)), x])
    step1 = _ols(X, y)
    b = float(step1["coef"][1])
    residuals = step1["resid"]

    adf_res = adf_test({"series": residuals.tolist(),
                         "n_lags": params.get("n_lags")})
    adf_stat = adf_res["adf_statistic"]

    if adf_stat < _EG_CRITICAL_VALUES["1%"]:
        conclusion = "Rechaza H0 al 1%: las series estan cointegradas."
    elif adf_stat < _EG_CRITICAL_VALUES["5%"]:
        conclusion = "Rechaza H0 al 5%: las series estan cointegradas."
    elif adf_stat < _EG_CRITICAL_VALUES["10%"]:
        conclusion = "Rechaza H0 al 10%: evidencia debil de cointegracion."
    else:
        conclusion = "No rechaza H0: no hay evidencia de cointegracion."

    return {
        "test": "Engle-Granger (2 pasos)",
        "cointegrating_coefficient": b,
        "intercept": float(step1["coef"][0]),
        "residual_adf_statistic": adf_stat,
        "critical_values_engle_granger": _EG_CRITICAL_VALUES,
        "conclusion": conclusion,
        "residuals": residuals.tolist(),
        "note": ("Paso 1: OLS de y sobre x. Paso 2: ADF sobre los residuos, "
                 "comparado contra valores criticos de Engle-Granger (mas "
                 "estrictos que ADF estandar). Si estan cointegradas, un "
                 "modelo VECM captura la dinamica de corto plazo -- no "
                 "implementado aqui, se puede agregar como extension."),
    }


# ---------------------------------------------------------------------------
# Panel de efectos fijos (within estimator)
# ---------------------------------------------------------------------------

def panel_fixed_effects(params):
    """
    params:
      y: list[float]           -- REQUERIDO. variable dependiente, apilada
      X: list[list[float]]     -- REQUERIDO. regresores, apilados (sin
                                    constante -- se remueve por demeaning)
      entity_ids: list         -- REQUERIDO. identificador de entidad/panel
                                    por observacion (mismo largo que y)
      var_names: list[str]     -- opcional, nombres de columnas de X
    """
    y_in = params.get("y")
    X_in = params.get("X")
    entity_ids = params.get("entity_ids")
    if y_in is None or X_in is None or entity_ids is None:
        raise ValueError("Faltan 'y', 'X' y/o 'entity_ids'.")

    y = _as_array(y_in, "y")
    X = _as_array(X_in, "X")
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    entity_ids = np.asarray(entity_ids)
    var_names = params.get("var_names", [f"x{i+1}" for i in range(X.shape[1])])

    if len(y) != X.shape[0] or len(y) != len(entity_ids):
        raise ValueError("'y', 'X' y 'entity_ids' deben tener el mismo numero de filas.")

    y_demeaned = y.copy()
    X_demeaned = X.copy()
    for entity in np.unique(entity_ids):
        mask = entity_ids == entity
        y_demeaned[mask] = y[mask] - y[mask].mean()
        X_demeaned[mask] = X[mask] - X[mask].mean(axis=0)

    fit = _ols(X_demeaned, y_demeaned)
    n_entities = len(np.unique(entity_ids))
    n_obs = len(y)

    coef_dict = {name: float(c) for name, c in zip(var_names, fit["coef"])}
    se_dict = {name: float(s) for name, s in zip(var_names, fit["se"])}
    t_stats = {name: float(c / s) if s > 0 else float("nan")
               for name, c, s in zip(var_names, fit["coef"], fit["se"])}

    ss_res = float(fit["resid"] @ fit["resid"])
    ss_tot = float(np.sum((y_demeaned - y_demeaned.mean()) ** 2))
    r2_within = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    return {
        "method": "Panel de efectos fijos (within estimator)",
        "n_entities": n_entities,
        "n_obs": n_obs,
        "coefficients": coef_dict,
        "std_errors": se_dict,
        "t_stats": t_stats,
        "r2_within": r2_within,
        "note": ("Efectos fijos por entidad removidos via demeaning (within "
                 "transformation). Errores estandar NO robustos a "
                 "heterocedasticidad ni clustered -- extension posible si "
                 "hace falta inferencia mas fina."),
    }


# ---------------------------------------------------------------------------
# IV / 2SLS
# ---------------------------------------------------------------------------

def iv_2sls(params):
    """
    params:
      y: list[float]                -- REQUERIDO. variable dependiente
      endog: list[float]             -- REQUERIDO. regresor endogeno (1 var)
      instruments: list[list[float]] -- REQUERIDO. instrumentos (>=1 columna)
      exog: list[list[float]]        -- opcional. regresores exogenos adicionales
    """
    y_in = params.get("y")
    endog_in = params.get("endog")
    instruments_in = params.get("instruments")
    if y_in is None or endog_in is None or instruments_in is None:
        raise ValueError("Faltan 'y', 'endog' y/o 'instruments'.")

    y = _as_array(y_in, "y")
    endog = _as_array(endog_in, "endog").reshape(-1, 1)
    Z = _as_array(instruments_in, "instruments")
    if Z.ndim == 1:
        Z = Z.reshape(-1, 1)

    exog_in = params.get("exog")
    if exog_in is not None:
        exog = _as_array(exog_in, "exog")
        if exog.ndim == 1:
            exog = exog.reshape(-1, 1)
    else:
        exog = np.zeros((len(y), 0))

    n = len(y)
    const = np.ones((n, 1))

    Z_full = np.column_stack([const, Z, exog])
    stage1 = _ols(Z_full, endog.ravel())
    endog_hat = stage1["y_hat"]

    X_stage2 = np.column_stack([const, endog_hat.reshape(-1, 1), exog])
    stage2 = _ols(X_stage2, y)

    var_names = ["const", "endog_instrumented"] + \
                [f"exog{i+1}" for i in range(exog.shape[1])]
    coef_dict = {name: float(c) for name, c in zip(var_names, stage2["coef"])}
    se_dict = {name: float(s) for name, s in zip(var_names, stage2["se"])}

    ss_tot_1 = float(np.sum((endog.ravel() - endog.mean()) ** 2))
    ss_res_1 = float(stage1["resid"] @ stage1["resid"])
    r2_stage1 = 1 - ss_res_1 / ss_tot_1 if ss_tot_1 > 0 else float("nan")
    k_instruments = Z.shape[1]
    dof1, dof2 = k_instruments, stage1["dof"]
    f_stat_stage1 = ((ss_tot_1 - ss_res_1) / dof1) / (ss_res_1 / dof2) if ss_res_1 > 0 else float("inf")

    weak_instrument_warning = None
    if f_stat_stage1 < 10:
        weak_instrument_warning = (
            "F-stat de primera etapa < 10: posible problema de instrumento "
            "debil (regla practica de Staiger-Stock)."
        )

    return {
        "method": "IV / 2SLS (dos etapas)",
        "coefficients": coef_dict,
        "std_errors": se_dict,
        "stage1_r2": r2_stage1,
        "stage1_f_stat": float(f_stat_stage1),
        "weak_instrument_warning": weak_instrument_warning,
        "note": ("Errores estandar de la etapa 2 calculados sobre el modelo "
                 "de segunda etapa directamente -- para inferencia exacta "
                 "conviene corregir por el hecho de que 'endog_instrumented' "
                 "es un valor estimado (correccion de varianza 2SLS "
                 "completa). Aqui se da una aproximacion util para "
                 "diagnostico rapido."),
    }


# ---------------------------------------------------------------------------
# Granger causality (F-test sobre VAR)
# ---------------------------------------------------------------------------

def granger_causality(params):
    """
    Testea si 'x' Granger-causa 'y': H0 = los rezagos de x no ayudan a
    predecir y, una vez controlado por los rezagos de y mismo.

    params:
      y: list[float]   -- REQUERIDO. serie a explicar
      x: list[float]   -- REQUERIDO. serie candidata a causa
      n_lags: int        -- default 2
    """
    _require_scipy()
    y_in = params.get("y")
    x_in = params.get("x")
    if y_in is None or x_in is None:
        raise ValueError("Faltan 'y' y/o 'x'.")
    y = _as_array(y_in, "y")
    x = _as_array(x_in, "x")
    if len(y) != len(x):
        raise ValueError("'y' y 'x' deben tener la misma longitud.")

    n_lags = int(params.get("n_lags", 2))
    n = len(y)
    if n < (4 * n_lags + 10):
        raise ValueError("Serie muy corta para el numero de lags solicitado.")

    y_current, y_lagged = _lag_matrix(y, n_lags)
    _, x_lagged = _lag_matrix(x, n_lags)

    X_restricted = np.column_stack([np.ones(len(y_current)), y_lagged])
    fit_restricted = _ols(X_restricted, y_current)
    rss_restricted = float(fit_restricted["resid"] @ fit_restricted["resid"])

    X_unrestricted = np.column_stack([np.ones(len(y_current)), y_lagged, x_lagged])
    fit_unrestricted = _ols(X_unrestricted, y_current)
    rss_unrestricted = float(fit_unrestricted["resid"] @ fit_unrestricted["resid"])

    n_obs = len(y_current)
    k_unrestricted = X_unrestricted.shape[1]
    dof1 = n_lags
    dof2 = n_obs - k_unrestricted

    if rss_unrestricted <= 0 or dof2 <= 0:
        raise ValueError("Datos insuficientes o degenerados para el F-test.")

    f_stat = ((rss_restricted - rss_unrestricted) / dof1) / (rss_unrestricted / dof2)
    f_stat = max(f_stat, 0.0)
    p_value = float(1 - _sp_stats.f.cdf(f_stat, dof1, dof2))

    if p_value < 0.01:
        conclusion = "Rechaza H0 al 1%: x Granger-causa a y."
    elif p_value < 0.05:
        conclusion = "Rechaza H0 al 5%: x Granger-causa a y."
    elif p_value < 0.10:
        conclusion = "Rechaza H0 al 10%: evidencia debil de causalidad de Granger."
    else:
        conclusion = "No rechaza H0: no hay evidencia de que x Granger-causa a y."

    return {
        "test": "Granger causality (F-test sobre VAR)",
        "direction": "x -> y",
        "n_lags": n_lags,
        "f_statistic": float(f_stat),
        "p_value": p_value,
        "dof": [dof1, dof2],
        "conclusion": conclusion,
        "note": ("Recordar que 'Granger-causalidad' es sobre capacidad "
                 "predictiva, no causalidad estructural. Correr tambien "
                 "granger_causality con y/x invertidos para chequear "
                 "causalidad bidireccional."),
    }


# ---------------------------------------------------------------------------
# Dispatcher del modulo
# ---------------------------------------------------------------------------

def compute_econometrics(mode, params=None):
    params = params or {}
    dispatch = {
        "adf_test": adf_test,
        "arima_forecast": arima_forecast,
        "garch_fit": garch_fit,
        "engle_granger_coint": engle_granger_coint,
        "panel_fixed_effects": panel_fixed_effects,
        "iv_2sls": iv_2sls,
        "granger_causality": granger_causality,
    }
    if mode not in dispatch:
        raise ValueError(
            f"Modo desconocido: '{mode}'. Modos validos: {list(dispatch.keys())}"
        )
    return dispatch[mode](params)


# ---------------------------------------------------------------------------
# Schema JSONRPC
# ---------------------------------------------------------------------------

ECONOMETRICS_TOOL_SCHEMA = {
    "name": "econometrics_tool",
    "description": (
        "Econometria: series temporales (ARIMA/GARCH), cointegracion "
        "(Engle-Granger, ADF), modelos de panel (efectos fijos), variables "
        "instrumentales (2SLS), causalidad de Granger. Modos disponibles: "
        "adf_test, arima_forecast, garch_fit, engle_granger_coint, "
        "panel_fixed_effects, iv_2sls, granger_causality. Complementa "
        "statistics_tool y cross_validation_tool (usar particionado "
        "walk-forward para series temporales, no k-fold random)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "adf_test", "arima_forecast", "garch_fit",
                    "engle_granger_coint", "panel_fixed_effects",
                    "iv_2sls", "granger_causality",
                ],
            },
            "params": {
                "type": "object",
                "description": "Parametros especificos de cada modo, ver docstrings.",
            },
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------------------
# Autotest (correr con: python3 econometrics_tool.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    rng = np.random.default_rng(42)

    print("== Test adf_test (serie no estacionaria: random walk) ==")
    random_walk = np.cumsum(rng.normal(0, 1, 100))
    adf_res = compute_econometrics("adf_test", {"series": random_walk.tolist()})
    print("adf_stat:", round(adf_res["adf_statistic"], 4), "->", adf_res["conclusion"])

    print("\n== Test adf_test (serie estacionaria: ruido blanco) ==")
    white_noise = rng.normal(0, 1, 100)
    adf_res2 = compute_econometrics("adf_test", {"series": white_noise.tolist()})
    print("adf_stat:", round(adf_res2["adf_statistic"], 4), "->", adf_res2["conclusion"])

    print("\n== Test arima_forecast (AR(1) simulado) ==")
    ar1 = [0.0]
    for _ in range(150):
        ar1.append(0.7 * ar1[-1] + rng.normal(0, 1))
    arima_res = compute_econometrics("arima_forecast", {
        "series": ar1, "p": 1, "d": 0, "q": 0, "n_forecast": 5,
    })
    print("ar_coef (esperado ~0.7):", round(arima_res["ar_coefficients"][0], 3))
    print("forecast:", [round(v, 3) for v in arima_res["forecast"]])

    print("\n== Test garch_fit (retornos simulados con volatility clustering) ==")
    n = 300
    sigma2 = np.zeros(n)
    r = np.zeros(n)
    sigma2[0] = 1.0
    for t in range(1, n):
        sigma2[t] = 0.05 + 0.1 * r[t - 1] ** 2 + 0.85 * sigma2[t - 1]
        r[t] = rng.normal(0, np.sqrt(sigma2[t]))
    garch_res = compute_econometrics("garch_fit", {"returns": r.tolist(), "n_forecast": 3})
    print("alpha+beta (esperado ~0.95):",
          round(garch_res["persistence_alpha_plus_beta"], 3))

    print("\n== Test engle_granger_coint (series cointegradas por construccion) ==")
    x_series = np.cumsum(rng.normal(0, 1, 100))
    y_series = 2.0 * x_series + rng.normal(0, 0.5, 100)
    eg_res = compute_econometrics("engle_granger_coint", {
        "y": y_series.tolist(), "x": x_series.tolist(),
    })
    print("coef (esperado ~2.0):", round(eg_res["cointegrating_coefficient"], 3))
    print("adf_stat residuo:", round(eg_res["residual_adf_statistic"], 3),
          "(vs critico 5%:", eg_res["critical_values_engle_granger"]["5%"], ")")
    print("conclusion:", eg_res["conclusion"])
    print("(nota: con n=100 el test puede quedar justo al limite de poder "
          "estadistico -- con mas muestras detecta la cointegracion sin "
          "ambiguedad, ver mas abajo)")

    x_series_big = np.cumsum(rng.normal(0, 1, 500))
    y_series_big = 2.0 * x_series_big + rng.normal(0, 0.5, 500)
    eg_res_big = compute_econometrics("engle_granger_coint", {
        "y": y_series_big.tolist(), "x": x_series_big.tolist(),
    })
    print("con n=500 -> adf_stat:", round(eg_res_big["residual_adf_statistic"], 3),
          "->", eg_res_big["conclusion"])

    print("\n== Test panel_fixed_effects ==")
    n_entities, n_periods = 5, 20
    entity_ids = []
    X_panel, y_panel = [], []
    for e in range(n_entities):
        fe = rng.normal(0, 2)
        for t in range(n_periods):
            xi = rng.normal(0, 1)
            yi = fe + 1.5 * xi + rng.normal(0, 0.3)
            entity_ids.append(e)
            X_panel.append([xi])
            y_panel.append(yi)
    panel_res = compute_econometrics("panel_fixed_effects", {
        "y": y_panel, "X": X_panel, "entity_ids": entity_ids,
    })
    print("coef x1 (esperado ~1.5):", round(panel_res["coefficients"]["x1"], 3))

    print("\n== Test iv_2sls ==")
    z_instrument = rng.normal(0, 1, 200)
    endog_var = 0.8 * z_instrument + rng.normal(0, 0.5, 200)
    y_iv = 3.0 * endog_var + rng.normal(0, 0.3, 200)
    iv_res = compute_econometrics("iv_2sls", {
        "y": y_iv.tolist(), "endog": endog_var.tolist(),
        "instruments": z_instrument.reshape(-1, 1).tolist(),
    })
    print("coef endog (esperado ~3.0):",
          round(iv_res["coefficients"]["endog_instrumented"], 3))
    print("stage1_f_stat:", round(iv_res["stage1_f_stat"], 1))

    print("\n== Test granger_causality (x causa a y por construccion) ==")
    x_gc = rng.normal(0, 1, 150)
    y_gc = np.zeros(150)
    for t in range(2, 150):
        y_gc[t] = 0.5 * y_gc[t - 1] + 0.6 * x_gc[t - 2] + rng.normal(0, 0.3)
    gc_res = compute_econometrics("granger_causality", {
        "y": y_gc.tolist(), "x": x_gc.tolist(), "n_lags": 2,
    })
    print("f_stat:", round(gc_res["f_statistic"], 3),
          "p_value:", round(gc_res["p_value"], 5))
    print("conclusion:", gc_res["conclusion"])

    print("\nOK - todos los tests corrieron sin excepciones.")
