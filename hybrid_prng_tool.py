#!/usr/bin/env python3
"""
hybrid_prng_tool.py - Generador PRNG híbrido (middle-square + msws64)
ejecutado en Octave nativo vía run_octave del servidor octave-mcp.

middle-square de von Neumann (1946) está roto como PRNG independiente:
8 ciclos en 4 dígitos, 18.18% de semillas colapsan a cero.
msws64 (Widynski 2017) es un PRNG decente de 64 bits por sí solo.
El híbrido XOR de ambos produce buena distribución estadística sin
depender exclusivamente de un solo mecanismo.

Registrado como tool MCP "hybrid_prng".
"""

from __future__ import annotations

from typing import Any, Dict

HYBRID_PRNG_TOOL_SCHEMA: Dict[str, Any] = {
    "name": "hybrid_prng",
    "description": (
        "Generador PRNG híbrido (middle-square de von Neumann + msws64 de "
        "Widynski 2017) ejecutado en Octave nativo. middle-square por sí solo "
        "está roto (ciclos cortos, colapso a cero); msws64 aporta entropía de "
        "64 bits. El híbrido XOR de ambos produce buena distribución "
        "estadística sin depender de un solo mecanismo. Devuelve coeficiente "
        "chi² de uniformidad, periodo, estado interno y valores de muestra."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "seed": {
                "type": "integer",
                "default": 1234,
                "description": "Semilla inicial (cualquier entero >= 0)",
            },
            "n_samples": {
                "type": "integer",
                "default": 10000,
                "description": "Número de muestras a generar",
            },
            "nbins": {
                "type": "integer",
                "default": 10,
                "description": "Bins para test chi² de uniformidad",
            },
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


def hybrid_prng(
    seed: int = 1234,
    n_samples: int = 10000,
    nbins: int = 10,
) -> Dict[str, Any]:
    from server import run_octave

    script = f"""
function y = ms_next(x)
  s = sprintf('%08d', mod(x^2, 10^8));
  mid = str2double(s(3:6));
  y = mid;
end

function [x, w] = weyl_next(x, w, s)
  w = mod(w + s, 10000);
  s8 = sprintf('%08d', mod(x^2 + w, 10^8));
  x = str2double(s8(3:6));
end

function x = msws64_next(x)
  x = x * 6364136223846793005;
  x = bitxor(x, bitshift(x, 17));
  x = x * 1442695040888963407;
  x = bitxor(x, bitshift(x, 31));
  x = x * 3141592653589793239;
  x = bitxor(x, bitshift(x, 27));
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

%% ---------- middle-square original ----------
seen = false(1, 10000);
cycles = {{}};
n_cycles = 0;
for x0 = 0:9999
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
for x0 = 0:9999
  x = x0;
  for i = 1:50
    x = ms_next(x);
  end
  if x == 0
    zero_sink = zero_sink + 1;
  end
end
zs_rel = zero_sink / 10000;

%% ---------- Weyl ----------
s = {seed % 10000}; w = 0; x = 1234;
trw = []; seenw = false(1, 10000); weyl_period = 0;
for i = 1:100000
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
p1 = 9973; p2 = 9967; M = p1 * p2;
w1 = 0; w2 = 0; x = 1234;
trcrt = []; seen_crt = false(1, 10000); tcr_period = 0;
inv = mod(inv_mod(p1, p2), p2);
for i = 1:100000
  w1 = mod(w1 + s, p1);
  w2 = mod(w2 + s, p2);
  k = mod((w2 - w1) * inv, p2);
  w = mod(w1 + p1 * k, M);
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

%% ---------- Hybrid PRNG ----------
hybrid_seed({seed});
n = {n_samples};
samples = zeros(1, n);
doubles = zeros(1, n);
for i = 1:n
  r = hybrid_prng_next();
  samples(i) = r;
  doubles(i) = hybrid_prng_next_double();
end

%% ---------- Chi^2 ----------
chi2_bins = {nbins};
chi2_samples = {n_samples};
expected = chi2_samples / chi2_bins;
counts = zeros(1, chi2_bins);
for i = 1:chi2_samples
  b = floor(samples(i) / UINT64_MAX * chi2_bins) + 1;
  if b > chi2_bins, b = chi2_bins; end
  counts(b) = counts(b) + 1;
end
chi2 = sum((counts - expected).^2 ./ expected);

mean_d = mean(doubles);

r = struct('middle_square_cycles', n_cycles, ...
           'middle_square_zero_sink', zs_rel, ...
           'weyl_period', weyl_period, ...
           'tcr_period', tcr_period, ...
           'tcr_modulus_M', M, ...
           'msws64_period', 0, ...
           'chi2', chi2, ...
           'chi2_bins', chi2_bins, ...
           'chi2_samples', chi2_samples, ...
           'mean_double', mean_d, ...
           'first_values', samples(1:min(10, chi2_samples)));
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
    name="hybrid_prng",
    schema=HYBRID_PRNG_TOOL_SCHEMA,
    handler=lambda args: hybrid_prng(**args),
)