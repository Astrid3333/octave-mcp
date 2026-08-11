"""
quantum_cosmology_tool.py
==========================

Herramienta para octave-mcp: cosmologia cuantica en minisuperspace
via la ecuacion de Wheeler-DeWitt, resuelta como una ecuacion tipo
Schrodinger para el factor de escala "a".

ENFOQUE (explicito y honesto):
No se re-derivan desde cero los coeficientes exactos de gravedad
cuantica de una minisuperspace de GR. En su lugar se implementa el
modelo estandar, bien documentado y verificable: una ecuacion tipo
Schrodinger

    i*hbar dPsi/dt = -hbar^2/(2M) d^2Psi/da^2 + V(a) Psi

para tres potenciales de juguete (libre / lineal tipo curvatura
cerrada / armonico tipo constante cosmologica), de la cual se extrae:
  - la evolucion cuantica <a>(t)
  - la trayectoria de De Broglie-Bohm a_bohm(t) (guiada por la fase
    de Psi)
  - la trayectoria clasica del mismo Hamiltoniano H = p^2/(2M)+V(a)

y se compara evitacion de singularidad (bounce) cuantico vs clasico.
Esto reproduce el resultado celebre de cosmologia cuantica en
minisuperspace sin inventar constantes de Relatividad General.

Metodo numerico: Crank-Nicolson sobre los nodos INTERIORES de la
grilla (frontera Dirichlet Psi=0 excluida del sistema lineal, no
forzada post-hoc) -> unitario, conserva la norma exactamente salvo
error de redondeo.

Modos:
  - "self_test": corre 2 regression tests contra soluciones analiticas
    exactas (ensanchamiento gaussiano libre, periodo del oscilador
    armonico via FFT) + chequeo de conservacion de norma.
  - "friedmann_corrections": corre la evolucion cuantica + Bohm +
    clasica para un potencial dado y devuelve series temporales y
    diagnostico de bounce.
"""

import numpy as np


# ----------------------------------------------------------------------
# Compat numpy 1.x / 2.x (np.trapz fue removido en numpy 2.x)
# ----------------------------------------------------------------------
def _trapz(y, x=None, dx=1.0):
    if hasattr(np, "trapezoid"):
        return np.trapezoid(y, x=x, dx=dx)
    return np.trapz(y, x=x, dx=dx)  # pragma: no cover (numpy viejo)


# ----------------------------------------------------------------------
# Potenciales de juguete
# ----------------------------------------------------------------------
def _potential(a, kind, k):
    if kind == "free":
        return np.zeros_like(a)
    if kind == "linear":
        # analogo de curvatura cerrada (termino lineal en a)
        return k * a
    if kind == "harmonic":
        # analogo de constante cosmologica / Lambda
        return 0.5 * k * a ** 2
    raise ValueError(f"potencial desconocido: {kind}")


def _dpotential_da(a, kind, k):
    if kind == "free":
        return np.zeros_like(a)
    if kind == "linear":
        return k * np.ones_like(a)
    if kind == "harmonic":
        return k * a
    raise ValueError(f"potencial desconocido: {kind}")


# ----------------------------------------------------------------------
# Grilla y Hamiltoniano discreto (solo nodos interiores)
# ----------------------------------------------------------------------
def _build_grid(a_min, a_max, n_a):
    a = np.linspace(a_min, a_max, n_a)
    da = a[1] - a[0]
    return a, da


def _interior_hamiltonian(a, da, M, hbar, kind, k):
    """Matriz H (complexa) tridiagonal SOLO sobre nodos interiores.
    Frontera Dirichlet Psi=0 excluida del sistema lineal (no post-hoc)."""
    a_int = a[1:-1]
    n_int = len(a_int)
    V = _potential(a_int, kind, k)

    diag = (hbar ** 2 / (M * da ** 2)) + V
    off = -hbar ** 2 / (2.0 * M * da ** 2) * np.ones(n_int - 1)

    H = np.zeros((n_int, n_int), dtype=complex)
    idx = np.arange(n_int)
    H[idx, idx] = diag
    H[idx[:-1], idx[1:]] = off
    H[idx[1:], idx[:-1]] = off
    return H, a_int


def _initial_gaussian(a, a0, sigma0, p0, hbar):
    psi = np.exp(-((a - a0) ** 2) / (4.0 * sigma0 ** 2)) * np.exp(
        1j * p0 * (a - a0) / hbar
    )
    norm = np.sqrt(_trapz(np.abs(psi) ** 2, x=a))
    return psi / norm


# ----------------------------------------------------------------------
# Evolucion Crank-Nicolson (interior only, unitaria)
# ----------------------------------------------------------------------
def _evolve(a, da, M, hbar, kind, k, a0, sigma0, p0, t_max, n_t):
    H, a_int = _interior_hamiltonian(a, da, M, hbar, kind, k)
    n_int = len(a_int)
    dt = t_max / (n_t - 1)

    I = np.eye(n_int, dtype=complex)
    A = I + 1j * dt / (2.0 * hbar) * H  # avanza
    B = I - 1j * dt / (2.0 * hbar) * H  # conocido

    psi0_full = _initial_gaussian(a, a0, sigma0, p0, hbar)
    psi_int = psi0_full[1:-1].astype(complex)
    # renormalizar restringido a interior (la cola en la frontera es ~0)
    psi_int = psi_int / np.sqrt(_trapz(np.abs(psi_int) ** 2, x=a_int))

    times = np.linspace(0.0, t_max, n_t)
    a_expect = np.zeros(n_t)
    norm_hist = np.zeros(n_t)
    psi_snapshots = np.zeros((n_t, n_int), dtype=complex)

    psi = psi_int.copy()
    for it in range(n_t):
        psi_snapshots[it] = psi
        prob = np.abs(psi) ** 2
        norm_hist[it] = _trapz(prob, x=a_int)
        a_expect[it] = _trapz(a_int * prob, x=a_int) / norm_hist[it]
        if it < n_t - 1:
            rhs = B @ psi
            psi = np.linalg.solve(A, rhs)

    return times, a_int, psi_snapshots, a_expect, norm_hist, dt


# ----------------------------------------------------------------------
# Trayectoria de Bohm (guiada por la fase de Psi)
# ----------------------------------------------------------------------
def _bohm_trajectory(times, a_int, psi_snapshots, M, hbar, a0):
    n_t = len(times)
    a_bohm = np.zeros(n_t)
    a_bohm[0] = a0
    dt = times[1] - times[0] if n_t > 1 else 0.0

    for it in range(n_t - 1):
        psi = psi_snapshots[it]
        # gradiente espacial de Psi via diferencias finitas centradas
        dpsi_da = np.gradient(psi, a_int)
        with np.errstate(divide="ignore", invalid="ignore"):
            v_field = (hbar / M) * np.imag(dpsi_da / psi)
        v_field = np.nan_to_num(v_field, nan=0.0, posinf=0.0, neginf=0.0)
        v_at_a = np.interp(a_bohm[it], a_int, v_field)
        a_bohm[it + 1] = a_bohm[it] + v_at_a * dt

    return a_bohm


# ----------------------------------------------------------------------
# Trayectoria clasica (Hamilton, RK4) del mismo H = p^2/2M + V(a)
# ----------------------------------------------------------------------
def _classical_trajectory(times, M, kind, k, a0, p0):
    n_t = len(times)
    dt = times[1] - times[0] if n_t > 1 else 0.0
    a_cl = np.zeros(n_t)
    p_cl = np.zeros(n_t)
    a_cl[0], p_cl[0] = a0, p0

    def deriv(a, p):
        da_dt = p / M
        dp_dt = -_dpotential_da(np.array([a]), kind, k)[0]
        return da_dt, dp_dt

    for it in range(n_t - 1):
        a, p = a_cl[it], p_cl[it]
        k1a, k1p = deriv(a, p)
        k2a, k2p = deriv(a + 0.5 * dt * k1a, p + 0.5 * dt * k1p)
        k3a, k3p = deriv(a + 0.5 * dt * k2a, p + 0.5 * dt * k2p)
        k4a, k4p = deriv(a + dt * k3a, p + dt * k3p)
        a_cl[it + 1] = a + dt / 6.0 * (k1a + 2 * k2a + 2 * k3a + k4a)
        p_cl[it + 1] = p + dt / 6.0 * (k1p + 2 * k2p + 2 * k3p + k4p)

    return a_cl, p_cl


# ----------------------------------------------------------------------
# self_test: regression contra soluciones analiticas exactas
# ----------------------------------------------------------------------
def _self_test():
    results = {}

    # --- Test 1: ensanchamiento gaussiano libre --------------------
    M, hbar = 1.0, 1.0
    a0, sigma0, p0 = 0.0, 1.0, 0.0
    a_min, a_max, n_a = -30.0, 30.0, 400
    t_max, n_t = 4.0, 200

    a, da = _build_grid(a_min, a_max, n_a)
    times, a_int, psi_snap, a_expect, norm_hist, dt = _evolve(
        a, da, M, hbar, "free", 0.0, a0, sigma0, p0, t_max, n_t
    )

    sigma_num = np.zeros(n_t)
    for it in range(n_t):
        prob = np.abs(psi_snap[it]) ** 2
        norm = _trapz(prob, x=a_int)
        mean = _trapz(a_int * prob, x=a_int) / norm
        var = _trapz((a_int - mean) ** 2 * prob, x=a_int) / norm
        sigma_num[it] = np.sqrt(var)

    sigma_analytic = sigma0 * np.sqrt(1.0 + (hbar * times / (2.0 * M * sigma0 ** 2)) ** 2)
    rel_err_1 = np.max(np.abs(sigma_num - sigma_analytic) / sigma_analytic)
    norm_drift_1 = np.max(np.abs(norm_hist - norm_hist[0]))

    results["free_gaussian_spreading"] = {
        "max_relative_error_sigma": float(rel_err_1),
        "max_norm_drift": float(norm_drift_1),
        "pass": bool(rel_err_1 < 1e-2 and norm_drift_1 < 1e-6),
    }

    # --- Test 2: periodo del oscilador armonico (via FFT) -----------
    M, hbar, k = 1.0, 1.0, 1.0
    a0, sigma0, p0 = 3.0, 0.7, 0.0
    a_min, a_max, n_a = -20.0, 20.0, 500
    T_analytic = 2.0 * np.pi * np.sqrt(M / k)
    t_max, n_t = 4.0 * T_analytic, 800

    a, da = _build_grid(a_min, a_max, n_a)
    times, a_int, psi_snap, a_expect, norm_hist, dt = _evolve(
        a, da, M, hbar, "harmonic", k, a0, sigma0, p0, t_max, n_t
    )

    signal = a_expect - np.mean(a_expect)
    freqs = np.fft.rfftfreq(n_t, d=dt)
    spectrum = np.abs(np.fft.rfft(signal))
    spectrum[0] = 0.0  # descartar componente DC
    dominant_freq = freqs[np.argmax(spectrum)]
    T_numeric = 1.0 / dominant_freq if dominant_freq > 0 else np.inf

    rel_err_2 = abs(T_numeric - T_analytic) / T_analytic
    norm_drift_2 = np.max(np.abs(norm_hist - norm_hist[0]))

    results["harmonic_oscillator_period"] = {
        "period_analytic": float(T_analytic),
        "period_numeric": float(T_numeric),
        "max_relative_error": float(rel_err_2),
        "max_norm_drift": float(norm_drift_2),
        "pass": bool(rel_err_2 < 1e-2 and norm_drift_2 < 1e-6),
    }

    all_pass = results["free_gaussian_spreading"]["pass"] and results[
        "harmonic_oscillator_period"
    ]["pass"]

    return {"mode": "self_test", "all_pass": bool(all_pass), "tests": results}


# ----------------------------------------------------------------------
# friedmann_corrections: corrida fisica principal
# ----------------------------------------------------------------------
def _friedmann_corrections(params):
    kind = params.get("potential", "linear")
    if kind not in ("free", "linear", "harmonic"):
        raise ValueError("potential debe ser 'free', 'linear' o 'harmonic'")

    M = float(params.get("M", 1.0))
    hbar = float(params.get("hbar", 1.0))
    k = float(params.get("k", 1.0))
    a0 = float(params.get("a0", 5.0))
    sigma0 = float(params.get("sigma0", 0.8))
    p0 = float(params.get("p0", 0.0))
    a_min = float(params.get("a_min", -20.0))
    a_max = float(params.get("a_max", 20.0))
    n_a = int(params.get("n_a", 500))
    t_max = float(params.get("t_max", 20.0))
    n_t = int(params.get("n_t", 800))

    a, da = _build_grid(a_min, a_max, n_a)
    times, a_int, psi_snap, a_expect, norm_hist, dt = _evolve(
        a, da, M, hbar, kind, k, a0, sigma0, p0, t_max, n_t
    )

    a_bohm = _bohm_trajectory(times, a_int, psi_snap, M, hbar, a0)
    a_classical, p_classical = _classical_trajectory(times, M, kind, k, a0, p0)

    # diagnostico de "bounce": el clasico cruza a=0 (singularidad),
    # el cuantico (Bohm) no, y se queda acotado lejos de 0.
    classical_hits_singularity = bool(np.any(a_classical <= 0.0))
    bohm_min = float(np.min(a_bohm))
    bohm_avoids_singularity = bool(bohm_min > 0.0)

    norm_drift = float(np.max(np.abs(norm_hist - norm_hist[0])))

    return {
        "mode": "friedmann_corrections",
        "potential": kind,
        "params_used": {
            "M": M, "hbar": hbar, "k": k, "a0": a0, "sigma0": sigma0,
            "p0": p0, "a_min": a_min, "a_max": a_max, "n_a": n_a,
            "t_max": t_max, "n_t": n_t,
        },
        "diagnostics": {
            "norm_conservation_drift": norm_drift,
            "classical_hits_singularity": classical_hits_singularity,
            "bohm_min_a": bohm_min,
            "bohm_avoids_singularity": bohm_avoids_singularity,
            "bounce_detected": bool(
                classical_hits_singularity and bohm_avoids_singularity
            ),
        },
        "series": {
            "t": times.tolist(),
            "a_quantum_expectation": a_expect.tolist(),
            "a_bohm": a_bohm.tolist(),
            "a_classical": a_classical.tolist(),
            "norm_history": norm_hist.tolist(),
        },
    }


# ----------------------------------------------------------------------
# Entry point de la herramienta (firma compatible con octave-mcp)
# ----------------------------------------------------------------------
def compute_quantum_cosmology_tool(mode, params=None):
    params = params or {}
    if mode == "self_test":
        return _self_test()
    elif mode == "friedmann_corrections":
        return _friedmann_corrections(params)
    else:
        return {"error": f"Modo desconocido: {mode}. Modos validos: self_test, friedmann_corrections."}


QUANTUM_COSMOLOGY_TOOL_SCHEMA = {
    "name": "quantum_cosmology_tool",
    "description": (
        "Cosmologia cuantica en minisuperspace via la ecuacion de Wheeler-DeWitt, "
        "resuelta como una ecuacion tipo Schrodinger para el factor de escala a "
        "(Crank-Nicolson unitario, frontera Dirichlet excluida del sistema lineal). "
        "Potenciales de juguete: free, linear (analogo curvatura cerrada), harmonic "
        "(analogo Lambda) -- no son coeficientes exactos de GR, es el modelo estandar "
        "y verificable de cosmologia cuantica en minisuperspace. mode=self_test: corre "
        "2 regression tests contra soluciones analiticas exactas (ensanchamiento "
        "gaussiano libre, periodo del oscilador armonico via FFT) + chequeo de "
        "conservacion de norma. mode=friedmann_corrections: evolucion cuantica <a>(t), "
        "trayectoria de De Broglie-Bohm, trayectoria clasica del mismo Hamiltoniano, y "
        "diagnostico de bounce (evitacion cuantica de la singularidad clasica)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["self_test", "friedmann_corrections"]},
            "params": {
                "type": "object",
                "properties": {
                    "potential": {"type": "string", "enum": ["free", "linear", "harmonic"], "description": "Potencial de juguete (default 'linear')"},
                    "M": {"type": "number", "description": "Masa efectiva en la ecuacion tipo Schrodinger (default 1.0)"},
                    "hbar": {"type": "number", "description": "hbar en unidades del modelo (default 1.0)"},
                    "k": {"type": "number", "description": "Constante de acoplamiento del potencial linear/harmonic (default 1.0)"},
                    "a0": {"type": "number", "description": "Posicion inicial del paquete de onda / condicion inicial clasica (default 5.0)"},
                    "sigma0": {"type": "number", "description": "Ancho inicial del paquete gaussiano (default 0.8)"},
                    "p0": {"type": "number", "description": "Momento inicial del paquete de onda (default 0.0)"},
                    "a_min": {"type": "number", "description": "Borde inferior de la grilla en a (default -20.0)"},
                    "a_max": {"type": "number", "description": "Borde superior de la grilla en a (default 20.0)"},
                    "n_a": {"type": "integer", "description": "Numero de puntos de grilla en a (default 500)"},
                    "t_max": {"type": "number", "description": "Tiempo total de evolucion (default 20.0)"},
                    "n_t": {"type": "integer", "description": "Numero de pasos temporales (default 800)"},
                },
            },
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_quantum_cosmology_tool("self_test"), indent=2))
