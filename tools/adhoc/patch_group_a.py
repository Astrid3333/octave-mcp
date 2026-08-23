import ast, shutil, datetime

PATCHES = [
    ("ocas_symbolic_tool.py",
     '"mode": {"type": "string", "enum": ["symbolic", "number_theory", "diophantine"], "default": "symbolic"}',
     '"mode": {"type": "string", "enum": ["symbolic", "number_theory", "diophantine", "validate"], "default": "symbolic"}'),
    ("reaction_diffusion_tool_real.py",
     '"mode": {"type": "string", "enum": ["check_turing_instability", "simulate_growth_rate"], "default": "check_turing_instability"}',
     '"mode": {"type": "string", "enum": ["check_turing_instability", "simulate_growth_rate", "validate"], "default": "check_turing_instability"}'),
]

for path, old, new in PATCHES:
    with open(path) as f:
        src = f.read()
    count = src.count(old)
    print(f"{path}: ocurrencias de anchor = {count}")
    if count != 1:
        print(f"  ABORTADO para {path}: anchor no es unico")
        continue
    new_src = src.replace(old, new)
    try:
        ast.parse(new_src)
    except SyntaxError as e:
        print(f"  ABORTADO para {path}: {e}")
        continue
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = f"{path}.bak_{ts}"
    shutil.copy(path, backup)
    with open(path, "w") as f:
        f.write(new_src)
    print(f"  OK: {path} patcheado (backup: {backup})")
