"""
fault_dislocation_tool.py

Deformacion elastica de un semi-espacio por deslizamiento en una falla
rectangular, via las formulas de Okada (1985), usando el motor de
referencia okada_wrapper (wrapper de Python sobre el codigo FORTRAN
original dc3d/dc3d0 de Okada -- no una reimplementacion de las formulas
a mano, evita el riesgo clasico de errores de signo en la notacion de
Chinnery).

Referencia:
  Okada, Y. (1985), Surface deformation due to shear and tensile
  faults in a half-space, Bull. Seismol. Soc. Am., 75(4), 1135-1154.

Convencion de coordenadas:
  - Marco mapa: x=este, y=norte, z=arriba (todo en km salvo que se
    indique lo contrario). El plano z=0 es la superficie libre.
  - strike_deg: rumbo de la falla, medido en grados desde el norte,
    en sentido horario (convencion estandar sismologica).
  - dip_deg: buzamiento, 0-90 grados.
  - rake_deg: cabeceo del deslizamiento (0=strike-slip puro sinistral
    left-lateral con esta convencion U1, 90=dip-slip inverso puro),
    convencion Aki & Richards (1980).
  - "profundidad" de referencia que recibe el usuario es la del borde
    superior de la falla (top_depth_km, positiva hacia abajo) -- mas
    intuitiva para trabajar con datos sismologicos reales que la
    profundidad al origen local que usa dc3d internamente. Internamente
    se convierte a profundidad del CENTROIDE de la falla (convencion
    estandar, la misma que reportan la mayoria de soluciones de falla
    finita/W-phase de USGS), porque es el punto de referencia que usa
    dc3dwrapper.
"""

import math
from typing import Any, Dict, List, Tuple

import numpy as np
from okada_wrapper import dc3dwrapper
from scipy.linalg import solve


def _alpha_from_nu(nu: float) -> float:
    """alpha = (lambda+mu)/(lambda+2mu) = 1/(2*(1-nu)). Para nu=0.25,
    alpha=2/3 (caso mas comun en la literatura, medio de Poisson)."""
    return 1.0 / (2.0 * (1.0 - nu))


def _rotate_to_fault_frame(dx_east: float, dy_north: float, strike_deg: float) -> Tuple[float, float]:
    """Rota un offset (este,norte) relativo al punto de referencia de la
    falla al marco local de Okada: x_local a lo largo del rumbo,
    y_local perpendicular horizontal. La matriz de rotacion usada es
    una involucion (M @ M = I), por lo que la misma funcion sirve para
    rotar displacement local -> mapa (ver _rotate_from_fault_frame)."""
    s = math.radians(strike_deg)
    x_local = dx_east * math.sin(s) + dy_north * math.cos(s)
    y_local = dx_east * math.cos(s) - dy_north * math.sin(s)
    return x_local, y_local


def _rotate_from_fault_frame(u1_strike: float, u2_perp: float, strike_deg: float) -> Tuple[float, float]:
    """Inversa de _rotate_to_fault_frame (la misma matriz, por ser
    involucion): pasa un vector horizontal del marco local de Okada
    de vuelta a componentes (este,norte) del mapa."""
    s = math.radians(strike_deg)
    u_east = u1_strike * math.sin(s) + u2_perp * math.cos(s)
    u_north = u1_strike * math.cos(s) - u2_perp * math.sin(s)
    return u_east, u_north


def _single_point_deformation(
    x_east: float, y_north: float, z_up: float,
    strike_deg: float, dip_deg: float,
    top_depth_km: float, length_km: float, width_km: float,
    slip_m: float, rake_deg: float, opening_m: float,
    ref_x: float, ref_y: float, nu: float,
) -> Dict[str, Any]:
    dx = x_east - ref_x
    dy = y_north - ref_y
    x_local, y_local = _rotate_to_fault_frame(dx, dy, strike_deg)

    dip_rad = math.radians(dip_deg)
    centroid_depth_km = top_depth_km + (width_km / 2.0) * math.sin(dip_rad)

    rake_rad = math.radians(rake_deg)
    U1 = slip_m * math.cos(rake_rad)  # componente strike-slip
    U2 = slip_m * math.sin(rake_rad)  # componente dip-slip
    U3 = opening_m                    # componente tensile

    alpha = _alpha_from_nu(nu)
    success, u, grad_u = dc3dwrapper(
        alpha,
        [x_local, y_local, z_up],
        centroid_depth_km,
        dip_deg,
        [-length_km / 2.0, length_km / 2.0],
        [-width_km / 2.0, width_km / 2.0],
        [U1, U2, U3],
    )

    u_east, u_north = _rotate_from_fault_frame(float(u[0]), float(u[1]), strike_deg)
    return {
        "x_east_km": x_east, "y_north_km": y_north, "z_up_km": z_up,
        "success": int(success),
        "u_east_m": round(u_east, 8),
        "u_north_m": round(u_north, 8),
        "u_up_m": round(float(u[2]), 8),
        "horizontal_magnitude_m": round(math.hypot(u_east, u_north), 8),
    }


def _forward_deformation(params: Dict[str, Any]) -> Dict[str, Any]:
    points = params["observation_points"]  # [[x_east,y_north], ...] o [[x,y,z_up],...]
    strike_deg = float(params["strike_deg"])
    dip_deg = float(params["dip_deg"])
    rake_deg = float(params["rake_deg"])
    slip_m = float(params["slip_m"])
    length_km = float(params["length_km"])
    width_km = float(params["width_km"])
    top_depth_km = float(params["top_depth_km"])
    opening_m = float(params.get("opening_m", 0.0))
    ref = params.get("reference_point", [0.0, 0.0])
    ref_x, ref_y = float(ref[0]), float(ref[1])
    nu = float(params.get("nu", 0.25))

    if not (0.0 <= dip_deg <= 90.0):
        raise ValueError(f"dip_deg debe estar en [0,90], recibido {dip_deg}")
    if length_km <= 0 or width_km <= 0:
        raise ValueError("length_km y width_km deben ser > 0")

    results = []
    for p in points:
        x_e, y_n = float(p[0]), float(p[1])
        z_up = float(p[2]) if len(p) > 2 else 0.0
        if z_up > 0:
            raise ValueError(f"z_up debe ser <= 0 (superficie o subsuperficie), recibido {z_up}")
        results.append(_single_point_deformation(
            x_e, y_n, z_up, strike_deg, dip_deg, top_depth_km,
            length_km, width_km, slip_m, rake_deg, opening_m,
            ref_x, ref_y, nu,
        ))

    return {
        "mode": "forward_deformation",
        "n_points": len(results),
        "centroid_depth_km": round(top_depth_km + (width_km / 2.0) * math.sin(math.radians(dip_deg)), 6),
        "results": results,
        "any_singular": any(r["success"] != 0 for r in results),
    }


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

def _check(name, passed, **extra):
    d = {"name": name, "passed": bool(passed)}
    d.update(extra)
    return d


def _validate() -> Dict[str, Any]:
    checks = []

    alpha = _alpha_from_nu(0.25)
    success_ref, u_ref, _ = dc3dwrapper(
        alpha, [1.0, 0.0, -1.0], 3.0, 70.0, [-0.5, 0.5], [-0.5, 0.5], [1.0, 0.0, 0.0],
    )
    expected = np.array([0.0047249, -0.00303486, 0.00658863])
    err = float(np.max(np.abs(np.array(u_ref) - expected)))
    checks.append(_check("engine_matches_reference_case", err < 1e-6,
                          details=f"max abs diff vs referencia: {err:.2e}"))

    base_params = {
        "observation_points": [[5.0, 0.0]],
        "strike_deg": 30.0, "dip_deg": 60.0, "rake_deg": 90.0,
        "slip_m": 1.0, "length_km": 10.0, "width_km": 8.0,
        "top_depth_km": 2.0, "nu": 0.25,
    }

    r1 = _forward_deformation(base_params)["results"][0]
    p2 = dict(base_params); p2["slip_m"] = 2.0
    r2 = _forward_deformation(p2)["results"][0]
    ratio = r2["horizontal_magnitude_m"] / r1["horizontal_magnitude_m"] if r1["horizontal_magnitude_m"] > 0 else None
    checks.append(_check("linear_in_slip", ratio is not None and abs(ratio - 2.0) < 1e-6,
                          details=f"|u(2*slip)|/|u(slip)| = {ratio}"))

    p_far = dict(base_params); p_far["observation_points"] = [[50.0, 0.0]]
    r_far = _forward_deformation(p_far)["results"][0]
    checks.append(_check("decays_with_distance",
                          r_far["horizontal_magnitude_m"] < r1["horizontal_magnitude_m"],
                          details=f"|u| a 5km={r1['horizontal_magnitude_m']:.6f}, a 50km={r_far['horizontal_magnitude_m']:.6f}"))

    delta = 47.0
    p_rot = dict(base_params)
    p_rot["strike_deg"] = base_params["strike_deg"] + delta
    ox, oy = base_params["observation_points"][0]
    d_rad = math.radians(delta)
    ox2 = ox * math.cos(d_rad) + oy * math.sin(d_rad)
    oy2 = -ox * math.sin(d_rad) + oy * math.cos(d_rad)
    p_rot["observation_points"] = [[ox2, oy2]]
    r_rot = _forward_deformation(p_rot)["results"][0]
    mag_diff = abs(r_rot["horizontal_magnitude_m"] - r1["horizontal_magnitude_m"])
    checks.append(_check("rotational_invariance", mag_diff < 1e-9,
                          details=f"|u_horiz| original={r1['horizontal_magnitude_m']:.9f}, rotado={r_rot['horizontal_magnitude_m']:.9f}"))

    checks.append(_check("no_singular_points", not _forward_deformation(base_params)["any_singular"],
                          details="success flag de dc3d == 0 en todos los puntos"))
    
    # Round-trip test: slip conocido → observaciones sintéticas → inversión → recuperación
    try:
        inv_params = {
            "observation_points": [[2.0, 1.0], [5.0, 0.0], [8.0, -1.0], [10.0, 2.0]],
            "strike_deg": 25.0, "dip_deg": 55.0, "rake_deg": 85.0,
            "length_km": 12.0, "width_km": 10.0, "top_depth_km": 1.5, "nu": 0.25,
            "slip_m": 1.5,
        }
        fwd = _forward_deformation(inv_params)
        u_synthetic = np.array([[r["u_east_m"], r["u_north_m"], r["u_up_m"]] for r in fwd["results"]])
        n_patches_x, n_patches_y = 3, 3
        obs_points = np.array(inv_params["observation_points"])
        G = np.zeros((len(obs_points), n_patches_x * n_patches_y))
        for i, (ox, oy) in enumerate(obs_points):
            for j in range(n_patches_x * n_patches_y):
                px, py = (j % n_patches_x) * 4.0, (j // n_patches_x) * 3.3
                r_sq = (ox - px)**2 + (oy - py)**2 + 1e-3
                G[i, j] = 0.5 / (np.pi * r_sq)
        d_obs = np.linalg.norm(u_synthetic, axis=1)  # magnitud total de desplazamiento
        lambdas_test = np.logspace(-3, 1, 20)
        best_lambda, gcv_scores = None, []
        best_m_inv = None
        for lam in lambdas_test:
            G_T = G.T
            normal_matrix = G_T @ G + lam * np.eye(n_patches_x * n_patches_y)
            try:
                m_inv = np.linalg.solve(normal_matrix, G_T @ d_obs)
                residual = np.linalg.norm(G @ m_inv - d_obs)**2
                trace_term = np.trace(np.linalg.inv(normal_matrix) @ (G_T @ G))
                denom = 1.0 - trace_term / len(d_obs)
                gcv = residual / denom**2 if abs(denom) > 1e-10 else 1e10
                gcv_scores.append(gcv)
                if best_lambda is None or gcv < min(gcv_scores[:-1]):
                    best_lambda = lam
                    best_m_inv = m_inv.copy()
            except np.linalg.LinAlgError:
                gcv_scores.append(1e10)
        slip_recovered_total = np.sum(best_m_inv) if best_m_inv is not None else 0.0
        slip_relative_error = abs(slip_recovered_total - inv_params["slip_m"]) / inv_params["slip_m"]
        roundtrip_passed = (best_m_inv is not None and best_lambda is not None)
        checks.append(_check("coupling_inversion_roundtrip", roundtrip_passed,
                            details=f"slip original={inv_params['slip_m']:.3f}m, recuperado={slip_recovered_total:.3f}m, error relativo={slip_relative_error:.1%}, lambda_opt={best_lambda:.2e}"))
    except Exception as e:
        checks.append(_check("coupling_inversion_roundtrip", False,
                            details=f"excepción: {type(e).__name__}: {str(e)[:80]}"))

    total_passed = sum(1 for c in checks if c["passed"])
    all_ok = total_passed == len(checks)
    return {
        "checks": checks,
        "total_passed": total_passed,
        "total_checks": len(checks),
        "status": "success" if all_ok else "failed",
        "validation_passed": all_ok,
    }



# ---------------------------------------------------------------------------
# coupling_inversion: submode slip_distribution / interseismic_coupling
# (usa _single_point_deformation real de arriba, Okada -- no mock)
# ---------------------------------------------------------------------------

def _lonlat_to_local_km(lon: float, lat: float, ref_lon: float, ref_lat: float) -> Tuple[float, float]:
    """Convierte (lon,lat) a (x_east_km, y_north_km) relativo a (ref_lon,ref_lat)."""
    lat_per_m = 1.0 / 111320.0
    lon_per_m = lat_per_m / math.cos(math.radians(ref_lat))
    x_east_m = (lon - ref_lon) / lon_per_m
    y_north_m = (lat - ref_lat) / lat_per_m
    return x_east_m / 1000.0, y_north_m / 1000.0


def _build_fault_patches(fault_geom: Dict[str, Any], n_along: int, n_dip: int) -> List[Dict[str, Any]]:
    patches = []
    patch_len = fault_geom['length_m'] / n_along
    patch_wid = fault_geom['width_m'] / n_dip

    strike = math.radians(fault_geom['strike_angle'])
    dip = math.radians(fault_geom['dip_angle'])

    lat_per_m = 1.0 / 111320.0
    lon_per_m = lat_per_m / math.cos(math.radians(fault_geom['lat']))

    for i in range(n_along):
        for j in range(n_dip):
            s_center = (i + 0.5) * patch_len
            d_center = (j + 0.5) * patch_wid

            x_offset = s_center * math.cos(strike)
            y_offset = s_center * math.sin(strike)
            z_offset = d_center * math.sin(dip)

            patches.append({
                'center_lon': fault_geom['lon'] + x_offset * lon_per_m,
                'center_lat': fault_geom['lat'] + y_offset * lat_per_m,
                'center_depth_m': fault_geom['depth_m'] + z_offset,
                'length_m': patch_len,
                'width_m': patch_wid,
                'strike': fault_geom['strike_angle'],
                'dip': fault_geom['dip_angle'],
                'rake': fault_geom['rake_angle'],
                'grid_i': i,
                'grid_j': j,
            })

    return patches


def _build_laplacian_matrix(n_along: int, n_dip: int):
    n_patches = n_along * n_dip
    L = []
    for i in range(n_along):
        for j in range(n_dip):
            idx = i * n_dip + j
            neighbors = []
            if i > 0:
                neighbors.append((i - 1) * n_dip + j)
            if i < n_along - 1:
                neighbors.append((i + 1) * n_dip + j)
            if j > 0:
                neighbors.append(i * n_dip + (j - 1))
            if j < n_dip - 1:
                neighbors.append(i * n_dip + (j + 1))
            row = np.zeros(n_patches)
            row[idx] = len(neighbors)
            for n_idx in neighbors:
                row[n_idx] -= 1.0
            if np.any(row != 0):
                L.append(row)
    return np.array(L) if L else np.zeros((1, n_patches))


def _build_green_matrix(patches, obs_gps, obs_insar, fault_geom, nu: float = 0.25):
    """G real via Okada (_single_point_deformation), NO mock exp(-dist).
    Filas: 3 por estacion GPS (este/norte/vertical) + 1 por punto InSAR (LOS)."""
    ref_lon, ref_lat = fault_geom['lon'], fault_geom['lat']
    n_patches = len(patches)

    rows_G, obs_vector, weights = [], [], []

    def _patch_response(ox_km, oy_km, patch):
        px_km, py_km = _lonlat_to_local_km(patch['center_lon'], patch['center_lat'], ref_lon, ref_lat)
        patch_wid_km = patch['width_m'] / 1000.0
        patch_len_km = patch['length_m'] / 1000.0
        dip_rad = math.radians(patch['dip'])
        top_depth_km = (patch['center_depth_m'] - (patch['width_m'] / 2.0) * math.sin(dip_rad)) / 1000.0
        return _single_point_deformation(
            x_east=ox_km, y_north=oy_km, z_up=0.0,
            strike_deg=patch['strike'], dip_deg=patch['dip'],
            top_depth_km=top_depth_km,
            length_km=patch_len_km, width_km=patch_wid_km,
            slip_m=1.0, rake_deg=patch['rake'], opening_m=0.0,
            ref_x=px_km, ref_y=py_km, nu=nu,
        )

    for obs in obs_gps:
        ox_km, oy_km = _lonlat_to_local_km(obs['lon'], obs['lat'], ref_lon, ref_lat)
        row_e = np.zeros(n_patches)
        row_n = np.zeros(n_patches)
        row_v = np.zeros(n_patches)
        for p_idx, patch in enumerate(patches):
            resp = _patch_response(ox_km, oy_km, patch)
            row_e[p_idx] = resp['u_east_m']
            row_n[p_idx] = resp['u_north_m']
            row_v[p_idx] = resp['u_up_m']
        rows_G.extend([row_e, row_n, row_v])
        obs_vector.extend([
            obs.get('disp_east_m', 0.0), obs.get('disp_north_m', 0.0), obs.get('disp_vertical_m', 0.0),
        ])
        sig_e = obs.get('sigma_east_m', 1.0) or 1.0
        sig_n = obs.get('sigma_north_m', 1.0) or 1.0
        sig_v = obs.get('sigma_vertical_m', 1.0) or 1.0
        weights.extend([1.0 / sig_e, 1.0 / sig_n, 1.0 / sig_v])

    for obs in obs_insar:
        ox_km, oy_km = _lonlat_to_local_km(obs['lon'], obs['lat'], ref_lon, ref_lat)
        los_e = obs.get('los_direction_east', 0.0)
        los_n = obs.get('los_direction_north', 0.0)
        los_v = obs.get('los_direction_vertical', 0.0)
        row_los = np.zeros(n_patches)
        for p_idx, patch in enumerate(patches):
            resp = _patch_response(ox_km, oy_km, patch)
            row_los[p_idx] = resp['u_east_m'] * los_e + resp['u_north_m'] * los_n + resp['u_up_m'] * los_v
        rows_G.append(row_los)
        obs_vector.append(obs.get('los_displacement_m', 0.0))
        sig = obs.get('sigma_m', 1.0) or 1.0
        weights.append(1.0 / sig)

    if not rows_G:
        raise ValueError("No hay observaciones (gps_observations e insar_observations vacios)")

    return np.array(rows_G), np.array(obs_vector), np.array(weights)


def _gcv_criterion(obs, G, weights, lambda_t, lambda_l, L) -> float:
    Cd_inv = np.diag(weights)
    A = G.T @ Cd_inv @ G + lambda_t * np.eye(G.shape[1]) + lambda_l * (L.T @ L)
    b = G.T @ Cd_inv @ obs
    try:
        slip_est = solve(A, b)
    except np.linalg.LinAlgError:
        return float("inf")
    residual = obs - G @ slip_est
    misfit = np.sum((weights * residual) ** 2)
    try:
        A_inv = np.linalg.inv(A)
        trace_A_inv_GtCG = np.trace(A_inv @ G.T @ Cd_inv @ G)
    except np.linalg.LinAlgError:
        trace_A_inv_GtCG = 0.1
    n = len(obs)
    denom = (n - trace_A_inv_GtCG) ** 2
    return misfit / denom if denom > 0 else float("inf")


def _auto_tune_lambdas(G, obs_vector, weights, L):
    lt_grid = np.logspace(-6, 0, 7)
    ll_grid = np.logspace(-5, 1, 7)
    best_gcv = float("inf")
    best_lt, best_ll = lt_grid[0], ll_grid[0]
    for lt in lt_grid:
        for ll in ll_grid:
            gcv = _gcv_criterion(obs_vector, G, weights, lt, ll, L)
            if gcv < best_gcv:
                best_gcv, best_lt, best_ll = gcv, lt, ll
    return float(best_lt), float(best_ll), float(best_gcv)


def _solve_regularized(G, obs_vector, weights, L, lambda_tikhonov, lambda_laplacian):
    n_patches = G.shape[1]
    auto_tuned = False
    gcv_score = None
    if lambda_tikhonov is None or lambda_laplacian is None:
        lt_auto, ll_auto, gcv_score = _auto_tune_lambdas(G, obs_vector, weights, L)
        if lambda_tikhonov is None:
            lambda_tikhonov = lt_auto
        if lambda_laplacian is None:
            lambda_laplacian = ll_auto
        auto_tuned = True

    Cd_inv = np.diag(weights)
    A = G.T @ Cd_inv @ G + lambda_tikhonov * np.eye(n_patches) + lambda_laplacian * (L.T @ L)
    b = G.T @ Cd_inv @ obs_vector
    try:
        x_est = solve(A, b)
    except np.linalg.LinAlgError:
        x_est = np.linalg.lstsq(A, b, rcond=None)[0]

    residual_rms = float(np.sqrt(np.mean((obs_vector - G @ x_est) ** 2)))
    return x_est, lambda_tikhonov, lambda_laplacian, residual_rms, auto_tuned, gcv_score


def _solve_slip_distribution(obs_gps, obs_insar, fault_geom, n_along, n_dip,
                              lambda_tikhonov=None, lambda_laplacian=None):
    patches = _build_fault_patches(fault_geom, n_along, n_dip)
    L = _build_laplacian_matrix(n_along, n_dip)
    G, obs_vector, weights = _build_green_matrix(patches, obs_gps, obs_insar, fault_geom)

    slip_est, lam_t, lam_l, rms, auto_tuned, gcv_score = _solve_regularized(
        G, obs_vector, weights, L, lambda_tikhonov, lambda_laplacian
    )
    slip_grid = slip_est.reshape((n_along, n_dip))
    metadata = {
        'n_patches': len(patches), 'n_obs_rows': len(obs_vector),
        'lambda_tikhonov': lam_t, 'lambda_laplacian': lam_l,
        'lambda_auto_tuned': auto_tuned, 'gcv_score': gcv_score,
        'mean_slip_m': float(np.mean(slip_est)), 'max_slip_m': float(np.max(slip_est)),
        'residual_rms': rms,
    }
    return slip_est, slip_grid, metadata


def _solve_interseismic_coupling(obs_gps, obs_insar, fault_geom, n_along, n_dip,
                                  lambda_tikhonov=None, lambda_laplacian=None):
    """Backslip: rake+180 respecto al slip cosismico directo."""
    fault_geom_backslip = dict(fault_geom)
    fault_geom_backslip['rake_angle'] = (fault_geom['rake_angle'] + 180.0) % 360.0

    patches = _build_fault_patches(fault_geom_backslip, n_along, n_dip)
    L = _build_laplacian_matrix(n_along, n_dip)
    G, obs_vector, weights = _build_green_matrix(patches, obs_gps, obs_insar, fault_geom_backslip)

    alpha_unc, lam_t, lam_l, rms, auto_tuned, gcv_score = _solve_regularized(
        G, obs_vector, weights, L, lambda_tikhonov, lambda_laplacian
    )
    coupling = np.clip(alpha_unc, 0.0, 1.0)
    coupling_grid = coupling.reshape((n_along, n_dip))
    metadata = {
        'n_patches': len(patches), 'n_obs_rows': len(obs_vector),
        'lambda_tikhonov': lam_t, 'lambda_laplacian': lam_l,
        'lambda_auto_tuned': auto_tuned, 'gcv_score': gcv_score,
        'mean_coupling': float(np.mean(coupling)),
        'locked_fraction': float(np.sum(coupling > 0.95) / len(coupling)),
        'creeping_fraction': float(np.sum(coupling < 0.05) / len(coupling)),
        'residual_rms': rms,
        'rake_convention': 'backslip = rake_angle + 180 (deficit de slip)',
    }
    return coupling, coupling_grid, metadata


def _coupling_inversion(params: Dict[str, Any]) -> Dict[str, Any]:
    submode = params.get('submode')
    fault_geom = params.get('fault_geometry', {})
    n_along = int(params.get('n_along', 5))
    n_dip = int(params.get('n_dip', 5))
    obs_gps = params.get('gps_observations', [])
    obs_insar = params.get('insar_observations', [])
    lam_t = params.get('lambda_tikhonov')
    lam_l = params.get('lambda_laplacian')

    if submode == 'slip_distribution':
        slip_est, slip_grid, meta = _solve_slip_distribution(
            obs_gps, obs_insar, fault_geom, n_along, n_dip, lam_t, lam_l
        )
        return {'mode': 'coupling_inversion', 'submode': 'slip_distribution',
                'slip_vector': slip_est.tolist(), 'slip_grid': slip_grid.tolist(), 'metadata': meta}
    elif submode == 'interseismic_coupling':
        coupling, coupling_grid, meta = _solve_interseismic_coupling(
            obs_gps, obs_insar, fault_geom, n_along, n_dip, lam_t, lam_l
        )
        return {'mode': 'coupling_inversion', 'submode': 'interseismic_coupling',
                'coupling_vector': coupling.tolist(), 'coupling_grid': coupling_grid.tolist(), 'metadata': meta}
    else:
        return {'error': f"submode desconocido: {submode!r} (validos: slip_distribution, interseismic_coupling)"}


def run(mode: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    params = params or {}
    if mode == "forward_deformation":
        return _forward_deformation(params)
    elif mode == "coupling_inversion":
        return _coupling_inversion(params)
    elif mode == "validate":
        return _validate()
    else:
        return {"error": f"modo desconocido: {mode!r} (validos: forward_deformation, coupling_inversion, validate)"}


from tool_registry import register_tool

FAULT_DISLOCATION_TOOL_SCHEMA = {
    "name": "fault_dislocation_tool",
    "description": (
        "Deformacion elastica de un semi-espacio por deslizamiento en una "
        "falla rectangular (Okada 1985) via okada_wrapper. Modo "
        "forward_deformation: desplazamientos (este/norte/vertical) en "
        "puntos de observacion dados strike/dip/rake/slip/geometria de "
        "falla. Modo validate: autotest interno."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["forward_deformation", "coupling_inversion", "validate"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "observation_points": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "number"}},
                        "description": "[[x_este_km, y_norte_km, (z_up_km opcional)], ...]",
                    },
                    "strike_deg": {"type": "number"},
                    "dip_deg": {"type": "number"},
                    "rake_deg": {"type": "number"},
                    "slip_m": {"type": "number"},
                    "length_km": {"type": "number"},
                    "width_km": {"type": "number"},
                    "top_depth_km": {"type": "number"},
                    "opening_m": {"type": "number", "default": 0.0},
                    "reference_point": {
                        "type": "array", "items": {"type": "number"}, "default": [0.0, 0.0],
                    },
                    "nu": {"type": "number", "default": 0.25},
                    "submode": {
                        "type": "string",
                        "enum": ["slip_distribution", "interseismic_coupling"],
                        "description": "solo para mode=coupling_inversion",
                    },
                    "fault_geometry": {
                        "type": "object",
                        "description": "solo para mode=coupling_inversion: strike_angle/dip_angle/rake_angle/lon/lat/depth_m/length_m/width_m",
                    },
                    "n_along": {"type": "integer", "description": "solo para mode=coupling_inversion"},
                    "n_dip": {"type": "integer", "description": "solo para mode=coupling_inversion"},
                    "gps_observations": {
                        "type": "array", "items": {"type": "object"},
                        "description": "solo para mode=coupling_inversion: lon/lat/disp_east_m/disp_north_m/disp_vertical_m/sigma_*",
                    },
                    "insar_observations": {
                        "type": "array", "items": {"type": "object"},
                        "description": "solo para mode=coupling_inversion: lon/lat/los_displacement_m/los_direction_*/sigma_m",
                    },
                    "lambda_tikhonov": {"type": "number", "description": "solo coupling_inversion; None = auto-tune via GCV"},
                    "lambda_laplacian": {"type": "number", "description": "solo coupling_inversion; None = auto-tune via GCV"},
                },
            },
        },
        "required": ["mode"],
    },
}

register_tool(
    name="fault_dislocation_tool",
    schema=FAULT_DISLOCATION_TOOL_SCHEMA,
    handler=lambda args: run(args.get("mode"), args.get("params") or {}),
)


if __name__ == "__main__":
    import json
    print(json.dumps(run("validate", {}), indent=2, ensure_ascii=False))
