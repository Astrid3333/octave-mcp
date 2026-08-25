"""
food_chemistry_tool.py

Herramienta MCP de quimica de la coccion / ciencia de los alimentos, enfocada
en las 4 reacciones clasicas que transforman los alimentos por calor/tiempo:

    - maillard              : pardeamiento no enzimatico (aminoacido + azucar reductor)
    - caramelization        : descomposicion termica de sacarosa (sin aminoacidos)
    - lipid_oxidation       : oxidacion lipidica (rancidez), periodo de induccion + fase autocatalitica
    - starch_gelatinization : gelatinizacion de almidon (perdida de cristalinidad)
    - validate              : 10 chequeos de consistencia fisica/quimica interna

Todos los modos cineticos usan la ecuacion de Arrhenius:

    k(T) = A * exp(-Ea / (R * T))      [T en Kelvin, R = 8.314 J/(mol*K)]

IMPORTANTE - nivel de confianza:
Los valores de Ea/A/Q10 usados por defecto son ORDENES DE MAGNITUD tipicos de
la literatura de food science (no una calibracion exacta contra un dataset
puntual). Cada resultado trae "confidence_note" aclarando esto. Si el usuario
tiene sus propios parametros cineticos medidos, puede pasarlos explicitamente
(activation_energy_kj_mol, pre_exponential_factor, etc.) y el resultado pasa
a ser tan preciso como esos parametros.
"""

import math

R_GAS = 8.314  # J/(mol*K)


def _celsius_to_kelvin(t_c):
    return t_c + 273.15


def _arrhenius_k(temperature_c, ea_kj_mol, pre_exponential_factor):
    """k(T) = A * exp(-Ea/(R*T)), Ea en kJ/mol -> se convierte a J/mol."""
    t_k = _celsius_to_kelvin(temperature_c)
    ea_j = ea_kj_mol * 1000.0
    return pre_exponential_factor * math.exp(-ea_j / (R_GAS * t_k))


# ---------------------------------------------------------------------------
# 1) MAILLARD
# ---------------------------------------------------------------------------
def _maillard(temperature_c, time_min, ph=7.0, initial_browning_index=0.0,
              activation_energy_kj_mol=100.0, pre_exponential_factor=1.5e11):
    """
    Modelo pseudo-cero-orden de pardeamiento de Maillard (indice de pardeamiento
    BI creciendo linealmente en el tiempo a T constante), con k(T) via Arrhenius.
    Orden de magnitud tipico para sistemas modelo glucosa/aminoacido: Ea ~ 90-160 kJ/mol.

    pH: la Maillard se acelera con pH mas alcalino hasta ~pH 10 (heuristica simple,
    NO calibrada contra un dataset especifico): factor = 1 + 0.15*(pH-7), acotado a >=0.
    """
    if time_min < 0:
        raise ValueError("time_min debe ser >= 0")
    if temperature_c < 0 or temperature_c > 250:
        raise ValueError("temperature_c fuera de rango fisico razonable para coccion (0-250 C)")

    k_base = _arrhenius_k(temperature_c, activation_energy_kj_mol, pre_exponential_factor)
    ph_factor = max(0.0, 1.0 + 0.15 * (ph - 7.0))
    k_eff = k_base * ph_factor

    browning_index = initial_browning_index + k_eff * time_min
    # tiempo estimado para duplicar el indice de pardeamiento actual (o alcanzar BI=1 si parte de 0)
    ref_bi = initial_browning_index if initial_browning_index > 0 else 1.0
    time_to_double_min = ref_bi / k_eff if k_eff > 0 else float("inf")

    return {
        "reaction": "maillard",
        "temperature_c": temperature_c,
        "time_min": time_min,
        "ph": ph,
        "rate_constant_per_min": k_eff,
        "browning_index": browning_index,
        "time_to_reach_bi1_min": time_to_double_min,
        "activation_energy_kj_mol": activation_energy_kj_mol,
        "confidence_note": (
            "Modelo pseudo-cero-orden con Ea/A tipicos de sistemas modelo glucosa-aminoacido "
            "(literatura general food science). No calibrado contra un alimento/dataset especifico; "
            "usar como orden de magnitud, no como valor de laboratorio."
        ),
    }


# ---------------------------------------------------------------------------
# 2) CARAMELIZACION
# ---------------------------------------------------------------------------
def _caramelization(temperature_c, time_min, initial_sucrose_g=100.0,
                     activation_energy_kj_mol=150.0, pre_exponential_factor=8.0e15,
                     onset_temperature_c=160.0):
    """
    Descomposicion termica de sacarosa pura sin aminoacidos: reaccion de primer
    orden (decaimiento exponencial de la concentracion de sacarosa remanente),
    con inversion 1:1:1 mol sacarosa -> mol glucosa + mol fructosa como primer paso
    simplificado (se ignoran productos posteriores tipo HMF/melanoidinas oscuras).

    onset_temperature_c: temperatura de inicio de caramelizacion visible para
    sacarosa (~160 C es el valor tipico citado en textos de food science).
    """
    if time_min < 0:
        raise ValueError("time_min debe ser >= 0")
    if initial_sucrose_g <= 0:
        raise ValueError("initial_sucrose_g debe ser > 0")

    MW_SUCROSE = 342.30  # g/mol
    MW_GLUCOSE = 180.16
    MW_FRUCTOSE = 180.16

    k = _arrhenius_k(temperature_c, activation_energy_kj_mol, pre_exponential_factor)
    fraction_remaining = math.exp(-k * time_min)
    fraction_decomposed = 1.0 - fraction_remaining

    moles_initial = initial_sucrose_g / MW_SUCROSE
    moles_decomposed = moles_initial * fraction_decomposed
    moles_remaining = moles_initial * fraction_remaining

    glucose_g = moles_decomposed * MW_GLUCOSE
    fructose_g = moles_decomposed * MW_FRUCTOSE
    sucrose_remaining_g = moles_remaining * MW_SUCROSE

    return {
        "reaction": "caramelization",
        "temperature_c": temperature_c,
        "time_min": time_min,
        "above_onset_temperature": temperature_c >= onset_temperature_c,
        "onset_temperature_c": onset_temperature_c,
        "rate_constant_per_min": k,
        "sucrose_fraction_remaining": fraction_remaining,
        "sucrose_remaining_g": sucrose_remaining_g,
        "glucose_formed_g": glucose_g,
        "fructose_formed_g": fructose_g,
        "moles_decomposed_mol": moles_decomposed,
        "activation_energy_kj_mol": activation_energy_kj_mol,
        "confidence_note": (
            "Cinetica de primer orden con Ea tipica de descomposicion termica de sacarosa pura "
            "(orden de magnitud de literatura general, no calibracion puntual). Ignora la formacion "
            "de HMF y melanoidinas de etapas posteriores; solo modela sacarosa -> glucosa + fructosa."
        ),
    }


# ---------------------------------------------------------------------------
# 3) OXIDACION LIPIDICA
# ---------------------------------------------------------------------------
def _lipid_oxidation(temperature_c, time_h, initial_peroxide_value=1.0,
                      induction_period_h_ref=100.0, reference_temperature_c=20.0,
                      q10=3.0, autocatalytic_rate_per_h=0.05):
    """
    Modelo de periodo de induccion + fase autocatalitica para el indice de
    peroxidos (PV, meq O2/kg grasa):

      - Para t < t_ind(T):  PV(t) = PV0  (fase de induccion, oxidacion lenta)
      - Para t >= t_ind(T): PV(t) = PV0 * exp(k_auto * (t - t_ind(T)))  (fase autocatalitica)

    t_ind(T) se escala con Q10 desde un periodo de induccion de referencia a
    reference_temperature_c: t_ind(T) = t_ind_ref * Q10^(-(T-T_ref)/10)
    Q10~2-3 es el rango tipico citado para oxidacion lipidica en aceites/grasas.
    """
    if time_h < 0:
        raise ValueError("time_h debe ser >= 0")
    if initial_peroxide_value <= 0:
        raise ValueError("initial_peroxide_value debe ser > 0")

    induction_period_h = induction_period_h_ref * (q10 ** (-(temperature_c - reference_temperature_c) / 10.0))

    if time_h < induction_period_h:
        peroxide_value = initial_peroxide_value
        phase = "induction"
    else:
        peroxide_value = initial_peroxide_value * math.exp(
            autocatalytic_rate_per_h * (time_h - induction_period_h)
        )
        phase = "autocatalytic"

    return {
        "reaction": "lipid_oxidation",
        "temperature_c": temperature_c,
        "time_h": time_h,
        "phase": phase,
        "induction_period_h": induction_period_h,
        "peroxide_value_meq_o2_kg": peroxide_value,
        "q10": q10,
        "confidence_note": (
            "Modelo de induccion + autocatalisis con Q10 tipico de literatura general de oxidacion "
            "lipidica (rango 2-3). El periodo de induccion real depende fuerte del perfil de acidos "
            "grasos y de antioxidantes presentes; usar como orden de magnitud."
        ),
    }


# ---------------------------------------------------------------------------
# 4) GELATINIZACION DE ALMIDON
# ---------------------------------------------------------------------------
_STARCH_CATALOG = {
    # Rangos tipicos citados en literatura de food science (DSC: onset-pico-conclusion, en C)
    # Marcados como valores de referencia tipicos, no una medicion especifica.
    "wheat": {"onset_c": 58.0, "peak_c": 61.0, "conclusion_c": 90.0},
    "corn": {"onset_c": 62.0, "peak_c": 67.0, "conclusion_c": 92.0},
    "potato": {"onset_c": 58.0, "peak_c": 63.0, "conclusion_c": 91.0},
    "rice": {"onset_c": 68.0, "peak_c": 75.0, "conclusion_c": 93.0},
    "cassava": {"onset_c": 62.0, "peak_c": 68.0, "conclusion_c": 90.0},
}


def _starch_gelatinization(temperature_c, time_min, starch_type="wheat",
                            activation_energy_kj_mol=250.0, pre_exponential_factor=1.0e35):
    """
    Grado de gelatinizacion X(t) via cinetica de primer orden (modelo estandar
    en literatura de gelatinizacion de almidon):

        X(t) = 1 - exp(-k(T) * t),   k(T) = A * exp(-Ea/(R*T))

    Ea tipica citada en literatura para gelatinizacion de almidon: ~200-300 kJ/mol
    (muy alta comparada con reacciones quimicas simples, refleja el caracter de
    transicion de fase cooperativa, no una reaccion elemental).
    """
    if starch_type not in _STARCH_CATALOG:
        raise ValueError(f"starch_type debe ser uno de {list(_STARCH_CATALOG.keys())}")
    if time_min < 0:
        raise ValueError("time_min debe ser >= 0")

    catalog = _STARCH_CATALOG[starch_type]
    k = _arrhenius_k(temperature_c, activation_energy_kj_mol, pre_exponential_factor)
    degree_of_gelatinization = 1.0 - math.exp(-k * time_min)
    degree_of_gelatinization = min(1.0, max(0.0, degree_of_gelatinization))

    below_onset = temperature_c < catalog["onset_c"]

    return {
        "reaction": "starch_gelatinization",
        "starch_type": starch_type,
        "temperature_c": temperature_c,
        "time_min": time_min,
        "below_onset_temperature": below_onset,
        "onset_c": catalog["onset_c"],
        "peak_c": catalog["peak_c"],
        "conclusion_c": catalog["conclusion_c"],
        "rate_constant_per_min": k,
        "degree_of_gelatinization": degree_of_gelatinization,
        "activation_energy_kj_mol": activation_energy_kj_mol,
        "confidence_note": (
            "Rango onset/peak/conclusion tomado de valores tipicos de literatura DSC por tipo de "
            "almidon (no una medicion de lote especifico). Cinetica de primer orden estandar para "
            "grado de gelatinizacion; Ea alta refleja transicion de fase cooperativa."
        ),
    }


# ---------------------------------------------------------------------------
# VALIDATE
# ---------------------------------------------------------------------------
def _validate():
    checks = []

    # 1) Maillard: BI crece monotonicamente con el tiempo a T fija
    bi_t1 = _maillard(140, 10)["browning_index"]
    bi_t2 = _maillard(140, 20)["browning_index"]
    checks.append({
        "name": "maillard_monotonic_in_time",
        "passed": bi_t2 > bi_t1,
        "detail": f"BI(10min)={bi_t1:.4f}, BI(20min)={bi_t2:.4f}",
    })

    # 2) Maillard: BI crece monotonicamente con la temperatura a t fijo (Arrhenius)
    bi_low = _maillard(120, 15)["browning_index"]
    bi_high = _maillard(160, 15)["browning_index"]
    checks.append({
        "name": "maillard_monotonic_in_temperature",
        "passed": bi_high > bi_low,
        "detail": f"BI(120C)={bi_low:.4f}, BI(160C)={bi_high:.4f}",
    })

    # 3) Maillard: pH mas alcalino acelera la reaccion (factor heuristico documentado)
    bi_ph7 = _maillard(140, 15, ph=7.0)["browning_index"]
    bi_ph9 = _maillard(140, 15, ph=9.0)["browning_index"]
    checks.append({
        "name": "maillard_ph_effect_direction",
        "passed": bi_ph9 > bi_ph7,
        "detail": f"BI(pH7)={bi_ph7:.4f}, BI(pH9)={bi_ph9:.4f}",
    })

    # 4) Caramelizacion: balance molar exacto sacarosa_inicial = remanente + descompuesta
    car = _caramelization(180, 30, initial_sucrose_g=100.0)
    MW_SUCROSE = 342.30
    moles_initial = 100.0 / MW_SUCROSE
    moles_remaining_check = car["sucrose_remaining_g"] / MW_SUCROSE
    moles_decomposed_check = car["moles_decomposed_mol"]
    balance_error = abs(moles_initial - (moles_remaining_check + moles_decomposed_check))
    checks.append({
        "name": "caramelization_molar_balance",
        "passed": balance_error < 1e-9,
        "detail": f"error absoluto de balance molar = {balance_error:.2e} mol",
    })

    # 5) Caramelizacion: 1 mol sacarosa descompuesta -> 1 mol glucosa + 1 mol fructosa (masa)
    MW_GLUCOSE = 180.16
    expected_glucose_g = car["moles_decomposed_mol"] * MW_GLUCOSE
    checks.append({
        "name": "caramelization_inversion_stoichiometry",
        "passed": abs(car["glucose_formed_g"] - expected_glucose_g) < 1e-6
        and abs(car["glucose_formed_g"] - car["fructose_formed_g"]) < 1e-6,
        "detail": f"glucosa={car['glucose_formed_g']:.4f}g, fructosa={car['fructose_formed_g']:.4f}g",
    })

    # 6) Caramelizacion: a t=0 no hay descomposicion (fraccion remanente = 1)
    car_t0 = _caramelization(180, 0)
    checks.append({
        "name": "caramelization_zero_time_no_decomposition",
        "passed": abs(car_t0["sucrose_fraction_remaining"] - 1.0) < 1e-12,
        "detail": f"fraccion remanente en t=0 = {car_t0['sucrose_fraction_remaining']:.12f}",
    })

    # 7) Oxidacion lipidica: Q10 escala el periodo de induccion en la direccion correcta
    #    y con la razon exacta esperada (T_ref+10 debe dar t_ind_ref / Q10)
    ox_ref = _lipid_oxidation(20, 0, induction_period_h_ref=100.0, reference_temperature_c=20.0, q10=3.0)
    ox_plus10 = _lipid_oxidation(30, 0, induction_period_h_ref=100.0, reference_temperature_c=20.0, q10=3.0)
    ratio = ox_ref["induction_period_h"] / ox_plus10["induction_period_h"]
    checks.append({
        "name": "lipid_oxidation_q10_scaling",
        "passed": abs(ratio - 3.0) < 1e-9,
        "detail": f"t_ind(20C)/t_ind(30C) = {ratio:.6f} (esperado 3.0 = Q10)",
    })

    # 8) Oxidacion lipidica: PV constante durante la induccion, crece despues
    ox_before = _lipid_oxidation(20, 1.0, induction_period_h_ref=100.0)
    ox_after = _lipid_oxidation(20, 150.0, induction_period_h_ref=100.0)
    checks.append({
        "name": "lipid_oxidation_phase_transition",
        "passed": ox_before["phase"] == "induction"
        and ox_after["phase"] == "autocatalytic"
        and ox_after["peroxide_value_meq_o2_kg"] > ox_before["peroxide_value_meq_o2_kg"],
        "detail": f"PV antes={ox_before['peroxide_value_meq_o2_kg']:.4f}, "
                  f"PV despues={ox_after['peroxide_value_meq_o2_kg']:.4f}",
    })

    # 9) Gelatinizacion: grado acotado en [0,1] cerca del onset, y tiende a 1
    #    cuando T esta cerca/por encima de la temperatura de conclusion del catalogo
    #    (a T baja el modelo satura muy lento a proposito -- Arrhenius con Ea alta -- asi
    #    que el chequeo de saturacion usa una T fisicamente coherente con "gelatinizacion completa")
    gel_short = _starch_gelatinization(70, 1, starch_type="wheat")
    gel_hot_long = _starch_gelatinization(95, 60, starch_type="wheat")
    checks.append({
        "name": "starch_gelatinization_bounded_and_saturates",
        "passed": 0.0 <= gel_short["degree_of_gelatinization"] <= 1.0
        and gel_hot_long["degree_of_gelatinization"] > 0.999,
        "detail": f"X(70C,1min)={gel_short['degree_of_gelatinization']:.6f}, "
                  f"X(95C,60min)={gel_hot_long['degree_of_gelatinization']:.6f}",
    })

    # 10) Gelatinizacion: temperatura por debajo del onset del catalogo se marca correctamente
    gel_cold = _starch_gelatinization(40, 10, starch_type="potato")
    checks.append({
        "name": "starch_gelatinization_below_onset_flag",
        "passed": gel_cold["below_onset_temperature"] is True and gel_cold["temperature_c"] < gel_cold["onset_c"],
        "detail": f"T={gel_cold['temperature_c']}C, onset={gel_cold['onset_c']}C, "
                  f"below_onset={gel_cold['below_onset_temperature']}",
    })

    all_passed = all(c["passed"] for c in checks)
    return {
        "reaction": "validate",
        "validation_passed": all_passed,
        "checks": checks,
        "n_checks": len(checks),
        "n_passed": sum(1 for c in checks if c["passed"]),
    }


# ---------------------------------------------------------------------------
# DISPATCHER
# ---------------------------------------------------------------------------
def food_chemistry_tool(mode, **kwargs):
    if mode == "maillard":
        return _maillard(
            temperature_c=kwargs["temperature_c"],
            time_min=kwargs["time_min"],
            ph=kwargs.get("ph", 7.0),
            initial_browning_index=kwargs.get("initial_browning_index", 0.0),
            activation_energy_kj_mol=kwargs.get("activation_energy_kj_mol", 100.0),
            pre_exponential_factor=kwargs.get("pre_exponential_factor", 1.5e11),
        )
    elif mode == "caramelization":
        return _caramelization(
            temperature_c=kwargs["temperature_c"],
            time_min=kwargs["time_min"],
            initial_sucrose_g=kwargs.get("initial_sucrose_g", 100.0),
            activation_energy_kj_mol=kwargs.get("activation_energy_kj_mol", 150.0),
            pre_exponential_factor=kwargs.get("pre_exponential_factor", 8.0e15),
            onset_temperature_c=kwargs.get("onset_temperature_c", 160.0),
        )
    elif mode == "lipid_oxidation":
        return _lipid_oxidation(
            temperature_c=kwargs["temperature_c"],
            time_h=kwargs["time_h"],
            initial_peroxide_value=kwargs.get("initial_peroxide_value", 1.0),
            induction_period_h_ref=kwargs.get("induction_period_h_ref", 100.0),
            reference_temperature_c=kwargs.get("reference_temperature_c", 20.0),
            q10=kwargs.get("q10", 3.0),
            autocatalytic_rate_per_h=kwargs.get("autocatalytic_rate_per_h", 0.05),
        )
    elif mode == "starch_gelatinization":
        return _starch_gelatinization(
            temperature_c=kwargs["temperature_c"],
            time_min=kwargs["time_min"],
            starch_type=kwargs.get("starch_type", "wheat"),
            activation_energy_kj_mol=kwargs.get("activation_energy_kj_mol", 250.0),
            pre_exponential_factor=kwargs.get("pre_exponential_factor", 1.0e35),
        )
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            f"mode desconocido: {mode!r}. Debe ser uno de "
            "['maillard', 'caramelization', 'lipid_oxidation', 'starch_gelatinization', 'validate']"
        )


# ---------------------------------------------------------------------------
# SCHEMA (patron inputSchema anidado, igual que el resto de octave-mcp)
# ---------------------------------------------------------------------------
FOOD_CHEMISTRY_TOOL_SCHEMA = {
    "name": "food_chemistry_tool",
    "description": (
        "Modela las 4 reacciones quimicas clasicas de la coccion: Maillard (pardeamiento "
        "no enzimatico), caramelizacion (descomposicion termica de sacarosa), oxidacion "
        "lipidica (rancidez, periodo de induccion + fase autocatalitica), y gelatinizacion "
        "de almidon (cinetica de primer orden con catalogo de temperaturas onset/peak/conclusion "
        "por tipo de almidon). Todas las cineticas usan Arrhenius. mode='validate' corre 10 "
        "chequeos de consistencia interna."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["maillard", "caramelization", "lipid_oxidation", "starch_gelatinization", "validate"],
                "description": "Que reaccion modelar, o 'validate' para autochequeo",
            },
            "temperature_c": {"type": "number", "description": "Temperatura en grados Celsius"},
            "time_min": {"type": "number", "description": "Tiempo en minutos (maillard, caramelization, starch_gelatinization)"},
            "time_h": {"type": "number", "description": "Tiempo en horas (lipid_oxidation)"},
            "ph": {"type": "number", "description": "pH del sistema (solo maillard, default 7.0)"},
            "initial_browning_index": {"type": "number", "description": "Indice de pardeamiento inicial (maillard, default 0.0)"},
            "initial_sucrose_g": {"type": "number", "description": "Gramos de sacarosa inicial (caramelization, default 100.0)"},
            "onset_temperature_c": {"type": "number", "description": "Temperatura de inicio de caramelizacion visible (default 160.0)"},
            "initial_peroxide_value": {"type": "number", "description": "Indice de peroxidos inicial, meq O2/kg (lipid_oxidation, default 1.0)"},
            "induction_period_h_ref": {"type": "number", "description": "Periodo de induccion de referencia en horas (lipid_oxidation, default 100.0)"},
            "reference_temperature_c": {"type": "number", "description": "Temperatura de referencia para el Q10 (lipid_oxidation, default 20.0)"},
            "q10": {"type": "number", "description": "Coeficiente Q10 de oxidacion lipidica (default 3.0)"},
            "autocatalytic_rate_per_h": {"type": "number", "description": "Tasa de crecimiento en fase autocatalitica, 1/h (default 0.05)"},
            "starch_type": {
                "type": "string",
                "enum": ["wheat", "corn", "potato", "rice", "cassava"],
                "description": "Tipo de almidon (starch_gelatinization, default 'wheat')",
            },
            "activation_energy_kj_mol": {"type": "number", "description": "Energia de activacion Ea en kJ/mol (override opcional del default por reaccion)"},
            "pre_exponential_factor": {"type": "number", "description": "Factor pre-exponencial A de Arrhenius (override opcional del default por reaccion)"},
        },
        "required": ["mode"],
    },
}


def _handler(kwargs):
    mode = kwargs.pop("mode")
    return food_chemistry_tool(mode, **kwargs)


try:
    from tool_registry import register_tool
    register_tool("food_chemistry_tool", FOOD_CHEMISTRY_TOOL_SCHEMA, _handler)
except ImportError:
    pass


if __name__ == "__main__":
    import json
    result = _validate()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print()
    print(f"validation_passed: {result['validation_passed']} "
          f"({result['n_passed']}/{result['n_checks']} checks)")
