"""
bacterial_growth_tool.py

Curvas de crecimiento bacteriano: modelo de Baranyi-Roberts (1994) y modelo
de Gompertz modificado (parametrizacion de Zwietering et al. 1990), ambos
estandar en microbiologia predictiva. Incluye ajuste (fit) de datos
experimentales (t, log N) contra Gompertz via minimos cuadrados no lineales.

Baranyi-Roberts:
    dy/dt = mu_max * alpha(t) * (1 - exp(y - y_max))
    alpha(t) = q(t) / (q(t) + 1),   dq/dt = mu_max * q
    y = ln(N/N0)
Integrado numericamente (RK4). h0 = ln(1 + 1/q0) controla el lag.

Gompertz modificado (Zwietering):
    y(t) = A * exp( -exp( (mu_max*e/A)*(lambda - t) + 1 ) )
    A = ln(Nmax/N0), mu_max = tasa max especifica, lambda = duracion del lag

Modos:
  - baranyi_roberts: simula la curva dado mu_max, y0, y_max, h0, t_max.
  - gompertz: simula la curva modificada de Gompertz dado A, mu_max, lambda.
  - fit_growth_curve: ajusta Gompertz modificado a datos (t, log N) via
    scipy.optimize.curve_fit, devuelve parametros + R^2.
  - validate: ambos modelos deben converger a la misma asintota (y_max/A)
    para t grande, dado un caso con parametros equivalentes.
"""

import numpy as np
from scipy.optimize import curve_fit


def _baranyi_rhs(y, q, mu_max, y_max):
    alpha = q / (q + 1.0)
    dydt = mu_max * alpha * (1.0 - np.exp(y - y_max))
    dqdt = mu_max * q
    return dydt, dqdt


def _baranyi_roberts(mu_max, y0, y_max, h0, t_max, n_points=200):
    q0 = 1.0 / (np.exp(h0) - 1.0) if h0 > 0 else 1e6
    dt = t_max / (n_points - 1)
    t = np.linspace(0, t_max, n_points)
    y = np.zeros(n_points)
    q = np.zeros(n_points)
    y[0], q[0] = y0, q0
    for i in range(n_points - 1):
        k1y, k1q = _baranyi_rhs(y[i], q[i], mu_max, y_max)
        k2y, k2q = _baranyi_rhs(y[i] + dt / 2 * k1y, q[i] + dt / 2 * k1q, mu_max, y_max)
        k3y, k3q = _baranyi_rhs(y[i] + dt / 2 * k2y, q[i] + dt / 2 * k2q, mu_max, y_max)
        k4y, k4q = _baranyi_rhs(y[i] + dt * k3y, q[i] + dt * k3q, mu_max, y_max)
        y[i + 1] = y[i] + dt / 6 * (k1y + 2 * k2y + 2 * k3y + k4y)
        q[i + 1] = q[i] + dt / 6 * (k1q + 2 * k2q + 2 * k3q + k4q)
    lag_time = float(np.log(1.0 + 1.0 / q0) / mu_max) if mu_max > 0 else None
    return {
        "mode": "baranyi_roberts",
        "params": {"mu_max": mu_max, "y0": y0, "y_max": y_max, "h0": h0, "t_max": t_max},
        "t": t.tolist(),
        "y_ln_N_N0": y.tolist(),
        "estimated_lag_time": lag_time,
        "final_y": float(y[-1]),
    }


def _gompertz_curve(t, A, mu_max, lam):
    return A * np.exp(-np.exp((mu_max * np.e / A) * (lam - t) + 1.0))


def _gompertz(A, mu_max, lam, t_max, n_points=200):
    t = np.linspace(0, t_max, n_points)
    y = _gompertz_curve(t, A, mu_max, lam)
    return {
        "mode": "gompertz",
        "params": {"A": A, "mu_max": mu_max, "lambda_lag": lam, "t_max": t_max},
        "t": t.tolist(),
        "y_ln_N_N0": y.tolist(),
        "final_y": float(y[-1]),
    }


def _fit_growth_curve(t_data, log_n_data):
    t_data = np.asarray(t_data, dtype=float)
    y_data = np.asarray(log_n_data, dtype=float)
    A0 = float(np.max(y_data) - np.min(y_data))
    mu0 = float(np.max(np.gradient(y_data, t_data))) if len(t_data) > 1 else 0.1
    lam0 = float(t_data[len(t_data) // 4])
    p0 = [max(A0, 1e-3), max(mu0, 1e-3), max(lam0, 0.0)]
    try:
        popt, pcov = curve_fit(_gompertz_curve, t_data, y_data, p0=p0, maxfev=10000)
    except RuntimeError as e:
        return {"mode": "fit_growth_curve", "converged": False, "error": str(e)}
    A_fit, mu_fit, lam_fit = popt
    y_pred = _gompertz_curve(t_data, *popt)
    ss_res = float(np.sum((y_data - y_pred) ** 2))
    ss_tot = float(np.sum((y_data - np.mean(y_data)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else None
    return {
        "mode": "fit_growth_curve",
        "converged": True,
        "A_fit": float(A_fit),
        "mu_max_fit": float(mu_fit),
        "lambda_lag_fit": float(lam_fit),
        "r_squared": r2,
        "fitted_values": y_pred.tolist(),
    }


def _validate():
    baranyi = _baranyi_roberts(mu_max=0.5, y0=0.0, y_max=8.0, h0=2.0, t_max=30.0)
    gompertz = _gompertz(A=8.0, mu_max=0.5, lam=4.0, t_max=30.0)
    baranyi_final = baranyi["final_y"]
    gompertz_final = gompertz["final_y"]
    both_near_asymptote = abs(baranyi_final - 8.0) < 0.5 and abs(gompertz_final - 8.0) < 0.5

    # test de fit: generar datos sinteticos desde Gompertz conocido + ruido chico, refitear
    t_synth = np.linspace(0, 30, 30)
    y_synth = _gompertz_curve(t_synth, A=8.0, mu_max=0.5, lam=4.0) + np.random.RandomState(0).normal(0, 0.05, 30)
    fit_result = _fit_growth_curve(t_synth.tolist(), y_synth.tolist())
    fit_ok = fit_result.get("converged") and fit_result.get("r_squared", 0) > 0.9

    return {
        "mode": "validate",
        "baranyi_final_y": baranyi_final,
        "gompertz_final_y": gompertz_final,
        "fit_r_squared": fit_result.get("r_squared"),
        "expected": "ambos modelos convergen a y~=8 (asintota); el fit sobre datos sinteticos recupera R2>0.9",
        "validation_passed": bool(both_near_asymptote and fit_ok),
    }


def compute_bacterial_growth_tool(mode, **kwargs):
    if mode == "baranyi_roberts":
        return _baranyi_roberts(
            kwargs["mu_max"], kwargs["y0"], kwargs["y_max"], kwargs["h0"], kwargs["t_max"],
            n_points=kwargs.get("n_points", 200),
        )
    elif mode == "gompertz":
        return _gompertz(
            kwargs["A"], kwargs["mu_max"], kwargs["lambda_lag"], kwargs["t_max"],
            n_points=kwargs.get("n_points", 200),
        )
    elif mode == "fit_growth_curve":
        return _fit_growth_curve(kwargs["t_data"], kwargs["log_n_data"])
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"mode desconocido: {mode}")


BACTERIAL_GROWTH_TOOL_SCHEMA = {
    "name": "bacterial_growth_tool",
    "description": (
        "Curvas de crecimiento bacteriano via modelo de Baranyi-Roberts (RK4 sobre el sistema "
        "y/q) y modelo de Gompertz modificado (Zwietering et al. 1990), mas ajuste no lineal de "
        "Gompertz a datos experimentales (t, log N). mode='baranyi_roberts' (mu_max, y0, y_max, "
        "h0, t_max); mode='gompertz' (A, mu_max, lambda_lag, t_max); mode='fit_growth_curve' "
        "(t_data, log_n_data); mode='validate' corre ambos modelos y un fit sintetico."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["baranyi_roberts", "gompertz", "fit_growth_curve", "validate"],
                "default": "validate",
            },
            "mu_max": {"type": "number", "description": "Tasa especifica maxima de crecimiento. baranyi_roberts, gompertz."},
            "y0": {"type": "number", "description": "ln(N0/N0)=0 tipicamente. baranyi_roberts."},
            "y_max": {"type": "number", "description": "ln(Nmax/N0). baranyi_roberts."},
            "h0": {"type": "number", "description": "Parametro de historia fisiologica (controla el lag). baranyi_roberts."},
            "t_max": {"type": "number", "description": "Tiempo final de simulacion. baranyi_roberts, gompertz."},
            "n_points": {"type": "integer", "default": 200},
            "A": {"type": "number", "description": "Asintota ln(Nmax/N0). gompertz."},
            "lambda_lag": {"type": "number", "description": "Duracion del lag. gompertz."},
            "t_data": {"type": "array", "items": {"type": "number"}, "description": "Tiempos experimentales. fit_growth_curve."},
            "log_n_data": {"type": "array", "items": {"type": "number"}, "description": "ln(N/N0) experimental. fit_growth_curve."},
        },
        "required": ["mode"],
    },
}

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("bacterial_growth_tool", BACTERIAL_GROWTH_TOOL_SCHEMA, lambda args, _f=compute_bacterial_growth_tool: _f(**args))
