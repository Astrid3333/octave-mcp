"""
sdf_tool.py — Signed Distance Functions: primitivas, booleanas, normales, extraccion de malla.

Integra con el patron octave-mcp: compute_sdf_tool(mode, params=None) + SDF_TOOL_SCHEMA.

Dependencias:
  - numpy (siempre requerido)
  - scikit-image (opcional, solo para mode="extract_mesh")
"""

import numpy as np

try:
    from skimage import measure as _sk_measure
    _HAS_SKIMAGE = True
except ImportError:
    _HAS_SKIMAGE = False


# ---------------------------------------------------------------------------
# Primitivas SDF (todas vectorizadas: p tiene shape (..., 3))
# ---------------------------------------------------------------------------

def _sdf_sphere(p, center, radius):
    return np.linalg.norm(p - np.asarray(center), axis=-1) - radius


def _sdf_box(p, center, half_extents):
    q = np.abs(p - np.asarray(center)) - np.asarray(half_extents)
    outside = np.linalg.norm(np.maximum(q, 0.0), axis=-1)
    inside = np.minimum(np.max(q, axis=-1), 0.0)
    return outside + inside


def _sdf_torus(p, center, major_r, minor_r):
    q = p - np.asarray(center)
    xy = np.linalg.norm(q[..., :2], axis=-1) - major_r
    return np.sqrt(xy ** 2 + q[..., 2] ** 2) - minor_r


def _sdf_cylinder(p, center, radius, half_height):
    q = p - np.asarray(center)
    d_xy = np.linalg.norm(q[..., :2], axis=-1) - radius
    d_z = np.abs(q[..., 2]) - half_height
    outside = np.sqrt(np.maximum(d_xy, 0.0) ** 2 + np.maximum(d_z, 0.0) ** 2)
    inside = np.minimum(np.maximum(d_xy, d_z), 0.0)
    return outside + inside


def _sdf_plane(p, normal, offset):
    n = np.asarray(normal, dtype=float)
    n = n / np.linalg.norm(n)
    return np.tensordot(p, n, axes=([-1], [0])) + offset


def _sdf_capsule(p, a, b, radius):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    pa = p - a
    ba = b - a
    h = np.clip(np.tensordot(pa, ba, axes=([-1], [0])) / np.dot(ba, ba), 0.0, 1.0)
    proj = pa - ba * h[..., None]
    return np.linalg.norm(proj, axis=-1) - radius


_PRIMITIVES = {
    "sphere": (_sdf_sphere, ("center", "radius")),
    "box": (_sdf_box, ("center", "half_extents")),
    "torus": (_sdf_torus, ("center", "major_r", "minor_r")),
    "cylinder": (_sdf_cylinder, ("center", "radius", "half_height")),
    "plane": (_sdf_plane, ("normal", "offset")),
    "capsule": (_sdf_capsule, ("a", "b", "radius")),
}


# ---------------------------------------------------------------------------
# Combinadores booleanos (hard y smooth, formulas de Inigo Quilez)
# ---------------------------------------------------------------------------

def _op_union(d1, d2, k=0.0):
    if k <= 0.0:
        return np.minimum(d1, d2)
    h = np.clip(0.5 + 0.5 * (d2 - d1) / k, 0.0, 1.0)
    return d2 * (1 - h) + d1 * h - k * h * (1 - h)


def _op_intersection(d1, d2, k=0.0):
    if k <= 0.0:
        return np.maximum(d1, d2)
    h = np.clip(0.5 - 0.5 * (d2 - d1) / k, 0.0, 1.0)
    return d2 * (1 - h) + d1 * h + k * h * (1 - h)


def _op_difference(d1, d2, k=0.0):
    # d1 menos d2 (resta d2 de d1)
    if k <= 0.0:
        return np.maximum(d1, -d2)
    h = np.clip(0.5 - 0.5 * (d2 + d1) / k, 0.0, 1.0)
    return d1 * (1 - h) + (-d2) * h + k * h * (1 - h)


_OPS = {
    "union": _op_union,
    "intersection": _op_intersection,
    "difference": _op_difference,
}


# ---------------------------------------------------------------------------
# Evaluador recursivo del arbol SDF
# ---------------------------------------------------------------------------

def evaluate_sdf(node, p):
    """
    node: dict con:
      - primitiva: {"op": "sphere"|"box"|"torus"|"cylinder"|"plane"|"capsule", <params...>}
      - combinador: {"op": "union"|"intersection"|"difference", "children": [n1, n2], "k": float (smooth, default 0)}
    p: ndarray shape (..., 3)
    """
    op = node.get("op")
    if op in _PRIMITIVES:
        fn, param_names = _PRIMITIVES[op]
        kwargs = {name: node[name] for name in param_names}
        return fn(p, **kwargs)
    if op in _OPS:
        children = node.get("children")
        if not children or len(children) < 2:
            raise ValueError(f"combinador '{op}' requiere al menos 2 children")
        k = float(node.get("k", 0.0))
        acc = evaluate_sdf(children[0], p)
        for child in children[1:]:
            d = evaluate_sdf(child, p)
            acc = _OPS[op](acc, d, k)
        return acc
    raise ValueError(f"op desconocido en nodo SDF: '{op}'")


def _sdf_normals(node, p, eps=1e-4):
    """Normales via diferencias centrales del gradiente del SDF."""
    p = np.asarray(p, dtype=float)
    offsets = np.eye(3) * eps
    grads = []
    for i in range(3):
        p_plus = p + offsets[i]
        p_minus = p - offsets[i]
        d_plus = evaluate_sdf(node, p_plus)
        d_minus = evaluate_sdf(node, p_minus)
        grads.append((d_plus - d_minus) / (2 * eps))
    grad = np.stack(grads, axis=-1)
    norm = np.linalg.norm(grad, axis=-1, keepdims=True)
    norm = np.where(norm < 1e-12, 1.0, norm)
    return grad / norm


# ---------------------------------------------------------------------------
# Entry point del tool
# ---------------------------------------------------------------------------

def compute_sdf_tool(mode, params=None):
    params = params or {}

    if mode == "evaluate":
        node = params["tree"]
        points = np.asarray(params["points"], dtype=float)
        distances = evaluate_sdf(node, points)
        result = {"distances": distances.tolist()}
        if params.get("with_normals"):
            result["normals"] = _sdf_normals(node, points).tolist()
        return result

    if mode == "normals":
        node = params["tree"]
        points = np.asarray(params["points"], dtype=float)
        return {"normals": _sdf_normals(node, points).tolist()}

    if mode == "boolean":
        # combina dos arrays de distancias ya evaluados (utilidad standalone)
        d1 = np.asarray(params["d1"], dtype=float)
        d2 = np.asarray(params["d2"], dtype=float)
        op = params.get("boolean_op", "union")
        k = float(params.get("k", 0.0))
        if op not in _OPS:
            raise ValueError(f"boolean_op debe ser uno de {list(_OPS)}")
        return {"distances": _OPS[op](d1, d2, k).tolist()}

    if mode == "extract_mesh":
        if not _HAS_SKIMAGE:
            return {
                "error": "scikit-image no esta instalado. Instalar con: "
                         "pip install scikit-image",
                "available_without_skimage": ["evaluate", "normals", "boolean"],
            }
        node = params["tree"]
        bounds_min = np.asarray(params.get("bounds_min", [-1, -1, -1]), dtype=float)
        bounds_max = np.asarray(params.get("bounds_max", [1, 1, 1]), dtype=float)
        resolution = int(params.get("resolution", 64))

        xs = np.linspace(bounds_min[0], bounds_max[0], resolution)
        ys = np.linspace(bounds_min[1], bounds_max[1], resolution)
        zs = np.linspace(bounds_min[2], bounds_max[2], resolution)
        grid = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), axis=-1)

        volume = evaluate_sdf(node, grid)

        if volume.min() > 0 or volume.max() < 0:
            return {
                "error": "el isosurface (nivel 0) no cruza el volumen — "
                         "ajustar bounds_min/bounds_max o revisar el arbol SDF",
                "volume_min": float(volume.min()),
                "volume_max": float(volume.max()),
            }

        spacing = (
            (bounds_max[0] - bounds_min[0]) / (resolution - 1),
            (bounds_max[1] - bounds_min[1]) / (resolution - 1),
            (bounds_max[2] - bounds_min[2]) / (resolution - 1),
        )
        verts, faces, normals, _values = _sk_measure.marching_cubes(
            volume, level=0.0, spacing=spacing
        )
        verts = verts + bounds_min  # offset al origen real

        result = {
            "vertices": verts.tolist(),
            "faces": faces.tolist(),
            "n_vertices": int(verts.shape[0]),
            "n_faces": int(faces.shape[0]),
        }
        if params.get("with_normals", True):
            result["normals"] = normals.tolist()
        if params.get("export_obj"):
            result["obj_text"] = _mesh_to_obj(verts, faces)
        return result

    raise ValueError(f"mode desconocido: '{mode}' (usar evaluate/normals/boolean/extract_mesh)")


def _mesh_to_obj(verts, faces):
    lines = []
    for v in verts:
        lines.append(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")
    for f in faces:
        # OBJ es 1-indexado
        lines.append(f"f {f[0]+1} {f[1]+1} {f[2]+1}")
    return "\n".join(lines)


SDF_TOOL_SCHEMA = {
    "name": "sdf_tool",
    "description": (
        "Funciones de distancia con signo (SDF): primitivas (sphere/box/torus/"
        "cylinder/plane/capsule), booleanas hard y smooth (union/intersection/"
        "difference), normales por gradiente, y extraccion de malla via marching "
        "cubes. Base para mallado implicito y modelado geometrico orgánico "
        "(ej: sockets de prótesis, formas organicas)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["evaluate", "normals", "boolean", "extract_mesh"],
                "description": "evaluate: distancias en puntos dados. normals: "
                                "gradiente/normal en puntos. boolean: combina dos "
                                "arrays de distancias. extract_mesh: marching cubes "
                                "sobre un arbol SDF (requiere scikit-image).",
            },
            "params": {
                "type": "object",
                "description": (
                    "evaluate/normals: {tree, points, with_normals?}. "
                    "boolean: {d1, d2, boolean_op, k?}. "
                    "extract_mesh: {tree, bounds_min?, bounds_max?, resolution?, "
                    "with_normals?, export_obj?}. "
                    "tree es un nodo recursivo: primitiva "
                    "{op: sphere|box|torus|cylinder|plane|capsule, ...params} o "
                    "combinador {op: union|intersection|difference, children: "
                    "[nodo, nodo, ...], k?: float (0=hard, >0=smooth blend radius)}."
                ),
            },
        },
        "required": ["mode"],
    },
}
