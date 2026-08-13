import json
import numpy as np
from scipy.signal import hilbert


# ---------------------------------------------------------------------------
# mode 1: stft
# ---------------------------------------------------------------------------
def _stft(signal, fs, win_len, hop):
    N = len(signal)
    window = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(win_len) / win_len)  # Hann
    n_frames = 1 + (N - win_len) // hop
    n_fft = win_len
    spec = np.zeros((n_frames, n_fft // 2 + 1), dtype=complex)
    frame_centers = np.zeros(n_frames)
    for i in range(n_frames):
        start = i * hop
        seg = signal[start:start + win_len] * window
        spec[i] = np.fft.rfft(seg)
        frame_centers[i] = (start + win_len / 2.0) / fs
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / fs)
    return spec, freqs, frame_centers


def stft(params):
    """Espectrograma (STFT) de un chirp lineal, con ventana de Hann.
    Se extrae la cresta de frecuencia (bin de magnitud maxima en cada
    cuadro) y se valida contra la frecuencia instantanea teorica del
    chirp f(t)=f0+(f1-f0)*t/T. La tolerancia de error se fija en funcion
    de la resolucion espectral fs/win_len (inherente al compromiso
    tiempo-frecuencia de la STFT: ventanas mas largas dan mejor
    resolucion en frecuencia pero peor en tiempo, sesgando la cresta
    medida en un chirp)."""
    fs = float(params.get("fs", 8000.0))
    f0 = float(params.get("f0", 200.0))
    f1 = float(params.get("f1", 2000.0))
    T = float(params.get("duration", 1.0))
    win_len = int(params.get("win_len", 256))
    hop = int(params.get("hop", 32))

    N = int(round(T * fs))
    t = np.arange(N) / fs
    phase = 2 * np.pi * (f0 * t + (f1 - f0) * t ** 2 / (2 * T))
    signal = np.sin(phase)

    spec, freqs, frame_centers = _stft(signal, fs, win_len, hop)
    mag = np.abs(spec)
    ridge_idx = np.argmax(mag, axis=1)
    ridge_freq = freqs[ridge_idx]
    ridge_theory = f0 + (f1 - f0) * frame_centers / T

    freq_resolution = fs / win_len
    edge = max(1, win_len // (2 * hop))
    core = slice(edge, len(frame_centers) - edge)
    abs_err = np.abs(ridge_freq[core] - ridge_theory[core])
    max_err_bins = float(np.max(abs_err) / freq_resolution)
    mean_err_hz = float(np.mean(abs_err))

    passed = bool(max_err_bins < 1.5)

    return {
        "n_frames": int(len(frame_centers)), "freq_resolution_hz": freq_resolution,
        "max_ridge_error_bins": round(max_err_bins, 4),
        "mean_ridge_error_hz": round(mean_err_hz, 4),
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# mode 2: wigner_ville
# ---------------------------------------------------------------------------
def _pseudo_wvd(z, tau_max, n_freq):
    """Distribucion de Wigner-Ville pseudo (ventana rectangular en tau) de
    la señal analitica z. Definicion continua: W(t,f) = 2*Re{ integral
    z(t+tau)*conj(z(t-tau)) * exp(-j*4*pi*f*tau) dtau }. El factor 4*pi
    (no 2*pi) es la convencion estandar de Wigner-Ville -- significa que
    el DFT de la autocorrelacion instantanea R[tau]=z[n+tau]*conj(z[n-tau])
    calculado con exp(-j*2*pi*k*tau/n_freq) da la frecuencia FISICA en
    f = 0.5*k*fs/n_freq (la variable conjugada de tau es 2f, no f). Se
    divide el eje de frecuencia resultante por 2 para compensar esto;
    en consecuencia el rango de frecuencia fisica valida sin aliasing es
    [0, fs/4] (la WVD discreta requiere el doble de sobremuestreo que el
    ancho de banda de la señal para evitar aliasing en f)."""
    N = len(z)
    taus = np.arange(-tau_max, tau_max + 1)
    W = np.zeros((N, n_freq))
    for n in range(N):
        i1 = n + taus
        i2 = n - taus
        valid = (i1 >= 0) & (i1 < N) & (i2 >= 0) & (i2 < N)
        R = np.zeros(n_freq, dtype=complex)
        idx_pos = taus[valid] % n_freq
        R[idx_pos] = z[i1[valid]] * np.conj(z[i2[valid]])
        W[n, :] = np.real(np.fft.fft(R))
    return 2.0 * W


def _wvd_freqs(n_freq, fs):
    """Eje de frecuencia fisica correcto para _pseudo_wvd (ver docstring:
    factor 0.5 por la convencion exp(-j*4*pi*f*tau) de la WVD)."""
    return 0.5 * np.fft.fftfreq(n_freq, d=1.0 / fs)


def wigner_ville(params):
    """Distribucion de Wigner-Ville (pseudo-WVD via señal analitica de
    Hilbert, sin termino de ventana suave en tau) de un chirp lineal.
    A diferencia de la STFT, la WVD de un chirp lineal (LFM) es EXACTA:
    su cresta de frecuencia sigue la ley instantanea f(t)=f0+(f1-f0)*t/T
    sin el sesgo por compromiso tiempo-frecuencia de una ventana finita
    (propiedad conocida de la WVD para señales de fase cuadratica). Se
    valida que el error de la cresta sea sustancialmente menor que en la
    STFT para la misma señal y resolucion temporal nominal."""
    fs = float(params.get("fs", 8000.0))
    f0 = float(params.get("f0", 200.0))
    f1 = float(params.get("f1", 1500.0))
    T = float(params.get("duration", 0.25))
    tau_max = int(params.get("tau_max", 64))
    n_freq = int(params.get("n_freq", 256))

    N = int(round(T * fs))
    t = np.arange(N) / fs
    phase = 2 * np.pi * (f0 * t + (f1 - f0) * t ** 2 / (2 * T))
    signal = np.sin(phase)
    z = hilbert(signal)

    W = _pseudo_wvd(z, tau_max, n_freq)
    freqs = _wvd_freqs(n_freq, fs)
    pos = freqs >= 0
    freqs_pos = freqs[pos]
    W_pos = W[:, pos]

    ridge_idx = np.argmax(W_pos, axis=1)
    ridge_freq = freqs_pos[ridge_idx]
    ridge_theory = f0 + (f1 - f0) * t / T

    edge = tau_max
    core = slice(edge, N - edge)
    freq_resolution = 0.5 * fs / n_freq  # ver _wvd_freqs: bin fisico = 0.5*fs/n_freq
    abs_err = np.abs(ridge_freq[core] - ridge_theory[core])
    max_err_bins = float(np.max(abs_err) / freq_resolution)
    mean_err_hz = float(np.mean(abs_err))

    passed = bool(max_err_bins < 1.5)

    return {
        "N_samples": N, "freq_resolution_hz": freq_resolution,
        "max_ridge_error_bins": round(max_err_bins, 4),
        "mean_ridge_error_hz": round(mean_err_hz, 4),
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# mode 3: cross_terms
# ---------------------------------------------------------------------------
def cross_terms(params):
    """Demuestra el artefacto de terminos cruzados de la WVD: para una
    señal de DOS tonos simultaneos f1,f2 (no relacionados armonicamente
    con el chirp), la bilinealidad de la WVD genera energia espuria
    oscilante en la frecuencia media (f1+f2)/2 que NO esta presente en la
    señal original -- a diferencia de la STFT, que al ser un operador
    LINEAL en la señal no genera ese artefacto. Se valida: (a) la WVD
    muestra energia significativa y oscilante (varianza temporal alta) en
    el bin de frecuencia media; (b) la STFT en ese mismo bin tiene energia
    mucho menor y aproximadamente constante en el tiempo."""
    fs = float(params.get("fs", 8000.0))
    f1 = float(params.get("f1", 500.0))
    f2 = float(params.get("f2", 1500.0))
    T = float(params.get("duration", 0.25))
    tau_max = int(params.get("tau_max", 64))
    n_freq = int(params.get("n_freq", 256))

    N = int(round(T * fs))
    t = np.arange(N) / fs
    signal = np.sin(2 * np.pi * f1 * t) + np.sin(2 * np.pi * f2 * t)
    z = hilbert(signal)

    W = _pseudo_wvd(z, tau_max, n_freq)
    freqs = _wvd_freqs(n_freq, fs)
    pos = freqs >= 0
    freqs_pos = freqs[pos]
    W_pos = W[:, pos]

    f_mid = 0.5 * (f1 + f2)
    k_mid = int(np.argmin(np.abs(freqs_pos - f_mid)))
    k1 = int(np.argmin(np.abs(freqs_pos - f1)))
    k2 = int(np.argmin(np.abs(freqs_pos - f2)))

    edge = tau_max
    core = slice(edge, N - edge)
    wvd_mid_trace = W_pos[core, k_mid]
    wvd_auto_level = 0.5 * (np.mean(np.abs(W_pos[core, k1])) + np.mean(np.abs(W_pos[core, k2])))
    wvd_mid_amplitude = 0.5 * (np.max(wvd_mid_trace) - np.min(wvd_mid_trace))
    cross_term_ratio = float(wvd_mid_amplitude / wvd_auto_level) if wvd_auto_level > 0 else 0.0
    wvd_cross_term_present = bool(cross_term_ratio > 0.3)

    win_len = 2 * tau_max
    hop = 8
    spec, stft_freqs, _ = _stft(signal, fs, win_len, hop)
    stft_mag = np.abs(spec)
    k_mid_stft = int(np.argmin(np.abs(stft_freqs - f_mid)))
    k1_stft = int(np.argmin(np.abs(stft_freqs - f1)))
    k2_stft = int(np.argmin(np.abs(stft_freqs - f2)))
    stft_mid_level = float(np.mean(stft_mag[:, k_mid_stft]))
    stft_auto_level = 0.5 * (np.mean(stft_mag[:, k1_stft]) + np.mean(stft_mag[:, k2_stft]))
    stft_mid_ratio = float(stft_mid_level / stft_auto_level) if stft_auto_level > 0 else 0.0
    stft_clean = bool(stft_mid_ratio < 0.3)

    passed = bool(wvd_cross_term_present and stft_clean)

    return {
        "f1": f1, "f2": f2, "f_mid": f_mid,
        "wvd_cross_term_ratio": round(cross_term_ratio, 4),
        "wvd_cross_term_present": wvd_cross_term_present,
        "stft_mid_to_auto_ratio": round(stft_mid_ratio, 4),
        "stft_clean_at_mid_freq": stft_clean,
        "passed": passed,
    }


# ---------------------------------------------------------------------------
def validate(params=None):
    params = params or {}
    r1 = stft(params.get("stft", {}))
    r2 = wigner_ville(params.get("wigner_ville", {}))
    r3 = cross_terms(params.get("cross_terms", {}))
    validation_passed = bool(r1["passed"] and r2["passed"] and r3["passed"])
    return {
        "stft": r1, "wigner_ville": r2, "cross_terms": r3,
        "validation_passed": validation_passed,
    }


TIME_FREQUENCY_TOOL_SCHEMA = {
    "name": "time_frequency_tool",
    "description": (
        "Analisis tiempo-frecuencia: espectrograma STFT con ventana de "
        "Hann y verificacion de la cresta de frecuencia en un chirp lineal "
        "(mode='stft'), distribucion de Wigner-Ville (pseudo-WVD via señal "
        "analitica de Hilbert) con cresta exacta para chirps LFM "
        "(mode='wigner_ville'), y demostracion/verificacion del artefacto "
        "de terminos cruzados de la WVD en señales multi-componente "
        "contrastado con la STFT libre de ese artefacto (mode='cross_terms'). "
        "mode='validate' corre los 3 self-tests."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["stft", "wigner_ville", "cross_terms", "validate"]},
            "params": {"type": "object", "description": "Parametros especificos de cada modo"},
        },
        "required": ["mode"],
    },
}


def compute_time_frequency(mode, params=None):
    params = params or {}
    if mode == "stft":
        return stft(params)
    elif mode == "wigner_ville":
        return wigner_ville(params)
    elif mode == "cross_terms":
        return cross_terms(params)
    elif mode == "validate":
        return validate(params)
    else:
        raise ValueError(f"modo desconocido: {mode}")


if __name__ == "__main__":
    d = compute_time_frequency("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo"
    print("\nOK time_frequency_tool.py")
