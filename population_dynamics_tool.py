"""
population_dynamics_tool.py

Dinamica de poblaciones: Lotka-Volterra (depredador-presa) y crecimiento
logistico. Relevante para modelar competencia/capacidad de carga en el
proyecto de cultivo de kelp (Macrocystis pyrifera) usando infraestructura
de longline existente de pelillo (Gracilaria chilensis) en Chiloe --
interaccion entre especies, capacidad de carga del longline, competencia
por espacio/nutrientes.

Via Octave ode45 (mismo patron que stiff_ode_tool, lyapunov_tool, etc).

Validacion: Lotka-Volterra tiene un equilibrio no trivial conocido
analiticamente (x*=c/d, y*=a/b) al que converge el PROMEDIO temporal de la
solucion oscilante (propiedad clasica del sistema, no un punto fijo
estable sino un centro). Crecimiento logistico tiene solucion analitica
cerrada exacta.
"""
import subprocess
import tempfile
import os
import math

POPULATION_DYNAMICS_SCHEMA = {
    "name": "compute_population_dynamics",
    "description": (
        "Dinamica de poblaciones via Octave: lotka_volterra (depredador-presa, "
        "parametros a,b,c,d), logistic_growth (crecimiento con capacidad de "
        "carga K, comparado contra solucion analitica exacta). Relevante "
        "para modelar competencia/capacidad de carga en cultivo de especies "
        "(ej. kelp en infraestructura de longline)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["lotka_volterra", "logistic_growth"], "default": "lotka_volterra"},
            "a": {"type": "number", "default": 1.0, "description": "LV: tasa crecimiento presa"},
            "b": {"type": "number", "default": 0.1, "description": "LV: tasa depredacion"},
            "c": {"type": "number", "default": 1.5, "description": "LV: tasa muerte depredador"},
            "d": {"type": "number", "default": 0.075, "description": "LV: tasa conversion presa->depredador"},
            "x0": {"type": "number", "default": 10.0, "description": "poblacion inicial presa/especie"},
            "y0": {"type": "number", "default": 5.0, "description": "LV: poblacion inicial depredador"},
            "r": {"type": "number", "default": 0.5, "description": "logistic: tasa de crecimiento intrinseca"},
            "K": {"type": "number", "default": 100.0, "description": "logistic: capacidad de carga"},
            "t_max": {"type": "number", "default": 50.0},
            "n_points": {"type": "integer", "default": 50, "description": "puntos de salida en la trayectoria"},
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


def compute_population_dynamics(mode="lotka_volterra", a=1.0, b=0.1, c=1.5, d=0.075,
                                 x0=10.0, y0=5.0, r=0.5, K=100.0, t_max=50.0, n_points=50):
    if mode == "lotka_volterra":
        code = f"""
a={a}; b={b}; c={c}; d={d};
f = @(t,s) [a*s(1)-b*s(1)*s(2); -c*s(2)+d*s(1)*s(2)];
tspan = linspace(0,{t_max},{n_points});
[t,S] = ode45(f, tspan, [{x0};{y0}]);
printf("%.8f ", S');
"""
        out, err = _run_octave(code)
        if out is None:
            return {"error": "octave fallo", "stderr": err}
        vals = [float(v) for v in out.split()]
        pairs = [(vals[i], vals[i + 1]) for i in range(0, len(vals), 2)]
        x_vals = [p[0] for p in pairs]
        y_vals = [p[1] for p in pairs]
        x_eq, y_eq = c / d, a / b
        x_mean, y_mean = sum(x_vals) / len(x_vals), sum(y_vals) / len(y_vals)
        return {
            "mode": "lotka_volterra", "params": {"a": a, "b": b, "c": c, "d": d},
            "initial": [x0, y0], "equilibrio_analitico": [round(x_eq, 4), round(y_eq, 4)],
            "promedio_temporal_simulado": [round(x_mean, 4), round(y_mean, 4)],
            "trajectory_sample": [{"presa": round(x_vals[i], 4), "depredador": round(y_vals[i], 4)} for i in range(0, len(x_vals), max(1, len(x_vals) // 10))],
            "nota": (
                "Lotka-Volterra no tiene un punto fijo estable -- el sistema oscila "
                "indefinidamente alrededor del equilibrio [c/d, a/b]. El PROMEDIO "
                "temporal de la trayectoria converge a ese equilibrio (propiedad "
                "clasica del sistema), no la trayectoria misma."
            ),
        }

    elif mode == "logistic_growth":
        code = f"""
r={r}; K={K};
f = @(t,x) r*x*(1-x/K);
tspan = linspace(0,{t_max},{n_points});
[t,X] = ode45(f, tspan, {x0});
printf("%.8f ", X);
"""
        out, err = _run_octave(code)
        if out is None:
            return {"error": "octave fallo", "stderr": err}
        x_vals = [float(v) for v in out.split()]
        t_vals = [i * t_max / (n_points - 1) for i in range(n_points)]
        x_analytic = [K / (1 + ((K - x0) / x0) * math.exp(-r * ti)) for ti in t_vals]
        max_err = max(abs(a - b) for a, b in zip(x_vals, x_analytic))
        return {
            "mode": "logistic_growth", "params": {"r": r, "K": K, "x0": x0},
            "max_error_vs_analytic": round(max_err, 8),
            "trajectory_sample": [round(x_vals[i], 4) for i in range(0, len(x_vals), max(1, len(x_vals) // 10))],
            "poblacion_final": round(x_vals[-1], 4),
            "nota": "solucion analitica: x(t) = K / (1 + ((K-x0)/x0)*exp(-r*t))",
        }

    else:
        return {"error": f"mode desconocido: {mode}"}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_population_dynamics("lotka_volterra"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_population_dynamics("logistic_growth"), indent=2, ensure_ascii=False))
