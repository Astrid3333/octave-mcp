#!/usr/bin/env python3
"""
patch_update_readme.py

Tres correcciones triviales al README:
  1. Conteo de tools: "125+" -> "241" (linea 2, desactualizado desde
     hace varias tandas, confirmado por run_all_validations.py).
  2. Nota de dependencia opcional: paquete Octave symbolic, usado por
     el check nuevo de statmech_partition_tool (skipped si no esta).
  3. statmech_partition_tool agregado a la lista de "Fisica y quimica"
     (faltaba desde que se creo la tool, gap preexistente).

Uso:
  python3 patch_update_readme.py --dry-run
  python3 patch_update_readme.py
"""
import shutil
import sys
from pathlib import Path

DRY = "--dry-run" in sys.argv
F = Path("README.md")
src = F.read_text()


def report(ok, msg):
    print(("OK -- " if ok else "FALLO -- ") + msg)
    return ok


old_count = "Servidor MCP (JSON-RPC manual, sin FastMCP) que expone 125+ herramientas matemáticas y de simulación científica sobre Octave/Python, pensadas para usarse desde Claude Desktop u otros clientes MCP."
new_count = "Servidor MCP (JSON-RPC manual, sin FastMCP) que expone 241 herramientas matemáticas y de simulación científica sobre Octave/Python, pensadas para usarse desde Claude Desktop u otros clientes MCP."
ok1 = report(old_count in src, "anchor del conteo de tools encontrado")

old_deps = "- Dependencias: numpy, sympy y scipy (`advanced_probability_tool`, `advanced_stochastic_tool` y `multivariate_bayes_tool` dependen de scipy.stats)."
new_deps = ("- Dependencias: numpy, sympy y scipy (`advanced_probability_tool`, `advanced_stochastic_tool` y `multivariate_bayes_tool` dependen de scipy.stats).\n"
            "- Dependencia opcional: paquete Octave `symbolic` (`pkg install -forge symbolic`) para el check simbolico de `statmech_partition_tool`; si no esta instalado, ese check se salta (`skipped`) sin afectar el resultado global de `validate`.")
ok2 = report(old_deps in src, "anchor de Dependencias encontrado")

old_fisica = "`quantum_information`, `qm_potential_well`, `nuclear_decay_chain`, `enzyme_kinetics`, `antibiotic_diffusion`, `population_genetics`, `braid_group`, `tritbraid`, `statistical_physics_tool`, `cfd_tool`"
new_fisica = old_fisica + ", `statmech_partition_tool`"
ok3 = report(old_fisica in src, "anchor de Fisica y quimica encontrado")

all_ok = ok1 and ok2 and ok3

if all_ok and not DRY:
    src = src.replace(old_count, new_count)
    src = src.replace(old_deps, new_deps)
    src = src.replace(old_fisica, new_fisica)
    shutil.copy(F, F.with_suffix(".md.bak"))
    print(f"  (backup en {F.with_suffix('.md.bak')})")
    F.write_text(src)

print()
if DRY:
    print("--dry-run: no escribi nada. Corre sin esa flag para aplicar.")
else:
    print("Aplicado (si los 3 anchors dieron OK).")
