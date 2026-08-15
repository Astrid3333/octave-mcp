"""
savings_rate_tool.py

Metricas de tasa de ahorro relativa al ingreso (distinto de
savings_goal_tool, que hace interes compuesto sobre un monto fijo de
meta). Cuatro modos:

- savings_rate: ahorro / ingreso neto, dado ingreso y gastos (o ahorro
  directo).
- benchmark_compare: compara la tasa de ahorro real contra reglas
  conocidas (50/30/20 -> implica 20% ahorro; regla del 15% de retiro).
- time_to_goal: dado un savings_rate constante sobre el ingreso, calcula
  cuantos anios se tarda en acumular un multiplo N del gasto anual
  (numero FIRE), con crecimiento real del portafolio via interes
  compuesto (aportes mensuales = ahorro mensual, mismo motor que
  savings_goal_tool pero resolviendo para el tiempo en vez del monto).
- rate_sensitivity: recalcula time_to_goal para una grilla de tasas de
  ahorro (rate +/- deltas) para mostrar sensibilidad.
- validate: suite de checks contra casos con solucion cerrada conocida.

Convencion identica al resto de Fase D: compute_savings_rate(mode,
params=None) -> dict, registrado via tool_registry.register_tool().
"""
import numpy as np


SAVINGS_RATE_TOOL_SCHEMA = {
    "name": "savings_rate_tool",
    "description": (
        "Metricas de tasa de ahorro relativa al ingreso (no confundir con "
        "savings_goal_tool, que es interes compuesto sobre un monto fijo): "
        "savings_rate (ahorro/ingreso neto dado ingreso y gastos o ahorro "
        "directo), benchmark_compare (compara la tasa real contra reglas "
        "conocidas: 50/30/20 implica 20% ahorro, regla del 15% de retiro), "
        "time_to_goal (anios para acumular N veces el gasto anual -numero "
        "FIRE- dado un savings_rate constante y una tasa de retorno anual, "
        "via interes compuesto con aportes mensuales), rate_sensitivity "
        "(recalcula time_to_goal para una grilla de tasas de ahorro +/- "
        "deltas), validate (suite de checks). Motor generico: la tasa de "
        "retorno y las reglas de benchmark las provee quien llama (con "
        "defaults razonables)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "savings_rate",
                    "benchmark_compare",
                    "time_to_goal",
                    "rate_sensitivity",
                    "validate",
                ],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


def _compute_rate(params):
    """Deriva (net_income, monthly_savings, rate) a partir de params,
    aceptando dos formas de input: (income, expenses) o (income, savings)."""
    income = float(params["net_income"])
    if income <= 0:
        raise ValueError("net_income debe ser > 0")

    if "monthly_savings" in params:
        savings = float(params["monthly_savings"])
    elif "monthly_expenses" in params:
        expenses = float(params["monthly_expenses"])
        savings = income - expenses
    else:
        raise ValueError("se requiere monthly_savings o monthly_expenses")

    rate = savings / income
    return income, savings, rate


def _mode_savings_rate(params):
    income, savings, rate = _compute_rate(params)
    return {
        "mode": "savings_rate",
        "net_income": income,
        "monthly_savings": savings,
        "savings_rate": rate,
        "savings_rate_pct": 100.0 * rate,
    }


def _mode_benchmark_compare(params):
    income, savings, rate = _compute_rate(params)

    benchmarks = {
        "regla_50_30_20": 0.20,
        "regla_15_retiro": 0.15,
    }
    custom_benchmarks = params.get("custom_benchmarks", {})
    benchmarks.update({k: float(v) for k, v in custom_benchmarks.items()})

    comparisons = [
        {
            "benchmark": name,
            "benchmark_rate": target,
            "diff_pp": 100.0 * (rate - target),
            "meets_or_exceeds": rate >= target,
        }
        for name, target in benchmarks.items()
    ]

    return {
        "mode": "benchmark_compare",
        "savings_rate": rate,
        "savings_rate_pct": 100.0 * rate,
        "comparisons": comparisons,
    }


def _solve_years_to_fire(annual_expenses, monthly_savings, annual_return, fire_multiple, max_years=100):
    """Resuelve para n (en meses) el problema de valor futuro de anualidad
    con aportes mensuales constantes hasta alcanzar target = fire_multiple *
    annual_expenses, via busqueda numerica sobre la formula cerrada de
    valor futuro de anualidad ordinaria (FV = PMT * ((1+i)^n - 1)/i).
    Devuelve (years, months_exact) o (None, None) si no converge en
    max_years."""
    target = fire_multiple * annual_expenses
    if monthly_savings <= 0:
        return None, None

    monthly_rate = annual_return / 12.0

    if monthly_rate == 0:
        months_exact = target / monthly_savings
    else:
        # FV = PMT * ((1+i)^n - 1) / i  =>  resolver n
        ratio = target * monthly_rate / monthly_savings + 1.0
        if ratio <= 0:
            return None, None
        months_exact = np.log(ratio) / np.log(1.0 + monthly_rate)

    months_exact = float(months_exact)

    if months_exact > max_years * 12:
        return None, None

    return months_exact / 12.0, months_exact


def _mode_time_to_goal(params):
    income, savings, rate = _compute_rate(params)
    if savings <= 0:
        raise ValueError("monthly_savings debe ser > 0 para calcular time_to_goal")

    annual_expenses = float(params.get("annual_expenses", (income - savings) * 12.0))
    annual_return = float(params.get("annual_return", 0.05))
    fire_multiple = float(params.get("fire_multiple", 25.0))

    years, months_exact = _solve_years_to_fire(annual_expenses, savings, annual_return, fire_multiple)
    if years is None:
        raise ValueError("no converge en un horizonte razonable (revisar savings_rate/annual_return)")

    return {
        "mode": "time_to_goal",
        "net_income": income,
        "monthly_savings": savings,
        "savings_rate": rate,
        "annual_expenses": annual_expenses,
        "annual_return": annual_return,
        "fire_multiple": fire_multiple,
        "fire_number": fire_multiple * annual_expenses,
        "years_to_goal": years,
        "months_to_goal_exact": months_exact,
    }


def _mode_rate_sensitivity(params):
    base = _mode_time_to_goal(params)
    deltas_pp = params.get("deltas_pp", [-5.0, -2.0, 2.0, 5.0])

    income = base["net_income"]
    annual_expenses = base["annual_expenses"]
    annual_return = base["annual_return"]
    fire_multiple = base["fire_multiple"]

    grid = []
    for d in deltas_pp:
        new_rate = base["savings_rate"] + d / 100.0
        if new_rate <= 0 or new_rate >= 1.0:
            grid.append({"delta_pp": d, "new_rate_pct": 100.0 * new_rate, "years_to_goal": None, "note": "tasa fuera de rango (0,1)"})
            continue
        new_savings = new_rate * income
        years, _ = _solve_years_to_fire(annual_expenses, new_savings, annual_return, fire_multiple)
        grid.append({
            "delta_pp": d,
            "new_rate_pct": 100.0 * new_rate,
            "new_monthly_savings": new_savings,
            "years_to_goal": years,
            "years_saved_vs_base": (base["years_to_goal"] - years) if years is not None else None,
        })

    return {
        "mode": "rate_sensitivity",
        "base": base,
        "grid": grid,
    }


def _mode_validate():
    checks = []

    # 1) savings_rate con monthly_savings directo
    r1 = _mode_savings_rate({"net_income": 1000.0, "monthly_savings": 200.0})
    checks.append({
        "name": "savings_rate_direct_savings",
        "rate": r1["savings_rate"],
        "passed": abs(r1["savings_rate"] - 0.20) < 1e-9,
    })

    # 2) savings_rate derivado de expenses da el mismo resultado
    r2 = _mode_savings_rate({"net_income": 1000.0, "monthly_expenses": 800.0})
    checks.append({
        "name": "savings_rate_from_expenses_matches_direct",
        "rate": r2["savings_rate"],
        "passed": abs(r2["savings_rate"] - r1["savings_rate"]) < 1e-9,
    })

    # 3) net_income <= 0 lanza excepcion
    try:
        _mode_savings_rate({"net_income": 0.0, "monthly_savings": 100.0})
        raised3 = False
    except ValueError:
        raised3 = True
    checks.append({"name": "zero_income_raises", "passed": raised3})

    # 4) benchmark_compare: 20% de ahorro empata exacto con regla 50/30/20
    r4 = _mode_benchmark_compare({"net_income": 1000.0, "monthly_savings": 200.0})
    b_50_30_20 = next(c for c in r4["comparisons"] if c["benchmark"] == "regla_50_30_20")
    checks.append({
        "name": "benchmark_50_30_20_exact_match",
        "diff_pp": b_50_30_20["diff_pp"], "meets": b_50_30_20["meets_or_exceeds"],
        "passed": abs(b_50_30_20["diff_pp"]) < 1e-9 and b_50_30_20["meets_or_exceeds"] is True,
    })

    # 5) time_to_goal con annual_return=0: solucion cerrada exacta (sin interes)
    # target = 25 * 12000 = 300000; monthly_savings=1000 => months = 300000/1000=300 => 25 anios
    r5 = _mode_time_to_goal({
        "net_income": 2000.0, "monthly_savings": 1000.0,
        "annual_expenses": 12000.0, "annual_return": 0.0, "fire_multiple": 25.0,
    })
    checks.append({
        "name": "time_to_goal_zero_return_exact",
        "years": r5["years_to_goal"],
        "passed": abs(r5["years_to_goal"] - 25.0) < 1e-9,
    })

    # 6) time_to_goal con retorno > 0 tarda MENOS que con retorno 0 (mismo ahorro)
    r6 = _mode_time_to_goal({
        "net_income": 2000.0, "monthly_savings": 1000.0,
        "annual_expenses": 12000.0, "annual_return": 0.07, "fire_multiple": 25.0,
    })
    checks.append({
        "name": "positive_return_reduces_years",
        "years_with_return": r6["years_to_goal"], "years_zero_return": r5["years_to_goal"],
        "passed": r6["years_to_goal"] < r5["years_to_goal"],
    })

    # 7) time_to_goal: monthly_savings <= 0 lanza excepcion
    try:
        _mode_time_to_goal({"net_income": 1000.0, "monthly_savings": 0.0, "annual_expenses": 12000.0})
        raised7 = False
    except ValueError:
        raised7 = True
    checks.append({"name": "zero_savings_raises_on_time_to_goal", "passed": raised7})

    # 8) rate_sensitivity: delta positivo de tasa reduce years_to_goal
    r8 = _mode_rate_sensitivity({
        "net_income": 2000.0, "monthly_savings": 400.0,
        "annual_expenses": 19200.0, "annual_return": 0.05, "fire_multiple": 25.0,
        "deltas_pp": [5.0],
    })
    g = r8["grid"][0]
    checks.append({
        "name": "positive_delta_reduces_years",
        "years_saved": g["years_saved_vs_base"],
        "passed": g["years_saved_vs_base"] is not None and g["years_saved_vs_base"] > 0,
    })

    # 9) rate_sensitivity: delta que saca la tasa fuera de (0,1) se marca sin calcular
    r9 = _mode_rate_sensitivity({
        "net_income": 1000.0, "monthly_savings": 950.0,
        "annual_expenses": 6000.0, "annual_return": 0.05, "fire_multiple": 25.0,
        "deltas_pp": [10.0],
    })
    g9 = r9["grid"][0]
    checks.append({
        "name": "out_of_range_delta_marked_none",
        "years_to_goal": g9["years_to_goal"],
        "passed": g9["years_to_goal"] is None,
    })

    # 10) modo invalido lanza excepcion
    try:
        compute_savings_rate("modo_invalido", {})
        invalid_raised = False
    except (KeyError, ValueError):
        invalid_raised = True
    checks.append({"name": "invalid_mode_raises", "passed": invalid_raised})

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_savings_rate(mode, params=None):
    params = params or {}

    if mode == "savings_rate":
        return _mode_savings_rate(params)
    elif mode == "benchmark_compare":
        return _mode_benchmark_compare(params)
    elif mode == "time_to_goal":
        return _mode_time_to_goal(params)
    elif mode == "rate_sensitivity":
        return _mode_rate_sensitivity(params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(
            f"modo desconocido: {mode}. Use savings_rate | benchmark_compare | "
            f"time_to_goal | rate_sensitivity | validate"
        )


try:
    from tool_registry import register_tool
    register_tool(
        name="savings_rate_tool",
        schema=SAVINGS_RATE_TOOL_SCHEMA,
        handler=lambda args: compute_savings_rate(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    d = compute_savings_rate("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de savings_rate_tool.py pasaron OK.")
