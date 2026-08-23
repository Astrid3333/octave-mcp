"""
algebraic_curve_tool.py

Curvas algebraicas planas definidas implicitamente por F(x,y)=0 (polinomios
en x,y via sympy): trazado numerico exacto por rebanadas verticales
(resolviendo la polinomial univariada en x para cada y, no un raster de
contorno aproximado), deteccion y clasificacion de singularidades (nodo,
cuspide, punto aislado) via el discriminante de la parte cuadratica del
desarrollo de Taylor en cada punto singular, y conteo de intersecciones
entre dos curvas via el teorema de Bezout (grado del resultante, eliminando
una variable).

Mismo patron que las otras tools del server: TOOL_SCHEMA (dict),
compute_algebraic_curve(mode, params=None) dispatcher, modo validate con
casos de verdad conocida, bloque __main__ con sys.argv[1] (modo) y
sys.argv[2] (json opcional), _register() via
tool_registry.register_tool(TOOL_SCHEMA["name"], TOOL_SCHEMA, _handler)
al final del archivo.

Modes:
- curve: dado F(x,y) (string sympy, ej 'y**2 - x**3 - x**2'), devuelve el
  grado total y el trazado numerico exacto: para cada y en un rango,
  resuelve F(x,y)=0 como polinomio univariado en x (via numpy.roots sobre
  los coeficientes exactos que da sympy) y devuelve las raices reales --
  no es un contorno aproximado por raster, son raices reales del
  polinomio univariado en cada rebanada.
- singularities: dado F(x,y), resuelve el sistema F=Fx=Fy=0 (sympy solve,
  practico para curvas de grado bajo/medio) y clasifica cada punto
  singular real via el discriminante disc = Fxy^2 - Fxx*Fyy de la forma
  cuadratica del desarrollo de Taylor centrado ahi (equivalente a menos
  el determinante del Hessiano): disc>0 nodo (dos ramas reales distintas
  que se cruzan), disc=0 cuspide o singularidad degenerada de orden mayor
  (hace falta el termino cubico para distinguir con certeza, se reporta
  como 'cuspide_o_superior'), disc<0 punto aislado / acnodo (sin ramas
  reales locales).
- bezout: dadas F1(x,y) y F2(x,y), calcula el resultante eliminando y
  (sympy.resultant) y compara su grado contra el producto de los grados
  totales de F1 y F2 -- el teorema de Bezout garantiza que el numero de
  intersecciones (contando multiplicidad, puntos complejos y puntos en el
  infinito, sobre un cuerpo algebraicamente cerrado) es exactamente ese
  producto para curvas sin componente comun. Tambien devuelve las
  intersecciones reales y finitas encontradas resolviendo el sistema
  numericamente. Un resultant_degree menor al producto es normal en casos
  degenerados (tangencias, puntos compartidos en el infinito, componentes
  comunes) -- no es un bug de la tool, es geometria real.
- validate: 5 casos con verdad conocida (ver _validate()).

Caveat declarado: resolver sistemas polinomiales simbolicos escala mal con
el grado -- practico para curvas de grado <= 4 o 5 aprox. Para grados
mayores sympy.solve puede no converger o tardar mucho; no hay fallback
numerico (homotopy continuation) implementado.
"""

import json
import sys

import numpy as np
import sympy as sp

_X, _Y = sp.symbols("x y", real=True)
_LOCALS = {"x": _X, "y": _Y}

TOOL_SCHEMA = {
    "name": "algebraic_curve",
    "description": (
        "Curvas algebraicas planas F(x,y)=0 (polinomios via sympy): "
        "mode='curve' traza la curva resolviendo la polinomial univariada "
        "en x para cada y (raices reales exactas, no raster aproximado) y "
        "devuelve el grado total. mode='singularities' resuelve F=Fx=Fy=0 "
        "y clasifica cada punto singular real (nodo/cuspide/aislado) via "
        "el discriminante de la parte cuadratica de Taylor. mode='bezout' "
        "calcula el resultante de dos curvas F1,F2 (eliminando y) y "
        "compara su grado contra el producto de grados totales (teorema "
        "de Bezout), mas las intersecciones reales finitas encontradas. "
        "mode='validate' corre 5 casos con verdad conocida. Practico para "
        "curvas de grado <=4-5; sympy.solve puede no converger en grados "
        "mayores."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["curve", "singularities", "bezout", "validate"],
                "default": "curve",
            },
            "expression": {
                "type": "string",
                "description": "F(x,y) en sintaxis sympy, ej 'y**2 - x**3 - x**2'. Modos curve, singularities, bezout (primera curva).",
            },
            "expression2": {
                "type": "string",
                "description": "Segunda curva F2(x,y), solo mode='bezout'.",
            },
            "y_range": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[min,max] de y para muestrear en mode='curve'. Default [-3,3].",
            },
            "resolution": {
                "type": "integer",
                "description": "Cantidad de rebanadas en y para mode='curve'. Default 60.",
            },
        },
    },
}


def _parse(expr_str):
    expr = sp.sympify(expr_str, locals=_LOCALS)
    return sp.expand(expr)


def _total_degree(expr):
    poly = sp.Poly(expr, _X, _Y)
    return poly.total_degree()


def _real_roots_of_univariate(expr_in_one_var, symbol):
    poly = sp.Poly(expr_in_one_var, symbol)
    coeffs = [float(c) for c in poly.all_coeffs()]
    if len(coeffs) < 2:
        return []
    roots = np.roots(coeffs)
    return sorted(float(r.real) for r in roots if abs(r.imag) < 1e-7)


def _mode_curve(expression, y_range=None, resolution=60):
    F = _parse(expression)
    degree = _total_degree(F)
    y_range = y_range or [-3.0, 3.0]
    resolution = int(resolution or 60)
    ys = np.linspace(y_range[0], y_range[1], resolution)
    points = []
    for yv in ys:
        F_x = sp.expand(F.subs(_Y, sp.Float(float(yv))))
        if not F_x.free_symbols:
            continue
        try:
            xs = _real_roots_of_univariate(F_x, _X)
        except Exception:
            continue
        for xv in xs:
            points.append({"x": round(xv, 6), "y": round(float(yv), 6)})
    return {"degree": degree, "num_points": len(points), "points": points}


def _mode_singularities(expression):
    F = _parse(expression)
    Fx = sp.diff(F, _X)
    Fy = sp.diff(F, _Y)
    sols = sp.solve([F, Fx, Fy], [_X, _Y], dict=True)
    singular_points = []
    for sol in sols:
        xv, yv = sol.get(_X), sol.get(_Y)
        if xv is None or yv is None:
            continue
        if not (xv.is_real and yv.is_real):
            continue
        xv_f, yv_f = float(xv), float(yv)
        Fxx = float(sp.diff(F, _X, 2).subs({_X: xv, _Y: yv}))
        Fxy = float(sp.diff(F, _X, _Y).subs({_X: xv, _Y: yv}))
        Fyy = float(sp.diff(F, _Y, 2).subs({_X: xv, _Y: yv}))
        disc = Fxy**2 - Fxx * Fyy
        if disc > 1e-9:
            kind = "nodo"
        elif abs(disc) <= 1e-9:
            kind = "cuspide_o_superior"
        else:
            kind = "aislado"
        singular_points.append(
            {"x": round(xv_f, 6), "y": round(yv_f, 6), "discriminant": round(disc, 6), "type": kind}
        )
    return {"num_singular_points": len(singular_points), "singular_points": singular_points}


def _mode_bezout(expression, expression2):
    F1 = _parse(expression)
    F2 = _parse(expression2)
    d1, d2 = _total_degree(F1), _total_degree(F2)
    res = sp.expand(sp.resultant(F1, F2, _Y))
    res_degree = None
    real_intersections = []
    if res != 0:
        res_poly = sp.Poly(res, _X)
        res_degree = res_poly.total_degree()
        if res_degree > 0:
            xs = _real_roots_of_univariate(res, _X)
            for xv in xs:
                F2_y = sp.expand(F2.subs(_X, sp.Float(xv)))
                if not F2_y.free_symbols:
                    continue
                try:
                    ys = _real_roots_of_univariate(F2_y, _Y)
                except Exception:
                    ys = []
                for yv in ys:
                    val1 = float(F1.subs({_X: xv, _Y: yv}))
                    if abs(val1) < 1e-4:
                        real_intersections.append({"x": round(xv, 6), "y": round(yv, 6)})
    bezout_bound = d1 * d2
    return {
        "degree_f1": d1,
        "degree_f2": d2,
        "bezout_bound": bezout_bound,
        "resultant_degree": res_degree,
        "resultant_degree_matches_bezout": (res_degree == bezout_bound) if res_degree is not None else False,
        "real_intersections": real_intersections,
        "num_real_intersections": len(real_intersections),
    }


def _validate():
    checks = []

    r1 = _mode_singularities("x**2 + y**2 - 1")
    checks.append(
        {
            "name": "circulo x^2+y^2-1: sin puntos singulares (curva suave)",
            "passed": r1["num_singular_points"] == 0,
            "got": r1["num_singular_points"],
        }
    )

    r2 = _mode_singularities("y**2 - x**3 - x**2")
    ok2 = (
        r2["num_singular_points"] == 1
        and r2["singular_points"][0]["type"] == "nodo"
        and abs(r2["singular_points"][0]["x"]) < 1e-6
        and abs(r2["singular_points"][0]["y"]) < 1e-6
    )
    checks.append(
        {
            "name": "cubica nodal y^2=x^3+x^2: 1 nodo en el origen",
            "passed": ok2,
            "got": r2["singular_points"],
        }
    )

    r3 = _mode_singularities("y**2 - x**3")
    ok3 = (
        r3["num_singular_points"] == 1
        and r3["singular_points"][0]["type"] == "cuspide_o_superior"
        and abs(r3["singular_points"][0]["x"]) < 1e-6
        and abs(r3["singular_points"][0]["y"]) < 1e-6
    )
    checks.append(
        {
            "name": "cubica cuspidal y^2=x^3: 1 cuspide en el origen",
            "passed": ok3,
            "got": r3["singular_points"],
        }
    )

    r4 = _mode_bezout("x - y", "x + y - 1")
    ok4 = (
        r4["bezout_bound"] == 1
        and r4["resultant_degree"] == 1
        and r4["resultant_degree_matches_bezout"]
        and r4["num_real_intersections"] == 1
        and abs(r4["real_intersections"][0]["x"] - 0.5) < 1e-6
        and abs(r4["real_intersections"][0]["y"] - 0.5) < 1e-6
    )
    checks.append(
        {
            "name": "bezout rectas x=y, x+y=1: 1 interseccion en (0.5,0.5), grado 1*1=1",
            "passed": ok4,
            "got": r4,
        }
    )

    r5 = _mode_bezout("x**2 + y**2 - 1", "x**2 - y - 0.5")
    ok5 = (
        r5["bezout_bound"] == 4
        and r5["resultant_degree"] == 4
        and r5["resultant_degree_matches_bezout"]
        and r5["num_real_intersections"] == 2
    )
    checks.append(
        {
            "name": "bezout circulo/parabola: grado 4 (2*2), 2 intersecciones reales de 4 totales",
            "passed": ok5,
            "got": r5,
        }
    )

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "all_passed": all_passed, "total": len(checks)}


def compute_algebraic_curve(mode="curve", params=None):
    params = params or {}
    try:
        if mode == "curve":
            expr = params.get("expression")
            if not expr:
                return {"error": "falta 'expression' para mode=curve"}
            return _mode_curve(
                expr,
                y_range=params.get("y_range"),
                resolution=params.get("resolution", 60),
            )
        elif mode == "singularities":
            expr = params.get("expression")
            if not expr:
                return {"error": "falta 'expression' para mode=singularities"}
            return _mode_singularities(expr)
        elif mode == "bezout":
            e1 = params.get("expression")
            e2 = params.get("expression2")
            if not e1 or not e2:
                return {"error": "faltan 'expression' y 'expression2' para mode=bezout"}
            return _mode_bezout(e1, e2)
        elif mode == "validate":
            return _validate()
        else:
            return {"error": f"modo desconocido: {mode}"}
    except Exception as e:
        return {"error": str(e)}


def _handler(arguments):
    arguments = arguments or {}
    mode = arguments.get("mode", "curve")
    return compute_algebraic_curve(mode=mode, params=arguments)


def _register():
    try:
        import tool_registry

        tool_registry.register_tool(TOOL_SCHEMA["name"], TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()


if __name__ == "__main__":
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "validate"
    params_arg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    print(json.dumps(compute_algebraic_curve(mode_arg, params_arg), indent=2, ensure_ascii=False))
