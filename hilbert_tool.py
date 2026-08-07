#!/usr/bin/env python3
"""
hilbert_tool.py — Transformada de Hilbert para series no estacionarias.

Expone compute_hilbert_transform(**kwargs) y HILBERT_TOOL_SCHEMA,
siguiendo el mismo patrón que lyapunov_tool.py / stiff_ode_tool.py / bifurcation_tool.py.
"""
import subprocess
import json
import tempfile
import os

HILBERT_TOOL_SCHEMA = {
    "name": "compute_hilbert_transform",
    "description": (
        "Calcula la transformada de Hilbert de una serie temporal no estacionaria "
        "y extrae envolvente (amplitud instantánea), fase instantánea y frecuencia "
        "instantánea vía la señal analítica. Incluye presets sintéticos (am_chirp, "
        "fm_chirp, noisy_am) para validar el método, o acepta una señal custom "
        "(ej. mediciones de campo eléctrico atmosférico)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "preset": {
                "type": "string",
                "enum": ["am_chirp", "fm_chirp", "noisy_am", "custom"],
                "default": "am_chirp",
                "description": (
                    "am_chirp: portadora con amplitud moduladora conocida (valida envolvente). "
                    "fm_chirp: frecuencia instantánea creciente conocida (valida fase/frecuencia). "
                    "noisy_am: como am_chirp + ruido gaussiano (robustez). "
                    "custom: usa la señal provista en 'signal'."
                ),
            },
            "signal": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Solo si preset='custom'. Serie temporal real, muestreada uniformemente.",
            },
            "fs": {
                "type": "number",
                "default": 1000.0,
                "description": "Frecuencia de muestreo en Hz.",
            },
            "duration": {
                "type": "number",
                "default": 1.0,
                "description": "Duración en segundos, solo para presets sintéticos.",
            },
            "detrend": {
                "type": "boolean",
                "default": True,
                "description": "Si true, remueve la media antes de calcular la señal analítica.",
            },
            "n_output_points": {
                "type": "integer",
                "default": 200,
                "description": "Número de puntos a devolver (submuestreo uniforme para no saturar la respuesta).",
            },
        },
        "required": [],
    },
}

_OCTAVE_TEMPLATE = r"""
pkg load signal;

fs = __FS__;
detrend_flag = __DETREND__;

__SIGNAL_GEN__

if detrend_flag
  x = x - mean(x);
end

n = length(x);
t = (0:n-1) / fs;

xa = hilbert(x(:));
env = abs(xa);
phase_raw = angle(xa);
phase_unwrapped = unwrap(phase_raw);

inst_freq = zeros(n,1);
inst_freq(2:end-1) = (phase_unwrapped(3:end) - phase_unwrapped(1:end-2)) / (2/fs) / (2*pi);
inst_freq(1) = inst_freq(2);
inst_freq(end) = inst_freq(end-1);

result.t = t(:);
result.x = x(:);
result.envelope = env;
result.inst_phase = phase_unwrapped;
result.inst_freq = inst_freq;

function s = vec2json(v)
  s = ["[" strjoin(arrayfun(@(z) sprintf("%.6g", z), v(:)', "UniformOutput", false), ",") "]"];
endfunction

printf("{\n");
printf("  \"t\": %s,\n", vec2json(result.t));
printf("  \"x\": %s,\n", vec2json(result.x));
printf("  \"envelope\": %s,\n", vec2json(result.envelope));
printf("  \"inst_phase\": %s,\n", vec2json(result.inst_phase));
printf("  \"inst_freq\": %s\n", vec2json(result.inst_freq));
printf("}\n");
"""

_PRESETS = {
    "am_chirp": (
        "f0 = 50; fm = 3; t = (0:round(__N__)-1)/__PFS__;\n"
        "x = (1 + 0.5*sin(2*pi*fm*t)) .* sin(2*pi*f0*t);\n"
    ),
    "fm_chirp": (
        "f0 = 20; f1 = 80; t = (0:round(__N__)-1)/__PFS__; dur = __DUR__;\n"
        "k = (f1-f0)/dur;\n"
        "x = sin(2*pi*(f0*t + 0.5*k*t.^2));\n"
    ),
    "noisy_am": (
        "f0 = 50; fm = 3; t = (0:round(__N__)-1)/__PFS__;\n"
        "x = (1 + 0.5*sin(2*pi*fm*t)) .* sin(2*pi*f0*t);\n"
        "x = x + 0.05*randn(size(x));\n"
    ),
}


def _downsample(vals, n_out):
    n = len(vals)
    if n_out is None or n_out >= n:
        return vals
    idx = [round(i * (n - 1) / (n_out - 1)) for i in range(n_out)]
    seen = []
    for i in idx:
        if not seen or seen[-1] != i:
            seen.append(i)
    return [vals[i] for i in seen]


def compute_hilbert_transform(
    preset="am_chirp",
    signal=None,
    fs=1000.0,
    duration=1.0,
    detrend=True,
    n_output_points=200,
    **kwargs,
):
    n_samples = int(round(fs * duration))

    if preset == "custom":
        if not signal:
            raise ValueError("preset='custom' requiere el parámetro 'signal' (lista de números).")
        signal_gen = "x = [" + ",".join(f"{v:.10g}" for v in signal) + "];\n"
    else:
        if preset not in _PRESETS:
            raise ValueError(f"preset desconocido: {preset}")
        signal_gen = (
            _PRESETS[preset]
            .replace("__N__", str(n_samples))
            .replace("__PFS__", repr(fs))
            .replace("__DUR__", repr(duration))
        )

    octave_code = (
        _OCTAVE_TEMPLATE
        .replace("__FS__", repr(fs))
        .replace("__DETREND__", "true" if detrend else "false")
        .replace("__SIGNAL_GEN__", signal_gen)
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

    out = {
        "preset": preset,
        "fs": fs,
        "n_samples": len(data["x"]),
        "t": _downsample(data["t"], n_output_points),
        "x": _downsample(data["x"], n_output_points),
        "envelope": _downsample(data["envelope"], n_output_points),
        "inst_phase": _downsample(data["inst_phase"], n_output_points),
        "inst_freq": _downsample(data["inst_freq"], n_output_points),
        "nota": (
            "envelope = amplitud instantánea |x_a(t)|. inst_freq = frecuencia "
            "instantánea en Hz vía derivada de la fase desenvuelta. Para "
            "am_chirp/fm_chirp, comparar envelope/inst_freq contra los valores "
            "conocidos (f0, fm o f0->f1) confirma la implementación."
        ),
    }
    return out


if __name__ == "__main__":
    for p in ["am_chirp", "fm_chirp", "noisy_am"]:
        r = compute_hilbert_transform(preset=p, fs=500, duration=0.5, n_output_points=10)
        env = r["envelope"]
        freq = r["inst_freq"]
        print(f"--- {p} ---")
        print(f"  envelope[3:7] = {[round(e,3) for e in env[3:7]]}")
        print(f"  inst_freq[3:7] = {[round(fr,2) for fr in freq[3:7]]}")
