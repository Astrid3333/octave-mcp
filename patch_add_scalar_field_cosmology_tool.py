#!/usr/bin/env python3
"""
patch_add_scalar_field_cosmology_tool.py

Registra scalar_field_cosmology_tool.py como tool MCP real, siguiendo el
patron de auto-registro via tool_registry (una linea en server.py, sin
tocar TOOLS ni el dispatch elif).

Correr desde la raiz del repo:
    python3 patch_add_scalar_field_cosmology_tool.py

Es idempotente: si ya aplico el patch antes, no vuelve a tocar nada.
"""
import re
import sys

TOOL_FILE = "scalar_field_cosmology_tool.py"
SERVER_FILE = "server.py"


def patch_tool_file():
    with open(TOOL_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    if "register_tool(" in content:
        print(f"[skip] {TOOL_FILE} ya tiene register_tool(), no se toca.")
        return

    # 1) agregar el import de register_tool despues de los imports existentes
    anchor_import = "from scipy.integrate import solve_ivp\n"
    if anchor_import not in content:
        sys.exit(f"[error] no encontre el anchor de import en {TOOL_FILE}, aborto.")
    content = content.replace(
        anchor_import,
        anchor_import + "from tool_registry import register_tool\n",
        1,
    )

    # 2) agregar la llamada a register_tool justo antes de if __name__ == "__main__":
    anchor_main = 'if __name__ == "__main__":'
    if anchor_main not in content:
        sys.exit(f"[error] no encontre el anchor de __main__ en {TOOL_FILE}, aborto.")

    registration = (
        "register_tool(\n"
        '    name="scalar_field_cosmology_tool",\n'
        "    schema=SCALAR_FIELD_COSMOLOGY_TOOL_SCHEMA,\n"
        "    handler=lambda args: compute_scalar_field_cosmology_tool(\n"
        '        args.get("mode"), args.get("params")\n'
        "    ),\n"
        ")\n\n\n"
    )
    content = content.replace(anchor_main, registration + anchor_main, 1)

    with open(TOOL_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[ok] {TOOL_FILE} parchado (import + register_tool).")


def patch_server_file():
    with open(SERVER_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    import_line = "import scalar_field_cosmology_tool  # auto-registra via tool_registry, no requiere mas ediciones\n"

    if import_line in content:
        print(f"[skip] {SERVER_FILE} ya importa scalar_field_cosmology_tool, no se toca.")
        return

    # anchor: la ultima linea de import de este mismo estilo antes del bloque
    # de imports 'from ..._tool import ...' explicitos de cosmologia
    anchor = "import tool_catalog_tool  # auto-registra via tool_registry, no requiere mas ediciones\n"
    if anchor not in content:
        sys.exit(f"[error] no encontre el anchor de import en {SERVER_FILE}, aborto.")

    content = content.replace(anchor, anchor + import_line, 1)

    with open(SERVER_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[ok] {SERVER_FILE} parchado (1 linea de import agregada).")


if __name__ == "__main__":
    patch_tool_file()
    patch_server_file()
    print("Listo. Revisa con: git diff")
