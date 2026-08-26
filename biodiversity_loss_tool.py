"""
biodiversity_loss_tool.py

Modelo agregado estándar de pérdida de biodiversidad basado en la relación
especies-área (SAR, Arrhenius):

    S = c * A^z

donde S es riqueza de especies, A es área de hábitat, c es una constante
específica del bioma/taxón y z es el exponente empírico (típicamente
0.20-0.35 para la mayoría de biomas terrestres).

Incorpora "deuda de extinción": cuando el hábitat se reduce, no todas las
especies condenadas se extinguen inmediatamente; se relaja hacia el nuevo
equilibrio S_final a una tasa anual (relaxation_rate).

Convención del módulo:
    biodiversity_loss_tool(params: dict) -> dict
"""

from dataclasses import dataclass
from typing import List, Dict


@dataclass
class BiodiversityLossParams:
    initial_habitat_area_ha: float = 100_000.0
    final_habitat_area_ha: float = 60_000.0     # área remanente tras el disturbio
    sar_constant_c: float = 5.0                  # constante c de la relación S = c*A^z
    sar_exponent_z: float = 0.27                 # exponente empírico típico
    years: int = 30
    extinction_debt_relaxation_rate: float = 0.08  # fracción de la deuda que se salda cada año


def biodiversity_loss_tool(params: dict) -> dict:
    p = BiodiversityLossParams(**params) if not isinstance(params, BiodiversityLossParams) else params

    def species_richness(area_ha: float) -> float:
        if area_ha <= 0:
            return 0.0
        return p.sar_constant_c * (area_ha ** p.sar_exponent_z)

    S_initial = species_richness(p.initial_habitat_area_ha)
    S_equilibrium_final = species_richness(p.final_habitat_area_ha)  # equilibrio a largo plazo tras la pérdida

    # Deuda de extinción: la riqueza observada decae gradualmente desde
    # S_initial hasta S_equilibrium_final, no de forma instantánea.
    S_current = S_initial
    richness_series: List[float] = [round(S_current, 2)]
    committed_extinctions_realized: List[float] = [0.0]

    total_debt = S_initial - S_equilibrium_final  # especies "condenadas" por la pérdida de área

    for year in range(1, p.years + 1):
        gap = S_current - S_equilibrium_final
        S_current = S_current - gap * p.extinction_debt_relaxation_rate
        richness_series.append(round(S_current, 2))
        realized = S_initial - S_current
        committed_extinctions_realized.append(round(realized, 2))

    pct_loss_final_equilibrium = ((S_initial - S_equilibrium_final) / S_initial * 100
                                   if S_initial > 0 else 0.0)
    pct_loss_realized_so_far = ((S_initial - S_current) / S_initial * 100
                                 if S_initial > 0 else 0.0)

    return {
        "years_simulated": p.years,
        "initial_habitat_area_ha": p.initial_habitat_area_ha,
        "final_habitat_area_ha": p.final_habitat_area_ha,
        "species_richness_initial_estimate": round(S_initial, 2),
        "species_richness_equilibrium_estimate": round(S_equilibrium_final, 2),
        "species_richness_timeseries": richness_series,
        "extinction_debt_total_species": round(total_debt, 2),
        "extinction_debt_realized_timeseries": committed_extinctions_realized,
        "pct_biodiversity_loss_at_new_equilibrium": round(pct_loss_final_equilibrium, 2),
        "pct_biodiversity_loss_realized_by_final_year": round(pct_loss_realized_so_far, 2),
    }


if __name__ == "__main__":
    test_params = {
        "initial_habitat_area_ha": 200_000,
        "final_habitat_area_ha": 90_000,
        "sar_constant_c": 6.0,
        "sar_exponent_z": 0.28,
        "years": 25,
        "extinction_debt_relaxation_rate": 0.1,
    }
    result = biodiversity_loss_tool(test_params)
    print("=== biodiversity_loss_tool self-test ===")
    print("Riqueza inicial estimada:", result["species_richness_initial_estimate"])
    print("Riqueza de equilibrio (tras pérdida de hábitat):", result["species_richness_equilibrium_estimate"])
    print("Deuda de extinción total (especies):", result["extinction_debt_total_species"])
    print("% pérdida en equilibrio final:", result["pct_biodiversity_loss_at_new_equilibrium"])
    print("% pérdida realizada al año", test_params["years"], ":", result["pct_biodiversity_loss_realized_by_final_year"])
    assert result["species_richness_equilibrium_estimate"] <= result["species_richness_initial_estimate"]
    assert result["pct_biodiversity_loss_realized_by_final_year"] <= result["pct_biodiversity_loss_at_new_equilibrium"] + 0.01
    print("OK: riqueza decreciente, deuda de extinción consistente.")
