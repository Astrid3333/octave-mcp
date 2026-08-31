"""
femur_biomechanics_tool.py

Datos de referencia geometricos y mecanicos del femur humano (fuente:
Losa Zapico, P. "Diseno de una protesis liviana de cadera con la
posibilidad de incorporar medicacion", TFG UPM 2018, Tabla 3.1 y 3.2),
mas un modo de chequeo de tension aplicada contra los limites de
resistencia del hueso cortical. Pensada como complemento de referencia
para socket_pattern_operations / freecad-organic (interfaz socket-femur)
y para fault/structural tools que necesiten un limite de resistencia osea.

Patron: compute_femur_biomechanics_tool(mode, **kwargs) + FEMUR_BIOMECHANICS_TOOL_SCHEMA
Auto-registro via register_tool (mismo patron que biodiversity_model_tool).

Modos:
  - geometry_reference : Tabla 3.1, dimensiones medias del femur (mm) y rango poblacional
  - cortical_strength_reference : Tabla 3.2, resistencia maxima del hueso cortical (MPa)
                                   por direccion (transversal/longitudinal) y tipo de carga
  - young_modulus      : modulo de Young del hueso cortical (17 GPa axial, 11 GPa transversal)
  - stress_check        : compara una tension aplicada contra el limite de Tabla 3.2 y
                           devuelve factor de seguridad
  - validate             : autotest

ADVERTENCIA DE CONFIANZA: los datos de las filas G/H/I de geometry_reference
tienen inconsistencias en la tabla ORIGINAL del TFG (la media de G cae fuera
de su propio rango, y H/I comparten un rango identico) -- se preservan tal
cual estan en la fuente, marcadas con confidence="low_source_inconsistency",
en vez de "corregirlas" por suposicion.
"""

try:
    from tool_registry import register_tool
except ImportError:
    register_tool = None


# Tabla 3.1 -- Dimensiones medias del femur (mm), poblacion adulta
# fuente: TFG Losa Zapico 2018, Fig 3.4 / Tabla 3.1
_GEOMETRY_TABLE = {
    "longitud": {"label": "Longitud", "mean_mm": 443.6, "range_mm": [402.0, 486.0], "confidence": "ok"},
    "A_offset_cabeza_femoral": {"label": "Offset de la cabeza femoral", "mean_mm": 47.0, "range_mm": [33.2, 62.8], "confidence": "ok"},
    "B_diametro_cabeza_femoral": {"label": "Diametro de la cabeza femoral", "mean_mm": 43.4, "range_mm": [39.3, 48.3], "confidence": "ok"},
    "C_posicion_cabeza_femoral": {"label": "Posicion de la cabeza femoral", "mean_mm": 56.1, "range_mm": [35.8, 70.2], "confidence": "ok"},
    "D_ancho_canal_medular_20mm_encima_troncater": {"label": "Ancho canal medular (20mm por encima del troncater menor)", "mean_mm": 43.1, "range_mm": [23.0, 35.9], "confidence": "ok"},
    "E_ancho_canal_medular_altura_troncater": {"label": "Ancho canal medular (a la altura del troncater menor)", "mean_mm": 27.9, "range_mm": [17.3, 26.4], "confidence": "ok"},
    "F_ancho_canal_medular_20mm_debajo_troncater": {"label": "Ancho canal medular (20mm por debajo del troncater menor)", "mean_mm": 21.0, "range_mm": [9.1, 18.3], "confidence": "ok"},
    "G_ancho_canal_nivel_istmo": {"label": "Ancho de canal al nivel del istmo", "mean_mm": 13.1, "range_mm": [23.1, 31.9], "confidence": "low_source_inconsistency", "note": "la media (13.1) cae fuera de su propio rango en la tabla original del TFG -- posible error de imprenta/copy-paste, se preserva tal cual"},
    "H_ancho_periostio_nivel_istmo": {"label": "Ancho del periostio al nivel del istmo", "mean_mm": 26.7, "range_mm": [100.7, 137.8], "confidence": "low_source_inconsistency", "note": "comparte rango identico con la fila I (angulo) en la tabla original -- posible error de imprenta, se preserva tal cual"},
    "I_angulo_cuello_vertical_deg": {"label": "Angulo entre el cuello y la vertical", "mean_deg": 124.8, "range_deg": [100.7, 137.8], "confidence": "low_source_inconsistency", "note": "comparte rango identico con la fila H en la tabla original -- posible error de imprenta, se preserva tal cual"},
}

# Tabla 3.2 -- Esfuerzos maximos permitidos en el hueso cortical (MPa)
# fuente: TFG Losa Zapico 2018, Tabla 3.2
_CORTICAL_STRENGTH_TABLE = {
    "transversal": {"traccion_mpa": 33.0, "compresion_mpa": 33.0, "cortante_mpa": None},
    "longitudinal": {"traccion_mpa": 133.0, "compresion_mpa": 193.0, "cortante_mpa": 68.0},
}

# Modulo de Young del hueso cortical, fuente: TFG Losa Zapico 2018, seccion 3.1.3
_YOUNG_MODULUS_GPA = {"longitudinal_axial": 17.0, "transversal": 11.0}


def _geometry_reference(param=None):
    if param is not None:
        if param not in _GEOMETRY_TABLE:
            raise ValueError(f"param desconocido: {param}. Opciones: {sorted(_GEOMETRY_TABLE.keys())}")
        return {param: _GEOMETRY_TABLE[param]}
    return dict(_GEOMETRY_TABLE)


def _cortical_strength_reference(direction=None):
    if direction is not None:
        direction = direction.lower()
        if direction not in _CORTICAL_STRENGTH_TABLE:
            raise ValueError("direction debe ser 'transversal' o 'longitudinal'")
        return {direction: _CORTICAL_STRENGTH_TABLE[direction]}
    return dict(_CORTICAL_STRENGTH_TABLE)


def _young_modulus(direction=None):
    if direction is not None:
        direction = direction.lower()
        if direction not in _YOUNG_MODULUS_GPA:
            raise ValueError("direction debe ser 'longitudinal_axial' o 'transversal'")
        return {direction: _YOUNG_MODULUS_GPA[direction]}
    return dict(_YOUNG_MODULUS_GPA)


def _stress_check(applied_stress_mpa, direction, load_type):
    direction = direction.lower()
    load_type = load_type.lower()
    if direction not in _CORTICAL_STRENGTH_TABLE:
        raise ValueError("direction debe ser 'transversal' o 'longitudinal'")
    key_map = {"traccion": "traccion_mpa", "tension": "traccion_mpa", "compresion": "compresion_mpa", "cortante": "cortante_mpa", "cortadura": "cortante_mpa"}
    if load_type not in key_map:
        raise ValueError("load_type debe ser 'traccion', 'compresion' o 'cortante'")
    limit = _CORTICAL_STRENGTH_TABLE[direction][key_map[load_type]]
    if limit is None:
        raise ValueError(f"No hay dato de resistencia a cortante en direccion '{direction}' en la tabla fuente")
    if applied_stress_mpa < 0:
        raise ValueError("applied_stress_mpa debe ser >= 0 (magnitud de tension)")
    safety_factor = limit / applied_stress_mpa if applied_stress_mpa > 0 else float("inf")
    return {
        "direction": direction,
        "load_type": load_type,
        "applied_stress_mpa": applied_stress_mpa,
        "allowable_stress_mpa": limit,
        "safety_factor": safety_factor,
        "exceeds_limit": applied_stress_mpa > limit,
    }


def _validate():
    checks = []

    r1 = _geometry_reference("longitud")
    ok1 = abs(r1["longitud"]["mean_mm"] - 443.6) < 1e-9
    checks.append(("geometry_reference_longitud_mean", ok1))

    r2 = _geometry_reference()
    ok2 = len(r2) == 10 and "I_angulo_cuello_vertical_deg" in r2
    checks.append(("geometry_reference_full_table_10_rows", ok2))

    r3 = _cortical_strength_reference("longitudinal")
    ok3 = r3["longitudinal"]["compresion_mpa"] == 193.0 and r3["longitudinal"]["cortante_mpa"] == 68.0
    checks.append(("cortical_strength_longitudinal_values", ok3))

    r4 = _cortical_strength_reference("transversal")
    ok4 = r4["transversal"]["cortante_mpa"] is None
    checks.append(("cortical_strength_transversal_no_shear_data", ok4))

    r5 = _young_modulus()
    ok5 = r5["longitudinal_axial"] == 17.0 and r5["transversal"] == 11.0
    checks.append(("young_modulus_values", ok5))

    # tension aplicada igual al limite -> safety_factor == 1, no excede
    r6 = _stress_check(133.0, "longitudinal", "traccion")
    ok6 = abs(r6["safety_factor"] - 1.0) < 1e-9 and r6["exceeds_limit"] is False
    checks.append(("stress_check_at_limit_sf_eq_1", ok6))

    # tension aplicada por sobre el limite -> exceeds_limit True, sf < 1
    r7 = _stress_check(200.0, "transversal", "compresion")
    ok7 = r7["exceeds_limit"] is True and r7["safety_factor"] < 1.0
    checks.append(("stress_check_over_limit_flagged", ok7))

    # tension 0 -> safety_factor infinito
    r8 = _stress_check(0.0, "longitudinal", "cortante")
    ok8 = r8["safety_factor"] == float("inf")
    checks.append(("stress_check_zero_stress_inf_sf", ok8))

    passed = sum(1 for _, ok in checks if ok)
    return {
        "mode": "validate",
        "checks": [{"name": n, "passed": ok} for n, ok in checks],
        "passed": passed,
        "total": len(checks),
        "all_passed": passed == len(checks),
    }


FEMUR_BIOMECHANICS_TOOL_SCHEMA = {
    "name": "femur_biomechanics_tool",
    "description": (
        "Datos de referencia geometricos (Tabla 3.1: longitud, offset/diametro/posicion de "
        "cabeza femoral, anchos de canal medular, angulo cuello-vertical) y mecanicos "
        "(Tabla 3.2: resistencia maxima del hueso cortical a traccion/compresion/cortante por "
        "direccion, y modulo de Young 17 GPa axial / 11 GPa transversal) del femur humano, "
        "fuente TFG Losa Zapico UPM 2018. Incluye un chequeo de tension aplicada vs limite de "
        "resistencia osea (stress_check). No reemplaza analisis FEM ni datos clinicos "
        "individualizados; valores poblacionales de referencia."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["geometry_reference", "cortical_strength_reference", "young_modulus", "stress_check", "validate"],
                "description": "Operacion a realizar, o 'validate' para autotest",
            },
            "param": {"type": "string", "description": "geometry_reference: clave especifica de la tabla (opcional, si se omite devuelve toda la tabla)"},
            "direction": {"type": "string", "enum": ["transversal", "longitudinal", "longitudinal_axial"], "description": "cortical_strength_reference / young_modulus / stress_check: direccion de carga"},
            "load_type": {"type": "string", "enum": ["traccion", "compresion", "cortante"], "description": "stress_check: tipo de carga"},
            "applied_stress_mpa": {"type": "number", "description": "stress_check: magnitud de la tension aplicada, en MPa"},
        },
        "required": ["mode"],
    },
}


def compute_femur_biomechanics_tool(mode, **kwargs):
    if mode == "validate":
        return _validate()
    elif mode == "geometry_reference":
        return {"mode": mode, "data": _geometry_reference(kwargs.get("param"))}
    elif mode == "cortical_strength_reference":
        return {"mode": mode, "data": _cortical_strength_reference(kwargs.get("direction"))}
    elif mode == "young_modulus":
        return {"mode": mode, "data": _young_modulus(kwargs.get("direction"))}
    elif mode == "stress_check":
        applied = kwargs.get("applied_stress_mpa")
        direction = kwargs.get("direction")
        load_type = kwargs.get("load_type")
        if applied is None or direction is None or load_type is None:
            raise ValueError("stress_check requiere 'applied_stress_mpa', 'direction' y 'load_type'")
        return {"mode": mode, **_stress_check(float(applied), direction, load_type)}
    else:
        raise ValueError(f"Modo desconocido: {mode}")


if __name__ == "__main__":
    import json
    print(json.dumps(compute_femur_biomechanics_tool(mode="validate"), indent=2, ensure_ascii=False))


try:
    from tool_registry import register_tool as _register_tool_real
    _register_tool_real(
        name="femur_biomechanics_tool",
        schema=FEMUR_BIOMECHANICS_TOOL_SCHEMA,
        handler=lambda args: compute_femur_biomechanics_tool(
            args.get("mode"),
            **{k: v for k, v in args.items() if k != "mode"}
        ),
    )
except ImportError:
    pass
