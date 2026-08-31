"""
octave_codegen_tool.py

Cierra el ciclo generacion -> validacion -> escritura para TOOLS NUEVAS
del repo octave-mcp (genera el boilerplate de una tool MCP nueva que ya
sigue el patron del repo: compute_<tool_name>(mode=..., **kwargs) +
_validate() con 'validation_passed' + self-registro via tool_registry).

Diseñado sobre dos bugs reales ya pisados en este repo:
  1) colision de nombre de modulo (ternary_arithmetic_tool.py sobrescrito
     por error al agregar una tool nueva con el mismo nombre) -> check_collision
     corre ANTES de escribir nada a disco.
  2) mismatch entre el "name" de registro y el nombre real de la funcion de
     dispatch (bug de advanced_probability_tool, server.py comparaba contra
     un string que no coincidia con el schema real) -> el scaffold generado
     deriva el nombre de la funcion compute_<tool_name> directamente de
     tool_name, para que ese tipo de mismatch no pueda reaparecer.

Modos (via compute_octave_codegen_tool(mode=..., **kwargs)):
  - check_collision(tool_name): escanea tools/ buscando choques de nombre
    de archivo, exactos y "cercanos" (con/sin sufijo _tool).
  - scaffold_tool(tool_name, modes, description): genera el codigo del
    boilerplate en memoria (NO escribe a disco). Bloquea si hay colision.
  - validate_candidate(code): valida un fragmento de codigo OCTAVE (el que
    va a vivir adentro de la tool nueva) via octave_grammar_tool.
  - write_scaffold(tool_name, modes, description, path=None): repite
    scaffold_tool, valida que el boilerplate compile como Python, y solo
    entonces escribe -- mismo patron "solo escribe si paso" que ya usas en
    octave_innovation_doc_tool.write_doc.
  - validate: autochequeo del propio tool.
"""

import os
import re
import ast
import datetime
import importlib

REPO_ROOT = os.environ.get("OCTAVE_MCP_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")

OCTAVE_CODEGEN_TOOL_SCHEMA = {
    "name": "octave_codegen_tool",
    "description": (
        "Cierra el ciclo generacion->validacion->escritura para tools NUEVAS de octave-mcp. "
        "check_collision escanea tools/ buscando choques de nombre de modulo (exactos y "
        "cercanos) antes de crear nada -- previene el bug de sobreescritura por colision de "
        "nombre ya sufrido en este repo. scaffold_tool genera el boilerplate (con "
        "compute_<tool_name> y patron de auto-registro identicos al resto del repo) sin "
        "escribir a disco. validate_candidate valida un fragmento de codigo Octave via "
        "octave_grammar_tool. write_scaffold repite scaffold_tool, valida que el boilerplate "
        "compile, y solo entonces escribe. mode='validate' corre el autochequeo."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "check_collision",
                    "scaffold_tool",
                    "validate_candidate",
                    "write_scaffold",
                    "validate",
                ],
            },
            "tool_name": {
                "type": "string",
                "description": "nombre propuesto de la tool nueva, ej. 'ion_chemistry_tool'",
            },
            "modes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "modos que tendra la tool nueva, ej. ['compute','validate']",
            },
            "description": {
                "type": "string",
                "description": "descripcion corta de que hace la tool (va al schema generado)",
            },
            "code": {
                "type": "string",
                "description": "fragmento de codigo Octave a validar (solo validate_candidate)",
            },
            "path": {
                "type": "string",
                "description": "ruta destino explicita (opcional, default tools/<tool_name>.py)",
            },
        },
        "required": ["mode"],
    },
}


def _list_existing_tool_names():
    names = set()
    if os.path.isdir(TOOLS_DIR):
        for fn in os.listdir(TOOLS_DIR):
            if fn.endswith(".py") and not fn.startswith("_"):
                names.add(fn[:-3])
    return names


def _check_collision(tool_name):
    if not tool_name:
        return {"error": "falta tool_name"}
    module_names = _list_existing_tool_names()
    module_file_collision = tool_name in module_names
    stem = tool_name[:-5] if tool_name.endswith("_tool") else tool_name
    near = sorted(
        n for n in module_names
        if n != tool_name and (n == stem or n == stem + "_tool" or n.startswith(stem + "_"))
    )
    return {
        "tool_name": tool_name,
        "module_file_collision": module_file_collision,
        "near_matches": near,
        "safe_to_create": not module_file_collision and not near,
    }


def _boilerplate(tool_name, modes, description):
    modes = list(modes) if modes else ["compute"]
    if "validate" not in modes:
        modes = modes + ["validate"]
    mode_enum = ", ".join(f'"{m}"' for m in modes)
    schema_var = tool_name.upper() + "_SCHEMA"
    dispatch_fn = "compute_" + tool_name
    branches = []
    for m in modes:
        if m == "validate":
            continue
        branches.append(
            f'    if mode == "{m}":\n'
            f'        # TODO: implementar {m}\n'
            f'        raise NotImplementedError("{m} sin implementar todavia")\n'
        )
    branches_src = "\n".join(branches)
    desc = (description or f"TODO: describir {tool_name}").replace('"', "'")
    return f'''"""
{tool_name}.py — scaffold generado por octave_codegen_tool
{desc}
Sigue el patron de octave-mcp: self-registro via tool_registry al final
del archivo (try/except ImportError), dispatcher {dispatch_fn}(mode=..., **kwargs),
y _validate() que devuelve 'validation_passed' (nombre exacto que exige
run_all_validations.py).
"""

{schema_var} = {{
    "name": "{tool_name}",
    "description": "{desc}",
    "input_schema": {{
        "type": "object",
        "properties": {{
            "mode": {{"type": "string", "enum": [{mode_enum}]}},
        }},
        "required": ["mode"],
    }},
}}


def _validate():
    """Autochequeo minimo: reemplazar por aserciones con verdad conocida antes de wirear."""
    checks = [
        {{"name": "placeholder", "passed": True}},
    ]
    n_passed = sum(1 for c in checks if c["passed"])
    return {{
        "validation_passed": n_passed == len(checks),
        "n_passed": n_passed,
        "n_checks": len(checks),
        "checks": checks,
    }}


def {dispatch_fn}(mode, **kwargs):
    if mode == "validate":
        return _validate()
{branches_src}
    raise ValueError(f"modo desconocido: {{mode}}")


def _register():
    try:
        import tool_registry
        tool_registry.register_tool(
            "{tool_name}", {schema_var}, {dispatch_fn}
        )
    except ImportError:
        pass


_register()

if __name__ == "__main__":
    import json
    result = _validate()
    print(json.dumps(
        {{"validation_passed": result["validation_passed"],
          "n_passed": result["n_passed"], "n_checks": result["n_checks"]}},
        indent=2,
    ))
'''


def _scaffold_tool(tool_name, modes, description):
    if not tool_name:
        return {"error": "falta tool_name"}
    collision = _check_collision(tool_name)
    if not collision.get("safe_to_create", False):
        return {
            "status": "BLOCKED",
            "reason": "posible colision de nombre, revisa antes de generar",
            "collision": collision,
        }
    code = _boilerplate(tool_name, modes, description)
    return {"status": "OK", "collision": collision, "code": code}


def _validate_candidate(code):
    """Reutiliza el motor real de octave_grammar_tool en vez de reimplementar el parser."""
    if not code:
        return {"error": "falta code"}
    try:
        octave_grammar_tool = importlib.import_module("octave_grammar_tool")
    except Exception as e:
        return {"error": f"no se pudo importar octave_grammar_tool: {e}"}
    fn = getattr(octave_grammar_tool, "compute_octave_grammar_tool", None) or getattr(
        octave_grammar_tool, "validate_code", None
    )
    if fn is None:
        return {"error": "octave_grammar_tool no expone una funcion de dispatch reconocida"}
    try:
        return fn(mode="validate_code", code=code)
    except TypeError:
        return fn(code=code)


def _write_scaffold(tool_name, modes, description, path=None):
    scaffold = _scaffold_tool(tool_name, modes, description)
    if scaffold.get("status") != "OK":
        return scaffold
    code = scaffold["code"]

    try:
        ast.parse(code)
    except SyntaxError as e:
        return {"status": "FAILED", "reason": f"boilerplate python invalido: {e}"}

    dest = path or os.path.join(TOOLS_DIR, f"{tool_name}.py")
    if os.path.exists(dest):
        return {"status": "BLOCKED", "reason": f"ya existe {dest}, no se sobreescribe"}

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(code)

    return {
        "status": "WRITTEN",
        "path": dest,
        "timestamp": ts,
        "next_steps": [
            f"agregar 'import {tool_name}  # auto-registra via tool_registry, no requiere mas ediciones' en server.py",
            "reemplazar los TODO del boilerplate por la logica real",
            "correr run_all_validations.py antes de pushear",
        ],
    }


def _validate():
    known = _list_existing_tool_names()
    sample_existing = next(iter(known), None)
    checks = []
    if sample_existing:
        c = _check_collision(sample_existing)
        checks.append({"name": "colision_detectada_en_tool_existente", "passed": c["module_file_collision"]})
    fresh = _check_collision("__zz_definitely_new_tool__")
    checks.append({"name": "nombre_nuevo_marcado_seguro", "passed": fresh["safe_to_create"]})
    n_passed = sum(1 for c in checks if c["passed"])
    return {
        "validation_passed": n_passed == len(checks),
        "n_passed": n_passed,
        "n_checks": len(checks),
        "checks": checks,
    }


def compute_octave_codegen_tool(mode, **kwargs):
    if mode == "validate":
        return _validate()
    if mode == "check_collision":
        return _check_collision(kwargs.get("tool_name"))
    if mode == "scaffold_tool":
        return _scaffold_tool(kwargs.get("tool_name"), kwargs.get("modes"), kwargs.get("description"))
    if mode == "validate_candidate":
        return _validate_candidate(kwargs.get("code"))
    if mode == "write_scaffold":
        return _write_scaffold(
            kwargs.get("tool_name"), kwargs.get("modes"), kwargs.get("description"), kwargs.get("path")
        )
    raise ValueError(f"modo desconocido: {mode}")


def _register():
    try:
        import tool_registry
        tool_registry.register_tool(
            "octave_codegen_tool", OCTAVE_CODEGEN_TOOL_SCHEMA, compute_octave_codegen_tool
        )
    except ImportError:
        pass


_register()

if __name__ == "__main__":
    import json
    result = _validate()
    print(json.dumps(
        {"validation_passed": result["validation_passed"],
         "n_passed": result["n_passed"], "n_checks": result["n_checks"]},
        indent=2,
    ))
    for c in result["checks"]:
        status = "OK" if c["passed"] else "FALLO"
        print(f"  [{status}] {c['name']}")
