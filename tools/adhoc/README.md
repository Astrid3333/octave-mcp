# tools/adhoc

Scripts de wireo/patch de una sola vez, ya aplicados al código actual.
Se conservan como referencia histórica de cómo se integró cada tool o
fix (mismo criterio que tools/migration/ y tools/patches/), no se
ejecutan de nuevo.

- wire_*.py: registran tools puntuales en server.py (bio tools, mesh
  spectral, sdf, structural analysis, quantity takeoff, etc.)
- patch_*.py: agregan modo 'validate' a enums de tools existentes,
  agregan entradas a ALTERNATE_VALIDATE_MODE en run_all_validations.py,
  o insertan funciones nuevas (ej. patch_frenet_3d.py en plotting_tools.py)

Confirmado (23-ago-2026): las tools/archivos que estos 25 scripts
tocan ya están presentes en el código actual -- ninguno quedó
pendiente de aplicar.
