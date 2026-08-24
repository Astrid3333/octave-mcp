"""
gene_drive_population_tool.py

Modelos de herencia y dinámica de poblaciones para gene drives.
Simula cómo se propaga una modificación genética en una población.

Aplicación: control de poblaciones (ej. mosquitos), análisis de impacto.
"""

import numpy as np
from scipy.integrate import odeint
import json

# Schema
GENE_DRIVE_POPULATION_SCHEMA = {
    "name": "gene_drive_population_tool",
    "type": "object",
    "description": "Modelos MGDrivE: herencia genética y dinámica poblacional con gene drives",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["mendelian", "gene_drive", "analyze_spread", "impact_report", "validate"],
                "description": "mendelian: herencia clásica | gene_drive: con modificación | analyze_spread: propagación temporal | impact_report: resumen | validate: self-test"
            },
            "initial_population": {
                "type": "number",
                "description": "Población inicial total"
            },
            "initial_modified_freq": {
                "type": "number",
                "description": "Frecuencia inicial del alelo modificado (0-1)"
            },
            "generations": {
                "type": "integer",
                "description": "Número de generaciones a simular"
            },
            "cutting_efficiency": {
                "type": "number",
                "description": "Eficiencia de corte del gene drive (0-1), default 0.95"
            },
            "fitness_cost": {
                "type": "number",
                "description": "Costo de fitness del alelo modificado (0-1), default 0.0"
            },
            "density_dependence": {
                "type": "number",
                "description": "Factor de dependencia de densidad, default 0.001"
            }
        },
        "required": ["mode", "initial_population", "initial_modified_freq", "generations"]
    }
}

def gene_drive_inheritance(freq_wild, freq_hetero, freq_modified, cutting_eff):
    """
    Herencia simplificada con gene drive: ventaja selectiva del alelo modificado.
    El drive aumenta la frecuencia del alelo modificado por cada generación.
    """
    # Frecuencia alélica total (p = wild, q = modificado)
    p = freq_wild
    q = freq_modified
    
    # Gene drive: copia el alelo modificado (copying advantage)
    # drive_advantage aumenta la frecuencia de q por el cutting efficiency
    drive_advantage = cutting_eff * q * (1 - q)
    
    q_new = q + drive_advantage
    p_new = 1.0 - q_new
    
    # Mantener en rango [0,1]
    q_new = max(0, min(1, q_new))
    p_new = 1.0 - q_new
    
    # Para mantener compatibilidad con heterocigotos
    freq_hetero_new = 2 * p_new * q_new
    
    return p_new, freq_hetero_new, q_new


def population_dynamics_ode(y, t, density_dependence, fitness_cost):
    """Dinámica poblacional con dependencia de densidad."""
    n_w, n_h, n_m = y
    total_pop = n_w + n_h + n_m
    
    lambda_growth = 2.0
    k_capacity = 10000
    
    dens_factor = 1.0 - (total_pop / k_capacity) * density_dependence
    
    fitness_w = 1.0
    fitness_h = 1.0 - 0.5 * fitness_cost
    fitness_m = 1.0 - fitness_cost
    
    dn_w_dt = n_w * lambda_growth * fitness_w * dens_factor
    dn_h_dt = n_h * lambda_growth * fitness_h * dens_factor
    dn_m_dt = n_m * lambda_growth * fitness_m * dens_factor
    
    return [dn_w_dt, dn_h_dt, dn_m_dt]

def simulate_mendelian(initial_pop, initial_modified_freq, generations):
    """Herencia mendeliana clásica."""
    freq_wild = 1.0 - initial_modified_freq
    freq_modified = initial_modified_freq
    
    history = {"generations": [], "freq_wild": [], "freq_modified": []}
    
    for gen in range(generations):
        history["generations"].append(gen)
        history["freq_wild"].append(freq_wild)
        history["freq_modified"].append(freq_modified)
        
        freq_wild = freq_wild**2 + 2*freq_wild*freq_modified*0.5
        freq_modified = freq_modified**2 + 2*freq_wild*freq_modified*0.5
        
        total = freq_wild + freq_modified
        freq_wild /= total
        freq_modified /= total
    
    return {
        "history": history,
        "final_freq_modified": float(freq_modified),
        "equilibrium_reached": abs(history["freq_modified"][-1] - history["freq_modified"][-2]) < 0.001 if len(history["freq_modified"]) > 1 else False
    }

def simulate_gene_drive(initial_pop, initial_modified_freq, generations, cutting_eff=0.95, fitness_cost=0.0, density_dep=0.001):
    """Simulación con gene drive."""
    freq_wild = 1.0 - initial_modified_freq
    freq_hetero = 0.0
    freq_modified = initial_modified_freq
    
    history = {
        "generations": [],
        "freq_wild": [],
        "freq_hetero": [],
        "freq_modified": [],
        "population": []
    }
    
    pop = initial_pop
    
    for gen in range(generations):
        history["generations"].append(gen)
        history["freq_wild"].append(float(freq_wild))
        history["freq_hetero"].append(float(freq_hetero))
        history["freq_modified"].append(float(freq_modified))
        history["population"].append(float(pop))
        
        freq_wild, freq_hetero, freq_modified = gene_drive_inheritance(
            freq_wild, freq_hetero, freq_modified, cutting_eff
        )
        
        y0 = [pop * freq_wild, pop * freq_hetero, pop * freq_modified]
        t = [0, 1]
        sol = odeint(population_dynamics_ode, y0, t, args=(density_dep, fitness_cost))
        
        n_w, n_h, n_m = sol[-1]
        pop = max(1, n_w + n_h + n_m)
        
        if freq_wild + freq_hetero + freq_modified == 0:
            break
    
    return {
        "history": history,
        "final_freq_modified": float(freq_modified),
        "final_population": float(pop),
        "generations_to_fixation": len(history["generations"]),
        "spread_success": int(freq_modified > 0.9)
    }

def analyze_spread(initial_pop, initial_modified_freq, generations, cutting_eff=0.95, fitness_cost=0.0):
    """Análisis de propagación."""
    result = simulate_gene_drive(initial_pop, initial_modified_freq, generations, cutting_eff, fitness_cost)
    
    freqs = result["history"]["freq_modified"]
    if len(freqs) > 1:
        velocities = [freqs[i+1] - freqs[i] for i in range(len(freqs)-1)]
        avg_velocity = float(np.mean(velocities)) if velocities else 0.0
    else:
        avg_velocity = 0.0
    
    return {
        "spread_result": result,
        "average_velocity": avg_velocity,
        "max_velocity": float(max(velocities)) if velocities else 0.0,
        "time_to_50_percent": int(next((i for i, f in enumerate(freqs) if f > 0.5), -1)),
        "time_to_90_percent": int(next((i for i, f in enumerate(freqs) if f > 0.9), -1))
    }

def impact_report(initial_pop, initial_modified_freq, generations, cutting_eff=0.95, fitness_cost=0.0, density_dep=0.001):
    """Reporte de impacto poblacional."""
    result = simulate_gene_drive(initial_pop, initial_modified_freq, generations, cutting_eff, fitness_cost, density_dep)
    
    final_pop = result["final_population"]
    pop_change_percent = ((final_pop - initial_pop) / initial_pop) * 100 if initial_pop > 0 else 0
    
    return {
        "initial_population": float(initial_pop),
        "final_population": float(final_pop),
        "population_change_percent": float(pop_change_percent),
        "final_modified_frequency": float(result["final_freq_modified"]),
        "spread_successful": int(result["spread_success"]),
        "generations_simulated": int(result["generations_to_fixation"]),
        "impact_assessment": "Control exitoso" if pop_change_percent < -50 else "Moderado" if pop_change_percent < -20 else "Bajo"
    }

def validate_gene_drive():
    """Validación de self-test."""
    tests = []
    
    # Test 1: Sin drive, alelo recesivo debería desaparecer
    mend = simulate_mendelian(1000, 0.1, 50)
    tests.append({
        "name": "Sin drive: alelo recesivo desaparece",
        "passed": int(mend["final_freq_modified"] < 0.05),
        "freq": mend["final_freq_modified"]
    })
    
    # Test 2: Con drive eficiente, debe propagarse
    drive = simulate_gene_drive(1000, 0.01, 100, cutting_eff=0.95)
    tests.append({
        "name": "Con drive (95% eficiencia): propagación exitosa",
        "passed": int(drive["final_freq_modified"] > 0.5),
        "freq": drive["final_freq_modified"]
    })
    
    # Test 3: Drive con bajo fitness cost debería propagarse igual
    drive_cost = simulate_gene_drive(1000, 0.01, 100, cutting_eff=0.95, fitness_cost=0.1)
    tests.append({
        "name": "Drive con fitness cost (10%): aún se propaga",
        "passed": int(drive_cost["final_freq_modified"] > 0.3),
        "freq": drive_cost["final_freq_modified"]
    })
    
    # Test 4: Análisis de velocidad
    analyze = analyze_spread(1000, 0.05, 50, cutting_eff=0.95)
    tests.append({
        "name": "Velocidad de propagación positiva",
        "passed": int(analyze["average_velocity"] > 0),
        "velocity": analyze["average_velocity"]
    })
    
    validation_passed = bool(all(t["passed"] for t in tests))
    return {
        "validation_passed": validation_passed,
        "tests": tests,
        "summary": f"{sum(1 for t in tests if t['passed'])}/{len(tests)} passed"
    }

def run_gene_drive_population_tool(mode, initial_population=None, initial_modified_freq=None, 
                                    generations=None, cutting_efficiency=0.95, fitness_cost=0.0, 
                                    density_dependence=0.001):
    """Entry point."""
    try:
        if mode == "validate":
            return validate_gene_drive()
        elif mode == "mendelian":
            return simulate_mendelian(initial_population, initial_modified_freq, generations)
        elif mode == "gene_drive":
            return simulate_gene_drive(initial_population, initial_modified_freq, generations, 
                                      cutting_efficiency, fitness_cost, density_dependence)
        elif mode == "analyze_spread":
            return analyze_spread(initial_population, initial_modified_freq, generations, 
                                 cutting_efficiency, fitness_cost)
        elif mode == "impact_report":
            return impact_report(initial_population, initial_modified_freq, generations, 
                               cutting_efficiency, fitness_cost, density_dependence)
        else:
            return {"error": f"Unknown mode: {mode}"}
    except Exception as e:
        return {"error": str(e), "validation_passed": False}

if __name__ == "__main__":
    print("=== Gene Drive Population Tool ===\n")
    
    # Validate
    print("1. Validation:")
    val = validate_gene_drive()
    print(json.dumps(val, indent=2, ensure_ascii=False))
    
    # Mendelian
    print("\n2. Mendelian (10% freq inicial, 30 generaciones):")
    mend = simulate_mendelian(1000, 0.1, 30)
    print(f"   Final freq: {mend['final_freq_modified']:.4f}")
    
    # Gene drive
    print("\n3. Gene drive (1% freq inicial, 95% cutting, 50 gen):")
    drive = simulate_gene_drive(1000, 0.01, 50, cutting_eff=0.95)
    print(f"   Final freq: {drive['final_freq_modified']:.4f}")
    print(f"   Final pop: {drive['final_population']:.0f}")
    
    # Impact
    print("\n4. Impact report:")
    impact = impact_report(1000, 0.05, 100, cutting_eff=0.95)
    print(json.dumps(impact, indent=2, ensure_ascii=False))

try:
    from tool_registry import register_tool
    register_tool(
        name="gene_drive_population_tool",
        schema=GENE_DRIVE_POPULATION_SCHEMA,
        handler=lambda args: run_gene_drive_population_tool(
            args.get("mode"),
            args.get("initial_population"),
            args.get("initial_modified_freq"),
            args.get("generations"),
            args.get("cutting_efficiency", 0.95),
            args.get("fitness_cost", 0.0),
            args.get("density_dependence", 0.001)
        ),
    )
except ImportError:
    pass
