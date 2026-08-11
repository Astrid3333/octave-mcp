"""
quantum_astro_tool.py

Fase 1 del plan quantum_astro_tool: andamiaje de algebra de operadores
cuanticos, reutilizable como base para Fase 2 (cosmologia semiclasica /
correcciones LQG a Friedmann) y Fase 3 (MCMC de parametros cosmologicos
via stochastic_processes_tool).

mode: "operator_algebra"
  operation:
    - "commutator"        -> [A, B] = AB - BA
    - "anticommutator"     -> {A, B} = AB + BA
    - "tensor_product"     -> kron(M1, M2, ..., Mn)
    - "pauli"               -> matrices de Pauli (sigma_x, sigma_y, sigma_z, I)
    - "ladder_operators"    -> a, a_dagger, n_op para un oscilador truncado a n_levels
    - "hamiltonian"         -> construye un Hamiltoniano estandar (ver hamiltonian_type)

hamiltonian_type (solo si operation == "hamiltonian"):
    - "harmonic_oscillator" -> H = hbar*omega*(a_dag a + 1/2)
    - "spin_field"          -> H = -gamma * (Bx*Sx + By*Sy + Bz*Sz), spin-1/2
    - "jaynes_cummings"     -> H = wc*a_dag a + (wa/2)*sigma_z + g*(acoplamiento)

Convencion numerica:
  Los numeros complejos se representan en JSON como [re, im] (par de floats)
  o como un solo float si la parte imaginaria es 0. Las matrices/vectores son
  listas anidadas de esos elementos. La salida usa el mismo formato.

Diagnosticos automaticos incluidos cuando aplica:
  - is_hermitian (para Hamiltonianos y operadores de salida cuadrados)
  - eigenvalues (autovalores; para H hermitico deberian ser reales dentro
    de una tolerancia numerica)
  - trace
"""

import numpy as np
from functools import reduce


# ---------------------------------------------------------------------------
# Parseo / serializacion de numeros y matrices complejas en formato JSON-safe
# ---------------------------------------------------------------------------

def _parse_complex(x):
    if isinstance(x, (int, float)):
        return complex(x, 0.0)
    if isinstance(x, list) and len(x) == 2:
        return complex(x[0], x[1])
    raise ValueError(f"Elemento complejo invalido: {x!r} (esperado numero o [re, im])")


def _parse_matrix(m):
    return np.array([[_parse_complex(e) for e in row] for row in m], dtype=complex)


def _complex_to_json(c, tol=1e-12):
    re = float(np.real(c))
    im = float(np.imag(c))
    if abs(im) < tol:
        return round(re, 12)
    return [round(re, 12), round(im, 12)]


def _matrix_to_json(M):
    return [[_complex_to_json(c) for c in row] for row in np.asarray(M)]


def _vector_to_json(v):
    return [_complex_to_json(c) for c in np.asarray(v)]


def _hermiticity_check(M, tol=1e-9):
    M = np.asarray(M)
    return bool(np.allclose(M, M.conj().T, atol=tol))


def _eig_summary(M, tol=1e-9):
    M = np.asarray(M)
    if _hermiticity_check(M, tol=tol):
        vals = np.linalg.eigvalsh(M)
        return [round(float(v), 12) for v in vals], True
    vals = np.linalg.eigvals(M)
    return [_complex_to_json(v) for v in vals], False


# ---------------------------------------------------------------------------
# Bloques basicos de algebra de operadores
# ---------------------------------------------------------------------------

def commutator(A, B):
    return A @ B - B @ A


def anticommutator(A, B):
    return A @ B + B @ A


def tensor_product(mats):
    return reduce(np.kron, mats)


def pauli_matrices():
    sx = np.array([[0, 1], [1, 0]], dtype=complex)
    sy = np.array([[0, -1j], [1j, 0]], dtype=complex)
    sz = np.array([[1, 0], [0, -1]], dtype=complex)
    I2 = np.eye(2, dtype=complex)
    return sx, sy, sz, I2


def ladder_operators(n_levels):
    """a (aniquilacion) truncado a n_levels: a|n> = sqrt(n)|n-1>."""
    a = np.zeros((n_levels, n_levels), dtype=complex)
    for i in range(n_levels - 1):
        a[i, i + 1] = np.sqrt(i + 1)
    a_dag = a.conj().T
    n_op = a_dag @ a
    return a, a_dag, n_op


# ---------------------------------------------------------------------------
# Hamiltonianos estandar
# ---------------------------------------------------------------------------

def harmonic_oscillator_hamiltonian(n_levels, omega=1.0, hbar=1.0):
    a, a_dag, n_op = ladder_operators(n_levels)
    H = hbar * omega * (n_op + 0.5 * np.eye(n_levels, dtype=complex))
    return H


def spin_field_hamiltonian(Bx=0.0, By=0.0, Bz=0.0, gyromagnetic=1.0):
    sx, sy, sz, _ = pauli_matrices()
    H = -gyromagnetic * (Bx * sx + By * sy + Bz * sz) / 2.0
    return H


def jaynes_cummings_hamiltonian(n_cavity_levels, omega_c, omega_a, g, rwa=True):
    a, a_dag, n_op = ladder_operators(n_cavity_levels)
    I_cav = np.eye(n_cavity_levels, dtype=complex)
    sx, sy, sz, I_atom = pauli_matrices()

    sigma_plus = np.array([[0, 1], [0, 0]], dtype=complex)   # |e><g|
    sigma_minus = sigma_plus.conj().T                         # |g><e|

    H_cav = omega_c * np.kron(n_op, I_atom)
    H_atom = (omega_a / 2.0) * np.kron(I_cav, sz)

    if rwa:
        H_int = g * (np.kron(a, sigma_plus) + np.kron(a_dag, sigma_minus))
    else:
        H_int = g * np.kron(a + a_dag, sigma_plus + sigma_minus)

    H = H_cav + H_atom + H_int
    return H


_HAMILTONIAN_BUILDERS = {
    "harmonic_oscillator": lambda p: harmonic_oscillator_hamiltonian(
        n_levels=int(p.get("n_levels", 10)),
        omega=float(p.get("omega", 1.0)),
        hbar=float(p.get("hbar", 1.0)),
    ),
    "spin_field": lambda p: spin_field_hamiltonian(
        Bx=float(p.get("Bx", 0.0)),
        By=float(p.get("By", 0.0)),
        Bz=float(p.get("Bz", 1.0)),
        gyromagnetic=float(p.get("gyromagnetic", 1.0)),
    ),
    "jaynes_cummings": lambda p: jaynes_cummings_hamiltonian(
        n_cavity_levels=int(p.get("n_cavity_levels", 6)),
        omega_c=float(p.get("omega_c", 1.0)),
        omega_a=float(p.get("omega_a", 1.0)),
        g=float(p.get("g", 0.1)),
        rwa=bool(p.get("rwa", True)),
    ),
}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def compute_quantum_astro_tool(mode, params=None):
    params = params or {}

    if mode != "operator_algebra":
        raise ValueError(
            f"mode '{mode}' no reconocido en Fase 1. "
            "Disponible: 'operator_algebra'. "
            "'hamiltonian_evolution', 'density_matrix', 'partition_function' "
            "llegan en fases posteriores."
        )

    operation = params.get("operation")
    if operation is None:
        raise ValueError("Falta 'operation' dentro de params para mode='operator_algebra'.")

    if operation == "commutator":
        A = _parse_matrix(params["matrices"][0])
        B = _parse_matrix(params["matrices"][1])
        C = commutator(A, B)
        return {
            "mode": mode,
            "operation": operation,
            "result": _matrix_to_json(C),
            "is_hermitian": _hermiticity_check(C),
            "note": "[A,B] = AB - BA. Si A y B son hermiticos, [A,B] es antihermitico (i*[A,B] es hermitico).",
        }

    if operation == "anticommutator":
        A = _parse_matrix(params["matrices"][0])
        B = _parse_matrix(params["matrices"][1])
        C = anticommutator(A, B)
        return {
            "mode": mode,
            "operation": operation,
            "result": _matrix_to_json(C),
            "is_hermitian": _hermiticity_check(C),
        }

    if operation == "tensor_product":
        mats = [_parse_matrix(m) for m in params["matrices"]]
        M = tensor_product(mats)
        return {
            "mode": mode,
            "operation": operation,
            "result": _matrix_to_json(M),
            "shape": list(M.shape),
        }

    if operation == "pauli":
        sx, sy, sz, I2 = pauli_matrices()
        return {
            "mode": mode,
            "operation": operation,
            "sigma_x": _matrix_to_json(sx),
            "sigma_y": _matrix_to_json(sy),
            "sigma_z": _matrix_to_json(sz),
            "identity": _matrix_to_json(I2),
        }

    if operation == "ladder_operators":
        n_levels = int(params.get("n_levels", 5))
        a, a_dag, n_op = ladder_operators(n_levels)
        return {
            "mode": mode,
            "operation": operation,
            "n_levels": n_levels,
            "a": _matrix_to_json(a),
            "a_dagger": _matrix_to_json(a_dag),
            "n_operator": _matrix_to_json(n_op),
            "note": "a|n> = sqrt(n)|n-1>, truncado a n_levels (aproximacion valida si la ocupacion esperada << n_levels).",
        }

    if operation == "hamiltonian":
        h_type = params.get("hamiltonian_type")
        if h_type not in _HAMILTONIAN_BUILDERS:
            raise ValueError(
                f"hamiltonian_type '{h_type}' no reconocido. "
                f"Disponibles: {sorted(_HAMILTONIAN_BUILDERS.keys())}"
            )
        h_params = params.get("params", {})
        H = _HAMILTONIAN_BUILDERS[h_type](h_params)
        eigenvalues, is_herm = _eig_summary(H)
        return {
            "mode": mode,
            "operation": operation,
            "hamiltonian_type": h_type,
            "H": _matrix_to_json(H),
            "shape": list(H.shape),
            "is_hermitian": is_herm,
            "eigenvalues": eigenvalues,
            "trace": _complex_to_json(np.trace(H)),
        }

    raise ValueError(
        f"operation '{operation}' no reconocida. "
        "Disponibles: commutator, anticommutator, tensor_product, pauli, "
        "ladder_operators, hamiltonian."
    )


# ---------------------------------------------------------------------------
# Schema MCP (mismo formato que el resto de tus tools en octave-mcp)
# ---------------------------------------------------------------------------

QUANTUM_ASTRO_TOOL_SCHEMA = {
    "name": "quantum_astro_tool",
    "description": (
        "Fase 1 de andamiaje de mecanica cuantica: algebra de operadores "
        "(conmutadores, anticonmutadores, producto tensorial, matrices de "
        "Pauli, operadores escalera) y construccion de Hamiltonianos estandar "
        "(oscilador armonico, spin en campo magnetico, Jaynes-Cummings). "
        "Base reutilizable para modos futuros hamiltonian_evolution "
        "(via solver de EDOs existente), density_matrix y partition_function, "
        "y para el puente a cosmologia semiclasica (Friedmann con correcciones LQG)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["operator_algebra"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "commutator",
                            "anticommutator",
                            "tensor_product",
                            "pauli",
                            "ladder_operators",
                            "hamiltonian",
                        ],
                    },
                    "matrices": {
                        "type": "array",
                        "description": "Lista de matrices (listas anidadas). Cada elemento numero o [re, im].",
                    },
                    "n_levels": {
                        "type": "integer",
                        "description": "Truncamiento del espacio de Fock para ladder_operators.",
                    },
                    "hamiltonian_type": {
                        "type": "string",
                        "enum": ["harmonic_oscillator", "spin_field", "jaynes_cummings"],
                    },
                    "params": {
                        "type": "object",
                        "description": (
                            "Parametros especificos del hamiltonian_type: "
                            "harmonic_oscillator {n_levels, omega, hbar}; "
                            "spin_field {Bx, By, Bz, gyromagnetic}; "
                            "jaynes_cummings {n_cavity_levels, omega_c, omega_a, g, rwa}."
                        ),
                    },
                },
                "required": ["operation"],
            },
        },
        "required": ["mode", "params"],
    },
}
