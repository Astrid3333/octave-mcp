"""
finite_element_tool.py
Metodo de elementos finitos: barra axial, viga Euler-Bernoulli, cercha 2D.

Modos:
  - bar_1d       : barra bajo carga axial, N elementos, ensamblaje directo de rigidez
  - beam_bending : viga en voladizo Euler-Bernoulli, 2 GDL/nodo (deflexion + giro)
  - truss_2d     : cercha plana de barras articuladas, matriz de rigidez global

Validado contra:
  - u_tip = P*L/(A*E)               (barra uniforme, carga axial en el extremo)
  - delta_tip = P*L^3/(3*E*I)       (viga en voladizo, carga puntual en la punta)
  - equilibrio de nodos (suma de fuerzas = 0 en nodos libres, libro de texto)
"""
import numpy as np

FINITE_ELEMENT_TOOL_SCHEMA = {
    "name": "finite_element_tool",
    "description": (
        "Metodo de elementos finitos: barra axial (bar_1d), viga en voladizo "
        "Euler-Bernoulli (beam_bending), cercha plana articulada (truss_2d). "
        "Validado contra soluciones analiticas de libro de texto."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["bar_1d", "beam_bending", "truss_2d"]},
            "params": {"type": "object", "description": "Parametros especificos de cada modo, ver docstrings."},
        },
        "required": ["mode"],
    },
}


def _bar_1d(E, A, L, P, n_el=2):
    n_nodes = n_el + 1
    le = L / n_el
    ke = (E*A/le) * np.array([[1, -1], [-1, 1]])
    K = np.zeros((n_nodes, n_nodes))
    for e in range(n_el):
        K[e:e+2, e:e+2] += ke
    F = np.zeros(n_nodes)
    F[-1] = P
    Kred, Fred = K[1:, 1:], F[1:]
    u = np.linalg.solve(Kred, Fred)
    u_full = np.concatenate(([0.0], u))
    u_analytic = P*L/(A*E)
    return {
        "mode": "bar_1d",
        "nodal_displacements": u_full.tolist(),
        "tip_displacement_fem": float(u_full[-1]),
        "tip_displacement_analytic": u_analytic,
        "relative_error_pct": 100*abs(u_full[-1]-u_analytic)/u_analytic,
    }


def _beam_ke(E, I, l):
    c = E*I/l**3
    return c*np.array([
        [12, 6*l, -12, 6*l],
        [6*l, 4*l**2, -6*l, 2*l**2],
        [-12, -6*l, 12, -6*l],
        [6*l, 2*l**2, -6*l, 4*l**2],
    ])


def _beam_bending(E, I, L, P, n_el=4):
    n_nodes = n_el + 1
    dof = 2*n_nodes
    le = L/n_el
    K = np.zeros((dof, dof))
    ke = _beam_ke(E, I, le)
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
    delta_analytic = P*L**3/(3*E*I)
    return {
        "mode": "beam_bending",
        "nodal_deflections": deflections.tolist(),
        "tip_deflection_fem": float(deflections[-1]),
        "tip_deflection_analytic": delta_analytic,
        "relative_error_pct": 100*abs(deflections[-1]-delta_analytic)/delta_analytic,
    }


def _truss_2d(nodes, elements, E, A, loads, fixed_dofs):
    n_nodes = len(nodes)
    dof = 2*n_nodes
    K = np.zeros((dof, dof))
    for (ni, nj) in elements:
        xi, yi = nodes[ni]
        xj, yj = nodes[nj]
        Le = np.hypot(xj-xi, yj-yi)
        c, s = (xj-xi)/Le, (yj-yi)/Le
        k = (E*A/Le) * np.array([
            [c*c, c*s, -c*c, -c*s],
            [c*s, s*s, -c*s, -s*s],
            [-c*c, -c*s, c*c, c*s],
            [-c*s, -s*s, c*s, s*s],
        ])
        idx = [2*ni, 2*ni+1, 2*nj, 2*nj+1]
        for a in range(4):
            for b in range(4):
                K[idx[a], idx[b]] += k[a, b]
    F = np.zeros(dof)
    for d, val in loads.items():
        F[int(d)] = val
    free = [d for d in range(dof) if d not in fixed_dofs]
    Kred, Fred = K[np.ix_(free, free)], F[free]
    u = np.linalg.solve(Kred, Fred)
    u_full = np.zeros(dof)
    for i, d in enumerate(free):
        u_full[d] = u[i]
    residual = K @ u_full - F
    return {
        "mode": "truss_2d",
        "nodal_displacements": u_full.reshape(-1, 2).tolist(),
        "equilibrium_residual_max": float(np.max(np.abs(residual[free]))),
    }


def compute_finite_element(mode, params=None):
    params = params or {}
    if mode == "bar_1d":
        return _bar_1d(**params)
    elif mode == "beam_bending":
        return _beam_bending(**params)
    elif mode == "truss_2d":
        return _truss_2d(**params)
    else:
        raise ValueError(f"modo desconocido: {mode}. Use bar_1d | beam_bending | truss_2d")


if __name__ == "__main__":
    r1 = compute_finite_element("bar_1d", {"E": 200e9, "A": 0.001, "L": 2.0, "P": 1000.0})
    print("bar_1d err%% =", r1["relative_error_pct"])
    r2 = compute_finite_element("beam_bending", {"E": 200e9, "I": 8e-6, "L": 3.0, "P": 500.0})
    print("beam_bending err%% =", r2["relative_error_pct"])
    r3 = compute_finite_element("truss_2d", {
        "nodes": [[0, 0], [1, 0], [0.5, 0.866]],
        "elements": [[0, 1], [1, 2], [0, 2]],
        "E": 200e9, "A": 0.0005,
        "loads": {5: -1000.0},
        "fixed_dofs": [0, 1, 2, 3],
    })
    print("truss_2d equilibrium residual max =", r3["equilibrium_residual_max"])
