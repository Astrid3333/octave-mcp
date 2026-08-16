"""
socket_topology_tool.py

Optimizacion topologica (metodo SIMP, plane stress, elementos Q4) aplicada
al diseno de la pared de un socket protesico, en dominio 2D "desenrollado"
(ancho x alto = circunferencia parcial x altura del socket).

Implementacion basada en el algoritmo clasico de 88 lineas de Andreassen,
Clausen, Schevenels, Lazarov & Sigmund (2011), "Efficient topology
optimization in MATLAB using 88 lines of code", adaptado con condiciones
de borde propias de socket en vez del voladizo generico de la version
original:

  - Borde SUPERIOR (fila y=0, todos los nodos): empotrado completo (ambos
    grados de libertad). Representa la linea de corte proximal, donde el
    socket se fija rigidamente al adaptador/pilon.
  - Borde INFERIOR (fila y=nely, banda central de ancho load_fraction):
    carga vertical distribuida hacia abajo. Representa la zona de carga
    anatomica (ej. tendon rotuliano en trans-tibial) donde el muñon
    transmite la mayor parte de la fuerza de apoyo al socket.

mode="validate": corre una optimizacion en una malla chica y compara la
compliance optimizada contra la compliance de una densidad uniforme al
mismo volumen (la optimizada debe ser estrictamente menor, ya que SIMP
minimiza compliance sujeto a la misma restriccion de volumen: es una
condicion necesaria, no un valor cerrado, pero es una prueba dura -- si
el solver FEM o el update OC estan mal, la comparacion falla o se
invierte), mas un chequeo de que el volumen final respeta la restriccion
dentro de tolerancia.

mode="optimize": corre la optimizacion completa con los parametros dados
y devuelve el campo de densidades final, historial de compliance y
volumen alcanzado.
"""

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve
import tool_registry

E0 = 1.0
EMIN = 1e-9
NU = 0.3


def _lk():
    """Matriz de rigidez local (Q4, plane stress, E=1, nu=NU) -- formula
    cerrada estandar del algoritmo de 88 lineas."""
    nu = NU
    k = np.array([
        1 / 2 - nu / 6, 1 / 8 + nu / 8, -1 / 4 - nu / 12, -1 / 8 + 3 * nu / 8,
        -1 / 4 + nu / 12, -1 / 8 - nu / 8, nu / 6, 1 / 8 - 3 * nu / 8,
    ])
    KE = 1 / (1 - nu ** 2) * np.array([
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
    edofMat = np.zeros((nelx * nely, 8), dtype=int)
    for elx in range(nelx):
        for ely in range(nely):
            el = ely + elx * nely
            n1 = (nely + 1) * elx + ely
            n2 = (nely + 1) * (elx + 1) + ely
            edofMat[el, :] = [2 * n1 + 2, 2 * n1 + 3, 2 * n2 + 2, 2 * n2 + 3,
                              2 * n2, 2 * n2 + 1, 2 * n1, 2 * n1 + 1]
    return edofMat


def _build_filter(nelx, nely, rmin):
    """Filtro de densidad estandar (convolucion con radio rmin) en formato
    disperso, devuelve H y su suma por fila Hs para normalizar."""
    nfilter = int(nelx * nely * ((2 * (np.ceil(rmin) - 1) + 1) ** 2))
    iH = np.zeros(nfilter, dtype=int)
    jH = np.zeros(nfilter, dtype=int)
    sH = np.zeros(nfilter)
    cc = 0
    for i in range(nelx):
        for j in range(nely):
            row = i * nely + j
            kk1 = int(max(i - (np.ceil(rmin) - 1), 0))
            kk2 = int(min(i + np.ceil(rmin), nelx))
            ll1 = int(max(j - (np.ceil(rmin) - 1), 0))
            ll2 = int(min(j + np.ceil(rmin), nely))
            for k in range(kk1, kk2):
                for l in range(ll1, ll2):
                    col = k * nely + l
                    fac = rmin - np.sqrt((i - k) ** 2 + (j - l) ** 2)
                    if fac > 0:
                        iH[cc] = row
                        jH[cc] = col
                        sH[cc] = fac
                        cc += 1
    H = coo_matrix((sH[:cc], (iH[:cc], jH[:cc])), shape=(nelx * nely, nelx * nely)).tocsr()
    Hs = np.asarray(H.sum(axis=1)).flatten()
    return H, Hs


def _socket_bc(nelx, nely, load_fraction=0.4, total_load=-1.0):
    """Condiciones de borde de socket: empotrado en borde superior (linea
    de corte), carga vertical distribuida en banda central del borde
    inferior (zona de carga anatomica)."""
    ndof = 2 * (nelx + 1) * (nely + 1)
    f = np.zeros(ndof)

    fixed = []
    for elx in range(nelx + 1):
        n = (nely + 1) * elx + 0  # nodo de la fila superior (ely=0) en esta columna
        fixed += [2 * n, 2 * n + 1]
    fixeddofs = np.array(sorted(set(fixed)))

    ncols = nelx + 1
    center = ncols // 2
    half_band = max(1, int(round(load_fraction * ncols / 2)))
    cols = list(range(max(0, center - half_band), min(ncols, center + half_band) + 1))
    load_per_node = total_load / len(cols)
    for elx in cols:
        n = (nely + 1) * elx + nely  # nodo de la fila inferior en esta columna
        f[2 * n + 1] += load_per_node

    alldofs = np.arange(ndof)
    freedofs = np.setdiff1d(alldofs, fixeddofs)
    return f, fixeddofs, freedofs, ndof


def _fe_solve(nelx, nely, x, penal, edofMat, KE, f, fixeddofs, freedofs, ndof):
    iK = np.kron(edofMat, np.ones((8, 1))).flatten()
    jK = np.kron(edofMat, np.ones((1, 8))).flatten()
    sK = ((KE.flatten()[np.newaxis]).T * (EMIN + x ** penal * (E0 - EMIN))).flatten(order="F")
    K = coo_matrix((sK, (iK, jK)), shape=(ndof, ndof)).tocsc()
    K = K[freedofs, :][:, freedofs]
    u = np.zeros(ndof)
    u[freedofs] = spsolve(K, f[freedofs])
    return u


def run_socket_topology_optimization(nelx=60, nely=40, volfrac=0.4, penal=3.0,
                                      rmin=1.8, load_fraction=0.4, total_load=-1.0,
                                      max_iter=80, move=0.2, tol=1e-3):
    KE = _lk()
    edofMat = _dof_map(nelx, nely)
    H, Hs = _build_filter(nelx, nely, rmin)
    f, fixeddofs, freedofs, ndof = _socket_bc(nelx, nely, load_fraction, total_load)

    x = np.full(nelx * nely, volfrac)
    xPhys = x.copy()
    compliance_history = []

    for it in range(max_iter):
        u = _fe_solve(nelx, nely, xPhys, penal, edofMat, KE, f, fixeddofs, freedofs, ndof)
        ce = (np.dot(u[edofMat], KE) * u[edofMat]).sum(1)
        c = ((EMIN + xPhys ** penal * (E0 - EMIN)) * ce).sum()
        compliance_history.append(float(c))

        dc = -penal * (E0 - EMIN) * xPhys ** (penal - 1) * ce
        dv = np.ones(nelx * nely)
        dc = np.asarray(H @ (x * dc) / Hs / np.maximum(x, 1e-3))
        dv = np.asarray(H @ (dv / Hs))

        l1, l2 = 0.0, 1e9
        while (l2 - l1) / (l1 + l2) > 1e-3:
            lmid = 0.5 * (l1 + l2)
            xnew = np.maximum(0.0, np.maximum(x - move,
                    np.minimum(1.0, np.minimum(x + move, x * np.sqrt(-dc / dv / lmid)))))
            xPhys = np.asarray(H @ xnew) / Hs
            if xPhys.sum() > volfrac * nelx * nely:
                l1 = lmid
            else:
                l2 = lmid
        change = float(np.max(np.abs(xnew - x)))
        x = xnew
        if change < tol:
            break

    return {
        "density": x.reshape(nelx, nely).T.tolist(),
        "compliance_final": compliance_history[-1],
        "compliance_history": compliance_history,
        "n_iterations": len(compliance_history),
        "volume_fraction_achieved": float(xPhys.sum() / (nelx * nely)),
        "volume_fraction_target": volfrac,
    }


def _uniform_density_compliance(nelx, nely, volfrac, load_fraction=0.4, total_load=-1.0):
    """Compliance de referencia con densidad uniforme = volfrac en todo el
    dominio (sin optimizar), mismas condiciones de borde de socket."""
    KE = _lk()
    edofMat = _dof_map(nelx, nely)
    f, fixeddofs, freedofs, ndof = _socket_bc(nelx, nely, load_fraction, total_load)
    x = np.full(nelx * nely, volfrac)
    u = _fe_solve(nelx, nely, x, 3.0, edofMat, KE, f, fixeddofs, freedofs, ndof)
    ce = (np.dot(u[edofMat], KE) * u[edofMat]).sum(1)
    c = ((EMIN + x ** 3.0 * (E0 - EMIN)) * ce).sum()
    return float(c)


def validate():
    nelx, nely, volfrac = 24, 16, 0.4
    opt = run_socket_topology_optimization(nelx=nelx, nely=nely, volfrac=volfrac,
                                            penal=3.0, rmin=1.5, max_iter=60)
    uniform_c = _uniform_density_compliance(nelx, nely, volfrac)

    optimized_better = opt["compliance_final"] < uniform_c
    vol_err = abs(opt["volume_fraction_achieved"] - volfrac)
    vol_ok = vol_err < 0.02
    compliance_decreased = opt["compliance_history"][-1] < opt["compliance_history"][0]

    checks = [
        {
            "name": "optimized_compliance_lower_than_uniform_density",
            "compliance_uniform": round(uniform_c, 6),
            "compliance_optimized": round(opt["compliance_final"], 6),
            "reduction_pct": round((1 - opt["compliance_final"] / uniform_c) * 100, 2),
            "passed": bool(optimized_better),
        },
        {
            "name": "volume_fraction_within_tolerance",
            "target": volfrac,
            "achieved": round(opt["volume_fraction_achieved"], 4),
            "error": round(vol_err, 4),
            "passed": bool(vol_ok),
        },
        {
            "name": "compliance_decreased_over_iterations",
            "compliance_first_iter": round(opt["compliance_history"][0], 6),
            "compliance_last_iter": round(opt["compliance_history"][-1], 6),
            "n_iterations": opt["n_iterations"],
            "passed": bool(compliance_decreased),
        },
    ]
    return {
        "mode": "validate",
        "checks": checks,
        "validation_passed": all(c["passed"] for c in checks),
    }


def compute_socket_topology(mode="validate", **kwargs):
    if mode == "validate":
        return validate()
    elif mode == "optimize":
        return {"mode": "optimize", **run_socket_topology_optimization(**kwargs)}
    else:
        raise ValueError(f"mode desconocido: {mode}")


SOCKET_TOPOLOGY_TOOL_SCHEMA = {
    "name": "socket_topology_tool",
    "description": (
        "Optimizacion topologica SIMP (plane stress, elementos Q4, filtro de "
        "densidad, OC update) para la pared de un socket protesico en dominio "
        "2D desenrollado: empotrado en la linea de corte proximal (borde "
        "superior), carga distribuida en la zona de carga anatomica del borde "
        "distal (ej. tendon rotuliano). mode=validate compara compliance "
        "optimizada vs. densidad uniforme al mismo volumen y chequea la "
        "restriccion de volumen; mode=optimize corre la optimizacion completa."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["validate", "optimize"]},
            "nelx": {"type": "integer", "description": "elementos en el ancho del dominio"},
            "nely": {"type": "integer", "description": "elementos en el alto del dominio"},
            "volfrac": {"type": "number", "description": "fraccion de volumen objetivo (0-1)"},
            "penal": {"type": "number", "description": "exponente de penalizacion SIMP"},
            "rmin": {"type": "number", "description": "radio del filtro de densidad, en elementos"},
            "load_fraction": {"type": "number", "description": "ancho de la banda de carga como fraccion del ancho total"},
            "total_load": {"type": "number", "description": "carga vertical total distribuida (negativa = hacia abajo)"},
            "max_iter": {"type": "integer"},
            "move": {"type": "number", "description": "paso maximo de actualizacion de densidad por iteracion (OC)"},
            "tol": {"type": "number", "description": "tolerancia de convergencia (cambio maximo de densidad)"},
        },
        "required": ["mode"],
    },
}


def _handler(args):
    args = dict(args or {})
    mode = args.pop("mode", "validate")
    params = args.pop("params", None) or {}
    merged = {**params, **args}
    return compute_socket_topology(mode=mode, **merged)


tool_registry.register_tool("socket_topology_tool", SOCKET_TOPOLOGY_TOOL_SCHEMA, _handler)


if __name__ == "__main__":
    import json
    print(json.dumps(validate(), indent=2, ensure_ascii=False))
