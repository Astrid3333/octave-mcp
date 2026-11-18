"""
hydraulic_network_tool.py

Hidráulica de tuberías: fricción (Darcy-Weisbach con Colebrook / Swamee-Jain),
pérdidas menores (K, Borda), Hazen-Williams, red de tuberías (análisis nodal
con Newton) y punto de operación de bomba. SI: m, m³/s, Pa, kg/m³.

Mismo patrón que materials_db_tool / conductor_losses_tool:
compute + _handler + register_tool(name, schema, handler).
Python puro (math) + numpy solo para la red.

Modos: friction, minor_losses, hazen_williams, network, pump, validate.
"""

import math

import numpy as np

from tool_registry import register_tool

G = 9.80665
RHO_WATER = 998.2        # kg/m³, agua a 20 °C
MU_WATER = 1.002e-3      # Pa·s, agua a 20 °C
HW_N = 1.852             # exponente Hazen-Williams

HYDRAULIC_NETWORK_TOOL_SCHEMA = {
    "name": "hydraulic_network_tool",
    "description": (
        "Hidráulica de tuberías en SI: Darcy-Weisbach (Colebrook, Swamee-Jain), "
        "pérdidas menores y Borda, Hazen-Williams, red de tuberías por análisis "
        "nodal y punto de operación de bomba. "
        "Modos: friction, minor_losses, hazen_williams, network, pump, validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["friction", "minor_losses", "hazen_williams",
                         "network", "pump", "validate"],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


# ------------------------------------------------------------------ friction
def reynolds(velocity, diameter, rho=RHO_WATER, mu=MU_WATER):
    """Re = rho*v*D/mu."""
    return rho * velocity * diameter / mu


def friction_colebrook(re, rel_roughness):
    """
    Factor de Darcy f por Colebrook-White (implícita), resuelta por bisección
    sobre x = 1/sqrt(f):  x + 2*log10(eps/(3.7D) + 2.51*x/Re) = 0.
    Laminar (Re < 2300): f = 64/Re.
    """
    if re <= 0:
        raise ValueError("Re debe ser > 0")
    if re < 2300.0:
        return 64.0 / re
    a = rel_roughness / 3.7
    b = 2.51 / re

    def g(x):
        return x + 2.0 * math.log10(a + b * x)

    lo, hi = 1e-3, 1000.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if g(mid) > 0:
            hi = mid
        else:
            lo = mid
    x = 0.5 * (lo + hi)
    return 1.0 / (x * x)


def friction_swamee_jain(re, rel_roughness):
    """Aproximación explícita de Swamee-Jain (5e3 < Re < 1e8, 1e-6 < eps/D < 1e-2)."""
    if re < 2300.0:
        return 64.0 / re
    return 0.25 / (math.log10(rel_roughness / 3.7 + 5.74 / re ** 0.9)) ** 2


def darcy_head_loss(f, length, diameter, velocity):
    """h_f = f*(L/D)*v²/(2g) [m]."""
    return f * (length / diameter) * velocity ** 2 / (2.0 * G)


def pipe_friction(flow_m3s, diameter, length, roughness_m,
                  rho=RHO_WATER, mu=MU_WATER):
    """Pérdida por fricción completa a partir de caudal."""
    area = math.pi * diameter ** 2 / 4.0
    v = flow_m3s / area
    re = reynolds(abs(v), diameter, rho, mu)
    rel = roughness_m / diameter
    f_c = friction_colebrook(re, rel)
    f_sj = friction_swamee_jain(re, rel)
    return {"velocity_ms": v, "Re": re, "f_colebrook": f_c, "f_swamee_jain": f_sj,
            "h_f_m": darcy_head_loss(f_c, length, diameter, abs(v)),
            "dP_Pa": rho * G * darcy_head_loss(f_c, length, diameter, abs(v))}


# ------------------------------------------------------------ minor losses
def minor_loss_head(k_factor, velocity):
    """h_m = K*v²/(2g) [m]."""
    return k_factor * velocity ** 2 / (2.0 * G)


def borda_expansion_head(v1, d1, d2):
    """Ensanchamiento brusco (Borda): h = (v1 - v2)²/(2g), v2 = v1*(D1/D2)²."""
    v2 = v1 * (d1 / d2) ** 2
    return (v1 - v2) ** 2 / (2.0 * G)


# ------------------------------------------------------------- Hazen-Williams
def hazen_williams_k(length, c_factor, diameter):
    """Coeficiente K tal que h_f = K*Q^1.852 (SI): K = 10.67*L/(C^1.852*D^4.87)."""
    return 10.67 * length / (c_factor ** HW_N * diameter ** 4.87)


def hazen_williams_head(flow_m3s, length, c_factor, diameter):
    """h_f = K*Q^1.852 [m]."""
    return hazen_williams_k(length, c_factor, diameter) * flow_m3s ** HW_N


# ----------------------------------------------------------------- network
def _pipe_flow(dh, k, n):
    """Caudal en tubería con pérdida h = K*|Q|^n*sign(Q): Q = sign(dH)*(|dH|/K)^(1/n)."""
    if dh == 0.0:
        return 0.0
    return math.copysign((abs(dh) / k) ** (1.0 / n), dh)


def solve_network(fixed_heads, free_nodes, pipes, demands, max_iter=100, tol=1e-10):
    """
    fixed_heads: {nodo: H} nodos con carga fija (embalses).
    free_nodes:  lista de nodos con carga incógnita.
    pipes:       [{"a": nodo, "b": nodo, "K": K, "n": n}] con h = K*|Q|^n.
    demands:     {nodo: q} caudal que sale de la red en ese nodo [m³/s].
    Devuelve cargas, caudales por tubería y balance de continuidad.
    """
    idx = {nd: i for i, nd in enumerate(free_nodes)}
    h_guess = np.array([np.mean(list(fixed_heads.values())) for _ in free_nodes], dtype=float)
    all_h = dict(fixed_heads)

    def heads_of(hv):
        d = dict(fixed_heads)
        for nd, i in idx.items():
            d[nd] = hv[i]
        return d

    def residual(hv):
        h = heads_of(hv)
        r = np.zeros(len(free_nodes))
        for p in pipes:
            q = _pipe_flow(h[p["a"]] - h[p["b"]], p["K"], p["n"])  # a -> b
            if p["a"] in idx:
                r[idx[p["a"]]] -= q   # sale de a
            if p["b"] in idx:
                r[idx[p["b"]]] += q   # entra a b
        for nd, i in idx.items():
            r[i] -= demands.get(nd, 0.0)  # demanda que sale de la red
        return r

    hv = h_guess.copy()
    for _ in range(max_iter):
        r = residual(hv)
        if np.max(np.abs(r)) < tol:
            break
        jac = np.zeros((len(free_nodes), len(free_nodes)))
        eps = 1e-7
        for j in range(len(free_nodes)):
            dhv = hv.copy()
            dhv[j] += eps
            jac[:, j] = (residual(dhv) - r) / eps
        step = np.linalg.solve(jac, -r)
        hv = hv + step
    h = heads_of(hv)
    flows = [{"a": str(p["a"]), "b": str(p["b"]),
              "Q_m3s": float(_pipe_flow(h[p["a"]] - h[p["b"]], p["K"], p["n"]))}
             for p in pipes]
    residual_max = float(np.max(np.abs(residual(hv)))) if free_nodes else 0.0
    return {"heads": {str(k): float(v) for k, v in h.items()},
            "pipe_flows": flows,
            "max_continuity_error": residual_max,
            "converged": residual_max < 1e-8}


# -------------------------------------------------------------------- pump
def pump_operating_point(h0, a_coef, static_head, k_sys, n_sys=HW_N, q_max=None):
    """
    Bomba: H_p(Q) = h0 - a*Q²; sistema: H_s(Q) = static + K*Q^n.
    Intersección por bisección. Potencia hidráulica P = rho*g*Q*H.
    """
    def f(q):
        return (h0 - a_coef * q * q) - (static_head + k_sys * q ** n_sys)

    lo = 0.0
    hi = q_max if q_max is not None else math.sqrt(max(h0, 1e-12) / a_coef)
    if f(lo) < 0:
        raise ValueError("la bomba no alcanza la altura estática")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    q = 0.5 * (lo + hi)
    head = static_head + k_sys * q ** n_sys
    p_hyd = RHO_WATER * G * q * head
    return {"Q_m3s": q, "H_m": head, "P_hydraulic_w": p_hyd,
            "P_hydraulic_hp": p_hyd / 745.6998715822702}


# ----------------------------------------------------------------- handlers
def _mode_friction(p):
    return pipe_friction(p["flow_m3s"], p["diameter_m"], p["length_m"],
                         p.get("roughness_m", 1.5e-6),
                         p.get("rho", RHO_WATER), p.get("mu", MU_WATER))


def _mode_minor(p):
    out = {}
    if "K" in p and "velocity_ms" in p:
        out["h_m_minor_m"] = minor_loss_head(p["K"], p["velocity_ms"])
    if all(k in p for k in ("velocity1_ms", "d1_m", "d2_m")):
        out["h_borda_m"] = borda_expansion_head(p["velocity1_ms"], p["d1_m"], p["d2_m"])
    return out


def _mode_hazen(p):
    return {"K_hw": hazen_williams_k(p["length_m"], p["c_factor"], p["diameter_m"]),
            "h_f_m": hazen_williams_head(p["flow_m3s"], p["length_m"],
                                         p["c_factor"], p["diameter_m"])}


def _mode_network(p):
    return solve_network(p["fixed_heads"], p["free_nodes"], p["pipes"],
                         p.get("demands", {}))


def _mode_pump(p):
    return pump_operating_point(p["h0_m"], p["a_coef"], p["static_head_m"],
                                p["k_sys"], p.get("n_sys", HW_N), p.get("q_max"))


_MODES = {"friction": _mode_friction, "minor_losses": _mode_minor,
          "hazen_williams": _mode_hazen, "network": _mode_network, "pump": _mode_pump}


def _mode_validate():
    checks = []

    def chk(name, ok, detail=""):
        checks.append({"name": name, "passed": bool(ok), "detail": detail})

    # 1. Laminar: f = 64/Re exacto
    chk("laminar f=64/Re", abs(friction_colebrook(1000.0, 0.01) - 0.064) < 1e-12)

    # 2. Colebrook satisface su propia ecuación (residual < 1e-8)
    re, rel = 1e5, 1e-4
    f = friction_colebrook(re, rel)
    res = 1 / math.sqrt(f) + 2 * math.log10(rel / 3.7 + 2.51 / (re * math.sqrt(f)))
    chk("Colebrook residual", abs(res) < 1e-8, f"residual={res:.2e}")

    # 3. Swamee-Jain vs Colebrook, dentro de 2 %
    fsj = friction_swamee_jain(re, rel)
    chk("Swamee-Jain ~ Colebrook (2%)", abs(fsj - f) / f < 0.02,
        f"Colebrook={f:.5f} SJ={fsj:.5f}")

    # 4. Darcy: h_f = f*L/D*v²/2g con valores simples (f=0.02, L=100, D=0.1, v=2)
    hf = darcy_head_loss(0.02, 100.0, 0.1, 2.0)
    chk("Darcy-Weisbach", abs(hf - 0.02 * 1000 * 4 / (2 * G)) < 1e-12)

    # 5. Borda: D1=0.2 -> D2=0.4, v1=1 -> v2=0.25, h=(0.75)²/2g
    chk("Borda", abs(borda_expansion_head(1.0, 0.2, 0.4) - 0.75 ** 2 / (2 * G)) < 1e-12)

    # 6. Hazen-Williams: h ∝ Q^1.852 (escala)
    h1 = hazen_williams_head(0.01, 100, 130, 0.1)
    h2 = hazen_williams_head(0.02, 100, 130, 0.1)
    chk("Hazen Q^1.852", abs(h2 / h1 - 2 ** HW_N) < 1e-9, f"ratio={h2/h1:.6f}")

    # 7. Red: reservorio 100 m, pipe K=10 n=2, demanda 2 m³/s -> H_N = 100 - 40
    r7 = solve_network({"R": 100.0}, ["N"], [{"a": "R", "b": "N", "K": 10.0, "n": 2.0}],
                       {"N": 2.0})
    chk("network una tubería", abs(r7["heads"]["N"] - 60.0) < 1e-6,
        f"H_N={r7['heads']['N']:.6f}")

    # 8. Red: dos tuberías iguales en paralelo, demanda 2 -> 1 por tubería, H_N = 90
    r8 = solve_network({"R": 100.0}, ["N"],
                       [{"a": "R", "b": "N", "K": 10.0, "n": 2.0},
                        {"a": "R", "b": "N", "K": 10.0, "n": 2.0}],
                       {"N": 2.0})
    chk("network paralelo reparto simétrico", abs(r8["heads"]["N"] - 90.0) < 1e-6,
        f"H_N={r8['heads']['N']:.6f}")

    # 9. Continuidad: caudal que sale del embalse = demanda total
    out_res = sum(f["Q_m3s"] for f in r8["pipe_flows"] if f["a"] == "R")
    chk("continuidad global", abs(out_res - 2.0) < 1e-6, f"salida={out_res:.6f}")

    # 10. Bomba n=2: Q* = sqrt((h0-Hs)/(a+K))
    h0, a, hs, k = 50.0, 0.5, 10.0, 2.0
    pump = pump_operating_point(h0, a, hs, k, n_sys=2.0)
    q_exact = math.sqrt((h0 - hs) / (a + k))
    chk("bomba punto de operación", abs(pump["Q_m3s"] - q_exact) < 1e-9,
        f"Q={pump['Q_m3s']:.6f} exacto={q_exact:.6f}")

    passed = sum(c["passed"] for c in checks)
    return {"checks": checks, "total_passed": passed, "total_checks": len(checks),
            "validation_passed": passed == len(checks)}


def _handler(args):
    mode = args.get("mode")
    params = args.get("params") or {}
    try:
        if mode == "validate":
            return _mode_validate()
        if mode in _MODES:
            return {"mode": mode, "result": _MODES[mode](params)}
        return {"error": f"mode desconocido: {mode}"}
    except (KeyError, ValueError, TypeError, ZeroDivisionError, np.linalg.LinAlgError) as e:
        return {"error": f"parámetros inválidos: {e}"}


register_tool(
    name="hydraulic_network_tool",
    schema=HYDRAULIC_NETWORK_TOOL_SCHEMA,
    handler=_handler,
)
