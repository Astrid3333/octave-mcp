#!/usr/bin/env python3
"""
goertzel_tool.py — Goertzel K, alpha, beta, hybrida ejecutados en Octave nativo
vía run_octave del servidor octave-mcp. Se auto-registra en tool_registry.
"""

from __future__ import annotations

from typing import Any, Dict

GOERTZEL_TOOL_SCHEMA: Dict[str, Any] = {
    "name": "goertzel",
    "description": (
        "Calcula el coeficiente DFT en una frecuencia angular w usando el "
        "algoritmo de Goertzel con formulaciones K=2cos(w), alpha=4sin^2(w/2), "
        "beta=4cos^2(w/2) (espejo para w cerca de pi) e híbrida. "
        "Ejecutado en Octave nativo."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "signal": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Senal de entrada (lista de floats).",
            },
            "w": {
                "type": "number",
                "description": "Frecuencia angular en radianes (0 <= w <= pi).",
            },
            "form": {
                "type": "string",
                "enum": ["K", "alpha", "beta", "hybrid"],
                "description": "Formulacion a usar. Default: 'hybrid'.",
                "default": "hybrid",
            },
        },
        "required": ["signal", "w"],
        "additionalProperties": False,
    },
}


def _oct_list(pylist: list) -> str:
    return "[" + ", ".join(str(float(x)) for x in pylist) + "]"


def goertzel(signal: list, w: float, form: str = "hybrid") -> Dict[str, Any]:
    from server import run_octave

    xs = _oct_list(signal)
    script = f"""
function c = goertzel_K(x, w)
  K = 2*cos(w); s1 = 0; s2 = 0;
  for v = x, s = v + K*s1 - s2; s2 = s1; s1 = s; end
  s = K*s1 - s2; c = s - exp(-1i*w)*s1;
end
function c = goertzel_alpha(x, w)
  al = 4*sin(w/2)^2; s = 0; d = 0;
  for v = x, d = d + v - al*s; s = s + d; end
  d = d - al*s; s = s + d; s1 = s - d;
  c = s - exp(-1i*w)*s1;
end
function c = goertzel_beta(x, w)
  be = 4*cos(w/2)^2; s = 0; d = 0;
  for v = x, d = v + be*s - d; s = d - s; end
  d = be*s - d; s = d - s; s1 = d - s;
  c = s - exp(-1i*w)*s1;
end
function c = goertzel_hybrid(x, w)
  if w < pi/2, c = goertzel_alpha(x, w); else, c = goertzel_beta(x, w); end
end
x = {xs}; w = {w};
c = goertzel_{form}(x, w);
r = struct('re', real(c), 'im', imag(c), 'magnitude', abs(c), 'form', '{form}');
function disp_struct(r)
  fields = fieldnames(r);
  for i = 1:length(fields)
    f = fields{{i}};
    v = r.(f);
    if isnumeric(v) && numel(v) == 1
      fprintf('%s=%g\\n', f, v);
    elseif ischar(v) || isstring(v)
      fprintf('%s=%s\\n', f, v);
    else
      fprintf('%s=<no scalar>\\n', f);
    end
  end
end
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
            parsed[key] = float(val)
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
    name="goertzel",
    schema=GOERTZEL_TOOL_SCHEMA,
    handler=lambda args: goertzel(
        signal=args.get("signal", []),
        w=args.get("w", 0.0),
        form=args.get("form", "hybrid"),
    ),
)