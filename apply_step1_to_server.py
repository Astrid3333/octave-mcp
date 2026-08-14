#!/usr/bin/env python3
"""
apply_step1_to_server.py

Aplica a server.py los 4 cambios puntuales del Paso 1 (registro automatico
de tools). No toca nada mas del archivo. Hace un backup automatico antes
de escribir.

Uso (parado en la carpeta del repo, junto a server.py):
    python3 apply_step1_to_server.py

Si algun cambio no matchea exactamente (por ejemplo porque server.py ya
fue editado desde que se genero este script), el script aborta ANTES de
escribir nada y te dice cual de los 4 cambios fallo.
"""
import sys
import shutil
import datetime

PATH = "server.py"

CHANGES = [
    # 1) importar tool_registry
    (
        "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
        "from lyapunov_tool import compute_lyapunov_exponent, LYAPUNOV_TOOL_SCHEMA",
        "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
        "import tool_registry\n"
        "from lyapunov_tool import compute_lyapunov_exponent, LYAPUNOV_TOOL_SCHEMA",
    ),
    # 2) sacar los 2 schemas migrados de la lista TOOLS legacy
    (
        "    FRACTIONAL_FOURIER_TOOL_SCHEMA,\n"
        "    WAVE_PROPAGATION_TOOL_SCHEMA,\n"
        "    DISPERSION_RELATION_TOOL_SCHEMA,",
        "    DISPERSION_RELATION_TOOL_SCHEMA,",
    ),
    # 3) agregar los schemas del registro al final de TOOLS
    (
        '    {"name": "early_warning_tool", "description": "Analisis de series '
        'temporales para alertas tempranas: threshold_crossing (cruce de umbrales '
        'tipo semaforo con proyeccion de tiempo hasta el proximo umbral), '
        'trend_analysis (regresion lineal, pendiente y R2), rate_of_change_alert '
        '(tasa de cambio y deteccion de subidas/bajadas criticas), '
        'moving_average_anomaly (deteccion de anomalias contra media movil '
        'trailing).", "inputSchema": {"type": "object", "properties": {"mode": '
        '{"type": "string"}, "params": {"type": "object"}}, "required": '
        '["mode"]}},\n]',
        '    {"name": "early_warning_tool", "description": "Analisis de series '
        'temporales para alertas tempranas: threshold_crossing (cruce de umbrales '
        'tipo semaforo con proyeccion de tiempo hasta el proximo umbral), '
        'trend_analysis (regresion lineal, pendiente y R2), rate_of_change_alert '
        '(tasa de cambio y deteccion de subidas/bajadas criticas), '
        'moving_average_anomaly (deteccion de anomalias contra media movil '
        'trailing).", "inputSchema": {"type": "object", "properties": {"mode": '
        '{"type": "string"}, "params": {"type": "object"}}, "required": '
        '["mode"]}},\n] + tool_registry.get_schemas()',
    ),
    # 4a) sacar los 2 bloques elif viejos (el de fractional_fourier_tool tenia el bug)
    (
        '                elif tool_name == "fractional_fourier_tool":\n'
        '                    result = compute_fractional_fourier(args.get("mode"), args.get("params"))\n'
        '                elif tool_name == "wave_propagation_tool":\n'
        '                    result = compute_wave_propagation(args.get("mode"), args.get("params"))\n'
        '                    resp = {\n'
        '                        "jsonrpc": "2.0", "id": req_id,\n'
        '                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
        '                    }\n'
        '                elif tool_name == "dispersion_relation_tool":',
        '                elif tool_name == "dispersion_relation_tool":',
    ),
    # 4b) agregar el chequeo del registro como primera rama del dispatch
    (
        '                tool_name = req["params"]["name"]\n'
        '                args = req["params"].get("arguments", {})\n'
        '\n'
        '                if tool_name == "run_octave":',
        '                tool_name = req["params"]["name"]\n'
        '                args = req["params"].get("arguments", {})\n'
        '\n'
        '                if tool_name in tool_registry.REGISTRY:\n'
        '                    result = tool_registry.REGISTRY[tool_name]["handler"](args)\n'
        '                    resp = {\n'
        '                        "jsonrpc": "2.0", "id": req_id,\n'
        '                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
        '                    }\n'
        '                elif tool_name == "run_octave":',
    ),
]


def main():
    with open(PATH, "r", encoding="utf-8") as f:
        content = f.read()

    for i, (old, new) in enumerate(CHANGES, 1):
        count = content.count(old)
        if count != 1:
            print(f"ABORTADO: el cambio {i}/5 no matchea exactamente "
                  f"(encontrado {count} veces, se esperaba 1).")
            print("No se modifico ningun archivo. Revisa si server.py ya "
                  "fue editado o si difiere del que uso Claude para generar este script.")
            sys.exit(1)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"server.py.bak.{ts}"
    shutil.copyfile(PATH, backup_path)
    print(f"Backup creado: {backup_path}")

    for old, new in CHANGES:
        content = content.replace(old, new, 1)

    with open(PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print("server.py actualizado con los 5 cambios del Paso 1.")
    print("Revisa el diff con: git diff server.py")


if __name__ == "__main__":
    main()
