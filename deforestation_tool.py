"""
deforestation_tool.py

Modelo agregado estandar de cambio de cobertura forestal (compartimental,
no espacial): el area de bosque es un stock que decae segun presiones de
expansion agricola y extraccion maderera, moderadas por la fraccion del
area bajo proteccion legal efectiva y un multiplicador de acceso vial.

    dA/dt (discreto, anual) = -k(t) * A(t)
    k(t) = (agri_expansion_rate + logging_rate * (1 - protected_fraction * protection_effectiveness))
           * road_expansion_multiplier

Patron: compute_deforestation_tool(mode, params) + DEFORESTATION_TOOL_SCHEMA
Auto-registro via register_tool (mismo patron que wildfire_risk_tool / plague_sir).

Modos:
  - simulate  : corre la trayectoria de area forestal N anios, con
                emisiones de CO2 estimadas por perdida de area
  - validate  : autotest de consistencia (mode="validate")

CONFIANZA MEDIA: los defaults (tasas, densidad de carbono) son ilustrativos
de ordenes de magnitud tipicos de literatura de deforestacion tropical, no
calibrados a un sitio real. Para uso en un caso concreto, pasar tasas y
densidad de carbono medidas o de fuente oficial via 'params'.
"""


def _simulate_deforestation(initial_forest_area_ha, years=20,
                             agri_expansion_rate=0.015, logging_rate=0.010,
                             protected_fraction=0.2, protection_effectiveness=0.7,
                             road_expansion_multiplier=1.0,
                             carbon_density_t_co2_per_ha=150.0):
    if initial_forest_area_ha <= 0:
        raise ValueError("initial_forest_area_ha debe ser > 0")
    if years <= 0:
        raise ValueError("years debe ser > 0")
    if not (0.0 <= protected_fraction <= 1.0):
        raise ValueError("protected_fraction debe estar en [0, 1]")
    if not (0.0 <= protection_effectiveness <= 1.0):
        raise ValueError("protection_effectiveness debe estar en [0, 1]")

    area = initial_forest_area_ha
    area_series = [round(area, 4)]
    annual_loss_ha = []
    annual_rate_pct = []
    cumulative_co2 = [0.0]

    for _year in range(1, years + 1):
        effective_logging = logging_rate * (1 - protected_fraction * protection_effectiveness)
        k = (agri_expansion_rate + effective_logging) * road_expansion_multiplier
        loss = area * k
        area = max(0.0, area - loss)

        area_series.append(round(area, 4))
        annual_loss_ha.append(round(loss, 4))
        annual_rate_pct.append(round(k * 100, 6))
        cumulative_co2.append(round(cumulative_co2[-1] + loss * carbon_density_t_co2_per_ha, 2))

    total_loss_ha = initial_forest_area_ha - area
    pct_lost = (total_loss_ha / initial_forest_area_ha) * 100 if initial_forest_area_ha > 0 else 0.0

    return {
        "years_simulated": years,
        "initial_forest_area_ha": initial_forest_area_ha,
        "final_forest_area_ha": round(area, 4),
        "forest_area_timeseries_ha": area_series,
        "annual_loss_ha": annual_loss_ha,
        "annual_deforestation_rate_pct": annual_rate_pct,
        "cumulative_co2_emissions_t": cumulative_co2,
        "total_area_lost_ha": round(total_loss_ha, 4),
        "total_pct_forest_lost": round(pct_lost, 4),
        "data_confidence": "medium (defaults ilustrativos de bosque tropical, no calibrados a sitio real)",
    }


def _validate():
    checks = []

    # 1) Sin presion (todas las tasas en 0) -> area no cambia
    r1 = _simulate_deforestation(100000, years=10, agri_expansion_rate=0.0,
                                  logging_rate=0.0, protected_fraction=0.0)
    ok1 = abs(r1["final_forest_area_ha"] - 100000) < 1e-6 and r1["total_pct_forest_lost"] == 0.0
    checks.append(("zero_pressure_no_change", ok1))

    # 2) El stock nunca es negativo ni crece
    r2 = _simulate_deforestation(50000, years=15, agri_expansion_rate=0.05, logging_rate=0.05)
    ok2 = all(a >= 0 for a in r2["forest_area_timeseries_ha"]) and \
        all(r2["forest_area_timeseries_ha"][i] <= r2["forest_area_timeseries_ha"][i - 1] + 1e-9
            for i in range(1, len(r2["forest_area_timeseries_ha"])))
    checks.append(("stock_nonnegative_and_nonincreasing", ok2))

    # 3) Mas proteccion efectiva -> menos perdida total, todo lo demas igual
    base_kwargs = dict(initial_forest_area_ha=100000, years=20,
                        agri_expansion_rate=0.02, logging_rate=0.02, protected_fraction=0.5)
    r_low_protection = _simulate_deforestation(protection_effectiveness=0.1, **base_kwargs)
    r_high_protection = _simulate_deforestation(protection_effectiveness=0.9, **base_kwargs)
    ok3 = r_high_protection["total_pct_forest_lost"] < r_low_protection["total_pct_forest_lost"]
    checks.append(("more_protection_less_loss", ok3))

    # 4) Mas acceso vial (road_expansion_multiplier > 1) -> mas perdida total
    r_no_roads = _simulate_deforestation(100000, years=20, agri_expansion_rate=0.02,
                                          logging_rate=0.01, road_expansion_multiplier=1.0)
    r_with_roads = _simulate_deforestation(100000, years=20, agri_expansion_rate=0.02,
                                            logging_rate=0.01, road_expansion_multiplier=1.8)
    ok4 = r_with_roads["total_pct_forest_lost"] > r_no_roads["total_pct_forest_lost"]
    checks.append(("road_expansion_increases_loss", ok4))

    # 5) CO2 acumulado es monotonamente no decreciente y proporcional a la perdida de area
    r5 = _simulate_deforestation(80000, years=12, agri_expansion_rate=0.03,
                                  logging_rate=0.02, carbon_density_t_co2_per_ha=180.0)
    co2 = r5["cumulative_co2_emissions_t"]
    ok5a = all(co2[i] >= co2[i - 1] - 1e-9 for i in range(1, len(co2)))
    expected_final_co2 = r5["total_area_lost_ha"] * 180.0
    ok5b = abs(co2[-1] - expected_final_co2) < max(1.0, expected_final_co2 * 0.01)
    checks.append(("co2_nondecreasing_and_proportional_to_loss", ok5a and ok5b))

    # 6) Area final invalida (<=0) o years invalido levanta error
    try:
        _simulate_deforestation(0, years=10)
        raised = False
    except ValueError:
        raised = True
    checks.append(("invalid_initial_area_raises", raised))

    passed = sum(1 for _, ok in checks if ok)
    return {
        "mode": "validate",
        "checks": [{"name": n, "passed": ok} for n, ok in checks],
        "passed": passed,
        "total": len(checks),
        "all_passed": passed == len(checks),
    }


DEFORESTATION_TOOL_SCHEMA = {
    "name": "deforestation_tool",
    "description": (
        "Modelo agregado de cambio de cobertura forestal: simula la trayectoria "
        "de area de bosque bajo presion de expansion agricola y tala, moderada por "
        "proteccion legal efectiva y acceso vial, con estimacion de emisiones de "
        "CO2 asociadas a la perdida de area (mode='simulate'). mode='validate' "
        "corre la suite de autotest."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["simulate", "validate"]},
            "params": {
                "type": "object",
                "properties": {
                    "initial_forest_area_ha": {"type": "number", "description": "Area forestal inicial en hectareas"},
                    "years": {"type": "integer", "description": "Anios a simular (default 20)"},
                    "agri_expansion_rate": {"type": "number", "description": "Tasa anual de perdida por expansion agricola (default 0.015)"},
                    "logging_rate": {"type": "number", "description": "Tasa anual de perdida por tala (default 0.010)"},
                    "protected_fraction": {"type": "number", "description": "Fraccion del area bajo proteccion legal (default 0.2)"},
                    "protection_effectiveness": {"type": "number", "description": "Efectividad de la proteccion, 0-1 (default 0.7)"},
                    "road_expansion_multiplier": {"type": "number", "description": "Multiplicador de presion por acceso vial (default 1.0)"},
                    "carbon_density_t_co2_per_ha": {"type": "number", "description": "Emision estimada por ha deforestada (default 150.0)"},
                },
            },
        },
        "required": ["mode"],
    },
}


def compute_deforestation_tool(mode, params):
    params = params or {}

    if mode == "simulate":
        initial_forest_area_ha = params.get("initial_forest_area_ha")
        if initial_forest_area_ha is None:
            raise ValueError("Se requiere 'initial_forest_area_ha' en params para mode='simulate'")
        return {
            "mode": mode,
            **_simulate_deforestation(
                float(initial_forest_area_ha),
                years=int(params.get("years", 20)),
                agri_expansion_rate=float(params.get("agri_expansion_rate", 0.015)),
                logging_rate=float(params.get("logging_rate", 0.010)),
                protected_fraction=float(params.get("protected_fraction", 0.2)),
                protection_effectiveness=float(params.get("protection_effectiveness", 0.7)),
                road_expansion_multiplier=float(params.get("road_expansion_multiplier", 1.0)),
                carbon_density_t_co2_per_ha=float(params.get("carbon_density_t_co2_per_ha", 150.0)),
            ),
        }
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"Modo desconocido: {mode}. Use 'simulate' o 'validate'")


try:
    from tool_registry import register_tool
    register_tool(
        name="deforestation_tool",
        schema=DEFORESTATION_TOOL_SCHEMA,
        handler=lambda args: compute_deforestation_tool(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    d = compute_deforestation_tool("validate", {})
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["all_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de deforestation_tool.py pasaron OK.")
