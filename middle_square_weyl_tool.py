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
        "métricas de calidad de salida. Modos: compute, validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["compute", "validate"],
                "default": "compute",
                "description": (
                    "compute: compara los cuatro generadores. validate: "
                    "autochequeo contra vectores de referencia (ciclos, "
                    "zero_sink, chi² de cada variante y módulo exacto del TCR)."
                ),
            },
            "params": {
                "type": "object",
                "description": (
                    "Parámetros alternos; accepted como override de los "
                    "campos planos (misma semántica)."
                ),
            },
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


def middle_square_weyl(
    digits: int = 4,
    modulus: int = 10000,
    weyl_s: int = 6329,
    tcr_p1: int = 9973,
    tcr_p2: int = 9967,
    max_iter: int = 1000000,
    chi2_bins: int = 10,
    chi2_samples: int = 10000,
    mode: str = "compute",
    params: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if mode == "validate":
        return _mode_validate()
    if isinstance(params, dict) and params:
        digits = params.get("digits", digits)
        modulus = params.get("modulus", modulus)
        weyl_s = params.get("weyl_s", weyl_s)
        tcr_p1 = params.get("tcr_p1", tcr_p1)
        tcr_p2 = params.get("tcr_p2", tcr_p2)
        max_iter = params.get("max_iter", max_iter)
        chi2_bins = params.get("chi2_bins", chi2_bins)
        chi2_samples = params.get("chi2_samples", chi2_samples)
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
  w = mod(w + s, {modulus});
  x = ms_mid4(mod(x^2 + w, 1e8));
end

function [x, w1, w2, w] = tcr_next(x, w1, w2, s, p1, p2, M)
  w1 = mod(w1 + s, p1);
  w2 = mod(w2 + s, p2);
  inv = mod(inv_mod(p1, p2), p2);
  k = mod((w2 - w1) * inv, p2);
  w = mod(w1 + p1 * k, M);
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

function [x, w, o] = msws64_out(x, w, s, modval)
  % salida comparable con middle-square: 32 bits altos reducidos a modval
  [x, w] = msws64_step(x, w, s);
  o = mod(double(bitshift(x, -32)), modval);
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
  x = ms_mid4(mod(x^2 + w, 1e8));
  if seen_crt(x+1)
    j = find(trcrt == x, 1);
    tcr_period = i - j;
    break;
  end
  seen_crt(x+1) = true;
  trcrt = [trcrt, x];
end

%% ---------- Widynski msws64 ----------
% estado de 64 bits: el periodo no es medible por busqueda de repeticion
% (repetir una salida de 4 digitos no implica ciclo de estado). -1 = no medible.
msws_period = -1;

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
  x_tc = ms_mid4(mod(x_tc^2 + w_tc, 1e8));
  samples_tc(i) = x_tc;
end
chi2_tc = compute_chi2(samples_tc, chi2_bins, {modulus});

% Chi² para msws64
x_msw = uint64(1234); w_msw = uint64(0); s_msw = msws64_const();
samples_msw = zeros(1, chi2_samples);
for i = 1:chi2_samples
  [x_msw, w_msw, o_msw] = msws64_out(x_msw, w_msw, s_msw, {modulus});
  samples_msw(i) = o_msw;
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


# --------------------------------------------------------------------------
# Autochequeo (mode=validate)
#
# Vectores de referencia calculados con una implementacion independiente en
# Python con aritmetica entera exacta (no con el codigo de Octave de esta
# tool):
#   - middle-square de 4 digitos: 8 ciclos en el espacio de estados modulo
#     10000; 1818 de las 10000 semillas colapsan a 0 en 50 pasos (18.18%).
#   - el middle-square sesga fuerte: la muestra desde la semilla 1234 cae
#     casi toda en un bin -> chi² ~= 89062 (10 bins, 10000 muestras).
#   - Weyl (s=6329) y TCR (9973 x 9967) rompen la correlacion del
#     middle-square; TCR con 16 digitos binarios reparte bien.
#   - msws64 (Widynski 2017) es el unico con chi² dentro de la banda.
# --------------------------------------------------------------------------
_MSWEYL_REF_CYCLES = 8
_MSWEYL_REF_ZERO_SINK = 0.1818
_MSWEYL_REF_CHI2_MS = 89062.522
_MSWEYL_REF_CHI2_WEYL = 377.746
_MSWEYL_REF_CHI2_TCR = 11.75
_MSWEYL_REF_CHI2_MSWS64 = 6.84
_MSWEYL_REF_TCR_M = 99400891  # 9973 * 9967 (exacto; con %g salia 99400900)
_CHI2_CRIT_9DF_1PCT = 21.666  # chi² crítico con 9 gl al 1% de significación


def _chk(name: str, got: Any, want: Any, rel_tol: float = 1e-9) -> Dict[str, Any]:
    ok = abs(float(got) - float(want)) <= rel_tol * max(1.0, abs(float(want)))
    return {"name": name, "got": got, "want": want, "passed": bool(ok)}


def _mode_validate() -> Dict[str, Any]:
    out = middle_square_weyl()
    if "error" in out:
        return {
            "checks": [{"name": "compute del tool", "passed": False, "detail": out["error"]}],
            "total_passed": 0,
            "total_checks": 1,
            "validation_passed": False,
        }

    checks = []
    checks.append(_chk("middle-square de 4 dígitos: 8 ciclos",
                       out["middle_square_cycles"], _MSWEYL_REF_CYCLES, 0))
    checks.append(_chk("middle-square: 18.18% de las semillas colapsan a 0",
                       out["middle_square_zero_sink"], _MSWEYL_REF_ZERO_SINK, 1e-12))
    checks.append(_chk("chi² del middle-square == referencia (89062.522)",
                       out["chi2_middle_square"], _MSWEYL_REF_CHI2_MS, 1e-6))
    checks.append({
        "name": "chi² del middle-square > 1000 (sesgo detectable del método)",
        "got": out["chi2_middle_square"],
        "passed": float(out["chi2_middle_square"]) > 1000,
    })
    checks.append(_chk("chi² de Weyl == referencia (377.746)",
                       out["chi2_weyl"], _MSWEYL_REF_CHI2_WEYL, 1e-6))
    checks.append({
        "name": "chi² de Weyl > 21.67 (Weyl no corrige del todo el sesgo)",
        "got": out["chi2_weyl"],
        "passed": float(out["chi2_weyl"]) > _CHI2_CRIT_9DF_1PCT,
    })
    checks.append(_chk("chi² del TCR == referencia (11.75)",
                       out["chi2_tcr"], _MSWEYL_REF_CHI2_TCR, 1e-6))
    checks.append({
        "name": f"chi² del TCR < {_CHI2_CRIT_9DF_1PCT} (9 gl, 1%)",
        "got": out["chi2_tcr"],
        "passed": float(out["chi2_tcr"]) < _CHI2_CRIT_9DF_1PCT,
    })
    checks.append(_chk("chi² de msws64 == referencia (6.84)",
                       out["chi2_msws64"], _MSWEYL_REF_CHI2_MSWS64, 1e-6))
    checks.append({
        "name": f"chi² de msws64 < {_CHI2_CRIT_9DF_1PCT} (9 gl, 1%)",
        "got": out["chi2_msws64"],
        "passed": float(out["chi2_msws64"]) < _CHI2_CRIT_9DF_1PCT,
    })
    checks.append(_chk("TCR: módulo M = 9973 x 9967 = 99400891",
                       out["tcr_modulus_M"], _MSWEYL_REF_TCR_M, 0))
    checks.append({
        "name": "msws64: período no medible se reporta como -1",
        "got": out["msws64_period"],
        "passed": out["msws64_period"] == -1,
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
    name="middle_square_weyl",
    schema=MIDDLE_SQUARE_WEYL_TOOL_SCHEMA,
    handler=lambda args: middle_square_weyl(**args),
)