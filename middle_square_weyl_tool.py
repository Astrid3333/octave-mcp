#!/usr/bin/env python3
"""
middle_square_weyl_tool.py — Compara middle-square de von Neumann vs
secuencia de Weyl vs TCR (Teorema Chino del Resto) en Octave nativo.
"""

from __future__ import annotations

from typing import Any, Dict

MIDDLE_SQUARE_WEYL_TOOL_SCHEMA: Dict[str, Any] = {
    "name": "middle_square_weyl",
    "description": (
        "Compara middle-square de von Neumann (4 dígitos) contra dos arreglos: "
        "secuencia de Weyl (contador aditivo) y TCR (Teorema Chino del Resto con "
        "primos coprimos 9973 y 9967). Devuelve ciclos, zero_sink, periodos y M."
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
) -> Dict[str, Any]:
    from server import run_octave

    script = f"""
function y = ms_next(x)
  s = sprintf('%08d', mod(x^2, 10^8));
  mid = str2double(s(3:6));
  y = mid;
end

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

function [x, w] = weyl_next(x, w, s)
  w = mod(w + s, {modulus});
  s8 = sprintf('%08d', mod(x^2 + w, 10^8));
  x = str2double(s8(3:6));
end

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

M = {tcr_p1} * {tcr_p2};
w1 = 0; w2 = 0; x = 1234;
trcrt = []; seen_crt = false(1, {modulus}); tcr_period = 0;
% Definir extgcd antes de usarlo
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

spread = abs(weyl_period - tcr_period) / max(abs(tcr_period), 1);

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

r = struct('middle_square_cycles', n_cycles, ...
           'middle_square_zero_sink', zs_rel, ...
           'weyl_period', weyl_period, ...
           'tcr_period', tcr_period, ...
           'tcr_modulus_M', M, ...
           'variant_spread', spread);
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