"""
chaos_diagnosis_tool.py

Diagnostico de caos determinista en una serie temporal 1D via reconstruccion
de Takens (delay embedding) + exponente de Lyapunov maximo (metodo de
Rosenstein) + test de significancia con datos sustitutos (surrogate data,
metodo IAAFT).

Motivacion: dado un observable escalar (nivel de rio, caudal, precipitacion),
diagnosticar si su dinamica es consistente con un sistema caotico determinista
de baja dimension (lambda1 > 0, con significancia estadistica frente a
sustitutos que preservan espectro/amplitud pero destruyen no-linealidad) o
si el comportamiento aparente es explicable por ruido lineal/estocastico.

Advertencia epistemica: con series cortas o ruidosas (el caso tipico en
datos hidrometeorologicos reales), un lambda1>0 medido NO es prueba
concluyente de caos por si solo. El test de sustitutos IAAFT es el control
minimo necesario: si el lambda1 medido no se distingue significativamente
del ensamble de sustitutos, el resultado es "no concluyente", no "caotico".

Integracion con hydrometeo_data_tool: mode="hydrometeo_run" llama a
compute_hydrometeo_data(mode="river_discharge"|"precipitation_history", ...)
y extrae la serie diaria del campo "daily" para alimentar el pipeline.
"""

import math
import random

try:
    from hydrometeo_data_tool import compute_hydrometeo_data
except ImportError:
    compute_hydrometeo_data = None


# ---------------------------------------------------------------------------
# Utilidades basicas
# ---------------------------------------------------------------------------

def _mean(x):
    return sum(x) / len(x)


def _std(x):
    m = _mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / len(x))


def _normalize(x):
    m, s = _mean(x), _std(x)
    if s == 0:
        return [0.0 for _ in x]
    return [(v - m) / s for v in x]


def _detrend_linear(x):
    n = len(x)
    t = list(range(n))
    tm, xm = _mean(t), _mean(x)
    num = sum((t[i] - tm) * (x[i] - xm) for i in range(n))
    den = sum((t[i] - tm) ** 2 for i in range(n))
    slope = num / den if den else 0.0
    intercept = xm - slope * tm
    return [x[i] - (slope * t[i] + intercept) for i in range(n)]


# ---------------------------------------------------------------------------
# Generador sintetico de Lorenz (Python puro, RK4) -- solo para _validate()
# ---------------------------------------------------------------------------

def _lorenz_series(n_steps=6000, dt=0.01, sigma=10.0, rho=28.0, beta=8.0 / 3.0,
                    y0=(1.0, 1.0, 1.0), discard=1000):
    def f(y):
        x, yv, z = y
        return (
            sigma * (yv - x),
            x * (rho - z) - yv,
            x * yv - beta * z,
        )

    y = list(y0)
    xs = []
    for i in range(n_steps + discard):
        k1 = f(y)
        y2 = [y[j] + dt / 2 * k1[j] for j in range(3)]
        k2 = f(y2)
        y3 = [y[j] + dt / 2 * k2[j] for j in range(3)]
        k3 = f(y3)
        y4 = [y[j] + dt * k3[j] for j in range(3)]
        k4 = f(y4)
        y = [y[j] + dt / 6 * (k1[j] + 2 * k2[j] + 2 * k3[j] + k4[j]) for j in range(3)]
        if i >= discard:
            xs.append(y[0])
    return xs


# ---------------------------------------------------------------------------
# Seleccion de tau: primer minimo de informacion mutua promedio (AMI)
# ---------------------------------------------------------------------------

def _average_mutual_information(x, tau, n_bins=16):
    n = len(x) - tau
    if n < 10:
        return None
    xa = x[:n]
    xb = x[tau:tau + n]
    lo, hi = min(x), max(x)
    if hi == lo:
        return 0.0
    width = (hi - lo) / n_bins

    def bin_idx(v):
        idx = int((v - lo) / width) if width > 0 else 0
        return min(idx, n_bins - 1)

    joint = {}
    marg_a = [0] * n_bins
    marg_b = [0] * n_bins
    for va, vb in zip(xa, xb):
        ia, ib = bin_idx(va), bin_idx(vb)
        joint[(ia, ib)] = joint.get((ia, ib), 0) + 1
        marg_a[ia] += 1
        marg_b[ib] += 1

    ami = 0.0
    for (ia, ib), c in joint.items():
        pij = c / n
        pi = marg_a[ia] / n
        pj = marg_b[ib] / n
        if pij > 0 and pi > 0 and pj > 0:
            ami += pij * math.log(pij / (pi * pj))
    return ami


def _select_tau(x, tau_max=30):
    amis = []
    for tau in range(1, tau_max + 1):
        v = _average_mutual_information(x, tau)
        if v is None:
            break
        amis.append((tau, v))
    if len(amis) < 3:
        return 1, amis
    for i in range(1, len(amis) - 1):
        if amis[i][1] < amis[i - 1][1] and amis[i][1] < amis[i + 1][1]:
            return amis[i][0], amis
    # sin minimo claro: fallback al tau con menor AMI encontrado
    best = min(amis, key=lambda p: p[1])
    return best[0], amis


# ---------------------------------------------------------------------------
# Embedding de Takens
# ---------------------------------------------------------------------------

def _embed(x, m, tau):
    n = len(x) - (m - 1) * tau
    if n <= 0:
        return []
    return [[x[i + j * tau] for j in range(m)] for i in range(n)]


def _euclid(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(len(a))))


# ---------------------------------------------------------------------------
# Seleccion de m: falsos vecinos mas cercanos (Kennel et al.)
# ---------------------------------------------------------------------------

def _false_nearest_neighbors_fraction(x, m, tau, rtol=15.0, atol_factor=2.0):
    emb_m = _embed(x, m, tau)
    emb_m1 = _embed(x, m + 1, tau)
    n = min(len(emb_m), len(emb_m1))
    if n < 10:
        return None
    ra = _std(x)
    false_count = 0
    valid_count = 0
    for i in range(n):
        best_j, best_d = None, float("inf")
        for j in range(n):
            if j == i:
                continue
            d = _euclid(emb_m[i], emb_m[j])
            if d < best_d:
                best_d, best_j = d, j
        if best_j is None or best_d == 0:
            continue
        extra = abs(x[i + m * tau] - x[best_j + m * tau]) if (i + m * tau < len(x) and best_j + m * tau < len(x)) else None
        if extra is None:
            continue
        valid_count += 1
        ratio = extra / best_d
        if ratio > rtol or best_d > atol_factor * ra:
            false_count += 1
    if valid_count == 0:
        return None
    return false_count / valid_count


def _select_m(x, tau, m_max=8, fnn_threshold=0.05, max_points=400):
    # submuestrear para que FNN (O(n^2)) sea manejable
    xs = x if len(x) <= max_points else x[:: max(1, len(x) // max_points)]
    for m in range(1, m_max + 1):
        frac = _false_nearest_neighbors_fraction(xs, m, tau)
        if frac is not None and frac < fnn_threshold:
            return m, frac
    return m_max, None


# ---------------------------------------------------------------------------
# Exponente de Lyapunov maximo: metodo de Rosenstein
# ---------------------------------------------------------------------------

def _rosenstein_lambda1(x, m, tau, dt=1.0, theiler_window=None, fit_frac=(0.05, 0.5)):
    emb = _embed(x, m, tau)
    n = len(emb)
    if n < 20:
        return None
    if theiler_window is None:
        theiler_window = m * tau

    nearest = []
    for i in range(n):
        best_j, best_d = None, float("inf")
        for j in range(n):
            if abs(j - i) <= theiler_window:
                continue
            d = _euclid(emb[i], emb[j])
            if d < best_d and d > 0:
                best_d, best_j = d, j
        nearest.append((best_j, best_d))

    # Techo de k independiente del peor caso individual: el bucle interno ya
    # corta por punto (ii>=n or jj>=n) si un vecino particular esta cerca del
    # final de la serie, asi que max_k puede ser un limite fijo razonable en
    # vez de derivarse de min(n - max(j0)), que un solo j0 cercano a n-1
    # colapsaba a un valor absurdamente chico (max_k=1) para toda la serie.
    max_k = min(int(n * 0.5), 60)
    max_k = max(max_k, 1)

    log_d_by_k = [[] for _ in range(max_k)]
    for i in range(n):
        j0, d0 = nearest[i]
        if j0 is None or d0 <= 0:
            continue
        for k in range(max_k):
            ii, jj = i + k, j0 + k
            if ii >= n or jj >= n:
                break
            d = _euclid(emb[ii], emb[jj])
            if d > 0:
                log_d_by_k[k].append(math.log(d))

    avg_log_d = []
    for k in range(max_k):
        if log_d_by_k[k]:
            avg_log_d.append(_mean(log_d_by_k[k]))
        else:
            avg_log_d.append(None)

    ks = [k for k in range(max_k) if avg_log_d[k] is not None]
    if len(ks) < 5:
        return None

    lo = ks[int(len(ks) * fit_frac[0])]
    hi = ks[int(len(ks) * fit_frac[1])]
    fit_ks = [k for k in ks if lo <= k <= hi]
    if len(fit_ks) < 3:
        fit_ks = ks

    tk = _mean(fit_ks)
    yk = _mean([avg_log_d[k] for k in fit_ks])
    num = sum((k - tk) * (avg_log_d[k] - yk) for k in fit_ks)
    den = sum((k - tk) ** 2 for k in fit_ks)
    slope = num / den if den else 0.0
    return slope / dt


# ---------------------------------------------------------------------------
# Datos sustitutos: IAAFT (Iterative Amplitude Adjusted Fourier Transform)
# ---------------------------------------------------------------------------

def _dft(x):
    n = len(x)
    re = [0.0] * n
    im = [0.0] * n
    for k in range(n):
        s_re = s_im = 0.0
        for t in range(n):
            ang = -2 * math.pi * k * t / n
            s_re += x[t] * math.cos(ang)
            s_im += x[t] * math.sin(ang)
        re[k], im[k] = s_re, s_im
    return re, im


def _idft(re, im):
    n = len(re)
    out = [0.0] * n
    for t in range(n):
        s = 0.0
        for k in range(n):
            ang = 2 * math.pi * k * t / n
            s += re[k] * math.cos(ang) - im[k] * math.sin(ang)
        out[t] = s / n
    return out


def _amplitudes(re, im):
    return [math.sqrt(re[k] ** 2 + im[k] ** 2) for k in range(len(re))]


def _iaaft_surrogate(x, n_iter=20, rng=None, max_n=200):
    # O(n^2) por DFT casera -- se recorta a max_n puntos para mantener
    # el costo manejable; suficiente para el test de significancia.
    rng = rng or random.Random()
    xs = x if len(x) <= max_n else x[:max_n]
    n = len(xs)
    sorted_vals = sorted(xs)
    target_re, target_im = _dft(xs)
    target_amp = _amplitudes(target_re, target_im)

    surrogate = xs[:]
    rng.shuffle(surrogate)

    for _ in range(n_iter):
        re, im = _dft(surrogate)
        phases = [math.atan2(im[k], re[k]) for k in range(n)]
        new_re = [target_amp[k] * math.cos(phases[k]) for k in range(n)]
        new_im = [target_amp[k] * math.sin(phases[k]) for k in range(n)]
        spectrum_matched = _idft(new_re, new_im)
        order = sorted(range(n), key=lambda i: spectrum_matched[i])
        surrogate = [0.0] * n
        for rank, idx in enumerate(order):
            surrogate[idx] = sorted_vals[rank]

    return surrogate


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def _diagnose(series, dt=1.0, detrend=True, n_surrogates=8, tau_max=30,
              m_max=8, rng_seed=0, surrogate_max_n=200):
    x = list(series)
    if len(x) < 50:
        return {"error": f"serie demasiado corta ({len(x)} puntos), se requieren al menos 50."}

    if detrend:
        x = _detrend_linear(x)
    x = _normalize(x)

    tau, ami_curve = _select_tau(x, tau_max=tau_max)
    m, fnn_frac = _select_m(x, tau, m_max=m_max)
    lambda1 = _rosenstein_lambda1(x, m, tau, dt=dt)

    if lambda1 is None:
        return {"error": "no se pudo estimar lambda1 (serie insuficiente tras embedding).",
                "tau": tau, "m": m}

    # lambda1 tiene efecto de tamano finito (mas positivo con series mas
    # largas, por sesgo del propio metodo de Rosenstein). Los surrogates
    # IAAFT se generan truncados a surrogate_max_n puntos (el DFT casera es
    # O(n^2) por iteracion y se vuelve inviable en series largas). Comparar
    # lambda1 de la serie completa contra lambda1 de surrogates truncados
    # arma un z-score con dos cantidades medidas en escalas distintas -- eso
    # producia falsos positivos (senoidal periodica) y falsos negativos
    # (Lorenz con z demasiado bajo). El fix: el lambda1 de referencia para
    # el z-score se mide sobre la MISMA longitud que los surrogates.
    x_cmp = x if len(x) <= surrogate_max_n else x[:surrogate_max_n]
    m_cmp, _ = _select_m(x_cmp, tau, m_max=m_max)
    lambda1_cmp = _rosenstein_lambda1(x_cmp, m_cmp, tau, dt=dt)
    if lambda1_cmp is None:
        lambda1_cmp = lambda1  # fallback si la serie truncada es insuficiente

    rng = random.Random(rng_seed)
    surrogate_lambdas = []
    for _ in range(n_surrogates):
        surr = _iaaft_surrogate(x, rng=rng, max_n=surrogate_max_n)
        surr_m, _ = _select_m(surr, tau, m_max=m_max)
        lam = _rosenstein_lambda1(surr, surr_m, tau, dt=dt)
        if lam is not None:
            surrogate_lambdas.append(lam)

    if len(surrogate_lambdas) >= 3:
        surr_mean = _mean(surrogate_lambdas)
        surr_std = _std(surrogate_lambdas)
        z = (lambda1_cmp - surr_mean) / surr_std if surr_std > 0 else None
    else:
        surr_mean = surr_std = z = None

    if z is None:
        diagnostico = "no_concluyente (sustitutos insuficientes)"
    elif lambda1_cmp > 0 and z > 2.0:
        diagnostico = "caos_probable"
    elif lambda1_cmp <= 0:
        diagnostico = "no_caotico"
    else:
        diagnostico = "no_concluyente"

    return {
        "tau": tau,
        "m": m,
        "fnn_fraction_at_m": fnn_frac,
        "lambda1": round(lambda1, 6),
        "lambda1_comparacion_surrogates": round(lambda1_cmp, 6),
        "lambda1_surrogate_mean": round(surr_mean, 6) if surr_mean is not None else None,
        "lambda1_surrogate_std": round(surr_std, 6) if surr_std is not None else None,
        "z_score": round(z, 3) if z is not None else None,
        "n_surrogates_ok": len(surrogate_lambdas),
        "diagnostico": diagnostico,
        "n_points_used": len(x),
        "n_points_comparacion": min(len(x), surrogate_max_n),
        "nota": (
            "lambda1 se reporta sobre la serie completa (mas preciso); el "
            "diagnostico y z_score usan lambda1_comparacion_surrogates, medido "
            "sobre la misma longitud que los surrogates para una comparacion "
            "justa (el metodo de Rosenstein tiene sesgo de tamano finito). "
            "z_score bajo o no disponible => resultado no concluyente, no "
            "evidencia de ausencia de caos."
        ),
    }


def _extract_hydrometeo_series(lat, lon, start_date, end_date, variable):
    if compute_hydrometeo_data is None:
        return None, "hydrometeo_data_tool no disponible en este entorno."
    mode = "river_discharge" if variable == "river_discharge" else "precipitation_history"
    key = "discharge_m3s" if variable == "river_discharge" else "precipitation_mm"
    result = compute_hydrometeo_data(mode, {
        "lat": lat, "lon": lon, "start_date": start_date, "end_date": end_date,
    })
    if "error" in result:
        return None, result["error"]
    daily = result.get("daily", [])
    series = [d[key] for d in daily if key in d]
    if len(series) < 50:
        return None, f"solo {len(series)} puntos disponibles (se requieren >=50)."
    return series, None


def compute_chaos_diagnosis(mode="series", series=None, dt=1.0, detrend=True,
                             n_surrogates=8, lat=None, lon=None,
                             start_date=None, end_date=None,
                             variable="river_discharge", **kwargs):
    if mode == "validate":
        return _validate()

    if mode == "hydrometeo_run":
        extracted, err = _extract_hydrometeo_series(lat, lon, start_date, end_date, variable)
        if err:
            return {"error": err}
        return _diagnose(extracted, dt=1.0, detrend=detrend, n_surrogates=n_surrogates)

    if mode == "series":
        if not series or len(series) < 50:
            return {"error": "mode='series' requiere una lista 'series' con al menos 50 puntos."}
        return _diagnose(series, dt=dt, detrend=detrend, n_surrogates=n_surrogates)

    return {"error": f"modo desconocido: {mode}. Modos validos: series, hydrometeo_run, validate"}


def _validate():
    checks = []

    # Check 1: serie caotica sintetica (Lorenz, coordenada x) debe dar
    # lambda1 > 0 y diagnostico distinto de "no_caotico".
    lorenz_x = _lorenz_series(n_steps=4000, dt=0.01)
    # dt efectivo de la serie observada: un punto cada paso de integracion
    r_chaos = _diagnose(lorenz_x, dt=0.01, detrend=False, n_surrogates=6, rng_seed=1)
    checks.append({
        "name": "lorenz_lambda1_positive",
        "lambda1": r_chaos.get("lambda1"),
        "diagnostico": r_chaos.get("diagnostico"),
        "passed": bool(r_chaos.get("lambda1") is not None and r_chaos["lambda1"] > 0),
    })

    # Check 2: serie puramente periodica (seno) debe dar lambda1 <= 0
    # (o al menos no reportar caos_probable) -- caso de referencia "no caotico".
    n = 2000
    sine_series = [math.sin(2 * math.pi * i / 50.0) for i in range(n)]
    r_periodic = _diagnose(sine_series, dt=1.0, detrend=False, n_surrogates=6, rng_seed=2)
    checks.append({
        "name": "periodic_signal_not_flagged_as_chaotic",
        "lambda1": r_periodic.get("lambda1"),
        "diagnostico": r_periodic.get("diagnostico"),
        "passed": bool(r_periodic.get("diagnostico") != "caos_probable"),
    })

    # Check 3: ruido blanco puro no debe reportar caos_probable con alta
    # confianza sistematicamente (chequeo mas laxo: solo que el pipeline
    # corra sin error y produzca un diagnostico).
    rng = random.Random(3)
    noise_series = [rng.gauss(0, 1) for _ in range(1000)]
    r_noise = _diagnose(noise_series, dt=1.0, detrend=False, n_surrogates=6, rng_seed=3)
    checks.append({
        "name": "white_noise_pipeline_runs",
        "diagnostico": r_noise.get("diagnostico"),
        "passed": bool("error" not in r_noise),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


CHAOS_DIAGNOSIS_TOOL_SCHEMA = {
    "name": "chaos_diagnosis",
    "description": (
        "Diagnostica si una serie temporal 1D (ej. caudal de rio, precipitacion) "
        "es consistente con dinamica caotica determinista de baja dimension, via "
        "reconstruccion de Takens (delay embedding con tau/m seleccionados "
        "automaticamente) + exponente de Lyapunov maximo (metodo de Rosenstein) "
        "+ test de significancia contra datos sustitutos IAAFT. mode='series' "
        "para pasar datos propios; mode='hydrometeo_run' para traer caudal/lluvia "
        "real via hydrometeo_data_tool y analizarlos directo. IMPORTANTE: "
        "lambda1>0 por si solo no es prueba de caos -- revisar z_score contra "
        "el ensamble de sustitutos antes de interpretar el resultado."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["series", "hydrometeo_run", "validate"],
                "default": "series",
            },
            "series": {"type": "array", "items": {"type": "number"},
                        "description": "Serie temporal 1D, requerido si mode='series'."},
            "dt": {"type": "number", "default": 1.0,
                   "description": "Intervalo de muestreo de la serie (para escalar lambda1)."},
            "detrend": {"type": "boolean", "default": True},
            "n_surrogates": {"type": "integer", "default": 8,
                              "description": "Cantidad de series sustitutas IAAFT para el test de significancia."},
            "lat": {"type": "number", "description": "Solo si mode='hydrometeo_run'."},
            "lon": {"type": "number", "description": "Solo si mode='hydrometeo_run'."},
            "start_date": {"type": "string", "description": "YYYY-MM-DD, solo si mode='hydrometeo_run'."},
            "end_date": {"type": "string", "description": "YYYY-MM-DD, solo si mode='hydrometeo_run'."},
            "variable": {"type": "string", "enum": ["river_discharge", "precipitation_history"],
                         "default": "river_discharge", "description": "Solo si mode='hydrometeo_run'."},
        },
        "required": [],
    },
}

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool(
    "chaos_diagnosis",
    CHAOS_DIAGNOSIS_TOOL_SCHEMA,
    lambda args, _f=compute_chaos_diagnosis: _f(**args),
)
