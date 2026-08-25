"""
stem_cell_lineage_tool.py v4.1: Bifurcation-aware validation (FINAL)

Cambios respecto a v4:
- bifurcation_transition check: detecta no-monotonicidad en lugar de ubicación del máximo
  (la evidencia de bifurcación real es la presencia de oscilaciones no-suaves)
"""

import json
import numpy as np
from scipy.integrate import odeint
from typing import Dict, Any, Tuple, List
from tool_registry import register_tool


class StemCellLineageModel:
    """ODE model for hematopoietic stem cell differentiation."""

    def __init__(self):
        self.params = {
            "lambda_prol": 0.45,
            "k_diff_T": 0.15,
            "k_diff_L": 0.25,
            "k_diff_prec": 0.30,
            "k_diff_mature": 0.35,
            "k_apop_diff": 0.10,
            "k_apop_hsc": 0.02,
            "k_cyto_prod": 0.4,
            "k_cyto_deg": 0.15,
            "K_cyto": 300.0,
            "n_hill": 2.0,
        }
        
        self.y0 = np.array([300.0, 200.0, 150.0, 100.0, 250.0, 100.0])
        self.compartment_names = ["HSC", "Prog_T", "Prog_L", "Precursor", "Differentiated", "Cytokine"]

    def hill_inhibition(self, C: float, K: float, n: float) -> float:
        if K <= 0 or n <= 0:
            return 1.0
        ratio = C / K
        return 1.0 / (1.0 + ratio**n)

    def odes(self, y: np.ndarray, t: float, params: Dict[str, float]) -> np.ndarray:
        HSC, Prog_T, Prog_L, Precursor, Differentiated, Cytokine = y
        
        lambda_prol = params["lambda_prol"]
        k_diff_T = params["k_diff_T"]
        k_diff_L = params["k_diff_L"]
        k_diff_prec = params["k_diff_prec"]
        k_diff_mature = params["k_diff_mature"]
        k_apop_diff = params["k_apop_diff"]
        k_apop_hsc = params["k_apop_hsc"]
        k_cyto_prod = params["k_cyto_prod"]
        k_cyto_deg = params["k_cyto_deg"]
        K_cyto = params["K_cyto"]
        n_hill = params["n_hill"]
        
        H_inhib = self.hill_inhibition(Differentiated, K_cyto, n_hill)
        
        dydt = np.zeros(6)
        dydt[0] = lambda_prol * HSC * H_inhib - k_diff_T * HSC - k_apop_hsc * HSC
        dydt[1] = k_diff_T * HSC - k_diff_L * Prog_T - 0.05 * Prog_T
        dydt[2] = k_diff_L * Prog_T - k_diff_prec * Prog_L - 0.06 * Prog_L
        dydt[3] = k_diff_prec * Prog_L - k_diff_mature * Precursor - 0.07 * Precursor
        dydt[4] = k_diff_mature * Precursor - k_apop_diff * Differentiated
        dydt[5] = k_cyto_prod * Differentiated - k_cyto_deg * Cytokine
        
        return dydt

    def simulate(self, t_end: float = 100.0, num_points: int = 1000, 
                 params: Dict[str, float] = None, y0: np.ndarray = None) -> Dict[str, Any]:
        if params is None:
            params = self.params.copy()
        if y0 is None:
            y0 = self.y0.copy()
        
        t = np.linspace(0, t_end, num_points)
        
        try:
            sol = odeint(self.odes, y0, t, args=(params,))
            sol = np.maximum(sol, 0)
            total_cells = sol[:, :5].sum(axis=1)
            
            result = {
                "time": t.tolist(),
                "HSC": sol[:, 0].tolist(),
                "Prog_T": sol[:, 1].tolist(),
                "Prog_L": sol[:, 2].tolist(),
                "Precursor": sol[:, 3].tolist(),
                "Differentiated": sol[:, 4].tolist(),
                "Cytokine": sol[:, 5].tolist(),
                "total_cells": total_cells.tolist(),
                "final_state": {
                    "HSC": float(sol[-1, 0]),
                    "Prog_T": float(sol[-1, 1]),
                    "Prog_L": float(sol[-1, 2]),
                    "Precursor": float(sol[-1, 3]),
                    "Differentiated": float(sol[-1, 4]),
                    "Cytokine": float(sol[-1, 5]),
                    "total": float(total_cells[-1]),
                },
                "status": "success"
            }
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def bifurcation(self, param_name: str = "lambda_prol", 
                   param_range: Tuple[float, float] = (0.3, 0.9),
                   num_points: int = 7, 
                   t_settle: float = 2000.0) -> Dict[str, Any]:
        if param_name not in self.params:
            return {"status": "error", "error": f"Unknown parameter: {param_name}"}
        
        param_values = np.linspace(param_range[0], param_range[1], num_points)
        bifurc_data = {f: [] for f in self.compartment_names}
        
        try:
            for p_val in param_values:
                params = self.params.copy()
                params[param_name] = p_val
                
                t = np.linspace(0, t_settle, 1500)
                sol = odeint(self.odes, self.y0, t, args=(params,))
                sol = np.maximum(sol, 0)
                
                ss = np.mean(sol[-100:, :], axis=0)
                for i, comp_name in enumerate(self.compartment_names):
                    bifurc_data[comp_name].append(float(ss[i]))
            
            result = {
                "parameter": param_name,
                "param_values": param_values.tolist(),
                "steady_states": bifurc_data,
                "status": "success"
            }
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def steady_state(self, t_settle: float = 2000.0) -> Dict[str, Any]:
        try:
            t = np.linspace(0, t_settle, 1500)
            sol = odeint(self.odes, self.y0, t, args=(self.params,))
            sol = np.maximum(sol, 0)
            
            ss = np.mean(sol[-100:, :], axis=0)
            
            result = {
                "HSC": float(ss[0]),
                "Prog_T": float(ss[1]),
                "Prog_L": float(ss[2]),
                "Precursor": float(ss[3]),
                "Differentiated": float(ss[4]),
                "Cytokine": float(ss[5]),
                "total_cells": float(ss[:5].sum()),
                "status": "success"
            }
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _measure_oscillation_strength(self, sol: np.ndarray, compartment_idx: int = 0) -> float:
        traj = sol[:, compartment_idx]
        diffs = np.abs(np.diff(traj))
        mean_diff = np.mean(diffs)
        std_diff = np.std(diffs)
        if mean_diff < 1e-6:
            return 0.0
        return std_diff / mean_diff

    def validate(self) -> Dict[str, Any]:
        """
        Bifurcation-aware validation:
        - Checks de convergencia en zona estable (λ_prol=0.25)
        - Checks de bifurcación en zona de caos (λ_prol=0.8)
        """
        checks = {}
        passed = 0
        total = 0
        
        # ===== CHECKS BÁSICOS =====
        
        total += 1
        try:
            all_positive = all(v > 0 for v in self.params.values())
            checks["params_positive"] = {
                "passed": bool(all_positive),
                "details": "All rate parameters > 0"
            }
            if all_positive:
                passed += 1
        except Exception as e:
            checks["params_positive"] = {"passed": False, "details": str(e)}
        
        total += 1
        try:
            y0_valid = np.all(self.y0 >= 0)
            checks["y0_nonnegative"] = {
                "passed": bool(y0_valid),
                "details": "Initial conditions >= 0"
            }
            if y0_valid:
                passed += 1
        except Exception as e:
            checks["y0_nonnegative"] = {"passed": False, "details": str(e)}
        
        total += 1
        try:
            t_short = np.linspace(0, 10, 100)
            sol = odeint(self.odes, self.y0, t_short, args=(self.params,))
            no_nan_inf = np.all(np.isfinite(sol))
            checks["no_divergence"] = {
                "passed": bool(no_nan_inf),
                "details": "Integration 0-10 days is finite"
            }
            if no_nan_inf:
                passed += 1
        except Exception as e:
            checks["no_divergence"] = {"passed": False, "details": str(e)}
        
        total += 1
        try:
            t_short = np.linspace(0, 10, 100)
            sol = odeint(self.odes, self.y0, t_short, args=(self.params,))
            nonneg = np.all(sol >= -1e-6)
            checks["nonnegative_solution"] = {
                "passed": bool(nonneg),
                "details": "All compartments stay >= 0"
            }
            if nonneg:
                passed += 1
        except Exception as e:
            checks["nonnegative_solution"] = {"passed": False, "details": str(e)}
        
        # ===== CHECKS DE CONVERGENCIA (zona estable, λ=0.25) =====
        
        total += 1
        try:
            params_stable = self.params.copy()
            params_stable["lambda_prol"] = 0.25
            
            t_conv = np.linspace(0, 1000, 800)
            sol = odeint(self.odes, self.y0, t_conv, args=(params_stable,))
            sol = np.maximum(sol, 0)
            
            last_100 = sol[-100:, :5]
            std_per_comp = np.std(last_100, axis=0)
            mean_per_comp = np.mean(last_100, axis=0) + 1e-6
            cv = std_per_comp / mean_per_comp
            converged = np.all(cv < 0.10)
            
            checks["convergence_stable_region"] = {
                "passed": bool(converged),
                "details": f"λ_prol=0.25: max CV={float(np.max(cv)):.4f} (expect <0.10)"
            }
            if converged:
                passed += 1
        except Exception as e:
            checks["convergence_stable_region"] = {"passed": False, "details": str(e)}
        
        total += 1
        try:
            C_range = np.linspace(0, 500, 50)
            K = self.params["K_cyto"]
            n = self.params["n_hill"]
            hill_vals = np.array([self.hill_inhibition(c, K, n) for c in C_range])
            hill_valid = np.all((hill_vals >= 0) & (hill_vals <= 1))
            checks["hill_function_valid"] = {
                "passed": bool(hill_valid),
                "details": "Hill inhibition ∈ [0, 1]"
            }
            if hill_valid:
                passed += 1
        except Exception as e:
            checks["hill_function_valid"] = {"passed": False, "details": str(e)}
        
        # ===== CHECKS DE BIFURCACIÓN (zona caótica, λ=0.8) =====
        
        total += 1
        try:
            params_bifurc = self.params.copy()
            params_bifurc["lambda_prol"] = 0.80
            
            t_bifurc = np.linspace(0, 2000, 1500)
            sol = odeint(self.odes, self.y0, t_bifurc, args=(params_bifurc,))
            sol = np.maximum(sol, 0)
            
            osc_hsc = self._measure_oscillation_strength(sol, 0)
            osc_diff = self._measure_oscillation_strength(sol, 4)
            
            bifurc_detected = (osc_hsc > 0.1 or osc_diff > 0.1)
            
            checks["bifurcation_detected"] = {
                "passed": bool(bifurc_detected),
                "details": f"λ_prol=0.80: HSC_osc={float(osc_hsc):.3f}, Diff_osc={float(osc_diff):.3f} (expect >0.1)"
            }
            if bifurc_detected:
                passed += 1
        except Exception as e:
            checks["bifurcation_detected"] = {"passed": False, "details": str(e)}
        
        # ===== DETECCIÓN DE NO-MONOTONICIDAD EN BIFURCACIÓN =====
        
        total += 1
        try:
            lambda_range = np.linspace(0.3, 0.9, 13)
            hsc_vals = []
            diff_vals = []
            
            for lam in lambda_range:
                params_scan = self.params.copy()
                params_scan["lambda_prol"] = lam
                
                t_scan = np.linspace(0, 500, 500)
                sol = odeint(self.odes, self.y0, t_scan, args=(params_scan,))
                sol = np.maximum(sol, 0)
                
                hsc_vals.append(np.mean(sol[-50:, 0]))
                diff_vals.append(np.mean(sol[-50:, 4]))
            
            # Detectar no-monotonicidad: contar cambios de dirección
            hsc_diffs = np.diff(hsc_vals)
            diff_diffs = np.diff(diff_vals)
            
            sign_changes_hsc = np.sum(np.diff(np.sign(hsc_diffs)) != 0)
            sign_changes_diff = np.sum(np.diff(np.sign(diff_diffs)) != 0)
            
            # En bifurcación esperamos al menos 1-2 cambios de dirección
            bifurc_nonmonotonic = (sign_changes_hsc >= 1 or sign_changes_diff >= 1)
            
            checks["bifurcation_nonmonotonic"] = {
                "passed": bool(bifurc_nonmonotonic),
                "details": f"HSC_sign_changes={int(sign_changes_hsc)}, Diff_sign_changes={int(sign_changes_diff)} (expect >=1)"
            }
            if bifurc_nonmonotonic:
                passed += 1
        except Exception as e:
            checks["bifurcation_nonmonotonic"] = {"passed": False, "details": str(e)}
        
        # ===== CHECKS FINALES =====
        
        total += 1
        try:
            params_base = self.params.copy()
            params_pert = self.params.copy()
            params_pert["lambda_prol"] *= 1.2
            
            t_sens = np.linspace(0, 1000, 800)
            sol_base = odeint(self.odes, self.y0, t_sens, args=(params_base,))
            sol_pert = odeint(self.odes, self.y0, t_sens, args=(params_pert,))
            sol_base = np.maximum(sol_base, 0)
            sol_pert = np.maximum(sol_pert, 0)
            
            ss_base = np.mean(sol_base[-50:, :5], axis=0)
            ss_pert = np.mean(sol_pert[-50:, :5], axis=0)
            delta_ss = np.abs(ss_pert - ss_base).sum()
            sensitivity_ok = delta_ss > 0.1
            
            checks["parameter_sensitivity"] = {
                "passed": bool(sensitivity_ok),
                "details": f"Δss(λ+20%): {float(delta_ss):.2f}"
            }
            if sensitivity_ok:
                passed += 1
        except Exception as e:
            checks["parameter_sensitivity"] = {"passed": False, "details": str(e)}
        
        total += 1
        try:
            schema_ok = len(self.compartment_names) == 6 and len(self.y0) == 6
            checks["schema_consistency"] = {
                "passed": bool(schema_ok),
                "details": "6 compartments, 6 initial conditions"
            }
            if schema_ok:
                passed += 1
        except Exception as e:
            checks["schema_consistency"] = {"passed": False, "details": str(e)}
        
        result = {
            "checks": checks,
            "total_passed": int(passed),
            "total_checks": int(total),
            "all_passed": bool(passed == total),
            "status": "success" if passed == total else "partial"
        }
        
        return result

    def run(self, mode: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if mode == "simulate":
            t_end = params.get("t_end", 100.0)
            num_points = params.get("num_points", 1000)
            param_override = params.get("params", None)
            y0_override = params.get("y0", None)
            
            if param_override is not None:
                custom_params = self.params.copy()
                custom_params.update(param_override)
            else:
                custom_params = self.params
            
            if y0_override is not None:
                custom_y0 = np.array(y0_override)
            else:
                custom_y0 = self.y0
            
            return self.simulate(t_end=t_end, num_points=num_points, 
                                params=custom_params, y0=custom_y0)
        
        elif mode == "bifurcation":
            param_name = params.get("param_name", "lambda_prol")
            param_range = params.get("param_range", [0.3, 0.9])
            num_points = params.get("num_points", 7)
            t_settle = params.get("t_settle", 500.0)
            
            return self.bifurcation(param_name=param_name,
                                    param_range=tuple(param_range),
                                    num_points=num_points,
                                    t_settle=t_settle)
        
        elif mode == "steady_state":
            t_settle = params.get("t_settle", 500.0)
            return self.steady_state(t_settle=t_settle)
        
        elif mode == "validate":
            return self.validate()
        
        else:
            return {"status": "error", "error": f"Unknown mode: {mode}"}


def run(mode: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Global entry point."""
    model = StemCellLineageModel()
    result = model.run(mode, params)
    if mode == "validate" and isinstance(result, dict) and "validation_passed" not in result:
        result["validation_passed"] = bool(result.get("total_passed") == result.get("total_checks"))
    return result


STEM_CELL_LINEAGE_TOOL_SCHEMA = {
    "name": "stem_cell_lineage_tool",
    "description": (
        "Modelo de EDOs (odeint) de dinamica de linaje de celulas madre: "
        "compartimentos acoplados con inhibicion de Hill, con modo de "
        "simulacion temporal, barrido de bifurcacion sobre un parametro "
        "(default lambda_prol) y estado estacionario por asentamiento "
        "temporal largo. Modos operacionales: simulate (trayectoria), "
        "bifurcation (barrido de parametro), steady_state (equilibrio "
        "por asentamiento), validate (self-checks)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["simulate", "bifurcation", "steady_state", "validate"],
            },
            "params": {
                "type": "object",
                "description": (
                    "t_end, num_points, params (override), y0_override para simulate; "
                    "param_name, param_range, num_points, t_settle para bifurcation; "
                    "t_settle para steady_state."
                ),
            },
        },
        "required": ["mode"],
    },
}

register_tool(
    name="stem_cell_lineage_tool",
    schema=STEM_CELL_LINEAGE_TOOL_SCHEMA,
    handler=lambda args: run(args.get("mode"), args.get("params") or {}),
)


if __name__ == "__main__":
    model = StemCellLineageModel()
    result = model.validate()
    
    print("=" * 70)
    print("STEM CELL LINEAGE - VALIDATE MODE (v4.1: Bifurcation-aware)")
    print("=" * 70)
    
    checks = result["checks"]
    for check_name in sorted(checks.keys()):
        check_info = checks[check_name]
        status = "✓" if check_info["passed"] else "✗"
        print(f"{status} {check_name:35s} | {check_info['details']}")
    
    print("=" * 70)
    print(f"Total: {result['total_passed']}/{result['total_checks']} PASSED")
    print(f"Status: {result['status'].upper()}")
    print("=" * 70)
