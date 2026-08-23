#!/usr/bin/env python3
"""
patch_plotting_tools_v2.py

Segunda pasada sobre plotting_tools.py (ya migrado al patron de
auto-registro por patch_plotting_tools.py). Agrega:

  1. Flechas de direccion en los ejes matematicos de _render_png_base64
     (draw_axes con flechas, no solo lineas en el origen).
  2. Modo nuevo animate_trace: GIF en base64 con traza progresiva de una
     parametric_curve o cycloid_family (requiere PIL/pillow instalado,
     matplotlib lo usa como writer='pillow' para animation.save(...,
     format='gif')).

Uso:
    cd ~/octave-mcp
    python3 patch_plotting_tools_v2.py

5 anchors independientes, cada uno con assert count==1. Backup
timestampeado antes de escribir, validacion ast.parse + py_compile.
"""

import ast
import py_compile
import shutil
import sys
import time
from pathlib import Path

TARGET = Path("plotting_tools.py")

# ---------------------------------------------------------------------------
# Anchor A: nota de docstring sobre animacion (queda desactualizada)
# ---------------------------------------------------------------------------

OLD_DOCSTRING_NOTE = '''Renderizado: cada modo acepta render=True para devolver un PNG estatico
en base64 (matplotlib). La animacion tipo GIF (traza progresiva) queda
para un modo aparte si se necesita -- no incluida aca para no acoplar
generacion de imagenes pesadas al calculo geometrico base.'''

NEW_DOCSTRING_NOTE = '''Renderizado: cada modo acepta render=True para devolver un PNG estatico
en base64 (matplotlib), con ejes matematicos en el origen y flechas de
direccion (draw_axes). El modo animate_trace genera un GIF en base64
con traza progresiva sobre parametric_curve o cycloid_family (requiere
pillow instalado; matplotlib lo usa como writer="pillow").'''

# ---------------------------------------------------------------------------
# Anchor B: MODES + TOOL_SCHEMA -- agregar animate_trace
# ---------------------------------------------------------------------------

OLD_MODES_SCHEMA = '''MODES = [
    "parametric_curve",
    "cycloid_family",
    "curve_with_vectors",
    "validate",
]

TOOL_SCHEMA = {
    "name": "plotting_tools",
    "description": (
        "Curvas parametricas 2D y visualizacion matematica: curva "
        "parametrica generica, familia de cicloides (cicloide / "
        "epicicloide / hipocicloide), y curva con vectores tangente/normal "
        "en un punto. Modos: parametric_curve, cycloid_family, "
        "curve_with_vectors, self_test, validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["parametric_curve", "cycloid_family",
                         "curve_with_vectors", "self_test", "validate"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "fx": {"type": "string", "description": "expresion x(t) (parametric_curve, curve_with_vectors)"},
                    "fy": {"type": "string", "description": "expresion y(t) (parametric_curve, curve_with_vectors)"},
                    "t_min": {"type": "number", "description": "t inicial (parametric_curve, curve_with_vectors)"},
                    "t_max": {"type": "number", "description": "t final (parametric_curve, curve_with_vectors)"},
                    "n_points": {"type": "integer", "description": "cantidad de puntos"},
                    "closed": {"type": "boolean", "description": "si la curva es cerrada (parametric_curve)"},
                    "r": {"type": "number", "description": "radio de la rueda (cycloid_family)"},
                    "kind": {"type": "string", "enum": ["cycloid", "epicycloid", "hypocycloid"], "description": "tipo de cicloide"},
                    "R_fixed": {"type": "number", "description": "radio del circulo fijo (epicycloid/hypocycloid)"},
                    "revolutions": {"type": "number", "description": "vueltas (cycloid_family)"},
                    "t_point": {"type": "number", "description": "punto t donde evaluar T/N (curve_with_vectors)"},
                    "render": {"type": "boolean", "description": "si True, devuelve png_base64 (default False)"},
                },
            },
        },
        "required": ["mode"],
    },
}'''

NEW_MODES_SCHEMA = '''MODES = [
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
        "en un punto, y animacion GIF de traza progresiva. Modos: "
        "parametric_curve, cycloid_family, curve_with_vectors, "
        "animate_trace, self_test, validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["parametric_curve", "cycloid_family",
                         "curve_with_vectors", "animate_trace",
                         "self_test", "validate"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "fx": {"type": "string", "description": "expresion x(t) (parametric_curve, curve_with_vectors, animate_trace con curve_mode=parametric_curve)"},
                    "fy": {"type": "string", "description": "expresion y(t) (parametric_curve, curve_with_vectors, animate_trace)"},
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
}'''

# ---------------------------------------------------------------------------
# Anchor C: _render_png_base64 -- agregar flechas de direccion en los ejes
# ---------------------------------------------------------------------------

OLD_RENDER_FN = '''def _render_png_base64(x, y, title="", extra_draw=None, equal_aspect=True):
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
    return base64.b64encode(buf.read()).decode("ascii")'''

NEW_RENDER_FN = '''def _render_png_base64(x, y, title="", extra_draw=None, equal_aspect=True):
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
    return base64.b64encode(buf.read()).decode("ascii")'''

# ---------------------------------------------------------------------------
# Anchor D: insertar _animate_trace despues de _cycloid_arch_area_galileo
# ---------------------------------------------------------------------------

OLD_INSERT_POINT = '''def _cycloid_arch_area_galileo(r, n_points=4000):
    """Area entre un arco de cicloide (t en [0,2*pi]) y la base y=0,
    calculada por integracion directa: A = integral( y(t) * dx/dt dt )."""
    t = np.linspace(0.0, 2 * np.pi, n_points)
    y = r * (1.0 - np.cos(t))
    dxdt = r * (1.0 - np.cos(t))
    return float(np.trapezoid(y * dxdt, t))'''

NEW_INSERT_POINT = '''def _cycloid_arch_area_galileo(r, n_points=4000):
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

    buf = io.BytesIO()
    anim.save(buf, format="gif", writer="pillow", fps=fps)
    plt.close(fig)
    buf.seek(0)
    gif_b64 = base64.b64encode(buf.read()).decode("ascii")

    return {
        "mode": "animate_trace",
        "curve_mode": curve_mode,
        "n_frames": int(len(frame_idx)),
        "fps": int(fps),
        "gif_base64": gif_b64,
        "underlying_params": data.get("params", {}),
    }'''

# ---------------------------------------------------------------------------
# Anchor E: run() -- agregar animate_trace al dispatch
# ---------------------------------------------------------------------------

OLD_RUN_ELIF = '''    elif mode == "curve_with_vectors":
        return _curve_with_vectors(**params)
    else:
        raise ValueError(
            f"modo desconocido: {mode} "
            "(usar parametric_curve/cycloid_family/curve_with_vectors/self_test)"
        )'''

NEW_RUN_ELIF = '''    elif mode == "curve_with_vectors":
        return _curve_with_vectors(**params)
    elif mode == "animate_trace":
        return _animate_trace(**params)
    else:
        raise ValueError(
            f"modo desconocido: {mode} "
            "(usar parametric_curve/cycloid_family/curve_with_vectors/"
            "animate_trace/self_test)"
        )'''

# ---------------------------------------------------------------------------
# Anchor F: run_self_test -- agregar check liviano de animate_trace
# ---------------------------------------------------------------------------

OLD_SELFTEST_TAIL = '''    total = len(checks)
    passed_n = sum(1 for c in checks if c["passed"])
    return {"total": total, "passed": passed_n, "all_passed": passed_n == total, "checks": checks}'''

NEW_SELFTEST_TAIL = '''    # -- animate_trace: check liviano (no pixel-perfect) -- confirma que
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
    return {"total": total, "passed": passed_n, "all_passed": passed_n == total, "checks": checks}'''


def apply_anchor(text, old, new, label):
    n = text.count(old)
    if n != 1:
        print(f"ERROR: anchor '{label}' encontrado {n} veces (se esperaba 1).")
        print("El archivo puede haber cambiado desde que se genero este patch.")
        sys.exit(1)
    assert n == 1
    return text.replace(old, new, 1)


def main():
    if not TARGET.exists():
        print(f"ERROR: no se encontro {TARGET} en el directorio actual ({Path.cwd()})")
        sys.exit(1)

    original = TARGET.read_text(encoding="utf-8")
    patched = original

    patched = apply_anchor(patched, OLD_DOCSTRING_NOTE, NEW_DOCSTRING_NOTE, "docstring nota animacion")
    patched = apply_anchor(patched, OLD_MODES_SCHEMA, NEW_MODES_SCHEMA, "MODES/TOOL_SCHEMA")
    patched = apply_anchor(patched, OLD_RENDER_FN, NEW_RENDER_FN, "_render_png_base64")
    patched = apply_anchor(patched, OLD_INSERT_POINT, NEW_INSERT_POINT, "insercion _animate_trace")
    patched = apply_anchor(patched, OLD_RUN_ELIF, NEW_RUN_ELIF, "run() dispatch")
    patched = apply_anchor(patched, OLD_SELFTEST_TAIL, NEW_SELFTEST_TAIL, "run_self_test tail")

    try:
        ast.parse(patched)
    except SyntaxError as e:
        print(f"ERROR: el resultado parcheado no es sintacticamente valido: {e}")
        sys.exit(1)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_path = TARGET.with_name(f"{TARGET.stem}.py.bak_{timestamp}")
    shutil.copy2(TARGET, backup_path)
    print(f"Backup creado: {backup_path}")

    TARGET.write_text(patched, encoding="utf-8")
    print(f"{TARGET} parcheado OK.")

    try:
        py_compile.compile(str(TARGET), doraise=True)
        print("py_compile OK.")
    except py_compile.PyCompileError as e:
        print(f"ERROR en py_compile tras escribir: {e}")
        print(f"Restaurando backup desde {backup_path}...")
        shutil.copy2(backup_path, TARGET)
        sys.exit(1)

    print("\\nListo. Ahora corre:")
    print("  python3 -c \"import PIL\" && echo 'pillow OK' || pip install pillow --break-system-packages")
    print("  python3 plotting_tools.py self_test")
    print("  python3 plotting_tools.py validate")


if __name__ == "__main__":
    main()
