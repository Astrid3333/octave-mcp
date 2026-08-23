#!/usr/bin/env python3
"""
patch_server.py
Wirea multibody_dynamics_tool, particle_simulation_tool y finite_element_tool
en server.py, siguiendo el patron de la sesion:
  import -> entrada de schema en TOOLS -> bloque elif tool_name == ... dispatch

Uso:
  cp server.py server.py.bak.$(date +%s)      # backup manual adicional
  python3 patch_server.py /ruta/a/octave-mcp/server.py

Cada insercion usa un marker + assert content.count(marker) == 1 antes de escribir,
para no tocar nada si el archivo cambio de forma inesperada.
"""
import sys
import shutil
import time
import json

TOOLS_TO_WIRE = [
    {
        "name": "multibody_dynamics_tool",
        "module": "multibody_dynamics_tool",
        "description": (
            "Dinamica de cuerpos rigidos y sistemas multi-cuerpo: pendulo fisico "
            "(compound_pendulum), rotacion libre de par via ecuaciones de Euler "
            "(rigid_body_euler), manipulador/pendulo doble planar via Lagrangiano "
            "(two_link_manipulator). Validado contra formulas de libro de texto."
        ),
    },
    {
        "name": "particle_simulation_tool",
        "module": "particle_simulation_tool",
        "description": (
            "Simulacion de particulas: orbita de Kepler de dos cuerpos (kepler_orbit), "
            "colisiones elasticas en cadena 1D (elastic_collision_nbody), caminata "
            "aleatoria y recuperacion de coeficiente de difusion (random_walk_diffusion)."
        ),
    },
    {
        "name": "finite_element_tool",
        "module": "finite_element_tool",
        "description": (
            "Metodo de elementos finitos: barra axial (bar_1d), viga en voladizo "
            "Euler-Bernoulli (beam_bending), cercha plana articulada (truss_2d). "
            "Validado contra soluciones analiticas de libro de texto."
        ),
    },
]

IMPORT_MARKER = "# === OCTAVE_MCP_IMPORTS ==="
TOOLS_LIST_MARKER = "# === OCTAVE_MCP_TOOLS_SCHEMA ==="
DISPATCH_MARKER = "# === OCTAVE_MCP_DISPATCH ==="


def main():
    if len(sys.argv) != 2:
        print("uso: python3 patch_server.py /ruta/a/server.py")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    backup_path = f"{path}.bak.{int(time.time())}"
    shutil.copy2(path, backup_path)
    print(f"backup creado: {backup_path}")

    # --- 1. imports ---
    for t in TOOLS_TO_WIRE:
        import_line = f"import {t['module']}\n"
        if import_line in content:
            print(f"[skip] import de {t['module']} ya presente")
            continue
        assert content.count(IMPORT_MARKER) == 1, (
            f"marker de imports '{IMPORT_MARKER}' no encontrado o duplicado; "
            "ajusta el marker en este script antes de continuar."
        )
        content = content.replace(IMPORT_MARKER, import_line + IMPORT_MARKER, 1)

    # --- 2. entradas de schema en TOOLS ---
    for t in TOOLS_TO_WIRE:
        schema_entry = json.dumps({
            "name": t["name"],
            "description": t["description"],
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "params": {"type": "object"}
                },
                "required": ["action"]
            }
        }, ensure_ascii=False, indent=4)
        marker_check = f'"name": "{t["name"]}"'
        if marker_check in content:
            print(f"[skip] schema de {t['name']} ya presente")
            continue
        assert content.count(TOOLS_LIST_MARKER) == 1, (
            f"marker de schema '{TOOLS_LIST_MARKER}' no encontrado o duplicado."
        )
        content = content.replace(
            TOOLS_LIST_MARKER,
            schema_entry + ",\n    " + TOOLS_LIST_MARKER,
            1,
        )

    # --- 3. dispatch elif ---
    for t in TOOLS_TO_WIRE:
        dispatch_block = (
            f'    elif tool_name == "{t["name"]}":\n'
            f"        return {t['module']}.handle(arguments)\n"
        )
        if f'tool_name == "{t["name"]}"' in content:
            print(f"[skip] dispatch de {t['name']} ya presente")
            continue
        assert content.count(DISPATCH_MARKER) == 1, (
            f"marker de dispatch '{DISPATCH_MARKER}' no encontrado o duplicado."
        )
        content = content.replace(DISPATCH_MARKER, dispatch_block + DISPATCH_MARKER, 1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    print("server.py parcheado OK.")
    print("Validando sintaxis...")
    import ast
    ast.parse(content)
    print("sintaxis OK. Reiniciar el server MCP para levantar los 3 tools nuevos.")


if __name__ == "__main__":
    main()
