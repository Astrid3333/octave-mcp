#!/usr/bin/env python3
"""
Limpia el patron de registro duplicado en server.py: 6 tools ya migradas
a tool_registry (import + register_tool() en su propio modulo) pero que
todavia conservan su entrada legacy vieja (schema hardcodeado en TOOLS +
bloque `elif tool_name == "..."` en el dispatch). Por cada tool: quita
la linea de schema, quita el bloque elif completo, y si el import
legacy `from X import Y` queda sin uso en el resto del archivo, lo
quita tambien. Hace backup de server.py antes de escribir. Si CUALQUIER
tool no da match unico (schema_matches != 1) o no se encuentra su bloque
elif, aborta sin escribir nada -- no hay assert mudo, se imprime el
reporte completo para revisar a mano.
"""
import re
import shutil
import sys
from datetime import datetime

DUPLICATED_TOOLS = [
    "earthquake_analysis_tool",
    "disaster_economics_tool",
    "insurance_risk_tool",
    "ocas_symbolic",
    "social_impact_tool",
    "wildfire_risk_tool",
]

TARGET = "server.py"


def remove_schema_line(lines, tool_name):
    pattern = f'"name": "{tool_name}"'
    matches = [i for i, line in enumerate(lines)
               if pattern in line and "elif tool_name" not in line]
    if len(matches) != 1:
        return lines, matches
    idx = matches[0]
    return lines[:idx] + lines[idx + 1:], matches


def remove_elif_block(lines, tool_name):
    marker = f'elif tool_name == "{tool_name}":'
    start = None
    indent = None
    for i, line in enumerate(lines):
        if marker in line:
            start = i
            indent = len(line) - len(line.lstrip())
            break
    if start is None:
        return lines, None, 0
    end = start + 1
    while end < len(lines):
        stripped = lines[end].lstrip()
        cur_indent = (len(lines[end]) - len(stripped)) if stripped else 999
        if stripped and cur_indent <= indent:
            break
        end += 1
    removed = end - start
    return lines[:start] + lines[end:], start, removed


def remove_dead_legacy_import(lines, tool_name):
    import_re = re.compile(rf'^from {re.escape(tool_name)} import (\w+)')
    for i, line in enumerate(lines):
        m = import_re.match(line.strip())
        if m:
            fn_name = m.group(1)
            other_uses = sum(
                1 for j, l in enumerate(lines)
                if j != i and re.search(rf'\b{re.escape(fn_name)}\b', l)
            )
            if other_uses == 0:
                return lines[:i] + lines[i + 1:], True, fn_name
            return lines, False, fn_name
    return lines, None, None


def main():
    dry_run = "--dry-run" in sys.argv

    with open(TARGET, encoding="utf-8") as f:
        lines = f.readlines()

    report = []
    working = lines[:]

    for tool_name in DUPLICATED_TOOLS:
        working, schema_matches = remove_schema_line(working, tool_name)
        schema_ok = len(schema_matches) == 1

        working, elif_start, elif_removed = remove_elif_block(working, tool_name)
        elif_ok = elif_start is not None

        working, import_removed, fn_name = remove_dead_legacy_import(working, tool_name)

        report.append({
            "tool": tool_name,
            "schema_matches": len(schema_matches),
            "schema_ok": schema_ok,
            "elif_lines_removed": elif_removed,
            "elif_ok": elif_ok,
            "legacy_import_removed": import_removed,
            "legacy_fn": fn_name,
        })

    print(f"Lineas originales: {len(lines)}")
    print(f"Lineas resultantes (si se aplica): {len(working)}")
    print()
    all_ok = True
    for r in report:
        ok = r["schema_ok"] and r["elif_ok"]
        all_ok = all_ok and ok
        status = "OK" if ok else "REVISAR"
        print(f"[{status}] {r['tool']}: schema_matches={r['schema_matches']} "
              f"elif_lineas_removidas={r['elif_lines_removed']} "
              f"import_legacy_removido={r['legacy_import_removed']} "
              f"fn={r['legacy_fn']}")

    if not all_ok:
        print("\nAl menos una tool no dio match limpio (schema_matches != 1 "
              "o sin bloque elif). NO SE ESCRIBIO NADA. Revisar a mano "
              "antes de reintentar.")
        sys.exit(1)

    if dry_run:
        print("\n(--dry-run: no se escribio nada)")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{TARGET}.bak.{ts}"
    shutil.copy(TARGET, backup_path)

    with open(TARGET, "w", encoding="utf-8") as f:
        f.writelines(working)

    print(f"\nPatch aplicado OK. Backup: {backup_path}")
    print("Ahora: git diff server.py (revisar a mano) y despues correr "
          "de nuevo el chequeo de duplicados antes de commitear.")


if __name__ == "__main__":
    main()
