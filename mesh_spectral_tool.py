#!/usr/bin/env python3
"""
mesh_spectral_tool.py

Espectro de Laplace-Beltrami para mallas triangulares 3D. El Laplaciano
discreto de una malla (matriz de pesos cotangente + matriz de masa por
area de Voronoi) tiene un espectro de autovalores que actua como
"huella dactilar" de la forma: es invariante ante rotacion, traslacion,
y (aproximadamente) ante deformaciones isometricas.

Modos:
  - "spectrum": calcula los primeros k autovalores/autovectores del
    problema generalizado L v = lambda M v para una malla dada.
  - "compare": calcula el espectro de dos mallas y una distancia entre
    firmas espectrales (comparacion de forma).
  - "laplacian_info": devuelve propiedades basicas de la matriz
    Laplaciana (dimension, dispersion, simetria) sin resolver
    autovalores, util para chequear una malla antes de un calculo caro.

Input de malla: vertices como lista de [x,y,z], faces como lista de
[i,j,k] (indices 0-based de vertices que forman cada triangulo).

Depende de numpy y scipy (scipy.sparse + scipy.sparse.linalg.eigsh),
ambos ya presentes en el entorno (scipy 1.18.0 confirmado).

Corre standalone: python3 mesh_spectral_tool.py
"""

import json
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import eigsh


# ---------------------------------------------------------------------------
# Construccion del Laplaciano discreto (cotangente + masa de Voronoi)
# ---------------------------------------------------------------------------

def _triangle_angles(v0, v1, v2):
    """Angulos interiores del triangulo (v0,v1,v2), en radianes."""
    def angle(a, b, c):
        # angulo en el vertice a, entre los lados a->b y a->c
        u = b - a
        w = c - a
        cos_t = np.dot(u, w) / (np.linalg.norm(u) * np.linalg.norm(w) + 1e-15)
        cos_t = np.clip(cos_t, -1.0, 1.0)
        return np.arccos(cos_t)
    return angle(v0, v1, v2), angle(v1, v2, v0), angle(v2, v0, v1)


def build_cotangent_laplacian(vertices, faces):
    """
    Construye L (cotangente, semidefinida negativa por convencion de signo
    estandar: L = D - W) y M (masa diagonal, area de Voronoi/3 por vertice)
    para el problema generalizado de autovalores L v = lambda M v.

    vertices: (N,3) ndarray
    faces: (F,3) ndarray de indices enteros
    Devuelve: L (csr sparse, NxN), M (dia sparse, NxN), n_degenerate (int)
    """
    n = vertices.shape[0]
    W = sparse.lil_matrix((n, n))
    vertex_area = np.zeros(n)
    n_degenerate = 0

    for tri in faces:
        i, j, k = int(tri[0]), int(tri[1]), int(tri[2])
        vi, vj, vk = vertices[i], vertices[j], vertices[k]

        area = 0.5 * np.linalg.norm(np.cross(vj - vi, vk - vi))
        if area < 1e-12:
            n_degenerate += 1
            continue

        ang_i, ang_j, ang_k = _triangle_angles(vi, vj, vk)

        # peso cotangente del lado opuesto a cada angulo
        cot_i = 1.0 / np.tan(ang_i) if np.tan(ang_i) != 0 else 0.0
        cot_j = 1.0 / np.tan(ang_j) if np.tan(ang_j) != 0 else 0.0
        cot_k = 1.0 / np.tan(ang_k) if np.tan(ang_k) != 0 else 0.0

        # lado j-k opuesto a i, lado i-k opuesto a j, lado i-j opuesto a k
        W[j, k] += 0.5 * cot_i
        W[k, j] += 0.5 * cot_i
        W[i, k] += 0.5 * cot_j
        W[k, i] += 0.5 * cot_j
        W[i, j] += 0.5 * cot_k
        W[j, i] += 0.5 * cot_k

        # masa de Voronoi aproximada: area del triangulo / 3 por vertice
        vertex_area[i] += area / 3.0
        vertex_area[j] += area / 3.0
        vertex_area[k] += area / 3.0

    W = W.tocsr()
    D = sparse.diags(np.asarray(W.sum(axis=1)).flatten())
    L = D - W

    # evitar masa cero en vertices aislados (division por cero en generalized eig)
    safe_area = np.where(vertex_area > 1e-12, vertex_area, 1e-12)
    M = sparse.diags(safe_area)

    return L.tocsr(), M.tocsr(), n_degenerate


def build_uniform_laplacian(vertices, faces):
    """
    Fallback: Laplaciano combinatorio uniforme (sin pesos geometricos),
    para mallas con demasiados triangulos degenerados para el metodo
    cotangente. Menos preciso geometricamente pero siempre bien definido.
    """
    n = vertices.shape[0]
    W = sparse.lil_matrix((n, n))
    for tri in faces:
        i, j, k = int(tri[0]), int(tri[1]), int(tri[2])
        for a, b in [(i, j), (j, k), (k, i)]:
            W[a, b] = 1.0
            W[b, a] = 1.0
    W = W.tocsr()
    deg = np.asarray(W.sum(axis=1)).flatten()
    D = sparse.diags(deg)
    L = D - W
    M = sparse.identity(n, format="csr")
    return L.tocsr(), M, 0


# ---------------------------------------------------------------------------
# Calculo de espectro
# ---------------------------------------------------------------------------

def compute_spectrum(vertices, faces, k=20, method="cotangent"):
    vertices = np.asarray(vertices, dtype=float)
    faces = np.asarray(faces, dtype=int)

    if vertices.shape[0] < k + 1:
        k = max(1, vertices.shape[0] - 1)

    degenerate_fallback = False
    if method == "cotangent":
        L, M, n_deg = build_cotangent_laplacian(vertices, faces)
        # si mas del 10% de las caras son degeneradas, el cotangente
        # no es confiable: caemos a uniforme
        if n_deg > 0.1 * len(faces):
            L, M, n_deg = build_uniform_laplacian(vertices, faces)
            degenerate_fallback = True
    else:
        L, M, n_deg = build_uniform_laplacian(vertices, faces)

    # problema generalizado L v = lambda M v, buscamos los k autovalores
    # mas pequenos (los que llevan la info de forma de baja frecuencia;
    # el autovalor 0 corresponde a la componente constante y se descarta)
    n = vertices.shape[0]
    k_eff = min(k + 1, n - 1)
    try:
        eigvals, eigvecs = eigsh(L, k=k_eff, M=M, sigma=0, which="LM")
    except Exception:
        # sigma=0 (shift-invert) puede fallar si L es singular en forma
        # degenerada; reintentamos sin shift-invert
        eigvals, eigvecs = eigsh(L, k=k_eff, M=M, which="SM")

    order = np.argsort(eigvals)
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]

    # descartar el primer autovalor (~0, modo constante) si esta presente
    if eigvals[0] < 1e-8:
        eigvals = eigvals[1:]
        eigvecs = eigvecs[:, 1:]

    return {
        "eigenvalues": [round(float(v), 8) for v in eigvals],
        "n_vertices": int(n),
        "n_faces": int(len(faces)),
        "method_used": "uniform_fallback" if degenerate_fallback else method,
        "n_degenerate_faces": int(n_deg),
        "note": "Autovalor ~0 (modo constante) descartado del espectro reportado.",
    }


def compare_spectra(spec_a, spec_b):
    """Distancia L2 normalizada entre dos firmas espectrales de distinta
    longitud (se compara hasta min(len_a, len_b) autovalores)."""
    a = np.array(spec_a, dtype=float)
    b = np.array(spec_b, dtype=float)
    k = min(len(a), len(b))
    a, b = a[:k], b[:k]
    # normalizamos cada espectro por su propio segundo autovalor (el
    # primero no-trivial) para hacer la comparacion invariante a escala
    scale_a = a[0] if a[0] > 1e-12 else 1.0
    scale_b = b[0] if b[0] > 1e-12 else 1.0
    a_norm = a / scale_a
    b_norm = b / scale_b
    dist = float(np.linalg.norm(a_norm - b_norm) / np.sqrt(k))
    return {
        "n_compared": int(k),
        "spectral_distance": round(dist, 6),
        "interpretation": (
            "Distancia normalizada; valores cercanos a 0 sugieren formas "
            "similares (incluyendo deformaciones isometricas). No es una "
            "metrica formal de distancia entre superficies, solo una "
            "heuristica basada en las primeras frecuencias."
        ),
    }


# ---------------------------------------------------------------------------
# Dispatcher unico (misma convencion que el resto de octave-mcp)
# ---------------------------------------------------------------------------

def compute_mesh_spectral_tool(mode, **kwargs):
    if mode == "spectrum":
        vertices = kwargs["vertices"]
        faces = kwargs["faces"]
        k = kwargs.get("k", 20)
        method = kwargs.get("method", "cotangent")
        return {"mode": mode, **compute_spectrum(vertices, faces, k=k, method=method)}

    elif mode == "compare":
        mesh_a = kwargs["mesh_a"]  # {"vertices":..., "faces":...}
        mesh_b = kwargs["mesh_b"]
        k = kwargs.get("k", 20)
        method = kwargs.get("method", "cotangent")
        spec_a = compute_spectrum(mesh_a["vertices"], mesh_a["faces"], k=k, method=method)
        spec_b = compute_spectrum(mesh_b["vertices"], mesh_b["faces"], k=k, method=method)
        comparison = compare_spectra(spec_a["eigenvalues"], spec_b["eigenvalues"])
        return {
            "mode": mode,
            "mesh_a": spec_a,
            "mesh_b": spec_b,
            "comparison": comparison,
        }

    elif mode == "laplacian_info":
        vertices = np.asarray(kwargs["vertices"], dtype=float)
        faces = np.asarray(kwargs["faces"], dtype=int)
        method = kwargs.get("method", "cotangent")
        if method == "cotangent":
            L, M, n_deg = build_cotangent_laplacian(vertices, faces)
        else:
            L, M, n_deg = build_uniform_laplacian(vertices, faces)
        return {
            "mode": mode,
            "n_vertices": int(vertices.shape[0]),
            "n_faces": int(len(faces)),
            "n_degenerate_faces": int(n_deg),
            "laplacian_nnz": int(L.nnz),
            "laplacian_symmetric": bool(np.allclose((L - L.T).toarray(), 0, atol=1e-8))
            if vertices.shape[0] <= 500 else None,
            "note": "laplacian_symmetric se omite (None) para mallas grandes (>500 vertices) por costo de toarray().",
        }

    else:
        raise ValueError(f"mesh_spectral_tool: mode desconocido '{mode}'. "
                          f"Modos validos: spectrum, compare, laplacian_info")


MESH_SPECTRAL_TOOL_SCHEMA = {
    "name": "mesh_spectral_tool",
    "description": (
        "Espectro de Laplace-Beltrami de mallas triangulares 3D (huella "
        "dactilar espectral de la forma). Modos: 'spectrum' (autovalores/"
        "autovectores de una malla), 'compare' (distancia espectral entre "
        "dos mallas), 'laplacian_info' (propiedades de la matriz sin "
        "resolver autovalores, mas barato)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["spectrum", "compare", "laplacian_info"],
            },
            "vertices": {
                "type": "array",
                "description": "Lista de [x,y,z] (usado en modo spectrum/laplacian_info).",
            },
            "faces": {
                "type": "array",
                "description": "Lista de [i,j,k] indices 0-based (usado en modo spectrum/laplacian_info).",
            },
            "mesh_a": {
                "type": "object",
                "description": "{'vertices':[[x,y,z],...], 'faces':[[i,j,k],...]} (usado en modo compare).",
            },
            "mesh_b": {
                "type": "object",
                "description": "Igual formato que mesh_a (usado en modo compare).",
            },
            "k": {
                "type": "integer",
                "description": "Numero de autovalores a calcular (default 20).",
            },
            "method": {
                "type": "string",
                "enum": ["cotangent", "uniform"],
                "description": "Metodo de construccion del Laplaciano (default cotangent).",
            },
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    # Test rapido: espectro de un tetraedro regular
    verts = [
        [1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1],
    ]
    faces = [
        [0, 1, 2], [0, 3, 1], [0, 2, 3], [1, 3, 2],
    ]
    print(json.dumps(compute_mesh_spectral_tool("spectrum", vertices=verts, faces=faces, k=3), indent=2))
    print(json.dumps(compute_mesh_spectral_tool("laplacian_info", vertices=verts, faces=faces), indent=2))
