"""
enzyme_stochastic_tool.py

Simulacion estocastica (Gillespie SSA, algoritmo exacto de Monte Carlo de
Gillespie 1977) de la cinetica enzimatica completa E+S<->ES->E+P, en numero
discreto de moleculas -- complementa a enzyme_kinetics_tool (que resuelve el
sistema determinista via ODEs). Util para regimenes de bajo numero de
moleculas donde el ruido estocastico es relevante (E0 chico).

Reacciones y propensiones:
    R1: E + S -> ES   a1 = k1  * E * S
    R2: ES -> E + S    a2 = km1 * ES
    R3: ES -> E + P    a3 = k2  * ES

Modos:
  - gillespie_michaelis_menten: corre una trayectoria SSA completa.
  - gillespie_ensemble: corre N trayectorias y devuelve estadisticos
    (media +- std de P(t) sobre una grilla temporal comun, via interpolacion
    tipo "ultimo valor" de cada trayectoria).
  - validate: la media del ensamble debe acercarse a la solucion
    determinista de las mismas tasas cuando E0,S0 son grandes (limite
    termodinamico, ley de los grandes numeros).
"""

import numpy as np


def _gillespie_run(k1, km1, k2, E0, S0, t_max, seed=None):
    rng = np.random.RandomState(seed)
    E, S, ES, P = E0, S0, 0, 0
    t = 0.0
    times = [0.0]
    E_traj, S_traj, ES_traj, P_traj = [E], [S], [ES], [P]

    while t < t_max:
        a1 = k1 * E * S
        a2 = km1 * ES
        a3 = k2 * ES
        a0 = a1 + a2 + a3
        if a0 <= 0:
            break
        tau = rng.exponential(1.0 / a0)
        t += tau
        if t > t_max:
            break
        r = rng.uniform(0, a0)
        if r < a1:
            E -= 1
            S -= 1
            ES += 1
        elif r < a1 + a2:
            E += 1
            S += 1
            ES -= 1
        else:
            E += 1
            ES -= 1
            P += 1
        times.append(t)
        E_traj.append(E)
        S_traj.append(S)
        ES_traj.append(ES)
        P_traj.append(P)

    return {
        "times": times,
        "E": E_traj,
        "S": S_traj,
        "ES": ES_traj,
        "P": P_traj,
    }


def _gillespie_michaelis_menten(k1, km1, k2, E0, S0, t_max, seed=None):
    traj = _gillespie_run(k1, km1, k2, E0, S0, t_max, seed=seed)
    return {
        "mode": "gillespie_michaelis_menten",
        "params": {"k1": k1, "km1": km1, "k2": k2, "E0": E0, "S0": S0, "t_max": t_max, "seed": seed},
        "n_reaction_events": len(traj["times"]) - 1,
        "trajectory": traj,
        "final_P": traj["P"][-1],
        "final_S": traj["S"][-1],
    }


def _sample_at_times(times, values, query_times):
    times = np.asarray(times)
    values = np.asarray(values)
    idx = np.searchsorted(times, query_times, side="right") - 1
    idx = np.clip(idx, 0, len(values) - 1)
    return values[idx]


def _gillespie_ensemble(k1, km1, k2, E0, S0, t_max, n_runs=50, n_time_points=30, seed=None):
    rng_master = np.random.RandomState(seed)
    query_times = np.linspace(0, t_max, n_time_points)
    P_matrix = np.zeros((n_runs, n_time_points))
    S_matrix = np.zeros((n_runs, n_time_points))
    for i in range(n_runs):
        run_seed = int(rng_master.randint(0, 2**31 - 1))
        traj = _gillespie_run(k1, km1, k2, E0, S0, t_max, seed=run_seed)
        P_matrix[i, :] = _sample_at_times(traj["times"], traj["P"], query_times)
        S_matrix[i, :] = _sample_at_times(traj["times"], traj["S"], query_times)

    return {
        "mode": "gillespie_ensemble",
        "params": {"k1": k1, "km1": km1, "k2": k2, "E0": E0, "S0": S0, "t_max": t_max, "n_runs": n_runs},
        "query_times": query_times.tolist(),
        "P_mean": np.mean(P_matrix, axis=0).tolist(),
        "P_std": np.std(P_matrix, axis=0).tolist(),
        "S_mean": np.mean(S_matrix, axis=0).tolist(),
        "S_std": np.std(S_matrix, axis=0).tolist(),
    }


def _deterministic_mm_reference(k1, km1, k2, E0, S0, t_max, n_points=30):
    """Integra el sistema determinista completo (mismo E+S<->ES->E+P) via RK4
    para comparar contra la media del ensamble estocastico."""

    def rhs(state):
        E, S, ES, P = state
        r1 = k1 * E * S
        r2 = km1 * ES
        r3 = k2 * ES
        return np.array([-r1 + r2 + r3, -r1 + r2, r1 - r2 - r3, r3])

    t = np.linspace(0, t_max, n_points)
    dt = t[1] - t[0]
    state = np.array([float(E0), float(S0), 0.0, 0.0])
    P_det = [0.0]
    for _ in range(n_points - 1):
        k1_ = rhs(state)
        k2_ = rhs(state + dt / 2 * k1_)
        k3_ = rhs(state + dt / 2 * k2_)
        k4_ = rhs(state + dt * k3_)
        state = state + dt / 6 * (k1_ + 2 * k2_ + 2 * k3_ + k4_)
        P_det.append(state[3])
    return t.tolist(), P_det


def _validate():
    # regimen de numero grande de moleculas: la media estocastica debe
    # aproximar la solucion determinista (ley de los grandes numeros)
    params = dict(k1=0.001, km1=0.1, k2=0.5, E0=200, S0=1000, t_max=10.0)
    ensemble = _gillespie_ensemble(**params, n_runs=40, n_time_points=15, seed=42)
    t_det, P_det = _deterministic_mm_reference(**params, n_points=15)
    P_stoch = np.array(ensemble["P_mean"])
    P_det_arr = np.array(P_det)
    rel_error_final = float(abs(P_stoch[-1] - P_det_arr[-1]) / max(P_det_arr[-1], 1e-9))

    return {
        "mode": "validate",
        "stochastic_final_P_mean": float(P_stoch[-1]),
        "deterministic_final_P": float(P_det_arr[-1]),
        "relative_error": rel_error_final,
        "expected": "con E0,S0 grandes, la media del ensamble SSA debe acercarse a la solucion ODE determinista (error relativo chico)",
        "validation_passed": bool(rel_error_final < 0.15),
    }


def compute_enzyme_stochastic(mode, **kwargs):
    if mode == "gillespie_michaelis_menten":
        return _gillespie_michaelis_menten(
            kwargs["k1"], kwargs["km1"], kwargs["k2"], kwargs["E0"], kwargs["S0"], kwargs["t_max"],
            seed=kwargs.get("seed"),
        )
    elif mode == "gillespie_ensemble":
        return _gillespie_ensemble(
            kwargs["k1"], kwargs["km1"], kwargs["k2"], kwargs["E0"], kwargs["S0"], kwargs["t_max"],
            n_runs=kwargs.get("n_runs", 50), n_time_points=kwargs.get("n_time_points", 30),
            seed=kwargs.get("seed"),
        )
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"mode desconocido: {mode}")


ENZYME_STOCHASTIC_SCHEMA = {
    "name": "enzyme_stochastic",
    "description": (
        "Simulacion estocastica exacta (Gillespie SSA) de la cinetica enzimatica completa "
        "E+S<->ES->E+P en numero discreto de moleculas. Complementa a enzyme_kinetics_tool "
        "(determinista/ODE), relevante cuando E0/S0 son chicos y el ruido molecular importa. "
        "mode='gillespie_michaelis_menten' (una trayectoria: k1, km1, k2, E0, S0, t_max, seed); "
        "mode='gillespie_ensemble' (N trayectorias, media+-std de P(t): agrega n_runs, "
        "n_time_points); mode='validate' compara la media del ensamble contra la solucion "
        "determinista en el regimen de numero grande de moleculas."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["gillespie_michaelis_menten", "gillespie_ensemble", "validate"],
                "default": "validate",
            },
            "k1": {"type": "number", "description": "Tasa de asociacion E+S->ES."},
            "km1": {"type": "number", "description": "Tasa de disociacion ES->E+S."},
            "k2": {"type": "number", "description": "Tasa catalitica ES->E+P."},
            "E0": {"type": "integer", "description": "Numero inicial de moleculas de enzima."},
            "S0": {"type": "integer", "description": "Numero inicial de moleculas de sustrato."},
            "t_max": {"type": "number", "description": "Tiempo final de simulacion."},
            "seed": {"type": "integer", "description": "Semilla RNG, opcional."},
            "n_runs": {"type": "integer", "default": 50, "description": "gillespie_ensemble."},
            "n_time_points": {"type": "integer", "default": 30, "description": "gillespie_ensemble."},
        },
        "required": ["mode"],
    },
}
