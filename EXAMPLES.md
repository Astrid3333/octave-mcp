# octave-mcp — Guia rapida de ejemplos

Generado automaticamente desde `tools/list` — 170 tools.

## `abstract_algebra`

Algebra abstracta sobre estructuras finitas chicas (orden <=8 para isomorfismo): cayley_table (genera tabla preset Zn_add, Zn_mult, Sn simetrico, Dn diedral), verify_group_axioms (cerradura/asociatividad/identidad/inverso, reporta si es abeliano), verify_ring_field_axioms (axiomas de anillo via grupo abeliano + distributividad, confirma cuerpo si hay inverso multiplicativo para todo no-cero), check_isomorphism (fuerza bruta sobre permutaciones -- respuesta negativa es definitiva para el orden dado, no una sospecha).

Modos disponibles (extraidos de `abstract_algebra_tool.py` via regex — **revisar a mano**):

- `cayley_table`
- `check_isomorphism`
- `validate`
- `verify_group_axioms`
- `verify_ring_field_axioms`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "abstract_algebra",
    "arguments": {
      "mode": "cayley_table",
      "params": {}
    }
  }
}
```

## `acoustics_tool`

Acustica: propagacion de ondas de presion 1D via FDTD (mode='pressure_wave_1d', bordes dirichlet/neumann, preset 'known_first_mode' valida contra solucion analitica); modos de resonancia de cavidades rectangulares rigidas (mode='room_modes', f_nlm=(c/2)*sqrt((nx/Lx)^2+(ny/Ly)^2+(nz/Lz)^2), clasificados axial/tangencial/oblicua); tiempo de reverberacion via formula de Sabine (mode='reverberation_sabine', RT60=0.161*V/A). Complementa infrasound_tool (atenuacion atmosferica a larga distancia) con acustica de interiores. mode='validate' corre los tres casos de referencia.

Modos disponibles:

- `pressure_wave_1d`
- `room_modes`
- `reverberation_sabine`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "acoustics_tool",
    "arguments": {
      "mode": "pressure_wave_1d",
      "params": {}
    }
  }
}
```

## `advanced_probability_tool`

Probabilidad avanzada e inferencia bayesiana: distributions (pdf/cdf/cuantiles/muestreo, 15 distribuciones via scipy.stats, validado contra momentos analiticos), bayesian_inference (Metropolis-Hastings propio, validado contra posteriores conjugados EXACTOS Beta-Binomial y Normal-Normal, mas regresion lineal bayesiana), model_comparison (WAIC y LOO por importance sampling, validado con caso sintetico donde el modelo verdadero gana), posterior_predictive (p-value predictivo posterior con estadistico de prueba, calibracion verificada, con nota sobre el conservadurismo conocido del metodo).

Modos disponibles:

- `distributions`
- `bayesian_inference`
- `model_comparison`
- `posterior_predictive`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "advanced_probability_tool",
    "arguments": {
      "mode": "distributions",
      "params": {}
    }
  }
}
```

## `advanced_stochastic_tool`

Procesos estocasticos avanzados: HMM (forward-backward + Viterbi), filtro de Kalman, particle filter (bootstrap), y GARCH(1,1) por MLE.

Modos disponibles:

- `hmm`
- `kalman`
- `particle_filter`
- `garch`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "advanced_stochastic_tool",
    "arguments": {
      "mode": "hmm",
      "params": {}
    }
  }
}
```

## `ancestral_octave`

Corre metodos ancestrales (suanpan_add, chinese_remainder, vedic_multiply, archimedes_pi, quipu_encode) como funciones Octave NATIVAS via ancestral.m, en el mismo motor que octave_run. extra_octave permite componer con otro codigo Octave en la misma sesion. mode='validate' corre checks matematicos contra valores conocidos, sin necesitar preset.

Modos disponibles:

- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "ancestral_octave",
    "arguments": {
      "mode": "validate",
      "params": {}
    }
  }
}
```

## `ancient_calculator`

Simula calculadoras historicas reales operando sus cuentas/fichas: suanpan, soroban, roman_hand_abacus, yupana_depasquale (hipotesis en disputa academica, ver advertencia en la respuesta).

Parametros directos (sin `mode`):

- `preset`
- `params`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "ancient_calculator",
    "arguments": {
      "preset": null,
      "params": null
    }
  }
}
```

## `antibiotic_diffusion`

Bioensayo de difusion en disco tipo Kirby-Bauer: difusion radial 2D exacta (Carslaw & Jaeger, disco de concentracion uniforme C0 en agar homogeneo) mas la aproximacion clasica de fuente puntual de Cooper. Liberacion instantanea, sin degradacion ni consumo bacteriano -- estimacion de ordenes de magnitud, no reemplaza ensayo real. Modes: zone_prediction (radio/diametro de halo a un C0 y tiempo de in

Modos disponibles (extraidos de `antibiotic_diffusion.py` via regex — **revisar a mano**):

- `calibration_curve`
- `validate`
- `zone_prediction`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "antibiotic_diffusion",
    "arguments": {
      "mode": "calibration_curve",
      "params": {}
    }
  }
}
```

## `archaeoastronomy`

Calculos astronomicos para datacion y arqueoastronomia via algoritmos de Meeus (baja precision, sin efemerides externas): posicion solar y lunar (longitud eclíptica, ascension recta, declinacion) para cualquier fecha desde ~1000 a.C., fecha de equinoccios/solsticios de un ano dado, conversion a dia juliano, y verificacion de alineamientos arqueologicos (dado azimut y latitud de un sitio, calcula la declinacion implicada y la compara contra solsticios/lunisticios).

Modos disponibles:

- `solar_position`
- `lunar_position`
- `equinox_solstice`
- `alignment_check`
- `julian_day`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "archaeoastronomy",
    "arguments": {
      "mode": "solar_position",
      "params": {}
    }
  }
}
```

## `archaeological_simulation`

Simulacion de dinamicas socio-demograficas arqueologicas: malthusian_growth (crecimiento logistico con capacidad de carga variable por ciclos climaticos), technology_diffusion (modelo de Bass de adopcion de innovaciones, solucion analitica cerrada), trade_network (modelo gravitacional de rutas comerciales entre asentamientos, identifica el hub por centralidad de autovector), collapse_dynamics (ciclo auge-colapso poblacion/recursos tipo Rosenzweig-MacArthur, analogo a los secular cycles de Turchin).

Modos disponibles:

- `malthusian_growth`
- `technology_diffusion`
- `trade_network`
- `collapse_dynamics`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "archaeological_simulation",
    "arguments": {
      "mode": "malthusian_growth",
      "params": {}
    }
  }
}
```

## `audio_processing_tool`

Procesamiento de señales de audio: analisis armonico con medicion de amplitudes/THD via FFT de muestreo coherente (mode='harmonics'), generacion de barridos (chirp) lineales y logaritmicos con verificacion de frecuencia instantanea via fase de Hilbert (mode='tone_sweep'), y filtro FIR pasa-bajos por ventaneado de sinc (Hamming) con verificacion de ganancia en banda pasante y atenuacion en banda rechazada (mode='audio_filter'). mode='validate' corre los 3 self-tests.

Modos disponibles:

- `harmonics`
- `tone_sweep`
- `audio_filter`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "audio_processing_tool",
    "arguments": {
      "mode": "harmonics",
      "params": {}
    }
  }
}
```

## `bacterial_growth_tool`

Curvas de crecimiento bacteriano via modelo de Baranyi-Roberts (RK4 sobre el sistema y/q) y modelo de Gompertz modificado (Zwietering et al. 1990), mas ajuste no lineal de Gompertz a datos experimentales (t, log N). mode='baranyi_roberts' (mu_max, y0, y_max, h0, t_max); mode='gompertz' (A, mu_max, lambda_lag, t_max); mode='fit_growth_curve' (t_data, log_n_data); mode='validate' corre ambos modelos y un fit sintetico.

Modos disponibles:

- `baranyi_roberts`
- `gompertz`
- `fit_growth_curve`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "bacterial_growth_tool",
    "arguments": {
      "mode": "baranyi_roberts",
      "params": {}
    }
  }
}
```

## `biorefinery_tool`

Balances de masa/energia y cinetica quimica para procesos de conversion de biomasa a biocombustible (pirolisis, hidrotratamiento, fermentacion, etc). mode='mass_balance': balance de masa global en estado estacionario, resuelve una incognita o reporta error de cierre. mode='energy_balance': balance de energia (calor sensible+latente) via entalpias especificas, resuelve Q o reporta cierre. mode='hhv_correlation': estima poder calorifico superior e inferior (HHV/LHV) a partir de composicion elemental C/H/O/N/S/Ash via correlacion de Channiwala-Parikh (2002). mode='yield_efficiency': rendimientos masicos y energeticos de producto(s) respecto a la materia prima, y eficiencia energetica global del proceso. mode='arrhenius': k=A*exp(-Ea/RT) directo, o resuelve Ea/A por dos puntos (T,k) o por regresion lineal ln(k) vs 1/T sobre 3+ puntos (con R^2 del ajuste). mode='rate_law': velocidad de reaccion de orden general multi-reactivo, -r=k*prod(C_i^orden_i). mode='batch_conversion': formas integradas orden 0/1/2 para reactor batch, resuelve t o X (conversion) dado el otro, mas concentracion y vida media. mode='pyrolysis_yield': distribucion tipica de productos (liquido/char/gas) por regimen de pirolisis (lenta/intermedia/rapida/gasificacion), explicito o clasificado desde velocidad de calentamiento/residencia/T_pico, via valores de referencia de Bridgwater (2012). mode='hdo_stoichiometry': consumo de H2 y coproductos (H2O/CO/CO2) en hidrodesoxigenacion, repartido entre rutas HDO/DCO/DCO2 segun el O removido. mode='hdo_degree': grado de desoxigenacion (%DOD, masa y molar O/C) y razon H/C molar (Van Krevelen) entre carga y producto de hidrotratamiento.

Modos disponibles:

- `mass_balance`
- `energy_balance`
- `hhv_correlation`
- `yield_efficiency`
- `arrhenius`
- `rate_law`
- `batch_conversion`
- `pyrolysis_yield`
- `hdo_stoichiometry`
- `hdo_degree`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "biorefinery_tool",
    "arguments": {
      "mode": "mass_balance",
      "params": {}
    }
  }
}
```

## `braid_group`

Grupos de trenzas y anyones de Fibonacci: verify_braid_relation (unitariedad + relacion de Yang-Baxter), apply_braid_sequence (aplica una secuencia de trenzas a un estado inicial, preserva la norma). Basado en Bonesteel et al 2005. Conexion con computacion cuantica topologica y con persistent_homology_tool / linear_algebra_tool.

Modos disponibles:

- `verify_braid_relation`
- `apply_braid_sequence`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "braid_group",
    "arguments": {
      "mode": "verify_braid_relation",
      "params": {}
    }
  }
}
```

## `budgeting_tool`

Generación de presupuestos de construcción: costo directo de partidas, análisis de precio unitario (APU: materiales + mano de obra + equipo), aplicación de gastos generales/utilidad/contingencia/impuesto sobre un costo directo, escalamiento compuesto por inflación, y presupuesto agregado por capítulos.

Modos disponibles:

- `direct_cost`
- `apply_markups`
- `unit_price_analysis`
- `escalation`
- `budget_summary`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "budgeting_tool",
    "arguments": {
      "mode": "direct_cost",
      "params": {}
    }
  }
}
```

## `cfd_tool`

Dinamica de fluidos computacional: flujo de Poiseuille plano (Stokes flow, validado contra solucion analitica exacta) y cavidad con tapa movil (lid-driven cavity, Navier-Stokes 2D laminar via vorticidad-funcion de corriente, validado contra el benchmark de Ghia, Ghia & Shin 1982).

Modos disponibles:

- `poiseuille_flow`
- `lid_driven_cavity`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "cfd_tool",
    "arguments": {
      "mode": "poiseuille_flow",
      "params": {}
    }
  }
}
```

## `chemometrics_tool`

Calibracion multivariante (PLS/PCR), diseno experimental (DOE) y espectroscopia sintetica (FTIR/RMN). Modos disponibles: generate_synthetic_spectra, pls_calibration, pcr_calibration, doe_design, validate_recovery. Este ultimo conecta con enzyme_kinetics_tool y reaction_diffusion_tool: toma concentraciones 'reales' generadas por esos tools, las convierte a espectros sinteticos ruidosos, y mide que tan bien PLS/PCR las recupera.

Modos disponibles:

- `generate_synthetic_spectra`
- `pls_calibration`
- `pcr_calibration`
- `doe_design`
- `validate_recovery`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "chemometrics_tool",
    "arguments": {
      "mode": "generate_synthetic_spectra",
      "params": {}
    }
  }
}
```

## `circuit_tool`

Analisis nodal modificado (MNA) de circuitos resistivos con fuentes de voltaje y corriente independientes. mode='validate' corre casos analiticos conocidos (divisor de voltaje, Ley de Ohm con fuente de corriente, deteccion de topologia degenerada) y un stress test de conservacion de energia sobre circuitos aleatorios. mode='nodal_analysis' resuelve un circuito dado: num_nodes (nodos no-tierra, nodo 0 = tierra), resistors=[[a,b,R],...], voltage_sources=[[nodo_pos,nodo_neg,V],...], current_sources=[[nodo_desde,nodo_hacia,I],...]. mode='stress_test' corre n_trials circuitos aleatorios y reporta estadisticas de conservacion de energia.

Modos disponibles:

- `validate`
- `nodal_analysis`
- `stress_test`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "circuit_tool",
    "arguments": {
      "mode": "validate",
      "params": {}
    }
  }
}
```

## `climate_scenario_tool`

Analisis de escenarios climaticos: trend_analysis (regresion lineal, Mann-Kendall, changepoint CUSUM sobre series temporales), rcp_projection (proyeccion de temperatura/nivel del mar para un RCP y anio dado), list_rcp_scenarios (catalogo RCP2.6/4.5/6.0/8.5 con datos IPCC AR5), validate.

Modos disponibles (extraidos de `climate_scenario_tool.py` via regex — **revisar a mano**):

- `list_rcp_scenarios`
- `rcp_projection`
- `trend_analysis`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "climate_scenario_tool",
    "arguments": {
      "mode": "list_rcp_scenarios",
      "params": {}
    }
  }
}
```

## `climate_tool`

Fisica climatica especifica con validacion analitica. Modos: energy_balance_ebm (balance de energia 0-D, punto de equilibrio T_eq), newton_cooling_trend (relajacion exponencial dT/dt=-k(T-Ta), proyeccion de series cortas), carbon_cycle_box (modelo de cajas atmosfera-oceano-tierra, conservacion de masa), bifurcation_snowball (histeresis albedo-temperatura tipo Budyko-Sellers, Snowball Earth).

Modos disponibles:

- `energy_balance_ebm`
- `newton_cooling_trend`
- `carbon_cycle_box`
- `bifurcation_snowball`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "climate_tool",
    "arguments": {
      "mode": "energy_balance_ebm",
      "params": {}
    }
  }
}
```

## `clustering_tool`

Clustering y reduccion de dimensionalidad: kmeans (particional, silhouette + davies-bouldin score), hierarchical (aglomerativo, linkage single/complete/average, con dendrograma), pca_extended (componentes principales, varianza explicada, contribuciones por variable).

Modos disponibles:

- `kmeans`
- `hierarchical`
- `pca_extended`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "clustering_tool",
    "arguments": {
      "mode": "kmeans",
      "params": {}
    }
  }
}
```

## `compute_bifurcation_diagram`

Genera un diagrama de bifurcación para un mapa iterativo 1D (x_next = f(x,r)), barriendo un rango de r y guardando los puntos del atractor tras un transitorio. Presets: logistic, sine, cubic, tent, o custom. Opcionalmente analiza estabilidad (vía derivada) en valores de r específicos.

Parametros directos (sin `mode`):

- `map_name`
- `custom_expr`
- `r_range`
- `x0`
- `n_r_values`
- `n_transient`
- `n_keep`
- `stability_check_rs`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "compute_bifurcation_diagram",
    "arguments": {
      "map_name": null,
      "custom_expr": null,
      "r_range": null,
      "x0": null,
      "n_r_values": null,
      "n_transient": null,
      "n_keep": null,
      "stability_check_rs": null
    }
  }
}
```

## `compute_gradient_hessian`

Calcula el gradiente (order=1) o gradiente + hessiano (order=2) de una funcion escalar f(x1,...,xn) por diferenciacion simbolica exacta (sympy).

Parametros directos (sin `mode`):

- `expression`
- `variables`
- `order`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "compute_gradient_hessian",
    "arguments": {
      "expression": null,
      "variables": null,
      "order": null
    }
  }
}
```

## `compute_hilbert_transform`

Calcula la transformada de Hilbert de una serie temporal no estacionaria y extrae envolvente (amplitud instantánea), fase instantánea y frecuencia instantánea vía la señal analítica. Incluye presets sintéticos (am_chirp, fm_chirp, noisy_am) para validar el método, o acepta una señal custom (ej. mediciones de campo eléctrico atmosférico).

Parametros directos (sin `mode`):

- `preset`
- `signal`
- `fs`
- `duration`
- `detrend`
- `n_output_points`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "compute_hilbert_transform",
    "arguments": {
      "preset": null,
      "signal": null,
      "fs": null,
      "duration": null,
      "detrend": null,
      "n_output_points": null
    }
  }
}
```

## `compute_jacobian`

Calcula el Jacobiano de un sistema de funciones vectorial F(x1,...,xn) -> R^m, con determinante si la matriz es cuadrada.

Parametros directos (sin `mode`):

- `expressions`
- `variables`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "compute_jacobian",
    "arguments": {
      "expressions": null,
      "variables": null
    }
  }
}
```

## `compute_lyapunov_exponent`

Calcula el exponente de Lyapunov máximo (λ1) de un sistema dinámico (presets: chen_lee, burke_shaw, lorenz, rossler, o ecuaciones custom) para cuantificar caos. λ1>0 confirma comportamiento caótico.

Parametros directos (sin `mode`):

- `system`
- `custom_equations`
- `custom_params`
- `y0`
- `dt`
- `n_steps`
- `d0`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "compute_lyapunov_exponent",
    "arguments": {
      "system": null,
      "custom_equations": null,
      "custom_params": null,
      "y0": null,
      "dt": null,
      "n_steps": null,
      "d0": null
    }
  }
}
```

## `compute_lyapunov_v2`

Calcula el exponente de Lyapunov maximo (lambda1) de un sistema dinamico (presets: chen_lee, burke_shaw, lorenz, rossler, o ecuaciones custom) para cuantificar caos. lambda1>0 confirma comportamiento caotico. Si se indica run_id, guarda la trayectoria completa en el workspace (util para graficar el atractor despues con plot_tool).

Parametros directos (sin `mode`):

- `system`
- `custom_equations`
- `custom_params`
- `y0`
- `dt`
- `n_steps`
- `d0`
- `run_id`
- `save_trajectory_every`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "compute_lyapunov_v2",
    "arguments": {
      "system": null,
      "custom_equations": null,
      "custom_params": null,
      "y0": null,
      "dt": null,
      "n_steps": null,
      "d0": null,
      "run_id": null,
      "save_trajectory_every": null
    }
  }
}
```

## `construction_scheduling_tool`

Planificación de obra: ruta crítica vía CPM (early/late start-finish, holguras, duración total del proyecto), perfil diario de demanda de recursos a partir de un cronograma, y compresión de cronograma (crashing) por menor pendiente de costo hacia una reducción de duración objetivo.

Modos disponibles:

- `critical_path`
- `resource_loading`
- `crash_schedule`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "construction_scheduling_tool",
    "arguments": {
      "mode": "critical_path",
      "params": {}
    }
  }
}
```

## `control_theory`

Teoria de control: respuesta a escalon de lazo PID cerrado, estabilidad de Routh-Hurwitz (sin resolver raices), lugar de raices (polos vs ganancia K), y control OGY para estabilizar orbitas periodicas inestables de mapas caoticos via perturbaciones pequenas de parametro.

Modos disponibles:

- `pid_step_response`
- `routh_hurwitz`
- `root_locus`
- `ogy_control`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "control_theory",
    "arguments": {
      "mode": "pid_step_response",
      "params": {}
    }
  }
}
```

## `cosmological_mcmc_tool`

MCMC (Metropolis-Hastings self-contained) para ajustar un modelo LCDM plano con techo holonomico tipo LQG (fase 3 de semiclassical_cosmology_tool) contra H(z). mode=mock_recovery: genera datos sinteticos con parametros conocidos y verifica que el sampler los recupera dentro de 2 sigma. mode=fit_hz_chronometers: ajusta contra la compilacion real de 31 mediciones de H(z) por cronometros cosmicos (Marra & Sapone 2018), devolviendo posteriors de H0 y Om0 y una cota inferior sobre rho_c (no constrenido por datos de bajo z, resultado fisico esperado).

Modos disponibles:

- `mock_recovery`
- `fit_hz_chronometers`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "cosmological_mcmc_tool",
    "arguments": {
      "mode": "mock_recovery",
      "params": {}
    }
  }
}
```

## `credit_simulation_tool`

Motor de amortizacion de creditos (sistema frances, cuota fija): payment_calculator (cuota mensual, total pagado, total interes), amortization_schedule (tabla de amortizacion, detail='summary' agrega por anio o 'full' cuota a cuota hasta 120 periodos), extra_payment_impact (compara credito base vs con pago extra mensual y/o abono unico -- meses e interes ahorrados), credit_card_payoff (saldo revolvente con pago minimo %-del-saldo o pago fijo, detecta 'trampa del pago minimo' e interes que excede el capital), affordability_check (DTI front-end/back-end vs heuristica 28/36, clasificacion descriptiva). Motor fundacional de la Fase D: debt_snowball_tool y refinance_analysis_tool importan directamente _standard_payment y _amortization_schedule de este modulo. confidence_flag 'alta' (formulas cerradas estandar o iteracion aritmetica determinista). No es asesoria financiera ni oferta de credito real. validate corre 5 checks de referencia.

Modos disponibles:

- `payment_calculator`
- `amortization_schedule`
- `extra_payment_impact`
- `credit_card_payoff`
- `affordability_check`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "credit_simulation_tool",
    "arguments": {
      "mode": "payment_calculator",
      "params": {}
    }
  }
}
```

## `critical_infrastructure_tool`

Resiliencia de infraestructura critica modelada como grafo: network_redundancy_n1 (identifica aristas cuya remocion desconecta la red, single point of failure a nivel de enlace, via BFS), cascading_failure_simulation (falla en cascada por sobrecarga: nodo falla si load>capacity, redistribuye excedente a vecinos activos proporcional al headroom disponible, itera hasta estabilizar), load_redistribution (un paso de redistribucion de carga desde un nodo dado), critical_node_identification (betweenness centrality exacta via algoritmo de Brandes, ranking de nodos por criticidad estructural), validate (suite de 10 checks). Algoritmos de grafo manuales (BFS, Brandes), sin dependencias externas. confidence_flag 'media' en cascading_failure_simulation (modelo de redistribucion proporcional es una aproximacion), 'alta' en el resto.

Modos disponibles (extraidos de `critical_infrastructure_tool.py` via regex — **revisar a mano**):

- `cascading_failure_simulation`
- `critical_node_identification`
- `load_redistribution`
- `network_redundancy_n1`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "critical_infrastructure_tool",
    "arguments": {
      "mode": "cascading_failure_simulation",
      "params": {}
    }
  }
}
```

## `cross_validation`

Valida un resultado de dimension fractal corriendo el mismo sistema dinamico con dos motores numericos independientes (Octave ode45 y scipy RK45). Devuelve ambas dimensiones, la diferencia relativa, y un flag cross_validated. Sistemas disponibles: chen_lee. mode='validate' corre un check rapido (resolucion reducida) contra el mismo mecanismo.

Modos disponibles:

- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "cross_validation",
    "arguments": {
      "mode": "validate",
      "params": {}
    }
  }
}
```

## `debt_snowball_tool`

Estrategias de pago de multiples deudas con motor de simulacion mes-a-mes. Modos: snowball (prioriza pagar primero la deuda de menor balance, aunque no sea la de mayor tasa -- beneficio psicologico de cerrar deudas rapido), avalanche (prioriza la deuda de mayor tasa de interes -- matematicamente optimo para minimizar interes total pagado), compare (corre ambas estrategias sobre el mismo set de deudas y devuelve el ahorro en interes y en tiempo de avalanche sobre snowball), validate (autochequeos internos).

Modos disponibles:

- `snowball`
- `avalanche`
- `compare`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "debt_snowball_tool",
    "arguments": {
      "mode": "snowball",
      "params": {}
    }
  }
}
```

## `decision_support_tool`

Sistemas de apoyo a decisiones multicriterio para priorizacion de inversiones publicas: ahp (Proceso Analitico Jerarquico de Saaty, pesos via autovector principal y ratio de consistencia CR), topsis (ordenamiento de alternativas por cercania a la solucion ideal, con criterios de beneficio/costo y pesos configurables).

Modos disponibles (extraidos de `decision_support_tool.py` via regex — **revisar a mano**):

- `ahp`
- `topsis`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "decision_support_tool",
    "arguments": {
      "mode": "ahp",
      "params": {}
    }
  }
}
```

## `disaster_economics_tool`

Economia de desastres para evaluacion de politica publica: direct_indirect_loss (perdida indirecta via multiplicador economico regional, indirect=direct*(m-1)), business_interruption_loss (perdida acumulada por interrupcion de actividad economica durante una recuperacion exponencial hacia el nivel pre-desastre, integral cerrada), benefit_cost_ratio (BCR de una inversion de mitigacion: VAN de la perdida anual esperada evitada vs costo de inversion, a tasa de descuento y horizonte dados), gdp_impact_icor (impacto en el flujo de producto por destruccion de stock de capital via ratio incremental capital-producto ICOR), validate (suite de 10 checks). Motor generico: no trae catalogo de multiplicadores/ICOR por region o sector (los provee quien llama), confidence_flag 'alta' para toda la mecanica.

Modos disponibles (extraidos de `disaster_economics_tool.py` via regex — **revisar a mano**):

- `benefit_cost_ratio`
- `business_interruption_loss`
- `direct_indirect_loss`
- `gdp_impact_icor`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "disaster_economics_tool",
    "arguments": {
      "mode": "benefit_cost_ratio",
      "params": {}
    }
  }
}
```

## `disaster_simulation_tool`

Simulacion Monte Carlo de desastres (modelo actuarial frecuencia-severidad Poisson-LogNormal) para gestion publica de riesgos: monte_carlo_losses (distribucion de perdida agregada anual dado lambda de frecuencia y mu/sigma de severidad lognormal, con VaR y CVaR/Tail-VaR a percentiles configurables), return_period_loss (perdida esperada para periodos de retorno dados, estimador empirico de Weibull T=(n+1)/m, consistente con natural_hazard_risk_tool.gumbel_return_period), exceedance_curve (curva de probabilidad de excedencia anual -EP curve- para una lista de umbrales de perdida), multi_hazard_combine (combina dos peligros independientes o correlacionados via copula gaussiana en una perdida agregada conjunta), validate (suite de 10 checks). Motor generico: no trae catalogo de parametros por tipo de peligro (lambda/mu/sigma los provee quien llama), confidence_flag 'alta' para toda la mecanica estadistica.

Modos disponibles (extraidos de `disaster_simulation_tool.py` via regex — **revisar a mano**):

- `exceedance_curve`
- `monte_carlo_losses`
- `multi_hazard_combine`
- `return_period_loss`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "disaster_simulation_tool",
    "arguments": {
      "mode": "exceedance_curve",
      "params": {}
    }
  }
}
```

## `dispersion_relation_tool`

Relaciones de dispersion de ondas en distintos medios: plasma no magnetizado (EM o Langmuir/Bohm-Gross, mode='plasma'), ondas de gravedad-capilaridad en agua de profundidad finita con limites de aguas profundas/someras (mode='water_waves'), y estructura de bandas de un medio periodico 1D bilaminar via matriz de transferencia de Bloch, con apertura de gap por contraste de impedancia (mode='periodic_medium'). mode='validate' corre los 3 self-tests.

Modos disponibles:

- `plasma`
- `water_waves`
- `periodic_medium`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "dispersion_relation_tool",
    "arguments": {
      "mode": "plasma",
      "params": {}
    }
  }
}
```

## `distmesh_tool`

Generacion de malla triangular 2D via el algoritmo distmesh de Persson & Strang (2004): modela la malla como una celosia de resortes que busca una longitud de arista objetivo, resolviendo un equilibrio de fuerzas sobre una triangulacion de Delaunay que se recalcula al moverse los nodos. mode='mesh_2d' genera la malla sobre un dominio preset (rectangle, circle, circle_with_hole) o custom (funcion de distancia con signo via expresion sympy en x,y). mode='mesh_quality' analiza angulo minimo y relacion de aspecto de una malla externa (points+triangles). mode='validate' corre el caso canonico del circulo unitario y chequea convergencia y calidad.

Modos disponibles:

- `mesh_2d`
- `mesh_quality`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "distmesh_tool",
    "arguments": {
      "mode": "mesh_2d",
      "params": {}
    }
  }
}
```

## `early_warning_tool`

Analisis de series temporales para alertas tempranas: threshold_crossing (cruce de umbrales tipo semaforo con proyeccion de tiempo hasta el proximo umbral), trend_analysis (regresion lineal, pendiente y R2), rate_of_change_alert (tasa de cambio y deteccion de subidas/bajadas criticas), moving_average_anomaly (deteccion de anomalias contra media movil trailing).

Modos disponibles (extraidos de `early_warning_tool.py` via regex — **revisar a mano**):

- `moving_average_anomaly`
- `rate_of_change_alert`
- `threshold_crossing`
- `trend_analysis`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "early_warning_tool",
    "arguments": {
      "mode": "moving_average_anomaly",
      "params": {}
    }
  }
}
```

## `earthquake_analysis_tool`

Peligrosidad sismica para gestion publica municipal: deterministic (atenuacion de Esteva PGA=5700*exp(0.8M)/(R+40)^2, amplificacion de sitio tipo NEHRP simplificado por clase de suelo A-E, conversion PGA->MMI de Wald et al.), psha (recurrencia Gutenberg-Richter, curva de peligrosidad tasa de excedencia vs PGA, inversion por biseccion a PGA de diseno para un periodo de retorno dado, ej. 475 anios), validate (suite de 9 checks).

Modos disponibles (extraidos de `earthquake_analysis_tool.py` via regex — **revisar a mano**):

- `deterministic`
- `psha`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "earthquake_analysis_tool",
    "arguments": {
      "mode": "deterministic",
      "params": {}
    }
  }
}
```

## `earthworks`

Movimiento de tierras a escala de trazado/terreno: volumen entre secciones transversales (método del área media), volumen de corte/relleno sobre una grilla de profundidades (terreno irregular), conversión de volumen banco/suelto/compactado por esponjamiento y contracción, y diagrama de masas acumulado con puntos de balance. Complementa quantity_takeoff (excavation_volume), que solo cubre prismas simples con talud.

Parametros directos (sin `mode`):

- `operation`
- `sections`
- `prismoidal`
- `depths`
- `dx`
- `dy`
- `bank_volume`
- `swell_factor`
- `shrinkage_factor`
- `stations`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "earthworks",
    "arguments": {
      "operation": null,
      "sections": null,
      "prismoidal": null,
      "depths": null,
      "dx": null,
      "dy": null,
      "bank_volume": null,
      "swell_factor": null,
      "shrinkage_factor": null,
      "stations": null
    }
  }
}
```

## `econometrics_tool`

Econometria: series temporales (ARIMA/GARCH), cointegracion (Engle-Granger, ADF), modelos de panel (efectos fijos), variables instrumentales (2SLS), causalidad de Granger. Modos disponibles: adf_test, arima_forecast, garch_fit, engle_granger_coint, panel_fixed_effects, iv_2sls, granger_causality. Complementa statistics_tool y cross_validation_tool (usar particionado walk-forward para series temporales, no k-fold random).

Modos disponibles:

- `adf_test`
- `arima_forecast`
- `garch_fit`
- `engle_granger_coint`
- `panel_fixed_effects`
- `iv_2sls`
- `granger_causality`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "econometrics_tool",
    "arguments": {
      "mode": "adf_test",
      "params": {}
    }
  }
}
```

## `education_funding_tool`

Planificacion de ahorro para educacion: cost_projection (costo futuro proyectado con inflacion educativa propia, distinta de la inflacion general), required_savings_plan (aporte periodico necesario dado ahorro ya acumulado, retorno esperado y anios hasta el inicio), funding_gap_analysis (ahorro proyectado bajo el plan actual vs la meta, banda cualitativa sin_plan/insuficiente/por_debajo_de_la_meta/cubierto/sobre_financiado), multi_child_allocation (reparte un presupuesto de ahorro mensual entre varios hijos proporcional a su necesidad, marca si cada uno individualmente alcanza su meta). confidence_flag 'alta' para la mecanica de interes compuesto (formulas cerradas deterministicas); costos, inflacion educativa y retornos futuros son supuestos de quien llama, no una prediccion. No es asesoria financiera. validate corre 8 checks de referencia.

Modos disponibles:

- `cost_projection`
- `required_savings_plan`
- `funding_gap_analysis`
- `multi_child_allocation`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "education_funding_tool",
    "arguments": {
      "mode": "cost_projection",
      "params": {}
    }
  }
}
```

## `electromagnetic_tool`

Simulaciones electromagneticas: propagacion de onda E/H via FDTD leapfrog con bordes PEC (mode='wave_1d'), deteccion de band gaps en cristales fotonicos 1D via matriz de transferencia y condicion de Bloch (mode='photonic_bandgap'), modos TE/TM y frecuencias de corte en guia de onda rectangular metalica (mode='waveguide_modes'), y elipse de polarizacion via parametros de Stokes de una onda plana (mode='polarization_state'). mode='validate' corre los 4 self-tests contra resultados analiticos conocidos.

Modos disponibles:

- `wave_1d`
- `photonic_bandgap`
- `waveguide_modes`
- `polarization_state`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "electromagnetic_tool",
    "arguments": {
      "mode": "wave_1d",
      "params": {}
    }
  }
}
```

## `emergency_fund_tool`

Fondo de emergencia: coverage_target (monto objetivo dado gasto mensual esencial y meses de cobertura deseados), current_coverage_months (meses de gasto que cubre el ahorro actual), funding_timeline (meses para alcanzar la meta dado aporte mensual y retorno esperado, formula cerrada via logaritmo), risk_adjusted_target (ajusta meses de cobertura recomendados segun factores de riesgo: ingreso unico, dependientes, empleo inestable, trabajo independiente). confidence_flag 'alta' para la mecanica de interes compuesto y el despeje algebraico de meses (deterministicos); los meses de cobertura recomendados en risk_adjusted_target son una heuristica de referencia, no una regla universal. No es asesoria financiera. validate corre 8 checks.

Modos disponibles:

- `coverage_target`
- `current_coverage_months`
- `funding_timeline`
- `risk_adjusted_target`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "emergency_fund_tool",
    "arguments": {
      "mode": "coverage_target",
      "params": {}
    }
  }
}
```

## `entropy_structure`

Calcula entropia de orden 0 y entropia condicional de orden 1 sobre una secuencia de simbolos, para evaluar evidencia de estructura combinatoria (compatible con codificacion tipo-lenguaje) vs. conteo simple/tally marks. Presets sinteticos validados (random_iid, markov_structured) o custom via 'sequence' con datos reales (khipu, yupana, corpus sin descifrar, etc).

Parametros directos (sin `mode`):

- `preset`
- `sequence`
- `alphabet_size`
- `n_symbols`
- `seed`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "entropy_structure",
    "arguments": {
      "preset": null,
      "sequence": null,
      "alphabet_size": null,
      "n_symbols": null,
      "seed": null
    }
  }
}
```

## `enzyme_kinetics`

Cinetica enzimatica: full_kinetics (E+S<->ES->E+P completo), michaelis_menten (aproximacion QSSA), compare (valida cuando la aproximacion es correcta, E0<<S0).

Modos disponibles:

- `full_kinetics`
- `michaelis_menten`
- `compare`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "enzyme_kinetics",
    "arguments": {
      "mode": "full_kinetics",
      "params": {}
    }
  }
}
```

## `enzyme_stochastic`

Simulacion estocastica exacta (Gillespie SSA) de la cinetica enzimatica completa E+S<->ES->E+P en numero discreto de moleculas. Complementa a enzyme_kinetics_tool (determinista/ODE), relevante cuando E0/S0 son chicos y el ruido molecular importa. mode='gillespie_michaelis_menten' (una trayectoria: k1, km1, k2, E0, S0, t_max, seed); mode='gillespie_ensemble' (N trayectorias, media+-std de P(t): agrega n_runs, n_time_points); mode='validate' compara la media del ensamble contra la solucion determinista en el regimen de numero grande de moleculas.

Modos disponibles:

- `gillespie_michaelis_menten`
- `gillespie_ensemble`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "enzyme_stochastic",
    "arguments": {
      "mode": "gillespie_michaelis_menten",
      "params": {}
    }
  }
}
```

## `ethnomath`

Algoritmos matematicos historicos: maya_long_count, chinese_remainder, vedic_multiply, quipu_encode, greek_archimedes_pi, japanese_enri_pi.

Parametros directos (sin `mode`):

- `preset`
- `params`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "ethnomath",
    "arguments": {
      "preset": null,
      "params": null
    }
  }
}
```

## `ethnomath2`

Segunda tanda de algoritmos matematicos historicos: egyptian_duplation, persian_khwarizmi, persian_alkashi_sin1, russian_peasant, ottoman_taqi_al_din, norse_rune_calendar, southeast_asian_metonic.

Parametros directos (sin `mode`):

- `preset`
- `params`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "ethnomath2",
    "arguments": {
      "preset": null,
      "params": null
    }
  }
}
```

## `evo_LGCA_tool`

Automata celular de gas reticular (LGCA, Deutsch & Dormann) en 1D para migracion colectiva de celulas, con capa evolutiva (nacimiento/muerte con herencia de fenotipo + mutacion gaussiana). mode='lgca_1d_run' (L, n_steps, initial_density, initial_region_frac, alignment_prob, birth_prob, death_prob, mutation_std, seed): corre la simulacion y devuelve snapshots de densidad + fenotipo medio final; mode='front_speed' (mismos params + threshold_fraction): estima la velocidad de avance del frente celular por regresion lineal posicion-vs-tiempo; mode='validate' verifica conservacion exacta de particulas sin nacimiento/muerte.

Modos disponibles:

- `lgca_1d_run`
- `front_speed`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "evo_LGCA_tool",
    "arguments": {
      "mode": "lgca_1d_run",
      "params": {}
    }
  }
}
```

## `fem_advanced_tool`

FEM avanzado sobre vigas Euler-Bernoulli/Timoshenko. mode='modal_beam': frecuencias naturales y modos propios via autovalores generalizados K*phi=omega^2*M*phi (masa consistente), validado contra Blevins. mode='buckling_linear': carga critica de pandeo via autovalores generalizados K*phi=Pcr*Kg*phi (rigidez geometrica consistente), validado contra Euler Pcr=pi^2EI/L^2 (pinned_pinned) y pi^2EI/(4L^2) (cantilever). mode='timoshenko_beam': deflexion de voladizo con deformacion por corte (matriz de Przemieniecki), validado contra delta=PL^3/(3EI)+PL/(G*As). support in ('pinned_pinned','cantilever') para modal_beam y buckling_linear.

Modos disponibles:

- `modal_beam`
- `buckling_linear`
- `timoshenko_beam`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "fem_advanced_tool",
    "arguments": {
      "mode": "modal_beam",
      "params": {}
    }
  }
}
```

## `filter_design_tool`

Diseno de filtros digitales: iir_design (Butterworth/Chebyshev I,II/Elliptic, lowpass/highpass/bandpass/bandstop), fir_design (ventaneado o Parks-McClellan equiripple), frequency_response (magnitud/fase de un filtro b,a), apply_filter (filtfilt fase cero o lfilter). Validado: atenuacion -3.0103dB exacta en corte de Butterworth, ripple de Chebyshev I coincide con el especificado, atenuacion de banda rechazada >40dB en caso de referencia.

Modos disponibles:

- `iir_design`
- `fir_design`
- `frequency_response`
- `apply_filter`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "filter_design_tool",
    "arguments": {
      "mode": "iir_design",
      "params": {}
    }
  }
}
```

## `financial_math`

Matematica financiera: valuacion de opciones Black-Scholes con griegas completas (black_scholes, option_greeks), Value at Risk parametrico/historico/Monte Carlo con Expected Shortfall (value_at_risk), valuacion de anualidades y perpetuidades con o sin crecimiento (annuity_valuation), y bonos: precio dado YTM o YTM dado precio de mercado via Newton-Raphson, mas duracion de Macaulay/modificada y convexidad (bond_pricing).

Modos disponibles:

- `black_scholes`
- `option_greeks`
- `value_at_risk`
- `annuity_valuation`
- `bond_pricing`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "financial_math",
    "arguments": {
      "mode": "black_scholes",
      "params": {}
    }
  }
}
```

## `finite_element_tool`

Metodo de elementos finitos: barra axial (bar_1d), viga en voladizo Euler-Bernoulli (beam_bending), cercha plana articulada (truss_2d). Validado contra soluciones analiticas de libro de texto.

Modos disponibles:

- `bar_1d`
- `beam_bending`
- `truss_2d`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "finite_element_tool",
    "arguments": {
      "mode": "bar_1d",
      "params": {}
    }
  }
}
```

## `flood_modeling_tool`

Modelado de crecidas para planificacion de drenajes: scs_triangular_hydrograph (hidrograma unitario triangular SCS), muskingum_routing (transito de crecidas por un tramo de cauce), manning_normal_depth (tirante normal y ancho de inundacion en seccion trapezoidal via ecuacion de Manning).

Modos disponibles (extraidos de `flood_modeling_tool.py` via regex — **revisar a mano**):

- `manning_normal_depth`
- `muskingum_routing`
- `scs_triangular_hydrograph`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "flood_modeling_tool",
    "arguments": {
      "mode": "manning_normal_depth",
      "params": {}
    }
  }
}
```

## `forced_vibration_tool`

Vibracion forzada de vigas Euler-Bernoulli con amortiguamiento de Rayleigh (C=a0*M+a1*K). mode='harmonic_response': barrido en frecuencia, respuesta estacionaria via solucion directa en dominio de frecuencia. mode='transient_free_decay': vibracion libre amortiguada via Newmark-beta. mode='validate' compara contra la formula analitica de amplificacion dinamica 1/(2*zeta) en resonancia y el decremento logaritmico teorico.

Modos disponibles:

- `harmonic_response`
- `transient_free_decay`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "forced_vibration_tool",
    "arguments": {
      "mode": "harmonic_response",
      "params": {}
    }
  }
}
```

## `fractal_dimension`

Dimension fractal por box-counting. Presets: sierpinski_triangle, koch_curve, cantor_set (con dimension analitica de referencia), chen_lee_attractor (integra el sistema caotico en Octave), o custom via 'points'. mode='validate' corre un check rapido contra los 3 presets con dimension analitica conocida.

Modos disponibles:

- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "fractal_dimension",
    "arguments": {
      "mode": "validate",
      "params": {}
    }
  }
}
```

## `fractional_fourier_tool`

Transformada Fraccional de Fourier (FRFT) discreta via autodescomposicion exacta (Dickinson-Steiglitz/Pei-Yeh-Tseng): frft (orden a, a=0 identidad, a=1 FFT estandar), frft_inverse, chirp_analysis (encuentra el orden que mejor compacta un chirp lineal). Validado: a=1 coincide exacto con FFT estandar, a=0 es identidad exacta, aditividad F_a1(F_a2(x))=F_(a1+a2)(x) garantizada por construccion, chirp_analysis recupera el orden optimo teorico dentro de margen conocido.

Modos disponibles:

- `frft`
- `frft_inverse`
- `chirp_analysis`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "fractional_fourier_tool",
    "arguments": {
      "mode": "frft",
      "params": {}
    }
  }
}
```

## `game_theory`

Teoria de juegos: equilibrios de Nash (puros y mixtos), valor de juegos de suma cero, eliminacion iterada de estrategias dominadas, valor de Shapley, chequeo del nucleo cooperativo, dinamica de replicador y ESS.

Modos disponibles:

- `nash_equilibrium`
- `zero_sum_value`
- `dominance_elimination`
- `shapley_value`
- `cooperative_core`
- `evolutionary_dynamics`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "game_theory",
    "arguments": {
      "mode": "nash_equilibrium",
      "params": {}
    }
  }
}
```

## `gas_tool`

Matematica de gases: gas ideal (PV=nRT), gases reales (Van der Waals, Dieterici, Berthelot, Redlich-Kwong), mezclas (Dalton, Amagat, entropia y Gibbs de mezcla), teoria cinetica molecular (velocidades caracteristicas, distribucion de Maxwell-Boltzmann, ley de Graham, propiedades de transporte: viscosidad, conductividad termica, autodifusion), dinamica de flujo compresible (numero de Mach, proceso adiabatico, ondas de choque normal, relacion area-Mach en toberas), fugacidad, y humedad de mezclas gas-vapor (presion de saturacion, razon de mezcla, densidad de aire humedo).

Modos disponibles:

- `ideal`
- `real`
- `van_der_waals`
- `mixture`
- `kinetic`
- `compressible`
- `humidity`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "gas_tool",
    "arguments": {
      "mode": "ideal",
      "params": {}
    }
  }
}
```

## `genome_signal_analysis`

Analisis de senal digital sobre secuencias genomicas: mapeo de bases a valores numericos/spin-like (complex_spin, eiip, purine_pyrimidine) y espectro de potencia via DFT, con deteccion del pico de periodicidad-3 asociado a regiones codificantes (Voss 1992, Anastassiou 2001). mode='dft_spectrum' (sequence, mapping, detrend); mode='spin_mapping' (sequence, mapping); mode='validate' corre un caso sintetico con periodicidad-3 inyectada.

Modos disponibles:

- `dft_spectrum`
- `spin_mapping`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "genome_signal_analysis",
    "arguments": {
      "mode": "dft_spectrum",
      "params": {}
    }
  }
}
```

## `geometric_algebra_protein`

Algebra geometrica (Cl(3,0), rotores via cuaterniones) aplicada al backbone de una proteina: compone las rotaciones phi/psi de cada residuo en un rotor neto que resume la orientacion acumulada de la cadena. mode='backbone_rotor_chain' (phi_psi_angles: lista de [phi,psi] en grados); mode='single_rotor' (angle_deg, axis opcional); mode='validate' verifica rotor identidad y normalizacion.

Modos disponibles:

- `backbone_rotor_chain`
- `single_rotor`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "geometric_algebra_protein",
    "arguments": {
      "mode": "backbone_rotor_chain",
      "params": {}
    }
  }
}
```

## `glm_tool`

Modelos lineales generalizados y regresion regularizada: regresion logistica binaria (logistic_regression, via IRLS, con odds ratios y p-values de Wald), regresion de Poisson (poisson_regression, GLM de conteos via IRLS), y Ridge/Lasso (ridge_lasso, con seleccion de lambda via validacion cruzada k-fold).

Modos disponibles:

- `logistic_regression`
- `poisson_regression`
- `ridge_lasso`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "glm_tool",
    "arguments": {
      "mode": "logistic_regression",
      "params": {}
    }
  }
}
```

## `graph_algorithms`

Corre algoritmos clasicos de grafos: Dijkstra, MST (Kruskal), deteccion de ciclos. Presets: small_weighted, disconnected, with_cycle, o custom via 'edges' [[u,v,peso],...]. mode='validate' corre un check rapido contra valores exactos calculados a mano.

Modos disponibles:

- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "graph_algorithms",
    "arguments": {
      "mode": "validate",
      "params": {}
    }
  }
}
```

## `historian`

Orquestador de analisis historico: parsea numeros de texto libre via regex (sin NLP complejo), arma arrays de numpy, y ajusta el motor correspondiente segun analysis_type -- inflation/demographics (regresion log-lineal: tasa anual %, R2), trade_network (centralidad de red: fuerza entrante + autovector, identifica el hub), units_entropy (entropia de Shannon sobre unidades historicas de medida -- in

Modos disponibles (extraidos de `historian_tool.py` via regex — **revisar a mano**):

- `analyze`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "historian",
    "arguments": {
      "mode": "analyze",
      "params": {}
    }
  }
}
```

## `historical_extractor`

Extrae MULTIPLES series (anio, valor) de un mismo texto historico via regex por oracion (no NLP), una serie por objeto/concepto mencionado (ej: trigo, cebada, jornal). Corre tendencia por regresion log-lineal en cada serie (reusa el motor de historian), calcula salario real indexado si se indica objeto_salario, y correlacion de Pearson entre series de precios que se solapan en anios. NO interpreta

Modos disponibles (extraidos de `historical_extractor_tool.py` via regex — **revisar a mano**):

- `analyze`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "historical_extractor",
    "arguments": {
      "mode": "analyze",
      "params": {}
    }
  }
}
```

## `information_theory`

Teoria de la informacion: entropia de Shannon, divergencia KL y distancia Jensen-Shannon entre distribuciones, informacion mutua entre variables conjuntas, entropia cruzada, y entropia condicional de secuencias (orden-n, para medir redundancia estructural en sistemas numerales o senales discretas).

Modos disponibles:

- `shannon_entropy`
- `kl_divergence`
- `mutual_information`
- `cross_entropy`
- `sequence_entropy`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "information_theory",
    "arguments": {
      "mode": "shannon_entropy",
      "params": {}
    }
  }
}
```

## `infrasound_tool`

Propagacion de infrasonido: perfil de atenuacion (esparcimiento esferico 20*log10(d) + absorcion atmosferica tipo ISO 9613-1 simplificada) en funcion de la distancia, y tiempo de viaje dado perfil simple de temperatura/viento. mode='attenuation_profile' (source_level_db, frequency_hz, temperature_c, relative_humidity_pct, distances_km); mode='travel_time' (distance_km, temperature_c, wind_speed_ms, wind_direction); mode='validate' chequea c(20C)~343m/s y monotonia de la atenuacion.

Modos disponibles:

- `attenuation_profile`
- `travel_time`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "infrasound_tool",
    "arguments": {
      "mode": "attenuation_profile",
      "params": {}
    }
  }
}
```

## `insurance_risk_tool`

Seguros y reaseguro de catastrofes: pure_premium (prima pura mas cargas de gasto y margen de utilidad, sobre una distribucion de perdida Poisson-LogNormal simulada o provista, prima_comercial = prima_pura/(1-expense_ratio-profit_margin)), excess_of_loss_layer (pricing de una capa de reaseguro XoL via Monte Carlo, perdida esperada de capa = E[min(max(L-attachment,0),limit)]), cat_bond_pricing (pricing simplificado de bono catastrofico: cupon = perdida esperada de la capa cubierta/principal + spread de mercado), loss_ratio_analysis (loss ratio, expense ratio y combined ratio de una cartera dado primas y siniestros historicos), validate (suite de 10 checks). Motor generico: no trae catalogo de tasas de mercado ni expense ratios (los provee quien llama), confidence_flag 'alta'.

Modos disponibles (extraidos de `insurance_risk_tool.py` via regex — **revisar a mano**):

- `cat_bond_pricing`
- `excess_of_loss_layer`
- `loss_ratio_analysis`
- `pure_premium`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "insurance_risk_tool",
    "arguments": {
      "mode": "cat_bond_pricing",
      "params": {}
    }
  }
}
```

## `integrate_stiff_ode`

Integra un sistema de ecuaciones diferenciales ordinarias, incluyendo sistemas rígidos/stiff (donde métodos explícitos como ode45/RK4 son extremadamente lentos), usando solvers implícitos de Octave (ode15s, ode23s) o lsode. Presets: van_der_pol (stiff clásico), robertson (cinética química rígida), o custom.

Parametros directos (sin `mode`):

- `system`
- `custom_equations`
- `custom_params`
- `y0`
- `tspan`
- `solver`
- `n_output_points`
- `rel_tol`
- `abs_tol`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "integrate_stiff_ode",
    "arguments": {
      "system": null,
      "custom_equations": null,
      "custom_params": null,
      "y0": null,
      "tspan": null,
      "solver": null,
      "n_output_points": null,
      "rel_tol": null,
      "abs_tol": null
    }
  }
}
```

## `investment_portfolio_tool`

Analisis de portafolio de inversion: expected_return_variance (retorno esperado y volatilidad del portafolio dado pesos, retornos/volatilidades por activo y matriz de correlacion opcional -identidad, sin correlacion, si se omite-), rebalancing_drift (pesos actuales vs objetivo, desvio por activo y montos de compra/venta para rebalancear), risk_return_score (clasificacion cualitativa conservador/moderado/agresivo segun volatilidad esperada), diversification_score (indice de concentracion Herfindahl-Hirschman sobre los pesos, banda concentrado/moderado/diversificado). confidence_flag 'alta' para la mecanica de varianza de portafolio (algebra lineal determinista); los retornos/volatilidades esperados por activo son un supuesto de quien llama, no una prediccion. No es asesoria financiera ni de inversion. validate corre 8 checks.

Modos disponibles:

- `expected_return_variance`
- `rebalancing_drift`
- `risk_return_score`
- `diversification_score`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "investment_portfolio_tool",
    "arguments": {
      "mode": "expected_return_variance",
      "params": {}
    }
  }
}
```

## `knowledge_graph_tool`

Guia de exploracion sobre el catalogo de tools de octave-mcp. mode='search': busca tools relevantes para una consulta en lenguaje natural (scoring lexico sobre nombre+descripcion de cada tool, sin categorias hardcodeadas). mode='related': dado el nombre de una tool, encuentra otras que comparten vocabulario en su descripcion. mode='stats': panorama del catalogo completo (terminos mas frecuentes, proxy de areas cubiertas). Se deriva en vivo de TOOLS, no requiere mantenimiento manual cuando se agregan tools nuevas.

Modos disponibles:

- `search`
- `related`
- `stats`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "knowledge_graph_tool",
    "arguments": {
      "mode": "search",
      "params": {}
    }
  }
}
```

## `levant`

Matematica cananea y de Juda/Israel: hebrew_molad (conjuncion lunar media, ciclo metonico de 19 anios), hebrew_gematria (valor numerico de palabras hebreas y su inverso), canaanite_phoenician_numeral (sistema aditivo 1/10/20/100).

Parametros directos (sin `mode`):

- `preset`
- `params`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "levant",
    "arguments": {
      "preset": null,
      "params": null
    }
  }
}
```

## `life_insurance_math_tool`

Calculos de seguro de vida: human_life_value (valor presente del ingreso neto futuro de la persona asegurada, con crecimiento salarial opcional), needs_based_coverage (metodo de necesidades: deudas + gastos finales + fondo de educacion + reemplazo de ingreso, menos activos liquidos), term_vs_permanent_cost (compara costo nominal y valor presente de poliza de termino vs permanente, netea valor en efectivo al horizonte), coverage_gap_analysis (cobertura actual vs necesaria, banda cualitativa sin_cobertura/insuficiente/por_debajo_de_lo_adecuado/adecuada/sobre_cobertura). confidence_flag 'alta' para la mecanica de valor presente (formulas cerradas y suma anio a anio deterministica); montos de necesidad y tasas de descuento son supuestos de quien llama. No es asesoria financiera ni actuarial. validate corre 8 checks de referencia.

Modos disponibles:

- `human_life_value`
- `needs_based_coverage`
- `term_vs_permanent_cost`
- `coverage_gap_analysis`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "life_insurance_math_tool",
    "arguments": {
      "mode": "human_life_value",
      "params": {}
    }
  }
}
```

## `linear_algebra`

Algebra lineal via Octave: eigen (autovalores/autovectores), svd (descomposicion en valores singulares + verificacion), pca (componentes principales, varianza explicada), matrix_analysis (rango, condicion, determinante, inversa). Prerrequisito de persistent_homology_tool.

Modos disponibles:

- `eigen`
- `svd`
- `pca`
- `matrix_analysis`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "linear_algebra",
    "arguments": {
      "mode": "eigen",
      "params": {}
    }
  }
}
```

## `lscm_tool`

Parametrizacion conforme (Least Squares Conformal Maps): aplana una malla 3D con borde (topologia de disco) a 2D minimizando distorsion angular. Incluye analisis de distorsion cuasi-conforme por triangulo (valores singulares del jacobiano, dilatacion K, coeficiente de Beltrami |mu|). Util para desenrollar superficies organicas (ej: sockets de protesis) para texturizado, comparacion de geometria, o deteccion de zonas de alta distorsion.

Modos disponibles:

- `flatten`
- `distortion`
- `flatten_and_distortion`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "lscm_tool",
    "arguments": {
      "mode": "flatten",
      "params": {}
    }
  }
}
```

## `machine_learning_math`

Fundamentos matematicos de machine learning: descenso de gradiente simbolico, regresion lineal/logistica, funciones de costo (MSE, MAE, cross-entropy, hinge), comparacion de regularizacion L1/L2, y PCA.

Modos disponibles:

- `gradient_descent`
- `linear_regression`
- `logistic_regression`
- `cost_functions`
- `regularization_compare`
- `pca`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "machine_learning_math",
    "arguments": {
      "mode": "gradient_descent",
      "params": {}
    }
  }
}
```

## `math_benchmark`

Compara metodos numericos contra soluciones analiticas conocidas y estima el orden de convergencia empirico. mode='ode_methods' (Euler/RK2/RK4 vs solucion analitica; kwargs: problem in ['exponential_decay','harmonic_oscillator','logistic_growth'], h_list, t_end, methods); mode='quadrature' (Trapecio/Simpson/Gauss-Legendre vs integral analitica via sympy; kwargs: function_expr, a, b o preset in ['polynomial','sine','exponential','oscillatory'], n_list, methods); mode='root_finding' (Biseccion/Newton-Raphson/Secante vs raiz de referencia; kwargs: function_expr, bracket, x0 o preset in ['cubic','transcendental'], tol, max_iter); mode='validate' corre un caso de cada familia con verdad conocida.

Modos disponibles:

- `ode_methods`
- `quadrature`
- `root_finding`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "math_benchmark",
    "arguments": {
      "mode": "ode_methods",
      "params": {}
    }
  }
}
```

## `math_error_analyzer`

Analiza error de truncamiento vs. redondeo en diferenciacion numerica (forward/central) y numero de condicionamiento de matrices, con demo de amplificacion de error via perturbacion. mode='truncation_roundoff' (function_expr, x0, method, h_min_exp, h_max_exp); mode='condition_number' (matrix, b opcional, delta_b opcional); mode='validate' corre ambos contra casos de libro con verdad conocida.

Modos disponibles:

- `truncation_roundoff`
- `condition_number`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "math_error_analyzer",
    "arguments": {
      "mode": "truncation_roundoff",
      "params": {}
    }
  }
}
```

## `math_explainer`

Genera una explicacion en espanol, paso a paso, del resultado JSON de otro tool matematico (compute_gradient_hessian, math_error_analyzer, compute_lyapunov_exponent, run_math_pipeline, etc.).

Parametros directos (sin `mode`):

- `source_tool`
- `result`
- `level`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "math_explainer",
    "arguments": {
      "source_tool": null,
      "result": null,
      "level": null
    }
  }
}
```

## `math_humanizer_tool`

Convierte conceptos matemáticos complejos en historias e ideas accesibles, conectando con la filosofía y la vida cotidiana (analogía cotidiana + conexión filosófica + nota más profunda para quien quiera seguir tirando del hilo). Contenido de referencia curado, no un cálculo — pensado para divulgación y enseñanza.

Modos disponibles:

- `explain_concept`
- `list_concepts`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "math_humanizer_tool",
    "arguments": {
      "mode": "explain_concept",
      "params": {}
    }
  }
}
```

## `math_interpolation`

Compara metodos de interpolacion contra la funcion exacta, con foco en el fenomeno de Runge y su mitigacion. mode='lagrange' (interpolacion de Lagrange en forma baricentrica; kwargs: preset in ['runge','smooth_sine','exponential','abs_kink'] o function_expr+domain, n_list, node_type in ['equally_spaced','chebyshev']); mode='spline' (spline cubico natural, sin scipy; mismos kwargs sin node_type); mode='compare_nodes' (corre lagrange con ambos tipos de nodo para el mismo n_list, marca runge_phenomenon_detected); mode='validate' corre casos con verdad conocida.

Modos disponibles:

- `lagrange`
- `spline`
- `compare_nodes`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "math_interpolation",
    "arguments": {
      "mode": "lagrange",
      "params": {}
    }
  }
}
```

## `math_interpreter`

Traduce consultas en espanol con frases canonicas (ej: 'gradiente y hessiano de x**2*sin(y) respecto a x,y', 'error de truncamiento de sin(x) en x0=1') a steps de run_math_pipeline, via matching de patrones regex (NO es NLU general). Util para invocar el ecosistema octave-mcp sin un LLM en el medio. auto_run=True ademas ejecuta el pipeline resultante.

Parametros directos (sin `mode`):

- `query`
- `auto_run`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "math_interpreter",
    "arguments": {
      "query": null,
      "auto_run": null
    }
  }
}
```

## `math_philosophy_history`

Referencia sobre filosofia e historia de la matematica (8 topics).

Parametros directos (sin `mode`):

- `topic`
- `params`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "math_philosophy_history",
    "arguments": {
      "topic": null,
      "params": null
    }
  }
}
```

## `math_visualization`

Genera visualizaciones (PNG base64) de funciones, retratos de fase de sistemas ODE, diagramas de bifurcacion y campos vectoriales/gradiente.

Modos disponibles:

- `function_plot`
- `phase_portrait`
- `bifurcation_render`
- `vector_field`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "math_visualization",
    "arguments": {
      "mode": "function_plot",
      "params": {}
    }
  }
}
```

## `mcdm`

Decision multicriterio: AHP (ponderacion de criterios via matriz de comparacion pareada + ratio de consistencia de Saaty), TOPSIS (ranking por cercania a los ideales positivo/negativo), y weighted_sum/weighted_product (WSM/WPM clasicos con normalizacion min-max).

Modos disponibles:

- `ahp`
- `topsis`
- `weighted_sum`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "mcdm",
    "arguments": {
      "mode": "ahp",
      "params": {}
    }
  }
}
```

## `mesh_pde_tool`

Mallado adaptativo y suavizado via EDPs elipticas: resuelve la posicion de los nodos interiores de una malla como solucion de una ecuacion de Laplace (mode=smooth) o Poisson con termino fuente (mode=poisson), usando la posicion de los nodos del borde como condicion de contorno Dirichlet. Usa el mismo Laplaciano cotangente (FEM lineal) que mesh_spectral_tool. Util para eliminar pliegues/cruces en una malla generada a mano o por distmesh_tool, o para regenerar el interior de una malla dado un nuevo contorno (ej: perfil de socket de protesis modificado).

Modos disponibles:

- `smooth`
- `poisson`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "mesh_pde_tool",
    "arguments": {
      "mode": "smooth",
      "params": {}
    }
  }
}
```

## `mesh_spectral_tool`

Espectro de Laplace-Beltrami de mallas triangulares 3D (huella dactilar espectral de la forma). Modos: 'spectrum' (autovalores/autovectores de una malla), 'compare' (distancia espectral entre dos mallas), 'laplacian_info' (propiedades de la matriz sin resolver autovalores, mas barato).

Modos disponibles:

- `spectrum`
- `compare`
- `laplacian_info`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "mesh_spectral_tool",
    "arguments": {
      "mode": "spectrum",
      "params": {}
    }
  }
}
```

## `multibody_dynamics_tool`

Dinamica de cuerpos rigidos y sistemas multi-cuerpo: pendulo fisico (compound_pendulum), rotacion libre de par via ecuaciones de Euler (rigid_body_euler), manipulador/pendulo doble planar via Lagrangiano (two_link_manipulator). Validado contra formulas de libro de texto.

Modos disponibles:

- `compound_pendulum`
- `rigid_body_euler`
- `two_link_manipulator`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "multibody_dynamics_tool",
    "arguments": {
      "mode": "compound_pendulum",
      "params": {}
    }
  }
}
```

## `multivariate_bayes_tool`

Estadistica bayesiana multivariada: normal/t multivariada, Wishart, modelo jerarquico (Gibbs), regresion via HMC, PCA con biplot y CV, y Factor Analysis via EM.

Modos disponibles:

- `mvn_sample`
- `mvt_sample`
- `wishart_sample`
- `hierarchical`
- `hmc_regression`
- `pca_biplot`
- `pca_cv`
- `factor_analysis`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "multivariate_bayes_tool",
    "arguments": {
      "mode": "mvn_sample",
      "params": {}
    }
  }
}
```

## `music_math`

Calculos de matematica musical: pythagorean_comma, temperament_comparison, harmonic_series, ternary_scale (division de la octava en 3^n pasos, conexion con TritOS), spectral_analysis (FFT real via Octave sobre una senal).

Parametros directos (sin `mode`):

- `preset`
- `f0`
- `n_harmonics`
- `n_power`
- `signal`
- `fs`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "music_math",
    "arguments": {
      "preset": null,
      "f0": null,
      "n_harmonics": null,
      "n_power": null,
      "signal": null,
      "fs": null
    }
  }
}
```

## `natural_hazard_risk_tool`

Modelado de riesgo multifactorial (R=H*E*V/A) para gestion publica de desastres naturales: risk_index (indice de riesgo puntual con clasificacion en bandas), risk_grid (mapa de calor de riesgo sobre grilla), gumbel_return_period (periodo de retorno empirico T=(n+1)/m), gumbel_fit (ajuste de distribucion de Gumbel por momentos y estimacion de magnitud de diseno o periodo de retorno).

Modos disponibles (extraidos de `natural_hazard_risk_tool.py` via regex — **revisar a mano**):

- `gumbel_fit`
- `gumbel_return_period`
- `risk_grid`
- `risk_index`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "natural_hazard_risk_tool",
    "arguments": {
      "mode": "gumbel_fit",
      "params": {}
    }
  }
}
```

## `network_science`

Ciencia de redes: centralidades (grado, betweenness, closeness, eigenvector, PageRank), deteccion de comunidades (Louvain, greedy modularity, label propagation), modelos de crecimiento (Barabasi-Albert, Erdos-Renyi, Watts-Strogatz), y metricas generales de grafo (densidad, clustering, componentes, diametro).

Modos disponibles:

- `centrality`
- `community_detection`
- `growth_model`
- `graph_metrics`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "network_science",
    "arguments": {
      "mode": "centrality",
      "params": {}
    }
  }
}
```

## `nonlinear_buckling_tool`

Pandeo no lineal / grandes deformaciones: armadura de dos barras (von Mises truss, snap-through) via elemento barra Lagrangiano Total (Green-Lagrange) multi-GDL y metodo de longitud de arco esferico (Crisfield), que traza la rama inestable que Newton-Raphson con control de carga no puede atravesar. mode='trace_path' corre el arc-length. mode='validate' compara la trayectoria contra la solucion cerrada P(w) y verifica que cruza los dos puntos limite.

Modos disponibles:

- `trace_path`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "nonlinear_buckling_tool",
    "arguments": {
      "mode": "trace_path",
      "params": {}
    }
  }
}
```

## `nuclear_decay_chain`

Resuelve una cadena de decaimiento nuclear (Bateman) via ode45. Presets: cs137_ba137m, sr90_y90, o custom via 'chain'. stable_last=True no sigue la cadena mas alla del ultimo isotopo pero NUNCA anula su lambda (permite alcanzar equilibrio secular). mode='validate' corre un check rapido: decaimiento simple vs analitico + equilibrio secular.

Modos disponibles:

- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "nuclear_decay_chain",
    "arguments": {
      "mode": "validate",
      "params": {}
    }
  }
}
```

## `number_theory`

Teoria de numeros con aplicacion criptografica: primality_test (Miller-Rabin, detecta incluso numeros de Carmichael como 561), rsa_toy (genera par de claves con primos dados, cifra/descifra un mensaje, valida contra el ejemplo clasico del paper RSA original), elliptic_curve_add (suma/duplicacion de puntos sobre y^2=x^3+ax+b mod p, validado contra ejemplo de libro de texto Hankerson et al).

Modos disponibles:

- `primality_test`
- `rsa_toy`
- `elliptic_curve_add`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "number_theory",
    "arguments": {
      "mode": "primality_test",
      "params": {}
    }
  }
}
```

## `numeral_systems_embedding`

Vectoriza sistemas numericos antiguos (base, tipo posicional/aditivo/ fisico, presencia de cero, redundancia representacional, soporte fisico) y proyecta a 2D via UMAP o t-SNE, para explorar agrupamientos estructurales entre culturas. Dataset base: maya_long_count, suanpan, soroban, roman_hand_abacus, yupana_depasquale, quipu, ifa_binary. Extensible via extra_systems (lista de dicts con el mismo s

Parametros directos (sin `mode`):

- `method`
- `extra_systems`
- `n_neighbors`
- `perplexity`
- `random_state`
- `run_id`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "numeral_systems_embedding",
    "arguments": {
      "method": null,
      "extra_systems": null,
      "n_neighbors": null,
      "perplexity": null,
      "random_state": null,
      "run_id": null
    }
  }
}
```

## `ocas_symbolic`

Algebra simbolica y teoria de numeros via oCAS (motor Rust, mas rapido que sympy pero mas nuevo/menos probado, v0.26.0). mode='symbolic': simplify/differentiate/integrate/substitute sobre 'expression' (string, potencia con '^' NO '**', ej 'x^2 + 2*x + 1'). mode='number_theory': operation=isprime|factorint|nextprime|totient|divisor_sigma|mobius|liouville_lambda|jacobi_symbol|discrete_log|crt sobre enteros. mode='diophantine': resuelve a*x+b*y=c. Presets con resultado conocido validado, o preset='custom' con los parametros propios.

Modos disponibles (extraidos de `ocas_symbolic_tool.py` via regex — **revisar a mano**):

- `differentiate`
- `diophantine`
- `integrate`
- `number_theory`
- `substitute`
- `symbolic`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "ocas_symbolic",
    "arguments": {
      "mode": "differentiate",
      "params": {}
    }
  }
}
```

## `octave_eval_expr`

Evalua una expresion Octave con disp().

Parametros directos (sin `mode`):

- `expression`
- `timeout`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "octave_eval_expr",
    "arguments": {
      "expression": null,
      "timeout": null
    }
  }
}
```

## `octave_run`

Ejecuta codigo Octave. timeout en segundos (default 60).

Parametros directos (sin `mode`):

- `code`
- `timeout`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "octave_run",
    "arguments": {
      "code": null,
      "timeout": null
    }
  }
}
```

## `octave_run_script`

Ejecuta un script .m existente en disco.

Parametros directos (sin `mode`):

- `script_path`
- `timeout`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "octave_run_script",
    "arguments": {
      "script_path": null,
      "timeout": null
    }
  }
}
```

## `octave_syntax`

Valida la sintaxis de un fragmento de codigo Octave sin ejecutarlo (envuelve el codigo en una funcion y lo parsea via source(), sin correr ninguna linea). mode='syntax_check'. Util para verificar codigo generado antes de guardarlo o correrlo.

Modos disponibles:

- `syntax_check`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "octave_syntax",
    "arguments": {
      "mode": "syntax_check",
      "params": {}
    }
  }
}
```

## `octave_version`

Devuelve la version de Octave instalada.

Parametros directos (sin `mode`):


```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "octave_version",
    "arguments": {}
  }
}
```

## `optical_sequence_id`

Simula difraccion de Fraunhofer (via FFT) de una secuencia codificada como apertura de indice de refraccion (EIIP), y permite identificar una secuencia desconocida por correlacion cruzada de su patron de difraccion contra un banco de referencias. Proxy matematico de biosensado optico, no simulacion fisica completa. mode='diffraction_pattern' (sequence, n_pad); mode='match_sequence' (unknown_sequence, reference_sequences: dict nombre->secuencia, n_pad); mode='validate' confirma match perfecto contra si misma.

Modos disponibles:

- `diffraction_pattern`
- `match_sequence`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "optical_sequence_id",
    "arguments": {
      "mode": "diffraction_pattern",
      "params": {}
    }
  }
}
```

## `optimal_control`

Control optimo: LQR (Riccati algebraica continua, ley de control -Kx, simulacion de lazo cerrado), control LQ escalar de horizonte finito via principio del maximo de Pontryagin (Riccati diferencial, trayectorias de estado/costado/control), y programacion dinamica (iteracion de valor para MDP finitos: politica y funcion de valor optimas).

Modos disponibles:

- `lqr`
- `pontryagin_lq`
- `dynamic_programming`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "optimal_control",
    "arguments": {
      "mode": "lqr",
      "params": {}
    }
  }
}
```

## `optimization`

Optimizacion: linear_programming (via glpk nativo de Octave), gradient_descent (gradiente EXACTO simbolico via sympy, no diferencias finitas). Presets validados contra optimos conocidos.

Modos disponibles:

- `linear_programming`
- `gradient_descent`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "optimization",
    "arguments": {
      "mode": "linear_programming",
      "params": {}
    }
  }
}
```

## `originarios`

Numeracion de pueblos originarios: mapuche_numeral (rakin, decimal aditivo-multiplicativo) y aymara_numeral (decimal con sufijo -ni, mas nota sobre vestigio quinario).

Parametros directos (sin `mode`):

- `preset`
- `params`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "originarios",
    "arguments": {
      "preset": null,
      "params": null
    }
  }
}
```

## `paleography`

Tres motores cuantitativos de paleografia/codicologia sobre rasgos YA EXTRAIDOS (no hace OCR ni lee imagenes): seriation (analisis de correspondencia via SVD sobre matriz documentos x rasgos, ordena por el eje 1 y valida contra anios_conocidos con Spearman si se dan), feature_dating_regression (ajusta anio ~ rasgo sobre documentos ancla de fecha conocida y estima fecha de documentos sin fecha, con error estandar residual), letterform_classification (nearest-centroid sobre rasgos normalizados, clasifica letterforms en clases conocidas y marca casos ambiguos por margen chico). Ninguno da fechas/atribuciones definitivas.

Modos disponibles (extraidos de `paleography_tool.py` via regex — **revisar a mano**):

- `correspondence_seriation`
- `feature_dating_regression`
- `letterform_classification`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "paleography",
    "arguments": {
      "mode": "correspondence_seriation",
      "params": {}
    }
  }
}
```

## `particle_simulation_tool`

Simulacion de particulas: orbita de Kepler de dos cuerpos (kepler_orbit), colisiones elasticas en cadena 1D (elastic_collision_nbody), caminata aleatoria y recuperacion de coeficiente de difusion (random_walk_diffusion).

Modos disponibles:

- `kepler_orbit`
- `elastic_collision_nbody`
- `random_walk_diffusion`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "particle_simulation_tool",
    "arguments": {
      "mode": "kepler_orbit",
      "params": {}
    }
  }
}
```

## `pde`

Ecuaciones en derivadas parciales via diferencias finitas explicitas en Octave: heat_equation (u_t=alpha*u_xx), wave_equation (u_tt=c^2*u_xx). Validado contra solucion analitica del primer modo normal. Extension de stiff_ode_tool hacia EDPs -- relevante para propagacion termica LIG.

Modos disponibles:

- `heat_equation`
- `wave_equation`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "pde",
    "arguments": {
      "mode": "heat_equation",
      "params": {}
    }
  }
}
```

## `percolation_theory`

Teoria de percolacion: percolacion de sitio y de enlace en grilla 2D, estimacion del umbral critico p_c via barrido de probabilidad, y percolacion sobre grafos arbitrarios (componente gigante). Aplicable a conectividad de crecimiento micelial y umbral de conductividad en composites micelio-grafeno.

Modos disponibles:

- `site_percolation`
- `bond_percolation`
- `critical_threshold`
- `graph_percolation`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "percolation_theory",
    "arguments": {
      "mode": "site_percolation",
      "params": {}
    }
  }
}
```

## `persistent_homology`

Homologia persistente (H0, H1) sobre una nube de puntos via complejo de Vietoris-Rips y reduccion de matriz de borde. Presets sinteticos validados (circle, two_clusters, random_noise) o custom via 'points' para datos reales -- por ejemplo nubes reconstruidas de un embedding de Takens (conexion directa con TritOS). Si se indica run_id, guarda points/h0_diagram/h1_diagram en el workspace para grafic

Parametros directos (sin `mode`):

- `preset`
- `points`
- `max_edge_length`
- `max_dim`
- `n_points`
- `seed`
- `run_id`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "persistent_homology",
    "arguments": {
      "preset": null,
      "points": null,
      "max_edge_length": null,
      "max_dim": null,
      "n_points": null,
      "seed": null,
      "run_id": null
    }
  }
}
```

## `personal_budget_tool`

Presupuesto personal/domestico: income_expense_balance (balance ingreso-gasto, tasa de ahorro, breakdown porcentual por categoria), category_benchmark (compara gasto real por tipo necesidad/deseo/ahorro contra un benchmark, regla 50/30/20 por defecto o uno custom que sume 1.0), fixed_variable_split (separa gasto fijo vs variable, ratio de compromiso fijo sobre ingreso), zero_based_allocation (presupuesto base-cero: asigna montos por categoria segun % objetivo y verifica que cierre en 100%). Aritmetica de presupuesto, confidence_flag 'alta' para toda la mecanica (sumas y porcentajes cerrados). No es asesoria financiera personalizada: los benchmarks son heuristicas de referencia, no normas. validate corre 6 checks de referencia.

Modos disponibles:

- `income_expense_balance`
- `category_benchmark`
- `fixed_variable_split`
- `zero_based_allocation`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "personal_budget_tool",
    "arguments": {
      "mode": "income_expense_balance",
      "params": {}
    }
  }
}
```

## `plague_sir`

SIR inverso para brotes historicos de peste: parsea defunciones semanales de texto libre via regex, ajusta beta (tasa de contagio) con curve_fit manteniendo gamma fijo (parametro de literatura, no medido), integra SIR con RK4, y reporta R0=beta/gamma. Proxy cuantitativo cuando no hay fuente epidemiologica directa -- no corrige subregistro, migracion, ni estacionalidad. Modes: fit_beta (requiere te

Modos disponibles (extraidos de `plague_sir_tool.py` via regex — **revisar a mano**):

- `fit_beta`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "plague_sir",
    "arguments": {
      "mode": "fit_beta",
      "params": {}
    }
  }
}
```

## `plane_stress_tool`

FEM 2D continuo: elemento triangular CST (Constant Strain Triangle) para estado plano de tensiones. mode='solve' resuelve una malla (nodos+triangulos, ej. de distmesh_tool) con cargas y apoyos propios. mode='patch_test' corre el patch test clasico (traccion uniforme, malla rectangular preset o propia) -- el CST da tension exactamente uniforme sin importar irregularidad de malla, es la validacion estandar de un codigo FEM plano. mode='validate' corre patch_test y chequea uniformidad.

Modos disponibles:

- `solve`
- `patch_test`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "plane_stress_tool",
    "arguments": {
      "mode": "solve",
      "params": {}
    }
  }
}
```

## `plot_workspace_run`

Genera una visualizacion (PNG en base64 + guardado en disco) a partir de un run guardado en el workspace (ej: la trayectoria de un atractor guardada por compute_lyapunov con run_id). No recalcula nada, solo lee y grafica. plot_type: auto (infiere segun el tool de origen), attractor_3d, attractor_2d, line, scatter, heatmap.

Parametros directos (sin `mode`):

- `run_id`
- `plot_type`
- `title`
- `array_name`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "plot_workspace_run",
    "arguments": {
      "run_id": null,
      "plot_type": null,
      "title": null,
      "array_name": null
    }
  }
}
```

## `polarization_mapping`

Mapea secuencias de ADN/proteina a estados de polarizacion optica (psi, chi fijos por simbolo) y calcula el vector de Stokes (S0..S3) y grado de polarizacion (DOP), agregado o por ventana deslizante. Proxy matematico, no medicion optica real. mode='sequence_to_stokes' (sequence, alphabet); mode='windowed_stokes' (sequence, alphabet, window, step); mode='validate' confirma DOP=1 para secuencia homogenea.

Modos disponibles:

- `sequence_to_stokes`
- `windowed_stokes`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "polarization_mapping",
    "arguments": {
      "mode": "sequence_to_stokes",
      "params": {}
    }
  }
}
```

## `population_dynamics`

Dinamica de poblaciones: lotka_volterra (depredador-presa), logistic_growth (capacidad de carga). Relevante para cultivo de kelp en infraestructura de longline existente.

Modos disponibles:

- `lotka_volterra`
- `logistic_growth`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "population_dynamics",
    "arguments": {
      "mode": "lotka_volterra",
      "params": {}
    }
  }
}
```

## `population_genetics`

Genetica de poblaciones: equilibrio de Hardy-Weinberg (con test chi-cuadrado), deriva genica (simulacion de Wright-Fisher), seleccion natural (dinamica de frecuencias alelicas), coalescencia (tiempo esperado al MRCA), y distancias geneticas (Fst de Wright, distancia de Nei).

Modos disponibles:

- `hardy_weinberg`
- `genetic_drift`
- `natural_selection`
- `coalescence`
- `genetic_distance`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "population_genetics",
    "arguments": {
      "mode": "hardy_weinberg",
      "params": {}
    }
  }
}
```

## `public_data_ingest_tool`

Calidad e ingesta de datos publicos: outlier_detection_zscore (media/std, documenta el efecto de masking donde un outlier extremo infla el std y puede enmascarar su propio z-score), outlier_detection_iqr (rango intercuartil, robusto ante masking porque no depende de media/std), data_quality_score (completeness + uniqueness + validity combinadas en score compuesto ponderado), deduplication_estimate (duplicados exactos por clave y duplicados difusos por similitud Jaccard sobre tokens), validate (suite de 10 checks). confidence_flag 'alta' en zscore/IQR/completeness (formulas cerradas), 'media' en deduplicacion difusa (umbral Jaccard heuristico, sin ground truth de duplicado real).

Modos disponibles (extraidos de `public_data_ingest_tool.py` via regex — **revisar a mano**):

- `data_quality_score`
- `deduplication_estimate`
- `outlier_detection_iqr`
- `outlier_detection_zscore`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "public_data_ingest_tool",
    "arguments": {
      "mode": "data_quality_score",
      "params": {}
    }
  }
}
```

## `qm_potential_well`

Resuelve la ecuacion de Schrodinger 1D independiente del tiempo por diferencias finitas. Presets: infinite_well, finite_well, harmonic_oscillator, o custom via custom_potential (expresion Octave en x).

Parametros directos (sin `mode`):

- `preset`
- `custom_potential`
- `well_params`
- `x_range`
- `n_points`
- `mass`
- `hbar`
- `n_states`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "qm_potential_well",
    "arguments": {
      "preset": null,
      "custom_potential": null,
      "well_params": null,
      "x_range": null,
      "n_points": null,
      "mass": null,
      "hbar": null,
      "n_states": null
    }
  }
}
```

## `quantity_takeoff`

Cubicaciones de construcción: volumen de hormigón, área de encofrado, peso de acero de refuerzo, volumen de excavación, conteo de unidades de albañilería y resumen de cubicación (BOQ).

Parametros directos (sin `mode`):

- `operation`
- `element`
- `dims`
- `bars`
- `items`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "quantity_takeoff",
    "arguments": {
      "operation": null,
      "element": null,
      "dims": null,
      "bars": null,
      "items": null
    }
  }
}
```

## `quantum_astro_tool`

Fase 1 de andamiaje de mecanica cuantica: algebra de operadores (conmutadores, anticonmutadores, producto tensorial, matrices de Pauli, operadores escalera) y construccion de Hamiltonianos estandar (oscilador armonico, spin en campo magnetico, Jaynes-Cummings). Base reutilizable para modos futuros hamiltonian_evolution (via solver de EDOs existente), density_matrix y partition_function, y para el puente a cosmologia semiclasica (Friedmann con correcciones LQG).

Modos disponibles:

- `operator_algebra`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "quantum_astro_tool",
    "arguments": {
      "mode": "operator_algebra",
      "params": {}
    }
  }
}
```

## `quantum_cosmology_tool`

Cosmologia cuantica en minisuperspace via la ecuacion de Wheeler-DeWitt, resuelta como una ecuacion tipo Schrodinger para el factor de escala a (Crank-Nicolson unitario, frontera Dirichlet excluida del sistema lineal). Potenciales de juguete: free, linear (analogo curvatura cerrada), harmonic (analogo Lambda) -- no son coeficientes exactos de GR, es el modelo estandar y verificable de cosmologia cuantica en minisuperspace. mode=self_test: corre 2 regression tests contra soluciones analiticas exactas (ensanchamiento gaussiano libre, periodo del oscilador armonico via FFT) + chequeo de conservacion de norma. mode=friedmann_corrections: evolucion cuantica <a>(t), trayectoria de De Broglie-Bohm, trayectoria clasica del mismo Hamiltoniano, y diagnostico de bounce (evitacion cuantica de la singularidad clasica).

Modos disponibles:

- `self_test`
- `friedmann_corrections`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "quantum_cosmology_tool",
    "arguments": {
      "mode": "self_test",
      "params": {}
    }
  }
}
```

## `quantum_information`

Simulacion de sistemas cuanticos de pocos qubits via statevector (numpy puro, sin qiskit): vector de Bloch de un qubit, aplicacion de puertas (H, X, Y, Z, CNOT, Toffoli) sobre registros de n qubits, algoritmos de Deutsch-Jozsa y Grover, entropia de von Neumann para cuantificar entrelazamiento entre subsistemas, y demostracion del codigo de correccion bit-flip por repeticion (bloque constructivo del codigo de Shor, no el codigo completo).

Modos disponibles:

- `bloch_vector`
- `gate_sequence`
- `deutsch_jozsa`
- `grover_search`
- `entanglement_entropy`
- `bit_flip_code`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "quantum_information",
    "arguments": {
      "mode": "bloch_vector",
      "params": {}
    }
  }
}
```

## `reaction_diffusion`

Sistemas de reaccion-difusion: Fisher-KPP 1D (frente de onda viajera, velocidad analitica c=2*sqrt(r*D) - modelo de colonizacion fungica) y Gray-Scott 2D (patrones de Turing: manchas, laberintos, ondas segun regimen feed/kill).

Modos disponibles:

- `fisher_kpp`
- `gray_scott`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "reaction_diffusion",
    "arguments": {
      "mode": "fisher_kpp",
      "params": {}
    }
  }
}
```

## `reaction_diffusion_real`

Inestabilidad de Turing (reaccion-difusion linealizada): evalua las 4 condiciones analiticas clasicas y compara tasa de crecimiento numerica vs analitica en el numero de onda mas inestable. Mecanismo detras de patrones biologicos (rayas, manchas, morfogenesis).

Modos disponibles:

- `check_turing_instability`
- `simulate_growth_rate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "reaction_diffusion_real",
    "arguments": {
      "mode": "check_turing_instability",
      "params": {}
    }
  }
}
```

## `refinance_analysis_tool`

Compara un credito actual vs una alternativa refinanciada (nueva tasa/plazo, costos de cierre). Modos: payment_comparison (cuota actual vs nueva), breakeven_analysis (meses para recuperar los costos de cierre via el ahorro mensual), total_cost_comparison (costo total actual vs nuevo bajo un horizonte de meses dado), refinance_decision (recomendacion conviene/no conviene combinando breakeven y horizonte de permanencia planeado). Modelo bajo los supuestos dados, no asesoria financiera real.

Modos disponibles:

- `validate`
- `payment_comparison`
- `breakeven_analysis`
- `total_cost_comparison`
- `refinance_decision`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "refinance_analysis_tool",
    "arguments": {
      "mode": "validate",
      "params": {}
    }
  }
}
```

## `retirement_planner_tool`

Planificacion de retiro con motor de interes compuesto: accumulation_projection (proyeccion de saldo con aportes que crecen por inflacion salarial), required_savings_rate (% de salario a ahorrar hoy para una meta de reemplazo de ingreso), withdrawal_sustainability (simulacion de decumulacion, regla de retiro tipo 4% de Bengen), replacement_ratio (% del ultimo salario cubierto por el fondo proyectado, con banda cualitativa). confidence_flag 'alta' para la mecanica (formulas cerradas de anualidad e iteracion aritmetica determinista); las tasas de retorno/inflacion futuras son un supuesto de quien llama, no una prediccion. No es asesoria financiera. validate corre 7 checks de referencia.

Modos disponibles:

- `accumulation_projection`
- `required_savings_rate`
- `withdrawal_sustainability`
- `replacement_ratio`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "retirement_planner_tool",
    "arguments": {
      "mode": "accumulation_projection",
      "params": {}
    }
  }
}
```

## `run_math_pipeline`

Encadena llamadas a los tools matematicos de octave-mcp (diferenciacion simbolica, Jacobiano, Lyapunov, ODEs stiff, bifurcacion, Hilbert, analisis de error, benchmark de metodos, interpolacion), pasando el output de un paso como input del siguiente via referencias '$save_as.campo.subcampo'. mode='validate' corre una demo fija (derivada -> analisis de error) sin pedir argumentos; mode='run' ejecuta los 'steps' dados.

Modos disponibles:

- `run`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "run_math_pipeline",
    "arguments": {
      "mode": "run",
      "params": {}
    }
  }
}
```

## `run_octave`

Ejecuta codigo GNU Octave

Parametros directos (sin `mode`):

- `code`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "run_octave",
    "arguments": {
      "code": null
    }
  }
}
```

## `savings_goal_tool`

Motor de interes compuesto para metas de ahorro (anualidad ordinaria, aportes a fin de periodo): future_value (valor futuro de capital inicial + aportes periodicos), required_contribution (aporte periodico necesario para alcanzar una meta en un plazo dado), time_to_goal (periodos necesarios para alcanzar una meta con aporte fijo, forma cerrada via logaritmo), goal_progress (meses restantes dado el ahorro acumulado actual y un aporte mensual fijo), inflation_adjusted_target (ajusta una meta nominal de hoy a su equivalente futuro bajo una tasa de inflacion esperada). Motor fundacional de la Fase D: retirement_planner_tool/education_funding_tool/financial_independence_tool reutilizan las mismas formulas cerradas. confidence_flag 'alta' para la mecanica (formulas estandar de interes compuesto); la tasa de interes/inflacion futura es un supuesto de quien llama, no una prediccion. validate corre 6 checks de referencia.

Modos disponibles:

- `future_value`
- `required_contribution`
- `time_to_goal`
- `goal_progress`
- `inflation_adjusted_target`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "savings_goal_tool",
    "arguments": {
      "mode": "future_value",
      "params": {}
    }
  }
}
```

## `sdf_tool`

Funciones de distancia con signo (SDF): primitivas (sphere/box/torus/cylinder/plane/capsule), booleanas hard y smooth (union/intersection/difference), normales por gradiente, y extraccion de malla via marching cubes. Base para mallado implicito y modelado geometrico orgánico (ej: sockets de prótesis, formas organicas).

Modos disponibles:

- `evaluate`
- `normals`
- `boolean`
- `extract_mesh`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "sdf_tool",
    "arguments": {
      "mode": "evaluate",
      "params": {}
    }
  }
}
```

## `semiclassical_cosmology_tool`

Fase 2 del puente cuantico-cosmologico: ecuacion de Friedmann modificada con la correccion holonomica estandar de Loop Quantum Cosmology H^2 = kappa*rho(a)*(1-rho(a)/rho_c), para un fluido FLRW homogeneo de ecuacion de estado w constante. mode=friedmann_lqg_correction integra la trayectoria a(t) simetrica alrededor del bounce; mode=bounce_dynamics da el diagnostico analitico (a_min, addot/a en el bounce, si es un bounce genuino) sin depender de diferenciacion numerica donde H=0; mode=power_spectrum es una utilidad FFT generica sobre cualquier serie temporal (no un pipeline completo de C_ell de CMB).

Modos disponibles:

- `friedmann_lqg_correction`
- `bounce_dynamics`
- `power_spectrum`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "semiclassical_cosmology_tool",
    "arguments": {
      "mode": "friedmann_lqg_correction",
      "params": {}
    }
  }
}
```

## `settlement_clusters`

Proxy arqueologico de barrios/clusters sociales: clusteriza coordenadas de hallazgos por distancia (union-find a radio fijo) en cada periodo/estrato, y rastrea clusters entre periodos consecutivos por proximidad de centroides -- detecta nacimiento y muerte de asentamientos. No hace inferencia cronologica, el orden de periodos lo define quien llama. Modes: analyze (requiere puntos_por_periodo y per

Modos disponibles (extraidos de `settlement_clusters_tool.py` via regex — **revisar a mano**):

- `analyze`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "settlement_clusters",
    "arguments": {
      "mode": "analyze",
      "params": {}
    }
  }
}
```

## `social_impact_tool`

Impacto social de desastres y de inversion publica: social_vulnerability_index (indice SoVI via suma de z-scores de indicadores socioeconomicos con signo configurable por indicador), displacement_estimate (poblacion desplazada y unidades de vivienda temporal requeridas a partir de dano habitacional por severidad y ocupacion promedio), equity_weighted_impact (pondera perdida/dano economico por un factor de vulnerabilidad social para priorizar inversion), casualty_estimate (estimacion simplificada de victimas a partir de fraccion de estructuras colapsadas, ocupacion y hora del dia, logica HAZUS-MH simplificada), validate (suite de 10 checks). Motor generico: no trae catalogo de indicadores/pesos por region (los provee quien llama), confidence_flag 'alta' para la mecanica.

Modos disponibles (extraidos de `social_impact_tool.py` via regex — **revisar a mano**):

- `casualty_estimate`
- `displacement_estimate`
- `equity_weighted_impact`
- `social_vulnerability_index`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "social_impact_tool",
    "arguments": {
      "mode": "casualty_estimate",
      "params": {}
    }
  }
}
```

## `spatial_statistics`

Estadistica espacial: autocorrelacion global (Moran's I y Geary's C con z-score/p-value bajo hipotesis nula de aleatoriedad), semivariograma empirico binneado por distancia, y kriging ordinario (interpolacion optima con modelo esferico/exponencial/gaussiano). Util para analisis de riesgo hidrologico multi-cuenca y variables ambientales georreferenciadas.

Modos disponibles:

- `morans_i`
- `gearys_c`
- `semivariogram`
- `kriging`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "spatial_statistics",
    "arguments": {
      "mode": "morans_i",
      "params": {}
    }
  }
}
```

## `spectral_analysis_tool`

Analisis espectral tipo ABRAVIBE: FFT, estimacion de FRF via H1 (Welch, promediado), y extraccion de parametros modales (frecuencia natural + amortiguamiento, metodo del ancho de banda de media potencia) DESDE UNA SEÑAL MEDIDA -- complementa a fem_advanced_tool, que los calcula desde el modelo K,M en vez de datos. mode='validate' genera la respuesta de un 1-GDL conocido a ruido blanco y verifica que se recuperan fn y zeta correctos desde la señal sintetica.

Modos disponibles:

- `fft_spectrum`
- `frf_h1`
- `modal_extraction`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "spectral_analysis_tool",
    "arguments": {
      "mode": "fft_spectrum",
      "params": {}
    }
  }
}
```

## `statistical_physics_tool`

Fisica estadistica: modelo de Ising 2D via Monte Carlo Metropolis (magnetizacion, energia, calor especifico, transicion de fase; params.backend='numpy' (default), 'numba' si esta instalado, u 'opencl' si hay pyopencl+GPU (usa checkerboard/red-black paralelo, equilibrio-equivalente pero no trayectoria-equivalente a los otros backends), para acelerar el sweep), y modelo de Potts para crecimiento de grano (microestructura).

Modos disponibles:

- `ising_2d`
- `potts_grain_growth`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "statistical_physics_tool",
    "arguments": {
      "mode": "ising_2d",
      "params": {}
    }
  }
}
```

## `statistics`

Estadistica e inferencia via Octave: linear_regression (minimos cuadrados), correlation (Pearson r), t_test (una muestra, t-stat + p-value via betainc), bayesian_beta_binomial (actualizacion conjugada Beta-Binomial). Pensado para analisis de riesgo (QGIS).

Modos disponibles:

- `linear_regression`
- `correlation`
- `t_test`
- `bayesian_beta_binomial`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "statistics",
    "arguments": {
      "mode": "linear_regression",
      "params": {}
    }
  }
}
```

## `stochastic_processes`

Procesos estocasticos: movimiento browniano (estandar/con drift/geometrico), proceso de Ornstein-Uhlenbeck (reversion a la media, util para variables ambientales con equilibrio), y cadenas de Markov discretas (distribucion estacionaria, tiempo de primer paso).

Modos disponibles:

- `brownian_motion`
- `ornstein_uhlenbeck`
- `markov_chain`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "stochastic_processes",
    "arguments": {
      "mode": "brownian_motion",
      "params": {}
    }
  }
}
```

## `structural_analysis`

Análisis estructural preliminar: reacciones/corte/momento/deflexión de vigas (simplemente apoyada o en voladizo), fuerzas axiales en cerchas 2D isostáticas (método de nudos), propiedades de sección (área, inercia, módulo, radio de giro), y chequeo de esfuerzo simple vs. esfuerzo admisible. Estimación preliminar, no reemplaza cálculo certificado por ingeniero estructural.

Modos disponibles:

- `beam_analysis`
- `truss_analysis`
- `section_properties`
- `stress_check`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "structural_analysis",
    "arguments": {
      "mode": "beam_analysis",
      "params": {}
    }
  }
}
```

## `survey_angles_tool`

Angulos y direcciones topograficas: bearing/azimut desde coordenadas, cierre angular de poligono, reduccion de angulos face-left/face-right.

Modos disponibles:

- `bearing_azimuth`
- `angle_closure`
- `mean_angle_reduction`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "survey_angles_tool",
    "arguments": {
      "mode": "bearing_azimuth",
      "params": {}
    }
  }
}
```

## `survey_area_volume_tool`

Area por coordenadas (shoelace), volumen de movimiento de tierra por area media entre secciones, volumen entre curvas de nivel.

Modos disponibles:

- `polygon_shoelace`
- `earthwork_avg_end_area`
- `contour_volume`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "survey_area_volume_tool",
    "arguments": {
      "mode": "polygon_shoelace",
      "params": {}
    }
  }
}
```

## `survey_curvature_tool`

Correccion combinada de curvatura terrestre y refraccion para angulos verticales observados.

Modos disponibles:

- `curvature_refraction`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "survey_curvature_tool",
    "arguments": {
      "mode": "curvature_refraction",
      "params": {}
    }
  }
}
```

## `survey_curves_tool`

Elementos de curva circular horizontal (T, L, E, M, cuerda) o curva vertical parabolica (elevaciones, punto alto/bajo).

Modos disponibles:

- `horizontal_circular`
- `vertical_parabolic`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "survey_curves_tool",
    "arguments": {
      "mode": "horizontal_circular",
      "params": {}
    }
  }
}
```

## `survey_distance_tool`

Correcciones de distancia: pendiente a horizontal, taquimetria/estadia, correccion EDM por indice de refraccion.

Modos disponibles:

- `slope_correction`
- `stadia`
- `edm_correction`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "survey_distance_tool",
    "arguments": {
      "mode": "slope_correction",
      "params": {}
    }
  }
}
```

## `symbolic`

Algebra simbolica via sympy: simplify, solve (resolver ecuaciones), differentiate (derivada), integrate (indefinida o definida con limites), taylor_series. Puente necesario porque Octave es 100% numerico.

Modos disponibles:

- `simplify`
- `solve`
- `differentiate`
- `integrate`
- `taylor_series`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "symbolic",
    "arguments": {
      "mode": "simplify",
      "params": {}
    }
  }
}
```

## `tax_estimation_tool`

Estimacion de impuesto sobre la renta con tramos progresivos provistos por quien llama (generico, sin tabla hardcodeada de ningun pais -los sistemas tributarios varian por jurisdiccion y cambian ano a ano-). Modos: marginal_tax (impuesto total sobre ingreso gravable, mas tasa efectiva y tasa marginal), after_tax_income (ingreso neto dado ingreso bruto, deducciones y tramos), bracket_breakdown (detalle de cuanto se tributa en cada tramo), what_if_income_change (impuesto marginal sobre un monto adicional de ingreso, ej. aumento o bono, y cuanto de ese monto queda neto). confidence_flag 'alta' para la mecanica de calculo progresivo (aritmetica determinista dados los tramos); los tramos, tasas y deducciones son un input de quien llama, no una tabla oficial ni actualizada por esta tool. No es asesoria fiscal ni legal; consultar la normativa vigente de la jurisdiccion correspondiente. validate corre 8 checks.

Modos disponibles:

- `marginal_tax`
- `after_tax_income`
- `bracket_breakdown`
- `what_if_income_change`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "tax_estimation_tool",
    "arguments": {
      "mode": "marginal_tax",
      "params": {}
    }
  }
}
```

## `tensor_calculus`

Calculo tensorial para geometria diferencial: simbolos de Christoffel, tensor de Riemann, tensor de Ricci, curvatura escalar y ecuaciones geodesicas a partir de una metrica g_mu_nu. Backend 'symbolic' (sympy, expresiones exactas) o 'numeric' (diferencias finitas centradas evaluadas en un punto). Incluye metricas precargadas: sphere_2d, polar_plane, schwarzschild.

Modos disponibles:

- `christoffel`
- `riemann`
- `ricci`
- `scalar_curvature`
- `geodesic_equations`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "tensor_calculus",
    "arguments": {
      "mode": "christoffel",
      "params": {}
    }
  }
}
```

## `text_analysis_math`

Matematica para linguistica computacional: distancias de edicion (Levenshtein, Jaro-Winkler), modelo de lenguaje n-grama con suavizado y perplejidad, leyes de frecuencia (Zipf, Heaps), y estilometria (KL / Jensen-Shannon entre distribuciones lexicas de dos textos) para atribucion de autoria o comparacion de corpus, incluyendo textos historicos.

Modos disponibles:

- `edit_distance`
- `ngram_model`
- `frequency_laws`
- `stylometry`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "text_analysis_math",
    "arguments": {
      "mode": "edit_distance",
      "params": {}
    }
  }
}
```

## `thermal_advanced_tool`

Modulos avanzados de calor/termodinamica: pcm_1d (fusion de material de cambio de fase, metodo de entalpia, validado contra solucion de Neumann del problema de Stefan), radiation_exchange (2 superficies grises difusas, red radiativa validada contra 3 casos limite cerrados), convection_correlations (Churchill-Chu, Blasius, Dittus-Boelter, validado contra limites e identidades exactas de las formulas), inverse_conductivity (recupera k desde datos T(x) ruidosos por regresion), thermodynamic_properties (gas ideal, capacidad calorifica de Debye validada contra Dulong-Petit y ley T^3, relacion de Kelvin Seebeck/Peltier).

Modos disponibles:

- `pcm_1d`
- `radiation_exchange`
- `convection_correlations`
- `inverse_conductivity`
- `thermodynamic_properties`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "thermal_advanced_tool",
    "arguments": {
      "mode": "pcm_1d",
      "params": {}
    }
  }
}
```

## `thermal_conduction_tool`

Conduccion de calor FEM: steady_1d (barra 1D estacionaria, Dirichlet en ambos extremos, generacion volumetrica uniforme opcional), transient_1d (misma barra, Crank-Nicolson en el tiempo, extremos fijados a T=0 en t=0+), y steady_2d (placa rectangular via triangulos lineales, tres lados a T1 y uno a T2). Validado contra soluciones analiticas de libro de texto (perfil lineal/parabolico en steady_1d, serie de Fourier en transient_1d y steady_2d).

Modos disponibles:

- `steady_1d`
- `transient_1d`
- `steady_2d`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "thermal_conduction_tool",
    "arguments": {
      "mode": "steady_1d",
      "params": {}
    }
  }
}
```

## `thermal_structural_tool`

Acoplamiento termico-estructural: tensiones inducidas por deltaT. mode='thermal_bar': barra empotrada ambos extremos, deltaT uniforme, valida contra sigma=-E*alpha*deltaT. mode='thermal_plate': placa CST totalmente empotrada, deltaT uniforme, valida contra solucion exacta equibiaxial sigma=-E*alpha*deltaT/(1-nu). mode='validate' corre ambos.

Modos disponibles:

- `thermal_bar`
- `thermal_plate`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "thermal_structural_tool",
    "arguments": {
      "mode": "thermal_bar",
      "params": {}
    }
  }
}
```

## `time_frequency_tool`

Analisis tiempo-frecuencia: espectrograma STFT con ventana de Hann y verificacion de la cresta de frecuencia en un chirp lineal (mode='stft'), distribucion de Wigner-Ville (pseudo-WVD via señal analitica de Hilbert) con cresta exacta para chirps LFM (mode='wigner_ville'), y demostracion/verificacion del artefacto de terminos cruzados de la WVD en señales multi-componente contrastado con la STFT libre de ese artefacto (mode='cross_terms'). mode='validate' corre los 3 self-tests.

Modos disponibles:

- `stft`
- `wigner_ville`
- `cross_terms`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "time_frequency_tool",
    "arguments": {
      "mode": "stft",
      "params": {}
    }
  }
}
```

## `topology_optimization_tool`

Optimizacion topologica de estructuras via metodo SIMP (Solid Isotropic Material with Penalization): encuentra la distribucion de densidad de material x(elemento) en [0,1] sobre una malla FEM que minimiza la compliance (maximiza rigidez) sujeta a una fraccion de volumen de material disponible. Incluye filtro de densidad (evita checkerboarding, garantiza independencia de malla) y update por Criterio de Optimalidad (OC). mode='validate' corre el benchmark estandar de viga cantilever y verifica restriccion de volumen exacta, densidades acotadas en [0,1], y mejora de compliance vs. densidad uniforme. mode='optimize' resuelve un caso: nelx, nely (tamano de malla), volfrac (fraccion de volumen 0-1), penal (exponente de penalizacion SIMP, tipico 3.0), rmin (radio de filtro en elementos), max_loop, move (limite de movimiento por iteracion), tol, bc ('cantilever' por ahora). Devuelve density_field como grilla 2D lista para visualizar.

Modos disponibles:

- `validate`
- `optimize`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "topology_optimization_tool",
    "arguments": {
      "mode": "validate",
      "params": {}
    }
  }
}
```

## `traverse_adjustment_tool`

Ajuste de poligonales: regla de Bowditch, regla del transito, cierre lineal, precision relativa, o full_traverse con ambos metodos.

Modos disponibles:

- `bowditch`
- `transit_rule`
- `closure_check`
- `linear_misclosure`
- `relative_accuracy`
- `full_traverse`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "traverse_adjustment_tool",
    "arguments": {
      "mode": "bowditch",
      "params": {}
    }
  }
}
```

## `tritbraid`

DSL TritBraid: secuencias de trenzas de Fibonacci que colapsan a un trit ternario (-1,0,+1). Tokens del programa: 0=identidad, 1=sigma1 (diagonal, no mezcla canales), 2=sigma2 (mezcla via matriz F), M=medicion (colapso proyectivo, regla de Born). Modes: run_program (ejecuta el programa dado y devuelve traza completa), validate_physics (verifica unitariedad, invariancia bajo identidad/sigma1, y mez

Modos disponibles (extraidos de `tritbraid_tool.py` via regex — **revisar a mano**):

- `run_program`
- `validate_physics`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "tritbraid",
    "arguments": {
      "mode": "run_program",
      "params": {}
    }
  }
}
```

## `urban_planning_tool`

Metricas de planificacion urbana: land_use_mix_index (indice de mezcla de uso de suelo via entropia de Shannon normalizada, 1.0=mezcla equilibrada, 0.0=monocultivo), service_accessibility_index (fraccion de poblacion cubierta dentro de una distancia umbral a un servicio), density_capacity_ratio (densidad poblacional y, si se provee capacidad de diseno, ratio de utilizacion con flag over_capacity), infrastructure_demand_projection (proyeccion de demanda via crecimiento poblacional geometrico y demanda per capita, detecta el anio en que se supera la capacidad instalada), validate (suite de 10 checks). confidence_flag 'alta' (formulas cerradas estandar); el crecimiento poblacional es geometrico simple, tratar la proyeccion como escenario, no pronostico.

Modos disponibles (extraidos de `urban_planning_tool.py` via regex — **revisar a mano**):

- `density_capacity_ratio`
- `infrastructure_demand_projection`
- `land_use_mix_index`
- `service_accessibility_index`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "urban_planning_tool",
    "arguments": {
      "mode": "density_capacity_ratio",
      "params": {}
    }
  }
}
```

## `viral_lattice_tool`

Dos motores: viral_spread_pde simula un sistema TIV (celulas blanco/infectadas/virus) con difusion 1D via diferencias finitas explicitas (analogo espacial al modelo in-host de Nowak & May); capsid_fock_state representa el numero de subunidades ensambladas de una capside como estado coherente en espacio de Fock (distribucion de Poisson, <n>=Var(n)=alpha^2). mode='viral_spread_pde' (beta, delta, p, c, D_T, D_I, D_V, T0, I0_peak, V0, L, nx, t_final, dt); mode='capsid_fock_state' (alpha, n_max); mode='validate' corre ambos con parametros de referencia.

Modos disponibles:

- `viral_spread_pde`
- `capsid_fock_state`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "viral_lattice_tool",
    "arguments": {
      "mode": "viral_spread_pde",
      "params": {}
    }
  }
}
```

## `water_resource_tool`

Hidrologia de cuencas para gestion de recursos hidricos: rational_method (caudal pico Qp=CIA/360), scs_curve_number (escorrentia directa por numero de curva SCS), time_of_concentration (formula de Kirpich), water_balance (balance de masa de embalse/cuenca con deteccion de deficit y desborde).

Modos disponibles (extraidos de `water_resource_tool.py` via regex — **revisar a mano**):

- `rational_method`
- `scs_curve_number`
- `time_of_concentration`
- `validate`
- `water_balance`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "water_resource_tool",
    "arguments": {
      "mode": "rational_method",
      "params": {}
    }
  }
}
```

## `wave_propagation_tool`

Propagacion de ondas 2D: FDTD escalar 2D con verificacion de velocidad de frente de onda via tiempo de arribo a dos radios (mode='wave_2d'), interferencia de dos fuentes coherentes tipo Young con espaciado de franjas validado contra teoria (mode='interference'), y difraccion de Fraunhofer de rendija simple con posicion del primer minimo validada (mode='diffraction'). mode='validate' corre los 3 self-tests.

Modos disponibles:

- `wave_2d`
- `interference`
- `diffraction`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "wave_propagation_tool",
    "arguments": {
      "mode": "wave_2d",
      "params": {}
    }
  }
}
```

## `wavelet`

Analisis wavelet para senales no estacionarias: CWT (espectrograma tiempo-escala), DWT multinivel con reconstruccion, denoising por umbralizacion (Donoho-Johnstone), y deteccion de transitorios via energia anomala por banda. Complementa a hilbert_tool para senales con eventos discretos o no estacionarias.

Modos disponibles:

- `cwt`
- `dwt`
- `denoise`
- `transient_detection`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "wavelet",
    "arguments": {
      "mode": "cwt",
      "params": {}
    }
  }
}
```

## `wildfire_risk_tool`

Peligrosidad de incendios forestales via modelo de Rothermel (1972) con ponderacion muerto/vivo: rate_of_spread (velocidad de propagacion ft/min, intensidad de linea de fuego e Byram, largo de llama, dado viento/pendiente/humedad y un modelo de combustible), fuel_model_info (parametros crudos de un modelo), list_fuel_models (codigos disponibles por catalogo), validate (suite de 10 checks de consistencia fisica). fuel_catalog: anderson13 (13 modelos, confianza media-alta), scott_burgan40 (40 modelos, confianza BAJA -- valores estimados por patron, no verificados contra la tabla fuente, ver campo data_confidence en cada respuesta), o custom (fuel_model provisto por quien llama, sin datos hardcodeados).

Modos disponibles (extraidos de `wildfire_risk_tool.py` via regex — **revisar a mano**):

- `fuel_model_info`
- `list_fuel_models`
- `rate_of_spread`
- `validate`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "wildfire_risk_tool",
    "arguments": {
      "mode": "fuel_model_info",
      "params": {}
    }
  }
}
```

## `workspace_delete`

Borra un run del workspace (libera espacio en disco).

Parametros directos (sin `mode`):

- `run_id`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "workspace_delete",
    "arguments": {
      "run_id": null
    }
  }
}
```

## `workspace_describe`

Muestra shapes/dtypes de un run sin cargar los arrays completos a memoria (util para trayectorias largas antes de graficar).

Parametros directos (sin `mode`):

- `run_id`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "workspace_describe",
    "arguments": {
      "run_id": null
    }
  }
}
```

## `workspace_list`

Lista todos los runs guardados en el workspace, opcionalmente filtrados por tool de origen (ej: 'compute_lyapunov_exponent').

Parametros directos (sin `mode`):

- `filter_tool`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "workspace_list",
    "arguments": {
      "filter_tool": null
    }
  }
}
```

## `workspace_load`

Carga un run guardado previamente por run_id. Si keys se omite, devuelve todos los arrays (cuidado con trayectorias muy largas: usar workspace_describe primero).

Parametros directos (sin `mode`):

- `run_id`
- `keys`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "workspace_load",
    "arguments": {
      "run_id": null,
      "keys": null
    }
  }
}
```

## `workspace_save`

Guarda arrays/resultados de un analisis bajo un run_id para reutilizarlos despues (ej: en plot_tool) sin recalcular. Si run_id se omite, se autogenera.

Parametros directos (sin `mode`):

- `run_id`
- `data`
- `meta`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "workspace_save",
    "arguments": {
      "run_id": null,
      "data": null,
      "meta": null
    }
  }
}
```

