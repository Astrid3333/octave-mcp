#!/usr/bin/env python3
"""
Agrega mode="validate" a compute_hilbert_transform en hilbert_tool.py.

A diferencia de compute_lyapunov_v2, esta tool ya usa el patron correcto
en server.py (importa HILBERT_TOOL_SCHEMA directo, sin duplicado
hardcodeado -- confirmado via grep), asi que este patch alcanza solo y
solo con este archivo, sin tocar server.py.

Autochequeo con dos presets sinteticos de forma analitica conocida:
- am_chirp: envolvente = 1 + 0.5*sin(2*pi*fm*t), fm=3 Hz.
- fm_chirp: frecuencia instantanea = rampa lineal f0 -> f1 (20 -> 80 Hz).
Se descarta el primer/ultimo 15% de las muestras por artefactos de borde
conocidos de la Hilbert transform via FFT (truncamiento de la senal),
no error de implementacion.
"""
import ast
import shutil
import sys
from datetime import datetime

TARGET = "hilbert_tool.py"

OLD_SIG = '''    detrend=True,
    n_output_points=200,
    **kwargs,
):
    n_samples = int(round(fs * duration))'''

NEW_SIG = '''    detrend=True,
    n_output_points=200,
    mode=None,
    **kwargs,
):
    if mode == "validate":
        return _validate_hilbert()

    n_samples = int(round(fs * duration))'''

OLD_MAIN_ANCHOR = '''if __name__ == "__main__":'''

VALIDATE_FN = '''def _validate_hilbert():
    """
    Autochequeo con dos presets sinteticos de forma analitica conocida:
    - am_chirp: envolvente conocida = 1 + 0.5*sin(2*pi*fm*t), fm=3 Hz.
    - fm_chirp: frecuencia instantanea conocida = f0 + k*t (rampa lineal),
      f0=20, f1=80, k=(f1-f0)/duration.
    Se descartan los bordes (primer/ultimo 15% de las muestras) porque
    la transformada de Hilbert via FFT tiene artefactos de borde
    conocidos (efecto de truncamiento de la senal, no error del metodo).
    """
    import math

    checks = []
    tol_env = 0.05
    tol_freq = 3.0  # Hz, generoso por el ruido de la derivada de fase

    # --- am_chirp: valida envolvente ---
    fm = 3.0
    r1 = compute_hilbert_transform(preset="am_chirp", fs=1000.0, duration=2.0, n_output_points=400)
    t1 = r1["t"]
    env1 = r1["envelope"]
    n1 = len(t1)
    lo1, hi1 = int(0.15 * n1), int(0.85 * n1)
    errs1 = [abs(env1[i] - (1 + 0.5 * math.sin(2 * math.pi * fm * t1[i]))) for i in range(lo1, hi1)]
    max_err1 = max(errs1) if errs1 else float("inf")
    ok1 = max_err1 < tol_env
    checks.append({
        "name": "am_chirp: envolvente ~ 1+0.5*sin(2*pi*3*t) (zona central, sin bordes)",
        "passed": ok1, "got": f"max_err={max_err1:.4g}",
    })

    # --- fm_chirp: valida frecuencia instantanea ---
    f0, f1, dur = 20.0, 80.0, 1.0
    k = (f1 - f0) / dur
    r2 = compute_hilbert_transform(preset="fm_chirp", fs=1000.0, duration=dur, n_output_points=400)
    t2 = r2["t"]
    freq2 = r2["inst_freq"]
    n2 = len(t2)
    lo2, hi2 = int(0.15 * n2), int(0.85 * n2)
    errs2 = [abs(freq2[i] - (f0 + k * t2[i])) for i in range(lo2, hi2)]
    max_err2 = max(errs2) if errs2 else float("inf")
    ok2 = max_err2 < tol_freq
    checks.append({
        "name": f"fm_chirp: freq. instantanea ~ rampa lineal {f0}->{f1} Hz (zona central, sin bordes)",
        "passed": ok2, "got": f"max_err={max_err2:.4g} Hz",
    })

    return {"mode": "validate", "validation_passed": bool(all(c["passed"] for c in checks)), "checks": checks}


if __name__ == "__main__":'''

OLD_SCHEMA = '''            "n_output_points": {
                "type": "integer",
                "default": 200,
                "description": "Número de puntos a devolver (submuestreo uniforme para no saturar la respuesta).",
            },
        },
        "required": [],
    },
}'''

NEW_SCHEMA = '''            "n_output_points": {
                "type": "integer",
                "default": 200,
                "description": "Número de puntos a devolver (submuestreo uniforme para no saturar la respuesta).",
            },
            "mode": {
                "type": "string",
                "enum": ["validate"],
                "description": "Si es 'validate', ejecuta el autochequeo interno (envolvente/frecuencia instantanea contra formas analiticas conocidas de am_chirp/fm_chirp) e ignora el resto de los parametros.",
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
    with open(TARGET, encoding="utf-8") as f:
        src = f.read()

    backup = f"{TARGET}.bak.{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy(TARGET, backup)

    src = apply(src, OLD_SIG, NEW_SIG, "firma compute_hilbert_transform + early return validate")
    src = apply(src, OLD_MAIN_ANCHOR, VALIDATE_FN, "insercion de _validate_hilbert antes de __main__")
    src = apply(src, OLD_SCHEMA, NEW_SCHEMA, "propiedad mode en HILBERT_TOOL_SCHEMA")

    try:
        ast.parse(src)
    except SyntaxError as e:
        print(f"ERROR: el resultado no parsea como Python valido: {e}", file=sys.stderr)
        sys.exit(1)

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(src)

    print(f"Patch aplicado OK. Backup: {backup}")
    print("Confirmar con:")
    print('  python3 -c "from hilbert_tool import compute_hilbert_transform as c; import json; print(json.dumps(c(mode=\'validate\'), indent=2, ensure_ascii=False))"')
    print("Recordar: server.py importa HILBERT_TOOL_SCHEMA directo (no hardcodeado), asi que no hace falta tocar server.py.")


if __name__ == "__main__":
    main()
