"""
patch_infraestructura_datos_wireup.py

Wirea critical_infrastructure_tool, urban_planning_tool y public_data_ingest_tool
en server.py: 3 imports + 3 entradas TOOLS[] + 3 bloques dispatch, en una sola
pasada, con backup timestamped y assert count==1 por ancla (si algo falla no
aplica nada a medias).

Usa como ancla la ultima tool wireada (insurance_risk_tool), asumiendo que
server.py fue restaurado al backup previo a la fase C (server.py.bak.20260813153753)
y por lo tanto NO contiene todavia critical_infrastructure_tool, urban_planning_tool
ni public_data_ingest_tool.
"""

import ast
import shutil
import datetime
import sys

SERVER_PATH = "server.py"


def read_server():
    with open(SERVER_PATH, "r", encoding="utf-8") as f:
        return f.read()


def write_server(content):
    with open(SERVER_PATH, "w", encoding="utf-8") as f:
        f.write(content)


def backup_server():
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = f"{SERVER_PATH}.bak.{ts}"
    shutil.copy2(SERVER_PATH, backup_path)
    print(f"Backup: {backup_path}")
    return backup_path


# ---------------------------------------------------------------------------
# Anclas e inserciones
# ---------------------------------------------------------------------------

IMPORT_ANCHOR = "from insurance_risk_tool import compute_insurance_risk\n"

NEW_IMPORTS = (
    "from insurance_risk_tool import compute_insurance_risk\n"
    "from critical_infrastructure_tool import compute_critical_infrastructure\n"
    "from urban_planning_tool import compute_urban_planning\n"
    "from public_data_ingest_tool import compute_public_data_ingest\n"
)

TOOLS_ANCHOR = (
    '    {"name": "insurance_risk_tool", "description": "Seguros y reaseguro de '
    'catastrofes: pure_premium (prima pura mas cargas de gasto y margen de utilidad, '
    'sobre una distribucion de perdida Poisson-LogNormal simulada o provista, '
    'prima_comercial = prima_pura/(1-expense_ratio-profit_margin)), excess_of_loss_layer '
    '(pricing de una capa de reaseguro XoL via Monte Carlo, perdida esperada de capa = '
    'E[min(max(L-attachment,0),limit)]), cat_bond_pricing (pricing simplificado de bono '
    'catastrofico: cupon = perdida esperada de la capa cubierta/principal + spread de '
    'mercado), loss_ratio_analysis (loss ratio, expense ratio y combined ratio de una '
    'cartera dado primas y siniestros historicos), validate (suite de 10 checks). Motor '
    'generico: no trae catalogo de tasas de mercado ni expense ratios (los provee quien '
    'llama), confidence_flag \'alta\'.", "inputSchema": {"type": "object", "properties": '
    '{"mode": {"type": "string"}, "params": {"type": "object"}}, "required": ["mode"]}},\n'
)

NEW_TOOLS_ENTRIES = (
    TOOLS_ANCHOR
    + "    CRITICAL_INFRASTRUCTURE_TOOL_SCHEMA,\n"
    + "    URBAN_PLANNING_TOOL_SCHEMA,\n"
    + "    PUBLIC_DATA_INGEST_TOOL_SCHEMA,\n"
)

DISPATCH_ANCHOR = (
    '                elif tool_name == "insurance_risk_tool":\n'
    "                    result = compute_insurance_risk(args.get(\"mode\"), args.get(\"params\"))\n"
    "                    resp = {\n"
    '                        "jsonrpc": "2.0", "id": req_id,\n'
    '                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    "                    }\n"
)

NEW_DISPATCH_BLOCKS = (
    DISPATCH_ANCHOR
    + '                elif tool_name == "critical_infrastructure_tool":\n'
    + "                    result = compute_critical_infrastructure(args.get(\"mode\"), args.get(\"params\"))\n"
    + "                    resp = {\n"
    + '                        "jsonrpc": "2.0", "id": req_id,\n'
    + '                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    + "                    }\n"
    + '                elif tool_name == "urban_planning_tool":\n'
    + "                    result = compute_urban_planning(args.get(\"mode\"), args.get(\"params\"))\n"
    + "                    resp = {\n"
    + '                        "jsonrpc": "2.0", "id": req_id,\n'
    + '                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    + "                    }\n"
    + '                elif tool_name == "public_data_ingest_tool":\n'
    + "                    result = compute_public_data_ingest(args.get(\"mode\"), args.get(\"params\"))\n"
    + "                    resp = {\n"
    + '                        "jsonrpc": "2.0", "id": req_id,\n'
    + '                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},\n'
    + "                    }\n"
)

# Import de las constantes de schema (van junto a los otros imports de tools)
NEW_SCHEMA_IMPORTS = (
    "from critical_infrastructure_tool import CRITICAL_INFRASTRUCTURE_TOOL_SCHEMA\n"
    "from urban_planning_tool import URBAN_PLANNING_TOOL_SCHEMA\n"
    "from public_data_ingest_tool import PUBLIC_DATA_INGEST_TOOL_SCHEMA\n"
)


def apply_patch():
    content = read_server()

    # --- validaciones de unicidad de anclas (assert count == 1) ---
    assert content.count(IMPORT_ANCHOR) == 1, (
        f"IMPORT_ANCHOR aparece {content.count(IMPORT_ANCHOR)} veces (se esperaba 1)"
    )
    assert content.count(TOOLS_ANCHOR) == 1, (
        f"TOOLS_ANCHOR aparece {content.count(TOOLS_ANCHOR)} veces (se esperaba 1) -- "
        "revisar si el texto de la descripcion de insurance_risk_tool cambio"
    )
    assert content.count(DISPATCH_ANCHOR) == 1, (
        f"DISPATCH_ANCHOR aparece {content.count(DISPATCH_ANCHOR)} veces (se esperaba 1)"
    )
    assert "critical_infrastructure_tool" not in content, (
        "server.py ya contiene referencias a critical_infrastructure_tool -- "
        "abortando para no duplicar el wireo"
    )

    backup_server()

    # 1) imports de funciones compute_x + imports de schemas
    content = content.replace(IMPORT_ANCHOR, NEW_IMPORTS + NEW_SCHEMA_IMPORTS, 1)

    # 2) entradas en TOOLS[]
    content = content.replace(TOOLS_ANCHOR, NEW_TOOLS_ENTRIES, 1)

    # 3) bloques de dispatch
    content = content.replace(DISPATCH_ANCHOR, NEW_DISPATCH_BLOCKS, 1)

    write_server(content)

    # --- validacion AST post-patch ---
    ast.parse(content)

    print("Patch aplicado: 9 inserciones (3 imports de funcion + 3 imports de schema, "
          "3 entradas TOOLS[], 3 bloques dispatch).")
    print("Fase C completa: Fenomenos Naturales, Gestion de Riesgos, "
          "Infraestructura Publica, Economia Publica, Gestion de Datos.")


if __name__ == "__main__":
    try:
        apply_patch()
    except AssertionError as e:
        print(f"ABORTADO (ancla no unica o ya aplicado): {e}", file=sys.stderr)
        sys.exit(1)
    except SyntaxError as e:
        print(f"ABORTADO (server.py resultante no es AST valido): {e}", file=sys.stderr)
        sys.exit(1)
