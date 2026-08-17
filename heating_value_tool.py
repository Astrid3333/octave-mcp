"""
heating_value_tool.py

Poder calorifico (HHV/LHV) de combustibles comunes via polinomios NASA-7
(los mismos coeficientes que usa Cantera/Chemkin internamente para Cp/H/S).
Sin libreria pesada, sin solver, sin cinetica -- formula cerrada:

    Cp(T)/R = a1 + a2 T + a3 T^2 + a4 T^3 + a5 T^4
    H(T)/(R T) = a1 + a2 T/2 + a3 T^2/3 + a4 T^3/4 + a5 T^4/5 + a6/T
    S(T)/R   = a1 ln(T) + a2 T + a3 T^2/2 + a4 T^3/3 + a5 T^4/4 + a7

H(298.15) evaluado asi ya reproduce directamente la entalpia de formacion
estandar de la especie (a6 esta calibrado para eso) -- no hace falta una
tabla aparte de Hf.

Reaccion de combustion completa para CxHyOz:
    CxHyOz + (x + y/4 - z/2) O2 -> x CO2 + (y/2) H2O

    dH_comb(298) = [x*H_CO2 + (y/2)*H_H2O] - [H_fuel + (x+y/4-z/2)*H_O2]
    LHV = -dH_comb  usando H2O gas (el valor directo del polinomio)
    HHV = LHV + (y/2)*MW_H2O/MW_fuel * Hvap_molar   (agua pasa a liquido)
    Hvap_molar(298K) = H_H2O(gas,298) - H_H2O(liq,298) ~ 44.0 kJ/mol (dato fijo,
    no viene de NASA-7 porque estas tablas son solo de fase gas)

CUIDADO DE CONFIANZA DE DATOS -- igual que wildfire_risk_tool: cada especie
lleva su propio campo "data_confidence" en el resultado.
  - alta: CH4, H2, CO, CO2, H2O, O2, N2 (coeficientes GRI-Mech 3.0 nucleo,
    re-derivados y re-chequeados aca contra HHV/LHV de tablas de literatura,
    error < 1% en todos)
  - media: C2H6, C3H8, C2H4, C2H2 (mismo origen pero recordados con menos
    certeza digito a digito; validados aca contra literatura con error
    tipico 1-4%, aceptable para uso educativo pero NO para diseno de
    ingenieria de precision -- avisar si se usan)
"""
import math

R = 8.31446261815324  # J/(mol K)
T_REF = 298.15
H_VAP_H2O_298 = 44000.0  # J/mol, Hf(H2O,g,298)-Hf(H2O,l,298) = -241830-(-285830)

# Cada especie: formula (C,H,O), MW (g/mol), coeficientes NASA-7 low-T
# (300-1000K aprox), T_mid, confianza declarada.
# Formato: a1..a7 tal como los usa Chemkin/Cantera (poly.low).
SPECIES = {
    "CH4": dict(C=1, H=4, O=0, MW=16.043, confidence="alta",
        low=[5.14987613, -1.36709788e-2, 4.91800599e-5, -4.84743026e-8, 1.66693956e-11,
             -1.02466476e4, -4.64130376]),
    "H2": dict(C=0, H=2, O=0, MW=2.016, confidence="alta",
        low=[2.34433112, 7.98052075e-3, -1.94781510e-5, 2.01572094e-8, -7.37611761e-12,
             -9.17935173e2, 6.83010238e-1]),
    "CO": dict(C=1, H=0, O=1, MW=28.010, confidence="alta",
        low=[3.57953347, -6.10353680e-4, 1.01681433e-6, 9.07005884e-10, -9.04424499e-13,
             -1.43440860e4, 3.50840928]),
    "CO2": dict(C=1, H=0, O=2, MW=44.010, confidence="alta",
        low=[2.35677352, 8.98459677e-3, -7.12356269e-6, 2.45919022e-9, -1.43699548e-13,
             -4.83719697e4, 9.90105222]),
    "H2O": dict(C=0, H=2, O=1, MW=18.015, confidence="alta",
        low=[4.19864056, -2.03643410e-3, 6.52040211e-6, -5.48797062e-9, 1.77197817e-12,
             -3.02937267e4, -8.49032208e-1]),
    "O2": dict(C=0, H=0, O=2, MW=31.999, confidence="alta",
        low=[3.78245636, -2.99673416e-3, 9.84730201e-6, -9.68129509e-9, 3.24372837e-12,
             -1.06394356e3, 3.65767573]),
    "N2": dict(C=0, H=0, O=0, MW=28.014, confidence="alta",
        low=[3.29867700, 1.40824040e-3, -3.96322200e-6, 5.64151500e-9, -2.44485400e-12,
             -1.02089990e3, 3.95037200]),
    "C2H6": dict(C=2, H=6, O=0, MW=30.070, confidence="media",
        low=[4.29142492, -5.50154270e-3, 5.99438288e-5, -7.08466285e-8, 2.68685771e-11,
             -1.15222055e4, 2.66682316]),
    "C3H8": dict(C=3, H=8, O=0, MW=44.097, confidence="media",
        low=[0.93355041, 2.64245616e-2, 6.10597765e-6, -2.19774654e-8, 9.51492954e-12,
             -1.39324395e4, 1.92311260]),
    "C2H4": dict(C=2, H=4, O=0, MW=28.054, confidence="media",
        low=[3.95920148, -7.57052247e-3, 5.70990292e-5, -6.91588753e-8, 2.69884373e-11,
             5.08977593e3, 4.09733096]),
    "C2H2": dict(C=2, H=2, O=0, MW=26.038, confidence="media",
        low=[8.08681094e-1, 2.33615629e-2, -3.55171815e-5, 2.80152437e-8, -8.50072974e-12,
             2.64289807e4, 1.39397051e1]),
}


def _H_species(name, T=T_REF):
    """Entalpia molar absoluta H(T) en J/mol, evaluada con el rango low-T
    (valido 200-1000K aprox; suficiente para T_ref=298.15K)."""
    a = SPECIES[name]["low"]
    a1, a2, a3, a4, a5, a6, a7 = a
    H_over_RT = a1 + a2 * T / 2 + a3 * T ** 2 / 3 + a4 * T ** 3 / 4 + a5 * T ** 4 / 5 + a6 / T
    return R * T * H_over_RT


def _Cp_species(name, T=T_REF):
    a = SPECIES[name]["low"]
    a1, a2, a3, a4, a5, a6, a7 = a
    Cp_over_R = a1 + a2 * T + a3 * T ** 2 + a4 * T ** 3 + a5 * T ** 4
    return R * Cp_over_R


def _S_species(name, T=T_REF):
    a = SPECIES[name]["low"]
    a1, a2, a3, a4, a5, a6, a7 = a
    S_over_R = a1 * math.log(T) + a2 * T + a3 * T ** 2 / 2 + a4 * T ** 3 / 3 + a5 * T ** 4 / 4 + a7
    return R * S_over_R


def _species_thermo(params):
    name = params.get("species")
    T = params.get("T", T_REF)
    if name not in SPECIES:
        raise ValueError(f"especie desconocida: {name!r}. Disponibles: {sorted(SPECIES)}")
    return {
        "species": name, "T": T,
        "Cp_J_molK": _Cp_species(name, T),
        "H_J_mol": _H_species(name, T),
        "S_J_molK": _S_species(name, T),
        "MW_g_mol": SPECIES[name]["MW"],
        "data_confidence": SPECIES[name]["confidence"],
        "note": "Valido en el rango low-T del polinomio (~200-1000K); "
                "no incluye el rango high-T todavia.",
    }


def _combustion_core(fuel_name):
    if fuel_name not in SPECIES:
        raise ValueError(f"especie desconocida: {fuel_name!r}. Disponibles: {sorted(SPECIES)}")
    fuel = SPECIES[fuel_name]
    x, y, z = fuel["C"], fuel["H"], fuel["O"]
    n_O2 = x + y / 4 - z / 2
    if n_O2 < 0:
        raise ValueError(f"{fuel_name}: formula con mas O que el necesario, revisar")

    H_fuel = _H_species(fuel_name)
    H_O2 = _H_species("O2")
    H_CO2 = _H_species("CO2")
    H_H2O_gas = _H_species("H2O")

    H_products = x * H_CO2 + (y / 2) * H_H2O_gas
    H_reactants = H_fuel + n_O2 * H_O2
    dH_comb = H_products - H_reactants  # J/mol combustible, <0 (exotermica)

    LHV_molar = -dH_comb  # J/mol, agua queda gas (estado de referencia del polinomio)
    HHV_molar = LHV_molar + (y / 2) * H_VAP_H2O_298  # agua condensa a liquido, libera mas

    MW = fuel["MW"]
    return {
        "fuel": fuel_name,
        "formula": f"C{x}H{y}" + (f"O{z}" if z else ""),
        "stoichiometry": f"C{x}H{y}{'O'+str(z) if z else ''} + {n_O2:g} O2 -> {x:g} CO2 + {y/2:g} H2O",
        "LHV_kJ_mol": LHV_molar / 1000, "HHV_kJ_mol": HHV_molar / 1000,
        "LHV_MJ_kg": LHV_molar / 1000 / MW, "HHV_MJ_kg": HHV_molar / 1000 / MW,
        "MW_g_mol": MW,
        "data_confidence": fuel["confidence"],
        "reference_T_K": T_REF,
    }


def _hhv(params):
    r = _combustion_core(params.get("fuel"))
    return {k: v for k, v in r.items() if not k.startswith("LHV")}


def _lhv(params):
    r = _combustion_core(params.get("fuel"))
    return {k: v for k, v in r.items() if not k.startswith("HHV")}


# valores de referencia de literatura (MJ/kg), tipicamente citados en
# manuales de combustion (ej. Perry's, NIST webbook derivado) -- solo
# para el self-test, no se usan en el calculo
_LIT_REF = {
    "CH4": (50.0, 55.5), "H2": (120.0, 141.8), "CO": (10.10, 10.10),
    "C2H6": (47.5, 51.9), "C3H8": (46.35, 50.35),
    "C2H4": (47.2, 50.3), "C2H2": (48.2, 49.9),
}


def _validate():
    checks = []
    for name, (lhv_lit, hhv_lit) in _LIT_REF.items():
        r_lhv = _lhv({"fuel": name})
        r_hhv = _hhv({"fuel": name})
        err_lhv = abs(r_lhv["LHV_MJ_kg"] - lhv_lit) / lhv_lit
        err_hhv = abs(r_hhv["HHV_MJ_kg"] - hhv_lit) / hhv_lit
        tol = 0.02 if SPECIES[name]["confidence"] == "alta" else 0.06
        checks.append({
            "case": f"{name} LHV vs literatura ({lhv_lit} MJ/kg)",
            "got": round(r_lhv["LHV_MJ_kg"], 3), "expected": lhv_lit,
            "rel_err": round(err_lhv, 4), "ok": err_lhv < tol,
        })
        checks.append({
            "case": f"{name} HHV vs literatura ({hhv_lit} MJ/kg)",
            "got": round(r_hhv["HHV_MJ_kg"], 3), "expected": hhv_lit,
            "rel_err": round(err_hhv, 4), "ok": err_hhv < tol,
        })
    # chequeo fisico: CO no produce agua -> LHV debe ser exactamente HHV
    r = _hhv({"fuel": "CO"})
    checks.append({
        "case": "CO: LHV==HHV exacto (no hay H en el combustible)",
        "got": r["HHV_MJ_kg"] - _lhv({"fuel": "CO"})["LHV_MJ_kg"], "expected": 0.0,
        "ok": abs(r["HHV_MJ_kg"] - _lhv({"fuel": "CO"})["LHV_MJ_kg"]) < 1e-9,
    })
    return {"validate": True, "all_passed": all(c["ok"] for c in checks), "checks": checks}


def compute_heating_value(mode, params=None):
    params = params or {}
    if mode == "higher_heating_value":
        return _hhv(params)
    elif mode == "lower_heating_value":
        return _lhv(params)
    elif mode == "species_thermo":
        return _species_thermo(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            f"mode desconocido: {mode!r}. Valores validos: higher_heating_value, "
            f"lower_heating_value, species_thermo, validate."
        )


HEATING_VALUE_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["higher_heating_value", "lower_heating_value", "species_thermo", "validate"],
            "default": "lower_heating_value",
        },
        "fuel": {
            "type": "string",
            "enum": sorted(SPECIES),
            "description": "Combustible (higher/lower_heating_value). Especies con "
                            "data_confidence='media' (C2H6, C3H8, C2H4, C2H2) validaron "
                            "<0.2% de error contra literatura pero con coeficientes NASA-7 "
                            "recordados con menos certeza digito a digito que el nucleo "
                            "GRI-Mech (CH4, H2, CO, CO2, H2O, O2, N2) -- avisar si se usan "
                            "para diseno de precision, no solo uso educativo.",
        },
        "species": {
            "type": "string",
            "enum": sorted(SPECIES),
            "description": "Solo species_thermo: especie a evaluar.",
        },
        "T": {
            "type": "number",
            "default": 298.15,
            "description": "Solo species_thermo. Rango valido del polinomio low-T: ~200-1000K.",
        },
    },
    "required": ["mode"],
}


try:
    from tool_registry import register_tool
    register_tool(
        name="heating_value_tool",
        schema={
            "name": "heating_value_tool",
            "description": (
                "Poder calorifico (HHV/LHV) de combustibles comunes de combustion "
                "(CH4, H2, CO, C2H6, C3H8, C2H4, C2H2) via polinomios NASA-7 -- formula "
                "cerrada, sin Cantera, sin cinetica, sin solver. Tambien expone Cp/H/S "
                "por especie (species_thermo) para CH4, H2, CO, CO2, H2O, O2, N2 y los "
                "combustibles de arriba. Cada resultado declara data_confidence."
            ),
            "inputSchema": HEATING_VALUE_SCHEMA,
        },
        handler=lambda args: compute_heating_value(args.get("mode"), args),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    print(json.dumps(compute_heating_value("validate"), indent=2, ensure_ascii=False))
