#!/usr/bin/env python3
"""
synthetic_elevation.py

Helper NO registrado como tool MCP (es una utilidad de soporte, no un
tool de octave-mcp). Genera elevacion sintetica para un conjunto de
vertices via una expresion sympy en x,y -- mismo patron que usa
distmesh_tool.py para su parametro de densidad de malla no uniforme.

USO PREVISTO: pruebas y demos del pipeline distmesh_tool ->
flood_connectivity_tool, mientras no exista una integracion real con una
fuente de elevacion (SRTM, OpenTopoData, IDEAM, etc.). Los valores que
devuelve esta funcion NO son datos de terreno reales -- son una funcion
matematica evaluada en las coordenadas de la malla.

NO USAR esto para generar un informe que se presente como analisis real
de riesgo de una direccion concreta. Es exclusivamente para verificar
que el pipeline geometrico (mallado -> inundacion por conectividad)
funciona de punta a punta con datos consistentes.

Ejemplo de expresion: "10 - 0.5*x - 0.2*y"  (plano inclinado, baja hacia
el rio si el rio esta en x,y grandes)
Ejemplo con pendiente hacia un punto (rio en x=0): "5 + 0.8*x**2"
"""

import sympy as sp


def elevations_from_expression(vertices, expr_str):
    """vertices: lista de [x,y]. expr_str: expresion sympy en x,y (usar
    ** no ^, mismo formato que distmesh_tool). Devuelve lista de floats,
    mismo orden que vertices."""
    x, y = sp.symbols("x y")
    expr = sp.sympify(expr_str)
    f = sp.lambdify((x, y), expr, "math")
    return [float(f(float(vx), float(vy))) for vx, vy in vertices]


def validate():
    """Auto-chequeo simple: plano inclinado evaluado en puntos conocidos."""
    vertices = [[0, 0], [1, 0], [0, 1], [2, 2]]
    expr = "10 - x - y"
    result = elevations_from_expression(vertices, expr)
    expected = [10.0, 9.0, 9.0, 6.0]
    ok = all(abs(a - b) < 1e-9 for a, b in zip(result, expected))
    return {
        "checks": [{"nombre": "plano_inclinado_valores_conocidos", "paso": ok,
                     "detalle": {"result": result, "expected": expected}}],
        "todos_pasaron": ok,
        "validation_passed": ok,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(validate(), indent=2))
