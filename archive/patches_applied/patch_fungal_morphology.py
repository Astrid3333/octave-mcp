#!/usr/bin/env python3
"""
patch_fungal_morphology.py

Migra fungal_morphology_tool.py del patron viejo
(compute_fungal_morphology(mode, **kwargs) + _validate_fungal_morphology())
al patron de auto-registro usado en vector_calculus_tool.py:
  TOOL_SCHEMA + run(mode, params=None) + run_self_test() + _register()

Uso:
    cd ~/octave-mcp
    python3 patch_fungal_morphology.py

Hace backup timestampeado antes de escribir, valida con ast.parse +
py_compile, y usa asserts count==1 sobre cada anchor para no aplicar
un parche a ciegas si el archivo ya cambio de forma inesperada.
"""

import ast
import py_compile
import shutil
import sys
import time
from pathlib import Path

TARGET = Path("fungal_morphology_tool.py")

# ---------------------------------------------------------------------------
# Anchors: bloques exactos a reemplazar. Deben aparecer exactamente 1 vez.
# ---------------------------------------------------------------------------

OLD_HEADER = '''import numpy as np

MODES = [
    "pileus_profile",
    "stipe_frustum",
    "gill_doubling",
    "pore_packing",
    "validate",
]


def compute_fungal_morphology(mode="pileus_profile", **kwargs):
    if mode == "validate":
        return _validate_fungal_morphology()
    if mode == "pileus_profile":
        return _pileus_profile(**kwargs)
    if mode == "stipe_frustum":
        return _stipe_frustum(**kwargs)
    if mode == "gill_doubling":
        return _gill_doubling(**kwargs)
    if mode == "pore_packing":
        return _pore_packing(**kwargs)
    raise ValueError(f"mode desconocido: {mode!r}. Modos validos: {MODES}")'''

NEW_HEADER = '''import numpy as np
import sys
import json

TOOL_SCHEMA = {
    "name": "fungal_morphology_tool",
    "description": (
        "Matematica de formas del cuerpo fungico (carpoforo): perfil del "
        "pileo (sombrero) como domo generalizado, geometria del estipite "
        "(frustum), doblamiento jerarquico de laminillas, y empaquetamiento "
        "hexagonal de poros en superficie. Modos: pileus_profile, "
        "stipe_frustum, gill_doubling, pore_packing, self_test, validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["pileus_profile", "stipe_frustum", "gill_doubling",
                         "pore_packing", "self_test", "validate"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "R": {"type": "number", "description": "radio del pileo (pileus_profile)"},
                    "h": {"type": "number", "description": "altura del domo (pileus_profile)"},
                    "p": {"type": "number", "description": "exponente radial (pileus_profile)"},
                    "q": {"type": "number", "description": "exponente de altura (pileus_profile)"},
                    "n_r": {"type": "integer", "description": "puntos radiales (pileus_profile)"},
                    "r_top": {"type": "number", "description": "radio superior del estipite (stipe_frustum)"},
                    "r_bottom": {"type": "number", "description": "radio inferior del estipite (stipe_frustum)"},
                    "H": {"type": "number", "description": "altura del estipite (stipe_frustum)"},
                    "n_z": {"type": "integer", "description": "puntos axiales (stipe_frustum)"},
                    "R_cap": {"type": "number", "description": "radio del sombrero (gill_doubling)"},
                    "r_stipe": {"type": "number", "description": "radio del estipite (gill_doubling)"},
                    "s_max": {"type": "number", "description": "espaciado angular maximo (gill_doubling)"},
                    "N0": {"type": "integer", "description": "n gills iniciales (gill_doubling)"},
                    "max_orders": {"type": "integer", "description": "ordenes maximos de duplicacion (gill_doubling)"},
                    "pore_diameter": {"type": "number", "description": "diametro de poro (pore_packing)"},
                    "domain_side": {"type": "number", "description": "lado del dominio (pore_packing)"},
                    "n_cells_side": {"type": "integer", "description": "celdas por lado (pore_packing)"},
                },
            },
        },
        "required": ["mode"],
    },
}'''

OLD_TAIL_MARKER_START = "# --------------------------------------------------------------------------\n# 5. Validate\n# --------------------------------------------------------------------------"

OLD_TAIL = '''# --------------------------------------------------------------------------
# 5. Validate
# --------------------------------------------------------------------------

def _validate_fungal_morphology():
    checks = []
    all_passed = True

    # -- pileus_profile: caso hemisferio exacto (p=q=2, h=R) --
    R = 5.0
    out = _pileus_profile(R=R, h=R, p=2.0, q=2.0, n_r=2000)
    area_exact = 2.0 * np.pi * R ** 2
    vol_exact = (2.0 / 3.0) * np.pi * R ** 3
    area_err = abs(out["surface_area_m2"] - area_exact) / area_exact
    vol_err = abs(out["volume_m3"] - vol_exact) / vol_exact
    tol = 1e-3
    passed = area_err < tol and vol_err < tol
    all_passed &= passed
    checks.append({
        "name": "pileus_profile_vs_hemisphere_closed_form",
        "passed": bool(passed),
        "area_relative_error": area_err,
        "volume_relative_error": vol_err,
        "tolerance": tol,
    })

    # -- stipe_frustum: numerico vs formula cerrada --
    out = _stipe_frustum(r_top=0.5, r_bottom=0.8, H=6.0, n_z=2000)
    tol_v = 1e-4
    tol_a = 1e-4
    passed = (out["volume_abs_error"] < tol_v and out["area_abs_error"] < tol_a)
    all_passed &= passed
    checks.append({
        "name": "stipe_frustum_numeric_vs_closed_form",
        "passed": bool(passed),
        "volume_abs_error": out["volume_abs_error"],
        "area_abs_error": out["area_abs_error"],
    })

    # -- gill_doubling: auto-consistencia (espaciado respetado y duplicacion necesaria) --
    out = _gill_doubling(R_cap=4.0, r_stipe=0.3, s_max=0.5, N0=4)
    passed = (out["constraint_satisfied"] and out["last_doubling_was_necessary"])
    all_passed &= passed
    checks.append({
        "name": "gill_doubling_self_consistency",
        "passed": bool(passed),
        "spacing_at_margin_m": out["spacing_at_margin_m"],
        "spacing_without_last_doubling_m": out["spacing_without_last_doubling_m"],
        "s_max": out["s_max"],
    })

    # -- pore_packing: empirico vs fraccion exacta pi/(2*sqrt(3)) --
    # n_cells_side grande: el error por efecto de borde decae ~O(1/n)
    # (circulos completos contados cerca del limite del dominio sobreestiman
    # la fraccion), confirmado empiricamente barriendo n=40..200 antes de
    # fijar este valor -- con n=200 el error cae a ~2e-4, tolerancia comoda.
    out = _pore_packing(pore_diameter=0.2, n_cells_side=200)
    tol = 0.01
    passed = out["abs_error"] < tol
    all_passed &= passed
    checks.append({
        "name": "pore_packing_vs_hexagonal_exact_fraction",
        "passed": bool(passed),
        "packing_fraction_empirical": out["packing_fraction_empirical"],
        "packing_fraction_exact": out["packing_fraction_exact"],
        "abs_error": out["abs_error"],
        "tolerance": tol,
    })

    return {
        "mode": "validate",
        "validation_passed": bool(all_passed),
        "checks": checks,
    }


# --------------------------------------------------------------------------
# NOTA DE INTEGRACION: mismo patron que mycelial_network_tool.py --
# schema con mode enum (MODES incluyendo "validate") + elif tool_name==
# "fungal_morphology" en el dispatch de server.py. Firma plana / mode
# estandar => no requiere entradas en ALTERNATE_VALIDATE_MODE /
# ALTERNATE_VALIDATE_PARAM_NAME / FLAT_SIGNATURE_TOOLS.
# --------------------------------------------------------------------------'''

NEW_TAIL = '''# --------------------------------------------------------------------------
# 5. self_test / run / registro
# --------------------------------------------------------------------------

def run_self_test():
    checks = []

    def check(name, cond, detail=""):
        checks.append({"name": name, "passed": bool(cond), "detail": detail})

    R = 5.0
    out = _pileus_profile(R=R, h=R, p=2.0, q=2.0, n_r=2000)
    area_exact = 2.0 * np.pi * R ** 2
    vol_exact = (2.0 / 3.0) * np.pi * R ** 3
    area_err = abs(out["surface_area_m2"] - area_exact) / area_exact
    vol_err = abs(out["volume_m3"] - vol_exact) / vol_exact
    check("pileus_profile vs hemisferio (area)", area_err < 1e-3, f"rel err={area_err:.2e}")
    check("pileus_profile vs hemisferio (volumen)", vol_err < 1e-3, f"rel err={vol_err:.2e}")

    out = _stipe_frustum(r_top=0.5, r_bottom=0.8, H=6.0, n_z=2000)
    check("stipe_frustum: volumen numerico vs cerrado",
          out["volume_abs_error"] < 1e-4, f"err={out['volume_abs_error']:.2e}")
    check("stipe_frustum: area numerica vs cerrada",
          out["area_abs_error"] < 1e-4, f"err={out['area_abs_error']:.2e}")

    out = _gill_doubling(R_cap=4.0, r_stipe=0.3, s_max=0.5, N0=4)
    check("gill_doubling: auto-consistencia",
          out["constraint_satisfied"] and out["last_doubling_was_necessary"],
          f"spacing_margin={out['spacing_at_margin_m']:.4f}")

    out = _pore_packing(pore_diameter=0.2, n_cells_side=200)
    check("pore_packing vs fraccion hexagonal exacta",
          out["abs_error"] < 0.01, f"err={out['abs_error']:.2e}")

    total = len(checks)
    passed = sum(1 for c in checks if c["passed"])
    return {"total": total, "passed": passed, "all_passed": passed == total, "checks": checks}


def run(mode, params=None):
    params = params or {}
    if mode == "validate":
        r = run_self_test()
        return {"checks": r["checks"], "validation_passed": r["all_passed"], "n_checks": r["total"]}
    elif mode == "self_test":
        return run_self_test()
    elif mode == "pileus_profile":
        return _pileus_profile(**params)
    elif mode == "stipe_frustum":
        return _stipe_frustum(**params)
    elif mode == "gill_doubling":
        return _gill_doubling(**params)
    elif mode == "pore_packing":
        return _pore_packing(**params)
    else:
        raise ValueError(
            f"modo desconocido: {mode} "
            "(usar pileus_profile/stipe_frustum/gill_doubling/pore_packing/self_test)"
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

        tool_registry.register_tool("fungal_morphology_tool", TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()'''


def main():
    if not TARGET.exists():
        print(f"ERROR: no se encontro {TARGET} en el directorio actual ({Path.cwd()})")
        sys.exit(1)

    original = TARGET.read_text(encoding="utf-8")

    # --- validar que los anchors existen exactamente 1 vez ---
    n_header = original.count(OLD_HEADER)
    n_tail = original.count(OLD_TAIL)

    if n_header != 1:
        print(f"ERROR: anchor de header encontrado {n_header} veces (se esperaba 1).")
        print("El archivo puede haber cambiado desde que se genero este patch.")
        sys.exit(1)

    if n_tail != 1:
        print(f"ERROR: anchor de tail (_validate_fungal_morphology + nota) encontrado {n_tail} veces (se esperaba 1).")
        sys.exit(1)

    assert n_header == 1
    assert n_tail == 1

    patched = original.replace(OLD_HEADER, NEW_HEADER, 1)
    patched = patched.replace(OLD_TAIL, NEW_TAIL, 1)

    # --- validar sintaxis antes de escribir ---
    try:
        ast.parse(patched)
    except SyntaxError as e:
        print(f"ERROR: el resultado parcheado no es sintacticamente valido: {e}")
        sys.exit(1)

    # --- backup timestampeado ---
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_path = TARGET.with_name(f"{TARGET.stem}.py.bak_{timestamp}")
    shutil.copy2(TARGET, backup_path)
    print(f"Backup creado: {backup_path}")

    # --- escribir el archivo parcheado ---
    TARGET.write_text(patched, encoding="utf-8")
    print(f"{TARGET} parcheado OK.")

    # --- validar con py_compile tambien ---
    try:
        py_compile.compile(str(TARGET), doraise=True)
        print("py_compile OK.")
    except py_compile.PyCompileError as e:
        print(f"ERROR en py_compile tras escribir: {e}")
        print(f"Restaurando backup desde {backup_path}...")
        shutil.copy2(backup_path, TARGET)
        sys.exit(1)

    print("\nListo. Ahora corre:")
    print("  python3 fungal_morphology_tool.py self_test")
    print("  python3 fungal_morphology_tool.py validate")


if __name__ == "__main__":
    main()
