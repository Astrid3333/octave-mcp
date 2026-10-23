#!/usr/bin/env python3
"""Ciclo de ejemplo de lispium_math_tool: CAS independiente por cable MCP.

Lispium es un binario Zig autocontenido (sintaxis Lisp, sin dependencias
Python) usado como motor de segunda opinion INDEPENDIENTE de Maxima,
Sagebrush y Octave. El ejemplo encadena sobre el wire MCP real:

1. mode=validate: 16 autochequeos de la propia tool.
2. factorial(100) exacto vs math.factorial (referencia Python).
3. Pin de la ventana float de factorial (18! imprime float).
4. solve de cuartica x^4-10x^2+9 -> raices {+-1, +-3}.
5. Verificacion en el propio motor: cada raiz satisface el polinomio.
6. Cruce con Maxima: solve debe dar el mismo conjunto de raices.
7. modpow 2^100 mod 1000003: lispium == Maxima == pow() de Python.
8. Antiderivada: maxima int(x*e^x) y lispium diff+subst en x=2
   deben normalizar a lo mismo (2*e^2).
9. factor(x^2-5x+6): lispium vs Maxima normalizados.
10. diff(x^3): lispium vs Maxima normalizados.
11. prime? cruza con sagebrush en 10^15+37 (acuerdo de dos motores).
12. Bug documentado: lispium prime?(2^61-1) devuelve 0 pero M61 es
    primo de Mersenne (sagebrush/sympy dicen True) -> desacuerdo
    esperado; para primos grandes usar sagebrush, no lispium.
13. Funcion desconocida: (fact 100) se devuelve sin evaluar, exit 0.
14. Cerrojo de parse: "(+ 1 2" -> ok=False con "Parse error".

Uso:
    .venv/bin/python examples/lispium_crosscheck.py
"""
import argparse
import json
import math
import re
import subprocess
import sys

SERVER = "/home/astrid/octave-mcp/server.py"
PYTHON = "/home/astrid/octave-mcp/.venv/bin/python"


class Wire:
    """Cliente MCP stdio mínimo (initialize + tools/call)."""

    def __init__(self):
        self.proc = subprocess.Popen(
            [PYTHON, SERVER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._id = 0
        self._send({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                    "params": {}})
        self._recv(0)

    def _send(self, payload):
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()

    def _recv(self, expect_id):
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("server.py cerró stdout")
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == expect_id:
                return msg

    def call_tool(self, name, args):
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": "tools/call",
                    "params": {"name": name, "arguments": args}})
        resp = self._recv(self._id)
        if "error" in resp:
            raise RuntimeError(f"RPC error: {resp['error']}")
        for item in resp["result"].get("content", []):
            if item.get("type") == "text":
                try:
                    return json.loads(item["text"])
                except json.JSONDecodeError:
                    return item["text"]
        return resp["result"]

    def close(self):
        self.proc.kill()


CHECKS = []


def check(label, ok, detail):
    CHECKS.append(ok)
    print(f"    {'OK  ' if ok else 'FAIL'} {label}: {detail}")
    return ok


def lis(wire, code):
    """Lispium operation=eval -> primera salida o error."""
    r = wire.call_tool("lispium_math_tool",
                       {"mode": "compute", "operation": "eval",
                        "code": code})
    return r


def out1(r):
    outs = r.get("outputs") or []
    return outs[0] if outs else None


def signed_ints(text):
    return sorted(int(x) for x in re.findall(r"-?\d+", text))


def norm_lisp_factors(text):
    return sorted(f"x-{d}" for d in re.findall(r"\(- x (\d+)\)", text))


def norm_max_factors(text):
    return sorted(f"x-{d}" for d in re.findall(r"x-(\d+)", text))


def main():
    argparse.ArgumentParser().parse_args()
    wire = Wire()
    try:
        # --- 1) autovalidacion de la tool ------------------------------
        print("[1] lispium_math_tool mode=validate")
        v = wire.call_tool("lispium_math_tool", {"mode": "validate"})
        n = len(v.get("checks", []))
        check("validate", bool(v.get("validation_passed")) and n == 17,
              f"{sum(c['passed'] for c in v.get('checks', []))}/{n} "
              f"passed, engine={v.get('engine')}")

        # --- 2) factorial exacto vs Python ----------------------------
        print("[2] factorial(100) exacto vs math.factorial")
        r = lis(wire, "(factorial 100)")
        check("100! exacto", out1(r) == str(math.factorial(100)),
              (out1(r) or str(r.get("error")))[:60] + "...")

        # --- 3) ventana float 18! (bug fijado) ------------------------
        print("[3] pin de la ventana float de factorial (n=18)")
        r = lis(wire, "(factorial 18)")
        check("18! float", out1(r) == "6.402373705728e15", str(out1(r)))

        # --- 4) solve de cuartica -------------------------------------
        print("[4] solve x^4-10x^2+9 -> {+-1, +-3}")
        r = lis(wire, "(solve (+ (^ x 4) (* -10 (^ x 2)) 9) x)")
        check("soluciones", signed_ints(out1(r) or "") == [-3, -1, 1, 3],
              str(out1(r)))

        # --- 5) cada raiz verifica el polinomio en el motor -----------
        print("[5] verificacion en motor: P(r)=0 para cada raiz")
        bad = []
        for root in (3, -3, 1, -1):
            r = lis(wire,
                    f"(simplify (substitute (+ (^ x 4) (* -10 (^ x 2)) 9) "
                    f"x {root}))")
            if out1(r) != "0":
                bad.append(f"r={root}: {out1(r)}")
        check("P(r)=0", not bad, ", ".join(bad) if bad else "4/4 raices")

        # --- 6) cruce con Maxima --------------------------------------
        print("[6] cruce solve: lispium vs Maxima")
        mx = wire.call_tool("maxima_eval_tool",
                            {"mode": "compute", "operation": "eval",
                             "expr": "solve(x^4-10*x^2+9, x)"})
        mx_txt = str(mx.get("result") or mx.get("stdout") or "")
        check("maxima coincide", signed_ints(mx_txt) == [-3, -1, 1, 3],
              mx_txt.strip())

        # --- 7) modpow triple -----------------------------------------
        print("[7] modpow 2^100 mod 1000003: lispium == Maxima == pow()")
        r = lis(wire, "(modpow 2 100 1000003)")
        lp = out1(r)
        mx = wire.call_tool("maxima_eval_tool",
                            {"mode": "compute", "operation": "eval",
                             "expr": "mod(2^100,1000003)"})
        mx_txt = str(mx.get("result") or mx.get("stdout") or "")
        ref = str(pow(2, 100, 1000003))
        check("triple acuerdo", lp == ref and ref in mx_txt,
              f"lispium={lp} maxima={mx_txt.strip()} pow={ref}")

        # --- 8) antiderivada cruzada ----------------------------------
        print("[8] antiderivada de x*e^x en x=2: dos motores, un valor")
        r = lis(wire,
                "(simplify (substitute (diff (* (- x 1) (exp x)) x) x 2))")
        lp = out1(r) or ""
        mx = wire.call_tool("maxima_eval_tool",
                            {"mode": "compute", "operation": "eval",
                             "expr": "subst(x=2, diff((x-1)*%e^x, x))"})
        mx_txt = str(mx.get("result") or mx.get("stdout") or "").strip()
        norm_lisp = (lp.replace("(* ", "").replace("(exp ", "*e^")
                      .replace(")", "").replace(" ", ""))
        norm_max = mx_txt.replace("%e", "e").replace(" ", "")
        check("normalizan a 2*e^2",
              norm_lisp == "2*e^2" and norm_max == "2*e^2",
              f"lispium={lp!r} maxima={mx_txt!r}")

        # --- 9) factor cruzado ----------------------------------------
        print("[9] factor(x^2-5x+6): lispium vs Maxima")
        r = lis(wire, "(factor (+ (^ x 2) (* -5 x) 6) x)")
        lp = out1(r) or ""
        mx = wire.call_tool("maxima_eval_tool",
                            {"mode": "compute", "operation": "eval",
                             "expr": "factor(x^2-5*x+6)"})
        mx_txt = str(mx.get("result") or mx.get("stdout") or "")
        check("mismos factores",
              norm_lisp_factors(lp) == ["x-2", "x-3"]
              and norm_max_factors(mx_txt) == ["x-2", "x-3"],
              f"lispium={lp} maxima={mx_txt.strip()}")

        # --- 10) derivada cruzada -------------------------------------
        print("[10] diff(x^3): lispium vs Maxima")
        r = lis(wire, "(diff (^ x 3) x)")
        lp = out1(r) or ""
        mx = wire.call_tool("maxima_eval_tool",
                            {"mode": "compute", "operation": "eval",
                             "expr": "diff(x^3, x)"})
        mx_txt = str(mx.get("result") or mx.get("stdout") or "").strip()
        m = re.fullmatch(r"\(\* (\d+) \(\^ x (\d+)\)\)", lp)
        norm_lisp = f"{m.group(1)}*x^{m.group(2)}" if m else lp
        check("ambos 3*x^2", norm_lisp == "3*x^2" and mx_txt == "3*x^2",
              f"lispium={lp!r} maxima={mx_txt!r}")

        # --- 11) prime? acuerdo sagebrush -----------------------------
        print("[11] prime?(10^15+37): lispium vs sagebrush (acuerdo)")
        r = lis(wire, "(prime? 1000000000000037)")
        sb = wire.call_tool("sagebrush_math_tool",
                            {"mode": "compute", "operation": "sage",
                             "code": "print(is_prime(10^15+37))"})
        sb_txt = (sb.get("stdout") or "").strip()
        check("acuerdo", out1(r) == "1" and sb_txt == "True",
              f"lispium={out1(r)} sagebrush={sb_txt}")

        # --- 12) bug documentado prime? M61 ---------------------------
        print("[12] bug documentado: prime?(2^61-1) desacuerda con sagebrush")
        r = lis(wire, "(prime? (- (^ 2 61) 1))")
        sb = wire.call_tool("sagebrush_math_tool",
                            {"mode": "compute", "operation": "sage",
                             "code": "print(is_prime(2^61 - 1))"})
        sb_txt = (sb.get("stdout") or "").strip()
        check("desacuerdo esperado (M61 es primo; lispium dice 0)",
              out1(r) == "0" and sb_txt == "True",
              f"lispium={out1(r)} sagebrush={sb_txt} "
              f"(sympy: {int(bool(__import__('sympy').isprime(2**61-1)))})")

        # --- 13) funcion desconocida silenciosa -----------------------
        print("[13] (fact 100): sin evaluar, exit 0")
        r = lis(wire, "(fact 100)")
        check("silenciosa", bool(r.get("ok")) and out1(r) == "(fact 100)",
              f"ok={r.get('ok')} out={out1(r)!r}")

        # --- 14) cerrojo de parse -------------------------------------
        print("[14] cerrojo de parse: '(+ 1 2'")
        r = lis(wire, "(+ 1 2")
        check("Parse error", (not r.get("ok")) and "Parse error"
              in str(r.get("error")), str(r.get("error"))[:80])
    finally:
        wire.close()

    ok = sum(CHECKS)
    total = len(CHECKS)
    print(f"\n{'=' * 62}\nRESULTADO: {ok}/{total} checks OK "
          f"-> {'PASS' if ok == total else 'FAIL'}")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
