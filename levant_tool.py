#!/usr/bin/env python3
"""
levant_tool.py — Sistemas matematicos de Canaan y Juda/Israel.

Presets:
  hebrew_molad             — calculo exacto del molad (conjuncion media de
                              la luna) de Tishrei para cualquier anio del
                              calendario hebreo, via el algoritmo fijo
                              codificado por Hillel II (s. IV d.C.): ciclo
                              metonico de 19 anios (7 bisiestos), mes medio
                              de 29d 12h 793 chalakim, molad tohu = BaHaRaD
                              (lunes, 5h, 204 chalakim). NO implementa las
                              4 dehiyyot (reglas de posposicion de Rosh
                              Hashaná) -- solo el molad medio y el anio
                              bisiesto, que es la parte puramente aritmetica.
  hebrew_gematria           — valor numerico de palabras hebreas (mispar
                              hejrachi, cada letra = un valor) y su inverso:
                              descomposicion de un numero en letras hebreas
                              segun la convencion estandar, incluida la
                              excepcion documentada 15->9+6 (tet-vav) y
                              16->9+7 (tet-zayin) en vez de 10+5/10+6, para
                              evitar escribir las iniciales del Tetragramaton.
  canaanite_phoenician_numeral — sistema numeral aditivo fenicio/cananeo:
                              simbolos distintos para 1, 10, 20 y 100,
                              combinados por repeticion y suma (mismo
                              principio que los numerales aticos griegos,
                              de los que es precursor historico).
"""
import math

LEVANT_SCHEMA = {
    "name": "compute_levant",
    "description": (
        "Algoritmos matematicos cananeos y de Juda/Israel. Presets: "
        "hebrew_molad (conjuncion lunar media de Tishrei, algoritmo fijo de "
        "Hillel II, ciclo metonico de 19 anios), hebrew_gematria (valor "
        "numerico de palabras hebreas y su inverso, con la excepcion "
        "15/16), canaanite_phoenician_numeral (sistema aditivo fenicio "
        "1/10/20/100)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "preset": {
                "type": "string",
                "enum": ["hebrew_molad", "hebrew_gematria", "canaanite_phoenician_numeral", "validate"],
            },
            "params": {"type": "object"},
        },
        "required": ["preset"],
    },
}

# ---------------------------------------------------------------------------
# HEBREW MOLAD -- unidades: 1 hora = 1080 chalakim; 1 dia = 25920 chalakim.
# Molad Tohu (BaHaRaD): dia-index 1 (Yom Sheni/lunes) contando desde
# dia-index 0 (Yom Rishon/domingo) como inicio de epoca, hora 5, chalakim 204.
# Mes medio: 29 dias, 12 horas, 793 chalakim (765433 chalakim, constante
# clasica del calendario hebreo).
# ---------------------------------------------------------------------------
_CHALAKIM_PER_HOUR = 1080
_CHALAKIM_PER_DAY = 24 * _CHALAKIM_PER_HOUR  # 25920
_MEAN_MONTH_CHALAKIM = 29 * _CHALAKIM_PER_DAY + 12 * _CHALAKIM_PER_HOUR + 793  # 765433
_MOLAD_TOHU_CHALAKIM = 1 * _CHALAKIM_PER_DAY + 5 * _CHALAKIM_PER_HOUR + 204  # 31524

_WEEKDAY_NAMES = ["Yom Rishon (domingo)", "Yom Sheni (lunes)", "Yom Shlishi (martes)",
                  "Yom Revii (miercoles)", "Yom Chamishi (jueves)", "Yom Shishi (viernes)",
                  "Shabbat (sabado)"]

_LEAP_REMAINDERS = {3, 6, 8, 11, 14, 17, 0}


def _is_leap_year(hebrew_year):
    return (hebrew_year % 19) in _LEAP_REMAINDERS


def _months_elapsed_before_year(hebrew_year):
    """Meses transcurridos desde Tishrei del anio 1 hasta Tishrei del anio
    dado: 12 meses por anio comun + 1 extra por cada anio bisiesto previo."""
    leap_count = sum(1 for y in range(1, hebrew_year) if _is_leap_year(y))
    return 12 * (hebrew_year - 1) + leap_count


def compute_hebrew_molad(hebrew_year):
    if hebrew_year < 1:
        return {"error": "hebrew_year debe ser >= 1"}
    months_elapsed = _months_elapsed_before_year(hebrew_year)
    total_chalakim = _MOLAD_TOHU_CHALAKIM + months_elapsed * _MEAN_MONTH_CHALAKIM

    day_index = total_chalakim // _CHALAKIM_PER_DAY
    remainder = total_chalakim % _CHALAKIM_PER_DAY
    hour = remainder // _CHALAKIM_PER_HOUR
    chalakim = remainder % _CHALAKIM_PER_HOUR
    weekday = _WEEKDAY_NAMES[day_index % 7]

    return {
        "hebrew_year": hebrew_year,
        "is_leap_year": _is_leap_year(hebrew_year),
        "months_elapsed_since_year_1": months_elapsed,
        "molad_weekday": weekday,
        "molad_hour": hour,
        "molad_chalakim": chalakim,
        "molad_total_chalakim_since_epoch": total_chalakim,
        "note": ("Molad medio (aritmetico), sin aplicar las 4 dehiyyot de "
                 "posposicion de Rosh Hashana -- esas requieren reglas "
                 "adicionales sobre el dia de la semana resultante"),
    }


# ---------------------------------------------------------------------------
# GEMATRIA -- mispar hejrachi (valor numerico estandar por letra)
# ---------------------------------------------------------------------------
_GEMATRIA_VALUES = {
    "alef": 1, "bet": 2, "gimel": 3, "dalet": 4, "he": 5, "vav": 6, "zayin": 7,
    "het": 8, "tet": 9, "yod": 10, "kaf": 20, "lamed": 30, "mem": 40, "nun": 50,
    "samekh": 60, "ayin": 70, "pe": 80, "tsade": 90, "qof": 100, "resh": 200,
    "shin": 300, "tav": 400,
}
_HUNDREDS_DESC = [("tav", 400), ("shin", 300), ("resh", 200), ("qof", 100)]
_TENS_DESC = [("tsade", 90), ("pe", 80), ("ayin", 70), ("samekh", 60), ("nun", 50),
              ("mem", 40), ("lamed", 30), ("kaf", 20)]
_UNITS_DESC = [("tet", 9), ("het", 8), ("zayin", 7), ("vav", 6), ("he", 5),
               ("dalet", 4), ("gimel", 3), ("bet", 2), ("alef", 1)]


def _gematria_word_value(letters):
    total = 0
    unknown = []
    for name in letters:
        if name not in _GEMATRIA_VALUES:
            unknown.append(name)
            continue
        total += _GEMATRIA_VALUES[name]
    return total, unknown


def _gematria_encode_number(n):
    if not (1 <= n <= 999):
        return None
    letters = []
    remaining = n
    for name, val in _HUNDREDS_DESC:
        while remaining >= val:
            letters.append(name)
            remaining -= val
    # excepcion documentada: 15 y 16 se escriben tet-vav / tet-zayin
    # para no formar las iniciales del Tetragramaton (10+5, 10+6)
    if remaining == 15:
        letters += ["tet", "vav"]
        remaining = 0
    elif remaining == 16:
        letters += ["tet", "zayin"]
        remaining = 0
    else:
        for name, val in _TENS_DESC:
            while remaining >= val:
                letters.append(name)
                remaining -= val
        for name, val in _UNITS_DESC:
            while remaining >= val:
                letters.append(name)
                remaining -= val
    return letters


def compute_hebrew_gematria(mode="word_value", letters=None, number=None):
    if mode == "word_value":
        if not letters:
            return {"error": "mode='word_value' requiere 'letters' (lista de nombres de letra)"}
        total, unknown = _gematria_word_value(letters)
        result = {"mode": mode, "letters": letters, "value": total}
        if unknown:
            result["unknown_letters"] = unknown
        return result
    elif mode == "encode_number":
        if number is None:
            return {"error": "mode='encode_number' requiere 'number' (1-999)"}
        letters_out = _gematria_encode_number(number)
        if letters_out is None:
            return {"error": "solo se soportan numeros entre 1 y 999"}
        check_total, _ = _gematria_word_value(letters_out)
        return {"mode": mode, "number": number, "letters": letters_out, "check": check_total == number}
    else:
        return {"error": f"mode desconocido: {mode}"}


# ---------------------------------------------------------------------------
# NUMERALES CANANEOS/FENICIOS -- sistema aditivo: simbolos para 1,10,20,100
# ---------------------------------------------------------------------------
_PHOENICIAN_SYMBOLS_DESC = [("hundred", 100), ("twenty", 20), ("ten", 10), ("one", 1)]


def compute_canaanite_phoenician_numeral(mode="encode", number=None, symbols=None):
    if mode == "encode":
        if number is None or number < 1:
            return {"error": "mode='encode' requiere 'number' >= 1"}
        remaining = number
        counts = {}
        for name, val in _PHOENICIAN_SYMBOLS_DESC:
            c = remaining // val
            if c:
                counts[name] = c
                remaining -= c * val
        symbol_sequence = []
        for name, _ in _PHOENICIAN_SYMBOLS_DESC:
            symbol_sequence += [name] * counts.get(name, 0)
        return {
            "mode": mode, "number": number,
            "symbol_counts": counts,
            "symbol_sequence_left_to_right": symbol_sequence,
            "note": "El '1' se agrupa tradicionalmente en bloques de 3 trazos verticales al grabarlo",
        }
    elif mode == "decode":
        if not symbols:
            return {"error": "mode='decode' requiere 'symbols' (lista de nombres)"}
        values = {"hundred": 100, "twenty": 20, "ten": 10, "one": 1}
        total = 0
        unknown = []
        for s in symbols:
            if s not in values:
                unknown.append(s)
                continue
            total += values[s]
        result = {"mode": mode, "symbols": symbols, "value": total}
        if unknown:
            result["unknown_symbols"] = unknown
        return result
    else:
        return {"error": f"mode desconocido: {mode}"}


def _validate_levant():
    """Checks anclados a constantes clasicas documentadas y relaciones
    analiticas conocidas (no solo 'no exploto')."""
    checks = []

    # --- hebrew_molad anio 1: debe coincidir EXACTO con BaHaRaD ---
    m1 = compute_hebrew_molad(1)
    checks.append({
        "name": "hebrew_molad_anio1_coincide_con_baharad",
        "weekday": m1.get("molad_weekday"),
        "hour": m1.get("molad_hour"),
        "chalakim": m1.get("molad_chalakim"),
        "passed": bool(m1.get("molad_weekday") == "Yom Sheni (lunes)"
                        and m1.get("molad_hour") == 5
                        and m1.get("molad_chalakim") == 204
                        and m1.get("is_leap_year") is False),
    })

    # --- hebrew_molad anio 20: 235 meses desde anio 1 (ciclo metonico) ---
    m2 = compute_hebrew_molad(20)
    checks.append({
        "name": "hebrew_molad_anio20_ciclo_metonico_235_meses",
        "months_elapsed": m2.get("months_elapsed_since_year_1"),
        "passed": bool(m2.get("months_elapsed_since_year_1") == 235),
    })

    # --- hebrew_molad: anios bisiestos correctos segun residuos documentados ---
    m3 = compute_hebrew_molad(19)
    m4 = compute_hebrew_molad(3)
    checks.append({
        "name": "hebrew_molad_anios_bisiestos_19_y_3",
        "anio19_leap": m3.get("is_leap_year"),
        "anio3_leap": m4.get("is_leap_year"),
        "passed": bool(m3.get("is_leap_year") is True and m4.get("is_leap_year") is True),
    })

    # --- hebrew_molad: anio invalido -> error estructurado ---
    m5 = compute_hebrew_molad(0)
    checks.append({
        "name": "hebrew_molad_anio_invalido_da_error_no_crash",
        "passed": bool(isinstance(m5, dict) and "error" in m5),
    })

    # --- gematria word_value: 'chai' (het+yod) = 18, numero de la vida ---
    g1 = compute_hebrew_gematria(mode="word_value", letters=["het", "yod"])
    checks.append({
        "name": "gematria_chai_het_yod_igual_18",
        "value": g1.get("value"),
        "passed": bool(g1.get("value") == 18),
    })

    # --- gematria encode_number: excepcion Tetragramaton 15 y 16 ---
    g2 = compute_hebrew_gematria(mode="encode_number", number=15)
    g3 = compute_hebrew_gematria(mode="encode_number", number=16)
    checks.append({
        "name": "gematria_excepcion_tetragramaton_15_16",
        "letters_15": g2.get("letters"),
        "letters_16": g3.get("letters"),
        "passed": bool(g2.get("letters") == ["tet", "vav"] and g2.get("check") is True
                        and g3.get("letters") == ["tet", "zayin"] and g3.get("check") is True),
    })

    # --- phoenician numeral: encode(234) exacto, decode roundtrip ---
    p1 = compute_canaanite_phoenician_numeral(mode="encode", number=234)
    counts = p1.get("symbol_counts", {})
    checks.append({
        "name": "phoenician_encode_234_conteo_exacto",
        "counts": counts,
        "passed": bool(counts.get("hundred") == 2 and counts.get("twenty") == 1
                        and counts.get("ten") == 1 and counts.get("one") == 4),
    })
    p2 = compute_canaanite_phoenician_numeral(
        mode="decode", symbols=p1.get("symbol_sequence_left_to_right", [])
    )
    checks.append({
        "name": "phoenician_decode_roundtrip_234",
        "value": p2.get("value"),
        "passed": bool(p2.get("value") == 234),
    })

    # --- phoenician numeral: simbolo desconocido reportado, no fallo silencioso ---
    p3 = compute_canaanite_phoenician_numeral(mode="decode", symbols=["hundred", "gorp"])
    checks.append({
        "name": "phoenician_decode_simbolo_desconocido_reportado",
        "unknown_symbols": p3.get("unknown_symbols"),
        "passed": bool(p3.get("unknown_symbols") == ["gorp"]),
    })

    # --- preset desconocido -> error estructurado ---
    unk = compute_levant("preset_inexistente")
    checks.append({
        "name": "preset_desconocido_devuelve_error",
        "passed": bool(isinstance(unk, dict) and "error" in unk),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed, "n_checks": len(checks)}


def compute_levant(preset, params=None):
    params = params or {}
    if preset == "validate":
        return _validate_levant()
    if preset == "hebrew_molad":
        return compute_hebrew_molad(**params)
    elif preset == "hebrew_gematria":
        return compute_hebrew_gematria(**params)
    elif preset == "canaanite_phoenician_numeral":
        return compute_canaanite_phoenician_numeral(**params)
    else:
        return {"error": f"preset desconocido: {preset}"}

try:
    from tool_registry import register_tool
    register_tool(
        name="levant",
        schema={**LEVANT_SCHEMA, "name": "levant"},
        handler=lambda args: compute_levant(**args),
    )
except ImportError:
    pass

