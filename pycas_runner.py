"""
pycas_runner.py

Helper compartido para CAS en proceso Python (python-flint, symengine):
evalua una expresion en un subprocess aislado con timeout duro y registra
la tool (compute + validate) con el patron tool_registry.
"""

import json
import subprocess
import sys

from tool_registry import register_tool

_TEMPLATE = r"""
import sys, json
__PREAMBLE__
req = json.loads(sys.stdin.read())
try:
    r = eval(req["expr"], globals())
    out = {"ok": True, "result": str(r), "type": type(r).__name__}
except Exception as exc:
    out = {"ok": False, "error": type(exc).__name__ + ": " + str(exc)}
print("<<J>>" + json.dumps(out))
"""


def run(engine, preamble, expr, timeout=30):
    if not isinstance(expr, str) or not expr.strip():
        raise ValueError("compute requiere expr")
    code = _TEMPLATE.replace("__PREAMBLE__", preamble)
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            input=json.dumps({"expr": expr}), capture_output=True,
            text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise ValueError(f"{engine} no respondio en {timeout}s")
    for ln in reversed((proc.stdout or "").splitlines()):
        if ln.startswith("<<J>>"):
            return {"input": expr, "engine": engine, **json.loads(ln[5:])}
    err = ((proc.stderr or "").strip().splitlines() or ["sin salida"])[-1]
    raise ValueError(f"{engine}: fallo el subprocess: {err}")


def run_checks(engine, preamble, specs):
    """specs: lista de (nombre, expr, esperado, modo) con modo eq|prefix|error."""
    checks = []
    for name, expr, expected, mode in specs:
        try:
            r = run(engine, preamble, expr, 30)
            got = r["result"] if r.get("ok") else "ERROR: " + str(r.get("error"))
            if mode == "error":
                passed = r.get("ok") is False
            elif mode == "prefix":
                passed = bool(r.get("ok")) and got.startswith(expected)
            else:
                passed = bool(r.get("ok")) and got == expected
        except Exception as exc:  # noqa: BLE001
            passed, got = False, f"{type(exc).__name__}: {exc}"
        checks.append({"name": name, "passed": bool(passed), "got": str(got)[:120], "expected": expected})
    return {
        "mode": "validate",
        "validation_passed": all(c["passed"] for c in checks),
        "checks": checks,
        "engine": engine,
    }


def register_py_engine(name, engine, preamble, description, specs):
    schema = {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["compute", "validate"]},
                "expr": {"type": "string", "description": "Expresion Python del motor (compute)."},
                "timeout": {"type": "integer", "description": "Segundos (default 30)."},
            },
            "required": ["mode"],
        },
    }

    def handler(args):
        mode = args.get("mode")
        if mode == "validate":
            return run_checks(engine, preamble, specs)
        if mode == "compute":
            return run(engine, preamble, args.get("expr"), int(args.get("timeout") or 30))
        raise ValueError("mode debe ser compute o validate")

    register_tool(name=name, schema=schema, handler=handler)

