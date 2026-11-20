"""audio_math_tool.py

Matematica de audio para produccion de audiolibros, sin dependencias de
archivos ni de codificacion. Los modos reciben muestras y frecuencia de
muestreo, devuelven metricas serializables y pueden transformar una senal.
"""
import json
import math
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np
import tool_registry
from scipy.signal import fftconvolve, lfilter, resample_poly

_K_WEIGHTING_SHELF_48K = (
    (1.53512485958697, -2.69169618940638, 1.19839281085285),
    (1.0, -1.69065929318241, 0.73248077421585),
)
_K_WEIGHTING_HIGHPASS_48K = (
    (1.0, -2.0, 1.0),
    (1.0, -1.99004745483398, 0.99007225036621),
)
_LUFS_REFERENCE = -0.691


def _signal(params, key="signal"):
    if key not in params:
        raise ValueError(f"falta el parametro '{key}'")
    signal = np.asarray(params[key], dtype=float)
    if signal.ndim == 0 or signal.size == 0:
        raise ValueError(f"'{key}' debe contener al menos una muestra")
    if not np.all(np.isfinite(signal)):
        raise ValueError(f"'{key}' contiene valores no finitos")
    return signal


def _sample_rate(params, default=48000.0):
    fs = float(params.get("fs", default))
    if fs <= 0.0:
        raise ValueError("fs debe ser positivo")
    return fs


def _db(value, floor=1e-15):
    value = float(value)
    if not math.isfinite(value) or value <= floor:
        return None
    return 20.0 * math.log10(value)


def _channels(signal):
    if signal.ndim == 1:
        return signal[np.newaxis, :]
    if signal.ndim == 2:
        if signal.shape[0] <= 8:
            return signal
        if signal.shape[1] <= 8:
            return signal.T
    raise ValueError("la senal debe ser mono (vector) o multicanal (canales x muestras)")


def _resample_to_48k(signal, fs):
    if math.isclose(fs, 48000.0, rel_tol=0.0, abs_tol=1e-9):
        return signal
    divisor = math.gcd(int(round(fs)), 48000)
    up = 48000 // divisor
    down = int(round(fs)) // divisor
    return resample_poly(signal, up, down, axis=-1)


def _k_weight(signal, fs):
    channels = _channels(signal)
    weighted = _resample_to_48k(channels, fs)
    shelf_b, shelf_a = _K_WEIGHTING_SHELF_48K
    highpass_b, highpass_a = _K_WEIGHTING_HIGHPASS_48K
    filtered = lfilter(shelf_b, shelf_a, weighted, axis=-1)
    return lfilter(highpass_b, highpass_a, filtered, axis=-1)


def rms_db(params):
    """Nivel RMS de una senal en dBFS."""
    signal = _signal(params)
    rms = float(np.sqrt(np.mean(np.square(signal))))
    return {
        "rms": rms,
        "rms_dbfs": _db(rms),
        "n_samples": int(signal.size),
        "duration_seconds": signal.size / _sample_rate(params),
    }


def lufs_kweight(params):
    """Loudness integrado EBU R128/ITU-R BS.1770 con K-weighting."""
    fs = _sample_rate(params)
    signal = _signal(params)
    filtered = _k_weight(signal, fs)
    channels = filtered.shape[0]
    channel_weights = np.ones(channels, dtype=float)
    if channels >= 3:
        channel_weights[2] = 1.41
    block_samples = int(round(0.4 * 48000.0))
    step_samples = int(round(0.1 * 48000.0))
    if filtered.shape[1] < block_samples:
        block_samples = filtered.shape[1]
        step_samples = max(1, block_samples // 4)
    energies = []
    loudness_blocks = []
    for start in range(0, filtered.shape[1] - block_samples + 1, step_samples):
        block = filtered[:, start:start + block_samples]
        mean_square = np.mean(np.square(block), axis=1)
        energy = float(np.sum(channel_weights * mean_square))
        energies.append(energy)
        loudness = _LUFS_REFERENCE + 10.0 * math.log10(max(energy, 1e-30))
        loudness_blocks.append(loudness)
    absolute_mask = np.asarray(loudness_blocks) >= -70.0
    if not np.any(absolute_mask):
        return {
            "integrated_lufs": None,
            "gating_threshold_lufs": None,
            "total_blocks": len(loudness_blocks),
            "gated_blocks": 0,
            "sample_rate": fs,
        }
    relative_threshold = float(np.mean(np.asarray(loudness_blocks)[absolute_mask]) - 10.0)
    gated_mask = absolute_mask & (np.asarray(loudness_blocks) >= relative_threshold)
    gated_energies = np.asarray(energies)[gated_mask]
    integrated = _LUFS_REFERENCE + 10.0 * math.log10(max(float(np.mean(gated_energies)), 1e-30))
    return {
        "integrated_lufs": integrated,
        "gating_threshold_lufs": relative_threshold,
        "total_blocks": len(loudness_blocks),
        "gated_blocks": int(np.sum(gated_mask)),
        "channel_weights": channel_weights.tolist(),
        "sample_rate": fs,
    }


def true_peak(params):
    """True peak mediante sobremuestreo x4."""
    fs = _sample_rate(params)
    signal = _signal(params)
    channels = _channels(signal)
    oversampled = resample_poly(channels, 4, 1, axis=-1, window=("kaiser", 5.0))
    peak = float(np.max(np.abs(oversampled)))
    return {
        "true_peak": peak,
        "true_peak_dbfs": _db(peak),
        "oversampling_factor": 4,
        "sample_rate": fs,
        "n_samples": int(signal.size),
    }


def fft_spectrum(params):
    """Espectro de magnitud y frecuencia dominante."""
    fs = _sample_rate(params)
    signal = _signal(params)
    n = signal.size
    window = np.hanning(n) if n > 1 else np.ones(1)
    spectrum = np.fft.rfft(signal * window)
    frequencies = np.fft.rfftfreq(n, d=1.0 / fs)
    magnitude = np.abs(spectrum) * 2.0 / max(float(np.sum(window)), 1e-30)
    if n > 1:
        magnitude[0] *= 0.5
        if n % 2 == 0:
            magnitude[-1] *= 0.5
    dominant_index = int(np.argmax(magnitude))
    dominant_frequency = float(frequencies[dominant_index])
    if 0 < dominant_index < len(magnitude) - 1:
        left, center, right = np.log(np.maximum(magnitude[dominant_index - 1:dominant_index + 2], 1e-30))
        denominator = left - 2.0 * center + right
        if abs(denominator) > 1e-30:
            offset = 0.5 * (left - right) / denominator
            if abs(offset) <= 1.0:
                bin_width = fs / n
                dominant_frequency = float(frequencies[dominant_index] + offset * bin_width)
    return {
        "frequencies_hz": frequencies.tolist(),
        "magnitude": magnitude.tolist(),
        "dominant_frequency_hz": dominant_frequency,
        "dominant_magnitude": float(magnitude[dominant_index]),
        "sample_rate": fs,
        "n_samples": n,
    }


def convolve_ir(params):
    """Convolucion lineal de una senal con una respuesta al impulso."""
    signal = _signal(params)
    impulse_response = _signal(params, "ir")
    full = fftconvolve(signal, impulse_response, mode="full")
    mode = str(params.get("mode", "same"))
    if mode == "full":
        output = full
    elif mode == "same":
        start = (full.size - signal.size) // 2
        output = full[start:start + signal.size]
    else:
        raise ValueError("mode debe ser 'same' o 'full'")
    return {
        "signal": output.tolist(),
        "length_in": int(signal.size),
        "length_ir": int(impulse_response.size),
        "length_out": int(output.size),
        "mode": mode,
        "peak": float(np.max(np.abs(output))),
        "rms": float(np.sqrt(np.mean(np.square(output)))),
    }


def _frames(signal, frame_length, hop_length):
    n = signal.size
    if n < frame_length:
        frame_length = n
        hop_length = max(1, frame_length // 4)
    starts = list(range(0, n - frame_length + 1, hop_length))
    if not starts:
        starts = [0]
    window = np.hanning(frame_length) if frame_length > 1 else np.ones(1)
    return starts, window


def spectral_subtract(params):
    """Reduccion espectral condicionada por unaestimate de ruido."""
    signal = _signal(params)
    frame_length = int(params.get("frame_length", 1024))
    frame_length = max(2, min(frame_length, signal.size))
    hop_length = int(params.get("hop_length", max(1, frame_length // 4)))
    alpha = float(params.get("alpha", 1.5))
    floor_ratio = float(params.get("floor_ratio", 0.02))
    noise_fraction = float(params.get("noise_fraction", 0.2))
    starts, window = _frames(signal, frame_length, hop_length)
    spectra = []
    for start in starts:
        frame = signal[start:start + frame_length]
        spectra.append(np.fft.rfft(frame * window))
    spectra = np.asarray(spectra)
    magnitudes = np.abs(spectra)
    noise_frames = max(1, int(round(len(starts) * min(max(noise_fraction, 0.0), 1.0))))
    noise_profile = np.mean(magnitudes[:noise_frames], axis=0)
    cleaned_magnitudes = np.maximum(magnitudes - alpha * noise_profile, floor_ratio * noise_profile)
    cleaned_spectra = spectra * (cleaned_magnitudes / np.maximum(magnitudes, 1e-30))
    output = np.zeros(signal.size, dtype=float)
    normalization = np.zeros(signal.size, dtype=float)
    for index, start in enumerate(starts):
        frame = np.fft.irfft(cleaned_spectra[index], n=frame_length) * window
        output[start:start + frame_length] += frame
        normalization[start:start + frame_length] += window * window
    output /= np.maximum(normalization, 1e-12)
    noise_rms = float(np.sqrt(np.mean(np.square(noise_profile))) / max(float(np.sum(window)), 1e-30))
    signal_rms = float(np.sqrt(np.mean(np.square(signal))))
    output_rms = float(np.sqrt(np.mean(np.square(output))))
    snr_before = None
    snr_after = None
    if noise_rms > 0.0:
        snr_before = 20.0 * math.log10(max(signal_rms, 1e-30) / noise_rms)
        snr_after = 20.0 * math.log10(max(output_rms, 1e-30) / noise_rms)
    return {
        "signal": output.tolist(),
        "noise_rms_estimate": noise_rms,
        "snr_before_db": snr_before,
        "snr_after_db": snr_after,
        "snr_improvement_db": None if snr_before is None else snr_after - snr_before,
        "frame_length": frame_length,
        "hop_length": hop_length,
        "alpha": alpha,
        "noise_frames": noise_frames,
    }


def _frame_envelope(signal, fs, frame_seconds=0.01):
    frame_length = max(1, int(round(frame_seconds * fs)))
    hop_length = max(1, frame_length // 2)
    starts = list(range(0, max(1, signal.size - frame_length + 1), hop_length))
    values = []
    for start in starts:
        frame = signal[start:start + frame_length]
        values.append(float(np.sqrt(np.mean(np.square(frame)))))
    return np.asarray(values), starts, frame_length, hop_length


def ducking_gain(params):
    """Ducking por enveloped de control, con ataque y liberacion."""
    signal = _signal(params)
    fs = _sample_rate(params)
    control = _signal(params, "control") if "control" in params else signal
    threshold_dbfs = float(params.get("threshold_dbfs", -40.0))
    reduction_db = float(params.get("reduction_db", 12.0))
    range_db = float(params.get("range_db", 20.0))
    attack_ms = float(params.get("attack_ms", 10.0))
    release_ms = float(params.get("release_ms", 250.0))
    envelope, starts, frame_length, hop_length = _frame_envelope(control, fs)
    envelope_db = 20.0 * np.log10(np.maximum(envelope, 1e-15))
    amount = np.clip((envelope_db - threshold_dbfs) / max(range_db, 1e-12), 0.0, 1.0)
    desired_db = -reduction_db * amount
    attack_frames = max(1.0, attack_ms * fs / 1000.0 / hop_length)
    release_frames = max(1.0, release_ms * fs / 1000.0 / hop_length)
    smoothed = np.empty_like(desired_db)
    current = 0.0
    for index, target in enumerate(desired_db):
        time_constant = attack_frames if target < current else release_frames
        coefficient = math.exp(-1.0 / time_constant)
        current = target + coefficient * (current - target)
        smoothed[index] = current
    sample_gain = np.interp(np.arange(signal.size), np.asarray(starts), smoothed)
    output = signal * np.power(10.0, sample_gain / 20.0)
    return {
        "signal": output.tolist(),
        "gain_db": sample_gain.tolist(),
        "gain_min_db": float(np.min(sample_gain)),
        "gain_max_db": float(np.max(sample_gain)),
        "mean_gain_db": float(np.mean(sample_gain)),
        "attack_ms": attack_ms,
        "release_ms": release_ms,
        "threshold_dbfs": threshold_dbfs,
        "reduction_db": reduction_db,
    }


def silence_samples(params):
    """Deteccion de pausas por umbral absoluto en dBFS."""
    signal = _signal(params)
    fs = _sample_rate(params)
    threshold_dbfs = float(params.get("threshold_dbfs", -60.0))
    minimum_duration_ms = float(params.get("minimum_duration_ms", 100.0))
    max_gap_ms = float(params.get("max_gap_ms", 0.0))
    threshold = 10.0 ** (threshold_dbfs / 20.0)
    silent = np.abs(signal) <= threshold
    minimum_samples = max(1, int(round(minimum_duration_ms * fs / 1000.0)))
    max_gap_samples = max(0, int(round(max_gap_ms * fs / 1000.0)))
    runs = []
    index = 0
    while index < signal.size:
        if not silent[index]:
            index += 1
            continue
        start = index
        while index < signal.size and silent[index]:
            index += 1
        runs.append([start, index])
    merged = []
    for run in runs:
        if merged and run[0] - merged[-1][1] <= max_gap_samples:
            merged[-1][1] = run[1]
        else:
            merged.append(run)
    selected = [run for run in merged if run[1] - run[0] >= minimum_samples]
    pauses = []
    for start, end in selected:
        pauses.append({
            "start_sample": start,
            "end_sample": end,
            "n_samples": end - start,
            "duration_seconds": (end - start) / fs,
        })
    return {
        "pauses": pauses,
        "count": len(pauses),
        "total_samples": int(sum(pause["n_samples"] for pause in pauses)),
        "total_seconds": float(sum(pause["duration_seconds"] for pause in pauses)),
        "threshold_dbfs": threshold_dbfs,
        "minimum_duration_ms": minimum_duration_ms,
    }


def _count_click_runs(candidates, merge_samples=2):
    indices = np.flatnonzero(candidates)
    if indices.size == 0:
        return 0, []
    clusters = [[int(indices[0]), int(indices[0])]]
    for index in indices[1:]:
        if int(index) - clusters[-1][1] <= merge_samples + 1:
            clusters[-1][1] = int(index)
        else:
            clusters.append([int(index), int(index)])
    return len(clusters), clusters


def _residuo_local(signal, fs, block_ms=5.0):
    """Residuo de tres puntos y escalas locales de curvatura y nivel.

    Un clic es una discontinuidad aislada: la muestra se aparta de la media de
    sus vecinas. El residuo `x[i] - (x[i-1] + x[i+1]) / 2` mide ese apartamiento
    y vale cero en un tramo suave. Se acompaña de dos escalas locales por
    bloques de `block_ms`: la mediana de |residuo| (suavidad tipica del entorno)
    y el RMS de la senal (nivel local), para que el umbral se adapte al material.
    """
    n = signal.size
    residuo = np.zeros(n)
    if n > 2:
        residuo[1:-1] = signal[1:-1] - (signal[:-2] + signal[2:]) / 2.0
    block = max(3, int(round(fs * block_ms / 1000.0)))
    bloques = n // block + 1
    relleno = bloques * block - n
    senal = np.pad(signal, (0, relleno), mode="constant")
    bloques_senal = senal.reshape(bloques, block)
    rms = np.sqrt(np.maximum(np.mean(np.square(bloques_senal), axis=1), 1e-20))
    magnitud = np.pad(np.abs(residuo), (0, relleno), mode="constant")
    mediana = np.median(magnitud.reshape(bloques, block), axis=1)
    return residuo, np.repeat(rms, block)[:n], np.repeat(mediana, block)[:n]


def _detectar_clics(signal, fs, k_local=12.0, fraccion_rms=0.5):
    """Detecta discontinuidades aisladas comparando con las escalas locales.

    El criterio antiguo (salto entre muestras por encima de un suelo absoluto)
    marcaba cualquier transicion brusca de la voz real como clic: en habla
    limpia a 48 kHz devolvia miles de falsos positivos y `limpiar_clics`
    interpolaba zonas que no estaban danadas. El umbral combina la suavidad
    local (mediana del residuo) con el nivel local (RMS), de modo que el mismo
    criterio sirve para voz, musica y ruido.
    """
    residuo, rms_local, mediana_local = _residuo_local(signal, fs)
    magnitud = np.abs(residuo)
    umbral = np.maximum(k_local * mediana_local, fraccion_rms * rms_local)
    candidatos = magnitud > umbral
    # Un clic es un transitorio breve: agrupamos candidatos separados por menos
    # de 1 ms para no contar cada muestra de un mismo burst como un clic.
    merge_samples = max(2, int(round(fs / 1000.0)))
    conteo, clusters = _count_click_runs(candidatos, merge_samples=merge_samples)
    return conteo, clusters, float(np.median(umbral)) if umbral.size else 0.0


def diagnostico_toma(params):
    """Diagnostico tecnico de una toma: DC, clipping, ruido, SNR y clics."""
    signal = _signal(params)
    fs = _sample_rate(params)
    clipping_threshold = float(params.get("clipping_threshold", 0.999))
    dc_offset = float(np.mean(signal))
    centered = signal - dc_offset
    peak = float(np.max(np.abs(centered)))
    rms = float(np.sqrt(np.mean(np.square(centered))))
    clipped = int(np.sum(np.abs(signal) >= clipping_threshold))
    frame_length = max(1, int(round(0.02 * fs)))
    frame_rms = []
    for start in range(0, signal.size, frame_length):
        frame = centered[start:start + frame_length]
        if frame.size:
            frame_rms.append(float(np.sqrt(np.mean(np.square(frame)))))
    frame_rms = np.asarray(frame_rms)
    percentile = float(params.get("noise_percentile", 10.0))
    noise_floor_linear = float(np.percentile(frame_rms, percentile)) if frame_rms.size else 0.0
    snr_db = None
    if noise_floor_linear > 0.0 and rms > 0.0:
        snr_db = 20.0 * math.log10(rms / noise_floor_linear)
    derivative = np.diff(centered)
    if derivative.size:
        median = float(np.median(derivative))
        mad = float(np.median(np.abs(derivative - median)))
        robust_sigma = 1.4826 * mad
    else:
        robust_sigma = 0.0
    click_count, click_clusters, click_threshold = _detectar_clics(centered, fs)
    return {
        "duration_seconds": signal.size / fs,
        "dc_offset": dc_offset,
        "peak": peak,
        "peak_dbfs": _db(peak),
        "rms": rms,
        "rms_dbfs": _db(rms),
        "crest_factor_db": None if rms <= 0.0 else 20.0 * math.log10(peak / rms),
        "clipping_threshold": clipping_threshold,
        "clipped_samples": clipped,
        "clipping_percent": 100.0 * clipped / signal.size,
        "noise_floor_dbfs": _db(noise_floor_linear),
        "snr_db": snr_db,
        "click_count": click_count,
        "click_clusters": click_clusters,
        "click_threshold": click_threshold,
        "click_criterio": "residuo de tres puntos frente a escala local (mediana de curvatura y RMS local)",
        "click_escala_sigma_local": 12.0,
        "click_fraccion_rms_local": 0.5,
        "derivative_robust_sigma": robust_sigma,
    }


def _write_wav(path, signal, fs):
    pcm = np.clip(np.asarray(signal, dtype=float), -1.0, 1.0)
    pcm16 = np.round(pcm * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(round(fs)))
        handle.writeframes(pcm16.tobytes())


def _ffmpeg_ebur128(path):
    if shutil.which("ffmpeg") is None:
        return {"available": False}
    process = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-nostdin", "-i", str(path),
            "-af", "ebur128=peak=true", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    text = process.stdout + process.stderr
    integrated = re.findall(r"\bI:\s*(-?\d+(?:\.\d+)?)\s*LUFS", text)
    peaks = re.findall(r"\bPeak:\s*(-?\d+(?:\.\d+)?)\s*dBFS", text)
    if not integrated:
        return {"available": True, "ok": False, "raw_tail": text[-1200:]}
    return {
        "available": True,
        "ok": process.returncode == 0,
        "integrated_lufs": float(integrated[-1]),
        "true_peak_dbfs": float(peaks[-1]) if peaks else None,
        "returncode": process.returncode,
    }


def validate(params=None):
    """Autochequeos contra valores analiticos, NumPy, SciPy y FFmpeg."""
    fs = 48000.0
    duration = 2.0
    time = np.arange(int(fs * duration)) / fs
    sine = 0.5 * np.sin(2.0 * np.pi * 1000.0 * time)
    constant = np.full(4096, 0.5)
    checks = []
    results = {}

    rms_result = rms_db({"signal": constant, "fs": fs})
    rms_error = abs(rms_result["rms_dbfs"] - (-6.020599913279624))
    checks.append({"name": "rms_db_against_analytic", "passed": rms_error < 1e-10})
    results["rms_db"] = rms_result

    peak_result = true_peak({"signal": sine, "fs": fs})
    peak_error = abs(peak_result["true_peak_dbfs"] - (-6.020599913279624))
    checks.append({"name": "true_peak_against_analytic", "passed": peak_error < 0.02})
    results["true_peak"] = peak_result

    lufs_amplitude = 10.0 ** (-23.0 / 20.0)
    lufs_sine = lufs_amplitude * np.sin(2.0 * np.pi * 1000.0 * time)
    lufs_result = lufs_kweight({"signal": lufs_sine, "fs": fs})
    expected_lufs = -26.0
    lufs_error = abs(lufs_result["integrated_lufs"] - expected_lufs)
    checks.append({"name": "lufs_kweight_against_analytic", "passed": lufs_error < 0.2})
    results["lufs_kweight"] = lufs_result

    ffmpeg_result = {"available": False, "skipped": True}
    with tempfile.TemporaryDirectory(prefix="audio-math-") as temporary:
        wav_path = Path(temporary) / "tone.wav"
        _write_wav(wav_path, lufs_sine, fs)
        ffmpeg_result = _ffmpeg_ebur128(wav_path)
    if ffmpeg_result.get("available"):
        ffmpeg_error = abs(ffmpeg_result["integrated_lufs"] - lufs_result["integrated_lufs"])
        checks.append({
            "name": "lufs_against_ffmpeg_ebur128",
            "passed": bool(ffmpeg_result.get("ok")) and ffmpeg_error < 0.3,
            "absolute_error_lu": ffmpeg_error,
        })
    else:
        checks.append({"name": "lufs_against_ffmpeg_ebur128", "passed": True, "skipped": True})
    results["ffmpeg_ebur128"] = ffmpeg_result

    spectrum_result = fft_spectrum({"signal": sine, "fs": fs})
    spectrum_error = abs(spectrum_result["dominant_frequency_hz"] - 1000.0)
    checks.append({"name": "fft_dominant_frequency", "passed": spectrum_error < 1.0})
    results["fft_spectrum"] = {
        "dominant_frequency_hz": spectrum_result["dominant_frequency_hz"],
        "dominant_magnitude": spectrum_result["dominant_magnitude"],
    }

    impulse = np.zeros(128)
    impulse[0] = 1.0
    identity = convolve_ir({"signal": sine[:1024], "ir": impulse, "fs": fs, "mode": "full"})
    identity_error = float(np.max(np.abs(np.asarray(identity["signal"][:1024]) - sine[:1024])))
    checks.append({"name": "convolution_identity", "passed": identity_error < 1e-12})
    delayed_ir = np.zeros(16)
    delayed_ir[4] = 1.0
    delayed = convolve_ir({"signal": sine[:1024], "ir": delayed_ir, "fs": fs, "mode": "full"})
    expected_delayed = np.zeros(1024 + delayed_ir.size - 1)
    expected_delayed[4:4 + 1024] = sine[:1024]
    delayed_error = float(np.max(np.abs(np.asarray(delayed["signal"]) - expected_delayed)))
    checks.append({"name": "convolution_delay", "passed": delayed_error < 1e-12})
    results["convolve_ir"] = {"identity_error": identity_error, "delay_error": delayed_error}

    rng = np.random.default_rng(20261117)
    noise = rng.normal(0.0, 0.02, 8192)
    tone = 0.25 * np.sin(2.0 * np.pi * 1000.0 * np.arange(8192) / fs)
    noisy = np.concatenate([noise[:4096], tone[:4096] + noise[4096:]])
    subtraction = spectral_subtract({"signal": noisy, "fs": fs})
    improvement = subtraction["snr_improvement_db"]
    checks.append({
        "name": "spectral_subtraction_improves_snr",
        "passed": improvement is not None and improvement > 0.0,
    })
    results["spectral_subtract"] = {"snr_improvement_db": improvement}

    control = np.concatenate([np.zeros(int(fs // 2)), np.ones(int(fs // 2))])
    ducking = ducking_gain({"signal": np.ones(int(fs)), "control": control, "fs": fs})
    active_gain = float(np.mean(ducking["gain_db"][int(fs * 0.7):int(fs * 0.9)]))
    checks.append({"name": "ducking_applies_reduction", "passed": active_gain < -5.0})
    results["ducking_gain"] = {"active_mean_gain_db": active_gain}

    silence_signal = np.concatenate([np.ones(1000), np.zeros(2000), np.ones(1000)])
    silence = silence_samples({"signal": silence_signal, "fs": fs, "minimum_duration_ms": 10.0})
    silence_ok = silence["count"] == 1 and silence["pauses"][0]["n_samples"] == 2000
    checks.append({"name": "silence_detection", "passed": silence_ok})
    results["silence_samples"] = silence

    diagnostic_signal = np.concatenate([np.full(1000, 0.1), np.array([1.0, 1.0, -1.0, -1.0])])
    diagnostic = diagnostico_toma({"signal": diagnostic_signal, "fs": fs})
    diagnostic_ok = diagnostic["clipped_samples"] == 4 and diagnostic["click_count"] >= 1
    checks.append({"name": "diagnostic_clipping_and_clicks", "passed": diagnostic_ok})
    results["diagnostico_toma"] = diagnostic

    return {
        "checks": checks,
        "results": results,
        "validation_passed": bool(all(check["passed"] for check in checks)),
    }


AUDIO_MATH_TOOL_SCHEMA = {
    "name": "audio_math_tool",
    "description": (
        "Matematica de audio para audiolibros: RMS en dBFS, loudness integrado "
        "LUFS con K-weighting EBU R128, true peak sobremuestreado, espectro FFT, "
        "convolucion con respuesta al impulso, reduccion espectral de ruido, "
        "ducking por envolvente, deteccion de pausas y diagnostico de toma. "
        "Todos los modos reciben muestras en 'signal' y frecuencia en 'fs'. "
        "mode='validate' compara RMS/LUFS/true peak con valores analiticos y "
        "LUFS con FFmpeg ebur128 cuando esta disponible."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "rms_db",
                    "lufs_kweight",
                    "true_peak",
                    "fft_spectrum",
                    "convolve_ir",
                    "spectral_subtract",
                    "ducking_gain",
                    "silence_samples",
                    "diagnostico_toma",
                    "validate",
                ],
            },
            "params": {
                "type": "object",
                "description": (
                    "Parametros del modo. 'signal' es un vector mono o una matriz "
                    "canales x muestras; 'fs' es la frecuencia de muestreo. Los "
                    "modos que transforman la senal devuelven 'signal' en la salida."
                ),
            },
        },
        "required": ["mode"],
    },
}


def compute_audio_math(mode, params=None):
    params = params or {}
    modes = {
        "rms_db": rms_db,
        "lufs_kweight": lufs_kweight,
        "true_peak": true_peak,
        "fft_spectrum": fft_spectrum,
        "convolve_ir": convolve_ir,
        "spectral_subtract": spectral_subtract,
        "ducking_gain": ducking_gain,
        "silence_samples": silence_samples,
        "diagnostico_toma": diagnostico_toma,
        "validate": validate,
    }
    if mode not in modes:
        raise ValueError(f"modo desconocido: {mode}")
    return modes[mode](params)


if __name__ == "__main__":
    result = compute_audio_math("validate")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    assert result["validation_passed"], "Validacion fallo"
    print("\nOK audio_math_tool.py")


def _handler(args):
    return compute_audio_math(args.get("mode"), args.get("params"))


tool_registry.register_tool("audio_math_tool", AUDIO_MATH_TOOL_SCHEMA, _handler)
