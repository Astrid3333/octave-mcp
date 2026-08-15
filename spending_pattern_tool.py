"""
spending_pattern_tool.py

Analisis de patrones de gasto en el tiempo. Cuatro modos:

- category_breakdown: gasto total y % del total por categoria, dado un
  listado de transacciones {category, amount}.
- trend_detection: regresion lineal simple (minimos cuadrados) sobre una
  serie de gasto mensual, devuelve pendiente, intercepto, R^2 y una
  clasificacion de tendencia (creciente/decreciente/estable) basada en un
  umbral relativo de pendiente sobre el promedio de la serie.
- seasonality_index: indice estacional por mes = gasto_promedio_mes /
  gasto_promedio_general, dado un historico de N años de gasto mensual
  (12 valores por año, se promedia across years si hay mas de un año).
- discretionary_vs_essential: separa transacciones en dos baldes segun un
  mapeo category -> tipo (essential/discretionary) y devuelve montos,
  porcentajes y el ratio discrecional/esencial.
- validate: suite de checks contra casos armados a mano con resultado
  conocido.

Convencion identica al resto de Fase D: compute_spending_pattern(mode,
params=None) -> dict; se registra en tool_registry via register_tool()
al final del modulo (patron identico a debt_snowball_tool.py /
insurance_risk_tool.py).
"""
import numpy as np


SPENDING_PATTERN_TOOL_SCHEMA = {
    "name": "spending_pattern_tool",
    "description": (
        "Analisis de patrones de gasto: category_breakdown (gasto total y % "
        "del total por categoria dado un listado de transacciones), "
        "trend_detection (regresion lineal simple sobre gasto mensual, "
        "pendiente/intercepto/R^2 y clasificacion creciente/decreciente/"
        "estable), seasonality_index (indice estacional por mes = "
        "gasto_promedio_mes/gasto_promedio_general, promediando sobre N "
        "anios si el historico tiene mas de 12 valores), "
        "discretionary_vs_essential (separa transacciones segun un mapeo "
        "categoria->tipo y devuelve montos/porcentajes/ratio "
        "discrecional/esencial), validate (suite de checks). Motor "
        "generico: no trae catalogo de categorias propio, lo provee quien "
        "llama."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "category_breakdown",
                    "trend_detection",
                    "seasonality_index",
                    "discretionary_vs_essential",
                    "validate",
                ],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


def _mode_category_breakdown(params):
    transactions = params.get("transactions")
    if not transactions:
        raise ValueError("transactions es requerido y no puede estar vacio")

    totals = {}
    for t in transactions:
        cat = t["category"]
        amt = float(t["amount"])
        totals[cat] = totals.get(cat, 0.0) + amt

    grand_total = sum(totals.values())
    if grand_total <= 0:
        raise ValueError("la suma total de montos debe ser > 0")

    breakdown = [
        {
            "category": cat,
            "total": total,
            "pct_of_total": 100.0 * total / grand_total,
        }
        for cat, total in totals.items()
    ]
    breakdown.sort(key=lambda x: x["total"], reverse=True)

    return {
        "mode": "category_breakdown",
        "grand_total": grand_total,
        "n_transactions": len(transactions),
        "n_categories": len(totals),
        "breakdown": breakdown,
    }


def _mode_trend_detection(params):
    monthly_spending = params.get("monthly_spending")
    if not monthly_spending or len(monthly_spending) < 2:
        raise ValueError("monthly_spending requiere al menos 2 valores")

    y = np.array(monthly_spending, dtype=float)
    n = len(y)
    x = np.arange(n, dtype=float)

    x_mean = x.mean()
    y_mean = y.mean()
    ss_xx = np.sum((x - x_mean) ** 2)
    ss_xy = np.sum((x - x_mean) * (y - y_mean))

    if ss_xx == 0:
        raise ValueError("varianza de x nula, no se puede ajustar")

    slope = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean

    y_pred = slope * x + intercept
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y_mean) ** 2)
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0

    threshold_pct = float(params.get("threshold_pct", 2.0))
    rel_slope_pct = 100.0 * slope / y_mean if y_mean != 0 else 0.0

    if rel_slope_pct > threshold_pct:
        classification = "creciente"
    elif rel_slope_pct < -threshold_pct:
        classification = "decreciente"
    else:
        classification = "estable"

    return {
        "mode": "trend_detection",
        "n_months": n,
        "slope": float(slope),
        "intercept": float(intercept),
        "r_squared": float(r_squared),
        "rel_slope_pct_per_month": float(rel_slope_pct),
        "threshold_pct": threshold_pct,
        "classification": classification,
    }


def _mode_seasonality_index(params):
    monthly_history = params.get("monthly_history")
    if not monthly_history or len(monthly_history) < 12:
        raise ValueError("monthly_history requiere al menos 12 valores (1 anio)")
    if len(monthly_history) % 12 != 0:
        raise ValueError("monthly_history debe ser multiplo de 12 (anios completos)")

    arr = np.array(monthly_history, dtype=float)
    n_years = len(arr) // 12
    by_month = arr.reshape(n_years, 12)

    month_avgs = by_month.mean(axis=0)
    overall_avg = arr.mean()
    if overall_avg <= 0:
        raise ValueError("el promedio general debe ser > 0")

    indices = month_avgs / overall_avg

    month_names = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    by_month_result = [
        {"month": month_names[i], "avg_spending": float(month_avgs[i]), "index": float(indices[i])}
        for i in range(12)
    ]

    peak_idx = int(np.argmax(indices))
    trough_idx = int(np.argmin(indices))

    return {
        "mode": "seasonality_index",
        "n_years": n_years,
        "overall_avg": float(overall_avg),
        "by_month": by_month_result,
        "peak_month": month_names[peak_idx],
        "peak_index": float(indices[peak_idx]),
        "trough_month": month_names[trough_idx],
        "trough_index": float(indices[trough_idx]),
    }


def _mode_discretionary_vs_essential(params):
    transactions = params.get("transactions")
    category_map = params.get("category_map")
    if not transactions:
        raise ValueError("transactions es requerido y no puede estar vacio")
    if not category_map:
        raise ValueError("category_map es requerido (dict category -> 'essential'|'discretionary')")

    essential_total = 0.0
    discretionary_total = 0.0
    unmapped = []

    for t in transactions:
        cat = t["category"]
        amt = float(t["amount"])
        kind = category_map.get(cat)
        if kind == "essential":
            essential_total += amt
        elif kind == "discretionary":
            discretionary_total += amt
        else:
            unmapped.append(cat)

    if unmapped:
        raise ValueError(
            f"categorias sin mapeo valido en category_map: {sorted(set(unmapped))}"
        )

    total = essential_total + discretionary_total
    if total <= 0:
        raise ValueError("el total de gasto mapeado debe ser > 0")

    ratio = discretionary_total / essential_total if essential_total > 0 else float("inf")

    return {
        "mode": "discretionary_vs_essential",
        "essential_total": essential_total,
        "discretionary_total": discretionary_total,
        "total": total,
        "essential_pct": 100.0 * essential_total / total,
        "discretionary_pct": 100.0 * discretionary_total / total,
        "discretionary_to_essential_ratio": ratio,
    }


def _mode_validate():
    checks = []

    # 1) category_breakdown: dos categorias, monto y % correctos
    r1 = _mode_category_breakdown({
        "transactions": [
            {"category": "comida", "amount": 300.0},
            {"category": "comida", "amount": 100.0},
            {"category": "transporte", "amount": 100.0},
        ]
    })
    comida = next(b for b in r1["breakdown"] if b["category"] == "comida")
    checks.append({
        "name": "category_breakdown_totals_and_pct",
        "comida_total": comida["total"], "comida_pct": comida["pct_of_total"],
        "passed": abs(comida["total"] - 400.0) < 1e-9 and abs(comida["pct_of_total"] - 80.0) < 1e-9,
    })

    # 2) category_breakdown: transactions vacio lanza excepcion
    try:
        _mode_category_breakdown({"transactions": []})
        raised2 = False
    except ValueError:
        raised2 = True
    checks.append({"name": "empty_transactions_raises", "passed": raised2})

    # 3) trend_detection: serie perfectamente lineal creciente, slope exacto y R^2=1
    r3 = _mode_trend_detection({"monthly_spending": [100.0, 110.0, 120.0, 130.0, 140.0]})
    checks.append({
        "name": "trend_perfect_linear_slope_and_r2",
        "slope": r3["slope"], "r_squared": r3["r_squared"], "classification": r3["classification"],
        "passed": abs(r3["slope"] - 10.0) < 1e-9 and abs(r3["r_squared"] - 1.0) < 1e-9 and r3["classification"] == "creciente",
    })

    # 4) trend_detection: serie constante da slope 0 y clasificacion estable
    r4 = _mode_trend_detection({"monthly_spending": [500.0, 500.0, 500.0, 500.0]})
    checks.append({
        "name": "trend_flat_series_is_stable",
        "slope": r4["slope"], "classification": r4["classification"],
        "passed": abs(r4["slope"]) < 1e-9 and r4["classification"] == "estable",
    })

    # 5) seasonality_index: un solo mes con el doble del resto da index=2 en ese mes
    monthly_history = [100.0] * 12
    monthly_history[0] = 200.0  # enero al doble
    r5 = _mode_seasonality_index({"monthly_history": monthly_history})
    enero = next(m for m in r5["by_month"] if m["month"] == "enero")
    checks.append({
        "name": "seasonality_single_spike_month_index",
        "enero_index": enero["index"], "peak_month": r5["peak_month"],
        "passed": abs(enero["index"] - 200.0 / (1300.0 / 12.0)) < 1e-9 and r5["peak_month"] == "enero",
    })

    # 6) seasonality_index: longitud no multiplo de 12 lanza excepcion
    try:
        _mode_seasonality_index({"monthly_history": [100.0] * 13})
        raised6 = False
    except ValueError:
        raised6 = True
    checks.append({"name": "non_multiple_of_12_raises", "passed": raised6})

    # 7) discretionary_vs_essential: ratio y porcentajes correctos
    r7 = _mode_discretionary_vs_essential({
        "transactions": [
            {"category": "alquiler", "amount": 700.0},
            {"category": "streaming", "amount": 100.0},
            {"category": "restaurantes", "amount": 200.0},
        ],
        "category_map": {
            "alquiler": "essential",
            "streaming": "discretionary",
            "restaurantes": "discretionary",
        },
    })
    checks.append({
        "name": "discretionary_ratio_and_pct",
        "ratio": r7["discretionary_to_essential_ratio"], "discretionary_pct": r7["discretionary_pct"],
        "passed": abs(r7["discretionary_to_essential_ratio"] - 300.0 / 700.0) < 1e-9
        and abs(r7["discretionary_pct"] - 30.0) < 1e-9,
    })

    # 8) discretionary_vs_essential: categoria sin mapeo lanza excepcion
    try:
        _mode_discretionary_vs_essential({
            "transactions": [{"category": "misterio", "amount": 50.0}],
            "category_map": {"otra": "essential"},
        })
        raised8 = False
    except ValueError:
        raised8 = True
    checks.append({"name": "unmapped_category_raises", "passed": raised8})

    # 9) modo invalido lanza excepcion
    try:
        compute_spending_pattern("modo_invalido", {})
        invalid_raised = False
    except (KeyError, ValueError):
        invalid_raised = True
    checks.append({"name": "invalid_mode_raises", "passed": invalid_raised})

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_spending_pattern(mode, params=None):
    params = params or {}

    if mode == "category_breakdown":
        return _mode_category_breakdown(params)
    elif mode == "trend_detection":
        return _mode_trend_detection(params)
    elif mode == "seasonality_index":
        return _mode_seasonality_index(params)
    elif mode == "discretionary_vs_essential":
        return _mode_discretionary_vs_essential(params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(
            f"modo desconocido: {mode}. Use category_breakdown | trend_detection | "
            f"seasonality_index | discretionary_vs_essential | validate"
        )


try:
    from tool_registry import register_tool
    register_tool(
        name="spending_pattern_tool",
        schema=SPENDING_PATTERN_TOOL_SCHEMA,
        handler=lambda args: compute_spending_pattern(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    d = compute_spending_pattern("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de spending_pattern_tool.py pasaron OK.")
