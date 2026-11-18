"""
conductor_losses_tool.py

Resistencia, tierra y pérdidas para circuitos con conductores.
Pensado para el repo octave-mcp (mismo patrón que materials_db_tool:
compute + _handler + register_tool). Todo en SI, Python puro (math/cmath).

Modos:
  resistance  -- R_dc = rho*L/A, R(T) lineal, R_ac por efecto piel,
                 caída de tensión por longitud de cable.
  grounding   -- electrodo de varilla (Dwight), resistividad desde
                 medición Wenner (rho = 2*pi*a*R), resistividad de suelo
                 desde humedad con Archie.
  losses      -- pérdida dieléctrica (tan delta), atenuación en
                 dieléctrico, Q desde ancho de banda, Q dieléctrico.
  validate    -- chequeos contra formas cerradas.

Hp: no se reimplementa; usar units_constants_tool (hp -> W).

Parámetros de Archie (a, m, n) son supuestos que deben calibrarse con
mediciones del sitio; los valores por defecto son solo punto de partida.
"""

import cmath
import math

from tool_registry import register_tool

MU0 = 4e-7 * math.pi
C0 = 299792458.0
RHO_CU_20C = 1.68e-8        # Ω·m, cobre recocido a 20 °C
ALPHA_CU = 0.00393          # 1/K, cobre a 20 °C

CONDUCTOR_LOSSES_TOOL_SCHEMA = {
    "name": "conductor_losses_tool",
    "description": (
        "Resistencia (DC, temperatura, efecto piel, longitud de cable), "
        "tierra (electrodo Dwight, Wenner, Archie desde humedad) y pérdidas "
        "(tan delta, atenuación dieléctrica, Q). SI. "
        "Modos: resistance, grounding, losses, validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["resistance", "grounding", "losses", "validate"],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------- resistance
def resistance_dc(rho, length_m, area_m2):
    """R = rho*L/A [Ω]."""
    if area_m2 <= 0 or length_m < 0:
        raise ValueError("area_m2 debe ser > 0 y length_m >= 0")
    return rho * length_m / area_m2


def resistance_temperature(r0, temp_c, t0_c=20.0, alpha=ALPHA_CU):
    """R(T) = R0*[1 + alpha*(T - T0)] (lineal, válido en rangos moderados)."""
    return r0 * (1.0 + alpha * (temp_c - t0_c))


def skin_depth(rho, freq_hz, mu_r=1.0):
    """delta = sqrt(2*rho / (omega*mu)) [m]."""
    if freq_hz <= 0:
        raise ValueError("freq_hz debe ser > 0")
    omega = 2.0 * math.pi * freq_hz
    return math.sqrt(2.0 * rho / (omega * MU0 * mu_r))


def ac_to_dc_ratio_exact(radius_m, delta_m):
    """
    Relación exacta R_ac/R_dc para un conductor cilíndrico sólido (Bessel):
      R_ac/R_dc = Re[ (k*a) * J0(k*a) / (2 * J1(k*a)) ],  k = (1 + j)/delta
    Válida para cualquier relación a/delta. Límites: -> 1 si a << delta,
    -> a/(2*delta) si a >> delta.
    """
    from scipy.special import jv
    if radius_m <= 0 or delta_m <= 0:
        raise ValueError("radius_m y delta_m deben ser > 0")
    z = (1.0 + 1.0j) * radius_m / delta_m
    return float(((z * jv(0, z)) / (2.0 * jv(1, z))).real)


def resistance_ac_round_wire(rho, length_m, radius_m, freq_hz):
    """
    R_ac exacto para cilindro sólido por Bessel. Incluye la aproximación
    asintótica a/(2*delta) solo como referencia (válida si a >> delta).
    """
    d = skin_depth(rho, freq_hz)
    r_dc = rho * length_m / (math.pi * radius_m ** 2)
    ratio = ac_to_dc_ratio_exact(radius_m, d)
    return {"skin_depth_m": d, "R_dc_ohm": r_dc, "R_ac_ohm": r_dc * ratio,
            "ratio_ac_dc": ratio, "ratio_asymptotic_a_over_2delta": radius_m / (2.0 * d),
            "method": "bessel_exact"}


def voltage_drop(current_a, rho, length_m, area_m2):
    """Caída de tensión por longitud de cable: dV = I*R."""
    return current_a * resistance_dc(rho, length_m, area_m2)


# ----------------------------------------------------------------- grounding
def ground_rod_resistance(rho, rod_length_m, rod_radius_m):
    """
    Electrodo vertical (Dwight): R = rho/(2*pi*L) * [ln(4L/a) - 1].
    Válido para L >> a.
    """
    if rod_length_m <= rod_radius_m:
        raise ValueError("la varilla debe ser más larga que su radio")
    L, a = rod_length_m, rod_radius_m
    return rho / (2.0 * math.pi * L) * (math.log(4.0 * L / a) - 1.0)


def wenner_resistivity(spacing_m, measured_r_ohm):
    """Método Wenner, b << a: rho = 2*pi*a*R [Ω·m]."""
    return 2.0 * math.pi * spacing_m * measured_r_ohm


def archie_resistivity(rho_water, porosity, saturation, a=1.0, m=2.0, n=2.0):
    """
    Ley de Archie: rho = a * rho_w * phi^(-m) * S_w^(-n).
    phi = porosidad; S_w = theta / theta_s. a, m, n requieren calibración.
    """
    if not (0 < porosity <= 1) or not (0 < saturation <= 1):
        raise ValueError("porosity y saturation deben estar en (0, 1]")
    return a * rho_water * porosity ** (-m) * saturation ** (-n)


def saturation_from_theta(theta, theta_s):
    """S_w = theta / theta_s, con porosidad phi ~ theta_s."""
    if theta_s <= 0:
        raise ValueError("theta_s debe ser > 0")
    return min(max(theta / theta_s, 1e-6), 1.0)


# -------------------------------------------------------------------- losses
def dielectric_loss_power(freq_hz, capacitance_f, voltage_v, tan_delta):
    """P = omega*C*V^2*tan(delta) [W] (condensador con dieléctrico con pérdidas)."""
    return 2.0 * math.pi * freq_hz * capacitance_f * voltage_v ** 2 * tan_delta


def dielectric_attenuation(freq_hz, eps_r, tan_delta):
    """
    Atenuación de onda plana en dieléctrico con pérdidas [Np/m].
    Se calcula como Re(gamma) con gamma = j*k0*sqrt(eps_r*(1 - j*tan)).
    Equivale a pi*sqrt(eps_r)*tan/lambda0 para tan << 1.
    """
    k0 = 2.0 * math.pi * freq_hz / C0
    gamma = 1j * k0 * cmath.sqrt(eps_r * (1.0 - 1j * tan_delta))
    return gamma.real


def q_from_bandwidth(f0_hz, f_low_hz, f_high_hz):
    """Q cargado = f0 / (f_high - f_low) con puntos de -3 dB."""
    bw = f_high_hz - f_low_hz
    if bw <= 0:
        raise ValueError("f_high debe ser mayor que f_low")
    return f0_hz / bw


def q_dielectric(tan_delta):
    """Q dieléctrico = 1/tan(delta)."""
    if tan_delta <= 0:
        raise ValueError("tan_delta debe ser > 0")
    return 1.0 / tan_delta


# ----------------------------------------------------------------- handlers
def _mode_resistance(p):
    rho = p.get("rho", RHO_CU_20C)
    L = p["length_m"]
    out = {}
    if "radius_m" in p:
        out["R_dc_ohm"] = resistance_dc(rho, L, math.pi * p["radius_m"] ** 2)
    elif "area_m2" in p:
        out["R_dc_ohm"] = resistance_dc(rho, L, p["area_m2"])
    if "temp_c" in p:
        out["R_at_temp_ohm"] = resistance_temperature(
            out["R_dc_ohm"], p["temp_c"], p.get("t0_c", 20.0), p.get("alpha", ALPHA_CU))
    if "freq_hz" in p and "radius_m" in p:
        out.update(resistance_ac_round_wire(rho, L, p["radius_m"], p["freq_hz"]))
    if "current_a" in p and "area_m2" in p:
        out["voltage_drop_v"] = voltage_drop(p["current_a"], rho, L, p["area_m2"])
    return out


def _mode_grounding(p):
    out = {}
    if "wenner_spacing_m" in p and "wenner_r_ohm" in p:
        out["rho_measured_ohm_m"] = wenner_resistivity(
            p["wenner_spacing_m"], p["wenner_r_ohm"])
    if "rho_water" in p and "porosity" in p and "saturation" in p:
        out["rho_archie_ohm_m"] = archie_resistivity(
            p["rho_water"], p["porosity"], p["saturation"],
            p.get("a", 1.0), p.get("m", 2.0), p.get("n", 2.0))
    if "theta" in p and "theta_s" in p and "rho_water" in p:
        s = saturation_from_theta(p["theta"], p["theta_s"])
        out["saturation"] = s
        out["rho_archie_ohm_m"] = archie_resistivity(
            p["rho_water"], p["theta_s"], s,
            p.get("a", 1.0), p.get("m", 2.0), p.get("n", 2.0))
    if "rod_length_m" in p and "rod_radius_m" in p:
        rho = p.get("rho", out.get("rho_measured_ohm_m",
                                   out.get("rho_archie_ohm_m")))
        if rho is None:
            raise ValueError("falta rho (medido, Wenner o Archie) para el electrodo")
        out["rod_R_ohm"] = ground_rod_resistance(rho, p["rod_length_m"], p["rod_radius_m"])
    return out


def _mode_losses(p):
    out = {}
    if "freq_hz" in p and "capacitance_f" in p and "voltage_v" in p and "tan_delta" in p:
        out["P_dielectric_w"] = dielectric_loss_power(
            p["freq_hz"], p["capacitance_f"], p["voltage_v"], p["tan_delta"])
    if "freq_hz" in p and "eps_r" in p and "tan_delta" in p:
        out["alpha_np_per_m"] = dielectric_attenuation(p["freq_hz"], p["eps_r"], p["tan_delta"])
    if "tan_delta" in p:
        out["Q_dielectric"] = q_dielectric(p["tan_delta"])
    if all(k in p for k in ("f0_hz", "f_low_hz", "f_high_hz")):
        out["Q_loaded"] = q_from_bandwidth(p["f0_hz"], p["f_low_hz"], p["f_high_hz"])
    return out


def _mode_validate():
    checks = []

    def chk(name, got, want, tol):
        ok = abs(got - want) <= tol * max(1.0, abs(want))
        checks.append({"name": name, "got": got, "want": want, "passed": ok})

    # 1. R_dc = rho*L/A (cobre, 100 m, 1 mm²)
    chk("R_dc cobre 100m 1mm2", resistance_dc(RHO_CU_20C, 100, 1e-6), 1.68, 1e-12)

    # 2. R(T) con alpha de cobre, 75 °C
    chk("R(T) 75C", resistance_temperature(1.0, 75.0), 1.21615, 1e-9)

    # 3a. Efecto piel, límite a >> delta: exacto -> a/(2 delta)  (tolerancia relativa 1 %)
    d_big = 1e-3 / 100.0
    r_big = ac_to_dc_ratio_exact(1e-3, d_big)
    chk("skin a>>delta -> a/(2delta)", r_big, 1e-3 / (2 * d_big), 0.01)

    # 3b. Efecto piel, límite a << delta: exacto -> 1
    chk("skin a<<delta -> 1", ac_to_dc_ratio_exact(1e-3, 1e-3 * 100), 1.0, 1e-4)

    # 3c. R_ac nunca menor que R_dc (MXene, a/delta = 0.2: antes salía 1581 < 15915)
    rr = [ac_to_dc_ratio_exact(1e-3, 1e-3 / x) for x in (0.1, 0.2, 0.5, 1, 2, 5, 20, 100)]
    checks.append({"name": "R_ac >= R_dc para todo a/delta",
                   "passed": all(v >= 1.0 - 1e-12 for v in rr),
                   "detail": f"min={min(rr):.6f}"})

    # 3d. Monotonía: el cociente crece con a/delta
    checks.append({"name": "ratio monótono en a/delta",
                   "passed": all(b > a for a, b in zip(rr, rr[1:])), "detail": ""})

    # 4. Dwight: varilla L=3 m, a=0.01 m, rho=100 Ω·m
    want = 100 / (2 * math.pi * 3) * (math.log(4 * 3 / 0.01) - 1)
    chk("Dwight rod", ground_rod_resistance(100, 3, 0.01), want, 1e-12)

    # 5. Wenner: a=2 m, R=10 Ω -> rho = 2*pi*a*R (inverso)
    chk("Wenner rho", wenner_resistivity(2.0, 10.0), 2 * math.pi * 2 * 10, 1e-12)

    # 6. Archie: phi=0.4, S=1, a=1, m=2, n=2, rho_w=20 -> 20/0.16 = 125
    chk("Archie phi=0.4 S=1", archie_resistivity(20, 0.4, 1.0), 125.0, 1e-12)

    # 7. Atenuación dieléctrica: comparar con pi*sqrt(eps)*tan/lambda0 (tan<<1)
    f, eps, tan = 1e9, 4.0, 1e-4
    lam0 = C0 / f
    chk("alpha dielectrico (tan<<1)",
        dielectric_attenuation(f, eps, tan),
        math.pi * math.sqrt(eps) * tan / lam0, 1e-4)

    # 8. Q de RLC serie: Q = (1/R)*sqrt(L/C), y f0/BW con BW = R/(2*pi*L)
    R, L, C = 2.0, 1e-6, 1e-9
    f0 = 1 / (2 * math.pi * math.sqrt(L * C))
    bw = R / (2 * math.pi * L)
    chk("Q RLC serie via BW", q_from_bandwidth(f0, f0 - bw / 2, f0 + bw / 2),
        (1 / R) * math.sqrt(L / C), 1e-9)

    # 9. P dieléctrico: omega*C*V^2*tan
    chk("P dielectrico", dielectric_loss_power(1e3, 1e-6, 10.0, 0.02),
        2 * math.pi * 1e3 * 1e-6 * 100 * 0.02, 1e-12)

    passed = sum(c["passed"] for c in checks)
    return {"checks": checks, "total_passed": passed, "total_checks": len(checks),
            "validation_passed": passed == len(checks)}


_MODES = {"resistance": _mode_resistance, "grounding": _mode_grounding,
          "losses": _mode_losses}


def _handler(args):
    mode = args.get("mode")
    params = args.get("params") or {}
    try:
        if mode == "validate":
            return _mode_validate()
        if mode in _MODES:
            return {"mode": mode, "result": _MODES[mode](params)}
        return {"error": f"mode desconocido: {mode}"}
    except (KeyError, ValueError, TypeError, ZeroDivisionError) as e:
        return {"error": f"parámetros inválidos: {e}"}


register_tool(
    name="conductor_losses_tool",
    schema=CONDUCTOR_LOSSES_TOOL_SCHEMA,
    handler=_handler,
)
