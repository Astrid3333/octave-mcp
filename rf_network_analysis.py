"""
rf_network_analysis.py

Funciones puras para extender openems_quantum_circuit_tool con 3 modos nuevos:
    - s_parameter_extraction
    - impedance_matching_analysis
    - touchstone_export

No dependen de openEMS ni de CSXCAD: trabajan sobre la impedancia
caracteristica Z0 (real o compleja, escalar o array vs frecuencia) que
ya devuelven los modos existentes cpw_impedance_analytic / cpw_resonator_fdtd.
Modelo: linea de transmision uniforme de longitud L, excitada y cargada
en la impedancia de referencia del sistema (tipicamente 50 ohm).

Convenciones:
    freq_hz      : float o array de floats, frecuencia en Hz
    Z0           : complex o array de complex, impedancia caracteristica de la linea
    Z_ref        : complex, impedancia de referencia del sistema (default 50+0j)
    eps_eff      : float, permitividad efectiva (para beta = 2*pi*f*sqrt(eps_eff)/c)
    length_m     : float, longitud fisica de la linea en metros
    alpha_np_per_m: float, atenuacion en Np/m (default 0 = sin perdidas)
"""

import numpy as np

C0 = 299792458.0  # m/s


def _gamma_reflection(Z0, Z_ref):
    """Coeficiente de reflexion mirando hacia la linea desde Z_ref."""
    Z0 = np.asarray(Z0, dtype=complex)
    return (Z0 - Z_ref) / (Z0 + Z_ref)


def _propagation_constant(freq_hz, eps_eff, alpha_np_per_m):
    freq_hz = np.asarray(freq_hz, dtype=float)
    beta = 2 * np.pi * freq_hz * np.sqrt(eps_eff) / C0
    return alpha_np_per_m + 1j * beta


# ---------------------------------------------------------------------
# Modo 1: s_parameter_extraction
# ---------------------------------------------------------------------
def compute_s_parameters(freq_hz, Z0, eps_eff, length_m,
                          Z_ref=50.0 + 0j, alpha_np_per_m=0.0):
    """
    S-parameters de una linea de transmision uniforme (2 puertos),
    formula estandar de linea con desadaptacion Gamma en ambos extremos
    (Pozar, Microwave Engineering, cap. 2).

    Devuelve dict con S11, S21, S12, S22 (arrays complejos, mismo shape
    que freq_hz) y las versiones en dB / grados para inspeccion directa.
    """
    freq_hz = np.atleast_1d(np.asarray(freq_hz, dtype=float))
    Z0_arr = np.broadcast_to(np.asarray(Z0, dtype=complex), freq_hz.shape).copy()

    gamma = _gamma_reflection(Z0_arr, Z_ref)
    g = _propagation_constant(freq_hz, eps_eff, alpha_np_per_m)
    e2gl = np.exp(-2 * g * length_m)

    denom = 1 - gamma**2 * e2gl
    S11 = gamma * (1 - e2gl) / denom
    S21 = (1 - gamma**2) * np.exp(-g * length_m) / denom
    S22 = S11.copy()          # linea simetrica
    S12 = S21.copy()          # reciproca

    def _mag_db(x):
        return 20 * np.log10(np.clip(np.abs(x), 1e-15, None))

    return {
        "freq_hz": freq_hz,
        "S11": S11, "S21": S21, "S12": S12, "S22": S22,
        "S11_dB": _mag_db(S11), "S21_dB": _mag_db(S21),
        "S21_phase_deg": np.angle(S21, deg=True),
        "S11_phase_deg": np.angle(S11, deg=True),
        "gamma_reflection": gamma,
    }


def _abcd_to_s(A, B, C, D, Z_ref):
    """Conversion ABCD -> S, usada solo para validacion cruzada interna."""
    denom = A + B / Z_ref + C * Z_ref + D
    S11 = (A + B / Z_ref - C * Z_ref - D) / denom
    S21 = 2.0 / denom
    S12 = 2.0 * (A * D - B * C) / denom
    S22 = (-A + B / Z_ref - C * Z_ref + D) / denom
    return S11, S21, S12, S22


# ---------------------------------------------------------------------
# Modo 2: impedance_matching_analysis
# ---------------------------------------------------------------------
def compute_impedance_matching(freq_hz, Z0, Z_ref=50.0 + 0j):
    """
    VSWR, return loss y perdida por desadaptacion a partir de Z0(f).
    Bandas de severidad = convencion estandar de ingenieria de RF.
    """
    freq_hz = np.atleast_1d(np.asarray(freq_hz, dtype=float))
    Z0_arr = np.broadcast_to(np.asarray(Z0, dtype=complex), freq_hz.shape).copy()

    gamma = _gamma_reflection(Z0_arr, Z_ref)
    gamma_mag = np.abs(gamma)
    gamma_mag_safe = np.clip(gamma_mag, 1e-12, 1 - 1e-12)

    vswr = (1 + gamma_mag) / np.clip(1 - gamma_mag, 1e-12, None)
    return_loss_db = -20 * np.log10(gamma_mag_safe)
    mismatch_loss_db = -10 * np.log10(np.clip(1 - gamma_mag**2, 1e-15, None))

    def _classify(v):
        if v <= 1.5:
            return "excelente"
        if v <= 2.0:
            return "bueno"
        if v <= 3.0:
            return "marginal"
        return "malo"

    severity = [_classify(v) for v in np.atleast_1d(vswr)]

    return {
        "freq_hz": freq_hz,
        "gamma_reflection": gamma,
        "gamma_mag": gamma_mag,
        "vswr": vswr,
        "return_loss_dB": return_loss_db,
        "mismatch_loss_dB": mismatch_loss_db,
        "severity": severity,
    }


# ---------------------------------------------------------------------
# Modo 3: touchstone_export
# ---------------------------------------------------------------------
def export_touchstone(freq_hz, S11, S21, S12, S22, Z_ref=50.0,
                       freq_unit="HZ", comment=""):
    """
    Genera contenido de un archivo Touchstone .s2p (formato RI = parte
    real/imaginaria), estandar de facto para intercambio de S-parameters
    entre herramientas de RF/microondas.
    """
    freq_hz = np.atleast_1d(np.asarray(freq_hz, dtype=float))
    lines = []
    if comment:
        for c in comment.strip().split("\n"):
            lines.append(f"! {c}")
    lines.append(f"# {freq_unit} S RI R {Z_ref:g}")
    for i, f in enumerate(freq_hz):
        row = [f"{f:.9g}"]
        for S in (S11, S21, S12, S22):
            s = np.atleast_1d(S)[i]
            row.append(f"{s.real:.9g}")
            row.append(f"{s.imag:.9g}")
        lines.append(" ".join(row))
    return "\n".join(lines) + "\n"


def parse_touchstone_s2p(text):
    """Parser minimo para validar el propio export (round-trip test)."""
    freqs, s11, s21, s12, s22 = [], [], [], [], []
    z_ref = None
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("!"):
            continue
        if line.startswith("#"):
            parts = line.split()
            z_ref = float(parts[parts.index("R") + 1])
            continue
        vals = [float(x) for x in line.split()]
        freqs.append(vals[0])
        s11.append(complex(vals[1], vals[2]))
        s21.append(complex(vals[3], vals[4]))
        s12.append(complex(vals[5], vals[6]))
        s22.append(complex(vals[7], vals[8]))
    return {
        "freq_hz": np.array(freqs), "Z_ref": z_ref,
        "S11": np.array(s11), "S21": np.array(s21),
        "S12": np.array(s12), "S22": np.array(s22),
    }


# ---------------------------------------------------------------------
# validate() - mismo patron que el resto del repo (self_test)
# ---------------------------------------------------------------------
def validate():
    results = []
    all_pass = True

    def check(name, cond):
        nonlocal all_pass
        results.append({"test": name, "passed": bool(cond)})
        all_pass = all_pass and bool(cond)

    freq = np.linspace(4e9, 8e9, 5)
    eps_eff = 6.45  # tipico CPW sobre silicio, sustrato semi-infinito ~(11.9+1)/2
    L = 0.006       # 6 mm

    # --- Caso 1: linea perfectamente adaptada, sin perdidas ---
    sp = compute_s_parameters(freq, Z0=50.0 + 0j, eps_eff=eps_eff,
                               length_m=L, Z_ref=50.0 + 0j, alpha_np_per_m=0.0)
    check("matched_S11_zero", np.allclose(sp["S11"], 0, atol=1e-12))
    check("matched_S21_unit_mag", np.allclose(np.abs(sp["S21"]), 1.0, atol=1e-9))

    # --- Caso 2: linea desadaptada, sin perdidas -> cruzar contra ABCD ---
    Z0_line = 65.0 + 0j
    g = _propagation_constant(freq, eps_eff, 0.0)
    A = np.cosh(g * L)
    B = Z0_line * np.sinh(g * L)
    Cc = np.sinh(g * L) / Z0_line
    D = np.cosh(g * L)
    S11_abcd, S21_abcd, S12_abcd, S22_abcd = _abcd_to_s(A, B, Cc, D, 50.0 + 0j)

    sp2 = compute_s_parameters(freq, Z0=Z0_line, eps_eff=eps_eff,
                                length_m=L, Z_ref=50.0 + 0j, alpha_np_per_m=0.0)
    check("S11_matches_ABCD_crosscheck", np.allclose(sp2["S11"], S11_abcd, atol=1e-9))
    check("S21_matches_ABCD_crosscheck", np.allclose(sp2["S21"], S21_abcd, atol=1e-9))
    check("S12_matches_ABCD_crosscheck", np.allclose(sp2["S12"], S12_abcd, atol=1e-9))
    check("S22_matches_ABCD_crosscheck", np.allclose(sp2["S22"], S22_abcd, atol=1e-9))
    check("lossless_reciprocal_S12_eq_S21", np.allclose(sp2["S12"], sp2["S21"]))
    # lossless 2-port pasivo: |S11|^2 + |S21|^2 = 1 (conservacion de energia)
    check("energy_conservation_lossless",
          np.allclose(np.abs(sp2["S11"])**2 + np.abs(sp2["S21"])**2, 1.0, atol=1e-9))

    # --- Caso 3: linea con perdidas -> ya no deberia conservar energia = 1 ---
    sp3 = compute_s_parameters(freq, Z0=Z0_line, eps_eff=eps_eff,
                                length_m=L, Z_ref=50.0 + 0j, alpha_np_per_m=5.0)
    check("lossy_energy_below_unity",
          bool(np.all(np.abs(sp3["S11"])**2 + np.abs(sp3["S21"])**2 < 1.0)))

    # --- impedance_matching_analysis: casos triviales ---
    im_matched = compute_impedance_matching(freq, Z0=50.0 + 0j, Z_ref=50.0 + 0j)
    check("matched_vswr_is_1", np.allclose(im_matched["vswr"], 1.0, atol=1e-6))
    check("matched_severity_excelente", all(s == "excelente" for s in im_matched["severity"]))

    im_open = compute_impedance_matching(freq, Z0=1e9 + 0j, Z_ref=50.0 + 0j)
    check("open_circuit_gamma_near_1", np.allclose(im_open["gamma_mag"], 1.0, atol=1e-6))
    check("open_circuit_severity_malo", all(s == "malo" for s in im_open["severity"]))

    # --- touchstone_export: round trip ---
    text = export_touchstone(freq, sp2["S11"], sp2["S21"], sp2["S12"], sp2["S22"],
                              Z_ref=50.0, comment="validate() round-trip test")
    parsed = parse_touchstone_s2p(text)
    check("touchstone_header_r50", parsed["Z_ref"] == 50.0)
    check("touchstone_freq_roundtrip", np.allclose(parsed["freq_hz"], freq, rtol=1e-6))
    check("touchstone_S11_roundtrip", np.allclose(parsed["S11"], sp2["S11"], atol=1e-6))
    check("touchstone_S21_roundtrip", np.allclose(parsed["S21"], sp2["S21"], atol=1e-6))

    return {
        "tests_passed": sum(r["passed"] for r in results),
        "tests_total": len(results),
        "results": results,
        "validation_passed": all_pass,
        "status": "PASSED" if all_pass else "FAILED",
    }


# ---------------------------------------------------------------------
# Dispatcher: para enchufar directo en el elif/switch de mode existente
# ---------------------------------------------------------------------
def run_mode(mode, params):
    """
    params esperado (todas las claves con default salvo freq_hz/Z0):
      freq_hz (float o list[float], requerido salvo en touchstone_export
               si ya se le pasan arrays de S-parameters hechos)
      Z0 (float/complex o list, requerido para s_parameter_extraction e
          impedance_matching_analysis) -- reusar el Z0 que ya devuelve
          cpw_impedance_analytic / cpw_resonator_fdtd
      eps_eff (float, requerido solo en s_parameter_extraction)
      length_m (float, requerido solo en s_parameter_extraction)
      Z_ref (float, default 50.0)
      alpha_np_per_m (float, default 0.0)
      comment (str, opcional, solo touchstone_export)
    """
    if mode == "s_parameter_extraction":
        return compute_s_parameters(
            freq_hz=params["freq_hz"], Z0=params["Z0"],
            eps_eff=params["eps_eff"], length_m=params["length_m"],
            Z_ref=params.get("Z_ref", 50.0 + 0j),
            alpha_np_per_m=params.get("alpha_np_per_m", 0.0),
        )
    elif mode == "impedance_matching_analysis":
        return compute_impedance_matching(
            freq_hz=params["freq_hz"], Z0=params["Z0"],
            Z_ref=params.get("Z_ref", 50.0 + 0j),
        )
    elif mode == "touchstone_export":
        content = export_touchstone(
            freq_hz=params["freq_hz"], S11=params["S11"], S21=params["S21"],
            S12=params["S12"], S22=params["S22"],
            Z_ref=params.get("Z_ref", 50.0), comment=params.get("comment", ""),
        )
        return {"touchstone_s2p": content}
    elif mode == "validate":
        return validate()
    else:
        raise ValueError(f"modo desconocido: {mode}")


if __name__ == "__main__":
    import json
    print(json.dumps(validate(), indent=2))


RF_NETWORK_ANALYSIS_TOOL_SCHEMA = {
    "name": "rf_network_analysis",
    "description": "Extraccion de parametros S, analisis de matching de impedancia y exportacion Touchstone (.s2p) para lineas de transmision RF (ej. resonadores CPW).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["s_parameter_extraction", "impedance_matching_analysis", "touchstone_export", "parse_touchstone_s2p", "validate"]
            },
            "params": {
                "type": "object",
                "description": "freq_hz, Z0, eps_eff, length_m, Z_ref, alpha_np_per_m, S11/S21/S12/S22, comment, text (segun mode)"
            }
        },
        "required": ["mode"]
    }
}

def compute_rf_network_analysis(args):
    mode = args.get("mode") if isinstance(args, dict) else args
    params = args.get("params") or {} if isinstance(args, dict) else {}
    if mode == "validate":
        return validate()
    if mode == "parse_touchstone_s2p":
        return parse_touchstone_s2p(params["text"])
    return run_mode(mode, params)

try:
    from tool_registry import register_tool
    register_tool("rf_network_analysis", RF_NETWORK_ANALYSIS_TOOL_SCHEMA, compute_rf_network_analysis)
except ImportError:
    pass
