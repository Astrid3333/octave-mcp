#!/usr/bin/env python3
"""
patch_grupo_b_validate.py

Agrega mode="validate" a las 4 tools del grupo B (dispatcher basado en
dict "fns" o if/elif, todas devolvian "mode desconocido: validate"):

  - math_humanizer_tool.py: valida que list_concepts no este vacio, que
    explain_concept sobre el primer concepto devuelva analogy/connection/
    note no vacios, y que un concepto inexistente levante ValueError.
  - network_science_tool.py: centrality sobre un triangulo K3 (A-B-C
    completo) tiene solucion cerrada exacta -- grado=2 para los 3 nodos,
    betweenness=0 (no hay caminos que pasen por un tercer nodo en un
    triangulo), closeness=1.0 (distancia 1 a los otros 2 nodos: (n-1)/
    sum(d)=2/2), pagerank uniforme=1/3 por simetria.
  - wavelet_tool.py: dwt con wavelet="haar" sobre una senal CONSTANTE
    tiene solucion cerrada exacta -- los coeficientes de detalle son
    cero exacto (diferencia de valores iguales), rmse de reconstruccion
    cero, y el coeficiente de aproximacion es value*sqrt(2) (normalizacion
    ortonormal de Haar).
  - percolation_theory_tool.py: site_percolation con p=1.0 (deterministico,
    sin importar el seed) da todos los sitios ocupados en un unico cluster
    que abarca toda la grilla (percolates=True); con p=0.0 da cero sitios
    ocupados, cero clusters, no percola.

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
    """Agrega "validate" al enum de mode que contiene first_mode_literal,
    si existe exactamente 1 y todavia no lo tiene."""
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
            f"(encontrados: {len(matches)}). El dispatcher acepta mode='validate' "
            "igual, pero puede seguir SKIPPED en run_all_validations.py hasta "
            "que el schema se actualice a mano."
        )
    return content


# ---------------------------------------------------------------------------
# 1) math_humanizer_tool.py
# ---------------------------------------------------------------------------

def patch_math_humanizer():
    path = "math_humanizer_tool.py"
    backup(path)
    content = read(path)

    validate_fn = '''
def _validate_math_humanizer():
    checks = []
    lst = _list_concepts()
    concepts = lst.get("concepts", [])
    checks.append({
        "name": "list_concepts_non_empty",
        "expected": ">0", "got": len(concepts),
        "passed": len(concepts) > 0,
    })

    sample_ok = False
    sample_concept = None
    if concepts:
        sample_concept = concepts[0]
        try:
            r = _explain_concept(sample_concept)
            sample_ok = (
                isinstance(r, dict)
                and bool(r.get("everyday_analogy"))
                and bool(r.get("philosophical_connection"))
                and bool(r.get("deeper_note"))
            )
        except Exception:
            sample_ok = False
    checks.append({
        "name": "explain_concept_sample_non_empty_fields",
        "expected": "dict con everyday_analogy/philosophical_connection/deeper_note no vacios",
        "got": sample_concept,
        "passed": sample_ok,
    })

    try:
        _explain_concept("concepto_inexistente_xyz_no_deberia_existir")
        unknown_raises = False
    except ValueError:
        unknown_raises = True
    except Exception:
        unknown_raises = False
    checks.append({
        "name": "explain_concept_unknown_raises_valueerror",
        "expected": True, "got": unknown_raises,
        "passed": unknown_raises,
    })

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}


'''

    def_anchor = "def compute_math_humanizer(mode, **params):"
    n = content.count(def_anchor)
    assert n == 1, f"{path}: esperaba 1 ocurrencia de def_anchor, encontre {n}"
    content = content.replace(def_anchor, validate_fn + def_anchor)

    dispatch_anchor = '''    if mode == "explain_concept":
        return _explain_concept(params["concept"])'''
    dispatch_repl = '''    if mode == "validate":
        return _validate_math_humanizer()
    if mode == "explain_concept":
        return _explain_concept(params["concept"])'''
    n2 = content.count(dispatch_anchor)
    assert n2 == 1, f"{path}: esperaba 1 ocurrencia de dispatch_anchor, encontre {n2}"
    content = content.replace(dispatch_anchor, dispatch_repl)

    content = patch_enum(content, path, "explain_concept")

    write(path, content)
    validate_syntax(path)
    print(f"OK: {path} parcheado y sintaxis valida.")


# ---------------------------------------------------------------------------
# 2) network_science_tool.py
# ---------------------------------------------------------------------------

def patch_network_science():
    path = "network_science_tool.py"
    backup(path)
    content = read(path)

    validate_fn = '''
def _validate_network_science():
    checks = []
    edges_k3 = [("A", "B"), ("B", "C"), ("A", "C")]
    r = compute_centrality(edges_k3, measures=["degree", "betweenness", "closeness", "pagerank"])
    deg = r["measures"]["degree"]
    bet = r["measures"]["betweenness"]
    clo = r["measures"]["closeness"]
    pr = r["measures"]["pagerank"]

    checks.append({
        "name": "k3_degree_all_2",
        "expected": 2, "got": deg,
        "passed": len(deg) == 3 and all(v == 2 for v in deg.values()),
    })
    checks.append({
        "name": "k3_betweenness_all_zero",
        "expected": 0.0, "got": bet,
        "passed": all(abs(v) < 1e-9 for v in bet.values()),
    })
    checks.append({
        "name": "k3_closeness_all_one",
        "expected": 1.0, "got": clo,
        "passed": all(abs(v - 1.0) < 1e-6 for v in clo.values()),
    })
    checks.append({
        "name": "k3_pagerank_uniform_third",
        "expected": round(1 / 3, 6), "got": pr,
        "passed": all(abs(v - 1 / 3) < 1e-3 for v in pr.values()),
    })
    checks.append({
        "name": "k3_node_edge_counts",
        "expected": {"n_nodes": 3, "n_edges": 3},
        "got": {"n_nodes": r["n_nodes"], "n_edges": r["n_edges"]},
        "passed": r["n_nodes"] == 3 and r["n_edges"] == 3,
    })

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}


'''

    def_anchor = "def compute_network_science(mode, **kwargs):"
    n = content.count(def_anchor)
    assert n == 1, f"{path}: esperaba 1 ocurrencia de def_anchor, encontre {n}"
    content = content.replace(def_anchor, validate_fn + def_anchor)

    dispatch_anchor = '''    """Dispatcher unico para el tool MCP network_science, segun 'mode'."""
    fns = {'''
    dispatch_repl = '''    """Dispatcher unico para el tool MCP network_science, segun 'mode'."""
    if mode == "validate":
        return _validate_network_science()
    fns = {'''
    n2 = content.count(dispatch_anchor)
    assert n2 == 1, f"{path}: esperaba 1 ocurrencia de dispatch_anchor, encontre {n2}"
    content = content.replace(dispatch_anchor, dispatch_repl)

    content = patch_enum(content, path, "centrality")

    write(path, content)
    validate_syntax(path)
    print(f"OK: {path} parcheado y sintaxis valida.")


# ---------------------------------------------------------------------------
# 3) wavelet_tool.py
# ---------------------------------------------------------------------------

def patch_wavelet():
    path = "wavelet_tool.py"
    backup(path)
    content = read(path)

    validate_fn = '''
def _validate_wavelet():
    checks = []
    signal = [5.0] * 16
    r = compute_dwt(signal, wavelet="haar", level=1)

    energy0 = r["energy_per_detail_level"][0] if r["energy_per_detail_level"] else None
    checks.append({
        "name": "constant_signal_detail_energy_zero",
        "expected": 0.0, "got": energy0,
        "passed": energy0 is not None and abs(energy0) < 1e-8,
    })
    checks.append({
        "name": "constant_signal_reconstruction_rmse_zero",
        "expected": 0.0, "got": r["reconstruction_rmse"],
        "passed": abs(r["reconstruction_rmse"]) < 1e-8,
    })

    exp_approx = 5.0 * (2 ** 0.5)
    got_approx = r["approximation_coeffs_sample"][0] if r["approximation_coeffs_sample"] else None
    checks.append({
        "name": "constant_signal_haar_approx_coeff",
        "expected": round(exp_approx, 6), "got": got_approx,
        "passed": got_approx is not None and abs(got_approx - exp_approx) < 1e-4,
    })

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}


'''

    def_anchor = "def compute_wavelet(mode, **kwargs):"
    n = content.count(def_anchor)
    assert n == 1, f"{path}: esperaba 1 ocurrencia de def_anchor, encontre {n}"
    content = content.replace(def_anchor, validate_fn + def_anchor)

    dispatch_anchor = '''    """Dispatcher unico para el tool MCP wavelet, segun 'mode'."""
    fns = {'''
    dispatch_repl = '''    """Dispatcher unico para el tool MCP wavelet, segun 'mode'."""
    if mode == "validate":
        return _validate_wavelet()
    fns = {'''
    n2 = content.count(dispatch_anchor)
    assert n2 == 1, f"{path}: esperaba 1 ocurrencia de dispatch_anchor, encontre {n2}"
    content = content.replace(dispatch_anchor, dispatch_repl)

    content = patch_enum(content, path, "cwt")

    write(path, content)
    validate_syntax(path)
    print(f"OK: {path} parcheado y sintaxis valida.")


# ---------------------------------------------------------------------------
# 4) percolation_theory_tool.py
# ---------------------------------------------------------------------------

def patch_percolation():
    path = "percolation_theory_tool.py"
    backup(path)
    content = read(path)

    validate_fn = '''
def _validate_percolation_theory():
    checks = []
    L = 10

    r_full = compute_site_percolation(L=L, p=1.0, seed=1)
    checks.append({
        "name": "site_percolation_p1_all_occupied",
        "expected": L * L, "got": r_full["n_occupied_sites"],
        "passed": r_full["n_occupied_sites"] == L * L,
    })
    checks.append({
        "name": "site_percolation_p1_single_cluster",
        "expected": 1, "got": r_full["n_clusters"],
        "passed": r_full["n_clusters"] == 1,
    })
    checks.append({
        "name": "site_percolation_p1_giant_fraction_one",
        "expected": 1.0, "got": r_full["giant_cluster_fraction"],
        "passed": abs(r_full["giant_cluster_fraction"] - 1.0) < 1e-9,
    })
    checks.append({
        "name": "site_percolation_p1_percolates_true",
        "expected": True, "got": r_full["percolates"],
        "passed": r_full["percolates"] is True,
    })

    r_empty = compute_site_percolation(L=L, p=0.0, seed=1)
    checks.append({
        "name": "site_percolation_p0_none_occupied",
        "expected": 0, "got": r_empty["n_occupied_sites"],
        "passed": r_empty["n_occupied_sites"] == 0,
    })
    checks.append({
        "name": "site_percolation_p0_no_clusters",
        "expected": 0, "got": r_empty["n_clusters"],
        "passed": r_empty["n_clusters"] == 0,
    })
    checks.append({
        "name": "site_percolation_p0_percolates_false",
        "expected": False, "got": r_empty["percolates"],
        "passed": r_empty["percolates"] is False,
    })

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}


'''

    def_anchor = "def compute_percolation_theory(mode, **kwargs):"
    n = content.count(def_anchor)
    assert n == 1, f"{path}: esperaba 1 ocurrencia de def_anchor, encontre {n}"
    content = content.replace(def_anchor, validate_fn + def_anchor)

    dispatch_anchor = '''    """Dispatcher unico para el tool MCP percolation_theory, segun 'mode'."""
    fns = {'''
    dispatch_repl = '''    """Dispatcher unico para el tool MCP percolation_theory, segun 'mode'."""
    if mode == "validate":
        return _validate_percolation_theory()
    fns = {'''
    n2 = content.count(dispatch_anchor)
    assert n2 == 1, f"{path}: esperaba 1 ocurrencia de dispatch_anchor, encontre {n2}"
    content = content.replace(dispatch_anchor, dispatch_repl)

    content = patch_enum(content, path, "site_percolation")

    write(path, content)
    validate_syntax(path)
    print(f"OK: {path} parcheado y sintaxis valida.")


# ---------------------------------------------------------------------------

def main():
    patch_math_humanizer()
    patch_network_science()
    patch_wavelet()
    patch_percolation()
    print("\nOK: los 4 archivos del grupo B fueron parcheados.")


if __name__ == "__main__":
    main()
