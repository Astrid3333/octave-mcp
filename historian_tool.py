"""
historian_tool.py

Orquestador de analisis historico: NO hace NLP complejo. Parsea numeros de
texto historico via regex, los convierte en arrays de numpy, y los enruta
al motor de analisis correspondiente segun analysis_type:

  - "inflation"     -> extrae pares (anio, precio) y ajusta una tasa de
                       crecimiento compuesta (regresion log-lineal)
  - "demographics"  -> extrae pares (anio, poblacion) y ajusta el mismo
                       motor de regresion log-lineal (tasa de crecimiento
                       + tiempo de duplicacion)
  - "trade_network" -> extrae triples (origen, destino, volumen) y arma
                       una red de comercio ponderada (centralidad por
                       fuerza entrante + centralidad por autovector)

NOTA DE DISEÑO (importante): este modulo NO importa statistics_tool.py ni
linear_algebra_tool.py directamente -- no tengo acceso al codigo fuente
de esos archivos en tu repo desde esta sesion, asi que no puedo verificar
sus firmas exactas con certeza. Para no arriesgar romper el servidor con
un import a ciegas, reimplemente aca el minimo necesario (regresion por
minimos cuadrados via numpy, centralidad de red via autovectores) --
matematicamente equivalente a lo que harian esos modulos. Si me pasas las
firmas exactas de compute_statistics / compute_linear_algebra puedo
recablear esto para que llame a esos modulos en vez de reimplementar.

Filosofia (misma que socket_qa_engine / mapear_caras_a_secciones): con
pocos datos o extraccion ambigua, escala en vez de adivinar -- devuelve
advertencia en vez de una regresion con falsa precision.
"""

import re
import math
import numpy as np


MIN_PUNTOS = 3  # bajo este umbral, se escala en vez de ajustar


# ---------------------------------------------------------------------------
# extraccion via regex
# ---------------------------------------------------------------------------

_PAT_ANIO_VALOR = re.compile(
    r'\b(1[3-9]\d{2}|20\d{2})\b[^\d]{0,60}?(\d+(?:[.,]\d{1,3})?)\b'
)

_PAT_COMERCIO = re.compile(
    r'([A-ZÁÉÍÓÚÑÜ][a-zA-ZÁÉÍÓÚÑÜáéíóúñü]{2,25})\s+'
    r'(?:comerci\w*|export\w*|envi\w*|vendi\w*|mand\w*|import\w*\s+)?\s*'
    r'(?:hacia|hasta|con)\s+'
    r'([A-ZÁÉÍÓÚÑÜ][a-zA-ZÁÉÍÓÚÑÜáéíóúñü]{2,25})'
    r'[^\d]{0,25}?(\d+(?:[.,]\d+)?)\b'
)


def _to_float(s):
    return float(s.replace(",", "."))


def _extraer_serie_temporal(text_data):
    """Extrae pares (anio, valor) de texto libre. Un anio por punto (si se
    repite, se promedian los valores). Devuelve (anios, valores, pares_crudos)."""
    crudos = []
    vistos = {}
    for m in _PAT_ANIO_VALOR.finditer(text_data):
        anio = int(m.group(1))
        valor = _to_float(m.group(2))
        crudos.append({"anio": anio, "valor": valor, "match": m.group(0)})
        vistos.setdefault(anio, []).append(valor)

    anios = sorted(vistos.keys())
    valores = [sum(vistos[a]) / len(vistos[a]) for a in anios]
    return np.array(anios, dtype=float), np.array(valores, dtype=float), crudos


def _extraer_red_comercio(text_data):
    """Extrae triples (origen, destino, volumen) de texto libre."""
    triples = []
    for m in _PAT_COMERCIO.finditer(text_data):
        origen, destino, volumen = m.group(1), m.group(2), _to_float(m.group(3))
        triples.append({"origen": origen, "destino": destino, "volumen": volumen, "match": m.group(0)})
    return triples


# ---------------------------------------------------------------------------
# motores de analisis (reimplementados aca, ver nota de diseño arriba)
# ---------------------------------------------------------------------------

def _regresion_log_lineal(x, y):
    """Ajusta ln(y) = ln(y0) + r*(x - x_min) por minimos cuadrados.
    Devuelve r (tasa por unidad de x), y0, R^2."""
    if np.any(y <= 0):
        return None  # log-lineal no aplica con valores no positivos
    x0 = x - x.min()
    ln_y = np.log(y)
    A = np.vstack([x0, np.ones_like(x0)]).T
    (r, ln_y0), _, _, _ = np.linalg.lstsq(A, ln_y, rcond=None)
    y0 = math.exp(ln_y0)
    pred = r * x0 + ln_y0
    ss_res = float(np.sum((ln_y - pred) ** 2))
    ss_tot = float(np.sum((ln_y - ln_y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 1.0
    return {"tasa_por_anio": r, "valor_inicial_estimado": y0, "r2_log_lineal": r2}


def _centralidad_red(triples):
    """Arma grafo dirigido ponderado desde los triples y calcula:
    fuerza_entrante (suma de pesos entrantes), fuerza_saliente, y
    centralidad de autovector sobre la version simetrizada."""
    nodos = sorted({t["origen"] for t in triples} | {t["destino"] for t in triples})
    idx = {n: i for i, n in enumerate(nodos)}
    n = len(nodos)
    W = np.zeros((n, n))
    for t in triples:
        W[idx[t["origen"]], idx[t["destino"]]] += t["volumen"]

    fuerza_entrante = W.sum(axis=0)
    fuerza_saliente = W.sum(axis=1)

    # centralidad de autovector sobre la matriz simetrizada (no dirigida)
    Wsym = W + W.T
    if n > 0 and np.any(Wsym):
        eigvals, eigvecs = np.linalg.eigh(Wsym)
        v = np.abs(eigvecs[:, np.argmax(eigvals)])
        if v.sum() > 0:
            v = v / v.sum()
    else:
        v = np.zeros(n)

    ranking = sorted(
        (
            {
                "nodo": nodos[i],
                "fuerza_entrante": float(fuerza_entrante[i]),
                "fuerza_saliente": float(fuerza_saliente[i]),
                "centralidad_autovector": float(v[i]),
            }
            for i in range(n)
        ),
        key=lambda d: d["centralidad_autovector"],
        reverse=True,
    )
    return {
        "nodos": nodos,
        "ranking": ranking,
        "hub_principal": ranking[0]["nodo"] if ranking else None,
    }


# ---------------------------------------------------------------------------
# analisis de alto nivel por tipo
# ---------------------------------------------------------------------------

def _analizar_inflation(text_data):
    anios, valores, crudos = _extraer_serie_temporal(text_data)
    if len(anios) < MIN_PUNTOS:
        return {
            "escalado": True,
            "motivo": f"solo se extrajeron {len(anios)} puntos (anio, precio); "
                      f"se necesitan al menos {MIN_PUNTOS} para un ajuste confiable",
            "pares_crudos_encontrados": crudos,
        }
    ajuste = _regresion_log_lineal(anios, valores)
    if ajuste is None:
        return {"escalado": True, "motivo": "hay precios <= 0, no aplica ajuste log-lineal", "pares_crudos_encontrados": crudos}
    return {
        "escalado": False,
        "n_puntos": len(anios),
        "anios": anios.tolist(),
        "precios": valores.tolist(),
        "tasa_inflacion_anual_pct": round(ajuste["tasa_por_anio"] * 100, 4),
        "precio_inicial_estimado": round(ajuste["valor_inicial_estimado"], 4),
        "r2_log_lineal": round(ajuste["r2_log_lineal"], 6),
        "pares_crudos_encontrados": crudos,
    }


def _analizar_demographics(text_data):
    anios, valores, crudos = _extraer_serie_temporal(text_data)
    if len(anios) < MIN_PUNTOS:
        return {
            "escalado": True,
            "motivo": f"solo se extrajeron {len(anios)} puntos (anio, poblacion); "
                      f"se necesitan al menos {MIN_PUNTOS} para un ajuste confiable",
            "pares_crudos_encontrados": crudos,
        }
    ajuste = _regresion_log_lineal(anios, valores)
    if ajuste is None:
        return {"escalado": True, "motivo": "hay poblaciones <= 0, no aplica ajuste log-lineal", "pares_crudos_encontrados": crudos}
    r = ajuste["tasa_por_anio"]
    tiempo_duplicacion = (math.log(2) / r) if r > 0 else None
    return {
        "escalado": False,
        "n_puntos": len(anios),
        "anios": anios.tolist(),
        "poblacion": valores.tolist(),
        "tasa_crecimiento_anual_pct": round(r * 100, 4),
        "poblacion_inicial_estimada": round(ajuste["valor_inicial_estimado"], 2),
        "tiempo_duplicacion_anios": round(tiempo_duplicacion, 2) if tiempo_duplicacion else None,
        "r2_log_lineal": round(ajuste["r2_log_lineal"], 6),
        "pares_crudos_encontrados": crudos,
    }


def _analizar_trade_network(text_data):
    triples = _extraer_red_comercio(text_data)
    if len(triples) < MIN_PUNTOS:
        return {
            "escalado": True,
            "motivo": f"solo se extrajeron {len(triples)} relaciones de comercio (origen, destino, volumen); "
                      f"se necesitan al menos {MIN_PUNTOS} para una red util",
            "triples_crudos_encontrados": triples,
        }
    resultado = _centralidad_red(triples)
    resultado["escalado"] = False
    resultado["n_relaciones"] = len(triples)
    resultado["triples_crudos_encontrados"] = triples
    return resultado


from units_entropy import analyze_units_entropy


def _analizar_units_entropy(text_data, min_mentions=3):
    categorias = analyze_units_entropy(text_data, min_mentions=min_mentions)
    resueltas = {k: v for k, v in categorias.items() if v.get("ok")}
    escalado = len(resueltas) == 0
    resultado = {"escalado": escalado, "categorias": categorias}
    if resueltas:
        principal = max(resueltas, key=lambda k: resueltas[k]["total"])
        resultado["categoria_principal"] = principal
        resultado["homogeneidad_pct"] = resueltas[principal]["homogeneidad_pct"]
        resultado["unidad_dominante"] = resueltas[principal]["unidad_dominante"]
    if escalado:
        resultado["warning"] = "ninguna categoria alcanzo el minimo de menciones; ver 'categorias' para los conteos crudos"
    return resultado


import math
from collections import Counter
from scipy import stats as _stats

_BENFORD_ESPERADO = {d: math.log10(1 + 1 / d) for d in range(1, 10)}


def _primeros_digitos(text_data):
    numeros = re.findall(r"\d+(?:[.,]\d+)?", text_data)
    digitos = []
    for n in numeros:
        n_limpio = n.replace(",", ".").lstrip("0")
        if not n_limpio or n_limpio[0] == ".":
            continue
        if n_limpio[0].isdigit() and n_limpio[0] != "0":
            digitos.append(int(n_limpio[0]))
    return digitos


def _analizar_benford(text_data, min_muestras=30):
    digitos = _primeros_digitos(text_data)
    n = len(digitos)
    if n < min_muestras:
        return {"escalado": True, "razon": f"solo {n} numeros extraidos, minimo {min_muestras}"}
    conteo = Counter(digitos)
    observado = np.array([conteo.get(d, 0) for d in range(1, 10)], dtype=float)
    esperado_frac = np.array([_BENFORD_ESPERADO[d] for d in range(1, 10)])
    esperado = esperado_frac * n
    chi2, p_valor = _stats.chisquare(observado, esperado)
    return {
        "escalado": False,
        "n_muestras": n,
        "distribucion_observada_pct": {str(d): round(100 * observado[d-1] / n, 2) for d in range(1, 10)},
        "distribucion_benford_esperada_pct": {str(d): round(100 * esperado_frac[d-1], 2) for d in range(1, 10)},
        "chi2": float(chi2),
        "p_valor": float(p_valor),
        "desviacion_significativa": bool(p_valor < 0.05),
    }


def _preset_benford_natural():
    valores = [round(10 ** (i / 50), 2) for i in range(150)]
    partes = [f"El padron registro {v} quintales de tributo." for v in valores]
    return " ".join(partes), {"benford_esperado": True}


def _preset_benford_inventado():
    valores = [500] * 20 + [50] * 15 + [5000] * 15 + [55] * 10
    partes = [f"El padron registro {v} quintales de tributo." for v in valores]
    return " ".join(partes), {"benford_esperado": False}


_ANALIZADORES = {
    "inflation": _analizar_inflation,
    "demographics": _analizar_demographics,
    "trade_network": _analizar_trade_network,
    "units_entropy": _analizar_units_entropy,
    "benford": _analizar_benford,
}


# ---------------------------------------------------------------------------
# presets de validacion (texto sintetico con verdad conocida)
# ---------------------------------------------------------------------------

def _preset_texto(preset):
    if preset == "inflation_demo":
        # tasa real incrustada: 2% anual desde precio 10 en 1700
        base, r, anio0 = 10.0, 0.02, 1700
        partes = []
        for k in range(8):
            anio = anio0 + k * 5
            precio = base * math.exp(r * (anio - anio0))
            partes.append(f"En {anio} el precio del trigo en Castro fue de {precio:.2f} reales por fanega.")
        return " ".join(partes), {"tasa_esperada_pct": r * 100}

    if preset == "demographics_demo":
        # tasa real incrustada: 1.5% anual desde poblacion 500 en 1750
        base, r, anio0 = 500.0, 0.015, 1750
        partes = []
        for k in range(8):
            anio = anio0 + k * 5
            pob = base * math.exp(r * (anio - anio0))
            partes.append(f"El censo de {anio} registro {pob:.0f} habitantes en Chiloe.")
        return " ".join(partes), {"tasa_esperada_pct": r * 100}

    if preset == "trade_network_demo":
        # Castro es el hub deliberado: recibe de todos, envia poco
        frases = [
            "Ancud comercio hacia Castro 120 quintales de papas.",
            "Quemchi comercio hacia Castro 90 quintales de mariscos.",
            "Dalcahue comercio hacia Castro 60 quintales de lana.",
            "Castro comercio hacia Ancud 15 quintales de sal.",
            "Ancud comercio hacia Quemchi 20 quintales de harina.",
        ]
        return " ".join(frases), {"hub_esperado": "Castro"}

    if preset == "units_entropy_demo":
        # capacidad homogenea deliberada: una sola unidad (fanega) repetida
        frases = [
            "Se cobraron 40 fanegas de trigo al senor.",
            "El diezmo sumo otras 30 fanegas de cebada.",
            "Ademas se registraron 25 fanegas de centeno en el granero.",
        ]
        return " ".join(frases), {
            "categoria_esperada": "capacidad",
            "unidad_esperada": "fanega",
            "homogeneidad_esperada_pct": 100.0,
        }

    if preset == "benford_natural_demo":
        return _preset_benford_natural()

    if preset == "benford_inventado_demo":
        return _preset_benford_inventado()

    raise ValueError(f"preset desconocido: {preset!r}")


def _validar():
    resultados = {}

    texto, verdad = _preset_texto("inflation_demo")
    r = _analizar_inflation(texto)
    ok_inflation = (
        not r["escalado"]
        and abs(r["tasa_inflacion_anual_pct"] - verdad["tasa_esperada_pct"]) < 0.05
        and r["r2_log_lineal"] > 0.999
    )
    resultados["inflation"] = {"ok": ok_inflation, "tasa_recuperada_pct": r.get("tasa_inflacion_anual_pct"), "tasa_esperada_pct": verdad["tasa_esperada_pct"]}

    texto, verdad = _preset_texto("demographics_demo")
    r = _analizar_demographics(texto)
    ok_demo = (
        not r["escalado"]
        and abs(r["tasa_crecimiento_anual_pct"] - verdad["tasa_esperada_pct"]) < 0.05
        and r["r2_log_lineal"] > 0.999
    )
    resultados["demographics"] = {"ok": ok_demo, "tasa_recuperada_pct": r.get("tasa_crecimiento_anual_pct"), "tasa_esperada_pct": verdad["tasa_esperada_pct"]}

    texto, verdad = _preset_texto("trade_network_demo")
    r = _analizar_trade_network(texto)
    ok_trade = (not r["escalado"]) and r["hub_principal"] == verdad["hub_esperado"]
    resultados["trade_network"] = {"ok": ok_trade, "hub_recuperado": r.get("hub_principal"), "hub_esperado": verdad["hub_esperado"]}

    texto, verdad = _preset_texto("units_entropy_demo")
    r = _analizar_units_entropy(texto)
    ok_entropy = (
        not r["escalado"]
        and r.get("categoria_principal") == verdad["categoria_esperada"]
        and r.get("unidad_dominante") == verdad["unidad_esperada"]
        and abs(r.get("homogeneidad_pct", -1) - verdad["homogeneidad_esperada_pct"]) < 0.01
    )
    resultados["units_entropy"] = {"ok": ok_entropy, "homogeneidad_recuperada_pct": r.get("homogeneidad_pct"), "homogeneidad_esperada_pct": verdad["homogeneidad_esperada_pct"]}

    texto, verdad = _preset_texto("benford_natural_demo")
    r = _analizar_benford(texto)
    ok_benford_natural = (not r["escalado"]) and not r["desviacion_significativa"]
    resultados["benford_natural"] = {"ok": ok_benford_natural, "p_valor": r.get("p_valor")}

    texto, verdad = _preset_texto("benford_inventado_demo")
    r = _analizar_benford(texto)
    ok_benford_inventado = (not r["escalado"]) and r["desviacion_significativa"]
    resultados["benford_inventado"] = {"ok": ok_benford_inventado, "p_valor": r.get("p_valor")}

    resultados["todos_correctos"] = ok_inflation and ok_demo and ok_trade and ok_benford_natural and ok_benford_inventado and ok_entropy
    return resultados


# ---------------------------------------------------------------------------
# entrypoint
# ---------------------------------------------------------------------------

def compute_historian(mode="validate", analysis_type="inflation", text_data=None, preset=None):
    if mode == "validate":
        return _validar()

    if mode == "analyze":
        if analysis_type not in _ANALIZADORES:
            return {"error": f"analysis_type invalido: {analysis_type!r} (validos: {list(_ANALIZADORES)})"}
        if text_data is None and preset is not None:
            text_data, _ = _preset_texto(preset)
        if not text_data:
            return {"error": "hay que pasar text_data (o un preset de demo) para mode='analyze'"}
        return _ANALIZADORES[analysis_type](text_data)

    return {"error": f"modo desconocido: {mode!r} (validos: analyze, validate)"}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_historian(mode="validate"), indent=2, ensure_ascii=False))
