"""
soil_foundation_tool.py

Mecánica de suelos para cimentaciones: capacidad de carga (Terzaghi con
factores de Vesic, cimentación corrida) y asentamiento por consolidación 1D
(arcilla normalmente consolidada y sobreconsolidada).

Unidades: kPa, kN/m³, m. Mismo patrón que los demás módulos:
compute + _handler + register_tool(name, schema, handler).

Modos: bearing_capacity, settlement_1d, validate.
Enlace con soil_mechanics_tool: lambda (Cam-Clay) -> Cc = lambda * ln(10).
"""

import math

from tool_registry import register_tool

LN10 = math.log(10.0)

SOIL_FOUNDATION_TOOL_SCHEMA = {
    "name": "soil_foundation_tool",
    "description": (
        "Cimentaciones en suelo: capacidad de carga última de cimentación corrida "
        "(Terzaghi con factores de Vesic) y asentamiento por consolidación 1D "
        "(NC y sobreconsolidada, o con lambda de Cam-Clay). SI con kPa, kN/m³, m. "
        "Modos: bearing_capacity, settlement_1d, validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string",
                     "enum": ["bearing_capacity", "settlement_1d", "validate"]},
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


# ------------------------------------------------------------ bearing capacity
def bearing_factors(phi_deg):
    """
    Factores Nc, Nq, Ngamma (Vesic, usados en Das):
      Nq = e^(pi*tan phi) * tan²(45 + phi/2)
      Nc = (Nq - 1) * cot phi       (phi > 0);  Nc = 5.14 para phi = 0
      Ngamma = 2*(Nq + 1)*tan phi
    """
    if not (0.0 <= phi_deg < 60.0):
        raise ValueError("phi_deg debe estar en [0, 60)")
    phi = math.radians(phi_deg)
    nq = math.exp(math.pi * math.tan(phi)) * math.tan(math.radians(45.0) + phi / 2.0) ** 2
    if phi_deg == 0.0:
        nc = 5.14
        ng = 0.0
    else:
        nc = (nq - 1.0) / math.tan(phi)
        ng = 2.0 * (nq + 1.0) * math.tan(phi)
    return {"Nc": nc, "Nq": nq, "Ngamma": ng}


def bearing_capacity_strip(c_kpa, phi_deg, gamma_kn_m3, width_m, depth_m):
    """
    q_ult = c*Nc + q*Nq + 0.5*gamma*B*Ngamma, con q = gamma*Df.
    Cimentación corrida, sin factores de forma ni de profundidad.
    """
    if width_m <= 0 or depth_m < 0:
        raise ValueError("width_m > 0 y depth_m >= 0")
    f = bearing_factors(phi_deg)
    q = gamma_kn_m3 * depth_m
    q_ult = c_kpa * f["Nc"] + q * f["Nq"] + 0.5 * gamma_kn_m3 * width_m * f["Ngamma"]
    return {"factors": f, "overburden_kpa": q, "q_ult_kpa": q_ult}


# ------------------------------------------------------------- settlement 1D
def cc_from_lambda(lam):
    """Cc (log10) a partir de lambda (ln) de Cam-Clay: Cc = lambda*ln(10)."""
    return lam * LN10


def settlement_1d(h_m, e0, sigma0_kpa, delta_sigma_kpa, cc=None, cs=None,
                  pc_kpa=None, lam=None):
    """
    Asentamiento primario por consolidación 1D.
      NC (o sigma_f <= pc):  S = Cc*H/(1+e0) * log10((s0+ds)/s0)
      OC cruzando pc:        S = Cs*H/(1+e0) * log10(pc/s0)
                              + Cc*H/(1+e0) * log10((s0+ds)/pc)
    Si se da lam y no cc, Cc = lam*ln(10).
    """
    if cc is None:
        if lam is None:
            raise ValueError("falta cc o lam")
        cc = cc_from_lambda(lam)
    if h_m <= 0 or e0 < 0 or sigma0_kpa <= 0 or delta_sigma_kpa < 0:
        raise ValueError("h_m > 0, e0 >= 0, sigma0 > 0, delta_sigma >= 0")
    sf = sigma0_kpa + delta_sigma_kpa
    k = h_m / (1.0 + e0)
    if pc_kpa is None or sf <= pc_kpa:
        if pc_kpa is not None and cs is not None and sf <= pc_kpa:
            s = cs * k * math.log10(sf / sigma0_kpa)
        else:
            s = cc * k * math.log10(sf / sigma0_kpa)
        branch = "NC_o_recompresion"
    else:
        if cs is None:
            raise ValueError("sigma_f supera pc: falta cs (indice de recompresion)")
        s = cs * k * math.log10(pc_kpa / sigma0_kpa) + cc * k * math.log10(sf / pc_kpa)
        branch = "OC_cruza_pc"
    return {"settlement_m": s, "Cc": cc, "branch": branch, "sigma_final_kpa": sf}


# ----------------------------------------------------------------- handlers
def _mode_bearing(p):
    return bearing_capacity_strip(p["c_kpa"], p["phi_deg"], p["gamma_kn_m3"],
                                  p["width_m"], p["depth_m"])


def _mode_settlement(p):
    return settlement_1d(p["h_m"], p["e0"], p["sigma0_kpa"], p["delta_sigma_kpa"],
                         cc=p.get("cc"), cs=p.get("cs"), pc_kpa=p.get("pc_kpa"),
                         lam=p.get("lambda"))


def _mode_validate():
    checks = []

    def chk(name, ok, detail=""):
        checks.append({"name": name, "passed": bool(ok), "detail": detail})

    # 1. Factores Vesic en phi=30 (tabla de Das)
    f30 = bearing_factors(30.0)
    chk("Nq(30) = 18.40", abs(f30["Nq"] - 18.40) < 0.01, f"{f30['Nq']:.3f}")
    chk("Nc(30) = 30.14", abs(f30["Nc"] - 30.14) < 0.01, f"{f30['Nc']:.3f}")
    chk("Ngamma(30) = 22.40", abs(f30["Ngamma"] - 22.40) < 0.02, f"{f30['Ngamma']:.3f}")

    # 2. phi=0: Nq=1, Nc=5.14, Ngamma=0
    f0 = bearing_factors(0.0)
    chk("phi=0: Nq=1", abs(f0["Nq"] - 1.0) < 1e-12)
    chk("phi=0: Nc=5.14", abs(f0["Nc"] - 5.14) < 1e-12)

    # 3. Cohesivo puro: q_ult = c*Nc + gamma*Df*Nq (phi=0, sin término gamma*B)
    r = bearing_capacity_strip(20.0, 0.0, 18.0, 2.0, 1.0)
    chk("phi=0 q_ult = c*5.14 + gamma*Df",
        abs(r["q_ult_kpa"] - (20.0 * 5.14 + 18.0 * 1.0)) < 1e-9,
        f"q_ult={r['q_ult_kpa']:.3f}")

    # 4. Friccionante sin cohesión ni sobrecarga: q_ult = 0.5*gamma*B*Ngamma
    r4 = bearing_capacity_strip(0.0, 30.0, 18.0, 2.0, 0.0)
    chk("solo gamma*B", abs(r4["q_ult_kpa"] - 0.5 * 18.0 * 2.0 * 22.40) < 0.05,
        f"q_ult={r4['q_ult_kpa']:.3f}")

    # 5. Asentamiento NC: Cc=0.3, H=2, e0=1, s0=100, ds=100 -> 0.3*2/2*log10(2)
    s5 = settlement_1d(2.0, 1.0, 100.0, 100.0, cc=0.3)
    want5 = 0.3 * 2.0 / 2.0 * math.log10(2.0)
    chk("settlement NC", abs(s5["settlement_m"] - want5) < 1e-12,
        f"S={s5['settlement_m']:.5f} m")

    # 6. Conversión lambda -> Cc: mismo resultado que con Cc=0.3
    s6 = settlement_1d(2.0, 1.0, 100.0, 100.0, lam=0.3 / LN10)
    chk("lambda -> Cc", abs(s6["settlement_m"] - want5) < 1e-12)

    # 7. OC con pc = s0 reduce al caso NC
    s7 = settlement_1d(2.0, 1.0, 100.0, 100.0, cc=0.3, cs=0.05, pc_kpa=100.0)
    chk("OC con pc=s0 = NC", abs(s7["settlement_m"] - want5) < 1e-12)

    # 8. Sobreconsolidada completa (sf <= pc): solo recompresión
    s8 = settlement_1d(2.0, 1.0, 100.0, 50.0, cc=0.3, cs=0.05, pc_kpa=300.0)
    want8 = 0.05 * 2.0 / 2.0 * math.log10(150.0 / 100.0)
    chk("recompresión sf<=pc", abs(s8["settlement_m"] - want8) < 1e-12,
        f"S={s8['settlement_m']:.5f}")

    passed = sum(c["passed"] for c in checks)
    return {"checks": checks, "total_passed": passed, "total_checks": len(checks),
            "validation_passed": passed == len(checks)}


_MODES = {"bearing_capacity": _mode_bearing, "settlement_1d": _mode_settlement}


def _handler(args):
    mode = args.get("mode")
    params = args.get("params") or {}
    try:
        if mode == "validate":
            return _mode_validate()
        if mode in _MODES:
            return {"mode": mode, "result": _MODES[mode](params)}
        return {"error": f"mode desconocido: {mode}"}
    except (KeyError, ValueError, TypeError, ZeroDivisionError) as e:
        return {"error": f"parámetros inválidos: {e}"}


register_tool(
    name="soil_foundation_tool",
    schema=SOIL_FOUNDATION_TOOL_SCHEMA,
    handler=_handler,
)
