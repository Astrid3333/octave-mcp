#!/usr/bin/env python3
"""
soil_mixture_tool.py
Mixture theory for soil and soil organic matter (SOM).

Core Concepts:
  - Three-phase model: soil solids + water + air (void ratio e)
  - Organic matter fraction within solid phase
  - Density relations: bulk (ρ_b), particle (ρ_p), specific for SOM
  - Porosity n = e/(1+e)
  - Hydro-thermal properties modeled as weighted averages

References:
  - Zhao & Jackson (2008): Hydro-thermal modeling with organic matter
  - Hillel (1998): Soil physics fundamentals

Modes:
  - volumetric_fractions: compute void ratio, porosity, saturation
  - organic_matter_estimate: estimate SOM% from organic carbon / loss-on-ignition
  - effective_properties: compute thermal/hydraulic properties via mixture rule
  - validate: 8-check self-test
"""

import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

# ============================================================================
# DATA STRUCTURES & CONSTANTS
# ============================================================================

@dataclass
class SoilPhaseComposition:
    """Three-phase soil model: solids, water, air."""
    bulk_density: float       # ρ_b [g/cm³], soil as received
    particle_density: float   # ρ_p [g/cm³], solid phase (quartz ~2.65)
    water_content_mass: float # w [%] or [fraction], mass of water / mass of dry soil
    water_density: float      # ρ_w [g/cm³], typically 1.0


@dataclass
class SoilOrganicMatter:
    """Organic matter component of soil solids."""
    mass_fraction: float      # [0, 1] mass fraction of organic matter in solids
    density_som: float        # [g/cm³] specific density of organic matter, ~1.3-1.5
    thermal_conductivity: float  # [W/(m·K)], typically 0.25-0.50
    volumetric_heat_capacity: float  # [J/(m³·K)], typically 1.5e6-2.0e6


# Physical constants
QUARTZ_DENSITY = 2.65       # g/cm³
WATER_DENSITY = 1.0         # g/cm³
WATER_THERMAL_COND = 0.6    # W/(m·K)
AIR_THERMAL_COND = 0.026    # W/(m·K)
MINERAL_THERMAL_COND = 2.0  # W/(m·K), typical sand/silt
MINERAL_HEAT_CAPACITY = 2.3e6  # J/(m³·K)
WATER_HEAT_CAPACITY = 4.18e6  # J/(m³·K)


# ============================================================================
# VOLUMETRIC RELATIONS
# ============================================================================

def void_ratio_from_bulk_density(
    bulk_density: float,
    particle_density: float = QUARTZ_DENSITY
) -> float:
    """
    Calculate void ratio e from bulk and particle density.
    
    e = (ρ_p - ρ_b) / ρ_b = ρ_p / ρ_b - 1
    
    Args:
        bulk_density: ρ_b [g/cm³]
        particle_density: ρ_p [g/cm³]
    
    Returns:
        e: void ratio (dimensionless)
    """
    assert bulk_density > 0, "Bulk density must be positive"
    assert particle_density > bulk_density, "Particle density must exceed bulk density"
    
    e = (particle_density - bulk_density) / bulk_density
    return e


def porosity_from_void_ratio(void_ratio: float) -> float:
    """
    Calculate porosity n from void ratio.
    
    n = e / (1 + e)
    
    Args:
        void_ratio: e (dimensionless)
    
    Returns:
        n: porosity, [0, 1]
    """
    assert void_ratio >= 0, "Void ratio must be non-negative"
    n = void_ratio / (1.0 + void_ratio)
    return n


def bulk_density_from_void_ratio(
    void_ratio: float,
    particle_density: float = QUARTZ_DENSITY
) -> float:
    """
    Inverse: calculate bulk density from void ratio.
    
    ρ_b = ρ_p / (1 + e)
    
    Args:
        void_ratio: e
        particle_density: ρ_p [g/cm³]
    
    Returns:
        ρ_b: bulk density [g/cm³]
    """
    rho_b = particle_density / (1.0 + void_ratio)
    return rho_b


def degree_of_saturation(
    water_content_mass: float,
    void_ratio: float,
    particle_density: float = QUARTZ_DENSITY,
    water_density: float = WATER_DENSITY
) -> float:
    """
    Calculate degree of saturation S_r from gravimetric water content.
    
    S_r = w · ρ_b / (e · ρ_w)
       = w · ρ_p / (e · ρ_w · (1 + e))
    
    where w is gravimetric water content (mass water / mass dry soil).
    
    Args:
        water_content_mass: w [0, 1] or [%]
        void_ratio: e
        particle_density: ρ_p [g/cm³]
        water_density: ρ_w [g/cm³]
    
    Returns:
        S_r: degree of saturation [0, 1]
    """
    # Convert percentage to fraction if needed
    if water_content_mass > 1.0:
        water_content_mass = water_content_mass / 100.0
    
    rho_b = bulk_density_from_void_ratio(void_ratio, particle_density)
    
    S_r = (water_content_mass * rho_b) / (void_ratio * water_density)
    S_r = np.clip(S_r, 0.0, 1.0)
    
    return S_r


def volumetric_water_content(
    gravimetric_water_content: float,
    void_ratio: float,
    particle_density: float = QUARTZ_DENSITY,
    water_density: float = WATER_DENSITY
) -> float:
    """
    Convert gravimetric water content to volumetric.
    
    θ = w · ρ_b / ρ_w
    
    Args:
        gravimetric_water_content: w [fraction]
        void_ratio: e
        particle_density: ρ_p [g/cm³]
        water_density: ρ_w [g/cm³]
    
    Returns:
        θ: volumetric water content [m³/m³] (dimensionless)
    """
    if gravimetric_water_content > 1.0:
        gravimetric_water_content /= 100.0
    
    rho_b = bulk_density_from_void_ratio(void_ratio, particle_density)
    theta = (gravimetric_water_content * rho_b) / water_density
    
    return theta


# ============================================================================
# ORGANIC MATTER PROPERTIES
# ============================================================================

def estimate_som_from_organic_carbon(organic_carbon_pct: float) -> float:
    """
    Estimate soil organic matter (SOM %) from organic carbon %.
    
    SOM ≈ 1.72 · OC  (empirical Van Bemmelen factor, range [1.5, 2.0])
    
    Args:
        organic_carbon_pct: OC [%, 0-10 typical]
    
    Returns:
        SOM [%]
    """
    van_bemmelen_factor = 1.72
    som_pct = van_bemmelen_factor * organic_carbon_pct
    return float(som_pct)


def estimate_som_from_loss_on_ignition(loi_pct: float) -> float:
    """
    Estimate SOM from loss-on-ignition (LOI).
    
    LOI measures mass loss at ~375-550°C, includes:
      - Organic matter (~85-95% of LOI)
      - Hygroscopic water & crystal water (~5-15% of LOI)
    
    SOM ≈ 0.9 · LOI  (conservative estimate)
    
    Args:
        loi_pct: LOI [%]
    
    Returns:
        SOM [%]
    """
    som_pct = 0.9 * loi_pct
    return float(som_pct)


def soil_solid_fraction_from_som(som_pct: float) -> float:
    """
    Calculate mass fraction of organic matter in solid phase.
    
    f_om = SOM / 100, but account for typical soil composition:
    SOM typically [0, 15%] in agricultural soils
    
    Args:
        som_pct: SOM [%]
    
    Returns:
        f_om: mass fraction of organic matter in solids [0, 1]
    """
    f_om = np.clip(som_pct / 100.0, 0.0, 1.0)
    return f_om


def particle_density_with_som(
    mineral_density: float,
    som_density: float,
    som_mass_fraction: float
) -> float:
    """
    Effective particle density accounting for organic matter.
    
    ρ_p,eff = 1 / (f_min/ρ_min + f_om/ρ_om)
    
    where f_min = 1 - f_om.
    
    Args:
        mineral_density: ρ_min [g/cm³], typically 2.65 (quartz)
        som_density: ρ_om [g/cm³], typically 1.3-1.5
        som_mass_fraction: f_om [0, 1]
    
    Returns:
        ρ_p,eff: effective particle density [g/cm³]
    """
    f_min = 1.0 - som_mass_fraction
    
    # Harmonic mean (volume-weighted)
    if som_mass_fraction == 0:
        return mineral_density
    
    rho_p_eff = 1.0 / (f_min / mineral_density + som_mass_fraction / som_density)
    return float(rho_p_eff)


# ============================================================================
# EFFECTIVE PROPERTIES (MIXTURE RULE)
# ============================================================================

def effective_thermal_conductivity(
    porosity: float,
    degree_saturation: float,
    som_fraction: float = 0.0,
    mineral_k: float = MINERAL_THERMAL_COND,
    som_k: float = 0.35,
    water_k: float = WATER_THERMAL_COND,
    air_k: float = AIR_THERMAL_COND
) -> float:
    """
    Effective thermal conductivity using parallel/series mixture rule.
    
    For partially saturated soil:
      K_eff ≈ K_min^(1-n) · K_water^(n·S_r) · K_air^(n·(1-S_r))
    
    Simplified linear combination with SOM:
      K_solid = (1-f_om)·K_min + f_om·K_som
      K_eff = (1-n)·K_solid + n·[S_r·K_water + (1-S_r)·K_air]
    
    Args:
        porosity: n [0, 1]
        degree_saturation: S_r [0, 1]
        som_fraction: f_om [0, 1]
        mineral_k: K_min [W/(m·K)]
        som_k: K_som [W/(m·K)]
        water_k: K_w [W/(m·K)]
        air_k: K_a [W/(m·K)]
    
    Returns:
        K_eff: effective thermal conductivity [W/(m·K)]
    """
    k_solid = (1.0 - som_fraction) * mineral_k + som_fraction * som_k
    k_pore = degree_saturation * water_k + (1.0 - degree_saturation) * air_k
    
    k_eff = (1.0 - porosity) * k_solid + porosity * k_pore
    
    return float(k_eff)


def effective_heat_capacity(
    porosity: float,
    degree_saturation: float,
    bulk_density: float,
    som_fraction: float = 0.0,
    mineral_cp: float = MINERAL_HEAT_CAPACITY,
    som_cp: float = 1.8e6,
    water_cp: float = WATER_HEAT_CAPACITY
) -> float:
    """
    Volumetric heat capacity C_eff.
    
    C_eff = ρ_b · (1-n) · [c_p,min + f_om·(c_p,som - c_p,min)]
          + ρ_w · n · S_r · c_p,water
    
    Args:
        porosity: n [0, 1]
        degree_saturation: S_r [0, 1]
        bulk_density: ρ_b [kg/m³] or normalized
        som_fraction: f_om [0, 1]
        mineral_cp: [J/(kg·K)] or [J/(m³·K)] normalized
        som_cp: [J/(kg·K)]
        water_cp: [J/(kg·K)]
    
    Returns:
        C_eff: volumetric heat capacity [J/(m³·K)]
    """
    # Convert bulk density to kg/m³ if in g/cm³
    if bulk_density < 10:
        bulk_density *= 1000  # g/cm³ → kg/m³
    
    water_density_kg_m3 = 1000  # kg/m³
    
    # Solid phase contribution
    c_solid = (1.0 - som_fraction) * mineral_cp + som_fraction * som_cp
    c_solid_vol = bulk_density * (1.0 - porosity) * c_solid
    
    # Pore fluid contribution
    c_water_vol = water_density_kg_m3 * porosity * degree_saturation * water_cp
    
    c_eff = c_solid_vol + c_water_vol
    
    return float(c_eff)


# ============================================================================
# MAIN DISPATCHER
# ============================================================================

def run(mode: str, params: Dict) -> Dict:
    """
    Main dispatcher for soil_mixture_tool.
    
    Modes:
      - 'volumetric_fractions': compute e, n, S_r, θ
      - 'organic_matter_estimate': estimate SOM% from OC or LOI
      - 'effective_properties': compute K_eff, C_eff
      - 'validate': 8-check self-test
    """
    
    if mode == "volumetric_fractions":
        return _mode_volumetric_fractions(params)
    
    elif mode == "organic_matter_estimate":
        return _mode_organic_matter(params)
    
    elif mode == "effective_properties":
        return _mode_effective_properties(params)
    
    elif mode == "validate":
        return _mode_validate()
    
    else:
        return {"error": f"Unknown mode: {mode}"}


def _mode_volumetric_fractions(params: Dict) -> Dict:
    """Calculate volumetric fractions."""
    try:
        bulk_density = params["bulk_density_g_cm3"]
        particle_density = params.get("particle_density_g_cm3", QUARTZ_DENSITY)
        water_content_mass = params["water_content_mass_fraction"]
        
        e = void_ratio_from_bulk_density(bulk_density, particle_density)
        n = porosity_from_void_ratio(e)
        S_r = degree_of_saturation(water_content_mass, e, particle_density)
        theta = volumetric_water_content(water_content_mass, e, particle_density)
        
        return {
            "success": True,
            "bulk_density_g_cm3": bulk_density,
            "particle_density_g_cm3": particle_density,
            "water_content_mass_fraction": water_content_mass,
            "void_ratio_e": float(e),
            "porosity_n": float(n),
            "degree_of_saturation_sr": float(S_r),
            "volumetric_water_content_theta": float(theta),
            "notes": "Three-phase model: solids + water + air"
        }
    
    except Exception as e:
        return {"error": str(e)}


def _mode_organic_matter(params: Dict) -> Dict:
    """Estimate SOM from OC or LOI."""
    try:
        som_pct = None
        
        if "organic_carbon_pct" in params:
            som_pct = estimate_som_from_organic_carbon(params["organic_carbon_pct"])
            source = "Van Bemmelen (1.72× factor)"
        
        elif "loss_on_ignition_pct" in params:
            som_pct = estimate_som_from_loss_on_ignition(params["loss_on_ignition_pct"])
            source = "Loss-on-ignition (0.9× factor)"
        
        else:
            return {"error": "Provide either organic_carbon_pct or loss_on_ignition_pct"}
        
        f_om = soil_solid_fraction_from_som(som_pct)
        
        # Effective particle density if SOM is included
        mineral_density = params.get("mineral_density_g_cm3", QUARTZ_DENSITY)
        som_density = params.get("som_density_g_cm3", 1.4)
        rho_p_eff = particle_density_with_som(mineral_density, som_density, f_om)
        
        return {
            "success": True,
            "som_pct": float(som_pct),
            "som_mass_fraction": float(f_om),
            "estimation_method": source,
            "mineral_density_g_cm3": mineral_density,
            "som_density_g_cm3": som_density,
            "effective_particle_density_g_cm3": float(rho_p_eff),
            "notes": "Higher SOM → lower effective particle density"
        }
    
    except Exception as e:
        return {"error": str(e)}


def _mode_effective_properties(params: Dict) -> Dict:
    """Calculate effective thermal and hydro properties."""
    try:
        porosity = params["porosity"]
        degree_saturation = params["degree_of_saturation"]
        bulk_density = params.get("bulk_density_g_cm3", 1.4)
        som_fraction = params.get("som_mass_fraction", 0.0)
        
        k_eff = effective_thermal_conductivity(
            porosity=porosity,
            degree_saturation=degree_saturation,
            som_fraction=som_fraction
        )
        
        c_eff = effective_heat_capacity(
            porosity=porosity,
            degree_saturation=degree_saturation,
            bulk_density=bulk_density,
            som_fraction=som_fraction
        )
        
        return {
            "success": True,
            "porosity": porosity,
            "degree_of_saturation": degree_saturation,
            "som_mass_fraction": som_fraction,
            "effective_thermal_conductivity_W_m_K": float(k_eff),
            "volumetric_heat_capacity_J_m3_K": float(c_eff),
            "thermal_diffusivity_m2_s": float(k_eff / c_eff) if c_eff > 0 else 0,
            "notes": "For land surface models (CLM, JULES, STEMMUS)"
        }
    
    except Exception as e:
        return {"error": str(e)}


def _mode_validate() -> Dict:
    """Self-test: 8 validation checks."""
    checks_passed = 0
    checks_total = 8
    details = []
    
    try:
        # Check 1: Void ratio positive and reasonable
        e = void_ratio_from_bulk_density(1.4, QUARTZ_DENSITY)
        if 0.5 < e < 1.0:
            checks_passed += 1
            details.append(f"✓ Check 1: Void ratio e={e:.3f} in reasonable range [0.5, 1.0]")
        else:
            details.append(f"✗ Check 1: Void ratio out of range: {e}")
        
        # Check 2: Porosity in [0, 1]
        n = porosity_from_void_ratio(e)
        if 0.3 < n < 0.7:
            checks_passed += 1
            details.append(f"✓ Check 2: Porosity n={n:.3f} in [0.3, 0.7]")
        else:
            details.append(f"✗ Check 2: Porosity out of range: {n}")
        
        # Check 3: Saturation degree in [0, 1]
        S_r = degree_of_saturation(0.2, e, QUARTZ_DENSITY)
        if 0 <= S_r <= 1.0:
            checks_passed += 1
            details.append(f"✓ Check 3: Degree of saturation S_r={S_r:.3f} ∈ [0, 1]")
        else:
            details.append(f"✗ Check 3: S_r out of range: {S_r}")
        
        # Check 4: Van Bemmelen factor (OC → SOM)
        som = estimate_som_from_organic_carbon(5.0)
        if 8.0 < som < 9.0:
            checks_passed += 1
            details.append(f"✓ Check 4: SOM={som:.2f}% from OC=5% (Van Bemmelen 1.72×)")
        else:
            details.append(f"✗ Check 4: SOM estimate incorrect: {som}")
        
        # Check 5: LOI conversion
        som_loi = estimate_som_from_loss_on_ignition(10.0)
        if 8.0 < som_loi < 9.2:
            checks_passed += 1
            details.append(f"✓ Check 5: SOM={som_loi:.2f}% from LOI=10% (0.9× factor)")
        else:
            details.append(f"✗ Check 5: LOI conversion incorrect: {som_loi}")
        
        # Check 6: Effective particle density decreases with SOM
        rho_p_min = particle_density_with_som(QUARTZ_DENSITY, 1.4, 0.0)
        rho_p_som = particle_density_with_som(QUARTZ_DENSITY, 1.4, 0.1)
        
        if rho_p_som < rho_p_min:
            checks_passed += 1
            details.append(f"✓ Check 6: Effective ρ_p decreases with SOM ({rho_p_min:.3f} → {rho_p_som:.3f})")
        else:
            details.append(f"✗ Check 6: SOM effect inverted")
        
        # Check 7: Thermal conductivity increases with saturation
        k_dry = effective_thermal_conductivity(n, 0.0)
        k_wet = effective_thermal_conductivity(n, 1.0)
        
        if k_wet > k_dry:
            checks_passed += 1
            details.append(f"✓ Check 7: K_eff increases with S_r ({k_dry:.3f} → {k_wet:.3f} W/m·K)")
        else:
            details.append(f"✗ Check 7: Thermal conductivity trend wrong")
        
        # Check 8: Heat capacity increases with saturation
        c_dry = effective_heat_capacity(n, 0.0, 1400.0)
        c_wet = effective_heat_capacity(n, 1.0, 1400.0)
        
        if c_wet > c_dry:
            checks_passed += 1
            details.append(f"✓ Check 8: C_eff increases with S_r ({c_dry:.2e} → {c_wet:.2e} J/m³·K)")
        else:
            details.append(f"✗ Check 8: Heat capacity trend wrong")
    
    except Exception as e:
        details.append(f"✗ Validation exception: {e}")
    
    return {
        "mode": "validate",
        "passed": checks_passed,
        "total": checks_total,
        "success": checks_passed == checks_total,
        "details": details
    }


# ============================================================================
# INPUT SCHEMA (MCP)
# ============================================================================

inputSchema = {
    "volumetric_fractions": {
        "type": "object",
        "properties": {
            "bulk_density_g_cm3": {"type": "number", "description": "ρ_b [g/cm³], typical [1.0, 1.8]"},
            "particle_density_g_cm3": {"type": "number", "description": "ρ_p [g/cm³], default 2.65"},
            "water_content_mass_fraction": {"type": "number", "description": "w [0, 1] or [%]"}
        },
        "required": ["bulk_density_g_cm3", "water_content_mass_fraction"]
    },
    "organic_matter_estimate": {
        "type": "object",
        "properties": {
            "organic_carbon_pct": {"type": "number", "description": "OC [%], optional"},
            "loss_on_ignition_pct": {"type": "number", "description": "LOI [%], optional"},
            "mineral_density_g_cm3": {"type": "number", "description": "default 2.65"},
            "som_density_g_cm3": {"type": "number", "description": "default 1.4"}
        },
        "required": []
    },
    "effective_properties": {
        "type": "object",
        "properties": {
            "porosity": {"type": "number", "description": "n [0, 1]"},
            "degree_of_saturation": {"type": "number", "description": "S_r [0, 1]"},
            "bulk_density_g_cm3": {"type": "number", "description": "for C_eff, default 1.4"},
            "som_mass_fraction": {"type": "number", "description": "[0, 1], default 0"}
        },
        "required": ["porosity", "degree_of_saturation"]
    },
    "validate": {
        "type": "object",
        "properties": {}
    }
}


if __name__ == "__main__":
    print("soil_mixture_tool.py loaded. Running smoke tests...\n")
    
    result = run("validate", {})
    print(f"Validation: {result['passed']}/{result['total']} checks passed\n")
    for detail in result["details"]:
        print(f"  {detail}")
    
    # Example: volumetric fractions
    print("\n--- Example: Soil Composition ---")
    ex = run("volumetric_fractions", {
        "bulk_density_g_cm3": 1.4,
        "water_content_mass_fraction": 0.15
    })
    if "success" in ex:
        print(f"Void ratio e: {ex['void_ratio_e']:.3f}")
        print(f"Porosity n: {ex['porosity_n']:.3f} ({ex['porosity_n']*100:.1f}%)")
        print(f"Degree of saturation S_r: {ex['degree_of_saturation_sr']:.3f}")
        print(f"Volumetric water content θ: {ex['volumetric_water_content_theta']:.3f} m³/m³")


# ============================================================================
# TOOL REGISTRATION (auto-agregado)
# ============================================================================

TOOL_SCHEMA = {
    "name": 'soil_mixture_tool',
    "description": 'Relaciones volumetricas de 3 fases y propiedades termicas efectivas del suelo, con contabilidad de materia organica (SOM).',
    "inputSchema": {
        "type": "object",
        "properties": {'bulk_density_g_cm3': {'description': 'ρ_b [g/cm³], typical [1.0, 1.8]', 'type': 'number'},
 'degree_of_saturation': {'description': 'S_r [0, 1]', 'type': 'number'},
 'loss_on_ignition_pct': {'description': 'LOI [%], optional', 'type': 'number'},
 'mineral_density_g_cm3': {'description': 'default 2.65', 'type': 'number'},
 'mode': {'description': 'Modo de operacion',
          'enum': ['volumetric_fractions',
                   'organic_matter_estimate',
                   'effective_properties',
                   'validate'],
          'type': 'string'},
 'organic_carbon_pct': {'description': 'OC [%], optional', 'type': 'number'},
 'particle_density_g_cm3': {'description': 'ρ_p [g/cm³], default 2.65', 'type': 'number'},
 'porosity': {'description': 'n [0, 1]', 'type': 'number'},
 'som_density_g_cm3': {'description': 'default 1.4', 'type': 'number'},
 'som_mass_fraction': {'description': '[0, 1], default 0', 'type': 'number'},
 'water_content_mass_fraction': {'description': 'w [0, 1] or [%]', 'type': 'number'}},
        "required": ["mode"],
    },
}


def _handler(arguments):
    mode = arguments.get("mode", "validate")
    result = run(mode, arguments)
    if mode == "validate" and isinstance(result, dict) and "passed" in result and "total" in result:
        details = result.get("details", [])
        return {
            "validation_passed": result.get("passed", 0) == result.get("total", 0),
            "checks": [
                {"name": f"check_{i}", "passed": "\u2713" in str(d), "detail": str(d)}
                for i, d in enumerate(details)
            ],
            "n_checks": result.get("total", 0),
            "n_passed": result.get("passed", 0),
        }
    return result


def _register():
    try:
        import tool_registry
        tool_registry.register_tool(TOOL_SCHEMA["name"], TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()
