"""
Round-trip test REAL para fault_dislocation_tool._coupling_inversion.

A diferencia del check interno ("coupling_inversion_roundtrip" en _validate()),
que arma su propio mini-inversor de juguete con un kernel 1/r^2, este script:

  1. Define una falla y un patron de slip CONOCIDO por parche.
  2. Genera desplazamientos sinteticos en estaciones GPS usando el MISMO
     motor Okada (_single_point_deformation) que usa _build_green_matrix.
  3. Alimenta esas observaciones sinteticas a _solve_slip_distribution
     (la funcion real que se llama en produccion via _coupling_inversion).
  4. Compara el slip recuperado contra el slip conocido.

Correr en la maquina donde vive fault_dislocation_tool.py:
    cd ~/octave-mcp
    python3 test_roundtrip_real.py
"""
import math
import numpy as np

from fault_dislocation_tool import (
    _build_fault_patches,
    _build_laplacian_matrix,
    _single_point_deformation,
    _lonlat_to_local_km,
    _solve_slip_distribution,
)

# ---------------------------------------------------------------------------
# 1. Geometria de falla (similar a la que ya usaste para San Andres sur)
# ---------------------------------------------------------------------------
fault_geom = {
    "lon": -120.5, "lat": 35.0,
    "depth_m": 3000.0,
    "length_m": 60000.0, "width_m": 15000.0,
    "strike_angle": 320.0, "dip_angle": 80.0, "rake_angle": 180.0,
}
N_ALONG, N_DIP = 4, 2

patches = _build_fault_patches(fault_geom, N_ALONG, N_DIP)
n_patches = len(patches)

# ---------------------------------------------------------------------------
# 2. Slip conocido por parche (patron no uniforme para que sea un test real)
# ---------------------------------------------------------------------------
rng = np.random.default_rng(42)
slip_true = rng.uniform(0.3, 2.0, size=n_patches)  # metros

# ---------------------------------------------------------------------------
# 3. Estaciones GPS sinteticas (grilla alrededor de la falla)
# ---------------------------------------------------------------------------
station_lonlat = []
for dx_km in np.linspace(-40, 40, 6):
    for dy_km in (-15.0, 15.0):
        lat_per_km = 1.0 / 111.32
        lon_per_km = lat_per_km / math.cos(math.radians(fault_geom["lat"]))
        lon = fault_geom["lon"] + dx_km * lon_per_km
        lat = fault_geom["lat"] + dy_km * lat_per_km
        station_lonlat.append((lon, lat))

ref_lon, ref_lat = fault_geom["lon"], fault_geom["lat"]


def patch_unit_response(ox_km, oy_km, patch):
    """Misma formula que _patch_response dentro de _build_green_matrix,
    pero exponiendola aca para poder escalar por slip_true y sumar."""
    px_km, py_km = _lonlat_to_local_km(patch["center_lon"], patch["center_lat"], ref_lon, ref_lat)
    patch_wid_km = patch["width_m"] / 1000.0
    patch_len_km = patch["length_m"] / 1000.0
    dip_rad = math.radians(patch["dip"])
    top_depth_km = (patch["center_depth_m"] - (patch["width_m"] / 2.0) * math.sin(dip_rad)) / 1000.0
    return _single_point_deformation(
        x_east=ox_km, y_north=oy_km, z_up=0.0,
        strike_deg=patch["strike"], dip_deg=patch["dip"],
        top_depth_km=top_depth_km,
        length_km=patch_len_km, width_km=patch_wid_km,
        slip_m=1.0, rake_deg=patch["rake"], opening_m=0.0,
        ref_x=px_km, ref_y=py_km, nu=0.25,
    )


gps_observations = []
for lon, lat in station_lonlat:
    ox_km, oy_km = _lonlat_to_local_km(lon, lat, ref_lon, ref_lat)
    ue = un = uv = 0.0
    for p_idx, patch in enumerate(patches):
        resp = patch_unit_response(ox_km, oy_km, patch)
        ue += resp["u_east_m"] * slip_true[p_idx]
        un += resp["u_north_m"] * slip_true[p_idx]
        uv += resp["u_up_m"] * slip_true[p_idx]
    gps_observations.append({
        "lon": lon, "lat": lat,
        "disp_east_m": ue, "disp_north_m": un, "disp_vertical_m": uv,
        "sigma_east_m": 0.001, "sigma_north_m": 0.001, "sigma_vertical_m": 0.002,
    })

# ---------------------------------------------------------------------------
# 4. Invertir con la funcion REAL de produccion y comparar
# ---------------------------------------------------------------------------
slip_est, slip_grid, meta = _solve_slip_distribution(
    gps_observations, [], fault_geom, N_ALONG, N_DIP,
    lambda_tikhonov=None, lambda_laplacian=None,  # auto-tune via GCV, como en produccion
)

rel_error_per_patch = np.abs(slip_est - slip_true) / slip_true
overall_rel_error = np.linalg.norm(slip_est - slip_true) / np.linalg.norm(slip_true)
correlation = float(np.corrcoef(slip_est, slip_true)[0, 1])

print("=" * 70)
print("ROUND-TRIP REAL: _solve_slip_distribution (produccion, GPS sintetico)")
print("=" * 70)
print(f"n_patches: {n_patches}  (n_along={N_ALONG}, n_dip={N_DIP})")
print(f"n_estaciones GPS sinteticas: {len(gps_observations)}")
print(f"lambda_tikhonov auto: {meta['lambda_tikhonov']:.3e}")
print(f"lambda_laplacian auto: {meta['lambda_laplacian']:.3e}")
print(f"residual_rms: {meta['residual_rms']:.6e}")
print()
print(f"{'patch':>5} {'slip_true':>10} {'slip_est':>10} {'err_rel':>9}")
for i in range(n_patches):
    print(f"{i:>5} {slip_true[i]:>10.4f} {slip_est[i]:>10.4f} {rel_error_per_patch[i]:>8.1%}")
print()
print(f"Error relativo global (norma L2): {overall_rel_error:.1%}")
print(f"Correlacion slip_true vs slip_est: {correlation:.4f}")
print()
if overall_rel_error < 0.15 and correlation > 0.9:
    print("RESULTADO: recuperacion BUENA (error <15%, correlacion >0.9)")
elif overall_rel_error < 0.40:
    print("RESULTADO: recuperacion ACEPTABLE pero con sesgo/suavizado notable")
else:
    print("RESULTADO: recuperacion POBRE -- revisar signos, unidades o Green's functions antes de usar datos reales")
