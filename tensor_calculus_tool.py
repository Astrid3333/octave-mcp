#!/usr/bin/env python3
"""
tensor_calculus_tool.py
Calculo tensorial simbolico (via sympy puro, sin diffgeom): simbolos de
Christoffel, tensor de Riemann, tensor y escalar de Ricci, derivada covariante,
algebra tensorial basica (contraccion, subir/bajar indices), y un chequeo
pedagogico de notacion de Einstein.

Pensado para geometria diferencial / relatividad general a nivel de curso
universitario. Todo se calcula a mano con sympy.diff/sympy.Matrix, no se usa
sympy.diffgeom (mas control, menos "caja negra").

Corre standalone: python3 tensor_calculus_tool.py
"""
import json
import sympy as sp


TENSOR_CALCULUS_TOOL_SCHEMA = {
    "name": "tensor_calculus",
    "description": (
        "Calculo tensorial simbolico: simbolos de Christoffel, tensor de Riemann, "
        "tensor/escalar de Ricci, derivada covariante, algebra tensorial basica "
        "(contraccion, subir/bajar indices) y chequeo de notacion de Einstein."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "christoffel_symbols",
                    "riemann_tensor",
                    "ricci_tensor",
                    "covariant_derivative",
                    "tensor_algebra",
                    "index_notation_check",
                ],
            },
            "metric": {
                "type": "array",
                "description": "Tensor metrico g_ij como matriz simbolica (lista de listas de strings). Requerido para christoffel_symbols, riemann_tensor, ricci_tensor, covariant_derivative, tensor_algebra (subir/bajar indices).",
            },
            "coordinates": {
                "type": "string",
                "description": "Coordenadas separadas por coma, ej. 'r,theta,phi'.",
            },
            "vector_field": {
                "type": "array",
                "description": "Componentes del campo vectorial V^i (strings), para covariant_derivative.",
            },
            "derivative_index": {
                "type": "integer",
                "description": "Indice de coordenada respecto al cual derivar covariantemente (0-based), para covariant_derivative.",
            },
            "operation": {
                "type": "string",
                "enum": ["contract", "raise_index", "lower_index"],
                "description": "Solo mode=tensor_algebra.",
            },
            "tensor": {
                "type": "array",
                "description": "Tensor de entrada (lista o lista de listas de strings), para tensor_algebra.",
            },
            "expression": {
                "type": "string",
                "description": "Expresion en notacion de Einstein a validar (ej. 'g_ij * V^i * V^j'), para index_notation_check.",
            },
        },
        "required": ["mode"],
    },
}


def _parse_metric(metric, coords_syms):
    n = len(coords_syms)
    g = sp.Matrix(n, n, lambda i, j: sp.sympify(metric[i][j]))
    return g


def _christoffel(g, coords_syms):
    n = len(coords_syms)
    g_inv = g.inv()
    christoffel = [[[sp.Integer(0)] * n for _ in range(n)] for _ in range(n)]
    for k in range(n):
        for i in range(n):
            for j in range(n):
                s = sp.Integer(0)
                for l in range(n):
                    term = sp.diff(g[l, j], coords_syms[i]) \
                        + sp.diff(g[l, i], coords_syms[j]) \
                        - sp.diff(g[i, j], coords_syms[l])
                    s += g_inv[k, l] * term
                christoffel[k][i][j] = sp.simplify(s / 2)
    return christoffel


def _christoffel_symbols(metric, coordinates):
    coords_syms = sp.symbols(coordinates)
    if not isinstance(coords_syms, (list, tuple)):
        coords_syms = [coords_syms]
    n = len(coords_syms)
    g = _parse_metric(metric, coords_syms)
    christoffel = _christoffel(g, coords_syms)

    nonzero = []
    for k in range(n):
        for i in range(n):
            for j in range(i, n):  # simetrico en i,j
                val = christoffel[k][i][j]
                if val != 0:
                    nonzero.append({"k": k, "i": i, "j": j, "value": str(val)})

    return {
        "mode": "christoffel_symbols",
        "coordinates": [str(c) for c in coords_syms],
        "n_dim": n,
        "metric_determinant": str(sp.simplify(g.det())),
        "nonzero_symbols": nonzero,
        "n_nonzero": len(nonzero),
    }


def _riemann_tensor(metric, coordinates):
    coords_syms = sp.symbols(coordinates)
    if not isinstance(coords_syms, (list, tuple)):
        coords_syms = [coords_syms]
    n = len(coords_syms)
    g = _parse_metric(metric, coords_syms)
    christoffel = _christoffel(g, coords_syms)

    # R^l_{ijk} = d_j Gamma^l_ik - d_k Gamma^l_ij + Gamma^l_jm Gamma^m_ik - Gamma^l_km Gamma^m_ij
    nonzero = []
    for l in range(n):
        for i in range(n):
            for j in range(n):
                for k in range(n):
                    term1 = sp.diff(christoffel[l][i][k], coords_syms[j])
                    term2 = sp.diff(christoffel[l][i][j], coords_syms[k])
                    term3 = sum(christoffel[l][j][m] * christoffel[m][i][k] for m in range(n))
                    term4 = sum(christoffel[l][k][m] * christoffel[m][i][j] for m in range(n))
                    val = sp.simplify(term1 - term2 + term3 - term4)
                    if val != 0:
                        nonzero.append({"l": l, "i": i, "j": j, "k": k, "value": str(val)})

    return {
        "mode": "riemann_tensor",
        "coordinates": [str(c) for c in coords_syms],
        "n_dim": n,
        "nonzero_components": nonzero,
        "n_nonzero": len(nonzero),
        "is_flat": len(nonzero) == 0,
    }


def _ricci_tensor(metric, coordinates):
    coords_syms = sp.symbols(coordinates)
    if not isinstance(coords_syms, (list, tuple)):
        coords_syms = [coords_syms]
    n = len(coords_syms)
    g = _parse_metric(metric, coords_syms)
    g_inv = g.inv()
    christoffel = _christoffel(g, coords_syms)

    def riemann_component(l, i, j, k):
        term1 = sp.diff(christoffel[l][i][k], coords_syms[j])
        term2 = sp.diff(christoffel[l][i][j], coords_syms[k])
        term3 = sum(christoffel[l][j][m] * christoffel[m][i][k] for m in range(n))
        term4 = sum(christoffel[l][k][m] * christoffel[m][i][j] for m in range(n))
        return term1 - term2 + term3 - term4

    ricci = sp.zeros(n, n)
    for i in range(n):
        for k in range(n):
            s = sp.Integer(0)
            for l in range(n):
                s += riemann_component(l, i, l, k)
            ricci[i, k] = sp.simplify(s)

    ricci_scalar = sp.simplify(sum(g_inv[i, j] * ricci[i, j] for i in range(n) for j in range(n)))

    return {
        "mode": "ricci_tensor",
        "coordinates": [str(c) for c in coords_syms],
        "n_dim": n,
        "ricci_tensor": [[str(ricci[i, j]) for j in range(n)] for i in range(n)],
        "ricci_scalar": str(ricci_scalar),
        "is_ricci_flat": all(ricci[i, j] == 0 for i in range(n) for j in range(n)),
    }


def _covariant_derivative(metric, coordinates, vector_field, derivative_index):
    coords_syms = sp.symbols(coordinates)
    if not isinstance(coords_syms, (list, tuple)):
        coords_syms = [coords_syms]
    n = len(coords_syms)
    g = _parse_metric(metric, coords_syms)
    christoffel = _christoffel(g, coords_syms)

    V = [sp.sympify(v) for v in vector_field]
    m = derivative_index

    # (nabla_m V)^i = d_m V^i + Gamma^i_mk V^k
    result = []
    for i in range(n):
        val = sp.diff(V[i], coords_syms[m])
        for k in range(n):
            val += christoffel[i][m][k] * V[k]
        result.append(sp.simplify(val))

    return {
        "mode": "covariant_derivative",
        "coordinates": [str(c) for c in coords_syms],
        "derivative_index": m,
        "vector_field": [str(v) for v in V],
        "covariant_derivative_components": [str(r) for r in result],
    }


def _tensor_algebra(operation, tensor, metric=None, coordinates=None):
    if operation == "contract":
        # asume tensor 2D (matriz), contrae indices (traza)
        n = len(tensor)
        T = sp.Matrix(n, n, lambda i, j: sp.sympify(tensor[i][j]))
        trace = sp.simplify(sum(T[i, i] for i in range(n)))
        return {
            "mode": "tensor_algebra",
            "operation": "contract",
            "input_shape": [n, n],
            "contracted_value": str(trace),
        }

    elif operation in ("raise_index", "lower_index"):
        if metric is None or coordinates is None:
            raise ValueError("raise_index/lower_index requieren 'metric' y 'coordinates'.")
        coords_syms = sp.symbols(coordinates)
        if not isinstance(coords_syms, (list, tuple)):
            coords_syms = [coords_syms]
        n = len(coords_syms)
        g = _parse_metric(metric, coords_syms)
        g_use = g.inv() if operation == "raise_index" else g

        V = sp.Matrix([sp.sympify(v) for v in tensor])
        result = g_use * V
        return {
            "mode": "tensor_algebra",
            "operation": operation,
            "input_vector": [str(v) for v in tensor],
            "output_vector": [str(sp.simplify(result[i])) for i in range(n)],
        }
    else:
        raise ValueError(f"operation desconocida: {operation}")


def _index_notation_check(expression):
    """
    Chequeo pedagogico simple: cuenta apariciones de cada indice (subindice/
    superindice) en la expresion y marca cuales estan repetidos (candidatos a
    suma de Einstein) vs sueltos (indices libres). No hace algebra real, es
    un parser de patrones tipo 'g_ij', 'V^i', 'T^i_jk'.
    """
    import re

    # extrae tokens tipo nombre_sub o nombre^sup, capturando las letras de indice
    sub_pattern = re.findall(r'_([a-zA-Z]+)', expression)
    sup_pattern = re.findall(r'\^([a-zA-Z]+)', expression)

    all_indices = []
    for grp in sub_pattern + sup_pattern:
        all_indices.extend(list(grp))

    from collections import Counter
    counts = Counter(all_indices)

    repeated = {idx: c for idx, c in counts.items() if c >= 2}
    free = {idx: c for idx, c in counts.items() if c == 1}

    warnings = []
    for idx, c in counts.items():
        if c > 2:
            warnings.append(f"Indice '{idx}' aparece {c} veces: en notacion de Einstein estandar no deberia repetirse mas de 2 veces (una arriba, una abajo).")

    return {
        "mode": "index_notation_check",
        "expression": expression,
        "repeated_indices_sum_convention": list(repeated.keys()),
        "free_indices": list(free.keys()),
        "warnings": warnings,
        "nota": "Chequeo pedagogico basado en patrones (conteo de indices repetidos), no valida balance covariante/contravariante real.",
    }


def compute_tensor_calculus(mode, **kwargs):
    if mode == "christoffel_symbols":
        return _christoffel_symbols(kwargs["metric"], kwargs["coordinates"])
    elif mode == "riemann_tensor":
        return _riemann_tensor(kwargs["metric"], kwargs["coordinates"])
    elif mode == "ricci_tensor":
        return _ricci_tensor(kwargs["metric"], kwargs["coordinates"])
    elif mode == "covariant_derivative":
        return _covariant_derivative(
            kwargs["metric"], kwargs["coordinates"],
            kwargs["vector_field"], kwargs["derivative_index"],
        )
    elif mode == "tensor_algebra":
        return _tensor_algebra(
            kwargs["operation"], kwargs["tensor"],
            kwargs.get("metric"), kwargs.get("coordinates"),
        )
    elif mode == "index_notation_check":
        return _index_notation_check(kwargs["expression"])
    else:
        raise ValueError(f"mode desconocido: {mode}")


if __name__ == "__main__":
    # Metrica de la esfera 2D (radio 1): ds^2 = dtheta^2 + sin^2(theta) dphi^2
    sphere_metric = [["1", "0"], ["0", "sin(theta)**2"]]

    print("=== christoffel_symbols (esfera 2D) ===")
    r1 = compute_tensor_calculus("christoffel_symbols", metric=sphere_metric, coordinates="theta,phi")
    print(json.dumps(r1, indent=2, ensure_ascii=False))

    print("\n=== riemann_tensor (esfera 2D, deberia ser curva -> is_flat=False) ===")
    r2 = compute_tensor_calculus("riemann_tensor", metric=sphere_metric, coordinates="theta,phi")
    print("n_nonzero:", r2["n_nonzero"], "| is_flat:", r2["is_flat"])

    print("\n=== ricci_tensor (esfera 2D, escalar de Ricci constante = 2) ===")
    r3 = compute_tensor_calculus("ricci_tensor", metric=sphere_metric, coordinates="theta,phi")
    print("ricci_scalar:", r3["ricci_scalar"])
    print("ricci_tensor:", r3["ricci_tensor"])

    print("\n=== covariant_derivative (campo V^i = (theta, 0) en la esfera) ===")
    r4 = compute_tensor_calculus(
        "covariant_derivative", metric=sphere_metric, coordinates="theta,phi",
        vector_field=["theta", "0"], derivative_index=1,
    )
    print(r4["covariant_derivative_components"])

    print("\n=== tensor_algebra: contract (traza de identidad 3x3) ===")
    identity_3 = [["1", "0", "0"], ["0", "1", "0"], ["0", "0", "1"]]
    r5 = compute_tensor_calculus("tensor_algebra", operation="contract", tensor=identity_3)
    print("trace:", r5["contracted_value"])

    print("\n=== tensor_algebra: lower_index (plano 2D, metrica identidad) ===")
    flat_metric = [["1", "0"], ["0", "1"]]
    r6 = compute_tensor_calculus(
        "tensor_algebra", operation="lower_index", tensor=["x", "y"],
        metric=flat_metric, coordinates="x,y",
    )
    print(r6["output_vector"])

    print("\n=== index_notation_check ===")
    r7 = compute_tensor_calculus("index_notation_check", expression="g_ij * V^i * V^j")
    print(json.dumps(r7, indent=2, ensure_ascii=False))

    print("\nOK - todos los modos corrieron sin excepciones.")
