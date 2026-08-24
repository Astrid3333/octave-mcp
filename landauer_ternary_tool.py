"""
landauer_ternary_tool.py

Limite de Landauer generalizado para logica de N valores (particularmente
ternaria/trit), y la eficiencia de codificacion por simbolo ln(B)/B que
explica por que la base 3 es casi optima frente a la base 2.

Referencia de anclaje (misma logica que ternary_combinatorics_tool: ejemplo
autoconsistente + un dato numerico verificable de la literatura, en vez de
citar una tabla que no se puede reproducir con confianza):

  - Landauer (1961): borrar un bit (N=2 estados equiprobables) disipa como
    minimo k_B*T*ln(2) de calor / incrementa la entropia en k_B*ln(2).
  - Generalizacion a N estados equiprobables (N-ario): k_B*T*ln(N) por
    simbolo borrado (Nosonovsky & Breki, Entropy 2019, 10.3390/e21121150;
    y multiples fuentes independientes que formulan el limite como
    k*ln(n) para n estados).
  - Valor numerico de referencia a T=300K: k_B*T*ln(2) ~ 2.87e-21 J
    (reportado como "~3e-21 J a temperatura ambiente" en la literatura).
  - Eficiencia de codificacion por simbolo: ln(B)/B se maximiza en B=e;
    tanto B=3 como B=2 son enteros vecinos, pero ln(3)/3 > ln(2)/2, es
    decir el trit es una codificacion mas eficiente por simbolo que el bit.

No confundir con informacion_theory (entropia de Shannon/KL/mutua/cruzada
sobre distribuciones de probabilidad, sin componente termodinamica) ni con
ternary_arithmetic_tool (aritmetica sobre trits, sin fisica estadistica).
"""

import math

K_B = 1.380649e-23  # Boltzmann constant, J/K (exact, SI 2019 definition)


def _erasure_energy(n_states, T, n_symbols=1):
    """Energia minima (J) para borrar n_symbols simbolos, cada uno con
    n_states estados equiprobables, a temperatura T (Kelvin)."""
    if n_states < 2:
        raise ValueError("n_states debe ser >= 2 (un solo estado no porta informacion)")
    if T <= 0:
        raise ValueError("T debe ser > 0 Kelvin")
    if n_symbols < 1:
        raise ValueError("n_symbols debe ser >= 1")
    energia_por_simbolo = K_B * T * math.log(n_states)
    entropia_por_simbolo = K_B * math.log(n_states)
    return {
        "n_states": n_states,
        "T_kelvin": T,
        "n_symbols": n_symbols,
        "energia_minima_joules": energia_por_simbolo * n_symbols,
        "entropia_minima_joules_por_kelvin": entropia_por_simbolo * n_symbols,
        "energia_por_simbolo_joules": energia_por_simbolo,
        "formula": "E_min = n_symbols * k_B * T * ln(n_states)",
    }


def _coding_efficiency(base):
    """ln(B)/B: informacion promedio por digito para un sistema de base B.
    Maximo en B=e (~2.71828); util para comparar bases enteras."""
    if base < 2:
        raise ValueError("base debe ser >= 2")
    return {
        "base": base,
        "ln_b_over_b": math.log(base) / base,
        "distancia_a_e": abs(base - math.e),
    }


def _compare_bases(bases):
    resultados = [_coding_efficiency(b) for b in bases]
    mejor = max(resultados, key=lambda r: r["ln_b_over_b"])
    return {
        "resultados": resultados,
        "base_mas_eficiente_del_conjunto": mejor["base"],
        "optimo_teorico": "B = e (~2.71828), maximiza ln(B)/B",
    }


def _validate_landauer_ternary():
    checks = []

    # 1. Valor numerico de referencia: k_B*T*ln(2) a 300K ~ 2.87e-21 J
    bit_300k = _erasure_energy(2, 300.0)
    esperado = 2.87e-21
    ok1 = abs(bit_300k["energia_minima_joules"] - esperado) / esperado < 0.01
    checks.append({
        "name": "bit_a_300K_coincide_con_referencia_literatura_2.87e-21J",
        "passed": bool(ok1),
        "detail": f"calculado={bit_300k['energia_minima_joules']:.4e} J, referencia~{esperado:.2e} J",
    })

    # 2. El trit cuesta mas energia bruta por simbolo que el bit (ln3 > ln2)
    trit_300k = _erasure_energy(3, 300.0)
    ok2 = trit_300k["energia_minima_joules"] > bit_300k["energia_minima_joules"]
    checks.append({
        "name": "trit_disipa_mas_energia_bruta_por_simbolo_que_bit_ln3_mayor_ln2",
        "passed": bool(ok2),
        "detail": f"bit={bit_300k['energia_minima_joules']:.4e} J, trit={trit_300k['energia_minima_joules']:.4e} J",
    })

    # 3. Escalado lineal: borrar n simbolos cuesta n veces el costo de 1 simbolo
    uno = _erasure_energy(3, 300.0, n_symbols=1)
    cinco = _erasure_energy(3, 300.0, n_symbols=5)
    ok3 = abs(cinco["energia_minima_joules"] - 5 * uno["energia_minima_joules"]) < 1e-30
    checks.append({
        "name": "escalado_lineal_en_n_symbols",
        "passed": bool(ok3),
    })

    # 4. Eficiencia por simbolo: ln(3)/3 > ln(2)/2 (el trit es una
    #    codificacion mas cercana al optimo B=e que el bit)
    eff = _compare_bases([2, 3, 4, 10])
    ln3_3 = eff["resultados"][1]["ln_b_over_b"]
    ln2_2 = eff["resultados"][0]["ln_b_over_b"]
    ok4 = ln3_3 > ln2_2 and eff["base_mas_eficiente_del_conjunto"] == 3
    checks.append({
        "name": "base_3_mas_eficiente_por_simbolo_que_base_2_y_optima_del_conjunto_2_3_4_10",
        "passed": bool(ok4),
        "detail": f"ln(2)/2={ln2_2:.5f}, ln(3)/3={ln3_3:.5f}",
    })

    # 5. Distancia a e: base 3 debe estar mas cerca de e que base 2 o base 4
    d2 = _coding_efficiency(2)["distancia_a_e"]
    d3 = _coding_efficiency(3)["distancia_a_e"]
    d4 = _coding_efficiency(4)["distancia_a_e"]
    ok5 = d3 < d2 and d3 < d4
    checks.append({
        "name": "base_3_es_el_entero_mas_cercano_a_e",
        "passed": bool(ok5),
        "detail": f"|2-e|={d2:.5f}, |3-e|={d3:.5f}, |4-e|={d4:.5f}",
    })

    # 6. Validacion de errores: parametros invalidos no crashean, dan error
    try:
        _erasure_energy(1, 300.0)
        ok6 = False
    except ValueError:
        ok6 = True
    checks.append({
        "name": "n_states_menor_a_2_da_error_no_crash",
        "passed": bool(ok6),
    })

    return {
        "validation_passed": all(c["passed"] for c in checks),
        "n_checks": len(checks),
        "checks": checks,
    }


def compute_landauer_ternary(mode, **kwargs):
    if mode == "validate":
        return _validate_landauer_ternary()

    if mode == "erasure_energy":
        n_states = kwargs.get("n_states", 3)
        T = kwargs.get("T_kelvin", 300.0)
        n_symbols = kwargs.get("n_symbols", 1)
        return _erasure_energy(n_states, T, n_symbols)

    if mode == "coding_efficiency":
        base = kwargs.get("base")
        if base is None:
            return {"error": "mode='coding_efficiency' requiere 'base' (entero >= 2)"}
        return _coding_efficiency(base)

    if mode == "compare_bases":
        bases = kwargs.get("bases", [2, 3, 4, 8, 10, 16])
        return _compare_bases(bases)

    return {"error": f"modo desconocido: {mode!r} (validos: erasure_energy, coding_efficiency, compare_bases, validate)"}


LANDAUER_TERNARY_TOOL_SCHEMA = {
    "name": "landauer_ternary_tool",
    "description": (
        "Limite de Landauer generalizado a logica de N valores (bit, trit, "
        "o base arbitraria): energia/entropia minima para borrar simbolos "
        "con N estados equiprobables (E_min = k_B*T*ln(N)), y eficiencia de "
        "codificacion por simbolo ln(B)/B (optima en B=e, por lo que el "
        "trit es mas eficiente por digito que el bit). Distinto de "
        "information_theory (Shannon/KL/mutua, sin componente termodinamica) "
        "y de ternary_arithmetic_tool (aritmetica de trits, sin fisica)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["erasure_energy", "coding_efficiency", "compare_bases", "validate"],
                "default": "validate",
            },
            "n_states": {"type": "integer", "description": "Numero de estados equiprobables del simbolo (2=bit, 3=trit, etc.)"},
            "T_kelvin": {"type": "number", "description": "Temperatura en Kelvin (default 300)"},
            "n_symbols": {"type": "integer", "description": "Cantidad de simbolos a borrar (default 1)"},
            "base": {"type": "integer", "description": "Base numerica para coding_efficiency"},
            "bases": {"type": "array", "description": "Lista de bases enteras para compare_bases"},
        },
        "required": ["mode"],
    },
}

try:
    from tool_registry import register_tool
    register_tool(
        name="landauer_ternary_tool",
        schema=LANDAUER_TERNARY_TOOL_SCHEMA,
        handler=lambda args: compute_landauer_ternary(**args),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    print(json.dumps(compute_landauer_ternary(mode="validate"), indent=2, ensure_ascii=False))
