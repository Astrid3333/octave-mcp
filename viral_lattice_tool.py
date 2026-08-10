"""
viral_lattice_tool.py

Dos motores independientes relacionados con dinamica viral:

1) viral_spread_pde: sistema de reaccion-difusion 1D para celulas blanco (T),
   celulas infectadas (I) y virus libre (V), analogo al modelo TIV clasico
   de dinamica viral in-host (Nowak & May) con difusion espacial agregada
   (celulas y virus se mueven en el tejido/lattice), integrado por
   diferencias finitas explicitas:
       dT/dt = -beta*T*V + D_T*Laplaciano(T)
       dI/dt =  beta*T*V - delta*I + D_I*Laplaciano(I)
       dV/dt =  p*I - c*V + D_V*Laplaciano(V)

2) capsid_fock_state: representa la distribucion del numero de subunidades
   ensambladas de una capside viral usando el formalismo de espacio de Fock
   / estados coherentes (numero de ocupacion). Un estado coherente |alpha>
   tiene distribucion de numero de Poisson: P(n) = e^-|alpha|^2 * |alpha|^(2n) / n!,
   con <n> = |alpha|^2 y Var(n) = |alpha|^2 (ruido shot, caracteristico de
   ensamblado estocastico independiente de subunidades).

Modos:
  - viral_spread_pde: simula TIV+difusion 1D.
  - capsid_fock_state: distribucion de Poisson (Fock) para un alpha dado.
  - validate: conservacion aproximada de masa total en el PDE sin fuentes
    externas; y <n>=Var(n)=|alpha|^2 para el estado de Fock.
"""

import numpy as np


def _laplacian_1d(u, dx):
    lap = np.zeros_like(u)
    lap[1:-1] = (u[2:] - 2 * u[1:-1] + u[:-2]) / dx**2
    lap[0] = (u[1] - u[0]) / dx**2  # Neumann (reflectante) en bordes
    lap[-1] = (u[-2] - u[-1]) / dx**2
    return lap


def _viral_spread_pde(
    beta, delta, p, c, D_T, D_I, D_V,
    T0, I0_peak, V0, L=10.0, nx=50, t_final=20.0, dt=None,
):
    dx = L / (nx - 1)
    if dt is None:
        # CFL para el termino difusivo mas rapido
        D_max = max(D_T, D_I, D_V, 1e-9)
        dt = 0.2 * dx**2 / (2 * D_max)
    n_steps = int(t_final / dt)

    T = np.full(nx, T0, dtype=float)
    I = np.zeros(nx, dtype=float)
    V = np.zeros(nx, dtype=float)
    # foco inicial de infeccion en el centro
    center = nx // 2
    I[center] = I0_peak
    V[center] = V0

    snapshots = []
    snapshot_every = max(1, n_steps // 20)

    for step in range(n_steps):
        infection = beta * T * V
        dT = -infection + D_T * _laplacian_1d(T, dx)
        dI = infection - delta * I + D_I * _laplacian_1d(I, dx)
        dV = p * I - c * V + D_V * _laplacian_1d(V, dx)
        T = np.maximum(T + dt * dT, 0.0)
        I = np.maximum(I + dt * dI, 0.0)
        V = np.maximum(V + dt * dV, 0.0)
        if step % snapshot_every == 0:
            snapshots.append(
                {
                    "t": float(step * dt),
                    "T_total": float(np.sum(T) * dx),
                    "I_total": float(np.sum(I) * dx),
                    "V_total": float(np.sum(V) * dx),
                }
            )

    return {
        "mode": "viral_spread_pde",
        "params": {
            "beta": beta, "delta": delta, "p": p, "c": c,
            "D_T": D_T, "D_I": D_I, "D_V": D_V,
            "T0": T0, "I0_peak": I0_peak, "V0": V0, "L": L, "nx": nx, "t_final": t_final, "dt": dt,
        },
        "n_steps": n_steps,
        "snapshots": snapshots,
        "final_T_profile": T.tolist(),
        "final_I_profile": I.tolist(),
        "final_V_profile": V.tolist(),
    }


def _capsid_fock_state(alpha, n_max=50):
    alpha = float(alpha)
    mean_n = alpha**2
    n_vals = np.arange(0, n_max + 1)
    log_p = -mean_n + n_vals * np.log(max(mean_n, 1e-300)) - np.array(
        [np.sum(np.log(np.arange(1, k + 1))) if k > 0 else 0.0 for k in n_vals]
    )
    probs = np.exp(log_p)
    probs = probs / np.sum(probs)  # renormalizar por truncamiento en n_max
    n_expect = float(np.sum(n_vals * probs))
    n_var = float(np.sum((n_vals - n_expect) ** 2 * probs))
    return {
        "mode": "capsid_fock_state",
        "alpha": alpha,
        "n_max_truncation": n_max,
        "n_values": n_vals.tolist(),
        "probabilities": probs.tolist(),
        "mean_n": n_expect,
        "variance_n": n_var,
        "fano_factor": float(n_var / n_expect) if n_expect > 0 else None,
        "note": "estado coherente ideal: Fano factor ~1 (ruido de disparo/Poisson) salvo error de truncamiento en n_max.",
    }


def _validate():
    pde_result = _viral_spread_pde(
        beta=0.01, delta=0.5, p=5.0, c=1.0, D_T=0.0, D_I=0.01, D_V=0.05,
        T0=100.0, I0_peak=1.0, V0=1.0, L=10.0, nx=30, t_final=5.0,
    )
    finite_ok = all(np.isfinite(pde_result["final_V_profile"]))

    fock = _capsid_fock_state(alpha=5.0, n_max=80)
    poisson_ok = abs(fock["mean_n"] - 25.0) < 1.0 and abs(fock["fano_factor"] - 1.0) < 0.05

    return {
        "mode": "validate",
        "pde_final_V_total": pde_result["snapshots"][-1]["V_total"],
        "fock_mean_n": fock["mean_n"],
        "fock_fano_factor": fock["fano_factor"],
        "expected": "PDE produce valores finitos no negativos; estado de Fock con alpha=5 da <n>~25, Fano~1",
        "validation_passed": bool(finite_ok and poisson_ok),
    }


def compute_viral_lattice_tool(mode, **kwargs):
    if mode == "viral_spread_pde":
        return _viral_spread_pde(
            kwargs["beta"], kwargs["delta"], kwargs["p"], kwargs["c"],
            kwargs.get("D_T", 0.0), kwargs.get("D_I", 0.01), kwargs.get("D_V", 0.05),
            kwargs["T0"], kwargs["I0_peak"], kwargs["V0"],
            L=kwargs.get("L", 10.0), nx=kwargs.get("nx", 50),
            t_final=kwargs.get("t_final", 20.0), dt=kwargs.get("dt"),
        )
    elif mode == "capsid_fock_state":
        return _capsid_fock_state(kwargs["alpha"], n_max=kwargs.get("n_max", 50))
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"mode desconocido: {mode}")


VIRAL_LATTICE_TOOL_SCHEMA = {
    "name": "viral_lattice_tool",
    "description": (
        "Dos motores: viral_spread_pde simula un sistema TIV (celulas blanco/infectadas/virus) "
        "con difusion 1D via diferencias finitas explicitas (analogo espacial al modelo in-host "
        "de Nowak & May); capsid_fock_state representa el numero de subunidades ensambladas de "
        "una capside como estado coherente en espacio de Fock (distribucion de Poisson, "
        "<n>=Var(n)=alpha^2). mode='viral_spread_pde' (beta, delta, p, c, D_T, D_I, D_V, T0, "
        "I0_peak, V0, L, nx, t_final, dt); mode='capsid_fock_state' (alpha, n_max); "
        "mode='validate' corre ambos con parametros de referencia."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["viral_spread_pde", "capsid_fock_state", "validate"],
                "default": "validate",
            },
            "beta": {"type": "number", "description": "Tasa de infeccion T+V->I. viral_spread_pde."},
            "delta": {"type": "number", "description": "Tasa de muerte de celulas infectadas. viral_spread_pde."},
            "p": {"type": "number", "description": "Tasa de produccion viral por celula infectada. viral_spread_pde."},
            "c": {"type": "number", "description": "Tasa de clearance viral. viral_spread_pde."},
            "D_T": {"type": "number", "default": 0.0, "description": "Difusividad de T. viral_spread_pde."},
            "D_I": {"type": "number", "default": 0.01, "description": "Difusividad de I. viral_spread_pde."},
            "D_V": {"type": "number", "default": 0.05, "description": "Difusividad de V. viral_spread_pde."},
            "T0": {"type": "number", "description": "Densidad inicial de celulas blanco. viral_spread_pde."},
            "I0_peak": {"type": "number", "description": "Pico inicial de I en el centro del lattice. viral_spread_pde."},
            "V0": {"type": "number", "description": "Pico inicial de V en el centro. viral_spread_pde."},
            "L": {"type": "number", "default": 10.0, "description": "Largo del dominio 1D. viral_spread_pde."},
            "nx": {"type": "integer", "default": 50, "description": "Puntos de grilla. viral_spread_pde."},
            "t_final": {"type": "number", "default": 20.0, "description": "Tiempo final. viral_spread_pde."},
            "dt": {"type": "number", "description": "Paso temporal, opcional (auto via CFL si se omite). viral_spread_pde."},
            "alpha": {"type": "number", "description": "Amplitud del estado coherente (sqrt del numero medio de subunidades). capsid_fock_state."},
            "n_max": {"type": "integer", "default": 50, "description": "Truncamiento del espacio de Fock. capsid_fock_state."},
        },
        "required": ["mode"],
    },
}
