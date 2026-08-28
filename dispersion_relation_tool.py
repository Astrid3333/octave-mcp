import tool_registry
import json
import numpy as np


def _check_params(params, allowed_keys, mode_name):
    """Valida que las claves de params sean subconjunto de allowed_keys.
    Si hay una clave no reconocida, tira ValueError explicito en vez de
    dejar que params.get() la ignore silenciosamente y caiga a un
    default sin avisar (bug real detectado: depth_m en water_waves)."""
    unknown = sorted(set(params.keys()) - set(allowed_keys))
    if unknown:
        raise ValueError(
            f"[{mode_name}] parametro(s) no reconocido(s): {unknown}. "
            f"Validos: {sorted(allowed_keys)}"
        )


# ---------------------------------------------------------------------------
# mode 1: plasma
# ---------------------------------------------------------------------------
def plasma(params):
    """Relacion de dispersion de ondas en plasma no magnetizado.
    wave_type='electromagnetic': onda EM transversal, omega^2 = omega_p^2 + c^2 k^2
    (cutoff exacto en k=0: omega=omega_p, y para k grande tiende a la luz en
    vacio omega->c*k).
    wave_type='langmuir': onda electrostatica longitudinal (Bohm-Gross),
    omega^2 = omega_p^2 + 3 k^2 v_th^2.
    Se valida: (a) el cutoff exacto en k=0, (b) que la velocidad de grupo
    numerica (diferencia finita central) coincide con la analitica
    domega/dk = c^2 k/omega (EM) o 3 k v_th^2/omega (Langmuir)."""
    _check_params(
        params, {"wave_type", "omega_p", "c", "v_th", "k_max", "n_points"}, "plasma"
    )
    wave_type = params.get("wave_type", "electromagnetic")
    omega_p = float(params.get("omega_p", 1.0e10))  # rad/s
    c = float(params.get("c", 3.0e8))
    v_th = float(params.get("v_th", 1.0e6))
    k_max = float(params.get("k_max", 5.0 * omega_p / c if wave_type == "electromagnetic" else 5.0 * omega_p / max(v_th, 1e-9)))
    n_points = int(params.get("n_points", 400))

    k = np.linspace(0.0, k_max, n_points)

    if wave_type == "electromagnetic":
        omega = np.sqrt(omega_p ** 2 + (c * k) ** 2)
        vg_analytic = np.zeros_like(k)
        vg_analytic[1:] = (c ** 2) * k[1:] / omega[1:]
    elif wave_type == "langmuir":
        omega = np.sqrt(omega_p ** 2 + 3.0 * (k * v_th) ** 2)
        vg_analytic = np.zeros_like(k)
        vg_analytic[1:] = 3.0 * (v_th ** 2) * k[1:] / omega[1:]
    else:
        raise ValueError(f"wave_type desconocido: {wave_type}")

    cutoff_measured = float(omega[0])
    cutoff_error_pct = abs(cutoff_measured / omega_p - 1.0) * 100.0

    dk = k[1] - k[0]
    vg_numeric = np.gradient(omega, dk)
    mid = slice(5, -5)
    vg_err_pct = float(np.max(np.abs(vg_numeric[mid] - vg_analytic[mid]) / np.maximum(np.abs(vg_analytic[mid]), 1e-30)) * 100.0)

    passed = bool(cutoff_error_pct < 1e-6 and vg_err_pct < 1.0)

    return {
        "wave_type": wave_type,
        "omega_p": omega_p,
        "cutoff_measured": cutoff_measured,
        "cutoff_error_pct": round(cutoff_error_pct, 8),
        "group_velocity_max_error_pct": round(vg_err_pct, 6),
        "omega_at_kmax": float(omega[-1]),
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# mode 2: water_waves
# ---------------------------------------------------------------------------
def water_waves(params):
    """Relacion de dispersion completa de ondas de gravedad-capilaridad en
    agua de profundidad finita h:
        omega^2 = (g k + (sigma/rho) k^3) * tanh(k h)
    Se valida contra los dos limites analiticos clasicos:
    (a) aguas profundas (k h >> 1): tanh(k h)->1, omega^2 ~ g k + (sigma/rho) k^3
    (b) aguas someras (k h << 1): tanh(k h)~k h, omega^2 ~ g h k^2
        (ondas no dispersivas, vg=vp=sqrt(g h))."""
    _check_params(params, {"g", "rho", "sigma", "h"}, "water_waves")
    g = float(params.get("g", 9.81))
    rho = float(params.get("rho", 1000.0))
    sigma = float(params.get("sigma", 0.072))  # tension superficial agua-aire N/m
    h = float(params.get("h", 50.0))  # profundidad, m

    def omega_full(k):
        return np.sqrt((g * k + (sigma / rho) * k ** 3) * np.tanh(k * h))

    # --- deep water check: k h >> 1 ---
    k_deep = 20.0 / h  # k*h=20, bien en regimen profundo
    omega_deep_full = omega_full(np.array([k_deep]))[0]
    omega_deep_approx = np.sqrt(g * k_deep + (sigma / rho) * k_deep ** 3)
    deep_error_pct = abs(omega_deep_full / omega_deep_approx - 1.0) * 100.0

    # --- shallow water check: k h << 1, despreciando capilaridad ---
    k_shallow = 1e-4 / h  # k*h=1e-4, bien en regimen somero
    omega_shallow_full = omega_full(np.array([k_shallow]))[0]
    omega_shallow_approx = k_shallow * np.sqrt(g * h)
    shallow_error_pct = abs(omega_shallow_full / omega_shallow_approx - 1.0) * 100.0

    # --- no dispersion en aguas someras: vg=vp=sqrt(g h) ---
    dk = k_shallow * 1e-3
    vp_shallow = omega_shallow_full / k_shallow
    vg_shallow = (omega_full(np.array([k_shallow + dk]))[0] - omega_full(np.array([k_shallow - dk]))[0]) / (2 * dk)
    c_shallow_theory = np.sqrt(g * h)
    nondispersive_error_pct = abs(vg_shallow / vp_shallow - 1.0) * 100.0
    shallow_speed_error_pct = abs(vp_shallow / c_shallow_theory - 1.0) * 100.0

    passed = bool(
        deep_error_pct < 0.1 and shallow_error_pct < 0.1
        and nondispersive_error_pct < 0.1 and shallow_speed_error_pct < 0.1
    )

    return {
        "h": h,
        "deep_water_check": {"k_h": float(k_deep * h), "error_pct": round(deep_error_pct, 6)},
        "shallow_water_check": {"k_h": float(k_shallow * h), "error_pct": round(shallow_error_pct, 6)},
        "shallow_nondispersive_check": {
            "vp": round(float(vp_shallow), 6), "vg": round(float(vg_shallow), 6),
            "c_theory_sqrt_gh": round(float(c_shallow_theory), 6),
            "vg_vs_vp_error_pct": round(nondispersive_error_pct, 6),
            "vp_vs_theory_error_pct": round(shallow_speed_error_pct, 6),
        },
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# mode 3: periodic_medium
# ---------------------------------------------------------------------------
def periodic_medium(params):
    """Estructura de bandas de un medio periodico 1D (analogo Kronig-Penney
    para ondas acusticas/EM), via matriz de transferencia de una celda
    bilaminar (capas 1 y 2, espesores d1,d2, velocidades c1,c2, impedancias
    Z1,Z2). Relacion de dispersion de Bloch exacta:
        cos(K a) = cos(k1 d1) cos(k2 d2)
                   - 0.5*(Z1/Z2 + Z2/Z1) * sin(k1 d1) sin(k2 d2)
    con a=d1+d2, k_i=omega/c_i. |RHS|>1 => banda prohibida (K complejo).
    Se valida: (a) con impedancias iguales (Z1=Z2) y c1=c2, el medio es
    homogeneo y K=omega/c exactamente, sin gaps; (b) con contraste de
    impedancia/velocidad, se abre un gap cerca de la condicion de Bragg
    k1 d1 + k2 d2 = pi."""
    _check_params(
        params, {"d1", "d2", "c1", "c2", "Z1", "Z2", "n_omega"}, "periodic_medium"
    )
    d1 = float(params.get("d1", 1.0))
    d2 = float(params.get("d2", 1.0))
    c1 = float(params.get("c1", 1.0))
    c2 = float(params.get("c2", 2.0))
    Z1 = float(params.get("Z1", 1.0))
    Z2 = float(params.get("Z2", 2.0))
    n_omega = int(params.get("n_omega", 2000))
    a = d1 + d2

    def rhs_of_omega(omega, c1_, c2_, Z1_, Z2_):
        k1 = omega / c1_
        k2 = omega / c2_
        return (np.cos(k1 * d1) * np.cos(k2 * d2)
                - 0.5 * (Z1_ / Z2_ + Z2_ / Z1_) * np.sin(k1 * d1) * np.sin(k2 * d2))

    # --- check homogeneo (sin contraste): K debe ser exactamente omega/c ---
    omega_test = np.linspace(1e-6, 3.0 * np.pi * c1 / a, 50)
    rhs_homog = rhs_of_omega(omega_test, c1, c1, 1.0, 1.0)
    K_homog = np.arccos(np.clip(rhs_homog, -1.0, 1.0)) / a
    K_homog_theory = omega_test / c1
    # arccos da rama principal [0,pi/a]; comparar modulo pliegue de zona
    K_folded_theory = np.abs(np.mod(K_homog_theory + np.pi / a, 2 * np.pi / a) - np.pi / a)
    homog_error = float(np.max(np.abs(K_homog - K_folded_theory)))
    homog_passed = bool(homog_error < 1e-6)

    # --- estructura de bandas con contraste real ---
    omega_bragg = np.pi * c1 * c2 / (c2 * d1 + c1 * d2)  # aprox Bragg (Z iguales o no)
    omega_scan = np.linspace(1e-6, 2.5 * omega_bragg, n_omega)
    rhs_scan = rhs_of_omega(omega_scan, c1, c2, Z1, Z2)
    in_gap = np.abs(rhs_scan) > 1.0

    # tomar solo el PRIMER gap contiguo (orden fundamental de Bragg); a
    # frecuencias mas altas aparecen gaps de orden superior que no deben
    # fusionarse con el primero al medir su centro.
    idx = np.where(in_gap)[0]
    gap_found = bool(len(idx) > 0)
    if gap_found:
        start = idx[0]
        prev = idx[0]
        for i in idx[1:]:
            if i != prev + 1:
                break
            prev = i
        gap_low, gap_high = float(omega_scan[start]), float(omega_scan[prev])
        gap_center = 0.5 * (gap_low + gap_high)
        bragg_error_pct = abs(gap_center / omega_bragg - 1.0) * 100.0
    else:
        gap_low = gap_high = gap_center = None
        bragg_error_pct = float("nan")

    contrast_passed = bool(gap_found and bragg_error_pct == bragg_error_pct and bragg_error_pct < 15.0)

    passed = bool(homog_passed and contrast_passed)

    return {
        "homogeneous_limit_check": {"max_abs_error_K": homog_error, "passed": homog_passed},
        "band_gap_check": {
            "omega_bragg_estimate": float(omega_bragg),
            "gap_found": gap_found,
            "gap_omega_low": gap_low, "gap_omega_high": gap_high,
            "gap_center": gap_center,
            "bragg_error_pct": round(bragg_error_pct, 4) if bragg_error_pct == bragg_error_pct else None,
            "passed": contrast_passed,
        },
        "passed": passed,
    }


# ---------------------------------------------------------------------------
def validate(params=None):
    params = params or {}
    r1 = plasma(params.get("plasma", {}))
    r2 = water_waves(params.get("water_waves", {}))
    r3 = periodic_medium(params.get("periodic_medium", {}))
    validation_passed = bool(r1["passed"] and r2["passed"] and r3["passed"])
    return {
        "plasma": r1, "water_waves": r2, "periodic_medium": r3,
        "validation_passed": validation_passed,
    }


DISPERSION_RELATION_TOOL_SCHEMA = {
    "name": "dispersion_relation_tool",
    "description": (
        "Relaciones de dispersion de ondas en distintos medios: plasma no "
        "magnetizado (EM o Langmuir/Bohm-Gross, mode='plasma'), ondas de "
        "gravedad-capilaridad en agua de profundidad finita con limites de "
        "aguas profundas/someras (mode='water_waves'), y estructura de "
        "bandas de un medio periodico 1D bilaminar via matriz de "
        "transferencia de Bloch, con apertura de gap por contraste de "
        "impedancia (mode='periodic_medium'). mode='validate' corre los 3 "
        "self-tests."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["plasma", "water_waves", "periodic_medium", "validate"]},
            "params": {
                "type": "object",
                "description": (
                    "Claves por modo (cualquier otra clave tira error). "
                    "plasma: wave_type ('electromagnetic'|'langmuir'), omega_p, "
                    "c, v_th, k_max, n_points. water_waves: g, rho, sigma, h "
                    "(SOLO estos 4; no existe wavelength_m, k se deriva de h). "
                    "periodic_medium: d1, d2, c1, c2, Z1, Z2, n_omega."
                ),
            },
        },
        "required": ["mode"],
    },
}


def compute_dispersion_relation(mode, params=None):
    params = params or {}
    if mode == "plasma":
        return plasma(params)
    elif mode == "water_waves":
        return water_waves(params)
    elif mode == "periodic_medium":
        return periodic_medium(params)
    elif mode == "validate":
        return validate(params)
    else:
        raise ValueError(f"modo desconocido: {mode}")


if __name__ == "__main__":
    d = compute_dispersion_relation("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo"
    print("\nOK dispersion_relation_tool.py")


def _handler(args):
    return compute_dispersion_relation(args.get("mode"), args.get("params"))


tool_registry.register_tool("dispersion_relation_tool", DISPERSION_RELATION_TOOL_SCHEMA, _handler)
