"""
vector_field_visualizer: prepara datos de campos vectoriales 2D discretos
para visualizacion (flechas submuestreadas estilo quiver, magnitud,
streamlines por integracion RK4 simple). No dibuja nada; devuelve los
datos ya listos para que Octave (u otra herramienta de graficos) los
grafique con quiver()/streamline().

Convenciones:
- El campo vectorial se representa como [Vx, Vy], dos mallas 2D con la
  misma forma (mismo formato que vector_calculus_tool para consistencia
  entre tools).
- x_range / y_range definen las coordenadas fisicas de la malla (por
  defecto, indices 0..N-1 con espaciado 1.0).
"""

import sys
import json

import numpy as np


# ---------------------------------------------------------------------------
# validacion
# ---------------------------------------------------------------------------

def _validate_vector_field_2d(components, name="vector_field"):
    if components is None:
        raise ValueError(f"falta '{name}' en params")
    if not isinstance(components, list) or len(components) != 2:
        raise ValueError(f"{name} debe ser una lista de exactamente 2 componentes [Vx, Vy] (solo 2D soportado)")
    Vx = np.array(components[0], dtype=float)
    Vy = np.array(components[1], dtype=float)
    if Vx.ndim != 2 or Vy.ndim != 2:
        raise ValueError(f"{name}: cada componente debe ser una malla 2D")
    if Vx.shape != Vy.shape:
        raise ValueError(f"{name}: Vx y Vy deben tener la misma forma, tienen {Vx.shape} y {Vy.shape}")
    if not (np.all(np.isfinite(Vx)) and np.all(np.isfinite(Vy))):
        raise ValueError(f"{name} contiene valores no finitos (NaN/inf)")
    return Vx, Vy


def _build_coords(shape, x_range, y_range):
    nx, ny = shape
    if x_range is None:
        x_range = [0.0, float(nx - 1)]
    if y_range is None:
        y_range = [0.0, float(ny - 1)]
    if len(x_range) != 2 or x_range[1] <= x_range[0]:
        raise ValueError("x_range debe ser [min, max] con max > min")
    if len(y_range) != 2 or y_range[1] <= y_range[0]:
        raise ValueError("y_range debe ser [min, max] con max > min")
    x = np.linspace(x_range[0], x_range[1], nx)
    y = np.linspace(y_range[0], y_range[1], ny)
    return x, y, x_range, y_range


# ---------------------------------------------------------------------------
# modo quiver_data: submuestrea y arma la data para flechas
# ---------------------------------------------------------------------------

def quiver_data(params):
    params = params or {}
    Vx, Vy = _validate_vector_field_2d(params.get("vector_field"))
    nx, ny = Vx.shape
    x, y, x_range, y_range = _build_coords((nx, ny), params.get("x_range"), params.get("y_range"))

    max_arrows_per_axis = int(params.get("max_arrows_per_axis", 20))
    if max_arrows_per_axis < 1:
        raise ValueError("max_arrows_per_axis debe ser >= 1")
    normalize = bool(params.get("normalize", False))

    step_x = max(1, nx // max_arrows_per_axis)
    step_y = max(1, ny // max_arrows_per_axis)

    idx_x = np.arange(0, nx, step_x)
    idx_y = np.arange(0, ny, step_y)

    X_sub, Y_sub = np.meshgrid(x[idx_x], y[idx_y], indexing="ij")
    Vx_sub = Vx[np.ix_(idx_x, idx_y)]
    Vy_sub = Vy[np.ix_(idx_x, idx_y)]
    magnitude = np.sqrt(Vx_sub**2 + Vy_sub**2)

    if normalize:
        safe_mag = np.where(magnitude < 1e-12, 1.0, magnitude)
        Vx_plot = Vx_sub / safe_mag
        Vy_plot = Vy_sub / safe_mag
    else:
        Vx_plot = Vx_sub
        Vy_plot = Vy_sub

    return {
        "n_arrows_x": len(idx_x),
        "n_arrows_y": len(idx_y),
        "x": X_sub.tolist(),
        "y": Y_sub.tolist(),
        "u": Vx_plot.tolist(),
        "v": Vy_plot.tolist(),
        "magnitude": magnitude.tolist(),
        "magnitude_range": [float(magnitude.min()), float(magnitude.max())],
        "normalized": normalize,
        "octave_hint": "quiver(x, y, u, v) grafica las flechas; usar 'magnitude' para colorear",
    }


# ---------------------------------------------------------------------------
# modo streamline: integra una linea de flujo desde un punto semilla
# ---------------------------------------------------------------------------

def _interpolate_field(Vx, Vy, x_coords, y_coords, px, py):
    """Interpolacion bilineal del campo en el punto fisico (px, py)."""
    nx, ny = Vx.shape
    if px < x_coords[0] or px > x_coords[-1] or py < y_coords[0] or py > y_coords[-1]:
        return None  # fuera de dominio

    i = np.searchsorted(x_coords, px) - 1
    j = np.searchsorted(y_coords, py) - 1
    i = min(max(i, 0), nx - 2)
    j = min(max(j, 0), ny - 2)

    x0, x1 = x_coords[i], x_coords[i + 1]
    y0, y1 = y_coords[j], y_coords[j + 1]
    tx = (px - x0) / (x1 - x0) if x1 > x0 else 0.0
    ty = (py - y0) / (y1 - y0) if y1 > y0 else 0.0

    def bilinear(F):
        return (
            F[i, j] * (1 - tx) * (1 - ty)
            + F[i + 1, j] * tx * (1 - ty)
            + F[i, j + 1] * (1 - tx) * ty
            + F[i + 1, j + 1] * tx * ty
        )

    return bilinear(Vx), bilinear(Vy)


def streamline(params):
    params = params or {}
    Vx, Vy = _validate_vector_field_2d(params.get("vector_field"))
    nx, ny = Vx.shape
    x, y, x_range, y_range = _build_coords((nx, ny), params.get("x_range"), params.get("y_range"))

    seed = params.get("seed_point")
    if seed is None:
        raise ValueError("falta 'seed_point' (punto [x, y] fisico donde iniciar la streamline)")
    if len(seed) != 2:
        raise ValueError("seed_point debe tener exactamente 2 componentes [x, y]")

    n_steps = int(params.get("n_steps", 200))
    if n_steps < 1:
        raise ValueError("n_steps debe ser >= 1")
    step_size = float(params.get("step_size", (x_range[1] - x_range[0]) / nx))
    if step_size <= 0:
        raise ValueError("step_size debe ser > 0")
    direction = params.get("direction", "forward")
    if direction not in ("forward", "backward", "both"):
        raise ValueError("direction debe ser forward/backward/both")

    def _unit_field(px, py):
        field_val = _interpolate_field(Vx, Vy, x, y, px, py)
        if field_val is None:
            return None
        vx, vy = field_val
        speed = np.hypot(vx, vy)
        if speed < 1e-12:
            return None
        return vx / speed, vy / speed

    def trace(sign):
        pts = [list(map(float, seed))]
        px, py = float(seed[0]), float(seed[1])
        for _ in range(n_steps):
            # RK4 sobre la direccion unitaria del campo (paso de arco fijo)
            k1 = _unit_field(px, py)
            if k1 is None:
                break
            k2 = _unit_field(px + sign * 0.5 * step_size * k1[0], py + sign * 0.5 * step_size * k1[1])
            if k2 is None:
                break
            k3 = _unit_field(px + sign * 0.5 * step_size * k2[0], py + sign * 0.5 * step_size * k2[1])
            if k3 is None:
                break
            k4 = _unit_field(px + sign * step_size * k3[0], py + sign * step_size * k3[1])
            if k4 is None:
                break
            dx = (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]) / 6.0
            dy = (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]) / 6.0
            px += sign * step_size * dx
            py += sign * step_size * dy
            pts.append([px, py])
        return pts

    if direction == "forward":
        points = trace(1)
    elif direction == "backward":
        points = trace(-1)
    else:
        back_pts = trace(-1)[1:][::-1]
        fwd_pts = trace(1)
        points = back_pts + fwd_pts

    return {
        "seed_point": [float(seed[0]), float(seed[1])],
        "direction": direction,
        "n_points": len(points),
        "points": points,
        "reached_boundary_or_stagnation": len(points) < n_steps,
        "octave_hint": "plot(points_x, points_y) sobre la misma figura que quiver()",
    }


TOOL_SCHEMA = {
    "name": "vector_field_visualizer",
    "description": (
        "Prepara datos de campos vectoriales 2D discretos para "
        "visualizacion. Modos: quiver_data (submuestrea el campo para "
        "flechas estilo quiver, con magnitud y direccion opcionalmente "
        "normalizada), streamline (traza una linea de flujo por "
        "integracion desde un punto semilla), self_test. No dibuja "
        "graficos; devuelve arrays listos para quiver()/plot() en Octave."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["quiver_data", "streamline", "self_test", "validate"]},
            "params": {
                "type": "object",
                "properties": {
                    "vector_field": {
                        "type": "array",
                        "description": "lista [Vx, Vy], cada uno malla 2D de igual forma",
                    },
                    "x_range": {"type": "array", "items": {"type": "number"}, "description": "[x_min, x_max] fisico (default: [0, nx-1])"},
                    "y_range": {"type": "array", "items": {"type": "number"}, "description": "[y_min, y_max] fisico (default: [0, ny-1])"},
                    "max_arrows_per_axis": {"type": "integer", "description": "para quiver_data: maximo de flechas por eje tras submuestreo (default 20)"},
                    "normalize": {"type": "boolean", "description": "para quiver_data: normalizar todas las flechas a longitud unitaria (default false)"},
                    "seed_point": {"type": "array", "items": {"type": "number"}, "description": "para streamline: punto [x, y] fisico de inicio"},
                    "n_steps": {"type": "integer", "description": "para streamline: pasos maximos de integracion (default 200)"},
                    "step_size": {"type": "number", "description": "para streamline: longitud de paso fisico (default: dx de la malla)"},
                    "direction": {"type": "string", "enum": ["forward", "backward", "both"], "description": "para streamline (default forward)"},
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

    n = 40
    x_range = [-2.0, 2.0]
    y_range = [-2.0, 2.0]
    x = np.linspace(*x_range, n)
    y = np.linspace(*y_range, n)
    X, Y = np.meshgrid(x, y, indexing="ij")

    # campo rotacional puro: V = (-y, x), magnitud = r
    Vx_rot = -Y
    Vy_rot = X

    # 1) quiver_data: submuestreo respeta max_arrows_per_axis
    out_q = quiver_data({
        "vector_field": [Vx_rot.tolist(), Vy_rot.tolist()],
        "x_range": x_range, "y_range": y_range,
        "max_arrows_per_axis": 10,
    })
    check("quiver_data: n_arrows respeta el limite pedido",
          out_q["n_arrows_x"] <= 10 and out_q["n_arrows_y"] <= 10,
          f"n_arrows_x={out_q['n_arrows_x']}, n_arrows_y={out_q['n_arrows_y']}")

    # 2) quiver_data: magnitud coincide con r=sqrt(x^2+y^2) en cada punto submuestreado
    xs = np.array(out_q["x"])
    ys = np.array(out_q["y"])
    mag = np.array(out_q["magnitude"])
    expected_mag = np.sqrt(xs**2 + ys**2)
    err_mag = np.max(np.abs(mag - expected_mag))
    check("quiver_data: magnitud coincide con sqrt(x^2+y^2)", err_mag < 1e-9, f"max err={err_mag:.2e}")

    # 3) quiver_data normalizado: todas las magnitudes de u,v deben ser 1 (excepto en el origen)
    out_q_norm = quiver_data({
        "vector_field": [Vx_rot.tolist(), Vy_rot.tolist()],
        "x_range": x_range, "y_range": y_range,
        "max_arrows_per_axis": 10, "normalize": True,
    })
    u = np.array(out_q_norm["u"])
    v = np.array(out_q_norm["v"])
    norm_check = np.sqrt(u**2 + v**2)
    # excluir puntos cercanos al origen donde la normalizacion no aplica (magnitud original ~0)
    orig_mag = np.array(out_q_norm["magnitude"])
    mask = orig_mag > 1e-6
    err_norm = np.max(np.abs(norm_check[mask] - 1.0))
    check("quiver_data: normalize=True produce vectores unitarios", err_norm < 1e-6, f"max err={err_norm:.2e}")

    # 4) streamline en campo rotacional puro desde (1,0) debe formar un circulo de radio 1
    out_s = streamline({
        "vector_field": [Vx_rot.tolist(), Vy_rot.tolist()],
        "x_range": x_range, "y_range": y_range,
        "seed_point": [1.0, 0.0],
        "n_steps": 300,
        "step_size": 0.02,
        "direction": "forward",
    })
    pts = np.array(out_s["points"])
    radii = np.sqrt(pts[:, 0]**2 + pts[:, 1]**2)
    radius_drift = np.max(np.abs(radii - 1.0))
    check("streamline: campo rotacional mantiene radio ~1 (circulo)", radius_drift < 0.05, f"max drift radio={radius_drift:.4f}")

    # 5) streamline en campo uniforme: linea recta
    Vx_uniform = np.ones((n, n))
    Vy_uniform = np.zeros((n, n))
    out_s2 = streamline({
        "vector_field": [Vx_uniform.tolist(), Vy_uniform.tolist()],
        "x_range": x_range, "y_range": y_range,
        "seed_point": [-1.5, 0.5],
        "n_steps": 50,
        "step_size": 0.05,
        "direction": "forward",
    })
    pts2 = np.array(out_s2["points"])
    y_drift = np.max(np.abs(pts2[:, 1] - 0.5))
    check("streamline: campo uniforme (1,0) mantiene y constante", y_drift < 1e-9, f"max drift y={y_drift:.2e}")

    # 6) errores esperados
    try:
        quiver_data({"vector_field": [Vx_rot.tolist()]})  # falta Vy
        check("ValueError con vector_field de 1 componente", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con vector_field de 1 componente", True, "")

    try:
        quiver_data({"vector_field": [Vx_rot.tolist(), Vy_rot[:-1].tolist()]})  # formas distintas
        check("ValueError con Vx/Vy de formas distintas", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con Vx/Vy de formas distintas", True, "")

    try:
        streamline({"vector_field": [Vx_rot.tolist(), Vy_rot.tolist()]})  # falta seed_point
        check("ValueError con streamline sin seed_point", False, "no se levanto excepcion")
    except ValueError:
        check("ValueError con streamline sin seed_point", True, "")

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
    if mode == "validate":
        r = run_self_test()
        return {"checks": r["checks"], "validation_passed": r["all_passed"], "n_checks": r["total"]}
    if mode == "quiver_data":
        return quiver_data(params or {})
    elif mode == "streamline":
        return streamline(params or {})
    elif mode == "self_test":
        return run_self_test()
    else:
        raise ValueError(f"modo desconocido: {mode} (usar quiver_data/streamline/self_test)")


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

        tool_registry.register_tool("vector_field_visualizer", TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()
