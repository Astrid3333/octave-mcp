"""
Wirea las 3 tools del grupo "Economia Publica" en server.py:
  - disaster_economics_tool
  - social_impact_tool
  - insurance_risk_tool

Mismo patron que los wireos anteriores (import + entrada en TOOLS[] con
schema inline + bloque de dispatch elif), aplicado 3 veces en una sola
pasada. Cada insercion usa su propio anchor y su propio assert count==1,
asi que si alguna falla las otras no quedan a medio aplicar (se corta
antes de escribir el archivo).

Uso: correr desde ~/octave-mcp. Crea backup timestampado antes de tocar nada.
"""
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

# ---------------------------------------------------------------------------
# 1) IMPORTS -- encadenados despues del import de disaster_simulation_tool
# ---------------------------------------------------------------------------
import_anchor = 'from disaster_simulation_tool import compute_disaster_simulation\n'
assert content.count(import_anchor) == 1, f"import_anchor no encontrado 1 vez (encontrado {content.count(import_anchor)})"
new_imports = (
    import_anchor
    + 'from disaster_economics_tool import compute_disaster_economics\n'
    + 'from social_impact_tool import compute_social_impact\n'
    + 'from insurance_risk_tool import compute_insurance_risk\n'
)
content = content.replace(import_anchor, new_imports, 1)

# ---------------------------------------------------------------------------
# 2) TOOLS[] -- se insertan justo despues de la entrada de disaster_simulation_tool
# ---------------------------------------------------------------------------
tools_anchor = (
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
assert content.count(tools_anchor) == 1, f"tools_anchor no encontrado 1 vez (encontrado {content.count(tools_anchor)})"

econ_schema_entry = (
    '    {"name": "disaster_economics_tool", "description": "Economia de desastres para evaluacion de '
    'politica publica: direct_indirect_loss (perdida indirecta via multiplicador economico regional, '
    'indirect=direct*(m-1)), business_interruption_loss (perdida acumulada por interrupcion de actividad '
    'economica durante una recuperacion exponencial hacia el nivel pre-desastre, integral cerrada), '
    'benefit_cost_ratio (BCR de una inversion de mitigacion: VAN de la perdida anual esperada evitada vs '
    'costo de inversion, a tasa de descuento y horizonte dados), gdp_impact_icor (impacto en el flujo de '
    'producto por destruccion de stock de capital via ratio incremental capital-producto ICOR), validate '
    '(suite de 10 checks). Motor generico: no trae catalogo de multiplicadores/ICOR por region o sector '
    '(los provee quien llama), confidence_flag \'alta\' para toda la mecanica.", "inputSchema": {"type": '
    '"object", "properties": {"mode": {"type": "string"}, "params": {"type": "object"}}, "required": '
    '["mode"]}},\n'
    '    {"name": "social_impact_tool", "description": "Impacto social de desastres y de inversion '
    'publica: social_vulnerability_index (indice SoVI via suma de z-scores de indicadores socioeconomicos '
    'con signo configurable por indicador), displacement_estimate (poblacion desplazada y unidades de '
    'vivienda temporal requeridas a partir de dano habitacional por severidad y ocupacion promedio), '
    'equity_weighted_impact (pondera perdida/dano economico por un factor de vulnerabilidad social para '
    'priorizar inversion), casualty_estimate (estimacion simplificada de victimas a partir de fraccion de '
    'estructuras colapsadas, ocupacion y hora del dia, logica HAZUS-MH simplificada), validate (suite de '
    '10 checks). Motor generico: no trae catalogo de indicadores/pesos por region (los provee quien '
    'llama), confidence_flag \'alta\' para la mecanica.", "inputSchema": {"type": "object", "properties": '
    '{"mode": {"type": "string"}, "params": {"type": "object"}}, "required": ["mode"]}},\n'
    '    {"name": "insurance_risk_tool", "description": "Seguros y reaseguro de catastrofes: pure_premium '
    '(prima pura mas cargas de gasto y margen de utilidad, sobre una distribucion de perdida '
    'Poisson-LogNormal simulada o provista, prima_comercial = prima_pura/(1-expense_ratio-profit_margin)), '
    'excess_of_loss_layer (pricing de una capa de reaseguro XoL via Monte Carlo, perdida esperada de capa '
    '= E[min(max(L-attachment,0),limit)]), cat_bond_pricing (pricing simplificado de bono catastrofico: '
    'cupon = perdida esperada de la capa cubierta/principal + spread de mercado), loss_ratio_analysis '
    '(loss ratio, expense ratio y combined ratio de una cartera dado primas y siniestros historicos), '
    'validate (suite de 10 checks). Motor generico: no trae catalogo de tasas de mercado ni expense ratios '
    '(los provee quien llama), confidence_flag \'alta\'.", "inputSchema": {"type": "object", "properties": '
    '{"mode": {"type": "string"}, "params": {"type": "object"}}, "required": ["mode"]}},\n'
)
content = content.replace(tools_anchor, tools_anchor + econ_schema_entry, 1)

# ---------------------------------------------------------------------------
# 3) DISPATCH -- se inserta despues del bloque de disaster_simulation_tool
# ---------------------------------------------------------------------------
dispatch_anchor = (
    '                elif tool_name == "disaster_simulation_tool":\n'
    '                    result = compute_disaster_simulation(args.get("mode"), args.get("params"))\n'
    '                    resp = {\n'
    '                        "jsonrpc": "2.0", "id": req_id,\n'
    '                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                    }\n'
)
assert content.count(dispatch_anchor) == 1, f"dispatch_anchor no encontrado 1 vez (encontrado {content.count(dispatch_anchor)})"

econ_dispatch = (
    '                elif tool_name == "disaster_economics_tool":\n'
    '                    result = compute_disaster_economics(args.get("mode"), args.get("params"))\n'
    '                    resp = {\n'
    '                        "jsonrpc": "2.0", "id": req_id,\n'
    '                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                    }\n'
    '                elif tool_name == "social_impact_tool":\n'
    '                    result = compute_social_impact(args.get("mode"), args.get("params"))\n'
    '                    resp = {\n'
    '                        "jsonrpc": "2.0", "id": req_id,\n'
    '                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                    }\n'
    '                elif tool_name == "insurance_risk_tool":\n'
    '                    result = compute_insurance_risk(args.get("mode"), args.get("params"))\n'
    '                    resp = {\n'
    '                        "jsonrpc": "2.0", "id": req_id,\n'
    '                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    '                    }\n'
)
content = content.replace(dispatch_anchor, dispatch_anchor + econ_dispatch, 1)

with open(SERVER, "w", encoding="utf-8") as f:
    f.write(content)

py_compile.compile(SERVER, doraise=True)

print(f"Backup: {BACKUP}")
print("Patch aplicado: 9 inserciones (3 imports, 3 entradas TOOLS[], 3 bloques dispatch).")
