"""
forced_vibration_tool.py
Analisis armonico y transitorio forzado de vigas Euler-Bernoulli, extendiendo
fem_advanced_tool (que solo da frecuencias propias, sin respuesta a carga
oscilante). Amortiguamiento de Rayleigh: C = a0*M + a1*K.

Modos:
  - harmonic_response : respuesta estacionaria (barrido en frecuencia) de un
                         voladizo ante fuerza armonica en la punta, resuelto
                         directamente en el dominio de frecuencia:
                         (-omega^2*M + i*omega*C + K) X = F0
  - transient_free_decay : vibracion libre amortiguada (deflexion estatica
                         inicial, sin fuerza externa), integrada con Newmark-
                         beta (promedio constante, incondicionalmente estable).
  - validate : corre ambos y compara contra formulas analiticas de sistema
               1-GDL equivalente (modo 1 dominante, amortiguamiento ligero)

Matriz de masa consistente y rigidez: identicas a fem_advanced_tool
(elemento viga Euler-Bernoulli, 2 GDL/nodo).
"""
import numpy as np

FORCED_VIBRATION_TOOL_SCHEMA = {
    "name": "forced_vibration_tool",
    "description": (
        "Vibracion forzada de vigas Euler-Bernoulli con amortiguamiento de "
        "Rayleigh (C=a0*M+a1*K). mode='harmonic_response': barrido en "
        "frecuencia, respuesta estacionaria via solucion directa en dominio "
        "de frecuencia. mode='transient_free_decay': vibracion libre "
        "amortiguada via Newmark-beta. mode='validate' compara contra la "
        "formula analitica de amplificacion dinamica 1/(2*zeta) en resonancia "
        "y el decremento logaritmico teorico."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["harmonic_response", "transient_free_decay", "validate"]},
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


def _beam_ke(E, I, l):
    c = E*I/l**3
    return c*np.array([
        [12, 6*l, -12, 6*l],
        [6*l, 4*l**2, -6*l, 2*l**2],
        [-12, -6*l, 12, -6*l],
        [6*l, 2*l**2, -6*l, 4*l**2],
    ])


def _beam_me(rho, A, l):
    """Matriz de masa consistente (misma familia de funciones de forma
    cubicas que la rigidez; mejor convergencia que masa concentrada)."""
    c = rho*A*l/420.0
    return c*np.array([
        [156, 22*l, 54, -13*l],
        [22*l, 4*l**2, 13*l, -3*l**2],
        [54, 13*l, 156, -22*l],
        [-13*l, -3*l**2, -22*l, 4*l**2],
    ])


def _assemble_cantilever(E, I, rho, A, L, n_el):
    n_nodes = n_el + 1
    dof = 2*n_nodes
    le = L/n_el
    K = np.zeros((dof, dof))
    M = np.zeros((dof, dof))
    ke = _beam_ke(E, I, le)
    me = _beam_me(rho, A, le)
    for e in range(n_el):
        idx = [2*e, 2*e+1, 2*e+2, 2*e+3]
        for i in range(4):
            for j in range(4):
                K[idx[i], idx[j]] += ke[i, j]
                M[idx[i], idx[j]] += me[i, j]
    free = list(range(2, dof))  # empotrado en el nodo 0
    return K, M, free, dof


def _first_mode_omega(Kff, Mff):
    from scipy.linalg import eigh
    w2, phi = eigh(Kff, Mff)
    idx = np.argsort(w2)
    return float(np.sqrt(max(w2[idx[0]], 0.0))), phi[:, idx[0]]


def _harmonic_response(E=200e9, I=8e-6, rho=7850.0, A=0.001, L=3.0, n_el=6,
                        a0=0.0, a1=0.0, F0=100.0, omega_range_factor=1.5,
                        n_omega=121):
    K, M, free, dof = _assemble_cantilever(E, I, rho, A, L, n_el)
    Kff, Mff = K[np.ix_(free, free)], M[np.ix_(free, free)]
    Cff = a0*Mff + a1*Kff
    omega1, _ = _first_mode_omega(Kff, Mff)

    F = np.zeros(dof)
    F[-2] = F0   # fuerza transversal en el nodo de la punta
    Fff = F[free]

    omegas = np.linspace(1e-6, omega_range_factor*omega1, n_omega)
    tip_amplitudes = []
    tip_dof_local = free.index(dof-2)
    for om in omegas:
        Dyn = (-om**2)*Mff + 1j*om*Cff + Kff
        X = np.linalg.solve(Dyn, Fff.astype(complex))
        tip_amplitudes.append(float(abs(X[tip_dof_local])))

    # estatica (omega=0) para el factor de amplificacion dinamica
    X_static = np.linalg.solve(Kff, Fff)
    tip_static = float(abs(X_static[tip_dof_local]))

    peak_idx = int(np.argmax(tip_amplitudes))
    return {
        "mode": "harmonic_response",
        "omega1_rad_s": omega1,
        "omegas_rad_s": omegas.tolist(),
        "tip_amplitude_m": tip_amplitudes,
        "tip_static_deflection_m": tip_static,
        "peak_omega_rad_s": float(omegas[peak_idx]),
        "peak_amplitude_m": tip_amplitudes[peak_idx],
        "dynamic_amplification_factor": tip_amplitudes[peak_idx] / tip_static if tip_static > 0 else None,
    }


def _newmark_free_decay(E=200e9, I=8e-6, rho=7850.0, A=0.001, L=3.0, n_el=6,
                         a0=0.0, a1=0.0, dt=0.0005, n_steps=4000,
                         tip_initial_disp=0.01):
    K, M, free, dof = _assemble_cantilever(E, I, rho, A, L, n_el)
    Kff, Mff = K[np.ix_(free, free)], M[np.ix_(free, free)]
    Cff = a0*Mff + a1*Kff
    nfree = len(free)

    F = np.zeros(dof); F[-2] = 1.0
    # deflexion estatica bajo carga unitaria en la punta, escalada para dar
    # la forma inicial de deflexion (aprox. primer modo de una viga en voladizo)
    u0_shape = np.linalg.solve(Kff, F[free])
    tip_local = free.index(dof-2)
    u0 = u0_shape * (tip_initial_disp / u0_shape[tip_local])
    v0 = np.zeros(nfree)

    beta, gamma = 0.25, 0.5   # Newmark promedio constante, incond. estable
    a_ = np.zeros(nfree)
    Fzero = np.zeros(nfree)
    a_ = np.linalg.solve(Mff, Fzero - Cff@v0 - Kff@u0)

    Keff = Kff + (gamma/(beta*dt))*Cff + (1.0/(beta*dt**2))*Mff
    u, v, acc = u0.copy(), v0.copy(), a_.copy()
    tip_history = [float(u[tip_local])]
    times = [0.0]

    for n in range(n_steps):
        Feff = (Fzero
                + Mff @ ((1.0/(beta*dt**2))*u + (1.0/(beta*dt))*v + (1.0/(2*beta)-1.0)*acc)
                + Cff @ ((gamma/(beta*dt))*u + (gamma/beta-1.0)*v + dt*(gamma/(2*beta)-1.0)*acc))
        u_new = np.linalg.solve(Keff, Feff)
        acc_new = (1.0/(beta*dt**2))*(u_new - u) - (1.0/(beta*dt))*v - (1.0/(2*beta)-1.0)*acc
        v_new = v + dt*((1-gamma)*acc + gamma*acc_new)
        u, v, acc = u_new, v_new, acc_new
        tip_history.append(float(u[tip_local]))
        times.append((n+1)*dt)

    omega1, _ = _first_mode_omega(Kff, Mff)
    return {
        "mode": "transient_free_decay",
        "omega1_rad_s": omega1,
        "times_s": times,
        "tip_displacement_m": tip_history,
    }


def _extract_log_decrement(times, signal):
    """Detecta picos locales positivos y calcula el decremento logaritmico
    promedio entre picos sucesivos: delta = ln(x_i / x_{i+1})."""
    sig = np.array(signal)
    peaks_idx = []
    for i in range(1, len(sig)-1):
        if sig[i] > sig[i-1] and sig[i] >= sig[i+1] and sig[i] > 0:
            peaks_idx.append(i)
    if len(peaks_idx) < 3:
        return None, [], []
    peak_vals = sig[peaks_idx]
    peak_times = np.array(times)[peaks_idx]
    deltas = np.log(peak_vals[:-1] / peak_vals[1:])
    return float(np.mean(deltas)), peak_times.tolist(), peak_vals.tolist()


def _mode_validate():
    E, I, rho, A, L, n_el = 200e9, 8e-6, 7850.0, 0.001, 3.0, 6
    K, M, free, dof = _assemble_cantilever(E, I, rho, A, L, n_el)
    Kff, Mff = K[np.ix_(free, free)], M[np.ix_(free, free)]
    omega1, _ = _first_mode_omega(Kff, Mff)

    # elegir a0,a1 tal que zeta_1 = 2% exactamente usando solo rigidez
    # proporcional (a1) para simplificar: zeta1 = a1*omega1/2 => a1 = 2*zeta1/omega1
    zeta_target = 0.02
    a1 = 2*zeta_target/omega1
    a0 = 0.0

    # --- test armonico: factor de amplificacion dinamica en resonancia ---
    r_harm = _harmonic_response(E=E, I=I, rho=rho, A=A, L=L, n_el=n_el,
                                 a0=a0, a1=a1, F0=100.0, n_omega=401,
                                 omega_range_factor=1.3)
    amp_factor_numeric = r_harm["dynamic_amplification_factor"]
    amp_factor_analytic = 1.0/(2*zeta_target)   # amplificacion resonante, amortig. ligero
    amp_err_pct = 100*abs(amp_factor_numeric - amp_factor_analytic)/amp_factor_analytic

    # --- test transitorio: decremento logaritmico ---
    r_trans = _newmark_free_decay(E=E, I=I, rho=rho, A=A, L=L, n_el=n_el,
                                   a0=a0, a1=a1, dt=0.0002, n_steps=6000,
                                   tip_initial_disp=0.01)
    delta_numeric, peak_times, peak_vals = _extract_log_decrement(
        r_trans["times_s"], r_trans["tip_displacement_m"])
    delta_analytic = 2*np.pi*zeta_target/np.sqrt(1-zeta_target**2)
    delta_err_pct = (100*abs(delta_numeric - delta_analytic)/delta_analytic
                      if delta_numeric is not None else None)

    checks = {
        "harmonic_peak_near_omega1": bool(abs(r_harm["peak_omega_rad_s"] - omega1)/omega1 < 0.05),
        "dynamic_amplification_matches_1_over_2zeta": bool(amp_err_pct < 5.0),
        "log_decrement_extracted": bool(delta_numeric is not None),
        "log_decrement_matches_theory": bool(delta_err_pct is not None and delta_err_pct < 5.0),
    }

    return {
        "mode": "validate",
        "omega1_rad_s": omega1,
        "zeta_target": zeta_target,
        "rayleigh_coeffs": {"a0": a0, "a1": a1},
        "harmonic_check": {
            "peak_omega_rad_s": r_harm["peak_omega_rad_s"],
            "amplification_numeric": amp_factor_numeric,
            "amplification_analytic_1_over_2zeta": amp_factor_analytic,
            "relative_error_pct": amp_err_pct,
        },
        "transient_check": {
            "log_decrement_numeric": delta_numeric,
            "log_decrement_analytic": delta_analytic,
            "relative_error_pct": delta_err_pct,
            "n_peaks_detected": len(peak_vals),
        },
        "checks": checks,
        "expected": "en resonancia (omega=omega1), amplificacion dinamica ~ "
                    "1/(2*zeta) para amortiguamiento ligero (formula estandar "
                    "de sistema 1-GDL). En vibracion libre amortiguada, el "
                    "decremento logaritmico entre picos sucesivos = "
                    "2*pi*zeta/sqrt(1-zeta^2) (formula de libro de texto).",
        "validation_passed": bool(all(checks.values())),
    }


def compute_forced_vibration(mode, params=None):
    params = params or {}
    if mode == "harmonic_response":
        return _harmonic_response(**params)
    elif mode == "transient_free_decay":
        return _newmark_free_decay(**params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(f"modo desconocido: {mode}")


if __name__ == "__main__":
    import json
    r = compute_forced_vibration("validate")
    print(json.dumps(r, indent=2, ensure_ascii=False))

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("forced_vibration_tool", FORCED_VIBRATION_TOOL_SCHEMA, lambda args, _f=compute_forced_vibration: _f(**args))
