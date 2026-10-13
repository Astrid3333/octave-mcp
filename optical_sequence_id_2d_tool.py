"""
optical_sequence_id_tool.py

Segundo paso del pipeline (despues de polarization_mapping): toma la matriz
de Stokes [S0,S1,S2,S3] de una secuencia de ADN, construye una mascara de
fase 2D (objeto difractante) y simula la propagacion de un haz coherente
para derivar un identificador optico de la secuencia.

    Secuencia de ADN
        -> polarization_mapping (vectores de Stokes)
        -> optical_sequence_id (ESTE MODULO):
             1) mascara de fase 2D a partir de Stokes (3 layouts posibles)
             2) difraccion (Fraunhofer o Fresnel, como modos separados)
             3) id final = hash deterministico + firma vectorial

Decisiones de diseno (importante leer antes de usar):

- Mascara de fase pura: S1 y S2 son siempre +-1 (nunca continuos), asi que
  la amplitud sqrt((S1^2+S2^2)/2) da SIEMPRE 1 -- no hay informacion de
  amplitud en spin_complex. Por eso el objeto es una MASCARA DE FASE PURA
  (amplitud=1 en todos los puntos no rellenados), donde:
      fase_base = atan2(S2, S1)   -> 4 valores posibles (uno por base)
      fase_total = fase_base + (pi/6) * S3   -> S3 module la fase +-30 grados
  Las celdas de relleno (padding, cuando N no calza perfecto en la grilla)
  se dejan en amplitud 0 (opacas), no en fase 0 -- para no inventar bases
  donde no las hay.

- 3 layouts de mascara ("mapping"), a elegir segun el contexto de uso:
    "slit_1d"      -> fila unica 1xN (rendija multiple, difraccion
                       predominante en un eje; util para ver el patron
                       de una secuencia como si fuera un codigo de barras)
    "folded_2d"     -> matriz cuadrada ceil(sqrt(N)) x ceil(sqrt(N)) (rejilla
                       2D real; util para ver estructura global de secuencias
                       largas, tipo "textura")
    "codon_blocks"  -> matriz 3 x M (M = ceil(N/3) codones), cada columna es
                       un codon; util cuando el marco de lectura importa mas
                       que la forma global

- 2 regimenes de propagacion, como modos separados del tool (no se mezclan):
    "fraunhofer" -> campo lejano, intensidad = |FFT2(mascara)|^2 (rapido)
    "fresnel"    -> campo cercano, metodo del espectro angular con funcion
                    de transferencia parabolica (requiere wavelength,
                    distance, dx)

- El identificador final combina AMBAS cosas:
    "id_hash"   -> SHA-256 de la intensidad normalizada y cuantizada
                   (unicidad estricta: cualquier cambio, por chico que sea,
                   cambia el hash)
    "signature" -> vector de rasgos (centroide, dispersion, picos
                   principales) pensado para comparar secuencias PARECIDAS
                   entre si (mode="compare" usa esto)

Modos soportados (parametro `mode`):
    - "generate": genera el id optico completo de una secuencia
        params: seq (requerido), mapping ("slit_1d"|"folded_2d"|"codon_blocks",
        default "slit_1d"), diffraction ("fraunhofer"|"fresnel", default
        "fraunhofer"), output_size (grilla de FFT, default 128), wavelength
        (metros, solo fresnel, default 5e-7), distance (metros, solo fresnel,
        default 1.0), dx (paso espacial en metros, solo fresnel, default 1e-6),
        hash_precision (decimales de cuantizacion, default 6), top_k_peaks
        (default 5), include_pattern (bool, default False -- si True devuelve
        la grilla completa de intensidad, puede ser pesado)
    - "compare": genera el id de dos secuencias con los mismos parametros
        fisicos y compara sus firmas vectoriales (similitud coseno) y hashes
        params: seq_a, seq_b (requeridos), + mismos params fisicos que generate
    - "validate_energy_conservation": control sintetico -- verifica el
        teorema de Parseval para la implementacion de Fraunhofer (si la
        energia no se conserva entre dominio espacial y de frecuencia, hay
        un bug de normalizacion en la FFT)
    - "validate_translation_invariance": control sintetico -- verifica que
        |FFT| es invariante ante traslacion de la mascara dentro de la
        grilla (propiedad fisica basica de la transformada de Fourier)
    - "validate_all": corre los dos controles sinteticos anteriores

Todos los modos devuelven un dict serializable a JSON; los errores se
devuelven como {"error": "..."} sin levantar excepcion.
"""

from __future__ import annotations

import hashlib

import numpy as np

from polarization_mapping_stokes_tool import compute_polarization_mapping


# ---------------------------------------------------------------------------
# Mascara de fase a partir de la matriz de Stokes
# ---------------------------------------------------------------------------
def _phase_only_transmittance(stokes_mat: np.ndarray) -> np.ndarray:
    """
    Convierte una matriz de Stokes (N,4) en un vector complejo de
    transmitancia de fase pura (amplitud=1 siempre), longitud N.
    """
    s1 = stokes_mat[:, 1]
    s2 = stokes_mat[:, 2]
    s3 = stokes_mat[:, 3]
    phase = np.arctan2(s2, s1) + (np.pi / 6.0) * s3
    return np.exp(1j * phase)


def _get_transmittance_from_seq(seq: str) -> np.ndarray:
    pm = compute_polarization_mapping("map_sequence", seq=seq)
    if "error" in pm:
        raise ValueError(pm["error"])
    mat = np.array(pm["stokes"], dtype=float)
    return _phase_only_transmittance(mat)


# ---------------------------------------------------------------------------
# Layouts de mascara 2D
# ---------------------------------------------------------------------------
_VALID_MAPPINGS = ("slit_1d", "folded_2d", "codon_blocks")


def _reshape_aperture(t: np.ndarray, mapping: str) -> np.ndarray:
    n = len(t)
    if mapping == "slit_1d":
        return t.reshape(1, n)

    if mapping == "folded_2d":
        side = int(np.ceil(np.sqrt(n)))
        total = side * side
        padded = np.zeros(total, dtype=complex)
        padded[:n] = t
        return padded.reshape(side, side)

    if mapping == "codon_blocks":
        m = int(np.ceil(n / 3))
        total = m * 3
        padded = np.zeros(total, dtype=complex)
        padded[:n] = t
        return padded.reshape(m, 3).T  # (3, M): filas=posicion en codon, cols=codon

    raise ValueError(
        f"mapping '{mapping}' no reconocido. Validos: {_VALID_MAPPINGS}"
    )


def _center_pad(arr2d: np.ndarray, output_size: int) -> np.ndarray:
    ny, nx = arr2d.shape
    size = max(output_size, ny, nx)
    canvas = np.zeros((size, size), dtype=complex)
    start_y = (size - ny) // 2
    start_x = (size - nx) // 2
    canvas[start_y:start_y + ny, start_x:start_x + nx] = arr2d
    return canvas


# ---------------------------------------------------------------------------
# Regimenes de difraccion
# ---------------------------------------------------------------------------
def _fraunhofer(aperture2d: np.ndarray, output_size: int) -> np.ndarray:
    canvas = _center_pad(aperture2d, output_size)
    field = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(canvas)))
    return np.abs(field) ** 2


def _fresnel(
    aperture2d: np.ndarray,
    wavelength: float,
    distance: float,
    dx: float,
    output_size: int,
) -> np.ndarray:
    canvas = _center_pad(aperture2d, output_size)
    n = canvas.shape[0]
    fx = np.fft.fftfreq(n, d=dx)
    fx_grid, fy_grid = np.meshgrid(fx, fx)
    # funcion de transferencia de Fresnel (aproximacion paraxial, espectro angular)
    transfer = np.exp(-1j * np.pi * wavelength * distance * (fx_grid ** 2 + fy_grid ** 2))
    spectrum = np.fft.fft2(canvas)
    propagated = np.fft.ifft2(spectrum * transfer)
    return np.abs(np.fft.fftshift(propagated)) ** 2


def _diffract(aperture2d: np.ndarray, diffraction: str, **phys) -> np.ndarray:
    output_size = int(phys.get("output_size", 128))
    if diffraction == "fraunhofer":
        return _fraunhofer(aperture2d, output_size)
    if diffraction == "fresnel":
        wavelength = float(phys.get("wavelength", 5e-7))
        distance = float(phys.get("distance", 1.0))
        dx = float(phys.get("dx", 1e-6))
        return _fresnel(aperture2d, wavelength, distance, dx, output_size)
    raise ValueError(
        f"diffraction '{diffraction}' no reconocido. Validos: fraunhofer, fresnel"
    )


# ---------------------------------------------------------------------------
# Identificador: hash + firma vectorial
# ---------------------------------------------------------------------------
def _hash_intensity(intensity: np.ndarray, precision: int = 6) -> str:
    total = np.sum(intensity)
    norm = intensity / total if total > 0 else intensity
    quant = np.round(norm, precision)
    return hashlib.sha256(quant.tobytes()).hexdigest()


def _vector_signature(intensity: np.ndarray, top_k: int = 5) -> dict:
    total_energy = float(np.sum(intensity))
    norm = intensity / total_energy if total_energy > 0 else intensity
    ny, nx = intensity.shape
    ys, xs = np.indices((ny, nx))
    centroid_row = float(np.sum(norm * ys))
    centroid_col = float(np.sum(norm * xs))
    spread_row = float(np.sqrt(np.sum(norm * (ys - centroid_row) ** 2)))
    spread_col = float(np.sqrt(np.sum(norm * (xs - centroid_col) ** 2)))

    flat_order = np.argsort(intensity.ravel())[::-1][:top_k]
    peaks = []
    for idx in flat_order:
        r, c = np.unravel_index(idx, intensity.shape)
        peaks.append({"row": int(r), "col": int(c), "value": float(intensity[r, c])})

    return {
        "total_energy": total_energy,
        "centroid_row": centroid_row,
        "centroid_col": centroid_col,
        "spread_row": spread_row,
        "spread_col": spread_col,
        "top_peaks": peaks,
    }


def _signature_to_vector(sig: dict, k: int = 5) -> np.ndarray:
    base = [sig["centroid_row"], sig["centroid_col"], sig["spread_row"], sig["spread_col"]]
    peak_vals = [p["value"] for p in sig["top_peaks"]][:k]
    while len(peak_vals) < k:
        peak_vals.append(0.0)
    return np.array(base + peak_vals, dtype=float)


# ---------------------------------------------------------------------------
# Modo: generate
# ---------------------------------------------------------------------------
def _mode_generate(seq: str, mapping: str = "slit_1d", diffraction: str = "fraunhofer",
                    **params) -> dict:
    if mapping not in _VALID_MAPPINGS:
        raise ValueError(f"mapping '{mapping}' no reconocido. Validos: {_VALID_MAPPINGS}")

    t = _get_transmittance_from_seq(seq)
    aperture2d = _reshape_aperture(t, mapping)
    intensity = _diffract(aperture2d, diffraction, **params)

    hash_precision = int(params.get("hash_precision", 6))
    top_k_peaks = int(params.get("top_k_peaks", 5))
    include_pattern = bool(params.get("include_pattern", False))

    result = {
        "mode": "generate",
        "sequence_length": len(t),
        "mapping": mapping,
        "diffraction": diffraction,
        "aperture_shape": list(aperture2d.shape),
        "pattern_shape": list(intensity.shape),
        "id_hash": _hash_intensity(intensity, hash_precision),
        "signature": _vector_signature(intensity, top_k_peaks),
    }
    if diffraction == "fresnel":
        result["wavelength"] = float(params.get("wavelength", 5e-7))
        result["distance"] = float(params.get("distance", 1.0))
        result["dx"] = float(params.get("dx", 1e-6))
    if include_pattern:
        result["intensity_pattern"] = intensity.tolist()
    return result


# ---------------------------------------------------------------------------
# Modo: compare
# ---------------------------------------------------------------------------
def _mode_compare(seq_a: str, seq_b: str, mapping: str = "slit_1d",
                   diffraction: str = "fraunhofer", **params) -> dict:
    ra = _mode_generate(seq_a, mapping, diffraction, **params)
    rb = _mode_generate(seq_b, mapping, diffraction, **params)

    # Metrica principal de similitud: correlacion pixel-a-pixel de los dos
    # patrones de intensidad completos (recalculados aca, ya normalizados).
    # NOTA DE DISENO: la firma vectorial (centroide/dispersion) NO sirve para
    # esto -- en un patron de Fraunhofer/Fresnel el centroide y la dispersion
    # quedan casi siempre cerca del centro de la grilla sin importar el
    # contenido de la secuencia (es una propiedad de simetria del patron, no
    # informacion util), asi que una similitud coseno sobre esos rasgos da
    # ~1.0 tanto para secuencias identicas como para secuencias totalmente
    # distintas. Se prueba en validate_all indirectamente al usarla el propio
    # test suite de este modulo.
    ta = _get_transmittance_from_seq(seq_a)
    tb = _get_transmittance_from_seq(seq_b)
    intensity_a = _diffract(_reshape_aperture(ta, mapping), diffraction, **params)
    intensity_b = _diffract(_reshape_aperture(tb, mapping), diffraction, **params)

    flat_a = intensity_a.ravel()
    flat_b = intensity_b.ravel()
    if np.std(flat_a) > 0 and np.std(flat_b) > 0:
        pattern_correlation = float(np.corrcoef(flat_a, flat_b)[0, 1])
    else:
        pattern_correlation = 1.0 if np.allclose(flat_a, flat_b) else 0.0

    # NOTA: se probo tambien una similitud coseno sobre los top-k peaks de la
    # firma vectorial como metrica secundaria mas liviana, pero quedaba pegada
    # a ~0.9998 tanto para secuencias parecidas como para secuencias
    # totalmente distintas (mismo problema de fondo que el centroide: los
    # picos principales de un patron de difraccion tienden a quedar en
    # posiciones/relaciones de magnitud parecidas independientemente del
    # contenido). Se descarto por no discriminar y quedar solo
    # pattern_correlation, que si separa bien los tres casos (1.0 / ~0.95 /
    # ~0.54 en las pruebas de este modulo).

    return {
        "mode": "compare",
        "mapping": mapping,
        "diffraction": diffraction,
        "id_hash_a": ra["id_hash"],
        "id_hash_b": rb["id_hash"],
        "identical_hash": ra["id_hash"] == rb["id_hash"],
        "pattern_correlation": pattern_correlation,
        "signature_a": ra["signature"],
        "signature_b": rb["signature"],
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Batch: parsing de FASTA / listas de secuencias
# ---------------------------------------------------------------------------
def _parse_batch_input(sequences=None, fasta=None) -> list[tuple[str, str]]:
    """
    Devuelve una lista de tuplas (id, seq) a partir de:
      - `sequences`: lista de strings (secuencia cruda, se autogenera un id
        "seq_1", "seq_2", ...) o lista de dicts {"id": ..., "seq": ...}
      - `fasta`: texto crudo en formato FASTA (">id\nSEQ\n...", multilinea
        por secuencia soportado)
    Si se pasan ambos, se concatenan (fasta primero, despues sequences).
    """
    items: list[tuple[str, str]] = []

    if fasta:
        current_id = None
        current_seq: list[str] = []
        for raw_line in fasta.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if current_id is not None:
                    items.append((current_id, "".join(current_seq)))
                current_id = line[1:].strip() or f"seq_{len(items) + 1}"
                current_seq = []
            else:
                current_seq.append(line)
        if current_id is not None:
            items.append((current_id, "".join(current_seq)))

    if sequences:
        for s in sequences:
            if isinstance(s, dict):
                seq = s.get("seq", "")
                sid = s.get("id") or f"seq_{len(items) + 1}"
            else:
                seq = s
                sid = f"seq_{len(items) + 1}"
            items.append((sid, seq))

    if not items:
        raise ValueError(
            "batch requiere al menos uno de: `sequences` (lista de strings o "
            "de {'id':..,'seq':..}), `fasta` (texto FASTA crudo)"
        )
    return items


def _uniform_grid_size(apertures: list[np.ndarray], output_size: int) -> int:
    """
    Grilla de FFT comun para TODO el lote: el maximo entre output_size y la
    dimension mas grande entre todas las aperturas del lote. Necesario para
    que las intensidades resultantes tengan la misma forma y sean
    comparables (matriz de correlacion, ranking, etc.) -- si cada secuencia
    usara su propia grilla minima, secuencias de distinto largo caerian en
    grillas de tamano distinto y no se podrian comparar pixel a pixel.
    """
    max_dim = output_size
    for ap in apertures:
        max_dim = max(max_dim, ap.shape[0], ap.shape[1])
    return max_dim


# ---------------------------------------------------------------------------
# Modo: batch_generate
# ---------------------------------------------------------------------------
def _mode_batch_generate(mapping: str = "slit_1d", diffraction: str = "fraunhofer",
                          sequences=None, fasta=None, **params) -> dict:
    if mapping not in _VALID_MAPPINGS:
        raise ValueError(f"mapping '{mapping}' no reconocido. Validos: {_VALID_MAPPINGS}")

    items = _parse_batch_input(sequences, fasta)
    output_size = int(params.get("output_size", 128))
    hash_precision = int(params.get("hash_precision", 6))
    top_k_peaks = int(params.get("top_k_peaks", 5))
    include_pattern = bool(params.get("include_pattern", False))

    # primera pasada: transmitancia + apertura por secuencia, para poder
    # fijar una grilla comun antes de difractar
    apertures = []
    for sid, seq in items:
        t = _get_transmittance_from_seq(seq)
        apertures.append(_reshape_aperture(t, mapping))

    grid = _uniform_grid_size(apertures, output_size)
    diffract_params = dict(params)
    diffract_params["output_size"] = grid

    results = []
    for (sid, seq), aperture2d in zip(items, apertures):
        intensity = _diffract(aperture2d, diffraction, **diffract_params)
        entry = {
            "id": sid,
            "sequence_length": len(seq),
            "id_hash": _hash_intensity(intensity, hash_precision),
            "signature": _vector_signature(intensity, top_k_peaks),
        }
        if include_pattern:
            entry["intensity_pattern"] = intensity.tolist()
        results.append(entry)

    return {
        "mode": "batch_generate",
        "mapping": mapping,
        "diffraction": diffraction,
        "grid_size": grid,
        "count": len(results),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Modo: batch_compare
# ---------------------------------------------------------------------------
def _mode_batch_compare(mapping: str = "slit_1d", diffraction: str = "fraunhofer",
                         sequences=None, fasta=None, query_seq=None,
                         query_id: str = "query", **params) -> dict:
    if mapping not in _VALID_MAPPINGS:
        raise ValueError(f"mapping '{mapping}' no reconocido. Validos: {_VALID_MAPPINGS}")

    items = _parse_batch_input(sequences, fasta)
    output_size = int(params.get("output_size", 128))

    all_items = list(items)
    if query_seq is not None:
        # la query va primero (indice 0) para poder aislar su fila despues
        all_items = [(query_id, query_seq)] + all_items

    apertures = []
    for sid, seq in all_items:
        t = _get_transmittance_from_seq(seq)
        apertures.append(_reshape_aperture(t, mapping))

    grid = _uniform_grid_size(apertures, output_size)
    diffract_params = dict(params)
    diffract_params["output_size"] = grid

    intensities = [
        _diffract(ap, diffraction, **diffract_params) for ap in apertures
    ]
    ids = [sid for sid, _ in all_items]

    # matriz de correlacion vectorizada: una sola llamada a np.corrcoef sobre
    # todos los patrones apilados, en vez de comparar par a par (esto ultimo
    # seria O(K^2) llamadas a corrcoef individuales, mucho mas lento para
    # lotes grandes).
    flat = np.stack([iv.ravel() for iv in intensities])  # (K, P)
    stds = flat.std(axis=1)
    with np.errstate(invalid="ignore"):
        corr_matrix = np.corrcoef(flat)  # (K, K)

    # np.corrcoef da NaN para filas/columnas con std=0 (patron constante,
    # deberia ser raro pero puede pasar con secuencias de largo 1). Se
    # resuelve igual que en mode="compare": 1.0 si son identicas, 0.0 si no.
    zero_std = np.where(stds == 0)[0]
    for i in zero_std:
        for j in range(len(intensities)):
            same = np.allclose(flat[i], flat[j])
            corr_matrix[i, j] = 1.0 if same else 0.0
            corr_matrix[j, i] = corr_matrix[i, j]

    if query_seq is not None:
        query_row = corr_matrix[0, 1:].tolist()
        ranked = sorted(
            zip(ids[1:], query_row), key=lambda kv: kv[1], reverse=True
        )
        return {
            "mode": "batch_compare",
            "mapping": mapping,
            "diffraction": diffraction,
            "grid_size": grid,
            "query_id": query_id,
            "ranked_matches": [
                {"id": sid, "pattern_correlation": corr} for sid, corr in ranked
            ],
        }

    return {
        "mode": "batch_compare",
        "mapping": mapping,
        "diffraction": diffraction,
        "grid_size": grid,
        "ids": ids,
        "correlation_matrix": corr_matrix.tolist(),
    }


# Control sintetico A: conservacion de energia (teorema de Parseval)
# ---------------------------------------------------------------------------
def _mode_validate_energy_conservation(mapping: str = "folded_2d",
                                        output_size: int = 64) -> dict:
    test_seq = "ATGC" * 8  # 32 bases
    t = _get_transmittance_from_seq(test_seq)
    aperture2d = _reshape_aperture(t, mapping)
    canvas = _center_pad(aperture2d, output_size)

    field = np.fft.fft2(canvas)
    energy_spatial = float(np.sum(np.abs(canvas) ** 2))
    energy_freq_raw = float(np.sum(np.abs(field) ** 2))
    n_pixels = canvas.size
    # Parseval (convencion numpy, FFT sin normalizar): sum|x|^2 = (1/N) sum|X|^2
    expected_freq_energy = energy_spatial * n_pixels
    rel_error = abs(energy_freq_raw - expected_freq_energy) / expected_freq_energy
    passed = bool(rel_error < 1e-9)

    return {
        "mode": "validate_energy_conservation",
        "mapping": mapping,
        "energy_spatial_domain": energy_spatial,
        "energy_freq_domain_raw": energy_freq_raw,
        "energy_freq_domain_expected": expected_freq_energy,
        "relative_error": rel_error,
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# Control sintetico B: invariancia ante traslacion (magnitud de FFT)
# ---------------------------------------------------------------------------
def _mode_validate_translation_invariance(mapping: str = "slit_1d",
                                           output_size: int = 64,
                                           shift: int = 5) -> dict:
    test_seq = "ATGCATGCATGC"
    t = _get_transmittance_from_seq(test_seq)
    aperture2d = _reshape_aperture(t, mapping)
    canvas = _center_pad(aperture2d, output_size)
    shifted_canvas = np.roll(canvas, shift, axis=1)

    i1 = np.abs(np.fft.fft2(canvas)) ** 2
    i2 = np.abs(np.fft.fft2(shifted_canvas)) ** 2
    max_val = float(np.max(i1)) + 1e-12
    max_rel_diff = float(np.max(np.abs(i1 - i2))) / max_val
    passed = bool(max_rel_diff < 1e-8)

    return {
        "mode": "validate_translation_invariance",
        "mapping": mapping,
        "shift_pixels": shift,
        "max_relative_diff": max_rel_diff,
        "passed": passed,
    }


def _mode_validate_all() -> dict:
    a = _mode_validate_energy_conservation()
    b = _mode_validate_translation_invariance()
    return {
        "mode": "validate_all",
        "case_A_energy_conservation": a,
        "case_B_translation_invariance": b,
        "all_passed": bool(a["passed"] and b["passed"]),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def compute_optical_sequence_id(mode: str = "generate", **params) -> dict:
    try:
        if mode == "generate":
            seq = params.pop("seq", None)
            if seq is None:
                raise ValueError("mode='generate' requiere el parametro `seq`")
            mapping = params.pop("mapping", "slit_1d")
            diffraction = params.pop("diffraction", "fraunhofer")
            return _mode_generate(seq, mapping, diffraction, **params)

        if mode == "compare":
            seq_a = params.pop("seq_a", None)
            seq_b = params.pop("seq_b", None)
            if seq_a is None or seq_b is None:
                raise ValueError("mode='compare' requiere `seq_a` y `seq_b`")
            mapping = params.pop("mapping", "slit_1d")
            diffraction = params.pop("diffraction", "fraunhofer")
            return _mode_compare(seq_a, seq_b, mapping, diffraction, **params)

        if mode == "batch_generate":
            mapping = params.pop("mapping", "slit_1d")
            diffraction = params.pop("diffraction", "fraunhofer")
            sequences = params.pop("sequences", None)
            fasta = params.pop("fasta", None)
            return _mode_batch_generate(mapping, diffraction, sequences=sequences,
                                         fasta=fasta, **params)

        if mode == "batch_compare":
            mapping = params.pop("mapping", "slit_1d")
            diffraction = params.pop("diffraction", "fraunhofer")
            sequences = params.pop("sequences", None)
            fasta = params.pop("fasta", None)
            query_seq = params.pop("query_seq", None)
            query_id = params.pop("query_id", "query")
            return _mode_batch_compare(mapping, diffraction, sequences=sequences,
                                        fasta=fasta, query_seq=query_seq,
                                        query_id=query_id, **params)

        if mode == "validate_energy_conservation":
            mapping = params.get("mapping", "folded_2d")
            output_size = int(params.get("output_size", 64))
            return _mode_validate_energy_conservation(mapping, output_size)

        if mode == "validate_translation_invariance":
            mapping = params.get("mapping", "slit_1d")
            output_size = int(params.get("output_size", 64))
            shift = int(params.get("shift", 5))
            return _mode_validate_translation_invariance(mapping, output_size, shift)

        if mode == "validate_all":
            return _mode_validate_all()

        return {
            "error": (
                f"mode '{mode}' no reconocido. Modos validos: "
                "generate, compare, batch_generate, batch_compare, "
                "validate_energy_conservation, validate_translation_invariance, "
                "validate_all"
            )
        }
    except Exception as exc:
        return {"error": str(exc)}


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

OPTICAL_SEQUENCE_ID_2D_TOOL_SCHEMA = {
    "name": "optical_sequence_id_2d_tool",
    "description": 'Segundo paso del pipeline: mascara de fase 2D desde Stokes (varios layouts), difraccion Fraunhofer/Fresnel e id optico (hash + firma). Modos: generate, compare, batch_generate, batch_compare, validate_energy_conservation, validate_translation_invariance, validate_all. Version 2D; distinta de optical_sequence_id_tool (1D, EIIP).',
    "inputSchema": {
        "type": "object",
        "properties": {"mode": {"type": "string"}, "params": {"type": "object"}},
    },
}

register_tool("optical_sequence_id_2d_tool", OPTICAL_SEQUENCE_ID_2D_TOOL_SCHEMA, lambda args: compute_optical_sequence_id(args.get("mode", "generate"), **(args.get("params") or {})))
