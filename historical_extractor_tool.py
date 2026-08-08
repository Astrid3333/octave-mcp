"""
historical_extractor_tool.py -- extrae MULTIPLES series (anio, valor) de un
mismo texto historico, una por objeto/concepto mencionado (ej: trigo,
cebada, salario), y las pasa automaticamente a los motores ya existentes:
tendencia por regresion log-lineal (reusa _regresion_log_lineal de
historian_tool.py, no la reimplementa), salario real indexado (si hay una
serie de salario y al menos una de precio), y correlacion entre series de
precios que se solapan en anios.

Extraccion por oracion, no NLP: para cada oracion del texto, busca el
primer par (anio, valor) con el mismo patron que historian_tool, y lo
asigna a cada objeto de la lista `objetos` cuya palabra-clave aparezca en
esa oracion. Una oracion puede aportar a mas de un objeto si los menciona
juntos, pero aporta como maximo un (anio, valor) por oracion (el primero
que encuentra el regex) -- no separa multiples precios dentro de la misma
oracion.

Filosofia identica al resto del repo: con pocos datos, escala en vez de
adivinar. La salida da tasas, indices y correlaciones -- NO interpreta
causalidad historica (crisis, epidemias, etc), eso queda para quien lee
el resultado.
"""
import re
import numpy as np

from historian_tool import _regresion_log_lineal, MIN_PUNTOS


_PAT_ANIO_VALOR = re.compile(
    r'\b(1[3-9]\d{2}|20\d{2})\b[^\d]{0,60}?(\d+(?:[.,]\d{1,3})?)\b'
)

KEYWORDS_SALARIO_DEFAULT = ["salario", "jornal", "sueldo"]


def _to_float(s):
    return float(s.replace(",", "."))


def _dividir_oraciones(text_data):
    return [o for o in re.split(r'(?<=[.!?])\s+', text_data) if o.strip()]


def _extraer_series_por_objeto(text_data, objetos):
    """objetos: lista de keywords en minuscula. Devuelve dict
    {objeto: (anios_array, valores_array)} solo para objetos con >=1 punto."""
    oraciones = _dividir_oraciones(text_data)
    crudos = {obj: [] for obj in objetos}
    for oracion in oraciones:
        oracion_lower = oracion.lower()
        m = _PAT_ANIO_VALOR.search(oracion)
        if not m:
            continue
        anio = int(m.group(1))
        valor = _to_float(m.group(2))
        for obj in objetos:
            if obj in oracion_lower:
                crudos[obj].append((anio, valor))

    series = {}
    for obj, pares in crudos.items():
        if not pares:
            continue
        vistos = {}
        for anio, valor in pares:
            vistos.setdefault(anio, []).append(valor)
        anios = sorted(vistos.keys())
        valores = [sum(vistos[a]) / len(vistos[a]) for a in anios]
        series[obj] = (np.array(anios, dtype=float), np.array(valores, dtype=float))
    return series


def _tendencia_series(series):
    resultado = {}
    for obj, (anios, valores) in series.items():
        if len(anios) < MIN_PUNTOS:
            resultado[obj] = {"escalado": True, "razon": f"solo {len(anios)} puntos, minimo {MIN_PUNTOS}",
                               "anios": anios.tolist(), "valores": valores.tolist()}
            continue
        r = _regresion_log_lineal(anios, valores)
        if r is None:
            resultado[obj] = {"escalado": True, "razon": "valores no positivos, log-lineal no aplica"}
            continue
        resultado[obj] = {
            "escalado": False,
            "tasa_anual_pct": round(float(r["tasa_por_anio"]) * 100, 4),
            "r2_log_lineal": round(r["r2_log_lineal"], 6),
            "n_puntos": len(anios),
            "anio_min": int(anios.min()),
            "anio_max": int(anios.max()),
            "anios": anios.tolist(),
            "valores": valores.tolist(),
        }
    return resultado


def _salario_real(series, objeto_salario, objetos_precio):
    if objeto_salario not in series:
        return None
    anios_sal, valores_sal = series[objeto_salario]
    dict_sal = dict(zip(anios_sal.tolist(), valores_sal.tolist()))

    resultados_por_precio = {}
    for obj in objetos_precio:
        if obj not in series or obj == objeto_salario:
            continue
        anios_prec, valores_prec = series[obj]
        dict_prec = dict(zip(anios_prec.tolist(), valores_prec.tolist()))
        anios_comunes = sorted(set(dict_sal) & set(dict_prec))
        if len(anios_comunes) < 2:
            resultados_por_precio[obj] = {"escalado": True, "razon": "menos de 2 anios en comun con la serie de salario"}
            continue
        salario_real = [dict_sal[a] / dict_prec[a] for a in anios_comunes]
        base = salario_real[0]
        indice = [round(100 * v / base, 2) for v in salario_real]
        cambio_pct_total = round(100 * (salario_real[-1] / salario_real[0] - 1), 2)
        resultados_por_precio[obj] = {
            "escalado": False,
            "anios": anios_comunes,
            "salario_real_indice_100": indice,
            "cambio_pct_total": cambio_pct_total,
            "anio_inicial": anios_comunes[0],
            "anio_final": anios_comunes[-1],
        }
    return resultados_por_precio


def _correlacion_series(series, excluir):
    objetos_precio = [o for o in series if o not in excluir]
    matriz = {}
    for i, obj_a in enumerate(objetos_precio):
        for obj_b in objetos_precio[i + 1:]:
            anios_a, valores_a = series[obj_a]
            anios_b, valores_b = series[obj_b]
            dict_a = dict(zip(anios_a.tolist(), valores_a.tolist()))
            dict_b = dict(zip(anios_b.tolist(), valores_b.tolist()))
            anios_comunes = sorted(set(dict_a) & set(dict_b))
            if len(anios_comunes) < 3:
                matriz[f"{obj_a}__{obj_b}"] = {"escalado": True, "razon": "menos de 3 anios en comun"}
                continue
            va = np.array([dict_a[a] for a in anios_comunes])
            vb = np.array([dict_b[a] for a in anios_comunes])
            if np.std(va) == 0 or np.std(vb) == 0:
                matriz[f"{obj_a}__{obj_b}"] = {"escalado": True, "razon": "varianza cero en alguna serie"}
                continue
            corr = float(np.corrcoef(va, vb)[0, 1])
            matriz[f"{obj_a}__{obj_b}"] = {"escalado": False, "correlacion_pearson": round(corr, 4),
                                            "n_anios_comunes": len(anios_comunes)}
    return matriz


def _preset_mercado_demo():
    # trigo sube ~5%/anio, cebada correlacionada (sube junto con trigo),
    # salario del peon casi estancado -> salario real cae
    frases = []
    for i, anio in enumerate(range(1545, 1556)):
        precio_trigo = round(200 * (1.05 ** i), 1)
        precio_cebada = round(120 * (1.048 ** i), 1)
        salario = round(100 * (1.01 ** i), 1)
        frases.append(f"En {anio} el precio del trigo fue de {precio_trigo} maravedies.")
        frases.append(f"En {anio} la cebada se vendio a {precio_cebada} maravedies.")
        frases.append(f"El jornal de un peon en {anio} fue de {salario} maravedies al dia.")
    texto = " ".join(frases)
    verdad = {
        "tasa_trigo_esperada_pct": 5.0,
        "tasa_cebada_esperada_pct": 4.8,
        "correlacion_trigo_cebada_esperada_min": 0.95,
        "salario_real_cae": True,
    }
    return texto, verdad


def compute_historical_extractor(mode="validate", text_data=None, objetos=None,
                                  objeto_salario=None):
    if mode == "validate":
        texto, verdad = _preset_mercado_demo()
        objetos_demo = ["trigo", "cebada", "jornal"]
        series = _extraer_series_por_objeto(texto, objetos_demo)
        tendencias = _tendencia_series(series)
        salario_real = _salario_real(series, "jornal", ["trigo", "cebada"])
        correlaciones = _correlacion_series(series, excluir={"jornal"})

        ok_trigo = (not tendencias["trigo"]["escalado"]) and abs(tendencias["trigo"]["tasa_anual_pct"] - verdad["tasa_trigo_esperada_pct"]) < 0.3
        ok_cebada = (not tendencias["cebada"]["escalado"]) and abs(tendencias["cebada"]["tasa_anual_pct"] - verdad["tasa_cebada_esperada_pct"]) < 0.3
        corr_key = "trigo__cebada" if "trigo__cebada" in correlaciones else "cebada__trigo"
        ok_corr = (not correlaciones[corr_key]["escalado"]) and correlaciones[corr_key]["correlacion_pearson"] >= verdad["correlacion_trigo_cebada_esperada_min"]
        ok_salario = salario_real is not None and "trigo" in salario_real and (not salario_real["trigo"]["escalado"]) and salario_real["trigo"]["cambio_pct_total"] < 0

        ok = bool(ok_trigo and ok_cebada and ok_corr and ok_salario)
        return {
            "ok": ok,
            "tendencias": {k: {"tasa_anual_pct": v.get("tasa_anual_pct"), "r2": v.get("r2_log_lineal")} for k, v in tendencias.items()},
            "correlacion_trigo_cebada": correlaciones.get(corr_key),
            "salario_real_vs_trigo": salario_real.get("trigo") if salario_real else None,
            "checks": {"trigo": bool(ok_trigo), "cebada": bool(ok_cebada), "correlacion": bool(ok_corr), "salario_real": bool(ok_salario)},
        }

    if mode == "analyze":
        if not text_data:
            return {"error": "mode='analyze' requiere text_data"}
        if not objetos:
            return {"error": "mode='analyze' requiere 'objetos': lista de keywords en minuscula a buscar (ej: ['trigo','cebada','jornal'])"}
        objetos = [o.lower() for o in objetos]
        series = _extraer_series_por_objeto(text_data, objetos)
        if not series:
            return {"error": "no se extrajo ninguna serie -- revisar que los objetos mencionados en 'objetos' aparezcan efectivamente en el texto, cerca de un anio y un numero"}

        tendencias = _tendencia_series(series)
        resultado = {"objetos_detectados": list(series.keys()), "tendencias": tendencias}

        if objeto_salario:
            objeto_salario = objeto_salario.lower()
            objetos_precio = [o for o in objetos if o != objeto_salario]
            salario_real = _salario_real(series, objeto_salario, objetos_precio)
            resultado["salario_real"] = salario_real

        excluir = {objeto_salario.lower()} if objeto_salario else set()
        resultado["correlaciones"] = _correlacion_series(series, excluir)
        resultado["nota"] = ("extraccion por oracion via regex, no NLP -- si un objeto tiene pocos puntos "
                              "o el texto menciona varios precios en la misma oracion, revisar 'anios'/'valores' "
                              "crudos antes de confiar en la tasa. Ninguna interpretacion causal (crisis, "
                              "epidemias, etc) esta incluida -- eso es lectura historica, no salida del calculo.")
        return resultado

    return {"error": f"modo desconocido: {mode!r} (validos: analyze, validate)"}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_historical_extractor(mode="validate"), indent=2, ensure_ascii=False))
