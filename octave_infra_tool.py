#!/usr/bin/env python3
"""
octave_infra_tool.py
Portado desde mcp-octave-real: 4 tools de infraestructura de Octave
(octave_run, octave_eval_expr, octave_run_script, octave_version) que en el
repo original vivian como funciones locales dentro de server.py, sin modulo
propio. Se extraen aca tal cual para poder importarlas en octave-mcp sin
duplicar la logica de _run_octave/_format_result.
"""
import subprocess
import tempfile
import os
from pathlib import Path

DEFAULT_TIMEOUT = 60


def _run_octave(code, working_dir=None, timeout=DEFAULT_TIMEOUT):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".m", delete=False, dir=working_dir) as f:
        f.write(code)
        script_path = f.name
    try:
        r = subprocess.run(
            ["octave", "--no-gui", "--no-init-file", script_path],
            capture_output=True, text=True, timeout=timeout,
            cwd=working_dir or os.path.expanduser("~"),
        )
        return {"stdout": r.stdout.strip(), "stderr": r.stderr.strip(), "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"Timeout tras {timeout}s", "returncode": -1}
    except FileNotFoundError:
        return {"stdout": "", "stderr": "octave no encontrado", "returncode": -2}
    finally:
        os.unlink(script_path)


def _format_result(r):
    parts = []
    if r["stdout"]:
        parts.append(r["stdout"])
    if r["stderr"]:
        parts.append("[stderr]\n" + r["stderr"])
    if r["returncode"] != 0:
        parts.append(f"[returncode: {r['returncode']}]")
    return "\n".join(parts) if parts else "(sin salida)"


def octave_run(code: str = None, timeout: int = DEFAULT_TIMEOUT, mode: str = None):
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
    return _format_result(r)


def octave_eval_expr(expression: str = None, timeout: int = DEFAULT_TIMEOUT, mode: str = None):
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
    return r["stdout"] if r["stdout"] else "(sin salida)"


def octave_run_script(script_path: str = None, timeout: int = DEFAULT_TIMEOUT, mode: str = None):
    """Ejecuta un script .m existente en disco."""
    if mode == "validate":
        import tempfile as _tempfile
        checks = []
        tmp_path = None
        try:
            with _tempfile.NamedTemporaryFile(mode="w", suffix=".m", delete=False) as f:
                f.write("disp(42)\n")
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
    return _format_result(r)


def octave_version(mode: str = None):
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
        return "Octave no encontrado"
