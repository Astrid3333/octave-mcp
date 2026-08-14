#!/usr/bin/env python3
import subprocess, json, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tool_registry
import debt_snowball_tool  # auto-registra via tool_registry, no requiere mas ediciones
from lyapunov_tool import compute_lyapunov_exponent, LYAPUNOV_TOOL_SCHEMA
from stiff_ode_tool import integrate_stiff_ode, STIFF_ODE_TOOL_SCHEMA
from bifurcation_tool import compute_bifurcation_diagram, BIFURCATION_TOOL_SCHEMA
from hilbert_tool import compute_hilbert_transform, HILBERT_TOOL_SCHEMA
from auto_differentiation_tool import compute_gradient_hessian, compute_jacobian, GRADIENT_HESSIAN_TOOL_SCHEMA, JACOBIAN_TOOL_SCHEMA
from math_error_analyzer_tool import compute_math_error_analysis, MATH_ERROR_ANALYZER_TOOL_SCHEMA
from math_benchmark_tool import compute_math_benchmark, MATH_BENCHMARK_TOOL_SCHEMA
from math_interpolation_tool import compute_math_interpolation, MATH_INTERPOLATION_TOOL_SCHEMA
from math_pipeline_builder_tool import run_math_pipeline, PIPELINE_BUILDER_TOOL_SCHEMA
from math_interpreter_tool import interpret_math_query, MATH_INTERPRETER_TOOL_SCHEMA
from math_visualization_tool import compute_math_visualization, MATH_VISUALIZATION_TOOL_SCHEMA
from math_explainer_tool import interpret_and_explain, MATH_EXPLAINER_TOOL_SCHEMA
from machine_learning_math_tool import compute_machine_learning_math, MACHINE_LEARNING_TOOL_SCHEMA
from financial_math_tool import compute_financial_math, FINANCIAL_MATH_TOOL_SCHEMA
from quantity_takeoff_tool import compute_quantity_takeoff, QUANTITY_TAKEOFF_TOOL_SCHEMA
from structural_analysis_tool import compute_structural_analysis, STRUCTURAL_ANALYSIS_TOOL_SCHEMA
from earthworks_tool import compute_earthworks, EARTHWORKS_TOOL_SCHEMA
from budgeting_tool import compute_budgeting, BUDGETING_TOOL_SCHEMA
from construction_scheduling_tool import compute_construction_scheduling, CONSTRUCTION_SCHEDULING_TOOL_SCHEMA
from math_humanizer_tool import compute_math_humanizer, MATH_HUMANIZER_TOOL_SCHEMA
from game_theory_tool import compute_game_theory, GAME_THEORY_TOOL_SCHEMA
from tensor_calculus_tool import compute_tensor_calculus, TENSOR_CALCULUS_TOOL_SCHEMA
from population_genetics_tool import compute_population_genetics, POPULATION_GENETICS_TOOL_SCHEMA
from network_science_tool import compute_network_science, NETWORK_SCIENCE_TOOL_SCHEMA
from population_genetics_tool import compute_population_genetics, POPULATION_GENETICS_TOOL_SCHEMA
from wavelet_tool import compute_wavelet, WAVELET_TOOL_SCHEMA
from percolation_theory_tool import compute_percolation_theory, PERCOLATION_THEORY_TOOL_SCHEMA
from reaction_diffusion_tool import compute_reaction_diffusion, REACTION_DIFFUSION_TOOL_SCHEMA
from chemometrics_tool import compute_chemometrics, CHEMOMETRICS_TOOL_SCHEMA
from econometrics_tool import compute_econometrics, ECONOMETRICS_TOOL_SCHEMA
from archaeological_simulation_tool import compute_archaeological_simulation, ARCHAEOLOGICAL_SIMULATION_TOOL_SCHEMA
from statistical_physics_tool import compute_statistical_physics, STATISTICAL_PHYSICS_TOOL_SCHEMA
from cfd_tool import compute_cfd, CFD_TOOL_SCHEMA
from glm_tool import compute_glm, GLM_TOOL_SCHEMA
from clustering_tool import compute_clustering, CLUSTERING_TOOL_SCHEMA
from mcdm_tool import compute_mcdm, MCDM_TOOL_SCHEMA
from octave_syntax_tool import compute_octave_syntax, OCTAVE_SYNTAX_TOOL_SCHEMA
from stochastic_processes_tool import compute_stochastic_processes, STOCHASTIC_PROCESSES_TOOL_SCHEMA
from advanced_probability_tool import compute_advanced_probability, ADVANCED_PROBABILITY_TOOL_SCHEMA
from filter_design_tool import compute_filter_design, FILTER_DESIGN_TOOL_SCHEMA
from fractional_fourier_tool import compute_fractional_fourier, FRACTIONAL_FOURIER_TOOL_SCHEMA
from wave_propagation_tool import compute_wave_propagation, WAVE_PROPAGATION_TOOL_SCHEMA
from dispersion_relation_tool import compute_dispersion_relation, DISPERSION_RELATION_TOOL_SCHEMA
from audio_processing_tool import compute_audio_processing, AUDIO_PROCESSING_TOOL_SCHEMA
from time_frequency_tool import compute_time_frequency, TIME_FREQUENCY_TOOL_SCHEMA
from information_theory_tool import compute_information_theory, INFORMATION_THEORY_TOOL_SCHEMA
from control_theory_tool import compute_control_theory, CONTROL_THEORY_TOOL_SCHEMA
from optimal_control_tool import compute_optimal_control, OPTIMAL_CONTROL_TOOL_SCHEMA
from spatial_statistics_tool import compute_spatial_statistics, SPATIAL_STATISTICS_TOOL_SCHEMA
from text_analysis_math_tool import compute_text_analysis_math, TEXT_ANALYSIS_MATH_TOOL_SCHEMA
from multibody_dynamics_tool import compute_multibody_dynamics, MULTIBODY_DYNAMICS_TOOL_SCHEMA
import particle_simulation_tool  # auto-registra via tool_registry
from finite_element_tool import compute_finite_element, FINITE_ELEMENT_TOOL_SCHEMA
from fem_advanced_tool import compute_fem_advanced, FEM_ADVANCED_TOOL_SCHEMA
from plane_stress_tool import compute_plane_stress, PLANE_STRESS_TOOL_SCHEMA
from thermal_structural_tool import compute_thermal_structural, THERMAL_STRUCTURAL_TOOL_SCHEMA
from thermal_conduction_tool import compute_thermal_conduction, THERMAL_CONDUCTION_TOOL_SCHEMA
from thermal_advanced_tool import compute_thermal_advanced, THERMAL_ADVANCED_TOOL_SCHEMA
from nonlinear_buckling_tool import compute_nonlinear_buckling, NONLINEAR_BUCKLING_TOOL_SCHEMA
from forced_vibration_tool import compute_forced_vibration, FORCED_VIBRATION_TOOL_SCHEMA
from spectral_analysis_tool import compute_spectral_analysis, SPECTRAL_ANALYSIS_TOOL_SCHEMA
from archaeoastronomy_tool import compute_archaeoastronomy, ARCHAEOASTRONOMY_TOOL_SCHEMA
from quantum_information_tool import compute_quantum_information, QUANTUM_INFORMATION_TOOL_SCHEMA
from octave_infra_tool import octave_run, octave_eval_expr, octave_run_script, octave_version
from lyapunov_tool_v2 import compute_lyapunov_exponent as compute_lyapunov_v2
from graph_tool import compute_graph_algorithms
from qm_tool import compute_qm_potential_well
from nuclear_decay_tool import compute_nuclear_decay_chain
from fractal_dimension_tool import compute_fractal_dimension
from ethnomath_tool import compute_ethnomath
from ethnomath2_tool import compute_ethnomath2
from ancient_calculators_tool import compute_ancient_calculator
from ancestral_octave_tool import compute_ancestral_octave
from filosofia_historia_mate_tool import compute_math_philosophy_history
from levant_tool import compute_levant
from originarios_tool import compute_originarios
from cross_validation_tool import compute_cross_validation
from entropy_structure_tool import compute_entropy_structure
from music_math_tool import compute_music_math
from linear_algebra_tool import compute_linear_algebra
from persistent_homology_tool import compute_persistent_homology
from statistics_tool import compute_statistics
from number_theory_tool import compute_number_theory
from symbolic_tool import compute_symbolic
from optimization_tool import compute_optimization
from pde_tool import compute_pde
from braid_group_tool import compute_braid_group
from population_dynamics_tool import compute_population_dynamics
from reaction_diffusion_tool_real import compute_reaction_diffusion as reaction_diffusion_real
from enzyme_kinetics_tool import compute_enzyme_kinetics
from tritbraid_tool import compute_tritbraid
from historian_tool import compute_historian
from antibiotic_diffusion import compute_antibiotic_diffusion
from plague_sir_tool import compute_plague_sir
from settlement_clusters_tool import compute_settlement_clusters
from historical_extractor_tool import compute_historical_extractor
from paleography_tool import compute_paleography
from abstract_algebra_tool import compute_abstract_algebra
from workspace_tool import save_run
from workspace_tool import load_run
from workspace_tool import list_runs
from workspace_tool import describe_run
from workspace_tool import delete_run
from plot_tool import plot_run
from numeral_systems_embedding_tool import compute_numeral_systems_embedding


def run_octave(code):
    result = subprocess.run(
        ["octave", "--no-gui", "--eval", code],
        capture_output=True, text=True, timeout=30
    )
    return result.stdout + result.stderr


from genome_signal_analysis_tool import compute_genome_signal_analysis, GENOME_SIGNAL_ANALYSIS_SCHEMA
from polarization_mapping_tool import compute_polarization_mapping, POLARIZATION_MAPPING_SCHEMA
from acoustics_tool import compute_acoustics_tool, ACOUSTICS_TOOL_SCHEMA
from circuit_tool import compute_circuit_tool, CIRCUIT_TOOL_SCHEMA
from topology_optimization_tool import compute_topology_optimization_tool, TOPOLOGY_OPTIMIZATION_TOOL_SCHEMA
from electromagnetic_tool import (
    ELECTROMAGNETIC_TOOL_SCHEMA,
    handle_electromagnetic_tool,
)
from distmesh_tool import compute_distmesh, DISTMESH_TOOL_SCHEMA
from sdf_tool import compute_sdf_tool, SDF_TOOL_SCHEMA
from lscm_tool import compute_lscm_tool, LSCM_TOOL_SCHEMA
from mesh_pde_tool import compute_mesh_pde_tool, MESH_PDE_TOOL_SCHEMA
from quantum_astro_tool import compute_quantum_astro_tool, QUANTUM_ASTRO_TOOL_SCHEMA
from semiclassical_cosmology_tool import compute_semiclassical_cosmology_tool, SEMICLASSICAL_COSMOLOGY_TOOL_SCHEMA
from cosmological_mcmc_tool import compute_cosmological_mcmc_tool, COSMOLOGICAL_MCMC_TOOL_SCHEMA
from quantum_cosmology_tool import compute_quantum_cosmology_tool, QUANTUM_COSMOLOGY_TOOL_SCHEMA
from geometric_algebra_protein_tool import compute_geometric_algebra_protein, GEOMETRIC_ALGEBRA_PROTEIN_SCHEMA
from optical_sequence_id_tool import compute_optical_sequence_id, OPTICAL_SEQUENCE_ID_SCHEMA
from infrasound_tool import compute_infrasound_tool, INFRASOUND_TOOL_SCHEMA
from bacterial_growth_tool import compute_bacterial_growth_tool, BACTERIAL_GROWTH_TOOL_SCHEMA
from viral_lattice_tool import compute_viral_lattice_tool, VIRAL_LATTICE_TOOL_SCHEMA
from enzyme_stochastic_tool import compute_enzyme_stochastic, ENZYME_STOCHASTIC_SCHEMA
from evo_lgca_tool import compute_evo_lgca_tool, EVO_LGCA_TOOL_SCHEMA
from mesh_spectral_tool import compute_mesh_spectral_tool, MESH_SPECTRAL_TOOL_SCHEMA
from gas_tool import compute_gas, GAS_TOOL_SCHEMA
from knowledge_graph_tool import compute_knowledge_graph, KNOWLEDGE_GRAPH_TOOL_SCHEMA
from biorefinery_tool import compute_biorefinery, BIOREFINERY_TOOL_SCHEMA
from survey_tools import (
    compute_survey_angles, SURVEY_ANGLES_TOOL_SCHEMA,
    compute_survey_distance, SURVEY_DISTANCE_TOOL_SCHEMA,
    compute_survey_curvature, SURVEY_CURVATURE_TOOL_SCHEMA,
    compute_traverse_adjustment, TRAVERSE_ADJUSTMENT_TOOL_SCHEMA,
    compute_survey_curves, SURVEY_CURVES_TOOL_SCHEMA,
    compute_survey_area_volume, SURVEY_AREA_VOLUME_TOOL_SCHEMA,
)
from climate_tool import compute_climate
from advanced_stochastic_tool import compute_advanced_stochastic
from multivariate_bayes_tool import compute_multivariate_bayes
from personal_budget_tool import compute_personal_budget_tool, PERSONAL_BUDGET_TOOL_SCHEMA
from savings_goal_tool import compute_savings_goal_tool, SAVINGS_GOAL_TOOL_SCHEMA
from credit_simulation_tool import compute_credit_simulation_tool, CREDIT_SIMULATION_TOOL_SCHEMA
from refinance_analysis_tool import compute_refinance_analysis_tool, REFINANCE_ANALYSIS_TOOL_SCHEMA
from natural_hazard_risk_tool import compute_natural_hazard_risk
from earthquake_analysis_tool import compute_earthquake_analysis
from wildfire_risk_tool import compute_wildfire_risk
from decision_support_tool import compute_decision_support
from water_resource_tool import compute_water_resource
from flood_modeling_tool import compute_flood_modeling
from early_warning_tool import compute_early_warning
from climate_scenario_tool import compute_climate_scenario
from disaster_simulation_tool import compute_disaster_simulation
from disaster_economics_tool import compute_disaster_economics
from social_impact_tool import compute_social_impact
from insurance_risk_tool import compute_insurance_risk
from critical_infrastructure_tool import compute_critical_infrastructure
from urban_planning_tool import compute_urban_planning
from public_data_ingest_tool import compute_public_data_ingest
from critical_infrastructure_tool import CRITICAL_INFRASTRUCTURE_TOOL_SCHEMA
from urban_planning_tool import URBAN_PLANNING_TOOL_SCHEMA
from public_data_ingest_tool import PUBLIC_DATA_INGEST_TOOL_SCHEMA
TOOLS = [
    {"name": "climate_scenario_tool", "description": "Analisis de escenarios climaticos: trend_analysis (regresion lineal, Mann-Kendall, changepoint CUSUM sobre series temporales), rcp_projection (proyeccion de temperatura/nivel del mar para un RCP y anio dado), list_rcp_scenarios (catalogo RCP2.6/4.5/6.0/8.5 con datos IPCC AR5), validate.", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "params": {"type": "object"}}, "required": ["mode"]}},
    {"name": "disaster_simulation_tool", "description": "Simulacion Monte Carlo de desastres (modelo actuarial frecuencia-severidad Poisson-LogNormal) para gestion publica de riesgos: monte_carlo_losses (distribucion de perdida agregada anual dado lambda de frecuencia y mu/sigma de severidad lognormal, con VaR y CVaR/Tail-VaR a percentiles configurables), return_period_loss (perdida esperada para periodos de retorno dados, estimador empirico de Weibull T=(n+1)/m, consistente con natural_hazard_risk_tool.gumbel_return_period), exceedance_curve (curva de probabilidad de excedencia anual -EP curve- para una lista de umbrales de perdida), multi_hazard_combine (combina dos peligros independientes o correlacionados via copula gaussiana en una perdida agregada conjunta), validate (suite de 10 checks). Motor generico: no trae catalogo de parametros por tipo de peligro (lambda/mu/sigma los provee quien llama), confidence_flag 'alta' para toda la mecanica estadistica.", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "params": {"type": "object"}}, "required": ["mode"]}},
    {"name": "disaster_economics_tool", "description": "Economia de desastres para evaluacion de politica publica: direct_indirect_loss (perdida indirecta via multiplicador economico regional, indirect=direct*(m-1)), business_interruption_loss (perdida acumulada por interrupcion de actividad economica durante una recuperacion exponencial hacia el nivel pre-desastre, integral cerrada), benefit_cost_ratio (BCR de una inversion de mitigacion: VAN de la perdida anual esperada evitada vs costo de inversion, a tasa de descuento y horizonte dados), gdp_impact_icor (impacto en el flujo de producto por destruccion de stock de capital via ratio incremental capital-producto ICOR), validate (suite de 10 checks). Motor generico: no trae catalogo de multiplicadores/ICOR por region o sector (los provee quien llama), confidence_flag 'alta' para toda la mecanica.", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "params": {"type": "object"}}, "required": ["mode"]}},
    {"name": "social_impact_tool", "description": "Impacto social de desastres y de inversion publica: social_vulnerability_index (indice SoVI via suma de z-scores de indicadores socioeconomicos con signo configurable por indicador), displacement_estimate (poblacion desplazada y unidades de vivienda temporal requeridas a partir de dano habitacional por severidad y ocupacion promedio), equity_weighted_impact (pondera perdida/dano economico por un factor de vulnerabilidad social para priorizar inversion), casualty_estimate (estimacion simplificada de victimas a partir de fraccion de estructuras colapsadas, ocupacion y hora del dia, logica HAZUS-MH simplificada), validate (suite de 10 checks). Motor generico: no trae catalogo de indicadores/pesos por region (los provee quien llama), confidence_flag 'alta' para la mecanica.", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "params": {"type": "object"}}, "required": ["mode"]}},
    {"name": "insurance_risk_tool", "description": "Seguros y reaseguro de catastrofes: pure_premium (prima pura mas cargas de gasto y margen de utilidad, sobre una distribucion de perdida Poisson-LogNormal simulada o provista, prima_comercial = prima_pura/(1-expense_ratio-profit_margin)), excess_of_loss_layer (pricing de una capa de reaseguro XoL via Monte Carlo, perdida esperada de capa = E[min(max(L-attachment,0),limit)]), cat_bond_pricing (pricing simplificado de bono catastrofico: cupon = perdida esperada de la capa cubierta/principal + spread de mercado), loss_ratio_analysis (loss ratio, expense ratio y combined ratio de una cartera dado primas y siniestros historicos), validate (suite de 10 checks). Motor generico: no trae catalogo de tasas de mercado ni expense ratios (los provee quien llama), confidence_flag 'alta'.", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "params": {"type": "object"}}, "required": ["mode"]}},
    CRITICAL_INFRASTRUCTURE_TOOL_SCHEMA,
    URBAN_PLANNING_TOOL_SCHEMA,
    PUBLIC_DATA_INGEST_TOOL_SCHEMA,
    {
        "name": "run_octave",
        "description": "Ejecuta codigo GNU Octave",
        "inputSchema": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    },
    LYAPUNOV_TOOL_SCHEMA,
    STIFF_ODE_TOOL_SCHEMA,
    BIFURCATION_TOOL_SCHEMA,
    HILBERT_TOOL_SCHEMA,
    GRADIENT_HESSIAN_TOOL_SCHEMA,
    JACOBIAN_TOOL_SCHEMA,
    MATH_ERROR_ANALYZER_TOOL_SCHEMA,
    MATH_BENCHMARK_TOOL_SCHEMA,
    MATH_INTERPOLATION_TOOL_SCHEMA,
    PIPELINE_BUILDER_TOOL_SCHEMA,
    MATH_INTERPRETER_TOOL_SCHEMA,
    MATH_VISUALIZATION_TOOL_SCHEMA,
    MATH_EXPLAINER_TOOL_SCHEMA,
    MACHINE_LEARNING_TOOL_SCHEMA,
    FINANCIAL_MATH_TOOL_SCHEMA,
    QUANTITY_TAKEOFF_TOOL_SCHEMA,
    STRUCTURAL_ANALYSIS_TOOL_SCHEMA,
    EARTHWORKS_TOOL_SCHEMA,
    BUDGETING_TOOL_SCHEMA,
    CONSTRUCTION_SCHEDULING_TOOL_SCHEMA,
    MATH_HUMANIZER_TOOL_SCHEMA,
    GAME_THEORY_TOOL_SCHEMA,
    TENSOR_CALCULUS_TOOL_SCHEMA,
    POPULATION_GENETICS_TOOL_SCHEMA,
    NETWORK_SCIENCE_TOOL_SCHEMA,
    POPULATION_GENETICS_TOOL_SCHEMA,
    WAVELET_TOOL_SCHEMA,
    PERCOLATION_THEORY_TOOL_SCHEMA,
    REACTION_DIFFUSION_TOOL_SCHEMA,
    CHEMOMETRICS_TOOL_SCHEMA,
    ECONOMETRICS_TOOL_SCHEMA,
    ARCHAEOLOGICAL_SIMULATION_TOOL_SCHEMA,
    STATISTICAL_PHYSICS_TOOL_SCHEMA,
    CFD_TOOL_SCHEMA,
    GLM_TOOL_SCHEMA,
    CLUSTERING_TOOL_SCHEMA,
    MCDM_TOOL_SCHEMA,
    OCTAVE_SYNTAX_TOOL_SCHEMA,
    STOCHASTIC_PROCESSES_TOOL_SCHEMA,
    ADVANCED_PROBABILITY_TOOL_SCHEMA,
    FILTER_DESIGN_TOOL_SCHEMA,
    DISPERSION_RELATION_TOOL_SCHEMA,
    AUDIO_PROCESSING_TOOL_SCHEMA,
    TIME_FREQUENCY_TOOL_SCHEMA,
    INFORMATION_THEORY_TOOL_SCHEMA,
    CONTROL_THEORY_TOOL_SCHEMA,
    OPTIMAL_CONTROL_TOOL_SCHEMA,
    SPATIAL_STATISTICS_TOOL_SCHEMA,
    TEXT_ANALYSIS_MATH_TOOL_SCHEMA,
    MULTIBODY_DYNAMICS_TOOL_SCHEMA,
    FINITE_ELEMENT_TOOL_SCHEMA,
    FEM_ADVANCED_TOOL_SCHEMA,
    PLANE_STRESS_TOOL_SCHEMA,
    THERMAL_STRUCTURAL_TOOL_SCHEMA,
    THERMAL_CONDUCTION_TOOL_SCHEMA,
    THERMAL_ADVANCED_TOOL_SCHEMA,
    NONLINEAR_BUCKLING_TOOL_SCHEMA,
    FORCED_VIBRATION_TOOL_SCHEMA,
    SPECTRAL_ANALYSIS_TOOL_SCHEMA,
    ARCHAEOASTRONOMY_TOOL_SCHEMA,
    QUANTUM_INFORMATION_TOOL_SCHEMA,
    {"name": "octave_run", "description": "Ejecuta codigo Octave. timeout en segundos (default 60).", "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["code"]}},
    {"name": "octave_eval_expr", "description": "Evalua una expresion Octave con disp().", "inputSchema": {"type": "object", "properties": {"expression": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["expression"]}},
    {"name": "octave_run_script", "description": "Ejecuta un script .m existente en disco.", "inputSchema": {"type": "object", "properties": {"script_path": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["script_path"]}},
    {"name": "octave_version", "description": "Devuelve la version de Octave instalada.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "compute_lyapunov_v2", "description": "Calcula el exponente de Lyapunov maximo (lambda1) de un sistema dinamico (presets: chen_lee, burke_shaw, lorenz, rossler, o ecuaciones custom) para cuantificar caos. lambda1>0 confirma comportamiento caotico. Si se indica run_id, guarda la trayectoria completa en el workspace (util para graficar el atractor despues con plot_tool).", "inputSchema": {"type": "object", "properties": {"system": {"type": "string"}, "custom_equations": {"type": "string"}, "custom_params": {"type": "object"}, "y0": {"type": "array"}, "dt": {"type": "number"}, "n_steps": {"type": "integer"}, "d0": {"type": "number"}, "run_id": {"type": "string"}, "save_trajectory_every": {"type": "integer"}}}},
    {"name": "graph_algorithms", "description": "Corre algoritmos clasicos de grafos: Dijkstra, MST (Kruskal), deteccion de ciclos. Presets: small_weighted, disconnected, with_cycle, o custom via 'edges' [[u,v,peso],...]. mode='validate' corre un check rapido contra valores exactos calculados a mano.", "inputSchema": {"type": "object", "properties": {"preset": {"type": "string"}, "edges": {"type": "array"}, "directed": {"type": "boolean"}, "operation": {"type": "string"}, "source": {"type": "string"}, "mode": {"type": "string", "enum": ["validate"]}}}},
    {"name": "qm_potential_well", "description": "Resuelve la ecuacion de Schrodinger 1D independiente del tiempo por diferencias finitas. Presets: infinite_well, finite_well, harmonic_oscillator, o custom via custom_potential (expresion Octave en x).", "inputSchema": {"type": "object", "properties": {"preset": {"type": "string"}, "custom_potential": {"type": "string"}, "well_params": {"type": "object"}, "x_range": {"type": "array"}, "n_points": {"type": "integer"}, "mass": {"type": "number"}, "hbar": {"type": "number"}, "n_states": {"type": "integer"}}}},
    {"name": "nuclear_decay_chain", "description": "Resuelve una cadena de decaimiento nuclear (Bateman) via ode45. Presets: cs137_ba137m, sr90_y90, o custom via 'chain'. stable_last=True no sigue la cadena mas alla del ultimo isotopo pero NUNCA anula su lambda (permite alcanzar equilibrio secular). mode='validate' corre un check rapido: decaimiento simple vs analitico + equilibrio secular.", "inputSchema": {"type": "object", "properties": {"preset": {"type": "string"}, "chain": {"type": "array"}, "t_max": {"type": "number"}, "n_points": {"type": "integer"}, "stable_last": {"type": "boolean"}, "mode": {"type": "string", "enum": ["validate"]}}}},
    {"name": "fractal_dimension", "description": "Dimension fractal por box-counting. Presets: sierpinski_triangle, koch_curve, cantor_set (con dimension analitica de referencia), chen_lee_attractor (integra el sistema caotico en Octave), o custom via 'points'. mode='validate' corre un check rapido contra los 3 presets con dimension analitica conocida.", "inputSchema": {"type": "object", "properties": {"preset": {"type": "string"}, "points": {"type": "array"}, "n_points": {"type": "integer"}, "order": {"type": "integer"}, "n_scales": {"type": "integer"}, "eps_min_frac": {"type": "number"}, "eps_max_frac": {"type": "number"}, "chen_lee_params": {"type": "object"}, "mode": {"type": "string", "enum": ["validate"]}}}},
    {"name": "ethnomath", "description": "Algoritmos matematicos historicos: maya_long_count, chinese_remainder, vedic_multiply, quipu_encode, greek_archimedes_pi, japanese_enri_pi.", "inputSchema": {"type": "object", "properties": {"preset": {"type": "string"}, "params": {"type": "object"}}, "required": ["preset"]}},
    {"name": "ethnomath2", "description": "Segunda tanda de algoritmos matematicos historicos: egyptian_duplation, persian_khwarizmi, persian_alkashi_sin1, russian_peasant, ottoman_taqi_al_din, norse_rune_calendar, southeast_asian_metonic.", "inputSchema": {"type": "object", "properties": {"preset": {"type": "string"}, "params": {"type": "object"}}, "required": ["preset"]}},
    {"name": "ancient_calculator", "description": "Simula calculadoras historicas reales operando sus cuentas/fichas: suanpan, soroban, roman_hand_abacus, yupana_depasquale (hipotesis en disputa academica, ver advertencia en la respuesta).", "inputSchema": {"type": "object", "properties": {"preset": {"type": "string"}, "params": {"type": "object"}}, "required": ["preset"]}},
    {"name": "ancestral_octave", "description": "Corre metodos ancestrales (suanpan_add, chinese_remainder, vedic_multiply, archimedes_pi, quipu_encode) como funciones Octave NATIVAS via ancestral.m, en el mismo motor que octave_run. extra_octave permite componer con otro codigo Octave en la misma sesion. mode='validate' corre checks matematicos contra valores conocidos, sin necesitar preset.", "inputSchema": {"type": "object", "properties": {"preset": {"type": "string"}, "params": {"type": "object"}, "extra_octave": {"type": "string"}, "mode": {"type": "string", "enum": ["validate"]}}, "required": []}},
    {"name": "math_philosophy_history", "description": "Referencia sobre filosofia e historia de la matematica (8 topics).", "inputSchema": {"type": "object", "properties": {"topic": {"type": "string"}, "params": {"type": "object"}}}},
    {"name": "levant", "description": "Matematica cananea y de Juda/Israel: hebrew_molad (conjuncion lunar media, ciclo metonico de 19 anios), hebrew_gematria (valor numerico de palabras hebreas y su inverso), canaanite_phoenician_numeral (sistema aditivo 1/10/20/100).", "inputSchema": {"type": "object", "properties": {"preset": {"type": "string"}, "params": {"type": "object"}}, "required": ["preset"]}},
    {"name": "originarios", "description": "Numeracion de pueblos originarios: mapuche_numeral (rakin, decimal aditivo-multiplicativo) y aymara_numeral (decimal con sufijo -ni, mas nota sobre vestigio quinario).", "inputSchema": {"type": "object", "properties": {"preset": {"type": "string"}, "params": {"type": "object"}}, "required": ["preset"]}},
    {"name": "cross_validation", "description": "Valida un resultado de dimension fractal corriendo el mismo sistema dinamico con dos motores numericos independientes (Octave ode45 y scipy RK45). Devuelve ambas dimensiones, la diferencia relativa, y un flag cross_validated. Sistemas disponibles: chen_lee. mode='validate' corre un check rapido (resolucion reducida) contra el mismo mecanismo.", "inputSchema": {"type": "object", "properties": {"system": {"type": "string"}, "params": {"type": "object"}, "t_max": {"type": "number"}, "n_steps": {"type": "integer"}, "transient_frac": {"type": "number"}, "tolerance": {"type": "number"}, "mode": {"type": "string", "enum": ["validate"]}}}},
    {"name": "entropy_structure", "description": "Calcula entropia de orden 0 y entropia condicional de orden 1 sobre una secuencia de simbolos, para evaluar evidencia de estructura combinatoria (compatible con codificacion tipo-lenguaje) vs. conteo simple/tally marks. Presets sinteticos validados (random_iid, markov_structured) o custom via 'sequence' con datos reales (khipu, yupana, corpus sin descifrar, etc).", "inputSchema": {"type": "object", "properties": {"preset": {"type": "string", "enum": ["random_iid", "markov_structured", "custom", "validate"]}, "sequence": {"type": "array"}, "alphabet_size": {"type": "integer"}, "n_symbols": {"type": "integer"}, "seed": {"type": "integer"}}}},
    {"name": "music_math", "description": "Calculos de matematica musical: pythagorean_comma, temperament_comparison, harmonic_series, ternary_scale (division de la octava en 3^n pasos, conexion con TritOS), spectral_analysis (FFT real via Octave sobre una senal).", "inputSchema": {"type": "object", "properties": {"preset": {"type": "string"}, "f0": {"type": "number"}, "n_harmonics": {"type": "integer"}, "n_power": {"type": "integer"}, "signal": {"type": "array"}, "fs": {"type": "number"}}}},
    {"name": "linear_algebra", "description": "Algebra lineal via Octave: eigen (autovalores/autovectores), svd (descomposicion en valores singulares + verificacion), pca (componentes principales, varianza explicada), matrix_analysis (rango, condicion, determinante, inversa). Prerrequisito de persistent_homology_tool.", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "preset": {"type": "string"}, "matrix": {"type": "array"}, "data": {"type": "array"}}}},
    {"name": "persistent_homology", "description": "Homologia persistente (H0, H1) sobre una nube de puntos via complejo de Vietoris-Rips y reduccion de matriz de borde. Presets sinteticos validados (circle, two_clusters, random_noise) o custom via 'points' para datos reales -- por ejemplo nubes reconstruidas de un embedding de Takens (conexion directa con TritOS). Si se indica run_id, guarda points/h0_diagram/h1_diagram en el workspace para grafic", "inputSchema": {"type": "object", "properties": {"preset": {"type": "string"}, "points": {"type": "array"}, "max_edge_length": {"type": "number"}, "max_dim": {"type": "integer"}, "n_points": {"type": "integer"}, "seed": {"type": "integer"}, "run_id": {"type": "string"}}}},
    {"name": "statistics", "description": "Estadistica e inferencia via Octave: linear_regression (minimos cuadrados), correlation (Pearson r), t_test (una muestra, t-stat + p-value via betainc), bayesian_beta_binomial (actualizacion conjugada Beta-Binomial). Pensado para analisis de riesgo (QGIS).", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "preset": {"type": "string"}, "x": {"type": "array"}, "y": {"type": "array"}, "sample": {"type": "array"}, "mu0": {"type": "number"}, "prior_a": {"type": "number"}, "prior_b": {"type": "number"}, "successes": {"type": "integer"}, "trials": {"type": "integer"}}}},
    {"name": "number_theory", "description": "Teoria de numeros con aplicacion criptografica: primality_test (Miller-Rabin, detecta numeros de Carmichael), rsa_toy (genera par de claves, cifra/descifra, valida contra ejemplo clasico del paper RSA), elliptic_curve_add (suma/duplicacion de puntos, validado contra Hankerson et al). Conecta con chinese_remainder via RSA-CRT.", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "preset": {"type": "string"}, "n": {"type": "integer"}, "p": {"type": "integer"}, "q": {"type": "integer"}, "e": {"type": "integer"}, "message": {"type": "integer"}, "curve_a": {"type": "integer"}, "curve_b": {"type": "integer"}, "curve_p": {"type": "integer"}, "point1": {"type": "array"}, "point2": {"type": "array"}}}},
    {"name": "symbolic", "description": "Algebra simbolica via sympy: simplify, solve (resolver ecuaciones), differentiate (derivada), integrate (indefinida o definida con limites), taylor_series. Puente necesario porque Octave es 100% numerico.", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "preset": {"type": "string"}, "expression": {"type": "string"}, "variable": {"type": "string"}, "lower_limit": {"type": "string"}, "upper_limit": {"type": "string"}, "point": {"type": "string"}, "order": {"type": "integer"}}}},
    {"name": "optimization", "description": "Optimizacion: linear_programming (via glpk nativo de Octave), gradient_descent (gradiente EXACTO simbolico via sympy, no diferencias finitas). Presets validados contra optimos conocidos.", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "preset": {"type": "string"}, "sense": {"type": "string"}, "c": {"type": "array"}, "A_ub": {"type": "array"}, "b_ub": {"type": "array"}, "expression": {"type": "string"}, "start": {"type": "array"}, "learning_rate": {"type": "number"}, "n_iterations": {"type": "integer"}}}},
    {"name": "pde", "description": "Ecuaciones en derivadas parciales via diferencias finitas explicitas en Octave: heat_equation (u_t=alpha*u_xx), wave_equation (u_tt=c^2*u_xx). Validado contra solucion analitica del primer modo normal. Extension de stiff_ode_tool hacia EDPs -- relevante para propagacion termica LIG.", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "preset": {"type": "string"}, "L": {"type": "number"}, "coefficient": {"type": "number"}, "n_points": {"type": "integer"}, "t_final": {"type": "number"}, "initial_profile": {"type": "array"}}}},
    {"name": "braid_group", "description": "Grupos de trenzas y anyones de Fibonacci: verify_braid_relation (unitariedad + relacion de Yang-Baxter), apply_braid_sequence (aplica una secuencia de trenzas a un estado inicial, preserva la norma). Basado en Bonesteel et al 2005. Conexion con computacion cuantica topologica y con persistent_homology_tool / linear_algebra_tool.", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string", "enum": ["verify_braid_relation", "apply_braid_sequence", "validate"]}, "sequence": {"type": "string"}, "initial_state": {"type": "array"}}}},
    {"name": "population_dynamics", "description": "Dinamica de poblaciones: lotka_volterra (depredador-presa), logistic_growth (capacidad de carga). Relevante para cultivo de kelp en infraestructura de longline existente.", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string", "enum": ["lotka_volterra", "logistic_growth", "validate"]}, "a": {"type": "number"}, "b": {"type": "number"}, "c": {"type": "number"}, "d": {"type": "number"}, "x0": {"type": "number"}, "y0": {"type": "number"}, "r": {"type": "number"}, "K": {"type": "number"}, "t_max": {"type": "number"}, "n_points": {"type": "integer"}}}},
    {"name": "reaction_diffusion_real", "description": "Inestabilidad de Turing (reaccion-difusion linealizada): evalua las 4 condiciones analiticas clasicas y compara tasa de crecimiento numerica vs analitica en el numero de onda mas inestable. Mecanismo detras de patrones biologicos (rayas, manchas, morfogenesis).", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "a11": {"type": "number"}, "a12": {"type": "number"}, "a21": {"type": "number"}, "a22": {"type": "number"}, "Du": {"type": "number"}, "Dv": {"type": "number"}}}},
    {"name": "enzyme_kinetics", "description": "Cinetica enzimatica: full_kinetics (E+S<->ES->E+P completo), michaelis_menten (aproximacion QSSA), compare (valida cuando la aproximacion es correcta, E0<<S0).", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string", "enum": ["full_kinetics", "michaelis_menten", "compare", "validate"]}, "k1": {"type": "number"}, "km1": {"type": "number"}, "k2": {"type": "number"}, "E0": {"type": "number"}, "S0": {"type": "number"}, "t_max": {"type": "number"}, "n_points": {"type": "integer"}}}},
    {"name": "tritbraid", "description": "DSL TritBraid: secuencias de trenzas de Fibonacci que colapsan a un trit ternario (-1,0,+1). Tokens del programa: 0=identidad, 1=sigma1 (diagonal, no mezcla canales), 2=sigma2 (mezcla via matriz F), M=medicion (colapso proyectivo, regla de Born). Modes: run_program (ejecuta el programa dado y devuelve traza completa), validate_physics (verifica unitariedad, invariancia bajo identidad/sigma1, y mez", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "program": {"type": "string"}, "seed": {"type": "integer"}, "initial_state": {"type": "array"}}}},
    {"name": "historian", "description": "Orquestador de analisis historico: parsea numeros de texto libre via regex (sin NLP complejo), arma arrays de numpy, y ajusta el motor correspondiente segun analysis_type -- inflation/demographics (regresion log-lineal: tasa anual %, R2), trade_network (centralidad de red: fuerza entrante + autovector, identifica el hub), units_entropy (entropia de Shannon sobre unidades historicas de medida -- in", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "analysis_type": {"type": "string"}, "text_data": {"type": "string"}, "preset": {"type": "string"}}}},
    {"name": "antibiotic_diffusion", "description": "Bioensayo de difusion en disco tipo Kirby-Bauer: difusion radial 2D exacta (Carslaw & Jaeger, disco de concentracion uniforme C0 en agar homogeneo) mas la aproximacion clasica de fuente puntual de Cooper. Liberacion instantanea, sin degradacion ni consumo bacteriano -- estimacion de ordenes de magnitud, no reemplaza ensayo real. Modes: zone_prediction (radio/diametro de halo a un C0 y tiempo de in", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "C0": {"type": "number"}, "a": {"type": "number"}, "D": {"type": "number"}, "MIC": {"type": "number"}, "t": {"type": "number"}}}},
    {"name": "plague_sir", "description": "SIR inverso para brotes historicos de peste: parsea defunciones semanales de texto libre via regex, ajusta beta (tasa de contagio) con curve_fit manteniendo gamma fijo (parametro de literatura, no medido), integra SIR con RK4, y reporta R0=beta/gamma. Proxy cuantitativo cuando no hay fuente epidemiologica directa -- no corrige subregistro, migracion, ni estacionalidad. Modes: fit_beta (requiere te", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "text_data": {"type": "string"}, "preset": {"type": "string"}, "gamma": {"type": "number"}, "poblacion_estimada": {"type": "number"}}}},
    {"name": "settlement_clusters", "description": "Proxy arqueologico de barrios/clusters sociales: clusteriza coordenadas de hallazgos por distancia (union-find a radio fijo) en cada periodo/estrato, y rastrea clusters entre periodos consecutivos por proximidad de centroides -- detecta nacimiento y muerte de asentamientos. No hace inferencia cronologica, el orden de periodos lo define quien llama. Modes: analyze (requiere puntos_por_periodo y per", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "puntos_por_periodo": {"type": "array"}, "periodos": {"type": "array"}, "radio": {"type": "number"}, "radio_match": {"type": "number"}, "run_id": {"type": "string"}}}},
    {"name": "historical_extractor", "description": "Extrae MULTIPLES series (anio, valor) de un mismo texto historico via regex por oracion (no NLP), una serie por objeto/concepto mencionado (ej: trigo, cebada, jornal). Corre tendencia por regresion log-lineal en cada serie (reusa el motor de historian), calcula salario real indexado si se indica objeto_salario, y correlacion de Pearson entre series de precios que se solapan en anios. NO interpreta", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "text_data": {"type": "string"}, "objetos": {"type": "array"}, "objeto_salario": {"type": "string"}}}},
    {"name": "paleography", "description": "Tres motores cuantitativos de paleografia/codicologia sobre rasgos YA EXTRAIDOS (no hace OCR ni lee imagenes): seriation (analisis de correspondencia via SVD sobre matriz documentos x rasgos, ordena por el eje 1 y valida contra anios_conocidos con Spearman si se dan), feature_dating_regression (ajusta anio ~ rasgo sobre documentos ancla de fecha conocida y estima fecha de documentos sin fecha, con error estandar residual), letterform_classification (nearest-centroid sobre rasgos normalizados, clasifica letterforms en clases conocidas y marca casos ambiguos por margen chico). Ninguno da fechas/atribuciones definitivas.", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "matriz": {"type": "array"}, "doc_ids": {"type": "array"}, "anios_conocidos": {"type": "object"}, "anios_ancla": {"type": "array"}, "rasgo_ancla": {"type": "array"}, "rasgo_predecir": {"type": "array"}, "ids_predecir": {"type": "array"}, "grado_polinomio": {"type": "integer"}, "rasgos_entrenamiento": {"type": "array"}, "clases_entrenamiento": {"type": "array"}, "rasgos_nuevos": {"type": "array"}, "ids_nuevos": {"type": "array"}}}},
    {"name": "abstract_algebra", "description": "Algebra abstracta sobre estructuras finitas chicas (orden <=8 para isomorfismo): cayley_table (genera tabla preset Zn_add, Zn_mult, Sn simetrico, Dn diedral), verify_group_axioms (cerradura/asociatividad/identidad/inverso, reporta si es abeliano), verify_ring_field_axioms (axiomas de anillo via grupo abeliano + distributividad, confirma cuerpo si hay inverso multiplicativo para todo no-cero), check_isomorphism (fuerza bruta sobre permutaciones -- respuesta negativa es definitiva para el orden dado, no una sospecha).", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "preset": {"type": "string"}, "n": {"type": "integer"}, "elementos": {"type": "array"}, "tabla": {"type": "array"}, "tabla_suma": {"type": "array"}, "tabla_mult": {"type": "array"}, "elementos_a": {"type": "array"}, "tabla_a": {"type": "array"}, "elementos_b": {"type": "array"}, "tabla_b": {"type": "array"}}}},
    {"name": "ocas_symbolic", "description": "Algebra simbolica y teoria de numeros via oCAS (motor Rust, mas rapido que sympy pero mas nuevo/menos probado, v0.26.0). mode='symbolic': simplify/differentiate/integrate/substitute sobre 'expression' (string, potencia con '^' NO '**', ej 'x^2 + 2*x + 1'). mode='number_theory': operation=isprime|factorint|nextprime|totient|divisor_sigma|mobius|liouville_lambda|jacobi_symbol|discrete_log|crt sobre enteros. mode='diophantine': resuelve a*x+b*y=c. Presets con resultado conocido validado, o preset='custom' con los parametros propios.", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "preset": {"type": "string"}, "sub_mode": {"type": "string"}, "expression": {"type": "string"}, "variable": {"type": "string"}, "sub_value": {"type": "string"}, "operation": {"type": "string"}, "n": {"type": "integer"}, "a": {"type": "integer"}, "b": {"type": "integer"}, "c": {"type": "integer"}, "moduli": {"type": "array"}, "residues": {"type": "array"}}}},
    {"name": "workspace_save", "description": "Guarda arrays/resultados de un analisis bajo un run_id para reutilizarlos despues (ej: en plot_tool) sin recalcular. Si run_id se omite, se autogenera.", "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}, "data": {"type": "object"}, "meta": {"type": "object"}}}},
    {"name": "workspace_load", "description": "Carga un run guardado previamente por run_id. Si keys se omite, devuelve todos los arrays (cuidado con trayectorias muy largas: usar workspace_describe primero).", "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}, "keys": {"type": "array"}}, "required": ["run_id"]}},
    {"name": "workspace_list", "description": "Lista todos los runs guardados en el workspace, opcionalmente filtrados por tool de origen (ej: 'compute_lyapunov_exponent').", "inputSchema": {"type": "object", "properties": {"filter_tool": {"type": "string"}}}},
    {"name": "workspace_describe", "description": "Muestra shapes/dtypes de un run sin cargar los arrays completos a memoria (util para trayectorias largas antes de graficar).", "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"]}},
    {"name": "workspace_delete", "description": "Borra un run del workspace (libera espacio en disco).", "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"]}},
    {"name": "plot_workspace_run", "description": "Genera una visualizacion (PNG en base64 + guardado en disco) a partir de un run guardado en el workspace (ej: la trayectoria de un atractor guardada por compute_lyapunov con run_id). No recalcula nada, solo lee y grafica. plot_type: auto (infiere segun el tool de origen), attractor_3d, attractor_2d, line, scatter, heatmap.", "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}, "plot_type": {"type": "string"}, "title": {"type": "string"}, "array_name": {"type": "string"}}, "required": ["run_id"]}},
    {"name": "numeral_systems_embedding", "description": "Vectoriza sistemas numericos antiguos (base, tipo posicional/aditivo/ fisico, presencia de cero, redundancia representacional, soporte fisico) y proyecta a 2D via UMAP o t-SNE, para explorar agrupamientos estructurales entre culturas. Dataset base: maya_long_count, suanpan, soroban, roman_hand_abacus, yupana_depasquale, quipu, ifa_binary. Extensible via extra_systems (lista de dicts con el mismo s", "inputSchema": {"type": "object", "properties": {"method": {"type": "string"}, "extra_systems": {"type": "array"}, "n_neighbors": {"type": "integer"}, "perplexity": {"type": "number"}, "random_state": {"type": "integer"}, "run_id": {"type": "string"}}}},
    GENOME_SIGNAL_ANALYSIS_SCHEMA,
    POLARIZATION_MAPPING_SCHEMA,
    ELECTROMAGNETIC_TOOL_SCHEMA,
    ACOUSTICS_TOOL_SCHEMA,
    DISTMESH_TOOL_SCHEMA,
    CIRCUIT_TOOL_SCHEMA,
    TOPOLOGY_OPTIMIZATION_TOOL_SCHEMA,
    MESH_PDE_TOOL_SCHEMA,
    QUANTUM_ASTRO_TOOL_SCHEMA,
    SEMICLASSICAL_COSMOLOGY_TOOL_SCHEMA,
    COSMOLOGICAL_MCMC_TOOL_SCHEMA,
    QUANTUM_COSMOLOGY_TOOL_SCHEMA,
    LSCM_TOOL_SCHEMA,
    SDF_TOOL_SCHEMA,
    GEOMETRIC_ALGEBRA_PROTEIN_SCHEMA,
    OPTICAL_SEQUENCE_ID_SCHEMA,
    INFRASOUND_TOOL_SCHEMA,
    BACTERIAL_GROWTH_TOOL_SCHEMA,
    VIRAL_LATTICE_TOOL_SCHEMA,
    ENZYME_STOCHASTIC_SCHEMA,
    EVO_LGCA_TOOL_SCHEMA,
    MESH_SPECTRAL_TOOL_SCHEMA,
    SURVEY_ANGLES_TOOL_SCHEMA,
    SURVEY_DISTANCE_TOOL_SCHEMA,
    SURVEY_CURVATURE_TOOL_SCHEMA,
    TRAVERSE_ADJUSTMENT_TOOL_SCHEMA,
    SURVEY_CURVES_TOOL_SCHEMA,
    SURVEY_AREA_VOLUME_TOOL_SCHEMA,
    GAS_TOOL_SCHEMA,
    KNOWLEDGE_GRAPH_TOOL_SCHEMA,
    PERSONAL_BUDGET_TOOL_SCHEMA,
    SAVINGS_GOAL_TOOL_SCHEMA,
    CREDIT_SIMULATION_TOOL_SCHEMA,
    REFINANCE_ANALYSIS_TOOL_SCHEMA,
    BIOREFINERY_TOOL_SCHEMA,
    {
        "name": "climate_tool",
        "description": (
            "Fisica climatica especifica con validacion analitica. Modos: "
            "energy_balance_ebm (balance de energia 0-D, punto de equilibrio T_eq), "
            "newton_cooling_trend (relajacion exponencial dT/dt=-k(T-Ta), proyeccion de series cortas), "
            "carbon_cycle_box (modelo de cajas atmosfera-oceano-tierra, conservacion de masa), "
            "bifurcation_snowball (histeresis albedo-temperatura tipo Budyko-Sellers, Snowball Earth)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": [
                        "energy_balance_ebm",
                        "newton_cooling_trend",
                        "carbon_cycle_box",
                        "bifurcation_snowball",
                    ],
                },
                "params": {
                    "type": "object",
                    "description": "Parametros especificos del modo (opcional, cada modo trae defaults razonables).",
                },
            },
            "required": ["mode"],
        },
    },


    {
        "name": "advanced_stochastic_tool",
        "description": "Procesos estocasticos avanzados: HMM (forward-backward + Viterbi), filtro de Kalman, particle filter (bootstrap), y GARCH(1,1) por MLE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["hmm", "kalman", "particle_filter", "garch"]},
                "params": {"type": "object"}
            },
            "required": ["mode", "params"]
        }
    },
    {
        "name": "multivariate_bayes_tool",
        "description": "Estadistica bayesiana multivariada: normal/t multivariada, Wishart, modelo jerarquico (Gibbs), regresion via HMC, PCA con biplot y CV, y Factor Analysis via EM.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["mvn_sample", "mvt_sample", "wishart_sample", "hierarchical", "hmc_regression", "pca_biplot", "pca_cv", "factor_analysis"]},
                "params": {"type": "object"}
            },
            "required": ["mode", "params"]
        }
    },
    {"name": "natural_hazard_risk_tool", "description": "Modelado de riesgo multifactorial (R=H*E*V/A) para gestion publica de desastres naturales: risk_index (indice de riesgo puntual con clasificacion en bandas), risk_grid (mapa de calor de riesgo sobre grilla), gumbel_return_period (periodo de retorno empirico T=(n+1)/m), gumbel_fit (ajuste de distribucion de Gumbel por momentos y estimacion de magnitud de diseno o periodo de retorno).", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "params": {"type": "object"}}, "required": ["mode"]}},
    {"name": "earthquake_analysis_tool", "description": "Peligrosidad sismica para gestion publica municipal: deterministic (atenuacion de Esteva PGA=5700*exp(0.8M)/(R+40)^2, amplificacion de sitio tipo NEHRP simplificado por clase de suelo A-E, conversion PGA->MMI de Wald et al.), psha (recurrencia Gutenberg-Richter, curva de peligrosidad tasa de excedencia vs PGA, inversion por biseccion a PGA de diseno para un periodo de retorno dado, ej. 475 anios), validate (suite de 9 checks).", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "params": {"type": "object"}}, "required": ["mode"]}},
    {"name": "wildfire_risk_tool", "description": "Peligrosidad de incendios forestales via modelo de Rothermel (1972) con ponderacion muerto/vivo: rate_of_spread (velocidad de propagacion ft/min, intensidad de linea de fuego e Byram, largo de llama, dado viento/pendiente/humedad y un modelo de combustible), fuel_model_info (parametros crudos de un modelo), list_fuel_models (codigos disponibles por catalogo), validate (suite de 10 checks de consistencia fisica). fuel_catalog: anderson13 (13 modelos, confianza media-alta), scott_burgan40 (40 modelos, confianza BAJA -- valores estimados por patron, no verificados contra la tabla fuente, ver campo data_confidence en cada respuesta), o custom (fuel_model provisto por quien llama, sin datos hardcodeados)." , "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "params": {"type": "object"}}, "required": ["mode"]}},
    {"name": "decision_support_tool", "description": "Sistemas de apoyo a decisiones multicriterio para priorizacion de inversiones publicas: ahp (Proceso Analitico Jerarquico de Saaty, pesos via autovector principal y ratio de consistencia CR), topsis (ordenamiento de alternativas por cercania a la solucion ideal, con criterios de beneficio/costo y pesos configurables).", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "params": {"type": "object"}}, "required": ["mode"]}},
    {"name": "water_resource_tool", "description": "Hidrologia de cuencas para gestion de recursos hidricos: rational_method (caudal pico Qp=CIA/360), scs_curve_number (escorrentia directa por numero de curva SCS), time_of_concentration (formula de Kirpich), water_balance (balance de masa de embalse/cuenca con deteccion de deficit y desborde).", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "params": {"type": "object"}}, "required": ["mode"]}},
    {"name": "flood_modeling_tool", "description": "Modelado de crecidas para planificacion de drenajes: scs_triangular_hydrograph (hidrograma unitario triangular SCS), muskingum_routing (transito de crecidas por un tramo de cauce), manning_normal_depth (tirante normal y ancho de inundacion en seccion trapezoidal via ecuacion de Manning).", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "params": {"type": "object"}}, "required": ["mode"]}},
    {"name": "early_warning_tool", "description": "Analisis de series temporales para alertas tempranas: threshold_crossing (cruce de umbrales tipo semaforo con proyeccion de tiempo hasta el proximo umbral), trend_analysis (regresion lineal, pendiente y R2), rate_of_change_alert (tasa de cambio y deteccion de subidas/bajadas criticas), moving_average_anomaly (deteccion de anomalias contra media movil trailing).", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "params": {"type": "object"}}, "required": ["mode"]}},
] + tool_registry.get_schemas()


if __name__ == "__main__":
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req_id = None
        try:
            req = json.loads(line)
            req_id = req.get("id")
            method = req.get("method", "")
            if req_id is None:
                continue

            if method == "initialize":
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "octave-mcp", "version": "1.2"},
                    },
                }

            elif method == "tools/list":
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

            elif method == "tools/call":
                tool_name = req["params"]["name"]
                args = req["params"].get("arguments", {})

                if tool_name in tool_registry.REGISTRY:
                    result = tool_registry.REGISTRY[tool_name]["handler"](args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "run_octave":
                    output = run_octave(args["code"])
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": output or "(sin salida)"}]},
                    }

                elif tool_name == "compute_lyapunov_exponent":
                    result = compute_lyapunov_exponent(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "integrate_stiff_ode":
                    result = integrate_stiff_ode(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "compute_bifurcation_diagram":
                    result = compute_bifurcation_diagram(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "compute_hilbert_transform":
                    result = compute_hilbert_transform(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "compute_gradient_hessian":
                    result = compute_gradient_hessian(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "compute_jacobian":
                    result = compute_jacobian(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "math_error_analyzer":
                    result = compute_math_error_analysis(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "math_benchmark":
                    result = compute_math_benchmark(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "math_interpolation":
                    result = compute_math_interpolation(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "run_math_pipeline":
                    # run_math_pipeline solo acepta steps/mode (no sigue la
                    # convencion mode+params del resto de las tools) -- se
                    # filtra explicitamente en vez de pasar **args a ciegas,
                    # para no romper si un cliente MCP manda 'params' de mas.
                    result = run_math_pipeline(
                        steps=args.get("steps"),
                        mode=args.get("mode", "validate"),
                    )
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "math_interpreter":
                    result = interpret_math_query(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "math_visualization":
                    result = compute_math_visualization(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "math_explainer":
                    result = interpret_and_explain(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "machine_learning_math":
                    result = compute_machine_learning_math(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "financial_math":
                    result = compute_financial_math(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "quantity_takeoff":
                    result = compute_quantity_takeoff(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "structural_analysis":
                    result = compute_structural_analysis(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "earthworks":
                    result = compute_earthworks(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "budgeting_tool":
                    result = compute_budgeting(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "construction_scheduling_tool":
                    result = compute_construction_scheduling(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "math_humanizer_tool":
                    result = compute_math_humanizer(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "game_theory":
                    result = compute_game_theory(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "tensor_calculus":
                    result = compute_tensor_calculus(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "population_genetics":
                    result = compute_population_genetics(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "network_science":
                    result = compute_network_science(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "population_genetics":
                    result = compute_population_genetics(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "wavelet":
                    result = compute_wavelet(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "percolation_theory":
                    result = compute_percolation_theory(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "reaction_diffusion":
                    result = compute_reaction_diffusion(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "chemometrics_tool":
                    result = compute_chemometrics(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "econometrics_tool":
                    result = compute_econometrics(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "archaeological_simulation":
                    result = compute_archaeological_simulation(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "statistical_physics_tool":
                    # bug conocido: schema declara "params" anidado pero la funcion
                    # usa **params flat -> desempaquetamos aca en vez de tocar el schema
                    _params = args.get("params") or {}
                    result = compute_statistical_physics(mode=args["mode"], **_params)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "cfd_tool":
                    result = compute_cfd(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "glm_tool":
                    result = compute_glm(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "clustering_tool":
                    _params = args.get("params") or {}
                    result = compute_clustering(mode=args["mode"], **_params)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "mcdm":
                    result = compute_mcdm(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "octave_syntax":
                    result = compute_octave_syntax(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "stochastic_processes":
                    result = compute_stochastic_processes(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "advanced_probability_tool":
                    result = compute_advanced_probability(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "filter_design_tool":
                    result = compute_filter_design(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "dispersion_relation_tool":
                    result = compute_dispersion_relation(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "natural_hazard_risk_tool":
                    result = compute_natural_hazard_risk(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "earthquake_analysis_tool":
                    result = compute_earthquake_analysis(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "wildfire_risk_tool":
                    result = compute_wildfire_risk(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "decision_support_tool":
                    result = compute_decision_support(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "water_resource_tool":
                    result = compute_water_resource(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "flood_modeling_tool":
                    result = compute_flood_modeling(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "climate_scenario_tool":
                    result = compute_climate_scenario(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "early_warning_tool":
                    result = compute_early_warning(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "disaster_simulation_tool":
                    result = compute_disaster_simulation(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "disaster_economics_tool":
                    result = compute_disaster_economics(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "social_impact_tool":
                    result = compute_social_impact(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "insurance_risk_tool":
                    result = compute_insurance_risk(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "critical_infrastructure_tool":
                    result = compute_critical_infrastructure(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "urban_planning_tool":
                    result = compute_urban_planning(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "public_data_ingest_tool":
                    result = compute_public_data_ingest(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "audio_processing_tool":
                    result = compute_audio_processing(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "time_frequency_tool":
                    result = compute_time_frequency(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "information_theory":
                    result = compute_information_theory(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "control_theory":
                    result = compute_control_theory(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "optimal_control":
                    result = compute_optimal_control(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "spatial_statistics":
                    result = compute_spatial_statistics(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "text_analysis_math":
                    result = compute_text_analysis_math(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "archaeoastronomy":
                    result = compute_archaeoastronomy(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "quantum_information":
                    result = compute_quantum_information(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "octave_run":
                    output = octave_run(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": output or "(sin salida)"}]},
                    }

                elif tool_name == "octave_eval_expr":
                    output = octave_eval_expr(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": output or "(sin salida)"}]},
                    }

                elif tool_name == "octave_run_script":
                    output = octave_run_script(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": output or "(sin salida)"}]},
                    }

                elif tool_name == "octave_version":
                    output = octave_version(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": output or "(sin salida)"}]},
                    }

                elif tool_name == "compute_lyapunov_v2":
                    result = compute_lyapunov_v2(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "graph_algorithms":
                    result = compute_graph_algorithms(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "qm_potential_well":
                    result = compute_qm_potential_well(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "nuclear_decay_chain":
                    result = compute_nuclear_decay_chain(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "fractal_dimension":
                    result = compute_fractal_dimension(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "ethnomath":
                    result = compute_ethnomath(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "ethnomath2":
                    result = compute_ethnomath2(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "ancient_calculator":
                    result = compute_ancient_calculator(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "ancestral_octave":
                    result = compute_ancestral_octave(**args, run_octave_fn=run_octave)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "math_philosophy_history":
                    result = compute_math_philosophy_history(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "levant":
                    result = compute_levant(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "originarios":
                    result = compute_originarios(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "cross_validation":
                    result = compute_cross_validation(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "entropy_structure":
                    result = compute_entropy_structure(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "music_math":
                    result = compute_music_math(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "linear_algebra":
                    result = compute_linear_algebra(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "persistent_homology":
                    result = compute_persistent_homology(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "statistics":
                    result = compute_statistics(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "number_theory":
                    result = compute_number_theory(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "symbolic":
                    result = compute_symbolic(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "optimization":
                    result = compute_optimization(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "pde":
                    result = compute_pde(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "braid_group":
                    result = compute_braid_group(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "population_dynamics":
                    result = compute_population_dynamics(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "reaction_diffusion_real":
                    result = reaction_diffusion_real(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "enzyme_kinetics":
                    result = compute_enzyme_kinetics(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "tritbraid":
                    result = compute_tritbraid(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "historian":
                    result = compute_historian(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "antibiotic_diffusion":
                    result = compute_antibiotic_diffusion(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "plague_sir":
                    result = compute_plague_sir(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "settlement_clusters":
                    result = compute_settlement_clusters(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "historical_extractor":
                    result = compute_historical_extractor(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "paleography":
                    result = compute_paleography(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "abstract_algebra":
                    result = compute_abstract_algebra(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "ocas_symbolic":
                    result = compute_ocas_symbolic(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "workspace_save":
                    result = save_run(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "workspace_load":
                    result = load_run(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "workspace_list":
                    result = list_runs(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "workspace_describe":
                    result = describe_run(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "workspace_delete":
                    result = delete_run(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "plot_workspace_run":
                    result = plot_run(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "multibody_dynamics_tool":
                    result = compute_multibody_dynamics(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "finite_element_tool":
                    result = compute_finite_element(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "fem_advanced_tool":
                    result = compute_fem_advanced(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "plane_stress_tool":
                    result = compute_plane_stress(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "thermal_structural_tool":
                    result = compute_thermal_structural(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "thermal_conduction_tool":
                    result = compute_thermal_conduction(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "thermal_advanced_tool":
                    result = compute_thermal_advanced(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "nonlinear_buckling_tool":
                    result = compute_nonlinear_buckling(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "forced_vibration_tool":
                    result = compute_forced_vibration(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "spectral_analysis_tool":
                    result = compute_spectral_analysis(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "genome_signal_analysis":
                    result = compute_genome_signal_analysis(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "sdf_tool":
                    result = compute_sdf_tool(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "lscm_tool":
                    result = compute_lscm_tool(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "mesh_pde_tool":
                    result = compute_mesh_pde_tool(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "quantum_astro_tool":
                    result = compute_quantum_astro_tool(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "semiclassical_cosmology_tool":
                    result = compute_semiclassical_cosmology_tool(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "cosmological_mcmc_tool":
                    result = compute_cosmological_mcmc_tool(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "quantum_cosmology_tool":
                    result = compute_quantum_cosmology_tool(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "distmesh_tool":
                    result = compute_distmesh(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "electromagnetic_tool":
                    result = handle_electromagnetic_tool(args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "acoustics_tool":
                    result = compute_acoustics_tool(args.get("mode", "validate"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "polarization_mapping":
                    result = compute_polarization_mapping(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "circuit_tool":
                    result = compute_circuit_tool(args.get("mode", "validate"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "topology_optimization_tool":
                    result = compute_topology_optimization_tool(args.get("mode", "validate"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "geometric_algebra_protein":
                    result = compute_geometric_algebra_protein(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "optical_sequence_id":
                    result = compute_optical_sequence_id(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "infrasound_tool":
                    result = compute_infrasound_tool(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "bacterial_growth_tool":
                    result = compute_bacterial_growth_tool(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "viral_lattice_tool":
                    result = compute_viral_lattice_tool(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "enzyme_stochastic":
                    result = compute_enzyme_stochastic(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "evo_LGCA_tool":
                    result = compute_evo_lgca_tool(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }

                elif tool_name == "mesh_spectral_tool":
                    result = compute_mesh_spectral_tool(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "survey_angles_tool":
                    result = compute_survey_angles(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "survey_distance_tool":
                    result = compute_survey_distance(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "survey_curvature_tool":
                    result = compute_survey_curvature(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "traverse_adjustment_tool":
                    result = compute_traverse_adjustment(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "survey_curves_tool":
                    result = compute_survey_curves(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "survey_area_volume_tool":
                    result = compute_survey_area_volume(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "gas_tool":
                    result = compute_gas(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "knowledge_graph_tool":
                    result = compute_knowledge_graph(args.get("mode"), args.get("params"), tools=TOOLS)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "biorefinery_tool":
                    result = compute_biorefinery(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "climate_tool":
                    result = compute_climate(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "advanced_stochastic_tool":
                    result = compute_advanced_stochastic(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "multivariate_bayes_tool":
                    result = compute_multivariate_bayes(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "personal_budget_tool":
                    result = compute_personal_budget_tool(args.get("mode", "validate"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "savings_goal_tool":
                    result = compute_savings_goal_tool(args.get("mode", "validate"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "credit_simulation_tool":
                    result = compute_credit_simulation_tool(args.get("mode", "validate"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                elif tool_name == "refinance_analysis_tool":
                    result = compute_refinance_analysis_tool(args.get("mode", "validate"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }
                else:
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "error": {"code": -32601, "message": f"Tool desconocido: {tool_name}"},
                    }

            else:
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}

            print(json.dumps(resp), flush=True)

        except Exception as e:
            print(json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(e)}}), flush=True)
