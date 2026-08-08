#!/usr/bin/env python3
"""
qm_tool.py — Cuántica: resuelve la ecuación de Schrödinger 1D independiente
del tiempo por diferencias finitas (matriz tridiagonal + eig).
"""
import subprocess
import json
import tempfile
import os

QM_TOOL_SCHEMA = {
    "name": "compute_qm_potential_well",
    "description": (
        "Resuelve la ecuación de Schrödinger 1D independiente del tiempo por "
        "diferencias finitas (condiciones de borde de Dirichlet), devolviendo "
        "las energías propias y autofunciones más bajas. Presets: infinite_well "
        "(pozo infinito), finite_well (pozo finito), harmonic_oscillator "
        "(oscilador armónico), o custom (potencial arbitrario V(x))."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "preset": {
                "type": "string",
                "enum": ["infinite_well", "finite_well", "harmonic_oscillator", "custom"],
                "default": "infinite_well",
            },
            "custom_potential": {"type": "string"},
            "well_params": {"type": "object"},
            "x_range": {"type": "array", "items": {"type": "number"}},
            "n_points": {"type": "integer", "default": 400},
            "mass": {"type": "number", "default": 1.0},
            "hbar": {"type": "number", "default": 1.0},
            "n_states": {"type": "integer", "default": 5},
        },
        "required": [],
    },
}

_OCTAVE_TEMPLATE = r"""
hbar = __HBAR__;
m = __MASS__;
xmin = __XMIN__;
xmax = __XMAX__;
N = __NPOINTS__;
n_states = __NSTATES__;

dx = (xmax - xmin) / (N + 1);
x = xmin + dx * (1:N)';

__POTENTIAL__

kin_coef = hbar^2 / (2 * m * dx^2);
main_diag = 2*kin_coef + V;
off_diag = -kin_coef * ones(N-1, 1);
H = diag(main_diag) + diag(off_diag, 1) + diag(off_diag, -1);

[vecs, vals] = eig(H);
evals = diag(vals);
[evals_sorted, idx] = sort(evals);
vecs_sorted = vecs(:, idx);

n_out = min(n_states, N);
energies = evals_sorted(1:n_out);

function s = vec2json(v)
  s = ["[" strjoin(arrayfun(@(z) sprintf("%.6g", z), v(:)', "UniformOutput", false), ",") "]"];
endfunction

printf("{\n");
printf("  \"x\": %s,\n", vec2json(x));
printf("  \"V\": %s,\n", vec2json(V));
printf("  \"energies\": %s,\n", vec2json(energies));
printf("  \"wavefunctions\": [\n");
for k = 1:n_out
  psi = vecs_sorted(:, k);
  psi = psi / sqrt(sum(psi.^2) * dx);
  [~, imax] = max(abs(psi));
  if psi(imax) < 0
    psi = -psi;
  end
  sep = ",";
  if k == n_out
    sep = "";
  end
  printf("    %s%s\n", vec2json(psi), sep);
end
printf("  ]\n");
printf("}\n");
"""


def _potential_code(preset, custom_potential, well_params, mass, hbar):
    wp = well_params or {}
    if preset == "infinite_well":
        return "V = zeros(N, 1);"
    elif preset == "finite_well":
        V0 = wp.get("V0", 50.0)
        width = wp.get("width", 2.0)
        return f"V = {V0} * (abs(x) > {width}/2);"
    elif preset == "harmonic_oscillator":
        omega = wp.get("omega", 1.0)
        return f"V = 0.5 * {mass} * {omega}^2 * x.^2;"
    elif preset == "custom":
        if not custom_potential:
            raise ValueError("preset='custom' requiere 'custom_potential' (expresión Octave en x).")
        return f"V = {custom_potential};\nif isscalar(V)\n  V = V * ones(N,1);\nend\nV = V(:);"
    else:
        raise ValueError(f"preset desconocido: {preset}")


def _default_x_range(preset, well_params):
    wp = well_params or {}
    if preset == "infinite_well":
        L = wp.get("L", 1.0)
        return [0.0, L]
    elif preset == "finite_well":
        width = wp.get("width", 2.0)
        return [-3 * width, 3 * width]
    elif preset == "harmonic_oscillator":
        return [-8.0, 8.0]
    else:
        return [-5.0, 5.0]


def compute_qm_potential_well(
    preset="infinite_well",
    custom_potential=None,
    well_params=None,
    x_range=None,
    n_points=400,
    mass=1.0,
    hbar=1.0,
    n_states=5,
    **kwargs,
):
    if x_range is None:
        x_range = _default_x_range(preset, well_params)
    xmin, xmax = x_range

    potential_code = _potential_code(preset, custom_potential, well_params, mass, hbar)

    octave_code = (
        _OCTAVE_TEMPLATE
        .replace("__HBAR__", repr(hbar))
        .replace("__MASS__", repr(mass))
        .replace("__XMIN__", repr(xmin))
        .replace("__XMAX__", repr(xmax))
        .replace("__NPOINTS__", str(n_points))
        .replace("__NSTATES__", str(n_states))
        .replace("__POTENTIAL__", potential_code)
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".m", delete=False) as f:
        f.write(octave_code)
        script_path = f.name

    try:
        proc = subprocess.run(
            ["octave", "--no-gui", "--quiet", script_path],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Octave error: {proc.stderr.strip()}")
        data = json.loads(proc.stdout)
    finally:
        os.unlink(script_path)

    return {
        "preset": preset,
        "mass": mass,
        "hbar": hbar,
        "x_range": x_range,
        "n_points": n_points,
        "energies": data["energies"],
        "x": data["x"],
        "V": data["V"],
        "wavefunctions": data["wavefunctions"],
        "nota": (
            "energies[k] es la energía del (k+1)-ésimo estado (base 0). "
            "wavefunctions[k] es psi_k(x) normalizada (∫|psi|²dx=1, signo fijado "
            "positivo en el máximo). Para infinite_well con L=1, m=1, hbar=1: "
            "E_n analítico = n²π²/2 (n=1,2,3,...). Para harmonic_oscillator con "
            "omega=1: E_n analítico = n+0.5 (n=0,1,2,...)."
        ),
    }
