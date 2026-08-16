"""
statmech_partition_tool.py

Mecanica estadistica: funcion de particion canonica y propiedades
termodinamicas derivadas (U, F, S, Cv) para tres sistemas modelo con
solucion analitica exacta -- sin libreria numerica nueva, todo cerrado
en forma cerrada o casi-cerrada.

Todas las formulas se escriben en terminos de exp(-x) (x >= 0), nunca
exp(+x), para evitar OverflowError a temperaturas bajas -- ver el caso
quantum_harmonic_oscillator con T=1e-8 en el docstring de validate().
Un primer intento con exp(+x) directo explotaba ahi; quedo documentado
como advertencia para el que edite esto despues.

Unidades: naturales por defecto (kB=1, hbar=1, h=2*pi). Se puede pasar
kB/hbar/h reales (SI) si se quieren magnitudes fisicas concretas, ya
que son simples factores multiplicativos en todas las formulas.
"""
import math


def _two_level(params):
    T = params.get("T", 1.0)
    dE = params.get("delta_E", 1.0)
    kB = params.get("kB", 1.0)
    if T <= 0:
        raise ValueError("T debe ser > 0")
    beta = 1.0 / (kB * T)
    q = math.exp(-beta * dE)  # underflow seguro a 0, nunca overflow
    Z = 1 + q
    U = dE * q / Z
    F = -kB * T * math.log(Z)
    S = (U - F) / T
    Cv = kB * (beta * dE) ** 2 * q / Z ** 2
    return {
        "system": "two_level_system",
        "inputs": {"T": T, "delta_E": dE, "kB": kB},
        "Z": Z, "U": U, "F": F, "S": S, "Cv": Cv,
        "note": "Limite T->0: Z->1 (solo estado base). Limite T->inf: Z->2, S->kB*ln(2).",
    }


def _qho(params):
    T = params.get("T", 1.0)
    hbar = params.get("hbar", 1.0)
    omega = params.get("omega", 1.0)
    kB = params.get("kB", 1.0)
    if T <= 0:
        raise ValueError("T debe ser > 0")
    beta = 1.0 / (kB * T)
    x = beta * hbar * omega
    q = math.exp(-x)
    one_minus_q = -math.expm1(-x)  # precision numerica cerca de x=0
    Z = math.exp(-x / 2) / one_minus_q if one_minus_q > 0 else float("inf")
    U = hbar * omega * (0.5 + (q / one_minus_q if one_minus_q > 0 else 0.0))
    F = kB * T * (x / 2 + math.log(one_minus_q)) if one_minus_q > 0 else hbar * omega / 2
    S = (U - F) / T
    Cv = kB * x ** 2 * q / one_minus_q ** 2 if one_minus_q > 0 else 0.0
    return {
        "system": "quantum_harmonic_oscillator",
        "inputs": {"T": T, "hbar": hbar, "omega": omega, "kB": kB},
        "Z": Z, "U": U, "F": F, "S": S, "Cv": Cv,
        "note": "Limite T->0: U->hbar*omega/2 (punto cero), Cv->0 (congelado). "
                "Limite T->inf: Cv->kB (equiparticion clasica).",
    }


def _ideal_gas(params):
    T = params.get("T", 300.0)
    V = params.get("V", 1.0)
    m = params.get("m", 1.0)
    N = params.get("N", 1)
    kB = params.get("kB", 1.0)
    h = params.get("h", 2 * math.pi)
    if T <= 0 or V <= 0 or m <= 0 or N <= 0:
        raise ValueError("T, V, m, N deben ser > 0")
    lam = h / math.sqrt(2 * math.pi * m * kB * T)  # longitud de onda termica de de Broglie
    Z1 = V / lam ** 3
    U = 1.5 * N * kB * T
    Cv = 1.5 * N * kB
    F = -kB * T * N * (math.log(Z1 / N) + 1)  # aproximacion de Stirling para ln(N!)
    S = (U - F) / T
    return {
        "system": "ideal_gas_translational",
        "inputs": {"T": T, "V": V, "m": m, "N": N, "kB": kB, "h": h},
        "Z1": Z1, "U": U, "F": F, "S": S, "Cv": Cv,
        "note": "Cv = 1.5*N*kB SIEMPRE para gas ideal monoatomico, independiente de T/V/m "
                "(equiparticion exacta, no aproximacion).",
    }


def _validate():
    checks = []

    r = _two_level({"T": 1000.0, "delta_E": 1.0, "kB": 1.0})
    checks.append({
        "case": "two_level high-T -> S=kB*ln(2)",
        "expected": math.log(2), "got": r["S"],
        "ok": abs(r["S"] - math.log(2)) < 1e-3,
    })

    r = _qho({"T": 1e-8, "hbar": 1.0, "omega": 1.0, "kB": 1.0})
    checks.append({
        "case": "qho T->0 extremo (antes explotaba con exp(+x)) -> U=hbar*omega/2",
        "expected": 0.5, "got": r["U"],
        "ok": abs(r["U"] - 0.5) < 1e-6,
    })

    r = _qho({"T": 1000.0, "hbar": 1.0, "omega": 1.0, "kB": 1.0})
    checks.append({
        "case": "qho high-T -> Cv=kB (clasico)",
        "expected": 1.0, "got": r["Cv"],
        "ok": abs(r["Cv"] - 1.0) < 1e-3,
    })

    for T, V, m in [(300, 1.0, 1.0), (500, 2.0, 0.5), (100, 0.1, 2.0)]:
        r = _ideal_gas({"T": T, "V": V, "m": m, "N": 10, "kB": 1.0})
        checks.append({
            "case": f"ideal_gas Cv invariante (T={T},V={V},m={m})",
            "expected": 15.0, "got": r["Cv"],
            "ok": abs(r["Cv"] - 15.0) < 1e-9,
        })

    return {"validate": True, "all_passed": all(c["ok"] for c in checks), "checks": checks}


def compute_statmech_partition(mode, params=None):
    params = params or {}
    if mode == "two_level_system":
        return _two_level(params)
    elif mode == "quantum_harmonic_oscillator":
        return _qho(params)
    elif mode == "ideal_gas_translational":
        return _ideal_gas(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            f"mode desconocido: {mode!r}. Valores validos: two_level_system, "
            f"quantum_harmonic_oscillator, ideal_gas_translational, validate."
        )


STATMECH_PARTITION_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": [
                "two_level_system",
                "quantum_harmonic_oscillator",
                "ideal_gas_translational",
                "validate",
            ],
            "default": "two_level_system",
        },
        "T": {
            "type": "number",
            "description": "Temperatura. Unidades naturales (kB=1) por defecto.",
        },
        "kB": {
            "type": "number",
            "default": 1.0,
            "description": "Constante de Boltzmann. Default=1.0 (unidades naturales); "
                            "usar 1.380649e-23 para valores fisicos reales en Joules/Kelvin.",
        },
        "delta_E": {
            "type": "number",
            "description": "Solo two_level_system: brecha de energia entre estado base y excitado.",
        },
        "hbar": {
            "type": "number",
            "description": "Solo quantum_harmonic_oscillator. Default=1.0 (unidades naturales).",
        },
        "omega": {
            "type": "number",
            "description": "Solo quantum_harmonic_oscillator: frecuencia angular.",
        },
        "V": {
            "type": "number",
            "description": "Solo ideal_gas_translational: volumen del contenedor.",
        },
        "m": {
            "type": "number",
            "description": "Solo ideal_gas_translational: masa de una particula.",
        },
        "N": {
            "type": "integer",
            "description": "Solo ideal_gas_translational: numero de particulas.",
        },
        "h": {
            "type": "number",
            "description": "Solo ideal_gas_translational: constante de Planck. Default=2*pi "
                            "(unidades naturales con hbar=1).",
        },
    },
    "required": ["mode"],
}


try:
    from tool_registry import register_tool
    register_tool(
        name="statmech_partition_tool",
        schema={
            "name": "statmech_partition_tool",
            "description": (
                "Mecanica estadistica: funcion de particion canonica y propiedades termodinamicas "
                "(Z, U, F, S, Cv) para tres sistemas con solucion analitica exacta -- "
                "two_level_system (sistema de 2 niveles, Z=1+e^-(beta*dE)), "
                "quantum_harmonic_oscillator (oscilador armonico cuantico), "
                "ideal_gas_translational (gas ideal monoatomico via longitud de onda termica de "
                "de Broglie, Cv=1.5*N*kB exacto siempre). Formulas numericamente estables a T baja "
                "(escritas en exp(-x), no exp(+x): evita overflow)."
            ),
            "inputSchema": STATMECH_PARTITION_SCHEMA,
        },
        handler=lambda args: compute_statmech_partition(args.get("mode"), args),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    print(json.dumps(compute_statmech_partition("validate"), indent=2, ensure_ascii=False))
