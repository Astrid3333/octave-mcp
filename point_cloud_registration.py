"""
point_cloud_registration.py -- Registro rigido de nubes de puntos via ICP
(Iterative Closest Point) con estimacion de transformacion por SVD
(algoritmo de Kabsch).

Modos:
  icp       -- alinea 'source' contra 'target', devuelve R, t, nube
               registrada y error residual
  validate  -- (a) verifica _best_fit_transform en aislamiento contra una
               transformacion afin conocida con correspondencia perfecta
               (matematica pura, sin iteracion); (b) corre ICP completo
               (con busqueda de vecino mas cercano, sin correspondencia
               dada) sobre una nube con rotacion+traslacion conocidas y
               verifica que recupera esa transformacion
"""

import numpy as np
from scipy.spatial import cKDTree


# ---------------------------------------------------------------------------
# Kabsch / SVD: mejor transformacion rigida dada correspondencia 1:1
# ---------------------------------------------------------------------------

def _best_fit_transform(A, B):
    """Rotacion R (3x3) y traslacion t (3,) que minimizan
    sum ||R @ A_i + t - B_i||^2, asumiendo A[i] <-> B[i]."""
    A = np.asarray(A, dtype=float)
    B = np.asarray(B, dtype=float)
    centroid_A = A.mean(axis=0)
    centroid_B = B.mean(axis=0)
    AA = A - centroid_A
    BB = B - centroid_B
    H = AA.T @ BB
    U, _, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[-1, :] *= -1
        R = Vt.T @ U.T
    t = centroid_B - R @ centroid_A
    return R, t


# ---------------------------------------------------------------------------
# ICP
# ---------------------------------------------------------------------------

def _icp(source, target, max_iterations=50, tolerance=1e-6):
    source = np.asarray(source, dtype=float)
    target = np.asarray(target, dtype=float)
    tree = cKDTree(target)

    src = source.copy()
    R_total = np.eye(3)
    t_total = np.zeros(3)
    prev_error = None
    mean_error = None
    n_iter = 0

    for n_iter in range(1, max_iterations + 1):
        dists, indices = tree.query(src, k=1)
        matched_target = target[indices]

        R_i, t_i = _best_fit_transform(src, matched_target)
        src = (R_i @ src.T).T + t_i

        R_total = R_i @ R_total
        t_total = R_i @ t_total + t_i

        mean_error = float(dists.mean())
        if prev_error is not None and abs(prev_error - mean_error) < tolerance:
            break
        prev_error = mean_error

    return {
        "R": R_total.tolist(),
        "t": t_total.tolist(),
        "iterations": n_iter,
        "final_mean_error": mean_error,
        "registered_points": src.tolist(),
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def compute_point_cloud_registration(mode, **params):
    if mode == "validate":
        return _validate_point_cloud_registration()
    elif mode == "icp":
        source = np.array(params["source"], dtype=float)
        target = np.array(params["target"], dtype=float)
        max_iterations = params.get("max_iterations", 50)
        tolerance = params.get("tolerance", 1e-6)
        return _icp(source, target, max_iterations=max_iterations, tolerance=tolerance)
    else:
        raise ValueError(f"modo desconocido: {mode}. Use icp")


# ---------------------------------------------------------------------------
# Validacion
# ---------------------------------------------------------------------------

def _rotation_matrix_xyz(angles_deg):
    """Matriz de rotacion 3x3 compuesta Rz @ Ry @ Rx, angulos en grados."""
    ax, ay, az = np.radians(angles_deg)
    Rx = np.array([[1, 0, 0], [0, np.cos(ax), -np.sin(ax)], [0, np.sin(ax), np.cos(ax)]])
    Ry = np.array([[np.cos(ay), 0, np.sin(ay)], [0, 1, 0], [-np.sin(ay), 0, np.cos(ay)]])
    Rz = np.array([[np.cos(az), -np.sin(az), 0], [np.sin(az), np.cos(az), 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def _validate_point_cloud_registration():
    checks = []
    rng = np.random.default_rng(123)

    # --- (a) _best_fit_transform en aislamiento, correspondencia perfecta ---
    A = rng.uniform(-1, 1, size=(20, 3))
    R_true = _rotation_matrix_xyz([12.0, -7.0, 20.0])
    t_true = np.array([0.4, -0.3, 0.9])
    B = (R_true @ A.T).T + t_true

    R_est, t_est = _best_fit_transform(A, B)
    R_diff = float(np.max(np.abs(R_est - R_true)))
    t_diff = float(np.max(np.abs(t_est - t_true)))
    checks.append({
        "name": "best_fit_transform_R_exacto_correspondencia_perfecta",
        "expected": "max abs diff < 1e-9",
        "got": round(R_diff, 12),
        "passed": bool(R_diff < 1e-9),
    })
    checks.append({
        "name": "best_fit_transform_t_exacto_correspondencia_perfecta",
        "expected": "max abs diff < 1e-9",
        "got": round(t_diff, 12),
        "passed": bool(t_diff < 1e-9),
    })

    # --- (b) ICP completo, sin correspondencia dada (nearest-neighbor) ---
    # rotacion/traslacion moderadas para que el vecino mas cercano converja
    # a la correspondencia correcta (nube ya razonablemente alineada)
    source = rng.uniform(-2, 2, size=(60, 3))
    R_true2 = _rotation_matrix_xyz([5.0, 3.0, 8.0])
    t_true2 = np.array([0.15, -0.1, 0.2])
    target = (R_true2 @ source.T).T + t_true2

    icp_result = _icp(source, target, max_iterations=50, tolerance=1e-10)
    R_icp = np.array(icp_result["R"])
    t_icp = np.array(icp_result["t"])
    R_diff2 = float(np.max(np.abs(R_icp - R_true2)))
    t_diff2 = float(np.max(np.abs(t_icp - t_true2)))
    checks.append({
        "name": "icp_recupera_rotacion_conocida",
        "expected": "max abs diff < 1e-4",
        "got": round(R_diff2, 8),
        "passed": bool(R_diff2 < 1e-4),
    })
    checks.append({
        "name": "icp_recupera_traslacion_conocida",
        "expected": "max abs diff < 1e-4",
        "got": round(t_diff2, 8),
        "passed": bool(t_diff2 < 1e-4),
    })

    # chequeo independiente: residual real punto-a-punto tras registrar
    registered = np.array(icp_result["registered_points"])
    residual = float(np.max(np.linalg.norm(registered - target, axis=1)))
    checks.append({
        "name": "icp_residual_punto_a_punto",
        "expected": "max distancia registrado-vs-target < 1e-3",
        "got": round(residual, 8),
        "passed": bool(residual < 1e-3),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}


if __name__ == "__main__":
    result = _validate_point_cloud_registration()
    for c in result["checks"]:
        status = "OK" if c["passed"] else "FALLO"
        print(f"[{status}] {c['name']}: esperado={c['expected']}  obtenido={c['got']}")
    print("\nTodas las validaciones pasaron." if result["all_passed"] else "\nHAY VALIDACIONES QUE FALLARON.")


POINT_CLOUD_REGISTRATION_TOOL_SCHEMA = {
    "name": "point_cloud_registration",
    "description": (
        "Registro rigido de nubes de puntos via ICP (Iterative Closest "
        "Point), con estimacion de transformacion por SVD (Kabsch) en "
        "cada iteracion. Devuelve matriz de rotacion R, traslacion t, "
        "nube registrada y error residual medio."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["icp", "validate"]},
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
    return compute_point_cloud_registration(mode=args["mode"], **_params)


register_tool("point_cloud_registration", POINT_CLOUD_REGISTRATION_TOOL_SCHEMA, _handle)
