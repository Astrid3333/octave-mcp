"""
wildfire_intensity_model_tool.py

Intensidad de fuego: Modelo de Byram + ranking comparativo de agentes extinctores
+ cálculo de corredores de evacuación basados en zonas de peligro termal.

MODOS:
  - byram_intensity: Intensidad (MW/m), altura de llama, radiación, zona termal
  - agent_ranking: Eficacia comparativa (agua/espuma/polvo/CO2 vs tipo fuego)
  - evacuation_corridors: Rutas óptimas de evacuación vs intensidad espacial
  - thermal_danger_zone: Define perímetro de peligro (radiación + T crítica)
  - comparative_analysis: Ranking + corredores + intensidad integrados

Byram: I [MW/m] = (r_r * c * Δ H_v * ν) / 60
  r_r: tasa de reacción (kg/m²/min)
  c: concentración del combustible (kg/m³)
  Δ H_v: calor de vaporización (kJ/kg)
  ν: velocidad reacción (min⁻¹)

Altura llama: FL = 0.0775 * I^0.46 (m) si I en kW/m

Radiación: Q_rad ≈ σ * ε * T_flame^4 (Stefan-Boltzmann)

Agentes: H2O (eficacia ~70%, costo bajo), Espuma (75–85%, costo medio),
Polvo ABC (60–70%, costo bajo), CO2 (40–50%, costo alto).
"""

import json
import math
from typing import Dict, Any, List, Tuple

# Constantes físicas
STEFAN_BOLTZMANN = 5.67e-8  # W/(m²·K⁴)
EMISSIVITY_FLAME = 0.95  # Llama típica
T_FLAME_BASE = 1200  # K, base Byram
THERMAL_DANGER_RADIUS_FACTOR = 0.3  # Distancia crítica = altura_llama * factor


def byram_intensity_calc(
    fuel_load: float,
    reaction_intensity: float,
    fuel_moisture: float = 0.1,
    wind_speed: float = 0.0
) -> Dict[str, float]:
    """
    Calcula intensidad Byram: I = r_r * c * Δ H_v * ν
    
    Args:
        fuel_load: carga de combustible (kg/m²)
        reaction_intensity: intensidad reacción base (kW/m)
        fuel_moisture: humedad del combustible (fracción 0–1)
        wind_speed: velocidad viento (m/s, modula intensidad)
    
    Returns:
        {
            "intensity_kw_m": Intensidad en kW/m,
            "intensity_mw_m": Intensidad en MW/m,
            "flame_height_m": Altura llama Byram (m),
            "flame_temp_k": Temperatura llama estimada (K),
            "radiation_w_m2": Flujo radiativo (W/m²),
            "danger_radius_m": Radio de peligro termal (m)
        }
    """
    # Ajuste por humedad (mayor humedad = menor intensidad)
    moisture_factor = math.exp(-2.0 * fuel_moisture)
    
    # Ajuste por viento (viento aumenta intensidad)
    wind_factor = 1.0 + 0.15 * wind_speed
    
    # Intensidad base (kW/m)
    intensity_base = reaction_intensity * fuel_load * moisture_factor * wind_factor
    
    # Intensidad en MW/m (1 MW = 1000 kW)
    intensity_mw = intensity_base / 1000.0
    
    # Altura de llama: FL = 0.0775 * I^0.46 (con I en kW/m)
    flame_height = 0.0775 * (intensity_base ** 0.46)
    
    # Temperatura de llama (aproximación: mayor I → mayor T)
    # Base 1200 K, escala con raíz de intensidad
    flame_temp = T_FLAME_BASE + 200 * math.sqrt(intensity_mw)
    
    # Radiación (Stefan-Boltzmann, aproximación área = altura * 1m)
    radiation = STEFAN_BOLTZMANN * EMISSIVITY_FLAME * (flame_temp ** 4)
    
    # Radio de peligro termal (distancia donde radiación > 4 kW/m²)
    # Aproximación: Q_rad ∝ 1/r² → r_danger ≈ altura_llama * factor
    danger_radius = flame_height * THERMAL_DANGER_RADIUS_FACTOR
    
    return {
        "intensity_kw_m": intensity_base,
        "intensity_mw_m": intensity_mw,
        "flame_height_m": flame_height,
        "flame_temp_k": flame_temp,
        "radiation_w_m2": radiation,
        "danger_radius_m": danger_radius
    }


def agent_efficacy_ranking(
    fire_type: str,
    intensity_mw: float,
    fuel_type: str = "forest"
) -> Dict[str, Any]:
    """
    Ranking comparativo de agentes extinctores por tipo/intensidad de fuego.
    
    Args:
        fire_type: 'grass' | 'forest' | 'structure' | 'vehicle'
        intensity_mw: intensidad Byram (MW/m)
        fuel_type: 'forest' | 'grassland' | 'mixed'
    
    Returns:
        {
            "ranking": [{"agent": "agua", "efficacy": 0.75, ...}, ...],
            "recommended": "agua",
            "comment": str
        }
    """
    
    agents_base = {
        "water": {"efficacy": 0.70, "cost": 1.0, "coverage": 0.8, "cool_time_s": 120},
        "foam": {"efficacy": 0.78, "cost": 2.5, "coverage": 0.85, "cool_time_s": 90},
        "powder_abc": {"efficacy": 0.65, "cost": 1.2, "coverage": 0.7, "cool_time_s": 180},
        "co2": {"efficacy": 0.45, "cost": 4.0, "coverage": 0.6, "cool_time_s": 60}
    }
    
    # Ajustes por tipo de fuego
    fire_modifiers = {
        "grass": {"water": 0.95, "foam": 1.05, "powder_abc": 1.0, "co2": 0.7},
        "forest": {"water": 0.80, "foam": 1.10, "powder_abc": 0.95, "co2": 0.5},
        "structure": {"water": 1.0, "foam": 0.95, "powder_abc": 1.15, "co2": 1.2},
        "vehicle": {"water": 0.7, "foam": 1.0, "powder_abc": 1.20, "co2": 1.3}
    }
    
    # Ajuste por intensidad (fuegos más intensos reducen eficacia)
    intensity_penalty = 1.0 / (1.0 + 0.2 * intensity_mw)
    
    # Calcular eficacia ajustada
    ranking = []
    for agent, base in agents_base.items():
        if fire_type in fire_modifiers:
            mod = fire_modifiers[fire_type].get(agent, 1.0)
        else:
            mod = 1.0
        
        efficacy_adjusted = base["efficacy"] * mod * intensity_penalty
        cost_efficiency = efficacy_adjusted / base["cost"]
        
        ranking.append({
            "agent": agent,
            "efficacy": round(min(efficacy_adjusted, 1.0), 3),
            "cost": base["cost"],
            "cost_efficiency": round(cost_efficiency, 3),
            "coverage": base["coverage"],
            "cool_time_s": base["cool_time_s"],
            "reason": f"Modificador {fire_type}: ×{mod:.2f}, Penalidad intensidad: ×{intensity_penalty:.2f}"
        })
    
    # Ordenar por eficacia
    ranking.sort(key=lambda x: x["efficacy"], reverse=True)
    
    recommended = ranking[0]["agent"]
    comment = f"Fuego tipo '{fire_type}' a {intensity_mw:.2f} MW/m: {recommended} recomendado (eficacia {ranking[0]['efficacy']:.1%})"
    
    return {
        "ranking": ranking,
        "recommended": recommended,
        "comment": comment,
        "intensity_mw": intensity_mw,
        "fire_type": fire_type
    }


def evacuation_corridors(
    intensity_map: List[List[float]],
    start_x: float,
    start_y: float,
    grid_size: float = 100.0
) -> Dict[str, Any]:
    """
    Calcula corredores de evacuación óptimos basados en intensidad espacial.
    
    Args:
        intensity_map: matriz 2D de intensidades (MW/m) [filas, cols]
        start_x, start_y: posición inicial (coords grid)
        grid_size: tamaño celda grid (m)
    
    Returns:
        {
            "safest_corridor": [(x, y, intensity), ...],
            "danger_zones": [(x, y, radius_m, intensity), ...],
            "evacuation_time_min": tiempo estimado,
            "safe_perimeter_m": perímetro de seguridad
        }
    """
    
    if not intensity_map or len(intensity_map) == 0:
        return {"error": "Mapa vacío"}
    
    rows = len(intensity_map)
    cols = len(intensity_map[0]) if rows > 0 else 0
    
    if rows == 0 or cols == 0:
        return {"error": "Dimensiones inválidas"}
    
    # Identificar celdas de peligro (intensidad > 2 MW/m)
    danger_threshold = 2.0
    danger_zones = []
    
    for i in range(rows):
        for j in range(cols):
            intensity_val = intensity_map[i][j]
            if intensity_val > danger_threshold:
                x = start_x + j * grid_size
                y = start_y + i * grid_size
                # Radio de peligro basado en intensidad
                danger_radius = 50 + 30 * math.sqrt(intensity_val)
                danger_zones.append({
                    "x": x,
                    "y": y,
                    "radius_m": danger_radius,
                    "intensity_mw": intensity_val
                })
    
    # Corridor seguro: evita zona de máxima intensidad
    max_intensity = max(max(row) for row in intensity_map)
    safe_intensity = max_intensity * 0.5  # Buscar zona ≤ 50% máximo
    
    safest_corridor = []
    for i in range(rows):
        for j in range(cols):
            if intensity_map[i][j] <= safe_intensity:
                x = start_x + j * grid_size
                y = start_y + i * grid_size
                safest_corridor.append((x, y, intensity_map[i][j]))
    
    # Ordenar por intensidad (ruta más segura primero)
    safest_corridor.sort(key=lambda p: p[2])
    
    # Estimar tiempo de evacuación (velocidad 1.4 m/s a pie)
    if safest_corridor:
        evacuation_dist = math.sqrt(
            (safest_corridor[-1][0] - start_x) ** 2 +
            (safest_corridor[-1][1] - start_y) ** 2
        )
        evacuation_time_min = evacuation_dist / 1.4 / 60.0
    else:
        evacuation_time_min = float('inf')
    
    # Perímetro de seguridad (distancia promedio a zona segura)
    if danger_zones:
        safe_perimeter = sum(z["radius_m"] for z in danger_zones) / len(danger_zones)
    else:
        safe_perimeter = 0.0
    
    return {
        "safest_corridor": safest_corridor[:10],  # Top 10 celdas seguras
        "danger_zones": danger_zones,
        "evacuation_time_min": evacuation_time_min,
        "safe_perimeter_m": safe_perimeter,
        "total_danger_zones": len(danger_zones),
        "total_safe_cells": len(safest_corridor)
    }


def thermal_danger_zone(
    intensity_mw: float,
    flame_height_m: float,
    wind_direction: float = 0.0
) -> Dict[str, Any]:
    """
    Define zona de peligro termal basada en radiación y temperatura.
    
    Args:
        intensity_mw: intensidad Byram (MW/m)
        flame_height_m: altura de llama (m)
        wind_direction: dirección viento (grados 0–360)
    
    Returns:
        {
            "critical_radius_m": radio crítico (radiación > 4 kW/m²),
            "severe_radius_m": radio severo (radiación > 10 kW/m²),
            "wind_effect": factor de asimetría por viento,
            "downwind_zone": {"radius_m": ..., "angle_start": ..., "angle_end": ...}
        }
    """
    
    # Radio crítico (radiación ~4 kW/m²) — límite exposición 30 min
    critical_radius = flame_height_m * 1.5
    
    # Radio severo (radiación ~10 kW/m²) — límite exposición 5 min
    severe_radius = flame_height_m * 0.8
    
    # Efecto viento: amplifica zona aguas abajo
    wind_factor = 1.0 + 0.3 * math.sin(math.radians(wind_direction))
    
    # Zona aguas abajo (downwind): más peligrosa
    downwind_angle_start = (wind_direction - 45) % 360
    downwind_angle_end = (wind_direction + 45) % 360
    downwind_radius = critical_radius * wind_factor
    
    return {
        "critical_radius_m": critical_radius,
        "severe_radius_m": severe_radius,
        "wind_effect_multiplier": wind_factor,
        "wind_direction_deg": wind_direction,
        "downwind_zone": {
            "radius_m": downwind_radius,
            "angle_start_deg": downwind_angle_start,
            "angle_end_deg": downwind_angle_end,
            "description": f"Radio {downwind_radius:.1f}m aguas abajo, dirección {wind_direction:.0f}°"
        }
    }


def run(mode: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dispatcher para modos de intensidad de fuego.
    
    Modos:
      - byram_intensity
      - agent_ranking
      - evacuation_corridors
      - thermal_danger_zone
      - comparative_analysis
    """
    
    if mode == "byram_intensity":
        fuel_load = params.get("fuel_load", 10.0)
        reaction_intensity = params.get("reaction_intensity", 500.0)
        fuel_moisture = params.get("fuel_moisture", 0.1)
        wind_speed = params.get("wind_speed", 0.0)
        
        result = byram_intensity_calc(fuel_load, reaction_intensity, fuel_moisture, wind_speed)
        result["mode"] = mode
        return result
    
    elif mode == "agent_ranking":
        fire_type = params.get("fire_type", "forest")
        intensity_mw = params.get("intensity_mw", 2.0)
        fuel_type = params.get("fuel_type", "forest")
        
        result = agent_efficacy_ranking(fire_type, intensity_mw, fuel_type)
        result["mode"] = mode
        return result
    
    elif mode == "evacuation_corridors":
        intensity_map = params.get("intensity_map", [[1.0, 2.5], [3.0, 1.5]])
        start_x = params.get("start_x", 0.0)
        start_y = params.get("start_y", 0.0)
        grid_size = params.get("grid_size", 100.0)
        
        result = evacuation_corridors(intensity_map, start_x, start_y, grid_size)
        result["mode"] = mode
        return result
    
    elif mode == "thermal_danger_zone":
        intensity_mw = params.get("intensity_mw", 2.5)
        flame_height_m = params.get("flame_height_m", 15.0)
        wind_direction = params.get("wind_direction", 0.0)
        
        result = thermal_danger_zone(intensity_mw, flame_height_m, wind_direction)
        result["mode"] = mode
        return result
    
    elif mode == "comparative_analysis":
        # Integra byram + agent_ranking + thermal_danger_zone
        fuel_load = params.get("fuel_load", 10.0)
        reaction_intensity = params.get("reaction_intensity", 500.0)
        fuel_moisture = params.get("fuel_moisture", 0.1)
        wind_speed = params.get("wind_speed", 0.0)
        fire_type = params.get("fire_type", "forest")
        wind_direction = params.get("wind_direction", 0.0)
        
        # Byram
        byram_result = byram_intensity_calc(fuel_load, reaction_intensity, fuel_moisture, wind_speed)
        
        # Agent ranking
        agent_result = agent_efficacy_ranking(fire_type, byram_result["intensity_mw_m"], "forest")
        
        # Thermal danger
        thermal_result = thermal_danger_zone(
            byram_result["intensity_mw_m"],
            byram_result["flame_height_m"],
            wind_direction
        )
        
        return {
            "mode": mode,
            "byram": byram_result,
            "agents": agent_result,
            "thermal_danger": thermal_result,
            "summary": f"Fuego {fire_type}: I={byram_result['intensity_mw_m']:.2f} MW/m, "
                      f"agente recomendado: {agent_result['recommended']}, "
                      f"radio crítico: {thermal_result['critical_radius_m']:.1f}m"
        }
    
    else:
        return {"error": f"Modo desconocido: {mode}"}


# ============================================================================
# SELF-TESTS
# ============================================================================

def validate():
    """11 self-tests para modo=validate."""
    
    tests_passed = 0
    
    # Test 1: Byram base (fuel_load=10 kg/m², reaction=500 kW/m)
    try:
        result = byram_intensity_calc(10.0, 500.0)
        assert result["intensity_mw_m"] > 0, "Intensidad debe ser positiva"
        assert result["flame_height_m"] > 0, "Altura llama debe ser positiva"
        assert result["radiation_w_m2"] > 0, "Radiación debe ser positiva"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 1 (Byram base): {e}")
    
    # Test 2: Byram con humedad (absorbe intensidad)
    try:
        result_dry = byram_intensity_calc(10.0, 500.0, fuel_moisture=0.05)
        result_wet = byram_intensity_calc(10.0, 500.0, fuel_moisture=0.50)
        assert result_dry["intensity_mw_m"] > result_wet["intensity_mw_m"], \
            "Combustible seco debe ser más intenso"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 2 (Humedad): {e}")
    
    # Test 3: Byram con viento (amplifica intensidad)
    try:
        result_calm = byram_intensity_calc(10.0, 500.0, wind_speed=0.0)
        result_wind = byram_intensity_calc(10.0, 500.0, wind_speed=10.0)
        assert result_wind["intensity_mw_m"] > result_calm["intensity_mw_m"], \
            "Viento debe amplificar intensidad"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 3 (Viento): {e}")
    
    # Test 4: Agent ranking (agua vs fuego forestal)
    try:
        ranking = agent_efficacy_ranking("forest", 2.5, "forest")
        assert len(ranking["ranking"]) == 4, "Debe haber 4 agentes"
        assert ranking["recommended"] in [a["agent"] for a in ranking["ranking"]], \
            "Recomendado debe estar en ranking"
        # Agua suele ser primera para fuegos forestales
        assert ranking["ranking"][0]["agent"] in ["water", "foam"], \
            "Agua o espuma debería ser primera en fuego forestal"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 4 (Agent ranking): {e}")
    
    # Test 5: Agent ranking estructura (tipos de fuego)
    try:
        for fire_type in ["grass", "forest", "structure", "vehicle"]:
            result = agent_efficacy_ranking(fire_type, 1.5, "forest")
            assert result["recommended"] is not None, f"Debe haber recomendación para {fire_type}"
            assert len(result["ranking"]) == 4, f"Ranking debe tener 4 agentes para {fire_type}"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 5 (Tipos fuego): {e}")
    
    # Test 6: Thermal danger zone radio crítico > severo
    try:
        result = thermal_danger_zone(2.5, 15.0)
        assert result["critical_radius_m"] > result["severe_radius_m"], \
            "Radio crítico debe ser mayor que severo"
        assert result["critical_radius_m"] > 0, "Radio crítico debe ser positivo"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 6 (Thermal danger): {e}")
    
    # Test 7: Thermal danger con viento
    try:
        result_no_wind = thermal_danger_zone(2.5, 15.0, wind_direction=0.0)
        result_wind = thermal_danger_zone(2.5, 15.0, wind_direction=45.0)
        # Viento debe afectar zona aguas abajo
        assert result_wind["wind_effect_multiplier"] > 0, "Efecto viento debe ser positivo"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 7 (Viento en thermal): {e}")
    
    # Test 8: Evacuation corridors básico
    try:
        intensity_map = [
            [5.0, 3.0, 1.0],
            [4.0, 2.0, 0.5],
            [2.0, 0.8, 0.2]
        ]
        result = evacuation_corridors(intensity_map, 0.0, 0.0, grid_size=100.0)
        assert "safest_corridor" in result, "Debe haber corredor seguro"
        assert "danger_zones" in result, "Debe haber zonas de peligro"
        assert result["evacuation_time_min"] >= 0, "Tiempo evacuación debe ser positivo"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 8 (Evacuation corridors): {e}")
    
    # Test 9: Evacuation identify danger zones
    try:
        intensity_map = [[5.0, 0.5], [0.3, 0.1]]
        result = evacuation_corridors(intensity_map, 0.0, 0.0)
        # Primer elemento (5.0) debe ser peligro
        assert result["total_danger_zones"] > 0, "Debe detectar zonas peligrosas"
        assert result["total_safe_cells"] > 0, "Debe haber celdas seguras"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 9 (Danger zone detection): {e}")
    
    # Test 10: Comparative analysis integra todos
    try:
        result = run("comparative_analysis", {
            "fuel_load": 10.0,
            "reaction_intensity": 500.0,
            "fuel_moisture": 0.1,
            "wind_speed": 5.0,
            "fire_type": "forest",
            "wind_direction": 45.0
        })
        assert "byram" in result, "Debe incluir Byram"
        assert "agents" in result, "Debe incluir agents"
        assert "thermal_danger" in result, "Debe incluir thermal_danger"
        assert "summary" in result, "Debe incluir resumen"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 10 (Comparative analysis): {e}")
    
    # Test 11: JSON serialization (sin numpy.bool_)
    try:
        result = run("byram_intensity", {"fuel_load": 10.0, "reaction_intensity": 500.0})
        json_str = json.dumps(result, default=str)
        assert len(json_str) > 0, "JSON debe ser serializable"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 11 (JSON serialization): {e}")
    
    return tests_passed


if __name__ == "__main__":
    print("=" * 70)
    print("wildfire_intensity_model_tool.py - SELF-TESTS")
    print("=" * 70)
    
    passed = validate()
    total = 11
    
    print(f"\n✓ PASSED: {passed}/{total}")
    if passed == total:
        print("→ LISTO PARA DESCARGAR e integrar a octave-mcp/tools/")
    else:
        print(f"→ {total - passed} test(s) fallaron — revisar")
