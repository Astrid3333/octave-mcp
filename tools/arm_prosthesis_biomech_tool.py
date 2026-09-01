"""
arm_prosthesis_biomech_tool.py

Analisis biomecanico para diseno de protesis de brazo transradial:
cargas en codo/muneca, seleccion de material, presion de contacto
socket-munon, cinematica de linkage de codo, y factor de seguridad.

Sigue el patron de octave-mcp: self-registro via tool_registry al final
del archivo (try/except ImportError), dispatcher
compute_arm_prosthesis_biomech_tool(mode=..., **kwargs), y _validate()
que devuelve 'validation_passed' (nombre exacto que exige
run_all_validations.py).
"""

import math

import numpy as np

ARM_PROSTHESIS_BIOMECH_TOOL_SCHEMA = {
    "name": "arm_prosthesis_biomech_tool",
    "description": "Analisis biomecanico para diseno de protesis de brazo transradial: cargas en codo/muneca, seleccion de material, presion de contacto socket-munon, cinematica de linkage de codo, y factor de seguridad.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "load_analysis",
                    "material_selection",
                    "socket_contact_pressure",
                    "elbow_linkage_kinematics",
                    "safety_factor",
                    "validate",
                ],
            },
        },
        "required": ["mode"],
    },
}

GRAVITY = 9.81  # m/s^2

# Base de materiales candidatos para componentes estructurales de protesis
# transradial (fuente: valores tipicos de literatura de ingenieria, no
# certificados para uso clinico -- placeholder de diseno preliminar).
MATERIAL_DB = {
    "ti6al4v": {
        "name": "Titanio Ti-6Al-4V",
        "yield_mpa": 880.0,
        "density_kg_m3": 4430.0,
        "cost_relative": 8.0,
    },
    "al7075_t6": {
        "name": "Aluminio 7075-T6",
        "yield_mpa": 503.0,
        "density_kg_m3": 2810.0,
        "cost_relative": 3.0,
    },
    "carbon_fiber_composite": {
        "name": "Composite de fibra de carbono (epoxy, laminado unidireccional)",
        "yield_mpa": 600.0,
        "density_kg_m3": 1600.0,
        "cost_relative": 6.0,
    },
    "nylon_pa12": {
        "name": "Nylon PA12 (SLS)",
        "yield_mpa": 48.0,
        "density_kg_m3": 1010.0,
        "cost_relative": 1.5,
    },
    "petg": {
        "name": "PETG (FDM)",
        "yield_mpa": 33.0,
        "density_kg_m3": 1270.0,
        "cost_relative": 1.0,
    },
    "delrin_pom": {
        "name": "Delrin / POM-C",
        "yield_mpa": 65.0,
        "density_kg_m3": 1410.0,
        "cost_relative": 2.0,
    },
}


def _load_analysis(
    payload_mass_kg=2.0,
    forearm_length_m=0.25,
    grip_offset_m=0.0,
    prosthesis_mass_kg=0.35,
    dynamic_factor=1.0,
):
    """
    Estatica simple de una protesis transradial modelada como viga en
    voladizo: el socket (interfaz proximal, 'codo') es el empotramiento,
    y la carga (objeto sostenido) se aplica en el dispositivo terminal
    ('mano'), a distancia forearm_length_m + grip_offset_m del socket.

    dynamic_factor amplifica la carga estatica para aproximar cargas de
    impacto/aceleracion (ej. 2.0-2.5x tipico en diseno de protesis para
    actividades dinamicas; 1.0 = solo estatico).
    """
    lever_arm_m = forearm_length_m + grip_offset_m
    payload_force_n = payload_mass_kg * GRAVITY * dynamic_factor
    self_weight_force_n = prosthesis_mass_kg * GRAVITY

    # Momento en el socket: carga en la punta + peso propio actuando en
    # el centroide del antebrazo protesico (aprox. L/2)
    socket_moment_nm = (payload_force_n * lever_arm_m) + (
        self_weight_force_n * (forearm_length_m / 2.0)
    )
    socket_shear_n = payload_force_n + self_weight_force_n

    return {
        "inputs": {
            "payload_mass_kg": payload_mass_kg,
            "forearm_length_m": forearm_length_m,
            "grip_offset_m": grip_offset_m,
            "prosthesis_mass_kg": prosthesis_mass_kg,
            "dynamic_factor": dynamic_factor,
        },
        "lever_arm_m": lever_arm_m,
        "payload_force_n": payload_force_n,
        "self_weight_force_n": self_weight_force_n,
        "socket_shear_force_n": socket_shear_n,
        "socket_bending_moment_nm": socket_moment_nm,
    }


def _material_selection(
    required_yield_mpa=50.0,
    max_mass_kg=None,
    part_volume_cm3=50.0,
    candidates=None,
    safety_margin=1.5,
):
    """
    Filtra y rankea materiales candidatos por resistencia especifica
    (yield / densidad) entre los que cumplen required_yield_mpa * safety_margin
    y, si se da max_mass_kg, el limite de masa de la pieza dado su volumen.
    """
    pool = candidates if candidates else list(MATERIAL_DB.keys())
    min_yield = required_yield_mpa * safety_margin
    volume_m3 = part_volume_cm3 * 1e-6

    scored = []
    for key in pool:
        if key not in MATERIAL_DB:
            continue
        mat = MATERIAL_DB[key]
        part_mass_kg = mat["density_kg_m3"] * volume_m3
        meets_strength = mat["yield_mpa"] >= min_yield
        meets_mass = True if max_mass_kg is None else part_mass_kg <= max_mass_kg
        specific_strength = mat["yield_mpa"] / mat["density_kg_m3"] * 1000.0  # (MPa*m^3)/kg -> escalado

        scored.append(
            {
                "material_key": key,
                "name": mat["name"],
                "yield_mpa": mat["yield_mpa"],
                "density_kg_m3": mat["density_kg_m3"],
                "cost_relative": mat["cost_relative"],
                "estimated_part_mass_kg": round(part_mass_kg, 4),
                "specific_strength_score": round(specific_strength, 2),
                "meets_strength_requirement": meets_strength,
                "meets_mass_requirement": meets_mass,
                "eligible": meets_strength and meets_mass,
            }
        )

    eligible = [c for c in scored if c["eligible"]]
    eligible.sort(key=lambda c: (-c["specific_strength_score"], c["cost_relative"]))
    scored.sort(key=lambda c: (-c["eligible"], -c["specific_strength_score"]))

    return {
        "required_yield_mpa": required_yield_mpa,
        "safety_margin": safety_margin,
        "min_yield_required_mpa": min_yield,
        "max_mass_kg": max_mass_kg,
        "part_volume_cm3": part_volume_cm3,
        "candidates_evaluated": scored,
        "recommended": eligible[0] if eligible else None,
        "n_eligible": len(eligible),
    }


def _socket_contact_pressure(
    axial_load_n=250.0,
    contact_area_cm2=180.0,
    pressure_distribution="uniform",
    peak_factor=1.4,
    tissue_pressure_limit_kpa=200.0,
):
    """
    Presion de contacto socket-munon. 'uniform' asume carga distribuida
    parejo sobre el area de contacto total; 'peak_load_bearing' aplica un
    factor de concentracion (peak_factor) sobre zonas tolerantes a carga
    (ej. tendon patelar en transtibial, o superficies flexoras en
    transradial), consistente con la practica de diseno de sockets de
    no cargar uniformemente sino concentrar en zonas tolerantes.

    tissue_pressure_limit_kpa: umbral de referencia de literatura para
    tejido blando bajo carga sostenida (valor de diseno preliminar, no
    clinico).
    """
    contact_area_m2 = contact_area_cm2 * 1e-4
    if contact_area_m2 <= 0:
        raise ValueError("contact_area_cm2 debe ser > 0")

    mean_pressure_pa = axial_load_n / contact_area_m2
    mean_pressure_kpa = mean_pressure_pa / 1000.0

    if pressure_distribution == "peak_load_bearing":
        peak_pressure_kpa = mean_pressure_kpa * peak_factor
    elif pressure_distribution == "uniform":
        peak_pressure_kpa = mean_pressure_kpa
    else:
        raise ValueError(
            f"pressure_distribution desconocida: {pressure_distribution} "
            "(usar 'uniform' o 'peak_load_bearing')"
        )

    exceeds_limit = peak_pressure_kpa > tissue_pressure_limit_kpa
    margin_ratio = tissue_pressure_limit_kpa / peak_pressure_kpa if peak_pressure_kpa > 0 else float("inf")

    return {
        "inputs": {
            "axial_load_n": axial_load_n,
            "contact_area_cm2": contact_area_cm2,
            "pressure_distribution": pressure_distribution,
            "peak_factor": peak_factor,
            "tissue_pressure_limit_kpa": tissue_pressure_limit_kpa,
        },
        "mean_pressure_kpa": round(mean_pressure_kpa, 2),
        "peak_pressure_kpa": round(peak_pressure_kpa, 2),
        "exceeds_tissue_limit": exceeds_limit,
        "margin_ratio": round(margin_ratio, 3),
    }


def _elbow_linkage_kinematics(
    crank_length_m=0.04,
    coupler_length_m=0.10,
    rocker_length_m=0.05,
    ground_length_m=0.09,
    crank_angle_start_deg=0.0,
    crank_angle_end_deg=120.0,
    n_steps=13,
):
    """
    Cinematica de posicion de un four-bar Grashof estandar (metodo de
    Freudenstein) para el linkage de flexion de codo protesico: eslabon
    fijo (ground, ej. estructura del codo), manivela (crank, actuada por
    cable/motor), acoplador (coupler) y balancin (rocker, conectado al
    antebrazo terminal).

    Devuelve el angulo de salida (rocker, proxy del angulo de flexion
    del antebrazo) para cada angulo de entrada del crank, via solucion
    cerrada de la ecuacion de Freudenstein.
    """
    L1, L2, L3, L4 = ground_length_m, crank_length_m, coupler_length_m, rocker_length_m

    # Coeficientes de Freudenstein: K1*cos(theta4) - K2*cos(theta2) + K3 = cos(theta2-theta4)
    K1 = L1 / L2
    K2 = L1 / L4
    K3 = (L2 ** 2 - L3 ** 2 + L4 ** 2 + L1 ** 2) / (2 * L2 * L4)

    angles_deg = np.linspace(crank_angle_start_deg, crank_angle_end_deg, n_steps)
    samples = []
    unreachable = 0

    for theta2_deg in angles_deg:
        theta2 = math.radians(theta2_deg)
        A = math.cos(theta2) - K1 - K2 * math.cos(theta2) + K3
        B = -2.0 * math.sin(theta2)
        C = K1 - (K2 + 1.0) * math.cos(theta2) + K3

        disc = B ** 2 - 4.0 * A * C
        if disc < 0 or abs(A) < 1e-12:
            unreachable += 1
            samples.append(
                {"crank_angle_deg": round(float(theta2_deg), 2), "reachable": False}
            )
            continue

        # Rama "abierta" del mecanismo (solucion + de la cuadratica en tan(theta4/2))
        t4 = (-B + math.sqrt(disc)) / (2.0 * A)
        theta4 = 2.0 * math.atan(t4)
        theta4_deg = math.degrees(theta4) % 360.0

        samples.append(
            {
                "crank_angle_deg": round(float(theta2_deg), 2),
                "rocker_angle_deg": round(theta4_deg, 3),
                "reachable": True,
            }
        )

    reachable_angles = [s["rocker_angle_deg"] for s in samples if s["reachable"]]
    flexion_range_deg = (
        round(max(reachable_angles) - min(reachable_angles), 3)
        if reachable_angles
        else 0.0
    )

    return {
        "link_lengths_m": {
            "ground": L1,
            "crank": L2,
            "coupler": L3,
            "rocker": L4,
        },
        "grashof_condition": _grashof_check(L1, L2, L3, L4),
        "n_steps": n_steps,
        "n_unreachable": unreachable,
        "flexion_range_deg": flexion_range_deg,
        "samples": samples,
    }


def _grashof_check(L1, L2, L3, L4):
    lengths = sorted([L1, L2, L3, L4])
    s, p, q, ll = lengths[0], lengths[1], lengths[2], lengths[3]
    is_grashof = (s + ll) <= (p + q)
    return {"is_grashof": bool(is_grashof), "sum_shortest_longest": s + ll, "sum_other_two": p + q}


def _safety_factor(
    applied_stress_mpa=None,
    material_yield_mpa=None,
    load_case=None,
    material_key=None,
    minimum_recommended_sf=1.5,
):
    """
    Factor de seguridad estatico simple: SF = yield / applied_stress.
    Acepta valores directos (applied_stress_mpa, material_yield_mpa) o,
    alternativamente, un load_case dict pasado a _load_analysis junto con
    material_key + una section_modulus_m3 para derivar el esfuerzo de
    flexion desde el momento en el socket (M/Z).

    minimum_recommended_sf: referencia de diseno preliminar (no
    normativa clinica) para clasificar 'adequate' vs 'insufficient'.
    """
    if applied_stress_mpa is None:
        if load_case is None:
            raise ValueError(
                "se requiere applied_stress_mpa, o load_case (+ section_modulus_m3) para derivarlo"
            )
        section_modulus_m3 = load_case.pop("section_modulus_m3", None)
        if section_modulus_m3 is None or section_modulus_m3 <= 0:
            raise ValueError("load_case requiere section_modulus_m3 > 0 para derivar el esfuerzo")
        loads = _load_analysis(**load_case)
        applied_stress_pa = loads["socket_bending_moment_nm"] / section_modulus_m3
        applied_stress_mpa = applied_stress_pa / 1e6
    else:
        loads = None

    if material_yield_mpa is None:
        if material_key is None or material_key not in MATERIAL_DB:
            raise ValueError("se requiere material_yield_mpa o un material_key valido de MATERIAL_DB")
        material_yield_mpa = MATERIAL_DB[material_key]["yield_mpa"]

    if applied_stress_mpa <= 0:
        raise ValueError("applied_stress_mpa debe ser > 0")

    safety_factor = material_yield_mpa / applied_stress_mpa

    return {
        "applied_stress_mpa": round(applied_stress_mpa, 3),
        "material_yield_mpa": material_yield_mpa,
        "safety_factor": round(safety_factor, 3),
        "meets_minimum_recommended": safety_factor >= minimum_recommended_sf,
        "minimum_recommended_sf": minimum_recommended_sf,
        "derived_from_load_analysis": loads,
    }


def _validate():
    """Autochequeo con casos analiticos/de sentido comun conocidos."""
    checks = []

    # 1) Estatica: viga en voladizo sin peso propio, carga puntual en la punta.
    #    M = F * L es exacto -> verificar contra formula cerrada.
    la = _load_analysis(
        payload_mass_kg=1.0,
        forearm_length_m=0.2,
        grip_offset_m=0.0,
        prosthesis_mass_kg=0.0,
        dynamic_factor=1.0,
    )
    expected_moment = 1.0 * GRAVITY * 0.2
    checks.append(
        {
            "name": "load_analysis_momento_viga_voladizo_exacto",
            "passed": abs(la["socket_bending_moment_nm"] - expected_moment) < 1e-9,
        }
    )

    # 2) Seleccion de materiales: titanio debe superar a PETG en resistencia
    #    especifica, y ambos deben aparecer evaluados.
    ms = _material_selection(required_yield_mpa=20.0, part_volume_cm3=50.0, safety_margin=1.0)
    by_key = {c["material_key"]: c for c in ms["candidates_evaluated"]}
    checks.append(
        {
            "name": "material_selection_ti_supera_petg_en_resistencia_especifica",
            "passed": (
                "ti6al4v" in by_key
                and "petg" in by_key
                and by_key["ti6al4v"]["specific_strength_score"]
                > by_key["petg"]["specific_strength_score"]
            ),
        }
    )

    # 3) Presion de contacto: formula presion = fuerza / area (SI exacto).
    scp = _socket_contact_pressure(
        axial_load_n=100.0, contact_area_cm2=100.0, pressure_distribution="uniform"
    )
    expected_kpa = (100.0 / (100.0 * 1e-4)) / 1000.0  # = 1000 kPa
    checks.append(
        {
            "name": "socket_contact_pressure_formula_exacta",
            "passed": abs(scp["mean_pressure_kpa"] - expected_kpa) < 1e-6,
        }
    )

    # 4) Cinematica de linkage: mecanismo Grashof valido debe ser
    #    alcanzable (reachable) en todo el barrido de angulos de entrada.
    elk = _elbow_linkage_kinematics(
        crank_length_m=0.03,
        coupler_length_m=0.09,
        rocker_length_m=0.07,
        ground_length_m=0.10,
        crank_angle_start_deg=0.0,
        crank_angle_end_deg=90.0,
        n_steps=10,
    )
    checks.append(
        {
            "name": "elbow_linkage_grashof_valido_y_alcanzable",
            "passed": elk["grashof_condition"]["is_grashof"] and elk["n_unreachable"] == 0,
        }
    )

    # 5) Factor de seguridad: caso directo con valores conocidos -> SF exacto.
    sf = _safety_factor(applied_stress_mpa=100.0, material_yield_mpa=500.0)
    checks.append(
        {
            "name": "safety_factor_division_exacta",
            "passed": abs(sf["safety_factor"] - 5.0) < 1e-9,
        }
    )

    n_passed = sum(1 for c in checks if c["passed"])
    return {
        "validation_passed": n_passed == len(checks),
        "n_passed": n_passed,
        "n_checks": len(checks),
        "checks": checks,
    }


def compute_arm_prosthesis_biomech_tool(mode, **kwargs):
    if mode == "validate":
        return _validate()
    if mode == "load_analysis":
        return _load_analysis(**kwargs)
    if mode == "material_selection":
        return _material_selection(**kwargs)
    if mode == "socket_contact_pressure":
        return _socket_contact_pressure(**kwargs)
    if mode == "elbow_linkage_kinematics":
        return _elbow_linkage_kinematics(**kwargs)
    if mode == "safety_factor":
        return _safety_factor(**kwargs)

    raise ValueError(f"modo desconocido: {mode}")


def _register():
    try:
        import tool_registry
        tool_registry.register_tool(
            "arm_prosthesis_biomech_tool",
            ARM_PROSTHESIS_BIOMECH_TOOL_SCHEMA,
            lambda args: compute_arm_prosthesis_biomech_tool(
                args.get("mode"), **(args.get("params") or {})
            ),
        )
    except ImportError:
        pass


_register()

if __name__ == "__main__":
    import json
    result = _validate()
    print(json.dumps(
        {"validation_passed": result["validation_passed"],
          "n_passed": result["n_passed"], "n_checks": result["n_checks"]},
        indent=2,
    ))
