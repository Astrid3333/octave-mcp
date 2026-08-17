"""
fix_handlers.py

Corrige la firma de _handler en gait_analysis_tool.py y socket_topology_tool.py:
el dispatch real de tool_registry llama al handler con el dict de argumentos
completo como UN SOLO parametro posicional (no expandido via **kwargs), asi
que _handler debe aceptar ese dict y desempacarlo el mismo (extrayendo 'mode'
y, si viene, un sub-dict 'params' que el harness de validacion manda vacio
por defecto).

Uso: correr desde ~/octave-mcp (donde ya estan los dos archivos wireados):
    python3 fix_handlers.py
"""
import ast
import shutil
from datetime import datetime

FIXES = {
    "gait_analysis_tool.py": (
        'def _handler(mode="validate", **kwargs):\n'
        '    return compute_gait_analysis(mode=mode, **kwargs)',
        'def _handler(args):\n'
        '    args = dict(args or {})\n'
        '    mode = args.pop("mode", "validate")\n'
        '    params = args.pop("params", None) or {}\n'
        '    merged = {**params, **args}\n'
        '    return compute_gait_analysis(mode=mode, **merged)',
    ),
    "socket_topology_tool.py": (
        'def _handler(mode="validate", **kwargs):\n'
        '    return compute_socket_topology(mode=mode, **kwargs)',
        'def _handler(args):\n'
        '    args = dict(args or {})\n'
        '    mode = args.pop("mode", "validate")\n'
        '    params = args.pop("params", None) or {}\n'
        '    merged = {**params, **args}\n'
        '    return compute_socket_topology(mode=mode, **merged)',
    ),
}

for path, (old, new) in FIXES.items():
    with open(path) as f:
        content = f.read()
    if old not in content:
        if new in content:
            print(f"{path}: ya tiene el fix aplicado -- nada que hacer.")
            continue
        raise SystemExit(f"{path}: no encontre el bloque _handler esperado -- revisar manualmente.")
    backup = f"{path}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(path, backup)
    new_content = content.replace(old, new)
    ast.parse(new_content)
    with open(path, "w") as f:
        f.write(new_content)
    print(f"{path}: _handler corregido (backup en {backup}), sintaxis OK")

print("\nListo. Ahora correr de nuevo run_all_validations.py")
