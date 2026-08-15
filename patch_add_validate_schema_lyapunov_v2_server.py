#!/usr/bin/env python3
"""
Agrega "mode" (enum: validate) al schema HARDCODEADO de compute_lyapunov_v2
en server.py (linea ~271, lista TOOLS). Este schema esta duplicado respecto
a LYAPUNOV_V2_TOOL_SCHEMA en lyapunov_tool_v2.py -- es el que realmente
se expone via tools/list y el que lee run_all_validations.py para decidir
que tools tienen modo validate. Por eso el patch anterior (a la funcion)
no hizo subir el contador: la funcion soporta mode='validate', pero el
schema publicado no lo anunciaba.

No toca el dispatcher (elif tool_name == "compute_lyapunov_v2": ...) --
ese ya hace compute_lyapunov_v2(**args) y no necesita cambios.
"""
import ast
import shutil
import sys
from datetime import datetime

TARGET = "server.py"

OLD = (
    '{"name": "compute_lyapunov_v2", "description": "Calcula el exponente de '
    'Lyapunov maximo (lambda1) de un sistema dinamico (presets: chen_lee, '
    'burke_shaw, lorenz, rossler, o ecuaciones custom) para cuantificar caos. '
    'lambda1>0 confirma comportamiento caotico. Si se indica run_id, guarda la '
    'trayectoria completa en el workspace (util para graficar el atractor '
    'despues con plot_tool).", "inputSchema": {"type": "object", "properties": '
    '{"system": {"type": "string"}, "custom_equations": {"type": "string"}, '
    '"custom_params": {"type": "object"}, "y0": {"type": "array"}, "dt": '
    '{"type": "number"}, "n_steps": {"type": "integer"}, "d0": {"type": '
    '"number"}, "run_id": {"type": "string"}, "save_trajectory_every": '
    '{"type": "integer"}}}},'
)

NEW = (
    '{"name": "compute_lyapunov_v2", "description": "Calcula el exponente de '
    'Lyapunov maximo (lambda1) de un sistema dinamico (presets: chen_lee, '
    'burke_shaw, lorenz, rossler, o ecuaciones custom) para cuantificar caos. '
    'lambda1>0 confirma comportamiento caotico. Si se indica run_id, guarda la '
    'trayectoria completa en el workspace (util para graficar el atractor '
    'despues con plot_tool).", "inputSchema": {"type": "object", "properties": '
    '{"system": {"type": "string"}, "custom_equations": {"type": "string"}, '
    '"custom_params": {"type": "object"}, "y0": {"type": "array"}, "dt": '
    '{"type": "number"}, "n_steps": {"type": "integer"}, "d0": {"type": '
    '"number"}, "run_id": {"type": "string"}, "save_trajectory_every": '
    '{"type": "integer"}, "mode": {"type": "string", "enum": ["validate"], '
    '"description": "Si es \'validate\', ejecuta el autocheque interno '
    '(sistemas lineales 3D con lambda1 exacto conocido) e ignora el resto de '
    'los parametros."}}}},'
)


def main():
    with open(TARGET, encoding="utf-8") as f:
        src = f.read()

    count = src.count(OLD)
    assert count == 1, f"[schema compute_lyapunov_v2 en server.py] se esperaba 1 ocurrencia, se encontraron {count} -- revisar a mano."

    backup = f"{TARGET}.bak.{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy(TARGET, backup)

    new_src = src.replace(OLD, NEW, 1)

    try:
        ast.parse(new_src)
    except SyntaxError as e:
        print(f"ERROR: el resultado no parsea como Python valido: {e}", file=sys.stderr)
        sys.exit(1)

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(new_src)

    print(f"Patch aplicado OK. Backup: {backup}")
    print("Confirmar con: grep -n 'compute_lyapunov_v2' server.py  (deberia mostrar \"mode\" en el inputSchema)")
    print("Y luego: git diff server.py")


if __name__ == "__main__":
    main()
