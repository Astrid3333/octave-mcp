"""
Envuelve cada 'passed': <expr> en bool(<expr>) dentro de las 4 funciones de
validate que fallaron por numpy.bool_ no serializable:
  _validate_survey_angles, _validate_survey_distance,
  _validate_survey_curvature, _validate_survey_curves

(traverse_adjustment y area_volume no se tocan: ya casteaban con float(...)
en el código original, por eso pasaron en la corrida anterior.)

Uso:
    python3 patch_fix_bool_serialization.py
"""
import ast
import re
import shutil
from datetime import datetime

PATH = "survey_tools.py"

REPLACEMENTS = [
    # _validate_survey_angles
    (
        '"passed": abs(r1["azimuth_deg"] - 45.0) < tol, "got": r1["azimuth_deg"]',
        '"passed": bool(abs(r1["azimuth_deg"] - 45.0) < tol), "got": r1["azimuth_deg"]',
    ),
    (
        '"passed": abs(suma_ajustada - 180.0) < 1e-9 and abs(r2["misclosure_deg"] - 1.0) < tol,',
        '"passed": bool(abs(suma_ajustada - 180.0) < 1e-9 and abs(r2["misclosure_deg"] - 1.0) < tol),',
    ),
    (
        '"passed": abs(r3["overall_mean_deg"] - 10.0) < tol and abs(r3["fl_fr_spread_deg"][0]) < tol,',
        '"passed": bool(abs(r3["overall_mean_deg"] - 10.0) < tol and abs(r3["fl_fr_spread_deg"][0]) < tol),',
    ),
    # _validate_survey_distance
    (
        '"passed": abs(r1["horizontal_distance"] - 50.0) < 1e-6 and abs(r1["correction"] - 50.0) < 1e-6,',
        '"passed": bool(abs(r1["horizontal_distance"] - 50.0) < 1e-6 and abs(r1["correction"] - 50.0) < 1e-6),',
    ),
    (
        '"passed": abs(r2["horizontal_distance"] - 100.0) < tol and abs(r2["vertical_component"]) < tol,',
        '"passed": bool(abs(r2["horizontal_distance"] - 100.0) < tol and abs(r2["vertical_component"]) < tol),',
    ),
    (
        '"passed": abs(r3["corrected_distance"] - 1000.1) < 1e-6, "got": r3["corrected_distance"]',
        '"passed": bool(abs(r3["corrected_distance"] - 1000.1) < 1e-6), "got": r3["corrected_distance"]',
    ),
    # _validate_survey_curvature
    (
        '"passed": abs(r1["correction_deg"] - correction_deg_esperado) < 1e-9,',
        '"passed": bool(abs(r1["correction_deg"] - correction_deg_esperado) < 1e-9),',
    ),
    # _validate_survey_curves
    (
        '"passed": abs(r1["tangent"] - 100.0) < 1e-6, "got": r1["tangent"]',
        '"passed": bool(abs(r1["tangent"] - 100.0) < 1e-6), "got": r1["tangent"]',
    ),
    (
        '"passed": abs(r2["elev_pvc"] - 102.0) < 1e-9 and abs(r2["elev_pvt"] - 102.0) < 1e-9\n'
        '                              and abs(r2["turning_point_offset_from_pvc"] - 100.0) < 1e-9,',
        '"passed": bool(abs(r2["elev_pvc"] - 102.0) < 1e-9 and abs(r2["elev_pvt"] - 102.0) < 1e-9\n'
        '                              and abs(r2["turning_point_offset_from_pvc"] - 100.0) < 1e-9),',
    ),
]

def main():
    with open(PATH, "r", encoding="utf-8") as f:
        src = f.read()

    backup = f"{PATH}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(PATH, backup)

    applied, missing = 0, []
    for old, new in REPLACEMENTS:
        count = src.count(old)
        if count == 0:
            missing.append(old[:80])
            continue
        assert count == 1, f"Se esperaba 1 ocurrencia, se encontraron {count}: {old[:80]}"
        src = src.replace(old, new, 1)
        applied += 1

    if missing:
        print(f"ADVERTENCIA: {len(missing)} patrones no encontrados (¿el archivo cambió?):")
        for m in missing:
            print(f"  - {m}")
        print(f"Backup intacto en {backup}. No se escribió nada.")
        return

    with open(PATH, "w", encoding="utf-8") as f:
        f.write(src)

    ast.parse(src)  # valida sintaxis antes de terminar
    print(f"Patch aplicado OK ({applied}/{len(REPLACEMENTS)} reemplazos). Backup: {backup}")

if __name__ == "__main__":
    main()
