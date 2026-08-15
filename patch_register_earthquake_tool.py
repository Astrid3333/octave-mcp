#!/usr/bin/env python3
import shutil
from datetime import datetime

TARGET = "earthquake_analysis_tool.py"
backup = f"{TARGET}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
shutil.copy(TARGET, backup)

with open(TARGET, "r", encoding="utf-8") as f:
    content = f.read()

SCHEMA = '''EARTHQUAKE_ANALYSIS_TOOL_SCHEMA = {
    "name": "earthquake_analysis_tool",
    "description": (
        "Peligrosidad sismica: deterministic (PGA por atenuacion de Esteva desde "
        "magnitud y distancia, amplificacion de sitio NEHRP simplificada, "
        "conversion a intensidad MMI), psha (peligrosidad probabilistica: "
        "recurrencia Gutenberg-Richter, curva de peligro, PGA de diseno para un "
        "periodo de retorno dado), validate (suite de checks)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["deterministic", "psha", "validate"]},
            "params": {
                "type": "object",
                "properties": {
                    "magnitude": {"type": "number", "description": "Magnitud (deterministic)"},
                    "distance_km": {"type": "number", "description": "Distancia epicentral en km (deterministic y psha)"},
                    "soil_class": {"type": "string", "description": "Clase de sitio NEHRP: A/B/C/D/E (deterministic, default B)"},
                    "gr_a": {"type": "number", "description": "Parametro a de Gutenberg-Richter (psha)"},
                    "gr_b": {"type": "number", "description": "Parametro b de Gutenberg-Richter (psha)"},
                    "m_min": {"type": "number", "description": "Magnitud minima (psha, default 4.0)"},
                    "m_max": {"type": "number", "description": "Magnitud maxima (psha)"},
                    "return_period_years": {"type": "number", "description": "Periodo de retorno en anios (psha, default 475)"},
                    "sigma_ln": {"type": "number", "description": "Dispersion lognormal del residuo de atenuacion (psha, opcional)"},
                },
            },
        },
        "required": ["mode"],
    },
}


'''

ANCHOR = "def compute_earthquake_analysis(mode, params=None):"
assert content.count(ANCHOR) == 1, f"se esperaba 1 ocurrencia de ANCHOR, se encontraron {content.count(ANCHOR)}"
content = content.replace(ANCHOR, SCHEMA + ANCHOR)

REGISTER_BLOCK = '''

try:
    from tool_registry import register_tool
    register_tool(
        name="earthquake_analysis_tool",
        schema=EARTHQUAKE_ANALYSIS_TOOL_SCHEMA,
        handler=lambda args: compute_earthquake_analysis(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    d = compute_earthquake_analysis("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\\nTodos los chequeos de earthquake_analysis_tool.py pasaron OK.")
'''

content = content + REGISTER_BLOCK

with open(TARGET, "w", encoding="utf-8") as f:
    f.write(content)

print(f"Patch aplicado OK. Backup: {backup}")
