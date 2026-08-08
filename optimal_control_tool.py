#!/usr/bin/env python3
"""
optimal_control_tool.py
Control optimo: LQR (regulador lineal-cuadratico, ecuacion de Riccati
algebraica continua) con simulacion de lazo cerrado, control LQ de horizonte
finito via Riccati diferencial hacia atras (caso escalar del principio del
maximo de Pontryagin, con trayectorias de estado/costado/control explicitas),
y programacion dinamica (iteracion de valor) para procesos de decision de
Markov finitos - politica optima y funcion de valor.
"""
import numpy as np
from scipy.linalg import solve_continuous_are


def compute_lqr(A, B, Q, R, x0, T=10.0, n_steps=500):
    A, B, Q, R = [np.asarray(m, dtype=float) for m in (A, B, Q, R)]
    x0 = np.asarray(x0, dtype=float)
    P = solve_continuous_are(A, B, Q, R)
    K = np.linalg.inv(R) @ B.T @ P
    A_cl = A - B @ K

    dt = T / n_steps
    n = A.shape[0]
    x = x0.copy()
    trajectory = [{"t": 0.0, "x": x.tolist(), "u": (-K @ x).tolist()}]
    for step in range(1, n_steps + 1):
        u = -K @ x
        x = x + dt * (A_cl @ x)
        if step % max(1, n_steps // 50) == 0:
            trajectory.append({"t": round(step * dt, 4), "x": [round(float(v), 6) for v in x], "u": [round(float(v), 6) for v in u]})

    eigvals_cl = np.linalg.eigvals(A_cl)
    return {
        "mode": "lqr", "T": T,
        "gain_matrix_K": [[round(float(v), 6) for v in row] for row in K],
        "riccati_solution_P": [[round(float(v), 6) for v in row] for row in P],
        "closed_loop_eigenvalues": [{"real": round(float(e.real), 6), "imag": round(float(e.imag), 6)} for e in eigvals_cl],
        "closed_loop_stable": bool(np.all(eigvals_cl.real < 0)),
        "trajectory": trajectory,
        "final_state": [round(float(v), 6) for v in x],
    }


def compute_pontryagin_lq(a, b, q, r, x0, T=5.0, n_steps=500):
    """
    Problema LQ escalar de horizonte finito: minimizar integral(q*x^2+r*u^2)dt
    con dx/dt=a*x+b*u, x(0)=x0. Via el principio del maximo de Pontryagin, el
    Hamiltoniano H=q*x^2+r*u^2+lambda*(a*x+b*u) se minimiza en u*=-b*lambda/(2r),
    y sustituyendo se obtiene la ecuacion de Riccati diferencial para P(t)
    (S(t)) integrada hacia atras desde P(T)=0: dP/dt = -2*a*P + (b^2/r)*P^2 - q.
    La ley de control optima es u(t) = -(b/r)*P(t)*x(t).
    """
    dt = T / n_steps
    P = np.zeros(n_steps + 1)
    P[-1] = 0.0
    for i in range(n_steps - 1, -1, -1):
        dP = -(-2 * a * P[i + 1] + (b ** 2 / r) * P[i + 1] ** 2 - q)
        P[i] = P[i + 1] + dt * (2 * a * P[i + 1] - (b ** 2 / r) * P[i + 1] ** 2 + q)

    x = np.zeros(n_steps + 1)
    u = np.zeros(n_steps)
    costate = np.zeros(n_steps + 1)
    x[0] = x0
    for i in range(n_steps):
        u[i] = -(b / r) * P[i] * x[i]
        costate[i] = 2 * P[i] * x[i]
        x[i + 1] = x[i] + dt * (a * x[i] + b * u[i])
    costate[-1] = 2 * P[-1] * x[-1]

    total_cost = float(np.sum((q * x[:-1] ** 2 + r * u ** 2) * dt))
    track_every = max(1, n_steps // 50)
    return {
        "mode": "pontryagin_lq", "a": a, "b": b, "q": q, "r": r, "x0": x0, "T": T,
        "riccati_P0": round(float(P[0]), 6),
        "total_cost": round(total_cost, 6),
        "final_state": round(float(x[-1]), 6),
        "trajectory": [{"t": round(i * dt, 4), "x": round(float(x[i]), 6),
                         "u": round(float(u[i]), 6) if i < n_steps else None,
                         "costate": round(float(costate[i]), 6)}
                        for i in range(0, n_steps + 1, track_every)],
    }


def compute_dynamic_programming(transition_probs, rewards, gamma=0.95, tol=1e-6, max_iter=1000):
    """
    transition_probs: array [n_states][n_actions][n_states] con P(s'|s,a).
    rewards: array [n_states][n_actions] con recompensa inmediata r(s,a).
    Iteracion de valor estandar de Bellman: V*(s) = max_a [r(s,a) + gamma*sum_s' P(s'|s,a)*V*(s')].
    """
    P = np.asarray(transition_probs, dtype=float)
    R = np.asarray(rewards, dtype=float)
    n_states, n_actions = R.shape
    V = np.zeros(n_states)
    for iteration in range(max_iter):
        Q = R + gamma * np.einsum('san,n->sa', P, V)
        V_new = Q.max(axis=1)
        delta = float(np.max(np.abs(V_new - V)))
        V = V_new
        if delta < tol:
            break
    Q_final = R + gamma * np.einsum('san,n->sa', P, V)
    policy = Q_final.argmax(axis=1)
    return {
        "mode": "dynamic_programming", "n_states": n_states, "n_actions": n_actions,
        "gamma": gamma, "n_iterations": iteration + 1, "converged": bool(delta < tol),
        "optimal_value_function": [round(float(v), 6) for v in V],
        "optimal_policy": [int(a) for a in policy],
        "q_values": [[round(float(v), 6) for v in row] for row in Q_final],
    }


def compute_optimal_control(mode, **kwargs):
    """Dispatcher unico para el tool MCP optimal_control, segun 'mode'."""
    fns = {
        "lqr": compute_lqr,
        "pontryagin_lq": compute_pontryagin_lq,
        "dynamic_programming": compute_dynamic_programming,
    }
    if mode not in fns:
        raise ValueError(f"mode desconocido: {mode}")
    return fns[mode](**kwargs)


OPTIMAL_CONTROL_TOOL_SCHEMA = {
    "name": "optimal_control",
    "description": "Control optimo: LQR (Riccati algebraica continua, ley de control -Kx, simulacion de lazo cerrado), control LQ escalar de horizonte finito via principio del maximo de Pontryagin (Riccati diferencial, trayectorias de estado/costado/control), y programacion dinamica (iteracion de valor para MDP finitos: politica y funcion de valor optimas).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["lqr", "pontryagin_lq", "dynamic_programming"]},
            "A": {"type": "array"}, "B": {"type": "array"}, "Q": {"type": "array"}, "R": {"type": "array"},
            "x0": {}, "T": {"type": "number"}, "n_steps": {"type": "integer"},
            "a": {"type": "number"}, "b": {"type": "number"}, "q": {"type": "number"}, "r": {"type": "number"},
            "transition_probs": {"type": "array"}, "rewards": {"type": "array"},
            "gamma": {"type": "number"}, "tol": {"type": "number"}, "max_iter": {"type": "integer"},
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    r1 = compute_optimal_control(mode="lqr", A=[[0, 1], [0, 0]], B=[[0], [1]], Q=[[1, 0], [0, 1]], R=[[1]], x0=[1.0, 0.0], T=10.0)
    print({k: v for k, v in r1.items() if k != "trajectory"})
    r2 = compute_optimal_control(mode="pontryagin_lq", a=0.0, b=1.0, q=1.0, r=1.0, x0=2.0, T=5.0)
    print({k: v for k, v in r2.items() if k != "trajectory"})
    # MDP de 2 estados / 2 acciones de juguete: estado 0="malo", estado 1="bueno"
    r3 = compute_optimal_control(
        mode="dynamic_programming",
        transition_probs=[[[0.8, 0.2], [0.3, 0.7]], [[0.5, 0.5], [0.1, 0.9]]],
        rewards=[[0, 1], [2, 5]],
        gamma=0.9,
    )
    print(r3)
