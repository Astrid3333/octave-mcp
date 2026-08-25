#!/usr/bin/env python3
"""
soil_mechanics_tool.py
Soil mechanics plasticity criteria for failure prediction.

Core Models:
  - Mohr-Coulomb: τ = c + σ·tan(φ), factor of safety F = (c + σ_n·tan(φ)) / τ_shear
  - Burzyński-Drucker-Prager (cone criterion): √J₂ = α·I₁ + k (smooth cap)
  - Modified Cam-Clay: elliptical yield surface for clay consolidation/shear
  
Modes:
  - mohr_coulomb: compute shear strength and factor of safety
  - drucker_prager: compute yield surface / safety margin
  - cam_clay: simulate clay consolidation + undrained shear
  - validate: 8-check self-test against reference cases
"""

import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import json

# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class SoilStrengthParams:
    """Soil strength parameters (Mohr-Coulomb)."""
    cohesion_c: float         # [kPa] or [Pa], cohesion
    friction_angle_deg: float # [°] internal friction angle φ
    adhesion: float           # [kPa] adhesion to interface (adhesion ≤ c typically)
    
    def __post_init__(self):
        assert self.cohesion_c >= 0, f"Cohesion must be ≥ 0, got {self.cohesion_c}"
        assert 0 <= self.friction_angle_deg <= 45, f"φ out of range [0, 45]°"
        assert 0 <= self.adhesion <= self.cohesion_c, f"Adhesion > cohesion"


@dataclass
class DruckerPragerParams:
    """Drucker-Prager plasticity parameters."""
    k: float                  # [MPa] yield parameter (equiv to cohesion)
    alpha: float              # [-] material parameter, related to φ
    # For association: α = 2·sin(φ) / √(3·(3 - sin(φ)))


@dataclass
class CamClayParams:
    """Modified Cam-Clay model parameters for clay."""
    lambda_cc: float          # [-] compression index (slope of virgin consolidation line)
    kappa: float              # [-] swelling index (slope of unload-reload line)
    m: float                  # [-] critical state line slope (M = tan(φ_cs))
    p_ref: float              # [kPa] reference pressure (typically 1 kPa or 100 kPa)
    preconsolidation_pressure_pc: float  # [kPa] preconsolidation pressure


@dataclass
class StressState:
    """3D stress state (σ_xx, σ_yy, σ_zz, τ_xy, τ_yz, τ_zx)."""
    sigma_1: float            # [kPa] major principal stress
    sigma_2: float            # [kPa] intermediate principal stress
    sigma_3: float            # [kPa] minor principal stress
    
    @property
    def mean_pressure(self) -> float:
        """p = (σ₁ + σ₂ + σ₃) / 3"""
        return (self.sigma_1 + self.sigma_2 + self.sigma_3) / 3.0
    
    @property
    def deviator_stress(self) -> float:
        """q = √(1.5·J₂), where J₂ = (1/6)·Σ(σ_i - σ_j)²"""
        s1_s3 = self.sigma_1 - self.sigma_3
        return s1_s3  # for simple shear case
    
    @property
    def j2_invariant(self) -> float:
        """Second invariant of deviatoric stress tensor."""
        diff = self.sigma_1 - self.sigma_3
        return (diff**2) / 6.0


# ============================================================================
# MOHR-COULOMB MODEL
# ============================================================================

def mohr_coulomb_shear_strength(
    normal_stress: np.ndarray,
    params: SoilStrengthParams
) -> np.ndarray:
    """
    Mohr-Coulomb shear strength envelope.
    
    τ_f = c + σ_n · tan(φ)
    
    Args:
        normal_stress: effective normal stress [kPa], shape (N,)
        params: SoilStrengthParams
    
    Returns:
        τ_f: shear strength [kPa], shape (N,)
    """
    sigma_n = np.asarray(normal_stress)
    phi_rad = np.radians(params.friction_angle_deg)
    
    tau_f = params.cohesion_c + sigma_n * np.tan(phi_rad)
    return np.maximum(tau_f, 0.0)


def mohr_coulomb_factor_of_safety(
    sigma_n: float,
    tau_applied: float,
    params: SoilStrengthParams
) -> Dict:
    """
    Factor of safety under Mohr-Coulomb criterion.
    
    F = τ_f / τ_applied = (c + σ_n·tan(φ)) / τ_applied
    
    F > 1: safe
    F = 1: failure
    F < 1: unsafe
    
    Args:
        sigma_n: effective normal stress [kPa]
        tau_applied: applied shear stress [kPa]
        params: SoilStrengthParams
    
    Returns:
        Dict with F, τ_f, status
    """
    phi_rad = np.radians(params.friction_angle_deg)
    
    tau_f = params.cohesion_c + sigma_n * np.tan(phi_rad)
    
    if tau_applied <= 0:
        return {
            "factor_of_safety": float('inf'),
            "shear_strength_kpa": tau_f,
            "applied_shear_kpa": tau_applied,
            "status": "safe (no shear loading)"
        }
    
    f = tau_f / tau_applied
    
    if f > 1.0:
        status = "safe"
    elif abs(f - 1.0) < 0.01:
        status = "critical"
    else:
        status = "failure"
    
    return {
        "factor_of_safety": float(f),
        "shear_strength_kpa": float(tau_f),
        "applied_shear_kpa": float(tau_applied),
        "status": status,
        "friction_angle_deg": params.friction_angle_deg,
        "cohesion_c_kpa": params.cohesion_c
    }


def failure_plane_angle(friction_angle_deg: float) -> float:
    """
    Angle of failure plane relative to horizontal (Mohr-Coulomb).
    
    θ_f = 45° + φ/2
    
    Args:
        friction_angle_deg: internal friction angle [°]
    
    Returns:
        Failure plane angle [°]
    """
    return 45.0 + friction_angle_deg / 2.0


# ============================================================================
# DRUCKER-PRAGER MODEL
# ============================================================================

def drucker_prager_yield(
    stress_state: StressState,
    params: DruckerPragerParams
) -> Dict:
    """
    Drucker-Prager (cone) yield criterion.
    
    √J₂ = α·I₁ + k
    
    Args:
        stress_state: StressState (σ₁, σ₂, σ₃)
        params: DruckerPragerParams
    
    Returns:
        Dict with yield value, margin, safety factor
    """
    I1 = stress_state.mean_pressure * 3.0  # I₁ = σ₁ + σ₂ + σ₃
    J2 = stress_state.j2_invariant
    sqrt_J2 = np.sqrt(max(J2, 0.0))
    
    # Yield surface: f = √J₂ - (α·I₁ + k)
    yield_val = sqrt_J2 - (params.alpha * I1 + params.k)
    
    # Safety margin (similar to factor of safety)
    denominator = max(abs(sqrt_J2), 1e-6)
    safety_factor = (params.alpha * I1 + params.k) / denominator if sqrt_J2 > 0 else float('inf')
    
    status = "elastic" if yield_val < 0 else ("yield" if abs(yield_val) < 1e-6 else "plastic")
    
    return {
        "yield_value": float(yield_val),
        "sqrt_j2_kpa": float(sqrt_J2),
        "mean_pressure_i1_kpa": float(I1),
        "safety_factor": float(safety_factor),
        "status": status,
        "alpha": params.alpha,
        "k_kpa": params.k
    }


# ============================================================================
# MODIFIED CAM-CLAY MODEL
# ============================================================================

def cam_clay_yield_surface(
    p: np.ndarray,
    q: np.ndarray,
    params: CamClayParams
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Modified Cam-Clay elliptical yield surface.
    
    (q/M·p)² + (p/p_c)² = 1, where M = tan(φ_cs)
    
    Args:
        p: mean effective pressure [kPa], shape (N,)
        q: deviatoric stress [kPa], shape (N,)
        params: CamClayParams
    
    Returns:
        (yield_values, p_c): yield surface values and preconsolidation pressure
    """
    p = np.asarray(p)
    q = np.asarray(q)
    
    # Critical state line slope
    M = params.m
    p_c = params.preconsolidation_pressure_pc
    
    # Modified Cam-Clay: (q/M·p_c)² + (p/p_c)² = 1
    # Rearranged: f = q²/(M·p_c)² + p²/p_c² - 1
    term1 = (q / (M * p_c))**2
    term2 = (p / p_c)**2
    f = term1 + term2 - 1.0
    
    return f, p_c


def cam_clay_consolidation_stress(
    e0: float,
    e_final: float,
    p0: float,
    params: CamClayParams
) -> float:
    """
    Calculate effective pressure after consolidation using compression index.
    
    e = e₀ - λ·log₁₀(p/p₀)   for virgin consolidation
    
    Args:
        e0: initial void ratio
        e_final: final void ratio
        p0: initial effective pressure [kPa]
        params: CamClayParams with λ
    
    Returns:
        p_final: final effective pressure [kPa]
    """
    delta_e = e0 - e_final
    # λ·log₁₀(p/p₀) = Δe
    # log₁₀(p/p₀) = Δe / λ
    # p = p₀ · 10^(Δe / λ)
    
    if params.lambda_cc <= 0:
        return p0
    
    p_final = p0 * (10.0 ** (delta_e / params.lambda_cc))
    return max(p_final, p0)  # pressure cannot decrease in virgin consolidation


def cam_clay_undrained_strength(
    p_c: float,
    overconsolidation_ratio: float,
    params: CamClayParams
) -> float:
    """
    Undrained shear strength from preconsolidation pressure (Cam-Clay).
    
    For normally consolidated clay: s_u ≈ 0.15 - 0.25 · p_c
    For OCR clay: s_u ≈ s_u,nc · OCR^κ (approximately)
    
    Args:
        p_c: preconsolidation pressure [kPa]
        overconsolidation_ratio: OCR = p_c / p_current
        params: CamClayParams
    
    Returns:
        s_u: undrained shear strength [kPa]
    """
    # Empirical correlation (Ladd & Foott, 1974)
    # s_u / p_c ≈ 0.20 - 0.25 for NC clay
    s_u_nc = 0.20 * p_c
    
    # For overconsol: apply OCR sensitivity (κ ~ 0.7-0.9 typically)
    s_u = s_u_nc * (overconsolidation_ratio ** params.kappa)
    
    return float(s_u)


# ============================================================================
# MAIN DISPATCHER
# ============================================================================

def run(mode: str, params: Dict) -> Dict:
    """
    Main dispatcher for soil_mechanics_tool.
    
    Modes:
      - 'mohr_coulomb': shear strength and FoS
      - 'drucker_prager': DP yield criterion
      - 'cam_clay': clay consolidation + undrained strength
      - 'validate': 8-check self-test
    """
    
    if mode == "mohr_coulomb":
        return _mode_mohr_coulomb(params)
    
    elif mode == "drucker_prager":
        return _mode_drucker_prager(params)
    
    elif mode == "cam_clay":
        return _mode_cam_clay(params)
    
    elif mode == "validate":
        return _mode_validate()
    
    else:
        return {"error": f"Unknown mode: {mode}"}


def _mode_mohr_coulomb(params: Dict) -> Dict:
    """Mohr-Coulomb shear strength analysis."""
    try:
        strength_params = SoilStrengthParams(
            cohesion_c=params["cohesion_c_kpa"],
            friction_angle_deg=params["friction_angle_deg"],
            adhesion=params.get("adhesion_kpa", params["cohesion_c_kpa"] * 0.8)
        )
        
        if "normal_stress_array" in params:
            # Compute envelope for multiple normal stresses
            sigma_n = np.array(params["normal_stress_array"])
            tau_f = mohr_coulomb_shear_strength(sigma_n, strength_params)
            
            return {
                "success": True,
                "model": "Mohr-Coulomb",
                "normal_stress_kpa": sigma_n.tolist(),
                "shear_strength_kpa": tau_f.tolist(),
                "failure_plane_angle_deg": float(failure_plane_angle(strength_params.friction_angle_deg)),
                "friction_angle_deg": strength_params.friction_angle_deg,
                "cohesion_c_kpa": strength_params.cohesion_c,
                "notes": "Envelope: τ = c + σ_n·tan(φ)"
            }
        else:
            # Single point: compute FoS
            result = mohr_coulomb_factor_of_safety(
                params["normal_stress_kpa"],
                params.get("applied_shear_kpa", 0),
                strength_params
            )
            result["success"] = True
            return result
    
    except Exception as e:
        return {"error": str(e)}


def _mode_drucker_prager(params: Dict) -> Dict:
    """Drucker-Prager yield criterion analysis."""
    try:
        # Map friction angle to DP parameters
        phi_deg = params["friction_angle_deg"]
        phi_rad = np.radians(phi_deg)
        
        # Typical DP association: α = 2·sin(φ) / √(3·(3 - sin(φ)))
        sin_phi = np.sin(phi_rad)
        alpha = (2.0 * sin_phi) / np.sqrt(3.0 * (3.0 - sin_phi))
        
        dp_params = DruckerPragerParams(
            k=params.get("k_kpa", params.get("cohesion_c_kpa", 10)),
            alpha=alpha
        )
        
        stress = StressState(
            sigma_1=params["sigma_1_kpa"],
            sigma_2=params.get("sigma_2_kpa", (params["sigma_1_kpa"] + params["sigma_3_kpa"]) / 2.0),
            sigma_3=params["sigma_3_kpa"]
        )
        
        result = drucker_prager_yield(stress, dp_params)
        result["success"] = True
        return result
    
    except Exception as e:
        return {"error": str(e)}


def _mode_cam_clay(params: Dict) -> Dict:
    """Modified Cam-Clay consolidation and undrained strength."""
    try:
        cc_params = CamClayParams(
            lambda_cc=params["lambda_compression_index"],
            kappa=params.get("kappa_swelling", 0.15),
            m=params.get("m_csl_slope", np.tan(np.radians(params["phi_critical_state_deg"]))),
            p_ref=params.get("p_ref_kpa", 100.0),
            preconsolidation_pressure_pc=params["p_c_kpa"]
        )
        
        results = {
            "success": True,
            "model": "Modified Cam-Clay",
            "compression_index_lambda": cc_params.lambda_cc,
            "swelling_index_kappa": cc_params.kappa,
            "csl_slope_m": cc_params.m,
            "preconsolidation_pressure_pc_kpa": cc_params.preconsolidation_pressure_pc
        }
        
        # Consolidation calculation if requested
        if "void_ratio_initial" in params and "void_ratio_final" in params:
            p_final = cam_clay_consolidation_stress(
                params["void_ratio_initial"],
                params["void_ratio_final"],
                params.get("initial_pressure_kpa", 100.0),
                cc_params
            )
            results["consolidation"] = {
                "final_effective_pressure_kpa": float(p_final),
                "void_ratio_change": float(params["void_ratio_initial"] - params["void_ratio_final"])
            }
        
        # Undrained strength
        if "overconsolidation_ratio" in params:
            s_u = cam_clay_undrained_strength(
                cc_params.preconsolidation_pressure_pc,
                params["overconsolidation_ratio"],
                cc_params
            )
            results["undrained_strength"] = {
                "s_u_kpa": s_u,
                "s_u_p_c_ratio": s_u / cc_params.preconsolidation_pressure_pc,
                "ocr": params["overconsolidation_ratio"]
            }
        
        # Yield surface envelope
        if "p_range_kpa" in params:
            p_vals = np.linspace(params["p_range_kpa"][0], params["p_range_kpa"][1], 20)
            q_vals = []
            for p in p_vals:
                q_max = cc_params.m * p  # on critical state line (approximately)
                q_vals.append(float(q_max))
            
            results["yield_surface"] = {
                "p_values_kpa": p_vals.tolist(),
                "q_values_kpa": q_vals
            }
        
        return results
    
    except Exception as e:
        return {"error": str(e)}


def _mode_validate() -> Dict:
    """Self-test: 8 validation checks."""
    checks_passed = 0
    checks_total = 8
    details = []
    
    try:
        # Check 1: Mohr-Coulomb FoS > 1 for reasonable inputs
        mc_params = SoilStrengthParams(
            cohesion_c=20.0,
            friction_angle_deg=30.0,
            adhesion=16.0
        )
        fos_result = mohr_coulomb_factor_of_safety(
            sigma_n=100.0,
            tau_applied=50.0,
            params=mc_params
        )
        if fos_result["factor_of_safety"] > 1.0 and fos_result["status"] == "safe":
            checks_passed += 1
            details.append("✓ Check 1: Mohr-Coulomb FoS > 1 for reasonable stress state")
        else:
            details.append(f"✗ Check 1: Unexpected FoS result: {fos_result}")
        
        # Check 2: Mohr-Coulomb FoS = 1 at failure
        tau_at_failure = fos_result["shear_strength_kpa"]
        fos_result_2 = mohr_coulomb_factor_of_safety(
            sigma_n=100.0,
            tau_applied=tau_at_failure,
            params=mc_params
        )
        if abs(fos_result_2["factor_of_safety"] - 1.0) < 0.01:
            checks_passed += 1
            details.append("✓ Check 2: FoS = 1.0 when applied shear equals strength")
        else:
            details.append(f"✗ Check 2: FoS ≠ 1.0 at failure (got {fos_result_2['factor_of_safety']:.4f})")
        
        # Check 3: Failure plane angle constraint
        theta_f = failure_plane_angle(30.0)
        if 45.0 <= theta_f <= 60.0:  # For φ=30°, θ_f should be exactly 60°
            checks_passed += 1
            details.append(f"✓ Check 3: Failure plane angle {theta_f:.1f}° in expected range [45, 60]°")
        else:
            details.append(f"✗ Check 3: Failure plane angle {theta_f:.1f}° out of range")
        
        # Check 4: Drucker-Prager yield criterion consistency
        stress_elastic = StressState(sigma_1=200.0, sigma_2=150.0, sigma_3=100.0)
        dp_params = DruckerPragerParams(k=15.0, alpha=0.1)
        dp_result = drucker_prager_yield(stress_elastic, dp_params)
        
        if dp_result["status"] == "elastic":
            checks_passed += 1
            details.append("✓ Check 4: Drucker-Prager correctly identifies elastic state")
        else:
            details.append(f"✗ Check 4: DP status incorrect: {dp_result['status']}")
        
        # Check 5: Cam-Clay consolidation monotonic
        cc_params = CamClayParams(
            lambda_cc=0.20,
            kappa=0.05,
            m=1.2,
            p_ref=100.0,
            preconsolidation_pressure_pc=200.0
        )
        p_final_1 = cam_clay_consolidation_stress(0.9, 0.8, 100.0, cc_params)
        p_final_2 = cam_clay_consolidation_stress(0.9, 0.7, 100.0, cc_params)
        
        if p_final_2 > p_final_1:
            checks_passed += 1
            details.append("✓ Check 5: Consolidation pressure increases with void ratio reduction")
        else:
            details.append(f"✗ Check 5: Consolidation not monotonic: {p_final_1} vs {p_final_2}")
        
        # Check 6: Undrained strength positive and reasonable
        s_u = cam_clay_undrained_strength(200.0, 1.0, cc_params)
        if 0 < s_u < 200.0:
            checks_passed += 1
            details.append(f"✓ Check 6: Undrained strength s_u = {s_u:.1f} kPa in reasonable range")
        else:
            details.append(f"✗ Check 6: Undrained strength out of range: {s_u}")
        
        # Check 7: OCR effect on undrained strength
        s_u_oc1 = cam_clay_undrained_strength(200.0, 1.0, cc_params)
        s_u_oc2 = cam_clay_undrained_strength(200.0, 2.0, cc_params)
        
        if s_u_oc2 > s_u_oc1:
            checks_passed += 1
            details.append(f"✓ Check 7: OCR increases undrained strength ({s_u_oc1:.1f} → {s_u_oc2:.1f} kPa)")
        else:
            details.append(f"✗ Check 7: OCR effect inverted")
        
        # Check 8: Mohr-Coulomb envelope monotonic
        sigma_n_array = np.array([50.0, 100.0, 150.0, 200.0])
        tau_array = mohr_coulomb_shear_strength(sigma_n_array, mc_params)
        
        if np.all(np.diff(tau_array) > 0):
            checks_passed += 1
            details.append("✓ Check 8: MC shear strength envelope increases monotonically")
        else:
            details.append(f"✗ Check 8: Envelope not monotonic")
    
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
    "mohr_coulomb": {
        "type": "object",
        "properties": {
            "cohesion_c_kpa": {"type": "number", "description": "Cohesion [kPa]"},
            "friction_angle_deg": {"type": "number", "description": "Internal friction angle [°], [0, 45]"},
            "adhesion_kpa": {"type": "number", "description": "Adhesion (interface), optional"},
            "normal_stress_array": {"type": "array", "items": {"type": "number"},
                                   "description": "Array of normal stresses for envelope [kPa], optional"},
            "normal_stress_kpa": {"type": "number", "description": "Single normal stress [kPa]"},
            "applied_shear_kpa": {"type": "number", "description": "Applied shear stress [kPa]"}
        },
        "required": ["cohesion_c_kpa", "friction_angle_deg"]
    },
    "drucker_prager": {
        "type": "object",
        "properties": {
            "friction_angle_deg": {"type": "number"},
            "cohesion_c_kpa": {"type": "number"},
            "k_kpa": {"type": "number", "description": "DP yield parameter (optional)"},
            "sigma_1_kpa": {"type": "number", "description": "Major principal stress"},
            "sigma_2_kpa": {"type": "number", "description": "Intermediate principal stress (optional)"},
            "sigma_3_kpa": {"type": "number", "description": "Minor principal stress"}
        },
        "required": ["friction_angle_deg", "sigma_1_kpa", "sigma_3_kpa"]
    },
    "cam_clay": {
        "type": "object",
        "properties": {
            "lambda_compression_index": {"type": "number"},
            "kappa_swelling": {"type": "number"},
            "phi_critical_state_deg": {"type": "number"},
            "p_c_kpa": {"type": "number", "description": "Preconsolidation pressure"},
            "void_ratio_initial": {"type": "number", "description": "e₀, optional"},
            "void_ratio_final": {"type": "number", "description": "e_final, optional"},
            "initial_pressure_kpa": {"type": "number"},
            "overconsolidation_ratio": {"type": "number", "description": "OCR, optional"},
            "p_range_kpa": {"type": "array", "items": {"type": "number"},
                           "description": "[p_min, p_max] for yield surface"}
        },
        "required": ["lambda_compression_index", "phi_critical_state_deg", "p_c_kpa"]
    },
    "validate": {
        "type": "object",
        "properties": {}
    }
}


if __name__ == "__main__":
    print("soil_mechanics_tool.py loaded. Running smoke tests...\n")
    
    result = run("validate", {})
    print(f"Validation: {result['passed']}/{result['total']} checks passed\n")
    for detail in result["details"]:
        print(f"  {detail}")
    
    # Example: Mohr-Coulomb FoS
    print("\n--- Example: Mohr-Coulomb Analysis ---")
    ex = run("mohr_coulomb", {
        "cohesion_c_kpa": 20,
        "friction_angle_deg": 30,
        "normal_stress_kpa": 100,
        "applied_shear_kpa": 70
    })
    if "success" in ex:
        print(f"FoS: {ex['factor_of_safety']:.2f} ({ex['status']})")
        print(f"Shear strength: {ex['shear_strength_kpa']:.1f} kPa")
        print(f"Failure plane angle: {ex['friction_angle_deg']}°")


# ============================================================================
# TOOL REGISTRATION (auto-agregado)
# ============================================================================

TOOL_SCHEMA = {
    "name": 'soil_mechanics_tool',
    "description": 'Criterios de falla (Mohr-Coulomb, Drucker-Prager) y consolidacion (Cam-Clay modificado) para mecanica de suelos.',
    "inputSchema": {
        "type": "object",
        "properties": {'adhesion_kpa': {'description': 'Adhesion (interface), optional', 'type': 'number'},
 'applied_shear_kpa': {'description': 'Applied shear stress [kPa]', 'type': 'number'},
 'cohesion_c_kpa': {'description': 'Cohesion [kPa]', 'type': 'number'},
 'friction_angle_deg': {'description': 'Internal friction angle [°], [0, 45]', 'type': 'number'},
 'initial_pressure_kpa': {'type': 'number'},
 'k_kpa': {'description': 'DP yield parameter (optional)', 'type': 'number'},
 'kappa_swelling': {'type': 'number'},
 'lambda_compression_index': {'type': 'number'},
 'mode': {'description': 'Modo de operacion',
          'enum': ['mohr_coulomb', 'drucker_prager', 'cam_clay', 'validate'],
          'type': 'string'},
 'normal_stress_array': {'description': 'Array of normal stresses for envelope [kPa], optional',
                         'items': {'type': 'number'},
                         'type': 'array'},
 'normal_stress_kpa': {'description': 'Single normal stress [kPa]', 'type': 'number'},
 'overconsolidation_ratio': {'description': 'OCR, optional', 'type': 'number'},
 'p_c_kpa': {'description': 'Preconsolidation pressure', 'type': 'number'},
 'p_range_kpa': {'description': '[p_min, p_max] for yield surface',
                 'items': {'type': 'number'},
                 'type': 'array'},
 'phi_critical_state_deg': {'type': 'number'},
 'sigma_1_kpa': {'description': 'Major principal stress', 'type': 'number'},
 'sigma_2_kpa': {'description': 'Intermediate principal stress (optional)', 'type': 'number'},
 'sigma_3_kpa': {'description': 'Minor principal stress', 'type': 'number'},
 'void_ratio_final': {'description': 'e_final, optional', 'type': 'number'},
 'void_ratio_initial': {'description': 'e₀, optional', 'type': 'number'}},
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
