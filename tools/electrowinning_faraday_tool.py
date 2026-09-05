"""
electrowinning_faraday_tool.py

Electrodeposicion / electrowinning: paso final del ciclo hidrometalurgico
(lixiviacion -> extraccion por solventes -> precipitacion -> ESTE PASO)
para obtener el metal puro solido a partir de la solucion purificada.

Cubre:
  - faraday_mass:       masa depositada dado corriente, tiempo, M, n, eficiencia
  - deposition_time:    tiempo necesario para depositar una masa objetivo
  - nernst_potential:   potencial de equilibrio de la celda (Nernst)
  - current_efficiency: eficiencia real vs. teorica (Faraday) a partir de masa medida
  - validate:           auto-chequeo contra casos de libro de texto

Formulas (todas cerradas, sin solver):
  Faraday:  m = eta * (I * t * M) / (n * F)
  Nernst:   E = E0 - (R*T)/(n*F) * ln(Q)
            Para M^n+ + n e- -> M(s):  Q = 1 / a_ion   (actividad del solido = 1)

Unidades: SI. F = 96485 C/mol, R = 8.314 J/(mol*K).
"""

import math

F_FARADAY = 96485.0  # C/mol
R_GAS = 8.314        # J/(mol*K)


def _faraday_mass(params):
    I = params["current_A"]
    t = params["time_s"]
    M = params["molar_mass_g_mol"]
    n = params["n_electrons"]
    eta = params.get("current_efficiency", 1.0)

    mass_g = eta * (I * t * M) / (n * F_FARADAY)
    theoretical_mass_g = (I * t * M) / (n * F_FARADAY)

    return {
        "mode": "faraday_mass",
        "mass_deposited_g": mass_g,
        "theoretical_mass_g_at_100pct": theoretical_mass_g,
        "current_efficiency_used": eta,
        "charge_passed_C": I * t,
        "equivalent_weight_g_per_mol": M / n,
        "confidence_flag": "alta",
        "note": "Formula cerrada de Faraday, exacta dada la corriente/tiempo/eficiencia.",
    }


def _deposition_time(params):
    target_mass_g = params["target_mass_g"]
    I = params["current_A"]
    M = params["molar_mass_g_mol"]
    n = params["n_electrons"]
    eta = params.get("current_efficiency", 1.0)

    t_s = (target_mass_g * n * F_FARADAY) / (eta * I * M)

    return {
        "mode": "deposition_time",
        "time_needed_s": t_s,
        "time_needed_h": t_s / 3600.0,
        "target_mass_g": target_mass_g,
        "current_efficiency_used": eta,
        "confidence_flag": "alta",
    }


def _nernst_potential(params):
    """
    Reaccion generica: Ox + n e- -> Red
    Caso mas comun en electrowinning: M^n+ + n e- -> M(s), con a_red=1 (solido puro),
    entonces Q = a_red/a_ox = 1/a_ion.

    Si se pasa 'reaction_quotient_Q' directo, se usa tal cual (mas general,
    permite mezclas, pares redox no metal-solido, etc).
    Si se pasa 'ion_activity' (caso M^n+/M(s)), se calcula Q = 1/ion_activity.
    """
    E0 = params["E0_V"]
    n = params["n_electrons"]
    T = params.get("temperature_K", 298.15)

    if "reaction_quotient_Q" in params:
        Q = params["reaction_quotient_Q"]
    elif "ion_activity" in params:
        Q = 1.0 / params["ion_activity"]
    else:
        raise ValueError(
            "nernst_potential requiere 'reaction_quotient_Q' o 'ion_activity'"
        )

    E = E0 - (R_GAS * T) / (n * F_FARADAY) * math.log(Q)

    return {
        "mode": "nernst_potential",
        "E0_V": E0,
        "equilibrium_potential_V": E,
        "reaction_quotient_Q": Q,
        "temperature_K": T,
        "confidence_flag": "alta",
        "note": "Convencion de reduccion: Ox + n e- -> Red. Para M^n+/M(s) solido, Q=1/actividad_ion.",
    }


def _current_efficiency(params):
    actual_mass_g = params["actual_mass_g"]
    I = params["current_A"]
    t = params["time_s"]
    M = params["molar_mass_g_mol"]
    n = params["n_electrons"]

    theoretical_mass_g = (I * t * M) / (n * F_FARADAY)
    efficiency = actual_mass_g / theoretical_mass_g

    return {
        "mode": "current_efficiency",
        "current_efficiency": efficiency,
        "current_efficiency_pct": efficiency * 100.0,
        "theoretical_mass_g": theoretical_mass_g,
        "actual_mass_g": actual_mass_g,
        "confidence_flag": "alta",
        "note": "eta<1 tipico por reacciones secundarias (ej. evolucion de H2 compitiendo con el deposito metalico).",
    }


def _validate():
    checks = []

    # 1) Caso de libro de texto: Cu2+ + 2e- -> Cu, 1 Faraday deposita 1 eq-gramo
    r = _faraday_mass({
        "current_A": 96485.0 / 3600.0,  # exactamente 1 Faraday en 1 hora
        "time_s": 3600.0,
        "molar_mass_g_mol": 63.546,
        "n_electrons": 2,
        "current_efficiency": 1.0,
    })
    expected = 63.546 / 2  # 31.773 g
    ok1 = abs(r["mass_deposited_g"] - expected) < 1e-6
    checks.append({"check": "faraday_1_equivalente_Cu", "passed": bool(ok1),
                    "expected": expected, "got": r["mass_deposited_g"]})

    # 2) Round-trip: deposition_time debe invertir exactamente a faraday_mass
    r2 = _deposition_time({
        "target_mass_g": 50.0,
        "current_A": 20.0,
        "molar_mass_g_mol": 58.933,  # Co
        "n_electrons": 2,
        "current_efficiency": 0.9,
    })
    r3 = _faraday_mass({
        "current_A": 20.0,
        "time_s": r2["time_needed_s"],
        "molar_mass_g_mol": 58.933,
        "n_electrons": 2,
        "current_efficiency": 0.9,
    })
    ok2 = abs(r3["mass_deposited_g"] - 50.0) < 1e-6
    checks.append({"check": "roundtrip_time_mass_Co", "passed": bool(ok2),
                    "expected": 50.0, "got": r3["mass_deposited_g"]})

    # 3) Nernst en condiciones estandar (actividad=1) debe devolver exactamente E0
    r4 = _nernst_potential({"E0_V": 0.34, "n_electrons": 2, "ion_activity": 1.0})
    ok3 = abs(r4["equilibrium_potential_V"] - 0.34) < 1e-9
    checks.append({"check": "nernst_condiciones_estandar", "passed": bool(ok3),
                    "expected": 0.34, "got": r4["equilibrium_potential_V"]})

    # 4) Nernst: bajar actividad del ion debe bajar el potencial de deposito
    #    (mas dificil depositar de una solucion diluida - sentido fisico correcto)
    r5 = _nernst_potential({"E0_V": 0.34, "n_electrons": 2, "ion_activity": 0.001})
    ok4 = bool(r5["equilibrium_potential_V"] < 0.34)
    checks.append({"check": "nernst_monotonia_actividad", "passed": ok4,
                    "E_diluido": r5["equilibrium_potential_V"], "E0": 0.34})

    # 5) current_efficiency: masa teorica exacta -> eficiencia = 1.0
    r6 = _current_efficiency({
        "actual_mass_g": expected,
        "current_A": 96485.0 / 3600.0,
        "time_s": 3600.0,
        "molar_mass_g_mol": 63.546,
        "n_electrons": 2,
    })
    ok5 = abs(r6["current_efficiency"] - 1.0) < 1e-6
    checks.append({"check": "eficiencia_100pct_caso_teorico", "passed": bool(ok5),
                    "expected": 1.0, "got": r6["current_efficiency"]})

    all_passed = all(c["passed"] for c in checks)
    return {
        "mode": "validate",
        "all_passed": all_passed,
        "n_checks": len(checks),
        "n_passed": sum(1 for c in checks if c["passed"]),
        "checks": checks,
    }


def run(mode, params=None):
    params = params or {}
    if mode == "faraday_mass":
        return _faraday_mass(params)
    elif mode == "deposition_time":
        return _deposition_time(params)
    elif mode == "nernst_potential":
        return _nernst_potential(params)
    elif mode == "current_efficiency":
        return _current_efficiency(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"Modo desconocido: {mode}")


# --- Registro MCP (patron auto-registro tool_registry) ---
# OJO: revisar que este import/registro calce EXACTO con el de tus otras
# tools (ej. ree_solvent_extraction_tool.py) — no pude correr octave_codegen_tool
# esta sesion para generarlo desde tu propio scaffold, asi que esto es una
# reconstruccion basada en el patron descrito, no una copia verificada.

TOOL_SCHEMA = {
    "name": "electrowinning_faraday_tool",
    "description": (
        "Electrodeposicion/electrowinning: Ley de Faraday (masa depositada), "
        "ecuacion de Nernst (potencial de equilibrio), tiempo de deposito y "
        "eficiencia de corriente. Paso final del ciclo hidrometalurgico "
        "(lixiviacion -> SX -> precipitacion -> electrowinning) para cobre, "
        "cobalto, o cualquier metal via reduccion M^n+ + n e- -> M(s)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "faraday_mass",
                    "deposition_time",
                    "nernst_potential",
                    "current_efficiency",
                    "validate",
                ],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


def _register():
    try:
        import tool_registry
        tool_registry.register_tool(
            name="electrowinning_faraday_tool",
            schema=TOOL_SCHEMA,
            handler=lambda mode, params=None: run(mode, params),
        )
    except ImportError:
        pass  # permite import standalone para testear sin el server completo


_register()
