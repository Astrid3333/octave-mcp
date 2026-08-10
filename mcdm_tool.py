#!/usr/bin/env python3
"""
mcdm_tool.py
Decision multicriterio (MCDM): AHP (ponderacion via matriz de comparacion
pareada, con ratio de consistencia de Saaty), TOPSIS (ranking por cercania
al ideal positivo/negativo), y weighted_sum/weighted_product (WSM/WPM
clasicos). Escala inicial acotada del roadmap MCDM (no las "80+" tecnicas
de la vision completa) — se puede extender con VIKOR, ELECTRE, PROMETHEE,
etc. como modos nuevos despues, mismo patron que las fases anteriores.

Nota sobre validacion: a diferencia de statistics_extended_tool o glm_tool,
no hay una libreria de referencia estandar tipo scipy/sklearn para MCDM.
La validacion es contra invariantes matematicos conocidos (CR de Saaty,
propiedades de TOPSIS) y contra un caso sintetico donde el resultado
correcto es obvio por construccion.
"""
import numpy as np

# Random Index de Saaty (n: RI), para n=1..10
SAATY_RI = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24,
            7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}


def compute_ahp(pairwise_matrix, criteria_names=None):
    """
    AHP: pondera criterios a partir de una matriz de comparacion pareada
    (n x n, reciproca: A[j][i] = 1/A[i][j], diagonal = 1).

    Pesos = autovector principal normalizado (metodo del autovector, el
    estandar de Saaty). Consistencia: lambda_max via (A @ w) / w promediado,
    CI = (lambda_max - n) / (n - 1), CR = CI / RI[n]. CR < 0.10 se considera
    aceptable (regla estandar de Saaty).
    """
    A = np.array(pairwise_matrix, dtype=float)
    n = A.shape[0]
    if A.shape != (n, n):
        raise ValueError("pairwise_matrix debe ser cuadrada")
    if not np.allclose(np.diag(A), 1.0, atol=1e-6):
        raise ValueError("la diagonal de pairwise_matrix debe ser 1")
    if not np.allclose(A * A.T, 1.0, atol=1e-6):
        raise ValueError("pairwise_matrix debe ser reciproca: A[j][i] = 1/A[i][j]")

    eigvals, eigvecs = np.linalg.eig(A)
    idx = np.argmax(eigvals.real)
    lambda_max = float(eigvals[idx].real)
    w = np.abs(eigvecs[:, idx].real)
    w = w / w.sum()

    CI = (lambda_max - n) / (n - 1) if n > 1 else 0.0
    RI = SAATY_RI.get(n, 1.49)
    CR = CI / RI if RI > 0 else 0.0

    result = {
        "mode": "ahp", "n_criteria": n,
        "weights": [round(float(x), 6) for x in w],
        "lambda_max": round(lambda_max, 6),
        "consistency_index": round(float(CI), 6),
        "consistency_ratio": round(float(CR), 6),
        "consistent": bool(CR < 0.10),
    }
    if criteria_names is not None:
        result["criteria_names"] = criteria_names
        result["weights_by_criterion"] = {criteria_names[i]: round(float(w[i]), 6) for i in range(n)}
    return result


def compute_topsis(decision_matrix, weights, criteria_types, alternative_names=None):
    """
    TOPSIS: decision_matrix es m alternativas x n criterios. weights suma 1
    (si no, se normaliza). criteria_types: lista de 'benefit' o 'cost' por
    columna. Devuelve distancias al ideal positivo/negativo, coeficiente de
    cercania (closeness) y ranking (1 = mejor).
    """
    X = np.array(decision_matrix, dtype=float)
    m, n = X.shape
    w = np.array(weights, dtype=float)
    w = w / w.sum()
    if len(criteria_types) != n:
        raise ValueError("criteria_types debe tener un elemento por columna de decision_matrix")

    # normalizacion vectorial
    norms = np.sqrt((X ** 2).sum(axis=0))
    R = X / norms
    V = R * w  # matriz ponderada

    ideal_best = np.zeros(n)
    ideal_worst = np.zeros(n)
    for j in range(n):
        if criteria_types[j] == "benefit":
            ideal_best[j] = V[:, j].max()
            ideal_worst[j] = V[:, j].min()
        elif criteria_types[j] == "cost":
            ideal_best[j] = V[:, j].min()
            ideal_worst[j] = V[:, j].max()
        else:
            raise ValueError(f"criteria_types[{j}] debe ser 'benefit' o 'cost'")

    dist_best = np.sqrt(((V - ideal_best) ** 2).sum(axis=1))
    dist_worst = np.sqrt(((V - ideal_worst) ** 2).sum(axis=1))
    closeness = dist_worst / (dist_best + dist_worst)

    order = np.argsort(-closeness)  # descendente: mejor primero
    ranking = np.empty(m, dtype=int)
    ranking[order] = np.arange(1, m + 1)

    result = {
        "mode": "topsis", "n_alternatives": m, "n_criteria": n,
        "weights_normalized": [round(float(x), 6) for x in w],
        "closeness_coefficient": [round(float(x), 6) for x in closeness],
        "distance_to_ideal_best": [round(float(x), 6) for x in dist_best],
        "distance_to_ideal_worst": [round(float(x), 6) for x in dist_worst],
        "ranking": [int(r) for r in ranking],
    }
    if alternative_names is not None:
        result["alternative_names"] = alternative_names
        result["ranked_alternatives"] = [alternative_names[i] for i in order]
    return result


def compute_weighted_sum(decision_matrix, weights, criteria_types, method="sum", alternative_names=None):
    """
    WSM (method='sum') o WPM (method='product'). Normaliza min-max por
    criterio (benefit: (x-min)/(max-min); cost: (max-x)/(max-min)) y agrega
    con la ponderacion dada, por suma o por producto de potencias.
    """
    X = np.array(decision_matrix, dtype=float)
    m, n = X.shape
    w = np.array(weights, dtype=float)
    w = w / w.sum()
    if len(criteria_types) != n:
        raise ValueError("criteria_types debe tener un elemento por columna de decision_matrix")

    R = np.zeros_like(X)
    for j in range(n):
        col = X[:, j]
        rng = col.max() - col.min()
        if rng == 0:
            R[:, j] = 1.0
            continue
        if criteria_types[j] == "benefit":
            R[:, j] = (col - col.min()) / rng
        elif criteria_types[j] == "cost":
            R[:, j] = (col.max() - col) / rng
        else:
            raise ValueError(f"criteria_types[{j}] debe ser 'benefit' o 'cost'")

    # evitar log(0)/potencia de 0 en WPM
    R_safe = np.clip(R, 1e-9, None)

    if method == "sum":
        scores = (R * w).sum(axis=1)
    elif method == "product":
        scores = np.prod(R_safe ** w, axis=1)
    else:
        raise ValueError("method debe ser 'sum' o 'product'")

    order = np.argsort(-scores)
    ranking = np.empty(m, dtype=int)
    ranking[order] = np.arange(1, m + 1)

    result = {
        "mode": "weighted_sum", "method": method, "n_alternatives": m, "n_criteria": n,
        "scores": [round(float(x), 6) for x in scores],
        "ranking": [int(r) for r in ranking],
    }
    if alternative_names is not None:
        result["alternative_names"] = alternative_names
        result["ranked_alternatives"] = [alternative_names[i] for i in order]
    return result


def compute_mcdm(mode, **kwargs):
    """Dispatcher unico para el tool MCP mcdm, segun 'mode'."""
    fns = {
        "ahp": compute_ahp,
        "topsis": compute_topsis,
        "weighted_sum": compute_weighted_sum,
    }
    if mode not in fns:
        raise ValueError(f"mode desconocido: {mode}")
    return fns[mode](**kwargs)


MCDM_TOOL_SCHEMA = {
    "name": "mcdm",
    "description": "Decision multicriterio: AHP (ponderacion de criterios via matriz de comparacion pareada + ratio de consistencia de Saaty), TOPSIS (ranking por cercania a los ideales positivo/negativo), y weighted_sum/weighted_product (WSM/WPM clasicos con normalizacion min-max).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["ahp", "topsis", "weighted_sum"]},
            "pairwise_matrix": {"type": "array"}, "criteria_names": {"type": "array"},
            "decision_matrix": {"type": "array"}, "weights": {"type": "array"},
            "criteria_types": {"type": "array"}, "alternative_names": {"type": "array"},
            "method": {"type": "string", "enum": ["sum", "product"]},
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    # --- AHP: ejemplo clasico de Saaty (compra de auto: precio, confort, seguridad) ---
    # matriz reciproca conocida, CR esperado < 0.10 (consistente)
    pairwise = [
        [1.0, 3.0, 5.0],
        [1/3, 1.0, 2.0],
        [1/5, 1/2, 1.0],
    ]
    r_ahp = compute_ahp(pairwise, criteria_names=["precio", "confort", "seguridad"])
    print("AHP:", r_ahp)
    assert abs(sum(r_ahp["weights"]) - 1.0) < 1e-6, "los pesos de AHP deben sumar 1"
    assert r_ahp["consistent"], f"CR esperado < 0.10, dio {r_ahp['consistency_ratio']}"
    # precio deberia pesar mas que confort, y confort mas que seguridad (por construccion de la matriz)
    assert r_ahp["weights"][0] > r_ahp["weights"][1] > r_ahp["weights"][2], "orden de pesos inesperado"

    # --- TOPSIS: caso sintetico donde una alternativa domina en todo ---
    # alt A domina en todos los criterios benefit y tiene el menor costo -> deberia ganar claramente
    decision = [
        [9, 9, 1],   # A: domina (alto en benefit, bajo en costo)
        [5, 5, 5],   # B: intermedio
        [1, 1, 9],   # C: dominado (bajo en benefit, alto en costo)
    ]
    r_topsis = compute_topsis(decision, weights=[0.4, 0.4, 0.2],
                               criteria_types=["benefit", "benefit", "cost"],
                               alternative_names=["A", "B", "C"])
    print("TOPSIS:", r_topsis)
    assert r_topsis["ranked_alternatives"][0] == "A", "A deberia ganar por dominancia"
    assert r_topsis["ranked_alternatives"][-1] == "C", "C deberia quedar ultimo por dominancia"
    assert r_topsis["closeness_coefficient"][0] > 0.9, "closeness de A deberia ser cercano a 1 (domina en todo)"
    assert r_topsis["closeness_coefficient"][2] < 0.1, "closeness de C deberia ser cercano a 0 (dominado en todo)"

    # --- weighted_sum (WSM) y weighted_product (WPM): mismo caso sintetico ---
    r_wsm = compute_weighted_sum(decision, weights=[0.4, 0.4, 0.2],
                                  criteria_types=["benefit", "benefit", "cost"],
                                  method="sum", alternative_names=["A", "B", "C"])
    print("WSM:", r_wsm)
    assert r_wsm["ranked_alternatives"][0] == "A"
    assert r_wsm["ranked_alternatives"][-1] == "C"

    r_wpm = compute_weighted_sum(decision, weights=[0.4, 0.4, 0.2],
                                  criteria_types=["benefit", "benefit", "cost"],
                                  method="product", alternative_names=["A", "B", "C"])
    print("WPM:", r_wpm)
    assert r_wpm["ranked_alternatives"][0] == "A"
    assert r_wpm["ranked_alternatives"][-1] == "C"

    print("\nTodas las validaciones (AHP consistente, TOPSIS/WSM/WPM con dominancia correcta) corrieron sin excepciones.")
