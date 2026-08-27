# octave-mcp

Servidor MCP (JSON-RPC manual, sin FastMCP) que expone 326 herramientas matemáticas y de simulación científica sobre Octave/Python, pensadas para usarse desde Claude Desktop u otros clientes MCP.

> **Nota de unificación:** este repositorio es el único proyecto activo. El antiguo `mcp-octave-real` (FastMCP, 39 tools) fue absorbido por completo — todas sus herramientas, incluidas las de historia cuantitativa (`plague_sir`, `settlement_clusters`, `historical_extractor`, `braid_group`, Benford en `historian`), viven ahora acá. `mcp-octave-real` queda deprecado y no debe usarse ni documentarse como proyecto en paralelo.

## Arquitectura

- `server.py`: dispatcher manual (sin FastMCP). Cada tool nuevo requiere tres ediciones coordinadas: línea de import, entrada en la lista `TOOLS`, y bloque `elif tool_name ==` en el dispatch.
- Dependencias: numpy, sympy y scipy (`advanced_probability_tool`, `advanced_stochastic_tool` y `multivariate_bayes_tool` dependen de scipy.stats).
- Dependencia opcional: paquete Octave `symbolic` (`pkg install -forge symbolic`) para el check simbolico de `statmech_partition_tool`; si no esta instalado, ese check se salta (`skipped`) sin afectar el resultado global de `validate`.
- Test rápido: pipear `initialize`, `tools/list`, `tools/call` (3 líneas JSON-RPC) a `timeout 30 python3 server.py`.
- Workspace persistente (`workspace_save` / `workspace_load` / `workspace_list` / `workspace_describe` / `workspace_delete`) para reutilizar resultados entre llamadas sin recomputar.

## Herramientas por área

### Orquestación y utilidades base
`octave_run`, `octave_run_script`, `octave_eval_expr`, `octave_version`, `run_math_pipeline`, `math_interpreter`, `math_explainer`, `math_error_analyzer`, `math_benchmark`, `cross_validation`, `plot_workspace_run`, `math_visualization`

### Gestión de workspace
`workspace_save`, `workspace_load`, `workspace_list`, `workspace_describe`, `workspace_delete`

### Álgebra, cálculo y análisis
`linear_algebra`, `symbolic`, `ocas_symbolic`, `abstract_algebra`, `compute_gradient_hessian`, `compute_jacobian`, `compute_hilbert_transform`, `tensor_calculus`, `integrate_stiff_ode`, `pde`, `math_interpolation`

### Sistemas dinámicos, caos y control
`compute_lyapunov_exponent`, `compute_lyapunov_v2`, `compute_bifurcation_diagram`, `population_dynamics`, `reaction_diffusion`, `reaction_diffusion_real`, `percolation_theory`, `stochastic_processes`, `control_theory`, `optimal_control`, `optimization`

### Estadística, datos y aprendizaje
`statistics`, `machine_learning_math`, `information_theory`, `spatial_statistics`, `network_science`, `persistent_homology`, `wavelet`, `entropy_structure`, `text_analysis_math`, `chemometrics_tool`, `econometrics_tool`, `graph_algorithms`, `glm_tool`, `clustering_tool`, `mcdm`

### Probabilidad avanzada e inferencia bayesiana

- **`advanced_probability_tool`** — Probabilidad avanzada e inferencia bayesiana. Modos (`mode` + `params`):
  - **`distributions`** — pdf/cdf/cuantiles/muestreo para 15 distribuciones (continuas y discretas) vía `scipy.stats`. Validado contra momentos analíticos (error <5% en media y varianza sobre 200k muestras). Parámetros: `name` (`normal`, `t`, `chi2`, `f`, `uniform`, `exponential`, `beta`, `gamma`, `weibull`, `lognormal`, `binomial`, `poisson`, `geometric`, `negative_binomial`, `hypergeometric`), `action` (`pdf`|`cdf`|`quantile`|`sample`|`summary`), `params` (parámetros propios de la distribución), `x`/`q`/`n_samples`/`seed` según acción.
  - **`bayesian_inference`** — Metropolis-Hastings propio para `beta_binomial`, `normal_known_variance`, y `linear_regression`. Validado contra posteriores conjugados exactos (error <0.1% en media, <2% en varianza).
  - **`model_comparison`** — WAIC y LOO (importance sampling con pesos truncados; no es PSIS completo). Valida correctamente que el modelo verdadero gana sobre uno mal especificado (172 vs 299 en el caso sintético de referencia).
  - **`posterior_predictive`** — p-value predictivo posterior con estadístico de prueba (max/min/mean/sd). Calibración de intervalos verificada al 90% (±0.2pp). El p-value es conservador por construcción (no uniforme), comportamiento documentado en la literatura, no un bug.
  - **`validate`** — corre todos los chequeos anteriores de una vez y devuelve `validation_passed`.

- **`advanced_stochastic_tool`** — Procesos estocásticos avanzados, numpy-only:
  - `hmm` — Hidden Markov Model discreto (forward-backward exacto + Viterbi). Validado contra fuerza bruta.
  - `kalman` — Filtro de Kalman lineal-gaussiano. Validado: MSE filtrado < MSE observación cruda, covarianza converge al punto fijo de Riccati.
  - `particle_filter` — Bootstrap particle filter con resampling sistemático. Validado contra Kalman (error relativo <5%).
  - `garch` — GARCH(1,1) por máxima verosimilitud con reinicios múltiples. Recupera parámetros con error <15% en varianza incondicional.

- **`multivariate_bayes_tool`** — Estadística bayesiana multivariada y reducción de dimensión:
  - `mvn_sample` / `mvt_sample` / `wishart_sample` — muestreo y verificación de momentos para normal, t y Wishart multivariadas.
  - `hierarchical` — modelo jerárquico normal-normal (estilo "8 schools") vía Gibbs sampling.
  - `hmc_regression` — regresión lineal bayesiana vía Hamiltonian Monte Carlo (leapfrog propio). Tasa de aceptación >95%.
  - `pca_biplot` — PCA vía SVD y eigh, cross-validados entre sí.
  - `pca_cv` — selección de componentes vía cross-validation real (holdout) con detección de codo tipo kneedle.
  - `factor_analysis` — Factor Analysis vía EM (Rubin-Thayer).

### Física y química
`quantum_information`, `qm_potential_well`, `nuclear_decay_chain`, `enzyme_kinetics`, `antibiotic_diffusion`, `population_genetics`, `braid_group`, `tritbraid`, `statistical_physics_tool`, `cfd_tool`, `statmech_partition_tool`

### Matemática financiera y teoría de juegos
`financial_math` (Black-Scholes, griegas, VaR, anualidades, bonos, riesgo catastrófico vía Monte Carlo Poisson compuesto/lognormal), `game_theory`

### Historia cuantitativa, arqueología y etnomatemática
*(absorbidas de `mcp-octave-real`)*
`historian`, `historical_extractor`, `archaeological_simulation`, `settlement_clusters`, `plague_sir`, `paleography`, `archaeoastronomy`, `numeral_systems_embedding`, `math_philosophy_history`, `ethnomath`, `ethnomath2`, `originarios`, `levant`, `ancestral_octave`, `ancient_calculator`, `music_math`

### Construcción y cubicaciones
> ⚠️ Estimación preliminar / educativa. `structural_analysis` no reemplaza el cálculo y timbre de un ingeniero estructural para obra real.

`quantity_takeoff` (volumen de hormigón, encofrado, peso de acero, excavación prismática, conteo de albañilería, resumen BOQ), `structural_analysis` (reacciones/corte/momento/deflexión de vigas, fuerzas axiales en cerchas 2D vía método de nudos con autoverificación de equilibrio, propiedades de sección, chequeo de esfuerzo), `earthworks` (volumen por área media entre secciones transversales, método de grilla para corte/relleno en terreno irregular, esponjamiento/contracción, diagrama de masas y puntos de balance), `budgeting_tool` (costo directo, análisis de precio unitario/APU, gastos generales/utilidad/contingencia/IVA, escalamiento por inflación, presupuesto agregado por capítulos), `construction_scheduling_tool` (ruta crítica vía CPM, carga diaria de recursos, compresión de cronograma/crashing por menor pendiente de costo)

### Topografía y geomática
`survey_angles_tool` (conversión de azimuts/rumbos, notación N/S-E/W), `survey_distance_tool` (distancia horizontal/vertical por estadia, corrección de pendiente), `survey_curvature_tool` (corrección por curvatura y refracción terrestre), `traverse_adjustment_tool` (ajuste de poligonales, cierre de coordenadas), `survey_curves_tool` (curvas circulares horizontales: tangente, longitud de curva, externa), `survey_area_volume_tool` (área por coordenadas, volumen entre secciones)

### Geometría, mallas y cosmología
`distmesh_tool` (generación de malla 2D, algoritmo de Persson & Strang), `sdf_tool` (funciones de distancia con signo), `lscm_tool` (parametrización conforme de superficies por mínimos cuadrados), `mesh_pde_tool` (EDPs sobre malla no estructurada), `mesh_spectral_tool` (análisis espectral de malla), `geometric_algebra_protein` (álgebra geométrica aplicada a estructura de proteínas), `quantum_astro_tool`, `semiclassical_cosmology_tool`, `cosmological_mcmc_tool`, `quantum_cosmology_tool`, `polarization_mapping`

### Biología computacional
`genome_signal_analysis`, `bacterial_growth_tool`, `viral_lattice_tool`, `enzyme_stochastic`, `evo_LGCA_tool`, `optical_sequence_id`, `infrasound_tool`

### Divulgación matemática
`math_humanizer_tool` (conceptos matemáticos traducidos a analogías cotidianas + conexión filosófica + nota técnica — contenido de referencia curado, mismo espíritu que `math_philosophy_history` o `ethnomath`)

---

*Correr `tools/list` contra el servidor es la fuente de verdad para el conteo exacto de tools.*

## Física / simulación (bloque final del roadmap)

| Tool | Acciones | Validacion analitica | Error numerico |
|---|---|---|---|
| `multibody_dynamics_tool` | `compound_pendulum`, `rigid_body_euler`, `two_link_manipulator` | T=2π√(I/mgd); conservacion de energia/\|L\|² en rotacion libre de par; conservacion de energia en pendulo doble | 0.016% / drift ~3.7e-13 / drift ~1.1e-12 |
| `particle_simulation_tool` | `kepler_orbit`, `elastic_collision_nbody`, `random_walk_diffusion` | 3ª ley de Kepler T=2π√(a³/GM); formula de colision elastica de libro de texto; MSD=2Dt | 5e-13% / drift ~1e-15 / 0.34% |
| `finite_element_tool` | `bar_1d`, `beam_bending`, `truss_2d` | u=PL/AE (barra); δ=PL³/3EI (viga voladizo Euler-Bernoulli); equilibrio de nodos (cercha) | 0% / ~1.7e-12% / residual 0 |

Pendiente: conectores externos (FreeCAD, BIM/IFC) — oCAS ya integrado.

## Gases y Exploracion del Catalogo

- **gas_tool**: gas ideal (`PV=nRT`); gases reales via Van der Waals (cubica exacta,
  Cardano), Dieterici, Berthelot y Redlich-Kwome (Newton-Raphson para V dado P);
  mezclas (Dalton, Amagat, entropia y Gibbs de mezcla); teoria cinetica molecular
  (velocidades caracteristicas, distribucion de Maxwell-Boltzmann, ley de Graham);
  flujo compresible (numero de Mach, proceso adiabatico, ondas de choque normal
  via Rankine-Hugoniot, relacion area-Mach en toberas); fugacidad via integracion
  numerica de (Z-1)dP/P. Validado contra STP (V_m=22.414 L), tablas NACA 1135
  (M1=2 -> M2=0.5774, P2/P1=4.5) y round-trip P->V->P en las 4 ecuaciones de estado.
- **knowledge_graph_tool**: guia de exploracion sobre el propio catalogo de tools.
  `mode=search`: busca tools relevantes para una consulta en lenguaje natural
  (scoring lexico sobre nombre+descripcion). `mode=related`: dado el nombre de una
  tool, encuentra otras que comparten vocabulario. `mode=stats`: panorama del
  catalogo completo. Se deriva en vivo de `TOOLS` (recibido por parametro desde el
  dispatcher) — no mantiene un grafo aparte, se actualiza solo cuando se agregan
  tools nuevas.

## Biorrefineria

- **biorefinery_tool**: balances de masa/energia y cinetica quimica para procesos
  biomasa -> biocombustible (pirolisis, hidrotratamiento, fermentacion). `mode=mass_balance`:
  balance de masa global en estado estacionario, resuelve una incognita entre streams
  de entrada/salida o reporta error de cierre. `mode=energy_balance`: balance de
  energia (calor sensible + latente via entalpias especificas), resuelve Q o reporta
  cierre. `mode=hhv_correlation`: poder calorifico superior/inferior (HHV/LHV) desde
  composicion elemental C/H/O/N/S/Ash via correlacion de Channiwala-Parikh (2002,
  error tipico ~1.45%). `mode=yield_efficiency`: rendimientos masicos/energeticos de
  producto(s) respecto a la materia prima y eficiencia energetica global. Bloque de
  cinetica: `mode=arrhenius` (`submodo=directo` calcula k desde A/Ea/T; `submodo=dos_puntos`
  resuelve Ea/A por sistema exacto desde dos pares (T,k); `submodo=regresion` ajusta
  ln(k) vs 1/T por minimos cuadrados sobre 3+ puntos, reportando R^2 como indicador de
  consistencia Arrhenius en el rango de T). `mode=rate_law`: velocidad de reaccion de
  orden general multi-reactivo, -r=k*prod(C_i^orden_i). `mode=batch_conversion`: formas
  integradas orden 0/1/2 para reactor batch de un reactivo limitante, resuelve tiempo o
  conversion (X) dado el otro, mas concentracion y vida media. `mode=pyrolysis_yield`:
  distribucion tipica de productos (liquido/char/gas) por regimen de pirolisis
  (lenta/intermedia/rapida/gasificacion) -- explicito via `regimen`, o clasificado
  automaticamente desde velocidad de calentamiento, tiempo de residencia de vapor y/o
  T_pico -- via valores de referencia de Bridgwater (2012); opcionalmente convierte a
  fracciones de masa/energia si se da `m_feed`/`HHV_feed`. Bloque de hidrotratamiento
  (HDO): `mode=hdo_stoichiometry` calcula consumo de H2 y coproductos (H2O/CO/CO2)
  para una masa de O removida, repartida entre rutas HDO/DCO/DCO2 (`ruta_reparto`,
  default 100% HDO); `mode=hdo_degree` calcula grado de desoxigenacion (%DOD, base
  masa y base molar O/C) y razon H/C molar (diagrama de Van Krevelen) entre carga y
  producto, para caracterizar severidad de saturacion. Validado: verificacion
  cruzada del segundo punto en `dos_puntos` (error ~1e-13%), round-trip X->t->X en
  `batch_conversion` orden 2 (recupera X=0.8 exacto), clasificacion correcta de los
  4 regimenes de `pyrolysis_yield` (incluida prioridad de gasificacion cuando
  T_pico>=700C independiente del heating rate), y `hdo_stoichiometry` con ruta 100%
  HDO reproduce exacto el minimo estequiometrico PM_H2/PM_O=0.126 kg H2/kg O removido.

## Acustica y Electromagnetismo

- **acoustics_tool**: ondas de presion 1D (`pressure_wave_1d`), modos propios de sala
  (`room_modes`), tiempo de reverberacion via formula de Sabine (`reverberation_sabine`).
  Validado contra solucion analitica y contra la relacion esperada RT60(reflectante) >
  RT60(absorbente).
- **electromagnetic_tool**: propagacion de campo E en 1D via FDTD leapfrog con bordes PEC
  (`wave_1d`); cristal fotonico 1D por matriz de transferencia, condicion de Bloch y deteccion
  de band gaps (`photonic_bandgap`). Validado end-to-end, incluyendo un apilado de cuarto de
  onda con el gap centrado exactamente en la frecuencia de diseno f0.


---


## Catalogo ampliado (326 tools totales -- seccion generada automaticamente desde `tools/list`, complementa las categorias curadas arriba)


*Las 122 tools de las secciones anteriores no se repiten aca. Esta seccion cubre las 202 tools agregadas despues de la ultima curacion manual del README.*


### Desastres y riesgo natural

- `bilevel_interdiction_tool` -- Optimiza estrategias de defensa en infraestructuras interdependientes
- `cascade_orchestrator_tool` -- Orquestador transversal que conecta cascadas entre múltiples dominios
- `cascading_failure_tool` -- Fallos en cascada en redes de infraestructura, con redistribucion de carga real (distinto de percolation_theory_tool, que es conectividad...
- `cascading_outbreak_predictor` -- Predice brotes tempranos usando teoría de percolación
- `critical_infrastructure_tool` -- Resiliencia de infraestructura critica modelada como grafo: network_redundancy_n1 (identifica aristas cuya remocion desconecta la red,...
- `disaster_early_warning_tool` -- Orquestador de alerta temprana de desastres: combina terrain_elevation_tool, hydrometeo_data_tool, flood_modeling_tool,...
- `disaster_economics_tool` -- Impacto economico de desastres (capa economica, no re-simula la fisica del peligro): direct_loss (perdida directa =...
- `disaster_simulation_tool` -- Simulacion Monte Carlo de desastres (modelo actuarial frecuencia-severidad Poisson-LogNormal) para gestion publica de riesgos:...
- `domino_effect_tool` -- Modela cascadas matemáticas fundamentales
- `early_warning_tool` -- Analisis de series temporales para alertas tempranas: threshold_crossing (cruce de umbrales tipo semaforo con proyeccion de tiempo hasta...
- `earthquake_analysis_tool` -- Peligrosidad sismica: deterministic (PGA por atenuacion de Esteva desde magnitud y distancia, amplificacion de sitio NEHRP simplificada,...
- `flood_connectivity_tool` -- Inundacion por conectividad (priority-flood) sobre una malla 2D con elevacion por nodo
- `flood_modeling_tool` -- Modelado de crecidas para planificacion de drenajes: scs_triangular_hydrograph (hidrograma unitario triangular SCS), muskingum_routing...
- `flood_risk_narrator` -- Clasifica el riesgo de inundación (bajo/medio/alto/crítico) y genera un reporte en lenguaje natural a partir de profundidad y velocidad...
- `forest_fire_simulator` -- Automata celular para propagacion de incendios forestales en grilla 2D (estados: 0=vacio/quemado, 1=en llamas, 2=bosque)
- `information_cascade_tool` -- Modela propagación de información en redes sociales
- `infrastructure_resilience_tool` -- Evaluacion de infraestructura critica ante desastres: curvas de fragilidad lognormales (genericas, el usuario pasa sus propios parametros...
- `landslide_risk_tool` -- Riesgo de deslizamiento de talud: infinite_slope_fs (factor de seguridad via el modelo clasico de Mohr-Coulomb para talud infinito:...
- `natural_hazard_risk_tool` -- Modelado de riesgo multifactorial (R=H*E*V/A) para gestion publica de desastres naturales: risk_index (indice de riesgo puntual con...
- `physics_based_fire_model` -- Extension 2D del modelo Fisher-KPP con adveccion vectorial de viento (magnitud+angulo): frente de incendio circular con reaccion...
- `sandpile_avalanche_tool` -- Modelo de Bak-Tang-Wiesenfeld (monton de arena, 1987): grilla NxN con frontera abierta, colapso ('toppling') cuando una celda alcanza el...
- `systemic_risk_tool` -- Contagio financiero en red de exposiciones interbancarias (mecanismo de Eisenberg & Noe 2001, version simplificada por rondas): cada...
- `wildfire_intensity_model_tool` -- Modelo de intensidad de incendios forestales: intensidad de linea de fuego (Byram 1959), ranking de agentes extintores, corredores de...
- `wildfire_risk_tool` -- Peligrosidad de incendios forestales: rate_of_spread (velocidad de propagacion via Rothermel, intensidad de linea de fuego y largo de...

### Clima, energia y sostenibilidad

- `battery_sizing_tool` -- Dimensionamiento de sistemas de bateria para energia renovable aislada: capacidad por autonomia (battery_capacity), potencia de arreglo...
- `carbon_footprint_tool` -- Estima y compara la huella de carbono (kg CO2) de entregar una misma energia util via combustion de lena vs
- `circular_economy_tool` -- Flujo de materiales con balance de masa por etapa (input/output/reciclaje/perdidas), encadenamiento multi-etapa, y un Material...
- `climate_scenario_tool` -- Analisis de escenarios climaticos: trend_analysis (regresion lineal, Mann-Kendall, changepoint CUSUM sobre series temporales),...
- `climate_tool` -- Fisica climatica especifica con validacion analitica
- `deforestation_tool` -- Modelo agregado de cambio de cobertura forestal: simula la trayectoria de area de bosque bajo presion de expansion agricola y tala,...
- `heating_value_tool` -- Poder calorifico (HHV/LHV) de combustibles comunes de combustion (CH4, H2, CO, C2H6, C3H8, C2H4, C2H2) via polinomios NASA-7 -- formula...
- `land_use_change_tool` -- Modelo de cambio de uso de suelo: mode=transition_model proyecta proporciones de cobertura (bosque/agricultura/urbano/agua) via cadena de...
- `public_data_ingest_tool` -- Calidad e ingesta de datos publicos: outlier_detection_zscore (media/std, documenta el efecto de masking donde un outlier extremo infla...
- `renewable_mpc_controller` -- MPC de despacho economico para microrred PV+eolica+bateria+red, horizonte rodante
- `renewable_potential_tool` -- Potencial de energia renovable a nivel comunitario/primer-orden
- `soil_erosion_tool` -- Modelado de erosion de suelo, complementario a land_use_change_tool
- `solar_heating_sizer` -- Dimensiona un sistema fotovoltaico de apoyo a calefaccion usando irradiancia real del peor dia del ano (solsticio de invierno),...
- `solar_radiation_tool` -- Geometria solar (declinacion, ecuacion del tiempo, posicion del sol, amanecer/atardecer) e irradiancia de cielo despejado (modelo Hottel...
- `sustainable_sourcing_tool` -- Calcula puntajes 0-10 (10=mejor) para transporte (modo+distancia), estacionalidad, certificaciones, y packaging de un alimento, mas un...
- `urban_planning_tool` -- Metricas de planificacion urbana: land_use_mix_index (indice de mezcla de uso de suelo via entropia de Shannon normalizada, 1.0=mezcla...
- `water_resource_tool` -- Hidrologia de cuencas para gestion de recursos hidricos: rational_method (caudal pico Qp=CIA/360), scs_curve_number (escorrentia directa...
- `wind_power_curve_tool` -- Potencia eolica: densidad del aire por altitud (ISA), potencia disponible en el viento y limite de Betz, curva de potencia cubica...

### Finanzas personales y actuaria

- `credit_simulation_tool` -- Motor de amortizacion de creditos (sistema frances, cuota fija): payment_calculator (cuota mensual, total pagado, total interes),...
- `debt_snowball_tool` -- Estrategias de pago de multiples deudas con motor de simulacion mes-a-mes
- `education_funding_tool` -- Planificacion de ahorro para educacion: cost_projection (costo futuro proyectado con inflacion educativa propia, distinta de la inflacion...
- `emergency_fund_tool` -- Fondo de emergencia: coverage_target (monto objetivo dado gasto mensual esencial y meses de cobertura deseados), current_coverage_months...
- `financial_literacy_score_tool` -- Score compuesto de salud financiera, combinando 4 componentes ya calculados por otras tools de Fase D (no los recalcula): liquidez (meses...
- `habit_streak_tool` -- Modelado de consistencia/adherencia a habitos financieros: streak_analysis (racha actual, racha mas larga, numero de rachas y tasa de...
- `insurance_risk_tool` -- Seguros y reaseguro de catastrofes: pure_premium (prima pura mas cargas de gasto y margen de utilidad, sobre una distribucion de perdida...
- `investment_portfolio_tool` -- Analisis de portafolio de inversion: expected_return_variance (retorno esperado y volatilidad del portafolio dado pesos,...
- `life_insurance_math_tool` -- Calculos de seguro de vida: human_life_value (valor presente del ingreso neto futuro de la persona asegurada, con crecimiento salarial...
- `personal_budget_tool` -- Presupuesto personal/domestico: income_expense_balance (balance ingreso-gasto, tasa de ahorro, breakdown porcentual por categoria),...
- `refinance_analysis_tool` -- Compara un credito actual vs una alternativa refinanciada (nueva tasa/plazo, costos de cierre)
- `retirement_planner_tool` -- Planificacion de retiro con motor de interes compuesto: accumulation_projection (proyeccion de saldo con aportes que crecen por inflacion...
- `savings_goal_tool` -- Motor de interes compuesto para metas de ahorro (anualidad ordinaria, aportes a fin de periodo): future_value (valor futuro de capital...
- `savings_rate_tool` -- Metricas de tasa de ahorro relativa al ingreso (no confundir con savings_goal_tool, que es interes compuesto sobre un monto fijo):...
- `spending_pattern_tool` -- Analisis de patrones de gasto: category_breakdown (gasto total y % del total por categoria dado un listado de transacciones),...
- `tax_estimation_tool` -- Estimacion de impuesto sobre la renta con tramos progresivos provistos por quien llama (generico, sin tabla hardcodeada de ningun pais...

### Biologia computacional y ecologia

- `agricultural_dynamics_tool` -- Dinamica de cultivos y plagas para planificacion agricola comunitaria
- `algae_chemostat_tool` -- Simula un ecosistema cerrado tipo quimiostato alga-microconsumidores con ley del minimo de Liebig (co-limitacion por C/N) y cinetica de...
- `aminoacid_tool` -- Analisis de aminoacidos y peptidos a partir de secuencia de una letra: composicion, peso molecular (promedio y monoisotopico), carga neta...
- `biodiversity_model_tool` -- Calcula indices de diversidad biologica (Shannon-Wiener, Simpson, estimador de riqueza Chao1) a partir de datos de abundancia por...
- `cardiac_regeneration_tool` -- Modelo de EDOs de regeneracion cardiaca post-infarto: 7 compartimentos (Wound, CM_dediff, CM_prolif, CM_regen, Fibroblast, Myofibroblast,...
- `cell_fate_decision_tool` -- Red Booleana de decisiones de destino celular hematopoyetico (8 genes: GATA1, PU1, CEBPA, FOG1, KLF1, GFI1, SCL, IKZF1), reglas...
- `compositional_analysis_tool` -- Análisis composicional: transformaciones log-ratio y mezclas lineales de minerales
- `crisprzip_energy_tool` -- CRISPRzip: modelo de energía libre para eficiencia de corte CRISPR-Cas9
- `cryptogam_biomass_tool` -- Estima biomasa de criptogamas (liquenes y musgos) a partir de correlaciones masa-volumen usando un modelo de regresion lineal bayesiana...
- `droop_kelp_tool` -- Modelo de Droop (cuota interna de nutriente N) con limitacion adicional por luz (funcion de Steele) para crecimiento de macroalgas/kelp
- `ethical_food_advisor_tool` -- Calcula puntajes 0-10 (10=mejor) para huella ambiental, bienestar animal y condiciones laborales de un alimento, mas un puntaje compuesto...
- `food_chemistry_tool` -- Modela las 4 reacciones quimicas clasicas de la coccion: Maillard (pardeamiento no enzimatico), caramelizacion (descomposicion termica de...
- `fungal_morphology_tool` -- Matematica de formas del cuerpo fungico (carpoforo): perfil del pileo (sombrero) como domo generalizado, geometria del estipite...
- `genESOM_simulator` -- Aumento de datos generativo estilo genESOM (generative Emergent Self-Organizing Map) para datasets biologicos pequenos
- `gene_drive_population_tool` -- Modelos MGDrivE: herencia genética y dinámica poblacional con gene drives
- `genetic_circuit_control_tool` -- Diseño y optimización de circuitos genéticos sintéticos con control dinámico
- `hormone_tool` -- Matematicas de hormonas y senalizacion celular: hormonas peptidicas (composicion, MW, pI via aminoacid_tool), hormonas esteroides (masa...
- `ion_chemistry_tool` -- Química de iones en solución: conversión de concentraciones, fuerza iónica, coeficiente de actividad (Davies), cálculo de pH (Henderson-...
- `lichen_growth_tool` -- Simula el crecimiento radial de talos liquenicos circulares segun un modelo de difusion de CO2 (tasa de crecimiento radial...
- `marine_ecosystem_impact_tool` -- Indicadores fisicos de riesgo de marea roja (transporte de Ekman/indice de surgencia de Bakun, frecuencia de Brunt-Vaisala para...
- `moss_lsystem_tool` -- Genera morfologias de musgo (protonema) mediante L-systems, interpreta la cadena resultante como turtle graphics, y calcula metricas de...
- `mycelial_network_tool` -- Modelado micelial: crecimiento logistico, eyeccion balistica de esporas (gota-de-Buller + drag de Stokes), estadistica espacial de...
- `pedotransfer_tool` -- Estima curvas de retencion de agua y conductividad hidraulica desde textura, densidad y materia organica (pedotransfer functions, van...
- `photosynthesis_lichen_tool` -- Calcula la tasa de fotosintesis neta (A) de liquenes y musgos en funcion de la luz (PPFD), la temperatura del talo y el contenido de...
- `poaching_tool` -- Modelo agregado de dinamica poblacional bajo presion de caza furtiva: crecimiento logistico menos extraccion por caza, moderada por...
- `rpa_kinetics_tool` -- Simula cinética enzimática de RPA (Recombinasa Polimerasa Amplificación)
- `soil_mechanics_tool` -- Criterios de falla (Mohr-Coulomb, Drucker-Prager) y consolidacion (Cam-Clay modificado) para mecanica de suelos.
- `soil_mixture_tool` -- Relaciones volumetricas de 3 fases y propiedades termicas efectivas del suelo, con contabilidad de materia organica (SOM).
- `soil_water_flow_tool` -- Solver 1D de la ecuacion de Richards para infiltracion, evaporacion e imbibicion, con solucion analitica Green-Ampt.
- `stem_cell_lineage_tool` -- Modelo de EDOs (odeint) de dinamica de linaje de celulas madre: compartimentos acoplados con inhibicion de Hill, con modo de simulacion...
- `stem_cell_niche_tool` -- Modelo estocastico (Gillespie SSA) de competencia por nicho de celulas madre
- `toxicity_predictor` -- Predice probabilidad de toxicidad in vitro (12 ensayos del panel Tox21 NIH/EPA/FDA: receptores nucleares y vias de respuesta a estres) a...
- `ultra_processed_metabolism_tool` -- Calcula puntajes 0-10 (10=mejor) relacionados con grado de procesamiento industrial e impacto metabolico esperado de un alimento:...
- `virtual_pharmacokinetics` -- Simulacion PBPK compartimental (flow-limited) de la distribucion de un compuesto en un cuerpo humano de referencia

### Resonancia magnetica / RMN

- `bloch_equation_tool` -- Ecuaciones de Bloch para RM/NMR: precesion libre con relajacion T1/T2 (analitica), simulacion numerica de pulso RF, senal de spin-echo y...
- `gradient_field_tool` -- Matematica de gradientes de campo en RM: seleccion de corte, codificacion de frecuencia y de fase, y trayectoria en k-space.
- `kspace_reconstruction_tool` -- Reconstruccion de imagenes de RM desde k-space: FFT2 inversa, zero-filling, y demostracion de aliasing por submuestreo en fase.
- `relaxometry_tool` -- Estimacion de parametros de relajacion T1/T2 en RM/NMR a partir de datos medidos: ajuste de recuperacion (T1, inversion o saturation...

### Procesamiento de senales

- `filter_design_tool` -- Diseno de filtros digitales: iir_design (Butterworth/Chebyshev I,II/Elliptic, lowpass/highpass/bandpass/bandstop), fir_design (ventaneado...
- `fractional_fourier_tool` -- Transformada Fraccional de Fourier (FRFT) discreta via autodescomposicion exacta (Dickinson-Steiglitz/Pei-Yeh-Tseng): frft (orden a, a=0...
- `spectral_analysis_tool` -- Analisis espectral tipo ABRAVIBE: FFT, estimacion de FRF via H1 (Welch, promediado), y extraccion de parametros modales (frecuencia...
- `time_frequency_tool` -- Analisis tiempo-frecuencia: espectrograma STFT con ventana de Hann y verificacion de la cresta de frecuencia en un chirp lineal...

### Perforacion y pozos petroleros

- `dynamic_kill_calculator_tool` -- Calcula el kill dinamico (densidad de lodo y tasa de bombeo criticas) para detener un influjo de yacimiento no controlado, usando...

### Acustica, ondas y electromagnetismo

- `audio_processing_tool` -- Procesamiento de señales de audio: analisis armonico con medicion de amplitudes/THD via FFT de muestreo coherente (mode='harmonics'),...
- `bem_electromagnetic_tool` -- Electromagnetismo via BEM (metodo de elementos de contorno): resuelve electrostatica 2D (ecuacion de Laplace) sobre uno o mas conductores...
- `bremsstrahlung_radiation_tool` -- Radiación de frenado: espectros de fotones e- → e- + γ, secciones transversales Bethe-Heitler, límite clásico Thomson
- `circuit_tool` -- Analisis nodal modificado (MNA) de circuitos resistivos con fuentes de voltaje y corriente independientes
- `dispersion_relation_tool` -- Relaciones de dispersion de ondas en distintos medios: plasma no magnetizado (EM o Langmuir/Bohm-Gross, mode='plasma'), ondas de...
- `electromagnetic_cascade_tool` -- Cascada electromagnética: pair_production → bremsstrahlung → pair_annihilation → synchrotron
- `fem_electromagnetic_tool` -- Electromagnetismo via FEM: resuelve la ecuacion de Poisson 2D (electrostatica) sobre malla triangular P1 (modo poisson_2d), delegando el...
- `gravitational_waves` -- Ondas gravitacionales de sistemas binarios compactos: masa de chirp, frecuencia GW en el ISCO, amplitud de strain, tiempo hasta la fusion...
- `nonlinear_vibration_tool` -- Vibraciones no lineales: oscilador de Duffing (rigidez cubica) via balance armonico de 1er orden
- `openems_quantum_circuit_tool` -- Simulacion electromagnetica de elementos de circuitos cuanticos (resonadores CPW de lectura)
- `pair_annihilation_tool` -- Aniquilación de pares e+e- → γγ: espectros, secciones transversales
- `pair_production_tool` -- Produccion de pares gamma+gamma -> e+e-: seccion eficaz, energia umbral de reaccion, y self-test.
- `rf_network_advanced_tool` -- Extension de rf_network_analysis: factor de estabilidad K/Delta y test-mu para amplificadores RF (stability_factor), cascada de redes de...
- `rf_network_analysis` -- Extraccion de parametros S, analisis de matching de impedancia y exportacion Touchstone (.s2p) para lineas de transmision RF (ej
- `synchrotron_radiation_tool` -- Radiacion de sincrotron de electrones relativistas: espectro, frecuencia critica, y self-test.
- `tight_binding_graphene_tool` -- Estructura de bandas tight-binding a primeros vecinos para grafeno (red honeycomb, 2 atomos por celda)
- `wave_propagation_tool` -- Propagacion de ondas 2D: FDTD escalar 2D con verificacion de velocidad de frente de onda via tiempo de arribo a dos radios...

### Geometria, mallas y cosmologia

- `algebraic_curve` -- Curvas algebraicas planas F(x,y)=0 (polinomios via sympy): mode='curve' traza la curva resolviendo la polinomial univariada en x para...
- `coordinate_transform` -- Convierte puntos entre sistemas de coordenadas: polar<->cartesiano (2D), cilindricas<->cartesiano (3D) y esfericas<->cartesiano (3D,...
- `curvilinear_coordinates` -- Cantidades diferenciales de sistemas de coordenadas curvilíneas (polares/cilíndricas/esféricas/parabólicas-cilíndricas o sistema custom):...
- `joukowski_schwarz_christoffel` -- Mapeos conformes clasicos
- `julia_mandelbrot` -- Genera conjuntos de Mandelbrot y de Julia via escape-time algorithm para f(z) = z^2 + c sobre el plano complejo.
- `linear_transform_figure` -- Transformaciones lineales aplicadas a una figura geometrica concreta (distinto de linear_algebra_tool, que analiza la matriz en abstracto...
- `morse_theory` -- Teoria de Morse explicita sobre f:R^n->R
- `projective_geometry` -- Geometría proyectiva: coordenadas homogéneas P²/P³, incidencia y colinealidad/concurrencia (Desargues, Pappus), razón cruzada y...
- `scalar_field_cosmology_tool` -- Simulador de campo escalar de quintaesencia phi(t) en FLRW plano (kappa=8*pi*G=1): Klein-Gordon phi_ddot+3H*phi_dot+dV/dphi=0 acoplada a...
- `space_curves` -- Curvas paramétricas r(t) en el espacio: triedro de Frenet-Serret (tangente, normal, binormal), curvatura, torsión, longitud de arco y...
- `surface_geometry` -- Geometría diferencial de superficies: primera y segunda forma fundamental, curvatura Gaussiana/media/principales y geodésicas
- `trilinear_coordinates` -- Coordenadas trilineales de un triángulo: normalización a distancias reales a los lados, conversión hacia/desde baricéntricas y...
- `voronoi_delaunay` -- Diagramas de Voronoi y triangulacion de Delaunay para un conjunto de puntos 2D, via scipy.spatial (Qhull).

### Ingenieria estructural y mecanica

- `fem_advanced_tool` -- FEM avanzado sobre vigas Euler-Bernoulli/Timoshenko
- `finite_element_advanced_tool` -- Análisis térmico FEM: conducción transitoria (1D/2D), transferencia con convección/radiación (3D), cambio de fase (Stefan), acoplamiento...
- `forced_vibration_tool` -- Vibracion forzada de vigas Euler-Bernoulli con amortiguamiento de Rayleigh (C=a0*M+a1*K)
- `gait_analysis_tool` -- Analisis de marcha en plano sagital 2D: angulos articulares de cadera/rodilla/tobillo a partir de trayectorias de marcadores...
- `kinematics_simulator` -- Integra con RK4 la trayectoria de una particula bajo gravedad constante, con arrastre (drag) opcional proporcional a v^2
- `molecular_dynamics_tool` -- Simula N particulas 2D interactuando por un potencial de Lennard-Jones, integradas con velocity Verlet (simplectico)
- `nonlinear_buckling_tool` -- Pandeo no lineal / grandes deformaciones: armadura de dos barras (von Mises truss, snap-through) via elemento barra Lagrangiano Total...
- `plane_stress_tool` -- FEM 2D continuo: elemento triangular CST (Constant Strain Triangle) para estado plano de tensiones
- `socket_topology_tool` -- Optimizacion topologica SIMP (plane stress, elementos Q4, filtro de densidad, OC update) para la pared de un socket protesico en dominio...
- `structural_analysis_advanced_tool` -- Análisis estructural: pandeo de Euler (columnas esbeltas), pandeo no-lineal con bifurcación, fallo de laminados (Tsai-Wu), modos de...
- `structural_beam_tool` -- Analisis de vigas Euler-Bernoulli: simplemente apoyadas y en voladizo (cantilever), con carga puntual o carga distribuida uniforme
- `thermal_advanced_tool` -- Modulos avanzados de calor/termodinamica: pcm_1d (fusion de material de cambio de fase, metodo de entalpia, validado contra solucion de...
- `thermal_conduction_tool` -- Conduccion de calor FEM: steady_1d (barra 1D estacionaria, Dirichlet en ambos extremos, generacion volumetrica uniforme opcional),...
- `thermal_structural_tool` -- Acoplamiento termico-estructural: tensiones inducidas por deltaT
- `topology_optimization_tool` -- Optimizacion topologica de estructuras via metodo SIMP (Solid Isotropic Material with Penalization): encuentra la distribucion de...

### Sistemas dinamicos y caos (extendido)

- `attractor_geometry` -- Geometria diferencial (Frenet-Serret) de una trayectoria 3D: curvatura, torsion, y discriminacion de zonas de movimiento lento vs
- `chaos_diagnosis` -- Diagnostica si una serie temporal 1D (ej
- `correlation_dimension` -- Dimension de correlacion de Grassberger-Procaccia (D2) para una serie temporal 1D observada
- `fractal_dimension` -- Dimension fractal por box-counting
- `lorenz` -- Simula el sistema de Lorenz (atractor caotico clasico, modelo simplificado de conveccion atmosferica)

### Geociencias, topografia y agrimensura (extendido)

- `altitude_pressure_tool` -- Calculos de presion atmosferica por altitud (modelo ISA, valido hasta 20000m) y conversion de coordenadas geodesicas WGS84 <-> ECEF
- `geospatial_risk_analysis_tool` -- Analisis geoespacial de riesgo: indice de riesgo de terreno, matriz de visibilidad, optimizador de rutas de dron, generacion de mapas de...
- `hydrometeo_data` -- Datos publicos de lluvia (historico diario, ERA5 reanalysis via Open-Meteo), caudal de rios (historico via modelo GloFAS, Open-Meteo...
- `hydrothermal_inference_tool` -- Inferencia bayesiana de fluidos hidrotermales con EM y modelos de transporte reactivo
- `terrain_elevation_tool` -- Consulta elevacion real del terreno via OpenTopoData (API publica gratuita, sin API key, dataset default srtm90m ~90m de resolucion)
- `tidal_harmonic_analysis_tool` -- Analisis armonico de mareas por minimos cuadrados (constituyentes M2, S2, N2, K2, K1, O1, P1, Q1) a partir de una serie de nivel del mar,...

### Ciencia de materiales y estado solido

- `crystal_symmetry_tool` -- Clasificación de grupos puntuales, redes de Bravais y operaciones de simetría cristalina
- `crystallography_tool` -- Geometria de red cristalina (volumen de celda, espaciado interplanar d(hkl) via formula general triclinica valida para los 7 sistemas...
- `dft_tool` -- Quimica computacional: energia Hartree-Fock y DFT (funcionales LDA/GGA/hibridos como B3LYP/PBE) para moleculas pequenas, via PySCF en...
- `spectroscopy_tool` -- Espectroscopía: Ley de Beer-Lambert (A=ε·b·c) para cálculo de concentraciones, detección de gases hasta 50 ppm, análisis de precisión,...
- `statmech_tool` -- Mecanica estadistica de equilibrio: funcion de particion canonica y cantidades termodinamicas derivadas (F, U, S, Cv) por diferenciacion...
- `unified_dark_sector_tool` -- Calcula H(z) y Omega_m(z)/Omega_de(z) bajo un formalismo Friedmann+continuidad unificado, para cuatro familias de sector oscuro...
- `vacuum_energy_density_tool` -- Energia de punto cero de un campo cuantico libre sin masa, con cutoff duro en momento: rho_vac(Lambda) = g*hbar*c*Lambda^4/(16*pi^2), g=2...

### Herramientas del catalogo / orquestacion (extendido)

- `compute_math_pipeline` -- Encadena llamadas a otros compute_* tools del servidor: cada paso puede referenciar el resultado de un paso anterior via strings...
- `health_check_tool` -- Corre la suite de autovalidacion de todas las tools de octave-mcp que declaran mode='validate' en su schema (mismo motor que...
- `mission_runner_tool` -- Orquestador narrativo/educativo: encadena plague_sir_tool[fit_beta] con disaster_economics_tool[direct_loss], mapeando...
- `octave_grammar_tool` -- Cierra el ciclo validacion->generacion corregida para codigo Octave: compile_grammar devuelve la gramatica GBNF del subconjunto de Octave...
- `octave_innovation_doc_tool` -- Sistema de 'contrato de innovacion' para documentos Octave (.m): un schema de campos obligatorios (PROBLEMA, SOLUCION_INNOVADORA,...
- `octave_syntax` -- Valida la sintaxis de un fragmento de codigo Octave sin ejecutarlo (envuelve el codigo en una funcion y lo parsea via source(), sin...
- `parallel_task_runner_tool` -- Corre varias invocaciones de otras tools EN PARALELO (ThreadPoolExecutor, default 2 workers) en una sola llamada MCP, en vez de una...
- `plotting_tools` -- Curvas parametricas 2D y visualizacion matematica: curva parametrica generica, familia de cicloides (cicloide / epicicloide /...
- `report_generator_tool` -- Exporta un dict de resultados (pasado directo via 'data' o cargado via 'run_id' desde workspace_tool) a un reporte: to_markdown (.md con...
- `run_octave` -- Ejecuta codigo GNU Octave
- `run_pipeline` -- Orquestador de pipelines con dependencias EXPLICITAS entre tools ya registradas (sin NLP, sin inferencia automatica)
- `semantic_bridge` -- Recomendador de tools para una tarea descrita en lenguaje natural
- `tool_catalog_tool` -- Indice searchable de todas las tools registradas en este servidor, generado en runtime (sin lista mantenida a mano, nunca se desincroniza)
- `workspace_link` -- Crea/resuelve/lista/borra alias legibles para run_ids del workspace (ej: alias 'ultimo_sismo' -> run_id real).
- `workspace_validate` -- Autochequeo de workspace_tool: ejercita save→describe→list→load→delete y el ciclo de workspace_link, incluyendo manejo de run_id inválido...

### Combinatoria y sistemas ternarios

- `landauer_ternary_tool` -- Limite de Landauer generalizado a logica de N valores (bit, trit, o base arbitraria): energia/entropia minima para borrar simbolos con N...
- `ternary_arithmetic_tool` -- Aritmetica ternaria balanceada (trits -1,0,1) generica, mas verificacion cruzada de 4 motores (Python/scipy, Rust, C++, ternario) del...
- `ternary_combinatorics_tool` -- Disenos Ternarios Balanceados (BTD): generate_cyclic construye un diseno por desarrollo ciclico de un bloque base modulo V y lo verifica;...
- `ternary_representation_tool` -- Aritmetica en base 3: ternario balanceado (digitos -1,0,1, algoritmo real de suma con acarreo tipo Setun) y ternario estandar (digitos...

### Datos externos y fuentes

- `arxiv_tool` -- Cliente de la API publica de arXiv (export.arxiv.org, sin API key)
- `data_file_reader_tool` -- Lectura de archivos de datos con formato mixto (texto y numeros): CSV/TSV con cabeceras o columnas de texto, deteccion automatica de...
- `nasa_tool` -- Cliente de APIs publicas de NASA (api.nasa.gov)
- `units_constants_tool` -- Conversion de unidades (longitud, masa, tiempo, energia, presion, fuerza, potencia, volumen, angulo, temperatura) y constantes fisicas...

### Modelado social y educativo

- `decision_support_tool` -- Sistemas de apoyo a decisiones multicriterio para priorizacion de inversiones publicas: ahp (Proceso Analitico Jerarquico de Saaty, pesos...
- `resource_assignment_tool` -- Asignacion optima de recursos a tareas (algoritmo hungaro, scipy.optimize.linear_sum_assignment) y ruteo heuristico tipo TSP (fuerza...
- `social_impact_tool` -- Impacto social de desastres: affected_population (poblacion expuesta * fraccion de exposicion), displaced_population (poblacion afectada...
- `teaching_strategies_simulator` -- Simula un aprendiz (red neuronal de juguete) cuya retencion por concepto esta modulada por una capa de repeticion espaciada (curva de...

### Point cloud y vision 3D

- `point_cloud_filter` -- Filtrado de nubes de puntos: voxel_downsample (reduccion por grid de voxeles, centroide por celda) y statistical_outlier_removal...
- `point_cloud_loader` -- Carga de nubes de puntos desde archivo (XYZ/TXT, PLY ascii, CSV) con autodeteccion de formato por extension, y calculo de estadisticas...
- `point_cloud_registration` -- Registro rigido de nubes de puntos via ICP (Iterative Closest Point), con estimacion de transformacion por SVD (Kabsch) en cada iteracion
- `point_cloud_surface_reconstruction` -- Reconstruccion de superficie desde una nube de puntos: convex_hull (envolvente convexa via scipy, area y volumen exactos) y alpha_shape...

### Machine learning y vectores

- `machine_learning_vector_tool` -- PCA (via SVD, sin dependencias externas) y extraccion de features basicas (normas, media/varianza por componente, angulos entre vectores)...
- `vector_calculus_tool` -- Calculo vectorial sobre campos discretos (gradiente, divergencia, rotacional) via diferencias finitas centradas en mallas regulares 2D o 3D
- `vector_field_visualizer` -- Prepara datos de campos vectoriales 2D discretos para visualizacion
- `vector_optimizer` -- Optimizacion de funciones escalares vectoriales via gradient descent (con momentum opcional) o metodo de Newton, con gradiente/Hessiano...

### Color y percepcion

- `color_math_tool` -- Matematica del color: conversion entre espacios RGB/HSL/XYZ/Lab (matrices sRGB D65 estandar), calculo de ratio de contraste WCAG 2.x,...

### Divulgacion matematica (extendido)

- `periodic_patterns_tool` -- Patrones numéricos de la tabla periódica: períodos, gases nobles, homólogos

### Algebra, calculo y analisis (extendido)

- `number_theory` -- Teoria de numeros con aplicacion criptografica: primality_test (Miller-Rabin, detecta incluso numeros de Carmichael como 561), rsa_toy...

## Estado

Todas las tools de probabilidad avanzada, procesos estocásticos y bayesiano multivariado están wireadas en `server.py`, probadas en vivo, y con `validation_passed: true` en sus auto-chequeos internos.
