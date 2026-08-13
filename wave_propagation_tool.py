import json
import numpy as np
from scipy.signal import find_peaks


def _fdtd_2d(nx, ny, nt, courant, src_pos, src_freq):
    dt = courant / np.sqrt(2)
    r2 = (dt / 1.0) ** 2
    u_prev = np.zeros((nx, ny))
    u_curr = np.zeros((nx, ny))
    hist = np.zeros((nt, nx, ny))

    for n in range(nt):
        lap = (
            np.roll(u_curr, 1, axis=0) + np.roll(u_curr, -1, axis=0)
            + np.roll(u_curr, 1, axis=1) + np.roll(u_curr, -1, axis=1)
            - 4 * u_curr
        )
        u_next = np.zeros((nx, ny))
        u_next[1:-1, 1:-1] = (
            2 * u_curr[1:-1, 1:-1] - u_prev[1:-1, 1:-1] + r2 * lap[1:-1, 1:-1]
        )
        t = n * dt
        t0 = 3.0 / src_freq
        sigma = 1.0 / src_freq
        u_next[src_pos] += np.sin(2 * np.pi * src_freq * t) * np.exp(-((t - t0) ** 2) / (2 * sigma ** 2))
        u_next[0, :] = 0; u_next[-1, :] = 0
        u_next[:, 0] = 0; u_next[:, -1] = 0
        u_prev, u_curr = u_curr, u_next
        hist[n] = u_curr
    return hist, dt


def wave_2d(params):
    nx = int(params.get("nx", 241))
    ny = int(params.get("ny", 241))
    nt = int(params.get("nt", 300))
    courant = float(params.get("courant", 0.7))
    src_freq = float(params.get("src_freq", 0.08))
    r_probe1 = int(params.get("r_probe1", 30))
    r_probe2 = int(params.get("r_probe2", 90))

    src_pos = (nx // 2, ny // 2)
    hist, dt = _fdtd_2d(nx, ny, nt, courant, src_pos, src_freq)

    probe1 = (src_pos[0] + r_probe1, src_pos[1])
    probe2 = (src_pos[0] + r_probe2, src_pos[1])
    trace1 = hist[:, probe1[0], probe1[1]]
    trace2 = hist[:, probe2[0], probe2[1]]

    peak_step1 = int(np.argmax(np.abs(trace1)))
    peak_step2 = int(np.argmax(np.abs(trace2)))

    if peak_step2 <= peak_step1:
        return {"error": "orden de picos invertido, revisar nt/r_probe", "passed": False}

    v_measured = (r_probe2 - r_probe1) / ((peak_step2 - peak_step1) * dt)
    v_expected = 1.0
    error_pct = abs(v_measured / v_expected - 1.0) * 100.0
    passed = bool(error_pct < 5.0)

    return {
        "r_probe1": r_probe1, "r_probe2": r_probe2,
        "peak_step_probe1": peak_step1, "peak_step_probe2": peak_step2,
        "v_measured": round(float(v_measured), 4), "v_expected": v_expected,
        "error_pct": round(error_pct, 4), "passed": passed,
    }


def interference(params):
    wavelength = float(params.get("wavelength", 10.0))
    d = float(params.get("slit_separation", 100.0))
    screen_dist = float(params.get("screen_distance", 2000.0))
    screen_width = float(params.get("screen_width", 2000.0))
    n_points = int(params.get("n_points", 4000))

    k = 2 * np.pi / wavelength
    y = np.linspace(-screen_width / 2, screen_width / 2, n_points)
    r1 = np.sqrt(screen_dist ** 2 + (y - d / 2) ** 2)
    r2 = np.sqrt(screen_dist ** 2 + (y + d / 2) ** 2)
    field = np.exp(1j * k * r1) + np.exp(1j * k * r2)
    intensity = np.abs(field) ** 2

    approx_spacing = wavelength * screen_dist / d
    min_distance_pts = max(1, int(0.3 * approx_spacing / (screen_width / n_points)))
    peak_idx, _ = find_peaks(intensity, prominence=0.5 * intensity.max(), distance=min_distance_pts)
    peaks_measured = y[peak_idx]

    m_max = int(d / wavelength)
    ms = np.arange(-m_max, m_max + 1)
    sin_theta = ms * wavelength / d
    valid = np.abs(sin_theta) < 1.0
    theta_m = np.arcsin(sin_theta[valid])
    y_theory = screen_dist * np.tan(theta_m)
    y_theory = y_theory[(y_theory >= -screen_width / 2) & (y_theory <= screen_width / 2)]

    if len(peaks_measured) == 0 or len(y_theory) == 0:
        return {"n_maxima_found": 0, "passed": False}

    errs = []
    for yp in peaks_measured:
        nearest = y_theory[np.argmin(np.abs(y_theory - yp))]
        denom = abs(nearest) if abs(nearest) > 1e-6 else approx_spacing
        errs.append(abs(yp - nearest) / denom * 100.0)
    max_error_pct = float(np.max(errs))
    mean_error_pct = float(np.mean(errs))

    passed = bool(max_error_pct < 1.0)

    return {
        "n_maxima_found": int(len(peaks_measured)),
        "n_theoretical_orders_visible": int(len(y_theory)),
        "measured_positions": [round(float(v), 3) for v in peaks_measured],
        "max_error_pct_vs_exact_theory": round(max_error_pct, 4),
        "mean_error_pct_vs_exact_theory": round(mean_error_pct, 4),
        "passed": passed,
    }


def diffraction(params):
    wavelength = float(params.get("wavelength", 10.0))
    a = float(params.get("slit_width", 30.0))
    screen_dist = float(params.get("screen_distance", 1000.0))
    theta_margin_factor = float(params.get("theta_margin_factor", 1.8))
    default_width = 2.0 * screen_dist * np.tan(theta_margin_factor * np.arcsin(min(0.99, wavelength / a)))
    screen_width = float(params.get("screen_width", default_width))
    n_points = int(params.get("n_points", 8000))

    y = np.linspace(1e-9, screen_width / 2, n_points)
    theta = np.arctan2(y, screen_dist)
    k = 2 * np.pi / wavelength
    beta = k * a * np.sin(theta) / 2.0
    amp = np.sin(beta) / beta
    intensity = amp ** 2

    sign_changes = np.where(np.diff(np.sign(amp)) != 0)[0]
    if len(sign_changes) > 0:
        i0 = sign_changes[0]
        b0, b1 = beta[i0], beta[i0 + 1]
        a0, a1 = amp[i0], amp[i0 + 1]
        frac = -a0 / (a1 - a0)
        theta_min_measured = float(theta[i0] + frac * (theta[i0 + 1] - theta[i0]))
    else:
        theta_min_measured = float("nan")

    theta_min_expected = float(np.arcsin(wavelength / a))
    error_pct = abs(theta_min_measured / theta_min_expected - 1.0) * 100.0 if theta_min_measured == theta_min_measured else float("nan")
    passed = bool(error_pct == error_pct and error_pct < 2.0)

    return {
        "theta_first_min_measured_rad": theta_min_measured if theta_min_measured == theta_min_measured else None,
        "theta_first_min_expected_rad": theta_min_expected,
        "error_pct": round(error_pct, 4) if error_pct == error_pct else None,
        "passed": passed,
    }


def validate(params=None):
    params = params or {}
    r1 = wave_2d(params.get("wave_2d", {}))
    r2 = interference(params.get("interference", {}))
    r3 = diffraction(params.get("diffraction", {}))
    validation_passed = bool(r1["passed"] and r2["passed"] and r3["passed"])
    return {
        "wave_2d": r1, "interference": r2, "diffraction": r3,
        "validation_passed": validation_passed,
    }


WAVE_PROPAGATION_TOOL_SCHEMA = {
    "name": "wave_propagation_tool",
    "description": (
        "Propagacion de ondas 2D: FDTD escalar 2D con verificacion de "
        "velocidad de frente de onda via tiempo de arribo a dos radios "
        "(mode='wave_2d'), interferencia de dos fuentes coherentes tipo "
        "Young con espaciado de franjas validado contra teoria "
        "(mode='interference'), y difraccion de Fraunhofer de rendija "
        "simple con posicion del primer minimo validada (mode='diffraction'). "
        "mode='validate' corre los 3 self-tests."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["wave_2d", "interference", "diffraction", "validate"]},
            "params": {"type": "object", "description": "Parametros especificos de cada modo"},
        },
        "required": ["mode"],
    },
}


def compute_wave_propagation(mode, params=None):
    params = params or {}
    if mode == "wave_2d":
        return wave_2d(params)
    elif mode == "interference":
        return interference(params)
    elif mode == "diffraction":
        return diffraction(params)
    elif mode == "validate":
        return validate(params)
    else:
        raise ValueError(f"modo desconocido: {mode}")


if __name__ == "__main__":
    d = compute_wave_propagation("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo"
    print("\nOK wave_propagation_tool.py")
