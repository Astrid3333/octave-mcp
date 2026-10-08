#!/usr/bin/env python3
import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent
README = ROOT / "README.md"

CATALOG_HEADER = "## Catalogo ampliado"
CATALOG_TAIL_ANCHOR = "## Despliegue con Docker"
N_LEGACY = 7

CATEGORIES = [
    ("Desastres y riesgo natural", [
        "disaster", "earthquake", "flood", "wildfire", "hazard", "landslide",
        "tsunami", "hurricane", "resilience", "early_warning", "cascading_failure",
        "cascading_outbreak", "systemic_risk", "sandpile", "domino_effect",
        "bilevel_interdiction", "critical_infrastructure", "forest_fire_simulator",
        "physics_based_fire_model", "cascade_orchestrator_tool", "information_cascade_tool",
    ]),
    ("Clima, energia y sostenibilidad", [
        "climate", "carbon_footprint", "renewable", "solar", "wind_power",
        "battery_sizing", "deforestation", "circular_economy", "sustainable",
        "water_resource", "urban_planning", "public_data_ingest", "land_use",
        "soil_erosion", "heating_value",
    ]),
    ("Finanzas personales y actuaria", [
        "debt_", "credit_", "tax_", "retirement_", "insurance_", "saving",
        "budget", "investment", "education_funding", "spending_pattern",
        "habit_streak", "financial_literacy", "refinance", "emergency_fund",
        "life_insurance",
    ]),
    ("Biologia computacional y ecologia", [
        "cell_", "stem_cell", "genom", "enzyme", "viral", "bacteri", "ecosystem",
        "agricultur", "biodivers", "cardiac", "gene_drive", "genetic_circuit",
        "crispr", "fungal", "lichen", "moss", "algae", "marine", "poaching",
        "toxicity", "pharmacokinet", "genesom", "hormone", "aminoacid",
        "mycelial", "cryptogam", "photosynthesis", "food_chemistry",
        "ultra_processed", "compositional_analysis", "chemometrics",
        "soil_mechanics", "soil_water", "soil_mixture", "pedotransfer",
        "ethical_food", "sustainable_sourcing", "droop_kelp_tool",
        "rpa_kinetics_tool", "ion_chemistry_tool",
    ]),
    ("Resonancia magnetica / RMN", [
        "bloch_equation_tool", "gradient_field_tool", "kspace_reconstruction_tool",
        "relaxometry_tool",
    ]),
    ("Procesamiento de senales", [
        "filter_design_tool", "fractional_fourier_tool", "spectral_analysis_tool",
        "time_frequency_tool",
    ]),
    ("Perforacion y pozos petroleros", ["dynamic_kill_calculator_tool"]),
    ("Acustica, ondas y electromagnetismo", [
        "acoustic", "wave_propagation", "audio_", "electromagnetic", "rf_network",
        "circuit_tool", "photonic", "infrasound", "openems", "bem_",
        "fem_electromagnetic", "polarization", "synchrotron", "bremsstrahlung",
        "pair_production", "pair_annihilation", "dispersion_relation",
        "tight_binding", "gravitational_waves", "nonlinear_vibration",
    ]),
    ("Geometria, mallas y cosmologia", [
        "mesh_", "distmesh", "sdf_tool", "lscm_", "cosmolog", "quantum_astro",
        "curvilinear", "coordinate_transform", "trilinear", "algebraic_curve",
        "morse_theory", "projective_geometry", "voronoi", "joukowski",
        "linear_transform_figure", "julia_mandelbrot", "surface_geometry",
        "space_curves",
    ]),
    ("Historia cuantitativa y arqueologia", [
        "archaeo", "historic", "paleograph", "ethnomath", "ancestral", "ancient",
        "levant", "originarios", "settlement_clusters", "plague_sir",
    ]),
    ("Ingenieria estructural y mecanica", [
        "structural_", "finite_element", "plane_stress", "thermal_structural",
        "thermal_conduction", "thermal_advanced", "nonlinear_buckling",
        "forced_vibration", "multibody_dynamics", "kinematics_simulator",
        "gait_analysis", "socket_topology", "topology_optimization",
        "particle_simulation", "molecular_dynamics", "fem_advanced_tool",
    ]),
    ("Sistemas dinamicos y caos (extendido)", [
        "lyapunov", "bifurcation", "chaos_diagnosis", "correlation_dimension",
        "attractor_geometry", "fractal_dimension", "lorenz",
    ]),
    ("Geociencias, topografia y agrimensura (extendido)", [
        "survey_", "terrain", "hydrometeo", "flood_connectivity",
        "flood_risk_narrator", "flood_modeling", "geospatial_risk",
        "tidal_harmonic", "marine_ecosystem", "natural_hazard",
        "hydrothermal_inference_tool", "altitude_pressure_tool",
    ]),
    ("Ciencia de materiales y estado solido", [
        "crystal", "spectroscopy", "dft_tool", "statmech", "quantum_information",
        "vacuum_energy", "scalar_field_cosmology", "unified_dark_sector",
        "semiclassical_cosmology", "quantum_cosmology",
    ]),
    ("Herramientas del catalogo / orquestacion (extendido)", [
        "tool_catalog", "knowledge_graph", "semantic_bridge", "report_generator",
        "parallel_task_runner", "mission_runner", "compute_math_pipeline",
        "octave_grammar", "octave_innovation_doc", "health_check", "octave_syntax",
        "plotting_tools", "run_octave", "run_pipeline", "workspace_link",
        "workspace_validate",
    ]),
    ("Combinatoria y sistemas ternarios", ["ternary_"]),
    ("Datos externos y fuentes", [
        "arxiv_tool", "nasa_tool", "data_file_reader", "units_constants",
    ]),
    ("Modelado social y educativo", [
        "teaching_strategies", "social_impact", "resource_assignment",
        "decision_support",
    ]),
    ("Point cloud y vision 3D", ["point_cloud"]),
    ("Machine learning y vectores", [
        "machine_learning_vector", "vector_optimizer", "vector_field_visualizer",
        "vector_calculus",
    ]),
    ("Color y percepcion", ["color_math"]),
    ("Divulgacion matematica (extendido)", ["periodic_patterns_tool"]),
    ("Algebra, calculo y analisis (extendido)", ["number_theory"]),
]

UNCATEGORIZED = "Sin categorizar (pendiente revision)"

TOOL_NAME_RE = re.compile(r"^-\s*`([a-zA-Z][a-zA-Z0-9_]*)`?(.*)$")
TICKED_NAME_RE = re.compile(r"[`*]{1,2}([A-Za-z][A-Za-z0-9_]*)[`*]{1,2}")


def load_runtime():
    try:
        import server

        from tool_registry import REGISTRY
    except ModuleNotFoundError:
        n_reg = 0
        for path in ROOT.glob("*_tool.py"):
            n_reg += path.read_text(errors="ignore").count("register_tool(")
        return n_reg + N_LEGACY, 3, n_reg, {}
    schemas = {}
    for tool in server.TOOLS:
        if isinstance(tool, dict) and tool.get("name"):
            schemas[tool["name"]] = tool.get("description", "")
    return len(server.TOOLS), len(server.META_TOOLS), len(REGISTRY), schemas


def short(description):
    first = re.split(r"\n", description or "")[0].strip()
    if len(first) <= 140:
        return first
    return textwrap.shorten(first, width=140, placeholder="...")


def main():
    check = "--check" in sys.argv
    if not README.exists():
        print(f"fatal: {README} no existe", file=sys.stderr)
        return 2

    n_total, n_meta, n_reg, schemas = load_runtime()
    n_all = n_total + n_meta

    lines = README.read_text(encoding="utf-8").split("\n")[:-1]

    catalog_start = next(
        (i for i, ln in enumerate(lines) if ln.startswith(CATALOG_HEADER)), None
    )
    tail_start = next(
        (i for i, ln in enumerate(lines) if ln.startswith(CATALOG_TAIL_ANCHOR)), None
    )
    if catalog_start is None or tail_start is None or tail_start <= catalog_start:
        print(
            "fatal: no se pudieron ubicar las secciones "
            f"{CATALOG_HEADER!r} / {CATALOG_TAIL_ANCHOR!r} en el README",
            file=sys.stderr,
        )
        return 2

    curated_lines = lines[:catalog_start]
    catalog_lines = lines[catalog_start:tail_start]
    tail_lines = lines[tail_start:]

    h3_start = next((i for i, ln in enumerate(catalog_lines) if ln.startswith("### ")), None)
    if h3_start is None:
        print("fatal: sin secciones h3 en el catalogo", file=sys.stderr)
        return 2
    intro_lines = catalog_lines[:h3_start]
    body_lines = catalog_lines[h3_start:]

    bullets = {}
    bullet_cat = {}
    current = None
    for ln in body_lines:
        if ln.startswith("### "):
            current = ln[4:].strip()
            continue
        m = TOOL_NAME_RE.match(ln)
        if m and current:
            name = m.group(1)
            if name in bullets:
                continue
            bullets[name] = ln.rstrip()
            bullet_cat[name] = current

    curated_names = set()
    for ln in curated_lines:
        for name in TICKED_NAME_RE.findall(ln):
            curated_names.add(name)

    alive = set(schemas)
    removed = sorted(set(bullets) - alive)
    for name in removed:
        del bullets[name]
        del bullet_cat[name]

    categories = {name: set() for name, _ in CATEGORIES}
    added = []

    def classify(name):
        lower = name.lower()
        for cat, keywords in CATEGORIES:
            if any(k in lower for k in keywords):
                return cat
        return UNCATEGORIZED

    for name in sorted(alive):
        if name in bullets:
            cat = bullet_cat.get(name)
            if cat not in categories:
                cat = classify(name)
            categories.setdefault(cat, set()).add(name)
            continue
        if name in curated_names:
            continue
        cat = classify(name)
        categories.setdefault(cat, set()).add(name)
        added.append(name)

    for cat, names in categories.items():
        for name in names:
            if name not in bullets:
                bullets[name] = f"- `{name}` -- {short(schemas.get(name))}" if schemas.get(name) else f"- `{name}`"

    intro_out = list(intro_lines)
    intro_out[0] = (
        f"{CATALOG_HEADER} ({n_total} herramientas + {n_meta} meta-tools = "
        f"{n_all} tools totales -- seccion generada automaticamente desde "
        "`tools/list_full`, complementa las categorias curadas arriba)"
    )
    for i, ln in enumerate(intro_out):
        if ln.startswith("*Las tools de las secciones anteriores"):
            intro_out[i] = (
                f"*Las tools de las secciones anteriores no se repiten aca. "
                f"Las secciones combinadas (curadas + catalogo) cubren las "
                f"{n_total} herramientas + {n_meta} meta-tools = {n_all} tools en total.*"
            )
            break

    groups = []
    for cat, _ in CATEGORIES:
        names = sorted(categories[cat])
        if not names:
            continue
        blocks = ["### " + cat, ""]
        blocks.extend(bullets[name] for name in names)
        groups.append(blocks)
    if categories.get(UNCATEGORIZED):
        names = sorted(categories[UNCATEGORIZED])
        blocks = ["### " + UNCATEGORIZED, ""]
        blocks.extend(bullets[name] for name in names)
        groups.append(blocks)
    rendered_bullets = sum(len(block) - 2 for block in groups)

    while intro_out and not intro_out[-1].strip():
        intro_out.pop()
    intro_out += ["", ""]

    footer = []
    for block in groups:
        footer.extend(block)
        footer.append("")

    body_out = intro_out + footer

    curated_out = []
    for ln in curated_lines:
        out = ln
        out = re.sub(r"expone \d+ herramientas", f"expone {n_total} herramientas", out)
        out = re.sub(
            r"más \d+ meta-tools de introspección, \d+ en total",
            f"más {n_meta} meta-tools de introspección, {n_all} en total",
            out,
        )
        out = re.sub(r"\(\d+ tools auto-registradas\)", f"({n_reg} tools auto-registradas)", out)
        out = re.sub(r"devuelve las \d+ herramientas", f"devuelve las {n_total} herramientas", out)
        out = re.sub(r"de las \d+ herramientas", f"de las {n_total} herramientas", out)
        curated_out.append(out)

    new_text = "\n".join(curated_out + body_out + tail_lines) + "\n"

    if check:
        old_text = "\n".join(lines) + "\n"
        if new_text == old_text:
            print(
                f"OK: README sincronizado ({n_total}+{n_meta}={n_all} tools, "
                f"{rendered_bullets} bullets en catalogo)"
            )
            return 0
        new_set = set(schemas)
        print("DRIFT: README fuera de sincronia", file=sys.stderr)
        print(f"  tools actuales: {n_total}+{n_meta}={n_all}", file=sys.stderr)
        if removed:
            print(f"  bullets huerfanos (tools que ya no existen): {', '.join(removed)}", file=sys.stderr)
        if added:
            print(f"  tools sin bullet en README: {', '.join(added)}", file=sys.stderr)
        print("  correr: .venv/bin/python render_readme.py", file=sys.stderr)
        return 1

    README.write_text(new_text, encoding="utf-8")
    print(
        f"README regenerado: {n_total}+{n_meta}={n_all} tools, "
        f"{rendered_bullets} bullets en catalogo"
    )
    if removed:
        print(f"  bullets huerfanos eliminados: {', '.join(removed)}")
    if added:
        print(f"  bullets nuevos agregados: {', '.join(added)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())