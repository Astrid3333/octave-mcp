#!/usr/bin/env python3
"""
patch_add_validate_group_ab.py

Group A: music_math_tool.py ya tenia _validate_music_math() real (de una
sesion anterior), pero el hook run_all_validations.py solo detecta un
parametro llamado literalmente "mode" con "validate" en su enum -- y
music_math usa "preset". Este patch agrega "mode" como alias sin tocar el
comportamiento existente de "preset".

Group B: agrega mode="validate" real (6 checks contra formulas cerradas de
geodesia, sin Octave) a los 6 tools de survey_tools.py: survey_angles,
survey_distance, survey_curvature, traverse_adjustment, survey_curves,
survey_area_volume. Todos los valores de referencia fueron calculados y
confirmados contra el codigo real antes de escribir este patch.

Uso:
    cd ~/octave-mcp
    python3 patch_add_validate_group_ab.py
"""
import ast

MUSIC_MATH_PATH = "music_math_tool.py"
SURVEY_TOOLS_PATH = "survey_tools.py"


def apply_replacements(path, replacements):
    with open(path, "r", encoding="utf-8") as fh:
        content = fh.read()
    for old, new, label in replacements:
        n = content.count(old)
        assert n == 1, (
            f"[{path}] Se esperaba 1 ocurrencia de bloque '{label}', se "
            f"encontraron {n} -- el archivo puede haber cambiado desde que "
            f"se escribio este patch. Revisar a mano."
        )
        content = content.replace(old, new)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


# ---------------------------------------------------------------------------
# Group A: music_math_tool.py
# ---------------------------------------------------------------------------
MUSIC_MATH_REPLACEMENTS = [
    (
        '            "preset": {\n'
        '                "type": "string",\n'
        '                "enum": ["pythagorean_comma", "temperament_comparison",\n'
        '                         "harmonic_series", "ternary_scale", "spectral_analysis", "validate"],\n'
        '                "default": "pythagorean_comma",\n'
        '            },',

        '            "preset": {\n'
        '                "type": "string",\n'
        '                "enum": ["pythagorean_comma", "temperament_comparison",\n'
        '                         "harmonic_series", "ternary_scale", "spectral_analysis", "validate"],\n'
        '                "default": "pythagorean_comma",\n'
        '            },\n'
        '            "mode": {\n'
        '                "type": "string",\n'
        '                "enum": ["validate"],\n'
        '                "description": "Alias de \'preset\' solo para mode=\'validate\' (asi lo detecta run_all_validations.py).",\n'
        '            },',
        "music_math schema mode alias",
    ),
    (
        'def compute_music_math(preset="pythagorean_comma", f0=220.0, n_harmonics=8,\n'
        '                        n_power=2, signal=None, fs=44100, **kwargs):\n'
        '    if preset == "validate":\n'
        '        return _validate_music_math()',

        'def compute_music_math(preset="pythagorean_comma", f0=220.0, n_harmonics=8,\n'
        '                        n_power=2, signal=None, fs=44100, mode=None, **kwargs):\n'
        '    if preset == "validate" or mode == "validate":\n'
        '        return _validate_music_math()',
        "music_math dispatch mode alias",
    ),
]

# ---------------------------------------------------------------------------
# Group B: survey_tools.py
# ---------------------------------------------------------------------------
VALIDATE_FUNCTIONS_BLOCK = '''

# ---------------------------------------------------------------------------
# VALIDACION: mode="validate" en cada tool, formulas cerradas sin Octave.
# Todos los casos son geometria/trigonometria exacta o casos de libro con
# tolerancia chica -- no requieren subprocess ni datos externos.
# ---------------------------------------------------------------------------
def _validate_survey_angles():
    checks = []
    tol = 1e-6

    r1 = compute_survey_angles("bearing_azimuth", delta_e=1, delta_n=1)
    checks.append({"name": "bearing_azimuth: delta_e=delta_n=1 -> azimut=45 exacto",
                    "passed": abs(r1["azimuth_deg"] - 45.0) < tol, "got": r1["azimuth_deg"]})

    r2 = compute_survey_angles("angle_closure", angles=[60, 60, 61])
    suma_ajustada = sum(r2["adjusted_angles_deg"])
    checks.append({"name": "angle_closure: triangulo con misclosure=1 -> suma ajustada=180 exacto",
                    "passed": abs(suma_ajustada - 180.0) < 1e-9 and abs(r2["misclosure_deg"] - 1.0) < tol,
                    "got": {"misclosure": r2["misclosure_deg"], "suma_ajustada": suma_ajustada}})

    r3 = compute_survey_angles("mean_angle_reduction", face_left=[10], face_right=[190])
    checks.append({"name": "mean_angle_reduction: FL=10,FR=190 (180 exacto de diferencia) -> mean=10, spread=0",
                    "passed": abs(r3["overall_mean_deg"] - 10.0) < tol and abs(r3["fl_fr_spread_deg"][0]) < tol,
                    "got": {"mean": r3["overall_mean_deg"], "spread": r3["fl_fr_spread_deg"][0]}})

    return {"mode": "validate", "validation_passed": all(c["passed"] for c in checks), "checks": checks}


def _validate_survey_distance():
    checks = []
    tol = 1e-6

    r1 = compute_survey_distance("slope_correction", slope_distance=100, angle_deg=60, method="angle")
    checks.append({"name": "slope_correction: L=100, angulo=60 -> horizontal=50, correction=50 exacto",
                    "passed": abs(r1["horizontal_distance"] - 50.0) < 1e-6 and abs(r1["correction"] - 50.0) < 1e-6,
                    "got": {"horizontal": r1["horizontal_distance"], "correction": r1["correction"]}})

    r2 = compute_survey_distance("stadia", k=100, s=1, angle_deg=0, c=0)
    checks.append({"name": "stadia: k=100,s=1,angulo=0 -> horizontal=100, vertical=0 exacto",
                    "passed": abs(r2["horizontal_distance"] - 100.0) < tol and abs(r2["vertical_component"]) < tol,
                    "got": {"horizontal": r2["horizontal_distance"], "vertical": r2["vertical_component"]}})

    r3 = compute_survey_distance("edm_correction", measured_distance=1000, delta_n=0.0001, n0=1)
    checks.append({"name": "edm_correction: 1000m + 100ppm -> corregida=1000.1 exacto",
                    "passed": abs(r3["corrected_distance"] - 1000.1) < 1e-6, "got": r3["corrected_distance"]})

    return {"mode": "validate", "validation_passed": all(c["passed"] for c in checks), "checks": checks}


def _validate_survey_curvature():
    import numpy as np
    checks = []
    d, k, R = 10000.0, 0.13, 6371000.0
    correction_deg_esperado = float(np.degrees((1 - k) * d / (2 * R)))

    r1 = compute_survey_curvature("curvature_refraction", observed_angle_deg=0, distance=d, k=k, R=R, direction="add")
    checks.append({"name": "curvature_refraction: formula (1-k)*d/(2R) vs calculo directo, 10km, k=0.13",
                    "passed": abs(r1["correction_deg"] - correction_deg_esperado) < 1e-9,
                    "got": {"correction_deg": r1["correction_deg"], "esperado": correction_deg_esperado}})

    return {"mode": "validate", "validation_passed": all(c["passed"] for c in checks), "checks": checks}


def _validate_traverse_adjustment():
    checks = []
    # cuadrado cerrado 100x100: azimuts 0/90/180/270 -> misclosure exacto 0
    sides = [
        {"length": 100, "bearing_deg": 0}, {"length": 100, "bearing_deg": 90},
        {"length": 100, "bearing_deg": 180}, {"length": 100, "bearing_deg": 270},
    ]
    r1 = compute_traverse_adjustment("linear_misclosure", sides=sides)
    checks.append({"name": "linear_misclosure: cuadrado 100x100 cerrado exacto -> misclosure ~0",
                    "passed": r1["linear_misclosure"] < 1e-6, "got": r1["linear_misclosure"]})

    return {"mode": "validate", "validation_passed": all(c["passed"] for c in checks), "checks": checks}


def _validate_survey_curves():
    import numpy as np
    checks = []

    r1 = compute_survey_curves("horizontal_circular", radius=100, delta_deg=90)
    checks.append({"name": "horizontal_circular: R=100, delta=90 -> tangent=R*tan(45)=100 exacto",
                    "passed": abs(r1["tangent"] - 100.0) < 1e-6, "got": r1["tangent"]})

    r2 = compute_survey_curves("vertical_parabolic", g1_pct=-2, g2_pct=2, length=200, elev_pvi=100, station_pvi=0)
    checks.append({"name": "vertical_parabolic: curva simetrica g1=-2,g2=2 -> elev_pvc==elev_pvt==102, punto bajo en el centro",
                    "passed": abs(r2["elev_pvc"] - 102.0) < 1e-9 and abs(r2["elev_pvt"] - 102.0) < 1e-9
                              and abs(r2["turning_point_offset_from_pvc"] - 100.0) < 1e-9,
                    "got": {"elev_pvc": r2["elev_pvc"], "elev_pvt": r2["elev_pvt"],
                            "turning_offset": r2["turning_point_offset_from_pvc"]}})

    return {"mode": "validate", "validation_passed": all(c["passed"] for c in checks), "checks": checks}


def _validate_survey_area_volume():
    checks = []

    r1 = compute_survey_area_volume("polygon_shoelace", points=[[0, 0], [10, 0], [10, 10], [0, 10]])
    checks.append({"name": "polygon_shoelace: cuadrado 10x10 -> area=100 exacto",
                    "passed": abs(r1["area"] - 100.0) < 1e-9, "got": r1["area"]})

    r2 = compute_survey_area_volume("earthwork_avg_end_area", areas=[10, 20, 10], station_interval=10)
    checks.append({"name": "earthwork_avg_end_area: areas=[10,20,10], interval=10 -> total=300 exacto",
                    "passed": abs(r2["total_volume"] - 300.0) < 1e-9, "got": r2["total_volume"]})

    r3 = compute_survey_area_volume("contour_volume", contour_areas=[100, 80, 60], contour_interval=5, method="average_end_area")
    checks.append({"name": "contour_volume average_end_area: [100,80,60], h=5 -> total=800 exacto",
                    "passed": abs(r3["total_volume"] - 800.0) < 1e-9, "got": r3["total_volume"]})

    return {"mode": "validate", "validation_passed": all(c["passed"] for c in checks), "checks": checks}

'''

SURVEY_REPLACEMENTS = [
    # insertar el bloque de funciones de validacion justo antes de la seccion de SCHEMAS
    (
        '# ---------------------------------------------------------------------------\n'
        '# SCHEMAS (para TOOLS list en server.py)\n'
        '# ---------------------------------------------------------------------------',

        VALIDATE_FUNCTIONS_BLOCK.strip("\n") + "\n\n\n"
        '# ---------------------------------------------------------------------------\n'
        '# SCHEMAS (para TOOLS list en server.py)\n'
        '# ---------------------------------------------------------------------------',
        "bloque de funciones _validate_*",
    ),
    # wiring: dispatch de mode=="validate" al inicio de cada compute_X + agregar
    # "validate" al enum del schema correspondiente
    (
        'def compute_survey_angles(mode, **params):\n'
        '    if mode == "bearing_azimuth":',

        'def compute_survey_angles(mode, **params):\n'
        '    if mode == "validate":\n'
        '        return _validate_survey_angles()\n'
        '    if mode == "bearing_azimuth":',
        "dispatch survey_angles",
    ),
    (
        '            "mode": {"type": "string", "enum": ["bearing_azimuth", "angle_closure", "mean_angle_reduction"]},',
        '            "mode": {"type": "string", "enum": ["bearing_azimuth", "angle_closure", "mean_angle_reduction", "validate"]},',
        "schema enum survey_angles",
    ),
    (
        'def compute_survey_distance(mode, **params):\n'
        '    if mode == "slope_correction":',

        'def compute_survey_distance(mode, **params):\n'
        '    if mode == "validate":\n'
        '        return _validate_survey_distance()\n'
        '    if mode == "slope_correction":',
        "dispatch survey_distance",
    ),
    (
        '            "mode": {"type": "string", "enum": ["slope_correction", "stadia", "edm_correction"]},',
        '            "mode": {"type": "string", "enum": ["slope_correction", "stadia", "edm_correction", "validate"]},',
        "schema enum survey_distance",
    ),
    (
        'def compute_survey_curvature(mode="curvature_refraction", **params):\n'
        '    if mode != "curvature_refraction":\n'
        '        raise ValueError(f"Modo desconocido para survey_curvature: {mode}")',

        'def compute_survey_curvature(mode="curvature_refraction", **params):\n'
        '    if mode == "validate":\n'
        '        return _validate_survey_curvature()\n'
        '    if mode != "curvature_refraction":\n'
        '        raise ValueError(f"Modo desconocido para survey_curvature: {mode}")',
        "dispatch survey_curvature",
    ),
    (
        '            "mode": {"type": "string", "enum": ["curvature_refraction"]},',
        '            "mode": {"type": "string", "enum": ["curvature_refraction", "validate"]},',
        "schema enum survey_curvature",
    ),
    (
        'def compute_traverse_adjustment(mode, **params):\n'
        '    sides = params.get("sides")',

        'def compute_traverse_adjustment(mode, **params):\n'
        '    if mode == "validate":\n'
        '        return _validate_traverse_adjustment()\n'
        '    sides = params.get("sides")',
        "dispatch traverse_adjustment",
    ),
    (
        '                "enum": ["bowditch", "transit_rule", "closure_check", "linear_misclosure", "relative_accuracy", "full_traverse"],',
        '                "enum": ["bowditch", "transit_rule", "closure_check", "linear_misclosure", "relative_accuracy", "full_traverse", "validate"],',
        "schema enum traverse_adjustment",
    ),
    (
        'def compute_survey_curves(mode, **params):\n'
        '    if mode == "horizontal_circular":',

        'def compute_survey_curves(mode, **params):\n'
        '    if mode == "validate":\n'
        '        return _validate_survey_curves()\n'
        '    if mode == "horizontal_circular":',
        "dispatch survey_curves",
    ),
    (
        '            "mode": {"type": "string", "enum": ["horizontal_circular", "vertical_parabolic"]},',
        '            "mode": {"type": "string", "enum": ["horizontal_circular", "vertical_parabolic", "validate"]},',
        "schema enum survey_curves",
    ),
    (
        'def compute_survey_area_volume(mode, **params):\n'
        '    if mode == "polygon_shoelace":',

        'def compute_survey_area_volume(mode, **params):\n'
        '    if mode == "validate":\n'
        '        return _validate_survey_area_volume()\n'
        '    if mode == "polygon_shoelace":',
        "dispatch survey_area_volume",
    ),
    (
        '            "mode": {"type": "string", "enum": ["polygon_shoelace", "earthwork_avg_end_area", "contour_volume"]},',
        '            "mode": {"type": "string", "enum": ["polygon_shoelace", "earthwork_avg_end_area", "contour_volume", "validate"]},',
        "schema enum survey_area_volume",
    ),
]

# required: agrega "sides" opcional en la practica para mode=validate (validate
# no manda sides), pero como compute_traverse_adjustment ya usa params.get()
# (no accede directo a params["sides"]) y el "required" del schema es solo
# informativo para el llamador MCP, no se toca "required".

# nota: run_all_validations.py llama con arguments={"mode":"validate","params":{}}
# es decir params={} se pasa como kwarg 'params', no como **params -- las 6
# funciones reciben (mode, **params) por lo que "params={}" entra como
# params["params"]={}, inofensivo porque el bloque validate corta antes de
# tocar cualquier clave de params.


def main():
    apply_replacements(MUSIC_MATH_PATH, MUSIC_MATH_REPLACEMENTS)
    apply_replacements(SURVEY_TOOLS_PATH, SURVEY_REPLACEMENTS)

    for path in (MUSIC_MATH_PATH, SURVEY_TOOLS_PATH):
        ast.parse(open(path, encoding="utf-8").read())

    print("Patch aplicado OK")


if __name__ == "__main__":
    main()
