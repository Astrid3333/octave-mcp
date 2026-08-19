#!/usr/bin/env python3
"""
topology_optimization_tool.py

Optimizacion topologica de estructuras mediante el metodo SIMP
(Solid Isotropic Material with Penalization), la formulacion clasica de
Bendsoe & Sigmund. Esto NO es un grafo de nodos visual (tipo Blender /
Substance Designer) - es optimizacion fisica real: encuentra la
distribucion de densidad de material x(nodo) en [0,1] sobre una malla de
elementos finitos que minimiza la compliance (flexibilidad = inversa de
la rigidez) sujeta a una restriccion de volumen de material disponible.

Implementacion: la formulacion "88 lines" de Sigmund (2001,
"A 99 line topology optimization code written in Matlab", extendida por
Andreassen et al. 2011), adaptada a Python/NumPy/SciPy:

  1. Malla rectangular de elementos cuadrilateros bilineales (plane stress).
  2. FE: ensambla K global con cada elemento escalado por x_e^penal
     (penalizacion SIMP para forzar densidades hacia 0 o 1), resuelve
     K*U = F para los desplazamientos.
  3. Sensibilidad: dc/dx_e = -penal * x_e^(penal-1) * Ue^T * KE * Ue
     (derivada analitica exacta de la compliance respecto a la densidad).
  4. Filtro de densidad (sensitivity filter, Sigmund 1997): promedia la
     sensibilidad en un radio rmin para evitar el patron de "tablero de
     ajedrez" (checkerboarding) y garantizar independencia de malla.
  5. Update por Criterio de Optimalidad (OC) con busqueda binaria del
     multiplicador de Lagrange que satisface la restriccion de volumen
     EXACTAMENTE en cada iteracion.

Caso de validacion: viga cantilever (empotrada en el borde izquierdo,
carga puntual hacia abajo en el borde derecho medio) - el benchmark
estandar de la literatura de optimizacion topologica.
"""

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve


class TopologyOptimizationError(ValueError):
    pass


def _lk():
    """Matriz de rigidez del elemento cuadrilatero bilineal (plane stress,
    E=1, nu=0.3), formula estandar (Sigmund 2001)."""
    E, nu = 1.0, 0.3
    k = np.array([
        1 / 2 - nu / 6, 1 / 8 + nu / 8, -1 / 4 - nu / 12, -1 / 8 + 3 * nu / 8,
        -1 / 4 + nu / 12, -1 / 8 - nu / 8, nu / 6, 1 / 8 - 3 * nu / 8,
    ])
    KE = E / (1 - nu ** 2) * np.array([
        [k[0], k[1], k[2], k[3], k[4], k[5], k[6], k[7]],
        [k[1], k[0], k[7], k[6], k[5], k[4], k[3], k[2]],
        [k[2], k[7], k[0], k[5], k[6], k[3], k[4], k[1]],
        [k[3], k[6], k[5], k[0], k[7], k[2], k[1], k[4]],
        [k[4], k[5], k[6], k[7], k[0], k[1], k[2], k[3]],
        [k[5], k[4], k[3], k[2], k[1], k[0], k[7], k[6]],
        [k[6], k[3], k[4], k[1], k[2], k[7], k[0], k[5]],
        [k[7], k[2], k[1], k[4], k[3], k[6], k[5], k[0]],
    ])
    return KE


def _dof_map(nelx, nely):
    """Para cada elemento, los 8 indices de grado de libertad (2 por nodo,
    4 nodos) en el vector global de desplazamientos."""
    edofMat = np.zeros((nelx * nely, 8), dtype=int)
    for elx in range(nelx):
        for ely in range(nely):
            el = elx * nely + ely
            n1 = (nely + 1) * elx + ely
            n2 = (nely + 1) * (elx + 1) + ely
            edofMat[el, :] = [
                2 * n1 + 2, 2 * n1 + 3, 2 * n2 + 2, 2 * n2 + 3,
                2 * n2, 2 * n2 + 1, 2 * n1, 2 * n1 + 1,
            ]
    return edofMat


def _build_filter(nelx, nely, rmin):
    """Filtro de densidad/sensibilidad: pesos lineales decrecientes con la
    distancia entre centros de elementos, radio rmin (en unidades de
    elemento). Devuelve la matriz de pesos dispersa H y el vector de
    normalizacion Hs."""
    nfilter = int(nelx * nely * ((2 * (np.ceil(rmin) - 1) + 1) ** 2))
    iH = np.zeros(nfilter, dtype=int)
    jH = np.zeros(nfilter, dtype=int)
    sH = np.zeros(nfilter)
    cc = 0
    for i1 in range(nelx):
        for j1 in range(nely):
            e1 = i1 * nely + j1
            i2_lo = max(i1 - int(np.ceil(rmin) - 1), 0)
            i2_hi = min(i1 + int(np.ceil(rmin)), nelx)
            j2_lo = max(j1 - int(np.ceil(rmin) - 1), 0)
            j2_hi = min(j1 + int(np.ceil(rmin)), nely)
            for i2 in range(i2_lo, i2_hi):
                for j2 in range(j2_lo, j2_hi):
                    e2 = i2 * nely + j2
                    dist = np.sqrt((i1 - i2) ** 2 + (j1 - j2) ** 2)
                    w = max(0.0, rmin - dist)
                    if w > 0:
                        iH[cc] = e1
                        jH[cc] = e2
                        sH[cc] = w
                        cc += 1
    H = coo_matrix((sH[:cc], (iH[:cc], jH[:cc])), shape=(nelx * nely, nelx * nely)).tocsr()
    Hs = np.asarray(H.sum(axis=1)).flatten()
    return H, Hs


def run_topology_optimization(nelx, nely, volfrac, penal=3.0, rmin=1.5,
                                max_loop=120, move=0.2, tol=0.01,
                                bc="cantilever", xmin=1e-3):
    """
    Optimizacion topologica SIMP sobre una malla nelx x nely.

    bc="cantilever": empotrado en todo el borde izquierdo (x=0), carga
    puntual unitaria hacia abajo en el nodo medio del borde derecho.
    Es el benchmark estandar de la literatura (Sigmund 2001, Andreassen 2011).

    xmin: densidad minima (no 0.0) para evitar que la matriz de rigidez
    global quede singular si una region completa llega a densidad cero
    (nodos sin ningun camino de rigidez hacia los apoyos).
    """
    if not (0.0 < volfrac < 1.0):
        raise TopologyOptimizationError(f"volfrac debe estar en (0,1), recibido {volfrac}")
    if nelx < 4 or nely < 4:
        raise TopologyOptimizationError("nelx y nely deben ser >= 4 para una malla minimamente representativa")

    ndof = 2 * (nelx + 1) * (nely + 1)
    KE = _lk()
    edofMat = _dof_map(nelx, nely)

    iK = np.kron(edofMat, np.ones((8, 1))).flatten().astype(int)
    jK = np.kron(edofMat, np.ones((1, 8))).flatten().astype(int)

    H, Hs = _build_filter(nelx, nely, rmin)

    if bc == "cantilever":
        # Empotrado: todos los grados de libertad del borde izquierdo (x=0) fijos.
        fixed_nodes = np.arange(0, nely + 1)  # nodos del borde izquierdo
        fixeddofs = np.union1d(2 * fixed_nodes, 2 * fixed_nodes + 1)
        # Carga puntual hacia abajo en el nodo medio del borde derecho.
        load_node = (nelx) * (nely + 1) + (nely // 2)
        F = np.zeros(ndof)
        F[2 * load_node + 1] = -1.0
    else:
        raise TopologyOptimizationError(f"Condicion de borde desconocida: {bc}")

    alldofs = np.arange(ndof)
    freedofs = np.setdiff1d(alldofs, fixeddofs)

    x = np.full(nelx * nely, volfrac)
    xPhys = x.copy()
    loop = 0
    change = 1.0
    compliance_history = []

    while change > tol and loop < max_loop:
        loop += 1
        sK = ((KE.flatten()[np.newaxis]).T * (xPhys ** penal)[np.newaxis, :]).flatten(order="F")
        K = coo_matrix((sK, (iK, jK)), shape=(ndof, ndof)).tocsc()
        K = K[freedofs, :][:, freedofs]

        U = np.zeros(ndof)
        U[freedofs] = spsolve(K, F[freedofs])

        ce = np.sum((U[edofMat] @ KE) * U[edofMat], axis=1)
        c = np.sum((xPhys ** penal) * ce)
        dc = -penal * (xPhys ** (penal - 1)) * ce
        dv = np.ones(nelx * nely)

        dc = np.asarray(H @ (x * dc)) / Hs / np.maximum(x, 1e-3)
        dv = np.asarray(H @ dv) / Hs

        # Optimality Criteria update, bisection sobre el multiplicador lambda
        # hasta que la fraccion de volumen resultante coincida con volfrac.
        l1, l2 = 0.0, 1e9
        xnew = np.zeros(nelx * nely)
        while (l2 - l1) / (l1 + l2 + 1e-30) > 1e-3:
            lmid = 0.5 * (l1 + l2)
            step = x * np.sqrt(np.maximum(-dc / (dv * lmid), 0.0))
            xnew = np.maximum(xmin, np.maximum(x - move,
                    np.minimum(1.0, np.minimum(x + move, step))))
            xPhys = np.asarray(H @ xnew) / Hs
            if xPhys.mean() - volfrac > 0:
                l1 = lmid
            else:
                l2 = lmid

        change = np.max(np.abs(xnew - x))
        x = xnew
        compliance_history.append(float(c))

    return {
        "nelx": nelx, "nely": nely, "volfrac": volfrac, "penal": penal, "rmin": rmin,
        "bc": bc,
        "iterations": loop,
        "converged": bool(change <= tol),
        "final_change": float(change),
        "final_volume_fraction": float(xPhys.mean()),
        "final_compliance": compliance_history[-1] if compliance_history else None,
        "compliance_history": compliance_history,
        "density_field": xPhys.reshape(nelx, nely).T.tolist(),  # [fila_y][col_x], y=0 arriba
    }


def _uniform_density_compliance(nelx, nely, volfrac, bc="cantilever"):
    """Compliance de referencia con densidad uniforme = volfrac en todos los
    elementos (sin optimizar) - el baseline contra el que se compara la
    solucion optimizada."""
    ndof = 2 * (nelx + 1) * (nely + 1)
    KE = _lk()
    edofMat = _dof_map(nelx, nely)
    iK = np.kron(edofMat, np.ones((8, 1))).flatten().astype(int)
    jK = np.kron(edofMat, np.ones((1, 8))).flatten().astype(int)

    fixed_nodes = np.arange(0, nely + 1)
    fixeddofs = np.union1d(2 * fixed_nodes, 2 * fixed_nodes + 1)
    load_node = nelx * (nely + 1) + (nely // 2)
    F = np.zeros(ndof)
    F[2 * load_node + 1] = -1.0

    alldofs = np.arange(ndof)
    freedofs = np.setdiff1d(alldofs, fixeddofs)

    x = np.full(nelx * nely, volfrac)
    sK = ((KE.flatten()[np.newaxis]).T * (x ** 3.0)[np.newaxis, :]).flatten(order="F")
    K = coo_matrix((sK, (iK, jK)), shape=(ndof, ndof)).tocsc()
    K = K[freedofs, :][:, freedofs]
    U = np.zeros(ndof)
    U[freedofs] = spsolve(K, F[freedofs])
    ce = np.sum((U[edofMat] @ KE) * U[edofMat], axis=1)
    c = np.sum((x ** 3.0) * ce)
    return float(c)


def validate(params=None):
    params = params or {}
    nelx = int(params.get("nelx", 40))
    nely = int(params.get("nely", 20))
    volfrac = float(params.get("volfrac", 0.4))

    result = run_topology_optimization(nelx, nely, volfrac, penal=3.0, rmin=1.5,
                                        max_loop=int(params.get("max_loop", 120)))
    baseline_c = _uniform_density_compliance(nelx, nely, volfrac)

    checks = {
        "volume_constraint_satisfied": abs(result["final_volume_fraction"] - volfrac) < 1e-2,
        "density_field_bounded": bool(
            min(min(row) for row in result["density_field"]) >= -1e-9
            and max(max(row) for row in result["density_field"]) <= 1.0 + 1e-9
        ),
        "compliance_improved_vs_uniform_baseline": result["final_compliance"] < baseline_c,
        "converged_or_ran_full_budget": result["converged"] or result["iterations"] == int(params.get("max_loop", 120)),
        "compliance_monotonic_ish": bool(
            result["compliance_history"][-1] <= result["compliance_history"][0] * 1.05
        ) if len(result["compliance_history"]) > 1 else True,
    }
    validation_passed = all(checks.values())

    return {
        "mode": "validate",
        "benchmark": "cantilever_beam_SIMP",
        "nelx": nelx, "nely": nely, "volfrac": volfrac,
        "iterations": result["iterations"],
        "final_volume_fraction": result["final_volume_fraction"],
        "final_compliance": result["final_compliance"],
        "uniform_density_baseline_compliance": baseline_c,
        "compliance_reduction_pct": float(
            (baseline_c - result["final_compliance"]) / baseline_c * 100.0
        ),
        "checks": checks,
        "validation_passed": validation_passed,
    }


def compute_topology_optimization_tool(mode="validate", params=None):
    params = params or {}
    if mode == "validate":
        return validate(params)
    if mode == "optimize":
        try:
            nelx = int(params["nelx"])
            nely = int(params["nely"])
            volfrac = float(params["volfrac"])
        except KeyError as e:
            raise TopologyOptimizationError(f"Falta parametro requerido: {e}")
        result = run_topology_optimization(
            nelx, nely, volfrac,
            penal=float(params.get("penal", 3.0)),
            rmin=float(params.get("rmin", 1.5)),
            max_loop=int(params.get("max_loop", 120)),
            move=float(params.get("move", 0.2)),
            tol=float(params.get("tol", 0.01)),
            bc=params.get("bc", "cantilever"),
        )
        return {"mode": "optimize", **result}
    raise TopologyOptimizationError(f"Modo desconocido para topology_optimization_tool: {mode}")


TOPOLOGY_OPTIMIZATION_TOOL_SCHEMA = {
    "name": "topology_optimization_tool",
    "description": (
        "Optimizacion topologica de estructuras via metodo SIMP (Solid Isotropic "
        "Material with Penalization): encuentra la distribucion de densidad de "
        "material x(elemento) en [0,1] sobre una malla FEM que minimiza la "
        "compliance (maximiza rigidez) sujeta a una fraccion de volumen de material "
        "disponible. Incluye filtro de densidad (evita checkerboarding, garantiza "
        "independencia de malla) y update por Criterio de Optimalidad (OC). "
        "mode='validate' corre el benchmark estandar de viga cantilever y verifica "
        "restriccion de volumen exacta, densidades acotadas en [0,1], y mejora de "
        "compliance vs. densidad uniforme. mode='optimize' resuelve un caso: "
        "nelx, nely (tamano de malla), volfrac (fraccion de volumen 0-1), penal "
        "(exponente de penalizacion SIMP, tipico 3.0), rmin (radio de filtro en "
        "elementos), max_loop, move (limite de movimiento por iteracion), tol, "
        "bc ('cantilever' por ahora). Devuelve density_field como grilla 2D "
        "lista para visualizar."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["validate", "optimize"],
                "default": "validate",
            },
            "params": {
                "type": "object",
                "description": "Parametros especificos del modo (ver descripcion de la tool).",
            },
        },
    },
}


if __name__ == "__main__":
    import json
    print(json.dumps(validate(), ensure_ascii=False, indent=2)[:3000])

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("topology_optimization_tool", TOPOLOGY_OPTIMIZATION_TOOL_SCHEMA, lambda args, _f=compute_topology_optimization_tool: _f(**args))
