#!/usr/bin/env python3
"""
stochastic_processes_tool.py
Procesos estocasticos: movimiento browniano (estandar, con drift, geometrico),
proceso de Ornstein-Uhlenbeck (reversion a la media, relevante para modelar
variables ambientales fluctuantes con equilibrio, ej. temperatura/humedad en
bioreactores), y cadenas de Markov discretas (distribucion estacionaria,
tiempos de primer paso, clasificacion de estados).
"""
import numpy as np


def compute_brownian_motion(T=1.0, n_steps=1000, n_paths=100, mu=0.0, sigma=1.0,
                             kind="standard", x0=1.0, seed=None):
    """
    kind='standard': dX = sigma*dW (o mu*dt + sigma*dW si mu!=0).
    kind='geometric': dX = mu*X*dt + sigma*X*dW (modelo log-normal, ej. para
    crecimiento poblacional multiplicativo con ruido).
    """
    rng = np.random.default_rng(seed)
    dt = T / n_steps
    dW = rng.normal(0, np.sqrt(dt), (n_paths, n_steps))
    t = np.linspace(0, T, n_steps + 1)

    if kind == "geometric":
        log_returns = (mu - 0.5 * sigma ** 2) * dt + sigma * dW
        log_paths = np.cumsum(log_returns, axis=1)
        paths = x0 * np.exp(np.hstack([np.zeros((n_paths, 1)), log_paths]))
    else:
        increments = mu * dt + sigma * dW
        paths = x0 + np.hstack([np.zeros((n_paths, 1)), np.cumsum(increments, axis=1)])

    mean_path = paths.mean(axis=0)
    std_path = paths.std(axis=0)
    track_every = max(1, n_steps // 50)
    return {
        "mode": "brownian_motion", "kind": kind, "T": T, "n_steps": n_steps, "n_paths": n_paths,
        "mu": mu, "sigma": sigma, "x0": x0,
        "final_value_mean": round(float(paths[:, -1].mean()), 6),
        "final_value_std": round(float(paths[:, -1].std()), 6),
        "trajectory_mean": [{"t": round(float(t[i]), 4), "mean": round(float(mean_path[i]), 6), "std": round(float(std_path[i]), 6)}
                             for i in range(0, n_steps + 1, track_every)],
        "sample_paths": [[round(float(x), 6) for x in paths[i, ::track_every]] for i in range(min(5, n_paths))],
    }


def compute_ornstein_uhlenbeck(T=10.0, n_steps=1000, n_paths=100, theta=1.0, mu=0.0,
                                sigma=0.5, x0=2.0, seed=None):
    """
    dX = theta*(mu - X)*dt + sigma*dW. Reversion a la media mu con velocidad
    theta. Varianza estacionaria teorica: sigma^2/(2*theta) - sirve de
    benchmark directo. Modelo natural para variables ambientales acotadas
    con equilibrio (temperatura, pH, humedad relativa en un bioreactor).
    """
    rng = np.random.default_rng(seed)
    dt = T / n_steps
    paths = np.zeros((n_paths, n_steps + 1))
    paths[:, 0] = x0
    dW = rng.normal(0, np.sqrt(dt), (n_paths, n_steps))
    for i in range(n_steps):
        paths[:, i + 1] = paths[:, i] + theta * (mu - paths[:, i]) * dt + sigma * dW[:, i]

    t = np.linspace(0, T, n_steps + 1)
    theoretical_stationary_var = sigma ** 2 / (2 * theta) if theta > 0 else None
    half_life = np.log(2) / theta if theta > 0 else None
    tail_frac = max(1, n_steps // 5)
    empirical_stationary_var = float(paths[:, -tail_frac:].var())

    track_every = max(1, n_steps // 50)
    return {
        "mode": "ornstein_uhlenbeck", "T": T, "n_steps": n_steps, "n_paths": n_paths,
        "theta": theta, "mu": mu, "sigma": sigma, "x0": x0,
        "half_life": round(float(half_life), 6) if half_life else None,
        "theoretical_stationary_variance": round(float(theoretical_stationary_var), 6) if theoretical_stationary_var else None,
        "empirical_stationary_variance": round(empirical_stationary_var, 6),
        "final_value_mean": round(float(paths[:, -1].mean()), 6),
        "trajectory_mean": [{"t": round(float(t[i]), 4), "mean": round(float(paths[:, i].mean()), 6), "std": round(float(paths[:, i].std()), 6)}
                             for i in range(0, n_steps + 1, track_every)],
    }


def compute_markov_chain(transition_matrix, initial_state=None, n_steps=20, target_state=None):
    P = np.asarray(transition_matrix, dtype=float)
    n = P.shape[0]
    row_sums = P.sum(axis=1)
    if not np.allclose(row_sums, 1.0, atol=1e-6):
        raise ValueError(f"filas de transition_matrix deben sumar 1, dieron: {row_sums.tolist()}")

    # distribucion estacionaria: autovector izquierdo de autovalor 1
    eigvals, eigvecs = np.linalg.eig(P.T)
    idx = np.argmin(np.abs(eigvals - 1))
    stationary = np.real(eigvecs[:, idx])
    stationary = stationary / stationary.sum()

    if initial_state is None:
        dist = np.ones(n) / n
    else:
        dist = np.zeros(n)
        dist[initial_state] = 1.0
    trajectory = [dist.tolist()]
    for _ in range(n_steps):
        dist = dist @ P
        trajectory.append(dist.tolist())

    result = {
        "mode": "markov_chain", "n_states": n, "n_steps": n_steps,
        "stationary_distribution": [round(float(x), 6) for x in stationary],
        "distribution_trajectory": [[round(float(x), 6) for x in d] for d in trajectory[::max(1, n_steps // 20)]],
        "converged_to_stationary": bool(np.allclose(trajectory[-1], stationary, atol=1e-3)),
    }

    if target_state is not None and initial_state is not None:
        # tiempo esperado de primer paso via sistema lineal estandar
        Q = P.copy()
        Q[target_state, :] = 0
        Q[target_state, target_state] = 1
        A = np.eye(n) - P
        b = np.ones(n)
        A[target_state, :] = 0
        A[target_state, target_state] = 1
        b[target_state] = 0
        try:
            h = np.linalg.solve(A, b)
            result["expected_first_passage_time"] = round(float(h[initial_state]), 6)
        except np.linalg.LinAlgError:
            result["expected_first_passage_time"] = None

    return result


def compute_stochastic_processes(mode, **kwargs):
    """Dispatcher unico para el tool MCP stochastic_processes, segun 'mode'."""
    fns = {
        "brownian_motion": compute_brownian_motion,
        "ornstein_uhlenbeck": compute_ornstein_uhlenbeck,
        "markov_chain": compute_markov_chain,
    }
    if mode not in fns:
        raise ValueError(f"mode desconocido: {mode}")
    return fns[mode](**kwargs)


STOCHASTIC_PROCESSES_TOOL_SCHEMA = {
    "name": "stochastic_processes",
    "description": "Procesos estocasticos: movimiento browniano (estandar/con drift/geometrico), proceso de Ornstein-Uhlenbeck (reversion a la media, util para variables ambientales con equilibrio), y cadenas de Markov discretas (distribucion estacionaria, tiempo de primer paso).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["brownian_motion", "ornstein_uhlenbeck", "markov_chain"]},
            "T": {"type": "number"}, "n_steps": {"type": "integer"}, "n_paths": {"type": "integer"},
            "mu": {"type": "number"}, "sigma": {"type": "number"}, "x0": {"type": "number"},
            "kind": {"type": "string", "enum": ["standard", "geometric"]}, "seed": {"type": "integer"},
            "theta": {"type": "number"},
            "transition_matrix": {"type": "array"}, "initial_state": {"type": "integer"},
            "target_state": {"type": "integer"},
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    r1 = compute_stochastic_processes(mode="brownian_motion", T=1.0, n_steps=500, n_paths=200, mu=0.0, sigma=1.0, seed=42)
    print({k: v for k, v in r1.items() if k not in ("trajectory_mean", "sample_paths")})
    r2 = compute_stochastic_processes(mode="ornstein_uhlenbeck", T=20.0, n_steps=1000, n_paths=200, theta=0.5, mu=2.0, sigma=0.8, x0=5.0, seed=42)
    print({k: v for k, v in r2.items() if k != "trajectory_mean"})
    r3 = compute_stochastic_processes(mode="markov_chain", transition_matrix=[[0.9, 0.1], [0.3, 0.7]], initial_state=0, n_steps=30, target_state=1)
    print(r3)
