#!/usr/bin/env python3
"""
Patch de wireo para health_check_tool.py.

Paso 1 (obligatorio): agrega UNA linea de import a server.py, siguiendo
exactamente el mismo patron ya usado por fractional_fourier_tool,
particle_simulation_tool, wave_propagation_tool, etc. (auto-registro via
tool_registry -- no toca la lista TOOLS ni la cadena elif de tools/call).

Paso 2 (opcional, --skip-dedupe para omitir): mientras confirmaba el
anchor para el paso 1, encontre 3 imports duplicados de una tanda
anterior (emergency_fund_tool, investment_portfolio_tool,
tax_estimation_tool aparecen importados dos veces cada uno, lineas 9-11
Y 13-15). Python ya los des-duplica solo (import cachea el modulo, la
segunda linea es un no-op), asi que NO es un bug funcional -- pero son
3 lineas muertas. Se limpian aca de paso porque ya estaba mirando ese
bloque exacto; si preferis no tocarlas, correr con --skip-dedupe.
"""
import sys

PATH = "server.py"

# --- paso 1: agregar el import de health_check_tool ---
ANCHOR = 'import particle_simulation_tool  # auto-registra via tool_registry\n'
NEW_IMPORT = 'import health_check_tool  # auto-registra via tool_registry, no requiere mas ediciones\n'

# --- paso 2 (opcional): imports duplicados a eliminar ---
DUPLICATE_BLOCK = (
    'import emergency_fund_tool  # auto-registra via tool_registry, no requiere mas ediciones\n'
    'import investment_portfolio_tool  # auto-registra via tool_registry, no requiere mas ediciones\n'
    'import tax_estimation_tool  # auto-registra via tool_registry, no requiere mas ediciones\n'
)

with open(PATH, encoding="utf-8") as f:
    content = f.read()

n_anchor = content.count(ANCHOR)
assert n_anchor == 1, f"Se esperaba 1 ocurrencia del anchor de import, se encontraron {n_anchor} -- revisar a mano antes de aplicar"
content = content.replace(ANCHOR, ANCHOR + NEW_IMPORT)

if "--skip-dedupe" not in sys.argv:
    n_dup = content.count(DUPLICATE_BLOCK)
    assert n_dup == 2, (
        f"Se esperaban exactamente 2 ocurrencias del bloque duplicado (original + copia), "
        f"se encontraron {n_dup} -- el archivo puede haber cambiado desde que se escribio "
        f"este patch. Revisar a mano, o correr con --skip-dedupe para omitir este paso."
    )
    first = content.find(DUPLICATE_BLOCK)
    second = content.find(DUPLICATE_BLOCK, first + len(DUPLICATE_BLOCK))
    content = content[:second] + content[second + len(DUPLICATE_BLOCK):]

with open(PATH, "w", encoding="utf-8") as f:
    f.write(content)

print("Patch aplicado OK")
