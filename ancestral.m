1;
% ancestral.m — Métodos de cálculo ancestral como funciones Octave nativas.
% Pensado para correr DENTRO del motor de Octave (via octave_run), no como
% simulación externa en Python — así se puede componer en el mismo script
% con ode45, eig, fft, etc.

function r = suanpan_add(a, b)
  % Suma con estado de varillas explícito (cielo=5, tierra=1), acarreo real.
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
  r.result = total;
  r.heaven = heaven;
  r.earth  = earth;
end

function r = extgcd(a, b)
  % Algoritmo de Euclides extendido: a*x + b*y = gcd(a,b)
  if b == 0
    r.g = a; r.x = 1; r.y = 0;
  else
    sub = extgcd(b, mod(a, b));
    r.g = sub.g;
    r.x = sub.y;
    r.y = sub.x - floor(a/b) * sub.y;
  end
end

function s = chinese_remainder(remainders, moduli)
  % TCR constructivo (Sunzi/Qin Jiushao) via inverso modular con Euclides ext.
  M = prod(moduli);
  s = 0;
  for i = 1:length(moduli)
    Mi = M / moduli(i);
    e = extgcd(Mi, moduli(i));
    inv = mod(e.x, moduli(i));
    s = s + remainders(i) * Mi * inv;
  end
  s = mod(s, M);
end

function r = vedic_multiply(a, b)
  % Urdhva-Tiryagbhyam sobre dígitos (multiplicación vertical-cruzada),
  % devuelve el resultado y la traza de productos cruzados por posición.
  sa = num2str(a); sb = num2str(b);
  da = str2double(num2cell(sa)); db = str2double(num2cell(sb));
  na = length(da); nb = length(db);
  conv = zeros(1, na+nb-1);
  for i = 1:na
    for j = 1:nb
      pos = i + j - 1;
      conv(pos) = conv(pos) + da(i)*db(j);
    end
  end
  r.result = a * b;                 % valor de referencia (aritmética nativa)
  r.cross_products = conv;          % traza védica, útil para mostrar el método
end

function [pi_lo, pi_hi, hist] = archimedes_pi(iterations)
  % Método real de Archimedes: media armónica (circunscrito) + media
  % geométrica (inscrito), doblando lados desde el hexágono. Sin usar
  % ninguna constante pi incorporada — solo sqrt, como el método original.
  a = 2*sqrt(3);   % semiperímetro hexágono circunscrito (cota superior)
  b = 3;           % semiperímetro hexágono inscrito (cota inferior)
  hist = zeros(iterations, 2);
  for k = 1:iterations
    a = 2*a*b / (a+b);   % media armónica -> nuevo circunscrito
    b = sqrt(a*b);       % media geométrica -> nuevo inscrito
    hist(k, :) = [b, a];
  end
  pi_lo = b; pi_hi = a;
end

function r = liu_hui_pi(iterations, levels)
  % Arquimedes (media armonica/geometrica, hexagono inicial) + extrapolacion de
  % Liu Hui (s. III): el error del poligono baja como 1/n^2, y
  % R <- R(k+1) + (R(k+1)-R(k))/(4^j-1) lo anula nivel a nivel (Romberg).
  % Sin restas inestables. pi_plain = ultima cota inscrita sin extrapolar.
  if nargin < 1, iterations = 10; end
  if nargin < 2, levels = 3; end
  if levels > iterations
    error('liu_hui_pi: levels (%d) debe ser <= iterations (%d)', levels, iterations);
  end
  a = 2*sqrt(3); b = 3;
  A = zeros(1, iterations+1); B = A; A(1) = a; B(1) = b;
  for k = 1:iterations
    a = 2*a*b / (a+b);
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

function r = quipu_encode(value)
  % Codificación decimal por nudos (nudo largo=unidades por vueltas,
  % nudo en ocho=1, nudos simples=centenas/millares por posición).
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
  r = cords;
end
