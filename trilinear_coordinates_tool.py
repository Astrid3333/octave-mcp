"""
trilinear_coordinates_tool.py

Coordenadas trilineales de un triángulo: normalización (distancias
reales a los lados), conversión hacia/desde baricéntricas, hacia/desde
cartesianas (dado un triángulo concreto), y trilineales de los cuatro
centros clásicos (incentro, centroide, circuncentro, ortocentro) en
función de los lados a,b,c.

Cierra el "área 4" (coordenadas en espacios abstractos / trilineales)
del roadmap: nicho autocontenido de geometría del triángulo, sin
solapamiento con el resto del repo.

Mismo patrón que space_curves_tool.py / curvilinear_coordinates_tool.py:
TOOL_SCHEMA, run(mode, params), run_self_test() -> {"checks",
"all_passed","total"}, __main__ con sys.argv[1]/sys.argv[2],
_register() vía tool_registry.register_tool(TOOL_SCHEMA["name"],
TOOL_SCHEMA, _handler).
"""

import json
import sys

import numpy as np


def _side_lengths_from_vertices(A, B, C):
    A, B, C = map(np.array, (A, B, C))
    a = float(np.linalg.norm(B - C))  # lado opuesto a A
    b = float(np.linalg.norm(C - A))  # lado opuesto a B
    c = float(np.linalg.norm(A - B))  # lado opuesto a C
    return a, b, c


def _area_from_sides(a, b, c):
    s = (a + b + c) / 2.0
    val = s * (s - a) * (s - b) * (s - c)
    if val < 0:
        raise ValueError("a,b,c no forman un triángulo válido (desigualdad triangular)")
    return float(np.sqrt(val))


def _angles_from_sides(a, b, c):
    """Ley de cosenos: ángulo A opuesto a a, etc."""
    cos_A = (b**2 + c**2 - a**2) / (2 * b * c)
    cos_B = (a**2 + c**2 - b**2) / (2 * a * c)
    cos_C = (a**2 + b**2 - c**2) / (2 * a * b)
    return (
        float(np.arccos(np.clip(cos_A, -1.0, 1.0))),
        float(np.arccos(np.clip(cos_B, -1.0, 1.0))),
        float(np.arccos(np.clip(cos_C, -1.0, 1.0))),
    )


def _get_sides(params):
    if "sides" in params:
        a, b, c = params["sides"]
        return float(a), float(b), float(c)
    if all(k in params for k in ("A", "B", "C")):
        return _side_lengths_from_vertices(params["A"], params["B"], params["C"])
    raise ValueError("se requiere 'sides': [a,b,c] o los vértices 'A','B','C'")


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------


def _mode_normalize(params):
    """Trilineales crudas (x:y:z, razón) -> trilineales reales (distancias a
    los lados), imponiendo a*x + b*y + c*z = 2*Area."""
    a, b, c = _get_sides(params)
    x, y, z = params["trilinear"]
    area = _area_from_sides(a, b, c)
    raw_sum = a * x + b * y + c * z
    if raw_sum == 0:
        raise ValueError("a*x + b*y + c*z = 0, no se puede normalizar (punto en el infinito)")
    k = (2 * area) / raw_sum
    actual = [k * x, k * y, k * z]
    return {
        "sides": [a, b, c],
        "area": area,
        "input_ratio": [x, y, z],
        "scale_factor": k,
        "trilinear_actual": actual,
        "check_sum_ax_by_cz": a * actual[0] + b * actual[1] + c * actual[2],
    }


def _mode_to_barycentric(params):
    a, b, c = _get_sides(params)
    x, y, z = params["trilinear"]
    bary_raw = [a * x, b * y, c * z]
    s = sum(bary_raw)
    bary_norm = [v / s for v in bary_raw] if s != 0 else None
    return {"trilinear": [x, y, z], "barycentric_ratio": bary_raw, "barycentric_normalized": bary_norm}


def _mode_from_barycentric(params):
    a, b, c = _get_sides(params)
    alpha, beta, gamma = params["barycentric"]
    tri = [alpha / a, beta / b, gamma / c]
    return {"barycentric": [alpha, beta, gamma], "trilinear_ratio": tri}


def _mode_to_cartesian(params):
    """Requiere vértices A,B,C cartesianos concretos (no solo lados)."""
    if not all(k in params for k in ("A", "B", "C")):
        raise ValueError("to_cartesian requiere los vértices 'A','B','C'")
    A = np.array(params["A"], dtype=float)
    B = np.array(params["B"], dtype=float)
    C = np.array(params["C"], dtype=float)
    a, b, c = _side_lengths_from_vertices(A, B, C)
    x, y, z = params["trilinear"]
    bary_raw = np.array([a * x, b * y, c * z])
    s = bary_raw.sum()
    if s == 0:
        raise ValueError("suma baricéntrica nula, punto en el infinito")
    alpha, beta, gamma = bary_raw / s
    P = alpha * A + beta * B + gamma * C
    return {"trilinear": [x, y, z], "barycentric_normalized": [float(alpha), float(beta), float(gamma)], "cartesian": P.tolist()}


def _mode_from_cartesian(params):
    """Punto cartesiano -> trilineales, dado un triángulo A,B,C concreto."""
    if not all(k in params for k in ("A", "B", "C", "point")):
        raise ValueError("from_cartesian requiere 'A','B','C' y 'point'")
    A = np.array(params["A"], dtype=float)
    B = np.array(params["B"], dtype=float)
    C = np.array(params["C"], dtype=float)
    P = np.array(params["point"], dtype=float)
    a, b, c = _side_lengths_from_vertices(A, B, C)
    area_total = _area_from_sides(a, b, c)

    def _tri_area(P1, P2, P3):
        # cross product 2D explícito (evita el warning de deprecación de
        # np.cross para vectores de 2 componentes en NumPy 2.0+)
        v1, v2 = P2 - P1, P3 - P1
        return 0.5 * abs(v1[0] * v2[1] - v1[1] * v2[0])

    alpha = _tri_area(P, B, C) / area_total
    beta = _tri_area(P, C, A) / area_total
    gamma = _tri_area(P, A, B) / area_total
    # trilineales (no normalizadas): x:y:z = alpha/a : beta/b : gamma/c
    tri_ratio = [alpha / a, beta / b, gamma / c]
    norm = _mode_normalize({"sides": [a, b, c], "trilinear": tri_ratio})
    return {
        "point": params["point"],
        "barycentric_normalized": [float(alpha), float(beta), float(gamma)],
        "trilinear_actual": norm["trilinear_actual"],
    }


def _mode_triangle_centers(params):
    a, b, c = _get_sides(params)
    A, B, C = _angles_from_sides(a, b, c)
    cosA, cosB, cosC = np.cos(A), np.cos(B), np.cos(C)

    centers = {
        "incenter": [1.0, 1.0, 1.0],
        "centroid": [1.0 / a, 1.0 / b, 1.0 / c],
        "circumcenter": [float(cosA), float(cosB), float(cosC)],
        "orthocenter": [float(cosB * cosC), float(cosC * cosA), float(cosA * cosB)],
    }
    return {"sides": [a, b, c], "angles_rad": [A, B, C], "trilinear_ratio": centers}


def _mode_list_centers(_params):
    return {"centers": ["incenter", "centroid", "circumcenter", "orthocenter"]}


_DISPATCH = {
    "normalize": _mode_normalize,
    "to_barycentric": _mode_to_barycentric,
    "from_barycentric": _mode_from_barycentric,
    "to_cartesian": _mode_to_cartesian,
    "from_cartesian": _mode_from_cartesian,
    "triangle_centers": _mode_triangle_centers,
    "list_centers": _mode_list_centers,
}


TOOL_SCHEMA = {
    "name": "trilinear_coordinates",
    "description": (
        "Coordenadas trilineales de un triángulo: normalización a distancias "
        "reales a los lados, conversión hacia/desde baricéntricas y "
        "cartesianas, y trilineales de incentro/centroide/circuncentro/"
        "ortocentro a partir de los lados a,b,c."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "normalize",
                    "to_barycentric",
                    "from_barycentric",
                    "to_cartesian",
                    "from_cartesian",
                    "triangle_centers",
                    "list_centers",
                    "validate",
                    "self_test",
                ],
            },
            "params": {
                "type": "object",
                "properties": {
                    "sides": {"type": "array", "description": "[a,b,c], lados opuestos a A,B,C"},
                    "A": {"type": "array", "description": "vértice A cartesiano (alternativa a 'sides')"},
                    "B": {"type": "array", "description": "vértice B cartesiano"},
                    "C": {"type": "array", "description": "vértice C cartesiano"},
                    "trilinear": {"type": "array", "description": "[x,y,z] trilineales (razón o reales)"},
                    "barycentric": {"type": "array", "description": "[alpha,beta,gamma] baricéntricas"},
                    "point": {"type": "array", "description": "punto cartesiano (modo from_cartesian)"},
                },
            },
        },
        "required": ["mode"],
    },
}


def run_self_test():
    checks = []

    # 1) normalize: triángulo 3-4-5 (área = 6), incentro 1:1:1 -> radio inscripto r = area/s = 6/6 = 1
    n = _mode_normalize({"sides": [3.0, 4.0, 5.0], "trilinear": [1.0, 1.0, 1.0]})
    checks.append({
        "name": "normalize_incenter_345_radius",
        "passed": bool(
            abs(n["trilinear_actual"][0] - 1.0) < 1e-8
            and abs(n["trilinear_actual"][1] - 1.0) < 1e-8
            and abs(n["trilinear_actual"][2] - 1.0) < 1e-8
        ),
    })

    # 2) check_sum_ax_by_cz siempre da 2*Area
    checks.append({
        "name": "normalize_area_identity",
        "passed": bool(abs(n["check_sum_ax_by_cz"] - 2 * n["area"]) < 1e-8),
    })

    # 3) área del 3-4-5 es exactamente 6
    checks.append({"name": "area_345", "passed": bool(abs(n["area"] - 6.0) < 1e-8)})

    # 4) equilátero: los 4 centros clásicos coinciden en trilineales 1:1:1
    tc = _mode_triangle_centers({"sides": [5.0, 5.0, 5.0]})
    ok = True
    for name in ("incenter", "centroid", "circumcenter", "orthocenter"):
        vals = tc["trilinear_ratio"][name]
        v0 = vals[0]
        if v0 == 0 or any(abs(v / v0 - 1.0) > 1e-6 for v in vals):
            ok = False
    checks.append({"name": "equilateral_centers_coincide", "passed": bool(ok)})

    # 5) centroide 3-4-5: razón 1/a:1/b:1/c
    tc345 = _mode_triangle_centers({"sides": [3.0, 4.0, 5.0]})
    cen = tc345["trilinear_ratio"]["centroid"]
    checks.append({
        "name": "centroid_ratio_345",
        "passed": bool(
            abs(cen[0] - 1.0 / 3.0) < 1e-8
            and abs(cen[1] - 1.0 / 4.0) < 1e-8
            and abs(cen[2] - 1.0 / 5.0) < 1e-8
        ),
    })

    # 6) to_barycentric / from_barycentric son inversos
    bc = _mode_to_barycentric({"sides": [3.0, 4.0, 5.0], "trilinear": [1.0, 1.0, 1.0]})
    back = _mode_from_barycentric({"sides": [3.0, 4.0, 5.0], "barycentric": bc["barycentric_ratio"]})
    ratio0 = back["trilinear_ratio"][0] / 1.0
    checks.append({
        "name": "barycentric_roundtrip",
        "passed": bool(all(abs(v / ratio0 - 1.0) < 1e-8 for v in back["trilinear_ratio"])),
    })

    # 7) to_cartesian del incentro coincide con la fórmula estándar
    #    incentro = (a*A + b*B + c*C) / (a+b+c)
    A, B, C = [0.0, 0.0], [4.0, 0.0], [0.0, 3.0]  # triángulo 3-4-5 rectángulo
    a, b, c = _side_lengths_from_vertices(A, B, C)
    expected_incenter = (
        a * np.array(A) + b * np.array(B) + c * np.array(C)
    ) / (a + b + c)
    tcart = _mode_to_cartesian({"A": A, "B": B, "C": C, "trilinear": [1.0, 1.0, 1.0]})
    checks.append({
        "name": "to_cartesian_incenter",
        "passed": bool(np.allclose(tcart["cartesian"], expected_incenter, atol=1e-8)),
    })

    # 8) from_cartesian del centroide real recupera razón 1:1:1 en baricéntricas
    centroid_point = (np.array(A) + np.array(B) + np.array(C)) / 3.0
    fc = _mode_from_cartesian({"A": A, "B": B, "C": C, "point": centroid_point.tolist()})
    bary = fc["barycentric_normalized"]
    checks.append({
        "name": "from_cartesian_centroid",
        "passed": bool(np.allclose(bary, [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0], atol=1e-8)),
    })

    # 9) round-trip to_cartesian -> from_cartesian para un punto arbitrario (no un centro)
    tri_in = [0.5, 2.0, 1.3]
    tc_pt = _mode_to_cartesian({"A": A, "B": B, "C": C, "trilinear": tri_in})
    fc_pt = _mode_from_cartesian({"A": A, "B": B, "C": C, "point": tc_pt["cartesian"]})
    norm_in = _mode_normalize({"sides": [a, b, c], "trilinear": tri_in})
    checks.append({
        "name": "cartesian_roundtrip_arbitrary_point",
        "passed": bool(np.allclose(fc_pt["trilinear_actual"], norm_in["trilinear_actual"], atol=1e-6)),
    })

    # 10) sides inválidos (desigualdad triangular violada) levanta error
    try:
        _mode_normalize({"sides": [1.0, 1.0, 10.0], "trilinear": [1.0, 1.0, 1.0]})
        invalid_ok = False
    except ValueError:
        invalid_ok = True
    checks.append({"name": "invalid_triangle_raises", "passed": bool(invalid_ok)})

    all_passed = all(chk["passed"] for chk in checks)
    return {"checks": checks, "all_passed": all_passed, "total": len(checks)}


def run(mode, params=None):
    params = params or {}
    if mode in ("validate", "self_test"):
        return run_self_test()
    if mode not in _DISPATCH:
        raise ValueError(
            f"modo desconocido: {mode} (usar " + "/".join(list(_DISPATCH) + ["validate", "self_test"]) + ")"
        )
    return _DISPATCH[mode](params)


def compute_trilinear_coordinates(mode, params=None):
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
    Auto-registro estilo octave-mcp (patrón self-registrante vía
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
