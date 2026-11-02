#!/usr/bin/env python3
"""
ancestral_octave_tool.py — Funciones ancestrales ejecutadas en Octave nativo
vía el mecanismo run_octave del servidor octave-mcp.

Usa salida de texto simple (una línea por campo) en lugar de jsonencode,
que no está disponible en todas las versiones de Octave.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

ANCESTRAL_OCTAVE_TOOL_SCHEMA: Dict[str, Any] = {
    "name": "ancestral_octave",
    "description": (
        "Ejecuta métodos de cálculo ancestral en Octave nativo (suanpan, TCR, "
        "vedic, pi de Arquímedes, Liu Hui, quipu, Ifá binario, etak, "
        "series de Madhava, babilónico, Al-Kashi, hebreo, cananeo, egipcio, "
        "maya, griego jónico, azteca, africano/yoruba). "
        "Corre dentro del motor de Octave vía run_octave."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "preset": {
                "type": "string",
                "enum": [
                    "suanpan_add", "chinese_remainder", "vedic_multiply",
                    "archimedes_pi", "liu_hui_pi", "quipu_encode", "ifa_cast",
                    "ifa_cast_random", "etak_deadreckoning", "madhava_pi_series",
                    "babylonian_sqrt2", "babylonian_reciprocal",
                    "sexagesimal_to_decimal", "decimal_to_sexagesimal",
                    "kashi_pi",
                    "hebrew_gematria", "hebrew_number_to_text",
                    "cananean_number_to_text",
                    "egyptian_unit_fraction", "egyptian_multiplication",
                    "maya_to_decimal", "decimal_to_maya",
                    "greek_ionic",
                    "azteca_number_to_text", "azteca_text_to_number",
                    "african_counting",
                ],
                "description": "Método ancestral a ejecutar.",
            },
            "params": {
                "type": "object",
                "description": "Parámetros específicos del preset.",
            },
        },
        "required": ["preset"],
        "additionalProperties": False,
    },
}


def _oct_list(pylist: List) -> str:
    return "[" + ", ".join(str(x) for x in pylist) + "]"


def _build_call(preset: str, params: Dict) -> str:
    params = params or {}
    if preset == "suanpan_add":
        return f"r = suanpan_add({params.get('a', 0)}, {params.get('b', 0)});"
    if preset == "chinese_remainder":
        return (
            f"sol = chinese_remainder({_oct_list(params.get('remainders', []))}, "
            f"{_oct_list(params.get('moduli', []))}); "
            f"r = struct('solution', sol);"
        )
    if preset == "vedic_multiply":
        return f"r = vedic_multiply({params.get('a', 0)}, {params.get('b', 0)});"
    if preset == "archimedes_pi":
        return (
            f"[lo, hi, hist] = archimedes_pi({params.get('iterations', 8)}); "
            f"r = struct('pi_lower', lo, 'pi_upper', hi, 'iterations', {params.get('iterations', 8)});"
        )
    if preset == "liu_hui_pi":
        return f"r = liu_hui_pi({params.get('iterations', 10)}, {params.get('levels', 3)});"
    if preset == "quipu_encode":
        return f"cords = quipu_encode({params.get('value', 0)}); r = struct('cords', {{cords}});"
    if preset == "ifa_cast":
        return f"r = ifa_cast({_oct_list(params.get('bits', [0]*8))});"
    if preset == "ifa_cast_random":
        return f"r = ifa_cast_random({params.get('seed', 1)});"
    if preset == "etak_deadreckoning":
        return (
            f"r = etak_deadreckoning({params.get('speed_knots', 0)}, "
            f"{params.get('heading_deg', 0)}, {params.get('hours', 0)}, "
            f"{params.get('lat0', 0)}, {params.get('lon0', 0)});"
        )
    if preset == "madhava_pi_series":
        return f"r = madhava_pi_series({params.get('n_terms', 10)});"
    if preset == "babylonian_sqrt2":
        return f"r = babylonian_sqrt2({params.get('n_iter', 10)}, {params.get('x0', 1.0)});"
    if preset == "babylonian_reciprocal":
        return f"r = babylonian_reciprocal({params.get('n', 60)});"
    if preset == "sexagesimal_to_decimal":
        return f"s = sexagesimal_to_decimal({_oct_list(params.get('digits', [1, 24, 51, 10]))}); r = struct('decimal', s);"
    if preset == "decimal_to_sexagesimal":
        return (
            f"d = decimal_to_sexagesimal({params.get('x', 1.414213562373)}, "
            f"{params.get('n_digits', 5)}); r = struct('sexagesimal', d);"
        )
    if preset == "kashi_pi":
        return f"p = kashi_pi({params.get('n_digits', 16)}); r = struct('pi', p);"
    if preset == "hebrew_gematria":
        return f"v = hebrew_gematria('{params.get('text', 'alef bet')}'); r = struct('gematria', v);"
    if preset == "hebrew_number_to_text":
        return f"t = hebrew_number_to_text({params.get('n', 2024)}); r = struct('text', t);"
    if preset == "cananean_number_to_text":
        return f"c = cananean_number_to_text({params.get('n', 2024)}); r = struct('text', c.text, 'places', c);"
    if preset == "egyptian_unit_fraction":
        return (
            f"t = egyptian_unit_fraction({params.get('n', 2)}, "
            f"{params.get('d', 3)}); r = struct('unit_terms', t);"
        )
    if preset == "egyptian_multiplication":
        return (
            f"m = egyptian_multiplication({params.get('a', 13)}, "
            f"{params.get('b', 12)}); r = struct('result', m.result, 'steps', m.steps);"
        )
    if preset == "maya_to_decimal":
        return f"m = maya_to_decimal({_oct_list(params.get('digits', [1, 0, 0]))}); r = struct('decimal', m);"
    if preset == "decimal_to_maya":
        return (
            f"d = decimal_to_maya({params.get('n', 400)}, "
            f"{params.get('n_positions', 3)}); r = struct('digits', d);"
        )
    if preset == "greek_ionic":
        return f"v = greek_ionic('{params.get('text', 'alpha beta')}'); r = struct('value', v);"
    if preset == "azteca_number_to_text":
        return f"r = azteca_number_to_text({params.get('n', 2024)});"
    if preset == "azteca_text_to_number":
        return f"n = azteca_text_to_number('{params.get('text', 'P')}'); r = struct('decimal', n);"
    if preset == "african_counting":
        return f"r = african_counting({params.get('n', 42)}, '{params.get('variant', 'yoruba')}');"
    raise ValueError(f"preset desconocido: {preset}")


def _octave_source_block() -> str:
    return r"""
function r = suanpan_add(a, b)
  total = a + b;
  s = num2str(total);
  n = length(s);
  heaven = zeros(1, n);
  earth  = zeros(1, n);
  for i = 1:n
    d = str2double(s(i));
    heaven(i) = (d >= 5);
    earth(i)  = mod(d, 5);
  end
  r = struct('result', total, 'heaven', heaven, 'earth', earth);
end

function [g, x, y] = extgcd(a, b)
  if b == 0, g = a; x = 1; y = 0;
  else
    [g1, x1, y1] = extgcd(b, mod(a, b));
    g = g1; x = y1; y = x1 - floor(a/b) * y1;
  end
end

function sol = chinese_remainder(remainders, moduli)
  M = prod(moduli);
  sol = 0;
  for i = 1:length(moduli)
    Mi = M / moduli(i);
    [~, ei, ~] = extgcd(Mi, moduli(i));
    inv = mod(ei, moduli(i));
    sol = sol + remainders(i) * Mi * inv;
  end
  sol = mod(sol, M);
end

function r = vedic_multiply(a, b)
  sa = num2str(a); sb = num2str(b);
  da = str2double(num2cell(sa)); db = str2double(num2cell(sb));
  conv = zeros(1, length(da)+length(db)-1);
  for i = 1:length(da)
    for j = 1:length(db)
      conv(i+j-1) = conv(i+j-1) + da(i)*db(j);
    end
  end
  r = struct('result', a*b, 'cross_products', conv);
end

function [lo, hi, hist] = archimedes_pi(iterations)
  a = 2*sqrt(3); b = 3;
  hist = zeros(iterations, 2);
  for k = 1:iterations
    a = 2*a*b/(a+b);
    b = sqrt(a*b);
    hist(k,:) = [b, a];
  end
  lo = b; hi = a;
end

function r = liu_hui_pi(iterations, levels)
  if nargin < 1, iterations = 10; end
  if nargin < 2, levels = 3; end
  a = 2*sqrt(3); b = 3;
  A = zeros(1, iterations+1); B = A; A(1) = a; B(1) = b;
  for k = 1:iterations
    a = 2*a*b/(a+b);
    b = sqrt(a*b);
    A(k+1) = a; B(k+1) = b;
  end
  RA = A; RB = B;
  for j = 1:levels
    f = 4^j - 1;
    RA = RA(2:end) + (RA(2:end) - RA(1:end-1)) / f;
    RB = RB(2:end) + (RB(2:end) - RB(1:end-1)) / f;
  end
  r = struct('pi_liu_hui', RB(end), 'pi_liu_hui_circ', RA(end), 'pi_plain', b, ...
             'iterations', iterations, 'levels', levels, 'sides', 6*2^iterations, ...
             'error_real', abs(RB(end) - pi));
end

function cords = quipu_encode(value)
  s = num2str(value);
  n = length(s);
  cords = cell(1, n);
  for i = 1:n
    d = str2double(s(i));
    place = n - i;
    if d == 0
      cords{i} = struct('digit', 0, 'knot_type', 'none', 'turns', 0, 'place', place);
    elseif place == 0 && d == 1
      cords{i} = struct('digit', d, 'knot_type', 'figure_eight', 'turns', 1, 'place', place);
    else
      cords{i} = struct('digit', d, 'knot_type', 'long_knot', 'turns', d, 'place', place);
    end
  end
end

function r = ifa_cast(bits)
  if numel(bits) ~= 8 || any(bits ~= 0 & bits ~= 1)
    error('ifa_cast espera 8 bits');
  end
  idx = 0;
  for i = 1:8, idx = idx*2 + bits(i); end
  upper = 0; lower = 0;
  for i = 1:4
    upper = upper*2 + bits(i);
    lower = lower*2 + bits(i+4);
  end
  r = struct('binary_index', idx, 'upper_tetragram', upper, 'lower_tetragram', lower, 'total_combinations', 256);
end

function r = ifa_cast_random(seed)
  rand('state', seed);
  bits = round(rand(1,8));
  r = ifa_cast(bits);
  r.seed = seed;
end

function r = etak_deadreckoning(speed_knots, heading_deg, hours, lat0, lon0)
  R_nm = 3440.065;
  dist_nm = speed_knots * hours;
  brg = deg2rad(heading_deg);
  lat1 = deg2rad(lat0);
  lon1 = deg2rad(lon0);
  ang = dist_nm / R_nm;
  lat2 = asin(sin(lat1)*cos(ang) + cos(lat1)*sin(ang)*cos(brg));
  lon2 = lon1 + atan2(sin(brg)*sin(ang)*cos(lat1), cos(ang)-sin(lat1)*sin(lat2));
  star_house = mod(round(heading_deg/11.25), 32);
  r = struct('lat_estimada', rad2deg(lat2), 'lon_estimada', rad2deg(lon2), ...
             'distancia_nm', dist_nm, 'casa_estelar_32', star_house);
end

function r = madhava_pi_series(n_terms)
  s = 0; sgn = 1;
  for k = 0:(n_terms-1)
    s = s + sgn / (2*k+1);
    sgn = -sgn;
  end
  n = n_terms;
  pi_basic = 4*s;
  correction = n / (2*(n^2+1));
  pi_corrected = 4*(s + sgn*correction/2);
  r = struct('n_terms', n_terms, 'pi_basic', pi_basic, 'pi_corrected', pi_corrected, ...
             'error_basic', abs(pi_basic - pi), 'error_corrected', abs(pi_corrected - pi));
end

function r = babylonian_sqrt2(n_iter, x0)
  if nargin < 1, n_iter = 10; end
  if nargin < 2, x0 = 1.0; end
  x = double(x0);
  for k = 1:n_iter, x = (x + 2.0/x) / 2.0; end
  r = struct('sqrt2_decimal', x, ...
             'sqrt2_sexagesimal', decimal_to_sexagesimal(x, 5), ...
             'iterations', n_iter, ...
             'tablette_YBC7289', [1, 24, 51, 10]);
end

function s = sexagesimal_to_decimal(digits)
  s = 0;
  for i = 1:length(digits), s = s + digits(i) / 60^(i-1); end
end

function d = decimal_to_sexagesimal(x, n_digits)
  d = zeros(1, n_digits);
  frac = x - floor(x);
  for i = 1:n_digits
    frac = frac * 60;
    d(i) = floor(frac);
    frac = frac - d(i);
  end
end

function r = babylonian_reciprocal(n)
  factors = factor(n);
  uf = unique(factors);
  regular = true;
  for f = uf
    if f ~= 1 && f ~= 2 && f ~= 3 && f ~= 5, regular = false; break; end
  end
  if ~regular, error('n no es regular'); end
  sexagesimal = decimal_to_sexagesimal(1.0/n, 6);
  r = struct('n', n, 'reciprocal_decimal', 1.0/n, 'reciprocal_sexagesimal', sexagesimal, 'is_regular', true);
end

function pi_val = kashi_pi(n_digits)
  kashi = [3, 8, 29, 44, 0, 47, 25, 53, 10, 14, 52, 35, 17, 44, 15, 40];
  pi_val = sexagesimal_to_decimal(kashi(1:min(n_digits, length(kashi))));
end

function val = hebrew_gematria(text)
  names = {'alef','bet','gimel','dalet','he','vav','zayin','het','tet', ...
           'yod','kaf','lamed','mem','nun','samekh','ayin','pe','tsadi', ...
           'qof','res','shin','tav', ...
           'final_kaf','final_mem','final_nun','final_pe','final_tsadi'};
  values = [1,2,3,4,5,6,7,8,9,10, ...
            20,30,40,50,60,70,80,90,100, ...
            200,300,400, ...
            500,600,700,800,900];
  val = 0;
  words = strsplit(lower(text), ' ');
  for i = 1:length(words)
    w = words{i};
    idx = strcmp(names, w);
    if any(idx), val = val + values(idx); end
  end
end

function s = hebrew_number_to_text(n)
  if n < 1 || n > 3999, error('1..3999'); end
  letters = {'ת','ק','ר','ש','צ','ץ','פ','ף','ע','ס','נ','ן','מ','ם','ל','ך','כ','י','ט','ח','ז','ו','ד','ג','ב','א'};
  values  = [400,300,200,100,90,90,80,80,70,60,50,50,40,40,30,20,20,10,9,8,7,6,5,4,3,2,1];
  s = '';
  rem = n;
  for i = 1:length(values)
    while rem >= values(i), s = [s, letters{i}]; rem = rem - values(i); end
  end
end

function r = cananean_number_to_text(n)
  thousands = floor(n / 1000);
  hundreds  = floor(mod(n,1000) / 100);
  tens      = floor(mod(n,100) / 10);
  ones      = mod(n,10);
  s = '';
  for i = 1:thousands, s = [s, 'M']; end
  for i = 1:hundreds,  s = [s, 'C']; end
  for i = 1:tens,      s = [s, 'X']; end
  for i = 1:ones,      s = [s, 'I']; end
  r = struct('text', s, 'thousands', thousands, 'hundreds', hundreds, 'tens', tens, 'ones', ones);
end

function terms = egyptian_unit_fraction(n, d)
  terms = [];
  while n > 0
    k = ceil(d / n);
    terms(end+1) = k;
    n = n * k - d;
    d = d * k;
  end
end

function r = egyptian_multiplication(a, b)
  x = a; y = b; acc = 0;
  steps = [];
  while x > 0
    if mod(x, 2) == 1, acc = acc + y; end
    steps(end+1, :) = [x, y, mod(x,2), acc];
    x = floor(x / 2);
    y = y * 2;
  end
  r = struct('result', acc, 'steps', steps);
end

function d = maya_to_decimal(digits)
  d = 0;
  for i = 1:length(digits), d = d + digits(i) * 20^(length(digits)-i); end
end

function digits = decimal_to_maya(n, n_positions)
  if nargin < 2, n_positions = 1; end
  digits = zeros(1, n_positions);
  rem = n;
  for i = n_positions:-1:1
    digits(i) = mod(rem, 20);
    rem = floor(rem / 20);
  end
  if rem > 0, error('n_positions insuficiente'); end
end

function val = greek_ionic(text)
  names = {'alpha','beta','gamma','delta','epsilon','digamma','zeta','eta', ...
           'theta','iota','kappa','lambda','mu','nu','xi','omicron','pi', ...
           'koppa','rho','sigma','tau','upsilon','phi','chi','psi','omega', ...
           'sampi'};
  values = [1,2,3,4,5,6,7,8,9,10, ...
            20,30,40,50,60,70,80,90,100, ...
            200,300,400,500,600,700,800,900];
  val = 0;
  words = strsplit(text, ' ');
  for i = 1:length(words)
    w = lower(words{i});
    idx = strcmp(names, w);
    if any(idx), val = val + values(idx); end
  end
end

function r = azteca_number_to_text(n)
  v8000 = floor(n / 8000);
  nrem  = mod(n, 8000);
  v400  = floor(nrem / 400);
  nrem  = mod(nrem, 400);
  v20   = floor(nrem / 20);
  v1    = mod(nrem, 20);
  s = '';
  for i = 1:v8000, s = [s, '8']; end   % 8000 (bolsa)
  for i = 1:v400,  s = [s, '4']; end   % 400 (pluma)
  for i = 1:v20,   s = [s, '2']; end   % 20 (bandera)
  for i = 1:v1,    s = [s, '1']; end   % 1 (punto)
  r = struct('text', s, 'v8000', v8000, 'v400', v400, 'v20', v20, 'v1', v1);
end

function n = azteca_text_to_number(text)
  n = 0;
  for i = 1:length(text)
    c = text(i);
    if c == '8', n = n + 8000;
    elseif c == '4', n = n + 400;
    elseif c == '2', n = n + 20;
    elseif c == '1', n = n + 1;
    end
  end
end

function r = african_counting(n, variant)
  if nargin < 2, variant = 'yoruba'; end
  if n < 1 || n > 400, error('1..400'); end
  if strcmpi(variant, 'yoruba')
    ogoro = 20;
    q = floor(n / ogoro);
    r = mod(n, ogoro);
    if r > 10
      q = q + 1;
      r = r - ogoro;
    end
    r_str = '';
    if r > 0
      for i = 1:r, r_str = [r_str, '|']; end
    elseif r < 0
      r_str = [r_str, '-'];
      for i = 1:-r, r_str = [r_str, '|']; end
    end
    r = struct('decimal', n, 'ogoro_blocks', q, 'remainder', r, ...
               'representation', r_str, 'variant', 'yoruba');
  else
    q = floor(n / 20);
    r = mod(n, 20);
    r_str = '';
    for i = 1:q, r_str = [r_str, '2']; end   % 20
    for i = 1:r, r_str = [r_str, '1']; end   % 1
    r = struct('decimal', n, 'v20_blocks', q, 'remainder', r, ...
               'representation', r_str, 'variant', 'additive');
  end
end

function disp_struct(r)
  % Imprime cada campo del struct como "clave=valor" una por línea.
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


def _parse_octave_output(raw: str) -> Dict[str, Any]:
    """Partea la salida de Octave buscando líneas 'clave=valor'."""
    result: Dict[str, Any] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or '=' not in line:
            continue
        key, _, val = line.partition('=')
        key = key.strip()
        val = val.strip()
        # Intentar convertir a número
        try:
            if '.' in val or 'e' in val.lower():
                result[key] = float(val)
            else:
                result[key] = int(val)
        except ValueError:
            result[key] = val
    return result


def ancestral_octave(preset: str, params: Dict = None) -> Dict[str, Any]:
    from server import run_octave

    params = params or {}
    call = _build_call(preset, params)
    script = _octave_source_block() + "\n" + call + "\ndisp_struct(r);\n"
    raw = run_octave(script)

    # Filtrar solo las líneas de resultado (líneas que contienen '=')
    result_lines = [l for l in raw.splitlines() if '=' in l and not l.startswith('{') and not l.startswith('}')]
    result_text = '\n'.join(result_lines)
    parsed = _parse_octave_output(result_text)
    if not parsed:
        return {"error": "no se pudo parsear salida de Octave", "raw_output": raw, "script": script}
    return parsed


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass


register_tool(
    name="ancestral_octave",
    schema=ANCESTRAL_OCTAVE_TOOL_SCHEMA,
    handler=lambda args: ancestral_octave(**args),
)

# Alias para compatibilidad con server.py legacy
compute_ancestral_octave = ancestral_octave