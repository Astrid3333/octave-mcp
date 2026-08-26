#!/usr/bin/env python3
"""
Agrega 'validate' al enum de MULTIVARIATE_BAYES_TOOL_SCHEMA en
multivariate_bayes_tool.py.

Contexto: la funcion validate() y la rama "validate" en el dispatch de
compute_multivariate_bayes() ya existen y ya funcionan -- la tool quedaba
SKIPPED en run_all_validations.py solo porque el schema REALMENTE registrado
(MULTIVARIATE_BAYES_TOOL_SCHEMA, via register_tool) no incluye "validate" en
su enum. El otro schema del archivo (TOOL_SCHEMA, linea ~582) si lo tiene,
pero es codigo muerto -- no lo usa ningun register_tool ni handler.

No se toca la funcion validate() ni el dispatch: ya estan completos.

Uso:
    cd ~/octave-mcp
    python3 patch_multivariate_bayes_add_validate_enum.py
"""
import ast
import datetime
import pathlib
import py_compile
import sys

TARGET = pathlib.Path("multivariate_bayes_tool.py")

if not TARGET.exists():
    print(f"ERROR: no se encuentra {TARGET} en el directorio actual.", file=sys.stderr)
    sys.exit(1)

original = TARGET.read_text(encoding="utf-8")

ANCHOR = """MULTIVARIATE_BAYES_TOOL_SCHEMA = {   'type': 'object',
    'properties': {   'mode': {   'type': 'string',
                                  'enum': [   'mvn_sample',
                                              'mvt_sample',
                                              'wishart_sample',
                                              'hierarchical',
                                              'hmc_regression',
                                              'pca_biplot',
                                              'pca_cv',
                                              'factor_analysis']},
                      'params': {'type': 'object'}},
    'required': ['mode', 'params']}"""

count = original.count(ANCHOR)
assert count == 1, f"ancla (MULTIVARIATE_BAYES_TOOL_SCHEMA) aparece {count} veces, se esperaba 1"

REPLACEMENT = """MULTIVARIATE_BAYES_TOOL_SCHEMA = {   'type': 'object',
    'properties': {   'mode': {   'type': 'string',
                                  'enum': [   'mvn_sample',
                                              'mvt_sample',
                                              'wishart_sample',
                                              'hierarchical',
                                              'hmc_regression',
                                              'pca_biplot',
                                              'pca_cv',
                                              'factor_analysis',
                                              'validate']},
                      'params': {'type': 'object'}},
    'required': ['mode', 'params']}"""

patched = original.replace(ANCHOR, REPLACEMENT, 1)

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
