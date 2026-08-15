#!/usr/bin/env python3
"""
Inserta una seccion 'Quick Start' (los 6 ejemplos curados de la sesion
anterior) justo despues del titulo de EXAMPLES.md, antes del resto del
cookbook completo. No pisa nada existente -- solo inserta.
"""
import shutil
import sys
from datetime import datetime

TARGET = "EXAMPLES.md"

QUICKSTART = '''
## Quick Start (6 ejemplos curados)

Antes de meterte en el cookbook completo de abajo, estos 6 ejemplos
cubren los "sabores" mas comunes de invocacion (mode/params clasico,
kwargs sueltos, meta-tool) y sirven de plantilla rapida para copiar y
extender.

### 1. Finanzas personales - savings_rate_tool

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "savings_rate_tool", "arguments": {"mode": "time_to_goal", "params": {"current_savings": 5000, "monthly_savings": 500, "goal": 20000, "annual_return_pct": 5}}}}' | python3 server.py
```

### 2. Riesgo sismico - earthquake_analysis_tool

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "earthquake_analysis_tool", "arguments": {"mode": "deterministic", "params": {"magnitude": 6.5, "distance_km": 20, "soil_class": "C"}}}}' | python3 server.py
```

### 3. Riesgo de incendios - wildfire_risk_tool

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "wildfire_risk_tool", "arguments": {"mode": "rate_of_spread", "params": {"fuel_model": "3", "wind_speed_20ft_mph": 15, "slope_percent": 10}}}}' | python3 server.py
```

### 4. Calculo simbolico (oCAS / Rust) - ocas_symbolic

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "ocas_symbolic", "arguments": {"mode": "symbolic", "params": {"preset": "custom", "expression": "x^3 + 2*x", "sub_mode": "differentiate"}}}}' | python3 server.py
```

### 5. Meta-tool en cadena - compute_math_pipeline

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "compute_math_pipeline", "arguments": {"mode": "list_tools"}}}' | python3 server.py
```

Pipeline real de 2 pasos (regresion lineal -> crecimiento logistico
usando la pendiente estimada):

```bash
python3 math_pipeline_tool.py
```

### 6. Habitos financieros - habit_streak_tool

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "habit_streak_tool", "arguments": {"mode": "streak", "params": {"monthly_success": [1,1,1,0,1,1]}}}}' | python3 server.py
```

---
'''

def main():
    dry_run = "--dry-run" in sys.argv

    with open(TARGET, encoding="utf-8") as f:
        lines = f.readlines()

    if not lines or not lines[0].lstrip().startswith("# "):
        first = repr(lines[0]) if lines else "(archivo vacio)"
        print(f"ABORTADO: la primera linea de {TARGET} no es un titulo '# ...' "
              f"como se esperaba. No se modifico nada. Primera linea real: {first}")
        sys.exit(1)

    old_line_count = len(lines)
    new_content = lines[0] + QUICKSTART + "\n" + "".join(lines[1:])
    new_line_count = new_content.count("\n")

    print(f"Lineas actuales: {old_line_count}")
    print(f"Lineas resultantes: ~{new_line_count}")
    print(f"Insercion despues de: {lines[0]!r}")

    if dry_run:
        print("\n(--dry-run: no se escribio nada)")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{TARGET}.bak.{ts}"
    shutil.copy(TARGET, backup_path)

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"\nPatch aplicado OK. Backup: {backup_path}")
    print(f"Confirmar con: wc -l {TARGET}  (deberia dar ~{new_line_count})")
    print(f"Y revisar visualmente: head -80 {TARGET}")

if __name__ == "__main__":
    main()
