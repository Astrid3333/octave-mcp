#!/usr/bin/env python3
"""
electromagnetic_tool.py -- electromagnetic_tool para octave-mcp

Modos:
  - wave_1d          : FDTD leapfrog (Yee) de un pulso E_z/H_y en 1D,
                        con condiciones de borde PEC (E=0 en el borde).
  - photonic_bandgap : metodo de matriz de transferencia (TMM) para un
                        cristal fotonico 1D (apilado periodico n1/n2),
                        deteccion de band gaps via condicion de Bloch
                        |Tr(M)/2| > 1.
  - waveguide_modes   : modos TE/TM y frecuencias de corte de una guia
                        de onda rectangular metalica hueca (paredes PEC).
  - polarization_state: elipse de polarizacion (Stokes, orientacion,
                        elipticidad, mano) de una onda plana totalmente
                        polarizada.
  - validate         : corre los 4 self-tests y devuelve JSON con
                        validation_passed.

Unidades:
  wave_1d trabaja en unidades normalizadas de rejilla (c=1, dx=1).
  photonic_bandgap, waveguide_modes y polarization_state trabajan en
  unidades fisicas (Hz, metros, c=299792458 m/s).
"""

import json
import numpy as np

C0 = 299792458.0  # m/s


# ---------------------------------------------------------------------
# wave_1d: FDTD leapfrog 1D con borde PEC
# ---------------------------------------------------------------------

def _run_fdtd_1d(nx, nt, courant, eps_r, src_pos, src_width, pec=True):
    dx = 1.0
    dt = courant * dx
    Ez = np.zeros(nx)
    Hy = np.zeros(nx - 1)
    Ez_hist = np.zeros((nt, nx))

    for n in range(nt):
        t0 = 3.0 * src_width
        pulse = np.exp(-((n * dt - t0) ** 2) / (2.0 * src_width ** 2))
        Ez[src_pos] += pulse

        Hy += (dt / dx) * (Ez[1:] - Ez[:-1])
        Ez[1:-1] += (dt / dx) * (Hy[1:] - Hy[:-1]) / eps_r[1:-1]

        if pec:
            Ez[0] = 0.0
            Ez[-1] = 0.0

        Ez_hist[n, :] = Ez

    return Ez_hist


def wave_1d(params):
    nx = int(params.get("nx", 400))
    nt = int(params.get("nt", 1000))
    courant = float(params.get("courant", 0.5))
    src_width = float(params.get("src_width", 15.0))

    eps_r = np.ones(nx)
    src_pos = nx // 2
    hist = _run_fdtd_1d(nx, nt, courant, eps_r, src_pos, src_width, pec=True)

    t1 = int(6 * src_width / courant)
    t2 = t1 + max(20, nx // 4)
    lo = src_pos + 3
    peak1 = lo + int(np.argmax(np.abs(hist[t1, lo:])))
    peak2 = lo + int(np.argmax(np.abs(hist[t2, lo:])))
    dx_cells = peak2 - peak1
    dt_steps = t2 - t1
    v_measured = dx_cells / dt_steps
    v_expected = courant
    speed_error_pct = abs(v_measured / v_expected - 1.0) * 100.0

    probe = src_pos - nx // 4
    trace = hist[:, probe]
    idx1 = int(np.argmax(np.abs(trace[: nt // 2])))
    sign1 = float(np.sign(trace[idx1]))
    amp1 = float(np.abs(trace[idx1]))
    idx2 = idx1 + 5 + int(np.argmax(np.abs(trace[idx1 + 5:])))
    sign2 = float(np.sign(trace[idx2]))
    amp2 = float(np.abs(trace[idx2]))

    sign_flipped = bool(sign2 == -sign1)
    amplitude_ratio = float(amp2 / amp1) if amp1 > 0 else float("nan")

    passed = bool(speed_error_pct < 5.0 and sign_flipped and 0.3 < amplitude_ratio < 3.0)

    return {
        "free_space_speed": {
            "measured_cells_per_step": round(float(v_measured), 4),
            "expected_cells_per_step": round(float(v_expected), 4),
            "error_pct": round(float(speed_error_pct), 4),
        },
        "pec_reflection": {
            "direct_pulse_sign": int(sign1),
            "reflected_pulse_sign": int(sign2),
            "sign_flipped_as_expected": sign_flipped,
            "amplitude_ratio_reflected_vs_direct": round(amplitude_ratio, 4),
        },
        "passed": passed,
    }


# ---------------------------------------------------------------------
# photonic_bandgap: matriz de transferencia (TMM) para cristal fotonico 1D
# ---------------------------------------------------------------------

def _layer_matrix(n, d, freq):
    k0 = 2.0 * np.pi * freq / C0
    phi = n * k0 * d
    return np.array([
        [np.cos(phi), 1j * np.sin(phi) / n],
        [1j * n * np.sin(phi), np.cos(phi)],
    ])


def _unit_cell_matrix(n1, d1, n2, d2, freq):
    return _layer_matrix(n2, d2, freq) @ _layer_matrix(n1, d1, freq)


def photonic_bandgap(params):
    f0 = float(params.get("f0_hz", 3.0e14))
    n1 = float(params.get("n1", 3.5))
    n2 = float(params.get("n2", 1.45))
    n_scan = int(params.get("n_scan", 4000))
    f_range = float(params.get("f_range_frac", 0.6))

    d1 = C0 / (4.0 * n1 * f0)
    d2 = C0 / (4.0 * n2 * f0)

    freqs = np.linspace(f0 * (1 - f_range), f0 * (1 + f_range), n_scan)
    trace_half = np.zeros(n_scan)
    for i, f in enumerate(freqs):
        M = _unit_cell_matrix(n1, d1, n2, d2, f)
        trace_half[i] = float(np.real(np.trace(M)) / 2.0)

    in_gap = np.abs(trace_half) > 1.0

    if not np.any(in_gap):
        return {
            "design_frequency_hz": f0,
            "gap_found": False,
            "passed": False,
            "note": "No se encontro band gap en el rango escaneado",
        }

    f0_idx = int(np.argmin(np.abs(freqs - f0)))
    f0_in_gap = bool(in_gap[f0_idx])

    if f0_in_gap:
        lo, hi = f0_idx, f0_idx
        while lo > 0 and in_gap[lo - 1]:
            lo -= 1
        while hi < n_scan - 1 and in_gap[hi + 1]:
            hi += 1
    else:
        gap_idx = np.where(in_gap)[0]
        nearest = gap_idx[np.argmin(np.abs(gap_idx - f0_idx))]
        lo, hi = nearest, nearest
        while lo > 0 and in_gap[lo - 1]:
            lo -= 1
        while hi < n_scan - 1 and in_gap[hi + 1]:
            hi += 1

    gap_lo_hz = float(freqs[lo])
    gap_hi_hz = float(freqs[hi])
    gap_center_hz = 0.5 * (gap_lo_hz + gap_hi_hz)
    center_error_pct = abs(gap_center_hz - f0) / f0 * 100.0

    passed = bool(f0_in_gap and center_error_pct < 1.0)

    return {
        "design_frequency_hz": f0,
        "layer_thicknesses_m": {"d1": d1, "d2": d2},
        "gap_found": True,
        "gap_range_hz": [gap_lo_hz, gap_hi_hz],
        "gap_center_hz": gap_center_hz,
        "f0_inside_gap": f0_in_gap,
        "center_vs_f0_error_pct": round(center_error_pct, 4),
        "passed": passed,
    }


# ---------------------------------------------------------------------
# waveguide_modes: guia de onda rectangular metalica hueca, modos TE/TM
# ---------------------------------------------------------------------

def _te_tm_cutoff_hz(m, n, a, b):
    """Frecuencia de corte f_c de un modo TE_mn o TM_mn en guia rectangular
    hueca de dimensiones a (ancho, eje x) x b (alto, eje y), a>b estandar.
    Formula identica para TE y TM (para TM se requiere m>=1 y n>=1)."""
    return (C0 / 2.0) * np.sqrt((m / a) ** 2 + (n / b) ** 2)


def waveguide_modes(params):
    """
    Guia de onda rectangular metalica hueca (paredes PEC), dimensiones
    a x b (a = lado ancho, b = lado angosto, convencion a > b).

    Parametros:
      a_m         : dimension ancha en metros (default 0.02286 m, WR-90 banda X)
      b_m         : dimension angosta en metros (default 0.01016 m, WR-90)
      m_max, n_max: indices maximos a barrer (default 3)
      f_operating_hz: si se da, marca que modos propagan (fc < f_operating)

    Modos TE_mn existen para todo (m,n) != (0,0). Modos TM_mn requieren
    m>=1 y n>=1 (TM_m0 y TM_0n no existen fisicamente). El modo dominante
    de una guia estandar (a>b>0) es TE10, con f_c = c/(2a) exacto (no
    depende de b) -- este es el valor validado contra teoria analitica.
    """
    a = float(params.get("a_m", 0.02286))
    b = float(params.get("b_m", 0.01016))
    m_max = int(params.get("m_max", 3))
    n_max = int(params.get("n_max", 3))
    f_op = params.get("f_operating_hz", None)

    modes = []
    for m in range(0, m_max + 1):
        for n in range(0, n_max + 1):
            if m == 0 and n == 0:
                continue
            fc = _te_tm_cutoff_hz(m, n, a, b)
            modes.append({"type": "TE", "m": m, "n": n, "fc_hz": fc})
            if m >= 1 and n >= 1:
                modes.append({"type": "TM", "m": m, "n": n, "fc_hz": fc})
    modes.sort(key=lambda d: d["fc_hz"])

    dominant = modes[0]

    fc_te10_expected = C0 / (2.0 * a)
    fc_te10_actual = next(
        d["fc_hz"] for d in modes if d["type"] == "TE" and d["m"] == 1 and d["n"] == 0
    )
    te10_error_pct = abs(fc_te10_actual / fc_te10_expected - 1.0) * 100.0

    dominant_is_te10 = bool(
        dominant["type"] == "TE" and dominant["m"] == 1 and dominant["n"] == 0
    )
    passed = bool(te10_error_pct < 1e-6 and dominant_is_te10)

    result = {
        "a_m": a, "b_m": b,
        "dominant_mode": dominant,
        "te10_cutoff_check": {
            "expected_hz": fc_te10_expected,
            "actual_hz": fc_te10_actual,
            "error_pct": te10_error_pct,
        },
        "modes": modes,
        "passed": passed,
    }

    if f_op is not None:
        f_op = float(f_op)
        propagating = [d for d in modes if d["fc_hz"] < f_op]
        result["f_operating_hz"] = f_op
        result["propagating_modes"] = propagating
        result["single_mode_operation"] = bool(
            len(propagating) == 1 and propagating[0]["type"] == "TE"
            and propagating[0]["m"] == 1 and propagating[0]["n"] == 0
        )

    return result


# ---------------------------------------------------------------------
# polarization_state: elipse de polarizacion via parametros de Stokes
# ---------------------------------------------------------------------

def polarization_state(params):
    """
    Estado de polarizacion de una onda plana totalmente polarizada, a
    partir de las amplitudes Ex, Ey y la diferencia de fase delta =
    fase_y - fase_x (convencion E_x(t)=Ex*cos(wt), E_y(t)=Ey*cos(wt+delta)).

    Calcula los parametros de Stokes:
      S0 = Ex^2+Ey^2                (intensidad total)
      S1 = Ex^2-Ey^2                (preferencia lineal H/V)
      S2 = 2*Ex*Ey*cos(delta)       (preferencia lineal +-45)
      S3 = 2*Ex*Ey*sin(delta)       (preferencia circular)

    y de ahi el angulo de orientacion de la elipse psi = 0.5*atan2(S2,S1)
    y el angulo de elipticidad chi = 0.5*arcsin(S3/S0) (chi=0 => lineal,
    chi=+-45 deg => circular, signo de chi define la mano segun convencion
    de mirar la onda de frente contra su direccion de propagacion).

    Validado contra 3 casos canonicos:
      - lineal horizontal (Ex=1,Ey=0)         -> chi=0, S3=0
      - lineal a 45 grados (Ex=1,Ey=1,d=0)     -> psi=45 deg, chi=0
      - circular (Ex=1,Ey=1,d=90 deg)          -> |chi|=45 deg, S2=0
    y contra la identidad de luz totalmente polarizada S0^2=S1^2+S2^2+S3^2.
    """
    Ex = float(params.get("Ex", 1.0))
    Ey = float(params.get("Ey", 0.0))
    delta_deg = float(params.get("delta_deg", 0.0))
    delta = np.radians(delta_deg)

    S0 = Ex ** 2 + Ey ** 2
    S1 = Ex ** 2 - Ey ** 2
    S2 = 2 * Ex * Ey * np.cos(delta)
    S3 = 2 * Ex * Ey * np.sin(delta)

    identity_err = abs(S0 ** 2 - (S1 ** 2 + S2 ** 2 + S3 ** 2))

    psi_deg = float(np.degrees(0.5 * np.arctan2(S2, S1))) if S0 > 0 else 0.0
    chi_deg = float(np.degrees(0.5 * np.arcsin(np.clip(S3 / S0, -1.0, 1.0)))) if S0 > 0 else 0.0

    if abs(chi_deg) < 1e-6:
        pol_type = "lineal"
        handedness = "n/a"
    elif abs(abs(chi_deg) - 45.0) < 1e-6:
        pol_type = "circular"
        handedness = "izquierda (S3>0)" if S3 > 0 else "derecha (S3<0)"
    else:
        pol_type = "eliptica"
        handedness = "izquierda (S3>0)" if S3 > 0 else "derecha (S3<0)"

    result = {
        "Ex": Ex, "Ey": Ey, "delta_deg": delta_deg,
        "stokes": {"S0": float(S0), "S1": float(S1), "S2": float(S2), "S3": float(S3)},
        "fully_polarized_identity_err": float(identity_err),
        "orientation_angle_deg": psi_deg,
        "ellipticity_angle_deg": chi_deg,
        "polarization_type": pol_type,
        "handedness": handedness,
    }

    if params.get("_run_selftest", False):
        c1 = polarization_state({"Ex": 1.0, "Ey": 0.0, "delta_deg": 0.0})
        chk_linear_h = bool(abs(c1["ellipticity_angle_deg"]) < 1e-6 and abs(c1["stokes"]["S3"]) < 1e-9)

        c2 = polarization_state({"Ex": 1.0, "Ey": 1.0, "delta_deg": 0.0})
        chk_linear_45 = bool(abs(c2["orientation_angle_deg"] - 45.0) < 1e-6 and abs(c2["ellipticity_angle_deg"]) < 1e-6)

        c3 = polarization_state({"Ex": 1.0, "Ey": 1.0, "delta_deg": 90.0})
        chk_circular = bool(abs(abs(c3["ellipticity_angle_deg"]) - 45.0) < 1e-6 and abs(c3["stokes"]["S2"]) < 1e-9)

        chk_identity = bool(identity_err < 1e-9)

        result["selftest"] = {
            "linear_horizontal_ok": chk_linear_h,
            "linear_45deg_ok": chk_linear_45,
            "circular_ok": chk_circular,
            "fully_polarized_identity_ok": chk_identity,
        }
        result["passed"] = bool(chk_linear_h and chk_linear_45 and chk_circular and chk_identity)

    return result


# ---------------------------------------------------------------------
# validate: corre los 4 self-tests
# ---------------------------------------------------------------------

def validate(params=None):
    params = params or {}
    r_wave = wave_1d(params.get("wave_1d", {}))
    r_bandgap = photonic_bandgap(params.get("photonic_bandgap", {}))
    r_waveguide = waveguide_modes(params.get("waveguide_modes", {}))
    r_polarization = polarization_state({"_run_selftest": True, **params.get("polarization_state", {})})
    validation_passed = bool(
        r_wave["passed"] and r_bandgap["passed"]
        and r_waveguide["passed"] and r_polarization["passed"]
    )
    return {
        "wave_1d": r_wave,
        "photonic_bandgap": r_bandgap,
        "waveguide_modes": r_waveguide,
        "polarization_state": r_polarization,
        "validation_passed": validation_passed,
    }


# ---------------------------------------------------------------------
# schema + dispatcher del tool (mismo patron que acoustics_tool)
# ---------------------------------------------------------------------

ELECTROMAGNETIC_TOOL_SCHEMA = {
    "name": "electromagnetic_tool",
    "description": (
        "Simulaciones electromagneticas: propagacion de onda E/H via FDTD "
        "leapfrog con bordes PEC (mode='wave_1d'), deteccion de band gaps "
        "en cristales fotonicos 1D via matriz de transferencia y condicion "
        "de Bloch (mode='photonic_bandgap'), modos TE/TM y frecuencias de "
        "corte en guia de onda rectangular metalica (mode='waveguide_modes'), "
        "y elipse de polarizacion via parametros de Stokes de una onda plana "
        "(mode='polarization_state'). mode='validate' corre los 4 self-tests "
        "contra resultados analiticos conocidos."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["wave_1d", "photonic_bandgap", "waveguide_modes", "polarization_state", "validate"],
            },
            "nx": {"type": "integer", "description": "Celdas de rejilla (wave_1d)"},
            "nt": {"type": "integer", "description": "Pasos temporales (wave_1d)"},
            "courant": {"type": "number", "description": "Numero de Courant S=c*dt/dx, <=1 (wave_1d)"},
            "src_width": {"type": "number", "description": "Ancho temporal del pulso gaussiano (wave_1d)"},
            "f0_hz": {"type": "number", "description": "Frecuencia de diseno del apilado (photonic_bandgap)"},
            "n1": {"type": "number", "description": "Indice de refraccion capa alta (photonic_bandgap)"},
            "n2": {"type": "number", "description": "Indice de refraccion capa baja (photonic_bandgap)"},
            "a_m": {"type": "number", "description": "Dimension ancha de la guia en metros (waveguide_modes)"},
            "b_m": {"type": "number", "description": "Dimension angosta de la guia en metros (waveguide_modes)"},
            "m_max": {"type": "integer", "description": "Indice m maximo a barrer (waveguide_modes)"},
            "n_max": {"type": "integer", "description": "Indice n maximo a barrer (waveguide_modes)"},
            "f_operating_hz": {"type": "number", "description": "Frecuencia de operacion, para listar modos propagantes (waveguide_modes)"},
            "Ex": {"type": "number", "description": "Amplitud de campo en x (polarization_state)"},
            "Ey": {"type": "number", "description": "Amplitud de campo en y (polarization_state)"},
            "delta_deg": {"type": "number", "description": "Diferencia de fase fase_y-fase_x en grados (polarization_state)"},
        },
        "required": ["mode"],
    },
}


def handle_electromagnetic_tool(arguments):
    mode = arguments.get("mode", "validate")
    if mode == "wave_1d":
        result = wave_1d(arguments)
    elif mode == "photonic_bandgap":
        result = photonic_bandgap(arguments)
    elif mode == "waveguide_modes":
        result = waveguide_modes(arguments)
    elif mode == "polarization_state":
        result = polarization_state(arguments)
    elif mode == "validate":
        result = validate(arguments)
    else:
        return {"error": f"modo desconocido: {mode}"}
    result["mode"] = mode
    return result


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
