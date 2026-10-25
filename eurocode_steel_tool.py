"""
eurocode_steel_tool.py

Verificación de secciones de acero según EN 1993-1-1 (Eurocódigo 3) con
el kernel Rust para χ/λ̄/N_cr (fórmulas cerradas, misma precisión que
el solver de pórticos).

Modos:
  section_class — clase de sección 1–4 (6.2.1) para I/H, L, tubo
                 rectangular y rectangular macizo.
  buckling      — pandeo de barras centradas (6.3.1): χ (curvas a0/a/b/c/d),
                  resistencia N_b,Rd.
  bending       — resistencia a flexión (6.2.5): W_el·fy/γM0, W_pl·fy/γM0.
  combined      — interacción N+M (6.6.1 bend- buckling, 6.6.2 N+M flexión).
  sls           — límites de flecha (EN 1993-1-1 NA / CEN: L/250 etc.) y
                  verificación de uso.
  ecb_combo     — combinaciones de cargas EN 1990 (6.4.3.2) ULS/SLS con
                  factores γ y ψ por defecto (edificación).

γ por defecto (NA España / EN comunes): γM0=1.0, γM1=1.0, γM2=1.1.
α curvas pandeo: a0=0.13, a=0.21, b=0.34, c=0.49, d=0.76 (4.1.2 Tabla 3).
"""

import json
import os
import struct_kernel_py as sk
from tool_registry import register_tool

_CATALOG_PATH = os.path.join(os.path.dirname(__file__), "steel_catalog.json")
_CATALOG_CACHE = None


def _load_catalog():
    global _CATALOG_CACHE
    if _CATALOG_CACHE is None:
        with open(_CATALOG_PATH, "r", encoding="utf-8") as f:
            _CATALOG_CACHE = json.load(f)
    return _CATALOG_CACHE


def _load_profile(name):
    """Carga un perfil del catálogo FreeCAD (cm) y lo convierte a SI (m, m², m⁴, m³).
    Devuelve dict con A_m2, Ix_m4, Iy_m4, Wx_m3, Wy_m3, h_m, b_m, tw_m, tf_m, peso_kg_m."""
    cat = _load_catalog()
    key = name.replace(" ", "").upper()
    entry = None
    for k in cat:
        if k.upper() == key:
            entry = cat[k]
            break
    if entry is None:
        # búsqueda parcial
        matches = [k for k in cat if key in k.upper()]
        if len(matches) == 1:
            entry = cat[matches[0]]
            key = matches[0]
        elif matches:
            raise ValueError(f"perfil ambiguo '{name}': {matches[:8]}")
        else:
            raise ValueError(f"perfil no encontrado: {name}")
    return {
        "name": key,
        "A_m2": entry["A"] * 1e-4,
        "Ix_m4": entry["Ix"] * 1e-8,
        "Iy_m4": entry["Iy"] * 1e-8,
        "Wx_m3": entry["Wx"] * 1e-6,
        "Wy_m3": entry["Wy"] * 1e-6,
        "h_m": entry["h"] * 0.01,
        "b_m": entry["b"] * 0.01,
        "tw_m": entry["tw"] * 0.01,
        "tf_m": entry["tf"] * 0.01,
        "r_m": entry.get("r", 0) * 0.01,
        "peso_kg_m": entry["peso"],
    }


def _inject_profile(params):
    """Si params['profile'] existe, rellena A/I/W/h/b/tw/tf ausentes desde el catálogo."""
    pname = params.get("profile")
    if not pname:
        return params
    p = _load_profile(pname)
    # no sobreescribir lo que el usuario ya puso
    mapping = {
        "A": "A_m2", "Iz": "Iy_m4", "Ix": "Ix_m4",
        "Wz": "Wx_m3", "Wx_cat": "Wx_m3", "Wy": "Wy_m3",
        "h": "h_m", "b": "b_m", "tw": "tw_m", "tf": "tf_m",
    }
    out = dict(params)
    out["_profile"] = p
    for target, src in mapping.items():
        if target not in out and src in p:
            out[target] = p[src]
    return out

EUROCODE_STEEL_TOOL_SCHEMA = {
    "name": "eurocode_steel_tool",
    "description": (
        "Verificación de acero EN 1993-1-1. section_class (clase 1-4), "
        "buckling (χ pandeo axial, N_b,Rd), bending (M_c,Rd elástico/"
        "plástico), combined (interacción N+M 6.6.1/6.6.2), sls "
        "(límites de flecha), ecb_combo (combinaciones EN 1990 ULS/SLS "
        "con γ y ψ), profile (buscar perfil en catálogo FreeCAD 317 secciones). "
        "Todos los modos aceptan 'profile': 'IPE300' para auto-llenar A/I/W/h/b. "
        "Motor de χ/λ̄/N_cr en Rust (doble precisión)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["section_class", "buckling", "bending",
                         "combined", "sls", "ecb_combo", "profile", "validate"],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}

_ALPHA = {"a0": 0.13, "a": 0.21, "b": 0.34, "c": 0.49, "d": 0.76}
_GM0 = 1.0
_GM1 = 1.0
_GM2 = 1.1

# EN 1990 Tabla A1.1 — ψ0, ψ1, ψ2 para edificación (B)
_PSI_B = {"G": 1.0, "Q": 0.7, "W": 0.6, "A": 0.0}   # ψ0
_PSI1_B = {"G": 1.0, "Q": 0.7, "W": 0.5, "A": 0.0}
_PSI2_B = {"G": 1.0, "Q": 0.6, "W": 0.3, "A": 0.0}


def _section_class_I(h, b, tw, tf, c, eps=None, fy=355e6):
    """Clase de sección para perfil doblado en frío / laminado I o H.
    h, b, tw, tf, c en metros; fy en Pa. eps = √(235/fy)."""
    if eps is None:
        eps = (235e6 / fy) ** 0.5
    out = {}
    # Alas: c/tf
    out["flange_c_over_tf"] = (b - tw) / 2 / tf if b else 0.0
    # Web: c/tw = (h − 2tf − 2r)/tw; sin r se usa h − 2tf
    out["web_h_over_tw"] = (h - 2 * tf) / tw if tw else float("inf")

    cf = out["flange_c_over_tf"]
    cw = out["web_h_over_tw"]
    # Clase ala (Tabla 5.2, sheet 1 para cargas concentradas altas no aplica)
    if cf <= 9 * eps:
        flange = 1
    elif cf <= 10 * eps:
        flange = 2
    elif cf <= 14 * eps:
        flange = 3
    else:
        flange = 4
    # Clase web en flexión/combinada (n = NEd=0): compresión uniforme
    if cw <= 33 * eps:
        web = 1
    elif cw <= 38 * eps:
        web = 2
    elif cw <= 42 * eps:
        web = 3
    else:
        web = 4
    out["flange_class"] = flange
    out["web_class"] = web
    out["section_class"] = max(flange, web)
    out["eps"] = eps
    return out


def _section_class_L(h, b, t, c, eps=None, fy=355e6):
    """Ángulo: c/t ≤ 9eps → clase 1/2, ≤ 14eps → 3, si no 4 (simplificado
    EN 1993-1-1 Tabla 5.2 para ángulos en compresión/flexión)."""
    if eps is None:
        eps = (235e6 / fy) ** 0.5
    ratio = max(h, b) / t
    if ratio <= 9 * eps:
        cls = 1
    elif ratio <= 14 * eps:
        cls = 3
    else:
        cls = 4
    return {"c_over_t": ratio, "section_class": cls, "eps": eps}


def _section_class_rect(h, b, t, eps=None, fy=355e6):
    """Tubo rectangular / macizo: c/t ≤ 33eps (1), 38eps (2), 42eps (3)."""
    if eps is None:
        eps = (235e6 / fy) ** 0.5
    ratio = min(h, b) / t
    if ratio <= 33 * eps:
        cls = 1
    elif ratio <= 38 * eps:
        cls = 2
    elif ratio <= 42 * eps:
        cls = 3
    else:
        cls = 4
    return {"c_over_t": ratio, "section_class": cls, "eps": eps}


def _buckling(params):
    n_ed = float(params["N_Ed"])
    area = float(params["A"])
    fy = float(params["fy"])
    l_cr = float(params["L_cr"])
    e_mod = float(params.get("E", 210e9))
    iz = float(params["Iz"])
    curve = str(params.get("curve", "b"))
    gm1 = float(params.get("gamma_M1", _GM1))
    alpha = _ALPHA.get(curve)
    if alpha is None:
        raise ValueError(f"curve desconocida: {curve} (a0/a/b/c/d)")

    n_cr = sk.euler_ncr(e_mod, iz, l_cr)
    if n_cr is None:
        n_cr = 3.141592653589793**2 * e_mod * iz / (l_cr * l_cr)
    lb = sk.lambda_bar(area, fy, n_cr)
    if lb is None:
        lb = (area * fy / n_cr) ** 0.5
    chi = sk.buckling_chi(lb, alpha)
    if chi is None:
        phi = 0.5 * (1 + alpha * (lb - 0.2) + lb * lb)
        chi = 1.0 if lb <= 0.2 else min(1.0, 1.0 / (phi + (phi * phi - lb * lb) ** 0.5))

    n_pl = area * fy / gm1
    n_brd = chi * n_pl
    util = n_ed / n_brd if n_brd > 0 else float("inf")
    return {
        "N_cr": n_cr,
        "lambda_bar": lb,
        "curve": curve,
        "alpha": alpha,
        "chi": chi,
        "N_pl_Rd": n_pl,
        "N_b_Rd": n_brd,
        "N_Ed": n_ed,
        "utilization": util,
        "ok": util <= 1.0,
    }


def _bending(params):
    wz = float(params["Wz"])
    fy = float(params["fy"])
    m_ed = float(params["M_Ed"])
    gm0 = float(params.get("gamma_M0", _GM0))
    section_class = int(params.get("section_class", 1))
    m_elrd = wz * fy / gm0
    if section_class <= 2:
        # W_pl aproximado: para I se pasa W_pl explícito o factor
        w_pl = float(params.get("W_pl", wz * 1.12))
        m_rdd = w_pl * fy / gm0
        m_rd = m_rdd
        basis = "plastic (clase≤2)"
    else:
        m_rd = m_elrd
        basis = "elastic (clase≥3)"
    util = m_ed / m_rd if m_rd > 0 else float("inf")
    return {
        "W_el": wz, "W_pl": params.get("W_pl"),
        "M_el_Rd": m_elrd, "M_Rd": m_rd,
        "basis": basis,
        "M_Ed": m_ed, "utilization": util, "ok": util <= 1.0,
    }


def _combined(params):
    """Interacción N+M (6.6.1 para pandeo, 6.6.2 para flexión pura clase 1/2)."""
    n_ed = float(params["N_Ed"])
    m_ed = float(params["M_Ed"])
    n_brd = float(params["N_b_Rd"])
    m_brd = float(params.get("M_b_Rd", params.get("M_Rd")))
    m_crd = float(params.get("M_c_Rd", params["M_Rd"]))
    kind = str(params.get("kind", "bending"))  # bending | buckling
    if kind == "buckling":
        # 6.6.1 N/M: k factors por curva (Tablas 6.6.1)
        kn = float(params.get("k_n", 0.9))  # curva b aprox
        km = float(params.get("k_m", 0.8))
        n_b = n_ed / n_brd
        m_b = m_ed / m_brd
        eta = n_b + km * m_b / (1.0 - kn * n_b) if (1.0 - kn * n_b) > 0 else float("inf")
        util = eta
    else:
        # 6.6.2 N+M flexión clase 1/2
        n_pl = float(params.get("N_pl_Rd", n_brd))
        n_b = n_ed / n_pl
        m_b = m_ed / m_crd
        # α=2 para secciones I (w≈0.83): 6.6.2 con n + αm + (1−α)n²m ≤ 1
        alpha = float(params.get("alpha_662", 2.0))
        eta = n_b + alpha * m_b + (1.0 - alpha) * n_b * n_b * m_b
        util = eta
    return {
        "kind": kind, "n_ratio": n_ed / n_brd if n_brd else None,
        "m_ratio": m_ed / m_brd if m_brd else None,
        "eta": util, "ok": util <= 1.0,
    }


def _sls(params):
    length = float(params["L"])
    v_ed = float(params["v_Ed"])
    limit = str(params.get("limit", "L/250"))
    limits = {
        "L/250": length / 250.0,
        "L/300": length / 300.0,
        "L/200": length / 200.0,
        "L/500": length / 500.0,
    }
    if limit not in limits:
        raise ValueError(f"limit desconocido: {limit}")
    v_lim = limits[limit]
    return {
        "L": length, "v_Ed": v_ed, "limit": limit, "v_lim": v_lim,
        "utilization": v_ed / v_lim if v_lim else float("inf"),
        "ok": abs(v_ed) <= v_lim,
    }


def _ecb_combo(params):
    """Combinaciones EN 1990 (6.4.3.2) para edificación (B).

    actions: {name: {"type": "G"|"Q"|"W"|"A", "value": float}}
    Los valores son característicos. Devuelve ULS/SLS con factores.
    """
    actions = params["actions"]
    design = str(params.get("design", "ULS"))
    g_g = float(params.get("gamma_G", 1.35))
    g_q = float(params.get("gamma_Q", 1.5))

    g_char = sum(a["value"] for a in actions.values() if a["type"] == "G")
    q_vars = {k: a for k, a in actions.items() if a["type"] in ("Q", "W")}
    w_vars = {k: a for k, a in actions.items() if a["type"] == "W"}

    combos = []
    if design == "ULS":
        # 6.4.3.2 básica: γG·G + γQ,1·Q1 + Σ γQi ψ0i Qi
        for lead, lead_a in q_vars.items():
            terms = [("G", g_g, g_char)]
            for k, a in q_vars.items():
                if k == lead:
                    terms.append((k, g_q, a["value"]))
                else:
                    psi0 = _PSI_B.get(a["type"], 0.7)
                    terms.append((k, g_q * psi0, a["value"]))
            for k, a in w_vars.items():
                if k == lead:
                    terms.append((k, g_q, a["value"]))
                else:
                    psi0 = _PSI_B.get("W", 0.6)
                    terms.append((k, g_q * psi0, a["value"]))
            ed = sum(f * v for _, f, v in terms)
            combos.append({
                "type": f"ULS_EQU_{lead}", "leading": lead,
                "factors": terms, "design_value": ed,
            })
    else:
        # SLS rara: G + Q1 + Σ ψ2 Qi; frecuente: G + ψ0 Q1...
        for lead, lead_a in q_vars.items():
            terms = [("G", 1.0, g_char)]
            for k, a in q_vars.items():
                f = 1.0 if k == lead else _PSI2_B.get("G", 0.6)
                terms.append((k, f, a["value"]))
            ed = sum(f * v for _, f, v in terms)
            combos.append({
                "type": f"SLS_q_{lead}", "leading": lead,
                "factors": terms, "design_value": ed,
            })
        for lead, lead_a in q_vars.items():
            terms = [("G", 1.0, g_char)]
            for k, a in q_vars.items():
                f = 1.0 if k == lead else _PSI_B.get(a["type"], 0.7)
                terms.append((k, f, a["value"]))
            ed = sum(f * v for _, f, v in terms)
            combos.append({
                "type": f"SLS_f_{lead}", "leading": lead,
                "factors": terms, "design_value": ed,
            })
    return {"design": design, "combos": combos,
            "gamma_G": g_g, "gamma_Q": g_q}


def _mode_validate() -> dict:
    """Autochequeo: clase de sección, N_cr de Euler, χ·N_pl y combinación ULS."""
    import math as _math

    checks = []

    def _check(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    try:
        r = _handler({"mode": "section_class",
                      "params": {"shape": "I", "h": 100, "b": 50,
                                 "tw": 5, "tf": 8}})
        # c/tf = ((50-5)/2)/8 = 2.8125 ; h/tw claro = (100-2*8)/5 = 16.8
        ok = (r["section_class"] == 1 and r["flange_class"] == 1
              and abs(r["flange_c_over_tf"] - 2.8125) < 1e-12
              and abs(r["web_h_over_tw"] - 16.8) < 1e-12)
        _check("section_class_I", ok,
               detail=f"class={r['section_class']}, c/tf={r['flange_c_over_tf']}")
    except Exception as e:
        _check("section_class_I", False, detail=repr(e))

    try:
        r = _handler({"mode": "buckling",
                      "params": {"N_Ed": 1e5, "A": 5380e-6, "fy": 355e6,
                                 "L_cr": 3.0, "Iz": 8360e-8}})
        n_cr_exp = _math.pi ** 2 * 210e9 * 8360e-8 / 3.0 ** 2
        chi_exp = r["chi"]
        n_b_exp = chi_exp * 5380e-6 * 355e6  # gamma_M1 = 1.0
        ok = (abs(r["N_cr"] - n_cr_exp) < 1e-3
              and abs(r["N_b_Rd"] - n_b_exp) < 1e-6
              and r["ok"] is True)
        _check("buckling_euler_ncr", ok,
               detail=f"N_cr={r['N_cr']} (exp {n_cr_exp}), N_b_Rd={r['N_b_Rd']}")
    except Exception as e:
        _check("buckling_euler_ncr", False, detail=repr(e))

    try:
        r = _handler({"mode": "ecb_combo",
                      "params": {"actions": {"dead": {"type": "G", "value": 100.0},
                                             "live": {"type": "Q", "value": 50.0}}}})
        # ULS básica: 1.35*100 + 1.5*50 = 210
        dv = r["combos"][0]["design_value"]
        ok = (r["gamma_G"] == 1.35 and r["gamma_Q"] == 1.5 and abs(dv - 210.0) < 1e-9)
        _check("ecb_combo_uls_210", ok, detail=f"design_value={dv}")
    except Exception as e:
        _check("ecb_combo_uls_210", False, detail=repr(e))

    try:
        r = _handler({"mode": "profile", "params": {"profile": "IPE300"}})
        # Catálogo: A=53.8 cm2, peso 42.2 kg/m
        ok = (r.get("name") == "IPE300" and abs(r.get("A_m2", 0) - 5.38e-3) < 1e-12
              and abs(r.get("peso_kg_m", 0) - 42.2) < 1e-9)
        _check("profile_ipe300_catalog", ok,
               detail=f"A={r.get('A_m2')}, peso={r.get('peso_kg_m')}")
    except Exception as e:
        _check("profile_ipe300_catalog", False, detail=repr(e))

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
    mode = args.get("mode", "section_class")
    params = args.get("params") or {}
    if mode == "validate":
        return _mode_validate()
    # inyectar propiedades del catálogo si se pasó 'profile'
    if params.get("profile"):
        params = _inject_profile(params)
    if mode == "profile":
        name = params.get("profile") or params.get("name")
        if not name:
            return {"error": "profile mode requiere 'profile' o 'name' (ej. 'IPE300')"}
        return _load_profile(name)
    if mode == "section_class":
        shape = str(params.get("shape", "I"))
        if shape == "I":
            return _section_class_I(
                float(params["h"]), float(params["b"]),
                float(params["tw"]), float(params["tf"]),
                float(params.get("c", 0.0)),
                eps=params.get("eps"), fy=float(params.get("fy", 355e6)),
            )
        if shape == "L":
            return _section_class_L(
                float(params["h"]), float(params["b"]), float(params["t"]),
                float(params.get("c", 0.0)),
                eps=params.get("eps"), fy=float(params.get("fy", 355e6)),
            )
        if shape == "rect":
            return _section_class_rect(
                float(params["h"]), float(params["b"]), float(params["t"]),
                eps=params.get("eps"), fy=float(params.get("fy", 355e6)),
            )
        raise ValueError(f"shape desconocido: {shape}")
    if mode == "buckling":
        return _buckling(params)
    if mode == "bending":
        return _bending(params)
    if mode == "combined":
        return _combined(params)
    if mode == "sls":
        return _sls(params)
    if mode == "ecb_combo":
        return _ecb_combo(params)
    raise ValueError(f"mode desconocido: {mode}")


register_tool(
    name="eurocode_steel_tool",
    schema=EUROCODE_STEEL_TOOL_SCHEMA,
    handler=_handler,
)
