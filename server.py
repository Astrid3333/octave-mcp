#!/usr/bin/env python3
import subprocess, json, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tools'))
import tool_registry
import debt_snowball_tool  # auto-registra via tool_registry, no requiere mas ediciones
import retirement_planner_tool  # auto-registra via tool_registry, no requiere mas ediciones
import life_insurance_math_tool  # auto-registra via tool_registry, no requiere mas ediciones
import education_funding_tool  # auto-registra via tool_registry, no requiere mas ediciones
import emergency_fund_tool  # auto-registra via tool_registry, no requiere mas ediciones
import rpa_kinetics_tool  # auto-registra via tool_registry, no requiere mas ediciones
import surface_geometry_tool  # auto-registra via tool_registry
import gene_drive_population_tool  # auto-registra via tool_registry, no requiere mas ediciones
import crisprzip_energy_tool  # auto-registra via tool_registry, no requiere mas ediciones
import genetic_circuit_control_tool  # auto-registra via tool_registry, no requiere mas ediciones
import stem_cell_lineage_tool
import femur_biomechanics_tool
import drug_delivery_poiseuille_tool
import fatigue_analysis_tool
import domino_effect_tool
import cascade_orchestrator_tool
import cascading_outbreak_predictor
import information_cascade_tool
import bilevel_interdiction_tool  # auto-registra via tool_registry
import cardiac_regeneration_tool  # auto-registra via tool_registry
import stem_cell_niche_tool  # auto-registra via tool_registry
import cell_fate_decision_tool  # auto-registra via tool_registry
import projective_geometry_tool  # auto-registra via tool_registry
import space_curves_tool  # auto-registra via tool_registry
import personal_budget_tool  # auto-registra via tool_registry, no requiere mas ediciones
import statmech_partition_tool  # auto-registra via tool_registry, no requiere mas ediciones
import fem_electromagnetic_tool  # auto-registra via tool_registry, no requiere mas ediciones
import cfd_tool  # auto-registra via tool_registry, no requiere mas ediciones
import bem_electromagnetic_tool  # auto-registra via tool_registry, no requiere mas ediciones
import statmech_tool  # auto-registra via tool_registry, no requiere mas ediciones
import molecular_dynamics_tool  # auto-registra via tool_registry, no requiere mas ediciones
import dft_tool  # auto-registra via tool_registry, no requiere mas ediciones
import savings_goal_tool  # auto-registra via tool_registry, no requiere mas ediciones
import investment_portfolio_tool  # auto-registra via tool_registry, no requiere mas ediciones
import tax_estimation_tool  # auto-registra via tool_registry, no requiere mas ediciones
import infrastructure_resilience_tool  # auto-registra via tool_registry, no requiere mas ediciones
import insurance_risk_tool  # auto-registra via tool_registry, no requiere mas ediciones
import spending_pattern_tool  # auto-registra via tool_registry, no requiere mas ediciones
import savings_rate_tool  # auto-registra via tool_registry, no requiere mas ediciones
import habit_streak_tool  # auto-registra via tool_registry, no requiere mas ediciones
import financial_literacy_score_tool  # auto-registra via tool_registry, no requiere mas ediciones
import earthquake_analysis_tool  # auto-registra via tool_registry, no requiere mas ediciones
import wildfire_risk_tool  # auto-registra via tool_registry, no requiere mas ediciones
import spectroscopy_tool  # auto-registra via tool_registry
import wildfire_intensity_model_tool  # auto-registra via tool_registry
import geospatial_risk_analysis_tool  # auto-registra via tool_registry
import tidal_harmonic_analysis_tool  # auto-registra via tool_registry
import marine_ecosystem_impact_tool  # auto-registra via tool_registry
import landslide_risk_tool  # auto-registra via tool_registry, no requiere mas ediciones
import disaster_economics_tool  # auto-registra via tool_registry, no requiere mas ediciones
import social_impact_tool  # auto-registra via tool_registry, no requiere mas ediciones
import math_pipeline_tool  # auto-registra via tool_registry, no requiere mas ediciones
import ocas_symbolic_tool  # auto-registra via tool_registry, no requiere mas ediciones
import pipeline_orchestrator_tool  # auto-registra via tool_registry, no requiere mas ediciones
import ternary_arithmetic_tool  # auto-registra via tool_registry, no requiere mas ediciones
import mission_runner_tool  # auto-registra via tool_registry, no requiere mas ediciones
import disaster_early_warning_tool  # auto-registra via tool_registry, no requiere mas ediciones
import terrain_elevation_tool  # auto-registra via tool_registry, no requiere mas ediciones
import hydrometeo_data_tool  # auto-registra via tool_registry, no requiere mas ediciones
import flood_risk_narrator_tool  # auto-registra via tool_registry, no requiere mas ediciones
import carbon_footprint_tool  # auto-registra via tool_registry, no requiere mas ediciones
import flood_connectivity_tool  # auto-registra via tool_registry, no requiere mas ediciones
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
import rf_network_advanced_tool  # auto-registra via tool_registry
import nonlinear_vibration_tool  # auto-registra via tool_registry
import structural_analysis_advanced_tool  # auto-registra via tool_registry
import finite_element_advanced_tool  # auto-registra via tool_registry
import statistical_physics_tool_extended  # auto-registra via tool_registry
from earthworks_tool import compute_earthworks, EARTHWORKS_TOOL_SCHEMA
from budgeting_tool import compute_budgeting, BUDGETING_TOOL_SCHEMA
from construction_scheduling_tool import compute_construction_scheduling, CONSTRUCTION_SCHEDULING_TOOL_SCHEMA
from math_humanizer_tool import compute_math_humanizer, MATH_HUMANIZER_TOOL_SCHEMA
from game_theory_tool import compute_game_theory, GAME_THEORY_TOOL_SCHEMA
import tensor_calculus_tool  # auto-registra via tool_registry, no requiere mas ediciones
import julia_mandelbrot_tool  # auto-registra via tool_registry, no requiere mas ediciones
import voronoi_delaunay_tool  # auto-registra via tool_registry, no requiere mas ediciones
import algebraic_curve_tool  # auto-registra via tool_registry, no requiere mas ediciones
import joukowski_schwarz_christoffel_tool  # auto-registra via tool_registry, no requiere mas ediciones
import morse_theory_tool  # auto-registra via tool_registry, no requiere mas ediciones
import linear_transform_figure_tool  # auto-registra via tool_registry, no requiere mas ediciones
from population_genetics_tool import compute_population_genetics, POPULATION_GENETICS_TOOL_SCHEMA
from network_science_tool import compute_network_science, NETWORK_SCIENCE_TOOL_SCHEMA
from wavelet_tool import compute_wavelet, WAVELET_TOOL_SCHEMA
from percolation_theory_tool import compute_percolation_theory, PERCOLATION_THEORY_TOOL_SCHEMA
from reaction_diffusion_tool import compute_reaction_diffusion, REACTION_DIFFUSION_TOOL_SCHEMA
from physics_based_fire_model_tool import physics_based_fire_model
from chemometrics_tool import compute_chemometrics, CHEMOMETRICS_TOOL_SCHEMA
from econometrics_tool import compute_econometrics, ECONOMETRICS_TOOL_SCHEMA
from archaeological_simulation_tool import compute_archaeological_simulation, ARCHAEOLOGICAL_SIMULATION_TOOL_SCHEMA
from cfd_tool import compute_cfd, CFD_TOOL_SCHEMA
from glm_tool import compute_glm, GLM_TOOL_SCHEMA
from clustering_tool import compute_clustering, CLUSTERING_TOOL_SCHEMA
from mcdm_tool import compute_mcdm, MCDM_TOOL_SCHEMA
from octave_syntax_tool import compute_octave_syntax, OCTAVE_SYNTAX_TOOL_SCHEMA
from stochastic_processes_tool import compute_stochastic_processes, STOCHASTIC_PROCESSES_TOOL_SCHEMA
from advanced_probability_tool import compute_advanced_probability, ADVANCED_PROBABILITY_TOOL_SCHEMA
import filter_design_tool  # auto-registra via tool_registry, no requiere mas ediciones
from fractional_fourier_tool import compute_fractional_fourier, FRACTIONAL_FOURIER_TOOL_SCHEMA
import wave_propagation_tool  # auto-registra via tool_registry, no requiere mas ediciones
import dispersion_relation_tool  # auto-registra via tool_registry, no requiere mas ediciones
import audio_processing_tool  # auto-registra via tool_registry, no requiere mas ediciones
import time_frequency_tool  # auto-registra via tool_registry, no requiere mas ediciones
from information_theory_tool import compute_information_theory, INFORMATION_THEORY_TOOL_SCHEMA
import control_theory_tool  # auto-registra via tool_registry, no requiere mas ediciones
from optimal_control_tool import compute_optimal_control, OPTIMAL_CONTROL_TOOL_SCHEMA
from spatial_statistics_tool import compute_spatial_statistics, SPATIAL_STATISTICS_TOOL_SCHEMA
from text_analysis_math_tool import compute_text_analysis_math, TEXT_ANALYSIS_MATH_TOOL_SCHEMA
from multibody_dynamics_tool import compute_multibody_dynamics, MULTIBODY_DYNAMICS_TOOL_SCHEMA
import particle_simulation_tool  # auto-registra via tool_registry
import health_check_tool  # auto-registra via tool_registry, no requiere mas ediciones
from finite_element_tool import compute_finite_element, FINITE_ELEMENT_TOOL_SCHEMA
from fem_advanced_tool import compute_fem_advanced, FEM_ADVANCED_TOOL_SCHEMA
from plane_stress_tool import compute_plane_stress, PLANE_STRESS_TOOL_SCHEMA
from thermal_structural_tool import compute_thermal_structural, THERMAL_STRUCTURAL_TOOL_SCHEMA
from thermal_conduction_tool import compute_thermal_conduction, THERMAL_CONDUCTION_TOOL_SCHEMA
from thermal_advanced_tool import compute_thermal_advanced, THERMAL_ADVANCED_TOOL_SCHEMA
from nonlinear_buckling_tool import compute_nonlinear_buckling, NONLINEAR_BUCKLING_TOOL_SCHEMA
from forced_vibration_tool import compute_forced_vibration, FORCED_VIBRATION_TOOL_SCHEMA
import spectral_analysis_tool  # auto-registra via tool_registry, no requiere mas ediciones
import gait_analysis_tool  # auto-registra via tool_registry, no requiere mas ediciones
import socket_topology_tool  # auto-registra via tool_registry, no requiere mas ediciones
import tight_binding_graphene_tool  # auto-registra via tool_registry, no requiere mas ediciones
import droop_kelp_tool  # auto-registra via tool_registry, no requiere mas ediciones
import octave_grammar_tool  # auto-registra via tool_registry, no requiere mas ediciones
import octave_innovation_doc_tool  # auto-registra via tool_registry, no requiere mas ediciones
import heating_value_tool  # auto-registra via tool_registry, no requiere mas ediciones
import units_constants_tool  # auto-registra via tool_registry, no requiere mas ediciones
import report_generator_tool  # auto-registra via tool_registry, no requiere mas ediciones
import arxiv_tool  # auto-registra via tool_registry, no requiere mas ediciones
import nasa_tool  # auto-registra via tool_registry, no requiere mas ediciones
import parallel_task_runner_tool  # auto-registra via tool_registry, no requiere mas ediciones
import solar_radiation_tool  # auto-registra via tool_registry, no requiere mas ediciones
import wind_power_curve_tool  # auto-registra via tool_registry, no requiere mas ediciones
import battery_sizing_tool  # auto-registra via tool_registry, no requiere mas ediciones
import solar_heating_sizer_tool  # auto-registra via tool_registry, no requiere mas ediciones
import forest_fire_simulator_tool  # auto-registra via tool_registry, no requiere mas ediciones
import chaos_diagnosis_tool  # auto-registra via tool_registry, no requiere mas ediciones
import correlation_dimension_tool  # auto-registra via tool_registry, no requiere mas ediciones
import lorenz_tool  # auto-registra via tool_registry, no requiere mas ediciones
import attractor_geometry_tool  # auto-registra via tool_registry, no requiere mas ediciones
import renewable_mpc_controller  # auto-registra via tool_registry, no requiere mas ediciones
import circular_economy_tool  # auto-registra via tool_registry, no requiere mas ediciones
import biodiversity_model_tool  # auto-registra via tool_registry, no requiere mas ediciones
import deforestation_tool  # auto-registra via tool_registry, no requiere mas ediciones
import poaching_tool  # auto-registra via tool_registry, no requiere mas ediciones
import crystallography_tool  # auto-registra via tool_registry, no requiere mas ediciones
import altitude_pressure_tool  # auto-registra via tool_registry, no requiere mas ediciones
import dynamic_kill_calculator_tool  # auto-registra via tool_registry, no requiere mas ediciones
import tool_catalog_tool  # auto-registra via tool_registry, no requiere mas ediciones
import scalar_field_cosmology_tool  # auto-registra via tool_registry, no requiere mas ediciones
import vacuum_energy_density_tool  # auto-registra via tool_registry, no requiere mas ediciones
import unified_dark_sector_tool  # auto-registra via tool_registry, no requiere mas ediciones
import gravitational_waves_tool  # auto-registra via tool_registry
import toxicity_predictor  # auto-registra via tool_registry
import virtual_pharmacokinetics  # auto-registra via tool_registry
import genESOM_simulator  # auto-registra via tool_registry
import vector_calculus_tool  # auto-registra via tool_registry
import kinematics_simulator  # auto-registra via tool_registry
import point_cloud_loader
import point_cloud_filter
import point_cloud_registration
import point_cloud_surface_reconstruction
import vector_field_visualizer  # auto-registra via tool_registry
import vector_optimizer  # auto-registra via tool_registry
import machine_learning_vector_tool  # auto-registra via tool_registry
import color_math_tool  # auto-registra via tool_registry
import land_use_change_tool  # auto-registra via tool_registry
import soil_erosion_tool  # auto-registra via tool_registry
import teaching_strategies_simulator_tool  # auto-registra via tool_registry
import mycelial_network_tool  # auto-registra via tool_registry
import fungal_morphology_tool  # auto-registra via tool_registry
import plotting_tools  # auto-registra via tool_registry
import data_file_reader_tool  # auto-registra via tool_registry
import coordinate_transform_tool  # auto-registra via tool_registry
import curvilinear_coordinates_tool  # auto-registra via tool_registry
import trilinear_coordinates_tool  # auto-registra via tool_registry
import ternary_combinatorics_tool  # auto-registra via tool_registry, no requiere mas ediciones
import landauer_ternary_tool  # auto-registra via tool_registry, no requiere mas ediciones
import synchrotron_radiation_tool  # auto-registra via tool_registry
import pair_production_tool  # auto-registra via tool_registry
import pair_annihilation_tool  # auto-registra via tool_registry
import bremsstrahlung_radiation_tool
import electromagnetic_cascade_tool  # auto-registra via tool_registry
from archaeoastronomy_tool import compute_archaeoastronomy, ARCHAEOASTRONOMY_TOOL_SCHEMA
from quantum_information_tool import compute_quantum_information, QUANTUM_INFORMATION_TOOL_SCHEMA
from octave_infra_tool import octave_run, octave_eval_expr, octave_run_script, octave_version
from lyapunov_tool_v2 import compute_lyapunov_exponent as compute_lyapunov_v2
from graph_tool import compute_graph_algorithms, GRAPH_ALGORITHMS_SCHEMA
from qm_tool import compute_qm_potential_well, QM_POTENTIAL_WELL_SCHEMA
from nuclear_decay_tool import compute_nuclear_decay_chain, NUCLEAR_DECAY_CHAIN_SCHEMA
from fractal_dimension_tool import compute_fractal_dimension, FRACTAL_DIMENSION_SCHEMA
from ethnomath_tool import compute_ethnomath, ETHNOMATH_SCHEMA
from ethnomath2_tool import compute_ethnomath2, ETHNOMATH2_SCHEMA
from ancient_calculators_tool import compute_ancient_calculator, ANCIENT_CALCULATOR_SCHEMA
from ancestral_octave_tool import compute_ancestral_octave
from filosofia_historia_mate_tool import compute_math_philosophy_history, MATH_PHILOSOPHY_HISTORY_SCHEMA
from levant_tool import compute_levant, LEVANT_SCHEMA
from originarios_tool import compute_originarios, ORIGINARIOS_SCHEMA
from cross_validation_tool import compute_cross_validation, CROSS_VALIDATION_SCHEMA
from entropy_structure_tool import compute_entropy_structure, ENTROPY_STRUCTURE_SCHEMA
from music_math_tool import compute_music_math, MUSIC_MATH_SCHEMA
from linear_algebra_tool import compute_linear_algebra, LINEAR_ALGEBRA_SCHEMA
from persistent_homology_tool import compute_persistent_homology, PERSISTENT_HOMOLOGY_SCHEMA
from statistics_tool import compute_statistics, STATISTICS_SCHEMA
from number_theory_tool import compute_number_theory, NUMBER_THEORY_SCHEMA
from symbolic_tool import compute_symbolic, SYMBOLIC_SCHEMA
from optimization_tool import compute_optimization, OPTIMIZATION_SCHEMA
from pde_tool import compute_pde, PDE_SCHEMA
from braid_group_tool import compute_braid_group, BRAID_GROUP_SCHEMA
from population_dynamics_tool import compute_population_dynamics, POPULATION_DYNAMICS_SCHEMA
from reaction_diffusion_tool_real import compute_reaction_diffusion as reaction_diffusion_real
from enzyme_kinetics_tool import compute_enzyme_kinetics, ENZYME_KINETICS_SCHEMA
from tritbraid_tool import compute_tritbraid
from historian_tool import compute_historian, HISTORIAN_SCHEMA
from antibiotic_diffusion import compute_antibiotic_diffusion, ANTIBIOTIC_DIFFUSION_SCHEMA
from plague_sir_tool import compute_plague_sir, PLAGUE_SIR_SCHEMA
from settlement_clusters_tool import compute_settlement_clusters, SETTLEMENT_CLUSTERS_SCHEMA
from historical_extractor_tool import compute_historical_extractor, HISTORICAL_EXTRACTOR_SCHEMA
from paleography_tool import compute_paleography, PALEOGRAPHY_SCHEMA
from abstract_algebra_tool import compute_abstract_algebra, ABSTRACT_ALGEBRA_SCHEMA
from workspace_tool import save_run, WORKSPACE_SAVE_SCHEMA, WORKSPACE_LOAD_SCHEMA, WORKSPACE_LIST_SCHEMA, WORKSPACE_DESCRIBE_SCHEMA, WORKSPACE_DELETE_SCHEMA, WORKSPACE_LINK_SCHEMA
from workspace_tool import load_run
from workspace_tool import list_runs
from workspace_tool import describe_run
from workspace_tool import delete_run
from workspace_tool import load_run_safe
from workspace_tool import workspace_link
from plot_tool import plot_run, PLOT_WORKSPACE_RUN_SCHEMA
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
from semantic_bridge_tool import compute_semantic_bridge, SEMANTIC_BRIDGE_TOOL_SCHEMA
from biorefinery_tool import compute_biorefinery, BIOREFINERY_TOOL_SCHEMA
from survey_tools import (
    compute_survey_angles, SURVEY_ANGLES_TOOL_SCHEMA,
    compute_survey_distance, SURVEY_DISTANCE_TOOL_SCHEMA,
    compute_survey_curvature, SURVEY_CURVATURE_TOOL_SCHEMA,
    compute_traverse_adjustment, TRAVERSE_ADJUSTMENT_TOOL_SCHEMA,
    compute_survey_curves, SURVEY_CURVES_TOOL_SCHEMA,
    compute_survey_area_volume, SURVEY_AREA_VOLUME_TOOL_SCHEMA,
)
from climate_tool import compute_climate, CLIMATE_TOOL_SCHEMA
from advanced_stochastic_tool import compute_advanced_stochastic, ADVANCED_STOCHASTIC_TOOL_SCHEMA
from multivariate_bayes_tool import compute_multivariate_bayes, MULTIVARIATE_BAYES_TOOL_SCHEMA
from credit_simulation_tool import compute_credit_simulation_tool, CREDIT_SIMULATION_TOOL_SCHEMA
from refinance_analysis_tool import compute_refinance_analysis_tool, REFINANCE_ANALYSIS_TOOL_SCHEMA
from natural_hazard_risk_tool import compute_natural_hazard_risk, NATURAL_HAZARD_RISK_TOOL_SCHEMA
from decision_support_tool import compute_decision_support, DECISION_SUPPORT_TOOL_SCHEMA
from water_resource_tool import compute_water_resource, WATER_RESOURCE_TOOL_SCHEMA
from flood_modeling_tool import compute_flood_modeling, FLOOD_MODELING_TOOL_SCHEMA
from early_warning_tool import compute_early_warning, EARLY_WARNING_TOOL_SCHEMA
from climate_scenario_tool import compute_climate_scenario, CLIMATE_SCENARIO_TOOL_SCHEMA
from disaster_simulation_tool import compute_disaster_simulation, DISASTER_SIMULATION_TOOL_SCHEMA
from critical_infrastructure_tool import compute_critical_infrastructure
from urban_planning_tool import compute_urban_planning
from public_data_ingest_tool import compute_public_data_ingest
from critical_infrastructure_tool import CRITICAL_INFRASTRUCTURE_TOOL_SCHEMA
from urban_planning_tool import URBAN_PLANNING_TOOL_SCHEMA
from agricultural_dynamics_tool import agricultural_dynamics_tool
import photosynthesis_lichen_tool
import cryptogam_biomass_tool
import lichen_growth_tool
import algae_chemostat_tool
import moss_lsystem_tool
import periodic_patterns_tool
import crystal_symmetry_tool
import compositional_analysis_tool
import hydrothermal_inference_tool
import pedotransfer_tool
import soil_mechanics_tool
import soil_mixture_tool
import soil_water_flow_tool
import pedotransfer_tool
import soil_mechanics_tool
import soil_mixture_tool
import soil_water_flow_tool
import food_chemistry_tool
import ethical_food_advisor_tool
import sustainable_sourcing_tool
import angle_math_tool
import bloch_equation_tool  # auto-registra via tool_registry
import relaxometry_tool  # auto-registra via tool_registry
import kspace_reconstruction_tool  # auto-registra via tool_registry
import gradient_field_tool  # auto-registra via tool_registry
import ternary_representation_tool  # auto-registra via tool_registry, no requiere mas ediciones
import aminoacid_tool  # auto-registra via tool_registry, no requiere mas ediciones
import hormone_tool  # auto-registra via tool_registry, no requiere mas ediciones
import octave_codegen_tool  # auto-registra via tool_registry, no requiere mas ediciones
import ultra_processed_metabolism_tool as _wire_agricultural_dynamics_tool
from renewable_potential_tool import renewable_potential_tool as _wire_renewable_potential_tool
from structural_beam_tool import compute_structural_beam_tool as _wire_structural_beam_tool
from public_data_ingest_tool import PUBLIC_DATA_INGEST_TOOL_SCHEMA
from ion_chemistry_tool import _dispatch as ion_chemistry_dispatch
from domino_effect_tool import run as domino_run
from cascade_orchestrator_tool import run as orchestrator_run
from information_cascade_tool import run as info_run
from bilevel_interdiction_tool import run as bilevel_run
from cascading_outbreak_predictor import run as outbreak_run
import openems_quantum_circuit_tool  # auto-registra via tool_registry
import rf_network_analysis  # auto-registra via tool_registry
import resource_assignment_tool  # auto-registra via tool_registry
import fault_dislocation_tool  # noqa: F401  -- autoregistra via tool_registry
import sandpile_avalanche_tool  # auto-registra via tool_registry
import cascading_failure_tool  # auto-registra via tool_registry
import systemic_risk_tool  # auto-registra via tool_registry
import bloch_equation_tool  # auto-registra via tool_registry
import cell_fate_decision_tool  # auto-registra via tool_registry
import gradient_field_tool  # auto-registra via tool_registry
import kspace_reconstruction_tool  # auto-registra via tool_registry
import marine_ecosystem_impact_tool  # auto-registra via tool_registry
import relaxometry_tool  # auto-registra via tool_registry
import stem_cell_niche_tool  # auto-registra via tool_registry
import tidal_harmonic_analysis_tool  # auto-registra via tool_registry
import genetic_ternary_encoder_tool  # auto-registra via tool_registry, no requiere mas ediciones
TOOLS = [
    {
            "name": "run_octave",
            "description": "Ejecuta codigo GNU Octave",
            "inputSchema": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
            },
        },
    PIPELINE_BUILDER_TOOL_SCHEMA,
    {"name": "octave_run", "description": "Ejecuta codigo Octave. timeout en segundos (default 60).", "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}, "timeout": {"type": "integer"}, "mode": {"type": "string", "enum": ["validate"]}}, "required": ["code"]}},
    {"name": "octave_eval_expr", "description": "Evalua una expresion Octave con disp().", "inputSchema": {"type": "object", "properties": {"expression": {"type": "string"}, "timeout": {"type": "integer"}, "mode": {"type": "string", "enum": ["validate"]}}, "required": ["expression"]}},
    {"name": "octave_run_script", "description": "Ejecuta un script .m existente en disco.", "inputSchema": {"type": "object", "properties": {"script_path": {"type": "string"}, "timeout": {"type": "integer"}, "mode": {"type": "string", "enum": ["validate"]}}, "required": ["script_path"]}},
    {"name": "octave_version", "description": "Devuelve la version de Octave instalada.", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string", "enum": ["validate"]}}}},
    {"name": "numeral_systems_embedding", "description": "Vectoriza sistemas numericos antiguos (base, tipo posicional/aditivo/ fisico, presencia de cero, redundancia representacional, soporte fisico) y proyecta a 2D via UMAP o t-SNE, para explorar agrupamientos estructurales entre culturas. Dataset base: maya_long_count, suanpan, soroban, roman_hand_abacus, yupana_depasquale, quipu, ifa_binary. Extensible via extra_systems (lista de dicts con el mismo s", "inputSchema": {"type": "object", "properties": {"method": {"type": "string", "enum": ["umap", "tsne", "validate"]}, "extra_systems": {"type": "array"}, "n_neighbors": {"type": "integer"}, "perplexity": {"type": "number"}, "random_state": {"type": "integer"}, "run_id": {"type": "string"}}}},
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

                elif tool_name == "numeral_systems_embedding":
                    result = compute_numeral_systems_embedding(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
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

                elif tool_name == "information_theory":
                    result = compute_information_theory(**args)
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
                    text = json.dumps(output, ensure_ascii=False, indent=2) if isinstance(output, dict) else (output or "(sin salida)")
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": text}]},
                    }

                elif tool_name == "octave_eval_expr":
                    output = octave_eval_expr(**args)
                    text = json.dumps(output, ensure_ascii=False, indent=2) if isinstance(output, dict) else (output or "(sin salida)")
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": text}]},
                    }

                elif tool_name == "octave_run_script":
                    output = octave_run_script(**args)
                    text = json.dumps(output, ensure_ascii=False, indent=2) if isinstance(output, dict) else (output or "(sin salida)")
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": text}]},
                    }

                elif tool_name == "octave_version":
                    output = octave_version(**args)
                    text = json.dumps(output, ensure_ascii=False, indent=2) if isinstance(output, dict) else (output or "(sin salida)")
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": text}]},
                    }

                elif tool_name == "compute_lyapunov_v2":
                    result = compute_lyapunov_v2(**args)
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

                elif tool_name == "number_theory":
                    result = compute_number_theory(**args)
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

                elif tool_name == "tritbraid":
                    tb_kwargs = {k: v for k, v in args.items() if k in ("mode", "program", "seed", "initial_state")}
                    result = compute_tritbraid(**tb_kwargs)
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
                elif tool_name == "semantic_bridge":
                    result = compute_semantic_bridge(args.get("mode"), args.get("params"), tools=TOOLS)
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
