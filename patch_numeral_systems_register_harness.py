#!/usr/bin/env python3
"""
Registra numeral_systems_embedding en el harness run_all_validations.py.

Contexto completo:
  - compute_numeral_systems_embedding(method="validate") ya existe y ya
    funciona (_validate_numeral_systems_embedding, formato correcto).
  - El schema real (hardcodeado en server.py) usa el parametro "method",
    no "mode" -- el detector automatico de build_requests() SIEMPRE mira
    properties.mode.enum, asi que nunca la va a encontrar sola, sin
    importar que el enum de "method" ya incluya "validate" (patch anterior).
  - La firma de compute_numeral_systems_embedding no acepta un kwarg
    "params" (ni **kwargs) -- el payload estandar {"mode":..., "params":{}}
    le tiraria TypeError.

Este patch agrega las 3 entradas necesarias:
  1) ALTERNATE_VALIDATE_MODE["numeral_systems_embedding"] = "validate"
  2) ALTERNATE_VALIDATE_PARAM_NAME["numeral_systems_embedding"] = "method"
  3) "numeral_systems_embedding" en FLAT_SIGNATURE_TOOLS

No se toca numeral_systems_embedding_tool.py ni server.py en este patch.

Uso:
    cd ~/octave-mcp
    python3 patch_numeral_systems_register_harness.py
"""
import ast
import datetime
import pathlib
import py_compile
import sys

TARGET = pathlib.Path("run_all_validations.py")

if not TARGET.exists():
    print(f"ERROR: no se encuentra {TARGET} en el directorio actual.", file=sys.stderr)
    sys.exit(1)

original = TARGET.read_text(encoding="utf-8")
patched = original

# ---------------------------------------------------------------------------
# 1) ALTERNATE_VALIDATE_MODE
# ---------------------------------------------------------------------------
ANCHOR_1 = '''    "semantic_bridge": "validate",
    # NOTA (2026-08-20):'''
count_1 = patched.count(ANCHOR_1)
assert count_1 == 1, f"ancla 1 (ALTERNATE_VALIDATE_MODE semantic_bridge) aparece {count_1} veces, se esperaba 1"

REPLACEMENT_1 = '''    "semantic_bridge": "validate",
    "numeral_systems_embedding": "validate",
    # NOTA (2026-08-20):'''
patched = patched.replace(ANCHOR_1, REPLACEMENT_1, 1)

# ---------------------------------------------------------------------------
# 2) ALTERNATE_VALIDATE_PARAM_NAME
# ---------------------------------------------------------------------------
ANCHOR_2 = '''    "math_explainer": "source_tool",
}'''
count_2 = patched.count(ANCHOR_2)
assert count_2 == 1, f"ancla 2 (ALTERNATE_VALIDATE_PARAM_NAME math_explainer) aparece {count_2} veces, se esperaba 1"

REPLACEMENT_2 = '''    "math_explainer": "source_tool",
    "numeral_systems_embedding": "method",
}'''
patched = patched.replace(ANCHOR_2, REPLACEMENT_2, 1)

# ---------------------------------------------------------------------------
# 3) FLAT_SIGNATURE_TOOLS
# ---------------------------------------------------------------------------
ANCHOR_3 = '    "entropy_structure", "ethnomath", "ethnomath2", "math_explainer",}'
count_3 = patched.count(ANCHOR_3)
assert count_3 == 1, f"ancla 3 (FLAT_SIGNATURE_TOOLS cierre) aparece {count_3} veces, se esperaba 1"

REPLACEMENT_3 = '    "entropy_structure", "ethnomath", "ethnomath2", "math_explainer", "numeral_systems_embedding",}'
patched = patched.replace(ANCHOR_3, REPLACEMENT_3, 1)

# ---------------------------------------------------------------------------
# Validar sintaxis antes de escribir
# ---------------------------------------------------------------------------
try:
    ast.parse(patched)
except SyntaxError as e:
    print(f"ERROR: el resultado parcheado no compila (ast.parse): {e}", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Backup + escritura
# ---------------------------------------------------------------------------
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = TARGET.with_name(f"{TARGET.name}.bak_{timestamp}")
backup_path.write_text(original, encoding="utf-8")
print(f"backup: {backup_path}")

TARGET.write_text(patched, encoding="utf-8")
print("aplicado OK")

py_compile.compile(str(TARGET), doraise=True)
print("py_compile OK")
