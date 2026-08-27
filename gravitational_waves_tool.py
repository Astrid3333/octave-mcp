"""
gravitational_waves_tool.py
Ondas gravitacionales: masa de chirp, evolucion de frecuencia (inspiral,
orden post-newtoniano de orden lider), amplitud de strain, frecuencia ISCO,
tiempo hasta la fusion. Formulas de orden lider (leading-order quadrupole /
0PN), no incluyen correcciones post-newtonianas de orden superior --
adecuadas para estimaciones, no para parameter estimation de precision.
"""
import numpy as np

G = 6.674e-11        # m^3 kg^-1 s^-2
C = 2.998e8          # m/s
MSUN = 1.989e30      # kg
MPC = 3.0857e22      # m


def _chirp_mass_msun(m1_msun, m2_msun):
    return (m1_msun * m2_msun) ** (3 / 5) / (m1_msun + m2_msun) ** (1 / 5)


def _isco_gw_frequency_hz(m1_msun, m2_msun):
    M = (m1_msun + m2_msun) * MSUN
    f_orbital = C ** 3 / (6 ** 1.5 * np.pi * G * M)
    return 2 * f_orbital  # frecuencia GW = 2x frecuencia orbital


def _strain_amplitude(m1_msun, m2_msun, f_gw_hz, distance_mpc):
    mc = _chirp_mass_msun(m1_msun, m2_msun) * MSUN
    d = distance_mpc * MPC
    h = (4.0 / d) * (G * mc / C ** 2) ** (5 / 3) * (np.pi * f_gw_hz / C) ** (2 / 3)
    return h


def _time_to_merger_s(m1_msun, m2_msun, f_gw_hz):
    mc = _chirp_mass_msun(m1_msun, m2_msun) * MSUN
    return (5.0 / 256.0) * (C ** 5 / (G * mc) ** (5 / 3)) * (np.pi * f_gw_hz) ** (-8 / 3)


def _frequency_derivative(m1_msun, m2_msun, f_gw_hz):
    mc = _chirp_mass_msun(m1_msun, m2_msun) * MSUN
    return (96.0 / 5.0) * np.pi ** (8 / 3) * (G * mc / C ** 3) ** (5 / 3) * f_gw_hz ** (11 / 3)


def compute_gravitational_waves(mode, **kwargs):
    if mode == "chirp_mass":
        m1 = kwargs["m1_msun"]
        m2 = kwargs["m2_msun"]
        return {"mode": mode, "chirp_mass_msun": _chirp_mass_msun(m1, m2)}

    elif mode == "isco_frequency":
        m1 = kwargs["m1_msun"]
        m2 = kwargs["m2_msun"]
        return {"mode": mode, "gw_frequency_isco_hz": _isco_gw_frequency_hz(m1, m2)}

    elif mode == "strain_amplitude":
        m1 = kwargs["m1_msun"]
        m2 = kwargs["m2_msun"]
        f_gw = kwargs["f_gw_hz"]
        d = kwargs["distance_mpc"]
        return {"mode": mode, "strain": _strain_amplitude(m1, m2, f_gw, d)}

    elif mode == "time_to_merger":
        m1 = kwargs["m1_msun"]
        m2 = kwargs["m2_msun"]
        f_gw = kwargs["f_gw_hz"]
        return {"mode": mode, "time_to_merger_s": _time_to_merger_s(m1, m2, f_gw)}

    elif mode == "frequency_derivative":
        m1 = kwargs["m1_msun"]
        m2 = kwargs["m2_msun"]
        f_gw = kwargs["f_gw_hz"]
        return {"mode": mode, "df_dt_hz_per_s": _frequency_derivative(m1, m2, f_gw)}

    elif mode == "inspiral_summary":
        m1 = kwargs["m1_msun"]
        m2 = kwargs["m2_msun"]
        f_gw = kwargs.get("f_gw_hz", 35.0)
        d = kwargs.get("distance_mpc", 410.0)
        return {
            "mode": mode,
            "chirp_mass_msun": _chirp_mass_msun(m1, m2),
            "gw_frequency_isco_hz": _isco_gw_frequency_hz(m1, m2),
            "strain_at_f": _strain_amplitude(m1, m2, f_gw, d),
            "time_to_merger_s": _time_to_merger_s(m1, m2, f_gw),
            "df_dt_hz_per_s": _frequency_derivative(m1, m2, f_gw),
            "f_gw_hz_used": f_gw,
            "distance_mpc_used": d,
        }

    elif mode == "validate":
        checks = []

        mc = _chirp_mass_msun(36.0, 29.0)
        checks.append(("chirp_mass_gw150914", abs(mc - 28.1) < 0.5))

        t = _time_to_merger_s(36.0, 29.0, 35.0)
        checks.append(("time_to_merger_gw150914", abs(t - 0.2) < 0.05))

        fdot = _frequency_derivative(36.0, 29.0, 35.0)
        checks.append(("freq_derivative_order_of_magnitude", 10.0 < fdot < 200.0))

        f_isco = _isco_gw_frequency_hz(36.0, 29.0)
        checks.append(("isco_frequency_order_of_magnitude", 80.0 < f_isco < 250.0))

        h = _strain_amplitude(36.0, 29.0, 150.0, 410.0)
        checks.append(("strain_order_of_magnitude", 3e-22 < h < 6e-21))

        t_low = _time_to_merger_s(36.0, 29.0, 20.0)
        t_high = _time_to_merger_s(36.0, 29.0, 100.0)
        checks.append(("time_decreases_with_frequency", t_low > t_high))

        fdot_low = _frequency_derivative(36.0, 29.0, 20.0)
        fdot_high = _frequency_derivative(36.0, 29.0, 100.0)
        checks.append(("fdot_increases_with_frequency", fdot_high > fdot_low))

        mc_swap = _chirp_mass_msun(29.0, 36.0)
        checks.append(("chirp_mass_symmetric", abs(mc - mc_swap) < 1e-9))

        n_passed = sum(1 for _, ok in checks if ok)
        n_total = len(checks)
        return {
            "mode": mode,
            "validation_passed": n_passed == n_total,
            "passed": n_passed,
            "total": n_total,
            "checks": checks,
        }

    else:
        return {"error": f"Modo desconocido: {mode}"}


GRAVITATIONAL_WAVES_TOOL_SCHEMA = {
    "name": "gravitational_waves",
    "description": (
        "Ondas gravitacionales de sistemas binarios compactos: masa de "
        "chirp, frecuencia GW en el ISCO, amplitud de strain, tiempo hasta "
        "la fusion y derivada de frecuencia (chirp rate). Formulas de orden "
        "lider (0PN), calibradas contra GW150914."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["chirp_mass", "isco_frequency", "strain_amplitude",
                         "time_to_merger", "frequency_derivative",
                         "inspiral_summary", "validate"],
            },
            "m1_msun": {"type": "number", "description": "masa del objeto 1 en masas solares"},
            "m2_msun": {"type": "number", "description": "masa del objeto 2 en masas solares"},
            "f_gw_hz": {"type": "number", "description": "frecuencia de la onda gravitacional en Hz (2x frecuencia orbital)"},
            "distance_mpc": {"type": "number", "description": "distancia de luminosidad en megaparsecs"},
        },
        "required": ["mode"],
    },
}

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("gravitational_waves", GRAVITATIONAL_WAVES_TOOL_SCHEMA,
              lambda args, _f=compute_gravitational_waves: _f(**args))
