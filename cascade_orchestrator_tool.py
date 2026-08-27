"""cascade_orchestrator_tool.py - Meta-orquestador transversal"""

import numpy as np
import json

TOOL_DESCRIPTION = {
    "name": "cascade_orchestrator_tool",
    "description": "Orquestador transversal que conecta cascadas entre múltiples dominios",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["orchestrate", "analyze_connections", "detect_critical_nodes", "validate"],
                "description": "Modo de operación"
            },
            "n_domains": {"type": "integer"},
            "cascade_coupling": {"type": "number"},
            "propagation_threshold": {"type": "number"},
            "initial_cascade_size": {"type": "number"}
        },
        "required": ["mode"]
    }
}

def run(mode, **params):
    if mode == "validate":
        return _validate()
    elif mode == "orchestrate":
        return _orchestrate(params)
    elif mode == "analyze_connections":
        return _analyze_connections(params)
    elif mode == "detect_critical_nodes":
        return _detect_critical_nodes(params)
    else:
        raise ValueError(f"Modo desconocido: {mode}")

def _orchestrate(params):
    n_domains = params.get("n_domains", 5)
    cascade_coupling = params.get("cascade_coupling", 0.2)
    threshold = params.get("propagation_threshold", 0.3)
    initial_size = params.get("initial_cascade_size", 0.35)
    
    np.random.seed(42)
    coupling_matrix = np.random.rand(n_domains, n_domains) < cascade_coupling
    coupling_matrix = coupling_matrix.astype(float)
    np.fill_diagonal(coupling_matrix, 0)
    
    cascade_state = np.zeros(n_domains)
    cascade_state[0] = initial_size
    cascade_history = [cascade_state.copy()]
    
    for step in range(20):
        new_state = cascade_state.copy()
        for i in range(n_domains):
            if cascade_state[i] > threshold:
                for j in range(n_domains):
                    if coupling_matrix[i, j] > 0:
                        influence = cascade_state[i] * coupling_matrix[i, j]
                        new_state[j] = min(1.0, new_state[j] + influence * 0.1)
        cascade_state = new_state
        cascade_history.append(cascade_state.copy())
    
    max_spread = float(np.max([np.sum(s) for s in cascade_history]))
    final_affected = int(np.sum(cascade_state > threshold))
    
    return {
        "orchestration_complete": True,
        "n_domains": n_domains,
        "final_cascade_state": cascade_state.tolist(),
        "max_global_spread": max_spread,
        "affected_domains": final_affected,
        "cascade_propagation_steps": len(cascade_history)
    }

def _analyze_connections(params):
    n_domains = params.get("n_domains", 5)
    cascade_coupling = params.get("cascade_coupling", 0.2)
    
    np.random.seed(42)
    coupling_matrix = np.random.rand(n_domains, n_domains) < cascade_coupling
    coupling_matrix = coupling_matrix.astype(float)
    np.fill_diagonal(coupling_matrix, 0)
    
    in_degree = np.sum(coupling_matrix, axis=0)
    out_degree = np.sum(coupling_matrix, axis=1)
    total_degree = in_degree + out_degree
    
    connectivity = float(np.sum(coupling_matrix) / (n_domains * (n_domains - 1)))
    n_connections = int(np.sum(coupling_matrix))
    
    return {
        "n_domains": n_domains,
        "connectivity": connectivity,
        "n_connections": n_connections,
        "avg_degree": float(np.mean(total_degree)),
        "most_connected_domain": int(np.argmax(total_degree)),
        "domain_degrees": total_degree.tolist()
    }

def _detect_critical_nodes(params):
    n_domains = params.get("n_domains", 5)
    cascade_coupling = params.get("cascade_coupling", 0.2)
    
    np.random.seed(42)
    coupling_matrix = np.random.rand(n_domains, n_domains) < cascade_coupling
    coupling_matrix = coupling_matrix.astype(float)
    np.fill_diagonal(coupling_matrix, 0)
    
    criticality = np.zeros(n_domains)
    for i in range(n_domains):
        reachable = np.sum(coupling_matrix[i] > 0)
        can_reach = np.sum(coupling_matrix[:, i] > 0)
        criticality[i] = (reachable + can_reach) * coupling_matrix[i].sum()
    
    critical_nodes = np.where(criticality > np.percentile(criticality, 75))[0].tolist()
    
    return {
        "critical_nodes": critical_nodes,
        "criticality_scores": criticality.tolist(),
        "n_critical": len(critical_nodes),
        "max_criticality": float(np.max(criticality)),
        "avg_criticality": float(np.mean(criticality))
    }

def _validate():
    checks = {
        "orchestrate_runs": "final_cascade_state" in _orchestrate({"n_domains": 5}),
        "orchestrate_propagates": _orchestrate({"n_domains": 5, "cascade_coupling": 0.5, "initial_cascade_size": 0.5})["affected_domains"] > 1,
        "analyze_connections_runs": "connectivity" in _analyze_connections({"n_domains": 5}),
        "detect_critical_nodes_runs": "critical_nodes" in _detect_critical_nodes({"n_domains": 5}),
        "critical_nodes_found": len(_detect_critical_nodes({"n_domains": 5, "cascade_coupling": 0.5})["critical_nodes"]) > 0
    }
    all_passed = all(checks.values())
    return {"validation_passed": all_passed, "checks": checks, "passed": sum(checks.values()), "total": len(checks)}

try:
    from tool_registry import register_tool
    register_tool(
        name="cascade_orchestrator_tool",
        schema=TOOL_DESCRIPTION,
        handler=lambda args: run(args.get("mode"), **{k: v for k, v in args.items() if k != "mode"})
    )
except ImportError:
    pass

if __name__ == "__main__":
    print(json.dumps(_validate(), indent=2))
