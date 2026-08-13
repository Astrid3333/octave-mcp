import shutil, datetime

path = "server.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
backup_path = f"server.py.bak.{ts}"
shutil.copy(path, backup_path)
print(f"Backup: {backup_path}")

# 1) import
anchor_import = "from earthquake_analysis_tool import compute_earthquake_analysis"
assert content.count(anchor_import) == 1, f"anchor_import aparece {content.count(anchor_import)} veces"
content = content.replace(
    anchor_import,
    anchor_import + "\nfrom wildfire_risk_tool import compute_wildfire_risk",
    1,
)

# 2) entrada en TOOLS
anchor_tools = '    {"name": "earthquake_analysis_tool", "description": "Peligrosidad sismica para gestion publica municipal: deterministic (atenuacion de Esteva PGA=5700*exp(0.8M)/(R+40)^2, amplificacion de sitio tipo NEHRP simplificado por clase de suelo A-E, conversion PGA->MMI de Wald et al.), psha (recurrencia Gutenberg-Richter, curva de peligrosidad tasa de excedencia vs PGA, inversion por biseccion a PGA de diseno para un periodo de retorno dado, ej. 475 anios), validate (suite de 9 checks).", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "params": {"type": "object"}}, "required": ["mode"]}},'
assert content.count(anchor_tools) == 1, f"anchor_tools aparece {content.count(anchor_tools)} veces"
wildfire_tools_entry = (
    '\n    {"name": "wildfire_risk_tool", "description": '
    '"Peligrosidad de incendios forestales via modelo de Rothermel (1972) con ponderacion muerto/vivo: '
    'rate_of_spread (velocidad de propagacion ft/min, intensidad de linea de fuego e Byram, largo de llama, dado '
    'viento/pendiente/humedad y un modelo de combustible), fuel_model_info (parametros crudos de un modelo), '
    'list_fuel_models (codigos disponibles por catalogo), validate (suite de 10 checks de consistencia fisica). '
    'fuel_catalog: anderson13 (13 modelos, confianza media-alta), scott_burgan40 (40 modelos, confianza BAJA -- '
    'valores estimados por patron, no verificados contra la tabla fuente, ver campo data_confidence en cada '
    'respuesta), o custom (fuel_model provisto por quien llama, sin datos hardcodeados)." , '
    '"inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "params": {"type": "object"}}, "required": ["mode"]}},'
)
content = content.replace(anchor_tools, anchor_tools + wildfire_tools_entry, 1)

# 3) dispatch
anchor_dispatch = '''                elif tool_name == "earthquake_analysis_tool":
                    result = compute_earthquake_analysis(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }'''
assert content.count(anchor_dispatch) == 1, f"anchor_dispatch aparece {content.count(anchor_dispatch)} veces"
wildfire_dispatch = '''
                elif tool_name == "wildfire_risk_tool":
                    result = compute_wildfire_risk(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }'''
content = content.replace(anchor_dispatch, anchor_dispatch + wildfire_dispatch, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patch aplicado: 3 inserciones (import, TOOLS, dispatch).")
