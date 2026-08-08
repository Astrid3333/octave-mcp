#!/usr/bin/env python3
"""
tensor_calculus_tool.py
Calculo tensorial para geometria diferencial / relatividad general:
simbolos de Christoffel, tensor de Riemann, tensor de Ricci, curvatura
escalar y ecuaciones geodesicas, a partir de un tensor metrico g_{mu nu}.

Dos backends:
  - "symbolic": derivadas exactas via sympy, resultados como expresiones
    simplificadas (validas para cualquier punto de la variedad).
  - "numeric": derivadas por diferencias finitas centradas evaluadas en
    un punto dado, sin simplificacion simbolica - util para chequear el
    resultado simbolico o para metricas sin forma cerrada simple.

Incluye metricas precargadas (sphere_2d, polar_plane, schwarzschild) para
validar contra resultados conocidos de libro (ej: esfera 2D con R=2/a^2,
plano en polares con curvatura nula, Schwarzschild con R_{mu nu}=0 en el
vacio).
"""
import sympy as sp
import numpy as np

PRESETS = {
    "sphere_2d": {
        "coords": ["theta", "phi"],
        "params": ["a"],
        "g": [["a**2", "0"],
              ["0", "a**2*sin(theta)**2"]],
    },
    "polar_plane": {
        "coords": ["r", "theta"],
        "params": [],
        "g": [["1", "0"],
              ["0", "r**2"]],
    },
    "schwarzschild": {
        "coords": ["t", "r", "theta", "phi"],
        "params": ["rs"],
        "g": [["-(1 - rs/r)", "0", "0", "0"],
              ["0", "1/(1 - rs/r)", "0", "0"],
              ["0", "0", "r**2", "0"],
              ["0", "0", "0", "r**2*sin(theta)**2"]],
    },
}


def _build_symbolic_metric(metric_preset=None, custom_metric=None, coords=None, params=None):
    if metric_preset is not None:
        if metric_preset not in PRESETS:
            raise ValueError(f"metric_preset desconocido: {metric_preset}. Opciones: {list(PRESETS)}")
        preset = PRESETS[metric_preset]
        coord_names = preset["coords"]
        param_names = preset["params"]
        g_raw = preset["g"]
    else:
        if custom_metric is None or coords is None:
            raise ValueError("para metrica custom hay que dar custom_metric y coords")
        coord_names = coords
        param_names = params or []
        g_raw = custom_metric

    coord_syms = list(sp.symbols(coord_names))
    param_syms = list(sp.symbols(param_names)) if param_names else []

    local_dict = {name: sym for name, sym in zip(coord_names, coord_syms)}
    local_dict.update({name: sym for name, sym in zip(param_names, param_syms)})

    n = len(coord_names)
    g = sp.zeros(n, n)
    for i in range(n):
        for j in range(n):
            g[i, j] = sp.sympify(g_raw[i][j], locals=local_dict)

    return g, list(coord_syms), list(param_syms), coord_names, param_names


def _christoffel_symbolic(g, coord_syms, simplify=True):
    n = len(coord_syms)
    ginv = g.inv()
    Gamma = [[[sp.Integer(0)] * n for _ in range(n)] for _ in range(n)]
    for lam in range(n):
        for mu in range(n):
            for nu in range(n):
                s = sp.Integer(0)
                for sigma in range(n):
                    term = (sp.diff(g[sigma, nu], coord_syms[mu])
                            + sp.diff(g[sigma, mu], coord_syms[nu])
                            - sp.diff(g[mu, nu], coord_syms[sigma]))
                    s += ginv[lam, sigma] * term
                val = s / 2
                if simplify:
                    val = sp.simplify(val)
                Gamma[lam][mu][nu] = val
    return Gamma


def _riemann_symbolic(g, coord_syms, Gamma, simplify=True):
    n = len(coord_syms)
    R = [[[[sp.Integer(0)] * n for _ in range(n)] for _ in range(n)] for _ in range(n)]
    for rho in range(n):
        for sigma in range(n):
            for mu in range(n):
                for nu in range(n):
                    term = (sp.diff(Gamma[rho][nu][sigma], coord_syms[mu])
                            - sp.diff(Gamma[rho][mu][sigma], coord_syms[nu]))
                    for lam in range(n):
                        term += (Gamma[rho][mu][lam] * Gamma[lam][nu][sigma]
                                 - Gamma[rho][nu][lam] * Gamma[lam][mu][sigma])
                    if simplify:
                        term = sp.simplify(term)
                    R[rho][sigma][mu][nu] = term
    return R


def _ricci_symbolic(Riemann, n):
    Ric = sp.zeros(n, n)
    for mu in range(n):
        for nu in range(n):
            s = sp.Integer(0)
            for rho in range(n):
                s += Riemann[rho][mu][rho][nu]
            Ric[mu, nu] = sp.simplify(s)
    return Ric


def _scalar_curvature_symbolic(g, Ric):
    ginv = g.inv()
    n = g.shape[0]
    s = sp.Integer(0)
    for mu in range(n):
        for nu in range(n):
            s += ginv[mu, nu] * Ric[mu, nu]
    return sp.simplify(s)


def _matrix_to_nested_list(M, n, fmt=str):
    return [[fmt(M[i, j]) for j in range(n)] for i in range(n)]


def _nonzero_entries_3(Gamma, n, tol=None):
    out = []
    for lam in range(n):
        for mu in range(n):
            for nu in range(n):
                val = Gamma[lam][mu][nu]
                is_zero = (val == 0) if tol is None else (abs(val) < tol)
                if not is_zero:
                    out.append({"indices": f"Gamma^{lam}_{mu}{nu}", "value": str(val) if tol is None else round(float(val), 8)})
    return out


def compute_symbolic(mode, metric_preset=None, custom_metric=None, coords=None, params=None, simplify=True):
    g, coord_syms, param_syms, coord_names, param_names = _build_symbolic_metric(
        metric_preset, custom_metric, coords, params)
    n = len(coord_syms)

    out = {
        "backend": "symbolic",
        "mode": mode,
        "coords": coord_names,
        "params": param_names,
        "metric": _matrix_to_nested_list(g, n),
    }

    if mode == "christoffel":
        Gamma = _christoffel_symbolic(g, coord_syms, simplify=simplify)
        out["nonzero_christoffel_symbols"] = _nonzero_entries_3(Gamma, n)
        return out

    Gamma = _christoffel_symbolic(g, coord_syms, simplify=simplify)
    if mode == "riemann":
        Riemann = _riemann_symbolic(g, coord_syms, Gamma, simplify=simplify)
        nz = []
        for rho in range(n):
            for sigma in range(n):
                for mu in range(n):
                    for nu in range(n):
                        val = Riemann[rho][sigma][mu][nu]
                        if val != 0:
                            nz.append({"indices": f"R^{rho}_{{{sigma}{mu}{nu}}}", "value": str(val)})
        out["nonzero_riemann_components"] = nz
        return out

    Riemann = _riemann_symbolic(g, coord_syms, Gamma, simplify=simplify)
    Ric = _ricci_symbolic(Riemann, n)
    if mode == "ricci":
        out["ricci_tensor"] = _matrix_to_nested_list(Ric, n)
        out["ricci_all_zero"] = all(Ric[i, j] == 0 for i in range(n) for j in range(n))
        return out

    if mode == "scalar_curvature":
        R = _scalar_curvature_symbolic(g, Ric)
        out["ricci_tensor"] = _matrix_to_nested_list(Ric, n)
        out["scalar_curvature"] = str(R)
        return out

    if mode == "geodesic_equations":
        xdot = sp.symbols([f"xdot{i}" for i in range(n)])
        eqs = []
        for lam in range(n):
            s = sp.Integer(0)
            for mu in range(n):
                for nu in range(n):
                    if Gamma[lam][mu][nu] != 0:
                        s += Gamma[lam][mu][nu] * xdot[mu] * xdot[nu]
            eqs.append(f"d2({coord_names[lam]})/dtau2 = -({sp.simplify(s)})")
        out["geodesic_equations"] = eqs
        out["note"] = "xdot_i representa d(coord_i)/dtau; ecuacion: d2x^lambda/dtau2 + Gamma^lambda_mu_nu * xdot^mu * xdot^nu = 0"
        return out

    raise ValueError(f"modo desconocido: {mode}")


# ---------- backend numerico (diferencias finitas) ----------

def _lambdify_metric(metric_preset, custom_metric, coords, params, param_values):
    g_sym, coord_syms, param_syms, coord_names, param_names = _build_symbolic_metric(
        metric_preset, custom_metric, coords, params)
    n = len(coord_syms)
    if param_names:
        if param_values is None or len(param_values) != len(param_names):
            raise ValueError(f"faltan valores numericos para params {param_names}")
        subs = {psym: val for psym, val in zip(param_syms, param_values)}
        g_sym = g_sym.subs(subs)
    g_func = sp.lambdify(coord_syms, g_sym, modules="numpy")
    return g_func, n, coord_names


def _g_at(g_func, point, n):
    val = np.array(g_func(*point), dtype=float)
    return val.reshape(n, n)


def _christoffel_numeric(g_func, point, n, h=1e-5):
    ginv = np.linalg.inv(_g_at(g_func, point, n))
    dg = np.zeros((n, n, n))  # dg[k][i][j] = d g_ij / d x^k
    for k in range(n):
        p_plus = list(point); p_plus[k] += h
        p_minus = list(point); p_minus[k] -= h
        dg[k] = (_g_at(g_func, p_plus, n) - _g_at(g_func, p_minus, n)) / (2 * h)

    Gamma = np.zeros((n, n, n))
    for lam in range(n):
        for mu in range(n):
            for nu in range(n):
                s = 0.0
                for sigma in range(n):
                    s += ginv[lam, sigma] * (dg[mu, sigma, nu] + dg[nu, sigma, mu] - dg[sigma, mu, nu])
                Gamma[lam, mu, nu] = s / 2
    return Gamma


def _christoffel_at(g_func, point, n, h):
    return _christoffel_numeric(g_func, point, n, h=h)


def _riemann_numeric(g_func, point, n, h=1e-4):
    dGamma = np.zeros((n, n, n, n))  # dGamma[k][rho][mu][nu] = d Gamma^rho_mu_nu / dx^k
    for k in range(n):
        p_plus = list(point); p_plus[k] += h
        p_minus = list(point); p_minus[k] -= h
        Gp = _christoffel_at(g_func, p_plus, n, h)
        Gm = _christoffel_at(g_func, p_minus, n, h)
        dGamma[k] = (Gp - Gm) / (2 * h)

    Gamma0 = _christoffel_at(g_func, point, n, h)
    Riemann = np.zeros((n, n, n, n))
    for rho in range(n):
        for sigma in range(n):
            for mu in range(n):
                for nu in range(n):
                    val = dGamma[mu, rho, nu, sigma] - dGamma[nu, rho, mu, sigma]
                    for lam in range(n):
                        val += Gamma0[rho, mu, lam] * Gamma0[lam, nu, sigma]
                        val -= Gamma0[rho, nu, lam] * Gamma0[lam, mu, sigma]
                    Riemann[rho, sigma, mu, nu] = val
    return Riemann, Gamma0


def compute_numeric(mode, point, metric_preset=None, custom_metric=None, coords=None,
                     params=None, param_values=None, h=1e-5, tol=1e-6):
    g_func, n, coord_names = _lambdify_metric(metric_preset, custom_metric, coords, params, param_values)
    if len(point) != n:
        raise ValueError(f"point debe tener {n} componentes ({coord_names}), recibido {len(point)}")

    out = {
        "backend": "numeric",
        "mode": mode,
        "coords": coord_names,
        "point": point,
        "metric_at_point": _g_at(g_func, point, n).round(8).tolist(),
        "finite_difference_h": h,
    }

    if mode == "christoffel":
        Gamma = _christoffel_at(g_func, point, n, h)
        out["nonzero_christoffel_symbols"] = _nonzero_entries_3(Gamma.tolist(), n, tol=tol)
        return out

    Riemann, Gamma0 = _riemann_numeric(g_func, point, n, h=max(h, 1e-4))
    if mode == "riemann":
        nz = []
        for rho in range(n):
            for sigma in range(n):
                for mu in range(n):
                    for nu in range(n):
                        val = Riemann[rho, sigma, mu, nu]
                        if abs(val) > tol:
                            nz.append({"indices": f"R^{rho}_{{{sigma}{mu}{nu}}}", "value": round(float(val), 8)})
        out["nonzero_riemann_components"] = nz
        return out

    Ric = np.zeros((n, n))
    for mu in range(n):
        for nu in range(n):
            Ric[mu, nu] = sum(Riemann[rho, mu, rho, nu] for rho in range(n))
    if mode == "ricci":
        out["ricci_tensor"] = Ric.round(8).tolist()
        out["ricci_all_zero"] = bool(np.max(np.abs(Ric)) < tol)
        return out

    if mode == "scalar_curvature":
        ginv = np.linalg.inv(_g_at(g_func, point, n))
        R = float(np.sum(ginv * Ric))
        out["ricci_tensor"] = Ric.round(8).tolist()
        out["scalar_curvature"] = round(R, 8)
        return out

    raise ValueError(f"modo desconocido para backend numeric: {mode} (geodesic_equations solo existe en backend symbolic)")


def compute_tensor_calculus(mode, backend="symbolic", metric_preset=None, custom_metric=None,
                             coords=None, params=None, param_values=None, point=None,
                             simplify=True, h=1e-5, tol=1e-6):
    if backend == "symbolic":
        return compute_symbolic(mode, metric_preset=metric_preset, custom_metric=custom_metric,
                                 coords=coords, params=params, simplify=simplify)
    elif backend == "numeric":
        if point is None:
            raise ValueError("backend numeric requiere 'point' (lista de coordenadas donde evaluar)")
        return compute_numeric(mode, point, metric_preset=metric_preset, custom_metric=custom_metric,
                                coords=coords, params=params, param_values=param_values, h=h, tol=tol)
    else:
        raise ValueError("backend debe ser 'symbolic' o 'numeric'")


TENSOR_CALCULUS_TOOL_SCHEMA = {
    "name": "tensor_calculus",
    "description": (
        "Calculo tensorial para geometria diferencial: simbolos de "
        "Christoffel, tensor de Riemann, tensor de Ricci, curvatura "
        "escalar y ecuaciones geodesicas a partir de una metrica g_mu_nu. "
        "Backend 'symbolic' (sympy, expresiones exactas) o 'numeric' "
        "(diferencias finitas centradas evaluadas en un punto). Incluye "
        "metricas precargadas: sphere_2d, polar_plane, schwarzschild."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["christoffel", "riemann", "ricci", "scalar_curvature", "geodesic_equations"]},
            "backend": {"type": "string", "enum": ["symbolic", "numeric"], "default": "symbolic"},
            "metric_preset": {"type": "string", "enum": list(PRESETS.keys()), "description": "atajo: usa una metrica precargada"},
            "custom_metric": {"type": "array", "description": "matriz n x n de expresiones (strings) en funcion de coords/params, si no se usa metric_preset"},
            "coords": {"type": "array", "description": "nombres de las coordenadas (requerido con custom_metric)"},
            "params": {"type": "array", "description": "nombres de parametros libres en la metrica (ej. 'rs', 'a'), opcional"},
            "param_values": {"type": "array", "description": "backend numeric: valores numericos para params, en el mismo orden"},
            "point": {"type": "array", "description": "backend numeric: punto (lista de floats) donde evaluar, mismo orden que coords"},
            "simplify": {"type": "boolean", "default": True, "description": "backend symbolic: simplificar cada componente (mas lento en Schwarzschild)"},
            "h": {"type": "number", "default": 1e-5, "description": "backend numeric: paso de diferencias finitas"},
            "tol": {"type": "number", "default": 1e-6, "description": "backend numeric: tolerancia para considerar una componente como cero (riemann/ricci acumulan mas ruido que christoffel por ser doble diferencia finita)"},
        },
        "required": ["mode"],
    },
}
