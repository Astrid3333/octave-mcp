"""
paleography_tool.py -- tres motores cuantitativos para paleografia/codicologia,
pensados para trabajar con corpora de manuscritos donde se midieron rasgos
(letterforms, abreviaturas, ductus) de forma numerica.

Ninguno de los tres motores "lee" imagenes ni hace OCR: todos toman matrices
o vectores de rasgos YA EXTRAIDOS (por el usuario, por otro tool, o a mano) y
hacen la parte estadistica. Filosofia identica al resto del repo: con pocos
datos, escala en vez de adivinar, y la salida da numeros/rankings -- NUNCA
una fecha o atribucion "definitiva", eso queda para quien interpreta.

Modes:

1. seriation -- seriacion por correspondencia (Kendall 1971 / analisis de
   correspondencias clasico via SVD de una tabla de contingencia
   documentos x rasgos). Ordena los documentos a lo largo del primer eje de
   correspondencia; asume "efecto herradura" (horseshoe effect): si el
   corpus tiene una unica tendencia temporal dominante, el primer eje
   deberia correlacionar con el orden cronologico real. No lo garantiza --
   por eso, si hay anios_conocidos para al menos algunos documentos, el
   modo devuelve ademas la correlacion de Spearman entre el eje 1 y esos
   anios, como chequeo de si el eje realmente capturo tiempo y no otra
   fuente de variacion (region, escriba, soporte).

2. feature_dating_regression -- regresion lineal (o polinomica de grado
   bajo) anio ~ rasgo(s), ajustada sobre documentos de fecha conocida
   (ancla), y usada para estimar la fecha de documentos sin fecha. Reporta
   R2 y, cuando es posible, el intervalo de confianza aproximado de la
   prediccion via el error estandar residual -- NO un rango "garantizado".

3. letterform_classification -- clasificador de vecino-mas-cercano-a-
   centroide (nearest centroid) sobre vectores de rasgos de letterforms
   (ej: proporcion astil/cuerpo, angulo de trazo, curvatura). Entrena
   centroides por clase conocida (ej: gotica textura, humanistica,
   cursiva) y clasifica muestras nuevas por distancia euclidea normalizada
   (z-score por rasgo) al centroide mas cercano. Reporta tambien la
   distancia al segundo centroide mas cercano (margen) para senalar casos
   ambiguos en vez de forzar una clase.
"""
import numpy as np


MIN_DOCS_SERIATION = 4
MIN_ANCLA_REGRESION = 3
MIN_MUESTRAS_POR_CLASE = 2


# ---------------------------------------------------------------------------
# 1. seriacion por correspondencia
# ---------------------------------------------------------------------------

def _correspondence_analysis(matriz):
    """matriz: (n_docs, n_rasgos) de frecuencias/conteos no negativos.
    Devuelve scores del eje 1 para filas (docs) y columnas (rasgos), via
    SVD de la matriz de residuos estandarizados (chi-cuadrado)."""
    matriz = np.asarray(matriz, dtype=float)
    total = matriz.sum()
    if total <= 0:
        return None
    P = matriz / total
    fila_masas = P.sum(axis=1)
    col_masas = P.sum(axis=0)
    esperado = np.outer(fila_masas, col_masas)
    fila_masas_safe = np.where(fila_masas > 0, fila_masas, 1.0)
    col_masas_safe = np.where(col_masas > 0, col_masas, 1.0)
    residuos_estandarizados = (P - esperado) / np.sqrt(np.outer(fila_masas_safe, col_masas_safe))

    U, S, Vt = np.linalg.svd(residuos_estandarizados, full_matrices=False)
    if len(S) == 0:
        return None

    fila_scores = U[:, 0] * S[0] / np.sqrt(fila_masas_safe)
    col_scores = Vt[0, :] * S[0] / np.sqrt(col_masas_safe)
    inercia_total = float(np.sum(S ** 2))
    inercia_eje1_pct = float(S[0] ** 2 / inercia_total * 100) if inercia_total > 0 else 0.0

    return {
        "fila_scores": fila_scores,
        "col_scores": col_scores,
        "inercia_eje1_pct": inercia_eje1_pct,
        "n_ejes": len(S),
    }


def _spearman(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    if np.std(ra) == 0 or np.std(rb) == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def _seriation(matriz, doc_ids=None, anios_conocidos=None):
    matriz = np.asarray(matriz, dtype=float)
    n_docs = matriz.shape[0]
    if n_docs < MIN_DOCS_SERIATION:
        return {"escalado": True, "razon": f"solo {n_docs} documentos, minimo {MIN_DOCS_SERIATION} para que la seriacion tenga sentido"}
    if doc_ids is None:
        doc_ids = [f"doc_{i}" for i in range(n_docs)]

    ca = _correspondence_analysis(matriz)
    if ca is None:
        return {"error": "la matriz esta vacia o degenerada (suma total 0)"}

    orden_idx = np.argsort(ca["fila_scores"])
    orden = [doc_ids[i] for i in orden_idx]

    resultado = {
        "escalado": False,
        "orden_seriado": orden,
        "eje1_scores": {doc_ids[i]: round(float(ca["fila_scores"][i]), 4) for i in range(n_docs)},
        "inercia_eje1_pct": round(ca["inercia_eje1_pct"], 2),
        "nota": ("el orden asume 'efecto herradura' (una unica tendencia dominante en el corpus). "
                 "Si inercia_eje1_pct es bajo, el eje 1 probablemente no captura una sola tendencia limpia -- "
                 "revisar con mas rasgos o separar el corpus."),
    }

    if anios_conocidos:
        anios_idx = [i for i in range(n_docs) if doc_ids[i] in anios_conocidos]
        if len(anios_idx) >= 3:
            scores_con_anio = [ca["fila_scores"][i] for i in anios_idx]
            anios_valores = [anios_conocidos[doc_ids[i]] for i in anios_idx]
            rho = _spearman(scores_con_anio, anios_valores)
            resultado["chequeo_cronologico"] = {
                "n_documentos_con_anio_conocido": len(anios_idx),
                "spearman_eje1_vs_anio": round(rho, 4) if rho is not None else None,
                "interpretacion": ("correlacion fuerte (|rho|>0.7) sugiere que el eje 1 SI captura tiempo -- "
                                    "correlacion debil sugiere que captura otra fuente de variacion (region, "
                                    "escriba, soporte) y el orden seriado no deberia leerse como cronologico"),
            }
        else:
            resultado["chequeo_cronologico"] = {"escalado": True, "razon": "menos de 3 documentos con anio conocido para validar el eje"}

    return resultado


def _preset_seriation_demo():
    rng = np.random.RandomState(7)
    n_docs = 8
    n_rasgos = 5
    matriz = np.zeros((n_docs, n_rasgos))
    for i in range(n_docs):
        frac = i / (n_docs - 1)
        pesos = np.array([1 - frac, 0.5, frac * 0.3, frac, 0.2 + 0.1 * np.sin(frac * np.pi)])
        pesos = np.clip(pesos, 0.01, None)
        conteos = rng.multinomial(40, pesos / pesos.sum())
        matriz[i] = conteos
    doc_ids = [f"ms_{i}" for i in range(n_docs)]
    anios_reales = {doc_ids[i]: 1200 + i * 15 for i in range(n_docs)}
    anios_conocidos = {doc_ids[i]: anios_reales[doc_ids[i]] for i in [0, 2, 5, 7]}
    return matriz.tolist(), doc_ids, anios_conocidos, anios_reales


# ---------------------------------------------------------------------------
# 2. regresion de datacion estilistica
# ---------------------------------------------------------------------------

def _fit_dating_regression(anios, rasgos, grado=1):
    anios = np.asarray(anios, dtype=float)
    rasgos = np.asarray(rasgos, dtype=float)
    if len(anios) < MIN_ANCLA_REGRESION:
        return None
    coef = np.polyfit(rasgos, anios, deg=grado)
    pred_ancla = np.polyval(coef, rasgos)
    ss_res = float(np.sum((anios - pred_ancla) ** 2))
    ss_tot = float(np.sum((anios - anios.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
    n = len(anios)
    dof = max(n - (grado + 1), 1)
    error_estandar_residual = float(np.sqrt(ss_res / dof))
    return {"coef": coef, "r2": r2, "error_estandar_residual": error_estandar_residual, "n_ancla": n}


def _feature_dating_regression(anios_ancla, rasgo_ancla, rasgo_predecir, ids_predecir=None, grado=1):
    if len(anios_ancla) != len(rasgo_ancla):
        return {"error": "anios_ancla y rasgo_ancla deben tener la misma longitud"}
    if len(anios_ancla) < MIN_ANCLA_REGRESION:
        return {"escalado": True, "razon": f"solo {len(anios_ancla)} documentos ancla con fecha conocida, minimo {MIN_ANCLA_REGRESION}"}
    if grado >= len(anios_ancla) - 1:
        grado = max(1, len(anios_ancla) - 2)

    modelo = _fit_dating_regression(anios_ancla, rasgo_ancla, grado=grado)
    if modelo is None:
        return {"error": "no se pudo ajustar el modelo"}

    if ids_predecir is None:
        ids_predecir = [f"undated_{i}" for i in range(len(rasgo_predecir))]

    predicciones = {}
    for doc_id, rasgo in zip(ids_predecir, rasgo_predecir):
        anio_estimado = float(np.polyval(modelo["coef"], rasgo))
        predicciones[doc_id] = {
            "anio_estimado": round(anio_estimado, 1),
            "intervalo_aprox_1sigma": [round(anio_estimado - modelo["error_estandar_residual"], 1),
                                        round(anio_estimado + modelo["error_estandar_residual"], 1)],
        }

    return {
        "escalado": False,
        "r2_ajuste_ancla": round(modelo["r2"], 4) if modelo["r2"] is not None else None,
        "error_estandar_residual_anios": round(modelo["error_estandar_residual"], 2),
        "n_documentos_ancla": modelo["n_ancla"],
        "grado_polinomio": grado,
        "predicciones": predicciones,
        "nota": ("el intervalo 1-sigma es aproximado (residuo del ajuste sobre el propio corpus ancla, no "
                 "un intervalo de prediccion formal) -- util para ordenar confianza relativa entre "
                 "documentos, no como cota estadistica rigurosa. Con pocos documentos ancla o R2 bajo, "
                 "tratar las fechas estimadas como orientativas."),
    }


def _preset_dating_demo():
    rng = np.random.RandomState(3)
    rasgo_ancla = np.linspace(0.1, 0.9, 6)
    anios_ancla = 1100 + 200 * rasgo_ancla + rng.normal(0, 3, size=6)
    rasgo_predecir = [0.35, 0.72]
    anio_esperado = [1100 + 200 * r for r in rasgo_predecir]
    return anios_ancla.tolist(), rasgo_ancla.tolist(), rasgo_predecir, anio_esperado


# ---------------------------------------------------------------------------
# 3. clasificacion de forma de letra (nearest centroid)
# ---------------------------------------------------------------------------

def _entrenar_centroides(rasgos_entrenamiento, clases_entrenamiento):
    rasgos = np.asarray(rasgos_entrenamiento, dtype=float)
    clases = np.asarray(clases_entrenamiento)
    medias = rasgos.mean(axis=0)
    stds = rasgos.std(axis=0)
    stds_safe = np.where(stds > 0, stds, 1.0)
    z = (rasgos - medias) / stds_safe

    centroides = {}
    conteos = {}
    for clase in np.unique(clases):
        mask = clases == clase
        conteos[str(clase)] = int(mask.sum())
        centroides[str(clase)] = z[mask].mean(axis=0)
    return centroides, conteos, medias, stds_safe


def _clasificar_letterforms(rasgos_entrenamiento, clases_entrenamiento, rasgos_nuevos, ids_nuevos=None):
    rasgos_entrenamiento = np.asarray(rasgos_entrenamiento, dtype=float)
    clases_entrenamiento = np.asarray(clases_entrenamiento)
    n_por_clase = {str(c): int((clases_entrenamiento == c).sum()) for c in np.unique(clases_entrenamiento)}
    clases_insuficientes = [c for c, n in n_por_clase.items() if n < MIN_MUESTRAS_POR_CLASE]
    if clases_insuficientes:
        return {"escalado": True, "razon": f"clase(s) {clases_insuficientes} con menos de {MIN_MUESTRAS_POR_CLASE} muestras de entrenamiento"}

    centroides, conteos, medias, stds_safe = _entrenar_centroides(rasgos_entrenamiento, clases_entrenamiento)
    nombres_clases = list(centroides.keys())

    rasgos_nuevos = np.asarray(rasgos_nuevos, dtype=float)
    if ids_nuevos is None:
        ids_nuevos = [f"sample_{i}" for i in range(rasgos_nuevos.shape[0])]

    resultados = {}
    for doc_id, rasgo in zip(ids_nuevos, rasgos_nuevos):
        z = (rasgo - medias) / stds_safe
        distancias = {c: float(np.linalg.norm(z - centroides[c])) for c in nombres_clases}
        ordenadas = sorted(distancias.items(), key=lambda kv: kv[1])
        mejor_clase, mejor_dist = ordenadas[0]
        segunda_clase, segunda_dist = ordenadas[1] if len(ordenadas) > 1 else (None, None)
        margen = (segunda_dist - mejor_dist) if segunda_dist is not None else None
        resultados[doc_id] = {
            "clase_predicha": mejor_clase,
            "distancias": {c: round(d, 4) for c, d in distancias.items()},
            "margen_vs_segunda_opcion": round(margen, 4) if margen is not None else None,
            "ambiguo": bool(margen is not None and margen < 0.3 * mejor_dist) if mejor_dist > 0 else False,
        }

    return {
        "escalado": False,
        "clases_entrenamiento": conteos,
        "predicciones": resultados,
        "nota": ("clasificador nearest-centroid sobre rasgos normalizados (z-score) por rasgo -- no es un "
                 "clasificador robusto a outliers ni a clases con distribuciones muy distintas en forma "
                 "(solo compara distancia al promedio). 'ambiguo'=true cuando el margen con la segunda "
                 "clase mas cercana es chico -- tratar esos casos como no concluyentes, no forzar la clase predicha."),
    }


def _preset_classification_demo():
    rng = np.random.RandomState(11)
    clase_a = rng.normal(loc=[1.2, 15], scale=[0.1, 2], size=(6, 2))
    clase_b = rng.normal(loc=[2.4, 45], scale=[0.15, 3], size=(6, 2))
    rasgos_entrenamiento = np.vstack([clase_a, clase_b]).tolist()
    clases_entrenamiento = ["gotica_textura"] * 6 + ["humanistica"] * 6
    nuevo_a = (rng.normal(loc=[1.2, 15], scale=[0.1, 2], size=2)).tolist()
    nuevo_b = (rng.normal(loc=[2.4, 45], scale=[0.15, 3], size=2)).tolist()
    return rasgos_entrenamiento, clases_entrenamiento, [nuevo_a, nuevo_b], ["gotica_textura", "humanistica"]


# ---------------------------------------------------------------------------
# dispatcher
# ---------------------------------------------------------------------------

def compute_paleography(mode="validate", matriz=None, doc_ids=None, anios_conocidos=None,
                         anios_ancla=None, rasgo_ancla=None, rasgo_predecir=None, ids_predecir=None,
                         grado_polinomio=1,
                         rasgos_entrenamiento=None, clases_entrenamiento=None,
                         rasgos_nuevos=None, ids_nuevos=None):

    if mode == "validate":
        matriz_demo, doc_ids_demo, anios_conocidos_demo, anios_reales = _preset_seriation_demo()
        seriacion = _seriation(matriz_demo, doc_ids_demo, anios_conocidos_demo)
        orden_obtenido = seriacion.get("orden_seriado", [])
        rho = seriacion.get("chequeo_cronologico", {}).get("spearman_eje1_vs_anio")
        ok_seriacion = bool(orden_obtenido) and rho is not None and abs(rho) > 0.7

        anios_ancla_demo, rasgo_ancla_demo, rasgo_predecir_demo, anio_esperado_demo = _preset_dating_demo()
        dating = _feature_dating_regression(anios_ancla_demo, rasgo_ancla_demo, rasgo_predecir_demo)
        ok_dating = dating.get("r2_ajuste_ancla", 0) is not None and dating.get("r2_ajuste_ancla", 0) > 0.9
        if ok_dating:
            for i, doc_id in enumerate([f"undated_{i}" for i in range(len(rasgo_predecir_demo))]):
                estimado = dating["predicciones"][doc_id]["anio_estimado"]
                if abs(estimado - anio_esperado_demo[i]) > 15:
                    ok_dating = False

        rasgos_e, clases_e, rasgos_n, clases_n_esperadas = _preset_classification_demo()
        clasif = _clasificar_letterforms(rasgos_e, clases_e, rasgos_n)
        ok_clasif = not clasif.get("escalado", False)
        if ok_clasif:
            for doc_id, esperado in zip(["sample_0", "sample_1"], clases_n_esperadas):
                if clasif["predicciones"][doc_id]["clase_predicha"] != esperado:
                    ok_clasif = False

        ok = bool(ok_seriacion and ok_dating and ok_clasif)
        return {
            "ok": ok,
            "checks": {"seriation": bool(ok_seriacion), "feature_dating_regression": bool(ok_dating), "letterform_classification": bool(ok_clasif)},
            "seriation_sample": {"orden_seriado": orden_obtenido, "spearman_eje1_vs_anio": rho},
            "dating_sample": {"r2_ajuste_ancla": dating.get("r2_ajuste_ancla"), "predicciones": dating.get("predicciones")},
            "classification_sample": clasif.get("predicciones"),
        }

    if mode == "seriation":
        if matriz is None:
            return {"error": "mode='seriation' requiere 'matriz' (n_docs x n_rasgos, conteos/frecuencias no negativas)"}
        return _seriation(matriz, doc_ids, anios_conocidos)

    if mode == "feature_dating_regression":
        if anios_ancla is None or rasgo_ancla is None or rasgo_predecir is None:
            return {"error": "mode='feature_dating_regression' requiere 'anios_ancla', 'rasgo_ancla' (mismo largo, documentos de fecha conocida) y 'rasgo_predecir' (rasgos de documentos sin fecha)"}
        return _feature_dating_regression(anios_ancla, rasgo_ancla, rasgo_predecir, ids_predecir, grado=grado_polinomio)

    if mode == "letterform_classification":
        if rasgos_entrenamiento is None or clases_entrenamiento is None or rasgos_nuevos is None:
            return {"error": "mode='letterform_classification' requiere 'rasgos_entrenamiento' (n_muestras x n_rasgos), 'clases_entrenamiento' (etiquetas, mismo largo) y 'rasgos_nuevos' (muestras a clasificar)"}
        return _clasificar_letterforms(rasgos_entrenamiento, clases_entrenamiento, rasgos_nuevos, ids_nuevos)

    return {"error": f"modo desconocido: {mode!r} (validos: seriation, feature_dating_regression, letterform_classification, validate)"}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_paleography(mode="validate"), indent=2, ensure_ascii=False))
