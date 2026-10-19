"""Herramienta unica de sistemas numericos y criptografia ancestral.

Unifica: conversion entre numerales (babilónico, maya, egipcio, romano,
griego jónico, hebreo, quipu), fracciones egipcias (delegadas),
aritmética sexagesimal exacta, gematria (hebreo/griego/abjad/persa),
cifrados clasicos (atbash/albam/atbah/cesar/vigenere), analisis de
frecuencia/IC/Kasiski, y generación de código del conversor en
python/octave/bend.

Es historia/educacion: los cifrados clasicos NO son criptografia
moderna segura.
"""
from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

TOOL_NAME = "ancient_numeral_crypto"

DISCLAIMER = (
    "Cifrados clasicos con valor historico/educativo. NO son criptografia "
    "moderna segura: son frecuentemente rotos. No usar para proteger datos reales."
)


# ---------------------------------------------------------------------------
# 1) ALFABETOS Y CONSTANTES DE NUMERALES
# ---------------------------------------------------------------------------

# Babilónico: dígito 0 = "·", 1-9 = 𒁹 (U+12079 DIŠ), 10-50 = 𒌋 (U+1230B U).
_BAB_ONE = "𒁹"  # U+12079 CUNEIFORM SIGN DIŠ
BAB_TEN = "𒌋"  # U+1230B CUNEIFORM SIGN U
BAB_ZERO = "·"  # U+00B7 MIDDLE DOT

# Maya: base-20. 0 = "○", 1-4 puntos "•", >=5 = puntos resto + barras "|".
_MAYA_ZERO = "○"
_MAYA_DOT = "•"
_MAYA_BAR = "|"

# Egipcio jeroglifico aditivo (por lugar, 1-9 repeticiones).
_EGY = {
    0: "",
    1: "𓏺",   # 𓏺
    10: "𓎆",  # 𓎆
    100: "𓍢",  # 𓍢
    1000: "𓆼",  # 𓆼
    10000: "𓂭",  # 𓂭
    100000: "𓎐",  # 𓎐
    1000000: "𓁨",  # 𓁨
}
_EGY_DIGIT_SIGNS = [1, 10, 100, 1000, 10000, 100000, 1000000]

_ROMAN_VALS = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]

# Griego jónico (isopsefia). Incluye stigma ϛ/Ϛ=6, koppa ϟ/Ϟ=90, sampi ϡ/Ϡ=900.
# ϝ (digamma) tambien vale 6; lo aceptamos al decodificar como sinónimo.
_GREEK = [
    (900, "ϡ"), (800, "ω"), (700, "ψ"), (600, "χ"), (500, "φ"),
    (400, "υ"), (300, "τ"), (200, "σ"), (100, "ρ"), (90, "ϟ"),
    (80, "π"), (70, "ο"), (60, "ξ"), (50, "ν"), (40, "μ"),
    (30, "λ"), (20, "κ"), (10, "ι"), (9, "θ"), (8, "η"),
    (7, "ζ"), (6, "ϛ"), (5, "ε"), (4, "δ"), (3, "γ"),
    (2, "β"), (1, "α"),
]
# Variantes aceptadas al decodificar (mayúsculas/finales de palabra).
_GREEK_DECODE_EXTRAS = {
    "ϛ": 6, "Ϛ": 6, "ϝ": 6, "Ϝ": 6,
    "ϟ": 90, "Ϟ": 90, "ϙ": 90, "Ϙ": 90,
    "ϡ": 900, "Ϡ": 900,
    "ς": 200, "σ": 200, "Σ": 200,
}
_GREEK_THOUSAND = "͵"  # ͵ (U+0375) multiplica el grupo siguiente por 1000
_GREEK_KERAIYA = "ʹ"   # ʹ (U+0374) marca millares/ordinales; se ignora al decodificar

# Hebreo. Valores base 1..400; sofit 500-900 (variante); miles = letra+geresh.
# Convención por defecto (estándar tav-based): 500=תק … 900=תתק (no se usan
# sofit para centenas); encode emite gershayim (״) antes de la última letra.
# style="sofit" usa ך׳=500 … ץ׳=900 (variante medieval). Geresh (׳) marca miles.
_HEBREW_LETTERS = [
    ("א", 1), ("ב", 2), ("ג", 3), ("ד", 4), ("ה", 5), ("ו", 6), ("ז", 7),
    ("ח", 8), ("ט", 9), ("י", 10), ("כ", 20), ("ל", 30), ("מ", 40), ("נ", 50),
    ("ס", 60), ("ע", 70), ("פ", 80), ("צ", 90), ("ק", 100), ("ר", 200),
    ("ש", 300), ("ת", 400),
]
# Formas finales (sofit): solo se emiten con style="sofit" y geresh (ך׳=500…);
# solas valen 20/40/50/80/90 (כ/מ/נ/פ/צ).
_HEBREW_FINALS = [("ך", 500), ("ם", 600), ("ן", 700), ("ף", 800), ("ץ", 900)]
_HEBREW_GERESH = "׳"       # U+05F3 HEBREW PUNCTUATION GERESH
_HEBREW_GERSHAYIM = "״"    # U+05F4 HEBREW PUNCTUATION GERSHAYIM
# basura para gematria/decode: nikud, gershayim, geresh, comillas, espacios
_HEBREW_JUNK = re.compile(r"[\u0591-\u05C7\s׳״\"']+")
# variante para _hebrew_decode: conserva el geresh (miles/sofit)
_HEBREW_JUNK_KEEP_GERESH = re.compile(r"[\u0591-\u05C7\s״\"']+")

# Abjad arabo completo (orden: 28 letras historicas + 4 persas).
_ABJAD_AR = {
    "ا": 1, "ب": 2, "ج": 3, "د": 4, "ه": 5, "و": 6, "ز": 7, "ح": 8, "ط": 9,
    "ي": 10, "ك": 20, "ل": 30, "م": 40, "ن": 50, "س": 60, "ع": 70, "ف": 80,
    "ص": 90, "ق": 100, "ر": 200, "ش": 300, "ت": 400, "ث": 500, "خ": 600,
    "ذ": 700, "ض": 800, "ظ": 900, "غ": 1000,
}
# Persa = abjad + پ(2) چ(3) ژ(7) گ(20). Variantes documentadas segun fuente.
_ABJAD_FA = dict(_ABJAD_AR)
_ABJAD_FA.update({"پ": 2, "چ": 3, "ژ": 7, "گ": 20})


def _strip_accents_greek(s: str) -> str:
    """Quita acentos/diaresis griegos dejando la letra base (NFD + Mn)."""
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# ---------------------------------------------------------------------------
# 2) CONVERSION DE NUMERALES
# ---------------------------------------------------------------------------

def _babylonian_encode(n: int) -> str:
    if n < 0:
        raise ValueError("babilónico solo codifica enteros no negativos")
    if n == 0:
        return BAB_ZERO
    groups = []
    while n > 0:
        n, d = divmod(n, 60)
        groups.append(d)
    groups.reverse()
    out = []
    for d in groups:
        if d == 0:
            out.append(BAB_ZERO)
        else:
            tens, ones = divmod(d, 10)
            out.append(BAB_TEN * tens + _BAB_ONE * ones)
    return " ".join(out)


def _babylonian_decode(text: str) -> int:
    text = text.strip()
    if not text:
        raise ValueError("texto vacío")
    if text == BAB_ZERO:
        return 0
    total = 0
    for group in text.split():
        tens = group.count(BAB_TEN)
        ones = group.count(_BAB_ONE)
        zero = BAB_ZERO in group
        if zero and (tens or ones):
            raise ValueError(f"grupo babilónico mixto inválido: {group!r}")
        d = tens * 10 + ones
        if d >= 60:
            raise ValueError(f"dígito sexagesimal >=60: {d}")
        total = total * 60 + d
    return total


def _maya_encode(n: int) -> str:
    if n < 0:
        raise ValueError("maya solo codifica enteros no negativos")
    if n == 0:
        return _MAYA_ZERO
    groups = []
    while n > 0:
        n, d = divmod(n, 20)
        groups.append(d)
    groups.reverse()

    def glyph(d: int) -> str:
        if d == 0:
            return _MAYA_ZERO
        dots = _MAYA_DOT * (d % 5)
        bars = _MAYA_BAR * (d // 5)
        return dots + bars

    return " ".join(glyph(d) for d in groups)


def _maya_decode(text: str) -> int:
    text = text.strip()
    if not text:
        raise ValueError("texto vacío")
    total = 0
    for group in text.split():
        if group == _MAYA_ZERO:
            d = 0
        else:
            dots = group.count(_MAYA_DOT)
            bars = group.count(_MAYA_BAR)
            if dots >= 5:
                raise ValueError(f"grupo maya inválido (>=5 puntos): {group!r}")
            d = dots + bars * 5
            if d >= 20:
                raise ValueError(f"dígito vigesimal >=20: {d}")
        total = total * 20 + d
    return total


def _egyptian_encode(n: int) -> str:
    if n < 0:
        raise ValueError("egipcio solo codifica enteros no negativos")
    if n == 0:
        return ""
    out = []
    for sign in reversed(_EGY_DIGIT_SIGNS):
        while n >= sign:
            out.append(_EGY[sign])
            n -= sign
    return "".join(out)


def _egyptian_decode(text: str) -> int:
    rev = {v: k for k, v in _EGY.items() if v}
    total = 0
    for ch in text.strip():
        if ch not in rev:
            raise ValueError(f"carácter no jeroglífico: {ch!r}")
        total += rev[ch]
    return total


def _roman_encode(n: int) -> str:
    if not (1 <= n <= 3999):
        raise ValueError("romano codifica enteros en [1, 3999]")
    out = []
    for val, sym in _ROMAN_VALS:
        while n >= val:
            out.append(sym)
            n -= val
    return "".join(out)


def _roman_decode(text: str) -> int:
    text = text.strip().upper()
    roman = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    vals = [roman.get(c) for c in text]
    if any(v is None for v in vals):
        raise ValueError("carácter romano inválido")
    total = 0
    for i, v in enumerate(vals):
        nxt = vals[i + 1] if i + 1 < len(vals) else 0
        total += -v if v < nxt else v
    # validación de forma canónica
    if _roman_encode(total) != text:
        raise ValueError("forma romana no canónica")
    return total


def _greek_encode(n: int) -> str:
    if n < 1:
        raise ValueError("griego codifica enteros >= 1")
    if n >= 10000:
        raise ValueError("griego codifica enteros en [1, 9999]")
    thousands, rest = divmod(n, 1000)
    body = []
    if thousands:
        # millares: ͵ + letras del grupo de miles (sin keraia interna)
        body.append(_GREEK_THOUSAND + _greek_letters_only(thousands))
    body.append(_greek_letters_only(rest))
    return "".join(body) + _GREEK_KERAIYA


def _greek_letters_only(n: int) -> str:
    """ letras isopseficas para un entero en [0,999] (sin keraia). """
    if n == 0:
        return ""
    out = []
    for val, letter in _GREEK:
        while n >= val:
            out.append(letter)
            n -= val
    return "".join(out)


def _greek_decode(text: str) -> int:
    # Quitar keraia en ambas formas: U+0374 (combinada) y U+02B9 (NFD).
    s = (text.replace(_GREEK_KERAIYA, "")
             .replace("ʹ", "")
             .replace("\u02b9", "")
             .strip())
    s = _strip_accents_greek(s)
    val = {letter: v for v, letter in _GREEK}
    val.update(_GREEK_DECODE_EXTRAS)

    def word(chs: str) -> int:
        total = 0
        for ch in chs.lower():
            if ch not in val:
                raise ValueError(f"letra griega inválida: {ch!r}")
            total += val[ch]
        return total

    if _GREEK_THOUSAND in s:
        head, tail = s.split(_GREEK_THOUSAND, 1)
        # ͵ marca millares: la(s) primera(s) letra(s) del grupo son los miles.
        # Para n < 10000 los miles son UNA sola letra (α..θ); el resto son
        # las centenas/decenas/unidades. Asi ͵βιθ = 2*1000 + 19 = 2019.
        if not tail:
            raise ValueError("keraia de millares sin letras")
        return word(head) * 1000 + word(tail[0]) * 1000 + word(tail[1:])
    return word(s)


# dígitos para miles (1-9), centenas, decenas, unidades
_HEBREW_MIL_MAP = {1: "א", 2: "ב", 3: "ג", 4: "ד", 5: "ה",
                   6: "ו", 7: "ז", 8: "ח", 9: "ט"}
# centenas estándar tav-based: 500=תק … 900=תתק (convención moderna)
# 700 = תש (tav+shin = 400+300); תשע sería 770 (equivocado).
_HEBREW_HUND_STD = {1: "ק", 2: "ר", 3: "ש", 4: "ת",
                    5: "תק", 6: "תר", 7: "תש", 8: "תת", 9: "תתק"}
_HEBREW_HUND_FINAL_MAP = {5: "ך", 6: "ם", 7: "ן", 8: "ף", 9: "ץ"}
_HEBREW_TENS_MAP = {1: "י", 2: "כ", 3: "ל", 4: "מ", 5: "נ",
                    6: "ס", 7: "ע", 8: "פ", 9: "צ"}
_HEBREW_ONES_MAP = {1: "א", 2: "ב", 3: "ג", 4: "ד", 5: "ה",
                    6: "ו", 7: "ז", 8: "ח", 9: "ט"}


def _hebrew_encode(n: int, gershayim: bool = True, style: str = "standard") -> str:
    """Codifica n en numerales hebreos.

    - Convención estándar (tav-based): 500=תק … 900=תתק.
    - style="sofit": centenas 500-900 usan finales+geresh (ך׳ … ץ׳).
    - Regla 15/16: n%100 ∈ {15,16} → ט+ו / ט+ז (no יה/יו).
    - gershayim=True (default): inserta ״ en el tail (parte posterior a los
      miles), solo si el tail tiene ≥2 letras y style=="standard".
    - Geresh de miles (א׳) se emite siempre; el gershayim NO toca los miles
      (encode(2001) = ב׳א, no ב׳״א).
    """
    if not (1 <= n <= 9999):
        raise ValueError("hebreo codifica enteros en [1, 9999]")
    if style not in ("standard", "sofit"):
        raise ValueError("style debe ser 'standard' o 'sofit'")
    prefix = ""
    if n >= 1000:
        prefix = _HEBREW_MIL_MAP[n // 1000] + _HEBREW_GERESH
        n %= 1000
    tail_parts = []
    hundreds = n // 100
    if hundreds:
        if style == "sofit" and hundreds >= 5:
            tail_parts.append(_HEBREW_HUND_FINAL_MAP[hundreds] + _HEBREW_GERESH)
        else:
            tail_parts.append(_HEBREW_HUND_STD[hundreds])
    rest = n % 100
    tens, ones = divmod(rest, 10)
    # regla 15/16: 15=ט״ו (9+6), 16=ט״ז (9+7); no יה/יו (10+5/10+6)
    if tens == 1 and ones in (5, 6):
        tail_parts.append(_HEBREW_ONES_MAP[9])        # ט (9)
        tail_parts.append(_HEBREW_ONES_MAP[ones + 1]) # ו (6) / ז (7)
    else:
        if tens:
            tail_parts.append(_HEBREW_TENS_MAP[tens])
        if ones:
            tail_parts.append(_HEBREW_ONES_MAP[ones])
    tail = "".join(tail_parts)
    # gershayim solo en el tail estándar con ≥2 letras
    if gershayim and style == "standard" and len(tail) >= 2:
        tail = tail[:-1] + _HEBREW_GERSHAYIM + tail[-1]
    return prefix + tail


def _hebrew_decode(text: str, strict: bool = False) -> int:
    """Decodifica numerales hebreos.

    - Acepta tanto la forma estándar (tav-based) como sofit (ך׳=500…).
    - Finales solos valen 20/40/50/80/90 (require para gematria de palabras).
    - Geresh de letras base = miles (א׳=1000); gershayim (״) se ignora.
    - strict=True: valida canonicidad (re-encode bare debe dar el texto sin ״
      y sin geresh, o con geresh de miles). Lanza ValueError si no es canónico.
    """
    # quitar nikud/gershayim y espacios; el geresh se conserva (miles/sofit)
    s = _HEBREW_JUNK_KEEP_GERESH.sub("", text)
    base = {ch: v for ch, v in _HEBREW_LETTERS}
    final = {ch: v for ch, v in _HEBREW_FINALS}
    # finales como decenas/centenas simples (ך=20, מ=40, נ=50, פ=80, צ=90)
    fin_as_base = {"ך": 20, "ם": 40, "ן": 50, "ף": 80, "ץ": 90}
    total = 0
    i = 0
    while i < len(s):
        ch = s[i]
        nxt = s[i + 1] if i + 1 < len(s) else ""
        if ch in final:
            # final + geresh = centena 500-900 (ך׳=500 … ץ׳=900, estilo sofit)
            if nxt == _HEBREW_GERESH:
                total += final[ch]
                i += 2
            else:
                total += fin_as_base[ch]
                i += 1
        elif nxt == _HEBREW_GERESH:
            # letra regular + geresh = miles (א׳=1000 … ט׳=9000)
            if ch not in base:
                raise ValueError(f"letra hebrea inválida antes de geresh: {ch!r}")
            total += base[ch] * 1000
            i += 2
        elif ch in base:
            total += base[ch]
            i += 1
        elif ch == _HEBREW_GERESH:
            i += 1
        else:
            raise ValueError(f"letra hebrea inválida: {ch!r}")
    if strict:
        # validar canonicidad: re-encode (bare, sin gershayim) debe dar el
        # mismo texto sin gershayim. Probar también style sofit.
        bare = text.strip().replace(_HEBREW_GERSHAYIM, "")
        ok_std = False
        ok_sofit = False
        try:
            ok_std = (_hebrew_encode(total, gershayim=False, style="standard")
                      == bare)
        except ValueError:
            pass
        try:
            ok_sofit = (_hebrew_encode(total, gershayim=False, style="sofit")
                        == bare)
        except ValueError:
            pass
        if not (ok_std or ok_sofit):
            raise ValueError(
                f"forma hebrea no canónica: {text!r} (valor={total})")
    return total


# Quipu: reusa ethnomath_tool (decimal <-> estructura de cordones).
try:
    from ethnomath_tool import _quipu_encode as _quipu_enc, _quipu_decode as _quipu_dec
except ImportError:  # pragma: no cover
    _quipu_enc = None
    _quipu_dec = None


def _quipu_convert(params: Dict[str, Any]) -> Dict[str, Any]:
    if _quipu_enc is None:
        return {"error": "ethnomath_tool no disponible para quipu"}
    mode = params.get("mode", "encode")
    if mode == "encode":
        if "value" not in params:
            return {"error": "mode='encode' requiere 'value'"}
        enc = _quipu_enc(int(params["value"]))
        enc["decoded_check"] = _quipu_dec(enc.get("cords", [])) == int(params["value"])
        return enc
    if mode == "decode":
        if not params.get("cords"):
            return {"error": "mode='decode' requiere 'cords'"}
        return {"decoded_value": _quipu_dec(params["cords"])}
    return {"error": f"mode quipu desconocido: {mode}"}


_SYSTEMS: Dict[str, Dict[str, Any]] = {
    "babilonico": {"enc": _babylonian_encode, "dec": _babylonian_decode, "kind": "str"},
    "maya": {"enc": _maya_encode, "dec": _maya_decode, "kind": "str"},
    "egipcio": {"enc": _egyptian_encode, "dec": _egyptian_decode, "kind": "str"},
    "romano": {"enc": _roman_encode, "dec": _roman_decode, "kind": "str"},
    "griego": {"enc": _greek_encode, "dec": _greek_decode, "kind": "str"},
    "hebreo": {"enc": _hebrew_encode, "dec": _hebrew_decode, "kind": "str"},
}


def _numeral_convert(params: Dict[str, Any]) -> Dict[str, Any]:
    system = params.get("system")
    if system == "quipu":
        return _quipu_convert(params)
    if system not in _SYSTEMS:
        return {"error": f"sistema desconocido: {system!r}",
                "systems": list(_SYSTEMS) + ["quipu"]}
    sysd = _SYSTEMS[system]
    mode = params.get("mode", "encode")
    if mode == "encode":
        if "value" not in params:
            return {"error": "mode='encode' requiere 'value'"}
        n = int(params["value"])
        if system == "hebreo":
            s = _hebrew_encode(n,
                               gershayim=bool(params.get("gershayim", True)),
                               style=str(params.get("style", "standard")))
        else:
            s = sysd["enc"](n)
        return {"system": system, "mode": mode, "value": n, "text": s,
                "decoded_check": sysd["dec"](s) == n}
    if mode == "decode":
        if "text" not in params:
            return {"error": "mode='decode' requiere 'text'"}
        raw = str(params["text"])
        if system == "hebreo":
            # hebreo: decodificar laxo + flag canónico (no lanza)
            style = str(params.get("style", "standard"))
            gershayim = bool(params.get("gershayim", True))
            n = _hebrew_decode(raw, strict=False)
            try:
                _hebrew_decode(raw, strict=True)
                canonical = True
            except ValueError:
                canonical = False
            return {"system": system, "mode": mode, "text": raw,
                    "value": n, "canonical": canonical,
                    "encoded_check": _hebrew_encode(
                        n, gershayim=gershayim, style=style) == raw}
        n = sysd["dec"](raw)
        return {"system": system, "mode": mode, "text": params["text"],
                "value": n, "encoded_check": sysd["enc"](n) == raw}
    return {"error": f"mode desconocido: {mode}"}


# ---------------------------------------------------------------------------
# 3) FRACCIONES EGIPCIAS (delegadas) Y ARITMETICA SEXAGESIMAL
# ---------------------------------------------------------------------------

def _egyptian_fractions(params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from ethnomath2_tool import compute_egyptian_duplation
    except ImportError:
        return {"error": "ethnomath2_tool no disponible"}
    num = int(params.get("numerator", 0))
    den = int(params.get("denominator", 1))
    r = compute_egyptian_duplation(
        mode="unit_fractions", numerator=num, denominator=den)
    # verificación exacta con Fraction (no decimal)
    terms = r.get("unit_fraction_denominators", [])
    if terms:
        r["check_exact"] = sum(Fraction(1, t) for t in terms) == Fraction(num, den)
    r["system"] = "egipcio"
    return r


def _parse_sexagesimal(text: str) -> Fraction:
    """'1;30' -> 1 + 30/60 = 3/2. Acepta '1:30'; parte entera con comas:
    '1,30;15' -> 1*60 + 30 = 90.75."""
    s = str(text).strip().replace(" ", "")
    for sep in (":", ";"):
        if sep in s:
            int_part, frac_part = s.split(sep, 1)
            break
    else:
        int_part, frac_part = s, ""
    # parte entera: digitos separados por coma = base-60 (1,30 = 90)
    if int_part:
        total = Fraction(
            sum(int(d) * 60 ** i
                for i, d in enumerate(reversed(int_part.split(",")))), 1)
    else:
        total = Fraction(0, 1)
    if frac_part:
        # multiples digitos: '1;2,30' = 1 + 2/60 + 30/3600
        for k, dig in enumerate(frac_part.split(","), start=1):
            d = int(dig)
            if not (0 <= d < 60):
                raise ValueError(f"dígito sexagesimal fuera de [0,59]: {d}")
            total += Fraction(d, 60 ** k)
    return total


def _to_sexagesimal(fr: Fraction) -> str:
    if fr < 0:
        return "-" + _to_sexagesimal(-fr)
    int_part = fr.numerator // fr.denominator
    frac = fr - int_part
    if frac == 0:
        return str(int_part)
    digits = []
    for _ in range(12):  # precision fija; los sexagesimales exactos terminan antes
        frac *= 60
        d = int(frac)
        digits.append(str(d))
        frac -= d
        if frac == 0:
            break
    return f"{int_part};" + ",".join(digits)


def _sexagesimal_arith(params: Dict[str, Any]) -> Dict[str, Any]:
    a = params.get("a")
    b = params.get("b")
    op = params.get("op")
    if a is None or op is None:
        return {"error": "sexagesimal_arith requiere 'a', 'op'"}
    if b is None and op != "reciprocal":
        return {"error": "sexagesimal_arith requiere 'b' (salvo op='reciprocal')"}
    fa = _parse_sexagesimal(a)
    fb = _parse_sexagesimal(b) if b is not None else Fraction(0, 1)
    ops: Dict[str, Callable[[Fraction, Fraction], Fraction]] = {
        "add": lambda x, y: x + y,
        "sub": lambda x, y: x - y,
        "mul": lambda x, y: x * y,
        "div": lambda x, y: x / y,
        "reciprocal": lambda x, y: 1 / x,
    }
    if op not in ops:
        return {"error": f"op desconocida: {op}",
                "ops": list(ops)}
    if op == "reciprocal":
        res = 1 / fa
    else:
        res = ops[op](fa, fb)
    # terminacion en base-60: denominador solo con factores 2,3,5
    d = res.denominator
    exact = True
    for p in (2, 3, 5):
        while d % p == 0:
            d //= p
    if d != 1:
        exact = False
    return {
        "op": op, "a": a, "b": b,
        "a_fraction": f"{fa.numerator}/{fa.denominator}",
        "b_fraction": f"{fb.numerator}/{fb.denominator}",
        "result_fraction": f"{res.numerator}/{res.denominator}",
        "result_sexagesimal": _to_sexagesimal(res),
        "terminates_sexagesimal": exact,
        "decimal": float(res),
    }


# ---------------------------------------------------------------------------
# 4) GEMATRIA
# ---------------------------------------------------------------------------

# Gematría hebrea: suma directa de letras (NO el decoder de numerales).
# El decoder trata geresh como miles (א׳=1000); en una palabra es puntuación:
# gematría("א׳ב") = 1+2 = 3, no 1002. Basa: ק=100..ת=400.
# Finales base: ך=20 ם=40 ן=50 ף=80 ץ=90; con gadol pasan a 500..900.
# (_HEBREW_JUNK y _HEBREW_JUNK_KEEP_GERESH se definen con las constantes hebrea
# arriba, porque _hebrew_decode tambien los usa.)
_HEBREW_GEM_BASE = {**{ch: v for ch, v in _HEBREW_LETTERS},
                    "ך": 20, "ם": 40, "ן": 50, "ף": 80, "ץ": 90}
# gadol (letras finales grandes): ך=500 ם=600 ן=700 ף=800 ץ=900
_HEBREW_GEM_GADOL = {"ך": 500, "ם": 600, "ן": 700, "ף": 800, "ץ": 900}

# Normalización árabe/persa para gematría abjad.
_AR_NORM = str.maketrans({"ک": "ك", "ی": "ي", "ؤ": "و", "ئ": "ي",
                          "ة": "ه", "ۀ": "ه", "أ": "ا", "إ": "ا",
                          "آ": "ا", "ٱ": "ا"})
_TASHKEEL = re.compile(r"[\u064B-\u065F\u0670]")


def _hebrew_gematria(text: str, gadol: bool = False) -> int:
    """Suma directa de letras hebreas; ignora nikud, gershayim, geresh y espacios."""
    s = _HEBREW_JUNK.sub("", text)
    table = _HEBREW_GEM_BASE if not gadol else {
        **{k: v for k, v in _HEBREW_GEM_BASE.items()
           if k not in _HEBREW_GEM_GADOL},
        **_HEBREW_GEM_GADOL}
    return sum(table.get(ch, 0) for ch in s)


def _gematria(params: Dict[str, Any]) -> Dict[str, Any]:
    system = params.get("system", "hebrew")
    text = str(params.get("text", "")).strip()
    note = DISCLAIMER
    if system == "hebrew":
        gadol = bool(params.get("gadol", False))
        v = _hebrew_gematria(text, gadol=gadol)
        note = (f"gematría directa (gadol={'sí' if gadol else 'no'}); "
                "geresh/gershayim/nikud ignorados")
    elif system == "griego":
        # suma directa de letras (isopsefia): ignora espacios, puntuacion,
        # keraia y marcas. NO usa _greek_decode (que exige texto valido de
        # numeral y lanza con frases de varias palabras).
        s = _strip_accents_greek(text)
        val = {letter: v for v, letter in _GREEK}
        val.update(_GREEK_DECODE_EXTRAS)
        v = sum(val.get(ch.lower(), 0) for ch in s)
    elif system == "abjad":
        s = _TASHKEEL.sub("", text)
        ta = int(params.get("ta_marbuta", 5))
        if ta not in (5, 400):
            return {"error": "ta_marbuta debe ser 5 u 400"}
        if ta == 400:
            # ta marbuta como т/ت (400): sustituir antes de normalizar
            s = s.replace("ة", "ت").replace("ۀ", "ت")
            s = s.translate(_AR_NORM)
        else:
            s = s.translate(_AR_NORM)  # ة -> ه (5)
        v = sum(_ABJAD_AR.get(ch, 0) for ch in s)
    elif system == "persa":
        ta = int(params.get("ta_marbuta", 5))
        if ta not in (5, 400):
            return {"error": "ta_marbuta debe ser 5 u 400"}
        s = _TASHKEEL.sub("", text)
        if ta == 400:
            # ta marbuta = ت (400): sustituir ANTES de normalizar ه/ة
            s = s.replace("ة", "ت").replace("ۀ", "ت")
        s = s.translate(_AR_NORM)
        v = sum(_ABJAD_FA.get(ch, 0) for ch in s)
    else:
        return {"error": f"sistema gematria desconocido: {system!r}",
                "systems": ["hebrew", "griego", "abjad", "persa"]}
    return {"system": system, "text": text, "value": v, "note": note}


# ---------------------------------------------------------------------------
# 5) CIFRADOS CLASICOS
# ---------------------------------------------------------------------------

_LATIN = "abcdefghijklmnopqrstuvwxyz"
# Alfabeto hebreo de 22 letras (orden alef..tav) para cifrados atbash/albam.
_HEBREW_ALPHA = "".join(ch for ch, _ in _HEBREW_LETTERS)
_ALPHABETS = {"hebrew": _HEBREW_ALPHA, "greek": "αβγδεζηθικλμνξοπρστυφχψω",
              "latin": _LATIN}

# Normalizacion previa de texto cifrado: quitar nikud/tashkeel y mapear
# finales (incluida la final sigma griega) a sus formas base para que el
# cifrado sobre el alfabeto de 22/24 letras sea biyectivo.
_NIKUD = re.compile(r"[\u0591-\u05C7]")
_FIN = str.maketrans({"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ",
                      "ς": "σ"})


def _apply_shift(ch: str, shift: int, alphabet: str) -> str:
    low = alphabet.lower()
    if ch.lower() not in low:
        return ch
    idx = low.index(ch.lower())
    out = low[(idx + shift) % len(alphabet)]
    return out.upper() if ch.isupper() else out


def _atbash_char(ch: str, alphabet: str) -> str:
    low = alphabet.lower()
    if ch.lower() not in low:
        return ch
    idx = low.index(ch.lower())
    out = low[len(alphabet) - 1 - idx]
    return out.upper() if ch.isupper() else out


def _cipher(params: Dict[str, Any]) -> Dict[str, Any]:
    cipher = params.get("cipher")
    # normalizar antes de autodetectar: quitar marcas, finales -> base
    text = _NIKUD.sub("", str(params.get("text", "")))
    text = text.translate(_FIN)
    alphabet = params.get("alphabet")
    if not alphabet:
        # autodetect: si el texto tiene letras hebreas, usa el alfabeto hebreo
        if any(ch in _HEBREW_ALPHA for ch in text):
            alphabet = _HEBREW_ALPHA
        elif any(ch in _ALPHABETS["greek"] for ch in text):
            alphabet = _ALPHABETS["greek"]
        else:
            alphabet = _LATIN
    key = params.get("key", "")
    shift = int(params.get("shift", 0) or 0)

    if cipher == "atbash":
        out = "".join(_atbash_char(c, alphabet) for c in text)
    elif cipher == "cesar":
        out = "".join(_apply_shift(c, shift, alphabet) for c in text)
    elif cipher == "albam":
        # albam: atbash con desplazamiento = media del alfabeto activo
        # (11 para hebreo de 22; 12 griego de 24; 13 latino de 26)
        out = "".join(_apply_shift(c, len(alphabet) // 2, alphabet)
                      for c in text)
    elif cipher == "atbah":
        # atbah: rotacion por bloques 1-9,10-90,100-400 (hebreo 22 letras)
        def rot_atbah(ch: str) -> str:
            if ch not in dict(_HEBREW_LETTERS):
                return ch
            v = dict(_HEBREW_LETTERS)[ch]
            if v <= 9:
                nv = 10 - v
            elif v <= 90:
                nv = 100 - v
            else:
                nv = 500 - v
            for let, val in _HEBREW_LETTERS:
                if val == nv:
                    return let
            return ch
        out = "".join(rot_atbah(c) for c in text)
    elif cipher == "vigenere":
        if not key:
            return {"error": "vigenere requiere 'key'"}
        low_key = [k for k in key.lower() if k in alphabet.lower()]
        if not low_key:
            return {"error": "key sin letras del alfabeto"}
        decrypt = bool(params.get("decrypt", False))
        out = []
        ki = 0
        for c in text:
            if c.lower() in alphabet.lower():
                shift_k = alphabet.lower().index(low_key[ki % len(low_key)])
                if decrypt:
                    shift_k = -shift_k
                out.append(_apply_shift(c, shift_k, alphabet))
                ki += 1
            else:
                out.append(c)
        out = "".join(out)
        return {"cipher": cipher, "text": text, "result": out,
                "decrypt": decrypt, "note": DISCLAIMER}
    else:
        return {"error": f"cifrado desconocido: {cipher!r}",
                "ciphers": ["atbash", "albam", "atbah", "cesar", "vigenere"]}
    return {"cipher": cipher, "text": text, "result": out, "note": DISCLAIMER}


# ---------------------------------------------------------------------------
# 6) ANALISIS DE FRECUENCIA / IC / KASISKI
# ---------------------------------------------------------------------------

def _frequency(params: Dict[str, Any]) -> Dict[str, Any]:
    text = str(params.get("text", "")).lower()
    alphabet = params.get("alphabet", _LATIN).lower()
    counts = {c: 0 for c in alphabet}
    total = 0
    for ch in text:
        if ch in counts:
            counts[ch] += 1
            total += 1
    freq = {c: (n / total if total else 0.0) for c, n in counts.items()}
    return {"total": total, "counts": counts, "relative_freq": freq}


def _index_of_coincidence(counts: Dict[str, int]) -> float:
    total = sum(counts.values())
    if total < 2:
        return 0.0
    num = sum(n * (n - 1) for n in counts.values())
    return num / (total * (total - 1))


# Frecuencias inglesas (orden alfabético a..z) para chi-cuadrado.
_EN = [0.0817, 0.0150, 0.0278, 0.0425, 0.1270, 0.0223, 0.0202,
       0.0609, 0.0697, 0.0015, 0.0077, 0.0403, 0.0241, 0.0675,
       0.0751, 0.0193, 0.0010, 0.0599, 0.0633, 0.0906, 0.0276,
       0.0098, 0.0236, 0.0015, 0.0197, 0.0007]


def _chi2(counts: Dict[str, int], expected: List[float]) -> float:
    """Chi-cuadrado de frecuencias; expected normalizado (suma 1) por letra."""
    total = sum(counts.values())
    if total == 0:
        return float("inf")
    chi = 0.0
    for c, exp in zip(sorted(counts), expected):
        obs = counts[c]
        e = exp * total
        if e > 0:
            chi += (obs - e) ** 2 / e
    return chi


def _analyze(params: Dict[str, Any]) -> Dict[str, Any]:
    analysis = params.get("analysis")
    text = str(params.get("text", ""))
    alphabet = params.get("alphabet", _LATIN)
    if analysis == "frequency":
        return _frequency(params)
    if analysis == "ic":
        counts = _frequency(params)["counts"]
        return {"analysis": "ic", "ic": _index_of_coincidence(counts),
                "note": "IC~0.066 english, ~0.038 random"}
    if analysis == "caesar_break":
        # IC es invariante ante el desplazamiento -> ranking por chi-cuadrado
        # contra frecuencias esperadas (inglés por defecto).
        low = alphabet.lower()
        if len(low) == len(_LATIN) and low == _LATIN:
            expected = list(_EN)
            note = "chi-cuadrado vs frecuencias inglesas"
        else:
            exp = params.get("expected")
            if not exp or len(exp) != len(low):
                return {
                    "error": "caesar_break para alfabeto no-latino requiere "
                             "'expected' (frecuencias por letra, misma longitud "
                             "y orden que 'alphabet')",
                    "example": {"alphabet": "αβγδεζηθικλμνξοπρστυφχψω",
                                "expected": [0.0]*24},
                }
            expected = [float(x) for x in exp]
            ssum = sum(expected)
            if ssum <= 0:
                return {"error": "'expected' debe sumar > 0"}
            expected = [x / ssum for x in expected]
            note = "chi-cuadrado vs 'expected' del usuario"
        best = []
        for s in range(len(alphabet)):
            dec = "".join(_apply_shift(c, -s, alphabet) for c in text)
            counts = {c: 0 for c in low}
            for ch in dec.lower():
                if ch in counts:
                    counts[ch] += 1
            chi = _chi2(counts, expected)
            best.append({"shift": s, "chi2": chi,
                         "ic": _index_of_coincidence(counts),
                         "candidate": dec})
        best.sort(key=lambda x: x["chi2"])
        return {"analysis": "caesar_break", "top": best[:5], "note": note}
    if analysis == "kasiski":
        low = alphabet.lower()
        s = "".join(c for c in text.lower() if c in low)
        trigrams: Dict[str, List[int]] = {}
        for i in range(len(s) - 2):
            t = s[i:i + 3]
            trigrams.setdefault(t, []).append(i)
        gaps = []
        repeats = []
        for t, pos in trigrams.items():
            if len(pos) > 1:
                repeats.append({"trigram": t, "positions": pos})
                for a, b in zip(pos, pos[1:]):
                    gaps.append(b - a)
        gcd_all = 0
        for g in gaps:
            gcd_all = math.gcd(gcd_all, g)
        # longitudes de clave candidatas: L en [2,20] con mas gaps divisibles
        scored = []
        for L in range(2, 21):
            hits = sum(1 for g in gaps if g % L == 0)
            if hits:
                scored.append({"length": L, "gaps_divisible": hits})
        scored.sort(key=lambda x: (-x["gaps_divisible"], x["length"]))
        return {"analysis": "kasiski", "repeats": repeats,
                "gap_gcd": gcd_all,
                "key_length_candidates": [d["length"] for d in scored],
                "key_length_scores": scored,
                "note": "key_length_candidates ordenado por gaps divisibles; "
                        "gap_gcd suele ser multiplo de la longitud de clave"}
    return {"error": f"analysis desconocido: {analysis!r}",
            "analyses": ["frequency", "ic", "caesar_break", "kasiski"]}


# ---------------------------------------------------------------------------
# 7) GENERADOR DE CODIGO (python / octave / bend)
# ---------------------------------------------------------------------------

def _codegen_python(system: str) -> str:
    """Genera un modulo python autocontenido con encode/decode + test."""
    if system == "babilonico":
        body = '''
BAB_ONE, BAB_TEN, BAB_ZERO = "\\U00012079", "\\U0001230B", "\\u00b7"

def encode(n):
    if n < 0: raise ValueError("rango [0,inf)")
    if n == 0: return BAB_ZERO
    groups = []
    while n > 0:
        n, d = divmod(n, 60); groups.append(d)
    groups.reverse(); out = []
    for d in groups:
        if d == 0: out.append(BAB_ZERO)
        else:
            if d >= 60: raise ValueError("grupo mixto >=60")
            t, o = divmod(d, 10); out.append(BAB_TEN * t + BAB_ONE * o)
    return " ".join(out)

def decode(text):
    if text.strip() == BAB_ZERO: return 0
    total = 0
    for g in text.split():
        d = g.count(BAB_TEN) * 10 + g.count(BAB_ONE)
        if d >= 60: raise ValueError("grupo mixto >=60")
        total = total * 60 + d
    return total
'''
    elif system == "romano":
        body = '''
_VALS = [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),
         (50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]
_ROM = {"I":1,"V":5,"X":10,"L":50,"C":100,"D":500,"M":1000}

def encode(n):
    if not (1 <= n <= 3999): raise ValueError("rango [1,3999]")
    out = []
    for v, s in _VALS:
        while n >= v: out.append(s); n -= v
    return "".join(out)

def decode(text):
    text = text.upper()
    if any(c not in _ROM for c in text): raise ValueError("letra romana inválida")
    vals = [_ROM[c] for c in text]
    t = 0
    for i, v in enumerate(vals):
        t += -v if v < (vals[i+1] if i+1 < len(vals) else 0) else v
    # canonicidad: re-encode debe dar el mismo texto
    if encode(t) != text: raise ValueError("forma romana no canónica")
    return t
'''
    elif system == "hebreo":
        body = '''
_GERESH, _GERSHAYIM = "\\u05f3", "\\u05f4"
_LET = {"\\u05d0":1,"\\u05d1":2,"\\u05d2":3,"\\u05d3":4,"\\u05d4":5,"\\u05d5":6,
        "\\u05d6":7,"\\u05d7":8,"\\u05d8":9,"\\u05d9":10,"\\u05db":20,"\\u05dc":30,
        "\\u05de":40,"\\u05e0":50,"\\u05e1":60,"\\u05e2":70,"\\u05e4":80,"\\u05e6":90,
        "\\u05e7":100,"\\u05e8":200,"\\u05e9":300,"\\u05ea":400}
_FIN = {"\\u05da":500,"\\u05dd":600,"\\u05df":700,"\\u05e3":800,"\\u05e5":900}
_FIN_BASE = {"\\u05da":20,"\\u05dd":40,"\\u05df":50,"\\u05e3":80,"\\u05e5":90}
_HUND = {1:"\\u05e7",2:"\\u05e8",3:"\\u05e9",4:"\\u05ea",
         5:"\\u05ea\\u05e7",6:"\\u05ea\\u05e8",7:"\\u05ea\\u05e9",8:"\\u05ea\\u05ea",
         9:"\\u05ea\\u05ea\\u05e7"}
_TENS = {1:"\\u05d9",2:"\\u05db",3:"\\u05dc",4:"\\u05de",5:"\\u05e0",
         6:"\\u05e1",7:"\\u05e2",8:"\\u05e4",9:"\\u05e6"}
_ONES = {1:"\\u05d0",2:"\\u05d1",3:"\\u05d2",4:"\\u05d3",5:"\\u05d4",
         6:"\\u05d5",7:"\\u05d6",8:"\\u05d7",9:"\\u05d8"}

def encode(n, gershayim=True):
    if not (1 <= n <= 9999): raise ValueError("rango [1,9999]")
    prefix = ""
    if n >= 1000:
        prefix = _ONES[n // 1000] + _GERESH
        n %= 1000
    h, r = divmod(n, 100)
    t, o = divmod(r, 10)
    parts = []
    if h: parts.append(_HUND[h])
    if t == 1 and o in (5, 6):
        parts.append(_ONES[9] + _ONES[o + 1])  # 15=ט+ו, 16=ט+ז
    else:
        if t: parts.append(_TENS[t])
        if o: parts.append(_ONES[o])
    tail = "".join(parts)
    if gershayim and len(tail) >= 2:
        tail = tail[:-1] + _GERSHAYIM + tail[-1]
    return prefix + tail

def decode(text):
    s = text.strip().replace(_GERSHAYIM, "")
    tot, i = 0, 0
    while i < len(s):
        ch = s[i]
        nxt = s[i+1] if i+1 < len(s) else ""
        if ch in _FIN and nxt == _GERESH:
            tot += _FIN[ch]; i += 2
        elif nxt == _GERESH:
            tot += _LET[ch] * 1000; i += 2
        elif ch in _FIN:
            tot += _FIN_BASE[ch]; i += 1
        elif ch in _LET:
            tot += _LET[ch]; i += 1
        elif ch == _GERESH:
            i += 1
        else:
            raise ValueError(ch)
    return tot
'''
    else:
        return f"error: codegen python no soporta sistema {system!r}"

    if system == "hebreo":
        main = ("if __name__ == '__main__':\n"
                "    assert decode(encode(1234)) == 1234\n"
                "    assert decode(encode(376)) == 376\n"
                "    assert encode(15) == '\\u05d8\\u05f4\\u05d5'  # ט״ו\n"
                "    assert encode(16) == '\\u05d8\\u05f4\\u05d6'  # ט״ז\n"
                "    assert encode(900, gershayim=False) == '\\u05ea\\u05ea\\u05e7'  # תתק\n"
                "    assert encode(2026, gershayim=False) == '\\u05d1\\u05f3\\u05db\\u05d5'  # ב׳כו\n"
                "    assert encode(2026) == '\\u05d1\\u05f3\\u05db\\u05f4\\u05d5'  # ב׳כ״ו\n"
                "    assert encode(2001) == '\\u05d1\\u05f3\\u05d0'  # ב׳א (una sola letra tras miles: sin ״)\n"
                "    assert decode('\\u05e9\\u05dc\\u05d5\\u05dd') == 376  # שלום\n"
                "    print('PYTHON_CODEGEN_OK')\n")
    elif system == "babilonico":
        main = ("if __name__ == '__main__':\n"
                "    assert len(BAB_ONE) == 1 and ord(BAB_ONE) == 0x12079\n"
                "    assert len(BAB_TEN) == 1 and ord(BAB_TEN) == 0x1230B\n"
                "    assert len(BAB_ZERO) == 1 and ord(BAB_ZERO) == 0x00B7\n"
                "    assert decode(encode(1234)) == 1234\n"
                "    assert decode(encode(0)) == 0\n"
                "    for n in range(0, 100000):\n"
                "        assert decode(encode(n)) == n, n\n"
                "    print('PYTHON_CODEGEN_OK')\n")
    elif system == "romano":
        main = ("if __name__ == '__main__':\n"
                "    assert decode(encode(1234)) == 1234\n"
                "    for n in range(1, 4000):\n"
                "        assert decode(encode(n)) == n, n\n"
                "    try:\n"
                "        decode('IC'); assert False\n"
                "    except ValueError: pass\n"
                "    try:\n"
                "        decode('IIII'); assert False\n"
                "    except ValueError: pass\n"
                "    print('PYTHON_CODEGEN_OK')\n")
    else:
        main = ("if __name__ == '__main__':\n"
                "    assert decode(encode(1234)) == 1234\n"
                "    assert decode(encode(376)) == 376\n"
                "    print('PYTHON_CODEGEN_OK')\n")

    return (
        "# Generado por ancient_numeral_crypto_tool -- historico/educativo\n"
        + body + "\n\n"
        + main
    )


def _codegen_bend(system: str) -> str:
    """Genera un programa Bend2 self-contained (conversion base-60 exacta).

    Bend2 no tiene `if`; se usa match sobre Bool/Nat con fuel. El core es
    b60_encode/b60_decode (enteros U32 <-> digitos empaquetados base-1000).

    Limite U32: los digitos base-60 se empaquetan en base-1000 y el lugar
    1000^3 alcanza 5 desbordes; n debe ser < 1_080_000 (4 digitos base-60:
    59*1000^3 = 59e9 > 2^32; 1_079_999 = 4,59,59,59 lo maximo seguro;
    empaquetado 4_059_059_059 < 2^32).
    """
    if system not in ("babilonico", "bend", "base60"):
        return f"error: codegen bend solo soporta babilonico/base60 (pidio {system!r})"
    return '''import Base

def b60_encode_go(fuel: Nat, +n: U32, +acc: U32, +place: U32, small: Bool) -> U32:
  match fuel:
    case 0n:
      acc
    case 1n+p:
      match small:
        case True{}:
          (acc + n * place : U32)
        case False{}:
          b60_encode_go(p, U32.div(n, 60), (acc + U32.mod(n, 60) * place : U32), (place * 1000 : U32), U32.is_lt(U32.div(n, 60), 60))

def b60_encode(+n: U32) -> U32:
  b60_encode_go(10n, n, 0, 1, U32.is_lt(n, 60))

def b60_decode_go(fuel: Nat, +p: U32, +acc: U32, +base: U32, small: Bool) -> U32:
  match fuel:
    case 0n:
      acc
    case 1n+p_fuel:
      match small:
        case True{}:
          (acc + p * base : U32)
        case False{}:
          b60_decode_go(p_fuel, U32.div(p, 1000), (acc + U32.mod(p, 1000) * base : U32), (base * 60 : U32), U32.is_lt(U32.div(p, 1000), 1000))

def b60_decode(+p: U32) -> U32:
  b60_decode_go(10n, p, 0, 1, U32.is_lt(p, 1000))

def main() -> Bool:
  U32.is_eq(b60_decode(b60_encode(1079999)), 1079999)
'''


def _codegen_numeral(params: Dict[str, Any]) -> Dict[str, Any]:
    system = params.get("system", "babilonico")
    language = params.get("language", "python")
    if language == "python":
        code = _codegen_python(system)
    elif language == "bend":
        code = _codegen_bend(system)
    elif language == "octave":
        return {"error": "codegen octave pendiente: use python o bend"}
    else:
        return {"error": f"language desconocido: {language!r}",
                "languages": ["python", "bend", "octave"]}
    if code.startswith("error:"):
        return {"error": code}
    return {"system": system, "language": language, "code": code,
            "note": DISCLAIMER}


# ---------------------------------------------------------------------------
# 8) VALIDACION (self-tests)
# ---------------------------------------------------------------------------

def _find_bend() -> str:
    # Bend 2 vive en ~/.bend/bin/bend; ~/.cargo/bin/bend es una version 1 vieja.
    cand = str(Path.home() / ".bend" / "bin" / "bend")
    if os.path.exists(cand):
        return cand
    return shutil.which("bend") or ""


def _run_bend_check(code: str) -> Dict[str, Any]:
    bend = _find_bend()
    if not bend or not os.path.exists(bend):
        return {"ran": False, "reason": "bend no disponible"}
    with tempfile.NamedTemporaryFile("w", suffix=".bend", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        chk = subprocess.run([bend, path, "--check-only"],
                             capture_output=True, text=True, timeout=60)
        run = subprocess.run([bend, path],
                             capture_output=True, text=True, timeout=60)
        return {"ran": True,
                "check_ok": chk.returncode == 0,
                "check_out": (chk.stdout + chk.stderr).strip(),
                "run_ok": run.returncode == 0,
                "run_out": (run.stdout + run.stderr).strip()}
    except Exception as e:  # pragma: no cover
        return {"ran": False, "reason": str(e)}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _run_python_check(code: str) -> Dict[str, Any]:
    python = shutil.which("python3") or "python3"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        run = subprocess.run([python, path],
                             capture_output=True, text=True, timeout=30)
        return {"ran": True, "ok": run.returncode == 0,
                "out": (run.stdout + run.stderr).strip()}
    except Exception as e:  # pragma: no cover
        return {"ran": False, "reason": str(e)}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _validate(params: Dict[str, Any]) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    def check(name: str, fn: Callable[[], bool]) -> None:
        try:
            ok = bool(fn())
        except Exception as e:
            ok = False
            checks.append({"name": name, "ok": False, "error": str(e)})
            return
        checks.append({"name": name, "ok": ok})

    def _raises(fn: Callable[..., Any], *args: Any, **kw: Any) -> bool:
        try:
            fn(*args, **kw)
            return False
        except ValueError:
            return True

    # round-trips por sistema
    samples = [1, 5, 9, 15, 16, 42, 99, 100, 376, 500, 999, 1000, 2019,
               3999, 4000, 4085, 66, 786, 1234]
    for sysname, sysd in _SYSTEMS.items():
        def rt(sd=sysd, name=sysname):
            for n in samples:
                try:
                    s = sd["enc"](n)
                except ValueError:
                    # fuera del rango valido de ese sistema (ej. romano <4000)
                    continue
                if sd["dec"](s) != n:
                    return False
            return True
        check(f"roundtrip_{sysname}", rt)

    # vectors historicos
    check("griego_2019", lambda: _greek_decode("͵βιθʹ") == 2019)
    check("griego_373", lambda: _greek_decode("λογος") == 373)
    check("griego_nfc_373", lambda: _greek_decode("λόγος") == 373)
    check("griego_9999_max", lambda: _greek_decode(_greek_encode(9999)) == 9999
          and _greek_decode("͵θϡϟθʹ") == 9999)
    check("griego_reject_10000", lambda: _raises(_greek_encode, 10000))
    check("hebreo_376", lambda: _hebrew_decode("שלום") == 376)
    check("hebreo_encode_376", lambda: _hebrew_decode(_hebrew_encode(376)) == 376)
    check("hebreo_decode_nikud",
          lambda: _hebrew_decode("שָׁלוֹם") == 376)  # nikud no rompe decode
    check("hebreo_decode_keeps_geresh",
          lambda: _hebrew_decode("ב׳א") == 2001
          and _hebrew_decode(_hebrew_encode(5786, gershayim=False,
                                            style="sofit")) == 5786)
    check("abjad_allah", lambda: sum(_ABJAD_AR.get(c, 0) for c in "الله") == 66)
    check("abjad_bism", lambda: sum(
        _ABJAD_AR.get(c, 0) for c in "بسم الله الرحمن الرحيم") == 786)
    check("abjad_zah_ghayn",
          lambda: _ABJAD_AR["ظ"] == 900 and _ABJAD_AR["غ"] == 1000)
    check("abjad_alphabet_sum_5995",
          lambda: sum(_ABJAD_AR.values()) == 5995)
    check("babylonian_2019", lambda: _babylonian_decode(
        _babylonian_encode(2019)) == 2019)
    check("sexagesimal_040x130", lambda: (
        _parse_sexagesimal("0;40") * _parse_sexagesimal("1;30")
        == Fraction(1, 1)))
    check("sexagesimal_1_8", lambda: (
        _to_sexagesimal(Fraction(1, 8)) == "0;7,30"))
    check("sexagesimal_1_7_inexact", lambda: (
        not _sexagesimal_arith({"a": "1", "b": "7", "op": "div"}
                               )["terminates_sexagesimal"]))
    check("atbash_shebo_bavel",
          # normalizacion quita nikud: שׁשׁך -> ששך -> atbash -> בבל
          lambda: _cipher({"cipher": "atbash", "text": "שׁשׁך"})["result"] == "בבל"
          and _cipher({"cipher": "atbash", "text": "ששך"})["result"] == "בבל")
    check("atbash_latin_abc", lambda: _cipher(
        {"cipher": "atbash", "text": "abc"})["result"] == "zyx")
    check("vigenere_vector_attack", lambda: _cipher(
        {"cipher": "vigenere", "text": "ATTACKATDAWN", "key": "LEMON"}
    )["result"] == "LXFOPVEFRNHR")
    check("vigenere_decrypt_roundtrip", lambda: _cipher(
        {"cipher": "vigenere", "text": "LXFOPVEFRNHR", "key": "LEMON",
         "decrypt": True})["result"] == "ATTACKATDAWN")
    check("atbah_abg", lambda: _cipher(
        {"cipher": "atbah", "text": "אבג"})["result"] == "טחז")

    # --- ciclo 5: fixes de review del usuario (codegen 2001, albam, gematria griega) ---
    def _gen_encode_2001():
        ns: dict = {}
        exec(compile(_codegen_python("hebreo"), "<gen>", "exec"), ns)
        return ns["encode"](2001) == "ב׳א"
    check("codegen_hebreo_2001_single", _gen_encode_2001)
    check("albam_half_len_hebrew", lambda: _cipher(
        {"cipher": "albam", "text": "שלום"})["result"] == "יאפב")
    check("albam_half_len_latin", lambda: _cipher(
        {"cipher": "albam", "text": "abc"})["result"] == "nop")  # 13 de 26
    check("albam_half_len_greek", lambda: _cipher(
        {"cipher": "albam", "text": "αβγ"})["result"] == "νξο")  # 12 de 24
    check("gematria_griego_spaces",
          # suma directa: no lanza con espacios/puntuacion (antes usaba decode)
          lambda: _gematria({"system": "griego", "text": "λόγος χωρίς"}
                            )["value"] == 373 + 1710)
    check("albam_latin_a_to_n", lambda: _cipher(
        {"cipher": "albam", "text": "a"})["result"] == "n")
    check("gematria_griego_estin",
          # λόγος=373, ἐστίν=5+200+300+10+50=565 -> 938
          lambda: _gematria({"system": "griego", "text": "λόγος ἐστίν"}
                            )["value"] == 938)

    # --- ciclo 2: egipcio 25, gematria, sexagesimal coma, analyze ---
    check("egipcio_25_2dec_5und", lambda:
          _egyptian_encode(25) == "𓎆𓎆" + "𓏺" * 5)
    check("egipcio_25_decode", lambda: _egyptian_decode(_egyptian_encode(25)) == 25)
    check("hebreo_encode_2001_single", lambda: _hebrew_encode(2001) == "ב׳א")
    check("gematria_hebrew_shalom_376",
          lambda: _gematria({"system": "hebrew", "text": "שלום"})["value"] == 376)
    check("gematria_hebrew_gadol_mem", lambda:
          _gematria({"system": "hebrew", "text": "ם", "gadol": True}
                    )["value"] == 600
          and _gematria({"system": "hebrew", "text": "ם"})["value"] == 40)
    check("gematria_hebrew_ignores_nikud",
          lambda: _gematria({"system": "hebrew", "text": "שָׁלוֹם"}
                            )["value"] == 376)
    check("gematria_abjad_kaf_20",
          lambda: _gematria({"system": "abjad", "text": "ك"})["value"] == 20)
    check("gematria_persa_kaf_gaf", lambda:
          _gematria({"system": "persa", "text": "ک"})["value"] == 20
          and _gematria({"system": "persa", "text": "گ"})["value"] == 20
          and _gematria({"system": "persa", "text": "ی"})["value"] == 10)
    check("gematria_persa_tashkeel_ignored",
          lambda: _gematria({"system": "persa", "text": "بِ"})["value"] == 2)
    check("gematria_abjad_ta_marbuta_5", lambda:
          _gematria({"system": "abjad", "text": "ة"})["value"] == 5
          and _gematria({"system": "abjad", "text": "ة", "ta_marbuta": 400}
                        )["value"] == 400)
    check("sexagesimal_coma_base60", lambda:
          _parse_sexagesimal("1,30;15") == Fraction(361, 4))
    check("sexagesimal_reciprocal_2", lambda:
          _sexagesimal_arith({"a": "2", "op": "reciprocal"}
                             )["result_sexagesimal"] == "0;30")
    _long_caesar = ("the quick brown fox jumps over the lazy dog and then "
                    "runs away into the forest")
    check("caesar_break_chi2_english", lambda: (
        _analyze({"analysis": "caesar_break",
                  "text": _cipher({"cipher": "cesar", "text": _long_caesar,
                                   "shift": 3})["result"]})["top"][0]
        ["candidate"].lower() == _long_caesar))
    check("caesar_break_requires_expected_nonlatin", lambda: (
        "error" in _analyze({"analysis": "caesar_break", "text": "αβγ",
                             "alphabet": _ALPHABETS["greek"]})))
    check("kasiski_key_length_candidates", lambda: (
        len(_analyze({"analysis": "kasiski",
                      "text": "the attack was at dawn and again at dawn "
                              "the attack"})["key_length_candidates"]) > 0))

    # numeral_convert hebreo conserva style/gershayim en su validacion
    check("numeral_convert_hebreo_sofit_style", lambda:
          _numeral_convert({"system": "hebreo", "mode": "encode", "value": 700,
                            "style": "sofit", "gershayim": False}
                           )["text"] == "ן׳")

    # --- hebreo: formas conocidas, rechazos, roundtrips exhaustivos ---
    check("hebreo_encode_15_gershayim",
          lambda: _hebrew_encode(15) == "ט״ו")
    check("hebreo_encode_16_gershayim",
          lambda: _hebrew_encode(16) == "ט״ז")
    check("hebreo_encode_15_bare",
          lambda: _hebrew_encode(15, gershayim=False) == "טו")
    check("hebreo_encode_16_bare",
          lambda: _hebrew_encode(16, gershayim=False) == "טז")
    check("hebreo_encode_900_bare",
          lambda: _hebrew_encode(900, gershayim=False) == "תתק")
    check("hebreo_encode_900_gershayim",
          lambda: _hebrew_encode(900) == "תת״ק")
    check("hebreo_encode_2026_bare",
          lambda: _hebrew_encode(2026, gershayim=False) == "ב׳כו")
    check("hebreo_encode_2026_gershayim",
          lambda: _hebrew_encode(2026) == "ב׳כ״ו")
    check("hebreo_encode_415_bare",
          lambda: _hebrew_encode(415, gershayim=False) == "תטו")
    check("hebreo_encode_5786_gershayim",
          lambda: _hebrew_encode(5786) == "ה׳תשפ״ו")

    def _raises_hebrew_strict(text: str) -> bool:
        try:
            _hebrew_decode(text, strict=True)
            return False
        except ValueError:
            return True
    check("hebreo_strict_reject_יה", lambda: _raises_hebrew_strict("יה"))
    check("hebreo_strict_reject_יו", lambda: _raises_hebrew_strict("יו"))
    check("hebreo_strict_reject_קק", lambda: _raises_hebrew_strict("קק"))
    check("hebreo_strict_reject_א׳א׳", lambda: _raises_hebrew_strict("א׳א׳"))
    check("hebreo_strict_accept_ט״ו",
          lambda: _hebrew_decode("ט״ו", strict=True) == 15)
    check("hebreo_strict_accept_טו",
          lambda: _hebrew_decode("טו", strict=True) == 15)
    check("hebreo_sofit_700",
          lambda: _hebrew_encode(700, gershayim=False, style="sofit") == "ן׳")
    check("hebreo_sofit_5786_roundtrip", lambda: _hebrew_decode(
        _hebrew_encode(5786, gershayim=False, style="sofit")) == 5786)

    def hebrew_rt_exhaustive() -> bool:
        for n in range(1, 10000):
            for style in ("standard", "sofit"):
                for g in (True, False):
                    s = _hebrew_encode(n, gershayim=g, style=style)
                    if _hebrew_decode(s) != n:
                        return False
        return True
    check("hebreo_exhaustive_1_9999", hebrew_rt_exhaustive)

    # --- romano: roundtrip 1..3999 + rechazos (tool ya valida canonicidad) ---
    def roman_rt_full() -> bool:
        for n in range(1, 4000):
            if _roman_decode(_roman_encode(n)) != n:
                return False
        return True
    check("romano_exhaustive_1_3999", roman_rt_full)

    def _raises_roman(text: str) -> bool:
        try:
            _roman_decode(text)
            return False
        except ValueError:
            return True
    check("romano_reject_IC", lambda: _raises_roman("IC"))
    check("romano_reject_IIII", lambda: _raises_roman("IIII"))
    check("romano_reject_VV", lambda: _raises_roman("VV"))

    # --- babilonico: roundtrip 0..99999 + codepoints ---
    def bab_rt_full() -> bool:
        for n in range(0, 100000):
            if _babylonian_decode(_babylonian_encode(n)) != n:
                return False
        return True
    check("babilonico_exhaustive_0_99999", bab_rt_full)
    check("babilonico_codepoints",
          lambda: ord(_BAB_ONE) == 0x12079 and ord(BAB_TEN) == 0x1230B
          and BAB_ZERO == "·")

    # --- codegen python
    for sysname in ("babilonico", "romano", "hebreo"):
        def py(sysn=sysname):
            code = _codegen_python(sysn)
            r = _run_python_check(code)
            return r.get("ok", False)
        check(f"codegen_python_{sysname}", py)

    # codegen bend (check + run -> True)
    def bendc():
        code = _codegen_bend("babilonico")
        r = _run_bend_check(code)
        return r.get("check_ok", False) and r.get("run_ok", False) \
            and "True" in r.get("run_out", "")
    check("codegen_bend_b60", bendc)

    n_pass = sum(1 for c in checks if c["ok"])
    return {
        "mode": "validate", "n_checks": len(checks),
        "n_passed": n_pass, "checks": checks,
        "validation_passed": n_pass == len(checks),
        "note": DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# 9) SCHEMA Y DISPATCH / REGISTRO
# ---------------------------------------------------------------------------

TOOL_MODES = [
    "numeral_convert", "egyptian_fractions", "sexagesimal_arith",
    "gematria", "cipher", "analyze", "codegen_numeral", "validate",
]

TOOL_SCHEMA: Dict[str, Any] = {
    "name": TOOL_NAME,
    "description": (
        "Sistemas numericos y criptografia ancestral: numerales (babilonico, "
        "maya, egipcio, romano, griego jónico, hebreo, quipu), fracciones "
        "egipcias, aritmetica sexagesimal exacta, gematria (hebreo/griego/"
        "abjad/persa), cifrados clasicos (atbash/albam/atbah/cesar/vigenere), "
        "analisis de frecuencia/IC/Kasiski, y codegen del conversor en "
        "python/bend. Historico/educativo; los cifrados NO son seguros."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": TOOL_MODES,
                "description": "Modo a ejecutar.",
            },
            "params": {
                "type": "object",
                "description": (
                    "Parametros del modo. numeral_convert: {system, mode, "
                    "value|text, cords, style?, gershayim? (hebreo: "
                    "'standard'|'sofit', gershayim bool)}. "
                    "egyptian_fractions: {numerator, denominator}. "
                    "sexagesimal_arith: {a, b?, op} (b solo si op != "
                    "'reciprocal'). gematria: {system, text, gadol? (hebreo), "
                    "ta_marbuta? 5|400 (abjad/persa)}. cipher: {cipher, text, "
                    "key?, shift?, alphabet?, decrypt? (vigenere)}. "
                    "analyze: {analysis, text, expected? (caesar_break con "
                    "alfabeto no-latino: frecuencias por letra)}. "
                    "codegen_numeral: {system, language}. validate: {}."
                ),
            },
        },
        "required": ["mode"],
    },
}


def _dispatch(mode: str, params: Dict[str, Any]) -> Dict[str, Any]:
    handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
        "numeral_convert": _numeral_convert,
        "egyptian_fractions": _egyptian_fractions,
        "sexagesimal_arith": _sexagesimal_arith,
        "gematria": _gematria,
        "cipher": _cipher,
        "analyze": _analyze,
        "codegen_numeral": _codegen_numeral,
        "validate": _validate,
    }
    if mode not in handlers:
        return {"error": f"mode desconocido: {mode!r}", "modes": TOOL_MODES}
    return handlers[mode](params or {})


def run(arguments: Dict[str, Any]) -> Dict[str, Any]:
    mode = (arguments or {}).get("mode")
    params = (arguments or {}).get("params") or {}
    if not mode:
        return {"error": "falta 'mode'", "modes": TOOL_MODES}
    try:
        return _dispatch(mode, params)
    except Exception as e:  # pragma: no cover
        return {"error": str(e), "mode": mode}


try:
    from tool_registry import register_tool as _rt

    _rt(name=TOOL_NAME, schema=TOOL_SCHEMA, handler=run)
except ImportError:  # pragma: no cover
    pass


if __name__ == "__main__":
    # El registro ocurre una sola vez a nivel de modulo (arriba). Aqui solo
    # se corre la validacion para uso directo del archivo.
    result = _validate({})
    print(f"checks: {result['n_passed']}/{result['n_checks']} "
          f"passed={result['validation_passed']}")
