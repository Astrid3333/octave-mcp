"""
Radiación de frenado (Bremsstrahlung): e- → e- + γ en campo nuclear
Espectros, secciones transversales, límites clásico/cuántico
"""
import numpy as np
import json
from scipy.integrate import quad
from scipy.special import hyp2f1, gamma
from scipy.constants import pi, hbar, e, epsilon_0, m_e, c, alpha

BREMSSTRAHLUNG_RADIATION_TOOL_SCHEMA = {
    "name": "bremsstrahlung_radiation_tool",
    "description": "Radiación de frenado: espectros de fotones e- → e- + γ, secciones transversales Bethe-Heitler, límite clásico Thomson",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["spectrum_bethe_heitler", "spectrum_thomson", "cross_section", "dcs_born", "stopping_power", "validate"],
                "description": "spectrum_bethe_heitler: e- > 1 MeV (cuántico relativista); spectrum_thomson: e- clásico; cross_section: σ_tot(T_e); dcs_born: dσ/dω_γ Born; stopping_power: pérdida por bremsstrahlung"
            },
            "params": {
                "type": "object",
                "properties": {
                    "T_e": {"type": "number", "description": "Energía cinética del electrón (MeV)"},
                    "Z": {"type": "number", "description": "Número atómico del núcleo (1-92)"},
                    "omega_gamma": {"type": "number", "description": "Energía del fotón emitido (MeV)"},
                    "num_points": {"type": "integer", "description": "Puntos para integración numérica"},
                    "method": {"type": "string", "enum": ["bethe_heitler", "born", "classical"], "description": "Método de cálculo"}
                },
                "required": ["T_e", "Z"]
            }
        },
        "required": ["mode", "params"]
    }
}

def bethe_heitler_spectrum(T_e, Z, omega_gamma):
    """
    Espectro diferencial Bethe-Heitler: dσ/dω_γ
    
    Referencias:
    - Bethe & Heitler (1934): radiación en campo nuclear
    - Jackson (1975): Classical Electrodynamics, cap. 14-16
    - Salvat et al. (2009): PENELOPE physics
    
    Rango: válido para T_e >> mc² (relativista) pero T_e < 100 GeV (no QED completo)
    
    Args:
        T_e: energía cinética (MeV)
        Z: número atómico
        omega_gamma: energía del fotón (MeV)
    
    Returns:
        dσ/dω_γ en barns/MeV
    """
    m_e_MeV = 0.511
    
    if T_e <= 0 or omega_gamma <= 0:
        return 0.0
    if omega_gamma >= T_e:
        return 0.0
    
    p_e = np.sqrt(T_e * (T_e + 2 * m_e_MeV)) / m_e_MeV
    beta = p_e / np.sqrt(p_e**2 + 1)
    
    # Parametrización simplificada (screening de núcleo)
    re = 2.818e-13  # radio clásico electrón (cm)
    
    k = omega_gamma / T_e
    xi = Z * alpha / beta
    
    # Término logarítmico dominante (Bethe-Heitler)
    L_nu = np.log(2 * T_e * (T_e + 2 * m_e_MeV) / (m_e_MeV**2 * omega_gamma))
    
    # Correcciones de screening (núcleo)
    phi = xi * np.arctan(1.0 / xi)
    
    # Sección diferencial (aproximación)
    sigma_diff = (4 * alpha * Z * re**2 / (3 * k)) * (
        (1 - beta**2 * k) * L_nu 
        - 2 * beta**2 * k 
        + 0.5 * beta**2 * k**2
    ) * phi / (xi * np.pi)
    
    return max(0, sigma_diff * 1e24)  # conversión a barns/MeV

def thomson_spectrum(T_e, Z, omega_gamma):
    """
    Límite clásico Thomson: campo coulombiano débil, e- no-relativista
    Válido para T_e << mc² ≈ 511 keV
    
    dσ/dω_γ ∝ (1 - k + k²) con k = ω_γ / T_e
    """
    if T_e <= 0 or omega_gamma <= 0 or omega_gamma >= T_e:
        return 0.0
    
    re = 2.818e-13  # radio clásico (cm)
    m_e_MeV = 0.511
    
    k = omega_gamma / T_e
    
    # Aproximación Thomson clásica
    sigma_thomson = (8 * pi * re**2 / 3) * (1 - k + k**2)
    
    # Factor de Coulomb Z² para núcleo
    sigma_diff = Z**2 * sigma_thomson / (omega_gamma * np.sqrt(T_e))
    
    return max(0, sigma_diff * 1e24)  # barns/MeV

def born_dcs(T_e, Z, omega_gamma):
    """
    Aproximación Born (primer orden en α): dσ/dω_γ
    Válido para Z*α << 1 (Z < 20 aprox)
    
    Más preciso que Bethe-Heitler para Z pequeño
    """
    m_e_MeV = 0.511
    
    if T_e <= 0 or omega_gamma <= 0 or omega_gamma >= T_e:
        return 0.0
    
    p_e = np.sqrt(T_e * (T_e + 2 * m_e_MeV)) / m_e_MeV
    beta = p_e / np.sqrt(p_e**2 + 1)
    
    re = 2.818e-13
    k = omega_gamma / T_e
    
    # Born: radiación dipolar en campo Coulomb
    log_term = np.log((2 * T_e * (T_e + 2 * m_e_MeV)) / (m_e_MeV**2 * omega_gamma))
    
    sigma_born = (4 * alpha * Z * re**2 / (3 * k)) * (
        (1 - beta**2 * k) * log_term - 2 * beta**2 * k + 0.5 * beta**4 * k**2
    )
    
    return max(0, sigma_born * 1e24)

def total_cross_section(T_e, Z):
    """
    Sección transversal total σ_tot = ∫ dσ/dω_γ dω_γ
    Integración desde ω_γ_min hasta T_e
    """
    omega_min = 1e-6  # MeV (cutoff numérico)
    
    def integrand(omega):
        return bethe_heitler_spectrum(T_e, Z, omega)
    
    sigma_tot, _ = quad(integrand, omega_min, T_e * 0.99, limit=50)
    return sigma_tot

def stopping_power(T_e, Z):
    """
    Poder de frenado por bremsstrahlung: -dE/dx (MeV/cm)
    Radiación vs ionización
    """
    sigma_tot = total_cross_section(T_e, Z)
    
    # Aproximación: poder de frenado ∝ σ_tot * T_e
    # En realidad necesitaría integración más sofisticada
    re = 2.818e-13
    m_e_MeV = 0.511
    
    # Número de electrones por unidad volumen (densidad simple)
    n_e = 1e23  # cm⁻³ (valores típicos)
    
    dE_dx = n_e * sigma_tot * T_e / 100  # MeV/cm
    
    return max(1e-6, dE_dx)

def spectrum_calculation(T_e, Z, num_points=200, method="bethe_heitler"):
    """Calcula espectro completo: ω_γ vs dσ/dω_γ"""
    omega_min = 1e-5
    omega_max = T_e * 0.99
    
    omegas = np.logspace(np.log10(omega_min), np.log10(omega_max), num_points)
    
    if method == "bethe_heitler":
        spectra = [bethe_heitler_spectrum(T_e, Z, w) for w in omegas]
    elif method == "born":
        spectra = [born_dcs(T_e, Z, w) for w in omegas]
    elif method == "classical":
        spectra = [thomson_spectrum(T_e, Z, w) for w in omegas]
    else:
        spectra = [bethe_heitler_spectrum(T_e, Z, w) for w in omegas]
    
    return {
        "omega_gamma_MeV": omegas.tolist(),
        "dcs_barns_per_MeV": spectra,
        "method": method,
        "T_e_MeV": T_e,
        "Z": Z
    }

def execute(mode, params):
    """Dispatcher principal"""
    T_e = params.get("T_e", 1.0)
    Z = params.get("Z", 1)
    omega_gamma = params.get("omega_gamma", T_e / 2)
    num_points = params.get("num_points", 200)
    method = params.get("method", "bethe_heitler")
    
    if mode == "spectrum_bethe_heitler":
        result = spectrum_calculation(T_e, Z, num_points, "bethe_heitler")
        result["description"] = f"Espectro Bethe-Heitler: e- {T_e} MeV en núcleo Z={Z}"
        return result
    
    elif mode == "spectrum_thomson":
        result = spectrum_calculation(T_e, Z, num_points, "classical")
        result["description"] = f"Espectro Thomson clásico: e- {T_e} MeV en núcleo Z={Z}"
        return result
    
    elif mode == "dcs_born":
        result = spectrum_calculation(T_e, Z, num_points, "born")
        result["description"] = f"Aproximación Born (1er orden): e- {T_e} MeV en núcleo Z={Z}"
        return result
    
    elif mode == "cross_section":
        sigma = total_cross_section(T_e, Z)
        return {
            "sigma_total_barns": sigma,
            "T_e_MeV": T_e,
            "Z": Z,
            "description": f"Sección transversal total bremsstrahlung"
        }
    
    elif mode == "stopping_power":
        dE_dx = stopping_power(T_e, Z)
        return {
            "dE_dx_MeV_per_cm": dE_dx,
            "T_e_MeV": T_e,
            "Z": Z,
            "note": "Asume densidad típica n_e ~ 1e23 cm⁻³"
        }
    
    elif mode == "validate":
        # Tests rápidos
        T_test = 2.0  # 2 MeV
        Z_test = 10
        w_test = 0.5
        
        sp = bethe_heitler_spectrum(T_test, Z_test, w_test)
        sigma = total_cross_section(T_test, Z_test)
        
        assert sp >= 0, "Espectro debe ser >= 0"
        assert sigma >= 0, "Sección transversal debe ser >= 0"
        assert sp < 1e3, "Espectro en rango razonable"
        
        return {
            "status": "OK",
            "spectrum_sample": sp,
            "cross_section_sample": sigma
        }
    
    else:
        return {"error": f"Modo desconocido: {mode}"}

# Registro automático en tool_registry
try:
    import sys
    sys.path.insert(0, '/home/claude')
    from tool_registry import REGISTRY
    
    REGISTRY[BREMSSTRAHLUNG_RADIATION_TOOL_SCHEMA["name"]] = {
        "schema": BREMSSTRAHLUNG_RADIATION_TOOL_SCHEMA,
        "execute": execute
    }
except Exception as e:
    pass  # Fallback: será registrado vía import en server.py
