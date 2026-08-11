"""
gas_tool.py
Matematica de gases para octave-mcp.
Sigue el patron: compute_gas(mode, params) + GAS_TOOL_SCHEMA
Integrar en server.py:
  - import: from gas_tool import compute_gas, GAS_TOOL_SCHEMA
  - dispatcher: elif tool_name == "gas_tool": result = compute_gas(params.get("mode"), params.get("params"))
  - schema list: agregar GAS_TOOL_SCHEMA a TOOLS
"""

import math

R = 8.314462618  # J/(mol*K)

# ---------------------------------------------------------------------------
# Modo: ideal
# ---------------------------------------------------------------------------
def _mode_ideal(p):
    """
    PV = nRT. Provee exactamente 3 de {P (Pa), V (m3), n (mol), T (K)},
    calcula la faltante. Tambien devuelve densidad si se da masa molar M (kg/mol).
    """
    P, V, n, T = p.get("P"), p.get("V"), p.get("n"), p.get("T")
    given = {k: v for k, v in {"P": P, "V": V, "n": n, "T": T}.items() if v is not None}
    missing = [k for k in ("P", "V", "n", "T") if k not in given]
    if len(missing) != 1:
        raise ValueError("Se requieren exactamente 3 de P, V, n, T (falta calcular la cuarta)")

    if missing == ["P"]:
        P = n * R * T / V
    elif missing == ["V"]:
        V = n * R * T / P
    elif missing == ["n"]:
        n = P * V / (R * T)
    elif missing == ["T"]:
        T = P * V / (n * R)

    out = {"P": P, "V": V, "n": n, "T": T, "R": R}

    M = p.get("M")  # masa molar kg/mol, opcional
    if M:
        rho = P * M / (R * T)
        out["densidad_kg_m3"] = rho
        out["volumen_molar_m3_mol"] = V / n if n else None

    # Casos limite / leyes clasicas si se piden explicitamente
    if p.get("check_stp"):
        out["V_molar_stp_L"] = 22.414

    return out


# ---------------------------------------------------------------------------
# Modo: real / van_der_waals (incluye variantes)
# ---------------------------------------------------------------------------
def _cubic_roots_real(coeffs):
    """Resuelve cubica con coeficientes [a3,a2,a1,a0] usando formula de Cardano,
    retorna raices reales."""
    a3, a2, a1, a0 = coeffs
    a2n, a1n, a0n = a2 / a3, a1 / a3, a0 / a3
    p = a1n - a2n ** 2 / 3
    q = 2 * a2n ** 3 / 27 - a2n * a1n / 3 + a0n
    disc = (q / 2) ** 2 + (p / 3) ** 3
    roots = []
    if disc >= 0:
        sqrt_disc = math.sqrt(disc)
        u = math.copysign(abs(-q / 2 + sqrt_disc) ** (1 / 3), -q / 2 + sqrt_disc)
        v = math.copysign(abs(-q / 2 - sqrt_disc) ** (1 / 3), -q / 2 - sqrt_disc)
        roots = [u + v - a2n / 3]
    else:
        r = math.sqrt(-(p / 3) ** 3)
        phi = math.acos(max(-1, min(1, -q / (2 * r))))
        for k in range(3):
            root = 2 * (-p / 3) ** 0.5 * math.cos((phi + 2 * math.pi * k) / 3) - a2n / 3
            roots.append(root)
    return sorted(roots)


def _mode_real(p):
    """
    Ecuaciones de estado para gases reales.
    eos: "van_der_waals" (default) | "dieterici" | "berthelot" | "redlich_kwong"
    Requiere: n, T, a, b, y (P o V, la que falta se resuelve).
    a, b: constantes de la ecuacion de estado (unidades SI segun EOS).
    """
    eos = p.get("eos", "van_der_waals")
    n, T, a, b = p["n"], p["T"], p["a"], p["b"]
    P, V = p.get("P"), p.get("V")

    if eos == "van_der_waals":
        if V is None:
            # (P + a n^2/V^2)(V - nb) = nRT  -> cubica en V
            # PV^3 - (Pnb + nRT)V^2 + a n^2 V - a n^2 b n = 0
            coeffs = [P, -(P * n * b + n * R * T), a * n ** 2, -a * n ** 3 * b]
            roots = _cubic_roots_real(coeffs)
            V = max(roots)  # raiz fisica = mayor volumen real
        elif P is None:
            P = n * R * T / (V - n * b) - a * (n ** 2) / (V ** 2)
        Z = P * V / (n * R * T)
        return {"eos": eos, "P": P, "V": V, "n": n, "T": T, "Z": Z, "a": a, "b": b}

    elif eos == "dieterici":
        if V is None:
            raise ValueError("Dieterici: proveer V para resolver P directamente (forma explicita en P)")
        Vm = V / n
        P = (R * T / (Vm - b)) * math.exp(-a / (R * T * Vm))
        Z = P * V / (n * R * T)
        return {"eos": eos, "P": P, "V": V, "n": n, "T": T, "Z": Z, "a": a, "b": b}

    elif eos == "berthelot":
        if V is None:
            raise ValueError("Berthelot: proveer V")
        Vm = V / n
        P = R * T / (Vm - b) - a / (T * Vm ** 2)
        Z = P * V / (n * R * T)
        return {"eos": eos, "P": P, "V": V, "n": n, "T": T, "Z": Z, "a": a, "b": b}

    elif eos == "redlich_kwong":
        if V is None:
            raise ValueError("Redlich-Kwong: proveer V (o extender con solver cubico dedicado)")
        Vm = V / n
        P = R * T / (Vm - b) - a / (Vm * (Vm + b) * math.sqrt(T))
        Z = P * V / (n * R * T)
        return {"eos": eos, "P": P, "V": V, "n": n, "T": T, "Z": Z, "a": a, "b": b}

    else:
        raise ValueError(f"EOS desconocida: {eos}")


# ---------------------------------------------------------------------------
# Modo: mixture
# ---------------------------------------------------------------------------
def _mode_mixture(p):
    """
    componentes: lista de {"nombre":.., "n":.., "P":.. (opcional si se da x)}
    T, V requeridos para calcular P_total via Dalton (gas ideal por componente).
    """
    componentes = p["componentes"]
    T, V = p["T"], p["V"]
    n_total = sum(c["n"] for c in componentes)

    resultados = []
    S_mix = 0.0
    for c in componentes:
        x_i = c["n"] / n_total
        P_i = x_i * n_total * R * T / V  # presion parcial (Dalton, gas ideal)
        mu_i = None
        if p.get("mu0") and c.get("P0"):
            mu_i = p["mu0"] + R * T * math.log(P_i / c["P0"])
        S_mix += -R * c["n"] * math.log(x_i) if x_i > 0 else 0
        resultados.append({
            "nombre": c.get("nombre"),
            "n": c["n"], "x": x_i, "P_parcial": P_i, "mu": mu_i
        })

    P_total = n_total * R * T / V
    return {
        "P_total": P_total,
        "n_total": n_total,
        "componentes": resultados,
        "entropia_mezcla_J_K": S_mix,
    }


# ---------------------------------------------------------------------------
# Modo: kinetic (teoria cinetica molecular)
# ---------------------------------------------------------------------------
def _mode_kinetic(p):
    """
    M: masa molar (kg/mol), T: temperatura (K).
    Retorna velocidades caracteristicas y, opcionalmente, la distribucion
    de Maxwell-Boltzmann evaluada en un rango de velocidades.
    """
    M, T = p["M"], p["T"]
    v_rms = math.sqrt(3 * R * T / M)
    v_prom = math.sqrt(8 * R * T / (math.pi * M))
    v_mp = math.sqrt(2 * R * T / M)
    E_k_media = 1.5 * R * T  # por mol

    out = {
        "v_rms_m_s": v_rms,
        "v_promedio_m_s": v_prom,
        "v_mas_probable_m_s": v_mp,
        "energia_cinetica_media_J_mol": E_k_media,
    }

    if p.get("distribucion"):
        v_min = p.get("v_min", 0.0)
        v_max = p.get("v_max", v_rms * 3)
        n_puntos = p.get("n_puntos", 50)
        paso = (v_max - v_min) / (n_puntos - 1) if n_puntos > 1 else 0
        pref = 4 * math.pi * (M / (2 * math.pi * R * T)) ** 1.5
        dist = []
        for i in range(n_puntos):
            v = v_min + i * paso
            f_v = pref * v ** 2 * math.exp(-M * v ** 2 / (2 * R * T))
            dist.append({"v": v, "f_v": f_v})
        out["distribucion_maxwell_boltzmann"] = dist

    if p.get("M2"):
        # Ley de Graham: tasa de efusion relativa
        out["graham_rate_ratio"] = math.sqrt(p["M2"] / M)

    return out


# ---------------------------------------------------------------------------
# Modo: compressible (flujo compresible / dinamica de gases)
# ---------------------------------------------------------------------------
def _mode_compressible(p):
    """
    gamma: Cp/Cv. Provee v y T (o directamente Mach) segun lo disponible.
    Calcula numero de Mach, relacion de presiones criticas, y proceso adiabatico
    P*V^gamma = const si se dan P1,V1,V2.
    """
    gamma = p.get("gamma", 1.4)
    out = {"gamma": gamma}

    if p.get("v") is not None and p.get("T") is not None and p.get("M_molar") is not None:
        c = math.sqrt(gamma * R * p["T"] / p["M_molar"])  # velocidad del sonido
        Mach = p["v"] / c
        out["velocidad_sonido_m_s"] = c
        out["mach"] = Mach

    if p.get("P1") is not None and p.get("V1") is not None and p.get("V2") is not None:
        P1, V1, V2 = p["P1"], p["V1"], p["V2"]
        P2 = P1 * (V1 / V2) ** gamma
        out["proceso_adiabatico"] = {"P1": P1, "V1": V1, "V2": V2, "P2": P2}

    # relacion de presion critica en toberas (flujo isentropico, garganta sonica)
    out["relacion_presion_critica"] = (2 / (gamma + 1)) ** (gamma / (gamma - 1))

    return out


# ---------------------------------------------------------------------------
# Dispatcher principal
# ---------------------------------------------------------------------------
def compute_gas(mode, params=None):
    params = params or {}
    if mode == "ideal":
        return _mode_ideal(params)
    elif mode in ("real", "van_der_waals"):
        return _mode_real(params)
    elif mode == "mixture":
        return _mode_mixture(params)
    elif mode == "kinetic":
        return _mode_kinetic(params)
    elif mode == "compressible":
        return _mode_compressible(params)
    else:
        raise ValueError(
            f"Modo desconocido: {mode}. Usar: ideal | real | mixture | kinetic | compressible"
        )


GAS_TOOL_SCHEMA = {
    "name": "gas_tool",
    "description": (
        "Matematica de gases: gas ideal (PV=nRT), gases reales "
        "(Van der Waals, Dieterici, Berthelot, Redlich-Kwong), mezclas "
        "(Dalton, entropia de mezcla, potencial quimico), teoria cinetica "
        "molecular (velocidades caracteristicas, distribucion de "
        "Maxwell-Boltzmann, ley de Graham), y dinamica de flujo compresible "
        "(numero de Mach, proceso adiabatico, relacion de presion critica)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["ideal", "real", "van_der_waals", "mixture", "kinetic", "compressible"],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    # smoke test rapido
    print(compute_gas("ideal", {"P": 101325, "n": 1, "T": 273.15}))
    print(compute_gas("real", {"eos": "van_der_waals", "n": 1, "T": 300, "a": 0.1358, "b": 3.183e-5, "P": 200000}))
    print(compute_gas("kinetic", {"M": 0.028, "T": 300}))
    print(compute_gas("compressible", {"gamma": 1.4, "P1": 101325, "V1": 1.0, "V2": 0.5}))
