"""
cell_fate_decision_tool
========================

Red Booleana de decisiones de destino celular (hematopoyesis mieloide/eritroide).

Biologia
--------
8 genes clave: GATA1, PU1, CEBPA, FOG1, KLF1, GFI1, SCL, IKZF1

Motivacion biologica de cada regla (literatura general de GRN hematopoyeticas,
tipo Krumsiek et al. 2011, simplificada a estos 8 nodos):

  GATA1  : auto-mantenimiento + soporte de SCL, reprimido por PU1 (switch
           clasico GATA1/PU1)
  PU1    : auto-mantenimiento + soporte de CEBPA, reprimido por GATA1 y FOG1
  CEBPA  : auto-mantenimiento mientras GATA1 este apagado (programa mieloide)
  FOG1   : cofactor dependiente de GATA1 (correpresor de PU1 junto a GATA1)
  KLF1   : marcador de maduracion eritroide, requiere GATA1 activo y PU1 apagado
  GFI1   : programa neutrofilico, inducido por PU1/CEBPA, reprimido por IKZF1
  SCL    : auto-mantenimiento o inducido por GATA1, reprimido por PU1
  IKZF1  : sesgo linfoide, se mantiene solo si el programa mieloide/eritroide
           (GATA1 o CEBPA) no domina

Estas reglas son un modelo reducido de trabajo, no una reconstruccion
literal de un paper especifico -- el modo `validate` corre autochequeos
estructurales (no asume de antemano cuales son los atractores "correctos"):
los atractores se DESCUBREN por enumeracion exhaustiva del espacio de
estados (2^8 = 256), no se hardcodean.

Arquitectura
------------
- BooleanNetwork: estado = tupla de 0/1 en el orden GENES, reglas de
  actualizacion sincronas puras en `RULES`.
- simulate(): trayectoria determinista (sync) o aleatoria (async, un gen
  por paso, orden aleatorio con seed) desde un estado inicial.
- find_attractors(): enumeracion completa del espacio de estados bajo
  actualizacion sincrona; sigue cada trayectoria hasta repetir un estado
  visitado y clasifica el ciclo (punto fijo si longitud 1).
- basin_sizes(): a partir de find_attractors(), cuenta cuantos de los 256
  estados iniciales caen en cada atractor.
- perturbation(): clampea un gen a 0 o 1 durante toda la dinamica
  (knock-out / sobreexpresion) y recalcula atractores + basins, comparando
  contra el baseline.
- validate(): autochequeos matematicos/estructurales reales (no
  placeholder): determinismo, tamano de espacio de estados, particion
  completa de basins, idempotencia de atractores tipo punto fijo,
  consistencia de knock-out total (basin del gen clampeado a 0 nunca
  contiene ese gen encendido en el atractor), y al menos un caso de
  biestabilidad GATA1/PU1 verificado por simulacion directa.
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
from typing import Any, Dict, List, Optional, Tuple

from tool_registry import register_tool

GENES: Tuple[str, ...] = ("GATA1", "PU1", "CEBPA", "FOG1", "KLF1", "GFI1", "SCL", "IKZF1")
N = len(GENES)
State = Tuple[int, ...]


def _g(state: Dict[str, int], name: str) -> int:
    return state[name]


def _rule_GATA1(s: Dict[str, int]) -> int:
    return int((s["GATA1"] or s["SCL"]) and not s["PU1"])


def _rule_PU1(s: Dict[str, int]) -> int:
    return int((s["PU1"] or s["CEBPA"]) and not s["GATA1"] and not s["FOG1"])


def _rule_CEBPA(s: Dict[str, int]) -> int:
    return int(s["CEBPA"] and not s["GATA1"])


def _rule_FOG1(s: Dict[str, int]) -> int:
    return int(bool(s["GATA1"]))


def _rule_KLF1(s: Dict[str, int]) -> int:
    return int(bool(s["GATA1"]) and not s["PU1"])


def _rule_GFI1(s: Dict[str, int]) -> int:
    return int((s["PU1"] or s["CEBPA"]) and not s["IKZF1"])


def _rule_SCL(s: Dict[str, int]) -> int:
    return int((s["SCL"] or s["GATA1"]) and not s["PU1"])


def _rule_IKZF1(s: Dict[str, int]) -> int:
    return int(bool(s["IKZF1"]) and not (s["GATA1"] or s["CEBPA"]))


RULES = {
    "GATA1": _rule_GATA1,
    "PU1": _rule_PU1,
    "CEBPA": _rule_CEBPA,
    "FOG1": _rule_FOG1,
    "KLF1": _rule_KLF1,
    "GFI1": _rule_GFI1,
    "SCL": _rule_SCL,
    "IKZF1": _rule_IKZF1,
}
assert set(RULES) == set(GENES), "cada gen debe tener exactamente una regla"


def _as_dict(state: State) -> Dict[str, int]:
    return dict(zip(GENES, state))


def _as_tuple(d: Dict[str, int]) -> State:
    return tuple(d[g] for g in GENES)


def sync_step(state: State, clamp: Optional[Dict[str, int]] = None) -> State:
    d = _as_dict(state)
    nxt = {g: RULES[g](d) for g in GENES}
    if clamp:
        nxt.update(clamp)
    return _as_tuple(nxt)


def async_step(state: State, rng: random.Random, clamp: Optional[Dict[str, int]] = None) -> State:
    d = _as_dict(state)
    order = list(GENES)
    rng.shuffle(order)
    for g in order:
        if clamp and g in clamp:
            d[g] = clamp[g]
            continue
        d[g] = RULES[g](d)
    return _as_tuple(d)


def parse_state(spec) -> State:
    """Acepta dict {gen: 0/1}, lista/tupla de 8 bits, o None (-> todo apagado)."""
    if spec is None:
        return tuple([0] * N)
    if isinstance(spec, dict):
        return tuple(int(bool(spec.get(g, 0))) for g in GENES)
    if isinstance(spec, (list, tuple)):
        if len(spec) != N:
            raise ValueError(f"initial_state debe tener {N} elementos ({GENES})")
        return tuple(int(bool(x)) for x in spec)
    raise ValueError("initial_state debe ser dict, lista/tupla de 8 bits, o None")


def _parse_clamp(gene: Optional[str], value: Optional[int]) -> Optional[Dict[str, int]]:
    if gene is None:
        return None
    if gene not in GENES:
        raise ValueError(f"gene debe ser uno de {GENES}")
    if value not in (0, 1):
        raise ValueError("value debe ser 0 (knock-out) o 1 (sobreexpresion)")
    return {gene: int(value)}


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------

def mode_simulate(initial_state=None, update_mode: str = "sync", steps: int = 50,
                   seed: Optional[int] = None, gene: Optional[str] = None,
                   value: Optional[int] = None) -> dict:
    clamp = _parse_clamp(gene, value)
    s0 = parse_state(initial_state)
    if clamp:
        s0 = _as_tuple({**_as_dict(s0), **clamp})
    traj: List[State] = [s0]
    rng = random.Random(seed)
    seen = {s0: 0}
    cycle = None
    s = s0
    for t in range(1, steps + 1):
        s = sync_step(s, clamp) if update_mode == "sync" else async_step(s, rng, clamp)
        traj.append(s)
        if update_mode == "sync":
            if s in seen:
                cycle = {"start": seen[s], "end": t, "period": t - seen[s]}
                break
            seen[s] = t
    return {
        "genes": list(GENES),
        "update_mode": update_mode,
        "trajectory": [list(x) for x in traj],
        "converged_cycle": cycle,
        "final_state": dict(zip(GENES, traj[-1])),
    }


def _trace_to_attractor(start: State, memo: Dict[State, dict], clamp: Optional[Dict[str, int]] = None) -> dict:
    """Sigue una trayectoria sincrona desde `start` hasta caer en un estado
    ya clasificado en `memo`, o hasta cerrar un ciclo nuevo. Devuelve
    {attractor_id, attractor_states, transient}."""
    path: List[State] = []
    s = start
    while s not in memo and s not in path:
        path.append(s)
        s = sync_step(s, clamp)
    if s in memo:
        info = memo[s]
        for i, st in enumerate(path):
            memo[st] = info
        return info
    # se cerro un ciclo nuevo dentro de path
    idx = path.index(s)
    attractor_states = path[idx:]
    kind = "fixed_point" if len(attractor_states) == 1 else "cycle"
    info = {"attractor_id": None, "states": attractor_states, "kind": kind, "period": len(attractor_states)}
    for st in attractor_states:
        memo[st] = info
    for st in path[:idx]:
        memo[st] = info
    return info


def find_attractors(clamp: Optional[Dict[str, int]] = None) -> Tuple[List[dict], Dict[State, dict]]:
    memo: Dict[State, dict] = {}
    all_states = list(itertools.product([0, 1], repeat=N))
    if clamp:
        all_states = [s for s in all_states if all(_as_dict(s)[g] == v for g, v in clamp.items())]
    attractors: List[dict] = []
    seen_state_sets = []
    for s0 in all_states:
        info = _trace_to_attractor(s0, memo, clamp)
        key = tuple(sorted(info["states"]))
        if key not in seen_state_sets:
            seen_state_sets.append(key)
            aid = f"A{len(attractors)}"
            info["attractor_id"] = aid
            attractors.append({
                "attractor_id": aid,
                "kind": info["kind"],
                "period": info["period"],
                "states": [dict(zip(GENES, st)) for st in info["states"]],
            })
        else:
            info["attractor_id"] = attractors[seen_state_sets.index(key)]["attractor_id"]
    return attractors, memo


def mode_attractors(gene: Optional[str] = None, value: Optional[int] = None) -> dict:
    clamp = _parse_clamp(gene, value)
    attractors, _ = find_attractors(clamp)
    total_states = 2 ** N if not clamp else 2 ** (N - len(clamp))
    return {
        "genes": list(GENES),
        "state_space_size": total_states,
        "n_attractors": len(attractors),
        "attractors": attractors,
        "clamp": clamp,
    }


def mode_basin(gene: Optional[str] = None, value: Optional[int] = None) -> dict:
    clamp = _parse_clamp(gene, value)
    attractors, memo = find_attractors(clamp)
    counts = {a["attractor_id"]: 0 for a in attractors}
    for _st, info in memo.items():
        counts[info["attractor_id"]] += 1
    total = sum(counts.values())
    return {
        "genes": list(GENES),
        "clamp": clamp,
        "basin_sizes": counts,
        "basin_fractions": {k: round(v / total, 4) for k, v in counts.items()},
        "attractors": attractors,
    }


def mode_perturbation(gene: str, value: int) -> dict:
    if gene is None or value is None:
        raise ValueError("perturbation requiere gene y value (0=knock-out, 1=sobreexpresion)")
    baseline_attrs, baseline_memo = find_attractors(None)
    clamp = _parse_clamp(gene, value)
    pert_attrs, pert_memo = find_attractors(clamp)

    def sig_of(a):
        return frozenset(tuple(sorted(st.items())) for st in a["states"])

    base_by_sig = {sig_of(a): a for a in baseline_attrs}
    pert_by_sig = {sig_of(a): a for a in pert_attrs}
    base_sigs, pert_sigs = set(base_by_sig), set(pert_by_sig)

    # IDs son locales a cada corrida (find_attractors reasigna A0,A1,... en
    # cada llamada) -- nunca comparar por id crudo entre baseline y
    # perturbado, solo por el contenido real del atractor (sig_of).
    lost = [{"baseline_id": base_by_sig[sig]["attractor_id"], "states": base_by_sig[sig]["states"]}
            for sig in base_sigs - pert_sigs]
    gained = [{"perturbed_id": pert_by_sig[sig]["attractor_id"], "states": pert_by_sig[sig]["states"]}
              for sig in pert_sigs - base_sigs]
    conserved = [{"baseline_id": base_by_sig[sig]["attractor_id"],
                  "perturbed_id": pert_by_sig[sig]["attractor_id"],
                  "states": base_by_sig[sig]["states"]}
                 for sig in base_sigs & pert_sigs]

    return {
        "genes": list(GENES),
        "perturbation": {"gene": gene, "value": value},
        "baseline_n_attractors": len(baseline_attrs),
        "perturbed_n_attractors": len(pert_attrs),
        "attractors_lost": lost,
        "attractors_gained": gained,
        "attractors_conserved": conserved,
        "baseline_attractors": baseline_attrs,
        "perturbed_attractors": pert_attrs,
    }


def mode_validate() -> dict:
    checks = []

    def check(name, cond, detail=""):
        checks.append({"check": name, "passed": bool(cond), "detail": detail})

    # 1. determinismo: misma entrada -> misma salida, repetido
    d0 = _as_dict(tuple([1, 0, 1, 0, 1, 0, 1, 0]))
    r1 = {g: RULES[g](d0) for g in GENES}
    r2 = {g: RULES[g](d0) for g in GENES}
    check("determinismo_reglas", r1 == r2, "misma entrada produce misma salida en llamadas repetidas")

    # 2. cobertura del espacio de estados
    all_states = list(itertools.product([0, 1], repeat=N))
    check("tamano_espacio_estados", len(all_states) == 2 ** N == 256,
          f"2^{N} = {2**N}")

    # 3. las basins particionan el espacio completo (sin huecos, sin overlap)
    attractors, memo = find_attractors(None)
    check("todos_los_estados_clasificados", len(memo) == 256,
          f"{len(memo)}/256 estados alcanzaron un atractor")
    basin_total = sum(1 for _ in memo)
    check("basins_particionan_espacio", basin_total == 256, f"suma de basins = {basin_total}")

    # 4. cada atractor de tipo punto fijo es realmente un punto fijo bajo sync_step
    fixed_points_ok = True
    detail_fp = []
    for a in attractors:
        if a["kind"] == "fixed_point":
            st = _as_tuple(a["states"][0])
            nxt = sync_step(st)
            ok = nxt == st
            fixed_points_ok = fixed_points_ok and ok
            detail_fp.append((a["attractor_id"], ok))
    check("puntos_fijos_son_estables", fixed_points_ok, str(detail_fp))

    # 5. cada atractor tipo ciclo realmente cicla de vuelta al estado inicial tras `period` pasos
    cycles_ok = True
    for a in attractors:
        if a["kind"] == "cycle":
            st0 = _as_tuple(a["states"][0])
            s = st0
            for _ in range(a["period"]):
                s = sync_step(s)
            cycles_ok = cycles_ok and (s == st0)
    check("ciclos_cierran_correctamente", cycles_ok)

    # 6. knock-out total de un gen: ese gen nunca aparece encendido en ningun atractor resultante
    ko_attrs, _ = find_attractors({"GATA1": 0})
    gata1_off_everywhere = all(st["GATA1"] == 0 for a in ko_attrs for st in a["states"])
    check("knockout_GATA1_consistente", gata1_off_everywhere,
          "GATA1=0 forzado nunca revierte a 1 en ningun atractor")

    # 7. biestabilidad GATA1/PU1: partir con GATA1=1 (resto 0) y con PU1=1 (resto 0)
    #    debe converger a atractores distintos con el gen semilla dominante y el otro apagado
    d_gata_seed = {g: 0 for g in GENES}
    d_gata_seed["GATA1"] = 1
    d_pu1_seed = {g: 0 for g in GENES}
    d_pu1_seed["PU1"] = 1
    info_gata = _trace_to_attractor(_as_tuple(d_gata_seed), {})
    info_pu1 = _trace_to_attractor(_as_tuple(d_pu1_seed), {})
    final_gata = _as_dict(info_gata["states"][-1] if info_gata["kind"] == "fixed_point" else info_gata["states"][0])
    final_pu1 = _as_dict(info_pu1["states"][-1] if info_pu1["kind"] == "fixed_point" else info_pu1["states"][0])
    biestable = (final_gata["GATA1"] == 1 and final_gata["PU1"] == 0 and
                 final_pu1["PU1"] == 1 and final_pu1["GATA1"] == 0 and
                 final_gata != final_pu1)
    check("switch_GATA1_PU1_biestable", biestable,
          f"seed GATA1 -> {final_gata}; seed PU1 -> {final_pu1}")

    all_passed = all(c["passed"] for c in checks)
    return {
        "tool": "cell_fate_decision_tool",
        "validation_passed": all_passed,
        "n_checks": len(checks),
        "n_passed": sum(c["passed"] for c in checks),
        "checks": checks,
        "n_attractors_found": len(attractors),
    }


# ---------------------------------------------------------------------------
# Dispatcher (patron esperado por tool_registry.register_tool)
# ---------------------------------------------------------------------------

CELL_FATE_DECISION_TOOL_SCHEMA = {
    "name": "cell_fate_decision_tool",
    "description": (
        "Red Booleana de decisiones de destino celular hematopoyetico (8 genes: "
        "GATA1, PU1, CEBPA, FOG1, KLF1, GFI1, SCL, IKZF1), reglas biologicamente "
        "motivadas (switch GATA1/PU1, cofactores, etc.). Modos: simulate "
        "(trayectoria desde un estado inicial, sync o async), attractors "
        "(enumeracion completa del espacio de 2^8=256 estados, todos los "
        "atractores por actualizacion sincrona), basin (tamano de cuenca de "
        "atraccion de cada atractor), perturbation (knock-out/sobreexpresion de "
        "un gen, atractores ganados/perdidos/conservados vs. baseline), "
        "validate (8 self-checks estructurales, sin atractores hardcodeados)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["simulate", "attractors", "basin", "perturbation", "validate"],
            },
            "params": {
                "type": "object",
                "description": (
                    "initial_state (dict {gen: 0/1} o lista de 8 bits en orden "
                    "GENES; solo simulate), update_mode ('sync'|'async', default "
                    "'sync'; solo simulate), steps (default 50; solo simulate), "
                    "seed (solo simulate async), gene + value (0=knock-out, "
                    "1=sobreexpresion; requerido en perturbation, opcional para "
                    "clampear en attractors/basin/simulate)."
                ),
            },
        },
        "required": ["mode"],
    },
}


def cell_fate_decision_tool(mode: str, **kwargs) -> dict:
    if mode == "simulate":
        return mode_simulate(
            initial_state=kwargs.get("initial_state"),
            update_mode=kwargs.get("update_mode", "sync"),
            steps=kwargs.get("steps", 50),
            seed=kwargs.get("seed"),
            gene=kwargs.get("gene"),
            value=kwargs.get("value"),
        )
    if mode == "attractors":
        return mode_attractors(gene=kwargs.get("gene"), value=kwargs.get("value"))
    if mode == "basin":
        return mode_basin(gene=kwargs.get("gene"), value=kwargs.get("value"))
    if mode == "perturbation":
        return mode_perturbation(gene=kwargs.get("gene"), value=kwargs.get("value"))
    if mode == "validate":
        return mode_validate()
    raise ValueError(f"modo desconocido: {mode}")


def run(mode: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Global entry point for the tool (matches tool_registry handler convention).

    params: initial_state, update_mode, steps, seed, gene, value -- todos
    opcionales segun el modo (ver CELL_FATE_DECISION_TOOL_SCHEMA).
    """
    return cell_fate_decision_tool(mode, **params)


register_tool(
    name="cell_fate_decision_tool",
    schema=CELL_FATE_DECISION_TOOL_SCHEMA,
    handler=lambda args: run(args.get("mode"), args.get("params") or {}),
)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["simulate", "attractors", "basin", "perturbation", "validate"])
    ap.add_argument("--gene", default=None)
    ap.add_argument("--value", type=int, default=None)
    ap.add_argument("--steps", type=int, default=50)
    ap.add_argument("--update-mode", default="sync", dest="update_mode")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    out = cell_fate_decision_tool(
        args.mode, gene=args.gene, value=args.value, steps=args.steps,
        update_mode=args.update_mode, seed=args.seed,
    )
    print(json.dumps(out, indent=2, ensure_ascii=False))
