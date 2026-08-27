"""
ultrasound_tool.py

Complementa acoustics_tool.py (que ya cubre propagacion FDTD 1D generica via
pressure_wave_1d, modos de sala y reverberacion de Sabine) con la fisica que
falta para modelar ultrasonido especificamente:

  1. Impedancia acustica y reflexion/transmision en interfaces (Z=rho*c,
     R=(Z2-Z1)/(Z2+Z1)) -- es literalmente el mecanismo por el cual un pulso
     de ultrasonido genera un eco al cruzar entre dos medios distintos.
  2. Atenuacion dependiente de frecuencia (ley de potencia, tipico en tejido
     blando ~0.3-1.0 dB/cm/MHz) -- el ultrasonido se atenua mucho mas rapido
     que el sonido audible, algo que un solver FDTD generico sin este termino
     no captura.
  3. Conversion tiempo de vuelo <-> distancia para pulso-eco (sonar/eco de
     ultrasonido: distancia = c*t/2).
  4. Simulacion de pulso-eco a traves de multiples capas (medio inicial +
     N interfaces), acumulando atenuacion y reflexion capa por capa -- util
     para casos tipo "medicion de espesor" o imagenologia simple por eco.
  5. Efecto Doppler en modo pulso-eco (desplazamiento de frecuencia por
     movimiento de un reflector -- base de la medicion de flujo sanguineo).
  6. Umbral de cavitacion acustica en liquidos, via dos aproximaciones
     independientes (Indice Mecanico clinico + umbral de Blake fisico
     cuasi-estatico) -- sin pretender que exista una unica formula canonica.
  7. Generacion de segundo armonico en propagacion no lineal de alta
     intensidad (base de la imagenologia armonica), en el regimen
     debilmente no lineal pre-choque (solucion de Fubini).

No reemplaza pressure_wave_1d (que resuelve la PDE completa); esta tool cubre
los efectos de perdida y de interfaz que ese solver generico no modela.

Referencias de orden de magnitud (no para uso clinico ni de precision):
  - Impedancias tipicas (rho en kg/m3, c en m/s):
      aire:   rho=1.2,    c=343   -> Z=411 Rayl
      agua:   rho=1000,   c=1480  -> Z=1.48e6 Rayl
      tejido blando: rho=1050, c=1540 -> Z=1.617e6 Rayl
      musculo: rho=1050,  c=1580  -> Z=1.659e6 Rayl
      grasa:  rho=920,    c=1450  -> Z=1.334e6 Rayl
      hueso:  rho=1900,   c=4080  -> Z=7.752e6 Rayl
      acero:  rho=7850,   c=5900  -> Z=4.632e7 Rayl
  - Atenuacion tipica en tejido blando: ~0.3-1.0 dB/cm/MHz (ley ~lineal en f)
"""
import json
import numpy as np
from scipy.special import jv
from typing import Dict, Any, List, Optional


MATERIALS = {
    "air":         {"rho": 1.2,    "c": 343.0},
    "water":       {"rho": 1000.0, "c": 1480.0},
    "soft_tissue": {"rho": 1050.0, "c": 1540.0},
    "fat":         {"rho": 920.0,  "c": 1450.0},
    "muscle":      {"rho": 1050.0, "c": 1580.0},
    "bone":        {"rho": 1900.0, "c": 4080.0},
    "steel":       {"rho": 7850.0, "c": 5900.0},
}

NEPER_PER_DB = 1.0 / 8.685889638  # 1 Np = 8.685889638 dB


# ----------------------------------------------------------------------
# Fisica base
# ----------------------------------------------------------------------

def acoustic_impedance(rho: float, c: float) -> float:
    """Z = rho * c, en Rayl (Pa*s/m)."""
    return rho * c


def reflection_transmission(Z1: float, Z2: float) -> Dict[str, Any]:
    """
    Coeficientes de reflexion/transmision en incidencia normal entre dos
    medios de impedancia Z1 (incidente) y Z2 (transmitido).

    R = (Z2 - Z1) / (Z2 + Z1)   -- coeficiente de reflexion de presion (amplitud)
    T = 2*Z2 / (Z1 + Z2)        -- coeficiente de transmision de presion (amplitud)
    R_intensity = R^2           -- fraccion de intensidad reflejada
    T_intensity = 1 - R_intensity  -- fraccion de intensidad transmitida (conservacion)
    """
    if Z1 <= 0 or Z2 <= 0:
        raise ValueError("Z1 y Z2 deben ser positivas")
    R = (Z2 - Z1) / (Z2 + Z1)
    T = 2.0 * Z2 / (Z1 + Z2)
    R_intensity = R ** 2
    T_intensity = 1.0 - R_intensity
    return {
        "Z1_rayl": Z1,
        "Z2_rayl": Z2,
        "pressure_reflection_coeff": R,
        "pressure_transmission_coeff": T,
        "intensity_reflection_coeff": R_intensity,
        "intensity_transmission_coeff": T_intensity,
    }


def attenuation_coefficient(freq_mhz: float, alpha_db_cm_mhz: float = 0.5,
                             power: float = 1.0) -> Dict[str, Any]:
    """
    Coeficiente de atenuacion en funcion de la frecuencia (ley de potencia,
    tipicamente power=1.0 para tejido blando; algunos medios usan power~1.1-1.3).

    alpha_dB_por_cm = alpha_db_cm_mhz * freq_mhz^power
    """
    if freq_mhz <= 0:
        raise ValueError("freq_mhz debe ser positiva")
    alpha_db_per_cm = alpha_db_cm_mhz * (freq_mhz ** power)
    alpha_np_per_cm = alpha_db_per_cm * NEPER_PER_DB
    alpha_np_per_m = alpha_np_per_cm * 100.0
    return {
        "freq_mhz": freq_mhz,
        "alpha_db_per_cm": alpha_db_per_cm,
        "alpha_np_per_m": alpha_np_per_m,
    }


def amplitude_after_distance(A0: float, distance_m: float, freq_mhz: float,
                              alpha_db_cm_mhz: float = 0.5,
                              power: float = 1.0) -> Dict[str, Any]:
    """Amplitud A0 tras propagarse distance_m con atenuacion exponencial."""
    if distance_m < 0:
        raise ValueError("distance_m no puede ser negativa")
    att = attenuation_coefficient(freq_mhz, alpha_db_cm_mhz, power)
    alpha_np_per_m = att["alpha_np_per_m"]
    amplitude_final = A0 * np.exp(-alpha_np_per_m * distance_m)
    db_loss = att["alpha_db_per_cm"] * (distance_m * 100.0)
    return {
        "A0": A0,
        "distance_m": distance_m,
        "freq_mhz": freq_mhz,
        "amplitude_final": float(amplitude_final),
        "db_loss": db_loss,
        "alpha_np_per_m": alpha_np_per_m,
    }


def time_of_flight_to_distance(t_seconds: float, c: float,
                                pulse_echo: bool = True) -> Dict[str, Any]:
    """Distancia recorrida a partir de un tiempo medido. pulse_echo=True
    asume ida y vuelta (sonar/eco), por lo que divide entre 2."""
    if t_seconds < 0 or c <= 0:
        raise ValueError("t_seconds >= 0 y c > 0 son requeridos")
    distance = (c * t_seconds / 2.0) if pulse_echo else (c * t_seconds)
    return {"t_seconds": t_seconds, "c": c, "pulse_echo": pulse_echo,
            "distance_m": distance}


def distance_to_time_of_flight(distance_m: float, c: float,
                                pulse_echo: bool = True) -> Dict[str, Any]:
    """Inverso de time_of_flight_to_distance: tiempo esperado para una
    distancia dada."""
    if distance_m < 0 or c <= 0:
        raise ValueError("distance_m >= 0 y c > 0 son requeridos")
    t = (2.0 * distance_m / c) if pulse_echo else (distance_m / c)
    return {"distance_m": distance_m, "c": c, "pulse_echo": pulse_echo,
            "t_seconds": t}


def pulse_echo_layers(layers: List[Dict[str, Any]], freq_mhz: float,
                       A0: float = 1.0, alpha_db_cm_mhz: float = 0.5,
                       power: float = 1.0) -> Dict[str, Any]:
    """
    Simula un pulso viajando a traves de N capas consecutivas y calcula la
    amplitud recibida de cada eco reflejado en cada interfaz interna.

    layers: lista ordenada de {"name"?: str, "rho": float, "c": float,
            "thickness_m": float}. La ultima capa no necesita thickness_m
            relevante para el calculo (el pulso no vuelve a cruzar mas
            interfaces despues de la ultima), pero se acepta por uniformidad.
            Requiere al menos 2 capas (1 interfaz).

    Para cada interfaz i (entre layers[i] y layers[i+1]):
      - el pulso viaja por las capas 0..i acumulando atenuacion,
      - se refleja parcialmente segun el coeficiente de reflexion de presion,
      - el eco vuelve por el mismo camino, acumulando atenuacion otra vez,
      - se registra profundidad, tiempo de ida-y-vuelta y amplitud recibida.

    La porcion transmitida sigue de largo hacia la siguiente interfaz.
    """
    n = len(layers)
    if n < 2:
        raise ValueError(
            "pulse_echo_layers requiere al menos 2 capas (medio inicial + "
            "al menos una interfaz)"
        )
    if freq_mhz <= 0:
        raise ValueError("freq_mhz debe ser positiva")

    Zs = [acoustic_impedance(l["rho"], l["c"]) for l in layers]

    echoes = []
    cumulative_distance = 0.0
    cumulative_amplitude = A0
    cumulative_time = 0.0

    for i in range(n - 1):
        thickness = layers[i]["thickness_m"]
        c_i = layers[i]["c"]
        if thickness < 0:
            raise ValueError(f"thickness_m negativo en layers[{i}]")

        cumulative_distance += thickness
        cumulative_time += thickness / c_i

        att = amplitude_after_distance(cumulative_amplitude, thickness,
                                        freq_mhz, alpha_db_cm_mhz, power)
        cumulative_amplitude = att["amplitude_final"]

        rt = reflection_transmission(Zs[i], Zs[i + 1])
        echo_amplitude_at_interface = cumulative_amplitude * abs(
            rt["pressure_reflection_coeff"]
        )

        back_att = amplitude_after_distance(
            echo_amplitude_at_interface, cumulative_distance,
            freq_mhz, alpha_db_cm_mhz, power
        )
        received_amplitude = back_att["amplitude_final"]
        round_trip_time = 2.0 * cumulative_time

        echoes.append({
            "interface_index": i,
            "between": [
                layers[i].get("name", f"layer_{i}"),
                layers[i + 1].get("name", f"layer_{i + 1}"),
            ],
            "depth_m": cumulative_distance,
            "reflection_coeff": rt["pressure_reflection_coeff"],
            "round_trip_time_s": round_trip_time,
            "received_amplitude": received_amplitude,
        })

        # la porcion transmitida continua hacia la siguiente interfaz
        cumulative_amplitude = cumulative_amplitude * rt["pressure_transmission_coeff"]

    return {
        "freq_mhz": freq_mhz,
        "n_layers": n,
        "echoes": echoes,
    }


def doppler_effect(f0_hz: float, c: float = 1540.0, theta_deg: float = 0.0,
                    v_ms: Optional[float] = None,
                    doppler_shift_hz: Optional[float] = None,
                    prf_hz: Optional[float] = None) -> Dict[str, Any]:
    """
    Efecto Doppler en modo pulso-eco (transductor unico, emisor=receptor),
    el caso estandar en ecografia Doppler medica.

    Formula clasica: Δf = 2 * f0 * v * cos(theta) / c
    (el factor 2 es porque el camino ida+vuelta duplica el corrimiento
    respecto al Doppler de una sola via).

    Dar UNO de v_ms / doppler_shift_hz -- el otro se despeja. Si se da
    prf_hz (frecuencia de repeticion de pulsos) se agrega el chequeo de
    aliasing/limite de Nyquist propio del Doppler pulsado.

    Limites: valido para |v| << c (siempre cierto en tejido); asume
    reflector puntual y haz bien colimado (sin dispersion angular). Con
    theta_deg=90 el corrimiento es nulo por geometria (cos(90)=0) -- no se
    puede despejar v_ms desde un doppler_shift_hz medido en ese caso, es
    una limitacion fisica real del metodo, no del codigo.
    """
    if f0_hz <= 0 or c <= 0:
        raise ValueError("f0_hz y c deben ser positivos")
    if v_ms is None and doppler_shift_hz is None:
        raise ValueError("doppler_effect requiere v_ms o doppler_shift_hz")

    theta = np.radians(theta_deg)
    cos_theta = np.cos(theta)

    if v_ms is not None:
        v = v_ms
        delta_f = 2.0 * f0_hz * v * cos_theta / c
    else:
        delta_f = doppler_shift_hz
        if abs(cos_theta) < 1e-9:
            raise ValueError(
                "theta_deg=90 hace cos(theta)=0, no se puede despejar "
                "v_ms desde doppler_shift_hz"
            )
        v = delta_f * c / (2.0 * f0_hz * cos_theta)

    result = {
        "f0_hz": f0_hz,
        "c": c,
        "theta_deg": theta_deg,
        "v_ms": float(v),
        "doppler_shift_hz": float(delta_f),
        "direction": ("acercandose" if delta_f > 0 else
                      "alejandose" if delta_f < 0 else "sin movimiento radial"),
    }

    if prf_hz:
        v_nyquist = ((prf_hz / 2.0) * c / (2.0 * f0_hz * cos_theta)
                     if abs(cos_theta) > 1e-9 else float("inf"))
        result.update({
            "prf_hz": prf_hz,
            "nyquist_shift_hz": prf_hz / 2.0,
            "v_nyquist_ms": v_nyquist,
            "aliasing": abs(delta_f) > (prf_hz / 2.0),
        })

    return result


def cavitation_threshold(peak_negative_pressure_mpa: Optional[float] = None,
                          frequency_mhz: Optional[float] = None,
                          bubble_radius_m: Optional[float] = None,
                          surface_tension_nm: float = 0.072,
                          ambient_pressure_pa: float = 101325.0) -> Dict[str, Any]:
    """
    No existe una unica formula "canonica" de umbral de cavitacion -- depende
    de que modelo se elija. Se implementan DOS aproximaciones bien
    establecidas, devueltas por separado, sin mezclarlas:

    (a) Indice Mecanico (MI) -- el estandar clinico/regulatorio real
        (AIUM/NEMA, guia FDA). Empirico, no derivado de primeros
        principios: MI = p_neg_MPa / sqrt(f_MHz)
        Requiere peak_negative_pressure_mpa y frequency_mhz. Umbrales
        orientativos de literatura (NO limites fisicos exactos): MI<0.7 =
        riesgo bajo sin agente de contraste; MI>1.9 = limite regulatorio
        FDA para la mayoria de aplicaciones diagnosticas; con contraste
        ecografico el umbral baja a MI~0.1-0.4.

    (b) Umbral de Blake -- modelo fisico cuasi-estatico de una burbuja de
        gas esferica libre (Blake, 1949), con supuestos EXPLICITOS: gas
        isotermico (kappa=1 -- un gas adiabatico real da un valor algo
        distinto), cuasi-estatico (ignora inercia/Rayleigh-Plesset
        dinamico -- por eso NO depende de la frecuencia de excitacion),
        sin viscosidad ni difusion de gas, presion de vapor despreciada.
        Formula (rederivada por balance de presion cuasi-estatico en la
        pared de la burbuja, validada contra el limite asintotico clasico
        P_B -> P0 + 4*sigma/(3*sqrt(3)*R0) para R0 chico):
            P_g0 = P0 + 2*sigma/R0
            x = 2*sigma / (3*P_g0*R0)
            p_umbral = P0 + 2*P_g0*x^(3/2)
        Requiere bubble_radius_m (surface_tension_nm y ambient_pressure_pa
        tienen default de agua a 20°C / 1 atm).

    Da (a) y/o (b) segun los parametros dados; con ambos juegos, calcula
    los dos modelos.
    """
    result = {}

    if peak_negative_pressure_mpa is not None and frequency_mhz is not None:
        if frequency_mhz <= 0:
            raise ValueError("frequency_mhz debe ser positiva")
        mi = peak_negative_pressure_mpa / np.sqrt(frequency_mhz)
        result["mechanical_index"] = {
            "mi": float(mi),
            "peak_negative_pressure_mpa": peak_negative_pressure_mpa,
            "frequency_mhz": frequency_mhz,
            "risk_note": (
                "bajo (MI<0.7, sin contraste)" if mi < 0.7 else
                "sobre limite regulatorio FDA (MI>1.9)" if mi > 1.9 else
                "rango intermedio -- depende de tejido/aplicacion"
            ),
        }

    if bubble_radius_m is not None:
        if bubble_radius_m <= 0:
            raise ValueError("bubble_radius_m debe ser positivo")
        r0 = bubble_radius_m
        sigma = surface_tension_nm
        p0 = ambient_pressure_pa
        p_g0 = p0 + 2.0 * sigma / r0
        x = 2.0 * sigma / (3.0 * p_g0 * r0)
        p_threshold = p0 + 2.0 * p_g0 * (x ** 1.5)
        result["blake_threshold"] = {
            "bubble_radius_m": r0,
            "surface_tension_nm": sigma,
            "ambient_pressure_pa": p0,
            "threshold_pressure_amplitude_pa": float(p_threshold),
            "threshold_pressure_amplitude_mpa": float(p_threshold / 1e6),
            "assumptions": "gas isotermico (kappa=1), cuasi-estatico, sin viscosidad/difusion de gas",
        }

    if not result:
        raise ValueError(
            "cavitation_threshold requiere (peak_negative_pressure_mpa + "
            "frequency_mhz) para MI, y/o bubble_radius_m para umbral de Blake"
        )

    return result


def nonlinear_ultrasound(f0_hz: float, p0_pa: float, c0: float = 1540.0,
                          rho0: float = 1050.0, b_over_a: float = 5.0,
                          x_m: Optional[float] = None) -> Dict[str, Any]:
    """
    Generacion de armonicos en propagacion de ultrasonido de alta
    intensidad (base fisica de la imagenologia armonica). Regimen
    DEBILMENTE NO LINEAL, PRE-CHOQUE (solucion de Fubini, 1935) -- NO
    resuelve la ecuacion de Burgers completa ni modela la onda de choque
    saturada mas alla de la distancia de formacion de choque (para eso
    haria falta un solver numerico espectral o de diferencias finitas de
    Burgers, fuera de alcance aca).

    Parametro de no linealidad: beta = 1 + B/(2A)
        B/A tipico: agua ~5, tejido blando ~4-9 (default 5.0).

    Distancia de formacion de choque (onda plana, fuente sinusoidal):
        x_shock = rho0 * c0^3 / (beta * omega * p0)

    Segunda armonica (solucion de Fubini, valida solo para x < x_shock,
    sigma = x/x_shock < 1):
        p2(x) = p0 * (1/sigma) * J2(2*sigma)
    con J2 la funcion de Bessel de primera especie orden 2. Mas alla de
    x_shock el resultado se marca explicitamente como no valido (warning)
    en vez de devolver un numero enganoso.
    """
    if f0_hz <= 0 or p0_pa <= 0 or c0 <= 0 or rho0 <= 0:
        raise ValueError("f0_hz, p0_pa, c0 y rho0 deben ser positivos")

    omega = 2.0 * np.pi * f0_hz
    beta = 1.0 + b_over_a / 2.0
    x_shock = rho0 * c0 ** 3 / (beta * omega * p0_pa)

    result = {
        "f0_hz": f0_hz,
        "p0_pa": p0_pa,
        "c0": c0,
        "rho0": rho0,
        "b_over_a": b_over_a,
        "beta_nonlinearity": beta,
        "shock_formation_distance_m": float(x_shock),
        "regime": "Fubini (pre-choque, debilmente no lineal)",
    }

    if x_m is not None:
        if x_m < 0:
            raise ValueError("x_m no puede ser negativo")
        sigma = x_m / x_shock
        result["x_m"] = x_m
        result["sigma_normalized_distance"] = float(sigma)
        if sigma >= 1.0:
            result["warning"] = (
                "x_m >= x_shock: la solucion de Fubini ya no es valida "
                "(se formo onda de choque), este resultado es solo orientativo"
            )
        p2 = 0.0 if sigma < 1e-9 else p0_pa * (1.0 / sigma) * jv(2, 2.0 * sigma)
        result["second_harmonic_pressure_pa"] = float(p2)
        result["second_harmonic_ratio"] = float(p2 / p0_pa) if p0_pa != 0 else None

    return result


def _resolve_impedance(params: Dict[str, Any], side: str,
                        default_material: str) -> float:
    """side es '1' o '2'. Prioridad: Z{side}_rayl explicito > rho{side}/c{side}
    explicitos > material{side} (lookup en MATERIALS) > default_material."""
    z_key = f"Z{side}_rayl"
    if params.get(z_key) is not None:
        return params[z_key]
    rho_key, c_key, mat_key = f"rho{side}", f"c{side}", f"material{side}"
    material = params.get(mat_key, default_material)
    ref = MATERIALS.get(material, MATERIALS[default_material])
    rho = params.get(rho_key, ref["rho"])
    c = params.get(c_key, ref["c"])
    return acoustic_impedance(rho, c)


# ----------------------------------------------------------------------
# Dispatcher
# ----------------------------------------------------------------------

TOOL_NAME = "ultrasound_tool"
TOOL_MODES = [
    "interface_reflection",
    "attenuation",
    "time_of_flight",
    "pulse_echo_layers",
    "doppler_effect",
    "cavitation_threshold",
    "nonlinear_ultrasound",
    "validate",
]


def run(mode: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Dispatcher de ultrasound_tool.

    Modos:
      - interface_reflection: coeficientes R/T en una interfaz de impedancia
      - attenuation: amplitud remanente tras atenuacion dependiente de frecuencia
      - time_of_flight: convierte t_seconds<->distance_m para pulso-eco
      - pulse_echo_layers: simula ecos a traves de N capas consecutivas
      - doppler_effect: corrimiento de frecuencia por movimiento del reflector
      - cavitation_threshold: Indice Mecanico y/o umbral de Blake
      - nonlinear_ultrasound: generacion de 2do armonico (regimen Fubini)
      - validate: autochequeo
    """
    params = params or {}

    if mode == "interface_reflection":
        Z1 = _resolve_impedance(params, "1", "water")
        Z2 = _resolve_impedance(params, "2", "soft_tissue")
        result = reflection_transmission(Z1, Z2)
        result["mode"] = mode
        return result

    elif mode == "attenuation":
        result = amplitude_after_distance(
            A0=params.get("A0", 1.0),
            distance_m=params.get("distance_m", 0.05),
            freq_mhz=params.get("freq_mhz", 5.0),
            alpha_db_cm_mhz=params.get("alpha_db_cm_mhz", 0.5),
            power=params.get("power", 1.0),
        )
        result["mode"] = mode
        return result

    elif mode == "time_of_flight":
        if "t_seconds" in params:
            result = time_of_flight_to_distance(
                t_seconds=params["t_seconds"],
                c=params.get("c", 1540.0),
                pulse_echo=params.get("pulse_echo", True),
            )
        elif "distance_m" in params:
            result = distance_to_time_of_flight(
                distance_m=params["distance_m"],
                c=params.get("c", 1540.0),
                pulse_echo=params.get("pulse_echo", True),
            )
        else:
            raise ValueError(
                "time_of_flight requiere 't_seconds' o 'distance_m' en params"
            )
        result["mode"] = mode
        return result

    elif mode == "pulse_echo_layers":
        layers = params.get("layers")
        if not layers:
            raise ValueError(
                "pulse_echo_layers requiere 'layers': lista de "
                "{name?, rho, c, thickness_m}, minimo 2 capas"
            )
        result = pulse_echo_layers(
            layers=layers,
            freq_mhz=params.get("freq_mhz", 5.0),
            A0=params.get("A0", 1.0),
            alpha_db_cm_mhz=params.get("alpha_db_cm_mhz", 0.5),
            power=params.get("power", 1.0),
        )
        result["mode"] = mode
        return result

    elif mode == "doppler_effect":
        result = doppler_effect(
            f0_hz=params["f0_hz"],
            c=params.get("c", 1540.0),
            theta_deg=params.get("theta_deg", 0.0),
            v_ms=params.get("v_ms"),
            doppler_shift_hz=params.get("doppler_shift_hz"),
            prf_hz=params.get("prf_hz"),
        )
        result["mode"] = mode
        return result

    elif mode == "cavitation_threshold":
        result = cavitation_threshold(
            peak_negative_pressure_mpa=params.get("peak_negative_pressure_mpa"),
            frequency_mhz=params.get("frequency_mhz"),
            bubble_radius_m=params.get("bubble_radius_m"),
            surface_tension_nm=params.get("surface_tension_nm", 0.072),
            ambient_pressure_pa=params.get("ambient_pressure_pa", 101325.0),
        )
        result["mode"] = mode
        return result

    elif mode == "nonlinear_ultrasound":
        result = nonlinear_ultrasound(
            f0_hz=params["f0_hz"],
            p0_pa=params["p0_pa"],
            c0=params.get("c0", 1540.0),
            rho0=params.get("rho0", 1050.0),
            b_over_a=params.get("b_over_a", 5.0),
            x_m=params.get("x_m"),
        )
        result["mode"] = mode
        return result

    elif mode == "validate":
        n_passed, checks = validate()
        n_total = 13
        return {
            "validation_passed": n_passed == n_total,
            "passed": n_passed,
            "total": n_total,
            "checks": checks,
            "mode": mode,
        }

    else:
        return {"error": f"Modo desconocido: {mode}"}


TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Fisica de ultrasonido complementaria a acoustics_tool: impedancia "
        "acustica y reflexion/transmision en interfaces (Z=rho*c, "
        "R=(Z2-Z1)/(Z2+Z1)), atenuacion dependiente de frecuencia (ley de "
        "potencia, tipico ~0.3-1.0 dB/cm/MHz en tejido blando), conversion "
        "tiempo de vuelo<->distancia para pulso-eco, y simulacion de "
        "pulso-eco a traves de multiples capas (util para medicion de "
        "espesor / imagenologia simple por eco), efecto Doppler pulso-eco "
        "(flujo/movimiento del reflector), umbral de cavitacion (Indice "
        "Mecanico clinico y/o umbral fisico de Blake) y generacion de 2do "
        "armonico en propagacion no lineal (regimen Fubini pre-choque). "
        "No reemplaza el solver FDTD de pressure_wave_1d en acoustics_tool."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": TOOL_MODES,
                "description": "Modo de calculo (ver docstring de run())",
            },
            "params": {
                "type": "object",
                "description": (
                    "interface_reflection: {Z1_rayl?, Z2_rayl?, material1?, "
                    "material2?, rho1?, c1?, rho2?, c2?} (material en "
                    "['air','water','soft_tissue','fat','muscle','bone',"
                    "'steel']) | "
                    "attenuation: {A0?, distance_m?, freq_mhz?, "
                    "alpha_db_cm_mhz?, power?} | "
                    "time_of_flight: {t_seconds? | distance_m?, c?, "
                    "pulse_echo?} | "
                    "pulse_echo_layers: {layers:[{name?, rho, c, "
                    "thickness_m}, ...], freq_mhz?, A0?, alpha_db_cm_mhz?, "
                    "power?} | "
                    "doppler_effect: {f0_hz, c?, theta_deg?, v_ms? | "
                    "doppler_shift_hz?, prf_hz?} (dar v_ms O "
                    "doppler_shift_hz) | "
                    "cavitation_threshold: {peak_negative_pressure_mpa? + "
                    "frequency_mhz? (Indice Mecanico), bubble_radius_m? "
                    "(umbral de Blake), surface_tension_nm?, "
                    "ambient_pressure_pa?} | "
                    "nonlinear_ultrasound: {f0_hz, p0_pa, c0?, rho0?, "
                    "b_over_a?, x_m?}"
                ),
            },
        },
        "required": ["mode"],
    },
}


# ----------------------------------------------------------------------
# Self-tests
# ----------------------------------------------------------------------

def validate():
    """13 self-tests para modo=validate. Devuelve (n_passed, checks)."""
    checks = []
    tests_passed = 0

    def check(name, passed, detail=""):
        nonlocal tests_passed
        passed = bool(passed)
        checks.append({"name": name, "passed": passed, "detail": detail})
        if passed:
            tests_passed += 1
        else:
            print(f"  ✗ {name}: {detail}")

    # Test 1: impedancia del agua
    try:
        Z = acoustic_impedance(1000.0, 1480.0)
        check("impedancia_agua", abs(Z - 1.48e6) < 1.0, f"Z={Z}")
    except Exception as e:
        check("impedancia_agua", False, str(e))

    # Test 2: interfaz agua-aire, reflexion casi total
    try:
        Z_water = acoustic_impedance(1000.0, 1480.0)
        Z_air = acoustic_impedance(1.2, 343.0)
        rt = reflection_transmission(Z_water, Z_air)
        check("reflexion_agua_aire_casi_total",
              abs(rt["pressure_reflection_coeff"]) > 0.99,
              f"R={rt['pressure_reflection_coeff']:.4f}")
    except Exception as e:
        check("reflexion_agua_aire_casi_total", False, str(e))

    # Test 3: interfaz mismo medio -> sin reflexion
    try:
        Z = acoustic_impedance(1000.0, 1480.0)
        rt = reflection_transmission(Z, Z)
        ok = (abs(rt["pressure_reflection_coeff"]) < 1e-9
              and abs(rt["pressure_transmission_coeff"] - 1.0) < 1e-9)
        check("interfaz_mismo_medio_sin_reflexion", ok,
              f"R={rt['pressure_reflection_coeff']}, T={rt['pressure_transmission_coeff']}")
    except Exception as e:
        check("interfaz_mismo_medio_sin_reflexion", False, str(e))

    # Test 4: conservacion de energia (R_intensity + T_intensity = 1)
    try:
        Z1 = acoustic_impedance(1050.0, 1540.0)
        Z2 = acoustic_impedance(1900.0, 4080.0)
        rt = reflection_transmission(Z1, Z2)
        total = rt["intensity_reflection_coeff"] + rt["intensity_transmission_coeff"]
        check("conservacion_energia_interfaz", abs(total - 1.0) < 1e-9,
              f"suma={total}")
    except Exception as e:
        check("conservacion_energia_interfaz", False, str(e))

    # Test 5: atenuacion aumenta con la frecuencia
    try:
        low = amplitude_after_distance(1.0, 0.05, freq_mhz=1.0)
        high = amplitude_after_distance(1.0, 0.05, freq_mhz=10.0)
        check("atenuacion_aumenta_con_frecuencia",
              high["amplitude_final"] < low["amplitude_final"],
              f"A(1MHz)={low['amplitude_final']:.4f} A(10MHz)={high['amplitude_final']:.4f}")
    except Exception as e:
        check("atenuacion_aumenta_con_frecuencia", False, str(e))

    # Test 6: atenuacion a distancia 0 no cambia la amplitud
    try:
        result = amplitude_after_distance(2.0, 0.0, freq_mhz=5.0)
        check("atenuacion_distancia_cero", abs(result["amplitude_final"] - 2.0) < 1e-9,
              f"A={result['amplitude_final']}")
    except Exception as e:
        check("atenuacion_distancia_cero", False, str(e))

    # Test 7: time_of_flight ida-y-vuelta consistente
    try:
        d = distance_to_time_of_flight(0.05, 1540.0, pulse_echo=True)
        back = time_of_flight_to_distance(d["t_seconds"], 1540.0, pulse_echo=True)
        check("time_of_flight_roundtrip_consistente",
              abs(back["distance_m"] - 0.05) < 1e-9,
              f"distancia recuperada={back['distance_m']}")
    except Exception as e:
        check("time_of_flight_roundtrip_consistente", False, str(e))

    # Test 8: pulse_echo_layers detecta la interfaz a la profundidad correcta
    try:
        layers = [
            {"name": "water", "rho": 1000.0, "c": 1480.0, "thickness_m": 0.03},
            {"name": "tissue", "rho": 1050.0, "c": 1540.0, "thickness_m": 0.02},
        ]
        result = pulse_echo_layers(layers, freq_mhz=5.0)
        ok = (len(result["echoes"]) == 1
              and abs(result["echoes"][0]["depth_m"] - 0.03) < 1e-9)
        check("pulse_echo_profundidad_correcta", ok, f"echoes={result['echoes']}")
    except Exception as e:
        check("pulse_echo_profundidad_correcta", False, str(e))

    # Test 9: pulse_echo_layers exige minimo 2 capas
    try:
        raised = False
        try:
            pulse_echo_layers(
                [{"rho": 1000.0, "c": 1480.0, "thickness_m": 0.01}],
                freq_mhz=5.0,
            )
        except ValueError:
            raised = True
        check("pulse_echo_minimo_2_capas", raised, "ValueError esperado con 1 capa")
    except Exception as e:
        check("pulse_echo_minimo_2_capas", False, str(e))

    # Test 10: serializable a JSON
    try:
        result = run("interface_reflection",
                      {"material1": "water", "material2": "soft_tissue"})
        json_str = json.dumps(result, default=str)
        check("json_serializable", len(json_str) > 0, "")
    except Exception as e:
        check("json_serializable", False, str(e))

    # Test 11: doppler_effect roundtrip v->shift->v (pulso-eco, factor 2)
    try:
        f0 = 5e6
        r1 = doppler_effect(f0_hz=f0, v_ms=0.5, theta_deg=60.0, c=1540.0)
        r2 = doppler_effect(f0_hz=f0, doppler_shift_hz=r1["doppler_shift_hz"],
                             theta_deg=60.0, c=1540.0)
        diff = abs(r2["v_ms"] - 0.5)
        check("doppler_effect_roundtrip", diff < 1e-9, f"diff={diff}")
    except Exception as e:
        check("doppler_effect_roundtrip", False, str(e))

    # Test 12: cavitation_threshold, MI exacto (1/sqrt(3)) + umbral de
    # Blake convergiendo a su forma asintotica clasica para R0 chico
    # (P_B -> P0 + 4*sigma/(3*sqrt(3)*R0), <1% de diff esperado)
    try:
        r_mi = cavitation_threshold(peak_negative_pressure_mpa=1.0, frequency_mhz=3.0)
        mi_expected = 1.0 / np.sqrt(3.0)
        mi_diff = abs(r_mi["mechanical_index"]["mi"] - mi_expected)

        sigma, r0, p0 = 0.072, 1e-8, 101325.0
        r_blake = cavitation_threshold(bubble_radius_m=r0, surface_tension_nm=sigma,
                                        ambient_pressure_pa=p0)
        asym = p0 + 4.0 * sigma / (3.0 * np.sqrt(3.0) * r0)
        reldiff = abs(r_blake["blake_threshold"]["threshold_pressure_amplitude_pa"] - asym) / asym

        check("cavitation_threshold_mi_y_blake", mi_diff < 1e-9 and reldiff < 0.01,
              f"MI_diff={mi_diff:.2e}, blake_reldiff={reldiff:.4f}")
    except Exception as e:
        check("cavitation_threshold_mi_y_blake", False, str(e))

    # Test 13: nonlinear_ultrasound, limite lineal de Fubini (sigma chico)
    # y warning explicito mas alla de la distancia de choque
    try:
        r_small = nonlinear_ultrasound(f0_hz=3e6, p0_pa=1e6, x_m=0.001)
        r_smaller = nonlinear_ultrasound(f0_hz=3e6, p0_pa=1e6, x_m=0.0005)
        ratio_x = r_small["x_m"] / r_smaller["x_m"]
        ratio_p2 = (r_small["second_harmonic_pressure_pa"] /
                    r_smaller["second_harmonic_pressure_pa"])
        linear_ok = abs(ratio_x - ratio_p2) < 0.05

        r_post = nonlinear_ultrasound(f0_hz=3e6, p0_pa=1e6,
                                       x_m=r_small["shock_formation_distance_m"] * 1.5)
        warning_ok = "warning" in r_post

        check("nonlinear_ultrasound_fubini_regimen", linear_ok and warning_ok,
              f"ratio_x={ratio_x:.4f}, ratio_p2={ratio_p2:.4f}, warning_ok={warning_ok}")
    except Exception as e:
        check("nonlinear_ultrasound_fubini_regimen", False, str(e))

    return tests_passed, checks


def _register():
    try:
        from tool_registry import register_tool
        register_tool(
            TOOL_NAME,
            TOOL_SCHEMA,
            lambda args: run(args.get("mode"), args.get("params", {})),
        )
    except ImportError:
        pass


_register()


if __name__ == "__main__":
    print("=" * 70)
    print("ultrasound_tool.py - SELF-TESTS")
    print("=" * 70)

    passed, checks = validate()
    total = 13

    print(f"\n✓ PASSED: {passed}/{total}")
    if passed == total:
        print("→ LISTO PARA INTEGRAR a octave-mcp/tools/")
    else:
        print(f"→ {total - passed} test(s) fallaron — revisar")
