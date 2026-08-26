"""
angle_math_tool.py

Utilidad de trigonometría y geometría de ángulos: funciones trig directas
e inversas, conversión grados/radianes, resolución de triángulos (ley de
senos/cosenos), y cálculo de rumbo/distancia entre dos puntos 2D.

Pensado como utilidad compartida para otras tools del repo que ya hacen
sus propios cálculos trig ad-hoc (navegación, geoespacial, incendios),
para no duplicar fórmulas.

Modes:
  - trig: sin/cos/tan/asin/acos/atan de un valor
  - atan2: arctan2(y, x), correcto en los 4 cuadrantes
  - convert: grados <-> radianes
  - solve_triangle: dado un set consistente de lados/ángulos, resuelve el resto
    (soporta SSS, SAS, ASA/AAS, y SSA con detección del caso ambiguo)
  - bearing_distance: rumbo (desde el norte, sentido horario) y distancia
    euclidiana entre dos puntos (x1,y1) -> (x2,y2)
  - validate: self-tests

Patrón de registro: idéntico al de spectroscopy_tool.py — TOOL_NAME,
TOOL_MODES, _dispatch(mode, params), run_self_test(), run(arguments),
TOOL_SCHEMA, _register() vía tool_registry.register_tool(TOOL_NAME, run,
modes=TOOL_MODES), llamado desde `if __name__ == '__main__':`.
"""

import math
from typing import Dict, Optional


# ============================================================================
# TRIGONOMETRÍA DIRECTA E INVERSA
# ============================================================================

_DIRECT_TRIG = {'sin': math.sin, 'cos': math.cos, 'tan': math.tan}
_INVERSE_TRIG = {'asin': math.asin, 'acos': math.acos, 'atan': math.atan}


def _trig(function: str, value: float, angle_unit: str = 'deg') -> Dict:
    """
    Evalúa una función trigonométrica directa o inversa.

    Directas (sin, cos, tan): 'value' es un ángulo en 'angle_unit',
    el resultado es adimensional.
    Inversas (asin, acos, atan): 'value' es adimensional (para asin/acos
    debe estar en [-1, 1]), el resultado es un ángulo en 'angle_unit'.
    """
    if angle_unit not in ('deg', 'rad'):
        return {'error': f'Unidad de ángulo desconocida: {angle_unit}. Válidas: deg, rad'}

    if function in _DIRECT_TRIG:
        angle_rad = math.radians(value) if angle_unit == 'deg' else value
        result = _DIRECT_TRIG[function](angle_rad)
        return {
            'function': function,
            'input_value': value,
            'input_unit': angle_unit,
            'result': result,
        }

    elif function in _INVERSE_TRIG:
        if function in ('asin', 'acos') and not (-1.0 - 1e-9 <= value <= 1.0 + 1e-9):
            return {'error': f'{function} requiere un valor en [-1, 1], se recibió {value}'}
        clamped = max(-1.0, min(1.0, value)) if function in ('asin', 'acos') else value
        angle_rad = _INVERSE_TRIG[function](clamped)
        result = math.degrees(angle_rad) if angle_unit == 'deg' else angle_rad
        return {
            'function': function,
            'input_value': value,
            'result': result,
            'output_unit': angle_unit,
        }

    else:
        valid = list(_DIRECT_TRIG.keys()) + list(_INVERSE_TRIG.keys())
        return {'error': f'Función desconocida: {function}. Válidas: {valid}'}


def _atan2(y: float, x: float, angle_unit: str = 'deg', normalize_360: bool = False) -> Dict:
    """arctan2(y, x), correcto en los 4 cuadrantes."""
    if angle_unit not in ('deg', 'rad'):
        return {'error': f'Unidad de ángulo desconocida: {angle_unit}. Válidas: deg, rad'}

    angle_rad = math.atan2(y, x)
    if normalize_360 and angle_rad < 0:
        angle_rad += 2 * math.pi

    result = math.degrees(angle_rad) if angle_unit == 'deg' else angle_rad
    return {
        'y': y,
        'x': x,
        'result': result,
        'angle_unit': angle_unit,
        'normalized_360': normalize_360,
    }


def _convert_angle(value: float, unit: str) -> Dict:
    """Convierte un ángulo entre grados y radianes."""
    if unit == 'deg':
        return {'input_value': value, 'input_unit': 'deg', 'degrees': value, 'radians': math.radians(value)}
    elif unit == 'rad':
        return {'input_value': value, 'input_unit': 'rad', 'degrees': math.degrees(value), 'radians': value}
    else:
        return {'error': f'Unidad desconocida: {unit}. Válidas: deg, rad'}


# ============================================================================
# RESOLUCIÓN DE TRIÁNGULOS (LEY DE SENOS / COSENOS)
# ============================================================================

def _law_of_cosines_angle(opposite_side: float, side1: float, side2: float) -> float:
    """Ángulo (rad) opuesto a 'opposite_side', dados los otros dos lados."""
    cos_val = (side1 ** 2 + side2 ** 2 - opposite_side ** 2) / (2 * side1 * side2)
    cos_val = max(-1.0, min(1.0, cos_val))  # clamp por seguridad de punto flotante
    return math.acos(cos_val)


def _law_of_cosines_side(angle_rad: float, side1: float, side2: float) -> float:
    """Lado opuesto a 'angle_rad', dados los dos lados adyacentes."""
    return math.sqrt(side1 ** 2 + side2 ** 2 - 2 * side1 * side2 * math.cos(angle_rad))


def _law_of_sines_side(known_side: float, known_angle_rad: float, target_angle_rad: float) -> float:
    """a/sin(A) = b/sin(B)  =>  b = a · sin(B) / sin(A)"""
    return known_side * math.sin(target_angle_rad) / math.sin(known_angle_rad)


_INCLUDED_ANGLE = {frozenset('ab'): 'C', frozenset('ac'): 'B', frozenset('bc'): 'A'}


def _solve_triangle(a: Optional[float] = None, b: Optional[float] = None, c: Optional[float] = None,
                     A: Optional[float] = None, B: Optional[float] = None, C: Optional[float] = None,
                     angle_unit: str = 'deg') -> Dict:
    """
    Resuelve un triángulo dado un set consistente de 3 valores conocidos
    entre {a,b,c (lados), A,B,C (ángulos opuestos a a,b,c respectivamente)}.

    Requiere exactamente 3 valores conocidos, con al menos un lado (tres
    ángulos solos determinan la forma pero no el tamaño).

    Casos soportados:
      - SSS: los tres lados conocidos
      - SAS: dos lados + el ángulo incluido entre ellos
      - SSA: dos lados + un ángulo no incluido (caso ambiguo: 0, 1 o 2
        soluciones — se devuelven todas las soluciones válidas)
      - ASA/AAS: un lado + dos ángulos
    """
    if angle_unit not in ('deg', 'rad'):
        return {'error': f'Unidad de ángulo desconocida: {angle_unit}. Válidas: deg, rad'}

    def to_rad(x):
        return math.radians(x) if angle_unit == 'deg' else x

    def from_rad(x):
        return math.degrees(x) if angle_unit == 'deg' else x

    sides = {k: v for k, v in (('a', a), ('b', b), ('c', c)) if v is not None}
    angles = {k: to_rad(v) for k, v in (('A', A), ('B', B), ('C', C)) if v is not None}

    if len(sides) + len(angles) != 3:
        return {'error': f'Se requieren exactamente 3 valores conocidos (lados+ángulos), se recibieron {len(sides) + len(angles)}'}

    if len(sides) == 0:
        return {'error': 'Se requiere al menos un lado conocido para determinar el tamaño del triángulo'}

    for v in list(sides.values()) + list(angles.values()):
        if v <= 0:
            return {'error': 'Lados y ángulos deben ser valores positivos'}

    # --- SSS ---
    if len(sides) == 3:
        a_, b_, c_ = sides['a'], sides['b'], sides['c']
        if a_ + b_ <= c_ or a_ + c_ <= b_ or b_ + c_ <= a_:
            return {'error': 'Los lados dados no satisfacen la desigualdad triangular'}
        A_ = _law_of_cosines_angle(a_, b_, c_)
        B_ = _law_of_cosines_angle(b_, a_, c_)
        C_ = math.pi - A_ - B_
        return {'case': 'SSS', 'a': a_, 'b': b_, 'c': c_,
                'A': from_rad(A_), 'B': from_rad(B_), 'C': from_rad(C_), 'angle_unit': angle_unit}

    # --- dos lados + un ángulo: SAS o SSA ---
    if len(sides) == 2 and len(angles) == 1:
        missing_side = (set('abc') - set(sides.keys())).pop()
        given_angle_key = next(iter(angles.keys()))
        included_angle = _INCLUDED_ANGLE[frozenset(sides.keys())]

        if given_angle_key == included_angle:
            # SAS
            keys = list(sides.keys())
            s1v, s2v = sides[keys[0]], sides[keys[1]]
            ang = angles[given_angle_key]
            missing_val = _law_of_cosines_side(ang, s1v, s2v)
            full_sides = dict(sides)
            full_sides[missing_side] = missing_val
            a_, b_, c_ = full_sides['a'], full_sides['b'], full_sides['c']
            A_ = _law_of_cosines_angle(a_, b_, c_)
            B_ = _law_of_cosines_angle(b_, a_, c_)
            C_ = math.pi - A_ - B_
            return {'case': 'SAS', 'a': a_, 'b': b_, 'c': c_,
                    'A': from_rad(A_), 'B': from_rad(B_), 'C': from_rad(C_), 'angle_unit': angle_unit}
        else:
            # SSA — caso ambiguo
            opp_side_key = given_angle_key.lower()
            known_opposite_side = sides[opp_side_key]
            other_side_key = (set(sides.keys()) - {opp_side_key}).pop()
            other_side = sides[other_side_key]
            ang = angles[given_angle_key]

            sin_other = other_side * math.sin(ang) / known_opposite_side
            if sin_other > 1.0 + 1e-9:
                return {'error': 'No existe triángulo con estos valores (SSA): caso sin solución'}
            sin_other = max(-1.0, min(1.0, sin_other))
            other_angle_1 = math.asin(sin_other)
            other_angle_2 = math.pi - other_angle_1

            candidates = [other_angle_1]
            if abs(other_angle_2 - other_angle_1) > 1e-9:
                candidates.append(other_angle_2)

            other_angle_key = other_side_key.upper()
            third_side_key = missing_side
            third_angle_key = missing_side.upper()

            solutions = []
            for other_angle in candidates:
                third_angle = math.pi - ang - other_angle
                if third_angle <= 0:
                    continue
                third_side = known_opposite_side * math.sin(third_angle) / math.sin(ang)
                full_sides = dict(sides)
                full_sides[third_side_key] = third_side
                full_angles = {given_angle_key: ang, other_angle_key: other_angle, third_angle_key: third_angle}
                solutions.append({
                    'a': full_sides['a'], 'b': full_sides['b'], 'c': full_sides['c'],
                    'A': from_rad(full_angles['A']), 'B': from_rad(full_angles['B']), 'C': from_rad(full_angles['C']),
                })

            if not solutions:
                return {'error': 'No existe triángulo válido con estos valores (SSA)'}

            result = {'case': 'SSA', 'ambiguous': len(solutions) > 1, 'solutions': solutions, 'angle_unit': angle_unit}
            if len(solutions) > 1:
                result['note'] = 'Caso lado-lado-ángulo: existen 2 soluciones válidas'
            return result

    # --- un lado + dos ángulos: ASA/AAS ---
    if len(sides) == 1 and len(angles) == 2:
        missing_angle_key = (set('ABC') - set(angles.keys())).pop()
        missing_angle = math.pi - sum(angles.values())
        if missing_angle <= 0:
            return {'error': 'La suma de los ángulos dados ya es ≥ 180° / π rad'}
        full_angles = dict(angles)
        full_angles[missing_angle_key] = missing_angle

        known_side_key = next(iter(sides.keys()))
        known_side_val = sides[known_side_key]
        known_side_angle = full_angles[known_side_key.upper()]

        full_sides = dict(sides)
        for side_key in 'abc':
            if side_key == known_side_key:
                continue
            full_sides[side_key] = _law_of_sines_side(known_side_val, known_side_angle, full_angles[side_key.upper()])

        return {'case': 'ASA/AAS', 'a': full_sides['a'], 'b': full_sides['b'], 'c': full_sides['c'],
                'A': from_rad(full_angles['A']), 'B': from_rad(full_angles['B']), 'C': from_rad(full_angles['C']),
                'angle_unit': angle_unit}

    return {'error': 'Combinación de datos no soportada (revisar qué lados/ángulos se pasaron)'}


# ============================================================================
# RUMBO Y DISTANCIA
# ============================================================================

def _bearing_distance(x1: float, y1: float, x2: float, y2: float, angle_unit: str = 'deg') -> Dict:
    """
    Rumbo (desde el norte = +y, sentido horario hacia el este = +x) y
    distancia euclidiana entre dos puntos 2D.
    """
    if angle_unit not in ('deg', 'rad'):
        return {'error': f'Unidad de ángulo desconocida: {angle_unit}. Válidas: deg, rad'}

    dx = x2 - x1
    dy = y2 - y1
    distance = math.hypot(dx, dy)

    bearing_rad = math.atan2(dx, dy)  # atan2(este, norte): 0=N, 90°=E, 180°=S, 270°=O
    if bearing_rad < 0:
        bearing_rad += 2 * math.pi

    bearing = math.degrees(bearing_rad) if angle_unit == 'deg' else bearing_rad

    return {
        'point1': [x1, y1], 'point2': [x2, y2],
        'dx': dx, 'dy': dy,
        'distance': distance,
        'bearing': bearing,
        'angle_unit': angle_unit,
    }


# ============================================================================
# DISPATCHER Y MODO VALIDATE
# ============================================================================

TOOL_NAME = 'angle_math_tool'
TOOL_MODES = ['trig', 'atan2', 'convert', 'solve_triangle', 'bearing_distance', 'validate']


def _dispatch(mode: str, params: Dict) -> Dict:
    """Dispatcher central."""

    if mode == 'trig':
        function = params.get('function', '')
        value = params.get('value')
        angle_unit = params.get('angle_unit', 'deg')
        if not function or value is None:
            return {'error': 'function y value son requeridos'}
        return _trig(function, value, angle_unit)

    elif mode == 'atan2':
        y = params.get('y')
        x = params.get('x')
        angle_unit = params.get('angle_unit', 'deg')
        normalize_360 = params.get('normalize_360', False)
        if y is None or x is None:
            return {'error': 'y y x son requeridos'}
        return _atan2(y, x, angle_unit, normalize_360)

    elif mode == 'convert':
        value = params.get('value')
        unit = params.get('unit', 'deg')
        if value is None:
            return {'error': 'value es requerido'}
        return _convert_angle(value, unit)

    elif mode == 'solve_triangle':
        angle_unit = params.get('angle_unit', 'deg')
        return _solve_triangle(
            a=params.get('a'), b=params.get('b'), c=params.get('c'),
            A=params.get('A'), B=params.get('B'), C=params.get('C'),
            angle_unit=angle_unit,
        )

    elif mode == 'bearing_distance':
        x1, y1, x2, y2 = params.get('x1'), params.get('y1'), params.get('x2'), params.get('y2')
        angle_unit = params.get('angle_unit', 'deg')
        if None in (x1, y1, x2, y2):
            return {'error': 'x1, y1, x2, y2 son requeridos'}
        return _bearing_distance(x1, y1, x2, y2, angle_unit)

    elif mode == 'validate':
        return run_self_test()

    else:
        return {'error': f'Unknown mode: {mode}'}


def run_self_test() -> Dict:
    """Auto-tests para validación."""
    tests_passed = 0
    tests_total = 0
    errors = []

    # Test 1: sin(30°) = 0.5
    tests_total += 1
    try:
        r = _trig('sin', 30, 'deg')['result']
        assert abs(r - 0.5) < 1e-9, f"Expected sin(30°)=0.5, got {r}"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 1 (sin 30deg): {e}")

    # Test 2: tan(45°) = 1.0
    tests_total += 1
    try:
        r = _trig('tan', 45, 'deg')['result']
        assert abs(r - 1.0) < 1e-9, f"Expected tan(45°)=1.0, got {r}"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 2 (tan 45deg): {e}")

    # Test 3: acos(0.5) = 60° (inversa, salida en grados)
    tests_total += 1
    try:
        r = _trig('acos', 0.5, 'deg')['result']
        assert abs(r - 60.0) < 1e-6, f"Expected acos(0.5)=60°, got {r}"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 3 (acos 0.5): {e}")

    # Test 4: asin fuera de rango debe dar error, no crashear
    tests_total += 1
    try:
        r = _trig('asin', 1.5, 'deg')
        assert 'error' in r, "asin(1.5) debería devolver error (fuera de [-1,1])"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 4 (asin fuera de rango): {e}")

    # Test 5: atan2 en los 4 cuadrantes
    tests_total += 1
    try:
        q1 = _atan2(1, 1, 'deg')['result']    # 45°
        q2 = _atan2(1, -1, 'deg')['result']   # 135°
        q3 = _atan2(-1, -1, 'deg')['result']  # -135°
        q4 = _atan2(-1, 1, 'deg')['result']   # -45°
        assert abs(q1 - 45) < 1e-6 and abs(q2 - 135) < 1e-6, "Cuadrantes 1/2 incorrectos"
        assert abs(q3 - (-135)) < 1e-6 and abs(q4 - (-45)) < 1e-6, "Cuadrantes 3/4 incorrectos"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 5 (atan2 cuadrantes): {e}")

    # Test 6: convert 180° <-> pi rad, roundtrip
    tests_total += 1
    try:
        r1 = _convert_angle(180, 'deg')
        assert abs(r1['radians'] - math.pi) < 1e-9, "180° debería ser pi rad"
        r2 = _convert_angle(math.pi, 'rad')
        assert abs(r2['degrees'] - 180) < 1e-9, "pi rad debería ser 180°"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 6 (convert roundtrip): {e}")

    # Test 7: solve_triangle SSS (triángulo 3-4-5, rectángulo)
    tests_total += 1
    try:
        r = _solve_triangle(a=3, b=4, c=5, angle_unit='deg')
        assert r['case'] == 'SSS'
        assert abs(r['C'] - 90.0) < 1e-6, f"Ángulo opuesto a c=5 debería ser 90°, dio {r['C']}"
        assert abs(r['A'] + r['B'] + r['C'] - 180) < 1e-6, "Suma de ángulos debería ser 180°"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 7 (solve_triangle SSS 3-4-5): {e}")

    # Test 8: solve_triangle SAS, consistencia con ley de cosenos
    tests_total += 1
    try:
        r = _solve_triangle(a=5, b=7, C=40, angle_unit='deg')
        assert r['case'] == 'SAS'
        expected_c = _law_of_cosines_side(math.radians(40), 5, 7)
        assert abs(r['c'] - expected_c) < 1e-9, "Lado c no coincide con ley de cosenos"
        assert abs(r['A'] + r['B'] + r['C'] - 180) < 1e-6, "Suma de ángulos debería ser 180°"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 8 (solve_triangle SAS): {e}")

    # Test 9: solve_triangle ASA/AAS, consistencia con ley de senos
    tests_total += 1
    try:
        r = _solve_triangle(c=10, A=50, B=60, angle_unit='deg')
        assert r['case'] == 'ASA/AAS'
        assert abs(r['A'] + r['B'] + r['C'] - 180) < 1e-6, "Suma de ángulos debería ser 180°"
        ratio_c = r['c'] / math.sin(math.radians(r['C']))
        ratio_a = r['a'] / math.sin(math.radians(r['A']))
        assert abs(ratio_c - ratio_a) < 1e-6, "No se cumple la ley de senos"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 9 (solve_triangle ASA/AAS): {e}")

    # Test 10: solve_triangle desigualdad triangular violada -> error
    tests_total += 1
    try:
        r = _solve_triangle(a=1, b=1, c=10, angle_unit='deg')
        assert 'error' in r, "Lados 1,1,10 violan la desigualdad triangular, debería dar error"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 10 (desigualdad triangular): {e}")

    # Test 11: bearing_distance, norte y este puros
    tests_total += 1
    try:
        north = _bearing_distance(0, 0, 0, 10, 'deg')
        east = _bearing_distance(0, 0, 10, 0, 'deg')
        assert abs(north['bearing'] - 0) < 1e-9 and abs(north['distance'] - 10) < 1e-9, "Rumbo norte incorrecto"
        assert abs(east['bearing'] - 90) < 1e-9 and abs(east['distance'] - 10) < 1e-9, "Rumbo este incorrecto"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 11 (bearing norte/este): {e}")

    # Test 12: bearing_distance, distancia 3-4-5 (verificación cruzada con Test 7)
    tests_total += 1
    try:
        r = _bearing_distance(0, 0, 3, 4, 'deg')
        assert abs(r['distance'] - 5.0) < 1e-9, f"Distancia debería ser 5, dio {r['distance']}"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 12 (bearing distancia 3-4-5): {e}")

    return {
        'tool': TOOL_NAME,
        'tests_passed': tests_passed,
        'tests_total': tests_total,
        'errors': errors,
        'status': 'PASSED' if tests_passed == tests_total else 'FAILED',
    }


def run(arguments: Dict) -> Dict:
    """Punto de entrada para handler de servidor."""
    mode = arguments.get('mode', 'validate')
    params = arguments.get('params', {})
    return _dispatch(mode, params)


# ============================================================================
# REGISTRO
# ============================================================================

TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": "Trigonometría y geometría de ángulos: funciones trig directas/inversas, atan2 de 4 cuadrantes, conversión grados/radianes, resolución de triángulos (SSS/SAS/SSA/ASA/AAS vía ley de senos y cosenos), y rumbo+distancia entre dos puntos 2D.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": TOOL_MODES,
                "description": "Modo de operación"
            },
            "params": {
                "type": "object",
                "properties": {
                    "function": {"type": "string", "description": "sin, cos, tan, asin, acos o atan (modo trig)"},
                    "value": {"type": "number", "description": "Valor de entrada (ángulo para funciones directas, ratio para inversas)"},
                    "angle_unit": {"type": "string", "enum": ["deg", "rad"], "description": "Unidad de ángulo, default 'deg'"},
                    "y": {"type": "number", "description": "Componente y (modo atan2)"},
                    "x": {"type": "number", "description": "Componente x (modo atan2)"},
                    "normalize_360": {"type": "boolean", "description": "Normalizar resultado de atan2 a [0,360)/[0,2π)"},
                    "unit": {"type": "string", "enum": ["deg", "rad"], "description": "Unidad de entrada (modo convert)"},
                    "a": {"type": "number", "description": "Lado a (opuesto al ángulo A)"},
                    "b": {"type": "number", "description": "Lado b (opuesto al ángulo B)"},
                    "c": {"type": "number", "description": "Lado c (opuesto al ángulo C)"},
                    "A": {"type": "number", "description": "Ángulo A (opuesto al lado a)"},
                    "B": {"type": "number", "description": "Ángulo B (opuesto al lado b)"},
                    "C": {"type": "number", "description": "Ángulo C (opuesto al lado c)"},
                    "x1": {"type": "number", "description": "Coordenada x del punto 1 (modo bearing_distance)"},
                    "y1": {"type": "number", "description": "Coordenada y del punto 1"},
                    "x2": {"type": "number", "description": "Coordenada x del punto 2"},
                    "y2": {"type": "number", "description": "Coordenada y del punto 2"},
                },
                "description": "Parámetros según el modo"
            }
        },
        "required": ["mode", "params"]
    }
}


def _register():
    """Registra la herramienta en tool_registry."""
    from tool_registry import register_tool
    register_tool(name=TOOL_NAME, schema=TOOL_SCHEMA, handler=run)


if __name__ == '__main__':
    _register()
