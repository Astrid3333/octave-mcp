# octave-mcp — Guía rápida de ejemplos

Este documento muestra cómo invocar las herramientas de este servidor MCP
usando el protocolo JSON-RPC crudo, útil para pruebas manuales, debugging,
o para entender el formato antes de conectar un cliente MCP real.

## Formato general

Todas las llamadas siguen el protocolo MCP estándar por stdin/stdout. Un
cliente primero manda `initialize`, después puede pedir `tools/list` (ver
todas las tools disponibles) o `tools/call` (ejecutar una).

### Ver todas las tools disponibles

```bash
cd ~/octave-mcp
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}' | python3 server.py
```

Esto imprime, entre otras cosas, el schema completo de cada tool (nombre,
descripción, parámetros esperados).

### Llamar a una tool puntual

El patrón general de una llamada es:

```json
{"jsonrpc": "2.0", "id": 3, "method": "tools/call",
 "params": {"name": "<nombre_de_la_tool>", "arguments": {"mode": "...", "params": {...}}}}
```

Se manda por stdin junto con `initialize` primero. Ejemplo genérico en bash:

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "NOMBRE_TOOL", "arguments": {"mode": "validate"}}}' | python3 server.py
```

Casi todas las tools soportan `mode="validate"` (o similar) como forma
rápida de comprobar que están funcionando sin necesidad de armar params
reales — es el mismo modo que usa `run_all_validations.py` antes de cada
push.

---

## Ejemplos por área

### 1. Finanzas personales — `savings_rate_tool`

Calcula tasa de ahorro y tiempo para alcanzar una meta.

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "savings_rate_tool", "arguments": {"mode": "time_to_goal", "params": {"current_savings": 5000, "monthly_savings": 500, "goal": 20000, "annual_return_pct": 5}}}}' | python3 server.py
```

### 2. Riesgo de desastres — `earthquake_analysis_tool`

Estimación determinista de PGA/intensidad sísmica por magnitud y distancia.

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "earthquake_analysis_tool", "arguments": {"mode": "deterministic", "params": {"magnitude": 6.5, "distance_km": 20, "soil_class": "C"}}}}' | python3 server.py
```

### 3. Riesgo de incendios — `wildfire_risk_tool`

Velocidad de propagación de un incendio via modelo de Rothermel.

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "wildfire_risk_tool", "arguments": {"mode": "rate_of_spread", "params": {"fuel_model": "3", "wind_speed_20ft_mph": 15, "slope_percent": 10}}}}' | python3 server.py
```

### 4. Cálculo simbólico (oCAS / Rust) — `ocas_symbolic`

Diferenciación simbólica, teoría de números, ecuaciones diofánticas.

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "ocas_symbolic", "arguments": {"mode": "symbolic", "params": {"preset": "custom", "expression": "x^3 + 2*x", "sub_mode": "differentiate"}}}}' | python3 server.py
```

### 5. Meta-tool que encadena otras tools — `compute_math_pipeline`

Corre varios pasos en secuencia, pasando el resultado de uno como input
del siguiente.

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "compute_math_pipeline", "arguments": {"mode": "list_tools"}}}' | python3 server.py
```

Para ver un pipeline real de 2 pasos (regresión lineal → crecimiento
logístico usando la pendiente estimada), correr el archivo directo:

```bash
python3 math_pipeline_tool.py
```

### 6. Hábitos financieros — `habit_streak_tool`

Racha de meses cumpliendo un objetivo de ahorro/gasto.

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "habit_streak_tool", "arguments": {"mode": "streak", "params": {"monthly_success": [1,1,1,0,1,1]}}}}' | python3 server.py
```

---

## Convención de auto-chequeo (`validate`)

La mayoría de las tools nuevas (wireadas vía `tool_registry`) exponen un
modo `mode="validate"` que corre una suite interna de checks contra
resultados conocidos (fórmulas cerradas, casos límite, valores de
referencia publicados). Es la forma más rápida de confirmar que una tool
sigue funcionando después de un cambio, sin tener que inventar params:

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "NOMBRE_TOOL", "arguments": {"mode": "validate"}}}' | python3 server.py
```

La respuesta trae `"validation_passed": true/false` y un detalle de cada
check individual en `"checks"`.

Para correr **todas** las validaciones de golpe (lo que hace el hook de
pre-push):

```bash
python3 run_all_validations.py
```

Con `--verbose` se ve el detalle de qué tools no tienen modo `validate`
(quedan como SKIPPED, no como fallidas).

---

## Notas de confiabilidad de datos

Varias tools declaran su nivel de confianza en los datos/tablas que usan
directamente en el campo `"data_confidence"` de la respuesta, o en el
docstring del archivo. Por ejemplo, `wildfire_risk_tool.py` distingue
confianza ALTA en la física de Rothermel/Byram vs. confianza BAJA en el
catálogo Scott & Burgan 40 (valores estimados por patrón, no la tabla
publicada exacta). Revisar el docstring de cada tool antes de usarla para
decisiones reales, no solo para prototipado.

