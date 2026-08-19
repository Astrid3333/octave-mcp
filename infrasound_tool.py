"""
infrasound_tool.py

Propagacion de infrasonido (frecuencias < 20 Hz): atenuacion por
esparcimiento geometrico esferico + absorcion atmosferica clasica
(formulacion simplificada tipo ISO 9613-1, coeficiente de absorcion
dependiente de frecuencia/temperatura/humedad), y tiempo de viaje dado un
perfil simple de velocidad del sonido con viento.

Modos:
  - attenuation_profile: dado nivel fuente (dB SPL @ 1m), frecuencia,
    temperatura, humedad relativa, devuelve nivel recibido en funcion de la
    distancia (barrido).
  - travel_time: distancia / velocidad efectiva del sonido (con
    temperatura y componente de viento a favor/en contra).
  - validate: a mayor distancia el nivel debe ser monotonamente decreciente;
    velocidad del sonido a 20C debe aproximar ~343 m/s.
"""

import numpy as np


def _sound_speed(temperature_c):
    # aproximacion estandar: c = 331.3 * sqrt(1 + T/273.15)  (m/s)
    return 331.3 * np.sqrt(1.0 + temperature_c / 273.15)


def _atmospheric_absorption_coefficient(frequency_hz, temperature_c, relative_humidity_pct):
    """Coeficiente de absorcion atmosferica simplificado (dB/m), basado en la
    forma funcional clasica de ISO 9613-1 con relajacion molecular de O2/N2.
    Simplificacion pensada para infrasonido (frecuencias bajas -> absorcion
    tipicamente muy chica, del orden de 1e-4 a 1e-2 dB/km)."""
    T = temperature_c + 273.15
    T0 = 293.15
    h = relative_humidity_pct  # % humedad relativa, uso directo simplificado
    f = max(frequency_hz, 1e-3)

    # frecuencias de relajacion (formulas simplificadas ISO 9613-1, Annex B)
    frO = 24.0 + 4.04e4 * h * (0.02 + h) / (0.391 + h)
    frN = (T / T0) ** (-0.5) * (9.0 + 280.0 * h * np.exp(-4.170 * ((T / T0) ** (-1.0 / 3.0) - 1.0)))

    term_classical = 1.84e-11 * (1.0 / (T / T0) ** 0.5) if False else 1.84e-11 * (T / T0) ** 0.5
    term_O2 = (T / T0) ** (-2.5) * 0.01275 * np.exp(-2239.1 / T) * (frO + f**2 / frO) ** -1
    term_N2 = (T / T0) ** (-2.5) * 0.1068 * np.exp(-3352.0 / T) * (frN + f**2 / frN) ** -1

    alpha = 8.686 * f**2 * (term_classical + term_O2 + term_N2)  # dB/m
    return float(max(alpha, 0.0))


def _attenuation_profile(source_level_db, frequency_hz, temperature_c=15.0, relative_humidity_pct=50.0,
                          distances_km=None):
    if distances_km is None:
        distances_km = list(np.linspace(1, 500, 20))
    alpha = _atmospheric_absorption_coefficient(frequency_hz, temperature_c, relative_humidity_pct)
    results = []
    for d_km in distances_km:
        d_m = d_km * 1000.0
        if d_m <= 1.0:
            spreading_loss = 0.0
        else:
            spreading_loss = 20.0 * np.log10(d_m / 1.0)  # referencia a 1 m
        absorption_loss = alpha * d_m
        received_level = source_level_db - spreading_loss - absorption_loss
        results.append(
            {
                "distance_km": d_km,
                "spreading_loss_db": float(spreading_loss),
                "absorption_loss_db": float(absorption_loss),
                "received_level_db": float(received_level),
            }
        )
    return {
        "mode": "attenuation_profile",
        "source_level_db": source_level_db,
        "frequency_hz": frequency_hz,
        "temperature_c": temperature_c,
        "relative_humidity_pct": relative_humidity_pct,
        "absorption_coefficient_db_per_m": alpha,
        "profile": results,
        "note": "spreading esferico ideal (20*log10(d)); no incluye refraccion atmosferica ni topografia.",
    }


def _travel_time(distance_km, temperature_c=15.0, wind_speed_ms=0.0, wind_direction="tailwind"):
    c = _sound_speed(temperature_c)
    sign = 1.0 if wind_direction == "tailwind" else -1.0
    c_eff = c + sign * wind_speed_ms
    if c_eff <= 0:
        raise ValueError("velocidad efectiva del sonido <= 0 (viento en contra excede c)")
    d_m = distance_km * 1000.0
    t_s = d_m / c_eff
    return {
        "mode": "travel_time",
        "distance_km": distance_km,
        "temperature_c": temperature_c,
        "sound_speed_still_air_ms": float(c),
        "wind_speed_ms": wind_speed_ms,
        "wind_direction": wind_direction,
        "effective_speed_ms": float(c_eff),
        "travel_time_s": float(t_s),
        "travel_time_min": float(t_s / 60.0),
    }


def _validate():
    c20 = _sound_speed(20.0)
    speed_ok = abs(c20 - 343.0) < 2.0

    profile = _attenuation_profile(140.0, 1.0, distances_km=[1, 10, 50, 100])
    levels = [p["received_level_db"] for p in profile["profile"]]
    monotonic_ok = all(levels[i] > levels[i + 1] for i in range(len(levels) - 1))

    return {
        "mode": "validate",
        "sound_speed_at_20C_ms": c20,
        "attenuation_levels_db": levels,
        "expected": "c(20C) ~343 m/s; nivel recibido decrece monotonamente con la distancia",
        "validation_passed": bool(speed_ok and monotonic_ok),
    }


def compute_infrasound_tool(mode, **kwargs):
    if mode == "attenuation_profile":
        return _attenuation_profile(
            kwargs["source_level_db"],
            kwargs["frequency_hz"],
            temperature_c=kwargs.get("temperature_c", 15.0),
            relative_humidity_pct=kwargs.get("relative_humidity_pct", 50.0),
            distances_km=kwargs.get("distances_km"),
        )
    elif mode == "travel_time":
        return _travel_time(
            kwargs["distance_km"],
            temperature_c=kwargs.get("temperature_c", 15.0),
            wind_speed_ms=kwargs.get("wind_speed_ms", 0.0),
            wind_direction=kwargs.get("wind_direction", "tailwind"),
        )
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"mode desconocido: {mode}")


INFRASOUND_TOOL_SCHEMA = {
    "name": "infrasound_tool",
    "description": (
        "Propagacion de infrasonido: perfil de atenuacion (esparcimiento esferico 20*log10(d) + "
        "absorcion atmosferica tipo ISO 9613-1 simplificada) en funcion de la distancia, y tiempo "
        "de viaje dado perfil simple de temperatura/viento. mode='attenuation_profile' "
        "(source_level_db, frequency_hz, temperature_c, relative_humidity_pct, distances_km); "
        "mode='travel_time' (distance_km, temperature_c, wind_speed_ms, wind_direction); "
        "mode='validate' chequea c(20C)~343m/s y monotonia de la atenuacion."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["attenuation_profile", "travel_time", "validate"],
                "default": "validate",
            },
            "source_level_db": {"type": "number", "description": "Nivel fuente dB SPL @1m. attenuation_profile."},
            "frequency_hz": {"type": "number", "description": "Frecuencia (Hz), tipicamente <20 para infrasonido."},
            "temperature_c": {"type": "number", "default": 15.0},
            "relative_humidity_pct": {"type": "number", "default": 50.0, "description": "attenuation_profile."},
            "distances_km": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Distancias a evaluar (km). attenuation_profile, opcional.",
            },
            "distance_km": {"type": "number", "description": "Distancia fuente-receptor (km). travel_time."},
            "wind_speed_ms": {"type": "number", "default": 0.0, "description": "travel_time."},
            "wind_direction": {
                "type": "string",
                "enum": ["tailwind", "headwind"],
                "default": "tailwind",
                "description": "travel_time.",
            },
        },
        "required": ["mode"],
    },
}

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("infrasound_tool", INFRASOUND_TOOL_SCHEMA, lambda args, _f=compute_infrasound_tool: _f(**args))
