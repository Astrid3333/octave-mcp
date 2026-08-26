#!/usr/bin/env python3
"""
Agrega el enum ["umap", "tsne", "validate"] a la propiedad "method" del
schema de numeral_systems_embedding, que esta hardcodeado como dict literal
en server.py (no usa register_tool ni NUMERAL_EMBEDDING_SCHEMA -- ambos
existen en numeral_systems_embedding_tool.py pero son codigo muerto, no
los referencia nadie).

Contexto: compute_numeral_systems_embedding(method="validate") ya existe y
ya funciona (despacha a _validate_numeral_systems_embedding(), formato
correcto: checks/validation_passed/n_checks). La tool quedaba SKIPPED solo
porque el schema real (el de server.py) no declaraba ningun enum en
"method" -- ni siquiera umap/tsne, mucho menos validate.

No se toca numeral_systems_embedding_tool.py. No se actualiza la
descripcion desactualizada del dict de server.py (dataset viejo de 7
sistemas vs. los 11 actuales) -- queda como mejora aparte si se quiere.

Uso:
    cd ~/octave-mcp
    python3 patch_numeral_systems_add_validate_enum.py
"""
import ast
import datetime
import pathlib
import py_compile
import sys

TARGET = pathlib.Path("server.py")

if not TARGET.exists():
    print(f"ERROR: no se encuentra {TARGET} en el directorio actual.", file=sys.stderr)
    sys.exit(1)

original = TARGET.read_text(encoding="utf-8")

ANCHOR = (
    '"properties": {"method": {"type": "string"}, "extra_systems": {"type": "array"}, '
    '"n_neighbors": {"type": "integer"}, "perplexity": {"type": "number"}, '
    '"random_state": {"type": "integer"}, "run_id": {"type": "string"}}}}'
)
count = original.count(ANCHOR)
assert count == 1, f"ancla (properties numeral_systems_embedding) aparece {count} veces, se esperaba 1"

REPLACEMENT = (
    '"properties": {"method": {"type": "string", "enum": ["umap", "tsne", "validate"]}, '
    '"extra_systems": {"type": "array"}, '
    '"n_neighbors": {"type": "integer"}, "perplexity": {"type": "number"}, '
    '"random_state": {"type": "integer"}, "run_id": {"type": "string"}}}}'
)

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
