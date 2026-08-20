"""
decision_support_tool.py

Sistemas de apoyo a decisiones multicriterio para priorizacion de inversiones
publicas (mitigacion de riesgo, infraestructura, etc.)

Modos:
  - ahp: Proceso Analitico Jerarquico (Saaty). Toma una matriz de comparacion
         pareada de criterios, calcula pesos via el metodo del autovector
         principal, y el ratio de consistencia (CR) contra el indice
         aleatorio (RI) de Saaty.
  - topsis: Tecnica de ordenamiento de preferencia por similitud a la solucion
         ideal. Toma una matriz de decision (alternativas x criterios), pesos
         y sentido de cada criterio (beneficio/costo), y devuelve el ranking
         por coeficiente de cercania a la solucion ideal.
"""

import numpy as np

# Indice aleatorio (RI) de Saaty para matrices de orden n=1..10
_SAATY_RI = {
    1: 0.00, 2: 0.00, 3: 0.58, 4: 0.90, 5: 1.12,
    6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49,
}


def _mode_ahp(p):
    M = np.asarray(p["comparison_matrix"], dtype=float)
    n = M.shape[0]
    if M.shape[0] != M.shape[1]:
        raise ValueError("comparison_matrix debe ser cuadrada")

    labels = p.get("labels", [f"criterio_{i+1}" for i in range(n)])

    # Metodo del autovector principal: autovector de autovalor maximo de M
    eigvals, eigvecs = np.linalg.eig(M)
    idx_max = int(np.argmax(eigvals.real))
    lambda_max = float(eigvals[idx_max].real)
    w = eigvecs[:, idx_max].real
    w = np.abs(w)
    w = w / np.sum(w)

    # Indice de consistencia y ratio de consistencia
    CI = (lambda_max - n) / (n - 1) if n > 1 else 0.0
    RI = _SAATY_RI.get(n, 1.49)  # para n>10 se usa el ultimo valor tabulado
    CR = CI / RI if RI > 0 else 0.0

    weights = {labels[i]: round(float(w[i]), 6) for i in range(n)}

    return {
        "labels": labels,
        "weights": weights,
        "lambda_max": round(lambda_max, 6),
        "consistency_index_CI": round(float(CI), 6),
        "random_index_RI": RI,
        "consistency_ratio_CR": round(float(CR), 6),
        "consistent": bool(CR < 0.10),  # umbral estandar de Saaty
        "ranking": [labels[i] for i in np.argsort(-w)],
    }


def _mode_topsis(p):
    X = np.asarray(p["decision_matrix"], dtype=float)  # alternativas x criterios
    n_alt, n_crit = X.shape

    alt_labels = p.get("alternative_labels", [f"alt_{i+1}" for i in range(n_alt)])
    crit_labels = p.get("criteria_labels", [f"crit_{j+1}" for j in range(n_crit)])

    weights = p.get("weights")
    if weights is None:
        weights = [1.0 / n_crit] * n_crit
    weights = np.asarray(weights, dtype=float)
    weights = weights / np.sum(weights)

    # sentido: "benefit" (mayor es mejor) o "cost" (menor es mejor), por criterio
    senses = p.get("criteria_sense", ["benefit"] * n_crit)

    # 1) normalizacion vectorial
    norm = np.sqrt(np.sum(X ** 2, axis=0))
    norm[norm == 0] = 1e-12
    R = X / norm

    # 2) matriz ponderada
    V = R * weights

    # 3) solucion ideal positiva (A+) y negativa (A-)
    A_plus = np.zeros(n_crit)
    A_minus = np.zeros(n_crit)
    for j in range(n_crit):
        if senses[j] == "benefit":
            A_plus[j] = np.max(V[:, j])
            A_minus[j] = np.min(V[:, j])
        elif senses[j] == "cost":
            A_plus[j] = np.min(V[:, j])
            A_minus[j] = np.max(V[:, j])
        else:
            raise ValueError(f"criteria_sense invalido: {senses[j]} (usar 'benefit' o 'cost')")

    # 4) distancias euclidianas a A+ y A-
    D_plus = np.sqrt(np.sum((V - A_plus) ** 2, axis=1))
    D_minus = np.sqrt(np.sum((V - A_minus) ** 2, axis=1))

    # 5) coeficiente de cercania relativa
    denom = D_plus + D_minus
    denom[denom == 0] = 1e-12
    C = D_minus / denom

    order = np.argsort(-C)
    ranking = [alt_labels[i] for i in order]

    alternatives = []
    for i in range(n_alt):
        alternatives.append({
            "label": alt_labels[i],
            "closeness_coefficient": round(float(C[i]), 6),
            "distance_to_ideal_best": round(float(D_plus[i]), 6),
            "distance_to_ideal_worst": round(float(D_minus[i]), 6),
        })

    return {
        "criteria_labels": crit_labels,
        "weights_normalized": np.round(weights, 6).tolist(),
        "criteria_sense": senses,
        "alternatives": alternatives,
        "ranking": ranking,
        "best_alternative": ranking[0],
    }


def _validate():
    checks = []

    # --- Check 1: AHP con matriz perfectamente consistente construida a partir
    # de pesos verdaderos conocidos (w_true). Una matriz M_ij = w_i/w_j es
    # exactamente consistente (lambda_max = n, CR = 0), y el autovector
    # principal debe recuperar w_true exactamente.
    w_true = np.array([0.6, 0.3, 0.1])
    n = len(w_true)
    M_consistent = np.array([[w_true[i] / w_true[j] for j in range(n)] for i in range(n)])
    ahp1 = _mode_ahp({"comparison_matrix": M_consistent.tolist(),
                       "labels": ["A", "B", "C"]})
    w_recovered = np.array([ahp1["weights"][k] for k in ["A", "B", "C"]])
    max_err_w = float(np.max(np.abs(w_recovered - w_true))) / np.max(w_true) * 100
    checks.append({
        "name": "ahp_perfectly_consistent_matrix",
        "lambda_max": ahp1["lambda_max"], "expected_lambda_max": float(n),
        "CR": ahp1["consistency_ratio_CR"],
        "max_weight_error_pct": round(max_err_w, 6),
        "passed": bool(abs(ahp1["lambda_max"] - n) < 1e-6 and ahp1["consistency_ratio_CR"] < 1e-6
                  and max_err_w < 1e-4),
    })

    # --- Check 2: AHP con matriz inconsistente conocida (ejemplo clasico de
    # comparacion de 3 criterios con juicios no perfectamente transitivos).
    # No comparamos contra un numero de libro (evitamos citar), sino que
    # verificamos las propiedades matematicas que CR *debe* cumplir:
    # CR > 0 (porque la matriz no es consistente) y lambda_max >= n (cota
    # teorica de Saaty para matrices reciprocas positivas).
    M_inconsistent = [[1, 3, 5], [1/3, 1, 2], [1/5, 1/2, 1]]
    # Rompemos la transitividad a mano para asegurar inconsistencia real:
    M_inconsistent[0][2] = 9  # en vez del 5 "transitivo" (3*2=6, no 9)
    M_inconsistent[2][0] = 1/9
    ahp2 = _mode_ahp({"comparison_matrix": M_inconsistent})
    checks.append({
        "name": "ahp_inconsistent_matrix_properties",
        "lambda_max": ahp2["lambda_max"],
        "CR": ahp2["consistency_ratio_CR"],
        "passed": bool(ahp2["lambda_max"] >= n - 1e-9 and ahp2["consistency_ratio_CR"] > 0),
    })

    # --- Check 3: AHP -- suma de pesos siempre debe dar 1.0
    sum_w = sum(ahp2["weights"].values())
    checks.append({
        "name": "ahp_weights_sum_to_1",
        "sum_weights": round(sum_w, 9),
        "passed": abs(sum_w - 1.0) < 1e-9,
    })

    # --- Check 4: TOPSIS con caso trivial disenado para tener respuesta obvia:
    # alternativa "dominante" que es la mejor en TODOS los criterios de
    # beneficio y la mejor (menor) en el criterio de costo debe ganar con
    # closeness coefficient = 1.0 exacto (coincide con la solucion ideal),
    # y la alternativa "dominada" (peor en todo) debe dar closeness = 0.0.
    decision_matrix = [
        [9, 9, 1],   # dominante: mejor en crit1 (benefit), crit2 (benefit), crit3 (cost, menor=mejor)
        [5, 5, 5],   # intermedia
        [1, 1, 9],   # dominada
    ]
    topsis1 = _mode_topsis({
        "decision_matrix": decision_matrix,
        "criteria_sense": ["benefit", "benefit", "cost"],
        "alternative_labels": ["dominante", "intermedia", "dominada"],
    })
    C = {a["label"]: a["closeness_coefficient"] for a in topsis1["alternatives"]}
    checks.append({
        "name": "topsis_dominant_dominated_extremes",
        "closeness_dominante": C["dominante"], "closeness_dominada": C["dominada"],
        "ranking": topsis1["ranking"],
        "passed": bool(abs(C["dominante"] - 1.0) < 1e-9 and abs(C["dominada"] - 0.0) < 1e-9
                  and topsis1["ranking"][0] == "dominante"
                  and topsis1["ranking"][-1] == "dominada"),
    })

    # --- Check 5: TOPSIS invariante ante escalado de una columna (normalizacion
    # vectorial debe hacer que el ranking no cambie si multiplico una columna
    # completa por una constante positiva)
    dm2 = np.array(decision_matrix, dtype=float)
    dm2[:, 0] = dm2[:, 0] * 100.0  # escalar primer criterio por 100
    topsis2 = _mode_topsis({
        "decision_matrix": dm2.tolist(),
        "criteria_sense": ["benefit", "benefit", "cost"],
        "alternative_labels": ["dominante", "intermedia", "dominada"],
    })
    checks.append({
        "name": "topsis_scale_invariance",
        "ranking_original": topsis1["ranking"],
        "ranking_scaled": topsis2["ranking"],
        "passed": topsis1["ranking"] == topsis2["ranking"],
    })

    # --- Check 6: TOPSIS -- pesos por defecto son uniformes y suman 1
    topsis3 = _mode_topsis({"decision_matrix": decision_matrix})
    sum_w_topsis = sum(topsis3["weights_normalized"])
    checks.append({
        "name": "topsis_default_weights",
        "weights": topsis3["weights_normalized"],
        "sum_weights": round(sum_w_topsis, 9),
        "passed": bool(abs(sum_w_topsis - 1.0) < 1e-4
                  and all(abs(w - 1/3) < 1e-4 for w in topsis3["weights_normalized"])),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_decision_support(mode, params=None):
    params = params or {}

    if mode == "ahp":
        return _mode_ahp(params)
    elif mode == "topsis":
        return _mode_topsis(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"Modo desconocido: {mode}")


if __name__ == "__main__":
    import json
    print(json.dumps(compute_decision_support("validate"), indent=2, ensure_ascii=False))

DECISION_SUPPORT_TOOL_SCHEMA = {   'type': 'object',
    'properties': {'mode': {'type': 'string', 'enum': ['ahp', 'topsis', 'validate'], 'default': 'validate'}, 'params': {'type': 'object'}},
    'required': ['mode']}

try:
    from tool_registry import register_tool
    register_tool(
        name="decision_support_tool",
        schema={
        "name": "decision_support_tool",
        "description": 'Sistemas de apoyo a decisiones multicriterio para priorizacion de inversiones publicas: ahp (Proceso Analitico Jerarquico de Saaty, pesos via autovector principal y ratio de consistencia CR), topsis (ordenamiento de alternativas por cercania a la solucion ideal, con criterios de beneficio/costo y pesos configurables).',
        "inputSchema": DECISION_SUPPORT_TOOL_SCHEMA,
    },
        handler=lambda args: compute_decision_support(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass

