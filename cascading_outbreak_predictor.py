"""cascading_outbreak_predictor.py - Predicción temprana de brotes"""

import numpy as np
import json

TOOL_DESCRIPTION = {
    "name": "cascading_outbreak_predictor",
    "description": "Predice brotes tempranos usando teoría de percolación",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["giant_component_prediction", "propagation_speed", "critical_point_detection", "intervention_timing", "validate"],
                "description": "Modo de predicción"
            },
            "network_size": {"type": "integer"},
            "connectivity": {"type": "number"},
            "infection_rate": {"type": "number"},
            "recovery_rate": {"type": "number"},
            "initial_infected": {"type": "integer"}
        },
        "required": ["mode"]
    }
}

def run(mode, **params):
    if mode == "validate":
        return _validate()
    elif mode == "giant_component_prediction":
        return _giant_component_prediction(params)
    elif mode == "propagation_speed":
        return _propagation_speed(params)
    elif mode == "critical_point_detection":
        return _critical_point_detection(params)
    elif mode == "intervention_timing":
        return _intervention_timing(params)
    else:
        raise ValueError(f"Modo desconocido: {mode}")

def _giant_component_prediction(params):
    n = params.get("network_size", 1000)
    p = params.get("connectivity", 0.003)
    
    avg_degree = (n - 1) * p
    threshold = 1.0
    giant_component_exists = avg_degree > threshold
    
    if giant_component_exists:
        z = avg_degree
        S = 1.0
        for _ in range(10):
            S = 1 - np.exp(-z * S)
        giant_component_fraction = float(S)
    else:
        giant_component_fraction = 0.0
    
    return {
        "giant_component_exists": bool(giant_component_exists),
        "giant_component_fraction": giant_component_fraction,
        "avg_degree": float(avg_degree),
        "threshold": threshold,
        "network_size": n,
        "connectivity": p
    }

def _propagation_speed(params):
    n = params.get("network_size", 1000)
    p = params.get("connectivity", 0.003)
    beta = params.get("infection_rate", 0.4)
    gamma = params.get("recovery_rate", 0.1)
    initial = params.get("initial_infected", 10)
    
    R0 = beta / gamma
    avg_degree = (n - 1) * p
    D = avg_degree
    
    if R0 > 1:
        propagation_speed = float(np.sqrt(2 * D * (R0 - 1)))
    else:
        propagation_speed = 0.0
    
    if R0 > 1:
        doubling_time = float(np.log(2) / (beta - gamma))
    else:
        doubling_time = float('inf')
    
    return {
        "R0": float(R0),
        "propagation_speed": propagation_speed,
        "doubling_time": doubling_time if doubling_time != float('inf') else -1,
        "epidemic_possible": bool(R0 > 1),
        "initial_infected": initial,
        "network_size": n
    }

def _critical_point_detection(params):
    n = params.get("network_size", 1000)
    
    connectivities = np.linspace(0.0001, 0.01, 100)
    giant_fractions = []
    
    for p in connectivities:
        avg_degree = (n - 1) * p
        threshold = 1.0
        
        if avg_degree > threshold:
            z = avg_degree
            S = 1.0
            for _ in range(10):
                S = 1 - np.exp(-z * S)
            giant_fractions.append(S)
        else:
            giant_fractions.append(0.0)
    
    giant_fractions = np.array(giant_fractions)
    critical_idx = np.argmax(np.abs(np.diff(giant_fractions)))
    critical_connectivity = float(connectivities[critical_idx])
    critical_avg_degree = (n - 1) * critical_connectivity
    transition_sharpness = float(giant_fractions[critical_idx + 1] - giant_fractions[critical_idx])
    
    return {
        "critical_connectivity": critical_connectivity,
        "critical_avg_degree": critical_avg_degree,
        "transition_sharpness": transition_sharpness,
        "network_size": n,
        "theoretical_threshold": 1.0
    }

def _intervention_timing(params):
    beta = params.get("infection_rate", 0.4)
    gamma = params.get("recovery_rate", 0.1)
    
    R0 = beta / gamma
    
    if R0 <= 1:
        return {
            "intervention_needed": False,
            "optimal_timing": -1,
            "reason": "R0 <= 1: brote no sostenible",
            "R0": float(R0)
        }
    
    t_peak = np.log(R0) / (beta - gamma)
    optimal_intervention_time = float(t_peak / 3)
    R0_after = R0 * 0.7
    
    return {
        "intervention_needed": True,
        "R0_before": float(R0),
        "R0_after_intervention": float(R0_after),
        "optimal_timing": optimal_intervention_time,
        "peak_time": float(t_peak),
        "intervention_window_days": float(t_peak / 2)
    }

def _validate():
    checks = {
        "giant_component_high_p": _giant_component_prediction({"network_size": 1000, "connectivity": 0.01})["giant_component_exists"],
        "giant_component_low_p": not _giant_component_prediction({"network_size": 1000, "connectivity": 0.0001})["giant_component_exists"],
        "propagation_speed_positive": _propagation_speed({"infection_rate": 0.4, "recovery_rate": 0.1})["propagation_speed"] > 0,
        "critical_point_detected": _critical_point_detection({"network_size": 1000})["critical_connectivity"] > 0,
        "intervention_timing_valid": _intervention_timing({"infection_rate": 0.4, "recovery_rate": 0.1})["optimal_timing"] > 0
    }
    all_passed = all(checks.values())
    return {"validation_passed": all_passed, "checks": checks, "passed": sum(checks.values()), "total": len(checks)}

try:
    from tool_registry import register_tool
    register_tool(
        name="cascading_outbreak_predictor",
        schema=TOOL_DESCRIPTION,
        handler=lambda args: run(args.get("mode"), **{k: v for k, v in args.items() if k != "mode"})
    )
except ImportError:
    pass

if __name__ == "__main__":
    print(json.dumps(_validate(), indent=2))
