"""
poaching_tool.py

Modelo agregado estandar de dinamica poblacional bajo presion de caza
furtiva: crecimiento logistico menos una extraccion (offtake) de tipo
respuesta funcional I, moderada por el esfuerzo de fiscalizacion.

    dN/dt (discreto, anual) = r*N*(1-N/K) - offtake(t)
    offtake(t) = catchability * effective_effort * N
    effective_effort = poacher_effort * (1 - enforcement_effectiveness)

Patron: compute_poaching_tool(mode, params) + POACHING_TOOL_SCHEMA
Auto-registro via register_tool (mismo patron que wildfire_risk_tool / plague_sir).

Modos:
  - simulate  : corre la trayectoria poblacional N anios, reporta riesgo de
                extincion (umbral MVP) y estimacion de rendimiento maximo
                sostenible (MSY, analogo a N=K/2)
  - validate  : autotest de consistencia (mode="validate")

CONFIANZA MEDIA: catchability y efectividad de fiscalizacion son dificiles
de medir directamente en campo; los defaults son ilustrativos de ordenes de
magnitud tipicos de literatura de manejo de vida silvestre, no calibrados a
una especie o sitio real.
"""


def _simulate_poaching(initial_population, carrying_capacity,
                        intrinsic_growth_rate=0.15, catchability=0.00006,
                        poacher_effort=800.0, enforcement_effectiveness=0.4,
                        years=25, minimum_viable_population=500.0):
    if initial_population < 0:
        raise ValueError("initial_population no puede ser negativo")
    if carrying_capacity <= 0:
        raise ValueError("carrying_capacity debe ser > 0")
    if years <= 0:
        raise ValueError("years debe ser > 0")
    if not (0.0 <= enforcement_effectiveness <= 1.0):
        raise ValueError("enforcement_effectiveness debe estar en [0, 1]")

    N = initial_population
    pop_series = [round(N, 4)]
    offtake_series = []
    extinction_year = None

    effective_effort = poacher_effort * (1 - enforcement_effectiveness)

    for year in range(1, years + 1):
        growth = intrinsic_growth_rate * N * (1 - N / carrying_capacity)
        offtake = catchability * effective_effort * N
        offtake = min(offtake, N)  # no se puede extraer mas de lo que hay
        N = max(0.0, N + growth - offtake)

        pop_series.append(round(N, 4))
        offtake_series.append(round(offtake, 4))

        if extinction_year is None and N <= minimum_viable_population:
            extinction_year = year

    msy_estimate = intrinsic_growth_rate * carrying_capacity / 4.0
    sustainable_effective_effort = (
        msy_estimate / (catchability * (carrying_capacity / 2))
        if catchability > 0 else None
    )

    return {
        "years_simulated": years,
        "initial_population": initial_population,
        "final_population": round(N, 4),
        "population_timeseries": pop_series,
        "annual_offtake_timeseries": offtake_series,
        "extinction_risk": extinction_year is not None,
        "year_reached_mvp_threshold": extinction_year,
        "effective_poaching_effort": round(effective_effort, 4),
        "max_sustainable_yield_estimate": round(msy_estimate, 4),
        "sustainable_effective_effort_estimate": (
            round(sustainable_effective_effort, 4) if sustainable_effective_effort is not None else None
        ),
        "data_confidence": "medium (catchability y defaults ilustrativos, no calibrados a especie/sitio real)",
    }


def _validate():
    checks = []

    # 1) Sin caza (poacher_effort=0) -> poblacion crece hacia K, nunca la supera
    r1 = _simulate_poaching(1000, 5000, poacher_effort=0.0, years=40)
    ok1 = r1["final_population"] <= 5000 + 1e-6 and r1["final_population"] > 1000
    checks.append(("zero_effort_grows_toward_K_never_exceeds", ok1))

    # 2) Poblacion nunca negativa
    r2 = _simulate_poaching(2000, 6000, poacher_effort=5000, catchability=0.0005,
                             enforcement_effectiveness=0.0, years=20)
    ok2 = all(p >= 0 for p in r2["population_timeseries"])
    checks.append(("population_never_negative", ok2))

    # 3) Mas fiscalizacion (enforcement_effectiveness alta) -> poblacion final mayor,
    #    todo lo demas igual
    base_kwargs = dict(initial_population=3000, carrying_capacity=6000,
                        intrinsic_growth_rate=0.18, catchability=0.00008,
                        poacher_effort=1200, years=20)
    r_low_enforcement = _simulate_poaching(enforcement_effectiveness=0.1, **base_kwargs)
    r_high_enforcement = _simulate_poaching(enforcement_effectiveness=0.9, **base_kwargs)
    ok3 = r_high_enforcement["final_population"] > r_low_enforcement["final_population"]
    checks.append(("more_enforcement_higher_final_population", ok3))

    # 4) Mayor esfuerzo de caza (poacher_effort) -> poblacion final menor,
    #    todo lo demas igual
    base_kwargs2 = dict(initial_population=3000, carrying_capacity=6000,
                         intrinsic_growth_rate=0.18, catchability=0.00008,
                         enforcement_effectiveness=0.3, years=20)
    r_low_effort = _simulate_poaching(poacher_effort=200, **base_kwargs2)
    r_high_effort = _simulate_poaching(poacher_effort=3000, **base_kwargs2)
    ok4 = r_high_effort["final_population"] < r_low_effort["final_population"]
    checks.append(("more_poaching_effort_lower_final_population", ok4))

    # 5) Presion extrema sostenida -> se detecta riesgo de extincion (cruce de MVP)
    r5 = _simulate_poaching(1000, 3000, intrinsic_growth_rate=0.1, catchability=0.001,
                             poacher_effort=4000, enforcement_effectiveness=0.0,
                             years=30, minimum_viable_population=200)
    ok5 = r5["extinction_risk"] is True and r5["year_reached_mvp_threshold"] is not None
    checks.append(("extreme_pressure_triggers_extinction_risk", ok5))

    # 6) MSY estimado es positivo y escala con K (K mayor -> MSY mayor, r y demas fijos)
    r6a = _simulate_poaching(1000, 4000, intrinsic_growth_rate=0.2, poacher_effort=0)
    r6b = _simulate_poaching(1000, 8000, intrinsic_growth_rate=0.2, poacher_effort=0)
    ok6 = r6a["max_sustainable_yield_estimate"] > 0 and \
        r6b["max_sustainable_yield_estimate"] > r6a["max_sustainable_yield_estimate"]
    checks.append(("msy_positive_and_scales_with_K", ok6))

    # 7) Parametros invalidos levantan error
    try:
        _simulate_poaching(-100, 1000)
        raised = False
    except ValueError:
        raised = True
    checks.append(("invalid_initial_population_raises", raised))

    passed = sum(1 for _, ok in checks if ok)
    return {
        "mode": "validate",
        "checks": [{"name": n, "passed": ok} for n, ok in checks],
        "passed": passed,
        "total": len(checks),
        "all_passed": passed == len(checks),
    }


POACHING_TOOL_SCHEMA = {
    "name": "poaching_tool",
    "description": (
        "Modelo agregado de dinamica poblacional bajo presion de caza furtiva: "
        "crecimiento logistico menos extraccion por caza, moderada por esfuerzo de "
        "fiscalizacion. Reporta riesgo de extincion (umbral MVP) y rendimiento maximo "
        "sostenible estimado (mode='simulate'). mode='validate' corre la suite de autotest."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["simulate", "validate"]},
            "params": {
                "type": "object",
                "properties": {
                    "initial_population": {"type": "number", "description": "Poblacion inicial (individuos)"},
                    "carrying_capacity": {"type": "number", "description": "Capacidad de carga K del habitat"},
                    "intrinsic_growth_rate": {"type": "number", "description": "Tasa intrinseca de crecimiento anual r (default 0.15)"},
                    "catchability": {"type": "number", "description": "Eficiencia de captura por unidad de esfuerzo (default 0.00006)"},
                    "poacher_effort": {"type": "number", "description": "Esfuerzo de caza, proxy cazadores-dia/anio (default 800)"},
                    "enforcement_effectiveness": {"type": "number", "description": "Fraccion del esfuerzo neutralizado por fiscalizacion, 0-1 (default 0.4)"},
                    "years": {"type": "integer", "description": "Anios a simular (default 25)"},
                    "minimum_viable_population": {"type": "number", "description": "Umbral de riesgo de extincion (default 500)"},
                },
            },
        },
        "required": ["mode"],
    },
}


def compute_poaching_tool(mode, params):
    params = params or {}

    if mode == "simulate":
        initial_population = params.get("initial_population")
        carrying_capacity = params.get("carrying_capacity")
        if initial_population is None or carrying_capacity is None:
            raise ValueError("Se requieren 'initial_population' y 'carrying_capacity' en params para mode='simulate'")
        return {
            "mode": mode,
            **_simulate_poaching(
                float(initial_population),
                float(carrying_capacity),
                intrinsic_growth_rate=float(params.get("intrinsic_growth_rate", 0.15)),
                catchability=float(params.get("catchability", 0.00006)),
                poacher_effort=float(params.get("poacher_effort", 800.0)),
                enforcement_effectiveness=float(params.get("enforcement_effectiveness", 0.4)),
                years=int(params.get("years", 25)),
                minimum_viable_population=float(params.get("minimum_viable_population", 500.0)),
            ),
        }
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"Modo desconocido: {mode}. Use 'simulate' o 'validate'")


try:
    from tool_registry import register_tool
    register_tool(
        name="poaching_tool",
        schema=POACHING_TOOL_SCHEMA,
        handler=lambda args: compute_poaching_tool(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    d = compute_poaching_tool("validate", {})
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["all_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de poaching_tool.py pasaron OK.")
