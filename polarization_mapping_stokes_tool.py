"""
polarization_mapping_tool.py

Mapeo de secuencias de ADN a vectores de Stokes (S0, S1, S2, S3), como
generalizacion de spin_complex (S1 = real, S2 = imaginario) mas un
componente posicional S3 ligado al marco de lectura (codon, posicion mod 3).

Pensado como primer paso del pipeline hacia optical_sequence_id:

    Secuencia de ADN
        -> polarization_mapping (vectores de Stokes)
        -> Matriz de Jones/Mueller (pantalla de fase 2D)
        -> Difraccion de haz polarizado (simulacion optica)
        -> optical_sequence_id (identificador unico)

Modos soportados (parametro `mode`):
    - "map_sequence": mapea una secuencia de ADN a su matriz de Stokes (N x 4)
        params: seq (str, requerido)
    - "validate_purine_pyrimidine": control sintetico A -> S1 separa A/G (+1) de C/T (-1)
    - "validate_hydrogen_bond": control sintetico B -> S2 separa A/T (-1) de G/C (+1)
    - "validate_periodicity": control sintetico C -> DFT de S3 sobre "ATG"*repeats
        tiene un pico en el bin N/3
        params: repeats (int, default 30)
    - "validate_all": corre los tres controles sinteticos y devuelve un resumen

Todos los modos devuelven un dict serializable a JSON (nunca levantan excepcion:
los errores se devuelven como {"error": "..."}).
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Mapeo base -> (S1, S2), identico a spin_complex (real, imaginario)
# ---------------------------------------------------------------------------
_S1_S2 = {
    "A": (+1.0, -1.0),  # purina, 2 puentes H
    "G": (+1.0, +1.0),  # purina, 3 puentes H
    "C": (-1.0, +1.0),  # pirimidina, 3 puentes H
    "T": (-1.0, -1.0),  # pirimidina, 2 puentes H
    "U": (-1.0, -1.0),  # uracilo (ARN), tratado igual que T
}

_VALID_BASES = set(_S1_S2.keys())


def _clean_sequence(seq: str) -> str:
    if not isinstance(seq, str) or len(seq) == 0:
        raise ValueError("`seq` debe ser un string no vacio con bases A/C/G/T(/U)")
    seq = seq.strip().upper()
    invalid = set(seq) - _VALID_BASES
    if invalid:
        raise ValueError(
            f"Bases invalidas encontradas: {sorted(invalid)}. "
            f"Bases validas: {sorted(_VALID_BASES)}"
        )
    return seq


def _s3_for_position(i: int) -> float:
    """
    S3 codifica el marco de lectura via posicion mod 3 (0-indexed):
        pos mod 3 == 0 -> +1.0  (primera base del codon)
        pos mod 3 == 1 ->  0.0  (segunda base del codon)
        pos mod 3 == 2 -> -1.0  (tercera base del codon)
    """
    r = i % 3
    if r == 0:
        return +1.0
    if r == 1:
        return 0.0
    return -1.0


def _stokes_matrix(seq: str) -> np.ndarray:
    """Devuelve una matriz (N, 4) con columnas [S0, S1, S2, S3]."""
    n = len(seq)
    mat = np.zeros((n, 4), dtype=float)
    for i, base in enumerate(seq):
        s1, s2 = _S1_S2[base]
        mat[i, 0] = 1.0
        mat[i, 1] = s1
        mat[i, 2] = s2
        mat[i, 3] = _s3_for_position(i)
    return mat


# ---------------------------------------------------------------------------
# Modo: map_sequence
# ---------------------------------------------------------------------------
def _mode_map_sequence(seq: str) -> dict:
    seq = _clean_sequence(seq)
    mat = _stokes_matrix(seq)
    # grado de polarizacion por base: DOP = sqrt(S1^2+S2^2+S3^2) / S0
    dop = np.sqrt(mat[:, 1] ** 2 + mat[:, 2] ** 2 + mat[:, 3] ** 2) / mat[:, 0]
    return {
        "mode": "map_sequence",
        "length": len(seq),
        "sequence": seq,
        "stokes": mat.tolist(),
        "columns": ["S0", "S1", "S2", "S3"],
        "degree_of_polarization": dop.tolist(),
        "degree_of_polarization_mean": float(np.mean(dop)),
    }


# ---------------------------------------------------------------------------
# Control sintetico A: separacion purina/pirimidina (S1)
# ---------------------------------------------------------------------------
def _mode_validate_purine_pyrimidine() -> dict:
    seq = "AGCT" * 5
    mat = _stokes_matrix(seq)
    s1 = mat[:, 1]
    purine_mask = np.array([b in ("A", "G") for b in seq])
    ok_purines = bool(np.all(s1[purine_mask] == 1.0))
    ok_pyrimidines = bool(np.all(s1[~purine_mask] == -1.0))
    passed = ok_purines and ok_pyrimidines
    return {
        "mode": "validate_purine_pyrimidine",
        "sequence": seq,
        "s1": s1.tolist(),
        "purinas_correctas_S1_+1": ok_purines,
        "pirimidinas_correctas_S1_-1": ok_pyrimidines,
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# Control sintetico B: separacion puente de hidrogeno (S2)
# ---------------------------------------------------------------------------
def _mode_validate_hydrogen_bond() -> dict:
    seq = "ATGC" * 5
    mat = _stokes_matrix(seq)
    s2 = mat[:, 2]
    weak_mask = np.array([b in ("A", "T") for b in seq])    # 2 puentes H
    strong_mask = np.array([b in ("G", "C") for b in seq])  # 3 puentes H
    ok_weak = bool(np.all(s2[weak_mask] == -1.0))
    ok_strong = bool(np.all(s2[strong_mask] == +1.0))
    passed = ok_weak and ok_strong
    return {
        "mode": "validate_hydrogen_bond",
        "sequence": seq,
        "s2": s2.tolist(),
        "AT_correctos_S2_-1": ok_weak,
        "GC_correctos_S2_+1": ok_strong,
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# Control sintetico C: periodicidad de marco de lectura (DFT de S3 -> pico en N/3)
# ---------------------------------------------------------------------------
def _mode_validate_periodicity(repeats: int = 30) -> dict:
    if repeats < 3:
        raise ValueError("`repeats` debe ser >= 3")
    seq = "ATG" * repeats
    mat = _stokes_matrix(seq)
    s3 = mat[:, 3]
    n = len(s3)

    spectrum = np.fft.fft(s3 - np.mean(s3))
    mags = np.abs(spectrum)
    expected_idx = round(n / 3)
    half = n // 2
    peak_idx = int(np.argmax(mags[1:half])) + 1  # ignora componente DC (k=0)

    passed = abs(peak_idx - expected_idx) <= 1  # tolerancia +-1 bin

    return {
        "mode": "validate_periodicity",
        "sequence_length": n,
        "repeats": repeats,
        "expected_peak_index_N_over_3": expected_idx,
        "actual_peak_index": peak_idx,
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# Modo: validate_all
# ---------------------------------------------------------------------------
def _mode_validate_all() -> dict:
    a = _mode_validate_purine_pyrimidine()
    b = _mode_validate_hydrogen_bond()
    c = _mode_validate_periodicity()
    all_passed = a["passed"] and b["passed"] and c["passed"]
    return {
        "mode": "validate_all",
        "case_A_purine_pyrimidine": a,
        "case_B_hydrogen_bond": b,
        "case_C_periodicity": c,
        "all_passed": all_passed,
    }


# ---------------------------------------------------------------------------
# Entry point (misma convencion mode + params que el resto de tools)
# ---------------------------------------------------------------------------
def compute_polarization_mapping(mode: str = "map_sequence", **params) -> dict:
    try:
        if mode == "map_sequence":
            seq = params.get("seq") or params.get("sequence")
            if seq is None:
                raise ValueError("mode='map_sequence' requiere el parametro `seq`")
            return _mode_map_sequence(seq)

        if mode == "validate_purine_pyrimidine":
            return _mode_validate_purine_pyrimidine()

        if mode == "validate_hydrogen_bond":
            return _mode_validate_hydrogen_bond()

        if mode == "validate_periodicity":
            repeats = int(params.get("repeats", 30))
            return _mode_validate_periodicity(repeats)

        if mode == "validate_all":
            return _mode_validate_all()

        return {
            "error": (
                f"mode '{mode}' no reconocido. Modos validos: "
                "map_sequence, validate_purine_pyrimidine, "
                "validate_hydrogen_bond, validate_periodicity, validate_all"
            )
        }
    except Exception as exc:  # nunca explotar: error serializable
        return {"error": str(exc)}


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

POLARIZATION_MAPPING_STOKES_TOOL_SCHEMA = {
    "name": "polarization_mapping_stokes_tool",
    "description": 'Mapeo de ADN a vectores de Stokes (S0-S3) con componente posicional S3 ligado al marco de lectura. Primer paso del pipeline ADN -> Stokes -> mascara de fase 2D -> difraccion -> id optico. Modos: map_sequence (params: seq), validate_purine_pyrimidine, validate_hydrogen_bond, validate_periodicity, validate_all. Distinto de polarization_mapping_tool (angulos psi/chi).',
    "inputSchema": {
        "type": "object",
        "properties": {"mode": {"type": "string"}, "params": {"type": "object"}},
    },
}

register_tool("polarization_mapping_stokes_tool", POLARIZATION_MAPPING_STOKES_TOOL_SCHEMA, lambda args: compute_polarization_mapping(args.get("mode", "map_sequence"), **(args.get("params") or {})))
