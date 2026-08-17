"""
battery_sizing_tool.py

Dimensionamiento de sistemas de bateria para energia renovable aislada
(off-grid) o respaldo -- formula cerrada, balance de energia, sin solver.

Fisica/ingenieria (referencias estandar de diseno de sistemas fotovoltaicos
aislados, ej. Sandia PV design handbooks, practica de ingenieria off-grid --
formulas de dominio publico re-derivadas aca):

  Balance de energia para autonomia (dias sin generacion):
    Capacidad_util_kWh = Carga_diaria_kWh * dias_autonomia
    Capacidad_nominal_kWh = Capacidad_util_kWh / (DoD * eta_bateria * eta_inversor)
    Capacidad_nominal_Ah = Capacidad_nominal_kWh * 1000 / V_sistema

  Dimensionamiento de arreglo PV para cubrir la carga diaria (metodo de
  horas de sol pico, HSP -- estandar de diseno off-grid):
    Potencia_pv_kW = Carga_diaria_kWh / (HSP * eta_sistema)
    donde eta_sistema agrupa perdidas de cableado, suciedad, temperatura,
    MPPT, inversor (tipico 0.75-0.90 combinado)

  Vida util en ciclos vs profundidad de descarga (modelo empirico tipo
  ley de potencia, ajustado a curvas de datasheet de fabricantes --
  MUY variable segun quimica, ver data_confidence):
    N_ciclos(DoD) = N_ref * (DoD_ref/DoD)^alpha
    Vida_anios = N_ciclos(DoD) / ciclos_por_anio

  Dimensionamiento de controlador de carga (regla NEC 690.8, factor de
  seguridad estandar de la industria):
    I_controlador = 1.25 * 1.25 * Isc_stc_array  (125% x 125%: uno por
    irradiancia sobre STC en dias frios/reflectivos, otro por seguridad
    de continuidad de la NEC)

CUIDADO DE CONFIANZA DE DATOS:
  - balance de energia (capacidad, autonomia, sizing PV por HSP): alta --
    formula cerrada estandar de ingenieria, sin parametros empiricos de
    fabricante mas alla de eficiencias declaradas por el usuario.
  - ciclo de vida vs DoD: media/baja -- el exponente alpha y N_ref son
    ajustes empiricos que varian fuertemente por quimica y fabricante
    (plomo-acido vs LiFePO4 vs NMC difieren en mas de 10x en vida a DoD
    profundo). Los valores default aca son ordenes de magnitud tipicos de
    literatura, NO reemplazan la curva del datasheet real del fabricante
    elegido -- avisar siempre si se usan para diseno final.
"""
import math

# Ordenes de magnitud tipicos de literatura para N_ref, DoD_ref, alpha por
# quimica (ver nota de confianza arriba -- estos son puntos de partida
# educativos, no specs de fabricante).
BATTERY_CHEMISTRY = {
    "lead_acid_flooded": dict(N_ref=1200, DoD_ref=0.50, alpha=1.5, confidence="baja",
        note="plomo-acido inundada, ciclado profundo reduce vida fuertemente (alpha alto)"),
    "lead_acid_agm": dict(N_ref=1500, DoD_ref=0.50, alpha=1.3, confidence="baja",
        note="plomo-acido AGM, algo mas tolerante a ciclado profundo que inundada"),
    "lifepo4": dict(N_ref=4000, DoD_ref=0.80, alpha=0.6, confidence="media",
        note="litio LiFePO4, tolera DoD profundo bastante mejor que plomo-acido"),
    "nmc": dict(N_ref=2000, DoD_ref=0.80, alpha=0.8, confidence="media",
        note="litio NMC, mayor densidad energetica pero vida algo menor que LFP a igual DoD"),
}


def _battery_capacity(params):
    daily_load = params.get("daily_load_kWh")
    autonomy = params.get("autonomy_days")
    dod = params.get("dod")
    eta_batt = params.get("eta_battery", 0.95)
    eta_inv = params.get("eta_inverter", 0.95)
    v_sys = params.get("system_voltage_V")
    if daily_load is None or autonomy is None or dod is None:
        raise ValueError("battery_capacity requiere daily_load_kWh, autonomy_days, dod")
    if not (0 < dod <= 1):
        raise ValueError("dod debe estar en (0, 1]")

    usable_kwh = daily_load * autonomy
    nominal_kwh = usable_kwh / (dod * eta_batt * eta_inv)
    result = {
        "daily_load_kWh": daily_load, "autonomy_days": autonomy, "dod": dod,
        "eta_battery": eta_batt, "eta_inverter": eta_inv,
        "usable_capacity_kWh": round(usable_kwh, 3),
        "nominal_capacity_kWh": round(nominal_kwh, 3),
    }
    if v_sys:
        result["system_voltage_V"] = v_sys
        result["nominal_capacity_Ah"] = round(nominal_kwh * 1000 / v_sys, 2)
    return result


def _pv_array_sizing(params):
    daily_load = params.get("daily_load_kWh")
    psh = params.get("peak_sun_hours")
    eta_sys = params.get("eta_system", 0.80)
    if daily_load is None or psh is None:
        raise ValueError("pv_array_sizing requiere daily_load_kWh y peak_sun_hours")
    if psh <= 0:
        raise ValueError("peak_sun_hours debe ser > 0")
    p_pv_kw = daily_load / (psh * eta_sys)
    return {
        "daily_load_kWh": daily_load, "peak_sun_hours": psh, "eta_system": eta_sys,
        "pv_array_power_kW": round(p_pv_kw, 4),
        "note": "eta_system agrupa cableado+suciedad+temperatura+MPPT+inversor; "
                "tipico 0.75-0.90 combinado, default 0.80.",
    }


def _cycle_life(params):
    chem = params.get("chemistry")
    dod = params.get("dod")
    cycles_per_year = params.get("cycles_per_year", 365)
    if chem is None or dod is None:
        raise ValueError("cycle_life_estimate requiere chemistry y dod")
    if chem not in BATTERY_CHEMISTRY:
        raise ValueError(f"chemistry desconocida: {chem!r}. Disponibles: {sorted(BATTERY_CHEMISTRY)}")
    if not (0 < dod <= 1):
        raise ValueError("dod debe estar en (0, 1]")
    c = BATTERY_CHEMISTRY[chem]
    n_cycles = c["N_ref"] * (c["DoD_ref"] / dod) ** c["alpha"]
    life_years = n_cycles / cycles_per_year
    return {
        "chemistry": chem, "dod": dod, "cycles_per_year": cycles_per_year,
        "estimated_cycles": round(n_cycles, 0),
        "estimated_life_years": round(life_years, 2),
        "reference_point": {"N_ref_cycles": c["N_ref"], "DoD_ref": c["DoD_ref"], "alpha": c["alpha"]},
        "data_confidence": c["confidence"],
        "note": c["note"] + ". Modelo ley de potencia calibrado a un punto de "
                "referencia -- verificar siempre contra la curva de ciclado del "
                "datasheet del fabricante especifico antes de un diseno final.",
    }


def _charge_controller_sizing(params):
    isc = params.get("array_isc_A")
    if isc is None:
        raise ValueError("charge_controller_sizing requiere array_isc_A")
    safety_irradiance = params.get("safety_factor_irradiance", 1.25)
    safety_nec = params.get("safety_factor_continuous", 1.25)
    i_controller = isc * safety_irradiance * safety_nec
    return {
        "array_isc_A": isc,
        "safety_factor_irradiance": safety_irradiance,
        "safety_factor_continuous": safety_nec,
        "min_controller_current_A": round(i_controller, 2),
        "note": "Regla estandar de la industria (NEC 690.8 estilo): 125% por "
                "irradiancia sobre STC en dias frios/reflectivos, x 125% adicional "
                "por seguridad de operacion continua.",
    }


def _energy_balance_mode(params):
    """Balance simple: dado consumo diario, generacion PV diaria estimada
    (potencia_pv * HSP * eta_sistema) y capacidad de bateria, calcula el
    excedente/deficit diario y cuantos dias de autonomia real cubre la
    bateria instalada frente al consumo dado."""
    daily_load = params.get("daily_load_kWh")
    pv_power_kw = params.get("pv_array_power_kW")
    psh = params.get("peak_sun_hours")
    eta_sys = params.get("eta_system", 0.80)
    battery_kwh = params.get("battery_nominal_capacity_kWh")
    dod = params.get("dod", 0.5)
    eta_batt = params.get("eta_battery", 0.95)
    eta_inv = params.get("eta_inverter", 0.95)
    if None in (daily_load, pv_power_kw, psh, battery_kwh):
        raise ValueError("energy_balance requiere daily_load_kWh, pv_array_power_kW, "
                          "peak_sun_hours, battery_nominal_capacity_kWh")
    daily_gen = pv_power_kw * psh * eta_sys
    surplus = daily_gen - daily_load
    usable_battery = battery_kwh * dod * eta_batt * eta_inv
    autonomy_covered_days = usable_battery / daily_load if daily_load > 0 else float("inf")
    return {
        "daily_load_kWh": daily_load, "daily_generation_kWh": round(daily_gen, 3),
        "daily_surplus_kWh": round(surplus, 3),
        "usable_battery_kWh": round(usable_battery, 3),
        "autonomy_covered_days": round(autonomy_covered_days, 2),
        "balance_status": "superavit" if surplus >= 0 else "deficit",
    }


def _validate():
    checks = []

    # 1) Consistencia: battery_capacity con eta=1 y dod=1 -> nominal == usable
    r1 = _battery_capacity({"daily_load_kWh": 10.0, "autonomy_days": 2, "dod": 1.0,
                              "eta_battery": 1.0, "eta_inverter": 1.0})
    checks.append({"case": "dod=1, eta=1: capacidad nominal == capacidad util (20 kWh)",
                    "got": r1["nominal_capacity_kWh"], "expected": 20.0,
                    "ok": abs(r1["nominal_capacity_kWh"] - 20.0) < 1e-9})

    # 2) Menor DoD (mas conservador) requiere mas capacidad nominal para la
    # misma autonomia util -- monotonicidad fisica
    r_dod_low = _battery_capacity({"daily_load_kWh": 10.0, "autonomy_days": 2, "dod": 0.3})
    r_dod_high = _battery_capacity({"daily_load_kWh": 10.0, "autonomy_days": 2, "dod": 0.9})
    checks.append({"case": "menor DoD => mayor capacidad nominal requerida (misma carga/autonomia)",
                    "got": r_dod_low["nominal_capacity_kWh"], "expected_greater_than": r_dod_high["nominal_capacity_kWh"],
                    "ok": r_dod_low["nominal_capacity_kWh"] > r_dod_high["nominal_capacity_kWh"]})

    # 3) Ah = kWh*1000/V, chequeo aritmetico directo
    r3 = _battery_capacity({"daily_load_kWh": 5.0, "autonomy_days": 3, "dod": 0.5,
                              "eta_battery": 0.9, "eta_inverter": 0.9, "system_voltage_V": 48})
    expected_ah = r3["nominal_capacity_kWh"] * 1000 / 48
    checks.append({"case": "conversion kWh->Ah consistente con V_sistema",
                    "got": r3["nominal_capacity_Ah"], "expected": round(expected_ah, 2),
                    "ok": abs(r3["nominal_capacity_Ah"] - expected_ah) < 0.01})

    # 4) PV sizing: mas horas de sol pico (mismo consumo) => menor potencia PV requerida
    r4a = _pv_array_sizing({"daily_load_kWh": 10.0, "peak_sun_hours": 3.0})
    r4b = _pv_array_sizing({"daily_load_kWh": 10.0, "peak_sun_hours": 6.0})
    checks.append({"case": "mas HSP => menor potencia PV requerida (mismo consumo)",
                    "got": r4b["pv_array_power_kW"], "expected_less_than": r4a["pv_array_power_kW"],
                    "ok": r4b["pv_array_power_kW"] < r4a["pv_array_power_kW"]})
    # chequeo aritmetico directo del caso simple eta=1
    r4c = _pv_array_sizing({"daily_load_kWh": 12.0, "peak_sun_hours": 4.0, "eta_system": 1.0})
    checks.append({"case": "PV sizing aritmetica directa (eta=1): 12kWh/4HSP=3kW",
                    "got": r4c["pv_array_power_kW"], "expected": 3.0, "ok": abs(r4c["pv_array_power_kW"] - 3.0) < 1e-9})

    # 5) Cycle life: DoD menor => mas ciclos de vida estimados (monotonicidad,
    # todas las quimicas de la tabla siguen alpha>0)
    for chem in BATTERY_CHEMISTRY:
        r_shallow = _cycle_life({"chemistry": chem, "dod": 0.2})
        r_deep = _cycle_life({"chemistry": chem, "dod": 0.8})
        checks.append({"case": f"{chem}: DoD bajo (0.2) da mas ciclos que DoD profundo (0.8)",
                        "got": r_shallow["estimated_cycles"], "expected_greater_than": r_deep["estimated_cycles"],
                        "ok": r_shallow["estimated_cycles"] > r_deep["estimated_cycles"]})

    # 6) Cycle life: en DoD == DoD_ref, ciclos == N_ref exacto (por construccion
    # de la formula de ley de potencia)
    for chem, c in BATTERY_CHEMISTRY.items():
        r_ref = _cycle_life({"chemistry": chem, "dod": c["DoD_ref"]})
        checks.append({"case": f"{chem}: en DoD==DoD_ref, ciclos==N_ref exacto",
                        "got": r_ref["estimated_cycles"], "expected": float(c["N_ref"]),
                        "ok": abs(r_ref["estimated_cycles"] - c["N_ref"]) < 1.0})

    # 7) Charge controller: caso simple con factores 1.0 -> igual a Isc
    r7 = _charge_controller_sizing({"array_isc_A": 10.0, "safety_factor_irradiance": 1.0,
                                      "safety_factor_continuous": 1.0})
    checks.append({"case": "charge controller con factores=1.0 == Isc",
                    "got": r7["min_controller_current_A"], "expected": 10.0,
                    "ok": abs(r7["min_controller_current_A"] - 10.0) < 1e-9})
    # caso default NEC-style: 10A * 1.25 * 1.25 = 15.625A
    r7b = _charge_controller_sizing({"array_isc_A": 10.0})
    checks.append({"case": "charge controller default (1.25x1.25): 10A -> 15.625A",
                    "got": r7b["min_controller_current_A"], "expected": 15.625,
                    "ok": abs(r7b["min_controller_current_A"] - 15.625) < 0.01})

    # 8) Energy balance: generacion == consumo exacto -> surplus 0, status superavit
    # (por convencion >=0 es superavit)
    r8 = _energy_balance_mode({"daily_load_kWh": 10.0, "pv_array_power_kW": 2.5,
                                 "peak_sun_hours": 5.0, "eta_system": 0.8,
                                 "battery_nominal_capacity_kWh": 10.0})
    # daily_gen = 2.5*5*0.8=10.0 == daily_load=10.0
    checks.append({"case": "energy_balance: generacion==consumo -> surplus~0",
                    "got": r8["daily_surplus_kWh"], "expected": 0.0, "ok": abs(r8["daily_surplus_kWh"]) < 1e-9})
    checks.append({"case": "energy_balance: surplus>=0 clasifica como superavit",
                    "got": r8["balance_status"], "expected": "superavit", "ok": r8["balance_status"] == "superavit"})

    return {"validate": True, "all_passed": all(c["ok"] for c in checks), "checks": checks}


def compute_battery_sizing(mode, params=None):
    params = params or {}
    if mode == "battery_capacity":
        return _battery_capacity(params)
    elif mode == "pv_array_sizing":
        return _pv_array_sizing(params)
    elif mode == "cycle_life_estimate":
        return _cycle_life(params)
    elif mode == "charge_controller_sizing":
        return _charge_controller_sizing(params)
    elif mode == "energy_balance":
        return _energy_balance_mode(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            f"mode desconocido: {mode!r}. Valores validos: battery_capacity, "
            f"pv_array_sizing, cycle_life_estimate, charge_controller_sizing, "
            f"energy_balance, validate."
        )


BATTERY_SIZING_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["battery_capacity", "pv_array_sizing", "cycle_life_estimate",
                     "charge_controller_sizing", "energy_balance", "validate"],
            "default": "battery_capacity",
        },
        "daily_load_kWh": {"type": "number"},
        "autonomy_days": {"type": "number"},
        "dod": {"type": "number", "description": "Profundidad de descarga, 0-1."},
        "eta_battery": {"type": "number", "default": 0.95},
        "eta_inverter": {"type": "number", "default": 0.95},
        "system_voltage_V": {"type": "number", "description": "Opcional, para convertir a Ah."},
        "peak_sun_hours": {"type": "number", "description": "HSP del sitio, kWh/m2/dia numericamente."},
        "eta_system": {"type": "number", "default": 0.80, "description": "Eficiencia combinada del sistema PV."},
        "chemistry": {"type": "string", "enum": sorted(BATTERY_CHEMISTRY)},
        "cycles_per_year": {"type": "number", "default": 365},
        "array_isc_A": {"type": "number", "description": "Corriente de cortocircuito del arreglo PV en STC."},
        "safety_factor_irradiance": {"type": "number", "default": 1.25},
        "safety_factor_continuous": {"type": "number", "default": 1.25},
        "pv_array_power_kW": {"type": "number", "description": "Solo energy_balance."},
        "battery_nominal_capacity_kWh": {"type": "number", "description": "Solo energy_balance."},
    },
    "required": ["mode"],
}


try:
    from tool_registry import register_tool
    register_tool(
        name="battery_sizing_tool",
        schema={
            "name": "battery_sizing_tool",
            "description": (
                "Dimensionamiento de sistemas de bateria para energia renovable "
                "aislada: capacidad por autonomia (battery_capacity), potencia de "
                "arreglo PV por horas de sol pico (pv_array_sizing), estimacion de "
                "vida en ciclos vs profundidad de descarga por quimica "
                "(cycle_life_estimate: lead_acid_flooded, lead_acid_agm, lifepo4, nmc), "
                "dimensionamiento de controlador de carga (charge_controller_sizing) "
                "y balance diario generacion vs consumo (energy_balance). Formula "
                "cerrada, sin solver."
            ),
            "inputSchema": BATTERY_SIZING_TOOL_SCHEMA,
        },
        handler=lambda args: compute_battery_sizing(args.get("mode"), args),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    print(json.dumps(compute_battery_sizing("validate"), indent=2, ensure_ascii=False))
