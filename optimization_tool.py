"""
optimization_tool.py

Optimizacion: programacion lineal via glpk (nativo de Octave, no requiere
paquetes extra) y descenso de gradiente con gradiente EXACTO calculado
simbolicamente via sympy (no diferencias finitas) -- reusa la misma
infraestructura de parseo seguro de symbolic_tool.py.

Relevante si el pipeline de FreeCAD/protesis necesita en algun momento
optimizar geometria bajo restricciones (LP para asignacion de recursos
discretos, descenso de gradiente para minimizar una funcion de costo
continua sobre parametros de diseno).

Mismo patron de validacion: LP contra ejemplo de libro de texto (optimo
conocido x=2,y=6, valor=36), descenso de gradiente contra un minimo
convexo conocido analiticamente.
"""
import subprocess
import tempfile
import os
import sympy as sp
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application

OPTIMIZATION_SCHEMA = {
    "name": "compute_optimization",
    "description": (
        "Optimizacion: linear_programming (maximizar/minimizar c'x sujeto a "
        "Ax<=b, x>=0, via glpk nativo de Octave), gradient_descent "
        "(minimizar una funcion via descenso de gradiente con gradiente "
        "EXACTO simbolico, no aproximado). Presets validados contra "
        "optimos conocidos, o 'custom' via los parametros correspondientes."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["linear_programming", "gradient_descent"], "default": "linear_programming"},
            "preset": {"type": "string", "enum": ["known_lp", "known_gradient_descent", "custom"], "default": "known_lp"},
            "sense": {"type": "string", "enum": ["max", "min"], "default": "max", "description": "Para linear_programming"},
            "c": {"type": "array", "description": "Coeficientes objetivo, solo si preset='custom' y mode='linear_programming'"},
            "A_ub": {"type": "array", "description": "Matriz de restricciones <=, custom LP"},
            "b_ub": {"type": "array", "description": "RHS de restricciones <=, custom LP"},
            "expression": {"type": "string", "description": "Funcion objetivo en x,y (string), custom gradient_descent"},
            "start": {"type": "array", "description": "Punto inicial [x0,y0], custom gradient_descent"},
            "learning_rate": {"type": "number", "default": 0.1},
            "n_iterations": {"type": "integer", "default": 200},
        },
    },
}

_TRANSFORMATIONS = standard_transformations + (implicit_multiplication_application,)


def _run_octave(code, timeout=30):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".m", delete=False) as fh:
        fh.write(code)
        script_path = fh.name
    try:
        r = subprocess.run(["octave", "--no-gui", "--no-init-file", script_path],
                            capture_output=True, text=True, timeout=timeout)
    finally:
        os.unlink(script_path)
    if r.returncode != 0:
        return None, r.stderr.strip()
    return r.stdout.strip(), None


def _vec_to_octave(v):
    return "[" + ",".join(str(x) for x in v) + "]"


def _matrix_to_octave(M):
    rows = [",".join(str(x) for x in row) for row in M]
    return "[" + ";".join(rows) + "]"


def _solve_lp(c, A_ub, b_ub, sense):
    n = len(c)
    m = len(A_ub)
    c_str = _vec_to_octave(c)
    A_str = _matrix_to_octave(A_ub)
    b_str = _vec_to_octave(b_ub)
    sense_val = -1 if sense == "max" else 1
    code = f"""
c = {c_str}';
A = {A_str};
b = {b_str}';
lb = zeros({n},1);
ub = [];
ctype = repmat("U", {m}, 1);
vartype = repmat("C", {n}, 1);
s = {sense_val};
[xopt, fmin, status] = glpk(c, A, b, lb, ub, ctype, vartype, s);
printf("%.8f ", xopt);
printf("|%.8f|%d", fmin, status);
"""
    out, err = _run_octave(code)
    if out is None:
        return None, err
    x_part, rest = out.split("|", 1)
    fmin_str, status_str = rest.rsplit("|", 1)
    x_opt = [float(v) for v in x_part.split()]
    fmin = float(fmin_str)
    status = int(status_str)
    return {"x_optimal": [round(v, 6) for v in x_opt], "objective_value": round(fmin, 6),
            "glpk_status": status, "status_ok": status == 5}, None


def _safe_parse(expr_str, symbols_dict):
    return parse_expr(expr_str, local_dict=symbols_dict, transformations=_TRANSFORMATIONS,
                       global_dict={"sin": sp.sin, "cos": sp.cos, "exp": sp.exp, "log": sp.log,
                                    "sqrt": sp.sqrt, "pi": sp.pi, "Integer": sp.Integer,
                                    "Float": sp.Float, "Rational": sp.Rational})


def compute_optimization(mode="linear_programming", preset="known_lp", sense="max",
                          c=None, A_ub=None, b_ub=None, expression=None, start=None,
                          learning_rate=0.1, n_iterations=200):
    known = None

    if mode == "linear_programming":
        if preset == "custom":
            if not c or not A_ub or not b_ub:
                return {"error": "preset='custom' requiere 'c', 'A_ub', 'b_ub'"}
        elif preset == "known_lp":
            c = [3, 5]
            A_ub = [[1, 0], [0, 2], [3, 2]]
            b_ub = [4, 12, 18]
            sense = "max"
            known = {"x_optimal_esperado": [2, 6], "objective_value_esperado": 36}
        else:
            return {"error": f"preset '{preset}' no aplica para mode='linear_programming'"}

        result, err = _solve_lp(c, A_ub, b_ub, sense)
        if result is None:
            return {"error": "octave/glpk fallo", "stderr": err}
        result["c"] = c
        result["A_ub"] = A_ub
        result["b_ub"] = b_ub
        result["sense"] = sense

    elif mode == "gradient_descent":
        x, y = sp.symbols("x y")
        symbols_dict = {"x": x, "y": y}
        if preset == "custom":
            if not expression:
                return {"error": "preset='custom' requiere 'expression' (funcion de x,y)"}
            try:
                f = _safe_parse(expression, symbols_dict)
            except Exception as ex:
                return {"error": f"error parseando expression: {ex}"}
            start_pos = start if start else [10.0, -5.0]
        elif preset == "known_gradient_descent":
            f = (x - 1) ** 2 + (y - 2) ** 2 + 3
            start_pos = [10.0, -5.0]
            known = {"minimo_esperado": [1, 2], "valor_esperado": 3}
        else:
            return {"error": f"preset '{preset}' no aplica para mode='gradient_descent'"}

        grad = [sp.diff(f, v) for v in (x, y)]
        grad_func = sp.lambdify((x, y), grad, "math")
        f_func = sp.lambdify((x, y), f, "math")

        pos = list(start_pos)
        trajectory = [{"iter": 0, "x": pos[0], "y": pos[1], "f": f_func(*pos)}]
        for i in range(1, n_iterations + 1):
            g = grad_func(*pos)
            pos = [pos[0] - learning_rate * g[0], pos[1] - learning_rate * g[1]]
            if i % max(1, n_iterations // 10) == 0 or i == n_iterations:
                trajectory.append({"iter": i, "x": round(pos[0], 6), "y": round(pos[1], 6),
                                   "f": round(f_func(*pos), 6)})

        result = {
            "expression": str(f),
            "gradient": [str(g) for g in grad],
            "start": start_pos,
            "converged_to": {"x": round(pos[0], 6), "y": round(pos[1], 6), "f": round(f_func(*pos), 6)},
            "trajectory_sample": trajectory,
            "learning_rate": learning_rate,
            "n_iterations": n_iterations,
        }

    else:
        return {"error": f"mode desconocido: {mode}"}

    if known:
        result["known_reference"] = known
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(compute_optimization("linear_programming", "known_lp"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_optimization("gradient_descent", "known_gradient_descent"), indent=2, ensure_ascii=False))
