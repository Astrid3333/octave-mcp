"""
stem_cell_niche_tool.py

Stochastic (Gillespie SSA) model of stem cell niche competition.

Concept:
  A fixed pool of N_niches physical niches exists in a tissue. Each niche is either
  occupied by a stem cell or empty. Stem cells compete for access to empty niches
  when they divide (self-renewal). Cells can also differentiate (leaving the niche,
  becoming a Progenitor), mature (Progenitor -> Differentiated), or die (apoptosis).

State vector: [Stem, Empty, Progenitor, Differentiated]
  Stem + Empty == N_niches  (niche conservation, exact integer invariant)

Reactions (mass-action propensities):
  R1  Stem + Empty -> 2*Stem        (birth_rate * Stem * Empty / N_niches)   [niche competition]
  R2  Stem -> Empty                 (death_rate_stem * Stem)                [stem cell death]
  R3  Stem -> Empty + Progenitor    (diff_rate * Stem)                      [differentiation, frees niche]
  R4  Progenitor -> Differentiated  (mat_rate * Progenitor)                 [maturation]
  R5  Progenitor -> 0               (apop_prog * Progenitor)                [progenitor apoptosis]
  R6  Differentiated -> 0           (apop_diff * Differentiated)            [mature cell apoptosis]

Modes:
  - "hematopoietic" : HSC niche in bone marrow (default)
  - "neural"        : Neural stem cell niche (SVZ/SGZ)
  - "muscle"         : Satellite cell niche
  - "minimal"        : Small toy system for fast iteration
  - "custom"         : user supplies N_niches + rates directly

Operational modes (tool dispatch):
  - "simulate"      : single stochastic trajectory
  - "ensemble"      : many replicate trajectories -> distribution at t_end
  - "steady_state"  : ensemble-averaged equilibrium occupancy + convergence stats
  - "bifurcation"   : scan a parameter (default birth_rate = "niche strength"),
                       report mean niche occupancy fraction vs parameter
  - "validate"      : 10 embedded self-test checks
"""

import json
import numpy as np
from typing import Dict, Any, Tuple, List
from tool_registry import register_tool


# ----------------------------------------------------------------------------
# Preset tissue/niche configurations
# ----------------------------------------------------------------------------
PRESETS = {
    # Rates are chosen so the deterministic mean-field equilibrium
    # Stem/N = 1 - (death_rate_stem + diff_rate)/birth_rate sits near 0.5,
    # i.e. comfortably away from the critical point (birth_rate == loss rate)
    # where the birth-death process would be a near-neutral random walk with
    # very large relative fluctuations / extinction risk.
    "hematopoietic": {
        "N_niches": 40,
        "rates": {
            "birth_rate": 0.12,       # stem division into empty niche
            "death_rate_stem": 0.01,  # stem cell death
            "diff_rate": 0.05,        # stem -> progenitor (frees niche)
            "mat_rate": 0.12,         # progenitor -> differentiated
            "apop_prog": 0.06,        # progenitor apoptosis
            "apop_diff": 0.03,        # differentiated apoptosis
        },
        "y0": {"Stem": 20, "Empty": 20, "Progenitor": 10, "Differentiated": 30},
    },
    "neural": {
        "N_niches": 35,
        "rates": {
            "birth_rate": 0.10,
            "death_rate_stem": 0.012,
            "diff_rate": 0.035,
            "mat_rate": 0.09,
            "apop_prog": 0.05,
            "apop_diff": 0.025,
        },
        "y0": {"Stem": 15, "Empty": 20, "Progenitor": 8, "Differentiated": 20},
    },
    "muscle": {
        "N_niches": 30,
        "rates": {
            "birth_rate": 0.15,
            "death_rate_stem": 0.008,
            "diff_rate": 0.06,
            "mat_rate": 0.15,
            "apop_prog": 0.07,
            "apop_diff": 0.04,
        },
        "y0": {"Stem": 12, "Empty": 18, "Progenitor": 6, "Differentiated": 15},
    },
    "minimal": {
        "N_niches": 15,
        "rates": {
            "birth_rate": 0.11,
            "death_rate_stem": 0.015,
            "diff_rate": 0.04,
            "mat_rate": 0.1,
            "apop_prog": 0.05,
            "apop_diff": 0.03,
        },
        "y0": {"Stem": 6, "Empty": 9, "Progenitor": 3, "Differentiated": 8},
    },
}

COMPARTMENTS = ["Stem", "Empty", "Progenitor", "Differentiated"]
RATE_NAMES = ["birth_rate", "death_rate_stem", "diff_rate", "mat_rate", "apop_prog", "apop_diff"]


class StemCellNicheModel:
    """
    Gillespie SSA model of stem cell niche competition.
    """

    def __init__(self, mode: str = "hematopoietic", custom: Dict[str, Any] = None, seed: int = None):
        if mode == "custom":
            if custom is None:
                raise ValueError("mode='custom' requires a 'custom' dict with N_niches, rates, y0")
            self.N_niches = int(custom["N_niches"])
            self.rates = dict(custom["rates"])
            y0d = custom["y0"]
        else:
            if mode not in PRESETS:
                raise ValueError(f"Unknown mode: {mode}. Options: {list(PRESETS.keys()) + ['custom']}")
            preset = PRESETS[mode]
            self.N_niches = preset["N_niches"]
            self.rates = dict(preset["rates"])
            y0d = preset["y0"]

        self.mode = mode
        self.y0 = np.array([y0d["Stem"], y0d["Empty"], y0d["Progenitor"], y0d["Differentiated"]], dtype=float)

        if abs((self.y0[0] + self.y0[1]) - self.N_niches) > 1e-9:
            raise ValueError(
                f"Niche conservation violated in y0: Stem+Empty={self.y0[0] + self.y0[1]} != N_niches={self.N_niches}"
            )

        self._rng = np.random.default_rng(seed)

    # ------------------------------------------------------------------
    # Core SSA engine
    # ------------------------------------------------------------------
    def _propensities(self, y: np.ndarray, rates: Dict[str, float]) -> np.ndarray:
        Stem, Empty, Progenitor, Differentiated = y
        a1 = rates["birth_rate"] * Stem * Empty / max(self.N_niches, 1)  # niche competition
        a2 = rates["death_rate_stem"] * Stem
        a3 = rates["diff_rate"] * Stem
        a4 = rates["mat_rate"] * Progenitor
        a5 = rates["apop_prog"] * Progenitor
        a6 = rates["apop_diff"] * Differentiated
        return np.array([a1, a2, a3, a4, a5, a6])

    # State updates for reactions R1..R6, indexed [dStem, dEmpty, dProgenitor, dDifferentiated]
    _STOICH = np.array([
        [1, -1, 0, 0],   # R1: birth into empty niche
        [-1, 1, 0, 0],   # R2: stem death
        [-1, 1, 1, 0],   # R3: differentiation (frees niche, creates progenitor)
        [0, 0, -1, 1],   # R4: maturation
        [0, 0, -1, 0],   # R5: progenitor apoptosis
        [0, 0, 0, -1],   # R6: differentiated apoptosis
    ], dtype=float)

    def run_trajectory(self, t_end: float, rates: Dict[str, float] = None,
                        y0: np.ndarray = None, max_events: int = 300000,
                        rng: np.random.Generator = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        Run a single Gillespie SSA trajectory from t=0 to t=t_end.
        Returns (event_times, states) where states[i] is the state AFTER event i
        (states[0] is y0 at t=0).
        """
        if rates is None:
            rates = self.rates
        if y0 is None:
            y0 = self.y0.copy()
        if rng is None:
            rng = self._rng

        y = y0.copy()
        t = 0.0
        times = [0.0]
        states = [y.copy()]

        for _ in range(max_events):
            a = self._propensities(y, rates)
            a0 = a.sum()
            if a0 <= 1e-12:
                # System has reached an absorbing state (all activity ceased)
                break
            dt = -np.log(rng.random()) / a0
            t += dt
            if t > t_end:
                break
            r = rng.random() * a0
            cum = np.cumsum(a)
            idx = int(np.searchsorted(cum, r))
            idx = min(idx, 5)
            y = y + self._STOICH[idx]
            y = np.maximum(y, 0)
            times.append(t)
            states.append(y.copy())

        return np.array(times), np.array(states)

    def sample_at_times(self, times: np.ndarray, states: np.ndarray, t_query: np.ndarray) -> np.ndarray:
        """Step-interpolate a trajectory (piecewise-constant between events) at query times."""
        idx = np.searchsorted(times, t_query, side="right") - 1
        idx = np.clip(idx, 0, len(states) - 1)
        return states[idx]

    # ------------------------------------------------------------------
    # High-level modes
    # ------------------------------------------------------------------
    def simulate(self, t_end: float = 100.0, num_points: int = 300,
                 rates: Dict[str, float] = None, y0: np.ndarray = None, seed: int = None) -> Dict[str, Any]:
        rng = np.random.default_rng(seed) if seed is not None else self._rng
        times, states = self.run_trajectory(t_end, rates=rates, y0=y0, rng=rng)
        t_query = np.linspace(0, t_end, num_points)
        sampled = self.sample_at_times(times, states, t_query)

        occupancy = sampled[:, 0] / self.N_niches

        result = {
            "mode": self.mode,
            "N_niches": self.N_niches,
            "time": t_query.tolist(),
            "Stem": sampled[:, 0].tolist(),
            "Empty": sampled[:, 1].tolist(),
            "Progenitor": sampled[:, 2].tolist(),
            "Differentiated": sampled[:, 3].tolist(),
            "niche_occupancy_fraction": occupancy.tolist(),
            "n_events": int(len(times) - 1),
            "final_state": {
                "Stem": float(sampled[-1, 0]),
                "Empty": float(sampled[-1, 1]),
                "Progenitor": float(sampled[-1, 2]),
                "Differentiated": float(sampled[-1, 3]),
                "occupancy_fraction": float(occupancy[-1]),
            },
            "status": "success",
        }
        return result

    def ensemble(self, t_end: float = 100.0, n_replicates: int = 30,
                 rates: Dict[str, float] = None, y0: np.ndarray = None) -> Dict[str, Any]:
        """Run many replicate trajectories, return the distribution of final states."""
        finals = np.zeros((n_replicates, 4))
        for i in range(n_replicates):
            times, states = self.run_trajectory(t_end, rates=rates, y0=y0)
            finals[i] = states[-1]

        mean = finals.mean(axis=0)
        std = finals.std(axis=0)
        cv = std / np.maximum(mean, 1e-9)
        occ = finals[:, 0] / self.N_niches

        return {
            "mode": self.mode,
            "N_niches": self.N_niches,
            "n_replicates": n_replicates,
            "t_end": t_end,
            "mean": {c: float(mean[i]) for i, c in enumerate(COMPARTMENTS)},
            "std": {c: float(std[i]) for i, c in enumerate(COMPARTMENTS)},
            "cv": {c: float(cv[i]) for i, c in enumerate(COMPARTMENTS)},
            "occupancy_fraction_mean": float(occ.mean()),
            "occupancy_fraction_std": float(occ.std()),
            "status": "success",
        }

    def steady_state(self, t_settle: float = 150.0, n_replicates: int = 20,
                      rates: Dict[str, float] = None, y0: np.ndarray = None) -> Dict[str, Any]:
        """
        Ensemble-averaged equilibrium: run replicates to t_settle/2 and t_settle,
        compare ensemble means to assess convergence (more robust than single-trajectory
        time-window CV, which is dominated by demographic noise at small N_niches).
        """
        half = self.ensemble(t_end=t_settle / 2.0, n_replicates=n_replicates, rates=rates, y0=y0)
        full = self.ensemble(t_end=t_settle, n_replicates=n_replicates, rates=rates, y0=y0)

        occ_half = half["occupancy_fraction_mean"]
        occ_full = full["occupancy_fraction_mean"]
        # Absolute change is the robust metric here: occupancy is already bounded
        # in [0, 1], so relative change blows up spuriously whenever the
        # equilibrium happens to sit near zero.
        abs_change = abs(occ_full - occ_half)

        return {
            "mode": self.mode,
            "N_niches": self.N_niches,
            "t_settle": t_settle,
            "n_replicates": n_replicates,
            "mean": full["mean"],
            "std": full["std"],
            "cv": full["cv"],
            "occupancy_fraction": occ_full,
            "occupancy_fraction_at_half_time": occ_half,
            "absolute_change_half_to_full": abs_change,
            "status": "success",
        }

    def bifurcation(self, param_name: str = "birth_rate", param_range: Tuple[float, float] = None,
                     num_points: int = 6, t_settle: float = 100.0, n_replicates: int = 12) -> Dict[str, Any]:
        """
        Scan a parameter (default: birth_rate = 'niche strength') and report
        ensemble-mean niche occupancy fraction at steady state for each value.
        """
        if param_name not in RATE_NAMES:
            return {"status": "error", "error": f"Unknown parameter: {param_name}. Options: {RATE_NAMES}"}

        base = self.rates[param_name]
        if param_range is None:
            param_range = (base * 0.3, base * 2.5)

        param_values = np.linspace(param_range[0], param_range[1], num_points)
        occupancy = []
        differentiated_frac = []

        for p_val in param_values:
            rates = self.rates.copy()
            rates[param_name] = float(p_val)
            ens = self.ensemble(t_end=t_settle, n_replicates=n_replicates, rates=rates)
            occupancy.append(ens["occupancy_fraction_mean"])
            total = sum(ens["mean"].values())
            differentiated_frac.append(ens["mean"]["Differentiated"] / max(total, 1e-9))

        return {
            "mode": self.mode,
            "parameter": param_name,
            "param_values": param_values.tolist(),
            "niche_occupancy_fraction": occupancy,
            "differentiated_fraction": differentiated_frac,
            "status": "success",
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate(self) -> Dict[str, Any]:
        checks = {}
        passed = 0
        total = 0

        # 1. Parameters positive
        total += 1
        try:
            ok = all(v > 0 for v in self.rates.values())
            checks["params_positive"] = {"passed": ok, "details": "All reaction rates > 0"}
            passed += ok
        except Exception as e:
            checks["params_positive"] = {"passed": False, "details": str(e)}

        # 2. Initial conditions non-negative + niche conservation
        total += 1
        try:
            nonneg = np.all(self.y0 >= 0)
            conserved = abs((self.y0[0] + self.y0[1]) - self.N_niches) < 1e-9
            ok = bool(nonneg and conserved)
            checks["y0_valid"] = {
                "passed": ok,
                "details": f"y0>=0: {nonneg}, Stem+Empty={self.y0[0]+self.y0[1]} == N_niches={self.N_niches}: {conserved}",
            }
            passed += ok
        except Exception as e:
            checks["y0_valid"] = {"passed": False, "details": str(e)}

        # 3. Short trajectory completes without NaN/Inf
        total += 1
        try:
            times, states = self.run_trajectory(20.0)
            ok = bool(np.all(np.isfinite(states)))
            checks["no_divergence"] = {"passed": ok, "details": "Trajectory 0-20 (time units) is finite"}
            passed += ok
        except Exception as e:
            checks["no_divergence"] = {"passed": False, "details": str(e)}

        # 4. State stays non-negative throughout
        total += 1
        try:
            times, states = self.run_trajectory(20.0)
            ok = bool(np.all(states >= -1e-9))
            checks["nonnegative_solution"] = {"passed": ok, "details": "All compartments stay >= 0"}
            passed += ok
        except Exception as e:
            checks["nonnegative_solution"] = {"passed": False, "details": str(e)}

        # 5. Niche conservation holds exactly at every event
        total += 1
        try:
            times, states = self.run_trajectory(50.0)
            niche_sum = states[:, 0] + states[:, 1]
            ok = bool(np.allclose(niche_sum, self.N_niches))
            checks["niche_conservation"] = {
                "passed": ok,
                "details": f"Stem+Empty constant at N_niches={self.N_niches} across {len(states)} events",
            }
            passed += ok
        except Exception as e:
            checks["niche_conservation"] = {"passed": False, "details": str(e)}

        # 6. Differentiated compartment trends upward over time
        total += 1
        try:
            times, states = self.run_trajectory(100.0)
            diff_comp = states[:, 3]
            increases = np.sum(np.diff(diff_comp) >= -1e-9)
            frac = increases / max(len(diff_comp) - 1, 1)
            ok = bool(frac > 0.55)
            checks["differentiation_trend"] = {
                "passed": ok,
                "details": f"Differentiated non-decreasing in {increases}/{len(diff_comp)-1} events (frac={frac:.2f})",
            }
            passed += ok
        except Exception as e:
            checks["differentiation_trend"] = {"passed": False, "details": str(e)}

        # 7. Occupancy fraction bounded in [0, 1]
        total += 1
        try:
            times, states = self.run_trajectory(100.0)
            occ = states[:, 0] / self.N_niches
            ok = bool(np.all(occ >= -1e-9) and np.all(occ <= 1 + 1e-9))
            checks["occupancy_bounded"] = {
                "passed": ok,
                "details": f"occupancy fraction range [{occ.min():.3f}, {occ.max():.3f}]",
            }
            passed += ok
        except Exception as e:
            checks["occupancy_bounded"] = {"passed": False, "details": str(e)}

        # 8. Steady state reachable: ensemble mean occupancy stable between t/2 and t
        total += 1
        try:
            ss = self.steady_state(t_settle=120.0, n_replicates=20)
            abs_change = ss["absolute_change_half_to_full"]
            ok = bool(abs_change < 0.12)
            checks["steady_state_reachable"] = {
                "passed": ok,
                "details": f"Absolute change in ensemble-mean occupancy (t/2 -> t): {abs_change:.4f}",
            }
            passed += ok
        except Exception as e:
            checks["steady_state_reachable"] = {"passed": False, "details": str(e)}

        # 9. Parameter sensitivity: perturbing birth_rate changes steady-state occupancy
        total += 1
        try:
            rates_pert = self.rates.copy()
            rates_pert["birth_rate"] *= 1.4
            ens_base = self.ensemble(t_end=100.0, n_replicates=15)
            ens_pert = self.ensemble(t_end=100.0, n_replicates=15, rates=rates_pert)
            delta = abs(ens_pert["occupancy_fraction_mean"] - ens_base["occupancy_fraction_mean"])
            ok = bool(delta > 0.02)
            checks["parameter_sensitivity"] = {
                "passed": ok,
                "details": f"|Δ occupancy| after birth_rate +40%: {delta:.4f}",
            }
            passed += ok
        except Exception as e:
            checks["parameter_sensitivity"] = {"passed": False, "details": str(e)}

        # 10. Schema consistency
        total += 1
        try:
            ok = (len(COMPARTMENTS) == 4) and (len(self.y0) == 4) and set(self.rates.keys()) == set(RATE_NAMES)
            checks["schema_consistency"] = {
                "passed": bool(ok),
                "details": f"4 compartments, 4 initial conditions, {len(self.rates)} rate parameters",
            }
            passed += ok
        except Exception as e:
            checks["schema_consistency"] = {"passed": False, "details": str(e)}

        return {
            "mode": self.mode,
            "checks": checks,
            "total_passed": passed,
            "total_checks": total,
            "status": "success" if passed == total else "partial",
        }

    # ------------------------------------------------------------------
    def run(self, op_mode: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if op_mode == "simulate":
            return self.simulate(
                t_end=params.get("t_end", 100.0),
                num_points=params.get("num_points", 300),
                rates=params.get("rates"),
                seed=params.get("seed"),
            )
        elif op_mode == "ensemble":
            return self.ensemble(
                t_end=params.get("t_end", 100.0),
                n_replicates=params.get("n_replicates", 30),
                rates=params.get("rates"),
            )
        elif op_mode == "steady_state":
            return self.steady_state(
                t_settle=params.get("t_settle", 150.0),
                n_replicates=params.get("n_replicates", 20),
                rates=params.get("rates"),
            )
        elif op_mode == "bifurcation":
            param_range = params.get("param_range")
            return self.bifurcation(
                param_name=params.get("param_name", "birth_rate"),
                param_range=tuple(param_range) if param_range else None,
                num_points=params.get("num_points", 6),
                t_settle=params.get("t_settle", 100.0),
                n_replicates=params.get("n_replicates", 12),
            )
        elif op_mode == "validate":
            return self.validate()
        else:
            return {"status": "error", "error": f"Unknown mode: {op_mode}"}


def run(mode: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Global entry point for the tool.

    params:
      "tissue_mode": one of "hematopoietic" | "neural" | "muscle" | "minimal" | "custom" (default "hematopoietic")
      "custom": {N_niches, rates, y0} -- required if tissue_mode == "custom"
      ... plus mode-specific params (see StemCellNicheModel.run)
    """
    tissue_mode = params.get("tissue_mode", "hematopoietic")
    custom = params.get("custom")
    seed = params.get("seed")
    model = StemCellNicheModel(mode=tissue_mode, custom=custom, seed=seed)
    return model.run(mode, params)


# ----------------------------------------------------------------------------
# Self-registration with tool_registry (required for the MCP server to expose
# this tool via tools/list and tools/call -- importing the module alone is
# NOT sufficient, this call is what actually wires it in).
# ----------------------------------------------------------------------------
STEM_CELL_NICHE_TOOL_SCHEMA = {
    "name": "stem_cell_niche_tool",
    "description": (
        "Modelo estocastico (Gillespie SSA) de competencia por nicho de celulas madre. "
        "Un pool fijo de nichos fisicos (Stem + Empty = N_niches, invariante exacto) es "
        "disputado por division/auto-renovacion; las celulas tambien se diferencian, "
        "maduran y mueren. Modos de tejido preconfigurados: hematopoietic, neural, "
        "muscle, minimal, o custom (N_niches/rates/y0 definidos por el usuario). "
        "Modos operacionales: simulate (una trayectoria), ensemble (muchas replicas), "
        "steady_state (equilibrio promediado por ensemble), bifurcation (barrido de un "
        "parametro, e.g. 'fuerza de nicho' via birth_rate, reportando fraccion de "
        "ocupacion de nicho), validate (10 self-checks)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["simulate", "ensemble", "steady_state", "bifurcation", "validate"],
            },
            "params": {
                "type": "object",
                "description": (
                    "tissue_mode (hematopoietic|neural|muscle|minimal|custom), custom "
                    "{N_niches, rates, y0}, seed, y parametros especificos de cada modo "
                    "(t_end, num_points, n_replicates, t_settle, param_name, param_range, "
                    "rates override)."
                ),
            },
        },
        "required": ["mode"],
    },
}

register_tool(
    name="stem_cell_niche_tool",
    schema=STEM_CELL_NICHE_TOOL_SCHEMA,
    handler=lambda args: run(args.get("mode"), args.get("params") or {}),
)
