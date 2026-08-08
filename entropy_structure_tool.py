"""
entropy_structure_tool.py

Analisis de entropia condicional sobre secuencias de simbolos, para evaluar
si una secuencia (khipu, yupana, corpus filisteo/cypro-minoico, cualquier
sistema de signos sin descifrar) tiene estructura combinatoria compatible
con codificacion tipo-lenguaje, o es estadisticamente indistinguible de
ruido/conteo simple.

Mismo espiritu metodologico que cross_validation_tool: no "descifra" nada
por si solo -- da evidencia estadistica indirecta que hay que triangular
con evidencia arqueologica/textual independiente. Replica la logica de
Rao et al. 2009 (Science) sobre la escritura del valle del Indo, que
comparo entropia condicional de secuencias de signos contra baselines de
lenguaje real vs. sistemas no-linguisticos (ADN, tally marks) -- y que
Sproat 2010 cuestiono por la eleccion de baselines, dejando el caso
todavia disputado. Ese desacuerdo metodologico es la razon por la que este
modulo expone los baselines de forma explicita en vez de dar un veredicto.

Metricas:
- H0: entropia de orden 0 (distribucion de frecuencia de simbolos sola)
- H1: entropia condicional de orden 1, H(X_n | X_{n-1})
- redundancia: 1 - H1/H0 -- fraccion de la entropia "explicada" por el
  simbolo anterior. Cerca de 0 = sin estructura secuencial detectable
  (compatible con tally marks / conteo). Valores altos = estructura
  combinatoria (compatible con sintaxis, pero NO prueba semantica).
"""
import math
from collections import Counter, defaultdict

ENTROPY_STRUCTURE_SCHEMA = {
    "name": "compute_entropy_structure",
    "description": (
        "Calcula entropia de orden 0 y entropia condicional de orden 1 sobre "
        "una secuencia de simbolos, para evaluar evidencia de estructura "
        "combinatoria (compatible con codificacion tipo-lenguaje) vs. ausencia "
        "de estructura (compatible con conteo/tally marks). Presets sinteticos "
        "(random_iid, markov_structured) para validar el metodo contra casos "
        "de estructura conocida, o 'custom' via 'sequence' para datos reales."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "preset": {
                "type": "string",
                "enum": ["random_iid", "markov_structured", "custom"],
                "default": "random_iid",
            },
            "sequence": {
                "type": "array",
                "description": "Solo si preset='custom'. Lista de simbolos (strings o numeros).",
            },
            "alphabet_size": {"type": "integer", "default": 5, "description": "Para presets sinteticos"},
            "n_symbols": {"type": "integer", "default": 5000, "description": "Para presets sinteticos"},
            "seed": {"type": "integer", "default": 1},
        },
    },
}


def _order0_entropy(seq):
    n = len(seq)
    if n == 0:
        return 0.0
    counts = Counter(seq)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _order1_conditional_entropy(seq):
    pair_counts = defaultdict(Counter)
    prev_counts = Counter()
    for i in range(1, len(seq)):
        prev, cur = seq[i - 1], seq[i]
        pair_counts[prev][cur] += 1
        prev_counts[prev] += 1
    total = sum(prev_counts.values())
    if total == 0:
        return 0.0
    H = 0.0
    for prev, cur_counts in pair_counts.items():
        n_prev = prev_counts[prev]
        p_prev = n_prev / total
        H_cond_prev = -sum((c / n_prev) * math.log2(c / n_prev) for c in cur_counts.values())
        H += p_prev * H_cond_prev
    return H


def _gen_random_iid(alphabet_size, n_symbols, seed):
    import random
    rng = random.Random(seed)
    alphabet = [chr(65 + i) for i in range(alphabet_size)]
    return [rng.choice(alphabet) for _ in range(n_symbols)], alphabet


def _gen_markov_structured(alphabet_size, n_symbols, seed):
    import random
    rng = random.Random(seed)
    alphabet = [chr(65 + i) for i in range(alphabet_size)]
    # cada simbolo tiene fuerte preferencia por "el siguiente en el ciclo"
    transition = {}
    for i, sym in enumerate(alphabet):
        preferred = alphabet[(i + 1) % alphabet_size]
        others = [s for s in alphabet if s != preferred]
        # 80% al preferido, 20% repartido entre el resto
        weighted = [preferred] * 8 + others
        transition[sym] = weighted
    seq = [alphabet[0]]
    for _ in range(n_symbols - 1):
        seq.append(rng.choice(transition[seq[-1]]))
    return seq, alphabet


def compute_entropy_structure(preset="random_iid", sequence=None, alphabet_size=5,
                               n_symbols=5000, seed=1):
    known_baseline = None

    if preset == "random_iid":
        seq, alphabet = _gen_random_iid(alphabet_size, n_symbols, seed)
        known_baseline = {
            "descripcion": "i.i.d. uniforme -- sin estructura secuencial por construccion",
            "redundancia_esperada": 0.0,
        }
    elif preset == "markov_structured":
        seq, alphabet = _gen_markov_structured(alphabet_size, n_symbols, seed)
        known_baseline = {
            "descripcion": "cadena de Markov con transiciones sesgadas -- estructura secuencial fuerte por construccion",
            "redundancia_esperada": "alta (>0.4 tipicamente)",
        }
    elif preset == "custom":
        if not sequence:
            return {"error": "preset='custom' requiere 'sequence' (lista de simbolos)"}
        seq = list(sequence)
    else:
        return {"error": f"preset desconocido: {preset}"}

    if len(seq) < 10:
        return {"error": "secuencia demasiado corta para un analisis confiable (minimo ~10 simbolos, idealmente cientos)"}

    H0 = _order0_entropy(seq)
    H1 = _order1_conditional_entropy(seq)
    redundancy = 1 - (H1 / H0) if H0 > 0 else 0.0
    alphabet_used = sorted(set(seq), key=lambda x: str(x))

    result = {
        "preset": preset,
        "n_symbols_used": len(seq),
        "alphabet_size_observed": len(alphabet_used),
        "H0_orden0_bits": round(H0, 4),
        "H1_condicional_orden1_bits": round(H1, 4),
        "redundancia_secuencial": round(redundancy, 4),
        "interpretacion": (
            "redundancia cerca de 0 = sin estructura secuencial detectable, "
            "compatible con conteo/tally marks. redundancia alta = estructura "
            "combinatoria presente, compatible con (pero NO prueba de) sintaxis "
            "tipo-lenguaje. Este numero solo, sin comparar contra corpora de "
            "control real, no es evidencia fuerte -- ver nota metodologica."
        ),
        "nota_metodologica": (
            "Rao et al. 2009 uso este tipo de metrica para argumentar estructura "
            "tipo-lenguaje en la escritura del Indo; Sproat 2010 objeto la eleccion "
            "de baselines de comparacion. La leccion: nunca reportar redundancia "
            "aislada -- compararla siempre contra baselines conocidos (random_iid "
            "y markov_structured en este modulo) generados con la MISMA longitud "
            "de secuencia y tamano de alfabeto que el corpus real, no valores "
            "genericos de la literatura."
        ),
    }
    if known_baseline:
        result["baseline_sintetico"] = known_baseline
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(compute_entropy_structure("random_iid"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_entropy_structure("markov_structured"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_entropy_structure("custom", sequence=["glifo_A","glifo_B","glifo_A","glifo_C"]*3), indent=2, ensure_ascii=False))
