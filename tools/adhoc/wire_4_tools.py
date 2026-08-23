"""
Wirea wave_propagation_tool, dispersion_relation_tool, audio_processing_tool
y time_frequency_tool en server.py, en un solo patch de 3 anclas (import,
TOOLS list, dispatcher), mismo patron que fractional_fourier_tool.

Uso (desde ~/octave-mcp):
    cp ~/Descargas/wave_propagation_tool.py .
    cp ~/Descargas/dispersion_relation_tool.py .
    cp ~/Descargas/audio_processing_tool.py .
    cp ~/Descargas/time_frequency_tool.py .
    cp ~/Descargas/wire_4_tools.py .
    python3 wire_4_tools.py
"""
import ast
import shutil
import datetime

PATH = "server.py"

TOOLS = [
    ("wave_propagation_tool", "compute_wave_propagation", "WAVE_PROPAGATION_TOOL_SCHEMA"),
    ("dispersion_relation_tool", "compute_dispersion_relation", "DISPERSION_RELATION_TOOL_SCHEMA"),
    ("audio_processing_tool", "compute_audio_processing", "AUDIO_PROCESSING_TOOL_SCHEMA"),
    ("time_frequency_tool", "compute_time_frequency", "TIME_FREQUENCY_TOOL_SCHEMA"),
]

IMPORT_ANCHOR = (
    "from fractional_fourier_tool import compute_fractional_fourier, "
    "FRACTIONAL_FOURIER_TOOL_SCHEMA\n"
)
TOOLS_ANCHOR = "    FRACTIONAL_FOURIER_TOOL_SCHEMA,\n"
DISPATCH_ANCHOR = (
    '            elif tool_name == "fractional_fourier_tool":\n'
    "                result = compute_fractional_fourier(args.get(\"mode\"), args.get(\"params\"))\n"
)


def fail(msg):
    raise SystemExit(f"ABORTADO: {msg}")


def main():
    with open(PATH, "r") as f:
        content = f.read()

    backup = f"{PATH}.bak.{datetime.datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy(PATH, backup)
    print(f"Backup: {backup}")

    for anchor, label in [
        (IMPORT_ANCHOR, "import"),
        (TOOLS_ANCHOR, "TOOLS list"),
        (DISPATCH_ANCHOR, "dispatcher"),
    ]:
        n = content.count(anchor)
        if n != 1:
            fail(f"ancla '{label}' encontrada {n} veces (se esperaba 1): {anchor!r}")

    # --- 1) imports ---
    import_block = "".join(
        f"from {mod} import {fn}, {schema}\n" for mod, fn, schema in TOOLS
    )
    content = content.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + import_block)

    # --- 2) TOOLS list ---
    tools_block = "".join(f"    {schema},\n" for _, _, schema in TOOLS)
    content = content.replace(TOOLS_ANCHOR, TOOLS_ANCHOR + tools_block)

    # --- 3) dispatcher ---
    dispatch_block = ""
    for mod, fn, _ in TOOLS:
        dispatch_block += (
            f'            elif tool_name == "{mod}":\n'
            f'                result = {fn}(args.get("mode"), args.get("params"))\n'
        )
    content = content.replace(DISPATCH_ANCHOR, DISPATCH_ANCHOR + dispatch_block)

    try:
        ast.parse(content)
    except SyntaxError as e:
        fail(f"ast.parse fallo tras el patch: {e}")

    with open(PATH, "w") as f:
        f.write(content)

    print("OK: 3 anclas x 4 tools aplicadas, ast.parse valido")
    for mod, fn, schema in TOOLS:
        print(f"  - {mod}  ({fn}, {schema})")


if __name__ == "__main__":
    main()
