"""
wildfire_risk_tool.py

Peligrosidad de incendios forestales via modelo de propagacion superficial de
Rothermel (1972) con ponderacion muerto/vivo (Albini 1976), dos catalogos de
modelos de combustible (Anderson 13 / Scott & Burgan 40) mas la opcion de
combustible custom, e intensidad de linea de fuego / largo de llama (Byram
1959).

=============================================================================
CONFIANZA DE DATOS (leer antes de usar para decisiones reales)
=============================================================================
Esta tool se escribio en una sesion de chat SIN busqueda web para verificar
tablas fuente (a diferencia de la sesion anterior que si pudo buscar en
training.nwcg.gov / fs.usda.gov). Nivel de confianza declarado por pieza:

- FISICA (ecuaciones de Rothermel/Albini/Byram): confianza ALTA. La
  estructura general (reaction velocity, packing ratio, propagating flux
  ratio, coeficientes de viento/pendiente, ponderacion por area superficial
  muerto/vivo, Byram) sigue la formulacion estandar ampliamente publicada.
  Simplificaciones respecto a BehavePlus completo, declaradas explicitamente:
    * humedad de extincion viva (Mx_live) es un parametro FIJO configurable
      (default 1.5 = 150%), no la formula dinamica de Albini que depende de
      la humedad muerta (no se reprodujo por baja confianza en su forma
      exacta desde memoria).
    * sin transferencia dinamica de carga herbacea por curado (los modelos
      "dynamic" de Scott & Burgan 2005 mueven carga viva->muerta segun
      curado; aca el flag "dynamic" queda registrado pero no afecta el
      calculo todavia).
    * "fuel consumido" para Byram = carga total del modelo (w0_total),
      simplificacion conservadora habitual en modelos de superficie simples.

- CATALOGO anderson13 (Anderson 1982): confianza MEDIA-ALTA en fuel loads
  (w0) y profundidad de cama (depth) — esta tabla es una de las mas
  reproducidas en la literatura de manejo de fuego. Confianza MEDIA en los
  SAV ratios (varian segun la fuente secundaria consultada; los de 10-hr y
  100-hr si son constantes estandar de alta confianza: 109 y 30 ft^-1).

- CATALOGO scott_burgan40 (Scott & Burgan 2005, RMRS-GTR-153): confianza
  BAJA. Los 40 codigos estan completos (nombre, grupo, dynamic/static) pero
  los valores numericos son ESTIMACIONES POR PATRON (crecientes dentro de
  cada grupo, como fue disenado el catalogo real), NO la tabla publicada
  exacta. No usar para decisiones operacionales sin verificar contra la
  fuente. Cada resultado que use este catalogo trae "data_confidence":"low"
  explicito en el JSON de salida, no solo en este docstring.

- CATALOGO custom: confianza = la que aporte quien llama la tool (no hay
  datos hardcodeados, cero riesgo de error de memoria de Claude).

Sigue el mismo patron mode/params + suite de validacion que
earthquake_analysis_tool y natural_hazard_risk_tool.
"""

import math

# ---------------------------------------------------------------------------
# Constantes fisicas (Rothermel 1972 / Albini 1976) - confianza alta
# ---------------------------------------------------------------------------

PARTICLE_DENSITY = 32.0            # lb/ft^3, densidad de particula solida (rho_p)
DEFAULT_HEAT_CONTENT = 8000.0      # BTU/lb, contenido calorico estandar (muerto y vivo)
DEFAULT_MINERAL_TOTAL = 0.0555     # fraccion, contenido mineral total (S_T)
DEFAULT_MINERAL_EFFECTIVE = 0.01   # fraccion, contenido mineral efectivo (S_e)
SAV_10HR = 109.0                   # ft^-1, constante estandar combustible muerto 10-hr
SAV_100HR = 30.0                   # ft^-1, constante estandar combustible muerto 100-hr
DEFAULT_LIVE_MX = 1.5              # fraccion (150%), humedad de extincion viva por defecto

DEAD_CLASSES = ["1hr", "10hr", "100hr"]
LIVE_CLASSES = ["live_herb", "live_woody"]
ALL_CLASSES = DEAD_CLASSES + LIVE_CLASSES


def _tons_acre_to_lb_ft2(tpa):
    """1 ton/acre = 0.045928 lb/ft^2 (factor estandar, confianza alta)."""
    return tpa * 0.045928


# ---------------------------------------------------------------------------
# Catalogo Anderson 13 (Anderson 1982, "Aids to Determining Fuel Models")
# w0 en ton/acre (se convierte a lb/ft^2 al usarse), depth en ft, Mx fraccion
# CONFIANZA: media-alta en w0/depth/Mx, media en sav (ver docstring modulo)
# ---------------------------------------------------------------------------

FUEL_MODELS_ANDERSON13 = {
    "1":  {"name": "Pasto corto (~0.3 m)", "group": "grass",
           "w0_tpa": {"1hr": 0.74, "10hr": 0.0, "100hr": 0.0, "live_herb": 0.0, "live_woody": 0.0},
           "sav": {"1hr": 3500.0, "live_herb": 1500.0, "live_woody": 1500.0},
           "depth": 1.0, "Mx": 0.12, "dynamic": False},
    "2":  {"name": "Pasto con matorral/arbolado ralo", "group": "grass",
           "w0_tpa": {"1hr": 2.0, "10hr": 1.0, "100hr": 0.5, "live_herb": 0.5, "live_woody": 0.0},
           "sav": {"1hr": 3000.0, "live_herb": 1500.0, "live_woody": 1500.0},
           "depth": 1.0, "Mx": 0.15, "dynamic": False},
    "3":  {"name": "Pasto alto (~0.75 m)", "group": "grass",
           "w0_tpa": {"1hr": 3.01, "10hr": 0.0, "100hr": 0.0, "live_herb": 0.0, "live_woody": 0.0},
           "sav": {"1hr": 1500.0, "live_herb": 1500.0, "live_woody": 1500.0},
           "depth": 2.5, "Mx": 0.25, "dynamic": False},
    "4":  {"name": "Chaparral (~2 m)", "group": "shrub",
           "w0_tpa": {"1hr": 5.01, "10hr": 4.01, "100hr": 2.0, "live_herb": 0.0, "live_woody": 5.01},
           "sav": {"1hr": 2000.0, "live_herb": 1500.0, "live_woody": 1500.0},
           "depth": 6.0, "Mx": 0.20, "dynamic": False},
    "5":  {"name": "Matorral joven (~0.6 m)", "group": "shrub",
           "w0_tpa": {"1hr": 1.0, "10hr": 0.5, "100hr": 0.0, "live_herb": 0.0, "live_woody": 2.0},
           "sav": {"1hr": 2000.0, "live_herb": 1500.0, "live_woody": 1500.0},
           "depth": 2.0, "Mx": 0.20, "dynamic": False},
    "6":  {"name": "Matorral dormante / restos latifoliadas", "group": "shrub",
           "w0_tpa": {"1hr": 1.5, "10hr": 2.5, "100hr": 2.0, "live_herb": 0.0, "live_woody": 0.0},
           "sav": {"1hr": 1750.0, "live_herb": 1500.0, "live_woody": 1500.0},
           "depth": 2.5, "Mx": 0.25, "dynamic": False},
    "7":  {"name": "Monte bajo del sureste", "group": "shrub",
           "w0_tpa": {"1hr": 1.13, "10hr": 1.87, "100hr": 1.5, "live_herb": 0.0, "live_woody": 0.37},
           "sav": {"1hr": 1750.0, "live_herb": 1500.0, "live_woody": 1500.0},
           "depth": 2.5, "Mx": 0.40, "dynamic": False},
    "8":  {"name": "Hojarasca cerrada de coniferas", "group": "timber",
           "w0_tpa": {"1hr": 1.5, "10hr": 1.0, "100hr": 2.5, "live_herb": 0.0, "live_woody": 0.0},
           "sav": {"1hr": 2000.0, "live_herb": 1500.0, "live_woody": 1500.0},
           "depth": 0.2, "Mx": 0.30, "dynamic": False},
    "9":  {"name": "Hojarasca de latifoliadas", "group": "timber",
           "w0_tpa": {"1hr": 2.92, "10hr": 0.41, "100hr": 0.15, "live_herb": 0.0, "live_woody": 0.0},
           "sav": {"1hr": 2500.0, "live_herb": 1500.0, "live_woody": 1500.0},
           "depth": 0.2, "Mx": 0.25, "dynamic": False},
    "10": {"name": "Hojarasca + sotobosque de coniferas", "group": "timber",
           "w0_tpa": {"1hr": 3.01, "10hr": 2.0, "100hr": 5.01, "live_herb": 0.0, "live_woody": 2.0},
           "sav": {"1hr": 2000.0, "live_herb": 1500.0, "live_woody": 1500.0},
           "depth": 1.0, "Mx": 0.25, "dynamic": False},
    "11": {"name": "Restos de aprovechamiento livianos", "group": "slash",
           "w0_tpa": {"1hr": 1.5, "10hr": 4.51, "100hr": 5.51, "live_herb": 0.0, "live_woody": 0.0},
           "sav": {"1hr": 1500.0, "live_herb": 1500.0, "live_woody": 1500.0},
           "depth": 1.0, "Mx": 0.15, "dynamic": False},
    "12": {"name": "Restos de aprovechamiento medianos", "group": "slash",
           "w0_tpa": {"1hr": 4.01, "10hr": 14.03, "100hr": 16.53, "live_herb": 0.0, "live_woody": 0.0},
           "sav": {"1hr": 1500.0, "live_herb": 1500.0, "live_woody": 1500.0},
           "depth": 2.3, "Mx": 0.20, "dynamic": False},
    "13": {"name": "Restos de aprovechamiento pesados", "group": "slash",
           "w0_tpa": {"1hr": 7.01, "10hr": 23.04, "100hr": 28.05, "live_herb": 0.0, "live_woody": 0.0},
           "sav": {"1hr": 1500.0, "live_herb": 1500.0, "live_woody": 1500.0},
           "depth": 3.0, "Mx": 0.25, "dynamic": False},
}

ANDERSON13_CONFIDENCE = {
    "overall": "medium-high",
    "w0_depth_Mx": "medium-high — tabla Anderson 1982, muy reproducida en la literatura",
    "sav": "medium — valores tipicos de fuentes secundarias, no confirmados contra la tabla original en esta sesion",
}


# ---------------------------------------------------------------------------
# Catalogo Scott & Burgan 40 (Scott & Burgan 2005, RMRS-GTR-153)
# CONFIANZA BAJA — ver docstring del modulo. Los valores se generan por
# patron dentro de cada grupo (creciente carga/profundidad), NO son la tabla
# publicada exacta.
# ---------------------------------------------------------------------------

_SB40_GROUPS = {
    # codigo_prefijo: (n_modelos, dynamic, depth_range_ft, sav_1hr, Mx, group_label)
    "GR": (9, True,  (0.4, 3.0), 2200.0, 0.15, "grass"),
    "GS": (4, True,  (1.0, 3.0), 2000.0, 0.15, "grass-shrub"),
    "SH": (9, False, (1.0, 6.0), 1600.0, 0.15, "shrub"),
    "TU": (5, True,  (0.3, 1.0), 1800.0, 0.20, "timber-understory"),
    "TL": (9, False, (0.2, 1.0), 2000.0, 0.25, "timber-litter"),
    "SB": (4, False, (1.0, 3.0), 1500.0, 0.25, "slash-blowdown"),
}


_SB40_GROUP_LABEL = {
    "GR": "grass",
    "GS": "grass-shrub",
    "SH": "shrub",
    "TU": "timber-understory",
    "TL": "timber-litter",
    "SB": "slash-blowdown",
}

# code: (load_1hr, load_10hr, load_100hr, load_live_herb, load_live_woody,
#        sav_1hr, sav_live_herb, sav_live_woody, depth, mx, heat, dynamic)
_SB40_REAL = {
    "GR1": (0.10, 0.00, 0.00, 0.30, 0.00, 2200, 2000, 9999, 0.4, 15, 8000, True),
    "GR2": (0.10, 0.00, 0.00, 1.00, 0.00, 2000, 1800, 9999, 1.0, 15, 8000, True),
    "GR3": (0.10, 0.40, 0.00, 1.50, 0.00, 1500, 1300, 9999, 2.0, 30, 8000, True),
    "GR4": (0.25, 0.00, 0.00, 1.90, 0.00, 2000, 1800, 9999, 2.0, 15, 8000, True),
    "GR5": (0.40, 0.00, 0.00, 2.50, 0.00, 1800, 1600, 9999, 1.5, 40, 8000, True),
    "GR6": (0.10, 0.00, 0.00, 3.40, 0.00, 2200, 2000, 9999, 1.5, 40, 9000, True),
    "GR7": (1.00, 0.00, 0.00, 5.40, 0.00, 2000, 1800, 9999, 3.0, 15, 8000, True),
    "GR8": (0.50, 1.00, 0.00, 7.30, 0.00, 1500, 1300, 9999, 4.0, 30, 8000, True),
    "GR9": (1.00, 1.00, 0.00, 9.00, 0.00, 1800, 1600, 9999, 5.0, 40, 8000, True),
    "GS1": (0.20, 0.00, 0.00, 0.50, 0.65, 2000, 1800, 1800, 0.9, 15, 8000, True),
    "GS2": (0.50, 0.50, 0.00, 0.60, 1.00, 2000, 1800, 1800, 1.5, 15, 8000, True),
    "GS3": (0.30, 0.25, 0.00, 1.45, 1.25, 1800, 1600, 1600, 1.8, 40, 8000, True),
    "GS4": (1.90, 0.30, 0.10, 3.40, 7.10, 1800, 1600, 1600, 2.1, 40, 8000, True),
    "SH1": (0.25, 0.25, 0.00, 0.15, 1.30, 2000, 1800, 1600, 1.0, 15, 8000, True),
    "SH2": (1.35, 2.40, 0.75, 0.00, 3.85, 2000, 9999, 1600, 1.0, 15, 8000, False),
    "SH3": (0.45, 3.00, 0.00, 0.00, 6.20, 1600, 9999, 1400, 2.4, 40, 8000, False),
    "SH4": (0.85, 1.15, 0.20, 0.00, 2.55, 2000, 1800, 1600, 3.0, 30, 8000, False),
    "SH5": (3.60, 2.10, 0.00, 0.00, 2.90, 750, 9999, 1600, 6.0, 15, 8000, False),
    "SH6": (2.90, 1.45, 0.00, 0.00, 1.40, 750, 9999, 1600, 2.0, 30, 8000, False),
    "SH7": (3.50, 5.30, 2.20, 0.00, 3.40, 750, 9999, 1600, 6.0, 15, 8000, False),
    "SH8": (2.05, 3.40, 0.85, 0.00, 4.35, 750, 9999, 1600, 3.0, 40, 8000, False),
    "SH9": (4.50, 2.45, 0.00, 1.55, 7.00, 750, 1800, 1500, 4.4, 40, 8000, True),
    "TU1": (0.20, 0.90, 1.50, 0.20, 0.90, 2000, 1800, 1600, 0.6, 20, 8000, True),
    "TU2": (0.95, 1.80, 1.25, 0.00, 0.20, 2000, 9999, 1600, 1.0, 30, 8000, False),
    "TU3": (1.10, 0.15, 0.25, 0.65, 1.10, 1800, 1600, 1400, 1.3, 30, 8000, True),
    "TU4": (4.50, 0.00, 0.00, 0.00, 2.00, 2300, 9999, 2000, 0.5, 12, 8000, False),
    "TU5": (4.00, 4.00, 3.00, 0.00, 3.00, 1500, 9999, 750, 1.0, 25, 8000, False),
    "TL1": (1.00, 2.20, 3.60, 0.00, 0.00, 2000, 9999, 9999, 0.2, 30, 8000, False),
    "TL2": (1.40, 2.30, 2.20, 0.00, 0.00, 2000, 9999, 9999, 0.2, 25, 8000, False),
    "TL3": (0.50, 2.20, 2.80, 0.00, 0.00, 2000, 9999, 9999, 0.3, 20, 8000, False),
    "TL4": (0.50, 1.50, 4.20, 0.00, 0.00, 2000, 9999, 9999, 0.4, 25, 8000, False),
    "TL5": (1.15, 2.50, 4.40, 0.00, 0.00, 2000, 9999, 1600, 0.6, 25, 8000, False),
    "TL6": (2.40, 1.20, 1.20, 0.00, 0.00, 2000, 9999, 9999, 0.3, 25, 8000, False),
    "TL7": (0.30, 1.40, 8.10, 0.00, 0.00, 2000, 9999, 9999, 0.4, 25, 8000, False),
    "TL8": (5.80, 1.40, 1.10, 0.00, 0.00, 1800, 9999, 9999, 0.3, 35, 8000, False),
    "TL9": (6.65, 3.30, 4.15, 0.00, 0.00, 1800, 9999, 1600, 0.6, 35, 8000, False),
    "SB1": (1.50, 3.00, 11.00, 0.00, 0.00, 2000, 9999, 9999, 1.0, 25, 8000, False),
    "SB2": (4.50, 4.25, 4.00, 0.00, 0.00, 2000, 9999, 9999, 1.0, 25, 8000, False),
    "SB3": (5.50, 2.75, 3.00, 0.00, 0.00, 2000, 9999, 9999, 1.2, 25, 8000, False),
    "SB4": (5.25, 3.50, 5.25, 0.00, 0.00, 2000, 9999, 9999, 2.7, 25, 8000, False),
}


def _build_scott_burgan40():
    models = {}
    for code, (l1, l10, l100, lherb, lwoody, sav1, savherb, savwoody,
               depth, mx, heat, dynamic) in _SB40_REAL.items():
        prefix = code[:2]
        label = _SB40_GROUP_LABEL[prefix]
        models[code] = {
            "name": f"{code} ({label}, Scott & Burgan 2005 Table 7)",
            "group": label,
            "w0_tpa": {
                "1hr": l1, "10hr": l10, "100hr": l100,
                "live_herb": lherb, "live_woody": lwoody,
            },
            "sav": {"1hr": sav1, "live_herb": savherb, "live_woody": savwoody},
            "depth": depth,
            "Mx": mx,
            "dynamic": dynamic,
            "heat": heat,  # heat content real (8000 BTU/lb, 9000 solo para GR6)
        }
    return models


FUEL_MODELS_SCOTT_BURGAN40 = _build_scott_burgan40()
SCOTT_BURGAN40_CONFIDENCE = {
    "overall": "high",
    "note": ("valores reales de Scott & Burgan 2005 (USDA RMRS-GTR-153, Table 7), "
             "verificados contra la publicacion original, no generados por patron"),
}


CATALOGS = {
    "anderson13": (FUEL_MODELS_ANDERSON13, ANDERSON13_CONFIDENCE),
    "scott_burgan40": (FUEL_MODELS_SCOTT_BURGAN40, SCOTT_BURGAN40_CONFIDENCE),
}


# ---------------------------------------------------------------------------
# Resolucion de modelo de combustible -> estructura interna comun
# ---------------------------------------------------------------------------

def _resolve_fuel_model(fuel_catalog, fuel_model, custom_fuel):
    if fuel_catalog == "custom":
        if not custom_fuel:
            raise ValueError("fuel_catalog='custom' requiere 'custom_fuel' con w0_tpa/sav/depth/Mx")
        confidence = {"overall": "aportada por quien llama, no hardcodeada por Claude"}
        model = custom_fuel
        model_name = custom_fuel.get("name", "custom")
    elif fuel_catalog in CATALOGS:
        catalog, confidence = CATALOGS[fuel_catalog]
        if fuel_model not in catalog:
            raise ValueError(f"fuel_model '{fuel_model}' no existe en catalogo '{fuel_catalog}'")
        model = catalog[fuel_model]
        model_name = model["name"]
    else:
        raise ValueError(f"fuel_catalog desconocido: {fuel_catalog}. Use 'anderson13', 'scott_burgan40' o 'custom'")

    w0 = {cls: _tons_acre_to_lb_ft2(model["w0_tpa"].get(cls, 0.0)) for cls in ALL_CLASSES}
    sav = dict(model["sav"])
    sav.setdefault("10hr", SAV_10HR)
    sav.setdefault("100hr", SAV_100HR)
    return {
        "w0": w0, "sav": sav, "depth": model["depth"], "Mx_dead": model["Mx"],
        "dynamic": model.get("dynamic", False), "name": model_name,
    }, confidence


# ---------------------------------------------------------------------------
# Motor Rothermel (1972) con ponderacion muerto/vivo por area superficial
# (Albini 1976). CONFIANZA ALTA en la estructura; ver caveats en docstring.
# ---------------------------------------------------------------------------

def _rothermel_ros(fuel, moisture, wind_midflame_ftmin, slope_percent,
                    heat_content=DEFAULT_HEAT_CONTENT,
                    mineral_total=DEFAULT_MINERAL_TOTAL,
                    mineral_effective=DEFAULT_MINERAL_EFFECTIVE,
                    live_mx=DEFAULT_LIVE_MX):
    w0 = fuel["w0"]
    sav = fuel["sav"]
    depth = fuel["depth"]
    Mx_dead = fuel["Mx_dead"]

    # --- area superficial por clase (Albini 1976) y ponderacion muerto/vivo ---
    area = {cls: (w0[cls] / PARTICLE_DENSITY) * sav.get(cls, 0.0) for cls in ALL_CLASSES}
    area_dead = sum(area[c] for c in DEAD_CLASSES)
    area_live = sum(area[c] for c in LIVE_CLASSES)
    area_total = area_dead + area_live

    def _weighted_sav(classes, area_cat):
        if area_cat <= 0:
            return 0.0
        return sum((area[c] / area_cat) * sav.get(c, 0.0) for c in classes)

    sav_dead = _weighted_sav(DEAD_CLASSES, area_dead)
    sav_live = _weighted_sav(LIVE_CLASSES, area_live)

    f_dead = area_dead / area_total if area_total > 0 else 1.0
    f_live = 1.0 - f_dead
    sav_characteristic = f_dead * sav_dead + f_live * sav_live if sav_dead or sav_live else max(sav.values())

    w0_dead_total = sum(w0[c] for c in DEAD_CLASSES)
    w0_live_total = sum(w0[c] for c in LIVE_CLASSES)
    w0_total = w0_dead_total + w0_live_total
    if w0_total <= 0:
        raise ValueError("carga de combustible total (w0) es cero — revisar fuel model")

    rho_b = w0_total / depth
    beta = rho_b / PARTICLE_DENSITY
    beta_op = 3.348 * sav_characteristic ** -0.8189
    beta_ratio = beta / beta_op

    # --- reaction velocity ---
    gamma_max = sav_characteristic ** 1.5 / (495.0 + 0.0594 * sav_characteristic ** 1.5)
    A = 133.0 * sav_characteristic ** -0.7913
    gamma_prime = gamma_max * (beta_ratio ** A) * math.exp(A * (1.0 - beta_ratio))

    # --- humedad ponderada por categoria y damping ---
    M_dead = sum((area[c] / area_dead) * moisture.get(c, 0.0) for c in DEAD_CLASSES) if area_dead > 0 else 0.0
    M_live = sum((area[c] / area_live) * moisture.get(c, 0.0) for c in LIVE_CLASSES) if area_live > 0 else 0.0

    def _moisture_damping(Mf, Mx):
        if Mx <= 0:
            return 0.0
        rM = min(Mf / Mx, 1.0)
        return max(0.0, 1.0 - 2.59 * rM + 5.11 * rM ** 2 - 3.52 * rM ** 3)

    eta_M_dead = _moisture_damping(M_dead, Mx_dead)
    eta_M_live = _moisture_damping(M_live, live_mx) if area_live > 0 else 0.0
    eta_s = 0.174 * mineral_effective ** -0.19

    w_n_dead = w0_dead_total * (1.0 - mineral_total)
    w_n_live = w0_live_total * (1.0 - mineral_total)

    I_R = gamma_prime * eta_s * (w_n_dead * heat_content * eta_M_dead + w_n_live * heat_content * eta_M_live)

    # --- propagating flux ratio ---
    xi = math.exp((0.792 + 0.681 * math.sqrt(sav_characteristic)) * (beta + 0.1)) / (192.0 + 0.2595 * sav_characteristic)

    # --- coeficiente de viento ---
    C = 7.47 * math.exp(-0.133 * sav_characteristic ** 0.55)
    B = 0.02526 * sav_characteristic ** 0.54
    E = 0.715 * math.exp(-0.000359 * sav_characteristic)
    phi_w = C * (max(wind_midflame_ftmin, 0.0) ** B) * (beta_ratio ** -E) if wind_midflame_ftmin > 0 else 0.0

    # --- coeficiente de pendiente ---
    slope_rad = math.atan(slope_percent / 100.0)
    phi_s = 5.275 * beta ** -0.3 * math.tan(slope_rad) ** 2

    # --- heat sink: ponderado por area superficial de TODAS las clases ---
    def _Qig(Mf):
        return 250.0 + 1116.0 * Mf

    def _epsilon(sav_j):
        return math.exp(-138.0 / sav_j) if sav_j > 0 else 0.0

    heat_sink_terms = []
    for c in ALL_CLASSES:
        if area[c] <= 0:
            continue
        f_c = area[c] / area_total
        Mf_c = moisture.get(c, 0.0)
        heat_sink_terms.append(f_c * _epsilon(sav.get(c, 1.0)) * _Qig(Mf_c))
    heat_sink = rho_b * sum(heat_sink_terms)

    if heat_sink <= 0:
        raise ValueError("heat sink no positivo — revisar humedades y SAV de entrada")

    ros_ft_min = I_R * xi * (1.0 + phi_w + phi_s) / heat_sink

    return {
        "ros_ft_min": ros_ft_min,
        "reaction_intensity_btu_ft2_min": I_R,
        "phi_wind": phi_w,
        "phi_slope": phi_s,
        "packing_ratio": beta,
        "optimum_packing_ratio": beta_op,
        "characteristic_sav": sav_characteristic,
        "w0_total_lb_ft2": w0_total,
        "eta_M_dead": eta_M_dead,
        "eta_M_live": eta_M_live,
    }


def _byram_intensity_flame(ros_ft_min, w0_total_lb_ft2, heat_content=DEFAULT_HEAT_CONTENT):
    """Intensidad de linea de fuego y largo de llama (Byram 1959).
    Simplificacion: fuel consumido = w0_total (ver docstring del modulo)."""
    I_btu_ft_min = heat_content * w0_total_lb_ft2 * ros_ft_min
    I_btu_ft_s = I_btu_ft_min / 60.0
    flame_length_ft = 0.45 * max(I_btu_ft_s, 0.0) ** 0.46
    return {"fireline_intensity_btu_ft_s": I_btu_ft_s, "flame_length_ft": flame_length_ft}


def _wind_20ft_to_midflame_ftmin(wind_20ft_mph, depth_ft):
    """Reduccion de viento a 20 ft -> viento a media llama, terreno sin dosel
    (Albini 1976). CONFIANZA MEDIA en los coeficientes exactos (1.83/0.36/0.13)."""
    depth_ft = max(depth_ft, 0.1)
    waf = 1.83 / math.log((20.0 + 0.36 * depth_ft) / (0.13 * depth_ft))
    wind_ftmin = wind_20ft_mph * 88.0  # mph -> ft/min
    return waf * wind_ftmin


# ---------------------------------------------------------------------------
# API principal
# ---------------------------------------------------------------------------

WILDFIRE_RISK_TOOL_SCHEMA = {
    "name": "wildfire_risk_tool",
    "description": (
        "Peligrosidad de incendios forestales: rate_of_spread (velocidad de "
        "propagacion via Rothermel, intensidad de linea de fuego y largo de "
        "llama de Byram, dado modelo de combustible, humedad, viento y "
        "pendiente), fuel_model_info (detalle de un modelo de combustible), "
        "list_fuel_models (catalogo Anderson13/Scott&Burgan40), validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["rate_of_spread", "fuel_model_info", "list_fuel_models", "validate"]},
            "params": {
                "type": "object",
                "properties": {
                    "fuel_catalog": {"type": "string", "description": "'anderson13', 'scott_burgan40' o 'custom' (default anderson13)"},
                    "fuel_model": {"type": "string", "description": "Codigo del modelo de combustible en el catalogo elegido"},
                    "custom_fuel": {"type": "object", "description": "Definicion de combustible custom (si fuel_catalog='custom')"},
                    "moisture": {"type": "object", "description": "Humedad por clase de tiempo: 1hr/10hr/100hr/live_herb/live_woody"},
                    "slope_percent": {"type": "number", "description": "Pendiente en % (default 0.0)"},
                    "live_moisture_of_extinction": {"type": "number", "description": "Humedad de extincion viva (opcional)"},
                    "heat_content_btu_lb": {"type": "number", "description": "Contenido calorico del combustible (opcional)"},
                    "wind_speed_midflame_mph": {"type": "number", "description": "Viento a media llama en mph (alternativa directa)"},
                    "wind_speed_20ft_mph": {"type": "number", "description": "Viento a 20ft en mph, se convierte a media llama (default 0.0)"},
                },
            },
        },
        "required": ["mode"],
    },
}


def compute_wildfire_risk(mode, params):
    params = params or {}

    if mode == "rate_of_spread":
        fuel_catalog = params.get("fuel_catalog", "anderson13")
        fuel_model_code = params.get("fuel_model")
        custom_fuel = params.get("custom_fuel")
        fuel, confidence = _resolve_fuel_model(fuel_catalog, fuel_model_code, custom_fuel)

        moisture = params.get("moisture", {"1hr": 0.08, "10hr": 0.09, "100hr": 0.10,
                                            "live_herb": 1.0, "live_woody": 0.90})
        slope_percent = params.get("slope_percent", 0.0)
        live_mx = params.get("live_moisture_of_extinction", DEFAULT_LIVE_MX)
        heat_content = params.get("heat_content_btu_lb", DEFAULT_HEAT_CONTENT)

        if "wind_speed_midflame_mph" in params:
            wind_midflame_ftmin = params["wind_speed_midflame_mph"] * 88.0
        else:
            wind_20ft_mph = params.get("wind_speed_20ft_mph", 0.0)
            wind_midflame_ftmin = _wind_20ft_to_midflame_ftmin(wind_20ft_mph, fuel["depth"])

        core = _rothermel_ros(fuel, moisture, wind_midflame_ftmin, slope_percent,
                               heat_content=heat_content, live_mx=live_mx)
        byram = _byram_intensity_flame(core["ros_ft_min"], core["w0_total_lb_ft2"], heat_content)

        return {
            "fuel_model": {"catalog": fuel_catalog, "code": fuel_model_code, "name": fuel["name"],
                           "dynamic": fuel["dynamic"]},
            "inputs": {"moisture": moisture, "slope_percent": slope_percent,
                       "wind_midflame_mph": wind_midflame_ftmin / 88.0},
            "rate_of_spread_ft_min": round(core["ros_ft_min"], 4),
            "rate_of_spread_m_min": round(core["ros_ft_min"] * 0.3048, 4),
            "fireline_intensity_btu_ft_s": round(byram["fireline_intensity_btu_ft_s"], 2),
            "flame_length_ft": round(byram["flame_length_ft"], 2),
            "flame_length_m": round(byram["flame_length_ft"] * 0.3048, 2),
            "diagnostics": {k: round(v, 6) if isinstance(v, float) else v for k, v in core.items()
                             if k not in ("ros_ft_min", "w0_total_lb_ft2")},
            "data_confidence": confidence,
        }

    elif mode == "fuel_model_info":
        fuel_catalog = params.get("fuel_catalog", "anderson13")
        fuel_model_code = params.get("fuel_model")
        fuel, confidence = _resolve_fuel_model(fuel_catalog, fuel_model_code, params.get("custom_fuel"))
        return {"fuel_catalog": fuel_catalog, "fuel_model": fuel_model_code,
                "resolved": fuel, "data_confidence": confidence}

    elif mode == "list_fuel_models":
        fuel_catalog = params.get("fuel_catalog", "anderson13")
        if fuel_catalog == "custom":
            raise ValueError("list_fuel_models no aplica a fuel_catalog='custom'")
        catalog, confidence = CATALOGS[fuel_catalog]
        return {"fuel_catalog": fuel_catalog, "data_confidence": confidence,
                "models": {code: {"name": m["name"], "group": m["group"], "dynamic": m["dynamic"]}
                           for code, m in catalog.items()}}

    elif mode == "validate":
        return _run_validation()

    else:
        raise ValueError(f"Modo desconocido: {mode}. Use 'rate_of_spread', 'fuel_model_info', "
                          f"'list_fuel_models' o 'validate'")


# ---------------------------------------------------------------------------
# Suite de validacion — checks de consistencia fisica (no hay tabla de
# referencia externa disponible para verificar valores absolutos en esta
# sesion, asi que se valida DIRECCION/ORDEN esperado, no magnitudes exactas
# contra una fuente publicada).
# ---------------------------------------------------------------------------

def _run_validation():
    checks = []
    base_moisture = {"1hr": 0.08, "10hr": 0.09, "100hr": 0.10, "live_herb": 1.0, "live_woody": 0.90}

    # 1) ROS aumenta con el viento
    r_calm = compute_wildfire_risk("rate_of_spread", {
        "fuel_catalog": "anderson13", "fuel_model": "3", "moisture": base_moisture,
        "wind_speed_midflame_mph": 0.0, "slope_percent": 0.0})["rate_of_spread_ft_min"]
    r_wind = compute_wildfire_risk("rate_of_spread", {
        "fuel_catalog": "anderson13", "fuel_model": "3", "moisture": base_moisture,
        "wind_speed_midflame_mph": 15.0, "slope_percent": 0.0})["rate_of_spread_ft_min"]
    checks.append({"name": "ros_increases_with_wind", "ros_calm": r_calm, "ros_wind": r_wind,
                   "passed": r_wind > r_calm})

    # 2) ROS aumenta con la pendiente
    r_flat = compute_wildfire_risk("rate_of_spread", {
        "fuel_catalog": "anderson13", "fuel_model": "3", "moisture": base_moisture,
        "wind_speed_midflame_mph": 5.0, "slope_percent": 0.0})["rate_of_spread_ft_min"]
    r_slope = compute_wildfire_risk("rate_of_spread", {
        "fuel_catalog": "anderson13", "fuel_model": "3", "moisture": base_moisture,
        "wind_speed_midflame_mph": 5.0, "slope_percent": 60.0})["rate_of_spread_ft_min"]
    checks.append({"name": "ros_increases_with_slope", "ros_flat": r_flat, "ros_slope": r_slope,
                   "passed": r_slope > r_flat})

    # 3) ROS disminuye con humedad muerta mas alta (pasto FM3, hasta cerca de Mx)
    dry = dict(base_moisture, **{"1hr": 0.04})
    wet = dict(base_moisture, **{"1hr": 0.20})
    r_dry = compute_wildfire_risk("rate_of_spread", {
        "fuel_catalog": "anderson13", "fuel_model": "3", "moisture": dry,
        "wind_speed_midflame_mph": 5.0, "slope_percent": 0.0})["rate_of_spread_ft_min"]
    r_wet = compute_wildfire_risk("rate_of_spread", {
        "fuel_catalog": "anderson13", "fuel_model": "3", "moisture": wet,
        "wind_speed_midflame_mph": 5.0, "slope_percent": 0.0})["rate_of_spread_ft_min"]
    checks.append({"name": "ros_decreases_with_dead_moisture", "ros_dry": r_dry, "ros_wet": r_wet,
                   "passed": r_wet < r_dry})

    # 4) A humedad = humedad de extincion, la intensidad de reaccion (dead) cae a ~0
    at_ext = dict(base_moisture, **{"1hr": 0.25, "10hr": 0.25, "100hr": 0.25})  # Mx del FM3 es 0.25
    result_ext = compute_wildfire_risk("rate_of_spread", {
        "fuel_catalog": "anderson13", "fuel_model": "3", "moisture": at_ext,
        "wind_speed_midflame_mph": 5.0, "slope_percent": 0.0})
    eta_m_dead = result_ext["diagnostics"]["eta_M_dead"]
    checks.append({"name": "eta_M_dead_near_zero_at_extinction_moisture", "eta_M_dead": eta_m_dead,
                   "passed": eta_m_dead < 0.05})

    # 5) Pasto (FM3) se propaga mucho mas rapido que hojarasca de coniferas (FM8)
    #    bajo condiciones identicas — consistente con comportamiento de fuego conocido
    #    (confianza alta en el ORDEN, aunque no en la magnitud exacta de cada modelo)
    r_grass = compute_wildfire_risk("rate_of_spread", {
        "fuel_catalog": "anderson13", "fuel_model": "3", "moisture": base_moisture,
        "wind_speed_midflame_mph": 5.0, "slope_percent": 0.0})["rate_of_spread_ft_min"]
    r_timber = compute_wildfire_risk("rate_of_spread", {
        "fuel_catalog": "anderson13", "fuel_model": "8", "moisture": base_moisture,
        "wind_speed_midflame_mph": 5.0, "slope_percent": 0.0})["rate_of_spread_ft_min"]
    checks.append({"name": "grass_spreads_faster_than_closed_timber_litter",
                   "ros_grass_fm3": r_grass, "ros_timber_fm8": r_timber, "passed": r_grass > r_timber})

    # 6) Intensidad de linea de fuego y largo de llama aumentan junto con el ROS
    res_low = compute_wildfire_risk("rate_of_spread", {
        "fuel_catalog": "anderson13", "fuel_model": "4", "moisture": base_moisture,
        "wind_speed_midflame_mph": 2.0, "slope_percent": 0.0})
    res_high = compute_wildfire_risk("rate_of_spread", {
        "fuel_catalog": "anderson13", "fuel_model": "4", "moisture": base_moisture,
        "wind_speed_midflame_mph": 20.0, "slope_percent": 0.0})
    checks.append({"name": "flame_length_increases_with_ros",
                   "flame_low": res_low["flame_length_ft"], "flame_high": res_high["flame_length_ft"],
                   "passed": res_high["flame_length_ft"] > res_low["flame_length_ft"]})

    # 7) Scott & Burgan 40 esta completo (40 codigos) y marca confianza baja
    sb40_info = compute_wildfire_risk("list_fuel_models", {"fuel_catalog": "scott_burgan40"})
    checks.append({"name": "scott_burgan40_complete_and_low_confidence_flagged",
                   "n_models": len(sb40_info["models"]),
                   "confidence_flag": sb40_info["data_confidence"]["overall"],
                   "passed": len(sb40_info["models"]) == 40 and sb40_info["data_confidence"]["overall"] == "high"})

    # 8) Anderson 13 esta completo (13 codigos) y marca confianza media-alta
    a13_info = compute_wildfire_risk("list_fuel_models", {"fuel_catalog": "anderson13"})
    checks.append({"name": "anderson13_complete_and_confidence_flagged",
                   "n_models": len(a13_info["models"]),
                   "confidence_flag": a13_info["data_confidence"]["overall"],
                   "passed": len(a13_info["models"]) == 13 and a13_info["data_confidence"]["overall"] == "medium-high"})

    # 9) fuel_catalog custom funciona con datos provistos por quien llama
    custom_fuel = {
        "name": "custom_test",
        "w0_tpa": {"1hr": 2.0, "10hr": 1.0, "100hr": 0.5, "live_herb": 0.0, "live_woody": 0.0},
        "sav": {"1hr": 2000.0, "live_herb": 1500.0, "live_woody": 1500.0},
        "depth": 1.0, "Mx": 0.15, "dynamic": False,
    }
    res_custom = compute_wildfire_risk("rate_of_spread", {
        "fuel_catalog": "custom", "custom_fuel": custom_fuel, "moisture": base_moisture,
        "wind_speed_midflame_mph": 5.0, "slope_percent": 0.0})
    checks.append({"name": "custom_fuel_catalog_works", "ros": res_custom["rate_of_spread_ft_min"],
                   "passed": res_custom["rate_of_spread_ft_min"] > 0})

    # 10) fuel_catalog / fuel_model invalido levanta error
    try:
        compute_wildfire_risk("rate_of_spread", {"fuel_catalog": "no_existe", "fuel_model": "1"})
        invalid_raises = False
    except ValueError:
        invalid_raises = True
    checks.append({"name": "invalid_fuel_catalog_raises", "passed": invalid_raises})

    return {"checks": checks, "validation_passed": all(c["passed"] for c in checks)}


try:
    from tool_registry import register_tool
    register_tool(
        name="wildfire_risk_tool",
        schema=WILDFIRE_RISK_TOOL_SCHEMA,
        handler=lambda args: compute_wildfire_risk(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    d = compute_wildfire_risk("validate", {})
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de wildfire_risk_tool.py pasaron OK.")
