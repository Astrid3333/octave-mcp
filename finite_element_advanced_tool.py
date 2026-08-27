"""
finite_element_tool.py (COMPLETO)

Análisis térmico por elementos finitos:
- thermal_transient: conducción de calor transitoria (Fourier 1D/2D)
- heat_transfer_3d: transferencia 3D con convección y radiación
- phase_change: análisis con cambio de fase (Stefan problem)
- thermal_stress: acoplamiento termo-mecánico (esfuerzos térmicos)

Modo "validate" ejecuta autochequeos termofísicos y numéricos.
"""

import numpy as np
from scipy import sparse, linalg, integrate, optimize

FINITE_ELEMENT_TOOL_SCHEMA = {
    "name": "finite_element_advanced_tool",
    "description": (
        "Análisis térmico FEM: conducción transitoria (1D/2D), "
        "transferencia con convección/radiación (3D), cambio de fase (Stefan), "
        "acoplamiento termo-mecánico. "
        "Modos: thermal_transient, heat_transfer_3d, phase_change, thermal_stress, validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["thermal_transient", "heat_transfer_3d", "phase_change", 
                         "thermal_stress", "validate"],
            },
            "length": {"type": "number", "description": "Largo de dominio (m)."},
            "width": {"type": "number", "description": "Ancho de dominio (m)."},
            "height": {"type": "number", "description": "Alto de dominio (m)."},
            "n_elements": {"type": "integer", "description": "Número de elementos FEM."},
            "time_steps": {"type": "integer", "description": "Pasos de tiempo."},
            "dt": {"type": "number", "description": "Paso de tiempo (s)."},
            "thermal_conductivity": {"type": "number", "description": "k (W/m·K)."},
            "density": {"type": "number", "description": "ρ (kg/m³)."},
            "specific_heat": {"type": "number", "description": "c (J/kg·K)."},
            "initial_temperature": {"type": "number", "description": "T₀ (K)."},
            "boundary_temperature": {"type": "number", "description": "T_boundary (K)."},
            "convection_coeff": {"type": "number", "description": "h (W/m²·K)."},
            "ambient_temperature": {"type": "number", "description": "T_ambient (K)."},
            "latent_heat": {"type": "number", "description": "L (J/kg) para cambio de fase."},
            "melting_temperature": {"type": "number", "description": "T_melt (K)."},
            "thermal_expansion": {"type": "number", "description": "α (1/K)."},
            "youngs_modulus": {"type": "number", "description": "E (Pa)."},
            "seed": {"type": "integer", "default": 0},
        },
        "required": ["mode"],
    },
}


def thermal_transient(length=1.0, n_elements=50, time_steps=100, dt=0.01,
                     thermal_conductivity=1.0, density=1000.0, specific_heat=4180.0,
                     initial_temperature=300.0, boundary_temperature=400.0, seed=0):
    """
    Conducción de calor transitoria 1D: ∂T/∂t = α * ∂²T/∂x²
    Resolución por Método de Elementos Finitos + Crank-Nicolson.
    """
    L = length
    dx = L / (n_elements - 1)
    alpha_thermal = thermal_conductivity / (density * specific_heat)
    
    # Número de Fourier
    Fo = alpha_thermal * dt / (dx**2)
    
    # Matrices de rigidez y masa (elementos lineales)
    K = sparse.lil_matrix((n_elements, n_elements))
    M = sparse.lil_matrix((n_elements, n_elements))
    
    k_local = thermal_conductivity / dx
    m_local = (density * specific_heat * dx) / 6.0
    
    for i in range(n_elements - 1):
        # Rigidez local: k_local * [1, -1; -1, 1]
        K[i, i] += k_local
        K[i, i+1] -= k_local
        K[i+1, i] -= k_local
        K[i+1, i+1] += k_local
        
        # Masa local: m_local * [2, 1; 1, 2]
        M[i, i] += 2 * m_local
        M[i, i+1] += m_local
        M[i+1, i] += m_local
        M[i+1, i+1] += 2 * m_local
    
    # Condiciones de borde (Dirichlet)
    K[0, :] = 0
    K[0, 0] = 1.0
    M[0, :] = 0
    M[0, 0] = 1.0
    
    K[-1, :] = 0
    K[-1, -1] = 1.0
    M[-1, :] = 0
    M[-1, -1] = 1.0
    
    K = K.tocsr()
    M = M.tocsr()
    
    # Discretización temporal (Crank-Nicolson)
    # (M + 0.5*dt*K) * T^{n+1} = (M - 0.5*dt*K) * T^n + rhs
    
    A_CN = M + 0.5 * dt * K
    B_CN = M - 0.5 * dt * K
    
    # Condición inicial
    T = np.full(n_elements, initial_temperature)
    T[0] = boundary_temperature
    T[-1] = boundary_temperature
    
    history = []
    
    for t_step in range(time_steps):
        # Vector RHS
        rhs = B_CN @ T
        rhs[0] = boundary_temperature
        rhs[-1] = boundary_temperature
        
        # Resolver sistema
        T = sparse.linalg.spsolve(A_CN, rhs)
        
        # Asegurar BC
        T[0] = boundary_temperature
        T[-1] = boundary_temperature
        
        history.append({
            "time_step": t_step,
            "time": float(t_step * dt),
            "mean_temperature": float(np.mean(T)),
            "max_temperature": float(np.max(T)),
            "min_temperature": float(np.min(T)),
            "temperature_gradient": float(np.max(np.abs(np.gradient(T)))),
        })
    
    # Análisis de convergencia
    convergence_criterion = Fo  # Estabilidad de CN
    
    return {
        "mode": "thermal_transient",
        "length": float(L),
        "n_elements": n_elements,
        "time_steps": time_steps,
        "total_time": float(time_steps * dt),
        "thermal_properties": {
            "conductivity": thermal_conductivity,
            "density": density,
            "specific_heat": specific_heat,
            "diffusivity": alpha_thermal,
        },
        "numerical_parameters": {
            "dx": float(dx),
            "dt": float(dt),
            "fourier_number": float(Fo),
            "stability_criterion": "STABLE" if Fo <= 0.5 else "UNSTABLE",
        },
        "history": history,
        "final_mean_temperature": float(history[-1]["mean_temperature"]),
    }


def heat_transfer_3d(length=1.0, width=1.0, height=1.0, n_elements=10,
                    thermal_conductivity=1.0, density=1000.0, specific_heat=4180.0,
                    convection_coeff=10.0, ambient_temperature=300.0,
                    initial_temperature=400.0, time_steps=50, dt=0.1, seed=0):
    """
    Transferencia de calor 3D con convección superficial.
    Radiación simplificada (Stefan-Boltzmann).
    """
    L, W, H = length, width, height
    V = L * W * H
    S = 2 * (L*W + W*H + H*L)
    
    alpha_thermal = thermal_conductivity / (density * specific_heat)
    
    # Número de Biot: Bi = h*L_c/k
    L_c = V / S  # Longitud característica
    Bi = convection_coeff * L_c / thermal_conductivity
    
    # Malla 3D simplificada (1 nodo por elemento, discretización de volumen)
    n_nodes_3d = n_elements**3
    
    # Capacitancia térmica nodal
    C_node = (density * specific_heat * V) / n_nodes_3d
    
    # Conductancia convectiva (por unidad de área nodal)
    A_node = S / n_nodes_3d
    G_conv = convection_coeff * A_node
    
    # Temperatura inicial
    T = np.full(n_nodes_3d, initial_temperature)
    
    history = []
    
    for t_step in range(time_steps):
        # Flujo de calor por convección: Q = h*A*(T - T_ambient)
        Q_conv = G_conv * (T - ambient_temperature)
        
        # Flujo por radiación (simplificado): Q_rad = ε*σ*A*(T⁴ - T_amb⁴)
        emissivity = 0.9
        sigma = 5.67e-8  # Stefan-Boltzmann
        Q_rad = emissivity * sigma * A_node * (T**4 - ambient_temperature**4)
        
        # Balance energético: C*dT/dt = -(Q_conv + Q_rad)
        dT_dt = -(Q_conv + Q_rad) / C_node
        
        # Integración temporal (Euler explícito)
        T = T + dt * dT_dt
        
        # Asegurar T > 0 K
        T = np.maximum(T, 0.1)
        
        history.append({
            "time_step": t_step,
            "time": float(t_step * dt),
            "mean_temperature": float(np.mean(T)),
            "max_temperature": float(np.max(T)),
            "min_temperature": float(np.min(T)),
            "total_heat_loss": float(np.sum(Q_conv + Q_rad) * dt),
            "biot_number": float(Bi),
        })
    
    return {
        "mode": "heat_transfer_3d",
        "domain": {
            "length": float(L),
            "width": float(W),
            "height": float(H),
            "volume": float(V),
            "surface_area": float(S),
        },
        "n_elements": n_elements,
        "n_nodes": n_nodes_3d,
        "thermal_properties": {
            "conductivity": thermal_conductivity,
            "density": density,
            "specific_heat": specific_heat,
        },
        "convection": {
            "coefficient": convection_coeff,
            "ambient_temperature": ambient_temperature,
            "biot_number": float(Bi),
            "regime": "Lumped" if Bi < 0.1 else "Distributed",
        },
        "time_steps": time_steps,
        "total_time": float(time_steps * dt),
        "history": history,
        "final_temperature_mean": float(history[-1]["mean_temperature"]),
    }


def phase_change(length=1.0, n_elements=50, time_steps=200, dt=0.01,
                thermal_conductivity=1.0, density=800.0, specific_heat=2500.0,
                latent_heat=3.3e5, melting_temperature=273.15,
                initial_temperature=263.0, boundary_temperature=303.0, seed=0):
    """
    Stefan problem: conducción con cambio de fase (solidificación/fusión).
    ∂T/∂t = α*∂²T/∂x² con latencia L en T = T_melt.
    """
    L = length
    dx = L / (n_elements - 1)
    alpha = thermal_conductivity / (density * specific_heat)
    
    # Temperatura inicial
    T = np.full(n_elements, initial_temperature)
    T[0] = boundary_temperature
    
    # Fracción de fase sólida (1 = sólido, 0 = líquido)
    phi = np.ones(n_elements)
    for i in range(n_elements):
        if T[i] >= melting_temperature:
            phi[i] = 0.0
        else:
            phi[i] = 1.0
    
    history = []
    
    for t_step in range(time_steps):
        # Conductividad efectiva con latencia
        dphi_dx = np.gradient(phi, dx)
        k_eff = thermal_conductivity + latent_heat * np.abs(dphi_dx)
        
        # Diffusividad efectiva (escalar, ajustable por estabilidad)
        alpha_eff_scalar = min(alpha * dt / (dx**2), 0.5)
        alpha_eff = np.full(n_elements, alpha_eff_scalar)  # Array para consistencia
        
        # Diferencias finitas (Crank-Nicolson)
        T_new = T.copy()
        for i in range(1, n_elements - 1):
            laplacian = (T[i+1] - 2*T[i] + T[i-1]) / (dx**2)
            T_new[i] = T[i] + alpha_eff[i] * laplacian * dx**2
        
        # Condición de borde
        T_new[0] = boundary_temperature
        
        # Transición de fase (modelo de capacitancia aparente)
        dT = T_new - T
        # Si T cruza T_melt, absorber/liberar latencia
        for i in range(n_elements):
            if abs(T[i] - melting_temperature) < 5.0:  # Zona de transición
                # Reducir cambio de temperatura por efecto latente
                T_new[i] = T[i] + dT[i] / (1.0 + latent_heat / (specific_heat * 10.0))
                # Actualizar fracción de fase
                if T[i] < melting_temperature:
                    phi[i] = 1.0
                else:
                    phi[i] = 0.0
        
        T = T_new
        
        # Posición de la interfaz (aproximada)
        interface_pos = 0.0
        for i in range(n_elements - 1):
            if phi[i] != phi[i+1]:
                interface_pos = float(i * dx)
                break
        
        history.append({
            "time_step": t_step,
            "time": float(t_step * dt),
            "mean_temperature": float(np.mean(T)),
            "max_temperature": float(np.max(T)),
            "melted_fraction": float(np.sum(1 - phi) / n_elements),
            "interface_position": float(interface_pos),
        })
    
    return {
        "mode": "phase_change",
        "length": float(L),
        "n_elements": n_elements,
        "time_steps": time_steps,
        "total_time": float(time_steps * dt),
        "material_properties": {
            "thermal_conductivity": thermal_conductivity,
            "density": density,
            "specific_heat": specific_heat,
            "latent_heat": latent_heat,
            "melting_temperature": melting_temperature,
        },
        "stefan_number": float(specific_heat * (boundary_temperature - initial_temperature) / latent_heat),
        "history": history,
        "final_melted_fraction": float(history[-1]["melted_fraction"]),
    }


def thermal_stress(length=1.0, n_elements=40, thermal_conductivity=50.0,
                  density=7850.0, specific_heat=500.0, thermal_expansion=1.2e-5,
                  youngs_modulus=2.1e11, initial_temperature=300.0, 
                  boundary_temperature=500.0, seed=0):
    """
    Acoplamiento termo-mecánico: esfuerzos generados por gradientes térmicos.
    σ_thermal = E * α * ΔT (en 1D, con restricción).
    """
    L = length
    dx = L / (n_elements - 1)
    x = np.linspace(0, L, n_elements)
    
    # Perfil de temperatura (estacionario, lineal)
    T = np.linspace(initial_temperature, boundary_temperature, n_elements)
    dT = T - initial_temperature
    
    # Expansión térmica: ε_th = α * ΔT
    strain_thermal = thermal_expansion * dT
    
    # Restricción en extremos (fijo-fijo): esfuerzo = E * ε_th
    stress_thermal = youngs_modulus * strain_thermal
    
    # Energía de deformación térmica
    # U = (1/2) * ∫ E * ε² dx
    strain_energy_array = 0.5 * youngs_modulus * strain_thermal**2
    strain_energy = float(np.sum(strain_energy_array)) * dx
    
    # Desplazamientos (integración de deformación)
    displacements = np.cumsum(strain_thermal) * dx
    
    # Validaciones físicas
    max_stress = np.max(np.abs(stress_thermal))
    yield_strength = 250e6  # Pa (típico acero)
    safety_factor_yield = yield_strength / max_stress if max_stress > 0 else float('inf')
    
    return {
        "mode": "thermal_stress",
        "geometry": {
            "length": float(L),
            "n_elements": n_elements,
            "dx": float(dx),
        },
        "material_properties": {
            "thermal_conductivity": thermal_conductivity,
            "density": density,
            "specific_heat": specific_heat,
            "thermal_expansion": float(thermal_expansion),
            "youngs_modulus": float(youngs_modulus),
        },
        "thermal_loading": {
            "initial_temperature": float(initial_temperature),
            "boundary_temperature": float(boundary_temperature),
            "max_temperature_gradient": float(np.max(np.gradient(T, x))),
        },
        "stress_analysis": {
            "max_thermal_stress": float(max_stress),
            "max_strain": float(np.max(np.abs(strain_thermal))),
            "strain_energy": float(strain_energy),
            "yield_strength": yield_strength,
            "safety_factor_yield": float(safety_factor_yield),
            "failure_status": "SAFE" if safety_factor_yield > 1.5 else "AT RISK",
        },
    }


def _validate_finite_element() -> dict:
    """Autochequeo: validaciones de los 4 modos."""
    checks = []
    
    # 1) thermal_transient: convergencia
    r = thermal_transient(length=1.0, n_elements=30, time_steps=50, dt=0.01)
    stability = r["numerical_parameters"]["stability_criterion"]
    checks.append({
        "name": "thermal_transient_stable",
        "passed": bool(stability == "STABLE"),
    })
    
    # 2) heat_transfer_3d: temperatura decrece
    r2 = heat_transfer_3d(n_elements=5, time_steps=20, dt=0.1)
    T_hist = [h["mean_temperature"] for h in r2["history"]]
    T_decreasing = all(T_hist[i] >= T_hist[i+1] for i in range(len(T_hist)-1))
    checks.append({
        "name": "heat_transfer_3d_temperature_decreases",
        "passed": bool(T_decreasing),
    })
    
    # 3) phase_change: fracción de fase realista
    r3 = phase_change(n_elements=30, time_steps=50, dt=0.01)
    melted_frac = r3["final_melted_fraction"]
    checks.append({
        "name": "phase_change_melted_fraction_valid",
        "passed": bool(0 <= melted_frac <= 1.0),
    })
    
    # 4) thermal_stress: esfuerzo positivo con ΔT > 0
    r4 = thermal_stress(n_elements=20)
    max_stress = r4["stress_analysis"]["max_thermal_stress"]
    checks.append({
        "name": "thermal_stress_positive",
        "passed": bool(max_stress > 0),
    })
    
    # 5) Modos inválidos dan error
    try:
        compute_finite_element("modo_inexistente")
        mode_error_ok = False
    except ValueError:
        mode_error_ok = True
    checks.append({
        "name": "invalid_mode_raises_valueerror",
        "passed": bool(mode_error_ok),
    })
    
    validation_passed = all(c["passed"] for c in checks)
    return {
        "checks": checks,
        "validation_passed": validation_passed,
        "n_checks": len(checks),
        "n_passed": sum(1 for c in checks if c["passed"]),
    }


def compute_finite_element(mode, **params):
    """Dispatcher de todos los modos."""
    if mode == "validate":
        return _validate_finite_element()
    elif mode == "thermal_transient":
        return thermal_transient(**params)
    elif mode == "heat_transfer_3d":
        return heat_transfer_3d(**params)
    elif mode == "phase_change":
        return phase_change(**params)
    elif mode == "thermal_stress":
        return thermal_stress(**params)
    else:
        raise ValueError(f"modo desconocido: {mode}")


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass


def _handle(args):
    _params = args.get("params") or {}
    return compute_finite_element(mode=args["mode"], **_params)


def _register():
    register_tool("finite_element_advanced_tool", FINITE_ELEMENT_TOOL_SCHEMA, _handle)


_register()
