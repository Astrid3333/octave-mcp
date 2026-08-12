"""
fem_advanced_tool.py
Analisis modal (vibraciones libres) de vigas Euler-Bernoulli via autovalores
generalizados K*phi = omega^2 * M*phi, con matriz de masa consistente
(no lumped -- misma familia de funciones de forma cubicas que la rigidez,
da mejor convergencia con pocos elementos).

Modos:
  - modal_beam : frecuencias naturales y modos propios de una viga con
                 condiciones de apoyo pinned_pinned o cantilever

Validado contra formulas analiticas de viga Euler-Bernoulli (Blevins,
Formulas for Natural Frequency and Mode Shape):
  omega_n = (beta_n*L)^2 * sqrt(E*I / (rho*A*L^4))
  pinned_pinned: beta_n*L = n*pi                    (n=1,2,3,...)
  cantilever:    beta_n*L = 1.875104, 4.694091, 7.854757, 10.995541, ...
"""
import numpy as np
from scipy.linalg import eigh

FEM_ADVANCED_TOOL_SCHEMA = {
    "name": "fem_advanced_tool",
    "description": (
        "Analisis modal de vigas Euler-Bernoulli: frecuencias naturales y "
        "modos propios via autovalores generalizados K*phi=omega^2*M*phi "
        "con matriz de masa consistente. mode='modal_beam', "
        "support in ('pinned_pinned','cantilever'). Validado contra formulas "
        "analiticas de Blevins."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["modal_beam", "validate"]},
            "params": {"type": "object", "description": "Ver docstring de modal_beam."},
        },
        "required": ["mode"],
    },
}

_CANTILEVER_BETAL = [1.875104, 4.694091, 7.854757, 10.995541, 14.137168]


def _beam_ke(E, I, l):
    c = E * I / l**3
    return c * np.array([
        [12, 6*l, -12, 6*l],
        [6*l, 4*l**2, -6*l, 2*l**2],
        [-12, -6*l, 12, -6*l],
        [6*l, 2*l**2, -6*l, 4*l**2],
    ])


def _beam_me(rho, A, l):
    # matriz de masa consistente, viga Euler-Bernoulli (Cook et al.)
    c = rho * A * l / 420.0
    return c * np.array([
        [156, 22*l, 54, -13*l],
        [22*l, 4*l**2, 13*l, -3*l**2],
        [54, 13*l, 156, -22*l],
        [-13*l, -3*l**2, -22*l, 4*l**2],
    ])


def _assemble(E, I, rho, A, L, n_el):
    n_nodes = n_el + 1
    dof = 2 * n_nodes
    le = L / n_el
    K = np.zeros((dof, dof))
    M = np.zeros((dof, dof))
    ke = _beam_ke(E, I, le)
    me = _beam_me(rho, A, le)
    for e in range(n_el):
        idx = [2*e, 2*e+1, 2*e+2, 2*e+3]
        for i in range(4):
            for j in range(4):
                K[idx[i], idx[j]] += ke[i, j]
                M[idx[i], idx[j]] += me[i, j]
    return K, M, dof


def _apply_support(K, M, dof, support):
    if support == "pinned_pinned":
        # deflexion=0 en ambos extremos, giro libre
        fixed = [0, dof-2]
    elif support == "cantilever":
        # empotrado en nodo 0: deflexion y giro = 0
        fixed = [0, 1]
    else:
        raise ValueError(f"support no reconocido: {support}. Use pinned_pinned | cantilever")
    free = [d for d in range(dof) if d not in fixed]
    return K[np.ix_(free, free)], M[np.ix_(free, free)], free


def _modal_beam(E=200e9, I=8e-6, L=3.0, rho=7850.0, A=0.001,
                 support="pinned_pinned", n_el=20, n_modes=4):
    K, M, dof = _assemble(E, I, rho, A, L, n_el)
    Kred, Mred, free = _apply_support(K, M, dof, support)

    eigvals, eigvecs = eigh(Kred, Mred)
    eigvals = np.clip(eigvals, 0, None)  # numerico: modos rigidos ~0 pueden salir negativos por redondeo
    omega_numeric = np.sqrt(eigvals)[:n_modes]
    freq_numeric_hz = (omega_numeric / (2*np.pi)).tolist()

    if support == "pinned_pinned":
        betaL = [n*np.pi for n in range(1, n_modes+1)]
    elif support == "cantilever":
        betaL = _CANTILEVER_BETAL[:n_modes]

    omega_analytic = [
        (bl**2) * np.sqrt(E*I / (rho*A*L**4)) for bl in betaL
    ]
    freq_analytic_hz = [float(w/(2*np.pi)) for w in omega_analytic]

    rel_err_pct = [
        float(100*abs(fn - fa)/fa) for fn, fa in zip(freq_numeric_hz, freq_analytic_hz)
    ]

    return {
        "mode": "modal_beam",
        "support": support,
        "n_elements": n_el,
        "natural_frequencies_hz_numeric": [float(x) for x in freq_numeric_hz],
        "natural_frequencies_hz_analytic": freq_analytic_hz,
        "relative_error_pct": rel_err_pct,
    }


def _mode_validate():
    results = {}
    all_passed = True
    for support in ("pinned_pinned", "cantilever"):
        r = _modal_beam(support=support, n_el=20, n_modes=4)
        max_err = float(max(r["relative_error_pct"]))
        passed = bool(max_err < 1.0)  # <1% para los primeros 4 modos con 20 elementos
        results[support] = {
            "natural_frequencies_hz_numeric": r["natural_frequencies_hz_numeric"],
            "natural_frequencies_hz_analytic": r["natural_frequencies_hz_analytic"],
            "max_relative_error_pct": max_err,
            "passed": passed,
        }
        all_passed = all_passed and passed
    return {
        "mode": "validate",
        "results": results,
        "expected": "primeros 4 modos, viga E=200GPa I=8e-6 rho=7850 A=0.001 L=3, "
                    "error relativo < 1%% contra Blevins (pinned_pinned: n*pi; "
                    "cantilever: 1.875/4.694/7.855/10.996)",
        "validation_passed": bool(all_passed),
    }


def compute_fem_advanced(mode, params=None):
    params = params or {}
    if mode == "modal_beam":
        return _modal_beam(**params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(f"modo desconocido: {mode}. Use modal_beam | validate")


if __name__ == "__main__":
    import json
    r = compute_fem_advanced("validate")
    print(json.dumps(r, indent=2, ensure_ascii=False))
