import json
import re
import textwrap

with open("/tmp/tools_list_raw.json", encoding="utf-8") as f:
    resp = json.loads(f.read().strip())
all_tools = {t["name"]: t.get("description", "") for t in resp["result"]["tools"]}

with open("README.md", encoding="utf-8") as f:
    readme = f.read()
mentioned = set(re.findall(r"`([a-zA-Z][a-zA-Z0-9_]*)`", readme))

new_tools = sorted(set(all_tools) - mentioned)

CATEGORIES = [
    ("Desastres y riesgo natural", ["disaster", "earthquake", "flood", "wildfire",
        "hazard", "landslide", "tsunami", "hurricane", "resilience", "early_warning",
        "cascading_failure", "cascading_outbreak", "systemic_risk", "sandpile",
        "domino_effect", "bilevel_interdiction", "critical_infrastructure"]),
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
        "pedotransfer", "ethical_food", "sustainable_sourcing"]),
    ("Acustica, ondas y electromagnetismo", ["acoustic", "wave_propagation",
        "audio_", "electromagnetic", "rf_network", "circuit_tool", "photonic",
        "infrasound", "openems", "bem_", "fem_electromagnetic", "polarization",
        "synchrotron", "bremsstrahlung", "pair_production", "pair_annihilation",
        "dispersion_relation", "tight_binding", "gravitational_waves"]),
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
        "nonlinear_vibration", "multibody_dynamics", "kinematics_simulator",
        "gait_analysis", "socket_topology", "topology_optimization",
        "particle_simulation", "molecular_dynamics"]),
    ("Sistemas dinamicos y caos (extendido)", ["lyapunov", "bifurcation",
        "chaos_diagnosis", "correlation_dimension", "attractor_geometry",
        "fractal_dimension"]),
    ("Geociencias, topografia y agrimensura (extendido)", ["survey_", "terrain",
        "hydrometeo", "flood_connectivity", "flood_risk_narrator",
        "flood_modeling", "geospatial_risk", "tidal_harmonic",
        "marine_ecosystem", "natural_hazard"]),
    ("Ciencia de materiales y estado solido", ["crystal", "spectroscopy",
        "dft_tool", "statmech", "tight_binding", "quantum_information",
        "vacuum_energy", "scalar_field_cosmology", "unified_dark_sector",
        "semiclassical_cosmology", "quantum_cosmology"]),
    ("Herramientas del catalogo / orquestacion (extendido)", ["tool_catalog",
        "knowledge_graph", "semantic_bridge", "report_generator",
        "parallel_task_runner", "mission_runner", "compute_math_pipeline",
        "octave_grammar", "octave_innovation_doc", "health_check"]),
    ("Combinatoria y sistemas ternarios", ["ternary_"]),
    ("Datos externos y fuentes", ["arxiv_tool", "nasa_tool", "data_file_reader",
        "units_constants"]),
    ("Modelado social y educativo", ["teaching_strategies", "social_impact",
        "resource_assignment", "decision_support"]),
    ("Point cloud y vision 3D", ["point_cloud"]),
    ("Machine learning y vectores", ["machine_learning_vector", "vector_optimizer",
        "vector_field_visualizer", "vector_calculus"]),
    ("Color y percepcion", ["color_math"]),
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

def short(desc, n=100):
    desc = desc.strip().split(". ")[0]
    return textwrap.shorten(desc, width=n, placeholder="...")

lines = []
lines.append(f"# Borrador de categorizacion -- {len(new_tools)} tools nuevas sin documentar en README\n")
for cat, _ in CATEGORIES:
    items = categorized[cat]
    if not items:
        continue
    lines.append(f"## {cat} ({len(items)})")
    for name, desc in items:
        lines.append(f"- `{name}` -- {short(desc)}")
    lines.append("")

lines.append(f"## SIN CATEGORIZAR -- revisar manualmente ({len(uncategorized)})")
for name, desc in uncategorized:
    lines.append(f"- `{name}` -- {short(desc)}")

with open("/tmp/readme_draft_categorized.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("Escrito en /tmp/readme_draft_categorized.md")
print(f"Categorizadas automaticamente: {len(used)} / {len(new_tools)}")
print(f"Sin categorizar (necesitan revision manual): {len(uncategorized)}")
