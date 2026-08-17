"""
quantity_takeoff_tool.py

Tool MCP: quantity_takeoff
Cubicaciones de construcción: volúmenes, áreas y materiales.

Operaciones soportadas (parámetro `operation`):
  - concrete_volume      : volumen de hormigón por elemento (footing/slab/column/beam/wall)
  - formwork_area        : área de encofrado (moldaje) por elemento
  - rebar_weight         : peso de acero de refuerzo a partir de un schedule de barras
  - excavation_volume    : volumen de excavación (prismatoide, con talud opcional)
  - masonry_count        : cantidad de unidades de albañilería (ladrillos/bloques) por muro
  - boq_summary          : agrega una lista de line items en una planilla de cubicación (BOQ)

mode="validate" (alternativa a 'operation'): corre 7 autochequeos contra
valores calculados a mano, uno por cada operación soportada, e ignora
cualquier otro parámetro.

Dependencias: numpy únicamente (sin scipy).
"""

import math
import numpy as np

# Densidad lineal estándar del acero de refuerzo (kg/m) por diámetro nominal en mm.
# Norma chilena/genérica (barras corrugadas, densidad acero 7850 kg/m3).
_REBAR_KG_PER_M = {
    6: 0.222, 8: 0.395, 10: 0.617, 12: 0.888, 14: 1.208,
    16: 1.578, 18: 1.998, 20: 2.466, 22: 2.984, 25: 3.853,
    28: 4.834, 32: 6.313, 36: 7.990,
}


def _concrete_volume(element, dims):
    """dims: dict según el tipo de elemento."""
    if element == "footing":  # zapata rectangular
        return dims["length"] * dims["width"] * dims["thickness"]
    if element == "slab":  # losa
        return dims["area"] * dims["thickness"]
    if element == "column":  # columna rectangular o circular
        if dims.get("shape", "rect") == "circular":
            return np.pi * (dims["diameter"] / 2) ** 2 * dims["height"]
        return dims["width"] * dims["depth"] * dims["height"]
    if element == "beam":
        return dims["width"] * dims["height"] * dims["length"]
    if element == "wall":
        return dims["length"] * dims["height"] * dims["thickness"]
    raise ValueError(f"Elemento no soportado: {element}")


def _formwork_area(element, dims):
    """Área de encofrado en contacto con el hormigón (superficies verticales/laterales, no la cara superior expuesta)."""
    if element == "footing":
        perim = 2 * (dims["length"] + dims["width"])
        return perim * dims["thickness"]
    if element == "column":
        if dims.get("shape", "rect") == "circular":
            return np.pi * dims["diameter"] * dims["height"]
        perim = 2 * (dims["width"] + dims["depth"])
        return perim * dims["height"]
    if element == "beam":
        # dos caras laterales + fondo
        return (2 * dims["height"] + dims["width"]) * dims["length"]
    if element == "wall":
        # dos caras
        return 2 * dims["length"] * dims["height"]
    if element == "slab":
        # solo borde perimetral (asumiendo apoyo inferior con puntales, no losa sobre el suelo)
        perim = dims.get("perimeter")
        if perim is None:
            raise ValueError("slab requiere 'perimeter' para formwork_area")
        return perim * dims["thickness"]
    raise ValueError(f"Elemento no soportado: {element}")


def _rebar_weight(bars):
    """bars: lista de {diameter_mm, length_m, count}"""
    total_kg = 0.0
    detail = []
    for b in bars:
        d = int(b["diameter_mm"])
        if d not in _REBAR_KG_PER_M:
            raise ValueError(f"Diámetro no tabulado: {d} mm")
        kg_per_m = _REBAR_KG_PER_M[d]
        length_total = b["length_m"] * b["count"]
        weight = length_total * kg_per_m
        total_kg += weight
        detail.append({
            "diameter_mm": d,
            "count": b["count"],
            "length_m_each": b["length_m"],
            "total_length_m": length_total,
            "kg_per_m": kg_per_m,
            "weight_kg": round(weight, 2),
        })
    return round(total_kg, 2), detail


def _excavation_volume(dims):
    """
    Excavación prismática con talud opcional (método del prismatoide / promedio de áreas).
    dims: {length, width, depth, slope_h_per_v} donde slope_h_per_v es la relación
    horizontal:vertical del talud (0 = paredes verticales).
    """
    L, W, D = dims["length"], dims["width"], dims["depth"]
    slope = dims.get("slope_h_per_v", 0.0)
    if slope == 0:
        return L * W * D
    # área superior se expande 'slope*D' en cada lado respecto del fondo
    top_L = L + 2 * slope * D
    top_W = W + 2 * slope * D
    bottom_area = L * W
    top_area = top_L * top_W
    mid_area = ((L + top_L) / 2) * ((W + top_W) / 2)
    # regla del prismatoide: V = D/6 * (A_top + 4*A_mid + A_bottom)
    return D / 6 * (top_area + 4 * mid_area + bottom_area)


def _masonry_count(dims):
    """
    dims: {wall_area, unit_length, unit_height, joint_thickness, waste_factor}
    Calcula unidades necesarias considerando junta de mortero.
    """
    unit_l = dims["unit_length"] + dims.get("joint_thickness", 0.01)
    unit_h = dims["unit_height"] + dims.get("joint_thickness", 0.01)
    unit_area = unit_l * unit_h
    raw_count = dims["wall_area"] / unit_area
    waste = dims.get("waste_factor", 0.05)  # 5% merma por defecto
    final_count = int(np.ceil(raw_count * (1 + waste)))
    return {
        "units_theoretical": round(raw_count, 1),
        "waste_factor": waste,
        "units_to_order": final_count,
    }


def _boq_summary(items):
    """
    items: lista de {description, quantity, unit, unit_cost (opcional)}
    Agrupa por 'unit' y calcula subtotal si hay unit_cost.
    """
    grouped = {}
    total_cost = 0.0
    has_cost = False
    for it in items:
        key = it["unit"]
        entry = grouped.setdefault(key, {"unit": key, "total_quantity": 0.0, "lines": []})
        entry["total_quantity"] += it["quantity"]
        line = {"description": it["description"], "quantity": it["quantity"], "unit": it["unit"]}
        if "unit_cost" in it:
            has_cost = True
            subtotal = it["quantity"] * it["unit_cost"]
            line["unit_cost"] = it["unit_cost"]
            line["subtotal"] = round(subtotal, 2)
            total_cost += subtotal
        entry["lines"].append(line)
    result = {"grouped_by_unit": list(grouped.values())}
    if has_cost:
        result["total_cost"] = round(total_cost, 2)
    return result


def _run_validate():
    """Autochequeos contra valores calculados a mano, uno por operación."""
    checks = []

    # 1. concrete_volume / footing: 2 x 1 x 0.3 = 0.6 m3
    vol = _concrete_volume("footing", {"length": 2, "width": 1, "thickness": 0.3})
    checks.append({
        "case": "concrete_volume footing 2x1x0.3",
        "got": round(vol, 4), "expected": 0.6, "ok": abs(vol - 0.6) < 1e-9,
    })

    # 2. formwork_area / column circular: pi * 0.4 * 3 = 3.7699 m2
    area = _formwork_area("column", {"shape": "circular", "diameter": 0.4, "height": 3})
    expected_area = round(math.pi * 0.4 * 3, 4)
    checks.append({
        "case": "formwork_area column circular d=0.4 h=3",
        "got": round(area, 4), "expected": expected_area,
        "ok": abs(round(area, 4) - expected_area) < 1e-6,
    })

    # 3. rebar_weight: 1 barra de 12mm x 1m = 0.888 kg/m (tabla), redondeado a 2 decimales -> 0.89
    total_kg, _ = _rebar_weight([{"diameter_mm": 12, "length_m": 1, "count": 1}])
    checks.append({
        "case": "rebar_weight 1x d12mm L=1m (tabla 0.888 kg/m, redondeado a 2 decimales)",
        "got": total_kg, "expected": 0.89, "ok": abs(total_kg - 0.89) < 1e-9,
    })

    # 4. excavation_volume sin talud: 3x2x1 = 6 m3
    vol_exc = _excavation_volume({"length": 3, "width": 2, "depth": 1})
    checks.append({
        "case": "excavation_volume sin talud 3x2x1",
        "got": round(vol_exc, 4), "expected": 6.0, "ok": abs(vol_exc - 6.0) < 1e-9,
    })

    # 5. excavation_volume con talud 1:1 (prismatoide): L=W=2, D=1 -> 9.3333 m3
    vol_exc_slope = _excavation_volume({"length": 2, "width": 2, "depth": 1, "slope_h_per_v": 1})
    expected_slope = 9.333333333333332
    checks.append({
        "case": "excavation_volume con talud 1:1, L=W=2 D=1 (prismatoide)",
        "got": round(vol_exc_slope, 4), "expected": round(expected_slope, 4),
        "ok": abs(vol_exc_slope - expected_slope) < 1e-6,
    })

    # 6. masonry_count: wall_area=10, unidad 0.39x0.19, junta 0.01, merma 5% -> 132 unidades
    masonry = _masonry_count({"wall_area": 10, "unit_length": 0.39, "unit_height": 0.19})
    checks.append({
        "case": "masonry_count wall_area=10 unit 0.39x0.19 junta 0.01 merma 5%",
        "got": masonry["units_to_order"], "expected": 132, "ok": masonry["units_to_order"] == 132,
    })

    # 7. boq_summary: dos líneas en m3 con costo -> total_quantity=15, total_cost=60
    boq = _boq_summary([
        {"description": "a", "quantity": 10, "unit": "m3", "unit_cost": 5},
        {"description": "b", "quantity": 5, "unit": "m3", "unit_cost": 2},
    ])
    tq = boq["grouped_by_unit"][0]["total_quantity"]
    tc = boq.get("total_cost")
    checks.append({
        "case": "boq_summary 2 lineas m3 con costo (total_quantity y total_cost)",
        "got": {"total_quantity": tq, "total_cost": tc},
        "expected": {"total_quantity": 15, "total_cost": 60},
        "ok": abs(tq - 15) < 1e-9 and abs(tc - 60) < 1e-9,
    })

    all_passed = all(c["ok"] for c in checks)
    return {"validate": True, "all_passed": all_passed, "checks": checks}


QUANTITY_TAKEOFF_TOOL_SCHEMA = {
    "name": "quantity_takeoff",
    "description": (
        "Cubicaciones de construcción: volumen de hormigón, área de encofrado, "
        "peso de acero de refuerzo, volumen de excavación, conteo de unidades "
        "de albañilería y resumen de cubicación (BOQ)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "concrete_volume", "formwork_area", "rebar_weight",
                    "excavation_volume", "masonry_count", "boq_summary",
                ],
                "description": "Tipo de cálculo a ejecutar.",
            },
            "mode": {
                "type": "string",
                "enum": ["validate"],
                "description": "Si es 'validate', ejecuta el autocheque interno (7 casos, uno por operación) contra valores calculados a mano, e ignora 'operation' y el resto de los parámetros.",
            },
            "element": {
                "type": "string",
                "description": "Tipo de elemento (footing/slab/column/beam/wall). Usado por concrete_volume y formwork_area.",
            },
            "dims": {
                "type": "object",
                "description": "Dimensiones del elemento, formato depende de 'element'/'operation'.",
            },
            "bars": {
                "type": "array",
                "description": "Lista de {diameter_mm, length_m, count}. Usado por rebar_weight.",
            },
            "items": {
                "type": "array",
                "description": "Lista de {description, quantity, unit, unit_cost opcional}. Usado por boq_summary.",
            },
        },
        "required": [],
    },
}


def compute_quantity_takeoff(operation=None, mode=None, **params):
    """
    Entry point del tool. Si mode=='validate', corre el autocheque interno.
    Si no, despacha según `operation` (comportamiento original sin cambios).
    Retorna un dict serializable a JSON.
    """
    if mode == "validate":
        return _run_validate()

    if operation is None:
        raise ValueError("Debe indicarse 'operation' (o mode='validate').")

    if operation == "concrete_volume":
        vol = _concrete_volume(params["element"], params["dims"])
        return {"operation": operation, "element": params["element"], "volume_m3": round(vol, 4)}

    if operation == "formwork_area":
        area = _formwork_area(params["element"], params["dims"])
        return {"operation": operation, "element": params["element"], "formwork_area_m2": round(area, 4)}

    if operation == "rebar_weight":
        total_kg, detail = _rebar_weight(params["bars"])
        return {"operation": operation, "total_weight_kg": total_kg, "detail": detail}

    if operation == "excavation_volume":
        vol = _excavation_volume(params["dims"])
        return {"operation": operation, "volume_m3": round(vol, 4)}

    if operation == "masonry_count":
        result = _masonry_count(params["dims"])
        return {"operation": operation, **result}

    if operation == "boq_summary":
        result = _boq_summary(params["items"])
        return {"operation": operation, **result}

    raise ValueError(
        f"Operación no soportada: {operation}. "
        "Usar: concrete_volume | formwork_area | rebar_weight | "
        "excavation_volume | masonry_count | boq_summary"
    )


if __name__ == "__main__":
    import json
    print(json.dumps(compute_quantity_takeoff(mode="validate"), ensure_ascii=False, indent=2))
