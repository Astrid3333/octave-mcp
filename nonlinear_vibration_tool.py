"""
nonlinear_vibration_tool.py
Vibraciones no lineales: oscilador de Duffing (rigidez cubica) via
metodo de balance armonico de primer orden (1-term Harmonic Balance).

Cubre un hueco que NO cubren forced_vibration_tool (lineal) ni
structural_analysis_advanced_tool.vibration_modes (eigenvalues lineales):
fenomenos de endurecimiento/ablandamiento, curva backbone, y salto
(jump phenomena) por multivaluacion de la amplitud en resonancia.

Ecuacion de movimiento (SDOF, Duffing forzado armonicamente):
    m*x'' + c*x' + k*x + k3*x^3 = F*cos(w*t)

Balance armonico de 1er orden: se asume x(t) = X*cos(w*t - phi) y se
retiene solo el armonico fundamental del termino cubico x^3 (coeficiente
3/4). Esto da la ecuacion de amplitud:

    X^2 * [ (k + (3/4)*k3*X^2 - m*w^2)^2 + (c*w)^2 ] = F^2

que es un polinomio cubico en Y = X^2:
    A*Y^3 + B*Y^2 + C*Y - F^2 = 0
    A = (9/16)*k3^2
    B = (3/2)*k3*(k - m*w^2)
    C = (k - m*w^2)^2 + (c*w)^2

Se resuelve con np.roots y se filtran las raices reales positivas.
Para F suficientemente grande y k3 != 0, pueden existir hasta 3 raices
reales por frecuencia -> multivaluacion -> fenomeno de salto.

Validado contra:
  - limite lineal (k3=0): la solucion HB debe coincidir exactamente con
    la respuesta forzada SDOF lineal clasica X = F/sqrt((k-m*w^2)^2+(c*w)^2)
  - backbone no amortiguada: w(X)^2 = (k + (3/4)*k3*X^2)/m
"""
import numpy as np

TOOL_SCHEMA = {
    "name": "nonlinear_vibration_tool",
    "description": (
        "Vibraciones no lineales: oscilador de Duffing (rigidez cubica) via "
        "balance armonico de 1er orden. Modos: duffing_frequency_response "
        "(barrido en frecuencia, hasta 3 ramas de amplitud por salto), "
        "backbone_curve (frecuencia natural no amortiguada vs amplitud), "
        "validate. Cubre endurecimiento/ablandamiento y fenomeno de salto, "
        "no cubierto por forced_vibration_tool (lineal) ni vibration_modes "
        "(eigenvalues lineales)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["duffing_frequency_response", "backbone_curve", "validate"],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


def _linear_response(m, c, k, w, F):
    denom = np.sqrt((k - m * w**2) ** 2 + (c * w) ** 2)
    return F / denom if denom > 0 else float("inf")


def _amplitude_roots(m, c, k, k3, w, F):
    """Raices reales positivas de X para una frecuencia w dada (balance armonico 1er orden)."""
    A = (9.0 / 16.0) * k3**2
    B = 1.5 * k3 * (k - m * w**2)
    C = (k - m * w**2) ** 2 + (c * w) ** 2
    D = -(F**2)

    if abs(A) < 1e-30:
        # k3 ~ 0: caso lineal, cuadratica en Y (en realidad C*Y = F^2)
        if abs(C) < 1e-30:
            return []
        Y = (F**2) / C
        if Y < 0:
            return []
        return [float(np.sqrt(Y))]

    coeffs = [A, B, C, D]
    roots = np.roots(coeffs)
    Xs = []
    for r in roots:
        if abs(r.imag) < 1e-6 * max(1.0, abs(r.real)) and r.real > 1e-12:
            Xs.append(float(np.sqrt(r.real)))
    return sorted(Xs)


def duffing_frequency_response(m=1.0, c=0.1, k=1.0, k3=0.0, F=1.0,
                                w_min=0.1, w_max=3.0, n_points=200):
    ws = np.linspace(w_min, w_max, n_points)
    branches = []  # lista de (w, X) para cada raiz encontrada
    max_n_roots = 1
    for w in ws:
        Xs = _amplitude_roots(m, c, k, k3, w, F)
        max_n_roots = max(max_n_roots, len(Xs))
        for X in Xs:
            branches.append({"w": float(w), "X": float(X)})

    w0 = np.sqrt(k / m)
    # pico de la rama principal (mayor amplitud por frecuencia)
    peak_w, peak_X = None, -1.0
    for pt in branches:
        if pt["X"] > peak_X:
            peak_X, peak_w = pt["X"], pt["w"]

    multivalued = max_n_roots >= 3
    hardening = k3 > 0
    softening = k3 < 0

    return {
        "mode": "duffing_frequency_response",
        "natural_frequency_linear": float(w0),
        "response_curve": branches,
        "peak_amplitude": float(peak_X) if peak_X >= 0 else None,
        "peak_frequency": float(peak_w) if peak_w is not None else None,
        "max_branches_at_single_frequency": int(max_n_roots),
        "jump_phenomenon_detected": bool(multivalued),
        "regime": "hardening" if hardening else ("softening" if softening else "linear"),
    }


def backbone_curve(m=1.0, k=1.0, k3=0.0, X_max=2.0, n_points=100):
    """Curva backbone no amortiguada: w(X) para vibracion libre no lineal."""
    Xs = np.linspace(0.0, X_max, n_points)
    ws = np.sqrt(np.maximum(k + 0.75 * k3 * Xs**2, 0.0) / m)
    w0 = float(np.sqrt(k / m))
    return {
        "mode": "backbone_curve",
        "natural_frequency_linear": w0,
        "amplitudes": Xs.tolist(),
        "frequencies": ws.tolist(),
        "regime": "hardening" if k3 > 0 else ("softening" if k3 < 0 else "linear"),
    }


def _validate_nonlinear_vibration():
    checks = []

    # 1) Limite lineal: k3=0 debe coincidir exactamente con la solucion SDOF clasica
    m, c, k, F = 1.0, 0.1, 1.0, 0.5
    w_test = 0.8
    Xs = _amplitude_roots(m, c, k, 0.0, w_test, F)
    X_hb = Xs[0] if Xs else None
    X_exact = _linear_response(m, c, k, w_test, F)
    checks.append({
        "name": "linear_limit_matches_classic_SDOF",
        "expected": round(X_exact, 6),
        "got": round(X_hb, 6) if X_hb is not None else None,
        "passed": bool(X_hb is not None and abs(X_hb - X_exact) < 1e-4),
    })

    # 2) Endurecimiento: pico se desplaza a frecuencia MAYOR que w0 = sqrt(k/m)
    r_hard = duffing_frequency_response(m=1.0, c=0.05, k=1.0, k3=0.5, F=0.3,
                                         w_min=0.5, w_max=2.5, n_points=300)
    w0 = r_hard["natural_frequency_linear"]
    checks.append({
        "name": "hardening_shifts_peak_above_w0",
        "expected": f"> {w0}",
        "got": r_hard["peak_frequency"],
        "passed": bool(r_hard["peak_frequency"] is not None and r_hard["peak_frequency"] > w0),
    })

    # 3) Ablandamiento: pico se desplaza a frecuencia MENOR que w0
    r_soft = duffing_frequency_response(m=1.0, c=0.05, k=1.0, k3=-0.15, F=0.15,
                                         w_min=0.3, w_max=1.5, n_points=300)
    checks.append({
        "name": "softening_shifts_peak_below_w0",
        "expected": f"< {w0}",
        "got": r_soft["peak_frequency"],
        "passed": bool(r_soft["peak_frequency"] is not None and r_soft["peak_frequency"] < w0),
    })

    # 4) Fenomeno de salto: con k3 y F suficientemente grandes debe haber
    #    multivaluacion (hasta 3 ramas reales en alguna frecuencia)
    r_jump = duffing_frequency_response(m=1.0, c=0.05, k=1.0, k3=1.0, F=0.4,
                                         w_min=0.5, w_max=2.5, n_points=400)
    checks.append({
        "name": "jump_phenomenon_multivalued_for_strong_drive",
        "expected": ">= 3 ramas en alguna frecuencia",
        "got": r_jump["max_branches_at_single_frequency"],
        "passed": bool(r_jump["jump_phenomenon_detected"]),
    })

    # 5) Backbone: para k3>0 la frecuencia debe crecer monotonamente con la amplitud
    bb = backbone_curve(m=1.0, k=1.0, k3=0.5, X_max=2.0, n_points=50)
    freqs = np.array(bb["frequencies"])
    checks.append({
        "name": "backbone_hardening_frequency_monotone_increasing",
        "expected": True,
        "got": bool(np.all(np.diff(freqs) >= -1e-12)),
        "passed": bool(np.all(np.diff(freqs) >= -1e-12)),
    })

    all_passed = all(ch["passed"] for ch in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed,
            "n_checks": len(checks), "n_passed": sum(1 for ch in checks if ch["passed"])}


def compute_nonlinear_vibration(mode, **params):
    if mode == "validate":
        return _validate_nonlinear_vibration()
    elif mode == "duffing_frequency_response":
        return duffing_frequency_response(**params)
    elif mode == "backbone_curve":
        return backbone_curve(**params)
    else:
        raise ValueError(
            f"modo desconocido: {mode}. Usar: duffing_frequency_response | "
            "backbone_curve | validate"
        )


if __name__ == "__main__":
    r = _validate_nonlinear_vibration()
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
    return compute_nonlinear_vibration(mode=args["mode"], **_params)


def _register():
    register_tool("nonlinear_vibration_tool", TOOL_SCHEMA, _handle)


_register()
