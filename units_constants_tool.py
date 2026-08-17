"""
units_constants_tool.py

Conversion de unidades y constantes fisicas fundamentales (CODATA). Sin
libreria nueva (no pint, no astropy.units) -- factores multiplicativos
a la unidad SI base de cada categoria, mas manejo especial para
temperatura (afin, no multiplicativo: K<->C<->F no pasan por el origen).

Todos los factores de longitud/masa/fuerza/energia derivados de
definiciones EXACTAS post-1959 (pie internacional, libra internacional)
o post-2019 (segunda redefinicion del SI: c, h, e, kB, NA son exactos
por definicion desde entonces). Las constantes marcadas type="measured"
tienen incertidumbre real (CODATA 2018) y se dan con las cifras
significativas publicadas, no mas.
"""
import math

# ---------------------------------------------------------------------
# Unidades: factor multiplicativo a la unidad SI base de la categoria.
# Todos los valores no-temperatura son EXACTOS (definiciones legales de
# las unidades), salvo donde se indica lo contrario.
# ---------------------------------------------------------------------
UNIT_CATEGORIES = {
    "length": {"si": "m", "factors": {
        "m": 1.0, "km": 1000.0, "cm": 0.01, "mm": 0.001, "um": 1e-6, "nm": 1e-9,
        "angstrom": 1e-10, "in": 0.0254, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344,
        "au": 1.495978707e11, "ly": 9.4607304725808e15, "pc": 3.0856775814913673e16,
    }},
    "mass": {"si": "kg", "factors": {
        "kg": 1.0, "g": 0.001, "mg": 1e-6, "tonne": 1000.0, "ton_us": 907.18474,
        "lb": 0.45359237, "oz": 0.028349523125,
        "amu": 1.66053906660e-27,  # CODATA 2018, medida (no exacta)
    }},
    "time": {"si": "s", "factors": {
        "s": 1.0, "min": 60.0, "hr": 3600.0, "day": 86400.0,
        "year": 31557600.0,  # ano juliano = 365.25 dias, convencion astronomica estandar
    }},
    "energy": {"si": "J", "factors": {
        "J": 1.0, "kJ": 1000.0, "erg": 1e-7,
        "cal": 4.184, "kcal": 4184.0,
        "eV": 1.602176634e-19, "keV": 1.602176634e-16, "MeV": 1.602176634e-13,
        "kWh": 3.6e6, "BTU": 1055.05585262,
    }},
    "pressure": {"si": "Pa", "factors": {
        "Pa": 1.0, "kPa": 1000.0, "bar": 1e5, "mbar": 100.0, "atm": 101325.0,
        "psi": 6894.757293168361, "torr": 101325.0 / 760.0,
        "mmHg": 101325.0 / 760.0,  # tratado = torr aca (difieren en la 7ma cifra, no relevante en la practica)
    }},
    "force": {"si": "N", "factors": {
        "N": 1.0, "dyn": 1e-5, "lbf": 4.4482216152605, "kgf": 9.80665,
    }},
    "power": {"si": "W", "factors": {
        "W": 1.0, "kW": 1000.0, "MW": 1e6, "hp": 745.6998715822702,
    }},
    "volume": {"si": "m3", "factors": {
        "m3": 1.0, "L": 0.001, "mL": 1e-6, "gal_us": 0.003785411784,
        "ft3": 0.028316846592, "in3": 1.6387064e-5,
    }},
    "angle": {"si": "rad", "factors": {
        "rad": 1.0, "deg": math.pi / 180, "arcmin": math.pi / 180 / 60,
        "arcsec": math.pi / 180 / 3600, "rev": 2 * math.pi,
    }},
}

# unidad -> categoria, para no pedirle a quien llama que especifique la categoria
_UNIT_TO_CATEGORY = {}
for _cat, _spec in UNIT_CATEGORIES.items():
    for _u in _spec["factors"]:
        _UNIT_TO_CATEGORY[_u] = _cat


def _temperature_to_K(value, unit):
    if unit == "K":
        return value
    elif unit == "C":
        return value + 273.15
    elif unit == "F":
        return (value - 32) * 5 / 9 + 273.15
    raise ValueError(f"unidad de temperatura desconocida: {unit!r}. Usar K, C o F.")


def _temperature_from_K(value_K, unit):
    if unit == "K":
        return value_K
    elif unit == "C":
        return value_K - 273.15
    elif unit == "F":
        return (value_K - 273.15) * 9 / 5 + 32
    raise ValueError(f"unidad de temperatura desconocida: {unit!r}. Usar K, C o F.")


def _convert(params):
    value = params.get("value")
    from_unit = params.get("from_unit")
    to_unit = params.get("to_unit")
    if value is None or from_unit is None or to_unit is None:
        raise ValueError("faltan value, from_unit o to_unit")

    if from_unit in ("K", "C", "F") or to_unit in ("K", "C", "F"):
        if from_unit not in ("K", "C", "F") or to_unit not in ("K", "C", "F"):
            raise ValueError("temperatura no se mezcla con otras categorias (K/C/F entre si nomas)")
        result = _temperature_from_K(_temperature_to_K(value, from_unit), to_unit)
        return {"value": value, "from_unit": from_unit, "to_unit": to_unit,
                "result": result, "category": "temperature",
                "note": "conversion afin (no multiplicativa), no pasa por 0"}

    cat_from = _UNIT_TO_CATEGORY.get(from_unit)
    cat_to = _UNIT_TO_CATEGORY.get(to_unit)
    if cat_from is None:
        raise ValueError(f"unidad desconocida: {from_unit!r}")
    if cat_to is None:
        raise ValueError(f"unidad desconocida: {to_unit!r}")
    if cat_from != cat_to:
        raise ValueError(f"{from_unit} es {cat_from} y {to_unit} es {cat_to} -- no son compatibles")

    factors = UNIT_CATEGORIES[cat_from]["factors"]
    si_value = value * factors[from_unit]
    result = si_value / factors[to_unit]
    return {"value": value, "from_unit": from_unit, "to_unit": to_unit,
            "result": result, "category": cat_from,
            "si_intermediate": {"value": si_value, "unit": UNIT_CATEGORIES[cat_from]["si"]}}


# ---------------------------------------------------------------------
# Constantes fisicas fundamentales (CODATA 2018 / SI 2019).
# type="exact": valor fijado por definicion legal del SI, sin incertidumbre.
# type="measured": tiene incertidumbre experimental real (CODATA 2018);
#   se da con las cifras significativas publicadas, no mas.
# ---------------------------------------------------------------------
CONSTANTS = {
    "c": {"value": 299792458.0, "unit": "m/s", "type": "exact",
          "description": "velocidad de la luz en el vacio"},
    "h": {"value": 6.62607015e-34, "unit": "J s", "type": "exact",
          "description": "constante de Planck"},
    "hbar": {"value": 1.054571817e-34, "unit": "J s", "type": "exact",
             "description": "constante de Planck reducida (h/2pi)"},
    "e": {"value": 1.602176634e-19, "unit": "C", "type": "exact",
          "description": "carga elemental"},
    "kB": {"value": 1.380649e-23, "unit": "J/K", "type": "exact",
           "description": "constante de Boltzmann"},
    "NA": {"value": 6.02214076e23, "unit": "1/mol", "type": "exact",
           "description": "numero de Avogadro"},
    "R": {"value": 8.31446261815324, "unit": "J/(mol K)", "type": "exact",
          "description": "constante de los gases ideales (= NA*kB)"},
    "F": {"value": 96485.33212331001, "unit": "C/mol", "type": "exact",
          "description": "constante de Faraday (= NA*e)"},
    "sigma_SB": {"value": 5.670374419e-8, "unit": "W/(m^2 K^4)", "type": "exact",
                 "description": "constante de Stefan-Boltzmann"},
    "g_n": {"value": 9.80665, "unit": "m/s^2", "type": "exact",
            "description": "gravedad estandar (definicion convencional, no medida local)"},
    "atm": {"value": 101325.0, "unit": "Pa", "type": "exact",
            "description": "atmosfera estandar (definicion)"},
    "G": {"value": 6.67430e-11, "unit": "m^3/(kg s^2)", "type": "measured",
          "uncertainty_rel": 2.2e-5,
          "description": "constante de gravitacion universal (CODATA 2018)"},
    "me": {"value": 9.1093837015e-31, "unit": "kg", "type": "measured",
           "description": "masa del electron (CODATA 2018)"},
    "mp": {"value": 1.67262192369e-27, "unit": "kg", "type": "measured",
           "description": "masa del proton (CODATA 2018)"},
    "mn": {"value": 1.67492749804e-27, "unit": "kg", "type": "measured",
           "description": "masa del neutron (CODATA 2018)"},
    "alpha": {"value": 7.2973525693e-3, "unit": "adimensional", "type": "measured",
              "description": "constante de estructura fina (CODATA 2018)"},
    "eps0": {"value": 8.8541878128e-12, "unit": "F/m", "type": "measured",
             "description": "permitividad del vacio (derivada de alpha, ya no exacta desde 2019)"},
    "mu0": {"value": 1.25663706212e-6, "unit": "N/A^2", "type": "measured",
            "description": "permeabilidad del vacio (derivada de alpha, ya no exacta desde 2019)"},
}


def _constants_get(params):
    name = params.get("name")
    if name is None:
        return {"constants": {k: v for k, v in CONSTANTS.items()}}
    if name not in CONSTANTS:
        raise ValueError(f"constante desconocida: {name!r}. Disponibles: {sorted(CONSTANTS)}")
    return {"name": name, **CONSTANTS[name]}


def _validate():
    checks = []

    def add(case, got, expected, tol=1e-6, rel=True):
        err = abs(got - expected) / abs(expected) if rel and expected != 0 else abs(got - expected)
        checks.append({"case": case, "got": got, "expected": expected, "ok": err < tol})

    # conversiones de unidades contra valores de referencia conocidos
    add("1 mi -> km", _convert({"value": 1, "from_unit": "mi", "to_unit": "km"})["result"], 1.609344, 1e-9)
    add("1 in -> cm", _convert({"value": 1, "from_unit": "in", "to_unit": "cm"})["result"], 2.54, 1e-9)
    add("1 lb -> kg", _convert({"value": 1, "from_unit": "lb", "to_unit": "kg"})["result"], 0.45359237, 1e-9)
    add("1 atm -> Pa", _convert({"value": 1, "from_unit": "atm", "to_unit": "Pa"})["result"], 101325.0, 1e-12)
    add("1 cal -> J", _convert({"value": 1, "from_unit": "cal", "to_unit": "J"})["result"], 4.184, 1e-9)
    add("1 eV -> J", _convert({"value": 1, "from_unit": "eV", "to_unit": "J"})["result"], 1.602176634e-19, 1e-9)
    add("1 hp -> W", _convert({"value": 1, "from_unit": "hp", "to_unit": "W"})["result"], 745.6998715822702, 1e-9)
    add("1 gal_us -> L", _convert({"value": 1, "from_unit": "gal_us", "to_unit": "L"})["result"], 3.785411784, 1e-9)
    add("1 rev -> deg", _convert({"value": 1, "from_unit": "rev", "to_unit": "deg"})["result"], 360.0, 1e-9)
    add("1 year -> day", _convert({"value": 1, "from_unit": "year", "to_unit": "day"})["result"], 365.25, 1e-9)

    # roundtrip generico: convertir ida y vuelta debe devolver el valor original
    for cat, spec in UNIT_CATEGORIES.items():
        units = list(spec["factors"])
        if len(units) >= 2:
            a, b = units[0], units[-1]
            r1 = _convert({"value": 3.7, "from_unit": a, "to_unit": b})["result"]
            r2 = _convert({"value": r1, "from_unit": b, "to_unit": a})["result"]
            add(f"roundtrip {cat} ({a}->{b}->{a})", r2, 3.7, 1e-9)

    # temperatura: puntos fijos conocidos
    add("0 C -> K", _convert({"value": 0, "from_unit": "C", "to_unit": "K"})["result"], 273.15, 1e-9)
    add("100 C -> F", _convert({"value": 100, "from_unit": "C", "to_unit": "F"})["result"], 212.0, 1e-9)
    add("-40 C -> F (punto de cruce C=F)", _convert({"value": -40, "from_unit": "C", "to_unit": "F"})["result"], -40.0, 1e-9)
    add("32 F -> C", _convert({"value": 32, "from_unit": "F", "to_unit": "C"})["result"], 0.0, 1e-9)
    add("temperatura roundtrip K->F->K", _temperature_from_K(_temperature_to_K(_temperature_from_K(300, "F"), "F"), "K"), 300.0, 1e-9)

    # constantes derivadas: coherencia interna (R=NA*kB, F=NA*e, sigma=2pi^5 kB^4/(15 h^3 c^2))
    NA, kB, e, h, c = (CONSTANTS[k]["value"] for k in ("NA", "kB", "e", "h", "c"))
    add("R == NA*kB", CONSTANTS["R"]["value"], NA * kB, 1e-12)
    add("F == NA*e", CONSTANTS["F"]["value"], NA * e, 1e-9)
    sigma_derived = (2 * math.pi ** 5 * kB ** 4) / (15 * h ** 3 * c ** 2)
    add("sigma_SB == 2pi^5 kB^4/(15 h^3 c^2)", CONSTANTS["sigma_SB"]["value"], sigma_derived, 1e-6)
    add("hbar == h/(2pi)", CONSTANTS["hbar"]["value"], h / (2 * math.pi), 1e-9)

    return {"validate": True, "all_passed": all(c["ok"] for c in checks), "checks": checks}


def compute_units_constants(mode, params=None):
    params = params or {}
    if mode == "convert":
        return _convert(params)
    elif mode == "constants_get":
        return _constants_get(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            f"mode desconocido: {mode!r}. Valores validos: convert, constants_get, validate."
        )


UNITS_CONSTANTS_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["convert", "constants_get", "validate"],
            "default": "convert",
        },
        "value": {"type": "number", "description": "Solo convert: valor numerico a convertir."},
        "from_unit": {"type": "string", "description": "Solo convert."},
        "to_unit": {"type": "string", "description": "Solo convert."},
        "name": {
            "type": "string",
            "enum": sorted(CONSTANTS),
            "description": "Solo constants_get: nombre de la constante. Si se omite, "
                            "devuelve la tabla completa.",
        },
    },
    "required": ["mode"],
}


try:
    from tool_registry import register_tool
    register_tool(
        name="units_constants_tool",
        schema={
            "name": "units_constants_tool",
            "description": (
                "Conversion de unidades (longitud, masa, tiempo, energia, presion, "
                "fuerza, potencia, volumen, angulo, temperatura) y constantes fisicas "
                "fundamentales CODATA (c, h, hbar, e, kB, NA, R, F, sigma_SB, G, me, mp, "
                "mn, alpha, eps0, mu0, g_n, atm) -- sin libreria nueva (no pint, no "
                "astropy.units), factores exactos donde la definicion de la unidad es "
                "exacta. Cada constante declara type=exact|measured."
            ),
            "inputSchema": UNITS_CONSTANTS_SCHEMA,
        },
        handler=lambda args: compute_units_constants(args.get("mode"), args),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    print(json.dumps(compute_units_constants("validate"), indent=2, ensure_ascii=False))
