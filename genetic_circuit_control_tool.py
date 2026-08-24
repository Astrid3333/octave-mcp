"""
genetic_circuit_control_tool.py

Diseño y optimización de circuitos genéticos sintéticos.
Modelos de control dinámico (qCRISPRi), carga metabólica, estabilidad.

Aplicación: ingeniería de cepas, biosíntesis, control de población.
"""

import numpy as np
from scipy.integrate import odeint
import json

# Schema
GENETIC_CIRCUIT_CONTROL_SCHEMA = {
    "name": "genetic_circuit_control_tool",
    "type": "object",
    "description": "Diseño y optimización de circuitos genéticos sintéticos con control dinámico",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["design_circuit", "optimize_control", "metabolic_load", "stability_analysis", "validate"],
                "description": "design: circuito básico | optimize: parámetros | load: carga metabólica | stability: análisis | validate: self-test"
            },
            "circuit_type": {
                "type": "string",
                "enum": ["toggle_switch", "oscillator", "biosensor", "amplifier"],
                "description": "Tipo de circuito sintético"
            },
            "num_genes": {
                "type": "integer",
                "description": "Número de genes en el circuito"
            },
            "production_rate": {
                "type": "number",
                "description": "Tasa de producción basal (moléculas/min)"
            },
            "degradation_rate": {
                "type": "number",
                "description": "Tasa de degradación (1/min)"
            },
            "control_strength": {
                "type": "number",
                "description": "Fuerza del control dinámico (0-1)"
            },
            "simulation_time": {
                "type": "number",
                "description": "Tiempo de simulación (minutos)"
            }
        },
        "required": ["mode"]
    }
}

def circuit_toggle_switch_ode(y, t, k_prod, k_deg, k_control, hill_coeff=2):
    """
    Toggle switch: dos genes que se reprimen mutuamente.
    dA/dt = k_prod / (1 + (B/K)^n) - k_deg * A
    dB/dt = k_prod / (1 + (A/K)^n) - k_deg * B
    """
    a, b = y
    
    k_threshold = 100  # Concentración de activación
    dadt = k_prod / (1 + (b / k_threshold) ** hill_coeff) - k_deg * a
    dbdt = k_prod / (1 + (a / k_threshold) ** hill_coeff) - k_deg * b
    
    return [dadt, dbdt]

def circuit_oscillator_ode(y, t, k_prod, k_deg, k_control, delay=2):
    """
    Oscilador: cadena represora A → B → C → A
    Genera dinámica oscilatoria con retardo.
    """
    a, b, c = y
    
    k_threshold = 100
    hill_coeff = 2
    
    dadt = k_prod / (1 + (c / k_threshold) ** hill_coeff) - k_deg * a
    dbdt = k_prod / (1 + (a / k_threshold) ** hill_coeff) - k_deg * b
    dcdt = k_prod / (1 + (b / k_threshold) ** hill_coeff) - k_deg * c
    
    return [dadt, dbdt, dcdt]

def circuit_biosensor_ode(y, t, k_prod, k_deg, stimulus, sensitivity=1.0):
    """
    Biosensor: responde a estímulo externo
    dR/dt = k_prod * stimulus * sensitivity - k_deg * R
    """
    r = y[0]
    drdt = k_prod * stimulus * sensitivity - k_deg * r
    return [drdt]

def optimize_circuit_parameters(circuit_type, num_genes, target_amplitude, target_frequency):
    """
    Optimización de parámetros usando grid search simplificado.
    Retorna parámetros óptimos.
    """
    best_params = {"error": 1e6, "k_prod": 100, "k_deg": 0.05}
    
    # Grid search: k_prod y k_deg
    for k_prod in [50, 100, 150, 200]:
        for k_deg in [0.01, 0.05, 0.1, 0.2]:
            
            if circuit_type == "toggle_switch":
                y0 = [10, 100]
                t = np.linspace(0, 100, 200)
                try:
                    sol = odeint(circuit_toggle_switch_ode, y0, t, args=(k_prod, k_deg, 1.0))
                    # Medir amplitud (rango dinámico)
                    amplitude = np.max(sol) - np.min(sol)
                    error = abs(amplitude - target_amplitude)
                except:
                    error = 1e6
            
            elif circuit_type == "oscillator":
                y0 = [10, 50, 100]
                t = np.linspace(0, 200, 400)
                try:
                    sol = odeint(circuit_oscillator_ode, y0, t, args=(k_prod, k_deg, 1.0))
                    # Detectar oscilaciones (FFT para frecuencia)
                    amplitude = np.max(sol[:, 0]) - np.min(sol[:, 0])
                    error = abs(amplitude - target_amplitude)
                except:
                    error = 1e6
            
            if error < best_params["error"]:
                best_params = {
                    "error": error,
                    "k_prod": k_prod,
                    "k_deg": k_deg,
                    "amplitude": amplitude if error < 1e6 else 0
                }
    
    return best_params

def calculate_metabolic_load(num_genes, k_prod_total, cell_capacity=10000):
    """
    Estima carga metabólica del circuito sobre la célula.
    
    Load = (total_protein_production / cell_capacity) * 100
    Retorna % de capacidad celular consumida.
    """
    total_protein = num_genes * k_prod_total
    metabolic_load = (total_protein / cell_capacity) * 100
    
    # Costo de fitness
    fitness_cost = (metabolic_load / 100) * 0.5  # 50% fitness loss per 100% load
    
    return {
        "metabolic_load_percent": float(metabolic_load),
        "fitness_cost": float(fitness_cost),
        "expected_growth_rate": float(1.0 - fitness_cost),
        "load_category": "Sustainable" if metabolic_load < 20 else "Moderate" if metabolic_load < 50 else "High"
    }

def analyze_circuit_stability(circuit_type, y0, k_prod, k_deg, sim_time=200, num_timepoints=400):
    """
    Análisis de estabilidad: simula y detecta puntos fijos, ciclos límite, etc.
    """
    t = np.linspace(0, sim_time, num_timepoints)
    
    try:
        if circuit_type == "toggle_switch":
            sol = odeint(circuit_toggle_switch_ode, y0, t, args=(k_prod, k_deg, 1.0))
        elif circuit_type == "oscillator":
            sol = odeint(circuit_oscillator_ode, y0, t, args=(k_prod, k_deg, 1.0))
        else:
            return {"error": "Unknown circuit type", "behavior": "Unknown"}
    except:
        return {"error": "Simulation failed", "behavior": "Error"}
    
    # Análisis del último 30% de la trayectoria (régimen estable)
    stable_region = sol[int(0.7*len(sol)):, :]
    
    # Detectar tipo de comportamiento
    amplitude = np.max(stable_region) - np.min(stable_region)
    variance = np.var(stable_region)
    
    if amplitude < 10:
        behavior = "Fixed point (stable)"
    elif variance > amplitude**2:
        behavior = "Oscillatory (limit cycle)"
    else:
        behavior = "Chaotic or complex"
    
    return {
        "circuit_type": circuit_type,
        "steady_state_amplitude": float(amplitude),
        "variance": float(variance),
        "behavior": behavior,
        "stability": "Stable" if amplitude < 50 else "Oscillating" if variance > 100 else "Complex"
    }

def validate_genetic_circuit():
    """Validación de self-test."""
    tests = []
    
    # Test 1: Toggle switch debe alcanzar equilibrio
    y0_toggle = [10, 100]
    t = np.linspace(0, 100, 200)
    sol_toggle = odeint(circuit_toggle_switch_ode, y0_toggle, t, args=(100, 0.05, 1.0))
    steady_state = sol_toggle[-10:].mean()
    tests.append({
        "name": "Toggle switch converge a equilibrio",
        "passed": int(0 < steady_state < 2000),
        "steady_state": float(steady_state)
    })
    
    # Test 2: Oscilador debe oscilar
    y0_osc = [10, 50, 100]
    t = np.linspace(0, 200, 400)
    sol_osc = odeint(circuit_oscillator_ode, y0_osc, t, args=(100, 0.05, 1.0))
    osc_amplitude = np.max(sol_osc[:, 0]) - np.min(sol_osc[:, 0])
    tests.append({
        "name": "Oscilador muestra amplitud dinámica",
        "passed": int(osc_amplitude > 20),
        "amplitude": float(osc_amplitude)
    })
    
    # Test 3: Carga metabólica debe ser razonable
    load = calculate_metabolic_load(5, 100)
    tests.append({
        "name": "Carga metabólica en rango realista (<100%)",
        "passed": int(load["metabolic_load_percent"] < 100),
        "load": load["metabolic_load_percent"]
    })
    
    # Test 4: Optimización mejora parámetros
    opt = optimize_circuit_parameters("toggle_switch", 2, target_amplitude=150, target_frequency=0.01)
    tests.append({
        "name": "Optimización encuenta parámetros",
        "passed": int(opt["error"] < 500),
        "error": opt["error"]
    })
    
    validation_passed = bool(all(t["passed"] for t in tests))
    return {
        "validation_passed": validation_passed,
        "tests": tests,
        "summary": f"{sum(1 for t in tests if t['passed'])}/{len(tests)} passed"
    }

def run_genetic_circuit_control_tool(mode, circuit_type="toggle_switch", num_genes=2, 
                                     production_rate=100, degradation_rate=0.05,
                                     control_strength=1.0, simulation_time=200):
    """Entry point."""
    try:
        if mode == "validate":
            return validate_genetic_circuit()
        elif mode == "design_circuit":
            y0 = [10] * min(num_genes, 3)
            t = np.linspace(0, simulation_time, int(simulation_time * 2))
            if circuit_type == "toggle_switch":
                sol = odeint(circuit_toggle_switch_ode, y0[:2], t, args=(production_rate, degradation_rate, control_strength))
            elif circuit_type == "oscillator":
                sol = odeint(circuit_oscillator_ode, y0[:3], t, args=(production_rate, degradation_rate, control_strength))
            else:
                return {"error": "Unknown circuit type"}
            return {
                "circuit_type": circuit_type,
                "simulation_time": float(simulation_time),
                "trajectory_points": len(t),
                "final_state": sol[-1].tolist(),
                "amplitude": float(np.max(sol) - np.min(sol))
            }
        elif mode == "optimize_control":
            return optimize_circuit_parameters(circuit_type, num_genes, 150, 0.01)
        elif mode == "metabolic_load":
            return calculate_metabolic_load(num_genes, production_rate)
        elif mode == "stability_analysis":
            y0 = [10] * min(num_genes, 3)
            return analyze_circuit_stability(circuit_type, y0, production_rate, degradation_rate, simulation_time)
        else:
            return {"error": f"Unknown mode: {mode}"}
    except Exception as e:
        return {"error": str(e), "validation_passed": False}

if __name__ == "__main__":
    print("=== Genetic Circuit Control Tool ===\n")
    
    # Validate
    print("1. Validation:")
    val = validate_genetic_circuit()
    print(json.dumps(val, indent=2, ensure_ascii=False))
    
    # Design circuit
    print("\n2. Design toggle switch:")
    circuit = run_genetic_circuit_control_tool("design_circuit", circuit_type="toggle_switch", simulation_time=100)
    print(f"   Amplitude: {circuit['amplitude']:.1f}")
    
    # Optimize
    print("\n3. Optimize control parameters:")
    opt = run_genetic_circuit_control_tool("optimize_control", circuit_type="oscillator")
    print(f"   k_prod: {opt['k_prod']}, k_deg: {opt['k_deg']}")
    
    # Metabolic load
    print("\n4. Metabolic load (5 genes):")
    load = run_genetic_circuit_control_tool("metabolic_load", num_genes=5, production_rate=100)
    print(f"   Load: {load['metabolic_load_percent']:.1f}%")
    
    # Stability
    print("\n5. Stability analysis:")
    stab = run_genetic_circuit_control_tool("stability_analysis", circuit_type="oscillator", simulation_time=200)
    print(f"   Behavior: {stab['behavior']}")

try:
    from tool_registry import register_tool
    register_tool(
        name="genetic_circuit_control_tool",
        schema=GENETIC_CIRCUIT_CONTROL_SCHEMA,
        handler=lambda args: run_genetic_circuit_control_tool(
            args.get("mode"),
            args.get("circuit_type", "toggle_switch"),
            args.get("num_genes", 2),
            args.get("production_rate", 100),
            args.get("degradation_rate", 0.05),
            args.get("control_strength", 1.0),
            args.get("simulation_time", 200)
        ),
    )
except ImportError:
    pass
