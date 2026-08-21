"""
Patch: agrega el bloque de registro (register_tool) y el runner __main__
faltantes en infrastructure_resilience_tool.py, calcando el patron exacto
de wildfire_risk_tool.py (via tool_registry, try/except ImportError, mismo
formato del bloque __main__ con validate + assert).

Uso: correr DESDE ~/octave-mcp (necesita el archivo real en el cwd).
Hace backup automático antes de tocar nada y reporta explícitamente qué
insertó, sin asserts mudos.
"""
import shutil
import re
import sys
import pathlib

TARGET = pathlib.Path("infrastructure_resilience_tool.py")

if not TARGET.exists():
    print(f"ERROR: no se encontro {TARGET} en el directorio actual ({pathlib.Path.cwd()}).")
    print("Corré este script desde ~/octave-mcp.")
    sys.exit(1)

original = TARGET.read_text(encoding="utf-8")

# Backup con timestamp explícito, nunca pisa un backup anterior
import datetime
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = TARGET.with_suffix(f".py.bak_{ts}")
shutil.copy2(TARGET, backup_path)
print(f"[backup] {TARGET} -> {backup_path}")

# Sanity checks explícitos antes de tocar nada
checks = {
    "tiene_dispatcher": "def compute_infrastructure_resilience(mode, params=None):" in original,
    "no_tiene_register_ya": "register_tool(" not in original,
    "no_tiene_main_ya": '__name__ == "__main__"' not in original,
    "tiene_schema_name": "INFRASTRUCTURE_RESILIENCE_TOOL_SCHEMA" in original,
}
print("[checks pre-patch]")
for name, ok in checks.items():
    print(f"  {name}: {'OK' if ok else 'FALLO'}")

if not all(checks.values()):
    print("\nERROR: no se cumplen las precondiciones esperadas, abortando sin tocar el archivo.")
    sys.exit(1)

# Bloque a insertar, calcado del patrón real de wildfire_risk_tool.py
block = '''

try:
    from tool_registry import register_tool
    register_tool(
        name="infrastructure_resilience_tool",
        schema=INFRASTRUCTURE_RESILIENCE_TOOL_SCHEMA,
        handler=lambda args: compute_infrastructure_resilience(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    d = compute_infrastructure_resilience("validate", {})
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\\nTodos los chequeos de infrastructure_resilience_tool.py pasaron OK.")
'''

new_content = original.rstrip("\n") + "\n" + block.lstrip("\n")

# Sanity: el archivo resultante debe compilar como Python válido
try:
    compile(new_content, str(TARGET), "exec")
except SyntaxError as e:
    print(f"\nERROR: el resultado del patch no compila: {e}")
    print("Restaurando desde backup, no se modifica el archivo original.")
    sys.exit(1)

TARGET.write_text(new_content, encoding="utf-8")

print(f"\n[OK] {TARGET} actualizado. Bloque insertado:")
print(block)
print(f"Tamaño: {len(original)} -> {len(new_content)} bytes")
print(f"\nSiguiente paso: correr 'python3 {TARGET}' solo, luego run_all_validations.py completo.")
