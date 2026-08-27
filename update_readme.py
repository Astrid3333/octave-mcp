import json
import re
import textwrap

with open("/tmp/tools_list_raw.json", encoding="utf-8") as f:
    resp = json.loads(f.read().strip())
all_tools = {t["name"]: t.get("description", "") for t in resp["result"]["tools"]}

with open("README.md", encoding="utf-8") as f:
    readme = f.read()

# --- respaldo ---
with open("README.md.bak", "w", encoding="utf-8") as f:
    f.write(readme)

mentioned = set(re.findall(r"[`*]{1,2}([a-zA-Z][a-zA-Z0-9_]*)[`*]{1,2}", readme))
new_tools = sorted(set(all_tools) - mentioned)

# falsos positivos ya documentados en negrita en el README (no van de nuevo)
FALSE_POSITIVES = {"biorefinery_tool", "gas_tool"}
new_tools = [t for t in new_tools if t not in FALSE_POSITIVES]

CATEGORIES = [
    ("Desastres y riesgo natural", ["disaster", "earthquake", "flood", "wildfire",
        "hazard", "landslide", "tsunami", "hurricane", "resilience", "early_warning",
        "cascading_failure", "cascading_outbreak", "systemic_risk", "sandpile",
        "domino_effect", "bilevel_interdiction", "critical_infrastructure",
        "forest_fire_simulator", "physics_based_fire_model", "cascade_orchestrator_tool",
        "information_cascade_tool"]),
    ("Clima, energia y sostenibilidad", ["climate", "carbon_footprint", "renewable",
        "solar", "wind_power", "battery_sizing", "deforestation", "circular_economy",
        "sustainable", "water_resource", "urban_planning", "public_data_ingest",
        "land_use", "soil_erosion", "heating_value"]),
    ("Finanzas personales y actuaria", ["debt_", "credit_", "tax_", "retirement_",
        "insurance_", "saving", "budget", "investment", "education_funding",
        "spending_pattern", "habit_streak", "financial_literacy", "refinance",
        "emergency_fund", "life_insurance"]),
    ("Biologia computacional y ecologia", ["cell_", "stem_cell", "genom", "enzyme",
        "viral", "bacteri", "ecosystem", "agricultur", "biodivers", "cardiac",
        "gene_drive", "genetic_circuit", "crispr", "fungal", "lichen", "moss",
        "algae", "marine", "poaching", "toxicity", "pharmacokinet", "genESOM",
        "hormone", "aminoacid", "mycelial", "cryptogam", "photosynthesis",
        "food_chemistry", "ultra_processed", "compositional_analysis",
        "chemometrics", "soil_mechanics", "soil_water", "soil_mixture",
        "pedotransfer", "ethical_food", "sustainable_sourcing", "droop_kelp_tool",
        "rpa_kinetics_tool", "ion_chemistry_tool"]),
    ("Resonancia magnetica / RMN", ["bloch_equation_tool", "gradient_field_tool",
        "kspace_reconstruction_tool", "relaxometry_tool"]),
    ("Procesamiento de senales", ["filter_design_tool", "fractional_fourier_tool",
        "spectral_analysis_tool", "time_frequency_tool"]),
    ("Perforacion y pozos petroleros", ["dynamic_kill_calculator_tool"]),
    ("Acustica, ondas y electromagnetismo", ["acoustic", "wave_propagation",
        "audio_", "electromagnetic", "rf_network", "circuit_tool", "photonic",
        "infrasound", "openems", "bem_", "fem_electromagnetic", "polarization",
        "synchrotron", "bremsstrahlung", "pair_production", "pair_annihilation",
        "dispersion_relation", "tight_binding", "gravitational_waves",
        "nonlinear_vibration"]),
    ("Geometria, mallas y cosmologia", ["mesh_", "distmesh", "sdf_tool", "lscm_",
        "cosmolog", "quantum_astro", "curvilinear", "coordinate_transform",
        "trilinear", "algebraic_curve", "morse_theory", "projective_geometry",
        "voronoi", "joukowski", "linear_transform_figure", "julia_mandelbrot",
        "surface_geometry", "space_curves"]),
    ("Historia cuantitativa y arqueologia", ["archaeo", "historic", "paleograph",
        "ethnomath", "ancestral", "ancient", "levant", "originarios",
        "settlement_clusters", "plague_sir"]),
    ("Ingenieria estructural y mecanica", ["structural_", "finite_element",
        "plane_stress", "thermal_structural", "thermal_conduction",
        "thermal_advanced", "nonlinear_buckling", "forced_vibration",
        "multibody_dynamics", "kinematics_simulator",
        "gait_analysis", "socket_topology", "topology_optimization",
        "particle_simulation", "molecular_dynamics", "fem_advanced_tool"]),
    ("Sistemas dinamicos y caos (extendido)", ["lyapunov", "bifurcation",
        "chaos_diagnosis", "correlation_dimension", "attractor_geometry",
        "fractal_dimension", "lorenz"]),
    ("Geociencias, topografia y agrimensura (extendido)", ["survey_", "terrain",
        "hydrometeo", "flood_connectivity", "flood_risk_narrator",
        "flood_modeling", "geospatial_risk", "tidal_harmonic",
        "marine_ecosystem", "natural_hazard", "hydrothermal_inference_tool",
        "altitude_pressure_tool"]),
    ("Ciencia de materiales y estado solido", ["crystal", "spectroscopy",
        "dft_tool", "statmech", "quantum_information",
        "vacuum_energy", "scalar_field_cosmology", "unified_dark_sector",
        "semiclassical_cosmology", "quantum_cosmology"]),
    ("Herramientas del catalogo / orquestacion (extendido)", ["tool_catalog",
        "knowledge_graph", "semantic_bridge", "report_generator",
        "parallel_task_runner", "mission_runner", "compute_math_pipeline",
        "octave_grammar", "octave_innovation_doc", "health_check",
        "octave_syntax", "plotting_tools", "run_octave", "run_pipeline",
        "workspace_link", "workspace_validate"]),
    ("Combinatoria y sistemas ternarios", ["ternary_"]),
    ("Datos externos y fuentes", ["arxiv_tool", "nasa_tool", "data_file_reader",
        "units_constants"]),
    ("Modelado social y educativo", ["teaching_strategies", "social_impact",
        "resource_assignment", "decision_support"]),
    ("Point cloud y vision 3D", ["point_cloud"]),
    ("Machine learning y vectores", ["machine_learning_vector", "vector_optimizer",
        "vector_field_visualizer", "vector_calculus"]),
    ("Color y percepcion", ["color_math"]),
    ("Divulgacion matematica (extendido)", ["periodic_patterns_tool"]),
    ("Algebra, calculo y analisis (extendido)", ["number_theory"]),
]

used = set()
categorized = {cat: [] for cat, _ in CATEGORIES}
for name in new_tools:
    desc = all_tools.get(name, "")
    for cat, keywords in CATEGORIES:
        if any(kw in name for kw in keywords):
            categorized[cat].append((name, desc))
            used.add(name)
            break

uncategorized = [(n, all_tools.get(n, "")) for n in new_tools if n not in used]


def short(desc, n=140):
    desc = desc.strip().split(". ")[0]
    return textwrap.shorten(desc, width=n, placeholder="...")


section_lines = []
section_lines.append("\n---\n")
section_lines.append(f"\n## Catalogo ampliado ({len(all_tools)} tools totales -- seccion generada automaticamente desde `tools/list`, "
                      f"complementa las categorias curadas arriba)\n")
section_lines.append(f"\n*Las {len(all_tools) - len(new_tools) - len(FALSE_POSITIVES)} tools de las secciones anteriores no se repiten aca. "
                      f"Esta seccion cubre las {len(new_tools)} tools agregadas despues de la ultima curacion manual del README.*\n")

for cat, _ in CATEGORIES:
    items = categorized[cat]
    if not items:
        continue
    section_lines.append(f"\n### {cat}\n")
    for name, desc in items:
        section_lines.append(f"- `{name}` -- {short(desc)}")

if uncategorized:
    section_lines.append(f"\n### Sin categorizar (pendiente revision)\n")
    for name, desc in uncategorized:
        section_lines.append(f"- `{name}` -- {short(desc)}")

new_section = "\n".join(section_lines) + "\n"

# actualizar conteo en la intro (241 -> 326, o el numero que corresponda)
updated_readme = re.sub(
    r"expone \d+ herramientas",
    f"expone {len(all_tools)} herramientas",
    readme,
)

# insertar la seccion nueva justo antes de "## Estado" si existe, si no al final
if "## Estado" in updated_readme:
    updated_readme = updated_readme.replace("## Estado", new_section + "\n## Estado")
else:
    updated_readme = updated_readme + new_section

with open("README.md", "w", encoding="utf-8") as f:
    f.write(updated_readme)

print(f"README.md actualizado. Respaldo del original en README.md.bak")
print(f"Tools totales: {len(all_tools)}")
print(f"Tools nuevas agregadas en la seccion nueva: {len(new_tools)}")
print(f"  - categorizadas automaticamente: {len(used)}")
print(f"  - sin categorizar (revisar): {len(uncategorized)}")
