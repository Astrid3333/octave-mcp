# tools/food_science_tool.py
"""
Ciencia de alimentos integrada: física, química y matemáticas.

Modos:
- water_activity: Actividad de agua (aw) y efecto en conservación
- thermal_processing: Procesamiento térmico (pasteurización, tiempo de cocción)
- validate: Autoverificación
"""

import numpy as np
from scipy.optimize import fsolve, brentq
from scipy.stats import binom


def register_tool(func):
    """Decorador simulado para testing sin server.py."""
    return func


@register_tool
def food_science_tool(mode, **params):
    """
    Ciencia de alimentos integrada: física, química y matemáticas
    
    Modos:
    - water_activity: Actividad de agua (aw) y su efecto en conservación
    - thermal_processing: Procesamiento térmico (pasteurización, esterilización)
    - validate: Autoverificación
    """
    if mode == 'water_activity':
        return _water_activity(params)
    elif mode == 'thermal_processing':
        return _thermal_processing(params)
    elif mode == 'validate':
        return _validate_food_science()
    else:
        return {
            'error': f'Modo desconocido: {mode}',
            'validation_passed': False
        }


def _water_activity(params):
    """
    Cálculo de actividad de agua (aw) y predicción de estabilidad.
    
    Modelo GAB (Guggenheim-Anderson-de Boer) para isoterma de sorción:
    X = (Xm * C * K * aw) / ((1 - K*aw) * (1 - K*aw + C*K*aw))
    
    Resuelve para aw dado X (moisture) usando método numérico.
    """
    product = params.get('product', 'fruit_jam')
    temperature = params.get('temperature', 25)  # °C
    moisture = params.get('moisture', 0.2)  # g agua / g sólido seco
    
    # Coeficientes GAB para diferentes productos (literatura real)
    # Xm = capacidad de monocapa (g agua / g sólido seco)
    sorption_params = {
        'fruit_jam': {'C': 10.2, 'K': 0.85, 'Xm': 0.18},
        'meat': {'C': 8.5, 'K': 0.90, 'Xm': 0.15},
        'cheese': {'C': 12.0, 'K': 0.82, 'Xm': 0.12},
        'bread': {'C': 15.0, 'K': 0.75, 'Xm': 0.22},
        'flour': {'C': 9.5, 'K': 0.88, 'Xm': 0.20},
        'milk_powder': {'C': 11.0, 'K': 0.83, 'Xm': 0.16}
    }
    
    params_prod = sorption_params.get(product, sorption_params['fruit_jam'])
    C = float(params_prod['C'])
    K = float(params_prod['K'])
    Xm = float(params_prod['Xm'])
    
    # Ecuación GAB a resolver: X - f(aw) = 0
    def gab_equation(aw):
        """Ecuación GAB para encontrar aw dado moisture X."""
        if aw <= 0 or aw >= 1:
            return float('inf')
        denom1 = 1 - K * aw
        denom2 = 1 - K * aw + C * K * aw
        if denom1 <= 0 or denom2 <= 0:
            return float('inf')
        return (Xm * C * K * aw) / (denom1 * denom2) - moisture
    
    # Verificar si moisture está dentro del rango físicamente posible
    # Rango: 0 < X < 1 (100% agua sobre base seca es el máximo teórico)
    if moisture <= 0 or moisture > 1.0:
        return {
            'error': f'Moisture {moisture} fuera del rango físico (0, 1.0]',
            'validation_passed': False
        }
    
    # Resolver usando método de Brent (robusto para una ecuación)
    # Rango válido para aw: (0, 1)
    try:
        aw = brentq(gab_equation, 0.01, 0.99)
    except ValueError:
        # Si Brent falla, usar fsolve como fallback
        aw_guess = 0.5
        aw_sol = fsolve(gab_equation, aw_guess, full_output=True)
        aw = float(aw_sol[0][0])
        if not aw_sol[2]:  # Si fsolve no convergió
            return {
                'error': f'No se pudo converger para producto {product}, moisture {moisture}',
                'validation_passed': False
            }
    
    # Asegurar que aw está en rango [0, 1]
    aw = float(np.clip(aw, 0, 1))
    
    # Predicción de estabilidad microbiológica (basada en literatura)
    if aw < 0.6:
        stability = 'Muy estable (sin crecimiento microbiano)'
    elif aw < 0.75:
        stability = 'Estable (bacterias halófilas)'
    elif aw < 0.85:
        stability = 'Moderadamente estable (hongos, levaduras)'
    elif aw < 0.91:
        stability = 'Poco estable (bacterias osmófilas)'
    else:
        stability = 'Inestable (la mayoría de bacterias)'
    
    return {
        'product': product,
        'moisture_input_g_per_g_dry': float(moisture),
        'water_activity_calculated': float(aw),
        'stability_prediction': stability,
        'microbial_growth_thresholds': {
            'bacteria_general_min': 0.91,
            'bacteria_halophilic_min': 0.75,
            'yeast_min': 0.88,
            'mold_min': 0.80
        },
        'gab_model_params': {
            'C': float(C),
            'K': float(K),
            'Xm_monolayer': float(Xm)
        },
        'validation_passed': True
    }


def _thermal_processing(params):
    """
    Procesamiento térmico de alimentos (pasteurización, tiempo de cocción).
    
    Submodos:
    - pasteurization: Modelo D-z para reducción microbiológica
    - cooking_time: Ecuación de Fourier para transferencia de calor
    """
    process_type = params.get('process_type', 'pasteurization')
    
    if process_type == 'pasteurization':
        return _pasteurization(params)
    elif process_type == 'cooking_time':
        return _cooking_time(params)
    else:
        return {
            'error': f'Tipo de procesamiento desconocido: {process_type}',
            'validation_passed': False
        }


def _pasteurization(params):
    """
    Cálculo de pasteurización usando modelo D-z.
    
    D-value: tiempo (minutos) a una temperatura de referencia para una reducción decimal
    z-value: cambio de temperatura (°C) para cambiar D en un factor de 10
    
    Parámetros:
    - target_microbe: Listeria, Salmonella, E_coli, Bacillus
    - initial_count: Carga inicial (log CFU/g)
    - target_reduction: Reducciones decimales deseadas
    - temperature: Temperatura de proceso (°C)
    """
    target = params.get('target_microbe', 'Listeria')
    initial_count = float(params.get('initial_count', 6))  # log CFU/g
    target_reduction = float(params.get('target_reduction', 5))  # log reducciones
    temp = float(params.get('temperature', 72))  # °C
    
    # Parámetros D-z de literatura (microbiología de alimentos)
    d_values = {
        'Listeria': {'D_ref': 0.25, 'T_ref': 72, 'z': 7.5},
        'Salmonella': {'D_ref': 0.38, 'T_ref': 72, 'z': 6.5},
        'E_coli': {'D_ref': 0.18, 'T_ref': 72, 'z': 6.0},
        'Bacillus': {'D_ref': 2.5, 'T_ref': 121, 'z': 10.0},  # Esporas
        'Clostridium': {'D_ref': 0.20, 'T_ref': 100, 'z': 8.5}
    }
    
    if target not in d_values:
        return {
            'error': f'Microorganismo desconocido: {target}',
            'validation_passed': False
        }
    
    params_micro = d_values[target]
    D_ref = float(params_micro['D_ref'])  # minutos
    T_ref = float(params_micro['T_ref'])  # °C
    z = float(params_micro['z'])  # °C
    
    # Corregir D por temperatura usando fórmula D-z
    # D_T = D_ref * 10^((T_ref - T) / z)
    D_actual = D_ref * (10 ** ((T_ref - temp) / z))
    
    # Tiempo de proceso para alcanzar reducciones deseadas
    # t = D * n_reducciones
    process_time = D_actual * target_reduction
    
    # Cuenta final
    final_count = initial_count - target_reduction
    
    return {
        'target_microbe': target,
        'initial_count_log_cfu_g': float(initial_count),
        'target_reduction_decimal_logs': float(target_reduction),
        'temperature_process_c': float(temp),
        'D_value_at_temp_min': float(D_actual),
        'z_value_c': float(z),
        'process_time_min': float(process_time),
        'process_time_hours': float(process_time / 60),
        'final_count_log_cfu_g': float(final_count),
        'microbe_details': {
            'D_ref_min': float(D_ref),
            'T_ref_c': float(T_ref)
        },
        'validation_passed': True
    }


def _cooking_time(params):
    """
    Modelo de conducción de calor para cocción (ecuación de Fourier).
    
    Solución analítica para placa infinita con:
    - Condición inicial: T(x,0) = T_initial
    - Condición de borde: T(±L/2, t) = T_oven
    - Buscamos tiempo para que centro alcance T_target
    
    Parámetros:
    - food: meat, fish, bread, vegetable
    - thickness: Espesor característico (metros)
    - initial_temp: Temperatura inicial (°C)
    - oven_temp: Temperatura de cocción (°C)
    - target_temp: Temperatura central deseada (°C)
    """
    food_type = params.get('food', 'meat')
    thickness = float(params.get('thickness', 0.05))  # metros
    initial_temp = float(params.get('initial_temp', 5))  # °C
    oven_temp = float(params.get('oven_temp', 180))  # °C
    target_temp = float(params.get('target_temp', 75))  # °C
    
    # Propiedades térmicas de alimentos (literatura, W/m·K o m²/s)
    thermal_props = {
        'meat': {'alpha': 1.2e-7, 'k': 0.45, 'rho': 1050, 'cp': 3500},
        'fish': {'alpha': 1.4e-7, 'k': 0.50, 'rho': 1000, 'cp': 3300},
        'bread': {'alpha': 1.0e-7, 'k': 0.25, 'rho': 300, 'cp': 2000},
        'vegetable': {'alpha': 1.1e-7, 'k': 0.40, 'rho': 900, 'cp': 3800},
        'chicken': {'alpha': 1.3e-7, 'k': 0.43, 'rho': 1030, 'cp': 3400},
        'pork': {'alpha': 1.1e-7, 'k': 0.44, 'rho': 1020, 'cp': 3450}
    }
    
    if food_type not in thermal_props:
        return {
            'error': f'Tipo de alimento desconocido: {food_type}',
            'validation_passed': False
        }
    
    props = thermal_props[food_type]
    alpha = float(props['alpha'])  # Difusividad térmica (m²/s)
    k = float(props['k'])  # Conductividad térmica (W/m·K)
    
    # Verificar que target está entre inicial y oven
    if not (min(initial_temp, oven_temp) <= target_temp <= max(initial_temp, oven_temp)):
        return {
            'error': f'target_temp {target_temp}°C fuera del rango [{min(initial_temp, oven_temp)}, {max(initial_temp, oven_temp)}]',
            'validation_passed': False
        }
    
    # Si initial_temp == oven_temp, sin gradiente térmico
    if abs(oven_temp - initial_temp) < 0.1:
        return {
            'error': 'No hay gradiente térmico (initial_temp ≈ oven_temp)',
            'validation_passed': False
        }
    
    # Solución analítica para placa infinita (primer término de la serie de Fourier):
    # T_center(t) = T_oven - (T_oven - T_initial) * exp(-π²*alpha*t / L²)
    # Donde L = thickness / 2 (distancia desde centro a borde)
    
    L = thickness / 2  # metros (semi-espesor)
    
    # Despejar t:
    # (T_oven - T_target) / (T_oven - T_initial) = exp(-π²*alpha*t / L²)
    # ln(...) = -π²*alpha*t / L²
    # t = -L² / (π²*alpha) * ln(...)
    
    ratio = (oven_temp - target_temp) / (oven_temp - initial_temp)
    
    if ratio <= 0:
        return {
            'error': 'Ratio de temperaturas inválido (probablemente temperatures cruzadas)',
            'validation_passed': False
        }
    
    ln_ratio = np.log(ratio)
    t_seconds = -(L**2) / (np.pi**2 * alpha) * ln_ratio
    t_minutes = t_seconds / 60
    t_hours = t_minutes / 60
    
    return {
        'food_type': food_type,
        'thickness_m': float(thickness),
        'initial_temp_c': float(initial_temp),
        'oven_temp_c': float(oven_temp),
        'target_center_temp_c': float(target_temp),
        'cooking_time_seconds': float(t_seconds),
        'cooking_time_minutes': float(t_minutes),
        'cooking_time_hours': float(t_hours),
        'thermal_properties': {
            'thermal_diffusivity_m2_s': float(alpha),
            'thermal_conductivity_w_m_k': float(k)
        },
        'validation_passed': True
    }


def _validate_food_science():
    """
    Auto-validación de food_science_tool.
    
    Checks:
    1. water_activity: calcular aw para ejemplo estándar (fruit_jam, moisture=0.2)
    2. pasteurization: calcular tiempo para Listeria a 72°C
    3. cooking_time: calcular tiempo para carne de 5°C a 75°C en horno 180°C
    """
    checks = []
    
    # Check 1: water_activity
    try:
        result1 = _water_activity({
            'product': 'fruit_jam',
            'temperature': 25,
            'moisture': 0.2
        })
        check1_passed = (
            result1.get('validation_passed') is True and
            0 < result1.get('water_activity_calculated', -1) < 1
        )
        checks.append(('water_activity_convergence', check1_passed))
    except Exception as e:
        checks.append(('water_activity_convergence', False))
    
    # Check 2: pasteurization
    try:
        result2 = _pasteurization({
            'target_microbe': 'Listeria',
            'initial_count': 6,
            'target_reduction': 5,
            'temperature': 72
        })
        check2_passed = (
            result2.get('validation_passed') is True and
            result2.get('process_time_min', -1) > 0
        )
        checks.append(('pasteurization_d_z_model', check2_passed))
    except Exception as e:
        checks.append(('pasteurization_d_z_model', False))
    
    # Check 3: cooking_time
    try:
        result3 = _cooking_time({
            'food': 'meat',
            'thickness': 0.05,
            'initial_temp': 5,
            'oven_temp': 180,
            'target_temp': 75
        })
        check3_passed = (
            result3.get('validation_passed') is True and
            result3.get('cooking_time_minutes', -1) > 0
        )
        checks.append(('cooking_fourier_equation', check3_passed))
    except Exception as e:
        checks.append(('cooking_fourier_equation', False))
    
    # Check 4: JSON serializable (tipos correctos)
    try:
        result1 = _water_activity({'product': 'bread', 'moisture': 0.15})
        result2 = _pasteurization({'target_microbe': 'Salmonella'})
        result3 = _cooking_time({'food': 'fish'})
        
        # Verificar que no hay numpy types
        def check_json_serializable(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    check_json_serializable(v)
            elif isinstance(obj, (list, tuple)):
                for item in obj:
                    check_json_serializable(item)
            elif isinstance(obj, (np.floating, np.integer)):
                raise TypeError(f'Tipo numpy detectado: {type(obj)}')
            elif isinstance(obj, (np.bool_)):
                raise TypeError(f'Bool numpy detectado: {type(obj)}')
        
        check_json_serializable(result1)
        check_json_serializable(result2)
        check_json_serializable(result3)
        checks.append(('json_serializable_types', True))
    except Exception as e:
        checks.append(('json_serializable_types', False))
    
    return {
        'validation_passed': all([c[1] for c in checks]),
        'checks': [{'name': c[0], 'passed': c[1]} for c in checks]
    }


def run(mode, params):
    """Interfaz compatibilidad con server.py"""
    if mode == 'validate':
        return _validate_food_science()
    else:
        return food_science_tool(mode, **params)
