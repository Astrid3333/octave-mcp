#!/usr/bin/env python3
"""
octave_syntax_tool.py
Valida sintaxis de codigo Octave SIN ejecutarlo. Truco: envuelve el
fragmento en una definicion de funcion y la carga via source() — Octave
tiene que parsear el cuerpo completo para poder definir la funcion, lo que
dispara errores de sintaxis (parentesis sin cerrar, 'end' faltante, tokens
invalidos, etc.) sin correr ninguna linea del codigo del usuario. Liviano:
solo invoca el binario octave-cli que ya esta instalado, sin dependencias
de Python nuevas.
"""
import os
import re
import subprocess
import tempfile
import textwrap


def compute_syntax_check(code, timeout=10):
    """
    Devuelve valid=True/False, y si es False, el mensaje de error crudo de
    Octave y la linea detectada si el mensaje la incluye (ojo: la linea
    reportada es dentro del wrapper, con un offset de 1 por la linea
    'function ...()' agregada — se resta ese offset antes de devolverla).
    """
    fn_name = "octave_syntax_check_tmp"
    indented = textwrap.indent(code, "  ")
    wrapped = f"function {fn_name}()\n{indented}\nendfunction\n"

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, fn_name + ".m")
        with open(path, "w") as f:
            f.write(wrapped)

        try:
            proc = subprocess.run(
                ["octave", "--no-gui", "--quiet", "--eval", f"source('{path}');"],
                capture_output=True, text=True, timeout=timeout, cwd=tmpdir,
            )
        except FileNotFoundError:
            return {
                "mode": "syntax_check", "valid": None,
                "error": "el binario 'octave' no esta instalado o no esta en PATH",
            }
        except subprocess.TimeoutExpired:
            return {
                "mode": "syntax_check", "valid": False,
                "error": f"timeout ({timeout}s) al parsear el codigo",
            }

        stderr = proc.stderr.strip()
        is_parse_error = ("parse error" in stderr.lower()) or (proc.returncode != 0 and stderr)

        result = {
            "mode": "syntax_check",
            "valid": not is_parse_error,
            "returncode": proc.returncode,
        }
        if is_parse_error:
            result["error_message"] = stderr
            line_match = re.search(r"near line (\d+)", stderr)
            if line_match:
                # -1 por la linea 'function ...()' que agrega el wrapper
                result["error_line"] = max(1, int(line_match.group(1)) - 1)
        return result


def compute_octave_syntax(mode, **kwargs):
    """Dispatcher unico para el tool MCP octave_syntax, segun 'mode'."""
    fns = {"syntax_check": compute_syntax_check}
    if mode not in fns:
        raise ValueError(f"mode desconocido: {mode}")
    return fns[mode](**kwargs)


OCTAVE_SYNTAX_TOOL_SCHEMA = {
    "name": "octave_syntax",
    "description": "Valida la sintaxis de un fragmento de codigo Octave sin ejecutarlo (envuelve el codigo en una funcion y lo parsea via source(), sin correr ninguna linea). mode='syntax_check'. Util para verificar codigo generado antes de guardarlo o correrlo.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["syntax_check"]},
            "code": {"type": "string"},
            "timeout": {"type": "integer"},
        },
        "required": ["mode", "code"],
    },
}


if __name__ == "__main__":
    valid_code = """
    x = 1;
    y = 2;
    for i = 1:10
      x = x + i;
    endfor
    printf("%d\\n", x);
    """
    r1 = compute_octave_syntax("syntax_check", code=valid_code)
    print("codigo valido:", r1)
    assert r1["valid"] is True, f"se esperaba valid=True, dio: {r1}"

    broken_paren = """
    x = 1;
    y = (1 + 2;
    z = x + y;
    """
    r2 = compute_octave_syntax("syntax_check", code=broken_paren)
    print("parentesis sin cerrar:", r2)
    assert r2["valid"] is False, f"se esperaba valid=False, dio: {r2}"

    broken_end = """
    for i = 1:10
      x = i;
    """
    r3 = compute_octave_syntax("syntax_check", code=broken_end)
    print("falta 'endfor':", r3)
    assert r3["valid"] is False, f"se esperaba valid=False, dio: {r3}"

    typo_keyword = """
    x = 1;
    fi x > 0
      y = 2;
    endif
    """
    r4 = compute_octave_syntax("syntax_check", code=typo_keyword)
    print("typo en keyword 'if':", r4)
    assert r4["valid"] is False, f"se esperaba valid=False, dio: {r4}"

    print("\nTodas las validaciones (1 codigo valido, 3 casos con errores de sintaxis distintos) corrieron sin excepciones.")
