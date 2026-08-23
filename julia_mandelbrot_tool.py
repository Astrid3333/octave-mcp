"""
julia_mandelbrot_tool.py

Genera conjuntos de Mandelbrot y de Julia por conteo de iteraciones de
escape (escape-time algorithm) para f(z) = z^2 + c sobre el plano
complejo, vectorizado con numpy. Ausente en el resto del repo (ver
notas de sesion 23-ago-2026: unico hueco real de "fractales" tras
confirmar que fractal_dimension_tool.py mide dimension, no genera
Julia/Mandelbrot).

Modes:
- mandelbrot: c varia por pixel (z0=0), devuelve grid de iteraciones
  de escape sobre x_range/y_range.
- julia: c fijo (parametro), z0 varia por pixel, mismo algoritmo.
- validate: casos con resultado analitico conocido (ver _validate).
- self_test: alias de validate para uso desde linea de comandos.
"""
import json
import sys
import numpy as np


def _escape_grid(c_real_grid, c_imag_grid, z0_real, z0_imag, max_iter, escape_radius=2.0):
    """Escape-time vectorizado: cuenta cuantas iteraciones tarda |z| en
    superar escape_radius para f(z) = z^2 + c, con c y z0 dados como
    grids (o escalares que numpy hace broadcast)."""
    C = c_real_grid + 1j * c_imag_grid
    Z = np.full(C.shape, z0_real + 1j * z0_imag, dtype=complex)
    if Z.shape != C.shape:
        Z = np.broadcast_to(Z, C.shape).copy()
    escaped_at = np.full(C.shape, max_iter, dtype=int)
    still_active = np.ones(C.shape, dtype=bool)

    for i in range(max_iter):
        Z[still_active] = Z[still_active] ** 2 + C[still_active]
        newly_escaped = still_active & (np.abs(Z) > escape_radius)
        escaped_at[newly_escaped] = i + 1
        still_active &= ~newly_escaped
        if not still_active.any():
            break

    return escaped_at


def _mode_mandelbrot(params):
    x_range = params.get("x_range", [-2.0, 0.5])
    y_range = params.get("y_range", [-1.25, 1.25])
    resolution = params.get("resolution", 200)
    max_iter = params.get("max_iter", 100)
    escape_radius = params.get("escape_radius", 2.0)

    x = np.linspace(x_range[0], x_range[1], resolution)
    y = np.linspace(y_range[0], y_range[1], resolution)
    X, Y = np.meshgrid(x, y)

    escaped_at = _escape_grid(X, Y, 0.0, 0.0, max_iter, escape_radius)

    return {
        "mode": "mandelbrot",
        "x_range": x_range,
        "y_range": y_range,
        "resolution": resolution,
        "max_iter": max_iter,
        "escaped_at": escaped_at.tolist(),
    }


def _mode_julia(params):
    c_real = params.get("c_real", -0.7)
    c_imag = params.get("c_imag", 0.27)
    x_range = params.get("x_range", [-1.5, 1.5])
    y_range = params.get("y_range", [-1.5, 1.5])
    resolution = params.get("resolution", 200)
    max_iter = params.get("max_iter", 100)
    escape_radius = params.get("escape_radius", 2.0)

    x = np.linspace(x_range[0], x_range[1], resolution)
    y = np.linspace(y_range[0], y_range[1], resolution)
    X, Y = np.meshgrid(x, y)

    # para julia, c es fijo y z0 varia por pixel: se logra pasando c
    # como escalar (broadcast automatico) y z0 como el grid X,Y.
    C = np.full(X.shape, complex(c_real, c_imag))
    Z = X + 1j * Y
    escaped_at = np.full(X.shape, max_iter, dtype=int)
    still_active = np.ones(X.shape, dtype=bool)
    for i in range(max_iter):
        Z[still_active] = Z[still_active] ** 2 + C[still_active]
        newly_escaped = still_active & (np.abs(Z) > escape_radius)
        escaped_at[newly_escaped] = i + 1
        still_active &= ~newly_escaped
        if not still_active.any():
            break

    return {
        "mode": "julia",
        "c_real": c_real,
        "c_imag": c_imag,
        "x_range": x_range,
        "y_range": y_range,
        "resolution": resolution,
        "max_iter": max_iter,
        "escaped_at": escaped_at.tolist(),
    }


def _validate():
    """Casos con comportamiento analitico conocido para f(z) = z^2 + c:

    1) Mandelbrot en c=0: z se queda en 0 para siempre (0^2+0=0), nunca
       escapa -- debe dar escaped_at == max_iter (punto en el conjunto).
    2) Mandelbrot en c=2: z0=0 -> z1=2 (ya en el borde) -> z2=4+2=6,
       escapa en la iteracion 2 -- caso clasico de fuera del conjunto
       (c=2 es el limite derecho conocido del conjunto de Mandelbrot
       sobre el eje real).
    3) Julia c=0, z0=0.5: |z| se achica geometricamente (0.5, 0.25,
       0.125, ...) sin nunca superar 2 -- debe quedarse dentro
       (comportamiento conocido de f(z)=z^2 para |z0|<1).
    4) Julia c=0, z0=2.0: z1 = 4.0, ya supera escape_radius=2 en la
       primera iteracion -- escape inmediato, conocido para |z0|>1.
    """
    max_iter = 50

    r1 = _escape_grid(np.array([0.0]), np.array([0.0]), 0.0, 0.0, max_iter)
    check1 = {
        "name": "mandelbrot_c0_permanece_acotado",
        "esperado": max_iter,
        "obtenido": int(r1[0]),
        "passed": bool(r1[0] == max_iter),
    }

    r2 = _escape_grid(np.array([2.0]), np.array([0.0]), 0.0, 0.0, max_iter)
    check2 = {
        "name": "mandelbrot_c2_escapa_iteracion_2",
        "esperado": 2,
        "obtenido": int(r2[0]),
        "passed": bool(r2[0] == 2),
    }

    r3 = _escape_grid(np.array([0.0]), np.array([0.0]), 0.5, 0.0, max_iter)
    check3 = {
        "name": "julia_c0_z0_05_permanece_acotado",
        "esperado": max_iter,
        "obtenido": int(r3[0]),
        "passed": bool(r3[0] == max_iter),
    }

    r4 = _escape_grid(np.array([0.0]), np.array([0.0]), 2.0, 0.0, max_iter)
    check4 = {
        "name": "julia_c0_z0_2_escapa_iteracion_1",
        "esperado": 1,
        "obtenido": int(r4[0]),
        "passed": bool(r4[0] == 1),
    }

    checks = [check1, check2, check3, check4]
    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def run_self_test():
    return _validate()


def run(mode, params=None):
    params = params or {}
    if mode == "mandelbrot":
        return _mode_mandelbrot(params)
    elif mode == "julia":
        return _mode_julia(params)
    elif mode == "validate":
        return _validate()
    elif mode == "self_test":
        return run_self_test()
    else:
        raise ValueError(
            f"modo desconocido: {mode} "
            "(usar mandelbrot/julia/validate/self_test)"
        )


def compute_julia_mandelbrot(mode, params=None):
    """Alias publico, mismo naming convention que compute_surface_geometry()."""
    return run(mode, params)


TOOL_SCHEMA = {
    "name": "julia_mandelbrot",
    "description": (
        "Genera conjuntos de Mandelbrot y de Julia via escape-time "
        "algorithm para f(z) = z^2 + c sobre el plano complejo."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["mandelbrot", "julia", "validate", "self_test"],
                "default": "mandelbrot",
            },
            "params": {
                "type": "object",
                "properties": {
                    "c_real": {"type": "number"},
                    "c_imag": {"type": "number"},
                    "x_range": {"type": "array", "items": {"type": "number"}},
                    "y_range": {"type": "array", "items": {"type": "number"}},
                    "resolution": {"type": "integer"},
                    "max_iter": {"type": "integer"},
                    "escape_radius": {"type": "number"},
                },
            },
        },
        "required": ["mode"],
    },
}


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
