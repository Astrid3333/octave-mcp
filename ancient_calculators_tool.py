#!/usr/bin/env python3
"""
ancient_calculators_tool.py — Simuladores de dispositivos de calculo
historicos reales (no solo el algoritmo abstracto, sino el estado fisico
de cuentas/fichas del aparato), para que Octave pueda operar Y VALIDAR
usando la misma mecanica que usaban estas culturas.

Presets:
  suanpan            — abaco chino tradicional (2 cuentas "cielo" x5 + 5
                        cuentas "tierra" x1 por varilla), suma con acarreo
                        simulando el movimiento de cuentas.
  soroban             — abaco japones moderno (1 cuenta cielo x5 + 4 cuentas
                        tierra x1 por varilla) -- una cuenta menos que el
                        suanpan, sin redundancia.
  roman_hand_abacus   — abaco de mano romano: columnas decimal-quinarias
                        (I,X,C,M...) para la parte entera + una columna
                        duodecimal (unciae, doceavos) para fracciones,
                        replicando la estructura de los abacos de bronce
                        romanos conservados (ej. Louvre, British Museum).
  yupana_depasquale   — tabla de contar inca (yupana), segun la hipotesis
                        de Nicolino De Pasquale (2001) de un sistema base-40
                        con valores de campo tipo Fibonacci (1,2,3,5).
                        ADVERTENCIA: no hay consenso academico sobre el uso
                        real de la yupana -- hay multiples hipotesis en
                        competencia (Wassen 1931, Radicati 1951, Burns
                        Glynn 1981, De Pasquale 2001, Moscovich 2007,
                        Florio 2008, Chirinos 2010). Esta es solo una de
                        ellas, implementada como modelo didactico.

Sin numpy, stdlib pura.
"""
import math

ANCIENT_CALC_SCHEMA = {
    "name": "compute_ancient_calculator",
    "description": (
        "Simula dispositivos de calculo historicos reales operando sus "
        "cuentas/fichas segun la mecanica documentada de cada uno. Presets: "
        "suanpan (abaco chino 2/5), soroban (abaco japones 1/4), "
        "roman_hand_abacus (abaco romano decimal-quinario + fraccion "
        "duodecimal), yupana_depasquale (tabla inca, hipotesis De Pasquale, "
        "en disputa academica)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "preset": {
                "type": "string",
                "enum": ["suanpan", "soroban", "roman_hand_abacus", "yupana_depasquale"],
            },
            "params": {"type": "object"},
        },
        "required": ["preset"],
    },
}


# ---------------------------------------------------------------------------
# ABACOS DE CUENTAS (suanpan chino 2/5, soroban japones 1/4)
# Cada varilla: N cuentas "cielo" (valor 5 c/u) + M cuentas "tierra" (valor 1
# c/u). digito de la varilla = heaven_active*5 + earth_active. Suma con
# acarreo: se simula varilla por varilla, de derecha a izquierda, empujando
# cuentas y propagando acarreo cuando el digito resultante excede lo que la
# varilla puede representar sin overflow (>9 para uso decimal estandar).
# ---------------------------------------------------------------------------
def _digit_to_beads(digit, heaven_beads, earth_beads):
    """Descompone un digito 0-9 en cuentas activas: se usa como maximo 1
    cuenta cielo (valor 5) y el resto en cuentas tierra (valor 1), que es
    la representacion canonica (no redundante) usada en la practica."""
    if digit > heaven_beads * 5 + earth_beads:
        return None
    heaven_active = 1 if digit >= 5 and heaven_beads >= 1 else 0
    earth_active = digit - heaven_active * 5
    if earth_active > earth_beads:
        return None
    return {"heaven_active": heaven_active, "earth_active": earth_active,
            "heaven_available": heaven_beads, "earth_available": earth_beads}


def _abacus_encode(value, heaven_beads, earth_beads):
    if value < 0:
        return {"error": "solo enteros no negativos"}
    digits = [int(c) for c in str(value)] or [0]
    rods = []
    for d in digits:
        beads = _digit_to_beads(d, heaven_beads, earth_beads)
        if beads is None:
            return {"error": f"digito {d} no representable con {heaven_beads} cielo + {earth_beads} tierra"}
        rods.append({"digit": d, **beads})
    return {"value": value, "rods": rods}


def _abacus_add(a, b, heaven_beads, earth_beads):
    """Suma digito a digito de derecha a izquierda con acarreo, registrando
    en cada paso el estado de cuentas de la varilla (igual que un operador
    humano empujando cuentas y 'llevando' al acarrear)."""
    sa, sb = str(a), str(b)
    n = max(len(sa), len(sb))
    sa, sb = sa.zfill(n), sb.zfill(n)
    carry = 0
    result_digits = []
    steps = []
    for i in range(n - 1, -1, -1):
        da, db = int(sa[i]), int(sb[i])
        carry_in = carry
        raw = da + db + carry_in
        digit = raw % 10
        carry = raw // 10
        beads = _digit_to_beads(digit, heaven_beads, earth_beads)
        steps.append({"position_from_right": n - 1 - i, "a_digit": da, "b_digit": db,
                       "carry_in": carry_in, "raw_sum": raw,
                       "result_digit": digit, "carry_out": carry, "rod_state": beads})
        result_digits.append(digit)
    if carry:
        result_digits.append(carry)
        steps.append({"position_from_right": n, "note": "acarreo final -> nueva varilla",
                       "result_digit": carry, "rod_state": _digit_to_beads(carry, heaven_beads, earth_beads)})
    result = int("".join(str(d) for d in reversed(result_digits)))
    return {"a": a, "b": b, "result": result, "check": result == a + b, "steps": list(reversed(steps))}


def compute_suanpan(mode="add", value=None, a=None, b=None):
    """suanpan tradicional: 2 cuentas cielo (x5) + 5 cuentas tierra (x1) por
    varilla -- permite representaciones redundantes (hasta 15 por varilla)
    aunque para calculo estandar se normaliza a 0-9."""
    heaven, earth = 2, 5
    if mode == "encode":
        if value is None:
            return {"error": "mode='encode' requiere 'value'"}
        return _abacus_encode(value, heaven, earth)
    elif mode == "add":
        if a is None or b is None:
            return {"error": "mode='add' requiere 'a' y 'b'"}
        return _abacus_add(a, b, heaven, earth)
    else:
        return {"error": f"mode desconocido: {mode}"}


def compute_soroban(mode="add", value=None, a=None, b=None):
    """soroban japones moderno: 1 cuenta cielo (x5) + 4 cuentas tierra (x1)
    por varilla -- exactamente 0-9 sin redundancia, mas eficiente que el
    suanpan de 2/5 y estandarizado en Japon desde principios del s. XX."""
    heaven, earth = 1, 4
    if mode == "encode":
        if value is None:
            return {"error": "mode='encode' requiere 'value'"}
        return _abacus_encode(value, heaven, earth)
    elif mode == "add":
        if a is None or b is None:
            return {"error": "mode='add' requiere 'a' y 'b'"}
        return _abacus_add(a, b, heaven, earth)
    else:
        return {"error": f"mode desconocido: {mode}"}


# ---------------------------------------------------------------------------
# ABACO DE MANO ROMANO: columnas decimal-quinarias (I,X,C,M,...) para la
# parte entera (misma mecanica de cuentas 1x5+4x1 que suanpan/soroban, pero
# etiquetada con numeros romanos) + una columna duodecimal aparte (unciae,
# doceavos) para la parte fraccionaria -- estructura documentada en los
# abacos de bronce romanos conservados.
# ---------------------------------------------------------------------------
_ROMAN_PLACE_LABELS = ["I", "X", "C", "M", "X (mil.)", "C (mil.)"]


def compute_roman_hand_abacus(mode="add", integer_a=None, integer_b=None,
                               unciae_a=0, unciae_b=0):
    """Suma la parte entera con la misma mecanica decimal-quinaria de
    cuentas (1 cuenta valor-5 + 4 cuentas valor-1 por columna, etiquetada
    I/X/C/M...) y la parte fraccionaria en base 12 (unciae, 0-11 doceavos
    de as) por separado, como en el abaco romano real."""
    if mode != "add":
        return {"error": f"mode desconocido: {mode}"}
    if integer_a is None or integer_b is None:
        return {"error": "requiere 'integer_a' e 'integer_b'"}

    int_result = _abacus_add(integer_a, integer_b, heaven_beads=1, earth_beads=4)
    for step in int_result["steps"]:
        pos = step.get("position_from_right", 0)
        step["roman_column"] = _ROMAN_PLACE_LABELS[pos] if pos < len(_ROMAN_PLACE_LABELS) else f"10^{pos}"

    unciae_sum = unciae_a + unciae_b
    unciae_carry = unciae_sum // 12
    unciae_final = unciae_sum % 12

    return {
        "integer_part": int_result,
        "unciae_a": unciae_a, "unciae_b": unciae_b,
        "unciae_sum_raw": unciae_sum,
        "unciae_final": unciae_final,
        "unciae_carry_to_integer": unciae_carry,
        "total_integer": int_result["result"] + unciae_carry,
        "total_as_mixed": f"{int_result['result'] + unciae_carry} + {unciae_final}/12",
    }


# ---------------------------------------------------------------------------
# YUPANA (hipotesis De Pasquale 2001) -- ADVERTENCIA: en disputa academica.
# Modelo didactico simplificado: cada campo (columna dentro de una "fila")
# tiene un valor Fibonacci 1,2,3,5 y una capacidad maxima de fichas; el
# digito de la fila (0-39, sistema base 40) se descompone de forma voraz
# sobre esos 4 campos.
# ---------------------------------------------------------------------------
_YUPANA_FIELD_VALUES = [5, 3, 2, 1]  # de izquierda a derecha, orden Fibonacci
_YUPANA_FIELD_MAX_COUNTERS = 4  # limite didactico por campo (no consensuado)


def _yupana_encode_digit(digit):
    if not (0 <= digit <= 39):
        return None
    remaining = digit
    fields = []
    for value in _YUPANA_FIELD_VALUES:
        count = min(remaining // value, _YUPANA_FIELD_MAX_COUNTERS)
        remaining -= count * value
        fields.append({"field_value": value, "counters": count})
    if remaining != 0:
        return None  # no representable bajo este modelo simplificado
    return fields


def compute_yupana_depasquale(value):
    """Descompone 'value' en digitos base-40 (mas significativo primero) y
    cada digito en 4 campos de valores Fibonacci 1,2,3,5 (hipotesis De
    Pasquale). ADVERTENCIA explicita: esto es UNA interpretacion en disputa,
    no un hecho arqueologico establecido -- ver docstring del modulo."""
    if value < 0:
        return {"error": "solo enteros no negativos"}
    if value == 0:
        base40_digits = [0]
    else:
        base40_digits = []
        v = value
        while v > 0:
            base40_digits.append(v % 40)
            v //= 40
        base40_digits.reverse()

    rows = []
    for d in base40_digits:
        fields = _yupana_encode_digit(d)
        if fields is None:
            return {"error": f"digito base-40 {d} no representable bajo el modelo "
                              "simplificado de capacidad-4-por-campo"}
        rows.append({"base40_digit": d, "fields": fields})

    return {
        "value": value,
        "base40_digits_most_significant_first": base40_digits,
        "rows": rows,
        "warning": ("Hipotesis de De Pasquale (2001), NO consenso academico. "
                    "Interpretaciones alternativas: Wassen (1931), Radicati "
                    "(1951), Burns Glynn (1981), Moscovich (2007), Florio "
                    "(2008), Chirinos (2010) proponen mecanicas distintas."),
    }


def compute_ancient_calculator(preset, params=None):
    params = params or {}
    if preset == "suanpan":
        return compute_suanpan(**params)
    elif preset == "soroban":
        return compute_soroban(**params)
    elif preset == "roman_hand_abacus":
        return compute_roman_hand_abacus(**params)
    elif preset == "yupana_depasquale":
        return compute_yupana_depasquale(**params)
    else:
        return {"error": f"preset desconocido: {preset}"}
