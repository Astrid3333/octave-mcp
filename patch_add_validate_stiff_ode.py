#!/usr/bin/env python3
"""
Agrega mode="validate" a integrate_stiff_ode en stiff_ode_tool.py.

Igual que hilbert_tool.py, esta tool ya usa el patron correcto en
server.py (importa STIFF_ODE_TOOL_SCHEMA directo, confirmado via grep en
la linea 208), asi que este patch alcanza solo con este archivo, sin
tocar server.py.

A diferencia de hilbert_tool.py, la firma de integrate_stiff_ode no tenia
**kwargs -- hay que agregarlo junto con mode.

Autochequeo con dos sistemas custom de solucion analitica exacta,
probando los dos solvers implicitos principales:
- decaimiento exponencial y'=-k*y (solver ode15s): y(t) = y0*exp(-k*t).
- oscilador armonico y1'=y2, y2'=-w^2*y1 (solver lsode): y1(t) = cos(w*t).
"""
import ast
import shutil
import sys
from datetime import datetime

TARGET = "stiff_ode_tool.py"

OLD_SIG = '''    octave_bin: str = "octave",
    timeout_s: int = 60,
) -> dict:'''

NEW_SIG = '''    octave_bin: str = "octave",
    timeout_s: int = 60,
    mode: str | None = None,
    **kwargs,
) -> dict:'''

OLD_BODY = '''    Returns:
        dict con t, y (lista de listas), solver usado, y metadatos.
    """
    if solver not in ("ode15s", "ode23s", "lsode"):'''

NEW_BODY = '''    Returns:
        dict con t, y (lista de listas), solver usado, y metadatos.
    """
    if mode == "validate":
        return _validate_stiff_ode(octave_bin=octave_bin, timeout_s=timeout_s)

    if solver not in ("ode15s", "ode23s", "lsode"):'''

OLD_SCHEMA_ANCHOR = '''STIFF_ODE_TOOL_SCHEMA = {'''

VALIDATE_FN = '''def _validate_stiff_ode(octave_bin: str = "octave", timeout_s: int = 60):
    """
    Autochequeo con dos sistemas custom de solucion analitica exacta,
    probando los dos solvers implicitos principales:
    - decaimiento exponencial y'=-k*y (solver ode15s): y(t) = y0*exp(-k*t).
    - oscilador armonico y1'=y2, y2'=-w^2*y1 (solver lsode): y1(t) = cos(w*t),
      con y0=[1,0].
    Ambos evaluados contra la formula cerrada en el ultimo punto de la
    malla de salida (que coincide exacto con tspan[1] via linspace).
    """
    import math

    checks = []
    tol = 0.01

    # --- decaimiento exponencial, ode15s ---
    k = 0.7
    y0_1 = 2.0
    tspan1 = [0.0, 3.0]
    r1 = integrate_stiff_ode(
        system="custom", custom_equations="-k*y(1)", custom_params={"k": k},
        y0=[y0_1], tspan=tspan1, solver="ode15s", n_output_points=50,
        octave_bin=octave_bin, timeout_s=timeout_s,
    )
    if "error" in r1:
        ok1, got1 = False, r1.get("error")
    else:
        t_final = r1["t"][-1]
        y_final = r1["y"][0][-1]
        expected = y0_1 * math.exp(-k * t_final)
        ok1 = abs(y_final - expected) < tol
        got1 = f"y_final={y_final:.6g} vs esperado={expected:.6g}"
    checks.append({
        "name": "custom y'=-0.7*y (ode15s): decaimiento exponencial vs formula cerrada y0*exp(-k*t)",
        "passed": ok1, "got": got1,
    })

    # --- oscilador armonico, lsode ---
    w = 2.0
    tspan2 = [0.0, 1.5]
    r2 = integrate_stiff_ode(
        system="custom", custom_equations="y(2); -w2*y(1)", custom_params={"w2": w ** 2},
        y0=[1.0, 0.0], tspan=tspan2, solver="lsode", n_output_points=50,
        octave_bin=octave_bin, timeout_s=timeout_s,
    )
    if "error" in r2:
        ok2, got2 = False, r2.get("error")
    else:
        t_final2 = r2["t"][-1]
        y_final2 = r2["y"][0][-1]
        expected2 = math.cos(w * t_final2)
        ok2 = abs(y_final2 - expected2) < tol
        got2 = f"y1_final={y_final2:.6g} vs esperado={expected2:.6g}"
    checks.append({
        "name": "custom oscilador armonico w=2 (lsode): y1(t) vs cos(w*t)",
        "passed": ok2, "got": got2,
    })

    return {"mode": "validate", "validation_passed": bool(all(c["passed"] for c in checks)), "checks": checks}


STIFF_ODE_TOOL_SCHEMA = {'''

OLD_SCHEMA_PROPS = '''            "abs_tol": {"type": "number", "default": 1e-8},
        },
        "required": [],
    },
}'''

NEW_SCHEMA_PROPS = '''            "abs_tol": {"type": "number", "default": 1e-8},
            "mode": {
                "type": "string",
                "enum": ["validate"],
                "description": "Si es 'validate', ejecuta el autochequeo interno (decaimiento exponencial vs ode15s, oscilador armonico vs lsode) e ignora el resto de los parametros.",
            },
        },
        "required": [],
    },
}'''


def apply(src, old, new, label):
    count = src.count(old)
    assert count == 1, f"[{label}] se esperaba 1 ocurrencia, se encontraron {count} -- revisar a mano."
    return src.replace(old, new, 1)


def main():
    with open(TARGET, encoding="utf-8") as f:
        src = f.read()

    backup = f"{TARGET}.bak.{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy(TARGET, backup)

    src = apply(src, OLD_SIG, NEW_SIG, "firma integrate_stiff_ode (agrega mode + **kwargs)")
    src = apply(src, OLD_BODY, NEW_BODY, "early return mode=='validate'")
    src = apply(src, OLD_SCHEMA_ANCHOR, VALIDATE_FN, "insercion de _validate_stiff_ode antes de STIFF_ODE_TOOL_SCHEMA")
    src = apply(src, OLD_SCHEMA_PROPS, NEW_SCHEMA_PROPS, "propiedad mode en STIFF_ODE_TOOL_SCHEMA")

    try:
        ast.parse(src)
    except SyntaxError as e:
        print(f"ERROR: el resultado no parsea como Python valido: {e}", file=sys.stderr)
        sys.exit(1)

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(src)

    print(f"Patch aplicado OK. Backup: {backup}")
    print("Confirmar con:")
    print('  python3 -c "from stiff_ode_tool import integrate_stiff_ode as c; import json; print(json.dumps(c(mode=\'validate\'), indent=2, ensure_ascii=False))"')
    print("Recordar: server.py importa STIFF_ODE_TOOL_SCHEMA directo (no hardcodeado), asi que no hace falta tocar server.py.")


if __name__ == "__main__":
    main()
