"""
wildfire_tool.py

Modelo agregado de riesgo y propagación de incendios forestales.

Versión determinista liviana de un autómata celular 2D: en vez de reglas
estocásticas (probabilidad de ignición por celda), usa un umbral de
transferencia de calor acumulado. Esto la hace 100% reproducible y fácil
de validar (misma entrada -> misma salida, siempre), sin dependencias
externas (solo stdlib).

Convención del módulo:
    wildfire_tool(params: dict) -> dict

Estados de celda:
    0 = no quemado
    1 = en llamas
    2 = quemado (combustible consumido, ya no propaga ni arde)
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional
import math


@dataclass
class WildfireParams:
    grid_width: int = 20
    grid_height: int = 20
    # Carga de combustible por celda (kg/m2). Si es None, grid homogéneo.
    fuel_load: Optional[List[List[float]]] = None
    default_fuel_load: float = 1.0
    # Humedad de combustible por celda (fracción 0-1). Si es None, homogénea.
    moisture: Optional[List[List[float]]] = None
    default_moisture: float = 0.2
    wind_direction_deg: float = 0.0   # 0 = viento soplando hacia +x (este)
    wind_speed: float = 5.0           # m/s
    ignition_points: Optional[List[Tuple[int, int]]] = None
    timesteps: int = 20
    base_spread_rate: float = 0.6     # tasa base de transferencia de calor
    ignition_threshold: float = 0.35  # umbral determinista de ignición
    burn_duration: int = 2            # pasos que una celda permanece en llamas


def _build_grid(value: Optional[List[List[float]]], default: float,
                 w: int, h: int) -> List[List[float]]:
    if value is not None:
        return value
    return [[default for _ in range(w)] for _ in range(h)]


def _wind_factor(dx: int, dy: int, wind_dir_deg: float, wind_speed: float) -> float:
    """Factor multiplicativo de propagación según alineación con el viento.
    dx, dy: dirección desde la celda en llamas hacia la celda vecina candidata.
    """
    if dx == 0 and dy == 0:
        return 1.0
    neighbor_angle = math.degrees(math.atan2(dy, dx)) % 360
    wind_angle = wind_dir_deg % 360
    diff = math.radians(neighbor_angle - wind_angle)
    # cos(diff): 1.0 si la celda está exactamente a favor del viento,
    # -1.0 si está exactamente en contra.
    alignment = math.cos(diff)
    factor = 1.0 + (wind_speed / 10.0) * alignment
    return max(0.05, factor)  # nunca negativo ni cero absoluto


NEIGHBORS_8 = [(-1, -1), (-1, 0), (-1, 1),
               (0, -1),           (0, 1),
               (1, -1),  (1, 0),  (1, 1)]


def wildfire_tool(params: dict) -> dict:
    p = WildfireParams(**params) if not isinstance(params, WildfireParams) else params

    w, h = p.grid_width, p.grid_height
    fuel = _build_grid(p.fuel_load, p.default_fuel_load, w, h)
    moisture = _build_grid(p.moisture, p.default_moisture, w, h)

    state = [[0 for _ in range(w)] for _ in range(h)]
    burn_clock = [[0 for _ in range(w)] for _ in range(h)]

    ignition_points = p.ignition_points or [(h // 2, w // 2)]
    for (r, c) in ignition_points:
        if 0 <= r < h and 0 <= c < w:
            state[r][c] = 1
            burn_clock[r][c] = p.burn_duration

    history_burned_fraction = []
    total_cells = w * h

    for t in range(p.timesteps):
        new_state = [row[:] for row in state]
        new_burn_clock = [row[:] for row in burn_clock]

        # 1. Propagación: cada celda no quemada recibe calor acumulado
        #    de vecinos en llamas.
        for i in range(h):
            for j in range(w):
                if state[i][j] != 0:
                    continue
                heat = 0.0
                for (di, dj) in NEIGHBORS_8:
                    ni, nj = i + di, j + dj
                    if 0 <= ni < h and 0 <= nj < w and state[ni][nj] == 1:
                        wf = _wind_factor(dj, di, p.wind_direction_deg, p.wind_speed)
                        heat += (p.base_spread_rate * fuel[i][j]
                                 * (1.0 - moisture[i][j]) * wf)
                effective_threshold = p.ignition_threshold * (1.0 + moisture[i][j])
                if heat >= effective_threshold:
                    new_state[i][j] = 1
                    new_burn_clock[i][j] = p.burn_duration

        # 2. Consumo: celdas en llamas avanzan su reloj de combustión.
        for i in range(h):
            for j in range(w):
                if state[i][j] == 1:
                    new_burn_clock[i][j] -= 1
                    if new_burn_clock[i][j] <= 0:
                        new_state[i][j] = 2  # quemado, ya no arde

        state = new_state
        burn_clock = new_burn_clock

        burned_or_burning = sum(1 for i in range(h) for j in range(w) if state[i][j] != 0)
        history_burned_fraction.append(round(burned_or_burning / total_cells, 4))

    final_burned = sum(1 for row in state for v in row if v == 2)
    final_burning = sum(1 for row in state for v in row if v == 1)

    return {
        "grid_size": [h, w],
        "timesteps_run": p.timesteps,
        "final_state": state,
        "final_burned_cells": final_burned,
        "final_burning_cells": final_burning,
        "final_burned_fraction": round((final_burned + final_burning) / total_cells, 4),
        "burned_fraction_timeseries": history_burned_fraction,
        "params_used": {
            "wind_direction_deg": p.wind_direction_deg,
            "wind_speed": p.wind_speed,
            "ignition_threshold": p.ignition_threshold,
            "base_spread_rate": p.base_spread_rate,
        },
    }


if __name__ == "__main__":
    # Autotest determinista: misma entrada -> misma salida siempre.
    test_params = {
        "grid_width": 15,
        "grid_height": 15,
        "ignition_points": [(7, 7)],
        "wind_direction_deg": 45.0,
        "wind_speed": 8.0,
        "timesteps": 12,
    }
    result = wildfire_tool(test_params)
    print("=== wildfire_tool self-test ===")
    print("Fracción quemada final:", result["final_burned_fraction"])
    print("Serie temporal (fracción quemada por paso):")
    print(result["burned_fraction_timeseries"])
    assert 0.0 <= result["final_burned_fraction"] <= 1.0
    assert len(result["burned_fraction_timeseries"]) == test_params["timesteps"]
    # Determinismo: correr dos veces debe dar exactamente el mismo resultado.
    result2 = wildfire_tool(test_params)
    assert result["burned_fraction_timeseries"] == result2["burned_fraction_timeseries"], \
        "El modelo debe ser determinista"
    print("OK: determinismo verificado, rangos válidos.")
