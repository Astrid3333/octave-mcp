#!/usr/bin/env python3
"""
flood_connectivity_tool.py

Inundacion por conectividad ("priority-flood" / bathtub-fill conectado)
sobre una malla 2D con elevacion por nodo.

A diferencia de un bathtub-fill ingenuo (marcar inundado todo nodo con
z < nivel_agua), este tool propaga la inundacion desde una o mas semillas
(el cauce del rio) siguiendo unicamente caminos conectados de la malla
cuya cota es <= nivel_agua. Esto evita el falso positivo clasico de
marcar como inundada una depresion del terreno que esta por debajo del
nivel de crecida pero aislada del rio por una loma intermedia.

Algoritmo: priority-flood via heap (Barnes et al., "Priority-flood: An
optimal depression-filling and watershed-labeling algorithm"), adaptado
a expansion desde semillas fijas en vez de relleno global.

Complejidad: O(n log n) sobre el numero de nodos de la malla.

Integra con el patron octave-mcp:
  - Pensado para recibir vertices/faces de distmesh_tool.py (mode="mesh_2d").
  - mode="mesh_quality" de distmesh_tool.py se recomienda correr ANTES
    sobre la malla, para descartar triangulos degenerados que puedan
    generar adyacencias espurias.

DEPENDENCIA PENDIENTE (documentada, no resuelta por este tool):
  Este tool NO trae datos de elevacion. El campo `elevations` debe llegar
  ya resuelto por quien llama al tool -- hoy no hay ninguna tool en
  octave-mcp que consulte una fuente de elevacion real (SRTM,
  OpenTopoData, IDEAM, etc.). `public_data_ingest_tool.py` tampoco cubre
  esto: es un tool de calidad de datos (outliers, deduplicacion, scoring),
  no un conector a APIs externas. Hasta que exista esa integracion, el
  uso previsto es: el usuario carga manualmente las cotas (ej. desde un
  levantamiento local o un mapa de curvas de nivel), o se pasa una
  funcion sintetica para pruebas / demos.

Dependencias: ninguna fuera de la stdlib (heapq).
"""

import heapq
import json
import math


# ---------------------------------------------------------------------------
# Nucleo
# ---------------------------------------------------------------------------

def _build_adjacency(n, faces):
    adj = [set() for _ in range(n)]
    for tri in faces:
        i, j, k = int(tri[0]), int(tri[1]), int(tri[2])
        adj[i] |= {j, k}
        adj[j] |= {i, k}
        adj[k] |= {i, j}
    return adj


def _bathtub_fill_connectivity(vertices, faces, elevations, seed_indices, water_level):
    n = len(vertices)
    if len(elevations) != n:
        raise ValueError(
            f"elevations tiene {len(elevations)} valores, se esperaban {n} (uno por vertice)"
        )
    for s in seed_indices:
        if not (0 <= s < n):
            raise ValueError(f"seed_indices contiene un indice fuera de rango: {s}")

    adj = _build_adjacency(n, faces)
    elevations = [float(z) for z in elevations]
    water_level = float(water_level)

    flooded = {}       # idx -> profundidad (agua sobre el terreno en ese nodo)
    visited = set()
    heap = []

    dry_seeds = []
    for s in seed_indices:
        if elevations[s] <= water_level:
            heapq.heappush(heap, (elevations[s], s))
        else:
            dry_seeds.append(s)

    while heap:
        z, node = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        if z > water_level:
            # No deberia ocurrir (solo empujamos nodos con z <= water_level),
            # queda como salvaguarda defensiva.
            continue
        flooded[node] = round(water_level - z, 6)
        for nb in adj[node]:
            if nb not in visited and elevations[nb] <= water_level:
                heapq.heappush(heap, (elevations[nb], nb))

    return {
        "flooded_nodes": sorted(flooded.keys()),
        "depths": {str(k): v for k, v in flooded.items()},
        "n_flooded": len(flooded),
        "n_total": n,
        "dry_seeds": dry_seeds,
        "water_level": water_level,
    }


def _point_in_triangle_barycentric(p, a, b, c):
    """Coordenadas baricentricas de p respecto al triangulo a-b-c.
    Devuelve None si p esta fuera del triangulo (con tolerancia)."""
    v0 = (c[0] - a[0], c[1] - a[1])
    v1 = (b[0] - a[0], b[1] - a[1])
    v2 = (p[0] - a[0], p[1] - a[1])

    dot00 = v0[0] * v0[0] + v0[1] * v0[1]
    dot01 = v0[0] * v1[0] + v0[1] * v1[1]
    dot02 = v0[0] * v2[0] + v0[1] * v2[1]
    dot11 = v1[0] * v1[0] + v1[1] * v1[1]
    dot12 = v1[0] * v2[0] + v1[1] * v2[1]

    denom = dot00 * dot11 - dot01 * dot01
    if abs(denom) < 1e-14:
        return None
    inv_denom = 1.0 / denom
    u = (dot11 * dot02 - dot01 * dot12) * inv_denom
    v = (dot00 * dot12 - dot01 * dot02) * inv_denom
    w = 1.0 - u - v

    tol = 1e-9
    if u >= -tol and v >= -tol and w >= -tol:
        return (w, v, u)  # pesos para (a, b, c)
    return None


def _query_depth_at_point(vertices, faces, elevations, water_level, flood_result, query_xy):
    """Interpola la profundidad de inundacion en un punto arbitrario (no
    necesariamente un vertice de la malla), usando coordenadas baricentricas
    del triangulo que lo contiene. Devuelve None si el punto cae fuera de
    la malla.

    IMPORTANTE (conectividad): el punto solo se reporta como inundado si
    los 3 vertices del triangulo que lo contiene estan en el conjunto
    conectado (flood_result['depths']). Comparar la elevacion interpolada
    contra water_level sin este chequeo reproduce el bug de bathtub-fill
    ingenuo que este tool existe para evitar -- un punto geometricamente
    bajo pero aislado del rio por una loma NO debe marcarse inundado."""
    depths_by_node = flood_result["depths"]
    for tri in faces:
        i, j, k = int(tri[0]), int(tri[1]), int(tri[2])
        a, b, c = vertices[i], vertices[j], vertices[k]
        bary = _point_in_triangle_barycentric(query_xy, a, b, c)
        if bary is None:
            continue
        wa, wb, wc = bary

        flooded_verts = [str(idx) in depths_by_node for idx in (i, j, k)]
        z_interp = wa * elevations[i] + wb * elevations[j] + wc * elevations[k]

        if not all(flooded_verts):
            # Al menos un vertice del triangulo no esta conectado a la
            # inundacion (aunque su cota sea baja) -> punto NO inundado.
            return {"flooded": False, "depth": 0.0, "elevation_interp": round(z_interp, 6),
                    "triangle": [i, j, k],
                    "nota": "triangulo no completamente conectado a la inundacion"}

        # Los 3 vertices estan conectados: interpolar PROFUNDIDAD real
        # (no elevacion) usando los valores ya calculados por el flood-fill.
        depth = (wa * depths_by_node[str(i)] + wb * depths_by_node[str(j)]
                 + wc * depths_by_node[str(k)])
        return {"flooded": True, "depth": round(depth, 6), "elevation_interp": round(z_interp, 6),
                "triangle": [i, j, k]}
    return None  # punto fuera de la malla


# ---------------------------------------------------------------------------
# Casos de prueba sinteticos (usados por mode=validate)
# ---------------------------------------------------------------------------

def _linear_chain_case():
    """5 nodos en fila. La semilla (nodo 0) tiene cota BAJA (mojada), y las
    cotas SUBEN hacia el otro extremo. Con water_level=6 deberian inundarse
    los nodos 0,1,2 (cotas 1,3,5, todas <= 6) pero NO 3,4 (cotas 7,9)."""
    vertices = [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0]]
    faces = [[0, 1, 2], [1, 2, 3], [2, 3, 4]]  # conectividad en cadena (triangulos degenerados a proposito, solo para adyacencia)
    elevations = [1, 3, 5, 7, 9]
    seed_indices = [0]
    water_level = 6
    return vertices, faces, elevations, seed_indices, water_level


def _isolated_depression_case():
    """Rejilla simple: nodo central (idx 4) tiene cota BAJA pero esta
    rodeado por un anillo de cota ALTA, y la semilla esta en una esquina
    del anillo exterior. El nodo central NO debe inundarse aunque su cota
    sea menor que water_level, porque no hay camino conectado con cota
    <= water_level hasta el.

    Grilla 3x3 (indices):
        0 1 2
        3 4 5
        6 7 8
    """
    vertices = [[x, y] for y in range(3) for x in range(3)]
    # Triangulacion simple de la grilla 3x3 (2 triangulos por celda)
    faces = []
    for r in range(2):
        for c in range(2):
            tl = r * 3 + c
            tr = tl + 1
            bl = tl + 3
            br = bl + 1
            faces.append([tl, tr, bl])
            faces.append([tr, br, bl])

    elevations = [10, 10, 10,
                  10, 1, 10,   # nodo 4 = depresion aislada
                  10, 10, 10]
    seed_indices = [0]      # esquina superior izquierda, cota 10
    water_level = 5         # cubre la semilla? NO: 10 > 5 -> no se inunda nada
    return vertices, faces, elevations, seed_indices, water_level


def _dry_seed_case():
    vertices = [[0, 0], [1, 0], [2, 0]]
    faces = [[0, 1, 2]]
    elevations = [10, 8, 6]
    seed_indices = [0]
    water_level = 5  # por debajo de TODAS las cotas, incluida la semilla
    return vertices, faces, elevations, seed_indices, water_level


def validate():
    checks = []

    # Check 1: cadena lineal, corte a la mitad (semilla mojada, propagacion
    # se detiene apenas la cota supera water_level)
    v, f, z, s, wl = _linear_chain_case()
    r = _bathtub_fill_connectivity(v, f, z, s, wl)
    actual_flooded = set(r["flooded_nodes"])
    check1_ok = (actual_flooded == {0, 1, 2})  # cotas 1,3,5 <=6 ; 7,9 quedan secos
    checks.append({"nombre": "cadena_lineal_umbral_basico", "paso": bool(check1_ok),
                    "detalle": {"flooded": sorted(actual_flooded)}})

    # Check 2: depresion aislada NO debe inundarse (el check clave)
    v, f, z, s, wl = _isolated_depression_case()
    r = _bathtub_fill_connectivity(v, f, z, s, wl)
    check2_ok = (r["n_flooded"] == 0) and (4 not in r["flooded_nodes"])
    checks.append({"nombre": "depresion_aislada_no_se_inunda", "paso": bool(check2_ok),
                    "detalle": {"flooded": r["flooded_nodes"], "dry_seeds": r["dry_seeds"]}})

    # Check 2b: mismo caso pero con water_level que SI conecta hasta el centro
    v, f, z, s, _ = _isolated_depression_case()
    r2 = _bathtub_fill_connectivity(v, f, z, s, water_level=10)
    check2b_ok = (4 in r2["flooded_nodes"]) and (r2["n_flooded"] == 9)
    checks.append({"nombre": "depresion_aislada_se_inunda_con_nivel_suficiente",
                    "paso": bool(check2b_ok), "detalle": {"flooded": r2["flooded_nodes"]}})

    # Check 3: semilla seca -> resultado vacio, sin excepcion
    v, f, z, s, wl = _dry_seed_case()
    r = _bathtub_fill_connectivity(v, f, z, s, wl)
    check3_ok = (r["n_flooded"] == 0) and (s[0] in r["dry_seeds"])
    checks.append({"nombre": "semilla_seca_resultado_vacio", "paso": bool(check3_ok),
                    "detalle": r})

    # Check 4: interpolacion baricentrica en un punto interior de un triangulo
    # totalmente conectado
    v, f, z, s, wl = _isolated_depression_case()
    r = _bathtub_fill_connectivity(v, f, z, s, water_level=10)
    # punto en el centro del triangulo [0,1,3] (cotas 10,10,10) -> deberia
    # interpolar a 10.0 exacto, con profundidad 0
    q = _query_depth_at_point(v, f, z, 10, r, query_xy=(0.33, 0.33))
    check4_ok = (q is not None) and abs(q["elevation_interp"] - 10.0) < 1e-6
    checks.append({"nombre": "interpolacion_baricentrica_punto_consulta",
                    "paso": bool(check4_ok), "detalle": q})

    # Check 5: consulta en un triangulo NO completamente conectado debe dar
    # flooded=False aunque su elevacion interpolada sea baja (este es el
    # check que verifica el fix del bug de conectividad en query_point)
    v, f, z, s, wl = _isolated_depression_case()
    r = _bathtub_fill_connectivity(v, f, z, s, wl)  # water_level=5, todo seco
    q5 = _query_depth_at_point(v, f, z, wl, r, query_xy=(1.0, 1.0))  # cerca del nodo 4 (cota 1, bajo)
    check5_ok = (q5 is not None) and (q5["flooded"] is False)
    checks.append({"nombre": "query_point_respeta_conectividad_no_falso_positivo",
                    "paso": bool(check5_ok), "detalle": q5})

    todos_pasaron = all(c["paso"] for c in checks)
    return {"checks": checks, "todos_pasaron": todos_pasaron, "validation_passed": todos_pasaron}


# ---------------------------------------------------------------------------
# Entry point / handler
# ---------------------------------------------------------------------------

def compute_flood_connectivity_tool(mode, vertices=None, faces=None, elevations=None,
                                     seed_indices=None, water_level=None,
                                     query_point=None):
    """Funcion nucleo, usable directo en Python/tests (no es el handler MCP)."""
    if mode == "bathtub_fill_connectivity":
        if vertices is None or faces is None or elevations is None:
            raise ValueError("bathtub_fill_connectivity requiere 'vertices', 'faces' y 'elevations'")
        if seed_indices is None:
            raise ValueError("bathtub_fill_connectivity requiere 'seed_indices'")
        if water_level is None:
            raise ValueError("bathtub_fill_connectivity requiere 'water_level'")

        result = _bathtub_fill_connectivity(vertices, faces, elevations, seed_indices, water_level)

        if query_point is not None:
            q = _query_depth_at_point(vertices, faces, elevations, water_level, result, query_point)
            result["query_point_result"] = q

        result["confidence_flag"] = (
            "elevacion: no verificada externamente -- este tool no consulta ninguna "
            "fuente de elevacion real, asume que 'elevations' fue provisto correctamente "
            "por quien llama"
        )
        return result

    if mode == "validate":
        return validate()

    raise ValueError(f"mode desconocido: {mode!r}")


def _handle(args):
    """Handler MCP: recibe el dict `args` de tools/call y delega."""
    return compute_flood_connectivity_tool(
        mode=args.get("mode"),
        vertices=args.get("vertices"),
        faces=args.get("faces"),
        elevations=args.get("elevations"),
        seed_indices=args.get("seed_indices"),
        water_level=args.get("water_level"),
        query_point=args.get("query_point"),
    )


# ---------------------------------------------------------------------------
# Schema (patron octave-mcp)
# ---------------------------------------------------------------------------

FLOOD_CONNECTIVITY_TOOL_SCHEMA = {
    "name": "flood_connectivity_tool",
    "description": (
        "Inundacion por conectividad (priority-flood) sobre una malla 2D con "
        "elevacion por nodo. A diferencia de un umbral simple (z < nivel), "
        "propaga la inundacion desde semillas (el cauce del rio) siguiendo solo "
        "caminos conectados con cota <= nivel_agua, evitando falsos positivos "
        "en depresiones de terreno aisladas. Pensado para recibir vertices/faces "
        "de distmesh_tool.py (mode='mesh_2d'). "
        "IMPORTANTE: no trae datos de elevacion -- 'elevations' debe ser provisto "
        "por quien llama (no hay integracion con SRTM/OpenTopoData/etc. todavia)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["bathtub_fill_connectivity", "validate"],
                "description": (
                    "bathtub_fill_connectivity: corre la propagacion de inundacion. "
                    "validate: suite de auto-chequeo (umbral basico, depresion aislada, "
                    "semilla seca, interpolacion baricentrica)."
                ),
            },
            "vertices": {
                "type": "array",
                "description": "Lista de [x,y]. bathtub_fill_connectivity. Tipicamente sale de distmesh_tool (mode='mesh_2d').",
            },
            "faces": {
                "type": "array",
                "description": "Lista de [i,j,k] (indices en vertices). bathtub_fill_connectivity.",
            },
            "elevations": {
                "type": "array",
                "description": (
                    "Lista de cotas, una por vertice, mismo orden que 'vertices'. "
                    "DEBE ser provista externamente -- este tool no consulta ninguna "
                    "fuente de elevacion real."
                ),
            },
            "seed_indices": {
                "type": "array",
                "description": "Indices de vertices que representan la fuente de inundacion (el cauce del rio). bathtub_fill_connectivity.",
            },
            "water_level": {
                "type": "number",
                "description": "Cota de la crecida a evaluar. bathtub_fill_connectivity.",
            },
            "query_point": {
                "type": "array",
                "description": "Opcional. [x,y] de un punto arbitrario (ej. la casa del usuario) para interpolar profundidad via coordenadas baricentricas. bathtub_fill_connectivity.",
            },
        },
        "required": ["mode"],
    },
}


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("flood_connectivity_tool", FLOOD_CONNECTIVITY_TOOL_SCHEMA,
              lambda args, _f=compute_flood_connectivity_tool: _f(
                  mode=args.get("mode"),
                  vertices=args.get("vertices"),
                  faces=args.get("faces"),
                  elevations=args.get("elevations"),
                  seed_indices=args.get("seed_indices"),
                  water_level=args.get("water_level"),
                  query_point=args.get("query_point"),
              ))


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
