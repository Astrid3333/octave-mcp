"""
domino_effect_tool.py - Cascadas matemáticas fundamentales
Modos: coupled_ode, percolation, sir_cascade, cusp_catastrophe, reaction_diffusion, validate
"""

import numpy as np
from scipy.integrate import odeint
import json

TOOL_DESCRIPTION = {
    "name": "domino_effect_tool",
    "description": "Modela cascadas matemáticas fundamentales",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["coupled_ode", "percolation", "sir_cascade", "cusp_catastrophe", "reaction_diffusion", "validate"],
                "description": "Modo de simulación"
            },
            "n_nodes": {"type": "integer"},
            "coupling_strength": {"type": "number"},
            "threshold": {"type": "number"},
            "beta": {"type": "number"},
            "gamma": {"type": "number"},
            "a": {"type": "number"},
            "b": {"type": "number"},
            "D": {"type": "number"},
            "r": {"type": "number"},
            "shock_magnitude": {"type": "number"},
            "n_shocked": {"type": "integer"}
        },
        "required": ["mode"]
    }
}

def run(mode, **params):
    if mode == "validate":
        return _validate()
    elif mode == "coupled_ode":
        return _coupled_ode(params)
    elif mode == "percolation":
        return _percolation(params)
    elif mode == "sir_cascade":
        return _sir_cascade(params)
    elif mode == "cusp_catastrophe":
        return _cusp_catastrophe(params)
    elif mode == "reaction_diffusion":
        return _reaction_diffusion(params)
    else:
        raise ValueError(f"Modo desconocido: {mode}")

def _coupled_ode(params):
    n_nodes = params.get("n_nodes", 10)
    coupling_strength = params.get("coupling_strength", 0.1)
    threshold = params.get("threshold", 0.5)
    time_steps = params.get("time_steps", 100)
    
    np.random.seed(42)
    adjacency = np.random.rand(n_nodes, n_nodes) < 0.3
    adjacency = adjacency.astype(float)
    adjacency = adjacency / (adjacency.sum(axis=1, keepdims=True) + 1e-8)
    
    initial = np.random.rand(n_nodes) * 0.2
    shock_magnitude = params.get("shock_magnitude", 0.0)
    n_shocked = params.get("n_shocked", 1 if shock_magnitude > 0 else 0)
    if shock_magnitude > 0 and n_shocked > 0:
        idx = np.arange(min(n_shocked, n_nodes))
        initial[idx] = np.clip(initial[idx] + shock_magnitude, 0, 1)
    
    # Integración explícita (Euler) con clip post-paso a [0, 1].
    # Se evita odeint/LSODA porque un clamp de derivada introduce una
    # discontinuidad que el solver adaptativo no maneja de forma estable.
    dt = 10.0 / time_steps
    x = initial.copy()
    trajectory = [x.copy()]
    for _ in range(time_steps - 1):
        dx = np.zeros_like(x)
        for i in range(n_nodes):
            f = x[i] * (1 - x[i]) - threshold
            influence = coupling_strength * np.sum(adjacency[i] * np.tanh(x - x[i]))
            dx[i] = f + influence
        x = x + dt * dx
        x = np.clip(x, 0.0, 1.0)
        trajectory.append(x.copy())
    solution = np.array(trajectory)
    
    fraction_high = float(np.mean(solution[-1] > 0.8))
    initial_shocked_fraction = n_shocked / n_nodes if n_nodes > 0 else 0
    # cascada = contagio real: la fracción final de nodos "altos" supera
    # claramente la fracción que fue shockeada directamente
    cascade = bool(fraction_high > max(2 * initial_shocked_fraction, 0.5))
    return {
        "cascade_detected": cascade,
        "max_state": float(np.max(solution[-1])),
        "fraction_high": fraction_high,
        "initial_shocked_fraction": initial_shocked_fraction,
        "n_nodes": n_nodes
    }

def _percolation(params):
    n_nodes = params.get("n_nodes", 100)
    threshold_mean = params.get("threshold_mean", 0.5)
    initial_failures = params.get("initial_failures", 5)
    
    np.random.seed(42)
    adjacency = np.random.rand(n_nodes, n_nodes) < 0.1
    adjacency = adjacency.astype(float)
    np.fill_diagonal(adjacency, 0)
    
    thresholds = np.random.normal(threshold_mean, 0.1, n_nodes)
    thresholds = np.clip(thresholds, 0.1, 0.9)
    
    failed = np.zeros(n_nodes, dtype=bool)
    initial_idx = np.random.choice(n_nodes, min(initial_failures, n_nodes), replace=False)
    failed[initial_idx] = True
    
    cascade_size = [int(np.sum(failed))]
    iteration = 0
    
    while iteration < 100:
        new_failures = False
        for i in range(n_nodes):
            if not failed[i]:
                neighbors = adjacency[i] > 0
                if np.sum(neighbors) > 0:
                    failed_neighbors = np.sum(failed[neighbors])
                    fraction = failed_neighbors / np.sum(neighbors)
                    if fraction > thresholds[i]:
                        failed[i] = True
                        new_failures = True
        if not new_failures:
            break
        cascade_size.append(int(np.sum(failed)))
        iteration += 1
    
    global_cascade = np.sum(failed) > 0.5 * n_nodes
    return {"cascade_size": cascade_size, "iterations": iteration, "global_cascade": bool(global_cascade), "final_failures": int(np.sum(failed))}

def _sir_cascade(params):
    beta = params.get("beta", 0.3)
    gamma = params.get("gamma", 0.1)
    initial_infected = params.get("initial_infected", 0.01)
    time_steps = params.get("time_steps", 100)
    
    def sir(y, t, b, g):
        S, I, R = y
        dSdt = -b * S * I
        dIdt = b * S * I - g * I
        dRdt = g * I
        return [dSdt, dIdt, dRdt]
    
    y0 = [1 - initial_infected, initial_infected, 0]
    t = np.linspace(0, 100, time_steps)
    solution = odeint(sir, y0, t, args=(beta, gamma))
    
    I = solution[:, 1]
    peak_infected = float(np.max(I))
    cascade = peak_infected > 0.3
    
    return {"peak_infected": peak_infected, "cascade_detected": bool(cascade), "beta": beta, "gamma": gamma}

def _cusp_catastrophe(params):
    a = params.get("a", 0.5)
    b = params.get("b", 0.0)
    x_range = params.get("x_range", 10)
    
    x = np.linspace(-x_range, x_range, 1000)
    V = x**4/4 + a*x**2/2 + b*x
    
    equilibria = []
    for x0 in np.linspace(-3, 3, 10):
        x_guess = x0
        for _ in range(20):
            f = x_guess**3 + a*x_guess + b
            df = 3*x_guess**2 + a
            if abs(df) < 1e-8:
                break
            x_guess = x_guess - f / df
        if -x_range < x_guess < x_range:
            equilibria.append(round(float(x_guess), 3))
    
    equilibria = sorted(list(set(equilibria)))
    catastrophe_possible = len(equilibria) == 3
    
    return {"equilibria": equilibria, "catastrophe_possible": bool(catastrophe_possible), "n_equilibria": len(equilibria)}

def _reaction_diffusion(params):
    nx = params.get("nx", 100)
    nt = params.get("nt", 50)
    D = params.get("D", 0.1)
    r = params.get("r", 0.5)
    
    x = np.linspace(-10, 10, nx)
    u = np.exp(-x**2)
    
    u_history = [u.copy()]
    for _ in range(nt):
        u_new = u.copy()
        for i in range(1, nx-1):
            u_new[i] = u[i] + D * (u[i-1] - 2*u[i] + u[i+1]) + r * u[i] * (1 - u[i])
        u_new[0] = u_new[1]
        u_new[-1] = u_new[-2]
        u = u_new.copy()
        u_history.append(u.copy())
    
    return {"max_amplitude": float(max([np.max(u) for u in u_history])), "n_x": nx, "n_t": nt}

def _validate():
    checks = {
        "coupled_ode_no_cascade": not _coupled_ode({"coupling_strength": 0.0, "n_nodes": 10, "threshold": 0.15, "shock_magnitude": 0.5, "n_shocked": 4})["cascade_detected"],
        "coupled_ode_cascade": _coupled_ode({"coupling_strength": 0.8, "n_nodes": 10, "threshold": 0.15, "shock_magnitude": 0.5, "n_shocked": 4})["cascade_detected"],
        "percolation_runs": _percolation({"initial_failures": 5})["final_failures"] >= 5,
        "sir_has_peak": _sir_cascade({"beta": 0.3, "gamma": 0.1})["peak_infected"] > 0.1,
        "cusp_equilibria": len(_cusp_catastrophe({"a": 0.5, "b": 0.0})["equilibria"]) > 0,
        "reaction_diffusion_runs": _reaction_diffusion({"nx": 50, "nt": 20})["max_amplitude"] > 0
    }
    all_passed = all(checks.values())
    return {"validation_passed": all_passed, "checks": checks, "passed": sum(checks.values()), "total": len(checks)}

try:
    from tool_registry import register_tool
    register_tool(
        name="domino_effect_tool",
        schema=TOOL_DESCRIPTION,
        handler=lambda args: run(args.get("mode"), **{k: v for k, v in args.items() if k != "mode"})
    )
except ImportError:
    pass

if __name__ == "__main__":
    print(json.dumps(_validate(), indent=2))
