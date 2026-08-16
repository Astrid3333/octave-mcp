import tool_registry
import json
import numpy as np
from scipy.signal import hilbert


# ---------------------------------------------------------------------------
# mode 1: harmonics
# ---------------------------------------------------------------------------
def harmonics(params):
    """Sintetiza una señal con fundamental f0 y armonicos de amplitud
    conocida, mide el espectro via FFT con muestreo coherente (numero
    entero de ciclos de f0 en la ventana, sin leakage), y valida que las
    amplitudes/frecuencias medidas coincidan con las especificadas, mas la
    Distorsion Armonica Total (THD) medida vs la calculada analiticamente
    de las amplitudes de entrada: THD = sqrt(sum(A_n^2, n>=2)) / A_1."""
    f0 = float(params.get("f0", 440.0))
    amplitudes = params.get("amplitudes", [1.0, 0.3, 0.15, 0.05])
    fs = float(params.get("fs", 44100.0))
    n_cycles = int(params.get("n_cycles", 200))

    amplitudes = np.asarray(amplitudes, dtype=float)
    n_harmonics = len(amplitudes)

    T = n_cycles / f0
    N = int(round(T * fs))
    # ajustar fs efectivo para que N muestras cubran EXACTAMENTE n_cycles
    # ciclos de f0 (muestreo coherente, sin fuga espectral)
    fs_eff = N / T
    t = np.arange(N) / fs_eff

    signal = np.zeros(N)
    for n in range(1, n_harmonics + 1):
        signal += amplitudes[n - 1] * np.sin(2 * np.pi * n * f0 * t)

    spectrum = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(N, d=1.0 / fs_eff)
    measured_amp = 2.0 * np.abs(spectrum) / N

    bin_width = fs_eff / N
    measured_amplitudes = []
    freq_errors_pct = []
    amp_errors_pct = []
    for n in range(1, n_harmonics + 1):
        target_freq = n * f0
        k = int(round(target_freq / bin_width))
        measured_amplitudes.append(float(measured_amp[k]))
        freq_errors_pct.append(abs(freqs[k] / target_freq - 1.0) * 100.0)
        amp_errors_pct.append(abs(measured_amp[k] / amplitudes[n - 1] - 1.0) * 100.0 if amplitudes[n - 1] > 0 else 0.0)

    max_amp_error_pct = float(np.max(amp_errors_pct))
    max_freq_error_pct = float(np.max(freq_errors_pct))

    thd_theory = float(np.sqrt(np.sum(amplitudes[1:] ** 2)) / amplitudes[0])
    thd_measured = float(np.sqrt(np.sum(np.array(measured_amplitudes[1:]) ** 2)) / measured_amplitudes[0])
    thd_error_pct = abs(thd_measured / thd_theory - 1.0) * 100.0 if thd_theory > 0 else 0.0

    passed = bool(max_amp_error_pct < 0.5 and max_freq_error_pct < 1e-6 and thd_error_pct < 0.5)

    return {
        "f0": f0, "n_harmonics": n_harmonics,
        "measured_amplitudes": [round(v, 6) for v in measured_amplitudes],
        "input_amplitudes": amplitudes.tolist(),
        "max_amplitude_error_pct": round(max_amp_error_pct, 6),
        "max_frequency_error_pct": round(max_freq_error_pct, 10),
        "thd_theory": round(thd_theory, 6), "thd_measured": round(thd_measured, 6),
        "thd_error_pct": round(thd_error_pct, 6),
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# mode 2: tone_sweep
# ---------------------------------------------------------------------------
def tone_sweep(params):
    """Genera un barrido (chirp) lineal o logaritmico (exponencial) entre
    f0 y f1 en tiempo T, y valida la frecuencia instantanea medida (via
    fase de la señal analitica de Hilbert, derivada numerica) contra la
    ley de barrido especificada:
    lineal: f(t) = f0 + (f1-f0)*t/T
    logaritmico: f(t) = f0*(f1/f0)**(t/T)
    Se descartan los bordes (primer/ultimo 5%) donde la transformada de
    Hilbert tiene artefactos de borde conocidos."""
    f0 = float(params.get("f0", 100.0))
    f1 = float(params.get("f1", 2000.0))
    T = float(params.get("duration", 2.0))
    fs = float(params.get("fs", 44100.0))
    sweep_type = params.get("sweep_type", "linear")

    N = int(round(T * fs))
    t = np.arange(N) / fs

    if sweep_type == "linear":
        phase = 2 * np.pi * (f0 * t + (f1 - f0) * t ** 2 / (2 * T))
        f_instantaneous_theory = f0 + (f1 - f0) * t / T
    elif sweep_type == "logarithmic":
        k_rate = (f1 / f0) ** (1.0 / T)
        phase = 2 * np.pi * f0 * (k_rate ** t - 1.0) / np.log(k_rate)
        f_instantaneous_theory = f0 * k_rate ** t
    else:
        raise ValueError(f"sweep_type desconocido: {sweep_type}")

    signal = np.sin(phase)

    analytic = hilbert(signal)
    inst_phase = np.unwrap(np.angle(analytic))
    inst_freq = np.gradient(inst_phase, 1.0 / fs) / (2 * np.pi)

    edge = int(0.05 * N)
    core = slice(edge, N - edge)
    error_pct = np.abs(inst_freq[core] / f_instantaneous_theory[core] - 1.0) * 100.0
    max_error_pct = float(np.max(error_pct))
    mean_error_pct = float(np.mean(error_pct))

    passed = bool(max_error_pct < 2.0)

    return {
        "sweep_type": sweep_type, "f0": f0, "f1": f1, "duration": T,
        "max_error_pct": round(max_error_pct, 4),
        "mean_error_pct": round(mean_error_pct, 4),
        "f_start_measured": float(inst_freq[edge]), "f_end_measured": float(inst_freq[-edge - 1]),
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# mode 3: audio_filter
# ---------------------------------------------------------------------------
def _windowed_sinc_lowpass(fc_norm, n_taps):
    """FIR pasa-bajos por ventaneado de sinc ideal (Hamming), fc_norm en
    ciclos/muestra (0..0.5). n_taps impar recomendado (fase lineal exacta,
    simetria de coeficientes)."""
    if n_taps % 2 == 0:
        n_taps += 1
    M = n_taps - 1
    n = np.arange(n_taps)
    h_ideal = np.sinc(2 * fc_norm * (n - M / 2))
    window = 0.54 - 0.46 * np.cos(2 * np.pi * n / M)  # Hamming
    h = h_ideal * window
    h /= np.sum(h)  # normaliza ganancia DC a 1
    return h


def audio_filter(params):
    """Filtro FIR pasa-bajos por ventaneado de sinc (implementacion propia,
    sin scipy.signal.firwin), aplicado a una señal de prueba con un tono en
    banda pasante y otro en banda rechazada. Valida: (a) el tono en banda
    pasante se preserva (ganancia ~1, error < 5%), (b) el tono en banda
    rechazada se atenua al menos target_atten_db (via FFT antes/despues)."""
    fs = float(params.get("fs", 44100.0))
    fc = float(params.get("cutoff_freq", 2000.0))
    f_pass = float(params.get("f_pass_test", 500.0))
    f_stop = float(params.get("f_stop_test", 8000.0))
    n_taps = int(params.get("n_taps", 401))
    target_atten_db = float(params.get("target_atten_db", 40.0))
    duration = float(params.get("duration", 0.2))

    fc_norm = fc / fs
    h = _windowed_sinc_lowpass(fc_norm, n_taps)

    N = int(round(duration * fs))
    t = np.arange(N) / fs
    signal = np.sin(2 * np.pi * f_pass * t) + np.sin(2 * np.pi * f_stop * t)

    filtered = np.convolve(signal, h, mode="same")

    # medir amplitud de cada tono antes/despues via correlacion con
    # referencia sin/cos en la region central (evita transitorios de borde
    # del filtro FIR, que dura ~n_taps/2 muestras)
    edge = n_taps
    core = slice(edge, N - edge)

    def tone_amplitude(x, f):
        tc = t[core]
        c = np.cos(2 * np.pi * f * tc)
        s = np.sin(2 * np.pi * f * tc)
        a = 2.0 / len(tc) * np.sum(x[core] * c)
        b = 2.0 / len(tc) * np.sum(x[core] * s)
        return np.hypot(a, b)

    amp_pass_in = tone_amplitude(signal, f_pass)
    amp_pass_out = tone_amplitude(filtered, f_pass)
    amp_stop_in = tone_amplitude(signal, f_stop)
    amp_stop_out = tone_amplitude(filtered, f_stop)

    passband_gain_error_pct = abs(amp_pass_out / amp_pass_in - 1.0) * 100.0
    stopband_atten_db = 20.0 * np.log10(amp_stop_in / max(amp_stop_out, 1e-30))

    passband_ok = bool(passband_gain_error_pct < 5.0)
    stopband_ok = bool(stopband_atten_db > target_atten_db)
    passed = bool(passband_ok and stopband_ok)

    return {
        "cutoff_freq": fc, "n_taps": n_taps,
        "f_pass_test": f_pass, "f_stop_test": f_stop,
        "passband_gain_error_pct": round(float(passband_gain_error_pct), 4),
        "stopband_attenuation_db": round(float(stopband_atten_db), 4),
        "target_atten_db": target_atten_db,
        "passband_ok": passband_ok, "stopband_ok": stopband_ok,
        "passed": passed,
    }


# ---------------------------------------------------------------------------
def validate(params=None):
    params = params or {}
    r1 = harmonics(params.get("harmonics", {}))
    r2 = tone_sweep(params.get("tone_sweep", {}))
    r3 = audio_filter(params.get("audio_filter", {}))
    validation_passed = bool(r1["passed"] and r2["passed"] and r3["passed"])
    return {
        "harmonics": r1, "tone_sweep": r2, "audio_filter": r3,
        "validation_passed": validation_passed,
    }


AUDIO_PROCESSING_TOOL_SCHEMA = {
    "name": "audio_processing_tool",
    "description": (
        "Procesamiento de señales de audio: analisis armonico con medicion "
        "de amplitudes/THD via FFT de muestreo coherente (mode='harmonics'), "
        "generacion de barridos (chirp) lineales y logaritmicos con "
        "verificacion de frecuencia instantanea via fase de Hilbert "
        "(mode='tone_sweep'), y filtro FIR pasa-bajos por ventaneado de "
        "sinc (Hamming) con verificacion de ganancia en banda pasante y "
        "atenuacion en banda rechazada (mode='audio_filter'). "
        "mode='validate' corre los 3 self-tests."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["harmonics", "tone_sweep", "audio_filter", "validate"]},
            "params": {"type": "object", "description": "Parametros especificos de cada modo"},
        },
        "required": ["mode"],
    },
}


def compute_audio_processing(mode, params=None):
    params = params or {}
    if mode == "harmonics":
        return harmonics(params)
    elif mode == "tone_sweep":
        return tone_sweep(params)
    elif mode == "audio_filter":
        return audio_filter(params)
    elif mode == "validate":
        return validate(params)
    else:
        raise ValueError(f"modo desconocido: {mode}")


if __name__ == "__main__":
    d = compute_audio_processing("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo"
    print("\nOK audio_processing_tool.py")


def _handler(args):
    return compute_audio_processing(args.get("mode"), args.get("params"))


tool_registry.register_tool("audio_processing_tool", AUDIO_PROCESSING_TOOL_SCHEMA, _handler)
