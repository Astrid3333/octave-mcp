"""
rf_network_advanced_tool.py
Extension de rf_network_analysis.py (que cubre lineas de transmision:
s_parameter_extraction, impedance_matching_analysis, touchstone_export).

Esta tool cubre lo que NO cubre la original:
  - stability_factor: factor K de Rollett + Delta, y test-mu (Edwards-Sinsky)
    para amplificadores/redes activas de 2 puertos.
  - network_cascade: cascada de N redes de 2 puertos via matrices ABCD.
  - parameter_conversion: conversion completa entre S, Z, Y, ABCD (2 puertos).

Convencion de numeros complejos en JSON (no hay tipo nativo): todo
parametro complejo se pasa/devuelve como {"re": float, "im": float}.

Formulas estandar (Pozar, "Microwave Engineering"):
  S->ABCD, ABCD->S, S->Z, Z->S  (formulas cerradas clasicas)
  S->Y, Y->S se obtienen via Z como paso intermedio (Y = Z^-1), lo que
  garantiza consistencia algebraica exacta en el round-trip.

Validado contra:
  - round-trip S->ABCD->S, S->Z->S, S->Y->S (deben reproducir el S original)
  - cascada con un "thru" ideal (ABCD identidad) no debe alterar la red
  - cascada es asociativa: (A cascada B) cascada C == A cascada (B cascada C)
  - estabilidad: red pasiva simetrica y bien adaptada (S bajos, reciproca)
    debe dar K>1 y |Delta|<1 (incondicionalmente estable); red con ganancia
    fuerte y muy desadaptada (S21 grande, S11/S22 altos) debe dar K<1
    (potencialmente inestable) -- ambos casos construidos por aritmetica
    directa en el propio validate(), no por valores de libro memorizados.
"""
import numpy as np

TOOL_SCHEMA = {
    "name": "rf_network_advanced_tool",
    "description": (
        "Extension de rf_network_analysis: factor de estabilidad K/Delta y "
        "test-mu para amplificadores RF (stability_factor), cascada de "
        "redes de 2 puertos via ABCD (network_cascade), y conversion "
        "completa S<->Z<->Y<->ABCD (parameter_conversion). Numeros "
        "complejos se representan como {re, im}. Modos: stability_factor, "
        "network_cascade, parameter_conversion, validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["stability_factor", "network_cascade",
                         "parameter_conversion", "validate"],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


def _c(d):
    """dict {re, im} -> complex"""
    return complex(d["re"], d["im"])


def _d(z):
    """complex -> dict {re, im}"""
    return {"re": float(z.real), "im": float(z.imag)}


# ---------------------------------------------------------------------
# Conversiones de parametros (formulas cerradas, Pozar)
# ---------------------------------------------------------------------

def s_to_abcd(S11, S12, S21, S22, Z0=50.0):
    denom = 2 * S21
    A = ((1 + S11) * (1 - S22) + S12 * S21) / denom
    B = Z0 * ((1 + S11) * (1 + S22) - S12 * S21) / denom
    C = (1.0 / Z0) * ((1 - S11) * (1 - S22) - S12 * S21) / denom
    D = ((1 - S11) * (1 + S22) + S12 * S21) / denom
    return A, B, C, D


def abcd_to_s(A, B, C, D, Z0=50.0):
    denom = A + B / Z0 + C * Z0 + D
    S11 = (A + B / Z0 - C * Z0 - D) / denom
    S12 = 2 * (A * D - B * C) / denom
    S21 = 2 / denom
    S22 = (-A + B / Z0 - C * Z0 + D) / denom
    return S11, S12, S21, S22


def s_to_z(S11, S12, S21, S22, Z0=50.0):
    denom = (1 - S11) * (1 - S22) - S12 * S21
    Z11 = Z0 * ((1 + S11) * (1 - S22) + S12 * S21) / denom
    Z12 = Z0 * (2 * S12) / denom
    Z21 = Z0 * (2 * S21) / denom
    Z22 = Z0 * ((1 - S11) * (1 + S22) + S12 * S21) / denom
    return Z11, Z12, Z21, Z22


def z_to_s(Z11, Z12, Z21, Z22, Z0=50.0):
    denom = (Z11 + Z0) * (Z22 + Z0) - Z12 * Z21
    S11 = ((Z11 - Z0) * (Z22 + Z0) - Z12 * Z21) / denom
    S12 = 2 * Z12 * Z0 / denom
    S21 = 2 * Z21 * Z0 / denom
    S22 = ((Z11 + Z0) * (Z22 - Z0) - Z12 * Z21) / denom
    return S11, S12, S21, S22


def _z_matrix_to_y(Z11, Z12, Z21, Z22):
    detZ = Z11 * Z22 - Z12 * Z21
    Y11 = Z22 / detZ
    Y12 = -Z12 / detZ
    Y21 = -Z21 / detZ
    Y22 = Z11 / detZ
    return Y11, Y12, Y21, Y22


def _y_matrix_to_z(Y11, Y12, Y21, Y22):
    detY = Y11 * Y22 - Y12 * Y21
    Z11 = Y22 / detY
    Z12 = -Y12 / detY
    Z21 = -Y21 / detY
    Z22 = Y11 / detY
    return Z11, Z12, Z21, Z22


def s_to_y(S11, S12, S21, S22, Z0=50.0):
    Z11, Z12, Z21, Z22 = s_to_z(S11, S12, S21, S22, Z0)
    return _z_matrix_to_y(Z11, Z12, Z21, Z22)


def y_to_s(Y11, Y12, Y21, Y22, Z0=50.0):
    Z11, Z12, Z21, Z22 = _y_matrix_to_z(Y11, Y12, Y21, Y22)
    return z_to_s(Z11, Z12, Z21, Z22, Z0)


# ---------------------------------------------------------------------
# Cascada de redes (via ABCD)
# ---------------------------------------------------------------------

def _abcd_matrix(A, B, C, D):
    return np.array([[A, B], [C, D]], dtype=complex)


def cascade_abcd_list(abcd_list):
    M = np.eye(2, dtype=complex)
    for (A, B, C, D) in abcd_list:
        M = M @ _abcd_matrix(A, B, C, D)
    return M[0, 0], M[0, 1], M[1, 0], M[1, 1]


def network_cascade(networks, Z0=50.0):
    """networks: lista de dicts {S11,S12,S21,S22} (cada uno {re,im})."""
    abcd_list = []
    for net in networks:
        S11 = _c(net["S11"]); S12 = _c(net["S12"])
        S21 = _c(net["S21"]); S22 = _c(net["S22"])
        abcd_list.append(s_to_abcd(S11, S12, S21, S22, Z0))
    A, B, C, D = cascade_abcd_list(abcd_list)
    S11, S12, S21, S22 = abcd_to_s(A, B, C, D, Z0)
    return {
        "mode": "network_cascade",
        "n_networks": len(networks),
        "S11": _d(S11), "S12": _d(S12), "S21": _d(S21), "S22": _d(S22),
        "ABCD": {"A": _d(A), "B": _d(B), "C": _d(C), "D": _d(D)},
    }


# ---------------------------------------------------------------------
# Estabilidad (Rollett K/Delta, y test-mu de Edwards-Sinsky)
# ---------------------------------------------------------------------

def stability_factor(S11, S12, S21, S22):
    S11c = _c(S11); S12c = _c(S12); S21c = _c(S21); S22c = _c(S22)
    Delta = S11c * S22c - S12c * S21c
    denom_K = 2 * abs(S12c * S21c)
    K = ((1 - abs(S11c) ** 2 - abs(S22c) ** 2 + abs(Delta) ** 2) / denom_K
         if denom_K > 0 else float("inf"))
    unconditionally_stable_K_delta = bool(K > 1 and abs(Delta) < 1)

    mu_denom = abs(S22c - Delta * np.conj(S11c)) + abs(S12c * S21c)
    mu = (1 - abs(S11c) ** 2) / mu_denom if mu_denom > 0 else float("inf")
    unconditionally_stable_mu = bool(mu > 1)

    return {
        "mode": "stability_factor",
        "K": float(K) if np.isfinite(K) else None,
        "Delta": _d(Delta),
        "Delta_mag": float(abs(Delta)),
        "mu": float(mu) if np.isfinite(mu) else None,
        "unconditionally_stable_K_delta_test": unconditionally_stable_K_delta,
        "unconditionally_stable_mu_test": unconditionally_stable_mu,
    }


# ---------------------------------------------------------------------
# Conversion generica de parametros
# ---------------------------------------------------------------------

def parameter_conversion(direction, Z0=50.0, **params):
    if direction == "s_to_abcd":
        A, B, C, D = s_to_abcd(_c(params["S11"]), _c(params["S12"]),
                                _c(params["S21"]), _c(params["S22"]), Z0)
        return {"A": _d(A), "B": _d(B), "C": _d(C), "D": _d(D)}
    elif direction == "abcd_to_s":
        S11, S12, S21, S22 = abcd_to_s(_c(params["A"]), _c(params["B"]),
                                        _c(params["C"]), _c(params["D"]), Z0)
        return {"S11": _d(S11), "S12": _d(S12), "S21": _d(S21), "S22": _d(S22)}
    elif direction == "s_to_z":
        Z11, Z12, Z21, Z22 = s_to_z(_c(params["S11"]), _c(params["S12"]),
                                     _c(params["S21"]), _c(params["S22"]), Z0)
        return {"Z11": _d(Z11), "Z12": _d(Z12), "Z21": _d(Z21), "Z22": _d(Z22)}
    elif direction == "z_to_s":
        S11, S12, S21, S22 = z_to_s(_c(params["Z11"]), _c(params["Z12"]),
                                     _c(params["Z21"]), _c(params["Z22"]), Z0)
        return {"S11": _d(S11), "S12": _d(S12), "S21": _d(S21), "S22": _d(S22)}
    elif direction == "s_to_y":
        Y11, Y12, Y21, Y22 = s_to_y(_c(params["S11"]), _c(params["S12"]),
                                     _c(params["S21"]), _c(params["S22"]), Z0)
        return {"Y11": _d(Y11), "Y12": _d(Y12), "Y21": _d(Y21), "Y22": _d(Y22)}
    elif direction == "y_to_s":
        S11, S12, S21, S22 = y_to_s(_c(params["Y11"]), _c(params["Y12"]),
                                     _c(params["Y21"]), _c(params["Y22"]), Z0)
        return {"S11": _d(S11), "S12": _d(S12), "S21": _d(S21), "S22": _d(S22)}
    else:
        raise ValueError(
            f"direccion desconocida: {direction}. Usar: s_to_abcd | abcd_to_s | "
            "s_to_z | z_to_s | s_to_y | y_to_s"
        )


# ---------------------------------------------------------------------
# validate()
# ---------------------------------------------------------------------

def _validate_rf_advanced():
    checks = []
    Z0 = 50.0

    # Red de prueba generica (no trivial, valores arbitrarios razonables
    # para un 2-puerto pasivo tipico)
    S11 = 0.15 - 0.05j
    S12 = 0.08 + 0.02j
    S21 = 0.85 + 0.10j
    S22 = 0.20 - 0.08j

    # 1) round-trip S -> ABCD -> S
    A, B, C, D = s_to_abcd(S11, S12, S21, S22, Z0)
    S11r, S12r, S21r, S22r = abcd_to_s(A, B, C, D, Z0)
    ok1 = (abs(S11r - S11) < 1e-9 and abs(S12r - S12) < 1e-9
           and abs(S21r - S21) < 1e-9 and abs(S22r - S22) < 1e-9)
    checks.append({"name": "roundtrip_S_ABCD_S", "expected": True, "got": bool(ok1), "passed": bool(ok1)})

    # 2) round-trip S -> Z -> S
    Z11, Z12, Z21, Z22 = s_to_z(S11, S12, S21, S22, Z0)
    S11z, S12z, S21z, S22z = z_to_s(Z11, Z12, Z21, Z22, Z0)
    ok2 = (abs(S11z - S11) < 1e-9 and abs(S12z - S12) < 1e-9
           and abs(S21z - S21) < 1e-9 and abs(S22z - S22) < 1e-9)
    checks.append({"name": "roundtrip_S_Z_S", "expected": True, "got": bool(ok2), "passed": bool(ok2)})

    # 3) round-trip S -> Y -> S
    Y11, Y12, Y21, Y22 = s_to_y(S11, S12, S21, S22, Z0)
    S11y, S12y, S21y, S22y = y_to_s(Y11, Y12, Y21, Y22, Z0)
    ok3 = (abs(S11y - S11) < 1e-9 and abs(S12y - S12) < 1e-9
           and abs(S21y - S21) < 1e-9 and abs(S22y - S22) < 1e-9)
    checks.append({"name": "roundtrip_S_Y_S", "expected": True, "got": bool(ok3), "passed": bool(ok3)})

    # 4) cascada con "thru" ideal (ABCD identidad: A=1,B=0,C=0,D=1) no altera la red
    thru = (1.0 + 0j, 0.0 + 0j, 0.0 + 0j, 1.0 + 0j)
    net = {"S11": _d(S11), "S12": _d(S12), "S21": _d(S21), "S22": _d(S22)}
    A2, B2, C2, D2 = cascade_abcd_list([s_to_abcd(S11, S12, S21, S22, Z0), thru])
    S11c, S12c2, S21c2, S22c2 = abcd_to_s(A2, B2, C2, D2, Z0)
    ok4 = (abs(S11c - S11) < 1e-9 and abs(S21c2 - S21) < 1e-9)
    checks.append({"name": "cascade_with_ideal_thru_unchanged", "expected": True, "got": bool(ok4), "passed": bool(ok4)})

    # 5) cascada asociativa: (A cascada B) cascada C == A cascada (B cascada C)
    netB_S = (0.05 + 0.01j, 0.02 - 0.01j, 0.9 - 0.05j, 0.04 + 0.02j)
    netC_S = (0.03 - 0.02j, 0.01 + 0.005j, 0.92 + 0.02j, 0.06 - 0.03j)
    abcdA = s_to_abcd(S11, S12, S21, S22, Z0)
    abcdB = s_to_abcd(*netB_S, Z0)
    abcdC = s_to_abcd(*netC_S, Z0)
    left = cascade_abcd_list([cascade_abcd_list([abcdA, abcdB]), abcdC]) if False else None
    # cascade_abcd_list espera una lista de tuplas ABCD; para "(A cascada B) cascada C"
    # armamos manualmente respetando la interfaz de matrices 2x2
    MA = _abcd_matrix(*abcdA); MB = _abcd_matrix(*abcdB); MC = _abcd_matrix(*abcdC)
    M_left = (MA @ MB) @ MC
    M_right = MA @ (MB @ MC)
    ok5 = np.allclose(M_left, M_right, atol=1e-9)
    checks.append({"name": "cascade_associative", "expected": True, "got": bool(ok5), "passed": bool(ok5)})

    # 6) estabilidad: red pasiva bien adaptada y simetrica -> K>1, |Delta|<1
    Sd_stable = {"S11": _d(0.1 + 0j), "S12": _d(0.1 + 0j),
                 "S21": _d(0.1 + 0j), "S22": _d(0.1 + 0j)}
    r_stable = stability_factor(**Sd_stable)
    ok6 = (r_stable["K"] is not None and r_stable["K"] > 1
           and r_stable["Delta_mag"] < 1
           and r_stable["unconditionally_stable_K_delta_test"])
    checks.append({"name": "stable_passive_matched_network_K_gt_1",
                    "expected": "K>1 y |Delta|<1", "got": r_stable["K"], "passed": bool(ok6)})

    # 7) estabilidad: ganancia fuerte + fuerte desadaptacion -> K<1 (inestable)
    #    construido por aritmetica directa: S11=S22=0.9, S12=0.01, S21=5 (real, fase 0)
    #    Delta = 0.81 - 0.05 = 0.76; K = (1-0.81-0.81+0.76^2)/(2*0.01*5) = -0.424 < 1
    Sd_unstable = {"S11": _d(0.9 + 0j), "S12": _d(0.01 + 0j),
                   "S21": _d(5.0 + 0j), "S22": _d(0.9 + 0j)}
    r_unstable = stability_factor(**Sd_unstable)
    ok7 = (r_unstable["K"] is not None and r_unstable["K"] < 1)
    checks.append({"name": "high_gain_mismatched_network_K_lt_1",
                    "expected": "K<1", "got": r_unstable["K"], "passed": bool(ok7)})

    all_passed = all(ch["passed"] for ch in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed,
            "n_checks": len(checks), "n_passed": sum(1 for ch in checks if ch["passed"])}


def compute_rf_network_advanced(mode, **params):
    if mode == "validate":
        return _validate_rf_advanced()
    elif mode == "stability_factor":
        return stability_factor(params["S11"], params["S12"], params["S21"], params["S22"])
    elif mode == "network_cascade":
        return network_cascade(params["networks"], Z0=params.get("Z0", 50.0))
    elif mode == "parameter_conversion":
        direction = params["direction"]
        p = {k: v for k, v in params.items() if k not in ("direction", "Z0")}
        return parameter_conversion(direction, Z0=params.get("Z0", 50.0), **p)
    else:
        raise ValueError(
            f"modo desconocido: {mode}. Usar: stability_factor | network_cascade | "
            "parameter_conversion | validate"
        )


if __name__ == "__main__":
    r = _validate_rf_advanced()
    for ch in r["checks"]:
        print(("PASS" if ch["passed"] else "FAIL"), ch["name"], ch["expected"], ch["got"])
    print(f"{r['n_passed']}/{r['n_checks']} checks passed")


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass


def _handle(args):
    _params = args.get("params") or {}
    return compute_rf_network_advanced(mode=args["mode"], **_params)


def _register():
    register_tool("rf_network_advanced_tool", TOOL_SCHEMA, _handle)


_register()
