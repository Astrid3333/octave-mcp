#!/usr/bin/env python3
"""
wire_sdf.py
Conecta sdf_tool.py a octave-mcp/server.py:
  1. Copia el archivo del tool a ~/octave-mcp/
  2. Backup timestamped de server.py
  3. Inserta el import (anclado despues del import de advanced_probability_tool)
  4. Inserta la entrada en la lista de schemas (anclado despues de
     ADVANCED_PROBABILITY_TOOL_SCHEMA,)
  5. Inserta el bloque dispatch elif (anclado despues del bloque de
     advanced_probability), dispatcheando como "sdf_tool" (nombre completo,
     igual en schema y dispatch -- no "sdf" a secas)
  6. py_compile antes y despues de cada escritura (si falla, restaura backup)
  7. Smoke test: echo "" | timeout 90 python3 server.py (90s por el peso de
     los imports del server, no 3s -- eso es lo que dio falso timeout la
     vez pasada)

Correr desde ~/octave-mcp/:
    python3 wire_sdf.py
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
SRC_TOOL = os.path.join(HOME, "work2", "sdf_tool.py")
DST_TOOL = os.path.join(OCTAVE_DIR, "sdf_tool.py")

TS = time.strftime("%Y%m%d_%H%M%S")

IMPORT_ANCHOR = "from advanced_probability_tool import compute_advanced_probability, ADVANCED_PROBABILITY_TOOL_SCHEMA\n"
IMPORT_INSERT = "from sdf_tool import compute_sdf, SDF_TOOL_SCHEMA\n"

SCHEMA_ANCHOR = "    ADVANCED_PROBABILITY_TOOL_SCHEMA,\n"
SCHEMA_INSERT = "    SDF_TOOL_SCHEMA,\n"

DISPATCH_ANCHOR = (
    '            elif tool_name == "advanced_probability":\n'
    '                result = compute_advanced_probability(**args)\n'
    '                resp = {\n'
    '                    "jsonrpc": "2.0", "id": req_id,\n'
    '                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                }\n'
)
DISPATCH_INSERT = (
    '            elif tool_name == "sdf_tool":\n'
    '                result = compute_sdf(**args)\n'
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

    shutil.copy2(SRC_TOOL, DST_TOOL)
    print(f"OK copiado -> {DST_TOOL}")

    try:
        py_compile.compile(DST_TOOL, doraise=True)
    except py_compile.PyCompileError as e:
        fail(f"sdf_tool.py no compila: {e}")
    print("OK py_compile sdf_tool.py (pre)")

    backup_path = f"{SERVER_PY}.bak.{TS}"
    shutil.copy2(SERVER_PY, backup_path)
    print(f"OK backup -> {backup_path}")

    with open(SERVER_PY, "r", encoding="utf-8") as f:
        content = f.read()

    try:
        py_compile.compile(SERVER_PY, doraise=True)
    except py_compile.PyCompileError as e:
        fail(f"server.py original ya no compila (antes de tocar nada): {e}")
    print("OK py_compile server.py (pre, original)")

    n = content.count(IMPORT_ANCHOR)
    assert n == 1, f"ancla de import aparece {n} veces, esperaba 1"
    content = content.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_INSERT)

    n = content.count(SCHEMA_ANCHOR)
    assert n == 1, f"ancla de schema aparece {n} veces, esperaba 1"
    content = content.replace(SCHEMA_ANCHOR, SCHEMA_ANCHOR + SCHEMA_INSERT)

    n = content.count(DISPATCH_ANCHOR)
    assert n == 1, f"ancla de dispatch aparece {n} veces, esperaba 1"
    content = content.replace(DISPATCH_ANCHOR, DISPATCH_ANCHOR + DISPATCH_INSERT)

    with open(SERVER_PY, "w", encoding="utf-8") as f:
        f.write(content)
    print("OK escrito server.py con las 3 inserciones")

    try:
        py_compile.compile(SERVER_PY, doraise=True)
    except py_compile.PyCompileError as e:
        print(f"FALLO py_compile post-escritura: {e}", file=sys.stderr)
        print(f"Restaurando desde backup {backup_path}...", file=sys.stderr)
        shutil.copy2(backup_path, SERVER_PY)
        fail("server.py restaurado desde backup, revisa el error de arriba")
    print("OK py_compile server.py (post)")

    result = subprocess.run(
        f'echo "" | timeout 90 python3 -u {SERVER_PY}',
        shell=True, cwd=OCTAVE_DIR, capture_output=True, text=True,
    )
    print("--- smoke test stdout ---")
    print(result.stdout[:2000])
    print("--- smoke test stderr ---")
    print(result.stderr[:2000])
    print(f"--- smoke test returncode: {result.returncode} ---")
    print(
        "\nNota: BrokenPipeError aca es esperado (el cliente cierra stdin primero), "
        "no es un fallo del server."
    )

    print("\nListo. Para probar el tool real (no solo el smoke test):")
    print(f"""  cd {OCTAVE_DIR}
  (echo '{{"jsonrpc":"2.0","id":1,"method":"initialize","params":{{}}}}'; \\
   echo '{{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{{"name":"sdf_tool","arguments":{{"mode":"validate"}}}}}}') \\
   | timeout 60 python3 -u server.py | tail -1""")
    print("\nSi todo se ve bien, el commit deberia incluir solo:")
    print("  server.py  sdf_tool.py")
    print("(sin wire_sdf.py ni el .bak)")


if __name__ == "__main__":
    main()
