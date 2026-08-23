#!/usr/bin/env python3
"""
patch_plotting_tools.py

Migra plotting_tools.py del patron viejo
(compute_plotting_curves(mode, **kwargs) + _validate_plotting_curves())
al patron de auto-registro usado en vector_calculus_tool.py / mycelial_network_tool.py
/ fungal_morphology_tool.py:
  TOOL_SCHEMA + run(mode, params=None) + run_self_test() + _register()

Uso:
    cd ~/octave-mcp
    python3 patch_plotting_tools.py

4 anchors independientes (imports, MODES, funcion compute_plotting_curves,
bloque de validate + nota), cada uno con assert count==1 para no aplicar
un parche a ciegas si el archivo cambio de forma inesperada. Backup
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
# Anchor A: imports -- agregar sys/json
# ---------------------------------------------------------------------------

OLD_IMPORTS = "from scipy.integrate import quad"
NEW_IMPORTS = "from scipy.integrate import quad\nimport sys\nimport json"

# ---------------------------------------------------------------------------
# Anchor B: MODES -- se deja igual, se agrega TOOL_SCHEMA a continuacion
# ---------------------------------------------------------------------------

OLD_MODES = '''MODES = [
    "parametric_curve",
    "cycloid_family",
    "curve_with_vectors",
    "validate",
]'''

NEW_MODES = '''MODES = [
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

# ---------------------------------------------------------------------------
# Anchor C: funcion compute_plotting_curves -- se elimina (reemplazada por run())
# ---------------------------------------------------------------------------

OLD_COMPUTE_FN = '''def compute_plotting_curves(mode="parametric_curve", **kwargs):
    if mode == "validate":
        return _validate_plotting_curves()
    if mode == "parametric_curve":
        return _parametric_curve(**kwargs)
    if mode == "cycloid_family":
        return _cycloid_family(**kwargs)
    if mode == "curve_with_vectors":
        return _curve_with_vectors(**kwargs)
    raise ValueError(f"mode desconocido: {mode!r}. Modos validos: {MODES}")'''

NEW_COMPUTE_FN = "# compute_plotting_curves() reemplazada por run() mas abajo (patron de auto-registro)"

# ---------------------------------------------------------------------------
# Anchor D: _validate_plotting_curves + nota de integracion -> run_self_test/run/_register
# ---------------------------------------------------------------------------

OLD_TAIL = '''def _validate_plotting_curves():
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
# --------------------------------------------------------------------------'''

NEW_TAIL = '''def run_self_test():
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
    else:
        raise ValueError(
            f"modo desconocido: {mode} "
            "(usar parametric_curve/cycloid_family/curve_with_vectors/self_test)"
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


_register()'''


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

    patched = apply_anchor(patched, OLD_IMPORTS, NEW_IMPORTS, "imports")
    patched = apply_anchor(patched, OLD_MODES, NEW_MODES, "MODES/TOOL_SCHEMA")
    patched = apply_anchor(patched, OLD_COMPUTE_FN, NEW_COMPUTE_FN, "compute_plotting_curves")
    patched = apply_anchor(patched, OLD_TAIL, NEW_TAIL, "validate/tail")

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

    print("\nListo. Ahora corre:")
    print("  python3 plotting_tools.py self_test")
    print("  python3 plotting_tools.py validate")


if __name__ == "__main__":
    main()
