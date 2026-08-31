"""
drug_delivery_poiseuille_tool.py

Modelo de liberacion de farmaco a caudal constante a traves de un capilar
calibrado, via la ley de Poiseuille (flujo laminar en tubo cilindrico).
Motivado por el mecanismo de administracion de medicacion descrito en
Losa Zapico, P. "Diseno de una protesis liviana de cadera con la
posibilidad de incorporar medicacion" (TFG UPM 2018): un reservorio
elastomerico tipo globo mantiene presion constante sobre el fluido a
medida que se vacia, por lo que el caudal de salida por el capilar es
constante (no depende del volumen remanente). La ley de Poiseuille en si
es fisica estandar (no propietaria del TFG); el TFG aporta el caso de uso
(reservorio de presion constante + capilar calibrado + protesis hueca).

Patron: compute_drug_delivery_poiseuille_tool(mode, **kwargs) + SCHEMA
Auto-registro via register_tool.

Ley de Poiseuille: Q = (pi * r^4 * delta_p) / (8 * mu * L)
  Q       : caudal volumetrico [m^3/s]
  r       : radio interno del capilar [m]
  delta_p : caida de presion a lo largo del capilar [Pa]
  mu      : viscosidad dinamica del fluido [Pa*s]
  L       : longitud del capilar [m]

Modos:
  - flow_rate           : calcula Q dado r, delta_p, mu, L
  - solve_radius         : despeja r dado Q objetivo, delta_p, mu, L
  - reservoir_depletion   : tiempo de vaciado de un reservorio a caudal constante
  - capillary_design      : combina flow_rate + reservoir_depletion en una sola llamada
  - validate               : autotest
"""

import math

try:
    from tool_registry import register_tool
except ImportError:
    register_tool = None


def _flow_rate_m3s(radius_m, delta_p_pa, viscosity_pa_s, length_m):
    if radius_m <= 0 or length_m <= 0:
        raise ValueError("radius_m y length_m deben ser > 0")
    if viscosity_pa_s <= 0:
        raise ValueError("viscosity_pa_s debe ser > 0")
    if delta_p_pa < 0:
        raise ValueError("delta_p_pa debe ser >= 0")
    return (math.pi * (radius_m ** 4) * delta_p_pa) / (8.0 * viscosity_pa_s * length_m)


def _flow_rate(radius_mm, delta_p_kpa, viscosity_mpa_s, length_mm):
    radius_m = radius_mm / 1000.0
    length_m = length_mm / 1000.0
    delta_p_pa = delta_p_kpa * 1000.0
    viscosity_pa_s = viscosity_mpa_s / 1000.0  # mPa*s -> Pa*s (agua ~1 mPa*s a 20C)
    Q_m3s = _flow_rate_m3s(radius_m, delta_p_pa, viscosity_pa_s, length_m)
    Q_ml_s = Q_m3s * 1e6
    return {
        "radius_mm": radius_mm,
        "delta_p_kpa": delta_p_kpa,
        "viscosity_mpa_s": viscosity_mpa_s,
        "length_mm": length_mm,
        "flow_rate_m3_s": Q_m3s,
        "flow_rate_ml_s": Q_ml_s,
        "flow_rate_ml_h": Q_ml_s * 3600.0,
        "flow_rate_ml_day": Q_ml_s * 86400.0,
    }


def _solve_radius(target_flow_rate_ml_h, delta_p_kpa, viscosity_mpa_s, length_mm):
    if target_flow_rate_ml_h <= 0:
        raise ValueError("target_flow_rate_ml_h debe ser > 0")
    Q_m3s = (target_flow_rate_ml_h / 1e6) / 3600.0
    length_m = length_mm / 1000.0
    delta_p_pa = delta_p_kpa * 1000.0
    viscosity_pa_s = viscosity_mpa_s / 1000.0
    if delta_p_pa <= 0:
        raise ValueError("delta_p_kpa debe ser > 0 para despejar el radio")
    r4 = (Q_m3s * 8.0 * viscosity_pa_s * length_m) / (math.pi * delta_p_pa)
    radius_m = r4 ** 0.25
    radius_mm = radius_m * 1000.0
    return {
        "target_flow_rate_ml_h": target_flow_rate_ml_h,
        "delta_p_kpa": delta_p_kpa,
        "viscosity_mpa_s": viscosity_mpa_s,
        "length_mm": length_mm,
        "required_radius_mm": radius_mm,
        "required_diameter_mm": radius_mm * 2.0,
    }


def _reservoir_depletion(reservoir_volume_ml, flow_rate_ml_h):
    if reservoir_volume_ml <= 0:
        raise ValueError("reservoir_volume_ml debe ser > 0")
    if flow_rate_ml_h <= 0:
        raise ValueError("flow_rate_ml_h debe ser > 0")
    time_h = reservoir_volume_ml / flow_rate_ml_h
    return {
        "reservoir_volume_ml": reservoir_volume_ml,
        "flow_rate_ml_h": flow_rate_ml_h,
        "depletion_time_h": time_h,
        "depletion_time_days": time_h / 24.0,
        "note": "asume caudal constante en el tiempo (reservorio elastomerico tipo globo a presion constante, no jeringa rigida)",
    }


def _capillary_design(radius_mm, delta_p_kpa, viscosity_mpa_s, length_mm, reservoir_volume_ml):
    fr = _flow_rate(radius_mm, delta_p_kpa, viscosity_mpa_s, length_mm)
    dep = _reservoir_depletion(reservoir_volume_ml, fr["flow_rate_ml_h"])
    return {**fr, **dep}


def _validate():
    checks = []

    # Caso 1: agua (mu=1 mPa*s) por un capilar de 0.1mm radio, 10mm largo, deltaP=10kPa
    # comparar contra calculo directo en SI
    r = _flow_rate(radius_mm=0.1, delta_p_kpa=10.0, viscosity_mpa_s=1.0, length_mm=10.0)
    expected_Q = _flow_rate_m3s(0.1e-3, 10000.0, 1e-3, 10e-3)
    ok1 = abs(r["flow_rate_m3_s"] - expected_Q) < 1e-15
    checks.append(("flow_rate_matches_direct_SI_calc", ok1))

    # Caso 2: Q escala como r^4 -- duplicar r debe multiplicar Q por 16
    r_a = _flow_rate(radius_mm=0.1, delta_p_kpa=10.0, viscosity_mpa_s=1.0, length_mm=10.0)
    r_b = _flow_rate(radius_mm=0.2, delta_p_kpa=10.0, viscosity_mpa_s=1.0, length_mm=10.0)
    ratio = r_b["flow_rate_m3_s"] / r_a["flow_rate_m3_s"]
    ok2 = abs(ratio - 16.0) < 1e-6
    checks.append(("flow_rate_scales_r4", ok2))

    # Caso 3: Q escala linealmente con delta_p
    r_c = _flow_rate(radius_mm=0.1, delta_p_kpa=20.0, viscosity_mpa_s=1.0, length_mm=10.0)
    ratio2 = r_c["flow_rate_m3_s"] / r_a["flow_rate_m3_s"]
    ok3 = abs(ratio2 - 2.0) < 1e-6
    checks.append(("flow_rate_scales_linear_deltap", ok3))

    # Caso 4: solve_radius es la inversa de flow_rate (round-trip)
    fr = _flow_rate(radius_mm=0.15, delta_p_kpa=15.0, viscosity_mpa_s=1.2, length_mm=8.0)
    sr = _solve_radius(fr["flow_rate_ml_h"], delta_p_kpa=15.0, viscosity_mpa_s=1.2, length_mm=8.0)
    ok4 = abs(sr["required_radius_mm"] - 0.15) < 1e-6
    checks.append(("solve_radius_inverts_flow_rate", ok4))

    # Caso 5: reservoir_depletion -- volumen/caudal, chequeo directo
    dep = _reservoir_depletion(reservoir_volume_ml=10.0, flow_rate_ml_h=0.5)
    ok5 = abs(dep["depletion_time_h"] - 20.0) < 1e-9
    checks.append(("reservoir_depletion_time_calc", ok5))

    # Caso 6: capillary_design combina ambos correctamente
    cd = _capillary_design(radius_mm=0.1, delta_p_kpa=10.0, viscosity_mpa_s=1.0, length_mm=10.0, reservoir_volume_ml=5.0)
    ok6 = abs(cd["depletion_time_h"] - (5.0 / cd["flow_rate_ml_h"])) < 1e-9
    checks.append(("capillary_design_consistency", ok6))

    passed = sum(1 for _, ok in checks if ok)
    return {
        "mode": "validate",
        "checks": [{"name": n, "passed": ok} for n, ok in checks],
        "passed": passed,
        "total": len(checks),
        "all_passed": passed == len(checks),
    }


DRUG_DELIVERY_POISEUILLE_TOOL_SCHEMA = {
    "name": "drug_delivery_poiseuille_tool",
    "description": (
        "Modelo de liberacion de farmaco a caudal constante por un capilar calibrado, via la "
        "ley de Poiseuille (Q = pi*r^4*deltaP / (8*mu*L)), para un reservorio elastomerico tipo "
        "globo que mantiene presion constante sobre el fluido a medida que se vacia (caso de uso "
        "motivado por TFG Losa Zapico UPM 2018, protesis de cadera con reservorio interno). "
        "flow_rate calcula el caudal dado el capilar; solve_radius despeja el radio necesario "
        "para un caudal objetivo; reservoir_depletion da el tiempo de vaciado; capillary_design "
        "combina ambos. Flujo laminar, fluido newtoniano -- no valido si Reynolds es alto o el "
        "fluido es no-newtoniano."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["flow_rate", "solve_radius", "reservoir_depletion", "capillary_design", "validate"],
                "description": "Operacion a realizar, o 'validate' para autotest",
            },
            "radius_mm": {"type": "number", "description": "flow_rate/capillary_design: radio interno del capilar, mm"},
            "delta_p_kpa": {"type": "number", "description": "flow_rate/solve_radius/capillary_design: caida de presion a lo largo del capilar, kPa"},
            "viscosity_mpa_s": {"type": "number", "description": "viscosidad dinamica del fluido, mPa*s (agua ~1.0 a 20C)"},
            "length_mm": {"type": "number", "description": "longitud del capilar, mm"},
            "target_flow_rate_ml_h": {"type": "number", "description": "solve_radius: caudal objetivo, mL/h"},
            "reservoir_volume_ml": {"type": "number", "description": "reservoir_depletion/capillary_design: volumen del reservorio, mL"},
            "flow_rate_ml_h": {"type": "number", "description": "reservoir_depletion: caudal ya conocido, mL/h (si no se calcula desde el capilar)"},
        },
        "required": ["mode"],
    },
}


def compute_drug_delivery_poiseuille_tool(mode, **kwargs):
    if mode == "validate":
        return _validate()
    elif mode == "flow_rate":
        req = ["radius_mm", "delta_p_kpa", "viscosity_mpa_s", "length_mm"]
        missing = [k for k in req if kwargs.get(k) is None]
        if missing:
            raise ValueError(f"flow_rate requiere: {missing}")
        return {"mode": mode, **_flow_rate(*(float(kwargs[k]) for k in req))}
    elif mode == "solve_radius":
        req = ["target_flow_rate_ml_h", "delta_p_kpa", "viscosity_mpa_s", "length_mm"]
        missing = [k for k in req if kwargs.get(k) is None]
        if missing:
            raise ValueError(f"solve_radius requiere: {missing}")
        return {"mode": mode, **_solve_radius(*(float(kwargs[k]) for k in req))}
    elif mode == "reservoir_depletion":
        if kwargs.get("reservoir_volume_ml") is None or kwargs.get("flow_rate_ml_h") is None:
            raise ValueError("reservoir_depletion requiere 'reservoir_volume_ml' y 'flow_rate_ml_h'")
        return {"mode": mode, **_reservoir_depletion(float(kwargs["reservoir_volume_ml"]), float(kwargs["flow_rate_ml_h"]))}
    elif mode == "capillary_design":
        req = ["radius_mm", "delta_p_kpa", "viscosity_mpa_s", "length_mm", "reservoir_volume_ml"]
        missing = [k for k in req if kwargs.get(k) is None]
        if missing:
            raise ValueError(f"capillary_design requiere: {missing}")
        return {"mode": mode, **_capillary_design(*(float(kwargs[k]) for k in req))}
    else:
        raise ValueError(f"Modo desconocido: {mode}")


if __name__ == "__main__":
    import json
    print(json.dumps(compute_drug_delivery_poiseuille_tool(mode="validate"), indent=2, ensure_ascii=False))


try:
    from tool_registry import register_tool as _register_tool_real
    _register_tool_real(
        name="drug_delivery_poiseuille_tool",
        schema=DRUG_DELIVERY_POISEUILLE_TOOL_SCHEMA,
        handler=lambda args: compute_drug_delivery_poiseuille_tool(
            args.get("mode"),
            **{k: v for k, v in args.items() if k != "mode"}
        ),
    )
except ImportError:
    pass
