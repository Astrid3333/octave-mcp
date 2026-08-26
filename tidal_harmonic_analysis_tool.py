"""
tidal_harmonic_analysis_tool.py
================================

Análisis armónico de mareas mediante ajuste por mínimos cuadrados de las
constituyentes de marea estándar (Doodson/Darwin) a partir de una serie
temporal de nivel del mar (o velocidad de corriente).

Método
------
Para una serie h(t) muestreada en tiempos t (horas desde t0), se ajusta:

    h(t) = h0 + sum_k [ a_k * cos(w_k * t) + b_k * sin(w_k * t) ]

donde w_k es la frecuencia angular (grados/hora, estándar de mareas) de
cada constituyente k. El sistema es lineal en (h0, a_k, b_k) y se resuelve
por mínimos cuadrados (numpy.linalg.lstsq) — este es el método clásico de
análisis armónico (Godin 1972; Pawlowicz, Beardsley & Lentz 2002, T_TIDE).

De (a_k, b_k) se obtiene:
    Amplitud:  H_k = sqrt(a_k^2 + b_k^2)
    Fase (retraso, grados, convención coseno):  g_k = atan2(-b_k, a_k) en grados, mod 360

Constituyentes soportadas (frecuencias estándar, grados/hora solar medio):
    M2 (semidiurna lunar principal)      28.9841042
    S2 (semidiurna solar principal)      30.0000000
    N2 (semidiurna lunar elíptica)       28.4397295
    K2 (semidiurna luni-solar)           30.0821373
    K1 (diurna luni-solar)               15.0410686
    O1 (diurna lunar principal)          13.9430356
    P1 (diurna solar principal)          14.9589314
    Q1 (diurna lunar elíptica)           13.3986609

Referencia de frecuencias: Pugh, D.T. (1987) "Tides, Surges and Mean
Sea-Level", Table 4.1 — valores estándar de constituyentes armónicas.

Validación (mode="validate")
-----------------------------
Se genera una serie sintética h(t) con amplitudes y fases KNOWN para un
subconjunto de constituyentes (M2, S2, K1, O1), muestreada cada hora
durante 30 días (720 puntos, resolución suficiente para separar M2/S2 y
K1/O1 sin aliasing según el criterio de Rayleigh), con ruido gaussiano
pequeño agregado. Se corre el análisis armónico sobre esa serie y se
confirma que las amplitudes y fases recuperadas coinciden con las
conocidas dentro de tolerancia — chequeo contra verdad conocida, no un
umbral arbitrario.
"""

import numpy as np

TOOL_NAME = "tidal_harmonic_analysis_tool"

# Frecuencias angulares estándar de las constituyentes de marea (grados/hora)
# Fuente: Pugh (1987), Tides Surges and Mean Sea-Level, Table 4.1
CONSTITUENT_FREQUENCIES_DEG_PER_HOUR = {
    "M2": 28.9841042,
    "S2": 30.0000000,
    "N2": 28.4397295,
    "K2": 30.0821373,
    "K1": 15.0410686,
    "O1": 13.9430356,
    "P1": 14.9589314,
    "Q1": 13.3986609,
}

DEFAULT_CONSTITUENTS = ["M2", "S2", "N2", "K1", "O1"]

TOOL_MODES = ["harmonic_analysis", "reconstruct", "validate"]


# ----------------------------------------------------------------------
# Núcleo matemático
# ----------------------------------------------------------------------

def _design_matrix(times_hours, constituents):
    """Construye la matriz de diseño [1, cos(w_k t), sin(w_k t), ...]."""
    n = len(times_hours)
    t = np.asarray(times_hours, dtype=float)
    cols = [np.ones(n)]
    for name in constituents:
        w = np.deg2rad(CONSTITUENT_FREQUENCIES_DEG_PER_HOUR[name])
        cols.append(np.cos(w * t))
        cols.append(np.sin(w * t))
    return np.column_stack(cols)


def analyze_harmonics(times_hours, elevations, constituents=None):
    """
    Ajusta las constituyentes de marea a la serie (times_hours, elevations)
    por mínimos cuadrados.

    Devuelve dict con h0 (nivel medio), y por constituyente: amplitud (m),
    fase (grados, 0-360), y las componentes crudas a_k, b_k.
    """
    if constituents is None:
        constituents = DEFAULT_CONSTITUENTS

    unknown = [c for c in constituents if c not in CONSTITUENT_FREQUENCIES_DEG_PER_HOUR]
    if unknown:
        raise ValueError(
            f"Constituyente(s) desconocida(s): {unknown}. "
            f"Disponibles: {sorted(CONSTITUENT_FREQUENCIES_DEG_PER_HOUR)}"
        )

    t = np.asarray(times_hours, dtype=float)
    h = np.asarray(elevations, dtype=float)
    if len(t) != len(h):
        raise ValueError("times_hours y elevations deben tener la misma longitud")
    if len(t) < 2 * len(constituents) + 1:
        raise ValueError(
            f"Muy pocos puntos ({len(t)}) para ajustar {len(constituents)} "
            f"constituyentes (se necesitan al menos {2*len(constituents)+1})"
        )

    A = _design_matrix(t, constituents)
    coeffs, residuals, rank, sv = np.linalg.lstsq(A, h, rcond=None)

    h0 = float(coeffs[0])
    harmonics = {}
    for i, name in enumerate(constituents):
        a_k = coeffs[1 + 2 * i]
        b_k = coeffs[2 + 2 * i]
        amplitude = float(np.hypot(a_k, b_k))
        phase_deg = float(np.rad2deg(np.arctan2(-b_k, a_k)) % 360.0)
        harmonics[name] = {
            "amplitude_m": amplitude,
            "phase_deg": phase_deg,
            "frequency_deg_per_hour": CONSTITUENT_FREQUENCIES_DEG_PER_HOUR[name],
            "a_coef": float(a_k),
            "b_coef": float(b_k),
        }

    h_fit = A @ coeffs
    residual_series = h - h_fit
    rms_residual = float(np.sqrt(np.mean(residual_series ** 2)))
    variance_explained = float(
        1.0 - np.sum(residual_series ** 2) / np.sum((h - np.mean(h)) ** 2)
    )

    return {
        "h0_m": h0,
        "harmonics": harmonics,
        "n_points": int(len(t)),
        "constituents_used": constituents,
        "rms_residual_m": rms_residual,
        "variance_explained": variance_explained,
    }


def reconstruct_tide(times_hours, h0, harmonics):
    """
    Reconstruye/predice el nivel de marea en times_hours a partir de un
    conjunto de armónicos ya ajustados (h0 + dict de {nombre: {amplitude_m,
    phase_deg}}).
    """
    t = np.asarray(times_hours, dtype=float)
    h = np.full_like(t, float(h0))
    for name, params in harmonics.items():
        if name not in CONSTITUENT_FREQUENCIES_DEG_PER_HOUR:
            raise ValueError(f"Constituyente desconocida: {name}")
        w = np.deg2rad(CONSTITUENT_FREQUENCIES_DEG_PER_HOUR[name])
        H = float(params["amplitude_m"])
        g = np.deg2rad(float(params["phase_deg"]))
        h += H * np.cos(w * t + g)
    return h


# ----------------------------------------------------------------------
# Validación
# ----------------------------------------------------------------------

def _validate():
    checks = []

    rng = np.random.default_rng(42)

    # Verdad conocida: 4 constituyentes con amplitud/fase típicas de una
    # costa macrotidal (rango ~4-6 m, similar a Chiloé)
    known = {
        "M2": {"amplitude_m": 1.80, "phase_deg": 45.0},
        "S2": {"amplitude_m": 0.55, "phase_deg": 80.0},
        "K1": {"amplitude_m": 0.40, "phase_deg": 210.0},
        "O1": {"amplitude_m": 0.30, "phase_deg": 150.0},
    }
    h0_known = 2.10

    # 30 días, muestreo horario -> 720 puntos, resolución de Rayleigh
    # suficiente para separar M2/S2 (periodo de batido ~14.8 dias) y
    # K1/O1 (periodo de batido ~13.7 dias) dentro de la ventana
    n_points = 24 * 30
    t = np.arange(n_points, dtype=float)
    h_clean = reconstruct_tide(t, h0_known, known)
    noise = rng.normal(0.0, 0.01, size=n_points)  # 1 cm de ruido instrumental
    h_synthetic = h_clean + noise

    result = analyze_harmonics(t, h_synthetic, constituents=list(known.keys()))

    # Check 1: h0 recuperado dentro de 2 cm
    check1 = abs(result["h0_m"] - h0_known) < 0.02
    checks.append({
        "name": "h0_recuperado",
        "passed": bool(check1),
        "detail": f"h0 ajustado={result['h0_m']:.4f}, conocido={h0_known}",
    })

    # Check 2: amplitudes recuperadas dentro de 3% o 1 cm (lo que sea mayor)
    amp_ok = True
    amp_detail = []
    for name, ref in known.items():
        fitted = result["harmonics"][name]["amplitude_m"]
        tol = max(0.01, 0.03 * ref["amplitude_m"])
        ok = abs(fitted - ref["amplitude_m"]) < tol
        amp_ok = amp_ok and ok
        amp_detail.append(f"{name}: fit={fitted:.4f} ref={ref['amplitude_m']} ok={ok}")
    checks.append({
        "name": "amplitudes_recuperadas",
        "passed": bool(amp_ok),
        "detail": "; ".join(amp_detail),
    })

    # Check 3: fases recuperadas dentro de 2 grados
    phase_ok = True
    phase_detail = []
    for name, ref in known.items():
        fitted = result["harmonics"][name]["phase_deg"]
        diff = min(abs(fitted - ref["phase_deg"]), 360 - abs(fitted - ref["phase_deg"]))
        ok = diff < 2.0
        phase_ok = phase_ok and ok
        phase_detail.append(f"{name}: fit={fitted:.2f} ref={ref['phase_deg']} diff={diff:.2f} ok={ok}")
    checks.append({
        "name": "fases_recuperadas",
        "passed": bool(phase_ok),
        "detail": "; ".join(phase_detail),
    })

    # Check 4: varianza explicada muy alta (serie casi pura + poco ruido)
    check4 = result["variance_explained"] > 0.995
    checks.append({
        "name": "varianza_explicada",
        "passed": bool(check4),
        "detail": f"variance_explained={result['variance_explained']:.5f}",
    })

    # Check 5: reconstruct_tide + analyze_harmonics son consistentes (roundtrip)
    # sobre un tramo nuevo de tiempo (extrapolación 5 dias hacia adelante)
    t_future = np.arange(n_points, n_points + 24 * 5, dtype=float)
    h_future_from_known = reconstruct_tide(t_future, h0_known, known)
    h_future_from_fit = reconstruct_tide(
        t_future, result["h0_m"],
        {k: {"amplitude_m": v["amplitude_m"], "phase_deg": v["phase_deg"]}
         for k, v in result["harmonics"].items()}
    )
    max_diff = float(np.max(np.abs(h_future_from_known - h_future_from_fit)))
    check5 = max_diff < 0.03
    checks.append({
        "name": "extrapolacion_roundtrip",
        "passed": bool(check5),
        "detail": f"max diff en 5 dias de extrapolacion={max_diff:.4f} m",
    })

    # Check 6: constituyente desconocida da error controlado, no crash
    try:
        analyze_harmonics(t[:100], h_synthetic[:100], constituents=["M2", "XX9"])
        check6 = False
        check6_detail = "no lanzo ValueError con constituyente invalida"
    except ValueError:
        check6 = True
        check6_detail = "ValueError controlado como se esperaba"
    checks.append({
        "name": "constituyente_invalida_da_error",
        "passed": bool(check6),
        "detail": check6_detail,
    })

    # Check 7: muy pocos puntos para el numero de constituyentes da error
    try:
        analyze_harmonics([0, 1, 2], [1.0, 1.1, 1.2], constituents=DEFAULT_CONSTITUENTS)
        check7 = False
        check7_detail = "no lanzo ValueError con muy pocos puntos"
    except ValueError:
        check7 = True
        check7_detail = "ValueError controlado como se esperaba"
    checks.append({
        "name": "pocos_puntos_da_error",
        "passed": bool(check7),
        "detail": check7_detail,
    })

    all_passed = all(c["passed"] for c in checks)
    return {
        "validation_passed": bool(all_passed),
        "n_checks": len(checks),
        "n_passed": sum(1 for c in checks if c["passed"]),
        "checks": checks,
    }


# ----------------------------------------------------------------------
# Dispatch / registro (patrón del repo: run(mode, params) + register_tool)
# ----------------------------------------------------------------------

def run(arguments):
    """
    Punto de entrada único. `arguments` es el dict completo de args
    (patrón de auto-registro del repo: handler recibe UN diccionario
    posicional, no **kwargs).
    """
    mode = arguments.get("mode", "harmonic_analysis")
    params = arguments.get("params", {}) or {}

    if mode == "harmonic_analysis":
        return analyze_harmonics(
            times_hours=params["times_hours"],
            elevations=params["elevations"],
            constituents=params.get("constituents", DEFAULT_CONSTITUENTS),
        )
    elif mode == "reconstruct":
        return {
            "elevations": reconstruct_tide(
                times_hours=params["times_hours"],
                h0=params["h0_m"],
                harmonics=params["harmonics"],
            ).tolist()
        }
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            f"mode desconocido: {mode!r}. Modos validos: {TOOL_MODES}"
        )


TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Analisis armonico de mareas por minimos cuadrados (constituyentes "
        "M2, S2, N2, K2, K1, O1, P1, Q1) a partir de una serie de nivel del "
        "mar, y reconstruccion/prediccion a partir de armonicos ajustados."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": TOOL_MODES,
                "description": "harmonic_analysis (ajustar), reconstruct (predecir), validate",
            },
            "params": {
                "type": "object",
                "description": (
                    "harmonic_analysis: {times_hours, elevations, constituents?} | "
                    "reconstruct: {times_hours, h0_m, harmonics}"
                ),
            },
        },
        "required": ["mode"],
    },
}


def _register():
    try:
        from tool_registry import register_tool
        register_tool(name=TOOL_NAME, schema=TOOL_SCHEMA, handler=run)
    except ImportError:
        pass


_register()


if __name__ == "__main__":
    import json
    print(json.dumps(run({"mode": "validate"}), indent=2))
