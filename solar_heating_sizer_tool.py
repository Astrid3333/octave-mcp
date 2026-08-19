"""
solar_heating_sizer_tool.py

Puente entre solar_radiation_tool, battery_sizing_tool y carbon_footprint_tool
para dimensionar un sistema fotovoltaico de apoyo a calefaccion, usando
irradiancia real del peor dia del ano (no un peak-sun-hours generico) y
proyectando el CO2 evitado vs lena a lo largo de la vida util del sistema.

Filosofia de diseno (peor caso, no promedio):
- El dimensionamiento usa daily_energy_kWh_m2 del solar_radiation_tool para
  un dia especifico (por defecto, el solsticio de invierno del hemisferio
  correspondiente a la latitud) con climate="midlatitude_winter" por
  defecto, porque un sistema de calefaccion tiene que cubrir la demanda
  cuando MENOS sol hay, no en el promedio anual. Esto es intencional: un
  dimensionamiento con peak_sun_hours de verano subestimaria el arreglo
  necesario para calefaccion.
- kWh/m^2/dia es numericamente equivalente a "peak sun hours" (1 sun =
  1 kW/m^2), asi que daily_energy_kWh_m2 se pasa directo como
  peak_sun_hours a _pv_array_sizing sin conversion.
- La proyeccion de CO2 usa el modo annual_projection de carbon_footprint_tool
  con comparison="solar" y fv_degradation_pct_per_year, para reflejar que el
  ahorro atribuible decae con la degradacion del panel (ver bugfix del check
  16 en carbon_footprint_tool).
"""

from solar_radiation_tool import _daily_energy_kwh_m2, HOTTEL_CLIMATES
from battery_sizing_tool import _pv_array_sizing
from carbon_footprint_tool import _mode_annual_projection


def _default_worst_case_day(lat_deg):
    """Solsticio de invierno segun hemisferio: dia 172 (~21 jun) para
    latitudes sur (invierno austral), dia 355 (~21 dic) para latitudes
    norte. En el ecuador (lat=0) no hay solsticio marcado; se usa 172
    igual por convencion (resultado casi identico a 355 ahi)."""
    return 172 if lat_deg < 0 else 355


def _mode_size_system_for_heating(params):
    lat = params.get("latitude_deg")
    annual_energy = params.get("annual_energy_needed_kWh")
    if lat is None or annual_energy is None:
        raise ValueError(
            "size_system_for_heating requiere latitude_deg y annual_energy_needed_kWh"
        )

    n = params.get("day_of_year", _default_worst_case_day(lat))
    beta = params.get("beta_deg", abs(lat) + 15.0)
    gamma = params.get("gamma_deg", 0.0 if lat >= 0 else 180.0)
    altitude_km = params.get("altitude_km", 0.0)
    climate = params.get("climate", "midlatitude_winter")
    albedo = params.get("albedo", 0.2)
    eta_system = params.get("eta_system", 0.80)
    years = params.get("years", 20)
    fv_deg = params.get("fv_degradation_pct_per_year", 0.5)
    daily_load = params.get("daily_load_kWh", annual_energy / 365.0)

    daily_energy_kwh_m2 = _daily_energy_kwh_m2(
        lat, n, beta, gamma, altitude_km, climate, albedo
    )

    pv = _pv_array_sizing({
        "daily_load_kWh": daily_load,
        "peak_sun_hours": daily_energy_kwh_m2,
        "eta_system": eta_system,
    })

    carbon = _mode_annual_projection({
        "annual_energy_needed_kwh": annual_energy,
        "years": years,
        "comparison": "solar",
        "fv_degradation_pct_per_year": fv_deg,
    })

    return {
        "latitude_deg": lat, "day_of_year": n, "beta_deg": beta, "gamma_deg": gamma,
        "climate": climate,
        "worst_case_daily_energy_kWh_m2": round(daily_energy_kwh_m2, 4),
        "daily_load_kWh": round(daily_load, 4),
        "pv_array_power_kW": pv["pv_array_power_kW"],
        "eta_system": eta_system,
        "co2_projection_years": years,
        "co2_cumulative_savings_kg": carbon["cumulative_savings_kg"],
        "note": (
            "Dimensionado contra el peor dia (solsticio de invierno, "
            "climate='midlatitude_winter' por defecto), no el promedio anual. "
            "daily_load_kWh por defecto es annual_energy_needed_kWh/365; "
            "pasar daily_load_kWh explicito si la demanda de calefaccion "
            "esta concentrada en menos dias."
        ),
    }


def _validate():
    checks = []

    e_invierno = _daily_energy_kwh_m2(-42.0, 172, 30.0, 180.0, 0.0, "midlatitude_winter", 0.2)
    e_verano = _daily_energy_kwh_m2(-42.0, 355, 30.0, 180.0, 0.0, "midlatitude_summer", 0.2)
    checks.append({
        "name": "worst_case_winter_day_less_energy_than_summer",
        "invierno_kWh_m2": e_invierno, "verano_kWh_m2": e_verano,
        "passed": bool(e_invierno < e_verano),
    })

    r = _mode_size_system_for_heating({
        "latitude_deg": -42.0, "annual_energy_needed_kWh": 5000.0,
        "day_of_year": 172, "beta_deg": 30.0, "climate": "midlatitude_winter",
    })
    e_directo = _daily_energy_kwh_m2(-42.0, 172, 30.0, 180.0, 0.0, "midlatitude_winter", 0.2)
    pv_directo = _pv_array_sizing({
        "daily_load_kWh": 5000.0 / 365.0, "peak_sun_hours": e_directo, "eta_system": 0.80,
    })
    checks.append({
        "name": "pv_array_power_matches_direct_call",
        "bridge_pv_kW": r["pv_array_power_kW"], "direct_pv_kW": pv_directo["pv_array_power_kW"],
        "passed": bool(abs(r["pv_array_power_kW"] - pv_directo["pv_array_power_kW"]) < 1e-6),
    })

    r_eta_baja = _mode_size_system_for_heating({
        "latitude_deg": -42.0, "annual_energy_needed_kWh": 5000.0, "eta_system": 0.70,
    })
    r_eta_alta = _mode_size_system_for_heating({
        "latitude_deg": -42.0, "annual_energy_needed_kWh": 5000.0, "eta_system": 0.90,
    })
    checks.append({
        "name": "higher_eta_system_reduces_pv_array_power",
        "pv_kW_eta_070": r_eta_baja["pv_array_power_kW"], "pv_kW_eta_090": r_eta_alta["pv_array_power_kW"],
        "passed": bool(r_eta_alta["pv_array_power_kW"] < r_eta_baja["pv_array_power_kW"]),
    })

    try:
        _mode_size_system_for_heating({"annual_energy_needed_kWh": 5000.0})
        check4_passed = False
    except ValueError:
        check4_passed = True
    checks.append({
        "name": "missing_latitude_gives_error_no_crash",
        "passed": bool(check4_passed),
    })

    try:
        _mode_size_system_for_heating({
            "latitude_deg": -42.0, "annual_energy_needed_kWh": 5000.0,
            "climate": "climate_inventado",
        })
        check5_passed = False
    except ValueError:
        check5_passed = True
    checks.append({
        "name": "invalid_climate_propagates_error",
        "passed": bool(check5_passed),
    })

    r6 = _mode_size_system_for_heating({
        "latitude_deg": -42.0, "annual_energy_needed_kWh": 5000.0, "years": 15,
    })
    savings = r6["co2_cumulative_savings_kg"]
    checks.append({
        "name": "cumulative_co2_savings_monotonic_increasing",
        "savings_first": savings[0], "savings_last": savings[-1],
        "passed": bool(all(savings[i] < savings[i + 1] for i in range(len(savings) - 1))),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_solar_heating_sizer(mode, params=None):
    params = params or {}
    if mode == "size_system_for_heating":
        return _mode_size_system_for_heating(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"modo desconocido: {mode!r}")


SOLAR_HEATING_SIZER_TOOL_SCHEMA = {
    "name": "solar_heating_sizer",
    "description": (
        "Dimensiona un sistema fotovoltaico de apoyo a calefaccion usando "
        "irradiancia real del peor dia del ano (solsticio de invierno), "
        "combinando solar_radiation_tool + battery_sizing_tool, y proyecta "
        "el CO2 evitado vs lena con carbon_footprint_tool."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["size_system_for_heating", "validate"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "latitude_deg": {"type": "number", "description": "Latitud del sitio, negativa en hemisferio sur"},
                    "annual_energy_needed_kWh": {"type": "number", "description": "Energia termica anual necesaria para calefaccion"},
                    "day_of_year": {"type": "integer", "description": "Dia del ano a usar como peor caso; default: solsticio de invierno segun hemisferio"},
                    "beta_deg": {"type": "number", "description": "Inclinacion del panel; default: abs(latitude_deg) + 15"},
                    "gamma_deg": {"type": "number", "description": "Azimut del panel; default: 0 (hemisferio norte) o 180 (hemisferio sur)"},
                    "altitude_km": {"type": "number", "default": 0.0},
                    "climate": {"type": "string", "enum": sorted(HOTTEL_CLIMATES), "default": "midlatitude_winter",
                        "description": (
                            "Perfil de turbidez atmosferica de Hottel (1976), no clima "
                            "geografico/bioma -- ver solar_radiation_tool para el detalle "
                            "completo de bandas de latitud y estacion. Default aqui es "
                            "'midlatitude_winter' (no 'midlatitude_summer' como en "
                            "solar_radiation_tool) porque este tool dimensiona contra el "
                            "peor dia del ano por diseno: la atmosfera mas clara de invierno "
                            "da MAS irradiancia directa relativa que un dia de verano turbio, "
                            "asi que subir el default a 'summer' aqui subestimaria el peor "
                            "caso real. Ajustar solo si el sitio esta fuera de la banda "
                            "23-66 grados de latitud (usar 'tropical' o 'subarctic_summer' "
                            "segun corresponda)."
                        )},
                    "albedo": {"type": "number", "default": 0.2},
                    "eta_system": {"type": "number", "default": 0.80, "description": "Eficiencia combinada cableado+suciedad+temperatura+MPPT+inversor"},
                    "years": {"type": "integer", "default": 20, "description": "Horizonte de proyeccion de CO2 evitado"},
                    "fv_degradation_pct_per_year": {"type": "number", "default": 0.5},
                    "daily_load_kWh": {"type": "number", "description": "Override de demanda diaria; default: annual_energy_needed_kWh / 365"},
                },
            },
        },
        "required": ["mode"],
    },
}


try:
    from tool_registry import register_tool
    register_tool(
        name="solar_heating_sizer",
        schema=SOLAR_HEATING_SIZER_TOOL_SCHEMA,
        handler=lambda args: compute_solar_heating_sizer(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass
