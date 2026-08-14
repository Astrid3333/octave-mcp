#!/usr/bin/env python3
"""
ancestral_octave_tool.py — Expone ancestral.m como tool MCP que corre DENTRO
del motor de Octave. Diferencia clave vs ethnomath_tool.py / ancient_calculators_tool.py:
esos corren en Python puro y devuelven JSON ya calculado; esto ejecuta código
Octave real (via _run_octave del server), lo que permite:

  1) que el propio Octave sea el que "razona" con el método ancestral, y
  2) encadenarlo con cualquier otro cálculo Octave en el mismo script
     (ode45, eig, fft, etc.) pasando 'extra_octave' — útil por ejemplo para
     usar el pi de Arquímedes como semilla de una integral numérica, o el
     TCR como paso previo a un análisis de congruencias más grande.

Requiere que ancestral.m viva en el mismo directorio que server.py.
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
ANCESTRAL_M_PATH = os.path.join(_HERE, "ancestral.m")
ANCESTRAL2_M_PATH = os.path.join(_HERE, "ancestral2.m")

ANCESTRAL_OCTAVE_SCHEMA = {
    "name": "ancestral_octave",
    "description": (
        "Corre metodos de calculo ancestral (suanpan, TCR, vedico, pi de "
        "Arquimedes, quipu, Ifa binario, etak/navegacion, series de Madhava) "
        "como funciones Octave NATIVAS, dentro del mismo motor que "
        "ode45/eig/fft — no una simulacion Python aparte. Permite pasar "
        "'extra_octave' para componer el resultado con otro calculo en la "
        "misma sesion."
    ),
}

def build_octave_call(preset: str, params: dict, extra_octave: str = None) -> str:
    """Arma el script .m completo: carga ancestral.m, llama el preset,
    imprime el resultado como JSON (jsonencode), y opcionalmente corre
    extra_octave a continuación usando las mismas variables."""
    params = params or {}

    if preset == "suanpan_add":
        a, b = params.get("a", 0), params.get("b", 0)
        call = f"r = suanpan_add({a}, {b});"
    elif preset == "chinese_remainder":
        rem = params.get("remainders", [])
        mod = params.get("moduli", [])
        call = (
            f"sol = chinese_remainder({_oct_vec(rem)}, {_oct_vec(mod)}); "
            f"r = struct('solution', sol);"
        )
    elif preset == "vedic_multiply":
        a, b = params.get("a", 0), params.get("b", 0)
        call = f"r = vedic_multiply({a}, {b});"
    elif preset == "archimedes_pi":
        it = params.get("iterations", 8)
        call = (
            f"[lo, hi, hist] = archimedes_pi({it}); "
            f"r = struct('pi_lower', lo, 'pi_upper', hi, 'iterations', {it});"
        )
    elif preset == "quipu_encode":
        v = params.get("value", 0)
        call = f"cords = quipu_encode({v}); r = struct('cords', {{cords}});"
    elif preset == "ifa_cast":
        bits = params.get("bits", [0, 0, 0, 0, 0, 0, 0, 0])
        call = f"r = ifa_cast({_oct_vec(bits)});"
    elif preset == "ifa_cast_random":
        seed = params.get("seed", 1)
        call = f"r = ifa_cast_random({seed});"
    elif preset == "etak_deadreckoning":
        call = (
            f"r = etak_deadreckoning({params.get('speed_knots', 0)}, "
            f"{params.get('heading_deg', 0)}, {params.get('hours', 0)}, "
            f"{params.get('lat0', 0)}, {params.get('lon0', 0)});"
        )
    elif preset == "madhava_pi_series":
        call = f"r = madhava_pi_series({params.get('n_terms', 10)});"
    else:
        raise ValueError(f"preset desconocido: {preset}")

    script = f"""
source('{ANCESTRAL_M_PATH}');
source('{ANCESTRAL2_M_PATH}');
{call}
"""
    if extra_octave:
        script += f"\n% --- extra_octave: composicion en la misma sesion ---\n{extra_octave}\n"

    script += "\ndisp(jsonencode(r));\n"
    return script


def _oct_vec(pylist):
    return "[" + ", ".join(str(x) for x in pylist) + "]"


def compute_ancestral_octave(preset: str = None, params: dict = None, extra_octave: str = None, run_octave_fn=None, mode: str = None) -> dict:
    """run_octave_fn: la funcion run_octave(code) real de server.py -- toma
    codigo Octave y devuelve stdout+stderr concatenados como UN SOLO STRING
    (no un dict con returncode/stdout/stderr por separado)."""
    if run_octave_fn is None:
        return {"error": "run_octave_fn no fue provisto (bug de wiring en server.py)"}
    if preset is None:
        return {"error": "falta 'preset' (parametro requerido salvo mode='validate')"}
    params = params or {}
    extra_octave = extra_octave or ""
    script = build_octave_call(preset, params, extra_octave)
    raw = run_octave_fn(script)
    lines = [l for l in raw.splitlines() if l.strip()]
    if not lines:
        return {"error": "Octave no devolvio salida", "raw": raw, "script": script}
    json_line = lines[-1]
    try:
        return json.loads(json_line)
    except json.JSONDecodeError:
        return {"error": "no se pudo parsear JSON de la ultima linea de salida", "raw_output": raw, "script": script}
