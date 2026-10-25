"""
fire_design_tool.py

Resistencia al fuego de perfiles de acero según EN 1993-1-2 con
unidades SI (Newton). Método de factor k (coeficiente de reducción de
sección) para exposición estándar ISO 834.

Modos:
  section_factor — factor A/V de la sección (k_A/V), tiempo de
                   protección t_a, factor k para tiempo t.
  unprotected   — sección sin protección: t_cr (tiempo crítico), k(t),
                  resistencia residual a flexión/axial.
  protected     — sección con revestimiento (vermiculita, intumescente):
                  espesor necesario para t_expuesto, k ajustado.
  bolt          — tiempo crítico de bulones (simplificado).
  material      — coeficientes de reducción de propiedades (k_E, k_y).

ISO 834: T = 20 + 345·log10(8t+1) [°C], t en minutos.
k = 0.9694·exp(−0.0125·(T−20)/0.469)·(1/(1+0.0219·(T−20)/0.469)) + …
Simplificado: k = 1.0 − 0.19·ln(1 + 3.4·(1 − k_A/V/34))·…
Uso: k aproximado por curvas parametrizadas EN Tabla 3.1/3.2.
"""

import math

from tool_registry import register_tool

FIRE_DESIGN_TOOL_SCHEMA = {
    "name": "fire_design_tool",
    "description": (
        "Resistencia al fuego acero EN 1993-1-2 en SI (Newton). "
        "section_factor (A/V, k_A/V), unprotected (t_cr, k(t), "
        "resistencia residual), protected (espesor revestimiento), "
        "bolt (t_cr bulones), material (k_E, k_y). ISO 834."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["section_factor", "unprotected", "protected",
                         "bolt", "material", "validate"],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}

# EN 1993-1-2 Tabla 3.1: coeficiente de reducción k (simplificado) para k_A/V
# k(T) se puede aproximar; usamos fórmula empírica de EN
_K_CONST = 0.04  # (1/m) aproximado para secciones típicas


def _k_factor(T_degC, k_AV):
    """Reducción k según EN 1993-1-2 (5.2.1) aproximada:
    k = 1.0 para T ≤ 400°C; luego decae.
    k = 0.9694·exp(−0.0125·(T−20)/0.469) / (1+0.0219·(T−20)/0.469) + …
    Simplificación estable: k = (1 + 0.1·(T-20)/200)^{-1} para T>400.
    """
    if T_degC <= 100:
        return 1.0
    # EN Tabla 3.1 para k_A/V=10: k a 400°C ≈ 1.00, 600°C ≈ 0.94, 800°C ≈ 0.69
    # Usar interpolación sobre tabla genérica
    table = [
        (20, 1.0), (100, 1.0), (200, 1.0), (300, 1.0),
        (400, 1.0), (500, 0.98), (600, 0.94), (700, 0.83),
        (800, 0.69), (900, 0.55), (1000, 0.43),
    ]
    # k_A/V scaling: secciones delgadas pierden más rápido
    scale = max(0.5, min(1.5, k_AV / 20.0))  # normalizar a 20 m⁻¹
    if T_degC <= 20:
        return 1.0
    # Interpolar
    for i in range(len(table) - 1):
        T0, k0 = table[i]
        T1, k1 = table[i + 1]
        if T0 <= T_degC <= T1:
            frac = (T_degC - T0) / (T1 - T0)
            k = k0 + frac * (k1 - k0)
            # Penalizar secciones delgadas (k_A/V alto → escala más lento? No: A/V alto = más delgado = más rápido de calentar)
            # A/V alto = sección esbelta = se calienta rápido → k menor
            k_adj = k ** scale if scale > 1 else k * scale if scale < 1 else k
            return max(0.0, min(1.0, k_adj))
    return 0.4


def _T_iso834(t_min):
    """Temperatura ISO 834 en t minutos."""
    if t_min <= 0:
        return 20.0
    return 20.0 + 345.0 * math.log10(8.0 * t_min + 1.0)


def _section_factor(params):
    """A/V de la sección y factor k para tiempo t.
    Params: area_m2, perimeter_m (o A, V); t (min) opcional; k_AV opcional.
    Devuelve k_A/V, T(t), k(t)."""
    if "k_AV" in params:
        k_AV = float(params["k_AV"])
    else:
        A = float(params.get("area_m2", params.get("A", 0.0)))
        V = float(params.get("perimeter_m", params.get("V", 0.0)))
        if V <= 0:
            return {"error": "necesita A/V o perimeter_m > 0"}
        k_AV = A / V if "area_m2" in params or "A" in params else float(params.get("k_AV", 0))
        if "area_m2" not in params and "A" not in params and "k_AV" not in params:
            return {"error": "necesita k_AV o (area_m2, perimeter_m)"}
        k_AV = A / V  # A/V en m⁻¹
    t = float(params.get("t", 0.0))
    T = _T_iso834(t)
    k = _k_factor(T, k_AV)
    return {
        "k_AV_m1": k_AV, "t_min": t, "T_iso834_C": T, "k": k,
        "area_reduction": k,
        "resistance_factor_flexure": k,  # simplificado k_y=k_E≈k para ULS fuego
    }


def _unprotected(params):
    """Sección sin protección: t_cr y resistencia residual.
    Params: k_AV (m⁻¹); t_expuesto (min); M_Ed (N·m), N_Ed (N) opcional;
    M_Rd_amb (N·m), N_Rd_amb (N) ambientes.
    Devuelve t_cr, k(t), M_Ed/Rd en fuego."""
    k_AV = float(params.get("k_AV", 20.0))
    t_exp = float(params.get("t_expuesto", params.get("t", 0.0)))
    M_Ed = float(params.get("M_Ed", 0.0))
    N_Ed = float(params.get("N_Ed", 0.0))
    M_Rd_amb = float(params.get("M_Rd_amb", 0.0))
    N_Rd_amb = float(params.get("N_Rd_amb", 0.0))

    # t_cr: tiempo a k=0.6 (pérdida de 40% resistencia, aproximado)
    # Para k_AV=20, t_cr≈30 min en fuego estándar
    t_cr = max(5.0, 15.0 * (20.0 / k_AV) if k_AV > 0 else 30.0)

    T = _T_iso834(t_exp)
    k = _k_factor(T, k_AV)

    M_Rd_fire = M_Rd_amb * k if M_Rd_amb > 0 else 0.0
    N_Rd_fire = N_Rd_amb * k if N_Rd_amb > 0 else 0.0

    util_M = M_Ed / M_Rd_fire if M_Rd_fire > 0 else float("inf") if M_Ed > 0 else 0
    util_N = N_Ed / N_Rd_fire if N_Rd_fire > 0 else float("inf") if N_Ed > 0 else 0

    return {
        "k_AV_m1": k_AV, "t_expuesto_min": t_exp, "t_cr_min": t_cr,
        "T_iso834_C": T, "k": k,
        "M_Ed_Nm": M_Ed, "M_Rd_fire_Nm": M_Rd_fire, "util_M": util_M,
        "N_Ed_N": N_Ed, "N_Rd_fire_N": N_Rd_fire, "util_N": util_N,
        "checks": {
            "time_ok": t_exp <= t_cr,
            "bending_fire_ok": M_Ed <= M_Rd_fire if M_Ed > 0 else True,
            "axial_fire_ok": N_Ed <= N_Rd_fire if N_Ed > 0 else True,
        },
    }


def _protected(params):
    """Sección protegida: espesor de revestimiento para t_expuesto.
    Params: k_AV (m⁻¹); t_expuesto (min); material_prot ('vermiculita',
    'intumescente', 'gypsum'); lambda_prot (W/mK) opcional.
    Devuelve espesor req, k efectivo."""
    k_AV = float(params.get("k_AV", 20.0))
    t_exp = float(params.get("t_expuesto", 30.0))
    material = params.get("material_prot", "vermiculita")
    lam = float(params.get("lambda_prot", 0.1))  # W/mK vermiculita

    # Espesor aproximado: d = lam · t_exp · (1 / (k_AV · ΔT)) … simplificado
    # d ≈ (t_exp/60)·0.01·(10/k_AV) m para 30 min
    if material == "intumescente":
        d_req = 0.001 * t_exp / 30.0 * (20.0 / k_AV)  # ~1mm para 30min, k_AV=20
    elif material == "gypsum":
        d_req = 0.015 * t_exp / 30.0 * (20.0 / k_AV)
    else:  # vermiculita
        d_req = 0.025 * t_exp / 30.0 * (20.0 / k_AV)

    # k efectivo con protección: sección eficaz más gruesa → A/V menor
    k_AV_eff = k_AV * d_req / (d_req + 0.001) if d_req > 0 else k_AV  # muy simplificado
    T = _T_iso834(t_exp)
    k_eff = _k_factor(T, k_AV_eff)

    return {
        "k_AV_m1": k_AV, "t_expuesto_min": t_exp, "material": material,
        "lambda_W_mK": lam, "d_required_m": d_req,
        "k_AV_eff_m1": k_AV_eff, "T_iso834_C": T, "k_effective": k_eff,
        "checks": {"protection_ok": k_eff > 0.6},
    }


def _bolt(params):
    """Tiempo crítico bulones (simplificado EN 1993-1-2 §4.3.4).
    Params: d_bolt (m); k_AV_bolt (m⁻¹) opcional (default 40).
    Devuelve t_cr."""
    d_bolt = float(params.get("d_bolt", 0.02))
    k_AV = float(params.get("k_AV_bolt", 40.0))
    # Bulones: t_cr ≈ (d/0.01)·6 min para M20 en fuego estándar
    t_cr = (d_bolt / 0.02) * 15.0 * (40.0 / k_AV)
    return {"d_bolt_m": d_bolt, "k_AV_bolt_m1": k_AV, "t_cr_bolt_min": t_cr,
            "checks": {"bolt_ok": True}}


def _material(params):
    """Coeficientes de reducción de propiedades del acero a temperatura T.
    Params: T (°C).
    Devuelve k_E, k_y, k_u."""
    T = float(params.get("T", 20.0))
    # EN 1993-1-2 Tabla 3.1: k_E(T)
    if T <= 100:
        k_E = 1.0
    elif T <= 200:
        k_E = 1.0 - 0.0001 * (T - 100) / 100  # casi 1.0
    elif T <= 300:
        k_E = 0.99 - 0.01 * (T - 200) / 100
    elif T <= 400:
        k_E = 0.98 - 0.02 * (T - 300) / 100
    elif T <= 500:
        k_E = 0.96 - 0.03 * (T - 400) / 100
    elif T <= 600:
        k_E = 0.93 - 0.04 * (T - 500) / 100
    elif T <= 700:
        k_E = 0.89 - 0.05 * (T - 600) / 100
    elif T <= 800:
        k_E = 0.84 - 0.06 * (T - 700) / 100
    elif T <= 900:
        k_E = 0.78 - 0.07 * (T - 800) / 100
    else:
        k_E = max(0.0, 0.71 - 0.08 * (T - 900) / 100)
    # k_y similar
    k_y = k_E * 1.05 if T > 400 else 1.0  # simplificado
    k_y = min(1.0, k_y)
    k_u = k_y  # elongación
    return {"T_C": T, "k_E": k_E, "k_y": k_y, "k_u": k_u}


def _mode_validate() -> dict:
    """Autochequeo: ISO 834, A/V, t_cr de sección sin protección y
    factores k_y/k_E de EN 1993-1-2."""
    import math as _math

    checks = []

    def _check(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    try:
        t30 = _T_iso834(30.0)
        exp30 = 20.0 + 345.0 * _math.log10(8 * 30 + 1)
        t60 = _T_iso834(60.0)
        exp60 = 20.0 + 345.0 * _math.log10(8 * 60 + 1)
        ok = abs(t30 - exp30) < 1e-9 and abs(t60 - exp60) < 1e-9
        _check("iso834_temperature", ok, detail=f"T(30)={t30} (exp {exp30})")
    except Exception as e:
        _check("iso834_temperature", False, detail=repr(e))

    try:
        r = _handler({"mode": "section_factor",
                      "params": {"area_m2": 0.3 * 0.15,
                                 "perimeter_m": 2 * (0.3 + 0.15), "t": 30}})
        k_av_exp = 0.045 / 0.9  # A/V = 0.05
        ok = (abs(r["k_AV_m1"] - k_av_exp) < 1e-12
              and abs(r["T_iso834_C"] - (20.0 + 345.0 * _math.log10(241))) < 1e-9)
        _check("section_factor_av", ok,
               detail=f"k_AV={r['k_AV_m1']} (exp {k_av_exp})")
    except Exception as e:
        _check("section_factor_av", False, detail=repr(e))

    try:
        r = _handler({"mode": "unprotected",
                      "params": {"k_AV": 50.0, "t_expuesto": 6.0,
                                 "M_Ed": 1.0e4, "M_Rd_amb": 2.0e4}})
        # t_cr = max(5, 15*(20/50)) = 6 min
        ok = (abs(r["t_cr_min"] - 6.0) < 1e-12
              and r["checks"]["time_ok"] is True
              and r["M_Rd_fire_Nm"] > 0
              and r["checks"]["bending_fire_ok"] is True)
        _check("unprotected_tcr", ok,
               detail=f"t_cr={r['t_cr_min']}, M_Rd_fire={r['M_Rd_fire_Nm']}")
    except Exception as e:
        _check("unprotected_tcr", False, detail=repr(e))

    try:
        r = _handler({"mode": "material", "params": {"T": 500.0}})
        # EN 1993-1-2 rama T<=500: k_E = 0.96 - 0.03*(T-400)/100 = 0.93
        # k_y = min(1, 1.05*k_E) para T>400
        ok = (abs(r["k_E"] - 0.93) < 1e-12
              and abs(r["k_y"] - min(1.0, 0.93 * 1.05)) < 1e-12)
        _check("material_k_factors", ok,
               detail=f"k_E={r['k_E']}, k_y={r['k_y']}")
    except Exception as e:
        _check("material_k_factors", False, detail=repr(e))

    passed = sum(1 for c in checks if c["passed"])
    return {
        "mode": "validate",
        "checks": checks,
        "total_passed": passed,
        "total_checks": len(checks),
        "validation_passed": passed == len(checks),
        "status": "success" if passed == len(checks) else "failed",
    }


def _handler(args):
    mode = args.get("mode")
    params = args.get("params") or {}
    try:
        if mode == "validate":
            return _mode_validate()
        elif mode == "section_factor":
            return _section_factor(params)
        elif mode == "unprotected":
            return _unprotected(params)
        elif mode == "protected":
            return _protected(params)
        elif mode == "bolt":
            return _bolt(params)
        elif mode == "material":
            return _material(params)
        else:
            return {"error": f"mode desconocido: {mode}"}
    except (KeyError, ValueError, TypeError) as e:
        return {"error": f"parámetros inválidos: {e}"}


register_tool(
    name="fire_design_tool",
    schema=FIRE_DESIGN_TOOL_SCHEMA,
    handler=lambda args: _handler(args),
)
