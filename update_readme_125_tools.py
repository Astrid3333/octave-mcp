"""
Actualiza README.md: conteo real de tools (121 -> 125, via tools/list) y agrega
seccion documentando gas_tool y knowledge_graph_tool. Backup timestamped.
"""
import shutil
from datetime import datetime

README = "README.md"

with open(README, "r") as f:
    content = f.read()

backup_name = f"{README}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
shutil.copy(README, backup_name)
print(f"Backup: {backup_name}")

replacements = [
    ("que expone 121 herramientas", "que expone 125 herramientas"),
    ("*Total: 121 herramientas registradas", "*Total: 125 herramientas registradas"),
    ("octave-mcp: 88 -> 121 tools.", "octave-mcp: 88 -> 125 tools."),
]

for old, new in replacements:
    if old not in content:
        print(f"AVISO: no encontrado '{old}' (¿ya estaba actualizado?)")
        continue
    assert content.count(old) == 1, f"'{old}' no es unico en el archivo"
    content = content.replace(old, new)
    print(f"OK: '{old}' -> '{new}'")

new_section = """
## Gases y Exploracion del Catalogo

- **gas_tool**: gas ideal (`PV=nRT`); gases reales via Van der Waals (cubica exacta,
  Cardano), Dieterici, Berthelot y Redlich-Kwong (Newton-Raphson para V dado P);
  mezclas (Dalton, Amagat, entropia y Gibbs de mezcla); teoria cinetica molecular
  (velocidades caracteristicas, distribucion de Maxwell-Boltzmann, ley de Graham);
  flujo compresible (numero de Mach, proceso adiabatico, ondas de choque normal
  via Rankine-Hugoniot, relacion area-Mach en toberas); fugacidad via integracion
  numerica de (Z-1)dP/P. Validado contra STP (V_m=22.414 L), tablas NACA 1135
  (M1=2 -> M2=0.5774, P2/P1=4.5) y round-trip P->V->P en las 4 ecuaciones de estado.
- **knowledge_graph_tool**: guia de exploracion sobre el propio catalogo de tools.
  `mode=search`: busca tools relevantes para una consulta en lenguaje natural
  (scoring lexico sobre nombre+descripcion). `mode=related`: dado el nombre de una
  tool, encuentra otras que comparten vocabulario. `mode=stats`: panorama del
  catalogo completo. Se deriva en vivo de `TOOLS` (recibido por parametro desde el
  dispatcher) — no mantiene un grafo aparte, se actualiza solo cuando se agregan
  tools nuevas.
"""

marker = "Pendiente: conectores externos (FreeCAD, BIM/IFC) — oCAS ya integrado.\n"
if marker in content:
    assert content.count(marker) == 1, "marker de seccion final no es unico"
    content = content.replace(marker, marker + new_section)
    print("Seccion de gas_tool/knowledge_graph_tool agregada.")
else:
    print("AVISO: no encontre el marker de cierre esperado, seccion no agregada. Revisar a mano.")

with open(README, "w") as f:
    f.write(content)

print("README.md actualizado. Revisa el diff antes de commitear:")
print("  git diff README.md | cat")
