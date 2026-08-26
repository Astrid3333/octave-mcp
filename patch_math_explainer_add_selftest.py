#!/usr/bin/env python3
"""
patch_math_explainer_add_selftest.py
Agrega self-test (source_tool="validate") a math_explainer_tool.py.

Cambios:
1) TOOL_SCHEMA: "required": ["source_tool", "result"] -> ["source_tool"]
   (result deja de ser obligatorio para poder llamar con solo source_tool="validate")
2) Inserta _run_self_test() antes de interpret_and_explain(), y agrega:
   - result=None como default en la firma
   - branch if source_tool == "validate": return _run_self_test()

No toca server.py (math_explainer ya esta importado/registrado ahi).
"""
import shutil
import datetime

PATH = "math_explainer_tool.py"

with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

# --- Anchor 1: required en el schema ---
anchor1 = '        "required": ["source_tool", "result"],\n    },\n}'
n1 = content.count(anchor1)
print(f"{PATH}: ocurrencias del ancla 1 (schema required) = {n1}")
assert n1 == 1, "ancla 1 no encontrada o no es unica -- abortando, no se toco el archivo"

replacement1 = '        "required": ["source_tool"],\n    },\n}'

# --- Anchor 2: firma + inicio de interpret_and_explain ---
anchor2 = (
    'def interpret_and_explain(source_tool, result, level="tecnico"):\n'
    '    if isinstance(result, str):\n'
    '        result = json.loads(result)'
)
n2 = content.count(anchor2)
print(f"{PATH}: ocurrencias del ancla 2 (interpret_and_explain) = {n2}")
assert n2 == 1, "ancla 2 no encontrada o no es unica -- abortando, no se toco el archivo"

self_test_code = '''def _run_self_test():
    """Autochequeo: corre interpret_and_explain sobre resultados sinteticos
    representativos de cada uno de los 17 tools reconocidos en _EXPLAINERS
    (mas el fallback generico), en ambos niveles ('basico' y 'tecnico'),
    y verifica que cada explicacion sea un string no vacio, que known_tool
    sea correcto, y que nada lance excepcion."""
    synthetic_cases = [
        ("compute_gradient_hessian", {
            "gradient": {"x": {"sympy": "2*x"}, "y": {"sympy": "2*y"}},
            "hessian": [[2, 0], [0, 2]],
        }),
        ("compute_jacobian", {"determinant": 3.5}),
        ("compute_lyapunov_exponent", {"lyapunov_exponent": 0.9}),
        ("integrate_stiff_ode", {"solver": "Radau", "t": [0.0, 0.1, 0.2]}),
        ("compute_bifurcation_diagram", {"stability": True}),
        ("compute_hilbert_transform", {}),
        ("math_error_analyzer", {"mode": "condition_number", "condition_number": 120.5}),
        ("math_benchmark", {"mode": "richardson"}),
        ("math_interpolation", {"runge_phenomenon_detected": True}),
        ("run_math_pipeline", {
            "n_steps": 2,
            "trace": [
                {"step": 0, "tool": "compute_gradient_hessian", "save_as": "grad"},
                {"step": 1, "tool": "math_error_analyzer", "save_as": "err"},
            ],
        }),
        ("math_visualization", {"mode": "function_plot", "y_min": -1.0, "y_max": 1.0}),
        ("compute_disaster_simulation", {
            "mode": "monte_carlo_losses", "n_years_simulated": 1000,
            "mean_annual_loss": 500.0, "std_annual_loss": 50.0,
            "median_annual_loss": 480.0, "max_simulated_loss": 2000.0,
            "probability_zero_loss_year": 0.1,
            "var_cvar_by_percentile": {"95%": {"VaR": 900.0, "CVaR": 1200.0}},
        }),
        ("compute_critical_infrastructure", {
            "redundancy_score": 0.8, "total_edges": 10,
            "base_graph_connected": True, "n_critical_edges": 1,
            "critical_edges": [{"from": "A", "to": "B"}],
        }),
        ("compute_urban_planning", {
            "shannon_entropy_normalized": 0.7, "n_categories": 3,
            "proportions": {"residencial": 0.5, "comercial": 0.3, "industrial": 0.2},
        }),
        ("compute_enzyme_kinetics", {
            "mode": "michaelis_menten", "Km": 5.0, "Vmax": 10.0,
            "formula": "v=Vmax*S/(Km+S)", "velocidad_sample": [1.0, 2.0, 3.0],
        }),
        ("compute_bacterial_growth_tool", {
            "mode": "gompertz",
            "params": {"mu_max": 0.5, "A": 3.0, "lambda_lag": 1.0, "t_max": 10.0},
            "final_y": 2.9,
        }),
        ("compute_enzyme_stochastic", {
            "mode": "gillespie_ensemble",
            "params": {"n_runs": 10, "E0": 5, "S0": 100, "t_max": 50.0},
            "P_mean": [0.0, 50.0, 95.0], "P_std": [0.0, 5.0, 3.0],
        }),
    ]

    checks = []

    for source_tool, synth_result in synthetic_cases:
        for level in ("basico", "tecnico"):
            try:
                out = interpret_and_explain(source_tool, synth_result, level=level)
                ok = (
                    isinstance(out.get("explanation"), str)
                    and len(out["explanation"]) > 0
                    and out.get("known_tool") is True
                )
                checks.append({
                    "name": f"{source_tool} ({level}): explicacion no vacia, known_tool=True",
                    "passed": ok,
                    "got_len": len(out.get("explanation", "")),
                })
            except Exception as e:
                checks.append({
                    "name": f"{source_tool} ({level}): no debe lanzar excepcion",
                    "passed": False,
                    "error": str(e),
                })

    # Caso fallback: tool desconocido -> explicacion generica, known_tool=False.
    try:
        out = interpret_and_explain("un_tool_que_no_existe_todavia", {"foo": 1, "bar": 2}, level="tecnico")
        ok = (
            isinstance(out.get("explanation"), str)
            and len(out["explanation"]) > 0
            and out.get("known_tool") is False
        )
        checks.append({
            "name": "tool desconocido: fallback generico, known_tool=False",
            "passed": ok,
        })
    except Exception as e:
        checks.append({
            "name": "tool desconocido: no debe lanzar excepcion",
            "passed": False,
            "error": str(e),
        })

    # Cobertura: todos los tools de _EXPLAINERS tienen un caso sintetico.
    covered = {c[0] for c in synthetic_cases}
    missing = set(_EXPLAINERS.keys()) - covered
    checks.append({
        "name": "cobertura: todos los _EXPLAINERS tienen caso sintetico",
        "passed": len(missing) == 0,
        "missing": sorted(missing),
    })

    all_passed = all(c["passed"] for c in checks)
    return {
        "checks": checks,
        "all_passed": all_passed,
        "total": len(checks),
        "validation_passed": all_passed,
    }


def interpret_and_explain(source_tool, result=None, level="tecnico"):
    if source_tool == "validate":
        return _run_self_test()
    if isinstance(result, str):
        result = json.loads(result)'''

# --- Aplicar ---
new_content = content.replace(anchor1, replacement1, 1)
new_content = new_content.replace(anchor2, self_test_code, 1)

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = f"{PATH}.bak_{ts}"
shutil.copy(PATH, backup_path)
print(f"backup: {backup_path}")

with open(PATH, "w", encoding="utf-8") as f:
    f.write(new_content)

print("aplicado OK")
