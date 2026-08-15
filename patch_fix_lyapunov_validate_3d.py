"""
Fix de _validate_lyapunov (lyapunov_tool.py): el script Octave interno de
compute_lyapunov_exponent tiene el printf final hardcodeado a 3 dimensiones
(imprime y(1), y(2), y(3) sin importar el tamano real del vector de estado).
Los presets (chen_lee, lorenz, etc.) son todos 3D asi que nunca lo tocaron,
pero los casos de validate usaban y0=[1.0] (1D) y Octave tira error de
indice fuera de rango.

Cambio los dos casos de validate a sistemas LINEALES 3D DESACOPLADOS (mismas
3 ecuaciones independientes con el mismo k), que siguen teniendo lambda1==k
exacto mientras respetan la dimension 3 que el script asume.

NOTA APARTE (no se toca en este patch): este printf hardcodeado es un bug
real que afecta a cualquier uso de system='custom' con dimension != 3, no
solo a la validacion. Candidato a arreglo separado.

Uso:
    python3 patch_fix_lyapunov_validate_3d.py
"""
import ast
import shutil
from datetime import datetime

PATH = "lyapunov_tool.py"

OLD = '''    r1 = compute_lyapunov_exponent(
        system="custom", custom_equations="k*y(1)", custom_params={"k": 0.3},
        y0=[1.0], dt=0.002, n_steps=5000, octave_bin=octave_bin, timeout_s=timeout_s,
    )
    ok1 = "lambda1" in r1 and abs(r1["lambda1"] - 0.3) < tol
    checks.append({"name": "custom y'=0.3*y: lambda1 ~ 0.3 (crecimiento exponencial puro)",
                    "passed": ok1, "got": r1.get("lambda1", r1.get("error"))})

    r2 = compute_lyapunov_exponent(
        system="custom", custom_equations="-k*y(1)", custom_params={"k": 0.5},
        y0=[1.0], dt=0.002, n_steps=5000, octave_bin=octave_bin, timeout_s=timeout_s,
    )
    ok2 = "lambda1" in r2 and abs(r2["lambda1"] - (-0.5)) < tol
    checks.append({"name": "custom y'=-0.5*y: lambda1 ~ -0.5 (decaimiento exponencial puro)",
                    "passed": ok2, "got": r2.get("lambda1", r2.get("error"))})'''

NEW = '''    # 3D desacoplado (no 1D): el script Octave interno tiene el printf final
    # hardcodeado a y(1),y(2),y(3) sin chequear la dimension real -- con
    # y0 de 1 elemento revienta con indice fuera de rango. Usando 3
    # ecuaciones independientes con el mismo k, lambda1 sigue siendo
    # exactamente k (misma tasa en las 3 direcciones), pero sin chocar
    # con esa limitacion.
    r1 = compute_lyapunov_exponent(
        system="custom", custom_equations="k*y(1); k*y(2); k*y(3)", custom_params={"k": 0.3},
        y0=[1.0, 1.0, 1.0], dt=0.002, n_steps=5000, octave_bin=octave_bin, timeout_s=timeout_s,
    )
    ok1 = "lambda1" in r1 and abs(r1["lambda1"] - 0.3) < tol
    checks.append({"name": "custom y'=0.3*y (3D desacoplado): lambda1 ~ 0.3 (crecimiento exponencial puro)",
                    "passed": ok1, "got": r1.get("lambda1", r1.get("error"))})

    r2 = compute_lyapunov_exponent(
        system="custom", custom_equations="-k*y(1); -k*y(2); -k*y(3)", custom_params={"k": 0.5},
        y0=[1.0, 1.0, 1.0], dt=0.002, n_steps=5000, octave_bin=octave_bin, timeout_s=timeout_s,
    )
    ok2 = "lambda1" in r2 and abs(r2["lambda1"] - (-0.5)) < tol
    checks.append({"name": "custom y'=-0.5*y (3D desacoplado): lambda1 ~ -0.5 (decaimiento exponencial puro)",
                    "passed": ok2, "got": r2.get("lambda1", r2.get("error"))})'''


def main():
    with open(PATH, "r", encoding="utf-8") as f:
        src = f.read()

    backup = f"{PATH}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(PATH, backup)

    count = src.count(OLD)
    assert count == 1, f"se esperaba 1 ocurrencia, se encontraron {count} -- revisar a mano."
    src = src.replace(OLD, NEW, 1)

    with open(PATH, "w", encoding="utf-8") as f:
        f.write(src)

    ast.parse(src)
    print(f"Patch aplicado OK. Backup: {backup}")


if __name__ == "__main__":
    main()
