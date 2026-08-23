#!/usr/bin/env python3
"""
patch_lote1_validate.py

Agrega mode="validate" a 5 tools del grupo B (dispatcher "fns" dict o
if/elif que devolvian "mode desconocido: validate"):

  - mcdm_tool.py: weighted_sum con matriz 2x2 disenada para que una
    alternativa domine en TODO (benefit alto + cost bajo) y la otra sea
    dominada en TODO -> normalizacion min-max da R=[[0,0],[1,1]] exacto,
    scores=[0.0, 1.0] exacto, ranking=[2, 1] exacto.
  - optimal_control_tool.py: LQR escalar A=0,B=1,Q=1,R=1 -> Riccati
    algebraica -P^2+1=0 tiene raiz positiva unica P=1, K=R^-1*B*P=1,
    lazo cerrado A-BK=-1 (autovalor real=-1, estable). Cero simulacion,
    resuelve un sistema 1x1.
  - spatial_statistics_tool.py: Moran's I sobre 4 puntos colineales
    equiespaciados (x=0,1,2,3) con values=[1,2,3,4], weight_type="knn",
    k=1 -> con vecino mas cercano de cada punto fijo por la geometria,
    I=8/20=0.4 y E[I]=-1/(n-1)=-1/3 exactos (verificados a mano completo,
    ver comentario en _validate_spatial_statistics).
  - stochastic_processes_tool.py: cadena de Markov de 2 estados con
    transition_matrix=[[0.9,0.1],[0.3,0.7]] -> distribucion estacionaria
    exacta resolviendo pi*P=pi, pi0+pi1=1: pi=[0.75, 0.25].
  - text_analysis_math_tool.py: distancia de Levenshtein es 100%
    determinista -- "gato" vs "gata" = 1, "" vs "abc" = 3, con sus
    normalized_distance/similarity derivados exactos.

Convenciones habituales: backup timestamped por archivo, anchors con
assert count==1, ast.parse + py_compile despues de cada escritura.
"""

import ast
import py_compile
import re
import shutil
import time


def backup(path):
    ts = int(time.time())
    dst = f"{path}.bak.{ts}"
    shutil.copy(path, dst)
    print(f"OK: backup creado en {dst}")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def validate_syntax(path):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    ast.parse(src)
    py_compile.compile(path, doraise=True)


def patch_enum(content, path, first_mode_literal):
    pattern = re.compile(r'"enum":\s*\[\s*"' + re.escape(first_mode_literal) + r'"[^\]]*\]')
    matches = pattern.findall(content)
    if len(matches) == 1 and '"validate"' not in matches[0]:
        old_enum = matches[0]
        new_enum = old_enum[:-1].rstrip() + ', "validate"]'
        content = content.replace(old_enum, new_enum, 1)
        print(f"OK ({path}): 'validate' agregado al enum del schema.")
    elif len(matches) == 1:
        print(f"OK ({path}): el enum ya incluia 'validate' (sin cambios).")
    else:
        print(
            f"AVISO ({path}): no se encontro exactamente 1 enum de mode "
            f"(encontrados: {len(matches)}). Revisar a mano."
        )
    return content


def patch_fns_dispatcher(content, path, docstring_snippet, validate_call):
    """Inserta 'if mode == \"validate\": return X()' justo despues del
    docstring del dispatcher, antes del dict fns = {...}."""
    anchor = docstring_snippet + '\n    fns = {'
    repl = docstring_snippet + f'\n    if mode == "validate":\n        return {validate_call}\n    fns = {{'
    n = content.count(anchor)
    assert n == 1, f"{path}: esperaba 1 ocurrencia de dispatcher anchor, encontre {n}"
    return content.replace(anchor, repl)


# ---------------------------------------------------------------------------
# 1) mcdm_tool.py
# ---------------------------------------------------------------------------

def patch_mcdm():
    path = "mcdm_tool.py"
    backup(path)
    content = read(path)

    validate_fn = '''
def _validate_mcdm():
    checks = []
    # A domina en todo (benefit alto, cost bajo), B es dominada en todo.
    r = compute_weighted_sum(
        decision_matrix=[[1, 10], [10, 1]],
        weights=[1, 1],
        criteria_types=["benefit", "cost"],
        method="sum",
    )
    exp_scores = [0.0, 1.0]
    exp_ranking = [2, 1]
    checks.append({
        "name": "weighted_sum_dominant_scores",
        "expected": exp_scores, "got": r["scores"],
        "passed": all(abs(a - b) < 1e-6 for a, b in zip(r["scores"], exp_scores)),
    })
    checks.append({
        "name": "weighted_sum_dominant_ranking",
        "expected": exp_ranking, "got": r["ranking"],
        "passed": r["ranking"] == exp_ranking,
    })

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}


'''
    def_anchor = "def compute_mcdm(mode, **kwargs):"
    n = content.count(def_anchor)
    assert n == 1, f"{path}: esperaba 1 ocurrencia de def_anchor, encontre {n}"
    content = content.replace(def_anchor, validate_fn + def_anchor, 1)

    content = patch_fns_dispatcher(
        content, path,
        '''    """Dispatcher unico para el tool MCP mcdm, segun 'mode'."""''',
        "_validate_mcdm()",
    )
    content = patch_enum(content, path, "ahp")

    write(path, content)
    validate_syntax(path)
    print(f"OK: {path} parcheado y sintaxis valida.")


# ---------------------------------------------------------------------------
# 2) optimal_control_tool.py
# ---------------------------------------------------------------------------

def patch_optimal_control():
    path = "optimal_control_tool.py"
    backup(path)
    content = read(path)

    validate_fn = '''
def _validate_optimal_control():
    checks = []
    # LQR escalar: A=0, B=1, Q=1, R=1 -> Riccati algebraica -P^2+1=0,
    # raiz positiva P=1; K=R^-1*B*P=1; lazo cerrado A-BK=-1 (estable).
    r = compute_lqr(A=[[0.0]], B=[[1.0]], Q=[[1.0]], R=[[1.0]], x0=[1.0], T=5.0, n_steps=200)

    K = r["gain_matrix_K"][0][0]
    P = r["riccati_solution_P"][0][0]
    checks.append({
        "name": "lqr_scalar_riccati_P",
        "expected": 1.0, "got": P,
        "passed": abs(P - 1.0) < 1e-4,
    })
    checks.append({
        "name": "lqr_scalar_gain_K",
        "expected": 1.0, "got": K,
        "passed": abs(K - 1.0) < 1e-4,
    })
    eig = r["closed_loop_eigenvalues"][0]
    checks.append({
        "name": "lqr_scalar_closed_loop_eigenvalue",
        "expected": {"real": -1.0, "imag": 0.0}, "got": eig,
        "passed": abs(eig["real"] - (-1.0)) < 1e-4 and abs(eig["imag"]) < 1e-6,
    })
    checks.append({
        "name": "lqr_scalar_stable",
        "expected": True, "got": r["closed_loop_stable"],
        "passed": r["closed_loop_stable"] is True,
    })

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}


'''
    def_anchor = "def compute_optimal_control(mode, **kwargs):"
    n = content.count(def_anchor)
    assert n == 1, f"{path}: esperaba 1 ocurrencia de def_anchor, encontre {n}"
    content = content.replace(def_anchor, validate_fn + def_anchor, 1)

    content = patch_fns_dispatcher(
        content, path,
        '''    """Dispatcher unico para el tool MCP optimal_control, segun 'mode'."""''',
        "_validate_optimal_control()",
    )
    content = patch_enum(content, path, "lqr")

    write(path, content)
    validate_syntax(path)
    print(f"OK: {path} parcheado y sintaxis valida.")


# ---------------------------------------------------------------------------
# 3) spatial_statistics_tool.py
# ---------------------------------------------------------------------------

def patch_spatial_statistics():
    path = "spatial_statistics_tool.py"
    backup(path)
    content = read(path)

    validate_fn = '''
def _validate_spatial_statistics():
    checks = []
    # 4 puntos colineales equiespaciados, values=[1,2,3,4], knn k=1.
    # Vecino mas cercano por punto (fijo por la geometria y el desempate
    # estable de np.argsort): 0->1, 1->0, 2->1, 3->2.
    # z_dev = values - 2.5 = [-1.5, -0.5, 0.5, 1.5]
    # S0 = 4 (cuatro pesos 1 en la matriz W)
    # num = n * sum(W * outer(z_dev, z_dev))
    #     = 4 * [z0*z1 + z1*z0 + z2*z1 + z3*z2]
    #     = 4 * [0.75 + 0.75 - 0.25 + 0.75] = 4 * 2.0 = 8.0
    # den = S0 * sum(z_dev^2) = 4 * 5.0 = 20.0
    # I = 8.0 / 20.0 = 0.4 exacto; E[I] = -1/(n-1) = -1/3 exacto
    coords = [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [3.0, 0.0]]
    values = [1.0, 2.0, 3.0, 4.0]
    r = compute_morans_i(values, coords, weight_type="knn", k=1)

    exp_I = 0.4
    exp_E_I = -1.0 / 3.0
    checks.append({
        "name": "morans_i_collinear_exact",
        "expected": round(exp_I, 6), "got": r["morans_i"],
        "passed": abs(r["morans_i"] - exp_I) < 1e-4,
    })
    checks.append({
        "name": "morans_i_expected_under_null",
        "expected": round(exp_E_I, 6), "got": r["expected_i_under_null"],
        "passed": abs(r["expected_i_under_null"] - exp_E_I) < 1e-4,
    })

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}


'''
    def_anchor = "def compute_spatial_statistics(mode, **kwargs):"
    n = content.count(def_anchor)
    assert n == 1, f"{path}: esperaba 1 ocurrencia de def_anchor, encontre {n}"
    content = content.replace(def_anchor, validate_fn + def_anchor, 1)

    content = patch_fns_dispatcher(
        content, path,
        '''    """Dispatcher unico para el tool MCP spatial_statistics, segun 'mode'."""''',
        "_validate_spatial_statistics()",
    )
    content = patch_enum(content, path, "morans_i")

    write(path, content)
    validate_syntax(path)
    print(f"OK: {path} parcheado y sintaxis valida.")


# ---------------------------------------------------------------------------
# 4) stochastic_processes_tool.py
# ---------------------------------------------------------------------------

def patch_stochastic_processes():
    path = "stochastic_processes_tool.py"
    backup(path)
    content = read(path)

    validate_fn = '''
def _validate_stochastic_processes():
    checks = []
    # Cadena de 2 estados, transition_matrix=[[0.9,0.1],[0.3,0.7]].
    # Estacionaria exacta: pi0*0.9+pi1*0.3=pi0 y pi0+pi1=1 -> pi=[0.75,0.25].
    r = compute_markov_chain(
        transition_matrix=[[0.9, 0.1], [0.3, 0.7]],
        n_steps=100,
    )
    exp_stationary = [0.75, 0.25]
    checks.append({
        "name": "markov_chain_stationary_distribution",
        "expected": exp_stationary, "got": r["stationary_distribution"],
        "passed": all(abs(a - b) < 1e-3 for a, b in zip(r["stationary_distribution"], exp_stationary)),
    })
    checks.append({
        "name": "markov_chain_converged",
        "expected": True, "got": r["converged_to_stationary"],
        "passed": r["converged_to_stationary"] is True,
    })

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}


'''
    def_anchor = "def compute_stochastic_processes(mode, **kwargs):"
    n = content.count(def_anchor)
    assert n == 1, f"{path}: esperaba 1 ocurrencia de def_anchor, encontre {n}"
    content = content.replace(def_anchor, validate_fn + def_anchor, 1)

    content = patch_fns_dispatcher(
        content, path,
        '''    """Dispatcher unico para el tool MCP stochastic_processes, segun 'mode'."""''',
        "_validate_stochastic_processes()",
    )
    content = patch_enum(content, path, "brownian_motion")

    write(path, content)
    validate_syntax(path)
    print(f"OK: {path} parcheado y sintaxis valida.")


# ---------------------------------------------------------------------------
# 5) text_analysis_math_tool.py
# ---------------------------------------------------------------------------

def patch_text_analysis_math():
    path = "text_analysis_math_tool.py"
    backup(path)
    content = read(path)

    validate_fn = '''
def _validate_text_analysis_math():
    checks = []
    r1 = compute_edit_distance("gato", "gata", method="levenshtein")
    checks.append({
        "name": "levenshtein_gato_gata_distance",
        "expected": 1, "got": r1["distance"],
        "passed": r1["distance"] == 1,
    })
    checks.append({
        "name": "levenshtein_gato_gata_normalized",
        "expected": 0.25, "got": r1["normalized_distance"],
        "passed": abs(r1["normalized_distance"] - 0.25) < 1e-6,
    })

    r2 = compute_edit_distance("", "abc", method="levenshtein")
    checks.append({
        "name": "levenshtein_empty_vs_abc_distance",
        "expected": 3, "got": r2["distance"],
        "passed": r2["distance"] == 3,
    })
    checks.append({
        "name": "levenshtein_empty_vs_abc_similarity",
        "expected": 0.0, "got": r2["similarity"],
        "passed": abs(r2["similarity"] - 0.0) < 1e-6,
    })

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}


'''
    def_anchor = "def compute_text_analysis_math(mode, **kwargs):"
    n = content.count(def_anchor)
    assert n == 1, f"{path}: esperaba 1 ocurrencia de def_anchor, encontre {n}"
    content = content.replace(def_anchor, validate_fn + def_anchor, 1)

    dispatch_anchor = '''def compute_text_analysis_math(mode, **kwargs):
    if mode == "edit_distance":'''
    dispatch_repl = '''def compute_text_analysis_math(mode, **kwargs):
    if mode == "validate":
        return _validate_text_analysis_math()
    if mode == "edit_distance":'''
    n2 = content.count(dispatch_anchor)
    assert n2 == 1, f"{path}: esperaba 1 ocurrencia de dispatch_anchor, encontre {n2}"
    content = content.replace(dispatch_anchor, dispatch_repl, 1)

    content = patch_enum(content, path, "edit_distance")

    write(path, content)
    validate_syntax(path)
    print(f"OK: {path} parcheado y sintaxis valida.")


# ---------------------------------------------------------------------------

def main():
    patch_mcdm()
    patch_optimal_control()
    patch_spatial_statistics()
    patch_stochastic_processes()
    patch_text_analysis_math()
    print("\nOK: las 5 tools del Lote 1 fueron parcheadas.")


if __name__ == "__main__":
    main()
