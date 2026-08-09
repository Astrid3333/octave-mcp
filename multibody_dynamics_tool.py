"""
multibody_dynamics_tool.py
Dinamica de cuerpos rigidos y sistemas multi-cuerpo.

Modos:
  - compound_pendulum   : pendulo fisico (varilla uniforme), periodo pequenas oscilaciones
  - rigid_body_euler    : rotacion libre de par (ecuaciones de Euler), conserva energia y |L|
  - two_link_manipulator: brazo/pendulo doble planar via Lagrangiano, conserva energia

Validado contra:
  - T = 2*pi*sqrt(I/(m*g*d))              (pendulo fisico, libro de texto)
  - conservacion de energia cinetica y |L|^2 en rotacion libre de par
  - conservacion de energia mecanica en el manipulador de 2 eslabones
"""
import numpy as np
from scipy.integrate import solve_ivp

MULTIBODY_DYNAMICS_TOOL_SCHEMA = {
    "name": "multibody_dynamics_tool",
    "description": (
        "Dinamica de cuerpos rigidos y sistemas multi-cuerpo: pendulo fisico "
        "(compound_pendulum), rotacion libre de par via ecuaciones de Euler "
        "(rigid_body_euler), manipulador/pendulo doble planar via Lagrangiano "
        "(two_link_manipulator). Validado contra formulas de libro de texto."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["compound_pendulum", "rigid_body_euler", "two_link_manipulator"]},
            "params": {"type": "object", "description": "Parametros especificos de cada modo, ver docstrings."},
        },
        "required": ["mode"],
    },
}


def _compound_pendulum(m=2.0, L=1.5, g=9.81, theta0=0.05, t_max=20.0):
    I = (1/3) * m * L**2
    d = L / 2
    T_analytic = 2*np.pi*np.sqrt(I/(m*g*d))

    def ode(t, y):
        th, om = y
        return [om, -(m*g*d/I)*np.sin(th)]

    sol = solve_ivp(ode, [0, t_max], [theta0, 0], max_step=0.001)
    th, t = sol.y[0], sol.t
    crossings = []
    for i in range(1, len(th)):
        if th[i-1] < 0 <= th[i]:
            frac = -th[i-1]/(th[i]-th[i-1])
            crossings.append(t[i-1] + frac*(t[i]-t[i-1]))
    T_numeric = float(np.mean(np.diff(crossings))) if len(crossings) > 1 else None
    return {
        "mode": "compound_pendulum",
        "moment_of_inertia_I": I,
        "distance_to_com_d": d,
        "period_analytic_s": T_analytic,
        "period_numeric_s": T_numeric,
        "relative_error_pct": (100*abs(T_numeric-T_analytic)/T_analytic) if T_numeric else None,
        "time": sol.t.tolist()[::50],
        "theta": sol.y[0].tolist()[::50],
    }


def _rigid_body_euler(I1=3.0, I2=2.0, I3=1.0, w0=None, t_max=50.0):
    w0 = w0 or [1.0, 0.5, 0.1]

    def ode(t, w):
        w1, w2, w3 = w
        return [
            (I2-I3)/I1 * w2*w3,
            (I3-I1)/I2 * w3*w1,
            (I1-I2)/I3 * w1*w2,
        ]
    sol = solve_ivp(ode, [0, t_max], w0, max_step=0.01)
    w1, w2, w3 = sol.y
    KE = 0.5*(I1*w1**2 + I2*w2**2 + I3*w3**2)
    L2 = (I1*w1)**2 + (I2*w2)**2 + (I3*w3)**2
    return {
        "mode": "rigid_body_euler",
        "energy_drift_relative": float(np.ptp(KE)/KE[0]),
        "angular_momentum_sq_drift_relative": float(np.ptp(L2)/L2[0]),
        "time": sol.t.tolist()[::20],
        "omega": [w1.tolist()[::20], w2.tolist()[::20], w3.tolist()[::20]],
    }


def _two_link_manipulator(m1=1.0, m2=1.0, l1=1.0, l2=1.0, g=9.81, theta0=None, t_max=10.0):
    theta0 = theta0 or [1.5, 0.0]

    def ode(t, y):
        th1, th2, w1, w2 = y
        delta = th1 - th2
        den1 = (m1+m2)*l1 - m2*l1*np.cos(delta)**2
        a1 = ((-m2*l1*w1**2*np.sin(delta)*np.cos(delta)
               + m2*g*np.sin(th2)*np.cos(delta)
               - m2*l2*w2**2*np.sin(delta)
               - (m1+m2)*g*np.sin(th1)) / den1)
        den2 = (l2/l1)*den1
        a2 = ((m2*l2*w2**2*np.sin(delta)*np.cos(delta)
               + (m1+m2)*g*np.sin(th1)*np.cos(delta)
               + (m1+m2)*l1*w1**2*np.sin(delta)
               - (m1+m2)*g*np.sin(th2)) / den2)
        return [w1, w2, a1, a2]

    th10, th20 = theta0
    sol = solve_ivp(ode, [0, t_max], [th10, th20, 0, 0], max_step=0.001)
    th1, th2, w1, w2 = sol.y
    x1, y1 = l1*np.sin(th1), -l1*np.cos(th1)
    x2 = x1 + l2*np.sin(th2)
    y2 = y1 - l2*np.cos(th2)
    v1sq = (l1*w1)**2
    v2sq = v1sq + (l2*w2)**2 + 2*l1*l2*w1*w2*np.cos(th1-th2)
    KE = 0.5*m1*v1sq + 0.5*m2*v2sq
    PE = m1*g*y1 + m2*g*y2
    E = KE + PE
    return {
        "mode": "two_link_manipulator",
        "energy_drift_relative": float(np.ptp(E)/abs(E[0])),
        "time": sol.t.tolist()[::50],
        "theta1": th1.tolist()[::50],
        "theta2": th2.tolist()[::50],
    }


def compute_multibody_dynamics(mode, params=None):
    params = params or {}
    if mode == "compound_pendulum":
        return _compound_pendulum(**params)
    elif mode == "rigid_body_euler":
        return _rigid_body_euler(**params)
    elif mode == "two_link_manipulator":
        return _two_link_manipulator(**params)
    else:
        raise ValueError(f"modo desconocido: {mode}. Use compound_pendulum | rigid_body_euler | two_link_manipulator")


if __name__ == "__main__":
    r1 = compute_multibody_dynamics("compound_pendulum", {"m": 2.0, "L": 1.5})
    print("compound_pendulum err%% =", r1["relative_error_pct"])
    r2 = compute_multibody_dynamics("rigid_body_euler", {"I1": 3.0, "I2": 2.0, "I3": 1.0})
    print("rigid_body_euler energy drift =", r2["energy_drift_relative"])
    r3 = compute_multibody_dynamics("two_link_manipulator", {})
    print("two_link_manipulator energy drift =", r3["energy_drift_relative"])
