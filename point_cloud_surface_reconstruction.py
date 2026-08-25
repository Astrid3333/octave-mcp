"""
point_cloud_surface_reconstruction.py -- Reconstruccion de superficie a
partir de una nube de puntos: convex hull (scipy.spatial.ConvexHull) y
alpha shapes 3D (filtrado de tetraedros de Delaunay por circunradio,
implementacion propia).

Modos:
  convex_hull  -- envolvente convexa: vertices, caras, area, volumen
  alpha_shape  -- superficie alpha (mas ajustada que el hull para nubes
                  con concavidades), via triangulacion de Delaunay +
                  filtrado por circunradio < alpha
  validate     -- casos con respuesta analitica exacta conocida (cubo
                  unitario, tetraedro regular) + verificacion cruzada
                  alpha_shape (alpha grande) vs convex_hull
"""

from collections import Counter
from itertools import combinations

import numpy as np
from scipy.spatial import ConvexHull, Delaunay


# ---------------------------------------------------------------------------
# Convex hull
# ---------------------------------------------------------------------------

def _convex_hull_reconstruction(points):
    points = np.asarray(points, dtype=float)
    hull = ConvexHull(points)
    return {
        "num_vertices": int(len(hull.vertices)),
        "num_faces": int(len(hull.simplices)),
        "surface_area": float(hull.area),
        "volume": float(hull.volume),
        "vertex_indices": hull.vertices.tolist(),
        "faces": hull.simplices.tolist(),
    }


# ---------------------------------------------------------------------------
# Alpha shape 3D (propio, sobre triangulacion de Delaunay de scipy)
# ---------------------------------------------------------------------------

def _tetra_circumradius(pts):
    """pts: 4x3. Devuelve (radio, centro). inf si el tetraedro es
    degenerado (los 4 puntos son coplanares)."""
    A = 2 * (pts[1:] - pts[0])
    b = np.sum(pts[1:] ** 2 - pts[0] ** 2, axis=1)
    try:
        center = np.linalg.solve(A, b)
    except np.linalg.LinAlgError:
        return float("inf"), None
    R = float(np.linalg.norm(center - pts[0]))
    return R, center


def _tetra_volume(pts):
    return abs(float(np.linalg.det(pts[1:] - pts[0]))) / 6.0


def _triangle_area(pts):
    v1 = pts[1] - pts[0]
    v2 = pts[2] - pts[0]
    return 0.5 * float(np.linalg.norm(np.cross(v1, v2)))


def _alpha_shape_3d(points, alpha):
    points = np.asarray(points, dtype=float)
    tri = Delaunay(points)
    kept = []
    for simplex in tri.simplices:
        pts = points[simplex]
        R, _ = _tetra_circumradius(pts)
        if R < alpha:
            kept.append(simplex)

    face_count = Counter()
    for tet in kept:
        for face in combinations(sorted(tet.tolist()), 3):
            face_count[face] += 1
    boundary_faces = [f for f, c in face_count.items() if c == 1]

    surface_area = sum(_triangle_area(points[list(f)]) for f in boundary_faces)
    volume = sum(_tetra_volume(points[simplex]) for simplex in kept)

    return {
        "alpha": float(alpha),
        "num_input_tetrahedra": int(len(tri.simplices)),
        "num_kept_tetrahedra": int(len(kept)),
        "num_boundary_faces": int(len(boundary_faces)),
        "surface_area": float(surface_area),
        "volume": float(volume),
        "boundary_faces": [list(f) for f in boundary_faces],
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def compute_point_cloud_surface_reconstruction(mode, **params):
    if mode == "validate":
        return _validate_point_cloud_surface_reconstruction()
    elif mode == "convex_hull":
        points = np.array(params["points"], dtype=float)
        return _convex_hull_reconstruction(points)
    elif mode == "alpha_shape":
        points = np.array(params["points"], dtype=float)
        alpha = params.get("alpha", 1.0)
        return _alpha_shape_3d(points, alpha)
    else:
        raise ValueError(f"modo desconocido: {mode}. Use convex_hull | alpha_shape")


# ---------------------------------------------------------------------------
# Validacion
# ---------------------------------------------------------------------------

def _fibonacci_sphere(n, radius=1.0):
    i = np.arange(n)
    phi = np.arccos(1 - 2 * (i + 0.5) / n)
    golden_angle = np.pi * (3 - np.sqrt(5))
    theta = golden_angle * i
    x = radius * np.sin(phi) * np.cos(theta)
    y = radius * np.sin(phi) * np.sin(theta)
    z = radius * np.cos(phi)
    return np.stack([x, y, z], axis=1)


def _validate_point_cloud_surface_reconstruction():
    checks = []

    # --- convex_hull del cubo unitario: volumen y area analiticos exactos ---
    cube = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1],
        [1, 1, 0], [1, 0, 1], [0, 1, 1], [1, 1, 1],
    ], dtype=float)
    hull_res = _convex_hull_reconstruction(cube)
    vol_diff = abs(hull_res["volume"] - 1.0)
    area_diff = abs(hull_res["surface_area"] - 6.0)
    checks.append({
        "name": "convex_hull_cubo_unitario_volumen",
        "expected": "1.0 (diff < 1e-9)",
        "got": {"volume": hull_res["volume"], "diff": round(vol_diff, 12)},
        "passed": bool(vol_diff < 1e-9),
    })
    checks.append({
        "name": "convex_hull_cubo_unitario_area",
        "expected": "6.0 (diff < 1e-9)",
        "got": {"surface_area": hull_res["surface_area"], "diff": round(area_diff, 12)},
        "passed": bool(area_diff < 1e-9),
    })

    # --- circumradio de un tetraedro regular: formula analitica R = a*sqrt(6)/4 ---
    a = 2.0  # longitud de arista
    # tetraedro regular con arista 'a' (coordenadas estandar)
    regular_tetra = np.array([
        [1, 1, 1],
        [1, -1, -1],
        [-1, 1, -1],
        [-1, -1, 1],
    ], dtype=float) * (a / (2 * np.sqrt(2)))
    edge_check = float(np.linalg.norm(regular_tetra[0] - regular_tetra[1]))
    R_mine, _ = _tetra_circumradius(regular_tetra)
    R_analitico = a * np.sqrt(6) / 4
    R_diff = abs(R_mine - R_analitico)
    checks.append({
        "name": "circumradio_tetraedro_regular_vs_formula_analitica",
        "expected": f"R = a*sqrt(6)/4 = {round(R_analitico, 8)} (diff < 1e-9, arista real={round(edge_check, 6)})",
        "got": round(R_mine, 8),
        "passed": bool(R_diff < 1e-9 and abs(edge_check - a) < 1e-9),
    })

    # --- alpha_shape con alpha grande sobre el cubo debe recuperar el hull completo ---
    alpha_res = _alpha_shape_3d(cube, alpha=10.0)
    vol_diff2 = abs(alpha_res["volume"] - 1.0)
    checks.append({
        "name": "alpha_shape_alpha_grande_vs_convex_hull_volumen",
        "expected": "volumen alpha_shape == volumen convex_hull == 1.0 (diff < 1e-9)",
        "got": {"alpha_shape_volume": alpha_res["volume"], "diff": round(vol_diff2, 12)},
        "passed": bool(vol_diff2 < 1e-9),
    })

    # --- alpha_shape sobre una esfera discretizada: sanity check aproximado ---
    sphere_pts = _fibonacci_sphere(300, radius=1.0)
    sphere_res = _alpha_shape_3d(sphere_pts, alpha=1.2)
    expected_vol = 4 / 3 * np.pi
    expected_area = 4 * np.pi
    vol_rel_err = abs(sphere_res["volume"] - expected_vol) / expected_vol
    area_rel_err = abs(sphere_res["surface_area"] - expected_area) / expected_area
    checks.append({
        "name": "alpha_shape_esfera_discretizada_volumen_aproximado",
        "expected": f"~{round(expected_vol, 4)} (error relativo < 15%, aproximacion numerica)",
        "got": {"volume": round(sphere_res["volume"], 4), "rel_error": round(vol_rel_err, 4)},
        "passed": bool(vol_rel_err < 0.15),
    })
    checks.append({
        "name": "alpha_shape_esfera_discretizada_area_aproximada",
        "expected": f"~{round(expected_area, 4)} (error relativo < 15%, aproximacion numerica)",
        "got": {"surface_area": round(sphere_res["surface_area"], 4), "rel_error": round(area_rel_err, 4)},
        "passed": bool(area_rel_err < 0.15),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}


if __name__ == "__main__":
    result = _validate_point_cloud_surface_reconstruction()
    for c in result["checks"]:
        status = "OK" if c["passed"] else "FALLO"
        print(f"[{status}] {c['name']}: esperado={c['expected']}  obtenido={c['got']}")
    print("\nTodas las validaciones pasaron." if result["all_passed"] else "\nHAY VALIDACIONES QUE FALLARON.")


POINT_CLOUD_SURFACE_RECONSTRUCTION_TOOL_SCHEMA = {
    "name": "point_cloud_surface_reconstruction",
    "description": (
        "Reconstruccion de superficie desde una nube de puntos: "
        "convex_hull (envolvente convexa via scipy, area y volumen "
        "exactos) y alpha_shape (superficie ajustada a concavidades, "
        "filtrado de tetraedros de Delaunay por circunradio < alpha, "
        "implementacion propia)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["convex_hull", "alpha_shape", "validate"]},
            "params": {"type": "object", "description": "Parametros especificos de cada modo, ver docstrings."},
        },
        "required": ["mode"],
    },
}


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass


def _handle(args):
    _params = args.get("params") or {}
    return compute_point_cloud_surface_reconstruction(mode=args["mode"], **_params)


register_tool("point_cloud_surface_reconstruction", POINT_CLOUD_SURFACE_RECONSTRUCTION_TOOL_SCHEMA, _handle)
