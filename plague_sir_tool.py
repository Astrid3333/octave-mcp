"""
plague_sir_tool.py -- SIR inverso para brotes historicos de peste a partir de
registros de defunciones semanales (proxy cuantitativo cuando no hay fuente
epidemiologica directa). Ajusta beta (tasa de contagio) manteniendo gamma
fijo (parametro de literatura, no medido), integra el sistema SIR con RK4,
y reporta R0 = beta/gamma. No corrige por subregistro de actas parroquiales,
migracion, ni estacionalidad -- estimacion de orden de magnitud, no
reconstruccion epidemiologica precisa. La interpretacion social (hacinamiento
vs dispersion) queda a cargo de quien usa el resultado.
"""
import re
import numpy as np
from scipy.optimize import curve_fit


def _deriv_sir(S, I, beta, gamma, N):
    dS = -beta * S * I / N
    dI = beta * S * I / N - gamma * I
    return dS, dI


def _rk4_sir(beta, gamma, S0, I0, n_semanas, sub_pasos=20):
    N = S0 + I0
    S, I = S0, I0
    dt = 1.0 / sub_pasos
    muertes_semanales = []
    for _ in range(n_semanas):
        muertes_semana = 0.0
        for _p in range(sub_pasos):
            k1S, k1I = _deriv_sir(S, I, beta, gamma, N)
            k2S, k2I = _deriv_sir(S + dt/2*k1S, I + dt/2*k1I, beta, gamma, N)
            k3S, k3I = _deriv_sir(S + dt/2*k2S, I + dt/2*k2I, beta, gamma, N)
            k4S, k4I = _deriv_sir(S + dt*k3S, I + dt*k3I, beta, gamma, N)
            dS = (k1S + 2*k2S + 2*k3S + k4S) / 6 * dt
            dI = (k1I + 2*k2I + 2*k3I + k4I) / 6 * dt
            muertes_semana += gamma * I * dt
            S = max(S + dS, 0.0)
            I = max(I + dI, 0.0)
        muertes_semanales.append(muertes_semana)
    return np.array(muertes_semanales)


def _ajustar_beta(muertes_observadas, gamma, poblacion_estimada,
                   beta_inicial=0.3, I0_frac_inicial=0.01):
    n = len(muertes_observadas)
    x = np.arange(n)

    def modelo(x, beta, I0_frac):
        beta_c = max(beta, 1e-6)
        I0_frac_c = min(max(I0_frac, 1e-6), 0.5)
        I0 = I0_frac_c * poblacion_estimada
        S0 = poblacion_estimada - I0
        return _rk4_sir(beta_c, gamma, S0, I0, n)

    popt, pcov = curve_fit(modelo, x, muertes_observadas,
                            p0=[beta_inicial, I0_frac_inicial],
                            bounds=([1e-6, 1e-6], [5.0, 0.5]),
                            maxfev=5000)
    beta_fit, I0_frac_fit = popt
    perr = np.sqrt(np.diag(pcov)) if pcov is not None else [float("nan")] * 2
    modelo_pred = modelo(x, *popt)
    ss_res = np.sum((muertes_observadas - modelo_pred) ** 2)
    ss_tot = np.sum((muertes_observadas - np.mean(muertes_observadas)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {
        "beta_ajustado": float(beta_fit),
        "beta_error_std": float(perr[0]),
        "I0_fraccion_ajustada": float(I0_frac_fit),
        "gamma_fijo": gamma,
        "R0_reproductivo_basico": float(beta_fit / gamma),
        "r2_ajuste": float(r2),
        "n_semanas": n,
        "muertes_modelo": [round(float(v), 2) for v in modelo_pred],
        "muertes_observadas": [round(float(v), 2) for v in muertes_observadas],
    }


def _parse_defunciones(text_data):
    frases = re.split(r'(?<=[.!?])\s+', text_data)
    verbo = re.compile(r'muri|falleci|pereci', re.IGNORECASE)
    resultados = []
    for frase in frases:
        if not verbo.search(frase):
            continue
        m_semana = re.search(r'semana\s+(\d+)', frase, re.IGNORECASE)
        m_num = re.search(r'(\d+)\s+(?:personas?|habitantes?|vecinos?|almas?)', frase, re.IGNORECASE)
        if m_semana and m_num:
            resultados.append((int(m_semana.group(1)), int(m_num.group(1))))
    if not resultados:
        return None
    resultados.sort(key=lambda t: t[0])
    semanas = [r[0] for r in resultados]
    muertes = [r[1] for r in resultados]
    return semanas, muertes


def _preset_peste_demo():
    beta_true = 0.9
    gamma_true = 0.4
    poblacion = 2000
    I0_true = 15
    S0_true = poblacion - I0_true
    n_semanas = 12
    muertes = _rk4_sir(beta_true, gamma_true, S0_true, I0_true, n_semanas)
    frases = [
        f"En la semana {i} murieron {int(round(m))} personas por la peste en la ciudad."
        for i, m in enumerate(muertes, start=1)
    ]
    texto = " ".join(frases)
    verdad = {
        "beta_verdadero": beta_true,
        "gamma_usado": gamma_true,
        "poblacion_estimada": poblacion,
        "R0_verdadero": beta_true / gamma_true,
    }
    return texto, verdad


def compute_plague_sir(mode="validate", text_data=None, preset=None,
                        gamma=0.4, poblacion_estimada=2000.0):
    if mode == "validate":
        texto, verdad = _preset_peste_demo()
        parsed = _parse_defunciones(texto)
        if parsed is None:
            return {"error": "parser no extrajo datos del preset -- bug interno"}
        _semanas, muertes = parsed
        ajuste = _ajustar_beta(np.array(muertes, dtype=float),
                                verdad["gamma_usado"], verdad["poblacion_estimada"])
        error_relativo_beta = abs(ajuste["beta_ajustado"] - verdad["beta_verdadero"]) / verdad["beta_verdadero"]
        ok = error_relativo_beta < 0.1 and ajuste["r2_ajuste"] > 0.95
        return {
            "ok": ok,
            "beta_verdadero": verdad["beta_verdadero"],
            "beta_recuperado": ajuste["beta_ajustado"],
            "error_relativo_beta": round(error_relativo_beta, 4),
            "R0_verdadero": verdad["R0_verdadero"],
            "R0_recuperado": ajuste["R0_reproductivo_basico"],
            "r2_ajuste": ajuste["r2_ajuste"],
        }

    if mode == "fit_beta":
        if text_data is None and preset is not None:
            if preset == "peste_demo":
                text_data, _ = _preset_peste_demo()
            else:
                return {"error": f"preset desconocido: {preset!r}"}
        if not text_data:
            return {"error": "hay que pasar text_data (o preset='peste_demo') para mode='fit_beta'"}
        parsed = _parse_defunciones(text_data)
        if parsed is None:
            return {"error": "no se pudieron extraer defunciones semanales -- formato esperado: 'en la semana N murieron X personas'"}
        semanas, muertes = parsed
        if len(muertes) < 4:
            return {"error": f"solo se extrajeron {len(muertes)} semanas, se requieren al menos 4"}
        resultado = _ajustar_beta(np.array(muertes, dtype=float), gamma, poblacion_estimada)
        resultado["semanas_detectadas"] = semanas
        resultado["nota"] = ("gamma es un parametro fijo de literatura, no ajustado -- R0 depende "
                              "directamente de ese supuesto. poblacion_estimada tambien es externa, "
                              "no dato censal directo salvo que lo tengas de fuente primaria.")
        return resultado

    return {"error": f"modo desconocido: {mode!r} (validos: fit_beta, validate)"}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_plague_sir(mode="validate"), indent=2, ensure_ascii=False))
