import shutil, datetime

path = "server.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
backup_path = f"server.py.bak.{ts}"
shutil.copy(path, backup_path)
print(f"Backup: {backup_path}")

anchor_import = "from natural_hazard_risk_tool import compute_natural_hazard_risk"
assert content.count(anchor_import) == 1, f"anchor_import aparece {content.count(anchor_import)} veces"
content = content.replace(
    anchor_import,
    anchor_import + "\nfrom earthquake_analysis_tool import compute_earthquake_analysis",
    1,
)

anchor_tools = '    {"name": "natural_hazard_risk_tool", "description": "Modelado de riesgo multifactorial (R=H*E*V/A) para gestion publica de desastres naturales: risk_index (indice de riesgo puntual con clasificacion en bandas), risk_grid (mapa de calor de riesgo sobre grilla), gumbel_return_period (periodo de retorno empirico T=(n+1)/m), gumbel_fit (ajuste de distribucion de Gumbel por momentos y estimacion de magnitud de diseno o periodo de retorno).", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "params": {"type": "object"}}, "required": ["mode"]}},'
assert content.count(anchor_tools) == 1, f"anchor_tools aparece {content.count(anchor_tools)} veces"
new_tools_entry = '    {"name": "earthquake_analysis_tool", "description": "Peligrosidad sismica para gestion publica municipal: deterministic (atenuacion de Esteva PGA=5700*exp(0.8M)/(R+40)^2, amplificacion de sitio tipo NEHRP simplificado por clase de suelo A-E, conversion PGA->MMI de Wald et al.), psha (recurrencia Gutenberg-Richter, curva de peligrosidad tasa de excedencia vs PGA, inversion por biseccion a PGA de diseno para un periodo de retorno dado, ej. 475 anios), validate (suite de 9 checks).", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string"}, "params": {"type": "object"}}, "required": ["mode"]}},'
content = content.replace(anchor_tools, anchor_tools + "\n" + new_tools_entry, 1)

anchor_dispatch = '''                elif tool_name == "natural_hazard_risk_tool":
                    result = compute_natural_hazard_risk(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }'''
assert content.count(anchor_dispatch) == 1, f"anchor_dispatch aparece {content.count(anchor_dispatch)} veces"
new_dispatch = '''
                elif tool_name == "earthquake_analysis_tool":
                    result = compute_earthquake_analysis(args.get("mode"), args.get("params"))
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                    }'''
content = content.replace(anchor_dispatch, anchor_dispatch + new_dispatch, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patch aplicado: 3 inserciones (import, TOOLS, dispatch).")
