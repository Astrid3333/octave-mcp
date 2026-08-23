"""
linear_transform_figure_tool.py

Transformaciones lineales aplicadas a una figura geometrica concreta (no
al analisis abstracto de la matriz, que ya cubre linear_algebra_tool con
SVD/eigen/determinante). Cierra el gap #4 (ultimo del roadmap original de
5 areas): tomar una matriz A de 2x2, aplicarla a un poligono, comparar
area antes/despues, factor de escala via determinante, y descomponer la
transformacion en rotacion+escala+cizallamiento (descomposicion polar).

Teoria (recordatorio breve):
  - area(A*poligono) = |det(A)| * area(poligono) -- teorema fundamental
    del cambio de variable lineal en 2D, exacto para cualquier poligono.
  - signo del area con signo (formula de Shoelace) indica orientacion
    (antihoraria si >0); si det(A)<0 la transformacion invierte la
    orientacion (reflexion), aunque el area sin signo se preserve segun
    |det(A)|.
  - Descomposicion polar A = R*S: R ortogonal (rotacion pura o rotacion+
    reflexion si det(R)=-1), S simetrica semidefinida positiva (el
    "cizallamiento+escala" puro, sin rotacion). S diagonalizable con
    autovalores = factores de escala principales (ejes de la elipse
    imagen del circulo unitario). R*S se obtiene via SVD: A = U*Sigma*V^T
    => R = U*V^T, S = V*Sigma*V^T.

Modos:
  - apply_to_polygon: dado 'vertices' (lista de [x,y]) y 'matrix' (2x2,
    lista de listas), aplica A a cada vertice, calcula area con signo
    antes/despues (formula de Shoelace) y compara la razon de areas
    contra |det(A)|.
  - decompose: dado 'matrix' (2x2), devuelve determinante, traza,
    autovalores, y la descomposicion polar A=R*S (R=rotacion/reflexion,
    S=escala+cizallamiento puro) via SVD, mas el angulo de rotacion de R
    en grados y los factores de escala principales (autovalores de S).
  - validate: 6 auto-chequeos (escala diagonal sobre cuadrado unitario,
    rotacion pura preserva area y distancias al origen, cizallamiento
    con det=1 preserva area pero cambia forma, reflexion con det=-1
    invierte el signo del area sin cambiar su magnitud, poligono
    arbitrario con matriz generica confirma |det(A)| en todos los casos,
    descomposicion polar reconstruye A=R*S exactamente).

Mismo patron que las otras tools del server: TOOL_SCHEMA, run(mode,
**params), validate() -> {"checks","all_passed","total",
"validation_passed"}, __main__ con sys.argv, _register() via
tool_registry.register_tool(TOOL_SCHEMA["name"], TOOL_SCHEMA, _handler).
"""

import json
import sys

import numpy as np


# ---------------------------------------------------------------------
# nucleo
# ---------------------------------------------------------------------

def _signed_area(vertices):
    v = np.asarray(vertices, dtype=float)
    x, y = v[:, 0], v[:, 1]
    x_next = np.roll(x, -1)
    y_next = np.roll(y, -1)
    return 0.5 * float(np.sum(x * y_next - x_next * y))


def apply_to_polygon(vertices, matrix):
    v = np.asarray(vertices, dtype=float)
    A = np.asarray(matrix, dtype=float)
    if A.shape != (2, 2):
        raise ValueError("matrix debe ser 2x2")
    if v.ndim != 2 or v.shape[1] != 2 or v.shape[0] < 3:
        raise ValueError("vertices debe ser una lista de al menos 3 puntos [x,y]")

    area_before = _signed_area(v)
    v_transformed = (A @ v.T).T
    area_after = _signed_area(v_transformed)

    det = float(np.linalg.det(A))
    ratio = area_after / area_before if area_before != 0 else float("nan")

    return {
        "vertices_before": v.tolist(),
        "vertices_after": v_transformed.tolist(),
        "matrix": A.tolist(),
        "determinant": det,
        "signed_area_before": area_before,
        "signed_area_after": area_after,
        "area_ratio_after_over_before": ratio,
        "area_ratio_matches_abs_det": bool(abs(abs(ratio) - abs(det)) < 1e-9 * max(1.0, abs(det))),
        "orientation_reversed": bool((area_before > 0) != (area_after > 0)),
        "orientation_reversed_matches_negative_det": bool(
            ((area_before > 0) != (area_after > 0)) == (det < 0)
        ),
    }


def decompose(matrix):
    A = np.asarray(matrix, dtype=float)
    if A.shape != (2, 2):
        raise ValueError("matrix debe ser 2x2")

    det = float(np.linalg.det(A))
    trace = float(np.trace(A))
    eigvals = np.linalg.eigvals(A)

    U, sigma, Vt = np.linalg.svd(A)
    R = U @ Vt
    S = Vt.T @ np.diag(sigma) @ Vt

    # angulo de R (rotacion pura si det(R)=+1; si det(R)=-1 es
    # reflexion compuesta con rotacion, no hay un unico "angulo" limpio,
    # se reporta igual el angulo de la matriz como si fuera rotacion)
    rot_angle_deg = float(np.degrees(np.arctan2(R[1, 0], R[0, 0])))

    reconstructed = R @ S

    return {
        "matrix": A.tolist(),
        "determinant": det,
        "trace": trace,
        "eigenvalues": [
            {"re": float(e.real), "im": float(e.imag)} for e in eigvals
        ],
        "polar_decomposition": {
            "R_rotation_or_reflection": R.tolist(),
            "S_scale_shear": S.tolist(),
            "det_R": float(np.linalg.det(R)),
            "is_pure_rotation": bool(abs(np.linalg.det(R) - 1.0) < 1e-9),
            "rotation_angle_deg": rot_angle_deg,
            "principal_scale_factors": [float(s) for s in sigma],
        },
        "reconstruction_check": {
            "R_times_S": reconstructed.tolist(),
            "matches_original": bool(np.allclose(reconstructed, A, atol=1e-9)),
        },
    }


# ---------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------

def _validate():
    checks = []
    unit_square = [[0, 0], [1, 0], [1, 1], [0, 1]]

    # 1) escala diagonal (2,3) sobre cuadrado unitario: area 1 -> 6
    r1 = apply_to_polygon(unit_square, [[2, 0], [0, 3]])
    checks.append({
        "name": "escala diag(2,3) sobre cuadrado unitario: area 1->6, det=6",
        "passed": bool(abs(r1["signed_area_after"] - 6.0) < 1e-9 and abs(r1["determinant"] - 6.0) < 1e-9
                        and r1["area_ratio_matches_abs_det"]),
        "got": r1,
    })

    # 2) rotacion pura (30 grados) sobre un triangulo: area preservada,
    #    distancias de cada vertice al origen preservadas
    theta = np.radians(30)
    Rm = [[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]]
    triangle = [[1, 0], [0, 2], [-1, -1]]
    r2 = apply_to_polygon(triangle, Rm)
    dists_before = [float(np.hypot(*p)) for p in triangle]
    dists_after = [float(np.hypot(*p)) for p in r2["vertices_after"]]
    dist_preserved = all(abs(a - b) < 1e-9 for a, b in zip(dists_before, dists_after))
    checks.append({
        "name": "rotacion 30 grados: area preservada (det=1) y distancias al origen preservadas",
        "passed": bool(abs(abs(r2["determinant"]) - 1.0) < 1e-9
                        and abs(abs(r2["area_ratio_after_over_before"]) - 1.0) < 1e-9
                        and dist_preserved),
        "got": {"determinant": r2["determinant"], "dists_before": dists_before, "dists_after": dists_after},
    })

    # 3) cizallamiento [[1,1],[0,1]] (det=1): area preservada, forma cambia
    #    (el vertice (0,1) se mueve a (1,1), el area total sigue siendo 1)
    r3 = apply_to_polygon(unit_square, [[1, 1], [0, 1]])
    shape_changed = not np.allclose(r3["vertices_after"], unit_square)
    checks.append({
        "name": "cizallamiento det=1 sobre cuadrado unitario: area preservada (1), forma cambia",
        "passed": bool(abs(r3["determinant"] - 1.0) < 1e-9
                        and abs(r3["signed_area_after"] - 1.0) < 1e-9
                        and shape_changed),
        "got": r3,
    })

    # 4) reflexion [[1,0],[0,-1]] (det=-1): magnitud de area preservada,
    #    orientacion invertida
    r4 = apply_to_polygon(unit_square, [[1, 0], [0, -1]])
    checks.append({
        "name": "reflexion det=-1 sobre cuadrado unitario: |area| preservada, orientacion invertida",
        "passed": bool(abs(r4["determinant"] + 1.0) < 1e-9
                        and abs(abs(r4["signed_area_after"]) - 1.0) < 1e-9
                        and r4["orientation_reversed"]
                        and r4["orientation_reversed_matches_negative_det"]),
        "got": r4,
    })

    # 5) poligono arbitrario con matriz generica: razon de areas = |det(A)|
    pentagon = [[0, 0], [2, 0], [3, 1.5], [1, 3], [-1, 1]]
    A_generic = [[1.3, -0.7], [0.4, 2.1]]
    r5 = apply_to_polygon(pentagon, A_generic)
    checks.append({
        "name": "pentagono con matriz generica: razon de areas == |det(A)|",
        "passed": r5["area_ratio_matches_abs_det"],
        "got": r5,
    })

    # 6) descomposicion polar reconstruye A=R*S exactamente, para una
    #    matriz con rotacion+escala+cizallamiento mezclados
    A_mixed = [[2.0, 1.0], [0.5, 1.5]]
    d6 = decompose(A_mixed)
    checks.append({
        "name": "descomposicion polar A=R*S reconstruye la matriz original",
        "passed": d6["reconstruction_check"]["matches_original"],
        "got": d6,
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "all_passed": all_passed, "total": len(checks),
            "validation_passed": all_passed}


# ---------------------------------------------------------------------
# schema + dispatcher
# ---------------------------------------------------------------------

TOOL_SCHEMA = {
    "name": "linear_transform_figure",
    "description": (
        "Transformaciones lineales aplicadas a una figura geometrica "
        "concreta (distinto de linear_algebra_tool, que analiza la matriz "
        "en abstracto sin la parte de figura/area). mode='apply_to_polygon': "
        "dado 'vertices' (lista de [x,y], >=3 puntos) y 'matrix' (2x2), "
        "aplica la transformacion a cada vertice y calcula area con signo "
        "antes/despues (Shoelace), comparando la razon contra |det(A)| "
        "(teorema fundamental del cambio de area lineal) y si se invirtio "
        "la orientacion (coincide con det(A)<0). mode='decompose': dado "
        "'matrix' (2x2), devuelve determinante, traza, autovalores, y la "
        "descomposicion polar A=R*S via SVD (R=rotacion/reflexion pura, "
        "S=escala+cizallamiento puro simetrico), con el angulo de R en "
        "grados y los factores de escala principales. mode='validate': 6 "
        "auto-chequeos (escala diagonal, rotacion preserva area y "
        "distancias, cizallamiento con det=1 preserva area pero cambia "
        "forma, reflexion con det=-1 invierte orientacion, poligono "
        "arbitrario confirma |det(A)|, reconstruccion A=R*S de la "
        "descomposicion polar)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["apply_to_polygon", "decompose", "validate"],
                "default": "validate",
            },
            "vertices": {"type": "array", "items": {"type": "array", "items": {"type": "number"}},
                         "description": "apply_to_polygon: lista de [x,y], >=3 puntos."},
            "matrix": {"type": "array", "items": {"type": "array", "items": {"type": "number"}},
                       "description": "Matriz 2x2 como [[a,b],[c,d]]."},
        },
    },
}


def run(mode="validate", **params):
    try:
        if mode == "apply_to_polygon":
            return {"result": apply_to_polygon(params["vertices"], params["matrix"])}
        elif mode == "decompose":
            return {"result": decompose(params["matrix"])}
        elif mode == "validate":
            return _validate()
        else:
            raise ValueError(f"mode desconocido: {mode}")
    except Exception as e:
        return {"error": str(e)}


def linear_transform_figure(mode="validate", **params):
    return run(mode=mode, **params)


def _handler(args):
    return run(**(args or {}))


try:
    import tool_registry
    tool_registry.register_tool(TOOL_SCHEMA["name"], TOOL_SCHEMA, _handler)
except ImportError:
    pass


if __name__ == "__main__":
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "validate"
    if mode_arg == "validate":
        print(json.dumps(_validate(), indent=2))
    else:
        params_arg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        print(json.dumps(run(mode=mode_arg, **params_arg), indent=2))
