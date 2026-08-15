#!/usr/bin/env python3
import shutil
from datetime import datetime

TARGET = "math_pipeline_tool.py"
backup = f"{TARGET}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
shutil.copy(TARGET, backup)

with open(TARGET, "r", encoding="utf-8") as f:
    content = f.read()

REGISTER_BLOCK = '''

try:
    from tool_registry import register_tool
    register_tool(
        name="compute_math_pipeline",
        schema=MATH_PIPELINE_SCHEMA,
        handler=lambda args: compute_math_pipeline(**args),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    d = compute_math_pipeline(mode="validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d.get("validation_passed", d.get("passed", False)), "Validacion fallo, ver detalle arriba"
    print("\\nTodos los chequeos de math_pipeline_tool.py pasaron OK.")
'''

content = content + REGISTER_BLOCK

with open(TARGET, "w", encoding="utf-8") as f:
    f.write(content)

print(f"Patch aplicado OK. Backup: {backup}")
