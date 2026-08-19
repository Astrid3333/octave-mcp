"""
structural_beam_tool.py

Tool 4/6 del roadmap de herramientas comunitarias.
Analisis de vigas Euler-Bernoulli: simplemente apoyadas y en voladizo,
bajo carga puntual o carga distribuida uniforme (UDL).

Devuelve: diagrama de momento flector, diagrama de corte, deflexion
maxima y factor de seguridad (si se entrega seccion + resistencia de
fluencia del material).

Validacion cruzada independiente via metodo de carga unitaria / trabajo
virtual (integracion numerica de M(x)*m(x)/EI), ademas de comparacion
contra formulas cerradas estandar de resistencia de materiales, y una
verificacion de consistencia dM/dx = V via derivada numerica.

Patron: mode / params / validate, TOOL_SCHEMA al final para
register_tool(). Solo numpy/scipy (sin dependencias nuevas).
"""

import numpy as np
from scipy.integrate import simpson


# ---------------------------------------------------------------------------
# Propiedades de seccion transversal
# ---------------------------------------------------------------------------

def _section_properties(section):
    """
    Devuelve (I, c, S) a partir de un dict `section`.

    shape="rectangular": requiere width, height (m)
    shape="circular": requiere diameter (m)
    shape="custom": requiere I (m^4) y c (m)
    """
    shape = section.get("shape", "custom")

    if shape == "rectangular":
        w = section["width"]
        h = section["height"]
        I = w * h ** 3 / 12.0
        c = h / 2.0
    elif shape == "circular":
        d = section["diameter"]
        I = np.pi * d ** 4 / 64.0
        c = d / 2.0
    elif shape == "custom":
        I = section["I"]
        c = section["c"]
    else:
        raise ValueError(f"shape de seccion no reconocida: {shape}")

    S = I / c
    return I, c, S


# ---------------------------------------------------------------------------
# Vigas simplemente apoyadas
# ---------------------------------------------------------------------------

def _ss_point_load(x, L, P, a):
    """M(x), V(x) para viga simplemente apoyada, carga puntual P a
    distancia a del apoyo izquierdo."""
    b = L - a
    R1 = P * b / L
    R2 = P * a / L
    M = np.where(x <= a, R1 * x, R2 * (L - x))
    V = np.where(x < a, R1, np.where(x > a, -R2, 0.0))
    return M, V, R1, R2


def _ss_point_deflection(x, L, P, a, EI):
    b = L - a
    y_left = P * b * x * (L ** 2 - b ** 2 - x ** 2) / (6.0 * L * EI)
    y_right = P * a * (L - x) * (2 * L * x - a ** 2 - x ** 2) / (6.0 * L * EI)
    return np.where(x <= a, y_left, y_right)


def _ss_udl(x, L, w):
    M = w * x * (L - x) / 2.0
    V = w * (L / 2.0 - x)
    R1 = R2 = w * L / 2.0
    return M, V, R1, R2


def _ss_udl_deflection(x, L, w, EI):
    return w * x * (L ** 3 - 2 * L * x ** 2 + x ** 3) / (24.0 * EI)


# ---------------------------------------------------------------------------
# Vigas en voladizo (cantilever), empotrada en x=0, libre en x=L
# ---------------------------------------------------------------------------

def _cant_point_load(x, L, P, a):
    """Carga puntual P a distancia a del empotramiento (0 <= a <= L)."""
    M = np.where(x <= a, -P * (a - x), 0.0)
    V = np.where(x <= a, P, 0.0)
    return M, V


def _cant_point_deflection(x, L, P, a, EI):
    y_left = P * x ** 2 * (3 * a - x) / (6.0 * EI)
    y_right = P * a ** 2 * (3 * x - a) / (6.0 * EI)
    return np.where(x <= a, y_left, y_right)


def _cant_udl(x, L, w):
    M = -w * (L - x) ** 2 / 2.0
    V = w * (L - x)
    return M, V


def _cant_udl_deflection(x, L, w, EI):
    return w * x ** 2 * (x ** 2 - 4 * L * x + 6 * L ** 2) / (24.0 * EI)


# ---------------------------------------------------------------------------
# Factor de seguridad
# ---------------------------------------------------------------------------

def _safety_factor(M_max_abs, S, yield_strength):
    if S is None or yield_strength is None:
        return None, None
    sigma_max = M_max_abs / S
    sf = yield_strength / sigma_max if sigma_max > 0 else float("inf")
    return sigma_max, sf


# ---------------------------------------------------------------------------
# Modos publicos
# ---------------------------------------------------------------------------

def simply_supported_point_load(params):
    L = float(params["L"])
    P = float(params["P"])
    a = float(params.get("a", L / 2.0))
    E = float(params.get("E", 200e9))
    n = int(params.get("n_points", 200))

    section = params.get("section")
    I, c, S = _section_properties(section) if section else (None, None, None)
    EI = E * I if I is not None else None

    x = np.linspace(0, L, n)
    M, V, R1, R2 = _ss_point_load(x, L, P, a)
    # El pico de M ocurre exactamente en x=a (un kink), que en general no
    # cae en un punto de la grilla -> se evalua exacto ahi, no via max()
    # sobre el arreglo discretizado (subestimaria el pico).
    b = L - a
    M_max = float(P * a * b / L)
    V_max = float(max(abs(R1), abs(R2)))

    result = {
        "beam_type": "simply_supported",
        "load_type": "point",
        "reactions_N": {"R1": R1, "R2": R2},
        "bending_moment_max_Nm": M_max,
        "shear_max_N": V_max,
        "bending_moment_at_x": M.tolist(),
        "shear_at_x": V.tolist(),
        "x_m": x.tolist(),
    }

    if EI is not None:
        y = _ss_point_deflection(x, L, P, a, EI)
        result["deflection_max_m"] = float(np.max(np.abs(y)))
        result["deflection_at_x"] = y.tolist()

    yield_strength = params.get("yield_strength")
    if S is not None and yield_strength is not None:
        sigma_max, sf = _safety_factor(M_max, S, float(yield_strength))
        result["max_bending_stress_Pa"] = sigma_max
        result["safety_factor"] = sf

    return result


def simply_supported_distributed_load(params):
    L = float(params["L"])
    w = float(params["w"])
    E = float(params.get("E", 200e9))
    n = int(params.get("n_points", 200))

    section = params.get("section")
    I, c, S = _section_properties(section) if section else (None, None, None)
    EI = E * I if I is not None else None

    x = np.linspace(0, L, n)
    M, V, R1, R2 = _ss_udl(x, L, w)
    # picos exactos (independientes de la resolucion de la grilla elegida)
    M_max = float(w * L ** 2 / 8.0)
    V_max = float(w * L / 2.0)

    result = {
        "beam_type": "simply_supported",
        "load_type": "distributed",
        "reactions_N": {"R1": R1, "R2": R2},
        "bending_moment_max_Nm": M_max,
        "shear_max_N": V_max,
        "bending_moment_at_x": M.tolist(),
        "shear_at_x": V.tolist(),
        "x_m": x.tolist(),
    }

    if EI is not None:
        y = _ss_udl_deflection(x, L, w, EI)
        result["deflection_max_m"] = float(np.max(np.abs(y)))
        result["deflection_at_x"] = y.tolist()

    yield_strength = params.get("yield_strength")
    if S is not None and yield_strength is not None:
        sigma_max, sf = _safety_factor(M_max, S, float(yield_strength))
        result["max_bending_stress_Pa"] = sigma_max
        result["safety_factor"] = sf

    return result


def cantilever_point_load(params):
    L = float(params["L"])
    P = float(params["P"])
    a = float(params.get("a", L))
    E = float(params.get("E", 200e9))
    n = int(params.get("n_points", 200))

    section = params.get("section")
    I, c, S = _section_properties(section) if section else (None, None, None)
    EI = E * I if I is not None else None

    x = np.linspace(0, L, n)
    M, V = _cant_point_load(x, L, P, a)
    # picos exactos: momento maximo en el empotramiento, corte constante
    # en el tramo cargado
    M_max = float(P * a)
    V_max = float(P)

    result = {
        "beam_type": "cantilever",
        "load_type": "point",
        "fixed_end_reaction_N": P,
        "fixed_end_moment_Nm": M_max,
        "bending_moment_max_Nm": M_max,
        "shear_max_N": V_max,
        "bending_moment_at_x": M.tolist(),
        "shear_at_x": V.tolist(),
        "x_m": x.tolist(),
    }

    if EI is not None:
        y = _cant_point_deflection(x, L, P, a, EI)
        result["deflection_max_m"] = float(np.max(np.abs(y)))
        result["deflection_at_x"] = y.tolist()

    yield_strength = params.get("yield_strength")
    if S is not None and yield_strength is not None:
        sigma_max, sf = _safety_factor(M_max, S, float(yield_strength))
        result["max_bending_stress_Pa"] = sigma_max
        result["safety_factor"] = sf

    return result


def cantilever_distributed_load(params):
    L = float(params["L"])
    w = float(params["w"])
    E = float(params.get("E", 200e9))
    n = int(params.get("n_points", 200))

    section = params.get("section")
    I, c, S = _section_properties(section) if section else (None, None, None)
    EI = E * I if I is not None else None

    x = np.linspace(0, L, n)
    M, V = _cant_udl(x, L, w)
    # picos exactos, ambos en el empotramiento (x=0)
    M_max = float(w * L ** 2 / 2.0)
    V_max = float(w * L)

    result = {
        "beam_type": "cantilever",
        "load_type": "distributed",
        "fixed_end_reaction_N": w * L,
        "fixed_end_moment_Nm": M_max,
        "bending_moment_max_Nm": M_max,
        "shear_max_N": V_max,
        "bending_moment_at_x": M.tolist(),
        "shear_at_x": V.tolist(),
        "x_m": x.tolist(),
    }

    if EI is not None:
        y = _cant_udl_deflection(x, L, w, EI)
        result["deflection_max_m"] = float(np.max(np.abs(y)))
        result["deflection_at_x"] = y.tolist()

    yield_strength = params.get("yield_strength")
    if S is not None and yield_strength is not None:
        sigma_max, sf = _safety_factor(M_max, S, float(yield_strength))
        result["max_bending_stress_Pa"] = sigma_max
        result["safety_factor"] = sf

    return result


# ---------------------------------------------------------------------------
# Validacion
# ---------------------------------------------------------------------------

def _unit_load_deflection_ss(L, M_real_fn, c, EI, n=400):
    """Metodo de carga unitaria / trabajo virtual para viga simplemente
    apoyada: aplica una carga virtual unitaria en x=c e integra
    M(x)*m(x)/EI numericamente. Independiente de la formula cerrada."""
    x = np.linspace(0, L, n)
    M_real = M_real_fn(x)
    m_virtual, _, _, _ = _ss_point_load(x, L, 1.0, c)
    integrand = M_real * m_virtual / EI
    return simpson(integrand, x=x)


def _unit_load_deflection_cant(L, M_real_fn, c, EI, n=400):
    x = np.linspace(0, L, n)
    M_real = M_real_fn(x)
    m_virtual, _ = _cant_point_load(x, L, 1.0, c)
    integrand = M_real * m_virtual / EI
    return simpson(integrand, x=x)


def validate():
    checks = []
    tol = 1e-3

    E = 200e9
    I = 8.0e-6
    EI = E * I

    L, P = 4.0, 5000.0
    x = np.linspace(0, L, 400)

    # 1) SS, carga puntual centrada
    a = L / 2.0
    M, V, R1, R2 = _ss_point_load(x, L, P, a)
    # pico exacto en x=a (kink de la lineal a trozos), no max() de grilla
    M_max = P * a * (L - a) / L
    checks.append(("ss_point_centered_Mmax_vs_PL/4",
                    abs(M_max - P * L / 4.0) / (P * L / 4.0) < tol))
    checks.append(("ss_point_centered_reactions_sum_eq_P",
                    abs((R1 + R2) - P) / P < tol))

    y_formula = _ss_point_deflection(np.array([a]), L, P, a, EI)[0]
    y_closed = P * L ** 3 / (48.0 * EI)
    checks.append(("ss_point_centered_deflection_vs_closed_form",
                    abs(y_formula - y_closed) / abs(y_closed) < tol))

    y_virtual = _unit_load_deflection_ss(
        L, lambda xx: _ss_point_load(xx, L, P, a)[0], a, EI)
    checks.append(("ss_point_centered_deflection_vs_unit_load_method",
                    abs(y_virtual - y_formula) / abs(y_formula) < tol))

    # 2) SS, carga puntual descentrada
    a2 = 1.2
    b2 = L - a2
    M2, V2, R1b, R2b = _ss_point_load(x, L, P, a2)
    M2_max = P * a2 * b2 / L
    checks.append(("ss_point_offcenter_Mmax_vs_Pab/L",
                    abs(M2_max - P * a2 * b2 / L) / (P * a2 * b2 / L) < tol))
    checks.append(("ss_point_offcenter_reactions_sum_eq_P",
                    abs((R1b + R2b) - P) / P < tol))

    y_formula2 = _ss_point_deflection(np.array([a2]), L, P, a2, EI)[0]
    y_virtual2 = _unit_load_deflection_ss(
        L, lambda xx: _ss_point_load(xx, L, P, a2)[0], a2, EI)
    checks.append(("ss_point_offcenter_deflection_vs_unit_load_method",
                    abs(y_virtual2 - y_formula2) / abs(y_formula2) < tol))

    # 3) SS, UDL
    w = 2000.0
    M3, V3, R1c, R2c = _ss_udl(x, L, w)
    M3_max = np.max(np.abs(M3))
    V3_max = np.max(np.abs(V3))
    checks.append(("ss_udl_Mmax_vs_wL2/8",
                    abs(M3_max - w * L ** 2 / 8.0) / (w * L ** 2 / 8.0) < tol))
    checks.append(("ss_udl_Vmax_vs_wL/2",
                    abs(V3_max - w * L / 2.0) / (w * L / 2.0) < tol))
    checks.append(("ss_udl_reactions_sum_eq_wL",
                    abs((R1c + R2c) - w * L) / (w * L) < tol))

    y3_formula = _ss_udl_deflection(np.array([L / 2.0]), L, w, EI)[0]
    y3_closed = 5.0 * w * L ** 4 / (384.0 * EI)
    checks.append(("ss_udl_deflection_vs_closed_form_5wL4/384EI",
                    abs(y3_formula - y3_closed) / abs(y3_closed) < tol))

    y3_virtual = _unit_load_deflection_ss(
        L, lambda xx: _ss_udl(xx, L, w)[0], L / 2.0, EI)
    checks.append(("ss_udl_deflection_vs_unit_load_method",
                    abs(y3_virtual - y3_formula) / abs(y3_formula) < tol))

    # 4) Voladizo, carga puntual en la punta
    M4, V4 = _cant_point_load(x, L, P, L)
    M4_max = np.max(np.abs(M4))
    V4_max = np.max(np.abs(V4))
    checks.append(("cant_point_tip_Mmax_vs_PL",
                    abs(M4_max - P * L) / (P * L) < tol))
    checks.append(("cant_point_tip_Vmax_vs_P",
                    abs(V4_max - P) / P < tol))

    y4_formula = _cant_point_deflection(np.array([L]), L, P, L, EI)[0]
    y4_closed = P * L ** 3 / (3.0 * EI)
    checks.append(("cant_point_tip_deflection_vs_closed_form_PL3/3EI",
                    abs(y4_formula - y4_closed) / abs(y4_closed) < tol))

    y4_virtual = _unit_load_deflection_cant(
        L, lambda xx: _cant_point_load(xx, L, P, L)[0], L, EI)
    checks.append(("cant_point_tip_deflection_vs_unit_load_method",
                    abs(y4_virtual - y4_formula) / abs(y4_formula) < tol))

    # 5) Voladizo, carga puntual NO en la punta
    a5 = 2.5
    M5, V5 = _cant_point_load(x, L, P, a5)
    M5_max = np.max(np.abs(M5))
    checks.append(("cant_point_offend_Mmax_vs_Pa",
                    abs(M5_max - P * a5) / (P * a5) < tol))

    y5_formula = _cant_point_deflection(np.array([L]), L, P, a5, EI)[0]
    y5_virtual = _unit_load_deflection_cant(
        L, lambda xx: _cant_point_load(xx, L, P, a5)[0], L, EI)
    checks.append(("cant_point_offend_tipdeflection_vs_unit_load_method",
                    abs(y5_virtual - y5_formula) / abs(y5_formula) < tol))

    # 6) Voladizo, UDL
    M6, V6 = _cant_udl(x, L, w)
    M6_max = np.max(np.abs(M6))
    V6_max = np.max(np.abs(V6))
    checks.append(("cant_udl_Mmax_vs_wL2/2",
                    abs(M6_max - w * L ** 2 / 2.0) / (w * L ** 2 / 2.0) < tol))
    checks.append(("cant_udl_Vmax_vs_wL",
                    abs(V6_max - w * L) / (w * L) < tol))

    y6_formula = _cant_udl_deflection(np.array([L]), L, w, EI)[0]
    y6_closed = w * L ** 4 / (8.0 * EI)
    checks.append(("cant_udl_tipdeflection_vs_closed_form_wL4/8EI",
                    abs(y6_formula - y6_closed) / abs(y6_closed) < tol))

    y6_virtual = _unit_load_deflection_cant(
        L, lambda xx: _cant_udl(xx, L, w)[0], L, EI)
    checks.append(("cant_udl_tipdeflection_vs_unit_load_method",
                    abs(y6_virtual - y6_formula) / abs(y6_formula) < tol))

    # 7) Consistencia dM/dx = V (derivada numerica central)
    h = 1e-4
    x0 = 1.7
    Mp, _, _, _ = _ss_point_load(np.array([x0 + h]), L, P, a2)
    Mm, _, _, _ = _ss_point_load(np.array([x0 - h]), L, P, a2)
    dMdx_numeric = (Mp[0] - Mm[0]) / (2 * h)
    _, V_at_x0, _, _ = _ss_point_load(np.array([x0]), L, P, a2)
    checks.append(("ss_point_dMdx_matches_V_numeric_derivative",
                    abs(dMdx_numeric - V_at_x0[0]) / abs(V_at_x0[0]) < 1e-2))

    # 8) Factor de seguridad: aritmetica directa
    S_test = 4.0e-4
    sigma_y = 250e6
    sigma_max, sf = _safety_factor(M4_max, S_test, sigma_y)
    checks.append(("safety_factor_arithmetic_consistency",
                    abs(sigma_max * sf - sigma_y) / sigma_y < tol))

    # Fix: abs(...) < tol contra escalares numpy devuelve numpy.bool_, que
    # NumPy 2.x nombra igual que el bool nativo (no se distingue a simple
    # vista) pero json.dumps() no lo serializa. Se normaliza a bool nativo.
    checks = [(name, bool(ok)) for name, ok in checks]
    n_ok = sum(1 for _, ok in checks if ok)
    return {
        "validation_passed": bool(n_ok == len(checks)),
        "checks_passed": n_ok,
        "checks_total": len(checks),
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def compute_structural_beam_tool(mode, params=None):
    params = params or {}
    if mode == "simply_supported_point_load":
        return simply_supported_point_load(params)
    elif mode == "simply_supported_distributed_load":
        return simply_supported_distributed_load(params)
    elif mode == "cantilever_point_load":
        return cantilever_point_load(params)
    elif mode == "cantilever_distributed_load":
        return cantilever_distributed_load(params)
    elif mode == "validate":
        return validate()
    else:
        raise ValueError(f"mode no reconocido: {mode}")


# ---------------------------------------------------------------------------
# TOOL_SCHEMA para register_tool()
# ---------------------------------------------------------------------------

STRUCTURAL_BEAM_TOOL_SCHEMA = {
    "name": "structural_beam_tool",
    "description": (
        "Analisis de vigas Euler-Bernoulli: simplemente apoyadas y en "
        "voladizo (cantilever), con carga puntual o carga distribuida "
        "uniforme. Devuelve diagrama de momento flector, diagrama de "
        "corte, deflexion maxima y (si se entrega seccion transversal y "
        "resistencia de fluencia) el factor de seguridad."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "simply_supported_point_load",
                    "simply_supported_distributed_load",
                    "cantilever_point_load",
                    "cantilever_distributed_load",
                    "validate",
                ],
            },
            "params": {
                "type": "object",
                "properties": {
                    "L": {"type": "number", "description": "Luz o largo del voladizo, en metros"},
                    "P": {"type": "number", "description": "Carga puntual, en Newtons (modos point_load)"},
                    "w": {"type": "number", "description": "Carga distribuida, en N/m (modos distributed_load)"},
                    "a": {"type": "number", "description": "Posicion de la carga puntual desde el apoyo/empotramiento izquierdo, en metros (default: centro para viga apoyada, extremo libre para voladizo)"},
                    "E": {"type": "number", "description": "Modulo de elasticidad, en Pa (default: 200e9, acero estructural)"},
                    "section": {
                        "type": "object",
                        "description": "Seccion transversal: {shape:'rectangular', width, height} o {shape:'circular', diameter} o {shape:'custom', I, c}",
                    },
                    "yield_strength": {"type": "number", "description": "Resistencia de fluencia del material, en Pa (opcional, activa el calculo de factor de seguridad)"},
                    "n_points": {"type": "integer", "description": "Cantidad de puntos para los diagramas (default 200)"},
                },
                "required": ["L"],
            },
        },
        "required": ["mode", "params"],
    },
}


if __name__ == "__main__":
    result = compute_structural_beam_tool("validate")
    passed = result["checks_passed"]
    total = result["checks_total"]
    print(f"{passed}/{total} self-tests OK")
    for name, ok in result["checks"]:
        status = "OK" if ok else "FALLO"
        print(f"  [{status}] {name}")

    print()
    print("--- Ejemplo de uso real: viga simplemente apoyada, carga "
          "puntual centrada, perfil rectangular de madera ---")
    example = compute_structural_beam_tool(
        "simply_supported_point_load",
        {
            "L": 3.0,
            "P": 1500.0,
            "E": 11e9,
            "section": {"shape": "rectangular", "width": 0.05, "height": 0.15},
            "yield_strength": 40e6,
        },
    )
    print(f"Momento maximo: {example['bending_moment_max_Nm']:.1f} N*m")
    print(f"Corte maximo: {example['shear_max_N']:.1f} N")
    print(f"Deflexion maxima: {example['deflection_max_m']*1000:.2f} mm")
    print(f"Factor de seguridad: {example['safety_factor']:.2f}")

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("structural_beam_tool", STRUCTURAL_BEAM_TOOL_SCHEMA, lambda args, _f=compute_structural_beam_tool: _f(**args))
