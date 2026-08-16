"""
Worker aislado para calculos DFT/HF via PySCF.
Se ejecuta exclusivamente con .venv-pyscf/bin/python3, invocado como
subprocess desde dft_tool.py (que corre en el Python del sistema/server
principal). Contrato: recibe JSON por stdin, devuelve JSON por stdout.
Nunca importar este modulo directamente desde server.py.
"""
import sys
import json


def _build_mol(atom, basis, charge=0, spin=0, unit="Angstrom"):
    from pyscf import gto
    return gto.M(atom=atom, basis=basis, charge=charge, spin=spin, unit=unit, verbose=0)


def run_hf_energy(params):
    from pyscf import scf
    mol = _build_mol(
        params["atom"], params.get("basis", "sto-3g"),
        params.get("charge", 0), params.get("spin", 0), params.get("unit", "Angstrom"))
    mf = scf.RHF(mol) if mol.spin == 0 else scf.UHF(mol)
    e_tot = mf.kernel()
    return {
        "method": "HF",
        "basis": params.get("basis", "sto-3g"),
        "energy_hartree": round(float(e_tot), 10),
        "converged": bool(mf.converged),
        "n_electrons": mol.nelectron,
        "n_basis_functions": mol.nao,
    }


def run_dft_energy(params):
    from pyscf import dft
    mol = _build_mol(
        params["atom"], params.get("basis", "sto-3g"),
        params.get("charge", 0), params.get("spin", 0), params.get("unit", "Angstrom"))
    xc = params.get("xc", "b3lyp")
    mf = dft.RKS(mol, xc=xc) if mol.spin == 0 else dft.UKS(mol, xc=xc)
    e_tot = mf.kernel()
    return {
        "method": "DFT",
        "xc_functional": xc,
        "basis": params.get("basis", "sto-3g"),
        "energy_hartree": round(float(e_tot), 10),
        "converged": bool(mf.converged),
        "n_electrons": mol.nelectron,
        "n_basis_functions": mol.nao,
    }


def run_validate(params):
    """H2/STO-3G HF contra valor de referencia (Szabo & Ostlund): -1.1167593 Ha."""
    checks = []

    r = run_hf_energy({"atom": "H 0 0 0; H 0 0 0.74", "basis": "sto-3g"})
    ref = -1.1167593073964253
    diff = abs(r["energy_hartree"] - ref)
    checks.append({
        "name": "HF/STO-3G H2 equilibrium geometry vs referencia de libro",
        "computed": r["energy_hartree"],
        "reference": ref,
        "abs_diff": diff,
        "passed": bool(diff < 1e-6),
    })

    r2 = run_dft_energy({"atom": "H 0 0 0; H 0 0 0.74", "basis": "sto-3g", "xc": "b3lyp"})
    checks.append({
        "name": "B3LYP/STO-3G H2 converge y da energia menor que HF (correlacion)",
        "hf_energy": r["energy_hartree"],
        "dft_energy": r2["energy_hartree"],
        "passed": bool(r2["converged"] and r2["energy_hartree"] < r["energy_hartree"]),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": bool(all_passed)}


def main():
    try:
        params = json.loads(sys.stdin.read())
        mode = params.get("mode")
        if mode == "hf_energy":
            out = run_hf_energy(params.get("params", {}))
        elif mode == "dft_energy":
            out = run_dft_energy(params.get("params", {}))
        elif mode == "validate":
            out = run_validate(params.get("params", {}))
        else:
            raise ValueError(f"modo desconocido: {mode}")
        print(json.dumps(out))
    except Exception as e:
        print(json.dumps({"error": str(e), "error_type": type(e).__name__}))
        sys.exit(1)


if __name__ == "__main__":
    main()
