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
                "enum": ["hebrew_molad", "hebrew_gematria", "canaanite_phoenician_numeral"],
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


def compute_levant(preset, params=None):
    params = params or {}
    if preset == "hebrew_molad":
        return compute_hebrew_molad(**params)
    elif preset == "hebrew_gematria":
        return compute_hebrew_gematria(**params)
    elif preset == "canaanite_phoenician_numeral":
        return compute_canaanite_phoenician_numeral(**params)
    else:
        return {"error": f"preset desconocido: {preset}"}
