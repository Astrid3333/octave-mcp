"""
Version 2 -- SOLO segmento Carrizo, con:
  1. Chequeo de rake corregido (el error de v1: el punto de prueba estaba del
     lado Norteamerica, no del lado Pacifico -- aca se recalculan ambos lados
     explicitamente y se etiquetan correctamente).
  2. Ventana perpendicular mas angosta (20 km en vez de 40) para reducir la
     contaminacion de senal de fallas vecinas (San Jacinto, etc. -- aunque
     Carrizo es el segmento mas aislado de las 4, igual conviene ser conservador).

Requiere: fault_dislocation_tool.py y gps_observations_raw.json en el mismo dir.
"""
import json
import math
import numpy as np

from fault_dislocation_tool import (
    _lonlat_to_local_km,
    _single_point_deformation,
    _solve_interseismic_coupling,
)

SEG = {
    "name": "Carrizo",
    "lon1": -119.87, "lat1": 35.31,
    "lon2": -118.51, "lat2": 34.70,
    "slip_rate_mm_yr": 26.5,
}

DEPTH_TOP_M = 0.0
LOCKING_DEPTH_M = 15000.0
N_ALONG = 6
N_DIP = 2

PERP_DIST_MAX_KM = 20.0
ALONG_STRIKE_MARGIN_KM = 10.0

MM_TO_M = 1.0 / 1000.0


def bearing_deg(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def build_fault_geometry(seg, rake_angle):
    strike = bearing_deg(seg["lat1"], seg["lon1"], seg["lat2"], seg["lon2"])
    length_m = haversine_m(seg["lat1"], seg["lon1"], seg["lat2"], seg["lon2"])
    return {
        "lon": seg["lon1"], "lat": seg["lat1"],
        "depth_m": DEPTH_TOP_M,
        "length_m": length_m, "width_m": LOCKING_DEPTH_M,
        "strike_angle": strike, "dip_angle": 90.0, "rake_angle": rake_angle,
    }


def station_offsets(strike_deg, ox_km, oy_km):
    strike_rad = math.radians(strike_deg)
    ux, uy = math.sin(strike_rad), math.cos(strike_rad)
    along = ox_km * ux + oy_km * uy
    perp = -ox_km * uy + oy_km * ux
    return along, perp


# ---------------------------------------------------------------------------
# 1. Chequeo de rake CORREGIDO: probamos explicitamente un punto a la
#    IZQUIERDA del rumbo (perp>0 con nuestra convencion de station_offsets)
#    y uno a la DERECHA (perp<0), y etiquetamos cada uno segun de que lado
#    geografico cae realmente (revisando el signo de su longitud relativa).
# ---------------------------------------------------------------------------
strike = bearing_deg(SEG["lat1"], SEG["lon1"], SEG["lat2"], SEG["lon2"])
print(f"Strike de Carrizo: {strike:.1f} grados (medido desde el extremo NO hacia el SE)")

test_template = dict(
    strike_deg=strike, dip_deg=90.0, top_depth_km=1.0,
    length_km=20.0, width_km=15.0, slip_m=1.0, opening_m=0.0,
    ref_x=0.0, ref_y=0.0, nu=0.25,
)

strike_rad = math.radians(strike)
# vector perpendicular al strike, dos sentidos posibles
perp_unit_a = (-math.cos(strike_rad), math.sin(strike_rad))   # "izquierda" (perp>0 en station_offsets)
perp_unit_b = (math.cos(strike_rad), -math.sin(strike_rad))   # "derecha"   (perp<0 en station_offsets)

DIST_KM = 10.0
point_a = (perp_unit_a[0] * DIST_KM, perp_unit_a[1] * DIST_KM)  # (x_este_km, y_norte_km)
point_b = (perp_unit_b[0] * DIST_KM, perp_unit_b[1] * DIST_KM)

# Convertir esos offsets locales (respecto al extremo NO del segmento) a lon/lat
# reales para saber si point_a cae al oeste (lado Pacifico) o al este (lado NA)
# del segmento -- usamos la longitud absoluta resultante como criterio simple.
lat_per_km = 1.0 / 111.32
lon_per_km = lat_per_km / math.cos(math.radians(SEG["lat1"]))
lon_a = SEG["lon1"] + point_a[0] * lon_per_km
lon_b = SEG["lon1"] + point_b[0] * lon_per_km

label_a = "OESTE (lado Pacifico)" if lon_a < SEG["lon1"] else "ESTE (lado Norteamerica)"
label_b = "OESTE (lado Pacifico)" if lon_b < SEG["lon1"] else "ESTE (lado Norteamerica)"

print(f"\nPunto A: offset_este_km={point_a[0]:+.2f} -> lon={lon_a:.4f} -> {label_a}")
print(f"Punto B: offset_este_km={point_b[0]:+.2f} -> lon={lon_b:.4f} -> {label_b}")

print(f"\n{'rake':>6} {'punto':>8} {'lado':>25} {'u_east_m':>12} {'u_north_m':>12}")
best_rake_for_pacific_NO = None
for rake_try in (0.0, 180.0):
    for label_point, (px, py), side in (("A", point_a, label_a), ("B", point_b, label_b)):
        r = _single_point_deformation(x_east=px, y_north=py, z_up=0.0, rake_deg=rake_try, **test_template)
        print(f"{rake_try:>6.0f} {label_point:>8} {side:>25} {r['u_east_m']:>+12.6f} {r['u_north_m']:>+12.6f}")
        # Movimiento lateral-derecho esperado: el lado Pacifico (oeste) se mueve
        # hacia el NO respecto al lado Norteamerica -> componente u_north debe
        # ser POSITIVA en el lado Pacifico bajo el rake correcto (aproximacion,
        # ya que "hacia el NO" en este tramo con strike~118 grados tiene fuerte
        # componente norte).
        if "Pacifico" in side and r["u_north_m"] > 0:
            best_rake_for_pacific_NO = rake_try

print(f"\n>>> rake que da movimiento hacia el NO en el lado Pacifico: {best_rake_for_pacific_NO}")
if best_rake_for_pacific_NO is None:
    print(">>> Ninguno de los dos dio el signo esperado con este criterio simplificado;")
    print(">>> revisar manualmente antes de continuar.")
    RAKE_ANGLE = 180.0
    print(f">>> Usando rake={RAKE_ANGLE} por defecto -- AJUSTAR si es necesario.")
else:
    RAKE_ANGLE = best_rake_for_pacific_NO
    print(f">>> Usando rake={RAKE_ANGLE} (elegido por el chequeo de arriba)")

# ---------------------------------------------------------------------------
# 2. Cargar GPS, filtrar SOLO Carrizo con ventana angosta
# ---------------------------------------------------------------------------
with open("gps_observations_raw.json") as f:
    all_obs = json.load(f)

fault_geom = build_fault_geometry(SEG, RAKE_ANGLE)
ref_lon, ref_lat = fault_geom["lon"], fault_geom["lat"]
slip_rate_m_yr = SEG["slip_rate_mm_yr"] * MM_TO_M
length_km = fault_geom["length_m"] / 1000.0

strike_rad = math.radians(strike)

seg_obs = []
diagnostic_rows = []
for i, obs in enumerate(all_obs):
    ox_km, oy_km = _lonlat_to_local_km(obs["lon"], obs["lat"], ref_lon, ref_lat)
    along_km, perp_km = station_offsets(strike, ox_km, oy_km)
    if -ALONG_STRIKE_MARGIN_KM <= along_km <= length_km + ALONG_STRIKE_MARGIN_KM \
            and abs(perp_km) <= PERP_DIST_MAX_KM:
        seg_obs.append({
            "lon": obs["lon"], "lat": obs["lat"],
            "disp_east_m": obs["disp_east_m"] / slip_rate_m_yr,
            "disp_north_m": obs["disp_north_m"] / slip_rate_m_yr,
            "disp_vertical_m": 0.0,
            "sigma_east_m": max(obs["sigma_east_m"] / slip_rate_m_yr, 1e-6),
            "sigma_north_m": max(obs["sigma_north_m"] / slip_rate_m_yr, 1e-6),
            "sigma_vertical_m": 1.0,
        })
        v_along_m_yr, _ = station_offsets(strike, obs["disp_east_m"], obs["disp_north_m"])
        sigma_along_m_yr = math.sqrt(
            (math.sin(strike_rad) * obs["sigma_east_m"]) ** 2
            + (math.cos(strike_rad) * obs["sigma_north_m"]) ** 2
        )
        diagnostic_rows.append({
            "station": obs.get("station", obs.get("id", f"sta_{i}")),
            "dist_perp_km": perp_km,
            "v_parallel_mm_yr": v_along_m_yr * 1000.0,
            "sigma_v_mm_yr": sigma_along_m_yr * 1000.0,
        })

import csv
with open("diagnostic_Carrizo.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["station", "dist_perp_km", "v_parallel_mm_yr", "sigma_v_mm_yr"])
    w.writeheader()
    w.writerows(diagnostic_rows)
print(f"Guardado: diagnostic_Carrizo.csv ({len(diagnostic_rows)} filas)")

print(f"\n{'=' * 70}")
print(f"Carrizo: n_estaciones={len(seg_obs)} (ventana perp={PERP_DIST_MAX_KM}km), "
      f"strike={strike:.1f}, rake={RAKE_ANGLE}, slip_rate={SEG['slip_rate_mm_yr']}mm/yr")
print(f"{'=' * 70}")

if len(seg_obs) < N_ALONG * N_DIP:
    print(f"SKIP: muy pocas estaciones ({len(seg_obs)}) para {N_ALONG * N_DIP} parches.")
else:
    coupling, coupling_grid, meta = _solve_interseismic_coupling(
        seg_obs, [], fault_geom, N_ALONG, N_DIP,
        lambda_tikhonov=None, lambda_laplacian=None,
    )
    print(f"lambda_tikhonov={meta['lambda_tikhonov']:.3e}  lambda_laplacian={meta['lambda_laplacian']:.3e}")
    print(f"residual_rms={meta['residual_rms']:.4e}")
    print(f"mean_coupling={meta['mean_coupling']:.3f}  locked={meta['locked_fraction']:.1%}  "
          f"creeping={meta['creeping_fraction']:.1%}")
    print("coupling_grid (n_along x n_dip):")
    print(np.round(coupling_grid, 3))

    with open("carrizo_coupling_result.json", "w") as f:
        json.dump({
            "fault_geometry": fault_geom, "rake_used": RAKE_ANGLE,
            "n_stations": len(seg_obs),
            "coupling_grid": coupling_grid.tolist(), "metadata": meta,
        }, f, indent=2)
    print("\nGuardado: carrizo_coupling_result.json")
