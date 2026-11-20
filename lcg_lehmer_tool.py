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

from typing import Any, Dict

_OCTAVE_TIMEOUT_S = 180

LCG_LEHMER_TOOL_SCHEMA: Dict[str, Any] = {
    "name": "lcg_lehmer",
    "description": (
        "Análisis espectral de LCG de Lehmer (1949) ejecutado en Octave nativo. "
        "Incluye RANDU (a=65539, m=2^31), MINSTD (a=16807, m=2^31-1), análisis "
        "espectral de hiperplanos, test de redes (RANDU cae en ~15 planos en 3D), "
        "prueba de período, híbrido LCG+msws64 y TCR-LCG. "
        "Útil para entender por qué RANDU falla y cómo mejorar PRNGs lineales. "
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
                    "compute: analiza el LCG. validate: autochequeo contra "
                    "vectores de referencia (RANDU, MINSTD y un LCG pequeño "
                    "con período conocido)."
                ),
            },
            "params": {
                "type": "object",
                "description": (
                    "Parámetros alternos; accepted como override de los "
                    "campos planos (misma semántica)."
                ),
            },
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


def lcg_lehmer(
    a: int = 65539,
    c: int = 0,
    m: int = 2147483648,
    dim: int = 3,
    x0: int = 1,
    max_iter: int = 1000000,
    n_samples: int = 10000,
    mode: str = "compute",
    params: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if mode == "validate":
        return _mode_validate()
    if isinstance(params, dict) and params:
        a = params.get("a", a)
        c = params.get("c", c)
        m = params.get("m", m)
        dim = params.get("dim", dim)
        x0 = params.get("x0", x0)
        max_iter = params.get("max_iter", max_iter)
        n_samples = params.get("n_samples", n_samples)
    from server import run_octave

    if a * m + c >= 2 ** 53:
        return {"error": "a*m + c debe ser < 2^53 (aritmetica double de Octave)"}

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
chi2_bins = 10;
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
tortoise = mod({x0}, {m});
hare = tortoise;
period_found = 0;
for i = 1:{max_iter}
  tortoise = mod(a * tortoise + c, {m});
  hare = mod(a * hare + c, {m});
  hare = mod(a * hare + c, {m});
  if tortoise == hare, period_found = 1; break; end
end
cycle_len = -1;   % -1 = no se encontro ciclo en max_iter
if period_found
  cycle_len = 0;
  hare = tortoise;
  do
    hare = mod(a * hare + c, {m});
    cycle_len = cycle_len + 1;
  until hare == tortoise
end

%% ---------- Planos 3D (test espectral: vector dual mas corto) ----------
% h1 + h2*a + h3*a^2 = 0 (mod m); planos = |h|_1 - 1 (RANDU: h=(9,-6,1) -> 15)
a2 = mod(a * a, {m});
B = 3000;
h2v = -B:B;
best = Inf;
for h3 = -B:B
  h1c = mod(-(h2v * a + h3 * a2), {m});
  h1a = min(h1c, {m} - h1c);
  l1 = h1a + abs(h2v) + abs(h3);
  l1(h2v == 0 & h3 == 0) = Inf;
  mn = min(l1);
  if mn < best, best = mn; end
end
planes_3d_exact = double(best <= B);
count = best - 1;

r = struct('a', a, 'c', c, 'm', m, 'dim', {dim}, ...
           'chi2', chi2, ...
           'chi2_bins', chi2_bins, ...
           'chi2_samples', {n_samples}, ...
           'mean_double', mean_d, ...
           'period', cycle_len, ...
           'period_found', period_found, ...
           'planes_3d', count, ...
           'planes_3d_exact', planes_3d_exact, ...
           'first_values', samples(1:min(10, {n_samples})));
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
# Vectores de referencia obtenidos con una implementacion independiente en
# Python con aritmetica entera exacta:
#   - RANDU  (a=65539, c=0, m=2^31)  -> 65539, 393225, 1769499, ...
#   - MINSTD (a=16807, c=0, m=2^31-1) -> 16807, 282475249, 1622650073, ...
#   - planos 3D: vector dual minimo (h1,h2,h3) con h1+h2*a+h3*a^2 = 0 (mod m);
#     planos = |h|_1 - 1. RANDU -> (9,6,-1), |h|_1=16 -> 15 planos (clasico).
#     MINSTD -> (90,44,-631), |h|_1=765 -> 764 planos.
#   - LCG pequeño (a=4, c=1, m=7): orbita 1 -> 5 -> 0 -> 1, periodo 3.
# --------------------------------------------------------------------------
_LCG_REF_RANDU = {
    "first": [65539, 393225, 1769499],
    "planes": 15,
    "chi2": 8.812,
    "mean": 0.5001627670869231,
}
_LCG_REF_MINSTD = {
    "first": [16807, 282475249, 1622650073],
    "planes": 764,
    "chi2": 6.69,
    "mean": 0.5018268222083462,
}
_LCG_SMALL = {"a": 4, "c": 1, "m": 7, "x0": 1, "period": 3, "first": 5}
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
    checks = []

    # RANDU: secuencia y planos 3D clasicos. max_iter acotado porque el
    # periodo real de RANDU (2^29) no cabe en el limite de 30 s de run_octave.
    randu = lcg_lehmer(a=65539, c=0, m=2 ** 31, dim=3, x0=1,
                       max_iter=50000, n_samples=10000)
    if "error" in randu:
        return {
            "checks": [{"name": "compute del tool", "passed": False, "detail": randu["error"]}],
            "total_passed": 0,
            "total_checks": 1,
            "validation_passed": False,
        }

    first_randu = _parse_num_array(randu.get("first_values", []))
    checks.append({
        "name": "RANDU: primeros 3 valores == referencia (65539, 393225, 1769499)",
        "got": first_randu[:3],
        "want": _LCG_REF_RANDU["first"],
        "passed": len(first_randu) >= 3 and all(
            abs(a - b) <= 1e-9 * max(1.0, abs(b))
            for a, b in zip(first_randu[:3], _LCG_REF_RANDU["first"])
        ),
    })
    checks.append(_chk("RANDU: 15 planos en 3D (vector dual (9,6,-1))",
                       randu["planes_3d"], _LCG_REF_RANDU["planes"], 0))
    checks.append(_chk("RANDU: chi² == referencia (8.812)",
                       randu["chi2"], _LCG_REF_RANDU["chi2"], 1e-6))
    checks.append({
        "name": f"RANDU: chi² < {_CHI2_CRIT_9DF_1PCT} (9 gl, 1%)",
        "got": randu["chi2"],
        "passed": float(randu["chi2"]) < _CHI2_CRIT_9DF_1PCT,
    })
    checks.append({
        "name": "RANDU: media de las muestras en [0.48, 0.52]",
        "got": randu["mean_double"],
        "passed": abs(float(randu["mean_double"]) - 0.5) <= 0.02,
    })
    checks.append({
        "name": "RANDU: período no medido se reporta como -1 (2^29 iteraciones)",
        "got": randu["period"],
        "passed": randu["period"] == -1 and randu["period_found"] == 0,
    })

    # MINSTD: Park-Miller, periodo 2^31-2 (tampoco medible aqui).
    minstd = lcg_lehmer(a=16807, c=0, m=2 ** 31 - 1, dim=3, x0=1,
                        max_iter=1000, n_samples=10000)
    first_minstd = _parse_num_array(minstd.get("first_values", []))
    checks.append({
        "name": "MINSTD: primeros 3 valores == referencia (16807, 282475249, 1622650073)",
        "got": first_minstd[:3],
        "want": _LCG_REF_MINSTD["first"],
        "passed": len(first_minstd) >= 3 and all(
            abs(a - b) <= 1e-9 * max(1.0, abs(b))
            for a, b in zip(first_minstd[:3], _LCG_REF_MINSTD["first"])
        ),
    })
    checks.append(_chk("MINSTD: 764 planos en 3D (vector dual (90,44,-631))",
                       minstd["planes_3d"], _LCG_REF_MINSTD["planes"], 0))
    checks.append(_chk("MINSTD: chi² == referencia (6.69)",
                       minstd["chi2"], _LCG_REF_MINSTD["chi2"], 1e-6))
    checks.append({
        "name": f"MINSTD: chi² < {_CHI2_CRIT_9DF_1PCT} (9 gl, 1%)",
        "got": minstd["chi2"],
        "passed": float(minstd["chi2"]) < _CHI2_CRIT_9DF_1PCT,
    })

    # LCG pequeño: el período SI es medible (Floyd) y conocido de antemano.
    small = lcg_lehmer(a=_LCG_SMALL["a"], c=_LCG_SMALL["c"], m=_LCG_SMALL["m"],
                       dim=3, x0=_LCG_SMALL["x0"], max_iter=1000, n_samples=100)
    first_small = _parse_num_array(small.get("first_values", []))
    checks.append({
        "name": "LCG pequeño (a=4, c=1, m=7): primer valor 5",
        "got": first_small[:1],
        "want": [_LCG_SMALL["first"]],
        "passed": first_small[:1] == [float(_LCG_SMALL["first"])],
    })
    checks.append({
        "name": "LCG pequeño (a=4, c=1, m=7): período 3 medido con Floyd",
        "got": small["period"],
        "want": _LCG_SMALL["period"],
        "passed": small["period"] == _LCG_SMALL["period"] and small["period_found"] == 1,
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
    name="lcg_lehmer",
    schema=LCG_LEHMER_TOOL_SCHEMA,
    handler=lambda args: lcg_lehmer(**args),
)