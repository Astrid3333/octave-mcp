"""
apply_fix_error_id_and_gitignore.py

1) Arregla el bug de "id": null en el path de error generico del
   dispatcher: inicializa req_id = None ANTES del try (para que este
   definido incluso si json.loads() falla), y usa req_id en vez de
   None hardcodeado dentro del except.
2) Reescribe .gitignore: agrega el patron *.bak_* (con guion bajo, que
   es el que realmente usan los backups como server.py.bak_chemometrics)
   y elimina las lineas duplicadas del archivo actual.

Backup automatico en server.py.bak_fix_error_id antes de tocar server.py.
"""
import shutil

# --- 1) Fix del "id": null en server.py ---
path = "server.py"
shutil.copy(path, "server.py.bak_fix_error_id")

with open(path, "r") as f:
    content = f.read()

marker_loop = "for line in sys.stdin:\n    line = line.strip()\n    if not line:\n        continue\n    try:\n"
new_loop = "for line in sys.stdin:\n    line = line.strip()\n    if not line:\n        continue\n    req_id = None\n    try:\n"
assert content.count(marker_loop) == 1, f"marker_loop aparece {content.count(marker_loop)} veces, esperado 1"
content = content.replace(marker_loop, new_loop, 1)

marker_except = 'except Exception as e:\n        print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}), flush=True)\n'
new_except = 'except Exception as e:\n        print(json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(e)}}), flush=True)\n'
assert content.count(marker_except) == 1, f"marker_except aparece {content.count(marker_except)} veces, esperado 1"
content = content.replace(marker_except, new_except, 1)

with open(path, "w") as f:
    f.write(content)

print("OK: fix de 'id': null aplicado (backup en server.py.bak_fix_error_id).")

# --- 2) Limpieza de .gitignore ---
gitignore_content = "*.bak_*\n*.bak-*\n__pycache__/\n*.pyc\n.DS_Store\n"
with open(".gitignore", "w") as f:
    f.write(gitignore_content)

print("OK: .gitignore reescrito (sin duplicados, con *.bak_* agregado).")
print("Verificar con: python3 -c \"import ast; ast.parse(open('server.py').read()); print('sintaxis OK')\"")
