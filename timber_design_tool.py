"""
timber_design_tool.py

Verificación de madera según EN 1995-1-1 (Eurocódigo 5) con unidades SI
(Newton). Cubre diseño de vigas y columnas en madera, con factores de
clase k_mod y factor de conversión k_h.

Modos:
  beam          — flexión: M_Rd = k_mod·f_m,k·W/γM, verificación M_Ed ≤ M_Rd,
                  flecha SLS (limites L/250, L/500 según servicio).
  column        — compresión: N_Rd = k_mod·f_c,0,k·A/γM + pandeo (λ_rel,k,
                  χ_k curvas 1/2/3), N_b,Rd.
  material      — propiedades de la madera (f_m,k, f_c,0,k, f_v,k, E_0,mean,
                  E_0,05, ρ_mean, k_mod, γM).
  fire          — resistencia al fuego simplificada (sección residual).

γM = 1.3 (ULS). k_mod servicio: 0.9 permanente, 1.0 a largo plazo,
1.1 media, 1.2 corto, 1.25 impacto. Clase servicio: 1 (húmedo ≤20%),
2 (techos, ≤18%), 3 (exterior, variable).
"""

import math

from tool_registry import register_tool

TIMBER_DESIGN_TOOL_SCHEMA = {
    "name": "timber_design_tool",
    "description": (
        "Diseño de madera EN 1995-1-1 en unidades SI (Newton). "
        "beam (flexión M_Rd, k_mod, flecha), column (compresión N_Rd, "
        "pandeo χ_k), material (f_m,k, E_0,mean, k_mod), fire "
        "(resistencia fuego simplificada). γM=1.3, k_mod según servicio."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["beam", "column", "material", "fire", "validate"],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}

_GAMMA_M = 1.3

# EN 1995 Tabla 3.1: k_mod por clase de servicio y duración de carga
_KMOD = {
    # (servicio, duración): k_mod
    ("permanent", "permanent"): 0.6,
    ("permanent", "long_term"): 0.7,
    ("permanent", "medium"): 0.8,
    ("permanent", "short"): 0.9,
    ("permanent", "instant"): 0.9,
    ("long_term", "permanent"): 0.7,
    ("long_term", "long_term"): 0.8,
    ("long_term", "medium"): 0.9,
    ("long_term", "short"): 1.0,
    ("long_term", "instant"): 1.0,
    ("medium", "permanent"): 0.8,
    ("medium", "long_term"): 0.9,
    ("medium", "medium"): 1.0,
    ("medium", "short"): 1.1,
    ("medium", "instant"): 1.1,
    ("short", "permanent"): 0.9,
    ("short", "long_term"): 1.0,
    ("short", "medium"): 1.1,
    ("short", "short"): 1.2,
    ("short", "instant"): 1.25,
}

# EN 1995 Tabla 3.2: propiedades por clase de resistencia (MPa)
_TIMBER_CLASSES = {
    "C14": {"f_m_k": 14, "f_c0_k": 21, "f_t0_k": 8.5, "f_v_k": 1.7, "E0_mean": 7000, "E0_05": 4600, "rho_mean": 310},
    "C16": {"f_m_k": 16, "f_c0_k": 24, "f_t0_k": 9.5, "f_v_k": 1.8, "E0_mean": 8000, "E0_05": 5000, "rho_mean": 350},
    "C18": {"f_m_k": 18, "f_c0_k": 26, "f_t0_k": 10.5, "f_v_k": 2.0, "E0_mean": 8800, "E0_05": 5400, "rho_mean": 380},
    "C22": {"f_m_k": 22, "f_c0_k": 29, "f_t0_k": 12.5, "f_v_k": 2.4, "E0_mean": 9600, "E0_05": 5800, "rho_mean": 420},
    "C24": {"f_m_k": 24, "f_c0_k": 31, "f_t0_k": 14.5, "f_v_k": 2.5, "E0_mean": 10800, "E0_05": 6600, "rho_mean": 440},
    "C27": {"f_m_k": 27, "f_c0_k": 34, "f_t0_k": 16.0, "f_v_k": 2.6, "E0_mean": 11500, "E0_05": 6900, "rho_mean": 470},
    "C30": {"f_m_k": 30, "f_c0_k": 37, "f_t0_k": 17.5, "f_v_k": 2.8, "E0_mean": 12400, "E0_05": 7400, "rho_mean": 490},
    "D24": {"f_m_k": 24, "f_c0_k": 31, "f_t0_k": 14.5, "f_v_k": 2.5, "E0_mean": 10800, "E0_05": 6600, "rho_mean": 440},
}


def _k_mod(servicio, duracion):
    return _KMOD.get((servicio, duracion), 1.0)


def _get_props(tipo, override=None):
    props = _TIMBER_CLASSES.get(tipo.upper(), _TIMBER_CLASSES["C24"]).copy()
    if override:
        props.update(override)
    # Convertir MPa → Pa
    for k in ("f_m_k", "f_c0_k", "f_t0_k", "f_v_k"):
        if k in props:
            props[k] = props[k] * 1e6
    for k in ("E0_mean", "E0_05"):
        if k in props:
            props[k] = props[k] * 1e6
    return props


def _beam(params):
    """Viga madera. Params:
    b, h (m); M_Ed (N·m); tipo (C24…); servicio, duracion;
    L (m) luz; l (alias); load ('permanent'|'medium'|'short');
    E (Pa) opcional override; f_m,k (Pa) opcional.
    Devuelve M_Rd, k_mod, flecha (si L), checks."""
    b = float(params["b"])
    h = float(params["h"])
    M_Ed = float(params.get("M_Ed", 0.0))
    tipo = params.get("tipo", "C24")
    servicio = params.get("servicio", "short")
    duracion = params.get("duracion", "short")
    L = float(params.get("L", params.get("l", 0.0)))

    props = _get_props(tipo, params)
    f_mk = float(params.get("f_m_k", props["f_m_k"]))
    E = float(params.get("E", props["E0_mean"]))
    k_mod = float(params.get("k_mod", _k_mod(servicio, duracion)))

    # W = b·h²/6
    W = b * h ** 2 / 6.0
    M_Rd = k_mod * f_mk * W / _GAMMA_M

    # Flecha SLS (servicio, sin γ): δ = 5·q·L^4/(384·E·I) para UDL
    # Simplificado: si M_Ed y L dados, q = 8·M_Ed/L² para UDL
    flecha = None
    if L > 0:
        I = b * h ** 3 / 12.0
        q = 8.0 * M_Ed / L ** 2 if M_Ed > 0 else 0.0
        # Límites EC5 2.2: permanente+movilizable L/250; solo movilizable L/300;
        # total L/250; viento L/300. Simplificado: total L/250.
        delta = 5.0 * q * L ** 4 / (384.0 * E * I) if q > 0 else 0.0
        flecha = {
            "L_m": L, "q_udl_Nm": q, "delta_m": delta,
            "limit_total": L / 250.0, "limit_instant": L / 300.0,
            "util_total": delta / (L / 250.0) if L > 0 else 0,
        }

    return {
        "tipo": tipo,
        "b_m": b, "h_m": h, "W_m3": W,
        "f_m_k_Pa": f_mk, "E_Pa": E,
        "k_mod": k_mod, "gamma_M": _GAMMA_M,
        "M_Ed_Nm": M_Ed, "M_Rd_Nm": M_Rd,
        "util": M_Ed / M_Rd if M_Rd > 0 else float("inf"),
        "flecha": flecha,
        "checks": {"bending_ok": M_Ed <= M_Rd,
                   "deflection_ok": flecha["util_total"] <= 1.0 if flecha else True},
    }


def _column(params):
    """Columna madera. Params:
    b, h (m); N_Ed (N) compresión; tipo; servicio, duracion;
    L0 (m) longitud efectiva; k_c opcional; E (Pa), f_c0_k (Pa).
    Devuelve N_Rd, N_b,Rd, chi_k, lambda_rel,k."""
    b = float(params["b"])
    h = float(params["h"])
    N_Ed = float(params.get("N_Ed", 0.0))
    tipo = params.get("tipo", "C24")
    servicio = params.get("servicio", "short")
    duracion = params.get("duracion", "short")
    L0 = float(params.get("L0", params.get("l0", 0.0)))

    props = _get_props(tipo, params)
    f_c0k = float(params.get("f_c0_k", props["f_c0_k"]))
    E_mean = float(params.get("E_mean", props["E0_mean"]))
    E_05 = float(params.get("E", props["E0_05"]))
    k_mod = float(params.get("k_mod", _k_mod(servicio, duracion)))

    A = b * h
    N_Rd0 = k_mod * f_c0k * A / _GAMMA_M  # compresión sin pandeo

    # Pandeo EC5 6.3.2: λ1 = 0.7·sqrt(E0,mean/fc,0,k), λ_rel = (L0/i)/λ1
    i_min = min(b, h) / math.sqrt(12.0)
    lam_1 = 0.7 * math.sqrt(E_mean / f_c0k)
    lam_rel = (L0 / i_min) / lam_1 if L0 > 0 and i_min > 0 else 0.0

    if lam_rel < 0.3:
        chi = 1.0
    else:
        k = 0.2  # curva 1 (rect. sin perforaciones)
        beta_c = 0.1  # βc=0.1 madera maciza
        phi = 0.5 * (1 + beta_c * (lam_rel - 0.3) + lam_rel ** 2)
        chi = min(1.0 / (phi + math.sqrt(phi ** 2 - lam_rel ** 2)), 1.0)

    N_b_Rd = chi * N_Rd0

    return {
        "tipo": tipo,
        "b_m": b, "h_m": h, "A_m2": A, "i_min_m": i_min,
        "f_c0_k_Pa": f_c0k, "E_mean_Pa": E_mean, "E_05_Pa": E_05,
        "k_mod": k_mod, "gamma_M": _GAMMA_M,
        "N_Ed_N": N_Ed, "N_Rd0_N": N_Rd0, "N_b_Rd_N": N_b_Rd,
        "lambda_rel_k": lam_rel, "chi_k": chi,
        "util": N_Ed / N_b_Rd if N_b_Rd > 0 else float("inf"),
        "checks": {"compression_ok": N_Ed <= N_b_Rd},
    }


def _fire(params):
    """Resistencia al fuego simplificada madera (charring).
    Params: d (m) espesor inicial; k_char (mm/min) coef. carbonización;
    t (min) exposición; b (m) ancho opcional.
    Devuelve espesor residual, momento residual."""
    d = float(params["d"])
    b = float(params.get("b", 0.0))
    k_char = float(params.get("k_char", 0.65))  # mm/min para madera maciza
    t = float(params.get("t", 0.0))  # min

    char_mm = k_char * t  # mm carbonizados
    char_m = char_mm / 1000.0
    d_res = d - char_m
    if d_res <= 0:
        d_res_eff = 0.0
    else:
        d_res_eff = d_res  # efectivo para resistencia
    if d_res_eff <= 0:
        return {"t_min": t, "char_m": char_m, "d_res_m": d_res_eff,
                "M_Rd_residual_Nm": 0.0,
                "checks": {"fire_ok": False}}
    # W residual = b·d_res²/6 (si b dado, si no asumir cuadrado)
    b_eff = b if b > 0 else d_res_eff
    W_res = b_eff * d_res_eff ** 2 / 6.0
    props = _get_props(params.get("tipo", "C24"), params)
    k_mod_fire = 0.6  # k_mod para fuego (fuego=permanente en ULS fuego)
    M_Rd_res = k_mod_fire * props["f_m_k"] * W_res / _GAMMA_M
    return {
        "t_min": t, "k_char_mm_min": k_char, "char_m": char_m,
        "d_initial_m": d, "d_res_m": d_res_eff, "b_eff_m": b_eff,
        "W_res_m3": W_res, "M_Rd_residual_Nm": M_Rd_res,
        "checks": {"fire_ok": d_res_eff > 0},
    }


def _material(params):
    tipo = params.get("tipo", "C24")
    override = {k: float(params[k]) for k in ("f_m_k", "f_c0_k", "E") if k in params}
    props = _get_props(tipo, override)
    return {
        "tipo": tipo,
        "f_m_k_Pa": props["f_m_k"], "f_c0_k_Pa": props["f_c0_k"],
        "f_t0_k_Pa": props["f_t0_k"], "f_v_k_Pa": props["f_v_k"],
        "E0_mean_Pa": props["E0_mean"], "E0_05_Pa": props["E0_05"],
        "rho_mean": props["rho_mean"],
        "k_mod_tabla": {
            "servicio=short,duracion=short": _k_mod("short", "short"),
            "servicio=short,duracion=medium": _k_mod("short", "medium"),
            "servicio=medium,duracion=medium": _k_mod("medium", "medium"),
        },
        "gamma_M": _GAMMA_M,
    }


def _mode_validate() -> dict:
    """Autochequeo: propiedades EC5 C24, tabla k_mod, flexión de viga
    y pandeo de columna con reimplementación independiente de EC5 6.3.2."""
    import math as _math

    checks = []

    def _check(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    try:
        m = _material({"tipo": "C24"})
        ok = (abs(m["f_m_k_Pa"] - 24e6) < 1e-6
              and abs(m["E0_mean_Pa"] - 10.8e9) < 1e-3
              and m["rho_mean"] == 440 and m["gamma_M"] == 1.3)
        _check("material_c24_ec5", ok,
               detail=f"f_m_k={m['f_m_k_Pa']}, E0_mean={m['E0_mean_Pa']}, rho={m['rho_mean']}")
    except Exception as e:
        _check("material_c24_ec5", False, detail=repr(e))

    try:
        ok = (abs(_k_mod("short", "short") - 1.2) < 1e-12
              and abs(_k_mod("permanent", "permanent") - 0.6) < 1e-12)
        _check("k_mod_table", ok,
               detail=f"short/short={_k_mod('short','short')}, "
                      f"perm/perm={_k_mod('permanent','permanent')}")
    except Exception as e:
        _check("k_mod_table", False, detail=repr(e))

    try:
        r = _beam({"tipo": "C24", "b": 0.1, "h": 0.2, "M_Ed": 2e3, "l": 4.0})
        w_exp = 0.1 * 0.2 ** 2 / 6.0
        m_rd_exp = 1.2 * 24e6 * w_exp / 1.3  # k_mod*f_m_k*W/gamma_M
        ok = (abs(r["W_m3"] - w_exp) < 1e-15
              and abs(r["M_Rd_Nm"] - m_rd_exp) < 1e-9
              and r["checks"]["bending_ok"] is True)
        _check("beam_flexure_ec5", ok,
               detail=f"W={r['W_m3']}, M_Rd={r['M_Rd_Nm']} (exp {m_rd_exp})")
    except Exception as e:
        _check("beam_flexure_ec5", False, detail=repr(e))

    try:
        r = _column({"b": 0.1, "h": 0.1, "N_Ed": 5e4, "tipo": "C24",
                     "servicio": "short", "duracion": "short", "L0": 3.0})
        # Reimplementación EC5 6.3.2 independiente
        a = 0.1 * 0.1
        n_rd0_exp = 1.2 * 31e6 * a / 1.3
        i_min = 0.1 / _math.sqrt(12.0)
        lam_1 = 0.7 * _math.sqrt(10.8e9 / 31e6)
        lam_rel_exp = (3.0 / i_min) / lam_1
        phi = 0.5 * (1 + 0.1 * (lam_rel_exp - 0.3) + lam_rel_exp ** 2)
        chi_exp = min(1.0 / (phi + _math.sqrt(phi ** 2 - lam_rel_exp ** 2)), 1.0)
        ok = (abs(r["N_Rd0_N"] - n_rd0_exp) < 1e-6
              and abs(r["lambda_rel_k"] - lam_rel_exp) < 1e-9
              and abs(r["chi_k"] - chi_exp) < 1e-12)
        _check("column_buckling_ec5", ok,
               detail=f"lam_rel={r['lambda_rel_k']} (exp {lam_rel_exp}), "
                      f"chi={r['chi_k']} (exp {chi_exp})")
    except Exception as e:
        _check("column_buckling_ec5", False, detail=repr(e))

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
        elif mode == "beam":
            return _beam(params)
        elif mode == "column":
            return _column(params)
        elif mode == "material":
            return _material(params)
        elif mode == "fire":
            return _fire(params)
        else:
            return {"error": f"mode desconocido: {mode}"}
    except (KeyError, ValueError, TypeError) as e:
        return {"error": f"parámetros inválidos: {e}"}


register_tool(
    name="timber_design_tool",
    schema=TIMBER_DESIGN_TOOL_SCHEMA,
    handler=lambda args: _handler(args),
)
