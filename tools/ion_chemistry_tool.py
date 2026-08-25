"""
ion_chemistry_tool.py

Tool de química de iones en solución. Cubre los 9 modos pendientes de la
tabla resumen: concentration, ionic_strength, activity_coefficient,
ph_calculation, solubility_product, conductivity, diffusion_coefficient,
electrophoretic_mobility, donnan_equilibrium.

Convenciones (mismo nivel de rigor que aminoacid_tool.py):
- Unidades SI salvo que se indique lo contrario (concentraciones en mol/L
  se aceptan como caso especial porque es lo estándar en fisicoquímica).
- Cada modo devuelve un dict con 'result', 'units', y 'method' (referencia
  a la ecuación/modelo usado), más 'warnings' si corresponde.
- Ecuaciones numéricas no lineales se resuelven con scipy.optimize.brentq
  (mismo patrón que water_activity/boiling_point).
- register_tool(...) al final, auto-registra via tool_registry al importar
  el módulo (mismo patrón que aminoacid_tool / sustainable_sourcing_tool).
"""

import math
from dataclasses import dataclass, field
from typing import Optional

try:
    from scipy.optimize import brentq
except ImportError:  # pragma: no cover
    brentq = None

# ---------------------------------------------------------------------------
# Constantes físicas (SI)
# ---------------------------------------------------------------------------
R = 8.314462618          # J/(mol*K)
F = 96485.33212          # C/mol
NA = 6.02214076e23       # 1/mol
E_CHARGE = 1.602176634e-19  # C
KB = 1.380649e-23        # J/K
EPS0 = 8.8541878128e-12  # F/m


# ---------------------------------------------------------------------------
# Modo 1: concentration
# ---------------------------------------------------------------------------
def concentration(mode="molarity", **kw):
    """
    Conversiones y cálculos de concentración de iones en solución.

    sub-modos:
      - molarity: moles / volumen(L)
      - dilution: C1*V1 = C2*V2 (despeja el que falte)
      - mass_to_molar: masa(g), masa_molar(g/mol), volumen(L) -> mol/L
      - molal_to_molar: molalidad(mol/kg), densidad(kg/L), masa_molar(g/mol)
      - ppm_to_molar: ppm (mg/L asumiendo solución acuosa diluida), masa_molar
    """
    if mode == "molarity":
        moles = kw["moles"]
        volume_L = kw["volume_L"]
        if volume_L <= 0:
            raise ValueError("volume_L debe ser > 0")
        c = moles / volume_L
        return {"result": c, "units": "mol/L", "method": "C = n/V"}

    if mode == "dilution":
        c1, v1, c2, v2 = kw.get("C1"), kw.get("V1"), kw.get("C2"), kw.get("V2")
        vals = {"C1": c1, "V1": v1, "C2": c2, "V2": v2}
        missing = [k for k, v in vals.items() if v is None]
        if len(missing) != 1:
            raise ValueError("Dar exactamente 3 de {C1,V1,C2,V2}, la 4ta se calcula")
        target = missing[0]
        if target == "C1":
            res = (c2 * v2) / v1
        elif target == "V1":
            res = (c2 * v2) / c1
        elif target == "C2":
            res = (c1 * v1) / v2
        else:
            res = (c1 * v1) / c2
        units = "mol/L" if target in ("C1", "C2") else "L (misma unidad que V1/V2 de entrada)"
        return {"result": res, "solved_for": target, "units": units,
                "method": "C1*V1 = C2*V2"}

    if mode == "mass_to_molar":
        mass_g = kw["mass_g"]
        molar_mass = kw["molar_mass_g_mol"]
        volume_L = kw["volume_L"]
        c = (mass_g / molar_mass) / volume_L
        return {"result": c, "units": "mol/L", "method": "C = (m/M)/V"}

    if mode == "molal_to_molar":
        molality = kw["molality_mol_kg"]
        density = kw["density_kg_L"]
        molar_mass = kw["molar_mass_g_mol"]
        # C = (molality * density) / (1 + molality * M_kg_per_mol)
        M_kg = molar_mass / 1000.0
        c = (molality * density) / (1 + molality * M_kg)
        return {"result": c, "units": "mol/L",
                "method": "C = (m*rho)/(1 + m*M), derivado de balance de masa"}

    if mode == "ppm_to_molar":
        ppm = kw["ppm"]
        molar_mass = kw["molar_mass_g_mol"]
        # ppm ~ mg soluto / L solucion (aprox. para soluciones acuosas diluidas, rho~1kg/L)
        c = (ppm / 1000.0) / molar_mass
        return {"result": c, "units": "mol/L",
                "method": "aprox. ppm=mg/L, rho_solucion~1kg/L",
                "warnings": ["válido solo para soluciones acuosas diluidas"]}

    raise ValueError(f"sub-modo desconocido: {mode}")


# ---------------------------------------------------------------------------
# Modo 2: ionic_strength
# ---------------------------------------------------------------------------
def ionic_strength(species):
    """
    I = 0.5 * sum(ci * zi^2)
    species: lista de dicts [{"c": mol/L, "z": carga}, ...]
    """
    if not species:
        raise ValueError("species no puede estar vacío")
    I = 0.5 * sum(s["c"] * (s["z"] ** 2) for s in species)
    return {"result": I, "units": "mol/L", "method": "I = 0.5 * sum(ci * zi^2) (Lewis-Randall)"}


# ---------------------------------------------------------------------------
# Modo 3: activity_coefficient
# ---------------------------------------------------------------------------
def activity_coefficient(z, ionic_strength_mol_L, T_K=298.15, model="davies",
                          a_ion_nm=None, solvent="water"):
    """
    Coeficiente de actividad iónico gamma.

    model:
      - "debye_huckel_limiting": log10(gamma) = -A*z^2*sqrt(I)   (válido I<~0.01M)
      - "debye_huckel_extended": log10(gamma) = -A*z^2*sqrt(I) / (1 + B*a*sqrt(I))
        (requiere a_ion_nm, radio iónico efectivo; válido I<~0.1M)
      - "davies": log10(gamma) = -A*z^2*(sqrt(I)/(1+sqrt(I)) - 0.3*I)
        (sin parámetros extra; válido hasta I~0.5M, el más usado en la práctica)

    A y B son función de T y del solvente (agua, vía constante dieléctrica
    epsilon_r(T) aproximada linealmente entre 0 y 100 C).
    """
    I = ionic_strength_mol_L
    if I < 0:
        raise ValueError("ionic_strength_mol_L debe ser >= 0")

    if solvent != "water":
        raise ValueError("solo 'water' soportado por ahora")

    # epsilon_r(agua) aproximación lineal 0-100C (CRC): ~87.9 a 0C, ~55.3 a 100C
    eps_r = 87.740 - 0.40008 * (T_K - 273.15) + 9.398e-4 * (T_K - 273.15) ** 2 \
        - 1.410e-6 * (T_K - 273.15) ** 3
    eps = eps_r * EPS0

    # densidad del agua aprox (kg/m3), rango 0-100C
    Tc = T_K - 273.15
    rho = 999.842594 + 6.793952e-2 * Tc - 9.09529e-3 * Tc ** 2 \
        + 1.001685e-4 * Tc ** 3 - 1.120083e-6 * Tc ** 4 + 6.536332e-9 * Tc ** 5

    # A de Debye-Huckel (L^1/2 mol^-1/2), derivada de teoria (unidades log10)
    A = (E_CHARGE ** 3 / (math.log(10) * 8 * math.pi)) * \
        math.sqrt((2 * NA * rho) / ((eps * KB * T_K) ** 3)) / 1000.0 ** 0.5
    # nota: el factor 1000 ajusta rho(kg/m3)->relación con mol/L; A tabulado en agua a 25C ~0.509
    # se corrige empíricamente contra el valor tabulado conocido
    A_ref_25C = 0.5092
    if abs(T_K - 298.15) < 1e-6:
        A = A_ref_25C
    else:
        # escalar proporcionalmente usando la dependencia teórica T^-3/2 * eps_r^-3/2
        A = A_ref_25C * (298.15 / T_K) ** 1.5 * (78.30 / eps_r) ** 1.5

    if model == "debye_huckel_limiting":
        log_gamma = -A * (z ** 2) * math.sqrt(I)
        method = "Debye-Huckel limitante: log10(gamma) = -A z^2 sqrt(I)"

    elif model == "debye_huckel_extended":
        if a_ion_nm is None:
            raise ValueError("debye_huckel_extended requiere a_ion_nm (radio iónico efectivo)")
        B_ref_25C = 0.3283  # nm^-1 * (mol/L)^-1/2, valor tabulado en agua a 25C
        B = B_ref_25C * (298.15 / T_K) ** 0.5 * (78.30 / eps_r) ** 0.5
        log_gamma = -A * (z ** 2) * math.sqrt(I) / (1 + B * a_ion_nm * math.sqrt(I))
        method = "Debye-Huckel extendida: log10(gamma) = -A z^2 sqrt(I) / (1+Ba*sqrt(I))"

    elif model == "davies":
        log_gamma = -A * (z ** 2) * (math.sqrt(I) / (1 + math.sqrt(I)) - 0.3 * I)
        method = "Davies: log10(gamma) = -A z^2 (sqrt(I)/(1+sqrt(I)) - 0.3 I)"

    else:
        raise ValueError(f"model desconocido: {model}")

    gamma = 10 ** log_gamma
    warnings = []
    if model == "debye_huckel_limiting" and I > 0.01:
        warnings.append("I > 0.01 mol/L: fuera del rango de validez de la ley límite")
    if model == "debye_huckel_extended" and I > 0.1:
        warnings.append("I > 0.1 mol/L: fuera del rango típico de validez de la extendida")
    if model == "davies" and I > 0.5:
        warnings.append("I > 0.5 mol/L: fuera del rango típico de validez de Davies")

    out = {"result": gamma, "log10_gamma": log_gamma, "A_debye": A,
           "units": "adimensional", "method": method}
    if warnings:
        out["warnings"] = warnings
    return out


# ---------------------------------------------------------------------------
# Modo 4: ph_calculation
# ---------------------------------------------------------------------------
def ph_calculation(mode="henderson_hasselbalch", **kw):
    """
    sub-modos:
      - henderson_hasselbalch: pH = pKa + log10([A-]/[HA])
      - from_H: pH = -log10(aH+)  (con actividad, si no se da gamma se asume 1)
      - weak_acid: dado Ka y C total, resuelve [H+] exacto (balance de masa +
        electroneutralidad, vía brentq) en vez de la aproximación sqrt(Ka*C)
      - buffer_capacity: beta = 2.303 * C_total * (Ka*[H+]) / (Ka+[H+])^2
    """
    if mode == "henderson_hasselbalch":
        pKa = kw["pKa"]
        A = kw["conc_base"]   # [A-]
        HA = kw["conc_acid"]  # [HA]
        if HA <= 0 or A <= 0:
            raise ValueError("concentraciones deben ser > 0")
        pH = pKa + math.log10(A / HA)
        return {"result": pH, "units": "adimensional",
                "method": "Henderson-Hasselbalch: pH = pKa + log10([A-]/[HA])"}

    if mode == "from_H":
        H = kw["H_conc_mol_L"]
        gamma = kw.get("gamma", 1.0)
        if H <= 0:
            raise ValueError("H_conc_mol_L debe ser > 0")
        pH = -math.log10(gamma * H)
        return {"result": pH, "units": "adimensional",
                "method": "pH = -log10(gamma_H * [H+]) (actividad, gamma=1 => ideal)"}

    if mode == "weak_acid":
        Ka = kw["Ka"]
        C = kw["C_total_mol_L"]
        Kw = kw.get("Kw", 1.0e-14)
        if brentq is None:
            raise RuntimeError("scipy no disponible para resolver weak_acid")

        def f(H):
            # balance exacto: H = [A-]_eq + [OH-] - ... usando electroneutralidad:
            # H+ = Ka*C/(Ka+H) + Kw/H - H  =>  reordenado como raiz
            return H - (Ka * C) / (Ka + H) - Kw / H

        H = brentq(f, 1e-14, max(1.0, C * 10))
        pH = -math.log10(H)
        return {"result": pH, "H_conc_mol_L": H, "units": "adimensional",
                "method": "balance de masa + electroneutralidad exacto (brentq), "
                          "no la aproximación sqrt(Ka*C)"}

    if mode == "buffer_capacity":
        Ka = kw["Ka"]
        C_total = kw["C_total_mol_L"]
        H = kw["H_conc_mol_L"]
        beta = 2.303 * C_total * (Ka * H) / ((Ka + H) ** 2)
        return {"result": beta, "units": "mol/L por unidad de pH",
                "method": "beta = 2.303*C_total*Ka*[H+]/(Ka+[H+])^2 (Van Slyke)"}

    raise ValueError(f"sub-modo desconocido: {mode}")


# ---------------------------------------------------------------------------
# Modo 5: solubility_product
# ---------------------------------------------------------------------------
def solubility_product(mode="from_solubility", **kw):
    """
    Sal general M_p X_q <-> p M^n+ + q X^m-

    sub-modos:
      - from_solubility: dado s (mol/L de sal disuelta) y estequiometría (p,q)
        -> Ksp = (p*s)^p * (q*s)^q
      - solubility_from_ksp: inverso, resuelve s dado Ksp, p, q (numérico)
      - common_ion: solubilidad en presencia de concentración extra de un ion común
      - will_precipitate: compara Q (producto iónico actual) contra Ksp
    """
    if mode == "from_solubility":
        s = kw["solubility_mol_L"]
        p = kw["p"]
        q = kw["q"]
        Ksp = (p * s) ** p * (q * s) ** q
        return {"result": Ksp, "units": f"(mol/L)^{p+q}",
                "method": "Ksp = (p*s)^p (q*s)^q"}

    if mode == "solubility_from_ksp":
        Ksp = kw["Ksp"]
        p = kw["p"]
        q = kw["q"]
        if brentq is None:
            raise RuntimeError("scipy no disponible")

        def f(s):
            return (p * s) ** p * (q * s) ** q - Ksp

        s = brentq(f, 1e-20, 100.0)
        return {"result": s, "units": "mol/L",
                "method": "inversión numérica de Ksp = (p*s)^p (q*s)^q (brentq)"}

    if mode == "common_ion":
        Ksp = kw["Ksp"]
        p = kw["p"]
        q = kw["q"]
        common_conc = kw["common_ion_conc_mol_L"]
        is_cation = kw.get("common_is_cation", False)
        if brentq is None:
            raise RuntimeError("scipy no disponible")

        if is_cation:
            def f(s):
                return ((p * s) + common_conc) ** p * (q * s) ** q - Ksp
        else:
            def f(s):
                return (p * s) ** p * ((q * s) + common_conc) ** q - Ksp

        s = brentq(f, 1e-20, 100.0)
        return {"result": s, "units": "mol/L",
                "method": "solubilidad con ion común, resuelto numéricamente (efecto de ion común)"}

    if mode == "will_precipitate":
        Ksp = kw["Ksp"]
        cation_conc = kw["cation_conc_mol_L"]
        anion_conc = kw["anion_conc_mol_L"]
        p = kw.get("p", 1)
        q = kw.get("q", 1)
        Q = (cation_conc ** p) * (anion_conc ** q)
        will = Q > Ksp
        return {"result": will, "Q": Q, "Ksp": Ksp,
                "method": "Q vs Ksp: precipita si Q > Ksp, satura si Q=Ksp, insaturada si Q<Ksp"}

    raise ValueError(f"sub-modo desconocido: {mode}")


# ---------------------------------------------------------------------------
# Modo 6: conductivity
# ---------------------------------------------------------------------------
# Conductividad iónica molar límite (lambda0, S*cm^2/mol) a 25C, valores tabulados
LAMBDA0_25C = {
    "H+": 349.8, "Na+": 50.1, "K+": 73.5, "Li+": 38.7, "NH4+": 73.5,
    "Ca2+": 119.0, "Mg2+": 106.0, "Ba2+": 127.2,
    "OH-": 198.0, "Cl-": 76.3, "Br-": 78.1, "I-": 76.8, "NO3-": 71.4,
    "SO4^2-": 160.0, "HCO3-": 44.5, "CH3COO-": 40.9, "F-": 55.4,
}


def conductivity(mode="molar_conductivity", **kw):
    """
    sub-modos:
      - limiting: lambda_m0 de una sal a partir de sus iones tabulados
        (ley de migración independiente de Kohlrausch)
      - molar_conductivity: lambda_m = kappa / C  (kappa en S/m, C en mol/m3)
      - specific_from_ions: kappa = sum(zi * F * ci * ui) (conductividad
        específica a partir de movilidades)
      - kohlrausch_extrapolation: lambda_m(C) = lambda_m0 - K*sqrt(C)
        (electrolitos fuertes, ley de Kohlrausch-Onsager simplificada)
    """
    if mode == "limiting":
        cation = kw["cation"]
        anion = kw["anion"]
        nu_cation = kw.get("nu_cation", 1)
        nu_anion = kw.get("nu_anion", 1)
        if cation not in LAMBDA0_25C or anion not in LAMBDA0_25C:
            raise ValueError("ion no está en la tabla LAMBDA0_25C; agregar valor tabulado")
        lam0 = nu_cation * LAMBDA0_25C[cation] + nu_anion * LAMBDA0_25C[anion]
        return {"result": lam0, "units": "S*cm^2/mol",
                "method": "Ley de migración independiente de Kohlrausch: "
                          "lambda_m0 = nu+*lambda0+ + nu-*lambda0-"}

    if mode == "molar_conductivity":
        kappa = kw["kappa_S_per_m"]
        C = kw["C_mol_per_m3"]
        if C <= 0:
            raise ValueError("C_mol_per_m3 debe ser > 0")
        lam = kappa / C
        return {"result": lam, "units": "S*m^2/mol", "method": "lambda_m = kappa/C"}

    if mode == "specific_from_ions":
        species = kw["species"]  # [{"c_mol_m3":, "z":, "mobility_m2_Vs":}, ...]
        kappa = sum(abs(s["z"]) * F * s["c_mol_m3"] * s["mobility_m2_Vs"] for s in species)
        return {"result": kappa, "units": "S/m",
                "method": "kappa = sum(|zi| F ci ui), suma sobre todas las especies"}

    if mode == "kohlrausch_extrapolation":
        lam0 = kw["lambda_m0"]
        K = kw["K_coef"]
        C = kw["C_mol_L"]
        if C < 0:
            raise ValueError("C_mol_L debe ser >= 0")
        lam = lam0 - K * math.sqrt(C)
        return {"result": lam, "units": "mismas unidades que lambda_m0",
                "method": "Kohlrausch: lambda_m(C) = lambda_m0 - K*sqrt(C), "
                          "válido solo para electrolitos fuertes"}

    raise ValueError(f"sub-modo desconocido: {mode}")


# ---------------------------------------------------------------------------
# Modo 7: diffusion_coefficient
# ---------------------------------------------------------------------------
def diffusion_coefficient(mode="nernst_einstein", **kw):
    """
    sub-modos:
      - nernst_einstein: D = (u * R * T) / (|z| * F)   (a partir de movilidad
        iónica u, ecuación de Nernst-Einstein)
      - stokes_einstein: D = (kB * T) / (6 * pi * eta * r)  (a partir de radio
        hidrodinámico y viscosidad del solvente)
      - from_lambda0: D a partir de conductividad molar límite del ion
        (lambda0 = |z|^2 * F^2 * D / (R*T), inversa de Nernst-Einstein)
    """
    T = kw.get("T_K", 298.15)

    if mode == "nernst_einstein":
        u = kw["mobility_m2_Vs"]
        z = kw["z"]
        D = (u * R * T) / (abs(z) * F)
        return {"result": D, "units": "m^2/s",
                "method": "Nernst-Einstein: D = u*R*T/(|z|*F)"}

    if mode == "stokes_einstein":
        eta = kw["viscosity_Pa_s"]
        r = kw["radius_m"]
        if eta <= 0 or r <= 0:
            raise ValueError("viscosity_Pa_s y radius_m deben ser > 0")
        D = (KB * T) / (6 * math.pi * eta * r)
        return {"result": D, "units": "m^2/s",
                "method": "Stokes-Einstein: D = kB*T/(6*pi*eta*r)",
                "warnings": ["asume esfera rígida y flujo continuo (no válido "
                             "para iones muy pequeños o solvatación fuerte)"]}

    if mode == "from_lambda0":
        lam0_S_cm2_mol = kw["lambda0_S_cm2_mol"]
        z = kw["z"]
        lam0_SI = lam0_S_cm2_mol * 1e-4  # S*cm^2/mol -> S*m^2/mol
        D = (lam0_SI * R * T) / ((z ** 2) * (F ** 2))
        return {"result": D, "units": "m^2/s",
                "method": "inversa de Nernst-Einstein: D = lambda0*R*T/(z^2*F^2)"}

    raise ValueError(f"sub-modo desconocido: {mode}")


# ---------------------------------------------------------------------------
# Modo 8: electrophoretic_mobility
# ---------------------------------------------------------------------------
def electrophoretic_mobility(mode="from_diffusion", **kw):
    """
    sub-modos:
      - from_diffusion: u = |z|*F*D / (R*T)  (Nernst-Einstein, inversa del
        modo anterior)
      - from_velocity: u = v_drift / E_field  (movilidad a partir de
        velocidad de deriva medida y campo eléctrico aplicado)
      - huckel: u = (2*eps*zeta) / (3*eta)  (partículas pequeñas, kappa*r << 1;
        electroforesis capilar / coloides pequeños en medio de baja fuerza iónica)
      - smoluchowski: u = (eps*zeta) / eta  (partículas grandes, kappa*r >> 1)
    """
    if mode == "from_diffusion":
        z = kw["z"]
        D = kw["D_m2_s"]
        T = kw.get("T_K", 298.15)
        u = (abs(z) * F * D) / (R * T)
        return {"result": u, "units": "m^2/(V*s)",
                "method": "Nernst-Einstein: u = |z|*F*D/(R*T)"}

    if mode == "from_velocity":
        v = kw["drift_velocity_m_s"]
        E = kw["E_field_V_m"]
        if E == 0:
            raise ValueError("E_field_V_m no puede ser 0")
        u = v / E
        return {"result": u, "units": "m^2/(V*s)", "method": "u = v_deriva / E"}

    if mode == "huckel":
        eps_r = kw.get("eps_r", 78.30)  # agua a 25C por defecto
        zeta_V = kw["zeta_potential_V"]
        eta = kw["viscosity_Pa_s"]
        eps = eps_r * EPS0
        u = (2.0 / 3.0) * (eps * zeta_V) / eta
        return {"result": u, "units": "m^2/(V*s)",
                "method": "Ecuación de Hückel (kappa*r << 1): u = 2*eps*zeta/(3*eta)"}

    if mode == "smoluchowski":
        eps_r = kw.get("eps_r", 78.30)
        zeta_V = kw["zeta_potential_V"]
        eta = kw["viscosity_Pa_s"]
        eps = eps_r * EPS0
        u = (eps * zeta_V) / eta
        return {"result": u, "units": "m^2/(V*s)",
                "method": "Ecuación de Smoluchowski (kappa*r >> 1): u = eps*zeta/eta"}

    raise ValueError(f"sub-modo desconocido: {mode}")


# ---------------------------------------------------------------------------
# Modo 9: donnan_equilibrium
# ---------------------------------------------------------------------------
def donnan_equilibrium(C_salt_out, C_fixed_charge_in, z_fixed=-1, z_salt=1,
                        V_in=None, V_out=None, T_K=298.15):
    """
    Equilibrio de Donnan entre dos compartimentos separados por una membrana
    permeable a un electrolito simple (z:z) pero impermeable a un macroión
    con carga fija (típicamente proteína, z_fixed<0).

    Derivación analítica exacta (no aproximación de "diluido"):
    - Compartimento "in" (con macroión fijo, concentración C_fixed_charge_in,
      carga z_fixed) y "out" (solución de electrolito puro, C_salt_out,
      electrolito z:-z simétrico, ej. NaCl con z_salt=+1/-1).
    - Electroneutralidad en "in": z_fixed*C_fixed + z_salt*C+_in - z_salt*C-_in = 0
    - Equilibrio químico (igual potencial electroquímico del electrolito a
      ambos lados): C+_in * C-_in = C+_out * C-_out = C_salt_out^2
      (asumiendo actividades ~1, o corregible con gamma si se pasa)
    - Con electrolito z:z simétrico y C_fixed en "in":
      Sea x = C-_in (concentración del co-ion, mismo signo que el fijo).
      x*(x + z_fixed_eq*C_fixed) = C_salt_out^2  -> cuadrática exacta.

    Devuelve las concentraciones de equilibrio a ambos lados, el potencial
    de Donnan (ecuación de Nernst para el ion permeable) y el desbalance
    osmótico resultante (relevante para hinchamiento de geles/membranas).
    """
    if z_salt <= 0:
        raise ValueError("z_salt debe ser la magnitud de carga del electrolito (>0)")

    # |carga| del macroión, con signo aplicado aparte
    Z = abs(z_fixed)
    Cf = C_fixed_charge_in  # concentración molar del macroión (no de carga)
    charge_fixed = z_fixed * Cf  # con signo

    # Caso electrolito 1:1 (z_salt=1): solución cuadrática cerrada exacta.
    # Electroneutralidad in: charge_fixed + C_cation_in - C_anion_in = 0
    # Producto: C_cation_in * C_anion_in = C_salt_out^2
    # Si charge_fixed < 0 (macroión aniónico, caso típico proteína):
    #   C_cation_in - C_anion_in = -charge_fixed = |charge_fixed|
    #   sea a = C_anion_in: (a+|charge_fixed|)*a = C_salt_out^2
    if z_salt != 1:
        raise ValueError("por ahora solo electrolito 1:1 soportado exactamente "
                          "(z_salt=1); para z:z>1 se requiere solver numérico aparte")

    Cout2 = C_salt_out ** 2
    b = charge_fixed  # con signo: C_cation_in - C_anion_in = -b

    # Resolver: sea a = C_anion_in >= 0
    # (a - b) * a = Cout2  =>  a^2 - b*a - Cout2 = 0
    disc = b ** 2 + 4 * Cout2
    a = (b + math.sqrt(disc)) / 2.0  # raíz físicamente válida (a>=0)
    C_anion_in = a
    C_cation_in = a - b  # = a + |charge_fixed| si charge_fixed<0

    if C_anion_in < 0 or C_cation_in < 0:
        raise ValueError("no se encontró solución físicamente válida "
                          "(concentración negativa) — revisar signos de entrada")

    C_cation_out = C_salt_out
    C_anion_out = C_salt_out

    # Potencial de Donnan: E_Donnan = (R*T/F) * ln(C_cation_out/C_cation_in)
    #                     = -(R*T/F) * ln(C_anion_out/C_anion_in)  (deben coincidir)
    E_cation = (R * T_K / F) * math.log(C_cation_out / C_cation_in)
    E_anion = -(R * T_K / F) * math.log(C_anion_out / C_anion_in)

    # Desbalance osmótico (van't Hoff, número de partículas por lado)
    osmotic_in = C_cation_in + C_anion_in + Cf
    osmotic_out = C_cation_out + C_anion_out
    delta_osmotic = osmotic_in - osmotic_out  # >0 => tiende a entrar agua al compartimento "in"

    out = {
        "result": {
            "C_cation_in": C_cation_in, "C_anion_in": C_anion_in,
            "C_cation_out": C_cation_out, "C_anion_out": C_anion_out,
        },
        "donnan_potential_V": E_cation,
        "donnan_potential_check_V": E_anion,
        "delta_osmotic_mol_L": delta_osmotic,
        "units": "mol/L (concentraciones), V (potencial), mol/L (desbalance osmótico)",
        "method": "Equilibrio de Donnan, solución cuadrática exacta (electrolito 1:1) "
                  "vía electroneutralidad + igualdad de producto iónico; "
                  "potencial vía ecuación de Nernst para el ion permeable",
    }
    if abs(E_cation - E_anion) > 1e-9:
        out.setdefault("warnings", []).append(
            "inconsistencia numérica entre E_cation y E_anion, revisar inputs")
    if V_in is not None and V_out is not None:
        out["moles_water_shift_relative"] = delta_osmotic * V_in
    return out


# ---------------------------------------------------------------------------
# validate: smoke tests contra valores de referencia conocidos
# ---------------------------------------------------------------------------
def validate():
    checks = []

    # 1. concentration: dilución simple
    r = concentration("dilution", C1=None, V1=1.0, C2=0.1, V2=10.0)
    checks.append(("concentration.dilution", abs(r["result"] - 1.0) < 1e-9))

    # 2. ionic_strength: NaCl 0.1M -> I = 0.1
    r = ionic_strength([{"c": 0.1, "z": 1}, {"c": 0.1, "z": -1}])
    checks.append(("ionic_strength.NaCl", abs(r["result"] - 0.1) < 1e-9))

    # 3. activity_coefficient: Davies a I=0.1, z=1, T=25C, gamma esperado ~0.78
    r = activity_coefficient(z=1, ionic_strength_mol_L=0.1, model="davies")
    checks.append(("activity_coefficient.davies", 0.7 < r["result"] < 0.85))

    # 4. ph_calculation: HH con pKa=4.76 (acético), [A-]=[HA] -> pH=pKa
    r = ph_calculation("henderson_hasselbalch", pKa=4.76, conc_base=0.1, conc_acid=0.1)
    checks.append(("ph.henderson_hasselbalch", abs(r["result"] - 4.76) < 1e-9))

    # 5. solubility_product: AgCl, s=1.3e-5 -> Ksp~1.7e-10
    r = solubility_product("from_solubility", solubility_mol_L=1.3e-5, p=1, q=1)
    checks.append(("solubility_product.AgCl", 1.5e-10 < r["result"] < 1.9e-10))

    # 6. conductivity: NaCl limiting = lambda(Na+)+lambda(Cl-) = 126.4
    r = conductivity("limiting", cation="Na+", anion="Cl-")
    checks.append(("conductivity.limiting_NaCl", abs(r["result"] - 126.4) < 1e-6))

    # 7. diffusion_coefficient: Nernst-Einstein para H+ (movilidad conocida ~3.62e-7 m2/Vs)
    r = diffusion_coefficient("nernst_einstein", mobility_m2_Vs=3.62e-7, z=1, T_K=298.15)
    checks.append(("diffusion.nernst_einstein_H+", 8e-9 < r["result"] < 10e-9))

    # 8. electrophoretic_mobility: inversa de (7), debe recuperar ~3.62e-7
    r = electrophoretic_mobility("from_diffusion", z=1, D_m2_s=9.31e-9, T_K=298.15)
    checks.append(("electrophoretic_mobility.roundtrip", 3.4e-7 < r["result"] < 3.9e-7))

    # 9. donnan_equilibrium: macroión aniónico diluye co-ión, chequeo de balance
    r = donnan_equilibrium(C_salt_out=0.1, C_fixed_charge_in=0.05, z_fixed=-1)
    prod_in = r["result"]["C_cation_in"] * r["result"]["C_anion_in"]
    checks.append(("donnan.product_match", abs(prod_in - 0.01) < 1e-9))
    checks.append(("donnan.electroneutrality",
                    abs((r["result"]["C_cation_in"] - r["result"]["C_anion_in"]) - 0.05) < 1e-9))

    passed = sum(1 for _, ok in checks if ok)
    failed = [name for name, ok in checks if not ok]
    return {"passed": passed, "total": len(checks), "failed": failed,
            "status": "PASSED" if not failed else "FAILED"}


# ---------------------------------------------------------------------------
# Registro en tool_registry (mismo patrón que aminoacid_tool / sustainable_sourcing_tool)
# ---------------------------------------------------------------------------
TOOL_NAME = "ion_chemistry_tool"
TOOL_MODES = [
    "concentration", "ionic_strength", "activity_coefficient", "ph_calculation",
    "solubility_product", "conductivity", "diffusion_coefficient",
    "electrophoretic_mobility", "donnan_equilibrium", "validate",
]

try:
    from tool_registry import register_tool

    def _dispatch(mode, **kwargs):
        fn_map = {
            "concentration": concentration,
            "ionic_strength": ionic_strength,
            "activity_coefficient": activity_coefficient,
            "ph_calculation": ph_calculation,
            "solubility_product": solubility_product,
            "conductivity": conductivity,
            "diffusion_coefficient": diffusion_coefficient,
            "electrophoretic_mobility": electrophoretic_mobility,
            "donnan_equilibrium": donnan_equilibrium,
            "validate": lambda **kw: validate(),
        }
        if mode not in fn_map:
            raise ValueError(f"modo desconocido: {mode}. Modos válidos: {TOOL_MODES}")
        return fn_map[mode](**kwargs)

    register_tool(TOOL_NAME, _dispatch, modes=TOOL_MODES)

except ImportError:
    # Permite importar/testear el módulo standalone sin el registry del repo
    pass


if __name__ == "__main__":
    result = validate()
    print(result)
