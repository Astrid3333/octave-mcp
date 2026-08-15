#!/usr/bin/env python3
import shutil
from datetime import datetime

TARGET = "wildfire_risk_tool.py"
backup = f"{TARGET}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
shutil.copy(TARGET, backup)

with open(TARGET, "r", encoding="utf-8") as f:
    content = f.read()

SCHEMA = '''WILDFIRE_RISK_TOOL_SCHEMA = {
    "name": "wildfire_risk_tool",
    "description": (
        "Peligrosidad de incendios forestales: rate_of_spread (velocidad de "
        "propagacion via Rothermel, intensidad de linea de fuego y largo de "
        "llama de Byram, dado modelo de combustible, humedad, viento y "
        "pendiente), fuel_model_info (detalle de un modelo de combustible), "
        "list_fuel_models (catalogo Anderson13/Scott&Burgan40), validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["rate_of_spread", "fuel_model_info", "list_fuel_models", "validate"]},
            "params": {
                "type": "object",
                "properties": {
                    "fuel_catalog": {"type": "string", "description": "'anderson13', 'scott_burgan40' o 'custom' (default anderson13)"},
                    "fuel_model": {"type": "string", "description": "Codigo del modelo de combustible en el catalogo elegido"},
                    "custom_fuel": {"type": "object", "description": "Definicion de combustible custom (si fuel_catalog='custom')"},
                    "moisture": {"type": "object", "description": "Humedad por clase de tiempo: 1hr/10hr/100hr/live_herb/live_woody"},
                    "slope_percent": {"type": "number", "description": "Pendiente en % (default 0.0)"},
                    "live_moisture_of_extinction": {"type": "number", "description": "Humedad de extincion viva (opcional)"},
                    "heat_content_btu_lb": {"type": "number", "description": "Contenido calorico del combustible (opcional)"},
                    "wind_speed_midflame_mph": {"type": "number", "description": "Viento a media llama en mph (alternativa directa)"},
                    "wind_speed_20ft_mph": {"type": "number", "description": "Viento a 20ft en mph, se convierte a media llama (default 0.0)"},
                },
            },
        },
        "required": ["mode"],
    },
}


'''

ANCHOR = "def compute_wildfire_risk(mode, params):"
assert content.count(ANCHOR) == 1, f"se esperaba 1 ocurrencia de ANCHOR, se encontraron {content.count(ANCHOR)}"
content = content.replace(ANCHOR, SCHEMA + ANCHOR)

REGISTER_BLOCK = '''

try:
    from tool_registry import register_tool
    register_tool(
        name="wildfire_risk_tool",
        schema=WILDFIRE_RISK_TOOL_SCHEMA,
        handler=lambda args: compute_wildfire_risk(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    d = compute_wildfire_risk("validate", {})
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\\nTodos los chequeos de wildfire_risk_tool.py pasaron OK.")
'''

content = content + REGISTER_BLOCK

with open(TARGET, "w", encoding="utf-8") as f:
    f.write(content)

print(f"Patch aplicado OK. Backup: {backup}")
