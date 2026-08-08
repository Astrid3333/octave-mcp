#!/usr/bin/env python3
"""
nuclear_decay_tool.py — Cadenas de decaimiento nuclear (ecuaciones de Bateman)
resueltas por integración numérica en Octave (ode45), en forma matricial
dN/dt = A N, con A tridiagonal-inferior: A[i][i]=-lambda_i, A[i][i-1]=lambda_{i-1}.

Nota sobre stable_last: NUNCA se fuerza lambda=0 en el último isótopo
trackeado. stable_last=True solo significa que no seguimos la cadena más
allá de ese isótopo (no sabemos ni nos importa a qué decae después) — pero
su propia N sigue decayendo con su propia vida media. Forzar lambda=0 ahí
rompe el equilibrio secular físico (ver bug corregido: antes Ba-137m nunca
alcanzaba equilibrio con Cs-137, quedaba acumulando indefinidamente).
"""
import subprocess
import tempfile
import os
import math

NUCLEAR_DECAY_SCHEMA = {
    "name": "compute_nuclear_decay_chain",
    "description": (
        "Resuelve una cadena de decaimiento nuclear (ecuaciones de Bateman) "
        "integrando numéricamente dN_i/dt = lambda_{i-1} N_{i-1} - lambda_i N_i "
        "para una secuencia de isótopos, vía ode45 en Octave. Presets: "
        "cs137_ba137m, sr90_y90, o custom vía 'chain' "
        "[{'name','half_life_s','initial_N'}, ...]. Devuelve N(t) y actividad "
        "(Bq relativo, lambda*N) por isótopo. stable_last=True (default) "
        "significa que no se sigue la cadena más allá del último isótopo "
        "listado, pero su lambda NUNCA se anula — su N sigue decayendo con su "
        "propia vida media, permitiendo alcanzar equilibrio secular."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "preset": {
                "type": "string",
                "enum": ["cs137_ba137m", "sr90_y90", "custom"],
                "default": "cs137_ba137m"
            },
            "chain": {
                "type": "array",
                "description": "Solo si preset='custom': [{'name':str,'half_life_s':float,'initial_N':float}]"
            },
            "t_max": {
                "type": "number",
                "description": "Tiempo máximo en segundos. Si se omite, se estima como 10x la vida media más larga."
            },
            "n_points": {"type": "integer", "default": 300},
            "stable_last": {"type": "boolean", "default": True},
        },
    },
}

# Vidas medias en segundos (fuente: valores estándar de física nuclear)
PRESETS = {
    "cs137_ba137m": [
        {"name": "Cs-137",  "half_life_s": 30.17 * 365.25 * 86400, "initial_N": 1.0},
        {"name": "Ba-137m", "half_life_s": 2.552 * 60,             "initial_N": 0.0},
    ],
    "sr90_y90": [
        {"name": "Sr-90", "half_life_s": 28.79 * 365.25 * 86400, "initial_N": 1.0},
        {"name": "Y-90",  "half_life_s": 64.0 * 3600,            "initial_N": 0.0},
    ],
}


def _half_life_to_lambda(t_half_s):
    if t_half_s <= 0:
        raise ValueError("half_life_s debe ser > 0")
    return math.log(2) / t_half_s


def compute_nuclear_decay_chain(preset="cs137_ba137m", chain=None, t_max=None,
                                 n_points=300, stable_last=True, timeout=60):
    if preset == "custom":
        if not chain:
            return {"error": "preset='custom' requiere 'chain' con al menos un isótopo"}
        isotopes = chain
    else:
        if preset not in PRESETS:
            return {"error": f"preset desconocido: {preset}. Opciones: {list(PRESETS.keys())} + 'custom'"}
        isotopes = PRESETS[preset]

    n = len(isotopes)
    names = [iso["name"] for iso in isotopes]
    lambdas = [_half_life_to_lambda(iso["half_life_s"]) for iso in isotopes]
    N0 = [iso.get("initial_N", 0.0) for iso in isotopes]

    if t_max is None:
        t_max = 10.0 / min(lambdas)  # 10 vidas medias del isótopo más lento (padre)

    # A[i][i] = -lambda_i ; A[i][i-1] = lambda_{i-1}. stable_last no toca
    # esta matriz en absoluto -- lambdas siempre completas, nunca zero.
    octave_code = f"""
n = {n};
lambdas = [{", ".join(f"{l:.10e}" for l in lambdas)}];
N0 = [{", ".join(f"{v:.10e}" for v in N0)}]';
A = zeros(n, n);
for i = 1:n
  A(i,i) = -lambdas(i);
  if i > 1
    A(i,i-1) = lambdas(i-1);
  end
end
tspan = linspace(0, {t_max:.10e}, {n_points});
f = @(t, N) A * N;
[t, N] = ode45(f, tspan, N0);
out = [t, N];
printf("%.10e ", out');
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".m", delete=False) as fh:
        fh.write(octave_code)
        script_path = fh.name
    try:
        r = subprocess.run(["octave", "--no-gui", "--no-init-file", script_path],
                            capture_output=True, text=True, timeout=timeout)
    finally:
        os.unlink(script_path)

    if r.returncode != 0:
        return {"error": "octave failed", "stderr": r.stderr.strip()}

    try:
        vals = [float(x) for x in r.stdout.split()]
    except ValueError:
        return {"error": "no se pudo parsear salida de Octave", "raw_head": r.stdout[:300]}

    ncols = n + 1
    if len(vals) % ncols != 0:
        return {"error": "dimension mismatch parseando salida", "got": len(vals), "expected_cols": ncols}

    rows = [vals[i:i + ncols] for i in range(0, len(vals), ncols)]
    t_vals = [row[0] for row in rows]
    N_series = {names[i]: [row[i + 1] for row in rows] for i in range(n)}
    activity = {names[i]: [lambdas[i] * v for v in N_series[names[i]]] for i in range(n)}

    return {
        "preset": preset,
        "isotopes": names,
        "half_lives_s": [iso["half_life_s"] for iso in isotopes],
        "lambdas_per_s": lambdas,
        "stable_last": stable_last,
        "t_max_s": t_max,
        "t": t_vals,
        "N": N_series,
        "activity": activity,
    }
