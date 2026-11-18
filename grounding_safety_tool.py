"""
grounding_safety_tool.py

Lo que faltaba de tierra: resistencia de contacto (constricción de Holm en
la unión conductor-terminal, más película superficial) y tensiones de paso y
contacto con el modelo de electrodo hemisférico, más límites tolerables
(IEEE 80, cuerpo de 50 y 70 kg).

SI: ohm, metros, Ω·m, A, V, s. Mismo patrón que los módulos anteriores:
compute + _handler + register_tool(name, schema, handler).

Modos: contact_resistance, step_touch, tolerable_limits, validate.
Nota: los coeficientes de IEEE 80 (0.157 y 0.116) deben verificarse con la
edición vigente antes de usarlos en un diseño real.
"""

import math

from tool_registry import register_tool

GROUNDING_SAFETY_TOOL_SCHEMA = {
    "name": "grounding_safety_tool",
    "description": (
        "Seguridad de puesta a tierra: resistencia de contacto (constricción de "
        "Holm y película superficial), tensiones de paso y contacto con electrodo "
        "hemisférico y límites tolerables IEEE 80. SI. "
        "Modos: contact_resistance, step_touch, tolerable_limits, validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string",
                     "enum": ["contact_resistance", "step_touch",
                              "tolerable_limits", "validate"]},
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


# ------------------------------------------------------- contact resistance
def holm_constriction_resistance(rho_m, contact_radius_m):
    """
    Resistencia de constricción de un contacto circular de radio a entre dos
    cuerpos del mismo material (Holm): R = rho/(2a).
    """
    if contact_radius_m <= 0:
        raise ValueError("contact_radius_m debe ser > 0")
    return rho_m / (2.0 * contact_radius_m)


def film_resistance(rho_film, film_thickness_m, contact_area_m2):
    """Película superficial (óxido, sulfuro): R = rho_f * t / A."""
    if contact_area_m2 <= 0:
        raise ValueError("contact_area_m2 debe ser > 0")
    return rho_film * film_thickness_m / contact_area_m2


def contact_resistance(rho_m, contact_radius_m, rho_film=None, film_thickness_m=0.0):
    """Constricción más película en paralelo con la constricción (ruta de corriente)."""
    r_c = holm_constriction_resistance(rho_m, contact_radius_m)
    out = {"R_constriction_ohm": r_c, "R_total_ohm": r_c}
    if rho_film is not None and film_thickness_m > 0:
        area = math.pi * contact_radius_m ** 2
        r_f = film_resistance(rho_film, film_thickness_m, area)
        out["R_film_ohm"] = r_f
        out["R_total_ohm"] = 1.0 / (1.0 / r_c + 1.0 / r_f)
    return out


# ------------------------------------------------------------- step / touch
def hemisphere_potential(rho_soil, current_a, distance_m, radius_m):
    """
    Electrodo hemisférico de radio a en suelo homogéneo:
      V(r) = rho*I/(2*pi*r)  para r >= a.  GPR = V(a).
    """
    if distance_m < radius_m:
        raise ValueError("la distancia debe ser >= radio del electrodo")
    return rho_soil * current_a / (2.0 * math.pi * distance_m)


def step_voltage(rho_soil, current_a, distance_m, radius_m, step_m=1.0):
    """Tensión de paso: V(r) - V(r + 1 m), con pies separados 1 m."""
    return (hemisphere_potential(rho_soil, current_a, distance_m, radius_m)
            - hemisphere_potential(rho_soil, current_a, distance_m + step_m, radius_m))


def touch_voltage(rho_soil, current_a, distance_m, radius_m):
    """Tensión de contacto: GPR - V(r), con la mano en el electrodo y pies a r."""
    gpr = hemisphere_potential(rho_soil, current_a, radius_m, radius_m)
    return gpr - hemisphere_potential(rho_soil, current_a, distance_m, radius_m)


def step_touch_report(rho_soil, current_a, distance_m, radius_m):
    gpr = hemisphere_potential(rho_soil, current_a, radius_m, radius_m)
    return {"GPR_V": gpr,
            "step_V": step_voltage(rho_soil, current_a, distance_m, radius_m),
            "touch_V": touch_voltage(rho_soil, current_a, distance_m, radius_m)}


# ------------------------------------------------------- tolerable (IEEE 80)
def tolerable_voltages(rho_surface, cs_factor, duration_s, body_kg=70):
    """
    IEEE 80 (forma de referencia): E = (1000 + 1.5*Cs*rho_s) * k / sqrt(t)
    con k = 0.157 para 70 kg y 0.116 para 50 kg. Verificar edición vigente.
    """
    if duration_s <= 0:
        raise ValueError("duration_s debe ser > 0")
    k = {70: 0.157, 50: 0.116}.get(body_kg)
    if k is None:
        raise ValueError("body_kg debe ser 50 o 70")
    base = 1000.0 + 1.5 * cs_factor * rho_surface
    return base * k / math.sqrt(duration_s)


# ----------------------------------------------------------------- handlers
def _mode_contact(p):
    return contact_resistance(p["rho_m"], p["contact_radius_m"],
                              p.get("rho_film"), p.get("film_thickness_m", 0.0))


def _mode_step_touch(p):
    return step_touch_report(p["rho_soil"], p["current_a"],
                             p["distance_m"], p["radius_m"])


def _mode_tolerable(p):
    return {"body_kg": p.get("body_kg", 70),
            "tolerable_V": tolerable_voltages(p["rho_surface"], p.get("cs_factor", 1.0),
                                              p["duration_s"], p.get("body_kg", 70))}


_MODES = {"contact_resistance": _mode_contact, "step_touch": _mode_step_touch,
          "tolerable_limits": _mode_tolerable}


def _mode_validate():
    checks = []

    def chk(name, ok, detail=""):
        checks.append({"name": name, "passed": bool(ok), "detail": detail})

    # 1. Holm: R = rho/(2a), con rho=1.68e-8, a=1e-3 -> 8.4e-6 Ω
    chk("Holm constricción", abs(holm_constriction_resistance(1.68e-8, 1e-3) - 8.4e-6) < 1e-12)

    # 2. Película: rho_f=1e-3 Ω·m, t=1e-6 m, A=pi*(1e-3)² -> R = 1e-3*1e-6/A
    r = contact_resistance(1.68e-8, 1e-3, rho_film=1e-3, film_thickness_m=1e-6)
    want_f = 1e-3 * 1e-6 / (math.pi * 1e-6)
    chk("película en paralelo", abs(r["R_film_ohm"] - want_f) < 1e-12,
        f"R_film={r['R_film_ohm']:.4e}")
    chk("paralelo <= mínimo de ramas",
        r["R_total_ohm"] <= min(r["R_constriction_ohm"], r["R_film_ohm"]) + 1e-18)

    # 3. GPR de hemisferio: V(a) = rho*I/(2*pi*a)
    gpr = hemisphere_potential(100.0, 1000.0, 1.0, 1.0)
    chk("GPR hemisferio", abs(gpr - 100 * 1000 / (2 * math.pi)) < 1e-9, f"GPR={gpr:.3f} V")

    # 4. Tensión de paso con fórmula cerrada: rho*I/(2*pi)*(1/r - 1/(r+1))
    rho, I, rr, a = 100.0, 1000.0, 2.0, 1.0
    want_s = rho * I / (2 * math.pi) * (1 / rr - 1 / (rr + 1))
    chk("tensión de paso", abs(step_voltage(rho, I, rr, a) - want_s) < 1e-9,
        f"step={step_voltage(rho, I, rr, a):.3f} V")

    # 5. Tensión de contacto -> 0 cuando el pie está en el electrodo (r = a)
    chk("contacto en r=a es 0", abs(touch_voltage(rho, I, a, a)) < 1e-12)

    # 6. Contacto crece con la distancia de los pies (monótono hasta GPR)
    t2, t5 = touch_voltage(rho, I, 2.0, a), touch_voltage(rho, I, 5.0, a)
    chk("contacto monótono en r", t5 > t2 > 0, f"t(2)={t2:.1f} t(5)={t5:.1f}")

    # 7. Límite tolerable IEEE 80 (70 kg): (1000+1.5*1*100)*0.157/sqrt(0.5)
    want_tol = (1000 + 150) * 0.157 / math.sqrt(0.5)
    chk("tolerable 70 kg", abs(tolerable_voltages(100.0, 1.0, 0.5, 70) - want_tol) < 1e-9,
        f"E={want_tol:.2f} V")

    # 8. 50 kg tolera menos que 70 kg (k=0.116 < 0.157)
    chk("50 kg más estricto que 70 kg",
        tolerable_voltages(100.0, 1.0, 0.5, 50) < tolerable_voltages(100.0, 1.0, 0.5, 70))

    passed = sum(c["passed"] for c in checks)
    return {"checks": checks, "total_passed": passed, "total_checks": len(checks),
            "validation_passed": passed == len(checks)}


def _handler(args):
    mode = args.get("mode")
    params = args.get("params") or {}
    try:
        if mode == "validate":
            return _mode_validate()
        if mode in _MODES:
            return {"mode": mode, "result": _MODES[mode](params)}
        return {"error": f"mode desconocido: {mode}"}
    except (KeyError, ValueError, TypeError, ZeroDivisionError) as e:
        return {"error": f"parámetros inválidos: {e}"}


register_tool(
    name="grounding_safety_tool",
    schema=GROUNDING_SAFETY_TOOL_SCHEMA,
    handler=_handler,
)
