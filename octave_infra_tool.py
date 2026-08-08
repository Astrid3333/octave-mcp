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


def octave_run(code: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Ejecuta codigo Octave. timeout en segundos (default 60)."""
    r = _run_octave(code, timeout=timeout)
    return _format_result(r)


def octave_eval_expr(expression: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Evalua una expresion Octave con disp()."""
    r = _run_octave("disp(" + expression + ")", timeout=timeout)
    if r["returncode"] != 0:
        return _format_result(r)
    return r["stdout"] if r["stdout"] else "(sin salida)"


def octave_run_script(script_path: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Ejecuta un script .m existente en disco."""
    p = Path(script_path)
    if not p.exists():
        return "Error: no existe " + script_path
    r = _run_octave(p.read_text(), working_dir=str(p.parent), timeout=timeout)
    return _format_result(r)


def octave_version() -> str:
    """Devuelve la version de Octave instalada."""
    try:
        r = subprocess.run(["octave", "--version"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except subprocess.TimeoutExpired:
        return "Timeout consultando version de Octave"
    except FileNotFoundError:
        return "Octave no encontrado"
