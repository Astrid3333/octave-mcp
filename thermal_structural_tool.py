"""
thermal_structural_tool.py
Acoplamiento termico-estructural: dilatacion termica y tensiones inducidas
por gradiente/uniforme de temperatura, en barra 1D y placa CST plane stress.

Modos:
  - thermal_bar    : barra empotrada en ambos extremos, deltaT uniforme,
                     tension inducida = -E*alpha*deltaT (formula de libro,
                     dilatacion totalmente impedida)
  - thermal_plate  : placa rectangular (malla CST, ej. de distmesh_tool)
                     totalmente empotrada en el borde, deltaT uniforme.
                     Solucion exacta: desplazamiento cero en todo el dominio,
                     tension equibiaxial sigma_xx=sigma_yy=-E*alpha*deltaT/(1-nu),
                     tau_xy=0 (Timoshenko & Goodier, placa clampeada bajo
                     dilatacion termica uniforme)
  - validate       : corre ambos casos y chequea contra formula analitica
"""
import numpy as np


THERMAL_STRUCTURAL_TOOL_SCHEMA = {
    "name": "thermal_structural_tool",
    "description": (
        "Acoplamiento termico-estructural: tensiones inducidas por deltaT. "
        "mode='thermal_bar': barra empotrada ambos extremos, deltaT uniforme, "
        "valida contra sigma=-E*alpha*deltaT. mode='thermal_plate': placa CST "
        "totalmente empotrada, deltaT uniforme, valida contra solucion exacta "
        "equibiaxial sigma=-E*alpha*deltaT/(1-nu). mode='validate' corre ambos."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["thermal_bar", "thermal_plate", "validate"]},
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


# ---------------- thermal_bar ----------------

def _thermal_bar(E=200e9, A=0.001, L=2.0, alpha=12e-6, deltaT=50.0, n_el=4):
    n_nodes = n_el + 1
    le = L / n_el
    K = np.zeros((n_nodes, n_nodes))
    ke = (E * A / le) * np.array([[1, -1], [-1, 1]])
    for e in range(n_el):
        K[e:e+2, e:e+2] += ke

    # fuerza termica nodal equivalente por elemento: E*A*alpha*deltaT*[-1,1]
    F_th = np.zeros(n_nodes)
    fe = E * A * alpha * deltaT * np.array([-1.0, 1.0])
    for e in range(n_el):
        F_th[e:e+2] += fe

    fixed = [0, n_nodes - 1]
    free = [d for d in range(n_nodes) if d not in fixed]
    Kred, Fred = K[np.ix_(free, free)], F_th[free]
    u_free = np.linalg.solve(Kred, Fred) if free else np.array([])
    u_full = np.zeros(n_nodes)
    for i, d in enumerate(free):
        u_full[d] = u_free[i]

    # tension por elemento: sigma = E*(du/dx - alpha*deltaT)
    stresses = []
    for e in range(n_el):
        du_dx = (u_full[e+1] - u_full[e]) / le
        sigma = E * (du_dx - alpha * deltaT)
        stresses.append(float(sigma))

    sigma_analytic = -E * alpha * deltaT
    max_err_pct = 100 * max(abs(s - sigma_analytic) for s in stresses) / abs(sigma_analytic)

    return {
        "mode": "thermal_bar",
        "nodal_displacements": u_full.tolist(),
        "element_stresses_Pa": stresses,
        "sigma_analytic_Pa": sigma_analytic,
        "max_relative_error_pct": max_err_pct,
    }


# ---------------- thermal_plate (reusa CST de plane_stress_tool) ----------------

def _plane_stress_D(E, nu):
    c = E / (1 - nu**2)
    return c * np.array([[1, nu, 0], [nu, 1, 0], [0, 0, (1 - nu) / 2]])


def _cst_B_area(coords):
    x1, y1 = coords[0]; x2, y2 = coords[1]; x3, y3 = coords[2]
    A2 = (x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)
    area = A2 / 2.0
    if area <= 0:
        raise ValueError("Triangulo con area no positiva; reordenar antihorario.")
    b1, b2, b3 = y2 - y3, y3 - y1, y1 - y2
    c1, c2, c3 = x3 - x2, x1 - x3, x2 - x1
    B = (1.0 / A2) * np.array([
        [b1, 0, b2, 0, b3, 0],
        [0, c1, 0, c2, 0, c3],
        [c1, b1, c2, b2, c3, b3],
    ])
    return B, area


def _build_rect_mesh(nx=3, ny=2, Lx=2.0, Ly=1.0, irregular=True, seed=42):
    rng = np.random.default_rng(seed)
    xs = np.linspace(0, Lx, nx + 1)
    ys = np.linspace(0, Ly, ny + 1)
    nodes = []
    node_id = {}
    boundary_nodes = []
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            xp, yp = x, y
            is_boundary = (i == 0 or i == nx or j == 0 or j == ny)
            if irregular and not is_boundary:
                dx = 0.3 * (Lx / nx); dy = 0.3 * (Ly / ny)
                xp += rng.uniform(-dx, dx); yp += rng.uniform(-dy, dy)
            node_id[(i, j)] = len(nodes)
            nodes.append([xp, yp])
            if is_boundary:
                boundary_nodes.append(node_id[(i, j)])
    triangles = []
    for j in range(ny):
        for i in range(nx):
            n00, n10 = node_id[(i, j)], node_id[(i+1, j)]
            n11, n01 = node_id[(i+1, j+1)], node_id[(i, j+1)]
            triangles.append((n00, n10, n11))
            triangles.append((n00, n11, n01))
    return np.array(nodes), triangles, boundary_nodes


def _thermal_plate(E=200e9, nu=0.3, thickness=0.01, alpha=12e-6, deltaT=40.0,
                    nx=3, ny=2, Lx=2.0, Ly=1.0, irregular=True, seed=42):
    nodes, triangles, boundary_nodes = _build_rect_mesh(nx, ny, Lx, Ly, irregular, seed)
    n_nodes = len(nodes)
    dof = 2 * n_nodes
    D = _plane_stress_D(E, nu)
    eps_th = alpha * deltaT * np.array([1.0, 1.0, 0.0])

    K = np.zeros((dof, dof))
    F_th = np.zeros(dof)
    elem_data = []
    for tri in triangles:
        coords = nodes[list(tri)]
        B, area = _cst_B_area(coords)
        ke = thickness * area * (B.T @ D @ B)
        fe_th = thickness * area * (B.T @ D @ eps_th)
        idx = []
        for n in tri:
            idx += [2*n, 2*n+1]
        for i in range(6):
            F_th[idx[i]] += fe_th[i]
            for j in range(6):
                K[idx[i], idx[j]] += ke[i, j]
        elem_data.append((B, area, idx))

    fixed_dofs = []
    for n in boundary_nodes:
        fixed_dofs += [2*n, 2*n+1]
    free = [d for d in range(dof) if d not in fixed_dofs]
    Kred, Fred = K[np.ix_(free, free)], F_th[free]
    u_free = np.linalg.solve(Kred, Fred) if free else np.array([])
    u_full = np.zeros(dof)
    for i, d in enumerate(free):
        u_full[d] = u_free[i]

    stresses = []
    for B, area, idx in elem_data:
        ue = u_full[idx]
        strain_total = B @ ue
        stress = D @ (strain_total - eps_th)
        stresses.append({"sigma_xx": float(stress[0]), "sigma_yy": float(stress[1]),
                          "tau_xy": float(stress[2])})

    sigma_analytic = -E * alpha * deltaT / (1 - nu)
    sxx = [s["sigma_xx"] for s in stresses]
    syy = [s["sigma_yy"] for s in stresses]
    txy = [s["tau_xy"] for s in stresses]
    max_err_sxx_pct = 100 * max(abs(s - sigma_analytic) for s in sxx) / abs(sigma_analytic)
    max_err_syy_pct = 100 * max(abs(s - sigma_analytic) for s in syy) / abs(sigma_analytic)
    max_abs_txy = max(abs(t) for t in txy)
    max_abs_u = float(np.max(np.abs(u_full)))

    return {
        "mode": "thermal_plate",
        "mesh": {"n_nodes": n_nodes, "n_triangles": len(triangles), "irregular": irregular},
        "sigma_analytic_equibiaxial_Pa": sigma_analytic,
        "max_sigma_xx_relative_error_pct": max_err_sxx_pct,
        "max_sigma_yy_relative_error_pct": max_err_syy_pct,
        "max_tau_xy_abs_Pa": max_abs_txy,
        "max_abs_displacement_m": max_abs_u,
    }


def _mode_validate():
    r_bar = _thermal_bar()
    r_plate = _thermal_plate()
    checks = {
        "bar_stress_matches_analytic": bool(r_bar["max_relative_error_pct"] < 1e-6),
        "plate_sigma_xx_matches_analytic": bool(r_plate["max_sigma_xx_relative_error_pct"] < 1e-6),
        "plate_sigma_yy_matches_analytic": bool(r_plate["max_sigma_yy_relative_error_pct"] < 1e-6),
        "plate_tau_xy_zero": bool(r_plate["max_tau_xy_abs_Pa"] < 1e-3),
        "plate_displacement_zero": bool(r_plate["max_abs_displacement_m"] < 1e-9),
    }
    return {
        "mode": "validate",
        "thermal_bar_result": r_bar,
        "thermal_plate_result": r_plate,
        "checks": checks,
        "expected": "bar empotrada: sigma=-E*alpha*deltaT (dilatacion totalmente impedida). "
                    "placa clampeada: desplazamiento cero en todo el dominio, tension "
                    "equibiaxial sigma=-E*alpha*deltaT/(1-nu), tau=0 (Timoshenko & Goodier).",
        "validation_passed": bool(all(checks.values())),
    }


def compute_thermal_structural(mode, params=None):
    params = params or {}
    if mode == "thermal_bar":
        return _thermal_bar(**params)
    elif mode == "thermal_plate":
        return _thermal_plate(**params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(f"modo desconocido: {mode}")


if __name__ == "__main__":
    import json
    print(json.dumps(compute_thermal_structural("validate"), indent=2, ensure_ascii=False))
