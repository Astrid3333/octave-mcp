"""
genome_signal_analysis_tool.py

Analisis de senal (DSP) sobre secuencias genomicas: mapeo de bases a valores
numericos ("spin-like"), transformada de Fourier discreta (DFT), y deteccion
del pico de periodicidad-3 (senal clasica de regiones codificantes, Voss 1992
/ Anastassiou 2001).

Modos:
  - dft_spectrum: mapea la secuencia a senal numerica y calcula el espectro
    de potencia via DFT, reportando el SNR del pico en periodo=3.
  - spin_mapping: mapea la secuencia a un estado "spin-like" (+-1, +-i) y
    devuelve estadisticos simples (analogo a magnetizacion neta).
  - validate: corre una secuencia sintetica period-3 conocida y confirma
    que el pico se detecta donde se espera.

Convencion de mapeo 'complex_spin' (Anastassiou / DSP genomico clasico):
    A -> 1+0j   T/U -> -1+0j   G -> 0+1j   C -> 0-1j
Convencion 'eiip' (Electron-Ion Interaction Potential, Nair & Sreenadhan 2006):
    A -> 0.1260   T/U -> 0.1335   G -> 0.0806   C -> 0.1340
Convencion 'purine_pyrimidine':
    A,G (purinas) -> +1   C,T/U (pirimidinas) -> -1
"""

import numpy as np

_COMPLEX_SPIN = {"A": 1 + 0j, "T": -1 + 0j, "U": -1 + 0j, "G": 0 + 1j, "C": 0 - 1j}
_EIIP = {"A": 0.1260, "T": 0.1335, "U": 0.1335, "G": 0.0806, "C": 0.1340}
_PURINE_PYRIMIDINE = {"A": 1.0, "G": 1.0, "C": -1.0, "T": -1.0, "U": -1.0}

_MAPPINGS = {
    "complex_spin": _COMPLEX_SPIN,
    "eiip": _EIIP,
    "purine_pyrimidine": _PURINE_PYRIMIDINE,
}


def _sequence_to_signal(sequence, mapping):
    seq = sequence.strip().upper()
    if mapping not in _MAPPINGS:
        raise ValueError(f"mapping desconocido: {mapping}. Use uno de {list(_MAPPINGS)}")
    table = _MAPPINGS[mapping]
    bad = set(seq) - set(table.keys())
    if bad:
        raise ValueError(f"simbolos no soportados por el mapeo '{mapping}': {sorted(bad)}")
    signal = np.array([table[b] for b in seq])
    return signal, seq


def _period3_snr(power_spectrum, n):
    """SNR del pico en periodo=3 (frecuencia = n/3) contra el ruido de fondo
    (promedio del espectro excluyendo el propio pico y su vecindad inmediata)."""
    if n < 9:
        return None, None
    k3 = int(round(n / 3.0))
    if k3 <= 0 or k3 >= len(power_spectrum):
        return None, None
    peak = power_spectrum[k3]
    mask = np.ones(len(power_spectrum), dtype=bool)
    lo, hi = max(0, k3 - 1), min(len(power_spectrum), k3 + 2)
    mask[lo:hi] = False
    mask[0] = False  # excluir componente DC
    background = power_spectrum[mask]
    noise_mean = float(np.mean(background)) if background.size else 1e-12
    snr = float(peak / noise_mean) if noise_mean > 0 else float("inf")
    return snr, k3


def _dft_spectrum(sequence, mapping="complex_spin", detrend=True):
    signal, seq = _sequence_to_signal(sequence, mapping)
    n = len(signal)
    if detrend:
        signal = signal - np.mean(signal)
    spectrum = np.fft.fft(signal)
    power = (np.abs(spectrum) ** 2) / n
    freqs = np.fft.fftfreq(n)
    # solo frecuencias positivas (senal real o compleja, nos interesa 0..n/2)
    half = n // 2 + 1
    power_half = power[:half]
    freqs_half = freqs[:half]
    dominant_idx = int(np.argmax(power_half[1:]) + 1) if half > 1 else 0
    dominant_period = float(1.0 / freqs_half[dominant_idx]) if freqs_half[dominant_idx] != 0 else None
    snr3, k3 = _period3_snr(power_half, n)
    return {
        "mode": "dft_spectrum",
        "mapping": mapping,
        "n": n,
        "frequencies": freqs_half.tolist(),
        "power_spectrum": power_half.tolist(),
        "dominant_frequency_index": dominant_idx,
        "dominant_period": dominant_period,
        "period3_index": k3,
        "period3_snr": snr3,
        "coding_region_signal": bool(snr3 is not None and snr3 > 2.0),
        "note": "period3_snr > ~2 es indicativo clasico de region codificante (Voss 1992); no diagnostico por si solo.",
    }


def _spin_mapping(sequence, mapping="complex_spin"):
    signal, seq = _sequence_to_signal(sequence, mapping)
    n = len(signal)
    net = complex(np.sum(signal)) if np.iscomplexobj(signal) else float(np.sum(signal))
    magnetization = abs(net) / n if n else 0.0
    return {
        "mode": "spin_mapping",
        "mapping": mapping,
        "n": n,
        "spin_sequence_real": np.real(signal).tolist(),
        "spin_sequence_imag": (np.imag(signal).tolist() if np.iscomplexobj(signal) else None),
        "net_spin": [net.real, net.imag] if isinstance(net, complex) else net,
        "magnetization_per_site": magnetization,
    }


def _validate():
    # secuencia sintetica con periodicidad-3 fuerte: repetir un codon variado
    synthetic = ("ATG" * 40) + "CGT" * 5
    result = _dft_spectrum(synthetic, mapping="complex_spin")
    ok = result["period3_snr"] is not None and result["period3_snr"] > 5.0
    return {
        "mode": "validate",
        "synthetic_length": len(synthetic),
        "period3_snr": result["period3_snr"],
        "expected": "SNR alto (>5) por periodicidad-3 sintetica inyectada",
        "validation_passed": bool(ok),
    }


def compute_genome_signal_analysis(mode, **kwargs):
    if mode == "dft_spectrum":
        return _dft_spectrum(
            kwargs["sequence"],
            mapping=kwargs.get("mapping", "complex_spin"),
            detrend=kwargs.get("detrend", True),
        )
    elif mode == "spin_mapping":
        return _spin_mapping(kwargs["sequence"], mapping=kwargs.get("mapping", "complex_spin"))
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"mode desconocido: {mode}")


GENOME_SIGNAL_ANALYSIS_SCHEMA = {
    "name": "genome_signal_analysis",
    "description": (
        "Analisis de senal digital sobre secuencias genomicas: mapeo de bases a valores "
        "numericos/spin-like (complex_spin, eiip, purine_pyrimidine) y espectro de potencia "
        "via DFT, con deteccion del pico de periodicidad-3 asociado a regiones codificantes "
        "(Voss 1992, Anastassiou 2001). mode='dft_spectrum' (sequence, mapping, detrend); "
        "mode='spin_mapping' (sequence, mapping); mode='validate' corre un caso sintetico "
        "con periodicidad-3 inyectada."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["dft_spectrum", "spin_mapping", "validate"],
                "default": "validate",
            },
            "sequence": {
                "type": "string",
                "description": "Secuencia de nucleotidos (A,T/U,G,C). Requerido salvo mode=validate.",
            },
            "mapping": {
                "type": "string",
                "enum": ["complex_spin", "eiip", "purine_pyrimidine"],
                "default": "complex_spin",
                "description": "Esquema de mapeo base->numero.",
            },
            "detrend": {
                "type": "boolean",
                "default": True,
                "description": "Restar la media antes de la DFT (solo dft_spectrum).",
            },
        },
        "required": ["mode"],
    },
}
