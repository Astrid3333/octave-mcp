"""
Agrega mode="validate" a compute_lyapunov_exponent en lyapunov_tool_v2.py
(registrada como tool compute_lyapunov_v2 en server.py).

Mismo enfoque que lyapunov_tool.py: sistemas lineales 3D desacoplados
(y'=k*y en cada componente) con lambda1 analitico exacto == k, en vez de
presets caoticos. Se usa 3D desde el arranque (no 1D) porque este archivo
comparte el mismo script Octave interno con el printf final hardcodeado a
y(1),y(2),y(3) -- un vector de 1 elemento revienta con indice fuera de rango
(bug ya encontrado y documentado en lyapunov_tool.py).

Los casos de validate no pasan run_id, asi que la rama de guardado de
trayectoria (save_run / workspace_tool) nunca se ejecuta durante el
autochequeo -- sin dependencias extra en juego.

IMPORTANTE: no probado con Octave real (no disponible en el sandbox).
Confirmar antes de commitear.

Uso:
    python3 patch_add_validate_lyapunov_v2.py
"""
import ast
import shutil
from datetime import datetime

PATH = "lyapunov_tool_v2.py"

OLD_SIG = '''    run_id: str | None = None,
    save_trajectory_every: int = 10,
) -> dict:'''

NEW_SIG = '''    run_id: str | None = None,
    save_trajectory_every: int = 10,
    mode: str | None = None,
    **kwargs,
) -> dict:'''

OLD_BODY_START = '''        dict con lambda1, interpretacion, y metadatos de la corrida.
    """
    if system == "custom":'''

NEW_BODY_START = '''        dict con lambda1, interpretacion, y metadatos de la corrida.
    """
    if mode == "validate":
        return _validate_lyapunov_v2(octave_bin=octave_bin, timeout_s=timeout_s)

    if system == "custom":'''

VALIDATE_FUNC = '''

def _validate_lyapunov_v2(octave_bin: str = "octave", timeout_s: int = 60):
    """
    Autochequeo con sistemas lineales 3D desacoplados de solucion analitica
    exacta: y'=k*y -> lambda1==k en cada componente. Se usa 3D (no 1D) porque
    el script Octave interno tiene el printf final hardcodeado a
    y(1),y(2),y(3) sin chequear la dimension real del vector de estado.
    No pasa run_id, asi que no dispara guardado de trayectoria.
    """
    checks = []
    tol = 0.02  # generoso: RK4 + renormalizacion sobre sistema lineal exacto

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
                    "passed": ok2, "got": r2.get("lambda1", r2.get("error"))})

    return {"mode": "validate", "validation_passed": bool(all(c["passed"] for c in checks)), "checks": checks}'''

OLD_SCHEMA_TAIL = '''            "save_trajectory_every": {
                "type": "integer",
                "default": 10,
                "description": "Guardar 1 de cada N pasos de la trayectoria (solo si run_id esta presente).",
            },
        },
        "required": [],
    },
}'''

NEW_SCHEMA_TAIL = '''            "save_trajectory_every": {
                "type": "integer",
                "default": 10,
                "description": "Guardar 1 de cada N pasos de la trayectoria (solo si run_id esta presente).",
            },
            "mode": {
                "type": "string",
                "enum": ["validate"],
                "description": "Si es 'validate', ejecuta el autochequeo interno (sistemas lineales con lambda1 exacto conocido) e ignora el resto de los parametros.",
            },
        },
        "required": [],
    },
}'''


def apply(src, old, new, label):
    count = src.count(old)
    assert count == 1, f"[{label}] se esperaba 1 ocurrencia, se encontraron {count} -- revisar a mano."
    return src.replace(old, new, 1)


def main():
    with open(PATH, "r", encoding="utf-8") as f:
        src = f.read()

    backup = f"{PATH}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(PATH, backup)

    src = apply(src, OLD_SIG, NEW_SIG, "firma compute_lyapunov_exponent")
    src = apply(src, OLD_BODY_START, NEW_BODY_START, "insercion del check mode==validate")
    src = apply(src, OLD_SCHEMA_TAIL, NEW_SCHEMA_TAIL, "schema")

    marker = "# --- Schema para registro manual"
    assert src.count(marker) == 1, "marcador del schema no encontrado -- revisar a mano."
    src = src.replace(marker, VALIDATE_FUNC.strip("\n") + "\n\n\n" + marker, 1)

    with open(PATH, "w", encoding="utf-8") as f:
        f.write(src)

    ast.parse(src)
    print(f"Patch aplicado OK. Backup: {backup}")
    print("IMPORTANTE: no probado con Octave real (no disponible en el sandbox).")
    print("Confirmar corriendo: python3 -c \"from lyapunov_tool_v2 import compute_lyapunov_exponent as c; import json; r=c(mode='validate'); print(json.dumps(r, indent=2, ensure_ascii=False))\"")


if __name__ == "__main__":
    main()
