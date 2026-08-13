"""
urban_planning_tool.py

Metricas de planificacion urbana: mezcla de uso de suelo, accesibilidad a
servicios, densidad vs. capacidad instalada, y proyeccion de demanda de
infraestructura por crecimiento poblacional.

Modos:
  - land_use_mix_index: indice de mezcla de uso de suelo via entropia de
    Shannon normalizada (Cervero & Kockelman 1997 usan una forma equivalente
    para el componente "diversity" del modelo 3D de forma urbana).
  - service_accessibility_index: fraccion de poblacion cubierta dentro de un
    radio/distancia umbral a un servicio (salud, educacion, transporte).
  - density_capacity_ratio: densidad poblacional y, si se provee capacidad
    de diseno, ratio de utilizacion vs. esa capacidad.
  - infrastructure_demand_projection: proyeccion de demanda de infraestructura
    (agua, energia, transporte) via crecimiento poblacional compuesto y
    demanda per capita, con deteccion del anio en que se supera la capacidad
    instalada.
  - validate: suite de 10 checks.

confidence_flag: "alta" (formulas cerradas estandar); el modelo de
crecimiento poblacional es geometrico simple (no captura migracion,
politicas de uso de suelo, ni shocks), asi que infrastructure_demand_projection
debe tratarse como escenario, no pronostico.
"""

import json
import math
import sys


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------

def _land_use_mix_index(params):
    areas = params["areas"]  # dict categoria -> area
    if not areas:
        raise ValueError("areas no puede estar vacio")
    total = sum(areas.values())
    if total <= 0:
        raise ValueError("el area total debe ser positiva")

    proportions = {k: v / total for k, v in areas.items()}
    n_categories = len(areas)
    if n_categories <= 1:
        h_norm = 0.0
    else:
        h = -sum(p * math.log(p) for p in proportions.values() if p > 0)
        h_max = math.log(n_categories)
        h_norm = h / h_max

    return {
        "proportions": {k: round(v, 6) for k, v in proportions.items()},
        "n_categories": n_categories,
        "shannon_entropy_normalized": round(h_norm, 6),
        "interpretation": (
            "1.0 = mezcla perfectamente equilibrada entre todas las categorias de uso "
            "de suelo presentes, 0.0 = monocultivo (una sola categoria domina el area)"
        ),
    }


def _service_accessibility_index(params):
    zones = params["zones"]  # [{"population","distance_to_service_km"}]
    if not zones:
        raise ValueError("zones no puede estar vacio")
    threshold_km = float(params.get("threshold_km", 0.5))

    total_pop = sum(z["population"] for z in zones)
    if total_pop <= 0:
        raise ValueError("la poblacion total debe ser positiva")

    covered_pop = sum(z["population"] for z in zones if z["distance_to_service_km"] <= threshold_km)
    accessibility_index = covered_pop / total_pop
    underserved = [z for z in zones if z["distance_to_service_km"] > threshold_km]

    return {
        "total_population": total_pop,
        "covered_population": covered_pop,
        "accessibility_index": round(accessibility_index, 6),
        "threshold_km": threshold_km,
        "n_underserved_zones": len(underserved),
        "underserved_population": sum(z["population"] for z in underserved),
    }


def _density_capacity_ratio(params):
    population = float(params["population"])
    area_km2 = float(params["area_km2"])
    if area_km2 <= 0:
        raise ValueError("area_km2 debe ser positiva")
    capacity_per_km2 = params.get("capacity_per_km2")

    density = population / area_km2
    result = {
        "population": population,
        "area_km2": area_km2,
        "density_per_km2": round(density, 6),
    }
    if capacity_per_km2 is not None:
        capacity_per_km2 = float(capacity_per_km2)
        if capacity_per_km2 <= 0:
            raise ValueError("capacity_per_km2 debe ser positiva")
        utilization_ratio = density / capacity_per_km2
        result["capacity_per_km2"] = capacity_per_km2
        result["utilization_ratio"] = round(utilization_ratio, 6)
        result["over_capacity"] = utilization_ratio > 1.0
    return result


def _infrastructure_demand_projection(params):
    population0 = float(params["population0"])
    growth_rate = float(params["annual_growth_rate"])
    years = int(params["years"])
    per_capita_demand = float(params["per_capita_demand"])
    current_capacity = params.get("current_capacity")
    if current_capacity is not None:
        current_capacity = float(current_capacity)
    if population0 <= 0:
        raise ValueError("population0 debe ser positiva")
    if years < 0:
        raise ValueError("years debe ser >= 0")

    projection = []
    exceeded_year = None
    for y in range(0, years + 1):
        pop_y = population0 * ((1 + growth_rate) ** y)
        demand_y = pop_y * per_capita_demand
        entry = {"year": y, "population": round(pop_y, 2), "demand": round(demand_y, 2)}
        if current_capacity is not None:
            entry["exceeds_capacity"] = demand_y > current_capacity
            if demand_y > current_capacity and exceeded_year is None:
                exceeded_year = y
        projection.append(entry)

    result = {
        "projection": projection,
        "final_population": projection[-1]["population"],
        "final_demand": projection[-1]["demand"],
    }
    if current_capacity is not None:
        result["current_capacity"] = current_capacity
        result["year_capacity_exceeded"] = exceeded_year
    return result


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

def _check(name, passed, **extra):
    return {"name": name, "passed": bool(passed), **extra}


def _validate():
    checks = []

    # Mix de uso de suelo: areas iguales entre categorias -> entropia normalizada = 1.0
    equal_mix = _land_use_mix_index({"areas": {"residencial": 25, "comercial": 25, "industrial": 25, "verde": 25}})
    checks.append(_check(
        "equal_land_use_areas_give_max_entropy",
        abs(equal_mix["shannon_entropy_normalized"] - 1.0) < 1e-9,
        entropy=equal_mix["shannon_entropy_normalized"],
    ))

    # Mix de uso de suelo: monocultivo -> entropia normalizada = 0.0
    mono_mix = _land_use_mix_index({"areas": {"residencial": 100, "comercial": 0, "industrial": 0}})
    checks.append(_check(
        "monoculture_land_use_gives_zero_entropy",
        abs(mono_mix["shannon_entropy_normalized"] - 0.0) < 1e-9,
        entropy=mono_mix["shannon_entropy_normalized"],
    ))

    checks.append(_check(
        "land_use_zero_total_area_raises",
        _raises(_land_use_mix_index, {"areas": {"a": 0, "b": 0}}),
    ))

    # Accesibilidad a servicios: todas las zonas dentro del umbral -> indice 1.0
    all_covered = _service_accessibility_index({
        "zones": [
            {"population": 100, "distance_to_service_km": 0.2},
            {"population": 200, "distance_to_service_km": 0.4},
        ],
        "threshold_km": 0.5,
    })
    checks.append(_check(
        "all_zones_within_threshold_gives_full_accessibility",
        all_covered["accessibility_index"] == 1.0,
        accessibility_index=all_covered["accessibility_index"],
    ))

    # Accesibilidad a servicios: ninguna zona dentro del umbral -> indice 0.0
    none_covered = _service_accessibility_index({
        "zones": [
            {"population": 100, "distance_to_service_km": 5.0},
            {"population": 200, "distance_to_service_km": 6.0},
        ],
        "threshold_km": 0.5,
    })
    checks.append(_check(
        "no_zones_within_threshold_gives_zero_accessibility",
        none_covered["accessibility_index"] == 0.0,
        accessibility_index=none_covered["accessibility_index"],
    ))

    # Densidad/capacidad: densidad calculada correctamente y flag over_capacity
    dens_over = _density_capacity_ratio({"population": 15000, "area_km2": 10, "capacity_per_km2": 1000})
    checks.append(_check(
        "density_over_capacity_correctly_flagged",
        dens_over["density_per_km2"] == 1500.0 and dens_over["over_capacity"] is True,
        density=dens_over["density_per_km2"], over_capacity=dens_over["over_capacity"],
    ))
    dens_under = _density_capacity_ratio({"population": 5000, "area_km2": 10, "capacity_per_km2": 1000})
    checks.append(_check(
        "density_under_capacity_correctly_flagged",
        dens_under["over_capacity"] is False,
        over_capacity=dens_under["over_capacity"],
    ))

    # Proyeccion de demanda: crecimiento compuesto reproduce formula cerrada
    proj = _infrastructure_demand_projection({
        "population0": 10000, "annual_growth_rate": 0.05, "years": 10,
        "per_capita_demand": 150, "current_capacity": 2_000_000,
    })
    expected_pop_year10 = 10000 * (1.05 ** 10)
    checks.append(_check(
        "demand_projection_matches_closed_form_growth",
        abs(proj["final_population"] - round(expected_pop_year10, 2)) < 0.5,
        computed=proj["final_population"], expected=round(expected_pop_year10, 2),
    ))
    checks.append(_check(
        "demand_projection_detects_capacity_exceeded_year",
        proj["year_capacity_exceeded"] is not None,
        year_capacity_exceeded=proj["year_capacity_exceeded"],
    ))

    checks.append(_check("invalid_mode_raises", _raises(compute_urban_planning, "modo_inexistente", {})))

    return {"checks": checks, "validation_passed": all(c["passed"] for c in checks)}


def _raises(fn, *args):
    try:
        fn(*args)
        return False
    except ValueError:
        return True


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def compute_urban_planning(mode, params):
    params = params or {}
    if mode == "land_use_mix_index":
        return _land_use_mix_index(params)
    elif mode == "service_accessibility_index":
        return _service_accessibility_index(params)
    elif mode == "density_capacity_ratio":
        return _density_capacity_ratio(params)
    elif mode == "infrastructure_demand_projection":
        return _infrastructure_demand_projection(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"modo desconocido: {mode}")


URBAN_PLANNING_TOOL_SCHEMA = {
    "name": "urban_planning_tool",
    "description": (
        "Metricas de planificacion urbana: land_use_mix_index (indice de mezcla de uso "
        "de suelo via entropia de Shannon normalizada, 1.0=mezcla equilibrada, "
        "0.0=monocultivo), service_accessibility_index (fraccion de poblacion cubierta "
        "dentro de una distancia umbral a un servicio), density_capacity_ratio (densidad "
        "poblacional y, si se provee capacidad de diseno, ratio de utilizacion con flag "
        "over_capacity), infrastructure_demand_projection (proyeccion de demanda via "
        "crecimiento poblacional geometrico y demanda per capita, detecta el anio en que "
        "se supera la capacidad instalada), validate (suite de 10 checks). confidence_flag "
        "'alta' (formulas cerradas estandar); el crecimiento poblacional es geometrico "
        "simple, tratar la proyeccion como escenario, no pronostico."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"mode": {"type": "string"}, "params": {"type": "object"}},
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        result = compute_urban_planning(req.get("mode", "validate"), req.get("params", {}))
        print(json.dumps(result, ensure_ascii=False, indent=2))
