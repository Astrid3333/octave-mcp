#!/usr/bin/env python3
"""
pipeline_demo_flood_connectivity_real_elevation.py

Variante de pipeline_demo_flood_connectivity.py que usa ELEVACION REAL
(via terrain_elevation_tool / OpenTopoData) en vez de la expresion
sintetica de synthetic_elevation.py.

Encadena:
  1. distmesh_tool.compute_distmesh(mode="mesh_2d")  -> malla real del
     dominio, en coordenadas locales (x,y).
  2. mesh_geo_utils.mesh_points_to_latlon()  -> convierte cada nodo de
     la malla a lat/lon real, a partir de un origen georreferenciado
     (origin_lat, origin_lon) y una escala (units_per_meter).
  3. terrain_elevation_tool.compute_terrain_elevation(mode="elevation_lookup")
     -> elevacion REAL de OpenTopoData para cada nodo. LLAMADA DE RED
     REAL -- requiere conectividad a api.opentopodata.org.
  4. flood_connectivity_tool.compute_flood_connectivity_tool(
       mode="bathtub_fill_connectivity")  -> inundacion por conectividad,
     igual firma que la version sintetica.

Adaptador de nombres de campo (igual que en la version sintetica):
  distmesh_tool devuelve 'points' / 'triangles'.
  flood_connectivity_tool espera 'vertices' / 'faces'.

DIFERENCIA CLAVE con la version sintetica: 'elevations' ahora viene de
un dataset real (default srtm90m, ~90m de resolucion horizontal). Dos
advertencias que hay que mantener visibles:
  (a) la conversion (x,y)->lat/lon es una aproximacion equirectangular
      simple (ver mesh_geo_utils.py), valida para dominios chicos;
  (b) si algun nodo cae en un punto sin cobertura del dataset (mar,
      hueco de datos), terrain_elevation_tool devuelve None -- este
      script lo trata como error fatal en vez de silenciarlo, porque
      flood_connectivity_tool no sabe interpretar elevacion None.

query_point sigue en coordenadas LOCALES (x,y) de la malla, igual que
en la version sintetica -- no se convierte a lat/lon, porque
flood_connectivity_tool lo usa para ubicar el triangulo contenedor en
el mismo sistema de coordenadas que vertices/faces.

Corre standalone: python3 pipeline_demo_flood_connectivity_real_elevation.py
(hace una llamada de red real -- no correr desde el sandbox de Claude)
"""

import json

from distmesh_tool import compute_distmesh
from mesh_geo_utils import mesh_points_to_latlon
from terrain_elevation_tool import compute_terrain_elevation
from flood_connectivity_tool import compute_flood_connectivity_tool


def _select_river_seeds(points, edge="x_min", tol=1e-3):
    """Identico a la version sintetica -- selecciona el borde del
    dominio que se usa como semilla de inundacion (el 'cauce del rio')."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    if edge == "x_min":
        target = min(xs)
        return [i for i, p in enumerate(points) if abs(p[0] - target) < tol]
    if edge == "x_max":
        target = max(xs)
        return [i for i, p in enumerate(points) if abs(p[0] - target) < tol]
    if edge == "y_min":
        target = min(ys)
        return [i for i, p in enumerate(points) if abs(p[1] - target) < tol]
    if edge == "y_max":
        target = max(ys)
        return [i for i, p in enumerate(points) if abs(p[1] - target) < tol]
    raise ValueError(f"edge desconocido: {edge!r}")


def run_demo_real_elevation(bbox, h0, origin_lat, origin_lon, water_level,
                             units_per_meter=1.0, dataset="srtm90m",
                             river_edge="x_min", query_point=None,
                             max_iter=200, seed_tol=None):
    # 1. Malla real (coordenadas locales)
    mesh = compute_distmesh(
        mode="mesh_2d", domain="rectangle", bbox=bbox, h0=h0,
        max_iter=max_iter,
    )

    if not mesh.get("converged", True):
        print(f"AVISO: la malla no convergio ({mesh.get('iterations_used')} "
              f"iteraciones). quality_warning={mesh.get('quality_warning')!r}, "
              f"min_angle_deg={mesh.get('quality', {}).get('min_angle_deg')}. "
              f"Revisar antes de confiar en el resultado hidraulico.")

    points = mesh["points"]
    triangles = mesh["triangles"]

    # 2. Conversion de coordenadas locales a lat/lon real
    latlons = mesh_points_to_latlon(points, origin_lat, origin_lon, units_per_meter)

    # 3. Elevacion REAL via OpenTopoData (llamada de red real)
    elevation_result = compute_terrain_elevation(
        "elevation_lookup", {"locations": latlons, "dataset": dataset}
    )
    elevations = elevation_result["elevations_m"]

    missing = [i for i, e in enumerate(elevations) if e is None]
    if missing:
        raise RuntimeError(
            f"{len(missing)} nodo(s) sin cobertura de elevacion en el dataset "
            f"'{dataset}' (indices: {missing[:10]}{'...' if len(missing) > 10 else ''}). "
            f"flood_connectivity_tool no puede operar con elevacion None -- "
            f"probar otro origen/dataset, o excluir esos nodos del dominio."
        )

    # 4. Semillas: borde del dominio elegido como "cauce del rio".
    # tol proporcional a h0 (no una constante absoluta): distmesh_tool
    # relaja los nodos del borde con el solver de resortes, no quedan
    # exactamente en el valor nominal del borde -- con tol=1e-3 fijo
    # solo el nodo mas extremo pasa el filtro (visto en corridas reales:
    # 1 de 9 nodos esperados), dejando "el rio" reducido a un solo punto
    # y el resultado de inundacion a merced de la elevacion de ese unico
    # nodo. h0/2 es un margen conservador: cualquier nodo a menos de
    # medio espaciado de malla del borde nominal se considera parte del
    # borde.
    if seed_tol is None:
        seed_tol = h0 / 2
    seed_indices = _select_river_seeds(points, edge=river_edge, tol=seed_tol)
    if not seed_indices:
        raise RuntimeError(f"No se encontraron puntos en el borde {river_edge!r}")

    # 5. Inundacion por conectividad, misma llamada que la version sintetica
    flood_result = compute_flood_connectivity_tool(
        mode="bathtub_fill_connectivity",
        vertices=points,          # adaptador de nombre: points -> vertices
        faces=triangles,          # adaptador de nombre: triangles -> faces
        elevations=elevations,
        seed_indices=seed_indices,
        water_level=water_level,
        query_point=query_point,
    )

    return {
        "mesh_summary": {
            "n_points": mesh["n_points"],
            "n_triangles": mesh["n_triangles"],
            "converged": mesh["converged"],
            "min_angle_deg": mesh.get("quality", {}).get("min_angle_deg"),
        },
        "geo_origin": {"lat": origin_lat, "lon": origin_lon, "units_per_meter": units_per_meter},
        "seed_tol_used": seed_tol,
        "elevation_dataset": dataset,
        "elevation_range_m": {"min": min(elevations), "max": max(elevations)},
        "seed_indices": seed_indices,
        "flood_result": flood_result,
    }


if __name__ == "__main__":
    # Punto de prueba GENERICO (Mississippi cerca de Memphis, TN) -- solo
    # para validar que el pipeline geometrico + red + inundacion funciona
    # de punta a punta. NO representa ningun sitio real de analisis.
    # Dominio de 200x200 metros alrededor del origen (bbox/h0 en metros
    # porque units_per_meter=1.0).
    #
    # water_level es un valor de arranque -- correr una vez, mirar
    # 'elevation_range_m' en la salida, y ajustarlo para que quede
    # DENTRO de ese rango (si no, todo se inunda o nada se inunda).
    result = run_demo_real_elevation(
        bbox=[0, 200, 0, 200],
        h0=25.0,
        origin_lat=35.1495,
        origin_lon=-90.0490,
        units_per_meter=1.0,
        water_level=65.0,
        river_edge="x_min",
        query_point=[150.0, 100.0],
        max_iter=200,
        # seed_tol=None -> default h0/2, ver nota en run_demo_real_elevation
    )
    print(json.dumps(result, indent=2))
    print(f"\nseeds: {len(result['seed_indices'])} nodo(s), "
          f"seed_tol usado: {result['seed_tol_used']}", file=__import__("sys").stderr)
