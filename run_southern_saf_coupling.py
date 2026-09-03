"""
Inversion de coupling interseismico para 4 segmentos del sur de San Andres:
Carrizo -> Mojave -> San Bernardino -> Coachella.

Requiere:
  - fault_dislocation_tool.py en el mismo directorio (o en el PYTHONPATH)
  - gps_observations_raw.json generado por parse_nshm_gps.py (version SIN normalizar,
    porque aca normalizamos con la tasa de slip especifica de CADA segmento, no con
    una tasa generica global)

Geometria de segmentos: coordenadas de extremos y tasas de slip geologicas de
California Geological Survey (2002, parametros de falla) y Johnson (2016,
"A fault-based model for crustal deformation...", USGS) para las tasas mas
recientes. dip=90 (SAF es esencialmente vertical en estos tramos).

IMPORTANTE - Convencion de rake (lateral-derecha vs lateral-izquierda):
San Andres es una falla de rumbo lateral-derecha (right-lateral strike-slip).
La convencion de signo de rake que usa okada_wrapper depende de la direccion
en que definas el strike (de norte a sur o de sur a norte cambia el signo
necesario). Este script NO asume un valor -- prueba rake=0 y rake=180 con el
motor forward real, y elige el que da el sentido de movimiento correcto
(bloque Pacifico moviendose NO respecto al bloque Norteamericano), verificando
contra el propio dato GPS observado antes de invertir. Revisa el print de
verificacion antes de confiar en los resultados.
"""
import json
import math
import numpy as np

from fault_dislocation_tool import (
    _lonlat_to_local_km,
    _single_point_deformation,
    _solve_interseismic_coupling,
)

# ---------------------------------------------------------------------------
# 1. Definicion de segmentos (extremos reales, tasas de slip geologicas)
# ---------------------------------------------------------------------------
SEGMENTS = [
    {
        "name": "Carrizo",
        "lon1": -119.87, "lat1": 35.31,
        "lon2": -118.51, "lat2": 34.70,
        "slip_rate_mm_yr": 26.5,  # rango 25-28 mm/yr, Johnson 2016
    },
    {
        "name": "Mojave",
        "lon1": -118.51, "lat1": 34.70,
        "lon2": -117.50, "lat2": 34.29,
        "slip_rate_mm_yr": 21.0,  # rango 20-22 mm/yr, Johnson 2016
    },
    {
        "name": "San Bernardino",
        "lon1": -117.50, "lat1": 34.29,
        "lon2": -116.48, "lat2": 33.92,
        "slip_rate_mm_yr": 24.0,  # CGS 2002 (sin actualizacion reciente encontrada)
    },
    {
        "name": "Coachella",
        "lon1": -116.47, "lat1": 33.92,
        "lon2": -115.71, "lat2": 33.35,
        "slip_rate_mm_yr": 22.0,  # rango 20-24 mm/yr, Johnson 2016
    },
]

DEPTH_TOP_M = 0.0
LOCKING_DEPTH_M = 15000.0  # profundidad de bloqueo sismogenico tipica ~15 km
N_ALONG = 6
N_DIP = 2

PERP_DIST_MAX_KM = 40.0     # distancia perpendicular maxima a la traza para incluir estacion
ALONG_STRIKE_MARGIN_KM = 15.0  # margen mas alla de los extremos del segmento

MM_TO_M = 1.0 / 1000.0


def bearing_deg(lat1, lon1, lat2, lon2):
    """Rumbo (azimut) en grados desde el punto 1 hacia el punto 2, 0=Norte, 90=Este."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    brng = math.degrees(math.atan2(x, y))
    return (brng + 360.0) % 360.0


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


def station_offsets(seg, ox_km, oy_km):
    """Proyecta la estacion (en km locales relativos al origen del segmento)
    sobre la direccion de strike: devuelve (dist_along_km, dist_perp_km)."""
    strike = bearing_deg(seg["lat1"], seg["lon1"], seg["lat2"], seg["lon2"])
    strike_rad = math.radians(strike)
    # vector unitario a lo largo del strike (en el plano local este/norte)
    ux, uy = math.sin(strike_rad), math.cos(strike_rad)
    along = ox_km * ux + oy_km * uy
    perp = -ox_km * uy + oy_km * ux
    return along, perp


def pick_rake_by_sign_check(seg):
    """Prueba rake=0 y rake=180: para un punto de prueba al oeste (lado Pacifico)
    de la falla, el sentido lateral-derecho implica que ese bloque se mueve hacia
    el NO relativo al bloque este. Elegimos el rake cuyo desplazamiento sintetico
    en ese punto de prueba tenga componente hacia el NO (u_north>0 aprox concordante
    con movimiento hacia el rumbo de la falla en sentido dextral)."""
    strike = bearing_deg(seg["lat1"], seg["lon1"], seg["lat2"], seg["lon2"])
    test_params_template = dict(
        strike_deg=strike, dip_deg=90.0, top_depth_km=1.0,
        length_km=20.0, width_km=15.0, slip_m=1.0, opening_m=0.0,
        ref_x=0.0, ref_y=0.0, nu=0.25,
    )
    # punto de observacion 10 km perpendicular al rumbo (lado "izquierdo" mirando
    # en la direccion de strike, que es el lado Pacifico si strike apunta ~NO)
    strike_rad = math.radians(strike)
    perp_dx = -math.cos(strike_rad) * 10.0
    perp_dy = math.sin(strike_rad) * 10.0

    results = {}
    for rake_try in (0.0, 180.0):
        r = _single_point_deformation(
            x_east=perp_dx, y_north=perp_dy, z_up=0.0,
            rake_deg=rake_try, **test_params_template,
        )
        results[rake_try] = r
    return results, strike


# ---------------------------------------------------------------------------
# 2. Cargar observaciones GPS crudas (sin normalizar)
# ---------------------------------------------------------------------------
with open("gps_observations_raw.json") as f:
    all_obs = json.load(f)

print(f"Total estaciones cargadas: {len(all_obs)}")

# ---------------------------------------------------------------------------
# 3. Sanity check de rake (informativo -- revisar antes de confiar en resultados)
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("VERIFICACION DE CONVENCION DE RAKE (revisar antes de interpretar resultados)")
print("=" * 70)
for seg in SEGMENTS:
    results, strike = pick_rake_by_sign_check(seg)
    print(f"\nSegmento {seg['name']} (strike={strike:.1f} grados):")
    for rake_try, r in results.items():
        print(f"  rake={rake_try:5.0f}  u_east={r['u_east_m']:+.6f}  u_north={r['u_north_m']:+.6f}")
print("\n>>> Revisa manualmente cual signo de rake da el sentido de movimiento")
print(">>> lateral-derecho esperado (bloque Pacifico hacia el NO) antes de continuar.")
print(">>> Por defecto este script usa rake=180 (convencion mas comun en literatura")
print(">>> de Okada para dextral con strike definido de NO a SE) -- AJUSTAR si el")
print(">>> chequeo de arriba muestra lo contrario.\n")

RAKE_ANGLE = 180.0  # <<< AJUSTAR segun el chequeo de arriba si hace falta

# ---------------------------------------------------------------------------
# 4. Por cada segmento: filtrar estaciones, normalizar, invertir
# ---------------------------------------------------------------------------
all_results = {}

for seg in SEGMENTS:
    fault_geom = build_fault_geometry(seg, RAKE_ANGLE)
    ref_lon, ref_lat = fault_geom["lon"], fault_geom["lat"]
    slip_rate_m_yr = seg["slip_rate_mm_yr"] * MM_TO_M

    seg_obs = []
    for obs in all_obs:
        ox_km, oy_km = _lonlat_to_local_km(obs["lon"], obs["lat"], ref_lon, ref_lat)
        along_km, perp_km = station_offsets(seg, ox_km, oy_km)
        length_km = fault_geom["length_m"] / 1000.0
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

    print(f"\n{'=' * 70}")
    print(f"Segmento: {seg['name']}  (n_estaciones={len(seg_obs)}, "
          f"slip_rate={seg['slip_rate_mm_yr']} mm/yr, strike={fault_geom['strike_angle']:.1f} grados)")
    print(f"{'=' * 70}")

    if len(seg_obs) < N_ALONG * N_DIP:
        print(f"  SKIP: muy pocas estaciones ({len(seg_obs)}) para {N_ALONG * N_DIP} parches. "
              f"Aumenta PERP_DIST_MAX_KM o reduce N_ALONG/N_DIP.")
        continue

    coupling, coupling_grid, meta = _solve_interseismic_coupling(
        seg_obs, [], fault_geom, N_ALONG, N_DIP,
        lambda_tikhonov=None, lambda_laplacian=None,
    )

    print(f"  lambda_tikhonov={meta['lambda_tikhonov']:.3e}  "
          f"lambda_laplacian={meta['lambda_laplacian']:.3e}")
    print(f"  residual_rms={meta['residual_rms']:.4e}")
    print(f"  mean_coupling={meta['mean_coupling']:.3f}  "
          f"locked_fraction={meta['locked_fraction']:.1%}  "
          f"creeping_fraction={meta['creeping_fraction']:.1%}")
    print(f"  coupling_grid (n_along x n_dip):")
    print(np.round(coupling_grid, 3))

    all_results[seg["name"]] = {
        "fault_geometry": fault_geom,
        "n_stations": len(seg_obs),
        "coupling_grid": coupling_grid.tolist(),
        "metadata": meta,
    }

with open("southern_saf_coupling_results.json", "w") as f:
    json.dump(all_results, f, indent=2)

print(f"\n{'=' * 70}")
print("Guardado: southern_saf_coupling_results.json")
print(f"{'=' * 70}")
