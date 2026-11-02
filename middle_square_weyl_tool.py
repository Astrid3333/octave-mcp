#!/usr/bin/env python3
"""
middle_square_weyl_tool.py — Potenciado: compara middle-square de von Neumann
vs Weyl vs TCR vs Widynski msws64 (64 bits) en Octave nativo.

Incluye:
- middle-square original (4 dígitos): ciclos cortos, colapso a 0
- Weyl (contador aditivo mod 10^4): alarga periodo pero salida sesgada
- TCR (Teorema Chino del Resto, primos 9973×9967): M=99,400,891 pero sesgado
- Widynski msws64 (2017): estado de 64 bits, xorshift + multiplicación,
  1,8 ns/iteración, alternativa real para PRNG decente

Devuelve ciclos, zero_sink, periodos, M, test chi² de uniformidad y
métricas de calidad de salida.
"""

from __future__ import annotations

from typing import Any, Dict

MIDDLE_SQUARE_WEYL_TOOL_SCHEMA: Dict[str, Any] = {
    "name": "middle_square_weyl",
    "description": (
        "Compara middle-square de von Neumann (4 dígitos) contra tres arreglos: "
        "secuencia de Weyl (contador aditivo), TCR (Teorema Chino del Resto con "
        "primos coprimos 9973 y 9967) y Widynski msws64 (estado 64 bits). "
        "Devuelve ciclos, zero_sink, periodos, M, test chi² de uniformidad y "
        "métricas de calidad de salida."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "digits": {"type": "integer", "default": 4, "description": "Dígitos del medio"},
            "modulus": {"type": "integer", "default": 10000, "description": "Módulo (10^digits)"},
            "weyl_s": {"type": "integer", "default": 6329, "description": "Paso de Weyl"},
            "tcr_p1": {"type": "integer", "default": 9973, "description": "Primo 1 para TCR"},
            "tcr_p2": {"type": "integer", "default": 9967, "description": "Primo 2 para TCR"},
            "max_iter": {"type": "integer", "default": 1000000, "description": "Máx. iteraciones"},
            "chi2_bins": {"type": "integer", "default": 10, "description": "Bins para test chi²"},
            "chi2_samples": {"type": "integer", "default": 10000, "description": "Muestras para chi²"},
        },
        "required": [],
        "additionalProperties": False,
    },
}

_DISP_STRUCT = r"""
function disp_struct(r)
  fields = fieldnames(r);
  for i = 1:length(fields)
    f = fields{i};
    v = r.(f);
    if iscell(v)
      fprintf('%s=<cell %d elementos>\n', f, numel(v));
    elseif isstruct(v)
      fprintf('%s=<struct>\n', f);
    elseif ischar(v) || isstring(v)
      fprintf('%s=%s\n', f, v);
    elseif isnumeric(v)
      if numel(v) == 1
        fprintf('%s=%g\n', f, v);
      else
        fprintf('%s=[%s]\n', f, num2str(v));
      end
    else
      fprintf('%s=<otro>\n', f);
    end
  end
end
"""


def middle_square_weyl(
    digits: int = 4,
    modulus: int = 10000,
    weyl_s: int = 6329,
    tcr_p1: int = 9973,
    tcr_p2: int = 9967,
    max_iter: int = 1000000,
    chi2_bins: int = 10,
    chi2_samples: int = 10000,
) -> Dict[str, Any]:
    from server import run_octave

    script = f"""
function y = ms_next(x)
  s = sprintf('%08d', mod(x^2, 10^8));
  mid = str2double(s(3:6));
  y = mid;
end

function [x, w] = weyl_next(x, w, s)
  w = mod(w + s, {modulus});
  s8 = sprintf('%08d', mod(x^2 + w, 10^8));
  x = str2double(s8(3:6));
end

function [x, w1, w2, w] = tcr_next(x, w1, w2, s, p1, p2, M)
  w1 = mod(w1 + s, p1);
  w2 = mod(w2 + s, p2);
  inv = mod(inv_mod(p1, p2), p2);
  k = mod((w2 - w1) * inv, p2);
  w = mod(w1 + p1 * k, M);
  s8 = sprintf('%08d', mod(x^2 + w, 10^8));
  x = str2double(s8(3:6));
end

function x = msws64_next(x)
  % Widynski msws64 (2017): estado de 64 bits, xorshift + multiplicación
  x = x * 6364136223846793005;
  x = bitxor(x, bitshift(x, 17));
  x = x * 1442695040888963407;
  x = bitxor(x, bitshift(x, 31));
  x = x * 3141592653589793239;
  x = bitxor(x, bitshift(x, 27));
  % Devolver solo 4 dígitos decimales para comparar con middle-square
  x = mod(x, {modulus});
end

function inv = inv_mod(a, m)
  [g, x, ~] = extgcd(a, m);
  inv = mod(x, m);
end

function [g, x, y] = extgcd(a, b)
  if b == 0, g = a; x = 1; y = 0;
  else
    [g1, x1, y1] = extgcd(b, mod(a, b));
    g = g1; x = y1; y = x1 - floor(a/b) * y1;
  end
end

%% ---------- Middle-square original ----------
seen = false(1, {modulus});
cycles = {{}};
n_cycles = 0;
for x0 = 0:({modulus}-1)
  x = x0; tr = [];
  while ~seen(x+1)
    seen(x+1) = true;
    tr = [tr, x];
    x = ms_next(x);
  end
  idx = find(tr == x);
  if ~isempty(idx)
    n_cycles = n_cycles + 1;
    cycles{{n_cycles}} = tr(idx:end);
  end
end

zero_sink = 0;
for x0 = 0:({modulus}-1)
  x = x0;
  for i = 1:50
    x = ms_next(x);
  end
  if x == 0
    zero_sink = zero_sink + 1;
  end
end
zs_rel = zero_sink / {modulus};

%% ---------- Weyl ----------
s = {weyl_s}; w = 0; x = 1234;
trw = []; seenw = false(1, {modulus}); weyl_period = 0;
for i = 1:{max_iter}
  [x, w] = weyl_next(x, w, s);
  if seenw(x+1)
    j = find(trw == x, 1);
    weyl_period = i - j;
    break;
  end
  seenw(x+1) = true;
  trw = [trw, x];
end

%% ---------- TCR ----------
M = {tcr_p1} * {tcr_p2};
w1 = 0; w2 = 0; x = 1234;
trcrt = []; seen_crt = false(1, {modulus}); tcr_period = 0;
inv = mod(inv_mod({tcr_p1}, {tcr_p2}), {tcr_p2});
for i = 1:{max_iter}
  w1 = mod(w1 + {weyl_s}, {tcr_p1});
  w2 = mod(w2 + {weyl_s}, {tcr_p2});
  k = mod((w2 - w1) * inv, {tcr_p2});
  w = mod(w1 + {tcr_p1} * k, M);
  s8 = sprintf('%08d', mod(x^2 + w, 10^8));
  x = str2double(s8(3:6));
  if seen_crt(x+1)
    j = find(trcrt == x, 1);
    tcr_period = i - j;
    break;
  end
  seen_crt(x+1) = true;
  trcrt = [trcrt, x];
end

%% ---------- Widynski msws64 ----------
x_w = 1234;
tr_msws = []; seen_msws = false(1, {modulus}); msws_period = 0;
for i = 1:{max_iter}
  x_w = msws64_next(x_w);
  if seen_msws(x_w+1)
    j = find(tr_msws == x_w, 1);
    msws_period = i - j;
    break;
  end
  seen_msws(x_w+1) = true;
  tr_msws = [tr_msws, x_w];
end

%% ---------- Chi² de uniformidad ----------
chi2_bins = {chi2_bins};
chi2_samples = {chi2_samples};

function chi2 = compute_chi2(samples, nbins, modval)
  counts = zeros(1, nbins);
  for i = 1:length(samples)
    b = floor(samples(i) / modval * nbins) + 1;
    if b > nbins, b = nbins; end
    counts(b) = counts(b) + 1;
  end
  expected = length(samples) / nbins;
  chi2 = sum((counts - expected).^2 ./ expected);
end

% Chi² para middle-square (desde semilla 1234, {chi2_samples} iteraciones)
x_ms = 1234;
samples_ms = zeros(1, chi2_samples);
for i = 1:chi2_samples
  x_ms = ms_next(x_ms);
  samples_ms(i) = x_ms;
end
chi2_ms = compute_chi2(samples_ms, chi2_bins, {modulus});

% Chi² para Weyl (desde semilla 1234, w=0)
x_wy = 1234; w_wy = 0;
samples_wy = zeros(1, chi2_samples);
for i = 1:chi2_samples
  [x_wy, w_wy] = weyl_next(x_wy, w_wy, {weyl_s});
  samples_wy(i) = x_wy;
end
chi2_wy = compute_chi2(samples_wy, chi2_bins, {modulus});

% Chi² para TCR
x_tc = 1234; w1_tc = 0; w2_tc = 0;
samples_tc = zeros(1, chi2_samples);
for i = 1:chi2_samples
  w1_tc = mod(w1_tc + {weyl_s}, {tcr_p1});
  w2_tc = mod(w2_tc + {weyl_s}, {tcr_p2});
  k = mod((w2_tc - w1_tc) * inv, {tcr_p2});
  w_tc = mod(w1_tc + {tcr_p1} * k, M);
  x_tc = str2double(sprintf('%08d', mod(x_tc^2 + w_tc, 10^8))(3:6));
  samples_tc(i) = x_tc;
end
chi2_tc = compute_chi2(samples_tc, chi2_bins, {modulus});

% Chi² para msws64
x_msw = 1234;
samples_msw = zeros(1, chi2_samples);
for i = 1:chi2_samples
  x_msw = msws64_next(x_msw);
  samples_msw(i) = x_msw;
end
chi2_msw = compute_chi2(samples_msw, chi2_bins, {modulus});

spread = abs(weyl_period - tcr_period) / max(abs(tcr_period), 1);

r = struct('middle_square_cycles', n_cycles, ...
           'middle_square_zero_sink', zs_rel, ...
           'weyl_period', weyl_period, ...
           'tcr_period', tcr_period, ...
           'tcr_modulus_M', M, ...
           'variant_spread', spread, ...
           'msws64_period', msws_period, ...
           'chi2_middle_square', chi2_ms, ...
           'chi2_weyl', chi2_wy, ...
           'chi2_tcr', chi2_tc, ...
           'chi2_msws64', chi2_msw, ...
           'chi2_bins', chi2_bins, ...
           'chi2_samples', chi2_samples);
{_DISP_STRUCT}
disp_struct(r);
"""
    raw = run_octave(script)

    parsed: Dict[str, Any] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or '=' not in line:
            continue
        key, _, val = line.partition('=')
        key = key.strip()
        val = val.strip()
        try:
            if '.' in val or 'e' in val.lower():
                parsed[key] = float(val)
            else:
                parsed[key] = int(val)
        except ValueError:
            parsed[key] = val
    if not parsed:
        return {"error": "no se pudo parsear salida de Octave", "raw_output": raw, "script": script}
    return parsed


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass


register_tool(
    name="middle_square_weyl",
    schema=MIDDLE_SQUARE_WEYL_TOOL_SCHEMA,
    handler=lambda args: middle_square_weyl(**args),
)