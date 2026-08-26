"""
resource_scarcity_tool.py

Modelos de dinamica poblacion-recursos con escasez finita:
- predict_collapse: modelo logistico de poblacion con recurso finito no renovable
  (variante simplificada de dinamica de sobreexplotacion / colapso tipo Tainter)
- rationing_sim: simula el efecto de un racionamiento (recorte de consumo per capita)
  sobre la duracion de un stock de recursos
- migration_flow: modelo de flujo migratorio forzado en funcion de un gradiente
  de "presion" (escasez relativa entre dos regiones)

Todos los modelos son deterministas y de proposito educativo/analitico:
sirven para explorar escenarios agregados, no para predecir eventos reales
especificos ni recomendar acciones sobre personas o grupos identificables.
"""

import math


# ---------------------------------------------------------------------------
# 1) predict_collapse — poblacion vs. stock de recurso finito
# ---------------------------------------------------------------------------
def predict_collapse(params):
    """
    Modelo discreto simple:
      stock(t+1) = stock(t) - consumo_percapita * poblacion(t)
      poblacion(t+1) = poblacion(t) * (1 + growth_rate * (stock(t)/stock0) - decline_if_scarce)

    Devuelve la serie temporal y el "tiempo de colapso" (cuando stock <= 0).
    """
    population0 = params.get("population0", 1000.0)
    stock0 = params.get("stock0", 100000.0)
    consumption_percapita = params.get("consumption_percapita", 1.0)
    growth_rate = params.get("growth_rate", 0.02)
    steps = int(params.get("steps", 200))

    population = population0
    stock = stock0

    series = []
    collapse_step = None

    for t in range(steps):
        series.append({"t": t, "population": population, "stock": stock})

        if stock <= 0:
            collapse_step = t
            break

        consumption = consumption_percapita * population
        stock_next = stock - consumption

        scarcity_ratio = max(0.0, stock / stock0)
        pop_next = population * (1 + growth_rate * scarcity_ratio - growth_rate * (1 - scarcity_ratio))

        stock = stock_next
        population = max(0.0, pop_next)

    return {
        "series": series,
        "collapse_step": collapse_step,
        "final_population": population,
        "final_stock": stock,
    }


# ---------------------------------------------------------------------------
# 2) rationing_sim — impacto de racionamiento en la duracion del stock
# ---------------------------------------------------------------------------
def rationing_sim(params):
    """
    Compara la duracion de un stock finito con y sin racionamiento
    (reduccion porcentual del consumo per capita).
    """
    population = params.get("population", 1000.0)
    stock0 = params.get("stock0", 100000.0)
    consumption_percapita = params.get("consumption_percapita", 1.0)
    rationing_pct = params.get("rationing_pct", 0.2)  # 20% de recorte

    baseline_daily = consumption_percapita * population
    rationed_daily = consumption_percapita * (1 - rationing_pct) * population

    duration_baseline = stock0 / baseline_daily if baseline_daily > 0 else float("inf")
    duration_rationed = stock0 / rationed_daily if rationed_daily > 0 else float("inf")

    extension_days = duration_rationed - duration_baseline
    extension_pct = (extension_days / duration_baseline * 100.0) if duration_baseline > 0 else 0.0

    return {
        "duration_baseline_days": duration_baseline,
        "duration_rationed_days": duration_rationed,
        "extension_days": extension_days,
        "extension_pct": extension_pct,
    }


# ---------------------------------------------------------------------------
# 3) migration_flow — flujo migratorio forzado por gradiente de escasez
# ---------------------------------------------------------------------------
def migration_flow(params):
    """
    Modelo simple tipo "gravedad" adaptado: el flujo migratorio es proporcional
    a la diferencia de presion (escasez relativa) entre origen y destino,
    atenuado por una "friccion" (distancia, barreras, costo de migrar).
    """
    population_origin = params.get("population_origin", 10000.0)
    scarcity_origin = params.get("scarcity_origin", 0.8)   # 0=abundancia, 1=escasez total
    scarcity_destination = params.get("scarcity_destination", 0.2)
    friction = params.get("friction", 0.5)  # 0=sin friccion, 1=friccion maxima
    mobility_rate = params.get("mobility_rate", 0.05)  # fraccion maxima movilizable por periodo

    pressure_gradient = max(0.0, scarcity_origin - scarcity_destination)
    effective_rate = mobility_rate * pressure_gradient * (1 - friction)
    migrants = population_origin * effective_rate

    return {
        "pressure_gradient": pressure_gradient,
        "effective_migration_rate": effective_rate,
        "migrants_per_period": migrants,
        "remaining_population_origin": population_origin - migrants,
    }


# ---------------------------------------------------------------------------
# Dispatch principal
# ---------------------------------------------------------------------------
def resource_scarcity_tool(params: dict) -> dict:
    mode = params.get("mode", "predict_collapse")

    if mode == "predict_collapse":
        return predict_collapse(params)
    elif mode == "rationing_sim":
        return rationing_sim(params)
    elif mode == "migration_flow":
        return migration_flow(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            "mode invalido. Opciones: predict_collapse, rationing_sim, "
            "migration_flow, validate"
        )


# ---------------------------------------------------------------------------
# Modo validate
# ---------------------------------------------------------------------------
def _validate():
    checks = []

    # 1) predict_collapse: con consumo mayor que la regeneracion (no hay regeneracion
    #    en este modelo, es stock finito), el stock debe llegar a 0 antes del limite de steps
    r1 = predict_collapse({
        "population0": 1000.0,
        "stock0": 5000.0,
        "consumption_percapita": 1.0,
        "growth_rate": 0.0,  # poblacion constante para simplificar el check
        "steps": 20,
    })
    checks.append({
        "name": "collapse_occurs_with_finite_stock",
        "passed": r1["collapse_step"] is not None and r1["collapse_step"] <= 5,
        "collapse_step": r1["collapse_step"],
        "expected_step": 5,
    })

    # 2) predict_collapse: stock muy grande y poblacion estable -> no colapsa en pocos steps
    r2 = predict_collapse({
        "population0": 10.0,
        "stock0": 1_000_000.0,
        "consumption_percapita": 1.0,
        "growth_rate": 0.0,
        "steps": 50,
    })
    checks.append({
        "name": "no_collapse_with_abundant_stock",
        "passed": r2["collapse_step"] is None,
        "collapse_step": r2["collapse_step"],
    })

    # 3) rationing_sim: racionar consumo debe SIEMPRE extender la duracion (extension >= 0)
    r3 = rationing_sim({
        "population": 1000.0,
        "stock0": 100000.0,
        "consumption_percapita": 1.0,
        "rationing_pct": 0.25,
    })
    # calculo manual: baseline = 100000/1000 = 100 dias; rationed = 100000/750 = 133.33 dias
    expected_baseline = 100.0
    expected_rationed = 100000.0 / 750.0
    checks.append({
        "name": "rationing_extends_duration",
        "passed": (
            r3["extension_days"] > 0
            and abs(r3["duration_baseline_days"] - expected_baseline) < 1e-6
            and abs(r3["duration_rationed_days"] - expected_rationed) < 1e-6
        ),
        "duration_baseline_days": r3["duration_baseline_days"],
        "duration_rationed_days": r3["duration_rationed_days"],
        "expected_baseline": expected_baseline,
        "expected_rationed": expected_rationed,
    })

    # 4) rationing_sim: 0% de racionamiento -> extension ~0
    r4 = rationing_sim({
        "population": 500.0,
        "stock0": 50000.0,
        "consumption_percapita": 2.0,
        "rationing_pct": 0.0,
    })
    checks.append({
        "name": "zero_rationing_no_extension",
        "passed": abs(r4["extension_days"]) < 1e-6,
        "extension_days": r4["extension_days"],
    })

    # 5) migration_flow: gradiente nulo (misma escasez en origen y destino) -> sin migrantes
    r5 = migration_flow({
        "population_origin": 10000.0,
        "scarcity_origin": 0.5,
        "scarcity_destination": 0.5,
        "friction": 0.3,
        "mobility_rate": 0.1,
    })
    checks.append({
        "name": "no_migration_with_zero_gradient",
        "passed": abs(r5["migrants_per_period"]) < 1e-9,
        "migrants_per_period": r5["migrants_per_period"],
    })

    # 6) migration_flow: friccion maxima (1.0) -> sin migrantes aunque haya gradiente
    r6 = migration_flow({
        "population_origin": 10000.0,
        "scarcity_origin": 0.9,
        "scarcity_destination": 0.1,
        "friction": 1.0,
        "mobility_rate": 0.1,
    })
    checks.append({
        "name": "no_migration_with_max_friction",
        "passed": abs(r6["migrants_per_period"]) < 1e-9,
        "migrants_per_period": r6["migrants_per_period"],
    })

    # 7) migration_flow: gradiente positivo y friccion baja -> migrantes > 0 y <= poblacion origen
    r7 = migration_flow({
        "population_origin": 10000.0,
        "scarcity_origin": 0.9,
        "scarcity_destination": 0.1,
        "friction": 0.0,
        "mobility_rate": 0.1,
    })
    checks.append({
        "name": "positive_migration_within_bounds",
        "passed": 0 < r7["migrants_per_period"] <= 10000.0,
        "migrants_per_period": r7["migrants_per_period"],
    })

    all_passed = all(c["passed"] for c in checks)
    return {
        "mode": "validate",
        "tool": "resource_scarcity_tool",
        "all_passed": all_passed,
        "checks": checks,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(resource_scarcity_tool({"mode": "validate"}), indent=2))
