"""
numeral_systems_embedding_tool.py

Vectoriza sistemas numericos antiguos (base, tipo, presencia de cero,
redundancia representacional, si usa dispositivo fisico) y proyecta a 2D
via UMAP o t-SNE, para explorar agrupamientos y posibles "migraciones
culturales" (sistemas estructuralmente cercanos, aunque geograficamente
distantes, o viceversa).

Dataset (11 sistemas) extraido de los sistemas YA implementados en
ethnomath_tool.py, ancient_calculators_tool.py y ancestral_octave_tool.py --
no reinventa los algoritmos, solo agrega la capa de metadata estructural
que esos tools no exponen (base, tipo, region, periodo).

IMPORTANTE sobre las features: se vectorizan atributos ESTRUCTURALES
(base, tipo, cero, redundancia, soporte fisico) -- NO region ni periodo.
Region/periodo se guardan como metadata para colorear el plot despues,
pero deliberadamente no entran al vector de distancia: si entraran, el
clustering por region seria circular (agruparia por la etiqueta que
justamente queremos usar para *interpretar* los clusters resultantes,
no para producirlos).

LIMITACION EXPLICITA DE ESCALA: con datasets chicos (<30 puntos, como el
inicial de 7), los hiperparametros por defecto de t-SNE (perplexity=30) y
UMAP (n_neighbors=15) EXCEDEN el numero de muestras y producen error o un
embedding sin sentido. Este modulo clampea automaticamente ambos valores
a n_samples-1 como maximo. A medida que el dataset crezca (via
extra_systems), estos valores efectivos van a crecer tambien -- pero con
pocos puntos el embedding 2D es mas una curiosidad exploratoria que una
proyeccion topologicamente confiable; eso se refleja en la nota_metodologica
de la respuesta.

INTEGRACION EN server.py:

    from numeral_systems_embedding_tool import compute_numeral_systems_embedding

    @mcp.tool()
    def numeral_systems_embedding(method: str = "umap", extra_systems: list = None,
                                   n_neighbors: int = None, perplexity: float = None,
                                   random_state: int = 1, run_id: str = None) -> dict:
        return compute_numeral_systems_embedding(method, extra_systems, n_neighbors,
                                                    perplexity, random_state, run_id)
"""
import math
import numpy as np

from workspace_tool import save_run

# ---------------------------------------------------------------------------
# DATASET: 7 sistemas ya cubiertos por ethnomath_tool / ancient_calculators_tool
# / ancestral_octave_tool. "source_tool" apunta a donde vive el algoritmo real.
# ---------------------------------------------------------------------------
NUMERAL_SYSTEMS_DATASET = [
    {
        "name": "maya_long_count",
        "region": "Mesoamerica",
        "period": "~400 BCE - 1500 CE",
        "base": 20,
        "type": "positional",
        "has_zero": True,
        "redundant": False,
        "physical_device": False,
        "source_tool": "ethnomath_tool.compute_maya_long_count",
        "nota": "vigesimal mixto: uinal tope en 18 (no 20), resto puro base 20",
    },
    {
        "name": "suanpan",
        "region": "China",
        "period": "~200 BCE - presente",
        "base": 10,
        "type": "physical_encoding",
        "has_zero": True,
        "redundant": True,
        "physical_device": True,
        "source_tool": "ancient_calculators_tool.compute_suanpan",
        "nota": "2 cuentas cielo (x5) + 5 cuentas tierra (x1): permite representaciones redundantes",
    },
    {
        "name": "soroban",
        "region": "Japon",
        "period": "~1600 CE - presente",
        "base": 10,
        "type": "physical_encoding",
        "has_zero": True,
        "redundant": False,
        "physical_device": True,
        "source_tool": "ancient_calculators_tool.compute_soroban",
        "nota": "1 cuenta cielo (x5) + 4 cuentas tierra (x1): sin redundancia, exactamente 0-9",
    },
    {
        "name": "roman_hand_abacus",
        "region": "Roma",
        "period": "~500 BCE - 500 CE",
        "base": 10,
        "type": "additive",
        "has_zero": False,
        "redundant": False,
        "physical_device": True,
        "source_tool": "ancient_calculators_tool.compute_roman_hand_abacus",
        "nota": "decimal-quinario para parte entera + columna duodecimal (unciae) para fracciones",
    },
    {
        "name": "yupana_depasquale",
        "region": "Andes (Inca)",
        "period": "~1400 - 1532 CE",
        "base": 40,
        "type": "physical_encoding",
        "has_zero": False,
        "redundant": False,
        "physical_device": True,
        "source_tool": "ancient_calculators_tool.compute_yupana_depasquale",
        "nota": "hipotesis De Pasquale (2001), EN DISPUTA academica -- campos Fibonacci 1,2,3,5",
    },
    {
        "name": "quipu",
        "region": "Andes (Inca)",
        "period": "~1400 - 1532 CE",
        "base": 10,
        "type": "physical_encoding",
        "has_zero": True,
        "redundant": False,
        "physical_device": True,
        "source_tool": "ethnomath_tool.compute_quipu_encode",
        "nota": "cero = ausencia de nudos en esa posicion; valor posicional por distancia al cordon principal",
    },
    {
        "name": "ifa_binary",
        "region": "Africa Occidental (Yoruba)",
        "period": "antiguo - presente",
        "base": 2,
        "type": "physical_encoding",
        "has_zero": False,
        "redundant": False,
        "physical_device": True,
        "source_tool": "ancestral_octave_tool (preset ifa_cast)",
        "nota": "256 odu posibles via 8 lanzamientos binarios (cadena de opele o semillas ikin)",
    },
    {
        "name": "babylonian_sexagesimal",
        "region": "Mesopotamia",
        "period": "~1900 BCE - 100 CE",
        "base": 60,
        "type": "positional",
        "has_zero": False,
        "redundant": False,
        "physical_device": False,
        "source_tool": None,
        "nota": "posicional sexagesimal en cuneiforme; el 'hueco' como placeholder aparece tarde y no funciona como cero terminal hasta periodo seleucida",
    },
    {
        "name": "egyptian_hieroglyphic",
        "region": "Egipto",
        "period": "~3000 BCE - 300 CE",
        "base": 10,
        "type": "additive",
        "has_zero": False,
        "redundant": False,
        "physical_device": False,
        "source_tool": None,
        "nota": "simbolo distinto por potencia de 10 (1, 10, 100...), sin valor posicional, se suman los simbolos presentes",
    },
    {
        "name": "indo_arabic",
        "region": "India / difusion global via mundo arabe",
        "period": "~500 CE - presente",
        "base": 10,
        "type": "positional",
        "has_zero": True,
        "redundant": False,
        "physical_device": False,
        "source_tool": None,
        "nota": "sistema posicional con cero explicito que termino desplazando a la mayoria de los sistemas aditivos regionales",
    },
    {
        "name": "greek_attic_ionic",
        "region": "Grecia",
        "period": "~600 BCE - 300 CE",
        "base": 10,
        "type": "additive",
        "has_zero": False,
        "redundant": False,
        "physical_device": False,
        "source_tool": None,
        "nota": "sistema jonico/alfabetico: letras asignadas a unidades/decenas/centenas (variante posterior al aticoacrofonico), aditivo sin valor posicional",
    },
]

# Orden fijo de features numericas para la vectorizacion
_FEATURE_KEYS = ["log2_base", "is_positional", "is_additive", "is_physical_encoding",
                  "has_zero", "redundant", "physical_device"]


def _system_to_vector(sys_dict):
    tipo = sys_dict["type"]
    return [
        math.log2(sys_dict["base"]),
        1.0 if tipo == "positional" else 0.0,
        1.0 if tipo == "additive" else 0.0,
        1.0 if tipo == "physical_encoding" else 0.0,
        1.0 if sys_dict["has_zero"] else 0.0,
        1.0 if sys_dict["redundant"] else 0.0,
        1.0 if sys_dict["physical_device"] else 0.0,
    ]


def _normalize_columns(X):
    """Normaliza cada columna a media 0, desvio 1 (evita que log2_base con
    rango mas amplio domine la distancia frente a las columnas binarias)."""
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std[std == 0] = 1.0
    return (X - mean) / std


def compute_numeral_systems_embedding(
    method="umap",
    extra_systems=None,
    n_neighbors=None,
    perplexity=None,
    random_state=1,
    run_id=None,
):
    """
    Vectoriza sistemas numericos (dataset base + extra_systems opcional) y
    proyecta a 2D via UMAP o t-SNE.

    Args:
        method: "umap" o "tsne".
        extra_systems: lista opcional de dicts con el mismo schema que
            NUMERAL_SYSTEMS_DATASET, para extender el dataset sin editar
            este archivo (util para expandir el catalogo iterativamente).
        n_neighbors: solo UMAP. Si None, se clampea automaticamente a
            min(15, n_samples-1).
        perplexity: solo t-SNE. Si None, se clampea automaticamente a
            min(30, n_samples-1)/3 (heuristica conservadora para datasets chicos).
        random_state: semilla para reproducibilidad.
        run_id: si se indica, guarda embedding_coords en el workspace junto
            con names/regions/periods en meta, para graficar despues con
            plot_workspace_run (plot_type=numeral_embedding).

    Returns:
        dict con method, n_systems, coords (lista de [x,y] en el mismo orden
        que systems), systems (metadata completa), nota_metodologica.
    """
    systems = list(NUMERAL_SYSTEMS_DATASET)
    if extra_systems:
        systems = systems + list(extra_systems)

    n = len(systems)
    if n < 3:
        return {"error": f"se necesitan al menos 3 sistemas para un embedding, hay {n}"}

    X = np.array([_system_to_vector(s) for s in systems])
    X = _normalize_columns(X)

    if method == "umap":
        import umap
        effective_n_neighbors = n_neighbors if n_neighbors is not None else min(15, n - 1)
        effective_n_neighbors = max(2, min(effective_n_neighbors, n - 1))
        reducer = umap.UMAP(n_neighbors=effective_n_neighbors, n_components=2,
                             random_state=random_state, min_dist=0.3)
        coords = reducer.fit_transform(X)
        method_params = {"n_neighbors": effective_n_neighbors}
    elif method == "tsne":
        from sklearn.manifold import TSNE
        effective_perplexity = perplexity if perplexity is not None else max(2, min(30, n - 1) / 3)
        effective_perplexity = max(2.0, min(effective_perplexity, n - 1))
        reducer = TSNE(n_components=2, perplexity=effective_perplexity,
                        random_state=random_state, init="pca")
        coords = reducer.fit_transform(X)
        method_params = {"perplexity": effective_perplexity}
    else:
        return {"error": f"method debe ser 'umap' o 'tsne', recibido: {method}"}

    names = [s["name"] for s in systems]
    regions = [s["region"] for s in systems]
    periods = [s["period"] for s in systems]

    result = {
        "method": method,
        "method_params": method_params,
        "n_systems": n,
        "names": names,
        "regions": regions,
        "periods": periods,
        "coords": coords.tolist(),
        "systems": systems,
        "nota_metodologica": (
            f"Con n={n} sistemas, los hiperparametros de vecindad/perplexity "
            "fueron clampeados automaticamente para evitar errores o embeddings "
            "sin sentido (los defaults de UMAP/t-SNE asumen >>30 muestras). "
            "Con pocos puntos, la posicion 2D es mas exploratoria que una "
            "proyeccion topologicamente robusta -- interpretar cercanias con "
            "cautela hasta expandir el dataset via extra_systems."
        ),
    }

    result["trajectory_saved"] = False
    result["run_id"] = None
    if run_id:
        save_result = save_run(
            run_id,
            {"embedding_coords": coords},
            {
                "tool": "compute_numeral_systems_embedding",
                "method": method,
                "method_params": method_params,
                "names": names,
                "regions": regions,
                "periods": periods,
                "n_systems": n,
            },
        )
        result["run_id"] = save_result.get("run_id")
        result["trajectory_saved"] = "error" not in save_result

    return result


NUMERAL_EMBEDDING_SCHEMA = {
    "name": "numeral_systems_embedding",
    "description": (
        "Vectoriza sistemas numericos antiguos (base, tipo posicional/aditivo/"
        "fisico, presencia de cero, redundancia representacional, soporte "
        "fisico) y proyecta a 2D via UMAP o t-SNE, para explorar agrupamientos "
        "estructurales. Dataset base: maya_long_count, suanpan, soroban, "
        "roman_hand_abacus, yupana_depasquale, quipu, ifa_binary, "
        "babylonian_sexagesimal, egyptian_hieroglyphic, indo_arabic, "
        "greek_attic_ionic. Extensible "
        "via extra_systems (mismo schema)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "method": {"type": "string", "enum": ["umap", "tsne"], "default": "umap"},
            "extra_systems": {"type": "array", "description": "Lista opcional de sistemas adicionales, mismo schema que el dataset base"},
            "n_neighbors": {"type": "integer", "description": "Solo UMAP, se clampea automaticamente si se omite"},
            "perplexity": {"type": "number", "description": "Solo t-SNE, se clampea automaticamente si se omite"},
            "random_state": {"type": "integer", "default": 1},
            "run_id": {"type": "string", "description": "Si se indica, guarda embedding en el workspace para graficar con plot_workspace_run"},
        },
    },
}


if __name__ == "__main__":
    import json
    r = compute_numeral_systems_embedding(method="umap", run_id="_numeral_selftest")
    print("umap:", r.get("trajectory_saved"), r.get("run_id"))
    print(json.dumps({"coords": r["coords"], "names": r["names"]}, indent=2, ensure_ascii=False))

    r2 = compute_numeral_systems_embedding(method="tsne")
    print("tsne perplexity used:", r2.get("method_params"))

    from workspace_tool import delete_run
    delete_run("_numeral_selftest")
