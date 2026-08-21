"""
Version generalizada del patch anterior: agrega el bloque register_tool()
+ runner __main__ faltante a CUALQUIER archivo de tool huerfano (importado
en server.py pero sin register_tool()), detectando automaticamente:
  - el nombre de la variable SCHEMA (primera que matchee *_SCHEMA = {)
  - el nombre de la funcion dispatcher (primera def compute_* que tenga
    un cuerpo tipo if mode == ... / elif mode == ...)

Uso: correr DESDE ~/octave-mcp, pasando uno o mas nombres de archivo
(sin extension, igual que en el import de server.py):

  python3 patch_add_register_generic.py circular_economy_tool biodiversity_model_tool dynamic_kill_calculator_tool

Backup automatico + reporte explicito por archivo, sin asserts mudos.
No adivina el tool_name registrado: usa el nombre de archivo tal cual,
que es el mismo criterio ya confirmado en infrastructure_resilience_tool
y wildfire_risk_tool (register_tool(name="<nombre_archivo>", ...)).
"""
import sys
import re
import shutil
import pathlib
import datetime
import compileall

def patch_one(modname: str) -> bool:
    target = pathlib.Path(f"{modname}.py")
    print(f"\n=== {target} ===")
    if not target.exists():
        print(f"  ERROR: no existe {target} en el directorio actual.")
        return False

    original = target.read_text(encoding="utf-8")

    if "register_tool(" in original:
        print("  SKIP: ya tiene register_tool(), no se toca.")
        return True

    # Detectar nombre de schema: primera línea "ALGO_SCHEMA = {"
    schema_match = re.search(r"^([A-Z0-9_]+_SCHEMA)\s*=\s*\{", original, re.MULTILINE)
    if not schema_match:
        print("  ERROR: no se encontró una variable *_SCHEMA = { ... }, abortando este archivo.")
        return False
    schema_name = schema_match.group(1)

    # Detectar función dispatcher: "def compute_xxx(mode, params=None):" o similar
    dispatcher_match = re.search(
        r"^def (compute_[a-zA-Z0-9_]+)\(mode(?:,\s*params\s*=\s*None)?\):",
        original, re.MULTILINE
    )
    if not dispatcher_match:
        print("  ERROR: no se encontró 'def compute_*(mode, params=None):', abortando este archivo.")
        return False
    dispatcher_name = dispatcher_match.group(1)

    print(f"  schema detectado: {schema_name}")
    print(f"  dispatcher detectado: {dispatcher_name}")

    if '__name__ == "__main__"' in original:
        print("  NOTA: ya tiene bloque __main__ (no se duplica, se agrega solo register_tool antes).")
        has_main = True
    else:
        has_main = False

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = target.with_suffix(f".py.bak_{ts}")
    shutil.copy2(target, backup_path)
    print(f"  [backup] -> {backup_path}")

    register_block = f'''

try:
    from tool_registry import register_tool
    register_tool(
        name="{modname}",
        schema={schema_name},
        handler=lambda args: {dispatcher_name}(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass
'''

    if has_main:
        # Insertar el bloque de registro justo ANTES del if __name__ existente
        marker = '\nif __name__ == "__main__":'
        idx = original.index(marker)
        new_content = original[:idx] + register_block + original[idx:]
    else:
        main_block = f'''

if __name__ == "__main__":
    import json
    d = {dispatcher_name}("validate", {{}})
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\\nTodos los chequeos de {modname}.py pasaron OK.")
'''
        new_content = original.rstrip("\n") + "\n" + register_block.lstrip("\n") + main_block

    try:
        compile(new_content, str(target), "exec")
    except SyntaxError as e:
        print(f"  ERROR: el resultado no compila ({e}), no se escribe el archivo.")
        return False

    target.write_text(new_content, encoding="utf-8")
    print(f"  [OK] {target} actualizado. Tamaño: {len(original)} -> {len(new_content)} bytes")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 patch_add_register_generic.py modulo1 [modulo2 ...]")
        sys.exit(1)

    results = {}
    for modname in sys.argv[1:]:
        results[modname] = patch_one(modname)

    print("\n=== RESUMEN ===")
    for modname, ok in results.items():
        print(f"  {modname}: {'OK' if ok else 'FALLÓ (ver detalle arriba, sin modificar)'}")

    if not all(results.values()):
        sys.exit(1)
