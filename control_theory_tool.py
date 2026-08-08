#!/usr/bin/env python3
"""
control_theory_tool.py
Teoria de control: respuesta a escalon de un lazo PID (planta + controlador
en funcion de transferencia), estabilidad de Routh-Hurwitz, lugar de raices
(polos en lazo cerrado vs. ganancia K), y control OGY (Ott-Grebogi-Yorke)
para estabilizar orbitas periodicas inestables de un mapa caotico mediante
perturbaciones pequenas de un parametro - el metodo clasico de control de
caos, directamente aplicable a TritOS (estabilizacion de estados del
atractor sobre coigue via perturbaciones acotadas).
"""
import numpy as np
from scipy import signal


def compute_pid_step_response(num_plant, den_plant, Kp=1.0, Ki=0.0, Kd=0.0, T=10.0, n_points=500):
    # C(s) = Kd*s^2 + Kp*s + Ki, sobre s (integrador)
    num_c = [Kd, Kp, Ki]
    den_c = [1.0, 0.0]
    num_open = np.polymul(num_c, num_plant)
    den_open = np.polymul(den_c, den_plant)
    # lazo cerrado unitario: G/(1+G) -> igualar grados antes de sumar
    deg = max(len(num_open), len(den_open))
    num_pad = np.pad(num_open, (deg - len(num_open), 0))
    den_pad = np.pad(den_open, (deg - len(den_open), 0))
    den_closed = den_pad + num_pad
    sys = signal.TransferFunction(num_pad, den_closed)
    t = np.linspace(0, T, n_points)
    t_out, y = signal.step(sys, T=t)
    overshoot = float((y.max() - y[-1]) / y[-1] * 100) if y[-1] != 0 else None
    settled = np.where(np.abs(y - y[-1]) < 0.02 * abs(y[-1]))[0] if y[-1] != 0 else []
    settling_time = float(t_out[settled[0]]) if len(settled) > 0 else None
    poles = np.roots(den_closed)
    return {
        "mode": "pid_step_response", "Kp": Kp, "Ki": Ki, "Kd": Kd, "T": T,
        "closed_loop_poles": [{"real": round(float(p.real), 6), "imag": round(float(p.imag), 6)} for p in poles],
        "stable": bool(np.all(poles.real < 0)),
        "steady_state_value": round(float(y[-1]), 6),
        "overshoot_pct": round(overshoot, 4) if overshoot is not None else None,
        "settling_time_2pct": round(settling_time, 4) if settling_time is not None else None,
        "response_sample": [{"t": round(float(t_out[i]), 4), "y": round(float(y[i]), 6)} for i in range(0, n_points, max(1, n_points // 40))],
    }


def compute_routh_hurwitz(coefficients):
    """
    coefficients: coeficientes del polinomio caracteristico en orden
    descendente de potencia (ej. [1, 5, 6] para s^2+5s+6). Construye el
    arreglo de Routh y determina estabilidad (todos los polos con parte
    real negativa) sin resolver raices explicitamente.
    """
    c = [float(x) for x in coefficients]
    n = len(c)
    if n < 2:
        raise ValueError("se necesitan al menos 2 coeficientes")
    n_cols = (n + 1) // 2
    table = np.zeros((n, n_cols))
    table[0, :len(c[0::2])] = c[0::2]
    table[1, :len(c[1::2])] = c[1::2]
    for i in range(2, n):
        for j in range(n_cols - 1):
            a, b = table[i - 2, 0], table[i - 1, 0]
            if b == 0:
                b = 1e-12
            table[i, j] = (b * table[i - 2, j + 1] - a * table[i - 1, j + 1]) / b
    first_col = table[:, 0]
    sign_changes = int(np.sum(np.diff(np.sign(first_col)) != 0))
    return {
        "mode": "routh_hurwitz", "coefficients": coefficients,
        "routh_array_first_column": [round(float(x), 6) for x in first_col],
        "sign_changes": sign_changes,
        "stable": sign_changes == 0,
        "n_poles_right_half_plane": sign_changes,
    }


def compute_root_locus(num_open, den_open, k_min=0.0, k_max=20.0, n_k=100):
    k_values = np.linspace(k_min, k_max, n_k)
    deg = max(len(num_open), len(den_open))
    num_pad = np.pad(num_open, (deg - len(num_open), 0)).astype(float)
    den_pad = np.pad(den_open, (deg - len(den_open), 0)).astype(float)
    loci = []
    first_unstable_k = None
    for k in k_values:
        char_poly = den_pad + k * num_pad
        poles = np.roots(char_poly)
        loci.append([{"real": round(float(p.real), 6), "imag": round(float(p.imag), 6)} for p in poles])
        if first_unstable_k is None and np.any(poles.real > 0):
            first_unstable_k = float(k)
    return {
        "mode": "root_locus", "k_min": k_min, "k_max": k_max, "n_k": n_k,
        "k_values": [round(float(k), 4) for k in k_values],
        "poles_per_k": loci,
        "critical_gain_k_instability": round(first_unstable_k, 4) if first_unstable_k is not None else None,
    }


def compute_ogy_control(map_type="logistic", r0=4.0, control_radius=0.1, max_perturbation=0.05,
                         n_steps=300, x0=None, seed=None):
    """
    Control OGY para el punto fijo inestable no nulo del mapa logistico
    x_{n+1} = r*x_n*(1-x_n). El punto fijo x* = 1 - 1/r0 es inestable para
    r0>3 (autovalor lambda = 2 - r0). El controlador perturba r_n dentro de
    +-max_perturbation solo cuando la orbita entra en un radio control_radius
    de x* (esperando la recurrencia natural del caos - ergodicidad), forzando
    la siguiente iteracion hacia x* via linealizacion de primer orden.
    """
    rng = np.random.default_rng(seed)
    if x0 is None:
        x0 = float(rng.uniform(0.05, 0.95))

    def f(x, r):
        return r * x * (1 - x)

    x_star = 1 - 1 / r0
    lam = r0 * (1 - 2 * x_star)  # = 2 - r0 para logistico
    g = x_star * (1 - x_star)  # df/dr en (x*, r0)

    x_ctrl, x_free = x0, x0
    traj_controlled, traj_free = [], []
    n_control_active = 0
    for n in range(n_steps):
        if abs(x_ctrl - x_star) < control_radius:
            delta_r = -lam * (x_ctrl - x_star) / g
            delta_r = float(np.clip(delta_r, -max_perturbation, max_perturbation))
            r_n = r0 + delta_r
            n_control_active += 1
        else:
            r_n = r0
        x_ctrl = f(x_ctrl, r_n)
        x_free = f(x_free, r0)
        traj_controlled.append(round(float(x_ctrl), 6))
        traj_free.append(round(float(x_free), 6))

    tail = traj_controlled[-50:]
    controlled_std_tail = float(np.std(tail))
    free_std_tail = float(np.std(traj_free[-50:]))
    return {
        "mode": "ogy_control", "map_type": map_type, "r0": r0, "x0": round(x0, 6),
        "unstable_fixed_point": round(float(x_star), 6),
        "local_eigenvalue_lambda": round(float(lam), 6),
        "parameter_sensitivity_g": round(float(g), 6),
        "control_radius": control_radius, "max_perturbation": max_perturbation,
        "n_steps": n_steps, "n_steps_control_active": n_control_active,
        "controlled_trajectory_tail_std": round(controlled_std_tail, 6),
        "free_chaotic_trajectory_tail_std": round(free_std_tail, 6),
        "control_effective": bool(controlled_std_tail < 0.05 * free_std_tail if free_std_tail > 0 else controlled_std_tail < 1e-3),
        "trajectory_controlled_sample": traj_controlled[::max(1, n_steps // 60)],
        "trajectory_free_sample": traj_free[::max(1, n_steps // 60)],
    }


def compute_control_theory(mode, **kwargs):
    """Dispatcher unico para el tool MCP control_theory, segun 'mode'."""
    fns = {
        "pid_step_response": compute_pid_step_response,
        "routh_hurwitz": compute_routh_hurwitz,
        "root_locus": compute_root_locus,
        "ogy_control": compute_ogy_control,
    }
    if mode not in fns:
        raise ValueError(f"mode desconocido: {mode}")
    return fns[mode](**kwargs)


CONTROL_THEORY_TOOL_SCHEMA = {
    "name": "control_theory",
    "description": "Teoria de control: respuesta a escalon de lazo PID cerrado, estabilidad de Routh-Hurwitz (sin resolver raices), lugar de raices (polos vs ganancia K), y control OGY para estabilizar orbitas periodicas inestables de mapas caoticos via perturbaciones pequenas de parametro.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["pid_step_response", "routh_hurwitz", "root_locus", "ogy_control"]},
            "num_plant": {"type": "array"}, "den_plant": {"type": "array"},
            "Kp": {"type": "number"}, "Ki": {"type": "number"}, "Kd": {"type": "number"},
            "T": {"type": "number"}, "n_points": {"type": "integer"},
            "coefficients": {"type": "array"},
            "num_open": {"type": "array"}, "den_open": {"type": "array"},
            "k_min": {"type": "number"}, "k_max": {"type": "number"}, "n_k": {"type": "integer"},
            "map_type": {"type": "string"}, "r0": {"type": "number"},
            "control_radius": {"type": "number"}, "max_perturbation": {"type": "number"},
            "n_steps": {"type": "integer"}, "x0": {"type": "number"}, "seed": {"type": "integer"},
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    r1 = compute_control_theory(mode="pid_step_response", num_plant=[1], den_plant=[1, 2, 1], Kp=4.0, Ki=2.0, Kd=0.5, T=15.0)
    print({k: v for k, v in r1.items() if k != "response_sample"})
    r2 = compute_control_theory(mode="routh_hurwitz", coefficients=[1, 5, 6])
    print(r2)
    r3 = compute_control_theory(mode="routh_hurwitz", coefficients=[1, -1, 2])
    print(r3)
    r4 = compute_control_theory(mode="root_locus", num_open=[1], den_open=[1, 3, 2], k_min=0, k_max=10, n_k=50)
    print({k: v for k, v in r4.items() if k != "poles_per_k"})
    r5 = compute_control_theory(mode="ogy_control", r0=4.0, control_radius=0.1, max_perturbation=0.05, n_steps=300, seed=42)
    print({k: v for k, v in r5.items() if not k.startswith("trajectory")})
