"""
biodiversity_model_tool.py

Indices de diversidad biologica sobre datos de abundancia por especie, mas
un modo de impacto por perdida de habitat via relacion especies-area.
Patron: compute_biodiversity_model_tool(mode, **kwargs) + BIODIVERSITY_MODEL_TOOL_SCHEMA
Auto-registro via @register_tool (mismo patron que cfd_tool / bem_electromagnetic_tool).

Modos:
  - shannon           : indice de Shannon-Wiener (H') y equitabilidad de Pielou (J)
  - simpson           : indice de Simpson (D) y su complemento (1-D)
  - chao1             : estimador de riqueza Chao1 (para datos de abundancia)
  - summary           : corre las tres metricas anteriores sobre el mismo dataset
  - habitat_area_loss : relacion especies-area (Arrhenius, S=c*A^z) + deuda de
                         extincion con relajacion temporal, dado un cambio de
                         area de habitat
  - validate          : autotest contra casos de libro de texto (mode="validate")
"""

import math

try:
    from tool_registry import register_tool
except ImportError:
    register_tool = None


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


def _habitat_area_loss(initial_area_ha, final_area_ha, sar_c=5.0, sar_z=0.27,
                        years=30, relaxation_rate=0.08):
    """Relacion especies-area de Arrhenius (S = c * A^z) con deuda de
    extincion: la riqueza observada no cae instantaneamente al nuevo
    equilibrio, se relaja hacia el con una tasa anual constante.
    CONFIANZA MEDIA: c y z son ajustables por bioma/taxon, los defaults
    (c=5.0, z=0.27) son ilustrativos, no especificos de un sitio real."""
    if initial_area_ha <= 0:
        raise ValueError("initial_area_ha debe ser > 0")
    if final_area_ha < 0:
        raise ValueError("final_area_ha no puede ser negativo")
    if not (0.0 < relaxation_rate <= 1.0):
        raise ValueError("relaxation_rate debe estar en (0, 1]")

    def richness(area_ha):
        return sar_c * (area_ha ** sar_z) if area_ha > 0 else 0.0

    S_initial = richness(initial_area_ha)
    S_equilibrium = richness(final_area_ha)
    total_debt = S_initial - S_equilibrium

    S_current = S_initial
    richness_timeseries = [round(S_current, 4)]
    realized_loss_timeseries = [0.0]
    for _year in range(1, years + 1):
        gap = S_current - S_equilibrium
        S_current = S_current - gap * relaxation_rate
        richness_timeseries.append(round(S_current, 4))
        realized_loss_timeseries.append(round(S_initial - S_current, 4))

    pct_loss_at_equilibrium = ((S_initial - S_equilibrium) / S_initial * 100) if S_initial > 0 else 0.0
    pct_loss_realized_final_year = ((S_initial - S_current) / S_initial * 100) if S_initial > 0 else 0.0

    return {
        "sar_constant_c": sar_c,
        "sar_exponent_z": sar_z,
        "initial_area_ha": initial_area_ha,
        "final_area_ha": final_area_ha,
        "species_richness_initial": round(S_initial, 4),
        "species_richness_equilibrium": round(S_equilibrium, 4),
        "extinction_debt_total_species": round(total_debt, 4),
        "species_richness_timeseries": richness_timeseries,
        "extinction_debt_realized_timeseries": realized_loss_timeseries,
        "pct_loss_at_new_equilibrium": round(pct_loss_at_equilibrium, 4),
        "pct_loss_realized_by_final_year": round(pct_loss_realized_final_year, 4),
        "years_simulated": years,
        "data_confidence": "medium (c y z son defaults ilustrativos, no especificos de bioma real)",
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

    # Caso 6: habitat_area_loss con area constante (sin perdida) -> equilibrio == inicial, deuda 0
    r7 = _habitat_area_loss(100000, 100000, years=5)
    ok6 = abs(r7["extinction_debt_total_species"]) < 1e-9 and abs(r7["pct_loss_at_new_equilibrium"]) < 1e-9
    checks.append(("habitat_area_loss_no_change_zero_debt", ok6))

    # Caso 7: habitat_area_loss con area final = 0 -> equilibrio = 0, perdida 100%
    r8 = _habitat_area_loss(50000, 0, years=5)
    ok7 = abs(r8["species_richness_equilibrium"]) < 1e-9 and abs(r8["pct_loss_at_new_equilibrium"] - 100.0) < 1e-6
    checks.append(("habitat_area_loss_total_loss_at_zero_area", ok7))

    # Caso 8: habitat_area_loss -- la riqueza realizada nunca supera la de equilibrio
    # en magnitud de perdida (convergencia monotona hacia el equilibrio)
    r9 = _habitat_area_loss(200000, 90000, years=25, relaxation_rate=0.1)
    ok8 = r9["pct_loss_realized_by_final_year"] <= r9["pct_loss_at_new_equilibrium"] + 1e-6
    checks.append(("habitat_area_loss_realized_bounded_by_equilibrium", ok8))

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
        "estimador de riqueza Chao1) a partir de datos de abundancia por especie, "
        "y estima impacto de perdida de habitat sobre riqueza de especies via "
        "relacion especies-area (Arrhenius) con deuda de extincion (habitat_area_loss). "
        "No hace interpretacion ecologica causal, solo devuelve las metricas calculadas."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["shannon", "simpson", "chao1", "summary", "habitat_area_loss", "validate"],
                "description": "Metrica a calcular, o 'validate' para autotest",
            },
            "abundances": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Abundancia (conteo de individuos) por especie (modos shannon/simpson/chao1/summary)",
            },
            "initial_area_ha": {"type": "number", "description": "Area de habitat inicial en ha (modo habitat_area_loss)"},
            "final_area_ha": {"type": "number", "description": "Area de habitat remanente en ha (modo habitat_area_loss)"},
            "sar_c": {"type": "number", "description": "Constante c de S=c*A^z (default 5.0, modo habitat_area_loss)"},
            "sar_z": {"type": "number", "description": "Exponente z de S=c*A^z (default 0.27, modo habitat_area_loss)"},
            "years": {"type": "integer", "description": "Anios a simular la relajacion de la deuda de extincion (default 30)"},
            "relaxation_rate": {"type": "number", "description": "Fraccion de la deuda saldada cada anio (default 0.08)"},
        },
        "required": ["mode"],
    },
}


def compute_biodiversity_model_tool(mode, **kwargs):
    if mode == "validate":
        return _validate()

    if mode == "habitat_area_loss":
        initial_area_ha = kwargs.get("initial_area_ha")
        final_area_ha = kwargs.get("final_area_ha")
        if initial_area_ha is None or final_area_ha is None:
            raise ValueError("Se requieren 'initial_area_ha' y 'final_area_ha' para mode='habitat_area_loss'")
        return {
            "mode": mode,
            **_habitat_area_loss(
                float(initial_area_ha),
                float(final_area_ha),
                sar_c=float(kwargs.get("sar_c", 5.0)),
                sar_z=float(kwargs.get("sar_z", 0.27)),
                years=int(kwargs.get("years", 30)),
                relaxation_rate=float(kwargs.get("relaxation_rate", 0.08)),
            ),
        }

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


try:
    from tool_registry import register_tool as _register_tool_real
    _register_tool_real(
        name="biodiversity_model_tool",
        schema=BIODIVERSITY_MODEL_TOOL_SCHEMA,
        handler=lambda args: compute_biodiversity_model_tool(
            args.get("mode"),
            **{k: v for k, v in args.items() if k != "mode"}
        ),
    )
except ImportError:
    pass
