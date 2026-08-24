"""
pair_production_tool.py

Seccion eficaz de creacion de pares por colision foton-foton (Breit-Wheeler,
gamma+gamma -> e+ + e-), en la forma de Gould & Schreder 1967 -- la
parametrizacion estandar usada en calculos de opacidad gamma-gamma de fondos
extragalacticos de luz (EBL) y de espectros de blazares TeV.

Formula central:

    sigma(beta) = (3*sigma_T/16) * (1-beta^2) *
                  [ (3-beta^4)*ln((1+beta)/(1-beta)) - 2*beta*(2-beta^2) ]

    beta = sqrt(1 - 1/s_tilde)
    s_tilde = (eps1 * eps2 * (1-cos(theta))) / (2 * (m_e*c^2)^2)

donde:
    eps1, eps2 = energias de los dos fotones (erg, CGS)
    theta      = angulo de colision entre los dos fotones
    sigma_T    = seccion eficaz de Thomson = (8*pi/3)*r_e^2
    s_tilde    = variable de Mandelstam adimensional; el umbral fisico de
                 creacion de pares es s_tilde=1 (para colision frontal
                 theta=pi, esto equivale a eps1*eps2 >= (m_e*c^2)^2)

Para s_tilde < 1 (por debajo del umbral cinematico) la seccion eficaz es
identicamente 0 -- no hay canal abierto.

Verificado numericamente antes de wireear (mismo criterio que synchrotron):
el pico de sigma/sigma_T ~ 0.256 en s_tilde ~ 2 coincide con el valor citado
en la literatura de opacidad de blazares TeV (Gould & Schreder 1967;
Aharonian, "Very High Energy Cosmic Gamma Radiation"), confirmado por barrido
numerico independiente, no copiado de memoria sin verificar.

Unidades: CGS-Gaussian, energias de foton en erg.
"""

import math

# ---------------------------------------------------------------------------
# Constantes fisicas (CGS-Gaussian)
# ---------------------------------------------------------------------------
M_E_C2_ERG = 8.187105776823886e-07  # m_e*c^2 en erg (511 keV)
SIGMA_THOMSON = 6.6524587321e-25    # seccion eficaz de Thomson, cm^2


# ---------------------------------------------------------------------------
# Nucleo matematico (generico, funcion de s_tilde adimensional)
# ---------------------------------------------------------------------------

def _s_tilde(eps1_erg, eps2_erg, cos_theta):
    """s_tilde = eps1*eps2*(1-cos(theta)) / (2*(m_e*c^2)^2), umbral en 1"""
    return (eps1_erg * eps2_erg * (1.0 - cos_theta)) / (2.0 * M_E_C2_ERG**2)


def _beta_cm(s_tilde):
    """velocidad (en unidades de c) del par e+/e- en el sistema centro de masa"""
    if s_tilde < 1.0:
        return None  # por debajo del umbral cinematico, canal cerrado
    return math.sqrt(1.0 - 1.0 / s_tilde)


def _sigma_breit_wheeler(s_tilde):
    """
    Seccion eficaz de Breit-Wheeler (Gould & Schreder 1967), en cm^2.
    Identicamente 0 por debajo del umbral s_tilde=1.
    """
    beta = _beta_cm(s_tilde)
    if beta is None or beta <= 0.0:
        return 0.0

    bracket = (3.0 - beta**4) * math.log((1.0 + beta) / (1.0 - beta)) - 2.0 * beta * (2.0 - beta**2)
    return (3.0 * SIGMA_THOMSON / 16.0) * (1.0 - beta**2) * bracket


def _cross_section_from_photon_energies(eps1_erg, eps2_erg, cos_theta):
    s_t = _s_tilde(eps1_erg, eps2_erg, cos_theta)
    sigma = _sigma_breit_wheeler(s_t)
    beta = _beta_cm(s_t)
    return {
        "s_tilde": s_t,
        "beta_cm": beta,
        "sigma_cm2": sigma,
        "sigma_over_sigma_thomson": sigma / SIGMA_THOMSON,
        "por_encima_del_umbral": s_t >= 1.0,
    }


def _threshold_energy_erg(eps_fixed_erg, cos_theta):
    """
    Dado un foton de energia fija (eps_fixed_erg) y un angulo de colision,
    devuelve la energia minima del segundo foton para abrir el canal
    (s_tilde=1): eps2_umbral = 2*(m_e*c^2)^2 / (eps1*(1-cos_theta))
    """
    denom = eps_fixed_erg * (1.0 - cos_theta)
    if denom <= 0.0:
        return None  # colision imposible (fotones paralelos o energia nula)
    return 2.0 * M_E_C2_ERG**2 / denom


# ---------------------------------------------------------------------------
# Validacion
# ---------------------------------------------------------------------------

def _validate_pair_production():
    checks = []

    # Check 1: sigma=0 exactamente en el umbral (beta=0 -> bracket=0)
    sigma_at_threshold = _sigma_breit_wheeler(1.0)
    checks.append({
        "name": "seccion eficaz es 0 exactamente en el umbral s_tilde=1 (beta=0)",
        "passed": bool(abs(sigma_at_threshold) < 1e-40),
        "sigma_obtenido": sigma_at_threshold,
    })

    # Check 2: sigma=0 identicamente por debajo del umbral
    sigma_below = _sigma_breit_wheeler(0.5)
    checks.append({
        "name": "seccion eficaz identicamente 0 por debajo del umbral cinematico",
        "passed": bool(sigma_below == 0.0),
        "sigma_obtenido": sigma_below,
    })

    # Check 3: el pico de sigma/sigma_T esta cerca de 0.256 en s_tilde~2
    # (valor confirmado por barrido numerico independiente contra la
    # literatura de opacidad de blazares TeV -- Gould & Schreder 1967)
    s_grid = [1.0 + 0.01 * i for i in range(1, 1000)]
    ratios = [_sigma_breit_wheeler(s) / SIGMA_THOMSON for s in s_grid]
    peak_idx = ratios.index(max(ratios))
    s_peak = s_grid[peak_idx]
    ratio_peak = ratios[peak_idx]
    checks.append({
        "name": "pico de sigma/sigma_Thomson ~0.256 en s_tilde~2 (Gould & Schreder 1967)",
        "passed": bool(abs(ratio_peak - 0.256) < 0.01 and abs(s_peak - 2.0) < 0.3),
        "s_tilde_peak_encontrado": s_peak,
        "ratio_peak_encontrado": ratio_peak,
    })

    # Check 4: sigma nunca supera sigma_Thomson (cota fisica: Breit-Wheeler
    # es sustancialmente menor que Thomson en todo el rango)
    all_below_thomson = all(r < 1.0 for r in ratios)
    checks.append({
        "name": "sigma < sigma_Thomson en todo el rango muestreado (cota fisica)",
        "passed": bool(all_below_thomson),
    })

    # Check 5: decaimiento a alta energia (s_tilde grande -> sigma decae)
    ratio_100 = _sigma_breit_wheeler(100.0) / SIGMA_THOMSON
    ratio_1e6 = _sigma_breit_wheeler(1e6) / SIGMA_THOMSON
    checks.append({
        "name": "seccion eficaz decae al aumentar s_tilde mas alla del pico (comportamiento ultrarelativista)",
        "passed": bool(ratio_1e6 < ratio_100 < ratio_peak),
        "ratio_s100": ratio_100,
        "ratio_s1e6": ratio_1e6,
    })

    # Check 6: simetria eps1<->eps2 (la formula depende solo del producto)
    eps_a, eps_b = 2.0e-6, 3.0e-6  # erg, del orden de GeV
    cos_theta_test = -1.0  # colision frontal
    res_ab = _cross_section_from_photon_energies(eps_a, eps_b, cos_theta_test)
    res_ba = _cross_section_from_photon_energies(eps_b, eps_a, cos_theta_test)
    checks.append({
        "name": "seccion eficaz simetrica ante intercambio eps1<->eps2",
        "passed": bool(abs(res_ab["sigma_cm2"] - res_ba["sigma_cm2"]) < 1e-40),
        "sigma_ab": res_ab["sigma_cm2"],
        "sigma_ba": res_ba["sigma_cm2"],
    })

    # Check 7: umbral cinematico -- foton de 1 GeV colisionando de frente
    # necesita un segundo foton de ~ (m_e c^2)^2/E1 para abrir el canal
    # (formula de umbral clasica de opacidad de rayos gamma vs EBL)
    eps1_1gev = 1.602176634e-3  # 1 GeV en erg
    eps2_umbral = _threshold_energy_erg(eps1_1gev, -1.0)
    # confirmar que justo en el umbral s_tilde=1 y por debajo del umbral sigma=0
    s_t_at_umbral = _s_tilde(eps1_1gev, eps2_umbral, -1.0)
    s_t_below = _s_tilde(eps1_1gev, eps2_umbral * 0.9, -1.0)
    checks.append({
        "name": "energia de umbral calculada da s_tilde=1 exacto; 10% por debajo da s_tilde<1",
        "passed": bool(abs(s_t_at_umbral - 1.0) < 1e-9 and s_t_below < 1.0),
        "eps2_umbral_erg": eps2_umbral,
        "s_tilde_en_umbral": s_t_at_umbral,
        "s_tilde_90pct_del_umbral": s_t_below,
    })

    # Check 8: fotones paralelos (cos_theta=1) nunca producen pares,
    # sin importar la energia (denom=0 en el calculo de umbral)
    checks.append({
        "name": "fotones colineales (cos_theta=1) no pueden producir pares (denom=0)",
        "passed": bool(_threshold_energy_erg(eps1_1gev, 1.0) is None),
    })

    passed_all = all(c["passed"] for c in checks)
    return {
        "mode": "validate",
        "validation_passed": passed_all,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Dispatch principal
# ---------------------------------------------------------------------------

def compute_pair_production(arguments):
    """
    Handler principal. Recibe el dict completo de argumentos (patron del
    repo: un solo parametro posicional, no **kwargs).

    Modos:
      - "cross_section": sigma(eps1, eps2, cos_theta) via Breit-Wheeler
      - "threshold_energy": energia minima del segundo foton para abrir el canal
      - "validate": self-test contra limites fisicos y valores de la literatura
    """
    mode = arguments.get("mode", "cross_section")
    params = arguments.get("params", {}) or {}

    if mode == "validate":
        return _validate_pair_production()

    if mode == "cross_section":
        eps1_erg = params["eps1_erg"]
        eps2_erg = params["eps2_erg"]
        cos_theta = params.get("cos_theta", -1.0)
        result = _cross_section_from_photon_energies(eps1_erg, eps2_erg, cos_theta)
        result["mode"] = mode
        return result

    if mode == "threshold_energy":
        eps_fixed_erg = params["eps_fixed_erg"]
        cos_theta = params.get("cos_theta", -1.0)
        eps2_umbral = _threshold_energy_erg(eps_fixed_erg, cos_theta)
        return {
            "mode": mode,
            "eps2_umbral_erg": eps2_umbral,
            "nota": "energia minima del segundo foton para abrir el canal gamma+gamma->e+e-; None si cos_theta>=1 (fotones colineales, colision imposible)",
        }

    raise ValueError(f"Modo desconocido: {mode}")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

PAIR_PRODUCTION_SCHEMA = {
    "name": "pair_production_tool",
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["cross_section", "threshold_energy", "validate"],
            "description": "Modo de calculo. 'validate' corre el self-test contra limites fisicos y valores de la literatura (Gould & Schreder 1967).",
        },
        "params": {
            "type": "object",
            "description": (
                "cross_section: {eps1_erg, eps2_erg, cos_theta=-1.0 (colision frontal por default)}. "
                "threshold_energy: {eps_fixed_erg, cos_theta=-1.0}. "
                "Unidades CGS-Gaussian: energias de foton en erg."
            ),
        },
    },
    "required": ["mode"],
}


# ---------------------------------------------------------------------------
# Auto-registro
# ---------------------------------------------------------------------------

try:
    from tool_registry import register_tool

    register_tool(
        "pair_production_tool",
        PAIR_PRODUCTION_SCHEMA,
        compute_pair_production,
    )
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Self-test standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    result = compute_pair_production({"mode": "validate"})
    print(json.dumps(result, indent=2, default=str))

    if not result["validation_passed"]:
        raise SystemExit("VALIDATE FALLO -- revisar checks arriba")
    print("\nTodos los checks PASSED.")
