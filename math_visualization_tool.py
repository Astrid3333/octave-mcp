#!/usr/bin/env python3
"""
math_visualization_tool.py
Genera graficos (PNG en base64) para funciones, retratos de fase de ODEs,
diagramas de bifurcacion y campos vectoriales/gradiente.

Modes:
  - function_plot     : grafico 1D de f(x) sobre un dominio (sympy expr)
  - phase_portrait     : trayectoria(s) 2D/3D de un sistema ODE (presets o custom)
  - bifurcation_render  : recibe puntos ya calculados (de compute_bifurcation_diagram)
                          y los renderiza como scatter r vs x
  - vector_field       : campo vectorial 2D de un gradiente o sistema (x,y) -> (u,v)

No requiere GUI (usa backend 'Agg'). Salida: dict con 'image_base64' (PNG) y metadata.
Corre standalone: python3 math_visualization_tool.py
"""
import io
import base64
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import sympy as sp
from scipy.integrate import solve_ivp


MATH_VISUALIZATION_TOOL_SCHEMA = {
    "name": "math_visualization",
    "description": (
        "Genera visualizaciones (PNG base64) de funciones, retratos de fase de "
        "sistemas ODE, diagramas de bifurcacion y campos vectoriales/gradiente."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["function_plot", "phase_portrait", "bifurcation_render", "vector_field", "validate"],
            },
            "function_expr": {"type": "string", "description": "Expresion sympy en x (mode=function_plot)"},
            "domain": {"type": "array", "items": {"type": "number"}, "description": "[a,b] (mode=function_plot)"},
            "system": {"type": "string", "enum": ["lorenz", "rossler", "van_der_pol", "custom"]},
            "custom_equations": {"type": "string", "description": "Ecuaciones separadas por ';' usando y[0],y[1],..."},
            "custom_params": {"type": "object"},
            "y0": {"type": "array", "items": {"type": "number"}},
            "tspan": {"type": "array", "items": {"type": "number"}},
            "projection": {"type": "string", "enum": ["2d", "3d"], "default": "2d"},
            "r_values": {"type": "array", "items": {"type": "number"}, "description": "mode=bifurcation_render"},
            "x_values": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}, "description": "mode=bifurcation_render, puntos del atractor por cada r"},
            "vector_expr_u": {"type": "string", "description": "componente u(x,y) (mode=vector_field)"},
            "vector_expr_v": {"type": "string", "description": "componente v(x,y) (mode=vector_field)"},
            "xy_domain": {"type": "array", "items": {"type": "number"}, "description": "[xmin,xmax,ymin,ymax] (mode=vector_field)"},
            "title": {"type": "string"},
        },
        "required": ["mode"],
    },
}

_PRESET_SYSTEMS = {
    "lorenz": {
        "eqs": ["10*(y[1]-y[0])", "y[0]*(28-y[2])-y[1]", "y[0]*y[1]-8/3*y[2]"],
        "dim": 3,
        "default_y0": [1.0, 1.0, 1.0],
        "default_tspan": [0, 40],
    },
    "rossler": {
        "eqs": ["-(y[1]+y[2])", "y[0]+0.2*y[1]", "0.2+y[2]*(y[0]-5.7)"],
        "dim": 3,
        "default_y0": [1.0, 1.0, 1.0],
        "default_tspan": [0, 100],
    },
    "van_der_pol": {
        "eqs": ["y[1]", "1.0*(1-y[0]**2)*y[1]-y[0]"],
        "dim": 2,
        "default_y0": [2.0, 0.0],
        "default_tspan": [0, 30],
    },
}


def _fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def _function_plot(args):
    expr_str = args["function_expr"]
    a, b = args.get("domain", [-5, 5])
    x = sp.symbols("x")
    expr = sp.sympify(expr_str)
    f = sp.lambdify(x, expr, "numpy")

    xs = np.linspace(a, b, 800)
    with np.errstate(all="ignore"):
        ys = f(xs)
    ys = np.asarray(ys, dtype=float)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(xs, ys, linewidth=1.8)
    ax.axhline(0, color="gray", linewidth=0.6)
    ax.axvline(0, color="gray", linewidth=0.6)
    ax.set_xlabel("x")
    ax.set_ylabel(f"f(x) = {expr_str}")
    ax.set_title(args.get("title") or f"f(x) = {expr_str}")
    ax.grid(alpha=0.3)

    return {
        "mode": "function_plot",
        "image_base64": _fig_to_base64(fig),
        "domain": [a, b],
        "y_min": float(np.nanmin(ys)),
        "y_max": float(np.nanmax(ys)),
    }


def _build_rhs(system, custom_equations, custom_params):
    if system == "custom":
        eqs = [e.strip() for e in custom_equations.split(";") if e.strip()]
    else:
        eqs = _PRESET_SYSTEMS[system]["eqs"]

    params = custom_params or {}

    def rhs(t, y):
        env = {"y": y, "t": t, "np": np}
        env.update(params)
        return [eval(e, {"__builtins__": {}}, env) for e in eqs]

    dim = len(eqs)
    return rhs, dim


def _phase_portrait(args):
    system = args.get("system", "lorenz")
    projection = args.get("projection", "2d")

    if system == "custom":
        custom_equations = args["custom_equations"]
        rhs, dim = _build_rhs("custom", custom_equations, args.get("custom_params"))
        y0 = args.get("y0", [1.0] * dim)
        tspan = args.get("tspan", [0, 40])
    else:
        preset = _PRESET_SYSTEMS[system]
        rhs, dim = _build_rhs(system, None, args.get("custom_params"))
        y0 = args.get("y0", preset["default_y0"])
        tspan = args.get("tspan", preset["default_tspan"])

    t_eval = np.linspace(tspan[0], tspan[1], 6000)
    sol = solve_ivp(rhs, tspan, y0, t_eval=t_eval, rtol=1e-8, atol=1e-9)

    if dim >= 3 and projection == "3d":
        fig = plt.figure(figsize=(6.5, 6))
        ax = fig.add_subplot(111, projection="3d")
        ax.plot(sol.y[0], sol.y[1], sol.y[2], linewidth=0.6)
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.set_zlabel("z")
    else:
        fig, ax = plt.subplots(figsize=(6.5, 6))
        ax.plot(sol.y[0], sol.y[1], linewidth=0.6)
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.set_aspect("auto")

    ax.set_title(args.get("title") or f"Retrato de fase: {system}")

    return {
        "mode": "phase_portrait",
        "system": system,
        "image_base64": _fig_to_base64(fig),
        "n_points": int(sol.y.shape[1]),
        "tspan": tspan,
        "y0": y0,
    }


def _bifurcation_render(args):
    r_values = args["r_values"]
    x_values = args["x_values"]

    rs_flat, xs_flat = [], []
    for r, xs in zip(r_values, x_values):
        rs_flat.extend([r] * len(xs))
        xs_flat.extend(xs)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(rs_flat, xs_flat, ",", color="black", markersize=0.5, alpha=0.6)
    ax.set_xlabel("r")
    ax.set_ylabel("x (atractor)")
    ax.set_title(args.get("title") or "Diagrama de bifurcacion")
    ax.grid(alpha=0.2)

    return {
        "mode": "bifurcation_render",
        "image_base64": _fig_to_base64(fig),
        "n_r_values": len(r_values),
        "n_points_total": len(rs_flat),
    }


def _vector_field(args):
    x, y = sp.symbols("x y")
    u_expr = sp.sympify(args["vector_expr_u"])
    v_expr = sp.sympify(args["vector_expr_v"])
    u_f = sp.lambdify((x, y), u_expr, "numpy")
    v_f = sp.lambdify((x, y), v_expr, "numpy")

    xmin, xmax, ymin, ymax = args.get("xy_domain", [-3, 3, -3, 3])
    xs = np.linspace(xmin, xmax, 22)
    ys = np.linspace(ymin, ymax, 22)
    X, Y = np.meshgrid(xs, ys)
    with np.errstate(all="ignore"):
        U = np.asarray(u_f(X, Y), dtype=float) * np.ones_like(X)
        V = np.asarray(v_f(X, Y), dtype=float) * np.ones_like(Y)

    mag = np.sqrt(U**2 + V**2)
    mag_safe = np.where(mag == 0, 1, mag)

    fig, ax = plt.subplots(figsize=(6.5, 6))
    ax.quiver(X, Y, U / mag_safe, V / mag_safe, mag, cmap="viridis")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_title(args.get("title") or f"Campo vectorial: ({args['vector_expr_u']}, {args['vector_expr_v']})")

    return {
        "mode": "vector_field",
        "image_base64": _fig_to_base64(fig),
        "xy_domain": [xmin, xmax, ymin, ymax],
        "max_magnitude": float(np.nanmax(mag)),
    }


def validate(params=None):
    """Checks anclados a metadata expuesta + verificacion numerica real
    del motor de integracion via _build_rhs (no solo 'no exploto')."""
    checks = []

    # --- function_plot: f(x)=x**2 en [-3,3], extremos exactos del linspace ---
    res_fp = _function_plot({"function_expr": "x**2", "domain": [-3, 3]})
    checks.append({
        "name": "function_plot_x_cuadrado_y_max_exacto_en_borde_dominio",
        "y_max": res_fp.get("y_max"),
        "passed": bool(abs(res_fp.get("y_max", -1) - 9.0) < 1e-9),
    })
    checks.append({
        "name": "function_plot_x_cuadrado_y_min_cerca_de_cero",
        "y_min": res_fp.get("y_min"),
        "passed": bool(res_fp.get("y_min", 999) < 1e-3),
    })

    # --- vector_field: campo constante u=1, v=0 -> magnitud exacta 1.0 ---
    res_vf = _vector_field({
        "vector_expr_u": "1", "vector_expr_v": "0",
        "xy_domain": [-2, 2, -2, 2],
    })
    checks.append({
        "name": "vector_field_campo_constante_magnitud_maxima_exacta",
        "max_magnitude": res_vf.get("max_magnitude"),
        "passed": bool(abs(res_vf.get("max_magnitude", -1) - 1.0) < 1e-9),
    })

    # --- bifurcation_render: dataset sintetico, conteo exacto de puntos ---
    r_values = [1, 2, 3]
    x_values = [[0.1], [0.2, 0.3], [0.4, 0.5, 0.6]]
    res_br = _bifurcation_render({"r_values": r_values, "x_values": x_values})
    expected_n = sum(len(xs) for xs in x_values)
    checks.append({
        "name": "bifurcation_render_conteo_puntos_coincide_con_dataset_sintetico",
        "expected": expected_n,
        "actual": res_br.get("n_points_total"),
        "passed": bool(res_br.get("n_points_total") == expected_n),
    })

    # --- phase_portrait: n_points hardcodeado a 6000, cualquier sistema ---
    res_pp = _phase_portrait({"system": "van_der_pol", "tspan": [0, 5]})
    checks.append({
        "name": "phase_portrait_n_points_hardcodeado_6000",
        "n_points": res_pp.get("n_points"),
        "passed": bool(res_pp.get("n_points") == 6000),
    })

    # --- phase_portrait: verificacion numerica real via _build_rhs ---
    # oscilador armonico simple: dx/dt = y[1], dy/dt = -y[0]
    # solucion analitica con y0=[1,0]: y[0](t)=cos(t), y[1](t)=-sin(t)
    # en t=2*pi debe volver casi exacto a y0
    import numpy as _np
    from scipy.integrate import solve_ivp as _solve_ivp

    rhs, dim = _build_rhs("custom", "y[1];-y[0]", None)
    y0 = [1.0, 0.0]
    t_final = 2 * _np.pi
    sol = _solve_ivp(rhs, [0, t_final], y0, t_eval=[0, t_final], rtol=1e-10, atol=1e-12)
    y_end = sol.y[:, -1]
    err = float(_np.max(_np.abs(y_end - _np.array(y0))))
    checks.append({
        "name": "phase_portrait_oscilador_armonico_retorna_a_y0_tras_un_periodo",
        "y0": y0,
        "y_final": y_end.tolist(),
        "error_max": err,
        "passed": bool(err < 1e-6),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_math_visualization(mode="function_plot", **kwargs):
    if mode == "function_plot":
        return _function_plot(kwargs)
    elif mode == "phase_portrait":
        return _phase_portrait(kwargs)
    elif mode == "bifurcation_render":
        return _bifurcation_render(kwargs)
    elif mode == "vector_field":
        return _vector_field(kwargs)
    elif mode == "validate":
        return validate(kwargs)
    else:
        raise ValueError(f"mode desconocido: {mode}")


if __name__ == "__main__":
    print("=== function_plot ===")
    r1 = compute_math_visualization(mode="function_plot", function_expr="sin(x)*exp(-x**2/10)", domain=[-8, 8])
    print("keys:", list(r1.keys()), "| bytes b64:", len(r1["image_base64"]))

    print("\n=== phase_portrait (lorenz) ===")
    r2 = compute_math_visualization(mode="phase_portrait", system="lorenz", projection="3d")
    print("keys:", list(r2.keys()), "| n_points:", r2["n_points"], "| bytes b64:", len(r2["image_base64"]))

    print("\n=== bifurcation_render (datos sinteticos) ===")
    r_values = list(np.linspace(2.5, 4.0, 20))
    x_values = [list(np.random.rand(15)) for _ in r_values]
    r3 = compute_math_visualization(mode="bifurcation_render", r_values=r_values, x_values=x_values)
    print("keys:", list(r3.keys()), "| n_points_total:", r3["n_points_total"])

    print("\n=== vector_field (gradiente de x**2+y**2) ===")
    r4 = compute_math_visualization(mode="vector_field", vector_expr_u="2*x", vector_expr_v="2*y")
    print("keys:", list(r4.keys()), "| max_magnitude:", round(r4["max_magnitude"], 3))

    print("\nOK - todos los modos corrieron sin excepciones.")

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("math_visualization", MATH_VISUALIZATION_TOOL_SCHEMA, lambda args, _f=compute_math_visualization: _f(**args))
