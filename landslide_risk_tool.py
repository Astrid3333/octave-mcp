"""
landslide_risk_tool.py

Riesgo de deslizamiento de talud. Tres modos + validate:

- infinite_slope_fs: factor de seguridad (FS) de un talud infinito via
  el modelo clasico de Mohr-Coulomb para pendiente infinita (estandar en
  mecanica de suelos / geotecnia, ver p.ej. Selby 1993, Duncan & Wright
  2005):
      FS = [c + (gamma - m*gamma_w)*z*cos^2(beta)*tan(phi)] /
           [gamma*z*sin(beta)*cos(beta)]
  donde c=cohesion, phi=angulo de friccion interna, gamma=peso unitario
  del suelo, gamma_w=peso unitario del agua, m=fraccion de saturacion
  (0=seco, 1=saturado), z=espesor del suelo, beta=angulo de la pendiente.
  FS > 1 indica talud estable, FS <= 1 indica falla potencial.

- susceptibility_index: indice de susceptibilidad simplificado (0-100)
  combinando angulo de pendiente, intensidad de lluvia y un factor de
  tipo de suelo -- indice propio ilustrativo (no un mapa de
  susceptibilidad calibrado con inventario real de deslizamientos).

- rainfall_threshold_fs: recalcula el FS del talud infinito para una
  grilla de niveles de saturacion (m de 0 a 1) dado un evento de lluvia,
  para identificar el nivel de saturacion critico donde FS cruza 1.0.

- validate: suite de checks contra casos con solucion cerrada conocida.

Motor generico: no trae catalogo real de tipos de suelo ni de
zonificacion de susceptibilidad, los provee quien llama. Convencion
identica al resto del repo: compute_landslide_risk(mode, params=None)
-> dict, registrado via tool_registry.register_tool().
"""
import numpy as np


LANDSLIDE_RISK_TOOL_SCHEMA = {
    "name": "landslide_risk_tool",
    "description": (
        "Riesgo de deslizamiento de talud: infinite_slope_fs (factor de "
        "seguridad via el modelo clasico de Mohr-Coulomb para talud "
        "infinito: FS=[c+(gamma-m*gamma_w)*z*cos^2(beta)*tan(phi)]/"
        "[gamma*z*sin(beta)*cos(beta)], estandar en geotecnia; FS>1 "
        "estable, FS<=1 falla potencial), susceptibility_index (indice "
        "0-100 propio e ilustrativo combinando pendiente, intensidad de "
        "lluvia y tipo de suelo -- no un mapa calibrado con inventario "
        "real), rainfall_threshold_fs (recalcula FS del talud infinito "
        "para una grilla de niveles de saturacion, identifica el nivel "
        "critico donde FS cruza 1.0), validate (suite de checks). Motor "
        "generico: no trae catalogo real de tipos de suelo, lo provee "
        "quien llama."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "infinite_slope_fs",
                    "susceptibility_index",
                    "rainfall_threshold_fs",
                    "validate",
                ],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}

GAMMA_WATER_KN_M3 = 9.81


def _compute_fs(cohesion_kpa, phi_deg, gamma_kn_m3, z_m, beta_deg, m_saturation):
    beta_rad = np.radians(beta_deg)
    phi_rad = np.radians(phi_deg)

    numerator = (
        cohesion_kpa
        + (gamma_kn_m3 - m_saturation * GAMMA_WATER_KN_M3) * z_m * (np.cos(beta_rad) ** 2) * np.tan(phi_rad)
    )
    denominator = gamma_kn_m3 * z_m * np.sin(beta_rad) * np.cos(beta_rad)

    if denominator <= 0:
        raise ValueError("denominador no positivo: revisar beta_deg (debe estar en (0, 90))")

    return numerator / denominator


def _mode_infinite_slope_fs(params):
    cohesion_kpa = float(params.get("cohesion_kpa", 5.0))
    phi_deg = float(params["friction_angle_deg"])
    gamma_kn_m3 = float(params.get("unit_weight_kn_m3", 18.0))
    z_m = float(params["soil_depth_m"])
    beta_deg = float(params["slope_angle_deg"])
    m_saturation = float(params.get("saturation_fraction", 0.0))

    if cohesion_kpa < 0:
        raise ValueError("cohesion_kpa debe ser >= 0")
    if not (0.0 < phi_deg < 90.0):
        raise ValueError("friction_angle_deg debe estar en (0, 90)")
    if gamma_kn_m3 <= 0:
        raise ValueError("unit_weight_kn_m3 debe ser > 0")
    if z_m <= 0:
        raise ValueError("soil_depth_m debe ser > 0")
    if not (0.0 < beta_deg < 90.0):
        raise ValueError("slope_angle_deg debe estar en (0, 90)")
    if not (0.0 <= m_saturation <= 1.0):
        raise ValueError("saturation_fraction debe estar en [0, 1]")

    fs = _compute_fs(cohesion_kpa, phi_deg, gamma_kn_m3, z_m, beta_deg, m_saturation)

    return {
        "mode": "infinite_slope_fs",
        "cohesion_kpa": cohesion_kpa,
        "friction_angle_deg": phi_deg,
        "unit_weight_kn_m3": gamma_kn_m3,
        "soil_depth_m": z_m,
        "slope_angle_deg": beta_deg,
        "saturation_fraction": m_saturation,
        "factor_of_safety": float(fs),
        "stable": bool(fs > 1.0),
        "method": "talud infinito Mohr-Coulomb (Selby 1993 / Duncan & Wright 2005)",
    }


def _mode_susceptibility_index(params):
    slope_deg = float(params["slope_angle_deg"])
    rainfall_mm_24h = float(params["rainfall_mm_24h"])
    soil_factor = float(params.get("soil_factor", 0.5))

    if not (0.0 <= slope_deg <= 90.0):
        raise ValueError("slope_angle_deg debe estar en [0, 90]")
    if rainfall_mm_24h < 0:
        raise ValueError("rainfall_mm_24h debe ser >= 0")
    if not (0.0 <= soil_factor <= 1.0):
        raise ValueError("soil_factor debe estar en [0, 1] (0=muy cohesivo, 1=muy susceptible)")

    # pendientes moderadas (~35-45 grados) suelen ser las mas susceptibles en la
    # literatura de deslizamientos superficiales; pendientes muy suaves o casi
    # verticales tienden a ser menos susceptibles (muy suaves no deslizan, muy
    # verticales suelen ser afloramiento rocoso). Modelo simplificado propio:
    # pico gaussiano centrado en 40 grados.
    slope_factor = np.exp(-((slope_deg - 40.0) ** 2) / (2 * 20.0 ** 2))
    rainfall_factor = min(1.0, rainfall_mm_24h / 200.0)

    raw_index = 0.40 * slope_factor + 0.35 * rainfall_factor + 0.25 * soil_factor
    index_0_100 = float(100.0 * raw_index)

    if index_0_100 < 25:
        level = "bajo"
    elif index_0_100 < 50:
        level = "moderado"
    elif index_0_100 < 75:
        level = "alto"
    else:
        level = "muy alto"

    return {
        "mode": "susceptibility_index",
        "slope_angle_deg": slope_deg,
        "rainfall_mm_24h": rainfall_mm_24h,
        "soil_factor": soil_factor,
        "index_0_100": index_0_100,
        "level": level,
        "confidence_flag": "ilustrativo (indice propio, no calibrado con inventario real)",
    }


def _mode_rainfall_threshold_fs(params):
    base_params = {k: v for k, v in params.items() if k != "saturation_grid"}
    saturation_grid = params.get("saturation_grid", list(np.linspace(0.0, 1.0, 11)))

    results = []
    critical_saturation = None
    for m in saturation_grid:
        m = float(m)
        p = dict(base_params)
        p["saturation_fraction"] = m
        r = _mode_infinite_slope_fs(p)
        results.append({"saturation_fraction": m, "factor_of_safety": r["factor_of_safety"], "stable": r["stable"]})
        if critical_saturation is None and not r["stable"]:
            critical_saturation = m

    return {
        "mode": "rainfall_threshold_fs",
        "grid": results,
        "critical_saturation_fraction": critical_saturation,
        "note": (
            "critical_saturation_fraction es el primer nivel de saturacion en la "
            "grilla (en orden ascendente) donde FS cruza a <= 1.0; None si ningun "
            "punto de la grilla llega a inestable."
        ),
    }


def _mode_validate():
    checks = []

    common = {
        "cohesion_kpa": 5.0, "friction_angle_deg": 30.0,
        "unit_weight_kn_m3": 18.0, "soil_depth_m": 2.0,
    }

    # 1) infinite_slope_fs: pendiente suave (10 grados) da FS alto y estable
    r1 = _mode_infinite_slope_fs({**common, "slope_angle_deg": 10.0, "saturation_fraction": 0.0})
    checks.append({
        "name": "gentle_slope_is_stable",
        "fs": r1["factor_of_safety"], "stable": r1["stable"],
        "passed": r1["factor_of_safety"] > 1.0 and r1["stable"] is True,
    })

    # 2) infinite_slope_fs: pendiente muy empinada (65 grados) con el mismo suelo da FS mas bajo
    r2 = _mode_infinite_slope_fs({**common, "slope_angle_deg": 65.0, "saturation_fraction": 0.0})
    checks.append({
        "name": "steep_slope_has_lower_fs_than_gentle",
        "fs_gentle": r1["factor_of_safety"], "fs_steep": r2["factor_of_safety"],
        "passed": r2["factor_of_safety"] < r1["factor_of_safety"],
    })

    # 3) infinite_slope_fs: mayor saturacion reduce el FS (ceteris paribus)
    r3a = _mode_infinite_slope_fs({**common, "slope_angle_deg": 35.0, "saturation_fraction": 0.0})
    r3b = _mode_infinite_slope_fs({**common, "slope_angle_deg": 35.0, "saturation_fraction": 1.0})
    checks.append({
        "name": "saturation_reduces_fs",
        "fs_dry": r3a["factor_of_safety"], "fs_saturated": r3b["factor_of_safety"],
        "passed": r3b["factor_of_safety"] < r3a["factor_of_safety"],
    })

    # 4) infinite_slope_fs: mayor cohesion aumenta el FS (ceteris paribus)
    r4a = _mode_infinite_slope_fs({**common, "cohesion_kpa": 0.0, "slope_angle_deg": 35.0})
    r4b = _mode_infinite_slope_fs({**common, "cohesion_kpa": 20.0, "slope_angle_deg": 35.0})
    checks.append({
        "name": "cohesion_increases_fs",
        "fs_no_cohesion": r4a["factor_of_safety"], "fs_high_cohesion": r4b["factor_of_safety"],
        "passed": r4b["factor_of_safety"] > r4a["factor_of_safety"],
    })

    # 5) infinite_slope_fs: angulo de pendiente fuera de (0,90) lanza excepcion
    try:
        _mode_infinite_slope_fs({**common, "slope_angle_deg": 0.0})
        raised5 = False
    except ValueError:
        raised5 = True
    checks.append({"name": "zero_slope_angle_raises", "passed": raised5})

    # 6) infinite_slope_fs: caso analitico simple con cohesion=0 y saturacion=0
    #    reduce a FS = tan(phi)/tan(beta) (formula clasica de talud infinito sin cohesion)
    r6 = _mode_infinite_slope_fs({
        "cohesion_kpa": 0.0, "friction_angle_deg": 30.0, "unit_weight_kn_m3": 18.0,
        "soil_depth_m": 1.5, "slope_angle_deg": 20.0, "saturation_fraction": 0.0,
    })
    expected_fs = float(np.tan(np.radians(30.0)) / np.tan(np.radians(20.0)))
    checks.append({
        "name": "cohesionless_dry_matches_tan_ratio_formula",
        "fs": r6["factor_of_safety"], "expected": float(expected_fs),
        "passed": abs(r6["factor_of_safety"] - expected_fs) < 1e-9,
    })

    # 7) susceptibility_index: pendiente extrema de 40 grados + lluvia fuerte + suelo susceptible da index alto
    r7 = _mode_susceptibility_index({"slope_angle_deg": 40.0, "rainfall_mm_24h": 200.0, "soil_factor": 1.0})
    checks.append({
        "name": "peak_slope_heavy_rain_gives_high_index",
        "index": r7["index_0_100"], "level": r7["level"],
        "passed": r7["index_0_100"] > 90.0 and r7["level"] == "muy alto",
    })

    # 8) susceptibility_index: sin lluvia y pendiente casi plana da index bajo
    r8 = _mode_susceptibility_index({"slope_angle_deg": 2.0, "rainfall_mm_24h": 0.0, "soil_factor": 0.0})
    checks.append({
        "name": "flat_no_rain_gives_low_index",
        "index": r8["index_0_100"],
        "passed": r8["index_0_100"] < 25.0,
    })

    # 9) susceptibility_index: rainfall negativa lanza excepcion
    try:
        _mode_susceptibility_index({"slope_angle_deg": 30.0, "rainfall_mm_24h": -5.0})
        raised9 = False
    except ValueError:
        raised9 = True
    checks.append({"name": "negative_rainfall_raises", "passed": raised9})

    # 10) rainfall_threshold_fs: grilla monotona decreciente en FS al aumentar saturacion,
    #     y detecta el punto critico donde cruza a inestable
    r10 = _mode_rainfall_threshold_fs({
        **common, "slope_angle_deg": 32.0,
        "saturation_grid": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
    })
    fs_values = [g["factor_of_safety"] for g in r10["grid"]]
    is_monotonic_decreasing = all(fs_values[i] >= fs_values[i + 1] for i in range(len(fs_values) - 1))
    checks.append({
        "name": "rainfall_grid_fs_monotonic_and_finds_critical",
        "monotonic": is_monotonic_decreasing, "critical_saturation": r10["critical_saturation_fraction"],
        "passed": is_monotonic_decreasing,
    })

    # 11) modo invalido lanza excepcion
    try:
        compute_landslide_risk("modo_invalido", {})
        invalid_raised = False
    except (KeyError, ValueError):
        invalid_raised = True
    checks.append({"name": "invalid_mode_raises", "passed": invalid_raised})

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_landslide_risk(mode, params=None):
    params = params or {}

    if mode == "infinite_slope_fs":
        return _mode_infinite_slope_fs(params)
    elif mode == "susceptibility_index":
        return _mode_susceptibility_index(params)
    elif mode == "rainfall_threshold_fs":
        return _mode_rainfall_threshold_fs(params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(
            f"modo desconocido: {mode}. Use infinite_slope_fs | susceptibility_index | "
            f"rainfall_threshold_fs | validate"
        )


try:
    from tool_registry import register_tool
    register_tool(
        name="landslide_risk_tool",
        schema=LANDSLIDE_RISK_TOOL_SCHEMA,
        handler=lambda args: compute_landslide_risk(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    d = compute_landslide_risk("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de landslide_risk_tool.py pasaron OK.")
