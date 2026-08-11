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
  - validate         : corre ambos self-tests y devuelve JSON con
                        validation_passed.

Unidades:
  wave_1d trabaja en unidades normalizadas de rejilla (c=1, dx=1).
  photonic_bandgap trabaja en unidades fisicas (Hz, metros, c=299792458 m/s).
"""

import json
import numpy as np

C0 = 299792458.0  # m/s


# ---------------------------------------------------------------------
# wave_1d: FDTD leapfrog 1D con borde PEC
# ---------------------------------------------------------------------

def _run_fdtd_1d(nx, nt, courant, eps_r, src_pos, src_width, pec=True):
    """Yee 1D FDTD. Retorna el historial completo de E_z (nt x nx)."""
    dx = 1.0
    dt = courant * dx  # c=1
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
    """
    Valida dos cosas contra teoria analitica:
      (a) velocidad de propagacion de un pulso en espacio libre: debe
          avanzar 'courant' celdas por paso (c=1, dx=1, dt=courant*dx).
      (b) reflexion en un borde PEC: el pulso reflejado debe volver
          por el mismo punto de referencia con el signo invertido
          (condicion de Dirichlet E=0 en el borde).
    """
    nx = int(params.get("nx", 400))
    nt = int(params.get("nt", 1000))
    courant = float(params.get("courant", 0.5))
    src_width = float(params.get("src_width", 15.0))

    eps_r = np.ones(nx)
    src_pos = nx // 2
    hist = _run_fdtd_1d(nx, nt, courant, eps_r, src_pos, src_width, pec=True)

    # (a) velocidad en espacio libre, lejos de cualquier borde
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

    # (b) reflexion PEC: signo invertido al volver a pasar por un probe
    #     a la izquierda de la fuente (rebota en el borde izquierdo)
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
    """Matriz caracteristica (convencion Born & Wolf) de una capa homogenea."""
    k0 = 2.0 * np.pi * freq / C0
    phi = n * k0 * d
    return np.array([
        [np.cos(phi), 1j * np.sin(phi) / n],
        [1j * n * np.sin(phi), np.cos(phi)],
    ])


def _unit_cell_matrix(n1, d1, n2, d2, freq):
    return _layer_matrix(n2, d2, freq) @ _layer_matrix(n1, d1, freq)


def photonic_bandgap(params):
    """
    Apilado periodico de cuarto de onda (n1 alto, n2 bajo) disenado
    para tener un band gap centrado en f0. Escanea frecuencia, calcula
    Tr(M)/2 por celda unidad; |Tr/2| > 1 => banda prohibida (condicion
    de Bloch no satisfecha por K real).
    """
    f0 = float(params.get("f0_hz", 3.0e14))
    n1 = float(params.get("n1", 3.5))   # ej. Si
    n2 = float(params.get("n2", 1.45))  # ej. SiO2
    n_scan = int(params.get("n_scan", 4000))
    f_range = float(params.get("f_range_frac", 0.6))

    d1 = C0 / (4.0 * n1 * f0)  # cuarto de onda a f0
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
# validate: corre ambos self-tests
# ---------------------------------------------------------------------

def validate(params=None):
    params = params or {}
    r_wave = wave_1d(params.get("wave_1d", {}))
    r_bandgap = photonic_bandgap(params.get("photonic_bandgap", {}))
    validation_passed = bool(r_wave["passed"] and r_bandgap["passed"])
    return {
        "wave_1d": r_wave,
        "photonic_bandgap": r_bandgap,
        "validation_passed": validation_passed,
    }


# ---------------------------------------------------------------------
# schema + dispatcher del tool (mismo patron que acoustics_tool)
# ---------------------------------------------------------------------

ELECTROMAGNETIC_TOOL_SCHEMA = {
    "name": "electromagnetic_tool",
    "description": (
        "Simulaciones electromagneticas 1D: propagacion de onda E/H via "
        "FDTD leapfrog con bordes PEC (mode='wave_1d'), y deteccion de "
        "band gaps en cristales fotonicos 1D via matriz de transferencia "
        "y condicion de Bloch (mode='photonic_bandgap'). mode='validate' "
        "corre ambos self-tests contra resultados analiticos conocidos."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["wave_1d", "photonic_bandgap", "validate"],
            },
            "nx": {"type": "integer", "description": "Celdas de rejilla (wave_1d)"},
            "nt": {"type": "integer", "description": "Pasos temporales (wave_1d)"},
            "courant": {"type": "number", "description": "Numero de Courant S=c*dt/dx, <=1 (wave_1d)"},
            "src_width": {"type": "number", "description": "Ancho temporal del pulso gaussiano (wave_1d)"},
            "f0_hz": {"type": "number", "description": "Frecuencia de diseno del apilado (photonic_bandgap)"},
            "n1": {"type": "number", "description": "Indice de refraccion capa alta (photonic_bandgap)"},
            "n2": {"type": "number", "description": "Indice de refraccion capa baja (photonic_bandgap)"},
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
    elif mode == "validate":
        result = validate(arguments)
    else:
        return {"error": f"modo desconocido: {mode}"}
    result["mode"] = mode
    return result


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
