import importlib
from pprint import pformat

MODULES = {
    "pedotransfer_tool": "Estima curvas de retencion de agua y conductividad hidraulica desde textura, densidad y materia organica (pedotransfer functions, van Genuchten/Brooks-Corey).",
    "soil_mechanics_tool": "Criterios de falla (Mohr-Coulomb, Drucker-Prager) y consolidacion (Cam-Clay modificado) para mecanica de suelos.",
    "soil_mixture_tool": "Relaciones volumetricas de 3 fases y propiedades termicas efectivas del suelo, con contabilidad de materia organica (SOM).",
    "soil_water_flow_tool": "Solver 1D de la ecuacion de Richards para infiltracion, evaporacion e imbibicion, con solucion analitica Green-Ampt.",
}

for modname, description in MODULES.items():
    fname = modname + ".py"
    print("=== " + fname + " ===")

    mod = importlib.import_module(modname)
    input_schema = mod.inputSchema
    modes = list(input_schema.keys())

    merged_props = {"mode": {"type": "string", "enum": modes, "description": "Modo de operacion"}}
    for mode_name, schema in input_schema.items():
        for prop_name, prop_def in schema.get("properties", {}).items():
            if prop_name not in merged_props:
                merged_props[prop_name] = prop_def

    props_src = pformat(merged_props, width=100)

    code = "\n\n"
    code += "# " + "=" * 76 + "\n"
    code += "# TOOL REGISTRATION (auto-agregado)\n"
    code += "# " + "=" * 76 + "\n\n"
    code += "TOOL_SCHEMA = {\n"
    code += "    \"name\": " + repr(modname) + ",\n"
    code += "    \"description\": " + repr(description) + ",\n"
    code += "    \"inputSchema\": {\n"
    code += "        \"type\": \"object\",\n"
    code += "        \"properties\": " + props_src + ",\n"
    code += "        \"required\": [\"mode\"],\n"
    code += "    },\n"
    code += "}\n\n\n"
    code += "def _handler(arguments):\n"
    code += "    mode = arguments.get(\"mode\", \"validate\")\n"
    code += "    result = run(mode, arguments)\n"
    code += "    if mode == \"validate\" and isinstance(result, dict) and \"passed\" in result and \"total\" in result:\n"
    code += "        details = result.get(\"details\", [])\n"
    code += "        return {\n"
    code += "            \"validation_passed\": result.get(\"passed\", 0) == result.get(\"total\", 0),\n"
    code += "            \"checks\": [\n"
    code += "                {\"name\": f\"check_{i}\", \"passed\": \"\\u2713\" in str(d), \"detail\": str(d)}\n"
    code += "                for i, d in enumerate(details)\n"
    code += "            ],\n"
    code += "            \"n_checks\": result.get(\"total\", 0),\n"
    code += "            \"n_passed\": result.get(\"passed\", 0),\n"
    code += "        }\n"
    code += "    return result\n\n\n"
    code += "def _register():\n"
    code += "    try:\n"
    code += "        import tool_registry\n"
    code += "        tool_registry.register_tool(TOOL_SCHEMA[\"name\"], TOOL_SCHEMA, _handler)\n"
    code += "    except ImportError:\n"
    code += "        pass\n\n\n"
    code += "_register()\n"

    with open(fname, "a", encoding="utf-8") as f:
        f.write(code)

    print("OK: TOOL_SCHEMA + _handler + _register() agregados a " + fname)

print("\nListo. Confirmar con el smoke test JSON-RPC de cada tool y con tools/list del server.")
