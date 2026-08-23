"""
plotting_tools.py

Curvas parametricas 2D y visualizacion matematica: curva parametrica
generica, familia de cicloides (cicloide / epicicloide / hipocicloide),
y curva con vectores tangente/normal en un punto. Calculo geometrico en
Python puro (numpy/sympy), sin depender de un binario externo de Octave
-- mismo patron de wrapper liviano que el resto de octave-mcp.

Modos:
  - parametric_curve  : curva x(t),y(t) a partir de expresiones sympy.
                         Longitud de arco (quad) y area encerrada
                         (teorema de Green, quad). Validado con el
                         circulo unitario (arco=2*pi, area=pi).
  - cycloid_family      : cicloide / epicicloide / hipocicloide.
                         Validado contra resultados clasicos exactos:
                         area de un arco de cicloide = 3*pi*r^2 (Galileo),
                         longitud de un arco = 8*r; caso astroide
                         (hipocicloide R=4r): area=(3/8)*pi*R^2,
                         longitud=6*R.
  - curve_with_vectors  : vector tangente/normal unitarios en un punto,
                         via derivadas simbolicas exactas (sympy).
                         Validado por autoconsistencia (T.N=0, |T|=|N|=1).
  - validate             : autochequeo de los 3 modos anteriores.

Renderizado: cada modo acepta render=True para devolver un PNG estatico
en base64 (matplotlib), con ejes matematicos en el origen y flechas de
direccion (draw_axes). El modo animate_trace genera un GIF en base64
con traza progresiva sobre parametric_curve o cycloid_family (requiere
pillow instalado; matplotlib lo usa como writer="pillow").
"""

import base64
import io

import numpy as np
import sympy as sp
from scipy.integrate import quad
import sys
import json

MODES = [
    "parametric_curve",
    "cycloid_family",
    "curve_with_vectors",
    "animate_trace",
    "validate",
]

TOOL_SCHEMA = {
    "name": "plotting_tools",
    "description": (
        "Curvas parametricas 2D y visualizacion matematica: curva "
        "parametrica generica, familia de cicloides (cicloide / "
        "epicicloide / hipocicloide), curva con vectores tangente/normal "
        "en un punto, triedro de Frenet-Serret 3D (tangente/normal/"
        "binormal), y animacion GIF de traza progresiva. Modos: "
        "parametric_curve, cycloid_family, curve_with_vectors, "
        "frenet_frame_3d, animate_trace, self_test, validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["parametric_curve", "cycloid_family",
                         "curve_with_vectors", "frenet_frame_3d",
                         "animate_trace", "self_test", "validate"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "fx": {"type": "string", "description": "expresion x(t) (parametric_curve, curve_with_vectors, animate_trace con curve_mode=parametric_curve)"},
                    "fy": {"type": "string", "description": "expresion y(t) (parametric_curve, curve_with_vectors, animate_trace)"},
                    "fz": {"type": "string", "description": "expresion z(t) (frenet_frame_3d)"},
                    "t_min": {"type": "number", "description": "t inicial (parametric_curve, curve_with_vectors)"},
                    "t_max": {"type": "number", "description": "t final (parametric_curve, curve_with_vectors)"},
                    "n_points": {"type": "integer", "description": "cantidad de puntos"},
                    "closed": {"type": "boolean", "description": "si la curva es cerrada (parametric_curve)"},
                    "r": {"type": "number", "description": "radio de la rueda (cycloid_family, animate_trace con curve_mode=cycloid_family)"},
                    "kind": {"type": "string", "enum": ["cycloid", "epicycloid", "hypocycloid"], "description": "tipo de cicloide"},
                    "R_fixed": {"type": "number", "description": "radio del circulo fijo (epicycloid/hypocycloid)"},
                    "revolutions": {"type": "number", "description": "vueltas (cycloid_family)"},
                    "t_point": {"type": "number", "description": "punto t donde evaluar T/N (curve_with_vectors)"},
                    "render": {"type": "boolean", "description": "si True, devuelve png_base64 (default False)"},
                    "curve_mode": {"type": "string", "enum": ["parametric_curve", "cycloid_family"], "description": "curva base a animar (animate_trace, default parametric_curve)"},
                    "n_frames": {"type": "integer", "description": "cantidad de cuadros del GIF (animate_trace, default 60)"},
                    "fps": {"type": "integer", "description": "cuadros por segundo del GIF (animate_trace, default 20)"},
                },
            },
        },
        "required": ["mode"],
    },
}

_T = sp.symbols("t", real=True)


# compute_plotting_curves() reemplazada por run() mas abajo (patron de auto-registro)


# --------------------------------------------------------------------------
# Utilidades internas
# --------------------------------------------------------------------------

def _parse_expr(expr_str):
    """Parsea una expresion en la variable t usando sympy (no eval crudo)."""
    return sp.sympify(expr_str, locals={"t": _T})


def _render_png_base64(x, y, title="", extra_draw=None, equal_aspect=True):
    """Renderiza x,y con matplotlib y devuelve un PNG en base64."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot(x, y, "b-", linewidth=2)
    if extra_draw is not None:
        extra_draw(ax)
    if equal_aspect:
        ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, alpha=0.3)
    ax.set_title(title)

    # ejes matematicos en el origen (draw_axes) CON flechas de direccion,
    # en vez de usar los ejes del borde de la grafica -- se dibujan al
    # final, sobre los limites ya calculados por autoscale, y luego se
    # restauran esos limites para que las flechas no los alteren.
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    ax.axhline(0, color="black", linewidth=0.8, zorder=1)
    ax.axvline(0, color="black", linewidth=0.8, zorder=1)
    arrow_kw = dict(arrowstyle="-|>", color="black", mutation_scale=14, linewidth=0.8)
    ax.annotate("", xy=(xlim[1], 0),
                xytext=(xlim[1] - (xlim[1] - xlim[0]) * 0.03, 0),
                arrowprops=arrow_kw, annotation_clip=False)
    ax.annotate("", xy=(0, ylim[1]),
                xytext=(0, ylim[1] - (ylim[1] - ylim[0]) * 0.03),
                arrowprops=arrow_kw, annotation_clip=False)
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


# --------------------------------------------------------------------------
# 1. Curva parametrica generica
# --------------------------------------------------------------------------

def _parametric_curve(fx="cos(t)", fy="sin(t)", t_min=0.0, t_max=2 * np.pi,
                       n_points=500, closed=True, render=False):
    """
    x(t), y(t) dadas como expresiones sympy en 't'. Se calculan:
      - longitud de arco: integral( sqrt(x'(t)^2 + y'(t)^2) dt )  (quad)
      - area encerrada (si closed=True), via teorema de Green:
            A = (1/2) * integral( x*y' - y*x' dt )  sobre [t_min, t_max]
        (exacto para curvas cerradas simples; si la curva no cierra
        sobre si misma el numero devuelto no representa un area fisica).
    """
    fx_sym = _parse_expr(fx)
    fy_sym = _parse_expr(fy)
    dfx = sp.diff(fx_sym, _T)
    dfy = sp.diff(fy_sym, _T)

    fx_num = sp.lambdify(_T, fx_sym, "numpy")
    fy_num = sp.lambdify(_T, fy_sym, "numpy")
    dfx_num = sp.lambdify(_T, dfx, "numpy")
    dfy_num = sp.lambdify(_T, dfy, "numpy")

    t_vals = np.linspace(t_min, t_max, n_points)
    x_vals = np.asarray(fx_num(t_vals), dtype=float)
    y_vals = np.asarray(fy_num(t_vals), dtype=float)

    speed = lambda t: float(np.hypot(dfx_num(t), dfy_num(t)))
    arc_length, _ = quad(speed, t_min, t_max)

    area = None
    if closed:
        green_integrand = lambda t: float(
            fx_num(t) * dfy_num(t) - fy_num(t) * dfx_num(t)
        )
        integral_val, _ = quad(green_integrand, t_min, t_max)
        area = 0.5 * integral_val

    result = {
        "mode": "parametric_curve",
        "t": t_vals.tolist(),
        "x": x_vals.tolist(),
        "y": y_vals.tolist(),
        "arc_length": float(arc_length),
        "enclosed_area": (float(area) if area is not None else None),
        "params": {"fx": fx, "fy": fy, "t_min": t_min, "t_max": t_max,
                    "closed": closed},
    }
    if render:
        result["png_base64"] = _render_png_base64(
            x_vals, y_vals, title=f"x={fx}, y={fy}")
    return result


# --------------------------------------------------------------------------
# 2. Familia de cicloides
# --------------------------------------------------------------------------

def _cycloid_family(r=1.0, kind="cycloid", R_fixed=None, revolutions=1.0,
                     n_points=1000, render=False):
    """
    kind='cycloid'     : x=r(t-sin t),  y=r(1-cos t)      (rueda sobre recta)
    kind='epicycloid'   : rueda de radio r por FUERA de un circulo fijo
                         de radio R_fixed
    kind='hypocycloid'  : rueda de radio r por DENTRO de un circulo fijo
                         de radio R_fixed  (R_fixed=4*r -> astroide)

    Resultados clasicos exactos usados para validar:
      - cicloide, un arco (t en [0,2*pi]):
            area entre el arco y la base = 3*pi*r^2   (Galileo)
            longitud del arco             = 8*r
      - astroide (hipocicloide con R_fixed = 4*r), curva cerrada completa:
            area encerrada = (3/8)*pi*R_fixed^2
            longitud total  = 6*R_fixed
    """
    if kind == "cycloid":
        t_max = 2 * np.pi * revolutions
        t = np.linspace(0.0, t_max, n_points)
        x = r * (t - np.sin(t))
        y = r * (1.0 - np.cos(t))
        dxdt = r * (1.0 - np.cos(t))
        dydt = r * np.sin(t)

    elif kind in ("epicycloid", "hypocycloid"):
        if R_fixed is None:
            raise ValueError(f"{kind} requiere R_fixed (radio del circulo fijo)")
        sign = 1.0 if kind == "epicycloid" else -1.0
        Rr = R_fixed + sign * r
        ratio = Rr / r
        t_max = 2 * np.pi * revolutions
        t = np.linspace(0.0, t_max, n_points)
        x = Rr * np.cos(t) - sign * r * np.cos(ratio * t)
        y = Rr * np.sin(t) - r * np.sin(ratio * t)
        dxdt = -Rr * np.sin(t) + sign * r * ratio * np.sin(ratio * t)
        dydt = Rr * np.cos(t) - r * ratio * np.cos(ratio * t)

    else:
        raise ValueError(
            f"kind desconocido: {kind!r}. Usar 'cycloid', 'epicycloid' o "
            "'hypocycloid'."
        )

    speed = np.hypot(dxdt, dydt)
    arc_length = float(np.trapezoid(speed, t))

    # area via Green (valida si la curva efectivamente cierra: epi/hipo
    # completas con revolutions=1 cierran; la cicloide NO cierra por si
    # sola -- su "area de un arco" se define contra la base y=0, que es
    # el resultado de Galileo, no un area de Green directa)
    green_area = float(0.5 * np.trapezoid(x * dydt - y * dxdt, t))

    result = {
        "mode": "cycloid_family",
        "kind": kind,
        "t": t.tolist(),
        "x": x.tolist(),
        "y": y.tolist(),
        "arc_length": arc_length,
        "green_area": green_area,
        "params": {"r": r, "R_fixed": R_fixed, "revolutions": revolutions},
    }
    if render:
        result["png_base64"] = _render_png_base64(x, y, title=f"{kind} (r={r})")
    return result


def _cycloid_arch_area_galileo(r, n_points=4000):
    """Area entre un arco de cicloide (t en [0,2*pi]) y la base y=0,
    calculada por integracion directa: A = integral( y(t) * dx/dt dt )."""
    t = np.linspace(0.0, 2 * np.pi, n_points)
    y = r * (1.0 - np.cos(t))
    dxdt = r * (1.0 - np.cos(t))
    return float(np.trapezoid(y * dxdt, t))


# --------------------------------------------------------------------------
# 4. Animacion de traza progresiva (GIF en base64)
# --------------------------------------------------------------------------

def _animate_trace(curve_mode="parametric_curve", n_frames=60, fps=20, **curve_kwargs):
    """
    Genera un GIF (base64) con la traza progresiva de una curva ya
    definida por parametric_curve o cycloid_family. Reutiliza el calculo
    exacto de esas funciones (misma x(t), y(t)) y solo agrega la logica
    de animacion -- no reimplementa geometria.

    curve_kwargs se pasan tal cual a _parametric_curve o _cycloid_family
    (sin render, que no aplica aca).
    """
    curve_kwargs = dict(curve_kwargs)
    curve_kwargs.pop("render", None)

    if curve_mode == "parametric_curve":
        data = _parametric_curve(render=False, **curve_kwargs)
    elif curve_mode == "cycloid_family":
        data = _cycloid_family(render=False, **curve_kwargs)
    else:
        raise ValueError(
            f"curve_mode desconocido: {curve_mode!r}. "
            "Usar 'parametric_curve' o 'cycloid_family'."
        )

    x = np.asarray(data["x"], dtype=float)
    y = np.asarray(data["y"], dtype=float)
    n_points = len(x)
    if n_points < 2:
        raise ValueError("la curva necesita al menos 2 puntos para animar")

    n_frames = max(2, min(int(n_frames), n_points))
    frame_idx = np.linspace(1, n_points, n_frames, dtype=int)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.animation as animation

    x_pad = 0.1 * (np.ptp(x) + 1e-9)
    y_pad = 0.1 * (np.ptp(y) + 1e-9)

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.set_xlim(x.min() - x_pad, x.max() + x_pad)
    ax.set_ylim(y.min() - y_pad, y.max() + y_pad)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.grid(True, alpha=0.3)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(f"{curve_mode} (animate_trace)")

    line, = ax.plot([], [], "b-", linewidth=2)
    point, = ax.plot([], [], "ro", markersize=8)

    def _update(frame):
        idx = frame_idx[frame]
        line.set_data(x[:idx], y[:idx])
        point.set_data([x[idx - 1]], [y[idx - 1]])
        return line, point

    anim = animation.FuncAnimation(
        fig, _update, frames=len(frame_idx), blit=True
    )

    import os
    import tempfile
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".gif")
    os.close(tmp_fd)
    try:
        anim.save(tmp_path, writer="pillow", fps=fps)
        plt.close(fig)
        with open(tmp_path, "rb") as _gif_f:
            gif_b64 = base64.b64encode(_gif_f.read()).decode("ascii")
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    return {
        "mode": "animate_trace",
        "curve_mode": curve_mode,
        "n_frames": int(len(frame_idx)),
        "fps": int(fps),
        "gif_base64": gif_b64,
        "underlying_params": data.get("params", {}),
    }


# --------------------------------------------------------------------------
# 3. Curva con vectores tangente / normal
# --------------------------------------------------------------------------

def _curve_with_vectors(fx="cos(t)", fy="sin(t)", t_point=0.7,
                         t_min=0.0, t_max=2 * np.pi, n_points=300,
                         render=False):
    """
    Derivadas EXACTAS via sympy (no diferenciacion numerica). En t_point:
      T = (dx/dt, dy/dt) / ||(dx/dt, dy/dt)||   (tangente unitario)
      N = (-dy/dt, dx/dt) / ||(dx/dt, dy/dt)||  (normal unitario, +90 grados)
    """
    fx_sym = _parse_expr(fx)
    fy_sym = _parse_expr(fy)
    dfx = sp.diff(fx_sym, _T)
    dfy = sp.diff(fy_sym, _T)

    fx_num = sp.lambdify(_T, fx_sym, "numpy")
    fy_num = sp.lambdify(_T, fy_sym, "numpy")
    dfx_num = sp.lambdify(_T, dfx, "numpy")
    dfy_num = sp.lambdify(_T, dfy, "numpy")

    t_vals = np.linspace(t_min, t_max, n_points)
    x_vals = np.asarray(fx_num(t_vals), dtype=float)
    y_vals = np.asarray(fy_num(t_vals), dtype=float)

    x0 = float(fx_num(t_point))
    y0 = float(fy_num(t_point))
    dx0 = float(dfx_num(t_point))
    dy0 = float(dfy_num(t_point))
    speed0 = float(np.hypot(dx0, dy0))

    if speed0 > 0:
        T = (dx0 / speed0, dy0 / speed0)
        N = (-dy0 / speed0, dx0 / speed0)
    else:
        T = (1.0, 0.0)
        N = (0.0, 1.0)

    dot_TN = T[0] * N[0] + T[1] * N[1]
    norm_T = float(np.hypot(*T))
    norm_N = float(np.hypot(*N))

    result = {
        "mode": "curve_with_vectors",
        "t": t_vals.tolist(),
        "x": x_vals.tolist(),
        "y": y_vals.tolist(),
        "point": {"t": t_point, "x": x0, "y": y0},
        "tangent_unit": T,
        "normal_unit": N,
        "dot_T_N": dot_TN,
        "norm_T": norm_T,
        "norm_N": norm_N,
        "params": {"fx": fx, "fy": fy, "t_point": t_point},
    }
    if render:
        def _draw_vectors(ax):
            scale = 0.5
            ax.plot(x0, y0, "ko", markersize=7)
            ax.annotate("", xy=(x0 + T[0] * scale, y0 + T[1] * scale),
                        xytext=(x0, y0),
                        arrowprops=dict(color="red", width=1.5, headwidth=6))
            ax.annotate("", xy=(x0 + N[0] * scale, y0 + N[1] * scale),
                        xytext=(x0, y0),
                        arrowprops=dict(color="green", width=1.5, headwidth=6))
        result["png_base64"] = _render_png_base64(
            x_vals, y_vals, title=f"x={fx}, y={fy}  (t0={t_point})",
            extra_draw=_draw_vectors)
    return result


# --------------------------------------------------------------------------
# 4. Validate
# --------------------------------------------------------------------------


def _frenet_frame_3d(fx, fy, fz, t_point, t_min=0.0, t_max=1.0,
                      n_points=200, render=False):
    t = _T
    x_expr = _parse_expr(fx)
    y_expr = _parse_expr(fy)
    z_expr = _parse_expr(fz)

    x1, y1, z1 = (sp.diff(e, t) for e in (x_expr, y_expr, z_expr))
    x2, y2, z2 = (sp.diff(e, t) for e in (x1, y1, z1))

    r1 = np.array([float(x1.subs(t, t_point)),
                   float(y1.subs(t, t_point)),
                   float(z1.subs(t, t_point))])
    r2 = np.array([float(x2.subs(t, t_point)),
                   float(y2.subs(t, t_point)),
                   float(z2.subs(t, t_point))])

    T = r1 / np.linalg.norm(r1)
    cross_12 = np.cross(r1, r2)
    cross_norm = np.linalg.norm(cross_12)

    if cross_norm < 1e-12:
        arbitrary = np.array([1.0, 0.0, 0.0])
        if abs(np.dot(T, arbitrary)) > 0.9:
            arbitrary = np.array([0.0, 1.0, 0.0])
        B = np.cross(T, arbitrary)
        B = B / np.linalg.norm(B)
        N = np.cross(B, T)
        curvature = 0.0
    else:
        B = cross_12 / cross_norm
        N = np.cross(B, T)
        curvature = cross_norm / (np.linalg.norm(r1) ** 3)

    result = {
        "T": T.tolist(), "N": N.tolist(), "B": B.tolist(),
        "curvature": float(curvature),
        "dot_T_N": float(np.dot(T, N)),
        "dot_T_B": float(np.dot(T, B)),
        "dot_N_B": float(np.dot(N, B)),
        "norm_T": float(np.linalg.norm(T)),
        "norm_N": float(np.linalg.norm(N)),
        "norm_B": float(np.linalg.norm(B)),
        "triad_dextrogyro": float(np.dot(T, np.cross(N, B))),
    }

    if render:
        f_x = sp.lambdify(t, x_expr, "numpy")
        f_y = sp.lambdify(t, y_expr, "numpy")
        f_z = sp.lambdify(t, z_expr, "numpy")
        ts_ = np.linspace(t_min, t_max, n_points)

        def _eval_grid(f):
            val = f(ts_)
            return np.broadcast_to(np.asarray(val, dtype=float), ts_.shape).astype(float)

        xs, ys, zs = _eval_grid(f_x), _eval_grid(f_y), _eval_grid(f_z)
        point = np.array([float(x_expr.subs(t, t_point)),
                           float(y_expr.subs(t, t_point)),
                           float(z_expr.subs(t, t_point))])
        result["png_base64"] = _render_png_base64_3d(xs, ys, zs, point, T, N, B)

    return result


def _render_png_base64_3d(x, y, z, point, T, N, B, scale=None):
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  (registra proyeccion 3d)

    fig = plt.figure(figsize=(6, 6))
    ax = fig.add_subplot(111, projection="3d")
    ax.plot(x, y, z, color="tab:blue", linewidth=1.2)

    if scale is None:
        span = max(np.ptp(x), np.ptp(y), np.ptp(z), 1e-9)
        scale = span * 0.15

    px, py, pz = point
    ax.quiver(px, py, pz, *(T * scale), color="red", linewidth=1.5)
    ax.quiver(px, py, pz, *(N * scale), color="green", linewidth=1.5)
    ax.quiver(px, py, pz, *(B * scale), color="blue", linewidth=1.5)
    ax.scatter([px], [py], [pz], color="black", s=20)
    ax.set_box_aspect([1, 1, 1])

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def run_self_test():
    checks = []

    def check(name, cond, detail=""):
        checks.append({"name": name, "passed": bool(cond), "detail": detail})

    # -- parametric_curve: circulo unitario --
    out = _parametric_curve(fx="cos(t)", fy="sin(t)", t_min=0.0,
                             t_max=2 * np.pi, n_points=500, closed=True)
    arc_err = abs(out["arc_length"] - 2 * np.pi)
    area_err = abs(out["enclosed_area"] - np.pi)
    check("parametric_curve: circulo unitario (arco)", arc_err < 1e-8, f"err={arc_err:.2e}")
    check("parametric_curve: circulo unitario (area)", area_err < 1e-8, f"err={area_err:.2e}")

    # -- cycloid: area de Galileo (3*pi*r^2) y longitud de arco (8*r) --
    r = 1.3
    out = _cycloid_family(r=r, kind="cycloid", revolutions=1.0, n_points=4000)
    area_galileo = _cycloid_arch_area_galileo(r, n_points=4000)
    area_exact = 3.0 * np.pi * r ** 2
    length_exact = 8.0 * r
    area_err = abs(area_galileo - area_exact) / area_exact
    length_err = abs(out["arc_length"] - length_exact) / length_exact
    check("cycloid: area vs Galileo", area_err < 1e-4, f"rel err={area_err:.2e}")
    check("cycloid: longitud de arco vs 8r", length_err < 1e-4, f"rel err={length_err:.2e}")

    # -- hipocicloide con R_fixed=4r -> astroide --
    r = 1.0
    R_fixed = 4.0 * r
    out = _cycloid_family(r=r, kind="hypocycloid", R_fixed=R_fixed,
                           revolutions=1.0, n_points=4000)
    area_exact = (3.0 / 8.0) * np.pi * R_fixed ** 2
    length_exact = 6.0 * R_fixed
    area_err = abs(abs(out["green_area"]) - area_exact) / area_exact
    length_err = abs(out["arc_length"] - length_exact) / length_exact
    check("hypocycloid/astroide: area vs forma cerrada", area_err < 1e-3, f"rel err={area_err:.2e}")
    check("hypocycloid/astroide: longitud vs forma cerrada", length_err < 1e-3, f"rel err={length_err:.2e}")

    # -- curve_with_vectors: autoconsistencia T.N=0, |T|=|N|=1 --
    out = _curve_with_vectors(fx="cos(t)+t/5", fy="sin(2*t)", t_point=1.1)
    passed = (abs(out["dot_T_N"]) < 1e-9 and
              abs(out["norm_T"] - 1.0) < 1e-9 and
              abs(out["norm_N"] - 1.0) < 1e-9)
    check("curve_with_vectors: ortonormalidad T,N", passed,
          f"dot={out['dot_T_N']:.2e}, |T|={out['norm_T']:.6f}, |N|={out['norm_N']:.6f}")

    # -- frenet_frame_3d: helice circular, formulas cerradas conocidas --
    out = _frenet_frame_3d(fx="cos(t)", fy="sin(t)", fz="t", t_point=1.1)
    ortho_ok = (abs(out["dot_T_N"]) < 1e-9 and abs(out["dot_T_B"]) < 1e-9 and
                abs(out["dot_N_B"]) < 1e-9)
    norms_ok = (abs(out["norm_T"] - 1.0) < 1e-9 and
                abs(out["norm_N"] - 1.0) < 1e-9 and
                abs(out["norm_B"] - 1.0) < 1e-9)
    dextro_ok = abs(out["triad_dextrogyro"] - 1.0) < 1e-9
    curv_err = abs(out["curvature"] - 0.5)
    check("frenet_frame_3d: helice - ortonormalidad T,N,B", ortho_ok and norms_ok,
          f"dotTN={out['dot_T_N']:.2e} dotTB={out['dot_T_B']:.2e} dotNB={out['dot_N_B']:.2e}")
    check("frenet_frame_3d: helice - triedro dextrogiro", dextro_ok,
          f"T.(NxB)={out['triad_dextrogyro']:.6f}")
    check("frenet_frame_3d: helice - curvatura=0.5", curv_err < 1e-9, f"err={curv_err:.2e}")

    # -- frenet_frame_3d: recta (curvatura nula, r'xr''=0, caso degenerado) --
    out = _frenet_frame_3d(fx="t", fy="t", fz="t", t_point=0.5)
    ortho_ok = (abs(out["dot_T_N"]) < 1e-9 and abs(out["dot_T_B"]) < 1e-9 and
                abs(out["dot_N_B"]) < 1e-9)
    check("frenet_frame_3d: recta - fallback sin r'xr'', ortonormalidad", ortho_ok,
          f"curvature={out['curvature']:.2e}")

    # -- animate_trace: check liviano (no pixel-perfect) -- confirma que
    # se genera un GIF base64 no vacio y decodificable, sin validar el
    # contenido visual cuadro a cuadro.
    try:
        out = _animate_trace(curve_mode="parametric_curve", n_frames=5,
                              fps=10, fx="cos(t)", fy="sin(t)", n_points=50)
        gif_b64 = out.get("gif_base64", "")
        decoded_ok = False
        if gif_b64:
            try:
                raw = base64.b64decode(gif_b64, validate=True)
                decoded_ok = raw[:6] in (b"GIF87a", b"GIF89a")
            except Exception:
                decoded_ok = False
        check("animate_trace: genera GIF base64 valido", decoded_ok,
              f"len(base64)={len(gif_b64)}")
    except Exception as e:
        check("animate_trace: genera GIF base64 valido", False, f"excepcion: {e}")

    total = len(checks)
    passed_n = sum(1 for c in checks if c["passed"])
    return {"total": total, "passed": passed_n, "all_passed": passed_n == total, "checks": checks}


def run(mode, params=None):
    params = params or {}
    if mode == "validate":
        r = run_self_test()
        return {"checks": r["checks"], "validation_passed": r["all_passed"], "n_checks": r["total"]}
    elif mode == "self_test":
        return run_self_test()
    elif mode == "parametric_curve":
        return _parametric_curve(**params)
    elif mode == "cycloid_family":
        return _cycloid_family(**params)
    elif mode == "curve_with_vectors":
        return _curve_with_vectors(**params)
    elif mode == "animate_trace":
        return _animate_trace(**params)
    elif mode == "frenet_frame_3d":
        return _frenet_frame_3d(**params)
    else:
        raise ValueError(
            f"modo desconocido: {mode} "
            "(usar parametric_curve/cycloid_family/curve_with_vectors/"
            "animate_trace/self_test)"
        )


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

        tool_registry.register_tool("plotting_tools", TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()
