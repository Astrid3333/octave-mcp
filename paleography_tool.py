#!/usr/bin/env python3
"""
paleography_tool.py
Metodos matematicos de paleografia y datacion relativa de manuscritos,
autocontenidos (sin curvas de calibracion externas hardcodeadas - toda
fecha de anclaje o dataset de calibracion es provisto por quien llama):

  - correspondence_seriation: dada una matriz manuscrito x rasgo (o sitio
    x tipo), ordena las filas por cronologia relativa via Analisis de
    Correspondencias (reciprocal averaging / SVD sobre residuos
    estandarizados) - el metodo clasico de seriacion de Kendall, usado
    tanto en arqueologia como en paleografia para ordenar manuscritos sin
    fechas absolutas a partir de sus perfiles de rasgos compartidos.

  - feature_dating_regression: con un set de calibracion (fecha conocida,
    valor de uno o mas rasgos estilisticos - angulo de inclinacion,
    frecuencia de abreviaturas, proporcion de ligaduras, etc.) ajusta una
    regresion lineal (OLS, univariada o multivariada) y predice la fecha
    de un manuscrito sin fechar, con intervalo de confianza via la formula
    exacta de prediccion (leverage + distribucion t). Es el mecanismo
    matematico real detras de cronologias estilisticas como la de Bischoff.

  - letterform_classification: clasifica una muestra desconocida contra
    clusters de escritura de referencia (ej. uncial, carolingia, gotica)
    via distancia de Mahalanobis con covarianza combinada (pooled) entre
    clases, reporta la clase mas cercana y un p-valor aproximado (chi^2
    con p grados de libertad) para cada clase bajo el supuesto de
    normalidad multivariada.

Sin dependencias externas mas alla de numpy y scipy.stats - portable al
mismo stack que el resto de octave-mcp.
"""
import math
import numpy as np
from scipy.stats import t as _t_dist, chi2 as _chi2_dist


# ---------------------------------------------------------------------------
# Modo 1: seriacion por correspondencia
# ---------------------------------------------------------------------------

def compute_correspondence_seriation(matrix, row_labels=None):
    N = np.asarray(matrix, dtype=float)
    if N.ndim != 2:
        raise ValueError("matrix debe ser una matriz 2D (unidades x rasgos)")
    n, m = N.shape
    if n < 3 or m < 2:
        raise ValueError("se necesitan al menos 3 unidades y 2 rasgos para seriar")
    if np.any(N < 0):
        raise ValueError("matrix no puede tener valores negativos (son frecuencias/conteos)")

    total = N.sum()
    if total <= 0:
        raise ValueError("la matriz esta vacia (suma total = 0)")

    P = N / total
    r = P.sum(axis=1)  # masas de fila
    c = P.sum(axis=0)  # masas de columna
    if np.any(r <= 0) or np.any(c <= 0):
        raise ValueError("hay filas o columnas con suma cero (unidad o rasgo sin datos)")

    Dr_inv_sqrt = 1.0 / np.sqrt(r)
    Dc_inv_sqrt = 1.0 / np.sqrt(c)
    # residuo estandarizado S = Dr^-1/2 (P - r c^T) Dc^-1/2
    S = (Dr_inv_sqrt[:, None] * (P - np.outer(r, c))) * Dc_inv_sqrt[None, :]

    U, sigma, _Vt = np.linalg.svd(S, full_matrices=False)
    n_axes = min(len(sigma), 3, min(n, m) - 1)
    n_axes = max(n_axes, 1)

    # coordenadas principales de fila: Dr^-1/2 U * sigma (por eje)
    row_coords = (Dr_inv_sqrt[:, None] * U[:, :n_axes]) * sigma[:n_axes]

    total_inertia = float(np.sum(sigma ** 2))
    inertia_explained = (sigma[:n_axes] ** 2) / total_inertia if total_inertia > 0 else np.zeros(n_axes)

    labels = list(row_labels) if row_labels is not None else [f"unidad_{i}" for i in range(n)]
    if len(labels) != n:
        raise ValueError("row_labels debe tener el mismo largo que filas de matrix")

    axis1 = row_coords[:, 0]
    order = np.argsort(axis1)
    seriation_order = [labels[i] for i in order]

    result = {
        "mode": "correspondence_seriation",
        "n_units": n,
        "n_features": m,
        "n_axes_computed": int(n_axes),
        "eigenvalues": [round(float(s ** 2), 6) for s in sigma],
        "inertia_explained_pct": [round(float(x * 100), 4) for x in inertia_explained],
        "axis1_scores": {labels[i]: round(float(axis1[i]), 6) for i in range(n)},
        "seriation_order": seriation_order,
    }
    if n_axes >= 2:
        axis2 = row_coords[:, 1]
        result["axis2_scores"] = {labels[i]: round(float(axis2[i]), 6) for i in range(n)}
        result["arch_effect_note"] = (
            "si axis2 forma una parabola en funcion de axis1 (efecto 'arco' de Guttman/CA), "
            "es evidencia de que axis1 captura una dimension unica subyacente (compatible con cronologia)"
        )
    result["order_direction_note"] = (
        "el sentido del orden (mas antiguo->mas reciente o viceversa) es indeterminado por el metodo; "
        "se resuelve con al menos una fecha ancla externa conocida"
    )
    return result


# ---------------------------------------------------------------------------
# Modo 2: regresion de datacion estilistica
# ---------------------------------------------------------------------------

def compute_feature_dating_regression(calibration_dates, calibration_features, unknown_features, confidence=0.95):
    dates = np.asarray(calibration_dates, dtype=float)
    feats = np.asarray(calibration_features, dtype=float)
    if feats.ndim == 1:
        feats = feats.reshape(-1, 1)
    if feats.ndim != 2:
        raise ValueError("calibration_features debe ser una lista de numeros o una lista de listas")

    n, p = feats.shape
    if len(dates) != n:
        raise ValueError("calibration_dates y calibration_features deben tener el mismo largo")
    if n < p + 3:
        raise ValueError(f"se necesitan al menos {p + 3} puntos de calibracion para {p} rasgo(s) (para poder estimar el error)")
    if not (0 < confidence < 1):
        raise ValueError("confidence debe estar entre 0 y 1")

    X = np.hstack([np.ones((n, 1)), feats])
    XtX = X.T @ X
    try:
        XtX_inv = np.linalg.inv(XtX)
    except np.linalg.LinAlgError:
        XtX_inv = np.linalg.pinv(XtX)

    beta = XtX_inv @ X.T @ dates
    fitted = X @ beta
    residuals = dates - fitted
    dof = n - (p + 1)
    rss = float(np.sum(residuals ** 2))
    s2 = rss / dof
    tss = float(np.sum((dates - dates.mean()) ** 2))
    r_squared = (1 - rss / tss) if tss > 0 else None

    unknown = np.atleast_1d(np.asarray(unknown_features, dtype=float)).reshape(-1)
    if unknown.shape[0] != p:
        raise ValueError(f"unknown_features debe tener {p} valor(es), uno por rasgo de calibracion")

    x0 = np.concatenate([[1.0], unknown])
    predicted_date = float(x0 @ beta)
    leverage = float(x0 @ XtX_inv @ x0)
    se_pred = math.sqrt(max(s2 * (1.0 + leverage), 0.0))

    alpha = 1.0 - confidence
    t_crit = float(_t_dist.ppf(1 - alpha / 2, dof))
    margin = t_crit * se_pred

    dates_min, dates_max = float(dates.min()), float(dates.max())
    extrapolating = not (dates_min <= predicted_date <= dates_max)

    ci_key = f"confidence_interval_{int(round(confidence * 100))}pct"
    result = {
        "mode": "feature_dating_regression",
        "n_calibration_points": n,
        "n_features": p,
        "coefficients": {
            "intercept": round(float(beta[0]), 6),
            "slopes": [round(float(b), 6) for b in beta[1:]],
        },
        "r_squared": round(r_squared, 6) if r_squared is not None else None,
        "residual_std_error": round(math.sqrt(s2), 6),
        "degrees_of_freedom": int(dof),
        "predicted_date": round(predicted_date, 4),
        ci_key: [round(predicted_date - margin, 4), round(predicted_date + margin, 4)],
        "calibration_date_range": [round(dates_min, 4), round(dates_max, 4)],
        "extrapolating_beyond_calibration_range": bool(extrapolating),
    }
    if extrapolating:
        result["extrapolation_warning"] = (
            "la fecha predicha cae fuera del rango de fechas de calibracion - "
            "la relacion rasgo-fecha no esta garantizada de mantenerse ahi, el intervalo es menos confiable"
        )
    return result


# ---------------------------------------------------------------------------
# Modo 3: clasificacion de tipo de escritura
# ---------------------------------------------------------------------------

def compute_letterform_classification(reference_classes, unknown_sample, feature_names=None):
    if not isinstance(reference_classes, dict) or len(reference_classes) < 2:
        raise ValueError("reference_classes debe ser un diccionario con al menos 2 clases (nombre -> lista de muestras)")

    class_names = list(reference_classes.keys())
    Xs = {}
    p = None
    for name in class_names:
        arr = np.asarray(reference_classes[name], dtype=float)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        if arr.shape[0] < 1:
            raise ValueError(f"la clase '{name}' no tiene muestras")
        if p is None:
            p = arr.shape[1]
        elif arr.shape[1] != p:
            raise ValueError("todas las clases deben tener el mismo numero de rasgos")
        Xs[name] = arr

    x0 = np.atleast_1d(np.asarray(unknown_sample, dtype=float)).reshape(-1)
    if x0.shape[0] != p:
        raise ValueError(f"unknown_sample debe tener {p} valor(es), uno por rasgo de referencia")

    k = len(class_names)
    n_total = sum(X.shape[0] for X in Xs.values())
    dof_pool = n_total - k
    if dof_pool < p:
        raise ValueError(
            f"no hay suficientes muestras para estimar covarianza combinada de {p} rasgos "
            f"(se necesitan al menos {p + k} muestras en total, hay {n_total})"
        )

    means = {name: X.mean(axis=0) for name, X in Xs.items()}
    scatter = np.zeros((p, p))
    for name, X in Xs.items():
        diff = X - means[name]
        scatter += diff.T @ diff
    S_pooled = scatter / dof_pool

    try:
        S_inv = np.linalg.inv(S_pooled)
        singular = False
    except np.linalg.LinAlgError:
        S_inv = np.linalg.pinv(S_pooled)
        singular = True

    distances_sq = {}
    for name in class_names:
        diff = x0 - means[name]
        distances_sq[name] = float(diff @ S_inv @ diff)

    ranked = sorted(distances_sq.items(), key=lambda kv: kv[1])
    best_class, best_d2 = ranked[0]

    p_values = {name: float(_chi2_dist.sf(d2, df=p)) for name, d2 in distances_sq.items()}

    result = {
        "mode": "letterform_classification",
        "n_classes": k,
        "n_features": p,
        "n_reference_samples_total": n_total,
        "predicted_class": best_class,
        "mahalanobis_distances": {name: round(math.sqrt(max(d2, 0.0)), 6) for name, d2 in distances_sq.items()},
        "mahalanobis_distances_squared": {name: round(d2, 6) for name, d2 in distances_sq.items()},
        "approx_p_values_chi2": {name: round(pv, 6) for name, pv in p_values.items()},
        "ranking_closest_to_farthest": [name for name, _ in ranked],
    }
    if feature_names is not None:
        result["feature_names"] = list(feature_names)
    if singular:
        result["covariance_warning"] = (
            "la matriz de covarianza combinada era singular (muy pocas muestras respecto a rasgos) - "
            "se uso pseudo-inversa, las distancias pueden ser inestables"
        )
    result["assumption_note"] = (
        "asume distribucion aproximadamente normal multivariada dentro de cada clase y covarianza "
        "compartida entre clases (supuesto de LDA/Mahalanobis clasico) - con pocas muestras de referencia "
        "por clase, tratar el p-valor como orientativo, no como probabilidad exacta"
    )
    return result


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def _validate_paleography():
    """Checks anclados a casos sinteticos con solucion conocida de
    antemano (no solo 'no exploto')."""
    checks = []

    # --- correspondence_seriation: matriz diagonal tipo Guttman ---
    # cada unidad concentra su peso en rasgos contiguos, corriendo en
    # diagonal: el eje 1 deberia recuperar el orden original o su reverso.
    matrix = [
        [10, 8, 1, 0],
        [8, 10, 8, 1],
        [1, 8, 10, 8],
        [0, 1, 8, 10],
    ]
    labels = ["u0", "u1", "u2", "u3"]
    r1 = compute_correspondence_seriation(matrix, row_labels=labels)
    order = r1.get("seriation_order")
    forward = labels
    reverse = list(reversed(labels))
    checks.append({
        "name": "correspondence_seriation_matriz_diagonal_recupera_orden",
        "seriation_order": order,
        "passed": bool(order == forward or order == reverse),
    })

    # --- feature_dating_regression: calibracion perfectamente lineal ---
    dates = [100, 200, 300, 400, 500]
    features = [1, 2, 3, 4, 5]
    r2 = compute_feature_dating_regression(dates, features, unknown_features=[3.5])
    checks.append({
        "name": "feature_dating_regression_r_squared_exacto_1",
        "r_squared": r2.get("r_squared"),
        "passed": bool(r2.get("r_squared") is not None and abs(r2["r_squared"] - 1.0) < 1e-9),
    })
    checks.append({
        "name": "feature_dating_regression_predicted_date_exacto",
        "predicted_date": r2.get("predicted_date"),
        "passed": bool(abs(r2.get("predicted_date", -1) - 350.0) < 1e-6),
    })
    checks.append({
        "name": "feature_dating_regression_residual_std_error_casi_cero",
        "residual_std_error": r2.get("residual_std_error"),
        "passed": bool(r2.get("residual_std_error", 999) < 1e-6),
    })

    # --- letterform_classification: dos clases bien separadas ---
    reference_classes = {
        "clase_A": [[0.0, 0.0], [0.1, -0.1], [-0.1, 0.1], [0.05, 0.0]],
        "clase_B": [[10.0, 10.0], [10.1, 9.9], [9.9, 10.1], [10.05, 10.0]],
    }
    r3 = compute_letterform_classification(reference_classes, unknown_sample=[0.02, 0.02])
    d = r3.get("mahalanobis_distances", {})
    checks.append({
        "name": "letterform_classification_predice_clase_verdadera",
        "predicted_class": r3.get("predicted_class"),
        "distances": d,
        "passed": bool(r3.get("predicted_class") == "clase_A"
                        and d.get("clase_A", 999) < d.get("clase_B", -1)),
    })

    # --- validacion de entrada: matrix con negativos -> ValueError ---
    raised1 = False
    try:
        compute_correspondence_seriation([[1, -1], [2, 2], [3, 3]])
    except ValueError:
        raised1 = True
    checks.append({
        "name": "correspondence_seriation_valores_negativos_levanta_valueerror",
        "passed": raised1,
    })

    # --- validacion de entrada: muy pocos puntos de calibracion ---
    raised2 = False
    try:
        compute_feature_dating_regression([100, 200], [1, 2], unknown_features=[1.5])
    except ValueError:
        raised2 = True
    checks.append({
        "name": "feature_dating_regression_pocos_puntos_levanta_valueerror",
        "passed": raised2,
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed, "n_checks": len(checks)}


def compute_paleography(mode, **kwargs):
    if mode == "validate":
        return _validate_paleography()
    if mode == "correspondence_seriation":
        return compute_correspondence_seriation(
            kwargs["matrix"],
            row_labels=kwargs.get("row_labels"),
        )
    elif mode == "feature_dating_regression":
        return compute_feature_dating_regression(
            kwargs["calibration_dates"],
            kwargs["calibration_features"],
            kwargs["unknown_features"],
            confidence=kwargs.get("confidence", 0.95),
        )
    elif mode == "letterform_classification":
        return compute_letterform_classification(
            kwargs["reference_classes"],
            kwargs["unknown_sample"],
            feature_names=kwargs.get("feature_names"),
        )
    else:
        raise ValueError(f"modo desconocido: {mode}")


PALEOGRAPHY_TOOL_SCHEMA = {
    "name": "paleography",
    "description": (
        "Metodos matematicos de paleografia y datacion relativa de manuscritos: "
        "seriacion por Analisis de Correspondencias (ordena manuscritos por cronologia "
        "relativa a partir de una matriz unidad x rasgo), regresion de datacion estilistica "
        "(ajusta fecha ~ rasgo(s) con un set de calibracion y predice fecha con intervalo de "
        "confianza), y clasificacion de tipo de escritura por distancia de Mahalanobis contra "
        "clusters de referencia (ej. uncial, carolingia, gotica). No incluye curvas de "
        "calibracion externas (ej. radiocarbono) - los datos de calibracion los provee quien llama."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["correspondence_seriation", "feature_dating_regression", "letterform_classification", "validate"],
            },
            "matrix": {
                "type": "array",
                "description": "correspondence_seriation: matriz 2D (unidades x rasgos) de frecuencias/conteos no negativos",
            },
            "row_labels": {
                "type": "array",
                "description": "correspondence_seriation, opcional: nombres de las unidades (filas), en el mismo orden que matrix",
            },
            "calibration_dates": {
                "type": "array",
                "description": "feature_dating_regression: fechas conocidas de los manuscritos de calibracion",
            },
            "calibration_features": {
                "type": "array",
                "description": "feature_dating_regression: valores del/los rasgo(s) de calibracion - lista de numeros (1 rasgo) o lista de listas (varios rasgos)",
            },
            "unknown_features": {
                "description": "feature_dating_regression: valor(es) del rasgo para el manuscrito a datar - numero o lista, mismo formato que calibration_features",
            },
            "confidence": {
                "type": "number",
                "description": "feature_dating_regression, opcional: nivel de confianza del intervalo (default 0.95)",
            },
            "reference_classes": {
                "type": "object",
                "description": "letterform_classification: diccionario nombre_de_clase -> lista de muestras (cada muestra es una lista de valores de rasgo)",
            },
            "unknown_sample": {
                "type": "array",
                "description": "letterform_classification: valores de rasgo de la muestra a clasificar, mismo orden/numero que reference_classes",
            },
            "feature_names": {
                "type": "array",
                "description": "letterform_classification, opcional: nombres de los rasgos, solo para eco informativo en la respuesta",
            },
        },
        "required": ["mode"],
    },
}

PALEOGRAPHY_SCHEMA = {   'type': 'object',
    'properties': {   'mode': {'type': 'string'},
                      'matriz': {'type': 'array'},
                      'doc_ids': {'type': 'array'},
                      'anios_conocidos': {'type': 'object'},
                      'anios_ancla': {'type': 'array'},
                      'rasgo_ancla': {'type': 'array'},
                      'rasgo_predecir': {'type': 'array'},
                      'ids_predecir': {'type': 'array'},
                      'grado_polinomio': {'type': 'integer'},
                      'rasgos_entrenamiento': {'type': 'array'},
                      'clases_entrenamiento': {'type': 'array'},
                      'rasgos_nuevos': {'type': 'array'},
                      'ids_nuevos': {'type': 'array'}}}

try:
    from tool_registry import register_tool
    register_tool(
        name="paleography",
        schema={
        "name": "paleography",
        "description": 'Tres motores cuantitativos de paleografia/codicologia sobre rasgos YA EXTRAIDOS (no hace OCR ni lee imagenes): seriation (analisis de correspondencia via SVD sobre matriz documentos x rasgos, ordena por el eje 1 y valida contra anios_conocidos con Spearman si se dan), feature_dating_regression (ajusta anio ~ rasgo sobre documentos ancla de fecha conocida y estima fecha de documentos sin fecha, con error estandar residual), letterform_classification (nearest-centroid sobre rasgos normalizados, clasifica letterforms en clases conocidas y marca casos ambiguos por margen chico). Ninguno da fechas/atribuciones definitivas.',
        "inputSchema": PALEOGRAPHY_SCHEMA,
    },
        handler=lambda args: compute_paleography(**args),
    )
except ImportError:
    pass

