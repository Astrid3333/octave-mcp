"""
mesh_pde_tool.py — Mallado adaptativo/suave via EDPs elipticas (Laplace/Poisson).

Resuelve la posicion de los nodos interiores de una malla como solucion de
una ecuacion de Laplace (mode="smooth") o Poisson (mode="poisson"), usando
la posicion de los nodos del borde como condicion de contorno Dirichlet.
Reutiliza el mismo Laplaciano cotangente (FEM lineal) que mesh_spectral_tool.

Integra con el patron octave-mcp: compute_mesh_pde_tool(mode, params=None) + MESH_PDE_TOOL_SCHEMA.

Dependencias: numpy, scipy.sparse
"""

import numpy as np
from scipy.sparse import lil_matrix, csr_matrix
from scipy.sparse.linalg import spsolve


# ---------------------------------------------------------------------------
# Laplaciano cotangente (misma convencion que mesh_spectral_tool: L = D - W,
# semidefinido positivo, L @ np.ones(n) == 0)
# ---------------------------------------------------------------------------

def _cot(a, b, c):
    """Cotangente del angulo en 'b', dado el triangulo a-b-c."""
    ba = a - b
    bc = c - b
    cross = np.linalg.norm(np.cross(ba, bc))
    dot = np.dot(ba, bc)
    if cross < 1e-14:
        return 0.0
    return dot / cross


def build_cotangent_laplacian(vertices, faces, clamp_negative=True):
    vertices = np.asarray(vertices, dtype=float)
    faces = np.asarray(faces, dtype=int)
    n = vertices.shape[0]

    W = lil_matrix((n, n))
    degenerate = 0

    for tri in faces:
        i, j, k = int(tri[0]), int(tri[1]), int(tri[2])
        vi, vj, vk = vertices[i], vertices[j], vertices[k]

        cot_i = _cot(vj, vi, vk)  # angulo en i, opuesto a la arista jk
        cot_j = _cot(vi, vj, vk)  # angulo en j, opuesto a la arista ik
        cot_k = _cot(vi, vk, vj)  # angulo en k, opuesto a la arista ij

        if cot_i == 0.0 and cot_j == 0.0 and cot_k == 0.0:
            degenerate += 1
            continue

        if clamp_negative:
            cot_i, cot_j, cot_k = max(cot_i, 0.0), max(cot_j, 0.0), max(cot_k, 0.0)

        W[j, k] += cot_i / 2.0; W[k, j] += cot_i / 2.0
        W[i, k] += cot_j / 2.0; W[k, i] += cot_j / 2.0
        W[i, j] += cot_k / 2.0; W[j, i] += cot_k / 2.0

    W = W.tocsr()
    d = np.asarray(W.sum(axis=1)).flatten()
    from scipy.sparse import diags
    L = diags(d) - W
    return L.tocsr(), degenerate


# ---------------------------------------------------------------------------
# Resolver Laplace/Poisson con condicion de contorno Dirichlet
# ---------------------------------------------------------------------------

def _solve_elliptic(L, boundary_indices, boundary_values, coords, source=None):
    """
    L: laplaciano (n x n), sparse.
    boundary_indices: indices fijos (Dirichlet).
    coords: array (n, d) — posiciones actuales, se sobreescriben en interior.
    source: (n, d) opcional — termino fuente para Poisson (L x = source). None = Laplace (L x = 0).
    """
    n = coords.shape[0]
    d = coords.shape[1]
    all_idx = np.arange(n)
    boundary_mask = np.zeros(n, dtype=bool)
    boundary_mask[boundary_indices] = True
    interior_idx = all_idx[~boundary_mask]

    if len(interior_idx) == 0:
        return coords.copy(), 0

    L_II = L[interior_idx][:, interior_idx]
    L_IB = L[interior_idx][:, boundary_indices]

    x_B = coords[boundary_indices]
    new_coords = coords.copy()

    for dim in range(d):
        rhs = -(L_IB @ x_B[:, dim])
        if source is not None:
            rhs = rhs + source[interior_idx, dim]
        x_I = spsolve(csr_matrix(L_II), rhs)
        new_coords[interior_idx, dim] = x_I

    return new_coords, len(interior_idx)


# ---------------------------------------------------------------------------
# Entry point del tool
# ---------------------------------------------------------------------------

def compute_mesh_pde_tool(mode, params=None):
    params = params or {}

    if mode == "validate":
        return validate()

    if mode in ("smooth", "poisson"):
        vertices = np.asarray(params["vertices"], dtype=float)
        faces = params["faces"]
        boundary_indices = params["boundary_indices"]
        clamp_negative = params.get("clamp_negative", True)

        L, degenerate = build_cotangent_laplacian(vertices, faces, clamp_negative)

        source = None
        if mode == "poisson":
            source = np.asarray(params["source"], dtype=float)
            if source.shape != vertices.shape:
                raise ValueError(
                    f"'source' debe tener shape {vertices.shape}, recibido {source.shape}"
                )

        new_coords, n_interior = _solve_elliptic(
            L, boundary_indices, None, vertices, source
        )

        displacement = np.linalg.norm(new_coords - vertices, axis=1)

        return {
            "vertices": new_coords.tolist(),
            "n_vertices": vertices.shape[0],
            "n_interior_solved": n_interior,
            "n_boundary_fixed": len(boundary_indices),
            "degenerate_faces": degenerate,
            "max_displacement": float(displacement.max()),
            "mean_displacement": float(displacement.mean()),
            "note": (
                "mode=smooth resuelve Laplace (L x = 0): posiciones interiores = "
                "promedio ponderado armonico de vecinos, dado el borde fijo. "
                "mode=poisson agrega un termino fuente por vertice para controlar "
                "densidad/curvatura local en vez de suavizado puramente armonico."
            ),
        }

    raise ValueError(f"mode desconocido: '{mode}' (usar smooth/poisson)")


MESH_PDE_TOOL_SCHEMA = {
    "name": "mesh_pde_tool",
    "description": (
        "Mallado adaptativo y suavizado via EDPs elipticas: resuelve la posicion "
        "de los nodos interiores de una malla como solucion de una ecuacion de "
        "Laplace (mode=smooth) o Poisson con termino fuente (mode=poisson), usando "
        "la posicion de los nodos del borde como condicion de contorno Dirichlet. "
        "Usa el mismo Laplaciano cotangente (FEM lineal) que mesh_spectral_tool. "
        "Util para eliminar pliegues/cruces en una malla generada a mano o por "
        "distmesh_tool, o para regenerar el interior de una malla dado un nuevo "
        "contorno (ej: perfil de socket de protesis modificado)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["smooth", "poisson", "validate"],
                "description": "smooth: Laplace puro (L x = 0). poisson: agrega "
                                "termino fuente por vertice (L x = source).",
            },
            "params": {
                "type": "object",
                "description": (
                    "smooth: {vertices: [[x,y,z],...], faces: [[i,j,k],...], "
                    "boundary_indices: [int,...], clamp_negative?: bool (default true)}. "
                    "poisson: mismos params + {source: [[fx,fy,fz],...], misma shape "
                    "que vertices, fuente por vertice, ignorada en indices de borde}."
                ),
            },
        },
        "required": ["mode"],
    },
}

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("mesh_pde_tool", MESH_PDE_TOOL_SCHEMA, lambda args, _f=compute_mesh_pde_tool: _f(**args))


# ---------------------------------------------------------------------------
# Validacion propia (mode="validate")
# ---------------------------------------------------------------------------

def validate():
    checks = []

    # Malla cuadrada 3x3 (9 vertices, borde = 8 exteriores, 1 interior),
    # triangulada. mode=smooth con borde fijo en un cuadrado plano:
    # el vertice interior (Laplace puro) debe converger al promedio
    # aritmetico de sus 4 vecinos (caso conocido: grilla regular ->
    # pesos cotangentes uniformes por simetria).
    vertices = [
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0],
        [0.0, 1.0, 0.0], [1.0, 1.0, 0.0], [2.0, 1.0, 0.0],
        [0.0, 2.0, 0.0], [1.0, 2.0, 0.0], [2.0, 2.0, 0.0],
    ]
    faces = [
        [0, 1, 4], [0, 4, 3],
        [1, 2, 5], [1, 5, 4],
        [3, 4, 7], [3, 7, 6],
        [4, 5, 8], [4, 8, 7],
    ]
    boundary_indices = [0, 1, 2, 3, 5, 6, 7, 8]  # todos menos el centro (4)

    r1 = compute_mesh_pde_tool("smooth", {
        "vertices": vertices, "faces": faces, "boundary_indices": boundary_indices,
    })
    center_new = np.array(r1["vertices"][4])
    expected_center = np.array([1.0, 1.0, 0.0])  # centroide de la grilla simetrica
    err = float(np.linalg.norm(center_new - expected_center))
    checks.append({
        "name": "smooth_converge_al_centroide_en_grilla_simetrica",
        "passed": err < 1e-6,
        "detail": f"centro_obtenido={center_new.tolist()} esperado={expected_center.tolist()} err={err:.2e}",
    })

    checks.append({
        "name": "smooth_no_reporta_caras_degeneradas_en_grilla_regular",
        "passed": r1["degenerate_faces"] == 0,
        "detail": f"degenerate_faces={r1['degenerate_faces']}",
    })

    all_pass = all(c["passed"] for c in checks)
    return {
        "validation_passed": all_pass,
        "n_checks": len(checks),
        "checks": checks,
    }
