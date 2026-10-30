1;
% ancestral3.m — Tercera tanda: sistemas numéricos y métodos ancestrales
% faltantes (babilonico, persa/Al-Kashi, hebreo/gematria, cananeo, egipcio,
% maya, griego jónico). Funciones Octave nativas, componibles.

% ---------------- BABILONICO (mesopotamia, base 60) ----------------

function s = sexagesimal_to_decimal(digits)
  % Convierte una lista de digitos base-60 (mas significativo primero) a decimal.
  % Ejemplo: [1, 24, 51, 10] -> 1 + 24/60 + 51/3600 + 10/216000 = 1.41421296...
  s = 0;
  for i = 1:length(digits)
    s = s + digits(i) / 60^(i-1);
  end
end

function d = decimal_to_sexagesimal(x, n_digits)
  % Convierte decimal a lista de n_digits digitos base-60 (fraccionario).
  d = zeros(1, n_digits);
  frac = x - floor(x);
  for i = 1:n_digits
    frac = frac * 60;
    d(i) = floor(frac);
    frac = frac - d(i);
  end
end

function r = babylonian_sqrt2(n_iter, x0)
  % Raiz cuadrada de 2 por metodo babilonico/heronico:
  %   x_{k+1} = (x_k + 2/x_k) / 2
  % La tablilla YBC 7289 registra 1;24,51,10 (base 60) ~= 1.41421296.
  if nargin < 1, n_iter = 10; end
  if nargin < 2, x0   = 1.0; end
  x = double(x0);
  for k = 1:n_iter
    x = (x + 2.0 / x) / 2.0;
  end
  r = struct('sqrt2_decimal', x, ...
             'sqrt2_sexagesimal', decimal_to_sexagesimal(x, 5), ...
             'iterations', n_iter, ...
             'tablette_YBC7289', [1, 24, 51, 10]);
end

function r = babylonian_reciprocal(n)
  % Tabla de recíprocos babilónicos: 1/n en base 60 (solo para n regulares,
  % es decir, cuyos factores primos son subconjunto de {2,3,5}).
  factors = factor(n);
  uf = unique(factors);
  regular = true;
  for f = uf
    if f ~= 1 && f ~= 2 && f ~= 3 && f ~= 5
      regular = false;
      break;
    end
  end
  if ~regular
    error('babylonian_reciprocal: n no es regular (solo factores 2,3,5)');
  end
  sexagesimal = decimal_to_sexagesimal(1.0 / n, 6);
  r = struct('n', n, 'reciprocal_decimal', 1.0/n, ...
             'reciprocal_sexagesimal', sexagesimal, ...
             'is_regular', true);
end

% ---------------- PERSA (Al-Kashi, s.XV) ----------------

function pi_val = kashi_pi(n_digits)
  % Pi de Jamshid Al-Kashi (1424 d.C.), calculado con polígono de
  % 3*2^28 lados (~805 millones), 16 dígitos sexagesimales correctos.
  % Valor sexagesimal registrado: 3;8,29,44,0,47,25,53,10,14,52,35,17,44,15,40
  % (aprox 3.141592653589793 en decimal).
  kashi_sexagesimal = [3, 8, 29, 44, 0, 47, 25, 53, 10, 14, 52, 35, 17, 44, 15, 40];
  pi_val = sexagesimal_to_decimal(kashi_sexagesimal(1:min(n_digits, length(kashi_sexagesimal))));
end

% ---------------- HEBREO (gematria) ----------------

function val = hebrew_gematria(text)
  % Valor gematria por nombres de letras en ingles (Octave no maneja bien
  % UTF-8 multibyte, por lo que no se recibe texto hebreo nativo directamente).
  % Nombres: alef=1 bet=2 gimel=3 dalet=4 he=5 vav=6 zayin=7 het=8 tet=9
  % yod=10 kaf=20 lamed=30 mem=40 nun=50 samekh=60 ayin=70 pe=80 tsadi=90
  % qof=100 res=200 shin=300 tav=400
  % Finales: final_kaf=500 final_mem=600 final_nun=700 final_pe=800
  %          final_tsadi=900
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
    if any(idx)
      val = val + values(idx);
    end
  end
end

function s = hebrew_number_to_text(n)
  % Convierte entero a notación numerica hebrea (aditiva, letras como dígitos).
  % No es una representacion posicional; cada letra suma su valor.
  % Soporta 1..3999 usando ת (400) repetido para los miles.
  if n < 1 || n > 3999
    error('hebrew_number_to_text soporta 1..3999');
  end
  letters = {'ת','ק','ר','ש','צ','ץ','פ','ף','ע','ס','נ','ן','מ','ם','ל','ך','כ','י','ט','ח','ז','ו','ד','ג','ב','א'};
  values  = [400,300,200,100,90,90,80,80,70,60,50,50,40,40,30,20,20,10,9,8,7,6,5,4,3,2,1];
  s = '';
  rem = n;
  for i = 1:length(values)
    while rem >= values(i)
      s = [s, letters{i}];
      rem = rem - values(i);
    end
  end
end

% ---------------- CANANEO (reconstruccion arqueologica) ----------------

function r = cananean_number_to_text(n)
  % Sistema numerico cananeo/fenicio antiguo (reconstruccion):
  % aditivo decimal con signos para 1, 10, 100, 1000 (palos verticales,
  % ganchos, círculos). No hay evidencia de cero posicional.
  % Nota: es una reconstruccion razonable, no una tabla cananica canonica.
  if n < 1 || n > 9999
    error('cananean_number_to_text soporta 1..9999');
  end
  thousands = floor(n / 1000);
  hundreds  = floor(mod(n,1000) / 100);
  tens      = floor(mod(n,100) / 10);
  ones      = mod(n,10);
  s = '';
  for i = 1:thousands, s = [s, '𐤀']; end   % 1000 (signo cananeo aproximado)
  for i = 1:hundreds,  s = [s, '𐤁']; end   % 100
  for i = 1:tens,      s = [s, '𐤂']; end   % 10
  for i = 1:ones,      s = [s, '𐤃']; end   % 1
  r = struct('text', s, 'thousands', thousands, 'hundreds', hundreds, ...
             'tens', tens, 'ones', ones);
end

% ---------------- EGIPCIO (fracciones unitarias) ----------------

function terms = egyptian_unit_fraction(n, d)
  % Descompone n/d en suma de fracciones unitarias 1/k (algoritmo goloso,
  % usado en el Papiro Rhind para la tabla 2/n).
  if n <= 0 || d <= 0
    error('egyptian_unit_fraction requiere n,d > 0');
  end
  terms = [];
  while n > 0
    k = ceil(d / n);
    terms(end+1) = k;
    n = n * k - d;
    d = d * k;
  end
end

function r = egyptian_multiplication(a, b)
  % Multiplicacion egipcia por duplicacion y adición (metodo del papiro Rhind).
  x = a; y = b; acc = 0;
  steps = [];
  while x > 0
    if mod(x, 2) == 1
      acc = acc + y;
    end
    steps(end+1, :) = [x, y, mod(x,2), acc];
    x = floor(x / 2);
    y = y * 2;
  end
  r = struct('result', acc, 'steps', steps);
end

% ---------------- MAYA (base 20) ----------------

function d = maya_to_decimal(digits)
  % Sistema posicional base 20 con cero (concha). digitos: mas significativo primero.
  % Posiciones: 20^0, 20^1, 20^2... (el calendario maya usa 18*20 para el segundo nivel,
  % pero aqui usamos base puramente vigesimal matematica).
  d = 0;
  for i = 1:length(digits)
    d = d + digits(i) * 20^(length(digits)-i);
  end
end

function digits = decimal_to_maya(n, n_positions)
  % Convierte decimal a lista de digitos base 20 (mas significativo primero).
  if nargin < 2, n_positions = 1; end
  digits = zeros(1, n_positions);
  rem = n;
  for i = n_positions:-1:1
    digits(i) = mod(rem, 20);
    rem = floor(rem / 20);
  end
  if rem > 0
    error('decimal_to_maya: n_positions insuficiente');
  end
end

% ---------------- GRIEGO JONICO ----------------

function val = greek_ionic(text)
  % Numeracion alfabetica griega (sistema jónico) por nombres en ASCII.
  % Octave no maneja bien UTF-8 multibyte, por lo que se reciben los nombres
  % de las letras en ingles separados por espacios: "alpha beta gamma".
  % Valores: alpha=1 beta=2 gamma=3 delta=4 epsilon=5 digamma=6 zeta=7
  % eta=8 theta=9 iota=10 kappa=20 lambda=30 mu=40 nu=50 xi=60 omicron=70
  % pi=80 koppa=90 rho=100 sigma=200 tau=300 upsilon=400 phi=500 chi=600
  % psi=700 omega=800 sampi=900
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
    if any(idx)
      val = val + values(idx);
    end
  end
end
