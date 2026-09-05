"""
ree_solvent_extraction_tool.py

Cascada de extraccion por solventes (SX, mixer-settlers) a contracorriente
para separacion de tierras raras (REE) adyacentes (ej. Nd/Pr, Sm/Nd).

Modos:
  stage_count   -> Fenske: numero minimo de etapas para una separacion dada
  mccabe_thiele -> perfil etapa por etapa (recursion tipo Kremser, equivalente
                   numerico al metodo grafico McCabe-Thiele) dado D_A, D_B y
                   razon de flujos O/A
  validate      -> autochequeo (6 checks)

Convenciones:
  beta = D_A / D_B = factor de separacion entre el elemento A (mas extraible,
         ej. Nd con extractantes acidicos) y B (menos extraible, ej. Pr).
         beta > 1 siempre (si A es el que mas se extrae).
  feed_ratio    = [A]/[B] en la alimentacion
  product_ratio = [A]/[B] objetivo en el producto (pureza deseada)
"""

import math

REE_SOLVENT_EXTRACTION_TOOL_SCHEMA = {
    "name": "ree_solvent_extraction_tool",
    "description": (
        "Cascada de extraccion por solventes (SX) para separacion de tierras "
        "raras adyacentes. Fenske (stage_count) para etapas minimas teoricas, "
        "y una simulacion etapa-por-etapa tipo McCabe-Thiele/Kremser "
        "(mccabe_thiele) para el perfil real dado O/A y coeficientes de "
        "distribucion."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["stage_count", "mccabe_thiele", "validate"],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


def _stage_count(beta, feed_ratio, product_ratio):
    """
    Ecuacion de Fenske: numero minimo de etapas de equilibrio (reflujo total)
    para llevar una razon de concentraciones feed_ratio a product_ratio,
    con factor de separacion beta constante entre etapas.

        N_min = ln(product_ratio / feed_ratio) / ln(beta)

    beta debe ser > 1 (si fuera <=1 no hay separacion posible, o A y B se
    extraen igual y ninguna cantidad finita de etapas alcanza la pureza).
    """
    if beta <= 1:
        raise ValueError(
            f"beta debe ser > 1 para que exista separacion (recibido beta={beta})"
        )
    if feed_ratio <= 0 or product_ratio <= 0:
        raise ValueError("feed_ratio y product_ratio deben ser > 0")

    n_min = math.log(product_ratio / feed_ratio) / math.log(beta)
    n_practical = math.ceil(n_min)

    return {
        "mode": "stage_count",
        "beta": beta,
        "feed_ratio": feed_ratio,
        "product_ratio": product_ratio,
        "n_stages_min_theoretical": n_min,
        "n_stages_practical": n_practical,
        "confidence_flag": "alta",
        "note": (
            "Fenske asume beta constante en todas las etapas y reflujo total "
            "(cota inferior teorica). En operacion real con reflujo finito se "
            "necesitan mas etapas que n_stages_practical."
        ),
    }


def _kremser_fraction_remaining(D, oa_ratio, n_stages):
    """
    Fraccion de un soluto que queda en la fase acuosa tras n_stages etapas
    de equilibrio ideal, en extraccion liquido-liquido a contracorriente.

    Factor de extraccion: E = D * (O/A)
    Ecuacion de Kremser (analoga a absorcion/stripping en destilacion):
        phi_extraida = (E^(n+1) - E) / (E^(n+1) - 1)      si E != 1
        phi_extraida = n / (n+1)                           si E == 1
        phi_remanente = 1 - phi_extraida
    """
    E = D * oa_ratio
    if abs(E - 1.0) < 1e-12:
        phi_extraida = n_stages / (n_stages + 1)
    else:
        phi_extraida = (E ** (n_stages + 1) - E) / (E ** (n_stages + 1) - 1)
    phi_remanente = max(0.0, min(1.0, 1.0 - phi_extraida))
    return phi_remanente, E


def _mccabe_thiele(D_A, D_B, n_stages, oa_ratio, feed_conc_A=1.0, feed_conc_B=1.0):
    """
    Simula la cascada a contracorriente de n_stages etapas de equilibrio
    ideal, para dos solutos A (mas extraible) y B (menos extraible), dada
    la razon de flujos organico/acuoso (oa_ratio) y sus coeficientes de
    distribucion D_A = C_organico/C_acuoso, D_B idem.

    Devuelve el balance de masa final (acuoso refinado + organico extracto)
    y la pureza/recuperacion de A en el extracto organico.
    """
    if n_stages < 1:
        raise ValueError("n_stages debe ser >= 1")
    if D_A <= 0 or D_B <= 0 or oa_ratio <= 0:
        raise ValueError("D_A, D_B y oa_ratio deben ser > 0")

    rem_A, E_A = _kremser_fraction_remaining(D_A, oa_ratio, n_stages)
    rem_B, E_B = _kremser_fraction_remaining(D_B, oa_ratio, n_stages)

    aq_A = feed_conc_A * rem_A
    aq_B = feed_conc_B * rem_B
    org_A = feed_conc_A - aq_A
    org_B = feed_conc_B - aq_B

    total_org = org_A + org_B
    purity_A_extract = org_A / total_org if total_org > 0 else float("nan")

    total_aq = aq_A + aq_B
    purity_B_refined = aq_B / total_aq if total_aq > 0 else float("nan")

    return {
        "mode": "mccabe_thiele",
        "n_stages": n_stages,
        "oa_ratio": oa_ratio,
        "extraction_factor_A": E_A,
        "extraction_factor_B": E_B,
        "aqueous_refined": {"A": aq_A, "B": aq_B},
        "organic_extract": {"A": org_A, "B": org_B},
        "purity_A_in_extract": purity_A_extract,
        "purity_B_in_refined": purity_B_refined,
        "recovery_A_pct": (org_A / feed_conc_A * 100.0) if feed_conc_A > 0 else float("nan"),
        "mass_balance_check_A": aq_A + org_A,
        "mass_balance_check_B": aq_B + org_B,
        "confidence_flag": "media",
        "note": (
            "Modelo de etapas de equilibrio ideal (Kremser), equivalente "
            "numerico al metodo grafico McCabe-Thiele. No modela eficiencia "
            "de etapa real (mixer-settler <100% eficiente) ni cinetica de "
            "transferencia de masa."
        ),
    }


def _validate():
    checks = []

    # 1) Formula de Fenske exacta
    r1 = _stage_count(beta=2.5, feed_ratio=1.0, product_ratio=99.0)
    expected_n = math.log(99.0) / math.log(2.5)
    checks.append({
        "name": "fenske_formula",
        "passed": bool(abs(r1["n_stages_min_theoretical"] - expected_n) < 1e-9),
    })

    # 2) n_practical siempre >= n_theoretical (redondeo hacia arriba)
    checks.append({
        "name": "fenske_ceil",
        "passed": bool(r1["n_stages_practical"] >= r1["n_stages_min_theoretical"]),
    })

    # 3) beta <= 1 debe rechazarse (sin separacion posible)
    try:
        _stage_count(beta=1.0, feed_ratio=1.0, product_ratio=10.0)
        beta_check = False
    except ValueError:
        beta_check = True
    checks.append({"name": "fenske_rejects_beta_le_1", "passed": bool(beta_check)})

    # 4) McCabe-Thiele a 1 etapa debe coincidir con la formula de extraccion
    #    batch de una sola etapa: fraccion remanente = 1/(1+D*R)
    D_test, R_test = 3.0, 0.5
    r4 = _mccabe_thiele(D_A=D_test, D_B=0.5, n_stages=1, oa_ratio=R_test,
                         feed_conc_A=1.0, feed_conc_B=1.0)
    expected_rem_1stage = 1.0 / (1.0 + D_test * R_test)
    got_rem_1stage = r4["aqueous_refined"]["A"]
    checks.append({
        "name": "mccabe_single_stage_matches_batch_formula",
        "passed": bool(abs(got_rem_1stage - expected_rem_1stage) < 1e-9),
    })

    # 5) Mas etapas -> mas extraccion (monotonia), cuando E>1
    r5a = _mccabe_thiele(D_A=2.0, D_B=0.4, n_stages=2, oa_ratio=1.0)
    r5b = _mccabe_thiele(D_A=2.0, D_B=0.4, n_stages=6, oa_ratio=1.0)
    checks.append({
        "name": "mccabe_more_stages_extracts_more",
        "passed": bool(r5b["aqueous_refined"]["A"] < r5a["aqueous_refined"]["A"]),
    })

    # 6) Conservacion de masa: acuoso + organico == feed, para A y B
    r6 = _mccabe_thiele(D_A=1.8, D_B=0.3, n_stages=4, oa_ratio=0.8,
                         feed_conc_A=1.0, feed_conc_B=1.0)
    mass_ok = (
        abs(r6["mass_balance_check_A"] - 1.0) < 1e-9
        and abs(r6["mass_balance_check_B"] - 1.0) < 1e-9
    )
    checks.append({"name": "mccabe_conserves_mass", "passed": bool(mass_ok)})

    n_passed = sum(1 for c in checks if c["passed"])
    return {
        "validation_passed": n_passed == len(checks),
        "n_passed": n_passed,
        "n_checks": len(checks),
        "checks": checks,
    }


def compute_ree_solvent_extraction_tool(mode, **kwargs):
    if mode == "validate":
        return _validate()
    if mode == "stage_count":
        return _stage_count(
            beta=kwargs["beta"],
            feed_ratio=kwargs["feed_ratio"],
            product_ratio=kwargs["product_ratio"],
        )
    if mode == "mccabe_thiele":
        return _mccabe_thiele(
            D_A=kwargs["D_A"],
            D_B=kwargs["D_B"],
            n_stages=kwargs["n_stages"],
            oa_ratio=kwargs["oa_ratio"],
            feed_conc_A=kwargs.get("feed_conc_A", 1.0),
            feed_conc_B=kwargs.get("feed_conc_B", 1.0),
        )
    raise ValueError(f"modo desconocido: {mode}")


def _register():
    try:
        import tool_registry
        tool_registry.register_tool(
            "ree_solvent_extraction_tool",
            REE_SOLVENT_EXTRACTION_TOOL_SCHEMA,
            lambda args: compute_ree_solvent_extraction_tool(
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
        {
            "validation_passed": result["validation_passed"],
            "n_passed": result["n_passed"],
            "n_checks": result["n_checks"],
        },
        indent=2,
    ))
