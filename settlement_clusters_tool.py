"""
settlement_clusters_tool.py -- proxy arqueologico de "barrios" o clusters
sociales a partir de coordenadas de hallazgos (ceramica, huesos, estructuras)
agrupadas por estrato/periodo. Clusteriza por distancia (union-find a un
radio fijo, equivalente a single-linkage cortado a esa escala) en cada
periodo, y rastrea clusters entre periodos consecutivos por proximidad de
centroides para detectar nacimiento (sin match en periodo anterior) y
muerte (sin match en periodo siguiente) de asentamientos. No hace
inferencia cronologica -- el orden de periodos lo define quien llama.
"""
import math
import numpy as np
from workspace_tool import save_run


def _dist(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _clusterizar_periodo_full(puntos, radio):
    n = len(puntos)
    padre = list(range(n))

    def find(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            padre[ri] = rj

    for i in range(n):
        for j in range(i + 1, n):
            if _dist(puntos[i], puntos[j]) <= radio:
                union(i, j)

    grupos = {}
    for i in range(n):
        r = find(i)
        grupos.setdefault(r, []).append(i)

    clusters = []
    labels = [0] * n
    for local_id, indices in enumerate(grupos.values()):
        pts = [puntos[i] for i in indices]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        clusters.append({"centroide": (cx, cy), "n_puntos": len(pts)})
        for i in indices:
            labels[i] = local_id
    return clusters, labels


def _clusterizar_periodo(puntos, radio):
    clusters, _ = _clusterizar_periodo_full(puntos, radio)
    return clusters


def _rastrear_ciclos_vida(clusters_por_periodo, periodos, radio_match):
    eventos = []
    ids_activos = {}
    siguiente_id = 0

    for idx_p, clusters in enumerate(clusters_por_periodo):
        ids_este_periodo = {}
        usados_previos = set()
        for c in clusters:
            mejor_id, mejor_dist = None, None
            if idx_p > 0:
                for id_prev, centroide_prev in ids_activos.items():
                    if id_prev in usados_previos:
                        continue
                    d = _dist(c["centroide"], centroide_prev)
                    if d <= radio_match and (mejor_dist is None or d < mejor_dist):
                        mejor_id, mejor_dist = id_prev, d
            if mejor_id is not None:
                ids_este_periodo[mejor_id] = c["centroide"]
                usados_previos.add(mejor_id)
            else:
                ids_este_periodo[siguiente_id] = c["centroide"]
                eventos.append({"evento": "nacimiento", "cluster_id": siguiente_id,
                                 "periodo": periodos[idx_p]})
                siguiente_id += 1

        if idx_p > 0:
            for id_prev in ids_activos:
                if id_prev not in usados_previos:
                    eventos.append({"evento": "muerte", "cluster_id": id_prev,
                                     "periodo_ultimo_visto": periodos[idx_p - 1]})

        ids_activos = ids_este_periodo

    for id_prev in ids_activos:
        eventos.append({"evento": "persiste_hasta_el_final", "cluster_id": id_prev,
                         "periodo_ultimo_visto": periodos[-1]})

    return eventos


def _preset_migracion_demo():
    periodo1 = [(0, 0), (0.2, 0.1), (0.1, -0.1), (10, 10), (10.2, 9.9)]
    periodo2 = [(0.1, 0.05), (0.15, -0.05), (-0.1, 0.1), (5, 5), (5.1, 4.9), (5.2, 5.1)]
    periodo3 = [(0.05, 0.0), (0.2, 0.15), (5.05, 5.05), (5.15, 4.95)]
    puntos_por_periodo = [periodo1, periodo2, periodo3]
    periodos = ["estrato_1", "estrato_2", "estrato_3"]
    return puntos_por_periodo, periodos


def compute_settlement_clusters(mode="validate", puntos_por_periodo=None,
                                 periodos=None, radio=1.0, radio_match=2.0, run_id=None):
    if mode == "validate":
        puntos_por_periodo, periodos = _preset_migracion_demo()
        clusters_por_periodo = [_clusterizar_periodo(pts, radio) for pts in puntos_por_periodo]
        eventos = _rastrear_ciclos_vida(clusters_por_periodo, periodos, radio_match)

        n_nacimientos = sum(1 for e in eventos if e["evento"] == "nacimiento")
        n_muertes = sum(1 for e in eventos if e["evento"] == "muerte")
        n_persisten = sum(1 for e in eventos if e["evento"] == "persiste_hasta_el_final")

        ok_persiste = n_persisten == 2  # cluster origen (A) + cluster nacido en estrato_2 (B)
        ok_nace_B = any(e["evento"] == "nacimiento" and e["periodo"] == "estrato_2" for e in eventos)
        ok_muere_C = any(e["evento"] == "muerte" and e["periodo_ultimo_visto"] == "estrato_1" for e in eventos)
        ok = ok_persiste and ok_nace_B and ok_muere_C

        return {
            "ok": ok,
            "n_nacimientos": n_nacimientos,
            "n_muertes": n_muertes,
            "n_persisten_hasta_el_final": n_persisten,
            "eventos": eventos,
            "clusters_por_periodo": [len(c) for c in clusters_por_periodo],
        }

    if mode == "analyze":
        if not puntos_por_periodo or not periodos:
            return {"error": "mode='analyze' requiere puntos_por_periodo (lista de listas de [x,y]) y periodos (misma longitud)"}
        if len(puntos_por_periodo) != len(periodos):
            return {"error": "puntos_por_periodo y periodos deben tener el mismo largo"}
        puntos_por_periodo = [[tuple(p) for p in pts] for pts in puntos_por_periodo]

        full_por_periodo = [_clusterizar_periodo_full(pts, radio) for pts in puntos_por_periodo]
        clusters_por_periodo = [c for c, _ in full_por_periodo]
        eventos = _rastrear_ciclos_vida(clusters_por_periodo, periodos, radio_match)

        result = {
            "clusters_por_periodo": [
                {"periodo": periodos[i], "n_clusters": len(c),
                 "clusters": [{"centroide": cl["centroide"], "n_puntos": cl["n_puntos"]} for cl in c]}
                for i, c in enumerate(clusters_por_periodo)
            ],
            "eventos": eventos,
            "nota": "radio y radio_match son supuestos de escala espacial, no calibrados a ningun sitio real -- ajustar segun densidad de hallazgos y separacion tipica entre asentamientos conocidos de la region.",
        }

        result["trajectory_saved"] = False
        result["run_id"] = None
        if run_id:
            rows = []
            for idx_periodo, (pts, (_, labels)) in enumerate(zip(puntos_por_periodo, full_por_periodo)):
                for (x, y), label in zip(pts, labels):
                    rows.append([idx_periodo, x, y, label])
            points_all = np.array(rows) if rows else np.zeros((0, 4))

            centroid_rows = []
            for idx_periodo, clusters in enumerate(clusters_por_periodo):
                for local_id, cl in enumerate(clusters):
                    centroid_rows.append([idx_periodo, cl["centroide"][0], cl["centroide"][1], local_id, cl["n_puntos"]])
            centroids_all = np.array(centroid_rows) if centroid_rows else np.zeros((0, 5))

            save_result = save_run(
                run_id,
                {"points_all": points_all, "centroids_all": centroids_all},
                {
                    "tool": "compute_settlement_clusters",
                    "periodos": list(periodos),
                    "radio": radio,
                    "radio_match": radio_match,
                    "eventos": eventos,
                    "columnas_points_all": ["idx_periodo", "x", "y", "cluster_local_id"],
                    "columnas_centroids_all": ["idx_periodo", "cx", "cy", "cluster_local_id", "n_puntos"],
                },
            )
            result["run_id"] = save_result.get("run_id")
            result["trajectory_saved"] = "error" not in save_result

        return result

    return {"error": f"modo desconocido: {mode!r} (validos: analyze, validate)"}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_settlement_clusters(mode="validate"), indent=2, ensure_ascii=False))
