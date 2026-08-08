#!/usr/bin/env python3
"""
wavelet_tool.py
Analisis wavelet para senales no estacionarias: transformada continua (CWT)
con espectrograma tiempo-escala, transformada discreta (DWT) multinivel con
reconstruccion, denoising por umbralizacion de coeficientes wavelet, y
deteccion de transitorios/eventos via energia por banda de escala. Complementa
a hilbert_tool: Hilbert da fase/amplitud instantanea de una banda ya conocida,
wavelet resuelve la localizacion tiempo-frecuencia completa sin asumir
estacionariedad - relevante para transitorios en mediciones de campo electrico
atmosferico o en la respuesta electrica de TritOS ante eventos discretos.
"""
import numpy as np
import pywt


def compute_cwt(signal, sampling_rate, wavelet="morl", scales=None, n_scales=64):
    signal = np.asarray(signal, dtype=float)
    n = len(signal)
    if scales is None:
        scales = np.geomspace(1, n / 8, n_scales)
    coeffs, freqs = pywt.cwt(signal, scales, wavelet, sampling_period=1.0 / sampling_rate)
    power = np.abs(coeffs) ** 2
    # energia total por escala, y el tiempo (indice) donde cada escala tiene su pico
    energy_per_scale = power.sum(axis=1)
    peak_time_idx = power.argmax(axis=1)
    dominant_scale_idx = int(energy_per_scale.argmax())
    return {
        "mode": "cwt", "wavelet": wavelet,
        "n_samples": n, "n_scales": len(scales),
        "frequencies_hz": [round(float(f), 6) for f in freqs],
        "scales": [round(float(s), 4) for s in scales],
        "energy_per_scale": [round(float(e), 6) for e in energy_per_scale],
        "dominant_frequency_hz": round(float(freqs[dominant_scale_idx]), 6),
        "peak_time_index_per_scale": [int(t) for t in peak_time_idx],
        "scalogram_shape": list(power.shape),
        "scalogram_sample": [[round(float(x), 6) for x in row[::max(1, n // 20)]] for row in power[::max(1, len(scales) // 10)]],
    }


def compute_dwt(signal, wavelet="db4", level=None, mode="symmetric"):
    signal = np.asarray(signal, dtype=float)
    if level is None:
        level = pywt.dwt_max_level(len(signal), pywt.Wavelet(wavelet).dec_len)
    coeffs = pywt.wavedec(signal, wavelet, mode=mode, level=level)
    approx = coeffs[0]
    details = coeffs[1:]
    energy_per_level = [float(np.sum(d ** 2)) for d in details]
    total_energy = float(np.sum(signal ** 2))
    reconstructed = pywt.waverec(coeffs, wavelet, mode=mode)
    reconstruction_error = float(np.sqrt(np.mean((reconstructed[:len(signal)] - signal) ** 2)))
    return {
        "mode": "dwt", "wavelet": wavelet, "level": level,
        "n_samples": len(signal),
        "approximation_coeffs_sample": [round(float(x), 6) for x in approx[:20]],
        "n_approximation_coeffs": len(approx),
        "detail_coeffs_lengths": [len(d) for d in details],
        "energy_per_detail_level": [round(e, 6) for e in energy_per_level],
        "approximation_energy": round(float(np.sum(approx ** 2)), 6),
        "relative_energy_per_level_pct": [round(100 * e / total_energy, 4) for e in energy_per_level],
        "reconstruction_rmse": round(reconstruction_error, 10),
    }


def compute_denoise(signal, wavelet="db4", level=None, mode="symmetric", threshold_method="soft", threshold_value=None):
    signal = np.asarray(signal, dtype=float)
    if level is None:
        level = pywt.dwt_max_level(len(signal), pywt.Wavelet(wavelet).dec_len)
    coeffs = pywt.wavedec(signal, wavelet, mode=mode, level=level)
    if threshold_value is None:
        # umbral universal de Donoho-Johnstone, estimado con MAD del nivel de detalle mas fino
        sigma = np.median(np.abs(coeffs[-1])) / 0.6745
        threshold_value = sigma * np.sqrt(2 * np.log(len(signal)))
    denoised_coeffs = [coeffs[0]] + [
        pywt.threshold(c, threshold_value, mode=threshold_method) for c in coeffs[1:]
    ]
    denoised_signal = pywt.waverec(denoised_coeffs, wavelet, mode=mode)[:len(signal)]
    noise_removed = signal - denoised_signal
    snr_db = 10 * np.log10(np.sum(denoised_signal ** 2) / max(np.sum(noise_removed ** 2), 1e-12))
    return {
        "mode": "denoise", "wavelet": wavelet, "level": level,
        "threshold_method": threshold_method, "threshold_value": round(float(threshold_value), 6),
        "denoised_signal_sample": [round(float(x), 6) for x in denoised_signal[:30]],
        "n_samples": len(signal),
        "estimated_snr_db": round(float(snr_db), 4),
        "noise_energy_removed": round(float(np.sum(noise_removed ** 2)), 6),
    }


def compute_transient_detection(signal, sampling_rate, wavelet="db4", level=None, mode="symmetric", energy_threshold_std=3.0):
    """
    Detecta transitorios localizando picos de energia anomalos en los
    coeficientes de detalle por nivel (cada nivel corresponde aprox. a una
    banda de frecuencia diadica). Un evento discreto (ej. una descarga
    electrica breve) se ve como un pico de energia muy por encima del
    promedio en uno o mas niveles de detalle, localizado temporalmente por
    la posicion del coeficiente dentro de ese nivel.
    """
    signal = np.asarray(signal, dtype=float)
    n = len(signal)
    if level is None:
        level = pywt.dwt_max_level(n, pywt.Wavelet(wavelet).dec_len)
    coeffs = pywt.wavedec(signal, wavelet, mode=mode, level=level)
    events = []
    for lvl_idx, d in enumerate(coeffs[1:], start=1):
        band_energy = d ** 2
        mu, sigma = band_energy.mean(), band_energy.std()
        if sigma == 0:
            continue
        z = (band_energy - mu) / sigma
        hits = np.where(z > energy_threshold_std)[0]
        for h in hits:
            # tiempo aproximado: escalar posicion del coeficiente al dominio original
            t_sec = (h / len(d)) * (n / sampling_rate)
            events.append({
                "level": lvl_idx, "coeff_index": int(h),
                "approx_time_sec": round(float(t_sec), 6),
                "z_score": round(float(z[h]), 4),
            })
    events.sort(key=lambda e: -e["z_score"])
    return {
        "mode": "transient_detection", "wavelet": wavelet, "level": level,
        "energy_threshold_std": energy_threshold_std,
        "n_events_detected": len(events),
        "events": events[:50],
    }


def compute_wavelet(mode, **kwargs):
    """Dispatcher unico para el tool MCP wavelet, segun 'mode'."""
    fns = {
        "cwt": compute_cwt,
        "dwt": compute_dwt,
        "denoise": compute_denoise,
        "transient_detection": compute_transient_detection,
    }
    if mode not in fns:
        raise ValueError(f"mode desconocido: {mode}")
    return fns[mode](**kwargs)


WAVELET_TOOL_SCHEMA = {
    "name": "wavelet",
    "description": "Analisis wavelet para senales no estacionarias: CWT (espectrograma tiempo-escala), DWT multinivel con reconstruccion, denoising por umbralizacion (Donoho-Johnstone), y deteccion de transitorios via energia anomala por banda. Complementa a hilbert_tool para senales con eventos discretos o no estacionarias.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["cwt", "dwt", "denoise", "transient_detection"]},
            "signal": {"type": "array"}, "sampling_rate": {"type": "number"},
            "wavelet": {"type": "string"}, "scales": {"type": "array"}, "n_scales": {"type": "integer"},
            "level": {"type": "integer"}, "mode_boundary": {"type": "string"},
            "threshold_method": {"type": "string", "enum": ["soft", "hard"]}, "threshold_value": {"type": "number"},
            "energy_threshold_std": {"type": "number"},
        },
        "required": ["mode", "signal"],
    },
}


if __name__ == "__main__":
    rng = np.random.default_rng(42)
    fs = 200.0
    t = np.arange(0, 5, 1 / fs)
    # senal base de baja frecuencia + un transitorio breve tipo "descarga" a los 2.5s + ruido
    base = np.sin(2 * np.pi * 2 * t)
    transient = np.zeros_like(t)
    idx_burst = (t > 2.5) & (t < 2.55)
    transient[idx_burst] = 3 * np.sin(2 * np.pi * 40 * t[idx_burst])
    noisy = base + transient + rng.normal(0, 0.15, len(t))

    r1 = compute_wavelet(mode="cwt", signal=noisy.tolist(), sampling_rate=fs, n_scales=32)
    print({k: v for k, v in r1.items() if k != "scalogram_sample"})
    r2 = compute_wavelet(mode="dwt", signal=noisy.tolist(), wavelet="db4")
    print(r2)
    r3 = compute_wavelet(mode="denoise", signal=noisy.tolist(), wavelet="db4")
    print({k: v for k, v in r3.items() if k != "denoised_signal_sample"})
    r4 = compute_wavelet(mode="transient_detection", signal=noisy.tolist(), sampling_rate=fs, wavelet="db4", energy_threshold_std=2.5)
    print(r4)
