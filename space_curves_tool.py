"""
space_curves_tool.py

Curvas paramétricas en el espacio: triedro de Frenet-Serret (T,N,B),
curvatura, torsión, longitud de arco y círculo osculador.

Complementa a surface_geometry_tool.py (curvas 1D en vez de superficies 2D)
dentro de la línea de geometría diferencial del roadmap.

Mismo patrón que las otras tools ya wireadas: TOOL_SCHEMA, run(mode, params),
run_self_test() -> {"checks","all_passed","total"}, __main__ con
sys.argv[1]/sys.argv[2], _register() via tool_registry.register_tool(
TOOL_SCHEMA["name"], TOOL_SCHEMA, _handler).
"""

import json
import sys

import numpy as np
import sympy as sp
from scipy.integrate import quad

_T = sp.symbols("t", real=True)
_LOCALS_T = {"t": _T}

TOOL_SCHEMA = {
    "name": "space_curves",
    "description": (
        "Curvas paramétricas r(t) en el espacio: triedro de Frenet-Serret "
        "(tangente, normal, binormal), curvatura, torsión, longitud de arco "
        "y círculo osculador."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "frenet_frame",
                    "curvature_torsion",
                    "arc_length",
                    "osculating_circle",
                    "validate",
                    "self_test",
                ],
            },
            "x": {"type": "string", "description": "x(t)"},
            "y": {"type": "string", "description": "y(t)"},
            "z": {"type": "string", "description": "z(t)"},
            "t0": {"type": "number"},
            "t1": {"type": "number"},
        },
        "required": ["mode"],
        "additionalProperties": True,
    },
}


# ---------------------------------------------------------------------------
# Helpers simbólicos
# ---------------------------------------------------------------------------

def _parse_curve(x_str, y_str, z_str):
    # IMPORTANTE: locals={'t': _T} explícito -- mismo bug que en
    # surface_geometry_tool.py: sin esto sympify crea un Symbol('t')
    # "genérico" que sympy no identifica con _T, y las derivadas dan 0
    # en silencio en vez de fallar.
    r = sp.Matrix([
        sp.sympify(x_str, locals=_LOCALS_T),
        sp.sympify(y_str, locals=_LOCALS_T),
        sp.sympify(z_str, locals=_LOCALS_T),
    ])
    r1 = r.diff(_T)
    r2 = r1.diff(_T)
    r3 = r2.diff(_T)
    return r, r1, r2, r3


def _frenet_exprs(r1, r2, r3):
    cross12 = r1.cross(r2)
    speed = sp.sqrt(sp.simplify(r1.dot(r1)))
    cross_norm = sp.sqrt(sp.simplify(cross12.dot(cross12)))

    T_expr = r1 / speed
    B_expr = cross12 / cross_norm
    N_expr = sp.simplify(B_expr.cross(T_expr))

    kappa_expr = sp.simplify(cross_norm / speed ** 3)
    tau_num = sp.simplify(cross12.dot(r3))
    tau_expr = sp.simplify(tau_num / (cross_norm ** 2))

    return {
        "T": T_expr, "N": N_expr, "B": B_expr,
        "kappa": kappa_expr, "tau": tau_expr, "speed": speed,
    }


def _eval_vec(expr_mat, t0):
    v = np.array([complex(c.subs({_T: t0}).evalf()) for c in expr_mat], dtype=complex)
    return np.real(v).tolist()


def _eval_scalar(expr, t0):
    return float(sp.re(expr.subs({_T: t0}).evalf()))


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------

def _mode_frenet_frame(params):
    r, r1, r2, r3 = _parse_curve(params["x"], params["y"], params["z"])
    fr = _frenet_exprs(r1, r2, r3)
    t0 = params["t0"]
    return {
        "t": t0,
        "point": _eval_vec(r, t0),
        "T": _eval_vec(fr["T"], t0),
        "N": _eval_vec(fr["N"], t0),
        "B": _eval_vec(fr["B"], t0),
        "kappa": _eval_scalar(fr["kappa"], t0),
        "tau": _eval_scalar(fr["tau"], t0),
        "speed": _eval_scalar(fr["speed"], t0),
    }


def _mode_curvature_torsion(params):
    r, r1, r2, r3 = _parse_curve(params["x"], params["y"], params["z"])
    fr = _frenet_exprs(r1, r2, r3)
    t0 = params["t0"]
    return {
        "t": t0,
        "kappa": _eval_scalar(fr["kappa"], t0),
        "tau": _eval_scalar(fr["tau"], t0),
        "kappa_expr": str(fr["kappa"]),
        "tau_expr": str(fr["tau"]),
    }


def _mode_arc_length(params):
    r, r1, r2, r3 = _parse_curve(params["x"], params["y"], params["z"])
    speed_expr = sp.sqrt(sp.simplify(r1.dot(r1)))
    speed_fn = sp.lambdify(_T, speed_expr, "numpy")
    t0, t1 = params["t0"], params["t1"]
    length, err = quad(lambda t: float(np.real(speed_fn(t))), t0, t1)
    return {"t0": t0, "t1": t1, "arc_length": length, "quad_abs_error_estimate": err}


def _mode_osculating_circle(params):
    r, r1, r2, r3 = _parse_curve(params["x"], params["y"], params["z"])
    fr = _frenet_exprs(r1, r2, r3)
    t0 = params["t0"]
    kappa_v = _eval_scalar(fr["kappa"], t0)
    if abs(kappa_v) < 1e-12:
        return {"t": t0, "kappa": kappa_v, "radius": None, "center": None,
                "note": "curvatura ≈0: no hay círculo osculador bien definido (punto de inflexión/recta)"}
    radius = 1.0 / kappa_v
    point = np.array(_eval_vec(r, t0))
    N_vec = np.array(_eval_vec(fr["N"], t0))
    center = (point + radius * N_vec).tolist()
    return {"t": t0, "kappa": kappa_v, "radius": radius, "center": center}


# ---------------------------------------------------------------------------
# validate / self_test
# ---------------------------------------------------------------------------

def run_self_test():
    """Devuelve {"checks": [...], "all_passed": bool, "total": int}."""
    checks = []

    def _sanitize(v):
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

    # --- Hélice circular: a=2, b=0.5 -- curvatura y torsión constantes conocidas ---
    a, b = 2.0, 0.5
    x_str, y_str, z_str = f"{a}*cos(t)", f"{a}*sin(t)", f"{b}*t"
    t0 = 1.3
    ft = _mode_frenet_frame({"x": x_str, "y": y_str, "z": z_str, "t0": t0})
    kappa_expected = a / (a ** 2 + b ** 2)
    tau_expected = b / (a ** 2 + b ** 2)
    check(
        "helix_curvature_torsion_vs_closed_form",
        abs(ft["kappa"] - kappa_expected) < 1e-9 and abs(ft["tau"] - tau_expected) < 1e-9,
        kappa=ft["kappa"], kappa_expected=kappa_expected,
        tau=ft["tau"], tau_expected=tau_expected,
    )

    # --- T,N,B ortonormales y dextrógiros (T x N = B) en el mismo punto ---
    Tv, Nv, Bv = np.array(ft["T"]), np.array(ft["N"]), np.array(ft["B"])
    check(
        "helix_frame_orthonormal_right_handed",
        abs(np.linalg.norm(Tv) - 1) < 1e-8 and abs(np.linalg.norm(Nv) - 1) < 1e-8
        and abs(np.linalg.norm(Bv) - 1) < 1e-8 and abs(Tv.dot(Nv)) < 1e-8
        and np.allclose(np.cross(Tv, Nv), Bv, atol=1e-6),
        T_norm=float(np.linalg.norm(Tv)), N_norm=float(np.linalg.norm(Nv)),
        B_norm=float(np.linalg.norm(Bv)), T_dot_N=float(Tv.dot(Nv)),
    )

    # --- Curva plana (círculo en z=0): torsión debe ser 0 ---
    ct_circle = _mode_curvature_torsion({"x": "3*cos(t)", "y": "3*sin(t)", "z": "0", "t0": 0.9})
    check(
        "planar_circle_zero_torsion",
        abs(ct_circle["tau"]) < 1e-9 and abs(ct_circle["kappa"] - 1.0 / 3.0) < 1e-9,
        kappa=ct_circle["kappa"], tau=ct_circle["tau"],
    )

    # --- Longitud de arco de la hélice vs forma cerrada: L = sqrt(a^2+b^2)*(t1-t0) ---
    al = _mode_arc_length({"x": x_str, "y": y_str, "z": z_str, "t0": 0.0, "t1": 2.0})
    L_expected = (a ** 2 + b ** 2) ** 0.5 * 2.0
    check(
        "helix_arc_length_vs_closed_form",
        abs(al["arc_length"] - L_expected) < 1e-6,
        arc_length=al["arc_length"], expected=L_expected,
    )

    # --- Círculo osculador del círculo plano: radio=3 (=1/kappa), centro=origen ---
    osc = _mode_osculating_circle({"x": "3*cos(t)", "y": "3*sin(t)", "z": "0", "t0": 1.4})
    center = osc["center"]
    check(
        "planar_circle_osculating_circle_matches_itself",
        osc["radius"] is not None and abs(osc["radius"] - 3.0) < 1e-8
        and abs(center[0]) < 1e-6 and abs(center[1]) < 1e-6 and abs(center[2]) < 1e-6,
        radius=osc["radius"], center=center,
    )

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "all_passed": all_passed, "total": len(checks)}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_DISPATCH = {
    "frenet_frame": _mode_frenet_frame,
    "curvature_torsion": _mode_curvature_torsion,
    "arc_length": _mode_arc_length,
    "osculating_circle": _mode_osculating_circle,
}


def run(mode, params=None):
    params = params or {}
    if mode == "validate":
        r = run_self_test()
        return {"checks": r["checks"], "validation_passed": r["all_passed"], "n_checks": r["total"]}
    elif mode == "self_test":
        return run_self_test()
    elif mode in _DISPATCH:
        return _DISPATCH[mode](params)
    else:
        raise ValueError(
            f"modo desconocido: {mode} (usar " + "/".join(list(_DISPATCH) + ["validate", "self_test"]) + ")"
        )


def compute_space_curves(mode, params=None):
    """Alias público, mismo naming convention que las otras tools."""
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
