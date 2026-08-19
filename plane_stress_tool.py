"""
plane_stress_tool.py
Elementos finitos 2D continuos: elemento triangular de deformacion constante
(CST, Constant Strain Triangle) para estado plano de tensiones (plane stress).

Modos:
  - patch_test : carga una malla (nodos + triangulos, tipicamente generada por
                 distmesh_tool) o una malla rectangular preset, aplica traccion
                 uniforme en un borde, empotra el borde opuesto, y resuelve
                 desplazamientos + tensiones por elemento.
  - solve      : mismo solver, para uso general con geometria/cargas propias
                 (no necesariamente el patch test).
  - validate   : corre el patch test clasico y verifica que la tension
                 recuperada en TODOS los elementos sea exactamente uniforme
                 (propiedad exacta del CST bajo carga uniforme, sin importar
                 la irregularidad de la malla -- es la prueba estandar de
                 correctitud de un codigo FEM plano, Cook Malkus & Plesha).

Convencion: 2 GDL por nodo (u_x, u_y). D de plane stress:
  D = E/(1-nu^2) * [[1, nu, 0], [nu, 1, 0], [0, 0, (1-nu)/2]]

NOTA (fix): el borde empotrado del patch test se restringe con u_x=0 en TODOS
sus nodos, pero u_y=0 SOLO en un nodo (para eliminar el modo de cuerpo rigido).
Fijar u_y=0 en todo el borde impide la contraccion de Poisson lateral
(u_y = -nu*sigma*y/E, que no es cero salvo en y=0) y sobre-restringe el
modelo, induciendo sigma_yy y tau_xy espurios y una sigma_xx no uniforme
-- aunque el equilibrio global siga satisfecho. Con el fix el patch test
da error ~1e-13% incluso en malla irregular.
"""
import numpy as np


PLANE_STRESS_TOOL_SCHEMA = {
    "name": "plane_stress_tool",
    "description": (
        "FEM 2D continuo: elemento triangular CST (Constant Strain Triangle) "
        "para estado plano de tensiones. mode='solve' resuelve una malla "
        "(nodos+triangulos, ej. de distmesh_tool) con cargas y apoyos propios. "
        "mode='patch_test' corre el patch test clasico (traccion uniforme, "
        "malla rectangular preset o propia) -- el CST da tension exactamente "
        "uniforme sin importar irregularidad de malla, es la validacion "
        "estandar de un codigo FEM plano. mode='validate' corre patch_test "
        "y chequea uniformidad."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["solve", "patch_test", "validate"]},
            "params": {"type": "object", "description": "Ver docstrings de cada modo."},
        },
        "required": ["mode"],
    },
}


def _plane_stress_D(E, nu):
    c = E / (1 - nu**2)
    return c * np.array([
        [1, nu, 0],
        [nu, 1, 0],
        [0, 0, (1 - nu) / 2],
    ])


def _cst_B_area(coords):
    # coords: 3x2 array [[x1,y1],[x2,y2],[x3,y3]]
    x1, y1 = coords[0]
    x2, y2 = coords[1]
    x3, y3 = coords[2]
    A2 = (x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)  # 2*area con signo
    area = A2 / 2.0
    if area <= 0:
        raise ValueError(
            "Triangulo con area no positiva (orden de nodos horario o degenerado). "
            "Reordenar nodos en sentido antihorario."
        )
    b1, b2, b3 = y2 - y3, y3 - y1, y1 - y2
    c1, c2, c3 = x3 - x2, x1 - x3, x2 - x1
    B = (1.0 / A2) * np.array([
        [b1, 0, b2, 0, b3, 0],
        [0, c1, 0, c2, 0, c3],
        [c1, b1, c2, b2, c3, b3],
    ])
    return B, area


def _assemble_plane_stress(nodes, triangles, E, nu, thickness):
    n_nodes = len(nodes)
    dof = 2 * n_nodes
    K = np.zeros((dof, dof))
    D = _plane_stress_D(E, nu)
    elem_data = []
    for tri in triangles:
        coords = nodes[list(tri)]
        B, area = _cst_B_area(coords)
        ke = thickness * area * (B.T @ D @ B)
        idx = []
        for n in tri:
            idx += [2*n, 2*n+1]
        for i in range(6):
            for j in range(6):
                K[idx[i], idx[j]] += ke[i, j]
        elem_data.append((B, area, idx))
    return K, dof, D, elem_data


def _solve(nodes, triangles, E=200e9, nu=0.3, thickness=0.01,
           fixed_dofs=None, loads=None):
    nodes = np.array(nodes, dtype=float)
    triangles = [tuple(t) for t in triangles]
    fixed_dofs = fixed_dofs or []
    loads = loads or {}

    K, dof, D, elem_data = _assemble_plane_stress(nodes, triangles, E, nu, thickness)

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
    equilibrium_residual_max = float(np.max(np.abs(residual[free]))) if free else 0.0

    stresses = []
    for B, area, idx in elem_data:
        ue = u_full[idx]
        strain = B @ ue
        stress = D @ strain
        stresses.append({
            "sigma_xx": float(stress[0]),
            "sigma_yy": float(stress[1]),
            "tau_xy": float(stress[2]),
            "area": float(area),
        })

    return {
        "nodal_displacements": u_full.reshape(-1, 2).tolist(),
        "element_stresses": stresses,
        "equilibrium_residual_max": equilibrium_residual_max,
    }


def _build_patch_mesh(nx=3, ny=2, Lx=2.0, Ly=1.0, irregular=True, seed=42):
    """
    Malla rectangular Lx*Ly, nx*ny celdas, cada celda partida en 2 triangulos.
    Si irregular=True, perturba los nodos interiores (no en el borde) para
    que el patch test sea sobre malla NO estructurada -- la prueba fuerte del
    patch test es justamente que funcione igual de bien con malla irregular.
    """
    rng = np.random.default_rng(seed)
    xs = np.linspace(0, Lx, nx + 1)
    ys = np.linspace(0, Ly, ny + 1)
    nodes = []
    node_id = {}
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            xp, yp = x, y
            is_boundary = (i == 0 or i == nx or j == 0 or j == ny)
            if irregular and not is_boundary:
                dx = 0.3 * (Lx / nx)
                dy = 0.3 * (Ly / ny)
                xp += rng.uniform(-dx, dx)
                yp += rng.uniform(-dy, dy)
            node_id[(i, j)] = len(nodes)
            nodes.append([xp, yp])

    triangles = []
    for j in range(ny):
        for i in range(nx):
            n00 = node_id[(i, j)]
            n10 = node_id[(i+1, j)]
            n11 = node_id[(i+1, j+1)]
            n01 = node_id[(i, j+1)]
            # antihorario
            triangles.append((n00, n10, n11))
            triangles.append((n00, n11, n01))

    left_nodes = [node_id[(0, j)] for j in range(ny + 1)]
    right_nodes = [node_id[(nx, j)] for j in range(ny + 1)]
    return np.array(nodes), triangles, left_nodes, right_nodes


def _patch_test(E=200e9, nu=0.3, thickness=0.01, sigma_applied=1e6,
                 nx=3, ny=2, Lx=2.0, Ly=1.0, irregular=True, seed=42):
    nodes, triangles, left_nodes, right_nodes = _build_patch_mesh(
        nx, ny, Lx, Ly, irregular, seed
    )

    # Empotrar borde izquierdo SOLO en u_x=0 (representa el plano x=0);
    # u_y=0 unicamente en un nodo, para fijar el modo de cuerpo rigido sin
    # impedir la contraccion de Poisson lateral (fix del bug original).
    left_sorted = sorted(left_nodes, key=lambda n: nodes[n][1])
    fixed_dofs = [2*n for n in left_nodes]
    fixed_dofs.append(2*left_sorted[0] + 1)

    # Fuerza nodal equivalente: cada tramo de borde derecho reparte su fuerza
    # total (sigma*t*altura_tramo) mitad a cada nodo extremo del tramo.
    right_sorted = sorted(right_nodes, key=lambda n: nodes[n][1])
    loads = {}
    for k in range(len(right_sorted) - 1):
        n_a, n_b = right_sorted[k], right_sorted[k+1]
        h = abs(nodes[n_b][1] - nodes[n_a][1])
        f_total = sigma_applied * thickness * h
        for n in (n_a, n_b):
            loads[2*n] = loads.get(2*n, 0.0) + f_total / 2.0

    result = _solve(nodes, triangles, E=E, nu=nu, thickness=thickness,
                     fixed_dofs=fixed_dofs, loads=loads)

    sigma_xx_all = [s["sigma_xx"] for s in result["element_stresses"]]
    sigma_yy_all = [s["sigma_yy"] for s in result["element_stresses"]]
    tau_xy_all = [s["tau_xy"] for s in result["element_stresses"]]

    max_sigma_xx_err_pct = 100 * max(abs(s - sigma_applied) for s in sigma_xx_all) / sigma_applied
    max_sigma_yy_abs = max(abs(s) for s in sigma_yy_all)
    max_tau_xy_abs = max(abs(s) for s in tau_xy_all)

    # desplazamiento analitico en el borde derecho: u_x = sigma*Lx/E
    u_x_analytic = sigma_applied * Lx / E
    u_x_numeric_right = [result["nodal_displacements"][n][0] for n in right_nodes]
    max_ux_err_pct = 100 * max(abs(u - u_x_analytic) for u in u_x_numeric_right) / u_x_analytic

    return {
        "mode": "patch_test",
        "mesh": {"n_nodes": len(nodes), "n_triangles": len(triangles), "irregular": irregular},
        "sigma_applied_Pa": sigma_applied,
        "sigma_xx_range": [min(sigma_xx_all), max(sigma_xx_all)],
        "max_sigma_xx_relative_error_pct": max_sigma_xx_err_pct,
        "max_sigma_yy_abs_Pa": max_sigma_yy_abs,
        "max_tau_xy_abs_Pa": max_tau_xy_abs,
        "u_x_right_analytic": u_x_analytic,
        "max_ux_relative_error_pct": max_ux_err_pct,
        "equilibrium_residual_max": result["equilibrium_residual_max"],
    }


def _mode_validate():
    r = _patch_test(irregular=True, nx=3, ny=2)
    checks = {
        "sigma_xx_uniform": bool(r["max_sigma_xx_relative_error_pct"] < 1e-6),
        "sigma_yy_zero": bool(r["max_sigma_yy_abs_Pa"] < 1e-3),
        "tau_xy_zero": bool(r["max_tau_xy_abs_Pa"] < 1e-3),
        "ux_matches_analytic": bool(r["max_ux_relative_error_pct"] < 1e-6),
        "equilibrium_satisfied": bool(r["equilibrium_residual_max"] < 1e-3),
    }
    validation_passed = all(checks.values())
    return {
        "mode": "validate",
        "patch_test_result": r,
        "checks": checks,
        "expected": "patch test clasico (Cook Malkus & Plesha): bajo traccion "
                    "uniforme, el CST debe recuperar sigma_xx exactamente "
                    "uniforme e igual al valor aplicado en TODOS los elementos "
                    "-- incluso con malla irregular -- y sigma_yy=tau_xy=0. "
                    "Es la prueba estandar de correctitud de un codigo FEM plano.",
        "validation_passed": bool(validation_passed),
    }


def compute_plane_stress(mode, params=None):
    params = params or {}
    if mode == "solve":
        return _solve(**params)
    elif mode == "patch_test":
        return _patch_test(**params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(f"modo desconocido: {mode}. Use solve | patch_test | validate")


if __name__ == "__main__":
    import json
    r = compute_plane_stress("validate")
    print(json.dumps(r, indent=2, ensure_ascii=False))

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("plane_stress_tool", PLANE_STRESS_TOOL_SCHEMA, lambda args, _f=compute_plane_stress: _f(**args))
