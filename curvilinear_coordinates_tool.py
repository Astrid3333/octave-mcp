"""
curvilinear_coordinates_tool.py

Cantidades diferenciales de sistemas de coordenadas curvilíneas:
Jacobiano completo (matriz, no solo determinante), factores de escala
(coeficientes de Lamé) y tensor métrico g_ij, para los presets
polar/cilíndricas/esféricas/parabólicas-cilíndricas o un sistema
custom definido por el usuario vía expresiones.

NO incluye conversión de puntos entre sistemas (polar_to_cartesian,
cartesian_to_polar, etc.) porque eso ya lo cubre coordinate_transform_tool.py
(registrado, 12/12 validate) para los 3 sistemas estándar, batch de
puntos, grados/radianes y determinante del Jacobiano como flag. Este
tool es el complemento: matriz Jacobiana completa (no solo su
determinante), factores de escala y tensor métrico -- nada de eso
estaba cubierto en ningún lado -- más soporte de sistema custom /
parabólico-cilíndrico, que coordinate_transform_tool tampoco cubre.

Cierra el "área 1" (Jacobiano genérico / cantidades diferenciales de
coordenadas curvilíneas) del roadmap de geometría diferencial.

Mismo patrón que space_curves_tool.py / surface_geometry_tool.py:
TOOL_SCHEMA, run(mode, params), run_self_test() -> {"checks",
"all_passed","total"}, __main__ con sys.argv[1]/sys.argv[2],
_register() vía tool_registry.register_tool(TOOL_SCHEMA["name"],
TOOL_SCHEMA, _handler).
"""

import json
import sys

import numpy as np
import sympy as sp

# ---------------------------------------------------------------------------
# Presets: cada uno define coords curvilíneas y su mapeo a cartesianas.
# ---------------------------------------------------------------------------

_r, _theta, _phi, _rho, _z, _sigma, _tau = sp.symbols(
    "r theta phi rho z sigma tau", real=True
)

PRESETS = {
    "polar": {
        "coords": ["r", "theta"],
        "cartesian": ["x", "y"],
        "to_cartesian": [_r * sp.cos(_theta), _r * sp.sin(_theta)],
    },
    "cylindrical": {
        "coords": ["rho", "phi", "z"],
        "cartesian": ["x", "y", "z"],
        "to_cartesian": [_rho * sp.cos(_phi), _rho * sp.sin(_phi), _z],
    },
    "spherical": {
        "coords": ["r", "theta", "phi"],
        "cartesian": ["x", "y", "z"],
        "to_cartesian": [
            _r * sp.sin(_theta) * sp.cos(_phi),
            _r * sp.sin(_theta) * sp.sin(_phi),
            _r * sp.cos(_theta),
        ],
    },
    "parabolic_cylindrical": {
        "coords": ["sigma", "tau", "z"],
        "cartesian": ["x", "y", "z"],
        "to_cartesian": [_sigma * _tau, (_tau**2 - _sigma**2) / 2, _z],
    },
}

_SYMS = {"r": _r, "theta": _theta, "phi": _phi, "rho": _rho, "z": _z, "sigma": _sigma, "tau": _tau}


def _resolve_system(params):
    """Devuelve (coord_names, coord_syms, to_cartesian_exprs) para preset o custom."""
    preset = params.get("preset")
    if preset:
        if preset not in PRESETS:
            raise ValueError(f"preset desconocido: {preset} (usar {'/'.join(PRESETS)})")
        p = PRESETS[preset]
        coord_names = p["coords"]
        coord_syms = [_SYMS[c] for c in coord_names]
        exprs = list(p["to_cartesian"])
        return coord_names, coord_syms, exprs

    coord_names = params.get("coords")
    to_cartesian = params.get("to_cartesian")
    if not coord_names or not to_cartesian:
        raise ValueError(
            "para sistema custom se requiere 'coords' (nombres) y "
            "'to_cartesian' (lista de expresiones string en función de coords)"
        )
    coord_syms = sp.symbols(coord_names, real=True)
    if len(coord_names) == 1:
        coord_syms = [coord_syms]
    else:
        coord_syms = list(coord_syms)
    local_dict = dict(zip(coord_names, coord_syms))
    exprs = [sp.sympify(e, locals=local_dict) for e in to_cartesian]
    return coord_names, coord_syms, exprs


def _jacobian_matrix(coord_syms, exprs):
    return sp.Matrix(exprs).jacobian(sp.Matrix(coord_syms))


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------


def _mode_jacobian(params):
    coord_names, coord_syms, exprs = _resolve_system(params)
    J = _jacobian_matrix(coord_syms, exprs)
    if params.get("simplify", True):
        J = sp.simplify(J)
    det = sp.simplify(J.det())

    out = {
        "coords": coord_names,
        "jacobian": [[str(e) for e in row] for row in J.tolist()],
        "determinant": str(det),
    }

    point = params.get("point")
    if point is not None:
        subs = dict(zip(coord_syms, point))
        J_num = np.array(J.subs(subs)).astype(np.float64)
        det_num = float(sp.N(det.subs(subs)))
        out["jacobian_at_point"] = J_num.tolist()
        out["determinant_at_point"] = det_num
    return out


def _mode_scale_factors(params):
    """Coeficientes de Lamé h_i = |d(x1..xn)/dq_i| (norma de la columna i del Jacobiano)."""
    coord_names, coord_syms, exprs = _resolve_system(params)
    J = _jacobian_matrix(coord_syms, exprs)
    h = []
    for i in range(len(coord_syms)):
        col = J[:, i]
        h_i = sp.simplify(sp.sqrt(sum(c**2 for c in col)))
        h.append(h_i)

    out = {"coords": coord_names, "scale_factors": [str(e) for e in h]}

    point = params.get("point")
    if point is not None:
        subs = dict(zip(coord_syms, point))
        out["scale_factors_at_point"] = [float(sp.N(e.subs(subs))) for e in h]
    return out


def _mode_metric_tensor(params):
    """g_ij = J^T J (sirve para sistemas ortogonales y no ortogonales)."""
    coord_names, coord_syms, exprs = _resolve_system(params)
    J = _jacobian_matrix(coord_syms, exprs)
    g = sp.simplify(J.T * J)

    out = {"coords": coord_names, "metric_tensor": [[str(e) for e in row] for row in g.tolist()]}

    point = params.get("point")
    if point is not None:
        subs = dict(zip(coord_syms, point))
        g_num = np.array(g.subs(subs)).astype(np.float64)
        out["metric_tensor_at_point"] = g_num.tolist()
    return out


def _mode_list_presets(_params):
    return {"presets": list(PRESETS.keys())}


_DISPATCH = {
    "jacobian": _mode_jacobian,
    "scale_factors": _mode_scale_factors,
    "metric_tensor": _mode_metric_tensor,
    "list_presets": _mode_list_presets,
}


TOOL_SCHEMA = {
    "name": "curvilinear_coordinates",
    "description": (
        "Cantidades diferenciales de sistemas de coordenadas curvilíneas "
        "(polares/cilíndricas/esféricas/parabólicas-cilíndricas o sistema "
        "custom): Jacobiano completo de la transformación (matriz, no solo "
        "determinante), factores de escala (coeficientes de Lamé) y tensor "
        "métrico g_ij. Para convertir puntos entre sistemas usar "
        "coordinate_transform_tool."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "jacobian",
                    "scale_factors",
                    "metric_tensor",
                    "list_presets",
                    "validate",
                    "self_test",
                ],
            },
            "params": {
                "type": "object",
                "properties": {
                    "preset": {
                        "type": "string",
                        "enum": list(PRESETS.keys()),
                        "description": "atajo: usa un sistema de coordenadas precargado",
                    },
                    "coords": {
                        "type": "array",
                        "description": "sistema custom: nombres de las coordenadas curvilíneas",
                    },
                    "to_cartesian": {
                        "type": "array",
                        "description": "sistema custom: expresiones (strings) x1..xn en función de coords",
                    },
                    "point": {
                        "type": "array",
                        "description": "punto (en las coords curvilíneas) donde evaluar numéricamente",
                    },
                    "simplify": {"type": "boolean", "default": True},
                },
            },
        },
        "required": ["mode"],
    },
}


def run_self_test():
    checks = []

    # 1) Jacobiano polar: det = r
    j = _mode_jacobian({"preset": "polar"})
    checks.append({"name": "jacobian_polar_det", "passed": j["determinant"] in ("r", "1.0*r")})

    # 2) Jacobiano cilíndrico: det = rho
    j = _mode_jacobian({"preset": "cylindrical"})
    checks.append({"name": "jacobian_cylindrical_det", "passed": j["determinant"].replace(".0*", "*") in ("rho", "1.0*rho")})

    # 3) Jacobiano esférico: det = r**2*sin(theta)  (o equivalente simplificado)
    j = _mode_jacobian({"preset": "spherical", "point": [2.0, np.pi / 3, 0.5]})
    expected = float(2.0**2 * np.sin(np.pi / 3))
    checks.append({
        "name": "jacobian_spherical_det_at_point",
        "passed": bool(abs(j["determinant_at_point"] - expected) < 1e-8),
    })

    # 4) scale factors esféricas: h_r=1, h_theta=r, h_phi=r*sin(theta)
    sf = _mode_scale_factors({"preset": "spherical", "point": [3.0, np.pi / 4, 0.2]})
    h = sf["scale_factors_at_point"]
    checks.append({
        "name": "scale_factors_spherical",
        "passed": bool(
            abs(h[0] - 1.0) < 1e-8
            and abs(h[1] - 3.0) < 1e-8
            and abs(h[2] - 3.0 * float(np.sin(np.pi / 4))) < 1e-8
        ),
    })

    # 5) metric tensor esférico diagonal = [1, r^2, r^2 sin^2(theta)]
    mt = _mode_metric_tensor({"preset": "spherical", "point": [2.0, np.pi / 3, 0.1]})
    g = mt["metric_tensor_at_point"]
    off_diag_ok = all(
        abs(g[i][j]) < 1e-8 for i in range(3) for j in range(3) if i != j
    )
    diag_ok = (
        abs(g[0][0] - 1.0) < 1e-8
        and abs(g[1][1] - 4.0) < 1e-8
        and abs(g[2][2] - 4.0 * float(np.sin(np.pi / 3)) ** 2) < 1e-8
    )
    checks.append({"name": "metric_tensor_spherical_diagonal", "passed": bool(off_diag_ok and diag_ok)})

    # 6) sistema custom: coordenadas "elípticas" simples, jacobiano numérico consistente
    custom = {
        "coords": ["u", "v"],
        "to_cartesian": ["u*v", "(u**2 - v**2)/2"],
        "point": [2.0, 1.0],
    }
    j_custom = _mode_jacobian(custom)
    checks.append({
        "name": "jacobian_custom_system",
        "passed": bool(
            abs(j_custom["jacobian_at_point"][0][0] - 1.0) < 1e-8
            and abs(j_custom["jacobian_at_point"][0][1] - 2.0) < 1e-8
        ),
    })

    # 7) list_presets devuelve los 4 presets esperados
    lp = _mode_list_presets({})
    checks.append({
        "name": "list_presets",
        "passed": set(lp["presets"]) == {"polar", "cylindrical", "spherical", "parabolic_cylindrical"},
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "all_passed": all_passed, "total": len(checks)}


def run(mode, params=None):
    params = params or {}
    if mode in ("validate", "self_test"):
        return run_self_test()
    if mode not in _DISPATCH:
        raise ValueError(
            f"modo desconocido: {mode} (usar " + "/".join(list(_DISPATCH) + ["validate", "self_test"]) + ")"
        )
    return _DISPATCH[mode](params)


def compute_curvilinear_coordinates(mode, params=None):
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
    Auto-registro estilo octave-mcp (patrón self-registrante vía
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
