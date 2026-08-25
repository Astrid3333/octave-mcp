# tools/cooking_physics_tool.py
"""
Física de la cocción: calor, presión, cambios de fase.

Modos:
- boiling_point: Punto de ebullición del agua según altitud
- oil_heating: Propiedades térmicas de aceites de fritura
- heat_transfer: Conducción de calor a través de una pared (ley de Fourier, estado estacionario)
- validate: Autoverificación
"""

import numpy as np


def register_tool(func):
    """Decorador simulado para testing sin server.py."""
    return func


@register_tool
def cooking_physics_tool(mode, **params):
    """
    Física de la cocción: calor, fluidos, cambios de fase

    Modos:
    - boiling_point: Punto de ebullición (efecto de la altitud)
    - oil_heating: Calentamiento de aceites (punto de humo)
    - heat_transfer: Transferencia de calor por conducción (estado estacionario)
    - validate: Autoverificación
    """
    if mode == 'boiling_point':
        return _boiling_point(params)
    elif mode == 'oil_heating':
        return _oil_heating(params)
    elif mode == 'heat_transfer':
        return _heat_transfer(params)
    elif mode == 'validate':
        return _validate_cooking_physics()
    else:
        return {
            'error': f'Modo desconocido: {mode}',
            'validation_passed': False
        }


def _boiling_point(params):
    """
    Punto de ebullición del agua en función de la altitud.

    Paso 1: presión atmosférica según altitud (fórmula barométrica estándar).
    Paso 2: temperatura de ebullición a esa presión, resolviendo la
            ecuación de Antoine para el agua:
                log10(P_mmHg) = A - B / (C + T)
            despejando T:
                T = B / (A - log10(P_mmHg)) - C
    Constantes de Antoine para agua (rango 1-100°C, NIST):
        A = 8.07131, B = 1730.63, C = 233.426
    """
    altitude = float(params.get('altitude', 0))  # metros sobre el nivel del mar

    if altitude < -500 or altitude > 9000:
        return {
            'error': f'Altitud {altitude} m fuera de rango físicamente razonable (-500, 9000)',
            'validation_passed': False
        }

    # Fórmula barométrica estándar (atmósfera internacional, válida hasta ~11km)
    pressure_pa = 101325.0 * (1 - 0.0065 * altitude / 288.15) ** 5.2561

    # Constantes de Antoine para agua (T en °C, P en mmHg)
    A = 8.07131
    B = 1730.63
    C = 233.426

    pressure_mmhg = pressure_pa / 133.322

    if pressure_mmhg <= 0:
        return {
            'error': 'Presión calculada no positiva — altitud fuera de rango del modelo',
            'validation_passed': False
        }

    log_p = np.log10(pressure_mmhg)
    denom = A - log_p
    if denom == 0:
        return {
            'error': 'Singularidad en la ecuación de Antoine para esta presión',
            'validation_passed': False
        }

    T_boiling = B / denom - C

    return {
        'altitude_m': float(altitude),
        'pressure_pa': float(pressure_pa),
        'pressure_atm': float(pressure_pa / 101325.0),
        'pressure_mmhg': float(pressure_mmhg),
        'boiling_point_c': float(T_boiling),
        'model': 'Antoine equation (NIST constants, agua, rango 1-100°C)',
        'validation_passed': True
    }


def _oil_heating(params):
    """
    Propiedades de aceites de cocina para fritura.

    Datos de literatura (punto de humo, punto de inflamación, calor específico).
    """
    oil_type = params.get('oil', 'olive')

    oil_props = {
        'olive': {'smoke_point_c': 210, 'flash_point_c': 320, 'specific_heat_kj_kgk': 1.97},
        'extra_virgin_olive': {'smoke_point_c': 160, 'flash_point_c': 300, 'specific_heat_kj_kgk': 1.97},
        'sunflower': {'smoke_point_c': 232, 'flash_point_c': 330, 'specific_heat_kj_kgk': 1.98},
        'canola': {'smoke_point_c': 238, 'flash_point_c': 340, 'specific_heat_kj_kgk': 1.96},
        'peanut': {'smoke_point_c': 232, 'flash_point_c': 340, 'specific_heat_kj_kgk': 1.95},
        'vegetable': {'smoke_point_c': 200, 'flash_point_c': 315, 'specific_heat_kj_kgk': 1.96},
        'coconut': {'smoke_point_c': 175, 'flash_point_c': 290, 'specific_heat_kj_kgk': 2.00},
        'avocado': {'smoke_point_c': 271, 'flash_point_c': 350, 'specific_heat_kj_kgk': 1.97},
        'butter': {'smoke_point_c': 150, 'flash_point_c': 208, 'specific_heat_kj_kgk': 2.05},
        'ghee': {'smoke_point_c': 250, 'flash_point_c': 320, 'specific_heat_kj_kgk': 2.05}
    }

    if oil_type not in oil_props:
        return {
            'error': f'Tipo de aceite desconocido: {oil_type}. Opciones: {list(oil_props.keys())}',
            'validation_passed': False
        }

    props = oil_props[oil_type]

    target_temp = params.get('target_temperature')
    warning = None
    if target_temp is not None:
        target_temp = float(target_temp)
        if target_temp >= props['smoke_point_c']:
            warning = f'{target_temp}°C supera el punto de humo ({props["smoke_point_c"]}°C) — el aceite se degrada'

    return {
        'oil_type': oil_type,
        'smoke_point_c': float(props['smoke_point_c']),
        'flash_point_c': float(props['flash_point_c']),
        'specific_heat_kj_kgk': float(props['specific_heat_kj_kgk']),
        'target_temperature_c': float(target_temp) if target_temp is not None else None,
        'warning': warning,
        'validation_passed': True
    }


def _heat_transfer(params):
    """
    Conducción de calor en estado estacionario a través de una pared plana
    (ley de Fourier): q = k * A * (T_hot - T_cold) / L

    Parámetros:
    - material: acero, vidrio, aluminio, ceramica, teflon (conductividad k, W/m·K)
    - area_m2: área de transferencia (m²)
    - thickness_m: espesor de la pared (m)
    - t_hot_c, t_cold_c: temperaturas a ambos lados (°C)
    """
    material = params.get('material', 'aluminio')
    area = float(params.get('area_m2', 0.05))
    thickness = float(params.get('thickness_m', 0.003))
    t_hot = float(params.get('t_hot_c', 200))
    t_cold = float(params.get('t_cold_c', 20))

    conductivity = {
        'acero': 50.0,
        'vidrio': 1.0,
        'aluminio': 237.0,
        'cobre': 401.0,
        'ceramica': 1.5,
        'teflon': 0.25,
        'hierro_fundido': 55.0
    }

    if material not in conductivity:
        return {
            'error': f'Material desconocido: {material}. Opciones: {list(conductivity.keys())}',
            'validation_passed': False
        }

    if area <= 0 or thickness <= 0:
        return {
            'error': 'area_m2 y thickness_m deben ser positivos',
            'validation_passed': False
        }

    k = conductivity[material]
    delta_t = t_hot - t_cold
    q_watts = k * area * delta_t / thickness

    return {
        'material': material,
        'thermal_conductivity_w_mk': float(k),
        'area_m2': float(area),
        'thickness_m': float(thickness),
        't_hot_c': float(t_hot),
        't_cold_c': float(t_cold),
        'heat_flux_w': float(q_watts),
        'validation_passed': True
    }


def _validate_cooking_physics():
    """
    Auto-validación de cooking_physics_tool.

    Checks:
    1. boiling_point a nivel del mar debe dar ~100°C
    2. boiling_point en altura (Ciudad de México, 2240m) debe ser < 100°C
    3. oil_heating retorna propiedades válidas y warning correcto
    4. heat_transfer con delta_t positivo da flujo positivo
    5. serialización JSON (sin tipos numpy)
    """
    checks = []

    # Check 1: nivel del mar ≈ 100°C
    try:
        result = _boiling_point({'altitude': 0})
        bp = result.get('boiling_point_c', -999)
        check1_passed = result.get('validation_passed') is True and abs(bp - 100.0) < 1.0
        checks.append(('boiling_point_sea_level_100c', check1_passed))
    except Exception:
        checks.append(('boiling_point_sea_level_100c', False))

    # Check 2: altura reduce el punto de ebullición
    try:
        result_sea = _boiling_point({'altitude': 0})
        result_high = _boiling_point({'altitude': 2240})
        check2_passed = (
            result_high.get('validation_passed') is True and
            result_high['boiling_point_c'] < result_sea['boiling_point_c']
        )
        checks.append(('boiling_point_decreases_with_altitude', check2_passed))
    except Exception:
        checks.append(('boiling_point_decreases_with_altitude', False))

    # Check 3: oil_heating con warning si excede smoke point
    try:
        result = _oil_heating({'oil': 'olive', 'target_temperature': 250})
        check3_passed = (
            result.get('validation_passed') is True and
            result.get('warning') is not None
        )
        checks.append(('oil_smoke_point_warning', check3_passed))
    except Exception:
        checks.append(('oil_smoke_point_warning', False))

    # Check 4: heat_transfer positivo
    try:
        result = _heat_transfer({'material': 'aluminio', 'area_m2': 0.05, 'thickness_m': 0.003, 't_hot_c': 200, 't_cold_c': 20})
        check4_passed = (
            result.get('validation_passed') is True and
            result.get('heat_flux_w', -1) > 0
        )
        checks.append(('heat_transfer_positive_flux', check4_passed))
    except Exception:
        checks.append(('heat_transfer_positive_flux', False))

    # Check 5: JSON serializable
    try:
        r1 = _boiling_point({'altitude': 1000})
        r2 = _oil_heating({'oil': 'canola'})
        r3 = _heat_transfer({'material': 'vidrio'})

        def check_json_serializable(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    check_json_serializable(v)
            elif isinstance(obj, (list, tuple)):
                for item in obj:
                    check_json_serializable(item)
            elif isinstance(obj, (np.floating, np.integer)):
                raise TypeError(f'Tipo numpy detectado: {type(obj)}')
            elif isinstance(obj, np.bool_):
                raise TypeError(f'Bool numpy detectado: {type(obj)}')

        check_json_serializable(r1)
        check_json_serializable(r2)
        check_json_serializable(r3)
        checks.append(('json_serializable_types', True))
    except Exception:
        checks.append(('json_serializable_types', False))

    return {
        'validation_passed': all([c[1] for c in checks]),
        'checks': [{'name': c[0], 'passed': c[1]} for c in checks]
    }


def run(mode, params):
    """Interfaz compatibilidad con server.py"""
    if mode == 'validate':
        return _validate_cooking_physics()
    else:
        return cooking_physics_tool(mode, **params)
