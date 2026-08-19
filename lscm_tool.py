"""
lscm_tool.py — Least Squares Conformal Maps + analisis de distorsion cuasi-conforme.

mode="flatten": aplana una malla 3D (topologia de disco, con borde) a 2D
    minimizando distorsion angular (Levy, Petitjean, Ray, Maillot 2002).
mode="distortion": dado un par malla-3D + UV-2D (propio o de otro origen),
    calcula el jacobiano por triangulo y de ahi: valores singulares,
    distorsion de area, dilatacion cuasi-conforme K, y coeficiente de
    Beltrami |mu| = (sigma1-sigma2)/(sigma1+sigma2).

Integra con el patron octave-mcp: compute_lscm_tool(mode, params=None) + LSCM_TOOL_SCHEMA.

Dependencias: numpy, scipy.sparse
"""

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import lsqr


# ---------------------------------------------------------------------------
# Geometria de triangulo: marco local 2D ortonormal + gradientes de base FEM
# ---------------------------------------------------------------------------

def _triangle_local_frame(v1, v2, v3):
    """Proyecta un triangulo 3D a coordenadas locales 2D (isometria exacta)."""
    e1 = v2 - v1
    len_e1 = np.linalg.norm(e1)
    if len_e1 < 1e-14:
        return None
    e1 = e1 / len_e1
    normal = np.cross(v2 - v1, v3 - v1)
    norm_n = np.linalg.norm(normal)
    if norm_n < 1e-14:
        return None  # triangulo degenerado
    normal = normal / norm_n
    e2 = np.cross(normal, e1)

    p1 = np.array([0.0, 0.0])
    p2 = np.array([np.dot(v2 - v1, e1), 0.0])
    p3 = np.array([np.dot(v3 - v1, e1), np.dot(v3 - v1, e2)])
    return p1, p2, p3


def _triangle_area_2d(p1, p2, p3):
    return 0.5 * ((p2[0] - p1[0]) * (p3[1] - p1[1]) - (p3[0] - p1[0]) * (p2[1] - p1[1]))


def _grad_basis(p1, p2, p3, area):
    """Gradientes de las 3 funciones base lineales (hat functions), en el plano local."""
    def rot90(v):
        return np.array([-v[1], v[0]])

    g1 = rot90(p3 - p2) / (2.0 * area)
    g2 = rot90(p1 - p3) / (2.0 * area)
    g3 = rot90(p2 - p1) / (2.0 * area)
    return g1, g2, g3


# ---------------------------------------------------------------------------
# mode="flatten": LSCM
# ---------------------------------------------------------------------------

def _find_pin_vertices(vertices):
    """Elige 2 vertices bien separados para fijar escala/rotacion/traslacion."""
    v0 = 0
    d = np.linalg.norm(vertices - vertices[v0], axis=1)
    v1 = int(np.argmax(d))
    dist = d[v1]
    return v0, v1, dist


def _lscm_flatten(vertices, faces, pin_a=None, pin_b=None):
    vertices = np.asarray(vertices, dtype=float)
    faces = np.asarray(faces, dtype=int)
    n_v = vertices.shape[0]
    n_f = faces.shape[0]

    if pin_a is None or pin_b is None:
        pin_a, pin_b, pin_dist = _find_pin_vertices(vertices)
    else:
        pin_dist = np.linalg.norm(vertices[pin_a] - vertices[pin_b])

    # filas: 2 por triangulo (parte real e imaginaria de Cauchy-Riemann)
    # columnas: [Ux_0..Ux_{n_v-1}, Uy_0..Uy_{n_v-1}]  (2*n_v incognitas)
    rows, cols, vals = [], [], []
    row_idx = 0
    degenerate = 0

    for tri in faces:
        i, j, k = int(tri[0]), int(tri[1]), int(tri[2])
        frame = _triangle_local_frame(vertices[i], vertices[j], vertices[k])
        if frame is None:
            degenerate += 1
            continue
        p1, p2, p3 = frame
        area = _triangle_area_2d(p1, p2, p3)
        if abs(area) < 1e-14:
            degenerate += 1
            continue
        g1, g2, g3 = _grad_basis(p1, p2, p3, area)
        w = np.sqrt(abs(area))  # pondera por tamano del triangulo

        idxs = [i, j, k]
        grads = [g1, g2, g3]

        # eq1 (real):  sum Ux_m*a_m - sum Uy_m*b_m = 0
        for m, g in zip(idxs, grads):
            rows.append(row_idx); cols.append(m); vals.append(w * g[0])
            rows.append(row_idx); cols.append(n_v + m); vals.append(-w * g[1])
        row_idx += 1

        # eq2 (imag):  sum Ux_m*b_m + sum Uy_m*a_m = 0
        for m, g in zip(idxs, grads):
            rows.append(row_idx); cols.append(m); vals.append(w * g[1])
            rows.append(row_idx); cols.append(n_v + m); vals.append(w * g[0])
        row_idx += 1

    n_rows = row_idx
    n_cols_total = 2 * n_v

    M = coo_matrix((vals, (rows, cols)), shape=(n_rows, n_cols_total)).tocsr()

    # separar columnas fijas (pines) de libres
    pinned_cols = [pin_a, n_v + pin_a, pin_b, n_v + pin_b]
    pinned_vals = np.array([0.0, 0.0, pin_dist, 0.0])  # pin_a -> (0,0), pin_b -> (dist,0)

    free_cols = [c for c in range(n_cols_total) if c not in pinned_cols]
    free_index_map = {c: idx for idx, c in enumerate(free_cols)}

    M_free = M[:, free_cols]
    M_pinned = M[:, pinned_cols]
    rhs = -(M_pinned @ pinned_vals)

    sol, istop, itn, r1norm = lsqr(M_free, rhs)[:4]

    U = np.zeros(n_cols_total)
    for c, v in zip(pinned_cols, pinned_vals):
        U[c] = v
    for c, idx in free_index_map.items():
        U[c] = sol[idx]

    uv = np.stack([U[:n_v], U[n_v:]], axis=1)

    return {
        "uv": uv.tolist(),
        "n_vertices": n_v,
        "n_faces": n_f,
        "degenerate_faces": degenerate,
        "pin_vertices": [pin_a, pin_b],
        "solver_residual": float(r1norm),
        "solver_iterations": int(itn),
    }


# ---------------------------------------------------------------------------
# mode="distortion": jacobiano por triangulo -> K y Beltrami |mu|
# ---------------------------------------------------------------------------

def _triangle_distortion(v1, v2, v3, q1, q2, q3):
    frame = _triangle_local_frame(v1, v2, v3)
    if frame is None:
        return None
    p1, p2, p3 = frame

    e1_3d = p2 - p1
    e2_3d = p3 - p1
    P = np.column_stack([e1_3d, e2_3d])  # 2x2

    e1_uv = np.asarray(q2) - np.asarray(q1)
    e2_uv = np.asarray(q3) - np.asarray(q1)
    Q = np.column_stack([e1_uv, e2_uv])  # 2x2

    try:
        P_inv = np.linalg.inv(P)
    except np.linalg.LinAlgError:
        return None

    J = Q @ P_inv  # jacobiano 2x2 local->uv

    sing = np.linalg.svd(J, compute_uv=False)
    sigma1, sigma2 = float(max(sing)), float(min(sing))
    if sigma1 + sigma2 < 1e-14:
        return None

    area_distortion = sigma1 * sigma2
    k_factor = sigma1 / sigma2 if sigma2 > 1e-14 else float("inf")
    beltrami_mu = (sigma1 - sigma2) / (sigma1 + sigma2)
    is_flipped = np.linalg.det(J) < 0

    return {
        "sigma_max": sigma1,
        "sigma_min": sigma2,
        "area_distortion": area_distortion,
        "quasi_conformal_K": k_factor,
        "beltrami_mu": beltrami_mu,
        "flipped": bool(is_flipped),
    }


def _lscm_distortion(vertices, faces, uv):
    vertices = np.asarray(vertices, dtype=float)
    faces = np.asarray(faces, dtype=int)
    uv = np.asarray(uv, dtype=float)

    per_triangle = []
    mus, ks = [], []
    flipped_count = 0
    skipped = 0

    for tri in faces:
        i, j, k = int(tri[0]), int(tri[1]), int(tri[2])
        d = _triangle_distortion(
            vertices[i], vertices[j], vertices[k], uv[i], uv[j], uv[k]
        )
        if d is None:
            skipped += 1
            per_triangle.append(None)
            continue
        per_triangle.append(d)
        mus.append(d["beltrami_mu"])
        ks.append(d["quasi_conformal_K"])
        if d["flipped"]:
            flipped_count += 1

    mus = np.array(mus) if mus else np.array([0.0])
    ks = np.array([k for k in ks if np.isfinite(k)]) if ks else np.array([1.0])

    return {
        "per_triangle": per_triangle,
        "n_faces": faces.shape[0],
        "skipped_degenerate": skipped,
        "flipped_triangles": flipped_count,
        "beltrami_mu_mean": float(np.mean(mus)),
        "beltrami_mu_max": float(np.max(mus)),
        "quasi_conformal_K_mean": float(np.mean(ks)),
        "quasi_conformal_K_max": float(np.max(ks)),
        "note": (
            "beltrami_mu cerca de 0 = mapeo casi conforme (angulos preservados). "
            "K cerca de 1 = lo mismo, en escala multiplicativa. flipped_triangles>0 "
            "indica inversion local (triangulo volteado) — señal de mala parametrizacion."
        ),
    }


# ---------------------------------------------------------------------------
# Entry point del tool
# ---------------------------------------------------------------------------

def compute_lscm_tool(mode, params=None):
    params = params or {}

    if mode == "flatten":
        vertices = params["vertices"]
        faces = params["faces"]
        pin_a = params.get("pin_vertex_a")
        pin_b = params.get("pin_vertex_b")
        return _lscm_flatten(vertices, faces, pin_a, pin_b)

    if mode == "distortion":
        vertices = params["vertices"]
        faces = params["faces"]
        uv = params["uv"]
        return _lscm_distortion(vertices, faces, uv)

    if mode == "flatten_and_distortion":
        vertices = params["vertices"]
        faces = params["faces"]
        pin_a = params.get("pin_vertex_a")
        pin_b = params.get("pin_vertex_b")
        flat = _lscm_flatten(vertices, faces, pin_a, pin_b)
        dist = _lscm_distortion(vertices, faces, flat["uv"])
        flat["distortion"] = dist
        return flat

    raise ValueError(f"mode desconocido: '{mode}' (usar flatten/distortion/flatten_and_distortion)")


LSCM_TOOL_SCHEMA = {
    "name": "lscm_tool",
    "description": (
        "Parametrizacion conforme (Least Squares Conformal Maps): aplana una "
        "malla 3D con borde (topologia de disco) a 2D minimizando distorsion "
        "angular. Incluye analisis de distorsion cuasi-conforme por triangulo "
        "(valores singulares del jacobiano, dilatacion K, coeficiente de "
        "Beltrami |mu|). Util para desenrollar superficies organicas "
        "(ej: sockets de protesis) para texturizado, comparacion de geometria, "
        "o deteccion de zonas de alta distorsion."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["flatten", "distortion", "flatten_and_distortion"],
                "description": "flatten: aplana 3D->2D. distortion: mide distorsion "
                                "dado un UV existente. flatten_and_distortion: hace "
                                "ambas cosas en una sola llamada.",
            },
            "params": {
                "type": "object",
                "description": (
                    "flatten: {vertices: [[x,y,z],...], faces: [[i,j,k],...], "
                    "pin_vertex_a?: int, pin_vertex_b?: int}. "
                    "distortion: {vertices, faces, uv: [[u,v],...]}. "
                    "flatten_and_distortion: mismos params que flatten. "
                    "Si no se especifican pin_vertex_a/b, se eligen automaticamente "
                    "(vertice 0 y el mas lejano a el)."
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

register_tool("lscm_tool", LSCM_TOOL_SCHEMA, lambda args, _f=compute_lscm_tool: _f(**args))
