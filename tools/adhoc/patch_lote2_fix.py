#!/usr/bin/env python3
"""
patch_lote2_fix.py

Dos correcciones sobre el estado actual de Lote 2:

1) glm_tool.py ya tiene _validate_glm() insertada, pero el check
   'lasso_sparsity_recovery' pedia n_nonzero_coefficients == 3, algo que
   CV estandar (lambda.min) no garantiza -- CV optimiza error de
   prediccion, no recuperacion de soporte exacto. Se reemplaza por un
   chequeo de magnitud relativa: los coeficientes verdaderamente nulos
   deben quedar chicos frente a los verdaderamente no nulos.

2) archaeological_simulation.py no existe -- el archivo real es
   archaeological_simulation_tool.py. Se aplica ahi el mismo patch de
   Lote 2 (_validate_archaeological_simulation + branch + enum).

Mismo patron de siempre: backup con timestamp, anchors unicos con
assert count==1, ast.parse antes de escribir.

Correr desde ~/octave-mcp:
    python3 patch_lote2_fix.py
"""
import ast
import re
import shutil
import time

TIMESTAMP = int(time.time())


def backup(path):
    bak = f"{path}.bak.{TIMESTAMP}"
    shutil.copy(path, bak)
    print(f"OK: backup creado en {bak}")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def replace_unique(content, old, new, path, label):
    count = content.count(old)
    if count != 1:
        raise RuntimeError(
            f"ANCHOR NO UNICO ({count} ocurrencias) en {path} para '{label}'. "
            "Abortando sin escribir -- revisa el archivo manualmente."
        )
    return content.replace(old, new, 1)


def verify_syntax(path, content):
    try:
        ast.parse(content)
    except SyntaxError as e:
        raise RuntimeError(f"SINTAXIS INVALIDA en {path} tras el parche: {e}")
    print(f"OK: {path} parcheado y sintaxis valida.")


# ---------------------------------------------------------------------
# 1) glm_tool.py: corregir lasso_sparsity_recovery
# ---------------------------------------------------------------------

GLM_OLD = '''        # lasso: recupera exactamente los 3 coeficientes no nulos de true_beta2
        r_lasso = _ridge_lasso("lasso", X2.tolist(), y2.tolist(),
                                lambdas=[0.001, 0.01, 0.1, 1.0], k_folds=5)
        checks.append({
            "name": "lasso_sparsity_recovery",
            "expected": 3,
            "got": r_lasso["n_nonzero_coefficients"],
            "passed": r_lasso["n_nonzero_coefficients"] == 3,
        })'''

GLM_NEW = '''        # lasso: CV estandar (lambda.min) minimiza error de prediccion, no
        # garantiza ceros exactos -- se compara magnitud relativa en vez de
        # contar no-nulos. true_beta2 = [1.5, 0.0, -2.0, 0.0, 3.0]
        r_lasso = _ridge_lasso("lasso", X2.tolist(), y2.tolist(),
                                lambdas=[0.001, 0.01, 0.1, 1.0], k_folds=5)
        coefs_lasso = np.array(r_lasso["coefficients_standardized"])
        true_nonzero_idx = [0, 2, 4]
        true_zero_idx = [1, 3]
        signal_mag = float(np.abs(coefs_lasso[true_nonzero_idx]).min())
        noise_mag = float(np.abs(coefs_lasso[true_zero_idx]).max())
        checks.append({
            "name": "lasso_sparsity_recovery",
            "expected": "coef en variables nulas << coef en variables con senal (noise < 0.1 * signal)",
            "got": {"min_signal_coef": round(signal_mag, 6), "max_noise_coef": round(noise_mag, 6)},
            "passed": bool(noise_mag < 0.1 * signal_mag),
        })'''


def patch_glm():
    path = "glm_tool.py"
    print(f"\n--- {path} ---")
    content = read(path)
    backup(path)
    content = replace_unique(content, GLM_OLD, GLM_NEW, path, "fix lasso_sparsity_recovery")
    verify_syntax(path, content)
    write(path, content)


# ---------------------------------------------------------------------
# 2) archaeological_simulation_tool.py: aplicar el patch de Lote 2
#    (mismo contenido que en patch_lote2_validate.py, apuntado al
#    nombre de archivo correcto)
# ---------------------------------------------------------------------

VALIDATE_ARCHAEO = '''
def _validate_archaeological_simulation():
    checks = []
    r1 = compute_malthusian_growth(P0=10, r=0.5, K0=100, K_amplitude=20,
                                    K_period=20, t_max=100, n_points=60)
    err1 = r1["validacion_caso_K_constante"]["max_error_vs_logistico_analitico"]
    checks.append({
        "name": "malthusian_growth_vs_logistico_analitico",
        "expected": "< 1e-3",
        "got": err1,
        "passed": bool(err1 < 1e-3),
    })

    r2 = compute_technology_diffusion(M_market=1000, p_innovation=0.03,
                                       q_imitation=0.4, t_max=30, n_points=30)
    err2 = r2["max_error_vs_analitico"]
    checks.append({
        "name": "technology_diffusion_vs_analitico",
        "expected": "< 1e-3",
        "got": err2,
        "passed": bool(err2 < 1e-3),
    })

    settlements = [
        {"name": "A", "population": 500, "x": 0, "y": 0},
        {"name": "B", "population": 300, "x": 10, "y": 0},
        {"name": "C", "population": 800, "x": 5, "y": 8},
        {"name": "D", "population": 150, "x": 15, "y": 5},
    ]
    r3 = compute_trade_network(settlements=settlements, gravity_exponent=2)
    # C tiene la mayor poblacion y esta relativamente central -> hub esperado.
    # NO VERIFICADO A MANO -- confirmar con una corrida suelta antes de confiar.
    checks.append({
        "name": "trade_network_hub_identificado",
        "expected": "C",
        "got": r3["hub_identificado"],
        "passed": r3["hub_identificado"] == "C",
    })

    r4 = compute_collapse_dynamics(P0=10, R0=50, r=0.5, K_capacity=200,
                                    a_attack=0.02, h_handling=0.4,
                                    e_efficiency=0.6, m_mortality=0.3,
                                    t_max=100, n_points=60)
    # Chequeo estructural minimo: el modulo corrio y devolvio el campo de
    # analisis esperado. Umbral de "ciclo_limite_detectado" NO verificado
    # a mano -- ajustar si el valor real difiere.
    checks.append({
        "name": "collapse_dynamics_returns_analysis_fields",
        "expected": "equilibrio_analitico_nullclines y ciclo_limite_detectado presentes",
        "got": {
            "has_equilibrio": "equilibrio_analitico_nullclines" in r4,
            "has_ciclo": "ciclo_limite_detectado" in r4,
        },
        "passed": ("equilibrio_analitico_nullclines" in r4 and "ciclo_limite_detectado" in r4),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}

'''

MAIN_ANCHOR = 'if __name__ == "__main__":'

ARCHAEO_DISPATCH_OLD = (
    'def compute_archaeological_simulation(mode, **kwargs):\n'
    '    """Dispatcher unico para el tool MCP archaeological_simulation, segun \'mode\'."""\n'
    '    fns = {\n'
    '        "malthusian_growth": compute_malthusian_growth,'
)
ARCHAEO_DISPATCH_NEW = (
    'def compute_archaeological_simulation(mode, **kwargs):\n'
    '    """Dispatcher unico para el tool MCP archaeological_simulation, segun \'mode\'."""\n'
    '    if mode == "validate":\n'
    '        return _validate_archaeological_simulation()\n'
    '    fns = {\n'
    '        "malthusian_growth": compute_malthusian_growth,'
)


def patch_mode_enum(content, path):
    pattern = re.compile(
        r'("mode":\s*\{\s*"type":\s*"string",\s*"enum":\s*\[)([^\]]*)(\])'
    )
    m = pattern.search(content)
    if not m:
        raise RuntimeError(f"No encontre el enum de 'mode' en {path} -- revisar a mano.")
    inner = m.group(2)
    if '"validate"' in inner:
        print(f"  (ya tenia 'validate' en el enum de {path}, no toco nada)")
        return content
    new_inner = inner.rstrip()
    if not new_inner.endswith(","):
        new_inner += ","
    new_inner += ' "validate"'
    new_block = m.group(1) + new_inner + m.group(3)
    content = content[: m.start()] + new_block + content[m.end():]
    print(f"OK ({path}): 'validate' agregado al enum del schema.")
    return content


def patch_archaeological():
    path = "archaeological_simulation_tool.py"
    print(f"\n--- {path} ---")
    content = read(path)
    backup(path)
    content = replace_unique(content, MAIN_ANCHOR, VALIDATE_ARCHAEO + MAIN_ANCHOR, path, "insercion _validate_*")
    content = replace_unique(content, ARCHAEO_DISPATCH_OLD, ARCHAEO_DISPATCH_NEW, path, "branch validate")
    content = patch_mode_enum(content, path)
    verify_syntax(path, content)
    write(path, content)


def main():
    patch_glm()
    patch_archaeological()
    print("\nOK: fix de glm_tool + patch de archaeological_simulation_tool aplicados.")


if __name__ == "__main__":
    main()
