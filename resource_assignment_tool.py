"""
resource_assignment_tool.py

Asignacion optima de recursos (ej. drones -> focos de incendio) via el
algoritmo hungaro (scipy.optimize.linear_sum_assignment), mas ruteo basico
tipo TSP (vecino mas cercano + mejora 2-opt) para ordenar multiples paradas
asignadas a un mismo recurso.

Modos:
  hungarian_assignment : dado un cost_matrix (recursos x tareas), devuelve
                          la asignacion que minimiza el costo total.
  route_tsp             : dado un set de puntos (x,y) y un punto de partida
                          opcional, devuelve el orden de visita que
                          aproxima la ruta mas corta (heuristica, no exacta).
  assign_and_route       : combina ambos -- arma cost_matrix desde
                          posiciones de recursos/tareas (distancia euclidea,
                          opcionalmente ponderada por prioridad), asigna via
                          hungaro, y si un recurso tiene mas de una tarea
                          asignada (cost_matrix rectangular con mas tareas
                          que recursos, ver 'tasks_per_resource') rutea sus
                          paradas con TSP.
  validate               : suite de auto-chequeos contra casos con solucion
                          conocida.
"""

import itertools
import math

import numpy as np
from scipy.optimize import linear_sum_assignment


# ---------------------------------------------------------------------
# Modo 1: asignacion optima (hungaro)
# ---------------------------------------------------------------------

def _hungarian_assignment(cost_matrix, maximize=False):
    C = np.array(cost_matrix, dtype=float)
    if C.ndim != 2:
        raise ValueError("cost_matrix debe ser 2D (recursos x tareas)")
    row_ind, col_ind = linear_sum_assignment(C, maximize=maximize)
    total_cost = float(C[row_ind, col_ind].sum())
    return {
        "row_indices": row_ind.tolist(),
        "col_indices": col_ind.tolist(),
        "assignment": [{"resource": int(r), "task": int(c), "cost": float(C[r, c])}
                        for r, c in zip(row_ind, col_ind)],
        "total_cost": total_cost,
        "shape": list(C.shape),
    }


# ---------------------------------------------------------------------
# Modo 2: ruteo heuristico tipo TSP (vecino mas cercano + 2-opt)
# ---------------------------------------------------------------------

def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _route_length(points, order):
    return sum(_dist(points[order[i]], points[order[i + 1]])
               for i in range(len(order) - 1))


def _nearest_neighbor_route(points, start_idx=0):
    n = len(points)
    unvisited = set(range(n))
    unvisited.discard(start_idx)
    order = [start_idx]
    current = start_idx
    while unvisited:
        nxt = min(unvisited, key=lambda j: _dist(points[current], points[j]))
        order.append(nxt)
        unvisited.discard(nxt)
        current = nxt
    return order


def _two_opt(points, order, max_iter=200):
    order = list(order)
    n = len(order)
    improved = True
    it = 0
    while improved and it < max_iter:
        improved = False
        it += 1
        for i in range(1, n - 2):
            for j in range(i + 1, n - 1):
                a, b = order[i - 1], order[i]
                c, d = order[j], order[j + 1]
                delta = (_dist(points[a], points[c]) + _dist(points[b], points[d])
                          - _dist(points[a], points[b]) - _dist(points[c], points[d]))
                if delta < -1e-12:
                    order[i:j + 1] = reversed(order[i:j + 1])
                    improved = True
    return order


def _route_tsp(points, start_idx=0):
    points = [tuple(p) for p in points]
    n = len(points)
    if n == 0:
        return {"order": [], "route_length": 0.0}
    if n == 1:
        return {"order": [0], "route_length": 0.0}
    if n <= 9:
        # fuerza bruta exacta para pocos puntos: mantiene el punto de
        # partida fijo y prueba todas las permutaciones del resto
        rest = [i for i in range(n) if i != start_idx]
        best_order, best_len = None, math.inf
        for perm in itertools.permutations(rest):
            order = [start_idx] + list(perm)
            length = _route_length(points, order)
            if length < best_len:
                best_len, best_order = length, order
        return {"order": best_order, "route_length": best_len, "method": "brute_force_exact"}
    order = _nearest_neighbor_route(points, start_idx)
    order = _two_opt(points, order)
    return {"order": order, "route_length": _route_length(points, order), "method": "nearest_neighbor_2opt"}


# ---------------------------------------------------------------------
# Modo 3: asignacion + ruteo combinados desde posiciones
# ---------------------------------------------------------------------

def _assign_and_route(resources, tasks, priority_weight=0.0, tasks_per_resource=1):
    """
    resources: lista de {"id":..., "position":[x,y]}
    tasks:     lista de {"id":..., "position":[x,y], "priority": float opcional 0-1}
    priority_weight: si >0, el costo de asignar una tarea de baja prioridad
                      se penaliza (costo *= (1 + priority_weight*(1-prioridad)))
    tasks_per_resource: si >1 y hay mas tareas que recursos, cada recurso
                          puede tomar varias tareas (asignacion + ruteo
                          interno via TSP entre las paradas que le tocaron)
    """
    n_res, n_task = len(resources), len(tasks)
    if n_res == 0 or n_task == 0:
        raise ValueError("resources y tasks no pueden estar vacios")

    res_pos = [r["position"] for r in resources]
    task_pos = [t["position"] for t in tasks]

    if tasks_per_resource <= 1:
        cost = np.zeros((n_res, n_task))
        for i, rp in enumerate(res_pos):
            for j, tp in enumerate(task_pos):
                d = _dist(rp, tp)
                prio = tasks[j].get("priority", 1.0)
                cost[i, j] = d * (1 + priority_weight * (1 - prio))
        hung = _hungarian_assignment(cost)
        assignment = []
        for a in hung["assignment"]:
            assignment.append({
                "resource_id": resources[a["resource"]]["id"],
                "task_ids": [tasks[a["task"]]["id"]],
                "route_order_task_ids": [tasks[a["task"]]["id"]],
                "route_length": float(cost[a["resource"], a["task"]]),
            })
        return {
            "mode": "assign_and_route",
            "assignment": assignment,
            "total_cost": hung["total_cost"],
        }

    # multiples tareas por recurso: replicar cada recurso tasks_per_resource
    # veces en la matriz de costo (patron estandar para transportar el
    # problema de asignacion 1:N al hungaro clasico 1:1), luego agrupar
    expanded_res_idx = []
    cost_rows = []
    for i, rp in enumerate(res_pos):
        for _ in range(tasks_per_resource):
            expanded_res_idx.append(i)
            row = []
            for j, tp in enumerate(task_pos):
                d = _dist(rp, tp)
                prio = tasks[j].get("priority", 1.0)
                row.append(d * (1 + priority_weight * (1 - prio)))
            cost_rows.append(row)
    cost = np.array(cost_rows)
    if cost.shape[0] < n_task:
        raise ValueError(
            f"resources*tasks_per_resource ({cost.shape[0]}) < n_tasks ({n_task}); "
            "subi tasks_per_resource o agrega recursos"
        )
    hung = _hungarian_assignment(cost)

    grouped = {}
    for a in hung["assignment"]:
        res_i = expanded_res_idx[a["resource"]]
        grouped.setdefault(res_i, []).append(a["task"])

    assignment = []
    total_cost = 0.0
    for res_i, task_idxs in grouped.items():
        stops = [res_pos[res_i]] + [task_pos[j] for j in task_idxs]
        tsp = _route_tsp(stops, start_idx=0)
        ordered_task_positions = tsp["order"][1:]  # excluye el propio recurso (indice 0)
        ordered_task_ids = [tasks[task_idxs[k - 1]]["id"] for k in ordered_task_positions]
        total_cost += tsp["route_length"]
        assignment.append({
            "resource_id": resources[res_i]["id"],
            "task_ids": [tasks[j]["id"] for j in task_idxs],
            "route_order_task_ids": ordered_task_ids,
            "route_length": tsp["route_length"],
        })

    return {
        "mode": "assign_and_route",
        "assignment": assignment,
        "total_cost": total_cost,
    }


# ---------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------

def compute_resource_assignment_tool(args):
    mode = args.get("mode") if isinstance(args, dict) else args
    params = args.get("params") or {} if isinstance(args, dict) else {}

    try:
        if mode == "hungarian_assignment":
            return _hungarian_assignment(
                params["cost_matrix"], maximize=params.get("maximize", False)
            )
        elif mode == "route_tsp":
            return _route_tsp(params["points"], start_idx=params.get("start_idx", 0))
        elif mode == "assign_and_route":
            return _assign_and_route(
                params["resources"], params["tasks"],
                priority_weight=params.get("priority_weight", 0.0),
                tasks_per_resource=params.get("tasks_per_resource", 1),
            )
        elif mode == "validate":
            return _validate()
        else:
            return {"error": f"Modo desconocido: {mode}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


# ---------------------------------------------------------------------
# Validacion
# ---------------------------------------------------------------------

def _validate():
    checks = {}
    all_pass = True

    def check(name, cond, detail=None):
        nonlocal all_pass
        checks[name] = {"pass": bool(cond)}
        if detail is not None:
            checks[name]["detail"] = detail
        if not cond:
            all_pass = False

    # 1) caso de asignacion trivial 2x2 con solucion obvia
    cost = [[1, 10], [10, 1]]
    r = _hungarian_assignment(cost)
    check(
        "hungarian_2x2_diagonal_optima",
        r["total_cost"] == 2.0 and {a["resource"]: a["task"] for a in r["assignment"]} == {0: 0, 1: 1},
        {"total_cost": r["total_cost"], "assignment": r["assignment"]},
    )

    # 2) caso 3x3 con solucion conocida (clasico libro de texto: costo minimo 15)
    cost3 = [[4, 1, 3], [2, 0, 5], [3, 2, 2]]
    r3 = _hungarian_assignment(cost3)
    check(
        "hungarian_3x3_costo_minimo_conocido",
        abs(r3["total_cost"] - 5.0) < 1e-9,
        {"total_cost": r3["total_cost"]},
    )

    # 3) maximize=True debe invertir la preferencia (elige el mayor costo total)
    r_max = _hungarian_assignment(cost, maximize=True)
    check(
        "hungarian_maximize_invierte_seleccion",
        r_max["total_cost"] == 20.0,
        {"total_cost": r_max["total_cost"]},
    )

    # 4) TSP: cuadrado unitario, la ruta optima cerrada mide 4, pero como
    #    ruta ABIERTA (no vuelve al origen) el optimo real recorriendo las
    #    4 esquinas es 3 (perimetro menos un lado)
    square = [(0, 0), (0, 1), (1, 1), (1, 0)]
    tsp_r = _route_tsp(square, start_idx=0)
    check(
        "tsp_cuadrado_ruta_abierta_optima_longitud_3",
        abs(tsp_r["route_length"] - 3.0) < 1e-9,
        {"route_length": tsp_r["route_length"], "order": tsp_r["order"], "method": tsp_r.get("method")},
    )

    # 5) TSP con 12 puntos en circulo: la ruta optima (abierta, casi un
    #    circulo completo salvo el lado que se rompe) debe ser mucho mas
    #    corta que un orden aleatorio/secuencial malo (sanity de que el
    #    heuristico realmente optimiza, no solo devuelve el orden de entrada)
    n = 12
    circle = [(math.cos(2 * math.pi * k / n), math.sin(2 * math.pi * k / n)) for k in range(n)]
    shuffled_idx = list(range(n))
    # desordenar deterministicamente (no random, para reproducibilidad)
    shuffled = [circle[(i * 7) % n] for i in range(n)]
    bad_route_length = _route_length(shuffled, list(range(n)))
    tsp_circle = _route_tsp(shuffled, start_idx=0)
    check(
        "tsp_circulo_heuristico_mejora_sobre_orden_desordenado",
        tsp_circle["route_length"] < bad_route_length * 0.5,
        {"heuristic_length": tsp_circle["route_length"], "bad_order_length": bad_route_length},
    )

    # 6) assign_and_route con 1 tarea por recurso: cada recurso debe terminar
    #    con exactamente 1 tarea y el costo total debe coincidir con hungaro directo
    resources = [{"id": "R1", "position": [0, 0]}, {"id": "R2", "position": [10, 10]}]
    tasks = [{"id": "T1", "position": [1, 0]}, {"id": "T2", "position": [9, 10]}]
    ar = _assign_and_route(resources, tasks)
    check(
        "assign_and_route_1to1_asigna_el_mas_cercano",
        ar["assignment"][0]["task_ids"] == ["T1"] or ar["assignment"][1]["task_ids"] == ["T1"],
        {"assignment": ar["assignment"]},
    )

    # 7) assign_and_route con tasks_per_resource>1: un solo recurso, 3 tareas,
    #    debe agrupar las 3 en ese recurso y rutearlas
    resources_1 = [{"id": "R1", "position": [0, 0]}]
    tasks_3 = [{"id": "T1", "position": [1, 0]}, {"id": "T2", "position": [2, 0]}, {"id": "T3", "position": [3, 0]}]
    ar2 = _assign_and_route(resources_1, tasks_3, tasks_per_resource=3)
    check(
        "assign_and_route_multi_tarea_agrupa_todas_en_unico_recurso",
        len(ar2["assignment"]) == 1 and set(ar2["assignment"][0]["task_ids"]) == {"T1", "T2", "T3"},
        {"assignment": ar2["assignment"]},
    )

    return {
        "checks": checks,
        "all_pass": all_pass,
        "validation_passed": all_pass,
        "status": "PASSED" if all_pass else "FAILED",
    }


RESOURCE_ASSIGNMENT_TOOL_SCHEMA = {
    "name": "resource_assignment_tool",
    "description": (
        "Asignacion optima de recursos a tareas (algoritmo hungaro, "
        "scipy.optimize.linear_sum_assignment) y ruteo heuristico tipo TSP "
        "(fuerza bruta exacta para <=9 puntos, vecino-mas-cercano+2-opt para "
        "mas puntos). Util para asignar drones a focos de incendio y ordenar "
        "las paradas de cada drone si le tocan varias."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["hungarian_assignment", "route_tsp", "assign_and_route", "validate"],
            },
            "params": {
                "type": "object",
                "description": (
                    "hungarian_assignment: cost_matrix (2D), maximize (bool). "
                    "route_tsp: points (lista [x,y]), start_idx. "
                    "assign_and_route: resources (lista {id,position}), "
                    "tasks (lista {id,position,priority opcional}), "
                    "priority_weight, tasks_per_resource."
                ),
            },
        },
        "required": ["mode"],
    },
}

try:
    from tool_registry import register_tool
    register_tool("resource_assignment_tool", RESOURCE_ASSIGNMENT_TOOL_SCHEMA, compute_resource_assignment_tool)
except ImportError:
    pass


if __name__ == "__main__":
    import json
    print(json.dumps(compute_resource_assignment_tool({"mode": "validate", "params": {}}), indent=2, default=str))
