#!/usr/bin/env python3
"""
pipeline_demo_flood_connectivity.py

Script de integracion end-to-end (NO es un tool MCP, no lleva
register_tool ni import en server.py -- es un script standalone, mismo
patron que fit_dark_sector_to_cc_data.py o plot_dark_sector_comparison.py).

Encadena:
  1. distmesh_tool.compute_distmesh(mode="mesh_2d")  -> malla real del
     dominio (points, triangles)
  2. synthetic_elevation.elevations_from_expression()  -> elevacion
     SINTETICA (no real -- ver DEPENDENCIA PENDIENTE mas abajo)
  3. flood_connectivity_tool.compute_flood_connectivity_tool(
       mode="bathtub_fill_connectivity")  -> inundacion por conectividad

Adaptador de nombres de campo:
  distmesh_tool devuelve 'points' / 'triangles'.
  flood_connectivity_tool espera 'vertices' / 'faces'.
  Son el mismo dato (lista de [x,y] / lista de [i,j,k]), solo cambia el
  nombre de la clave -- se mapea 1:1 sin transformacion.

DEPENDENCIA PENDIENTE: la elevacion que usa este script es sintetica
(una expresion matematica evaluada en x,y), NO un dato de terreno real.
Este script sirve para verificar que el pipeline geometrico funciona de
punta a punta con datos consistentes -- NO para generar un informe de
riesgo real de una direccion concreta. Ver synthetic_elevation.py.

Corre standalone: python3 pipeline_demo_flood_connectivity.py
"""

import json

from distmesh_tool import compute_distmesh
from synthetic_elevation import elevations_from_expression
from flood_connectivity_tool import compute_flood_connectivity_tool


def _select_river_seeds(points, edge="x_min", tol=1e-3):
    """Selecciona los indices de puntos sobre un borde del dominio, para
    usarlos como semilla de inundacion (el 'cauce del rio' en el ejemplo).
    edge: 'x_min' | 'x_max' | 'y_min' | 'y_max'."""
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


def run_demo(bbox, h0, elevation_expr, water_level, river_edge="x_min",
             query_point=None, max_iterations=200):
    # 1. Malla real
    mesh = compute_distmesh(
        mode="mesh_2d", domain="rectangle", bbox=bbox, h0=h0,
        max_iterations=max_iterations,
    )

    if not mesh.get("converged", True):
        print(f"AVISO: la malla no convergio ({mesh.get('iterations_used')} "
              f"iteraciones). quality_warning={mesh.get('quality_warning')!r}, "
              f"min_angle_deg={mesh.get('quality', {}).get('min_angle_deg')}. "
              f"Revisar antes de confiar en el resultado hidraulico.")

    points = mesh["points"]
    triangles = mesh["triangles"]

    # 2. Elevacion SINTETICA (no real -- ver docstring del modulo)
    elevations = elevations_from_expression(points, elevation_expr)

    # 3. Semillas: borde del dominio elegido como "cauce del rio"
    seed_indices = _select_river_seeds(points, edge=river_edge)
    if not seed_indices:
        raise RuntimeError(f"No se encontraron puntos en el borde {river_edge!r}")

    # 4. Inundacion por conectividad
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
        "seed_indices": seed_indices,
        "flood_result": flood_result,
    }


if __name__ == "__main__":
    # Ejemplo: dominio 4x4, rio en el borde x_min, terreno sintetico que
    # BAJA hacia el rio (mas bajo cerca de x=0, mas alto lejos: 2 + 1.5*x),
    # crecida a cota 6.
    result = run_demo(
        bbox=[0, 4, 0, 4],
        h0=0.5,
        elevation_expr="2 + 1.5*x",
        water_level=6.0,
        river_edge="x_min",
        query_point=[3.0, 2.0],   # "casa" en el extremo opuesto al rio
    )
    print(json.dumps(result, indent=2))
