import re
import json

with open("README.md", encoding="utf-8") as f:
    readme = f.read()

# extrae todo lo que esta entre backticks simples que parezca un nombre de tool
# (snake_case, sin espacios, sin parentesis dentro)
candidates = re.findall(r"`([a-zA-Z][a-zA-Z0-9_]*)`", readme)
mentioned = set(candidates)

with open("/tmp/tools_names.txt", encoding="utf-8") as f:
    real_tools = set(line.strip() for line in f if line.strip())

new_tools = sorted(real_tools - mentioned)
missing_from_real = sorted(mentioned - real_tools)

print(f"Total tools reales: {len(real_tools)}")
print(f"Total nombres mencionados en README (incluye falsos positivos: params, funciones, etc.): {len(mentioned)}")
print()
print(f"=== TOOLS NUEVAS (en server.py pero no mencionadas en README): {len(new_tools)} ===")
for t in new_tools:
    print(" ", t)
print()
print(f"=== Mencionadas en README pero que NO son nombres de tool actuales: {len(missing_from_real)} ===")
print("(normal que haya bastantes acá: son params, funciones internas, nombres de metodos, etc. -- no todo esto es una tool 'perdida')")
for t in missing_from_real:
    print(" ", t)
