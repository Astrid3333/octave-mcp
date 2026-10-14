"""
materials_db_tool.py

Base de datos de materiales de ingeniería: comunes (acero, hormigón,
madera, aluminio, cobre, vidrio, plásticos) e innovadores (CFRP, GFRP,
UHPC, ECC, SMA NiTi, hormigón auto-sanable, aerogel, aleaciones de alta
entropía, MXene, grafeno reforzado). Unidades SI (Pa, kg/m³, W/m·K).

Modos:
  lookup     — propiedades de un material por nombre o id.
  compare    — comparación lado a lado de 2+ materiales (misma categoría
               o cross-category).
  search     — filtrar por rango de propiedades (E, fy, ρ, λ, etc.).
  innovate   — sugerir materiales innovadores para un caso de uso con
               trade-offs (masa, coste, TRL, límites).

Fuentes: EN 1990/1992/1993/1995, EN 1990s (aluminio AA), datasheets
típicos, literatura de materiales avanzados (valores representativos,
no certificados para diseño de producción — verificar con datasheet
del proveedor).
"""

from tool_registry import register_tool

MATERIALS_DB_TOOL_SCHEMA = {
    "name": "materials_db_tool",
    "description": (
        "Base de datos de materiales comunes e innovadores en SI (Newton). "
        "lookup (propiedades), compare (lado a lado), search (filtro por "
        "rango), innovate (sugerencias con trade-offs TRL/coste/masa). "
        "Acero S235-S460, hormigón C25-C80, madera C14-D40, aluminio, "
        "CFRP/GFRP, UHPC, ECC, SMA, aerogel, aleaciones alta entropía."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["lookup", "compare", "search", "innovate"],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}

# ---------------------------------------------------------------------------
# Base de datos: materiales comunes
# ---------------------------------------------------------------------------
# E en Pa, fy/fu en Pa, rho en kg/m3, lambda (conductividad) en W/mK,
# alpha (dilatación) en 1/K, cp en J/kgK, coste relativo (1 = referencia
# acero estructural), TRL (1-9), note.

COMMON_DB = {
    # --- ACERO (EN 1993-1-1 Tabla 3.1) ---
    "S235": {"cat": "steel", "E": 210e9, "fy": 235e6, "fu": 360e6, "rho": 7850,
             "lambda": 50.0, "alpha": 12e-6, "cp": 440, "nu": 0.30, "cost_rel": 1.0,
             "TRL": 9, "note": "Acero estructural común, lámina/plegado"},
    "S275": {"cat": "steel", "E": 210e9, "fy": 275e6, "fu": 430e6, "rho": 7850,
             "lambda": 50.0, "alpha": 12e-6, "cp": 440, "nu": 0.30, "cost_rel": 1.05,
             "TRL": 9, "note": "Acero estructural común"},
    "S355": {"cat": "steel", "E": 210e9, "fy": 355e6, "fu": 510e6, "rho": 7850,
             "lambda": 50.0, "alpha": 12e-6, "cp": 440, "nu": 0.30, "cost_rel": 1.10,
             "TRL": 9, "note": "Acero estructural estándar puentes"},
    "S460": {"cat": "steel", "E": 210e9, "fy": 460e6, "fu": 540e6, "rho": 7850,
             "lambda": 50.0, "alpha": 12e-6, "cp": 440, "nu": 0.30, "cost_rel": 1.30,
             "TRL": 9, "note": "Acero alta resistencia, puentes largos"},
    "AISI_4140": {"cat": "steel", "E": 210e9, "fy": 655e6, "fu": 1020e6, "rho": 7850,
                  "lambda": 42.0, "alpha": 12e-6, "cp": 440, "nu": 0.30, "cost_rel": 1.8,
                  "TRL": 9, "note": "Acero aleado para ejes, engranajes"},
    "stainless_304": {"cat": "steel", "E": 193e9, "fy": 215e6, "fu": 505e6, "rho": 8000,
                      "lambda": 16.0, "alpha": 17e-6, "cp": 500, "nu": 0.29, "cost_rel": 4.0,
                      "TRL": 9, "note": "Inoxidable austenítico, corrosión"},

    # --- HORMIGÓN (EN 1992-1-1 Tabla 3.1) ---
    "C25/30": {"cat": "concrete", "fck_MPa": 25, "E_cm_GPa": 31, "rho": 2400,
               "lambda": 1.9, "alpha": 10e-6, "cp": 880, "cost_rel": 1.0,
               "TRL": 9, "note": "Hormigón estructural común"},
    "C30/37": {"cat": "concrete", "fck_MPa": 30, "E_cm_GPa": 33, "rho": 2400,
               "lambda": 1.9, "alpha": 10e-6, "cp": 880, "cost_rel": 1.05,
               "TRL": 9, "note": "Hormigón estructural estándar"},
    "C35/45": {"cat": "concrete", "fck_MPa": 35, "E_cm_GPa": 34, "rho": 2400,
               "lambda": 1.9, "alpha": 10e-6, "cp": 880, "cost_rel": 1.10,
               "TRL": 9, "note": "Hormigón puentes"},
    "C50/60": {"cat": "concrete", "fck_MPa": 50, "E_cm_GPa": 38, "rho": 2450,
               "lambda": 2.0, "alpha": 10e-6, "cp": 880, "cost_rel": 1.30,
               "TRL": 9, "note": "Hormigón alta resistencia"},
    "C60/75": {"cat": "concrete", "fck_MPa": 60, "E_cm_GPa": 41, "rho": 2500,
               "lambda": 2.1, "alpha": 10e-6, "cp": 880, "cost_rel": 1.50,
               "TRL": 9, "note": "Hormigón muy alta resistencia"},
    "lightweight_C30": {"cat": "concrete", "fck_MPa": 30, "E_cm_GPa": 20, "rho": 1800,
                        "lambda": 1.0, "alpha": 8e-6, "cp": 1000, "cost_rel": 1.4,
                        "TRL": 9, "note": "Hormigón ligero (arcilla/pumicita)"},

    # --- MADERA (EN 1995 Tabla 3.2) ---
    "C24": {"cat": "timber", "f_mk_MPa": 24, "E0_mean_GPa": 10.8, "rho": 440,
            "lambda": 0.12, "alpha": 5e-6, "cp": 1600, "cost_rel": 0.8,
            "TRL": 9, "note": "Madera maciza structural común"},
    "C30": {"cat": "timber", "f_mk_MPa": 30, "E0_mean_GPa": 12.4, "rho": 490,
            "lambda": 0.13, "alpha": 5e-6, "cp": 1600, "cost_rel": 0.9,
            "TRL": 9, "note": "Madera maciza clase 30"},
    "GL28h": {"cat": "timber", "f_mk_MPa": 28, "E0_mean_GPa": 12.6, "rho": 390,
              "lambda": 0.12, "alpha": 5e-6, "cp": 1600, "cost_rel": 1.2,
              "TRL": 9, "note": "Madera laminada encolada (glulam)"},
    "CLT_C24": {"cat": "timber", "f_mk_MPa": 24, "E0_mean_GPa": 10.8, "rho": 470,
                "lambda": 0.13, "alpha": 5e-6, "cp": 1600, "cost_rel": 1.5,
                "TRL": 9, "note": "Madera laminada cruzada (CLT) paneles"},

    # --- ALUMINIO (EN 1999-1-1) ---
    "ENAW_6061_T6": {"cat": "aluminum", "E": 69e9, "fy": 240e6, "fu": 290e6,
                     "rho": 2700, "lambda": 167.0, "alpha": 23e-6, "cp": 896,
                     "nu": 0.33, "cost_rel": 3.0, "TRL": 9,
                     "note": "Aluminio estructural, soldable T6"},
    "ENAW_6082_T6": {"cat": "aluminum", "E": 70e9, "fy": 260e6, "fu": 310e6,
                     "rho": 2700, "lambda": 180.0, "alpha": 23e-6, "cp": 896,
                     "nu": 0.33, "cost_rel": 3.2, "TRL": 9,
                     "note": "Aluminio puentes, perfiles extruidos"},
    "ENAW_5083": {"cat": "aluminum", "E": 71e9, "fy": 125e6, "fu": 275e6,
                  "rho": 2660, "lambda": 120.0, "alpha": 24e-6, "cp": 900,
                  "nu": 0.33, "cost_rel": 2.8, "TRL": 9,
                  "note": "Aluminio marítimo, resistencia corrosión"},

    # --- COBRE / OTROS METALES ---
    "copper": {"cat": "metal", "E": 110e9, "fy": 70e6, "fu": 220e6, "rho": 8960,
               "lambda": 400.0, "alpha": 17e-6, "cp": 385, "nu": 0.34,
               "cost_rel": 8.0, "TRL": 9, "note": "Conductor eléctrico, anti-corrosión"},
    "titanium_Gr2": {"cat": "metal", "E": 105e9, "fy": 275e6, "fu": 345e6, "rho": 4510,
                     "lambda": 16.0, "alpha": 8.6e-6, "cp": 520, "nu": 0.34,
                     "cost_rel": 25.0, "TRL": 9,
                     "note": "Ti puro, biocompatible, corrosión extremo"},

    # --- VIDRIO / CERÁMICA ---
    "glass_float": {"cat": "ceramic", "E": 70e9, "fu": 40e6, "rho": 2500,
                    "lambda": 1.0, "alpha": 9e-6, "cp": 840, "nu": 0.22,
                    "cost_rel": 0.5, "TRL": 9,
                    "note": "Vidrio flotado, frágil, alta compresión"},
    "alumina_96": {"cat": "ceramic", "E": 300e9, "fu_compression": 2000e6,
                   "rho": 3800, "lambda": 25.0, "alpha": 7e-6, "cp": 880,
                   "nu": 0.21, "cost_rel": 15.0, "TRL": 9,
                   "note": "Alúmina técnica, desgaste, alta T"},

    # --- PLÁSTICOS / POLÍMEROS ---
    "ABS": {"cat": "polymer", "E": 2.3e9, "fy": 40e6, "fu": 43e6, "rho": 1040,
            "lambda": 0.17, "alpha": 90e-6, "cp": 1400, "nu": 0.35,
            "cost_rel": 1.5, "TRL": 9, "note": "Ingeniería termoplástico común"},
    "PEEK": {"cat": "polymer", "E": 3.6e9, "fy": 100e6, "fu": 100e6, "rho": 1320,
             "lambda": 0.25, "alpha": 47e-6, "cp": 1300, "nu": 0.40,
             "cost_rel": 40.0, "TRL": 9,
             "note": "Polímero alto rendimiento, biocompatible, alta T"},
    "nylon_PA6": {"cat": "polymer", "E": 3.0e9, "fy": 80e6, "fu": 85e6, "rho": 1130,
                  "lambda": 0.25, "alpha": 80e-6, "cp": 1700, "nu": 0.39,
                  "cost_rel": 2.5, "TRL": 9, "note": "Poliamida, engrenajes, fibras"},
}

# ---------------------------------------------------------------------------
# Base de datos: materiales de innovación
# ---------------------------------------------------------------------------
INNOVATION_DB = {
    # --- COMPOSITOS DE FIBRA ---
    "CFRP_T700": {"cat": "composite_fiber", "E1_GPa": 135, "E2_GPa": 10,
                  "G12_GPa": 5.0, "rho": 1600, "X_t_MPa": 2100, "X_c_MPa": 1200,
                  "lambda": 8.0, "TRL": 9, "cost_rel": 50.0,
                  "note": "CFRP unidireccional T700, aeronáutico, puentes refuerzo"},
    "CFRP_T800": {"cat": "composite_fiber", "E1_GPa": 155, "E2_GPa": 10,
                  "G12_GPa": 5.5, "rho": 1600, "X_t_MPa": 2550, "X_c_MPa": 1400,
                  "lambda": 8.0, "TRL": 8, "cost_rel": 80.0,
                  "note": "CFRP T800 alta resistencia, prensado alto"},
    "GFRP_E": {"cat": "composite_fiber", "E1_GPa": 45, "E2_GPa": 12,
               "G12_GPa": 5.5, "rho": 1900, "X_t_MPa": 1000, "X_c_MPa": 600,
               "lambda": 0.3, "TRL": 9, "cost_rel": 8.0,
               "note": "GFRP Epoxi, barras armadura corrosión-free"},
    "basalt_fiber": {"cat": "composite_fiber", "E1_GPa": 89, "E2_GPa": 15,
                     "G12_GPa": 15, "rho": 1900, "X_t_MPa": 2100, "X_c_MPa": 1200,
                     "lambda": 0.04, "TRL": 7, "cost_rel": 25.0,
                     "note": "Fibra de basalto, alternativa CFRP más barata"},

    # --- HORMIGONES AVANZADOS ---
    "UHPC": {"cat": "concrete_advanced", "fck_MPa": 150, "fcm_MPa": 200,
             "E_cm_GPa": 55, "rho": 2500, "f_ct_MPa": 9.0, "lambda": 2.5,
             "TRL": 8, "cost_rel": 8.0,
             "note": "Ultra-hormigón de alto desempeño, fibras, puentes prefabricados"},
    "ECC": {"cat": "concrete_advanced", "fck_MPa": 40, "f_cm_MPa": 50,
            "E_cm_GPa": 22, "rho": 2100, "f_ct_MPa": 6.0, "strain_flexure": 0.05,
            "lambda": 1.5, "TRL": 6, "cost_rel": 10.0,
            "note": "Composite cementicio ductil (ECC), pseudodúctil, auto-fisuras"},
    "self_healing": {"cat": "concrete_advanced", "fck_MPa": 35, "E_cm_GPa": 34,
                     "rho": 2400, "lambda": 1.9, "healing_efficiency": 0.8,
                     "TRL": 5, "cost_rel": 4.0,
                     "note": "Hormigón auto-sanable (bacterias/capsulas), reduce mantenimiento"},
    "geopolymer": {"cat": "concrete_advanced", "fck_MPa": 40, "E_cm_GPa": 30,
                   "rho": 2350, "lambda": 1.8, "CO2_reduction": 0.6,
                   "TRL": 7, "cost_rel": 1.5,
                   "note": "Hormigón geopolimérico, bajo CO2 (escoria/laterita)"},

    # --- ALEACIONES DE SHAPE MEMORY ---
    "NiTi": {"cat": "smart_metal", "E_a_GPa": 75, "E_m_GPa": 30, "rho": 6450,
             "Af_C": 40, "recoverable_strain": 0.06, "sigma_MPa": 500,
             "lambda": 8.0, "TRL": 7, "cost_rel": 200.0,
             "note": "NiTi SMA, memoria de forma, superelástico, actuadores"},
    "NiTiHf": {"cat": "smart_metal", "E_a_GPa": 80, "rho": 6800, "Af_C": 150,
               "recoverable_strain": 0.04, "TRL": 5, "cost_rel": 400.0,
               "note": "NiTiHf SMA alta temperatura (>150°C)"},
    "CuAlNi": {"cat": "smart_metal", "E_a_GPa": 70, "rho": 7200, "Af_C": 150,
               "recoverable_strain": 0.04, "TRL": 5, "cost_rel": 80.0,
               "note": "SMA Cu-Al-Ni, más barato que NiTi, menos cíclico"},

    # --- ALEACIONES DE ALTA ENTROPÍA (HEA) ---
    "CoCrFeMnNi": {"cat": "HEA", "E_GPa": 200, "fy_MPa": 450, "fu_MPa": 900,
                   "rho": 8000, "ductility": 0.6, "lambda": 12.0,
                   "TRL": 4, "cost_rel": 100.0,
                   "note": "Cantor alloy (CoCrFeMnNi), alta ductilidad, criogénico"},
    "AlCoCrFeNi": {"cat": "HEA", "E_GPa": 180, "fy_MPa": 500, "fu_MPa": 1000,
                   "rho": 7300, "TRL": 4, "cost_rel": 120.0,
                   "note": "HEA ligera AlCoCrFeNi, precipitación endurecida"},

    # --- AEROGEL Y AISLANTES NANO ---
    "silica_aerogel": {"cat": "insulator", "E_MPa": 1.0, "rho": 150,
                       "lambda": 0.015, "T_max_C": 650, "TRL": 8,
                       "cost_rel": 50.0,
                       "note": "Aerogel de sílice, λ récord, frágil"},
    "aerogel_blanket": {"cat": "insulator", "rho": 200, "lambda": 0.016,
                        "T_max_C": 650, "TRL": 8, "cost_rel": 30.0,
                        "note": "Manta aerogel flexible, retrofit aislamiento"},

    # --- GRAFENO Y 2D ---
    "graphene_sheet": {"cat": "nano_2d", "E_TPa": 1.0, "strength_MPa": 130000,
                       "rho": 2267, "lambda": 5000, "thickness_nm": 0.335,
                       "TRL": 3, "cost_rel": 10000.0,
                       "note": "Grafeno monoláxido, propiedades récord lab, escalabilidad limitada"},
    "graphene_bulk": {"cat": "nano_2d", "E_GPa": 100, "rho": 1500, "lambda": 5.0,
                      "TRL": 5, "cost_rel": 200.0,
                      "note": "Compuesto grafeno-matriz, propiedades efectivas mucho menores"},
    "MXene_Ti3C2": {"cat": "nano_2d", "E_GPa": 330, "strength_MPa": 22000,
                    "rho": 2400, "conductivity_SM_m": 10000, "TRL": 3,
                    "cost_rel": 500.0,
                    "note": "MXene Ti3C2Tx, conductor 2D, EMI shielding, supercond."},

    # --- FIBRAS NATURALES / BIO ---
   "hemp_fiber": {"cat": "bio_fiber", "E_GPa": 35, "strength_MPa": 550,
                  "rho": 1400, "TRL": 7, "cost_rel": 2.0,
                  "note": "Fibra de cáñamo, refuerzo bio, baja huella carbono"},
    "flax_fiber": {"cat": "bio_fiber", "E_GPa": 50, "strength_MPa": 800,
                   "rho": 1500, "TRL": 7, "cost_rel": 3.0,
                   "note": "Fibra de lino, mejor E que cáñamo, composites auto"},

    # --- OTROS INNOVADORES ---
    "translucent_concrete": {"cat": "smart", "E_GPa": 30, "rho": 2100,
                             "light_transmission": 0.2, "TRL": 6, "cost_rel": 15.0,
                             "note": "Hormigón translúcido (fibra óptica), fachadas"},
    "phase_change_material": {"cat": "smart", "latent_heat_kJ_kg": 200,
                              "melt_C": 23, "rho": 880, "TRL": 7, "cost_rel": 10.0,
                              "note": "PCM (parafina/salicilato), almacenamiento térmico edificio"},
    "piezoelectric_PZT": {"cat": "smart", "d33_pC_N": 400, "E_GPa": 60,
                          "rho": 7800, "TRL": 8, "cost_rel": 50.0,
                          "note": "Cerámica piezoeléctrica PZT, sensores/actuadores, energy harvesting"},
}


def _lookup(params):
    name = params.get("name") or params.get("material")
    if not name:
        return {"error": "necesita 'name' o 'material'"}
    # Búsqueda case-insensitive: comparar minúsculas
    key = name.lower().replace(" ", "_").replace("-", "_")
    for db, cat in ((COMMON_DB, "common"), (INNOVATION_DB, "innovation")):
        for k, m in db.items():
            if k.lower().replace(" ", "_").replace("-", "_") == key:
                return {"name": k, "category": cat, "properties": m}
    # Búsqueda parcial (substring)
    matches = []
    for db, cat in ((COMMON_DB, "common"), (INNOVATION_DB, "innovation")):
        for k in db:
            kk = k.lower().replace(" ", "_").replace("-", "_")
            if key in kk or kk in key:
                matches.append({"name": k, "category": cat})
    return {"error": f"'{name}' no encontrado", "suggestions": matches[:10]}


def _compare(params):
    names = params.get("names") or params.get("materials") or []
    if len(names) < 2:
        return {"error": "necesita al menos 2 'names'"}
    out = []
    for name in names:
        r = _lookup({"name": name})
        if "properties" in r:
            out.append({"name": r["name"], "category": r["category"],
                        **r["properties"]})
        else:
            out.append({"name": name, "error": "not found"})
    return {"materials": out, "n": len(out)}


def _search(params):
    cat = params.get("category")
    E_min = params.get("E_min")  # Pa
    E_max = params.get("E_max")
    fy_min = params.get("fy_min")
    rho_max = params.get("rho_max")
    lambda_max = params.get("lambda_max")  # conductividad
    TRL_min = params.get("TRL_min")
    cost_max = params.get("cost_max")
    results = []
    for db, dbcat in ((COMMON_DB, "common"), (INNOVATION_DB, "innovation")):
        for k, m in db.items():
            if cat and m.get("cat") != cat and not (dbcat == cat or cat in k):
                continue
            # Filtros numéricos
            E = m.get("E", m.get("E1_GPa", m.get("E_cm_GPa", m.get("E_a_GPa", m.get("E_TPa", m.get("E_MPa", None))))))
            if E_min and E is not None:
                E_pa = E * (1e12 if E < 1e3 and "TPa" in str(m.get("E_TPa", "")) else
                            1e9 if E < 1e5 else 1e6 if E < 1e8 else 1)
                # Normalizar: si valor es en GPa (chico), convertir
                if E < 1e4:  # está en GPa o similar
                    E_pa = E * 1e9
                if E_pa < E_min:
                    continue
            if E_max and E is not None:
                E_pa = E * 1e9 if E < 1e4 else E
                if E_pa > E_max:
                    continue
            fy = m.get("fy", m.get("fy_MPa", m.get("fck_MPa", m.get("f_mk_MPa", None))))
            if fy_min and fy is not None:
                fy_pa = fy * 1e6 if fy < 1e4 else fy
                if fy_pa < fy_min:
                    continue
            if rho_max and m.get("rho") and m["rho"] > rho_max:
                continue
            lam = m.get("lambda")
            if lambda_max and lam is not None and lam > lambda_max:
                continue
            if TRL_min and m.get("TRL", 0) < TRL_min:
                continue
            if cost_max and m.get("cost_rel", 999) > cost_max:
                continue
            results.append({"name": k, "category": dbcat, **m})
    return {"results": results, "n": len(results)}


def _innovate(params):
    use_case = params.get("use_case", "").lower()
    # Mapeo caso de uso → materiales innovadores sugeridos
    suggestions = {
        "corrosion": {
            "why": "Para entornos corrosivos (marino, químico):",
            "materials": ["GFRP_E", "basalt_fiber", "stainless_304", "CFRP_T700"],
            "tradeoff": "GFRP: 1/6 peso acero, E~1/4.7, sin corrosión, coste 8×.",
        },
        "seismic": {
            "why": "Para disipación sismo/aislamiento:",
            "materials": ["NiTi", "CuAlNi", "ECC", "phase_change_material"],
            "tradeoff": "NiTi: 6% deformación recuperable, TRL 7, coste 200×. ECC: pseudodúctil 5% strain.",
        },
        "lightweight": {
            "why": "Para minimizar masa (aero, movilidad):",
            "materials": ["CFRP_T700", "GFRP_E", "basalt_fiber", "graphene_bulk",
                          "hemp_fiber", "flax_fiber"],
            "tradeoff": "CFRP: ρ=1600 (−80% vs acero), E1=135GPa (−36%), coste 50×. Bio: barato, ρ~1400.",
        },
        "thermal_insulation": {
            "why": "Para aislamiento térmico extremo:",
            "materials": ["silica_aerogel", "aerogel_blanket", "phase_change_material"],
            "tradeoff": "Aerogel: λ=0.015 W/mK (récord), frágil, coste 50×. PCM: almacena 200kJ/kg.",
        },
        "high_temperature": {
            "why": "Para servicio >500°C:",
            "materials": ["alumina_96", "NiTiHf", "CoCrFeMnNi", "silica_aerogel"],
            "tradeoff": "Alúmina: T>1500°C, frágil. NiTiHf: SMA hasta 150°C. HEA: microestructura estable.",
        },
        "low_carbon": {
            "why": "Para reducir huella de carbono:",
            "materials": ["geopolymer", "hemp_fiber", "flax_fiber", "self_healing"],
            "tradeoff": "Geopolimérico: −60% CO2 vs Portland. Cáñamo: fija CO2. Self-healing: menos reparaciones.",
        },
        "sensors_actuators": {
            "why": "Para estructuras inteligentes (SHM):",
            "materials": ["piezoelectric_PZT", "NiTi", "graphene_bulk", "phase_change_material"],
            "tradeoff": "PZT: d33=400pC/N, frágil. NiTi: actuación por temperatura. Grafeno: sensor strain ultrasensible.",
        },
    }
    if use_case in suggestions:
        s = suggestions[use_case]
        mats = []
        for name in s["materials"]:
            r = _lookup({"name": name})
            if "properties" in r:
                mats.append({"name": name, **r["properties"]})
            else:
                mats.append({"name": name})
        return {
            "use_case": use_case, "why": s["why"],
            "suggested": mats, "tradeoff": s["tradeoff"],
            "available_cases": list(suggestions.keys()),
        }
    return {"error": f"use_case '{use_case}' no reconocido",
            "available_cases": list(suggestions.keys())}


def _handler(args):
    mode = args.get("mode")
    params = args.get("params") or {}
    try:
        if mode == "lookup":
            return _lookup(params)
        elif mode == "compare":
            return _compare(params)
        elif mode == "search":
            return _search(params)
        elif mode == "innovate":
            return _innovate(params)
        else:
            return {"error": f"mode desconocido: {mode}"}
    except (KeyError, ValueError, TypeError) as e:
        return {"error": f"parámetros inválidos: {e}"}


register_tool(
    name="materials_db_tool",
    schema=MATERIALS_DB_TOOL_SCHEMA,
    handler=lambda args: _handler(args),
)
