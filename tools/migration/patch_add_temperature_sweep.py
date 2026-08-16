#!/usr/bin/env python3
"""
patch_add_temperature_sweep.py (v2 -- corregido contra grep real)

Correcciones vs v1:
  - dispatcher real: compute_statmech_partition(mode, params=None)
    (no compute_statmech_partition_tool)
  - modos reales: "two_level_system", "quantum_harmonic_oscillator",
    "ideal_gas_translational" -> _two_level, _qho, _ideal_gas
  - workspace real: workspace_tool.save_run(run_id, data, meta=None)
    (no compute_workspace_save)

Agrega el modo temperature_sweep a statmech_partition_tool.py:
  1. Inserta _linspace() y _temperature_sweep() antes del dispatcher.
  2. Agrega el elif "temperature_sweep" justo despues del elif de
     "ideal_gas_translational" en el dispatcher (busca ese bloque
     como texto literal -- si no aparece exactamente una vez, ABORTA
     sin tocar nada y pide el grep real).
  3. Intenta agregar "temperature_sweep" al enum de "mode" del schema
     (best-effort: si el patron no matchea, avisa pero NO aborta el
     resto -- la funcion queda operativa igual, el schema se puede
     ajustar a mano despues).
  4. Valida con ast.parse() antes de escribir. Si no parsea, ABORTA
     sin escribir nada.

Uso:
    python3 patch_add_temperature_sweep.py --dry-run
    python3 patch_add_temperature_sweep.py
"""
import ast
import re
import shutil
import sys

PATH = "statmech_partition_tool.py"

NEW_FUNCTIONS = '''

def _linspace(a, b, n):
    if n <= 1:
        return [a]
    step = (b - a) / (n - 1)
    return [a + i * step for i in range(n)]


def _temperature_sweep(params):
    """
    Barrido de T para uno de los tres sistemas, reusando las mismas
    funciones puntuales ya validadas (no reimplementa la fisica).
    Escala log por defecto -- T baja es donde mas resolucion hace
    falta. Si se pasa run_id, guarda T/U/F/S/Cv en el workspace
    (via workspace_tool.save_run) para graficar con plot_tool.
    """
    system = params.get("system", "two_level_system")
    T_min = params.get("T_min", 0.01)
    T_max = params.get("T_max", 10.0)
    n_points = params.get("n_points", 50)
    log_scale = params.get("log_scale", True)
    run_id = params.get("run_id")

    if T_min <= 0:
        raise ValueError("T_min debe ser > 0 (T=0 es singular para S y F)")
    if T_max <= T_min:
        raise ValueError("T_max debe ser > T_min")

    dispatch = {
        "two_level_system": _two_level,
        "quantum_harmonic_oscillator": _qho,
        "ideal_gas_translational": _ideal_gas,
    }
    if system not in dispatch:
        raise ValueError(f"system debe ser uno de {list(dispatch.keys())}")
    fn = dispatch[system]

    Ts = ([math.exp(x) for x in _linspace(math.log(T_min), math.log(T_max), n_points)]
          if log_scale else _linspace(T_min, T_max, n_points))

    U, F, S, Cv, Z = [], [], [], [], []
    for T in Ts:
        p = dict(params)
        p["T"] = T
        r = fn(p)
        U.append(r["U"]); F.append(r["F"]); S.append(r["S"]); Cv.append(r["Cv"])
        Z.append(r.get("Z1", r.get("Z")))

    result = {"system": system, "T": Ts, "U": U, "F": F, "S": S, "Cv": Cv, "Z": Z, "n_points": n_points}

    if run_id:
        try:
            from workspace_tool import save_run
            save_run(run_id, {"T": Ts, "U": U, "F": F, "S": S, "Cv": Cv},
                      {"tool": "statmech_partition_tool", "mode": "temperature_sweep", "system": system})
            result["workspace_saved"] = True
        except Exception as e:
            result["workspace_saved"] = False
            result["workspace_save_error"] = str(e)

    return result

'''

DISPATCHER_ANCHOR = "def compute_statmech_partition(mode, params=None):"
IDEAL_GAS_ELIF = '    elif mode == "ideal_gas_translational":\n        return _ideal_gas(params)\n'
NEW_ELIF = '    elif mode == "temperature_sweep":\n        return _temperature_sweep(params)\n'
MODE_ENUM_PATTERN = re.compile(r'("mode"\s*:\s*\{\s*"type"\s*:\s*"string"\s*,\s*"enum"\s*:\s*\[)([^\]]*)(\])')


def main():
    dry_run = "--dry-run" in sys.argv
    with open(PATH) as f:
        src = f.read()

    if "_temperature_sweep" in src:
        print("Ya existe _temperature_sweep -- no se aplica de nuevo.")
        return

    idx = src.find(DISPATCHER_ANCHOR)
    if idx == -1:
        print(f"ABORTA: no encontre '{DISPATCHER_ANCHOR}' tal cual. "
              f"Pegame 'grep -n \"^def compute_statmech\" {PATH}' y ajusto.")
        return

    n_elif = src.count(IDEAL_GAS_ELIF)
    if n_elif != 1:
        print(f"ABORTA: el bloque elif de ideal_gas_translational aparecio {n_elif} veces "
              f"(esperaba 1) con el formato exacto que asumo. Pegame "
              f"'grep -n \"ideal_gas_translational\" -A2 {PATH}' y ajusto el texto literal.")
        return

    new_src = src[:idx] + NEW_FUNCTIONS.strip("\n") + "\n\n\n" + src[idx:]
    new_src = new_src.replace(IDEAL_GAS_ELIF, IDEAL_GAS_ELIF + NEW_ELIF, 1)

    schema_touched = False
    m = MODE_ENUM_PATTERN.search(new_src)
    if m and "temperature_sweep" not in m.group(2):
        new_enum = m.group(2).rstrip().rstrip(",") + ', "temperature_sweep"'
        new_src = new_src[:m.start()] + m.group(1) + new_enum + m.group(3) + new_src[m.end():]
        schema_touched = True
    elif not m:
        print("AVISO (no aborta): no encontre el enum de 'mode' del schema con el patron "
              "esperado -- la funcion queda operativa via tool_registry igual, pero agregar "
              "'temperature_sweep' al enum del schema a mano despues, si el schema lo valida.")

    try:
        ast.parse(new_src)
    except SyntaxError as e:
        print(f"ABORTA: no parsea como Python valido: {e}")
        return

    if dry_run:
        print(f"[DRY] {PATH}: {len(src)} -> {len(new_src)} caracteres. "
              f"elif insertado OK. schema enum tocado: {schema_touched}. ast.parse() OK.")
        return

    shutil.copy(PATH, PATH + ".bak")
    with open(PATH, "w") as f:
        f.write(new_src)
    print(f"Aplicado OK. schema enum tocado: {schema_touched}. Backup en {PATH}.bak")


if __name__ == "__main__":
    main()
