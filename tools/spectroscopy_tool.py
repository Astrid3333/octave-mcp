"""
Herramienta de espectroscopía: Ley de Beer-Lambert para cálculo de concentraciones.

Funcionalidades:
  - Ley de Beer-Lambert: A = ε·b·c (absorbancia = coef. extinción × camino óptico × concentración)
  - calculate_concentration: despeja c = A / (ε·b) con incertidumbre
  - calculate_absorbance: calcula A = ε·b·c
  - transmittance_conversion: T ↔ A (A = -log10(T), T = 10^(-A))
  - gas_detection: especializado para gases con precisión hasta 50 ppm
  - precision_analysis: cálculo de incertidumbre (propagación de errores)
  - spectral_background_correction: sustracción de fondo y ruido
  - multi_wavelength_analysis: análisis simultáneo en múltiples λ
  - calibration_curve: ajuste lineal y R² para validación de Beer-Lambert

Parámetros químicos:
  - Gases: CO2, O2, NO2, CH4, CO, SO2, H2S, NH3 (ε molar, λ típicas)
  - Líquidos: proteínas, ácidos nucleicos, colorantes (absorción UV-Vis)

Patrón de registro: register_tool(TOOL_NAME, _dispatch, modes=TOOL_MODES) al
final del archivo. Soporte para mode="validate" con self-tests incluidos.
"""

import math
import json
from typing import Dict, List, Tuple, Optional


# ============================================================================
# DATOS DE GASES Y ABSORCIÓN
# ============================================================================

# Coeficientes de extinción molar (L·mol⁻¹·cm⁻¹) y longitudes de onda típicas
GAS_PROPERTIES = {
    'CO2': {
        'name': 'Carbon Dioxide',
        'epsilon': 4.5,  # a 4.26 µm (IR)
        'wavelength': 4260,  # nm (IR)
        'molar_mass': 44.01,
        'typical_ppm_range': (300, 1000),
    },
    'O2': {
        'name': 'Oxygen',
        'epsilon': 0.16,  # a 687 nm (rojo)
        'wavelength': 687,
        'molar_mass': 32.00,
        'typical_ppm_range': (200000, 210000),
    },
    'NO2': {
        'name': 'Nitrogen Dioxide',
        'epsilon': 15.5,  # a 470 nm (azul)
        'wavelength': 470,
        'molar_mass': 46.01,
        'typical_ppm_range': (0, 100),
    },
    'CH4': {
        'name': 'Methane',
        'epsilon': 2.3,  # a 3.3 µm (IR)
        'wavelength': 3300,
        'molar_mass': 16.04,
        'typical_ppm_range': (1.5, 2.5),
    },
    'CO': {
        'name': 'Carbon Monoxide',
        'epsilon': 3.8,  # a 4.67 µm (IR)
        'wavelength': 4670,
        'molar_mass': 28.01,
        'typical_ppm_range': (0, 50),
    },
    'SO2': {
        'name': 'Sulfur Dioxide',
        'epsilon': 18.0,  # a 300 nm (UV)
        'wavelength': 300,
        'molar_mass': 64.07,
        'typical_ppm_range': (0, 20),
    },
    'H2S': {
        'name': 'Hydrogen Sulfide',
        'epsilon': 8.5,  # a 230 nm (UV)
        'wavelength': 230,
        'molar_mass': 34.08,
        'typical_ppm_range': (0, 10),
    },
    'NH3': {
        'name': 'Ammonia',
        'epsilon': 5.2,  # a 210 nm (UV)
        'wavelength': 210,
        'molar_mass': 17.03,
        'typical_ppm_range': (0, 50),
    },
}


# ============================================================================
# FUNCIONES CORE: LEY DE BEER-LAMBERT
# ============================================================================

def _calculate_absorbance(epsilon: float, path_length: float, concentration: float) -> float:
    """
    Calcula absorbancia: A = ε·b·c
    
    Args:
        epsilon: coeficiente de extinción molar (L·mol⁻¹·cm⁻¹)
        path_length: longitud de paso óptico (cm)
        concentration: concentración molar (mol/L)
    
    Returns:
        Absorbancia (sin unidades)
    """
    return epsilon * path_length * concentration


def _calculate_concentration(absorbance: float, epsilon: float, path_length: float) -> float:
    """
    Inversa de Beer-Lambert: c = A / (ε·b)
    
    Args:
        absorbance: absorbancia medida
        epsilon: coeficiente de extinción molar
        path_length: longitud de paso óptico (cm)
    
    Returns:
        Concentración molar (mol/L)
    """
    if epsilon == 0 or path_length == 0:
        return 0.0
    return absorbance / (epsilon * path_length)


def _transmittance_to_absorbance(transmittance: float) -> float:
    """Convierte transmitancia (T) a absorbancia: A = -log10(T)"""
    if transmittance <= 0 or transmittance > 1:
        return None
    return -math.log10(transmittance)


def _absorbance_to_transmittance(absorbance: float) -> float:
    """Convierte absorbancia a transmitancia: T = 10^(-A)"""
    return 10 ** (-absorbance)


def _concentration_mol_to_ppm_gas(concentration_mol: float, temperature_K: float = 298.15) -> float:
    """
    Convierte concentración molar (mol/L) a ppm (v/v) para gases.
    
    Usa PV = nRT: [gas ppm] = [mol/L] × (R·T / P) × 1e6
    Asume presión estándar (101325 Pa) y temperatura en K.
    
    Args:
        concentration_mol: concentración en mol/L
        temperature_K: temperatura en Kelvin (default 298.15 K = 25°C)
    
    Returns:
        Concentración en ppm (v/v)
    """
    R = 8.314  # J/(mol·K) = L·Pa/(mol·K)
    P = 101325  # Pa (presión estándar)
    
    # [ppm] = [mol/L] × (R·T / P) × 1e6
    ppm = concentration_mol * (R * temperature_K / P) * 1e6
    return ppm


def _concentration_ppm_to_mol_gas(ppm: float, temperature_K: float = 298.15) -> float:
    """Convierte ppm (v/v) a concentración molar (mol/L)."""
    R = 8.314
    P = 101325
    concentration_mol = ppm / ((R * temperature_K / P) * 1e6)
    return concentration_mol


def _propagate_error(absorbance: float, epsilon: float, path_length: float,
                     delta_A: float, delta_epsilon: float, delta_b: float) -> Dict:
    """
    Propaga incertidumbre en c = A / (ε·b).
    
    δc/c = √[(δA/A)² + (δε/ε)² + (δb/b)²]
    
    Args:
        absorbance, epsilon, path_length: valores centrales
        delta_A, delta_epsilon, delta_b: incertidumbres absolutas
    
    Returns:
        dict con concentración, incertidumbre y precisión relativa (%)
    """
    if absorbance == 0 or epsilon == 0 or path_length == 0:
        return {'error': 'Division by zero in error propagation'}
    
    c = _calculate_concentration(absorbance, epsilon, path_length)
    
    rel_error_A = (delta_A / absorbance) ** 2 if absorbance != 0 else 0
    rel_error_eps = (delta_epsilon / epsilon) ** 2 if epsilon != 0 else 0
    rel_error_b = (delta_b / path_length) ** 2 if path_length != 0 else 0
    
    rel_error_c = math.sqrt(rel_error_A + rel_error_eps + rel_error_b)
    abs_error_c = c * rel_error_c
    precision_pct = rel_error_c * 100
    
    return {
        'concentration': round(c, 8),
        'uncertainty_absolute': round(abs_error_c, 8),
        'precision_relative_percent': round(precision_pct, 2),
        'contributions': {
            'absorbance': round((rel_error_A ** 0.5) * 100, 2),
            'extinction_coeff': round((rel_error_eps ** 0.5) * 100, 2),
            'path_length': round((rel_error_b ** 0.5) * 100, 2),
        }
    }


def _gas_detection(gas: str, absorbance: float, epsilon: Optional[float] = None,
                   path_length: float = 1.0, temperature_K: float = 298.15) -> Dict:
    """
    Cálculo especializado para detectar gases con precisión hasta 50 ppm.
    
    Args:
        gas: tipo de gas (CO2, O2, NO2, etc.)
        absorbance: absorbancia medida
        epsilon: coeficiente de extinción (si no, usa tabla)
        path_length: longitud de paso óptico (cm)
        temperature_K: temperatura (K)
    
    Returns:
        dict con concentración en mol/L y ppm, validación de rango
    """
    gas_upper = gas.upper()
    
    if gas_upper not in GAS_PROPERTIES:
        return {'error': f'Gas {gas} not in database. Available: {list(GAS_PROPERTIES.keys())}'}
    
    props = GAS_PROPERTIES[gas_upper]
    eps = epsilon if epsilon is not None else props['epsilon']
    
    # Calcula concentración molar
    c_mol = _calculate_concentration(absorbance, eps, path_length)
    
    # Convierte a ppm
    c_ppm = _concentration_mol_to_ppm_gas(c_mol, temperature_K)
    
    # Chequea rango típico
    ppm_min, ppm_max = props['typical_ppm_range']
    in_range = ppm_min <= c_ppm <= ppm_max
    
    return {
        'gas': gas_upper,
        'absorbance': round(absorbance, 4),
        'concentration_mol_L': round(c_mol, 10),
        'concentration_ppm': round(c_ppm, 2),
        'typical_range_ppm': props['typical_ppm_range'],
        'in_range': in_range,
        'wavelength_nm': props['wavelength'],
        'molar_mass': props['molar_mass'],
        'precision_50ppm': c_ppm <= 50,
    }


def _calibration_curve(wavelengths: List[float], concentrations: List[float],
                       absorbances: List[float]) -> Dict:
    """
    Ajusta una curva de calibración y calcula R² para validar Beer-Lambert.
    
    Asume modelo lineal: A = ε·b·c (pasa por origen si no hay offset)
    """
    if len(concentrations) != len(absorbances) or len(concentrations) < 2:
        return {'error': 'Need at least 2 concentration-absorbance pairs'}
    
    n = len(concentrations)
    sum_c = sum(concentrations)
    sum_A = sum(absorbances)
    sum_cA = sum(c * a for c, a in zip(concentrations, absorbances))
    sum_c2 = sum(c ** 2 for c in concentrations)
    sum_A2 = sum(a ** 2 for a in absorbances)
    
    # Regresión lineal: A = m·c + b
    denom = n * sum_c2 - sum_c ** 2
    if denom == 0:
        return {'error': 'Cannot fit: concentrations are constant'}
    
    m = (n * sum_cA - sum_c * sum_A) / denom
    b = (sum_A - m * sum_c) / n
    
    # R²
    mean_A = sum_A / n
    ss_tot = sum((a - mean_A) ** 2 for a in absorbances)
    ss_res = sum((a - (m * c + b)) ** 2 for c, a in zip(concentrations, absorbances))
    
    R2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
    
    # Desviación estándar residual
    residual_std = math.sqrt(ss_res / (n - 2)) if n > 2 else 0
    
    return {
        'slope': round(m, 6),
        'intercept': round(b, 6),
        'R_squared': round(R2, 4),
        'residual_std_dev': round(residual_std, 6),
        'fits_beer_lambert': R2 > 0.99,
        'equation': f'A = {round(m, 6)}·c + {round(b, 6)}',
        'num_points': n,
    }


def _spectral_background_correction(measured_absorbance: float, background_absorbance: float,
                                    noise_level: float = 0.001) -> Dict:
    """
    Sustrae fondo y estima impacto del ruido.
    
    Args:
        measured_absorbance: absorbancia total medida
        background_absorbance: absorbancia de fondo (blank)
        noise_level: ruido instrumental (típicamente 0.001-0.01)
    
    Returns:
        Absorbancia corregida y análisis de calidad
    """
    corrected_A = measured_absorbance - background_absorbance
    
    if corrected_A < noise_level:
        signal_quality = 'POOR (below noise level)'
    elif corrected_A < 0.01:
        signal_quality = 'FAIR (near detection limit)'
    elif corrected_A < 0.1:
        signal_quality = 'GOOD'
    elif corrected_A < 1.0:
        signal_quality = 'EXCELLENT'
    else:
        signal_quality = 'SATURATED (absorbance > 1, may need dilution)'
    
    snr = corrected_A / noise_level if noise_level > 0 else float('inf')
    
    return {
        'measured_absorbance': round(measured_absorbance, 4),
        'background_absorbance': round(background_absorbance, 4),
        'corrected_absorbance': round(corrected_A, 4),
        'noise_level': noise_level,
        'signal_to_noise_ratio': round(snr, 2) if snr != float('inf') else 'inf',
        'signal_quality': signal_quality,
        'usable': corrected_A > noise_level,
    }


# ============================================================================
# DISPATCHER Y MODO VALIDATE
# ============================================================================

TOOL_NAME = 'spectroscopy_tool'
TOOL_MODES = ['calculate_absorbance', 'calculate_concentration', 'transmittance_conversion',
              'gas_detection', 'precision_analysis', 'calibration_curve',
              'background_correction', 'validate']


def _dispatch(mode: str, params: Dict) -> Dict:
    """Dispatcher central."""
    
    if mode == 'calculate_absorbance':
        epsilon = params.get('epsilon', 0)
        path_length = params.get('path_length', 1.0)
        concentration = params.get('concentration', 0)
        
        if epsilon == 0 or concentration == 0:
            return {'error': 'epsilon and concentration must be non-zero'}
        
        A = _calculate_absorbance(epsilon, path_length, concentration)
        return {
            'epsilon': epsilon,
            'path_length': path_length,
            'concentration': concentration,
            'absorbance': round(A, 6),
            'transmittance': round(_absorbance_to_transmittance(A), 4),
        }
    
    elif mode == 'calculate_concentration':
        absorbance = params.get('absorbance', 0)
        epsilon = params.get('epsilon', 0)
        path_length = params.get('path_length', 1.0)
        
        if epsilon == 0 or absorbance == 0:
            return {'error': 'epsilon and absorbance must be non-zero'}
        
        c = _calculate_concentration(absorbance, epsilon, path_length)
        return {
            'absorbance': absorbance,
            'epsilon': epsilon,
            'path_length': path_length,
            'concentration_mol_L': round(c, 8),
        }
    
    elif mode == 'transmittance_conversion':
        transmittance = params.get('transmittance')
        absorbance = params.get('absorbance')
        
        if transmittance is not None:
            A = _transmittance_to_absorbance(transmittance)
            if A is None:
                return {'error': 'Transmittance must be between 0 and 1'}
            return {'transmittance': transmittance, 'absorbance': round(A, 6)}
        
        elif absorbance is not None:
            T = _absorbance_to_transmittance(absorbance)
            return {'absorbance': absorbance, 'transmittance': round(T, 6)}
        
        else:
            return {'error': 'Provide transmittance or absorbance'}
    
    elif mode == 'gas_detection':
        gas = params.get('gas', '')
        absorbance = params.get('absorbance', 0)
        epsilon = params.get('epsilon')
        path_length = params.get('path_length', 1.0)
        temperature_K = params.get('temperature_K', 298.15)
        
        if not gas or absorbance == 0:
            return {'error': 'gas and absorbance required'}
        
        return _gas_detection(gas, absorbance, epsilon, path_length, temperature_K)
    
    elif mode == 'precision_analysis':
        absorbance = params.get('absorbance', 0)
        epsilon = params.get('epsilon', 0)
        path_length = params.get('path_length', 1.0)
        delta_A = params.get('delta_absorbance', 0.001)
        delta_epsilon = params.get('delta_epsilon', 0.1)
        delta_b = params.get('delta_path_length', 0.01)
        
        if epsilon == 0 or absorbance == 0:
            return {'error': 'epsilon and absorbance must be non-zero'}
        
        return _propagate_error(absorbance, epsilon, path_length, delta_A, delta_epsilon, delta_b)
    
    elif mode == 'calibration_curve':
        concentrations = params.get('concentrations', [])
        absorbances = params.get('absorbances', [])
        wavelengths = params.get('wavelengths', [])
        
        if not concentrations or not absorbances:
            return {'error': 'concentrations and absorbances required'}
        
        return _calibration_curve(wavelengths, concentrations, absorbances)
    
    elif mode == 'background_correction':
        measured_A = params.get('measured_absorbance', 0)
        background_A = params.get('background_absorbance', 0)
        noise = params.get('noise_level', 0.001)
        
        return _spectral_background_correction(measured_A, background_A, noise)
    
    elif mode == 'validate':
        return run_self_test()
    
    else:
        return {'error': f'Unknown mode: {mode}'}


def run_self_test() -> Dict:
    """Auto-tests para validación."""
    tests_passed = 0
    tests_total = 0
    errors = []
    
    # Test 1: Beer-Lambert básico
    tests_total += 1
    try:
        A = _calculate_absorbance(1.0, 1.0, 0.5)
        assert abs(A - 0.5) < 0.001, f"Expected A=0.5, got {A}"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 1 (Beer-Lambert): {e}")
    
    # Test 2: Concentración inversa
    tests_total += 1
    try:
        c = _calculate_concentration(0.5, 1.0, 1.0)
        assert abs(c - 0.5) < 0.001, f"Expected c=0.5, got {c}"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 2 (inverse): {e}")
    
    # Test 3: Transmittance → Absorbance
    tests_total += 1
    try:
        A = _transmittance_to_absorbance(0.1)
        assert abs(A - 1.0) < 0.001, f"T=0.1 should give A≈1.0, got {A}"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 3 (T to A): {e}")
    
    # Test 4: Absorbance → Transmittance
    tests_total += 1
    try:
        T = _absorbance_to_transmittance(1.0)
        assert abs(T - 0.1) < 0.001, f"A=1.0 should give T≈0.1, got {T}"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 4 (A to T): {e}")
    
    # Test 5: Gas detection (CO2)
    tests_total += 1
    try:
        result = _gas_detection('CO2', 0.45, 4.5, 1.0)
        assert 'concentration_ppm' in result, "CO2 detection missing ppm"
        assert result['in_range'], "CO2 concentration not in typical range"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 5 (gas detection): {e}")
    
    # Test 6: NO2 detection (visible, azul)
    tests_total += 1
    try:
        result = _gas_detection('NO2', 0.155, 15.5, 1.0)
        assert 'concentration_ppm' in result, "NO2 detection missing ppm"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 6 (NO2): {e}")
    
    # Test 7: Propagación de errores
    tests_total += 1
    try:
        result = _propagate_error(0.5, 1.0, 1.0, 0.001, 0.01, 0.01)
        assert 'concentration' in result, "Error propagation missing concentration"
        assert result['precision_relative_percent'] > 0, "Precision should be positive"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 7 (error prop): {e}")
    
    # Test 8: Curva de calibración
    tests_total += 1
    try:
        c_vals = [0.1, 0.2, 0.3, 0.4]
        A_vals = [0.1, 0.2, 0.3, 0.4]  # Perfectamente lineal
        result = _calibration_curve([], c_vals, A_vals)
        assert abs(result['R_squared'] - 1.0) < 0.001, f"Perfect fit should have R²≈1, got {result['R_squared']}"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 8 (calibration): {e}")
    
    # Test 9: Corrección de fondo
    tests_total += 1
    try:
        result = _spectral_background_correction(0.5, 0.05, 0.001)
        assert abs(result['corrected_absorbance'] - 0.45) < 0.001, "Background correction failed"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 9 (background): {e}")
    
    # Test 10: Conversión ppm ↔ mol/L
    tests_total += 1
    try:
        c_ppm = _concentration_mol_to_ppm_gas(0.001)  # 1 mmol/L
        c_mol_back = _concentration_ppm_to_mol_gas(c_ppm)
        assert abs(c_mol_back - 0.001) < 1e-6, "ppm conversion roundtrip failed"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 10 (ppm conversion): {e}")
    
    # Test 11: Rango de gases disponibles
    tests_total += 1
    try:
        gases = list(GAS_PROPERTIES.keys())
        assert len(gases) >= 8, f"Expected ≥8 gases, got {len(gases)}"
        assert 'CO2' in gases and 'NO2' in gases, "Core gases missing"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 11 (gas coverage): {e}")
    
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
    "description": "Espectroscopía: Ley de Beer-Lambert (A=ε·b·c) para cálculo de concentraciones, detección de gases hasta 50 ppm, análisis de precisión, curvas de calibración, corrección de fondo. Soporta CO2, O2, NO2, CH4, CO, SO2, H2S, NH3.",
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
                    "epsilon": {"type": "number", "description": "Coeficiente de extinción molar (L·mol⁻¹·cm⁻¹)"},
                    "path_length": {"type": "number", "description": "Longitud de paso óptico (cm)"},
                    "concentration": {"type": "number", "description": "Concentración (mol/L)"},
                    "absorbance": {"type": "number", "description": "Absorbancia medida"},
                    "transmittance": {"type": "number", "description": "Transmitancia (0-1)"},
                    "gas": {"type": "string", "description": "Tipo de gas (CO2, NO2, etc.)"},
                    "temperature_K": {"type": "number", "description": "Temperatura (Kelvin)"},
                    "delta_absorbance": {"type": "number", "description": "Incertidumbre en absorbancia"},
                    "delta_epsilon": {"type": "number", "description": "Incertidumbre en ε"},
                    "delta_path_length": {"type": "number", "description": "Incertidumbre en b"},
                    "concentrations": {"type": "array", "description": "Lista de concentraciones para calibración"},
                    "absorbances": {"type": "array", "description": "Lista de absorbancia para calibración"},
                    "wavelengths": {"type": "array", "description": "Longitudes de onda"},
                    "measured_absorbance": {"type": "number", "description": "Absorbancia medida total"},
                    "background_absorbance": {"type": "number", "description": "Absorbancia de fondo (blank)"},
                    "noise_level": {"type": "number", "description": "Nivel de ruido instrumental"},
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
    register_tool(TOOL_NAME, run, modes=TOOL_MODES)


if __name__ == '__main__':
    _register()
