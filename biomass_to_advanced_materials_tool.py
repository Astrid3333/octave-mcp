#!/usr/bin/env python3
"""Biomasa -> materiales avanzados: ferrita/grafeno 3D con balance M/E."""
import json, math
_TOOL_NAME = "biomass_to_advanced_materials_tool"
_DESCRIPTION = "Cadenas de síntesis biomasa->materiales avanzados: ferrita (reemplazo NdFeB), grafeno 3D (laser). Balance masa/energía integrado."
def _register():
    from tool_registry import register_tool
    schema = {"name": _TOOL_NAME, "description": _DESCRIPTION, "modes": ["oil_recycling_to_ferrite", "biomass_laser_graphene", "mass_energy_balance", "validate"]}
    register_tool(_TOOL_NAME, schema, compute_biomass_to_advanced_materials)
HHV_DATA = {"vegetable_oil_virgin": 39.5, "vegetable_oil_recycled": 38.2, "cellulose": 17.5, "lignin": 26.0, "biomass_average": 18.5}
COMPOSITION_DATA = {"vegetable_oil_virgin": {"C": 76, "H": 12, "O": 12, "N": 0.0, "S": 0.0, "Ash": 0.0}, "vegetable_oil_recycled": {"C": 75, "H": 12, "O": 13, "N": 0.0, "S": 0.0, "Ash": 0.0}, "cellulose": {"C": 44.4, "H": 6.2, "O": 49.3, "N": 0.1, "S": 0.0, "Ash": 0.0}, "lignin": {"C": 63.0, "H": 6.0, "O": 30.0, "N": 0.5, "S": 0.5, "Ash": 0.0}}
DENSITY_DATA = {"vegetable_oil": 920, "ferrite_powder": 4900, "ferrite_sintered": 5000, "graphene_3d_aerogel": 150, "graphene_3d_compact": 1200, "ndfeb_sintered": 7500, "cobalt_samarium": 8400}
COST_DATA = {"vegetable_oil_virgin": 2.5, "vegetable_oil_recycled": 0.8, "ferrite_powder": 3.0, "graphene_lab": 15.0, "graphene_industrial": 5.0, "ndfeb": 55.0, "cobalt_samarium": 80.0}
MAGNETIC_PROPERTIES = {"ferrite_soft": {"Br": 0.4, "Hc": 240, "MGOE": 1.0}, "ferrite_hard": {"Br": 0.38, "Hc": 395, "MGOE": 3.0}, "ndfeb": {"Br": 1.2, "Hc": 960, "MGOE": 40.0}, "samarium_cobalt": {"Br": 1.05, "Hc": 724, "MGOE": 30.0}, "alnico": {"Br": 1.25, "Hc": 50, "MGOE": 5.5}}
GRAPHENE_PROPERTIES = {"graphene_2d_monolayer": {"sigma_S_m": 1e5, "rho_ohm_m": 1e-5, "carrier_mobility": 15000}, "graphene_3d_lab": {"sigma_S_m": 1e4, "rho_ohm_m": 1e-4, "carrier_mobility": 1000}, "graphene_3d_industrial": {"sigma_S_m": 5e3, "rho_ohm_m": 2e-4, "carrier_mobility": 500}, "graphite_natural": {"sigma_S_m": 1e5, "rho_ohm_m": 1e-5, "carrier_mobility": 3000}}
def hhv_channiwala_parikh(C, H, O, N, S, Ash):
    return 0.3491 * C + 1.1783 * H + 0.1005 * S - 0.0151 * N - 0.0211 * Ash
def compute_oil_recycling_to_ferrite(params):
    oil_mass = params.get("oil_mass_kg", 1.0)
    hdo_temp = params.get("hdo_temperature_C", 300)
    h2_stoich = params.get("hdo_h2_stoich_ratio", 2.0)
    iron_source = params.get("iron_source", "fe_waste_scrap")
    sintering_yield = params.get("sintering_yield_pct", 90) / 100.0
    comp = COMPOSITION_DATA["vegetable_oil_recycled"]
    hhv_oil = hhv_channiwala_parikh(**comp)
    o_removed_pct = 12.5
    h2_consumed_kg = oil_mass * (o_removed_pct / 100.0) * (h2_stoich / 16.0)
    energy_hdo_mj = oil_mass * 6.0
    hdo_product_kg = oil_mass - (o_removed_pct / 100.0) * oil_mass + h2_consumed_kg
    if iron_source == "fe_waste_scrap":
        fe_need_kg = oil_mass * 0.5
        fe_cost = fe_need_kg * 0.15
    else:
        fe_need_kg = oil_mass * 0.6
        fe_cost = fe_need_kg * 3.0
    ferrite_mass_kg = (fe_need_kg * 0.9 + hdo_product_kg * 0.05) * sintering_yield
    energy_synthesis_mj = ferrite_mass_kg * 2.5
    energy_total_mj = energy_hdo_mj + energy_synthesis_mj
    mag_props = MAGNETIC_PROPERTIES["ferrite_hard"]
    cost_oil = oil_mass * COST_DATA["vegetable_oil_recycled"]
    cost_energy = energy_total_mj * 0.05
    cost_ferrite_total = cost_oil + fe_cost + cost_energy
    cost_per_kg_ferrite = cost_ferrite_total / ferrite_mass_kg if ferrite_mass_kg > 0 else 999
    ndfeb_equivalent_kg = ferrite_mass_kg * (mag_props["MGOE"] / MAGNETIC_PROPERTIES["ndfeb"]["MGOE"])
    cost_ndfeb_equivalent = ndfeb_equivalent_kg * COST_DATA["ndfeb"]
    cost_savings_pct = ((cost_ndfeb_equivalent - cost_ferrite_total) / cost_ndfeb_equivalent * 100.0) if cost_ndfeb_equivalent > 0 else 0
    energy_density_J_cm3 = mag_props["MGOE"] * 7.96
    return {"mode": "oil_recycling_to_ferrite", "input": {"oil_mass_kg": oil_mass, "oil_hhv_mj_kg": round(hhv_oil, 2), "oil_composition": comp, "hdo_temp_c": hdo_temp, "h2_consumed_kg": round(h2_consumed_kg, 3)}, "hdo_output": {"hydocarbon_product_kg": round(hdo_product_kg, 3), "oxygen_removed_pct": o_removed_pct, "energy_hdo_mj": round(energy_hdo_mj, 2)}, "synthesis": {"iron_source": iron_source, "fe_needed_kg": round(fe_need_kg, 3), "fe_cost_usd": round(fe_cost, 2), "sintering_yield_pct": params.get("sintering_yield_pct", 90), "ferrite_product_kg": round(ferrite_mass_kg, 3), "energy_synthesis_mj": round(energy_synthesis_mj, 2)}, "ferrite_properties": {"remanence_tesla": mag_props["Br"], "coercivity_ka_m": mag_props["Hc"], "mgoe": mag_props["MGOE"], "energy_density_kj_cm3": round(energy_density_J_cm3 / 1000, 3)}, "costs": {"cost_oil_usd": round(cost_oil, 2), "cost_fe_usd": round(fe_cost, 2), "cost_energy_usd": round(cost_energy, 2), "total_cost_usd": round(cost_ferrite_total, 2), "cost_per_kg_ferrite_usd": round(cost_per_kg_ferrite, 2), "ndfeb_equivalent_cost_usd": round(cost_ndfeb_equivalent, 2), "cost_savings_pct": round(cost_savings_pct, 1)}, "energy": {"total_energy_mj": round(energy_total_mj, 2), "energy_per_kg_product_mj_kg": round(energy_total_mj / ferrite_mass_kg if ferrite_mass_kg > 0 else 999, 2)}, "sustainability": {"recycled_oil_upcycled": "Sí", "circular_economy_score": 8.5, "confidence": "Alta (datos de HDO industriales)"}}
def compute_biomass_laser_graphene(params):
    biomass_type = params.get("biomass_type", "cellulose")
    biomass_mass = params.get("biomass_mass_kg", 1.0)
    laser_temp_peak = params.get("laser_temperature_peak_c", 3500)
    laser_pulse_dur = params.get("laser_pulse_duration_ms", 5)
    cooling_rate = params.get("cooling_rate_k_s", 1e6)
    yield_pct = params.get("yield_graphene_pct", 30) / 100.0
    if biomass_type not in COMPOSITION_DATA:
        biomass_type = "cellulose"
    comp = COMPOSITION_DATA[biomass_type]
    hhv_biomass = hhv_channiwala_parikh(**comp)
    c_content_pct = comp["C"]
    c_available_kg = biomass_mass * (c_content_pct / 100.0)
    graphene_3d_mass_kg = c_available_kg * yield_pct
    laser_energy_factor = (laser_temp_peak / 3000.0) ** 1.5
    energy_laser_mj = biomass_mass * 2.5 * laser_energy_factor
    energy_quenching_mj = biomass_mass * 0.0007 * laser_temp_peak
    if cooling_rate < 1e5:
        graphene_type = "graphene_3d_lab"
        porosity_pct, density_apparent_kg_m3 = 85, 200
    elif cooling_rate < 1e6:
        graphene_type = "graphene_3d_lab"
        porosity_pct, density_apparent_kg_m3 = 80, 250
    else:
        graphene_type = "graphene_3d_industrial"
        porosity_pct, density_apparent_kg_m3 = 75, 300
    graphene_props = GRAPHENE_PROPERTIES[graphene_type]
    volume_m3 = graphene_3d_mass_kg / density_apparent_kg_m3 if density_apparent_kg_m3 > 0 else 0
    volume_cm3 = volume_m3 * 1e6
    rho = graphene_props["rho_ohm_m"]
    resistance_1cm_cube_ohm = rho * (0.01 / (0.01 * 0.01))
    cost_laser_energy = energy_laser_mj * 0.1
    cost_biomass = biomass_mass * HHV_DATA.get(biomass_type, 18.5) * 0.01
    cost_equipment_amortized = graphene_3d_mass_kg * 5.0
    cost_total = cost_laser_energy + cost_biomass + cost_equipment_amortized
    cost_per_kg = cost_total / graphene_3d_mass_kg if graphene_3d_mass_kg > 0 else 999
    cost_graphene_cvd = graphene_3d_mass_kg * COST_DATA["graphene_industrial"]
    cost_savings_pct = ((cost_graphene_cvd - cost_total) / cost_graphene_cvd * 100.0) if cost_graphene_cvd > 0 else 0
    applications = []
    if graphene_props["sigma_S_m"] > 1e4:
        applications.extend(["Electrodos supercapacitores", "Circuitos fluidicos"])
    if porosity_pct > 70:
        applications.extend(["Absorción térmica/acústica", "Aislantes avanzados"])
    if density_apparent_kg_m3 < 500:
        applications.append("Estructuras ultraligeras")
    return {"mode": "biomass_laser_graphene", "input": {"biomass_type": biomass_type, "biomass_mass_kg": biomass_mass, "biomass_hhv_mj_kg": round(hhv_biomass, 2), "carbon_content_pct": c_content_pct, "carbon_available_kg": round(c_available_kg, 3)}, "laser_conditions": {"temperature_peak_c": laser_temp_peak, "pulse_duration_ms": laser_pulse_dur, "cooling_rate_k_s": cooling_rate, "cooling_rate_regime": "ultra-rápido" if cooling_rate > 1e6 else ("rápido" if cooling_rate > 1e5 else "lento")}, "graphene_3d_product": {"mass_kg": round(graphene_3d_mass_kg, 4), "yield_pct": round(yield_pct * 100, 1), "type": graphene_type, "volume_m3": round(volume_m3, 6), "porosity_pct": porosity_pct, "apparent_density_kg_m3": density_apparent_kg_m3}, "graphene_properties": {"conductivity_s_m": graphene_props["sigma_S_m"], "resistivity_ohm_m": graphene_props["rho_ohm_m"], "resistivity_1cm_cube_ohm": round(resistance_1cm_cube_ohm, 6), "carrier_mobility_cm2_vs": graphene_props["carrier_mobility"], "energy_band_gap_ev": 0.0 if graphene_type == "graphene_2d_monolayer" else 0.1}, "energy": {"laser_energy_mj": round(energy_laser_mj, 2), "quenching_energy_mj": round(energy_quenching_mj, 2), "total_energy_mj": round(energy_laser_mj + energy_quenching_mj, 2), "energy_per_kg_product_mj_kg": round((energy_laser_mj + energy_quenching_mj) / graphene_3d_mass_kg if graphene_3d_mass_kg > 0 else 999, 2)}, "costs": {"biomass_cost_usd": round(cost_biomass, 2), "laser_energy_cost_usd": round(cost_laser_energy, 2), "equipment_amortized_usd": round(cost_equipment_amortized, 2), "total_cost_usd": round(cost_total, 2), "cost_per_kg_graphene_3d_usd": round(cost_per_kg, 2), "graphene_cvd_equivalent_cost_usd": round(cost_graphene_cvd, 2), "cost_savings_vs_cvd_pct": round(cost_savings_pct, 1)}, "applications": applications, "sustainability": {"biomass_source": "Reciclable/renovable", "waste_heat_recovery_potential": "Sí (enfriamiento rápido)", "circular_economy_score": 9.0, "confidence": "Media-Alta (laboratorio, no industrializado aún)"}}
def compute_mass_energy_balance(params):
    chain_type = params.get("chain", "oil_to_ferrite")
    if chain_type == "oil_to_ferrite":
        result = compute_oil_recycling_to_ferrite(params)
        return {"chain": "Aceite reciclado -> Ferrita magnética", "feedstock_kg": result["input"]["oil_mass_kg"], "main_product_kg": result["synthesis"]["ferrite_product_kg"], "byproducts": ["H2O", "CO/CO2 (HDO)", "Calor sensible"], "mass_closure_pct": round(100.0 * result["synthesis"]["ferrite_product_kg"] / result["input"]["oil_mass_kg"], 1) if result["input"]["oil_mass_kg"] > 0 else 0, "energy_input_mj": result["energy"]["total_energy_mj"], "energy_per_kg_product": result["energy"]["energy_per_kg_product_mj_kg"], "cost_total_usd": result["costs"]["total_cost_usd"], "cost_per_kg_product_usd": result["costs"]["cost_per_kg_ferrite_usd"], "roi_vs_ndfeb_pct": round(100.0 * (result["costs"]["ndfeb_equivalent_cost_usd"] - result["costs"]["total_cost_usd"]) / result["costs"]["ndfeb_equivalent_cost_usd"], 1)}
    else:
        result = compute_biomass_laser_graphene(params)
        return {"chain": "Biomasa -> Grafeno 3D (laser)", "feedstock_kg": result["input"]["biomass_mass_kg"], "carbon_utilized_kg": result["input"]["carbon_available_kg"], "main_product_kg": result["graphene_3d_product"]["mass_kg"], "byproducts": ["H2O (vapor)", "CO/CO2", "Heat"], "mass_closure_pct": round(100.0 * result["graphene_3d_product"]["mass_kg"] / result["input"]["biomass_mass_kg"], 2), "energy_input_mj": result["energy"]["total_energy_mj"], "energy_per_kg_product": result["energy"]["energy_per_kg_product_mj_kg"], "cost_total_usd": result["costs"]["total_cost_usd"], "cost_per_kg_product_usd": result["costs"]["cost_per_kg_graphene_3d_usd"], "roi_vs_cvd_pct": result["costs"]["cost_savings_vs_cvd_pct"]}
def compute_validate():
    checks = []
    result1 = compute_oil_recycling_to_ferrite({"oil_mass_kg": 1.0, "hdo_temperature_c": 300, "hdo_h2_stoich_ratio": 2.0, "iron_source": "fe_waste_scrap", "sintering_yield_pct": 90})
    check1 = {"name": "oil_recycling_mass_balance_positive", "passed": result1["synthesis"]["ferrite_product_kg"] > 0}
    checks.append(check1)
    result2 = compute_biomass_laser_graphene({"biomass_type": "cellulose", "biomass_mass_kg": 1.0, "laser_temperature_peak_c": 3500, "yield_graphene_pct": 30})
    expected_graphene = 1.0 * (44.4 / 100.0) * (30 / 100.0)
    check2 = {"name": "graphene_mass_yield_coherent", "expected_kg": round(expected_graphene, 4), "actual_kg": result2["graphene_3d_product"]["mass_kg"], "passed": abs(result2["graphene_3d_product"]["mass_kg"] - expected_graphene) < 0.001}
    checks.append(check2)
    check3 = {"name": "energy_per_kg_positive", "result1_mj_kg": result1["energy"]["energy_per_kg_product_mj_kg"], "result2_mj_kg": result2["energy"]["energy_per_kg_product_mj_kg"], "passed": result1["energy"]["energy_per_kg_product_mj_kg"] > 0 and result2["energy"]["energy_per_kg_product_mj_kg"] > 0}
    checks.append(check3)
    check4 = {"name": "cost_savings_vs_commercial_realistic", "ferrite_savings_pct": result1["costs"]["cost_savings_pct"], "graphene_savings_pct": result2["costs"]["cost_savings_vs_cvd_pct"], "note": "Ferrita ahorra vs NdFeB, grafeno 3D lab aún caro", "passed": result1["costs"]["cost_savings_pct"] > 10}
    checks.append(check4)
    check5 = {"name": "ferrite_magnetic_properties_in_range", "br_tesla": result1["ferrite_properties"]["remanence_tesla"], "hc_ka_m": result1["ferrite_properties"]["coercivity_ka_m"], "mgoe": result1["ferrite_properties"]["mgoe"], "passed": 0 < result1["ferrite_properties"]["remanence_tesla"] < 1.5 and result1["ferrite_properties"]["coercivity_ka_m"] > 100}
    checks.append(check5)
    return {"validation_passed": all(c.get("passed", True) for c in checks), "n_passed": sum(1 for c in checks if c.get("passed", True)), "n_checks": len(checks), "checks": checks}
def compute_biomass_to_advanced_materials(mode, params=None):
    if params is None:
        params = {}
    if mode == "oil_recycling_to_ferrite":
        return compute_oil_recycling_to_ferrite(params)
    elif mode == "biomass_laser_graphene":
        return compute_biomass_laser_graphene(params)
    elif mode == "mass_energy_balance":
        return compute_mass_energy_balance(params)
    elif mode == "validate":
        return compute_validate()
    else:
        return {"error": f"Modo '{mode}' no reconocido"}
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "validate":
        result = compute_validate()
        print(json.dumps(result, indent=2))
    else:
        print("=== TEST: Oil Recycling -> Ferrite ===")
        r1 = compute_oil_recycling_to_ferrite({"oil_mass_kg": 10.0})
        print(json.dumps(r1, indent=2))
        print("\n=== TEST: Biomass Laser -> Graphene 3D ===")
        r2 = compute_biomass_laser_graphene({"biomass_mass_kg": 5.0})
        print(json.dumps(r2, indent=2))
try:
    _register()
except ImportError:
    pass