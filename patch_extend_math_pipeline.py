"""
patch_extend_math_pipeline.py

Extiende math_pipeline_builder_tool.py (el orquestador REALMENTE conectado
a server.py, no el math_pipeline_tool.py que quedo sin usar) con 6 tools
nuevos verificados como autocontenidos (cada uno define su propio
_run_octave local, no dependen de nada externo de server.py):

    bacterial_growth_tool, enzyme_kinetics, population_dynamics,
    reaction_diffusion_real, statistics, symbolic

Mismo patron backup->patch->validate de siempre. Corre esto desde
~/octave-mcp.
"""
import ast
import shutil
from datetime import datetime

path = "math_pipeline_builder_tool.py"
c = open(path, encoding="utf-8").read()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
shutil.copy(path, f"{path}.bak.{ts}")

# --- 1. imports ---
old_imports = 'from math_interpolation_tool import compute_math_interpolation\n'
assert c.count(old_imports) == 1, f"imports match={c.count(old_imports)}"
new_imports = old_imports + (
    "from bacterial_growth_tool import compute_bacterial_growth_tool\n"
    "from enzyme_kinetics_tool import compute_enzyme_kinetics\n"
    "from population_dynamics_tool import compute_population_dynamics\n"
    "from reaction_diffusion_tool_real import compute_reaction_diffusion as compute_reaction_diffusion_real\n"
    "from statistics_tool import compute_statistics\n"
    "from symbolic_tool import compute_symbolic\n"
)
c = c.replace(old_imports, new_imports)

# --- 2. REGISTRY ---
old_registry_tail = '    "compute_math_interpolation": compute_math_interpolation,\n}'
assert c.count(old_registry_tail) == 1, f"registry match={c.count(old_registry_tail)}"
new_registry_tail = (
    '    "compute_math_interpolation": compute_math_interpolation,\n'
    '    "compute_bacterial_growth_tool": compute_bacterial_growth_tool,\n'
    '    "compute_enzyme_kinetics": compute_enzyme_kinetics,\n'
    '    "compute_population_dynamics": compute_population_dynamics,\n'
    '    "compute_reaction_diffusion_real": compute_reaction_diffusion_real,\n'
    '    "compute_statistics": compute_statistics,\n'
    '    "compute_symbolic": compute_symbolic,\n'
    '}'
)
c = c.replace(old_registry_tail, new_registry_tail)

# --- 3. TOOL_NAME_ALIASES ---
old_aliases_tail = '    "math_interpolation": "compute_math_interpolation",\n}'
assert c.count(old_aliases_tail) == 1, f"aliases match={c.count(old_aliases_tail)}"
new_aliases_tail = (
    '    "math_interpolation": "compute_math_interpolation",\n'
    '    "bacterial_growth_tool": "compute_bacterial_growth_tool",\n'
    '    "enzyme_kinetics": "compute_enzyme_kinetics",\n'
    '    "population_dynamics": "compute_population_dynamics",\n'
    '    "reaction_diffusion_real": "compute_reaction_diffusion_real",\n'
    '    "statistics": "compute_statistics",\n'
    '    "symbolic": "compute_symbolic",\n'
    '}'
)
c = c.replace(old_aliases_tail, new_aliases_tail)

# --- 4. schema: descripcion general (lista de dominios cubiertos) ---
old_desc = (
    '"Encadena llamadas a los tools matematicos de octave-mcp (diferenciacion "\n'
    '        "simbolica, Jacobiano, Lyapunov, ODEs stiff, bifurcacion, Hilbert, analisis "\n'
    '        "de error, benchmark de metodos, interpolacion), pasando el output de un "'
)
assert c.count(old_desc) == 1, f"desc general match={c.count(old_desc)}"
new_desc = old_desc.replace(
    "interpolacion), pasando",
    "interpolacion, crecimiento bacteriano, cinetica enzimatica, dinamica "
    "poblacional, reaccion-difusion, estadistica, calculo simbolico), pasando"
)
c = c.replace(old_desc, new_desc)

# --- 5. schema: enum textual "Uno de: ..." dentro de items.tool.description ---
old_enum_desc = (
    '"Nombre del tool a invocar. Uno de: compute_gradient_hessian, "\n'
    '                                "compute_jacobian, compute_lyapunov_exponent, integrate_stiff_ode, "\n'
    '                                "compute_bifurcation_diagram, compute_hilbert_transform, "\n'
    '                                "math_error_analyzer, math_benchmark, math_interpolation."'
)
assert c.count(old_enum_desc) == 1, f"enum desc match={c.count(old_enum_desc)}"
new_enum_desc = old_enum_desc.replace(
    'math_error_analyzer, math_benchmark, math_interpolation."',
    'math_error_analyzer, math_benchmark, math_interpolation, '
    'bacterial_growth_tool, enzyme_kinetics, population_dynamics, '
    'reaction_diffusion_real, statistics, symbolic."'
)
c = c.replace(old_enum_desc, new_enum_desc)

# --- 6. docstring del modulo (lista de fuentes) ---
old_docstring_list = (
    "auto_differentiation_tool, math_error_analyzer_tool,\n"
    "math_benchmark_tool, math_interpolation_tool, lyapunov_tool, stiff_ode_tool,\n"
    "bifurcation_tool, hilbert_tool)."
)
assert c.count(old_docstring_list) == 1, f"docstring match={c.count(old_docstring_list)}"
new_docstring_list = old_docstring_list.replace(
    "bifurcation_tool, hilbert_tool).",
    "bifurcation_tool, hilbert_tool, bacterial_growth_tool, enzyme_kinetics_tool,\n"
    "population_dynamics_tool, reaction_diffusion_tool_real, statistics_tool,\n"
    "symbolic_tool)."
)
c = c.replace(old_docstring_list, new_docstring_list)

ast.parse(c)
open(path, "w", encoding="utf-8").write(c)
print(f"math_pipeline_builder_tool.py parcheado (backup en {path}.bak.{ts})")

# --- 7. validacion Python-level: confirmar que los 15 tools quedaron registrados ---
import importlib
import math_pipeline_builder_tool as mpb
importlib.reload(mpb)
esperados = {
    "compute_gradient_hessian", "compute_jacobian", "compute_lyapunov_exponent",
    "integrate_stiff_ode", "compute_bifurcation_diagram", "compute_hilbert_transform",
    "compute_math_error_analysis", "compute_math_benchmark", "compute_math_interpolation",
    "compute_bacterial_growth_tool", "compute_enzyme_kinetics", "compute_population_dynamics",
    "compute_reaction_diffusion_real", "compute_statistics", "compute_symbolic",
}
faltantes = esperados - set(mpb.REGISTRY)
sobrantes_alias = {"bacterial_growth_tool", "enzyme_kinetics", "population_dynamics",
                    "reaction_diffusion_real", "statistics", "symbolic"} - set(mpb.TOOL_NAME_ALIASES)
assert not faltantes, f"faltan en REGISTRY: {faltantes}"
assert not sobrantes_alias, f"faltan en TOOL_NAME_ALIASES: {sobrantes_alias}"
print(f"REGISTRY: {len(mpb.REGISTRY)} tools (eran 9, ahora {len(mpb.REGISTRY)})")
print(f"TOOL_NAME_ALIASES: {len(mpb.TOOL_NAME_ALIASES)} aliases")

# --- 8. smoke test funcional real: mismo par (statistics -> ref encadenada) que
# ya se sabe que funciona, mas un tool nuevo standalone (bacterial_growth_tool) ---
r1 = mpb.run_math_pipeline(mode="run", steps=[
    {"tool": "statistics", "args": {"mode": "linear_regression", "preset": "known_linear"}, "save_as": "reg"},
])
assert r1["trace"][0]["tool"] == "statistics" and "reg" in r1["results"], "smoke test statistics fallo"
print("smoke test 'statistics' via alias: OK ->", r1["results"]["reg"].get("slope"))

r2 = mpb.run_math_pipeline(mode="run", steps=[
    {"tool": "compute_bacterial_growth_tool", "args": {"mode": "validate"}, "save_as": "bg"},
])
print("smoke test 'bacterial_growth_tool' via nombre de funcion:", r2["trace"][0].get("tool"), "-> OK" if "bg" in r2["results"] else "-> REVISAR")
