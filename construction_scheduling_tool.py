"""
construction_scheduling_tool.py

Tool MCP: construction_scheduling_tool
Planificación de obra: ruta crítica (CPM), carga de recursos, compresión de
cronograma (time-cost tradeoff / crashing).

Operaciones soportadas (parámetro `mode`):
  - critical_path       : método de la ruta crítica (CPM), forward/backward pass
  - resource_loading     : perfil diario de demanda de recursos a partir de un cronograma CPM
  - crash_schedule        : compresión greedy del cronograma (crashing) hacia una reducción objetivo

Dependencias: ninguna externa.
"""

CONSTRUCTION_SCHEDULING_TOOL_SCHEMA = {
    "name": "construction_scheduling_tool",
    "description": (
        "Planificación de obra: ruta crítica vía CPM (early/late start-finish, holguras, "
        "duración total del proyecto), perfil diario de demanda de recursos a partir de un "
        "cronograma, y compresión de cronograma (crashing) por menor pendiente de costo "
        "hacia una reducción de duración objetivo."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["critical_path", "resource_loading", "crash_schedule"]},
            "activities": {
                "type": "array",
                "description": (
                    "Lista de actividades. critical_path/resource_loading: {id, duration, predecessors}. "
                    "crash_schedule: {id, normal_duration, crash_duration, normal_cost, crash_cost, predecessors}."
                ),
            },
            "resource_demand": {"type": "object", "description": "{activity_id: recursos/día}. resource_loading."},
            "target_reduction": {"type": "number", "description": "Días a reducir del proyecto. crash_schedule."},
        },
        "required": ["mode"],
    },
}


def _topo_order(activities):
    by_id = {a["id"]: a for a in activities}
    in_degree = {a["id"]: len(a.get("predecessors", []) or []) for a in activities}
    successors = {a["id"]: [] for a in activities}
    for a in activities:
        for p in a.get("predecessors", []) or []:
            successors[p].append(a["id"])

    queue = [aid for aid, d in in_degree.items() if d == 0]
    order = []
    indeg = dict(in_degree)
    while queue:
        n = queue.pop(0)
        order.append(n)
        for s in successors[n]:
            indeg[s] -= 1
            if indeg[s] == 0:
                queue.append(s)
    if len(order) != len(activities):
        raise ValueError("Ciclo detectado en las dependencias, o predecesor inexistente")
    return order, by_id, successors


def _cpm(activities, duration_key="duration"):
    order, by_id, successors = _topo_order(activities)

    ES, EF = {}, {}
    for aid in order:
        preds = by_id[aid].get("predecessors", []) or []
        ES[aid] = max((EF[p] for p in preds), default=0)
        EF[aid] = ES[aid] + by_id[aid][duration_key]

    project_duration = max(EF.values()) if EF else 0

    LF, LS = {}, {}
    for aid in reversed(order):
        succs = successors[aid]
        LF[aid] = min((LS[s] for s in succs), default=project_duration)
        LS[aid] = LF[aid] - by_id[aid][duration_key]

    schedule = []
    critical_path = []
    for aid in order:
        float_ = round(LS[aid] - ES[aid], 6)
        is_critical = abs(float_) < 1e-9
        schedule.append({
            "id": aid, "duration": by_id[aid][duration_key],
            "ES": ES[aid], "EF": EF[aid], "LS": LS[aid], "LF": LF[aid],
            "float": float_, "critical": is_critical,
        })
        if is_critical:
            critical_path.append(aid)

    return {
        "schedule": schedule, "project_duration": project_duration,
        "critical_path": critical_path, "ES": ES, "EF": EF, "LS": LS, "LF": LF,
    }


def _critical_path(activities):
    result = _cpm(activities, duration_key="duration")
    return {
        "mode": "critical_path",
        "project_duration": result["project_duration"],
        "critical_path": result["critical_path"],
        "schedule": result["schedule"],
    }


def _resource_loading(activities, resource_demand):
    cpm = _cpm(activities, duration_key="duration")
    project_duration = cpm["project_duration"]
    profile = [0.0] * int(project_duration)
    for aid, demand in resource_demand.items():
        es, ef = cpm["ES"][aid], cpm["EF"][aid]
        for day in range(int(es), int(ef)):
            if 0 <= day < len(profile):
                profile[day] += demand

    peak = max(profile) if profile else 0.0
    peak_day = profile.index(peak) if profile else None
    return {
        "mode": "resource_loading",
        "project_duration": project_duration,
        "daily_profile": profile,
        "peak_demand": peak,
        "peak_day": peak_day,
    }


def _crash_schedule(activities, target_reduction):
    # Copia mutable de duraciones normales como duración de trabajo actual
    work = {a["id"]: dict(a) for a in activities}
    for aid, a in work.items():
        a["duration"] = a["normal_duration"]

    total_extra_cost = 0.0
    history = []
    remaining = target_reduction

    while remaining > 1e-9:
        current_activities = list(work.values())
        cpm = _cpm(current_activities, duration_key="duration")
        crit_ids = set(cpm["critical_path"])

        # candidatas: en ruta crítica y aún crasheables
        candidates = []
        for aid in crit_ids:
            a = work[aid]
            crashable = a["duration"] - a["crash_duration"]
            if crashable > 1e-9:
                slope = (a["crash_cost"] - a["normal_cost"]) / (a["normal_duration"] - a["crash_duration"])
                candidates.append((slope, aid, crashable))

        if not candidates:
            break  # no se puede comprimir más

        candidates.sort(key=lambda x: x[0])
        slope, aid, crashable = candidates[0]
        reduce_by = min(1.0, crashable, remaining)
        work[aid]["duration"] -= reduce_by
        cost_added = slope * reduce_by
        total_extra_cost += cost_added
        remaining -= reduce_by
        history.append({
            "activity_crashed": aid, "days_reduced": reduce_by,
            "cost_slope": round(slope, 4), "cost_added": round(cost_added, 2),
        })

    final_cpm = _cpm(list(work.values()), duration_key="duration")
    achieved_reduction = target_reduction - remaining

    return {
        "mode": "crash_schedule",
        "target_reduction": target_reduction,
        "achieved_reduction": round(achieved_reduction, 4),
        "final_project_duration": final_cpm["project_duration"],
        "total_extra_cost": round(total_extra_cost, 2),
        "crash_history": history,
        "final_critical_path": final_cpm["critical_path"],
        "note": None if remaining <= 1e-9 else (
            f"No se alcanzó la reducción objetivo; quedaron {round(remaining,4)} días sin poder "
            "comprimir (actividades críticas ya en su duración de crash mínima)."
        ),
    }


def compute_construction_scheduling(mode, **params):
    """Entry point del tool. Despacha según `mode`. Retorna un dict serializable a JSON."""
    if mode == "critical_path":
        return _critical_path(params["activities"])
    if mode == "resource_loading":
        return _resource_loading(params["activities"], params["resource_demand"])
    if mode == "crash_schedule":
        return _crash_schedule(params["activities"], params["target_reduction"])

    raise ValueError(f"mode no soportado: {mode}. Usar: critical_path | resource_loading | crash_schedule")
