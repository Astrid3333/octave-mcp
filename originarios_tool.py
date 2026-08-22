#!/usr/bin/env python3
"""
originarios_tool.py — Sistemas de numeracion de pueblos originarios de Chile
y la region andina: mapuche y aimara. Elegidos porque tienen reglas
aritmeticas explicitas y bien documentadas (a diferencia de otros sistemas
de conteo orales de la region, donde no hay suficiente documentacion
academica como para reconstruir un algoritmo sin inventar).

Presets:
  mapuche_numeral  — sistema decimal mapuche (rakin), oral, sin simbolos.
                      Regla documentada: una palabra a la DERECHA de mari
                      (10), pataka (100) o warangka (1000) SUMA su valor;
                      una palabra a la IZQUIERDA MULTIPLICA. Ej.: "kechu
                      pataka küla mari küla" = 5*100 + 3*10 + 3 = 533.
  aymara_numeral    — sistema decimal aimara moderno (con influencia
                      quechua en varios terminos), con el sufijo -ni
                      marcando la unidad final tras "tunka" (10). Incluye
                      nota sobre el vestigio quinario documentado en
                      paqallqu (2+5) y kimsaqallqu (3+5) para 7 y 8 -- un
                      fosil linguistico de un sistema base-5 anterior, NO
                      un sistema aritmetico activo reconstruible.
"""

ORIGINARIOS_SCHEMA = {
    "name": "compute_originarios",
    "description": (
        "Sistemas de numeracion de pueblos originarios: mapuche_numeral "
        "(rakin, decimal aditivo-multiplicativo oral) y aymara_numeral "
        "(decimal con sufijo -ni, mas nota sobre el vestigio quinario en "
        "paqallqu/kimsaqallqu)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "preset": {"type": "string", "enum": ["mapuche_numeral", "aymara_numeral", "validate"]},
            "params": {"type": "object"},
        },
        "required": ["preset"],
    },
}

# ---------------------------------------------------------------------------
# MAPUCHE (Mapudungun) — sistema decimal, aditivo a la derecha / multiplicativo
# a la izquierda de mari/pataka/warangka
# ---------------------------------------------------------------------------
_MAPUCHE_UNITS = {1: "kiñe", 2: "epu", 3: "küla", 4: "meli", 5: "kechu",
                  6: "kayu", 7: "regle", 8: "pura", 9: "aylla"}
_MAPUCHE_UNITS_INV = {v: k for k, v in _MAPUCHE_UNITS.items()}
_MAPUCHE_SCALES = [("warangka", 1000), ("pataka", 100), ("mari", 10)]
_MAPUCHE_SCALE_VALUES = {name: val for name, val in _MAPUCHE_SCALES}


def _mapuche_encode(n):
    if not (1 <= n <= 9999):
        return {"error": "rango soportado: 1-9999"}
    remaining = n
    parts = []
    for name, val in _MAPUCHE_SCALES:
        d = remaining // val
        if d > 0:
            if d > 1:
                parts.append(_MAPUCHE_UNITS[d])
            parts.append(name)
            remaining -= d * val
    if remaining > 0:
        parts.append(_MAPUCHE_UNITS[remaining])
    return {"number": n, "words": parts, "phrase": " ".join(parts)}


def _mapuche_decode(words):
    total = 0
    i = 0
    while i < len(words):
        w = words[i]
        if w in _MAPUCHE_UNITS_INV and i + 1 < len(words) and words[i + 1] in _MAPUCHE_SCALE_VALUES:
            total += _MAPUCHE_UNITS_INV[w] * _MAPUCHE_SCALE_VALUES[words[i + 1]]
            i += 2
        elif w in _MAPUCHE_SCALE_VALUES:
            total += _MAPUCHE_SCALE_VALUES[w]
            i += 1
        elif w in _MAPUCHE_UNITS_INV:
            total += _MAPUCHE_UNITS_INV[w]
            i += 1
        else:
            return {"error": f"palabra desconocida: {w}"}
    return {"words": words, "value": total}


def compute_mapuche_numeral(mode="encode", number=None, words=None):
    if mode == "encode":
        if number is None:
            return {"error": "mode='encode' requiere 'number'"}
        enc = _mapuche_encode(number)
        if "phrase" in enc:
            dec = _mapuche_decode(enc["words"])
            enc["roundtrip_check"] = dec.get("value") == number
        return enc
    elif mode == "decode":
        if not words:
            return {"error": "mode='decode' requiere 'words' (lista)"}
        return _mapuche_decode(words)
    else:
        return {"error": f"mode desconocido: {mode}"}


# ---------------------------------------------------------------------------
# AYMARA — sistema decimal moderno, sufijo -ni en la unidad final tras tunka.
# Formas contraidas ma/pa se usan como multiplicador de tunka para 1 y 2
# (documentado); el resto de multiplicadores usa la forma plena.
# ---------------------------------------------------------------------------
_AYMARA_UNITS = {1: "maya", 2: "paya", 3: "kimsa", 4: "pusi", 5: "phisqa",
                 6: "suxta", 7: "paqallqu", 8: "kimsaqallqu", 9: "llätunka"}
_AYMARA_UNITS_INV = {v: k for k, v in _AYMARA_UNITS.items()}
_AYMARA_TENS_MULT_OVERRIDE = {1: "mä", 2: "pä"}
_AYMARA_TENS_MULT_INV = {v: k for k, v in _AYMARA_TENS_MULT_OVERRIDE.items()}
_AYMARA_SCALES = [("waranqa", 1000), ("pataka", 100)]
_AYMARA_SCALE_VALUES = {name: val for name, val in _AYMARA_SCALES}

_QUINARY_VESTIGE_NOTE = (
    "Vestigio documentado de un sistema quinario anterior: paqallqu (7) "
    "proviene historicamente de 'paya qallqu' (2+5) y kimsaqallqu (8) de "
    "'kimsa qallqu' (3+5), donde qallqu era la palabra ancestral para 5 "
    "-- fosil linguistico, no una base aritmetica activa reconstruible "
    "hoy con la documentacion disponible."
)


def _aymara_encode(n):
    if not (1 <= n <= 9999):
        return {"error": "rango soportado: 1-9999"}
    remaining = n
    parts = []
    for name, val in _AYMARA_SCALES:
        d = remaining // val
        if d > 0:
            if d > 1:
                parts.append(_AYMARA_UNITS[d])
            parts.append(name)
            remaining -= d * val

    tens_digit = remaining // 10
    units_digit = remaining % 10

    if tens_digit == 1:
        parts.append("tunka")
    elif tens_digit > 1:
        parts.append(_AYMARA_TENS_MULT_OVERRIDE.get(tens_digit, _AYMARA_UNITS[tens_digit]))
        parts.append("tunka")

    if units_digit > 0:
        if tens_digit > 0:
            parts.append(_AYMARA_UNITS[units_digit] + "ni")
        else:
            parts.append(_AYMARA_UNITS[units_digit])

    return {"number": n, "words": parts, "phrase": " ".join(parts)}


def _aymara_decode(words):
    total = 0
    i = 0
    while i < len(words):
        w = words[i]
        if w in _AYMARA_UNITS_INV and i + 1 < len(words) and words[i + 1] in _AYMARA_SCALE_VALUES:
            total += _AYMARA_UNITS_INV[w] * _AYMARA_SCALE_VALUES[words[i + 1]]
            i += 2
        elif w in _AYMARA_SCALE_VALUES:
            total += _AYMARA_SCALE_VALUES[w]
            i += 1
        elif w == "tunka":
            total += 10
            i += 1
        elif w in _AYMARA_TENS_MULT_INV and i + 1 < len(words) and words[i + 1] == "tunka":
            total += _AYMARA_TENS_MULT_INV[w] * 10
            i += 2
        elif w in _AYMARA_UNITS_INV and i + 1 < len(words) and words[i + 1] == "tunka":
            total += _AYMARA_UNITS_INV[w] * 10
            i += 2
        elif w.endswith("ni") and w[:-2] in _AYMARA_UNITS_INV:
            total += _AYMARA_UNITS_INV[w[:-2]]
            i += 1
        elif w in _AYMARA_UNITS_INV:
            total += _AYMARA_UNITS_INV[w]
            i += 1
        else:
            return {"error": f"palabra desconocida: {w}"}
    return {"words": words, "value": total}


def compute_aymara_numeral(mode="encode", number=None, words=None):
    if mode == "encode":
        if number is None:
            return {"error": "mode='encode' requiere 'number'"}
        enc = _aymara_encode(number)
        if "phrase" in enc:
            dec = _aymara_decode(enc["words"])
            enc["roundtrip_check"] = dec.get("value") == number
            enc["quinary_vestige_note"] = _QUINARY_VESTIGE_NOTE
        return enc
    elif mode == "decode":
        if not words:
            return {"error": "mode='decode' requiere 'words'"}
        return _aymara_decode(words)
    else:
        return {"error": f"mode desconocido: {mode}"}


def _validate_originarios():
    """Checks apoyados en roundtrip_check interno + valores concretos
    verificados por corrida real (no inventados)."""
    checks = []

    # --- mapuche: n=1, caso trivial sin escalas, phrase exacta ---
    m1 = compute_mapuche_numeral(mode="encode", number=1)
    checks.append({
        "name": "mapuche_n1_phrase_exacta_kine",
        "phrase": m1.get("phrase"),
        "passed": bool(m1.get("phrase") == "kiñe" and m1.get("roundtrip_check") is True),
    })

    # --- mapuche: n=1234, usa las 3 escalas, roundtrip ok ---
    m2 = compute_mapuche_numeral(mode="encode", number=1234)
    checks.append({
        "name": "mapuche_n1234_usa_3_escalas_y_roundtrip_ok",
        "words": m2.get("words"),
        "passed": bool(m2.get("roundtrip_check") is True
                        and "warangka" in m2.get("words", [])
                        and "pataka" in m2.get("words", [])
                        and "mari" in m2.get("words", [])),
    })

    # --- mapuche: fuera de rango -> error estructurado, no crash ---
    m3 = compute_mapuche_numeral(mode="encode", number=10000)
    checks.append({
        "name": "mapuche_fuera_de_rango_da_error_no_crash",
        "passed": bool(isinstance(m3, dict) and "error" in m3),
    })

    # --- aymara: n=21, forma contraida 'pä' (tens_digit=2 dispara override) ---
    a1 = compute_aymara_numeral(mode="encode", number=21)
    checks.append({
        "name": "aymara_n21_forma_contraida_pa",
        "words": a1.get("words"),
        "passed": bool(a1.get("words") == ["pä", "tunka", "mayani"]
                        and a1.get("roundtrip_check") is True),
    })

    # --- aymara: n=41, forma plena 'pusi' (tens_digit=4, NO dispara override) ---
    a2 = compute_aymara_numeral(mode="encode", number=41)
    checks.append({
        "name": "aymara_n41_forma_plena_pusi_no_contraida",
        "words": a2.get("words"),
        "passed": bool(a2.get("words") == ["pusi", "tunka", "mayani"]
                        and a2.get("roundtrip_check") is True),
    })

    # --- aymara: n=347, centena+decena+unidad con sufijo -ni ---
    a3 = compute_aymara_numeral(mode="encode", number=347)
    checks.append({
        "name": "aymara_n347_centena_decena_unidad_sufijo_ni",
        "words": a3.get("words"),
        "passed": bool(a3.get("words") == ["kimsa", "pataka", "pusi", "tunka", "paqallquni"]
                        and a3.get("roundtrip_check") is True),
    })

    # --- aymara: fuera de rango -> error estructurado, no crash ---
    a4 = compute_aymara_numeral(mode="encode", number=10000)
    checks.append({
        "name": "aymara_fuera_de_rango_da_error_no_crash",
        "passed": bool(isinstance(a4, dict) and "error" in a4),
    })

    # --- preset desconocido -> error estructurado, no ValueError ---
    unk = compute_originarios("preset_inexistente")
    checks.append({
        "name": "preset_desconocido_devuelve_error",
        "passed": bool(isinstance(unk, dict) and "error" in unk),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed, "n_checks": len(checks)}


def compute_originarios(preset, params=None):
    params = params or {}
    if preset == "validate":
        return _validate_originarios()
    if preset == "mapuche_numeral":
        return compute_mapuche_numeral(**params)
    elif preset == "aymara_numeral":
        return compute_aymara_numeral(**params)
    else:
        return {"error": f"preset desconocido: {preset}"}

try:
    from tool_registry import register_tool
    register_tool(
        name="originarios",
        schema={**ORIGINARIOS_SCHEMA, "name": "originarios"},
        handler=lambda args: compute_originarios(**args),
    )
except ImportError:
    pass

