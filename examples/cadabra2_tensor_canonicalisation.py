"""Cadena de cross-checks de Cadabra2 2.6.0 por Wire MCP.

Ejemplo de `cadabra2_math_tool`: algebra tensorial, fermiones de
Grassmann, substitute, puente sympy y cercas de error — todo por la
fachada MCP (initialize + tools/call), sin tocar el modulo directamente.

Uso:  .venv/bin/python examples/cadabra2_tensor_canonicalisation.py
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
    print("Cadena Cadabra2 2.6.0 por Wire MCP")
    w = Wire()
    try:
        v = w.call_tool("cadabra2_math_tool", {"mode": "validate"})
        check(
            "validate",
            v["validation_passed"] and len(v["checks"]) == 18,
            "%d/18 checks, engine=%s" % (
                sum(1 for c in v["checks"] if c["passed"]), v["engine"]),
        )

        r = w.call_tool("cadabra2_math_tool", {
            "mode": "compute", "operation": "eval",
            "code": (
                "AntiSymmetric(Ex('A_{m n}'))\n"
                "print(str(canonicalise(Ex('A_{n m}'))))"
            ),
        })
        check(
            "antisym",
            r["ok"] and r["stdout"].strip() == "-A_{m n}",
            "canonicalise(A_{n m}) -> %r" % r["stdout"].strip(),
        )

        r = w.call_tool("cadabra2_math_tool", {
            "mode": "compute", "operation": "eval",
            "code": (
                "Indices(Ex('m, n, k'), Ex('position = fixed'))\n"
                "Metric(Ex('g_{m n}'))\n"
                "print(str(eliminate_metric(Ex('g_{m n} g^{n k}'))))"
            ),
        })
        check(
            "metric",
            r["ok"] and r["stdout"].strip() == "g_{m}^{k}",
            "eliminate_metric(g_{m n} g^{n k}) -> %r" % r["stdout"].strip(),
        )

        r = w.call_tool("cadabra2_math_tool", {
            "mode": "compute", "operation": "eval",
            "code": (
                "SortOrder(Ex(r'\\psi_1, \\psi_2'))\n"
                "AntiCommuting(Ex(r'\\psi_1, \\psi_2'))\n"
                "ex = Ex(r'\\psi_1 \\psi_2 + \\psi_2 \\psi_1')\n"
                "sort_product(ex)\n"
                "collect_terms(ex)\n"
                "print(str(ex))"
            ),
        })
        check(
            "grassmann",
            r["ok"] and r["stdout"].strip() == "0",
            "psi_1 psi_2 + psi_2 psi_1 -> %r" % r["stdout"].strip(),
        )

        r = w.call_tool("cadabra2_math_tool", {
            "mode": "compute", "operation": "simplify",
            "ex": "(x + 1)**2 - x**2 - 2*x - 1",
        })
        check(
            "simplify",
            r["ok"] and r["result"] == "0",
            "simplify -> %r" % r["result"],
        )

        r = w.call_tool("cadabra2_math_tool", {
            "mode": "compute", "operation": "substitute",
            "ex": "x^2 + y", "rule": "x^2 = a",
        })
        check(
            "substitute-patron",
            r["ok"] and r["result"] == "a + y",
            "substitute(x^2 = a) -> %r" % r["result"],
        )

        r = w.call_tool("cadabra2_math_tool", {
            "mode": "compute", "operation": "substitute",
            "ex": "x^2 + y", "rule": "x = a + b",
        })
        check(
            "substitute-base-pin",
            r["ok"] and r["result"] == "x^{2} + y",
            "base de potencia NO reemplazada (pin) -> %r" % r["result"],
        )

        r = w.call_tool("cadabra2_math_tool", {
            "mode": "compute", "operation": "eval",
            "code": (
                "print(str(Ex('1 + 1')))\n"
                "print(str(evaluate(Ex('1 + 1'))))"
            ),
        })
        check(
            "evaluate-vs-raw",
            r["ok"] and r["stdout"].split() == ["1", "+", "1", "2"],
            "crudo no evalua, evaluate -> 2 (%r)" % r["stdout"].strip(),
        )

        r = w.call_tool("cadabra2_math_tool", {
            "mode": "compute", "operation": "to_sympy",
            "ex": "(x + 1)*(x - 1)",
        })
        got = r.get("result", "")
        import sympy as sp
        want = sp.sstr(sp.expand(sp.sympify("(x + 1)*(x - 1)")))
        check(
            "sympy-bridge",
            r["ok"] and sp.expand(sp.sympify(got)) == sp.expand(sp.sympify(want)),
            "to_sympy((x+1)*(x-1)) -> %r == sympy %r" % (got, want),
        )

        r = w.call_tool("cadabra2_math_tool", {
            "mode": "compute", "operation": "eval",
            "code": (
                "import sympy as _sp\n"
                "print(_sp.sstr(SympyBridge(Ex('x^2')).to_sympy()))"
            ),
        })
        check(
            "sympy-bridge-power-bug",
            r["ok"] and r["stdout"].strip() == "x(UP2)",
            "x^2 -> 'x(UP2)' en el bridge (pin) -> %r" % r["stdout"].strip(),
        )

        r = w.call_tool("cadabra2_math_tool", {
            "mode": "compute", "operation": "eval",
            "code": "raise RuntimeError('fence')",
        })
        check(
            "error-fence-subprocess",
            (not r["ok"]) and "RuntimeError" in (r.get("stderr") or ""),
            "ok=False + stderr RuntimeError (%r)" % (r.get("error") or ""),
        )

        r = w.call_tool("cadabra2_math_tool", {
            "mode": "compute", "operation": "canonicalise",
        })
        check(
            "error-fence-handler",
            isinstance(r, str) and "ValueError" in r and "requiere ex" in r,
            "handler ValueError como texto isError (%r)" % str(r)[:70],
        )
    finally:
        w.close()

    n_ok = sum(CHECKS)
    print("    ----")
    print("    %d/%d PASS" % (n_ok, len(CHECKS)))
    return 0 if n_ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
