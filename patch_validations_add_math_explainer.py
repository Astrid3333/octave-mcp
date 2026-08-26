#!/usr/bin/env python3
"""
patch_validations_add_math_explainer.py
Mapea math_explainer en run_all_validations.py para que el pre-push hook
lo detecte y lo valide via source_tool="validate" (en vez del default mode="validate").

Requiere que patch_math_explainer_add_selftest.py ya se haya aplicado
(math_explainer_tool.py debe tener source_tool="validate" funcionando)
-- si no, este mapeo hace que el hook llame a algo que todavia no existe
y la validacion va a fallar con un error claro, no un crash silencioso.
"""
import shutil
import datetime

PATH = "run_all_validations.py"

with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

# --- Anchor 1: ALTERNATE_VALIDATE_MODE ---
anchor1 = (
    '    "ethnomath": "validate",\n'
    '    "ethnomath2": "validate",\n'
    '    # NOTA (2026-08-20): plague_sir, settlement_clusters, historical_extractor'
)
n1 = content.count(anchor1)
print(f"{PATH}: ocurrencias del ancla 1 (ALTERNATE_VALIDATE_MODE) = {n1}")
assert n1 == 1, "ancla 1 no encontrada o no es unica -- abortando, no se toco el archivo"

replacement1 = (
    '    "ethnomath": "validate",\n'
    '    "ethnomath2": "validate",\n'
    '    "math_explainer": "validate",\n'
    '    # NOTA (2026-08-20): plague_sir, settlement_clusters, historical_extractor'
)

# --- Anchor 2: ALTERNATE_VALIDATE_PARAM_NAME ---
anchor2 = (
    '    "ethnomath": "preset",\n'
    '    "ethnomath2": "preset",\n'
    '}'
)
n2 = content.count(anchor2)
print(f"{PATH}: ocurrencias del ancla 2 (ALTERNATE_VALIDATE_PARAM_NAME) = {n2}")
assert n2 == 1, "ancla 2 no encontrada o no es unica -- abortando, no se toco el archivo"

replacement2 = (
    '    "ethnomath": "preset",\n'
    '    "ethnomath2": "preset",\n'
    '    "math_explainer": "source_tool",\n'
    '}'
)

# --- Aplicar ---
new_content = content.replace(anchor1, replacement1, 1)
new_content = new_content.replace(anchor2, replacement2, 1)

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = f"{PATH}.bak_{ts}"
shutil.copy(PATH, backup_path)
print(f"backup: {backup_path}")

with open(PATH, "w", encoding="utf-8") as f:
    f.write(new_content)

print("aplicado OK")
