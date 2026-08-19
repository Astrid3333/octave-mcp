"""
mesh_geo_utils.py

Conversion simple de coordenadas locales (x,y) de una malla de
distmesh_tool a lat/lon reales, para poder pedirle elevacion real a
terrain_elevation_tool por cada nodo de la malla.

Aproximacion equirectangular (valida para dominios chicos, del orden
de cientos de metros a pocos km -- el error de esta aproximacion crece
con la distancia al origen y con la latitud, pero para el tamano tipico
de un dominio de flood_connectivity_tool es despreciable frente a la
resolucion horizontal del dataset de elevacion (~90m para srtm90m)).

NO es un tool MCP (no tiene modo validate ni se registra en
tool_registry) -- es un helper de soporte, mismo rol que
synthetic_elevation.py.
"""

import math


METERS_PER_DEGREE_LAT = 111320.0


def local_xy_to_latlon(origin_lat, origin_lon, x, y, units_per_meter=1.0):
    """
    origin_lat, origin_lon: lat/lon reales del punto (x=0, y=0) de la malla.
    x, y: coordenadas locales de un nodo de la malla (mismas unidades
          que bbox/h0 en distmesh_tool).
    units_per_meter: cuantas unidades locales equivalen a 1 metro real.
          Si el dominio de distmesh_tool ya esta en metros, dejar en 1.0.
    Devuelve (lat, lon).
    """
    x_m = x / units_per_meter
    y_m = y / units_per_meter
    lat = origin_lat + y_m / METERS_PER_DEGREE_LAT
    meters_per_degree_lon = METERS_PER_DEGREE_LAT * math.cos(math.radians(origin_lat))
    lon = origin_lon + x_m / meters_per_degree_lon
    return lat, lon


def mesh_points_to_latlon(points, origin_lat, origin_lon, units_per_meter=1.0):
    """points: lista de [x, y] (formato que devuelve distmesh_tool).
    Devuelve lista de [lat, lon] en el mismo orden -- lista directamente
    usable como params['locations'] de terrain_elevation_tool."""
    return [
        list(local_xy_to_latlon(origin_lat, origin_lon, x, y, units_per_meter))
        for x, y in points
    ]


def _self_test():
    checks = []

    # Check 1: el origen (0,0) mapea exactamente a (origin_lat, origin_lon)
    lat, lon = local_xy_to_latlon(35.1495, -90.0490, 0, 0)
    ok = abs(lat - 35.1495) < 1e-9 and abs(lon - (-90.0490)) < 1e-9
    checks.append(("origen_mapea_a_si_mismo", ok, (lat, lon)))

    # Check 2: moverse 1000m en y (norte) cambia la latitud en ~1000/111320 grados
    lat, lon = local_xy_to_latlon(35.1495, -90.0490, 0, 1000)
    expected_dlat = 1000 / METERS_PER_DEGREE_LAT
    ok = abs((lat - 35.1495) - expected_dlat) < 1e-9
    checks.append(("desplazamiento_norte_1000m", ok, lat - 35.1495))

    # Check 3: mesh_points_to_latlon preserva el orden y la cantidad
    pts = [[0, 0], [100, 0], [0, 100], [-50, 50]]
    latlons = mesh_points_to_latlon(pts, 35.1495, -90.0490)
    ok = len(latlons) == 4 and latlons[0] == [35.1495, -90.0490]
    checks.append(("mesh_points_orden_y_cantidad", ok, latlons))

    # Check 4: units_per_meter=2 (malla en unidades de "medio metro")
    # produce la mitad del desplazamiento real
    lat_a, _ = local_xy_to_latlon(35.1495, -90.0490, 0, 1000, units_per_meter=1.0)
    lat_b, _ = local_xy_to_latlon(35.1495, -90.0490, 0, 1000, units_per_meter=2.0)
    ok = abs((lat_a - 35.1495) - 2 * (lat_b - 35.1495)) < 1e-9
    checks.append(("units_per_meter_escala_correctamente", ok, (lat_a, lat_b)))

    todos = all(c[1] for c in checks)
    for nombre, paso, detalle in checks:
        print(f"  {'OK' if paso else 'FALLO'}  {nombre}  {detalle}")
    print(f"todos_pasaron: {todos}")
    return todos


if __name__ == "__main__":
    _self_test()
