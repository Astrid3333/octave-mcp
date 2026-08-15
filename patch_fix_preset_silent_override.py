#!/usr/bin/env python3
"""
patch_fix_preset_silent_override.py

Corrige el bug de "silent override" en symbolic_tool.py y statistics_tool.py:
si se pasa 'expression' (symbolic) o 'x'/'y'/'sample' (statistics) sin poner
preset="custom" explicitamente, el codigo actual ignora esos datos sin avisar
y devuelve el resultado del preset "known_*" por defecto, como si fuera la
respuesta a lo que se pidio.

Reproducible antes del patch:
    compute_symbolic(expression="x**3 - 2*x")
    -> devuelve la simplificacion de (x**2-1)/(x-1) = x+1, ignorando la
       expresion dada, sin error.

Este patch agrega una guardia explicita al inicio de cada rama de mode que
detecta esa combinacion (dato custom presente + preset != "custom") y
devuelve un error claro en vez de continuar en silencio. Tambien actualiza
las descripciones de ambos schemas para documentar el requisito.

Uso:
    cd ~/octave-mcp
    python3 patch_fix_preset_silent_override.py
"""
import ast
import sys

SYMBOLIC_PATH = "symbolic_tool.py"
STATISTICS_PATH = "statistics_tool.py"


def apply_replacements(path, replacements):
    with open(path, "r", encoding="utf-8") as fh:
        content = fh.read()
    for old, new, label in replacements:
        n = content.count(old)
        assert n == 1, (
            f"[{path}] Se esperaba 1 ocurrencia de bloque '{label}', se "
            f"encontraron {n} -- el archivo puede haber cambiado desde que "
            f"se escribio este patch. Revisar a mano."
        )
        content = content.replace(old, new)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


# ---------------------------------------------------------------------------
# symbolic_tool.py
# ---------------------------------------------------------------------------
SYMBOLIC_REPLACEMENTS = [
    (
        '        if mode == "simplify":\n'
        '            if preset == "custom":\n'
        '                if not expression:\n'
        '                    return {"error": "preset=\'custom\' requiere \'expression\'"}\n'
        '                expr = _safe_parse(expression, symbols_dict)\n'
        '            elif preset == "known_simplify":',

        '        if mode == "simplify":\n'
        '            if expression is not None and preset != "custom":\n'
        '                return {"error": f"Se paso \'expression\' pero preset=\'{preset}\' "\n'
        '                                  f"(no \'custom\') -- el preset conocido ignora "\n'
        '                                  f"\'expression\' silenciosamente. Usa preset=\'custom\'."}\n'
        '            if preset == "custom":\n'
        '                if not expression:\n'
        '                    return {"error": "preset=\'custom\' requiere \'expression\'"}\n'
        '                expr = _safe_parse(expression, symbols_dict)\n'
        '            elif preset == "known_simplify":',
        "simplify",
    ),
    (
        '        elif mode == "solve":\n'
        '            if preset == "custom":\n'
        '                if not expression:\n'
        '                    return {"error": "preset=\'custom\' requiere \'expression\' (se resuelve expression=0)"}\n'
        '                expr = _safe_parse(expression, symbols_dict)\n'
        '            elif preset == "known_solve":',

        '        elif mode == "solve":\n'
        '            if expression is not None and preset != "custom":\n'
        '                return {"error": f"Se paso \'expression\' pero preset=\'{preset}\' "\n'
        '                                  f"(no \'custom\') -- el preset conocido ignora "\n'
        '                                  f"\'expression\' silenciosamente. Usa preset=\'custom\'."}\n'
        '            if preset == "custom":\n'
        '                if not expression:\n'
        '                    return {"error": "preset=\'custom\' requiere \'expression\' (se resuelve expression=0)"}\n'
        '                expr = _safe_parse(expression, symbols_dict)\n'
        '            elif preset == "known_solve":',
        "solve",
    ),
    (
        '        elif mode == "differentiate":\n'
        '            if preset == "custom":\n'
        '                if not expression:\n'
        '                    return {"error": "preset=\'custom\' requiere \'expression\'"}\n'
        '                expr = _safe_parse(expression, symbols_dict)\n'
        '            elif preset == "known_derivative":',

        '        elif mode == "differentiate":\n'
        '            if expression is not None and preset != "custom":\n'
        '                return {"error": f"Se paso \'expression\' pero preset=\'{preset}\' "\n'
        '                                  f"(no \'custom\') -- el preset conocido ignora "\n'
        '                                  f"\'expression\' silenciosamente. Usa preset=\'custom\'."}\n'
        '            if preset == "custom":\n'
        '                if not expression:\n'
        '                    return {"error": "preset=\'custom\' requiere \'expression\'"}\n'
        '                expr = _safe_parse(expression, symbols_dict)\n'
        '            elif preset == "known_derivative":',
        "differentiate",
    ),
    (
        '        elif mode == "integrate":\n'
        '            if preset == "custom":\n'
        '                if not expression:\n'
        '                    return {"error": "preset=\'custom\' requiere \'expression\'"}\n'
        '                expr = _safe_parse(expression, symbols_dict)\n'
        '            elif preset == "known_integral":',

        '        elif mode == "integrate":\n'
        '            if expression is not None and preset != "custom":\n'
        '                return {"error": f"Se paso \'expression\' pero preset=\'{preset}\' "\n'
        '                                  f"(no \'custom\') -- el preset conocido ignora "\n'
        '                                  f"\'expression\' silenciosamente. Usa preset=\'custom\'."}\n'
        '            if preset == "custom":\n'
        '                if not expression:\n'
        '                    return {"error": "preset=\'custom\' requiere \'expression\'"}\n'
        '                expr = _safe_parse(expression, symbols_dict)\n'
        '            elif preset == "known_integral":',
        "integrate",
    ),
    (
        '        elif mode == "taylor_series":\n'
        '            if preset == "custom":\n'
        '                if not expression:\n'
        '                    return {"error": "preset=\'custom\' requiere \'expression\'"}\n'
        '                expr = _safe_parse(expression, symbols_dict)\n'
        '            elif preset == "known_taylor":',

        '        elif mode == "taylor_series":\n'
        '            if expression is not None and preset != "custom":\n'
        '                return {"error": f"Se paso \'expression\' pero preset=\'{preset}\' "\n'
        '                                  f"(no \'custom\') -- el preset conocido ignora "\n'
        '                                  f"\'expression\' silenciosamente. Usa preset=\'custom\'."}\n'
        '            if preset == "custom":\n'
        '                if not expression:\n'
        '                    return {"error": "preset=\'custom\' requiere \'expression\'"}\n'
        '                expr = _safe_parse(expression, symbols_dict)\n'
        '            elif preset == "known_taylor":',
        "taylor_series",
    ),
    (
        '            "expression": {"type": "string", "description": "Expresion en variable \'x\' (y opcionalmente \'y\'), solo si preset=\'custom\'. Ej: \'sin(x)*x**2\'"},',
        '            "expression": {"type": "string", "description": "Expresion en variable \'x\' (y opcionalmente \'y\'). IMPORTANTE: tambien hay que pasar preset=\'custom\' explicitamente -- si se omite, el preset conocido por defecto ignora esta expresion sin avisar. Ej: \'sin(x)*x**2\'"},',
        "schema expression description",
    ),
]

# ---------------------------------------------------------------------------
# statistics_tool.py
# ---------------------------------------------------------------------------
STATISTICS_REPLACEMENTS = [
    (
        '    if mode == "linear_regression":\n'
        '        if preset == "custom":\n'
        '            if not x or not y or len(x) != len(y):\n'
        '                return {"error": "preset=\'custom\' requiere \'x\' e \'y\' de igual longitud"}\n'
        '        elif preset == "known_linear":\n'
        '            x, y, known = _gen_known_linear()\n'
        '        else:\n'
        '            return {"error": f"preset \'{preset}\' no aplica para mode=\'linear_regression\'"}',

        '    if mode == "linear_regression":\n'
        '        if (x is not None or y is not None) and preset != "custom":\n'
        '            return {"error": f"Se paso \'x\'/\'y\' pero preset=\'{preset}\' (no \'custom\') "\n'
        '                              f"-- el preset conocido ignora esos datos silenciosamente. "\n'
        '                              f"Usa preset=\'custom\'."}\n'
        '        if preset == "custom":\n'
        '            if not x or not y or len(x) != len(y):\n'
        '                return {"error": "preset=\'custom\' requiere \'x\' e \'y\' de igual longitud"}\n'
        '        elif preset == "known_linear":\n'
        '            x, y, known = _gen_known_linear()\n'
        '        else:\n'
        '            return {"error": f"preset \'{preset}\' no aplica para mode=\'linear_regression\'"}',
        "linear_regression",
    ),
    (
        '    elif mode == "correlation":\n'
        '        if preset == "custom":\n'
        '            if not x or not y or len(x) != len(y):\n'
        '                return {"error": "preset=\'custom\' requiere \'x\' e \'y\' de igual longitud"}\n'
        '        elif preset == "known_correlation":\n'
        '            x, y, known = _gen_known_correlation()\n'
        '        else:\n'
        '            return {"error": f"preset \'{preset}\' no aplica para mode=\'correlation\'"}',

        '    elif mode == "correlation":\n'
        '        if (x is not None or y is not None) and preset != "custom":\n'
        '            return {"error": f"Se paso \'x\'/\'y\' pero preset=\'{preset}\' (no \'custom\') "\n'
        '                              f"-- el preset conocido ignora esos datos silenciosamente. "\n'
        '                              f"Usa preset=\'custom\'."}\n'
        '        if preset == "custom":\n'
        '            if not x or not y or len(x) != len(y):\n'
        '                return {"error": "preset=\'custom\' requiere \'x\' e \'y\' de igual longitud"}\n'
        '        elif preset == "known_correlation":\n'
        '            x, y, known = _gen_known_correlation()\n'
        '        else:\n'
        '            return {"error": f"preset \'{preset}\' no aplica para mode=\'correlation\'"}',
        "correlation",
    ),
    (
        '    elif mode == "t_test":\n'
        '        if preset == "custom":\n'
        '            if not sample:\n'
        '                return {"error": "preset=\'custom\' requiere \'sample\'"}\n'
        '        elif preset == "known_ttest":\n'
        '            sample, known = _gen_known_ttest()\n'
        '        else:\n'
        '            return {"error": f"preset \'{preset}\' no aplica para mode=\'t_test\'"}',

        '    elif mode == "t_test":\n'
        '        if sample is not None and preset != "custom":\n'
        '            return {"error": f"Se paso \'sample\' pero preset=\'{preset}\' (no \'custom\') "\n'
        '                              f"-- el preset conocido ignora esos datos silenciosamente. "\n'
        '                              f"Usa preset=\'custom\'."}\n'
        '        if preset == "custom":\n'
        '            if not sample:\n'
        '                return {"error": "preset=\'custom\' requiere \'sample\'"}\n'
        '        elif preset == "known_ttest":\n'
        '            sample, known = _gen_known_ttest()\n'
        '        else:\n'
        '            return {"error": f"preset \'{preset}\' no aplica para mode=\'t_test\'"}',
        "t_test",
    ),
    (
        '            "x": {"type": "array", "description": "Solo si preset=\'custom\', mode in [linear_regression, correlation]"},\n'
        '            "y": {"type": "array", "description": "Solo si preset=\'custom\', mode in [linear_regression, correlation]"},\n'
        '            "sample": {"type": "array", "description": "Solo si preset=\'custom\', mode=\'t_test\'"},',

        '            "x": {"type": "array", "description": "mode in [linear_regression, correlation]. IMPORTANTE: tambien hay que pasar preset=\'custom\' explicitamente -- si se omite, el preset conocido ignora este dato sin avisar."},\n'
        '            "y": {"type": "array", "description": "mode in [linear_regression, correlation]. IMPORTANTE: tambien hay que pasar preset=\'custom\' explicitamente -- si se omite, el preset conocido ignora este dato sin avisar."},\n'
        '            "sample": {"type": "array", "description": "mode=\'t_test\'. IMPORTANTE: tambien hay que pasar preset=\'custom\' explicitamente -- si se omite, el preset conocido ignora este dato sin avisar."},',
        "schema x/y/sample description",
    ),
]


def main():
    apply_replacements(SYMBOLIC_PATH, SYMBOLIC_REPLACEMENTS)
    apply_replacements(STATISTICS_PATH, STATISTICS_REPLACEMENTS)

    for path in (SYMBOLIC_PATH, STATISTICS_PATH):
        ast.parse(open(path, encoding="utf-8").read())

    print("Patch aplicado OK")


if __name__ == "__main__":
    main()
