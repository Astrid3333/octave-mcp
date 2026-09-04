"""
kleinberg_burst_tool.py

octave-mcp tool: deteccion de rafagas jerarquicas (Kleinberg, "Bursty and
Hierarchical Structure in Streams", KDD 2002 / Data Min. Knowl. Discov. 2003).

Modela una secuencia de timestamps de eventos como un automata de estados
(0 = tasa base "reposo", 1..N-1 = estados de rafaga cada vez mas intensos),
donde el gap entre eventos consecutivos en el estado i sigue una exponencial
de tasa r_i = r0 * s^i. Encuentra, via programacion dinamica (tipo Viterbi),
la secuencia de estados que minimiza el costo total = -log-verosimilitud de
los gaps bajo cada estado + costo de transicion entre estados (penaliza subir
de nivel, gamma * log(n) por cada nivel que sube).

Modos:
  - detect_bursts : corre el algoritmo sobre una lista de timestamps y devuelve
                     los intervalos de rafaga detectados por nivel jerarquico.
  - validate       : self-test con datos sinteticos (actividad de fondo uniforme
                      + una rafaga sincronizada inyectada en una ventana corta),
                      verifica que la rafaga inyectada se detecte correctamente.

Convencion de registro: igual que el resto de octave-mcp — el handler recibe
el dict completo de tools/call; este modulo expone run(mode, params) y
register(reg).
"""

import math
import numpy as np

TOOL_NAME = "kleinberg_burst_tool"

TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["detect_bursts", "validate"],
        },
        "params": {
            "type": "object",
            "properties": {
                "timestamps": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Timestamps de eventos (segundos u otra unidad consistente), no necesariamente ordenados.",
                },
                "s": {
                    "type": "number",
                    "description": "Factor de escala entre tasas de estados consecutivos (default 2.0, valor clasico del paper).",
                },
                "gamma": {
                    "type": "number",
                    "description": "Coeficiente de costo de transicion hacia arriba (default 1.0). Mayor gamma = mas dificil entrar en rafaga (menos falsos positivos, rafagas mas cortas).",
                },
                "num_states": {
                    "type": "integer",
                    "description": "Numero de estados de rafaga por encima del reposo (default: se infiere automaticamente del rango de gaps, tipicamente 4-8).",
                },
            },
            "required": ["timestamps"],
        },
    },
    "required": ["mode"],
}


# ---------------------------------------------------------------------------
# Nucleo del algoritmo de Kleinberg
# ---------------------------------------------------------------------------

def _infer_num_states(gaps, s):
    """Elige N tal que la tasa del estado mas alto cubra el gap minimo observado
    (evita estados 'inutiles' que nunca se activan, y evita explosion combinatoria)."""
    r0 = 1.0 / np.mean(gaps)
    min_gap = max(np.min(gaps), 1e-12)
    max_rate_needed = 1.0 / min_gap
    if max_rate_needed <= r0:
        return 2
    n_states = int(math.ceil(math.log(max_rate_needed / r0) / math.log(s))) + 1
    return int(np.clip(n_states, 2, 64))


def _fit_kleinberg(timestamps, s=2.0, gamma=1.0, num_states=None):
    t = np.sort(np.asarray(timestamps, dtype=float))
    t = np.unique(t)  # eventos simultaneos colapsan (gap=0 no es valido para exponencial)
    n_events = len(t)
    if n_events < 3:
        raise ValueError("Se necesitan al menos 3 timestamps distintos para detectar rafagas.")

    gaps = np.diff(t)
    gaps = np.maximum(gaps, 1e-9)  # evita log(0) / division por cero
    n = len(gaps)

    total_span = t[-1] - t[0]
    r0 = (n_events - 1) / total_span  # tasa base: eventos por unidad de tiempo

    if num_states is None:
        num_states = _infer_num_states(gaps, s)
    rates = r0 * (s ** np.arange(num_states))  # rates[0] = r0 (reposo)

    # Costo de emision: -log f(gap | rate) para exponencial, f(x)=r*exp(-r*x)
    # cost(i, gap) = rate_i * gap - log(rate_i)
    emission_cost = rates[:, None] * gaps[None, :] - np.log(rates)[:, None]  # (num_states, n)

    # Costo de transicion: gamma * (j - i) * log(n) si j > i, 0 si j <= i
    transition_up_unit = gamma * math.log(n) if n > 1 else 0.0

    # Viterbi / DP hacia adelante
    dp = np.full((num_states, n), np.inf)
    backptr = np.zeros((num_states, n), dtype=int)
    dp[:, 0] = emission_cost[:, 0]  # estado inicial: sin costo de transicion previo

    for k in range(1, n):
        prev = dp[:, k - 1]  # (num_states,)
        # costo de venir de estado i a estado j: prev[i] + transition(i->j)
        # transition(i->j) = transition_up_unit * max(0, j - i)
        i_idx = np.arange(num_states)[:, None]
        j_idx = np.arange(num_states)[None, :]
        trans = transition_up_unit * np.maximum(0, j_idx - i_idx)
        candidates = prev[:, None] + trans  # (i, j)
        best_i = np.argmin(candidates, axis=0)  # para cada j, mejor i
        best_cost = candidates[best_i, np.arange(num_states)]
        dp[:, k] = best_cost + emission_cost[:, k]
        backptr[:, k] = best_i

    # backtrack desde el estado final de menor costo
    states = np.zeros(n, dtype=int)
    states[-1] = int(np.argmin(dp[:, -1]))
    for k in range(n - 1, 0, -1):
        states[k - 1] = backptr[states[k], k]

    return t, gaps, states, rates, r0


def _extract_burst_intervals(t, states, rates, gaps):
    """Convierte la secuencia de estados por gap en intervalos de rafaga
    contiguos (nivel > 0), con un 'peso' = reduccion acumulada de costo
    respecto de quedarse en reposo (que tan fuerte es la rafaga)."""
    n = len(states)
    bursts = []
    k = 0
    while k < n:
        if states[k] > 0:
            level = states[k]
            start_idx = k
            weight = 0.0
            while k < n and states[k] > 0:
                cur_level = states[k]
                cost_at_state = rates[cur_level] * gaps[k] - math.log(rates[cur_level])
                cost_at_rest = rates[0] * gaps[k] - math.log(rates[0])
                weight += max(0.0, cost_at_rest - cost_at_state)
                level = max(level, cur_level)
                k += 1
            end_idx = k
            bursts.append({
                "start_time": float(t[start_idx]),
                "end_time": float(t[end_idx]),
                "max_level": int(level),
                "n_events_in_burst": int(end_idx - start_idx + 1),
                "weight": float(weight),
            })
        else:
            k += 1
    bursts.sort(key=lambda b: b["weight"], reverse=True)
    return bursts


def detect_bursts(params):
    timestamps = params.get("timestamps")
    if not timestamps or len(timestamps) < 3:
        raise ValueError("params.timestamps requiere al menos 3 valores.")
    s = float(params.get("s", 2.0))
    gamma = float(params.get("gamma", 1.0))
    num_states = params.get("num_states")
    num_states = int(num_states) if num_states is not None else None

    t, gaps, states, rates, r0 = _fit_kleinberg(timestamps, s=s, gamma=gamma, num_states=num_states)
    bursts = _extract_burst_intervals(t, states, rates, gaps)

    return {
        "n_events": int(len(t)),
        "base_rate_r0": float(r0),
        "num_states_used": int(len(rates)),
        "state_rates": rates.tolist(),
        "n_bursts_detected": len(bursts),
        "bursts": bursts,
        "interpretation": (
            "Cada rafaga marca un tramo donde la frecuencia de eventos subio muy por "
            "encima de la tasa base y de forma sostenida (no un unico gap corto aislado). "
            "max_level alto + weight alto = coordinacion temporal fuerte, tipica de "
            "amplificacion sincronizada por granjas de bots o campañas coordinadas. "
            "Actividad humana organica raramente produce rafagas de nivel alto sostenidas."
        ),
    }


# ---------------------------------------------------------------------------
# validate — self-test
# ---------------------------------------------------------------------------

def _validate():
    rng = np.random.default_rng(7)
    checks = {}

    # 1) Actividad de fondo: proceso de Poisson homogeneo durante 10000s (tasa ~0.02 ev/s)
    #    + una rafaga sincronizada de 40 eventos en una ventana de 20s en torno a t=6000.
    background = np.sort(rng.uniform(0, 10000, size=200))
    burst_window = 6000 + rng.uniform(0, 20, size=40)
    all_events = np.sort(np.concatenate([background, burst_window]))

    res = detect_bursts({"timestamps": all_events.tolist(), "s": 2.0, "gamma": 1.0})
    found_burst_in_window = any(
        b["start_time"] <= 6010 <= b["end_time"] and b["max_level"] >= 1
        for b in res["bursts"]
    )
    checks["injected_burst_detected"] = {
        "n_bursts_detected": res["n_bursts_detected"],
        "found_in_expected_window": found_burst_in_window,
        "passed": found_burst_in_window,
    }

    # 2) Caso negativo: puramente Poisson homogeneo sin rafaga inyectada, tasa constante.
    #    No deberia haber rafagas de nivel alto (weight grande) — algo de ruido de nivel
    #    bajo es aceptable, así que exigimos que no haya nivel > 1 dominante.
    pure_poisson = np.sort(rng.uniform(0, 10000, size=200))
    res_neg = detect_bursts({"timestamps": pure_poisson.tolist(), "s": 2.0, "gamma": 1.0})
    max_level_neg = max((b["max_level"] for b in res_neg["bursts"]), default=0)
    checks["no_spurious_high_level_burst"] = {
        "n_bursts_detected": res_neg["n_bursts_detected"],
        "max_level_seen": max_level_neg,
        "passed": max_level_neg <= 1,
    }

    # 3) Sanity check: r0 estimado debe ser cercano a la tasa teorica de fondo (200 eventos / 10000s = 0.02)
    r0_err = abs(res_neg["base_rate_r0"] - 0.02)
    checks["base_rate_sane"] = {
        "estimated_r0": res_neg["base_rate_r0"],
        "expected_r0": 0.02,
        "abs_error": r0_err,
        "passed": r0_err < 0.01,
    }

    all_passed = all(c["passed"] for c in checks.values())
    return {
        "validation_passed": bool(all_passed),
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

def run(mode, params):
    params = params or {}
    if mode == "detect_bursts":
        return detect_bursts(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"Modo desconocido: {mode!r}. Modos validos: detect_bursts, validate.")


def register(reg):
    """Llamar desde server.py: from tools.kleinberg_burst_tool import register; register(tool_registry)"""
    reg.register_tool(TOOL_NAME, TOOL_SCHEMA, lambda args: run(args.get("mode"), args.get("params") or {}))


if __name__ == "__main__":
    import json
    print(json.dumps(run("validate", {}), indent=2, ensure_ascii=False))
