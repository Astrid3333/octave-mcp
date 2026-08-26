#!/usr/bin/env python3
"""
patch_validations_add_math_explainer_flatsig.py
Agrega math_explainer a FLAT_SIGNATURE_TOOLS en run_all_validations.py.

Motivo: el push anterior confirmo en la practica que el harness real SI
manda {"source_tool": "validate", "params": {}} (no solo {"source_tool":
"validate"} como se asumio al mirar build_requests parcialmente). Como
interpret_and_explain(source_tool, result=None, level="tecnico") no acepta
un kwarg "params", explota con TypeError. Mismo fix que ya se uso para
ethnomath, levant, ancient_calculator, etc.: FLAT_SIGNATURE_TOOLS le dice
al harness que omita "params" del payload para esta tool especifica.
"""
import shutil
import datetime

PATH = "run_all_validations.py"

with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

anchor = (
    '    "entropy_structure", "ethnomath", "ethnomath2",}'
)
n = content.count(anchor)
print(f"{PATH}: ocurrencias del ancla (FLAT_SIGNATURE_TOOLS) = {n}")
assert n == 1, "ancla no encontrada o no es unica -- abortando, no se toco el archivo"

replacement = (
    '    "entropy_structure", "ethnomath", "ethnomath2", "math_explainer",}'
)

new_content = content.replace(anchor, replacement, 1)

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = f"{PATH}.bak_{ts}"
shutil.copy(PATH, backup_path)
print(f"backup: {backup_path}")

with open(PATH, "w", encoding="utf-8") as f:
    f.write(new_content)

print("aplicado OK")
