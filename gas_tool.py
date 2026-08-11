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
K_B = 1.380649e-23  # J/K
N_A = 6.02214076e23  # 1/mol

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


def _newton_solve_V(P_target, T, n, a, b, eos, V0=None, tol=1e-10, max_iter=100):
    """Newton-Raphson para resolver V dado P en EOS implicitas en V
    (Dieterici, Berthelot, Redlich-Kwong). Devuelve V que hace P_eos(V) = P_target."""
    Vm = (V0 / n) if V0 else (R * T / P_target)  # arranque desde gas ideal
    if Vm <= b:
        Vm = b * 1.5

    def P_of_Vm(Vm):
        if eos == "dieterici":
            return (R * T / (Vm - b)) * math.exp(-a / (R * T * Vm))
        elif eos == "berthelot":
            return R * T / (Vm - b) - a / (T * Vm ** 2)
        elif eos == "redlich_kwong":
            return R * T / (Vm - b) - a / (Vm * (Vm + b) * math.sqrt(T))
        raise ValueError(f"Newton solver no soporta eos={eos}")

    for _ in range(max_iter):
        f = P_of_Vm(Vm) - P_target
        h = max(Vm * 1e-6, 1e-12)
        df = (P_of_Vm(Vm + h) - P_of_Vm(Vm - h)) / (2 * h)
        if df == 0:
            break
        step = f / df
        Vm_new = Vm - step
        if Vm_new <= b:
            Vm_new = (Vm + b) / 2  # backtrack, evitar cruzar la asintota en V=b
        if abs(Vm_new - Vm) < tol:
            Vm = Vm_new
            break
        Vm = Vm_new
    return Vm * n


def _solve_V_at_P(P, T, n, a, b, eos, V_guess=None):
    """Resuelve V para una P dada, cualquier EOS soportada. Usa cubica exacta para
    van_der_waals y Newton (con warm-start V_guess) para las demas."""
    if eos == "van_der_waals":
        coeffs = [P, -(P * n * b + n * R * T), a * n ** 2, -a * n ** 3 * b]
        roots = _cubic_roots_real(coeffs)
        real_roots = [r for r in roots if r > n * b]
        return max(real_roots) if real_roots else max(roots)
    else:
        return _newton_solve_V(P, T, n, a, b, eos, V0=V_guess)


def _fugacity_coefficient(P, T, n, a, b, eos, n_points=200):
    """ln(phi) = integral_0^P (Z-1) dP/P, integrado en espacio log(P) por estabilidad
    (el integrando (Z-1)/P es bien comportado en ln P porque Z-1 -> const finita cuando P->0)."""
    P_min = P * 1e-6
    ln_P_vals = [
        math.log(P_min) + i * (math.log(P) - math.log(P_min)) / (n_points - 1)
        for i in range(n_points)
    ]
    P_vals = [math.exp(lp) for lp in ln_P_vals]

    integrand = []
    V_guess = None
    for P_i in P_vals:
        V_i = _solve_V_at_P(P_i, T, n, a, b, eos, V_guess=V_guess)
        V_guess = V_i
        Z_i = P_i * V_i / (n * R * T)
        integrand.append(Z_i - 1)

    # trapecio en ln(P): integral f dlnP
    integral = 0.0
    for i in range(1, n_points):
        d_lnP = ln_P_vals[i] - ln_P_vals[i - 1]
        integral += 0.5 * (integrand[i] + integrand[i - 1]) * d_lnP

    ln_phi = integral
    phi = math.exp(ln_phi)
    return phi


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
        result = {"eos": eos, "P": P, "V": V, "n": n, "T": T, "Z": Z, "a": a, "b": b}

    elif eos in ("dieterici", "berthelot", "redlich_kwong"):
        if V is None:
            V = _newton_solve_V(P, T, n, a, b, eos)
        elif P is None:
            Vm = V / n
            if eos == "dieterici":
                P = (R * T / (Vm - b)) * math.exp(-a / (R * T * Vm))
            elif eos == "berthelot":
                P = R * T / (Vm - b) - a / (T * Vm ** 2)
            elif eos == "redlich_kwong":
                P = R * T / (Vm - b) - a / (Vm * (Vm + b) * math.sqrt(T))
        Z = P * V / (n * R * T)
        result = {"eos": eos, "P": P, "V": V, "n": n, "T": T, "Z": Z, "a": a, "b": b}

    else:
        raise ValueError(f"EOS desconocida: {eos}")

    if p.get("compute_fugacity"):
        phi = _fugacity_coefficient(result["P"], T, n, a, b, eos)
        result["fugacity_coefficient"] = phi
        result["fugacity"] = phi * result["P"]

    return result


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
        V_i = x_i * V  # volumen parcial (Amagat, mezcla ideal: V_i = x_i * V_total)
        mu_i = None
        if p.get("mu0") and c.get("P0"):
            mu_i = p["mu0"] + R * T * math.log(P_i / c["P0"])
        S_mix += -R * c["n"] * math.log(x_i) if x_i > 0 else 0
        resultados.append({
            "nombre": c.get("nombre"),
            "n": c["n"], "x": x_i, "P_parcial": P_i, "V_parcial_amagat": V_i, "mu": mu_i
        })

    P_total = n_total * R * T / V
    G_mix = -T * S_mix  # mezcla ideal: H_mix = 0 -> DeltaG_mix = -T*DeltaS_mix
    return {
        "P_total": P_total,
        "n_total": n_total,
        "componentes": resultados,
        "entropia_mezcla_J_K": S_mix,
        "gibbs_mezcla_J": G_mix,
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

    # Propiedades de transporte (teoria cinetica elemental, no Chapman-Enskog exacto)
    # Requiere: P (presion, Pa) y d (diametro molecular efectivo, m)
    P_t, d = p.get("P"), p.get("d")
    if P_t is not None and d is not None:
        lam = K_B * T / (math.sqrt(2) * math.pi * d ** 2 * P_t)  # recorrido libre medio
        rho = P_t * M / (R * T)  # densidad de masa
        n_density = P_t / (K_B * T)  # densidad numerica (moleculas/m3)

        eta = (1 / 3) * rho * v_prom * lam  # viscosidad dinamica

        # Cv molar: se puede pasar directo, o inferir de grados de libertad (dof)
        # dof=3 monoatomico (Cv=3/2 R), dof=5 diatomico rigido (Cv=5/2 R), dof=6 poliatomico no lineal (Cv=3R)
        dof = p.get("dof", 3)
        Cv_molar = p.get("Cv_molar", dof / 2 * R)
        Cv_per_molecule = Cv_molar / N_A
        kappa_thermal = (1 / 3) * n_density * v_prom * lam * Cv_per_molecule  # conductividad termica

        D_self = (1 / 3) * v_prom * lam  # autodifusion

        out["transporte"] = {
            "recorrido_libre_medio_m": lam,
            "viscosidad_dinamica_Pa_s": eta,
            "conductividad_termica_W_m_K": kappa_thermal,
            "difusion_autodifusion_m2_s": D_self,
            "Cv_molar_usado_J_mol_K": Cv_molar,
            "nota": "Teoria cinetica elemental (prefactor 1/3); Chapman-Enskog exacto usa "
                    "prefactores distintos (~5pi/32 para viscosidad) y da resultados ~20-30% mayores.",
        }

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

    # Onda de choque normal (Rankine-Hugoniot), dado Mach upstream M1 > 1
    M1 = p.get("shock_mach")
    if M1 is not None:
        if M1 <= 1:
            raise ValueError("shock_mach debe ser > 1 (onda de choque solo existe en flujo supersonico)")
        g = gamma
        M2_sq = (1 + (g - 1) / 2 * M1 ** 2) / (g * M1 ** 2 - (g - 1) / 2)
        M2 = math.sqrt(M2_sq)
        P2_P1 = 1 + 2 * g / (g + 1) * (M1 ** 2 - 1)
        rho2_rho1 = ((g + 1) * M1 ** 2) / ((g - 1) * M1 ** 2 + 2)
        T2_T1 = P2_P1 / rho2_rho1  # via ley de gas ideal, ambos lados mismo R
        # perdida de presion de estancamiento (medida de irreversibilidad)
        P02_P01 = (
            ((g + 1) * M1 ** 2 / ((g - 1) * M1 ** 2 + 2)) ** (g / (g - 1))
            * ((g + 1) / (2 * g * M1 ** 2 - (g - 1))) ** (1 / (g - 1))
        )
        out["onda_choque_normal"] = {
            "M1": M1, "M2": M2,
            "P2_P1": P2_P1, "rho2_rho1": rho2_rho1, "T2_T1": T2_T1,
            "P02_P01": P02_P01,
        }

    # Relacion area-Mach en tobera (flujo isentropico cuasi-1D): A/A* = f(M, gamma)
    def _area_ratio(M, g):
        return (1 / M) * ((2 / (g + 1)) * (1 + (g - 1) / 2 * M ** 2)) ** ((g + 1) / (2 * (g - 1)))

    M_in = p.get("nozzle_mach")
    if M_in is not None:
        out["nozzle_area_ratio"] = _area_ratio(M_in, gamma)

    A_ratio = p.get("nozzle_area_ratio")
    regimen = p.get("nozzle_regime", "subsonic")  # "subsonic" | "supersonic"
    if A_ratio is not None:
        M_guess = 0.3 if regimen == "subsonic" else 2.0
        for _ in range(100):
            f = _area_ratio(M_guess, gamma) - A_ratio
            h = 1e-6
            df = (_area_ratio(M_guess + h, gamma) - _area_ratio(M_guess - h, gamma)) / (2 * h)
            if df == 0:
                break
            M_new = M_guess - f / df
            if M_new <= 0:
                M_new = M_guess / 2
            if abs(M_new - M_guess) < 1e-10:
                M_guess = M_new
                break
            M_guess = M_new
        out["nozzle_mach_solved"] = {"regime": regimen, "M": M_guess, "area_ratio_target": A_ratio}

    return out


# ---------------------------------------------------------------------------
# Modo: humidity (humedad en mezclas gas-vapor, tipicamente aire-agua)
# ---------------------------------------------------------------------------
def _saturation_vapor_pressure_Pa(T_K):
    """Formula de Buck (1981) para presion de vapor de saturacion del agua.
    Valida entre 0-50 C aprox, error < 0.2%."""
    T_C = T_K - 273.15
    if T_C >= 0:
        return 611.21 * math.exp((18.678 - T_C / 234.5) * (T_C / (257.14 + T_C)))
    else:
        return 611.15 * math.exp((23.036 - T_C / 333.7) * (T_C / (279.82 + T_C)))


def _mode_humidity(p):
    """
    Humedad de una mezcla gas-vapor (default: aire humedo).
    Inputs: T (K), P_total (Pa, presion atmosferica total).
    Uno de: RH (0-100, humedad relativa) o P_vapor (Pa, presion parcial de vapor directa).
    M_dry, M_vapor: masas molares (default aire seco 0.028964 kg/mol, agua 0.018015 kg/mol).
    """
    T, P_total = p["T"], p["P_total"]
    M_dry = p.get("M_dry", 0.028964)
    M_vapor = p.get("M_vapor", 0.018015)

    P_sat = _saturation_vapor_pressure_Pa(T)

    if "P_vapor" in p:
        P_vapor = p["P_vapor"]
        RH = 100 * P_vapor / P_sat
    elif "RH" in p:
        RH = p["RH"]
        P_vapor = (RH / 100) * P_sat
    else:
        raise ValueError("Se requiere RH (0-100) o P_vapor (Pa)")

    if P_vapor >= P_total:
        raise ValueError("P_vapor no puede ser >= P_total (mezcla saturada/inconsistente)")

    P_dry = P_total - P_vapor
    # razon de mezcla (humidity ratio): masa de vapor / masa de aire seco
    w = (M_vapor / M_dry) * P_vapor / P_dry

    # densidad de la mezcla humeda (suma de densidades parciales, gas ideal)
    rho_dry = P_dry * M_dry / (R * T)
    rho_vapor = P_vapor * M_vapor / (R * T)
    rho_humid = rho_dry + rho_vapor

    # densidad equivalente si todo fuera aire seco a la misma P_total, T (referencia)
    rho_dry_equiv = P_total * M_dry / (R * T)

    return {
        "T_K": T, "P_total_Pa": P_total,
        "P_saturacion_Pa": P_sat,
        "P_vapor_Pa": P_vapor,
        "P_dry_Pa": P_dry,
        "humedad_relativa_pct": RH,
        "razon_mezcla_kg_vapor_por_kg_seco": w,
        "densidad_humeda_kg_m3": rho_humid,
        "densidad_seca_equivalente_kg_m3": rho_dry_equiv,
        "nota": "El aire humedo es MENOS denso que el aire seco a igual P,T (el vapor de agua "
                "tiene menor masa molar que el aire seco) — chequeo: densidad_humeda < densidad_seca_equivalente.",
    }


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
    elif mode == "humidity":
        return _mode_humidity(params)
    else:
        raise ValueError(
            f"Modo desconocido: {mode}. Usar: ideal | real | mixture | kinetic | compressible | humidity"
        )


GAS_TOOL_SCHEMA = {
    "name": "gas_tool",
    "description": (
        "Matematica de gases: gas ideal (PV=nRT), gases reales "
        "(Van der Waals, Dieterici, Berthelot, Redlich-Kwong), mezclas "
        "(Dalton, Amagat, entropia y Gibbs de mezcla), teoria cinetica "
        "molecular (velocidades caracteristicas, distribucion de "
        "Maxwell-Boltzmann, ley de Graham, propiedades de transporte: "
        "viscosidad, conductividad termica, autodifusion), dinamica de "
        "flujo compresible (numero de Mach, proceso adiabatico, ondas de "
        "choque normal, relacion area-Mach en toberas), fugacidad, y "
        "humedad de mezclas gas-vapor (presion de saturacion, razon de "
        "mezcla, densidad de aire humedo)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["ideal", "real", "van_der_waals", "mixture", "kinetic", "compressible", "humidity"],
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
