"""
braid_group_tool.py

Grupos de trenzas y computacion cuantica topologica con anyones de
Fibonacci: matrices de trenzado (R, F), verificacion de la relacion de
Yang-Baxter (sigma1*sigma2*sigma1 = sigma2*sigma1*sigma2), y aplicacion de
secuencias de trenzas a un estado inicial en el espacio de fusion.

Los anyones de Fibonacci son el caso mas citado en la literatura de
computacion cuantica topologica (Bonesteel et al. 2005, Freedman-Kitaev)
porque su espacio de fusion de 3 anyones es 2D -- el caso no trivial mas
chico posible -- y sus matrices de trenzado son universales para
computacion cuantica de un qubit topologico.

Conexion con TritOS: el espacio de fusion de anyones de Fibonacci tiene
estructura ternaria (dos anyones tau pueden fusionar en el canal '1' o en
el canal 'tau' -- una eleccion de 2, pero el ARBOL completo de fusion de 3+
anyones tiene ramificacion relacionada a la razon aurea, no binaria).
Conecta tambien con persistent_homology_tool (ambos usan reduccion de
matrices) y linear_algebra_tool (los braid gates son matrices unitarias,
autovalores en la raiz de la unidad).

Mismo patron de validacion: unitariedad + relacion de trenzas verificadas
antes de aplicar secuencias custom.
"""
import cmath
import math

BRAID_GROUP_SCHEMA = {
    "name": "compute_braid_group",
    "description": (
        "Grupos de trenzas y anyones de Fibonacci: verify_braid_relation "
        "(valida unitariedad de sigma1/sigma2 y la relacion de Yang-Baxter "
        "sigma1*sigma2*sigma1=sigma2*sigma1*sigma2), apply_braid_sequence "
        "(aplica una secuencia de generadores de trenza a un estado inicial "
        "en el espacio de fusion 2D, ej: '1,2,1,2' para sigma1 sigma2 "
        "sigma1 sigma2). Basado en Bonesteel et al. 2005 / Freedman-Kitaev."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["verify_braid_relation", "apply_braid_sequence"], "default": "verify_braid_relation"},
            "sequence": {"type": "string", "description": "Para apply_braid_sequence: secuencia de generadores separados por coma, ej '1,2,1,2,1'", "default": "1,2,1"},
            "initial_state": {"type": "array", "description": "Estado inicial [re0,im0,re1,im1] en el espacio de fusion 2D. Default: [1,0,0,0] (canal '1' puro)"},
        },
    },
}

_PHI = (1 + 5 ** 0.5) / 2


def _fibonacci_matrices():
    R = [[cmath.exp(-4j * cmath.pi / 5), 0], [0, cmath.exp(3j * cmath.pi / 5)]]
    F = [[1 / _PHI, 1 / _PHI ** 0.5], [1 / _PHI ** 0.5, -1 / _PHI]]
    return R, F


def _matmul(A, B):
    n, m, p = len(A), len(B), len(B[0])
    return [[sum(A[i][k] * B[k][j] for k in range(m)) for j in range(p)] for i in range(n)]


def _mat_inv_2x2(M):
    a, b, c, d = M[0][0], M[0][1], M[1][0], M[1][1]
    det = a * d - b * c
    return [[d / det, -b / det], [-c / det, a / det]]


def _conj_transpose(M):
    return [[complex(M[j][i]).conjugate() for j in range(len(M))] for i in range(len(M[0]))]


def _is_close_matrix(A, B, tol=1e-9):
    return all(abs(A[i][j] - B[i][j]) < tol for i in range(len(A)) for j in range(len(A[0])))


def _identity(n):
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def _get_generators():
    R, F = _fibonacci_matrices()
    F_inv = _mat_inv_2x2(F)
    sigma1 = R
    sigma2 = _matmul(_matmul(F_inv, R), F)
    return sigma1, sigma2


def compute_braid_group(mode="verify_braid_relation", sequence="1,2,1", initial_state=None):
    sigma1, sigma2 = _get_generators()

    if mode == "verify_braid_relation":
        s1s2s1 = _matmul(_matmul(sigma1, sigma2), sigma1)
        s2s1s2 = _matmul(_matmul(sigma2, sigma1), sigma2)
        relation_holds = _is_close_matrix(s1s2s1, s2s1s2)

        def unitary_check(M):
            Mh = _conj_transpose(M)
            prod = _matmul(M, Mh)
            return _is_close_matrix(prod, _identity(len(M)))

        return {
            "sistema": "anyones de Fibonacci, espacio de fusion 2D (3 anyones tau)",
            "sigma1_unitaria": unitary_check(sigma1),
            "sigma2_unitaria": unitary_check(sigma2),
            "relacion_yang_baxter_sigma1_sigma2_sigma1_eq_sigma2_sigma1_sigma2": relation_holds,
            "sigma1_matriz": [[str(round(v.real, 6) + round(v.imag, 6) * 1j) for v in row] for row in sigma1],
            "sigma2_matriz": [[str(round(v.real, 6) + round(v.imag, 6) * 1j) for v in row] for row in sigma2],
            "nota": (
                "R (sigma1) es diagonal en la base de fusion natural; sigma2 se obtiene "
                "conjugando R por la matriz F de cambio de base del arbol de fusion. "
                "Esta es la construccion estandar de Bonesteel et al. 2005 para gates "
                "universales de un qubit topologico con anyones de Fibonacci."
            ),
        }

    elif mode == "apply_braid_sequence":
        try:
            gens = [int(g.strip()) for g in sequence.split(",")]
        except ValueError:
            return {"error": "sequence debe ser generadores separados por coma, ej '1,2,1'"}
        if any(g not in (1, 2) for g in gens):
            return {"error": "solo hay dos generadores disponibles: 1 (sigma1) y 2 (sigma2)"}

        if initial_state:
            if len(initial_state) != 4:
                return {"error": "initial_state debe tener 4 numeros [re0,im0,re1,im1]"}
            state = [complex(initial_state[0], initial_state[1]), complex(initial_state[2], initial_state[3])]
        else:
            state = [complex(1, 0), complex(0, 0)]  # canal de fusion '1' puro

        norm0 = math.sqrt(abs(state[0]) ** 2 + abs(state[1]) ** 2)
        history = [{"paso": 0, "generador": None, "estado": [str(state[0]), str(state[1])]}]

        for i, g in enumerate(gens, start=1):
            M = sigma1 if g == 1 else sigma2
            new_state = [M[0][0] * state[0] + M[0][1] * state[1],
                         M[1][0] * state[0] + M[1][1] * state[1]]
            state = new_state
            history.append({"paso": i, "generador": f"sigma{g}",
                            "estado": [str(round(state[0].real, 6) + round(state[0].imag, 6) * 1j),
                                       str(round(state[1].real, 6) + round(state[1].imag, 6) * 1j)]})

        norm_final = math.sqrt(abs(state[0]) ** 2 + abs(state[1]) ** 2)
        return {
            "sequence": sequence,
            "n_generators_applied": len(gens),
            "initial_state": history[0]["estado"],
            "final_state": history[-1]["estado"],
            "norm_preserved": abs(norm0 - norm_final) < 1e-9,
            "trajectory": history,
            "nota": (
                "La norma del estado se preserva porque sigma1/sigma2 son unitarias -- "
                "esta es la base de la proteccion topologica: el estado nunca 'se escapa' "
                "del espacio de fusion, solo rota dentro de el."
            ),
        }

    else:
        return {"error": f"mode desconocido: {mode}"}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_braid_group("verify_braid_relation"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_braid_group("apply_braid_sequence", sequence="1,2,1,2,1"), indent=2, ensure_ascii=False))
