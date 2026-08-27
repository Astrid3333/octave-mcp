"""
projective_geometry_tool.py

Área 4 del roadmap de geometría: geometría proyectiva.
Cobertura: coordenadas homogéneas en P² y P³ (con transformaciones/proyección
entre ambos), incidencia y colinealidad/concurrencia (con chequeo de los
teoremas de Desargues y Pappus), razón cruzada y proyectividades 1D, y
cónicas proyectivas (ajuste por 5 puntos, polar/tangente, intersección
cónica-recta).

Mismo patrón que las otras tools: TOOL_SCHEMA, run() dispatcher,
run_self_test()/validate, bloque __main__, _register() al final.
AJUSTAR el import de tool_registry según la convención real del repo.
"""

import json
import sys

import numpy as np

# ---------------------------------------------------------------------------
# TOOL SCHEMA
# ---------------------------------------------------------------------------

TOOL_SCHEMA = {
    "name": "projective_geometry",
    "description": (
        "Geometría proyectiva: coordenadas homogéneas P²/P³, incidencia y "
        "colinealidad/concurrencia (Desargues, Pappus), razón cruzada y "
        "proyectividades 1D, cónicas proyectivas (ajuste, polar/tangente, "
        "intersección con recta)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "homogeneous_convert",
                    "incidence",
                    "desargues_check",
                    "pappus_check",
                    "cross_ratio",
                    "projectivity_1d",
                    "conic_fit",
                    "conic_tangent_or_polar",
                    "conic_line_intersection",
                    "projection_p3_to_p2",
                    "validate",
                    "self_test",
                ],
            },
        },
        "required": ["mode"],
        "additionalProperties": True,
    },
}

_TOL = 1e-8


# ---------------------------------------------------------------------------
# Helpers generales
# ---------------------------------------------------------------------------

def _to_homog(coords):
    """Lista de coords afines -> vector homogéneo (agrega w=1)."""
    return np.array(list(coords) + [1.0], dtype=float)


def _normalize(v):
    v = np.array(v, dtype=float)
    idx = np.argmax(np.abs(v))
    if abs(v[idx]) < _TOL:
        return v
    return v / v[idx]


def _det_rows(*vectors):
    return float(np.linalg.det(np.array(vectors, dtype=float)))


def _line_through(p, q):
    """Recta en P² que pasa por p y q (producto cruz de sus coords homog.)."""
    return np.cross(np.array(p, dtype=float), np.array(q, dtype=float))


def _point_intersection(l1, l2):
    """Intersección de dos rectas en P² (dual del producto cruz)."""
    return np.cross(np.array(l1, dtype=float), np.array(l2, dtype=float))


def _collinear(points, tol=1e-6):
    """points: lista de 3 vectores homogéneos en P². True si det==0."""
    M = np.array(points, dtype=float)
    det = float(np.linalg.det(M))
    # bool() explícito: np.linalg.det da np.float64, y la comparación "<"
    # produce numpy.bool_ (no serializable por json.dumps sin cast).
    return bool(abs(det) < tol), det


# ---------------------------------------------------------------------------
# homogeneous_convert
# ---------------------------------------------------------------------------

def _mode_homogeneous_convert(params):
    space = params["space"]  # "P2" o "P3"
    direction = params["direction"]  # "to_homogeneous" o "to_affine"
    coords = params["coords"]
    expected_len = 2 if space == "P2" else 3
    if direction == "to_homogeneous":
        if len(coords) != expected_len:
            raise ValueError(f"{space} afín espera {expected_len} coords, recibí {len(coords)}")
        h = _to_homog(coords)
        return {"space": space, "affine": coords, "homogeneous": h.tolist()}
    elif direction == "to_affine":
        h = np.array(coords, dtype=float)
        if len(h) != expected_len + 1:
            raise ValueError(f"{space} homogéneo espera {expected_len + 1} coords, recibí {len(h)}")
        if abs(h[-1]) < _TOL:
            return {"space": space, "homogeneous": coords, "affine": None,
                     "note": "punto en el infinito (w≈0), no tiene representación afín"}
        affine = (h[:-1] / h[-1]).tolist()
        return {"space": space, "homogeneous": coords, "affine": affine}
    else:
        raise ValueError(f"direction desconocida: {direction}")


# ---------------------------------------------------------------------------
# incidence
# ---------------------------------------------------------------------------

def _mode_incidence(params):
    space = params["space"]
    kind = params["kind"]  # "collinear_points" | "concurrent_lines" | "point_on_line" | "point_on_plane"
    if kind == "collinear_points":
        pts = [np.array(p, dtype=float) for p in params["points"]]
        is_col, det = _collinear(pts)
        return {"kind": kind, "collinear": is_col, "det": det}
    elif kind == "concurrent_lines":
        lns = [np.array(l, dtype=float) for l in params["lines"]]
        is_conc, det = _collinear(lns)  # dual: mismo criterio de det==0
        return {"kind": kind, "concurrent": is_conc, "det": det}
    elif kind == "point_on_line":
        p = np.array(params["point"], dtype=float)
        l = np.array(params["line"], dtype=float)
        val = float(p.dot(l))
        return {"kind": kind, "incident": abs(val) < 1e-6, "value": val}
    elif kind == "point_on_plane":
        p = np.array(params["point"], dtype=float)  # 4-vector P3
        pi = np.array(params["plane"], dtype=float)  # 4-vector P3
        val = float(p.dot(pi))
        return {"kind": kind, "incident": abs(val) < 1e-6, "value": val}
    else:
        raise ValueError(f"kind desconocido: {kind}")


# ---------------------------------------------------------------------------
# Desargues / Pappus
# ---------------------------------------------------------------------------

def _mode_desargues_check(params):
    """Dadas 2 triángulos A,B,C / A',B',C' (homog. P2), chequea las dos
    formulaciones equivalentes del teorema: perspectiva desde un punto
    (AA', BB', CC' concurrentes) <=> perspectiva desde una recta
    (AB∩A'B', BC∩B'C', CA∩C'A' colineales)."""
    A, B, C = [np.array(x, dtype=float) for x in params["triangle1"]]
    A2, B2, C2 = [np.array(x, dtype=float) for x in params["triangle2"]]

    l_AA = _line_through(A, A2)
    l_BB = _line_through(B, B2)
    l_CC = _line_through(C, C2)
    conc, det_center = _collinear([l_AA, l_BB, l_CC])

    p1 = _point_intersection(_line_through(A, B), _line_through(A2, B2))
    p2 = _point_intersection(_line_through(B, C), _line_through(B2, C2))
    p3 = _point_intersection(_line_through(C, A), _line_through(C2, A2))
    col, det_axis = _collinear([p1, p2, p3])

    return {
        "perspective_from_point": conc, "det_concurrency": det_center,
        "perspective_from_line": col, "det_collinearity": det_axis,
        "desargues_holds": conc and col,
        "axis_points": [p1.tolist(), p2.tolist(), p3.tolist()],
    }


def _mode_pappus_check(params):
    """Puntos A,B,C colineales sobre l1; A',B',C' colineales sobre l2.
    Teorema: X=AB'∩A'B, Y=AC'∩A'C, Z=BC'∩B'C son colineales."""
    A, B, C = [np.array(x, dtype=float) for x in params["line1_points"]]
    A2, B2, C2 = [np.array(x, dtype=float) for x in params["line2_points"]]

    col1, _ = _collinear([A, B, C])
    col2, _ = _collinear([A2, B2, C2])
    if not (col1 and col2):
        return {"error": "los puntos de entrada no son colineales en su propia recta",
                "line1_collinear": col1, "line2_collinear": col2}

    X = _point_intersection(_line_through(A, B2), _line_through(A2, B))
    Y = _point_intersection(_line_through(A, C2), _line_through(A2, C))
    Z = _point_intersection(_line_through(B, C2), _line_through(B2, C))
    col, det = _collinear([X, Y, Z])

    return {
        "pappus_holds": col, "det_collinearity": det,
        "pappus_line_points": [X.tolist(), Y.tolist(), Z.tolist()],
    }


# ---------------------------------------------------------------------------
# Razón cruzada / proyectividades 1D
# ---------------------------------------------------------------------------

def _line_parameters(points):
    """4 puntos homogéneos P2 colineales -> parámetro escalar t_i tal que
    p_i ≈ p0 + t_i*(p1-p0) (basis afín sobre la recta que contienen)."""
    pts = [np.array(p, dtype=float) for p in points]
    is_col, det = _collinear(pts[:3])
    if not is_col:
        raise ValueError(f"los primeros 3 puntos no son colineales (det={det})")
    p0, p1 = pts[0], pts[1]
    d = p1 - p0
    # elegir la coordenada con mayor variación para proyectar el parámetro
    idx = int(np.argmax(np.abs(d)))
    ts = []
    for p in pts:
        denom = d[idx]
        t = (p[idx] - p0[idx]) / denom if abs(denom) > _TOL else float("nan")
        ts.append(t)
    return ts


def _cross_ratio_from_t(t1, t2, t3, t4):
    return ((t3 - t1) * (t4 - t2)) / ((t3 - t2) * (t4 - t1))


def _mode_cross_ratio(params):
    pts = params["points"]  # 4 puntos homogéneos colineales
    t1, t2, t3, t4 = _line_parameters(pts)
    cr = _cross_ratio_from_t(t1, t2, t3, t4)
    return {"parameters": [t1, t2, t3, t4], "cross_ratio": cr}


def _mode_projectivity_1d(params):
    """Ajusta t' = (a t + b)/(c t + d) a partir de 3 pares (t_i, t_i'),
    aplica a un t4 nuevo para obtener t4'."""
    corr = params["correspondences"]  # [[t1,t1p], [t2,t2p], [t3,t3p]]
    t_new = params["t_new"]
    if len(corr) != 3:
        raise ValueError("se necesitan exactamente 3 correspondencias")

    # Sistema lineal homogéneo en (a,b,c,d): a*t + b - t'*c*t - t'*d = 0
    rows = []
    for t, tp in corr:
        rows.append([t, 1.0, -tp * t, -tp])
    M = np.array(rows, dtype=float)
    # una ecuación libre (escala): fijamos d=1 y resolvemos el sistema 3x3
    # restante; si d resulta ~0 en la solución exacta, caemos a SVD/nullspace.
    A3 = M[:, :3]
    rhs = -M[:, 3]
    try:
        sol = np.linalg.solve(A3, rhs)
        a, b, c = sol
        d = 1.0
    except np.linalg.LinAlgError:
        _, _, Vt = np.linalg.svd(M)
        a, b, c, d = Vt[-1]

    def mobius(t):
        denom = c * t + d
        if abs(denom) < _TOL:
            return None  # imagen en el infinito
        return (a * t + b) / denom

    t_new_image = mobius(t_new)
    check_errors = [abs(mobius(t) - tp) for t, tp in corr if mobius(t) is not None]
    return {
        "coefficients": {"a": a, "b": b, "c": c, "d": d},
        "t_new": t_new, "t_new_image": t_new_image,
        "max_fit_residual": max(check_errors) if check_errors else None,
    }


# ---------------------------------------------------------------------------
# Cónicas
# ---------------------------------------------------------------------------

def _conic_row(p):
    x, y, w = p
    return [x * x, x * y, y * y, x * w, y * w, w * w]


def _mode_conic_fit(params):
    pts = [np.array(p, dtype=float) for p in params["points"]]
    if len(pts) != 5:
        raise ValueError("se necesitan exactamente 5 puntos para ajustar una cónica")
    M = np.array([_conic_row(p) for p in pts], dtype=float)
    _, _, Vt = np.linalg.svd(M)
    a, b, c, d, e, f = Vt[-1]
    C = np.array([[a, b / 2, d / 2],
                  [b / 2, c, e / 2],
                  [d / 2, e / 2, f]], dtype=float)
    residuals = [float(p.dot(C).dot(p)) for p in pts]
    return {
        "conic_matrix": C.tolist(),
        "coefficients_xy": {"a": a, "b": b, "c": c, "d": d, "e": e, "f": f},
        "max_abs_residual_on_points": max(abs(r) for r in residuals),
    }


def _mode_conic_tangent_or_polar(params):
    C = np.array(params["conic_matrix"], dtype=float)
    p = np.array(params["point"], dtype=float)
    on_conic = abs(float(p.dot(C).dot(p))) < 1e-6
    line = C.dot(p)
    return {
        "point_on_conic": on_conic,
        "line": line.tolist(),
        "role": "tangent" if on_conic else "polar",
    }


def _mode_conic_line_intersection(params):
    C = np.array(params["conic_matrix"], dtype=float)
    l = np.array(params["line"], dtype=float)
    # 2 puntos base sobre la recta l: cualquier par de soluciones
    # independientes de l·x=0. Se construyen vía producto cruz con dos
    # vectores base no paralelos a l.
    e1, e2 = np.array([1.0, 0, 0]), np.array([0, 1.0, 0])
    base1 = np.cross(l, e1)
    base2 = np.cross(l, e2)
    p0 = base1 if np.linalg.norm(base1) > 1e-9 else base2
    # segundo punto independiente sobre la recta
    e3 = np.array([0, 0, 1.0])
    p1c = np.cross(l, e3)
    if np.linalg.norm(np.cross(p0, p1c)) < 1e-9:
        p1c = base2
    p1c = p1c / np.linalg.norm(p1c)
    p0 = p0 / np.linalg.norm(p0)

    # parametrizar x(s) = p0 + s*p1 y resolver x^T C x = 0 (cuadrática en s)
    A = float(p1c.dot(C).dot(p1c))
    B = float(2 * p0.dot(C).dot(p1c))
    Cc = float(p0.dot(C).dot(p0))
    if abs(A) < 1e-12:
        if abs(B) < 1e-12:
            return {"intersection_type": "no_solution_or_degenerate", "points": []}
        s = -Cc / B
        pt = _normalize(p0 + s * p1c)
        return {"intersection_type": "tangent_or_single", "points": [pt.tolist()]}
    disc = B * B - 4 * A * Cc
    if disc < -1e-9:
        return {"intersection_type": "no_real_intersection", "discriminant": disc, "points": []}
    disc = max(disc, 0.0)
    s1 = (-B + disc ** 0.5) / (2 * A)
    s2 = (-B - disc ** 0.5) / (2 * A)
    pt1 = _normalize(p0 + s1 * p1c)
    pt2 = _normalize(p0 + s2 * p1c)
    kind = "tangent" if disc < 1e-9 else "secant"
    return {"intersection_type": kind, "discriminant": disc, "points": [pt1.tolist(), pt2.tolist()]}


# ---------------------------------------------------------------------------
# Proyección P3 -> P2
# ---------------------------------------------------------------------------

def _mode_projection_p3_to_p2(params):
    P = np.array(params["projection_matrix"], dtype=float)  # 3x4
    pt3 = np.array(params["point_p3_homogeneous"], dtype=float)  # 4-vector
    if P.shape != (3, 4):
        raise ValueError(f"projection_matrix debe ser 3x4, recibí {P.shape}")
    if pt3.shape != (4,):
        raise ValueError("point_p3_homogeneous debe tener 4 componentes")
    result = P.dot(pt3)
    return {"point_p2_homogeneous": result.tolist()}


# ---------------------------------------------------------------------------
# validate / self_test
# ---------------------------------------------------------------------------

def run_self_test():
    """Devuelve {"checks": [...], "all_passed": bool, "total": int} —
    mismo shape que fungal_morphology_tool.py / mycelial_network_tool.py."""
    checks = []

    def _sanitize(v):
        """Cast recursivo de tipos numpy (bool_, float64, ndarray) a nativos
        de Python -- json.dumps no serializa numpy.bool_/float64 directo."""
        if isinstance(v, (np.bool_, bool)):
            return bool(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, np.ndarray):
            return v.tolist()
        if isinstance(v, dict):
            return {k: _sanitize(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [_sanitize(x) for x in v]
        return v

    def check(name, passed, **extra):
        entry = {"name": name, "passed": bool(passed)}
        entry.update({k: _sanitize(v) for k, v in extra.items()})
        checks.append(entry)

    # --- homogeneous_convert round-trip ---
    r1 = _mode_homogeneous_convert({"space": "P2", "direction": "to_homogeneous", "coords": [3.0, -2.0]})
    r2 = _mode_homogeneous_convert({"space": "P2", "direction": "to_affine", "coords": r1["homogeneous"]})
    check("homogeneous_roundtrip_P2", np.allclose(r2["affine"], [3.0, -2.0]), affine_back=r2["affine"])

    # --- incidencia: 3 puntos colineales conocidos ---
    inc = _mode_incidence({"space": "P2", "kind": "collinear_points",
                            "points": [[0, 0, 1], [1, 1, 1], [2, 2, 1]]})
    check("collinear_points_known_case", inc["collinear"], det=inc["det"])

    inc2 = _mode_incidence({"space": "P2", "kind": "collinear_points",
                             "points": [[0, 0, 1], [1, 1, 1], [2, 3, 1]]})
    check("noncollinear_points_known_case", not inc2["collinear"], det=inc2["det"])

    # --- Desargues con triángulos en perspectiva central desde el origen ---
    A, B, C = [1.0, 0.0, 1.0], [0.0, 1.0, 1.0], [1.0, 1.0, 1.0]
    k = 2.0
    A2, B2, C2 = [k * A[0], k * A[1], 1.0], [k * B[0], k * B[1], 1.0], [k * C[0], k * C[1], 1.0]
    des = _mode_desargues_check({"triangle1": [A, B, C], "triangle2": [A2, B2, C2]})
    check("desargues_central_scaling", des["desargues_holds"],
          det_concurrency=des["det_concurrency"], det_collinearity=des["det_collinearity"])

    # --- Pappus con puntos sobre dos rectas conocidas ---
    l1_pts = [[0, 0, 1], [1, 0, 1], [2, 0, 1]]
    l2_pts = [[0, 1, 1], [1, 2, 1], [3, 4, 1]]
    pap = _mode_pappus_check({"line1_points": l1_pts, "line2_points": l2_pts})
    check("pappus_known_lines", pap.get("pappus_holds", False), result=pap)

    # --- Razón cruzada: caso armónico (CR = -1) ---
    pts_cr = [[0, 0, 1], [1, 0, 1], [2, 0, 1], [-2, 0, 1]]  # t = 0,1,2,-2
    cr = _mode_cross_ratio({"points": pts_cr})
    # CR(0,1;2,-2) = ((2-0)(-2-1))/((2-1)(-2-0)) = (2*-3)/(1*-2) = -6/-2 = 3
    expected_cr = ((2 - 0) * (-2 - 1)) / ((2 - 1) * (-2 - 0))
    check("cross_ratio_known_points", abs(cr["cross_ratio"] - expected_cr) < 1e-9,
          computed=cr["cross_ratio"], expected=expected_cr)

    # --- Proyectividad 1D: identidad (t'=t) recuperada exacta ---
    proj = _mode_projectivity_1d({
        "correspondences": [[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]], "t_new": 5.0,
    })
    check("projectivity_identity_recovers_t", abs(proj["t_new_image"] - 5.0) < 1e-6,
          t_new_image=proj["t_new_image"])

    # --- Cónica: círculo unitario ajustado por 5 puntos, chequeo x^2+y^2-1 ---
    import math
    angles = [0, 1.1, 2.3, 3.7, 5.0]
    circle_pts = [[math.cos(a), math.sin(a), 1.0] for a in angles]
    fit = _mode_conic_fit({"points": circle_pts})
    check("conic_fit_unit_circle_low_residual", fit["max_abs_residual_on_points"] < 1e-8,
          max_abs_residual=fit["max_abs_residual_on_points"])

    C_unit = np.array(fit["conic_matrix"])
    tangent_test = _mode_conic_tangent_or_polar({"conic_matrix": C_unit.tolist(),
                                                   "point": [1.0, 0.0, 1.0]})
    check("conic_tangent_at_point_on_circle", tangent_test["point_on_conic"] and tangent_test["role"] == "tangent")

    # --- Intersección cónica-recta: recta y=0 corta círculo unitario en (±1,0) ---
    inter = _mode_conic_line_intersection({"conic_matrix": C_unit.tolist(), "line": [0.0, 1.0, 0.0]})
    xs = sorted(p[0] / p[2] for p in inter["points"])
    check("conic_line_intersection_unit_circle_y0",
          len(inter["points"]) == 2 and abs(xs[0] - (-1.0)) < 1e-4 and abs(xs[1] - 1.0) < 1e-4,
          points=inter["points"])

    # --- Proyección P3->P2 con matriz identidad truncada ---
    P_id = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]]
    proj32 = _mode_projection_p3_to_p2({"projection_matrix": P_id, "point_p3_homogeneous": [3.0, -1.0, 2.0, 1.0]})
    check("projection_p3_to_p2_identity_truncation",
          np.allclose(proj32["point_p2_homogeneous"], [3.0, -1.0, 2.0]))

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "all_passed": all_passed, "total": len(checks)}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_DISPATCH = {
    "homogeneous_convert": _mode_homogeneous_convert,
    "incidence": _mode_incidence,
    "desargues_check": _mode_desargues_check,
    "pappus_check": _mode_pappus_check,
    "cross_ratio": _mode_cross_ratio,
    "projectivity_1d": _mode_projectivity_1d,
    "conic_fit": _mode_conic_fit,
    "conic_tangent_or_polar": _mode_conic_tangent_or_polar,
    "conic_line_intersection": _mode_conic_line_intersection,
    "projection_p3_to_p2": _mode_projection_p3_to_p2,
}


def run(mode, params=None):
    params = params or {}
    if mode == "validate":
        r = run_self_test()
        return {"checks": r["checks"], "validation_passed": r["all_passed"], "n_checks": r["total"]}
    elif mode == "self_test":
        return run_self_test()
    elif mode in _DISPATCH:
        return _DISPATCH[mode](params)
    else:
        raise ValueError(
            f"modo desconocido: {mode} (usar " + "/".join(list(_DISPATCH) + ["validate", "self_test"]) + ")"
        )


def compute_projective_geometry(mode, params=None):
    """Alias público, mismo naming convention que las otras tools."""
    return run(mode, params)


if __name__ == "__main__":
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "self_test"
    params_arg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    try:
        out = run(mode_arg, params_arg)
        print(json.dumps(out, indent=2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)


def _register():
    """
    Auto-registro estilo octave-mcp (patron self-registrante via
    tool_registry, register_tool(name, schema, handler)).
    """
    try:
        import tool_registry
        def _handler(args):
            return run(args.get("mode"), args.get("params"))
        tool_registry.register_tool(TOOL_SCHEMA["name"], TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()
