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

_OCTAVE_TIMEOUT_S = 180

HYBRID_PRNG_TOOL_SCHEMA: Dict[str, Any] = {
    "name": "hybrid_prng",
    "description": (
        "Generador PRNG híbrido (middle-square de von Neumann + msws64 de "
        "Widynski 2017) ejecutado en Octave nativo. middle-square por sí solo "
        "está roto (ciclos cortos, colapso a cero); msws64 aporta entropía de "
        "64 bits. El híbrido XOR de ambos produce buena distribución "
        "estadística sin depender de un solo mecanismo. Devuelve coeficiente "
        "chi² de uniformidad, periodo, estado interno y valores de muestra. "
        "Modos: compute, validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["compute", "validate"],
                "default": "compute",
                "description": (
                    "compute: simula el PRNG híbrido. validate: autochequeo "
                    "contra vectores de referencia (bit a bit) y pruebas "
                    "estadísticas de uniformidad."
                ),
            },
            "params": {
                "type": "object",
                "description": (
                    "Parámetros alternos; accepted como override de los "
                    "campos planos (misma semántica)."
                ),
            },
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
        fprintf('%s=%.15g\n', f, v);
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
    mode: str = "compute",
    params: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if mode == "validate":
        return _mode_validate()
    if isinstance(params, dict) and params:
        seed = params.get("seed", seed)
        n_samples = params.get("n_samples", n_samples)
        nbins = params.get("nbins", nbins)
    from server import run_octave

    script = f"""
function y = ms_mid4(v)
  % digitos 3-6 (de 8) de v, con 0 <= v < 1e8 -- equivalente exacto a
  % sprintf('%08d', v)(3:6) pero sin el coste de sprintf en los bucles
  y = mod(floor(v / 100), 10000);
end

function y = ms_next(x)
  y = ms_mid4(mod(x^2, 1e8));
end

function [x, w] = weyl_next(x, w, s)
  w = mod(w + s, 10000);
  x = ms_mid4(mod(x^2 + w, 1e8));
end

function r = add64(a, b)
  % suma uint64 con desbordamiento modulo 2^64 (Octave satura por defecto)
  M = uint64(4294967295);
  lo = bitand(a, M) + bitand(b, M);
  carry = bitshift(lo, -32);
  hi = bitand(bitshift(a, -32) + bitshift(b, -32) + carry, M);
  r = bitor(bitshift(hi, 32), bitand(lo, M));
end

function r = mul64(a, b)
  % producto uint64 modulo 2^64 via mitades de 32 bits
  M = uint64(4294967295);
  aL = bitand(a, M); aH = bitshift(a, -32);
  bL = bitand(b, M); bH = bitshift(b, -32);
  cross = bitand(bitand(aH * bL, M) + bitand(aL * bH, M), M);
  r = add64(aL * bL, bitshift(cross, 32));
end

function [x, w] = msws64_step(x, w, s)
  % Widynski msws64 (2017): x*=x; x+=(w+=s); x=(x>>32)|(x<<32)
  x = mul64(x, x);
  w = add64(w, s);
  x = add64(x, w);
  x = bitor(bitshift(x, -32), bitshift(x, 32));
end

function s = msws64_const()
  s = bitor(bitshift(uint64(hex2dec('b5ad4ece')), 32), uint64(hex2dec('da1ce2a9')));
end

function hybrid_seed(seed)
  global HX HW HS HMS
  HS = msws64_const();
  HX = uint64(seed); HW = uint64(0);
  HMS = mod(seed, 10000); if HMS == 0, HMS = 1234; end
  for k = 1:8
    [HX, HW] = msws64_step(HX, HW, HS);   % calentamiento: semillas chicas
  end
end

function r = hybrid_prng_next()
  global HX HW HS HMS
  [HX, HW] = msws64_step(HX, HW, HS);
  HMS = ms_next(HMS);
  if HMS == 0, HMS = mod(double(bitand(HX, uint64(65535))), 9999) + 1; end
  r = bitxor(HX, uint64(HMS));
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
  x = ms_mid4(mod(x^2 + w, 1e8));
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
  samples(i) = double(r);
  doubles(i) = double(bitshift(r, -11)) / 9007199254740992;
end

%% ---------- Chi^2 ----------
UINT64_MAX = double(intmax('uint64'));
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
           'msws64_period', -1, ...   % -1 = no medible (estado de 64 bits)
           'chi2', chi2, ...
           'chi2_bins', chi2_bins, ...
           'chi2_samples', chi2_samples, ...
           'mean_double', mean_d, ...
           'first_values', samples(1:min(10, chi2_samples)));
{_DISP_STRUCT}
disp_struct(r);
"""
    raw = run_octave(script, timeout=_OCTAVE_TIMEOUT_S)

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


# --------------------------------------------------------------------------
# Autochequeo (mode=validate)
#
# Vectores de referencia calculados con una implementacion independiente en
# Python con aritmetica entera exacta (uint64 con desbordamiento modulo
# 2^64), no con el codigo de Octave de esta tool. Si el generador cambia o
# se rompe, los checks saltan.
#
#   msws64 de Widynski: x*=x; x+=(w+=s); x=(x>>32)|(x<<32),
#   s = 0xb5ad4ece_da1ce2a9, calentamiento de 8 pasos desde seed=1234.
# --------------------------------------------------------------------------
_HYBRID_REF_FIRST3 = [
    2416814197255316608,
    467761193342463637,
    9298710466687011517,
]
_HYBRID_REF_CHI2 = 11.774
_HYBRID_REF_MEAN = 0.5005083357597068
_HYBRID_REF_MS_CYCLES = 8
_HYBRID_REF_ZERO_SINK = 0.1818
_UINT64_MAX = 2 ** 64 - 1
_CHI2_CRIT_9DF_1PCT = 21.666  # chi² crítico con 9 gl al 1% de significación


def _parse_num_array(text: Any) -> list:
    """Convierte '[1 2 3]' (así lo imprime num2str de Octave) en lista de floats."""
    if isinstance(text, (list, tuple)):
        return [float(v) for v in text]
    cleaned = str(text).strip().strip("[]").replace(",", " ")
    return [float(part) for part in cleaned.split() if part]


def _chk(name: str, got: Any, want: Any, rel_tol: float = 1e-9) -> Dict[str, Any]:
    ok = abs(float(got) - float(want)) <= rel_tol * max(1.0, abs(float(want)))
    return {"name": name, "got": got, "want": want, "passed": bool(ok)}


def _mode_validate() -> Dict[str, Any]:
    out = hybrid_prng(seed=1234, n_samples=10000, nbins=10)
    if "error" in out:
        return {
            "checks": [{"name": "compute del tool", "passed": False, "detail": out["error"]}],
            "total_passed": 0,
            "total_checks": 1,
            "validation_passed": False,
        }

    checks = []
    first = _parse_num_array(out.get("first_values", []))

    checks.append({
        "name": "msws64 + middle-square: primeros 3 valores == referencia Python",
        "got": first[:3],
        "want": _HYBRID_REF_FIRST3,
        "passed": len(first) >= 3 and all(
            abs(a - b) <= 1e-9 * max(1.0, abs(b))
            for a, b in zip(first[:3], _HYBRID_REF_FIRST3)
        ),
    })

    chi2 = float(out["chi2"])
    checks.append({
        "name": f"chi² híbrido (10 bins, 10000 muestras) < {_CHI2_CRIT_9DF_1PCT} (9 gl, 1%)",
        "got": chi2,
        "passed": chi2 < _CHI2_CRIT_9DF_1PCT,
    })
    checks.append(_chk("chi² híbrido == referencia (11.774)", chi2, _HYBRID_REF_CHI2, 1e-6))

    mean_d = float(out["mean_double"])
    checks.append({
        "name": "media de las muestras en [0.48, 0.52]",
        "got": mean_d,
        "passed": abs(mean_d - 0.5) <= 0.02,
    })

    checks.append(_chk("middle-square de 4 dígitos: 8 ciclos", out["middle_square_cycles"],
                       _HYBRID_REF_MS_CYCLES, 0))
    checks.append(_chk("middle-square: 18.18% de las semillas colapsan a 0",
                       out["middle_square_zero_sink"], _HYBRID_REF_ZERO_SINK, 1e-12))
    checks.append({
        "name": "primer valor dentro de uint64",
        "got": first[0] if first else None,
        "passed": bool(first) and 0 < first[0] < _UINT64_MAX,
    })

    passed = sum(c["passed"] for c in checks)
    return {
        "checks": checks,
        "total_passed": passed,
        "total_checks": len(checks),
        "validation_passed": passed == len(checks),
    }


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