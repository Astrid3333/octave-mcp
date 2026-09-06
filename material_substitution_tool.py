"""
material_substitution_tool.py
Comparacion cuantitativa de sustitutos de materiales para dos casos de uso:
conductores electricos (cobre/aluminio/plata/grafeno de laboratorio) e imanes
permanentes (NdFeB/SmCo/ferrita/alnico/Fe16N2 de laboratorio), usando formulas
cerradas de ingenieria electrica y de circuitos magneticos.

No existe "material matematicamente superior" en abstracto -- solo trade-offs
medibles (masa, costo, disponibilidad de tierras raras) para un uso especifico
dado. Esta tool cuantifica esos trade-offs, no declara ganadores.
"""

import math

MATERIAL_SUBSTITUTION_TOOL_SCHEMA = {
    "name": "material_substitution_tool",
    "description": "Comparacion cuantitativa de sustitutos de materiales conductores e imanes permanentes",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["compare_conductors", "compare_magnets", "validate"]},
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}

# Constantes fisicas de referencia (valores tipicos de ingenieria, orden de
# magnitud correcto pero no certificados para diseno de produccion real).
CONDUCTOR_DB = {
    "copper": {
        "resistivity_ohm_m": 1.68e-8, "density_kg_m3": 8960, "price_usd_kg": 9.0,
        "note": "referencia estandar industrial",
    },
    "aluminum": {
        "resistivity_ohm_m": 2.82e-8, "density_kg_m3": 2700, "price_usd_kg": 2.5,
        "note": "ya reemplaza cobre en lineas de alta tension por menor masa a igual resistencia",
    },
    "silver": {
        "resistivity_ohm_m": 1.59e-8, "density_kg_m3": 10490, "price_usd_kg": 800.0,
        "note": "mejor conductor metalico puro, inviable por costo salvo usos de nicho",
    },
    "graphene_lab": {
        "resistivity_ohm_m": 1e-8, "density_kg_m3": 2267, "price_usd_kg": None,
        "note": "resistividad de mejor caso reportado en laminas monocristalinas de laboratorio; "
                "NO representa cable macroscopico fabricable hoy, confidence baja",
    },
}

MAGNET_DB = {
    "ndfeb": {
        "bhmax_kj_m3": 400, "density_kg_m3": 7500,
        "note": "mayor densidad de energia comercial, contiene tierras raras (Nd + a veces Dy/Tb)",
    },
    "smco": {
        "bhmax_kj_m3": 240, "density_kg_m3": 8400,
        "note": "sin Nd pero sigue usando tierras raras (Sm), mejor estabilidad termica que NdFeB",
    },
    "alnico": {
        "bhmax_kj_m3": 40, "density_kg_m3": 7300,
        "note": "sin tierras raras, buena estabilidad termica, muy baja coercitividad",
    },
    "ferrite": {
        "bhmax_kj_m3": 35, "density_kg_m3": 5000,
        "note": "sin tierras raras, barato y abundante, la sustitucion mas madura hoy",
    },
    "fe16n2_lab": {
        "bhmax_kj_m3": 450, "density_kg_m3": 7200,
        "note": "proyeccion teorica de mejor caso en investigacion de laboratorio, "
                "NO estabilizado a escala industrial, confidence baja",
    },
}


def _compare_conductors(length_m, resistance_target_ohm, materials=None):
    materials = materials or ["copper", "aluminum", "silver"]
    if length_m <= 0 or resistance_target_ohm <= 0:
        raise ValueError("length_m y resistance_target_ohm deben ser > 0")

    results = {}
    for mat in materials:
        if mat not in CONDUCTOR_DB:
            raise ValueError(f"material desconocido: {mat}")
        props = CONDUCTOR_DB[mat]
        rho = props["resistivity_ohm_m"]
        area_m2 = rho * length_m / resistance_target_ohm
        volume_m3 = area_m2 * length_m
        mass_kg = volume_m3 * props["density_kg_m3"]
        cost_usd = mass_kg * props["price_usd_kg"] if props["price_usd_kg"] is not None else None
        results[mat] = {
            "cross_section_area_m2": area_m2,
            "mass_kg": mass_kg,
            "cost_usd": cost_usd,
            "note": props["note"],
        }

    reference = materials[0]
    ref_mass = results[reference]["mass_kg"]
    for mat in results:
        results[mat][f"mass_ratio_vs_{reference}"] = results[mat]["mass_kg"] / ref_mass

    return {
        "mode": "compare_conductors",
        "length_m": length_m,
        "resistance_target_ohm": resistance_target_ohm,
        "reference_material": reference,
        "materials_compared": results,
        "confidence_flag": "alta para metales industriales, baja para graphene_lab",
        "note": "Formula cerrada R=rho*L/A. Compara masa/costo para IGUAL resistencia electrica "
                "e igual longitud -- no hay 'material superior' universal, solo el trade-off mas "
                "conveniente para un uso dado.",
    }


def _compare_magnets(reference_mass_kg, reference_material="ndfeb", materials=None):
    materials = materials or ["ndfeb", "smco", "ferrite", "alnico", "fe16n2_lab"]
    if reference_mass_kg <= 0:
        raise ValueError("reference_mass_kg debe ser > 0")
    if reference_material not in MAGNET_DB:
        raise ValueError(f"reference_material desconocido: {reference_material}")

    ref_props = MAGNET_DB[reference_material]
    ref_volume_m3 = reference_mass_kg / ref_props["density_kg_m3"]
    ref_energy = ref_volume_m3 * ref_props["bhmax_kj_m3"]

    results = {}
    for mat in materials:
        if mat not in MAGNET_DB:
            raise ValueError(f"material desconocido: {mat}")
        props = MAGNET_DB[mat]
        volume_needed_m3 = ref_energy / props["bhmax_kj_m3"]
        mass_needed_kg = volume_needed_m3 * props["density_kg_m3"]
        results[mat] = {
            "volume_needed_m3": volume_needed_m3,
            "mass_needed_kg": mass_needed_kg,
            "mass_ratio_vs_reference": mass_needed_kg / reference_mass_kg,
            "uses_rare_earths": mat in ("ndfeb", "smco"),
            "note": props["note"],
        }

    return {
        "mode": "compare_magnets",
        "reference_material": reference_material,
        "reference_mass_kg": reference_mass_kg,
        "materials_compared": results,
        "confidence_flag": "alta para materiales comerciales, baja para fe16n2_lab (proyeccion de investigacion)",
        "note": "Masa necesaria para igualar la energia magnetica (BHmax*volumen) del material de "
                "referencia. No modela geometria real del circuito magnetico ni temperatura de operacion.",
    }


def _validate():
    checks = []

    r1 = _compare_conductors(length_m=100, resistance_target_ohm=0.1, materials=["copper", "aluminum"])
    checks.append({
        "name": "conductor_self_ratio_is_one",
        "passed": abs(r1["materials_compared"]["copper"]["mass_ratio_vs_copper"] - 1.0) < 1e-9,
    })
    checks.append({
        "name": "aluminum_lighter_than_copper_same_resistance",
        "passed": r1["materials_compared"]["aluminum"]["mass_kg"] < r1["materials_compared"]["copper"]["mass_kg"],
    })

    r2 = _compare_conductors(length_m=100, resistance_target_ohm=0.2, materials=["copper"])
    ratio = r1["materials_compared"]["copper"]["mass_kg"] / r2["materials_compared"]["copper"]["mass_kg"]
    checks.append({
        "name": "mass_scales_inversely_with_resistance_target",
        "passed": abs(ratio - 2.0) < 1e-9,
    })

    m1 = _compare_magnets(reference_mass_kg=1.0, reference_material="ndfeb", materials=["ndfeb", "ferrite"])
    checks.append({
        "name": "magnet_self_ratio_is_one",
        "passed": abs(m1["materials_compared"]["ndfeb"]["mass_ratio_vs_reference"] - 1.0) < 1e-9,
    })
    checks.append({
        "name": "ferrite_needs_much_more_mass_than_ndfeb",
        "passed": m1["materials_compared"]["ferrite"]["mass_ratio_vs_reference"] > 5.0,
    })

    try:
        _compare_conductors(length_m=1, resistance_target_ohm=1, materials=["unobtainium"])
        rejects_unknown = False
    except ValueError:
        rejects_unknown = True
    checks.append({"name": "rejects_unknown_material", "passed": rejects_unknown})

    n_passed = sum(1 for c in checks if c["passed"])
    return {
        "validation_passed": n_passed == len(checks),
        "n_passed": n_passed,
        "n_checks": len(checks),
        "checks": checks,
    }


def compute_material_substitution_tool(mode, **kwargs):
    if mode == "validate":
        return _validate()
    if mode == "compare_conductors":
        return _compare_conductors(
            length_m=kwargs["length_m"],
            resistance_target_ohm=kwargs["resistance_target_ohm"],
            materials=kwargs.get("materials"),
        )
    if mode == "compare_magnets":
        return _compare_magnets(
            reference_mass_kg=kwargs["reference_mass_kg"],
            reference_material=kwargs.get("reference_material", "ndfeb"),
            materials=kwargs.get("materials"),
        )
    raise ValueError(f"modo desconocido: {mode}")


def _register():
    try:
        import tool_registry
        tool_registry.register_tool(
            "material_substitution_tool",
            MATERIAL_SUBSTITUTION_TOOL_SCHEMA,
            lambda args: compute_material_substitution_tool(
                args.get("mode"), **(args.get("params") or {})
            ),
        )
    except ImportError:
        pass


_register()

if __name__ == "__main__":
    import json
    result = _validate()
    print(json.dumps(
        {"validation_passed": result["validation_passed"],
         "n_passed": result["n_passed"], "n_checks": result["n_checks"]},
        indent=2,
    ))
