"""
relaxometry_tool.py

Estimacion de T1/T2 a partir de datos de resonancia magnetica/NMR:
ajuste de curvas de recuperacion (T1, inversion-recovery o
saturation-recovery) y de decaimiento (T2, monoexponencial), mas
estimacion de SNR. Complementa a bloch_equation_tool: alli se simula la
fisica hacia adelante (dado T1/T2, predecir la senal); aca se resuelve
el problema inverso (dada la senal medida, estimar T1/T2).

Modes:
  - t1_fit: ajuste de T1 a partir de pares (tiempo, senal)
    (params: times_s, signal, method='inversion_recovery'|'saturation_recovery')
  - t2_fit: ajuste de T2 por regresion log-lineal de decaimiento
    monoexponencial (params: te_s, signal)
  - snr_estimate: SNR = media(senal) / desviacion_estandar(ruido)
    (params: signal_region, noise_region)
  - validate: auto-validacion contra casos con resultado conocido
"""
import json
import math

import numpy as np
from scipy.optimize import curve_fit

TOOL_NAME = "relaxometry_tool"


def _ir_model(t, m0, t1):
    return m0 * (1 - 2 * np.exp(-t / t1))


def _sr_model(t, m0, t1):
    return m0 * (1 - np.exp(-t / t1))


def t1_fit(times_s, signal, method="inversion_recovery"):
    t = np.asarray(times_s, dtype=float)
    s = np.asarray(signal, dtype=float)
    model = _ir_model if method == "inversion_recovery" else _sr_model
    m0_guess = float(np.max(np.abs(s)))
    t1_guess = float(np.median(t)) if np.median(t) > 0 else 1.0
    popt, _ = curve_fit(model, t, s, p0=[m0_guess, t1_guess], maxfev=10000)
    m0_fit, t1_fit_val = popt
    residuals = s - model(t, *popt)
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((s - np.mean(s)) ** 2))
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else None
    return {
        "method": method,
        "m0": float(m0_fit),
        "t1_s": float(t1_fit_val),
        "r_squared": r_squared,
        "n_points": len(t),
    }


def t2_fit(te_s, signal):
    te = np.asarray(te_s, dtype=float)
    s = np.asarray(signal, dtype=float)
    mask = s > 0
    te_m, s_m = te[mask], s[mask]
    # regresion log-lineal: ln(S) = ln(S0) - TE/T2
    A = np.vstack([te_m, np.ones_like(te_m)]).T
    slope, intercept = np.linalg.lstsq(A, np.log(s_m), rcond=None)[0]
    t2_val = -1.0 / slope if slope != 0 else float("inf")
    s0 = math.exp(intercept)
    pred = s0 * np.exp(-te_m / t2_val)
    ss_res = float(np.sum((s_m - pred) ** 2))
    ss_tot = float(np.sum((s_m - np.mean(s_m)) ** 2))
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else None
    return {
        "t2_s": float(t2_val),
        "s0": float(s0),
        "r_squared": r_squared,
        "n_points": int(mask.sum()),
    }


def snr_estimate(signal_region, noise_region):
    sig = np.asarray(signal_region, dtype=float)
    noise = np.asarray(noise_region, dtype=float)
    signal_mean = float(np.mean(sig))
    noise_std = float(np.std(noise, ddof=1)) if len(noise) > 1 else float(np.std(noise))
    snr = signal_mean / noise_std if noise_std > 0 else float("inf")
    return {
        "signal_mean": signal_mean,
        "noise_std": noise_std,
        "snr": snr,
        "snr_db": 20 * math.log10(snr) if snr not in (0, float("inf")) else None,
    }


def _validate():
    errors = []
    tests_total = 0
    tests_passed = 0

    tests_total += 1
    t2_true = 0.08
    s0_true = 100.0
    te = [0.01, 0.02, 0.04, 0.06, 0.08, 0.10]
    signal = [s0_true * math.exp(-x / t2_true) for x in te]
    r = t2_fit(te, signal)
    if abs(r["t2_s"] - t2_true) / t2_true < 1e-3:
        tests_passed += 1
    else:
        errors.append(f"t2_fit: T2 recuperado {r['t2_s']} != {t2_true}")

    tests_total += 1
    t1_true = 0.9
    m0_true = 50.0
    tr = [0.1, 0.3, 0.5, 0.8, 1.2, 2.0, 3.0]
    signal = [m0_true * (1 - math.exp(-x / t1_true)) for x in tr]
    r = t1_fit(tr, signal, method="saturation_recovery")
    if abs(r["t1_s"] - t1_true) / t1_true < 1e-2:
        tests_passed += 1
    else:
        errors.append(f"t1_fit(saturation): T1 recuperado {r['t1_s']} != {t1_true}")

    tests_total += 1
    t1_true = 1.2
    m0_true = 80.0
    ti = [0.1, 0.3, 0.6, 1.0, 1.5, 2.5, 4.0]
    signal = [m0_true * (1 - 2 * math.exp(-x / t1_true)) for x in ti]
    r = t1_fit(ti, signal, method="inversion_recovery")
    if abs(r["t1_s"] - t1_true) / t1_true < 1e-2:
        tests_passed += 1
    else:
        errors.append(f"t1_fit(inversion): T1 recuperado {r['t1_s']} != {t1_true}")

    tests_total += 1
    r = snr_estimate([10, 10, 10], [0, 0, 0])
    if r["snr"] == float("inf"):
        tests_passed += 1
    else:
        errors.append("snr_estimate: ruido cero deberia dar SNR infinito")

    tests_total += 1
    r = snr_estimate([20, 20, 20, 20], [1, -1, 1, -1])
    if r["noise_std"] > 0 and r["snr"] > 0:
        tests_passed += 1
    else:
        errors.append("snr_estimate: calculo inconsistente")

    return {
        "tool": TOOL_NAME,
        "tests_passed": tests_passed,
        "tests_total": tests_total,
        "errors": errors,
        "status": "PASSED" if tests_passed == tests_total else "FAILED",
        "validation_passed": tests_passed == tests_total,
    }


def run(mode, params=None):
    params = params or {}
    if mode == "t1_fit":
        return t1_fit(**params)
    if mode == "t2_fit":
        return t2_fit(**params)
    if mode == "snr_estimate":
        return snr_estimate(**params)
    if mode == "validate":
        return _validate()
    return {"error": f"modo desconocido: {mode}"}


TOOL_MODES = ["t1_fit", "t2_fit", "snr_estimate", "validate"]

TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Estimacion de parametros de relajacion T1/T2 en RM/NMR a partir "
        "de datos medidos: ajuste de recuperacion (T1, inversion o "
        "saturation recovery), decaimiento T2 (regresion log-lineal), y "
        "estimacion de SNR."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": TOOL_MODES,
                "description": "Modo de calculo (ver docstring de run())",
            },
            "params": {
                "type": "object",
                "description": "Parametros segun el modo (ver docstring de run())",
            },
        },
        "required": ["mode"],
    },
}


def _register():
    try:
        from tool_registry import register_tool
        register_tool(
            TOOL_NAME,
            TOOL_SCHEMA,
            lambda args: run(args.get("mode"), args.get("params", {})),
        )
    except ImportError:
        pass


_register()


if __name__ == "__main__":
    result = run("validate")
    print(json.dumps(result, indent=2, default=str))
    total = result["tests_total"]
    passed = result["tests_passed"]
    if result["validation_passed"]:
        print("→ LISTO PARA DESCARGAR e integrar a octave-mcp/tools/")
    else:
        print(f"→ {total - passed} test(s) fallaron — revisar")
