"""
statmech_tool.py

Mecanica estadistica de equilibrio: funcion de particion canonica y
cantidades termodinamicas derivadas, para sistemas de espectro discreto.
Matematica cerrada (sin solver numerico pesado, no requiere submotor Rust).

Modos:
- partition_function: dado un espectro {energias} y T, calcula Z, F, U, S, Cv
  por sumatoria directa sobre niveles.
- harmonic_oscillator: oscilador armonico cuantico 1D (formula cerrada
  exacta), frecuencia angular omega.
- two_level_system: sistema de dos niveles / spin 1/2 en campo magnetico
  (formula cerrada exacta), splitting de energia delta. Caso clasico con pico
  de Schottky en Cv(T).
- rigid_rotor: rotor rigido cuantico (aprox. alta T, suma sobre J).

Convencion: k_B = 1 (energias y temperaturas en unidades reducidas) salvo que
se pase k_B explicito en SI.

Validado contra formulas analiticas de libro de texto (Kittel & Kroemer,
Reif) para harmonic_oscillator y two_level_system.
"""
import math


def _thermo_from_partition(z_of_beta, beta, d_beta=None):
    """Deriva F, U, S, Cv de Z(beta) por diferenciacion numerica central de
    ln Z respecto a beta. d_beta es relativo a beta (beta * 1e-4), no absoluto:
    un paso absoluto fijo falla en extremos de temperatura -- para beta~1 un
    d_beta=1e-4 es optimo (balance truncamiento/redondeo para derivada
    segunda), pero para beta~0.001 (T alta) ese mismo paso absoluto es 10% de
    beta y el error de truncamiento domina. Escalar el paso con beta mantiene
    la misma precision relativa en cualquier regimen de temperatura."""
    if d_beta is None:
        d_beta = max(abs(beta) * 1e-4, 1e-10)
    ln_z = math.log(z_of_beta(beta))
    ln_z_plus = math.log(z_of_beta(beta + d_beta))
    ln_z_minus = math.log(z_of_beta(beta - d_beta))

    u = -(ln_z_plus - ln_z_minus) / (2 * d_beta)  # U = -d(lnZ)/d(beta)
    d2_ln_z = (ln_z_plus - 2 * ln_z + ln_z_minus) / d_beta ** 2
    cv = beta ** 2 * d2_ln_z  # Cv = k_B beta^2 d^2(lnZ)/d(beta)^2, k_B=1

    t = 1.0 / beta
    f = -t * ln_z  # F = -kT ln Z
    s = (u - f) / t  # S = (U - F) / T

    return {"Z": z_of_beta(beta), "ln_Z": ln_z, "F": f, "U": u, "S": s, "Cv": cv}


def _z_partition_from_levels(energies, beta, degeneracies=None):
    degeneracies = degeneracies or [1] * len(energies)
    return sum(g * math.exp(-beta * e) for g, e in zip(degeneracies, energies))


def _compute_partition_function(params):
    energies = params["energies"]
    degeneracies = params.get("degeneracies")
    temperature = params["temperature"]
    beta = 1.0 / temperature

    result = _thermo_from_partition(
        lambda b: _z_partition_from_levels(energies, b, degeneracies), beta
    )
    result["temperature"] = temperature
    result["n_levels"] = len(energies)
    return result


def _compute_harmonic_oscillator(params):
    omega = params["omega"]
    temperature = params["temperature"]
    beta = 1.0 / temperature
    hbar = params.get("hbar", 1.0)

    # Z exacto (incluyendo energia de punto cero): Z = exp(-beta hbar omega/2) / (1 - exp(-beta hbar omega))
    def z_of_beta(b):
        x = b * hbar * omega
        return math.exp(-x / 2) / (1 - math.exp(-x))

    result = _thermo_from_partition(z_of_beta, beta)

    # formulas analiticas exactas para comparar
    x = beta * hbar * omega
    u_exact = hbar * omega * (0.5 + 1.0 / (math.exp(x) - 1))
    cv_exact = (x ** 2 * math.exp(x)) / (math.exp(x) - 1) ** 2

    result["U_exact"] = u_exact
    result["Cv_exact"] = cv_exact
    result["temperature"] = temperature
    result["omega"] = omega
    return result


def _compute_two_level_system(params):
    delta = params["delta"]  # splitting de energia entre los dos niveles
    temperature = params["temperature"]
    beta = 1.0 / temperature

    def z_of_beta(b):
        return math.exp(-b * 0) + math.exp(-b * delta)  # niveles en 0 y delta

    result = _thermo_from_partition(z_of_beta, beta)

    # formulas analiticas exactas (Schottky)
    x = beta * delta
    u_exact = delta / (math.exp(x) + 1)
    cv_exact = x ** 2 * math.exp(x) / (math.exp(x) + 1) ** 2

    result["U_exact"] = u_exact
    result["Cv_exact"] = cv_exact
    result["temperature"] = temperature
    result["delta"] = delta
    return result


def _compute_rigid_rotor(params):
    b_rot = params["rotational_constant"]  # B = hbar^2 / (2 I), unidades de energia
    temperature = params["temperature"]
    j_max = params.get("j_max", 200)  # truncamiento de la suma
    beta = 1.0 / temperature

    def z_of_beta(b):
        return sum((2 * j + 1) * math.exp(-b * b_rot * j * (j + 1)) for j in range(j_max))

    result = _thermo_from_partition(z_of_beta, beta)
    result["temperature"] = temperature
    result["rotational_constant"] = b_rot
    result["j_max"] = j_max
    return result


def _validate():
    checks = []

    # Check 1: oscilador armonico, x=1.5 (regimen intermedio, ni clasico ni degenerado)
    r1 = _compute_harmonic_oscillator({"omega": 1.5, "temperature": 1.0, "hbar": 1.0})
    err1_u = abs(r1["U"] - r1["U_exact"]) / abs(r1["U_exact"])
    err1_cv = abs(r1["Cv"] - r1["Cv_exact"]) / abs(r1["Cv_exact"])
    checks.append({
        "name": "harmonic_oscillator_x1.5",
        "err_U": err1_u, "err_Cv": err1_cv,
        "passed": err1_u < 1e-4 and err1_cv < 1e-4,
    })

    # Check 2: dos niveles, cerca del pico de Schottky (x~2.4 da el maximo de Cv)
    r2 = _compute_two_level_system({"delta": 2.4, "temperature": 1.0})
    err2_u = abs(r2["U"] - r2["U_exact"]) / abs(r2["U_exact"])
    err2_cv = abs(r2["Cv"] - r2["Cv_exact"]) / abs(r2["Cv_exact"])
    checks.append({
        "name": "two_level_schottky_peak",
        "err_U": err2_u, "err_Cv": err2_cv,
        "passed": err2_u < 1e-4 and err2_cv < 1e-4,
    })

    # Check 3: limite clasico del oscilador armonico (T grande -> Cv -> 1, teorema equiparticion, k_B=1)
    r3 = _compute_harmonic_oscillator({"omega": 1.0, "temperature": 1000.0, "hbar": 1.0})
    err3 = abs(r3["Cv"] - 1.0)
    checks.append({
        "name": "harmonic_oscillator_classical_limit",
        "Cv": r3["Cv"], "expected": 1.0, "err": err3,
        "passed": err3 < 1e-3,
    })

    return {
        "mode": "validate",
        "checks": checks,
        "validation_passed": all(c["passed"] for c in checks),
    }


def compute_statmech(mode, params=None):
    params = params or {}

    dispatch = {
        "partition_function": _compute_partition_function,
        "harmonic_oscillator": _compute_harmonic_oscillator,
        "two_level_system": _compute_two_level_system,
        "rigid_rotor": _compute_rigid_rotor,
        "validate": lambda p: _validate(),
    }

    if mode not in dispatch:
        raise ValueError(f"mode desconocido: '{mode}'. Validos: {list(dispatch.keys())}")

    return dispatch[mode](params)


STATMECH_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["partition_function", "harmonic_oscillator", "two_level_system", "rigid_rotor", "validate"],
            "default": "harmonic_oscillator",
        },
        "energies": {"type": "array", "items": {"type": "number"}, "description": "Para partition_function: espectro de niveles de energia."},
        "degeneracies": {"type": "array", "items": {"type": "integer"}, "description": "Para partition_function: degeneracion de cada nivel (default 1)."},
        "omega": {"type": "number", "description": "Para harmonic_oscillator: frecuencia angular."},
        "hbar": {"type": "number", "default": 1.0},
        "delta": {"type": "number", "description": "Para two_level_system: splitting de energia entre los dos niveles."},
        "rotational_constant": {"type": "number", "description": "Para rigid_rotor: B = hbar^2/(2I)."},
        "j_max": {"type": "integer", "default": 200, "description": "Para rigid_rotor: truncamiento de la suma sobre J."},
        "temperature": {"type": "number", "description": "Temperatura en unidades reducidas (k_B=1)."},
    },
    "required": ["mode"],
}

try:
    from tool_registry import register_tool
    register_tool(
        name="statmech_tool",
        schema={
            "name": "statmech_tool",
            "description": "Mecanica estadistica de equilibrio: funcion de particion canonica y cantidades termodinamicas derivadas (F, U, S, Cv) por diferenciacion numerica de ln Z. Modos con formula cerrada: harmonic_oscillator, two_level_system (pico de Schottky), rigid_rotor; modo generico partition_function para espectro arbitrario. Validado contra formulas analiticas exactas de libro de texto y limite clasico de equiparticion.",
            "inputSchema": STATMECH_TOOL_SCHEMA,
        },
        handler=lambda args: compute_statmech(args.get("mode"), args),
    )
except ImportError:
    pass
