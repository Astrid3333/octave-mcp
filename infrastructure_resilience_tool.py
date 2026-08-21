"""
infrastructure_resilience_tool.py

Complementa a critical_infrastructure_tool.py (analisis de redes por grafos:
N-1, cascada por sobrecarga, centralidad de Brandes) con el enfoque de
ingenieria sismica/estructural: curvas de fragilidad lognormales,
propagacion de fallos en cascada sobre una red de dependencias, curvas de
restauracion de funcionalidad, e indice de resiliencia del sistema
(Bruneau et al. 2003). Autocontenido, sin imports cruzados a otras tools.

Precision: la CDF normal se calcula via math.erf (forma cerrada exacta,
sin aproximaciones racionales tipo Abramowitz-Stegun), y la perdida de
resiliencia usa la primitiva analitica exacta de la curva de restauracion
en vez de solo integracion numerica.
"""

import math

TOOL_NAME = "infrastructure_resilience_tool"

INFRASTRUCTURE_RESILIENCE_TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Evaluacion de infraestructura critica ante desastres: curvas de "
        "fragilidad lognormales (genericas, el usuario pasa sus propios "
        "parametros theta/beta por estado de dano en vez de una tabla "
        "hardcodeada por norma/pais), propagacion de fallos en cascada "
        "sobre una red de dependencias, curvas de restauracion de "
        "funcionalidad en el tiempo, e indice de resiliencia del sistema "
        "(perdida de resiliencia de Bruneau et al. 2003)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "fragility_assessment",
                    "network_cascading_failure",
                    "restoration_curve",
                    "system_resilience_index",
                    "validate",
                ],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


def _norm_cdf(x):
    """CDF exacta de la normal estandar via math.erf."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _fragility_assessment(params):
    im = params["im"]
    damage_states = params["damage_states"]  # [{"name","theta","beta"}, ...]
    results = []
    for ds in damage_states:
        theta = ds["theta"]
        beta = ds["beta"]
        if im <= 0 or theta <= 0 or beta <= 0:
            raise ValueError("im, theta y beta deben ser > 0 (escala lognormal)")
        z = math.log(im / theta) / beta
        p = _norm_cdf(z)
        results.append({
            "name": ds.get("name", ""),
            "theta": theta,
            "beta": beta,
            "p_exceed": p,
        })
    return {"im": im, "damage_states": results}


def _network_cascading_failure(params):
    nodes = params["nodes"]
    dependencies = params.get("dependencies", {})
    backups = set(params.get("backups", []))
    initial_failed = set(params["initial_failed"])

    failed = set(initial_failed)
    changed = True
    steps = 0
    while changed:
        changed = False
        steps += 1
        for n in nodes:
            if n in failed or n in backups:
                continue
            deps = dependencies.get(n, [])
            if deps and all(d in failed for d in deps):
                failed.add(n)
                changed = True
        if steps > len(nodes) + 5:
            break

    return {
        "nodes_total": len(nodes),
        "failed_initial": sorted(initial_failed),
        "failed_final": sorted(failed),
        "survived": sorted(set(nodes) - failed),
        "propagation_steps": steps,
    }


def _q_of_t(t, q0, tau):
    return 1.0 - (1.0 - q0) * math.exp(-t / tau)


def _restoration_curve(params):
    q0 = params["q0"]
    tau = params["tau"]
    times = params["times"]
    if not (0.0 <= q0 <= 1.0):
        raise ValueError("q0 debe estar en [0,1]")
    if tau <= 0:
        raise ValueError("tau debe ser > 0")
    curve = []
    for t in times:
        if t < 0:
            raise ValueError("t debe ser >= 0")
        curve.append({"t": t, "q": _q_of_t(t, q0, tau)})
    return {"q0": q0, "tau": tau, "curve": curve}


def _system_resilience_index(params):
    q0 = params["q0"]
    tau = params["tau"]
    t_recovery = params["t_recovery"]
    n_steps = params.get("n_steps", 2000)
    if not (0.0 <= q0 <= 1.0):
        raise ValueError("q0 debe estar en [0,1]")
    if tau <= 0 or t_recovery <= 0:
        raise ValueError("tau y t_recovery deben ser > 0")

    # Primitiva analitica exacta de integral(1 - Q(t)) dt entre 0 y t_recovery:
    # integral (1-q0)*exp(-t/tau) dt = -(1-q0)*tau*exp(-t/tau)
    # evaluado en [0, t_recovery] = (1-q0)*tau*(1 - exp(-t_recovery/tau))
    resilience_loss_exact = (1.0 - q0) * tau * (1.0 - math.exp(-t_recovery / tau))

    # Cruce-check independiente: integracion numerica (trapecio)
    h = t_recovery / n_steps
    prev = 1.0 - _q_of_t(0.0, q0, tau)
    total = 0.0
    for i in range(1, n_steps + 1):
        t = i * h
        curr = 1.0 - _q_of_t(t, q0, tau)
        total += (prev + curr) / 2.0 * h
        prev = curr

    return {
        "q0": q0,
        "tau": tau,
        "t_recovery": t_recovery,
        "resilience_loss_exact": resilience_loss_exact,
        "resilience_loss_numeric_trapezoid": total,
        "resilience_index": 1.0 - resilience_loss_exact / t_recovery,
    }


def _validate():
    checks = []

    # 1) En IM = theta, P debe ser exactamente 0.5 (definicion de mediana)
    r = _fragility_assessment({
        "im": 0.4,
        "damage_states": [{"name": "moderado", "theta": 0.4, "beta": 0.6}],
    })
    p_theta = r["damage_states"][0]["p_exceed"]
    checks.append({
        "name": "fragility_median_gives_p_half_exact",
        "computed": p_theta,
        "expected": 0.5,
        "passed": abs(p_theta - 0.5) < 1e-12,
    })

    # 2) Fragilidad monotona creciente en IM
    p_low = _fragility_assessment({"im": 0.1, "damage_states": [{"theta": 0.4, "beta": 0.6}]})["damage_states"][0]["p_exceed"]
    p_high = _fragility_assessment({"im": 2.0, "damage_states": [{"theta": 0.4, "beta": 0.6}]})["damage_states"][0]["p_exceed"]
    checks.append({
        "name": "fragility_monotonic_increasing_in_im",
        "p_low": p_low, "p_high": p_high,
        "passed": p_low < p_high,
    })

    # 3) Nodo sin dependencias y fuera del set inicial nunca cae
    r_no_dep = _network_cascading_failure({
        "nodes": ["A", "B", "C"],
        "dependencies": {"B": ["A"]},
        "initial_failed": ["A"],
        "backups": [],
    })
    checks.append({
        "name": "node_without_deps_and_not_seeded_never_falls",
        "failed_final": r_no_dep["failed_final"],
        "passed": "C" not in r_no_dep["failed_final"],
    })

    # 4) Cascada real: B depende solo de A, A cae -> B debe caer
    checks.append({
        "name": "dependent_node_falls_when_sole_dependency_fails",
        "failed_final": r_no_dep["failed_final"],
        "passed": "B" in r_no_dep["failed_final"],
    })

    # 5) Backup evita la caida en cascada
    r_backup = _network_cascading_failure({
        "nodes": ["A", "B"],
        "dependencies": {"B": ["A"]},
        "initial_failed": ["A"],
        "backups": ["B"],
    })
    checks.append({
        "name": "backup_node_survives_dependency_loss",
        "failed_final": r_backup["failed_final"],
        "passed": "B" not in r_backup["failed_final"],
    })

    # 6) Restauracion en t=0 da Q0 exacto
    rc = _restoration_curve({"q0": 0.3, "tau": 10.0, "times": [0.0, 1000.0]})
    checks.append({
        "name": "restoration_at_t0_equals_q0_exact",
        "computed": rc["curve"][0]["q"], "expected": 0.3,
        "passed": abs(rc["curve"][0]["q"] - 0.3) < 1e-12,
    })

    # 7) Restauracion a t grande tiende a 1
    checks.append({
        "name": "restoration_at_large_t_approaches_one",
        "computed": rc["curve"][1]["q"],
        "passed": abs(rc["curve"][1]["q"] - 1.0) < 1e-9,
    })

    # 8) Resiliencia sin dano (q0=1) da perdida exactamente 0
    sri0 = _system_resilience_index({"q0": 1.0, "tau": 5.0, "t_recovery": 20.0})
    checks.append({
        "name": "no_damage_gives_zero_resilience_loss",
        "computed": sri0["resilience_loss_exact"], "expected": 0.0,
        "passed": abs(sri0["resilience_loss_exact"]) < 1e-12,
    })

    # 9) Primitiva analitica exacta vs integracion numerica coinciden (cruce-check)
    sri1 = _system_resilience_index({"q0": 0.2, "tau": 8.0, "t_recovery": 40.0, "n_steps": 5000})
    diff = abs(sri1["resilience_loss_exact"] - sri1["resilience_loss_numeric_trapezoid"])
    checks.append({
        "name": "exact_primitive_matches_numeric_trapezoid",
        "exact": sri1["resilience_loss_exact"],
        "numeric": sri1["resilience_loss_numeric_trapezoid"],
        "abs_diff": diff,
        "passed": diff < 1e-3,
    })

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "validation_passed": all_passed}


def compute_infrastructure_resilience(mode, params=None):
    params = params or {}
    if mode == "fragility_assessment":
        return _fragility_assessment(params)
    elif mode == "network_cascading_failure":
        return _network_cascading_failure(params)
    elif mode == "restoration_curve":
        return _restoration_curve(params)
    elif mode == "system_resilience_index":
        return _system_resilience_index(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"mode desconocido: {mode}")
try:
    from tool_registry import register_tool
    register_tool(
        name="infrastructure_resilience_tool",
        schema=INFRASTRUCTURE_RESILIENCE_TOOL_SCHEMA,
        handler=lambda args: compute_infrastructure_resilience(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    d = compute_infrastructure_resilience("validate", {})
    print(json.dumps(d, indent=2, ensure_ascii=False))
    assert d["validation_passed"], "Validacion fallo, ver detalle arriba"
    print("\nTodos los chequeos de infrastructure_resilience_tool.py pasaron OK.")
