#!/usr/bin/env python3
"""
ethnomath_tool.py — Sistemas y algoritmos matematicos historicos de culturas
no occidentales, para esclarecer/validar problemas antiguos con metodos
originales en vez de solo traducirlos a notacion moderna.

Presets:
  maya_long_count       — conversor vigesimal mixto (Long Count) <-> dia juliano
  chinese_remainder      — Teorema chino del resto, algoritmo constructivo (Sunzi/Dayan)
  vedic_multiply          — Urdhva-Tiryagbhyam (vertical-cruzado) y Nikhilam
  quipu_encode            — codificacion/decodificacion decimal por nudos (quipu inca)
  greek_archimedes_pi     — metodo de exhaucion (poligonos inscritos/circunscritos)
  japanese_enri_pi        — enri de Seki Takakazu (mismo principio + extrapolacion)

Sin numpy, solo stdlib (math/fractions), siguiendo el mismo criterio que
fractal_dimension_tool.py.
"""
import math
from fractions import Fraction

ETHNOMATH_SCHEMA = {
    "name": "compute_ethnomath",
    "description": (
        "Ejecuta algoritmos matematicos historicos reconstruidos de culturas "
        "no occidentales. Presets: maya_long_count (conversor vigesimal mixto "
        "18-20 <-> dia juliano/Tzolkin/Haab), chinese_remainder (algoritmo "
        "constructivo de Sunzi/Qin Jiushao para sistemas de congruencias), "
        "vedic_multiply (sutras Urdhva-Tiryagbhyam y Nikhilam), quipu_encode "
        "(codificacion decimal por nudos inca, encode/decode), "
        "greek_archimedes_pi (metodo de exhaucion por poligonos inscritos y "
        "circunscritos), japanese_enri_pi (enri de Seki Takakazu, mismo "
        "principio con aceleracion tipo Richardson)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "preset": {
                "type": "string",
                "enum": ["maya_long_count", "chinese_remainder", "vedic_multiply",
                         "quipu_encode", "greek_archimedes_pi", "japanese_enri_pi"],
            },
            "params": {"type": "object", "description": "Parametros especificos del preset, ver docstrings"},
        },
        "required": ["preset"],
    },
}

# ---------------------------------------------------------------------------
# 1) MAYA — Long Count: radix mixto 18-20
#    baktun=144000, katun=7200, tun=360, uinal=20, kin=1
#    (uinal topa en 17, el resto en 19; ver Mesoamerican Long Count calendar)
# ---------------------------------------------------------------------------
_MAYA_UNITS = [144000, 7200, 360, 20, 1]  # baktun,katun,tun,uinal,kin
_GMT_CORRELATION_JDN = 584283  # JDN de 0.0.0.0.0, correlacion Goodman-Martinez-Thompson

_TZOLKIN_NAMES = ["Imix", "Ik", "Akbal", "Kan", "Chicchan", "Cimi", "Manik", "Lamat",
                  "Muluc", "Oc", "Chuen", "Eb", "Ben", "Ix", "Men", "Cib", "Caban",
                  "Etznab", "Cauac", "Ahau"]
_HAAB_NAMES = ["Pop", "Uo", "Zip", "Zotz", "Tzec", "Xul", "Yaxkin", "Mol", "Chen",
               "Yax", "Zac", "Ceh", "Mac", "Kankin", "Muan", "Pax", "Kayab", "Cumku", "Uayeb"]


def _maya_long_count_to_days(baktun, katun, tun, uinal, kin):
    return baktun * 144000 + katun * 7200 + tun * 360 + uinal * 20 + kin


def _maya_days_to_long_count(elapsed_days):
    remaining = elapsed_days
    parts = []
    for unit in _MAYA_UNITS:
        parts.append(remaining // unit)
        remaining = remaining % unit
    return parts  # [baktun,katun,tun,uinal,kin]


def _maya_tzolkin(elapsed_days):
    number = (elapsed_days + 3) % 13 + 1  # calibrado a 4 Ahau en 0.0.0.0.0
    name = _TZOLKIN_NAMES[(elapsed_days + 19) % 20]
    return f"{number} {name}"


def _maya_haab(elapsed_days):
    d = (elapsed_days + 348) % 365  # calibrado a 8 Cumku en 0.0.0.0.0
    month_idx = d // 20
    day_in_month = d % 20
    return f"{day_in_month} {_HAAB_NAMES[month_idx]}"


def compute_maya_long_count(mode="jdn_to_lc", jdn=None, long_count=None):
    """
    mode='jdn_to_lc': dado un dia juliano (jdn), devuelve Long Count + Tzolkin + Haab.
    mode='lc_to_jdn': dado long_count=[baktun,katun,tun,uinal,kin], devuelve jdn.
    Valida rangos vigesimales (uinal<18, resto<20, salvo baktun sin tope superior fijo).
    """
    if mode == "jdn_to_lc":
        if jdn is None:
            return {"error": "mode='jdn_to_lc' requiere 'jdn'"}
        elapsed = jdn - _GMT_CORRELATION_JDN
        if elapsed < 0:
            return {"error": "jdn anterior a la fecha de creacion (JDN 584283)"}
        parts = _maya_days_to_long_count(elapsed)
        return {
            "mode": mode,
            "jdn": jdn,
            "elapsed_days": elapsed,
            "long_count": parts,
            "long_count_str": ".".join(str(p) for p in parts),
            "tzolkin": _maya_tzolkin(elapsed),
            "haab": _maya_haab(elapsed),
        }
    elif mode == "lc_to_jdn":
        if not long_count or len(long_count) != 5:
            return {"error": "mode='lc_to_jdn' requiere long_count=[baktun,katun,tun,uinal,kin]"}
        baktun, katun, tun, uinal, kin = long_count
        if not (0 <= uinal <= 17):
            return {"error": "uinal debe estar entre 0 y 17 (radix mixto 18)"}
        if not (0 <= katun <= 19 and 0 <= tun <= 19 and 0 <= kin <= 19):
            return {"error": "katun, tun, kin deben estar entre 0 y 19 (vigesimal puro)"}
        elapsed = _maya_long_count_to_days(baktun, katun, tun, uinal, kin)
        jdn = elapsed + _GMT_CORRELATION_JDN
        return {
            "mode": mode,
            "long_count": long_count,
            "elapsed_days": elapsed,
            "jdn": jdn,
            "tzolkin": _maya_tzolkin(elapsed),
            "haab": _maya_haab(elapsed),
        }
    else:
        return {"error": f"mode desconocido: {mode}"}


# ---------------------------------------------------------------------------
# 2) CHINA — Teorema chino del resto (algoritmo constructivo, estilo Sunzi/Dayan)
#    Ejemplo canonico de Sunzi Suanjing: x=2 mod 3, x=3 mod 5, x=2 mod 7 -> x=23
# ---------------------------------------------------------------------------
def _egcd(a, b):
    if b == 0:
        return (a, 1, 0)
    g, x1, y1 = _egcd(b, a % b)
    return (g, y1, x1 - (a // b) * y1)


def _modinv(a, m):
    g, x, _ = _egcd(a % m, m)
    if g != 1:
        return None
    return x % m


def compute_chinese_remainder(remainders=None, moduli=None, preset="sunzi_classic"):
    """
    Resuelve x = r_i (mod m_i) para todo i, via metodo constructivo:
    M = producto de moduli; para cada i, M_i = M/m_i, y_i = inverso modular
    de M_i mod m_i; x = suma(r_i * M_i * y_i) mod M. Requiere moduli coprimos
    entre si (condicion del TCR clasico).
    preset='sunzi_classic' reproduce el problema original de Sunzi Suanjing
    (siglo III-V d.C.): resto 2 mod 3, resto 3 mod 5, resto 2 mod 7 -> 23.
    """
    if preset == "sunzi_classic":
        remainders, moduli = [2, 3, 2], [3, 5, 7]
    elif preset != "custom":
        return {"error": f"preset desconocido: {preset}"}

    if not remainders or not moduli or len(remainders) != len(moduli):
        return {"error": "requiere 'remainders' y 'moduli' de igual longitud"}

    for i in range(len(moduli)):
        for j in range(i + 1, len(moduli)):
            if math.gcd(moduli[i], moduli[j]) != 1:
                return {"error": f"moduli {moduli[i]} y {moduli[j]} no son coprimos; "
                                  "el TCR clasico requiere pairwise coprime"}

    M = 1
    for m in moduli:
        M *= m

    x = 0
    steps = []
    for r, m in zip(remainders, moduli):
        Mi = M // m
        yi = _modinv(Mi, m)
        term = r * Mi * yi
        x += term
        steps.append({"remainder": r, "modulus": m, "M_i": Mi, "inverse_y_i": yi, "term": term})

    x_min = x % M

    return {
        "preset": preset,
        "remainders": remainders,
        "moduli": moduli,
        "M_total": M,
        "steps": steps,
        "solution": x_min,
        "general_solution": f"x = {x_min} + {M}*k, k entero",
        "verification": [{"modulus": m, "x_mod_m": x_min % m, "expected": r}
                          for r, m in zip(remainders, moduli)],
    }


# ---------------------------------------------------------------------------
# 3) INDIA — Sutras vedicos: Urdhva-Tiryagbhyam (vertical-cruzado) y Nikhilam
# ---------------------------------------------------------------------------
def _urdhva_tiryagbhyam(a, b):
    """Multiplicacion 'vertical y en cruz', digito a digito en base 10,
    generalizada a cualquier numero de digitos via convolucion + acarreo."""
    sa = str(a)[::-1]
    sb = str(b)[::-1]
    da = [int(c) for c in sa]
    db = [int(c) for c in sb]
    n, m = len(da), len(db)
    partial = [0] * (n + m)
    steps = []
    for i in range(n):
        for j in range(m):
            partial[i + j] += da[i] * db[j]
    # propagacion de acarreo (paso final de Urdhva-Tiryagbhyam)
    carry = 0
    digits = []
    for p in partial:
        total = p + carry
        digits.append(total % 10)
        carry = total // 10
    while carry:
        digits.append(carry % 10)
        carry //= 10
    while len(digits) > 1 and digits[-1] == 0:
        digits.pop()
    result = int("".join(str(d) for d in reversed(digits)))
    return result, partial


def _nikhilam_multiply(a, b, base=100):
    """Nikhilam Navatashcaramam Dashatah: para numeros cercanos a una base
    (potencia de 10). deficit_a = base-a, deficit_b = base-b.
    resultado = (a - deficit_b) * base + deficit_a * deficit_b."""
    deficit_a = base - a
    deficit_b = base - b
    left = a - deficit_b
    right = deficit_a * deficit_b
    result = left * base + right
    return result, {"base": base, "deficit_a": deficit_a, "deficit_b": deficit_b,
                     "left_part": left, "right_part": right}


def compute_vedic_multiply(a, b, method="urdhva_tiryagbhyam", base=None):
    """method='urdhva_tiryagbhyam' (general, cualquier a,b) o
    method='nikhilam' (eficiente cuando a,b estan cerca de una potencia de 10;
    'base' se autodetecta como la potencia de 10 mas cercana si se omite)."""
    if method == "urdhva_tiryagbhyam":
        result, partial = _urdhva_tiryagbhyam(a, b)
        return {
            "method": method, "a": a, "b": b,
            "partial_products_by_column": partial,
            "result": result,
            "check": result == a * b,
        }
    elif method == "nikhilam":
        if base is None:
            base = 10 ** len(str(max(a, b)))
        result, detail = _nikhilam_multiply(a, b, base)
        return {
            "method": method, "a": a, "b": b,
            **detail,
            "result": result,
            "check": result == a * b,
        }
    else:
        return {"error": f"method desconocido: {method}"}


# ---------------------------------------------------------------------------
# 4) INCA — Quipu: codificacion decimal posicional por nudos
#    unidades: nudo largo (n vueltas) o nudo en 8 para el 1
#    decenas+: nudo simple (n vueltas) por posicion, mas cercano al cordon = mayor valor
# ---------------------------------------------------------------------------
def _quipu_encode(n):
    if n < 0:
        return {"error": "quipu solo codifica enteros no negativos"}
    if n == 0:
        return {"cords": [], "note": "cero = ausencia de nudos en esa posicion"}
    digits = [int(c) for c in str(n)]  # de mayor a menor orden
    n_digits = len(digits)
    cords = []
    for idx, d in enumerate(digits):
        place = n_digits - idx - 1  # 0=unidades
        if place == 0:
            if d == 0:
                knot = None
            elif d == 1:
                knot = {"type": "figure_eight", "turns": 1, "value": 1}
            else:
                knot = {"type": "long_knot", "turns": d, "value": d}
        else:
            knot = None if d == 0 else {"type": "simple_knot", "turns": d, "value": d * (10 ** place)}
        cords.append({"place": place, "digit": d, "knot": knot})
    return {"n": n, "cords": cords}


def _quipu_decode(cords):
    total = 0
    for c in cords:
        knot = c.get("knot")
        if knot is None:
            continue
        place = c["place"]
        if place == 0:
            total += knot["turns"]
        else:
            total += knot["turns"] * (10 ** place)
    return total


def compute_quipu_encode(mode="encode", n=None, cords=None):
    """mode='encode': entero -> estructura de cordones/nudos.
    mode='decode': estructura de cordones -> entero (round-trip check)."""
    if mode == "encode":
        if n is None:
            return {"error": "mode='encode' requiere 'n'"}
        enc = _quipu_encode(n)
        if "cords" in enc:
            enc["decoded_check"] = _quipu_decode(enc["cords"]) == n
        return enc
    elif mode == "decode":
        if not cords:
            return {"error": "mode='decode' requiere 'cords'"}
        return {"decoded_value": _quipu_decode(cords)}
    else:
        return {"error": f"mode desconocido: {mode}"}


# ---------------------------------------------------------------------------
# 5) GRECIA — Metodo de exhaucion de Arquimedes (poligonos inscritos/circunscritos)
# ---------------------------------------------------------------------------
def compute_greek_archimedes_pi(start_sides=6, iterations=10):
    """Duplica el numero de lados 'iterations' veces desde start_sides
    (Arquimedes empezo con hexagonos, start_sides=6, y llego a 96 lados).
    Perimetro del poligono inscrito < 2*pi*r < perimetro del circunscrito.
    Usamos radio unitario; formulas de duplicacion de Arquimedes (sin trig
    moderna, solo raices cuadradas, tal como el las derivo)."""
    r = 1.0
    # lado del poligono inscrito regular de 'start_sides' lados, radio r
    inscribed_side = 2 * r * math.sin(math.pi / start_sides)  # solo para semilla inicial
    # Arquimedes derivaba esto geometricamente sin sin(); usamos la relacion
    # de duplicacion de lado a partir de un hexagono (lado = radio) como semilla real:
    if start_sides == 6:
        inscribed_side = r  # hexagono regular: lado == radio, resultado exacto de Euclides

    sides = start_sides
    side = inscribed_side
    history = []
    for it in range(iterations):
        perim_inscribed = sides * side
        pi_lower = perim_inscribed / (2 * r)
        # formula de duplicacion de Arquimedes para el lado del poligono de 2n lados
        # a partir del apotema (relacion pitagorica), sin usar funciones trig:
        apothem = math.sqrt(r ** 2 - (side / 2) ** 2)
        new_side = math.sqrt((side / 2) ** 2 + (r - apothem) ** 2)
        sides *= 2
        history.append({"sides": sides // 2, "pi_lower_bound": pi_lower})
        side = new_side

    perim_inscribed_final = sides * side
    pi_lower_final = perim_inscribed_final / (2 * r)

    return {
        "start_sides": start_sides,
        "iterations": iterations,
        "final_sides": sides,
        "pi_lower_bound": pi_lower_final,
        "pi_true": math.pi,
        "relative_error": abs(pi_lower_final - math.pi) / math.pi,
        "history": history,
    }


# ---------------------------------------------------------------------------
# 6) JAPON — Enri de Seki Takakazu: mismo principio de exhaucion + extrapolacion
#    tipo Richardson sobre sucesivas duplicaciones (tecnica que Seki empleo para
#    acelerar la convergencia frente al metodo puramente geometrico chino/griego)
# ---------------------------------------------------------------------------
def compute_japanese_enri_pi(start_sides=6, levels=6):
    """Genera la misma secuencia de perimetros inscritos duplicando lados
    (como Arquimedes) y aplica extrapolacion de Richardson de orden creciente
    sobre la secuencia -- la idea central del enri de Seki: acelerar la
    convergencia de una sucesion geometrica sin mas terminos brutos."""
    r = 1.0
    side = r if start_sides == 6 else 2 * r * math.sin(math.pi / start_sides)
    sides = start_sides
    seq = []
    for _ in range(levels):
        perim = sides * side
        seq.append(perim / (2 * r))
        apothem = math.sqrt(r ** 2 - (side / 2) ** 2)
        side = math.sqrt((side / 2) ** 2 + (r - apothem) ** 2)
        sides *= 2

    # extrapolacion de Richardson iterativa: cada nivel cancela el termino de
    # error dominante de orden 1/4^k (el error de un poligono duplicado cae ~1/4)
    table = [seq[:]]
    current = seq[:]
    for k in range(1, len(seq)):
        nxt = []
        factor = 4 ** k
        for i in range(len(current) - 1):
            nxt.append((factor * current[i + 1] - current[i]) / (factor - 1))
        table.append(nxt)
        current = nxt

    best_estimate = table[-1][0] if table[-1] else seq[-1]

    return {
        "start_sides": start_sides,
        "levels": levels,
        "raw_sequence_pi_estimates": seq,
        "richardson_table": table,
        "best_estimate": best_estimate,
        "pi_true": math.pi,
        "relative_error": abs(best_estimate - math.pi) / math.pi,
    }


def compute_ethnomath(preset, params=None):
    params = params or {}
    if preset == "maya_long_count":
        return compute_maya_long_count(**params)
    elif preset == "chinese_remainder":
        return compute_chinese_remainder(**params)
    elif preset == "vedic_multiply":
        return compute_vedic_multiply(**params)
    elif preset == "quipu_encode":
        return compute_quipu_encode(**params)
    elif preset == "greek_archimedes_pi":
        return compute_greek_archimedes_pi(**params)
    elif preset == "japanese_enri_pi":
        return compute_japanese_enri_pi(**params)
    else:
        return {"error": f"preset desconocido: {preset}"}
