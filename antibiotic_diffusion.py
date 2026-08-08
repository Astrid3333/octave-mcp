"""
Modelo de difusion radial (2D, medio homogeneo semi-infinito) de un
antimicrobiano depositado en un disco de radio `a` sobre agar, segun la
teoria clasica de bioensayo de difusion en disco (Cooper 1955): el halo de
inhibicion es el radio donde la concentracion cae a la MIC (concentracion
minima inhibitoria) en el tiempo critico de incubacion.

Simplificacion explicita: liberacion instantanea (todo el soluto se
deposita en t=0 dentro del disco, sin disolucion progresiva ni consumo/
degradacion bacteriana). Es el mismo supuesto que sostiene la ley lineal
clasica de Cooper (diametro^2 de zona ~ ln(dosis)); no reemplaza un ensayo
real, es una herramienta de estimacion/comparacion de ordenes de magnitud.
"""
import math
import numpy as np
from scipy.special import ive
from scipy.integrate import quad
from scipy.optimize import brentq


def C_disco(r, t, C0, a, D):
    """Solucion exacta (Carslaw & Jaeger) para difusion radial 2D desde un
    disco de radio a con concentracion inicial uniforme C0. Usa la Bessel
    escalada (ive = I0(x)*exp(-x)) para evitar overflow."""
    if t <= 0:
        return C0 if r < a else (0.0 if r > a else C0 / 2)

    def integrando(rp):
        return rp * math.exp(-((r - rp) ** 2) / (4 * D * t)) * ive(0, r * rp / (2 * D * t))

    puntos = [r] if 0 < r < a else None
    valor, _ = quad(integrando, 0, a, limit=400, points=puntos)
    return float((C0 / (2 * D * t)) * valor)


def C_gauss_puntual(r, t, C0, a, D):
    """Aproximacion de fuente puntual (masa M = C0*pi*a^2 concentrada en
    r=0). Valida cuando a << sqrt(4*D*t)."""
    if t <= 0:
        return float("inf") if r == 0 else 0.0
    return (C0 * a ** 2) / (4 * D * t) * math.exp(-(r ** 2) / (4 * D * t))


def radio_zona(C0, a, D, MIC, t, r_max_inicial=None):
    """Radio donde C_disco(r,t) = MIC. None si ni siquiera el centro
    alcanza la MIC (no hay zona visible a ese tiempo)."""
    c_centro = C_disco(0.0, t, C0, a, D)
    if c_centro < MIC:
        return None

    r_max = r_max_inicial or max(a * 5, math.sqrt(4 * D * t) * 5)
    f = lambda r: C_disco(r, t, C0, a, D) - MIC
    intentos = 0
    while f(r_max) > 0 and intentos < 20:
        r_max *= 1.5
        intentos += 1
    if f(r_max) > 0:
        return None  # no converge a una zona finita en un rango razonable

    return brentq(f, a * 0.999 if a > 0 else 0.0, r_max, xtol=1e-8)


def regresion_log_lineal(x, y):
    """Minimos cuadrados simple de y = m*x + b, mismo criterio de R2 que
    historian_tool."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = len(x)
    m, b = np.polyfit(x, y, 1)
    y_pred = m * x + b
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1 - ss_res / ss_tot
    return {"pendiente": float(m), "intercepto": float(b), "r2": float(r2)}


# ---------------------------------------------------------------------------
# modos publicos
# ---------------------------------------------------------------------------

def zone_prediction(C0=1000.0, a=0.3, D=5e-6, MIC=1.0, t=57600.0):
    r_exacto = radio_zona(C0, a, D, MIC, t)
    r_gauss = None
    if r_exacto is not None:
        f_g = lambda r: C_gauss_puntual(r, t, C0, a, D) - MIC
        try:
            r_max_g = max(a * 5, math.sqrt(4 * D * t) * 5)
            intentos = 0
            while f_g(r_max_g) > 0 and intentos < 20:
                r_max_g *= 1.5
                intentos += 1
            r_gauss = brentq(f_g, 1e-9, r_max_g, xtol=1e-8)
        except ValueError:
            r_gauss = None

    resultado = {
        "radio_zona_cm_exacto": r_exacto,
        "diametro_zona_cm_exacto": 2 * r_exacto if r_exacto else None,
        "radio_zona_cm_aprox_puntual": r_gauss,
        "aproximacion_valida": (r_exacto is not None and r_gauss is not None
                                 and abs(r_exacto - r_gauss) / r_exacto < 0.05),
        "longitud_difusion_cm": math.sqrt(4 * D * t),
        "radio_disco_cm": a,
    }
    return resultado


def calibration_curve(a=0.3, D=5e-6, MIC=1.0, t=57600.0,
                       C0_valores=(200.0, 500.0, 1000.0, 2000.0, 5000.0, 10000.0)):
    diametros2 = []
    logs_C0 = []
    detalle = []
    for C0 in C0_valores:
        r = radio_zona(C0, a, D, MIC, t)
        if r is None:
            continue
        diametros2.append((2 * r) ** 2)
        logs_C0.append(math.log(C0))
        detalle.append({"C0": C0, "radio_cm": r, "diametro_cm": 2 * r})

    if len(diametros2) < 3:
        return {"escalado": True, "warning": "menos de 3 dosis produjeron zona medible", "detalle": detalle}

    reg = regresion_log_lineal(logs_C0, diametros2)
    return {"escalado": False, "regresion_diametro2_vs_ln_C0": reg, "detalle": detalle}


# ---------------------------------------------------------------------------
# validacion contra propiedades analiticas conocidas
# ---------------------------------------------------------------------------

def _validar():
    resultados = {}

    # 1) conservacion de masa: integral 2D de C(r,t) debe ser C0*pi*a^2 para todo t
    C0, a, D = 1000.0, 0.3, 5e-6
    masa_esperada = C0 * math.pi * a ** 2
    errores_masa = []
    for t in (1.0, 3600.0, 57600.0):
        integrando = lambda r: C_disco(r, t, C0, a, D) * 2 * math.pi * r
        r_max = a + 8 * math.sqrt(4 * D * max(t, 1e-6))
        masa, _ = quad(integrando, 0, r_max, limit=400, points=[a])
        errores_masa.append(float(abs(masa - masa_esperada) / masa_esperada))
    ok_masa = bool(max(errores_masa) < 1e-3)
    resultados["conservacion_masa"] = {"ok": ok_masa, "errores_relativos": errores_masa}

    # 2) limite de fuente puntual: a << sqrt(4Dt) -> exacto ~ aproximacion gaussiana
    a_chico, D2, t2, C0_2 = 0.01, 5e-6, 57600.0, 1000.0
    long_dif = math.sqrt(4 * D2 * t2)
    r_test = long_dif * 0.5
    c_exacto = C_disco(r_test, t2, C0_2, a_chico, D2)
    c_gauss = C_gauss_puntual(r_test, t2, C0_2, a_chico, D2)
    err_puntual = float(abs(c_exacto - c_gauss) / c_gauss)
    ok_puntual = bool(err_puntual < 0.01)
    resultados["limite_fuente_puntual"] = {"ok": ok_puntual, "error_relativo": err_puntual, "long_difusion_cm": long_dif}

    # 3) tiempo temprano: perfil casi escalon (C~C0 bien adentro, C~0 bien afuera)
    t_temprano = 0.5
    r_adentro = a * 0.3
    r_afuera = a * 3.0
    c_adentro = C_disco(r_adentro, t_temprano, C0, a, D)
    c_afuera = C_disco(r_afuera, t_temprano, C0, a, D)
    ok_escalon = bool((abs(c_adentro - C0) / C0 < 0.01) and (c_afuera / C0 < 0.01))
    resultados["limite_tiempo_temprano"] = {"ok": ok_escalon, "c_adentro": c_adentro, "c_afuera": c_afuera}

    # 4) ley lineal de Cooper: diametro^2 vs ln(C0) debe dar R2 muy alto
    cal = calibration_curve(a=a, D=D, MIC=1.0, t=57600.0)
    r2_cooper = float(cal["regresion_diametro2_vs_ln_C0"]["r2"]) if not cal["escalado"] else None
    ok_cooper = bool((not cal["escalado"]) and r2_cooper > 0.999)
    resultados["ley_cooper_diametro2_vs_ln_dosis"] = {"ok": ok_cooper, "r2": r2_cooper}

    resultados["todos_correctos"] = bool(all(v["ok"] for v in resultados.values() if isinstance(v, dict) and "ok" in v))
    return resultados


def compute_antibiotic_diffusion(mode="validate", C0=1000.0, a=0.3, D=5e-6, MIC=1.0, t=57600.0):
    if mode == "validate":
        return _validar()
    if mode == "zone_prediction":
        return zone_prediction(C0, a, D, MIC, t)
    if mode == "calibration_curve":
        return calibration_curve(a, D, MIC, t)
    return {"error": f"modo desconocido: {mode!r} (validos: validate, zone_prediction, calibration_curve)"}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_antibiotic_diffusion(mode="validate"), indent=2, ensure_ascii=False))
