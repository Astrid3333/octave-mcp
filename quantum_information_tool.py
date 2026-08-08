#!/usr/bin/env python3
"""
quantum_information_tool.py
Simulacion de sistemas cuanticos de pocos qubits via representacion de
estado (statevector) con numpy puro, sin dependencia de qiskit/cirq:
vector de Bloch de un qubit, aplicacion de puertas cuanticas estandar
(Hadamard, Pauli X/Y/Z, CNOT, Toffoli) sobre registros de n qubits,
los algoritmos de Deutsch-Jozsa y Grover (amplificacion de amplitud),
entropia de von Neumann para cuantificar entrelazamiento entre
subsistemas, y una demostracion del codigo de correccion de errores por
repeticion de bit-flip (el bloque constructivo basico del codigo de
Shor de 9 qubits - la implementacion completa de Shor queda fuera de
alcance por complejidad, se documenta explicitamente).
Conexion con TritOS: los estados de Bloch y la logica de puertas dan
un puente natural hacia TritBraid (trenzas sobre espacio de fusion de
anyones de Fibonacci -> estados ternarios).
"""
import numpy as np

I2 = np.array([[1, 0], [0, 1]], dtype=complex)
X = np.array([[0, 1], [1, 0]], dtype=complex)
Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
Z = np.array([[1, 0], [0, -1]], dtype=complex)
H = (1 / np.sqrt(2)) * np.array([[1, 1], [1, -1]], dtype=complex)

GATES_1Q = {"I": I2, "X": X, "Y": Y, "Z": Z, "H": H}


def _kron_all(mats):
    out = mats[0]
    for m in mats[1:]:
        out = np.kron(out, m)
    return out


def _single_qubit_gate_matrix(gate, qubit_idx, n):
    mats = [GATES_1Q[gate] if i == qubit_idx else I2 for i in range(n)]
    return _kron_all(mats)


def _cnot_matrix(control, target, n):
    dim = 2 ** n
    M = np.zeros((dim, dim), dtype=complex)
    for x in range(dim):
        bits = [(x >> (n - 1 - i)) & 1 for i in range(n)]
        if bits[control] == 1:
            bits[target] ^= 1
        y = 0
        for b in bits:
            y = (y << 1) | b
        M[y, x] = 1.0
    return M


def _toffoli_matrix(c1, c2, target, n):
    dim = 2 ** n
    M = np.zeros((dim, dim), dtype=complex)
    for x in range(dim):
        bits = [(x >> (n - 1 - i)) & 1 for i in range(n)]
        if bits[c1] == 1 and bits[c2] == 1:
            bits[target] ^= 1
        y = 0
        for b in bits:
            y = (y << 1) | b
        M[y, x] = 1.0
    return M


def _zero_state(n):
    v = np.zeros(2 ** n, dtype=complex)
    v[0] = 1.0
    return v


def _amp_str_list(state, max_show=16):
    dim = len(state)
    out = []
    for i in range(min(dim, max_show)):
        amp = state[i]
        if abs(amp) > 1e-9:
            out.append({"basis": format(i, f"0{int(np.log2(dim))}b"),
                        "amplitude_real": round(float(amp.real), 6),
                        "amplitude_imag": round(float(amp.imag), 6),
                        "probability": round(float(abs(amp) ** 2), 6)})
    return out


def math_radians(deg):
    return deg * np.pi / 180.0


def compute_bloch_vector(theta=None, phi=None, amplitudes=None):
    if amplitudes is not None:
        a, b = complex(amplitudes[0][0], amplitudes[0][1]), complex(amplitudes[1][0], amplitudes[1][1])
        norm = np.sqrt(abs(a) ** 2 + abs(b) ** 2)
        a, b = a / norm, b / norm
    else:
        th, ph = math_radians(theta), math_radians(phi)
        a = np.cos(th / 2)
        b = np.exp(1j * ph) * np.sin(th / 2)
    state = np.array([a, b], dtype=complex)
    x = 2 * (state[0].conjugate() * state[1]).real
    y = 2 * (state[0].conjugate() * state[1]).imag
    z = abs(state[0]) ** 2 - abs(state[1]) ** 2
    return {
        "mode": "bloch_vector",
        "state_amplitudes": [{"re": round(float(state[0].real), 6), "im": round(float(state[0].imag), 6)},
                              {"re": round(float(state[1].real), 6), "im": round(float(state[1].imag), 6)}],
        "bloch_x": round(float(x), 6),
        "bloch_y": round(float(y), 6),
        "bloch_z": round(float(z), 6),
        "bloch_norm": round(float(np.sqrt(x ** 2 + y ** 2 + z ** 2)), 6),
    }


def compute_gate_sequence(n_qubits, gates, initial_state=None):
    state = _zero_state(n_qubits) if initial_state is None else np.array(
        [complex(re, im) for re, im in initial_state], dtype=complex)

    for g in gates:
        name = g["gate"].upper()
        qs = g["qubits"]
        if name in GATES_1Q:
            Mat = _single_qubit_gate_matrix(name, qs[0], n_qubits)
        elif name == "CNOT":
            Mat = _cnot_matrix(qs[0], qs[1], n_qubits)
        elif name == "TOFFOLI":
            Mat = _toffoli_matrix(qs[0], qs[1], qs[2], n_qubits)
        else:
            raise ValueError(f"puerta desconocida: {name}")
        state = Mat @ state

    return {
        "mode": "gate_sequence",
        "n_qubits": n_qubits,
        "n_gates_applied": len(gates),
        "final_state": _amp_str_list(state),
        "normalization_check": round(float(np.sum(np.abs(state) ** 2)), 6),
    }


def compute_deutsch_jozsa(n, oracle_type="balanced", seed=0):
    rng = np.random.default_rng(seed)
    N = 2 ** n

    if oracle_type == "constant":
        const_val = int(rng.integers(0, 2))
        f = lambda x: const_val
    elif oracle_type == "balanced":
        f = lambda x: bin(x).count("1") % 2
    else:
        raise ValueError("oracle_type debe ser 'constant' o 'balanced'")

    n_total = n + 1
    dim = 2 ** n_total
    state = np.zeros(dim, dtype=complex)
    state[1] = 1.0

    for i in range(n_total):
        state = _single_qubit_gate_matrix("H", i, n_total) @ state

    new_state = np.zeros(dim, dtype=complex)
    for idx in range(dim):
        if abs(state[idx]) < 1e-14:
            continue
        x = idx >> 1
        y = idx & 1
        fy = y ^ f(x)
        new_idx = (x << 1) | fy
        new_state[new_idx] += state[idx]
    state = new_state

    for i in range(n):
        state = _single_qubit_gate_matrix("H", i, n_total) @ state

    prob_all_zero = 0.0
    for idx in range(dim):
        x = idx >> 1
        if x == 0:
            prob_all_zero += abs(state[idx]) ** 2

    conclusion = "constante" if prob_all_zero > 0.999 else "balanceada"

    return {
        "mode": "deutsch_jozsa",
        "n_input_qubits": n,
        "oracle_type_used": oracle_type,
        "prob_measure_all_zero": round(float(prob_all_zero), 6),
        "algorithm_concludes": conclusion,
        "correct": conclusion == ("constante" if oracle_type == "constant" else "balanceada"),
    }


def _grover_optimal_iterations(N, M):
    theta = np.arcsin(np.sqrt(M / N))
    if theta == 0:
        return 1
    return max(1, round(np.pi / (4 * theta) - 0.5))


def compute_grover_search(n, marked_indices, n_iterations=None):
    N = 2 ** n
    if n_iterations is None:
        n_iterations = _grover_optimal_iterations(N, len(marked_indices))

    state = np.ones(N, dtype=complex) / np.sqrt(N)

    oracle_diag = np.ones(N, dtype=complex)
    for m in marked_indices:
        oracle_diag[m] = -1.0
    Oracle = np.diag(oracle_diag)

    mean = np.ones((N, N), dtype=complex) / N
    Diffusion = 2 * mean - np.eye(N, dtype=complex)

    history = []
    for it in range(n_iterations):
        state = Oracle @ state
        state = Diffusion @ state
        prob_marked = float(sum(abs(state[m]) ** 2 for m in marked_indices))
        history.append(round(prob_marked, 6))

    final_probs = {i: round(float(abs(state[i]) ** 2), 6) for i in range(N) if abs(state[i]) ** 2 > 1e-6}

    return {
        "mode": "grover_search",
        "n_qubits": n,
        "search_space_size": N,
        "marked_indices": marked_indices,
        "n_iterations_used": n_iterations,
        "n_iterations_optimal_estimate": _grover_optimal_iterations(N, len(marked_indices)),
        "prob_marked_history": history,
        "final_prob_marked_total": round(float(sum(abs(state[m]) ** 2 for m in marked_indices)), 6),
        "final_state_probabilities": final_probs,
    }


def compute_entanglement_entropy(n, state_amplitudes, subsystem_qubits):
    dim = 2 ** n
    psi = np.array([complex(re, im) for re, im in state_amplitudes], dtype=complex)
    psi = psi / np.linalg.norm(psi)

    n_a = len(subsystem_qubits)
    n_b = n - n_a
    other_qubits = [q for q in range(n) if q not in subsystem_qubits]

    dim_a, dim_b = 2 ** n_a, 2 ** n_b
    psi_matrix = np.zeros((dim_a, dim_b), dtype=complex)
    for idx in range(dim):
        bits = [(idx >> (n - 1 - i)) & 1 for i in range(n)]
        a_bits = [bits[q] for q in subsystem_qubits]
        b_bits = [bits[q] for q in other_qubits]
        a_idx = int("".join(map(str, a_bits)), 2) if a_bits else 0
        b_idx = int("".join(map(str, b_bits)), 2) if b_bits else 0
        psi_matrix[a_idx, b_idx] = psi[idx]

    rho_a = psi_matrix @ psi_matrix.conj().T
    eigvals = np.linalg.eigvalsh(rho_a)
    eigvals = np.clip(eigvals.real, 1e-14, 1.0)
    entropy = -float(np.sum(eigvals * np.log2(eigvals)))
    max_entropy = min(n_a, n_b)

    return {
        "mode": "entanglement_entropy",
        "n_qubits_total": n,
        "subsystem_qubits": subsystem_qubits,
        "reduced_density_matrix_eigenvalues": [round(float(e), 6) for e in sorted(eigvals, reverse=True)],
        "von_neumann_entropy_bits": round(entropy, 6),
        "max_possible_entropy_bits": max_entropy,
        "interpretation": (
            "estado_maximamente_entrelazado" if abs(entropy - max_entropy) < 1e-3 else
            "estado_producto_sin_entrelazamiento" if entropy < 1e-3 else
            "entrelazamiento_parcial"
        ),
    }


def compute_bit_flip_code(logical_bit=1, error_qubit=None):
    n = 3
    dim = 2 ** n
    state = np.zeros(dim, dtype=complex)
    encoded_idx = 0 if logical_bit == 0 else 7
    state[encoded_idx] = 1.0

    if error_qubit is not None:
        Xerr = _single_qubit_gate_matrix("X", error_qubit, n)
        state = Xerr @ state

    idx_after_error = int(np.argmax(np.abs(state)))
    bits = [(idx_after_error >> (n - 1 - i)) & 1 for i in range(n)]
    syndrome_01 = bits[0] ^ bits[1]
    syndrome_12 = bits[1] ^ bits[2]

    syndrome_table = {
        (0, 0): None,
        (1, 0): 0,
        (1, 1): 1,
        (0, 1): 2,
    }
    detected_error_qubit = syndrome_table[(syndrome_01, syndrome_12)]

    corrected_state = state.copy()
    if detected_error_qubit is not None:
        Xcorr = _single_qubit_gate_matrix("X", detected_error_qubit, n)
        corrected_state = Xcorr @ corrected_state

    corrected_idx = int(np.argmax(np.abs(corrected_state)))
    decoded_bit = 0 if corrected_idx == 0 else (1 if corrected_idx == 7 else None)

    return {
        "mode": "bit_flip_code",
        "logical_bit_encoded": logical_bit,
        "error_qubit_injected": error_qubit,
        "physical_state_after_error": format(idx_after_error, "03b"),
        "syndrome_q0_q1_parity": syndrome_01,
        "syndrome_q1_q2_parity": syndrome_12,
        "detected_error_qubit": detected_error_qubit,
        "physical_state_after_correction": format(corrected_idx, "03b"),
        "decoded_logical_bit": decoded_bit,
        "correction_successful": decoded_bit == logical_bit,
        "note": "codigo de repeticion bit-flip (3 qubits) - bloque constructivo del codigo de Shor de 9 qubits, no el codigo completo",
    }


def compute_quantum_information(mode, **kwargs):
    if mode == "bloch_vector":
        return compute_bloch_vector(
            theta=kwargs.get("theta"), phi=kwargs.get("phi"),
            amplitudes=kwargs.get("amplitudes"),
        )
    elif mode == "gate_sequence":
        return compute_gate_sequence(
            kwargs["n_qubits"], kwargs["gates"], initial_state=kwargs.get("initial_state"),
        )
    elif mode == "deutsch_jozsa":
        return compute_deutsch_jozsa(
            kwargs["n"], oracle_type=kwargs.get("oracle_type", "balanced"), seed=kwargs.get("seed", 0),
        )
    elif mode == "grover_search":
        return compute_grover_search(
            kwargs["n"], kwargs["marked_indices"], n_iterations=kwargs.get("n_iterations"),
        )
    elif mode == "entanglement_entropy":
        return compute_entanglement_entropy(
            kwargs["n"], kwargs["state_amplitudes"], kwargs["subsystem_qubits"],
        )
    elif mode == "bit_flip_code":
        return compute_bit_flip_code(
            logical_bit=kwargs.get("logical_bit", 1), error_qubit=kwargs.get("error_qubit"),
        )
    else:
        raise ValueError(f"modo desconocido: {mode}")


QUANTUM_INFORMATION_TOOL_SCHEMA = {
    "name": "quantum_information",
    "description": (
        "Simulacion de sistemas cuanticos de pocos qubits via statevector "
        "(numpy puro, sin qiskit): vector de Bloch de un qubit, aplicacion "
        "de puertas (H, X, Y, Z, CNOT, Toffoli) sobre registros de n "
        "qubits, algoritmos de Deutsch-Jozsa y Grover, entropia de von "
        "Neumann para cuantificar entrelazamiento entre subsistemas, y "
        "demostracion del codigo de correccion bit-flip por repeticion "
        "(bloque constructivo del codigo de Shor, no el codigo completo)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["bloch_vector", "gate_sequence", "deutsch_jozsa", "grover_search",
                         "entanglement_entropy", "bit_flip_code"],
            },
            "theta": {"type": "number", "description": "bloch_vector, grados, angulo polar"},
            "phi": {"type": "number", "description": "bloch_vector, grados, angulo azimutal"},
            "amplitudes": {"type": "array", "description": "bloch_vector, alternativa: [[re_a,im_a],[re_b,im_b]]"},
            "n_qubits": {"type": "integer", "description": "gate_sequence"},
            "gates": {"type": "array", "description": "gate_sequence, lista de {gate, qubits}"},
            "initial_state": {"type": "array", "description": "gate_sequence, opcional, [[re,im],...] tamano 2^n_qubits"},
            "n": {"type": "integer", "description": "deutsch_jozsa (qubits de entrada), grover_search (qubits totales), entanglement_entropy (qubits totales)"},
            "oracle_type": {"type": "string", "enum": ["constant", "balanced"], "description": "deutsch_jozsa"},
            "seed": {"type": "integer", "description": "deutsch_jozsa"},
            "marked_indices": {"type": "array", "description": "grover_search, indices marcados en base computacional"},
            "n_iterations": {"type": "integer", "description": "grover_search, opcional, default = optimo estimado"},
            "state_amplitudes": {"type": "array", "description": "entanglement_entropy, [[re,im],...] tamano 2^n"},
            "subsystem_qubits": {"type": "array", "description": "entanglement_entropy, indices del subsistema A"},
            "logical_bit": {"type": "integer", "description": "bit_flip_code, 0 o 1, default 1"},
            "error_qubit": {"type": "integer", "description": "bit_flip_code, indice del qubit con error (0,1,2), opcional"},
        },
        "required": ["mode"],
    },
}
