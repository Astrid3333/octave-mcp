#!/usr/bin/env python3
"""
ancestral_octave_tool.py — Funciones ancestrales ejecutadas en Octave nativo
vía el mecanismo run_octave del servidor octave-mcp.

Las implementaciones viven en ancestral.m / ancestral2.m / ancestral3.m, que se
cargan con source() usando rutas absolutas: los .m son la única fuente de
verdad y este archivo no duplica ningún algoritmo.

El resultado se serializa con jsonencode (misma convención que
dynamic_kill_calculator_tool y math_error_analyzer_tool).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

_HERE = os.path.dirname(os.path.abspath(__file__))
ANCESTRAL_M_PATH = os.path.join(_HERE, "ancestral.m")
ANCESTRAL2_M_PATH = os.path.join(_HERE, "ancestral2.m")
ANCESTRAL3_M_PATH = os.path.join(_HERE, "ancestral3.m")

ANCESTRAL_OCTAVE_TOOL_SCHEMA: Dict[str, Any] = {
    "name": "ancestral_octave",
    "description": (
        "Ejecuta métodos de cálculo ancestral en Octave nativo (suanpan, TCR, "
        "vedic, pi de Arquímedes, Liu Hui, quipu, Ifá binario, etak, "
        "series de Madhava, babilónico, Al-Kashi, hebreo, cananeo, egipcio, "
        "maya, griego jónico, azteca, africano/yoruba). "
        "Corre dentro del motor de Octave vía run_octave."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["validate"],
                "description": (
                    "Si se pasa 'validate', corre 12 casos de referencia contra "
                    "valores analíticos conocidos y devuelve pass/fail "
                    "(no requiere 'preset'). Si se omite, se ejecuta el 'preset' "
                    "indicado normalmente."
                ),
            },
            "preset": {
                "type": "string",
                "enum": [
                    "suanpan_add", "chinese_remainder", "vedic_multiply",
                    "archimedes_pi", "liu_hui_pi", "quipu_encode", "ifa_cast",
                    "ifa_cast_random", "etak_deadreckoning", "madhava_pi_series",
                    "babylonian_sqrt2", "babylonian_reciprocal",
                    "sexagesimal_to_decimal", "decimal_to_sexagesimal",
                    "kashi_pi",
                    "hebrew_gematria", "hebrew_number_to_text",
                    "cananean_number_to_text",
                    "egyptian_unit_fraction", "egyptian_multiplication",
                    "maya_to_decimal", "decimal_to_maya",
                    "greek_ionic",
                    "azteca_number_to_text", "azteca_text_to_number",
                    "african_counting",
                ],
                "description": "Método ancestral a ejecutar. Requerido salvo cuando mode='validate'.",
            },
            "params": {
                "type": "object",
                "description": "Parámetros específicos del preset.",
            },
            "extra_octave": {
                "type": "string",
                "description": (
                    "Código Octave extra que se ejecuta en la misma sesión, "
                    "después del preset, con las mismas variables disponibles."
                ),
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


def _oct_list(pylist: List) -> str:
    return "[" + ", ".join(str(x) for x in pylist) + "]"


def _oct_str(value: Any) -> str:
    """Literal de cadena Octave seguro: duplica las comillas simples.
    Los params llegan de un cliente MCP y se interpolan dentro del script, así
    que sin esto un texto con ' rompe el script (o inyecta código Octave)."""
    return "'" + str(value).replace("'", "''") + "'"


def _build_call(preset: str, params: Dict) -> str:
    params = params or {}
    if preset == "suanpan_add":
        return f"r = suanpan_add({params.get('a', 0)}, {params.get('b', 0)});"
    if preset == "chinese_remainder":
        return (
            f"sol = chinese_remainder({_oct_list(params.get('remainders', []))}, "
            f"{_oct_list(params.get('moduli', []))}); "
            f"r = struct('solution', sol);"
        )
    if preset == "vedic_multiply":
        return f"r = vedic_multiply({params.get('a', 0)}, {params.get('b', 0)});"
    if preset == "archimedes_pi":
        return (
            f"[lo, hi, hist] = archimedes_pi({params.get('iterations', 8)}); "
            f"r = struct('pi_lower', lo, 'pi_upper', hi, 'iterations', {params.get('iterations', 8)});"
        )
    if preset == "liu_hui_pi":
        return f"r = liu_hui_pi({params.get('iterations', 10)}, {params.get('levels', 3)});"
    if preset == "quipu_encode":
        return f"cords = quipu_encode({params.get('value', 0)}); r = struct('cords', {{cords}});"
    if preset == "ifa_cast":
        return f"r = ifa_cast({_oct_list(params.get('bits', [0]*8))});"
    if preset == "ifa_cast_random":
        return f"r = ifa_cast_random({params.get('seed', 1)});"
    if preset == "etak_deadreckoning":
        return (
            f"r = etak_deadreckoning({params.get('speed_knots', 0)}, "
            f"{params.get('heading_deg', 0)}, {params.get('hours', 0)}, "
            f"{params.get('lat0', 0)}, {params.get('lon0', 0)});"
        )
    if preset == "madhava_pi_series":
        return f"r = madhava_pi_series({params.get('n_terms', 10)});"
    if preset == "babylonian_sqrt2":
        return f"r = babylonian_sqrt2({params.get('n_iter', 10)}, {params.get('x0', 1.0)});"
    if preset == "babylonian_reciprocal":
        return f"r = babylonian_reciprocal({params.get('n', 60)});"
    if preset == "sexagesimal_to_decimal":
        return f"s = sexagesimal_to_decimal({_oct_list(params.get('digits', [1, 24, 51, 10]))}); r = struct('decimal', s);"
    if preset == "decimal_to_sexagesimal":
        return (
            f"d = decimal_to_sexagesimal({params.get('x', 1.414213562373)}, "
            f"{params.get('n_digits', 5)}); r = struct('sexagesimal', d);"
        )
    if preset == "kashi_pi":
        return f"p = kashi_pi({params.get('n_digits', 16)}); r = struct('pi', p);"
    if preset == "hebrew_gematria":
        return f"v = hebrew_gematria({_oct_str(params.get('text', 'alef bet'))}); r = struct('gematria', v);"
    if preset == "hebrew_number_to_text":
        return f"t = hebrew_number_to_text({params.get('n', 2024)}); r = struct('text', t);"
    if preset == "cananean_number_to_text":
        return f"c = cananean_number_to_text({params.get('n', 2024)}); r = struct('text', c.text, 'places', c);"
    if preset == "egyptian_unit_fraction":
        return (
            f"t = egyptian_unit_fraction({params.get('n', 2)}, "
            f"{params.get('d', 3)}); r = struct('unit_terms', t);"
        )
    if preset == "egyptian_multiplication":
        return (
            f"m = egyptian_multiplication({params.get('a', 13)}, "
            f"{params.get('b', 12)}); r = struct('result', m.result, 'steps', m.steps);"
        )
    if preset == "maya_to_decimal":
        return f"m = maya_to_decimal({_oct_list(params.get('digits', [1, 0, 0]))}); r = struct('decimal', m);"
    if preset == "decimal_to_maya":
        return (
            f"d = decimal_to_maya({params.get('n', 400)}, "
            f"{params.get('n_positions', 3)}); r = struct('digits', d);"
        )
    if preset == "greek_ionic":
        return f"v = greek_ionic({_oct_str(params.get('text', 'alpha beta'))}); r = struct('value', v);"
    if preset == "azteca_number_to_text":
        return f"r = azteca_number_to_text({params.get('n', 2024)});"
    if preset == "azteca_text_to_number":
        return f"n = azteca_text_to_number({_oct_str(params.get('text', '•'))}); r = struct('decimal', n);"
    if preset == "african_counting":
        return f"r = african_counting({params.get('n', 42)}, {_oct_str(params.get('variant', 'yoruba'))});"
    raise ValueError(f"preset desconocido: {preset}")


def _extract_json(raw: str):
    """Devuelve el último objeto JSON parseable de la salida, recorriendo las
    líneas de última a primera. run_octave concatena stdout + stderr, así que
    los avisos de Octave pueden caer después del JSON."""
    for line in reversed([ln for ln in raw.splitlines() if ln.strip()]):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def _extract_octave_error(raw: str):
    """Primer mensaje de error de Octave en la salida.

    Sin esto, un error lanzado por el .m (p.ej. validación de parámetros)
    se pierde: no hay JSON que parsear y el cliente solo veria 'no se pudo
    parsear JSON', sin la causa real."""
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("error:"):
            return s[len("error:"):].strip()
    return None


def _source_block() -> str:
    """Carga ancestral.m / ancestral2.m / ancestral3.m con source() usando rutas
    absolutas: los .m son la única fuente de verdad y este módulo no duplica
    ningún algoritmo."""
    return "".join(
        f"source({_oct_str(path)});\n"
        for path in (ANCESTRAL_M_PATH, ANCESTRAL2_M_PATH, ANCESTRAL3_M_PATH)
    )


def _build_script(preset: str, params: Dict, extra_octave: str = "") -> str:
    """Script Octave completo: carga los .m, ejecuta el preset, corre
    extra_octave en la misma sesión y serializa r con jsonencode."""
    call = _build_call(preset, params)
    script = _source_block() + call + "\n"
    if extra_octave:
        script += f"\n% --- extra_octave: composicion en la misma sesion ---\n{extra_octave}\n"
    script += "\ndisp(jsonencode(r));\n"
    return script


def ancestral_octave(
    preset: str = None,
    params: Dict = None,
    mode: str = None,
    extra_octave: str = None,
    run_octave_fn=None,
) -> Dict[str, Any]:
    if run_octave_fn is None:
        from server import run_octave as run_octave_fn

    if mode == "validate":
        return _validate_ancestral_octave(run_octave_fn)
    if preset is None:
        return {"error": "falta 'preset' (requerido salvo mode='validate')"}
    params = params or {}
    try:
        script = _build_script(preset, params, extra_octave or "")
    except ValueError as exc:
        return {"error": str(exc)}
    raw = run_octave_fn(script)
    parsed = _extract_json(raw)
    if parsed is not None:
        return parsed
    octave_error = _extract_octave_error(raw)
    if octave_error:
        return {"error": octave_error, "raw_output": raw, "script": script}
    return {
        "error": "no se pudo parsear JSON en la salida de Octave",
        "raw_output": raw,
        "script": script,
    }


def _validate_ancestral_octave(run_octave_fn) -> Dict[str, Any]:
    """Corre 12 presets contra valores analíticos o de referencia conocidos.

    Se ejecutan sobre los .m reales (source + jsonencode), no sobre una copia
    embebida: si un .m cambia, el validate refleja el cambio real.

    Quedan fuera quipu_encode, ifa_cast, ifa_cast_random y etak_deadreckoning:
    no hay valor analítico de referencia con el que comparar, así que un check
    sobre ellos sería placebo.
    """
    import math

    def _call(preset, params):
        script = _build_script(preset, params)
        raw = run_octave_fn(script)
        return _extract_json(raw)

    checks = []

    r = _call("suanpan_add", {"a": 3, "b": 4})
    checks.append({"name": "suanpan_add(3,4)==7", "passed": r is not None and r.get("result") == 7, "got": r})

    r = _call("vedic_multiply", {"a": 6, "b": 7})
    checks.append({"name": "vedic_multiply(6,7)==42", "passed": r is not None and r.get("result") == 42, "got": r})

    r = _call("chinese_remainder", {"remainders": [2, 3, 2], "moduli": [3, 5, 7]})
    checks.append({"name": "chinese_remainder([2,3,2],[3,5,7])==23", "passed": r is not None and r.get("solution") == 23, "got": r})

    r4 = _call("archimedes_pi", {"iterations": 4})
    r8 = _call("archimedes_pi", {"iterations": 8})
    encloses = (
        r4 is not None and r8 is not None
        and r4.get("pi_lower", 0) <= math.pi <= r4.get("pi_upper", 0)
        and r8.get("pi_lower", 0) <= math.pi <= r8.get("pi_upper", 0)
    )
    checks.append({"name": "archimedes_pi encierra pi real en iter=4 y iter=8", "passed": encloses, "got": {"iter4": r4, "iter8": r8}})
    tightened = (
        r4 is not None and r8 is not None
        and (r8["pi_upper"] - r8["pi_lower"]) < (r4["pi_upper"] - r4["pi_lower"])
    )
    checks.append({"name": "archimedes_pi: cota mas angosta con mas iteraciones", "passed": tightened, "got": None})

    r = _call("liu_hui_pi", {"iterations": 10, "levels": 3})
    ok = (
        r is not None
        and abs(r.get("pi_liu_hui", 0) - math.pi) < 1e-12
        and abs(r.get("pi_liu_hui", 0) - math.pi) < abs(r.get("pi_plain", 0) - math.pi) / 1e3
    )
    checks.append({"name": "liu_hui_pi: Liu Hui (3 niveles) alcanza pi a <1e-12 y mejora >1000x al poligono simple", "passed": ok, "got": r})

    r = _call("madhava_pi_series", {"n_terms": 10})
    ok = (
        r is not None
        and r.get("error_corrected", 1) < r.get("error_basic", 0)
        and r.get("error_corrected", 1) < 0.01
    )
    checks.append({"name": "madhava_pi_series: correccion de Kerala reduce error real y converge <1%", "passed": ok, "got": r})

    r = _call("babylonian_sqrt2", {"n_iter": 5, "x0": 1.0})
    ok = r is not None and abs(r.get("sqrt2_decimal", 0) - math.sqrt(2)) < 1e-10
    checks.append({"name": "babylonian_sqrt2: converge a sqrt(2) en 5 iteraciones", "passed": ok, "got": r})

    r = _call("kashi_pi", {"n_digits": 16})
    ok = r is not None and abs(r.get("pi", 0) - math.pi) < 1e-12
    checks.append({"name": "kashi_pi: Al-Kashi pi a 16 digitos sexagesimales coincide con pi real", "passed": ok, "got": r})

    r = _call("egyptian_unit_fraction", {"n": 2, "d": 3})
    ok = r is not None and r.get("unit_terms") == [2, 6]
    checks.append({"name": "egyptian_unit_fraction: 2/3 = 1/2 + 1/6", "passed": ok, "got": r})

    r = _call("egyptian_multiplication", {"a": 13, "b": 12})
    ok = r is not None and r.get("result") == 156
    checks.append({"name": "egyptian_multiplication: 13 x 12 = 156", "passed": ok, "got": r})

    r = _call("greek_ionic", {"text": "alpha beta"})
    ok = r is not None and r.get("value") == 3
    checks.append({"name": "greek_ionic: alpha+beta = 1+2 = 3", "passed": ok, "got": r})

    return {
        "validation_passed": all(c["passed"] for c in checks),
        "checks": checks,
        "not_covered": [
            "quipu_encode", "ifa_cast", "ifa_cast_random", "etak_deadreckoning",
            "azteca_number_to_text", "azteca_text_to_number", "african_counting",
        ],
    }


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass


register_tool(
    name="ancestral_octave",
    schema=ANCESTRAL_OCTAVE_TOOL_SCHEMA,
    handler=lambda args: ancestral_octave(**args),
)

# Alias para compatibilidad con server.py legacy
compute_ancestral_octave = ancestral_octave