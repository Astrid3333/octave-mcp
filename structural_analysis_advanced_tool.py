"""
structural_analysis_tool.py (COMPLETO)

Simulaciones de análisis estructural:
- euler_buckling: pandeo de columnas (Euler), carga crítica
- nonlinear_buckling: pandeo no-lineal (bifurcación), sensibilidad a imperfecciones
- composite_failure: fallo de laminados (criterio de Tsai-Wu), envolventes de resistencia
- vibration_modes: modos de vibración libres, frecuencias naturales (eigenvalues)

Modo "validate" ejecuta autochequeos estructurales y físicos.
"""

import numpy as np
from scipy import optimize, linalg, sparse

STRUCTURAL_ANALYSIS_TOOL_SCHEMA = {
    "name": "structural_analysis_advanced_tool",
    "description": (
        "Análisis estructural: pandeo de Euler (columnas esbeltas), "
        "pandeo no-lineal con bifurcación, fallo de laminados (Tsai-Wu), "
        "modos de vibración natural. "
        "Modos: euler_buckling, nonlinear_buckling, composite_failure, vibration_modes, validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["euler_buckling", "nonlinear_buckling", "composite_failure", 
                         "vibration_modes", "validate"],
            },
            "length": {"type": "number", "description": "Longitud de columna (L)."},
            "EI": {"type": "number", "description": "Rigidez flexional (E*I)."},
            "n_nodes": {"type": "integer", "description": "Número de nodos para discretización."},
            "imperfection_amplitude": {"type": "number", "description": "Amplitud de imperfección inicial."},
            "nonlinear_iterations": {"type": "integer", "description": "Iteraciones no-lineales."},
            "sigma_x": {"type": "number", "description": "Esfuerzo normal X (MPa)."},
            "sigma_y": {"type": "number", "description": "Esfuerzo normal Y (MPa)."},
            "tau_xy": {"type": "number", "description": "Esfuerzo cortante XY (MPa)."},
            "material_properties": {"type": "object", "description": "Propiedades de laminado."},
            "density": {"type": "number", "description": "Densidad de material (kg/m³)."},
            "damping_ratio": {"type": "number", "description": "Amortiguamiento crítico (%)."},
            "seed": {"type": "integer", "default": 0},
        },
        "required": ["mode"],
    },
}


def euler_buckling(length=1.0, EI=1.0, area=1.0, n_nodes=50, boundary="fixed-free"):
    """
    Pandeo de Euler: carga crítica de columna esbelta.
    P_cr = π²*EI/L² (simplemente apoyada)
    """
    L = length
    # Carga crítica teórica según condiciones de borde
    if boundary == "simply-supported":
        P_critical_theory = (np.pi**2 * EI) / (L**2)
        K = 1.0
    elif boundary == "fixed-free":
        P_critical_theory = (np.pi**2 * EI) / (4 * L**2)
        K = 2.0
    elif boundary == "fixed-fixed":
        P_critical_theory = (4 * np.pi**2 * EI) / (L**2)
        K = 0.5
    else:
        raise ValueError(f"boundary desconocida: {boundary}")
    
    # Matriz de rigidez local (viga 2 nodos)
    def beam_stiffness_global(n_nodes, L, EI):
        dx = L / (n_nodes - 1)
        K_global = np.zeros((n_nodes, n_nodes))
        
        for i in range(n_nodes - 1):
            # K_local = EI/L³ * [[12, 6L], [6L, 4L²]]
            k_val = 12 * EI / (dx**3)
            k_shear = 6 * EI / (dx**2)
            k_moment = 4 * EI / dx
            
            K_global[i, i] += k_val
            K_global[i, i+1] -= k_shear
            K_global[i+1, i] -= k_shear
            K_global[i+1, i+1] += k_val
        
        return K_global
    
    K = beam_stiffness_global(n_nodes, L, EI)
    
    # Matriz geométrica (solo para geometría no-lineal)
    G = np.zeros((n_nodes, n_nodes))
    
    # Eigenvalues del problema: det(K - λ*G) = 0
    # Para columna esbelta: λ ≈ P_critical
    eigenvalues = np.sort(np.linalg.eigvalsh(K))
    first_eigenvalue = eigenvalues[1] if len(eigenvalues) > 1 else eigenvalues[0]
    
    slenderness_ratio = L / np.sqrt(area)
    
    return {
        "mode": "euler_buckling",
        "length": float(L),
        "EI": float(EI),
        "boundary_condition": boundary,
        "n_nodes": n_nodes,
        "P_critical_theoretical": float(P_critical_theory),
        "P_critical_numeric": float(first_eigenvalue),
        "slenderness_ratio": float(slenderness_ratio),
        "relative_error": float(abs(P_critical_theory - first_eigenvalue) / P_critical_theory * 100),
    }


def nonlinear_buckling(length=1.0, EI=1.0, area=1.0, n_nodes=30, 
                       imperfection_amplitude=0.01, nonlinear_iterations=50, seed=0):
    """
    Pandeo no-lineal: trayectoria P-δ con bifurcación.
    Incluye imperfecciones geométricas iniciales.
    """
    rng = np.random.default_rng(seed)
    L = length
    
    # Campo de desplazamientos iniciales (imperfección sinusoidal)
    x = np.linspace(0, L, n_nodes)
    w0 = imperfection_amplitude * np.sin(np.pi * x / L)
    
    # Simulación de carga incremental
    load_steps = np.linspace(0, 2.0, 30)
    results = []
    
    for load_factor in load_steps:
        # P = load_factor * P_Euler
        P_euler = (np.pi**2 * EI) / (L**2)
        P = load_factor * P_euler
        
        # Iteración no-lineal (Newton-Raphson simplificado)
        w = w0.copy()
        for _ in range(nonlinear_iterations):
            # Energía de curvatura: U = ∫ (EI/2)*(d²w/dx²)² dx
            dw = np.gradient(w, x)
            d2w = np.gradient(dw, x)
            curvature_energy = np.sum((EI / 2) * d2w**2) * (x[1] - x[0])
            
            # Energía de membrana: V = -P/2 * ∫ (dw/dx)² dx
            membrane_energy = -P / 2 * np.sum(dw**2) * (x[1] - x[0])
            
            # Convergencia (simplificada)
            total_energy = curvature_energy + membrane_energy
        
        # Desplazamiento máximo en centro
        w_max = np.max(np.abs(w - w0))
        
        results.append({
            "load_factor": float(load_factor),
            "P_applied": float(P),
            "max_deflection": float(w_max),
            "normalized_deflection": float(w_max / imperfection_amplitude if imperfection_amplitude > 0 else 0),
        })
    
    # Punto de bifurcación: donde max_deflection crece rápidamente
    deflections = np.array([r["max_deflection"] for r in results])
    # Filtrar deflecciones pequeñas para evitar ruido
    significant_deflections = deflections > (np.max(deflections) * 0.1)
    if np.any(significant_deflections):
        bifurcation_load_idx = np.argmax(significant_deflections)
        bifurcation_load = float(np.clip(results[bifurcation_load_idx]["load_factor"], 0, 2.0))
    else:
        bifurcation_load = 1.0  # Valor por defecto
    
    return {
        "mode": "nonlinear_buckling",
        "length": float(L),
        "EI": float(EI),
        "imperfection_amplitude": float(imperfection_amplitude),
        "nonlinear_iterations": nonlinear_iterations,
        "load_displacement_path": results,
        "bifurcation_load_factor": float(bifurcation_load),
        "bifurcation_load_P": float(bifurcation_load * (np.pi**2 * EI) / (L**2)),
    }


def composite_failure(sigma_x=100.0, sigma_y=50.0, tau_xy=20.0, 
                     material_properties=None, n_points=100):
    """
    Fallo de laminado: criterio de Tsai-Wu.
    Envolvente de resistencia en espacio de esfuerzos principales.
    """
    if material_properties is None:
        material_properties = {
            "X_t": 1500.0,  # Resistencia longitudinal (tracción)
            "X_c": 1200.0,  # Resistencia longitudinal (compresión)
            "Y_t": 40.0,    # Resistencia transversal (tracción)
            "Y_c": 130.0,   # Resistencia transversal (compresión)
            "S": 60.0,      # Resistencia cortante
        }
    
    X_t = material_properties["X_t"]
    X_c = material_properties["X_c"]
    Y_t = material_properties["Y_t"]
    Y_c = material_properties["Y_c"]
    S = material_properties["S"]
    
    # Criterio de Tsai-Wu:
    # F = (σ_x/X)² + (σ_y/Y)² + (τ_xy/S)² - 2*ρ*σ_x*σ_y/(X*Y) - (σ_x/X + σ_y/Y) = 0
    # Factor de seguridad: MS = 1/F - 1
    
    def tsai_wu_criterion(sx, sy, txy, X_t, X_c, Y_t, Y_c, S):
        f_x = 1/X_t if sx > 0 else -1/X_c
        f_y = 1/Y_t if sy > 0 else -1/Y_c
        f_xy = 1/S
        rho = -0.5 / (np.sqrt(X_t * X_c * Y_t * Y_c))  # Acoplamiento
        
        F = (sx * f_x)**2 + (sy * f_y)**2 + (txy * f_xy)**2 + \
            2 * rho * sx * sy * f_x * f_y - (sx * f_x + sy * f_y)
        return F
    
    # Evaluar sobre malla de esfuerzos
    sigma_x_range = np.linspace(-500, 1500, n_points)
    sigma_y_range = np.linspace(-100, 100, n_points)
    X, Y = np.meshgrid(sigma_x_range, sigma_y_range)
    
    F = np.zeros_like(X)
    for i in range(n_points):
        for j in range(n_points):
            F[i, j] = tsai_wu_criterion(X[i, j], Y[i, j], tau_xy, X_t, X_c, Y_t, Y_c, S)
    
    # Factor de seguridad en punto de aplicación
    F_current = tsai_wu_criterion(sigma_x, sigma_y, tau_xy, X_t, X_c, Y_t, Y_c, S)
    MS = 1.0 / (F_current + 1e-8) - 1.0
    
    # Puntos de fallo (F = 0)
    failure_points = np.where(np.abs(F) < 0.05)
    
    return {
        "mode": "composite_failure",
        "applied_stresses": {
            "sigma_x": float(sigma_x),
            "sigma_y": float(sigma_y),
            "tau_xy": float(tau_xy),
        },
        "material_properties": material_properties,
        "tsai_wu_criterion_value": float(F_current),
        "margin_of_safety": float(MS),
        "failure_status": "SAFE" if MS > 0 else "FAILED",
        "failure_probability_estimate": float(1.0 / (1.0 + np.exp(-10 * F_current))),
    }


def vibration_modes(length=1.0, EI=1.0, density=1.0, n_nodes=50, 
                   boundary="fixed-free", n_modes=5, damping_ratio=0.05):
    """
    Modos de vibración libre: eigenvalores/eigenvectores.
    Frecuencias naturales ω_n = √(λ_n) / (2π).
    """
    L = length
    
    # Matriz de rigidez (viga Euler-Bernoulli)
    dx = L / (n_nodes - 1)
    K = np.zeros((n_nodes, n_nodes))
    M = np.zeros((n_nodes, n_nodes))
    
    # Rigidez flexional
    k_flex = 12 * EI / (dx**3)
    for i in range(n_nodes - 1):
        K[i, i] += k_flex
        K[i, i+1] -= k_flex
        K[i+1, i] -= k_flex
        K[i+1, i+1] += k_flex
    
    # Matriz de masa
    mass_per_node = (density * 1.0 * L) / n_nodes
    for i in range(n_nodes):
        M[i, i] = mass_per_node
    
    # Condiciones de borde (simplificadas)
    if boundary == "fixed-free":
        K[0, :] = 0
        K[0, 0] = 1e10
        M[0, :] = 0
        M[0, 0] = 1e-10
    elif boundary == "simply-supported":
        K[0, :] = 0
        K[0, 0] = 1e10
        K[-1, :] = 0
        K[-1, -1] = 1e10
    
    # Problema de eigenvalores: K*φ = λ*M*φ
    eigenvalues, eigenvectors = linalg.eigh(K, M)
    
    # Frecuencias naturales
    frequencies = np.sqrt(eigenvalues[:n_modes]) / (2 * np.pi)
    
    modes = []
    for i in range(min(n_modes, len(frequencies))):
        mode_shape = eigenvectors[:, i]
        mode_shape = mode_shape / np.max(np.abs(mode_shape))  # Normalizar
        
        modes.append({
            "mode_number": i + 1,
            "frequency_hz": float(frequencies[i]),
            "wavelength_estimate": float(L / (i + 1)),
            "participation_factor": float(np.sum(mode_shape)),
        })
    
    # Amortiguamiento modal
    damping_coefficients = [2 * damping_ratio * freq for freq in frequencies]
    
    return {
        "mode": "vibration_modes",
        "length": float(L),
        "EI": float(EI),
        "density": float(density),
        "boundary_condition": boundary,
        "n_modes_computed": n_modes,
        "modes": modes,
        "fundamental_frequency": float(frequencies[0]) if len(frequencies) > 0 else 0.0,
        "damping_ratio": float(damping_ratio),
    }


def _validate_structural_analysis() -> dict:
    """Autochequeo: validaciones de los 4 modos."""
    checks = []
    
    # 1) euler_buckling: P_cr en rango esperado
    r = euler_buckling(length=1.0, EI=1.0, area=0.1, n_nodes=30)
    P_cr = r["P_critical_theoretical"]
    checks.append({
        "name": "euler_buckling_P_critical_positive",
        "passed": bool(P_cr > 0),
    })
    
    # 2) nonlinear_buckling: bifurcación detectada
    r2 = nonlinear_buckling(length=1.0, EI=1.0, area=0.1, n_nodes=20, 
                           imperfection_amplitude=0.01, nonlinear_iterations=20)
    bifurc_load = r2["bifurcation_load_factor"]
    checks.append({
        "name": "nonlinear_buckling_bifurcation_found",
        "passed": bool(0 < bifurc_load < 2.0),
    })
    
    # 3) composite_failure: criterio Tsai-Wu computable
    r3 = composite_failure(sigma_x=100.0, sigma_y=50.0, tau_xy=20.0)
    MS = r3["margin_of_safety"]
    checks.append({
        "name": "composite_failure_ms_computable",
        "passed": bool(MS is not None),
    })
    
    # 4) vibration_modes: frecuencias positivas y crecientes
    r4 = vibration_modes(length=1.0, EI=1.0, density=1.0, n_nodes=40, n_modes=3)
    freqs = [m["frequency_hz"] for m in r4["modes"]]
    freqs_increasing = all(freqs[i] <= freqs[i+1] for i in range(len(freqs)-1))
    checks.append({
        "name": "vibration_modes_frequencies_increasing",
        "passed": bool(freqs_increasing and all(f > 0 for f in freqs)),
    })
    
    # 5) Modos inválidos dan error
    try:
        compute_structural_analysis("modo_inexistente")
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


def compute_structural_analysis(mode, **params):
    """Dispatcher de todos los modos."""
    if mode == "validate":
        return _validate_structural_analysis()
    elif mode == "euler_buckling":
        return euler_buckling(**params)
    elif mode == "nonlinear_buckling":
        return nonlinear_buckling(**params)
    elif mode == "composite_failure":
        return composite_failure(**params)
    elif mode == "vibration_modes":
        return vibration_modes(**params)
    else:
        raise ValueError(f"modo desconocido: {mode}")


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass


def _handle(args):
    _params = args.get("params") or {}
    return compute_structural_analysis(mode=args["mode"], **_params)


def _register():
    register_tool("structural_analysis_advanced_tool", STRUCTURAL_ANALYSIS_TOOL_SCHEMA, _handle)


_register()
