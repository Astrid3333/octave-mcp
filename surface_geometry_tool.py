"""
surface_geometry_tool.py

Área 3 del roadmap de geometría: superficies, primera y segunda forma
fundamental, curvatura (Gaussiana, media, principales) y geodésicas.

Modo dual de entrada, igual que las otras tools del server:
  - "parametric": r(u,v) = (x(u,v), y(u,v), z(u,v)) dado como expresiones
    sympy en string, usando los símbolos u, v.
  - "implicit":   F(x,y,z) = 0 dado como expresión sympy en string, usando
    los símbolos x, y, z.

NOTA DE INTEGRACION: mismo patrón que mycelial_network_tool.py (post-refactor)
y fungal_morphology_tool.py — TOOL_SCHEMA con mode enum, run() dispatcher,
self_test / validate, bloque __main__, _register() al final del archivo.
AJUSTAR el import de tool_registry / firma de _register() si no coincide
exactamente con la convención real del repo (infiero el patrón a partir de
la descripción de otras tools, no tengo el archivo real a la vista).
"""

import json
import sys

import numpy as np
import sympy as sp
from scipy.integrate import solve_ivp

# ---------------------------------------------------------------------------
# TOOL SCHEMA (estilo MCP, mode enum + params por modo)
# ---------------------------------------------------------------------------

TOOL_SCHEMA = {
    "name": "surface_geometry",
    "description": (
        "Geometría diferencial de superficies: primera y segunda forma "
        "fundamental, curvatura Gaussiana/media/principales y geodésicas. "
        "Acepta superficies paramétricas r(u,v) o implícitas F(x,y,z)=0."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "first_fundamental_form",
                    "second_fundamental_form",
                    "curvature",
                    "geodesic",
                    "validate",
                    "self_test",
                ],
            },
            "surface_type": {
                "type": "string",
                "enum": ["parametric", "implicit"],
                "description": "Cómo está definida la superficie de entrada.",
            },
            "x": {"type": "string", "description": "x(u,v), modo parametric"},
            "y": {"type": "string", "description": "y(u,v), modo parametric"},
            "z": {"type": "string", "description": "z(u,v), modo parametric"},
            "F": {"type": "string", "description": "F(x,y,z), modo implicit"},
            "point": {
                "type": "object",
                "description": (
                    "Punto de evaluación. Parametric: {'u':.., 'v':..}. "
                    "Implicit: {'x':.., 'y':.., 'z':..} (debe satisfacer F≈0)."
                ),
            },
            "geodesic_params": {
                "type": "object",
                "description": (
                    "Para mode='geodesic'. Parametric: u0,v0,du0,dv0,t_span,n_points. "
                    "Implicit: x0,y0,z0,vx0,vy0,vz0,t_span,n_points."
                ),
            },
        },
        "required": ["mode"],
    },
}

_U, _V = sp.symbols("u v", real=True)
_X, _Y, _Z = sp.symbols("x y z", real=True)


# ---------------------------------------------------------------------------
# Helpers - superficie paramétrica
# ---------------------------------------------------------------------------

_LOCALS_UV = {"u": _U, "v": _V}
_LOCALS_XYZ = {"x": _X, "y": _Y, "z": _Z}


def _parse_parametric(x_str, y_str, z_str):
    # IMPORTANTE: pasar locals={'u': _U, 'v': _V} explícito. sp.sympify sin
    # locals crea Symbol('u') "genérico" (sin real=True), que sympy NO
    # considera igual a _U pese a tener el mismo nombre -> r.diff(_U) da 0
    # silenciosamente en vez de fallar. Bug sutil, costó una ronda de debug.
    r = sp.Matrix([
        sp.sympify(x_str, locals=_LOCALS_UV),
        sp.sympify(y_str, locals=_LOCALS_UV),
        sp.sympify(z_str, locals=_LOCALS_UV),
    ])
    r_u = r.diff(_U)
    r_v = r.diff(_V)
    r_uu = r_u.diff(_U)
    r_uv = r_u.diff(_V)
    r_vv = r_v.diff(_V)
    return r, r_u, r_v, r_uu, r_uv, r_vv


def _first_fundamental_form_expr(r_u, r_v):
    E = sp.simplify(r_u.dot(r_u))
    F = sp.simplify(r_u.dot(r_v))
    G = sp.simplify(r_v.dot(r_v))
    return E, F, G


def _normal_expr(r_u, r_v):
    cross = r_u.cross(r_v)
    norm = sp.sqrt(sp.simplify(cross.dot(cross)))
    n = cross / norm
    return sp.simplify(n), norm


def _second_fundamental_form_expr(r_uu, r_uv, r_vv, n):
    L = sp.simplify(r_uu.dot(n))
    M = sp.simplify(r_uv.dot(n))
    N = sp.simplify(r_vv.dot(n))
    return L, M, N


def _subs_point_param(expr, u0, v0):
    return complex(expr.subs({_U: u0, _V: v0}).evalf())


def _christoffel_second_kind(E, F, G):
    """Γ^k_{ij} para métrica g = [[E,F],[F,G]] en coords (u,v).
    Devuelve dict {(k,i,j): expr} con k,i,j en {0,1} -> (u,v)."""
    g = sp.Matrix([[E, F], [F, G]])
    # Inversión manual 2x2 (evitar Matrix.inv(): el chequeo de rango de
    # sympy no logra probar sin(v)**2 != 0 simbólicamente y falla espurio).
    det = sp.simplify(E * G - F ** 2)
    g_inv = sp.Matrix([[G, -F], [-F, E]]) / det
    coords = [_U, _V]
    Gamma = {}
    for k in range(2):
        for i in range(2):
            for j in range(2):
                s = 0
                for l in range(2):
                    s += g_inv[k, l] * (
                        sp.diff(g[i, l], coords[j])
                        + sp.diff(g[j, l], coords[i])
                        - sp.diff(g[i, j], coords[l])
                    )
                Gamma[(k, i, j)] = sp.simplify(s / 2)
    return Gamma


# ---------------------------------------------------------------------------
# Helpers - superficie implícita (fórmulas de Goldman para curvatura)
# ---------------------------------------------------------------------------

def _implicit_curvature_exprs(F_expr):
    grad = sp.Matrix([sp.diff(F_expr, v) for v in (_X, _Y, _Z)])
    H = sp.hessian(F_expr, (_X, _Y, _Z))
    grad_norm2 = sp.simplify(grad.dot(grad))
    # adj(H) = cofactor matrix (para la fórmula de curvatura Gaussiana)
    adjH = H.adjugate()
    K_num = sp.simplify((grad.T * adjH * grad)[0, 0])
    K = sp.simplify(K_num / grad_norm2 ** 2)

    # Curvatura media (fórmula de Goldman)
    Fx, Fy, Fz = grad[0], grad[1], grad[2]
    Fxx, Fyy, Fzz = H[0, 0], H[1, 1], H[2, 2]
    Fxy, Fxz, Fyz = H[0, 1], H[0, 2], H[1, 2]
    H_num = (
        Fx ** 2 * (Fyy + Fzz) + Fy ** 2 * (Fxx + Fzz) + Fz ** 2 * (Fxx + Fyy)
        - 2 * (Fx * Fy * Fxy + Fx * Fz * Fxz + Fy * Fz * Fyz)
    )
    H_mean = sp.simplify(H_num / (2 * grad_norm2 ** sp.Rational(3, 2)))
    return K, H_mean, grad, grad_norm2


def _implicit_project_acceleration(F_expr):
    """Devuelve función numérica accel(pos, vel) que proyecta la aceleración
    sobre el plano tangente para integrar geodésicas por el método de
    restricción: r'' = -(v^T Hess(F) v / |grad F|^2) grad F.
    """
    grad_expr = sp.Matrix([sp.diff(F_expr, v) for v in (_X, _Y, _Z)])
    Hess_expr = sp.hessian(F_expr, (_X, _Y, _Z))
    grad_fn = sp.lambdify((_X, _Y, _Z), grad_expr, "numpy")
    hess_fn = sp.lambdify((_X, _Y, _Z), Hess_expr, "numpy")
    F_fn = sp.lambdify((_X, _Y, _Z), F_expr, "numpy")

    def accel(pos, vel):
        g = np.array(grad_fn(*pos), dtype=float).reshape(3)
        Hm = np.array(hess_fn(*pos), dtype=float).reshape(3, 3)
        gnorm2 = g.dot(g)
        if gnorm2 < 1e-14:
            return np.zeros(3)
        lam = (vel @ Hm @ vel) / gnorm2
        return -lam * g

    return accel, F_fn


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------

def _mode_first_fundamental_form(params):
    stype = params["surface_type"]
    if stype != "parametric":
        raise ValueError("first_fundamental_form solo aplica a surface_type='parametric'")
    r, r_u, r_v, *_ = _parse_parametric(params["x"], params["y"], params["z"])
    E, F, G = _first_fundamental_form_expr(r_u, r_v)
    pt = params.get("point", {})
    result = {
        "E": str(E), "F": str(F), "G": str(G),
        "area_element": str(sp.sqrt(sp.simplify(E * G - F ** 2))),
    }
    if "u" in pt and "v" in pt:
        u0, v0 = pt["u"], pt["v"]
        result["evaluated_at"] = {"u": u0, "v": v0}
        result["E_value"] = float(E.subs({_U: u0, _V: v0}).evalf())
        result["F_value"] = float(F.subs({_U: u0, _V: v0}).evalf())
        result["G_value"] = float(G.subs({_U: u0, _V: v0}).evalf())
    return result


def _mode_second_fundamental_form(params):
    stype = params["surface_type"]
    if stype != "parametric":
        raise ValueError("second_fundamental_form solo aplica a surface_type='parametric'")
    r, r_u, r_v, r_uu, r_uv, r_vv = _parse_parametric(params["x"], params["y"], params["z"])
    n, _ = _normal_expr(r_u, r_v)
    L, M, N = _second_fundamental_form_expr(r_uu, r_uv, r_vv, n)
    result = {"L": str(L), "M": str(M), "N": str(N)}
    pt = params.get("point", {})
    if "u" in pt and "v" in pt:
        u0, v0 = pt["u"], pt["v"]
        result["evaluated_at"] = {"u": u0, "v": v0}
        result["L_value"] = float(L.subs({_U: u0, _V: v0}).evalf())
        result["M_value"] = float(M.subs({_U: u0, _V: v0}).evalf())
        result["N_value"] = float(N.subs({_U: u0, _V: v0}).evalf())
    return result


def _mode_curvature(params):
    stype = params["surface_type"]
    pt = params.get("point", {})
    if stype == "parametric":
        r, r_u, r_v, r_uu, r_uv, r_vv = _parse_parametric(params["x"], params["y"], params["z"])
        E, F, G = _first_fundamental_form_expr(r_u, r_v)
        n, _ = _normal_expr(r_u, r_v)
        L, M, N = _second_fundamental_form_expr(r_uu, r_uv, r_vv, n)
        denom = sp.simplify(E * G - F ** 2)
        K = sp.simplify((L * N - M ** 2) / denom)
        H = sp.simplify((E * N + G * L - 2 * F * M) / (2 * denom))
        result = {"K": str(K), "H": str(H)}
        if "u" in pt and "v" in pt:
            u0, v0 = pt["u"], pt["v"]
            Kv = float(K.subs({_U: u0, _V: v0}).evalf())
            Hv = float(H.subs({_U: u0, _V: v0}).evalf())
            disc = Hv ** 2 - Kv
            disc = max(disc, 0.0)
            k1 = Hv + disc ** 0.5
            k2 = Hv - disc ** 0.5
            result.update({
                "evaluated_at": {"u": u0, "v": v0},
                "K_value": Kv, "H_value": Hv,
                "principal_curvatures": [k1, k2],
            })
        return result
    elif stype == "implicit":
        F_expr = sp.sympify(params["F"], locals=_LOCALS_XYZ)
        K, Hm, grad, gnorm2 = _implicit_curvature_exprs(F_expr)
        result = {"K": str(K), "H": str(Hm)}
        if all(c in pt for c in ("x", "y", "z")):
            subsmap = {_X: pt["x"], _Y: pt["y"], _Z: pt["z"]}
            Kv = float(K.subs(subsmap).evalf())
            Hv = float(Hm.subs(subsmap).evalf())
            disc = max(Hv ** 2 - Kv, 0.0)
            k1 = Hv + disc ** 0.5
            k2 = Hv - disc ** 0.5
            result.update({
                "evaluated_at": pt, "K_value": Kv, "H_value": Hv,
                "principal_curvatures": [k1, k2],
            })
        return result
    else:
        raise ValueError(f"surface_type desconocido: {stype}")


def _mode_geodesic(params):
    stype = params["surface_type"]
    gp = params["geodesic_params"]
    t_span = tuple(gp.get("t_span", (0.0, 1.0)))
    n_points = int(gp.get("n_points", 50))
    t_eval = np.linspace(t_span[0], t_span[1], n_points)

    if stype == "parametric":
        r, r_u, r_v, *_ = _parse_parametric(params["x"], params["y"], params["z"])
        E, F, G = _first_fundamental_form_expr(r_u, r_v)
        Gamma = _christoffel_second_kind(E, F, G)
        gamma_fns = {k: sp.lambdify((_U, _V), expr, "numpy") for k, expr in Gamma.items()}
        r_fn = sp.lambdify((_U, _V), r, "numpy")

        def rhs(t, state):
            u, v, du, dv = state
            g = {(0, 0): du * du, (0, 1): du * dv, (1, 0): dv * du, (1, 1): dv * dv}
            d2u = -sum(gamma_fns[(0, i, j)](u, v) * g[(i, j)] for i in range(2) for j in range(2))
            d2v = -sum(gamma_fns[(1, i, j)](u, v) * g[(i, j)] for i in range(2) for j in range(2))
            return [du, dv, d2u, d2v]

        state0 = [gp["u0"], gp["v0"], gp["du0"], gp["dv0"]]
        sol = solve_ivp(rhs, t_span, state0, t_eval=t_eval, rtol=1e-9, atol=1e-11)
        path_uv = list(zip(sol.y[0].tolist(), sol.y[1].tolist()))
        path_xyz = [np.array(r_fn(u, v), dtype=float).reshape(3).tolist() for u, v in path_uv]
        return {"t": t_eval.tolist(), "path_uv": path_uv, "path_xyz": path_xyz, "success": bool(sol.success)}

    elif stype == "implicit":
        F_expr = sp.sympify(params["F"], locals=_LOCALS_XYZ)
        accel, F_fn = _implicit_project_acceleration(F_expr)
        state0 = [gp["x0"], gp["y0"], gp["z0"], gp["vx0"], gp["vy0"], gp["vz0"]]
        f0 = float(F_fn(*state0[:3]))
        if abs(f0) > 1e-6:
            raise ValueError(f"Punto inicial no está sobre la superficie: F={f0:.3e} (esperado ≈0)")

        def rhs(t, state):
            pos = np.array(state[:3])
            vel = np.array(state[3:])
            a = accel(pos, vel)
            return [*vel, *a]

        sol = solve_ivp(rhs, t_span, state0, t_eval=t_eval, rtol=1e-9, atol=1e-11)
        path_xyz = list(zip(sol.y[0].tolist(), sol.y[1].tolist(), sol.y[2].tolist()))
        f_residual = [float(F_fn(*p)) for p in path_xyz]
        return {
            "t": t_eval.tolist(), "path_xyz": path_xyz,
            "max_abs_F_residual": max(abs(f) for f in f_residual),
            "success": bool(sol.success),
        }
    else:
        raise ValueError(f"surface_type desconocido: {stype}")


# ---------------------------------------------------------------------------
# Validate / self_test
# ---------------------------------------------------------------------------

def run_self_test():
    """Devuelve {"checks": [...], "all_passed": bool, "total": int} —
    mismo shape que fungal_morphology_tool.py / mycelial_network_tool.py."""
    checks = []

    def _sanitize(v):
        """Cast recursivo de tipos numpy (bool_, float64, ndarray) a nativos
        de Python -- json.dumps no serializa numpy.bool_/float64 directo."""
        if isinstance(v, (np.bool_, bool)):
            return bool(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, np.ndarray):
            return v.tolist()
        if isinstance(v, dict):
            return {k: _sanitize(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [_sanitize(x) for x in v]
        return v

    def check(name, passed, **extra):
        entry = {"name": name, "passed": bool(passed)}
        entry.update({k: _sanitize(v) for k, v in extra.items()})
        checks.append(entry)

    R = 2.0

    # --- Esfera paramétrica: E,F,G y K,H conocidos analíticamente ---
    # Usar coeficiente racional exacto (Rational(2)) en vez de "2.0": sympy
    # falla al invertir matrices simbólicas con coeficientes float (Matrix
    # det==0 espurio en el método de inversión por defecto).
    x = "2*cos(u)*sin(v)"
    y = "2*sin(u)*sin(v)"
    z = "2*cos(v)"
    r, r_u, r_v, r_uu, r_uv, r_vv = _parse_parametric(x, y, z)
    E, F, G = _first_fundamental_form_expr(r_u, r_v)
    u0, v0 = 0.7, 1.1
    E_val = float(E.subs({_U: u0, _V: v0}).evalf())
    F_val = float(F.subs({_U: u0, _V: v0}).evalf())
    G_val = float(G.subs({_U: u0, _V: v0}).evalf())
    E_expected = R ** 2 * np.sin(v0) ** 2
    G_expected = R ** 2
    check(
        "sphere_first_fundamental_form_vs_analytic",
        abs(E_val - E_expected) < 1e-8 and abs(F_val) < 1e-8 and abs(G_val - G_expected) < 1e-8,
        E_error=abs(E_val - E_expected), F_value=F_val, G_error=abs(G_val - G_expected),
    )

    n, _ = _normal_expr(r_u, r_v)
    L, M, N = _second_fundamental_form_expr(r_uu, r_uv, r_vv, n)
    denom = E * G - F ** 2
    K_expr = sp.simplify((L * N - M ** 2) / denom)
    H_expr = sp.simplify((E * N + G * L - 2 * F * M) / (2 * denom))
    K_val = float(K_expr.subs({_U: u0, _V: v0}).evalf())
    H_val = float(H_expr.subs({_U: u0, _V: v0}).evalf())
    check(
        "sphere_gaussian_mean_curvature_vs_1_over_R2",
        abs(abs(K_val) - 1.0 / R ** 2) < 1e-6 and abs(abs(H_val) - 1.0 / R) < 1e-6,
        K_value=K_val, K_expected=1.0 / R ** 2, H_value=H_val, H_expected=1.0 / R,
    )

    # --- Esfera implícita: fórmulas de Goldman vs 1/R2, 1/R ---
    F_impl = _X ** 2 + _Y ** 2 + _Z ** 2 - R ** 2
    Kimp, Himp, _, _ = _implicit_curvature_exprs(F_impl)
    px, py, pz = 1.0, 1.0, np.sqrt(R ** 2 - 2.0)
    subsmap = {_X: px, _Y: py, _Z: pz}
    Kimp_val = float(Kimp.subs(subsmap).evalf())
    Himp_val = float(Himp.subs(subsmap).evalf())
    check(
        "implicit_sphere_curvature_vs_analytic",
        abs(abs(Kimp_val) - 1.0 / R ** 2) < 1e-6 and abs(abs(Himp_val) - 1.0 / R) < 1e-6,
        K_value=Kimp_val, K_expected=1.0 / R ** 2, H_value=Himp_val, H_expected=1.0 / R,
    )

    # --- Geodésica en esfera paramétrica (meridiano: círculo máximo por v) ---
    # du/dt = 0, dv/dt = const es geodésica exacta en esta parametrización.
    # v0=0.5 (lejos de los polos v=0,pi: la parametrización esférica tiene
    # una singularidad de coordenadas ahí, 1/tan(v) diverge y solve_ivp
    # se atasca adaptando el paso en vez de fallar limpio).
    res = _mode_geodesic({
        "surface_type": "parametric", "x": x, "y": y, "z": z,
        "geodesic_params": {"u0": 0.3, "v0": 0.5, "du0": 0.0, "dv0": 1.0,
                             "t_span": [0.0, 1.0], "n_points": 30},
    })
    u_path = [p[0] for p in res["path_uv"]]
    check(
        "sphere_meridian_geodesic_u_constant",
        max(abs(u - 0.3) for u in u_path) < 1e-6 and res["success"],
        max_u_drift=max(abs(u - 0.3) for u in u_path),
    )

    # --- Geodésica en esfera implícita (gran círculo, velocidad tangente) ---
    res_i = _mode_geodesic({
        "surface_type": "implicit", "F": f"x**2+y**2+z**2-{R**2}",
        "geodesic_params": {"x0": R, "y0": 0.0, "z0": 0.0,
                             "vx0": 0.0, "vy0": 1.0, "vz0": 0.0,
                             "t_span": [0.0, 1.0], "n_points": 30},
    })
    check(
        "implicit_sphere_geodesic_stays_on_surface",
        res_i["max_abs_F_residual"] < 1e-4 and res_i["success"],
        max_abs_F_residual=res_i["max_abs_F_residual"],
    )

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "all_passed": all_passed, "total": len(checks)}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def run(mode, params=None):
    params = params or {}
    if mode == "first_fundamental_form":
        return _mode_first_fundamental_form(params)
    elif mode == "second_fundamental_form":
        return _mode_second_fundamental_form(params)
    elif mode == "curvature":
        return _mode_curvature(params)
    elif mode == "geodesic":
        return _mode_geodesic(params)
    elif mode == "validate":
        r = run_self_test()
        return {"checks": r["checks"], "validation_passed": r["all_passed"], "n_checks": r["total"]}
    elif mode == "self_test":
        return run_self_test()
    else:
        raise ValueError(
            f"modo desconocido: {mode} "
            "(usar first_fundamental_form/second_fundamental_form/curvature/geodesic/validate/self_test)"
        )


def compute_surface_geometry(mode, params=None):
    """Alias público, mismo naming convention que compute_mycelial_network()."""
    return run(mode, params)


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
