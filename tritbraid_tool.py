"""
tritbraid_tool.py

DSL minimo "TritBraid": los programas son secuencias de trenzas sobre el
espacio de fusion de anyones de Fibonacci (3 anyones tau, espacio 2D),
donde cada "medicion" colapsa el estado a un trit ternario (-1, 0, +1).

Puente concreto entre computacion cuantica topologica (braid_group_tool)
y el sistema ternario de TritOS.

Fisica: misma construccion estandar de Bonesteel et al. 2005 usada en
braid_group_tool -- sigma1 es diagonal en la base de fusion natural
(R-matrix), sigma2 se obtiene conjugando sigma1 por la matriz F de
cambio de base del arbol de fusion (F^2 = I, real, simetrica).

Tokens del programa (separados por coma o espacio):
  "0"  -> identidad (no-op unitario)
  "1"  -> aplica sigma1 (diagonal, no mezcla canales de fusion)
  "2"  -> aplica sigma2 (mezcla canales via conjugacion F)
  "M"  -> mide: colapso proyectivo (regla de Born), fija el trit actual

Convencion de trit:
  0   -> estado aun no medido (default inicial, canal de fusion "1"/vacio
         sin colapsar todavia)
  -1  -> colapsado al canal de fusion "1" (vacio)
  +1  -> colapsado al canal de fusion "tau"

Tras el primer colapso, aplicar "0" dejar el trit intacto (probabilidad
exacta 1.0 en la siguiente medicion); aplicar "1" repetidamente tampoco
cambia el trit (sigma1 es diagonal, no mezcla canales); aplicar "2" si
puede cambiar el trit (mezcla los canales via F).
"""

import cmath
import math
import random


# ---------------------------------------------------------------------------
# Construccion estandar Bonesteel et al. 2005 (misma que braid_group_tool)
# ---------------------------------------------------------------------------

PHI = (1 + math.sqrt(5)) / 2  # razon aurea

def _sigma1_matrix():
    # R-matrix: diagonal en la base de fusion natural (|1>, |tau>)
    r_vac = cmath.exp(-1j * 4 * math.pi / 5)
    r_tau = cmath.exp(1j * 3 * math.pi / 5)
    return [[r_vac, 0j], [0j, r_tau]]


def _f_matrix():
    # F-matrix de Fibonacci: real, simetrica, F^2 = I
    inv_phi = 1 / PHI
    inv_sqrt_phi = 1 / math.sqrt(PHI)
    return [[inv_phi, inv_sqrt_phi], [inv_sqrt_phi, -inv_phi]]


def _matmul2(a, b):
    return [
        [a[0][0] * b[0][0] + a[0][1] * b[1][0], a[0][0] * b[0][1] + a[0][1] * b[1][1]],
        [a[1][0] * b[0][0] + a[1][1] * b[1][0], a[1][0] * b[0][1] + a[1][1] * b[1][1]],
    ]


def _sigma2_matrix():
    # sigma2 = F * sigma1 * F  (F es su propia inversa)
    f = _f_matrix()
    s1 = _sigma1_matrix()
    return _matmul2(_matmul2(f, s1), f)


SIGMA = {
    "0": [[1 + 0j, 0j], [0j, 1 + 0j]],  # identidad
    "1": _sigma1_matrix(),
    "2": _sigma2_matrix(),
}


def _apply(matrix, state):
    c0, c1 = state
    return (
        matrix[0][0] * c0 + matrix[0][1] * c1,
        matrix[1][0] * c0 + matrix[1][1] * c1,
    )


def _norm2(state):
    return abs(state[0]) ** 2 + abs(state[1]) ** 2


def _measure(state, rng):
    """Colapso proyectivo (regla de Born). Devuelve (trit, prob_usada, nuevo_estado)."""
    p0 = abs(state[0]) ** 2
    p1 = abs(state[1]) ** 2
    total = p0 + p1
    p0n = p0 / total if total > 0 else 0.5
    r = rng.random()
    if r < p0n:
        return -1, p0n, (1 + 0j, 0j)
    else:
        return 1, 1 - p0n, (0j, 1 + 0j)


def _parse_program(program):
    tokens = [t.strip() for t in program.replace(",", " ").split() if t.strip()]
    for t in tokens:
        if t not in ("0", "1", "2", "M"):
            raise ValueError(f"token invalido en programa TritBraid: {t!r} (validos: 0,1,2,M)")
    return tokens


def _fmt(c):
    return f"{c.real:.6f}{'+' if c.imag >= 0 else ''}{c.imag:.6f}j"


# ---------------------------------------------------------------------------
# mode: run_program
# ---------------------------------------------------------------------------

def _run_program(program, seed, initial_state):
    tokens = _parse_program(program)
    rng = random.Random(seed)

    if initial_state is not None:
        re0, im0, re1, im1 = initial_state
        state = (complex(re0, im0), complex(re1, im1))
    else:
        state = (1 + 0j, 0j)  # canal "1" (vacio) por defecto

    current_trit = 0
    trace = []
    trace.append({"paso": 0, "token": None, "estado": [_fmt(state[0]), _fmt(state[1])], "trit": current_trit})

    for i, tok in enumerate(tokens, start=1):
        if tok == "M":
            trit, prob, state = _measure(state, rng)
            current_trit = trit
            trace.append({
                "paso": i, "token": "M", "resultado_medicion": trit,
                "probabilidad_del_resultado": round(prob, 6),
                "estado_colapsado": [_fmt(state[0]), _fmt(state[1])],
                "trit": current_trit,
            })
        else:
            state = _apply(SIGMA[tok], state)
            trace.append({
                "paso": i, "token": tok, "estado": [_fmt(state[0]), _fmt(state[1])],
                "norma": round(_norm2(state), 9), "trit": current_trit,
            })

    return {
        "programa": program,
        "seed": seed,
        "trace": trace,
        "trit_final": current_trit,
        "n_pasos": len(tokens),
    }


# ---------------------------------------------------------------------------
# mode: validate_physics
# ---------------------------------------------------------------------------

def _validate_physics(n_trials=200, seed=1234):
    rng = random.Random(seed)

    # 1) unitariedad: sigma1 y sigma2 preservan la norma
    unit_ok = True
    for tok in ("1", "2"):
        s = (0.6 + 0.2j, 0.5 - 0.3j)
        n0 = _norm2(s)
        s2 = _apply(SIGMA[tok], s)
        n1 = _norm2(s2)
        if abs(n0 - n1) > 1e-9:
            unit_ok = False

    # 2) identidad tras colapso: no cambia el trit (prob exacta 1.0)
    identidad_ok = True
    for _ in range(n_trials):
        state = (1 + 0j, 0j)
        trit, _, state = _measure(state, rng)
        state = _apply(SIGMA["0"], state)
        trit2, prob2, state = _measure(state, rng)
        if trit2 != trit or abs(prob2 - 1.0) > 1e-9:
            identidad_ok = False
            break

    # 3) sigma1 es diagonal: repetirlo tras colapso tampoco cambia el trit
    sigma1_diag_ok = True
    for _ in range(n_trials):
        state = (1 + 0j, 0j)
        trit, _, state = _measure(state, rng)
        for _ in range(3):
            state = _apply(SIGMA["1"], state)
        trit2, prob2, state = _measure(state, rng)
        if trit2 != trit or abs(prob2 - 1.0) > 1e-9:
            sigma1_diag_ok = False
            break

    # 4) sigma2 mezcla los canales: tras colapso, a veces cambia el trit,
    #    con probabilidad consistente con la regla de Born (|F_01|^2)
    resultados_sigma2 = []
    for _ in range(n_trials):
        state = (1 + 0j, 0j)
        trit, _, state = _measure(state, rng)
        state = _apply(SIGMA["2"], state)
        trit2, prob2, state = _measure(state, rng)
        resultados_sigma2.append(trit2 != trit)

    frac_cambia = sum(resultados_sigma2) / len(resultados_sigma2)
    # probabilidad teorica de cambiar de canal tras sigma2 desde un estado
    # colapsado en el canal "1": |sigma2[1][0]|^2 (elemento fuera de diagonal)
    s2 = SIGMA["2"]
    p_teorica_cambio = abs(s2[1][0]) ** 2
    sigma2_mezcla_ok = (
        any(resultados_sigma2)  # al menos alguna vez cambia
        and not all(resultados_sigma2)  # y al menos alguna vez no cambia
        and abs(frac_cambia - p_teorica_cambio) < 0.12  # estadisticamente cerca
    )

    todos_correctos = unit_ok and identidad_ok and sigma1_diag_ok and sigma2_mezcla_ok

    return {
        "unitariedad_preservada": unit_ok,
        "identidad_preserva_colapso": identidad_ok,
        "sigma1_diagonal_preserva_colapso": sigma1_diag_ok,
        "sigma2_puede_cambiar_colapso": sigma2_mezcla_ok,
        "sigma2_fraccion_cambio_empirica": round(frac_cambia, 4),
        "sigma2_probabilidad_cambio_teorica": round(p_teorica_cambio, 4),
        "n_trials": n_trials,
        "todos_correctos": todos_correctos,
    }


# ---------------------------------------------------------------------------
# entrypoint
# ---------------------------------------------------------------------------

def compute_tritbraid(mode="validate_physics", program="1,2,M,0,M,2,M", seed=42, initial_state=None):
    if mode == "run_program":
        return _run_program(program, seed, initial_state)
    elif mode == "validate_physics":
        return _validate_physics(seed=seed)
    else:
        return {"error": f"modo desconocido: {mode!r} (validos: run_program, validate_physics)"}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_tritbraid(mode="validate_physics"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_tritbraid(mode="run_program", program="1,2,M,0,M,2,M"), indent=2, ensure_ascii=False))
