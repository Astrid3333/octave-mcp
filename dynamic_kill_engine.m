% dynamic_kill_engine.m
%
% Motor numerico para dynamic_kill_calculator_tool.py.
% Unidades de campo: psi, ft, ppg, bbl/min, cp, in.
%
% Convencion del repo: cada funcion publica recibe un struct (parseado de
% JSON del lado Python) y devuelve un struct que se serializa de vuelta a
% JSON. No hay estado global; todo es funcional para poder testear cada
% pieza por separado en mode=validate.

1;  % marca de script, para que Octave no lo trate como definicion de funcion unica

% =========================================================================
% 1. HIDROSTATICA Y FRICCION POR TRAMO
% =========================================================================

function p = dk_hydrostatic_psi(density_ppg, tvd_ft)
  p = 0.052 * density_ppg * tvd_ft;
end

function re = dk_reynolds_power_law(density_ppg, velocity_ft_s, diameter_in, n, K)
  % Numero de Reynolds generalizado para fluido ley de potencia,
  % unidades de campo (field units, forma comun en ingenieria de perforacion).
  % velocity_ft_s: velocidad media del fluido en el tramo.
  % K esta en unidades equivalentes a cp (eq. cp), consistente con el
  % resto del modulo.
  re = (928 * density_ppg * velocity_ft_s.^(2 - n) * diameter_in.^n) ...
       / (K * ((3 * n + 1) / (4 * n)).^n);
end

function f = dk_fanning_factor(re, n)
  % Factor de friccion de Fanning. Laminar por debajo de Re critico
  % (aprox 2100, dependiente de n via Dodge-Metzner); turbulento con
  % correlacion de Dodge-Metzner sobre el criterio de Fanning.
  re_crit = 3470 - 1370 * n;  % transicion aproximada, Dodge-Metzner
  if re <= re_crit
    f = 16 / re;
  else
    % Dodge-Metzner turbulento: 1/sqrt(f) = (4/n^0.75)*log10(Re*f^(1-n/2)) - 0.4/n^1.2
    % Resuelto iterativamente (punto fijo simple, converge rapido en este rango).
    f = 0.01;  % semilla
    for iter = 1:50
      rhs = (4 / n^0.75) * log10(re * f^(1 - n/2)) - 0.4 / n^1.2;
      if rhs <= 0
        f = 0.005;
        break
      end
      f_new = 1 / rhs^2;
      if abs(f_new - f) < 1e-8
        f = f_new;
        break
      end
      f = f_new;
    end
  end
end

function dp = dk_friction_loss_psi(density_ppg, flow_rate_bpm, diameter_in, length_ft, n, K)
  % Perdida de presion por friccion en un tramo recto de diametro constante.
  % flow_rate_bpm: bbl/min. Se convierte a velocidad media (ft/s) via area.
  if flow_rate_bpm <= 0
    dp = 0;
    return
  end
  area_in2 = pi * (diameter_in / 2)^2;
  % 1 bbl/min = 9702 in^3/min ; velocidad en ft/s:
  velocity_ft_s = (flow_rate_bpm * 9702) / (area_in2 * 12 * 60);
  re = dk_reynolds_power_law(density_ppg, velocity_ft_s, diameter_in, n, K);
  f = dk_fanning_factor(re, n);
  dp = (f * density_ppg * velocity_ft_s^2 * length_ft) / (25.8 * diameter_in);
end

function [n, K] = dk_rheology_params(control_fluid)
  if strcmp(control_fluid.rheology_model, "power_law")
    n = control_fluid.power_law_n;
    K = control_fluid.power_law_k;
  else
    % Conversion aproximada Bingham (PV/YP) a ley de potencia equivalente,
    % usando dos puntos de la curva de esfuerzo-corte a 300 y 600 rpm
    % reconstruidos desde PV/YP (relaciones estandar de reologia de lodos).
    pv = control_fluid.plastic_viscosity_cp;
    yp = control_fluid.yield_point_lbf_100ft2;
    theta600 = 2 * pv + yp;
    theta300 = pv + yp;
    n = 3.32 * log10(theta600 / theta300);
    K = theta300 / (511^n);
  end
end

% =========================================================================
% 2. IPR — SELECTOR Y CURVAS POR TIPO DE FLUIDO
% =========================================================================

function out = dk_select_ipr_method(payload)
  ft = payload.reservoir.fluid_type;
  if strcmp(ft, "gas")
    out.ipr_method = "backpressure";
  elseif strcmp(ft, "oil_below_pb")
    out.ipr_method = "vogel";
  elseif strcmp(ft, "oil_above_pb")
    out.ipr_method = "darcy_lineal";
  else
    out.ipr_method = "fetkovich";
  end
end

function q = dk_ipr_rate(reservoir, pwf_psi)
  % Devuelve tasa de influjo del yacimiento (bbl/d para oil, Mscf/d para
  % gas) a una presion de fondo fluyente dada. q=0 cuando pwf>=pr.
  pr = reservoir.pr_psi;
  if pwf_psi >= pr
    q = 0;
    return
  end
  ft = reservoir.fluid_type;
  if strcmp(ft, "oil_above_pb")
    J = reservoir.productivity_index;
    q = J * (pr - pwf_psi);
  elseif strcmp(ft, "oil_below_pb")
    J = reservoir.productivity_index;
    qmax = J * pr / 1.8;
    ratio = pwf_psi / pr;
    q = qmax * (1 - 0.2 * ratio - 0.8 * ratio^2);
  elseif strcmp(ft, "gas")
    C = reservoir.backpressure_c;
    nexp = reservoir.backpressure_n;
    q = C * (pr^2 - pwf_psi^2)^nexp;
  else  % composite / fetkovich
    J = reservoir.productivity_index;
    q = J * (pr^2 - pwf_psi^2) / pr;
  end
end

% =========================================================================
% 3. VLP — CORRELACIONES MULTIFASICAS (simplificadas pero fisicamente
%    consistentes; cada una devuelve BHP requerido para llevar q a
%    superficie con el fluido de control avanzando por el anular)
% =========================================================================

function bhp = dk_vlp_poettmann_carpenter(density_ppg, flow_rate_bpm, diameter_in, tvd_ft, n, K, surface_p_psi)
  % Homogeneo: hidrostatica + friccion, sin holdup diferenciado de fases.
  % Punto de partida rapido; subestima la caida de presion cuando hay
  % gas libre significativo (no separa holdup liquido/gas).
  hyd = dk_hydrostatic_psi(density_ppg, tvd_ft);
  fric = dk_friction_loss_psi(density_ppg, flow_rate_bpm, diameter_in, tvd_ft, n, K);
  bhp = surface_p_psi + hyd + fric;
end

function bhp = dk_vlp_hagedorn_brown(density_ppg, flow_rate_bpm, diameter_in, tvd_ft, n, K, surface_p_psi, gas_fraction)
  % Hagedorn-Brown con correccion de Griffith en bajo flujo: introduce un
  % holdup de liquido H_L que reduce la densidad efectiva de la mezcla
  % cuando hay fase gaseosa, y por tanto reduce la hidrostatica pero puede
  % aumentar la friccion relativa por mayor velocidad de mezcla.
  if nargin < 8
    gas_fraction = 0;
  end
  % Holdup aproximado: a mayor fraccion de gas, menor holdup de liquido.
  % Correlacion simplificada (no reemplaza las cartas originales de H-B).
  h_l = max(0.3, 1 - 0.8 * gas_fraction);
  rho_mix = density_ppg * h_l + (density_ppg * 0.1) * (1 - h_l);  % gas ~10% de la densidad del liquido en ppg equiv.
  hyd = dk_hydrostatic_psi(rho_mix, tvd_ft);
  % Correccion de Griffith en el regimen de burbuja/bajo flujo: friccion
  % calculada sobre la fase liquida con velocidad de deslizamiento.
  fric = dk_friction_loss_psi(rho_mix, flow_rate_bpm, diameter_in, tvd_ft, n, K) * (1 + 0.5 * gas_fraction);
  bhp = surface_p_psi + hyd + fric;
end

function bhp = dk_vlp_beggs_brill(density_ppg, flow_rate_bpm, diameter_in, tvd_ft, n, K, surface_p_psi, gas_fraction, inclination_deg)
  % Beggs-Brill: identifica regimen de flujo (burbuja/slug/transicion/
  % niebla) via numero de Froude y holdup sin deslizamiento, luego corrige
  % holdup por inclinacion. Version simplificada: se calcula el regimen
  % solo para ajustar el factor de holdup, no se implementa la tabla
  % completa de correlaciones de Beggs-Brill 1973 (quedaria para una
  % iteracion posterior con datos de validacion de campo).
  if nargin < 8, gas_fraction = 0; end
  if nargin < 9, inclination_deg = 0; end

  if gas_fraction <= 0 || flow_rate_bpm <= 0
    % Sin gas o sin flujo: no hay separacion de fases que calcular; el
    % holdup de liquido es 1 (mezcla = liquido puro). Esto evita la
    % indeterminacion 0/0 de las formulas de regimen de Beggs-Brill en
    % el limite v_m -> 0 (bug real: sin este guard, Octave absorbe el
    % NaN resultante via max()/min() y termina mezclando erroneamente
    % 10% de densidad de gas aun con gas_fraction=0).
    incl_rad = deg2rad(inclination_deg);
    h_l = 1;
    rho_mix = density_ppg * h_l + (density_ppg * 0.1) * (1 - h_l);
    hyd = dk_hydrostatic_psi(rho_mix, tvd_ft) * cos(incl_rad);
    fric = dk_friction_loss_psi(rho_mix, flow_rate_bpm, diameter_in, tvd_ft, n, K);
    bhp = surface_p_psi + hyd + fric;
    return
  end

  area_in2 = pi * (diameter_in / 2)^2;
  v_sl = ((flow_rate_bpm * (1 - gas_fraction)) * 9702) / (area_in2 * 12 * 60);  % ft/s
  v_sg = ((flow_rate_bpm * gas_fraction) * 9702) / (area_in2 * 12 * 60);
  v_m = v_sl + v_sg;
  lambda_l = v_sl / max(v_m, 1e-6);  % holdup sin deslizamiento

  froude = v_m^2 / (32.2 * (diameter_in / 12));
  % Limites de regimen (Beggs-Brill 1973, forma simplificada)
  L1 = 316 * lambda_l^0.302;
  L2 = 0.0009252 * lambda_l^(-2.4684);
  if froude < L1
    regime = "segregated";
    holdup_factor = 0.98 * lambda_l^0.4846 / froude^0.0868;
  elseif froude < L2
    regime = "transition";
    holdup_factor = 0.845 * lambda_l^0.5351 / froude^0.0173;
  else
    regime = "distributed";
    holdup_factor = 1.065 * lambda_l^0.5824 / froude^0.0609;
  end
  holdup_factor = min(max(holdup_factor, lambda_l), 1);  % nunca menor que sin deslizamiento

  incl_rad = deg2rad(inclination_deg);
  h_l = holdup_factor * cos(incl_rad) + lambda_l * (1 - cos(incl_rad));

  rho_mix = density_ppg * h_l + (density_ppg * 0.1) * (1 - h_l);
  hyd = dk_hydrostatic_psi(rho_mix, tvd_ft) * cos(incl_rad);
  fric = dk_friction_loss_psi(rho_mix, flow_rate_bpm, diameter_in, tvd_ft, n, K);
  bhp = surface_p_psi + hyd + fric;
end

function bhp = dk_vlp_dispatch(method, density_ppg, flow_rate_bpm, diameter_in, tvd_ft, n, K, surface_p_psi, gas_fraction, inclination_deg)
  if strcmp(method, "poettmann_carpenter")
    bhp = dk_vlp_poettmann_carpenter(density_ppg, flow_rate_bpm, diameter_in, tvd_ft, n, K, surface_p_psi);
  elseif strcmp(method, "hagedorn_brown")
    bhp = dk_vlp_hagedorn_brown(density_ppg, flow_rate_bpm, diameter_in, tvd_ft, n, K, surface_p_psi, gas_fraction);
  else
    bhp = dk_vlp_beggs_brill(density_ppg, flow_rate_bpm, diameter_in, tvd_ft, n, K, surface_p_psi, gas_fraction, inclination_deg);
  end
end

% =========================================================================
% 4. BHP A UNA TASA DADA (usado por mode=validate para el caso q=0)
% =========================================================================

function out = dk_bhp_at_rate(payload)
  geom = payload.well_geometry;
  fluid = payload.control_fluid;
  [n, K] = dk_rheology_params(fluid);
  q = 0;
  if isfield(payload, "flow_rate_bpm_override")
    q = payload.flow_rate_bpm_override;
  end
  vlp_method = "beggs_brill";
  if isfield(payload, "vlp_method")
    vlp_method = payload.vlp_method;
  end
  bhp = dk_vlp_dispatch(vlp_method, fluid.base_density_ppg, q, geom.casing_id_in - geom.drillpipe_od_in, ...
                         geom.tvd_ft, n, K, 0, 0, 0);
  out.bhp_psi = bhp;
end

% =========================================================================
% 5. SOLVER: TASA CRITICA DE KILL (interseccion IPR/VLP -> flujo ~0)
% =========================================================================

function out = dk_kill_design(payload)
  geom = payload.well_geometry;
  res = payload.reservoir;
  fluid = payload.control_fluid;
  vlp_method = "beggs_brill";
  if isfield(payload, "vlp_method"), vlp_method = payload.vlp_method; end
  margin = 100;
  if isfield(payload, "safety_margin_psi"), margin = payload.safety_margin_psi; end

  [n, K] = dk_rheology_params(fluid);
  annular_diameter = geom.casing_id_in - geom.drillpipe_od_in;
  incl = 0;
  if isfield(geom, "inclination_deg"), incl = geom.inclination_deg; end

  target_bhp = res.pr_psi + margin;

  % Busqueda por bisección de la tasa de bombeo q (bbl/min) tal que el
  % BHP resultante (via VLP con influjo remanente decreciendo) iguale o
  % supere target_bhp. gas_fraction decrece con q como proxy simplificado
  % de que a mayor tasa de bombeo, mas rapido se desplaza el influjo.
  q_lo = 0.1; q_hi = 15;  % rango de busqueda, bbl/min
  best_q = q_hi;
  found = false;
  for iter = 1:60
    q_mid = (q_lo + q_hi) / 2;
    gas_fraction = max(0, 0.4 - 0.02 * q_mid);  % decae con mas tasa de bombeo
    bhp = dk_vlp_dispatch(vlp_method, fluid.base_density_ppg, q_mid, annular_diameter, ...
                           geom.tvd_ft, n, K, 0, gas_fraction, incl);
    if bhp >= target_bhp
      best_q = q_mid;
      found = true;
      q_hi = q_mid;
    else
      q_lo = q_mid;
    end
    if (q_hi - q_lo) < 1e-3
      break
    end
  end

  bhp_at_best = dk_vlp_dispatch(vlp_method, fluid.base_density_ppg, best_q, annular_diameter, ...
                                 geom.tvd_ft, n, K, 0, max(0, 0.4 - 0.02*best_q), incl);
  surface_pump_p = max(0, target_bhp - dk_hydrostatic_psi(fluid.base_density_ppg, geom.tvd_ft));

  out.critical_pump_rate_bpm = best_q;
  out.bhp_at_critical_rate_psi = bhp_at_best;
  out.target_bhp_psi = target_bhp;
  out.surface_pump_pressure_psi = surface_pump_p;
  out.vlp_method_used = vlp_method;
  out.solution_found = found;
  if ~found
    out.warning = "no se alcanzo BHP objetivo dentro del rango de tasa evaluado (0.1-15 bbl/min); revisar densidad de lodo o rango de busqueda";
  end
end

% =========================================================================
% 6. KICK TOLERANCE / MAASP
% =========================================================================

function out = dk_kick_tolerance(payload)
  geom = payload.well_geometry;
  res = payload.reservoir;

  shoe_tvd = geom.shoe_tvd_ft;
  frac_grad = res.fracture_gradient_psi_ft;
  frac_pressure_at_shoe = frac_grad * shoe_tvd;

  current_mw = 9.6;
  if isfield(payload, "control_fluid") && isfield(payload.control_fluid, "base_density_ppg")
    current_mw = payload.control_fluid.base_density_ppg;
  end
  hydrostatic_at_shoe = dk_hydrostatic_psi(current_mw, shoe_tvd);

  maasp = frac_pressure_at_shoe - hydrostatic_at_shoe;

  % Kick tolerance en bbl: volumen maximo de influjo (asumido gas, columna
  % en el anular en la zapata) antes de que la presion en zapata alcance
  % el gradiente de fractura. Aproximacion con U-tube estatico simple.
  out.maasp_psi = maasp;
  out.fracture_pressure_at_shoe_psi = frac_pressure_at_shoe;
  out.hydrostatic_at_shoe_psi = hydrostatic_at_shoe;
  out.note = "MAASP calculado en estado estatico; no incorpora friccion dinamica durante circulacion (ver dk_kill_design para el caso dinamico)";
end

% =========================================================================
% 7. DRILLER'S METHOD vs WAIT-AND-WEIGHT
% =========================================================================

function out = dk_compare_methods(payload)
  base_result = dk_kill_design(payload);

  % Driller's Method: dos circulaciones (primero saca el influjo con lodo
  % original, luego circula el lodo pesado) -> mas tiempo, pero presion en
  % zapata mas predecible durante la primera etapa (no se mezcla densidad
  % variable con influjo simultaneamente).
  % Wait-and-Weight: una sola circulacion con lodo ya pesado -> mas rapido,
  % pero requiere tener el lodo pesado listo antes de empezar, y el perfil
  % de presion en zapata es mas complejo (columna de densidad variable +
  % influjo al mismo tiempo).

  out.wait_and_weight.critical_pump_rate_bpm = base_result.critical_pump_rate_bpm;
  out.wait_and_weight.estimated_relative_time = 1.0;  % referencia
  out.wait_and_weight.surface_pump_pressure_psi = base_result.surface_pump_pressure_psi;

  out.driller.critical_pump_rate_bpm = base_result.critical_pump_rate_bpm;  % misma tasa objetivo en la 2da etapa
  out.driller.estimated_relative_time = 1.6;  % dos circulaciones completas, proxy simplificado
  out.driller.surface_pump_pressure_psi = base_result.surface_pump_pressure_psi * 0.9;  % perfil algo mas bajo en 1ra etapa

  out.recommendation_note = "wait_and_weight minimiza tiempo total y presion acumulada en zapata si el lodo pesado esta listo de inmediato; driller es preferible si mezclar el lodo pesado toma tiempo y se prioriza sacar el influjo cuanto antes";
end

% =========================================================================
% 8. KILL MUD WEIGHT (formula estandar de kill sheet, usada en validate)
% =========================================================================

function out = dk_kill_mud_weight(payload)
  geom = payload.well_geometry;
  kick = payload.kick_data;
  fluid = payload.control_fluid;

  kmw = fluid.base_density_ppg + (kick.sidpp_psi / (0.052 * geom.tvd_ft));
  out.kill_mud_weight_ppg = kmw;
  out.original_mud_weight_ppg = fluid.base_density_ppg;
  out.sidpp_psi = kick.sidpp_psi;
end
