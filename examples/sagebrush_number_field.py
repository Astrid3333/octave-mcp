#!/usr/bin/env python3
"""Ejercicio donde sagebrush_math_tool es necesaria: teoria de numeros.

Nada mas en el servidor cubre grupos de clase, formas modulares ni
curvas elipticas (Maxima no evalua class_number, Octave sin symbolic),
y alkahest tiene su bug SIGILL en factorizacion. Cadena sobre el wire
MCP real:

1. Validacion cruzada: factor(2^64-1) y factor(x^2-5x+6) en sagebrush
   vs Maxima -> los dos motores deben dar el mismo resultado normalizado.
2. Campos numericos (exclusivo): Q(^(3)11) con grado, discriminante,
   numero de clase y regulador.
3. Formas modulares (exclusivo): newform_orbits(11, 2) -> 11.2.a.a.
4. Curvas elipticas (exclusivo): conductor de la curva 37a1 -> 37.
5. ECM: factor(2^128+1) -> dos primos grandes cuyo producto
   reconstruye 2^128+1 exacto (y Maxima debe coincidir).
6. Sesion persistente: b=7 en una llamada, b^8 en la siguiente.
7. mode=validate: 11 autochequeos de la propia tool.

Uso:
    .venv/bin/python examples/sagebrush_number_field.py
"""
import argparse
import json
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


def ints(text):
    return sorted(int(x) for x in re.findall(r"\d+", text))


def main():
    argparse.ArgumentParser().parse_args()
    wire = Wire()
    try:
        # --- 1) validacion cruzada con Maxima -------------------------
        print("[1] validacion cruzada factor(2^64-1): sagebrush vs Maxima")
        sb = wire.call_tool(
            "sagebrush_math_tool",
            {"mode": "compute", "operation": "factor", "n": "2^64 - 1"},
        )
        mx = wire.call_tool(
            "maxima_eval_tool",
            {"mode": "compute", "operation": "eval",
             "expr": "factor(2^64-1)"},
        )
        sb_out, mx_out = sb.get("stdout", ""), str(mx.get("result") or mx.get("stdout") or "")
        check("sagebrush", ints(sb_out) == [3, 5, 17, 257, 641, 65537,
                                            6700417], sb_out.strip())
        check("maxima coincide", ints(sb_out) == ints(mx_out),
              mx_out.strip())

        print("[2] validacion cruzada factor(x^2-5x+6)")
        sb = wire.call_tool(
            "sagebrush_math_tool",
            {"mode": "compute", "operation": "sage",
             "code": "R.<x> = QQ[]\nprint(factor(x^2 - 5*x + 6))"},
        )
        mx = wire.call_tool(
            "maxima_eval_tool",
            {"mode": "compute", "operation": "eval",
             "expr": "factor(x^2-5*x+6)"},
        )
        def norm(s):
            return sorted(t.strip().replace(" ", "")
                          for t in s.split("*") if t.strip())
        check("sagebrush", norm(sb.get("stdout", "")) == ["(x-2)", "(x-3)"],
              sb.get("stdout", "").strip())
        mx2 = str(mx.get("result") or mx.get("stdout") or "")
        check("maxima coincide", norm(mx2) == ["(x-2)", "(x-3)"],
              mx2.strip())

        # --- 3) campo numerico (exclusivo) ----------------------------
        print("[3] numero de clase de Q(^(3)11) (exclusivo sagebrush)")
        nf = wire.call_tool(
            "sagebrush_math_tool",
            {"mode": "compute", "operation": "number_field",
             "polynomial": "x^3 - 11"},
        )
        out = nf.get("stdout", "")
        if nf.get("error"):
            print(f"    error: {nf['error']}")
        deg = re.search(r"degree:\s*(-?\d+)", out)
        disc = re.search(r"discriminant:\s*(-?\d+)", out)
        cl = re.search(r"class number:\s*(\d+)", out)
        reg = re.search(r"regulator:\s*([0-9.]+)", out)
        check("grado", bool(deg) and deg.group(1) == "3",
              deg.group(1) if deg else "ausente")
        check("discriminante", bool(disc) and disc.group(1) == "-3267",
              disc.group(1) if disc else "ausente")
        check("numero de clase", bool(cl) and cl.group(1) == "2",
              cl.group(1) if cl else "ausente")
        check("regulador ~5.587",
              bool(reg) and 5.5 < float(reg.group(1)) < 5.7,
              reg.group(1) if reg else "ausente")

        # --- 4) formas modulares (exclusivo) --------------------------
        print("[4] newform_orbits(11, 2) (exclusivo sagebrush)")
        nf = wire.call_tool(
            "sagebrush_math_tool",
            {"mode": "compute", "operation": "newforms",
             "level": 11, "weight": 2},
        )
        out = nf.get("stdout", "")
        check("orbita 11.2.a.a dimension 1",
              "11.2.a.a" in out and "dimension 1" in out,
              out.splitlines()[0] if out.strip() else "vacío")

        # --- 5) curva eliptica (exclusivo) ----------------------------
        print("[5] conductor de la curva 37a1 (exclusivo sagebrush)")
        el = wire.call_tool(
            "sagebrush_math_tool",
            {"mode": "compute", "operation": "sage",
             "code": "E = EllipticCurve([0, 0, 1, -1, 0])\n"
                     "print(E.conductor())"},
        )
        check("conductor", el.get("stdout", "").strip() == "37",
              el.get("stdout", "").strip() or str(el.get("error", "")))

        # --- 6) ECM grande + reconstruccion exacta --------------------
        print("[6] factor(2^128+1) por ECM y recomposicion exacta")
        big = 2 ** 128 + 1
        sb = wire.call_tool(
            "sagebrush_math_tool",
            {"mode": "compute", "operation": "factor", "n": "2^128 + 1"},
        )
        fac = [int(x) for x in re.findall(r"\d+", sb.get("stdout", ""))]
        mx = wire.call_tool(
            "maxima_eval_tool",
            {"mode": "compute", "operation": "eval",
             "expr": "factor(2^128+1)"},
        )
        check("dos factores primos grandes",
              len(fac) == 2 and all(f > 10 ** 15 for f in fac),
              sb.get("stdout", "").strip())
        check("producto == 2^128+1", fac and math_prod(fac) == big,
              f"{len(fac)} factores")
        mx2 = str(mx.get("result") or mx.get("stdout") or "")
        check("maxima coincide", ints(mx2) == sorted(fac), mx2.strip())

        # --- 7) sesion persistente ------------------------------------
        print("[7] sesion persistente entre llamadas")
        wire.call_tool("sagebrush_math_tool",
                       {"mode": "compute", "operation": "sage",
                        "code": "b = 7"})
        r = wire.call_tool("sagebrush_math_tool",
                           {"mode": "compute", "operation": "sage",
                            "code": "print(b^8)"})
        check("b^8 == 5764801", r.get("stdout", "").strip() == "5764801",
              r.get("stdout", "").strip())

        # --- 8) autovalidacion de la tool -----------------------------
        print("[8] sagebrush_math_tool mode=validate")
        v = wire.call_tool("sagebrush_math_tool", {"mode": "validate"})
        n = len(v.get("checks", []))
        check("validate", bool(v.get("validation_passed")) and n == 11,
              f"{sum(c['passed'] for c in v.get('checks', []))}/{n} "
              f"passed, engine={v.get('engine')}")
    finally:
        wire.close()

    ok = sum(CHECKS)
    total = len(CHECKS)
    print(f"\n{'=' * 62}\nRESULTADO: {ok}/{total} checks OK "
          f"-> {'PASS' if ok == total else 'FAIL'}")
    return 0 if ok == total else 1


def math_prod(xs):
    p = 1
    for x in xs:
        p *= x
    return p


if __name__ == "__main__":
    sys.exit(main())
