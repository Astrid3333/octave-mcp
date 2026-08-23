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
en base64 (matplotlib). La animacion tipo GIF (traza progresiva) queda
para un modo aparte si se necesita -- no incluida aca para no acoplar
generacion de imagenes pesadas al calculo geometrico base.
"""

import base64
import io

import numpy as np
import sympy as sp
from scipy.integrate import quad

MODES = [
    "parametric_curve",
    "cycloid_family",
    "curve_with_vectors",
    "validate",
]

_T = sp.symbols("t", real=True)


def compute_plotting_curves(mode="parametric_curve", **kwargs):
    if mode == "validate":
        return _validate_plotting_curves()
    if mode == "parametric_curve":
        return _parametric_curve(**kwargs)
    if mode == "cycloid_family":
        return _cycloid_family(**kwargs)
    if mode == "curve_with_vectors":
        return _curve_with_vectors(**kwargs)
    raise ValueError(f"mode desconocido: {mode!r}. Modos validos: {MODES}")


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
    # ejes matematicos en el origen (draw_axes), no en el borde
    ax.axhline(0, color="black", linewidth=0.8)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.plot(x, y, "b-", linewidth=2)
    if extra_draw is not None:
        extra_draw(ax)
    if equal_aspect:
        ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, alpha=0.3)
    ax.set_title(title)

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

def _validate_plotting_curves():
    checks = []
    all_passed = True

    # -- parametric_curve: circulo unitario --
    out = _parametric_curve(fx="cos(t)", fy="sin(t)", t_min=0.0,
                             t_max=2 * np.pi, n_points=500, closed=True)
    arc_err = abs(out["arc_length"] - 2 * np.pi)
    area_err = abs(out["enclosed_area"] - np.pi)
    tol = 1e-8
    passed = arc_err < tol and area_err < tol
    all_passed &= passed
    checks.append({
        "name": "parametric_curve_unit_circle_vs_closed_form",
        "passed": bool(passed),
        "arc_length_abs_error": arc_err,
        "area_abs_error": area_err,
        "tolerance": tol,
    })

    # -- cycloid: area de Galileo (3*pi*r^2) y longitud de arco (8*r) --
    r = 1.3
    out = _cycloid_family(r=r, kind="cycloid", revolutions=1.0, n_points=4000)
    area_galileo = _cycloid_arch_area_galileo(r, n_points=4000)
    area_exact = 3.0 * np.pi * r ** 2
    length_exact = 8.0 * r
    area_err = abs(area_galileo - area_exact) / area_exact
    length_err = abs(out["arc_length"] - length_exact) / length_exact
    tol = 1e-4
    passed = area_err < tol and length_err < tol
    all_passed &= passed
    checks.append({
        "name": "cycloid_arch_vs_galileo_closed_form",
        "passed": bool(passed),
        "area_relative_error": area_err,
        "arc_length_relative_error": length_err,
        "tolerance": tol,
    })

    # -- hipocicloide con R_fixed=4r -> astroide --
    r = 1.0
    R_fixed = 4.0 * r
    out = _cycloid_family(r=r, kind="hypocycloid", R_fixed=R_fixed,
                           revolutions=1.0, n_points=4000)
    area_exact = (3.0 / 8.0) * np.pi * R_fixed ** 2
    length_exact = 6.0 * R_fixed
    area_err = abs(abs(out["green_area"]) - area_exact) / area_exact
    length_err = abs(out["arc_length"] - length_exact) / length_exact
    tol = 1e-3
    passed = area_err < tol and length_err < tol
    all_passed &= passed
    checks.append({
        "name": "hypocycloid_astroid_vs_closed_form",
        "passed": bool(passed),
        "area_relative_error": area_err,
        "arc_length_relative_error": length_err,
        "tolerance": tol,
    })

    # -- curve_with_vectors: autoconsistencia T.N=0, |T|=|N|=1 --
    out = _curve_with_vectors(fx="cos(t)+t/5", fy="sin(2*t)", t_point=1.1)
    tol = 1e-9
    passed = (abs(out["dot_T_N"]) < tol and
              abs(out["norm_T"] - 1.0) < tol and
              abs(out["norm_N"] - 1.0) < tol)
    all_passed &= passed
    checks.append({
        "name": "curve_with_vectors_orthonormality",
        "passed": bool(passed),
        "dot_T_N": out["dot_T_N"],
        "norm_T": out["norm_T"],
        "norm_N": out["norm_N"],
        "tolerance": tol,
    })

    return {
        "mode": "validate",
        "validation_passed": bool(all_passed),
        "checks": checks,
    }


# --------------------------------------------------------------------------
# NOTA DE INTEGRACION: mismo patron que mycelial_network_tool.py /
# fungal_morphology_tool.py -- schema con mode enum (MODES incluyendo
# "validate") + elif tool_name=="plotting_curves" en el dispatch de
# server.py. Firma plana / mode estandar => no requiere entradas en
# ALTERNATE_VALIDATE_MODE / ALTERNATE_VALIDATE_PARAM_NAME /
# FLAT_SIGNATURE_TOOLS.
#
# render=True devuelve png_base64 en el resultado -- pensar si conviene
# que el schema exponga render como parametro opcional (default False)
# para no inflar la respuesta de validate ni de llamadas exploratorias.
# --------------------------------------------------------------------------
