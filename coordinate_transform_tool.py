"""
coordinate_transform_tool.py

Conversion entre sistemas de coordenadas curvilineas y cartesianas:
  - polar <-> cartesiano (2D)
  - cilindricas <-> cartesiano (3D)
  - esfericas <-> cartesiano (3D, convencion fisica: theta = angulo polar
    medido desde el eje z, phi = angulo azimutal en el plano xy desde el eje x)

Soporta puntos individuales o batch (lista de puntos), angulos en radianes
(default) o grados, y calculo opcional del Jacobiano simbolico de la
transformacion via sympy (mismo patron que compute_jacobian en
auto_differentiation_tool.py).

Uso como script:
  python3 coordinate_transform_tool.py self_test
  python3 coordinate_transform_tool.py validate
"""
import json
import math
import sys

try:
    import sympy
except ImportError:  # pragma: no cover
    sympy = None

try:
    from tool_registry import register_tool
except ImportError:  # standalone / entorno de pruebas sin tool_registry
    def register_tool(*args, **kwargs):
        pass


MODES = (
    "polar_to_cartesian",
    "cartesian_to_polar",
    "cylindrical_to_cartesian",
    "cartesian_to_cylindrical",
    "spherical_to_cartesian",
    "cartesian_to_spherical",
)

_TOL = 1e-9


# ---------------------------------------------------------------------------
# Normalizacion de entrada: acepta un punto plano [a, b, ...] o una lista de
# puntos [[a, b], [c, d], ...] y siempre devuelve una lista de puntos.
# ---------------------------------------------------------------------------
def _normalize_points(points):
    if points is None:
        raise ValueError("falta el parametro 'points' (o 'point')")
    if len(points) == 0:
        raise ValueError("'points' esta vacio")
    if isinstance(points[0], (int, float)):
        return [list(points)], True  # un solo punto, was_single=True
    return [list(p) for p in points], False


def _wrap_result(converted, was_single):
    if was_single:
        return converted[0]
    return converted


# ---------------------------------------------------------------------------
# Transformaciones puntuales (escalares -> escalares, sin numpy)
# ---------------------------------------------------------------------------
def _polar_to_cartesian(r, theta):
    return [r * math.cos(theta), r * math.sin(theta)]


def _cartesian_to_polar(x, y):
    return [math.hypot(x, y), math.atan2(y, x)]


def _cylindrical_to_cartesian(rho, phi, z):
    return [rho * math.cos(phi), rho * math.sin(phi), z]


def _cartesian_to_cylindrical(x, y, z):
    return [math.hypot(x, y), math.atan2(y, x), z]


def _spherical_to_cartesian(r, theta, phi):
    return [
        r * math.sin(theta) * math.cos(phi),
        r * math.sin(theta) * math.sin(phi),
        r * math.cos(theta),
    ]


def _cartesian_to_spherical(x, y, z):
    r = math.sqrt(x * x + y * y + z * z)
    theta = math.atan2(math.hypot(x, y), z) if r > 0 else 0.0
    phi = math.atan2(y, x)
    return [r, theta, phi]


_SCALAR_FN = {
    "polar_to_cartesian": _polar_to_cartesian,
    "cartesian_to_polar": _cartesian_to_polar,
    "cylindrical_to_cartesian": _cylindrical_to_cartesian,
    "cartesian_to_cylindrical": _cartesian_to_cylindrical,
    "spherical_to_cartesian": _spherical_to_cartesian,
    "cartesian_to_spherical": _cartesian_to_spherical,
}

_EXPECTED_DIM = {
    "polar_to_cartesian": 2,
    "cartesian_to_polar": 2,
    "cylindrical_to_cartesian": 3,
    "cartesian_to_cylindrical": 3,
    "spherical_to_cartesian": 3,
    "cartesian_to_spherical": 3,
}

_ANGLE_INPUT_IDX = {
    # indices (0-based) de componentes de entrada que son angulos
    "polar_to_cartesian": [1],
    "cartesian_to_polar": [],
    "cylindrical_to_cartesian": [1],
    "cartesian_to_cylindrical": [],
    "spherical_to_cartesian": [1, 2],
    "cartesian_to_spherical": [],
}

_ANGLE_OUTPUT_IDX = {
    "polar_to_cartesian": [],
    "cartesian_to_polar": [1],
    "cylindrical_to_cartesian": [],
    "cartesian_to_cylindrical": [1],
    "spherical_to_cartesian": [],
    "cartesian_to_spherical": [1, 2],
}


# ---------------------------------------------------------------------------
# Jacobiano simbolico de la transformacion "forward" de cada modo
# ---------------------------------------------------------------------------
def _symbolic_jacobian(mode):
    if sympy is None:
        return {"error": "sympy no disponible en este entorno"}

    if mode == "polar_to_cartesian":
        r, theta = sympy.symbols("r theta", real=True)
        exprs = [r * sympy.cos(theta), r * sympy.sin(theta)]
        varlist = [r, theta]
    elif mode == "cartesian_to_polar":
        x, y = sympy.symbols("x y", real=True)
        exprs = [sympy.sqrt(x**2 + y**2), sympy.atan2(y, x)]
        varlist = [x, y]
    elif mode == "cylindrical_to_cartesian":
        rho, phi, z = sympy.symbols("rho phi z", real=True)
        exprs = [rho * sympy.cos(phi), rho * sympy.sin(phi), z]
        varlist = [rho, phi, z]
    elif mode == "cartesian_to_cylindrical":
        x, y, z = sympy.symbols("x y z", real=True)
        exprs = [sympy.sqrt(x**2 + y**2), sympy.atan2(y, x), z]
        varlist = [x, y, z]
    elif mode == "spherical_to_cartesian":
        r, theta, phi = sympy.symbols("r theta phi", real=True)
        exprs = [
            r * sympy.sin(theta) * sympy.cos(phi),
            r * sympy.sin(theta) * sympy.sin(phi),
            r * sympy.cos(theta),
        ]
        varlist = [r, theta, phi]
    elif mode == "cartesian_to_spherical":
        x, y, z = sympy.symbols("x y z", real=True)
        rr = sympy.sqrt(x**2 + y**2 + z**2)
        exprs = [
            rr,
            sympy.atan2(sympy.sqrt(x**2 + y**2), z),
            sympy.atan2(y, x),
        ]
        varlist = [x, y, z]
    else:
        raise ValueError(f"modo desconocido para jacobiano: {mode}")

    J = sympy.Matrix(exprs).jacobian(varlist)
    J_simplified = J.applyfunc(sympy.simplify)
    nested = [[{"sympy": str(J_simplified[i, j])} for j in range(J_simplified.cols)]
              for i in range(J_simplified.rows)]
    det = sympy.simplify(J_simplified.det()) if J_simplified.rows == J_simplified.cols else None

    return {
        "variables": [str(v) for v in varlist],
        "matrix": nested,
        "determinant": str(det) if det is not None else None,
    }


# ---------------------------------------------------------------------------
# Dispatcher principal
# ---------------------------------------------------------------------------
def run(mode, params):
    params = params or {}

    if mode == "validate":
        return _validate()

    if mode not in MODES:
        return {"error": f"modo invalido: {mode!r}. Modos validos: {MODES + ('validate',)}"}

    raw_points = params.get("points", params.get("point"))
    degrees = bool(params.get("degrees", False))
    want_jacobian = bool(params.get("jacobian", False))

    try:
        points, was_single = _normalize_points(raw_points)
    except ValueError as e:
        return {"error": str(e)}

    expected_dim = _EXPECTED_DIM[mode]
    for p in points:
        if len(p) != expected_dim:
            return {
                "error": (
                    f"modo {mode!r} espera puntos de dimension {expected_dim}, "
                    f"se recibio uno de dimension {len(p)}"
                )
            }

    fn = _SCALAR_FN[mode]
    angle_in_idx = _ANGLE_INPUT_IDX[mode]
    angle_out_idx = _ANGLE_OUTPUT_IDX[mode]

    converted = []
    for p in points:
        p_work = list(p)
        if degrees:
            for idx in angle_in_idx:
                p_work[idx] = math.radians(p_work[idx])
        out = fn(*p_work)
        if degrees:
            for idx in angle_out_idx:
                out[idx] = math.degrees(out[idx])
        # asegurar floats planos de Python (nunca numpy)
        out = [float(v) for v in out]
        converted.append(out)

    result = {
        "mode": mode,
        "degrees": degrees,
        "result": _wrap_result(converted, was_single),
    }

    if want_jacobian:
        result["jacobian"] = _symbolic_jacobian(mode)

    return result


# ---------------------------------------------------------------------------
# Self-test / validate
# ---------------------------------------------------------------------------
def _approx_eq(a, b, tol=1e-6):
    return bool(abs(a - b) < tol)


def _run_checks():
    checks = []

    # 1. polar_to_cartesian: r=1, theta=0 -> (1, 0)
    r1 = run("polar_to_cartesian", {"points": [1.0, 0.0]})
    ok = _approx_eq(r1["result"][0], 1.0) and _approx_eq(r1["result"][1], 0.0)
    checks.append({"name": "polar_to_cartesian: r=1,theta=0 -> (1,0)",
                    "passed": bool(ok), "detail": str(r1.get("result"))})

    # 2. polar_to_cartesian: r=1, theta=pi/2 -> (0, 1)
    r2 = run("polar_to_cartesian", {"points": [1.0, math.pi / 2]})
    ok = _approx_eq(r2["result"][0], 0.0) and _approx_eq(r2["result"][1], 1.0)
    checks.append({"name": "polar_to_cartesian: r=1,theta=pi/2 -> (0,1)",
                    "passed": bool(ok), "detail": str(r2.get("result"))})

    # 3. cartesian_to_polar: (1,1) -> r=sqrt(2), theta=pi/4
    r3 = run("cartesian_to_polar", {"points": [1.0, 1.0]})
    ok = _approx_eq(r3["result"][0], math.sqrt(2)) and _approx_eq(r3["result"][1], math.pi / 4)
    checks.append({"name": "cartesian_to_polar: (1,1) -> r=sqrt2,theta=pi/4",
                    "passed": bool(ok), "detail": str(r3.get("result"))})

    # 4. round-trip polar
    orig = [3.7, 1.2]
    fwd = run("polar_to_cartesian", {"points": orig})["result"]
    back = run("cartesian_to_polar", {"points": fwd})["result"]
    ok = _approx_eq(back[0], orig[0]) and _approx_eq(back[1], orig[1])
    checks.append({"name": "round-trip polar: cartesian_to_polar(polar_to_cartesian(p)) == p",
                    "passed": bool(ok), "detail": f"orig={orig} back={back}"})

    # 5. cylindrical_to_cartesian: rho=2, phi=pi/2, z=3 -> (0, 2, 3)
    r5 = run("cylindrical_to_cartesian", {"points": [2.0, math.pi / 2, 3.0]})
    ok = _approx_eq(r5["result"][0], 0.0) and _approx_eq(r5["result"][1], 2.0) and _approx_eq(r5["result"][2], 3.0)
    checks.append({"name": "cylindrical_to_cartesian: rho=2,phi=pi/2,z=3 -> (0,2,3)",
                    "passed": bool(ok), "detail": str(r5.get("result"))})

    # 6. round-trip cilindricas
    orig6 = [1.5, 0.9, -2.0]
    fwd6 = run("cylindrical_to_cartesian", {"points": orig6})["result"]
    back6 = run("cartesian_to_cylindrical", {"points": fwd6})["result"]
    ok = all(_approx_eq(a, b) for a, b in zip(orig6, back6))
    checks.append({"name": "round-trip cilindricas",
                    "passed": bool(ok), "detail": f"orig={orig6} back={back6}"})

    # 7. spherical_to_cartesian: r=1, theta=pi/2, phi=0 -> (1, 0, 0)
    r7 = run("spherical_to_cartesian", {"points": [1.0, math.pi / 2, 0.0]})
    ok = _approx_eq(r7["result"][0], 1.0) and _approx_eq(r7["result"][1], 0.0) and _approx_eq(r7["result"][2], 0.0)
    checks.append({"name": "spherical_to_cartesian: r=1,theta=pi/2,phi=0 -> (1,0,0)",
                    "passed": bool(ok), "detail": str(r7.get("result"))})

    # 8. spherical_to_cartesian: polo norte, r=1, theta=0, phi=0 -> (0,0,1)
    r8 = run("spherical_to_cartesian", {"points": [1.0, 0.0, 0.0]})
    ok = _approx_eq(r8["result"][0], 0.0) and _approx_eq(r8["result"][1], 0.0) and _approx_eq(r8["result"][2], 1.0)
    checks.append({"name": "spherical_to_cartesian: polo norte r=1,theta=0,phi=0 -> (0,0,1)",
                    "passed": bool(ok), "detail": str(r8.get("result"))})

    # 9. round-trip esfericas
    orig9 = [2.2, 1.1, 0.7]
    fwd9 = run("spherical_to_cartesian", {"points": orig9})["result"]
    back9 = run("cartesian_to_spherical", {"points": fwd9})["result"]
    ok = all(_approx_eq(a, b) for a, b in zip(orig9, back9))
    checks.append({"name": "round-trip esfericas",
                    "passed": bool(ok), "detail": f"orig={orig9} back={back9}"})

    # 10. jacobiano polar_to_cartesian: determinante == r
    r10 = run("polar_to_cartesian", {"points": [1.0, 0.3], "jacobian": True})
    det = r10.get("jacobian", {}).get("determinant")
    ok = det == "r"
    checks.append({"name": "jacobiano polar_to_cartesian: determinante simbolico == 'r'",
                    "passed": bool(ok), "detail": f"det={det}"})

    # 11. batch: multiples puntos, longitud preservada, sin degradar a numpy
    batch_pts = [[1.0, 0.0], [2.0, math.pi], [0.5, math.pi / 2]]
    r11 = run("polar_to_cartesian", {"points": batch_pts})
    res = r11["result"]
    ok = (len(res) == 3
          and all(isinstance(v, float) for row in res for v in row)
          and _approx_eq(res[0][0], 1.0) and _approx_eq(res[0][1], 0.0))
    checks.append({"name": "batch: 3 puntos, tipos float planos, primer punto correcto",
                    "passed": bool(ok), "detail": f"len={len(res)} res0={res[0] if res else None}"})

    # 12. grados: cartesian_to_polar con degrees=True
    r12 = run("cartesian_to_polar", {"points": [0.0, 1.0], "degrees": True})
    ok = _approx_eq(r12["result"][1], 90.0)
    checks.append({"name": "cartesian_to_polar con degrees=True: (0,1) -> theta=90",
                    "passed": bool(ok), "detail": str(r12.get("result"))})

    return checks


def self_test():
    checks = _run_checks()
    passed = sum(1 for c in checks if c["passed"])
    return {
        "total": len(checks),
        "passed": passed,
        "all_passed": bool(passed == len(checks)),
        "checks": checks,
    }


def _validate():
    checks = _run_checks()
    return {
        "checks": checks,
        "validation_passed": bool(all(c["passed"] for c in checks)),
        "n_checks": len(checks),
    }


# ---------------------------------------------------------------------------
# Schema y auto-registro
# ---------------------------------------------------------------------------
COORDINATE_TRANSFORM_SCHEMA = {
    "name": "coordinate_transform",
    "description": (
        "Convierte puntos entre sistemas de coordenadas: polar<->cartesiano (2D), "
        "cilindricas<->cartesiano (3D) y esfericas<->cartesiano (3D, convencion fisica). "
        "Soporta puntos individuales o batch, angulos en radianes o grados, y calculo "
        "opcional del Jacobiano simbolico de la transformacion."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": list(MODES) + ["validate"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "points": {
                        "description": "Un punto [a,b(,c)] o una lista de puntos [[a,b],...]",
                    },
                    "degrees": {"type": "boolean", "default": False},
                    "jacobian": {"type": "boolean", "default": False},
                },
            },
        },
        "required": ["mode"],
    },
}

register_tool(
    "coordinate_transform",
    COORDINATE_TRANSFORM_SCHEMA,
    lambda args: run(args.get("mode"), args.get("params")),
)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "self_test":
        print(json.dumps(self_test(), indent=2, ensure_ascii=False))
    elif len(sys.argv) > 1 and sys.argv[1] == "validate":
        print(json.dumps(_validate(), indent=2, ensure_ascii=False))
    else:
        print("Uso: python3 coordinate_transform_tool.py [self_test|validate]")
