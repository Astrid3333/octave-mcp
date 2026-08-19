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

    if mode == "validate":
        return _validate_sdf()

    raise ValueError(f"mode desconocido: '{mode}' (usar evaluate/normals/boolean/extract_mesh/validate)")


def _mesh_to_obj(verts, faces):
    lines = []
    for v in verts:
        lines.append(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")
    for f in faces:
        # OBJ es 1-indexado
        lines.append(f"f {f[0]+1} {f[1]+1} {f[2]+1}")
    return "\n".join(lines)


def _validate_sdf():
    """
    Suite de validaciones internas para sdf_tool.py, sin dependencias externas
    de referencia (todo se contrasta contra geometria analitica conocida).

    Chequeos:
      1. primitivas_vs_analitico: para cada primitiva, un punto de prueba
         cuya distancia firmada se puede derivar geometricamente a mano
         (no solo re-evaluando la misma formula).
      2. smooth_limit_k0: el blend suave (k pequeno) converge al booleano
         hard (k=0) cuando k -> 0.
      3. union_commutativa: op_union(d1,d2,k) == op_union(d2,d1,k) para
         varios k (las formulas de Quilez deben ser simetricas).
      4. volumen_monte_carlo: volumen encerrado por una esfera SDF, estimado
         por muestreo aleatorio uniforme, comparado contra 4/3 pi r^3.
      5. normales_radiales_esfera: el gradiente normalizado del SDF de una
         esfera debe apuntar radialmente hacia afuera desde el centro.
      6. volumen_malla_teorema_divergencia (solo si hay scikit-image):
         volumen del mesh extraido por marching_cubes de una esfera,
         calculado con el teorema de la divergencia sobre los triangulos,
         comparado contra 4/3 pi r^3.
    """
    rng = np.random.default_rng(12345)
    checks = {}
    errors = {}

    # -----------------------------------------------------------------
    # 1. Primitivas vs distancia analitica (puntos derivados a mano)
    # -----------------------------------------------------------------
    prim_err = {}

    # sphere: center=(0,0,0) r=2, punto en (7,0,0) -> dist = 7-2 = 5
    d = float(_sdf_sphere(np.array([7.0, 0.0, 0.0]), [0, 0, 0], 2.0))
    prim_err["sphere"] = abs(d - 5.0)

    # box: center=(0,0,0) half_extents=(1,2,3), punto en (5,0,0) -> dist = 5-1 = 4
    d = float(_sdf_box(np.array([5.0, 0.0, 0.0]), [0, 0, 0], [1, 2, 3]))
    prim_err["box"] = abs(d - 4.0)

    # torus: center=(0,0,0) major_r=3 minor_r=1, punto en (8,0,0)
    # -> xy = |8|-3 = 5, z=0 -> dist = sqrt(5^2+0^2)-1 = 4
    d = float(_sdf_torus(np.array([8.0, 0.0, 0.0]), [0, 0, 0], 3.0, 1.0))
    prim_err["torus"] = abs(d - 4.0)

    # cylinder: center=(0,0,0) radius=1 half_height=2, punto en (5,0,0)
    # -> d_xy = 5-1=4, d_z = 0-2=-2 (adentro en z) -> outside = 4, inside=min(max(4,-2),0)=0 -> dist=4
    d = float(_sdf_cylinder(np.array([5.0, 0.0, 0.0]), [0, 0, 0], 1.0, 2.0))
    prim_err["cylinder"] = abs(d - 4.0)

    # plane: normal=(0,0,1) offset=-5 (plano z=5), punto en (0,0,10) -> dist = 10-5 = 5
    d = float(_sdf_plane(np.array([0.0, 0.0, 10.0]), [0, 0, 1], -5.0))
    prim_err["plane"] = abs(d - 5.0)

    # capsule: a=(0,0,0) b=(0,0,4) radius=1, punto en (5,0,2)
    # -> proyeccion cae en (0,0,2) (dentro del segmento) -> dist = 5-1 = 4
    d = float(_sdf_capsule(np.array([5.0, 0.0, 2.0]), [0, 0, 0], [0, 0, 4], 1.0))
    prim_err["capsule"] = abs(d - 4.0)

    errors["primitives_abs_err"] = prim_err
    checks["primitives_match_analytic"] = all(v < 1e-8 for v in prim_err.values())

    # -----------------------------------------------------------------
    # 2. Limite k->0 del blend suave vs booleano hard
    # -----------------------------------------------------------------
    d1 = np.array([-3.0, -1.0, 0.5, 2.0, 5.0])
    d2 = np.array([2.0, -2.0, -0.5, 1.5, -4.0])
    smooth_limit_err = {}
    for name, op in _OPS.items():
        hard = op(d1, d2, 0.0)
        near_zero = op(d1, d2, 1e-6)
        smooth_limit_err[name] = float(np.max(np.abs(hard - near_zero)))
    errors["smooth_limit_k0_abs_err"] = smooth_limit_err
    checks["smooth_ops_converge_to_hard_as_k_to_0"] = all(
        v < 1e-4 for v in smooth_limit_err.values()
    )

    # -----------------------------------------------------------------
    # 3. Union suave es conmutativa (simetria de la formula de Quilez)
    # -----------------------------------------------------------------
    comm_err = 0.0
    for k in (0.0, 0.3, 1.0, 2.5):
        a = _op_union(d1, d2, k)
        b = _op_union(d2, d1, k)
        comm_err = max(comm_err, float(np.max(np.abs(a - b))))
    errors["union_commutativity_abs_err"] = comm_err
    checks["union_is_commutative"] = comm_err < 1e-10

    # -----------------------------------------------------------------
    # 4. Volumen de una esfera via Monte Carlo vs 4/3 pi r^3
    # -----------------------------------------------------------------
    r = 1.7
    n_samples = 400_000
    box_half = r * 1.2
    box_vol = (2 * box_half) ** 3
    samples = rng.uniform(-box_half, box_half, size=(n_samples, 3))
    d = _sdf_sphere(samples, [0, 0, 0], r)
    frac_inside = float(np.mean(d < 0.0))
    vol_mc = frac_inside * box_vol
    vol_analytic = (4.0 / 3.0) * np.pi * r ** 3
    vol_err_pct = 100.0 * abs(vol_mc - vol_analytic) / vol_analytic
    errors["sphere_volume_montecarlo_err_pct"] = round(vol_err_pct, 4)
    checks["sphere_volume_montecarlo_matches_analytic"] = vol_err_pct < 2.0

    # -----------------------------------------------------------------
    # 5. Normales radiales en la superficie de una esfera
    # -----------------------------------------------------------------
    normals_sphere_node = {"op": "sphere", "center": [0, 0, 0], "radius": 2.0}
    dirs = rng.normal(size=(50, 3))
    dirs = dirs / np.linalg.norm(dirs, axis=-1, keepdims=True)
    surf_pts = dirs * 2.0
    normals = _sdf_normals(normals_sphere_node, surf_pts)
    dot = np.sum(normals * dirs, axis=-1)
    normal_align_err = float(np.max(np.abs(dot - 1.0)))
    errors["sphere_normals_radial_align_err"] = normal_align_err
    checks["sphere_normals_point_radially_outward"] = normal_align_err < 1e-3

    # -----------------------------------------------------------------
    # 6. Volumen de malla (marching cubes) via teorema de la divergencia
    # -----------------------------------------------------------------
    if _HAS_SKIMAGE:
        resolution = 60
        bounds_min = np.array([-r * 1.3] * 3)
        bounds_max = np.array([r * 1.3] * 3)
        xs = np.linspace(bounds_min[0], bounds_max[0], resolution)
        ys = np.linspace(bounds_min[1], bounds_max[1], resolution)
        zs = np.linspace(bounds_min[2], bounds_max[2], resolution)
        grid = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), axis=-1)
        mesh_sphere_node = {"op": "sphere", "center": [0, 0, 0], "radius": r}
        vol_grid = evaluate_sdf(mesh_sphere_node, grid)
        spacing = (
            (bounds_max[0] - bounds_min[0]) / (resolution - 1),
            (bounds_max[1] - bounds_min[1]) / (resolution - 1),
            (bounds_max[2] - bounds_min[2]) / (resolution - 1),
        )
        verts, faces, _n, _v = _sk_measure.marching_cubes(vol_grid, level=0.0, spacing=spacing)
        verts = verts + bounds_min
        tri = verts[faces]
        v0, v1, v2 = tri[:, 0, :], tri[:, 1, :], tri[:, 2, :]
        # volumen = (1/6) * sum( v0 . (v1 x v2) ) sobre triangulos orientados
        cross = np.cross(v1, v2)
        signed_vol_terms = np.sum(v0 * cross, axis=-1)
        vol_mesh = abs(float(np.sum(signed_vol_terms)) / 6.0)
        vol_mesh_err_pct = 100.0 * abs(vol_mesh - vol_analytic) / vol_analytic
        errors["sphere_volume_mesh_divergence_err_pct"] = round(vol_mesh_err_pct, 4)
        checks["mesh_volume_matches_analytic"] = vol_mesh_err_pct < 2.0
    else:
        checks["mesh_volume_matches_analytic"] = None
        errors["sphere_volume_mesh_divergence_err_pct"] = None

    validation_passed = all(v for v in checks.values() if v is not None)

    return {
        "mode": "validate",
        "checks": checks,
        "errors": errors,
        "expected": (
            "primitives_match_analytic: distancia analitica derivada a mano "
            "(no la misma formula reevaluada) debe coincidir <1e-8. "
            "smooth_ops_converge_to_hard_as_k_to_0: blend suave con k=1e-6 "
            "debe ser practicamente identico al booleano hard (k=0), <1e-4. "
            "union_is_commutative: la formula de Quilez para union suave es "
            "simetrica en d1/d2 por construccion, error debe ser ~0 (<1e-10). "
            "sphere_volume_montecarlo_matches_analytic: 400k muestras "
            "uniformes en una caja, fraccion adentro * volumen de caja vs "
            "4/3 pi r^3, error <2%%. sphere_normals_point_radially_outward: "
            "en la superficie de una esfera centrada en el origen el gradiente "
            "del SDF debe ser paralelo al vector posicion (dot~1), error <1e-3. "
            "mesh_volume_matches_analytic (si hay scikit-image): volumen del "
            "mesh de marching_cubes calculado via teorema de la divergencia "
            "(suma de v0.(v1 x v2)/6 sobre triangulos) vs 4/3 pi r^3, error <2%%."
        ),
        "validation_passed": validation_passed,
    }


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
                "enum": ["evaluate", "normals", "boolean", "extract_mesh", "validate"],
                "description": "evaluate: distancias en puntos dados. normals: "
                                "gradiente/normal en puntos. boolean: combina dos "
                                "arrays de distancias. extract_mesh: marching cubes "
                                "sobre un arbol SDF (requiere scikit-image)." " validate: corre una suite de auto-chequeos internos (primitivas vs distancia analitica, limite k->0 de smooth booleans, conmutatividad de union, volumen via Monte Carlo, normales radiales, y volumen de malla via teorema de la divergencia si hay scikit-image).",
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

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("sdf_tool", SDF_TOOL_SCHEMA, lambda args, _f=compute_sdf_tool: _f(**args))
