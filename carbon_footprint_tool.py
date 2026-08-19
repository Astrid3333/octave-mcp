"""
carbon_footprint_tool.py

Estima y compara la huella de carbono de distintas formas de generar la
misma energía útil (tipicamente calefaccion), pensado para preguntas de
gestion comunitaria del tipo:

    "Cuanto contamina nuestra quema de lena comparada con usar paneles
    solares?"

Modos:
  - wood_vs_solar_heating: compara CO2 emitido para entregar una misma
                cantidad de energia util (kWh) via combustion de lena vs.
                via electricidad de origen solar fotovoltaico (calefaccion
                electrica -- resistiva o bomba de calor, segun heater_efficiency).
  - validate: 5 checks internos con valores calculados a mano.

Factores usados (valores de referencia estandar, no especificos de ningun
proveedor):
  - Poder calorifico de lena seca:      ~4.5 kWh/kg  (~16 MJ/kg)
  - CO2 por combustion de lena:         ~1.7 kg CO2/kg lena
        (fraccion de carbono ~50% en masa, oxidacion completa a CO2;
        cifra de combustion bruta -- ver nota_biogenica abajo)
  - Emision de ciclo de vida de FV:      ~41 g CO2eq/kWh
        (mediana IPCC AR5 para solar fotovoltaica utility-scale; incluye
        fabricacion de paneles, no solo operacion, que es ~0)

Nota importante (no confundir "carbono neutral" con "sin impacto"):
La CO2 de la combustion de lena suele contabilizarse como "biogenica"
(neutral a largo plazo SI la lena viene de manejo forestal sostenible,
porque el carbono ya habia sido capturado por el arbol). Este tool reporta
la emision de combustion igual, porque: (a) libera el carbono de una vez,
no a lo largo de decadas de crecimiento del arbol, y (b) la quema de lena
domestica es ademas la principal fuente de material particulado (PM2.5) en
el sur de Chile durante el invierno -- un problema de calidad del aire
independiente del balance de CO2, que este tool NO cuantifica (fuera de
alcance: requeriria factores de emision de PM2.5 por tipo de combustion,
que dependen mucho de la humedad de la lena y el tipo de cocina/salamandra).
"""

WOOD_HHV_KWH_PER_KG_DEFAULT = 4.5
WOOD_CO2_KG_PER_KG_DEFAULT = 1.7
SOLAR_PV_G_CO2_PER_KWH_DEFAULT = 41.0
GRID_SEN_G_CO2_PER_KWH_DEFAULT = 220.0
# Factor de emisiones GEI del Sistema Electrico Nacional (SEN) de Chile.
# Fuente: Coordinador Electrico Nacional, factor oficial 2023 = 238.4 gCO2/kWh
# (0.2384 tCO2e/MWh); Generadoras de Chile reporta ~200 gCO2/kWh para 2024
# (70% de generacion renovable). 220 es un punto medio razonable entre ambos
# anos -- a diferencia del factor de lena/solar, este NO es estable en el
# tiempo: la matriz chilena se esta descarbonizando rapido (63% de baja desde
# 2013 segun el mismo gremio), asi que conviene actualizar este default
# periodicamente o pasar grid_g_co2_per_kwh explicito con el dato del ano en
# curso (energia.gob.cl/indicadores-ambientales-factor-de-emisiones-gei-del-sistema-electrico-nacional).


def _mode_wood_vs_solar_heating(p):
    energy_needed_kwh = float(p["energy_needed_kwh"])
    if energy_needed_kwh < 0:
        raise ValueError("energy_needed_kwh debe ser >= 0")

    stove_efficiency = float(p.get("stove_efficiency", 0.65))
    heater_efficiency = float(p.get("heater_efficiency", 1.0))
    wood_hhv_kwh_per_kg = float(p.get("wood_hhv_kwh_per_kg", WOOD_HHV_KWH_PER_KG_DEFAULT))
    wood_co2_kg_per_kg = float(p.get("wood_co2_kg_per_kg", WOOD_CO2_KG_PER_KG_DEFAULT))
    solar_g_co2_per_kwh = float(p.get("solar_g_co2_per_kwh", SOLAR_PV_G_CO2_PER_KWH_DEFAULT))

    if not (0 < stove_efficiency <= 1):
        raise ValueError("stove_efficiency debe estar en (0, 1]")
    if not (0 < heater_efficiency):
        raise ValueError("heater_efficiency debe ser > 0 (1.0 = resistiva, ~3.0 = bomba de calor)")

    # Camino A: lena
    wood_energy_input_kwh = energy_needed_kwh / stove_efficiency
    wood_kg = wood_energy_input_kwh / wood_hhv_kwh_per_kg
    wood_co2_kg = wood_kg * wood_co2_kg_per_kg

    # Camino B: electricidad de origen solar
    elec_input_kwh = energy_needed_kwh / heater_efficiency
    solar_co2_kg = elec_input_kwh * (solar_g_co2_per_kwh / 1000.0)

    reduction_pct = (
        (wood_co2_kg - solar_co2_kg) / wood_co2_kg * 100.0 if wood_co2_kg > 0 else 0.0
    )

    report_lines = [
        f"Para entregar {energy_needed_kwh:.1f} kWh de energia util:",
        f"- Via lena: {wood_kg:.2f} kg de lena quemada -> {wood_co2_kg:.2f} kg CO2 "
        f"(eficiencia de estufa {stove_efficiency*100:.0f}%).",
        f"- Via solar+electrico: {elec_input_kwh:.2f} kWh electricos -> {solar_co2_kg:.3f} kg CO2 "
        f"(eficiencia de calefaccion {heater_efficiency*100:.0f}%).",
        f"Reduccion de CO2 usando solar en vez de lena: {reduction_pct:.1f}%.",
        "",
        "Nota: la CO2 de la lena suele contarse como 'biogenica' si el bosque se maneja "
        "de forma sostenible, pero se libera de una sola vez (no a lo largo de decadas "
        "de crecimiento del arbol), y la quema domestica es ademas la principal fuente "
        "de material particulado (PM2.5) en el sur de Chile en invierno -- un problema "
        "de calidad de aire que este calculo no cuantifica.",
    ]

    return {
        "energy_needed_kwh": energy_needed_kwh,
        "wood_kg": round(wood_kg, 4),
        "wood_co2_kg": round(wood_co2_kg, 4),
        "elec_input_kwh": round(elec_input_kwh, 4),
        "solar_co2_kg": round(solar_co2_kg, 4),
        "reduction_pct": round(reduction_pct, 2),
        "report": "\n".join(report_lines),
    }


def _mode_wood_vs_grid_heating(p):
    """
    Igual que _mode_wood_vs_solar_heating pero compara contra el factor de
    emisiones REAL de la matriz electrica chilena (SEN) en vez de asumir
    electricidad 100% solar. Util para el caso real de calefaccion electrica
    conectada a la red, no a paneles propios.
    """
    energy_needed_kwh = float(p["energy_needed_kwh"])
    if energy_needed_kwh < 0:
        raise ValueError("energy_needed_kwh debe ser >= 0")

    stove_efficiency = float(p.get("stove_efficiency", 0.65))
    heater_efficiency = float(p.get("heater_efficiency", 1.0))
    wood_hhv_kwh_per_kg = float(p.get("wood_hhv_kwh_per_kg", WOOD_HHV_KWH_PER_KG_DEFAULT))
    wood_co2_kg_per_kg = float(p.get("wood_co2_kg_per_kg", WOOD_CO2_KG_PER_KG_DEFAULT))
    grid_g_co2_per_kwh = float(p.get("grid_g_co2_per_kwh", GRID_SEN_G_CO2_PER_KWH_DEFAULT))

    if not (0 < stove_efficiency <= 1):
        raise ValueError("stove_efficiency debe estar en (0, 1]")
    if not (0 < heater_efficiency):
        raise ValueError("heater_efficiency debe ser > 0 (1.0 = resistiva, ~3.0 = bomba de calor)")

    wood_energy_input_kwh = energy_needed_kwh / stove_efficiency
    wood_kg = wood_energy_input_kwh / wood_hhv_kwh_per_kg
    wood_co2_kg = wood_kg * wood_co2_kg_per_kg

    elec_input_kwh = energy_needed_kwh / heater_efficiency
    grid_co2_kg = elec_input_kwh * (grid_g_co2_per_kwh / 1000.0)

    reduction_pct = (
        (wood_co2_kg - grid_co2_kg) / wood_co2_kg * 100.0 if wood_co2_kg > 0 else 0.0
    )

    report_lines = [
        f"Para entregar {energy_needed_kwh:.1f} kWh de energia util:",
        f"- Via lena: {wood_kg:.2f} kg de lena quemada -> {wood_co2_kg:.2f} kg CO2 "
        f"(eficiencia de estufa {stove_efficiency*100:.0f}%).",
        f"- Via electricidad de la red (SEN, factor {grid_g_co2_per_kwh:.0f} gCO2/kWh): "
        f"{elec_input_kwh:.2f} kWh electricos -> {grid_co2_kg:.2f} kg CO2 "
        f"(eficiencia de calefaccion {heater_efficiency*100:.0f}%).",
        f"Reduccion de CO2 usando electricidad de red en vez de lena: {reduction_pct:.1f}%.",
        "",
        "Nota: a diferencia del modo wood_vs_solar_heating (que asume electricidad "
        "100% fotovoltaica), este modo usa el factor de emisiones REAL de la matriz "
        "electrica chilena (SEN), que mezcla renovables con termoelectrica a gas y "
        "carbon -- por eso el ahorro de CO2 acá es menor que contra solar puro, y "
        "cambia ano a ano segun avance la descarbonizacion del sistema.",
    ]

    return {
        "energy_needed_kwh": energy_needed_kwh,
        "wood_kg": round(wood_kg, 4),
        "wood_co2_kg": round(wood_co2_kg, 4),
        "elec_input_kwh": round(elec_input_kwh, 4),
        "grid_co2_kg": round(grid_co2_kg, 4),
        "grid_g_co2_per_kwh_used": grid_g_co2_per_kwh,
        "reduction_pct": round(reduction_pct, 2),
        "report": "\n".join(report_lines),
    }


def _mode_annual_projection(p):
    """
    Proyeccion multi-anual de wood_vs_solar_heating o wood_vs_grid_heating,
    segun el parametro comparison ("solar" default, o "grid" contra el
    factor real de la matriz electrica chilena/SEN). Acumula kg CO2 ano a
    ano.

    Con comparison="solar" admite fv_degradation_pct_per_year (default 0.0):
    reduce el AHORRO (wood_co2 - clean_co2) atribuible al sistema FV en cada
    ano, no el clean_co2 directamente (encoger clean_co2 invertiria el signo:
    menos clean_co2 = mas ahorro, al reves de lo esperado). El ahorro decae
    geometricamente: savings_n = savings_year1 * (1 - tasa)^(n-1), y
    clean_co2_n se deriva como wood_co2_per_year - savings_n (por lo tanto
    clean_co2 crece hacia wood_co2_per_year a medida que el beneficio del
    sistema decae). IMPORTANTE: esto NO modela de donde sale la energia
    faltante por la degradacion (backup a red, menor cobertura de la
    demanda, etc.) -- solo reporta que el ahorro atribuible a ese sistema
    decae con el tiempo; el resto queda fuera de alcance.
    fv_degradation_pct_per_year no aplica con comparison="grid" (la red no
    es un sistema propio que se degrade).
    """
    annual_energy_needed_kwh = float(p["annual_energy_needed_kwh"])
    years = int(p.get("years", 20))
    if years < 0:
        raise ValueError("years debe ser >= 0")

    comparison = p.get("comparison", "solar")
    if comparison not in ("solar", "grid"):
        raise ValueError("comparison debe ser 'solar' o 'grid'")

    fv_degradation_pct_per_year = float(p.get("fv_degradation_pct_per_year", 0.0))
    if fv_degradation_pct_per_year < 0:
        raise ValueError("fv_degradation_pct_per_year debe ser >= 0")
    if fv_degradation_pct_per_year > 0 and comparison != "solar":
        raise ValueError("fv_degradation_pct_per_year solo aplica con comparison='solar'")

    base_params = dict(p)
    base_params["energy_needed_kwh"] = annual_energy_needed_kwh
    for key in ("annual_energy_needed_kwh", "years", "comparison", "fv_degradation_pct_per_year"):
        base_params.pop(key, None)

    if comparison == "solar":
        base = _mode_wood_vs_solar_heating(base_params)
        clean_co2_year1 = base["solar_co2_kg"]
    else:
        base = _mode_wood_vs_grid_heating(base_params)
        clean_co2_year1 = base["grid_co2_kg"]

    wood_co2_per_year = base["wood_co2_kg"]

    cumulative_wood, cumulative_clean, cumulative_savings = [], [], []
    running_wood = running_clean = running_savings = 0.0

    for y in range(1, years + 1):
        degradation_factor = (1.0 - fv_degradation_pct_per_year / 100.0) ** (y - 1)
        # El ahorro atribuible al sistema decae con la degradacion (no el CO2
        # del lado limpio, que se derivaria mal si se encoge directamente --
        # eso invertiria el signo: menos clean_co2 = MAS ahorro, al reves de
        # lo esperado). clean_this_year se recalcula desde el ahorro ya
        # decaido, para que crezca hacia wood_co2_per_year a medida que la
        # degradacion reduce el beneficio atribuible al sistema.
        savings_this_year = (wood_co2_per_year - clean_co2_year1) * degradation_factor
        clean_this_year = wood_co2_per_year - savings_this_year

        running_wood += wood_co2_per_year
        running_clean += clean_this_year
        running_savings += savings_this_year

        cumulative_wood.append(round(running_wood, 4))
        cumulative_clean.append(round(running_clean, 4))
        cumulative_savings.append(round(running_savings, 4))

    milestone_years = [y for y in (1, 5, 10, 20) if y <= years]
    milestones = [
        {
            "year": y,
            "cumulative_wood_co2_kg": cumulative_wood[y - 1],
            "cumulative_clean_co2_kg": cumulative_clean[y - 1],
            "cumulative_savings_kg": cumulative_savings[y - 1],
        }
        for y in milestone_years
    ]

    result = {
        "annual_energy_needed_kwh": annual_energy_needed_kwh,
        "years": years,
        "comparison": comparison,
        "fv_degradation_pct_per_year": fv_degradation_pct_per_year,
        "wood_co2_per_year_kg": round(wood_co2_per_year, 4),
        "clean_co2_per_year_kg": round(clean_co2_year1, 4),
        "savings_per_year_kg": round(wood_co2_per_year - clean_co2_year1, 4),
        "cumulative_wood_co2_kg": cumulative_wood,
        "cumulative_clean_co2_kg": cumulative_clean,
        "cumulative_savings_kg": cumulative_savings,
        "milestones": milestones,
        "note": (
            "Modelo lineal en energia y factores de emision (constantes ano a "
            "ano salvo por fv_degradation_pct_per_year si se especifica). No "
            "incluye ahorro economico -- este tool no tiene precios de "
            "referencia de lena/electricidad."
        ),
    }

    # Alias de compatibilidad con el nombre historico de estas claves
    # (comparison="solar" sigue siendo el default y el comportamiento previo)
    if comparison == "solar":
        result["solar_co2_per_year_kg"] = result["clean_co2_per_year_kg"]
        result["cumulative_solar_co2_kg"] = result["cumulative_clean_co2_kg"]
    else:
        result["grid_co2_per_year_kg"] = result["clean_co2_per_year_kg"]
        result["cumulative_grid_co2_kg"] = result["cumulative_clean_co2_kg"]

    return result

def _validate():
    checks = []

    # Check 1: valores de referencia con defaults, calculados a mano
    r = _mode_wood_vs_solar_heating({"energy_needed_kwh": 10.0})
    wood_energy_input = 10.0 / 0.65
    wood_kg_expected = wood_energy_input / WOOD_HHV_KWH_PER_KG_DEFAULT
    wood_co2_expected = wood_kg_expected * WOOD_CO2_KG_PER_KG_DEFAULT
    solar_co2_expected = 10.0 * (SOLAR_PV_G_CO2_PER_KWH_DEFAULT / 1000.0)
    checks.append({
        "name": "defaults_calculo_manual",
        "wood_co2_expected": round(wood_co2_expected, 4), "wood_co2_actual": r["wood_co2_kg"],
        "solar_co2_expected": round(solar_co2_expected, 4), "solar_co2_actual": r["solar_co2_kg"],
        "passed": bool(
            abs(r["wood_co2_kg"] - wood_co2_expected) < 1e-3
            and abs(r["solar_co2_kg"] - solar_co2_expected) < 1e-3
        ),
    })

    # Check 2: linealidad -- duplicar la energia requerida debe duplicar
    # ambas emisiones (misma eficiencia, mismos factores)
    r1 = _mode_wood_vs_solar_heating({"energy_needed_kwh": 5.0})
    r2 = _mode_wood_vs_solar_heating({"energy_needed_kwh": 10.0})
    checks.append({
        "name": "linealidad_energia_vs_emisiones",
        "wood_ratio": round(r2["wood_co2_kg"] / r1["wood_co2_kg"], 4),
        "solar_ratio": round(r2["solar_co2_kg"] / r1["solar_co2_kg"], 4),
        "passed": bool(
            abs(r2["wood_co2_kg"] / r1["wood_co2_kg"] - 2.0) < 1e-6
            and abs(r2["solar_co2_kg"] / r1["solar_co2_kg"] - 2.0) < 1e-6
        ),
    })

    # Check 3: solar siempre emite muchisimo menos que lena para eficiencias
    # tipicas (estufa 40-80%, calefaccion electrica 1.0-4.0 de "eficiencia")
    all_much_lower = True
    for stove_eff in (0.4, 0.65, 0.8):
        for heater_eff in (1.0, 2.5, 4.0):
            rr = _mode_wood_vs_solar_heating({
                "energy_needed_kwh": 20.0,
                "stove_efficiency": stove_eff, "heater_efficiency": heater_eff,
            })
            if not (rr["solar_co2_kg"] < rr["wood_co2_kg"]):
                all_much_lower = False
    checks.append({
        "name": "solar_siempre_menor_que_lena_rango_tipico",
        "passed": bool(all_much_lower),
    })

    # Check 4: energia requerida cero no revienta (division por cero en
    # reduction_pct evitada explicitamente)
    r0 = _mode_wood_vs_solar_heating({"energy_needed_kwh": 0.0})
    checks.append({
        "name": "energia_cero_no_revienta",
        "wood_co2": r0["wood_co2_kg"], "solar_co2": r0["solar_co2_kg"],
        "reduction_pct": r0["reduction_pct"],
        "passed": bool(r0["wood_co2_kg"] == 0.0 and r0["solar_co2_kg"] == 0.0 and r0["reduction_pct"] == 0.0),
    })

    # Check 5: parametro requerido faltante da error explicito, no crash
    try:
        _mode_wood_vs_solar_heating({})
        check5_passed = False
    except KeyError:
        check5_passed = True
    checks.append({
        "name": "energy_needed_kwh_faltante_da_error_no_crash",
        "passed": bool(check5_passed),
    })

    # Check 6: annual_projection, year 1 debe coincidir exactamente con el
    # calculo puntual base (misma energia, mismos defaults)
    base_single = _mode_wood_vs_solar_heating({"energy_needed_kwh": 15.0})
    proj = _mode_annual_projection({"annual_energy_needed_kwh": 15.0, "years": 10})
    checks.append({
        "name": "annual_projection_year1_matches_single_calc",
        "single_wood_co2": base_single["wood_co2_kg"], "proj_wood_co2_per_year": proj["wood_co2_per_year_kg"],
        "passed": bool(abs(base_single["wood_co2_kg"] - proj["wood_co2_per_year_kg"]) < 1e-6),
    })

    # Check 7: annual_projection, linealidad acumulada -- el ahorro acumulado
    # en el ultimo ano debe ser exactamente savings_per_year_kg * years
    expected_final_savings = round(proj["savings_per_year_kg"] * 10, 4)
    checks.append({
        "name": "annual_projection_cumulative_linear",
        "expected": expected_final_savings, "actual": proj["cumulative_savings_kg"][-1],
        "passed": bool(abs(proj["cumulative_savings_kg"][-1] - expected_final_savings) < 1e-6),
    })

    # Check 8: annual_projection con years=0 no revienta -- listas vacias,
    # sin division por cero ni index error
    proj0 = _mode_annual_projection({"annual_energy_needed_kwh": 15.0, "years": 0})
    checks.append({
        "name": "annual_projection_years_cero_no_revienta",
        "years": proj0["years"], "cumulative_len": len(proj0["cumulative_savings_kg"]),
        "passed": bool(proj0["years"] == 0 and len(proj0["cumulative_savings_kg"]) == 0),
    })

    # Check 9: annual_energy_needed_kwh faltante da error explicito, no crash
    try:
        _mode_annual_projection({})
        check9_passed = False
    except KeyError:
        check9_passed = True
    checks.append({
        "name": "annual_projection_energia_faltante_da_error_no_crash",
        "passed": bool(check9_passed),
    })

    # Check 10: wood_vs_grid_heating, valores de referencia con defaults,
    # calculados a mano (mismo patron que el check de solar)
    rg = _mode_wood_vs_grid_heating({"energy_needed_kwh": 10.0})
    wood_co2_expected_g = wood_kg_expected * WOOD_CO2_KG_PER_KG_DEFAULT
    grid_co2_expected = 10.0 * (GRID_SEN_G_CO2_PER_KWH_DEFAULT / 1000.0)
    checks.append({
        "name": "grid_defaults_calculo_manual",
        "wood_co2_expected": round(wood_co2_expected_g, 4), "wood_co2_actual": rg["wood_co2_kg"],
        "grid_co2_expected": round(grid_co2_expected, 4), "grid_co2_actual": rg["grid_co2_kg"],
        "passed": bool(
            abs(rg["wood_co2_kg"] - wood_co2_expected_g) < 1e-3
            and abs(rg["grid_co2_kg"] - grid_co2_expected) < 1e-3
        ),
    })

    # Check 11: wood_vs_grid_heating, la lena sigue emitiendo mas que la red
    # (aun con matriz mixta, no 100% renovable) para eficiencias tipicas
    all_grid_lower = True
    for stove_eff in (0.4, 0.65, 0.8):
        for heater_eff in (1.0, 2.5, 4.0):
            rrg = _mode_wood_vs_grid_heating({
                "energy_needed_kwh": 20.0,
                "stove_efficiency": stove_eff, "heater_efficiency": heater_eff,
            })
            if not (rrg["grid_co2_kg"] < rrg["wood_co2_kg"]):
                all_grid_lower = False
    checks.append({
        "name": "grid_siempre_menor_que_lena_rango_tipico",
        "passed": bool(all_grid_lower),
    })

    # Check 12: wood_vs_grid_heating, ahorro vs. red debe ser MENOR o igual
    # que el ahorro vs. solar puro (la red tiene mas gCO2/kWh que FV solo)
    r_solar = _mode_wood_vs_solar_heating({"energy_needed_kwh": 20.0})
    r_grid = _mode_wood_vs_grid_heating({"energy_needed_kwh": 20.0})
    checks.append({
        "name": "grid_reduction_menor_o_igual_que_solar",
        "reduction_pct_solar": r_solar["reduction_pct"], "reduction_pct_grid": r_grid["reduction_pct"],
        "passed": bool(r_grid["reduction_pct"] <= r_solar["reduction_pct"] + 1e-9),
    })

    # Check 13: wood_vs_grid_heating, energia cero no revienta
    rg0 = _mode_wood_vs_grid_heating({"energy_needed_kwh": 0.0})
    checks.append({
        "name": "grid_energia_cero_no_revienta",
        "wood_co2": rg0["wood_co2_kg"], "grid_co2": rg0["grid_co2_kg"],
        "passed": bool(rg0["wood_co2_kg"] == 0.0 and rg0["grid_co2_kg"] == 0.0 and rg0["reduction_pct"] == 0.0),
    })

    # Check 14: wood_vs_grid_heating, parametro requerido faltante da error
    try:
        _mode_wood_vs_grid_heating({})
        check14_passed = False
    except KeyError:
        check14_passed = True
    checks.append({
        "name": "grid_energy_needed_kwh_faltante_da_error_no_crash",
        "passed": bool(check14_passed),
    })

    # Check 15: annual_projection con comparison='grid', year 1 debe
    # coincidir con wood_vs_grid_heating puntual (mismo patron que check 6)
    base_single_grid = _mode_wood_vs_grid_heating({"energy_needed_kwh": 15.0})
    proj_grid = _mode_annual_projection({"annual_energy_needed_kwh": 15.0, "years": 10, "comparison": "grid"})
    checks.append({
        "name": "annual_projection_grid_year1_matches_single_calc",
        "single_grid_co2": base_single_grid["grid_co2_kg"], "proj_clean_co2_per_year": proj_grid["clean_co2_per_year_kg"],
        "passed": bool(abs(base_single_grid["grid_co2_kg"] - proj_grid["clean_co2_per_year_kg"]) < 1e-6),
    })

    # Check 16: annual_projection con fv_degradation_pct_per_year>0, el CO2
    # limpio acumulado debe ser MAYOR que sin degradacion (el sistema
    # entrega/evita menos con el tiempo -> el 'no evitado' crece) y el ahorro
    # acumulado debe ser MENOR que el caso sin degradacion
    proj_no_deg = _mode_annual_projection({"annual_energy_needed_kwh": 15.0, "years": 10, "comparison": "solar"})
    proj_deg = _mode_annual_projection({
        "annual_energy_needed_kwh": 15.0, "years": 10, "comparison": "solar",
        "fv_degradation_pct_per_year": 5.0,
    })
    checks.append({
        "name": "annual_projection_degradation_reduce_savings",
        "savings_sin_degradacion": proj_no_deg["cumulative_savings_kg"][-1],
        "savings_con_degradacion": proj_deg["cumulative_savings_kg"][-1],
        "passed": bool(proj_deg["cumulative_savings_kg"][-1] < proj_no_deg["cumulative_savings_kg"][-1]),
    })

    # Check 17: fv_degradation_pct_per_year con comparison='grid' debe dar
    # error explicito (la red no es un sistema propio que se degrade)
    try:
        _mode_annual_projection({
            "annual_energy_needed_kwh": 15.0, "comparison": "grid",
            "fv_degradation_pct_per_year": 5.0,
        })
        check17_passed = False
    except ValueError:
        check17_passed = True
    checks.append({
        "name": "annual_projection_degradation_con_grid_da_error_no_crash",
        "passed": bool(check17_passed),
    })

    # Check 18: comparison invalido (ni solar ni grid) debe dar error explicito
    try:
        _mode_annual_projection({"annual_energy_needed_kwh": 15.0, "comparison": "nuclear"})
        check18_passed = False
    except ValueError:
        check18_passed = True
    checks.append({
        "name": "annual_projection_comparison_invalido_da_error_no_crash",
        "passed": bool(check18_passed),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_carbon_footprint(mode, params=None):
    params = params or {}

    if mode == "wood_vs_solar_heating":
        return _mode_wood_vs_solar_heating(params)
    elif mode == "wood_vs_grid_heating":
        return _mode_wood_vs_grid_heating(params)
    elif mode == "annual_projection":
        return _mode_annual_projection(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"Modo desconocido: {mode}. Usar 'wood_vs_solar_heating', 'wood_vs_grid_heating', 'annual_projection' o 'validate'.")


if __name__ == "__main__":
    import json
    print(json.dumps(compute_carbon_footprint("validate"), indent=2, ensure_ascii=False))


CARBON_FOOTPRINT_TOOL_SCHEMA = {
    "type": "object",
    "properties": {"mode": {"type": "string"}, "params": {"type": "object"}},
    "required": ["mode"],
}

try:
    from tool_registry import register_tool
    register_tool(
        name="carbon_footprint_tool",
        schema={
            "name": "carbon_footprint_tool",
            "description": (
                "Estima y compara la huella de carbono (kg CO2) de entregar una misma "
                "energia util via combustion de lena vs. electricidad de origen solar "
                "fotovoltaico -- p.ej. 'cuanto contamina nuestra quema de lena comparada "
                "con usar paneles solares'. Modo wood_vs_solar_heating (energy_needed_kwh, "
                "stove_efficiency opcional, heater_efficiency opcional), wood_vs_grid_heating "
                "(igual pero contra el factor de emisiones REAL de la matriz electrica "
                "chilena/SEN en vez de FV puro -- mas realista para calefaccion conectada "
                "a la red), annual_projection (annual_energy_needed_kwh, years, comparison "
                "opcional 'solar' o 'grid', fv_degradation_pct_per_year opcional solo con "
                "comparison='solar' -- proyecta el calculo acumulado a varios anos, sin "
                "ahorro economico) y validate."
            ),
            "inputSchema": CARBON_FOOTPRINT_TOOL_SCHEMA,
        },
        handler=lambda args: compute_carbon_footprint(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass
