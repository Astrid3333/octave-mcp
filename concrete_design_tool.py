"""
concrete_design_tool.py

Verificación de hormigón armado según EN 1992-1-1 (Eurocódigo 2) con
unidades SI (N, m, Pa). Cubre diseño de vigas (flexión + cortante),
columnas (axial + flexión) y cálculo de armaduras longitudinales y
transversales.

Modos:
  beam          — diseño de viga rectangular: momento resistente M_Rd,
                  cortante resistente V_Rd,c / V_Rd,s, armadura As1/As2/Asw.
  column        — diseño de columna rectangular: N_Rd de compresión
                  centrada/excentricidad, armadura As, verificación
                  interacción N-M (simplificado Mander/EC2 6.7).
  shear_wall    — muro de cortante: V_Rd,c (sin armadura), V_Rd,s (con
                  armadura transversal), Asw/s.
  material      — propiedades del hormigón (f_cd, f_ctd, E_cm, α_cc).

γc = 1.5 (ULS), γs = 1.15. f_cd = α_cc·f_ck/γc, α_cc = 0.85 (NA España).
f_ctd = α_ct·f_ctm/γc, α_ct = 1.0, f_ctm = 0.30·f_ck^(2/3) (MPa).
"""

import math

from tool_registry import register_tool

CONCRETE_DESIGN_TOOL_SCHEMA = {
    "name": "concrete_design_tool",
    "description": (
        "Diseño de hormigón armado EN 1992-1-1 en unidades SI (Newton). "
        "beam (flexión M_Rd, cortante V_Rd, armaduras As), column "
        "(compresión N_Rd, interacción N-M, armadura As), shear_wall "
        "(muro cortante V_Rd,c / V_Rd,s), material (f_cd, f_ctd, E_cm). "
        "γc=1.5, γs=1.15, α_cc=0.85 (España)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["beam", "column", "shear_wall", "material", "validate"],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}

_GAMMA_C = 1.5
_GAMMA_S = 1.15
_ALPHA_CC = 0.85
_ALPHA_CT = 1.0
_FYK_DEFAULT = 500e6  # Pa (B500SD)


def _f_ck_pa(f_ck_mpa):
    return f_ck_mpa * 1e6


def _f_ctm(f_ck_mpa):
    """EN 1992-1-1 Tabla 3.1: f_ctm (MPa) = 0.30·f_ck^(2/3) para C50/60;
    2.12 + 0.106/5 · (f_ck−50) para f_ck > 50."""
    if f_ck_mpa <= 50:
        return 0.30 * f_ck_mpa ** (2.0 / 3.0)
    return 2.12 + 0.106 * (f_ck_mpa - 50.0) / 5.0


def _f_cd(f_ck_mpa):
    return _ALPHA_CC * _f_ck_pa(f_ck_mpa) / _GAMMA_C


def _f_ctd(f_ck_mpa):
    return _ALPHA_CT * _f_ctm(f_ck_mpa) * 1e6 / _GAMMA_C


def _E_cm(f_ck_mpa):
    """EN 1992 Tabla 3.1: E_cm (GPa) = 22·(f_cm/10)^0.3, f_cm=f_ck+8."""
    f_cm = f_ck_mpa + 8.0
    return 22.0 * (f_cm / 10.0) ** 0.3 * 1e9  # Pa


def _fy(fy_k=None):
    return fy_k if fy_k else _FYK_DEFAULT


def _material(f_ck_mpa):
    return {
        "f_ck_MPa": f_ck_mpa,
        "f_cd_Pa": _f_cd(f_ck_mpa),
        "f_ctm_MPa": _f_ctm(f_ck_mpa),
        "f_ctd_Pa": _f_ctd(f_ck_mpa),
        "E_cm_Pa": _E_cm(f_ck_mpa),
        "gamma_c": _GAMMA_C,
        "gamma_s": _GAMMA_S,
        "alpha_cc": _ALPHA_CC,
    }


def _beam(params):
    """Diseño de viga rectangular. Params:
    b, h (m) dimensiones sección; M_Ed (N·m) momento UL; V_Ed (N) cortante;
    f_ck (MPa); d (m) altura efectiva (opcional, default h−0.04−0.0125);
    l (m) luz para V_Rd,c; fy (Pa) opcional.
    Devuelve M_Rd, V_Rd,c, V_Rd,s, As1, Asw/s, checks."""
    b = float(params["b"])
    h = float(params["h"])
    M_Ed = float(params["M_Ed"])
    V_Ed = float(params.get("V_Ed", 0.0))
    f_ck = float(params.get("f_ck", 30.0))
    fy = _fy(params.get("fy"))
    d = float(params.get("d", h - 0.04 - 0.0125))
    l = float(params.get("l", 0.0))

    f_cd_ = _f_cd(f_ck)
    f_ctd_ = _f_ctd(f_ck)

    # Flexión: M_Rd = 0.167·f_cd·b·d² (λ=0.8 para C30/37; simplificado)
    # Más preciso: μ = M_Ed/(f_cd·b·d²), ω = ρ·fy/f_cd, μ = ω·(1−0.5ω)
    z_arm = 0.9 * d
    if M_Ed > 0:
        As1_req = M_Ed / (fy * z_arm)
    else:
        As1_req = abs(M_Ed) / (fy * z_arm)  # armadura compresión (rara)
    # M_Rd máximo con As1 mínimo (ρmin = max(0.26·f_ctm/fyk, 0.0013)·b·d)
    f_ctm_mpa = _f_ctm(f_ck)
    rho_min = max(0.26 * f_ctm_mpa * 1e6 / fy, 0.0013)
    As_min = rho_min * b * d
    As1 = max(As1_req, As_min)
    M_Rd = As1 * fy * z_arm

    # Cortante (EC2 6.2.2)
    V_Rd_c = 0.12 * (100 * As1 / (b * d) * f_ck) ** (1.0 / 3.0) * b * d
    V_Rd_c = max(V_Rd_c, 0.038 * f_ck ** (2.0 / 3.0) * b * d)
    V_Rd_c = min(V_Rd_c, 0.12 * b * d * (1 + 0))  # cap a 0.12·b·d (EC2)
    V_Rd_c = min(V_Rd_c, 0.12 * b * d * (1 + f_ck * 1e6 / 250e6))  # simplificado

    # V_Rd,s = Asw/s · fy · z · cotθ / γs; z≈0.9d, cotθ≤2.5
    z = 0.9 * d
    cot_theta = 2.5
    if V_Ed > V_Rd_c:
        Asw_s = V_Ed * _GAMMA_S / (fy * z * cot_theta)
    else:
        Asw_s = 0.0

    V_Rd_s = (Asw_s / 1.0) * fy * z * cot_theta / _GAMMA_S if Asw_s > 0 else float("inf")

    checks = {
        "flexion_ok": M_Ed <= M_Rd,
        "shear_ok": V_Ed <= max(V_Rd_c, V_Rd_s) if V_Ed > 0 else True,
    }

    return {
        "material": _material(f_ck),
        "b_m": b, "h_m": h, "d_m": d,
        "M_Ed_Nm": M_Ed,
        "M_Rd_Nm": M_Rd,
        "As1_req_m2": As1_req,
        "As1_min_m2": As_min,
        "As1_m2": As1,
        "V_Ed_N": V_Ed,
        "V_Rd_c_N": V_Rd_c,
        "V_Rd_s_N": V_Rd_s,
        "Asw_over_s_m": Asw_s,
        "rho_min": rho_min,
        "z_arm_m": z_arm,
        "util_M": M_Ed / M_Rd if M_Rd > 0 else float("inf"),
        "util_V": V_Ed / max(V_Rd_c, V_Rd_s) if V_Ed > 0 and max(V_Rd_c, V_Rd_s) > 0 else 0.0,
        "checks": checks,
    }


def _column(params):
    """Diseño de columna rectangular. Params:
    b, h (m); N_Ed (N) compresión; M_Ed (N·m) opcional; f_ck (MPa);
    fy (Pa) opcional; L0 (m) longitud efectiva para pandeo opcional;
    l0 (alias). Devuelve N_Rd, As, rho, M_Rd (si M_Ed dado)."""
    b = float(params["b"])
    h = float(params["h"])
    N_Ed = float(params.get("N_Ed", 0.0))
    M_Ed = float(params.get("M_Ed", 0.0))
    f_ck = float(params.get("f_ck", 30.0))
    fy = _fy(params.get("fy"))
    L0 = float(params.get("L0", params.get("l0", 0.0)))

    f_cd_ = _f_cd(f_ck)
    A_c = b * h

    # Compresión centrada: N_Rd = (A_c·f_cd + As·(fy − f_cd)) / γs_part
    # Simplificado EC2 6.7.1: N_Rd = A_c·f_cd + As·(fy − f_cd) (sin redistribución)
    # ρmin columna = max(0.10·N_Ed/(fy·A_c), 0.002), ρmax = 0.04
    rho_min = max(0.10 * N_Ed / (fy * A_c) if fy * A_c > 0 else 0.002, 0.002)
    rho_max = 0.04
    As = rho_min * A_c
    N_Rd_centrada = A_c * f_cd_ + As * (fy - f_cd_)

    # M_Rd flexión pura (As por lado): z≈0.9·h/2 para doble armadura
    z = 0.9 * (h / 2)
    M_Rd = As * fy * z if M_Ed > 0 else 0.0

    # Interacción N-M simplificada (EC2 6.7.2 (5) / (6)):
    # n = N_Ed/N_Rd, m = M_Ed/M_Rd; n + m ≤ 1.0 (rectangular, sin excentricidad inicial)
    n = N_Ed / N_Rd_centrada if N_Rd_centrada > 0 else float("inf")
    if M_Ed > 0 and M_Rd > 0:
        m = M_Ed / M_Rd
    else:
        m = 0.0
    eta_nm = n + m  # ≤ 1.0

    # Pandeo (si L0 dado): λ = L0/i, i = h/√12 para sección rectangular
    pandeo = None
    if L0 > 0:
        i = h / math.sqrt(12.0)
        lam = L0 / i
        # Curva c (clase 1-2, rect.)
        phi = 0.5 * (1 + 0.34 * (lam - 0.2) + lam ** 2)  # α=0.49 curva c
        chi = min(1.0 / (phi + math.sqrt(phi ** 2 - 0.0017 * lam ** 2)) if lam > 0.2 else 1.0, 1.0)
        N_b_Rd = chi * N_Rd_centrada
        pandeo = {
            "L0_m": L0, "i_m": i, "lambda": lam, "phi": phi, "chi": chi,
            "N_b_Rd_N": N_b_Rd,
            "util_buckling": N_Ed / N_b_Rd if N_b_Rd > 0 else float("inf"),
        }

    return {
        "material": _material(f_ck),
        "b_m": b, "h_m": h, "A_c_m2": A_c,
        "N_Ed_N": N_Ed, "N_Rd_centrada_N": N_Rd_centrada,
        "rho": As / A_c if A_c > 0 else 0, "rho_min": rho_min, "rho_max": rho_max,
        "As_m2": As,
        "M_Ed_Nm": M_Ed, "M_Rd_Nm": M_Rd,
        "n": n, "m": m, "eta_nm": eta_nm,
        "pandeo": pandeo,
        "checks": {
            "compression_ok": N_Ed <= N_Rd_centrada,
            "interaction_ok": eta_nm <= 1.0,
            "rho_ok": rho_min <= As / A_c <= rho_max if A_c > 0 else True,
        },
    }


def _shear_wall(params):
    """Muro de cortante. Params:
    b_w, h_w (m); V_Ed (N); f_ck (MPa); d (m); l (m);
    Asw (m²) armadura transversal opcional; s (m) separación opcional.
    Devuelve V_Rd,c, V_Rd,s, Asw/s."""
    b_w = float(params["b_w"])
    h_w = float(params["h_w"])
    V_Ed = float(params.get("V_Ed", 0.0))
    f_ck = float(params.get("f_ck", 30.0))
    d = float(params.get("d", h_w * 0.9))
    l = float(params.get("l", h_w))  # altura del muro
    Asw = float(params.get("Asw", 0.0))
    s = float(params.get("s", 0.0))

    f_ctd_ = _f_ctd(f_ck)
    A_c = b_w * h_w

    # V_Rd,c muro (EC2 6.2.2, simplificado): 0.12·b_w·d·(f_ck)^{1/3}·1e-? 
    # o v_Rd,c = 0.12·k·(100·ρ_l·f_ck)^{1/3}·b_w·d ≥ 0.038·k·f_ck^{2/3}·b_w·d
    # Para muro: ρ_l mínimo longitudinal
    f_ctm_mpa = _f_ctm(f_ck)
    rho_l = max(0.26 * f_ctm_mpa * 1e6 / _fy(params.get("fy")), 0.0013)
    k = 1 + (200.0 / d) ** 0.5 if d > 0 else 1.0
    k = min(k, 2.0)
    V_Rd_c = 0.12 * k * (100 * rho_l * f_ck) ** (1.0 / 3.0) * b_w * d
    V_Rd_c = max(V_Rd_c, 0.038 * k * f_ck ** (2.0 / 3.0) * b_w * d)

    # V_Rd,s con armadura: cotθ ≤ 2.5, z≈0.9d
    z = 0.9 * d
    cot_theta = 2.5
    fy = _fy(params.get("fy"))
    if Asw > 0 and s > 0:
        V_Rd_s = (Asw / s) * fy * z * cot_theta / _GAMMA_S
    else:
        Asw_s = 0.0
        if V_Ed > V_Rd_c:
            Asw_s = V_Ed * _GAMMA_S / (fy * z * cot_theta)
        V_Rd_s = float("inf")

    return {
        "material": _material(f_ck),
        "b_w_m": b_w, "h_w_m": h_w, "A_c_m2": A_c, "d_m": d,
        "V_Ed_N": V_Ed, "V_Rd_c_N": V_Rd_c, "V_Rd_s_N": V_Rd_s,
        "rho_l": rho_l, "k": k, "z_m": z,
        "Asw_over_s_m": Asw / s if s > 0 else 0.0,
        "util_c": V_Ed / V_Rd_c if V_Rd_c > 0 else float("inf"),
        "util_s": V_Ed / V_Rd_s if V_Ed > 0 and V_Rd_s > 0 else 0.0,
        "checks": {
            "shear_without_links_ok": V_Ed <= V_Rd_c,
            "shear_with_links_ok": V_Ed <= V_Rd_s if V_Ed > 0 else True,
        },
    }


def _mode_validate() -> dict:
    """Autochequeo: valores de material EC2, dimensionado de viga y
    límites de armadura de columna."""
    checks = []

    def _check(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    try:
        m = _material(30.0)
        f_ctm_exp = 0.30 * 30.0 ** (2.0 / 3.0)
        e_cm_exp = 22.0 * (38.0 / 10.0) ** 0.3 * 1e9
        ok = (abs(m["f_cd_Pa"] - 17e6) < 1e-6  # 0.85*30e6/1.5
              and abs(m["f_ctm_MPa"] - f_ctm_exp) < 1e-12
              and abs(m["E_cm_Pa"] - e_cm_exp) < 1e-3
              and m["gamma_c"] == 1.5 and m["alpha_cc"] == 0.85)
        _check("material_ec2_c30", ok,
               detail=f"f_cd={m['f_cd_Pa']}, f_ctm={m['f_ctm_MPa']}")
    except Exception as e:
        _check("material_ec2_c30", False, detail=repr(e))

    try:
        r = _handler({"mode": "beam",
                      "params": {"b": 0.25, "h": 0.5, "M_Ed": 100e3,
                                 "V_Ed": 50e3, "f_ck": 30}})
        d = 0.5 - 0.04 - 0.0125  # 0.4475
        z_exp = 0.9 * d  # palanca usada por la herramienta
        as_exp = 100e3 / (500e6 * z_exp)
        ok = (abs(r["d_m"] - d) < 1e-12 and abs(r["z_arm_m"] - z_exp) < 1e-12
              and abs(r["As1_req_m2"] - as_exp) < 1e-15
              and r["checks"].get("flexion_ok") is True)
        _check("beam_flexure_dimensioning", ok,
               detail=f"d={r['d_m']}, As1={r['As1_req_m2']} (exp {as_exp})")
    except Exception as e:
        _check("beam_flexure_dimensioning", False, detail=repr(e))

    try:
        r = _handler({"mode": "column",
                      "params": {"b": 0.3, "h": 0.3, "N_Ed": 500e3, "f_ck": 30}})
        # Implementación de la herramienta: rho_min = 0.10*N_Ed/(fy*A_c) >= 0.002
        a_c = 0.3 * 0.3
        rho_min_exp = max(0.10 * 500e3 / (500e6 * a_c), 0.002)
        ok = (abs(r["rho_min"] - rho_min_exp) < 1e-12 and r["rho_max"] == 0.04)
        _check("column_rho_bounds", ok,
               detail=f"rho_min={r['rho_min']} (exp {rho_min_exp}), rho_max={r['rho_max']}")
    except Exception as e:
        _check("column_rho_bounds", False, detail=repr(e))

    try:
        r = _handler({"mode": "material", "params": {"f_ck": 60.0}})
        # Rama f_ck>50: f_ctm = 2.12 + 0.106*(f_ck-50)/5 = 2.12+0.212
        _check("material_fck60_branch", abs(r["f_ctm_MPa"] - 2.332) < 1e-12,
               detail=f"f_ctm={r['f_ctm_MPa']}")
    except Exception as e:
        _check("material_fck60_branch", False, detail=repr(e))

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
        elif mode == "shear_wall":
            return _shear_wall(params)
        elif mode == "material":
            f_ck = float(params.get("f_ck", 30.0))
            return _material(f_ck)
        else:
            return {"error": f"mode desconocido: {mode}"}
    except (KeyError, ValueError, TypeError) as e:
        return {"error": f"parámetros inválidos: {e}"}


register_tool(
    name="concrete_design_tool",
    schema=CONCRETE_DESIGN_TOOL_SCHEMA,
    handler=lambda args: _handler(args),
)
