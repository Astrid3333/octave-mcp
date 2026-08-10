"""
optical_sequence_id_tool.py

Simula un patron de difraccion (aproximacion de Fraunhofer, campo lejano)
generado por una secuencia codificada como una modulacion de indice de
refraccion espacial, y permite "identificar" una secuencia desconocida por
correlacion cruzada de su patron de difraccion contra un banco de
referencias. Es un proxy optico-matematico (via FFT, que es exactamente la
transformada que rige la difraccion de Fraunhofer) util para pensar
biosensado optico de secuencias, no una simulacion fisica completa de un
experimento real.

Modos:
  - diffraction_pattern: sequence -> perfil de intensidad de difraccion
    (|FFT(apertura)|^2).
  - match_sequence: compara el patron de difraccion de una secuencia
    desconocida contra un diccionario de referencias via correlacion
    cruzada normalizada, devuelve ranking.
  - validate: una secuencia comparada contra si misma debe dar
    correlacion = 1.0 (match perfecto).
"""

import numpy as np

_EIIP = {"A": 0.1260, "T": 0.1335, "U": 0.1335, "G": 0.0806, "C": 0.1340}


def _sequence_to_aperture(sequence):
    seq = sequence.strip().upper()
    bad = set(seq) - set(_EIIP.keys())
    if bad:
        raise ValueError(f"simbolos no soportados: {sorted(bad)}")
    return np.array([_EIIP[b] for b in seq]), seq


def _diffraction_pattern(sequence, n_pad=512):
    aperture, seq = _sequence_to_aperture(sequence)
    n = len(aperture)
    if n_pad < n:
        n_pad = int(2 ** np.ceil(np.log2(n)))
    padded = np.zeros(n_pad)
    padded[:n] = aperture - np.mean(aperture)
    field = np.fft.fftshift(np.fft.fft(padded))
    intensity = np.abs(field) ** 2
    intensity = intensity / (np.max(intensity) if np.max(intensity) > 0 else 1.0)
    angle_axis = np.fft.fftshift(np.fft.fftfreq(n_pad))
    return {
        "mode": "diffraction_pattern",
        "sequence_length": n,
        "n_pad": n_pad,
        "spatial_frequency_axis": angle_axis.tolist(),
        "intensity_profile": intensity.tolist(),
        "peak_spatial_frequency": float(angle_axis[int(np.argmax(intensity))]),
    }


def _normalized_cross_correlation(a, b):
    a = a - np.mean(a)
    b = b - np.mean(b)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _match_sequence(unknown_sequence, reference_sequences, n_pad=512):
    unk = _diffraction_pattern(unknown_sequence, n_pad=n_pad)
    unk_profile = np.array(unk["intensity_profile"])
    scores = []
    for name, seq in reference_sequences.items():
        ref = _diffraction_pattern(seq, n_pad=n_pad)
        ref_profile = np.array(ref["intensity_profile"])
        score = _normalized_cross_correlation(unk_profile, ref_profile)
        scores.append({"reference_name": name, "correlation": score})
    scores.sort(key=lambda d: d["correlation"], reverse=True)
    return {
        "mode": "match_sequence",
        "unknown_length": len(unknown_sequence),
        "n_references": len(reference_sequences),
        "ranking": scores,
        "best_match": scores[0] if scores else None,
    }


def _validate():
    # nota: la intensidad de difraccion (|FFT|^2) es invariante ante reversion
    # de la secuencia (propiedad de simetria de la transformada), asi que la
    # referencia "distinta" debe ser genuinamente distinta en composicion,
    # no solo invertida, para que el test de identificacion sea significativo.
    seq = "ATGCGTACGGATTCA" * 4
    different = "CCCCGGGGAAAATTTT" * 4
    self_match = _match_sequence(seq, {"self": seq, "different": different})
    best = self_match["best_match"]
    ok = best["reference_name"] == "self" and best["correlation"] > 0.99
    return {
        "mode": "validate",
        "best_match": best,
        "expected": "la secuencia comparada contra si misma debe ganar con correlacion ~1.0 frente a una referencia de composicion distinta",
        "validation_passed": bool(ok),
    }


def compute_optical_sequence_id(mode, **kwargs):
    if mode == "diffraction_pattern":
        return _diffraction_pattern(kwargs["sequence"], n_pad=kwargs.get("n_pad", 512))
    elif mode == "match_sequence":
        return _match_sequence(
            kwargs["unknown_sequence"], kwargs["reference_sequences"], n_pad=kwargs.get("n_pad", 512)
        )
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"mode desconocido: {mode}")


OPTICAL_SEQUENCE_ID_SCHEMA = {
    "name": "optical_sequence_id",
    "description": (
        "Simula difraccion de Fraunhofer (via FFT) de una secuencia codificada como apertura "
        "de indice de refraccion (EIIP), y permite identificar una secuencia desconocida por "
        "correlacion cruzada de su patron de difraccion contra un banco de referencias. Proxy "
        "matematico de biosensado optico, no simulacion fisica completa. mode='diffraction_pattern' "
        "(sequence, n_pad); mode='match_sequence' (unknown_sequence, reference_sequences: dict "
        "nombre->secuencia, n_pad); mode='validate' confirma match perfecto contra si misma."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["diffraction_pattern", "match_sequence", "validate"],
                "default": "validate",
            },
            "sequence": {"type": "string", "description": "Secuencia ATGC/U. diffraction_pattern."},
            "unknown_sequence": {"type": "string", "description": "Secuencia a identificar. match_sequence."},
            "reference_sequences": {
                "type": "object",
                "description": "Diccionario {nombre: secuencia} de referencias. match_sequence.",
            },
            "n_pad": {
                "type": "integer",
                "default": 512,
                "description": "Tamano de FFT (zero-padding), potencia de 2 recomendada.",
            },
        },
        "required": ["mode"],
    },
}
