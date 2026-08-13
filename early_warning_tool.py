"""
early_warning_tool.py

Analisis de series temporales para sistemas de alerta temprana (inundaciones,
sequias) en gestion publica: deteccion de cruce de umbrales, tendencias, y
tasa de cambio para anticipar situaciones criticas.

Modos:
  - threshold_crossing: detecta cruces de uno o mas umbrales en una serie
                (con niveles de alerta tipo semaforo), y estima el tiempo
                hasta cruzar el umbral si la tendencia reciente continua
                (extrapolacion lineal simple)
  - trend_analysis: regresion lineal simple sobre una serie (pendiente,
                intercepto, R2) para cuantificar tendencia (ej. nivel de
                un rio o volumen de un embalse a lo largo del tiempo)
  - rate_of_change_alert: tasa de cambio (diferencias finitas) entre pasos
                consecutivos, con deteccion de eventos que superan una tasa
                critica (ej. subida rapida de nivel de rio)
  - moving_average_anomaly: media movil + desviacion, marca puntos que se
                alejan mas de k desviaciones estandar de la media movil local
                (deteccion simple de anomalias para alerta)
"""

import numpy as np


def _mode_threshold_crossing(p):
    series = np.asarray(p["series"], dtype=float)
    times = np.asarray(p.get("times", np.arange(len(series))), dtype=float)
    thresholds = p["thresholds"]  # dict label -> valor, ej {"amarillo": 3.0, "naranja": 4.5, "rojo": 6.0}

    n = len(series)
    crossings = {}
    for label, thr in thresholds.items():
        thr = float(thr)
        idx_above = np.where(series >= thr)[0]
        first_idx = int(idx_above[0]) if len(idx_above) > 0 else None
        crossings[label] = {
            "threshold": thr,
            "first_crossing_index": first_idx,
            "first_crossing_time": float(times[first_idx]) if first_idx is not None else None,
            "currently_above": bool(series[-1] >= thr),
        }

    # nivel de alerta actual: el umbral mas alto que el ultimo valor supera
    current_value = float(series[-1])
    sorted_thr = sorted(thresholds.items(), key=lambda kv: kv[1])
    current_level = "normal"
    for label, thr in sorted_thr:
        if current_value >= thr:
            current_level = label

    # extrapolacion lineal simple con los ultimos k puntos, para estimar tiempo
    # hasta cruzar el proximo umbral no superado (si la tendencia es creciente)
    k = min(5, n)
    if n >= 2:
        t_recent = times[-k:]
        s_recent = series[-k:]
        slope, intercept = np.polyfit(t_recent, s_recent, 1)
    else:
        slope, intercept = 0.0, current_value

    eta = {}
    if slope > 0:
        for label, thr in sorted_thr:
            if current_value < thr:
                t_cross = (thr - intercept) / slope
                dt_ahead = t_cross - times[-1]
                eta[label] = round(float(dt_ahead), 4) if dt_ahead > 0 else 0.0
            else:
                eta[label] = 0.0
    else:
        for label, _ in sorted_thr:
            eta[label] = None  # tendencia no creciente, no se proyecta cruce

    return {
        "current_value": current_value,
        "current_alert_level": current_level,
        "crossings": crossings,
        "recent_trend_slope": round(float(slope), 6),
        "estimated_time_to_threshold": eta,
    }


def _mode_trend_analysis(p):
    series = np.asarray(p["series"], dtype=float)
    times = np.asarray(p.get("times", np.arange(len(series))), dtype=float)

    n = len(series)
    if n < 2:
        raise ValueError("Se necesitan al menos 2 puntos para trend_analysis")

    slope, intercept = np.polyfit(times, series, 1)
    pred = slope * times + intercept
    ss_res = float(np.sum((series - pred) ** 2))
    ss_tot = float(np.sum((series - np.mean(series)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0

    direction = "creciente" if slope > 1e-9 else ("decreciente" if slope < -1e-9 else "estable")

    return {
        "n_points": n,
        "slope": round(float(slope), 6),
        "intercept": round(float(intercept), 6),
        "r_squared": round(float(r2), 6),
        "trend_direction": direction,
        "predicted_at_last_time": round(float(pred[-1]), 6),
    }


def _mode_rate_of_change_alert(p):
    series = np.asarray(p["series"], dtype=float)
    times = np.asarray(p.get("times", np.arange(len(series))), dtype=float)
    critical_rate = float(p["critical_rate"])  # unidades de serie por unidad de tiempo

    dt = np.diff(times)
    if np.any(dt == 0):
        raise ValueError("times no puede tener pasos repetidos (dt=0)")

    rate = np.diff(series) / dt  # tasa de cambio entre pasos consecutivos

    alert_mask = np.abs(rate) >= critical_rate
    alert_indices = [int(i) for i in np.where(alert_mask)[0]]

    return {
        "critical_rate": critical_rate,
        "rate_of_change": np.round(rate, 6).tolist(),
        "max_abs_rate": round(float(np.max(np.abs(rate))), 6) if len(rate) > 0 else 0.0,
        "alert_indices": alert_indices,
        "n_alerts": len(alert_indices),
        "any_alert": bool(len(alert_indices) > 0),
    }


def _mode_moving_average_anomaly(p):
    series = np.asarray(p["series"], dtype=float)
    window = int(p.get("window", 5))
    k = float(p.get("k_std", 2.0))

    n = len(series)
    if window < 1 or window >= n:
        raise ValueError("window debe estar entre 1 y len(series)-1")

    ma = np.full(n, np.nan)
    std = np.full(n, np.nan)
    anomaly = np.zeros(n, dtype=bool)

    # ventana TRAILING que excluye el punto actual: evita que un pico infle
    # su propia media/desvio y quede escondido
    for i in range(window, n):
        seg = series[i - window:i]
        ma[i] = np.mean(seg)
        std[i] = np.std(seg, ddof=0)
        if std[i] > 0:
            anomaly[i] = abs(series[i] - ma[i]) > k * std[i]
        else:
            # ventana de referencia perfectamente constante: cualquier
            # desviacion del valor actual respecto de ese nivel es anomala
            anomaly[i] = bool(series[i] != ma[i])

    anomaly_indices = [int(i) for i in np.where(anomaly)[0]]

    return {
        "window": window, "k_std": k,
        "moving_average": [None if np.isnan(x) else round(float(x), 6) for x in ma],
        "moving_std": [None if np.isnan(x) else round(float(x), 6) for x in std],
        "anomaly_flags": anomaly.tolist(),
        "anomaly_indices": anomaly_indices,
        "n_anomalies": len(anomaly_indices),
    }


def _validate():
    checks = []

    # --- Check 1: threshold_crossing, caso construido a mano donde se sabe
    # exactamente en que indice cruza cada umbral
    series1 = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]  # sube de a 1
    tc = _mode_threshold_crossing({
        "series": series1, "thresholds": {"amarillo": 3.0, "naranja": 5.0, "rojo": 7.0}
    })
    checks.append({
        "name": "threshold_crossing_known_indices",
        "amarillo_idx": tc["crossings"]["amarillo"]["first_crossing_index"],
        "naranja_idx": tc["crossings"]["naranja"]["first_crossing_index"],
        "rojo_idx": tc["crossings"]["rojo"]["first_crossing_index"],
        "current_level": tc["current_alert_level"],
        "passed": bool(tc["crossings"]["amarillo"]["first_crossing_index"] == 2
                  and tc["crossings"]["naranja"]["first_crossing_index"] == 4
                  and tc["crossings"]["rojo"]["first_crossing_index"] == 6
                  and tc["current_alert_level"] == "rojo"),
    })

    # --- Check 2: threshold_crossing, serie que nunca cruza -- first_crossing
    # debe ser None y currently_above False
    tc2 = _mode_threshold_crossing({
        "series": [1.0, 1.5, 1.2, 1.8], "thresholds": {"rojo": 10.0}
    })
    checks.append({
        "name": "threshold_crossing_never_crosses",
        "first_crossing": tc2["crossings"]["rojo"]["first_crossing_index"],
        "currently_above": tc2["crossings"]["rojo"]["currently_above"],
        "passed": bool(tc2["crossings"]["rojo"]["first_crossing_index"] is None
                  and tc2["crossings"]["rojo"]["currently_above"] is False),
    })

    # --- Check 3: trend_analysis, recta perfecta y = 2x + 1 -> slope=2,
    # intercept=1, R2=1.0 exactos (sin ruido)
    t = np.arange(20)
    y = 2.0 * t + 1.0
    ta = _mode_trend_analysis({"series": y.tolist(), "times": t.tolist()})
    checks.append({
        "name": "trend_analysis_perfect_line",
        "slope": ta["slope"], "intercept": ta["intercept"], "r2": ta["r_squared"],
        "passed": bool(abs(ta["slope"] - 2.0) < 1e-9 and abs(ta["intercept"] - 1.0) < 1e-9
                  and abs(ta["r_squared"] - 1.0) < 1e-9),
    })

    # --- Check 4: trend_analysis, serie constante -> slope=0, direction="estable"
    ta2 = _mode_trend_analysis({"series": [5.0] * 10})
    checks.append({
        "name": "trend_analysis_constant_series",
        "slope": ta2["slope"], "direction": ta2["trend_direction"],
        "passed": bool(abs(ta2["slope"]) < 1e-9 and ta2["trend_direction"] == "estable"),
    })

    # --- Check 5: rate_of_change_alert, tasa constante conocida (serie lineal
    # con paso dt=1, pendiente 3) -> todas las tasas deben dar exactamente 3.0
    series5 = [0.0, 3.0, 6.0, 9.0, 12.0]
    roc = _mode_rate_of_change_alert({"series": series5, "critical_rate": 2.5})
    checks.append({
        "name": "rate_of_change_constant_slope",
        "rates": roc["rate_of_change"],
        "passed": bool(all(abs(r - 3.0) < 1e-9 for r in roc["rate_of_change"])
                  and roc["n_alerts"] == 4),
    })

    # --- Check 6: rate_of_change_alert, sin alertas cuando la tasa esta por
    # debajo del umbral critico
    roc2 = _mode_rate_of_change_alert({"series": series5, "critical_rate": 10.0})
    checks.append({
        "name": "rate_of_change_no_alerts_below_critical",
        "n_alerts": roc2["n_alerts"], "passed": bool(roc2["n_alerts"] == 0),
    })

    # --- Check 7: moving_average_anomaly -- un pico artificial insertado en
    # una serie constante debe quedar marcado como anomalia; el resto no
    base = [10.0] * 20
    base[10] = 100.0  # pico artificial
    ma_res = _mode_moving_average_anomaly({"series": base, "window": 5, "k_std": 2.0})
    checks.append({
        "name": "moving_average_anomaly_detects_spike",
        "anomaly_indices": ma_res["anomaly_indices"],
        "passed": bool(10 in ma_res["anomaly_indices"]),
    })

    # --- Check 8: moving_average_anomaly -- serie perfectamente constante
    # (sin ruido, sin picos) no debe marcar ninguna anomalia
    ma_res2 = _mode_moving_average_anomaly({"series": [7.0] * 15, "window": 4, "k_std": 2.0})
    checks.append({
        "name": "moving_average_no_anomalies_constant_series",
        "n_anomalies": ma_res2["n_anomalies"], "passed": bool(ma_res2["n_anomalies"] == 0),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_early_warning(mode, params=None):
    params = params or {}

    if mode == "threshold_crossing":
        return _mode_threshold_crossing(params)
    elif mode == "trend_analysis":
        return _mode_trend_analysis(params)
    elif mode == "rate_of_change_alert":
        return _mode_rate_of_change_alert(params)
    elif mode == "moving_average_anomaly":
        return _mode_moving_average_anomaly(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"Modo desconocido: {mode}")


if __name__ == "__main__":
    import json
    print(json.dumps(compute_early_warning("validate"), indent=2, ensure_ascii=False))
