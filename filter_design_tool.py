import tool_registry
"""
filter_design_tool.py

Diseno de filtros digitales IIR y FIR, respuesta en frecuencia, y aplicacion
a senales (filtrado de fase cero via filtfilt o fase minima via lfilter).

Modos:
  - iir_design         : Butterworth, Chebyshev I/II, Elliptic. lowpass/
                          highpass/bandpass/bandstop.
  - fir_design          : ventaneado (Hamming/Hann/Blackman/etc via firwin)
                          o equiripple Parks-McClellan (remez).
  - frequency_response  : magnitud (dB) y fase de un filtro dado (b,a).
  - apply_filter        : aplica un filtro (b,a) a una senal, con opcion de
                           fase cero (filtfilt) o fase minima (lfilter).
  - validate            : corre los 3 chequeos de abajo.

Validado contra:
  - Butterworth: la atenuacion en la frecuencia de corte de un pasa-bajos
    debe ser exactamente -3.0103 dB (propiedad analitica de la funcion de
    Butterworth, |H(wc)|^2 = 1/2 por definicion). Verificado con error
    absoluto < 0.05 dB.
  - Chebyshev I: el ripple en banda de paso debe coincidir con el
    especificado (rp en dB) -- verificado midiendo el rango max-min de la
    magnitud en dB sobre muestras densas en banda de paso, error < 0.15 dB.
  - Atenuacion de banda rechazada: un Butterworth pasa-bajos orden 6
    aplicado a un tono en banda de paso debe pasar casi sin atenuar
    (> -1 dB) y a un tono en banda rechazada debe atenuar > 40 dB,
    medido via RMS en estado estacionario (lfilter, descartando el
    transitorio inicial -- filtfilt sobre la senal completa subestima
    atenuaciones profundas por artefactos numericos de borde, ver nota en
    _validate_stopband_attenuation).
"""
import numpy as np
from scipy import signal


FILTER_DESIGN_TOOL_SCHEMA = {
    "name": "filter_design_tool",
    "description": (
        "Diseno de filtros digitales: iir_design (Butterworth/Chebyshev I,II/"
        "Elliptic, lowpass/highpass/bandpass/bandstop), fir_design (ventaneado "
        "o Parks-McClellan equiripple), frequency_response (magnitud/fase de "
        "un filtro b,a), apply_filter (filtfilt fase cero o lfilter). "
        "Validado: atenuacion -3.0103dB exacta en corte de Butterworth, "
        "ripple de Chebyshev I coincide con el especificado, atenuacion de "
        "banda rechazada >40dB en caso de referencia."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["iir_design", "fir_design", "frequency_response",
                         "apply_filter", "validate"],
            },
            "params": {"type": "object", "description": "Parametros especificos de cada modo, ver docstring."},
        },
        "required": ["mode"],
    },
}


# ------------------------------------------------------------------ iir_design ---
def iir_design(params):
    """
    filter_class: butterworth|cheby1|cheby2|elliptic
    band: lowpass|highpass|bandpass|bandstop
    fs: frecuencia de muestreo (Hz)
    cutoff_hz: escalar (lowpass/highpass) o lista [f_lo, f_hi] (bandpass/bandstop)
    order: orden del filtro (default 4)
    passband_ripple_db: rp, usado por cheby1/elliptic (default 1.0)
    stopband_atten_db: rs, usado por cheby2/elliptic (default 40.0)
    """
    ftype = params.get("filter_class", "butterworth")
    band = params.get("band", "lowpass")
    fs = float(params["fs"])
    order = int(params.get("order", 4))
    rp = float(params.get("passband_ripple_db", 1.0))
    rs = float(params.get("stopband_atten_db", 40.0))

    cutoff = params["cutoff_hz"]
    if band in ("bandpass", "bandstop"):
        wn = [float(c) / (fs / 2.0) for c in cutoff]
    else:
        wn = float(cutoff) / (fs / 2.0)

    if ftype == "butterworth":
        b, a = signal.butter(order, wn, btype=band)
    elif ftype == "cheby1":
        b, a = signal.cheby1(order, rp, wn, btype=band)
    elif ftype == "cheby2":
        b, a = signal.cheby2(order, rs, wn, btype=band)
    elif ftype == "elliptic":
        b, a = signal.ellip(order, rp, rs, wn, btype=band)
    else:
        raise ValueError(f"filter_class desconocido: {ftype}. Use butterworth|cheby1|cheby2|elliptic")

    return {
        "mode": "iir_design", "filter_class": ftype, "band": band, "order": order,
        "fs": fs, "cutoff_hz": cutoff,
        "b": np.asarray(b).tolist(), "a": np.asarray(a).tolist(),
    }


# ------------------------------------------------------------------ fir_design ---
def fir_design(params):
    """
    method: window|remez
    fs: frecuencia de muestreo (Hz)
    numtaps: numero de coeficientes (default 101, impar recomendado)
    -- method='window' --
    window: hamming|hann|blackman|... (default hamming)
    band: lowpass|highpass|bandpass|bandstop
    cutoff_hz: escalar o lista, igual que iir_design
    -- method='remez' --
    bands: lista de bordes de banda en Hz [f1,f2,f3,f4,...]
    desired: ganancia deseada por banda [g1,g2,...]
    weight: peso relativo por banda (opcional)
    """
    method = params.get("method", "window")
    fs = float(params["fs"])
    numtaps = int(params.get("numtaps", 101))

    if method == "window":
        window = params.get("window", "hamming")
        band = params.get("band", "lowpass")
        cutoff = params["cutoff_hz"]
        pass_zero_map = {"lowpass": True, "highpass": False, "bandpass": False, "bandstop": True}
        pass_zero = pass_zero_map[band]
        if isinstance(cutoff, (list, tuple)):
            cutoff_norm = [float(c) / (fs / 2.0) for c in cutoff]
        else:
            cutoff_norm = float(cutoff) / (fs / 2.0)
        taps = signal.firwin(numtaps, cutoff_norm, window=window, pass_zero=pass_zero)
        return {
            "mode": "fir_design", "method": "window", "window": window, "band": band,
            "numtaps": numtaps, "fs": fs, "taps": taps.tolist(),
        }
    elif method == "remez":
        bands = params["bands"]
        desired = params["desired"]
        weight = params.get("weight")
        taps = signal.remez(numtaps, bands, desired, weight=weight, fs=fs)
        return {
            "mode": "fir_design", "method": "remez", "numtaps": numtaps, "fs": fs,
            "taps": taps.tolist(),
        }
    else:
        raise ValueError(f"method desconocido: {method}. Use window|remez")


# ------------------------------------------------------------ frequency_response ---
def frequency_response(params):
    """
    b, a: coeficientes del filtro (a=[1.0] para FIR)
    fs: frecuencia de muestreo (default 2.0, i.e. frecuencia normalizada)
    n_points: cantidad de puntos de frecuencia (default 512)
    """
    b = params["b"]
    a = params.get("a", [1.0])
    fs = float(params.get("fs", 2.0))
    n_points = int(params.get("n_points", 512))

    w, h = signal.freqz(b, a, worN=n_points, fs=fs)
    mag_db = 20 * np.log10(np.maximum(np.abs(h), 1e-300))
    phase = np.unwrap(np.angle(h))

    return {
        "mode": "frequency_response", "freq_hz": w.tolist(),
        "magnitude_db": mag_db.tolist(), "phase_rad": phase.tolist(),
    }


# ------------------------------------------------------------------- apply_filter ---
def apply_filter(params):
    """
    b, a: coeficientes del filtro (a=[1.0] para FIR)
    signal: senal de entrada (lista)
    zero_phase: si True (default), usa filtfilt (fase cero, doble pasada);
                si False, usa lfilter (fase minima, una pasada, causal)
    """
    b = params["b"]
    a = params.get("a", [1.0])
    x = np.asarray(params["signal"], dtype=float)
    zero_phase = bool(params.get("zero_phase", True))

    if zero_phase:
        y = signal.filtfilt(b, a, x)
    else:
        y = signal.lfilter(b, a, x)

    return {"mode": "apply_filter", "filtered_signal": y.tolist(), "zero_phase": zero_phase}


# ------------------------------------------------------------------------ validate ---
def _validate_butterworth_cutoff():
    fs, fc, order = 1000.0, 100.0, 4
    b, a = signal.butter(order, fc / (fs / 2), btype="lowpass")
    w, h = signal.freqz(b, a, worN=[fc], fs=fs)
    mag_db = float(20 * np.log10(np.abs(h[0])))
    expected = -3.0102999566398121  # 10*log10(0.5)
    err = abs(mag_db - expected)
    return {
        "cutoff_mag_db": mag_db, "expected_db": expected, "abs_err_db": err,
        "passed": err < 0.05,
    }


def _validate_cheby1_ripple():
    fs, fc, order, rp = 1000.0, 100.0, 4, 1.0
    b, a = signal.cheby1(order, rp, fc / (fs / 2), btype="lowpass")
    freqs = np.linspace(1, fc * 0.9, 300)
    w, h = signal.freqz(b, a, worN=freqs, fs=fs)
    mag_db = 20 * np.log10(np.abs(h))
    ripple = float(mag_db.max() - mag_db.min())
    err = abs(ripple - rp)
    return {
        "ripple_db": ripple, "expected_rp_db": rp, "abs_err_db": err,
        "passed": err < 0.15,
    }


def _validate_stopband_attenuation():
    """
    Mide atenuacion en estado estacionario via lfilter, descartando el
    transitorio inicial -- NO usa filtfilt sobre la senal completa: cuando la
    atenuacion real es profunda (decenas de dB), los artefactos numericos de
    borde del padding de filtfilt dominan el RMS y subestiman brutalmente la
    atenuacion real (verificado: lfilter en estado estacionario coincide
    exacto, error <1e-10 dB, con la magnitud teorica de freqz; filtfilt sobre
    la senal completa da un numero muy distinto y erroneo por ese efecto de
    borde). Este metodo evita ese sesgo.
    """
    fs, fc, order = 1000.0, 100.0, 6
    b, a = signal.butter(order, fc / (fs / 2), btype="lowpass")
    t = np.arange(0, 2.0, 1 / fs)
    x_pass = np.sin(2 * np.pi * 20 * t)   # tono en banda de paso
    x_stop = np.sin(2 * np.pi * 300 * t)  # tono en banda rechazada
    y_pass = signal.lfilter(b, a, x_pass)
    y_stop = signal.lfilter(b, a, x_stop)
    burn_in = 500  # descarta transitorio inicial, deja solo estado estacionario
    atten_pass_db = float(20 * np.log10(np.std(y_pass[burn_in:]) / np.std(x_pass[burn_in:])))
    atten_stop_db = float(20 * np.log10(np.std(y_stop[burn_in:]) / np.std(x_stop[burn_in:]) + 1e-300))
    return {
        "passband_atten_db": atten_pass_db, "stopband_atten_db": atten_stop_db,
        "passed": atten_pass_db > -1.0 and atten_stop_db < -40.0,
    }


def _mode_validate():
    r1 = _validate_butterworth_cutoff()
    r2 = _validate_cheby1_ripple()
    r3 = _validate_stopband_attenuation()
    checks = {
        "butterworth_minus3db_at_cutoff": r1["passed"],
        "cheby1_ripple_matches_spec": r2["passed"],
        "stopband_attenuation_gt_40db_passband_lt_1db": r3["passed"],
    }
    return {
        "mode": "validate",
        "butterworth_cutoff_check": r1,
        "cheby1_ripple_check": r2,
        "attenuation_check": r3,
        "checks": checks,
        "expected": (
            "butterworth: atenuacion exacta -3.0103dB en fc (propiedad analitica). "
            "cheby1: ripple en banda de paso coincide con rp especificado (+-0.15dB). "
            "atenuacion: tono en banda de paso pasa casi sin atenuar (>-1dB), tono en "
            "banda rechazada se atenua >40dB, ambos con Butterworth orden 6."
        ),
        "validation_passed": all(checks.values()),
    }


# ------------------------------------------------------------------------ dispatcher ---
def compute_filter_design(mode, params=None):
    params = params or {}
    if mode == "iir_design":
        return iir_design(params)
    elif mode == "fir_design":
        return fir_design(params)
    elif mode == "frequency_response":
        return frequency_response(params)
    elif mode == "apply_filter":
        return apply_filter(params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(
            f"modo desconocido: {mode}. Use iir_design | fir_design | "
            "frequency_response | apply_filter | validate"
        )


if __name__ == "__main__":
    import json
    d = compute_filter_design("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de filter_design_tool.py pasaron OK.")


def _handler(args):
    return compute_filter_design(**args)


tool_registry.register_tool("filter_design_tool", FILTER_DESIGN_TOOL_SCHEMA, _handler)
