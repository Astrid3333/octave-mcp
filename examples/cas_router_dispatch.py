"""Cadena de cross-checks del router unificado de CAS por Wire MCP.

Ejemplo de `cas_router_math_tool`: despacho automatico a los cuatro
motores (maxima, sagebrush, lispium, cadabra2), hint de dominio,
cadena de fallback y reporte de intentos — todo por la fachada MCP
(initialize + tools/call).

Uso:  .venv/bin/python examples/cas_router_dispatch.py
"""

import json
import subprocess
import sys

SERVER = "/home/astrid/octave-mcp/server.py"
PYTHON = "/home/astrid/octave-mcp/.venv/bin/python"


class Wire:
    """Cliente MCP stdio minimo (initialize + tools/call)."""

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
                raise RuntimeError("server.py cerro stdout")
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
            raise RuntimeError("RPC error: %s" % resp["error"])
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
    print("    %s %s: %s" % ("OK  " if ok else "FAIL", label, detail))
    return ok


def main():
    print("Cadena del router unificado de CAS por Wire MCP")
    w = Wire()
    router = "cas_router_math_tool"
    try:
        v = w.call_tool(router, {"mode": "validate"})
        check(
            "validate",
            v["validation_passed"] and v["checks_total"] == 10,
            "%d/10 checks, engine=%s" % (v["checks_passed"], v["engine"]),
        )

        r = w.call_tool(router, {"mode": "compute", "operation": "eval",
                                 "query": "diff(x^3, x)"})
        check(
            "sniff-maxima",
            r["ok"] and r["engine_used"] == "maxima",
            "diff(x^3, x) -> %s (%s) = %r" % (
                r["engine_used"], r["routed_by"], r["result"]),
        )

        r = w.call_tool(router, {"mode": "compute", "operation": "eval",
                                 "query": "print(euler_phi(100))"})
        check(
            "sniff-sagebrush",
            r["ok"] and r["engine_used"] == "sagebrush",
            "euler_phi(100) -> %s = %r" % (r["engine_used"], r["result"]),
        )

        r = w.call_tool(router, {"mode": "compute", "operation": "eval",
                                 "query": "(^ 2 10)"})
        check(
            "sniff-lispium",
            r["ok"] and r["engine_used"] == "lispium" and "1024" in r["result"],
            "(^ 2 10) -> %s = %r" % (r["engine_used"], r["result"]),
        )

        r = w.call_tool(router, {"mode": "compute", "operation": "eval",
                                 "query": "A_{m n} A^{n k}"})
        check(
            "sniff-cadabra2",
            r["ok"] and r["engine_used"] == "cadabra2",
            "A_{m n} A^{n k} -> %s = %r" % (r["engine_used"], r["result"]),
        )

        r = w.call_tool(router, {"mode": "compute", "operation": "eval",
                                 "query": "1 + 1", "engine": "maxima"})
        check(
            "explicit-engine",
            r["ok"] and r["engine_used"] == "maxima" and r["result"] == "2",
            "engine=maxima 1+1 -> %r (%s)" % (r["result"], r["routed_by"]),
        )

        r = w.call_tool(router, {"mode": "compute", "operation": "eval",
                                 "query": "(^ 2 10)", "engine": "maxima",
                                 "fallback": True})
        check(
            "fallback-chain",
            r["ok"] and r["engine_used"] == "lispium"
            and len(r["attempts"]) >= 2,
            "maxima falla -> %s tras %d intentos" % (
                r["engine_used"], len(r["attempts"])),
        )

        r = w.call_tool(router, {"mode": "compute", "operation": "eval",
                                 "query": "raise ValueError('boom')",
                                 "fallback": False})
        check(
            "no-fallback-single",
            (not r["ok"]) and len(r["attempts"]) == 1,
            "fallback=false -> %d intento, ok=%s" % (
                len(r["attempts"]), r["ok"]),
        )

        r = w.call_tool(router, {"mode": "compute", "operation": "guia"})
        check(
            "guia",
            r["ok"] and "routing" in r["guia"] and "crosscheck" in r["guia"],
            "guia con tabla de ruteo y nota de cross-check",
        )
    finally:
        w.close()

    n_ok = sum(CHECKS)
    print("    ----")
    print("    %d/%d PASS" % (n_ok, len(CHECKS)))
    return 0 if n_ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
