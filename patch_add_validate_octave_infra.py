#!/usr/bin/env python3
"""
patch_add_validate_octave_infra.py

Agrega mode="validate" a las 4 tools de octave_infra_tool.py
(octave_run, octave_eval_expr, octave_run_script, octave_version).
NO toca run_octave (server.py:195) -- queda afuera a proposito, ver
justificacion en el chat (es un duplicado funcional y esta inyectado
como run_octave_fn en compute_ancestral_octave).

Aplica:
  1. octave_infra_tool.py: agrega param mode=None a las 4 funciones,
     con un bloque de self-test real (subprocess a octave de verdad,
     no mocks) al principio de cada una cuando mode=="validate".
  2. server.py: agrega "mode": {"enum": ["validate"]} a los 4 schemas
     (lineas 272-275), y json.dumps condicional en los 4 dispatch
     elif (porque ahora pueden devolver dict en vez de str).
  3. run_all_validations.py: agrega las 4 a FLAT_SIGNATURE_TOOLS.

Uso:
  python3 patch_add_validate_octave_infra.py --dry-run
  python3 patch_add_validate_octave_infra.py
"""
import re
import shutil
import sys
from pathlib import Path

DRY = "--dry-run" in sys.argv


def report(ok, msg):
    print(("OK -- " if ok else "FALLO -- ") + msg)
    return ok


def backup(p: Path):
    b = p.with_suffix(p.suffix + ".bak")
    if not DRY:
        shutil.copy(p, b)
    print(f"  (backup en {b})")


# ---------------------------------------------------------------- octave_infra_tool.py
INFRA = Path("octave_infra_tool.py")
infra_src = INFRA.read_text()
all_ok = True

old_octave_run = '''def octave_run(code: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Ejecuta codigo Octave. timeout en segundos (default 60)."""
    r = _run_octave(code, timeout=timeout)
    return _format_result(r)'''

new_octave_run = '''def octave_run(code: str = None, timeout: int = DEFAULT_TIMEOUT, mode: str = None):
    """Ejecuta codigo Octave. timeout en segundos (default 60)."""
    if mode == "validate":
        checks = []
        r1 = _run_octave("disp(2+2)")
        checks.append({"name": "basic_eval", "passed": r1["returncode"] == 0 and "4" in r1["stdout"], "detail": r1["stdout"]})
        r2 = _run_octave("this is not valid octave syntax !!!")
        checks.append({"name": "error_capture_on_bad_code", "passed": r2["returncode"] != 0 or bool(r2["stderr"]), "detail": r2["stderr"][:200]})
        r3 = _run_octave("disp(1)", timeout=5)
        checks.append({"name": "custom_timeout_param_works", "passed": r3["returncode"] == 0, "detail": r3["stdout"]})
        passed = sum(c["passed"] for c in checks)
        return {"tool": "octave_run", "checks": checks, "passed": passed, "total": len(checks), "all_passed": passed == len(checks)}
    r = _run_octave(code, timeout=timeout)
    return _format_result(r)'''

all_ok &= report(old_octave_run in infra_src, "anchor octave_run encontrado")

old_eval = '''def octave_eval_expr(expression: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Evalua una expresion Octave con disp()."""
    r = _run_octave("disp(" + expression + ")", timeout=timeout)
    if r["returncode"] != 0:
        return _format_result(r)
    return r["stdout"] if r["stdout"] else "(sin salida)"'''

new_eval = '''def octave_eval_expr(expression: str = None, timeout: int = DEFAULT_TIMEOUT, mode: str = None):
    """Evalua una expresion Octave con disp()."""
    if mode == "validate":
        checks = []
        v1 = octave_eval_expr("2+2")
        checks.append({"name": "eval_addition", "passed": v1.strip() == "4", "detail": v1})
        v2 = octave_eval_expr("3*3")
        checks.append({"name": "eval_multiplication", "passed": v2.strip() == "9", "detail": v2})
        v3 = octave_eval_expr("this_var_is_not_defined_xyz")
        checks.append({"name": "eval_error_on_undefined", "passed": "[stderr]" in v3 or "error" in v3.lower(), "detail": v3[:200]})
        passed = sum(c["passed"] for c in checks)
        return {"tool": "octave_eval_expr", "checks": checks, "passed": passed, "total": len(checks), "all_passed": passed == len(checks)}
    r = _run_octave("disp(" + expression + ")", timeout=timeout)
    if r["returncode"] != 0:
        return _format_result(r)
    return r["stdout"] if r["stdout"] else "(sin salida)"'''

all_ok &= report(old_eval in infra_src, "anchor octave_eval_expr encontrado")

old_script = '''def octave_run_script(script_path: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Ejecuta un script .m existente en disco."""
    p = Path(script_path)
    if not p.exists():
        return "Error: no existe " + script_path
    r = _run_octave(p.read_text(), working_dir=str(p.parent), timeout=timeout)
    return _format_result(r)'''

new_script = '''def octave_run_script(script_path: str = None, timeout: int = DEFAULT_TIMEOUT, mode: str = None):
    """Ejecuta un script .m existente en disco."""
    if mode == "validate":
        import tempfile as _tempfile
        checks = []
        tmp_path = None
        try:
            with _tempfile.NamedTemporaryFile(mode="w", suffix=".m", delete=False) as f:
                f.write("disp(42)\\n")
                tmp_path = f.name
            out = octave_run_script(tmp_path)
            checks.append({"name": "runs_existing_script", "passed": "42" in out, "detail": out})
        finally:
            if tmp_path:
                os.unlink(tmp_path)
        out2 = octave_run_script("/no/existe/archivo_inventado_validate_xyz.m")
        checks.append({"name": "missing_script_returns_error", "passed": out2.startswith("Error: no existe"), "detail": out2})
        passed = sum(c["passed"] for c in checks)
        return {"tool": "octave_run_script", "checks": checks, "passed": passed, "total": len(checks), "all_passed": passed == len(checks)}
    p = Path(script_path)
    if not p.exists():
        return "Error: no existe " + script_path
    r = _run_octave(p.read_text(), working_dir=str(p.parent), timeout=timeout)
    return _format_result(r)'''

all_ok &= report(old_script in infra_src, "anchor octave_run_script encontrado")

old_version = '''def octave_version() -> str:
    """Devuelve la version de Octave instalada."""
    try:
        r = subprocess.run(["octave", "--version"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except subprocess.TimeoutExpired:
        return "Timeout consultando version de Octave"
    except FileNotFoundError:
        return "Octave no encontrado"'''

new_version = '''def octave_version(mode: str = None):
    """Devuelve la version de Octave instalada."""
    if mode == "validate":
        checks = []
        v = octave_version()
        bad = ("Timeout" in v) or ("no encontrado" in v)
        checks.append({"name": "version_string_nonempty", "passed": bool(v) and not bad, "detail": v})
        checks.append({"name": "version_looks_like_version", "passed": (not bad) and any(c.isdigit() for c in v), "detail": v})
        passed = sum(c["passed"] for c in checks)
        return {"tool": "octave_version", "checks": checks, "passed": passed, "total": len(checks), "all_passed": passed == len(checks)}
    try:
        r = subprocess.run(["octave", "--version"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except subprocess.TimeoutExpired:
        return "Timeout consultando version de Octave"
    except FileNotFoundError:
        return "Octave no encontrado"'''

all_ok &= report(old_version in infra_src, "anchor octave_version encontrado")

if all_ok and not DRY:
    infra_src = infra_src.replace(old_octave_run, new_octave_run)
    infra_src = infra_src.replace(old_eval, new_eval)
    infra_src = infra_src.replace(old_script, new_script)
    infra_src = infra_src.replace(old_version, new_version)
    backup(INFRA)
    INFRA.write_text(infra_src)

# ---------------------------------------------------------------- server.py
SERVER = Path("server.py")
server_src = SERVER.read_text()

old_schemas = '''    {"name": "octave_run", "description": "Ejecuta codigo Octave. timeout en segundos (default 60).", "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["code"]}},
    {"name": "octave_eval_expr", "description": "Evalua una expresion Octave con disp().", "inputSchema": {"type": "object", "properties": {"expression": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["expression"]}},
    {"name": "octave_run_script", "description": "Ejecuta un script .m existente en disco.", "inputSchema": {"type": "object", "properties": {"script_path": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["script_path"]}},
    {"name": "octave_version", "description": "Devuelve la version de Octave instalada.", "inputSchema": {"type": "object", "properties": {}}},'''

new_schemas = '''    {"name": "octave_run", "description": "Ejecuta codigo Octave. timeout en segundos (default 60).", "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}, "timeout": {"type": "integer"}, "mode": {"type": "string", "enum": ["validate"]}}, "required": ["code"]}},
    {"name": "octave_eval_expr", "description": "Evalua una expresion Octave con disp().", "inputSchema": {"type": "object", "properties": {"expression": {"type": "string"}, "timeout": {"type": "integer"}, "mode": {"type": "string", "enum": ["validate"]}}, "required": ["expression"]}},
    {"name": "octave_run_script", "description": "Ejecuta un script .m existente en disco.", "inputSchema": {"type": "object", "properties": {"script_path": {"type": "string"}, "timeout": {"type": "integer"}, "mode": {"type": "string", "enum": ["validate"]}}, "required": ["script_path"]}},
    {"name": "octave_version", "description": "Devuelve la version de Octave instalada.", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string", "enum": ["validate"]}}}},'''

all_ok &= report(old_schemas in server_src, "anchor de los 4 schemas encontrado")

old_dispatch = '''                elif tool_name == "octave_run":
                    output = octave_run(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": output or "(sin salida)"}]},
                    }

                elif tool_name == "octave_eval_expr":
                    output = octave_eval_expr(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": output or "(sin salida)"}]},
                    }

                elif tool_name == "octave_run_script":
                    output = octave_run_script(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": output or "(sin salida)"}]},
                    }

                elif tool_name == "octave_version":
                    output = octave_version(**args)
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": output or "(sin salida)"}]},
                    }'''

new_dispatch = '''                elif tool_name == "octave_run":
                    output = octave_run(**args)
                    text = json.dumps(output, ensure_ascii=False, indent=2) if isinstance(output, dict) else (output or "(sin salida)")
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": text}]},
                    }

                elif tool_name == "octave_eval_expr":
                    output = octave_eval_expr(**args)
                    text = json.dumps(output, ensure_ascii=False, indent=2) if isinstance(output, dict) else (output or "(sin salida)")
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": text}]},
                    }

                elif tool_name == "octave_run_script":
                    output = octave_run_script(**args)
                    text = json.dumps(output, ensure_ascii=False, indent=2) if isinstance(output, dict) else (output or "(sin salida)")
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": text}]},
                    }

                elif tool_name == "octave_version":
                    output = octave_version(**args)
                    text = json.dumps(output, ensure_ascii=False, indent=2) if isinstance(output, dict) else (output or "(sin salida)")
                    resp = {
                        "jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": text}]},
                    }'''

all_ok &= report(old_dispatch in server_src, "anchor de los 4 dispatch elif encontrado")

if all_ok and not DRY:
    server_src = server_src.replace(old_schemas, new_schemas)
    server_src = server_src.replace(old_dispatch, new_dispatch)
    backup(SERVER)
    SERVER.write_text(server_src)

# ---------------------------------------------------------------- run_all_validations.py
HARNESS = Path("run_all_validations.py")
harness_src = HARNESS.read_text()

m = re.search(r"FLAT_SIGNATURE_TOOLS\s*=\s*\{([^}]*)\}", harness_src)
if m is None:
    all_ok = report(False, "no encontre FLAT_SIGNATURE_TOOLS como set literal -- revisar a mano")
else:
    block = m.group(0)
    already = all(name in block for name in
                  ('"octave_run"', '"octave_eval_expr"', '"octave_run_script"', '"octave_version"'))
    report(True, f"FLAT_SIGNATURE_TOOLS encontrado (ya con las 4: {already})")
    if not already and not DRY:
        new_block = block[:-1].rstrip()
        if not new_block.endswith(",") and not new_block.endswith("{"):
            new_block += ","
        new_block += ' "octave_run", "octave_eval_expr", "octave_run_script", "octave_version",}'
        harness_src = harness_src.replace(block, new_block)
        backup(HARNESS)
        HARNESS.write_text(harness_src)

print()
if DRY:
    print("--dry-run: no escribi nada. Corre sin esa flag para aplicar.")
else:
    print("Aplicado (si todos los anchors dieron OK). Backups .bak generados.")
