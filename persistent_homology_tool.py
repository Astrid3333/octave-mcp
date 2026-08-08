"""
persistent_homology_tool.py

Homologia persistente sobre nubes de puntos via complejo de Vietoris-Rips
y el algoritmo estandar de reduccion de matriz de borde (Zomorodian-Carlsson /
Edelsbrunner-Harer), implementado en Python puro (Octave no tiene esto nativo).

Calcula H0 (componentes conexas) y H1 (lazos/agujeros de dimension 1) como
"barcodes": pares (nacimiento, muerte) en la escala de distancia epsilon.
Barras que nunca mueren (death=None) son clases "esenciales" -- topologia
que persiste hasta el final del rango de filtracion calculado.

Conexion directa con TritOS: el pipeline de deteccion de perturbaciones via
embedding de Takens + homologia persistente (H0, H1, caracteristica de Euler
chi(t)) que ya usas conceptualmente en el sistema LIG sobre madera de coigue
puede correr este mismo codigo sobre las nubes de puntos reconstruidas del
embedding, en vez de solo describirlo.

Prerrequisito: ninguno de Octave (Python puro), pero conceptualmente
complementa linear_algebra_tool (PCA se usa tipicamente para proyectar nubes
de puntos de alta dimension antes de la filtracion Vietoris-Rips).

Limitacion de escala: la complejidad es O(n^3) en el peor caso para
2-simplices (triangulos) y la reduccion de matriz. Para nubes de puntos
grandes (>150-200 puntos) hay que submuestrear (landmarks) antes de llamar
a este modulo -- no esta pensado para reemplazar herramientas dedicadas
como ripser/gudhi en produccion, sino para exploracion y validacion rapida
dentro del ecosistema MCP.
"""
import math
import itertools
import random
import numpy as np
from workspace_tool import save_run

PERSISTENT_HOMOLOGY_SCHEMA = {
    "name": "compute_persistent_homology",
    "description": (
        "Homologia persistente (H0, H1) sobre una nube de puntos via complejo "
        "de Vietoris-Rips y reduccion de matriz de borde. Presets sinteticos "
        "validados: 'circle' (un lazo H1 persistente con nacimiento/muerte "
        "analiticos conocidos), 'two_clusters' (dos componentes H0 esenciales, "
        "sin H1), 'random_noise' (baseline sin estructura topologica "
        "significativa). 'custom' via 'points' para datos reales -- por "
        "ejemplo nubes reconstruidas de un embedding de Takens."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "preset": {
                "type": "string",
                "enum": ["circle", "two_clusters", "random_noise", "custom"],
                "default": "circle",
            },
            "points": {"type": "array", "description": "Lista de puntos (cada uno una lista de coordenadas), solo si preset='custom'"},
            "max_edge_length": {"type": "number", "default": None, "description": "Umbral maximo de distancia para la filtracion. Si None, se calcula automaticamente"},
            "max_dim": {"type": "integer", "default": 2, "description": "Dimension maxima de simplices: 2 = puntos+aristas+triangulos (permite H0 y H1)"},
            "n_points": {"type": "integer", "default": 20, "description": "Para presets sinteticos"},
            "seed": {"type": "integer", "default": 1},
            "run_id": {"type": "string", "description": "Si se indica, guarda points/h0_diagram/h1_diagram en el workspace para graficar despues con plot_tool."},
        },
    },
}


def _dist(p, q):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p, q)))


def _build_filtration(points, max_edge_length, max_dim=2):
    n = len(points)
    simplices = [(0.0, 0, (i,)) for i in range(n)]
    dmat = [[_dist(points[i], points[j]) for j in range(n)] for i in range(n)]
    edge_set = set()
    for i in range(n):
        for j in range(i + 1, n):
            d = dmat[i][j]
            if d <= max_edge_length:
                simplices.append((d, 1, (i, j)))
                edge_set.add((i, j))
    if max_dim >= 2:
        for i, j, k in itertools.combinations(range(n), 3):
            if (i, j) in edge_set and (i, k) in edge_set and (j, k) in edge_set:
                birth = max(dmat[i][j], dmat[i][k], dmat[j][k])
                if birth <= max_edge_length:
                    simplices.append((birth, 2, (i, j, k)))
    return simplices


def _boundary_faces(simplex):
    if len(simplex) == 1:
        return []
    return [simplex[:idx] + simplex[idx + 1:] for idx in range(len(simplex))]


def _persistent_homology(points, max_edge_length, max_dim=2):
    simplices = _build_filtration(points, max_edge_length, max_dim)
    simplices.sort(key=lambda s: (s[0], s[1]))
    index_of = {s[2]: i for i, s in enumerate(simplices)}

    columns = []
    for _, _, simp in simplices:
        faces = _boundary_faces(simp)
        columns.append(set(index_of[tuple(f)] for f in faces))

    low = {}
    pairs = []
    n = len(columns)
    col_copy = [set(c) for c in columns]
    for j in range(n):
        while col_copy[j]:
            piv = max(col_copy[j])
            if piv in low:
                j2 = low[piv]
                col_copy[j] = col_copy[j].symmetric_difference(col_copy[j2])
            else:
                low[piv] = j
                pairs.append((piv, j))
                break

    paired = set(p[0] for p in pairs) | set(p[1] for p in pairs)
    essential = [i for i in range(n) if i not in paired]

    bars = []
    for birth_idx, death_idx in pairs:
        b_time, b_dim, _ = simplices[birth_idx]
        d_time, _, _ = simplices[death_idx]
        if d_time > b_time:
            bars.append({"dim": b_dim, "birth": round(b_time, 6), "death": round(d_time, 6),
                         "persistence": round(d_time - b_time, 6)})
    for idx in essential:
        b_time, b_dim, _ = simplices[idx]
        bars.append({"dim": b_dim, "birth": round(b_time, 6), "death": None, "persistence": None})

    return bars, len(simplices)


def _gen_circle(n_points):
    return [(math.cos(2 * math.pi * i / n_points), math.sin(2 * math.pi * i / n_points))
            for i in range(n_points)], {
        "nacimiento_H1_analitico": round(2 * math.sin(math.pi / n_points), 6),
        "nota": "el nacimiento del lazo H1 debe coincidir con la longitud de arista del poligono regular inscrito: 2*sin(pi/n_points)",
    }


def _gen_two_clusters(n_points, seed):
    rng = random.Random(seed)
    half = n_points // 2
    c1 = [(rng.gauss(0, 0.1), rng.gauss(0, 0.1)) for _ in range(half)]
    c2 = [(rng.gauss(5, 0.1), rng.gauss(5, 0.1)) for _ in range(n_points - half)]
    return c1 + c2, {"H0_esenciales_esperados": 2, "H1_esperado": "ninguno significativo"}


def _gen_random_noise(n_points, seed):
    rng = random.Random(seed)
    return [(rng.uniform(0, 3), rng.uniform(0, 3)) for _ in range(n_points)], {
        "nota": "sin estructura por construccion -- deberia dar barras H1 cortas/ruidosas si aparecen, no un lazo dominante",
    }


def compute_persistent_homology(preset="circle", points=None, max_edge_length=None,
                                 max_dim=2, n_points=20, seed=1, run_id=None):
    known = None

    if preset == "custom":
        if not points:
            return {"error": "preset='custom' requiere 'points'"}
        pts = [tuple(p) for p in points]
    elif preset == "circle":
        pts, known = _gen_circle(n_points)
    elif preset == "two_clusters":
        pts, known = _gen_two_clusters(n_points, seed)
    elif preset == "random_noise":
        pts, known = _gen_random_noise(n_points, seed)
    else:
        return {"error": f"preset desconocido: {preset}"}

    if len(pts) > 200:
        return {"error": f"n_points={len(pts)} excede el limite practico de 200 -- submuestrea antes de llamar (complejidad O(n^3))"}

    if max_edge_length is None:
        dists = [_dist(pts[i], pts[j]) for i in range(len(pts)) for j in range(i + 1, len(pts))]
        max_edge_length = max(dists) * 0.9 if dists else 1.0

    bars, n_simplices = _persistent_homology(pts, max_edge_length, max_dim)

    h0 = sorted([b for b in bars if b["dim"] == 0], key=lambda b: -(b["persistence"] or 1e18))
    h1 = sorted([b for b in bars if b["dim"] == 1], key=lambda b: -(b["persistence"] or 1e18))

    result = {
        "preset": preset,
        "n_points": len(pts),
        "n_simplices_in_filtration": n_simplices,
        "max_edge_length_used": round(max_edge_length, 6),
        "H0_barcode": h0,
        "H1_barcode": h1,
        "H0_essential_count": sum(1 for b in h0 if b["death"] is None),
        "H1_essential_count": sum(1 for b in h1 if b["death"] is None),
        "nota_metodologica": (
            "Barras 'esenciales' (death=None) significan que la clase topologica "
            "no muere dentro del rango de filtracion calculado -- si max_edge_length "
            "es muy chico, un lazo real (H1) puede aparecer como esencial sin serlo; "
            "conviene aumentar max_edge_length y confirmar que el nacimiento/muerte "
            "se estabiliza (no cambia al seguir aumentando el umbral) antes de "
            "interpretar una barra como topologia real vs. artefacto de corte."
        ),
    }
    if known:
        result["known_reference"] = known

    result["trajectory_saved"] = False
    result["run_id"] = None
    if run_id:
        def _to_diagram_array(barcode):
            if not barcode:
                return np.zeros((0, 2))
            return np.array([[b["birth"], b["death"] if b["death"] is not None else np.inf] for b in barcode])

        save_result = save_run(
            run_id,
            {
                "points": np.array(pts),
                "h0_diagram": _to_diagram_array(h0),
                "h1_diagram": _to_diagram_array(h1),
            },
            {
                "tool": "compute_persistent_homology",
                "preset": preset,
                "n_points": len(pts),
                "max_edge_length_used": round(max_edge_length, 6),
                "H0_essential_count": result["H0_essential_count"],
                "H1_essential_count": result["H1_essential_count"],
            },
        )
        result["run_id"] = save_result.get("run_id")
        result["trajectory_saved"] = "error" not in save_result

    return result


if __name__ == "__main__":
    import json
    print(json.dumps(compute_persistent_homology("circle", n_points=20, max_edge_length=2.5), indent=2, ensure_ascii=False))
    print(json.dumps(compute_persistent_homology("two_clusters", n_points=20, max_edge_length=1.0), indent=2, ensure_ascii=False))
