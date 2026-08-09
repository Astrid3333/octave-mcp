"""
chemometrics_tool.py
=====================
Modulo para octave-mcp / mcp-octave-real siguiendo el patron:
    compute_chemometrics(mode, params) -> dict
    CHEMOMETRICS_TOOL_SCHEMA (JSONRPC tool schema)

Cubre:
  - generate_synthetic_spectra : genera espectros FTIR/RMN sinteticos
  - pls_calibration            : regresion PLS (algoritmo NIPALS) con CV
  - pcr_calibration             : regresion PCR (PCA + regresion lineal) con CV
  - doe_design                  : diseno experimental (factorial completo,
                                   Box-Behnken simplificado, Latin Hypercube)
  - validate_recovery           : test de extremo a extremo -> toma
                                   concentraciones "reales" generadas por
                                   enzyme_kinetics_tool o reaction_diffusion_tool,
                                   las convierte a espectros sinteticos con ruido,
                                   y mide que tan bien PLS/PCR las recupera.

Contrato de conexion (acordado con Astrid, 2026-08):
  enzyme_kinetics_tool / reaction_diffusion_tool  -->  concentraciones "reales"
        (lista de floats, una serie temporal o espacial)
                    |
                    v
        generate_synthetic_spectra(concentrations, ...)
                    |
                    v
              espectros sinteticos con ruido
                    |
                    v
        pls_calibration / pcr_calibration
                    |
                    v
        concentraciones RECUPERADAS  -->  comparar contra las "reales"
                                            (validate_recovery hace este loop)

Sin dependencias externas mas alla de numpy (misma filosofia liviana que el
resto de octave-mcp). No se usa scikit-learn a proposito.
"""

import numpy as np


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def _as_array(x, name):
    try:
        arr = np.asarray(x, dtype=float)
    except Exception as e:
        raise ValueError(f"'{name}' debe ser numerico (lista o lista de listas): {e}")
    return arr


def _kfold_indices(n_samples, k, seed=0):
    rng = np.random.default_rng(seed)
    idx = rng.permutation(n_samples)
    folds = np.array_split(idx, k)
    return folds


def _rmse(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float).ravel()
    y_pred = np.asarray(y_pred, dtype=float).ravel()
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def _r2(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float).ravel()
    y_pred = np.asarray(y_pred, dtype=float).ravel()
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        return 1.0 if ss_res == 0 else 0.0
    return float(1 - ss_res / ss_tot)


# ---------------------------------------------------------------------------
# Generacion de espectros sinteticos (FTIR / RMN)
# ---------------------------------------------------------------------------

def _synthetic_spectrum(concentration, n_points, peak_centers, peak_widths,
                         peak_heights_per_unit, baseline_drift, noise_std, rng):
    """
    Genera un espectro como suma de picos gaussianos cuya altura escala
    linealmente con la concentracion (ley de Beer-Lambert simplificada),
    mas deriva de linea base y ruido gaussiano.
    """
    x = np.linspace(0, 1, n_points)
    spectrum = np.zeros(n_points)
    for center, width, height_per_unit in zip(peak_centers, peak_widths,
                                                peak_heights_per_unit):
        amplitude = height_per_unit * concentration
        spectrum += amplitude * np.exp(-0.5 * ((x - center) / width) ** 2)

    if baseline_drift:
        drift = baseline_drift * (x - 0.5)
        spectrum += drift

    spectrum += rng.normal(0, noise_std, size=n_points)
    return spectrum


def generate_synthetic_spectra(params):
    """
    params:
      concentrations: list[float]      -- REQUERIDO. una por muestra
      spectrum_type: 'ftir' | 'rmn'    -- default 'ftir'
      n_points: int                    -- default 200 (resolucion espectral)
      n_peaks: int                     -- default 3 (num picos caracteristicos)
      noise_std: float                 -- default 0.02
      baseline_drift: float            -- default 0.05
      seed: int                        -- default 0
    """
    concentrations = params.get("concentrations")
    if concentrations is None:
        raise ValueError("Falta 'concentrations' (lista de floats).")
    concentrations = _as_array(concentrations, "concentrations")

    spectrum_type = params.get("spectrum_type", "ftir")
    n_points = int(params.get("n_points", 200))
    n_peaks = int(params.get("n_peaks", 3))
    noise_std = float(params.get("noise_std", 0.02))
    baseline_drift = float(params.get("baseline_drift", 0.05))
    seed = int(params.get("seed", 0))

    rng = np.random.default_rng(seed)

    # Picos "caracteristicos" fijos para la corrida (mismo compuesto en
    # todas las muestras), tipicos de FTIR (bandas anchas) vs RMN (picos finos)
    if spectrum_type == "rmn":
        peak_widths = list(rng.uniform(0.005, 0.02, size=n_peaks))
    else:
        peak_widths = list(rng.uniform(0.03, 0.08, size=n_peaks))

    peak_centers = list(rng.uniform(0.1, 0.9, size=n_peaks))
    peak_heights_per_unit = list(rng.uniform(0.5, 2.0, size=n_peaks))

    spectra = np.array([
        _synthetic_spectrum(c, n_points, peak_centers, peak_widths,
                             peak_heights_per_unit, baseline_drift,
                             noise_std, rng)
        for c in concentrations
    ])

    return {
        "spectrum_type": spectrum_type,
        "n_samples": int(len(concentrations)),
        "n_points": n_points,
        "wavelength_axis": np.linspace(0, 1, n_points).tolist(),
        "peak_centers": peak_centers,
        "peak_widths": peak_widths,
        "concentrations": concentrations.tolist(),
        "spectra": spectra.tolist(),
        "note": ("Espectro sintetico: amplitud de picos proporcional a la "
                 "concentracion (Beer-Lambert simplificado) + deriva de "
                 "linea base + ruido gaussiano."),
    }


# ---------------------------------------------------------------------------
# PLS (NIPALS) - implementacion propia, sin sklearn
# ---------------------------------------------------------------------------

def _pls_nipals_fit(X, y, n_components):
    """
    PLS1 via NIPALS. X: (n_samples, n_features), y: (n_samples,)
    Devuelve W, P, Q, T (scores) y las medias/desvios para poder predecir.
    """
    X = np.array(X, dtype=float)
    y = np.array(y, dtype=float).reshape(-1, 1)

    x_mean, x_std = X.mean(axis=0), X.std(axis=0)
    x_std[x_std == 0] = 1.0
    y_mean, y_std = y.mean(), (y.std() or 1.0)

    Xc = (X - x_mean) / x_std
    yc = (y - y_mean) / y_std

    n_samples, n_features = Xc.shape
    n_components = min(n_components, n_features, n_samples - 1)
    n_components = max(1, n_components)

    W = np.zeros((n_features, n_components))
    P = np.zeros((n_features, n_components))
    Q = np.zeros(n_components)
    T = np.zeros((n_samples, n_components))

    X_res = Xc.copy()
    y_res = yc.copy()

    for a in range(n_components):
        w = X_res.T @ y_res
        norm = np.linalg.norm(w)
        if norm < 1e-12:
            n_components = a
            break
        w = w / norm
        t = X_res @ w
        t_norm_sq = float((t.T @ t).item()) or 1e-12
        p = (X_res.T @ t) / t_norm_sq
        q = float(((y_res.T @ t) / t_norm_sq).item())

        X_res = X_res - t @ p.reshape(1, -1)
        y_res = y_res - t * q

        W[:, a] = w.ravel()
        P[:, a] = p.ravel()
        Q[a] = q
        T[:, a] = t.ravel()

    W = W[:, :n_components]
    P = P[:, :n_components]
    Q = Q[:n_components]

    # matriz de regresion en el espacio original estandarizado
    # B = W (P'W)^-1 Q
    PtW = P.T @ W
    try:
        PtW_inv = np.linalg.pinv(PtW)
    except np.linalg.LinAlgError:
        PtW_inv = np.linalg.pinv(PtW + 1e-8 * np.eye(PtW.shape[0]))
    B = W @ PtW_inv @ Q.reshape(-1, 1)  # (n_features, 1)

    model = {
        "B": B, "x_mean": x_mean, "x_std": x_std,
        "y_mean": y_mean, "y_std": y_std, "n_components": n_components,
    }
    return model


def _pls_predict(model, X):
    X = np.array(X, dtype=float)
    Xc = (X - model["x_mean"]) / model["x_std"]
    y_pred_c = Xc @ model["B"]
    y_pred = y_pred_c.ravel() * model["y_std"] + model["y_mean"]
    return y_pred


def pls_calibration(params):
    """
    params:
      spectra: list[list[float]]   -- REQUERIDO (n_samples x n_points)
      concentrations: list[float]  -- REQUERIDO (n_samples,)
      n_components: int            -- default 3
      cv_folds: int                -- default 5 (0 = sin CV)
      seed: int                    -- default 0
    """
    spectra = params.get("spectra")
    concentrations = params.get("concentrations")
    if spectra is None or concentrations is None:
        raise ValueError("Faltan 'spectra' y/o 'concentrations'.")

    X = _as_array(spectra, "spectra")
    y = _as_array(concentrations, "concentrations")
    n_components = int(params.get("n_components", 3))
    cv_folds = int(params.get("cv_folds", 5))
    seed = int(params.get("seed", 0))

    model = _pls_nipals_fit(X, y, n_components)
    y_pred_train = _pls_predict(model, X)

    result = {
        "method": "PLS (NIPALS)",
        "n_components_used": model["n_components"],
        "train_rmse": _rmse(y, y_pred_train),
        "train_r2": _r2(y, y_pred_train),
        "predicted_train": y_pred_train.tolist(),
    }

    if cv_folds and cv_folds > 1 and len(y) >= cv_folds:
        folds = _kfold_indices(len(y), cv_folds, seed)
        cv_pred = np.zeros_like(y)
        for i, test_idx in enumerate(folds):
            train_idx = np.setdiff1d(np.arange(len(y)), test_idx)
            m = _pls_nipals_fit(X[train_idx], y[train_idx], n_components)
            cv_pred[test_idx] = _pls_predict(m, X[test_idx])
        result["cv_folds"] = cv_folds
        result["cv_rmse"] = _rmse(y, cv_pred)
        result["cv_r2"] = _r2(y, cv_pred)
        result["cv_predicted"] = cv_pred.tolist()

    return result


# ---------------------------------------------------------------------------
# PCR: PCA (via SVD) + regresion lineal sobre los scores
# ---------------------------------------------------------------------------

def _pca_fit(X, n_components):
    x_mean = X.mean(axis=0)
    x_std = X.std(axis=0)
    x_std[x_std == 0] = 1.0
    Xc = (X - x_mean) / x_std

    U, S, Vt = np.linalg.svd(Xc, full_matrices=False)
    n_components = min(n_components, Vt.shape[0])
    loadings = Vt[:n_components].T          # (n_features, n_components)
    scores = Xc @ loadings                   # (n_samples, n_components)
    explained_var = (S ** 2) / np.sum(S ** 2)
    return {
        "loadings": loadings, "x_mean": x_mean, "x_std": x_std,
        "explained_variance_ratio": explained_var[:n_components].tolist(),
        "scores": scores, "n_components": n_components,
    }


def _pcr_regress(scores, y):
    y_mean = y.mean()
    yc = y - y_mean
    coef, *_ = np.linalg.lstsq(scores, yc, rcond=None)
    return coef, y_mean


def pcr_calibration(params):
    """
    params:
      spectra: list[list[float]]   -- REQUERIDO
      concentrations: list[float]  -- REQUERIDO
      n_components: int            -- default 3
      cv_folds: int                -- default 5 (0 = sin CV)
      seed: int                    -- default 0
    """
    spectra = params.get("spectra")
    concentrations = params.get("concentrations")
    if spectra is None or concentrations is None:
        raise ValueError("Faltan 'spectra' y/o 'concentrations'.")

    X = _as_array(spectra, "spectra")
    y = _as_array(concentrations, "concentrations")
    n_components = int(params.get("n_components", 3))
    cv_folds = int(params.get("cv_folds", 5))
    seed = int(params.get("seed", 0))

    pca = _pca_fit(X, n_components)
    coef, y_mean = _pcr_regress(pca["scores"], y)
    y_pred_train = pca["scores"] @ coef + y_mean

    result = {
        "method": "PCR (PCA + regresion lineal)",
        "n_components_used": pca["n_components"],
        "explained_variance_ratio": pca["explained_variance_ratio"],
        "train_rmse": _rmse(y, y_pred_train),
        "train_r2": _r2(y, y_pred_train),
        "predicted_train": y_pred_train.tolist(),
    }

    if cv_folds and cv_folds > 1 and len(y) >= cv_folds:
        folds = _kfold_indices(len(y), cv_folds, seed)
        cv_pred = np.zeros_like(y)
        for test_idx in folds:
            train_idx = np.setdiff1d(np.arange(len(y)), test_idx)
            pca_tr = _pca_fit(X[train_idx], n_components)
            coef_tr, y_mean_tr = _pcr_regress(pca_tr["scores"], y[train_idx])

            Xc_test = (X[test_idx] - pca_tr["x_mean"]) / pca_tr["x_std"]
            scores_test = Xc_test @ pca_tr["loadings"]
            cv_pred[test_idx] = scores_test @ coef_tr + y_mean_tr

        result["cv_folds"] = cv_folds
        result["cv_rmse"] = _rmse(y, cv_pred)
        result["cv_r2"] = _r2(y, cv_pred)
        result["cv_predicted"] = cv_pred.tolist()

    return result


# ---------------------------------------------------------------------------
# DOE (diseno experimental)
# ---------------------------------------------------------------------------

def _full_factorial(factor_levels):
    """factor_levels: dict {factor_name: [level1, level2, ...]}"""
    names = list(factor_levels.keys())
    grids = np.meshgrid(*[factor_levels[n] for n in names], indexing="ij")
    combos = np.stack([g.ravel() for g in grids], axis=1)
    return names, combos


def _box_behnken(n_factors, low=-1.0, high=1.0):
    """
    Box-Behnken simplificado para 3 factores (el caso mas comun).
    Para n_factors != 3 cae a factorial completo de 3 niveles como fallback
    documentado (no es un BBD estricto, pero deja el diseno usable).
    """
    if n_factors != 3:
        levels = {f"x{i+1}": [low, 0.0, high] for i in range(n_factors)}
        names, combos = _full_factorial(levels)
        return names, combos, "fallback_full_factorial_3_niveles"

    mid = 0.0
    combos = []
    pairs = [(0, 1), (0, 2), (1, 2)]
    for i, j in pairs:
        for a in (low, high):
            for b in (low, high):
                row = [mid, mid, mid]
                row[i] = a
                row[j] = b
                combos.append(row)
    combos.append([mid, mid, mid])  # punto central
    return ["x1", "x2", "x3"], np.array(combos), "box_behnken_3_factores"


def _latin_hypercube(n_factors, n_runs, seed=0):
    rng = np.random.default_rng(seed)
    result = np.zeros((n_runs, n_factors))
    for f in range(n_factors):
        cut = np.linspace(0, 1, n_runs + 1)
        u = rng.uniform(cut[:-1], cut[1:])
        rng.shuffle(u)
        result[:, f] = u * 2 - 1  # escalar a [-1, 1]
    names = [f"x{i+1}" for i in range(n_factors)]
    return names, result


def doe_design(params):
    """
    params:
      design_type: 'full_factorial' | 'box_behnken' | 'latin_hypercube'
      n_factors: int              -- REQUERIDO para box_behnken / latin_hypercube
      factor_levels: dict         -- REQUERIDO para full_factorial
                                      {"temp": [20,30,40], "pH": [5,7,9]}
      n_runs: int                 -- REQUERIDO para latin_hypercube
      seed: int                   -- default 0
    """
    design_type = params.get("design_type", "full_factorial")

    if design_type == "full_factorial":
        factor_levels = params.get("factor_levels")
        if not factor_levels:
            raise ValueError("Falta 'factor_levels' para full_factorial.")
        names, combos = _full_factorial(factor_levels)
        return {
            "design_type": "full_factorial",
            "factor_names": names,
            "n_runs": int(combos.shape[0]),
            "design_matrix": combos.tolist(),
        }

    elif design_type == "box_behnken":
        n_factors = int(params.get("n_factors", 3))
        names, combos, variant = _box_behnken(n_factors)
        return {
            "design_type": "box_behnken",
            "variant": variant,
            "factor_names": names,
            "n_runs": int(combos.shape[0]),
            "design_matrix": combos.tolist(),
        }

    elif design_type == "latin_hypercube":
        n_factors = int(params.get("n_factors", 2))
        n_runs = int(params.get("n_runs", 10))
        seed = int(params.get("seed", 0))
        names, combos = _latin_hypercube(n_factors, n_runs, seed)
        return {
            "design_type": "latin_hypercube",
            "factor_names": names,
            "n_runs": n_runs,
            "design_matrix": combos.tolist(),
        }

    else:
        raise ValueError(f"design_type desconocido: {design_type}")


# ---------------------------------------------------------------------------
# Validacion de extremo a extremo -- el punto de conexion con
# enzyme_kinetics_tool / reaction_diffusion_tool
# ---------------------------------------------------------------------------

def validate_recovery(params):
    """
    Loop de validacion acordado:
      concentraciones "reales" (vienen de afuera, p.ej. de
      enzyme_kinetics_tool.compute_michaelis_menten o de un corte temporal/
      espacial de reaction_diffusion_tool) -> se generan espectros sinteticos
      con ruido -> se recuperan con PLS y PCR -> se compara contra las
      "reales".

    params:
      true_concentrations: list[float]  -- REQUERIDO. viene de
          enzyme_kinetics_tool / reaction_diffusion_tool (o de donde sea)
      source: str                       -- opcional, solo informativo
          ('enzyme_kinetics_tool' | 'reaction_diffusion_tool' | 'manual')
      spectrum_type: 'ftir' | 'rmn'      -- default 'ftir'
      noise_std: float                  -- default 0.02
      n_components: int                 -- default 3
      cv_folds: int                     -- default 5
      seed: int                         -- default 0
    """
    true_conc = params.get("true_concentrations")
    if true_conc is None:
        raise ValueError("Falta 'true_concentrations' (de enzyme_kinetics_tool "
                          "o reaction_diffusion_tool).")

    spec_params = {
        "concentrations": true_conc,
        "spectrum_type": params.get("spectrum_type", "ftir"),
        "n_points": params.get("n_points", 200),
        "n_peaks": params.get("n_peaks", 3),
        "noise_std": params.get("noise_std", 0.02),
        "baseline_drift": params.get("baseline_drift", 0.05),
        "seed": params.get("seed", 0),
    }
    spectra_result = generate_synthetic_spectra(spec_params)

    common = {
        "spectra": spectra_result["spectra"],
        "concentrations": true_conc,
        "n_components": params.get("n_components", 3),
        "cv_folds": params.get("cv_folds", 5),
        "seed": params.get("seed", 0),
    }
    pls_result = pls_calibration(common)
    pcr_result = pcr_calibration(common)

    return {
        "source": params.get("source", "manual"),
        "n_samples": spectra_result["n_samples"],
        "spectrum_type": spectra_result["spectrum_type"],
        "true_concentrations": true_conc,
        "pls": {
            "cv_rmse": pls_result.get("cv_rmse", pls_result["train_rmse"]),
            "cv_r2": pls_result.get("cv_r2", pls_result["train_r2"]),
            "recovered": pls_result.get("cv_predicted",
                                         pls_result["predicted_train"]),
        },
        "pcr": {
            "cv_rmse": pcr_result.get("cv_rmse", pcr_result["train_rmse"]),
            "cv_r2": pcr_result.get("cv_r2", pcr_result["train_r2"]),
            "recovered": pcr_result.get("cv_predicted",
                                         pcr_result["predicted_train"]),
        },
        "note": ("Comparar 'true_concentrations' contra 'pls.recovered' / "
                 "'pcr.recovered'. cv_r2 cercano a 1 y cv_rmse bajo indican "
                 "buena recuperacion desde el espectro sintetico ruidoso."),
    }


# ---------------------------------------------------------------------------
# Dispatcher del modulo
# ---------------------------------------------------------------------------

def compute_chemometrics(mode, params=None):
    params = params or {}
    dispatch = {
        "generate_synthetic_spectra": generate_synthetic_spectra,
        "pls_calibration": pls_calibration,
        "pcr_calibration": pcr_calibration,
        "doe_design": doe_design,
        "validate_recovery": validate_recovery,
    }
    if mode not in dispatch:
        raise ValueError(
            f"Modo desconocido: '{mode}'. Modos validos: {list(dispatch.keys())}"
        )
    return dispatch[mode](params)


# ---------------------------------------------------------------------------
# Schema JSONRPC (mismo patron que el resto de octave-mcp)
# ---------------------------------------------------------------------------

CHEMOMETRICS_TOOL_SCHEMA = {
    "name": "chemometrics_tool",
    "description": (
        "Calibracion multivariante (PLS/PCR), diseno experimental (DOE) y "
        "espectroscopia sintetica (FTIR/RMN). Modos disponibles: "
        "generate_synthetic_spectra, pls_calibration, pcr_calibration, "
        "doe_design, validate_recovery. Este ultimo conecta con "
        "enzyme_kinetics_tool y reaction_diffusion_tool: toma concentraciones "
        "'reales' generadas por esos tools, las convierte a espectros "
        "sinteticos ruidosos, y mide que tan bien PLS/PCR las recupera."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "generate_synthetic_spectra",
                    "pls_calibration",
                    "pcr_calibration",
                    "doe_design",
                    "validate_recovery",
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
# Bloque de autotest rapido (correr con: python3 chemometrics_tool.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("== Test generate_synthetic_spectra ==")
    conc = [0.1, 0.3, 0.5, 0.7, 0.9, 1.1, 1.3, 1.5]
    spec = compute_chemometrics("generate_synthetic_spectra", {
        "concentrations": conc, "spectrum_type": "ftir", "n_points": 100,
    })
    print("n_samples:", spec["n_samples"], "n_points:", spec["n_points"])

    print("\n== Test pls_calibration ==")
    pls_res = compute_chemometrics("pls_calibration", {
        "spectra": spec["spectra"], "concentrations": conc,
        "n_components": 2, "cv_folds": 4,
    })
    print("train_r2:", round(pls_res["train_r2"], 4),
          "cv_r2:", round(pls_res.get("cv_r2", -1), 4))

    print("\n== Test pcr_calibration ==")
    pcr_res = compute_chemometrics("pcr_calibration", {
        "spectra": spec["spectra"], "concentrations": conc,
        "n_components": 2, "cv_folds": 4,
    })
    print("train_r2:", round(pcr_res["train_r2"], 4),
          "cv_r2:", round(pcr_res.get("cv_r2", -1), 4))

    print("\n== Test doe_design (full_factorial) ==")
    doe_res = compute_chemometrics("doe_design", {
        "design_type": "full_factorial",
        "factor_levels": {"temp": [20, 30, 40], "pH": [5, 7, 9]},
    })
    print("n_runs:", doe_res["n_runs"])

    print("\n== Test doe_design (box_behnken) ==")
    bb_res = compute_chemometrics("doe_design", {
        "design_type": "box_behnken", "n_factors": 3,
    })
    print("n_runs:", bb_res["n_runs"], "variant:", bb_res["variant"])

    print("\n== Test validate_recovery (simulando salida de enzyme_kinetics_tool) ==")
    # Ejemplo: concentraciones que 'vendrian' de una curva de Michaelis-Menten
    fake_mm_concentrations = [0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4]
    val_res = compute_chemometrics("validate_recovery", {
        "true_concentrations": fake_mm_concentrations,
        "source": "enzyme_kinetics_tool",
        "noise_std": 0.03,
        "n_components": 2,
        "cv_folds": 4,
    })
    print("PLS cv_r2:", round(val_res["pls"]["cv_r2"], 4),
          "PCR cv_r2:", round(val_res["pcr"]["cv_r2"], 4))
    print("\nOK - todos los tests corrieron sin excepciones.")
