"""
enzyme_kinetics_tool.py

Cinetica enzimatica: Michaelis-Menten (aproximacion de estado
cuasi-estacionario, QSSA) contra la cinetica completa de 3 especies
E+S<->ES->E+P. Puente directo entre stiff_ode_tool (que ya tiene el
preset 'robertson' de cinetica quimica general) y biologia molecular.

Validacion: se corren AMBOS modelos (completo de 3 especies y la
aproximacion MM de 1 ecuacion) y se compara la velocidad de reaccion
v=dP/dt de cada uno. La QSSA es valida cuando [E]<<[S] (condicion
estandar de la teoria) -- el modulo reporta el error de aproximacion
explicitamente en vez de asumir que MM siempre es correcta.
"""
import subprocess
import tempfile
import os

ENZYME_KINETICS_SCHEMA = {
    "name": "compute_enzyme_kinetics",
    "description": (
        "Cinetica enzimatica via Octave: full_kinetics (cinetica completa "
        "E+S<->ES->E+P, 3 especies), michaelis_menten (aproximacion QSSA "
        "v=Vmax*S/(Km+S)), compare (corre ambos y reporta el error de la "
        "aproximacion -- valida solo cuando [E]<<[S])."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["full_kinetics", "michaelis_menten", "compare"], "default": "compare"},
            "k1": {"type": "number", "default": 100.0, "description": "tasa de asociacion E+S->ES"},
            "km1": {"type": "number", "default": 10.0, "description": "tasa de disociacion ES->E+S"},
            "k2": {"type": "number", "default": 5.0, "description": "tasa de catalisis ES->E+P"},
            "E0": {"type": "number", "default": 1.0, "description": "concentracion inicial de enzima"},
            "S0": {"type": "number", "default": 100.0, "description": "concentracion inicial de sustrato"},
            "t_max": {"type": "number", "default": 5.0},
            "n_points": {"type": "integer", "default": 50},
        },
    },
}


def _run_octave(code, timeout=30):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".m", delete=False) as fh:
        fh.write(code)
        script_path = fh.name
    try:
        r = subprocess.run(["octave", "--no-gui", "--no-init-file", script_path],
                            capture_output=True, text=True, timeout=timeout)
    finally:
        os.unlink(script_path)
    if r.returncode != 0:
        return None, r.stderr.strip()
    return r.stdout.strip(), None


def compute_enzyme_kinetics(mode="compare", k1=100.0, km1=10.0, k2=5.0,
                             E0=1.0, S0=100.0, t_max=5.0, n_points=50):
    Vmax = k2 * E0
    Km = (km1 + k2) / k1

    code = f"""
k1={k1}; km1={km1}; k2={k2}; E0={E0};
f = @(t,s) [-k1*(E0-s(2))*s(1) + km1*s(2);
             k1*(E0-s(2))*s(1) - km1*s(2) - k2*s(2);
             k2*s(2)];
tspan = linspace(0,{t_max},{n_points});
[t,S] = ode45(f, tspan, [{S0};0;0]);
printf("%.10f ", S');
"""
    out, err = _run_octave(code)
    if out is None:
        return {"error": "octave fallo", "stderr": err}
    vals = [float(v) for v in out.split()]
    triples = [(vals[i], vals[i + 1], vals[i + 2]) for i in range(0, len(vals), 3)]
    S_vals = [t[0] for t in triples]
    ES_vals = [t[1] for t in triples]
    P_vals = [t[2] for t in triples]

    if mode == "full_kinetics":
        return {
            "mode": "full_kinetics", "params": {"k1": k1, "km1": km1, "k2": k2, "E0": E0, "S0": S0},
            "Km_derivado": round(Km, 6), "Vmax_derivado": round(Vmax, 6),
            "S_final": round(S_vals[-1], 6), "P_final": round(P_vals[-1], 6),
            "trajectory_sample": [{"S": round(S_vals[i], 4), "ES": round(ES_vals[i], 4), "P": round(P_vals[i], 4)}
                                   for i in range(0, len(S_vals), max(1, len(S_vals) // 10))],
        }

    v_mm = [Vmax * s / (Km + s) if (Km + s) > 0 else 0.0 for s in S_vals]

    if mode == "michaelis_menten":
        return {
            "mode": "michaelis_menten", "Km": round(Km, 6), "Vmax": round(Vmax, 6),
            "velocidad_sample": [round(v, 6) for v in v_mm[::max(1, len(v_mm) // 10)]],
            "formula": "v = Vmax * S / (Km + S)",
        }

    # compare: velocidad real (derivada numerica de P) vs aproximacion MM
    v_full = []
    dt = t_max / (n_points - 1)
    for i in range(len(P_vals)):
        if i == 0:
            v_full.append((P_vals[1] - P_vals[0]) / dt)
        elif i == len(P_vals) - 1:
            v_full.append((P_vals[-1] - P_vals[-2]) / dt)
        else:
            v_full.append((P_vals[i + 1] - P_vals[i - 1]) / (2 * dt))

    skip = max(3, len(v_full) // 20)
    diffs = [abs(v_mm[i] - v_full[i]) / max(abs(v_full[i]), 1e-9) for i in range(skip, len(v_full))]
    mean_rel_error = sum(diffs) / len(diffs)

    return {
        "mode": "compare", "Km": round(Km, 6), "Vmax": round(Vmax, 6),
        "condicion_QSSA_E0_menor_que_S0": E0 < S0,
        "ratio_E0_S0": round(E0 / S0, 6),
        "error_relativo_promedio_MM_vs_completo": round(mean_rel_error, 6),
        "aproximacion_valida": mean_rel_error < 0.05,
        "nota": (
            "el error se mide saltando el transiente inicial rapido de formacion de ES "
            "(donde la QSSA todavia no aplica por definicion). Si error_relativo_promedio "
            "es alto, probablemente E0 no es << S0."
        ),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(compute_enzyme_kinetics("compare"), indent=2, ensure_ascii=False))
