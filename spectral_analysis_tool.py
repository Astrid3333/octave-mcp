"""
spectral_analysis_tool.py
Analisis espectral tipo ABRAVIBE: FFT, funciones de transferencia (FRF) via
estimador H1, y extraccion de parametros modales (frecuencia natural,
amortiguamiento) DESDE DATOS -- a diferencia de fem_advanced_tool que calcula
frecuencias propias desde el modelo (K,M), esto las extrae de una señal
medida (entrada/salida), como en un ensayo de vibraciones real.

Modos:
  - fft_spectrum       : espectro de magnitud/fase de una señal temporal
  - frf_h1             : estima la FRF H1 = Gxy/Gxx (Welch, promediado por
                         segmentos) a partir de señales de entrada x(t) y
                         salida y(t)
  - modal_extraction   : identifica frecuencia natural (pico de la FRF) y
                         razon de amortiguamiento (metodo del ancho de banda
                         de media potencia, -3dB) a partir de una FRF
  - validate           : genera la respuesta de un sistema 1-GDL conocido
                         (fn, zeta) a ruido blanco, corre H1 + extraccion
                         modal, y compara los parametros identificados contra
                         los valores verdaderos usados para generar la señal
"""
import numpy as np

SPECTRAL_ANALYSIS_TOOL_SCHEMA = {
    "name": "spectral_analysis_tool",
    "description": (
        "Analisis espectral tipo ABRAVIBE: FFT, estimacion de FRF via H1 "
        "(Welch, promediado), y extraccion de parametros modales (frecuencia "
        "natural + amortiguamiento, metodo del ancho de banda de media "
        "potencia) DESDE UNA SEÑAL MEDIDA -- complementa a fem_advanced_tool, "
        "que los calcula desde el modelo K,M en vez de datos. mode='validate' "
        "genera la respuesta de un 1-GDL conocido a ruido blanco y verifica "
        "que se recuperan fn y zeta correctos desde la señal sintetica."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["fft_spectrum", "frf_h1", "modal_extraction", "validate"]},
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


def _fft_spectrum(signal, fs=1000.0):
    signal = np.asarray(signal, dtype=float)
    n = len(signal)
    X = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(n, d=1.0/fs)
    mag = np.abs(X) * 2.0 / n
    phase = np.angle(X)
    return {
        "mode": "fft_spectrum",
        "freqs_hz": freqs.tolist(),
        "magnitude": mag.tolist(),
        "phase_rad": phase.tolist(),
    }


def _welch_segments(x, y, fs, nperseg):
    n = len(x)
    step = nperseg // 2  # 50% overlap
    win = np.hanning(nperseg)
    win_norm = np.sum(win**2)
    Gxx_sum, Gyy_sum, Gxy_sum = None, None, None
    n_seg = 0
    start = 0
    while start + nperseg <= n:
        xs = (x[start:start+nperseg] - np.mean(x[start:start+nperseg])) * win
        ys = (y[start:start+nperseg] - np.mean(y[start:start+nperseg])) * win
        Xf = np.fft.rfft(xs)
        Yf = np.fft.rfft(ys)
        Gxx = np.abs(Xf)**2
        Gyy = np.abs(Yf)**2
        Gxy = np.conj(Xf) * Yf
        if Gxx_sum is None:
            Gxx_sum, Gyy_sum, Gxy_sum = Gxx, Gyy, Gxy
        else:
            Gxx_sum = Gxx_sum + Gxx
            Gyy_sum = Gyy_sum + Gyy
            Gxy_sum = Gxy_sum + Gxy
        n_seg += 1
        start += step
    freqs = np.fft.rfftfreq(nperseg, d=1.0/fs)
    return freqs, Gxx_sum/n_seg, Gyy_sum/n_seg, Gxy_sum/n_seg, n_seg


def _frf_h1(x, y, fs=1000.0, nperseg=1024):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    freqs, Gxx, Gyy, Gxy, n_seg = _welch_segments(x, y, fs, nperseg)
    H1 = Gxy / np.where(Gxx == 0, 1e-30, Gxx)
    coherence = (np.abs(Gxy)**2) / np.where(Gxx*Gyy == 0, 1e-30, Gxx*Gyy)
    return {
        "mode": "frf_h1",
        "freqs_hz": freqs.tolist(),
        "H1_magnitude": np.abs(H1).tolist(),
        "H1_phase_rad": np.angle(H1).tolist(),
        "coherence": np.real(coherence).tolist(),
        "n_segments_averaged": n_seg,
    }


def _modal_extraction_from_frf(freqs_hz, H1_magnitude):
    freqs = np.asarray(freqs_hz, dtype=float)
    mag = np.asarray(H1_magnitude, dtype=float)
    # ignorar frecuencia 0 (evita picos espurios en DC)
    mask = freqs > 1e-6
    freqs_m, mag_m = freqs[mask], mag[mask]
    peak_idx = int(np.argmax(mag_m))
    fn_hz = float(freqs_m[peak_idx])
    peak_val = mag_m[peak_idx]
    half_power = peak_val / np.sqrt(2.0)

    # buscar cruces de media potencia a izquierda y derecha del pico
    left_idx = peak_idx
    while left_idx > 0 and mag_m[left_idx] > half_power:
        left_idx -= 1
    right_idx = peak_idx
    while right_idx < len(mag_m)-1 and mag_m[right_idx] > half_power:
        right_idx += 1

    def _interp_crossing(i1, i2, target):
        f1, f2 = freqs_m[i1], freqs_m[i2]
        m1, m2 = mag_m[i1], mag_m[i2]
        if m2 == m1:
            return f2
        t = (target - m1) / (m2 - m1)
        return f1 + t*(f2 - f1)

    f_low = _interp_crossing(left_idx, left_idx+1, half_power) if left_idx < peak_idx else freqs_m[0]
    f_high = _interp_crossing(right_idx-1, right_idx, half_power) if right_idx > peak_idx else freqs_m[-1]

    bandwidth = f_high - f_low
    zeta = bandwidth / (2*fn_hz) if fn_hz > 0 else None

    return {
        "mode": "modal_extraction",
        "fn_hz": fn_hz,
        "half_power_freqs_hz": [float(f_low), float(f_high)],
        "bandwidth_hz": float(bandwidth),
        "zeta_estimated": float(zeta) if zeta is not None else None,
    }


def _mode_validate():
    # sistema 1-GDL conocido: fn, zeta verdaderos, excitado con ruido blanco,
    # respuesta simulada por integracion de la EDO m*x''+c*x'+k*x=f(t)
    fn_true_hz = 15.0
    zeta_true = 0.03
    m = 1.0
    omega_n = 2*np.pi*fn_true_hz
    k = m*omega_n**2
    c = 2*zeta_true*m*omega_n

    fs = 1000.0
    T = 60.0
    n = int(fs*T)
    rng = np.random.default_rng(7)
    force = rng.normal(0, 1.0, n)

    dt = 1.0/fs
    x = np.zeros(n)
    v = np.zeros(n)
    a = (force[0] - c*v[0] - k*x[0]) / m
    for i in range(1, n):
        a = (force[i-1] - c*v[i-1] - k*x[i-1]) / m
        v[i] = v[i-1] + a*dt
        x[i] = x[i-1] + v[i]*dt

    frf = _frf_h1(force, x, fs=fs, nperseg=4096)
    modal = _modal_extraction_from_frf(frf["freqs_hz"], frf["H1_magnitude"])

    fn_err_pct = 100*abs(modal["fn_hz"] - fn_true_hz)/fn_true_hz
    zeta_err_pct = (100*abs(modal["zeta_estimated"] - zeta_true)/zeta_true
                     if modal["zeta_estimated"] is not None else None)
    mean_coherence_near_peak = float(np.mean([c for f, c in zip(frf["freqs_hz"], frf["coherence"])
                                                if abs(f - fn_true_hz) < 2.0]))

    checks = {
        "fn_recovered": bool(fn_err_pct < 5.0),
        "zeta_recovered": bool(zeta_err_pct is not None and zeta_err_pct < 25.0),
        "coherence_high_near_resonance": bool(mean_coherence_near_peak > 0.8),
    }

    return {
        "mode": "validate",
        "true_params": {"fn_hz": fn_true_hz, "zeta": zeta_true},
        "identified_params": {"fn_hz": modal["fn_hz"], "zeta": modal["zeta_estimated"]},
        "fn_relative_error_pct": fn_err_pct,
        "zeta_relative_error_pct": zeta_err_pct,
        "mean_coherence_near_resonance": mean_coherence_near_peak,
        "checks": checks,
        "expected": "sistema 1-GDL conocido (fn=15Hz, zeta=3%) excitado con "
                    "ruido blanco. La FRF H1 estimada por Welch debe mostrar "
                    "un pico claro en fn, y el metodo de ancho de banda de "
                    "media potencia debe recuperar zeta dentro de ~25% "
                    "(la extraccion de amortiguamiento desde datos ruidosos "
                    "es intrinsecamente menos precisa que fn).",
        "validation_passed": bool(all(checks.values())),
    }


def compute_spectral_analysis(mode, params=None):
    params = params or {}
    if mode == "fft_spectrum":
        return _fft_spectrum(**params)
    elif mode == "frf_h1":
        return _frf_h1(**params)
    elif mode == "modal_extraction":
        return _modal_extraction_from_frf(**params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(f"modo desconocido: {mode}")


if __name__ == "__main__":
    import json
    r = compute_spectral_analysis("validate")
    print(json.dumps(r, indent=2, ensure_ascii=False))
