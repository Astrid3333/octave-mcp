#!/usr/bin/env python3
"""
fractal_dimension_tool.py — Dimension fractal por box-counting.
D = -slope de log(N(eps)) vs log(1/eps), ajuste por minimos cuadrados.
Sin numpy (solo random/math de stdlib), salvo el preset chen_lee_attractor
que integra el sistema via Octave (ode45) para generar la trayectoria del
atractor antes de aplicar box-counting sobre los puntos resultantes.
"""
import subprocess
import tempfile
import os
import math
import random

FRACTAL_DIM_SCHEMA = {
    "name": "compute_fractal_dimension",
    "description": (
        "Calcula la dimension fractal (box-counting) de un conjunto de puntos. "
        "Presets: sierpinski_triangle, koch_curve, cantor_set (autosimilares, "
        "con dimension analitica conocida para validar), chen_lee_attractor "
        "(genera la trayectoria integrando el sistema caotico Chen-Lee en "
        "Octave y mide la dimension fractal del atractor), o custom via "
        "'points' [[x,y,...], ...]."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "preset": {
                "type": "string",
                "enum": ["sierpinski_triangle", "koch_curve", "cantor_set",
                         "chen_lee_attractor", "custom"],
                "default": "sierpinski_triangle",
            },
            "points": {"type": "array", "description": "Solo si preset='custom'"},
            "n_points": {"type": "integer", "default": 60000, "description": "Para presets IFS (sierpinski/cantor)"},
            "order": {"type": "integer", "default": 6, "description": "Para koch_curve (nivel de recursion)"},
            "n_scales": {"type": "integer", "default": 14},
            "eps_min_frac": {"type": "number", "default": 0.001},
            "eps_max_frac": {"type": "number", "default": 0.3},
            "chen_lee_params": {"type": "object", "description": "{'a':5,'b':-10,'c':-3.8} por defecto"},
        },
    },
}


def _box_counting_dimension(points, n_scales=14, eps_min_frac=0.001, eps_max_frac=0.3):
    dim = len(points[0])
    mins = [min(p[d] for p in points) for d in range(dim)]
    maxs = [max(p[d] for p in points) for d in range(dim)]
    span = max(maxs[d] - mins[d] for d in range(dim)) or 1.0
    eps_min = eps_min_frac * span
    eps_max = eps_max_frac * span
    ratio = (eps_max / eps_min) ** (1.0 / (n_scales - 1))
    eps_list = [eps_min * (ratio ** i) for i in range(n_scales)]
    table = []
    for eps in eps_list:
        occupied = set()
        for p in points:
            key = tuple(int((p[d] - mins[d]) // eps) for d in range(dim))
            occupied.add(key)
        table.append({"eps": eps, "n_boxes": len(occupied)})

    n_points_total = len(points)
    usable = [t for t in table
              if t["n_boxes"] >= 20
              and t["n_boxes"] <= 0.3 * n_points_total]
    fit_table = usable if len(usable) >= 4 else table

    xs = [math.log(1.0 / t["eps"]) for t in fit_table]
    ys = [math.log(t["n_boxes"]) for t in fit_table]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    den = sum((xs[i] - mx) ** 2 for i in range(n))
    slope = num / den if den != 0 else float("nan")
    return slope, table

def _gen_sierpinski(n_points, seed=42):
    rng = random.Random(seed)
    verts = [(0.0, 0.0), (1.0, 0.0), (0.5, math.sqrt(3) / 2)]
    p = (0.5, 0.25)
    pts = []
    for _ in range(n_points):
        v = verts[rng.randrange(3)]
        p = ((p[0] + v[0]) / 2, (p[1] + v[1]) / 2)
        pts.append(p)
    return pts[500:]  # descarta transiente


def _gen_cantor(n_points, seed=42):
    rng = random.Random(seed)
    p = 0.5
    pts = []
    for _ in range(n_points):
        p = (p / 3) if rng.random() < 0.5 else (p / 3 + 2 / 3)
        pts.append((p,))
    return pts[500:]


def _gen_koch(order):
    def rec(p1, p2, depth):
        if depth == 0:
            return [p1]
        dx = (p2[0] - p1[0]) / 3
        dy = (p2[1] - p1[1]) / 3
        a = (p1[0] + dx, p1[1] + dy)
        b = (p1[0] + 2 * dx, p1[1] + 2 * dy)
        angle = math.pi / 3
        rdx = dx * math.cos(angle) - dy * math.sin(angle)
        rdy = dx * math.sin(angle) + dy * math.cos(angle)
        peak = (a[0] + rdx, a[1] + rdy)
        pts = []
        pts += rec(p1, a, depth - 1)
        pts += rec(a, peak, depth - 1)
        pts += rec(peak, b, depth - 1)
        pts += rec(b, p2, depth - 1)
        return pts
    pts = rec((0.0, 0.0), (1.0, 0.0), order)
    pts.append((1.0, 0.0))
    return pts


def _gen_chen_lee_attractor(params, timeout=60):
    a = params.get("a", 5.0)
    b = params.get("b", -10.0)
    c = params.get("c", -0.38)
    t_max = params.get("t_max", 200)
    n_steps = params.get("n_steps", 20000)
    transient_frac = params.get("transient_frac", 0.1)
    transient_idx = max(1, int(n_steps * transient_frac))
    octave_code = f"""
a = {a}; b = {b}; c = {c};
f = @(t, s) [a*s(1) - s(2)*s(3); b*s(2) + s(1)*s(3); c*s(3) + s(1)*s(2)/3];
tspan = linspace(0, {t_max}, {n_steps});
[t, S] = ode45(f, tspan, [1; 1; 1]);
S = S({transient_idx}:end, :);  % descarta transiente
printf("%.8e ", S');
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".m", delete=False) as fh:
        fh.write(octave_code)
        script_path = fh.name
    try:
        r = subprocess.run(["octave", "--no-gui", "--no-init-file", script_path],
                            capture_output=True, text=True, timeout=timeout)
    finally:
        os.unlink(script_path)
    if r.returncode != 0:
        return None, r.stderr.strip()
    vals = [float(x) for x in r.stdout.split()]
    pts = [(vals[i], vals[i + 1], vals[i + 2]) for i in range(0, len(vals), 3)]
    return pts, None

def compute_fractal_dimension(preset="sierpinski_triangle", points=None, n_points=60000,
                               order=6, n_scales=14, eps_min_frac=0.001, eps_max_frac=0.3,
                               chen_lee_params=None):
    known_analytic = None
    if preset == "sierpinski_triangle":
        pts = _gen_sierpinski(n_points)
        known_analytic = math.log(3) / math.log(2)
    elif preset == "cantor_set":
        pts = _gen_cantor(n_points)
        known_analytic = math.log(2) / math.log(3)
    elif preset == "koch_curve":
        pts = _gen_koch(order)
        known_analytic = math.log(4) / math.log(3)
    elif preset == "chen_lee_attractor":
        pts, err = _gen_chen_lee_attractor(chen_lee_params or {})
        if pts is None:
            return {"error": "octave failed generando atractor Chen-Lee", "stderr": err}
    elif preset == "custom":
        if not points:
            return {"error": "preset='custom' requiere 'points'"}
        pts = [tuple(p) for p in points]
    else:
        return {"error": f"preset desconocido: {preset}"}

    D, table = _box_counting_dimension(pts, n_scales, eps_min_frac, eps_max_frac)

    result = {
        "preset": preset,
        "n_points_used": len(pts),
        "dimension_estimate": D,
        "box_counting_table": table,
    }
    if known_analytic is not None:
        result["known_analytic_dimension"] = known_analytic
        result["relative_error"] = abs(D - known_analytic) / known_analytic
    return result
