"""
genetic_ternary_encoder_tool.py

Codifica genotipos multi-locus (0=homocigoto sano, 1=heterocigoto portador,
2=homocigoto mutado) como numeros en base 3, calcula frecuencias esperadas
via Hardy-Weinberg a partir de una incidencia real, y marca que codigos son
"candidatos CRISPR-Cas9" (locus objetivo con al menos un alelo mutado).

Convencion de registro real del repo (confirmada por grep de tool_registry.py
y statmech_partition_tool.py): register_tool(name, schema, handler) explicito
a nivel de modulo, envuelto en try/except ImportError; handler=lambda args:
run(args.get("mode"), args).
"""

import math


# ---------------------------------------------------------------------------
# Logica de codificacion (base 3 estandar, digitos 0,1,2 -- NO balanceada)
# ---------------------------------------------------------------------------

def _encode(digits):
    """Lista de digitos (0,1,2), mas significativo primero -> entero decimal."""
    value = 0
    for d in digits:
        d = int(d)
        if d not in (0, 1, 2):
            raise ValueError(f"digito invalido: {d} (debe ser 0, 1 o 2)")
        value = value * 3 + d
    return value


def _decode(value, n_loci):
    """Entero decimal -> lista de digitos de largo n_loci, mas significativo primero."""
    value = int(value)
    if value < 0 or value >= 3 ** n_loci:
        raise ValueError(f"value {value} fuera de rango para n_loci={n_loci} (0..{3**n_loci - 1})")
    digits = []
    for k in range(n_loci - 1, -1, -1):
        digits.append((value // (3 ** k)) % 3)
    return digits


_GENOTYPE_LABEL = {0: "AA (sano)", 1: "Aa (portador)", 2: "aa (afectado)"}


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------

def mode_encode(params):
    if "digits" in params:
        raw = params["digits"]
        digits = [int(c) for c in raw] if isinstance(raw, str) else [int(x) for x in raw]
    else:
        raise ValueError("encode requiere params.digits (string '210' o lista [2,1,0])")
    value = _encode(digits)
    return {
        "digits": digits,
        "labels": [_GENOTYPE_LABEL[d] for d in digits],
        "value_decimal": value,
        "n_loci": len(digits),
    }


def mode_decode(params):
    value = int(params["value"])
    n_loci = int(params["n_loci"])
    digits = _decode(value, n_loci)
    return {
        "value_decimal": value,
        "n_loci": n_loci,
        "digits": digits,
        "labels": [_GENOTYPE_LABEL[d] for d in digits],
    }


def mode_hardy_weinberg_locus(params):
    if "incidence" in params:
        incidence = float(params["incidence"])
        q = math.sqrt(incidence)
    else:
        q = float(params["q"])
        incidence = q ** 2
    p = 1.0 - q
    freqs = {"AA": p * p, "Aa": 2 * p * q, "aa": q * q}
    return {
        "p_alelo_normal": p,
        "q_alelo_mutado": q,
        "incidencia_homocigoto_afectado": incidence,
        "frecuencias_genotipo": freqs,
        "frecuencias_por_digito": {0: freqs["AA"], 1: freqs["Aa"], 2: freqs["aa"]},
    }


def mode_crispr_targets(params):
    n_loci = int(params["n_loci"])
    # target_locus_index: 0 = mas a la izquierda (convencion: locus principal, ej. ABCA12)
    target_locus_index = int(params.get("target_locus_index", 0))
    if not (0 <= target_locus_index < n_loci):
        raise ValueError("target_locus_index fuera de rango")

    total_states = 3 ** n_loci
    candidates = []
    for value in range(total_states):
        digits = _decode(value, n_loci)
        if digits[target_locus_index] != 0:
            candidates.append(value)

    return {
        "n_loci": n_loci,
        "target_locus_index": target_locus_index,
        "total_states": total_states,
        "n_crispr_candidates": len(candidates),
        "fraction_crispr_candidates": len(candidates) / total_states,
        "crispr_candidate_values": candidates,
    }


def mode_is_crispr_candidate(params):
    """Chequeo puntual para un solo genotipo ya codificado (value + n_loci)."""
    value = int(params["value"])
    n_loci = int(params["n_loci"])
    target_locus_index = int(params.get("target_locus_index", 0))
    digits = _decode(value, n_loci)
    digit = digits[target_locus_index]
    return {
        "value_decimal": value,
        "digits": digits,
        "target_locus_index": target_locus_index,
        "target_digit": digit,
        "target_label": _GENOTYPE_LABEL[digit],
        "is_crispr_candidate": digit != 0,
        "reason": (
            "el locus objetivo tiene al menos un alelo mutado (heterocigoto u homocigoto)"
            if digit != 0
            else "el locus objetivo es homocigoto sano, no requiere edicion"
        ),
    }


def validate():
    checks = []

    # 1. roundtrip encode/decode sobre todos los codigos de 3 loci
    ok = True
    for v in range(27):
        digits = _decode(v, 3)
        if _encode(digits) != v:
            ok = False
            break
    checks.append({"name": "roundtrip_encode_decode_3loci", "passed": ok})

    # 2. ejemplo del chat: "210" -> 21
    checks.append({"name": "ejemplo_210_es_21", "passed": _encode([2, 1, 0]) == 21})

    # 3. Hardy-Weinberg contra incidencia real de ictiosis arlequin (1/300000)
    hw = mode_hardy_weinberg_locus({"incidence": 1.0 / 300000.0})
    aa = hw["frecuencias_genotipo"]["aa"]
    checks.append({
        "name": "hardy_weinberg_incidencia_ictiosis_arlequin",
        "passed": abs(aa - 1.0 / 300000.0) < 1e-9,
    })

    # 4. fraccion de candidatos CRISPR para 1 locus = 2/3 (digitos 1 y 2 de 3)
    ct1 = mode_crispr_targets({"n_loci": 1, "target_locus_index": 0})
    checks.append({
        "name": "fraccion_crispr_1_locus_es_2_tercios",
        "passed": abs(ct1["fraction_crispr_candidates"] - 2.0 / 3.0) < 1e-9,
    })

    # 5. fraccion de candidatos CRISPR es independiente de n_loci (siempre 2/3
    #    para el locus objetivo, porque los otros loci no afectan el conteo)
    ct3 = mode_crispr_targets({"n_loci": 3, "target_locus_index": 0})
    checks.append({
        "name": "fraccion_crispr_invariante_con_mas_loci",
        "passed": abs(ct3["fraction_crispr_candidates"] - 2.0 / 3.0) < 1e-9,
    })

    # 6. is_crispr_candidate puntual sobre el ejemplo del chat (210 -> value 21)
    chk = mode_is_crispr_candidate({"value": 21, "n_loci": 3, "target_locus_index": 0})
    checks.append({
        "name": "ejemplo_210_es_candidato_crispr",
        "passed": chk["is_crispr_candidate"] is True and chk["target_digit"] == 2,
    })

    total = len(checks)
    passed = sum(1 for c in checks if c["passed"])
    return {
        "checks": checks,
        "total_checks": total,
        "total_passed": passed,
        "validation_passed": passed == total,
    }


def run(mode, params=None):
    params = params or {}
    if mode == "encode":
        return mode_encode(params)
    if mode == "decode":
        return mode_decode(params)
    if mode == "hardy_weinberg_locus":
        return mode_hardy_weinberg_locus(params)
    if mode == "crispr_targets":
        return mode_crispr_targets(params)
    if mode == "is_crispr_candidate":
        return mode_is_crispr_candidate(params)
    if mode == "validate":
        return validate()
    raise ValueError(f"Modo desconocido: {mode}")


GENETIC_TERNARY_ENCODER_TOOL_SCHEMA = {
    "name": "genetic_ternary_encoder_tool",
    "description": (
        "Codifica genotipos multi-locus en base 3 (0=AA sano, 1=Aa portador, "
        "2=aa afectado), calcula frecuencias esperadas via Hardy-Weinberg a "
        "partir de una incidencia real, y marca que codigos son candidatos "
        "de edicion CRISPR-Cas9 (locus objetivo con al menos un alelo mutado)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "encode",
                    "decode",
                    "hardy_weinberg_locus",
                    "crispr_targets",
                    "is_crispr_candidate",
                    "validate",
                ],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}

try:
    from tool_registry import register_tool
    register_tool(
        "genetic_ternary_encoder_tool",
        GENETIC_TERNARY_ENCODER_TOOL_SCHEMA,
        lambda args: run(args.get("mode"), args.get("params", {})),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    print(json.dumps(validate(), indent=2, ensure_ascii=False))
