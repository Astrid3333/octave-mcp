1;
% ancestral2.m — Segunda tanda: Ifá (Yoruba), etak (navegación Pacífico),
% series de Madhava (escuela de Kerala). Mismo criterio que ancestral.m:
% funciones Octave nativas, componibles con cualquier otro cálculo.

function r = ifa_cast(bits)
  % Estructura combinatoria binaria del opele (cadena de 8 mitades de
  % semilla, cada una cae convexa=1 o concava=0), documentada por
  % Ron Eglash ("African Fractals", 1999). Devuelve el indice binario
  % 0-255 y su descomposicion en dos tetragramas de 4 bits.
  % NOTA: esto implementa la MECANICA COMBINATORIA (2^8=256 estados,
  % generados recursivamente por pares), no la correspondencia con los
  % 256 nombres tradicionales de Odu Ifá — esa tabla requiere fuente
  % etnografica verificada y no se inventa aqui.
  if numel(bits) ~= 8 || any(bits ~= 0 & bits ~= 1)
    error('ifa_cast espera un vector de 8 bits (0 o 1)');
  end
  idx = 0;
  for i = 1:8
    idx = idx*2 + bits(i);
  end
  upper = 0; lower = 0;
  for i = 1:4
    upper = upper*2 + bits(i);
    lower = lower*2 + bits(i+4);
  end
  r = struct('binary_index', idx, 'upper_tetragram', upper, ...
              'lower_tetragram', lower, 'total_combinations', 256, 'bits', bits);
end

function r = ifa_cast_random(seed)
  % Simula el lanzamiento fisico (cada mitad cae 0/1 con p=0.5),
  % util cuando no se tiene el resultado de un lanzamiento real.
  rand('state', seed);
  bits = round(rand(1,8));
  r = ifa_cast(bits);
  r.seed = seed;
end

function r = etak_deadreckoning(speed_knots, heading_deg, hours, lat0, lon0)
  % Estima de posicion (dead reckoning) por velocidad + rumbo + tiempo,
  % sin instrumentos — el nucleo matematico del sistema etak/paafu descrito
  % por David Lewis en "We, the Navigators" (1972): la isla de referencia
  % se rastrea conceptualmente contra una brujula sideral de 32 puntos
  % (una division del horizonte en 32 sectores, cada uno historicamente
  % anclado a la salida/puesta de una estrella conocida por el navegante).
  % La formula de proyeccion esferica es navegacion estandar exacta;
  % los indices de "casa estelar" son la estructura de 32 sectores, sin
  % asignar aqui nombres tradicionales especificos de estrellas.
  R_nm = 3440.065; % radio terrestre en millas nauticas
  dist_nm = speed_knots * hours;
  brg = deg2rad(heading_deg);
  lat1 = deg2rad(lat0);
  lon1 = deg2rad(lon0);
  ang = dist_nm / R_nm;
  lat2 = asin( sin(lat1)*cos(ang) + cos(lat1)*sin(ang)*cos(brg) );
  lon2 = lon1 + atan2( sin(brg)*sin(ang)*cos(lat1), cos(ang)-sin(lat1)*sin(lat2) );
  star_house = mod(round(heading_deg/11.25), 32); % 32 sectores de 11.25 grados
  r = struct('lat_estimada', rad2deg(lat2), 'lon_estimada', rad2deg(lon2), ...
             'distancia_nm', dist_nm, 'casa_estelar_32', star_house);
end

function r = madhava_pi_series(n_terms)
  % Serie de Madhava-Leibniz para pi/4 = 1 - 1/3 + 1/5 - 1/7 + ...
  % mas el termino de correccion final atribuido a Madhava (escuela de
  % Kerala, s.XIV, documentado en el Yuktibhasa de Jyesthadeva) que
  % acelera la convergencia de orden n^-1 a n^-3 — siglos antes de las
  % tecnicas de aceleracion de Euler. Formula de correccion segun
  % Roy, R. (1990) "Discovery of the Series Formula for Pi by Leibniz,
  % Gregory, and Nicolas", Math. Magazine 63(5) — cita de literatura
  % secundaria, no fuente primaria en sanscrito.
  s = 0;
  sgn = 1;
  for k = 0:(n_terms-1)
    s = s + sgn / (2*k+1);
    sgn = -sgn;
  end
  n = n_terms;
  pi_basic = 4*s;
  correction = n / (2*(n^2+1));
  pi_corrected = 4*(s + sgn*correction/2);
  r = struct('n_terms', n_terms, 'pi_basic', pi_basic, ...
             'pi_corrected', pi_corrected, ...
             'error_basic', abs(pi_basic - pi), ...
             'error_corrected', abs(pi_corrected - pi));
end
