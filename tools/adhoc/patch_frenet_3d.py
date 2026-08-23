import re
import shutil
import datetime
import py_compile

FILE = "plotting_tools.py"
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup = f"{FILE}.bak_{ts}"
shutil.copy(FILE, backup)
print(f"Backup creado: {backup}")

with open(FILE, "r", encoding="utf-8") as f:
    src = f.read()

# --- 1) funciones nuevas, insertadas antes de run_self_test ---
NEW_FUNCS = '''
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


'''

anchor_funcs = "def run_self_test():"
assert src.count(anchor_funcs) == 1, "anchor de funciones no es unico"
src = src.replace(anchor_funcs, NEW_FUNCS + anchor_funcs, 1)

# --- 2) checks nuevos en run_self_test ---
anchor_checks = '''    check("curve_with_vectors: ortonormalidad T,N", passed,
          f"dot={out['dot_T_N']:.2e}, |T|={out['norm_T']:.6f}, |N|={out['norm_N']:.6f}")
'''
NEW_CHECKS = anchor_checks + '''
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
'''
assert src.count(anchor_checks) == 1, "anchor de checks no es unico"
src = src.replace(anchor_checks, NEW_CHECKS, 1)

# --- 3) dispatcher ---
anchor_dispatch = '''    elif mode == "animate_trace":
        return _animate_trace(**params)
    else:'''
NEW_DISPATCH = '''    elif mode == "animate_trace":
        return _animate_trace(**params)
    elif mode == "frenet_frame_3d":
        return _frenet_frame_3d(**params)
    else:'''
assert src.count(anchor_dispatch) == 1, "anchor de dispatcher no es unico"
src = src.replace(anchor_dispatch, NEW_DISPATCH, 1)

# --- 4) TOOL_SCHEMA: description ---
old_desc = '''    "description": (
        "Curvas parametricas 2D y visualizacion matematica: curva "
        "parametrica generica, familia de cicloides (cicloide / "
        "epicicloide / hipocicloide), curva con vectores tangente/normal "
        "en un punto, y animacion GIF de traza progresiva. Modos: "
        "parametric_curve, cycloid_family, curve_with_vectors, "
        "animate_trace, self_test, validate."
    ),'''
new_desc = '''    "description": (
        "Curvas parametricas 2D y visualizacion matematica: curva "
        "parametrica generica, familia de cicloides (cicloide / "
        "epicicloide / hipocicloide), curva con vectores tangente/normal "
        "en un punto, triedro de Frenet-Serret 3D (tangente/normal/"
        "binormal), y animacion GIF de traza progresiva. Modos: "
        "parametric_curve, cycloid_family, curve_with_vectors, "
        "frenet_frame_3d, animate_trace, self_test, validate."
    ),'''
assert src.count(old_desc) == 1, "anchor de description no es unico"
src = src.replace(old_desc, new_desc, 1)

# --- 5) TOOL_SCHEMA: enum ---
old_enum = '''                "enum": ["parametric_curve", "cycloid_family",
                         "curve_with_vectors", "animate_trace",
                         "self_test", "validate"],'''
new_enum = '''                "enum": ["parametric_curve", "cycloid_family",
                         "curve_with_vectors", "frenet_frame_3d",
                         "animate_trace", "self_test", "validate"],'''
assert src.count(old_enum) == 1, "anchor de enum no es unico"
src = src.replace(old_enum, new_enum, 1)

# --- 6) TOOL_SCHEMA: parametro fz ---
old_fy = '''                    "fy": {"type": "string", "description": "expresion y(t) (parametric_curve, curve_with_vectors, animate_trace)"},'''
new_fy = old_fy + '''
                    "fz": {"type": "string", "description": "expresion z(t) (frenet_frame_3d)"},'''
assert src.count(old_fy) == 1, "anchor de fy no es unico"
src = src.replace(old_fy, new_fy, 1)

with open(FILE, "w", encoding="utf-8") as f:
    f.write(src)

py_compile.compile(FILE, doraise=True)
print(f"{FILE} parcheado OK. py_compile OK.")
