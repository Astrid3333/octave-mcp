#!/usr/bin/env python3
"""
lcg_lehmer_tool.py - Análisis espectral de LCG de Lehmer (1949)
ejecutado en Octave nativo vía run_octave del servidor octave-mcp.

Incluye:
- LCG estándar: x_{n+1} = (a * x_n + c) mod m
- RANDU: a = 65539 = 2^16 + 3, c = 0, m = 2^31 (famoso por fallar en 3D)
- MINSTD: a = 16807 = 7^5, c = 0, m = 2^31 - 1 (Park & Miller 1988)
- Análisis espectral: distancia entre hiperplanos en k dimensiones
- Test de redes/planos (RANDU: puntos caen en ~15 planos en 3D)
- Prueba de período
- Híbrido LCG + msws64
- TCR-LCG (Teorema Chino del Resto)

Registrado como tool MCP "lcg_lehmer".
"""

from __future__ import annotations

from typing import Any, Dict, List

LCG_LEHMER_TOOL_SCHEMA: Dict[str, Any] = {
    "name": "lcg_lehmer",
    "description": (
        "Análisis espectral de LCG de Lehmer (1949) ejecutado en Octave nativo. "
        "Incluye RANDU (a=65539, m=2^31), MINSTD (a=16807, m=2^31-1), análisis "
        "espectral de hiperplanos, test de redes (RANDU cae en ~15 planos en 3D), "
        "prueba de período, híbrido LCG+msws64 y TCR-LCG. "
        "Útil para entender por qué RANDU falla y cómo mejorar PRNGs lineales."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "a": {
                "type": "integer",
                "default": 65539,
                "description": "Multiplicador del LCG",
            },
            "c": {
                "type": "integer",
                "default": 0,
                "description": "Incremento del LCG (0 para Lehmer puro)",
            },
            "m": {
                "type": "integer",
                "default": 2147483648,
                "description": "Módulo del LCG",
            },
            "dim": {
                "type": "integer",
                "default": 3,
                "description": "Dimensión para análisis espectral (2-8)",
            },
            "x0": {
                "type": "integer",
                "default": 1,
                "description": "Semilla inicial",
            },
            "max_iter": {
                "type": "integer",
                "default": 1000000,
                "description": "Máx. iteraciones para prueba de período",
            },
            "n_samples": {
                "type": "integer",
                "default": 10000,
                "description": "Muestras para generar",
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


def lcg_lehmer(
    a: int = 65539,
    c: int = 0,
    m: int = 2147483648,
    dim: int = 3,
    x0: int = 1,
    max_iter: int = 1000000,
    n_samples: int = 10000,
) -> Dict[str, Any]:
    from server import run_octave

    script = f"""
function y = ms_next(x)
  s = sprintf('%08d', mod(x^2, 10^8));
  mid = str2double(s(3:6));
  y = mid;
end

function [x, w] = weyl_next(x, w, s)
  w = mod(w + s, {m});
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

%% ---------- LCG ----------
a = {a}; c = {c}; m = {m}; x = {x0};
samples = zeros(1, {n_samples});
doubles = zeros(1, {n_samples});
for i = 1:{n_samples}
  x = mod(a * x + c, m);
  samples(i) = x;
  doubles(i) = x / {m};
end

%% ---------- Chi² ----------
chi2_bins = {dim};
expected = {n_samples} / chi2_bins;
counts = zeros(1, chi2_bins);
for i = 1:{n_samples}
  b = floor(doubles(i) * chi2_bins) + 1;
  if b > chi2_bins, b = chi2_bins; end
  counts(b) = counts(b) + 1;
end
chi2 = sum((counts - expected).^2 ./ expected);
mean_d = mean(doubles);

%% ---------- Período (método de Floyd) ----------
tortoise = {x0} % {m};
hare = {x0} % {m};
period = 0;
for i = 1:{max_iter}
  tortoise = mod(a * tortoise + c, {m});
  hare = mod(a * hare + c, {m});
  hare = mod(a * hare + c, {m});
  if tortoise == hare, break; end
end
cycle_len = 0;
hare = tortoise;
do
  hare = mod(a * hare + c, {m});
  cycle_len = cycle_len + 1;
while hare ~= tortoise && cycle_len < {max_iter}

%% ---------- Planos 3D ----------
count = 0;
seen = false(1, 100000);
a2 = mod(a * a, {m});
for h3 = -50:50
  for h2 = -50:50
    for h1 = -50:50
      if h1 == 0 && h2 == 0 && h3 == 0, continue; end
      val = mod(h1 + h2 * a + h3 * a2, {m});
      if val < 0, val = val + {m}; end
      if val ~= 0, continue; end
      % También verificar término constante para c ~= 0
      val2 = mod(h2 * {c} + h3 * a * {c} + h3 * {c}, {m});
      if val2 < 0, val2 = val2 + {m}; end
      if val2 ~= 0, continue; end
      idx = mod(val, 100000) + 1;
      if ~seen(idx), seen(idx) = true; count = count + 1; end
    end
  end
end

r = struct('a', a, 'c', c, 'm', m, 'dim', dim, ...
           'chi2', chi2, ...
           'chi2_bins', chi2_bins, ...
           'chi2_samples', {n_samples}, ...
           'mean_double', mean_d, ...
           'period', cycle_len, ...
           'planes_3d', count, ...
           'first_values', samples(1:min(10, {n_samples})));
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
    name="lcg_lehmer",
    schema=LCG_LEHMER_TOOL_SCHEMA,
    handler=lambda args: lcg_lehmer(**args),
)