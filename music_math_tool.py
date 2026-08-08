"""
music_math_tool.py

Matematica de la musica: afinacion (pitagorica vs. temperamento igual vs.
justa), serie armonica, escalas de division ternaria de la octava (puente
directo con TritOS -- grafeno con 3 estados nativos: -1, 0, +1), y analisis
espectral real via FFT en Octave para detectar armonicos y estimar
disonancia sensorial (aspereza de Plomp-Levelt, version simplificada).

Mismo patron que fractal_dimension_tool / cross_validation_tool: presets
con valor analitico conocido para validar (coma pitagorica = 23.46 cents
exactos, serie armonica con desviaciones en cents contra 12-TET conocidas)
antes de aplicar el mismo codigo a una senal real via 'custom'.
"""
import subprocess
import tempfile
import os
import math

MUSIC_MATH_SCHEMA = {
    "name": "compute_music_math",
    "description": (
        "Calculos de matematica musical: pythagorean_comma (coma pitagorica "
        "exacta), temperament_comparison (justo vs 12-TET en cents), "
        "harmonic_series (armonicos de una fundamental y su desviacion vs "
        "12-TET), ternary_scale (division de la octava en 3^n pasos, "
        "conexion con sistemas ternarios), spectral_analysis (FFT real via "
        "Octave sobre una senal, deteccion de armonicos y aspereza "
        "Plomp-Levelt simplificada)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "preset": {
                "type": "string",
                "enum": ["pythagorean_comma", "temperament_comparison",
                         "harmonic_series", "ternary_scale", "spectral_analysis"],
                "default": "pythagorean_comma",
            },
            "f0": {"type": "number", "default": 220.0, "description": "Frecuencia fundamental en Hz"},
            "n_harmonics": {"type": "integer", "default": 8},
            "n_power": {"type": "integer", "default": 2, "description": "Para ternary_scale: divide en 3^n_power pasos"},
            "signal": {"type": "array", "description": "Solo si preset='spectral_analysis': muestras de audio"},
            "fs": {"type": "number", "default": 44100, "description": "Frecuencia de muestreo para spectral_analysis"},
        },
    },
}

JUST_RATIOS = {
    "unisono": 1/1, "segunda_menor": 16/15, "segunda_mayor": 9/8,
    "tercera_menor": 6/5, "tercera_mayor": 5/4, "cuarta_justa": 4/3,
    "tritono": 45/32, "quinta_justa": 3/2, "sexta_menor": 8/5,
    "sexta_mayor": 5/3, "septima_menor": 9/5, "septima_mayor": 15/8, "octava": 2/1,
}


def _pythagorean_comma():
    twelve_fifths = (3/2) ** 12
    seven_octaves = 2 ** 7
    ratio = twelve_fifths / seven_octaves
    cents = 1200 * math.log2(ratio)
    return {
        "ratio_12_quintas_vs_7_octavas": round(ratio, 8),
        "cents": round(cents, 4),
        "valor_referencia_conocido_cents": 23.46,
        "explicacion": (
            "Apilar 12 quintas justas (3:2) no cae exacto en 7 octavas (2:1) -- "
            "la diferencia es la coma pitagorica. Es la razon estructural por la "
            "que ningun temperamento puede tener quintas Y octavas simultaneamente "
            "puras en un circulo cerrado de 12 notas: hay que repartir el error "
            "(temperamento igual) o dejarlo concentrado en un intervalo 'lobo' "
            "(temperamentos historicos como mesotonico)."
        ),
    }


def _temperament_comparison():
    rows = []
    for i, (name, ratio) in enumerate(JUST_RATIOS.items()):
        cents_just = 1200 * math.log2(ratio)
        cents_equal = i * 100
        rows.append({
            "intervalo": name,
            "ratio_justo": round(ratio, 6),
            "cents_justo": round(cents_just, 2),
            "cents_12_TET": cents_equal,
            "diferencia_cents": round(cents_just - cents_equal, 2),
        })
    return {
        "tabla": rows,
        "nota": (
            "Diferencias positivas = el intervalo justo es mas agudo que 12-TET; "
            "negativas = mas grave. La tercera mayor justa (5:4) es ~14 cents mas "
            "grave que en piano -- por eso un coro a capella 'suena mas limpio' "
            "que un piano en el mismo acorde."
        ),
    }


def _harmonic_series(f0, n_harmonics):
    rows = []
    for k in range(1, n_harmonics + 1):
        f = f0 * k
        cents_from_f0 = 1200 * math.log2(f / f0) if k > 1 else 0.0
        nearest_semitone = round(cents_from_f0 / 100)
        equal_cents = nearest_semitone * 100
        deviation = cents_from_f0 - equal_cents
        rows.append({
            "armonico": k,
            "freq_hz": round(f, 3),
            "cents_desde_f0": round(cents_from_f0, 2),
            "semitono_12TET_mas_cercano": nearest_semitone,
            "desviacion_cents": round(deviation, 2),
        })
    return {
        "f0_hz": f0,
        "armonicos": rows,
        "nota": (
            "El armonico 7 es el que mas se desvia del temperamento igual "
            "(~31 cents grave) -- es la base de la 'septima armonica' usada en "
            "musica microtonal y en ciertos estilos de blues/barbershop que "
            "explotan esa nota 'entre las teclas del piano'."
        ),
    }


def _ternary_scale(f0, n_power):
    steps = 3 ** n_power
    cents_per_step = 1200.0 / steps
    rows = []
    for k in range(steps + 1):
        cents = k * cents_per_step
        f = f0 * (2 ** (cents / 1200))
        nearest_semitone = round(cents / 100)
        diff_vs_12tet = round(cents - nearest_semitone * 100, 2)
        rows.append({
            "paso": k, "cents": round(cents, 2), "freq_hz": round(f, 3),
            "diff_vs_12TET_cents": diff_vs_12tet,
        })
    return {
        "n_power": n_power,
        "n_pasos_por_octava": steps,
        "cents_por_paso": round(cents_per_step, 3),
        "escala": rows,
        "conexion_tritos": (
            f"3^{n_power}={steps} pasos por octava mapea directo a un sistema "
            "de computo ternario balanceado (-1,0,+1 por digito, base 3) -- "
            "cada nota de la escala corresponde a un valor ternario. Nota: solo "
            "los pasos multiplos de steps/3 (si n_power>=1) caen exactos sobre "
            "el temperamento igual de 12 notas; el resto queda desafinado "
            "respecto a 12-TET por construccion, no por error."
        ),
    }


def _spectral_analysis(signal, fs, timeout=30):
    if not signal or len(signal) < 64:
        return {"error": "spectral_analysis requiere 'signal' con al menos 64 muestras"}

    signal_str = ",".join(f"{x:.8f}" for x in signal)
    octave_code = f"""
x = [{signal_str}];
fs = {fs};
N = length(x);
X = abs(fft(x));
X = X(1:floor(N/2));
freqs = (0:floor(N/2)-1) * fs / N;
[pks, locs] = sort(X, 'descend');
n_peaks = min(8, length(pks));
printf("%.6f ", freqs(locs(1:n_peaks)));
printf("|");
printf("%.6f ", pks(1:n_peaks));
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".m", delete=False) as fh:
        fh.write(octave_code)
        script_path = fh.name
    try:
        r = subprocess.run(["octave", "--no-gui", "--no-init-file", script_path],
                            capture_output=True, text=True, timeout=timeout)
    finally:
        os.unlink(script_path)
    if r.returncode != 0:
        return {"error": "octave fallo en analisis espectral", "stderr": r.stderr.strip()}

    freqs_part, mags_part = r.stdout.split("|")
    freqs = [float(x) for x in freqs_part.split()]
    mags = [float(x) for x in mags_part.split()]

    fundamental = freqs[0] if freqs else 0.0
    partials = []
    for f, m in zip(freqs, mags):
        ratio_to_f0 = f / fundamental if fundamental > 0 else 0.0
        partials.append({"freq_hz": round(f, 2), "magnitud_relativa": round(m, 2),
                          "ratio_a_fundamental": round(ratio_to_f0, 3)})

    # aspereza Plomp-Levelt simplificada: suma sobre pares de partials cercanos en frecuencia
    roughness = 0.0
    for i in range(len(freqs)):
        for j in range(i + 1, len(freqs)):
            df = abs(freqs[i] - freqs[j])
            fmin = min(freqs[i], freqs[j])
            if fmin <= 0:
                continue
            # banda critica aproximada (modelo simplificado, no el modelo completo de Plomp-Levelt)
            cb = 1.72 * (fmin ** 0.65)
            x = df / cb if cb > 0 else 0
            r_ij = math.exp(-3.5 * x) - math.exp(-5.75 * x) if x > 0 else 0
            roughness += mags[i] * mags[j] * max(r_ij, 0)

    return {
        "fundamental_estimada_hz": round(fundamental, 2),
        "partials": partials,
        "aspereza_relativa_plomp_levelt_simplificada": round(roughness, 4),
        "nota_metodologica": (
            "Aspereza calculada con el modelo simplificado de Plomp & Levelt "
            "(1965) sobre bandas criticas aproximadas -- sirve para comparar "
            "aspereza RELATIVA entre distintas senales/acordes generadas con el "
            "mismo metodo, no como valor absoluto calibrado psicoacusticamente."
        ),
    }


def compute_music_math(preset="pythagorean_comma", f0=220.0, n_harmonics=8,
                        n_power=2, signal=None, fs=44100):
    if preset == "pythagorean_comma":
        return _pythagorean_comma()
    elif preset == "temperament_comparison":
        return _temperament_comparison()
    elif preset == "harmonic_series":
        return _harmonic_series(f0, n_harmonics)
    elif preset == "ternary_scale":
        return _ternary_scale(f0, n_power)
    elif preset == "spectral_analysis":
        return _spectral_analysis(signal, fs)
    else:
        return {"error": f"preset desconocido: {preset}"}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_music_math("pythagorean_comma"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_music_math("ternary_scale", n_power=2), indent=2, ensure_ascii=False))
