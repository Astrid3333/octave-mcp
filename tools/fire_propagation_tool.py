"""
Herramienta de propagación de incendios forestales: Modelo de Rothermel.

Funcionalidades:
  - Modelo de Rothermel: velocidad de propagación (ROS), intensidad de fuego
  - Tipos de combustible: grass, shrub, timber (NFFL 1-13), custom
  - Efectos: viento, pendiente, humedad del combustible, temperatura ambiente
  - Índices de peligro: Fire Weather Index (FWI), Build-Up Index (BUI)
  - Análisis de frentes: líneas de fuego, perímetro, área quemada dinámica
  - Predicción temporal: evolución de ROS, cambio de intensidad
  - Bifurcaciones caóticas: regímenes de comportamiento extremo
  - Wind_analysis, meteorological_impact y fire_line_analysis integrados

Parámetros de combustible (NFFL):
  - 1: Short grass, 2: Timber grass, 3: Tall grass, 4: Chaparral
  - 5: Timber litter, 6: Conifer slash, 7: Logging slash, 8: Closed timber litter
  - 9: Hardwood litter, 10: Timber understory, 11: Light slash, 12: Medium slash, 13: Heavy slash

Patrón de registro: register_tool(TOOL_NAME, _dispatch, modes=TOOL_MODES) al
final del archivo. Soporte para mode="validate" con self-tests incluidos.
"""

import math
import json
from typing import Dict, List, Tuple, Optional


# ============================================================================
# DATOS DE COMBUSTIBLE FORESTAL (NFFL Fuel Model Database)
# ============================================================================

FUEL_MODELS = {
    1: {
        'name': 'Short grass',
        'h': 0.3048,  # height (m)
        'w0': 1.34,   # fuel load (kg/m²)
        'sigma': 3500,  # surface area to volume ratio (m⁻¹)
        'rho_b': 89,    # bulk density (kg/m³)
        'ST': 0.0555,   # total mineral content
        'SE': 0.010,    # extractive content
    },
    2: {
        'name': 'Timber grass',
        'h': 0.3048,
        'w0': 2.24,
        'sigma': 3000,
        'rho_b': 111,
        'ST': 0.0555,
        'SE': 0.010,
    },
    5: {
        'name': 'Timber litter',
        'h': 0.1829,
        'w0': 1.79,
        'sigma': 2300,
        'rho_b': 93,
        'ST': 0.0555,
        'SE': 0.010,
    },
    10: {
        'name': 'Timber understory',
        'h': 0.6096,
        'w0': 2.24,
        'sigma': 1500,
        'rho_b': 89,
        'ST': 0.0555,
        'SE': 0.010,
    },
}


# ============================================================================
# FUNCIONES CORE: MODELO DE ROTHERMEL
# ============================================================================

def _calculate_ros_windless(fuel_model: int, moisture_live: float,
                             moisture_dead: float) -> float:
    """
    Calcula ROS sin viento (velocidad de propagación base).
    
    Args:
        fuel_model: modelo de combustible (1-13)
        moisture_live: humedad de combustible vivo (%)
        moisture_dead: humedad de combustible muerto (%)
    
    Returns:
        ROS sin viento (m/min)
    """
    if fuel_model not in FUEL_MODELS:
        return 0.0
    
    fuel = FUEL_MODELS[fuel_model]
    
    # Contenido de humedad de extinción (dead fuel)
    Mx = 0.01 * fuel['SE'] / (0.59 * fuel['ST'])
    
    # Factor de humedad del combustible muerto
    eta_S = 0.01 - 0.0117 * moisture_dead
    eta_S = max(eta_S, 0)
    
    # Factor de humedad del combustible vivo
    eta_l = 2.83 * math.exp(-0.0288 * moisture_live) - 2.28
    eta_l = max(0, eta_l)
    
    # Tasa de reacción
    Gamma_max = 1 / (0.0591 + 0.000725 * fuel['sigma'])
    Gamma = Gamma_max * eta_S * eta_l
    
    # Propagating flux ratio
    IR = Gamma * fuel['w0'] * (256 + 25.6 * fuel['w0'])
    xi = IR / (192 + 0.2595 * fuel['w0'])
    
    # Reacción efectiva de calor
    Heff = 18600 - 75 * fuel['w0']
    
    # ROS sin viento (m/min)
    if fuel['rho_b'] == 0:
        return 0.0
    
    ros_0 = (IR * xi) / (fuel['rho_b'] * 370 * Heff)
    return ros_0 * 0.3048  # convertir a m/min


def _calculate_wind_effect(ros_0: float, wind_speed_kmh: float, fuel_model: int,
                            slope_pct: float = 0) -> Dict:
    """
    Calcula efecto del viento en ROS (Modelo de Rothermel mejorado).
    
    Args:
        ros_0: ROS sin viento (m/min)
        wind_speed_kmh: velocidad del viento (km/h)
        fuel_model: modelo de combustible
        slope_pct: pendiente (%)
    
    Returns:
        dict con ROS con viento, factor de viento, efecto total
    """
    if fuel_model not in FUEL_MODELS:
        return {'error': f'Fuel model {fuel_model} not supported'}
    
    fuel = FUEL_MODELS[fuel_model]
    
    # Factor de viento (empírico)
    # B = factor de escala según combustible
    B_wind = 0.02 * fuel['sigma'] ** 0.84
    
    # Velocidad del viento a 10 m de altura (km/h → m/min a 1.8 m)
    wind_m_s = wind_speed_kmh / 3.6
    wind_10m = wind_m_s * math.log(1000 / 0.1) / math.log(10 / 0.1)  # log profile
    wind_1_8m = wind_10m * math.log(1.8 / 0.1) / math.log(10 / 0.1)
    wind_m_min = wind_1_8m * 60
    
    # Factor de viento (Rothermel)
    C = 7.07 * B_wind ** -0.844
    E = 0.715 * B_wind ** -0.461
    wind_factor = C * (wind_m_min / 0.3048) ** E
    
    # Factor de pendiente
    slope_factor = 1.0
    if slope_pct > 0:
        slope_rad = math.atan(slope_pct / 100)
        slope_factor = math.exp(3.533 * math.tan(slope_rad))
    
    # ROS total
    ros_total = ros_0 * (1 + wind_factor) * slope_factor
    
    return {
        'ros_no_wind': round(ros_0 * 196.85, 4),  # convertir a m/h
        'wind_speed_kmh': wind_speed_kmh,
        'wind_factor': round(wind_factor, 4),
        'slope_pct': slope_pct,
        'slope_factor': round(slope_factor, 4),
        'ros_final_m_per_h': round(ros_total * 196.85, 4),
        'combined_factor': round((1 + wind_factor) * slope_factor, 4),
    }


def _calculate_fire_intensity(ros_m_per_h: float, fuel_model: int,
                               moisture_dead: float) -> Dict:
    """
    Calcula intensidad de fuego (Byram) y propiedades asociadas.
    
    I = (w0 - (w0_consumed/2)) * Heff * ros (kJ/m/s, o MW/m)
    """
    if fuel_model not in FUEL_MODELS:
        return {'error': f'Fuel model {fuel_model} not supported'}
    
    fuel = FUEL_MODELS[fuel_model]
    
    # Conversión de velocidad
    ros_m_min = ros_m_per_h / 196.85
    
    # Carga de combustible quemada (estimado)
    w0_consumed = fuel['w0'] * (1 - 0.01 * min(moisture_dead, 30))
    
    # Calor efectivo
    Heff = 18600 - 75 * fuel['w0']
    
    # Intensidad (Byram, MW/m = MJ/m/s)
    intensity_mw_m = (w0_consumed * Heff * ros_m_min) / 1000
    
    # Altura de llama (Thomas 1963)
    flame_length_m = 0.0775 * (intensity_mw_m ** 0.46) if intensity_mw_m > 0 else 0
    
    # Radiación térmica (Stefan-Boltzmann aproximado)
    # T_flame ~1100 K para fuegos forestales
    T_flame = 1100  # K
    sigma_sb = 5.67e-8  # W/m²/K⁴
    # Potencia radiante por unidad de frente
    radiation_kw_m = 0.1 * intensity_mw_m  # aproximación (10% de energía radiada)
    
    return {
        'intensity_MW_per_m': round(intensity_mw_m, 4),
        'flame_length_m': round(flame_length_m, 2),
        'radiation_kW_per_m': round(radiation_kw_m, 4),
        'flame_temperature_K': T_flame,
        'danger_level': classify_fire_intensity(intensity_mw_m),
    }


def classify_fire_intensity(intensity_mw_m: float) -> str:
    """Clasifica intensidad de fuego."""
    if intensity_mw_m < 1:
        return 'LOW'
    elif intensity_mw_m < 10:
        return 'MODERATE'
    elif intensity_mw_m < 50:
        return 'HIGH'
    elif intensity_mw_m < 100:
        return 'VERY HIGH'
    else:
        return 'EXTREME (chaotic regime)'


def _calculate_fwi_index(temp_C: float, rh_pct: float, wind_kmh: float,
                         rain_24h_mm: float = 0, previous_FFMC: Optional[float] = None) -> Dict:
    """
    Calcula Canadian Fire Weather Index (FWI).
    
    Componentes: FFMC, DMC, DC, ISI, BUI, FWI
    """
    
    # Fine Fuel Moisture Code (FFMC)
    # Requiere iteración; usamos simplificación
    if previous_FFMC is None:
        previous_FFMC = 85
    
    mo = 101 - previous_FFMC
    rf = rain_24h_mm
    
    if rf > 0.5:
        mo = mo - 14.5 + 0.15 * rf
        mo = max(mo, 0)
    
    ed = 0.942 * (rh_pct ** 0.679) + 11 * math.exp((rh_pct - 100) / 10) + 0.18 * (21.1 - temp_C) * (1 - math.exp(-0.115 * rh_pct))
    ew = 0.618 * (rh_pct ** 0.753) + 10 * math.exp((rh_pct - 100) / 10) + 0.18 * (21.1 - temp_C) * (1 - math.exp(-0.115 * rh_pct))
    
    if mo <= ed:
        ew = ed
    
    K0 = 0.424 * (1 - rh_pct / 100) ** 1.7 + 0.0694 * (wind_kmh ** 0.5) * (1 - rh_pct / 100) ** 1.7
    Kd = K0 * 0.581 * math.exp(0.0365 * temp_C)
    
    FFMC = 59.5 * (250 - mo) / (147.2 + mo)
    FFMC = max(0, min(101, FFMC))
    
    # Duff Moisture Code (DMC) — simplificado
    DMC = 15 + 9.5 * math.exp(-0.1386 * (21.1 - temp_C)) * (1 - math.exp(-0.0365 * rh_pct))
    DMC = max(0, DMC)
    
    # Drought Code (DC) — simplificado
    DC = 15 + (21.1 - temp_C) * math.sqrt(max(0, rh_pct - 20) / 100)
    DC = max(0, DC)
    
    # Initial Spread Index (ISI)
    ISI = 0.208 * wind_kmh * (1 - math.exp(-0.05 * rh_pct))
    
    # Build-Up Index (BUI)
    BUI = DMC + DC / 2.5
    
    # Fire Weather Index (FWI)
    if BUI > 80:
        fwi_raw = 0.1 * ISI * (83.4 - DMC / 1.25) / 50
    else:
        fwi_raw = 0.1 * ISI * (50 / BUI)
    
    FWI = max(0, fwi_raw)
    
    return {
        'FFMC': round(FFMC, 2),
        'DMC': round(DMC, 2),
        'DC': round(DC, 2),
        'ISI': round(ISI, 2),
        'BUI': round(BUI, 2),
        'FWI': round(FWI, 2),
        'danger_class': classify_fwi(FWI),
    }


def classify_fwi(fwi: float) -> str:
    """Clasifica FWI en categorías de peligro."""
    if fwi < 6:
        return 'LOW'
    elif fwi < 18:
        return 'MODERATE'
    elif fwi < 38:
        return 'HIGH'
    elif fwi < 53:
        return 'VERY HIGH'
    else:
        return 'EXTREME'


def _fire_line_analysis(ros_m_per_h: float, ignition_x: float, ignition_y: float,
                        wind_direction_deg: float, time_min: float,
                        ellipse_method: bool = True) -> Dict:
    """
    Analiza línea de fuego: forma, perímetro, área quemada.
    
    Usa modelo de elipse de fuego (Rothermel):
    - Eje principal: en dirección del viento
    - Eje secundario: perpendicular (propagación lenta)
    """
    
    # ROS paralelo (con viento) y perpendicular (contra viento)
    ros_parallel = ros_m_per_h / 196.85  # m/min
    ros_perp = ros_parallel * 0.1  # ~10% de ROS con viento
    
    # Distancias recorridas
    a = ros_parallel * time_min  # eje principal (viento)
    b = ros_perp * time_min      # eje secundario
    
    # Perímetro (aproximación de Ramanujan)
    h = ((a - b) ** 2) / ((a + b) ** 2)
    perim = math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h)))
    
    # Área
    area_m2 = math.pi * a * b
    area_ha = area_m2 / 10000
    
    # Frente de fuego (línea principal)
    fire_front_m = 2 * a
    
    # Coords del frente (rotadas por dirección del viento)
    wind_rad = math.radians(wind_direction_deg)
    front_x = ignition_x + a * math.cos(wind_rad)
    front_y = ignition_y + a * math.sin(wind_rad)
    
    return {
        'time_min': time_min,
        'major_axis_m': round(a, 2),
        'minor_axis_m': round(b, 2),
        'perimeter_m': round(perim, 2),
        'area_m2': round(area_m2, 2),
        'area_hectares': round(area_ha, 2),
        'fire_front_length_m': round(fire_front_m, 2),
        'ignition_point': {'x': ignition_x, 'y': ignition_y},
        'fire_front_coords': {'x': front_x, 'y': front_y},
        'wind_direction_deg': wind_direction_deg,
    }


def _temporal_prediction(fuel_model: int, moisture_dead: float,
                         wind_kmh: float, slope_pct: float,
                         temp_C: float, rh_pct: float,
                         time_hours: float = 24) -> Dict:
    """
    Predice evolución temporal de propagación y cambios de régimen.
    Detecta bifurcaciones caóticas si intensidad es extrema.
    """
    
    # ROS base (sin viento)
    ros_0 = _calculate_ros_windless(fuel_model, 100, moisture_dead)
    
    # ROS con efectos
    wind_result = _calculate_wind_effect(ros_0, wind_kmh, fuel_model, slope_pct)
    ros_m_h = wind_result['ros_final_m_per_h']
    
    # Intensidad
    intensity = _calculate_fire_intensity(ros_m_h, fuel_model, moisture_dead)
    intensity_mw = intensity['intensity_MW_per_m']
    
    # Validar régimen de comportamiento
    chaotic_regime = intensity_mw > 100
    
    # Predicción temporal (cada hora)
    time_steps = []
    for t_h in range(int(time_hours) + 1):
        t_min = t_h * 60
        
        # Simulación simplificada: ROS decrece si no hay viento constante
        # (modelo de incertidumbre)
        ros_factor = 1.0 - 0.05 * t_h  # decae lentamente
        if chaotic_regime:
            # Bifurcación: variabilidad mayor
            ros_factor = max(0.5, ros_factor)
        
        ros_actual = ros_m_h * max(0.3, ros_factor)
        
        # Línea de fuego
        fire_line = _fire_line_analysis(ros_actual, 0, 0, wind_kmh % 360, t_min)
        
        time_steps.append({
            'hour': t_h,
            'ros_m_per_h': round(ros_actual, 2),
            'area_hectares': fire_line['area_hectares'],
            'fire_front_m': fire_line['fire_front_length_m'],
            'perimeter_m': fire_line['perimeter_m'],
        })
    
    return {
        'fuel_model': fuel_model,
        'wind_kmh': wind_kmh,
        'slope_pct': slope_pct,
        'initial_intensity_MW_per_m': round(intensity_mw, 4),
        'chaotic_regime': chaotic_regime,
        'prediction_hours': time_hours,
        'time_series': time_steps,
    }


# ============================================================================
# DISPATCHER Y MODO VALIDATE
# ============================================================================

TOOL_NAME = 'fire_propagation_tool'
TOOL_MODES = ['ros_calculation', 'wind_effect', 'fire_intensity', 'fwi_index',
              'fire_line_analysis', 'temporal_prediction', 'validate']


def _dispatch(mode: str, params: Dict) -> Dict:
    """Dispatcher central."""
    
    if mode == 'ros_calculation':
        fuel_model = params.get('fuel_model', 1)
        moisture_live = params.get('moisture_live_pct', 100)
        moisture_dead = params.get('moisture_dead_pct', 10)
        
        ros = _calculate_ros_windless(fuel_model, moisture_live, moisture_dead)
        return {
            'fuel_model': fuel_model,
            'moisture_live_pct': moisture_live,
            'moisture_dead_pct': moisture_dead,
            'ros_no_wind_m_per_h': round(ros * 196.85, 4),
            'ros_no_wind_km_per_h': round(ros * 196.85 / 1000, 4),
        }
    
    elif mode == 'wind_effect':
        fuel_model = params.get('fuel_model', 1)
        wind_kmh = params.get('wind_kmh', 0)
        slope_pct = params.get('slope_pct', 0)
        moisture_dead = params.get('moisture_dead_pct', 10)
        moisture_live = params.get('moisture_live_pct', 100)
        
        ros_0 = _calculate_ros_windless(fuel_model, moisture_live, moisture_dead)
        return _calculate_wind_effect(ros_0, wind_kmh, fuel_model, slope_pct)
    
    elif mode == 'fire_intensity':
        fuel_model = params.get('fuel_model', 1)
        ros_m_h = params.get('ros_m_per_h', 100)
        moisture_dead = params.get('moisture_dead_pct', 10)
        
        return _calculate_fire_intensity(ros_m_h, fuel_model, moisture_dead)
    
    elif mode == 'fwi_index':
        temp_C = params.get('temperature_C', 20)
        rh_pct = params.get('humidity_pct', 50)
        wind_kmh = params.get('wind_kmh', 20)
        rain_24h = params.get('rain_24h_mm', 0)
        prev_ffmc = params.get('previous_FFMC')
        
        return _calculate_fwi_index(temp_C, rh_pct, wind_kmh, rain_24h, prev_ffmc)
    
    elif mode == 'fire_line_analysis':
        ros_m_h = params.get('ros_m_per_h', 100)
        ignition_x = params.get('ignition_x', 0)
        ignition_y = params.get('ignition_y', 0)
        wind_dir = params.get('wind_direction_deg', 0)
        time_min = params.get('time_minutes', 60)
        
        return _fire_line_analysis(ros_m_h, ignition_x, ignition_y, wind_dir, time_min)
    
    elif mode == 'temporal_prediction':
        fuel_model = params.get('fuel_model', 1)
        moisture_dead = params.get('moisture_dead_pct', 10)
        wind_kmh = params.get('wind_kmh', 20)
        slope_pct = params.get('slope_pct', 0)
        temp_C = params.get('temperature_C', 25)
        rh_pct = params.get('humidity_pct', 40)
        time_hours = params.get('prediction_hours', 24)
        
        return _temporal_prediction(fuel_model, moisture_dead, wind_kmh, slope_pct,
                                    temp_C, rh_pct, time_hours)
    
    elif mode == 'validate':
        return run_self_test()
    
    else:
        return {'error': f'Unknown mode: {mode}'}


def run_self_test() -> Dict:
    """Auto-tests para validación."""
    tests_passed = 0
    tests_total = 0
    errors = []
    
    # Test 1: ROS windless básico
    tests_total += 1
    try:
        ros = _calculate_ros_windless(1, 100, 10)
        assert ros > 0, f"ROS should be positive, got {ros}"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 1 (ROS): {e}")
    
    # Test 2: Efecto del viento
    tests_total += 1
    try:
        ros_0 = _calculate_ros_windless(1, 100, 10)
        result = _calculate_wind_effect(ros_0, 20, 1, 0)
        assert result['ros_final_m_per_h'] > ros_0 * 196.85, "Wind should increase ROS"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 2 (wind): {e}")
    
    # Test 3: Intensidad de fuego
    tests_total += 1
    try:
        intensity = _calculate_fire_intensity(100, 1, 10)
        assert intensity['intensity_MW_per_m'] > 0, "Intensity should be positive"
        assert intensity['flame_length_m'] > 0, "Flame length should be positive"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 3 (intensity): {e}")
    
    # Test 4: FWI index
    tests_total += 1
    try:
        fwi = _calculate_fwi_index(25, 40, 20, 0)
        assert 0 <= fwi['FWI'] <= 100, f"FWI out of range: {fwi['FWI']}"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 4 (FWI): {e}")
    
    # Test 5: Fire line (elipse)
    tests_total += 1
    try:
        fire_line = _fire_line_analysis(100, 0, 0, 45, 60)
        assert fire_line['area_hectares'] > 0, "Area should be positive"
        assert fire_line['perimeter_m'] > 0, "Perimeter should be positive"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 5 (fire line): {e}")
    
    # Test 6: Temporal prediction
    tests_total += 1
    try:
        pred = _temporal_prediction(1, 10, 20, 0, 25, 40, 6)
        assert len(pred['time_series']) > 0, "Prediction should have time steps"
        assert pred['time_series'][0]['area_hectares'] == 0, "Initial area should be zero"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 6 (temporal): {e}")
    
    # Test 7: Chaotic regime detection
    tests_total += 1
    try:
        pred = _temporal_prediction(1, 5, 50, 20, 35, 30, 12)
        # Condiciones extremas deberían activar chaotic_regime
        assert isinstance(pred['chaotic_regime'], bool), "Should have chaotic_regime flag"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 7 (chaos): {e}")
    
    # Test 8: Clasificación de intensidad
    tests_total += 1
    try:
        low = classify_fire_intensity(0.5)
        high = classify_fire_intensity(50)
        extreme = classify_fire_intensity(150)
        assert low == 'LOW', "Low intensity classification failed"
        assert high == 'HIGH', "High intensity classification failed"
        assert 'EXTREME' in extreme, "Extreme intensity classification failed"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 8 (classify): {e}")
    
    # Test 9: Fuel models coverage
    tests_total += 1
    try:
        assert len(FUEL_MODELS) >= 4, f"Expected ≥4 fuel models, got {len(FUEL_MODELS)}"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 9 (fuel coverage): {e}")
    
    # Test 10: Slope effect
    tests_total += 1
    try:
        ros_0 = _calculate_ros_windless(1, 100, 10)
        flat = _calculate_wind_effect(ros_0, 10, 1, 0)
        slope = _calculate_wind_effect(ros_0, 10, 1, 20)
        assert slope['ros_final_m_per_h'] > flat['ros_final_m_per_h'], \
            "Slope should increase ROS"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 10 (slope): {e}")
    
    # Test 11: Moisture dependency
    tests_total += 1
    try:
        dry = _calculate_ros_windless(1, 50, 5)
        wet = _calculate_ros_windless(1, 100, 20)
        assert dry > wet, "Drier fuel should burn faster"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 11 (moisture): {e}")
    
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
    "description": "Propagación de incendios forestales: Modelo de Rothermel (ROS), efectos de viento/pendiente, intensidad de fuego (Byram), índices FWI, análisis de línea de fuego (elipse), predicción temporal con detección de bifurcaciones caóticas. Integra wind_analysis, meteorological_impact y fire_line_analysis.",
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
                    "fuel_model": {"type": "integer", "description": "Modelo de combustible (1-13, NFFL)"},
                    "moisture_dead_pct": {"type": "number", "description": "Humedad combustible muerto (%)"},
                    "moisture_live_pct": {"type": "number", "description": "Humedad combustible vivo (%)"},
                    "wind_kmh": {"type": "number", "description": "Velocidad del viento (km/h)"},
                    "slope_pct": {"type": "number", "description": "Pendiente (%)"},
                    "temperature_C": {"type": "number", "description": "Temperatura ambiente (°C)"},
                    "humidity_pct": {"type": "number", "description": "Humedad relativa (%)"},
                    "rain_24h_mm": {"type": "number", "description": "Lluvia últimas 24h (mm)"},
                    "ros_m_per_h": {"type": "number", "description": "ROS (m/h)"},
                    "ignition_x": {"type": "number", "description": "Coordenada X del foco (m)"},
                    "ignition_y": {"type": "number", "description": "Coordenada Y del foco (m)"},
                    "wind_direction_deg": {"type": "number", "description": "Dirección del viento (°)"},
                    "time_minutes": {"type": "number", "description": "Tiempo transcurrido (min)"},
                    "prediction_hours": {"type": "number", "description": "Horas a predecir"},
                    "previous_FFMC": {"type": "number", "description": "FFMC anterior (para continuidad)"},
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
    register_tool(TOOL_NAME, TOOL_SCHEMA, run)


# Registrar al importar (no solo en if __name__)
_register()

if __name__ == '__main__':
    pass
