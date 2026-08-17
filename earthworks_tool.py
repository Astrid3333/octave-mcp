"""
earthworks_tool.py

Tool MCP: earthworks
Movimiento de tierras a escala de trazado/terreno (complementa quantity_takeoff.excavation_volume,
que solo cubre prismas simples con talud constante).

Operaciones soportadas (parámetro `operation`):
  - average_end_area    : volumen entre secciones transversales a lo largo de un trazado
  - cut_fill_grid        : volumen de corte/relleno sobre una grilla de profundidades (terreno irregular)
  - swell_shrinkage      : conversión banco -> suelto -> compactado
  - mass_haul_balance    : diagrama de masas acumulado y puntos de balance a lo largo de un trazado

mode="validate" (alternativa a 'operation'): corre 4 autochequeos contra
valores calculados a mano, uno por cada operación soportada, e ignora
cualquier otro parámetro.

Dependencias: numpy únicamente (sin scipy).
"""

import numpy as np

EARTHWORKS_TOOL_SCHEMA = {
    "name": "earthworks",
    "description": (
        "Movimiento de tierras a escala de trazado/terreno: volumen entre secciones "
        "transversales (método del área media), volumen de corte/relleno sobre una grilla "
        "de profundidades (terreno irregular), conversión de volumen banco/suelto/compactado "
        "por esponjamiento y contracción, y diagrama de masas acumulado con puntos de balance. "
        "Complementa quantity_takeoff (excavation_volume), que solo cubre prismas simples con talud."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["average_end_area", "cut_fill_grid", "swell_shrinkage", "mass_haul_balance"],
            },
            "mode": {
                "type": "string",
                "enum": ["validate"],
                "description": "Si es 'validate', ejecuta el autocheque interno (4 casos, uno por operación) contra valores calculados a mano, e ignora 'operation' y el resto de los parámetros.",
            },
            "sections": {
                "type": "array",
                "description": "Lista de {station, area} en orden a lo largo del trazado. average_end_area.",
            },
            "prismoidal": {"type": "boolean", "default": False, "description": "Usar corrección prismoidal si hay área media. average_end_area."},
            "depths": {"type": "array", "description": "Grilla 2D (lista de listas) de profundidades corte-relleno (existente-diseño) en nodos. cut_fill_grid."},
            "dx": {"type": "number", "description": "Espaciado de grilla en x. cut_fill_grid."},
            "dy": {"type": "number", "description": "Espaciado de grilla en y. cut_fill_grid."},
            "bank_volume": {"type": "number", "description": "Volumen en banco (in situ), m3. swell_shrinkage."},
            "swell_factor": {"type": "number", "description": "Esponjamiento como fracción (ej 0.25 = 25%). swell_shrinkage."},
            "shrinkage_factor": {"type": "number", "description": "Contracción como fracción (ej 0.15 = 15%). swell_shrinkage."},
            "stations": {"type": "array", "description": "Lista de {station, net_volume} (corte positivo, relleno negativo). mass_haul_balance."},
        },
        "required": [],
    },
}


# ---------------------------------------------------------------------------
# average_end_area
# ---------------------------------------------------------------------------

def _average_end_area(sections, prismoidal=False):
    sections = sorted(sections, key=lambda s: s["station"])
    intervals = []
    total = 0.0
    for a, b in zip(sections[:-1], sections[1:]):
        L = b["station"] - a["station"]
        if prismoidal and "area_mid" in a:
            Am = a["area_mid"]
            V = L / 6 * (a["area"] + 4 * Am + b["area"])
            method = "prismoidal"
        else:
            V = L * (a["area"] + b["area"]) / 2
            method = "average_end_area"
        total += V
        intervals.append({
            "from_station": a["station"], "to_station": b["station"],
            "length": round(L, 4), "volume_m3": round(V, 4), "method": method,
        })
    return {
        "operation": "average_end_area",
        "intervals": intervals,
        "total_volume_m3": round(total, 4),
    }


# ---------------------------------------------------------------------------
# cut_fill_grid
# ---------------------------------------------------------------------------

def _cut_fill_grid(depths, dx, dy):
    d = np.array(depths, dtype=float)
    if d.ndim != 2 or d.shape[0] < 2 or d.shape[1] < 2:
        raise ValueError("depths debe ser una grilla 2D de al menos 2x2 nodos")

    cell_area = dx * dy
    cut_vol = 0.0
    fill_vol = 0.0
    nrows, ncols = d.shape
    for i in range(nrows - 1):
        for j in range(ncols - 1):
            avg_depth = (d[i, j] + d[i + 1, j] + d[i, j + 1] + d[i + 1, j + 1]) / 4.0
            cell_vol = avg_depth * cell_area
            if cell_vol >= 0:
                cut_vol += cell_vol
            else:
                fill_vol += -cell_vol

    return {
        "operation": "cut_fill_grid",
        "cut_volume_m3": round(cut_vol, 4),
        "fill_volume_m3": round(fill_vol, 4),
        "net_volume_m3": round(cut_vol - fill_vol, 4),
        "note": (
            "Aproximación por celda (promedio de 4 esquinas por celda, clasificada íntegramente "
            "como corte o relleno según el signo del promedio). Celdas que cruzan la línea de "
            "corte/relleno internamente no se subdividen — estimación preliminar."
        ),
    }


# ---------------------------------------------------------------------------
# swell_shrinkage
# ---------------------------------------------------------------------------

def _swell_shrinkage(bank_volume, swell_factor=None, shrinkage_factor=None):
    result = {"operation": "swell_shrinkage", "bank_volume_m3": round(bank_volume, 4)}
    if swell_factor is not None:
        loose = bank_volume * (1 + swell_factor)
        result["loose_volume_m3"] = round(loose, 4)
        result["swell_factor"] = swell_factor
    if shrinkage_factor is not None:
        compacted = bank_volume * (1 - shrinkage_factor)
        result["compacted_volume_m3"] = round(compacted, 4)
        result["shrinkage_factor"] = shrinkage_factor
    if swell_factor is None and shrinkage_factor is None:
        raise ValueError("Se requiere al menos swell_factor o shrinkage_factor")
    return result


# ---------------------------------------------------------------------------
# mass_haul_balance
# ---------------------------------------------------------------------------

def _mass_haul_balance(stations):
    stations = sorted(stations, key=lambda s: s["station"])
    cum = 0.0
    ordinates = []
    for s in stations:
        cum += s["net_volume"]
        ordinates.append({"station": s["station"], "net_volume": s["net_volume"], "cumulative": round(cum, 4)})

    balance_points = []
    if ordinates and ordinates[0]["cumulative"] == 0.0:
        balance_points.append(round(ordinates[0]["station"], 4))
    for a, b in zip(ordinates[:-1], ordinates[1:]):
        ca, cb = a["cumulative"], b["cumulative"]
        if cb == 0.0:
            balance_points.append(round(b["station"], 4))
        elif ca != 0.0 and (ca > 0) != (cb > 0):  # cambio de signo -> cruce por cero
            frac = -ca / (cb - ca)
            station_zero = a["station"] + frac * (b["station"] - a["station"])
            balance_points.append(round(float(station_zero), 4))

    return {
        "operation": "mass_haul_balance",
        "mass_diagram": ordinates,
        "balance_points": balance_points,
        "final_cumulative_m3": ordinates[-1]["cumulative"] if ordinates else 0.0,
        "note": (
            "cumulative final != 0 implica desbalance neto corte/relleno del trazado "
            "(sobra o falta material, requiere préstamo o botadero)."
        ),
    }


def _run_validate():
    """Autochequeos contra valores calculados a mano, uno por operación."""
    checks = []

    # 1. average_end_area: 2 secciones station 0/10, area 10/20 -> V = 10*(10+20)/2 = 150
    aea = _average_end_area([{"station": 0, "area": 10}, {"station": 10, "area": 20}])
    checks.append({
        "case": "average_end_area station 0->10, area 10->20",
        "got": aea["total_volume_m3"], "expected": 150.0,
        "ok": abs(aea["total_volume_m3"] - 150.0) < 1e-6,
    })

    # 2. cut_fill_grid: grilla 2x2 uniforme depth=2, dx=3 dy=2 -> 1 celda, cut = 2*6 = 12, fill=0
    cfg = _cut_fill_grid([[2, 2], [2, 2]], dx=3, dy=2)
    checks.append({
        "case": "cut_fill_grid 2x2 uniforme depth=2 dx=3 dy=2",
        "got": {"cut": cfg["cut_volume_m3"], "fill": cfg["fill_volume_m3"]},
        "expected": {"cut": 12.0, "fill": 0.0},
        "ok": abs(cfg["cut_volume_m3"] - 12.0) < 1e-6 and abs(cfg["fill_volume_m3"] - 0.0) < 1e-6,
    })

    # 3. swell_shrinkage: banco 100 m3, swell 25% -> suelto 125, shrinkage 15% -> compactado 85
    ss = _swell_shrinkage(100, swell_factor=0.25, shrinkage_factor=0.15)
    checks.append({
        "case": "swell_shrinkage banco=100 swell=25% shrink=15%",
        "got": {"loose": ss["loose_volume_m3"], "compacted": ss["compacted_volume_m3"]},
        "expected": {"loose": 125.0, "compacted": 85.0},
        "ok": abs(ss["loose_volume_m3"] - 125.0) < 1e-6 and abs(ss["compacted_volume_m3"] - 85.0) < 1e-6,
    })

    # 4. mass_haul_balance: corte 10 en station 0, relleno -10 en station 10 -> cumulativo [10, 0], balance en station 10
    mhb = _mass_haul_balance([{"station": 0, "net_volume": 10}, {"station": 10, "net_volume": -10}])
    checks.append({
        "case": "mass_haul_balance corte 10@0, relleno -10@10",
        "got": {"final_cumulative": mhb["final_cumulative_m3"], "balance_points": mhb["balance_points"]},
        "expected": {"final_cumulative": 0.0, "balance_points": [10.0]},
        "ok": abs(mhb["final_cumulative_m3"] - 0.0) < 1e-6 and mhb["balance_points"] == [10.0],
    })

    all_passed = all(c["ok"] for c in checks)
    return {"validate": True, "all_passed": all_passed, "checks": checks}


def compute_earthworks(operation=None, mode=None, **params):
    """Entry point del tool. Si mode=='validate', corre el autocheque interno.
    Si no, despacha según `operation` (comportamiento original sin cambios)."""
    if mode == "validate":
        return _run_validate()

    if operation is None:
        raise ValueError("Debe indicarse 'operation' (o mode='validate').")

    if operation == "average_end_area":
        return _average_end_area(params["sections"], params.get("prismoidal", False))
    if operation == "cut_fill_grid":
        return _cut_fill_grid(params["depths"], params["dx"], params["dy"])
    if operation == "swell_shrinkage":
        return _swell_shrinkage(
            params["bank_volume"], params.get("swell_factor"), params.get("shrinkage_factor")
        )
    if operation == "mass_haul_balance":
        return _mass_haul_balance(params["stations"])

    raise ValueError(
        f"operation no soportada: {operation}. Usar: average_end_area | cut_fill_grid | "
        "swell_shrinkage | mass_haul_balance"
    )


if __name__ == "__main__":
    import json
    print(json.dumps(compute_earthworks(mode="validate"), ensure_ascii=False, indent=2))
