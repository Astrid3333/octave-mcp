"""
systemic_risk_tool.py

Contagio financiero en una red de exposiciones interbancarias, distinto
de econometrics_tool/financial_math_tool (series de tiempo, sin
estructura de red) y de cascading_failure_tool (carga fisica en
infraestructura, no capital/pasivos). Implementa el mecanismo clasico
de Eisenberg & Noe (2001, "Systemic Risk in Financial Systems"): cada
banco tiene capital propio (equity) y pasivos interbancarios con otros
bancos (matriz de exposiciones); si el capital de un banco cae a cero o
negativo por perdidas en sus contrapartes, el banco quiebra y transmite
perdidas (via loss-given-default) a sus acreedores, quienes a su vez
pueden quebrar -- el mismo mecanismo cualitativo de cascading_failure
pero con la contabilidad especifica de un balance bancario en vez de
carga/capacidad de red.

Modelo de red: cada banco i tiene equity E_i (capital propio) y una
matriz de exposiciones interbancarias L_ij (cuanto el banco i le debe
al banco j). Al recibir un shock inicial (perdida en activos externos
de algunos bancos), el capital de esos bancos cae; si un banco queda
con capital <= 0, quiebra, y sus acreedores (bancos que le prestaron)
pierden una fraccion (1-recovery_rate) de esa exposicion, reduciendo su
propio capital -- lo que puede disparar mas quiebras (contagio).

Modos:
  - interbank_contagion: corre la cascada de default de Eisenberg-Noe
    (version simplificada por rondas, sin resolver el punto fijo
    completo de pagos de clearing) sobre una red de exposiciones
    generada sinteticamente, con shock inicial en un subconjunto de
    bancos.
  - protection_sensitivity: mismo mecanismo, barriendo el nivel de
    capital/proteccion inicial (buffer de capital como multiplo de la
    exposicion total) para mostrar como mas capital reduce el contagio
    -- analogo financiero de alpha en cascading_failure_tool.
  - validate: chequeos contra el comportamiento conocido del modelo.
"""

import numpy as np


def _generate_interbank_network(n_banks, connectivity, mean_exposure,
                                 capital_buffer, seed):
    """Genera una red sintetica de exposiciones interbancarias.

    connectivity: probabilidad de que exista un prestamo i->j (i le
    presto a j, o sea L_ij = exposicion de i hacia j en el sentido de
    Eisenberg-Noe donde el default de j hace perder a i).
    capital_buffer: equity de cada banco = capital_buffer * (exposicion
    total que ese banco tiene HACIA afuera, es decir cuanto le deben);
    un buffer alto significa que el banco tiene mucho capital propio
    relativo a lo que otros bancos le deben, asi que puede absorber
    perdidas de contraparte sin quebrar.
    """
    rng = np.random.default_rng(seed)
    exposures = np.zeros((n_banks, n_banks))
    for i in range(n_banks):
        for j in range(n_banks):
            if i != j and rng.random() < connectivity:
                exposures[i, j] = rng.exponential(mean_exposure)

    # equity de cada banco proporcional a lo que le deben (sus activos
    # interbancarios), con el buffer como margen de seguridad
    receivables = exposures.sum(axis=0)  # lo que cada banco j tiene por cobrar
    equity = capital_buffer * np.maximum(receivables, 1.0)

    return exposures, equity


def _run_contagion(exposures, equity, initial_shock, recovery_rate=0.4,
                    max_rounds=200):
    """Cascada de default por rondas: un banco quiebra si su capital
    efectivo (equity - perdidas acumuladas de contrapartes en default)
    cae a <= 0. Al quebrar, transmite (1-recovery_rate) de lo que le
    debia a cada acreedor, proporcional a la exposicion de ese acreedor
    hacia el banco quebrado.
    """
    n = len(equity)
    capital = equity.astype(float).copy() - np.asarray(initial_shock, dtype=float)
    defaulted = capital <= 0
    default_round = np.where(defaulted, 0, -1)

    history = [int(defaulted.sum())]
    rnd = 0
    newly_defaulted = np.where(defaulted)[0].tolist()

    while newly_defaulted and rnd < max_rounds:
        rnd += 1
        loss_transmitted = np.zeros(n)
        for j in newly_defaulted:
            # bancos i que le prestaron al banco j (exposures[i, j] > 0)
            # pierden (1-recovery_rate) de esa exposicion
            creditor_losses = exposures[:, j] * (1.0 - recovery_rate)
            loss_transmitted += creditor_losses

        capital -= loss_transmitted
        newly_defaulted = [i for i in range(n) if (not defaulted[i]) and capital[i] <= 0]
        for i in newly_defaulted:
            defaulted[i] = True
            default_round[i] = rnd
        history.append(int(defaulted.sum()))

    return {
        "defaulted": defaulted,
        "n_defaulted": int(defaulted.sum()),
        "fraction_defaulted": float(defaulted.sum() / n),
        "rounds": rnd,
        "history": history,
        "final_capital": capital.tolist(),
    }


def _mode_interbank_contagion(params):
    n_banks = int(params.get("n_banks", 40))
    connectivity = float(params.get("connectivity", 0.15))
    mean_exposure = float(params.get("mean_exposure", 10.0))
    capital_buffer = float(params.get("capital_buffer", 0.5))
    recovery_rate = float(params.get("recovery_rate", 0.4))
    seed = int(params.get("seed", 42))
    n_shocked = int(params.get("n_shocked", 1))
    shock_size_fraction = float(params.get("shock_size_fraction", 1.0))

    exposures, equity = _generate_interbank_network(
        n_banks, connectivity, mean_exposure, capital_buffer, seed
    )

    rng = np.random.default_rng(seed + 1)
    shocked_banks = rng.choice(n_banks, size=min(n_shocked, n_banks), replace=False)
    initial_shock = np.zeros(n_banks)
    for b in shocked_banks:
        initial_shock[b] = shock_size_fraction * equity[b]

    result = _run_contagion(exposures, equity, initial_shock,
                             recovery_rate=recovery_rate)

    return {
        "mode": "interbank_contagion",
        "n_banks": n_banks,
        "capital_buffer": capital_buffer,
        "recovery_rate": recovery_rate,
        "shocked_banks": shocked_banks.tolist(),
        "n_defaulted": result["n_defaulted"],
        "fraction_defaulted": result["fraction_defaulted"],
        "contagion_rounds": result["rounds"],
        "default_history": result["history"],
        "total_interbank_exposure": float(exposures.sum()),
        "note": (
            "shock inicial elimina shock_size_fraction del capital propio "
            "de n_shocked bancos elegidos al azar; el contagio se propaga "
            "solo via la red de exposiciones interbancarias (perdida de "
            "contraparte), no hay shock adicional a otros bancos. "
            "recovery_rate=0.4 significa que un acreedor recupera 40% de "
            "lo que le debia un banco en default (60% de perdida neta)."
        ),
    }


def _mode_protection_sensitivity(params):
    n_banks = int(params.get("n_banks", 40))
    connectivity = float(params.get("connectivity", 0.15))
    mean_exposure = float(params.get("mean_exposure", 10.0))
    recovery_rate = float(params.get("recovery_rate", 0.4))
    seed = int(params.get("seed", 42))
    n_shocked = int(params.get("n_shocked", 3))
    buffer_range = params.get("buffer_range", [0.05, 0.1, 0.2, 0.3, 0.5, 0.8, 1.2, 2.0])

    curve = []
    for buf in buffer_range:
        exposures, equity = _generate_interbank_network(
            n_banks, connectivity, mean_exposure, float(buf), seed
        )
        rng = np.random.default_rng(seed + 1)
        shocked_banks = rng.choice(n_banks, size=min(n_shocked, n_banks), replace=False)
        initial_shock = np.zeros(n_banks)
        for b in shocked_banks:
            initial_shock[b] = equity[b]  # shock total en los bancos elegidos

        result = _run_contagion(exposures, equity, initial_shock,
                                 recovery_rate=recovery_rate)
        curve.append({
            "capital_buffer": float(buf),
            "fraction_defaulted": result["fraction_defaulted"],
            "n_defaulted": result["n_defaulted"],
        })

    return {
        "mode": "protection_sensitivity",
        "n_banks": n_banks,
        "n_shocked": n_shocked,
        "curve": curve,
        "note": (
            "analogo financiero de barrer alpha en cascading_failure_tool: "
            "mas capital_buffer (mas capital propio relativo a lo que le "
            "deben a un banco) deberia reducir el contagio, mismo shock "
            "inicial y misma red base."
        ),
    }


def _validate():
    checks = {}
    errors = []

    # 1) Sin exposiciones interbancarias (red vacia), un shock nunca se
    #    contagia -- solo quiebran los bancos directamente shockeados.
    n = 20
    exposures_empty = np.zeros((n, n))
    equity = np.full(n, 100.0)
    shock = np.zeros(n)
    shock[0] = 150.0  # mas que su capital, deberia quebrar
    r_empty = _run_contagion(exposures_empty, equity, shock, recovery_rate=0.4)
    no_contagion_without_links = (r_empty["n_defaulted"] == 1)
    checks["no_contagion_without_interbank_links"] = bool(no_contagion_without_links)
    if not no_contagion_without_links:
        errors.append(f"sin exposiciones interbancarias igual se contagio a {r_empty['n_defaulted']} bancos")

    # 2) Con recovery_rate=1.0 (recuperacion total, sin perdida neta
    #    para acreedores), el default de un banco no debilita a nadie
    #    mas -- no hay contagio aunque haya exposiciones.
    exposures_dense, equity_dense = _generate_interbank_network(30, 0.3, 8.0, 0.4, seed=1)
    shock_dense = np.zeros(30)
    shock_dense[0] = equity_dense[0] * 1.5
    r_full_recovery = _run_contagion(exposures_dense, equity_dense, shock_dense, recovery_rate=1.0)
    no_contagion_full_recovery = (r_full_recovery["n_defaulted"] == 1)
    checks["no_contagion_with_full_recovery_rate"] = bool(no_contagion_full_recovery)
    if not no_contagion_full_recovery:
        errors.append(f"con recovery_rate=1.0 igual hubo contagio a {r_full_recovery['n_defaulted']} bancos")

    # 3) Monotonicidad en capital_buffer: mas capital propio -> igual o
    #    menos contagio, mismo shock/seed.
    sens = _mode_protection_sensitivity({
        "n_banks": 40, "seed": 3, "n_shocked": 3,
        "buffer_range": [0.05, 0.3, 1.0, 3.0],
    })
    fracs = [c["fraction_defaulted"] for c in sens["curve"]]
    monotonic_or_flat = all(fracs[i] >= fracs[i + 1] - 1e-9 for i in range(len(fracs) - 1))
    checks["contagion_monotonic_nonincreasing_in_buffer"] = bool(monotonic_or_flat)
    checks["fraction_defaulted_by_buffer"] = fracs
    if not monotonic_or_flat:
        errors.append(f"contagion no decrece monotonicamente con capital_buffer: {fracs}")

    # 4) A muy bajo capital_buffer con red densa, el contagio afecta a
    #    mas de un banco (mecanismo de propagacion real, no solo el
    #    shock inicial).
    low_buffer_spreads = (sens["curve"][0]["n_defaulted"] > 3)
    checks["low_buffer_shows_real_contagion"] = bool(low_buffer_spreads)
    checks["n_defaulted_lowest_buffer"] = sens["curve"][0]["n_defaulted"]
    if not low_buffer_spreads:
        errors.append(f"con buffer bajo solo quebraron {sens['curve'][0]['n_defaulted']} bancos (deberia superar los 3 shockeados por contagio)")

    # 5) Perdida total transmitida nunca supera la exposicion total en
    #    default (conservacion: no se puede perder mas de lo que se
    #    debia). Chequeo indirecto: el capital final de bancos NO en
    #    default siempre es >= 0 (si fuera negativo tambien habrian
    #    quebrado, por definicion del bucle de contagio).
    exposures_c, equity_c = _generate_interbank_network(25, 0.2, 5.0, 0.5, seed=9)
    shock_c = np.zeros(25)
    shock_c[[0, 1]] = equity_c[[0, 1]]
    r_c = _run_contagion(exposures_c, equity_c, shock_c, recovery_rate=0.3)
    survivors_capital = [r_c["final_capital"][i] for i in range(25) if not r_c["defaulted"][i]]
    survivors_solvent = all(c > 0 for c in survivors_capital)
    checks["surviving_banks_remain_solvent"] = bool(survivors_solvent)
    if not survivors_solvent:
        errors.append("hay bancos marcados como no-default con capital final <= 0 (bug de logica de contagio)")

    # 6) Reproducibilidad: misma seed, mismo resultado exacto.
    r_a = _mode_interbank_contagion({"n_banks": 30, "seed": 55, "capital_buffer": 0.3})
    r_b = _mode_interbank_contagion({"n_banks": 30, "seed": 55, "capital_buffer": 0.3})
    reproducible = (r_a["default_history"] == r_b["default_history"])
    checks["reproducible_with_same_seed"] = bool(reproducible)
    if not reproducible:
        errors.append("contagio no reproducible con la misma seed")

    return {
        "mode": "validate",
        "validation_passed": len(errors) == 0,
        "checks": checks,
        "errors": errors,
    }


def compute_systemic_risk_tool(mode, params=None):
    params = params or {}
    if mode == "interbank_contagion":
        return _mode_interbank_contagion(params)
    elif mode == "protection_sensitivity":
        return _mode_protection_sensitivity(params)
    elif mode == "validate":
        return _validate()
    else:
        return {
            "error": (
                f"Modo desconocido: {mode}. Modos validos: "
                "interbank_contagion, protection_sensitivity, validate."
            )
        }


SYSTEMIC_RISK_TOOL_SCHEMA = {
    "name": "systemic_risk_tool",
    "description": (
        "Contagio financiero en red de exposiciones interbancarias "
        "(mecanismo de Eisenberg & Noe 2001, version simplificada por "
        "rondas): cada banco tiene capital propio y deudas/creditos con "
        "otros bancos; el default de uno transmite perdidas a sus "
        "acreedores (proporcional a la exposicion, neta de "
        "recovery_rate), que pueden quebrar a su vez. Distinto de "
        "cascading_failure_tool (carga fisica de red de infraestructura, "
        "no balance bancario) y de econometrics_tool/financial_math_tool "
        "(series de tiempo sin estructura de red). "
        "mode=interbank_contagion corre un shock inicial sobre bancos "
        "elegidos y devuelve la cascada de defaults resultante. "
        "mode=protection_sensitivity barre el nivel de capital propio "
        "(capital_buffer) para mostrar como mas capital reduce el "
        "contagio, analogo financiero de alpha en cascading_failure_tool."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["interbank_contagion", "protection_sensitivity", "validate"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "n_banks": {"type": "integer", "description": "Numero de bancos en la red (default 40)"},
                    "connectivity": {"type": "number", "description": "Probabilidad de exposicion entre cada par de bancos (default 0.15)"},
                    "mean_exposure": {"type": "number", "description": "Exposicion promedio por prestamo interbancario (default 10.0)"},
                    "capital_buffer": {"type": "number", "description": "Capital propio como multiplo de lo que le deben al banco, solo interbank_contagion (default 0.5)"},
                    "recovery_rate": {"type": "number", "description": "Fraccion recuperada por acreedores de un banco en default, 0-1 (default 0.4)"},
                    "n_shocked": {"type": "integer", "description": "Numero de bancos con shock inicial (default 1-3 segun modo)"},
                    "shock_size_fraction": {"type": "number", "description": "Fraccion del capital propio perdida en el shock inicial, solo interbank_contagion (default 1.0)"},
                    "buffer_range": {"type": "array", "description": "Valores de capital_buffer a barrer, solo protection_sensitivity"},
                    "seed": {"type": "integer", "description": "Semilla RNG (default 42)"},
                },
            },
        },
        "required": ["mode"],
    },
}

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool(
    "systemic_risk_tool",
    SYSTEMIC_RISK_TOOL_SCHEMA,
    lambda args, _f=compute_systemic_risk_tool: _f(**args),
)
