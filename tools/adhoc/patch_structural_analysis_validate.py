#!/usr/bin/env python3
"""
patch_structural_analysis_validate.py

Agrega mode="validate" a structural_analysis_tool.py con 5 checks de
solucion cerrada:
  1. beam_analysis simply_supported (P=1500N, a=1.5m, L=3m -> M=1125 N*m,
     R_A=R_B=750N, max_shear=750N)
  2. beam_analysis cantilever (P=1000N en la punta, L=2m -> M_A=2000 N*m,
     R_A=1000N, max_shear=1000N)
  3. truss_analysis triangulo isostatico A(0,0)-B(4,0)-C(2,2), carga
     vertical 1000N en C, pin en A, roller_y en B -> F_AB=+500 (tension),
     F_AC=F_BC=-707.107 (compresion), R_Ay=R_By=500N (verificado a mano
     con equilibrio nodal, independiente del solver)
  4. section_properties rectangular b=0.2m h=0.4m -> I=bh^3/12=0.00106667 m^4
     exacto, area=0.08 m^2
  5. stress_check F=10000N, area=0.01m^2, allowable=2e6 Pa -> stress=1e6 Pa,
     safety_factor=2.0, pass=True

Sigue las convenciones habituales: backup timestamped, anchors con
assert count==1, ast.parse + py_compile despues de escribir.
"""

import ast
import py_compile
import re
import shutil
import time

PATH = "structural_analysis_tool.py"


def read():
    with open(PATH, "r", encoding="utf-8") as f:
        return f.read()


def write(content):
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(content)


def backup():
    ts = int(time.time())
    dst = f"{PATH}.bak.{ts}"
    shutil.copy(PATH, dst)
    print(f"OK: backup creado en {dst}")


VALIDATE_FN = '''
def _validate_structural():
    """Autochequeo con 5 casos de solucion cerrada, uno por sub-modo."""
    checks = []

    # --- 1) beam_analysis, simplemente apoyada, carga puntual ---
    r1 = _beam_analysis(
        support="simply_supported", length=3.0,
        point_loads=[{"P": 1500.0, "x": 1.5}],
    )
    exp_M1, exp_R1 = 1125.0, 750.0
    checks.append({
        "name": "beam_simply_supported_max_moment",
        "expected": exp_M1, "got": r1["max_moment"],
        "passed": abs(abs(r1["max_moment"]) - exp_M1) < 1e-3,
    })
    checks.append({
        "name": "beam_simply_supported_reactions",
        "expected": exp_R1, "got": r1["reactions"],
        "passed": (
            abs(r1["reactions"]["R_A"] - exp_R1) < 1e-3
            and abs(r1["reactions"]["R_B"] - exp_R1) < 1e-3
        ),
    })
    checks.append({
        "name": "beam_simply_supported_max_shear",
        "expected": exp_R1, "got": r1["max_shear"],
        "passed": abs(r1["max_shear"] - exp_R1) < 1e-3,
    })

    # --- 2) beam_analysis, voladizo, carga en la punta ---
    r2 = _beam_analysis(
        support="cantilever", length=2.0,
        point_loads=[{"P": 1000.0, "x": 2.0}],
    )
    exp_M2, exp_R2 = 2000.0, 1000.0
    checks.append({
        "name": "beam_cantilever_max_moment",
        "expected": exp_M2, "got": r2["max_moment"],
        "passed": abs(abs(r2["max_moment"]) - exp_M2) < 1e-3,
    })
    checks.append({
        "name": "beam_cantilever_reactions",
        "expected": {"R_A": exp_R2, "M_A": exp_M2}, "got": r2["reactions"],
        "passed": (
            abs(r2["reactions"]["R_A"] - exp_R2) < 1e-3
            and abs(r2["reactions"]["M_A"] - exp_M2) < 1e-3
        ),
    })
    checks.append({
        "name": "beam_cantilever_max_shear",
        "expected": exp_R2, "got": r2["max_shear"],
        "passed": abs(r2["max_shear"] - exp_R2) < 1e-3,
    })

    # --- 3) truss_analysis, triangulo isostatico simple ---
    r3 = _truss_analysis(
        nodes={"A": (0.0, 0.0), "B": (4.0, 0.0), "C": (2.0, 2.0)},
        members=[("A", "B"), ("A", "C"), ("B", "C")],
        supports={"A": "pin", "B": "roller_y"},
        loads={"C": (0.0, -1000.0)},
    )
    forces = {m["member"]: m["force"] for m in r3["member_forces"]}
    exp_AB, exp_AC_BC = 500.0, -707.107
    tol_truss = 0.05
    checks.append({
        "name": "truss_member_force_AB",
        "expected": exp_AB, "got": forces.get("A-B"),
        "passed": forces.get("A-B") is not None and abs(forces["A-B"] - exp_AB) < tol_truss,
    })
    checks.append({
        "name": "truss_member_force_AC",
        "expected": exp_AC_BC, "got": forces.get("A-C"),
        "passed": forces.get("A-C") is not None and abs(forces["A-C"] - exp_AC_BC) < tol_truss,
    })
    checks.append({
        "name": "truss_member_force_BC",
        "expected": exp_AC_BC, "got": forces.get("B-C"),
        "passed": forces.get("B-C") is not None and abs(forces["B-C"] - exp_AC_BC) < tol_truss,
    })
    exp_reac = 500.0
    r_ay = r3["reactions"].get("A", {}).get("R_y")
    r_by = r3["reactions"].get("B", {}).get("R_y")
    checks.append({
        "name": "truss_reactions_symmetric",
        "expected": exp_reac, "got": {"R_Ay": r_ay, "R_By": r_by},
        "passed": (
            r_ay is not None and r_by is not None
            and abs(r_ay - exp_reac) < tol_truss
            and abs(r_by - exp_reac) < tol_truss
        ),
    })
    checks.append({
        "name": "truss_equilibrium_residual",
        "expected": 0.0, "got": r3["equilibrium_check"],
        "passed": (
            abs(r3["equilibrium_check"]["sum_fx_residual"]) < 1e-6
            and abs(r3["equilibrium_check"]["sum_fy_residual"]) < 1e-6
        ),
    })

    # --- 4) section_properties, rectangular exacta ---
    r4 = _section_properties("rectangular", {"b": 0.2, "h": 0.4})
    exp_I = 0.2 * 0.4 ** 3 / 12
    exp_area = 0.08
    checks.append({
        "name": "section_rectangular_area",
        "expected": exp_area, "got": r4["area_m2"],
        "passed": abs(r4["area_m2"] - exp_area) < 1e-6,
    })
    checks.append({
        "name": "section_rectangular_moment_of_inertia",
        "expected": round(exp_I, 8), "got": r4["moment_of_inertia_m4"],
        "passed": abs(r4["moment_of_inertia_m4"] - exp_I) < 1e-8,
    })

    # --- 5) stress_check ---
    r5 = _stress_check(force=10000.0, area=0.01, allowable_stress=2e6)
    exp_stress, exp_sf = 1_000_000.0, 2.0
    checks.append({
        "name": "stress_check_value",
        "expected": exp_stress, "got": r5["stress"],
        "passed": abs(r5["stress"] - exp_stress) < 1e-3,
    })
    checks.append({
        "name": "stress_check_safety_factor",
        "expected": exp_sf, "got": r5["safety_factor"],
        "passed": abs(r5["safety_factor"] - exp_sf) < 1e-3,
    })
    checks.append({
        "name": "stress_check_pass_flag",
        "expected": True, "got": r5["pass"],
        "passed": r5["pass"] is True,
    })

    all_passed = all(c["passed"] for c in checks)
    return {
        "mode": "validate",
        "checks": checks,
        "all_passed": all_passed,
    }


'''

DISPATCH_ANCHOR = '''    """Entry point del tool. Despacha según `mode`. Retorna un dict serializable a JSON."""
    if mode == "beam_analysis":'''

DISPATCH_REPLACEMENT = '''    """Entry point del tool. Despacha según `mode`. Retorna un dict serializable a JSON."""
    if mode == "validate":
        return _validate_structural()
    if mode == "beam_analysis":'''

DEF_ANCHOR = "def compute_structural_analysis(mode, **params):"


def main():
    backup()
    content = read()

    # 1) insertar _validate_structural() justo antes de compute_structural_analysis
    n_def = content.count(DEF_ANCHOR)
    assert n_def == 1, f"esperaba 1 ocurrencia de DEF_ANCHOR, encontre {n_def}"
    content = content.replace(DEF_ANCHOR, VALIDATE_FN + DEF_ANCHOR)

    # 2) insertar el branch mode=="validate" al principio del dispatcher
    n_dispatch = content.count(DISPATCH_ANCHOR)
    assert n_dispatch == 1, f"esperaba 1 ocurrencia de DISPATCH_ANCHOR, encontre {n_dispatch}"
    content = content.replace(DISPATCH_ANCHOR, DISPATCH_REPLACEMENT)

    # 3) agregar "validate" al enum de mode en el schema, si existe y no esta ya
    enum_pattern = re.compile(r'"enum":\s*\[\s*"beam_analysis"[^\]]*\]')
    matches = enum_pattern.findall(content)
    if len(matches) == 1 and '"validate"' not in matches[0]:
        old_enum = matches[0]
        new_enum = old_enum[:-1].rstrip() + ', "validate"]'
        content = content.replace(old_enum, new_enum, 1)
        print("OK: 'validate' agregado al enum del schema.")
    elif len(matches) == 1 and '"validate"' in matches[0]:
        print("OK: el enum del schema ya incluia 'validate' (sin cambios).")
    else:
        print(
            f"AVISO: no se encontro exactamente 1 enum de mode en el schema "
            f"(encontrados: {len(matches)}). El dispatcher acepta mode='validate' "
            "igual, pero puede seguir apareciendo como SKIPPED en run_all_validations.py "
            "hasta que el schema se actualice a mano."
        )

    write(content)

    # validaciones de sintaxis
    with open(PATH, "r", encoding="utf-8") as f:
        src = f.read()
    ast.parse(src)
    py_compile.compile(PATH, doraise=True)
    print("OK: patch aplicado y sintaxis valida.")


if __name__ == "__main__":
    main()
