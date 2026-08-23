"""
morse_theory_tool.py

Teoria de Morse explicita: clasificacion de puntos criticos de una funcion
f: R^n -> R por su indice de Morse (numero de autovalores negativos del
Hessiano en el punto), y calculo del polinomio de Morse / caracteristica
de Euler a partir de un conjunto de puntos criticos ya clasificados.
Cierra el gap #3 del roadmap de geometria (100% nuevo, aunque el insumo
--gradiente/Hessiano-- ya existe en el repo via otras tools de calculo
simbolico/algebra lineal; esta tool no las reusa, calcula su propio
gradiente/Hessiano con sympy para no depender de su firma exacta).

Teoria (recordatorio breve):
  - Punto critico: grad f(p) = 0.
  - No degenerado (Morse): el Hessiano en p es invertible (ningun
    autovalor es cero). Si hay un autovalor ~0, el punto es degenerado
    y el indice no esta bien definido por el criterio de segunda derivada
    (ej. x^3 en 1D, o el ombligo monkey saddle x^3-3xy^2 en el origen).
  - Indice de Morse = cantidad de autovalores negativos del Hessiano.
    indice 0 = minimo local, indice n = maximo local (n=dimension),
    indice intermedio = punto silla de ese orden.
  - Polinomio de Morse: M(t) = suma_p t^(indice(p)) sobre todos los
    puntos criticos. La desigualdad de Morse debil dice que el numero
    de puntos criticos de indice k es >= al k-esimo numero de Betti;
    en el caso mas simple (funcion de Morse perfecta) la igualdad vale
    termino a termino. La caracteristica de Euler es M(-1) = suma
    (-1)^indice(p), y coincide con chi(variedad) para una funcion de
    Morse sobre una variedad cerrada (teorema de Morse-Euler-Poincare).

Modos:
  - classify_point: dado f(x1,...,xn) y un punto candidato, confirma que
    es critico (|grad|~0) y lo clasifica (indice, tipo, autovalores del
    Hessiano, degenerado o no). Sirve para expresiones trascendentes
    (trigonometricas, etc.) donde resolver grad=0 simbolicamente no es
    practico -- el punto candidato se conoce de antemano (analiticamente
    o por inspeccion) y esta tool solo verifica y clasifica.
  - find_and_classify: dado f(x1,...,xn) polinomica, resuelve grad=0 via
    sympy.solve (mismo enfoque y mismo caveat de escalabilidad que el
    modo 'singularities' de algebraic_curve_tool: practico hasta pocas
    variables/grado bajo) y clasifica cada solucion real encontrada.
  - morse_polynomial: dada una lista de indices (uno por punto critico,
    ya clasificados por los modos anteriores o a mano), arma el
    polinomio de Morse (conteo por indice) y la caracteristica de Euler
    M(-1).
  - validate: 6 auto-chequeos (paraboloide=minimo indice0, paraboloide
    invertido=maximo indice2, silla 2D x^2-y^2=indice1, silla 3D
    x^2+y^2-z^2=indice1, funcion de Morse perfecta -- funcion altura
    sobre un toro parametrizado, 4 puntos criticos con indices
    0,1,1,2 -- y su polinomio de Morse 1+2t+t^2 con caracteristica de
    Euler 0, que coincide con chi(toro)=0).

Mismo patron que las otras tools del server: TOOL_SCHEMA, run(mode,
**params), validate() -> {"checks","all_passed","total",
"validation_passed"}, __main__ con sys.argv, _register() via
tool_registry.register_tool(TOOL_SCHEMA["name"], TOOL_SCHEMA, _handler).
"""

import json
import sys

import numpy as np
import sympy as sp


# ---------------------------------------------------------------------
# nucleo simbolico: gradiente, Hessiano, clasificacion
# ---------------------------------------------------------------------

def _parse(expression, var_names):
    symbols = sp.symbols(var_names, real=True)
    if len(var_names) == 1:
        symbols = (symbols,)
    locals_map = {name: sym for name, sym in zip(var_names, symbols)}
    expr = sp.sympify(expression, locals=locals_map)
    return expr, list(symbols)


def _gradient(expr, symbols):
    return [sp.diff(expr, s) for s in symbols]


def _hessian(expr, symbols):
    n = len(symbols)
    H = sp.zeros(n, n)
    for i in range(n):
        for j in range(n):
            H[i, j] = sp.diff(expr, symbols[i], symbols[j])
    return H


def _classify_from_hessian_numeric(H_numeric, tol=1e-9):
    eigvals = np.linalg.eigvalsh(H_numeric)
    degenerate = bool(np.any(np.abs(eigvals) < tol))
    n_negative = int(np.sum(eigvals < -tol))
    n_positive = int(np.sum(eigvals > tol))
    n = len(eigvals)
    if degenerate:
        kind = "degenerado (criterio de 2da derivada no decide)"
    elif n_negative == 0:
        kind = "minimo local"
    elif n_negative == n:
        kind = "maximo local"
    else:
        kind = f"punto silla de indice {n_negative}"
    return {
        "eigenvalues": [float(e) for e in eigvals],
        "degenerate": degenerate,
        "index": None if degenerate else n_negative,
        "n_positive_eigenvalues": n_positive,
        "n_negative_eigenvalues": n_negative,
        "type": kind,
    }


def classify_point(expression, variables, point, tol=1e-6, hess_tol=1e-9):
    expr, symbols = _parse(expression, variables)
    grad = _gradient(expr, symbols)
    subs_map = dict(zip(symbols, point))
    grad_val = np.array([float(g.evalf(subs=subs_map)) for g in grad])
    is_critical = bool(np.max(np.abs(grad_val)) < tol)

    H = _hessian(expr, symbols)
    H_numeric = np.array(
        [[float(H[i, j].evalf(subs=subs_map)) for j in range(len(symbols))]
         for i in range(len(symbols))]
    )
    classification = _classify_from_hessian_numeric(H_numeric, tol=hess_tol)

    return {
        "point": [float(p) for p in point],
        "gradient_at_point": [float(g) for g in grad_val],
        "max_abs_gradient": float(np.max(np.abs(grad_val))),
        "is_critical": is_critical,
        "hessian": H_numeric.tolist(),
        **classification,
    }


def find_and_classify(expression, variables, tol=1e-6, hess_tol=1e-9):
    expr, symbols = _parse(expression, variables)
    grad = _gradient(expr, symbols)
    solutions = sp.solve(grad, symbols, dict=True)

    results = []
    for sol in solutions:
        point = []
        ok = True
        for s in symbols:
            val = sol.get(s)
            if val is None or val.has(sp.I) or not val.is_real:
                ok = False
                break
            point.append(float(val))
        if not ok:
            continue
        results.append(classify_point(expression, variables, point, tol=tol, hess_tol=hess_tol))

    return {
        "expression": expression,
        "variables": variables,
        "n_solutions_raw": len(solutions),
        "n_real_critical_points": len(results),
        "critical_points": results,
    }


def morse_polynomial(indices):
    counts = {}
    for idx in indices:
        counts[idx] = counts.get(idx, 0) + 1
    max_index = max(counts) if counts else 0
    coeffs = [counts.get(k, 0) for k in range(max_index + 1)]
    euler_characteristic = sum(((-1) ** k) * counts.get(k, 0) for k in range(max_index + 1))
    poly_str = " + ".join(
        f"{c}*t^{k}" if c != 1 or k == 0 else f"t^{k}"
        for k, c in enumerate(coeffs) if c > 0
    ) or "0"
    return {
        "indices": list(indices),
        "counts_by_index": counts,
        "morse_polynomial_coeffs": coeffs,
        "morse_polynomial_str": poly_str,
        "euler_characteristic": euler_characteristic,
    }


# ---------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------

def _validate():
    checks = []

    # 1) paraboloide x^2+y^2 -> minimo, indice 0
    c1 = classify_point("x**2 + y**2", ["x", "y"], [0.0, 0.0])
    checks.append({
        "name": "paraboloide x^2+y^2 en (0,0): minimo, indice 0",
        "passed": bool(c1["is_critical"] and not c1["degenerate"] and c1["index"] == 0),
        "got": c1,
    })

    # 2) paraboloide invertido -x^2-y^2 -> maximo, indice 2
    c2 = classify_point("-x**2 - y**2", ["x", "y"], [0.0, 0.0])
    checks.append({
        "name": "paraboloide invertido -x^2-y^2 en (0,0): maximo, indice 2",
        "passed": bool(c2["is_critical"] and not c2["degenerate"] and c2["index"] == 2),
        "got": c2,
    })

    # 3) silla 2D x^2-y^2 -> indice 1
    c3 = classify_point("x**2 - y**2", ["x", "y"], [0.0, 0.0])
    checks.append({
        "name": "silla x^2-y^2 en (0,0): indice 1",
        "passed": bool(c3["is_critical"] and not c3["degenerate"] and c3["index"] == 1),
        "got": c3,
    })

    # 4) silla 3D x^2+y^2-z^2 -> indice 1 (autovalores 2,2,-2: 1 negativo)
    c4 = classify_point("x**2 + y**2 - z**2", ["x", "y", "z"], [0.0, 0.0, 0.0])
    checks.append({
        "name": "silla 3D x^2+y^2-z^2 en origen: indice 1",
        "passed": bool(c4["is_critical"] and not c4["degenerate"] and c4["index"] == 1),
        "got": c4,
    })

    # 5) find_and_classify sobre polinomio x^3-3*x*y^2 (monkey saddle, degenerado en el origen)
    c5 = find_and_classify("x**3 - 3*x*y**2", ["x", "y"])
    origin_hit = any(
        abs(cp["point"][0]) < 1e-8 and abs(cp["point"][1]) < 1e-8 and cp["degenerate"]
        for cp in c5["critical_points"]
    )
    checks.append({
        "name": "monkey saddle x^3-3xy^2: unico punto critico (origen) degenerado",
        "passed": bool(c5["n_real_critical_points"] == 1 and origin_hit),
        "got": c5,
    })

    # 6) funcion de Morse perfecta: altura sobre un toro parametrizado por
    #    (theta,phi) -- h(theta,phi) = (R + r*cos(phi)) * sin(theta),
    #    R=2, r=1. 4 puntos criticos analiticos conocidos con indices
    #    0,1,1,2 (min, 2 sillas, max) -- ver docstring del modulo.
    R, r = 2.0, 1.0
    h_expr = f"({R} + {r}*cos(phi)) * sin(theta)"
    # theta=pi/2 (sin theta=1): h=(R+r*cos phi); phi=0 -> h=R+r (maximo global,
    # el punto mas "afuera" arriba); phi=pi -> h=R-r (silla, la cresta interior
    # de arriba). theta=3pi/2 (sin theta=-1): h=-(R+r*cos phi); phi=0 ->
    # h=-(R+r) (minimo global, el punto mas "afuera" abajo); phi=pi ->
    # h=-(R-r) (silla, la cresta interior de abajo).
    torus_points = {
        "max (theta=pi/2, phi=0)": ([np.pi / 2, 0.0], 2),
        "saddle1 (theta=pi/2, phi=pi)": ([np.pi / 2, np.pi], 1),
        "min (theta=3pi/2, phi=0)": ([3 * np.pi / 2, 0.0], 0),
        "saddle2 (theta=3pi/2, phi=pi)": ([3 * np.pi / 2, np.pi], 1),
    }
    torus_results = {}
    indices_found = []
    all_match = True
    for name, (pt, expected_idx) in torus_points.items():
        res = classify_point(h_expr, ["theta", "phi"], pt)
        torus_results[name] = res
        indices_found.append(res["index"])
        if res["degenerate"] or res["index"] != expected_idx:
            all_match = False
    checks.append({
        "name": "toro (R=2,r=1): funcion altura h=(R+r*cos(phi))*sin(theta), 4 puntos con indices 0,1,1,2",
        "passed": all_match,
        "got": torus_results,
    })

    # 7) polinomio de Morse del toro: 1 + 2t + t^2, caracteristica de Euler = 0 = chi(toro)
    mp = morse_polynomial(indices_found)
    checks.append({
        "name": "polinomio de Morse del toro = 1+2t+t^2, euler_characteristic=0=chi(toro)",
        "passed": bool(mp["morse_polynomial_coeffs"] == [1, 2, 1] and mp["euler_characteristic"] == 0),
        "got": mp,
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "all_passed": all_passed, "total": len(checks),
            "validation_passed": all_passed}


# ---------------------------------------------------------------------
# schema + dispatcher
# ---------------------------------------------------------------------

TOOL_SCHEMA = {
    "name": "morse_theory",
    "description": (
        "Teoria de Morse explicita sobre f:R^n->R. mode='classify_point': "
        "dado 'expression' (string sympy en 'variables', lista de nombres) "
        "y 'point' (lista de coordenadas), confirma que es critico y lo "
        "clasifica por el indice de Morse (autovalores negativos del "
        "Hessiano): minimo/maximo/silla de indice k, o degenerado si algun "
        "autovalor es ~0. mode='find_and_classify': resuelve grad(f)=0 via "
        "sympy.solve para 'expression' polinomica y clasifica cada solucion "
        "real (mismo caveat de escalabilidad que otras tools con sympy.solve: "
        "practico para pocas variables/grado bajo). mode='morse_polynomial': "
        "dada 'indices' (lista de indices enteros, uno por punto critico), "
        "arma el polinomio de Morse (conteo de puntos por indice) y la "
        "caracteristica de Euler M(-1) = suma (-1)^indice. mode='validate': "
        "7 auto-chequeos (paraboloide, paraboloide invertido, silla 2D, "
        "silla 3D, monkey saddle degenerado, funcion altura sobre un toro "
        "parametrizado con sus 4 puntos criticos clasicos, y el polinomio "
        "de Morse resultante contra la caracteristica de Euler del toro)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["classify_point", "find_and_classify", "morse_polynomial", "validate"],
                "default": "validate",
            },
            "expression": {"type": "string", "description": "f(x1,...,xn) en sintaxis sympy."},
            "variables": {"type": "array", "items": {"type": "string"},
                          "description": "Nombres de variables, en el mismo orden que 'point'."},
            "point": {"type": "array", "items": {"type": "number"},
                      "description": "classify_point: coordenadas del punto candidato."},
            "tol": {"type": "number", "default": 1e-6, "description": "Tolerancia |grad|~0."},
            "hess_tol": {"type": "number", "default": 1e-9,
                         "description": "Tolerancia para autovalor~0 (degenerado)."},
            "indices": {"type": "array", "items": {"type": "integer"},
                        "description": "morse_polynomial: un indice de Morse por punto critico."},
        },
    },
}


def run(mode="validate", **params):
    try:
        if mode == "classify_point":
            return {"result": classify_point(
                params["expression"], params["variables"], params["point"],
                tol=params.get("tol", 1e-6), hess_tol=params.get("hess_tol", 1e-9),
            )}
        elif mode == "find_and_classify":
            return {"result": find_and_classify(
                params["expression"], params["variables"],
                tol=params.get("tol", 1e-6), hess_tol=params.get("hess_tol", 1e-9),
            )}
        elif mode == "morse_polynomial":
            return {"result": morse_polynomial(params["indices"])}
        elif mode == "validate":
            return _validate()
        else:
            raise ValueError(f"mode desconocido: {mode}")
    except Exception as e:
        return {"error": str(e)}


def morse_theory(mode="validate", **params):
    return run(mode=mode, **params)


def _handler(args):
    return run(**(args or {}))


try:
    import tool_registry
    tool_registry.register_tool(TOOL_SCHEMA["name"], TOOL_SCHEMA, _handler)
except ImportError:
    pass


if __name__ == "__main__":
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "validate"
    if mode_arg == "validate":
        print(json.dumps(_validate(), indent=2))
    else:
        params_arg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        print(json.dumps(run(mode=mode_arg, **params_arg), indent=2))
