"""
vector_calculus_tool: calculo vectorial sobre campos discretos (gradiente,
divergencia, rotacional) via diferencias finitas centradas en mallas
regulares 2D o 3D.

Convenciones:
- Un campo escalar se representa como un array N-dimensional (2D o 3D).
- Un campo vectorial se representa como una lista de arrays N-dimensionales,
  uno por componente (ej. [Vx, Vy] en 2D, [Vx, Vy, Vz] en 3D), todos con la
  misma forma.
- El espaciado de la malla (dx, dy, [dz]) se asume uniforme por eje.
- Diferencias finitas centradas de segundo orden en el interior; en los
  bordes se usan diferencias de un solo lado (forward/backward) de primer
  orden, para evitar asumir condiciones de frontera periodicas o de
  reflejo que el usuario no pidio.
"""

import sys
import json

import numpy as np


# ---------------------------------------------------------------------------
# validacion
# ---------------------------------------------------------------------------

def _to_array(field, name="field"):
    arr = np.array(field, dtype=float)
    if arr.ndim not in (2, 3):
        raise ValueError(f"{name} debe ser 2D o 3D, se recibio {arr.ndim}D")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contiene valores no finitos (NaN/inf)")
    return arr


def _validate_spacing(spacing, ndim):
    if spacing is None:
        spacing = [1.0] * ndim
    spacing = list(spacing)
    if len(spacing) != ndim:
        raise ValueError(f"spacing debe tener {ndim} valores (uno por eje), se recibieron {len(spacing)}")
    for s in spacing:
        if s <= 0:
            raise ValueError("todos los valores de spacing deben ser > 0")
    return spacing


def _validate_vector_field(components, name="vector_field"):
    if components is None:
        raise ValueError(f"falta '{name}' en params")
    if not isinstance(components, list) or len(components) < 2:
        raise ValueError(f"{name} debe ser una lista de al menos 2 componentes (arrays)")
    arrays = [_to_array(c, f"{name}[{i}]") for i, c in enumerate(components)]
    ndim = arrays[0].ndim
    shape = arrays[0].shape
    if ndim not in (2, 3):
        raise ValueError(f"{name}: cada componente debe ser 2D o 3D")
    if len(arrays) != ndim:
        raise ValueError(
            f"{name}: numero de componentes ({len(arrays)}) debe coincidir con "
            f"la dimensionalidad de las mallas ({ndim}D)"
        )
    for i, a in enumerate(arrays):
        if a.shape != shape:
            raise ValueError(f"{name}[{i}] tiene forma {a.shape}, esperada {shape} (igual a {name}[0])")
    return arrays, shape, ndim


# ---------------------------------------------------------------------------
# derivadas centradas con borde de un solo lado
# ---------------------------------------------------------------------------

def _partial_derivative(arr, axis, h):
    """Derivada parcial de arr respecto al eje `axis`, paso h.
    Centrada en el interior, forward/backward de primer orden en bordes."""
    n = arr.shape[axis]
    if n < 2:
        raise ValueError(f"el eje {axis} necesita al menos 2 puntos para derivar")
    d = np.zeros_like(arr)

    # interior: diferencia centrada
    sl_c = [slice(None)] * arr.ndim
    sl_f = [slice(None)] * arr.ndim
    sl_b = [slice(None)] * arr.ndim
    sl_c[axis] = slice(1, n - 1)
    sl_f[axis] = slice(2, n)
    sl_b[axis] = slice(0, n - 2)
    d[tuple(sl_c)] = (arr[tuple(sl_f)] - arr[tuple(sl_b)]) / (2 * h)

    # borde inicial: forward
    sl0 = [slice(None)] * arr.ndim
    sl0[axis] = 0
    sl1 = [slice(None)] * arr.ndim
    sl1[axis] = 1
    d[tuple(sl0)] = (arr[tuple(sl1)] - arr[tuple(sl0)]) / h

    # borde final: backward
    slm1 = [slice(None)] * arr.ndim
    slm1[axis] = n - 1
    slm2 = [slice(None)] * arr.ndim
    slm2[axis] = n - 2
    d[tuple(slm1)] = (arr[tuple(slm1)] - arr[tuple(slm2)]) / h

    return d


# ---------------------------------------------------------------------------
# modos
# ---------------------------------------------------------------------------

def gradient(params):
    params = params or {}
    field = _to_array(params.get("field"), "field")
    ndim = field.ndim
    spacing = _validate_spacing(params.get("spacing"), ndim)

    components = [_partial_derivative(field, axis, spacing[axis]) for axis in range(ndim)]

    return {
        "shape": list(field.shape),
        "ndim": ndim,
        "spacing": spacing,
        "gradient": [c.tolist() for c in components],
    }


def divergence(params):
    params = params or {}
    arrays, shape, ndim = _validate_vector_field(params.get("vector_field"))
    spacing = _validate_spacing(params.get("spacing"), ndim)

    div = np.zeros(shape)
    for axis in range(ndim):
        div += _partial_derivative(arrays[axis], axis, spacing[axis])

    return {
        "shape": list(shape),
        "ndim": ndim,
        "spacing": spacing,
        "divergence": div.tolist(),
    }


def curl(params):
    params = params or {}
    arrays, shape, ndim = _validate_vector_field(params.get("vector_field"))
    spacing = _validate_spacing(params.get("spacing"), ndim)

    if ndim == 2:
        # rotacional en 2D es un escalar: dVy/dx - dVx/dy
        Vx, Vy = arrays
        dVy_dx = _partial_derivative(Vy, 0, spacing[0])
        dVx_dy = _partial_derivative(Vx, 1, spacing[1])
        curl_z = dVy_dx - dVx_dy
        return {
            "shape": list(shape),
            "ndim": 2,
            "spacing": spacing,
            "curl": curl_z.tolist(),
            "note": "en 2D el rotacional es un campo escalar (componente z)",
        }
    else:
        # rotacional en 3D es un vector
        Vx, Vy, Vz = arrays
        dVz_dy = _partial_derivative(Vz, 1, spacing[1])
        dVy_dz = _partial_derivative(Vy, 2, spacing[2])
        dVx_dz = _partial_derivative(Vx, 2, spacing[2])
        dVz_dx = _partial_derivative(Vz, 0, spacing[0])
        dVy_dx = _partial_derivative(Vy, 0, spacing[0])
        dVx_dy = _partial_derivative(Vx, 1, spacing[1])

        curl_x = dVz_dy - dVy_dz
        curl_y = dVx_dz - dVz_dx
        curl_z = dVy_dx - dVx_dy

        return {
            "shape": list(shape),
            "ndim": 3,
            "spacing": spacing,
            "curl": [curl_x.tolist(), curl_y.tolist(), curl_z.tolist()],
        }


TOOL_SCHEMA = {
    "name": "vector_calculus_tool",
    "description": (
        "Calculo vectorial sobre campos discretos (gradiente, divergencia, "
        "rotacional) via diferencias finitas centradas en mallas regulares "
        "2D o 3D. Modos: gradient (de un campo escalar), divergence y curl "
        "(de un campo vectorial dado como lista de componentes), self_test."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["gradient", "divergence", "curl", "self_test"]},
            "params": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "array",
                        "description": "campo escalar 2D o 3D (solo para mode=gradient)",
                    },
                    "vector_field": {
                        "type": "array",
                        "description": "lista de componentes [Vx, Vy] o [Vx, Vy, Vz], cada uno malla 2D/3D (para mode=divergence/curl)",
                    },
                    "spacing": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "espaciado de malla por eje, ej [dx, dy] o [dx, dy, dz] (default: 1.0 en cada eje)",
                    },
                },
            },
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------------------
# self_test
# ---------------------------------------------------------------------------

def run_self_test():
    checks = []

    def check(name, cond, detail=""):
        checks.append({"name": name, "passed": bool(cond), "detail": detail})

    # malla 2D: f(x,y) = x^2 + y^2  =>  grad f = (2x, 2y)
    n = 21
    dx = dy = 0.1
    x = np.arange(n) * dx
    y = np.arange(n) * dy
    X, Y = np.meshgrid(x, y, indexing="ij")
    f = X**2 + Y**2

    out = gradient({"field": f.tolist(), "spacing": [dx, dy]})
    gx = np.array(out["gradient"][0])
    gy = np.array(out["gradient"][1])
    expected_gx = 2 * X
    expected_gy = 2 * Y
    # excluir bordes (forward/backward difference, menos preciso)
    interior = (slice(1, -1), slice(1, -1))
    err_gx = np.max(np.abs(gx[interior] - expected_gx[interior]))
    err_gy = np.max(np.abs(gy[interior] - expected_gy[interior]))
    check("gradient: df/dx de f=x^2+y^2 coincide con 2x (interior)", err_gx < 1e-6, f"max err={err_gx:.2e}")
    check("gradient: df/dy de f=x^2+y^2 coincide con 2y (interior)", err_gy < 1e-6, f"max err={err_gy:.2e}")

    # divergencia de campo radial V = (x, y) en 2D => div V = 2 (constante)
    Vx = X.copy()
    Vy = Y.copy()
    out_div = divergence({"vector_field": [Vx.tolist(), Vy.tolist()], "spacing": [dx, dy]})
    div_arr = np.array(out_div["divergence"])
    err_div = np.max(np.abs(div_arr[interior] - 2.0))
    check("divergence: div(x,y) = 2 constante (interior)", err_div < 1e-6, f"max err={err_div:.2e}")

    # rotacional de campo radial (x, y) en 2D debe ser 0 (campo conservativo)
    out_curl = curl({"vector_field": [Vx.tolist(), Vy.tolist()], "spacing": [dx, dy]})
    curl_arr = np.array(out_curl["curl"])
    err_curl = np.max(np.abs(curl_arr[interior]))
    check("curl: rot(x,y) = 0 (campo radial conservativo, interior)", err_curl < 1e-6, f"max err={err_curl:.2e}")

    # rotacional de campo rotacional V = (-y, x) en 2D debe ser 2 (constante)
    Vx_rot = -Y.copy()
    Vy_rot = X.copy()
    out_curl2 = curl({"vector_field": [Vx_rot.tolist(), Vy_rot.tolist()], "spacing": [dx, dy]})
    curl2_arr = np.array(out_curl2["curl"])
    err_curl2 = np.max(np.abs(curl2_arr[interior] - 2.0))
    check("curl: rot(-y,x) = 2 constante (interior)", err_curl2 < 1e-6, f"max err={err_curl2:.2e}")

    # caso 3D: divergencia de V=(x,y,z) debe ser 3
    n3 = 6
    x3 = np.arange(n3) * 0.2
    X3, Y3, Z3 = np.meshgrid(x3, x3, x3, indexing="ij")
    out_div3 = divergence({
        "vector_field": [X3.tolist(), Y3.tolist(), Z3.tolist()],
        "spacing": [0.2, 0.2, 0.2],
    })
    div3_arr = np.array(out_div3["divergence"])
    interior3 = (slice(1, -1), slice(1, -1), slice(1, -1))
    err_div3 = np.max(np.abs(div3_arr[interior3] - 3.0))
    check("divergence 3D: div(x,y,z) = 3 constante (interior)", err_div3 < 1e-6, f"max err={err_div3:.2e}")

    # rotacional 3D de campo uniforme debe ser (0,0,0)
    ones3 = np.ones((n3, n3, n3))
    out_curl3 = curl({
        "vector_field": [ones3.tolist(), ones3.tolist(), ones3.tolist()],
        "spacing": [0.2, 0.2, 0.2],
    })
    curl3_arr = np.array(out_curl3["curl"])
    err_curl3 = np.max(np.abs(curl3_arr))
    check("curl 3D: rot(campo uniforme) = 0", err_curl3 < 1e-9, f"max err={err_curl3:.2e}")

    # shape/dimension mismatch debe levantar error
    try:
        divergence({"vector_field": [f.tolist(), f[:-1].tolist()]})
        check("ValueError con componentes de forma distinta", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con componentes de forma distinta", True, "")

    try:
        divergence({"vector_field": [f.tolist()]})  # solo 1 componente
        check("ValueError con solo 1 componente en vector_field", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con solo 1 componente en vector_field", True, "")

    try:
        gradient({"field": [1, 2, 3]})  # 1D en vez de 2D/3D
        check("ValueError con field 1D", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con field 1D", True, "")

    try:
        run("modo_inexistente", {})
        check("ValueError con modo desconocido en run()", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con modo desconocido en run()", True, "")

    total = len(checks)
    passed = sum(1 for c in checks if c["passed"])
    return {"total": total, "passed": passed, "all_passed": passed == total, "checks": checks}


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

def run(mode, params=None):
    if mode == "gradient":
        return gradient(params or {})
    elif mode == "divergence":
        return divergence(params or {})
    elif mode == "curl":
        return curl(params or {})
    elif mode == "self_test":
        return run_self_test()
    else:
        raise ValueError(f"modo desconocido: {mode} (usar gradient/divergence/curl/self_test)")


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

        tool_registry.register_tool("vector_calculus_tool", TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()
