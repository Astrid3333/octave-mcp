#!/usr/bin/env python3
"""
patch_lote2_validate.py

Agrega mode="validate" a 5 tools del bloque dispatcher (Lote 2):
  glm_tool, clustering_tool, multibody_dynamics_tool,
  finite_element_tool, archaeological_simulation

Mismo patron que patch_lote1_validate.py:
  - backup con shutil.copy antes de tocar cada archivo
  - anchors de string exactos con assert count==1
  - ast.parse() de verificacion antes de dar por buena la escritura
  - enum del schema actualizado via regex sobre "enum": [...] de la
    propiedad "mode" (no dependemos de tener visto el schema completo
    de cada archivo)

Correr desde ~/octave-mcp:
    python3 patch_lote2_validate.py
"""
import ast
import re
import shutil
import time

TIMESTAMP = int(time.time())


def backup(path):
    bak = f"{path}.bak.{TIMESTAMP}"
    shutil.copy(path, bak)
    print(f"OK: backup creado en {bak}")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def replace_unique(content, old, new, path, label):
    count = content.count(old)
    if count != 1:
        raise RuntimeError(
            f"ANCHOR NO UNICO ({count} ocurrencias) en {path} para '{label}'. "
            "Abortando sin escribir -- revisa el archivo manualmente."
        )
    return content.replace(old, new, 1)


def patch_mode_enum(content, path):
    """
    Busca la primera propiedad "mode": {"type": "string", "enum": [...]}
    y agrega "validate" si no esta. Usa regex porque no en todos los
    archivos vimos el schema completo literal.
    """
    pattern = re.compile(
        r'("mode":\s*\{\s*"type":\s*"string",\s*"enum":\s*\[)([^\]]*)(\])'
    )
    m = pattern.search(content)
    if not m:
        raise RuntimeError(f"No encontre el enum de 'mode' en {path} -- revisar a mano.")
    inner = m.group(2)
    if '"validate"' in inner:
        print(f"  (ya tenia 'validate' en el enum de {path}, no toco nada)")
        return content
    new_inner = inner.rstrip()
    if not new_inner.endswith(","):
        new_inner += ","
    new_inner += ' "validate"'
    new_block = m.group(1) + new_inner + m.group(3)
    content = content[: m.start()] + new_block + content[m.end():]
    print(f"OK ({path}): 'validate' agregado al enum del schema.")
    return content


def verify_syntax(path, content):
    try:
        ast.parse(content)
    except SyntaxError as e:
        raise RuntimeError(f"SINTAXIS INVALIDA en {path} tras el parche: {e}")
    print(f"OK: {path} parcheado y sintaxis valida.")


# ---------------------------------------------------------------------
# Bloques _validate_* -- se insertan antes de 'if __name__ == "__main__":'
# en cada archivo (anchor comun a los 5).
# ---------------------------------------------------------------------

VALIDATE_GLM = '''
def _validate_glm():
    checks = []
    rng = np.random.default_rng(0)

    # --- logistic_regression vs sklearn (mismo caso que el __main__) ---
    try:
        from sklearn.linear_model import LogisticRegression as SkLogistic
        n = 500
        X = rng.normal(0, 1, (n, 2))
        true_beta = np.array([0.5, -1.2, 2.0])
        eta = true_beta[0] + X @ true_beta[1:]
        p_true = 1 / (1 + np.exp(-eta))
        y = (rng.uniform(0, 1, n) < p_true).astype(float)
        r = _logistic_regression(X.tolist(), y.tolist())
        sk = SkLogistic(penalty=None, max_iter=1000).fit(X, y)
        intercept_diff = abs(r["coefficients"][0] - sk.intercept_[0])
        coef_diff = float(np.max(np.abs(np.array(r["coefficients"][1:]) - sk.coef_[0])))
        checks.append({
            "name": "logistic_regression_vs_sklearn",
            "expected": "diffs < 1e-2",
            "got": {"intercept_diff": round(float(intercept_diff), 6), "max_coef_diff": round(coef_diff, 6)},
            "passed": bool(intercept_diff < 1e-2 and coef_diff < 1e-2),
        })
    except ImportError as e:
        checks.append({"name": "logistic_regression_vs_sklearn", "expected": "sklearn disponible",
                        "got": str(e), "passed": False})

    # --- poisson_regression vs sklearn ---
    try:
        from sklearn.linear_model import PoissonRegressor
        true_beta_p = np.array([0.3, 0.5, -0.2])
        eta_p = true_beta_p[0] + X @ true_beta_p[1:]
        mu_p = np.exp(np.clip(eta_p, -10, 10))
        y_p = rng.poisson(mu_p).astype(float)
        r = _poisson_regression(X.tolist(), y_p.tolist())
        sk_p = PoissonRegressor(alpha=0.0, max_iter=1000).fit(X, y_p)
        intercept_diff_p = abs(r["coefficients"][0] - sk_p.intercept_)
        coef_diff_p = float(np.max(np.abs(np.array(r["coefficients"][1:]) - sk_p.coef_)))
        checks.append({
            "name": "poisson_regression_vs_sklearn",
            "expected": "diffs < 1e-3",
            "got": {"intercept_diff": round(float(intercept_diff_p), 6), "max_coef_diff": round(coef_diff_p, 6)},
            "passed": bool(intercept_diff_p < 1e-3 and coef_diff_p < 1e-3),
        })
    except ImportError as e:
        checks.append({"name": "poisson_regression_vs_sklearn", "expected": "sklearn disponible",
                        "got": str(e), "passed": False})

    # --- ridge_lasso (ridge) vs sklearn, ecuacion normal en escala estandarizada ---
    try:
        from sklearn.linear_model import Ridge as SkRidge
        from sklearn.preprocessing import StandardScaler
        n2 = 200
        X2 = rng.normal(0, 1, (n2, 5))
        true_beta2 = np.array([1.5, 0.0, -2.0, 0.0, 3.0])
        y2 = X2 @ true_beta2 + rng.normal(0, 1, n2)
        r = _ridge_lasso("ridge", X2.tolist(), y2.tolist(),
                          lambdas=[0.01, 0.1, 1.0, 10.0, 100.0], k_folds=5)
        scaler = StandardScaler().fit(X2)
        X2s = scaler.transform(X2)
        y2c = y2 - y2.mean()
        sk_ridge = SkRidge(alpha=r["best_lambda"], fit_intercept=False).fit(X2s, y2c)
        ridge_diff = float(np.max(np.abs(np.array(r["coefficients_standardized"]) - sk_ridge.coef_)))
        checks.append({
            "name": "ridge_vs_sklearn",
            "expected": "max diff < 1e-3",
            "got": {"max_coef_diff": round(ridge_diff, 6), "best_lambda": r["best_lambda"]},
            "passed": bool(ridge_diff < 1e-3),
        })

        # lasso: recupera exactamente los 3 coeficientes no nulos de true_beta2
        r_lasso = _ridge_lasso("lasso", X2.tolist(), y2.tolist(),
                                lambdas=[0.001, 0.01, 0.1, 1.0], k_folds=5)
        checks.append({
            "name": "lasso_sparsity_recovery",
            "expected": 3,
            "got": r_lasso["n_nonzero_coefficients"],
            "passed": r_lasso["n_nonzero_coefficients"] == 3,
        })
    except ImportError as e:
        checks.append({"name": "ridge_vs_sklearn", "expected": "sklearn disponible",
                        "got": str(e), "passed": False})

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}

'''

VALIDATE_CLUSTERING = '''
def _validate_clustering():
    checks = []
    try:
        from sklearn.cluster import KMeans as SKKMeans, AgglomerativeClustering
        from sklearn.metrics import adjusted_rand_score
        from sklearn.decomposition import PCA as SKPCA

        rng = np.random.default_rng(42)
        c1 = rng.normal(loc=[0, 0], scale=0.5, size=(40, 2))
        c2 = rng.normal(loc=[5, 5], scale=0.5, size=(40, 2))
        c3 = rng.normal(loc=[0, 5], scale=0.5, size=(40, 2))
        X = np.vstack([c1, c2, c3])

        mine = _kmeans(X, k=3, random_state=42)
        sk = SKKMeans(n_clusters=3, n_init=10, random_state=42).fit(X)
        inertia_diff = abs(mine["inertia"] - sk.inertia_)
        checks.append({
            "name": "kmeans_inertia_vs_sklearn",
            "expected": "diff < 1e-3",
            "got": round(float(inertia_diff), 8),
            "passed": bool(inertia_diff < 1e-3),
        })

        for method in ["single", "complete", "average"]:
            mine_h = _hierarchical(X, linkage=method, n_clusters=3)
            sk_h = AgglomerativeClustering(n_clusters=3, linkage=method).fit(X)
            ari = adjusted_rand_score(mine_h["labels"], sk_h.labels_)
            checks.append({
                "name": f"hierarchical_{method}_ari_vs_sklearn",
                "expected": ">= 0.95",
                "got": round(float(ari), 6),
                "passed": bool(ari >= 0.95),
            })

        mine_p = _pca_extended(X, n_components=2, standardize=True)
        sk_p = SKPCA(n_components=2).fit((X - X.mean(0)) / X.std(0, ddof=1))
        evr_diff = float(np.max(np.abs(
            np.array(mine_p["explained_variance_ratio"]) - sk_p.explained_variance_ratio_
        )))
        checks.append({
            "name": "pca_explained_variance_vs_sklearn",
            "expected": "max diff < 1e-6",
            "got": round(evr_diff, 8),
            "passed": bool(evr_diff < 1e-6),
        })
    except ImportError as e:
        checks.append({"name": "clustering_vs_sklearn", "expected": "sklearn disponible",
                        "got": str(e), "passed": False})

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}

'''

VALIDATE_MULTIBODY = '''
def _validate_multibody_dynamics():
    checks = []
    r1 = _compound_pendulum(m=2.0, L=1.5)
    checks.append({
        "name": "compound_pendulum_relative_error_pct",
        "expected": "< 1.0",
        "got": round(float(r1["relative_error_pct"]), 6),
        "passed": bool(r1["relative_error_pct"] < 1.0),
    })
    r2 = _rigid_body_euler(I1=3.0, I2=2.0, I3=1.0)
    checks.append({
        "name": "rigid_body_euler_energy_drift",
        "expected": "< 1e-3",
        "got": round(float(r2["energy_drift_relative"]), 8),
        "passed": bool(r2["energy_drift_relative"] < 1e-3),
    })
    r3 = _two_link_manipulator()
    checks.append({
        "name": "two_link_manipulator_energy_drift",
        "expected": "< 1e-3",
        "got": round(float(r3["energy_drift_relative"]), 8),
        "passed": bool(r3["energy_drift_relative"] < 1e-3),
    })
    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}

'''

VALIDATE_FEM = '''
def _validate_finite_element():
    checks = []
    r1 = _bar_1d(E=200e9, A=0.001, L=2.0, P=1000.0)
    checks.append({
        "name": "bar_1d_relative_error_pct",
        "expected": "< 0.5",
        "got": round(float(r1["relative_error_pct"]), 6),
        "passed": bool(r1["relative_error_pct"] < 0.5),
    })
    r2 = _beam_bending(E=200e9, I=8e-6, L=3.0, P=500.0)
    checks.append({
        "name": "beam_bending_relative_error_pct",
        "expected": "< 0.5",
        "got": round(float(r2["relative_error_pct"]), 6),
        "passed": bool(r2["relative_error_pct"] < 0.5),
    })
    r3 = _truss_2d(
        nodes=[[0, 0], [1, 0], [0.5, 0.866]],
        elements=[[0, 1], [1, 2], [0, 2]],
        E=200e9, A=0.0005,
        loads={5: -1000.0},
        fixed_dofs=[0, 1, 2, 3],
    )
    checks.append({
        "name": "truss_2d_equilibrium_residual_max",
        "expected": "< 1e-6",
        "got": r3["equilibrium_residual_max"],
        "passed": bool(r3["equilibrium_residual_max"] < 1e-6),
    })
    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}

'''

VALIDATE_ARCHAEO = '''
def _validate_archaeological_simulation():
    checks = []
    r1 = compute_malthusian_growth(P0=10, r=0.5, K0=100, K_amplitude=20,
                                    K_period=20, t_max=100, n_points=60)
    err1 = r1["validacion_caso_K_constante"]["max_error_vs_logistico_analitico"]
    checks.append({
        "name": "malthusian_growth_vs_logistico_analitico",
        "expected": "< 1e-3",
        "got": err1,
        "passed": bool(err1 < 1e-3),
    })

    r2 = compute_technology_diffusion(M_market=1000, p_innovation=0.03,
                                       q_imitation=0.4, t_max=30, n_points=30)
    err2 = r2["max_error_vs_analitico"]
    checks.append({
        "name": "technology_diffusion_vs_analitico",
        "expected": "< 1e-3",
        "got": err2,
        "passed": bool(err2 < 1e-3),
    })

    settlements = [
        {"name": "A", "population": 500, "x": 0, "y": 0},
        {"name": "B", "population": 300, "x": 10, "y": 0},
        {"name": "C", "population": 800, "x": 5, "y": 8},
        {"name": "D", "population": 150, "x": 15, "y": 5},
    ]
    r3 = compute_trade_network(settlements=settlements, gravity_exponent=2)
    # C tiene la mayor poblacion y esta relativamente central -> hub esperado.
    # NO VERIFICADO A MANO -- confirmar con una corrida suelta antes de confiar.
    checks.append({
        "name": "trade_network_hub_identificado",
        "expected": "C",
        "got": r3["hub_identificado"],
        "passed": r3["hub_identificado"] == "C",
    })

    r4 = compute_collapse_dynamics(P0=10, R0=50, r=0.5, K_capacity=200,
                                    a_attack=0.02, h_handling=0.4,
                                    e_efficiency=0.6, m_mortality=0.3,
                                    t_max=100, n_points=60)
    # Chequeo estructural minimo: el modulo corrio y devolvio el campo de
    # analisis esperado. Umbral de "ciclo_limite_detectado" NO verificado
    # a mano -- ajustar si el valor real difiere.
    checks.append({
        "name": "collapse_dynamics_returns_analysis_fields",
        "expected": "equilibrio_analitico_nullclines y ciclo_limite_detectado presentes",
        "got": {
            "has_equilibrio": "equilibrio_analitico_nullclines" in r4,
            "has_ciclo": "ciclo_limite_detectado" in r4,
        },
        "passed": ("equilibrio_analitico_nullclines" in r4 and "ciclo_limite_detectado" in r4),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}

'''

MAIN_ANCHOR = 'if __name__ == "__main__":'


def patch_file(path, validate_block, dispatch_old, dispatch_new):
    print(f"\\n--- {path} ---")
    content = read(path)
    backup(path)

    # 1) Insertar la funcion _validate_* justo antes del bloque __main__
    content = replace_unique(
        content, MAIN_ANCHOR, validate_block + MAIN_ANCHOR, path, "insercion _validate_*"
    )

    # 2) Insertar el branch mode == "validate" al inicio del dispatcher
    content = replace_unique(content, dispatch_old, dispatch_new, path, "branch validate")

    # 3) Actualizar el enum del schema
    content = patch_mode_enum(content, path)

    # 4) Verificar sintaxis antes de escribir
    verify_syntax(path, content)
    write(path, content)


def main():
    patch_file(
        "glm_tool.py",
        VALIDATE_GLM,
        'def compute_glm(mode, params=None):\n    params = dict(params or {})\n    if mode == "logistic_regression":',
        'def compute_glm(mode, params=None):\n    params = dict(params or {})\n    if mode == "validate":\n        return _validate_glm()\n    if mode == "logistic_regression":',
    )
    patch_file(
        "clustering_tool.py",
        VALIDATE_CLUSTERING,
        'def compute_clustering(mode, **params):',
        'def compute_clustering(mode, **params):\n    if mode == "validate":\n        return _validate_clustering()',
    )
    patch_file(
        "multibody_dynamics_tool.py",
        VALIDATE_MULTIBODY,
        'def compute_multibody_dynamics(mode, params=None):\n    params = params or {}\n    if mode == "compound_pendulum":',
        'def compute_multibody_dynamics(mode, params=None):\n    params = params or {}\n    if mode == "validate":\n        return _validate_multibody_dynamics()\n    if mode == "compound_pendulum":',
    )
    patch_file(
        "finite_element_tool.py",
        VALIDATE_FEM,
        'def compute_finite_element(mode, params=None):\n    params = params or {}\n    if mode == "bar_1d":',
        'def compute_finite_element(mode, params=None):\n    params = params or {}\n    if mode == "validate":\n        return _validate_finite_element()\n    if mode == "bar_1d":',
    )
    patch_file(
        "archaeological_simulation.py",
        VALIDATE_ARCHAEO,
        'def compute_archaeological_simulation(mode, **kwargs):\n    """Dispatcher unico para el tool MCP archaeological_simulation, segun \'mode\'."""\n    fns = {\n        "malthusian_growth": compute_malthusian_growth,',
        'def compute_archaeological_simulation(mode, **kwargs):\n    """Dispatcher unico para el tool MCP archaeological_simulation, segun \'mode\'."""\n    if mode == "validate":\n        return _validate_archaeological_simulation()\n    fns = {\n        "malthusian_growth": compute_malthusian_growth,',
    )

    print("\\nOK: las 5 tools del Lote 2 fueron parcheadas.")


if __name__ == "__main__":
    main()
