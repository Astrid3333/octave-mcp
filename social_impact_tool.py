"""
social_impact_tool.py

Impacto social de desastres. Cuatro modos + validate:

- affected_population: poblacion afectada = poblacion_expuesta *
  fraccion_de_exposicion (dado el area/huella del peligro sobre el
  area total de la poblacion expuesta).

- displaced_population: poblacion desplazada = poblacion_afectada *
  tasa_de_desplazamiento, donde la tasa de desplazamiento es una
  funcion simple del ratio de dano a vivienda (mas dano estructural ->
  mayor fraccion de la poblacion afectada queda desplazada):
  displacement_rate = min(1, housing_damage_ratio * displacement_factor).

- social_vulnerability_index: indice compuesto ponderado 0-100 (mismo
  patron de composicion que financial_literacy_score_tool), combinando
  4 componentes normalizados que provee quien llama: dependencia etaria
  (fraccion de poblacion menor de 15 o mayor de 65), pobreza (fraccion
  bajo linea de pobreza), densidad poblacional relativa, y fraccion con
  discapacidad o movilidad reducida -- todos en escala 0-1 donde 1 =
  mayor vulnerabilidad. Es un indice propio e ilustrativo (no reproduce
  un indice normativo especifico como el SoVI de Cutter et al.).

- social_recovery_time: tiempo de recuperacion de la funcionalidad
  social de una comunidad, mismo modelo de recuperacion exponencial que
  disaster_economics_tool.recovery_time pero aplicado a un indicador de
  funcionalidad social (acceso a servicios, cohesion comunitaria, etc.)
  en vez de funcionalidad economica.

- validate: suite de checks contra casos con solucion cerrada conocida.

Convencion identica al resto del repo: compute_social_impact(mode,
params=None) -> dict, registrado via tool_registry.register_tool().
"""
import numpy as np


SOCIAL_IMPACT_TOOL_SCHEMA = {
    "name": "social_impact_tool",
    "description": (
        "Impacto social de desastres: affected_population (poblacion "
        "expuesta * fraccion de exposicion), displaced_population "
        "(poblacion afectada * tasa de desplazamiento, funcion del ratio "
        "de dano a vivienda), social_vulnerability_index (indice "
        "compuesto 0-100 ponderando dependencia etaria, pobreza, "
        "densidad relativa y discapacidad/movilidad reducida -- indice "
        "propio e ilustrativo, no reproduce un indice normativo "
        "especifico como el SoVI de Cutter et al.), social_recovery_time "
        "(tiempo para alcanzar un umbral de funcionalidad social via "
        "recuperacion exponencial, mismo modelo que disaster_economics_"
        "tool.recovery_time pero aplicado a funcionalidad social), "
        "validate (suite de checks). Motor generico: los componentes de "
        "vulnerabilidad normalizados los provee quien llama."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "affected_population",
                    "displaced_population",
                    "social_vulnerability_index",
                    "social_recovery_time",
                    "validate",
                ],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}

DEFAULT_VULNERABILITY_WEIGHTS = {
    "age_dependency": 0.25,
    "poverty": 0.30,
    "density": 0.20,
    "disability": 0.25,
}


def _mode_affected_population(params):
    exposed_population = float(params["exposed_population"])
    if exposed_population < 0:
        raise ValueError("exposed_population debe ser >= 0")

    exposure_fraction = float(params["exposure_fraction"])
    if not (0.0 <= exposure_fraction <= 1.0):
        raise ValueError("exposure_fraction debe estar en [0, 1]")

    affected = exposed_population * exposure_fraction

    return {
        "mode": "affected_population",
        "exposed_population": exposed_population,
        "exposure_fraction": exposure_fraction,
        "affected_population": float(affected),
    }


def _mode_displaced_population(params):
    affected_population = float(params["affected_population"])
    if affected_population < 0:
        raise ValueError("affected_population debe ser >= 0")

    housing_damage_ratio = float(params["housing_damage_ratio"])
    if not (0.0 <= housing_damage_ratio <= 1.0):
        raise ValueError("housing_damage_ratio debe estar en [0, 1]")

    displacement_factor = float(params.get("displacement_factor", 1.0))
    if displacement_factor < 0:
        raise ValueError("displacement_factor debe ser >= 0")

    displacement_rate = min(1.0, housing_damage_ratio * displacement_factor)
    displaced = affected_population * displacement_rate

    return {
        "mode": "displaced_population",
        "affected_population": affected_population,
        "housing_damage_ratio": housing_damage_ratio,
        "displacement_factor": displacement_factor,
        "displacement_rate": float(displacement_rate),
        "displaced_population": float(displaced),
    }


def _get_vulnerability_weights(params):
    weights = dict(DEFAULT_VULNERABILITY_WEIGHTS)
    custom = params.get("weights", {})
    weights.update({k: float(v) for k, v in custom.items()})
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"los pesos deben sumar 1.0, suman {total}")
    return weights


def _mode_social_vulnerability_index(params):
    required = ["age_dependency", "poverty", "density", "disability"]
    missing = [r for r in required if r not in params]
    if missing:
        raise ValueError(f"faltan parametros requeridos: {missing}")

    components = {}
    for k in required:
        v = float(params[k])
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"{k} debe estar en [0, 1]")
        components[k] = v

    weights = _get_vulnerability_weights(params)
    score = sum(components[k] * 100.0 * weights[k] for k in weights)

    if score >= 75:
        level = "muy alta"
    elif score >= 50:
        level = "alta"
    elif score >= 25:
        level = "moderada"
    else:
        level = "baja"

    return {
        "mode": "social_vulnerability_index",
        "components": components,
        "weights": weights,
        "index_0_100": float(score),
        "level": level,
        "confidence_flag": "ilustrativo (indice propio, no reproduce un indice normativo especifico)",
    }


def _mode_social_recovery_time(params):
    functionality_0 = float(params["functionality_0"])
    if not (0.0 <= functionality_0 < 1.0):
        raise ValueError("functionality_0 debe estar en [0, 1)")

    tau_days = float(params["tau_days"])
    if tau_days <= 0:
        raise ValueError("tau_days debe ser > 0")

    target_functionality = float(params.get("target_functionality", 0.90))
    if not (functionality_0 < target_functionality <= 1.0):
        raise ValueError("target_functionality debe estar en (functionality_0, 1]")

    ratio = (1.0 - target_functionality) / (1.0 - functionality_0)
    if ratio <= 0:
        recovery_days = None
    else:
        recovery_days = float(-tau_days * np.log(ratio))

    return {
        "mode": "social_recovery_time",
        "functionality_0": functionality_0,
        "tau_days": tau_days,
        "target_functionality": target_functionality,
        "recovery_time_days": recovery_days,
        "method": "recuperacion exponencial: functionality(t) = 1 - (1-f0)*exp(-t/tau)",
    }


def _mode_validate():
    checks = []

    # 1) affected_population: caso exacto (10000 * 0.3 = 3000)
    r1 = _mode_affected_population({"exposed_population": 10000.0, "exposure_fraction": 0.3})
    checks.append({
        "name": "affected_population_exact",
        "affected": r1["affected_population"],
        "passed": abs(r1["affected_population"] - 3000.0) < 1e-9,
    })

    # 2) affected_population: exposure_fraction fuera de rango lanza excepcion
    try:
        _mode_affected_population({"exposed_population": 1000.0, "exposure_fraction": 1.5})
        raised2 = False
    except ValueError:
        raised2 = True
    checks.append({"name": "exposure_fraction_out_of_range_raises", "passed": raised2})

    # 3) displaced_population: dano total (ratio=1) con factor=1 desplaza a toda la poblacion afectada
    r3 = _mode_displaced_population({"affected_population": 500.0, "housing_damage_ratio": 1.0, "displacement_factor": 1.0})
    checks.append({
        "name": "full_housing_damage_displaces_all_affected",
        "displaced": r3["displaced_population"],
        "passed": abs(r3["displaced_population"] - 500.0) < 1e-9,
    })

    # 4) displaced_population: dano parcial da desplazamiento proporcional
    r4 = _mode_displaced_population({"affected_population": 1000.0, "housing_damage_ratio": 0.4, "displacement_factor": 1.0})
    checks.append({
        "name": "partial_housing_damage_proportional",
        "displaced": r4["displaced_population"],
        "passed": abs(r4["displaced_population"] - 400.0) < 1e-9,
    })

    # 5) displaced_population: displacement_factor alto se clippea la tasa a 1.0 (no puede desplazar mas del 100%)
    r5 = _mode_displaced_population({"affected_population": 200.0, "housing_damage_ratio": 0.8, "displacement_factor": 3.0})
    checks.append({
        "name": "displacement_rate_clips_at_one",
        "rate": r5["displacement_rate"], "displaced": r5["displaced_population"],
        "passed": abs(r5["displacement_rate"] - 1.0) < 1e-9 and abs(r5["displaced_population"] - 200.0) < 1e-9,
    })

    # 6) social_vulnerability_index: todos los componentes en el maximo dan index 100
    r6 = _mode_social_vulnerability_index({
        "age_dependency": 1.0, "poverty": 1.0, "density": 1.0, "disability": 1.0,
    })
    checks.append({
        "name": "all_max_vulnerability_gives_index_100",
        "index": r6["index_0_100"], "level": r6["level"],
        "passed": abs(r6["index_0_100"] - 100.0) < 1e-9 and r6["level"] == "muy alta",
    })

    # 7) social_vulnerability_index: todos los componentes en el minimo dan index 0
    r7 = _mode_social_vulnerability_index({
        "age_dependency": 0.0, "poverty": 0.0, "density": 0.0, "disability": 0.0,
    })
    checks.append({
        "name": "all_min_vulnerability_gives_index_0",
        "index": r7["index_0_100"], "level": r7["level"],
        "passed": abs(r7["index_0_100"]) < 1e-9 and r7["level"] == "baja",
    })

    # 8) social_vulnerability_index: pesos que no suman 1 lanzan excepcion
    try:
        _mode_social_vulnerability_index({
            "age_dependency": 0.5, "poverty": 0.5, "density": 0.5, "disability": 0.5,
            "weights": {"poverty": 0.9},
        })
        raised8 = False
    except ValueError:
        raised8 = True
    checks.append({"name": "invalid_weights_sum_raises", "passed": raised8})

    # 9) social_vulnerability_index: componente fuera de [0,1] lanza excepcion
    try:
        _mode_social_vulnerability_index({
            "age_dependency": 1.5, "poverty": 0.5, "density": 0.5, "disability": 0.5,
        })
        raised9 = False
    except ValueError:
        raised9 = True
    checks.append({"name": "component_out_of_range_raises", "passed": raised9})

    # 10) social_recovery_time: caso analitico simple, f0=0, target=1-1/e da recovery_time=tau exacto
    target = 1.0 - 1.0 / np.e
    r10 = _mode_social_recovery_time({"functionality_0": 0.0, "tau_days": 60.0, "target_functionality": float(target)})
    checks.append({
        "name": "social_recovery_time_at_one_tau",
        "recovery_days": r10["recovery_time_days"],
        "passed": abs(r10["recovery_time_days"] - 60.0) < 1e-6,
    })

    # 11) social_recovery_time: target_functionality fuera de rango lanza excepcion
    try:
        _mode_social_recovery_time({"functionality_0": 0.5, "tau_days": 30.0, "target_functionality": 0.3})
        raised11 = False
    except ValueError:
        raised11 = True
    checks.append({"name": "target_below_initial_raises", "passed": raised11})

    # 12) modo invalido lanza excepcion
    try:
        compute_social_impact("modo_invalido", {})
        invalid_raised = False
    except (KeyError, ValueError):
        invalid_raised = True
    checks.append({"name": "invalid_mode_raises", "passed": invalid_raised})

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_social_impact(mode, params=None):
    params = params or {}

    if mode == "affected_population":
        return _mode_affected_population(params)
    elif mode == "displaced_population":
        return _mode_displaced_population(params)
    elif mode == "social_vulnerability_index":
        return _mode_social_vulnerability_index(params)
    elif mode == "social_recovery_time":
        return _mode_social_recovery_time(params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(
            f"modo desconocido: {mode}. Use affected_population | displaced_population | "
            f"social_vulnerability_index | social_recovery_time | validate"
        )


try:
    from tool_registry import register_tool
    register_tool(
        name="social_impact_tool",
        schema=SOCIAL_IMPACT_TOOL_SCHEMA,
        handler=lambda args: compute_social_impact(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    d = compute_social_impact("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de social_impact_tool.py pasaron OK.")
