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
        "FEM avanzado sobre vigas Euler-Bernoulli/Timoshenko. "
        "mode='modal_beam': frecuencias naturales y modos propios via "
        "autovalores generalizados K*phi=omega^2*M*phi (masa consistente), "
        "validado contra Blevins. mode='buckling_linear': carga critica de "
        "pandeo via autovalores generalizados K*phi=Pcr*Kg*phi (rigidez "
        "geometrica consistente), validado contra Euler Pcr=pi^2EI/L^2 "
        "(pinned_pinned) y pi^2EI/(4L^2) (cantilever). "
        "mode='timoshenko_beam': deflexion de voladizo con deformacion por "
        "corte (matriz de Przemieniecki), validado contra "
        "delta=PL^3/(3EI)+PL/(G*As). support in ('pinned_pinned','cantilever') "
        "para modal_beam y buckling_linear."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["modal_beam", "buckling_linear", "timoshenko_beam", "validate"]},
            "params": {"type": "object", "description": "Ver docstrings de cada modo."},
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


def _beam_kg_unit(l):
    # matriz de rigidez geometrica consistente, viga Euler-Bernoulli, para P=1
    # (compresion positiva reduce rigidez). Cook, Malkus & Plesha.
    c = 1.0 / (30.0 * l)
    return c * np.array([
        [36, 3*l, -36, 3*l],
        [3*l, 4*l**2, -3*l, -l**2],
        [-36, -3*l, 36, -3*l],
        [3*l, -l**2, -3*l, 4*l**2],
    ])


def _assemble_kg(L, n_el):
    n_nodes = n_el + 1
    dof = 2 * n_nodes
    le = L / n_el
    Kg = np.zeros((dof, dof))
    kge = _beam_kg_unit(le)
    for e in range(n_el):
        idx = [2*e, 2*e+1, 2*e+2, 2*e+3]
        for i in range(4):
            for j in range(4):
                Kg[idx[i], idx[j]] += kge[i, j]
    return Kg


def _buckling_linear(E=200e9, I=8e-6, L=3.0, support="pinned_pinned", n_el=20):
    n_nodes = n_el + 1
    dof = 2 * n_nodes
    le = L / n_el
    K = np.zeros((dof, dof))
    ke = _beam_ke(E, I, le)
    for e in range(n_el):
        idx = [2*e, 2*e+1, 2*e+2, 2*e+3]
        for i in range(4):
            for j in range(4):
                K[idx[i], idx[j]] += ke[i, j]
    Kg_unit = _assemble_kg(L, n_el)

    if support == "pinned_pinned":
        fixed = [0, dof-2]
    elif support == "cantilever":
        fixed = [0, 1]
    else:
        raise ValueError(f"support no reconocido: {support}. Use pinned_pinned | cantilever")
    free = [d for d in range(dof) if d not in fixed]

    Kred = K[np.ix_(free, free)]
    Kg_red = Kg_unit[np.ix_(free, free)]

    # K*phi = Pcr * Kg*phi -> autovalores generalizados
    eigvals, eigvecs = eigh(Kred, Kg_red)
    eigvals = eigvals[eigvals > 0]  # descartar espurios no positivos
    Pcr_numeric = float(np.min(eigvals))

    if support == "pinned_pinned":
        Pcr_analytic = float(np.pi**2 * E * I / L**2)
    elif support == "cantilever":
        Pcr_analytic = float(np.pi**2 * E * I / (4 * L**2))

    rel_err_pct = 100 * abs(Pcr_numeric - Pcr_analytic) / Pcr_analytic

    return {
        "mode": "buckling_linear",
        "support": support,
        "n_elements": n_el,
        "Pcr_numeric_N": Pcr_numeric,
        "Pcr_analytic_N": Pcr_analytic,
        "relative_error_pct": rel_err_pct,
    }


def _timoshenko_ke(E, I, G, As, l):
    phi = 12.0 * E * I / (G * As * l**2)
    c = E * I / ((1 + phi) * l**3)
    return c * np.array([
        [12, 6*l, -12, 6*l],
        [6*l, (4+phi)*l**2, -6*l, (2-phi)*l**2],
        [-12, -6*l, 12, -6*l],
        [6*l, (2-phi)*l**2, -6*l, (4+phi)*l**2],
    ]), phi


def _timoshenko_beam(E=200e9, I=8e-6, L=3.0, P=500.0, G=77e9,
                      shear_area_factor=0.833, A=0.001, n_el=4):
    As = shear_area_factor * A  # area de corte efectiva (5/6 rectangular tipico)
    n_nodes = n_el + 1
    dof = 2 * n_nodes
    le = L / n_el
    K = np.zeros((dof, dof))
    ke, phi = _timoshenko_ke(E, I, G, As, le)
    for e in range(n_el):
        idx = [2*e, 2*e+1, 2*e+2, 2*e+3]
        for i in range(4):
            for j in range(4):
                K[idx[i], idx[j]] += ke[i, j]
    F = np.zeros(dof)
    F[-2] = P
    free = list(range(2, dof))
    Kred, Fred = K[np.ix_(free, free)], F[free]
    u = np.linalg.solve(Kred, Fred)
    u_full = np.concatenate(([0.0, 0.0], u))
    deflections = u_full[0::2]

    delta_analytic = P*L**3/(3*E*I) + P*L/(G*As)
    tip_fem = float(deflections[-1])
    rel_err_pct = 100 * abs(tip_fem - delta_analytic) / delta_analytic

    return {
        "mode": "timoshenko_beam",
        "n_elements": n_el,
        "shear_parameter_phi": float(phi),
        "shear_area_m2": As,
        "tip_deflection_fem": tip_fem,
        "tip_deflection_analytic": delta_analytic,
        "tip_deflection_euler_bernoulli_only": float(P*L**3/(3*E*I)),
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
    buckling_results = {}
    for support in ("pinned_pinned", "cantilever"):
        rb = _buckling_linear(support=support, n_el=20)
        passed_b = bool(rb["relative_error_pct"] < 1.0)
        buckling_results[support] = {
            "Pcr_numeric_N": rb["Pcr_numeric_N"],
            "Pcr_analytic_N": rb["Pcr_analytic_N"],
            "relative_error_pct": rb["relative_error_pct"],
            "passed": passed_b,
        }
        all_passed = all_passed and passed_b

    rt = _timoshenko_beam(n_el=4)
    passed_t = bool(rt["relative_error_pct"] < 1.0)
    timoshenko_result = {
        "tip_deflection_fem": rt["tip_deflection_fem"],
        "tip_deflection_analytic": rt["tip_deflection_analytic"],
        "relative_error_pct": rt["relative_error_pct"],
        "passed": passed_t,
    }
    all_passed = all_passed and passed_t

    return {
        "mode": "validate",
        "modal_results": results,
        "buckling_results": buckling_results,
        "timoshenko_result": timoshenko_result,
        "expected": "modal: primeros 4 modos error <1%% vs Blevins. buckling: "
                    "Pcr error <1%% vs Euler (pi^2EI/L^2 pinned, pi^2EI/(4L^2) "
                    "cantilever). timoshenko: deflexion voladizo error <1%% vs "
                    "PL^3/(3EI)+PL/(G*As)",
        "validation_passed": bool(all_passed),
    }


def compute_fem_advanced(mode, params=None):
    params = params or {}
    if mode == "modal_beam":
        return _modal_beam(**params)
    elif mode == "buckling_linear":
        return _buckling_linear(**params)
    elif mode == "timoshenko_beam":
        return _timoshenko_beam(**params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(f"modo desconocido: {mode}. Use modal_beam | buckling_linear | timoshenko_beam | validate")


if __name__ == "__main__":
    import json
    r = compute_fem_advanced("validate")
    print(json.dumps(r, indent=2, ensure_ascii=False))

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("fem_advanced_tool", FEM_ADVANCED_TOOL_SCHEMA, lambda args, _f=compute_fem_advanced: _f(**args))
