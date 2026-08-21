"""
correlation_dimension_tool.py

Dimension de correlacion (Grassberger-Procaccia, 1983): cuantifica que tan
"complejo" es un atractor -- complementa a chaos_diagnosis_tool (que
responde "es caotico?" via lambda1 de Rosenstein) respondiendo "que tan
compleja es la geometria del atractor?" via D2.

Reusa el embedding de Takens (_embed, _select_tau, _select_m) y las series
de referencia (_lorenz_series) de chaos_diagnosis_tool directamente -- cero
reimplementacion del embedding, mismo criterio de tau/m en ambas tools.

Metodo:
1. Embedding de Takens con (tau, m) auto-seleccionados igual que en
   chaos_diagnosis_tool (AMI para tau, FNN para m), o provistos a mano.
2. Integral de correlacion C(r) = fraccion de pares (i,j) con |i-j| > W
   (ventana de Theiler, evita sesgo por autocorrelacion temporal) tales
   que dist(emb_i, emb_j) < r, para un rango log-espaciado de r.
3. D2 = pendiente de log C(r) vs log r en la region de scaling lineal
   (se descartan los extremos: r muy chico = ruido/pocos pares, r muy
   grande = saturacion en C(r)->1).

Nota de complejidad: O(n^2) en el numero de puntos embebidos, igual que
_false_nearest_neighbors_fraction en chaos_diagnosis_tool -- se aplica el
mismo submuestreo (max_points) por la misma razon.
"""

import math

from chaos_diagnosis_tool import (
    _embed,
    _euclid,
    _select_tau,
    _select_m,
    _normalize,
    _detrend_linear,
    _lorenz_series,
)

CORRELATION_DIMENSION_SCHEMA = {
    "name": "compute_correlation_dimension",
    "description": (
        "Dimension de correlacion de Grassberger-Procaccia (D2) para una serie "
        "temporal 1D observada. Complementa a chaos_diagnosis_tool: esa tool "
        "responde si una serie es caotica (lambda1 de Rosenstein), esta "
        "responde que tan compleja es la geometria del atractor subyacente. "
        "Reusa el mismo embedding de Takens (tau via AMI, m via FNN) que "
        "chaos_diagnosis_tool para consistencia entre ambas tools."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["series", "validate"],
                "default": "series",
            },
            "series": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Serie temporal 1D observada (requerida si mode='series').",
            },
            "dt": {"type": "number", "default": 1.0},
            "detrend": {"type": "boolean", "default": True},
            "tau": {
                "type": "integer",
                "description": "Retardo de embedding. Si se omite, se autoselecciona via AMI (igual que chaos_diagnosis_tool).",
            },
            "m": {
                "type": "integer",
                "description": "Dimension de embedding. Si se omite, se autoselecciona via FNN (igual que chaos_diagnosis_tool).",
            },
            "n_radii": {"type": "integer", "default": 20, "description": "Puntos log-espaciados de r entre r_min y r_max."},
            "theiler_window": {
                "type": "integer",
                "description": "Ventana de exclusion temporal para pares (i,j). Default: m*tau (igual criterio que Rosenstein).",
            },
            "max_points": {"type": "integer", "default": 400, "description": "Submuestreo para mantener el O(n^2) manejable."},
        },
    },
}


def _pairwise_distances(emb, theiler_window):
    """Devuelve la lista de distancias euclideas de todos los pares (i,j)
    con i<j y |i-j| > theiler_window. O(n^2), mismo patron que FNN."""
    n = len(emb)
    dists = []
    for i in range(n):
        for j in range(i + 1, n):
            if j - i <= theiler_window:
                continue
            dists.append(_euclid(emb[i], emb[j]))
    return dists


def _correlation_integral(dists, radii):
    """C(r) para cada r en radii: fraccion de distancias < r."""
    n = len(dists)
    if n == 0:
        return [0.0 for _ in radii]
    sorted_d = sorted(dists)
    counts = []
    for r in radii:
        # cuenta de distancias < r via busqueda en la lista ordenada
        lo, hi = 0, len(sorted_d)
        while lo < hi:
            mid = (lo + hi) // 2
            if sorted_d[mid] < r:
                lo = mid + 1
            else:
                hi = mid
        counts.append(lo / n)
    return counts


def _fit_scaling_slope(log_r, log_c):
    """Ajusta la pendiente en la region de scaling lineal: descarta el
    20% inferior (r chico, pocos pares -> ruido) y el 20% superior
    (r grande, C(r) saturando hacia 1) de los puntos validos, y hace
    minimos cuadrados sobre el resto."""
    pairs = [(lr, lc) for lr, lc in zip(log_r, log_c) if lc is not None and math.isfinite(lc)]
    if len(pairs) < 5:
        return None, None, pairs
    pairs.sort(key=lambda p: p[0])
    n = len(pairs)
    lo_cut = max(1, int(n * 0.2))
    hi_cut = max(lo_cut + 3, n - int(n * 0.2))
    region = pairs[lo_cut:hi_cut] if hi_cut > lo_cut else pairs
    if len(region) < 3:
        region = pairs

    xs = [p[0] for p in region]
    ys = [p[1] for p in region]
    n_r = len(xs)
    mean_x = sum(xs) / n_r
    mean_y = sum(ys) / n_r
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return None, None, region
    slope = num / den
    intercept = mean_y - slope * mean_x
    # R^2 del ajuste, para que el resultado venga con una medida de que tan
    # limpio fue el scaling (util para desconfiar de D2 en series cortas/ruidosas)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else None
    return slope, r_squared, region


def compute_correlation_dimension(
    mode="series",
    series=None,
    dt=1.0,
    detrend=True,
    tau=None,
    m=None,
    n_radii=20,
    theiler_window=None,
    max_points=400,
    **kwargs,
):
    if mode == "validate":
        return _validate_correlation_dimension()

    if not series or len(series) < 50:
        return {"error": f"serie demasiado corta o ausente ({len(series or [])} puntos), se requieren al menos 50."}

    x = list(series)
    if detrend:
        x = _detrend_linear(x)
    x = _normalize(x)

    # submuestreo antes del embedding, igual criterio que _select_m
    xs = x if len(x) <= max_points else x[:: max(1, len(x) // max_points)]

    tau_used = tau
    ami_curve = None
    if tau_used is None:
        tau_used, ami_curve = _select_tau(xs, tau_max=30)

    m_used = m
    fnn_frac = None
    if m_used is None:
        m_used, fnn_frac = _select_m(xs, tau_used, m_max=8)

    emb = _embed(xs, m_used, tau_used)
    if len(emb) < 20:
        return {"error": f"embedding demasiado corto ({len(emb)} puntos) para tau={tau_used}, m={m_used}."}

    if theiler_window is None:
        theiler_window = m_used * tau_used

    dists = _pairwise_distances(emb, theiler_window)
    if not dists:
        return {"error": "ventana de Theiler excluyo todos los pares -- serie muy corta para tau/m elegidos."}

    d_min, d_max = min(d for d in dists if d > 0), max(dists)
    if d_min <= 0 or d_max <= d_min:
        return {"error": "rango de distancias degenerado (serie constante o casi-constante)."}

    log_min, log_max = math.log(d_min), math.log(d_max)
    radii = [math.exp(log_min + (log_max - log_min) * i / (n_radii - 1)) for i in range(n_radii)]
    c_r = _correlation_integral(dists, radii)

    log_r = [math.log(r) for r in radii]
    log_c = [math.log(c) if c > 0 else None for c in c_r]

    slope, r_squared, region = _fit_scaling_slope(log_r, log_c)

    return {
        "mode": "series",
        "tau_used": tau_used,
        "m_used": m_used,
        "n_points_embedded": len(emb),
        "n_pairs_used": len(dists),
        "theiler_window": theiler_window,
        "D2_dimension_correlacion": round(slope, 4) if slope is not None else None,
        "r_squared_ajuste_scaling": round(r_squared, 4) if r_squared is not None else None,
        "n_puntos_region_scaling": len(region),
        "log_log_curve": [{"log_r": round(lr, 4), "log_C": round(lc, 4) if lc is not None else None}
                           for lr, lc in zip(log_r, log_c)],
        "nota": (
            "D2 se estima por minimos cuadrados en el 60% central de la region "
            "log-log (se descartan extremos: r chico = pocos pares/ruido, r grande "
            "= C(r) saturando a 1). r_squared_ajuste_scaling bajo (<0.95) sugiere "
            "desconfiar de D2 -- probablemente la serie es corta o ruidosa para "
            "esta estimacion, no un problema del metodo en si."
        ),
    }


def _validate_correlation_dimension() -> dict:
    """3 checks: 1) Lorenz con params clasicos (sigma=10,rho=28,beta=8/3) via
    _lorenz_series (misma serie de referencia que usa chaos_diagnosis_tool)
    debe dar D2 en el rango [1.7, 2.4] -- el valor de referencia en la
    literatura (Grassberger & Procaccia 1983) es D2~2.05, dejamos margen
    generoso porque el metodo es sensible a n_points/tau/m. 2) Una senoidal
    pura (orbita periodica simple, dimension topologica 1) debe dar D2 bajo
    (<1.5) -- una curva cerrada simple no debe parecer un atractor complejo.
    3) El ajuste de Lorenz debe tener r_squared_ajuste_scaling > 0.9 -- si el
    scaling log-log no es razonablemente lineal, el D2 reportado no es
    confiable y eso mismo seria una falla de la tool."""
    checks = []

    lorenz_x = _lorenz_series(n_steps=6000, dt=0.01)
    r_lorenz = compute_correlation_dimension(mode="series", series=lorenz_x, dt=0.01, max_points=400)
    if "error" in r_lorenz:
        checks.append({"name": "lorenz: sin error", "passed": False, "got": r_lorenz})
    else:
        d2 = r_lorenz["D2_dimension_correlacion"]
        checks.append({
            "name": "lorenz clasico: D2 en [1.7, 2.4] (referencia literatura ~2.05)",
            "passed": bool(d2 is not None and 1.7 <= d2 <= 2.4),
            "got": {"D2": d2},
        })
        r2 = r_lorenz["r_squared_ajuste_scaling"]
        checks.append({
            "name": "lorenz: r_squared_ajuste_scaling > 0.9 (scaling log-log limpio)",
            "passed": bool(r2 is not None and r2 > 0.9),
            "got": {"r_squared": r2},
        })

    n = 2000
    seno = [math.sin(2 * math.pi * i / 50.0) for i in range(n)]
    r_seno = compute_correlation_dimension(mode="series", series=seno, dt=1.0, max_points=400)
    if "error" in r_seno:
        checks.append({"name": "senoidal: sin error", "passed": False, "got": r_seno})
    else:
        d2_seno = r_seno["D2_dimension_correlacion"]
        checks.append({
            "name": "senoidal pura: D2 < 1.5 (orbita periodica simple, no compleja)",
            "passed": bool(d2_seno is not None and d2_seno < 1.5),
            "got": {"D2": d2_seno},
        })

    return {"mode": "validate", "validation_passed": all(c["passed"] for c in checks), "checks": checks}


if __name__ == "__main__":
    import json
    lorenz_x = _lorenz_series(n_steps=6000, dt=0.01)
    print(json.dumps(compute_correlation_dimension(series=lorenz_x, dt=0.01), indent=2, ensure_ascii=False)[:2000])
    print("---VALIDATE---")
    print(json.dumps(_validate_correlation_dimension(), indent=2, ensure_ascii=False))


try:
    from tool_registry import register_tool
    register_tool(
        name="correlation_dimension",
        schema={**CORRELATION_DIMENSION_SCHEMA, "name": "correlation_dimension"},
        handler=lambda args: compute_correlation_dimension(**args),
    )
except ImportError:
    pass
