"""
biodiversity_model_tool.py

Indices de diversidad biologica sobre datos de abundancia por especie.
Patron: compute_biodiversity_model_tool(mode, **kwargs) + BIODIVERSITY_MODEL_TOOL_SCHEMA
Auto-registro via @register_tool (mismo patron que cfd_tool / bem_electromagnetic_tool).

Modos:
  - shannon        : indice de Shannon-Wiener (H') y equitabilidad de Pielou (J)
  - simpson        : indice de Simpson (D) y su complemento (1-D)
  - chao1          : estimador de riqueza Chao1 (para datos de abundancia)
  - summary        : corre las tres metricas anteriores sobre el mismo dataset
  - validate       : autotest contra casos de libro de texto (mode="validate")
"""

import math

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(schema):
        def _decorator(fn):
            return fn
        return _decorator


def _shannon(abundances):
    n = sum(abundances)
    if n <= 0:
        raise ValueError("La suma de abundancias debe ser > 0")
    H = 0.0
    for a in abundances:
        if a <= 0:
            continue
        p = a / n
        H -= p * math.log(p)
    S = sum(1 for a in abundances if a > 0)
    J = H / math.log(S) if S > 1 else 0.0
    return {"shannon_H": H, "richness_S": S, "pielou_J": J}


def _simpson(abundances):
    n = sum(abundances)
    if n <= 0:
        raise ValueError("La suma de abundancias debe ser > 0")
    D = sum((a / n) ** 2 for a in abundances if a > 0)
    return {"simpson_D": D, "simpson_1_minus_D": 1.0 - D, "simpson_reciprocal_1_over_D": (1.0 / D if D > 0 else float("inf"))}


def _chao1(abundances):
    # Chao1 clasico (abundance-based): S_est = S_obs + f1^2 / (2*f2)
    # Version bias-corrected para f2 = 0: S_obs + f1*(f1-1) / 2
    S_obs = sum(1 for a in abundances if a > 0)
    f1 = sum(1 for a in abundances if a == 1)  # singletons
    f2 = sum(1 for a in abundances if a == 2)  # doubletons
    if f2 > 0:
        S_chao1 = S_obs + (f1 ** 2) / (2.0 * f2)
        variance = (f1 ** 2 / (2 * f2)) + \
                   ((f1 ** 3) / (4 * f2 ** 2)) + \
                   ((f1 ** 4) / (4 * f2 ** 3)) if f2 > 0 else None
    else:
        S_chao1 = S_obs + (f1 * (f1 - 1)) / 2.0
        variance = None
    return {
        "S_obs": S_obs,
        "f1_singletons": f1,
        "f2_doubletons": f2,
        "S_chao1": S_chao1,
        "variance": variance,
        "bias_corrected": f2 == 0,
    }


def _validate():
    checks = []

    # Caso 1: comunidad perfectamente uniforme, 4 especies, 25 individuos c/u
    # Shannon max = ln(S), Pielou J = 1
    uniform = [25, 25, 25, 25]
    r = _shannon(uniform)
    ok1 = abs(r["shannon_H"] - math.log(4)) < 1e-9 and abs(r["pielou_J"] - 1.0) < 1e-9
    checks.append(("shannon_uniform_J_eq_1", ok1))

    # Caso 2: una sola especie -> H = 0, D = 1
    mono = [50]
    r2 = _shannon(mono)
    r3 = _simpson(mono)
    ok2 = abs(r2["shannon_H"] - 0.0) < 1e-9 and abs(r3["simpson_D"] - 1.0) < 1e-9
    checks.append(("monoculture_H0_D1", ok2))

    # Caso 3: Simpson con 2 especies iguales (10,10) -> D = 0.5
    r4 = _simpson([10, 10])
    ok3 = abs(r4["simpson_D"] - 0.5) < 1e-9
    checks.append(("simpson_two_equal_species", ok3))

    # Caso 4: Chao1 sin singletons ni doubletons -> S_chao1 == S_obs
    no_rare = [10, 15, 20]
    r5 = _chao1(no_rare)
    ok4 = r5["S_chao1"] == r5["S_obs"]
    checks.append(("chao1_no_rare_species_equals_Sobs", ok4))

    # Caso 5: Chao1 con f1=3, f2=1 -> S_est = S_obs + 9/2 = S_obs + 4.5
    mixed = [1, 1, 1, 2, 5, 8]  # f1=3 (los tres '1'), f2=1 (el '2')
    r6 = _chao1(mixed)
    expected = r6["S_obs"] + (3 ** 2) / (2.0 * 1)
    ok5 = abs(r6["S_chao1"] - expected) < 1e-9
    checks.append(("chao1_f1_f2_formula", ok5))

    passed = sum(1 for _, ok in checks if ok)
    return {
        "mode": "validate",
        "checks": [{"name": n, "passed": ok} for n, ok in checks],
        "passed": passed,
        "total": len(checks),
        "all_passed": passed == len(checks),
    }


BIODIVERSITY_MODEL_TOOL_SCHEMA = {
    "name": "biodiversity_model_tool",
    "description": (
        "Calcula indices de diversidad biologica (Shannon-Wiener, Simpson, "
        "estimador de riqueza Chao1) a partir de datos de abundancia por especie. "
        "No hace interpretacion ecologica causal, solo devuelve indices/estadisticas."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["shannon", "simpson", "chao1", "summary", "validate"],
                "description": "Metrica a calcular, o 'validate' para autotest",
            },
            "abundances": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Abundancia (conteo de individuos) por especie",
            },
        },
        "required": ["mode"],
    },
}


@register_tool(BIODIVERSITY_MODEL_TOOL_SCHEMA)
def compute_biodiversity_model_tool(mode, **kwargs):
    if mode == "validate":
        return _validate()

    abundances = kwargs.get("abundances")
    if not abundances:
        raise ValueError("Se requiere 'abundances' (lista de conteos por especie)")
    abundances = [float(a) for a in abundances]

    if mode == "shannon":
        return {"mode": mode, **_shannon(abundances)}
    elif mode == "simpson":
        return {"mode": mode, **_simpson(abundances)}
    elif mode == "chao1":
        return {"mode": mode, **_chao1(abundances)}
    elif mode == "summary":
        return {
            "mode": mode,
            "shannon": _shannon(abundances),
            "simpson": _simpson(abundances),
            "chao1": _chao1(abundances),
        }
    else:
        raise ValueError(f"Modo desconocido: {mode}")


if __name__ == "__main__":
    import json
    print(json.dumps(compute_biodiversity_model_tool(mode="validate"), indent=2, ensure_ascii=False))
