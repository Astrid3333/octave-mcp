#!/usr/bin/env python3
"""
wire_advanced_probability.py
Conecta advanced_probability_tool.py a octave-mcp/server.py:
  1. Copia el archivo del tool a ~/octave-mcp/
  2. Backup timestamped de server.py
  3. Inserta el import (anclado despues del import de stochastic_processes)
  4. Inserta la entrada en la lista de schemas (anclado despues de
     STOCHASTIC_PROCESSES_TOOL_SCHEMA,)
  5. Inserta el bloque dispatch elif (anclado despues del bloque de
     stochastic_processes)
  6. py_compile antes y despues de cada escritura
  7. Smoke test: echo "" | timeout 3 python3 server.py

Correr desde ~/octave-mcp/:
    python3 wire_advanced_probability.py
"""
import os
import shutil
import subprocess
import sys
import time
import py_compile

HOME = os.path.expanduser("~")
OCTAVE_DIR = os.path.join(HOME, "octave-mcp")
SERVER_PY = os.path.join(OCTAVE_DIR, "server.py")
SRC_TOOL = os.path.join(HOME, "work2", "advanced_probability_tool.py")
DST_TOOL = os.path.join(OCTAVE_DIR, "advanced_probability_tool.py")

TS = time.strftime("%Y%m%d_%H%M%S")

IMPORT_ANCHOR = "from stochastic_processes_tool import compute_stochastic_processes, STOCHASTIC_PROCESSES_TOOL_SCHEMA\n"
IMPORT_INSERT = "from advanced_probability_tool import compute_advanced_probability, ADVANCED_PROBABILITY_TOOL_SCHEMA\n"

SCHEMA_ANCHOR = "    STOCHASTIC_PROCESSES_TOOL_SCHEMA,\n"
SCHEMA_INSERT = "    ADVANCED_PROBABILITY_TOOL_SCHEMA,\n"

DISPATCH_ANCHOR = (
    '            elif tool_name == "stochastic_processes":\n'
    '                result = compute_stochastic_processes(**args)\n'
    '                resp = {\n'
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                }\n'
)
DISPATCH_INSERT = (
    '            elif tool_name == "advanced_probability":\n'
    '                result = compute_advanced_probability(**args)\n'
    '                resp = {\n'
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                }\n'
)


def fail(msg):
    print(f"FALLO: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    if not os.path.isfile(SERVER_PY):
        fail(f"no encuentro {SERVER_PY} -- corre este script desde ~/octave-mcp/")
    if not os.path.isfile(SRC_TOOL):
        fail(f"no encuentro {SRC_TOOL} -- ajusta SRC_TOOL si el archivo esta en otro lado")

    # 1. copiar el tool
    shutil.copy2(SRC_TOOL, DST_TOOL)
    print(f"OK copiado -> {DST_TOOL}")

    # validar que el tool compila standalone antes de tocar server.py
    try:
        py_compile.compile(DST_TOOL, doraise=True)
    except py_compile.PyCompileError as e:
        fail(f"advanced_probability_tool.py no compila: {e}")
    print("OK py_compile advanced_probability_tool.py (pre)")

    # 2. backup timestamped de server.py
    backup_path = f"{SERVER_PY}.bak.{TS}"
    shutil.copy2(SERVER_PY, backup_path)
    print(f"OK backup -> {backup_path}")

    with open(SERVER_PY, "r", encoding="utf-8") as f:
        content = f.read()

    # py_compile server.py original, por las dudas
    try:
        py_compile.compile(SERVER_PY, doraise=True)
    except py_compile.PyCompileError as e:
        fail(f"server.py original ya no compila (antes de tocar nada): {e}")
    print("OK py_compile server.py (pre, original)")

    # 3. insertar import
    n = content.count(IMPORT_ANCHOR)
    assert n == 1, f"ancla de import aparece {n} veces, esperaba 1"
    content = content.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_INSERT)

    # 4. insertar entrada de schema
    n = content.count(SCHEMA_ANCHOR)
    assert n == 1, f"ancla de schema aparece {n} veces, esperaba 1"
    content = content.replace(SCHEMA_ANCHOR, SCHEMA_ANCHOR + SCHEMA_INSERT)

    # 5. insertar bloque dispatch
    n = content.count(DISPATCH_ANCHOR)
    assert n == 1, f"ancla de dispatch aparece {n} veces, esperaba 1"
    content = content.replace(DISPATCH_ANCHOR, DISPATCH_ANCHOR + DISPATCH_INSERT)

    with open(SERVER_PY, "w", encoding="utf-8") as f:
        f.write(content)
    print("OK escrito server.py con las 3 inserciones")

    # 6. py_compile despues
    try:
        py_compile.compile(SERVER_PY, doraise=True)
    except py_compile.PyCompileError as e:
        print(f"FALLO py_compile post-escritura: {e}", file=sys.stderr)
        print(f"Restaurando desde backup {backup_path}...", file=sys.stderr)
        shutil.copy2(backup_path, SERVER_PY)
        fail("server.py restaurado desde backup, revisa el error de arriba")
    print("OK py_compile server.py (post)")

    # 7. smoke test
    result = subprocess.run(
        f'echo "" | timeout 3 python3 {SERVER_PY}',
        shell=True, cwd=OCTAVE_DIR, capture_output=True, text=True,
    )
    print("--- smoke test stdout ---")
    print(result.stdout[:2000])
    print("--- smoke test stderr ---")
    print(result.stderr[:2000])
    print(f"--- smoke test returncode: {result.returncode} ---")
    print(
        "\nNota: BrokenPipeError aca es esperado (el cliente cierra stdin primero), "
        "no es un fallo del server -- ya lo confirmamos antes."
    )

    print("\nListo. Verifica manualmente:")
    print(f"  grep -n advanced_probability {SERVER_PY}")
    print("Si todo se ve bien, el commit deberia incluir solo:")
    print("  server.py  advanced_probability_tool.py")
    print("(sin wire_advanced_probability.py ni el .bak)")


if __name__ == "__main__":
    main()
