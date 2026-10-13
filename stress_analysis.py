"""
stress_analysis: modo nuevo para finite_element_tool.
Elasticidad plana (plane stress / plane strain), elementos cuadrilateros
bilineales (Q4), integracion de Gauss 2x2.
"""
import numpy as np

def constitutive_matrix(E, nu, mode="plane_stress"):
    if mode == "plane_stress":
        C = (E / (1 - nu**2)) * np.array([
            [1, nu, 0],
            [nu, 1, 0],
            [0, 0, (1 - nu) / 2]
        ])
    elif mode == "plane_strain":
        C = (E / ((1 + nu) * (1 - 2 * nu))) * np.array([
            [1 - nu, nu, 0],
            [nu, 1 - nu, 0],
            [0, 0, (1 - 2 * nu) / 2]
        ])
    else:
        raise ValueError("mode debe ser 'plane_stress' o 'plane_strain'")
    return C

def q4_shape_derivs(xi, eta, coords):
    """Derivadas de las funciones de forma Q4 respecto a x,y (via Jacobiano)."""
    dN_dxi = 0.25 * np.array([-(1 - eta), (1 - eta), (1 + eta), -(1 + eta)])
    dN_deta = 0.25 * np.array([-(1 - xi), -(1 + xi), (1 + xi), (1 - xi)])
    J = np.zeros((2, 2))
    J[0, 0] = dN_dxi @ coords[:, 0]
    J[0, 1] = dN_dxi @ coords[:, 1]
    J[1, 0] = dN_deta @ coords[:, 0]
    J[1, 1] = dN_deta @ coords[:, 1]
    detJ = np.linalg.det(J)
    Jinv = np.linalg.inv(J)
    dN_dxy = Jinv @ np.vstack([dN_dxi, dN_deta])
    return dN_dxy, detJ

def element_stiffness(coords, C, thickness=1.0):
    gp = 1 / np.sqrt(3)
    points = [(-gp, -gp), (gp, -gp), (gp, gp), (-gp, gp)]
    Ke = np.zeros((8, 8))
    for xi, eta in points:
        dN_dxy, detJ = q4_shape_derivs(xi, eta, coords)
        B = np.zeros((3, 8))
        for a in range(4):
            B[0, 2*a]   = dN_dxy[0, a]
            B[1, 2*a+1] = dN_dxy[1, a]
            B[2, 2*a]   = dN_dxy[1, a]
            B[2, 2*a+1] = dN_dxy[0, a]
        Ke += B.T @ C @ B * detJ * thickness
    return Ke

def build_rect_mesh(Lx, Ly, nx, ny):
    """Malla rectangular estructurada de elementos Q4."""
    nodes = []
    for j in range(ny + 1):
        for i in range(nx + 1):
            nodes.append([i * Lx / nx, j * Ly / ny])
    nodes = np.array(nodes)
    elements = []
    for j in range(ny):
        for i in range(nx):
            n0 = j * (nx + 1) + i
            n1 = n0 + 1
            n2 = n1 + (nx + 1)
            n3 = n0 + (nx + 1)
            elements.append([n0, n1, n2, n3])
    return nodes, np.array(elements)

def solve_plane_plate(Lx, Ly, nx, ny, E, nu, mode, sigma_applied, thickness=1.0):
    """
    Placa rectangular en traccion uniaxial: borde izquierdo fijo en x (u_x=0),
    esquina inferior izquierda tambien fija en y (evita cuerpo rigido),
    borde derecho con traccion uniforme sigma_applied en x.
    Devuelve nodos, desplazamientos, y tensor de esfuerzos promedio por elemento.
    """
    nodes, elements = build_rect_mesh(Lx, Ly, nx, ny)
    n_nodes = len(nodes)
    ndof = 2 * n_nodes
    C = constitutive_matrix(E, nu, mode)
    K = np.zeros((ndof, ndof))
    for el in elements:
        coords = nodes[el]
        Ke = element_stiffness(coords, C, thickness)
        dofs = np.array([[2*n, 2*n+1] for n in el]).flatten()
        for a in range(8):
            for b in range(8):
                K[dofs[a], dofs[b]] += Ke[a, b]
    F = np.zeros(ndof)
    # Traccion en el borde derecho (x = Lx): distribuir la fuerza total entre nodos del borde
    right_nodes = [n for n in range(n_nodes) if np.isclose(nodes[n, 0], Lx)]
    right_nodes.sort(key=lambda n: nodes[n, 1])
    total_force = sigma_applied * Ly * thickness
    # Regla trapezoidal: nodos extremos con mitad de peso
    weights = np.ones(len(right_nodes))
    weights[0] = 0.5; weights[-1] = 0.5
    weights *= total_force / weights.sum()
    for n, w in zip(right_nodes, weights):
        F[2*n] += w
    # BCs: borde izquierdo fijo en x, esquina inferior izquierda fija tambien en y
    left_nodes = [n for n in range(n_nodes) if np.isclose(nodes[n, 0], 0.0)]
    fixed_dofs = set()
    for n in left_nodes:
        fixed_dofs.add(2*n)  # u_x = 0
    bottom_left = min(left_nodes, key=lambda n: nodes[n, 1])
    fixed_dofs.add(2*bottom_left + 1)  # u_y = 0 solo en esa esquina
    free_dofs = [d for d in range(ndof) if d not in fixed_dofs]
    Kff = K[np.ix_(free_dofs, free_dofs)]
    Ff = F[free_dofs]
    Uf = np.linalg.solve(Kff, Ff)
    U = np.zeros(ndof)
    for i, d in enumerate(free_dofs):
        U[d] = Uf[i]
    # Esfuerzo promedio (centro del elemento) para cada elemento
    stresses = []
    for el in elements:
        coords = nodes[el]
        dofs = np.array([[2*n, 2*n+1] for n in el]).flatten()
        ue = U[dofs]
        dN_dxy, _ = q4_shape_derivs(0.0, 0.0, coords)
        B = np.zeros((3, 8))
        for a in range(4):
            B[0, 2*a]   = dN_dxy[0, a]
            B[1, 2*a+1] = dN_dxy[1, a]
            B[2, 2*a]   = dN_dxy[1, a]
            B[2, 2*a+1] = dN_dxy[0, a]
        stresses.append(C @ B @ ue)
    return nodes, U.reshape(-1, 2), np.array(stresses)

if __name__ == "__main__":
    # --- Patch test: traccion uniaxial pura en una placa sin agujero ---
    # Con carga uniforme y malla regular, el resultado FEM DEBE reproducir
    # exactamente el estado de esfuerzo uniforme sigma_xx = sigma_applied,
    # sigma_yy = 0, sigma_xy = 0 en todos los elementos (requisito basico de
    # cualquier formulacion FEM valida: "constant stress patch test").
    E = 200e9  # acero, Pa
    nu = 0.3
    sigma_applied = 1e6  # 1 MPa
    nodes, U, stresses = solve_plane_plate(
        Lx=2.0, Ly=1.0, nx=8, ny=4, E=E, nu=nu,
        mode="plane_stress", sigma_applied=sigma_applied
    )
    sxx = stresses[:, 0]
    syy = stresses[:, 1]
    sxy = stresses[:, 2]
    print(f"[patch test] sigma_xx: media={sxx.mean():.4e}, std={sxx.std():.4e} (esperado {sigma_applied:.4e})")
    print(f"[patch test] sigma_yy: media={syy.mean():.4e}, std={syy.std():.4e} (esperado 0)")
    print(f"[patch test] sigma_xy: media={sxy.mean():.4e}, std={sxy.std():.4e} (esperado 0)")
    assert np.allclose(sxx, sigma_applied, rtol=1e-6), "patch test fallo en sigma_xx"
    assert np.allclose(syy, 0, atol=1e-3), "patch test fallo en sigma_yy"
    assert np.allclose(sxy, 0, atol=1e-3), "patch test fallo en sigma_xy"

    # --- Comparacion adicional: deformacion axial vs teoria elemental ---
    eps_xx_analytic = sigma_applied / E
    # desplazamiento en el borde derecho (promedio) debe ser eps_xx * Lx
    right_nodes_idx = [n for n in range(len(nodes)) if np.isclose(nodes[n, 0], 2.0)]
    u_right_mean = U[right_nodes_idx, 0].mean()
    u_analytic = eps_xx_analytic * 2.0
    print(f"[desplazamiento] u_x borde derecho: FEM={u_right_mean:.6e}, analitico={u_analytic:.6e}")
    assert np.isclose(u_right_mean, u_analytic, rtol=1e-6)

    print("\nTodas las validaciones de stress_analysis (patch test) pasaron OK.")
    print("NOTA: el caso de Kirsch (placa con agujero) requiere un generador de malla")
    print("con geometria circular, que este modulo aun no incluye (mesh rectangular")
    print("estructurado solamente). Queda documentado como extension futura (fase")
    print("2 de materiales) en vez de una validacion falsa contra ese caso.")
