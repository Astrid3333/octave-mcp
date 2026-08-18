"""
vacuum_energy_density_tool.py

Herramienta para octave-mcp: energia de punto cero de un campo cuantico
(regularizada con un cutoff duro en momento) versus la densidad de
energia oscura observada, para cuantificar explicitamente el problema
de la constante cosmologica.

ENFOQUE (explicito y honesto):
Esto es el calculo de libro de texto (Martin 2012, "Everything you
always wanted to know about the cosmological constant problem"), NO una
derivacion de QFT completa con renormalizacion. El punto de todo el
problema es precisamente que este calculo ingenuo con cutoff duro es
regularization-scheme-dependent (dimensional regularization da un
resultado distinto y mas sutil), pero el orden de magnitud del desajuste
resultante (~120 ordenes) es el numero que aparece en toda la literatura
y motiva el problema.

Fisica:
Para un campo cuantico libre sin masa con g grados de libertad (g=2 para
el campo electromagnetico, 2 polarizaciones), la energia de punto cero
por modo es (1/2)*hbar*omega_k = (1/2)*hbar*c*k. Sumando (integrando) en
tres dimensiones hasta un cutoff duro Lambda en el numero de onda k:

    rho_vac(Lambda) = g * Integral_0^Lambda [d^3k/(2*pi)^3] * (1/2)*hbar*c*k
                     = g * hbar * c * Lambda^4 / (16*pi^2)

Este calculo se hace tanto analiticamente (formula cerrada de arriba)
como numericamente (cuadratura de la integral radial), y ambos se
comparan en el self_test.

La densidad de energia oscura observada se obtiene de los parametros
cosmologicos estandar:

    rho_crit = 3*H0^2*c^2 / (8*pi*G)      (densidad critica, energia)
    rho_DE_obs = Omega_Lambda * rho_crit

mode: "self_test"
  1. Compara la formula analitica rho_vac(Lambda) contra cuadratura
     numerica de la integral radial (deben coincidir a precision de
     maquina, es la misma integral).
  2. Sanity check de orden de magnitud: el cociente rho_vac(Lambda_Planck)
     / rho_DE_obs (con parametros cosmologicos estandar) debe caer en el
     rango ~10^110 - 10^130, que es el rango citado en la literatura del
     problema de la constante cosmologica (Weinberg 1989, Martin 2012).
  3. Verifica que las constantes de Planck derivadas (masa, longitud,
     energia) satisfacen las relaciones dimensionales exactas entre ellas
     (m_Pl*c^2 == E_Pl, l_Pl == hbar/(m_Pl*c), etc.) usando solo hbar, c, G.

mode: "cutoff_comparison"
  Dado un cutoff (preset: "planck", "gut", "electroweak", "qcd", o un
  valor de energia custom en GeV) y parametros cosmologicos (H0, Omega_Lambda),
  devuelve rho_vac teorico, rho_DE observado, el cociente, y cuantos
  ordenes de magnitud de diferencia hay -- el numero central del problema
  de la constante cosmologica.

NOTA DE ALCANCE: cutoff duro en 3-momento, campo libre sin masa, sin
renormalizacion. Es el calculo estandar que aparece en todo texto de
introduccion al problema, explicitamente NO el estado del arte de QFT en
espacio curvo.
"""

import numpy as np
from scipy.integrate import quad
from tool_registry import register_tool


# ---------------------------------------------------------------------------
# Constantes fisicas (CODATA / valores estandar), SI
# ---------------------------------------------------------------------------

HBAR = 1.054571817e-34   # J*s
C = 2.99792458e8         # m/s
G = 6.67430e-11          # m^3 kg^-1 s^-2
GEV_TO_JOULE = 1.602176634e-10  # 1 GeV en Joules
MPC_TO_M = 3.0856775814913673e22  # 1 megaparsec en metros


# ---------------------------------------------------------------------------
# Energia de punto cero: analitica + numerica
# ---------------------------------------------------------------------------

def _rho_vac_analytic(Lambda_k, g=2.0):
    """rho_vac(Lambda) = g*hbar*c*Lambda^4 / (16*pi^2), Lambda en 1/m."""
    return g * HBAR * C * Lambda_k ** 4 / (16.0 * np.pi ** 2)


def _rho_vac_numeric(Lambda_k, g=2.0):
    """Misma integral por cuadratura: g * (4*pi*k^2)/(2*pi)^3 * (hbar*c*k/2), 0..Lambda."""
    integrand = lambda k: g * (4.0 * np.pi * k ** 2) / (2.0 * np.pi) ** 3 * (0.5 * HBAR * C * k)
    val, _ = quad(integrand, 0.0, Lambda_k, limit=200)
    return val


def _lambda_from_energy_GeV(E_GeV):
    """Cutoff en numero de onda (1/m) correspondiente a una energia en GeV,
    via k = E/(hbar*c)."""
    E_J = E_GeV * GEV_TO_JOULE
    return E_J / (HBAR * C)


# ---------------------------------------------------------------------------
# Cosmologia observacional
# ---------------------------------------------------------------------------

def _H0_si(H0_km_s_Mpc):
    """Convierte H0 de km/s/Mpc a 1/s."""
    return (H0_km_s_Mpc * 1000.0) / MPC_TO_M


def _rho_crit(H0_km_s_Mpc):
    """Densidad critica de energia, J/m^3."""
    H0 = _H0_si(H0_km_s_Mpc)
    return 3.0 * H0 ** 2 * C ** 2 / (8.0 * np.pi * G)


def _rho_DE_observed(H0_km_s_Mpc, Omega_Lambda):
    return Omega_Lambda * _rho_crit(H0_km_s_Mpc)


# ---------------------------------------------------------------------------
# Escalas de Planck (derivadas, no hardcodeadas)
# ---------------------------------------------------------------------------

def _planck_mass():
    return np.sqrt(HBAR * C / G)


def _planck_length():
    return np.sqrt(HBAR * G / C ** 3)


def _planck_energy_GeV():
    E_J = _planck_mass() * C ** 2
    return E_J / GEV_TO_JOULE


# ---------------------------------------------------------------------------
# Presets de cutoff (escala de energia en GeV)
# ---------------------------------------------------------------------------

def _cutoff_presets():
    return {
        "planck": _planck_energy_GeV(),
        "gut": 2.0e16,           # escala tipica de Gran Unificacion
        "electroweak": 246.0,    # vev de Higgs, GeV
        "qcd": 0.2,              # escala de confinamiento QCD, GeV
    }


# ---------------------------------------------------------------------------
# self_test
# ---------------------------------------------------------------------------

def _self_test():
    results = {}

    # --- Test 1: formula analitica vs cuadratura numerica ---------------
    Lambda_test = _lambda_from_energy_GeV(100.0)  # cutoff arbitrario, 100 GeV
    rho_an = _rho_vac_analytic(Lambda_test)
    rho_num = _rho_vac_numeric(Lambda_test)
    rel_err = abs(rho_an - rho_num) / rho_an

    results["analytic_vs_numeric_integral"] = {
        "Lambda_k_1_per_m": Lambda_test,
        "rho_analytic_J_per_m3": rho_an,
        "rho_numeric_J_per_m3": rho_num,
        "relative_error": rel_err,
        "pass": bool(rel_err < 1e-8),
    }

    # --- Test 2: orden de magnitud del problema (cutoff de Planck) ------
    H0_std, Omega_L_std = 67.4, 0.685  # Planck 2018, valores estandar
    Lambda_Pl = _lambda_from_energy_GeV(_planck_energy_GeV())
    rho_theory = _rho_vac_analytic(Lambda_Pl)
    rho_obs = _rho_DE_observed(H0_std, Omega_L_std)
    ratio = rho_theory / rho_obs
    orders_of_magnitude = float(np.log10(ratio))

    results["cosmological_constant_problem_magnitude"] = {
        "rho_theory_planck_cutoff_J_per_m3": rho_theory,
        "rho_observed_J_per_m3": rho_obs,
        "ratio": ratio,
        "orders_of_magnitude": orders_of_magnitude,
        "expected_range": [100, 130],
        "note": (
            "El valor citado en la literatura estandar (Weinberg 1989, "
            "Martin 2012) es ~120 ordenes de magnitud para este calculo "
            "de cutoff duro; el rango de sanity check es deliberadamente "
            "amplio porque el numero exacto depende de convenciones de "
            "regularizacion y de los valores cosmologicos usados."
        ),
        "pass": bool(100.0 < orders_of_magnitude < 130.0),
    }

    # --- Test 3: consistencia dimensional de las escalas de Planck ------
    m_Pl = _planck_mass()
    l_Pl = _planck_length()
    E_Pl_J = m_Pl * C ** 2
    l_Pl_from_m_Pl = HBAR / (m_Pl * C)  # relacion de De Broglie, debe dar l_Pl
    rel_err_length = abs(l_Pl_from_m_Pl - l_Pl) / l_Pl

    results["planck_scale_self_consistency"] = {
        "m_Pl_kg": m_Pl,
        "l_Pl_m": l_Pl,
        "E_Pl_GeV": E_Pl_J / GEV_TO_JOULE,
        "l_Pl_from_debroglie_relative_error": rel_err_length,
        "pass": bool(rel_err_length < 1e-10),
    }

    all_pass = all(r["pass"] for r in results.values())
    return {"mode": "self_test", "all_pass": bool(all_pass), "tests": results}


# ---------------------------------------------------------------------------
# cutoff_comparison
# ---------------------------------------------------------------------------

def _cutoff_comparison(params):
    presets = _cutoff_presets()

    preset_name = params.get("cutoff_preset")
    custom_GeV = params.get("cutoff_energy_GeV")

    if custom_GeV is not None:
        E_GeV = float(custom_GeV)
        label = f"custom ({E_GeV:g} GeV)"
    elif preset_name is not None:
        if preset_name not in presets:
            raise ValueError(f"cutoff_preset debe ser uno de {sorted(presets.keys())}")
        E_GeV = presets[preset_name]
        label = preset_name
    else:
        preset_name = "planck"
        E_GeV = presets[preset_name]
        label = preset_name

    g = float(params.get("g_dof", 2.0))
    H0 = float(params.get("H0_km_s_Mpc", 67.4))
    Omega_L = float(params.get("Omega_Lambda", 0.685))

    Lambda_k = _lambda_from_energy_GeV(E_GeV)
    rho_theory = _rho_vac_analytic(Lambda_k, g=g)
    rho_obs = _rho_DE_observed(H0, Omega_L)
    ratio = rho_theory / rho_obs
    orders_of_magnitude = float(np.log10(ratio)) if ratio > 0 else None

    return {
        "mode": "cutoff_comparison",
        "cutoff_label": label,
        "cutoff_energy_GeV": E_GeV,
        "cutoff_k_1_per_m": Lambda_k,
        "g_degrees_of_freedom": g,
        "cosmology_used": {"H0_km_s_Mpc": H0, "Omega_Lambda": Omega_L},
        "rho_vacuum_theory_J_per_m3": rho_theory,
        "rho_dark_energy_observed_J_per_m3": rho_obs,
        "ratio_theory_over_observed": ratio,
        "orders_of_magnitude_discrepancy": orders_of_magnitude,
        "note": (
            "Calculo de energia de punto cero con cutoff duro en momento, "
            "campo libre sin masa (g=2 default, tipo electromagnetico). "
            "No incluye renormalizacion ni corrimiento por gravedad "
            "cuantica; es el calculo estandar de libro de texto que "
            "expone el problema de la constante cosmologica, no una "
            "prediccion de QFT en espacio curvo de ultima generacion."
        ),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def compute_vacuum_energy_density_tool(mode, params=None):
    params = params or {}
    if mode == "self_test":
        return _self_test()
    elif mode == "cutoff_comparison":
        return _cutoff_comparison(params)
    else:
        return {"error": f"Modo desconocido: {mode}. Modos validos: self_test, cutoff_comparison."}


VACUUM_ENERGY_DENSITY_TOOL_SCHEMA = {
    "name": "vacuum_energy_density_tool",
    "description": (
        "Energia de punto cero de un campo cuantico libre sin masa, con cutoff "
        "duro en momento: rho_vac(Lambda) = g*hbar*c*Lambda^4/(16*pi^2), g=2 "
        "default (tipo electromagnetico). Comparada contra la densidad de "
        "energia oscura observada rho_DE = Omega_Lambda*3*H0^2*c^2/(8*pi*G). "
        "Es el calculo estandar de libro de texto (Weinberg 1989, Martin 2012) "
        "que expone el problema de la constante cosmologica -- NO renormalizacion "
        "de QFT en espacio curvo de ultima generacion. mode=self_test: formula "
        "analitica vs cuadratura numerica de la misma integral, sanity check de "
        "que el desajuste con cutoff de Planck cae en ~100-130 ordenes de "
        "magnitud (rango citado en la literatura), y consistencia dimensional "
        "de las escalas de Planck derivadas de hbar/c/G. mode=cutoff_comparison: "
        "dado un cutoff (preset planck/gut/electroweak/qcd o valor custom en GeV) "
        "y parametros cosmologicos, devuelve rho_teorico, rho_observado, cociente "
        "y ordenes de magnitud de discrepancia."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["self_test", "cutoff_comparison"]},
            "params": {
                "type": "object",
                "properties": {
                    "cutoff_preset": {"type": "string", "enum": ["planck", "gut", "electroweak", "qcd"], "description": "Escala de cutoff predefinida (default 'planck')"},
                    "cutoff_energy_GeV": {"type": "number", "description": "Cutoff custom en GeV, tiene prioridad sobre cutoff_preset"},
                    "g_dof": {"type": "number", "description": "Grados de libertad / polarizaciones del campo (default 2.0, tipo EM)"},
                    "H0_km_s_Mpc": {"type": "number", "description": "Constante de Hubble en km/s/Mpc (default 67.4, Planck 2018)"},
                    "Omega_Lambda": {"type": "number", "description": "Fraccion de densidad critica en energia oscura (default 0.685)"},
                },
            },
        },
        "required": ["mode"],
    },
}


register_tool(
    name="vacuum_energy_density_tool",
    schema=VACUUM_ENERGY_DENSITY_TOOL_SCHEMA,
    handler=lambda args: compute_vacuum_energy_density_tool(
        args.get("mode"), args.get("params")
    ),
)


if __name__ == "__main__":
    import json
    print(json.dumps(compute_vacuum_energy_density_tool("self_test"), indent=2))
    print(json.dumps(compute_vacuum_energy_density_tool("cutoff_comparison", {"cutoff_preset": "planck"}), indent=2))
