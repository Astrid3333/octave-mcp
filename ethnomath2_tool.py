#!/usr/bin/env python3
"""
ethnomath2_tool.py — Segunda tanda de sistemas matematicos historicos:
Egipto, Persia (2 metodos), Rusia, Imperio Otomano/Turquia, mundo nordico
(vikingo), y calendario lunisolar del sudeste asiatico (Tailandia/Chula
Sakarat). Mismo criterio que ethnomath_tool.py: sin numpy, funciones puras,
validadas contra casos historicos conocidos.

Presets:
  egyptian_duplation      — multiplicacion/division por duplicacion (Ahmes,
                             Papiro Rhind) + descomposicion en fracciones
                             egipcias (algoritmo voraz de Fibonacci-Sylvester,
                             NO es identico a las tablas 2/n del papiro, que
                             usaban preferencias del escriba sin formula
                             general conocida -- esto se indica honestamente).
  persian_khwarizmi        — restauracion geometrica de Al-Khwarizmi para
                             ecuaciones cuadraticas (los 3 casos historicos
                             con coeficientes positivos, sin numeros negativos).
  persian_alkashi_sin1     — iteracion de punto fijo de Al-Kashi (1424) para
                             sin(1 grado) via la cubica de triplicacion de angulo.
  russian_peasant           — multiplicacion campesina rusa (mitad/duplicar),
                             linaje compartido con la duplicacion egipcia pero
                             algoritmo folclorico distinto.
  ottoman_taqi_al_din       — conversor sexagesimal<->decimal (innovacion
                             documentada de Taqi al-Din, observatorio de
                             Estambul, 1577) + tabla trigonometrica decimal.
  norse_rune_calendar       — numero aureo (ciclo metonico de 19 anos) del
                             calendario runico nordico (primstav).
  southeast_asian_metonic   — deteccion de anio con mes intercalar en
                             calendarios lunisolares tipo Chula Sakarat,
                             aproximacion via ciclo metonico de 19 anos
                             (NO reproduce las excepciones irregulares del
                             algoritmo completo de Eade -- se indica).
"""
import math

ETHNOMATH2_SCHEMA = {
    "name": "compute_ethnomath2",
    "description": (
        "Segunda tanda de algoritmos matematicos historicos: egyptian_duplation "
        "(multiplicacion Ahmes + fracciones egipcias), persian_khwarizmi "
        "(restauracion geometrica de cuadraticas, 3 casos), persian_alkashi_sin1 "
        "(iteracion de Al-Kashi para sin 1 grado), russian_peasant (multiplicacion "
        "campesina), ottoman_taqi_al_din (conversor sexagesimal-decimal + tabla "
        "trig), norse_rune_calendar (numero aureo del primstav), "
        "southeast_asian_metonic (mes intercalar aproximado, calendarios tipo "
        "Chula Sakarat)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "preset": {
                "type": "string",
                "enum": ["egyptian_duplation", "persian_khwarizmi", "persian_alkashi_sin1",
                         "russian_peasant", "ottoman_taqi_al_din", "norse_rune_calendar",
                         "southeast_asian_metonic"],
            },
            "params": {"type": "object"},
        },
        "required": ["preset"],
    },
}


# ---------------------------------------------------------------------------
# 1) EGIPTO — duplicacion (Ahmes, Papiro Rhind) + fracciones unitarias
# ---------------------------------------------------------------------------
def _egyptian_duplation_multiply(a, b):
    """a * b via duplicacion: se duplica 'b' mientras se resta la potencia
    de 2 correspondiente de 'a', tal como en el ejemplo 41*59 del papiro Rhind."""
    table = []
    power, doubled = 1, b
    remaining = a
    while power <= a:
        table.append({"power_of_2": power, "doubled_value": doubled})
        power *= 2
        doubled *= 2
    # descomponer 'a' en suma de potencias de 2 (de mayor a menor)
    used = []
    total = 0
    rem = a
    for row in reversed(table):
        if row["power_of_2"] <= rem:
            rem -= row["power_of_2"]
            used.append(row)
            total += row["doubled_value"]
    return total, table, list(reversed(used))


def _egyptian_greedy_fraction(numerator, denominator, max_terms=20):
    """Algoritmo voraz de Fibonacci-Sylvester: en cada paso resta la fraccion
    unitaria mas grande posible. Genera una descomposicion valida en fracciones
    egipcias, aunque no necesariamente la misma que eligieron los escribas en
    las tablas 2/n del papiro Rhind (esas seguian preferencias praticas propias,
    sin formula general documentada)."""
    terms = []
    n, d = numerator, denominator
    steps = 0
    while n != 0 and steps < max_terms:
        unit_denom = math.ceil(d / n)
        terms.append(unit_denom)
        n, d = n * unit_denom - d, d * unit_denom
        g = math.gcd(n, d) if n != 0 else d
        if n != 0:
            n //= g
            d //= g
        steps += 1
    return terms


def compute_egyptian_duplation(mode="multiply", a=None, b=None, numerator=None, denominator=None):
    if mode == "multiply":
        if a is None or b is None:
            return {"error": "mode='multiply' requiere 'a' y 'b'"}
        result, table, used = _egyptian_duplation_multiply(a, b)
        return {
            "mode": mode, "a": a, "b": b,
            "doubling_table": table,
            "rows_used": used,
            "result": result,
            "check": result == a * b,
        }
    elif mode == "unit_fractions":
        if numerator is None or denominator is None:
            return {"error": "mode='unit_fractions' requiere 'numerator' y 'denominator'"}
        terms = _egyptian_greedy_fraction(numerator, denominator)
        reconstructed = sum(1.0 / t for t in terms)
        return {
            "mode": mode, "numerator": numerator, "denominator": denominator,
            "unit_fraction_denominators": terms,
            "check_decimal": abs(reconstructed - numerator / denominator) < 1e-9,
            "note": "Algoritmo voraz de Fibonacci-Sylvester, no las tablas 2/n originales del papiro Rhind",
        }
    else:
        return {"error": f"mode desconocido: {mode}"}


# ---------------------------------------------------------------------------
# 2) PERSIA (a) — restauracion geometrica de Al-Khwarizmi (3 casos historicos,
#    todos con coeficientes positivos: sin numeros negativos)
# ---------------------------------------------------------------------------
def compute_persian_khwarizmi(case, b, c):
    """
    case=1: x^2 + b*x = c  ('raices y cuadrados igual a numeros')
            x = -b/2 + sqrt((b/2)^2 + c)
    case=2: x^2 + c = b*x  ('cuadrados y numeros igual a raices')
            x = b/2 +- sqrt((b/2)^2 - c)   (requiere (b/2)^2 >= c)
    case=3: x^2 = b*x + c  ('cuadrados igual a raices y numeros')
            x = b/2 + sqrt((b/2)^2 + c)
    Devuelve tambien los pasos geometricos (area del cuadrado agregado,
    lado del cuadrado completado) tal como los describe en Al-Jabr.
    """
    half_b = b / 2.0
    area_added = half_b ** 2

    if case == 1:
        completed_square_area = area_added + c
        side = math.sqrt(completed_square_area)
        x = side - half_b
        return {
            "case": 1, "equation": f"x^2 + {b}x = {c}",
            "half_of_b": half_b, "area_of_small_square_added": area_added,
            "completed_square_area": completed_square_area,
            "completed_square_side": side,
            "x": x, "check": abs(x ** 2 + b * x - c) < 1e-6,
        }
    elif case == 2:
        discriminant = area_added - c
        if discriminant < 0:
            return {"error": "sin solucion real: (b/2)^2 < c en el caso 2"}
        side = math.sqrt(discriminant)
        x1 = half_b + side
        x2 = half_b - side
        return {
            "case": 2, "equation": f"x^2 + {c} = {b}x",
            "half_of_b": half_b, "discriminant": discriminant,
            "completed_square_side": side,
            "x1": x1, "x2": x2,
            "check_x1": abs(x1 ** 2 + c - b * x1) < 1e-6,
            "check_x2": abs(x2 ** 2 + c - b * x2) < 1e-6 if x2 > 0 else "x2 no positivo, descartado historicamente",
        }
    elif case == 3:
        completed_square_area = area_added + c
        side = math.sqrt(completed_square_area)
        x = half_b + side
        return {
            "case": 3, "equation": f"x^2 = {b}x + {c}",
            "half_of_b": half_b, "area_of_small_square_added": area_added,
            "completed_square_area": completed_square_area,
            "completed_square_side": side,
            "x": x, "check": abs(x ** 2 - b * x - c) < 1e-6,
        }
    else:
        return {"error": "case debe ser 1, 2 o 3"}


# ---------------------------------------------------------------------------
# 2) PERSIA (b) — iteracion de Al-Kashi para sin(1 grado) (1424)
#    3*sin(1) - 4*sin(1)^3 = sin(3), resuelto por punto fijo:
#    x_{n+1} = (sin(3) + 4*x_n^3) / 3
# ---------------------------------------------------------------------------
def compute_persian_alkashi_sin1(iterations=10, x0=0.0):
    """sin(3 grados) se calcula aqui con math.sin solo para fijar la constante
    de entrada (Al-Kashi la obtenia geometricamente a partir de cuerdas
    conocidas, sin funciones trigonometricas modernas). La iteracion en si
    -- el metodo numerico -- es el suyo: point fijo sobre la cubica de
    triplicacion de angulo, que converge porque la derivada cerca de la raiz
    es pequena."""
    sin3 = math.sin(math.radians(3))
    x = x0
    history = [x]
    for _ in range(iterations):
        x = (sin3 + 4 * x ** 3) / 3
        history.append(x)
    true_sin1 = math.sin(math.radians(1))
    return {
        "sin3_input": sin3,
        "iterations": iterations,
        "history": history,
        "estimate_sin1": x,
        "true_sin1": true_sin1,
        "relative_error": abs(x - true_sin1) / true_sin1,
    }


# ---------------------------------------------------------------------------
# 3) RUSIA — multiplicacion campesina (mitad/duplicar)
# ---------------------------------------------------------------------------
def compute_russian_peasant(a, b):
    """Se reduce 'a' a la mitad (descartando resto) mientras se duplica 'b';
    se suman las filas donde 'a' es impar. Comparte el mismo principio binario
    que la duplicacion egipcia (Ahmes), pero organizado al reves: en vez de
    descomponer el multiplicador en potencias de 2 explicitas, se usa la
    paridad en cada fila como criterio de inclusion."""
    table = []
    x, y = a, b
    total = 0
    while x >= 1:
        include = (x % 2 == 1)
        table.append({"a": x, "b": y, "included": include})
        if include:
            total += y
        x //= 2
        y *= 2
    return {
        "a": a, "b": b,
        "table": table,
        "result": total,
        "check": total == a * b,
    }


# ---------------------------------------------------------------------------
# 4) IMPERIO OTOMANO — Taqi al-Din: notacion decimal en vez de sexagesimal
# ---------------------------------------------------------------------------
def _sexagesimal_to_decimal(degrees, minutes, seconds):
    return degrees + minutes / 60.0 + seconds / 3600.0


def _decimal_to_sexagesimal(value):
    degrees = int(value)
    frac = abs(value - degrees) * 60
    minutes = int(frac)
    seconds = (frac - minutes) * 60
    return degrees, minutes, seconds


def compute_ottoman_taqi_al_din(mode="sexagesimal_to_decimal", degrees=None,
                                 minutes=None, seconds=None, decimal_value=None,
                                 sine_table_step_degrees=1, sine_table_max_degrees=10):
    """mode='sexagesimal_to_decimal' o 'decimal_to_sexagesimal': convierte
    entre notacion tradicional (grados,minutos,segundos en base 60) y la
    notacion decimal con punto que Taqi al-Din introdujo en su observatorio
    de Estambul (1577) para tablas trigonometricas, en lugar de la fraccion
    sexagesimal heredada de Ptolomeo. Tambien genera una pequena tabla
    seno/coseno en notacion decimal como las que el compilaba."""
    if mode == "sexagesimal_to_decimal":
        if degrees is None:
            return {"error": "requiere 'degrees','minutes','seconds'"}
        dec = _sexagesimal_to_decimal(degrees, minutes or 0, seconds or 0)
        return {"mode": mode, "input": [degrees, minutes, seconds], "decimal_value": dec}
    elif mode == "decimal_to_sexagesimal":
        if decimal_value is None:
            return {"error": "requiere 'decimal_value'"}
        d, m, s = _decimal_to_sexagesimal(decimal_value)
        return {"mode": mode, "input": decimal_value, "sexagesimal": [d, m, s]}
    elif mode == "sine_table":
        table = []
        deg = 0
        while deg <= sine_table_max_degrees:
            table.append({
                "degrees_decimal": deg,
                "sin": round(math.sin(math.radians(deg)), 10),
                "cos": round(math.cos(math.radians(deg)), 10),
            })
            deg += sine_table_step_degrees
        return {"mode": mode, "table": table}
    else:
        return {"error": f"mode desconocido: {mode}"}


# ---------------------------------------------------------------------------
# 5) NORDICO — numero aureo del calendario runico (primstav), ciclo metonico
# ---------------------------------------------------------------------------
_RUNE_NAMES_19 = ["Fe", "Ur", "Thurs", "Os", "Reid", "Kaun", "Hagall", "Naud",
                  "Is", "Ar", "Sol", "Tyr", "Bjarkan", "Madr", "Logr", "Yr",
                  "Ar-2", "Sol-2", "Naud-2"]  # ciclo de 19 runas del bastón rúnico


def compute_norse_rune_calendar(year):
    """El numero aureo (golden number) = (year mod 19) + 1, es la posicion en
    el ciclo metonico de 19 anos usado tanto por el computus eclesiastico
    como por el bastón rúnico (primstav) escandinavo para marcar las fases
    lunares en el calendario tallado en madera."""
    golden_number = (year % 19) + 1
    rune = _RUNE_NAMES_19[golden_number - 1]
    return {
        "year": year,
        "golden_number": golden_number,
        "rune_of_the_year": rune,
        "cycle_length_years": 19,
        "note": "Mismo ciclo metonico que el computus eclesiastico; el primstav "
                "lo usaba para posicionar las fases lunares en el calendario tallado",
    }


# ---------------------------------------------------------------------------
# 6) SUDESTE ASIATICO — aproximacion de mes intercalar (tipo Chula Sakarat)
# ---------------------------------------------------------------------------
_METONIC_LEAP_YEAR_POSITIONS = {3, 6, 8, 11, 14, 17, 19}  # posicion en el ciclo de 19


def compute_southeast_asian_metonic(cs_year):
    """Aproximacion via ciclo metonico estandar (7 anios con mes intercalar
    en cada ciclo de 19, en las posiciones clasicas 3,6,8,11,14,17,19).
    ADVERTENCIA: el calendario Chula Sakarat real (Tailandia/Birmania) usa
    el algoritmo irregular de J.C. Eade con excepciones historicas ("escape
    clause") que esta aproximacion NO reproduce -- es solo el patron
    metonico subyacente, no el calendario oficial exacto."""
    position = ((cs_year - 1) % 19) + 1
    has_intercalary_month = position in _METONIC_LEAP_YEAR_POSITIONS
    return {
        "cs_year": cs_year,
        "position_in_19y_cycle": position,
        "approx_has_intercalary_month": has_intercalary_month,
        "warning": "Aproximacion metonica generica -- el calendario Chula Sakarat "
                   "real usa el algoritmo irregular de Eade con excepciones no "
                   "modeladas aqui",
    }


def compute_ethnomath2(preset, params=None):
    params = params or {}
    if preset == "egyptian_duplation":
        return compute_egyptian_duplation(**params)
    elif preset == "persian_khwarizmi":
        return compute_persian_khwarizmi(**params)
    elif preset == "persian_alkashi_sin1":
        return compute_persian_alkashi_sin1(**params)
    elif preset == "russian_peasant":
        return compute_russian_peasant(**params)
    elif preset == "ottoman_taqi_al_din":
        return compute_ottoman_taqi_al_din(**params)
    elif preset == "norse_rune_calendar":
        return compute_norse_rune_calendar(**params)
    elif preset == "southeast_asian_metonic":
        return compute_southeast_asian_metonic(**params)
    else:
        return {"error": f"preset desconocido: {preset}"}
