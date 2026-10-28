"""
pari_gp_tool.py

PARI/GP (via cypari, wheel manylinux con libpari incluido) como CAS de
teoria algebraica de numeros, curvas elipticas y aritmetica de precision
arbitraria. Complementa a maxima/sagebrush/lispium en validacion cruzada.

Cada llamada corre en un subprocess aislado (timeout duro, un cuelgue o
crash de libpari no tumba el servidor). Sintaxis: GP estandar.

Modos:
- compute: expr (string GP) -> resultado como string + tipo PARI.
  precision = digitos decimales de los reales (default 38).
- validate: autochequeos contra referencias analiticas conocidas.
"""

import json
import subprocess
import sys

from tool_registry import register_tool

_RUNNER = (
    "import sys, json\n"
    "from cypari import pari\n"
    "req = json.loads(sys.stdin.read())\n"
    "pari.set_real_precision(req[\"precision\"])\n"
    "try:\n"
    "    r = pari(req[\"expr\"])\n"
    "    out = {\"ok\": True, \"result\": str(r), \"type\": str(r.type())}\n"
    "except Exception as exc:\n"
    "    out = {\"ok\": False, \"error\": str(exc)}\n"
    "print(\"<<J>>\" + json.dumps(out))\n"
)

PARI_GP_TOOL_SCHEMA = {
    "name": "pari_gp_tool",
    "description": (
        "CAS PARI/GP (via cypari) para teoria de numeros: factorizacion, "
        "primalidad, cuerpos numericos (nfinit/bnfinit, discriminante, numero "
        "de clases), curvas elipticas (ellinit, conductor), funciones "
        "aritmeticas y reales de precision arbitraria. Modos: compute (expr "
        "en sintaxis GP) y validate (autochequeos contra referencias "
        "analiticas conocidas)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["compute", "validate"]},
            "expr": {
                "type": "string",
                "description": "Expresion GP, ej: factor(2^64-1) o bnfinit(x^2+23).no",
            },
            "precision": {
                "type": "integer",
                "description": "Digitos decimales de los reales (default 38).",
            },
            "timeout": {"type": "integer", "description": "Segundos (default 30)."},
        },
        "required": ["mode"],
    },
}


def _eval(expr, timeout=30, precision=38):
    if not isinstance(expr, str) or not expr.strip():
        raise ValueError("compute requiere expr (string GP)")
    payload = json.dumps({"expr": expr, "precision": int(precision)})
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _RUNNER],
            input=payload, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise ValueError(f"PARI no respondio en {timeout}s")
    for ln in reversed((proc.stdout or "").splitlines()):
        if ln.startswith("<<J>>"):
            return {"input": expr, "engine": "PARI/GP (cypari)", **json.loads(ln[5:])}
    err = ((proc.stderr or "").strip().splitlines() or ["sin salida"])[-1]
    raise ValueError(f"cypari no disponible o fallo el subprocess: {err}")


def _validate():
    checks = []

    def chk(name, expr, expected, precision=38, mode="eq"):
        try:
            r = _eval(expr, 30, precision)
            got = r.get("result") if r.get("ok") else "ERROR: " + str(r.get("error"))
            if mode == "prefix":
                passed = r.get("ok") and got.startswith(expected)
            elif mode == "error":
                passed = r.get("ok") is False
            else:
                passed = r.get("ok") and got == expected
        except Exception as exc:  # noqa: BLE001
            passed, got = False, f"{type(exc).__name__}: {exc}"
        checks.append({"name": name, "passed": bool(passed), "got": str(got)[:120], "expected": expected})

    chk("factor_2_64_minus_1", "factor(2^64-1)",
        "[3, 1; 5, 1; 17, 1; 257, 1; 641, 1; 65537, 1; 6700417, 1]")
    chk("isprime_mersenne_61", "isprime(2^61-1)", "1")
    chk("eulerphi_100", "eulerphi(100)", "40")
    chk("sigma_28_perfecto", "sigma(28)", "56")
    chk("nfdisc_x2_mas_1", "nfdisc(x^2+1)", "-4")
    chk("clase_Q_sqrt_menos_23", "bnfinit(x^2+23).no", "3")
    chk("conductor_curva_11a1", "ellglobalred(ellinit([0,-1,1,-10,-20]))[1]", "11")
    chk("zeta2_igual_pi2_sobre_6", "abs(zeta(2)-Pi^2/6) < 10^-30", "1")
    chk("pi_50_digitos", "Pi", "3.14159265358979323846264338327950288419716939937", 50, "prefix")
    chk("error_no_revienta", "1/0", "-", 38, "error")
    return {
        "mode": "validate",
        "validation_passed": all(c["passed"] for c in checks),
        "checks": checks,
        "engine": "PARI/GP (cypari)",
    }


def _handler(args):
    mode = args.get("mode")
    if mode == "validate":
        return _validate()
    if mode == "compute":
        return _eval(args.get("expr"), int(args.get("timeout") or 30), args.get("precision") or 38)
    raise ValueError("mode debe ser compute o validate")


register_tool(name="pari_gp_tool", schema=PARI_GP_TOOL_SCHEMA, handler=_handler)

