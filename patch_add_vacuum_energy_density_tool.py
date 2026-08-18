#!/usr/bin/env python3
"""
patch_add_vacuum_energy_density_tool.py

Registra vacuum_energy_density_tool.py como tool MCP real, siguiendo el
patron de auto-registro via tool_registry (una linea en server.py, sin
tocar TOOLS ni el dispatch elif).

Correr desde la raiz del repo, DESPUES de copiar vacuum_energy_density_tool.py
a la raiz:
    python3 patch_add_vacuum_energy_density_tool.py

Es idempotente: si ya aplico el patch antes, no vuelve a tocar nada.
"""
import sys

TOOL_FILE = "vacuum_energy_density_tool.py"
SERVER_FILE = "server.py"


def patch_server_file():
    with open(SERVER_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    import_line = "import vacuum_energy_density_tool  # auto-registra via tool_registry, no requiere mas ediciones\n"

    if import_line in content:
        print(f"[skip] {SERVER_FILE} ya importa vacuum_energy_density_tool, no se toca.")
        return

    # anchor: la linea de import del patch anterior (scalar_field_cosmology_tool),
    # si existe; si no, cae al anchor de tool_catalog_tool como en el patch previo.
    anchor_candidates = [
        "import scalar_field_cosmology_tool  # auto-registra via tool_registry, no requiere mas ediciones\n",
        "import tool_catalog_tool  # auto-registra via tool_registry, no requiere mas ediciones\n",
    ]
    anchor = next((a for a in anchor_candidates if a in content), None)
    if anchor is None:
        sys.exit(f"[error] no encontre ningun anchor de import conocido en {SERVER_FILE}, aborto.")

    content = content.replace(anchor, anchor + import_line, 1)

    with open(SERVER_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[ok] {SERVER_FILE} parchado (1 linea de import agregada).")


def check_tool_file():
    try:
        with open(TOOL_FILE, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        sys.exit(
            f"[error] no encuentro {TOOL_FILE} en el directorio actual. "
            f"Copialo a la raiz del repo antes de correr este patch."
        )
    if "register_tool(" not in content:
        sys.exit(
            f"[error] {TOOL_FILE} no tiene register_tool() -- parece una version "
            f"vieja del archivo, volve a descargarlo."
        )
    print(f"[ok] {TOOL_FILE} ya se auto-registra (nada que tocar en este archivo).")


if __name__ == "__main__":
    check_tool_file()
    patch_server_file()
    print("Listo. Revisa con: git diff")
