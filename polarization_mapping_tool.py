"""
polarization_mapping_tool.py

Mapea una secuencia (nucleotidos o aminoacidos) a estados de polarizacion
optica y calcula el vector de Stokes (S0,S1,S2,S3) agregado y por ventana
deslizante, junto con el grado de polarizacion (DOP).

Cada simbolo se mapea a un par (angulo de polarizacion psi, elipticidad chi)
via una tabla fija; esto es un proxy matematico (no una medicion optica real)
util para explorar si existe estructura de "polarizacion neta" en tramos de
una secuencia, analogo a la idea de optical_sequence_id_tool.

Convencion del vector de Stokes normalizado (S0=1 por simbolo, coherente):
    S1 = cos(2*psi)*cos(2*chi)
    S2 = sin(2*psi)*cos(2*chi)
    S3 = sin(2*chi)
Agregando sobre una ventana de N simbolos con suma vectorial (like sumar
Stokes de fuentes incoherentes) y luego normalizando por N.

Modos:
  - sequence_to_stokes: Stokes agregado de una secuencia completa.
  - windowed_stokes: Stokes por ventana deslizante (perfil a lo largo de la
    secuencia).
  - validate: secuencia homogenea (single simbolo repetido) debe dar DOP=1.
"""

import numpy as np

# angulos de polarizacion (psi, grados) y elipticidad (chi, grados) por base.
# Asignacion arbitraria pero fija y reproducible, espaciada uniformemente en
# el circulo de Poincare para las 4 bases de ADN; aminoacidos reusan el
# alfabeto extendido con 20 puntos espaciados.
_DNA_ANGLES = {
    "A": (0.0, 0.0),
    "T": (90.0, 0.0),
    "U": (90.0, 0.0),
    "G": (45.0, 45.0),
    "C": (135.0, -45.0),
}

_AA_ORDER = list("ACDEFGHIKLMNPQRSTVWY")
_AA_ANGLES = {
    aa: (i * (180.0 / len(_AA_ORDER)), 45.0 * np.cos(2 * np.pi * i / len(_AA_ORDER)))
    for i, aa in enumerate(_AA_ORDER)
}


def _angles_for(alphabet):
    if alphabet == "dna":
        return _DNA_ANGLES
    elif alphabet == "protein":
        return _AA_ANGLES
    else:
        raise ValueError("alphabet debe ser 'dna' o 'protein'")


def _symbol_to_stokes(psi_deg, chi_deg):
    psi = np.radians(psi_deg)
    chi = np.radians(chi_deg)
    s1 = np.cos(2 * psi) * np.cos(2 * chi)
    s2 = np.sin(2 * psi) * np.cos(2 * chi)
    s3 = np.sin(2 * chi)
    return np.array([1.0, s1, s2, s3])


def _sequence_stokes_array(sequence, alphabet):
    table = _angles_for(alphabet)
    seq = sequence.strip().upper()
    bad = set(seq) - set(table.keys())
    if bad:
        raise ValueError(f"simbolos no soportados para alphabet='{alphabet}': {sorted(bad)}")
    return np.array([_symbol_to_stokes(*table[s]) for s in seq]), seq


def _aggregate_stokes(stokes_array):
    n = len(stokes_array)
    agg = np.mean(stokes_array, axis=0)  # S0 queda ~1, S1..S3 se promedian (incoherente)
    s0, s1, s2, s3 = agg
    dop = float(np.sqrt(s1**2 + s2**2 + s3**2) / s0) if s0 != 0 else 0.0
    psi = float(0.5 * np.degrees(np.arctan2(s2, s1)))
    chi = float(0.5 * np.degrees(np.arcsin(np.clip(s3, -1.0, 1.0))))
    return {
        "n_symbols": n,
        "S0": float(s0),
        "S1": float(s1),
        "S2": float(s2),
        "S3": float(s3),
        "degree_of_polarization": dop,
        "mean_psi_deg": psi,
        "mean_chi_deg": chi,
    }


def _sequence_to_stokes(sequence, alphabet="dna"):
    arr, seq = _sequence_stokes_array(sequence, alphabet)
    result = _aggregate_stokes(arr)
    result["mode"] = "sequence_to_stokes"
    result["alphabet"] = alphabet
    return result


def _windowed_stokes(sequence, alphabet="dna", window=20, step=10):
    arr, seq = _sequence_stokes_array(sequence, alphabet)
    n = len(arr)
    if window <= 0 or window > n:
        raise ValueError("window debe ser > 0 y <= largo de la secuencia")
    profile = []
    positions = []
    for start in range(0, n - window + 1, step):
        chunk = arr[start : start + window]
        stats = _aggregate_stokes(chunk)
        profile.append(stats)
        positions.append(start)
    return {
        "mode": "windowed_stokes",
        "alphabet": alphabet,
        "window": window,
        "step": step,
        "n_windows": len(profile),
        "start_positions": positions,
        "profile": profile,
    }


def _validate():
    homogeneous = "A" * 50
    stats = _sequence_to_stokes(homogeneous, alphabet="dna")
    ok = abs(stats["degree_of_polarization"] - 1.0) < 1e-9
    mixed = "ATGC" * 20
    stats_mixed = _sequence_to_stokes(mixed, alphabet="dna")
    return {
        "mode": "validate",
        "homogeneous_dop": stats["degree_of_polarization"],
        "mixed_dop": stats_mixed["degree_of_polarization"],
        "expected": "secuencia homogenea -> DOP=1 (totalmente polarizada); secuencia mixta -> DOP menor",
        "validation_passed": bool(ok and stats_mixed["degree_of_polarization"] < stats["degree_of_polarization"]),
    }


def compute_polarization_mapping(mode, **kwargs):
    if mode == "sequence_to_stokes":
        return _sequence_to_stokes(kwargs["sequence"], alphabet=kwargs.get("alphabet", "dna"))
    elif mode == "windowed_stokes":
        return _windowed_stokes(
            kwargs["sequence"],
            alphabet=kwargs.get("alphabet", "dna"),
            window=kwargs.get("window", 20),
            step=kwargs.get("step", 10),
        )
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"mode desconocido: {mode}")


POLARIZATION_MAPPING_SCHEMA = {
    "name": "polarization_mapping",
    "description": (
        "Mapea secuencias de ADN/proteina a estados de polarizacion optica (psi, chi fijos "
        "por simbolo) y calcula el vector de Stokes (S0..S3) y grado de polarizacion (DOP), "
        "agregado o por ventana deslizante. Proxy matematico, no medicion optica real. "
        "mode='sequence_to_stokes' (sequence, alphabet); mode='windowed_stokes' (sequence, "
        "alphabet, window, step); mode='validate' confirma DOP=1 para secuencia homogenea."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["sequence_to_stokes", "windowed_stokes", "validate"],
                "default": "validate",
            },
            "sequence": {"type": "string", "description": "Secuencia de simbolos. Requerido salvo validate."},
            "alphabet": {
                "type": "string",
                "enum": ["dna", "protein"],
                "default": "dna",
            },
            "window": {"type": "integer", "default": 20, "description": "Tamano de ventana. windowed_stokes."},
            "step": {"type": "integer", "default": 10, "description": "Paso entre ventanas. windowed_stokes."},
        },
        "required": ["mode"],
    },
}
