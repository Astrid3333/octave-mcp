#!/usr/bin/env python3
"""
game_theory_tool.py
Teoria de juegos: equilibrios de Nash (puros y mixtos via enumeracion de
soportes), valor de juegos de suma cero (via LP), eliminacion iterada de
estrategias dominadas, valor de Shapley, chequeo del nucleo cooperativo,
y dinamica de replicador / estabilidad evolutiva (ESS) para juegos
simetricos 2x2.

Pensado para economia / ciencia politica / CS a nivel de curso universitario.
Nash y dominancia usan sympy (aritmetica exacta con racionales). Zero-sum
usa scipy.optimize.linprog (programacion lineal). Shapley y core usan
sympy sobre la funcion caracteristica.

Corre standalone: python3 game_theory_tool.py
"""
import json
import math
from itertools import combinations

import numpy as np
import sympy as sp
from scipy.optimize import linprog


GAME_THEORY_TOOL_SCHEMA = {
    "name": "game_theory",
    "description": (
        "Teoria de juegos: equilibrios de Nash (puros y mixtos), valor de juegos "
        "de suma cero, eliminacion iterada de estrategias dominadas, valor de "
        "Shapley, chequeo del nucleo cooperativo, dinamica de replicador y ESS."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "nash_equilibrium",
                    "zero_sum_value",
                    "dominance_elimination",
                    "shapley_value",
                    "cooperative_core",
                    "evolutionary_dynamics",
                ],
            },
            "payoff_p1": {
                "type": "array",
                "description": "Matriz de pagos del jugador 1 (filas), strings o numeros. Para nash_equilibrium, dominance_elimination.",
            },
            "payoff_p2": {
                "type": "array",
                "description": "Matriz de pagos del jugador 2 (columnas). Para nash_equilibrium, dominance_elimination.",
            },
            "payoff_matrix": {
                "type": "array",
                "description": "Matriz de pagos del jugador 1 en un juego de suma cero (el jugador 2 recibe el negativo), para zero_sum_value. O matriz simetrica 2x2 para evolutionary_dynamics.",
            },
            "strict": {
                "type": "boolean",
                "description": "Dominancia estricta (true) o debil (false), para dominance_elimination. Default true.",
            },
            "characteristic_function": {
                "type": "object",
                "description": "Funcion caracteristica v(S): claves como 'i,j,k' (indices de jugadores separados por coma, 0-based) o '' para la coalicion vacia, valores numericos. Para shapley_value, cooperative_core.",
            },
            "n_players": {
                "type": "integer",
                "description": "Numero de jugadores, para shapley_value, cooperative_core.",
            },
            "allocation": {
                "type": "array",
                "description": "Asignacion de pagos propuesta (uno por jugador), para cooperative_core.",
            },
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------------------
# nash_equilibrium
# ---------------------------------------------------------------------------

def _solve_support(A, B, I, J, m, n):
    """Intenta resolver un equilibrio mixto con soporte I (jugador 1) / J (jugador 2)."""
    k = len(I)

    # q (sobre J) hace indiferente al jugador 1 entre las filas de I
    q_syms = sp.symbols(f'q0:{k}')
    v1 = sp.Symbol('v1')
    eqs = []
    for i in I:
        eqs.append(sp.Eq(sum(q_syms[jj] * A[i, J[jj]] for jj in range(k)), v1))
    eqs.append(sp.Eq(sum(q_syms), 1))
    sol_q = sp.solve(eqs, list(q_syms) + [v1], dict=True)
    if not sol_q:
        return None
    sol_q = sol_q[0]
    q_vals = [sol_q.get(s) for s in q_syms]
    if any(v is None for v in q_vals) or any(v < 0 for v in q_vals):
        return None
    v1_val = sol_q.get(v1)
    if v1_val is None:
        return None

    # p (sobre I) hace indiferente al jugador 2 entre las columnas de J
    p_syms = sp.symbols(f'p0:{k}')
    v2 = sp.Symbol('v2')
    eqs2 = []
    for j in J:
        eqs2.append(sp.Eq(sum(p_syms[ii] * B[I[ii], j] for ii in range(k)), v2))
    eqs2.append(sp.Eq(sum(p_syms), 1))
    sol_p = sp.solve(eqs2, list(p_syms) + [v2], dict=True)
    if not sol_p:
        return None
    sol_p = sol_p[0]
    p_vals = [sol_p.get(s) for s in p_syms]
    if any(v is None for v in p_vals) or any(v < 0 for v in p_vals):
        return None
    v2_val = sol_p.get(v2)
    if v2_val is None:
        return None

    # nadie fuera del soporte quiere desviarse
    for i in range(m):
        if i in I:
            continue
        payoff = sum(q_vals[jj] * A[i, J[jj]] for jj in range(k))
        if payoff > v1_val:
            return None
    for j in range(n):
        if j in J:
            continue
        payoff = sum(p_vals[ii] * B[I[ii], j] for ii in range(k))
        if payoff > v2_val:
            return None

    p_full = [sp.Integer(0)] * m
    for ii, i in enumerate(I):
        p_full[i] = p_vals[ii]
    q_full = [sp.Integer(0)] * n
    for jj, j in enumerate(J):
        q_full[j] = q_vals[jj]

    return {
        "type": "mixed",
        "support_p1": list(I),
        "support_p2": list(J),
        "p1_mixed_strategy": [str(v) for v in p_full],
        "p2_mixed_strategy": [str(v) for v in q_full],
        "payoff_p1": str(v1_val),
        "payoff_p2": str(v2_val),
    }


def _nash_equilibrium(payoff_p1, payoff_p2):
    A = sp.Matrix(payoff_p1).applyfunc(sp.sympify)
    B = sp.Matrix(payoff_p2).applyfunc(sp.sympify)
    m, n = A.shape

    equilibria = []

    # puros: fuerza bruta (mejor respuesta mutua)
    for i in range(m):
        for j in range(n):
            col_j = [A[k_, j] for k_ in range(m)]
            row_i = [B[i, k_] for k_ in range(n)]
            if A[i, j] == max(col_j) and B[i, j] == max(row_i):
                equilibria.append({
                    "type": "pure",
                    "p1_strategy": i,
                    "p2_strategy": j,
                    "payoff_p1": str(A[i, j]),
                    "payoff_p2": str(B[i, j]),
                })

    # mixtos: enumeracion de soportes de igual tamano >= 2
    for k in range(2, min(m, n) + 1):
        for I in combinations(range(m), k):
            for J in combinations(range(n), k):
                sol = _solve_support(A, B, I, J, m, n)
                if sol is not None:
                    equilibria.append(sol)

    return {
        "mode": "nash_equilibrium",
        "n_strategies_p1": m,
        "n_strategies_p2": n,
        "equilibria": equilibria,
        "n_equilibria": len(equilibria),
    }


# ---------------------------------------------------------------------------
# zero_sum_value
# ---------------------------------------------------------------------------

def _zero_sum_value(payoff_matrix):
    A = np.array([[float(sp.sympify(x)) for x in row] for row in payoff_matrix])
    m, n = A.shape

    # jugador fila (maximiza v): variables [p_1..p_m, v]
    c = np.zeros(m + 1)
    c[-1] = -1.0
    A_ub = np.zeros((n, m + 1))
    for j in range(n):
        for i in range(m):
            A_ub[j, i] = -A[i, j]
        A_ub[j, m] = 1.0
    b_ub = np.zeros(n)
    A_eq = np.zeros((1, m + 1))
    A_eq[0, :m] = 1.0
    bounds = [(0, 1)] * m + [(None, None)]
    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=[1], bounds=bounds, method='highs')
    if not res.success:
        raise RuntimeError(f"LP no convergio (jugador fila): {res.message}")
    p = res.x[:m]
    v = res.x[m]

    # jugador columna (minimiza v): variables [q_1..q_n, v]
    c2 = np.zeros(n + 1)
    c2[-1] = 1.0
    A_ub2 = np.zeros((m, n + 1))
    for i in range(m):
        for j in range(n):
            A_ub2[i, j] = A[i, j]
        A_ub2[i, n] = -1.0
    b_ub2 = np.zeros(m)
    A_eq2 = np.zeros((1, n + 1))
    A_eq2[0, :n] = 1.0
    bounds2 = [(0, 1)] * n + [(None, None)]
    res2 = linprog(c2, A_ub=A_ub2, b_ub=b_ub2, A_eq=A_eq2, b_eq=[1], bounds=bounds2, method='highs')
    if not res2.success:
        raise RuntimeError(f"LP no convergio (jugador columna): {res2.message}")
    q = res2.x[:n]
    v2 = res2.x[n]

    def _clean(val):
        val = round(float(val), 6)
        return 0.0 if val == 0 else val

    return {
        "mode": "zero_sum_value",
        "game_value": _clean(v),
        "game_value_column_check": _clean(v2),
        "p1_optimal_strategy": [_clean(x) for x in p],
        "p2_optimal_strategy": [_clean(x) for x in q],
    }


# ---------------------------------------------------------------------------
# dominance_elimination
# ---------------------------------------------------------------------------

def _dominance_elimination(payoff_p1, payoff_p2, strict=True):
    A = sp.Matrix(payoff_p1).applyfunc(sp.sympify)
    B = sp.Matrix(payoff_p2).applyfunc(sp.sympify)
    m, n = A.shape

    rows = list(range(m))
    cols = list(range(n))
    eliminations = []

    changed = True
    while changed:
        changed = False
        for i in rows[:]:
            for i2 in rows:
                if i2 == i:
                    continue
                if strict:
                    dominated = all(A[i2, j] > A[i, j] for j in cols)
                else:
                    dominated = all(A[i2, j] >= A[i, j] for j in cols) and any(A[i2, j] > A[i, j] for j in cols)
                if dominated:
                    eliminations.append({"player": 1, "strategy_removed": i, "dominated_by": i2})
                    rows.remove(i)
                    changed = True
                    break
            if changed:
                break
        if changed:
            continue
        for j in cols[:]:
            for j2 in cols:
                if j2 == j:
                    continue
                if strict:
                    dominated = all(B[i, j2] > B[i, j] for i in rows)
                else:
                    dominated = all(B[i, j2] >= B[i, j] for i in rows) and any(B[i, j2] > B[i, j] for i in rows)
                if dominated:
                    eliminations.append({"player": 2, "strategy_removed": j, "dominated_by": j2})
                    cols.remove(j)
                    changed = True
                    break
            if changed:
                break

    return {
        "mode": "dominance_elimination",
        "strict": strict,
        "eliminations": eliminations,
        "remaining_p1_strategies": rows,
        "remaining_p2_strategies": cols,
    }


# ---------------------------------------------------------------------------
# shapley_value / cooperative_core (comparten parseo de v(S))
# ---------------------------------------------------------------------------

def _parse_characteristic_function(characteristic_function):
    v = {}
    for key, val in characteristic_function.items():
        if isinstance(key, str):
            coalition = frozenset(int(x) for x in key.split(",")) if key.strip() != "" else frozenset()
        else:
            coalition = frozenset(key)
        v[coalition] = sp.sympify(val)
    if frozenset() not in v:
        v[frozenset()] = sp.Integer(0)
    return v


def _shapley_value(characteristic_function, n_players):
    v = _parse_characteristic_function(characteristic_function)
    n = n_players
    all_players = list(range(n))
    shapley = [sp.Integer(0)] * n

    for i in all_players:
        others = [p for p in all_players if p != i]
        total = sp.Integer(0)
        for r in range(len(others) + 1):
            for S in combinations(others, r):
                S_set = frozenset(S)
                Si_set = S_set | {i}
                weight = sp.Rational(math.factorial(r) * math.factorial(n - r - 1), math.factorial(n))
                marginal = v.get(Si_set, sp.Integer(0)) - v.get(S_set, sp.Integer(0))
                total += weight * marginal
        shapley[i] = sp.simplify(total)

    return {
        "mode": "shapley_value",
        "n_players": n,
        "shapley_values": [str(s) for s in shapley],
        "sum_check": str(sp.simplify(sum(shapley))),
        "v_grand_coalition": str(v.get(frozenset(all_players), sp.Integer(0))),
    }


def _cooperative_core(characteristic_function, n_players, allocation):
    v = _parse_characteristic_function(characteristic_function)
    n = n_players
    x = [sp.sympify(a) for a in allocation]
    all_players = frozenset(range(n))

    efficiency_ok = sp.simplify(sum(x) - v.get(all_players, sp.Integer(0))) == 0

    violations = []
    for r in range(1, n + 1):
        for S in combinations(range(n), r):
            S_set = frozenset(S)
            coalition_payoff = sum(x[i] for i in S)
            coalition_value = v.get(S_set, sp.Integer(0))
            if sp.simplify(coalition_payoff - coalition_value) < 0:
                violations.append({
                    "coalition": list(S),
                    "allocation_sum": str(coalition_payoff),
                    "coalition_value": str(coalition_value),
                })

    is_in_core = bool(efficiency_ok) and len(violations) == 0

    return {
        "mode": "cooperative_core",
        "allocation": [str(v_) for v_ in x],
        "efficiency_satisfied": bool(efficiency_ok),
        "coalition_violations": violations,
        "is_in_core": is_in_core,
    }


# ---------------------------------------------------------------------------
# evolutionary_dynamics
# ---------------------------------------------------------------------------

def _evolutionary_dynamics(payoff_matrix):
    A = sp.Matrix(payoff_matrix).applyfunc(sp.sympify)
    if A.shape != (2, 2):
        raise ValueError("Por ahora solo soporta juegos simetricos 2x2 (dos estrategias).")

    a11, a12, a21, a22 = A[0, 0], A[0, 1], A[1, 0], A[1, 1]
    x = sp.Symbol('x')

    pi1 = x * a11 + (1 - x) * a12
    pi2 = x * a21 + (1 - x) * a22
    f = sp.simplify(pi1 - pi2)
    g = sp.simplify(x * (1 - x) * f)  # dx/dt (dinamica de replicador)
    gprime = sp.diff(g, x)

    fixed_points = {sp.Integer(0), sp.Integer(1)}
    for s in sp.solve(sp.Eq(f, 0), x):
        s_simpl = sp.simplify(s)
        if s_simpl.is_real and 0 < s_simpl < 1:
            fixed_points.add(s_simpl)

    results = []
    for fp in sorted(fixed_points, key=lambda v_: float(v_)):
        deriv_val = sp.simplify(gprime.subs(x, fp))
        if deriv_val < 0:
            stability = "estable (ESS candidato)"
        elif deriv_val > 0:
            stability = "inestable"
        else:
            stability = "indeterminado (derivada=0, requiere analisis de orden superior)"
        results.append({
            "fixed_point_x": str(fp),
            "derivative_at_fp": str(deriv_val),
            "stability": stability,
        })

    return {
        "mode": "evolutionary_dynamics",
        "payoff_matrix": [[str(A[i, j]) for j in range(2)] for i in range(2)],
        "replicator_equation_dxdt": str(g),
        "fixed_points": results,
    }


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

def compute_game_theory(mode, **kwargs):
    if mode == "nash_equilibrium":
        return _nash_equilibrium(kwargs["payoff_p1"], kwargs["payoff_p2"])
    elif mode == "zero_sum_value":
        return _zero_sum_value(kwargs["payoff_matrix"])
    elif mode == "dominance_elimination":
        return _dominance_elimination(kwargs["payoff_p1"], kwargs["payoff_p2"], kwargs.get("strict", True))
    elif mode == "shapley_value":
        return _shapley_value(kwargs["characteristic_function"], kwargs["n_players"])
    elif mode == "cooperative_core":
        return _cooperative_core(kwargs["characteristic_function"], kwargs["n_players"], kwargs["allocation"])
    elif mode == "evolutionary_dynamics":
        return _evolutionary_dynamics(kwargs["payoff_matrix"])
    else:
        raise ValueError(f"mode desconocido: {mode}")


if __name__ == "__main__":
    print("=== nash_equilibrium (Batalla de los Sexos) ===")
    # fila: Opera(0)/Futbol(1). A = pagos jugador1, B = pagos jugador2.
    A = [["2", "0"], ["0", "1"]]
    B = [["1", "0"], ["0", "2"]]
    r1 = compute_game_theory("nash_equilibrium", payoff_p1=A, payoff_p2=B)
    print(json.dumps(r1, indent=2, ensure_ascii=False))
    print("Esperado: 2 puros (0,0) y (1,1), 1 mixto p=(2/3,1/3) q=(1/3,2/3) valor (2/3,2/3)")

    print("\n=== zero_sum_value (Matching Pennies) ===")
    matching_pennies = [["1", "-1"], ["-1", "1"]]
    r2 = compute_game_theory("zero_sum_value", payoff_matrix=matching_pennies)
    print(json.dumps(r2, indent=2, ensure_ascii=False))
    print("Esperado: valor=0, estrategias (0.5,0.5) para ambos")

    print("\n=== dominance_elimination (Dilema del Prisionero) ===")
    # Cooperar(0)/Defectar(1). Defectar domina estrictamente.
    A_pd = [["3", "0"], ["5", "1"]]
    B_pd = [["3", "5"], ["0", "1"]]
    r3 = compute_game_theory("dominance_elimination", payoff_p1=A_pd, payoff_p2=B_pd, strict=True)
    print(json.dumps(r3, indent=2, ensure_ascii=False))
    print("Esperado: converge a (Defectar,Defectar) = estrategia 1 para ambos")

    print("\n=== shapley_value (juego de los guantes: 1 guante izq. vs 2 der.) ===")
    glove_cf = {
        "": 0, "0": 0, "1": 0, "2": 0,
        "0,1": 1, "0,2": 1, "1,2": 0,
        "0,1,2": 1,
    }
    r4 = compute_game_theory("shapley_value", characteristic_function=glove_cf, n_players=3)
    print(json.dumps(r4, indent=2, ensure_ascii=False))
    print("Esperado: (2/3, 1/6, 1/6), suma=1")

    print("\n=== cooperative_core (mismo juego de los guantes) ===")
    r5 = compute_game_theory("cooperative_core", characteristic_function=glove_cf, n_players=3,
                              allocation=["1", "0", "0"])
    print(json.dumps(r5, indent=2, ensure_ascii=False))
    print("Esperado: is_in_core=True (el nucleo de este juego es exactamente {(1,0,0)})")

    print("\n=== evolutionary_dynamics (Halcon-Paloma, V=2 C=4) ===")
    # Halcon(0)/Paloma(1). (V-C)/2=-1, V=2, 0, V/2=1
    hawk_dove = [["-1", "2"], ["0", "1"]]
    r6 = compute_game_theory("evolutionary_dynamics", payoff_matrix=hawk_dove)
    print(json.dumps(r6, indent=2, ensure_ascii=False))
    print("Esperado: x=0 inestable, x=1 inestable, x=1/2 estable (ESS mixto, x*=V/C=0.5)")

    print("\nOK - todos los modos corrieron sin excepciones.")
