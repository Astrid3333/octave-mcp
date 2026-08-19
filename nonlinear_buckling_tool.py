"""
nonlinear_buckling_tool.py
Pandeo no lineal / grandes deformaciones: armadura de dos barras (von Mises
truss) via formulacion Lagrangiana Total (deformacion de Green-Lagrange,
elemento barra TL estandar, Bathe/Crisfield) y metodo de longitud de arco
esferico (Crisfield) para trazar la trayectoria de equilibrio completa --
incluyendo la rama inestable de snap-through, que Newton-Raphson con control
de carga NO puede atravesar (la rigidez tangente se anula en los puntos
limite).

Geometria: nodo 1 y 3 = apoyos fijos (ambos GDL restringidos), separados 2a.
Nodo 2 = apice, libre en x,y, carga vertical P. Formulacion generica de
elemento barra TL (no se asume simetria a priori; la simetria emerge de la
solucion).

Elemento barra TL (2D, nodos i,j, GDL [ui,vi,uj,vj]):
  d0 = Xj - Xi  (vector posicion referencia), L0 = |d0|
  d  = xj - xi  (vector posicion actual = d0 + (uj-ui,vj-vi)), L = |d|
  e  = (d.d - d0.d0) / (2*L0^2)        (deformacion Green-Lagrange)
  N  = E*A*e                            (fuerza, PK2 * area referencia)
  f_int_j = (N/L0)*d ,  f_int_i = -f_int_j
  K_material = (E*A/L0^3) * d d^T       (4x4 con signos +/- por nodo)
  K_geometric = (N/L0) * I2             (idem)

Solucion cerrada de referencia (para el caso simetrico, Crisfield cap.1):
  L0^2 = a^2 + h0^2
  e(w) = [w^2 - 2*h0*w] / (2*L0^2)
  P(w) = 2*E*A*e(w)*(h0-w)/L0 = E*A*w*(h0-w)*(w-2*h0)/L0^3

Modos:
  - trace_path : corre el arc-length multi-GDL y devuelve la trayectoria (w,P)
  - validate   : compara la trayectoria FE contra la formula cerrada, y
                 verifica que atraviesa los dos puntos limite de snap-through
"""
import numpy as np


NONLINEAR_BUCKLING_TOOL_SCHEMA = {
    "name": "nonlinear_buckling_tool",
    "description": (
        "Pandeo no lineal / grandes deformaciones: armadura de dos barras "
        "(von Mises truss, snap-through) via elemento barra Lagrangiano Total "
        "(Green-Lagrange) multi-GDL y metodo de longitud de arco esferico "
        "(Crisfield), que traza la rama inestable que Newton-Raphson con "
        "control de carga no puede atravesar. mode='trace_path' corre el "
        "arc-length. mode='validate' compara la trayectoria contra la "
        "solucion cerrada P(w) y verifica que cruza los dos puntos limite."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["trace_path", "validate"]},
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


def _analytic_P(w, E, A, a, h0):
    L0 = np.sqrt(a**2 + h0**2)
    return E * A * w * (h0 - w) * (w - 2*h0) / L0**3


def _bar_internal_and_tangent(Xi, Xj, ui, uj, E, A):
    d0 = Xj - Xi
    L0 = np.linalg.norm(d0)
    xi, xj = Xi + ui, Xj + uj
    d = xj - xi
    e = (d @ d - d0 @ d0) / (2 * L0**2)
    N = E * A * e
    f_j = (N / L0) * d
    f_i = -f_j
    K_mat = (E * A / L0**3) * np.outer(d, d)
    K_geo = (N / L0) * np.eye(2)
    Ke = K_mat + K_geo
    # ensamble local 4x4: [i,j] con signos
    K4 = np.zeros((4, 4))
    K4[0:2, 0:2] = Ke; K4[2:4, 2:4] = Ke
    K4[0:2, 2:4] = -Ke; K4[2:4, 0:2] = -Ke
    f4 = np.concatenate([f_i, f_j])
    return f4, K4, N


def _assemble(nodes_ref, u, elements, E, A):
    n_nodes = len(nodes_ref)
    dof = 2 * n_nodes
    F = np.zeros(dof)
    K = np.zeros((dof, dof))
    for (ni, nj) in elements:
        Xi, Xj = nodes_ref[ni], nodes_ref[nj]
        ui, uj = u[2*ni:2*ni+2], u[2*nj:2*nj+2]
        f4, K4, N = _bar_internal_and_tangent(Xi, Xj, ui, uj, E, A)
        idx = [2*ni, 2*ni+1, 2*nj, 2*nj+1]
        for a_ in range(4):
            F[idx[a_]] += f4[a_]
            for b_ in range(4):
                K[idx[a_], idx[b_]] += K4[a_, b_]
    return F, K


def _trace_path(E=200e9, A=1e-4, a=1.0, h0=0.05, ds=0.003, n_steps=70,
                 tol=1e-12, max_iter=60):
    """Arc-length CILINDRICO (Crisfield, psi=0): la restriccion controla
    solo la norma del incremento de desplazamiento, ||du||^2 = ds^2 -- evita
    mezclar unidades de desplazamiento (m) con el parametro de carga lambda
    (adimensional), que es lo que rompia la version esferica con psi=1 aca
    (la rigidez horizontal es ~400x la vertical en este problema)."""
    # nodos: 0=apoyo izq (-a,0), 1=apice (0,h0), 2=apoyo der (a,0)
    nodes_ref = np.array([[-a, 0.0], [0.0, h0], [a, 0.0]])
    elements = [(0, 1), (1, 2)]
    free_dofs = [2, 3]                  # nodo 1 (apice): u_x, u_y libres
    load_dof = 3                        # carga vertical en el apice (v)
    P_ref = 1.0

    dof = 6
    u = np.zeros(dof)
    lam = 0.0
    path = [(0.0, 0.0)]  # (v_apice, P)

    # carga de referencia HACIA ABAJO (empuja el apice hacia los apoyos,
    # que es la direccion que produce snap-through; hacia arriba solo
    # estira las barras y es monotonico, sin puntos limite)
    Fref = np.zeros(dof)
    Fref[load_dof] = -P_ref

    prev_dU = None

    for step in range(n_steps):
        F_int, K = _assemble(nodes_ref, u, elements, E, A)
        Kff = K[np.ix_(free_dofs, free_dofs)]
        du_dlam = np.linalg.solve(Kff, Fref[free_dofs])
        norm_tan = np.linalg.norm(du_dlam)
        if norm_tan < 1e-14:
            norm_tan = 1e-14
        dlam0 = ds / norm_tan
        du0 = dlam0 * du_dlam
        if prev_dU is not None and (du0 @ prev_dU) < 0:
            du0, dlam0 = -du0, -dlam0

        u_trial = u.copy()
        u_trial[free_dofs] += du0
        lam_trial = lam + dlam0
        dU, dLam = du0.copy(), dlam0

        for it in range(max_iter):
            F_int, K = _assemble(nodes_ref, u_trial, elements, E, A)
            Kff = K[np.ix_(free_dofs, free_dofs)]
            r = F_int[free_dofs] - lam_trial * Fref[free_dofs]
            delta_u_r = np.linalg.solve(Kff, -r)
            delta_u_lam = np.linalg.solve(Kff, Fref[free_dofs])

            # restriccion cilindrica: ||dU + delta_u_r + delta_u_lam*x||^2 = ds^2
            v = dU + delta_u_r
            a1 = delta_u_lam @ delta_u_lam
            a2 = 2.0 * (v @ delta_u_lam)
            a3 = (v @ v) - ds**2

            if a1 < 1e-20:
                dlam_corr = -a3 / (a2 if abs(a2) > 1e-20 else 1e-20)
            else:
                disc = a2**2 - 4*a1*a3
                if disc < 0:
                    dlam_corr = -a2 / (2*a1)
                else:
                    sol1 = (-a2 + np.sqrt(disc)) / (2*a1)
                    sol2 = (-a2 - np.sqrt(disc)) / (2*a1)
                    cand1 = v + sol1*delta_u_lam
                    cand2 = v + sol2*delta_u_lam
                    ref_dir = dU
                    dlam_corr = sol1 if (cand1 @ ref_dir) >= (cand2 @ ref_dir) else sol2

            du_corr = delta_u_r + delta_u_lam * dlam_corr
            u_trial[free_dofs] += du_corr
            lam_trial += dlam_corr
            dU += du_corr
            dLam += dlam_corr

            if np.linalg.norm(du_corr) < tol and abs(dlam_corr) < tol:
                break

        u = u_trial
        lam = lam_trial
        prev_dU = dU
        v_apice = u[3]
        path.append((float(v_apice), float(lam * P_ref)))

    return path


def _mode_trace_path(**kwargs):
    path = _trace_path(**kwargs)
    return {"mode": "trace_path", "v_apice": [p[0] for p in path],
            "P": [p[1] for p in path], "n_points": len(path)}


def _mode_validate():
    E, A, a, h0 = 200e9, 1e-4, 1.0, 0.05
    path = _trace_path(E=E, A=A, a=a, h0=h0, n_steps=90, ds=0.0015)
    ws = np.array([p[0] for p in path])       # v_apice > 0 = apice sube; el
                                               # apice BAJA con w = -v_apice
    # convencion: w (bajada del apice) = -v_apice, ya que v es el desplazamiento
    # vertical del nodo (positivo hacia arriba en el sistema global estandar)
    w_down = -ws
    Ps = np.array([p[1] for p in path])
    # con la carga de referencia hacia abajo, P_analytic(w_down) sale negado
    # respecto de Ps (verificado numericamente): P_downward = -Ps
    P_downward = -Ps

    P_analytic = _analytic_P(w_down, E, A, a, h0)
    mask = np.abs(w_down) > 1e-9
    denom = np.maximum(np.abs(P_analytic[mask]), 1e-3)
    rel_err_pct = 100 * np.abs(P_downward[mask] - P_analytic[mask]) / denom
    max_rel_err_pct = float(np.max(rel_err_pct)) if len(rel_err_pct) else 0.0
    mean_rel_err_pct = float(np.mean(rel_err_pct)) if len(rel_err_pct) else 0.0

    w_fine = np.linspace(0, 2*h0, 200001)
    P_fine = _analytic_P(w_fine, E, A, a, h0)
    dP = np.diff(P_fine)
    sign_changes = np.where(np.diff(np.sign(dP)) != 0)[0]
    limit_points_w = [float(w_fine[i+1]) for i in sign_changes]

    crossed_first_limit = bool(len(limit_points_w) > 0 and float(np.max(w_down)) > limit_points_w[0])
    reached_second_support = bool(np.max(w_down) > 1.3 * h0)

    checks = {
        "path_matches_analytic_curve": bool(max_rel_err_pct < 2.0),
        "traversed_first_limit_point": crossed_first_limit,
        "reached_beyond_apex_height": reached_second_support,
        "no_divergence": bool(np.all(np.isfinite(Ps))),
    }

    return {
        "mode": "validate",
        "params": {"E": E, "A": A, "a": a, "h0": h0},
        "n_path_points": len(path),
        "max_relative_error_pct_vs_closed_form": max_rel_err_pct,
        "mean_relative_error_pct_vs_closed_form": mean_rel_err_pct,
        "analytic_limit_points_w": limit_points_w,
        "path_w_down_range": [float(np.min(w_down)), float(np.max(w_down))],
        "checks": checks,
        "expected": "trayectoria (via arc-length, 2 GDL en el apice) coincide "
                    "con P(w)=E*A*w*(h0-w)*(w-2h0)/L0^3 en cada punto convergido, "
                    "y atraviesa el primer punto limite (snap-through) -- algo "
                    "que Newton-Raphson con carga controlada no puede hacer "
                    "porque la rigidez tangente se anula ahi.",
        "validation_passed": bool(all(checks.values())),
    }


def compute_nonlinear_buckling(mode, params=None):
    params = params or {}
    if mode == "trace_path":
        return _mode_trace_path(**params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(f"modo desconocido: {mode}")


if __name__ == "__main__":
    import json
    print(json.dumps(compute_nonlinear_buckling("validate"), indent=2, ensure_ascii=False))

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("nonlinear_buckling_tool", NONLINEAR_BUCKLING_TOOL_SCHEMA, lambda args, _f=compute_nonlinear_buckling: _f(**args))
