#!/usr/bin/env python3
"""
patch_validations_add_semantic_bridge.py
Mapea semantic_bridge en run_all_validations.py.

semantic_bridge_tool.py ya tiene mode="validate" implementado y funcionando
(devuelve {"checks": [...], "validation_passed": bool}, coincide con
VALIDATION_FIELD_ALIASES). El unico motivo por el que quedaba SKIPPED es
que su TOOL_SCHEMA declara "mode": {"type": "string"} SIN enum -- el
detector automatico busca "validate" en el enum de mode, y como no hay
enum en absoluto, cae al fallback ALTERNATE_VALIDATE_MODE, donde
semantic_bridge no estaba listada. No hace falta tocar el schema de
semantic_bridge_tool.py ni su codigo: alcanza con este mapeo.

El nombre real del parametro ya es "mode" (no preset/topic/etc.), asi
que no hace falta tocar ALTERNATE_VALIDATE_PARAM_NAME. El handler usa
args.get("params") en vez de **args, asi que tampoco hace falta
FLAT_SIGNATURE_TOOLS.
"""
import shutil
import datetime

PATH = "run_all_validations.py"

with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

anchor = (
    '    "math_explainer": "validate",\n'
    '    # NOTA (2026-08-20): plague_sir, settlement_clusters, historical_extractor'
)
n = content.count(anchor)
print(f"{PATH}: ocurrencias del ancla (ALTERNATE_VALIDATE_MODE) = {n}")
assert n == 1, "ancla no encontrada o no es unica -- abortando, no se toco el archivo"

replacement = (
    '    "math_explainer": "validate",\n'
    '    "semantic_bridge": "validate",\n'
    '    # NOTA (2026-08-20): plague_sir, settlement_clusters, historical_extractor'
)

new_content = content.replace(anchor, replacement, 1)

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = f"{PATH}.bak_{ts}"
shutil.copy(PATH, backup_path)
print(f"backup: {backup_path}")

with open(PATH, "w", encoding="utf-8") as f:
    f.write(new_content)

print("aplicado OK")
