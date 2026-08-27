"""information_cascade_tool.py - Propagación de información en redes sociales"""

import numpy as np
import json

TOOL_DESCRIPTION = {
    "name": "information_cascade_tool",
    "description": "Modela propagación de información en redes sociales",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["informational_cascade", "bandwagon_effect", "rumor_propagation", "influencer_impact", "validate"],
                "description": "Modo de propagación"
            },
            "network_size": {"type": "integer"},
            "connectivity": {"type": "number"},
            "initial_adopters": {"type": "integer"},
            "conformity_bias": {"type": "number"},
            "rumor_decay": {"type": "number"},
            "n_influencers": {"type": "integer"},
            "influencer_reach": {"type": "number"}
        },
        "required": ["mode"]
    }
}

def run(mode, **params):
    if mode == "validate":
        return _validate()
    elif mode == "informational_cascade":
        return _informational_cascade(params)
    elif mode == "bandwagon_effect":
        return _bandwagon_effect(params)
    elif mode == "rumor_propagation":
        return _rumor_propagation(params)
    elif mode == "influencer_impact":
        return _influencer_impact(params)
    else:
        raise ValueError(f"Modo desconocido: {mode}")

def _informational_cascade(params):
    n = params.get("network_size", 1000)
    p = params.get("connectivity", 0.003)
    initial = params.get("initial_adopters", 10)
    conformity = params.get("conformity_bias", 0.6)
    
    np.random.seed(42)
    connections = np.random.rand(n, n) < p
    np.fill_diagonal(connections, 0)
    
    state = np.zeros(n)
    state[:initial] = 1
    adoption_history = [int(np.sum(state))]
    
    for step in range(50):
        new_state = state.copy()
        for i in range(n):
            if state[i] == 0:
                neighbors = connections[i] > 0
                n_neighbors = np.sum(neighbors)
                if n_neighbors > 0:
                    fraction_adopted = np.sum(state[neighbors]) / n_neighbors
                    adopt_prob = conformity * fraction_adopted
                    if np.random.rand() < adopt_prob:
                        new_state[i] = 1
        state = new_state
        adoption_history.append(int(np.sum(state)))
        if np.sum(state) > 0.95 * n:
            break
    
    adoption_fraction = np.sum(state) / n
    return {
        "total_adoption": int(np.sum(state)),
        "adoption_fraction": float(adoption_fraction),
        "adoption_steps": len(adoption_history),
        "network_size": n,
        "conformity_bias": conformity,
        "cascade_saturation": float(adoption_fraction) > 0.5
    }

def _bandwagon_effect(params):
    n = params.get("network_size", 1000)
    p = params.get("connectivity", 0.005)
    initial = params.get("initial_adopters", 20)
    conformity = params.get("conformity_bias", 0.8)
    
    np.random.seed(42)
    connections = np.random.rand(n, n) < p
    np.fill_diagonal(connections, 0)
    
    state = np.zeros(n)
    state[:initial] = 1
    momentum_history = [int(np.sum(state))]
    
    for step in range(100):
        new_state = state.copy()
        current_adopters = np.sum(state)
        current_acceleration = 1.0 + 0.5 * (current_adopters / n)
        
        for i in range(n):
            if state[i] == 0:
                neighbors = connections[i] > 0
                n_neighbors = np.sum(neighbors)
                if n_neighbors > 0:
                    fraction_adopted = np.sum(state[neighbors]) / n_neighbors
                    adopt_prob = min(1.0, conformity * fraction_adopted * current_acceleration)
                    if np.random.rand() < adopt_prob:
                        new_state[i] = 1
        
        state = new_state
        momentum_history.append(int(np.sum(state)))
        if np.sum(state) > 0.95 * n:
            break
    
    adoption_fraction = np.sum(state) / n
    time_to_saturation = len(momentum_history)
    
    return {
        "bandwagon_adoption": float(adoption_fraction),
        "time_to_saturation": time_to_saturation,
        "network_size": n,
        "conformity_strength": conformity,
        "bandwagon_effect_present": time_to_saturation < 30
    }

def _rumor_propagation(params):
    n = params.get("network_size", 1000)
    p = params.get("connectivity", 0.004)
    initial = params.get("initial_adopters", 5)
    decay = params.get("rumor_decay", 0.1)
    
    np.random.seed(42)
    connections = np.random.rand(n, n) < p
    np.fill_diagonal(connections, 0)
    
    state = np.zeros(n)
    state[:initial] = 1.0
    rumor_intensity = [float(np.sum(state))]
    
    for step in range(100):
        new_state = state.copy()
        for i in range(n):
            if state[i] > 0:
                new_state[i] = state[i] * (1 - decay)
            else:
                neighbors = connections[i] > 0
                n_neighbors = np.sum(neighbors)
                if n_neighbors > 0:
                    max_neighbor_intensity = np.max(state[neighbors])
                    learn_prob = 0.3 * max_neighbor_intensity
                    if np.random.rand() < learn_prob:
                        new_state[i] = 0.5
        state = new_state
        rumor_intensity.append(float(np.sum(state)))
        if np.max(state) < 0.01:
            break
    
    peak_intensity = max(rumor_intensity)
    lifespan = len(rumor_intensity)
    
    return {
        "peak_intensity": float(peak_intensity),
        "rumor_lifespan": lifespan,
        "final_intensity": float(np.sum(state)),
        "network_size": n,
        "decay_rate": decay,
        "rumor_extinction": float(np.sum(state)) < 0.1
    }

def _influencer_impact(params):
    n = params.get("network_size", 1000)
    n_influencers = params.get("n_influencers", 5)
    reach = params.get("influencer_reach", 0.1)
    
    np.random.seed(42)
    degrees = np.random.binomial(30, 0.1, n)
    influencer_indices = np.argsort(degrees)[-n_influencers:] if n_influencers > 0 else np.array([], dtype=int)
    
    p = 0.003
    connections = np.random.rand(n, n) < p
    np.fill_diagonal(connections, 0)
    
    direct_reach = int(reach * n)
    state = np.zeros(n)
    state[influencer_indices] = 1
    
    for step in range(40):
        new_state = state.copy()
        for inf_idx in influencer_indices:
            reachable = np.random.choice(n, min(direct_reach, n), replace=False)
            new_state[reachable] = 1
        for i in range(n):
            if state[i] == 0:
                neighbors = connections[i] > 0
                if np.sum(neighbors) > 0:
                    if np.sum(state[neighbors]) > 0:
                        if np.random.rand() < 0.2:
                            new_state[i] = 1
        state = new_state
        if np.sum(state) > 0.9 * n:
            break
    
    adoption_with_influencers = np.sum(state) / n
    
    state_without = np.zeros(n)
    state_without[:int(n_influencers * reach)] = 1
    for _ in range(40):
        for i in range(n):
            if state_without[i] == 0:
                neighbors = connections[i] > 0
                if np.sum(neighbors) > 0:
                    if np.sum(state_without[neighbors]) > 0:
                        if np.random.rand() < 0.2:
                            state_without[i] = 1
    
    adoption_without = np.sum(state_without) / n
    influencer_boost = adoption_with_influencers - adoption_without
    
    return {
        "adoption_with_influencers": float(adoption_with_influencers),
        "adoption_without_influencers": float(adoption_without),
        "influencer_boost": float(influencer_boost),
        "n_influencers": n_influencers,
        "influencer_reach": reach,
        "network_size": n
    }

def _validate():
    checks = {
        "informational_cascade_runs": "adoption_fraction" in _informational_cascade({"network_size": 500}),
        "cascade_reaches_saturation": _informational_cascade({"network_size": 500, "conformity_bias": 0.9})["cascade_saturation"],
        "bandwagon_faster": _bandwagon_effect({"network_size": 500, "conformity_bias": 0.9, "connectivity": 0.02})["time_to_saturation"] < 50,
        "rumor_propagates": _rumor_propagation({"network_size": 500})["peak_intensity"] > 0,
        "influencer_boost_positive": _influencer_impact({"network_size": 500, "n_influencers": 3})["influencer_boost"] > 0
    }
    all_passed = all(checks.values())
    return {"validation_passed": all_passed, "checks": checks, "passed": sum(checks.values()), "total": len(checks)}

try:
    from tool_registry import register_tool
    register_tool(
        name="information_cascade_tool",
        schema=TOOL_DESCRIPTION,
        handler=lambda args: run(args.get("mode"), **{k: v for k, v in args.items() if k != "mode"})
    )
except ImportError:
    pass

if __name__ == "__main__":
    print(json.dumps(_validate(), indent=2))
