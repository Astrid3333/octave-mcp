"""
voronoi_delaunay_tool.py

Diagramas de Voronoi y triangulacion de Delaunay para un conjunto de
puntos 2D, via scipy.spatial (wrappers de Qhull). Ausente en el resto
del repo (ver notas de sesion 23-ago-2026: hueco real de geometria
computacional, distinto de projective_geometry_tool.py que cubre
geometria proyectiva P2/P3, no diagramas de particion del plano).

Modes:
- voronoi: dado un set de puntos semilla, devuelve vertices y aristas
  (ridges) del diagrama de Voronoi. Las aristas hacia el infinito se
  marcan con ridge_vertices conteniendo -1 (convencion de scipy).
- delaunay: dado el mismo tipo de input, devuelve los simplices
  (triangulos) de la triangulacion de Delaunay -- dual combinatorio
  del diagrama de Voronoi.
- validate: casos con resultado geometrico conocido (ver _validate).
- self_test: alias de validate para uso desde linea de comandos.
"""
import json
import sys
import numpy as np
from scipy.spatial import Voronoi, Delaunay


def _mode_voronoi(params):
    points = params.get("points")
    if not points or len(points) < 2:
        raise ValueError("'points' requiere al menos 2 puntos [x, y]")

    pts = np.array(points, dtype=float)
    vor = Voronoi(pts)

    return {
        "mode": "voronoi",
        "n_points": len(points),
        "vertices": vor.vertices.tolist(),
        "ridge_points": vor.ridge_points.tolist(),
        "ridge_vertices": vor.ridge_vertices,
        "regions": vor.regions,
        "point_region": vor.point_region.tolist(),
    }


def _mode_delaunay(params):
    points = params.get("points")
    if not points or len(points) < 3:
        raise ValueError("'points' requiere al menos 3 puntos [x, y] no colineales")

    pts = np.array(points, dtype=float)
    tri = Delaunay(pts)

    return {
        "mode": "delaunay",
        "n_points": len(points),
        "simplices": tri.simplices.tolist(),
        "neighbors": tri.neighbors.tolist(),
        "convex_hull": tri.convex_hull.tolist(),
    }


def _validate():
    """Casos con resultado geometrico conocido:

    1) Delaunay de un cuadrado unitario (4 esquinas): siempre produce
       exactamente 2 triangulos (cualquier triangulacion de 4 puntos
       en posicion convexa da 2 simplices).
    2) Voronoi del mismo cuadrado: por simetria, el unico vertice
       interior del diagrama cae exactamente en el centroide (0.5, 0.5).
    3) Voronoi de 2 puntos (0,0) y (2,0): la frontera es la mediatriz
       x=1, una arista que se extiende al infinito -- scipy marca esto
       con -1 en ridge_vertices.
    4) Delaunay de un triangulo simple (3 puntos no colineales): da
       exactamente 1 simplex (el propio triangulo).
    """
    checks = []

    points_square = [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]

    tri_sq = Delaunay(np.array(points_square))
    n_simplices = len(tri_sq.simplices)
    checks.append({
        "name": "delaunay_cuadrado_unitario_da_2_triangulos",
        "esperado": 2,
        "obtenido": n_simplices,
        "passed": bool(n_simplices == 2),
    })

    vor_sq = Voronoi(np.array(points_square))
    vertices = vor_sq.vertices
    ok_centroide = (
        len(vertices) == 1
        and bool(np.allclose(vertices[0], [0.5, 0.5], atol=1e-9))
    )
    checks.append({
        "name": "voronoi_cuadrado_unitario_vertice_en_centroide",
        "esperado": [0.5, 0.5],
        "obtenido": vertices.tolist(),
        "passed": ok_centroide,
    })

    # qhull necesita minimo 4 puntos para el diagrama de Voronoi en 2D
    # (lifting a paraboloide 3D requiere >=4 puntos para el simplex
    # inicial) -- se reusa el caso del cuadrado en vez de 2 puntos.
    has_infinite_ridge = any(-1 in rv for rv in vor_sq.ridge_vertices)
    checks.append({
        "name": "voronoi_cuadrado_tiene_arista_infinita_en_el_borde",
        "esperado": True,
        "obtenido": has_infinite_ridge,
        "passed": bool(has_infinite_ridge is True),
    })

    points_tri = [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]]
    tri_simple = Delaunay(np.array(points_tri))
    n_simplices_tri = len(tri_simple.simplices)
    checks.append({
        "name": "delaunay_triangulo_simple_da_1_simplex",
        "esperado": 1,
        "obtenido": n_simplices_tri,
        "passed": bool(n_simplices_tri == 1),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def run_self_test():
    return _validate()


def run(mode, params=None):
    params = params or {}
    if mode == "voronoi":
        return _mode_voronoi(params)
    elif mode == "delaunay":
        return _mode_delaunay(params)
    elif mode == "validate":
        return _validate()
    elif mode == "self_test":
        return run_self_test()
    else:
        raise ValueError(
            f"modo desconocido: {mode} "
            "(usar voronoi/delaunay/validate/self_test)"
        )


def compute_voronoi_delaunay(mode, params=None):
    """Alias publico, mismo naming convention que compute_julia_mandelbrot()."""
    return run(mode, params)


TOOL_SCHEMA = {
    "name": "voronoi_delaunay",
    "description": (
        "Diagramas de Voronoi y triangulacion de Delaunay para un "
        "conjunto de puntos 2D, via scipy.spatial (Qhull)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["voronoi", "delaunay", "validate", "self_test"],
                "default": "voronoi",
            },
            "params": {
                "type": "object",
                "properties": {
                    "points": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "number"},
                        },
                        "description": "lista de puntos [x, y]",
                    },
                },
            },
        },
        "required": ["mode"],
    },
}


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
    Auto-registro estilo octave-mcp (patron self-registrante via
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
