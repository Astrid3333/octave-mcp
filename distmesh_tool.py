#!/usr/bin/env python3
"""
distmesh_tool.py

Generacion de malla triangular 2D via el algoritmo de Persson & Strang
(distmesh, SIAM Review 2004): modela la malla como una celosia de barras
con resortes que buscan una longitud de arista objetivo (h0), resolviendo
iterativamente un equilibrio de fuerzas sobre una triangulacion de Delaunay
que se recalcula cuando los nodos se mueven lo suficiente.

El dominio se define via una funcion de distancia con signo (SDF, fd):
negativa dentro del dominio, positiva fuera, cero en el borde. Presets
disponibles: 'rectangle', 'circle', 'circle_with_hole' (anillo), o
'custom' via una expresion sympy en x,y.

mode='mesh_2d' genera la malla; mode='mesh_quality' analiza una malla
externa (puntos + triangulos) via angulo minimo y relacion de aspecto por
triangulo; mode='validate' corre el caso canonico (circulo unitario) y
chequea que el algoritmo converja a una malla de buena calidad.

Corre standalone: python3 distmesh_tool.py
"""
import json
import math

import numpy as np
from scipy.spatial import Delaunay
import sympy as sp


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _round(x, nd=6):
    if isinstance(x, (int, float, np.floating, np.integer)):
        return round(float(x), nd)
    return x


def _round_list(arr, nd=6):
    return [[_round(v, nd) for v in row] if hasattr(row, "__iter__") else _round(row, nd)
            for row in arr]


# ---------------------------------------------------------------------------
# Funciones de distancia con signo (SDF) para presets
# ---------------------------------------------------------------------------

def _fd_rectangle(p, x1, x2, y1, y2):
    x, y = p[:, 0], p[:, 1]
    return np.maximum(np.maximum(x1 - x, x - x2), np.maximum(y1 - y, y - y2))


def _fd_circle(p, cx, cy, r):
    return np.sqrt((p[:, 0] - cx) ** 2 + (p[:, 1] - cy) ** 2) - r


def _fd_circle_with_hole(p, cx, cy, r_outer, r_inner):
    d_outer = _fd_circle(p, cx, cy, r_outer)
    d_inner = _fd_circle(p, cx, cy, r_inner)
    return np.maximum(d_outer, -d_inner)


def _make_custom_fd(expr_str):
    x, y = sp.symbols("x y")
    expr = sp.sympify(expr_str)
    f = sp.lambdify((x, y), expr, "numpy")

    def fd(p):
        return np.asarray(f(p[:, 0], p[:, 1]), dtype=float)

    return fd


def _build_fd(domain, params):
    if domain == "rectangle":
        x1, x2, y1, y2 = params.get("bbox", [0.0, 1.0, 0.0, 1.0])
        return lambda p: _fd_rectangle(p, x1, x2, y1, y2)
    elif domain == "circle":
        cx, cy = params.get("center", [0.0, 0.0])
        r = params.get("radius", 1.0)
        return lambda p: _fd_circle(p, cx, cy, r)
    elif domain == "circle_with_hole":
        cx, cy = params.get("center", [0.0, 0.0])
        r_outer = params.get("radius_outer", 1.0)
        r_inner = params.get("radius_inner", 0.4)
        return lambda p: _fd_circle_with_hole(p, cx, cy, r_outer, r_inner)
    elif domain == "custom":
        expr_str = params.get("custom_fd")
        if not expr_str:
            raise ValueError("domain='custom' requiere 'custom_fd' (expresion sympy en x,y)")
        return _make_custom_fd(expr_str)
    else:
        raise ValueError(f"domain no reconocido: {domain}")


def _build_fh(params):
    expr_str = params.get("custom_fh")
    if not expr_str:
        return lambda p: np.ones(len(p))
    x, y = sp.symbols("x y")
    expr = sp.sympify(expr_str)
    f = sp.lambdify((x, y), expr, "numpy")

    def fh(p):
        return np.asarray(f(p[:, 0], p[:, 1]), dtype=float)

    return fh


# ---------------------------------------------------------------------------
# Nucleo del algoritmo distmesh2d (Persson & Strang, 2004)
# ---------------------------------------------------------------------------

def _distmesh2d(fd, fh, h0, bbox, max_iter=500, dptol=0.001, ttol=0.1,
                fscale=1.2, deltat=0.2, seed=42):
    rng = np.random.default_rng(seed)
    geps = 0.001 * h0
    deps = math.sqrt(np.finfo(float).eps) * h0
    xmin, xmax, ymin, ymax = bbox

    # 1. Distribucion inicial: grilla triangular equilatera
    xs = np.arange(xmin, xmax + h0, h0)
    ys = np.arange(ymin, ymax + h0 * math.sqrt(3) / 2, h0 * math.sqrt(3) / 2)
    x, y = np.meshgrid(xs, ys)
    x[1::2, :] += h0 / 2.0  # desplaza filas alternas -> triangulos equilateros
    p = np.column_stack([x.ravel(), y.ravel()])

    # 2. Descarta puntos fuera del dominio
    p = p[fd(p) < geps]

    # 3. Rechazo probabilistico segun la funcion de densidad deseada fh
    r0 = 1.0 / fh(p) ** 2
    p = p[rng.random(len(p)) < r0 / r0.max()]

    N = p.shape[0]
    if N < 3:
        raise ValueError("Muy pocos puntos iniciales dentro del dominio; revisa bbox/h0/domain")

    pold = np.full_like(p, np.inf)
    t = None
    bars = None
    converged = False
    iterations_used = 0

    for it in range(max_iter):
        iterations_used = it + 1

        # Retriangula solo si los nodos se movieron lo suficiente
        if np.max(np.sqrt(np.sum((p - pold) ** 2, axis=1))) / h0 > ttol:
            pold = p.copy()
            tri = Delaunay(p)
            t = tri.simplices
            pmid = p[t].sum(axis=1) / 3.0
            t = t[fd(pmid) < -geps]  # descarta triangulos fuera del dominio
            bars_all = np.vstack([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
            bars_sorted = np.sort(bars_all, axis=1)
            bars = np.unique(bars_sorted, axis=0)

        # Fuerzas tipo resorte sobre cada barra
        barvec = p[bars[:, 0]] - p[bars[:, 1]]
        L = np.sqrt(np.sum(barvec ** 2, axis=1))
        L[L < 1e-12] = 1e-12
        hbars = fh((p[bars[:, 0]] + p[bars[:, 1]]) / 2.0)
        L0 = hbars * fscale * math.sqrt(np.sum(L ** 2) / np.sum(hbars ** 2))
        F = np.maximum(L0 - L, 0.0)
        Fvec = (F / L)[:, None] * barvec

        Ftot = np.zeros_like(p)
        np.add.at(Ftot, bars[:, 0], Fvec)
        np.add.at(Ftot, bars[:, 1], -Fvec)

        p += deltat * Ftot

        # Proyecta los puntos que salieron del dominio de vuelta al borde
        d = fd(p)
        ix = d > 0
        if np.any(ix):
            dgradx = (fd(p[ix] + [deps, 0]) - d[ix]) / deps
            dgrady = (fd(p[ix] + [0, deps]) - d[ix]) / deps
            p[ix, 0] -= d[ix] * dgradx
            p[ix, 1] -= d[ix] * dgrady

        # Criterio de convergencia: desplazamiento maximo de nodos interiores
        interior = d < -geps
        if np.any(interior):
            disp = np.sqrt(np.sum((deltat * Ftot[interior]) ** 2, axis=1))
            if disp.max() / h0 < dptol:
                converged = True
                break

    return p, t, converged, iterations_used


def _cleanup_slivers(fd, fh, p, t, h0, fscale=1.2, deltat=0.2, extra_iters=200,
                      angle_threshold_deg=10.0, max_cleanup_rounds=3, seed=42):
    """Post-procesamiento: distmesh (clasico, sin edges de borde restringidos)
    puede quedar atascado en un minimo local con un puñado de triangulos muy
    agudos en el borde, especialmente en dominios anisotropicos o de baja
    curvatura. Detecta esos triangulos, perturba levemente sus nodos, y
    corre relajacion extra acotada. No garantiza eliminar el sliver, pero
    en la practica lo resuelve en la gran mayoria de los casos."""
    rng = np.random.default_rng(seed + 1)
    geps = 0.001 * h0

    for _round_i in range(max_cleanup_rounds):
        angles = _triangle_angles_deg(p, t)
        min_angles = angles.min(axis=1)
        bad = min_angles < angle_threshold_deg
        if not np.any(bad):
            break

        bad_nodes = np.unique(t[bad].ravel())
        p[bad_nodes] += rng.normal(0, h0 * 0.15, size=(len(bad_nodes), 2))

        # clamp de vuelta al dominio tras la perturbacion
        d = fd(p)
        ix = d > 0
        if np.any(ix):
            deps = math.sqrt(np.finfo(float).eps) * h0
            dgradx = (fd(p[ix] + [deps, 0]) - d[ix]) / deps
            dgrady = (fd(p[ix] + [0, deps]) - d[ix]) / deps
            p[ix, 0] -= d[ix] * dgradx
            p[ix, 1] -= d[ix] * dgrady

        pold = np.full_like(p, np.inf)
        bars = None
        for it in range(extra_iters):
            if np.max(np.sqrt(np.sum((p - pold) ** 2, axis=1))) / h0 > 0.1:
                pold = p.copy()
                tri = Delaunay(p)
                t_new = tri.simplices
                pmid = p[t_new].sum(axis=1) / 3.0
                t_new = t_new[fd(pmid) < -geps]
                bars_all = np.vstack([t_new[:, [0, 1]], t_new[:, [1, 2]], t_new[:, [2, 0]]])
                bars = np.unique(np.sort(bars_all, axis=1), axis=0)
                t = t_new

            barvec = p[bars[:, 0]] - p[bars[:, 1]]
            L = np.sqrt(np.sum(barvec ** 2, axis=1))
            L[L < 1e-12] = 1e-12
            hbars = fh((p[bars[:, 0]] + p[bars[:, 1]]) / 2.0)
            L0 = hbars * fscale * math.sqrt(np.sum(L ** 2) / np.sum(hbars ** 2))
            F = np.maximum(L0 - L, 0.0)
            Fvec = (F / L)[:, None] * barvec

            Ftot = np.zeros_like(p)
            np.add.at(Ftot, bars[:, 0], Fvec)
            np.add.at(Ftot, bars[:, 1], -Fvec)
            p += deltat * Ftot

            d = fd(p)
            ix = d > 0
            if np.any(ix):
                deps = math.sqrt(np.finfo(float).eps) * h0
                dgradx = (fd(p[ix] + [deps, 0]) - d[ix]) / deps
                dgrady = (fd(p[ix] + [0, deps]) - d[ix]) / deps
                p[ix, 0] -= d[ix] * dgradx
                p[ix, 1] -= d[ix] * dgrady

        tri = Delaunay(p)
        t = tri.simplices
        pmid = p[t].sum(axis=1) / 3.0
        t = t[fd(pmid) < -geps]

    return p, t


# ---------------------------------------------------------------------------
# Metricas de calidad de malla
# ---------------------------------------------------------------------------

def _triangle_angles_deg(p, t):
    a = np.linalg.norm(p[t[:, 1]] - p[t[:, 2]], axis=1)
    b = np.linalg.norm(p[t[:, 0]] - p[t[:, 2]], axis=1)
    c = np.linalg.norm(p[t[:, 0]] - p[t[:, 1]], axis=1)

    def safe_acos(x):
        return np.degrees(np.arccos(np.clip(x, -1.0, 1.0)))

    A = safe_acos((b ** 2 + c ** 2 - a ** 2) / (2 * b * c))
    B = safe_acos((a ** 2 + c ** 2 - b ** 2) / (2 * a * c))
    C = 180.0 - A - B
    return np.column_stack([A, B, C])


def _triangle_areas(p, t):
    v0 = p[t[:, 1]] - p[t[:, 0]]
    v1 = p[t[:, 2]] - p[t[:, 0]]
    return 0.5 * np.abs(v0[:, 0] * v1[:, 1] - v0[:, 1] * v1[:, 0])


def _triangle_aspect_ratio(p, t):
    """Relacion de aspecto = arista_mas_larga / (2*sqrt(3)*inradio).
    Vale 1.0 para un triangulo equilatero, crece para triangulos degenerados."""
    a = np.linalg.norm(p[t[:, 1]] - p[t[:, 2]], axis=1)
    b = np.linalg.norm(p[t[:, 0]] - p[t[:, 2]], axis=1)
    c = np.linalg.norm(p[t[:, 0]] - p[t[:, 1]], axis=1)
    s = (a + b + c) / 2.0
    area = np.sqrt(np.maximum(s * (s - a) * (s - b) * (s - c), 1e-300))
    inradius = area / s
    longest = np.maximum(np.maximum(a, b), c)
    inradius[inradius < 1e-300] = 1e-300
    return longest / (2.0 * math.sqrt(3) * inradius)


def _mesh_quality_summary(p, t):
    angles = _triangle_angles_deg(p, t)
    areas = _triangle_areas(p, t)
    aspect = _triangle_aspect_ratio(p, t)
    min_angles = angles.min(axis=1)
    return {
        "n_triangles": int(len(t)),
        "min_angle_deg": _round(float(min_angles.min())),
        "mean_min_angle_deg": _round(float(min_angles.mean())),
        "max_angle_deg": _round(float(angles.max())),
        "mean_aspect_ratio": _round(float(aspect.mean())),
        "max_aspect_ratio": _round(float(aspect.max())),
        "total_area": _round(float(areas.sum())),
        "mean_triangle_area": _round(float(areas.mean())),
    }


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------

def _mode_mesh_2d(params):
    domain = params.get("domain", "circle")
    h0 = params.get("h0", 0.1)
    bbox = params.get("bbox")
    max_iter = params.get("max_iter", 500)
    dptol = params.get("dptol", 0.001)
    seed = params.get("seed", 42)

    if bbox is None:
        if domain == "rectangle":
            bbox = params.get("bbox", [0.0, 1.0, 0.0, 1.0])
        elif domain in ("circle", "circle_with_hole"):
            cx, cy = params.get("center", [0.0, 0.0])
            r = params.get("radius", params.get("radius_outer", 1.0))
            bbox = [cx - r, cx + r, cy - r, cy + r]
        else:
            bbox = params.get("bbox", [-1.0, 1.0, -1.0, 1.0])

    fd = _build_fd(domain, params)
    fh = _build_fh(params)

    p, t, converged, iterations_used = _distmesh2d(
        fd, fh, h0, bbox, max_iter=max_iter, dptol=dptol, seed=seed
    )

    quality = _mesh_quality_summary(p, t)
    sliver_cleanup_applied = False

    if quality["min_angle_deg"] < 10.0:
        p, t = _cleanup_slivers(fd, fh, p, t, h0, seed=seed)
        quality = _mesh_quality_summary(p, t)
        sliver_cleanup_applied = True

    quality_warning = None
    if quality["min_angle_deg"] < 5.0:
        quality_warning = (
            "La malla conserva al menos un triangulo muy degenerado "
            f"(angulo minimo {quality['min_angle_deg']}deg) tras la limpieza "
            "automatica. Esto es una limitacion conocida de distmesh en bordes "
            "de baja curvatura o dominios muy anisotropicos. Probar con h0 mas "
            "chico, o revisar la geometria del dominio."
        )
    elif quality["min_angle_deg"] < 15.0:
        quality_warning = (
            f"Angulo minimo bajo ({quality['min_angle_deg']}deg). La malla es "
            "usable pero de calidad marginal en el borde; considerar reducir h0."
        )

    return {
        "mode": "mesh_2d",
        "domain": domain,
        "h0": h0,
        "n_points": int(len(p)),
        "n_triangles": int(len(t)),
        "converged": bool(converged),
        "iterations_used": iterations_used,
        "sliver_cleanup_applied": sliver_cleanup_applied,
        "points": _round_list(p.tolist()),
        "triangles": t.tolist(),
        "quality": quality,
        "quality_warning": quality_warning,
    }


def _mode_mesh_quality(params):
    points = params.get("points")
    triangles = params.get("triangles")
    if points is None or triangles is None:
        raise ValueError("mesh_quality requiere 'points' y 'triangles'")
    p = np.array(points, dtype=float)
    t = np.array(triangles, dtype=int)
    return {"mode": "mesh_quality", **_mesh_quality_summary(p, t)}


def _mode_validate():
    # Caso canonico distmesh: circulo unitario, h0=0.15 (resolucion moderada
    # para mantener el tiempo de ejecucion acotado en un chequeo automatico)
    result = _mode_mesh_2d({"domain": "circle", "center": [0.0, 0.0],
                             "radius": 1.0, "h0": 0.15, "max_iter": 300})

    q = result["quality"]
    p = np.array(result["points"])
    fd = _build_fd("circle", {"center": [0.0, 0.0], "radius": 1.0})
    max_outside = float(fd(p).max())

    checks = {
        "converged": result["converged"],
        "min_angle_above_15deg": q["min_angle_deg"] > 15.0,
        "mean_min_angle_above_25deg": q["mean_min_angle_deg"] > 25.0,
        "max_aspect_ratio_below_5": q["max_aspect_ratio"] < 5.0,
        "all_points_within_domain": max_outside < 1e-3,
    }
    validation_passed = all(checks.values())

    return {
        "mode": "validate",
        "n_points": result["n_points"],
        "n_triangles": result["n_triangles"],
        "iterations_used": result["iterations_used"],
        "quality": q,
        "max_point_outside_domain": _round(max_outside, 8),
        "checks": checks,
        "expected": "malla del circulo unitario converge, angulo minimo > 15deg "
                    "(idealmente cerca de 30deg como en Persson&Strang 2004), "
                    "sin triangulos muy degenerados, todos los puntos dentro del dominio",
        "validation_passed": validation_passed,
    }


def compute_distmesh(mode="validate", **kwargs):
    """
    mode: 'mesh_2d' | 'mesh_quality' | 'validate'

    mesh_2d:
      domain: 'rectangle' | 'circle' | 'circle_with_hole' | 'custom'
      h0: longitud de arista objetivo (float, default 0.1)
      bbox: [xmin,xmax,ymin,ymax], opcional (se infiere del domain si se omite)
      rectangle -> bbox
      circle -> center [cx,cy], radius
      circle_with_hole -> center [cx,cy], radius_outer, radius_inner
      custom -> custom_fd (expresion sympy en x,y, negativa dentro, '^' NO soportado usar '**')
      custom_fh: expresion sympy opcional en x,y para densidad de malla no uniforme
      max_iter, dptol, seed: parametros del solver, opcionales

    mesh_quality:
      points: lista de [x,y]
      triangles: lista de [i,j,k] (indices en points)

    validate: sin parametros, corre el caso canonico (circulo unitario)
    """
    if mode == "mesh_2d":
        return _mode_mesh_2d(kwargs)
    elif mode == "mesh_quality":
        return _mode_mesh_quality(kwargs)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(f"mode no reconocido: {mode}")


DISTMESH_TOOL_SCHEMA = {
    "name": "distmesh_tool",
    "description": (
        "Generacion de malla triangular 2D via el algoritmo distmesh de "
        "Persson & Strang (2004): modela la malla como una celosia de "
        "resortes que busca una longitud de arista objetivo, resolviendo "
        "un equilibrio de fuerzas sobre una triangulacion de Delaunay que "
        "se recalcula al moverse los nodos. mode='mesh_2d' genera la malla "
        "sobre un dominio preset (rectangle, circle, circle_with_hole) o "
        "custom (funcion de distancia con signo via expresion sympy en "
        "x,y). mode='mesh_quality' analiza angulo minimo y relacion de "
        "aspecto de una malla externa (points+triangles). mode='validate' "
        "corre el caso canonico del circulo unitario y chequea convergencia "
        "y calidad."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["mesh_2d", "mesh_quality", "validate"],
                "default": "validate",
            },
            "domain": {
                "type": "string",
                "enum": ["rectangle", "circle", "circle_with_hole", "custom"],
                "default": "circle",
                "description": "mesh_2d.",
            },
            "h0": {
                "type": "number",
                "default": 0.1,
                "description": "Longitud de arista objetivo. mesh_2d.",
            },
            "bbox": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[xmin,xmax,ymin,ymax]. mesh_2d, requerido para domain='rectangle' o 'custom' (opcional, se infiere para circle/circle_with_hole).",
            },
            "center": {
                "type": "array",
                "items": {"type": "number"},
                "default": [0.0, 0.0],
                "description": "[cx,cy]. mesh_2d, domain='circle'/'circle_with_hole'.",
            },
            "radius": {
                "type": "number",
                "default": 1.0,
                "description": "mesh_2d, domain='circle'.",
            },
            "radius_outer": {
                "type": "number",
                "description": "mesh_2d, domain='circle_with_hole'.",
            },
            "radius_inner": {
                "type": "number",
                "description": "mesh_2d, domain='circle_with_hole'.",
            },
            "custom_fd": {
                "type": "string",
                "description": "Expresion sympy en x,y (usar ** no ^), negativa dentro del dominio. mesh_2d, domain='custom'.",
            },
            "custom_fh": {
                "type": "string",
                "description": "Expresion sympy en x,y para densidad de malla no uniforme (mayor valor = malla mas gruesa ahi). Opcional, default uniforme. mesh_2d.",
            },
            "max_iter": {
                "type": "integer",
                "default": 500,
                "description": "mesh_2d.",
            },
            "dptol": {
                "type": "number",
                "default": 0.001,
                "description": "Tolerancia de convergencia (desplazamiento relativo maximo). mesh_2d.",
            },
            "seed": {
                "type": "integer",
                "default": 42,
                "description": "Semilla RNG para la distribucion inicial de puntos. mesh_2d.",
            },
            "points": {
                "type": "array",
                "description": "Lista de [x,y]. mesh_quality.",
            },
            "triangles": {
                "type": "array",
                "description": "Lista de [i,j,k] (indices en points). mesh_quality.",
            },
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    print(json.dumps(compute_distmesh(mode="validate"), indent=2))
