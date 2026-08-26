"""
bloch_equation_tool.py

Ecuaciones de Bloch para resonancia magnetica (RM/NMR): precesion libre
con relajacion T1/T2, simulacion de pulso RF (integracion numerica del
sistema completo), spin-echo y saturation-recovery. Complementa a
relaxometry_tool (que estima T1/T2 a partir de datos) simulando la fisica
hacia adelante: dada la fisica, predice la senal.

Convencion: campo B0 a lo largo de z, RF (B1) en el marco rotante a lo
largo de x cuando corresponde (on-resonance). Gamma de proton (1H):
267.522e6 rad/s/T (42.5774e6 Hz/T).

Modes:
  - free_precession: solucion analitica M(t) bajo B0 con relajacion,
    sin RF (params: m0, t1, t2, mxy0, mz0, phase0, larmor_hz, t_array)
  - rf_pulse: integracion numerica del sistema completo de Bloch durante
    un pulso RF de duracion tau con amplitud b1 (on-resonance)
    (params: m0, t1, t2, b1_tesla, tau_s, mz0, n_steps)
  - spin_echo: senal predicha a tiempo TE en una secuencia spin-echo
    (params: m0, t2, te_s)
  - saturation_recovery: recuperacion de Mz tras pulso de 90 grados,
    en funcion de TR (params: m0, t1, tr_s)
  - validate: auto-validacion contra casos con resultado conocido
"""
import json
import math

import numpy as np
from scipy.integrate import solve_ivp

TOOL_NAME = "bloch_equation_tool"

GAMMA_HZ = 42.5774e6                 # Hz/T, proton (1H)
GAMMA_RAD = 2 * math.pi * GAMMA_HZ   # rad/s/T


def free_precession(m0=1.0, t1=1.0, t2=0.1, mxy0=0.0, mz0=None,
                     phase0=0.0, larmor_hz=0.0, t_array=None):
    if mz0 is None:
        mz0 = m0
    if t_array is None:
        t_array = [0.0, 0.05, 0.1, 0.2, 0.5, 1.0]
    t = np.asarray(t_array, dtype=float)
    omega = 2 * math.pi * larmor_hz
    mag_xy = mxy0 * np.exp(-t / t2)
    mx = mag_xy * np.cos(omega * t + phase0)
    my = -mag_xy * np.sin(omega * t + phase0)
    mz = m0 - (m0 - mz0) * np.exp(-t / t1)
    return {
        "t_s": t.tolist(),
        "mx": mx.tolist(),
        "my": my.tolist(),
        "mz": mz.tolist(),
        "mxy_magnitude": mag_xy.tolist(),
    }


def _bloch_rhs(t, M, b1, t1, t2, m0):
    mx, my, mz = M
    # B1 a lo largo de x, on-resonance (Bz efectivo = 0, By = 0)
    dmx = -mx / t2
    dmy = GAMMA_RAD * (mz * b1) - my / t2
    dmz = -GAMMA_RAD * (my * b1) - (mz - m0) / t1
    return [dmx, dmy, dmz]


def rf_pulse(m0=1.0, t1=1.0, t2=0.1, b1_tesla=1e-5, tau_s=None,
             mz0=None, n_steps=200):
    if mz0 is None:
        mz0 = m0
    if tau_s is None:
        # pulso de 90 grados por defecto: gamma*B1*tau = pi/2
        tau_s = (math.pi / 2) / (GAMMA_RAD * b1_tesla)
    t_eval = np.linspace(0, tau_s, n_steps)
    sol = solve_ivp(_bloch_rhs, [0, tau_s], [0.0, 0.0, mz0],
                     args=(b1_tesla, t1, t2, m0), t_eval=t_eval,
                     method="RK45", rtol=1e-8, atol=1e-10)
    flip_angle_rad = GAMMA_RAD * b1_tesla * tau_s
    return {
        "t_s": sol.t.tolist(),
        "mx": sol.y[0].tolist(),
        "my": sol.y[1].tolist(),
        "mz": sol.y[2].tolist(),
        "flip_angle_deg": math.degrees(flip_angle_rad),
        "mxy_final": float(math.hypot(sol.y[0][-1], sol.y[1][-1])),
        "mz_final": float(sol.y[2][-1]),
    }


def spin_echo(m0=1.0, t2=0.1, te_s=0.05):
    signal = m0 * math.exp(-te_s / t2)
    return {"te_s": te_s, "t2_s": t2, "signal": signal, "m0": m0}


def saturation_recovery(m0=1.0, t1=1.0, tr_s=None):
    if tr_s is None:
        tr_s = [0.1, 0.3, 0.5, 1.0, 2.0, 5.0]
    tr = np.asarray(tr_s, dtype=float) if isinstance(tr_s, (list, tuple)) else np.array([tr_s])
    mz = m0 * (1 - np.exp(-tr / t1))
    return {"tr_s": tr.tolist(), "mz": mz.tolist(), "m0": m0, "t1_s": t1}


def _validate():
    errors = []
    tests_total = 0
    tests_passed = 0

    tests_total += 1
    r = free_precession(m0=1.0, t1=1.0, t2=0.1, mxy0=0.5, mz0=0.2,
                         larmor_hz=0.0, t_array=[0.0])
    if abs(r["mxy_magnitude"][0] - 0.5) < 1e-9 and abs(r["mz"][0] - 0.2) < 1e-9:
        tests_passed += 1
    else:
        errors.append("free_precession: estado inicial incorrecto")

    tests_total += 1
    r = free_precession(m0=1.0, t1=0.5, t2=0.1, mxy0=0.0, mz0=0.0,
                         t_array=[10.0])
    if abs(r["mz"][0] - 1.0) < 1e-3:
        tests_passed += 1
    else:
        errors.append("free_precession: Mz no converge a M0")

    tests_total += 1
    r = rf_pulse(m0=1.0, t1=1000.0, t2=1000.0, b1_tesla=1e-4, mz0=1.0)
    if abs(r["mz_final"]) < 0.02 and abs(r["mxy_final"] - 1.0) < 0.02:
        tests_passed += 1
    else:
        errors.append(f"rf_pulse: pulso 90 no da el resultado esperado ({r})")

    tests_total += 1
    r = spin_echo(m0=1.0, t2=0.1, te_s=0.0)
    if abs(r["signal"] - 1.0) < 1e-9:
        tests_passed += 1
    else:
        errors.append("spin_echo: TE=0 deberia dar senal maxima")

    tests_total += 1
    r = saturation_recovery(m0=1.0, t1=1.0, tr_s=[50.0])
    if abs(r["mz"][0] - 1.0) < 1e-6:
        tests_passed += 1
    else:
        errors.append("saturation_recovery: no converge a M0")

    tests_total += 1
    r = saturation_recovery(m0=1.0, t1=1.0, tr_s=[0.0])
    if abs(r["mz"][0]) < 1e-9:
        tests_passed += 1
    else:
        errors.append("saturation_recovery: TR=0 deberia dar Mz=0")

    return {
        "tool": TOOL_NAME,
        "tests_passed": tests_passed,
        "tests_total": tests_total,
        "errors": errors,
        "status": "PASSED" if tests_passed == tests_total else "FAILED",
        "validation_passed": tests_passed == tests_total,
    }


def run(mode, params=None):
    params = params or {}
    if mode == "free_precession":
        return free_precession(**params)
    if mode == "rf_pulse":
        return rf_pulse(**params)
    if mode == "spin_echo":
        return spin_echo(**params)
    if mode == "saturation_recovery":
        return saturation_recovery(**params)
    if mode == "validate":
        return _validate()
    return {"error": f"modo desconocido: {mode}"}


TOOL_MODES = [
    "free_precession",
    "rf_pulse",
    "spin_echo",
    "saturation_recovery",
    "validate",
]

TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Ecuaciones de Bloch para RM/NMR: precesion libre con relajacion "
        "T1/T2 (analitica), simulacion numerica de pulso RF, senal de "
        "spin-echo y curva de saturation-recovery."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": TOOL_MODES,
                "description": "Modo de calculo (ver docstring de run())",
            },
            "params": {
                "type": "object",
                "description": "Parametros segun el modo (ver docstring de run())",
            },
        },
        "required": ["mode"],
    },
}


def _register():
    try:
        from tool_registry import register_tool
        register_tool(
            TOOL_NAME,
            TOOL_SCHEMA,
            lambda args: run(args.get("mode"), args.get("params", {})),
        )
    except ImportError:
        pass


_register()


if __name__ == "__main__":
    result = run("validate")
    print(json.dumps(result, indent=2, default=str))
    total = result["tests_total"]
    passed = result["tests_passed"]
    if result["validation_passed"]:
        print("→ LISTO PARA DESCARGAR e integrar a octave-mcp/tools/")
    else:
        print(f"→ {total - passed} test(s) fallaron — revisar")
