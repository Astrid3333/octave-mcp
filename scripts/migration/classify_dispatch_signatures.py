#!/usr/bin/env python3
import re

with open("server.py") as f:
    content = f.read()

elif_pattern = re.compile(
    r' {16}elif tool_name == "(\w+)":\n( {20}result = .+?\n)',
)
matches = elif_pattern.findall(content)

standard = []   # result = X(args.get("mode", "validate"), args.get("params"))
kwargs_style = []  # result = X(**args)
other = []

for name, result_line in matches:
    line = result_line.strip()
    if 'args.get("mode"' in line and 'args.get("params")' in line:
        standard.append((name, line))
    elif '(**args)' in line:
        kwargs_style.append((name, line))
    else:
        other.append((name, line))

print(f"=== {len(standard)} tools con firma ESTANDAR (mode, params) ===")
for name, line in standard:
    print(f"  {name}")

print(f"\n=== {len(kwargs_style)} tools con firma **args (kwargs planos) ===")
for name, line in kwargs_style:
    print(f"  {name}: {line}")

print(f"\n=== {len(other)} tools con firma ATIPICA (revisar uno x uno) ===")
for name, line in other:
    print(f"  {name}: {line}")

with open("signature_classification.txt", "w") as f:
    f.write(f"ESTANDAR ({len(standard)}):\n")
    for name, _ in standard:
        f.write(f"{name}\n")
    f.write(f"\nKWARGS ({len(kwargs_style)}):\n")
    for name, line in kwargs_style:
        f.write(f"{name}: {line}\n")
    f.write(f"\nATIPICA ({len(other)}):\n")
    for name, line in other:
        f.write(f"{name}: {line}\n")

print("\nReporte guardado en signature_classification.txt")
