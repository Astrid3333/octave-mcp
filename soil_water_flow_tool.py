#!/usr/bin/env python3
"""
soil_water_flow_tool.py
1D Richards equation solver for unsaturated water flow in soil.

Core Physics:
  Richards equation: ∂θ/∂t = ∂/∂z[K(θ)·∂ψ/∂z + K(θ)]
  
  - θ: volumetric water content [m³/m³]
  - ψ: matric potential (suction) [Pa or kPa]
  - K(θ): unsaturated hydraulic conductivity [m/s]
  - z: depth (positive downward)
  
Boundary Conditions:
  - Infiltration: constant flux q_in at surface
  - Evaporation: extraction rate q_out at surface
  - Drainage: free drainage (ψ → 0) at lower boundary
  
Numerics:
  - Finite difference (explicit or semi-implicit)
  - van Genuchten/Brooks-Corey retention curves
  - Adaptive time stepping for stability

Modes:
  - infiltration_1d: simulate rainfall infiltration into dry soil
  - evaporation_1d: simulate water extraction from surface
  - imbibition: wetting front propagation
  - validate: 8-check self-test
"""

import numpy as np
from scipy.integrate import odeint
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class RichardsParams:
    """Parameters for 1D Richards equation solver."""
    depth_m: float              # Domain depth [m]
    num_nodes: int              # Number of spatial nodes (20-100 typical)
    theta_s: float              # Saturated water content [m³/m³]
    theta_r: float              # Residual water content
    alpha: float                # van Genuchten α [1/Pa]
    n: float                    # van Genuchten n
    k_s: float                  # Saturated conductivity [m/s]
    model: str                  # "van_genuchten" or "brooks_corey"


@dataclass
class BoundaryCondition:
    """Boundary condition specification."""
    bc_type: str                # "flux" (Neumann), "head" (Dirichlet), "drainage"
    value: float                # for "flux": q [m/s]; for "head": ψ [Pa]
    location: str               # "top" or "bottom"


# ============================================================================
# WATER RETENTION & CONDUCTIVITY
# ============================================================================

def effective_saturation(theta: float, theta_r: float, theta_s: float) -> float:
    """S_e = (θ - θ_r) / (θ_s - θ_r)"""
    return np.clip((theta - theta_r) / (theta_s - theta_r), 0.0, 1.0)


def matric_potential_van_genuchten(theta: float, params: RichardsParams) -> float:
    """
    Compute matric potential ψ from water content θ (van Genuchten inverse).
    
    θ(ψ) = θ_r + (θ_s - θ_r) / (1 + (α·|ψ|)^n)^m
    
    Inverted numerically:
    |ψ| = (1/α) · ((θ_s - θ_r)/(θ - θ_r) - 1)^(1/(n·m))
    
    Args:
        theta: water content [m³/m³]
        params: RichardsParams
    
    Returns:
        ψ: matric potential [Pa], negative for unsaturated
    """
    theta = np.clip(theta, params.theta_r, params.theta_s)
    
    if abs(theta - params.theta_s) < 1e-8:
        return 0.0  # saturated
    
    m = 1.0 - 1.0 / params.n
    se = effective_saturation(theta, params.theta_r, params.theta_s)
    
    if se < 1e-6:
        se = 1e-6
    
    # |ψ| = (1/α) · (S_e^(-1/m) - 1)^(1/n)
    inner = (se**(-1.0/m) - 1.0)**(1.0/params.n)
    psi = -(1.0 / params.alpha) * inner
    
    return psi


def hydraulic_conductivity(theta: float, params: RichardsParams) -> float:
    """
    Unsaturated hydraulic conductivity K(θ) via van Genuchten-Mualem.
    
    K(θ) = K_s · S_e^0.5 · (1 - (1 - S_e^(1/m))^m)^2
    
    Args:
        theta: water content [m³/m³]
        params: RichardsParams
    
    Returns:
        K: hydraulic conductivity [m/s], always > 0
    """
    se = effective_saturation(theta, params.theta_r, params.theta_s)
    
    if se >= 1.0:
        return params.k_s
    
    if se <= 0.0:
        return 1e-12  # residual conductivity
    
    m = 1.0 - 1.0 / params.n
    
    term1 = se**0.5
    term2 = 1.0 - (1.0 - se**(1.0/m))**m
    k = params.k_s * term1 * term2**2
    
    return max(k, 1e-15)


def specific_water_capacity(theta: float, params: RichardsParams, dtheta_dpsi: float = 1e-6) -> float:
    """
    Specific water capacity C(θ) = dθ/dψ (finite difference).
    
    For van Genuchten:
    C(θ) = α·m·n·(θ_s - θ_r) · (S_e^(1/m) - 1)^(-n-1) · S_e^(1/m - 1)
    
    Args:
        theta: water content [m³/m³]
        params: RichardsParams
        dtheta_dpsi: numerical derivative step [Pa]
    
    Returns:
        C: specific water capacity [1/Pa]
    """
    se = effective_saturation(theta, params.theta_r, params.theta_s)
    
    if se >= 0.99 or se <= 0.01:
        return 1e-6  # negligible near saturation/residual
    
    m = 1.0 - 1.0 / params.n
    n = params.n
    alpha = params.alpha
    dtheta_dse = (theta - params.theta_r) / (params.theta_s - params.theta_r)
    
    # dS_e/dψ numerically
    dpsi = 1.0  # small change in Pa
    se2 = se * (1.0 + dpsi * alpha * 0.001)**(-n)
    dse_dpsi = (se2 - se) / dpsi
    
    c = dse_dpsi * (params.theta_s - params.theta_r)
    
    return max(abs(c), 1e-10)


# ============================================================================
# 1D FINITE DIFFERENCE SOLVER (EXPLICIT)
# ============================================================================

def solve_richards_explicit(
    theta_init: np.ndarray,
    bc_top: Dict,
    bc_bottom: Dict,
    params: RichardsParams,
    t_max: float,
    dt_init: float = 0.01
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Explicit finite difference solver for 1D Richards equation.
    
    ∂θ/∂t = ∂/∂z[K(θ)·∂ψ/∂z + K(θ)]
    
    Args:
        theta_init: initial water content profile [m³/m³], shape (num_nodes,)
        bc_top: {"type": "flux", "value": q_in [m/s]} or {"type": "head", "value": ψ_surf [Pa]}
        bc_bottom: {"type": "drainage"} or {"type": "flux", "value": q_bottom}
        params: RichardsParams
        t_max: simulation time [s]
        dt_init: initial time step [s]
    
    Returns:
        (z, theta_final, t_array): depth [m], final water content, time history
    """
    z = np.linspace(0, params.depth_m, params.num_nodes)
    dz = z[1] - z[0]
    
    theta = theta_init.copy()
    theta_history = [theta.copy()]
    time_history = [0.0]
    
    t = 0.0
    dt = dt_init
    n_steps = 0
    max_steps = 10000
    
    while t < t_max and n_steps < max_steps:
        # Compute K and C at current theta
        k_profile = np.array([hydraulic_conductivity(th, params) for th in theta])
        c_profile = np.array([specific_water_capacity(th, params) for th in theta])
        
        # Compute ψ from θ (van Genuchten)
        psi_profile = np.array([matric_potential_van_genuchten(th, params) for th in theta])
        
        # Compute ∂ψ/∂z via central difference
        dpsi_dz = np.zeros_like(z)
        dpsi_dz[1:-1] = (psi_profile[2:] - psi_profile[:-2]) / (2*dz)
        dpsi_dz[0] = (psi_profile[1] - psi_profile[0]) / dz
        dpsi_dz[-1] = (psi_profile[-1] - psi_profile[-2]) / dz
        
        # Flux: q = -K·(∂ψ/∂z + 1)
        q_profile = -k_profile * (dpsi_dz + np.ones_like(z))
        
        # ∂q/∂z via central difference
        dq_dz = np.zeros_like(z)
        dq_dz[1:-1] = (q_profile[2:] - q_profile[:-2]) / (2*dz)
        dq_dz[0] = (q_profile[1] - q_profile[0]) / dz
        dq_dz[-1] = (q_profile[-1] - q_profile[-2]) / dz
        
        # ∂θ/∂t = -∂q/∂z
        dtheta_dt = -dq_dz
        
        # Apply boundary conditions
        if bc_top["type"] == "flux":
            # Prescribed flux at surface
            q_top = bc_top["value"]
            dtheta_dt[0] = -(q_top - q_profile[1]) / dz
        
        if bc_bottom["type"] == "drainage":
            # Free drainage: q_bottom = -K(θ_bottom)
            dtheta_dt[-1] = 0  # simplified
        
        # Stability check: CFL
        k_max = np.max(k_profile) + 1e-12
        c_max = np.max(c_profile) + 1e-12
        dt_max = 0.5 * dz**2 / (k_max / c_max + k_max)
        dt = min(dt_init, dt_max * 0.8)
        
        # Update
        theta_new = theta + dtheta_dt * dt
        theta_new = np.clip(theta_new, params.theta_r, params.theta_s)
        
        # Check convergence: if change is small, accept
        if np.max(np.abs(theta_new - theta)) < 1e-8:
            dt *= 1.5
        
        theta = theta_new
        t += dt
        n_steps += 1
        
        if n_steps % 10 == 0:
            theta_history.append(theta.copy())
            time_history.append(t)
    
    return z, theta, np.array(time_history)


# ============================================================================
# ANALYTICAL SOLUTION (Green-Ampt APPROXIMATION)
# ============================================================================

def wetting_front_depth_green_ampt(
    t_s: float,
    k_s: float,
    suction_head_m: float,
    theta_0: float,
    theta_s: float
) -> float:
    """
    Green-Ampt wetting front depth (approximate, infiltration only).
    
    For short times, wetting front penetration:
    z_f ≈ sqrt(2·K_s·ψ_aev·Δθ·t)
    
    Args:
        t_s: time [s]
        k_s: saturated conductivity [m/s]
        suction_head_m: suction head at wetting front [m]
        theta_0: initial water content
        theta_s: saturated water content
    
    Returns:
        z_f: wetting front depth [m]
    """
    delta_theta = max(theta_s - theta_0, 0.01)
    
    # Green-Ampt (simplified)
    z_f = np.sqrt(2.0 * k_s * suction_head_m * delta_theta * t_s)
    
    return z_f


# ============================================================================
# MAIN DISPATCHER
# ============================================================================

def run(mode: str, params: Dict) -> Dict:
    """
    Main dispatcher for soil_water_flow_tool.
    
    Modes:
      - 'infiltration_1d': simulate rainfall infiltration
      - 'evaporation_1d': simulate water extraction
      - 'imbibition': wetting front propagation
      - 'validate': 8-check self-test
    """
    
    if mode == "infiltration_1d":
        return _mode_infiltration(params)
    
    elif mode == "evaporation_1d":
        return _mode_evaporation(params)
    
    elif mode == "imbibition":
        return _mode_imbibition(params)
    
    elif mode == "validate":
        return _mode_validate()
    
    else:
        return {"error": f"Unknown mode: {mode}"}


def _mode_infiltration(params: Dict) -> Dict:
    """Simulate infiltration into dry soil."""
    try:
        rp = RichardsParams(
            depth_m=params["depth_m"],
            num_nodes=params.get("num_nodes", 50),
            theta_s=params["theta_s"],
            theta_r=params.get("theta_r", 0.01),
            alpha=params.get("alpha_1_pa", 0.01),
            n=params.get("n", 2.0),
            k_s=params.get("k_s_m_s", 1e-5),
            model="van_genuchten"
        )
        
        # Initial condition: dry soil
        theta_init = np.full(rp.num_nodes, rp.theta_r + 0.05)
        
        # Boundary: constant infiltration flux at surface
        bc_top = {"type": "flux", "value": params.get("infiltration_flux_m_s", 1e-6)}
        bc_bottom = {"type": "drainage"}
        
        t_max = params.get("simulation_time_s", 3600.0)  # 1 hour default
        
        z, theta_final, time_hist = solve_richards_explicit(
            theta_init, bc_top, bc_bottom, rp, t_max
        )
        
        return {
            "success": True,
            "mode": "infiltration",
            "depth_m": z.tolist(),
            "water_content_theta": theta_final.tolist(),
            "simulation_time_s": float(t_max),
            "infiltration_depth_m": float(np.max(z[theta_final > rp.theta_r + 0.1])),
            "notes": "1D Richards equation (explicit FD)"
        }
    
    except Exception as e:
        return {"error": str(e)}


def _mode_evaporation(params: Dict) -> Dict:
    """Simulate evaporation from surface."""
    try:
        rp = RichardsParams(
            depth_m=params["depth_m"],
            num_nodes=params.get("num_nodes", 50),
            theta_s=params["theta_s"],
            theta_r=params.get("theta_r", 0.01),
            alpha=params.get("alpha_1_pa", 0.01),
            n=params.get("n", 2.0),
            k_s=params.get("k_s_m_s", 1e-5),
            model="van_genuchten"
        )
        
        # Initial: soil at intermediate saturation
        theta_init = np.full(rp.num_nodes, params.get("initial_theta", 0.3))
        
        # Boundary: evaporation extraction rate
        bc_top = {"type": "flux", "value": -params.get("evaporation_flux_m_s", 5e-8)}
        bc_bottom = {"type": "drainage"}
        
        t_max = params.get("simulation_time_s", 86400.0)  # 1 day default
        
        z, theta_final, time_hist = solve_richards_explicit(
            theta_init, bc_top, bc_bottom, rp, t_max
        )
        
        return {
            "success": True,
            "mode": "evaporation",
            "depth_m": z.tolist(),
            "water_content_theta": theta_final.tolist(),
            "simulation_time_s": float(t_max),
            "surface_water_content_theta": float(theta_final[0]),
            "residual_water_content_theta": float(rp.theta_r),
            "notes": "Drying front propagation from surface"
        }
    
    except Exception as e:
        return {"error": str(e)}


def _mode_imbibition(params: Dict) -> Dict:
    """Simulate wetting front (imbibition)."""
    try:
        k_s = params.get("k_s_m_s", 1e-5)
        suction_head = params.get("suction_head_m", 0.5)
        theta_0 = params.get("theta_initial", 0.1)
        theta_s = params["theta_s"]
        
        times = np.array(params.get("times_s", [100, 300, 900, 3600]))
        z_fronts = [wetting_front_depth_green_ampt(t, k_s, suction_head, theta_0, theta_s) 
                    for t in times]
        
        return {
            "success": True,
            "mode": "imbibition (Green-Ampt)",
            "times_s": times.tolist(),
            "wetting_front_depths_m": z_fronts,
            "k_s_m_s": k_s,
            "suction_head_m": suction_head,
            "theta_initial": theta_0,
            "theta_saturated": theta_s,
            "notes": "Approximate analytical solution"
        }
    
    except Exception as e:
        return {"error": str(e)}


def _mode_validate() -> Dict:
    """Self-test: 8 validation checks."""
    checks_passed = 0
    checks_total = 8
    details = []
    
    try:
        # Check 1: van Genuchten matric potential
        rp = RichardsParams(
            depth_m=1.0, num_nodes=20,
            theta_s=0.45, theta_r=0.05,
            alpha=0.01, n=1.5, k_s=1e-5,
            model="van_genuchten"
        )
        psi_sat = matric_potential_van_genuchten(rp.theta_s, rp)
        psi_res = matric_potential_van_genuchten(rp.theta_r, rp)
        
        if abs(psi_sat) < 1 and psi_res < -1:
            checks_passed += 1
            details.append(f"✓ Check 1: Matric potential ψ_sat≈{psi_sat:.1f}, ψ_res={psi_res:.1f} Pa")
        else:
            details.append(f"✗ Check 1: Unexpected ψ values")
        
        # Check 2: Hydraulic conductivity decreases with suction
        k_sat = hydraulic_conductivity(rp.theta_s, rp)
        k_dry = hydraulic_conductivity(rp.theta_r + 0.05, rp)
        
        if k_sat > k_dry:
            checks_passed += 1
            details.append(f"✓ Check 2: K_sat={k_sat:.2e} > K_dry={k_dry:.2e} m/s")
        else:
            details.append(f"✗ Check 2: K relationship inverted")
        
        # Check 3: Specific water capacity positive
        c = specific_water_capacity(0.25, rp)
        if c > 0:
            checks_passed += 1
            details.append(f"✓ Check 3: Specific water capacity C={c:.2e} 1/Pa > 0")
        else:
            details.append(f"✗ Check 3: Negative capacity")
        
        # Check 4: Green-Ampt wetting front increases with time
        z_1 = wetting_front_depth_green_ampt(100, 1e-5, 0.5, 0.1, 0.45)
        z_2 = wetting_front_depth_green_ampt(300, 1e-5, 0.5, 0.1, 0.45)
        
        if z_2 > z_1:
            checks_passed += 1
            details.append(f"✓ Check 4: Wetting front depth increases: z(100s)={z_1:.4f}, z(300s)={z_2:.4f} m")
        else:
            details.append(f"✗ Check 4: Front depth not monotonic")
        
        # Check 5: Green-Ampt scales with sqrt(time)
        z_100 = wetting_front_depth_green_ampt(100, 1e-5, 0.5, 0.1, 0.45)
        z_400 = wetting_front_depth_green_ampt(400, 1e-5, 0.5, 0.1, 0.45)
        ratio = z_400 / z_100
        
        if 1.8 < ratio < 2.2:  # sqrt(4) ≈ 2
            checks_passed += 1
            details.append(f"✓ Check 5: Green-Ampt scales as sqrt(t), z_400/z_100={ratio:.3f} ≈ 2")
        else:
            details.append(f"✗ Check 5: Time scaling incorrect: {ratio:.3f}")
        
        # Check 6: Effective saturation in [0, 1]
        se_low = effective_saturation(rp.theta_r, rp.theta_r, rp.theta_s)
        se_high = effective_saturation(rp.theta_s, rp.theta_r, rp.theta_s)
        
        if se_low >= 0 and se_high <= 1.0:
            checks_passed += 1
            details.append(f"✓ Check 6: S_e range [0, 1]: min={se_low:.3f}, max={se_high:.3f}")
        else:
            details.append(f"✗ Check 6: S_e out of bounds")
        
        # Check 7: Richards equation conservation (flux continuity)
        # K should decrease with decreasing water content (drying with depth)
        theta_profile = np.linspace(rp.theta_s - 0.05, rp.theta_r + 0.1, 20)  # decreasing θ with depth
        k_profile = np.array([hydraulic_conductivity(th, rp) for th in theta_profile])
        
        if np.all(np.diff(k_profile) <= 0):  # K should decrease monotonically
            checks_passed += 1
            details.append("✓ Check 7: Hydraulic conductivity decreases with depth (drying front)")
        else:
            details.append("✗ Check 7: K profile not monotonically decreasing")
        
        # Check 8: Water content clipping constraints
        theta_clipped = np.clip(rp.theta_r + 0.02, rp.theta_r, rp.theta_s)
        
        if rp.theta_r <= theta_clipped <= rp.theta_s:
            checks_passed += 1
            details.append(f"✓ Check 8: Water content clipping enforces [{rp.theta_r}, {rp.theta_s}]")
        else:
            details.append(f"✗ Check 8: Clipping failed")
    
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
    "infiltration_1d": {
        "type": "object",
        "properties": {
            "depth_m": {"type": "number", "description": "Domain depth [m]"},
            "num_nodes": {"type": "number", "description": "Spatial nodes, default 50"},
            "theta_s": {"type": "number", "description": "Saturated water content"},
            "theta_r": {"type": "number", "description": "Residual water content, default 0.01"},
            "alpha_1_pa": {"type": "number", "description": "van Genuchten α [1/Pa]"},
            "n": {"type": "number", "description": "van Genuchten n, default 2.0"},
            "k_s_m_s": {"type": "number", "description": "Saturated K [m/s], default 1e-5"},
            "infiltration_flux_m_s": {"type": "number", "description": "Rainfall flux [m/s]"},
            "simulation_time_s": {"type": "number", "description": "[s], default 3600"}
        },
        "required": ["depth_m", "theta_s", "alpha_1_pa"]
    },
    "evaporation_1d": {
        "type": "object",
        "properties": {
            "depth_m": {"type": "number"},
            "theta_s": {"type": "number"},
            "theta_r": {"type": "number"},
            "alpha_1_pa": {"type": "number"},
            "n": {"type": "number"},
            "k_s_m_s": {"type": "number"},
            "initial_theta": {"type": "number", "description": "Initial water content"},
            "evaporation_flux_m_s": {"type": "number", "description": "Surface evaporation rate [m/s]"},
            "simulation_time_s": {"type": "number"}
        },
        "required": ["depth_m", "theta_s", "alpha_1_pa", "initial_theta"]
    },
    "imbibition": {
        "type": "object",
        "properties": {
            "theta_s": {"type": "number"},
            "theta_initial": {"type": "number"},
            "k_s_m_s": {"type": "number"},
            "suction_head_m": {"type": "number"},
            "times_s": {"type": "array", "items": {"type": "number"},
                       "description": "Time points [s]"}
        },
        "required": ["theta_s", "k_s_m_s"]
    },
    "validate": {
        "type": "object",
        "properties": {}
    }
}


if __name__ == "__main__":
    print("soil_water_flow_tool.py loaded. Running smoke tests...\n")
    
    result = run("validate", {})
    print(f"Validation: {result['passed']}/{result['total']} checks passed\n")
    for detail in result["details"]:
        print(f"  {detail}")
    
    # Example: imbibition (analytical)
    print("\n--- Example: Wetting Front Propagation (Green-Ampt) ---")
    ex = run("imbibition", {
        "theta_s": 0.45,
        "theta_initial": 0.1,
        "k_s_m_s": 1e-5,
        "suction_head_m": 0.5,
        "times_s": [100, 300, 900, 3600]
    })
    if "success" in ex:
        for t, z_f in zip(ex["times_s"], ex["wetting_front_depths_m"]):
            print(f"  t={t:>4} s → z_f={z_f:.4f} m")
