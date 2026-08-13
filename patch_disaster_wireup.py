"""
Wirea disaster_simulation_tool en server.py:
  1) import compute_disaster_simulation
  2) entrada en TOOLS[] (schema inline, mismo patron que climate_scenario_tool)
  3) bloque de dispatch elif tool_name == "disaster_simulation_tool"

Uso: correr desde ~/octave-mcp (o el directorio con server.py real).
Crea backup timestamado antes de tocar nada.
"""
import re
import shutil
import time
import py_compile

SERVER = "server.py"
TS = time.strftime("%Y%m%d%H%M%S")
BACKUP = f"{SERVER}.bak.{TS}"

with open(SERVER, "r", encoding="utf-8") as f:
    content = f.read()

py_compile.compile(SERVER, doraise=True)
shutil.copy(SERVER, BACKUP)

# 1) import
import_anchor = 'from climate_scenario_tool import compute_climate_scenario\n'
assert content.count(import_anchor) == 1, f"import_anchor no encontrado 1 vez (encontrado {content.count(import_anchor)})"
new_import = import_anchor + 'from disaster_simulation_tool import compute_disaster_simulation\n'
content = content.replace(import_anchor, new_import, 1)

# 2) entrada en TOOLS[] -- se inserta justo despues de la entrada de climate_scenario_tool,
# mismo lugar relativo donde climate_scenario_tool se inserto respecto de TOOLS = [
tools_anchor = (
    '{"name": "climate_scenario_tool", "description": "Analisis de escenarios climaticos: '
    'trend_analysis (regresion lineal, Mann-Kendall, changepoint CUSUM sobre series temporales), '
    'rcp_projection (proyeccion de temperatura/nivel del mar para un RCP y anio dado), '
    'list_rcp_scenarios (catalogo RCP2.6/4.5/6.0/8.5 con datos IPCC AR5), validate.", '
    '"inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, '
    '"params": {"type": "object"}}, "required": ["mode"]}},\n'
)
assert content.count(tools_anchor) == 1, f"tools_anchor no encontrado 1 vez (encontrado {content.count(tools_anchor)})"

disaster_schema_entry = (
    '    {"name": "disaster_simulation_tool", "description": "Simulacion Monte Carlo de desastres '
    '(modelo actuarial frecuencia-severidad Poisson-LogNormal) para gestion publica de riesgos: '
    'monte_carlo_losses (distribucion de perdida agregada anual dado lambda de frecuencia y '
    'mu/sigma de severidad lognormal, con VaR y CVaR/Tail-VaR a percentiles configurables), '
    'return_period_loss (perdida esperada para periodos de retorno dados, estimador empirico de '
    'Weibull T=(n+1)/m, consistente con natural_hazard_risk_tool.gumbel_return_period), '
    'exceedance_curve (curva de probabilidad de excedencia anual -EP curve- para una lista de '
    'umbrales de perdida), multi_hazard_combine (combina dos peligros independientes o '
    'correlacionados via copula gaussiana en una perdida agregada conjunta), validate (suite de '
    '10 checks). Motor generico: no trae catalogo de parametros por tipo de peligro (lambda/mu/sigma '
    'los provee quien llama), confidence_flag \'alta\' para toda la mecanica estadistica.", '
    '"inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, '
    '"params": {"type": "object"}}, "required": ["mode"]}},\n'
)
content = content.replace(tools_anchor, tools_anchor + disaster_schema_entry, 1)

# 3) dispatch -- se inserta despues del bloque de early_warning_tool
dispatch_anchor = (
    '                elif tool_name == "early_warning_tool":\n'
    '                    result = compute_early_warning(args.get("mode"), args.get("params"))\n'
    '                    resp = {\n'
    '                        "jsonrpc": "2.0", "id": req_id,\n'
    '                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                    }\n'
)
assert content.count(dispatch_anchor) == 1, f"dispatch_anchor no encontrado 1 vez (encontrado {content.count(dispatch_anchor)})"

disaster_dispatch = (
    '                elif tool_name == "disaster_simulation_tool":\n'
    '                    result = compute_disaster_simulation(args.get("mode"), args.get("params"))\n'
    '                    resp = {\n'
    '                        "jsonrpc": "2.0", "id": req_id,\n'
    '                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                    }\n'
)
content = content.replace(dispatch_anchor, dispatch_anchor + disaster_dispatch, 1)

with open(SERVER, "w", encoding="utf-8") as f:
    f.write(content)

py_compile.compile(SERVER, doraise=True)

print(f"Backup: {BACKUP}")
print("Patch aplicado: 3 inserciones (import, TOOLS, dispatch).")
