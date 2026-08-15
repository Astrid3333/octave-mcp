#!/usr/bin/env python3
"""Agrega los 9 nombres directos que faltan en el enum del schema
(fix para test_schema_tool_enum_lists_every_registered_alias_and_tool)."""

PATH = "math_pipeline_builder_tool.py"

OLD = "reaction_diffusion_real, statistics, symbolic."
NEW = (
    "reaction_diffusion_real, statistics, symbolic, "
    "compute_bacterial_growth_tool, compute_enzyme_kinetics, "
    "compute_math_benchmark, compute_math_error_analysis, "
    "compute_math_interpolation, compute_population_dynamics, "
    "compute_reaction_diffusion_real, compute_statistics, compute_symbolic."
)

with open(PATH, encoding="utf-8") as f:
    content = f.read()

n = content.count(OLD)
assert n == 1, f"Se esperaba 1 ocurrencia, se encontraron {n} — revisar a mano antes de aplicar"

with open(PATH, "w", encoding="utf-8") as f:
    f.write(content.replace(OLD, NEW))

print("Patch aplicado OK")
