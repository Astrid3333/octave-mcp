"""
Agrega mode="validate" a compute_lyapunov_exponent (lyapunov_tool.py).

Estrategia: en vez de validar contra un atractor caotico real (chen_lee,
lorenz, etc.), donde el "valor correcto" de lambda1 depende de la
sensibilidad numerica de la corrida y no hay forma limpia de fijar una
tolerancia chica, se usan dos sistemas LINEALES con solucion analitica
exacta:

    y' = +k*y  ->  lambda1 == +k exacto (crecimiento exponencial puro)
    y' = -k*y  ->  lambda1 == -k exacto (decaimiento exponencial puro)

Esto SI requiere Octave real (subprocess), por eso este patch se entrega
para que Astrid lo corra y confirme los valores antes de dar la validacion
por buena -- no fue probado end-to-end en el sandbox (sin Octave disponible
aca).

Uso:
    python3 patch_add_validate_lyapunov.py
"""
import ast
import shutil
from datetime import datetime

PATH = "lyapunov_tool.py"

OLD_SIG = '''def compute_lyapunov_exponent(
    system: str = "chen_lee",
    custom_equations: str | None = None,
    custom_params: dict | None = None,
    y0: list[float] | None = None,
    dt: float | None = None,
    n_steps: int = 20000,
    d0: float = 1e-8,
    octave_bin: str = "octave",
    timeout_s: int = 60,
) -> dict:'''

NEW_SIG = '''def compute_lyapunov_exponent(
    system: str = "chen_lee",
    custom_equations: str | None = None,
    custom_params: dict | None = None,
    y0: list[float] | None = None,
    dt: float | None = None,
    n_steps: int = 20000,
    d0: float = 1e-8,
    octave_bin: str = "octave",
    timeout_s: int = 60,
    mode: str | None = None,
    **kwargs,
) -> dict:
    if mode == "validate":
        return _validate_lyapunov(octave_bin=octave_bin, timeout_s=timeout_s)'''

VALIDATE_FUNC = '''

def _validate_lyapunov(octave_bin: str = "octave", timeout_s: int = 60):
    """
    Autochequeo con sistemas lineales de solucion analitica exacta:
    y'=k*y -> lambda1==k. No usa presets caoticos porque su lambda1
    "verdadero" depende de la sensibilidad numerica de la corrida y no
    admite una tolerancia chica y estable.
    """
    checks = []
    tol = 0.02  # generoso: RK4 + renormalizacion sobre sistema lineal exacto

    r1 = compute_lyapunov_exponent(
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
                    "passed": ok2, "got": r2.get("lambda1", r2.get("error"))})

    return {"mode": "validate", "validation_passed": bool(all(c["passed"] for c in checks)), "checks": checks}'''

OLD_SCHEMA_TAIL = '''            "n_steps": {"type": "integer", "default": 20000},
            "d0": {"type": "number", "default": 1e-8},
        },
        "required": [],
    },
}'''

NEW_SCHEMA_TAIL = '''            "n_steps": {"type": "integer", "default": 20000},
            "d0": {"type": "number", "default": 1e-8},
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
    src = apply(src, OLD_SCHEMA_TAIL, NEW_SCHEMA_TAIL, "schema")

    # Inserta _validate_lyapunov justo antes del schema (necesita que
    # compute_lyapunov_exponent ya este definida arriba, por eso va despues
    # de la funcion, no antes).
    marker = "# --- Schema para registro manual"
    assert src.count(marker) == 1, "marcador del schema no encontrado -- revisar a mano."
    src = src.replace(marker, VALIDATE_FUNC.strip("\n") + "\n\n\n" + marker, 1)

    with open(PATH, "w", encoding="utf-8") as f:
        f.write(src)

    ast.parse(src)
    print(f"Patch aplicado OK. Backup: {backup}")
    print("IMPORTANTE: este patch no se probo con Octave real (no disponible en el sandbox).")
    print("Confirmar corriendo: python3 -c \"from lyapunov_tool import compute_lyapunov_exponent as c; import json; r=c(mode='validate'); print(json.dumps(r, indent=2)); print(r['validation_passed'])\"")


if __name__ == "__main__":
    main()
