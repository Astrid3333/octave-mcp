"""
math_error_analyzer_tool.py

Modulo #27 de la hoja de ruta (math_error_analyzer_tool): analisis de error
de truncamiento vs. redondeo en diferenciacion numerica, y numero de
condicionamiento de matrices. Troncal en cualquier curso de metodos
numericos -- cuantifica el trade-off clasico "h chico reduce truncamiento
pero dispara redondeo" y el amplificador de error que es un mal
condicionamiento.

Sigue el mismo criterio que math_pipeline_tool, historian_tool y
socket_qa_engine: si un paso falla (expresion invalida, matriz no
cuadrada, dimensiones que no calzan), se reporta el motivo especifico y no
se sigue adivinando con datos incompletos.

Requiere: sympy (derivada analitica exacta), y octave-cli en PATH para el
computo numerico (forward/central difference, cond()).
"""

import json
import re
import subprocess
import tempfile
import os

import sympy
from sympy import symbols, sympify, diff, lambdify


def _py_expr_to_octave(expr_str: str) -> str:
    """Convierte sintaxis python/sympy ('x**2 + sin(x)') a Octave escalar
    ('x^2 + sin(x)'). Las funciones (sin, cos, exp, log, sqrt, tan, ...)
    ya coinciden entre ambos lenguajes para argumentos escalares."""
    return expr_str.replace("**", "^")


def _run_octave(script: str) -> dict:
    """Corre un script Octave que termina imprimiendo jsonencode(resultado)
    como ultima linea de stdout, y devuelve ese dict parseado. No traga
    errores de Octave: si el proceso falla o no hay JSON en stdout, se
    reporta el motivo especifico."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".m", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        proc = subprocess.run(
            ["octave-cli", "--no-gui", "-q", path],
            capture_output=True, text=True, timeout=60,
        )
    finally:
        os.unlink(path)

    if proc.returncode != 0:
        return {"error": f"octave_failed", "detail": proc.stderr.strip()[-2000:]}

    json_line = None
    for line in reversed(proc.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") or line.startswith("["):
            json_line = line
            break
    if json_line is None:
        return {"error": "no_json_output", "detail": proc.stdout.strip()[-2000:]}
    try:
        return json.loads(json_line)
    except json.JSONDecodeError as e:
        return {"error": "json_decode_failed", "detail": str(e), "raw": json_line[:500]}


def _analytic_derivative(function_expr: str, x0: float):
    """Deriva analiticamente con sympy y evalua en x0. Devuelve
    (valor_float, error) -- error no-None si la expresion no parsea."""
    x = symbols("x")
    try:
        f_sym = sympify(function_expr)
    except (sympy.SympifyError, SyntaxError, TypeError) as e:
        return None, f"expresion invalida: {e}"
    try:
        d_sym = diff(f_sym, x)
        val = float(d_sym.subs(x, x0))
    except Exception as e:
        return None, f"no se pudo evaluar la derivada en x0: {e}"
    return val, None


def _truncation_roundoff(function_expr: str, x0: float, method: str,
                          h_min_exp: int, h_max_exp: int) -> dict:
    true_deriv, err = _analytic_derivative(function_expr, x0)
    if err:
        return {"error": "invalid_function", "detail": err}
    if method not in ("forward", "central", "both"):
        return {"error": "invalid_method",
                "detail": f"'{method}' no es forward/central/both"}
    if h_min_exp >= h_max_exp:
        return {"error": "invalid_range",
                "detail": "h_min_exp debe ser menor que h_max_exp"}

    octave_expr = _py_expr_to_octave(function_expr)
    script = f"""
f = @(x) {octave_expr};
x0 = {x0!r};
true_deriv = {true_deriv!r};
exps = {h_min_exp}:{h_max_exp};
hs = 10.^(-exps);
n = numel(hs);
errs_f = nan(1, n);
errs_c = nan(1, n);
for k = 1:n
  h = hs(k);
  errs_f(k) = abs((f(x0+h) - f(x0)) / h - true_deriv);
  errs_c(k) = abs((f(x0+h) - f(x0-h)) / (2*h) - true_deriv);
end
[minerr_f, idxf] = min(errs_f);
[minerr_c, idxc] = min(errs_c);
result.h_values = hs;
result.errs_forward = errs_f;
result.errs_central = errs_c;
result.true_derivative = true_deriv;
result.optimal_h_forward = hs(idxf);
result.optimal_err_forward = minerr_f;
result.optimal_h_central = hs(idxc);
result.optimal_err_central = minerr_c;
result.theory_optimal_h_forward = sqrt(eps);
result.theory_optimal_h_central = eps^(1/3);
printf("%s\\n", jsonencode(result));
"""
    out = _run_octave(script)
    if "error" in out:
        return out

    result = {
        "function": function_expr,
        "x0": x0,
        "true_derivative": out["true_derivative"],
        "h_values": out["h_values"],
        "theory_optimal_h": {
            "forward": out["theory_optimal_h_forward"],
            "central": out["theory_optimal_h_central"],
        },
    }
    if method in ("forward", "both"):
        result["forward"] = {
            "errors": out["errs_forward"],
            "optimal_h": out["optimal_h_forward"],
            "optimal_error": out["optimal_err_forward"],
        }
    if method in ("central", "both"):
        result["central"] = {
            "errors": out["errs_central"],
            "optimal_h": out["optimal_h_central"],
            "optimal_error": out["optimal_err_central"],
        }
    return result


def _condition_number(matrix, b=None, delta_b=None) -> dict:
    if not isinstance(matrix, list) or not matrix or not all(isinstance(r, list) for r in matrix):
        return {"error": "invalid_matrix", "detail": "matrix debe ser una lista de listas no vacia"}
    n_rows = len(matrix)
    if any(len(r) != len(matrix[0]) for r in matrix):
        return {"error": "invalid_matrix", "detail": "todas las filas deben tener el mismo largo"}
    n_cols = len(matrix[0])
    if n_rows != n_cols:
        return {"error": "not_square",
                "detail": f"cond() de Octave requiere matriz cuadrada, recibida {n_rows}x{n_cols}"}

    octave_rows = ";".join(",".join(repr(float(v)) for v in row) for row in matrix)
    lines = [f"A = [{octave_rows}];", "c = cond(A);", "result.condition_number = c;"]

    do_perturb = b is not None and delta_b is not None
    if do_perturb:
        if len(b) != n_rows or len(delta_b) != n_rows:
            return {"error": "dimension_mismatch",
                    "detail": f"b y delta_b deben tener largo {n_rows}"}
        b_str = ",".join(repr(float(v)) for v in b)
        db_str = ",".join(repr(float(v)) for v in delta_b)
        lines += [
            f"b = [{b_str}]';",
            f"db = [{db_str}]';",
            "x1 = A\\b;",
            "x2 = A\\(b+db);",
            "rel_delta_b = norm(db)/norm(b);",
            "rel_delta_x = norm(x2-x1)/norm(x1);",
            "result.rel_delta_b = rel_delta_b;",
            "result.rel_delta_x = rel_delta_x;",
            "result.amplification_observed = rel_delta_x/rel_delta_b;",
            "result.amplification_bound = c;",
        ]
    lines.append('printf("%s\\n", jsonencode(result));')
    out = _run_octave("\n".join(lines))
    if "error" in out:
        return out

    cond_num = out["condition_number"]
    interpretation = (
        "bien condicionada" if cond_num < 1e2 else
        "moderadamente sensible" if cond_num < 1e6 else
        "mal condicionada (posible perdida severa de precision en la solucion)"
    )
    result = {"condition_number": cond_num, "interpretation": interpretation}
    if do_perturb:
        result["perturbation_demo"] = {
            "rel_delta_b": out["rel_delta_b"],
            "rel_delta_x": out["rel_delta_x"],
            "amplification_observed": out["amplification_observed"],
            "amplification_bound_cond": out["amplification_bound"],
            "note": ("rel_delta_x <= condition_number * rel_delta_b es la cota teorica; "
                     "el valor observado siempre deberia cumplirla."),
        }
    return result


def _validate() -> dict:
    checks = []

    # Check 1: forward/central error minimo cerca del optimo teorico (orden de magnitud)
    tr = _truncation_roundoff("sin(x)", 1.0, "both", 1, 16)
    if "error" in tr:
        return {"error": "validate_failed_truncation", "detail": tr}
    fwd_ratio = tr["forward"]["optimal_h"] / tr["theory_optimal_h"]["forward"]
    ctr_ratio = tr["central"]["optimal_h"] / tr["theory_optimal_h"]["central"]
    checks.append({
        "check": "forward optimal h dentro de 2 ordenes de magnitud de sqrt(eps)",
        "passed": 0.01 < fwd_ratio < 100,
        "ratio": fwd_ratio,
    })
    checks.append({
        "check": "central optimal h dentro de 2 ordenes de magnitud de eps^(1/3)",
        "passed": 0.01 < ctr_ratio < 100,
        "ratio": ctr_ratio,
    })
    checks.append({
        "check": "central converge mas (mejor error minimo) que forward, como predice la teoria O(h^2) vs O(h)",
        "passed": tr["central"]["optimal_error"] < tr["forward"]["optimal_error"],
    })

    # Check 2: matriz bien condicionada vs Hilbert(6) mal condicionada
    well = _condition_number([[2.0, 0.0], [0.0, 3.0]])
    ill = _condition_number([[float(1) / (i + j + 1) for j in range(6)] for i in range(6)])
    if "error" in well or "error" in ill:
        return {"error": "validate_failed_condition", "detail": {"well": well, "ill": ill}}
    checks.append({
        "check": "matriz diagonal esta bien condicionada (cond < 100)",
        "passed": well["condition_number"] < 100,
        "value": well["condition_number"],
    })
    checks.append({
        "check": "Hilbert(6) esta mal condicionada (cond > 1e6), caso de libro",
        "passed": ill["condition_number"] > 1e6,
        "value": ill["condition_number"],
    })

    # Check 3: cota de perturbacion se respeta
    pert = _condition_number([[4.0, 3.0], [6.0, 3.0]], b=[1.0, 1.0], delta_b=[1e-6, 0.0])
    if "error" in pert:
        return {"error": "validate_failed_perturbation", "detail": pert}
    bound_respected = pert["perturbation_demo"]["amplification_observed"] <= pert["condition_number"] + 1e-9
    checks.append({
        "check": "amplificacion observada respeta la cota amplification <= condition_number",
        "passed": bound_respected,
        "observed": pert["perturbation_demo"]["amplification_observed"],
        "bound": pert["condition_number"],
    })

    # Check 4: los 4 caminos de error se detienen con motivo especifico (no adivinan)
    error_checks = [
        ("expresion invalida", _truncation_roundoff("esto no es matematica(((", 1.0, "both", 1, 16)),
        ("metodo desconocido", _truncation_roundoff("sin(x)", 1.0, "diagonal", 1, 16)),
        ("matriz no cuadrada", _condition_number([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])),
        ("dimensiones de b/delta_b no calzan", _condition_number([[1.0, 0.0], [0.0, 1.0]], b=[1.0], delta_b=[1.0, 2.0])),
    ]
    for name, res in error_checks:
        checks.append({
            "check": f"camino de error '{name}' se detiene con 'error' explicito",
            "passed": isinstance(res, dict) and "error" in res,
            "result": res,
        })

    all_passed = all(c["passed"] for c in checks)
    return {"all_passed": all_passed, "checks": checks}


def compute_math_error_analysis(mode: str = "validate", **kwargs) -> dict:
    """Punto de entrada del tool.

    mode='truncation_roundoff': barre h de 10^-h_min_exp a 10^-h_max_exp
      para diferenciacion forward y/o central de function_expr (sintaxis
      python/sympy, ej. 'sin(x)', 'x**3 - 2*x') evaluada en x0, comparando
      contra la derivada analitica exacta (sympy). Muestra el trade-off
      clasico: error de truncamiento domina con h grande (O(h) forward,
      O(h^2) central), error de redondeo domina con h chico (O(eps/h)).
      kwargs: function_expr (str, default 'sin(x)'), x0 (float, default 1.0),
      method ('forward'|'central'|'both', default 'both'),
      h_min_exp (int, default 1), h_max_exp (int, default 16).

    mode='condition_number': calcula cond(A) de una matriz cuadrada y,
      opcionalmente, demuestra la cota de amplificacion de error
      ||delta_x||/||x|| <= cond(A) * ||delta_b||/||b|| perturbando b.
      kwargs: matrix (list[list[float]], requerido), b (list[float],
      opcional), delta_b (list[float], opcional -- si se pasan b y delta_b
      se corre la demo de perturbacion).

    mode='validate': corre ambos modos contra casos de libro con verdad
      conocida (sin(x) en x=1 con derivada analitica cos(1); matriz
      diagonal bien condicionada vs. Hilbert(6) mal condicionada; cota de
      perturbacion) y prueba los caminos de error a proposito. Mismo
      criterio que math_pipeline_tool: si algo falla, se detiene ahi y
      reporta el motivo especifico.
    """
    if mode == "truncation_roundoff":
        return _truncation_roundoff(
            kwargs.get("function_expr", "sin(x)"),
            kwargs.get("x0", 1.0),
            kwargs.get("method", "both"),
            kwargs.get("h_min_exp", 1),
            kwargs.get("h_max_exp", 16),
        )
    elif mode == "condition_number":
        if "matrix" not in kwargs:
            return {"error": "missing_param", "detail": "condition_number requiere 'matrix'"}
        return _condition_number(kwargs["matrix"], kwargs.get("b"), kwargs.get("delta_b"))
    elif mode == "validate":
        return _validate()
    else:
        return {"error": "unknown_mode",
                "detail": f"'{mode}' no es truncation_roundoff/condition_number/validate"}
MATH_ERROR_ANALYZER_TOOL_SCHEMA = {
    "name": "math_error_analyzer",
    "description": (
        "Analiza error de truncamiento vs. redondeo en diferenciacion numerica "
        "(forward/central) y numero de condicionamiento de matrices, con demo de "
        "amplificacion de error via perturbacion. mode='truncation_roundoff' "
        "(function_expr, x0, method, h_min_exp, h_max_exp); "
        "mode='condition_number' (matrix, b opcional, delta_b opcional); "
        "mode='validate' corre ambos contra casos de libro con verdad conocida."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["truncation_roundoff", "condition_number", "validate"],
                "default": "validate",
            },
            "function_expr": {
                "type": "string",
                "description": "Sintaxis python/sympy, ej 'sin(x)' o 'x**3 - 2*x'. Solo mode=truncation_roundoff.",
            },
            "x0": {"type": "number", "description": "Punto de evaluacion. Solo mode=truncation_roundoff."},
            "method": {
                "type": "string",
                "enum": ["forward", "central", "both"],
                "description": "Solo mode=truncation_roundoff.",
            },
            "h_min_exp": {"type": "integer", "description": "Exponente minimo del barrido (10^-h). Solo mode=truncation_roundoff."},
            "h_max_exp": {"type": "integer", "description": "Exponente maximo del barrido. Solo mode=truncation_roundoff."},
            "matrix": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "number"}},
                "description": "Matriz cuadrada. Requerido para mode=condition_number.",
            },
            "b": {"type": "array", "items": {"type": "number"}, "description": "Vector b, demo de perturbacion. Opcional."},
            "delta_b": {"type": "array", "items": {"type": "number"}, "description": "Perturbacion de b. Opcional."},
        },
        "required": [],
    },
}

