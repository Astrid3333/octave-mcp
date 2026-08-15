"""
habit_streak_tool.py

Modelado de consistencia/adherencia a habitos financieros. Tres modos:

- streak_analysis: dado un historico binario mes a mes (1=cumplido,
  0=no cumplido), calcula la racha actual, la racha mas larga historica,
  el numero de rachas y la tasa global de cumplimiento.
- consistency_score: dado un historico numerico de gasto mes a mes,
  calcula el coeficiente de variacion (desviacion estandar / media) como
  proxy de disciplina -- CV mas bajo = gasto mas consistente/predecible.
  Se devuelve tambien un score normalizado 0-100 (100 = CV=0) via
  score = 100 / (1 + CV).
- habit_decay: modelo de decaimiento exponencial de adherencia post-inicio
  de un habito, adherence(t) = adherence_0 * exp(-t / tau), dado
  adherence_0, tau (vida media derivada de half_life = tau * ln(2)) y un
  horizonte de meses; devuelve la curva y la vida media.
- validate: suite de checks contra casos con solucion cerrada conocida.

Convencion identica al resto de Fase D: compute_habit_streak(mode,
params=None) -> dict, registrado via tool_registry.register_tool().
"""
import numpy as np


HABIT_STREAK_TOOL_SCHEMA = {
    "name": "habit_streak_tool",
    "description": (
        "Modelado de consistencia/adherencia a habitos financieros: "
        "streak_analysis (racha actual, racha mas larga, numero de "
        "rachas y tasa de cumplimiento dado un historico binario mes a "
        "mes), consistency_score (coeficiente de variacion del gasto "
        "mensual como proxy de disciplina, con score normalizado 0-100 = "
        "100/(1+CV)), habit_decay (curva de decaimiento exponencial de "
        "adherencia adherence(t)=adherence_0*exp(-t/tau), con vida media "
        "= tau*ln(2)), validate (suite de checks). Componente conductual: "
        "los umbrales/horizontes los provee quien llama."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "streak_analysis",
                    "consistency_score",
                    "habit_decay",
                    "validate",
                ],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


def _mode_streak_analysis(params):
    history = params.get("history")
    if not history or len(history) < 1:
        raise ValueError("history es requerido y no puede estar vacio (lista de 0/1)")

    vals = [int(v) for v in history]
    if any(v not in (0, 1) for v in vals):
        raise ValueError("history debe contener solo 0 (no cumplido) o 1 (cumplido)")

    longest_streak = 0
    current_run = 0
    n_streaks = 0
    prev = 0
    for v in vals:
        if v == 1:
            current_run += 1
            if prev == 0:
                n_streaks += 1
            longest_streak = max(longest_streak, current_run)
        else:
            current_run = 0
        prev = v

    # racha actual = racha activa al final del historico (0 si el ultimo mes fallo)
    current_streak = 0
    for v in reversed(vals):
        if v == 1:
            current_streak += 1
        else:
            break

    compliance_rate = sum(vals) / len(vals)

    return {
        "mode": "streak_analysis",
        "n_months": len(vals),
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "n_streaks": n_streaks,
        "compliance_rate": compliance_rate,
        "compliance_rate_pct": 100.0 * compliance_rate,
    }


def _mode_consistency_score(params):
    monthly_spending = params.get("monthly_spending")
    if not monthly_spending or len(monthly_spending) < 2:
        raise ValueError("monthly_spending requiere al menos 2 valores")

    arr = np.array(monthly_spending, dtype=float)
    mean = arr.mean()
    if mean <= 0:
        raise ValueError("el promedio de gasto debe ser > 0")

    std = arr.std(ddof=0)
    cv = std / mean
    score = 100.0 / (1.0 + cv)

    return {
        "mode": "consistency_score",
        "n_months": len(arr),
        "mean_spending": float(mean),
        "std_spending": float(std),
        "coefficient_of_variation": float(cv),
        "consistency_score": float(score),
    }


def _mode_habit_decay(params):
    adherence_0 = float(params.get("adherence_0", 1.0))
    if not (0.0 < adherence_0 <= 1.0):
        raise ValueError("adherence_0 debe estar en (0, 1]")

    horizon_months = int(params.get("horizon_months", 12))
    if horizon_months < 1:
        raise ValueError("horizon_months debe ser >= 1")

    if "tau" in params:
        tau = float(params["tau"])
        if tau <= 0:
            raise ValueError("tau debe ser > 0")
    elif "half_life_months" in params:
        half_life = float(params["half_life_months"])
        if half_life <= 0:
            raise ValueError("half_life_months debe ser > 0")
        tau = half_life / np.log(2.0)
    else:
        raise ValueError("se requiere tau o half_life_months")

    half_life_months = tau * np.log(2.0)

    months = np.arange(0, horizon_months + 1)
    curve = adherence_0 * np.exp(-months / tau)

    curve_list = [
        {"month": int(m), "adherence": float(a)}
        for m, a in zip(months, curve)
    ]

    return {
        "mode": "habit_decay",
        "adherence_0": adherence_0,
        "tau": float(tau),
        "half_life_months": float(half_life_months),
        "horizon_months": horizon_months,
        "curve": curve_list,
        "adherence_at_horizon": float(curve[-1]),
    }


def _mode_validate():
    checks = []

    # 1) streak_analysis: caso simple con racha final activa
    r1 = _mode_streak_analysis({"history": [1, 1, 0, 1, 1, 1]})
    checks.append({
        "name": "streak_current_and_longest",
        "current": r1["current_streak"], "longest": r1["longest_streak"], "n_streaks": r1["n_streaks"],
        "passed": r1["current_streak"] == 3 and r1["longest_streak"] == 3 and r1["n_streaks"] == 2,
    })

    # 2) streak_analysis: ultimo mes fallido da racha actual 0
    r2 = _mode_streak_analysis({"history": [1, 1, 1, 0]})
    checks.append({
        "name": "streak_ends_on_failure_current_zero",
        "current": r2["current_streak"], "longest": r2["longest_streak"],
        "passed": r2["current_streak"] == 0 and r2["longest_streak"] == 3,
    })

    # 3) streak_analysis: valores fuera de {0,1} lanzan excepcion
    try:
        _mode_streak_analysis({"history": [1, 2, 0]})
        raised3 = False
    except ValueError:
        raised3 = True
    checks.append({"name": "invalid_binary_value_raises", "passed": raised3})

    # 4) consistency_score: serie constante da CV=0 y score=100
    r4 = _mode_consistency_score({"monthly_spending": [500.0, 500.0, 500.0, 500.0]})
    checks.append({
        "name": "constant_spending_cv_zero_score_100",
        "cv": r4["coefficient_of_variation"], "score": r4["consistency_score"],
        "passed": abs(r4["coefficient_of_variation"]) < 1e-9 and abs(r4["consistency_score"] - 100.0) < 1e-9,
    })

    # 5) consistency_score: mas dispersion da CV mayor y score menor
    r5a = _mode_consistency_score({"monthly_spending": [500.0, 500.0, 500.0, 500.0]})
    r5b = _mode_consistency_score({"monthly_spending": [200.0, 800.0, 300.0, 700.0]})
    checks.append({
        "name": "higher_dispersion_lowers_score",
        "score_low_dispersion": r5a["consistency_score"], "score_high_dispersion": r5b["consistency_score"],
        "passed": r5b["consistency_score"] < r5a["consistency_score"],
    })

    # 6) habit_decay: t=0 da adherence_0 exacto
    r6 = _mode_habit_decay({"adherence_0": 0.8, "tau": 6.0, "horizon_months": 12})
    t0 = r6["curve"][0]
    checks.append({
        "name": "decay_at_t0_equals_adherence_0",
        "adherence_t0": t0["adherence"],
        "passed": abs(t0["adherence"] - 0.8) < 1e-9,
    })

    # 7) habit_decay: en t=half_life, adherence = adherence_0/2 (via half_life_months directo)
    r7 = _mode_habit_decay({"adherence_0": 1.0, "half_life_months": 6.0, "horizon_months": 6})
    t_half = r7["curve"][6]  # mes 6 = half_life exacta
    checks.append({
        "name": "decay_at_half_life_is_half",
        "adherence_at_half_life": t_half["adherence"], "half_life_months": r7["half_life_months"],
        "passed": abs(t_half["adherence"] - 0.5) < 1e-6 and abs(r7["half_life_months"] - 6.0) < 1e-6,
    })

    # 8) habit_decay: adherence_0 fuera de (0,1] lanza excepcion
    try:
        _mode_habit_decay({"adherence_0": 1.5, "tau": 6.0})
        raised8 = False
    except ValueError:
        raised8 = True
    checks.append({"name": "adherence_0_out_of_range_raises", "passed": raised8})

    # 9) habit_decay: sin tau ni half_life_months lanza excepcion
    try:
        _mode_habit_decay({"adherence_0": 0.9, "horizon_months": 6})
        raised9 = False
    except ValueError:
        raised9 = True
    checks.append({"name": "missing_tau_and_half_life_raises", "passed": raised9})

    # 10) modo invalido lanza excepcion
    try:
        compute_habit_streak("modo_invalido", {})
        invalid_raised = False
    except (KeyError, ValueError):
        invalid_raised = True
    checks.append({"name": "invalid_mode_raises", "passed": invalid_raised})

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_habit_streak(mode, params=None):
    params = params or {}

    if mode == "streak_analysis":
        return _mode_streak_analysis(params)
    elif mode == "consistency_score":
        return _mode_consistency_score(params)
    elif mode == "habit_decay":
        return _mode_habit_decay(params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(
            f"modo desconocido: {mode}. Use streak_analysis | consistency_score | "
            f"habit_decay | validate"
        )


try:
    from tool_registry import register_tool
    register_tool(
        name="habit_streak_tool",
        schema=HABIT_STREAK_TOOL_SCHEMA,
        handler=lambda args: compute_habit_streak(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    d = compute_habit_streak("validate")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de habit_streak_tool.py pasaron OK.")
