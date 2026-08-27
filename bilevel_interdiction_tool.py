"""bilevel_interdiction_tool.py - Optimización atacante vs defensor"""

import numpy as np
import json

TOOL_DESCRIPTION = {
    "name": "bilevel_interdiction_tool",
    "description": "Optimiza estrategias de defensa en infraestructuras interdependientes",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["attacker_vs_defender", "interdependent_infrastructure", "optimal_defense_strategy", "defense_cost_benefit", "validate"],
                "description": "Modo de análisis"
            },
            "n_nodes": {"type": "integer"},
            "n_systems": {"type": "integer"},
            "attack_budget": {"type": "number"},
            "defense_budget": {"type": "number"},
            "interdependence_strength": {"type": "number"}
        },
        "required": ["mode"]
    }
}

def run(mode, **params):
    if mode == "validate":
        return _validate()
    elif mode == "attacker_vs_defender":
        return _attacker_vs_defender(params)
    elif mode == "interdependent_infrastructure":
        return _interdependent_infrastructure(params)
    elif mode == "optimal_defense_strategy":
        return _optimal_defense_strategy(params)
    elif mode == "defense_cost_benefit":
        return _defense_cost_benefit(params)
    else:
        raise ValueError(f"Modo desconocido: {mode}")

def _attacker_vs_defender(params):
    n_nodes = params.get("n_nodes", 100)
    attack_budget = params.get("attack_budget", 10)
    defense_budget = params.get("defense_budget", 5)
    
    np.random.seed(42)
    importance = np.random.rand(n_nodes) * 100
    
    defended = np.argsort(importance)[-defense_budget:] if defense_budget > 0 else np.array([], dtype=int)
    defended_mask = np.zeros(n_nodes, dtype=bool)
    defended_mask[defended] = True
    
    undefended_importance = importance.copy()
    undefended_importance[defended] = -1
    
    attacked = np.argsort(undefended_importance)[-attack_budget:]
    attacked_mask = np.zeros(n_nodes, dtype=bool)
    attacked_mask[attacked] = True
    
    connectivity = np.random.rand(n_nodes, n_nodes) < 0.05
    np.fill_diagonal(connectivity, 0)
    
    failed = attacked_mask.copy()
    
    for _ in range(10):
        new_failed = failed.copy()
        for i in range(n_nodes):
            if not failed[i] and not defended_mask[i]:
                neighbors_failed = np.sum(failed[connectivity[i]])
                total_neighbors = np.sum(connectivity[i])
                if total_neighbors > 0 and neighbors_failed / total_neighbors > 0.3:
                    new_failed[i] = True
        failed = new_failed
    
    total_damage = np.sum(failed)
    damage_fraction = total_damage / n_nodes
    
    return {
        "total_damage": int(total_damage),
        "damage_fraction": float(damage_fraction),
        "directly_attacked": int(np.sum(attacked_mask)),
        "cascading_failures": int(total_damage - np.sum(attacked_mask)),
        "defended_nodes": int(np.sum(defended_mask)),
        "attack_budget": int(attack_budget),
        "defense_budget": int(defense_budget)
    }

def _interdependent_infrastructure(params):
    n_nodes = params.get("n_nodes", 100)
    n_systems = params.get("n_systems", 3)
    interdependence = params.get("interdependence_strength", 0.3)
    
    np.random.seed(42)
    nodes_per_system = n_nodes // n_systems
    
    system_connectivity = [np.random.rand(nodes_per_system, nodes_per_system) < 0.05 
                          for _ in range(n_systems)]
    
    interdependence_matrix = np.random.rand(n_systems, n_systems) < interdependence
    np.fill_diagonal(interdependence_matrix, 0)
    
    failed = [np.zeros(nodes_per_system, dtype=bool) for _ in range(n_systems)]
    failed[0][0:3] = True
    
    for iteration in range(5):
        new_failed = [f.copy() for f in failed]
        
        for sys in range(n_systems):
            for i in range(nodes_per_system):
                if not failed[sys][i]:
                    neighbors_failed = np.sum(failed[sys][system_connectivity[sys][i]])
                    total_neighbors = np.sum(system_connectivity[sys][i])
                    if total_neighbors > 0 and neighbors_failed / total_neighbors > 0.3:
                        new_failed[sys][i] = True
        
        for sys_i in range(n_systems):
            for sys_j in range(n_systems):
                if interdependence_matrix[sys_i, sys_j] and np.sum(failed[sys_i]) > 0:
                    fraction_failed_i = np.sum(failed[sys_i]) / nodes_per_system
                    n_fail_j = int(fraction_failed_i * nodes_per_system * 0.2)
                    if n_fail_j > 0:
                        fail_indices = np.random.choice(nodes_per_system, min(n_fail_j, nodes_per_system), replace=False)
                        new_failed[sys_j][fail_indices] = True
        
        failed = new_failed
    
    total_failed = sum([np.sum(f) for f in failed])
    total_damaged_fraction = total_failed / n_nodes
    damage_by_system = [float(np.sum(f) / nodes_per_system) for f in failed]
    
    return {
        "total_damaged_fraction": float(total_damaged_fraction),
        "damage_by_system": damage_by_system,
        "n_systems": n_systems,
        "total_nodes": n_nodes,
        "interdependence_strength": interdependence,
        "critical_interdependence": total_damaged_fraction > 0.5
    }

def _optimal_defense_strategy(params):
    n_nodes = params.get("n_nodes", 100)
    defense_budget = params.get("defense_budget", 10)
    attack_budget = params.get("attack_budget", 15)
    
    np.random.seed(42)
    connectivity = np.random.rand(n_nodes, n_nodes) < 0.05
    np.fill_diagonal(connectivity, 0)
    degree = np.sum(connectivity, axis=1)
    
    strategy_centrality = np.argsort(degree)[-defense_budget:] if defense_budget > 0 else np.array([], dtype=int)
    strategy_random = np.random.choice(n_nodes, defense_budget, replace=False)
    
    betweenness = np.zeros(n_nodes)
    for i in range(n_nodes):
        for j in range(i+1, n_nodes):
            if connectivity[i, j]:
                betweenness[i] += 1
    
    strategy_bridges = np.argsort(betweenness)[-defense_budget:] if defense_budget > 0 else np.array([], dtype=int)
    
    def evaluate_defense(defended_nodes):
        attacked = np.random.choice([i for i in range(n_nodes) if i not in defended_nodes], 
                                   min(attack_budget, n_nodes - len(defended_nodes)), 
                                   replace=False)
        failed = np.zeros(n_nodes, dtype=bool)
        failed[attacked] = True
        
        for _ in range(10):
            new_failed = failed.copy()
            for i in range(n_nodes):
                if not failed[i]:
                    neighbors_failed = np.sum(failed[connectivity[i]])
                    total_neighbors = np.sum(connectivity[i])
                    if total_neighbors > 0 and neighbors_failed / total_neighbors > 0.3:
                        new_failed[i] = True
            failed = new_failed
        
        return np.sum(failed) / n_nodes
    
    effectiveness_centrality = evaluate_defense(strategy_centrality)
    effectiveness_bridges = evaluate_defense(strategy_bridges)
    
    best_strategy_name = "centrality" if effectiveness_centrality < effectiveness_bridges else "bridges"
    
    return {
        "best_strategy": best_strategy_name,
        "effectiveness_centrality": float(effectiveness_centrality),
        "effectiveness_bridges": float(effectiveness_bridges),
        "defense_budget": defense_budget,
        "attack_budget": attack_budget,
        "recommended_nodes": strategy_centrality.tolist() if best_strategy_name == "centrality" else strategy_bridges.tolist()
    }

def _defense_cost_benefit(params):
    n_nodes = params.get("n_nodes", 100)
    attack_budget = params.get("attack_budget", 15)
    
    np.random.seed(42)
    connectivity = np.random.rand(n_nodes, n_nodes) < 0.05
    np.fill_diagonal(connectivity, 0)
    
    defense_budgets = range(0, max(n_nodes // 4, 1), max(2, 1) if n_nodes // 4 > 1 else 1)
    damages = []
    
    for defense_budget in defense_budgets:
        degree = np.sum(connectivity, axis=1)
        defended = np.argsort(degree)[-defense_budget:] if defense_budget > 0 else []
        
        undefended_importance = degree.copy()
        undefended_importance[defended] = -1
        attacked = np.argsort(undefended_importance)[-attack_budget:]
        
        failed = np.zeros(n_nodes, dtype=bool)
        failed[attacked] = True
        
        for _ in range(10):
            new_failed = failed.copy()
            for i in range(n_nodes):
                if not failed[i]:
                    neighbors_failed = np.sum(failed[connectivity[i]])
                    total_neighbors = np.sum(connectivity[i])
                    if total_neighbors > 0 and neighbors_failed / total_neighbors > 0.3:
                        new_failed[i] = True
            failed = new_failed
        
        damages.append(np.sum(failed) / n_nodes)
    
    defense_costs = [b * 100 for b in defense_budgets]
    benefits = [max(0, (damages[0] - damages[i]) * 1000) for i in range(len(damages))]
    roi = [benefits[i] / max(1, defense_costs[i]) if defense_costs[i] > 0 else 0 for i in range(len(defense_costs))]
    
    if roi and max(roi) > 0:
        optimal_idx = np.argmax(roi)
        optimal_budget = defense_budgets[optimal_idx]
    else:
        optimal_budget = 0
    
    return {
        "optimal_defense_budget": int(optimal_budget),
        "defense_costs": defense_costs,
        "damages": damages,
        "roi_values": roi,
        "max_roi": float(max(roi)) if roi else 0,
        "infrastructure_value": 1000
    }

def _validate():
    checks = {
        "attacker_vs_defender_runs": "total_damage" in _attacker_vs_defender({"n_nodes": 50}),
        "defense_reduces_damage": _attacker_vs_defender({"n_nodes": 50, "defense_budget": 10})["total_damage"] < 
                                  _attacker_vs_defender({"n_nodes": 50, "defense_budget": 0})["total_damage"],
        "interdependent_infrastructure_runs": "total_damaged_fraction" in _interdependent_infrastructure({"n_nodes": 100, "n_systems": 3}),
        "optimal_defense_runs": "best_strategy" in _optimal_defense_strategy({"n_nodes": 50}),
        "cost_benefit_analysis_runs": "optimal_defense_budget" in _defense_cost_benefit({"n_nodes": 50})
    }
    all_passed = all(checks.values())
    return {"validation_passed": all_passed, "checks": checks, "passed": sum(checks.values()), "total": len(checks)}

try:
    from tool_registry import register_tool
    register_tool(
        name="bilevel_interdiction_tool",
        schema=TOOL_DESCRIPTION,
        handler=lambda args: run(args.get("mode"), **{k: v for k, v in args.items() if k != "mode"})
    )
except ImportError:
    pass

if __name__ == "__main__":
    print(json.dumps(_validate(), indent=2))
