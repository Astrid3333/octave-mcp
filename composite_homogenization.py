"""
composite_homogenization: nuevo tool que usa sympy (mismo motor que
ocas_symbolic_tool) para derivar simbolicamente las propiedades efectivas
de un material compuesto de 2 fases via reglas de mezcla Voigt-Reuss.
"""
import sympy as sp

def voigt_reuss_symbolic():
    """
    Deriva simbolicamente las cotas de Voigt (iso-deformacion, limite superior)
    y Reuss (iso-esfuerzo, limite inferior) para una propiedad efectiva P_eff
    de un compuesto de 2 fases con fracciones de volumen f1, f2 = 1-f1 y
    propiedades P1, P2.
    """
    f1, P1, P2 = sp.symbols('f1 P1 P2', positive=True)
    f2 = 1 - f1

    # Voigt: promedio ponderado por fraccion de volumen (regla de mezclas)
    P_voigt = f1 * P1 + f2 * P2

    # Reuss: promedio armonico ponderado (iso-esfuerzo)
    P_reuss = 1 / (f1 / P1 + f2 / P2)
    P_reuss_simplified = sp.simplify(P_reuss)

    return {
        "P_voigt": P_voigt,
        "P_reuss": P_reuss_simplified,
        "symbols": {"f1": f1, "P1": P1, "P2": P2}
    }

def evaluate(f1_val, P1_val, P2_val):
    """Evalua Voigt y Reuss numericamente para valores dados."""
    result = voigt_reuss_symbolic()
    subs = {result["symbols"]["f1"]: f1_val,
            result["symbols"]["P1"]: P1_val,
            result["symbols"]["P2"]: P2_val}
    voigt_val = float(result["P_voigt"].subs(subs))
    reuss_val = float(result["P_reuss"].subs(subs))
    return voigt_val, reuss_val

def _mode_validate() -> dict:
    """Autochequeo: cotas Voigt>=Reuss, limites f1=0/1 y valor de referencia."""
    checks = []

    def _check(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    try:
        v05, r05 = evaluate(0.5, 2.0, 1.0)
        ok = abs(v05 - 1.5) < 1e-12 and abs(r05 - 4.0 / 3.0) < 1e-12
        _check("voigt_reuss_f1_half", ok, detail=f"voigt={v05}, reuss={r05}")
    except Exception as e:
        _check("voigt_reuss_f1_half", False, detail=repr(e))

    try:
        v0, r0 = evaluate(0.0, 70.0, 400.0)
        v1, r1 = evaluate(1.0, 70.0, 400.0)
        ok = abs(v0 - 400.0) < 1e-9 and abs(r0 - 400.0) < 1e-9
        ok = ok and abs(v1 - 70.0) < 1e-9 and abs(r1 - 70.0) < 1e-9
        _check("pure_phase_limits", ok,
               detail=f"f1=0:({v0},{r0}), f1=1:({v1},{r1})")
    except Exception as e:
        _check("pure_phase_limits", False, detail=repr(e))

    try:
        ordered = True
        for f in (0.1, 0.3, 0.5, 0.7, 0.9):
            v, r = evaluate(f, 70.0, 400.0)
            ordered = ordered and v >= r - 1e-12
        _check("voigt_ge_reuss", ordered, detail="Voigt >= Reuss en 5 fracciones")
    except Exception as e:
        _check("voigt_ge_reuss", False, detail=repr(e))

    try:
        v, r = evaluate(0.3, 70.0, 400.0)
        # Referencia cerrada: Voigt = f*P1+(1-f)*P2; Reuss = 1/(f/P1+(1-f)/P2)
        v_exp = 0.3 * 70.0 + 0.7 * 400.0
        r_exp = 1.0 / (0.3 / 70.0 + 0.7 / 400.0)
        _check("analytic_reference", abs(v - v_exp) < 1e-9 and abs(r - r_exp) < 1e-9,
               detail=f"voigt={v} (exp {v_exp}), reuss={r} (exp {r_exp})")
    except Exception as e:
        _check("analytic_reference", False, detail=repr(e))

    passed = sum(1 for c in checks if c["passed"])
    return {
        "mode": "validate",
        "checks": checks,
        "total_passed": passed,
        "total_checks": len(checks),
        "validation_passed": passed == len(checks),
        "status": "success" if passed == len(checks) else "failed",
    }


def compute_composite_homogenization(mode, params=None):
    """
    Firma compatible con el patron uniforme mode+params=None del resto
    del ecosistema.
    mode='elastic_modulus' o mode='thermal_conductivity' (misma matematica,
    solo cambia la interpretacion fisica de P1/P2).
    mode='validate' corre el autochequeo determinista (cotas y limites).
    params: {f1, P1, P2}  (fraccion de volumen de la fase 1, propiedad de
    fase 1, propiedad de fase 2)
    """
    if mode == "validate":
        return _mode_validate()
    params = params or {}
    f1 = params.get("f1", 0.5)
    P1 = params.get("P1", 1.0)
    P2 = params.get("P2", 1.0)
    sym = voigt_reuss_symbolic()
    voigt_val, reuss_val = evaluate(f1, P1, P2)
    return {
        "mode": mode,
        "f1": f1, "f2": 1 - f1,
        "P1": P1, "P2": P2,
        "P_voigt_expr": str(sym["P_voigt"]),
        "P_reuss_expr": str(sym["P_reuss"]),
        "P_voigt_value": voigt_val,
        "P_reuss_value": reuss_val,
        "note": "Voigt = cota superior (iso-deformacion), Reuss = cota inferior (iso-esfuerzo). El valor real del compuesto esta entre ambas."
    }

if __name__ == "__main__":
    sym = voigt_reuss_symbolic()
    print("P_voigt (simbolico) =", sym["P_voigt"])
    print("P_reuss (simbolico) =", sym["P_reuss"])

    # --- Validacion 1: casos limite ---
    # f1=0 -> el compuesto es 100% fase 2, ambas cotas deben dar P2
    v, r = evaluate(f1_val=0.0, P1_val=210e9, P2_val=70e9)  # acero/aluminio, Pa
    print(f"\n[f1=0] Voigt={v:.3e}, Reuss={r:.3e} (esperado ambos = 70e9)")
    assert abs(v - 70e9) < 1
    assert abs(r - 70e9) < 1

    # f1=1 -> 100% fase 1, ambas cotas deben dar P1
    v, r = evaluate(f1_val=1.0, P1_val=210e9, P2_val=70e9)
    print(f"[f1=1] Voigt={v:.3e}, Reuss={r:.3e} (esperado ambos = 210e9)")
    assert abs(v - 210e9) < 1
    assert abs(r - 210e9) < 1

    # --- Validacion 2: Reuss <= Voigt siempre (propiedad matematica de las cotas,
    # demostrada por la desigualdad de la media aritmetica vs armonica) ---
    import random
    random.seed(0)
    violations = 0
    for _ in range(1000):
        f1v = random.uniform(0.01, 0.99)
        P1v = random.uniform(1, 1000)
        P2v = random.uniform(1, 1000)
        v, r = evaluate(f1v, P1v, P2v)
        if r > v + 1e-9:
            violations += 1
    print(f"\n[Reuss <= Voigt] violaciones en 1000 muestras aleatorias: {violations}")
    assert violations == 0, "Reuss no puede superar a Voigt -- error matematico"

    # --- Validacion 3: caso de referencia de libro (compuesto epoxy/fibra de vidrio) ---
    # Fibra de vidrio E=72 GPa, matriz epoxy E=3.4 GPa, f_fibra=0.5 (caso tipico Callister)
    result = compute_composite_homogenization("elastic_modulus", {"f1": 0.5, "P1": 72e9, "P2": 3.4e9})
    print(f"\n[compuesto vidrio/epoxy, f=0.5] E_voigt={result['P_voigt_value']/1e9:.2f} GPa, "
          f"E_reuss={result['P_reuss_value']/1e9:.2f} GPa")
    # Valor de referencia (Callister, Materials Science and Engineering): E_voigt ~ 37.7 GPa
    assert abs(result['P_voigt_value']/1e9 - 37.7) < 0.5

    print("\nTodas las validaciones de composite_homogenization pasaron OK.")


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

COMPOSITE_HOMOGENIZATION_TOOL_SCHEMA = {
    "name": "composite_homogenization_tool",
    "description": "Propiedades efectivas de un material compuesto de 2 fases via reglas de mezcla Voigt (cota superior) y Reuss (cota inferior), derivadas simbolicamente con sympy. mode='elastic_modulus' o 'thermal_conductivity'. params: f1 (fraccion de volumen de la fase 1), P1, P2 (propiedad de cada fase).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["elastic_modulus", "thermal_conductivity", "validate"]},
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}

register_tool("composite_homogenization_tool", COMPOSITE_HOMOGENIZATION_TOOL_SCHEMA,
              lambda args: compute_composite_homogenization(args.get("mode"), args.get("params") or {}))
