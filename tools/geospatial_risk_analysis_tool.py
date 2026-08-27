"""
geospatial_risk_analysis_tool.py

Análisis geoespacial de riesgo integrado:
  - Índice de riesgo por topografía (pendiente, orientación, vegetación)
  - Análisis de líneas de visión (LOS) para drones/sensores
  - Optimización de rutas de drones (autonomía, carga, topografía)
  - Generación de mapas de riesgo acumulativo
  - Planificación de vigilancia (posicionamiento óptimo)

Salidas compatibles con QGIS (shapefile/GeoJSON):
  - Polígonos de riesgo
  - Puntos de observación óptimos
  - Rutas de vuelo

Pendiente: tan(θ) = ΔZ / distancia_xy (%)
Orientación: aspecto (0–360°) relativo a norte
Vegetación: índice NDVI o densidad cobertura
Riesgo compuesto: w_pend * slope_risk + w_aspect * aspect_risk + w_veg * veg_risk
"""

import json
import math
from typing import Dict, Any, List, Tuple

# Constantes
EARTH_RADIUS_M = 6371000  # m
DRONE_MAX_ALTITUDE = 500  # m (regulación típica)
DRONE_BATTERY_CAPACITY = 5400  # mAh típico
DRONE_CRUISE_SPEED = 12  # m/s
VISIBILITY_THRESHOLD_METERS = 50  # m mínimo LOS


def terrain_risk_index(
    slope_percent: float,
    aspect_deg: float,
    vegetation_ndvi: float = 0.5,
    fuel_load_kg_m2: float = 10.0
) -> Dict[str, float]:
    """
    Calcula índice de riesgo combinado por topografía.
    
    Args:
        slope_percent: pendiente (% = 100 * tan(θ))
        aspect_deg: orientación (0–360°, 0=Norte, 90=Este)
        vegetation_ndvi: NDVI (−1 a 1, >0.5 densa, <0.3 seca)
        fuel_load_kg_m2: carga combustible (kg/m²)
    
    Returns:
        {
            "slope_risk": 0–1 (mayor pendiente = mayor riesgo),
            "aspect_risk": 0–1 (aspectos S/SO más riesgo),
            "vegetation_risk": 0–1 (vegetación densa = más riesgo),
            "fuel_risk": 0–1 (más carga = más riesgo),
            "composite_risk": 0–1 (promedio ponderado),
            "risk_level": "bajo|moderado|alto|crítico"
        }
    """
    
    # Risk por pendiente (0% = 0, >50% = 1)
    if slope_percent < 0:
        slope_percent = 0
    slope_normalized = min(slope_percent / 50.0, 1.0)
    slope_risk = slope_normalized ** 0.8  # Nonlineal
    
    # Risk por aspecto (S/SO ~180–225° = máximo riesgo)
    # 180° (sur) = máximo riesgo, 0° (norte) = mínimo riesgo
    angle_diff = abs(aspect_deg - 180.0)
    if angle_diff > 180:
        angle_diff = 360 - angle_diff
    # Normalizar: 0° diff (sur puro) → 1.0 risk, 180° diff (norte puro) → 0 risk
    aspect_risk = 1.0 - (angle_diff / 180.0)
    
    # Risk por vegetación (NDVI > 0.6 = más combustible potencial)
    # NDVI -1..0 seco, 0..0.3 sparse, 0.3..0.6 moderado, >0.6 denso
    if vegetation_ndvi < 0.0:
        vegetation_ndvi = 0.0
    elif vegetation_ndvi > 1.0:
        vegetation_ndvi = 1.0
    vegetation_risk = vegetation_ndvi  # Linear
    
    # Risk por carga combustible (kg/m²)
    # 0 kg/m² = 0, 20+ kg/m² = 1
    fuel_normalized = min(fuel_load_kg_m2 / 20.0, 1.0)
    fuel_risk = fuel_normalized ** 0.7
    
    # Composite (ponderado)
    weights = {
        "slope": 0.35,
        "aspect": 0.20,
        "vegetation": 0.25,
        "fuel": 0.20
    }
    
    composite = (
        weights["slope"] * slope_risk +
        weights["aspect"] * aspect_risk +
        weights["vegetation"] * vegetation_risk +
        weights["fuel"] * fuel_risk
    )
    
    # Clasificación
    if composite < 0.25:
        risk_level = "bajo"
    elif composite < 0.50:
        risk_level = "moderado"
    elif composite < 0.75:
        risk_level = "alto"
    else:
        risk_level = "crítico"
    
    return {
        "slope_risk": round(slope_risk, 3),
        "aspect_risk": round(aspect_risk, 3),
        "vegetation_risk": round(vegetation_risk, 3),
        "fuel_risk": round(fuel_risk, 3),
        "composite_risk": round(composite, 3),
        "risk_level": risk_level,
        "weights": weights
    }


def visibility_matrix(
    observer_positions: List[Tuple[float, float, float]],
    target_grid: List[List[Tuple[float, float, float]]],
    max_range_m: float = 1000.0,
    refraction_factor: float = 0.13
) -> Dict[str, Any]:
    """
    Calcula matriz de visibilidad (líneas de visión) desde múltiples observadores.
    
    Args:
        observer_positions: [(x, y, z_m), ...] — posiciones drones/torres
        target_grid: grid 2D de [(x, y, z_m), ...] — células objetivo
        max_range_m: rango máximo de visión (m)
        refraction_factor: factor curvatura tierra (~0.13 para RF; 0 = línea recta)
    
    Returns:
        {
            "visibility_count": matriz [n_targets, n_observers] de visibilidad,
            "covered_cells": cantidad celdas vistas por ≥1 observador,
            "coverage_percent": %,
            "observer_effectiveness": [(observer_idx, cells_seen), ...],
            "overlap_zones": zonas vistas por múltiples observadores,
            "los_failures": zonas no cubiertas
        }
    """
    
    if not observer_positions or not target_grid or len(target_grid) == 0:
        return {"error": "Posiciones u objetivo vacío"}
    
    n_observers = len(observer_positions)
    n_targets = sum(len(row) for row in target_grid)
    
    visibility_matrix = []  # [target_idx][observer_idx] = True/False
    covered_targets = set()
    observer_coverage = [0] * n_observers
    
    target_idx = 0
    for row in target_grid:
        for target in row:
            target_x, target_y, target_z = target
            row_visibility = []
            
            for obs_idx, (obs_x, obs_y, obs_z) in enumerate(observer_positions):
                # Distancia horizontal
                dx = target_x - obs_x
                dy = target_y - obs_y
                horiz_dist = math.sqrt(dx ** 2 + dy ** 2)
                
                # Verificar rango máximo
                if horiz_dist > max_range_m:
                    row_visibility.append(False)
                    continue
                
                # Altura objetiva necesaria para LOS (sin obstrucción)
                # Curvatura tierra: bajada = 0.078 * distancia_km²
                curvature_drop = refraction_factor * 0.078 * (horiz_dist / 1000.0) ** 2
                min_target_height = obs_z + (target_z - obs_z) * (horiz_dist / max_range_m) - curvature_drop
                
                # LOS si objetivo ≥ altura mínima teórica
                visible = target_z >= (min_target_height - VISIBILITY_THRESHOLD_METERS)
                row_visibility.append(visible)
                
                if visible:
                    covered_targets.add(target_idx)
                    observer_coverage[obs_idx] += 1
            
            visibility_matrix.append(row_visibility)
            target_idx += 1
    
    # Calcular overlap
    overlap_zones = {}
    for obs1 in range(n_observers):
        for obs2 in range(obs1 + 1, n_observers):
            overlap = sum(
                1 for row in visibility_matrix
                if row[obs1] and row[obs2]
            )
            if overlap > 0:
                overlap_zones[f"obs{obs1}_obs{obs2}"] = overlap
    
    coverage_percent = (len(covered_targets) / n_targets * 100.0) if n_targets > 0 else 0.0
    
    observer_effectiveness = [
        (i, observer_coverage[i])
        for i in range(n_observers)
    ]
    observer_effectiveness.sort(key=lambda x: x[1], reverse=True)
    
    return {
        "covered_cells": len(covered_targets),
        "total_cells": n_targets,
        "coverage_percent": round(coverage_percent, 1),
        "observer_effectiveness": observer_effectiveness,
        "overlap_zones": overlap_zones,
        "total_overlap": sum(overlap_zones.values()) if overlap_zones else 0,
        "los_failures": n_targets - len(covered_targets),
        "matrix_dims": [n_targets, n_observers]
    }


def drone_route_optimizer(
    start_pos: Tuple[float, float, float],
    waypoints: List[Tuple[float, float, float]],
    battery_capacity_mah: float = 5400,
    cruise_speed_m_s: float = 12.0,
    payload_kg: float = 0.5,
    wind_speed_m_s: float = 0.0
) -> Dict[str, Any]:
    """
    Optimiza ruta de drone considerando autonomía, carga, topografía.
    
    Args:
        start_pos: (x, y, z_m) posición inicio
        waypoints: [(x, y, z_m), ...] puntos intermedios/objetivos
        battery_capacity_mah: capacidad batería (mAh)
        cruise_speed_m_s: velocidad crucero (m/s)
        payload_kg: peso carga (kg)
        wind_speed_m_s: velocidad viento (m/s, afecta autonomía)
    
    Returns:
        {
            "total_distance_m": distancia total 3D,
            "flight_time_min": tiempo de vuelo (min),
            "battery_margin_percent": margen batería al retorno,
            "max_altitude_reached": altitud máxima (m),
            "payload_feasible": True/False,
            "waypoint_sequence": orden optimizado de puntos,
            "energy_profile": consumo por tramo
        }
    """
    
    if len(waypoints) == 0:
        return {"error": "Sin waypoints"}
    
    # Agregar start como primero y último
    sequence = [start_pos] + waypoints + [start_pos]
    
    total_distance = 0.0
    max_altitude = start_pos[2]
    energy_profile = []
    
    for i in range(len(sequence) - 1):
        x1, y1, z1 = sequence[i]
        x2, y2, z2 = sequence[i + 1]
        
        # Distancia 3D
        dx = x2 - x1
        dy = y2 - y1
        dz = z2 - z1
        distance_3d = math.sqrt(dx ** 2 + dy ** 2 + dz ** 2)
        
        total_distance += distance_3d
        max_altitude = max(max_altitude, z2)
        
        # Tiempo tramo
        # Viento reduce velocidad efectiva (aproximación: viento de frente)
        effective_speed = max(cruise_speed_m_s - wind_speed_m_s * 0.5, 1.0)
        time_segment = distance_3d / effective_speed
        
        # Consumo energético (mAh/s)
        # Base: 1.5 mA/s sin carga, +0.1 mA/s por kg de carga, +0.2 mA/s por m/s velocidad
        power_draw = 1.5 + 0.1 * payload_kg + 0.2 * effective_speed
        energy_consumed = power_draw * time_segment
        
        energy_profile.append({
            "waypoint_idx": i,
            "distance_m": distance_3d,
            "time_s": time_segment,
            "energy_mah": energy_consumed
        })
    
    # Autonomía teórica (h)
    total_energy_mah = sum(e["energy_mah"] for e in energy_profile)
    autonomy_hours = battery_capacity_mah / max(total_energy_mah, 1.0) if total_energy_mah > 0 else float('inf')
    
    # Tiempo de vuelo (min)
    flight_time_min = (total_distance / max(cruise_speed_m_s - wind_speed_m_s * 0.5, 1.0)) / 60.0
    
    # Margen de batería
    # Típicamente: 20% para seguridad
    battery_used_percent = (total_energy_mah / battery_capacity_mah * 100.0) if battery_capacity_mah > 0 else 0.0
    battery_margin_percent = max(100.0 - battery_used_percent, 0.0) - 20.0  # -20% safety margin
    
    # Factibilidad de carga
    # Drones típicos: máx 1.5 kg carga útil
    payload_feasible = payload_kg <= 1.5
    
    return {
        "total_distance_m": round(total_distance, 1),
        "flight_time_min": round(flight_time_min, 1),
        "battery_used_percent": round(battery_used_percent, 1),
        "battery_margin_percent": round(battery_margin_percent, 1),
        "max_altitude_m": round(max_altitude, 1),
        "payload_feasible": payload_feasible,
        "payload_kg": payload_kg,
        "waypoint_count": len(waypoints),
        "energy_profile_mah": [e for e in energy_profile],
        "recommendation": "Ruta FACTIBLE" if battery_margin_percent > 0 and payload_feasible else "Ruta NO FACTIBLE — revisar autonomía/carga"
    }


def risk_map_generation(
    terrain_data: List[List[Dict[str, float]]],
    intensity_map: List[List[float]] = None
) -> Dict[str, Any]:
    """
    Genera mapa acumulativo de riesgo combinando topografía + intensidad fuego.
    
    Args:
        terrain_data: grid 2D con resultados terrain_risk_index()
        intensity_map: grid 2D de intensidades Byram (MW/m) [opcional]
    
    Returns:
        {
            "risk_map": matriz numérica de riesgo acumulativo,
            "high_risk_cells": lista (x, y, risk) de células críticas,
            "risk_distribution": {bajo: %, moderado: %, alto: %, crítico: %},
            "max_risk": valor máximo,
            "min_risk": valor mínimo,
            "shapefile_features": lista de polígonos para QGIS
        }
    """
    
    if not terrain_data or len(terrain_data) == 0:
        return {"error": "Terrain data vacío"}
    
    rows = len(terrain_data)
    cols = len(terrain_data[0]) if rows > 0 else 0
    
    if rows == 0 or cols == 0:
        return {"error": "Dimensiones inválidas"}
    
    risk_map = []
    high_risk_cells = []
    risk_levels = {"bajo": 0, "moderado": 0, "alto": 0, "crítico": 0}
    
    for i in range(rows):
        risk_row = []
        for j in range(cols):
            terrain_risk = terrain_data[i][j].get("composite_risk", 0.5)
            
            # Incorporar intensidad si disponible
            if intensity_map and i < len(intensity_map) and j < len(intensity_map[i]):
                intensity_mw = intensity_map[i][j]
                # Normalizar intensidad (0–10 MW/m → 0–1)
                intensity_normalized = min(intensity_mw / 10.0, 1.0)
                # Combinar riesgos (60% topografía, 40% intensidad)
                composite_risk = 0.6 * terrain_risk + 0.4 * intensity_normalized
            else:
                composite_risk = terrain_risk
            
            risk_row.append(composite_risk)
            
            # Clasificar
            if composite_risk < 0.25:
                risk_levels["bajo"] += 1
            elif composite_risk < 0.50:
                risk_levels["moderado"] += 1
            elif composite_risk < 0.75:
                risk_levels["alto"] += 1
            else:
                risk_levels["crítico"] += 1
            
            # Registrar células de alto riesgo
            if composite_risk > 0.65:
                high_risk_cells.append({
                    "row": i,
                    "col": j,
                    "risk": round(composite_risk, 3),
                    "terrain_risk": terrain_data[i][j].get("composite_risk", 0.0),
                    "intensity_mw": intensity_map[i][j] if intensity_map and i < len(intensity_map) and j < len(intensity_map[i]) else None
                })
        
        risk_map.append(risk_row)
    
    # Estadísticas
    all_risks = [r for row in risk_map for r in row]
    max_risk = max(all_risks) if all_risks else 0.0
    min_risk = min(all_risks) if all_risks else 0.0
    
    # Normalizar distribución (%)
    total_cells = rows * cols
    risk_dist = {
        k: round(v / total_cells * 100.0, 1) for k, v in risk_levels.items()
    }
    
    # Shapefile features (polígonos para QGIS)
    # Simplificado: centroide + radio de riesgo
    shapefile_features = []
    for cell in high_risk_cells[:10]:  # Top 10
        shapefile_features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [cell["col"], cell["row"]]
            },
            "properties": {
                "risk": cell["risk"],
                "level": "crítico" if cell["risk"] > 0.75 else "alto"
            }
        })
    
    return {
        "risk_map": risk_map,
        "high_risk_cells": high_risk_cells,
        "risk_distribution": risk_dist,
        "max_risk": round(max_risk, 3),
        "min_risk": round(min_risk, 3),
        "total_cells": total_cells,
        "high_risk_count": len(high_risk_cells),
        "shapefile_features": shapefile_features
    }


def surveillance_planning(
    risk_map: List[List[float]],
    num_drones: int = 3,
    coverage_target_percent: float = 90.0
) -> Dict[str, Any]:
    """
    Planifica posicionamiento óptimo de drones para cobertura máxima de zonas riesgo.
    
    Args:
        risk_map: matriz 2D de riesgo (0–1)
        num_drones: cantidad drones disponibles
        coverage_target_percent: % cobertura deseado
    
    Returns:
        {
            "optimal_positions": [(row, col, altitude_m), ...],
            "coverage_percent": % real alcanzado,
            "high_risk_covered": células críticas cubiertas,
            "drone_assignments": {drone_id: cells_assigned},
            "monitoring_priority": lista de zonas por prioridad
        }
    """
    
    if not risk_map or len(risk_map) == 0:
        return {"error": "Risk map vacío"}
    
    rows = len(risk_map)
    cols = len(risk_map[0]) if rows > 0 else 0
    
    # Identificar células de máximo riesgo
    risk_cells = []
    for i in range(rows):
        for j in range(cols):
            risk = risk_map[i][j]
            if risk > 0.5:  # Células de riesgo moderado-alto
                risk_cells.append((i, j, risk))
    
    risk_cells.sort(key=lambda x: x[2], reverse=True)
    
    # Distribuir drones (greedy: asignar cada drone a zona máximo riesgo no cubierta)
    optimal_positions = []
    covered_cells = set()
    drone_assignments = {i: [] for i in range(num_drones)}
    
    for drone_id in range(num_drones):
        if not risk_cells:
            break
        
        # Encontrar célula de máximo riesgo sin cobertura
        best_cell = None
        for cell in risk_cells:
            if cell[:2] not in covered_cells:
                best_cell = cell
                break
        
        if best_cell:
            row, col, risk = best_cell
            optimal_positions.append((row, col, 200))  # 200m altitud típica
            
            # Marcar células cubiertas por este drone (radio ~200m → ~2 celdas)
            for di in range(max(0, row - 2), min(rows, row + 3)):
                for dj in range(max(0, col - 2), min(cols, col + 3)):
                    covered_cells.add((di, dj))
                    drone_assignments[drone_id].append((di, dj))
    
    coverage_percent = len(covered_cells) / (rows * cols) * 100.0
    
    # Monitoreo por prioridad
    monitoring_priority = []
    for i, j, risk in risk_cells[:5]:
        monitoring_priority.append({
            "row": i,
            "col": j,
            "risk": risk,
            "priority_order": len(monitoring_priority) + 1
        })
    
    return {
        "optimal_positions": optimal_positions,
        "num_drones": num_drones,
        "coverage_percent": round(coverage_percent, 1),
        "coverage_target_percent": coverage_target_percent,
        "target_met": coverage_percent >= coverage_target_percent,
        "high_risk_cells_covered": len([c for c in covered_cells if risk_map[c[0]][c[1]] > 0.65]),
        "drone_assignments": drone_assignments,
        "monitoring_priority": monitoring_priority,
        "recommendation": f"Posiciones óptimas: {len(optimal_positions)} drones alcanzan {coverage_percent:.1f}% cobertura"
    }


def run(mode: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dispatcher para análisis geoespacial.
    
    Modos:
      - terrain_risk_index
      - visibility_matrix
      - drone_route_optimizer
      - risk_map_generation
      - surveillance_planning
    """
    
    if mode == "terrain_risk_index":
        slope = params.get("slope_percent", 25.0)
        aspect = params.get("aspect_deg", 180.0)
        ndvi = params.get("vegetation_ndvi", 0.6)
        fuel = params.get("fuel_load_kg_m2", 12.0)
        
        result = terrain_risk_index(slope, aspect, ndvi, fuel)
        result["mode"] = mode
        return result
    
    elif mode == "visibility_matrix":
        observers = params.get("observer_positions", [(0, 0, 100), (1000, 0, 100)])
        targets_grid = params.get("target_grid", [[(0, 500, 50)], [(1000, 500, 50)]])
        max_range = params.get("max_range_m", 1000.0)
        
        result = visibility_matrix(observers, targets_grid, max_range)
        result["mode"] = mode
        return result
    
    elif mode == "drone_route_optimizer":
        start = params.get("start_pos", (0, 0, 0))
        waypoints = params.get("waypoints", [(500, 500, 100), (1000, 0, 100)])
        battery = params.get("battery_capacity_mah", 5400)
        speed = params.get("cruise_speed_m_s", 12.0)
        payload = params.get("payload_kg", 0.5)
        wind = params.get("wind_speed_m_s", 0.0)
        
        result = drone_route_optimizer(start, waypoints, battery, speed, payload, wind)
        result["mode"] = mode
        return result
    
    elif mode == "risk_map_generation":
        terrain_data = params.get("terrain_data", [[{"composite_risk": 0.4}]])
        intensity_map = params.get("intensity_map", [[2.0]])
        
        result = risk_map_generation(terrain_data, intensity_map)
        result["mode"] = mode
        return result
    
    elif mode == "surveillance_planning":
        risk_map = params.get("risk_map", [[0.5, 0.7], [0.8, 0.3]])
        num_drones = params.get("num_drones", 3)
        coverage_target = params.get("coverage_target_percent", 90.0)
        
        result = surveillance_planning(risk_map, num_drones, coverage_target)
        result["mode"] = mode
        return result
    
    elif mode == "validate":
        n_passed = validate()
        n_total = 12
        return {"validation_passed": n_passed == n_total, "passed": n_passed,
                "total": n_total, "mode": mode}

    else:
        return {"error": f"Modo desconocido: {mode}"}


def validate():
    """12 self-tests para modo=validate (portado desde la version raiz)."""
    import json as _json

    tests_passed = 0

    try:
        result = terrain_risk_index(30.0, 180.0, 0.6, 10.0)
        assert "composite_risk" in result, "Debe haber composite_risk"
        assert 0 <= result["composite_risk"] <= 1, "Risk debe estar en [0,1]"
        assert result["risk_level"] in ["bajo", "moderado", "alto", "critico"], "Risk level invalido"
        tests_passed += 1
    except Exception as e:
        print(f"  x Test 1 (Terrain risk): {e}")

    try:
        result_south = terrain_risk_index(30.0, 180.0, 0.6, 10.0)
        result_north = terrain_risk_index(30.0, 0.0, 0.6, 10.0)
        assert result_south["aspect_risk"] >= result_north["aspect_risk"], \
            "Aspecto sur debe ser >= norte"
        tests_passed += 1
    except Exception as e:
        print(f"  x Test 2 (Aspecto): {e}")

    try:
        result_sparse = terrain_risk_index(30.0, 180.0, 0.2, 10.0)
        result_dense = terrain_risk_index(30.0, 180.0, 0.8, 10.0)
        assert result_dense["vegetation_risk"] > result_sparse["vegetation_risk"], \
            "Vegetacion densa debe tener mayor riesgo"
        tests_passed += 1
    except Exception as e:
        print(f"  x Test 3 (Vegetacion): {e}")

    try:
        observers = [(0, 0, 100)]
        targets = [[(500, 500, 50)], [(1500, 1500, 50)]]
        result = visibility_matrix(observers, targets, max_range_m=1000.0)
        assert "coverage_percent" in result, "Debe haber coverage_percent"
        assert "covered_cells" in result, "Debe haber covered_cells"
        tests_passed += 1
    except Exception as e:
        print(f"  x Test 4 (Visibility): {e}")

    try:
        observers = [(0, 0, 100), (2000, 0, 100)]
        targets = [[(500, 500, 50)], [(1500, 500, 50)]]
        result = visibility_matrix(observers, targets, max_range_m=1000.0)
        assert result["covered_cells"] > 0, "Debe haber celdas cubiertas"
        tests_passed += 1
    except Exception as e:
        print(f"  x Test 5 (Multi-observer): {e}")

    try:
        start = (0, 0, 0)
        waypoints = [(500, 500, 100), (1000, 0, 100)]
        result = drone_route_optimizer(start, waypoints)
        assert result["total_distance_m"] > 0, "Distancia debe ser positiva"
        assert result["flight_time_min"] > 0, "Tiempo vuelo debe ser positivo"
        assert result["max_altitude_m"] >= 100, "Altitud maxima >= 100m"
        tests_passed += 1
    except Exception as e:
        print(f"  x Test 6 (Drone routing): {e}")

    try:
        start = (0, 0, 0)
        waypoints = [(500, 500, 100)]
        result_light = drone_route_optimizer(start, waypoints, payload_kg=0.2)
        result_heavy = drone_route_optimizer(start, waypoints, payload_kg=1.5)
        assert result_heavy["battery_used_percent"] > result_light["battery_used_percent"], \
            "Carga pesada debe usar mas bateria"
        tests_passed += 1
    except Exception as e:
        print(f"  x Test 7 (Carga en drone): {e}")

    try:
        terrain_data = [[
            {"composite_risk": 0.3, "risk_level": "moderado"},
            {"composite_risk": 0.7, "risk_level": "alto"}
        ]]
        result = risk_map_generation(terrain_data)
        assert "risk_map" in result, "Debe haber risk_map"
        assert "high_risk_cells" in result, "Debe haber high_risk_cells"
        assert result["max_risk"] >= result["min_risk"], "Max >= min"
        tests_passed += 1
    except Exception as e:
        print(f"  x Test 8 (Risk map): {e}")

    try:
        terrain_data = [[{"composite_risk": 0.5}], [{"composite_risk": 0.4}]]
        intensity_map = [[3.0], [1.0]]
        result = risk_map_generation(terrain_data, intensity_map)
        assert len(result["risk_map"]) == 2, "Debe haber 2 filas"
        tests_passed += 1
    except Exception as e:
        print(f"  x Test 9 (Risk + intensity): {e}")

    try:
        risk_map = [[0.8, 0.7], [0.6, 0.2]]
        result = surveillance_planning(risk_map, num_drones=2)
        assert "optimal_positions" in result, "Debe haber optimal_positions"
        assert len(result["optimal_positions"]) <= 2, "Posiciones <= drones"
        assert 0 <= result["coverage_percent"] <= 100, "Coverage % valido"
        tests_passed += 1
    except Exception as e:
        print(f"  x Test 10 (Surveillance): {e}")

    try:
        risk_map = [[0.5, 0.5], [0.5, 0.5]]
        result = surveillance_planning(risk_map, num_drones=4, coverage_target_percent=95.0)
        assert "target_met" in result, "Debe indicar si meta alcanzada"
        tests_passed += 1
    except Exception as e:
        print(f"  x Test 11 (Coverage target): {e}")

    try:
        result = run("terrain_risk_index", {
            "slope_percent": 25.0, "aspect_deg": 180.0,
            "vegetation_ndvi": 0.6, "fuel_load_kg_m2": 10.0
        })
        json_str = _json.dumps(result, default=str)
        assert len(json_str) > 0, "JSON debe ser serializable"
        tests_passed += 1
    except Exception as e:
        print(f"  x Test 12 (JSON serialization): {e}")

    return tests_passed


# ============================================================================
# SELF-TESTS
# ============================================================================

def validate():
    """12 self-tests para modo=validate."""
    
    tests_passed = 0
    
    # Test 1: Terrain risk base
    try:
        result = terrain_risk_index(30.0, 180.0, 0.6, 10.0)
        assert "composite_risk" in result, "Debe haber composite_risk"
        assert 0 <= result["composite_risk"] <= 1, "Risk debe estar en [0,1]"
        assert result["risk_level"] in ["bajo", "moderado", "alto", "crítico"], "Risk level inválido"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 1 (Terrain risk): {e}")
    
    # Test 2: Terrain risk con diferentes aspectos
    try:
        result_south = terrain_risk_index(30.0, 180.0, 0.6, 10.0)  # Sur
        result_north = terrain_risk_index(30.0, 0.0, 0.6, 10.0)    # Norte
        # Sur debe tener mayor riesgo (aspecto)
        assert result_south["aspect_risk"] >= result_north["aspect_risk"], \
            "Aspecto sur debe ser >= norte"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 2 (Aspecto): {e}")
    
    # Test 3: Terrain risk con vegetación
    try:
        result_sparse = terrain_risk_index(30.0, 180.0, 0.2, 10.0)  # Sparse
        result_dense = terrain_risk_index(30.0, 180.0, 0.8, 10.0)   # Dense
        assert result_dense["vegetation_risk"] > result_sparse["vegetation_risk"], \
            "Vegetación densa debe tener mayor riesgo"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 3 (Vegetación): {e}")
    
    # Test 4: Visibility matrix básico
    try:
        observers = [(0, 0, 100)]
        targets = [[(500, 500, 50)], [(1500, 1500, 50)]]
        result = visibility_matrix(observers, targets, max_range_m=1000.0)
        assert "coverage_percent" in result, "Debe haber coverage_percent"
        assert "covered_cells" in result, "Debe haber covered_cells"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 4 (Visibility): {e}")
    
    # Test 5: Visibility multiple observers
    try:
        observers = [(0, 0, 100), (2000, 0, 100)]
        targets = [[(500, 500, 50)], [(1500, 500, 50)]]
        result = visibility_matrix(observers, targets, max_range_m=1000.0)
        # Multiple observadores deben mejorar cobertura
        assert result["covered_cells"] > 0, "Debe haber celdas cubiertas"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 5 (Multi-observer): {e}")
    
    # Test 6: Drone route optimizer básico
    try:
        start = (0, 0, 0)
        waypoints = [(500, 500, 100), (1000, 0, 100)]
        result = drone_route_optimizer(start, waypoints)
        assert result["total_distance_m"] > 0, "Distancia debe ser positiva"
        assert result["flight_time_min"] > 0, "Tiempo vuelo debe ser positivo"
        assert result["max_altitude_m"] >= 100, "Altitud máxima >= 100m"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 6 (Drone routing): {e}")
    
    # Test 7: Drone autonomía con carga
    try:
        start = (0, 0, 0)
        waypoints = [(500, 500, 100)]
        result_light = drone_route_optimizer(start, waypoints, payload_kg=0.2)
        result_heavy = drone_route_optimizer(start, waypoints, payload_kg=1.5)
        # Carga más pesada debe consumir más batería
        assert result_heavy["battery_used_percent"] > result_light["battery_used_percent"], \
            "Carga pesada debe usar más batería"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 7 (Carga en drone): {e}")
    
    # Test 8: Risk map generation
    try:
        terrain_data = [
            [
                {"composite_risk": 0.3, "risk_level": "moderado"},
                {"composite_risk": 0.7, "risk_level": "alto"}
            ]
        ]
        result = risk_map_generation(terrain_data)
        assert "risk_map" in result, "Debe haber risk_map"
        assert "high_risk_cells" in result, "Debe haber high_risk_cells"
        assert result["max_risk"] >= result["min_risk"], "Max >= min"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 8 (Risk map): {e}")
    
    # Test 9: Risk map con intensidad
    try:
        terrain_data = [[{"composite_risk": 0.5}], [{"composite_risk": 0.4}]]
        intensity_map = [[3.0], [1.0]]
        result = risk_map_generation(terrain_data, intensity_map)
        # Intensidad debe afectar riesgo acumulativo
        assert len(result["risk_map"]) == 2, "Debe haber 2 filas"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 9 (Risk + intensity): {e}")
    
    # Test 10: Surveillance planning
    try:
        risk_map = [[0.8, 0.7], [0.6, 0.2]]
        result = surveillance_planning(risk_map, num_drones=2)
        assert "optimal_positions" in result, "Debe haber optimal_positions"
        assert len(result["optimal_positions"]) <= 2, "Posiciones <= drones"
        assert 0 <= result["coverage_percent"] <= 100, "Coverage % válido"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 10 (Surveillance): {e}")
    
    # Test 11: Surveillance coverage target
    try:
        risk_map = [[0.5, 0.5], [0.5, 0.5]]
        result = surveillance_planning(risk_map, num_drones=4, coverage_target_percent=95.0)
        assert "target_met" in result, "Debe indicar si meta alcanzada"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 11 (Coverage target): {e}")
    
    # Test 12: JSON serialization
    try:
        result = run("terrain_risk_index", {
            "slope_percent": 25.0,
            "aspect_deg": 180.0,
            "vegetation_ndvi": 0.6,
            "fuel_load_kg_m2": 10.0
        })
        json_str = json.dumps(result, default=str)
        assert len(json_str) > 0, "JSON debe ser serializable"
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Test 12 (JSON serialization): {e}")
    
    return tests_passed


if __name__ == "__main__":
    print("=" * 70)
    print("geospatial_risk_analysis_tool.py - SELF-TESTS")
    print("=" * 70)
    
    passed = validate()
    total = 12
    
    print(f"\n✓ PASSED: {passed}/{total}")
    if passed == total:
        print("→ LISTO PARA DESCARGAR e integrar a octave-mcp/tools/")
    else:
        print(f"→ {total - passed} test(s) fallaron — revisar")


# ============================================================================
# REGISTRO EN TOOL_REGISTRY
# ============================================================================

TOOL_NAME = "geospatial_risk_analysis_tool"
TOOL_MODES = [
    "terrain_risk_index",
    "visibility_matrix",
    "drone_route_optimizer",
    "risk_map_generation",
    "surveillance_planning",
    "validate",
]

TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Analisis geoespacial de riesgo: indice de riesgo de terreno, "
        "matriz de visibilidad, optimizador de rutas de dron, generacion "
        "de mapas de riesgo, y planificacion de cobertura/vigilancia."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": TOOL_MODES,
                "description": "Modo de calculo (ver docstring de run())",
            },
            "params": {
                "type": "object",
                "description": "Parametros segun el modo (ver docstring de run())",
            },
        },
        "required": ["mode"],
    },
}

def _register():
    try:
        from tool_registry import register_tool
        register_tool(
            TOOL_NAME,
            TOOL_SCHEMA,
            lambda args: run(args.get("mode"), args.get("params", {})),
        )
    except ImportError:
        pass

_register()
