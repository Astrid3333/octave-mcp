"""
octave_grammar_tool.py

Cierra el gap de flujo de trabajo entre validacion y generacion de codigo
Octave: cuando octave_validate/octave_write detectan codigo invalido, la
respuesta incluye un campo `grammar_hint` con la gramatica GBNF del
subconjunto de Octave soportado, para que el agente pueda pasarla
directamente a su motor de inferencia en el siguiente intento (constrained
decoding), sin una llamada separada a octave_compile_grammar.

Diseño, de cero (no existia nada de esto en el repo: se confirmo por
busqueda exhaustiva -- grep local y github:search_code -- que
octave_validate, octave_write y octave_compile_grammar no existian bajo
ningun nombre en octave-mcp ni en ningun otro repo de la cuenta):

  - compile_grammar: devuelve el texto GBNF completo (gramatica canonica,
    subconjunto de Octave: statements, bloques de control, expresiones,
    matrices, strings, comentarios). No depende de octave-cli.

  - validate_code: valida un fragmento de codigo combinando dos fuentes.
    (1) un checker estructural en Python puro (balance de delimitadores +
    emparejamiento de bloques con palabra clave, tipo if/endif, for/endfor,
    while/endwhile, function/endfunction, switch/endswitch,
    try/end_try_catch, do/until) -- no depende de octave-cli, siempre
    disponible. (2) cuando use_real_check=True (default) y
    octave_syntax_tool esta disponible en el mismo directorio con el
    binario 'octave' instalado, el parser real de Octave (via source(),
    sin ejecutar el codigo del usuario) para errores mas finos que el
    checker estructural no puede detectar (typos de keywords, sintaxis
    invalida dentro de una expresion que igual balancea sus delimitadores).
    La integracion con octave_syntax_tool es opcional y defensiva: si el
    modulo o el binario no estan disponibles, se degrada silenciosamente
    al resultado del checker estructural solo (ver campo
    real_check_status en la respuesta: "ok", "unavailable_no_module",
    "unavailable_no_binary"). Si el codigo resulta invalido por cualquiera
    de las dos fuentes, la respuesta incluye grammar_hint con la gramatica
    completa mas hint_focus con las reglas GBNF mas relevantes al tipo de
    error detectado.

  - write_code: valida (via validate_code) y, solo si el resultado es
    valido, escribe el archivo a disco. Si es invalido, devuelve el mismo
    validation_status=INVALID + grammar_hint, sin tocar el filesystem.

  - validate: autochequeo del propio tool (convencion del repo): un
    fragmento valido no debe traer grammar_hint; un parentesis sin cerrar
    y un bloque sin 'end' deben detectarse como invalidos y traer
    grammar_hint; y la gramatica GBNF debe ser estructuralmente consistente
    (regla raiz definida, toda regla referenciada esta definida en algun
    lado).

Nota de alcance: este checker estructural NO reemplaza a octave_syntax_tool
(que si invoca octave-cli real y por lo tanto detecta una clase de errores
mas amplia). Es un chequeo complementario, mas liviano y sin dependencias,
pensado especificamente para poder devolver grammar_hint en el mismo
intercambio.
"""

import os

import tool_registry

try:
    from octave_syntax_tool import compute_syntax_check as _real_syntax_check
except ImportError:
    _real_syntax_check = None


# ----------------------------------------------------------------------
# Gramatica GBNF (subconjunto de Octave suficiente para constrained
# decoding de scripts tipicos: asignaciones, expresiones aritmeticas,
# matrices, control de flujo, definicion de funciones, llamadas comunes
# como printf/disp, strings y comentarios).
# ----------------------------------------------------------------------

OCTAVE_GBNF = r'''
root        ::= ws statement-list ws

statement-list ::= (statement statement-sep)*

statement-sep  ::= ws (";" | "\n") ws

statement   ::= if-block
              | for-block
              | while-block
              | do-until-block
              | switch-block
              | try-block
              | function-block
              | assignment
              | expr-statement
              | comment

comment     ::= ("%" | "#") [^\n]*

assignment  ::= lvalue ws assign-op ws expr
assign-op   ::= "=" | "+=" | "-=" | "*=" | "/="
lvalue      ::= identifier (ws index-suffix)*

expr-statement ::= expr

if-block    ::= "if" ws expr statement-sep statement-list
                (ws "elseif" ws expr statement-sep statement-list)*
                (ws "else" statement-sep statement-list)?
                ws ("endif" | "end")

for-block   ::= "for" ws identifier ws "=" ws expr statement-sep
                statement-list ws ("endfor" | "end")

while-block ::= "while" ws expr statement-sep
                statement-list ws ("endwhile" | "end")

do-until-block ::= "do" statement-sep statement-list ws "until" ws expr

switch-block ::= "switch" ws expr statement-sep
                 (ws "case" ws expr statement-sep statement-list)*
                 (ws "otherwise" statement-sep statement-list)?
                 ws ("endswitch" | "end")

try-block   ::= "try" statement-sep statement-list
                (ws "catch" (ws identifier)? statement-sep statement-list)?
                ws ("end_try_catch" | "end")

function-block ::= "function" ws (output-spec ws "=" ws)? identifier
                    ws "(" ws param-list? ws ")" statement-sep
                    statement-list ws ("endfunction" | "end")

output-spec ::= identifier | ("[" ws identifier (ws "," ws identifier)* ws "]")
param-list  ::= identifier (ws "," ws identifier)*

expr        ::= or-expr
or-expr     ::= and-expr (ws ("||" | "|") ws and-expr)*
and-expr    ::= cmp-expr (ws ("&&" | "&") ws cmp-expr)*
cmp-expr    ::= add-expr (ws cmp-op ws add-expr)?
cmp-op      ::= "==" | "~=" | "!=" | "<=" | ">=" | "<" | ">"
add-expr    ::= mul-expr (ws ("+" | "-") ws mul-expr)*
mul-expr    ::= unary-expr (ws ("*" | "/" | ".*" | "./" | "^" | ".^") ws unary-expr)*
unary-expr  ::= ("-" | "+" | "~" | "!")? postfix-expr
postfix-expr ::= primary (ws index-suffix)*
index-suffix ::= "(" ws arg-list? ws ")" | "{" ws arg-list? ws "}"
arg-list    ::= expr (ws "," ws expr)*

primary     ::= number
              | string
              | matrix-literal
              | function-call
              | identifier
              | "(" ws expr ws ")"

function-call ::= identifier ws "(" ws arg-list? ws ")"

matrix-literal ::= "[" ws row-list? ws "]"
row-list    ::= row (ws (";" | "\n") ws row)*
row         ::= expr (ws ("," | ws) ws expr)*

identifier  ::= [a-zA-Z_][a-zA-Z0-9_]*
number      ::= [0-9]+ ("." [0-9]+)? (("e" | "E") ("+" | "-")? [0-9]+)?
string      ::= "\"" [^"]* "\"" | "'" [^']* "'"

ws          ::= [ \t\n]*
'''.strip("\n")


_BLOCK_OPENERS = {
    "if": {"endif", "end"},
    "for": {"endfor", "end"},
    "parfor": {"endparfor", "end"},
    "while": {"endwhile", "end"},
    "switch": {"endswitch", "end"},
    "function": {"endfunction", "end"},
    "try": {"end_try_catch", "end"},
    "do": {"until"},
}
_ALL_CLOSERS = {c for closers in _BLOCK_OPENERS.values() for c in closers}

_DELIM_PAIRS = {")": "(", "]": "[", "}": "{"}
_DELIM_OPENERS = set(_DELIM_PAIRS.values())


def _strip_comments_and_strings(line):
    """Reemplaza contenido de strings y comentarios por espacios, para que
    el tokenizado de palabras clave / delimitadores no se confunda con
    texto literal (ej: un 'end' dentro de un string, o un '%' dentro de
    un string de formato para printf)."""
    out = []
    i = 0
    n = len(line)
    in_string = None
    while i < n:
        ch = line[i]
        if in_string:
            out.append(" ")
            if ch == in_string:
                in_string = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_string = ch
            out.append(" ")
            i += 1
            continue
        if ch in ("%", "#"):
            out.append(" " * (n - i))
            break
        out.append(ch)
        i += 1
    return "".join(out)


def _check_delimiters(code):
    errors = []
    stack = []
    for lineno, raw_line in enumerate(code.splitlines(), start=1):
        line = _strip_comments_and_strings(raw_line)
        for col, ch in enumerate(line, start=1):
            if ch in _DELIM_OPENERS:
                stack.append((ch, lineno, col))
            elif ch in _DELIM_PAIRS:
                expected = _DELIM_PAIRS[ch]
                if not stack:
                    errors.append({
                        "type": "unbalanced_delimiter",
                        "message": f"'{ch}' de cierre sin apertura correspondiente",
                        "line": lineno, "column": col,
                    })
                elif stack[-1][0] != expected:
                    open_ch, open_line, open_col = stack.pop()
                    errors.append({
                        "type": "unbalanced_delimiter",
                        "message": (
                            f"'{ch}' en linea {lineno} no coincide con "
                            f"'{open_ch}' abierto en linea {open_line}"
                        ),
                        "line": lineno, "column": col,
                    })
                else:
                    stack.pop()
    for open_ch, open_line, open_col in stack:
        errors.append({
            "type": "unbalanced_delimiter",
            "message": f"'{open_ch}' abierto en linea {open_line} nunca se cierra",
            "line": open_line, "column": open_col,
        })
    return errors


def _check_blocks(code):
    errors = []
    stack = []  # (keyword, lineno)
    for lineno, raw_line in enumerate(code.splitlines(), start=1):
        line = _strip_comments_and_strings(raw_line)
        tokens = line.replace(",", " ").replace(";", " ").split()
        for tok in tokens:
            word = tok.strip().lower()
            if word in _BLOCK_OPENERS:
                stack.append((word, lineno))
            elif word in _ALL_CLOSERS:
                if not stack:
                    errors.append({
                        "type": "unterminated_block",
                        "message": f"'{word}' en linea {lineno} sin bloque abierto correspondiente",
                        "line": lineno,
                    })
                    continue
                open_word, open_line = stack[-1]
                valid_closers = _BLOCK_OPENERS[open_word]
                if word in valid_closers:
                    stack.pop()
                elif word == "end":
                    # 'end' generico cierra cualquier bloque abierto
                    stack.pop()
                else:
                    errors.append({
                        "type": "unterminated_block",
                        "message": (
                            f"'{word}' en linea {lineno} no cierra el bloque "
                            f"'{open_word}' abierto en linea {open_line} "
                            f"(se esperaba uno de: {sorted(valid_closers)})"
                        ),
                        "line": lineno,
                    })
    for open_word, open_line in stack:
        expected = sorted(_BLOCK_OPENERS[open_word])
        errors.append({
            "type": "unterminated_block",
            "message": (
                f"bloque '{open_word}' abierto en linea {open_line} nunca se "
                f"cierra (se esperaba uno de: {expected})"
            ),
            "line": open_line,
        })
    return errors


def _real_octave_check(code, timeout=30):
    """Intenta usar el checker real de octave_syntax_tool (envuelve el
    fragmento en una funcion y lo parsea via octave-cli real, sin
    ejecutarlo), cuando esta disponible en el mismo directorio y el
    binario 'octave' esta instalado. Devuelve (errors, status) donde
    status in {"ok", "unavailable_no_module", "unavailable_no_binary",
    "error"}. Nunca lanza excepcion: en cualquier caso no cubierto,
    degrada a devolver sin errores adicionales y el status correspondiente,
    para que validate_code siga funcionando con el checker liviano aunque
    esta integracion no este disponible en el entorno."""
    if _real_syntax_check is None:
        return [], "unavailable_no_module"
    try:
        r = _real_syntax_check(code, timeout=timeout)
    except Exception as e:
        return [], f"error: {e}"

    if r.get("valid") is None:
        return [], "unavailable_no_binary"
    if r.get("valid") is False:
        err = {
            "type": "octave_parse_error",
            "message": r.get("error_message", "error de sintaxis detectado por octave-cli (octave_syntax_tool)"),
        }
        if "error_line" in r:
            err["line"] = r["error_line"]
        return [err], "ok"
    return [], "ok"


# Reglas GBNF mas relevantes segun el tipo de error detectado, para no
# obligar al agente a releer la gramatica completa buscando que parte le
# aplica.
_HINT_FOCUS_RULES = {
    "unbalanced_delimiter": ["postfix-expr", "index-suffix", "matrix-literal", "primary"],
    "unterminated_block": [
        "if-block", "for-block", "while-block", "do-until-block",
        "switch-block", "try-block", "function-block",
    ],
    # un error de octave-cli real puede caer en cualquier parte del
    # lenguaje; no se acota el foco, se deja que el agente use la
    # gramatica completa junto con la linea/mensaje reportado por Octave.
    "octave_parse_error": [],
}


def compile_grammar():
    rule_count = sum(
        1 for line in OCTAVE_GBNF.splitlines() if "::=" in line
    )
    return {
        "mode": "compile_grammar",
        "format": "GBNF",
        "grammar": OCTAVE_GBNF,
        "root_rule": "root",
        "rule_count": rule_count,
    }


def _extract_hint_focus(errors):
    focus = []
    seen = set()
    for err in errors:
        for rule in _HINT_FOCUS_RULES.get(err["type"], []):
            if rule not in seen:
                seen.add(rule)
                focus.append(rule)
    return focus


def validate_code(code, use_real_check=True, timeout=30):
    errors = _check_delimiters(code) + _check_blocks(code)

    real_status = "skipped"
    if use_real_check:
        real_errors, real_status = _real_octave_check(code, timeout=timeout)
        errors += real_errors

    errors.sort(key=lambda e: (e.get("line", 0), e.get("column", 0)))

    result = {
        "mode": "validate_code",
        "validation_status": "INVALID" if errors else "VALID",
        "errors": errors,
        "real_check_status": real_status,
    }
    if errors:
        grammar = compile_grammar()
        result["grammar_hint"] = grammar["grammar"]
        result["grammar_format"] = grammar["format"]
        result["grammar_hint_focus"] = _extract_hint_focus(errors)
    return result


def write_code(code, path, use_real_check=True, timeout=30):
    validation = validate_code(code, use_real_check=use_real_check, timeout=timeout)
    if validation["validation_status"] == "INVALID":
        return {**validation, "mode": "write_code", "written": False, "path": path}

    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w") as f:
        f.write(code)

    return {
        "mode": "write_code",
        "validation_status": "VALID",
        "errors": [],
        "written": True,
        "path": path,
        "bytes_written": len(code.encode("utf-8")),
    }


# ----------------------------------------------------------------------
# Validacion (autochequeo del tool, convencion del repo)
# ----------------------------------------------------------------------

def _grammar_self_check():
    """Chequeo estructural de la propia gramatica GBNF: la regla raiz
    'root' debe estar definida, y toda regla referenciada (identificador
    en minuscula/guiones fuera de comillas) debe estar definida en algun
    lado del texto de la gramatica."""
    import re

    defined = set()
    for line in OCTAVE_GBNF.splitlines():
        m = re.match(r"^\s*([a-zA-Z_][a-zA-Z0-9_-]*)\s*::=", line)
        if m:
            defined.add(m.group(1))

    # extraer identificadores tipo regla (con guion, ej. "if-block") que
    # aparecen fuera de literales entre comillas y fuera de clases de
    # caracteres [ ... ] (que no son referencias a reglas, son GBNF nativo)
    no_strings = re.sub(r'"(?:[^"\\]|\\.)*"', " ", OCTAVE_GBNF)
    no_charclasses = re.sub(r"\[[^\]]*\]", " ", no_strings)
    referenced = set(re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*-[a-zA-Z0-9_-]*\b", no_charclasses))
    referenced |= set(re.findall(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*::=", OCTAVE_GBNF, re.M))

    missing = sorted(r for r in referenced if r not in defined)
    root_ok = "root" in defined

    return {
        "name": "grammar_self_consistency",
        "root_rule_defined": root_ok,
        "rules_defined": len(defined),
        "undefined_referenced_rules": missing,
        "passed": bool(root_ok and not missing),
    }


def _valid_code_no_hint_check():
    code = "x = 1;\nfor i = 1:10\n  x = x + i;\nendfor\nprintf(\"%d\\n\", x);\n"
    res = validate_code(code)
    ok = res["validation_status"] == "VALID" and "grammar_hint" not in res
    return {
        "name": "valid_code_produces_no_grammar_hint",
        "validation_status": res["validation_status"],
        "has_grammar_hint": "grammar_hint" in res,
        "passed": bool(ok),
    }


def _unbalanced_paren_check():
    code = "x = 1;\ny = (1 + 2;\nz = x + y;\n"
    res = validate_code(code)
    ok = (
        res["validation_status"] == "INVALID"
        and "grammar_hint" in res
        and any(e["type"] == "unbalanced_delimiter" for e in res["errors"])
    )
    return {
        "name": "unbalanced_paren_detected_with_hint",
        "validation_status": res["validation_status"],
        "has_grammar_hint": "grammar_hint" in res,
        "error_types": sorted({e["type"] for e in res["errors"]}),
        "passed": bool(ok),
    }


def _unterminated_block_check():
    code = "for i = 1:10\n  x = i;\n"
    res = validate_code(code)
    ok = (
        res["validation_status"] == "INVALID"
        and "grammar_hint" in res
        and any(e["type"] == "unterminated_block" for e in res["errors"])
    )
    return {
        "name": "unterminated_block_detected_with_hint",
        "validation_status": res["validation_status"],
        "has_grammar_hint": "grammar_hint" in res,
        "error_types": sorted({e["type"] for e in res["errors"]}),
        "passed": bool(ok),
    }


def _real_check_integration_robust():
    """Chequeo de robustez: validate_code con use_real_check=True nunca
    debe lanzar excepcion, sin importar si octave_syntax_tool o el
    binario 'octave' estan presentes en el entorno -- y el resultado
    estructural (errors, validation_status) debe seguir siendo correcto
    por si solo, ya que el checker liviano no depende de esa integracion."""
    valid_code = "x = 1;\nfor i = 1:10\n  x = x + i;\nendfor\n"
    broken_code = "x = 1;\ny = (1 + 2;\n"

    try:
        r_valid = validate_code(valid_code, use_real_check=True)
        r_broken = validate_code(broken_code, use_real_check=True)
        crashed = False
    except Exception as e:
        r_valid = r_broken = None
        crashed = True

    ok = (
        not crashed
        and r_valid["validation_status"] == "VALID"
        and r_broken["validation_status"] == "INVALID"
        and "grammar_hint" in r_broken
    )
    return {
        "name": "real_check_integration_never_crashes",
        "crashed": crashed,
        "real_check_status_on_valid": None if crashed else r_valid.get("real_check_status"),
        "real_check_status_on_broken": None if crashed else r_broken.get("real_check_status"),
        "passed": bool(ok),
    }


def validate():
    checks = [
        _grammar_self_check(),
        _valid_code_no_hint_check(),
        _unbalanced_paren_check(),
        _unterminated_block_check(),
        _real_check_integration_robust(),
    ]
    return {
        "mode": "validate",
        "checks": checks,
        "validation_passed": all(c["passed"] for c in checks),
    }


def compute_octave_grammar(mode="validate", **kwargs):
    if mode == "compile_grammar":
        return compile_grammar()
    elif mode == "validate_code":
        return validate_code(
            kwargs["code"],
            use_real_check=kwargs.get("use_real_check", True),
            timeout=kwargs.get("timeout", 30),
        )
    elif mode == "write_code":
        return write_code(
            kwargs["code"], kwargs["path"],
            use_real_check=kwargs.get("use_real_check", True),
            timeout=kwargs.get("timeout", 30),
        )
    elif mode == "validate":
        return validate()
    else:
        raise ValueError(f"mode desconocido: {mode}")


OCTAVE_GRAMMAR_TOOL_SCHEMA = {
    "name": "octave_grammar_tool",
    "description": (
        "Cierra el ciclo validacion->generacion corregida para codigo Octave: "
        "compile_grammar devuelve la gramatica GBNF del subconjunto de Octave "
        "soportado; validate_code chequea un fragmento SIN ejecutarlo "
        "combinando dos fuentes -- un checker estructural liviano en Python "
        "puro (balance de delimitadores y de bloques if/for/while/function/ "
        "switch/try) que no depende de octave-cli, y, cuando "
        "octave_syntax_tool esta disponible en el entorno (use_real_check, "
        "default true), el parser real de octave-cli via source() para "
        "detectar errores mas finos (typos de keywords, sintaxis rota "
        "dentro de expresiones). Si el resultado es invalido, la respuesta "
        "incluye grammar_hint (la gramatica GBNF completa) y "
        "grammar_hint_focus (las reglas mas relevantes al error) en la "
        "MISMA respuesta -- sin necesidad de una llamada separada a "
        "compile_grammar. write_code valida y solo escribe a disco si el "
        "resultado es valido, devolviendo el mismo grammar_hint si no lo "
        "es. mode=validate corre el autochequeo del tool."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["compile_grammar", "validate_code", "write_code", "validate"],
            },
            "code": {"type": "string", "description": "fragmento de codigo Octave (validate_code, write_code)"},
            "path": {"type": "string", "description": "ruta de destino (write_code)"},
            "use_real_check": {
                "type": "boolean",
                "description": (
                    "si es true (default), ademas del checker estructural liviano "
                    "intenta usar octave_syntax_tool/octave-cli para errores mas "
                    "finos; se degrada silenciosamente si no esta disponible en "
                    "el entorno (ver campo real_check_status en la respuesta)"
                ),
            },
            "timeout": {"type": "integer", "description": "timeout en segundos para el chequeo real via octave-cli (default 30)"},
        },
        "required": ["mode"],
    },
}


def _handler(args):
    args = dict(args or {})
    mode = args.pop("mode", "validate")
    params = args.pop("params", None) or {}
    merged = {**params, **args}
    return compute_octave_grammar(mode=mode, **merged)


tool_registry.register_tool("octave_grammar_tool", OCTAVE_GRAMMAR_TOOL_SCHEMA, _handler)


if __name__ == "__main__":
    import json
    print(json.dumps(validate(), indent=2, ensure_ascii=False))
