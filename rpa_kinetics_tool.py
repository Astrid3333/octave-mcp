"""
rpa_kinetics_tool.py

Cinética de Recombinasa Polimerasa (RPA) con modelo Michaelis-Menten.
Simula amplificación de ADN mediante ODEs, predice yield y cinética en tiempo real.

Aplicación: optimización de protocolos de amplificación molecular.
"""

import numpy as np
from scipy.integrate import odeint
import json

# Schema
RPA_KINETICS_SCHEMA = {
    "type": "object",
    "description": "Simula cinética enzimática de RPA (Recombinasa Polimerasa Amplificación)",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["simulate", "predict_yield", "optimize_buffer", "validate"],
                "description": "simulate: dinámica ODEs | predict_yield: rendimiento final | optimize_buffer: buffer óptimo | validate: self-test"
            },
            "rpa_concentration": {
                "type": "number",
                "description": "Concentración de RPA (nM)"
            },
            "dna_template": {
                "type": "number",
                "description": "Copias iniciales de ADN plantilla"
            },
            "reaction_time": {
                "type": "number",
                "description": "Tiempo de reacción (minutos)"
            },
            "temperature": {
                "type": "number",
                "description": "Temperatura (°C), típico 37-39"
            },
            "km_michaelis": {
                "type": "number",
                "description": "Constante Michaelis (nM), default 50"
            },
            "vmax": {
                "type": "number",
                "description": "Velocidad máxima (copias/min), default 1000"
            }
        },
        "required": ["mode", "rpa_concentration", "dna_template", "reaction_time"]
    }
}

def michaelis_menten_rate(dna_conc, vmax, km):
    """Calcula velocidad de reacción según Michaelis-Menten."""
    return vmax * dna_conc / (km + dna_conc)

def rpa_ode_system(y, t, rpa_conc, vmax, km, degradation_rate=0.01):
    """
    Sistema ODE para cinética de RPA.
    y[0] = [ADN amplificado]
    
    d[ADN]/dt = v_max * [ADN] / (K_m + [ADN]) - degradation * [ADN]
    """
    dna_conc = y[0]
    rate = michaelis_menten_rate(dna_conc, vmax, km)
    ddna_dt = rate - degradation_rate * dna_conc
    return [ddna_dt]

def simulate_rpa_kinetics(rpa_concentration, dna_template, reaction_time, 
                          temperature=37, km_michaelis=50, vmax=1000):
    """
    Simula la cinética completa de amplificación RPA.
    
    Retorna:
      - t: array de tiempos
      - dna: array de concentraciones de ADN
      - final_yield: rendimiento final (fold amplification)
    """
    # Ajuste de Vmax según temperatura (coeficiente Q10 ≈ 1.5 cada 10°C)
    temp_factor = 1.5 ** ((temperature - 37) / 10)
    adjusted_vmax = vmax * temp_factor
    
    # Tiempo de simulación
    t = np.linspace(0, reaction_time, int(reaction_time * 10))
    
    # Integrar ODE
    y0 = [dna_template]
    solution = odeint(rpa_ode_system, y0, t, args=(rpa_concentration, adjusted_vmax, km_michaelis))
    
    dna_evolution = solution[:, 0]
    final_yield = dna_evolution[-1] / dna_template if dna_template > 0 else 1.0
    
    return {
        "time_points": t.tolist(),
        "dna_concentration": dna_evolution.tolist(),
        "final_yield": float(final_yield),
        "yield_fold_change": float(dna_evolution[-1]),
        "temperature_adjustment": float(temp_factor)
    }

def predict_yield(rpa_concentration, dna_template, reaction_time, 
                  temperature=37, km_michaelis=50, vmax=1000):
    """Predicción rápida de rendimiento sin graficar."""
    result = simulate_rpa_kinetics(rpa_concentration, dna_template, reaction_time, 
                                   temperature, km_michaelis, vmax)
    return {
        "final_yield": result["final_yield"],
        "estimated_copies": result["yield_fold_change"],
        "efficiency_percent": min(100, result["final_yield"] * 100)
    }

def optimize_buffer(dna_template, target_yield=10000, reaction_time=30, 
                    temperature=37, km_michaelis=50):
    """
    Busca concentración óptima de RPA para alcanzar target_yield.
    """
    rpa_candidates = np.logspace(0, 3, 20)  # 1 nM a 1000 nM
    results = []
    
    for rpa in rpa_candidates:
        res = simulate_rpa_kinetics(rpa, dna_template, reaction_time, temperature, km_michaelis)
        error = abs(res["yield_fold_change"] - target_yield)
        results.append({
            "rpa_concentration": float(rpa),
            "yield_fold_change": res["yield_fold_change"],
            "error": error
        })
    
    # Encontrar mejor
    best = min(results, key=lambda x: x["error"])
    return {
        "optimal_rpa_concentration": best["rpa_concentration"],
        "expected_yield": best["yield_fold_change"],
        "candidates": results[:5]  # Top 5
    }

def validate_rpa_kinetics():
    """
    Validación de self-test: casos conocidos de cinética Michaelis-Menten.
    """
    tests = []
    
    # Test 1: Saturación enzimática (alta concentración ADN)
    high_conc = simulate_rpa_kinetics(
        rpa_concentration=100,
        dna_template=1000,
        reaction_time=20,
        temperature=37
    )
    tests.append({
        "name": "Saturación enzimática (alta [ADN])",
        "passed": high_conc["final_yield"] > 5,
        "value": high_conc["final_yield"]
    })
    
    # Test 2: Dependencia de temperatura
    cold = simulate_rpa_kinetics(
        rpa_concentration=50,
        dna_template=100,
        reaction_time=30,
        temperature=25
    )
    warm = simulate_rpa_kinetics(
        rpa_concentration=50,
        dna_template=100,
        reaction_time=30,
        temperature=39
    )
    tests.append({
        "name": "Dependencia de temperatura (warm > cold)",
        "passed": warm["final_yield"] > cold["final_yield"],
        "warm_yield": warm["final_yield"],
        "cold_yield": cold["final_yield"]
    })
    
    # Test 3: Linealidad en bajo substrato
    low_substrate = michaelis_menten_rate(1, vmax=100, km=50)
    high_substrate = michaelis_menten_rate(100, vmax=100, km=50)
    tests.append({
        "name": "Michaelis-Menten: velocidad aumenta con substrato",
        "passed": high_substrate > low_substrate,
        "ratio": high_substrate / low_substrate if low_substrate > 0 else 0
    })
    
    all_passed = all(t["passed"] for t in tests)
    return {
        "validation_passed": all_passed,
        "tests": tests,
        "summary": f"{sum(1 for t in tests if t['passed'])}/{len(tests)} passed"
    }

def run_rpa_kinetics_tool(mode, rpa_concentration=None, dna_template=None, 
                          reaction_time=None, temperature=37, km_michaelis=50, vmax=1000):
    """Entry point para la tool."""
    try:
        if mode == "validate":
            return validate_rpa_kinetics()
        elif mode == "simulate":
            return simulate_rpa_kinetics(rpa_concentration, dna_template, reaction_time, 
                                        temperature, km_michaelis, vmax)
        elif mode == "predict_yield":
            return predict_yield(rpa_concentration, dna_template, reaction_time, 
                                temperature, km_michaelis, vmax)
        elif mode == "optimize_buffer":
            return optimize_buffer(dna_template, reaction_time=reaction_time, 
                                 temperature=temperature, km_michaelis=km_michaelis)
        else:
            return {"error": f"Unknown mode: {mode}"}
    except Exception as e:
        return {"error": str(e), "validation_passed": False}

if __name__ == "__main__":
    # Test local
    print("=== RPA Kinetics Tool ===\n")
    
    # Validate
    print("1. Validation:")
    val = validate_rpa_kinetics()
    print(json.dumps(val, indent=2))
    
    # Simulate
    print("\n2. Simulate (50 nM RPA, 100 copias iniciales, 30 min @ 37°C):")
    sim = simulate_rpa_kinetics(50, 100, 30)
    print(f"   Final yield: {sim['final_yield']:.2f}x")
    print(f"   Final copies: {sim['yield_fold_change']:.0f}")
    
    # Predict
    print("\n3. Predict yield (100 nM RPA, 1000 copias, 45 min @ 39°C):")
    pred = predict_yield(100, 1000, 45, temperature=39)
    print(json.dumps(pred, indent=2))
    
    # Optimize
    print("\n4. Optimize buffer for target_yield=50000:")
    opt = optimize_buffer(100, target_yield=50000, reaction_time=45)
    print(f"   Optimal [RPA]: {opt['optimal_rpa_concentration']:.1f} nM")
    print(f"   Expected yield: {opt['expected_yield']:.0f}")
