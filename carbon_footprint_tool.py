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
  - CO2 por combustion de lena:         ~1.83 kg CO2/kg lena
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
WOOD_CO2_KG_PER_KG_DEFAULT = 1.83
SOLAR_PV_G_CO2_PER_KWH_DEFAULT = 41.0


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

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_carbon_footprint(mode, params=None):
    params = params or {}

    if mode == "wood_vs_solar_heating":
        return _mode_wood_vs_solar_heating(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"Modo desconocido: {mode}. Usar 'wood_vs_solar_heating' o 'validate'.")


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
                "stove_efficiency opcional, heater_efficiency opcional) y validate."
            ),
            "inputSchema": CARBON_FOOTPRINT_TOOL_SCHEMA,
        },
        handler=lambda args: compute_carbon_footprint(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass
